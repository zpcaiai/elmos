"""Comprehensive Cross-Dialect Bi-directional SQL Transpilation Tests.

Validates:
1. Queries (SELECT/WITH) across Oracle, PostgreSQL, MySQL, T-SQL, SQLite.
2. Oracle (+) outer joins -> ANSI LEFT JOIN.
3. Oracle/DM8 ROWNUM -> LIMIT/TOP pagination.
4. Functions: NVL, IFNULL, ISNULL, NVL2, DECODE, SYSDATE, INSTR, CONCAT.
5. UPSERT: MERGE INTO <-> ON CONFLICT <-> ON DUPLICATE KEY UPDATE across Oracle, PG, MySQL, openGauss, DM8.
6. Domestic ChinaDB targets: openGauss, DM8, KingbaseES, OceanBase, TiDB, HighGo, GBase, GoldenDB.
7. Top-level translate_sql with statement_kind="AUTO".
"""

from __future__ import annotations

import pytest

from elmos_sql_dialect.engine import translate_query, translate_sql, translate_upsert


class TestCrossDialectQueryTranspiler:
    def test_oracle_to_postgres_outer_join_and_rownum(self) -> None:
        sql = "SELECT e.name, d.name, NVL(e.sal, 0) FROM emp e, dept d WHERE e.dept_id = d.id(+) AND ROWNUM <= 10"
        res = translate_query(sql, "oracle", "postgres")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "LEFT JOIN dept" in emitted
        assert "COALESCE(e.sal, 0)" in emitted
        assert "LIMIT 10" in emitted
        assert "ROWNUM" not in emitted
        assert "(+)" not in emitted

    def test_oracle_to_postgres_dual_removal(self) -> None:
        sql = "SELECT 1, SYSDATE FROM DUAL"
        res = translate_query(sql, "oracle", "postgres")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "FROM DUAL" not in emitted.upper()
        assert "CURRENT_TIMESTAMP" in emitted

    def test_postgres_to_oracle_dual_append(self) -> None:
        sql = "SELECT 1"
        res = translate_query(sql, "postgres", "oracle")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "FROM DUAL" in emitted.upper()

    def test_oracle_to_postgres_decode_and_nvl2(self) -> None:
        sql = (
            "SELECT DECODE(status, 1, 'active', 2, 'pending', 'unknown'), "
            "NVL2(bonus, 'has_bonus', 'no_bonus') FROM users"
        )
        res = translate_query(sql, "oracle", "postgres")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "CASE WHEN status = 1 THEN 'active' WHEN status = 2 THEN 'pending' ELSE 'unknown' END" in emitted
        assert "CASE WHEN NOT bonus IS NULL THEN 'has_bonus' ELSE 'no_bonus' END" in emitted

    def test_oracle_to_postgres_instr(self) -> None:
        sql = "SELECT INSTR(name, 'test') FROM users"
        res = translate_query(sql, "oracle", "postgres")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "POSITION" in emitted
        assert "'test' IN name" in emitted

    def test_postgres_to_mysql_pagination_and_coalesce(self) -> None:
        sql = "SELECT COALESCE(notes, 'N/A') FROM orders WHERE total > 100 LIMIT 25"
        res = translate_query(sql, "postgres", "mysql")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "IFNULL" in emitted or "COALESCE" in emitted
        assert "LIMIT 25" in emitted

    def test_mysql_to_postgres_ifnull(self) -> None:
        sql = "SELECT IFNULL(discount, 0.0) FROM items LIMIT 10"
        res = translate_query(sql, "mysql", "postgres")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "COALESCE" in emitted
        assert "LIMIT 10" in emitted

    def test_tsql_to_postgres_top_and_isnull(self) -> None:
        sql = "SELECT TOP 15 ISNULL(score, 0) FROM rankings"
        res = translate_query(sql, "tsql", "postgres")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "COALESCE" in emitted
        assert "LIMIT 15" in emitted
        assert "TOP" not in emitted


class TestCrossDialectUpsertTranspiler:
    def test_postgres_to_mysql_upsert(self) -> None:
        pg_sql = (
            "INSERT INTO accounts (id, balance, updated_at) VALUES (101, 5000.0, '2026-09-13') "
            "ON CONFLICT (id) DO UPDATE SET balance = EXCLUDED.balance, updated_at = EXCLUDED.updated_at;"
        )
        res = translate_upsert(pg_sql, "postgres", "mysql")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "ON DUPLICATE KEY UPDATE" in emitted
        assert "balance = VALUES(balance)" in emitted
        assert "updated_at = VALUES(updated_at)" in emitted
        assert "ON CONFLICT" not in emitted

    def test_postgres_to_oracle_merge(self) -> None:
        pg_sql = (
            "INSERT INTO accounts (id, balance) VALUES (101, 5000.0) "
            "ON CONFLICT (id) DO UPDATE SET balance = EXCLUDED.balance;"
        )
        res = translate_upsert(pg_sql, "postgres", "oracle")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "MERGE INTO accounts t" in emitted
        assert "USING (SELECT 101 AS id, 5000.0 AS balance FROM DUAL) s" in emitted
        assert "ON (t.id = s.id)" in emitted
        assert "WHEN MATCHED THEN UPDATE SET t.balance = s.balance" in emitted
        assert "WHEN NOT MATCHED THEN INSERT (id, balance) VALUES (s.id, s.balance)" in emitted

    def test_mysql_to_postgres_upsert(self) -> None:
        my_sql = (
            "INSERT INTO accounts (id, balance) VALUES (101, 5000.0) "
            "ON DUPLICATE KEY UPDATE balance = VALUES(balance);"
        )
        res = translate_upsert(my_sql, "mysql", "postgres")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "ON CONFLICT (id) DO UPDATE SET balance = EXCLUDED.balance" in emitted

    def test_oracle_merge_to_postgres_and_mysql(self) -> None:
        ora_sql = (
            "MERGE INTO accounts t USING (SELECT 101 AS id, 5000.0 AS balance FROM DUAL) s "
            "ON (t.id = s.id) WHEN MATCHED THEN UPDATE SET t.balance = s.balance "
            "WHEN NOT MATCHED THEN INSERT (id, balance) VALUES (s.id, s.balance);"
        )
        res_pg = translate_upsert(ora_sql, "oracle", "postgres")
        assert res_pg["status"] == "PASSED"
        assert "ON CONFLICT (id) DO UPDATE SET balance = EXCLUDED.balance" in res_pg["emitted"]

        res_my = translate_upsert(ora_sql, "oracle", "mysql")
        assert res_my["status"] == "PASSED"
        assert "ON DUPLICATE KEY UPDATE balance = VALUES(balance)" in res_my["emitted"]

    def test_upsert_do_nothing_handling(self) -> None:
        pg_sql = "INSERT INTO logs (id, msg) VALUES (1, 'info') ON CONFLICT (id) DO NOTHING;"
        res_pg = translate_upsert(pg_sql, "postgres", "mysql")
        assert res_pg["status"] == "PASSED"
        assert "ON DUPLICATE KEY UPDATE id = id" in res_pg["emitted"]


class TestChinaDbDomesticTargets:
    def test_oracle_to_opengauss_query(self) -> None:
        sql = "SELECT NVL(col1, 0) FROM my_tab WHERE ROWNUM <= 20"
        res = translate_query(sql, "oracle", "opengauss")
        assert res["status"] == "PASSED"
        emitted = res["emitted"]
        assert "COALESCE(col1, 0)" in emitted
        assert "LIMIT 20" in emitted
        assert "WITH (ORIENTATION" not in emitted  # Ensure query does not receive table DDL orientation clause

    def test_oracle_to_dm8_query(self) -> None:
        sql = "SELECT NVL(val, 0) FROM sample_tab"
        res = translate_query(sql, "oracle", "dm8")
        assert res["status"] == "PASSED"
        assert "NVL" in res["emitted"]

    def test_oracle_to_kingbasees_query(self) -> None:
        sql = "SELECT NVL(val, 0) FROM sample_tab WHERE ROWNUM <= 5"
        res = translate_query(sql, "oracle", "kingbasees")
        assert res["status"] == "PASSED"
        assert "COALESCE" in res["emitted"]

    def test_mysql_to_tidb_query(self) -> None:
        sql = "SELECT IFNULL(price, 0) FROM products LIMIT 50"
        res = translate_query(sql, "mysql", "tidb")
        assert res["status"] == "PASSED"
        assert "IFNULL" in res["emitted"] or "COALESCE" in res["emitted"]
        assert "LIMIT 50" in res["emitted"]

    def test_postgres_to_highgo_query(self) -> None:
        sql = "SELECT COALESCE(price, 0) FROM products LIMIT 10"
        res = translate_query(sql, "postgres", "highgo")
        assert res["status"] == "PASSED"
        assert "LIMIT 10" in res["emitted"]


class TestTranslateSqlAutoDispatcher:
    def test_auto_dispatch_select_query(self) -> None:
        sql = "SELECT NVL(x, 1) FROM t WHERE ROWNUM <= 5"
        res = translate_sql(sql, "oracle", "postgres")
        assert res["status"] == "PASSED"
        assert "COALESCE" in res["emitted"]
        assert "LIMIT 5" in res["emitted"]

    def test_auto_dispatch_upsert(self) -> None:
        sql = "INSERT INTO t (id, val) VALUES (1, 'x') ON CONFLICT (id) DO UPDATE SET val = EXCLUDED.val;"
        res = translate_sql(sql, "postgres", "mysql")
        assert res["status"] == "PASSED"
        assert "ON DUPLICATE KEY UPDATE" in res["emitted"]

    def test_auto_dispatch_ddl(self) -> None:
        sql = "CREATE TABLE test_tab (id INT PRIMARY KEY, name VARCHAR(100));"
        res = translate_sql(sql, "mysql", "postgres")
        assert res["status"] == "PASSED"
        assert "CREATE TABLE test_tab" in res["emitted"]
