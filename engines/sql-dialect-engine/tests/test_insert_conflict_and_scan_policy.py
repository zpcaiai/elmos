from __future__ import annotations

import tempfile
from pathlib import Path

from elmos_sql_dialect.engine import translate_ddl
from elmos_sql_dialect.models import Dialect, TypeMigrationPolicy
from elmos_sql_dialect.scan import scan_repository


def test_insert_on_conflict_do_nothing_postgres_to_mysql() -> None:
    sql_pg = "INSERT INTO users (id, name) VALUES (1, 'alice') ON CONFLICT DO NOTHING;"
    report = translate_ddl(sql_pg, "postgres", "mysql", statement_kind="INSERT")
    assert report["status"] == "PASSED", report
    assert report["emitted"] == "INSERT IGNORE INTO users (id, name) VALUES (1, 'alice')"


def test_insert_ignore_mysql_to_postgres() -> None:
    sql_mysql = "INSERT IGNORE INTO users (id, name) VALUES (1, 'alice');"
    report = translate_ddl(sql_mysql, "mysql", "postgres", statement_kind="INSERT")
    assert report["status"] == "PASSED", report
    assert report["emitted"] == "INSERT INTO users (id, name) VALUES (1, 'alice') ON CONFLICT DO NOTHING"


def test_insert_conflict_oracle_and_tsql_fails_closed() -> None:
    sql_pg = "INSERT INTO users (id, name) VALUES (1, 'alice') ON CONFLICT DO NOTHING;"
    report_ora = translate_ddl(sql_pg, "postgres", "oracle", statement_kind="INSERT")
    assert report_ora["status"] == "BLOCKED", report_ora
    assert report_ora["reasonCode"] == "CERTIFIED_INSERT_UNSUPPORTED_TARGET"

    report_tsql = translate_ddl(sql_pg, "postgres", "tsql", statement_kind="INSERT")
    assert report_tsql["status"] == "BLOCKED", report_tsql
    assert report_tsql["reasonCode"] == "CERTIFIED_INSERT_UNSUPPORTED_TARGET"


def test_scan_repository_with_type_policy_and_alter_column() -> None:
    sql_content = """
    CREATE TABLE accounts (
        id BIGINT UNSIGNED NOT NULL,
        balance DECIMAL NOT NULL,
        PRIMARY KEY (id)
    );
    ALTER TABLE accounts ALTER COLUMN balance TYPE DECIMAL(18, 2);
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        sql_file = Path(tmpdir) / "01_schema.sql"
        sql_file.write_text(sql_content, encoding="utf-8")

        # 1. Scan without policy -> Fail-closed on unsigned bigint
        report_default = scan_repository(tmpdir, Dialect.MYSQL)
        assert report_default.totals["outOfSubset"] >= 1
        codes = {f.reason_code for f in report_default.findings if f.status == "OUT_OF_SUBSET"}
        assert "CERTIFIED_DDL_UNSIGNED_BIGINT_UNREPRESENTABLE" in codes

        # 2. Scan with TypeMigrationPolicy and allow_alter_column=True -> Admitted to subset
        policy = TypeMigrationPolicy(
            unsigned_bigint="decimal20",
            unbounded_decimal="decimal38_10",
        )
        report_with_policy = scan_repository(
            tmpdir,
            Dialect.MYSQL,
            type_policy=policy,
            allow_alter_column=True,
        )
        # All statements in the schema should now be IN_SUBSET
        assert report_with_policy.totals["inSubset"] == 2
        assert report_with_policy.totals["outOfSubset"] == 0
