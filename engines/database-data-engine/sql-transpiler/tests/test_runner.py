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


def test_qualified_performance_confirmation_preserves_initial_failure(
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

    evidence = runner_module._performance_evidence(
        FakeRunner(),
        target,
        object(),
        object(),
        environment={"state": "QUALIFIED"},
    )
    first = evidence["queries"][0]

    assert evidence["state"] == "PASSED"
    assert first["measurementAttempts"] == 2
    assert first["confirmationUsed"] is True
    assert [attempt["state"] for attempt in first["attempts"]] == ["FAILED", "PASSED"]
    assert first["sloP95Milliseconds"] == 75.0


def test_performance_environment_requires_opt_in_and_dedicated_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ELMOS_PERFORMANCE_QUALIFICATION", raising=False)
    monkeypatch.delenv("ELMOS_PERFORMANCE_RUNNER_CLASS", raising=False)
    monkeypatch.delenv("ELMOS_PERFORMANCE_RUNNER_ID", raising=False)
    monkeypatch.delenv("ELMOS_PERFORMANCE_RUNNER_ATTESTATION_DIGEST", raising=False)
    monkeypatch.setattr(runner_module.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(runner_module.os, "getloadavg", lambda: (16.0, 8.0, 4.0))

    blocked = runner_module._performance_environment_evidence()
    assert blocked["state"] == "INVALID"
    assert blocked["reasons"] == [
        "EXPLICIT_PERFORMANCE_QUALIFICATION_NOT_ENABLED",
        "DEDICATED_PERFORMANCE_RUNNER_REQUIRED",
        "DEDICATED_RUNNER_ID_REQUIRED",
        "DEDICATED_RUNNER_ATTESTATION_DIGEST_REQUIRED",
        "HOST_LOAD_EXCEEDS_QUALIFICATION_THRESHOLD",
    ]

    monkeypatch.setenv("ELMOS_PERFORMANCE_QUALIFICATION", "1")
    monkeypatch.setenv("ELMOS_PERFORMANCE_RUNNER_CLASS", "DEDICATED")
    monkeypatch.setenv("ELMOS_PERFORMANCE_RUNNER_ID", "sql-perf-runner-01")
    monkeypatch.setenv(
        "ELMOS_PERFORMANCE_RUNNER_ATTESTATION_DIGEST",
        "sha256:" + "a" * 64,
    )
    monkeypatch.setattr(runner_module.os, "getloadavg", lambda: (4.0, 4.0, 4.0))

    qualified = runner_module._performance_environment_evidence()
    assert qualified["state"] == "QUALIFIED"
    assert qualified["normalizedOneMinuteLoad"] == 0.5
    assert qualified["runnerClass"] == "DEDICATED"
    assert qualified["runnerId"] == "sql-perf-runner-01"


def test_performance_environment_rejects_invalid_runner_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELMOS_PERFORMANCE_QUALIFICATION", "1")
    monkeypatch.setenv("ELMOS_PERFORMANCE_RUNNER_CLASS", "DEDICATED")
    monkeypatch.setenv("ELMOS_PERFORMANCE_RUNNER_ID", "not allowed")
    monkeypatch.setenv("ELMOS_PERFORMANCE_RUNNER_ATTESTATION_DIGEST", "sha256:bad")
    monkeypatch.setattr(runner_module.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(runner_module.os, "getloadavg", lambda: (1.0, 1.0, 1.0))

    blocked = runner_module._performance_environment_evidence()
    assert blocked["state"] == "INVALID"
    assert blocked["reasons"] == [
        "DEDICATED_RUNNER_ID_REQUIRED",
        "DEDICATED_RUNNER_ATTESTATION_DIGEST_REQUIRED",
    ]


def test_runner_capabilities_are_exact_and_fail_closed() -> None:
    capabilities = runner_capabilities()

    ready = {item["profileId"] for item in capabilities["ready"]}
    blocked = {item["profileId"] for item in capabilities["blocked"]}
    assert {"sqlite-3.53.3", "duckdb-1.5.4"} <= ready
    assert {
        "postgresql-18.4",
        "mysql-8.4.10-lts",
        "sqlserver-2022-cu26",
        "oracle-26ai-ee",
    } <= blocked
    assert ("postgresql-17.5" in ready) != ("postgresql-17.5" in blocked)
    ready_local = ready & {"postgresql-17.5", "sqlite-3.53.3", "duckdb-1.5.4"}
    expected_routes = {
        f"{source}--to--{target}"
        for source in ready_local
        for target in ready_local
        if source != target
    }
    assert set(capabilities["readyDirectedRoutes"]) == expected_routes
    assert capabilities["readyDirectedRouteCount"] == len(expected_routes)
    assert all(item["runtimeEvidence"] == "NOT_RUN" for item in capabilities["blocked"])
    assert capabilities["certification"] == "NOT_CERTIFIED"


def test_runner_capabilities_downgrade_missing_postgresql_without_claiming_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POSTGRESQL_17_BIN", raising=False)
    monkeypatch.setattr(runner_module, "_POSTGRES_CANDIDATE_DIRS", ())
    monkeypatch.setattr(runner_module.shutil, "which", lambda _name: None)

    capabilities = runner_capabilities()
    ready = {item["profileId"] for item in capabilities["ready"]}
    blocked = {item["profileId"]: item for item in capabilities["blocked"]}

    assert "postgresql-17.5" not in ready
    assert blocked["postgresql-17.5"]["state"] == "BLOCKED"
    assert "required PostgreSQL executable is unavailable" in blocked["postgresql-17.5"]["reason"]
    assert capabilities["runtimeEvidence"] == "NOT_RUN"
    assert capabilities["certification"] == "NOT_CERTIFIED"


def test_sqlite_to_duckdb_executes_equivalence_and_writes_digest_bound_evidence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "sqlite-to-duckdb"
    result = verify_route("sqlite-3.53.3", "duckdb-1.5.4", output)

    assert result["localDecision"] == "FAILED"
    assert result["sourceExecution"] == "PASSED"
    assert result["targetExecution"] == "PASSED"
    assert result["resultEquivalence"] == "FAILED"
    assert result["checks"]["localPerformanceSlo"] == "NOT_RUN"
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

    performance_evidence = json.loads((output / "performance.json").read_text())
    assert performance_evidence["state"] == "NOT_RUN_ENVIRONMENT_INVALID"
    assert performance_evidence["queries"] == []

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

    assert result["localDecision"] == "FAILED"
    assert result["sourceExecution"] == "PASSED"
    assert result["targetExecution"] == "PASSED"
    assert result["resultEquivalence"] == "FAILED"
    assert result["checks"]["localPerformanceSlo"] == "NOT_RUN"
    assert result["independentVerification"] == "NOT_RUN"
    assert result["certification"] == "NOT_CERTIFIED"

    environment = json.loads((output / "environment.json").read_text())
    source_runner = environment["sourceRunner"]
    assert source_runner["engineVersionObserved"] == "17.5"
    assert source_runner["engineVersionObservedRaw"] == "17.5 (Homebrew)"
    assert source_runner["profile"]["id"] == "postgresql-17.5"
    assert source_runner["network"] == "LOOPBACK_EPHEMERAL_PORT"

    performance_evidence = json.loads((output / "performance.json").read_text())
    assert performance_evidence["state"] == "NOT_RUN_ENVIRONMENT_INVALID"
    assert performance_evidence["queries"] == []

    manifest = json.loads((output / "runner-evidence.json").read_text())
    assert manifest["contentAddressed"] is True
    for item in manifest["evidence"]:
        content = (output / item["path"]).read_bytes()
        assert item["bytes"] == len(content)
        assert item["digest"] == f"sha256:{sha256(content).hexdigest()}"
    assert not list(output.rglob("*.sqlite3"))
    assert list(output.parent.rglob("*.sqlite3")) == []


def test_postgresql_to_duckdb_executes_on_real_server_175(
    tmp_path: Path,
) -> None:
    capabilities = runner_capabilities()
    ready = {item["profileId"] for item in capabilities["ready"]}
    if "postgresql-17.5" not in ready or "duckdb-1.5.4" not in ready:
        pytest.skip(
            "pinned PostgreSQL 17.5 or DuckDB 1.5.4 runtime is absent; "
            "runtime evidence stays NOT_RUN on this host"
        )

    output = tmp_path / "postgresql-to-duckdb"
    result = verify_route("postgresql-17.5", "duckdb-1.5.4", output)

    assert result["localDecision"] == "FAILED"
    assert result["sourceExecution"] == "PASSED"
    assert result["targetExecution"] == "PASSED"
    assert result["resultEquivalence"] == "FAILED"
    assert result["independentVerification"] == "NOT_RUN"
    assert result["certification"] == "NOT_CERTIFIED"

    environment = json.loads((output / "environment.json").read_text())
    assert environment["sourceRunner"]["engineVersionObserved"] == "17.5"
    assert environment["sourceRunner"]["profile"]["id"] == "postgresql-17.5"

    manifest = json.loads((output / "runner-evidence.json").read_text())
    assert manifest["contentAddressed"] is True
    for item in manifest["evidence"]:
        content = (output / item["path"]).read_bytes()
        assert item["bytes"] == len(content)
        assert item["digest"] == f"sha256:{sha256(content).hexdigest()}"


def test_unavailable_exact_runtime_remains_not_run(tmp_path: Path) -> None:
    with pytest.raises(RunnerBlockedError, match="runtime evidence remains NOT_RUN"):
        verify_route(
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            tmp_path / "blocked",
        )
    assert not (tmp_path / "blocked").exists()
