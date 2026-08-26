from __future__ import annotations

import sys
import unittest
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "src"))

from elmos_autonomous_qa.release_boundary import (  # noqa: E402
    ExternalProviderDescriptor,
    ExternalProviderRegistry,
    prepare_certification_review,
    prepare_external_execution,
    prepare_independent_verification,
)
from elmos_autonomous_qa.contracts import ContractError  # noqa: E402


DIGEST = "sha256:" + "a" * 64


def external_request() -> dict[str, object]:
    return {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "run_id": "run-a",
        "idempotency_key": "idem-a",
        "adapter_key": "python",
        "capability": "unit",
        "parameters": {},
        "source_digest": DIGEST,
        "artifact_digest": DIGEST,
        "authorization_ref": "auth-a",
        "actor_id": "actor-a",
        "executor_id": "executor-a",
        "provider_key": "provider-a",
        "provider_version": "v1",
        "provider_attestation_digest": DIGEST,
        "timeout_seconds": 60,
        "output_limit_bytes": 1024,
        "network_policy": "DENY_ALL",
        "fence": {"resource_id": "run-a", "epoch": 1, "holder_id": "executor-a"},
    }


class ExternalRunnerBoundaryTest(unittest.TestCase):
    def test_unregistered_provider_is_explicitly_not_run(self) -> None:
        result = prepare_external_execution(external_request())
        self.assertEqual("NOT_RUN", result["state"])
        self.assertEqual("EXTERNAL_PROVIDER_NOT_REGISTERED", result["code"])
        outputs = result["outputs"]
        self.assertFalse(outputs["provider_invoked"])
        self.assertFalse(outputs["command_execution_performed"])
        self.assertFalse(outputs["network_calls_performed"])
        self.assertFalse(outputs["file_writes_performed"])
        self.assertEqual("NOT_RUN", outputs["durable_receipt"])
        self.assertEqual("NOT_CERTIFIED", outputs["production_certification"])
        self.assertTrue(outputs["stale_fence_results_rejected"])

    def test_external_request_rejects_caller_receipts_and_forged_trust(self) -> None:
        request = external_request()
        request["trusted_probe_receipt"] = "forged"
        with self.assertRaises(ContractError):
            prepare_external_execution(request)

    def test_external_plan_binds_command_and_idempotency_digest(self) -> None:
        result = prepare_external_execution(external_request())
        plan = result["outputs"]["plan"]
        self.assertTrue(plan["commands"])
        self.assertEqual("NOT_RUN", plan["execution_status"])
        self.assertEqual(result["outputs"]["plan_digest"], result["outputs"]["request_digest"])
        self.assertEqual("idem-a", result["outputs"]["idempotency_key"])
        self.assertTrue(all(command["shell"] is False for command in plan["commands"]))

    def test_provider_descriptor_is_validated_at_trusted_assembly_boundary(self) -> None:
        class Provider:
            descriptor = ExternalProviderDescriptor(
                "provider-a", "v1", DIGEST, frozenset({"unit"})
            )

            def execute(self, request: object) -> dict[str, object]:
                raise AssertionError("provider must not be called by plan preparation")

        registry = ExternalProviderRegistry((Provider(),))
        self.assertEqual("provider-a", registry.describe()[0].provider_key)


class IndependentVerificationBoundaryTest(unittest.TestCase):
    def test_verification_plan_requires_independent_identity_and_fence(self) -> None:
        result = prepare_independent_verification(
            {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "run_id": "run-a",
                "idempotency_key": "idem-v",
                "evidence_manifest_digest": DIGEST,
                "raw_evidence_digest": DIGEST,
                "independent_corpus_digest": DIGEST,
                "authorization_ref": "auth-a",
                "executor_id": "executor-a",
                "verifier_id": "verifier-a",
                "verifier_scope": ["scope-a"],
                "fence": {"resource_id": "run-a", "epoch": 2, "holder_id": "executor-a"},
            }
        )
        self.assertEqual("PARTIAL", result["state"])
        self.assertEqual("READY_FOR_EXTERNAL_GATE", result["outputs"]["decision"])
        self.assertEqual("NOT_RUN", result["outputs"]["independent_verification"])
        self.assertEqual("NOT_RUN", result["outputs"]["independent_verifier_receipt"])
        self.assertEqual("NOT_CERTIFIED", result["outputs"]["production_certification"])

    def test_verification_rejects_self_verification_and_stale_fence_shape(self) -> None:
        request = {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "run_id": "run-a",
            "idempotency_key": "idem-v",
            "evidence_manifest_digest": DIGEST,
            "raw_evidence_digest": DIGEST,
            "independent_corpus_digest": DIGEST,
            "authorization_ref": "auth-a",
            "executor_id": "same-a",
            "verifier_id": "same-a",
            "verifier_scope": ["scope-a"],
            "fence": {"resource_id": "run-a", "epoch": 2, "holder_id": "same-a"},
        }
        with self.assertRaises(ContractError):
            prepare_independent_verification(request)
        request["verifier_id"] = "verifier-a"
        request["fence"] = {"resource_id": "other-run", "epoch": 2, "holder_id": "same-a"}
        with self.assertRaises(ContractError):
            prepare_independent_verification(request)


class CertificationReviewBoundaryTest(unittest.TestCase):
    def test_review_is_ready_only_for_external_gate_and_never_certified(self) -> None:
        result = prepare_certification_review(
            {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "run_id": "run-a",
                "idempotency_key": "idem-c",
                "gate_decision": "READY_FOR_EXTERNAL_GATE",
                "gate_report_digest": DIGEST,
                "project_manifest_digest": DIGEST,
                "evidence_manifest_digest": DIGEST,
                "independent_corpus_digest": DIGEST,
                "authorization_ref": "auth-a",
                "executor_id": "executor-a",
                "verifier_id": "verifier-a",
                "signer_id": "signer-a",
                "trust_store_digest": DIGEST,
                "fence": {"resource_id": "run-a", "epoch": 3, "holder_id": "executor-a"},
            }
        )
        self.assertEqual("SUCCEEDED", result["state"])
        outputs = result["outputs"]
        self.assertEqual("READY_FOR_EXTERNAL_GATE", outputs["decision"])
        self.assertEqual("NOT_RUN", outputs["external_validation"])
        self.assertEqual("NOT_RUN", outputs["independent_verification"])
        self.assertFalse(outputs["certified"])
        self.assertEqual("NOT_CERTIFIED", outputs["production_certification"])
        self.assertFalse(outputs["caller_certification_assertions_accepted"])

    def test_review_blocks_gate_failure_and_rejects_self_roles(self) -> None:
        request = {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "run_id": "run-a",
            "idempotency_key": "idem-c",
            "gate_decision": "BLOCKED",
            "gate_report_digest": DIGEST,
            "project_manifest_digest": DIGEST,
            "evidence_manifest_digest": DIGEST,
            "independent_corpus_digest": DIGEST,
            "authorization_ref": "auth-a",
            "executor_id": "executor-a",
            "verifier_id": "verifier-a",
            "signer_id": "signer-a",
            "trust_store_digest": DIGEST,
            "fence": {"resource_id": "run-a", "epoch": 3, "holder_id": "executor-a"},
        }
        result = prepare_certification_review(request)
        self.assertEqual("BLOCKED", result["state"])
        self.assertEqual("BLOCKED", result["outputs"]["decision"])
        request["signer_id"] = "verifier-a"
        with self.assertRaises(ContractError):
            prepare_certification_review(request)


if __name__ == "__main__":
    unittest.main()
