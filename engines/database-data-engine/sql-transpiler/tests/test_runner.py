from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

import elmos_sql_transpiler.runner as runner_module
from elmos_sql_transpiler.runner import (
    RunnerBlockedError,
    runner_capabilities,
    verify_route,
)


def _performance_attempt(state: str, p95: float) -> dict[str, object]:
    return {
        "state": state,
        "warmups": 5,
        "iterations": 40,
        "source": {
            "p50Milliseconds": 1.0,
            "p95Milliseconds": p95,
            "samplesMilliseconds": [p95],
        },
        "target": {
            "p50Milliseconds": 1.0,
            "p95Milliseconds": p95,
            "samplesMilliseconds": [p95],
        },
        "targetToSourceP95Ratio": 1.0,
    }


def test_shared_host_performance_confirmation_preserves_initial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRunner:
        profile_id = "sqlite-3.53.3"

        def analyze(self, _: object) -> None:
            pass

    target = FakeRunner()
    target.profile_id = "duckdb-1.5.4"
    attempts = iter(
        [
            _performance_attempt("FAILED", 90.0),
            _performance_attempt("PASSED", 20.0),
            *[_performance_attempt("PASSED", 20.0) for _ in range(5)],
        ]
    )
    monkeypatch.setattr(
        runner_module,
        "_measure_performance_attempt",
        lambda *_args: next(attempts),
    )

    evidence = runner_module._performance_evidence(FakeRunner(), target, object(), object())
    first = evidence["queries"][0]

    assert evidence["state"] == "PASSED"
    assert first["measurementAttempts"] == 2
    assert first["confirmationUsed"] is True
    assert [attempt["state"] for attempt in first["attempts"]] == ["FAILED", "PASSED"]
    assert first["sloP95Milliseconds"] == 75.0


def test_runner_capabilities_are_exact_and_fail_closed() -> None:
    capabilities = runner_capabilities()

    ready_profiles = {item["profileId"] for item in capabilities["ready"]}
    blocked_profiles = {item["profileId"] for item in capabilities["blocked"]}
    assert ready_profiles >= {
        "sqlite-3.53.3",
        "duckdb-1.5.4",
    }
    assert ready_profiles | blocked_profiles == {
        "postgresql-17.5",
        "sqlite-3.53.3",
        "duckdb-1.5.4",
        "postgresql-18.4",
        "mysql-8.4.10-lts",
        "sqlserver-2022-cu26",
        "oracle-26ai-ee",
    }
    assert blocked_profiles >= {
        "postgresql-18.4",
        "mysql-8.4.10-lts",
        "sqlserver-2022-cu26",
        "oracle-26ai-ee",
    }
    assert capabilities["readyDirectedRouteCount"] == len(ready_profiles) * (
        len(ready_profiles) - 1
    )
    assert all(item["runtimeEvidence"] == "NOT_RUN" for item in capabilities["blocked"])
    assert capabilities["certification"] == "NOT_CERTIFIED"


def test_runner_capabilities_do_not_advertise_postgresql_on_wrong_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(runner_module.platform, "machine", lambda: "x86_64")

    capabilities = runner_capabilities()
    ready_profiles = {item["profileId"] for item in capabilities["ready"]}
    postgresql = next(
        item
        for item in capabilities["blocked"]
        if item["profileId"] == "postgresql-17.5"
    )

    assert ready_profiles == {"sqlite-3.53.3", "duckdb-1.5.4"}
    assert capabilities["readyDirectedRouteCount"] == 2
    assert postgresql["state"] == "BLOCKED"
    assert postgresql["declaredState"] == "LOCAL_RUNNER_READY"
    assert "requires the declared darwin-arm64 host" in postgresql["reason"]
    assert postgresql["runtimeEvidence"] == "NOT_RUN"


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
        and "planStructuralComparison" in item
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


def test_postgresql_to_sqlite_executes_on_real_server_175(
    tmp_path: Path,
) -> None:
    """The declared darwin-arm64 host tuple: PostgreSQL 17.5 from the pinned
    Homebrew keg, provisioned through a fresh initdb cluster that is destroyed
    afterwards. On a host without the exact keg the route is NOT_RUN and the
    test skips rather than fabricating execution evidence.
    """
    capabilities = runner_capabilities()
    if "postgresql-17.5" not in {item["profileId"] for item in capabilities["ready"]}:
        pytest.skip(
            "pinned PostgreSQL 17.5 Homebrew keg is absent; "
            "postgresql-17.5 runtime evidence stays NOT_RUN on this host"
        )

    output = tmp_path / "postgresql-to-sqlite"
    result = verify_route("postgresql-17.5", "sqlite-3.53.3", output)

    assert result["localDecision"] == "READY_FOR_EXTERNAL_GATE"
    assert result["sourceExecution"] == "PASSED"
    assert result["targetExecution"] == "PASSED"
    assert result["resultEquivalence"] == "PASSED"
    assert result["independentVerification"] == "NOT_RUN"
    assert result["certification"] == "NOT_CERTIFIED"

    environment = json.loads((output / "environment.json").read_text())
    source_runner = environment["sourceRunner"]
    assert source_runner["engineVersionObserved"] == "17.5"
    assert source_runner["engineVersionObservedRaw"] == "17.5 (Homebrew)"
    assert source_runner["profile"]["id"] == "postgresql-17.5"
    assert source_runner["network"] == "LOOPBACK_EPHEMERAL_PORT"

    manifest = json.loads((output / "runner-evidence.json").read_text())
    assert manifest["contentAddressed"] is True
    for item in manifest["evidence"]:
        content = (output / item["path"]).read_bytes()
        assert item["bytes"] == len(content)
        assert item["digest"] == f"sha256:{sha256(content).hexdigest()}"
    assert not list(output.rglob("*.sqlite3"))
    assert list(output.parent.rglob("*.sqlite3")) == []


def test_unavailable_exact_runtime_remains_not_run(tmp_path: Path) -> None:
    with pytest.raises(RunnerBlockedError, match="runtime evidence remains NOT_RUN"):
        verify_route(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            tmp_path / "blocked",
        )
    assert not (tmp_path / "blocked").exists()
