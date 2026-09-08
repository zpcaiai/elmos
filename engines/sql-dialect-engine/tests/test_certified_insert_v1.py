"""Typed coverage for the fixed-column literal INSERT profile."""

from __future__ import annotations

import pytest

from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError
from elmos_sql_dialect.parser import parse_insert


@pytest.mark.parametrize("target", ["mysql", "oracle", "tsql"])
def test_literal_seed_insert_reaches_every_other_dialect(target: str) -> None:
    report = translate_ddl(
        "INSERT INTO seed_rows (id, enabled, label, deleted_at) "
        "VALUES (-1, TRUE, 'O''Reilly', NULL), (2, FALSE, 'ready', NULL)",
        "postgres",
        target,
        statement_kind="INSERT",
    )
    assert report["status"] == "PASSED", report
    emitted = report["emitted"] or ""
    assert "INSERT INTO seed_rows (id, enabled, label, deleted_at)" in emitted
    assert "O''Reilly" in emitted
    assert "NULL" in emitted
    if target in {"oracle", "tsql"}:
        assert "1" in emitted and "0" in emitted
    else:
        assert "TRUE" in emitted and "FALSE" in emitted


def test_literal_seed_insert_preserves_mapped_namespace() -> None:
    report = translate_ddl(
        "INSERT INTO app.seed_rows (id, label) VALUES (1, 'ready')",
        "postgres",
        "mysql",
        statement_kind="INSERT",
        namespace_map={"app": "tenant"},
    )
    assert report["status"] == "PASSED", report
    assert report["emitted"].startswith("INSERT INTO tenant.seed_rows")


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        (
            "INSERT INTO seed_rows (id) SELECT source_rows.id FROM source_rows "
            "JOIN other_rows ON other_rows.id = source_rows.id",
            "CERTIFIED_INSERT_SELECT_UNSUPPORTED_QUERY",
        ),
        (
            "INSERT INTO seed_rows (id) VALUES (1) ON CONFLICT (id) DO NOTHING",
            "CERTIFIED_INSERT_UNSUPPORTED_MODIFIER",
        ),
        (
            "INSERT INTO seed_rows (id) VALUES (CURRENT_TIMESTAMP)",
            "CERTIFIED_INSERT_UNSUPPORTED_EXPRESSION",
        ),
        (
            "INSERT INTO seed_rows DEFAULT VALUES",
            "CERTIFIED_INSERT_UNSUPPORTED_MODIFIER",
        ),
    ],
)
def test_non_literal_insert_semantics_fail_closed(sql: str, code: str) -> None:
    report = translate_ddl(sql, "postgres", "mysql", statement_kind="INSERT")
    assert report["status"] == "BLOCKED", report
    assert report["reasonCode"] == code


def test_insert_model_rejects_row_arity_mismatch() -> None:
    with pytest.raises(DialectError, match="CERTIFIED_INSERT_ARITY_MISMATCH"):
        parse_insert("INSERT INTO seed_rows (id, label) VALUES (1)", Dialect.POSTGRES)
