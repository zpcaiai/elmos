from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from etgb.io import iter_jsonl, suite_manifest
from etgb.features import feature_coverage_report
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

    feature_report = feature_coverage_report(root)
    errors.extend(f"feature coverage: {message}" for message in feature_report["errors"][:max_errors])

    matrix_schema_pairs = [
        ("matrices/feature-registry.yaml", "feature-registry.schema.json"),
        ("matrices/product-journeys.yaml", "product-journey.schema.json"),
        ("matrices/standards-controls.yaml", "standards-profile.schema.json"),
        ("integrations/harness/full-product-adapters.yaml", "adapter-conformance.schema.json"),
    ]
    for document_rel, schema_name in matrix_schema_pairs:
        document_path = root / document_rel
        if not document_path.exists():
            errors.append(f"missing governed document: {document_rel}")
            continue
        document = yaml.safe_load(document_path.read_text(encoding="utf-8"))
        errors.extend(
            f"{document_rel}: {error.message}"
            for error in Draft202012Validator(_schema(root, schema_name)).iter_errors(document)
        )

    product_surface_path = root / "examples/product-surface.yaml"
    if product_surface_path.exists():
        product_surface = yaml.safe_load(product_surface_path.read_text(encoding="utf-8"))
        errors.extend(
            f"examples/product-surface.yaml: {error.message}"
            for error in Draft202012Validator(_schema(root, "product-surface.schema.json")).iter_errors(product_surface)
        )

    adapter_catalog_path = root / "integrations/harness/full-product-adapters.yaml"
    if adapter_catalog_path.exists():
        adapter_catalog = yaml.safe_load(adapter_catalog_path.read_text(encoding="utf-8"))
        for adapter in adapter_catalog.get("adapters", []):
            if adapter.get("status") != "conformant":
                message = f"production adapter conformance required: {adapter.get('id')} ({adapter.get('status')})"
                (errors if release else warnings).append(message)

    required = [
        "README.md",
        "docs/SOTA_TEST_PLAN.md",
        "matrices/coverage-requirements.yaml",
        "integrations/postgres/001_etgb_schema.sql",
        "integrations/harness/adapter-contract.yaml",
        "integrations/harness/full-product-adapters.yaml",
        "integrations/postgres/003_full_product_assurance.sql",
        "integrations/postgres/004_full_product_rls.sql",
        "matrices/feature-registry.yaml",
        "matrices/product-journeys.yaml",
        "matrices/standards-controls.yaml",
        "examples/product-surface.yaml",
        "schemas/product-surface.schema.json",
        "integrations/harness/full_product_adapter_sdk.py",
        "docs/FULL_PRODUCT_TEST_PLAN.md",
        "docs/FEATURE_COVERAGE_MODEL.md",
        "docs/FUNCTION_INVENTORY.md",
        "integrations/openapi/etgb-control-plane.openapi.yaml",
        "integrations/events/etgb-events.asyncapi.yaml",
        "schemas/environment-authority.schema.json",
        "schemas/evidence-manifest.schema.json",
    ]
    for rel in required:
        if not (root / rel).exists():
            errors.append(f"missing required package artifact: {rel}")

    return {
        "valid": not errors, "release_mode": release, "case_count": total, "case_files": counts,
        "skill_count": skill_audit["skill_count"], "feature_count": feature_report["feature_count"],
        "feature_coverage_ratio": feature_report["coverage_ratio"],
        "errors": errors[:max_errors], "warnings": warnings
    }
