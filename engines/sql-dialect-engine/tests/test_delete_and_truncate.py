from __future__ import annotations

import pytest
import sqlglot

from elmos_sql_dialect.emitter import emit_delete, emit_truncate_table
from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, DialectError
from elmos_sql_dialect.parser import parse_delete, parse_truncate_table
from elmos_sql_dialect.scan import _classify


def test_truncate_table_cross_dialect_translation() -> None:
    sql = "TRUNCATE TABLE accounts;"
    for src in [Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE, Dialect.TSQL]:
        parsed = parse_truncate_table(sql, src)
        assert parsed.table == "accounts"
        assert parsed.schema is None
        for tgt in [Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE, Dialect.TSQL]:
            emitted = emit_truncate_table(parsed, tgt)
            assert "TRUNCATE TABLE" in emitted
            assert "accounts" in emitted

            # Full translate_ddl round-trip
            if src != tgt:
                report = translate_ddl(sql, src.value, tgt.value, statement_kind="TRUNCATE")
                assert report["status"] == "PASSED", report.get("reason")
                assert report["validation"]["syntaxStatus"] == "PASSED"


def test_truncate_table_qualified_with_namespace_mapping() -> None:
    sql = "TRUNCATE TABLE billing.invoices;"
    parsed = parse_truncate_table(sql, Dialect.POSTGRES, namespace_map={"billing": "dbo"})
    assert parsed.table == "invoices"
    assert parsed.schema == "dbo"

    emitted_tsql = emit_truncate_table(parsed, Dialect.TSQL)
    assert emitted_tsql == "TRUNCATE TABLE dbo.invoices"

    emitted_pg = emit_truncate_table(parsed, Dialect.POSTGRES)
    assert emitted_pg == "TRUNCATE TABLE dbo.invoices"


def test_delete_simple_cross_dialect_translation() -> None:
    sql = "DELETE FROM orders WHERE amount_cents <= 0;"
    for src in [Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE, Dialect.TSQL]:
        parsed = parse_delete(sql, src)
        assert parsed.table == "orders"
        assert parsed.predicate is not None

        for tgt in [Dialect.POSTGRES, Dialect.MYSQL, Dialect.ORACLE, Dialect.TSQL]:
            emitted = emit_delete(parsed, tgt)
            assert "DELETE FROM" in emitted
            assert "orders" in emitted
            assert "amount_cents" in emitted

            if src != tgt:
                report = translate_ddl(sql, src.value, tgt.value, statement_kind="DELETE")
                assert report["status"] == "PASSED", report.get("reason")
                assert report["validation"]["syntaxStatus"] == "PASSED"


def test_delete_compound_where_and_namespace() -> None:
    sql = "DELETE FROM app.users WHERE status = 'DEACTIVATED' AND age > 100;"
    parsed = parse_delete(sql, Dialect.POSTGRES, namespace_map={"app": "sec"})
    assert parsed.table == "users"
    assert parsed.schema == "sec"

    emitted_oracle = emit_delete(parsed, Dialect.ORACLE)
    assert "DELETE FROM sec.users" in emitted_oracle
    assert "status" in emitted_oracle
    assert "age" in emitted_oracle

    report = translate_ddl(sql, "postgres", "oracle", statement_kind="DELETE", namespace_map={"app": "sec"})
    assert report["status"] == "PASSED"
    assert report["validation"]["syntaxStatus"] == "PASSED"


def test_delete_fail_closed_on_unsupported_modifiers() -> None:
    # LIMIT / ORDER BY on DELETE is outside certified-dml-v1
    sql_limit = "DELETE FROM orders WHERE id = 1 LIMIT 10;"
    with pytest.raises(DialectError) as exc_limit:
        parse_delete(sql_limit, Dialect.MYSQL)
    assert exc_limit.value.code == "CERTIFIED_DELETE_UNSUPPORTED_MODIFIER"

    # USING clause is outside certified-dml-v1
    sql_using = "DELETE FROM orders USING other WHERE orders.id = other.id;"
    with pytest.raises(DialectError) as exc_using:
        parse_delete(sql_using, Dialect.POSTGRES)
    assert exc_using.value.code == "CERTIFIED_DELETE_UNSUPPORTED_MODIFIER"


def test_scanner_classifies_delete_and_truncate_in_subset() -> None:
    del_stmt = sqlglot.parse_one("DELETE FROM person WHERE id = 42;", read="postgres")
    status, code, _ = _classify(del_stmt, Dialect.POSTGRES)
    assert status == "IN_SUBSET"
    assert code is None

    trunc_stmt = sqlglot.parse_one("TRUNCATE TABLE person;", read="postgres")
    status, code, _ = _classify(trunc_stmt, Dialect.POSTGRES)
    assert status == "IN_SUBSET"
    assert code is None
