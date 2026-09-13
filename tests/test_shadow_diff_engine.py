import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = ROOT / "engines/legacy-web-modernization-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_legacy_web_modernization.shadow_diff_engine import (
    HttpExchange,
    ShadowDiffEngine,
    TableSnapshot,
)


class TestShadowDiffEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ShadowDiffEngine()

    def test_identical_exchanges_pass(self):
        legacy = HttpExchange(
            method="GET",
            path="/api/hello",
            status_code=200,
            headers={"Content-Type": "application/json", "Date": "Wed, 09 Sep 2026 08:00:00 GMT"},
            body='{"status":"ok","msg":"hello"}',
            latency_ms=10.0,
        )
        target = HttpExchange(
            method="GET",
            path="/api/hello",
            status_code=200,
            headers={"Content-Type": "application/json", "Date": "Wed, 09 Sep 2026 08:00:05 GMT"},
            body='{"status":"ok","msg":"hello"}',
            latency_ms=12.0,
        )
        res = self.engine.compare_exchanges(legacy, target)
        self.assertTrue(res.equivalent)
        self.assertEqual("PASS", res.verdict)
        self.assertFalse(res.critical_regression)

    def test_volatile_timestamp_normalized_passes(self):
        legacy = HttpExchange(
            method="GET",
            path="/api/time",
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"timestamp":"2026-09-09T08:00:00Z","user":"admin"}',
        )
        target = HttpExchange(
            method="GET",
            path="/api/time",
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"timestamp":"2026-09-09T08:05:00Z","user":"admin"}',
        )
        res = self.engine.compare_exchanges(legacy, target)
        self.assertTrue(res.equivalent)
        self.assertEqual("PASS", res.verdict)

    def test_status_code_mismatch_fails_with_critical_regression(self):
        legacy = HttpExchange(
            method="POST",
            path="/api/pay",
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"paid":true}',
        )
        target = HttpExchange(
            method="POST",
            path="/api/pay",
            status_code=500,
            headers={"Content-Type": "application/json"},
            body='{"error":"Internal Server Error"}',
        )
        res = self.engine.compare_exchanges(legacy, target)
        self.assertFalse(res.equivalent)
        self.assertEqual("FAIL", res.verdict)
        self.assertTrue(res.critical_regression)
        self.assertIn("Status code mismatch: 200 vs 500", res.mismatches)

    def test_database_row_checksum_reconciliation(self):
        rows1 = [{"id": 1, "name": "itemA"}, {"id": 2, "name": "itemB"}]
        rows2 = [{"id": 2, "name": "itemB"}, {"id": 1, "name": "itemA"}]  # different order, same content
        rows3 = [{"id": 1, "name": "itemA"}, {"id": 2, "name": "itemModified"}]

        snap1 = TableSnapshot.from_rows("orders", rows1)
        snap2 = TableSnapshot.from_rows("orders", rows2)
        snap3 = TableSnapshot.from_rows("orders", rows3)

        self.assertEqual(snap1.row_checksums, snap2.row_checksums)
        self.assertNotEqual(snap1.row_checksums, snap3.row_checksums)

        req = HttpExchange("POST", "/api/order", 200, {}, '{"ok":true}')
        res_matched = self.engine.compare_exchanges(req, req, legacy_db=snap1, target_db=snap2)
        self.assertTrue(res_matched.equivalent)
        self.assertEqual(1, len(res_matched.database_diffs))
        self.assertTrue(res_matched.database_diffs[0].matched)

        res_diff = self.engine.compare_exchanges(req, req, legacy_db=snap1, target_db=snap3)
        self.assertFalse(res_diff.equivalent)
        self.assertTrue(res_diff.critical_regression)
        self.assertEqual(0.0, res_diff.dimension_scores["database"])


if __name__ == "__main__":
    unittest.main()
