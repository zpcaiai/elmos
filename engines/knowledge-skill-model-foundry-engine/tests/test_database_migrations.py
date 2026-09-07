"""Database source inspection must never masquerade as runtime execution."""

from __future__ import annotations

import unittest

from elmos_foundry.database import DatabaseBoundaryError, DatabaseManager


class DatabaseMigrationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = DatabaseManager()

    def test_postgres_source_has_exact_bounded_structure(self) -> None:
        validation = self.database.validate_schema_structure()
        self.assertTrue(validation["structurally_valid"])
        self.assertEqual(validation["table_count"], 38)
        self.assertEqual(validation["source_status"], "UNTRUSTED_DECLARATIVE_INPUT")
        self.assertEqual(validation["execution_status"], "NOT_RUN")
        self.assertEqual(validation["certification_status"], "NOT_CERTIFIED")

    def test_untrusted_postgres_sql_is_never_regex_executed_in_sqlite(self) -> None:
        with self.assertRaises(DatabaseBoundaryError):
            self.database.create_in_memory_sqlite_db()


if __name__ == "__main__":
    unittest.main()
