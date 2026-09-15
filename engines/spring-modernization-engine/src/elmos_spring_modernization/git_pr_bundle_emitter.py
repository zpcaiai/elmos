from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .semantic_diff_explainer import RiskLevel, SemanticCategory, SemanticChange, SemanticDiffReport


@dataclass
class ModernizationPR:
    pr_index: int
    branch_name: str
    title: str
    commit_message: str
    category: str
    risk_level: str
    target_files: List[str]
    verification_command: str
    description: str


@dataclass
class PRBundleManifest:
    project_id: str
    base_branch: str
    total_prs: int
    prs: List[ModernizationPR]
    output_directory: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


class GitPRBundleEmitter:
    """
    Splits large Spring modernization changesets into logical, atomic
    stacked PRs / commits for safe code review and zero-downtime deployment.
    """

    PR_ORDER_MAP = [
        (
            SemanticCategory.TOOLCHAIN_BUILD,
            "chore(build): modernize maven/gradle toolchain and java 21 baseline",
            "modernize/01-toolchain-baseline",
            "mvn clean compile -DskipTests=false",
            RiskLevel.MEDIUM,
        ),
        (
            SemanticCategory.ECOSYSTEM_DEPENDENCY,
            "refactor(deps): upgrade ecosystem dependencies for jakarta and spring boot 3",
            "modernize/02-ecosystem-dependencies",
            "mvn clean test-compile",
            RiskLevel.MEDIUM,
        ),
        (
            SemanticCategory.JAKARTA_NAMESPACE,
            "refactor(core): migrate javax namespace to jakarta ee 10",
            "modernize/03-jakarta-namespace",
            "mvn clean compile",
            RiskLevel.MEDIUM,
        ),
        (
            SemanticCategory.FRAMEWORK_CONFIGURATION,
            "refactor(config): update spring boot 3 properties and autoconfiguration",
            "modernize/04-framework-config",
            "mvn clean test-compile",
            RiskLevel.LOW,
        ),
        (
            SemanticCategory.MICROSERVICE_NETFLIX,
            "refactor(cloud): replace netflix oss with spring cloud 2023 stack",
            "modernize/05-spring-cloud-netflix-replacement",
            "mvn clean test -Dtest=*Gateway*,*Client*,*CircuitBreaker*",
            RiskLevel.HIGH,
        ),
        (
            SemanticCategory.SECURITY_AUTH,
            "refactor(security): modernize spring security 6 filter chain and oauth2",
            "modernize/06-spring-security-filterchain",
            "mvn clean test -Dtest=*Security*,*Auth*",
            RiskLevel.HIGH,
        ),
        (
            SemanticCategory.TEST_MOCKING,
            "test: modernize test suite to junit 5 and mockito 5 static mocking",
            "modernize/07-test-suite-junit5-mockito",
            "mvn clean test",
            RiskLevel.LOW,
        ),
        (
            SemanticCategory.PERSISTENCE_TRANSACTION,
            "refactor(data): update persistence and transaction managers for spring 6",
            "modernize/08-persistence-and-data",
            "mvn clean test -Dtest=*Repository*,*Dao*",
            RiskLevel.MEDIUM,
        ),
        (
            SemanticCategory.GENERAL_REFACTOR,
            "refactor(app): general cleanups and spring boot 3 deprecation fixes",
            "modernize/09-application-refactoring",
            "mvn clean verify",
            RiskLevel.LOW,
        ),
    ]

    @classmethod
    def plan_pr_splits(
        cls,
        diff_report: SemanticDiffReport,
        project_id: str = "spring-app",
        base_branch: str = "main",
    ) -> List[ModernizationPR]:
        """
        Groups file changes into distinct atomic PRs based on semantic categories.
        """
        # Bucket files by category
        category_files: Dict[SemanticCategory, List[str]] = {}
        for change in diff_report.changes:
            if change.category not in category_files:
                category_files[change.category] = []
            if change.file_path not in category_files[change.category]:
                category_files[change.category].append(change.file_path)

        planned_prs: List[ModernizationPR] = []
        pr_idx = 1

        for cat, title, branch_slug, verify_cmd, default_risk in cls.PR_ORDER_MAP:
            if cat in category_files and category_files[cat]:
                files = category_files[cat]
                # Determine risk level from changes in this category
                cat_changes = [c for c in diff_report.changes if c.category == cat]
                risk = default_risk.value
                if any(c.risk == RiskLevel.CRITICAL for c in cat_changes):
                    risk = RiskLevel.CRITICAL.value
                elif any(c.risk == RiskLevel.HIGH for c in cat_changes):
                    risk = RiskLevel.HIGH.value

                description = cls._generate_pr_description(cat, cat_changes, files, verify_cmd)
                pr = ModernizationPR(
                    pr_index=pr_idx,
                    branch_name=f"{branch_slug}",
                    title=f"[PR {pr_idx:02d}] {title}",
                    commit_message=title,
                    category=cat.value,
                    risk_level=risk,
                    target_files=files,
                    verification_command=verify_cmd,
                    description=description,
                )
                planned_prs.append(pr)
                pr_idx += 1

        return planned_prs

    @classmethod
    def _generate_pr_description(
        cls,
        category: SemanticCategory,
        changes: List[SemanticChange],
        files: List[str],
        verify_cmd: str,
    ) -> str:
        lines = [
            f"## Summary of Changes (`{category.value}`)",
            "",
            "This pull request is an automated part of the Spring Modernization upgrade pipeline.",
            "",
            "### Modified Files",
        ]
        for f in files:
            lines.append(f"- `{f}`")
        lines.append("")
        lines.append("### Key Rationales & Review Guidance")
        for c in changes:
            lines.append(f"- **{c.title}**: {c.rationale}")
            lines.append(f"  - *Reviewer Action*: {c.reviewer_guidance}")
        lines.append("")
        lines.append("### Verification Command")
        lines.append(f"```bash\n{verify_cmd}\n```")
        lines.append("")
        lines.append("### Rollback Strategy")
        lines.append("- Safe to revert independently before merging subsequent dependent PRs.")
        return "\n".join(lines)

    @classmethod
    def emit_bundle(
        cls,
        prs: List[ModernizationPR],
        output_dir: Path,
        project_id: str = "spring-app",
        base_branch: str = "main",
    ) -> PRBundleManifest:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write individual PR markdown files
        for pr in prs:
            pr_file = output_dir / f"PR_{pr.pr_index:02d}_{pr.category.lower()}.md"
            pr_file.write_text(pr.description, encoding="utf-8")

        # Write aggregated overview
        overview_lines = [
            f"# Modernization Pull Request Stack: {project_id}",
            "",
            f"Total Atomic PRs: **{len(prs)}** | Base Branch: `{base_branch}`",
            "",
            "| # | Branch | Title | Risk | Files | Verification |",
            "|---|---|---|---|---|---|",
        ]
        for pr in prs:
            overview_lines.append(
                f"| {pr.pr_index:02d} | `{pr.branch_name}` | {pr.title} | `{pr.risk_level}` | {len(pr.target_files)} | `{pr.verification_command}` |"
            )
        overview_lines.append("")

        (output_dir / "PR_STACK_OVERVIEW.md").write_text("\n".join(overview_lines), encoding="utf-8")

        manifest = PRBundleManifest(
            project_id=project_id,
            base_branch=base_branch,
            total_prs=len(prs),
            prs=prs,
            output_directory=str(output_dir.resolve()),
        )

        (output_dir / "bundle_manifest.json").write_text(manifest.to_json(), encoding="utf-8")
        return manifest
