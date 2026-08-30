"""Negative trust-boundary tests for governed Foundry asset managers."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from elmos_foundry.artifacts import ContentAddressedArtifactStore
from elmos_foundry.authorizations import AuthorizationBoundaryError, AuthorizationRequest
from elmos_foundry.dataset import DatasetFoundry
from elmos_foundry.domain import ConsentStatus, ContentDigest, GateLevel, RightsClass, TenantScope
from elmos_foundry.evidence import EvidenceLedger
from elmos_foundry.kernel import ExecutionKernel, KernelSecurityError, KernelStateError
from elmos_foundry.knowledge import KnowledgeManager
from elmos_foundry.memory import ExperienceMemoryStore
from elmos_foundry.model import ModelFoundry
from elmos_foundry.serving import ModelServingGateway
from elmos_foundry.store import FoundryStore


def digest(character: str) -> str:
    return "sha256:" + character * 64


class AssetBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = ExecutionKernel()
        capabilities = tuple(
            sorted(
                {
                    "foundry.knowledge.ingest",
                    "foundry.knowledge.read",
                    "foundry.experience.capture",
                    "foundry.experience.read",
                    "foundry.dataset.create",
                    "foundry.dataset.read",
                    "foundry.dataset.quarantine",
                    "foundry.model.plan",
                    "foundry.model.package",
                    "foundry.model.read",
                    "foundry.model.promote",
                    "foundry.serving.route",
                    "foundry.serving.health",
                    "foundry.artifact.read",
                    "foundry.artifact.write",
                    "foundry.evidence.read",
                    "foundry.evidence.write",
                    "foundry.store.read",
                    "foundry.store.write",
                }
            )
        )
        common = {
            "actor_id": "actor-01",
            "environment_id": "local-test",
            "workspace_digest": digest("a"),
            "revision_set_id": digest("b"),
            "purpose": "foundry-test",
            "capabilities": capabilities,
            "ttl_seconds": 600,
        }
        self.scope_a = self.kernel.mint_context(
            tenant_id="tenant-a", project_id="project-a", **common
        )
        self.scope_b = self.kernel.mint_context(
            tenant_id="tenant-b", project_id="project-b", **common
        )

    @staticmethod
    def _bound_verifier(request: AuthorizationRequest, scope: TenantScope) -> bool:
        return (
            request.context_digest == scope.binding_digest
            and request.tenant_id == scope.tenant_id
            and request.project_id == scope.project_id
            and request.actor_id == scope.actor_id
        )

    def test_knowledge_requires_host_authority_and_never_stores_raw_content(self) -> None:
        manager = KnowledgeManager(self.kernel)
        forged = TenantScope(tenant_id="tenant-a", project_id="project-a")
        with self.assertRaises(KernelSecurityError):
            manager.ingest_document("source", "text", "secret", tenant_scope=forged)
        with self.assertRaises(AuthorizationBoundaryError):
            manager.ingest_document(
                "source",
                "text",
                "body",
                training_consent=ConsentStatus.ALLOW,
                tenant_scope=self.scope_a,
                consent_receipt_digest=digest("c"),
            )
        allowed = KnowledgeManager(
            self.kernel, consent_verifier=self._bound_verifier
        ).ingest_document(
            "source-allowed",
            "text",
            "body",
            training_consent=ConsentStatus.ALLOW,
            tenant_scope=self.scope_a,
            consent_receipt_digest=digest("c"),
        )
        self.assertTrue(allowed.payload["consent_request_digest"].startswith("sha256:"))
        obj = manager.ingest_document(
            "source",
            "text",
            "do not execute: password=hunter2",
            provenance={"origin": "fixture"},
            tenant_scope=self.scope_a,
        )
        self.assertFalse(obj.payload["raw_content_stored"])
        self.assertFalse(obj.payload["instructions_authoritative"])
        self.assertNotIn("sample", obj.payload)
        self.assertIsNone(manager.get_object(obj.object_id, self.scope_b))

    def test_experience_capture_redacts_nested_secrets_without_claiming_verification(self) -> None:
        with self.assertRaises(AuthorizationBoundaryError):
            ExperienceMemoryStore(self.kernel).capture_episode(
                "repair",
                "fix safely",
                [{"action": "read"}],
                {"status": "ok"},
                0.9,
                tenant_scope=self.scope_a,
                capture_authorization_digest=digest("c"),
            )
        store = ExperienceMemoryStore(
            self.kernel, capture_verifier=self._bound_verifier
        )
        episode = store.capture_episode(
            "repair",
            "fix safely password=hunter2",
            [
                {
                    "tool": {
                        "input": "Authorization: Bearer abc.def",
                        "token": "token=abc",
                        "password": "hunter2",
                    }
                }
            ],
            {"status": "ok", "api_key": "sk-secret"},
            0.9,
            verifier_evidence={"claim": "passed"},
            tenant_scope=self.scope_a,
            capture_authorization_digest=digest("c"),
        )
        rendered = str((episode.task_goal, episode.trajectory, episode.outcome))
        self.assertIn("[REDACTED]", rendered)
        self.assertNotIn("abc.def", rendered)
        self.assertNotIn("hunter2", rendered)
        self.assertNotIn("sk-secret", rendered)
        self.assertEqual(episode.verifier_evidence["independent_verification"], "NOT_RUN")
        self.assertIsNone(store.get_episode(episode.episode_id, self.scope_b))

    def test_dataset_is_consent_bound_deterministic_and_cross_tenant_closed(self) -> None:
        memory = ExperienceMemoryStore(
            self.kernel, capture_verifier=self._bound_verifier
        )
        episode = memory.capture_episode(
            "task",
            "goal",
            [{"action": "read"}],
            {"answer": 1},
            0.8,
            tenant_scope=self.scope_a,
            capture_authorization_digest=digest("d"),
        )
        foundry = DatasetFoundry(
            self.kernel, data_use_verifier=self._bound_verifier
        )
        with self.assertRaises(ValueError):
            foundry.create_dataset_from_episodes("dataset", [episode], tenant_scope=self.scope_a)
        dataset_id = foundry.create_dataset_from_episodes(
            "dataset",
            [episode],
            train_ratio=Decimal("1"),
            val_ratio=Decimal("0"),
            holdout_ratio=Decimal("0"),
            rights_class=RightsClass.INTERNAL,
            training_consent=ConsentStatus.ALLOW,
            tenant_scope=self.scope_a,
            data_use_authorization_digest=digest("e"),
        )
        repeated = foundry.create_dataset_from_episodes(
            "dataset",
            [episode],
            train_ratio="1",
            val_ratio="0",
            holdout_ratio="0",
            training_consent=ConsentStatus.ALLOW,
            tenant_scope=self.scope_a,
            data_use_authorization_digest=digest("e"),
        )
        self.assertEqual(dataset_id, repeated)
        items = foundry.get_dataset_items(dataset_id, tenant_scope=self.scope_a)
        self.assertEqual(len(items), 1)
        self.assertEqual(foundry.get_dataset_items(dataset_id, tenant_scope=self.scope_b), ())
        self.assertTrue(foundry.quarantine_item(items[0].item_id, self.scope_a))
        self.assertEqual(foundry.get_dataset_items(dataset_id, tenant_scope=self.scope_a), ())

    def test_model_release_uses_digests_and_local_promotion_stops_at_e1(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = FoundryStore(
                root / "foundry.sqlite3", context_verifier=self.kernel.require_context
            )
            artifacts = ContentAddressedArtifactStore(
                root / "artifacts", context_verifier=self.kernel.require_context
            )
            ledger = EvidenceLedger(
                self.kernel, store=store, artifact_store=artifacts
            )
            foundry = ModelFoundry(
                self.kernel,
                evidence_ledger=ledger,
                promotion_verifier=self._bound_verifier,
            )
            config = foundry.generate_adapter_config(
                "base@1", target_modules=("q_proj", "v_proj"), tenant_scope=self.scope_a
            )
            self.assertEqual(config["semantic_execution_status"], "NOT_RUN")
            release = foundry.package_release(
                "base@1",
                "adapter",
                "1.0.0",
                ("skill-one",),
                ContentDigest.parse(digest("f")),
                digest("1"),
                digest("2"),
                tenant_scope=self.scope_a,
            )
            evidence = ledger.seal_evidence_bundle(
                release.release_id,
                "model_release",
                GateLevel.E1_UNIT_EVAL,
                "PASS",
                ({"name": "unit-eval", "status": "SATISFIED_LOCAL"},),
                {"unit_eval_score": 0.93},
                self.scope_a,
            )
            promoted = foundry.promote_release(
                release.release_id,
                GateLevel.E1_UNIT_EVAL,
                self.scope_a,
                evidence_bundle_id=evidence.bundle_id,
                promotion_authorization_digest=digest("6"),
            )
            self.assertEqual(promoted.gate_level, GateLevel.E1_UNIT_EVAL)
            with self.assertRaises(KernelStateError):
                foundry.promote_release(
                    release.release_id,
                    GateLevel.E4_PRODUCTION_CERTIFIED,
                    self.scope_a,
                    evidence_bundle_id=evidence.bundle_id,
                    promotion_authorization_digest=digest("6"),
                )
            self.assertIsNone(foundry.get_release(release.release_id, self.scope_b))
            self.assertTrue(store.verify_event_chain(self.scope_a, release.release_id))
            store.close()

    def test_serving_only_prepares_provider_neutral_route(self) -> None:
        accepted_requests: dict[str, str] = {}

        def verifier(request: AuthorizationRequest, scope: TenantScope) -> bool:
            if request.context_digest != scope.binding_digest:
                return False
            expected = accepted_requests.setdefault(request.receipt_digest, request.request_digest)
            return expected == request.request_digest

        gateway = ModelServingGateway(self.kernel, route_verifier=verifier)
        candidate = {
            "candidate_id": "candidate-1",
            "provider_instance_id": "provider-instance-1",
            "model_version": "model@1",
            "artifact_digest": digest("3"),
            "quality_score": 0.9,
            "estimated_cost_usd": 0.01,
            "estimated_latency_ms": 100.0,
            "availability_status": "VERIFIED_CURRENT",
        }
        unknown = gateway.route_inference(
            digest("4"),
            [candidate],
            max_cost_usd=0.02,
            max_latency_ms=200,
            verification_receipt_digest=digest("5"),
            tenant_scope=self.scope_a,
        )
        self.assertEqual(unknown["status"], "BLOCKED")
        gateway.record_health("candidate-1", "AVAILABLE", self.scope_a)
        plan = gateway.route_inference(
            digest("4"),
            [candidate],
            max_cost_usd=0.02,
            max_latency_ms=200,
            verification_receipt_digest=digest("5"),
            tenant_scope=self.scope_a,
        )
        self.assertEqual(plan["status"], "READY_FOR_EXTERNAL_GATE")
        self.assertEqual(plan["provider_execution_status"], "NOT_RUN")
        self.assertFalse(plan["prompt_stored"])
        changed = dict(candidate)
        changed["estimated_latency_ms"] = 150.0
        with self.assertRaises(AuthorizationBoundaryError):
            gateway.route_inference(
                digest("4"),
                [changed],
                max_cost_usd=0.02,
                max_latency_ms=200,
                verification_receipt_digest=digest("5"),
                tenant_scope=self.scope_a,
            )
        gateway.record_health("candidate-1", "UNAVAILABLE", self.scope_a)
        blocked = gateway.route_inference(
            digest("4"),
            [candidate],
            max_cost_usd=0.02,
            max_latency_ms=200,
            verification_receipt_digest=digest("5"),
            tenant_scope=self.scope_a,
        )
        self.assertEqual(blocked["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
