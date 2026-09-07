"""Real SQLite restart, migration, identity, tenant, and atomic audit regressions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from typing import Any

from elmos_foundry.artifacts import ContentAddressedArtifactStore
from elmos_foundry.asset_store import asset_payload, restore_asset
from elmos_foundry.authorizations import AuthorizationRequest
from elmos_foundry.canonical import canonical_digest, canonical_json
from elmos_foundry.dataset import DatasetFoundry
from elmos_foundry.domain import (
    ConsentStatus,
    ContentDigest,
    EvidenceState,
    GateLevel,
    KnowledgeObject,
    LifecycleState,
    ModelRelease,
    TenantScope,
)
from elmos_foundry.evidence import EvidenceLedger
from elmos_foundry.kernel import ExecutionKernel, KernelSecurityError, KernelStateError
from elmos_foundry.knowledge import KnowledgeManager
from elmos_foundry.memory import ExperienceMemoryStore
from elmos_foundry.model import ModelFoundry
from elmos_foundry.serving import ModelServingGateway
from elmos_foundry.store import (
    FoundryStore,
    IdempotencyConflict,
    RecordConflict,
    StoreIntegrityError,
    StoreSecurityError,
    _ASSET_DDL,
    _V1_SCHEMA,
    _V1_SCHEMA_DIGEST,
    _V1_VERSION,
)


def digest(value: str) -> str:
    return canonical_digest({"fixture": value})


def authorize(request: AuthorizationRequest, scope: TenantScope) -> bool:
    return (
        request.context_digest == scope.binding_digest
        and request.tenant_id == scope.tenant_id
        and request.project_id == scope.project_id
    )


class DurableAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "assets.sqlite3"
        self.now = [2_000_000_000.0]
        self.kernel = ExecutionKernel(clock=lambda: self.now[0])
        self.capabilities = tuple(
            sorted(
                {
                    "foundry.knowledge.ingest",
                    "foundry.knowledge.read",
                    "foundry.experience.capture",
                    "foundry.experience.read",
                    "foundry.dataset.create",
                    "foundry.dataset.read",
                    "foundry.dataset.quarantine",
                    "foundry.model.package",
                    "foundry.model.read",
                    "foundry.model.promote",
                    "foundry.serving.route",
                    "foundry.serving.health",
                    "foundry.evidence.read",
                    "foundry.evidence.write",
                    "foundry.artifact.read",
                    "foundry.artifact.write",
                    "foundry.store.read",
                    "foundry.store.write",
                }
            )
        )
        self.scope = self.mint("tenant-a", "project-a")
        self.other_project = self.mint("tenant-a", "project-b")
        self.other_tenant = self.mint("tenant-b", "project-a")
        self.store = self.open_store()

    def mint(self, tenant: str, project: str) -> TenantScope:
        return self.kernel.mint_context(
            tenant_id=tenant,
            project_id=project,
            actor_id="actor",
            environment_id="local-test",
            workspace_digest=digest("workspace"),
            revision_set_id=digest("revision"),
            purpose="durability-test",
            capabilities=self.capabilities,
            ttl_seconds=600,
        )

    def open_store(self) -> FoundryStore:
        result = FoundryStore(
            self.path, context_verifier=self.kernel.require_context, clock=lambda: self.now[0]
        )
        self.addCleanup(result.close)
        return result

    def restart(self) -> None:
        self.store.close()
        self.store = self.open_store()

    def test_knowledge_restart_metadata_identity_and_scoped_pagination(self) -> None:
        manager = KnowledgeManager(self.kernel, store=self.store)
        obj = manager.ingest_document(
            "source", "text", "raw-secret-not-stored", tenant_scope=self.scope
        )
        restricted = manager.ingest_document(
            "source",
            "text",
            "raw-secret-not-stored",
            confidentiality="restricted",
            tenant_scope=self.scope,
        )
        self.assertNotEqual(obj.object_id, restricted.object_id)
        manager.ingest_document(
            "source-other", "binary", b"untrusted bytes", tenant_scope=self.scope
        )
        self.restart()
        manager = KnowledgeManager(self.kernel, store=self.store)
        recovered = manager.get_object(obj.object_id, self.scope)
        self.assertEqual(recovered, obj)
        retry = manager.ingest_document(
            "source", "text", "raw-secret-not-stored", tenant_scope=self.scope
        )
        self.assertEqual(retry.created_at, obj.created_at)
        for other in (self.other_project, self.other_tenant):
            self.assertIsNone(manager.get_object(obj.object_id, other))
            self.assertEqual(manager.query_objects(tenant_scope=other), ())
        first = manager.query_objects(object_type="text", tenant_scope=self.scope, limit=1)
        second = manager.query_objects(
            object_type="text", tenant_scope=self.scope, limit=1, after_id=first[0].object_id
        )
        self.assertEqual(
            {first[0].object_id, second[0].object_id}, {obj.object_id, restricted.object_id}
        )
        self.assertNotIn(b"raw-secret-not-stored", self.path.read_bytes())
        with self.assertRaises(KernelSecurityError):
            manager.get_object(obj.object_id, TenantScope("tenant-a", "project-a"))

    def episode(self) -> Any:
        return ExperienceMemoryStore(
            self.kernel, store=self.store, capture_verifier=authorize
        ).capture_episode(
            "repair",
            "repair token=private-goal",
            ({"password": "private-pass", "action": "inspect"},),
            {"result": "fixed", "api_key": "private-key"},
            0.9,
            tenant_scope=self.scope,
            capture_authorization_digest=digest("capture"),
        )

    def test_experience_restart_redaction_and_retry(self) -> None:
        episode = self.episode()
        self.restart()
        memory = ExperienceMemoryStore(self.kernel, store=self.store, capture_verifier=authorize)
        self.assertEqual(memory.get_episode(episode.episode_id, self.scope), episode)
        self.assertEqual(self.episode().created_at, episode.created_at)
        self.assertEqual(len(memory.query_high_reward_episodes(tenant_scope=self.scope)), 1)
        self.assertEqual(memory.query_high_reward_episodes(tenant_scope=self.other_project), ())
        for secret in (b"private-goal", b"private-pass", b"private-key"):
            self.assertNotIn(secret, self.path.read_bytes())

    def test_dataset_quarantine_survives_restart_and_creation_retry(self) -> None:
        episode = self.episode()
        episodes = (episode, replace(episode, episode_id="ep-second"))
        foundry = DatasetFoundry(self.kernel, store=self.store, data_use_verifier=authorize)
        params: dict[str, Any] = {
            "training_consent": ConsentStatus.ALLOW,
            "tenant_scope": self.scope,
            "data_use_authorization_digest": digest("data-use"),
        }
        dataset = foundry.create_dataset_from_episodes("training", episodes, **params)
        first = foundry.get_dataset_items(dataset, tenant_scope=self.scope, limit=1)[0]
        second = foundry.get_dataset_items(
            dataset, tenant_scope=self.scope, limit=1, after_id=first.item_id
        )[0]
        self.assertNotEqual(first.item_id, second.item_id)
        self.assertFalse(foundry.quarantine_item(first.item_id, self.other_project))
        self.assertTrue(foundry.quarantine_item(first.item_id, self.scope))
        self.restart()
        foundry = DatasetFoundry(self.kernel, store=self.store, data_use_verifier=authorize)
        self.assertEqual(
            foundry.create_dataset_from_episodes("training", episodes, **params), dataset
        )
        visible = foundry.get_dataset_items(dataset, tenant_scope=self.scope)
        self.assertEqual([item.item_id for item in visible], [second.item_id])
        self.assertTrue(foundry.quarantine_item(first.item_id, self.scope))
        self.assertEqual(len(self.store.list_events(self.scope, first.item_id)), 1)
        self.assertTrue(self.store.verify_event_chain(self.scope, first.item_id))
        self.assertEqual(foundry.get_dataset_items(dataset, tenant_scope=self.other_tenant), ())
        with self.assertRaises(ValueError):
            foundry.create_dataset_from_episodes("training", (episode, episode), **params)

    def test_process_local_dataset_retry_also_preserves_quarantine(self) -> None:
        foundry = DatasetFoundry(self.kernel, data_use_verifier=authorize)
        episodes = (self.episode(),)
        params: dict[str, Any] = {
            "training_consent": ConsentStatus.ALLOW,
            "tenant_scope": self.scope,
            "data_use_authorization_digest": digest("data-use"),
        }
        dataset = foundry.create_dataset_from_episodes("training", episodes, **params)
        item = foundry.get_dataset_items(dataset, tenant_scope=self.scope)[0]
        foundry.quarantine_item(item.item_id, self.scope)
        foundry.create_dataset_from_episodes("training", episodes, **params)
        self.assertEqual(foundry.get_dataset_items(dataset, tenant_scope=self.scope), ())

    def test_model_promotion_is_atomic_and_recovers_with_its_audit(self) -> None:
        artifacts = ContentAddressedArtifactStore(
            self.root / "artifacts", context_verifier=self.kernel.require_context
        )
        ledger = EvidenceLedger(self.kernel, store=self.store, artifact_store=artifacts)
        foundry = ModelFoundry(
            self.kernel, store=self.store, evidence_ledger=ledger, promotion_verifier=authorize
        )
        args = (
            "base",
            "adapter",
            "1.0",
            ("skill-a",),
            ContentDigest.parse(digest("weights")),
            digest("knowledge"),
            digest("policy"),
        )
        release = foundry.package_release(*args, tenant_scope=self.scope)
        bundle = ledger.seal_evidence_bundle(
            release.release_id,
            "model_release",
            GateLevel.E1_UNIT_EVAL,
            "PASS",
            ({"name": "unit-eval", "status": "SATISFIED_LOCAL"},),
            {"unit_eval_score": 0.93},
            self.scope,
        )
        params = {
            "evidence_bundle_id": bundle.bundle_id,
            "promotion_authorization_digest": digest("promotion"),
        }
        with patch.object(self.store, "_append_event", side_effect=RuntimeError("audit failed")):
            with self.assertRaisesRegex(RuntimeError, "audit failed"):
                foundry.promote_release(
                    release.release_id, GateLevel.E1_UNIT_EVAL, self.scope, **params
                )
        self.assertEqual(foundry.get_release(release.release_id, self.scope), release)
        self.assertEqual(self.store.list_events(self.scope, release.release_id), ())
        promoted = foundry.promote_release(
            release.release_id, GateLevel.E1_UNIT_EVAL, self.scope, **params
        )
        self.restart()
        foundry = ModelFoundry(self.kernel, store=self.store)
        self.assertEqual(foundry.get_release(release.release_id, self.scope), promoted)
        self.assertEqual(foundry.package_release(*args, tenant_scope=self.scope), promoted)
        self.assertIsNone(foundry.get_release(release.release_id, self.other_project))
        events = self.store.list_events(self.scope, release.release_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].payload["details"]["evidence_bundle_digest"], bundle.bundle_digest
        )
        self.assertTrue(self.store.verify_event_chain(self.scope, release.release_id))

    def test_serving_availability_expires_and_restart_fences_old_observations(self) -> None:
        candidate = {
            "candidate_id": "candidate",
            "provider_instance_id": "provider",
            "model_version": "v1",
            "artifact_digest": digest("artifact"),
            "quality_score": 0.9,
            "estimated_cost_usd": 0.1,
            "estimated_latency_ms": 10,
            "availability_status": "VERIFIED_CURRENT",
        }

        def gateway() -> ModelServingGateway:
            return ModelServingGateway(
                self.kernel,
                store=self.store,
                route_verifier=authorize,
                clock=lambda: self.now[0],
                health_ttl_seconds=10,
            )

        def route(target: ModelServingGateway) -> str:
            return str(
                target.route_inference(
                    digest("request"),
                    (candidate,),
                    max_cost_usd=1,
                    max_latency_ms=20,
                    verification_receipt_digest=digest("verified"),
                    tenant_scope=self.scope,
                )["status"]
            )

        first = gateway()
        first.record_success("candidate", self.scope)
        self.assertEqual(route(first), "READY_FOR_EXTERNAL_GATE")
        self.now[0] += 10
        self.assertEqual(route(first), "BLOCKED")
        first.record_success("candidate", self.scope)
        self.restart()
        second = gateway()
        self.assertEqual(route(second), "BLOCKED")
        second.record_success("candidate", self.scope)
        self.assertEqual(route(second), "READY_FOR_EXTERNAL_GATE")
        second.record_failure("candidate", self.scope)
        self.assertEqual(route(second), "BLOCKED")
        self.now[0] -= 1
        self.assertEqual(route(second), "BLOCKED")

    def test_atomic_identity_collision_and_cas_across_two_connections(self) -> None:
        payload = {
            "tenant_id": self.scope.tenant_id,
            "project_id": self.scope.project_id,
            "value": 1,
            "candidate_id": "candidate",
        }
        asset = ("health", "candidate", "", digest("identity"), payload)
        original = self.store.create_assets(self.scope, (asset,))[0]
        second = self.open_store()
        updated = {**payload, "value": 2}
        self.store.update_asset(
            self.scope,
            "health",
            "candidate",
            original.revision,
            updated,
            event_type="health.changed",
            event_payload={},
        )
        with self.assertRaises(RecordConflict):
            second.update_asset(
                self.scope,
                "health",
                "candidate",
                original.revision,
                payload,
                event_type="health.changed",
                event_payload={},
            )
        self.assertEqual(second.create_assets(self.scope, (asset,))[0].payload, updated)
        with self.assertRaises(IdempotencyConflict):
            second.create_assets(
                self.scope,
                (
                    ("health", "new", "", digest("new"), {**payload, "candidate_id": "new"}),
                    ("health", "candidate", "", digest("identity"), updated),
                ),
            )
        self.assertIsNone(self.store.get_asset(self.scope, "health", "new"))
        self.assertEqual(len(self.store.list_events(self.scope, "candidate")), 1)
        with self.assertRaises(StoreSecurityError):
            self.store.create_assets(self.other_project, (asset,))
        with self.assertRaises(ValueError):
            self.store.query_assets(self.scope, "health", limit=True)

    def test_asset_tampering_and_revocation_fail_closed(self) -> None:
        manager = KnowledgeManager(self.kernel, store=self.store)
        obj = manager.ingest_document("source", "text", "body", tenant_scope=self.scope)
        self.store._connection.execute(
            "UPDATE foundry_assets SET revision=revision+1,payload_json=? WHERE asset_id=?",
            (canonical_json({"tenant_id": "tenant-a", "project_id": "project-a"}), obj.object_id),
        )
        with self.assertRaises(StoreIntegrityError):
            manager.get_object(obj.object_id, self.scope)
        self.kernel.revoke_lease(self.scope.lease_id)
        with self.assertRaises(StoreSecurityError):
            self.store.query_assets(self.scope, "knowledge")

    def test_local_asset_codecs_reject_fabricated_high_evidence_and_gate_states(self) -> None:
        manager = KnowledgeManager(self.kernel, store=self.store)
        obj = manager.ingest_document("source", "text", "body", tenant_scope=self.scope)
        with self.assertRaises(StoreIntegrityError):
            restore_asset(
                KnowledgeObject,
                {**asset_payload(obj), "evidence_state": EvidenceState.VERIFIED_INDEPENDENT},
            )
        foundry = ModelFoundry(self.kernel, store=self.store)
        args = (
            "base",
            "adapter",
            "1",
            ("skill",),
            ContentDigest.parse(digest("weights")),
            digest("knowledge"),
            digest("policy"),
        )
        release = foundry.package_release(*args, tenant_scope=self.scope)
        with self.assertRaises(KernelStateError):
            foundry.package_release(
                *args, gate_level=GateLevel.E1_UNIT_EVAL, tenant_scope=self.scope
            )
        for changed in (
            {"gate_level": GateLevel.E5_FORMAL_PROVEN},
            {"gate_level": GateLevel.E1_UNIT_EVAL},
            {"status": LifecycleState.CERTIFIED},
            {"evidence_state": EvidenceState.VERIFIED_INDEPENDENT},
            {"external_evidence_status": "VERIFIED"},
        ):
            with self.subTest(changed=changed), self.assertRaises(StoreIntegrityError):
                restore_asset(ModelRelease, {**asset_payload(release), **changed})
        forged = {
            **asset_payload(release),
            "release_id": "rel-forged",
            "gate_level": GateLevel.E1_UNIT_EVAL,
            "status": LifecycleState.VERIFYING,
        }
        with self.assertRaises(StoreIntegrityError):
            self.store.create_assets(
                self.scope, (("model", "rel-forged", "", digest("forged"), forged),)
            )

    def test_public_generic_store_cannot_rewrite_consent_or_promote_model(self) -> None:
        manager = KnowledgeManager(self.kernel, store=self.store)
        obj = manager.ingest_document("source", "text", "body", tenant_scope=self.scope)
        foundry = ModelFoundry(self.kernel, store=self.store)
        release = foundry.package_release(
            "base",
            "adapter",
            "1",
            ("skill",),
            ContentDigest.parse(digest("weights")),
            digest("knowledge"),
            digest("policy"),
            tenant_scope=self.scope,
        )
        store_only = self.kernel.mint_context(
            tenant_id=self.scope.tenant_id,
            project_id=self.scope.project_id,
            actor_id="store-only",
            environment_id="local-test",
            workspace_digest=digest("workspace"),
            revision_set_id=digest("revision"),
            purpose="durability-test",
            capabilities=("foundry.store.read", "foundry.store.write"),
            ttl_seconds=600,
        )
        for scope in (store_only, self.scope):
            with self.subTest(scope=scope.actor_id):
                with self.assertRaises(RecordConflict):
                    self.store.update_asset(
                        scope,
                        "knowledge",
                        obj.object_id,
                        1,
                        {**asset_payload(obj), "training_consent": ConsentStatus.ALLOW},
                        event_type="forged",
                        event_payload={},
                    )
                with self.assertRaises(StoreSecurityError):
                    self.store.update_asset(
                        scope,
                        "model",
                        release.release_id,
                        1,
                        {
                            **asset_payload(release),
                            "gate_level": GateLevel.E1_UNIT_EVAL,
                            "status": LifecycleState.VERIFYING,
                        },
                        event_type="forged",
                        event_payload={},
                    )
        self.assertEqual(manager.get_object(obj.object_id, self.scope), obj)
        self.assertEqual(foundry.get_release(release.release_id, self.scope), release)

    def test_public_asset_creation_cannot_fabricate_governed_authorization(self) -> None:
        manager = KnowledgeManager(self.kernel, store=self.store, consent_verifier=authorize)
        knowledge = manager.ingest_document(
            "allowed",
            "text",
            "body",
            training_consent=ConsentStatus.ALLOW,
            tenant_scope=self.scope,
            consent_receipt_digest=digest("consent"),
        )
        self.assertEqual(manager.get_object(knowledge.object_id, self.scope), knowledge)
        episode = self.episode()
        forged_knowledge = {**asset_payload(knowledge), "object_id": "ko-forged"}
        forged_episode = {**asset_payload(episode), "episode_id": "ep-forged"}
        manifest = {
            "tenant_id": self.scope.tenant_id,
            "project_id": self.scope.project_id,
            "dataset_id": "ds-forged",
        }
        for asset in (
            ("knowledge", "ko-forged", "", digest("forged"), forged_knowledge),
            ("experience", "ep-forged", "", digest("forged"), forged_episode),
            ("dataset", "ds-forged", "", digest("forged"), manifest),
            ("dataset_item", "di-forged", "ds-forged", digest("forged"), manifest),
        ):
            with self.subTest(kind=asset[0]), self.assertRaises(StoreSecurityError):
                self.store.create_assets(self.scope, (asset,))
            self.assertIsNone(self.store.get_asset(self.scope, asset[0], asset[1]))

    def test_asset_identity_substitution_rejected_even_with_matching_payload_digest(self) -> None:
        manager = KnowledgeManager(self.kernel, store=self.store)
        obj = manager.ingest_document("source", "text", "body", tenant_scope=self.scope)
        substituted = {**asset_payload(obj), "object_id": "ko-substituted"}
        with self.assertRaises(StoreIntegrityError):
            self.store.create_assets(
                self.scope,
                (
                    (
                        "knowledge",
                        "ko-new",
                        "",
                        digest("substitute"),
                        substituted,
                    ),
                ),
            )
        self.store._connection.execute(
            "UPDATE foundry_assets SET revision=revision+1,payload_json=?,payload_digest=? WHERE asset_id=?",
            (canonical_json(substituted), canonical_digest(substituted), obj.object_id),
        )
        with self.assertRaises(StoreIntegrityError):
            manager.get_object(obj.object_id, self.scope)

    def legacy_store(self, *, corrupt_metadata: bool = False) -> Path:
        path = self.root / "legacy.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.executescript(_V1_SCHEMA)
            connection.execute(
                "INSERT INTO foundry_schema_metadata VALUES(1,?,?)",
                (_V1_VERSION, "invalid" if corrupt_metadata else _V1_SCHEMA_DIGEST),
            )
            request = {"legacy": True}
            connection.execute(
                "INSERT INTO foundry_runs VALUES(?,?,?,?,?,?,?,?,NULL,?,?,?)",
                (
                    self.scope.tenant_id,
                    self.scope.project_id,
                    "legacy-run",
                    "operation",
                    "idem",
                    canonical_json(request),
                    canonical_digest(request),
                    "PENDING",
                    "then",
                    "then",
                    self.scope.binding_digest,
                ),
            )
        return path

    def test_exact_v1_migration_preserves_existing_runs(self) -> None:
        path = self.legacy_store()
        with FoundryStore(path, context_verifier=self.kernel.require_context) as migrated:
            self.assertEqual(migrated.get_run(self.scope, "legacy-run").request, {"legacy": True})
            self.assertEqual(migrated.query_assets(self.scope, "knowledge"), ())
            self.assertEqual(migrated.persistence_mode, "SQLITE_DURABLE")
        with FoundryStore(path, context_verifier=self.kernel.require_context) as reopened:
            self.assertEqual(reopened.get_run(self.scope, "legacy-run").state, "PENDING")

    def test_invalid_v1_metadata_does_not_mutate_legacy_schema(self) -> None:
        path = self.legacy_store(corrupt_metadata=True)
        with self.assertRaises(StoreIntegrityError):
            FoundryStore(path, context_verifier=self.kernel.require_context)
        with sqlite3.connect(path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM sqlite_master WHERE name='foundry_assets'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute("SELECT count(*) FROM foundry_runs").fetchone()[0], 1
            )

    def test_failed_schema_upgrade_rolls_back_created_tables(self) -> None:
        path = self.legacy_store()
        with patch("elmos_foundry.store._ASSET_DDL", (_ASSET_DDL[0], "INVALID SQL")):
            with self.assertRaises(sqlite3.OperationalError):
                FoundryStore(path, context_verifier=self.kernel.require_context)
        with sqlite3.connect(path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM sqlite_master WHERE name='foundry_assets'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute("SELECT schema_version FROM foundry_schema_metadata").fetchone()[
                    0
                ],
                _V1_VERSION,
            )
        with FoundryStore(path, context_verifier=self.kernel.require_context) as migrated:
            self.assertEqual(migrated.get_run(self.scope, "legacy-run").state, "PENDING")

    def test_invalid_wal_database_rejected_without_persistent_journal_mutation(self) -> None:
        path = self.legacy_store(corrupt_metadata=True)
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        before = path.read_bytes()
        with self.assertRaises(StoreIntegrityError):
            FoundryStore(path, context_verifier=self.kernel.require_context)
        self.assertEqual(path.read_bytes(), before)
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")


if __name__ == "__main__":
    unittest.main()
