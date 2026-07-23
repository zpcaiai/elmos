from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class ToolkitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        cls.schema = json.loads(
            (ROOT / "schemas" / "executable-skill-contract-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        cls.compiler = load_module(
            "batch97_104_test_compiler", ROOT / "scripts" / "compile_skill_contract.py"
        )
        cls.graph_validator = load_module(
            "batch97_104_test_graph", ROOT / "scripts" / "validate_capability_graph.py"
        )
        cls.installer = load_module(
            "batch97_104_test_installer", ROOT / "scripts" / "install_skills.py"
        )

    def test_package_validator_covers_exact_distribution(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_package.py"), str(ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("128 Skills validated", result.stdout)

    def test_all_128_skills_compile_to_strict_contracts(self) -> None:
        compiled_ids: list[str] = []
        for skill in self.manifest["skills"]:
            contract = self.compiler.compile_contract(ROOT / skill["path"])
            jsonschema.validate(contract, self.schema)
            compiled_ids.append(contract["id"])
            self.assertGreaterEqual(len(contract["steps"]), 10)
            self.assertTrue(contract["inputs"])
            self.assertTrue(contract["outputs"])
            self.assertTrue(contract["rollback"])
            self.assertEqual(
                {"unit", "integration", "negative"},
                {test["type"] for test in contract["tests"]},
            )
            self.assertEqual("deny", contract["permissions"]["default"])
        self.assertEqual([skill["id"] for skill in self.manifest["skills"]], compiled_ids)

    def test_contract_schema_rejects_prose_only_shape(self) -> None:
        invalid = {
            "schema_version": "elmos.executable-skill-contract.v1",
            "id": "B98-S01",
            "name": "b98-executable-skill-contract-schema",
            "version": "1.0.0",
            "batch": 98,
            "inputs": [],
            "outputs": [],
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, self.schema)

    def test_capability_graph_accepts_valid_dag(self) -> None:
        graph = json.loads(
            (ROOT / "templates" / "capability-graph.example.json").read_text(encoding="utf-8")
        )
        self.assertEqual([], self.graph_validator.validate_graph(graph))

    def test_capability_graph_rejects_cycles_duplicates_and_dangling_edges(self) -> None:
        node = {
            "id": "a",
            "type": "skill",
            "name": "a",
            "version": "1.0.0",
            "provenance": {"source": "test"},
        }
        other = {**node, "id": "b", "name": "b"}
        cycle = {
            "schema_version": "elmos.capability-graph.v1",
            "snapshot_id": "sha256:test",
            "nodes": [node, other],
            "edges": [
                {"from": "a", "to": "b", "relation": "depends", "blocking": True},
                {"from": "b", "to": "a", "relation": "depends", "blocking": True},
            ],
        }
        self.assertIn("blocking dependency cycle", self.graph_validator.validate_graph(cycle))
        duplicate = {**cycle, "nodes": [node, node], "edges": []}
        self.assertIn("duplicate node id: a", self.graph_validator.validate_graph(duplicate))
        dangling = {
            **cycle,
            "edges": [{"from": "a", "to": "missing", "relation": "depends"}],
        }
        self.assertIn("edge 0 is dangling", self.graph_validator.validate_graph(dangling))
        malformed = {
            **cycle,
            "edges": [{"from": {}, "to": "a", "relation": "depends"}],
        }
        self.assertIn("edge 0 has invalid endpoints", self.graph_validator.validate_graph(malformed))

    def make_candidate(self, directory: Path, scope: str) -> tuple[Path, dict[str, Any]]:
        roles = [
            "authorization",
            "runner-attestation",
            "runtime-environment",
            "test-result",
            "certification-request",
        ]
        records: list[dict[str, Any]] = []
        refs: dict[str, str] = {}
        for role in roles:
            path = directory / f"{role}.json"
            path.write_text(json.dumps({"scope": scope, "role": role}) + "\n", encoding="utf-8")
            reference = digest(path)
            refs[role] = reference
            records.append(
                {
                    "path": path.name,
                    "sha256": reference,
                    "size_bytes": path.stat().st_size,
                    "role": role,
                }
            )
        candidate = {
            "scope": scope,
            "status": "candidate",
            "evidence_files": records,
            "evidence_refs": list(refs.values()),
            "executor": {"identity": "executor@example.invalid"},
            "independent_verifier": {
                "identity": "verifier@example.invalid",
                "decision": "approved",
            },
            "authorization": {
                "status": "approved",
                "scope": scope,
                "approval_ref": refs["authorization"],
            },
            "runtime": {
                "status": "passed",
                "environment_digest": refs["runtime-environment"],
                "runner_attestation_ref": refs["runner-attestation"],
            },
            "tests": [
                {
                    "id": "p0-runtime",
                    "priority": "P0",
                    "required": True,
                    "status": "passed",
                    "evidence_refs": [refs["test-result"]],
                }
            ],
            "certification_request": {
                "status": "prepared",
                "scope": scope,
                "digest": refs["certification-request"],
            },
        }
        result_path = directory / "candidate.json"
        result_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
        return result_path, candidate

    def run_gate(self, scope: str, result: Path | None = None) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "run_certification_gate.py"),
            "--package",
            str(ROOT),
            "--scope",
            scope,
        ]
        if result is not None:
            command.extend(["--result", str(result), "--evidence-root", str(result.parent)])
        return subprocess.run(command, check=False, capture_output=True, text=True)

    def test_gate_reports_not_run_without_runtime_evidence(self) -> None:
        scope = self.manifest["skills"][-1]["id"]
        result = self.run_gate(scope)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual("not_run", json.loads(result.stdout)["status"])

    def test_gate_rejects_fabricated_or_unbound_evidence(self) -> None:
        scope = self.manifest["skills"][-1]["id"]
        with tempfile.TemporaryDirectory() as temporary:
            result_path, candidate = self.make_candidate(Path(temporary), scope)
            candidate["evidence_files"][0]["sha256"] = "sha256:" + "f" * 64
            result_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            result = self.run_gate(scope, result_path)
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual("blocked", payload["status"])
        self.assertTrue(any("digest does not match" in error for error in payload["errors"]))

    def test_gate_rejects_evidence_path_escape(self) -> None:
        scope = self.manifest["skills"][-1]["id"]
        with tempfile.TemporaryDirectory() as temporary:
            evidence_root = Path(temporary) / "evidence"
            evidence_root.mkdir()
            result_path, candidate = self.make_candidate(evidence_root, scope)
            outside = Path(temporary) / "outside.json"
            outside.write_text('{"outside": true}\n', encoding="utf-8")
            outside_ref = digest(outside)
            old_ref = candidate["evidence_files"][0]["sha256"]
            candidate["evidence_files"][0].update(
                {"path": "../outside.json", "sha256": outside_ref, "size_bytes": outside.stat().st_size}
            )
            candidate["evidence_refs"] = [
                outside_ref if reference == old_ref else reference
                for reference in candidate["evidence_refs"]
            ]
            candidate["authorization"]["approval_ref"] = outside_ref
            result_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            result = self.run_gate(scope, result_path)
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual("blocked", payload["status"])
        self.assertTrue(any("escapes evidence root" in error for error in payload["errors"]))

    def test_gate_rejects_malformed_reference_types_without_crashing(self) -> None:
        scope = self.manifest["skills"][-1]["id"]
        with tempfile.TemporaryDirectory() as temporary:
            result_path, candidate = self.make_candidate(Path(temporary), scope)
            candidate["evidence_refs"] = [{}]
            result_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            result = self.run_gate(scope, result_path)
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual("blocked", payload["status"])
        self.assertIn(
            "evidence_refs must contain at least two unique SHA-256 references",
            payload["errors"],
        )

    def test_gate_maximum_local_state_requires_external_gate(self) -> None:
        scope = self.manifest["skills"][-1]["id"]
        with tempfile.TemporaryDirectory() as temporary:
            result_path, _ = self.make_candidate(Path(temporary), scope)
            result = self.run_gate(scope, result_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("ready_for_external_gate", payload["status"])
        self.assertFalse(payload["certified"])

    def test_global_id_tool_is_non_mutating_without_namespace_authority(self) -> None:
        before = (ROOT / "manifest.json").read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "remap_global_ids.py"),
                "--root",
                str(ROOT),
                "--start",
                "500",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        proposal = json.loads(result.stdout)
        self.assertEqual("PROPOSED_UNAPPROVED", proposal["status"])
        self.assertFalse(proposal["package_mutated"])
        self.assertEqual(before, (ROOT / "manifest.json").read_bytes())

    def test_installer_is_transactional_and_preserves_replaced_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "skills"
            first = self.installer.install(ROOT, target, 97, False)
            self.assertEqual(16, first["installed"])
            first_name = self.manifest["skills"][0]["name"]
            user_note = target / first_name / "user-note.txt"
            user_note.write_text("preserve me\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                self.installer.install(ROOT, target, 97, False)
            replaced = self.installer.install(ROOT, target, 97, True)
            backup = Path(replaced["backup"])
            self.assertEqual("preserve me\n", (backup / first_name / "user-note.txt").read_text())
            self.assertTrue((target / first_name / "agents" / "openai.yaml").is_file())
            self.assertTrue(Path(replaced["receipt"]).is_file())
            self.assertFalse(list(target.glob(".elmos-batch97-104-stage-*")))

    def test_split_manifests_cover_exact_batches(self) -> None:
        ids: list[str] = []
        for batch in self.manifest["batches"]:
            split = json.loads(
                (ROOT / "manifests" / f"batch-{batch}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(16, split["skill_count"])
            ids.extend(skill["id"] for skill in split["skills"])
        self.assertEqual([skill["id"] for skill in self.manifest["skills"]], ids)


if __name__ == "__main__":
    unittest.main()
