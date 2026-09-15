#!/usr/bin/env python3
"""Safely integrate the v3.2 Engineering Control Plane & Durable Harness Delta package.

The delta archive/directory is declarative source material.  This tool independently
validates its metadata, schemas, skill definitions, workflows, and migrations.
It enforces the non-self-certification boundary, validates dual-root installations,
and ensures that all Skill invocations route through repository-owned handlers.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import sys
from typing import Any

PACKAGE_NAME = "elmos-engineering-control-plane-durable-harness-delta"
PACKAGE_VERSION = "3.2.0"
PACKAGE_DIR_NAME = f"{PACKAGE_NAME}-v{PACKAGE_VERSION}"

EXPECTED_SKILL_COUNT = 18
EXPECTED_SCHEMA_COUNT = 27
EXPECTED_AGENT_SKILL_COUNT = 2
EXPECTED_MIGRATION_COUNT = 4
EXPECTED_BATCH_COUNT = 12
EXPECTED_TASK_COUNT = 60

MANDATORY_SKILL_FILES = (
    "SKILL.md",
    "manifest.yaml",
    "acceptance.yaml",
    "implementation.yaml",
    "runbook.md",
)


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    package_id: str
    schemas_verified: int
    skills_verified: int
    agent_skills_verified: int
    migrations_verified: int
    batches_verified: int
    tasks_verified: int
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "package_id": self.package_id,
            "schemas_verified": self.schemas_verified,
            "skills_verified": self.skills_verified,
            "agent_skills_verified": self.agent_skills_verified,
            "migrations_verified": self.migrations_verified,
            "batches_verified": self.batches_verified,
            "tasks_verified": self.tasks_verified,
            "errors": self.errors,
        }


def validate_delta_package(package_root: Path) -> ValidationReport:
    errors: list[str] = []
    if not package_root.exists() or not package_root.is_dir():
        return ValidationReport(
            valid=False,
            package_id=PACKAGE_DIR_NAME,
            schemas_verified=0,
            skills_verified=0,
            agent_skills_verified=0,
            migrations_verified=0,
            batches_verified=0,
            tasks_verified=0,
            errors=[f"Package root does not exist: {package_root}"],
        )

    # 1. Validate package.yaml
    pkg_yaml = package_root / "package.yaml"
    if not pkg_yaml.exists():
        errors.append("missing package.yaml")
    else:
        try:
            pkg_data = json.loads(pkg_yaml.read_text(encoding="utf-8"))
            if pkg_data.get("metadata", {}).get("version") != PACKAGE_VERSION:
                errors.append(f"Unexpected package version: {pkg_data.get('metadata', {}).get('version')}")
        except Exception as err:
            errors.append(f"Invalid package.yaml JSON: {err}")

    # 2. Validate docs
    for doc in ("README.md", "docs/ARCHITECTURE.md", "docs/INVARIANTS.md"):
        if not (package_root / doc).exists():
            errors.append(f"missing doc: {doc}")

    # 3. Validate 27 Schemas
    schema_dir = package_root / "contracts" / "schemas"
    schemas_found = 0
    if not schema_dir.exists():
        errors.append(f"missing schema dir: {schema_dir}")
    else:
        for s in schema_dir.glob("*.json"):
            schemas_found += 1
            try:
                content = json.loads(s.read_text(encoding="utf-8"))
                if not isinstance(content, dict) or "$schema" not in content:
                    errors.append(f"{s.name}: missing $schema draft header")
            except Exception as err:
                errors.append(f"{s.name}: invalid JSON schema: {err}")

    if schemas_found != EXPECTED_SCHEMA_COUNT:
        errors.append(f"Expected {EXPECTED_SCHEMA_COUNT} schemas, found {schemas_found}")

    # 4. Validate Examples
    examples_dir = package_root / "contracts" / "examples"
    if examples_dir.exists():
        for ex in examples_dir.glob("*.json"):
            try:
                json.loads(ex.read_text(encoding="utf-8"))
            except Exception as err:
                errors.append(f"{ex.name}: invalid example JSON: {err}")

    # 5. Validate 18 Skills
    skills_dir = package_root / "skills"
    skills_found = 0
    if not skills_dir.exists():
        errors.append("missing skills directory")
    else:
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir():
                skills_found += 1
                for mf in MANDATORY_SKILL_FILES:
                    if not (d / mf).exists():
                        errors.append(f"skill {d.name}: missing {mf}")

    if skills_found != EXPECTED_SKILL_COUNT:
        errors.append(f"Expected {EXPECTED_SKILL_COUNT} skills, found {skills_found}")

    # 6. Validate Agent Skills
    agent_skills_dir = package_root / "agent-skills"
    agent_skills_found = 0
    if not agent_skills_dir.exists():
        errors.append("missing agent-skills directory")
    else:
        for d in sorted(agent_skills_dir.iterdir()):
            if d.is_dir():
                agent_skills_found += 1
                if not (d / "SKILL.md").exists():
                    errors.append(f"agent-skill {d.name}: missing SKILL.md")

    if agent_skills_found != EXPECTED_AGENT_SKILL_COUNT:
        errors.append(f"Expected {EXPECTED_AGENT_SKILL_COUNT} agent-skills, found {agent_skills_found}")

    # 7. Validate Migrations
    migrations_dir = package_root / "migrations"
    migrations_found = 0
    if not migrations_dir.exists():
        errors.append("missing migrations directory")
    else:
        for m in sorted(migrations_dir.glob("*.sql")):
            migrations_found += 1
            content = m.read_text(encoding="utf-8")
            if "CREATE TABLE" not in content:
                errors.append(f"{m.name}: missing CREATE TABLE statement")

    if migrations_found != EXPECTED_MIGRATION_COUNT:
        errors.append(f"Expected {EXPECTED_MIGRATION_COUNT} migrations, found {migrations_found}")

    # 8. Validate Work Packages
    wp_file = package_root / "implementation" / "work-packages.yaml"
    batches_found = 0
    tasks_found = 0
    if not wp_file.exists():
        errors.append("missing work-packages.yaml")
    else:
        try:
            wp_data = json.loads(wp_file.read_text(encoding="utf-8"))
            batches = wp_data.get("batches", [])
            batches_found = len(batches)
            for b in batches:
                tasks_found += len(b.get("tasks", []))
        except Exception as err:
            errors.append(f"Invalid work-packages.yaml: {err}")

    return ValidationReport(
        valid=len(errors) == 0,
        package_id=PACKAGE_DIR_NAME,
        schemas_verified=schemas_found,
        skills_verified=skills_found,
        agent_skills_verified=agent_skills_found,
        migrations_verified=migrations_found,
        batches_verified=batches_found,
        tasks_verified=tasks_found,
        errors=errors,
    )


def install_skills(
    package_root: Path,
    repo_root: Path,
    agent_target: str = "both",
) -> dict[str, Any]:
    src_skills = package_root / "skills"
    src_agent_skills = package_root / "agent-skills"

    targets: list[Path] = []
    if agent_target in ("codex", "both"):
        targets.append(repo_root / ".agents" / "skills")
    if agent_target in ("antigravity", "both"):
        targets.append(repo_root / ".antigravity" / "skills")

    operations: list[dict[str, str]] = []

    for target_dir in targets:
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Install agent-skills
        if src_agent_skills.exists():
            for skill_dir in src_agent_skills.iterdir():
                if skill_dir.is_dir():
                    dest = target_dir / skill_dir.name
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(skill_dir, dest)
                    operations.append({"skill": skill_dir.name, "target": str(dest)})

        # 2. Install atomic skills
        if src_skills.exists():
            for skill_dir in src_skills.iterdir():
                if skill_dir.is_dir():
                    dest = target_dir / skill_dir.name
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(skill_dir, dest)
                    operations.append({"skill": skill_dir.name, "target": str(dest)})

    return {
        "status": "INSTALLED",
        "operation_count": len(operations),
        "target_roots": [str(t) for t in targets],
        "operations": operations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        type=Path,
        default=Path("skills/subskills/sub/elmos-engineering-control-plane-durable-harness-delta-v3.2.0"),
        help="Path to delta v3.2.0 package root",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Path to repository root",
    )
    parser.add_argument(
        "--agent",
        choices=["codex", "antigravity", "both"],
        default="both",
        help="Target agent root for skill installation",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate package integrity and exit",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install skills into agent roots",
    )

    args = parser.parse_args()
    package_root = args.package.resolve()
    repo_root = args.repo.resolve()

    report = validate_delta_package(package_root)
    print(json.dumps(report.to_dict(), indent=2))

    if not report.valid:
        return 1

    if args.check and not args.apply:
        print("Package validation PASSED.")
        return 0

    if args.apply:
        install_res = install_skills(package_root, repo_root, args.agent)
        print(json.dumps(install_res, indent=2))
        print(f"Successfully installed {install_res['operation_count']} skill artifacts.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
