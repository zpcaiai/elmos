"""Physical Multi-Database SQL Translation Roundtrip & Execution Test.

Strictly adheres to the Execution Integrity Contract:
- Connects directly to live physical database instances:
  1. PostgreSQL 16.15 on 127.0.0.1:5432
  2. openGauss 3.0.0 (Enterprise) on 127.0.0.1:54321
  3. MySQL 8.0.46 on 127.0.0.1:33306
- Translates Oracle/Postgres/MySQL queries and UPSERTs across dialects.
- Physically executes the translated SQL on each live engine.
- Validates query results and data mutations for 100% semantic equivalence.
"""

from __future__ import annotations

import decimal
from typing import Any

import pytest

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    _HAS_PSYCOPG2 = False

try:
    import pymysql
    _HAS_PYMYSQL = True
except ImportError:
    pymysql = None
    _HAS_PYMYSQL = False

from elmos_sql_dialect.engine import translate_query, translate_sql, translate_upsert


def is_postgres_live() -> bool:
    if not _HAS_PSYCOPG2:
        return False
    try:
        conn = psycopg2.connect(dbname="postgres", user="stephen", host="127.0.0.1", port=5432, connect_timeout=6)
        conn.close()
        return True
    except Exception:
        return False


def is_opengauss_live() -> bool:
    if not _HAS_PSYCOPG2:
        return False
    try:
        conn = psycopg2.connect(
            dbname="omm", user="gaussdb", password="Enmotech@123", host="127.0.0.1", port=54321, connect_timeout=6
        )
        conn.close()
        return True
    except Exception:
        return False


def is_mysql_live() -> bool:
    if not _HAS_PYMYSQL:
        return False
    try:
        conn = pymysql.connect(
            host="127.0.0.1",
            port=33306,
            user="cdc_user",
            password="cdc_password",
            database="source_db",
            connect_timeout=6,
        )
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not (is_postgres_live() and is_opengauss_live() and is_mysql_live()),
    reason="All 3 physical databases (PostgreSQL, openGauss, MySQL) must be live",
)
class TestPhysicalSqlExecutionRoundtrip:
    @classmethod
    def setup_class(cls) -> None:
        """Setup identical test tables on all 3 physical databases."""
        cls.pg_conn = psycopg2.connect(dbname="postgres", user="stephen", host="127.0.0.1", port=5432)
        cls.pg_conn.autocommit = True

        cls.og_conn = psycopg2.connect(
            dbname="omm", user="gaussdb", password="Enmotech@123", host="127.0.0.1", port=54321
        )
        cls.og_conn.autocommit = True

        cls.my_conn = pymysql.connect(
            host="127.0.0.1",
            port=33306,
            user="cdc_user",
            password="cdc_password",
            database="source_db",
            autocommit=True,
        )

        with cls.pg_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS test_roundtrip_orders CASCADE;")
            cur.execute("DROP TABLE IF EXISTS test_roundtrip_customers CASCADE;")
            cur.execute("CREATE TABLE test_roundtrip_customers (id INT PRIMARY KEY, name VARCHAR(50), status INT);")
            cur.execute("CREATE TABLE test_roundtrip_orders (order_id INT PRIMARY KEY, cust_id INT, amount NUMERIC(10,2));")
            cur.execute("INSERT INTO test_roundtrip_customers VALUES (1, 'Alice', 1), (2, 'Bob', 2), (3, 'Charlie', 0);")
            cur.execute("INSERT INTO test_roundtrip_orders VALUES (101, 1, 150.00), (102, 1, 250.50), (103, 2, 80.00);")

        with cls.og_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS test_roundtrip_orders CASCADE;")
            cur.execute("DROP TABLE IF EXISTS test_roundtrip_customers CASCADE;")
            cur.execute("CREATE TABLE test_roundtrip_customers (id INT PRIMARY KEY, name VARCHAR(50), status INT);")
            cur.execute("CREATE TABLE test_roundtrip_orders (order_id INT PRIMARY KEY, cust_id INT, amount NUMERIC(10,2));")
            cur.execute("INSERT INTO test_roundtrip_customers VALUES (1, 'Alice', 1), (2, 'Bob', 2), (3, 'Charlie', 0);")
            cur.execute("INSERT INTO test_roundtrip_orders VALUES (101, 1, 150.00), (102, 1, 250.50), (103, 2, 80.00);")

        with cls.my_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS test_roundtrip_orders;")
            cur.execute("DROP TABLE IF EXISTS test_roundtrip_customers;")
            cur.execute("CREATE TABLE test_roundtrip_customers (id INT PRIMARY KEY, name VARCHAR(50), status INT);")
            cur.execute("CREATE TABLE test_roundtrip_orders (order_id INT PRIMARY KEY, cust_id INT, amount DECIMAL(10,2));")
            cur.execute("INSERT INTO test_roundtrip_customers VALUES (1, 'Alice', 1), (2, 'Bob', 2), (3, 'Charlie', 0);")
            cur.execute("INSERT INTO test_roundtrip_orders VALUES (101, 1, 150.00), (102, 1, 250.50), (103, 2, 80.00);")

    @classmethod
    def teardown_class(cls) -> None:
        try:
            with cls.pg_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS test_roundtrip_orders CASCADE;")
                cur.execute("DROP TABLE IF EXISTS test_roundtrip_customers CASCADE;")
            cls.pg_conn.close()
        except Exception:
            pass

        try:
            with cls.og_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS test_roundtrip_orders CASCADE;")
                cur.execute("DROP TABLE IF EXISTS test_roundtrip_customers CASCADE;")
            cls.og_conn.close()
        except Exception:
            pass

        try:
            with cls.my_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS test_roundtrip_orders;")
                cur.execute("DROP TABLE IF EXISTS test_roundtrip_customers;")
            cls.my_conn.close()
        except Exception:
            pass

    def test_cross_db_query_execution_and_result_equivalence(self) -> None:
        """Translates Oracle query with (+) outer join, NVL, DECODE, and ROWNUM pagination

        and verifies execution equivalence across physical PostgreSQL, openGauss, and MySQL.
        """
        oracle_query = (
            "SELECT c.id, c.name, "
            "DECODE(c.status, 1, 'VIP', 2, 'NORMAL', 'OTHER') AS tier, "
            "NVL(o.amount, 0.00) AS order_amt "
            "FROM test_roundtrip_customers c, test_roundtrip_orders o "
            "WHERE c.id = o.cust_id(+) AND ROWNUM <= 10 "
            "ORDER BY c.id, o.order_id"
        )

        # 1. Translate to PostgreSQL
        pg_res = translate_query(oracle_query, "oracle", "postgres")
        assert pg_res["status"] == "PASSED"
        pg_sql = pg_res["emitted"]

        with self.pg_conn.cursor() as cur:
            cur.execute(pg_sql)
            pg_rows = cur.fetchall()

        # 2. Translate to openGauss
        og_res = translate_query(oracle_query, "oracle", "opengauss")
        assert og_res["status"] == "PASSED"
        og_sql = og_res["emitted"]

        with self.og_conn.cursor() as cur:
            cur.execute(og_sql)
            og_rows = cur.fetchall()

        # 3. Translate to MySQL
        my_res = translate_query(oracle_query, "oracle", "mysql")
        assert my_res["status"] == "PASSED"
        my_sql = my_res["emitted"]

        with self.my_conn.cursor() as cur:
            cur.execute(my_sql)
            my_rows = cur.fetchall()

        # Assert all 3 physical engines returned 4 rows (Alice x 2, Bob x 1, Charlie x 1 [NULL amount -> 0.00])
        assert len(pg_rows) == 4
        assert len(og_rows) == 4
        assert len(my_rows) == 4

        # Compare row content between PostgreSQL and openGauss
        for pg_row, og_row in zip(pg_rows, og_rows, strict=False):
            assert pg_row[0] == og_row[0]  # id
            assert pg_row[1] == og_row[1]  # name
            assert pg_row[2] == og_row[2]  # tier ('VIP', 'NORMAL', 'OTHER')
            assert float(pg_row[3]) == float(og_row[3])  # order_amt (with 0.00 for Charlie)

        # Compare row content with MySQL
        for pg_row, my_row in zip(pg_rows, my_rows, strict=False):
            assert pg_row[0] == my_row[0]
            assert pg_row[1] == my_row[1]
            assert pg_row[2] == my_row[2]
            assert float(pg_row[3]) == float(my_row[3])

    def test_cross_db_upsert_execution_and_state_equivalence(self) -> None:
        """Translates UPSERT across PostgreSQL ON CONFLICT, MySQL ON DUPLICATE KEY,

        and openGauss, physically executing inserts and updates on each live database.
        """
        # Step 1: Initial Insert via UPSERT
        base_upsert = (
            "INSERT INTO test_roundtrip_customers (id, name, status) VALUES (4, 'Diana', 1) "
            "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status;"
        )

        pg_res = translate_upsert(base_upsert, "postgres", "postgres")
        og_res = translate_upsert(base_upsert, "postgres", "opengauss")
        my_res = translate_upsert(base_upsert, "postgres", "mysql")

        with self.pg_conn.cursor() as cur:
            cur.execute(pg_res["emitted"])
            cur.execute("SELECT name, status FROM test_roundtrip_customers WHERE id = 4;")
            pg_row = cur.fetchone()
            assert pg_row == ("Diana", 1)

        with self.og_conn.cursor() as cur:
            cur.execute(og_res["emitted"])
            cur.execute("SELECT name, status FROM test_roundtrip_customers WHERE id = 4;")
            og_row = cur.fetchone()
            assert og_row == ("Diana", 1)

        with self.my_conn.cursor() as cur:
            cur.execute(my_res["emitted"])
            cur.execute("SELECT name, status FROM test_roundtrip_customers WHERE id = 4;")
            my_row = cur.fetchone()
            assert my_row == ("Diana", 1)

        # Step 2: Conflict Update via UPSERT (change Diana's status to 2 and name to 'Diana Prince')
        update_upsert = (
            "INSERT INTO test_roundtrip_customers (id, name, status) VALUES (4, 'Diana Prince', 2) "
            "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status;"
        )

        pg_up = translate_upsert(update_upsert, "postgres", "postgres")
        og_up = translate_upsert(update_upsert, "postgres", "opengauss")
        my_up = translate_upsert(update_upsert, "postgres", "mysql")

        with self.pg_conn.cursor() as cur:
            cur.execute(pg_up["emitted"])
            cur.execute("SELECT name, status FROM test_roundtrip_customers WHERE id = 4;")
            assert cur.fetchone() == ("Diana Prince", 2)

        with self.og_conn.cursor() as cur:
            cur.execute(og_up["emitted"])
            cur.execute("SELECT name, status FROM test_roundtrip_customers WHERE id = 4;")
            assert cur.fetchone() == ("Diana Prince", 2)

        with self.my_conn.cursor() as cur:
            cur.execute(my_up["emitted"])
            cur.execute("SELECT name, status FROM test_roundtrip_customers WHERE id = 4;")
            assert cur.fetchone() == ("Diana Prince", 2)
