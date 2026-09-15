"""Tests for CLI v3.2 unified skill registry, gate evaluation, and db commands."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch


from elmos_proof_harness.cli import main


def run_cli(*args: str) -> tuple[int, dict[str, object]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(args))
    raw = buf.getvalue().strip()
    data = json.loads(raw) if raw else {}
    return code, data


def test_cli_list_skills_versions() -> None:
    code, out_all = run_cli("list-skills", "--version", "all")
    assert code == 0
    assert out_all["version"] == "all"
    skills_all = out_all["skills"]
    assert isinstance(skills_all, list)
    assert len(skills_all) >= 49

    code, out_v30 = run_cli("list-skills", "--version", "v3.0")
    assert code == 0
    assert out_v30["count"] == 16

    code, out_v31 = run_cli("list-skills", "--version", "v3.1")
    assert code == 0
    assert out_v31["count"] == 13

    code, out_v32 = run_cli("list-skills", "--version", "v3.2")
    assert code == 0
    assert out_v32["count"] == 20


def test_cli_invoke_v32_skill() -> None:
    payload = json.dumps({
        "audit_run_id": "audit-cli-001",
        "authoritative_evidence": {
            "test_evidence": {"exit_code": 0},
            "build_evidence": {"exit_code": 0},
        },
        "sabotage_blind_test_passed": True,
        "external_verifier_attestations": ["ext-verifier-1"],
    })
    code, data = run_cli("invoke", "release-evidence-exact-artifact", "--payload", payload)
    assert code == 0
    assert data["status"] == "SUCCESS"
    assert data["skill"] == "release-evidence-exact-artifact"
    assert data["gate_decision"] == "PASS"


def test_cli_invoke_v31_non_routable() -> None:
    code, data = run_cli("invoke", "elmos-environment-attachment-authority", "--payload", "{}")
    assert code == 0
    assert data["status"] == "NON_ROUTABLE_INTERNAL"


def test_cli_gate_evaluate() -> None:
    payload = json.dumps({
        "audit_run_id": "gate-cli-test",
        "authoritative_evidence": {
            "test_evidence": {"exit_code": 0},
            "build_evidence": {"exit_code": 0},
        },
        "sabotage_blind_test_passed": True,
        "external_verifier_attestations": ["attest-01"],
    })
    code, data = run_cli("gate", "evaluate", "--payload", payload)
    assert code == 0
    assert data["gate_decision"] == "PASS"


def test_cli_db_missing_dsn() -> None:
    code, data = run_cli("db", "check")
    assert code == 1
    assert data["status"] == "ERROR"


def test_cli_db_check_mocked() -> None:
    with patch("elmos_proof_harness.cli.PostgresStore") as mock_pg:
        mock_instance = MagicMock()
        mock_readiness = MagicMock()
        mock_readiness.ready = True
        mock_readiness.status.value = "READY"
        mock_readiness.reason = "Online"
        mock_readiness.backend = "PostgreSQL"
        mock_readiness.schema_version = "3.2.0"
        mock_readiness.server_version = "17.0"
        mock_instance.readiness.return_value = mock_readiness
        mock_pg.return_value = mock_instance

        code, data = run_cli("db", "check", "--dsn", "postgresql://test:test@localhost:5432/test")
        assert code == 0
        assert data["status"] == "SUCCESS"
        assert data["readiness"]["ready"] is True
