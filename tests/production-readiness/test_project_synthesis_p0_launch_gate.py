from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast


ROOT = Path(__file__).resolve().parents[2]
SUBJECT_PATH = ROOT / "scripts" / "operations" / "run_project_synthesis_p0_launch_gate.py"
SPEC = importlib.util.spec_from_file_location("project_synthesis_p0_launch_gate", SUBJECT_PATH)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class ProjectSynthesisP0LaunchGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, command: list[str], cwd: Path) -> str:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        return completed.stdout.strip()

    def _write(self, root: Path, relative: str, content: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _copy(self, root: Path, relative: str) -> None:
        self._write(root, relative, (ROOT / relative).read_text(encoding="utf-8"))

    def _repository(self, name: str = "source") -> Path:
        repository = self.root / name
        repository.mkdir()
        for relative in (
            "AGENTS.md",
            "Makefile",
            "engines/project-synthesis-engine/pyproject.toml",
            "docs/project-synthesis/p0-launch-scope-v1.json",
            "docs/project-synthesis/p0-launch-gate-contract.json",
            "scripts/operations/validate_project_synthesis_p0_scope.py",
            "scripts/operations/run_project_synthesis_p0_launch_gate.py",
        ):
            self._copy(repository, relative)
        self._run(["git", "init", "-q"], repository)
        self._run(["git", "config", "user.name", "P0 Test"], repository)
        self._run(["git", "config", "user.email", "p0-test@example.invalid"], repository)
        self._run(["git", "remote", "add", "origin", "https://github.com/zpcaiai/elmos.git"], repository)
        self._run(["git", "add", "."], repository)
        self._run(["git", "commit", "-q", "-m", "fixture"], repository)
        return repository

    def _evidence(self, name: str = "evidence") -> Path:
        evidence = self.root / name
        evidence.mkdir()
        return evidence

    def _artifact(
        self,
        repository: Path,
        evidence: Path,
        gate: dict[str, Any],
        *,
        status: str = "PASSED",
        self_promote: bool = False,
    ) -> Path:
        references: list[dict[str, Any]] = []
        for role in gate["required_evidence_roles"]:
            raw = evidence / f"{gate['id']}-{role}.json"
            raw.write_text(json.dumps({"role": role}) + "\n", encoding="utf-8")
            references.append(
                {
                    "role": role,
                    "path": raw.name,
                    "sha256": subject.sha256_file(raw),
                    "byte_count": raw.stat().st_size,
                }
            )
        now = datetime.now(UTC)
        artifact = {
            "schema_version": "1.0.0",
            "kind": gate["kind"],
            "gate_id": gate["id"],
            "scope": {
                "id": "project-synthesis-api-v1",
                "sha256": subject.load_contract()["scope"]["canonical_sha256"],
            },
            "source_revision": {
                "commit_sha": self._run(["git", "rev-parse", "HEAD"], repository),
                "tree_sha": self._run(["git", "rev-parse", "HEAD^{tree}"], repository),
            },
            "status": status,
            "evidence_class": gate["evidence_class"],
            "producer": {"id": "external-executor"},
            "independent_verifier": {"id": "external-verifier", "role": gate["signer_role"]},
            "observed_at": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "claims": gate["required_claims"],
            "evidence_refs": references,
            "production_ready": self_promote,
            "certified": self_promote,
        }
        path = evidence / cast(str, gate["artifact"])
        path.write_text(json.dumps(artifact, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_missing_artifacts_are_not_run_and_cli_exits_nonzero(self) -> None:
        repository = self._repository()
        evidence = self._evidence()
        output = self.root / "result.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(SUBJECT_PATH),
                "--repository",
                str(repository),
                "--evidence-directory",
                str(evidence),
                "--output",
                str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(2, completed.returncode)
        result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["certified"])
        self.assertTrue(all(gate["status"] == "NOT_RUN" for gate in result["gates"].values()))
        self.assertIn("release_bundle:ARTIFACT_NOT_RUN", result["blockers"])

    def test_unrelated_repository_is_rejected(self) -> None:
        repository = self.root / "unrelated"
        repository.mkdir()
        self._write(repository, "README.md", "unrelated\n")
        self._run(["git", "init", "-q"], repository)
        self._run(["git", "config", "user.name", "P0 Test"], repository)
        self._run(["git", "config", "user.email", "p0-test@example.invalid"], repository)
        self._run(["git", "remote", "add", "origin", "https://example.invalid/unrelated.git"], repository)
        self._run(["git", "add", "."], repository)
        self._run(["git", "commit", "-q", "-m", "fixture"], repository)
        result = subject.evaluate_launch_gate(repository, self._evidence())
        self.assertEqual("BLOCKED", result["decision"])
        self.assertIn("repository:SOURCE_REPOSITORY_ORIGIN_NOT_ALLOWED", result["blockers"])
        self.assertTrue(any("SOURCE_MARKER_NOT_TRACKED" in blocker for blocker in result["blockers"]))

    def test_dirty_source_tree_is_rejected_from_observed_git_state(self) -> None:
        repository = self._repository()
        (repository / "Makefile").write_text("project-synthesis:\n\t@false\n", encoding="utf-8")
        result = subject.evaluate_launch_gate(repository, self._evidence())
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["repository"]["worktree_clean"])
        self.assertIn("repository:SOURCE_WORKTREE_NOT_CLEAN", result["blockers"])

    def test_caller_reported_pass_and_self_promotion_are_rejected(self) -> None:
        repository = self._repository()
        evidence = self._evidence()
        gate = subject.load_contract()["gates"][0]
        self._artifact(repository, evidence, gate, self_promote=True)
        result = subject.evaluate_launch_gate(repository, evidence)
        self.assertEqual("BLOCKED", result["decision"])
        self.assertIn("release_bundle:ARTIFACT_SELF_PROMOTION_REJECTED", result["blockers"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["certified"])

    def test_not_run_status_cannot_be_upgraded_by_claims(self) -> None:
        repository = self._repository()
        evidence = self._evidence()
        gate = subject.load_contract()["gates"][0]
        self._artifact(repository, evidence, gate, status="NOT_RUN")
        result = subject.evaluate_launch_gate(repository, evidence)
        self.assertEqual("BLOCKED", result["decision"])
        self.assertIn("release_bundle:ARTIFACT_STATUS_NOT_RUN", result["blockers"])

    def test_unsigned_pass_is_blocked_by_fixed_empty_trust_policy(self) -> None:
        repository = self._repository()
        evidence = self._evidence()
        gate = subject.load_contract()["gates"][0]
        artifact_path = self._artifact(repository, evidence, gate)
        envelope = {
            "schema_version": "1.0.0",
            "kind": "elmos.project-synthesis.p0-gate-signature",
            "gate_id": gate["id"],
            "algorithm": "ed25519",
            "key_id": "caller-created-key",
            "signer_role": gate["signer_role"],
            "payload_format": "canonical-json",
            "payload_sha256": subject.sha256_bytes(
                subject.canonical_json(json.loads(artifact_path.read_text(encoding="utf-8")))
            ),
            "signature_base64": "A" * 88,
            "signed_at": datetime.now(UTC).isoformat(),
        }
        (evidence / gate["signature"]).write_text(json.dumps(envelope) + "\n", encoding="utf-8")
        result = subject.evaluate_launch_gate(repository, evidence)
        self.assertIn("trust:PRODUCTION_TRUST_POLICY_NOT_CONFIGURED", result["blockers"])
        self.assertIn("release_bundle:PRODUCTION_TRUST_POLICY_NOT_CONFIGURED", result["blockers"])
        self.assertFalse(result["production_ready"])

    def test_test_mode_can_only_validate_contract(self) -> None:
        repository = self._repository()
        evidence = self._evidence()
        for gate in subject.load_contract()["gates"]:
            self._artifact(repository, evidence, gate, self_promote=True)
        result = subject.evaluate_launch_gate(repository, evidence, test_mode=True)
        self.assertEqual("LOCAL_CONTRACT_VALID", result["decision"])
        self.assertEqual("BLOCKED", result["launch_decision"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["certified"])


if __name__ == "__main__":
    unittest.main()
