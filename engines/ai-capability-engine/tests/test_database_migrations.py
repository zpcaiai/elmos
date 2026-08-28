"""Tests for PostgreSQL database migrations."""

from __future__ import annotations

import unittest
from elmos_ai_capability.database import MigrationManager


class DatabaseMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manager = MigrationManager()

    def test_20_migrations_present(self) -> None:
        migs = self.manager.list_migrations()
        self.assertEqual(len(migs), 20)
        self.assertIn("001_ai_solution_core.sql", migs)
        self.assertIn("024_database_security_routines.sql", migs)

    def test_validate_migration_001(self) -> None:
        res = self.manager.validate_migration("001_ai_solution_core.sql")
        self.assertEqual(res.status, "VALIDATED")
        self.assertGreater(res.statement_count, 0)
        self.assertGreater(len(res.tables_created), 0)

    def test_validate_all_migrations(self) -> None:
        results = self.manager.validate_all_migrations()
        self.assertEqual(len(results), 20)
        for name, res in results.items():
            self.assertEqual(res.status, "VALIDATED", f"Migration {name} failed validation")


if __name__ == "__main__":
    unittest.main()
