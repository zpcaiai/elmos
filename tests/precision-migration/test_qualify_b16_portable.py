from __future__ import annotations

import unittest
from unittest import mock

from scripts.precision_migration import qualify_b16


class QualifyB16PortableTest(unittest.TestCase):
    def test_evidence_only_rebuild_never_executes_a_native_route_gate(self) -> None:
        with mock.patch.object(
            qualify_b16.subprocess,
            "run",
            side_effect=AssertionError("native route gate must remain NOT_RUN"),
        ):
            result = qualify_b16.build(execute_gates=False)

        self.assertEqual(30, result["skill_count"])
        self.assertEqual(150, result["result_count"])
        self.assertEqual("NOT_RUN", result["independent_verification"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])


if __name__ == "__main__":
    unittest.main()
