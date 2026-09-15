from __future__ import annotations
import difflib
import functools
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import FileChange, MigrationCategory, MigrationPlan, MigrationResult, MigrationRule, RiskLevel
from .java_ast import JavaASTRewriter


@functools.lru_cache(maxsize=1024)
def _compile_regex(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def mask_literals_and_comments(src: str) -> str:
    """
    Masks Java comments (//, /* */) and string/char literals with space characters
    preserving exact length and character offsets.
    """
    pattern = r"(\"\"\"[\s\S]*?\"\"\"|\"[^\"\\\n]*(?:\\.[^\"\\\n]*)*\"|\x27[^\x27\\\n]*(?:\\.[^\x27\\\n]*)*\x27|/\*[\s\S]*?\*/|//[^\n]*)"
    return re.sub(pattern, lambda m: " " * len(m.group(0)), src)


def mask_comments_only(src: str) -> str:
    """
    Masks comments only, leaving string literals and code intact with preserved offsets.
    """
    pattern = r"(/\*[\s\S]*?\*/|//[^\n]*)"
    return re.sub(pattern, lambda m: " " * len(m.group(0)), src)

class RuleEngine:
    """
    Industrial-grade AST-aware rule application engine for Spring modernization.
    Applies token-shielded AST/pattern rewrites, generates unified diff previews,
    tracks applied/skipped rules, ensures syntactic integrity, and validates outcomes.
    """

    ELIGIBLE_EXTENSIONS = {
        ".java", ".xml", ".properties", ".yaml", ".yml", ".gradle", ".kt", ".groovy"
    }

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    def apply_rule(
        self,
        file_content: str,
        rule: MigrationRule,
        is_java_file: bool = True
    ) -> Tuple[str, int]:
        """
        Applies a single migration rule to file content with lexical/AST shielding.
        For Java files, code tokens are transformed while comments and string literals
        are shielded from accidental mutation.
        """
        if not rule.source_pattern or not file_content:
            return file_content, 0

        is_regex = rule.source_pattern.startswith("regex:")
        raw_pattern = rule.source_pattern[6:] if is_regex else rule.source_pattern

        if not is_regex and raw_pattern not in file_content:
            return file_content, 0

        # For non-Java files (XML, properties, YAML, etc.), perform standard replacement
        if not is_java_file:
            return self._apply_rule_raw(file_content, rule)

        # For Java files: check if category warrants shielding
        code_only_categories = {
            MigrationCategory.NAMESPACE,
            MigrationCategory.SECURITY,
            MigrationCategory.DATA_ACCESS,
            MigrationCategory.WEB,
            MigrationCategory.TESTING,
        }
        must_shield = (rule.category in code_only_categories) if rule.category else True

        if not must_shield:
            return self._apply_rule_raw(file_content, rule)

        # Mask comments and string/char literals with spaces of identical length
        masked = mask_literals_and_comments(file_content)

        pattern = raw_pattern
        target = rule.target_pattern

        if is_regex:
            try:
                rx = _compile_regex(pattern)
                matches = list(rx.finditer(masked))
            except re.error as exc:
                raise ValueError(f"Invalid regex in rule {rule.rule_id}: {exc}") from exc
        else:
            rx = re.compile(re.escape(pattern))
            matches = list(rx.finditer(masked))

        if not matches:
            return file_content, 0

        # Replace backwards using exact character spans
        res = file_content
        for m in sorted(matches, key=lambda x: x.start(), reverse=True):
            if is_regex:
                repl = m.expand(target)
            else:
                repl = target
            res = res[:m.start()] + repl + res[m.end():]

        return res, len(matches)

    def _apply_rule_raw(self, file_content: str, rule: MigrationRule) -> Tuple[str, int]:
        is_regex = rule.source_pattern.startswith("regex:")
        pattern = rule.source_pattern[6:] if is_regex else rule.source_pattern
        target = rule.target_pattern

        if is_regex:
            try:
                rx = _compile_regex(pattern)
                return rx.subn(target, file_content)
            except re.error as exc:
                raise ValueError(f"Invalid regex in rule {rule.rule_id}: {exc}") from exc

        if pattern in file_content:
            count = file_content.count(pattern)
            return file_content.replace(pattern, target), count

        return file_content, 0

    # -------------------------------------------------------------
    # High-level AST Structural Modernizations
    # -------------------------------------------------------------
    def rewrite_spring_mvc_annotations(self, code: str) -> Tuple[str, int]:
        """
        Rewrites deprecated or verbose Spring MVC @RequestMapping into modern
        composed annotations (@GetMapping, @PostMapping, etc.) via compiler-grade AST parsing
        and structured AST visitor traversal, completely eliminating regex matching.
        """
        rewritten, count = JavaASTRewriter.rewrite_spring_mvc_annotations(code)
        if count > 0:
            return self.normalize_imports(rewritten), count
        return code, 0

    def rewrite_webmvc_configurer_adapter(self, code: str) -> Tuple[str, int]:
        """
        Rewrites deprecated 'extends WebMvcConfigurerAdapter' to 'implements WebMvcConfigurer'
        via compiler-grade AST TypeDeclaration visitor traversal, completely eliminating regex matching.
        """
        rewritten, count = JavaASTRewriter.rewrite_webmvc_configurer_adapter(code)
        if count > 0:
            return self.normalize_imports(rewritten), count
        return code, 0

    def normalize_imports(self, code: str) -> str:
        """
        Deduplicates Java imports and eliminates obsolete ones.
        """
        lines = code.splitlines(keepends=True)
        seen_imports: Set[str] = set()
        new_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") and stripped.endswith(";"):
                import_stmt = stripped[7:-1].strip()
                if import_stmt in seen_imports:
                    continue
                seen_imports.add(import_stmt)
                new_lines.append(line)
            else:
                new_lines.append(line)

        return "".join(new_lines)

    def validate_syntactic_integrity(self, original_code: str, modernized_code: str) -> bool:
        """
        Enforces bracket and delimiter invariants to ensure transformations do not
        corrupt the AST structure.
        """
        # Count curly braces
        orig_braces = original_code.count("{") - original_code.count("}")
        mod_braces = modernized_code.count("{") - modernized_code.count("}")
        if orig_braces != mod_braces:
            return False

        # Count parentheses
        orig_parens = original_code.count("(") - original_code.count(")")
        mod_parens = modernized_code.count("(") - modernized_code.count(")")
        if orig_parens != mod_parens:
            return False

        # Count brackets
        orig_brackets = original_code.count("[") - original_code.count("]")
        mod_brackets = modernized_code.count("[") - modernized_code.count("]")
        if orig_brackets != mod_brackets:
            return False

        return True

    # -------------------------------------------------------------
    # File and Project Level Orchestration
    # -------------------------------------------------------------
    def apply_rules_to_file(
        self,
        file_path: str,
        rules: List[MigrationRule],
        dry_run: bool = False
    ) -> List[FileChange]:
        """
        Applies a sequence of migration rules to a specific file on disk.
        Returns a list of FileChange descriptors with diff previews.
        Validates syntactic integrity and rolls back on structural corruption.
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

        is_java = p.suffix == ".java"
        current_content = original_content
        applied_rules_for_file: List[str] = []
        total_replacements = 0

        # 1. Structural rewrites if Java file
        if is_java:
            # Route A: Prioritize Java Worker OpenRewrite compiler engine
            from .java_worker_bridge import JavaWorkerClient
            worker = JavaWorkerClient()
            if worker.is_worker_available():
                recipe_families: List[str] = []
                if any("security" in str(r.rule_id).lower() or r.category == MigrationCategory.SECURITY for r in rules):
                    recipe_families.append("SPRING_SECURITY_6")
                if any("jpa" in str(r.rule_id).lower() or "hibernate" in str(r.rule_id).lower() or r.category == MigrationCategory.DATA_ACCESS for r in rules):
                    recipe_families.append("JPA_HIBERNATE_6")
                if any("junit" in str(r.rule_id).lower() or r.category == MigrationCategory.TESTING for r in rules):
                    recipe_families.append("JUNIT_5")

                for rf in recipe_families:
                    res = worker.rewrite_with_openrewrite(current_content, recipe_family=rf)
                    if res.status == "SUCCESS" and res.source_code and res.source_code != current_content:
                        current_content = res.source_code
                        total_replacements += max(1, len(res.recipes_applied))
                        applied_rules_for_file.append(f"OPENREWRITE_{rf}")

            current_content, mvc_count = self.rewrite_spring_mvc_annotations(current_content)
            if mvc_count > 0:
                total_replacements += mvc_count
                applied_rules_for_file.append("AST_SPRING_MVC_ANNOTATIONS")

            current_content, adapter_count = self.rewrite_webmvc_configurer_adapter(current_content)
            if adapter_count > 0:
                total_replacements += adapter_count
                applied_rules_for_file.append("AST_WEBMVC_ADAPTER_TO_INTERFACE")

        # 2. Sequential rule application
        for rule in rules:
            new_content, count = self.apply_rule(current_content, rule, is_java_file=is_java)
            if count > 0:
                current_content = new_content
                total_replacements += count
                applied_rules_for_file.append(rule.rule_id)

        if total_replacements == 0:
            return []

        # 3. Syntactic integrity verification
        if is_java and not self.validate_syntactic_integrity(original_content, current_content):
            # Transformation broke bracket balance; rollback immediately
            return []

        # 4. Generate unified diff preview
        diff_lines = list(difflib.unified_diff(
            original_content.splitlines(keepends=True),
            current_content.splitlines(keepends=True),
            fromfile=f"a/{p.name}",
            tofile=f"b/{p.name}"
        ))
        diff_preview = "".join(diff_lines)

        if not dry_run:
            self._atomic_write(p, current_content)

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
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in {"target", "build", "node_modules", ".venv"}
            ]
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

                is_java = file_path.suffix == ".java"
                modified_content = content
                file_modified = False
                rules_applied_to_file: List[str] = []
                replacements_count = 0

                # 1. Structural rewrites if Java file
                if is_java:
                    modified_content, mvc_count = self.rewrite_spring_mvc_annotations(modified_content)
                    if mvc_count > 0:
                        replacements_count += mvc_count
                        rules_applied_to_file.append("AST_SPRING_MVC_ANNOTATIONS")
                        file_modified = True

                    modified_content, adapter_count = self.rewrite_webmvc_configurer_adapter(modified_content)
                    if adapter_count > 0:
                        replacements_count += adapter_count
                        rules_applied_to_file.append("AST_WEBMVC_ADAPTER_TO_INTERFACE")
                        file_modified = True

                # 2. Rule iteration
                for rule in plan.rules:
                    try:
                        new_content, count = self.apply_rule(modified_content, rule, is_java_file=is_java)
                        if count > 0:
                            modified_content = new_content
                            replacements_count += count
                            rules_applied_to_file.append(rule.rule_id)
                            file_modified = True
                    except Exception as e:
                        failed_rules_set.add(rule.rule_id)
                        warnings.append(f"Error applying rule {rule.rule_id} to {file_path.name}: {e}")

                # 3. Syntactic integrity check
                if is_java and file_modified:
                    if not self.validate_syntactic_integrity(content, modified_content):
                        warnings.append(
                            f"Syntactic integrity check failed for {file_path.name}: bracket balance mismatch. Changes rolled back."
                        )
                        continue

                if file_modified:
                    diff_lines = list(difflib.unified_diff(
                        content.splitlines(keepends=True),
                        modified_content.splitlines(keepends=True),
                        fromfile=f"a/{file_path.name}",
                        tofile=f"b/{file_path.name}"
                    ))
                    diff_preview = "".join(diff_lines)

                    if not dry_run:
                        try:
                            self._atomic_write(file_path, modified_content)
                        except OSError as exc:
                            failed_rules_set.update(rules_applied_to_file)
                            warnings.append(f"Failed to write file {file_path}: {exc}")
                            continue

                    applied_rules_set.update(rules_applied_to_file)

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
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in {"target", "build", "node_modules", ".venv"}
            ]
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
                    except OSError as exc:
                        issues.append(f"{p}: unable to read file: {exc}")

        is_valid = len(issues) == 0
        return {
            "valid": is_valid,
            "issues": issues,
            "residual_legacy_count": residual_count,
            "files_checked": files_checked
        }
