"""Enterprise Blackbox SQL Coverage & Handoff Integration Test.

Tests that arbitrary enterprise blackbox SQL estates achieve 100% disposition
coverage through the dual-track auto-repair + handoff ledger architecture.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "engines" / "sql-dialect-engine" / "src"),
)

from elmos_sql_dialect.database_handoff_ledger import DatabaseHandoffLedger
from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.scan import scan_repository
from elmos_sql_dialect.sql_diagnostic_auto_repairer import SqlDiagnosticAutoRepairer


class EnterpriseBlackboxSqlCoverageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.corpus_dir = Path(self.temp_dir.name)
        self.schema_dir = Path(__file__).resolve().parents[2] / "schemas" / "batch31"

        # Create realistic enterprise blackbox migration scripts
        # V1: Standard DDL with dirty directives and proprietary data types
        v1 = self.corpus_dir / "V1__legacy_tables.sql"
        v1.write_text(
            """
            \\c enterprise_db;
            CREATE TABLE public.departments (
                dept_id SERIAL PRIMARY KEY,
                dept_name VARCHAR(100) NOT NULL
            );

            CREATE TABLE public.employees (
                emp_id SERIAL PRIMARY KEY,
                dept_id INT REFERENCES public.departments(dept_id),
                full_name VARCHAR(120) NOT NULL,
                salary DECIMAL(12, 2) NOT NULL
            );
            """,
            encoding="utf-8",
        )

        # V2: Oracle-style PL/SQL package with autonomous transaction
        v2 = self.corpus_dir / "V2__audit_package.sql"
        v2.write_text(
            """
            CREATE OR REPLACE PROCEDURE log_security_event(msg VARCHAR) AS
            PRAGMA AUTONOMOUS_TRANSACTION;
            BEGIN
                INSERT INTO audit_log (event_message, created_at) VALUES (msg, CURRENT_TIMESTAMP);
                COMMIT;
            END;
            """,
            encoding="utf-8",
        )

        # V3: Dynamic SQL procedure
        v3 = self.corpus_dir / "V3__dynamic_reporting.sql"
        v3.write_text(
            """
            CREATE PROCEDURE run_partition_cleanup(tbl_name VARCHAR) AS
            BEGIN
                EXECUTE IMMEDIATE 'TRUNCATE TABLE ' || tbl_name;
            END;
            """,
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sql_auto_repairer_cleans_directives_and_schemas(self) -> None:
        repairer = SqlDiagnosticAutoRepairer(
            namespace_map={"public": "dbo"},
            target_dialect="postgresql",
        )

        raw_sql = (
            "\\c my_db\nCREATE TABLE public.orders ([id] INT, created_at SYSDATE);"
        )
        result = repairer.repair_statement(raw_sql)

        self.assertTrue(result.is_modified)
        self.assertNotIn("\\c", result.repaired_sql)
        self.assertIn("dbo.orders", result.repaired_sql)
        self.assertIn('"id"', result.repaired_sql)
        self.assertIn("CURRENT_TIMESTAMP", result.repaired_sql)

    def test_end_to_end_enterprise_sql_scan_achieves_100_percent_coverage(self) -> None:
        report = scan_repository(
            repository=self.corpus_dir,
            source_dialect=Dialect.POSTGRES,
            include_all_findings=True,
            namespace_map={"public": "dbo"},
        )

        self.assertGreater(report.totals["discovered"], 0)
        # Verify 100% disposition coverage on raw scan
        self.assertEqual(report.disposition_coverage, 1.0)

        # Build formal DatabaseHandoffLedger
        ledger = DatabaseHandoffLedger.from_report(report)
        self.assertTrue(ledger.is_100_percent_covered())
        self.assertEqual(ledger.disposition_coverage, 1.0)
        self.assertEqual(
            ledger.total_discovered,
            len(ledger.automated_candidates) + len(ledger.manual_items),
        )

        backlog = ledger.to_manual_review_backlog()

        # Validate against Batch 31 schema
        schema_file = self.schema_dir / "manual-review-backlog.schema.json"
        if schema_file.exists():
            schema = json.loads(schema_file.read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema)
            errors = list(validator.iter_errors(backlog))
            self.assertEqual(errors, [], f"Schema validation errors: {errors}")

        # Check Markdown dossier generation
        dossier = ledger.generate_markdown_dossier()
        self.assertIn("Executive Disposition Summary", dossier)
        self.assertIn("100% Accounted", dossier)


if __name__ == "__main__":
    unittest.main()
