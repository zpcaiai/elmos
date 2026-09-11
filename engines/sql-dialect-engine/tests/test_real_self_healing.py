"""Real physical PostgreSQL 16 Closed-Loop Self-Healing Test.

Validates:
1. Feeding non-native / foreign dialect SQL (MySQL backticks, AUTO_INCREMENT, Oracle VARCHAR2, unquoted keywords)
2. Live PostgreSQL runtime error interception (SQLSTATE 42601 syntax errors)
3. Multi-round AST & lexical self-healing inside savepoint sandbox
4. Successful final execution and real table creation
"""

import pytest
import psycopg2
from elmos_sql_dialect.self_healing_engine import ClosedLoopSelfHealingEngine


def is_pg_available() -> bool:
    try:
        conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not is_pg_available(), reason="PostgreSQL 16 not running locally")
def test_real_closed_loop_self_healing():
    conn = psycopg2.connect(dbname="postgres", user="stephen", host="localhost", port=5432)
    conn.autocommit = True
    schema_name = "elmos_heal_test"

    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name};")
        cur.execute(f"DROP TABLE IF EXISTS {schema_name}.inventory CASCADE;")
        cur.execute(f"DROP TABLE IF EXISTS {schema_name}.invoices CASCADE;")

    try:
        engine = ClosedLoopSelfHealingEngine(connection=conn, target_dialect="postgresql")

        # Test Case 1: MySQL DDL with backticks, AUTO_INCREMENT, and Oracle VARCHAR2
        bad_ddl = f"CREATE TABLE {schema_name}.`inventory` (`item_id` INT AUTO_INCREMENT PRIMARY KEY, `description` VARCHAR2(120));"

        report1 = engine.execute_with_self_healing(bad_ddl, schema=schema_name)

        assert report1.success is True, f"Failed to heal bad_ddl: {report1.error}"
        assert report1.iterations_count >= 1
        assert "REPLACED_BACKTICKS_WITH_DOUBLE_QUOTES" in report1.repairs_summary
        assert "REWRITTEN_AUTO_INCREMENT_TO_SERIAL" in report1.repairs_summary
        assert "REWRITTEN_VARCHAR2_TO_VARCHAR" in report1.repairs_summary

        # Verify table physically exists in PostgreSQL
        with conn.cursor() as cur:
            cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = '{schema_name}' AND table_name = 'inventory';")
            cols = {r[0]: r[1] for r in cur.fetchall()}
            assert "item_id" in cols
            assert "description" in cols
            assert cols["description"] == "character varying"

        # Test Case 2: Unquoted PostgreSQL reserved keyword columns (order, user)
        bad_keywords_ddl = f"CREATE TABLE {schema_name}.invoices (id SERIAL PRIMARY KEY, order INT, user VARCHAR(50));"

        report2 = engine.execute_with_self_healing(bad_keywords_ddl, schema=schema_name)

        assert report2.success is True, f"Failed to heal reserved keywords: {report2.error}"
        assert any("QUOTED_RESERVED_KEYWORD" in r for r in report2.repairs_summary)

        # Verify invoices table physically exists
        with conn.cursor() as cur:
            cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_schema = '{schema_name}' AND table_name = 'invoices';")
            cols = [r[0] for r in cur.fetchall()]
            assert "order" in cols
            assert "user" in cols

    finally:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
        conn.close()
