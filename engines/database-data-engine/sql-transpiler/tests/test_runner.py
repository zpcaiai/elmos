from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from elmos_sql_transpiler.runner import (
    RunnerBlockedError,
    runner_capabilities,
    verify_route,
)


def test_runner_capabilities_are_exact_and_fail_closed() -> None:
    capabilities = runner_capabilities()

    assert capabilities["readyDirectedRouteCount"] == 6
    assert {item["profileId"] for item in capabilities["ready"]} == {
        "postgresql-17.5",
        "sqlite-3.53.3",
        "duckdb-1.5.4",
    }
    assert {item["profileId"] for item in capabilities["blocked"]} == {
        "postgresql-18.4",
        "mysql-8.4.10-lts",
        "sqlserver-2022-cu26",
        "oracle-26ai-ee",
    }
    assert all(item["runtimeEvidence"] == "NOT_RUN" for item in capabilities["blocked"])
    assert capabilities["certification"] == "NOT_CERTIFIED"


def test_sqlite_to_duckdb_executes_equivalence_and_writes_digest_bound_evidence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "sqlite-to-duckdb"
    result = verify_route("sqlite-3.53.3", "duckdb-1.5.4", output)

    assert result["localDecision"] == "READY_FOR_EXTERNAL_GATE"
    assert result["sourceExecution"] == "PASSED"
    assert result["targetExecution"] == "PASSED"
    assert result["resultEquivalence"] == "PASSED"
    assert result["independentVerification"] == "NOT_RUN"
    assert result["certification"] == "NOT_CERTIFIED"

    query_evidence = json.loads((output / "query-results.json").read_text())
    assert len(query_evidence["queries"]) == 6
    assert all(item["state"] == "PASSED" for item in query_evidence["queries"])
    assert all(
        item["checks"]["rowValues"] == "PASSED"
        and item["checks"]["logicalTypes"] == "PASSED"
        and item["checks"]["ordering"] == "PASSED"
        for item in query_evidence["queries"]
    )

    transaction_evidence = json.loads((output / "transaction-locking.json").read_text())
    assert transaction_evidence["state"] == "PASSED"
    assert transaction_evidence["engines"]["source"]["locking"]["state"] == "PASSED"
    assert transaction_evidence["engines"]["target"]["locking"]["state"] == "PASSED"

    manifest = json.loads((output / "runner-evidence.json").read_text())
    assert manifest["contentAddressed"] is True
    assert manifest["evidenceCount"] == 10
    for item in manifest["evidence"]:
        content = (output / item["path"]).read_bytes()
        assert item["bytes"] == len(content)
        assert item["digest"] == f"sha256:{sha256(content).hexdigest()}"
    assert not list(output.rglob("*.sqlite3"))
    assert not list(output.rglob("*.duckdb"))

    with pytest.raises(FileExistsError, match="must not already exist"):
        verify_route("sqlite-3.53.3", "duckdb-1.5.4", output)


def test_unavailable_exact_runtime_remains_not_run(tmp_path: Path) -> None:
    with pytest.raises(RunnerBlockedError, match="runtime evidence remains NOT_RUN"):
        verify_route(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            tmp_path / "blocked",
        )
    assert not (tmp_path / "blocked").exists()
