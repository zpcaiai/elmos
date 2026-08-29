"""Unit tests for database migrations, table counts, and SQLite emulation."""

from __future__ import annotations

import unittest

from elmos_foundry.database import DatabaseManager


class DatabaseMigrationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager()

    def test_postgres_schema_has_25_tables(self) -> None:
        validation = self.db.validate_schema_structure()
        self.assertTrue(validation["valid"], f"Validation failed: missing tables {validation['missing_tables']}")
        self.assertEqual(validation["table_count"], 25)

    def test_sqlite_in_memory_emulation(self) -> None:
        conn = self.db.create_in_memory_sqlite_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        self.assertIn("knowledge_source", tables)
        self.assertIn("skill", tables)
        self.assertIn("dataset_item", tables)
        self.assertIn("model_artifact", tables)
        self.assertIn("audit_event", tables)
        conn.close()


if __name__ == "__main__":
    unittest.main()
