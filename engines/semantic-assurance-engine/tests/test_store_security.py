"""Durability, idempotency, integrity and tenant-isolation tests."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from elmos_semantic_assurance.canonical import canonical_json, digest_value
from elmos_semantic_assurance.contracts import ArtifactRecord, AssuranceScope
from elmos_semantic_assurance.store import (
    IdempotencyConflict,
    SemanticAssuranceStore,
    StoreError,
)

import sys

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from fixtures import make_scope


def _artifact(path: str, content: dict[str, object]) -> ArtifactRecord:
    encoded = canonical_json(content)
    return ArtifactRecord(
        logical_path=path,
        media_type="application/json",
        content_digest=digest_value(content),
        byte_count=len(encoded),
    )


def _other_scope(scope: AssuranceScope, *, tenant: str, project: str) -> AssuranceScope:
    values = {
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "run_id": scope.run_id,
        "snapshot_id": scope.snapshot_id,
        "snapshot_digest": scope.snapshot_digest,
        "source_digest": scope.source_digest,
        "target_digest": scope.target_digest,
        "environment_digest": scope.environment_digest,
        "semantic_profile_digest": scope.semantic_profile_digest,
        "toolchain_digest": scope.toolchain_digest,
        "corpus_digest": scope.corpus_digest,
        "assumptions_digest": scope.assumptions_digest,
        "route_id": scope.route_id,
        "source_technology": scope.source_technology,
        "source_dialect": scope.source_dialect,
        "source_runtime": scope.source_runtime,
        "target_technology": scope.target_technology,
        "target_dialect": scope.target_dialect,
        "target_runtime": scope.target_runtime,
    }
    values.update(tenant_id=tenant, project_id=project)
    return AssuranceScope(**values)


class TestStoreSecurity(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SemanticAssuranceStore()
        self.scope = make_scope()
        self.addCleanup(self.store.close)

    def test_idempotent_completion_replays_exact_response(self) -> None:
        request_digest = digest_value({"request": 1})
        response = {"executionStatus": "LOCAL_EXECUTED", "result": {"count": 1}}
        content = {"kind": "semantic-model", "nodes": ["a", "b"]}
        artifact = _artifact("semantic-assurance/model.json", content)

        first = self.store.complete(
            self.scope,
            "elmos-syntax-tree-normalizer",
            "idem-001",
            "subject-001",
            request_digest,
            response,
            ((artifact, content),),
        )
        replay = self.store.replay(
            self.scope,
            "elmos-syntax-tree-normalizer",
            "idem-001",
            request_digest,
        )
        second = self.store.complete(
            self.scope,
            "elmos-syntax-tree-normalizer",
            "idem-001",
            "subject-001",
            request_digest,
            {"ignored": "a replay cannot replace the response"},
            (),
        )

        self.assertEqual(first, response)
        self.assertEqual(replay, response)
        self.assertEqual(second, response)
        self.assertEqual(
            self.store.artifact(
                self.scope,
                "elmos-syntax-tree-normalizer",
                artifact.logical_path,
            ),
            content,
        )

    def test_idempotency_key_conflict_fails_closed(self) -> None:
        self.store.complete(
            self.scope,
            "elmos-syntax-tree-normalizer",
            "idem-conflict",
            "subject-001",
            digest_value({"request": 1}),
            {"result": "first"},
            (),
        )

        with self.assertRaisesRegex(IdempotencyConflict, "different request digest"):
            self.store.replay(
                self.scope,
                "elmos-syntax-tree-normalizer",
                "idem-conflict",
                digest_value({"request": 2}),
            )

    def test_artifacts_and_idempotency_are_tenant_project_scoped(self) -> None:
        content = {"tenantBound": True}
        artifact = _artifact("semantic-assurance/scoped.json", content)
        request_digest = digest_value({"request": "tenant-a"})
        self.store.complete(
            self.scope,
            "elmos-syntax-tree-normalizer",
            "idem-shared-name",
            "subject-001",
            request_digest,
            {"tenant": "a"},
            ((artifact, content),),
        )
        other = _other_scope(self.scope, tenant="tenant-b", project="project-b")

        self.assertIsNone(
            self.store.replay(
                other,
                "elmos-syntax-tree-normalizer",
                "idem-shared-name",
                request_digest,
            )
        )
        with self.assertRaisesRegex(StoreError, "unknown scoped artifact"):
            self.store.artifact(
                other,
                "elmos-syntax-tree-normalizer",
                artifact.logical_path,
            )

    def test_artifact_digest_tampering_is_detected(self) -> None:
        content = {"verified": True}
        artifact = _artifact("semantic-assurance/evidence.json", content)
        self.store.complete(
            self.scope,
            "elmos-semantic-diff-engine",
            "idem-artifact",
            "subject-001",
            digest_value({"request": "artifact"}),
            {"result": "stored"},
            ((artifact, content),),
        )

        with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
            self.store._connection.execute(
                "UPDATE artifacts SET content_json='{}' WHERE tenant_id=?",
                (self.scope.tenant_id,),
            )

        # Model an attacker who has bypassed the append-only trigger. Digest checks
        # must still prevent the corrupted content from being trusted.
        self.store._connection.execute(
            "DROP TRIGGER semantic_artifacts_no_update"
        )
        self.store._connection.execute(
            "UPDATE artifacts SET content_json='{}' WHERE tenant_id=?",
            (self.scope.tenant_id,),
        )
        with self.assertRaisesRegex(StoreError, "integrity validation"):
            self.store.artifact(
                self.scope,
                "elmos-semantic-diff-engine",
                artifact.logical_path,
            )

    def test_idempotent_response_tampering_is_detected(self) -> None:
        request_digest = digest_value({"request": "response"})
        self.store.complete(
            self.scope,
            "elmos-semantic-diff-engine",
            "idem-response",
            "subject-001",
            request_digest,
            {"verdict": "NOT_RUN"},
            (),
        )
        self.store._connection.execute(
            "UPDATE invocations SET response_json=? WHERE tenant_id=?",
            (json.dumps({"verdict": "PASS"}), self.scope.tenant_id),
        )

        with self.assertRaisesRegex(StoreError, "integrity validation"):
            self.store.replay(
                self.scope,
                "elmos-semantic-diff-engine",
                "idem-response",
                request_digest,
            )

    def test_event_log_is_append_only(self) -> None:
        self.store.complete(
            self.scope,
            "elmos-semantic-diff-engine",
            "idem-event",
            "subject-001",
            digest_value({"request": "event"}),
            {"verdict": "NOT_RUN"},
            (),
        )

        with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
            self.store._connection.execute(
                "UPDATE events SET payload_json='{}' WHERE tenant_id=?",
                (self.scope.tenant_id,),
            )
        with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
            self.store._connection.execute(
                "DELETE FROM events WHERE tenant_id=?",
                (self.scope.tenant_id,),
            )
        verification = self.store.verify_event_chain(self.scope)
        self.assertTrue(verification["verified"])
        self.assertEqual(verification["eventCount"], 1)
        self.assertTrue(verification["chainHead"].startswith("sha256:"))

    def test_event_chain_detects_payload_tampering(self) -> None:
        self.store.complete(
            self.scope,
            "elmos-semantic-diff-engine",
            "idem-event-tamper",
            "subject-001",
            digest_value({"request": "event-tamper"}),
            {"verdict": "NOT_RUN"},
            (),
        )
        self.store._connection.execute(
            "DROP TRIGGER semantic_events_no_update"
        )
        self.store._connection.execute(
            "UPDATE events SET payload_json='{}' WHERE tenant_id=? AND project_id=?",
            (self.scope.tenant_id, self.scope.project_id),
        )

        with self.assertRaisesRegex(StoreError, "event payload integrity"):
            self.store.verify_event_chain(self.scope)

    def test_cache_entries_are_immutable_and_tenant_scoped(self) -> None:
        cache_key = digest_value({"formula": "x > 0"})
        dependency = digest_value({"solver": "z3-4.13", "assumptions": []})
        stored = self.store.put_cache(
            self.scope,
            "elmos-proof-cache-invalidation",
            cache_key,
            dependency,
            {"status": "NOT_RUN"},
        )
        self.assertFalse(stored["stale"])

        with self.assertRaisesRegex(StoreError, "immutable semantic cache entry conflict"):
            self.store.put_cache(
                self.scope,
                "elmos-proof-cache-invalidation",
                cache_key,
                dependency,
                {"status": "PASS"},
            )

        other = _other_scope(self.scope, tenant="tenant-b", project="project-b")
        self.assertEqual(
            self.store.invalidate_cache(
                other,
                "elmos-proof-cache-invalidation",
                digest_value({"solver": "changed"}),
            ),
            0,
        )

    def test_state_database_rejects_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            target = tmp_path / "target.db"
            target.touch(mode=0o600)
            link = tmp_path / "state.db"
            link.symlink_to(target)

            with self.assertRaisesRegex(StoreError, "must not be a symlink"):
                SemanticAssuranceStore(link)

    def test_state_database_rejects_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            real_parent = tmp_path / "real-state"
            real_parent.mkdir()
            linked_parent = tmp_path / "linked-state"
            linked_parent.symlink_to(real_parent, target_is_directory=True)

            with self.assertRaisesRegex(StoreError, "parent path must not contain symlinks"):
                SemanticAssuranceStore(linked_parent / "state.db")

    def test_state_database_rejects_hardlink_and_permissive_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            original = tmp_path / "original.db"
            original.touch(mode=0o600)
            hardlink = tmp_path / "hardlink.db"
            os.link(original, hardlink)
            with self.assertRaisesRegex(StoreError, "non-hardlinked"):
                SemanticAssuranceStore(hardlink)

            permissive = tmp_path / "permissive.db"
            permissive.touch(mode=0o644)
            with self.assertRaisesRegex(StoreError, "mode must be 0600"):
                SemanticAssuranceStore(permissive)


if __name__ == "__main__":
    unittest.main()
