from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling"))

import validate_spring_golden_route_source_task_coverage as coverage  # noqa: E402


class SpringSourceTaskCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ledger = coverage.build_expected(ROOT)

    def test_pinned_archive_and_manifest_are_bound(self) -> None:
        self.assertEqual(coverage.EXPECTED_SKILLS, self.ledger["skill_count"])
        self.assertEqual(coverage.EXPECTED_TASKS, self.ledger["task_count"])
        self.assertEqual(
            f"sha256:{coverage.EXPECTED_ARCHIVE_SHA256}",
            self.ledger["source_archive_sha256"],
        )
        self.assertEqual(
            "sha256:e2689dfcd95b4cae38bd29b704da028c79703d247cc12e67e019a7da768d51aa",
            self.ledger["installed_manifest_sha256"],
        )
        self.assertEqual(
            "LOCAL_STATIC_SOURCE_AND_INSTALLED_MANIFEST_MATCH",
            self.ledger["evidence_boundary"]["inventory_evidence"],
        )

    def test_all_4368_tasks_have_stable_ids_and_exact_source_digests(self) -> None:
        tasks = self.ledger["tasks"]
        self.assertEqual(coverage.EXPECTED_TASKS, len(tasks))
        self.assertEqual(coverage.EXPECTED_TASKS, len({task["task_id"] for task in tasks}))
        self.assertEqual(list(range(1, coverage.EXPECTED_TASKS + 1)), [task["global_ordinal"] for task in tasks])
        for task in tasks:
            with self.subTest(task=task["task_id"]):
                self.assertRegex(task["task_id"], coverage.TASK_ID)
                self.assertEqual("unchecked", task["source_checkbox"])
                self.assertTrue(task["source_skill_sha256"].startswith("sha256:"))
                self.assertTrue(task["source_contract_sha256"].startswith("sha256:"))
                self.assertEqual(
                    "sha256:" + coverage._sha256_bytes(task["source_text"].encode("utf-8")),
                    task["source_task_line_sha256"],
                )
                self.assertEqual("NOT_RUN", task["task_status"])
                self.assertEqual("BLOCKED", task["execution_status"])
                self.assertEqual(
                    coverage.BLOCK_REASON,
                    task["block_reason"],
                )
                self.assertEqual("NOT_RUN", task["runtime_evidence_status"])
                self.assertEqual("NOT_RUN", task["customer_evidence_status"])
                self.assertEqual("NOT_RUN", task["external_evidence_status"])
                self.assertEqual("NOT_CERTIFIED", task["certification"])
                self.assertFalse(task["side_effects_authorized"])

    def test_skill_summaries_cover_source_order_without_generic_dispatch(self) -> None:
        skills = self.ledger["skills"]
        self.assertEqual(coverage.EXPECTED_SKILLS, len(skills))
        self.assertEqual(
            coverage.EXPECTED_TASKS,
            sum(skill["task_count"] for skill in skills),
        )
        self.assertEqual(
            {"foundation": coverage.EXPECTED_FOUNDATION_SKILLS, "commercial-extension": coverage.EXPECTED_COMMERCIAL_SKILLS},
            {
                origin: sum(1 for skill in skills if skill["source_origin"] == origin)
                for origin in ("foundation", "commercial-extension")
            },
        )
        self.assertNotIn("dispatcher", self.ledger)
        self.assertEqual("SOURCE_SPECIFICATION_ONLY_NO_AUTHORIZED_RUNTIME", self.ledger["block_reason"])
        for skill in skills:
            self.assertEqual(skill["task_count"], len(skill["task_ids"]))
            self.assertEqual({"NOT_RUN": skill["task_count"]}, skill["task_status_counts"])
            self.assertEqual({"BLOCKED": skill["task_count"]}, skill["execution_status_counts"])

    def test_checked_source_task_fails_closed(self) -> None:
        archive = coverage._read_archive(ROOT)
        source = coverage._source_manifest(archive)
        installed, _ = coverage._load_installed_manifest(ROOT)
        first_skill = source["skills"][0]
        source_path = first_skill["path"]
        mutated = dict(archive)
        mutated[source_path] = archive[source_path].replace(b"- [ ]", b"- [x]", 1)
        with self.assertRaises(coverage.InventoryError):
            coverage._task_records(source, mutated, installed)

    def test_archive_digest_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / coverage.ARCHIVE_RELATIVE).parent.mkdir(parents=True)
            shutil.copy2(ROOT / coverage.ARCHIVE_RELATIVE, root / coverage.ARCHIVE_RELATIVE)
            (root / coverage.MANIFEST_RELATIVE).parent.mkdir(parents=True)
            shutil.copy2(ROOT / coverage.MANIFEST_RELATIVE, root / coverage.MANIFEST_RELATIVE)

            # The archive digest is intentionally pinned; changing any source
            # task therefore fails before a fabricated ledger can pass.
            archive_path = root / coverage.ARCHIVE_RELATIVE
            archive_bytes = bytearray(archive_path.read_bytes())
            archive_bytes[-1] ^= 1
            archive_path.write_bytes(archive_bytes)
            with self.assertRaises(coverage.InventoryError):
                coverage.build_expected(root)

    def test_installed_manifest_source_digest_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / coverage.ARCHIVE_RELATIVE).parent.mkdir(parents=True)
            shutil.copy2(ROOT / coverage.ARCHIVE_RELATIVE, root / coverage.ARCHIVE_RELATIVE)
            manifest_path = root / coverage.MANIFEST_RELATIVE
            manifest_path.parent.mkdir(parents=True)
            manifest = json.loads((ROOT / coverage.MANIFEST_RELATIVE).read_text(encoding="utf-8"))
            manifest["skills"][0]["source_sha256"] = "sha256:" + ("0" * 64)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaises(coverage.InventoryError):
                coverage.build_expected(root)

    def test_checked_in_ledger_is_byte_identical(self) -> None:
        result = coverage.check(ROOT)
        self.assertEqual("SOURCE_TASK_INVENTORY_VERIFIED", result["decision"])
        self.assertEqual(coverage.EXPECTED_SKILLS, result["skills"])
        self.assertEqual(coverage.EXPECTED_TASKS, result["tasks"])
        self.assertEqual("NOT_RUN", result["task_status"])
        self.assertEqual("BLOCKED", result["execution_status"])
        self.assertEqual("NOT_CERTIFIED", result["certification"])


if __name__ == "__main__":
    unittest.main()
