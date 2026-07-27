from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IMPORTER = ROOT / "tooling" / "import_product_convergence_complete.py"
PACKAGE = ROOT / "batch46-product-convergence-complete-skills"
MANIFEST = (
    ROOT
    / "docs"
    / "product-closure-convergence"
    / "batch46-complete-installed-manifest.json"
)
DEPENDENCIES = (
    ROOT
    / "docs"
    / "product-closure-convergence"
    / "batch46-complete-normalized-prerequisites.json"
)
REPOSITORY_GATE = (
    ROOT / "scripts" / "product-convergence" / "run_repository_convergence_gate.py"
)


class Batch46CompleteIntegrationTest(unittest.TestCase):
    def test_importer_verifies_immutable_source_and_deduplicated_runtime(self) -> None:
        result = subprocess.run(
            [sys.executable, str(IMPORTER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(180, report["source_files"])
        self.assertEqual(40, report["source_skills"])
        self.assertEqual(29, report["source_schemas"])
        self.assertEqual(10, report["installed_new_semantic_owners"])
        self.assertEqual(30, report["reused_existing_semantic_owners"])
        self.assertFalse(report["source_gate_authoritative"])
        self.assertEqual("NOT_RUN", report["external_evidence"])

    def test_source_batch_label_never_installs_as_global_b46(self) -> None:
        self.assertEqual([], list((ROOT / ".agents" / "skills").glob("b46-*")))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            "Project Synthesis PG001 start; never overwritten",
            manifest["namespace_policy"]["global_batch46"],
        )
        self.assertEqual(40, len(manifest["skills"]))
        self.assertEqual(10, manifest["installed_new_semantic_owners"])
        self.assertEqual(30, manifest["reused_existing_semantic_owners"])
        self.assertFalse(
            manifest["source_registry_repairs"]["source_gate_authoritative"]
        )
        self.assertFalse(manifest["certified"])
        self.assertFalse(manifest["production_certified"])

    def test_normalized_prerequisites_are_exact_and_acyclic(self) -> None:
        payload = json.loads(DEPENDENCIES.read_text(encoding="utf-8"))
        dependencies = payload["dependencies"]
        self.assertEqual([str(number) for number in range(1497, 1537)], list(dependencies))
        self.assertEqual([], dependencies["1497"])
        self.assertEqual([], dependencies["1498"])
        self.assertEqual(["1498"], dependencies["1500"])
        self.assertEqual(["1498", "1500"], dependencies["1501"])
        self.assertEqual([str(number) for number in range(1498, 1535)], dependencies["1535"])
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(skill_id: str) -> None:
            self.assertNotIn(skill_id, visiting)
            if skill_id in visited:
                return
            visiting.add(skill_id)
            for prerequisite in dependencies[skill_id]:
                self.assertIn(prerequisite, dependencies)
                visit(prerequisite)
            visiting.remove(skill_id)
            visited.add(skill_id)

        for skill_id in dependencies:
            visit(skill_id)
        self.assertEqual(40, len(visited))

    def test_new_runtime_skills_retain_source_provenance_and_safe_authority(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        new_records = [
            record
            for record in manifest["skills"]
            if record["disposition"] == "installed_missing_semantic_owner"
        ]
        self.assertEqual(10, len(new_records))
        for record in new_records:
            text = (ROOT / record["installed_path"]).read_text(encoding="utf-8")
            header = text.split("---", 2)[1]
            self.assertIn("source_package: batch46-product-convergence-complete-skills", header)
            self.assertIn(f"source_id: '{record['source_id']}'", header)
            self.assertIn(f"source_name: {record['source_name']}", header)
            self.assertIn("normalized_namespace: product-convergence-overlay", header)
            self.assertIn("$conv-product-convergence-orchestrator", text)
            self.assertIn("run_repository_convergence_gate.py", text)
            self.assertIn("`NOT_RUN`", text)

    def test_checked_in_complete_pack_and_repository_gate_fail_closed(self) -> None:
        source_gate = (
            PACKAGE / "scripts" / "batch46-complete" / "run_convergence_gate.py"
        )
        source_result = subprocess.run(
            [
                sys.executable,
                str(source_gate),
                str(PACKAGE / "convergence-packs" / "reference-product"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, source_result.returncode)
        repository_result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_GATE),
                str(ROOT / "product-convergence"),
                "--evidence-root",
                str(ROOT),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, repository_result.returncode)
        report = json.loads(repository_result.stdout)
        self.assertEqual("BLOCKED", report["decision"])
        self.assertEqual("NOT_RUN", report["external_evidence"])
        self.assertFalse(report["certified"])
        self.assertFalse(report["production_certified"])
        self.assertFalse(report["approves_deployment"])


if __name__ == "__main__":
    unittest.main()
