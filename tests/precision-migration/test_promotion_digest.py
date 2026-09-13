from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.precision_migration.promotion import (  # noqa: E402
    PROMOTION_METADATA,
    normalized_promoted_skill,
    promoted_skill_source_digest,
)


class PromotionDigestTests(unittest.TestCase):
    def test_exact_overlay_hashes_and_validates_as_unpromoted_source(self) -> None:
        name = "pm-example"
        source = b"---\nname: pm-example\ndescription: Exact fixture\n---\nBody\n"
        promoted = source.replace(
            b"name: pm-example\n",
            b"name: pm-example\n" + PROMOTION_METADATA,
        )
        with self.subTest("manifest digest"):
            with tempfile.TemporaryDirectory() as directory:
                skill_dir = Path(directory)
                path = skill_dir / "SKILL.md"
                path.write_bytes(promoted)
                self.assertEqual(
                    promoted_skill_source_digest(path.read_bytes(), name),
                    hashlib.sha256(source).hexdigest(),
                )
                self.assertEqual(normalized_promoted_skill(promoted, name), source)

    def test_missing_partial_or_duplicate_overlay_fails_closed(self) -> None:
        cases = (
            b"---\nname: pm-example\ndescription: Missing overlay\n---\nBody\n",
            b"---\nname: pm-example\nimplementation_state: \"VERIFIED\"\n---\nBody\n",
            (
                b"---\nname: pm-example\n"
                + PROMOTION_METADATA
                + PROMOTION_METADATA
                + b"description: Duplicate overlay\n---\nBody\n"
            ),
        )
        for content in cases:
            with self.subTest(content=content):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "SKILL.md"
                    path.write_bytes(content)
                    with self.assertRaisesRegex(
                        ValueError,
                        "installed Skill promotion metadata mismatch",
                    ):
                        promoted_skill_source_digest(path.read_bytes(), "pm-example")


if __name__ == "__main__":
    unittest.main()
