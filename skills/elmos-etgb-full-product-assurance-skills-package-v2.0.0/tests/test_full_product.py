from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from etgb.features import feature_coverage_report
from etgb.io import iter_cases, package_root


def test_full_product_feature_registry_and_bindings() -> None:
    root = package_root()
    report = feature_coverage_report(root)
    assert report["complete"] is True, report["errors"][:20]
    assert report["feature_count"] == 1452
    assert report["domain_count"] == 23
    assert report["coverage_ratio"] == 1.0
    assert report["expected_case_bindings"] == 23232
    assert report["actual_case_bindings"] == 23232


def test_journeys_standards_and_adapter_catalog() -> None:
    root = package_root()
    journeys = yaml.safe_load((root / "matrices/product-journeys.yaml").read_text(encoding="utf-8"))
    standards = yaml.safe_load((root / "matrices/standards-controls.yaml").read_text(encoding="utf-8"))
    adapters = yaml.safe_load((root / "integrations/harness/full-product-adapters.yaml").read_text(encoding="utf-8"))
    assert len(journeys["journeys"]) == 41
    assert len(journeys["personas"]) == 5
    assert len(journeys["variants"]) == 3
    assert len(standards["profiles"]) == 11
    assert sum(len(profile["controls"]) for profile in standards["profiles"]) == 100
    assert len(adapters["adapters"]) == 25
    assert all(item["release_blocking"] for item in adapters["adapters"])


def test_new_governed_documents_match_schemas() -> None:
    root = package_root()
    pairs = [
        ("matrices/feature-registry.yaml", "feature-registry.schema.json"),
        ("matrices/product-journeys.yaml", "product-journey.schema.json"),
        ("matrices/standards-controls.yaml", "standards-profile.schema.json"),
        ("integrations/harness/full-product-adapters.yaml", "adapter-conformance.schema.json"),
    ]
    for document, schema_name in pairs:
        value = yaml.safe_load((root / document).read_text(encoding="utf-8"))
        schema = json.loads((root / "schemas" / schema_name).read_text(encoding="utf-8"))
        assert list(Draft202012Validator(schema).iter_errors(value)) == []


def test_every_product_adapter_is_used_by_cases() -> None:
    root = package_root()
    catalog = yaml.safe_load((root / "integrations/harness/full-product-adapters.yaml").read_text(encoding="utf-8"))
    declared = {item["id"] for item in catalog["adapters"]}
    used = {
        case["execution"]["adapter"]
        for case in iter_cases(root)
        if case["business_line"] not in {
            "spring-modernization", "cross-language", "project-generation", "sql-conversion", "cross-cutting"
        } and "smoke" not in case["profiles"]
    }
    assert declared == used


def test_all_json_schemas_are_meta_valid() -> None:
    root = package_root()
    for path in (root / "schemas").glob("*.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
