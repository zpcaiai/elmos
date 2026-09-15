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


def test_cli_fingerprint() -> None:
    code, data = run_cli("fingerprint")
    assert code == 0
    assert "os_system" in data
    assert "arch" in data
    assert "python_version" in data
    assert "active_isolation_level" in data


def test_cli_verify_smt_proved() -> None:
    # SMT formula for theorem: x + 0 == x (negation is (not (= (+ x 0) x)))
    formula = """
(declare-const x Int)
(assert (not (= (+ x 0) x)))
(check-sat)
"""
    code, data = run_cli("verify-smt", "--formula", formula)
    assert code == 0
    assert data["verdict"] == "PROVED"
    assert data["solver"] == "z3"


def test_cli_verify_smt_refuted() -> None:
    # Formula where property does not hold: x > 0 (negation is (not (> x 0)) -> sat if x <= 0)
    formula = """
(declare-const x Int)
(assert (not (> x 0)))
(check-sat)
(get-model)
"""
    code, data = run_cli("verify-smt", "--formula", formula)
    assert code == 1  # exit code 1 for REFUTED
    assert data["verdict"] == "REFUTED"
    assert "counterexample" in data
    assert "x" in data["counterexample"]
    assert data["has_generated_test"] is True
    assert "generated_test_code" in data


def test_cli_sandbox_run() -> None:
    code, data = run_cli("sandbox-run", "python3", "-c", "print('hello from sandbox')")
    assert code == 0
    assert data["exit_code"] == 0
    assert "hello from sandbox" in data["stdout"]
    assert data["timed_out"] is False


def test_cli_egress_check_allowed_and_blocked() -> None:
    # Allowed
    code_ok, data_ok = run_cli("egress-check", "--target", "https://api.openai.com", "--allow-domain", "openai.com")
    assert code_ok == 0
    assert data_ok["status"] == "ALLOWED"

    # Blocked by metadata / localhost
    code_ssrf, data_ssrf = run_cli("egress-check", "--target", "http://169.254.169.254/meta-data")
    assert code_ssrf == 2
    assert data_ssrf["status"] == "BLOCKED"

    # Blocked by internal domain suffix
    code_internal, data_internal = run_cli("egress-check", "--target", "http://auth.service.internal")
    assert code_internal == 2
    assert data_internal["status"] == "BLOCKED"

    # Rejected by payload secret
    dummy_gh = f"{'gh'}{'p_'}{'1' * 36}"
    code_secret, data_secret = run_cli(
        "egress-check",
        "--target",
        "https://api.openai.com",
        "--allow-domain",
        "openai.com",
        "--payload",
        f"Here is the token: {dummy_gh}",
    )
    assert code_secret == 2
    assert data_secret["status"] == "REJECTED"
    assert "GitHub Token" in data_secret["reason"]

