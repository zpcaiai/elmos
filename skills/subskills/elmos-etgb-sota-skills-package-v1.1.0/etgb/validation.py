from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from etgb.io import iter_jsonl, suite_manifest
from etgb.skills import audit_skills


def _schema(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / "schemas" / name).read_text(encoding="utf-8"))


def validate_package(root: Path, *, release: bool = False, max_errors: int = 25) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    manifest = suite_manifest(root)
    suite_errors = list(Draft202012Validator(_schema(root, "suite.schema.json")).iter_errors(manifest))
    errors.extend(f"suite.yaml: {e.message}" for e in suite_errors)

    validator = Draft202012Validator(_schema(root, "test-case.schema.json"))
    seen: set[str] = set()
    counts: dict[str, int] = {}
    total = 0
    for rel in manifest["case_files"]:
        path = root / rel
        if not path.exists():
            errors.append(f"missing case file: {rel}")
            continue
        count = 0
        for number, case in enumerate(iter_jsonl(path), 1):
            total += 1
            count += 1
            if case.get("id") in seen:
                errors.append(f"duplicate id: {case.get('id')}")
            seen.add(case.get("id", ""))
            for err in validator.iter_errors(case):
                errors.append(f"{rel}:{number}:{'.'.join(map(str, err.absolute_path))}: {err.message}")
                if len(errors) >= max_errors:
                    break
            if len(errors) >= max_errors:
                break
        counts[rel] = count
        if len(errors) >= max_errors:
            break

    if total < manifest.get("expected_minimum_case_count", 1):
        errors.append(f"case count {total} is below required minimum {manifest['expected_minimum_case_count']}")

    corpus = yaml.safe_load((root / "corpora/corpus-lock.yaml").read_text(encoding="utf-8"))
    corpus_errors = list(Draft202012Validator(_schema(root, "corpus-lock.schema.json")).iter_errors(corpus))
    errors.extend(f"corpus-lock.yaml: {e.message}" for e in corpus_errors)
    for repo in corpus.get("repositories", []):
        if not re.fullmatch(r"[0-9a-f]{40}", repo.get("commit", "")):
            errors.append(f"un-pinned corpus: {repo.get('id')}")
        if repo.get("license_review") != "approved":
            message = f"corpus license review required: {repo.get('id')}"
            (errors if release else warnings).append(message)

    skill_audit = audit_skills(root)
    errors.extend(f"skills: {message}" for message in skill_audit["errors"])
    warnings.extend(f"skills: {message}" for message in skill_audit["warnings"])

    required = [
        "README.md",
        "docs/SOTA_TEST_PLAN.md",
        "matrices/coverage-requirements.yaml",
        "integrations/postgres/001_etgb_schema.sql",
        "integrations/harness/adapter-contract.yaml",
        "integrations/openapi/etgb-control-plane.openapi.yaml",
        "integrations/events/etgb-events.asyncapi.yaml",
        "schemas/environment-authority.schema.json",
        "schemas/evidence-manifest.schema.json",
    ]
    for rel in required:
        if not (root / rel).exists():
            errors.append(f"missing required package artifact: {rel}")

    return {"valid": not errors, "release_mode": release, "case_count": total, "case_files": counts, "skill_count": skill_audit["skill_count"], "errors": errors[:max_errors], "warnings": warnings}
