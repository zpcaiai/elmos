from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_sql_transpiler.materialize import materialize
from elmos_sql_transpiler.models import ParameterContract, TranspileRequest
from elmos_sql_transpiler.transpiler import transpile


def test_typed_transpilation_parses_emits_and_reparses_without_runtime_claims() -> None:
    result = transpile(
        TranspileRequest(
            query_id="orders-by-tenant",
            source_profile="postgresql-18.4",
            target_profile="mysql-8.4.10-lts",
            sql=(
                "SELECT id, created_at FROM orders "
                "WHERE tenant_id = :tenant_id ORDER BY created_at DESC LIMIT 10"
            ),
            parameters=(
                ParameterContract(
                    name="tenant_id",
                    logical_type="unicode-text",
                    nullable=False,
                ),
            ),
        )
    )

    assert result.state == "SYNTAX_READY"
    assert result.target_sql is not None
    # The placeholder is rewritten into MySQL's own bind syntax. Carrying
    # `:tenant_id` through verbatim (what this test asserted before the
    # placeholder fix) produces SQL MySQL does not read as a bind parameter at
    # all -- see tests/test_placeholders.py and placeholders.py.
    assert ":tenant_id" not in result.target_sql
    assert "tenant_id = ?" in result.target_sql
    assert result.syntax_parse == "PASSED"
    assert result.target_emit == "PASSED"
    assert result.target_reparse == "PASSED"
    assert result.parameter_contract == "PASSED"
    assert result.source_execution == "NOT_RUN"
    assert result.target_execution == "NOT_RUN"
    assert result.result_equivalence == "NOT_RUN"
    assert result.certification == "NOT_CERTIFIED"
    assert result.statements[0].source_ast
    assert result.statements[0].target_ast
    assert result.metadata["silentFallbackUsed"] is False
    adapter = result.metadata["targetAdapter"]
    assert adapter["adapterId"] == "core.mysql-8.4.10-lts.sqlglot-target-adapter"
    assert adapter["protocolVersion"] == "1.0"
    assert adapter["targetProfileId"] == "mysql-8.4.10-lts"
    assert adapter["adapterDigest"].startswith("sha256:")
    assert result.metadata["ruleTrace"]
    assert result.metadata["ruleTraceDigest"].startswith("sha256:")
    assert any(
        trace["ruleId"] == "core.sqlglot-target-emitter"
        and trace["outputDigest"].startswith("sha256:")
        and trace["ruleDigest"].startswith("sha256:")
        for trace in result.metadata["ruleTrace"]
    )


def test_positional_group_and_order_references_are_normalized_in_typed_ast() -> None:
    result = transpile(
        TranspileRequest(
            query_id="monthly-revenue",
            source_profile="postgresql-18.4",
            target_profile="sqlserver-2022-cu26",
            sql=(
                "SELECT DATE_TRUNC('month', created_at) AS month, SUM(total) AS revenue "
                "FROM orders GROUP BY 1 ORDER BY 1"
            ),
        )
    )

    assert result.state == "SYNTAX_READY"
    assert "POSITIONAL_REFERENCE_NORMALIZED" in result.statements[0].obligations
    assert result.target_sql is not None
    assert "ORDER BY" in result.target_sql


@pytest.mark.parametrize(
    ("source", "target", "sql"),
    [
        ("postgresql-18.4", "mysql-8.4.10-lts", "SELECT * FROM"),
        ("postgresql-18.4", "mysql-8.4.10-lts", "SELECT 'unterminated"),
        (
            "mysql-8.4.10-lts",
            "sqlite-3.53.3",
            "SELECT GROUP_CONCAT(name ORDER BY name SEPARATOR ',') FROM customers",
        ),
        (
            "oracle-26ai-ee",
            "mysql-8.4.10-lts",
            "SELECT TRUNC(created_at, 'MM') FROM orders",
        ),
    ],
)
def test_invalid_or_unsupported_semantics_are_blocked(source: str, target: str, sql: str) -> None:
    result = transpile(
        TranspileRequest(
            query_id="negative",
            source_profile=source,
            target_profile=target,
            sql=sql,
        )
    )
    assert result.state == "BLOCKED"
    assert result.target_sql is None
    assert result.target_execution == "NOT_RUN"
    assert result.certification == "NOT_CERTIFIED"


def test_materialization_is_complete_create_only_and_does_not_copy_raw_source(
    tmp_path: Path,
) -> None:
    result = transpile(
        TranspileRequest(
            query_id="materialized-query",
            source_profile="sqlite-3.53.3",
            target_profile="postgresql-18.4",
            sql="SELECT id, total FROM orders ORDER BY id LIMIT 10",
        )
    )
    output = tmp_path / "generated"
    report = materialize(result, output)

    assert report["fileCount"] == 8
    assert (output / "target.sql").is_file()
    assert (output / "canonical-ir/query-ir.json").is_file()
    assert (output / "route.json").is_file()
    assert (output / "runner-config.json").is_file()
    assert not (output / "source.sql").exists()
    verification = json.loads((output / "verification.json").read_text())
    assert verification["targetExecution"] == "NOT_RUN"
    assert verification["resultEquivalence"] == "NOT_RUN"
    assert verification["certification"] == "NOT_CERTIFIED"
    runner_config = json.loads((output / "runner-config.json").read_text())
    assert runner_config["sourceRunner"]["status"] == "LOCAL_RUNNER_READY"
    assert runner_config["sourceRunner"]["runtimeEvidence"] == "NOT_RUN"
    assert runner_config["targetRunner"]["status"] == "BLOCKED"
    assert runner_config["targetRunner"]["runtimeEvidence"] == "NOT_RUN"

    with pytest.raises(FileExistsError, match="absent or empty"):
        materialize(result, output)


def test_request_rejects_floating_profiles_same_route_and_oversized_input() -> None:
    with pytest.raises(ValueError, match="unknown exact SQL profile"):
        transpile(
            TranspileRequest(
                query_id="floating",
                source_profile="postgresql-latest",
                target_profile="mysql-8.4.10-lts",
                sql="SELECT 1",
            )
        )
    with pytest.raises(ValueError, match="must differ"):
        transpile(
            TranspileRequest(
                query_id="same",
                source_profile="sqlite-3.53.3",
                target_profile="sqlite-3.53.3",
                sql="SELECT 1",
            )
        )
    with pytest.raises(ValueError, match="one MiB"):
        transpile(
            TranspileRequest(
                query_id="large",
                source_profile="sqlite-3.53.3",
                target_profile="postgresql-18.4",
                sql="SELECT '" + ("a" * 1_048_577) + "'",
            )
        )


# --- fail-closed backstop -------------------------------------------------
#
# An aggregate FILTER combined with an explicit window frame reaches sqlglot's
# `ordered_sql`, which calls `sql_name()` on a `Filter` node that has no such
# attribute.  Before the backstop this AttributeError propagated straight to the
# caller on all eight routes whose target is MySQL or SQL Server, bypassing the
# Batch 31 requirement that target emission fail closed.  Reproduced in bare
# sqlglot at 30.13.0 and 30.14.0, so pinning forward does not remove the need.

_FILTER_WITH_EXPLICIT_FRAME = (
    "SELECT SUM(a) FILTER (WHERE b) OVER "
    "(ORDER BY d ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM t"
)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("postgresql-17.5", "mysql-8.4.10-lts"),
        ("postgresql-17.5", "sqlserver-2022-cu26"),
        ("postgresql-18.4", "mysql-8.4.10-lts"),
        ("postgresql-18.4", "sqlserver-2022-cu26"),
        ("oracle-26ai-ee", "mysql-8.4.10-lts"),
        ("oracle-26ai-ee", "sqlserver-2022-cu26"),
        ("duckdb-1.5.4", "mysql-8.4.10-lts"),
        ("duckdb-1.5.4", "sqlserver-2022-cu26"),
    ],
)
def test_unexpected_emission_faults_are_failed_closed_not_raised(
    source: str, target: str
) -> None:
    result = transpile(
        TranspileRequest(
            query_id="emission-fault",
            source_profile=source,
            target_profile=target,
            sql=_FILTER_WITH_EXPLICIT_FRAME,
        )
    )
    assert result.state == "BLOCKED"
    assert result.target_sql is None
    assert result.target_emit == "FAILED"
    assert result.certification == "NOT_CERTIFIED"
    codes = {diagnostic.code for diagnostic in result.diagnostics}
    # A defect must carry its own code. Reporting it as UNSUPPORTED_SEMANTICS
    # would let an engine crash be counted as a declared subset boundary.
    assert "TARGET_EMISSION_FAULTED" in codes
    assert "UNSUPPORTED_SEMANTICS" not in codes


def test_emission_fault_diagnostic_does_not_leak_source_sql() -> None:
    secret = "SELECT SUM(a) FILTER (WHERE tenant_secret_column) OVER (ORDER BY d ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM t"
    result = transpile(
        TranspileRequest(
            query_id="emission-fault-privacy",
            source_profile="postgresql-17.5",
            target_profile="mysql-8.4.10-lts",
            sql=secret,
        )
    )
    assert result.state == "BLOCKED"
    assert result.metadata["rawSourceSqlPersisted"] is False
    for diagnostic in result.diagnostics:
        assert "tenant_secret_column" not in diagnostic.message


def test_adapter_identity_violations_still_raise_and_are_not_blocked_results() -> None:
    """The backstop must not launder an integrity violation into a verdict.

    If the registry and the emission disagree about who produced the SQL, that is
    not a subset boundary and not a parser defect -- it means the trust chain is
    broken, and it has to stay loud.
    """
    from dataclasses import replace

    from elmos_sql_transpiler import transpiler as transpiler_module

    original = transpiler_module.target_adapter_for_profile

    class _MismatchedAdapter:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

        def emit(self, statement: object) -> object:
            emission = self._inner.emit(statement)  # type: ignore[attr-defined]
            return replace(emission, adapter_digest="sha256:" + "0" * 64)

    transpiler_module.target_adapter_for_profile = (  # type: ignore[assignment]
        lambda profile_id: _MismatchedAdapter(original(profile_id))
    )
    try:
        with pytest.raises(RuntimeError):
            transpile(
                TranspileRequest(
                    query_id="integrity",
                    source_profile="postgresql-17.5",
                    target_profile="mysql-8.4.10-lts",
                    sql="SELECT a FROM t ORDER BY a",
                )
            )
    finally:
        transpiler_module.target_adapter_for_profile = original  # type: ignore[assignment]
