"""Unit tests for PostgreSQL MigrationManager."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from elmos_proof_harness.migration_manager import (
    MigrationDriftError,
    MigrationManager,
    _parse_version_key,
)


class MigrationManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.migrations_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_version_key(self) -> None:
        self.assertEqual(_parse_version_key("001"), (1,))
        self.assertEqual(_parse_version_key("304"), (304,))
        self.assertEqual(_parse_version_key("3_2_0"), (3, 2, 0))

    def test_discover_migrations_sorting_and_checksum(self) -> None:
        # Create out-of-order migration files
        f2 = self.migrations_path / "V305__third.sql"
        f2.write_text("SELECT 3;", encoding="utf-8")

        f1 = self.migrations_path / "V001__first.sql"
        f1.write_text("SELECT 1;", encoding="utf-8")

        f3 = self.migrations_path / "V002__second.sql"
        f3.write_text("SELECT 2;", encoding="utf-8")

        manager = MigrationManager(dsn="postgresql://test", migrations_dir=self.migrations_path)
        discovered = manager.discover_migrations()

        self.assertEqual(len(discovered), 3)
        self.assertEqual(discovered[0].version, "001")
        self.assertEqual(discovered[0].description, "first")
        self.assertEqual(discovered[1].version, "002")
        self.assertEqual(discovered[1].description, "second")
        self.assertEqual(discovered[2].version, "305")
        self.assertEqual(discovered[2].description, "third")

        # Verify SHA-256
        expected_csum = hashlib.sha256(b"SELECT 1;").hexdigest()
        self.assertEqual(discovered[0].checksum, expected_csum)

    def test_real_repo_migrations_discovery(self) -> None:
        """Verify discovering real repository migrations."""
        manager = MigrationManager(dsn="postgresql://test")
        discovered = manager.discover_migrations()
        self.assertGreaterEqual(len(discovered), 3)
        versions = [m.version for m in discovered]
        self.assertIn("001", versions)
        self.assertIn("304", versions)
        self.assertIn("305", versions)

    @patch("elmos_proof_harness.migration_manager.MigrationManager._get_driver")
    def test_drift_detection_raises_error(self, mock_get_driver: MagicMock) -> None:
        f1 = self.migrations_path / "V001__first.sql"
        f1.write_text("SELECT 1_modified;", encoding="utf-8")

        manager = MigrationManager(dsn="postgresql://test", migrations_dir=self.migrations_path)

        # Mock DB connection and cursor
        mock_driver = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_driver.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_driver.return_value = mock_driver

        # Simulate DB having a different checksum for V001
        from datetime import datetime, UTC
        old_checksum = hashlib.sha256(b"SELECT 1_original;").hexdigest()
        mock_cursor.fetchall.return_value = [
            (1, "001", "first", "V001__first.sql", old_checksum, "user", datetime.now(UTC), 10, True)
        ]

        with self.assertRaises(MigrationDriftError) as ctx:
            manager.apply_pending()

        self.assertIn("checksum mismatch", str(ctx.exception))
