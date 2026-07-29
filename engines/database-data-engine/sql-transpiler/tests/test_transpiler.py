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
