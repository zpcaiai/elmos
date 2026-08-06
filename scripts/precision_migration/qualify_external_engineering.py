#!/usr/bin/env python3
"""Execute all 2,785 local-engineering cases for 557 external profiles.

This runner invokes every bounded handler for positive, negative, integration,
holdout, and representative fixtures.  It also runs the disposable-key release
workflow tests.  Its evidence is engineering-only and can never mutate or
replace the checked-in external-readiness state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.precision_migration.external import scaffold
from scripts.precision_migration.qualify_b41 import build as build_b41
from scripts.precision_migration.qualify_domains import build as build_domains
from scripts.precision_migration.qualify_specialized import build as build_specialized
from scripts.precision_migration.runtime import canonical_digest


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "verification-packs" / "precision-migration-b01-44-runtime"
CASES = PACK / "external-engineering-qualification" / "cases.json"
OUTPUT = PACK / "external-engineering-qualification" / "results.json"
EXTERNAL_STATE = PACK / "external-readiness" / "current.json"
EXTERNAL_TESTS = ROOT / "tests" / "precision-migration" / "test_precision_migration_external.py"

RELEASE_TESTS = (
    "profile-registry-exactness",
    "external-state-isolation",
    "corpus-overlap-rejection",
    "external-verified-boundary",
    "disposable-ed25519-hsm-and-certificate-chain",
    "signed-digest-pinned-adapter-execution",
    "command-injection-rejection",
    "authorized-canary-and-registered-rollback",
)


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validate_case_digest(case: dict[str, Any]) -> None:
    body = {key: value for key, value in case.items() if key != "case_digest"}
    if case.get("case_digest") != canonical_digest(body):
        raise ValueError(f"engineering case digest mismatch: {case.get('case_id')}")


def run_release_drill() -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/precision-migration",
            "-p",
            "test_precision_migration_external.py",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    combined = completed.stdout + completed.stderr
    match = re.search(r"Ran (\d+) tests?", combined)
    observed = int(match.group(1)) if match else 0
    if completed.returncode != 0 or observed != len(RELEASE_TESTS) or "OK" not in combined:
        raise ValueError(f"external release engineering drill failed:\n{combined[-4000:]}")
    return {
        "state": "PASS",
        "test_count": observed,
        "scenarios": list(RELEASE_TESTS),
        "scope": "DISPOSABLE_TEST_TRUST_AND_LOCAL_LEDGER",
        "test_module_digest": file_digest(EXTERNAL_TESTS),
        "engineering_hsm_signature_verification": "PASSED_WITH_EPHEMERAL_ED25519_KEY",
        "engineering_canary_and_rollback": "PASSED_WITH_LOCAL_SIGNED_ADAPTERS",
        "engineering_external_certificate": "PASSED_WITH_EPHEMERAL_EXTERNAL_CERTIFIER",
        "production_hsm": "NOT_RUN",
        "authorized_production_canary": "NOT_RUN",
        "external_certification": "NOT_RUN",
        "production_eligible": False,
    }


def build() -> dict[str, Any]:
    case_suite = json.loads(CASES.read_text(encoding="utf-8"))
    suite_body = {key: value for key, value in case_suite.items() if key != "suite_digest"}
    if case_suite.get("suite_digest") != canonical_digest(suite_body):
        raise ValueError("external engineering suite digest mismatch")
    if case_suite.get("case_count") != 2785 or case_suite.get("skill_count") != 557:
        raise ValueError("external engineering case inventory mismatch")

    # Each build call below performs fresh handler invocation against disposable
    # fixtures; no checked-in PASS row is trusted as execution evidence.
    fresh_suites = {
        "exact-domain": build_domains(),
        "b41-evidence": build_b41(),
        "specialized-runtime": build_specialized(),
    }
    expected_suite_counts = {
        "exact-domain": (536, 2680),
        "b41-evidence": (10, 50),
        "specialized-runtime": (11, 55),
    }
    result_index: dict[tuple[str, str], dict[str, Any]] = {}
    result_owners: dict[tuple[str, str], str] = {}
    qualification_bindings: dict[str, Any] = {}
    for suite_name, payload in fresh_suites.items():
        expected_skills, expected_results = expected_suite_counts[suite_name]
        if payload.get("skill_count") != expected_skills or payload.get("result_count") != expected_results:
            raise ValueError(f"fresh qualification inventory mismatch: {suite_name}")
        if payload.get("all_tests_passed") is not True:
            raise ValueError(f"fresh qualification did not pass: {suite_name}")
        for result in payload["results"]:
            key = (result["skill"], result["test_type"])
            if key in result_index:
                raise ValueError(f"duplicate fresh qualification result: {key}")
            result_index[key] = result
            result_owners[key] = suite_name
        qualification_bindings[suite_name] = {
            "skill_count": expected_skills,
            "result_count": expected_results,
            "fresh_payload_digest": canonical_digest(payload),
            "execution_scope": payload["execution_scope"],
        }

    if len(result_index) != 2785:
        raise ValueError("fresh handler qualification must contain exactly 2,785 results")

    results: list[dict[str, Any]] = []
    for case in case_suite["cases"]:
        validate_case_digest(case)
        key = (case["skill"], case["test_type"])
        source = result_index.get(key)
        if source is None or source.get("state") != "PASS":
            raise ValueError(f"engineering case has no fresh PASS execution: {case['case_id']}")
        if result_owners.get(key) != case["qualification_suite"]:
            raise ValueError(f"engineering case qualification owner mismatch: {case['case_id']}")
        body = {
            "case_id": case["case_id"],
            "case_digest": case["case_digest"],
            "skill": case["skill"],
            "test_type": case["test_type"],
            "engineering_stage": case["engineering_stage"],
            "engineering_state": "PASS",
            "handler_invoked": True,
            "fresh_qualification_result_digest": source["result_digest"],
            "fixture_binding_digest": case["fixture_binding_digest"],
            "evidence_class": "LOCAL_ENGINEERING_SIMULATION",
            "external_stage": case["external_stage"],
            "external_stage_state": "NOT_RUN" if case["external_stage"] else "NOT_APPLICABLE",
            "production_eligible": False,
        }
        results.append({**body, "result_digest": canonical_digest(body)})

    case_ids = {item["case_id"] for item in results}
    skills = {item["skill"] for item in results}
    if len(results) != 2785 or len(case_ids) != 2785 or len(skills) != 557:
        raise ValueError("engineering execution result inventory mismatch")

    current = json.loads(EXTERNAL_STATE.read_text(encoding="utf-8"))
    expected_external_state = scaffold()
    if current != expected_external_state:
        raise ValueError("checked-in external readiness state must remain the exact NOT_RUN scaffold")
    release_drill = run_release_drill()
    test_type_summary = dict(sorted(Counter(item["test_type"] for item in results).items()))
    stage_summary = dict(sorted(Counter(item["engineering_stage"] for item in results).items()))
    return {
        "schema_version": 1,
        "suite": "precision-migration-external-engineering-v1",
        "decision": "PASSED_LOCAL_ENGINEERING_SIMULATION",
        "evidence_class": "LOCAL_ENGINEERING_SIMULATION",
        "production_eligible": False,
        "skill_count": 557,
        "case_count": 2785,
        "result_count": 2785,
        "actual_handler_invocation_count": 2785,
        "all_engineering_tests_passed": True,
        "test_type_summary": test_type_summary,
        "engineering_stage_summary": stage_summary,
        "qualification_bindings": qualification_bindings,
        "case_suite_digest": case_suite["suite_digest"],
        "release_engineering_drill": release_drill,
        "real_external_state": {
            "decision": "NOT_READY",
            "verified_skill_count": 0,
            "production_operation_authorized": False,
            "production_certification": "NOT_CERTIFIED",
            "stage_states": expected_external_state["stage_states"],
            "binding_digest": file_digest(EXTERNAL_STATE),
        },
        "limitations": [
            "Local fixtures are not real native source or target toolchain evidence unless separately recorded by the exact route runner.",
            "The local holdout partition is independent from development fixtures but is not independently executed or verified by an external party.",
            "Representative fixtures are not customer workloads and carry no customer data authorization.",
            "Ephemeral Ed25519 keys and the local ledger do not constitute production HSM, production change approval, Canary, rollback, or certification evidence.",
        ],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    payload = build()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("external engineering qualification drifted; regenerate it")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "skills": payload["skill_count"],
                "cases": payload["case_count"],
                "actual_handler_invocations": payload["actual_handler_invocation_count"],
                "decision": payload["decision"],
                "production_certification": payload["real_external_state"]["production_certification"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
