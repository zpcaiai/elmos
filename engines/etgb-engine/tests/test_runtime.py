from __future__ import annotations

import base64
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from elmos_etgb.attestation import verify_attestation, unsigned_payload
from elmos_etgb.budget import BudgetLedger
from elmos_etgb.canonical import CanonicalizationError, canonical_json, digest_json
from elmos_etgb.checkpoint import CheckpointStore
from elmos_etgb.evidence import EvidenceStore, build_evidence_manifest, create_deterministic_bundle, verify_evidence_manifest
from elmos_etgb.gates import evaluate_gate
from elmos_etgb.harness import HarnessContractError, HarnessRuntime, PhaseResult, harness_contract_report
from elmos_etgb.oracles import compare_json, compare_trace
from elmos_etgb.runner import execute_case, run_cases
from elmos_etgb.registry import SkillRegistry
from elmos_etgb.security import ExecutionPolicy, SecurityBoundaryError, parse_command, resolve_within, run_command_sequence
from elmos_etgb.state_v11 import JsonRunStateStore
from elmos_etgb.state import StateConflict, StateStore
from elmos_etgb.corpus import verify_license_reviews


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "skills/subskills/elmos-etgb-sota-skills-package-v1.1.0"


class _ConformantHarnessAdapter:
    def __init__(self, artifact: Path) -> None:
        self.artifact = artifact
        self.calls: list[str] = []
        self.digest = "sha256:" + "a" * 64

    def _result(self, phase: str, outputs: dict[str, object], *, artifacts: list[Path] | None = None) -> PhaseResult:
        self.calls.append(phase)
        return PhaseResult("passed", outputs=outputs, artifacts=artifacts or [])

    def prepare(self, _context: dict[str, object]) -> PhaseResult:
        return self._result("prepare", {"workspace_digest": self.digest, "toolchain_digest": self.digest, "dependency_lock_digest": self.digest})

    def baseline(self, _context: dict[str, object]) -> PhaseResult:
        return self._result("baseline", {"source_build": {"passed": True}, "source_contract": {}, "source_state": {}, "source_trace": [], "source_flake_report": {}})

    def transform_or_generate(self, _context: dict[str, object]) -> PhaseResult:
        return self._result("transform_or_generate", {"target_repository_digest": self.digest, "adaptation_manifest": {}, "unsupported_manifest": [], "machine_usage": {}})

    def build(self, _context: dict[str, object]) -> PhaseResult:
        artifact_digest = "sha256:" + __import__("hashlib").sha256(self.artifact.read_bytes()).hexdigest()
        return self._result("build", {"clean_build_result": {"passed": True}, "sbom_digest": self.digest, "provenance_digest": self.digest, "artifact_digests": [artifact_digest]}, artifacts=[self.artifact])

    def validate(self, _context: dict[str, object]) -> PhaseResult:
        return self._result("validate", {"public_test_results": [], "hidden_test_results": [], "oracle_results": [{"passed": True}], "mutation_results": [], "performance_results": {}})

    def score(self, _context: dict[str, object]) -> PhaseResult:
        return self._result("score", {"score_document": {"score": 1.0}, "failure_classifications": [], "silent_semantic_error_claims": []})

    def publish(self, _context: dict[str, object]) -> PhaseResult:
        return self._result("publish", {"evidence_manifest_digest": self.digest, "evidence_signature": {"status": "signed-by-provider"}, "report_uris": []})

    def compensate(self, _context: dict[str, object]) -> PhaseResult:
        return self._result("compensate", {"compensation_receipts": [], "unresolved_side_effects": []})

    def cleanup(self, _context: dict[str, object]) -> PhaseResult:
        return self._result("cleanup", {"workspace_cleanup_receipt": {"status": "clean"}, "retained_artifact_refs": []})


class RuntimeTests(unittest.TestCase):
    def test_harness_contract_is_digest_bound_and_registry_exposed(self) -> None:
        report = harness_contract_report(PACKAGE / "integrations/harness/adapter-contract.yaml")
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["required_phases"], ["prepare", "baseline", "transform_or_generate", "build", "validate", "score", "publish", "compensate", "cleanup"])
        self.assertTrue(report["contract_digest"].startswith("sha256:"))
        registry = SkillRegistry(PACKAGE)
        self.assertEqual(registry.dispatch("production-harness-integration", "contract_report")["valid"], True)

    def test_harness_runtime_enforces_phases_and_persists_raw_phase_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_artifact = root / "build.log"
            build_artifact.write_text("build passed\n", encoding="utf-8")
            candidate_digest = "sha256:" + "b" * 64
            plan_digest = "sha256:" + "c" * 64
            state_store = JsonRunStateStore(root / "state")
            state_store.create(run_id="run-1", owner_id="worker-1", tenant_id="tenant-1", candidate_digest=candidate_digest, plan_digest=plan_digest)
            BudgetLedger(root / "budget.json").reserve(run_id="run-1", tenant_id="tenant-1", owner_id="worker-1", max_input_tokens=1000, max_output_tokens=1000, max_credit_usd=10, max_wall_clock_ms=100000)
            capabilities = [f"harness.{phase}" for phase in ("prepare", "baseline", "transform_or_generate", "build", "validate", "score", "publish", "compensate", "cleanup")]
            authority = {
                "schema_version": "1.0", "authority_id": "authority-1", "environment_id": "environment-1", "owner_type": "environment", "owner_id": "worker-1", "tenant_id": "tenant-1", "capabilities": capabilities,
                "filesystem": {"read_roots": [str(root)], "write_roots": [str(root)]}, "network": {"mode": "deny", "allowlist": []}, "secrets": {"allowed_refs": []}, "hidden_tests": {}, "fencing_token": 1,
            }
            context = {
                "tenant_id": "tenant-1", "project_id": "project-1", "task_id": "task-1", "case_run_id": "case-run-1", "candidate_digest": candidate_digest, "plan_digest": plan_digest, "case_digest": "sha256:" + "d" * 64,
                "environment_id": "environment-1", "authority_id": "authority-1", "idempotency_key": "tenant-1:run-1:case-run-1:prepare:1", "checkpoint_digest": "sha256:" + "e" * 64,
            }
            adapter = _ConformantHarnessAdapter(build_artifact)
            evidence = EvidenceStore(root / "evidence")
            result = HarnessRuntime(
                state_store=state_store,
                checkpoint_store=CheckpointStore(root / "checkpoints"),
                budget_ledger=BudgetLedger(root / "budget.json"),
                evidence_store=evidence,
            ).execute(run_id="run-1", adapter=adapter, context=context, authority=authority, owner_id="worker-1", fencing_token=1)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(adapter.calls, ["prepare", "baseline", "transform_or_generate", "build", "validate", "score", "publish"])
            self.assertTrue(all(record["raw_result_artifact"]["sha256"] for record in result["phases"]))
            checkpoint = CheckpointStore(root / "checkpoints").load("run-1")
            self.assertEqual(checkpoint["workspace_digest"], adapter.digest)
            self.assertTrue(checkpoint["resume_payload"]["raw_result_artifact"]["sha256"])
            self.assertTrue(CheckpointStore(root / "checkpoints").verify("run-1")["valid"])
            self.assertTrue(evidence.verify()["valid"])
            self.assertTrue(evidence.verify()["sealed"])

    def test_harness_runtime_rejects_missing_required_phase_output_before_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_store = JsonRunStateStore(root / "state")
            candidate_digest = "sha256:" + "b" * 64
            plan_digest = "sha256:" + "c" * 64
            state_store.create(run_id="run-1", owner_id="worker-1", tenant_id="tenant-1", candidate_digest=candidate_digest, plan_digest=plan_digest)
            BudgetLedger(root / "budget.json").reserve(run_id="run-1", tenant_id="tenant-1", owner_id="worker-1", max_input_tokens=1000, max_output_tokens=1000, max_credit_usd=10, max_wall_clock_ms=100000)
            capabilities = [f"harness.{phase}" for phase in ("prepare", "baseline", "transform_or_generate", "build", "validate", "score", "publish", "compensate", "cleanup")]
            authority = {
                "schema_version": "1.0", "authority_id": "authority-1", "environment_id": "environment-1", "owner_type": "environment", "owner_id": "worker-1", "tenant_id": "tenant-1", "capabilities": capabilities,
                "filesystem": {"read_roots": [str(root)], "write_roots": [str(root)]}, "network": {"mode": "deny", "allowlist": []}, "secrets": {"allowed_refs": []}, "hidden_tests": {}, "fencing_token": 1,
            }
            context = {
                "tenant_id": "tenant-1", "project_id": "project-1", "task_id": "task-1", "case_run_id": "case-run-1", "candidate_digest": candidate_digest, "plan_digest": plan_digest, "case_digest": "sha256:" + "d" * 64,
                "environment_id": "environment-1", "authority_id": "authority-1", "idempotency_key": "tenant-1:run-1:case-run-1:prepare:1", "checkpoint_digest": "sha256:" + "e" * 64,
            }
            adapter = _ConformantHarnessAdapter(root / "missing.log")
            adapter.prepare = lambda _context: PhaseResult("passed", outputs={})  # type: ignore[method-assign]
            with self.assertRaises(HarnessContractError):
                HarnessRuntime(
                    state_store=state_store,
                    checkpoint_store=CheckpointStore(root / "checkpoints"),
                    budget_ledger=BudgetLedger(root / "budget.json"),
                    evidence_store=EvidenceStore(root / "evidence"),
                ).execute(run_id="run-1", adapter=adapter, context=context, authority=authority, owner_id="worker-1", fencing_token=1)
            self.assertEqual(state_store.load("run-1")["state"], "FAILED")
            self.assertFalse((root / "checkpoints/run-1.checkpoint.json").exists())

    def test_canonical_json_is_stable_and_rejects_nan(self) -> None:
        self.assertEqual(canonical_json({"b": 2, "a": 1}), b'{"a":1,"b":2}')
        self.assertEqual(digest_json({"a": 1}), digest_json({"a": 1}))
        with self.assertRaises(CanonicalizationError):
            canonical_json(float("nan"))

    def test_oracles_preserve_order_and_make_ignores_visible(self) -> None:
        self.assertTrue(compare_json({"items": [2, 1]}, {"items": [1, 2]}, unordered_paths=["$.items"])["passed"])
        result = compare_json({"amount": "1.00"}, {"amount": "1.01"}, ignore_paths=[])
        self.assertFalse(result["passed"])
        self.assertEqual(result["first_difference"]["path"], "$.amount")
        self.assertTrue(compare_trace([{"event": "begin"}, {"event": "commit"}], [{"event": "begin"}, {"event": "commit"}], happens_before=[("begin", "commit")])["passed"])

    def test_shell_and_path_boundaries_are_fail_closed(self) -> None:
        with self.assertRaises(SecurityBoundaryError):
            parse_command("python3 -c 'print(1)' ; touch bad", allowed_executables=("python3",))
        with self.assertRaises(SecurityBoundaryError):
            resolve_within(PACKAGE, "../README.md")
        policy = ExecutionPolicy(root=PACKAGE, timeout_seconds=10)
        result = run_command_sequence("python3 -c 'print(\"ok\")'", PACKAGE, policy)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"].strip(), "ok")

    def test_evidence_is_content_addressed_and_tamper_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(Path(directory))
            artifact = store.put_json({"value": 1}, role="case-input")
            result = {"run_id": "run-1", "case_id": "case-1", "status": "passed"}
            manifest = build_evidence_manifest(run_id="run-1", case_id="case-1", result=result, artifacts=[artifact])
            self.assertEqual(verify_evidence_manifest(manifest, store), [])
            store._path(artifact["sha256"]).write_bytes(b"tampered")
            self.assertTrue(verify_evidence_manifest(manifest, store))

    def test_evidence_bundle_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as output_directory:
            root = Path(directory)
            (root / "b.txt").write_text("b", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            first = Path(output_directory) / "first.tar.gz"
            second = Path(output_directory) / "second.tar.gz"
            first_result = create_deterministic_bundle(root, first)
            second_result = create_deterministic_bundle(root, second)
            self.assertEqual(first_result["files"], 2)
            self.assertEqual(first_result["sha256"], second_result["sha256"])

    def test_state_store_enforces_idempotency_and_fencing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with StateStore(Path(directory) / "state.sqlite") as store:
                store.create_run(run_id="run-1", idempotency_key="idem-1", suite_id="suite", profile="smoke", owner="worker", plan_digest="plan", candidate={}, budget={})
                token = store.claim_run("run-1", owner="worker")
                store.transition("run-1", owner="worker", fencing_token=token, expected="PLANNED", new_status="PREPARING")
                store.transition("run-1", owner="worker", fencing_token=token, expected="PREPARING", new_status="RUNNING")
                result = {"status": "passed", "started_at": "now", "finished_at": "now"}
                store.save_case_result("run-1", "case-1", 0, owner="worker", fencing_token=token, result=result)
                newer = store.claim_run("run-1", owner="worker")
                with self.assertRaises(StateConflict):
                    store.save_checkpoint("run-1", "case-1", owner="worker", fencing_token=token, phase="stale", cursor={})
                store.save_checkpoint("run-1", "case-1", owner="worker", fencing_token=newer, phase="resume", cursor={"offset": 1})
                self.assertEqual(len(store.get_case_results("run-1")), 1)

    def test_release_gate_never_promotes_without_external_attestation(self) -> None:
        score = {"complete_run": True, "metrics": {"critical_oracle_pass_rate": 1.0, "silent_semantic_error_rate": 0.0, "data_corruption_count": 0, "security_regression_count": 0, "transaction_mismatch_count": 0, "flaky_case_count": 0, "evidence_completeness": 1.0, "unapproved_corpus_count": 0}, "by_priority": {"P1": {"weighted_pass_rate": 1.0}, "P2": {"weighted_pass_rate": 1.0}}}
        decision = evaluate_gate(score=score, validation={"valid": True}, coverage={"complete": True}, profile="release")
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertIn("independent external attestation", " ".join(decision["blockers"]))

    def test_release_gate_does_not_accept_boolean_attestation_bypass(self) -> None:
        score = {"complete_run": True, "metrics": {"critical_oracle_pass_rate": 1.0, "silent_semantic_error_rate": 0.0, "data_corruption_count": 0, "security_regression_count": 0, "transaction_mismatch_count": 0, "flaky_case_count": 0, "evidence_completeness": 1.0, "unapproved_corpus_count": 0}, "by_priority": {"P1": {"weighted_pass_rate": 1.0}, "P2": {"weighted_pass_rate": 1.0}}}
        decision = evaluate_gate(score=score, validation={"valid": True}, coverage={"complete": True}, profile="release", external_attested=True, independent_verifier="verifier-1")
        self.assertEqual(decision["decision"], "BLOCKED")
        self.assertFalse(decision["external_attested"])

    def test_ed25519_attestation_is_verified_and_tamper_evident(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        digest = "a" * 64
        candidate_digest = "sha256:" + digest
        attestation = {
            "schema_version": "1.0",
            "attestation_id": "attestation-1",
            "profile": "release",
            "subject": {
                "candidate_digest": candidate_digest,
                "score_digest": digest,
                "validation_digest": digest,
                "coverage_digest": digest,
                "corpus_digest": digest,
                "evidence_digest": digest,
            },
            "executor_id": "executor-1",
            "verifier_id": "verifier-1",
            "issued_at": now.isoformat(),
            "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
            "key_id": "key-1",
            "algorithm": "ed25519",
        }
        attestation["signature"] = base64.urlsafe_b64encode(private_key.sign(canonical_json(unsigned_payload(attestation)))).decode().rstrip("=")
        trust_store = {
            "schema_version": "1.0",
            "keys": [{"key_id": "key-1", "algorithm": "ed25519", "status": "active", "public_key": base64.urlsafe_b64encode(public_key).decode().rstrip("="), "not_before": (now - dt.timedelta(hours=1)).isoformat(), "not_after": (now + dt.timedelta(hours=2)).isoformat()}],
        }
        self.assertTrue(verify_attestation(attestation, trust_store, now=now)["valid"])
        attestation["subject"]["score_digest"] = "b" * 64
        self.assertFalse(verify_attestation(attestation, trust_store, now=now)["valid"])

    def test_release_gate_accepts_a_valid_candidate_digest_as_a_supplied_input(self) -> None:
        score = {"complete_run": False, "metrics": {"critical_oracle_pass_rate": 1.0, "silent_semantic_error_rate": 0.0, "data_corruption_count": 0, "security_regression_count": 0, "transaction_mismatch_count": 0, "flaky_case_count": 0, "evidence_completeness": 1.0, "unapproved_corpus_count": 0}, "by_priority": {}}
        decision = evaluate_gate(score=score, validation={"valid": True}, coverage={"complete": True}, profile="release", candidate_digest="sha256:" + "a" * 64)
        self.assertNotIn("frozen candidate digest is required for release/golden evaluation", decision["blockers"])
        self.assertEqual(decision["candidate_digest"], "sha256:" + "a" * 64)

    def test_signed_license_review_is_bound_to_locked_commit(self) -> None:
        import yaml
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "corpora").mkdir()
            commit = "a" * 40
            (root / "corpora/corpus-lock.yaml").write_text(yaml.safe_dump({"schema_version": "1.0", "generated_at": "2026-08-27", "repositories": [{"id": "sample-corpus", "repository": "example/sample", "commit": commit, "license_review": "required", "redistribution": "metadata-only", "policy": {"network": "allowlisted", "secrets": "none"}}]}), encoding="utf-8")
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            private_key = Ed25519PrivateKey.generate()
            public_key = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            record = {
                "schema_version": "1.0",
                "record_type": "license-review",
                "payload": {"corpus_id": "sample-corpus", "repository": "example/sample", "commit": commit, "license_spdx": ["Apache-2.0"], "patent_and_trademark_scope": "reviewed", "data_and_export_control_scope": "reviewed", "redistribution_decision": "metadata-only", "review_status": "approved"},
                "issuer_id": "license-reviewer-1",
                "key_id": "license-key-1",
                "algorithm": "ed25519",
                "issued_at": (now - dt.timedelta(minutes=1)).isoformat(),
                "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
            }
            record["signature"] = base64.urlsafe_b64encode(private_key.sign(canonical_json(unsigned_payload(record)))).decode().rstrip("=")
            (root / "corpora/license-reviews.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
            trust_store = {"schema_version": "1.0", "keys": [{"key_id": "license-key-1", "algorithm": "ed25519", "status": "active", "record_types": ["license-review"], "public_key": base64.urlsafe_b64encode(public_key).decode().rstrip("="), "not_before": (now - dt.timedelta(hours=1)).isoformat(), "not_after": (now + dt.timedelta(hours=2)).isoformat()}]}
            result = verify_license_reviews(root, release=True, trust_store=trust_store)
            self.assertTrue(result["valid"])
            self.assertEqual(result["approved"], 1)

    def test_runner_persists_completed_results_and_replays_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = {
                "id": "RUNNER-LOCAL-001",
                "business_line": "cross-cutting",
                "priority": "P0",
                "level": "L1",
                "execution": {
                    "adapter": "local-process",
                    "command": "python3 -c 'print(1)'",
                    "cwd": ".",
                    "timeout_seconds": 10,
                    "max_output_bytes": 4096,
                },
            }
            first = run_cases([case], root, profile="smoke", state_db=root / "state.sqlite", artifact_root=root / "evidence", run_id="run-1", owner="worker")
            second = run_cases([case], root, profile="smoke", state_db=root / "state.sqlite", artifact_root=root / "evidence", run_id="run-1", owner="another-worker", resume=True)
            self.assertEqual(first, second)
            self.assertEqual(first[0]["status"], "passed")

    def test_external_adapters_are_explicitly_unavailable(self) -> None:
        case = {"id": "EXTERNAL-001", "business_line": "cross-language", "priority": "P0", "execution": {"adapter": "external-transformation-harness"}}
        result = execute_case(case, PACKAGE)
        self.assertEqual(result["status"], "unavailable")
        self.assertNotEqual(result["claim_state"], "success")

    def test_registry_exposes_real_oracle_and_package_operations(self) -> None:
        registry = SkillRegistry(PACKAGE)
        names = {item["name"] for item in registry.describe()}
        self.assertEqual(len(names), 24)
        self.assertTrue(registry.dispatch("differential-oracle-engine", "compare_json", {"left": {"a": 1}, "right": {"a": 1}})["passed"])
        self.assertTrue(registry.dispatch("test-case-authoring", "coverage")["complete"])


if __name__ == "__main__":
    unittest.main()
