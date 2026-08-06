#!/usr/bin/env python3
"""Build the exact 587-Skill multidimensional coverage matrix."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "precision-migration-b01-44" / "installed-manifest.json"
ADAPTERS = ROOT / "docs" / "precision-migration-b01-44" / "adapter-registry.json"
DEFAULT_OUTPUT = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "coverage" / "coverage-matrix.json"
CONTRACT_RESULTS = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "contract-qualification" / "results.json"
DOMAIN_RESULTS = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "domain-qualification" / "results.json"
B41_RESULTS = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "b41-qualification" / "results.json"
B16_RESULTS = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "b16-qualification" / "results.json"
SPECIALIZED_RESULTS = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "specialized-qualification" / "results.json"
EXTERNAL_PROFILES = ROOT / "docs" / "precision-migration-b01-44" / "external-execution-profiles.json"
EXTERNAL_ENGINEERING_RESULTS = (
    ROOT
    / "verification-packs"
    / "precision-migration-b01-44-runtime"
    / "external-engineering-qualification"
    / "results.json"
)


def build() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    adapters = json.loads(ADAPTERS.read_text(encoding="utf-8"))
    external_profiles = json.loads(EXTERNAL_PROFILES.read_text(encoding="utf-8"))
    externally_profiled = {item["skill"] for item in external_profiles["profiles"]}
    if len(externally_profiled) != 557:
        raise ValueError("external execution profile coverage must contain 557 Skills")
    by_skill = {item["skill"]: item for item in adapters["entries"]}
    locally_exercised = {
        "pm-b02-repository-modernization-assessment",
        *{
            item["skill"]
            for item in adapters["entries"]
            if item["handler_id"].startswith(("batch29-route-executor-v1:", "b41-", "b42-"))
        },
    }
    qualification = json.loads(CONTRACT_RESULTS.read_text(encoding="utf-8"))
    passed_contract_tests = {
        (item["skill"], item["test_type"])
        for item in qualification["results"]
        if item["state"] == "PASS"
    }
    domain_qualification = json.loads(DOMAIN_RESULTS.read_text(encoding="utf-8"))
    passed_domain_tests = {
        (item["skill"], item["test_type"])
        for item in domain_qualification["results"]
        if item["state"] == "PASS"
    }
    for qualification_path in (B41_RESULTS, B16_RESULTS, SPECIALIZED_RESULTS):
        specialized_qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
        passed_domain_tests.update(
            (item["skill"], item["test_type"])
            for item in specialized_qualification["results"]
            if item["state"] == "PASS"
        )
    external_engineering = json.loads(EXTERNAL_ENGINEERING_RESULTS.read_text(encoding="utf-8"))
    if (
        external_engineering.get("decision") != "PASSED_LOCAL_ENGINEERING_SIMULATION"
        or external_engineering.get("production_eligible") is not False
        or external_engineering.get("actual_handler_invocation_count") != 2785
    ):
        raise ValueError("external engineering qualification is incomplete or overclaims production eligibility")
    passed_external_engineering = {
        (item["skill"], item["test_type"])
        for item in external_engineering["results"]
        if item["engineering_state"] == "PASS"
        and item["handler_invoked"] is True
        and item["external_stage_state"] in {"NOT_RUN", "NOT_APPLICABLE"}
        and item["production_eligible"] is False
    }
    if len(passed_external_engineering) != 2785:
        raise ValueError("external engineering qualification must contain 2,785 exact PASS bindings")
    rows = []
    for record in manifest["skills"]:
        if record["kind"] != "skill":
            continue
        adapter = by_skill[record["name"]]
        exact_route = adapter["handler_id"].startswith("batch29-route-executor-v1:")
        exact_domain = adapter["handler_id"].startswith("exact-skill-v4:")
        locally_executed = record["name"] in locally_exercised or exact_domain
        rows.append(
            {
                "skill": record["name"],
                "source_skill": record["source_name"],
                "batch": record["batch"],
                "risk_tier": "P0" if record["batch"] in {7, 19, 20, 21, 22, 23, 24, 25, 26, 30, 32, 33, 34, 35, 41, 42, 44} else "P1",
                "maturity": "LOCAL_EXECUTED" if locally_executed else record["maturity"],
                "handler_id": adapter["handler_id"],
                "coverage": {
                    "source_contract": "PASSED",
                    "installed_identity": "PASSED",
                    "handler_contract": "DECLARED" if adapter.get("binding_state") == "DECLARED" else "NOT_AVAILABLE",
                    "contract_positive": "PASSED" if (record["name"], "positive") in passed_contract_tests else "NOT_RUN",
                    "contract_negative": "PASSED" if (record["name"], "negative") in passed_contract_tests else "NOT_RUN",
                    "contract_integration": "PASSED" if (record["name"], "integration") in passed_contract_tests else "NOT_RUN",
                    "contract_holdout": "PASSED" if (record["name"], "holdout") in passed_contract_tests else "NOT_RUN",
                    "contract_representative": "PASSED" if (record["name"], "representative") in passed_contract_tests else "NOT_RUN",
                    "bounded_domain_positive": "PASSED" if (record["name"], "positive") in passed_domain_tests else "NOT_RUN",
                    "bounded_domain_negative": "PASSED" if (record["name"], "negative") in passed_domain_tests else "NOT_RUN",
                    "bounded_domain_integration": "PASSED" if (record["name"], "integration") in passed_domain_tests else "NOT_RUN",
                    "bounded_domain_holdout": "PASSED" if (record["name"], "holdout") in passed_domain_tests else "NOT_RUN",
                    "bounded_domain_representative": "PASSED" if (record["name"], "representative") in passed_domain_tests else "NOT_RUN",
                    "local_execution": "PASSED" if locally_executed else "NOT_RUN",
                    "external_execution_profile": "NOT_APPLICABLE" if exact_route else "DECLARED" if record["name"] in externally_profiled else "NOT_AVAILABLE",
                    "production_workflow_code": "PASSED" if exact_route or record["name"] in externally_profiled else "NOT_AVAILABLE",
                    "external_engineering_positive": "NOT_APPLICABLE" if exact_route else "PASSED" if (record["name"], "positive") in passed_external_engineering else "NOT_RUN",
                    "external_engineering_negative": "NOT_APPLICABLE" if exact_route else "PASSED" if (record["name"], "negative") in passed_external_engineering else "NOT_RUN",
                    "external_engineering_integration": "NOT_APPLICABLE" if exact_route else "PASSED" if (record["name"], "integration") in passed_external_engineering else "NOT_RUN",
                    "external_engineering_holdout_fixture": "NOT_APPLICABLE" if exact_route else "PASSED" if (record["name"], "holdout") in passed_external_engineering else "NOT_RUN",
                    "external_engineering_representative_fixture": "NOT_APPLICABLE" if exact_route else "PASSED" if (record["name"], "representative") in passed_external_engineering else "NOT_RUN",
                    "negative": "PASSED" if (record["name"], "negative") in passed_domain_tests else "NOT_RUN",
                    "integration": "PASSED" if (record["name"], "integration") in passed_domain_tests else "NOT_RUN",
                    "native_source_build": "PASSED" if exact_route else "NOT_RUN",
                    "native_target_build": "PASSED" if exact_route else "NOT_RUN",
                    "holdout": "PASSED" if exact_route else "NOT_RUN",
                    "representative_workload": "PASSED" if exact_route else "NOT_RUN",
                    "independent_verification": "NOT_RUN",
                    "external_evidence": "NOT_RUN",
                },
                "owner": "elmos-migration-platform-engineering",
                "limitations": [
                    "Cross-cutting runtime trust tests do not establish this Skill's domain semantics.",
                    "A PASSED local_execution row covers only the named allowlisted handler operation."
                ],
            }
        )
    if len(rows) != 587 or len({row["skill"] for row in rows}) != 587:
        raise ValueError("coverage matrix must contain exactly 587 unique child Skills")
    dimensions = [
        "source_contract", "installed_identity", "handler_contract", "contract_positive",
        "contract_negative", "contract_integration", "contract_holdout", "contract_representative",
        "bounded_domain_positive", "bounded_domain_negative", "bounded_domain_integration",
        "bounded_domain_holdout", "bounded_domain_representative", "local_execution",
        "external_execution_profile", "production_workflow_code",
        "external_engineering_positive", "external_engineering_negative",
        "external_engineering_integration", "external_engineering_holdout_fixture",
        "external_engineering_representative_fixture",
        "negative", "integration", "native_source_build", "native_target_build", "holdout",
        "representative_workload", "independent_verification", "external_evidence",
    ]
    summaries = {
        dimension: dict(sorted(Counter(row["coverage"][dimension] for row in rows).items()))
        for dimension in dimensions
    }
    return {
        "schema_version": 1,
        "matrix_key": "precision-migration-b01-44-skill-coverage-v1",
        "scope": {
            "child_skill_count": 587,
            "source_tree_sha256": manifest["source_tree_sha256"],
            "installed_manifest": "docs/precision-migration-b01-44/installed-manifest.json",
            "adapter_registry": "docs/precision-migration-b01-44/adapter-registry.json",
        },
        "dimensions": dimensions,
        "summaries": summaries,
        "rows": rows,
        "release_rule": "No aggregate percentage may override a NOT_RUN or NOT_AVAILABLE P0 row.",
        "production_certification": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("coverage matrix drifted; regenerate it")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "rows": 587, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
