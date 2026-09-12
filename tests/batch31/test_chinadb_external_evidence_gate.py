from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION = ROOT / "scripts/batch31/run_chinadb_qualification.py"
EXTERNAL_GATE = ROOT / "scripts/operations/run_database_external_gate.py"
WORKFLOW = ROOT / ".github/workflows/chinadb-production-qualification.yml"
MAKEFILE = ROOT / "Makefile.batch31"


def test_qualification_cli_cannot_manufacture_evidence() -> None:
    source = QUALIFICATION.read_text(encoding="utf-8")
    forbidden = (
        "Ed25519PrivateKey",
        "signed_envelope",
        "private_key",
        "1.0.0-dm8",
        'maximumObservedTargetP95Milliseconds": 25.0',
    )
    assert all(token not in source for token in forbidden)


def test_checked_in_qualification_input_is_rejected_as_external() -> None:
    draft = (
        ROOT
        / "engines/database-data-engine/sql-transpiler/examples"
        / "chinadb-production-qualification-draft.json"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(QUALIFICATION),
            "--request",
            str(draft),
            "--trust-store",
            str(draft),
            "--require-target",
            "dm8",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "external evidence mount" in completed.stderr


def test_external_gate_requires_explicit_chinadb_inputs() -> None:
    completed = subprocess.run(
        [sys.executable, str(EXTERNAL_GATE), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "--chinadb-request" in completed.stderr
    assert "--chinadb-trust-store" in completed.stderr


def test_external_gate_requires_pinned_runner_attestation() -> None:
    source = EXTERNAL_GATE.read_text(encoding="utf-8")
    assert '--expected-runner-attestation-digest", required=True' in source
    assert "RUNNER_ATTESTATION_MISMATCH" in source
    assert '"postgresql-to-opengauss"' in source


def test_no_repository_generated_chinadb_certification_artifacts() -> None:
    forbidden = (
        ROOT / "docs/batch31/evidence/chinadb-production-qualification-certified.json",
        ROOT / "docs/batch31/evidence/chinadb-trust-store-certified.json",
        ROOT / "docs/batch31/evidence/chinadb-industrial-evaluation-receipt.json",
        ROOT / "evidence/batch31/chinadb-industrial-evaluation-receipt.json",
        ROOT / "certification/reports/database-m31-certification-report.json",
        ROOT
        / "certification/reports/business-line-3-database-chinadb-l5-certification.json",
        ROOT / "scripts/batch31/run_business_line_3_l5_gate.py",
        ROOT / "scripts/batch31/run_chinadb_industrial_evaluation.py",
    )
    assert not any(path.exists() for path in forbidden)
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert "run_chinadb_industrial_evaluation.py" not in makefile
    assert "b31-external-qualification" in makefile


def test_launch_scope_stays_fail_closed() -> None:
    launch = json.loads(
        (ROOT / "docs/batch31/sql-line-launch-scope.json").read_text(encoding="utf-8")
    )
    assert launch["release_channel"] == "PREFLIGHT_BETA"
    assert [route["status"] for route in launch["routes"]] == [
        "experimental",
        "research",
        "experimental",
    ]
    assert not any(route["release_eligible"] for route in launch["routes"])


def test_checked_in_database_packs_cannot_claim_external_certification() -> None:
    for pack in (ROOT / "database-packs").iterdir():
        evidence_path = pack / "certification/evidence.json"
        certification_path = pack / "certification/certification.json"
        if not evidence_path.is_file() or not certification_path.is_file():
            continue
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        certification = json.loads(certification_path.read_text(encoding="utf-8"))
        states = evidence["evidence_status"]

        assert states["external_certification"] == "NOT_RUN"
        assert states["independent_verification"] == "NOT_RUN"
        assert certification["external_certification"] == "NOT_RUN"
        assert certification.get("production_certification") != "CERTIFIED"
        assert certification["approved_by"] == []


def test_dedicated_runner_workflow_pins_external_evidence_and_attestation() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "elmos-sql-perf-dedicated" in workflow
    assert "request_sha256" in workflow
    assert "trust_store_sha256" in workflow
    assert "--expected-runner-attestation-digest" in workflow
    assert "--require-target dm8" in workflow
    assert "cancel-in-progress: false" in workflow


def test_authoritative_closure_plan_does_not_claim_external_completion() -> None:
    closure = json.loads(
        (ROOT / "docs/batch31/evidence/sql-route-closure-plan.json").read_text(
            encoding="utf-8"
        )
    )
    current = closure["current"]
    assert current["externalExecution"] == "NOT_RUN"
    assert current["independentVerification"] == "NOT_RUN"
    assert current["certification"] == "NOT_CERTIFIED"
    assert closure["executionSequence"][1]["state"] == "BLOCKED_EXTERNAL_INPUT"
    assert closure["executionSequence"][2]["state"] == "NOT_RUN_ENVIRONMENT_INVALID"
