from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from elmos_etgb.benchmark import validate_hidden_test_boundary
from elmos_etgb.budget import BudgetExceeded, BudgetLedger
from elmos_etgb.candidate import freeze_candidate, validate_candidate
from elmos_etgb.checkpoint import CheckpointStore
from elmos_etgb.corpus import build_license_review_request
from elmos_etgb.evidence import EvidenceStore
from elmos_etgb.incidents import regression_from_incident
from elmos_etgb.materializer import materialize, smoke_cases
from elmos_etgb.performance import evaluate_performance
from elmos_etgb.registry import SkillRegistry
from elmos_etgb.scheduling import FairScheduler, TaskRequest
from elmos_etgb.skills import audit_skills
from elmos_etgb.statistics import multi_seed_stability
from elmos_etgb.supply_chain import inspect_tree
from elmos_etgb.triage import cluster_failures
from elmos_etgb.orchestrator import release_attestation_request, release_preflight
from elmos_etgb.validation import coverage_report, validate_package


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "skills/subskills/elmos-etgb-sota-skills-package-v1.1.0"
ARCHIVE = ROOT / "skills/subskills/elmos-etgb-sota-skills-package-v1.1.0.tar.gz"


def candidate() -> dict[str, str]:
    return {
        "candidate_id": "rc-1", "source_commit": "a" * 40, "model": "gpt-5.6-pro",
        "model_revision": "2026-08-27", "prompt_digest": "sha256:" + "1" * 64,
        "skill_manifest_digest": "sha256:" + "2" * 64, "rule_bundle_digest": "sha256:" + "3" * 64,
        "toolchain_image_digest": "sha256:" + "4" * 64, "oracle_version": "etgb-oracle-v1.1.0",
        "normalization_version": "etgb-normalize-v1.1.0",
    }


class V11RuntimeTests(unittest.TestCase):
    def test_package_is_complete_and_source_is_digest_bound(self) -> None:
        result = validate_package(PACKAGE, archive=ARCHIVE, extracted=PACKAGE)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["case_count"], 46664)
        self.assertTrue(result["coverage"]["complete"])
        self.assertTrue(audit_skills(PACKAGE)["valid"])
        self.assertEqual(len(SkillRegistry(PACKAGE).describe()), 24)

    def test_materialized_scope_has_four_smoke_routes(self) -> None:
        result = materialize(PACKAGE)
        self.assertEqual(result["total_cases"], 46664)
        self.assertEqual({case["business_line"] for case in smoke_cases(PACKAGE)}, {"spring-modernization", "cross-language", "project-generation", "sql-conversion"})
        self.assertTrue(coverage_report(PACKAGE)["complete"])

    def test_corpus_review_request_is_complete_but_not_an_approval(self) -> None:
        request = build_license_review_request(PACKAGE)
        self.assertEqual(request["request_type"], "corpus-license-review-request")
        self.assertEqual(request["repository_count"], 17)
        self.assertEqual(request["status"], "PENDING_EXTERNAL_REVIEW")
        self.assertTrue(all(item["status"] == "PENDING_EXTERNAL_REVIEW" for item in request["repositories"]))
        self.assertNotIn("signature", request)

    def test_release_preflight_separates_full_scope_from_smoke(self) -> None:
        result = release_preflight(PACKAGE, results=[])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["scope"]["expected_cases"], 46664)
        self.assertEqual(result["scope"]["expected_case_runs"], 131452)
        self.assertEqual(result["scope"]["observed_results"], 0)
        self.assertEqual(result["scope"]["external_adapter_cases"], 46660)
        self.assertEqual(result["scope"]["external_adapter_case_runs"], 131448)
        self.assertEqual(result["corpus"]["unapproved"], 17)
        self.assertTrue(any("full release scope" in blocker for blocker in result["blockers"]))

    def test_attestation_request_is_unsigned_and_blocked_until_inputs_are_complete(self) -> None:
        request = release_attestation_request(PACKAGE, [], profile="release", candidate_digest="sha256:" + "a" * 64)
        self.assertEqual(request["status"], "BLOCKED")
        self.assertFalse(request["signing_authorized"])
        self.assertEqual(request["certification_status"], "NOT_CERTIFIED")
        self.assertNotIn("signature", request)
        self.assertTrue(any("release result scope" in blocker for blocker in request["blockers"]))

    def test_candidate_and_hidden_boundary_fail_closed(self) -> None:
        frozen = freeze_candidate(candidate())
        self.assertTrue(frozen["candidate_digest"].startswith("sha256:"))
        bad = candidate(); bad["model_revision"] = "latest"
        self.assertTrue(any("mutable alias" in item for item in validate_candidate(bad)))
        self.assertFalse(validate_hidden_test_boundary(["public/a"], ["hidden/a"], worker_role="transform-worker")["valid"])
        self.assertFalse(validate_hidden_test_boundary(["same"], ["same"], worker_role="validation-worker")["valid"])

    def test_budget_is_idempotent_and_overrun_is_not_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = BudgetLedger(Path(directory) / "budget.json")
            ledger.reserve(run_id="run", tenant_id="tenant", owner_id="owner", max_input_tokens=5, max_output_tokens=5, max_credit_usd=1, max_wall_clock_ms=100)
            first = ledger.consume(run_id="run", idempotency_key="event-1", phase="prepare", input_tokens=1, wall_clock_ms=1)
            second = ledger.consume(run_id="run", idempotency_key="event-1", phase="prepare", input_tokens=1, wall_clock_ms=1)
            self.assertEqual(first, second)
            with self.assertRaises(BudgetExceeded):
                ledger.consume(run_id="run", idempotency_key="event-2", phase="build", input_tokens=5, wall_clock_ms=1)
            self.assertTrue(ledger.reconcile("run")["valid"])

    def test_checkpoint_and_evidence_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); artifact = root / "artifact.txt"; artifact.write_text("password=secret", encoding="utf-8")
            checkpoint = CheckpointStore(root / "checkpoints")
            record = checkpoint.save(run_id="run", phase="BUILDING", candidate_digest="sha256:" + "a" * 64, plan_digest="sha256:" + "b" * 64, environment_digest="sha256:" + "c" * 64, fencing_token=2, artifacts=[{"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}])
            self.assertTrue(checkpoint.verify("run")["valid"])
            self.assertFalse(checkpoint.resume_contract("run", candidate_digest=record["candidate_digest"], plan_digest=record["plan_digest"], current_fencing_token=2)["resumable"])
            store = EvidenceStore(root / "evidence", hmac_key=b"key")
            stored = store.add_file(artifact, logical_name="phase/log.txt", producer_environment="env", redact=True)
            self.assertNotIn(b"secret", (root / "evidence" / stored["sha256"][:2] / stored["sha256"]).read_bytes())
            store.seal({"run_id": "run"})
            self.assertTrue(store.verify()["valid"])

    def test_failure_triage_performance_supply_chain_and_regression(self) -> None:
        results = [{"case_id": "a", "business_line": "sql-conversion", "status": "failed", "failure_class": "behavior-mismatch", "oracle_results": [{"type": "semantic mismatch", "passed": False}]}]
        self.assertEqual(cluster_failures(results)["cluster_count"], 1)
        self.assertFalse(evaluate_performance({"latency_p95_ms": 120}, {"latency_p95_ms": {"limit": 100}})["passed"])
        self.assertTrue(inspect_tree(PACKAGE)["valid"])
        regression = regression_from_incident({"incident_id": "INC-1", "summary": "lost rollback", "business_line": "sql-conversion", "failure_class": "state-transaction-mismatch"})
        self.assertTrue(regression["regression_id"].startswith("INC-REG-"))
        stable = multi_seed_stability([{"case_id": "a", "status": "passed", "seed": 1}, {"case_id": "a", "status": "passed", "seed": 2}, {"case_id": "a", "status": "passed", "seed": 3}])
        self.assertEqual(stable["insufficient_seed_case_count"], 0)

    def test_tenant_scheduler_enforces_cap_and_binding(self) -> None:
        scheduler = FairScheduler(max_active_per_account=3)
        for number in range(4):
            scheduler.enqueue(TaskRequest(f"task-{number}", "tenant-a", "account-a"))
        dispatched = [scheduler.dispatch(account_id="account-a") for _ in range(4)]
        self.assertEqual(sum(item is not None for item in dispatched), 3)
        with self.assertRaises(PermissionError):
            scheduler.complete(task_id="task-0", tenant_id="tenant-b")


if __name__ == "__main__":
    unittest.main()
