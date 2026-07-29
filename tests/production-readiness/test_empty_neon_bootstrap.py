from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "commercial" / "bootstrap_empty_neon_via_psql.py"
SPEC = importlib.util.spec_from_file_location("empty_neon_bootstrap", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class EmptyNeonBootstrapTests(unittest.TestCase):
    def test_repository_migrations_are_contiguous_and_checksums_match_flyway(self) -> None:
        migrations = MODULE.discover_migrations()

        self.assertEqual(list(range(1, 52)), [item.version for item in migrations])
        self.assertEqual(-1305174584, migrations[0].checksum)
        self.assertEqual(410399635, migrations[1].checksum)
        self.assertEqual(1595351014, migrations[2].checksum)

    def test_bootstrap_contract_requires_explicit_empty_database_confirmation(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("ELMOS_COMMERCIAL_DATABASE_EMPTY_BOOTSTRAP_CONFIRMED", source)
        self.assertIn("TARGET_DATABASE_NOT_EMPTY", source)
        self.assertIn("FLYWAY_HISTORY_RECONCILIATION_FAILED", source)
        self.assertIn("--single-transaction", source)

    def test_history_literals_are_escaped_without_psql_command_substitution(self) -> None:
        self.assertEqual("'owner''s migration'", MODULE.sql_literal("owner's migration"))
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn(":'migration_version'", source)


if __name__ == "__main__":
    unittest.main()
