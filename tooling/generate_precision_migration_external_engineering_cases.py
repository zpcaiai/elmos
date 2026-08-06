#!/usr/bin/env python3
"""Generate exact local-engineering cases for all 557 external profiles.

The generated cases exercise the production workflow code with bounded local
fixtures.  They deliberately do not claim native toolchain, independent-party,
customer, production HSM, canary, rollback, or certification execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "docs" / "precision-migration-b01-44" / "external-execution-profiles.json"
OUTPUT = (
    ROOT
    / "verification-packs"
    / "precision-migration-b01-44-runtime"
    / "external-engineering-qualification"
    / "cases.json"
)

CASE_SPECS = (
    {
        "engineering_stage": "source_fixture_execution",
        "external_stage": "native_source_execution",
        "test_type": "positive",
        "fixture_role": "development",
        "partition": "development-source",
    },
    {
        "engineering_stage": "target_integration_fixture_execution",
        "external_stage": "native_target_execution",
        "test_type": "integration",
        "fixture_role": "integration",
        "partition": "development-target-integration",
    },
    {
        "engineering_stage": "negative_fail_closed_execution",
        "external_stage": None,
        "test_type": "negative",
        "fixture_role": "negative",
        "partition": "adversarial-negative",
    },
    {
        "engineering_stage": "holdout_fixture_execution",
        "external_stage": "independent_holdout",
        "test_type": "holdout",
        "fixture_role": "holdout",
        "partition": "local-holdout",
    },
    {
        "engineering_stage": "representative_fixture_execution",
        "external_stage": "representative_customer_workload",
        "test_type": "representative",
        "fixture_role": "representative",
        "partition": "engineering-representative",
    },
)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def qualification_suite(handler_id: str) -> str:
    if handler_id.startswith("exact-skill-v4:"):
        return "exact-domain"
    if handler_id.startswith("b41-"):
        return "b41-evidence"
    if handler_id == "repository-assessment-v1" or handler_id.startswith("b42-"):
        return "specialized-runtime"
    raise ValueError(f"external profile has no engineering qualification suite: {handler_id}")


def build() -> dict[str, Any]:
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    counter = 0
    for profile in profiles["profiles"]:
        suite = qualification_suite(str(profile["handler_id"]))
        for spec in CASE_SPECS:
            counter += 1
            fixture_binding = {
                "skill": profile["skill"],
                "profile_digest": profile["profile_digest"],
                "partition": spec["partition"],
                "fixture_role": spec["fixture_role"],
            }
            body = {
                "case_id": f"PM-EXT-ENG-{counter:04d}",
                "skill": profile["skill"],
                "batch": profile["batch"],
                "risk_tier": profile["risk_tier"],
                "profile_digest": profile["profile_digest"],
                "handler_id": profile["handler_id"],
                "execution_kind": profile["execution_kind"],
                "qualification_suite": suite,
                "test_type": spec["test_type"],
                "engineering_stage": spec["engineering_stage"],
                "external_stage": spec["external_stage"],
                "fixture_role": spec["fixture_role"],
                "partition": spec["partition"],
                "fixture_binding_digest": canonical_digest(fixture_binding),
                "expected_result": "PASS",
                "evidence_class": "LOCAL_ENGINEERING_SIMULATION",
                "production_eligible": False,
            }
            cases.append({**body, "case_digest": canonical_digest(body)})

    if len(cases) != 2785 or len({item["case_id"] for item in cases}) != 2785:
        raise ValueError("external engineering suite must contain exactly 2,785 unique cases")
    skills = {item["skill"] for item in cases}
    if len(skills) != 557:
        raise ValueError("external engineering suite must cover exactly 557 Skills")
    for skill in skills:
        skill_cases = [item for item in cases if item["skill"] == skill]
        if {item["test_type"] for item in skill_cases} != {item["test_type"] for item in CASE_SPECS}:
            raise ValueError(f"external engineering case categories are incomplete: {skill}")

    result_without_digest = {
        "schema_version": 1,
        "namespace": "precision-migration-b01-44",
        "suite_key": "precision-migration-external-engineering-v1",
        "profile_registry_digest": profiles["registry_digest"],
        "skill_count": 557,
        "case_count": 2785,
        "per_skill_case_count": 5,
        "evidence_class": "LOCAL_ENGINEERING_SIMULATION",
        "production_eligible": False,
        "external_stage_effect": "NONE",
        "case_categories": [item["test_type"] for item in CASE_SPECS],
        "cases": cases,
    }
    return {**result_without_digest, "suite_digest": canonical_digest(result_without_digest)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("external engineering cases drifted; regenerate them")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "skills": 557, "cases": 2785}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
