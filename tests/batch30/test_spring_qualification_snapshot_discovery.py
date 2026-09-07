import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/batch30/run_spring_boot_reference.py"
SPEC = importlib.util.spec_from_file_location("spring_boot_reference", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REFERENCE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REFERENCE
SPEC.loader.exec_module(REFERENCE)


class SpringQualificationSnapshotDiscoveryTests(unittest.TestCase):
    def snapshot(self, path: Path, **overrides: object) -> None:
        record = {
            "pack_key": REFERENCE.PACK_KEY,
            "evidence_class": "LOCAL_QUALIFICATION_SNAPSHOT",
            "certification_eligible": False,
            "certification_decision": "NOT_CERTIFIED",
        }
        record.update(overrides)
        path.write_text(json.dumps(record), encoding="utf-8")

    def test_preserves_every_governed_historical_snapshot_in_sorted_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.snapshot(root / "local-product-surface-qualification-z.json")
            self.snapshot(root / "local-product-surface-qualification-a.json")
            (root / "unrelated.json").write_text("{}", encoding="utf-8")
            self.assertEqual(
                REFERENCE.governed_qualification_snapshots(root),
                [
                    "local-product-surface-qualification-a.json",
                    "local-product-surface-qualification-z.json",
                ],
            )

    def test_rejects_a_snapshot_that_claims_certification_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.snapshot(
                root / "local-product-surface-qualification-unsafe.json",
                certification_eligible=True,
            )
            with self.assertRaisesRegex(
                ValueError, "UNSAFE_LOCAL_QUALIFICATION_SNAPSHOT"
            ):
                REFERENCE.governed_qualification_snapshots(root)


if __name__ == "__main__":
    unittest.main()
