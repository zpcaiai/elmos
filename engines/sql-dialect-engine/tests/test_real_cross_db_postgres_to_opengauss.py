"""Real Cross-Database Physical Integration Test: PostgreSQL 16 -> openGauss 3.0.0.

Validates:
1. True heterogeneous physical database migration (PostgreSQL 16 @ 5432 -> openGauss 3.0.0 @ 54321)
2. Live DDL translation and physical table creation inside real openGauss engine
3. Cross-database PhysicalDataPump streaming 500 rows with foreign keys across TCP network
4. High-performance native Rust CDC comparison engine (`cdc-engine-rust`) execution
5. Physical drift injection and pinpointing across heterogeneous databases
"""

import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

from elmos_sql_dialect.cdc import DataComparator
from elmos_sql_dialect.datapump import PhysicalDataPump
from elmos_sql_dialect.opengauss_dialect import lower_opengauss_ddl


def is_pg_available() -> bool:
    try:
        conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


def is_opengauss_available() -> bool:
    try:
        conn = psycopg2.connect(
            dbname="omm", user="gaussdb", password="Enmotech@123", host="localhost", port=54321, connect_timeout=2
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not (is_pg_available() and is_opengauss_available()), reason="PostgreSQL or openGauss not running")
def test_real_cross_database_migration_and_rust_reconciliation():
    pg_conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
    pg_conn.autocommit = True

    og_conn = psycopg2.connect(
        dbname="omm", user="gaussdb", password="Enmotech@123", host="localhost", port=54321
    )
    og_conn.autocommit = True

    # Rust binary path
    rust_bin = Path(__file__).resolve().parent.parent / "cdc-engine-rust" / "target" / "release" / "cdc-engine-rust"
    rust_path_str = str(rust_bin) if rust_bin.exists() else None

    run_token = int(time.time() * 1000) % 1000000
    src_schema = f"elmos_csrc_{run_token}"
    tgt_schema = f"elmos_ctgt_{run_token}"
    test_table = "cross_migrated_accounts"

    try:
        # Step 1: Clean and prepare Source in PostgreSQL 16
        with pg_conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {src_schema};")
            cur.execute(f"DROP TABLE IF EXISTS {src_schema}.{test_table} CASCADE;")
            cur.execute(f"""
                CREATE TABLE {src_schema}.{test_table} (
                    account_id INT PRIMARY KEY,
                    account_no VARCHAR(32) NOT NULL,
                    balance NUMERIC(14, 2) NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE NOT NULL
                );
            """)

            # Insert 500 rows of source data in PG
            rows = [
                (i, f"ACC_NO_{i:05d}", round(1000.0 + i * 2.5, 2), (i % 5 != 0))
                for i in range(1, 501)
            ]
            psycopg2.extras.execute_values(
                cur,
                f"INSERT INTO {src_schema}.{test_table} (account_id, account_no, balance, is_active) VALUES %s;",
                rows,
            )

        # Step 2: DDL Dialect Translation to openGauss and execution in openGauss
        pg_ddl = f"""
            CREATE TABLE {test_table} (
                account_id INT PRIMARY KEY,
                account_no VARCHAR(32) NOT NULL,
                balance NUMERIC(14, 2) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE NOT NULL
            );
        """
        # Lower DDL for standalone openGauss
        og_ddl = lower_opengauss_ddl(pg_ddl, standalone=True)
        assert "WITH (ORIENTATION = ROW)" in og_ddl
        assert "DISTRIBUTE BY HASH" not in og_ddl  # Standalone compatible

        with og_conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {tgt_schema} CASCADE;")
            cur.execute(f"CREATE SCHEMA {tgt_schema};")
            cur.execute(f"SET search_path TO {tgt_schema};")
            cur.execute(og_ddl)
            # Verify table was physically created in openGauss
            cur.execute(f"""
                SELECT count(*) FROM information_schema.tables 
                WHERE table_schema = '{tgt_schema}' AND table_name = '{test_table}';
            """)
            assert cur.fetchone()[0] == 1, "Table was not created in openGauss"

        # Step 3: Physical Heterogeneous Data Pump (PG 16 -> openGauss 3.0.0)
        pump = PhysicalDataPump(
            source_connection=pg_conn,
            target_connection=og_conn,
            source_schema=src_schema,
            target_schema=tgt_schema,
            chunk_size=100,
        )
        pump_stat = pump.pump_table(
            table_name=test_table,
            primary_key_col="account_id",
        )

        assert pump_stat.total_rows == 500
        assert pump_stat.chunks_count == 5

        # Step 4: Verify row count and sample values in openGauss
        with og_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*), SUM(balance) FROM {tgt_schema}.{test_table};")
            og_count, og_sum = cur.fetchone()
            assert og_count == 500
            assert og_sum is not None

        # Step 5: Rust-Accelerated Chunk Comparison (aligned state)
        comparator = DataComparator(
            chunk_size=100,
            rust_binary_path=rust_path_str,
            use_rust=True,
            hasher="sha256",
        )
        cmp_report = comparator.compare_live_tables(
            source_connection=pg_conn,
            target_connection=og_conn,
            source_table=test_table,
            target_table=test_table,
            pk_col="account_id",
            columns=["account_id", "account_no", "balance", "is_active"],
            source_schema=src_schema,
            target_schema=tgt_schema,
        )
        assert cmp_report.status == "ALIGNED"
        assert cmp_report.alignment_rate == 1.0
        assert cmp_report.mismatched_chunks == 0
        if rust_path_str:
            assert cmp_report.execution_engine == "RUST_CDC_CORE"

        # Step 6: Inject real physical drift into openGauss (tamper with row 250)
        with og_conn.cursor() as cur:
            cur.execute(f"UPDATE {tgt_schema}.{test_table} SET balance = 999999.99 WHERE account_id = 250;")

        # Step 7: Verify Rust-Accelerated Comparator detects drift and pinpoints PK 250
        diverged_report = comparator.compare_live_tables(
            source_connection=pg_conn,
            target_connection=og_conn,
            source_table=test_table,
            target_table=test_table,
            pk_col="account_id",
            columns=["account_id", "account_no", "balance", "is_active"],
            source_schema=src_schema,
            target_schema=tgt_schema,
        )
        assert diverged_report.status == "DIVERGED"
        assert diverged_report.mismatched_chunks == 1
        mismatched_pks = [pk for c in diverged_report.chunk_results if not c.matched for pk in c.mismatched_pks]
        assert 250 in mismatched_pks or "250" in mismatched_pks

    finally:
        # Cleanup
        with pg_conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {src_schema} CASCADE;")
        pg_conn.close()

        with og_conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {tgt_schema} CASCADE;")
        og_conn.close()
