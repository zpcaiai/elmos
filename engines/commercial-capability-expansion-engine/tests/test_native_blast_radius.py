"""Test native blast radius bridge."""

from __future__ import annotations

import unittest
from elmos_commercial_expansion.native_blast_radius_bridge import fast_blast_radius


class NativeBlastRadiusTest(unittest.TestCase):
    def test_blast_radius_propagation(self) -> None:
        changed = ["module_a"]
        edges = [
            {"source": "module_a", "target": "module_b"},
            {"source": "module_b", "target": "module_c"},
            {"source": "module_c", "target": "module_d"},
        ]
        res = fast_blast_radius(changed, edges)
        self.assertIsNotNone(res)
        self.assertEqual(res, ["module_a", "module_b", "module_c", "module_d"])

    def test_cyclic_graph(self) -> None:
        changed = ["A"]
        edges = [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
            {"source": "C", "target": "A"},
        ]
        res = fast_blast_radius(changed, edges)
        self.assertIsNotNone(res)
        self.assertEqual(res, ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
