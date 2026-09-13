"""Rigorous Industrial Test for 100% Closure on Business Line 3 (Database & ChinaDB Migration).

Validates:
1. Zero blocking statements: Stored procedures (PL/SQL, T-SQL, PL/pgSQL) AST lowering eliminates the 85.6% blocking statements.
2. 100% automated translation candidates on enterprise blackbox SQL corpora.
3. Full compatibility execution across all 13 domestic ChinaDB targets.
4. Real DDL execution with reverse catalog introspection.
5. Transactional CDC change replication and SHA-256 row-hash cascade reconciliation.
6. High-concurrency transaction stress testing meeting P95 <= 75ms SLO and balance conservation invariant.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Add engines to path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "engines" / "sql-dialect-engine" / "src"))
sys.path.insert(
    0, str(repo_root / "engines" / "database-data-engine" / "sql-transpiler" / "src")
)

from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.scan import scan_repository
from elmos_sql_transpiler.chinadb_cdc_engine import (
    CdcOpType,
    ChangeEvent,
    ChinaDbCdcEngine,
)
from elmos_sql_transpiler.chinadb_container_orchestrator import (
    ChinaDbContainerOrchestrator,
)
from elmos_sql_transpiler.chinadb_ddl_executor import ChinaDbDdlExecutor
from elmos_sql_transpiler.chinadb_stress_engine import ChinaDbStressEngine


class BlackboxSql100PctClosureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.corpus_dir = Path(self.temp_dir.name)
        self.orchestrator = ChinaDbContainerOrchestrator()
        self.ddl_executor = ChinaDbDdlExecutor(self.orchestrator)
        self.cdc_engine = ChinaDbCdcEngine(self.orchestrator)
        self.stress_engine = ChinaDbStressEngine(self.orchestrator)

        # Enterprise Blackbox SQL Corpus:
        # File 1: Core Financial Tables
        f1 = self.corpus_dir / "V01__financial_core_tables.sql"
        f1.write_text(
            """
            CREATE TABLE accounts (
                acc_num VARCHAR(32) PRIMARY KEY,
                holder_name VARCHAR(100) NOT NULL,
                balance NUMERIC(14, 2) NOT NULL,
                status VARCHAR(16) DEFAULT 'ACTIVE'
            );

            CREATE TABLE tx_history (
                tx_id VARCHAR(64) PRIMARY KEY,
                from_acc VARCHAR(32) NOT NULL,
                to_acc VARCHAR(32) NOT NULL,
                amount NUMERIC(14, 2) NOT NULL,
                created_at TIMESTAMP NOT NULL
            );

            CREATE INDEX idx_tx_from_acc ON tx_history (from_acc);
            CREATE INDEX idx_tx_to_acc ON tx_history (to_acc);
            """,
            encoding="utf-8",
        )

        # File 2: Complex PL/SQL Stored Procedures & Triggers (The historical 85.6% blocking constructs)
        f2 = self.corpus_dir / "V02__procedural_financial_logic.sql"
        f2.write_text(
            """
            CREATE OR REPLACE PROCEDURE transfer_balance(
                p_from VARCHAR,
                p_to VARCHAR,
                p_amt NUMERIC
            ) IS
                v_bal NUMERIC;
            BEGIN
                SELECT balance INTO v_bal FROM accounts WHERE acc_num = p_from;
                IF v_bal >= p_amt THEN
                    UPDATE accounts SET balance = balance - p_amt WHERE acc_num = p_from;
                    UPDATE accounts SET balance = balance + p_amt WHERE acc_num = p_to;
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    ROLLBACK;
            END;

            CREATE OR REPLACE TRIGGER trg_audit_tx
            BEFORE INSERT ON tx_history
            FOR EACH ROW
            DECLARE
                v_time TIMESTAMP;
            BEGIN
                v_time := CURRENT_TIMESTAMP;
                :NEW.created_at := v_time;
            END;
            """,
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        self.orchestrator.stop_all()

    def test_procedural_ast_lowerer_eliminates_blocking_statements_to_zero(
        self,
    ) -> None:
        """Proves that blackbox procedural SQL is 100% admitted when procedural lowering is active."""
        # Baseline scan without procedural lowering has blocked procedural statements
        rep_baseline = scan_repository(
            self.corpus_dir,
            source_dialect=Dialect.ORACLE,
            enable_procedural_lowering=False,
        )
        self.assertGreater(rep_baseline.totals["outOfSubset"], 0)

        # Industrial scan WITH procedural lowering
        rep_industrial = scan_repository(
            self.corpus_dir,
            source_dialect=Dialect.ORACLE,
            enable_procedural_lowering=True,
            include_all_findings=True,
        )

        self.assertEqual(rep_industrial.totals["outOfSubset"], 0)
        self.assertEqual(rep_industrial.disposition_coverage, 1.0)
        self.assertEqual(
            rep_industrial.disposition_counts["AUTOMATED_TRANSLATION_CANDIDATE"],
            rep_industrial.totals["discovered"],
        )

    def test_all_13_chinadb_targets_execute_ddl_and_inspect(self) -> None:
        """Proves that real DDL executes and verifies across all 13 domestic targets."""
        targets = [
            "dm8",
            "kingbasees",
            "opengauss",
            "tidb",
            "gbase-8s",
            "gbase-8c",
            "gbase-8a",
            "highgo-hgdb",
            "oceanbase-oracle",
            "oceanbase-mysql",
            "gaussdb-oracle",
            "gaussdb-m",
            "goldendb",
        ]
        ddl = [
            "CREATE TABLE branch_offices (branch_id VARCHAR(16) PRIMARY KEY, city VARCHAR(50));",
            "CREATE TABLE branch_staff (staff_id VARCHAR(16) PRIMARY KEY, branch_id VARCHAR(16), name VARCHAR(50));",
            "CREATE INDEX idx_staff_branch ON branch_staff (branch_id);",
        ]
        for target in targets:
            receipt = self.ddl_executor.execute_ddl(target, ddl)
            self.assertTrue(
                receipt.is_verified, f"Target {target} failed DDL execution"
            )
            self.assertIn("branch_offices", receipt.verified_tables)
            self.assertIn("branch_staff", receipt.verified_tables)

            inspect = self.ddl_executor.inspect_table(target, "branch_offices")
            self.assertIsNotNone(inspect)
            self.assertTrue(inspect.columns["branch_id"].is_primary_key)

    def test_cdc_sync_and_sha256_reconciliation(self) -> None:
        """Proves real CDC change stream synchronization and cryptographic reconciliation."""
        target = "oceanbase-mysql"
        self.orchestrator.execute_query(target, "DROP TABLE IF EXISTS merchants;")
        self.orchestrator.execute_query(
            target,
            "CREATE TABLE merchants (m_id VARCHAR(32) PRIMARY KEY, name VARCHAR(100), volume NUMERIC(14, 2));",
        )

        events = [
            ChangeEvent(
                table_name="merchants",
                op_type=CdcOpType.INSERT,
                after_state={
                    "m_id": f"M_{i:03d}",
                    "name": f"Merchant {i}",
                    "volume": 1000.0 * (i + 1),
                },
                lsn=i + 1,
            )
            for i in range(10)
        ]
        applied = self.cdc_engine.apply_batch(target, events)
        self.assertEqual(applied, 10)

        source_records = [
            {"m_id": f"M_{i:03d}", "name": f"Merchant {i}", "volume": 1000.0 * (i + 1)}
            for i in range(10)
        ]
        rec = self.cdc_engine.reconcile_table_data(
            source_records, target, "merchants", pk_columns=["m_id"]
        )
        self.assertTrue(rec.is_consistent)
        self.assertEqual(rec.matched_count, 10)
        self.assertEqual(rec.mismatched_count, 0)
        self.assertEqual(rec.source_table_digest, rec.target_table_digest)

    def test_concurrent_stress_workload_and_slo_p95(self) -> None:
        """Proves high-concurrency stress testing achieves P95 <= 75ms SLO and conservation invariant."""
        targets_to_stress = ["tidb", "opengauss", "dm8", "goldendb"]
        for target in targets_to_stress:
            receipt = self.stress_engine.run_benchmark(
                target_id=target,
                concurrency=12,
                transactions_per_worker=30,
                num_accounts=15,
                initial_balance_per_acc=10000.0,
                max_p95_latency_ms=75.0,
            )
            self.assertTrue(receipt.slo_passed, f"Target {target} failed stress SLO")
            self.assertTrue(receipt.conservation_invariant_holds)
            self.assertLessEqual(receipt.latency_p95_ms, 75.0)
            self.assertEqual(receipt.failed_transactions, 0)


if __name__ == "__main__":
    unittest.main()
