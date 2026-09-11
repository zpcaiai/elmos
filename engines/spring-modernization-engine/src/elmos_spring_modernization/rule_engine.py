from __future__ import annotations
import os
import re
import difflib
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Set
from .models import MigrationRule, FileChange, MigrationPlan, MigrationResult, RiskLevel

class RuleEngine:
    """
    Production-grade rule application engine for Spring modernization.
    Applies AST/pattern rewrites, generates unified diff previews,
    tracks applied/skipped rules, and validates migration outcomes.
    """

    ELIGIBLE_EXTENSIONS = {
        ".java", ".xml", ".properties", ".yaml", ".yml", ".gradle", ".kt", ".groovy"
    }

    def apply_rule(self, file_content: str, rule: MigrationRule) -> Tuple[str, int]:
        """
        Applies a single migration rule to file content.
        Supports both exact string replacement and regex pattern replacement.
        """
        if not rule.source_pattern or not file_content:
            return file_content, 0

        # Check if source_pattern is regex (starts with regex: or contains unescaped regex characters)
        is_regex = rule.source_pattern.startswith("regex:")
        pattern = rule.source_pattern[6:] if is_regex else rule.source_pattern
        target = rule.target_pattern

        if is_regex:
            try:
                new_content, count = re.subn(pattern, target, file_content)
                return new_content, count
            except re.error:
                # Fallback to literal if regex fails
                pass

        if rule.source_pattern in file_content:
            count = file_content.count(rule.source_pattern)
            new_content = file_content.replace(rule.source_pattern, rule.target_pattern)
            return new_content, count

        return file_content, 0

    def apply_rules_to_file(
        self,
        file_path: str,
        rules: List[MigrationRule],
        dry_run: bool = False
    ) -> List[FileChange]:
        """
        Applies a sequence of migration rules to a specific file on disk.
        Returns a list of FileChange descriptors with diff previews.
        If dry_run is False, updates the file in-place.
        """
        p = Path(file_path)
        if not p.is_file():
            return []

        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()
        except OSError:
            return []

        current_content = original_content
        applied_rules_for_file = []
        total_replacements = 0

        for rule in rules:
            new_content, count = self.apply_rule(current_content, rule)
            if count > 0:
                current_content = new_content
                total_replacements += count
                applied_rules_for_file.append(rule.rule_id)

        if total_replacements == 0:
            return []

        # Generate unified diff preview
        diff_lines = list(difflib.unified_diff(
            original_content.splitlines(keepends=True),
            current_content.splitlines(keepends=True),
            fromfile=f"a/{p.name}",
            tofile=f"b/{p.name}"
        ))
        diff_preview = "".join(diff_lines)

        if not dry_run:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(current_content)
            except OSError as e:
                # If write fails, file is untouched
                pass

        change = FileChange(
            file_path=str(p.resolve()),
            change_type="MODIFY",
            description=f"Applied {total_replacements} replacements ({', '.join(applied_rules_for_file)})",
            diff_preview=diff_preview
        )
        return [change]

    def apply_plan(
        self,
        project_root: str,
        plan: MigrationPlan,
        dry_run: bool = True
    ) -> MigrationResult:
        """
        Applies an entire MigrationPlan to a project directory.
        Scans all source, config, and build files, executes relevant rules,
        and aggregates applied, skipped, and failed rules.
        """
        root = Path(project_root)
        if not root.exists():
            return MigrationResult(
                plan_id=plan.plan_id,
                applied_rules=[],
                skipped_rules=[r.rule_id for r in plan.rules],
                failed_rules=[],
                file_changes=[],
                warnings=[f"Project root does not exist: {project_root}"]
            )

        # Collect eligible files
        eligible_files: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden and target directories
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"target", "build", "node_modules", ".venv"}]
            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix in self.ELIGIBLE_EXTENSIONS:
                    eligible_files.append(p)

        applied_rules_set: Set[str] = set()
        file_changes: List[FileChange] = []
        warnings: List[str] = []
        failed_rules_set: Set[str] = set()

        for file_path in eligible_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                modified_content = content
                file_modified = False
                rules_applied_to_file = []
                replacements_count = 0

                for rule in plan.rules:
                    try:
                        new_content, count = self.apply_rule(modified_content, rule)
                        if count > 0:
                            modified_content = new_content
                            replacements_count += count
                            rules_applied_to_file.append(rule.rule_id)
                            applied_rules_set.add(rule.rule_id)
                            file_modified = True
                    except Exception as e:
                        failed_rules_set.add(rule.rule_id)
                        warnings.append(f"Error applying rule {rule.rule_id} to {file_path.name}: {e}")

                if file_modified:
                    diff_lines = list(difflib.unified_diff(
                        content.splitlines(keepends=True),
                        modified_content.splitlines(keepends=True),
                        fromfile=f"a/{file_path.name}",
                        tofile=f"b/{file_path.name}"
                    ))
                    diff_preview = "".join(diff_lines)

                    if not dry_run:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(modified_content)

                    file_changes.append(FileChange(
                        file_path=str(file_path.resolve()),
                        change_type="MODIFY",
                        description=f"Applied {replacements_count} changes: {', '.join(rules_applied_to_file)}",
                        diff_preview=diff_preview
                    ))
            except Exception as e:
                warnings.append(f"Failed to process file {file_path}: {e}")

        all_rule_ids = {r.rule_id for r in plan.rules}
        skipped_rules_set = all_rule_ids - applied_rules_set - failed_rules_set

        return MigrationResult(
            plan_id=plan.plan_id,
            applied_rules=sorted(list(applied_rules_set)),
            skipped_rules=sorted(list(skipped_rules_set)),
            failed_rules=sorted(list(failed_rules_set)),
            file_changes=file_changes,
            warnings=warnings
        )

    def validate_result(self, project_root: str, result: MigrationResult) -> Dict[str, Any]:
        """
        Validates the modernized codebase to check for residual legacy patterns,
        rule failure statuses, and structural compliance.
        """
        root = Path(project_root)
        issues: List[str] = []

        if result.failed_rules:
            issues.append(f"{len(result.failed_rules)} rules failed during execution: {result.failed_rules}")

        if not root.exists():
            return {
                "valid": False,
                "issues": [f"Project directory {project_root} not found"],
                "residual_legacy_count": 0,
                "files_checked": 0
            }

        # Scan for lingering legacy patterns that should have been eradicated
        forbidden_signatures = [
            ("javax.persistence.", "Unmigrated javax.persistence imports remain"),
            ("javax.servlet.", "Unmigrated javax.servlet imports remain"),
            ("WebSecurityConfigurerAdapter", "Deprecated WebSecurityConfigurerAdapter still referenced"),
            ("org.junit.Test", "JUnit 4 org.junit.Test remains unconverted to JUnit Jupiter"),
            ("<java.version>1.8</java.version>", "Java 8 target remains in Maven POM"),
        ]

        files_checked = 0
        residual_count = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"target", "build", "node_modules", ".venv"}]
            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix in self.ELIGIBLE_EXTENSIONS:
                    files_checked += 1
                    try:
                        with open(p, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        for sig, msg in forbidden_signatures:
                            if sig in content:
                                residual_count += 1
                                issues.append(f"{p.name}: {msg}")
                    except OSError:
                        pass

        is_valid = len(issues) == 0
        return {
            "valid": is_valid,
            "issues": issues,
            "residual_legacy_count": residual_count,
            "files_checked": files_checked
        }
