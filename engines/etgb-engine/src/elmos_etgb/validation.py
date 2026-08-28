"""Independent package, case, matrix and run-result validation."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

import yaml
from jsonschema import Draft202012Validator

from .contracts import validate_domain_case
from .corpus import verify_lock
from .package import verify_source_package
from .skills import audit_skills


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL record is not an object: {path}:{number}")
            yield value


def load_cases(package_root: Path) -> Iterator[dict[str, Any]]:
    suite = yaml.safe_load((package_root / "suites/suite.yaml").read_text(encoding="utf-8"))
    for relative in suite.get("case_files", []):
        path = (package_root / relative).resolve(strict=True)
        try:
            path.relative_to(package_root.resolve(strict=True))
        except ValueError as exc:
            raise ValueError(f"case file escapes package root: {relative}") from exc
        yield from iter_jsonl(path)


def _expected_cells(package_root: Path) -> dict[str, set[tuple[tuple[str, str], ...]]]:
    expected: dict[str, set[tuple[tuple[str, str], ...]]] = defaultdict(set)
    def add(line: str, dimensions: dict[str, Any]) -> None:
        expected[line].add(tuple(sorted((str(key), str(value)) for key, value in dimensions.items())))
    spring = yaml.safe_load((package_root / "matrices/spring-modernization.yaml").read_text(encoding="utf-8"))
    for archetype in spring["archetypes"]:
        traits = set(archetype.get("traits", []))
        for feature in spring["features"]:
            required = set(feature.get("requires_any", []))
            if required and not traits.intersection(required):
                continue
            for variant in spring["variants"]:
                add("spring-modernization", {"archetype": archetype["id"], "feature": feature["id"], "variant": variant})
    language = yaml.safe_load((package_root / "matrices/cross-language.yaml").read_text(encoding="utf-8"))
    for pair in language["pairs"]:
        for feature in language["features"]:
            required = set(feature.get("requires_any", []))
            if required and pair["kind"] not in required:
                continue
            for variant in language["variants"]:
                add("cross-language", {"pair": pair["id"], "feature": feature["id"], "variant": variant})
    generation = yaml.safe_load((package_root / "matrices/project-generation.yaml").read_text(encoding="utf-8"))
    for stack in generation["stacks"]:
        for template in generation["templates"]:
            for deployment in generation["deployment_profiles"]:
                add("project-generation", {"stack": stack["id"], "template_or_change": template["id"], "deployment_or_mode": deployment})
        for change in generation["evolution_tasks"]:
            add("project-generation", {"stack": stack["id"], "template_or_change": _slug(change), "deployment_or_mode": "incremental-evolution"})
        for adversarial in generation["adversarial_requirements"]:
            add("project-generation", {"stack": stack["id"], "template_or_change": _slug(adversarial), "deployment_or_mode": "adversarial-requirement"})
    sql = yaml.safe_load((package_root / "matrices/sql-conversion.yaml").read_text(encoding="utf-8"))
    for pair in sql["pairs"]:
        for feature in sql["features"]:
            required = set(feature.get("requires_any", []))
            if required and pair["kind"] not in required:
                continue
            for variant in sql["variants"]:
                add("sql-conversion", {"pair": pair["id"], "feature": feature["id"], "variant": variant})
    cross = yaml.safe_load((package_root / "matrices/cross-cutting.yaml").read_text(encoding="utf-8"))
    for line in cross["business_lines"]:
        for scenario in cross["scenarios"]:
            for variant in cross["variants"]:
                add("cross-cutting", {"business_line": line, "scenario": scenario["id"], "fault_position": variant})
    return expected


def _slug(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def coverage_report(package_root: Path) -> dict[str, Any]:
    expected = _expected_cells(package_root)
    actual: dict[str, set[tuple[tuple[str, str], ...]]] = defaultdict(set)
    duplicate_ids: list[str] = []
    seen: set[str] = set()
    total = 0
    for case in load_cases(package_root):
        total += 1
        if case.get("id") in seen:
            duplicate_ids.append(str(case.get("id")))
        seen.add(str(case.get("id")))
        coverage = case.get("coverage", {})
        if case.get("id", "").startswith(("SM-SMOKE", "XLC-SMOKE", "PG-SMOKE", "SQL-SMOKE")):
            continue
        actual[str(case.get("business_line"))].add(tuple(sorted((str(key), str(value)) for key, value in coverage.get("dimensions", {}).items())))
    lines: dict[str, Any] = {}
    missing: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    for line in sorted(expected):
        missing_cells = expected[line] - actual.get(line, set())
        extra_cells = actual.get(line, set()) - expected[line]
        missing.extend({"business_line": line, "dimensions": dict(cell)} for cell in sorted(missing_cells))
        unexpected.extend({"business_line": line, "dimensions": dict(cell)} for cell in sorted(extra_cells))
        lines[line] = {
            "expected_cells": len(expected[line]),
            "covered_cells": len(expected[line] & actual.get(line, set())),
            "coverage": len(expected[line] & actual.get(line, set())) / len(expected[line]) if expected[line] else 1.0,
        }
    return {
        "complete": not duplicate_ids and not missing and not unexpected,
        "declared_model": "ETGB-COVERAGE-1.0",
        "case_count": total,
        "lines": lines,
        "missing_case_count": len(missing),
        "missing_case_examples": missing[:20],
        "unexpected_case_count": len(unexpected),
        "unexpected_case_examples": unexpected[:20],
        "duplicate_case_ids": duplicate_ids[:20],
    }


def validate_package(package_root: Path, *, release: bool = False, archive: Path | None = None, extracted: Path | None = None, trust_store: dict[str, Any] | None = None, license_reviews_path: Path | None = None, max_errors: int = 50) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    package_root = package_root.resolve(strict=True)
    try:
        suite = yaml.safe_load((package_root / "suites/suite.yaml").read_text(encoding="utf-8"))
        suite_schema = _load_json(package_root / "schemas/suite.schema.json")
        errors.extend(f"suite.yaml: {error.message}" for error in Draft202012Validator(suite_schema).iter_errors(suite))
        case_validator = Draft202012Validator(_load_json(package_root / "schemas/test-case.schema.json"))
        seen: set[str] = set()
        counts: Counter[str] = Counter()
        total = 0
        for case in load_cases(package_root):
            total += 1
            case_id = str(case.get("id"))
            if case_id in seen:
                errors.append(f"duplicate case id: {case_id}")
            seen.add(case_id)
            counts[str(case.get("business_line"))] += 1
            errors.extend(f"case {case_id}: {error.message}" for error in case_validator.iter_errors(case))
            errors.extend(f"case {case_id}: {error}" for error in validate_domain_case(case))
            if len(errors) >= max_errors:
                break
        minimum = int(suite.get("expected_minimum_case_count", 1))
        if total < minimum:
            errors.append(f"case count {total} is below minimum {minimum}")
        expected_manifest = package_root / "PACKAGE_MANIFEST.json"
        if expected_manifest.is_file():
            manifest = _load_json(expected_manifest)
            summary = manifest.get("case_summary", {})
            declared_total = summary.get("total_cases")
            if declared_total != total:
                errors.append(f"PACKAGE_MANIFEST total_cases {declared_total} != materialized {total}")
            for field, actual in (("by_business_line", counts),):
                declared = summary.get(field, {})
                if dict(declared) != dict(actual):
                    errors.append(f"PACKAGE_MANIFEST {field} does not match materialized cases")
            if manifest.get("skill_count") not in (24, 50):
                errors.append(f"PACKAGE_MANIFEST skill_count must be 24 or 50, got {manifest.get('skill_count')}")
        coverage = coverage_report(package_root)
        if not coverage["complete"]:
            errors.append("declared capability matrix is not complete")
        if (package_root / "matrices/feature-registry.yaml").is_file():
            from .features import feature_coverage_report
            feature_report = feature_coverage_report(package_root)
            if not feature_report["complete"]:
                errors.extend(f"feature coverage: {e}" for e in feature_report.get("errors", [])[:max_errors])
        skills = audit_skills(package_root)
        if not skills["valid"]:
            errors.extend(f"skills: {message}" for message in skills["errors"])
        assurance = package_root / "suites/assurance-techniques.yaml"
        if assurance.is_file():
            techniques = yaml.safe_load(assurance.read_text(encoding="utf-8"))
            required = {"example-based", "property-based", "differential", "metamorphic", "fuzz", "mutation", "fault-injection", "temporal-hidden"}
            declared = {str(item.get("id")) for item in techniques.get("techniques", [])} if isinstance(techniques, dict) else set()
            if not required.issubset(declared):
                errors.append("assurance-techniques.yaml is missing required techniques")
        required_integrations = (
            "integrations/harness/adapter-contract.yaml",
            "integrations/postgres/001_etgb_schema.sql",
            "integrations/postgres/002_etgb_rls.sql",
            "integrations/openapi/etgb-control-plane.openapi.yaml",
            "integrations/events/etgb-events.asyncapi.yaml",
            "integrations/otel/semantic-conventions.yaml",
            "integrations/temporal/WORKFLOW_PSEUDOCODE.md",
        )
        for relative in required_integrations:
            path = package_root / relative
            if not path.is_file():
                errors.append(f"missing integration contract: {relative}")
        corpus = verify_lock(package_root, release=release, trust_store=trust_store, license_reviews_path=license_reviews_path)
        errors.extend(f"corpus: {message}" for message in corpus["errors"])
        warnings.extend(f"corpus: {message}" for message in corpus["warnings"])
        source_package = verify_source_package(archive, extracted=extracted) if archive else None
        if source_package and not source_package["valid"]:
            errors.extend(f"source package: {message}" for message in source_package["errors"])
            warnings.extend(f"source package: {message}" for message in source_package["warnings"])
        return {"valid": not errors, "release_mode": release, "case_count": total, "case_files": dict(counts), "coverage": coverage, "skills": skills, "corpus": corpus, "source_package": source_package, "errors": errors[:max_errors], "warnings": warnings}
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        return {"valid": False, "release_mode": release, "case_count": 0, "case_files": {}, "errors": [str(exc)], "warnings": warnings}


def validate_results(results: list[dict[str, Any]], package_root: Path) -> list[str]:
    validator = Draft202012Validator(_load_json(package_root / "schemas/run-result.schema.json"))
    errors: list[str] = []
    for index, result in enumerate(results, 1):
        errors.extend(f"result {index}: {error.message}" for error in validator.iter_errors(result))
    return errors
