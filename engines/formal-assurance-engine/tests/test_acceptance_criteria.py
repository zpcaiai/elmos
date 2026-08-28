from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from elmos_formal_assurance.contracts import (
    AssuranceLevel,
    Criticality,
    ProofObligation,
    ProofResult,
    ProofStatus,
    Scope,
    TrustedIdentity,
)
from elmos_formal_assurance.gate import evaluate_release_gate
from elmos_formal_assurance.runtime import (
    FormalAssuranceRuntime,
    RuntimeAuthorizationError,
    RuntimeConfig,
)
from elmos_formal_assurance.store import StateStore, StoreError
from test_all_skill_contracts import EXPECTED_OUTPUT_KEYS, fixtures, scope


ROOT = Path(__file__).resolve().parents[3]
TRACEABILITY_PATH = ROOT / "docs/formal-assurance-kernel/acceptance-traceability.json"
TRACEABILITY = json.loads(TRACEABILITY_PATH.read_text(encoding="utf-8"))
CRITERIA = TRACEABILITY["criteria"]


def _token(criterion_id: str) -> str:
    return hashlib.sha256(criterion_id.encode("utf-8")).hexdigest()[:24]


class AcceptanceCriteriaTests(unittest.TestCase):
    """One executable repository-owned control for each of 481 source criteria.

    These tests establish local code-path and fail-closed control behavior. They
    deliberately do not convert local execution into native, independent,
    representative, provider, deployment, customer, or certification evidence.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if TRACEABILITY.get("criterionCount") != 481 or len(CRITERIA) != 481:
            raise RuntimeError("acceptance traceability must contain exactly 481 rows")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.store = StateStore()
        cls.runtime = FormalAssuranceRuntime(
            store=cls.store,
            config=RuntimeConfig(
                artifact_root=Path(cls.temporary.name) / "artifacts",
                execution_root=Path(cls.temporary.name) / "executions",
            ),
        )
        cls.identity = TrustedIdentity("tenant-a", "operator-a", "project-a")
        cls.scope = Scope(
            "tenant-a",
            "account-a",
            "project-a",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "all-skill-contracts",
        )
        cls.cases = fixtures()
        runtime_skills = {item["skillId"] for item in cls.runtime.list_skills()}
        if (
            set(cls.cases) != runtime_skills
            or set(EXPECTED_OUTPUT_KEYS) != runtime_skills
        ):
            raise RuntimeError(
                "acceptance probes do not cover the exact runtime registry"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls.temporary.cleanup()

    def _assert_trace_row(self, row: dict[str, object]) -> None:
        self.assertEqual(row["traceabilityState"], "MAPPED_TO_EXECUTABLE_LOCAL_CONTROL")
        self.assertEqual(row["qualificationState"], "EVIDENCE_PENDING")
        self.assertEqual(row["externalEvidenceStatus"], "NOT_RUN")
        self.assertEqual(row["independentVerificationStatus"], "NOT_RUN")
        self.assertEqual(row["certificationStatus"], "NOT_CERTIFIED")
        self.assertTrue(str(row["sourceCriterionDigest"]).startswith("sha256:"))

    def _skill_specific_contract(self, row: dict[str, object]) -> None:
        criterion_id = str(row["criterionId"])
        skill_id = str(row["skillId"])
        token = _token(criterion_id)
        payload = deepcopy(self.cases[skill_id])
        if skill_id == "elmos-formal-assurance-orchestrator":
            payload["runId"] = "run-" + token
            payload["obligationId"] = "obl-" + token
        result = self.runtime.dispatch(
            skill_id,
            {
                "scope": scope(),
                "subjectId": "acceptance-" + token,
                "idempotencyKey": "criterion-" + token,
                **payload,
            },
            self.identity,
        )
        if skill_id == "elmos-formal-assurance-orchestrator":
            self.store.control_run(self.scope, str(payload["runId"]), "CANCEL")
        self.assertEqual(result["skillId"], skill_id)
        self.assertEqual(result["handlerId"], row["handlerId"])
        self.assertEqual(result["implementationState"], "PRODUCTION_CODE_COMPLETE")
        self.assertIn(EXPECTED_OUTPUT_KEYS[skill_id], result["output"])
        self.assertTrue(result["output"])
        self.assertTrue(result["requestDigest"].startswith("sha256:"))
        self.assertEqual(result["externalEvidenceStatus"], "NOT_RUN")
        self.assertEqual(result["certificationStatus"], "NOT_CERTIFIED")
        self.assertNotEqual(result["proofStatus"], "PROVED_CERTIFIED")

    def _bounded_honesty_gate(self, row: dict[str, object]) -> None:
        token = _token(str(row["criterionId"]))
        obligation = ProofObligation(
            id="obl-" + token,
            criticality=Criticality.P0,
            property_kind="NONINTERFERENCE",
            required_assurance=AssuranceLevel.A2_SOLVER_PROVED,
            formula_hash="a" * 64,
            allow_bounded=False,
        )
        result = ProofResult(
            run_id="run-" + token,
            obligation_id=obligation.id,
            status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
            assurance_level=AssuranceLevel.A1_BOUNDED,
            engine="local-bounded",
            mode="BOUNDED",
            assumption_hash="b" * 64,
            tcb_hash="c" * 64,
            bound={"samples": 8},
        )
        decision = evaluate_release_gate(
            [obligation], {obligation.id: result}, required_gate="E2_MODEL"
        )
        self.assertEqual(decision.decision, "DENY")
        self.assertTrue(decision.blocking_reasons)

    def _counterexample_replay(self, row: dict[str, object]) -> None:
        token = _token(str(row["criterionId"]))
        result = self.runtime.dispatch(
            "elmos-counterexample-to-test",
            {
                "scope": scope(),
                "subjectId": "counterexample-" + token,
                "idempotencyKey": "counterexample-" + token,
                "counterexample": {
                    "id": "cex-" + token,
                    "obligationId": "obl-" + token,
                    "kind": "INPUT",
                    "witness": {"token": "must-redact", "value": -1},
                    "violatedProperty": "value remains non-negative",
                    "replay": {"command": "pytest -k cex_" + token},
                },
            },
            self.identity,
        )
        self.assertEqual(result["proofStatus"], "REFUTED_WITH_COUNTEREXAMPLE")
        self.assertEqual(result["output"]["scenario"]["obligationId"], "obl-" + token)
        self.assertEqual(result["output"]["scenario"]["witness"]["token"], "[REDACTED]")
        self.assertIn("def test_", result["output"]["pytestSource"])
        self.assertEqual(
            result["output"]["scenario"]["replay"]["executionStatus"], "NOT_RUN"
        )

    def _dependency_drift_invalidation(self, row: dict[str, object]) -> None:
        token = _token(str(row["criterionId"]))
        run_id = "run-" + token
        obligation_id = "obl-" + token
        self.store.submit_run(self.scope, run_id, obligation_id)
        leased = self.store.lease_run(self.scope, run_id, "worker-" + token, 1)
        self.store.start_run(
            self.scope, run_id, "worker-" + token, leased["fencing_token"]
        )
        self.store.commit_run(
            self.scope,
            run_id,
            "worker-" + token,
            leased["fencing_token"],
            ProofResult(
                run_id,
                obligation_id,
                ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
                AssuranceLevel.A1_BOUNDED,
                "local-bounded",
                "BOUNDED",
                "d" * 64,
                "e" * 64,
                bound={"samples": 8},
            ),
        )
        dependency_id = "tcb-" + token
        self.store.register_dependency(
            self.scope,
            subject_type="proof_run",
            subject_id=run_id,
            dependency_kind="TCB",
            dependency_id=dependency_id,
            dependency_hash="f" * 64,
        )
        cache_key = "cache-" + token
        self.store.put_cache(
            self.scope,
            cache_key,
            {
                "dependencies": [dependency_id],
                "dependencyBindings": {dependency_id: "sha256:" + "f" * 64},
                "resultRunId": run_id,
            },
        )
        drift_actor = TrustedIdentity(
            "tenant-a",
            "drift-" + token,
            "project-a",
            roles=("formal-assurance-drift",),
            authorization_ref="authz:drift:" + token,
        )
        invalidated = self.runtime.report_drift(
            {
                "scope": scope(),
                "idempotencyKey": "drift-" + token,
                "dependencyKind": "TCB",
                "dependencyId": dependency_id,
                "newHash": "1" * 64,
            },
            drift_actor,
        )
        self.assertEqual(invalidated["proofResultsMarkedStale"], 1)
        self.assertEqual(invalidated["cacheEntriesInvalidated"], 1)
        self.assertIsNone(self.store.get_cache(self.scope, cache_key))
        persisted = json.loads(self.store.get_run(self.scope, run_id)["result_json"])
        self.assertTrue(persisted["stale"])
        self.assertTrue(
            any(
                item["subjectId"] == run_id
                for item in self.store.pending_reproofs(self.scope, limit=1000)
            )
        )

    def _tenant_fencing_audit_denial(self, row: dict[str, object]) -> None:
        token = _token(str(row["criterionId"]))
        document_id = "evidence-" + token
        self.store.put_document(
            self.scope,
            "proof_artifact",
            document_id,
            {"runId": "run-" + token, "status": "LOCAL_ENGINEERING"},
        )
        foreign_scope = Scope(
            "tenant-b",
            self.scope.account_id,
            self.scope.project_id,
            self.scope.source_artifact_digest,
            self.scope.target_artifact_digest,
            self.scope.environment_digest,
            self.scope.workload_key,
        )
        with self.assertRaises(StoreError):
            self.store.get_document(foreign_scope, "proof_artifact", document_id)
        foreign_identity = TrustedIdentity("tenant-b", "foreign-" + token, "project-a")
        with self.assertRaises(RuntimeAuthorizationError):
            self.runtime.register_assumption(
                {
                    "scope": scope(),
                    "idempotencyKey": "foreign-" + token,
                },
                foreign_identity,
            )
        audit = self.store.security_audit(foreign_identity, limit=1000)
        self.assertTrue(
            any(
                item["action"] == "register-assumption" and item["decision"] == "DENY"
                for item in audit
            )
        )

    def _run_criterion(self, row: dict[str, object]) -> None:
        self._assert_trace_row(row)
        scenario = str(row["scenario"])
        if scenario == "skill-specific-contract":
            self._skill_specific_contract(row)
        elif scenario == "bounded-honesty-gate":
            self._bounded_honesty_gate(row)
        elif scenario == "counterexample-replay":
            self._counterexample_replay(row)
        elif scenario == "dependency-drift-invalidation":
            self._dependency_drift_invalidation(row)
        elif scenario == "tenant-fencing-audit-denial":
            self._tenant_fencing_audit_denial(row)
        else:  # pragma: no cover - importer rejects unknown scenarios
            self.fail(f"unknown acceptance scenario: {scenario}")


def _criterion_test(row: dict[str, object]):
    def test(self: AcceptanceCriteriaTests) -> None:
        self._run_criterion(row)

    identifier = str(row["criterionId"])
    test.__name__ = "test_" + identifier.replace("-", "_")
    test.__qualname__ = f"AcceptanceCriteriaTests.{test.__name__}"
    return test


for _row in CRITERIA:
    _method = _criterion_test(_row)
    if hasattr(AcceptanceCriteriaTests, _method.__name__):
        raise RuntimeError(f"duplicate generated acceptance test: {_method.__name__}")
    setattr(AcceptanceCriteriaTests, _method.__name__, _method)


if __name__ == "__main__":
    unittest.main()
