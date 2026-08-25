from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from elmos_project_intelligence.canonical import (
    CanonicalizationError,
    canonical_digest,
    canonical_json,
    digest_matches,
)
from elmos_project_intelligence.contracts import (
    ArtifactInput,
    CreateRunRequest,
    EvidenceInput,
    EvidenceState,
    IdempotencyDisposition,
    RunStatus,
    SnapshotLimits,
    SnapshotRequest,
)
from elmos_project_intelligence.snapshot import snapshot_repository
from elmos_project_intelligence.store import (
    CheckpointConflict,
    IdempotencyConflict,
    ProjectIntelligenceStore,
    RecordNotFound,
    StateTransitionError,
)


class CanonicalTests(unittest.TestCase):
    def test_canonical_json_is_order_independent_and_digest_bound(self) -> None:
        left = {"z": [3, 2, 1], "a": {"enabled": True}}
        right = {"a": {"enabled": True}, "z": [3, 2, 1]}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(canonical_digest(left), canonical_digest(right))
        self.assertTrue(
            digest_matches(canonical_json(left).encode("utf-8"), canonical_digest(left))
        )

    def test_canonical_json_rejects_ambiguous_values(self) -> None:
        with self.assertRaises(CanonicalizationError):
            canonical_json({"measurement": 1.25})
        with self.assertRaises(CanonicalizationError):
            canonical_json({1: "non-string key"})
        cyclic: list[object] = []
        cyclic.append(cyclic)
        with self.assertRaises(CanonicalizationError):
            canonical_json(cyclic)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_captures_stable_text_without_following_symlinks(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            root.mkdir()
            literal = "super-secret-value"
            source = f'API_KEY="{literal}"\nprint("safe")\n'
            (root / "app.py").write_text(source, encoding="utf-8")
            (root / "outside-link").symlink_to("/etc/passwd")
            executable = root / "do-not-run.sh"
            executable.write_text(
                "#!/bin/sh\ntouch executed-marker\n", encoding="utf-8"
            )
            executable.chmod(0o755)

            result = snapshot_repository(
                SnapshotRequest(
                    tenant_id="tenant-a",
                    project_id="project-a",
                    run_id="run-a",
                    root=root,
                    limits=SnapshotLimits(
                        max_files=10,
                        max_total_bytes=16_384,
                        max_file_bytes=8_192,
                    ),
                )
            )

            self.assertTrue(result.ok, result.error)
            snapshot = result.value
            assert snapshot is not None
            self.assertEqual(snapshot.read_text("app.py"), source)
            self.assertFalse((root / "executed-marker").exists())
            self.assertEqual(snapshot.file_count, 2)
            self.assertEqual(snapshot.symlink_count, 1)
            self.assertEqual(
                snapshot.snapshot_digest,
                canonical_digest(snapshot.digest_manifest()),
            )

            app = next(entry for entry in snapshot.entries if entry.path == "app.py")
            self.assertTrue(app.secret_fingerprints)
            self.assertNotIn(literal, repr(app.secret_fingerprints))
            link = next(
                entry for entry in snapshot.entries if entry.path == "outside-link"
            )
            self.assertIsNone(link.text)
            self.assertNotIn("/etc/passwd", repr(link))

            default_manifest = snapshot.to_manifest()
            self.assertNotIn("text", default_manifest["files"][0])
            text_manifest = snapshot.to_manifest(include_text=True)
            app_manifest = next(
                item for item in text_manifest["files"] if item["path"] == "app.py"
            )
            self.assertEqual(app_manifest["text"], source)
            self.assertEqual(app_manifest["sha256"], app.sha256)
            self.assertEqual(app_manifest["bytes"], len(source.encode("utf-8")))

    def test_snapshot_limits_count_directories_and_fail_without_partial_value(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            root.mkdir()
            (root / "one").mkdir()
            (root / "two").mkdir()
            result = snapshot_repository(
                SnapshotRequest(
                    tenant_id="tenant-a",
                    project_id="project-a",
                    run_id="run-a",
                    root=root,
                    limits=SnapshotLimits(
                        max_files=1,
                        max_total_bytes=100,
                        max_file_bytes=100,
                    ),
                    exclusions=(),
                )
            )
            self.assertFalse(result.ok)
            self.assertIsNone(result.value)
            assert result.error is not None
            self.assertEqual(result.error.code, "SNAPSHOT_LIMIT_EXCEEDED")

    def test_snapshot_rejects_symlink_root_and_preserves_binary_as_digest_only(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "repository"
            root.mkdir()
            (root / "binary.bin").write_bytes(b"\x00\xff\x01")
            link_root = parent / "linked-repository"
            link_root.symlink_to(root, target_is_directory=True)

            linked = snapshot_repository(
                SnapshotRequest("tenant-a", "project-a", "run-a", link_root)
            )
            self.assertFalse(linked.ok)
            assert linked.error is not None
            self.assertEqual(linked.error.code, "UNSAFE_FILESYSTEM_ENTRY")

            captured = snapshot_repository(
                SnapshotRequest("tenant-a", "project-a", "run-b", root)
            )
            self.assertTrue(captured.ok, captured.error)
            snapshot = captured.value
            assert snapshot is not None
            binary = snapshot.entries[0]
            self.assertIsNone(binary.text)
            with self.assertRaises(ValueError):
                snapshot.read_text("binary.bin")


class StoreTests(unittest.TestCase):
    def test_scoped_idempotent_lifecycle_artifacts_evidence_and_checkpoints(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / "state.sqlite3"
            clock_values = iter(
                f"2026-08-24T00:00:{index:02d}.000000Z" for index in range(30)
            )
            with ProjectIntelligenceStore(
                database, clock=lambda: next(clock_values)
            ) as store:
                store.register_project("tenant-a", "project-a", metadata={"name": "A"})
                store.register_project("tenant-b", "project-a", metadata={"name": "B"})
                request = CreateRunRequest(
                    tenant_id="tenant-a",
                    project_id="project-a",
                    run_id="run-a",
                    operation="snapshot",
                    idempotency_key="request-a",
                    request={"revision": "abc123"},
                )
                created = store.create_run(request)
                self.assertEqual(created.disposition, IdempotencyDisposition.CREATED)
                replayed = store.create_run(
                    CreateRunRequest(
                        "tenant-a",
                        "project-a",
                        "ignored-run-id",
                        "snapshot",
                        "request-a",
                        {"revision": "abc123"},
                    )
                )
                self.assertEqual(replayed.disposition, IdempotencyDisposition.REPLAYED)
                self.assertEqual(replayed.run.run_id, "run-a")
                with self.assertRaises(IdempotencyConflict):
                    store.create_run(
                        CreateRunRequest(
                            "tenant-a",
                            "project-a",
                            "run-b",
                            "snapshot",
                            "request-a",
                            {"revision": "different"},
                        )
                    )
                with self.assertRaises(RecordNotFound):
                    store.get_run("tenant-b", "project-a", "run-a")

                store.set_run_status(
                    "tenant-a", "project-a", "run-a", RunStatus.RUNNING
                )
                subject_digest = canonical_digest({"snapshot": "abc123"})
                artifact = store.put_artifact(
                    "tenant-a",
                    "project-a",
                    "run-a",
                    ArtifactInput(
                        artifact_id="snapshot-a",
                        kind="repository-snapshot",
                        content_digest=subject_digest,
                        byte_count=123,
                        media_type="application/json",
                        metadata={"stable": True},
                    ),
                )
                self.assertEqual(artifact.content_digest, subject_digest)
                evidence = store.put_evidence(
                    "tenant-a",
                    "project-a",
                    "run-a",
                    EvidenceInput(
                        evidence_id="evidence-a",
                        kind="bounded-local-read",
                        subject_digest=subject_digest,
                        state=EvidenceState.COLLECTED,
                        artifact_id="snapshot-a",
                        details={"external": "NOT_RUN"},
                    ),
                )
                self.assertEqual(evidence.state, EvidenceState.COLLECTED)
                checkpoint = store.append_checkpoint(
                    "tenant-a",
                    "project-a",
                    "run-a",
                    {"stage": "snapshot"},
                    expected_previous_sequence=0,
                )
                self.assertEqual(checkpoint.sequence, 1)
                with self.assertRaises(CheckpointConflict):
                    store.append_checkpoint(
                        "tenant-a",
                        "project-a",
                        "run-a",
                        {"stage": "analysis"},
                        expected_previous_sequence=0,
                    )
                completed = store.set_run_status(
                    "tenant-a",
                    "project-a",
                    "run-a",
                    RunStatus.SUCCEEDED,
                    response={
                        "artifact_digest": artifact.content_digest,
                        "certification": "NOT_CERTIFIED",
                    },
                )
                self.assertEqual(completed.status, RunStatus.SUCCEEDED)
                with self.assertRaises(StateTransitionError):
                    store.set_run_status(
                        "tenant-a", "project-a", "run-a", RunStatus.RUNNING
                    )
                self.assertEqual(
                    len(store.list_artifacts("tenant-a", "project-a", "run-a")), 1
                )
                self.assertEqual(
                    len(store.list_evidence("tenant-a", "project-a", "run-a")), 1
                )
                self.assertEqual(
                    len(store.list_checkpoints("tenant-a", "project-a", "run-a")), 1
                )
                self.assertEqual(
                    len(store.list_events("tenant-a", "project-a", "run-a")), 6
                )

            mode = os.stat(database).st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_failed_transaction_leaves_no_evidence_or_event_and_events_are_immutable(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / "state.sqlite3"
            with ProjectIntelligenceStore(database) as store:
                store.register_project("tenant-a", "project-a")
                store.create_run(
                    CreateRunRequest(
                        "tenant-a",
                        "project-a",
                        "run-a",
                        "snapshot",
                        "request-a",
                        {"revision": "abc123"},
                    )
                )
                before = store.list_events("tenant-a", "project-a", "run-a")
                with self.assertRaises(RecordNotFound):
                    store.put_evidence(
                        "tenant-a",
                        "project-a",
                        "run-a",
                        EvidenceInput(
                            evidence_id="evidence-a",
                            kind="bounded-local-read",
                            subject_digest=canonical_digest({"snapshot": "abc123"}),
                            state=EvidenceState.COLLECTED,
                            artifact_id="missing-artifact",
                        ),
                    )
                self.assertEqual(
                    store.list_evidence("tenant-a", "project-a", "run-a"), ()
                )
                self.assertEqual(
                    store.list_events("tenant-a", "project-a", "run-a"), before
                )

            external = sqlite3.connect(database)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    external.execute(
                        "DELETE FROM events WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                        ("tenant-a", "project-a", "run-a"),
                    )
            finally:
                external.rollback()
                external.close()

    def test_verified_evidence_cannot_manufacture_anonymous_verification(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceInput(
                evidence_id="evidence-a",
                kind="external-verification",
                subject_digest=canonical_digest({"artifact": "a"}),
                state=EvidenceState.VERIFIED,
                verifier=None,
            )


if __name__ == "__main__":
    unittest.main()
