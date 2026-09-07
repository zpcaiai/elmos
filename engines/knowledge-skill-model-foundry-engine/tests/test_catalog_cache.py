"""Catalog reuse must retain live byte-identity and immutable-state checks."""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import elmos_foundry.skills as skills


class CatalogCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = skills.load_compiled_catalog()

    def test_repeated_load_reuses_validated_immutable_graph(self) -> None:
        first = skills.load_compiled_catalog()
        with mock.patch.object(
            skills, "_verify_archive_sources", wraps=skills._verify_archive_sources
        ) as verify:
            second = skills.load_compiled_catalog()
        self.assertIs(first, second)
        verify.assert_not_called()
        with self.assertRaises(TypeError):
            second.atomic_skills["typed-skill-contract"]["version"] = "forged"

    def test_cache_hit_still_rejects_missing_corrupt_or_symlinked_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.zip"
            with mock.patch.object(skills, "SOURCE_ARCHIVE_PATH", path):
                with self.assertRaisesRegex(skills.CatalogValidationError, "unavailable"):
                    skills.load_compiled_catalog()
                path.write_bytes(b"corrupt")
                with self.assertRaisesRegex(skills.CatalogValidationError, "byte size"):
                    skills.load_compiled_catalog()
                path.unlink()
                path.symlink_to(__file__)
                with self.assertRaisesRegex(skills.CatalogValidationError, "symlink"):
                    skills.load_compiled_catalog()

    def test_cache_hit_hashes_archive_content_not_only_length(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.zip"
            content = bytearray(skills.SOURCE_ARCHIVE_PATH.read_bytes())
            content[-1] ^= 1
            path.write_bytes(content)
            with mock.patch.object(skills, "SOURCE_ARCHIVE_PATH", path):
                with self.assertRaisesRegex(skills.CatalogValidationError, "SHA-256"):
                    skills.load_compiled_catalog()

    def test_changed_catalog_never_reuses_prior_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_bytes(skills.DEFAULT_CATALOG_PATH.read_bytes() + b" ")
            with self.assertRaisesRegex(skills.CatalogValidationError, "SHA-256"):
                skills.load_compiled_catalog(path)

    def test_control_character_validation_preserves_unicode(self) -> None:
        for character in [chr(value) for value in range(32)] + [chr(127)]:
            with (
                self.subTest(character=ord(character)),
                self.assertRaises(skills.CatalogValidationError),
            ):
                skills._string("left" + character + "right", "name")
        self.assertEqual(skills._string("中文é😀", "name"), "中文é😀")


if __name__ == "__main__":
    unittest.main()
