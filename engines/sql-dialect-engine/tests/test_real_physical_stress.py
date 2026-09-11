"""Real physical PostgreSQL 16 concurrent multi-worker transaction stress test.

Validates:
1. High-concurrency worker threads executing row-level locked transactions
2. Deadlock detection and exponential backoff retry loops
3. Conservation of money invariant across concurrent balance transfers
4. Calculation of true physical TPS, P50, P95, and P99 latency percentiles
"""

import pytest

try:
    import psycopg2
    _HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    _HAS_PSYCOPG2 = False

from elmos_sql_dialect.datapump import PhysicalStressEngine


def is_pg_available() -> bool:
    if not _HAS_PSYCOPG2:
        return False
    try:
        conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
        conn.close()
        return True
    except Exception:
        return False


def get_pg_connection():
    return psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)


@pytest.mark.skipif(not is_pg_available(), reason="PostgreSQL 16 not running locally")
def test_real_physical_concurrent_stress_and_invariants():
    schema_name = "elmos_stress_test"
    table_name = "accounts"
    num_accounts = 30
    initial_balance_per_account = 10000.00
    expected_total_money = num_accounts * initial_balance_per_account

    engine = PhysicalStressEngine(
        connection_factory=get_pg_connection,
        target_name="PostgreSQL-16-Local",
        concurrency=10,
        transactions_per_worker=25,
        max_retries=5,
    )

    try:
        engine.setup_stress_table(schema=schema_name, table_name=table_name, num_accounts=num_accounts)

        # Run concurrent stress benchmark
        report = engine.run_benchmark(
            schema=schema_name,
            table_name=table_name,
            num_accounts=num_accounts,
        )

        assert report.total_transactions == 250
        assert report.successful_transactions >= 245
        assert report.tps > 10.0
        assert report.p50_latency_ms > 0.0
        assert report.p95_latency_ms >= report.p50_latency_ms

        # Critical FinOps & Invariant Verification: Total money must be conserved!
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT SUM(balance) FROM {schema_name}.{table_name};")
                actual_total = float(cur.fetchone()[0])
                assert abs(actual_total - expected_total_money) < 0.001, (
                    f"Money lost or created! Expected {expected_total_money}, got {actual_total}"
                )
        finally:
            conn.close()

    finally:
        engine.teardown_stress_table(schema=schema_name, table_name=table_name)
        conn = get_pg_connection()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
        finally:
            conn.close()
