"""Tests for SqlDiagnosticAutoRepairer and DatabaseHandoffLedger."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None
import pytest

from elmos_sql_dialect.database_handoff_ledger import DatabaseHandoffLedger
from elmos_sql_dialect.scan import ScanFinding
from elmos_sql_dialect.sql_diagnostic_auto_repairer import SqlDiagnosticAutoRepairer


def test_sql_diagnostic_auto_repairer_stage1_directives():
    repairer = SqlDiagnosticAutoRepairer(target_dialect="postgresql")

    raw_sql = "\\c my_database\nSELECT 1;"
    res = repairer.repair_statement(raw_sql)
    assert res.is_modified
    assert "\\c" not in res.repaired_sql
    assert "STRIPPED_CLIENT_SLASH_COMMAND" in res.repairs_applied

    raw_delim = "DELIMITER //\nCREATE TABLE t (id INT);//\nDELIMITER ;"
    res_delim = repairer.repair_statement(raw_delim)
    assert res_delim.is_modified
    assert "DELIMITER" not in res_delim.repaired_sql


def test_sql_diagnostic_auto_repairer_stage2_identifiers_and_schema():
    repairer = SqlDiagnosticAutoRepairer(
        namespace_map={"public": "dbo", "auth": "sec"},
        target_dialect="postgresql",
    )

    raw_sql = "SELECT [user_id], `username` FROM public.users JOIN auth.tokens ON [user_id] = `token_uid`;"
    res = repairer.repair_statement(raw_sql)
    assert res.is_modified
    assert '"user_id"' in res.repaired_sql
    assert '"username"' in res.repaired_sql
    assert "dbo.users" in res.repaired_sql
    assert "sec.tokens" in res.repaired_sql
    assert "NORMALIZED_BRACKET_IDENTIFIERS" in res.repairs_applied
    assert "NORMALIZED_BACKTICK_IDENTIFIERS" in res.repairs_applied


def test_sql_diagnostic_auto_repairer_stage3_functions_and_types():
    repairer = SqlDiagnosticAutoRepairer(target_dialect="postgresql")

    raw_sql = """
    CREATE TABLE orders (
        order_id NUMBER(18, 0) PRIMARY KEY,
        customer_name VARCHAR2(100),
        amount NUMBER(12, 2),
        notes CLOB,
        created_at SYSDATE
    );
    """
    res = repairer.repair_statement(raw_sql)
    assert res.is_modified
    assert "VARCHAR(100)" in res.repaired_sql
    assert "DECIMAL(12, 2)" in res.repaired_sql
    assert "TEXT" in res.repaired_sql
    assert "CURRENT_TIMESTAMP" in res.repaired_sql

    raw_query = "SELECT NVL(discount, 0), IFNULL(tax, 0) FROM orders;"
    res_query = repairer.repair_statement(raw_query)
    assert res_query.is_modified
    assert "COALESCE(discount, 0)" in res_query.repaired_sql
    assert "COALESCE(tax, 0)" in res_query.repaired_sql


def test_database_handoff_ledger_100_percent_disposition_coverage():
    findings = [
        ScanFinding(
            source_path="db/migration/V1__init.sql",
            statement_index=1,
            status="IN_SUBSET",
            statement_kind="Create",
            reason_code=None,
            reason=None,
            family=None,
            excerpt="CREATE TABLE accounts (id INT PRIMARY KEY);",
            disposition="AUTOMATED_TRANSLATION_CANDIDATE",
        ),
        ScanFinding(
            source_path="db/migration/V2__dynamic.sql",
            statement_index=1,
            status="OUT_OF_SUBSET",
            statement_kind="Execute",
            reason_code="DYNAMIC_SQL_CONCATENATION",
            reason="Dynamic SQL string concatenation via EXECUTE IMMEDIATE",
            family="statement-kind",
            excerpt="EXECUTE IMMEDIATE 'SELECT * FROM ' || tab_name;",
            disposition="MANUAL_MIGRATION_REQUIRED",
        ),
        ScanFinding(
            source_path="db/migration/V3__autonomous.sql",
            statement_index=1,
            status="OUT_OF_SUBSET",
            statement_kind="Procedure",
            reason_code="AUTONOMOUS_TRANSACTION",
            reason="PRAGMA AUTONOMOUS_TRANSACTION in procedure body",
            family="statement-kind",
            excerpt="CREATE PROCEDURE log_audit() AS PRAGMA AUTONOMOUS_TRANSACTION ...",
            disposition="MANUAL_MIGRATION_REQUIRED",
        ),
        ScanFinding(
            source_path="db/migration/V4__directive.sql",
            statement_index=1,
            status="OUT_OF_SUBSET",
            statement_kind=None,
            reason_code="CERTIFIED_DDL_CLIENT_DIRECTIVE",
            reason="psql client slash command",
            family="source-format",
            excerpt="\\i /tmp/seed.sql",
            disposition="SOURCE_FORMAT_REVIEW",
        ),
    ]

    ledger = DatabaseHandoffLedger.from_findings(findings, report_digest="sha256:" + "a" * 64)

    assert ledger.total_discovered == 4
    assert len(ledger.automated_candidates) == 1
    assert len(ledger.manual_items) == 3
    assert ledger.disposition_coverage == 1.0
    assert ledger.is_100_percent_covered()

    backlog = ledger.to_manual_review_backlog()
    assert backlog["schema_version"] == 1
    assert backlog["kind"] == "elmos.batch31.manual-review-backlog"
    assert backlog["summary"]["total"] == 3
    assert backlog["summary"]["open"] == 3
    assert backlog["summary"]["release_blocked"] is True

    # Validate against actual repository schema
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "batch31" / "manual-review-backlog.schema.json"
    if schema_path.exists() and jsonschema is not None:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(instance=backlog, schema=schema)

    # Verify Markdown Dossier generation
    dossier = ledger.generate_markdown_dossier()
    assert "Executive Disposition Summary" in dossier
    assert "100% Accounted" in dossier
    assert "Item #001 [P0] `DYNAMIC_SQL_CONCATENATION`" in dossier
    assert "Item #002 [P0] `AUTONOMOUS_TRANSACTION`" in dossier
    assert "Item #003 [P2] `CERTIFIED_DDL_CLIENT_DIRECTIVE`" in dossier
