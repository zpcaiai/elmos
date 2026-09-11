"""Real physical PostgreSQL 16 Logical Replication CDC Integration Test.

Validates:
1. Native PostgreSQL logical decoding slot creation with test_decoding
2. Live transaction WAL capture of INSERT, UPDATE, and DELETE operations
3. Parsing into canonical CdcEvent objects
4. Incremental stream replay and anomaly check via EventComparator
"""

import pytest
import psycopg2
from elmos_sql_dialect.cdc import (
    CdcOpType,
    EventComparator,
    PostgresLogicalReplicationCdc,
)


def is_pg_available() -> bool:
    try:
        conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not is_pg_available(), reason="PostgreSQL 16 not running locally")
def test_real_postgres_logical_cdc_capture():
    conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
    conn.autocommit = True
    slot_name = "elmos_pytest_cdc_slot"

    cdc = PostgresLogicalReplicationCdc(connection=conn, slot_name=slot_name)
    cdc.drop_slot_if_exists()

    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS elmos_cdc_test;")
        cur.execute("DROP TABLE IF EXISTS elmos_cdc_test.products CASCADE;")
        cur.execute("""
            CREATE TABLE elmos_cdc_test.products (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(50) NOT NULL,
                stock INT NOT NULL,
                price NUMERIC(10, 2) NOT NULL
            );
        """)

    try:
        cdc.create_slot_if_not_exists()

        # Step A: Perform transactional INSERTs
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO elmos_cdc_test.products (sku, stock, price)
                VALUES ('SKU-001', 100, 19.99),
                       ('SKU-002', 50, 49.50);
            """)

        # Step B: Perform transactional UPDATE
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE elmos_cdc_test.products
                SET stock = 90, price = 21.00
                WHERE sku = 'SKU-001';
            """)

        # Step C: Perform transactional DELETE
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM elmos_cdc_test.products
                WHERE sku = 'SKU-002';
            """)

        # Fetch WAL changes via pg_logical_slot_get_changes
        events = cdc.fetch_changes(up_to_n_changes=100)

        # Filter events for elmos_cdc_test.products
        product_events = [e for e in events if e.table == "products"]

        assert len(product_events) >= 4, f"Expected at least 4 product events, got {len(product_events)}"

        ops = [e.op for e in product_events]
        assert CdcOpType.INSERT in ops, "Missing INSERT event"
        assert CdcOpType.UPDATE in ops, "Missing UPDATE event"
        assert CdcOpType.DELETE in ops, "Missing DELETE event"

        # Check payload of first INSERT
        insert_events = [e for e in product_events if e.op == CdcOpType.INSERT]
        assert len(insert_events) == 2
        assert insert_events[0].after is not None
        assert insert_events[0].after["sku"] == "SKU-001"
        assert int(insert_events[0].after["stock"]) == 100

        # Query the real final state from PostgreSQL
        with conn.cursor() as cur:
            cur.execute("SELECT id, sku, stock, price FROM elmos_cdc_test.products ORDER BY id;")
            db_rows = cur.fetchall()
            final_target_state = [
                {"id": str(r[0]), "sku": r[1], "stock": str(r[2]), "price": str(r[3])}
                for r in db_rows
            ]

        # Feed the real captured events into EventComparator
        comparator = EventComparator(pk_col="id")
        # Replay events on initial state (empty) and compare against target state
        report = comparator.replay_and_verify(
            initial_state=[],
            events=product_events,
            final_target_state=final_target_state,
            table_name="products",
        )
        assert report.total_events == len(product_events)
        assert report.inserts == 2
        assert report.updates == 1
        assert report.deletes == 1
        assert report.out_of_order_count == 0
        assert report.duplicate_count == 0
        assert report.state_consistent is True
        assert report.status == "CONSISTENT"

    finally:
        cdc.drop_slot_if_exists()
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS elmos_cdc_test CASCADE;")
        conn.close()
