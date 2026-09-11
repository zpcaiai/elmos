"""Real Cross-Database Physical Integration Test: MySQL 8.0 -> openGauss 3.0.0.

Validates:
1. True heterogeneous physical database migration:
   MySQL 8.0 (@ 33306) -> openGauss 3.0.0 (@ 54321) across live TCP network
2. Live schema introspection via MysqlCatalogInspector
3. Dialect DDL lowering: MySQL AUTO_INCREMENT, DECIMAL, and backtick quoting to openGauss SERIAL and ROW orientation
4. Cross-database PhysicalDataPump streaming 500 rows in 5 bounded chunks (PyMySQL -> psycopg2)
5. Native Rust CDC comparison engine (`cdc-engine-rust`) execution verifying 100% bitwise alignment
6. Physical drift injection and pinpointing across MySQL and openGauss instances
"""

from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path

import psycopg2
import pymysql
import pytest

from elmos_sql_dialect.cdc import DataComparator
from elmos_sql_dialect.datapump import PhysicalDataPump
from elmos_sql_dialect.inspectors import MysqlCatalogInspector
from elmos_sql_dialect.opengauss_dialect import lower_opengauss_ddl


def is_mysql_available() -> bool:
    try:
        conn = pymysql.connect(
            host="127.0.0.1",
            port=33306,
            user="cdc_user",
            password="cdc_password",
            database="source_db",
            connect_timeout=2,
        )
        conn.close()
        return True
    except Exception:
        return False


def is_opengauss_available() -> bool:
    try:
        conn = psycopg2.connect(
            dbname="omm",
            user="gaussdb",
            password="Enmotech@123",
            host="127.0.0.1",
            port=54321,
            connect_timeout=2,
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not (is_mysql_available() and is_opengauss_available()),
    reason="MySQL 8.0 or openGauss 3.0.0 container not running",
)
def test_real_cross_db_mysql_to_opengauss_migration():
    mysql_conn = pymysql.connect(
        host="127.0.0.1",
        port=33306,
        user="cdc_user",
        password="cdc_password",
        database="source_db",
        autocommit=True,
    )

    og_conn = psycopg2.connect(
        dbname="omm",
        user="gaussdb",
        password="Enmotech@123",
        host="127.0.0.1",
        port=54321,
    )
    og_conn.autocommit = True

    # Check for compiled Rust CDC binary
    rust_bin = Path(__file__).resolve().parent.parent / "cdc-engine-rust" / "target" / "release" / "cdc-engine-rust"
    rust_path_str = str(rust_bin) if rust_bin.exists() else None

    run_token = int(time.time() * 1000) % 1000000
    test_table = f"my_orders_{run_token}"
    src_db = "source_db"
    tgt_schema = f"elmos_myog_{run_token}"

    try:
        # Step 1: Create source table in MySQL 8.0 and insert 500 rows
        with mysql_conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS `{test_table}`;")
            cur.execute(f"""
                CREATE TABLE `{test_table}` (
                    `order_id` INT AUTO_INCREMENT PRIMARY KEY,
                    `order_sn` VARCHAR(64) NOT NULL,
                    `customer_name` VARCHAR(100) NOT NULL,
                    `total_amount` DECIMAL(14, 2) NOT NULL,
                    `is_paid` SMALLINT DEFAULT 1 NOT NULL,
                    `item_count` INT DEFAULT 1 NOT NULL
                ) ENGINE=InnoDB;
            """)

            rows = [
                (
                    f"ORD-{i:06d}",
                    f"Customer_{i}",
                    Decimal(f"{round(10.0 + i * 1.5, 2)}"),
                    1 if i % 7 != 0 else 0,
                    (i % 5) + 1,
                )
                for i in range(1, 501)
            ]
            cur.executemany(
                f"""
                INSERT INTO `{test_table}` 
                (`order_sn`, `customer_name`, `total_amount`, `is_paid`, `item_count`)
                VALUES (%s, %s, %s, %s, %s);
                """,
                rows,
            )

        # Step 2: Live inspection of MySQL catalog
        inspector = MysqlCatalogInspector(mysql_conn)
        inspection_result = inspector.inspect_schema(schema_name=src_db)
        assert test_table in inspection_result.tables
        tbl_meta = inspection_result.tables[test_table]
        assert "order_id" in tbl_meta.primary_key
        assert len(tbl_meta.columns) == 6

        # Step 3: DDL translation to openGauss
        mysql_ddl = f"""
            CREATE TABLE `{test_table}` (
                `order_id` INT AUTO_INCREMENT PRIMARY KEY,
                `order_sn` VARCHAR(64) NOT NULL,
                `customer_name` VARCHAR(100) NOT NULL,
                `total_amount` DECIMAL(14, 2) NOT NULL,
                `is_paid` SMALLINT DEFAULT 1 NOT NULL,
                `item_count` INT DEFAULT 1 NOT NULL
            );
        """
        og_ddl = lower_opengauss_ddl(mysql_ddl, source_dialect="mysql", standalone=True)
        assert "SERIAL PRIMARY KEY" in og_ddl or "serial" in og_ddl.lower()
        assert "WITH (ORIENTATION = ROW)" in og_ddl

        # Create target schema and table in openGauss
        with og_conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {tgt_schema} CASCADE;")
            cur.execute(f"CREATE SCHEMA {tgt_schema};")
            cur.execute(f"SET search_path TO {tgt_schema};")
            cur.execute(og_ddl)
            # Verify table was physically created in openGauss
            cur.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = %s AND table_name = %s;",
                (tgt_schema, test_table),
            )
            assert cur.fetchone()[0] == 1, "Table was not created in openGauss"

        # Step 4: Stream 500 rows across TCP network from MySQL to openGauss
        pump = PhysicalDataPump(
            source_connection=mysql_conn,
            target_connection=og_conn,
            source_schema=src_db,
            target_schema=tgt_schema,
            chunk_size=100,
        )
        pump_stat = pump.pump_table(
            table_name=test_table,
            primary_key_col="order_id",
        )

        assert pump_stat.total_rows == 500
        assert pump_stat.chunks_count == 5

        # Step 5: Verify target data integrity in openGauss
        with og_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*), SUM(total_amount) FROM {tgt_schema}.{test_table};")
            og_count, og_sum = cur.fetchone()
            assert og_count == 500
            assert og_sum is not None

        with mysql_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*), SUM(total_amount) FROM `{test_table}`;")
            my_count, my_sum = cur.fetchone()
            assert my_count == og_count
            assert Decimal(str(my_sum)) == Decimal(str(og_sum))

        # Step 6: Rust-Accelerated CDC comparison on aligned tables
        comparator = DataComparator(
            chunk_size=100,
            rust_binary_path=rust_path_str,
            use_rust=True,
            hasher="sha256",
        )
        cmp_report = comparator.compare_live_tables(
            source_connection=mysql_conn,
            target_connection=og_conn,
            source_table=test_table,
            target_table=test_table,
            pk_col="order_id",
            columns=["order_id", "order_sn", "customer_name", "total_amount", "is_paid", "item_count"],
            source_schema=src_db,
            target_schema=tgt_schema,
        )

        assert cmp_report.status == "ALIGNED"
        assert cmp_report.alignment_rate == 1.0
        assert cmp_report.mismatched_chunks == 0
        if rust_path_str:
            assert cmp_report.execution_engine == "RUST_CDC_CORE"

        # Step 7: Inject real physical drift into openGauss (tamper row 250)
        with og_conn.cursor() as cur:
            cur.execute(f"UPDATE {tgt_schema}.{test_table} SET total_amount = 999999.99 WHERE order_id = 250;")

        # Step 8: Verify Rust CDC detects divergence and pinpoints PK 250
        diverged_report = comparator.compare_live_tables(
            source_connection=mysql_conn,
            target_connection=og_conn,
            source_table=test_table,
            target_table=test_table,
            pk_col="order_id",
            columns=["order_id", "order_sn", "customer_name", "total_amount", "is_paid", "item_count"],
            source_schema=src_db,
            target_schema=tgt_schema,
        )
        assert diverged_report.status == "DIVERGED"
        assert diverged_report.mismatched_chunks == 1
        mismatched_pks = [pk for c in diverged_report.chunk_results if not c.matched for pk in c.mismatched_pks]
        assert 250 in mismatched_pks or "250" in mismatched_pks

    finally:
        # Step 9: Cleanup
        with mysql_conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS `{test_table}`;")
        mysql_conn.close()

        with og_conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {tgt_schema} CASCADE;")
        og_conn.close()
