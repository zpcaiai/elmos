from __future__ import annotations

import unittest

from elmos_ai_optimization.contracts import StaleVersionError
from elmos_ai_optimization.projection import ProjectionCatalog


class ProjectionCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ProjectionCatalog(":memory:")

    def tearDown(self) -> None:
        self.catalog.close()

    def test_lifecycle_and_atomic_cas_publish(self) -> None:
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", expected_count=10)
        self.assertIsNone(self.catalog.get_head("t1", "r1"))

        # Chunk count mismatch
        with self.assertRaises(StaleVersionError):
            self.catalog.validate("t1", "r1", "gen-1", actual_count=9)

        # Correct validation
        self.catalog.validate("t1", "r1", "gen-1", actual_count=10)

        # Publish initial head
        self.catalog.publish("t1", "r1", "gen-1", expected_head=None)
        self.assertEqual(self.catalog.get_head("t1", "r1"), "gen-1")

        # Second version lifecycle
        self.catalog.begin("t1", "r1", "gen-2", "snap-2", expected_count=15)
        self.catalog.validate("t1", "r1", "gen-2", actual_count=15)

        # Stale CAS head promotion
        with self.assertRaises(StaleVersionError):
            self.catalog.publish("t1", "r1", "gen-2", expected_head="gen-old")

        # Correct CAS head promotion
        self.catalog.publish("t1", "r1", "gen-2", expected_head="gen-1")
        self.assertEqual(self.catalog.get_head("t1", "r1"), "gen-2")


if __name__ == "__main__":
    unittest.main()
