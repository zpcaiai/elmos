"""Real physical PostgreSQL 16 Data Comparator and Chunk Hashing Test.

Validates:
1. Streaming live table rows via ChunkReader directly into DataComparator
2. Chunk-based hashing and mismatch detection
3. Exact row-level diff identification (MODIFIED, MISSING_IN_TARGET, EXTRA_IN_TARGET)
"""

import pytest
import psycopg2
import psycopg2.extras
from elmos_sql_dialect.cdc import DataComparator


def is_pg_available() -> bool:
    try:
        conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not is_pg_available(), reason="PostgreSQL 16 not running locally")
def test_real_live_data_comparator_mismatch_pinpointing():
    conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
    conn.autocommit = True
    schema_name = "elmos_cmp_test"

    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name};")
        cur.execute(f"DROP TABLE IF EXISTS {schema_name}.orders_source CASCADE;")
        cur.execute(f"DROP TABLE IF EXISTS {schema_name}.orders_target CASCADE;")
        cur.execute(f"""
            CREATE TABLE {schema_name}.orders_source (
                order_id INT PRIMARY KEY,
                customer VARCHAR(50),
                amount NUMERIC(10, 2),
                status VARCHAR(20)
            );
        """)
        cur.execute(f"""
            CREATE TABLE {schema_name}.orders_target (
                order_id INT PRIMARY KEY,
                customer VARCHAR(50),
                amount NUMERIC(10, 2),
                status VARCHAR(20)
            );
        """)

        # Insert 600 rows into source
        rows = [
            (i, f"Customer_{i}", i * 1.5, "COMPLETED")
            for i in range(1, 601)
        ]
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO {schema_name}.orders_source (order_id, customer, amount, status) VALUES %s",
            rows,
        )

        # Copy to target with 3 intentional discrepancies:
        # 1. order_id = 250 is MODIFIED (amount differs)
        # 2. order_id = 599 is MISSING_IN_TARGET (omitted)
        # 3. order_id = 999 is EXTRA_IN_TARGET (added only to target)
        target_rows = [
            (r[0], r[1], r[2] if r[0] != 250 else 9999.99, r[3])
            for r in rows
            if r[0] != 599
        ]
        target_rows.append((999, "Extra_Customer", 123.45, "PENDING"))

        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO {schema_name}.orders_target (order_id, customer, amount, status) VALUES %s",
            target_rows,
        )

    try:
        comparator = DataComparator(chunk_size=100)
        report = comparator.compare_live_tables(
            source_connection=conn,
            target_connection=conn,
            source_table="orders_source",
            target_table="orders_target",
            pk_col="order_id",
            columns=["order_id", "customer", "amount", "status"],
            source_schema=schema_name,
            target_schema=schema_name,
        )

        assert report.total_source_rows == 600
        assert report.total_target_rows == 600
        assert report.total_chunks == 7  # 601 total distinct PKs / 100
        assert report.status == "DIVERGED"
        assert report.mismatched_chunks >= 2

        # Collect all mismatched row diffs across all chunks
        all_diffs = []
        for chunk in report.chunk_results:
            if not chunk.matched:
                all_diffs.extend(chunk.diff_samples)

        diff_types = {d.primary_key: d.diff_type for d in all_diffs}
        assert 250 in diff_types, "Failed to catch modified order 250"
        assert diff_types[250] == "MODIFIED"

        assert 599 in diff_types, "Failed to catch missing order 599"
        assert diff_types[599] == "MISSING_IN_TARGET"

        assert 999 in diff_types, "Failed to catch extra order 999"
        assert diff_types[999] == "EXTRA_IN_TARGET"

        # Check modified field detection
        diff_250 = next(d for d in all_diffs if d.primary_key == 250)
        assert "amount" in diff_250.differing_fields

    finally:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
        conn.close()
