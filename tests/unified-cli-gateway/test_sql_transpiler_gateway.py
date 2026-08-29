"""Tests for Enterprise SQL & ChinaDB Dialect Transpiler Gateway."""

import unittest
from elmos_sql_dialect.sql_transpiler_gateway import SqlTranspilerGateway, get_supported_dialects


class TestSqlTranspilerGateway(unittest.TestCase):
    def setUp(self):
        self.gw = SqlTranspilerGateway()

    def test_get_supported_dialects(self):
        d = get_supported_dialects()
        self.assertIsInstance(d, list)
        dialect_ids = [item["id"] for item in d]
        self.assertIn("oracle", dialect_ids)
        self.assertIn("dm8", dialect_ids)
        self.assertIn("tidb", dialect_ids)
        self.assertIn("kingbasees", dialect_ids)

    def test_oracle_to_postgres_transpilation(self):
        sql = "SELECT NVL(nickname, 'Anonymous'), SYSDATE FROM users WHERE ROWNUM <= 10"
        res = self.gw.transpile(sql, "oracle", "postgres")
        self.assertEqual(res.source_dialect, "oracle")
        self.assertEqual(res.target_dialect, "postgres")
        self.assertIn("COALESCE", res.target_sql)
        self.assertIn("CURRENT_TIMESTAMP", res.target_sql)
        self.assertIn("LIMIT 10", res.target_sql)
        self.assertEqual(res.semantic_equivalence, "VERIFIED_SEMANTIC_EQUIVALENCE")
        self.assertTrue(res.merkle_receipt.startswith("sha256:"))

    def test_oracle_to_dm8_transpilation(self):
        sql = "SELECT NVL(col1, 'N/A') FROM tbl WHERE ROWNUM <= 5"
        res = self.gw.transpile(sql, "oracle", "dm8")
        self.assertEqual(res.target_dialect, "dm8")
        self.assertIn("NVL", res.target_sql)  # DM8 retains Oracle compatibility

    def test_sqlserver_to_postgres_transpilation(self):
        sql = "SELECT TOP 10 ISNULL(col, 'DEFAULT'), GETDATE() FROM tbl"
        res = self.gw.transpile(sql, "sqlserver", "postgres")
        self.assertIn("COALESCE", res.target_sql)
        self.assertIn("CURRENT_TIMESTAMP", res.target_sql)
        self.assertIn("LIMIT 10", res.target_sql)

    def test_diff_schemas(self):
        ddl1 = "CREATE TABLE users (id INT, name VARCHAR(100));"
        ddl2 = "CREATE TABLE orders (id INT, name VARCHAR(100), tenant_id VARCHAR(64));"
        diff = self.gw.diff_schemas(ddl1, ddl2)
        self.assertEqual(diff["status"], "BREAKING_REMOVALS_DETECTED")
        self.assertIn("orders", diff["added_tables"])
        self.assertIn("users", diff["removed_tables"])


if __name__ == "__main__":
    unittest.main()
