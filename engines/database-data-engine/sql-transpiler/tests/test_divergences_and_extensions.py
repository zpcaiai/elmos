from __future__ import annotations

import pytest

from elmos_sql_transpiler.models import TranspileRequest
from elmos_sql_transpiler.profiles import profile_by_id
from elmos_sql_transpiler.transpiler import transpile


def test_integer_division_normalization() -> None:
    # Unnormalized: raises warning
    unnormalized_req = TranspileRequest(
        query_id="q-div-warn",
        source_profile="postgresql-17.5",
        target_profile="mysql-8.4.10-lts",
        sql="SELECT total / count FROM metrics;",
    )
    res = transpile(unnormalized_req)
    diag_codes = [d.code for d in res.diagnostics]
    assert "INTEGER_DIVISION_SEMANTICS_DIFFER" in diag_codes

    # Normalized with integer_division_mode="truncate"
    normalized_req = TranspileRequest(
        query_id="q-div-truncate",
        source_profile="postgresql-17.5",
        target_profile="mysql-8.4.10-lts",
        sql="SELECT total / count FROM metrics;",
        integer_division_mode="truncate",
    )
    norm_res = transpile(normalized_req)
    norm_diag_codes = [d.code for d in norm_res.diagnostics]
    assert "INTEGER_DIVISION_SEMANTICS_DIFFER" not in norm_diag_codes
    assert "DIV" in norm_res.target_sql or "CAST" in norm_res.target_sql


def test_quote_identifiers_normalization() -> None:
    # Unquoted case folding difference between PG (lower) and Oracle (upper)
    unquoted_req = TranspileRequest(
        query_id="q-quote-warn",
        source_profile="postgresql-17.5",
        target_profile="oracle-26ai-ee",
        sql="SELECT userName FROM userTable;",
    )
    res = transpile(unquoted_req)
    diag_codes = [d.code for d in res.diagnostics]
    assert "IDENTIFIER_CASE_FOLDING_DIFFERS" in diag_codes

    # Normalized with quote_identifiers_mode="all"
    quoted_req = TranspileRequest(
        query_id="q-quote-all",
        source_profile="postgresql-17.5",
        target_profile="oracle-26ai-ee",
        sql="SELECT userName FROM userTable;",
        quote_identifiers_mode="all",
    )
    quoted_res = transpile(quoted_req)
    quoted_diag_codes = [d.code for d in quoted_res.diagnostics]
    assert "IDENTIFIER_CASE_FOLDING_DIFFERS" not in quoted_diag_codes
    assert '"userName"' in quoted_res.target_sql
    assert '"userTable"' in quoted_res.target_sql


@pytest.mark.parametrize(
    "ext_id",
    [
        "mariadb-11.8.8",
        "ibm-db2-11.5.9",
        "bigquery-managed-2026-07-28",
        "snowflake-managed-2026-07-28",
        "clickhouse-26.6",
        "redshift-managed-2026-07-28",
    ],
)
def test_extension_profiles_fail_closed_against_disguise(ext_id: str) -> None:
    with pytest.raises(ValueError) as exc:
        profile_by_id(ext_id)
    msg = str(exc.value)
    assert "is an extension" in msg
    assert "Disguised alias transpilation is strictly prohibited" in msg
