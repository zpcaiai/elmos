from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from tempfile import TemporaryDirectory
import unittest

from elmos_project_intelligence.artifacts import (
    ArtifactStoreError,
    ContentAddressedArtifactStore,
)
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
    StoreError,
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
            root = Path(temporary).resolve() / "repository"
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
            root = Path(temporary).resolve() / "repository"
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
            parent = Path(temporary).resolve()
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

    def test_snapshot_rejects_symlinked_root_ancestor(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            outside = parent / "outside"
            repository = outside / "repository"
            repository.mkdir(parents=True)
            (repository / "app.py").write_text("print('outside')\n", encoding="utf-8")
            linked_ancestor = parent / "authorized"
            linked_ancestor.symlink_to(outside, target_is_directory=True)

            result = snapshot_repository(
                SnapshotRequest(
                    "tenant-a",
                    "project-a",
                    "run-a",
                    linked_ancestor / "repository",
                )
            )

            self.assertFalse(result.ok)
            assert result.error is not None
            self.assertEqual(result.error.code, "UNSAFE_FILESYSTEM_ENTRY")


class ArtifactStoreTests(unittest.TestCase):
    def test_private_descriptor_relative_store_round_trips_immutable_content(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            store = ContentAddressedArtifactStore(
                Path(temporary).resolve() / "artifacts"
            )
            content = b"bounded-project-intelligence-artifact"
            digest = store.put(content)

            self.assertEqual(store.put(content), digest)
            self.assertEqual(store.read(digest), content)
            self.assertTrue(store.contains(digest))
            self.assertEqual(stat.S_IMODE(store._path(digest).stat().st_mode), 0o600)

    def test_store_rejects_public_root_and_symlinked_digest_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            public_root = parent / "public-artifacts"
            public_root.mkdir(mode=0o700)
            public_root.chmod(0o755)
            with self.assertRaisesRegex(ArtifactStoreError, "group or other"):
                ContentAddressedArtifactStore(public_root)

            store = ContentAddressedArtifactStore(parent / "private-artifacts")
            content = b"symlink-race-target"
            hexadecimal = hashlib.sha256(content).hexdigest()
            outside = parent / "outside"
            outside.mkdir()
            (store.objects / hexadecimal[:2]).symlink_to(
                outside, target_is_directory=True
            )
            with self.assertRaises(ArtifactStoreError):
                store.put(content)
            self.assertEqual(list(outside.iterdir()), [])

    def test_store_rejects_a_symlink_as_the_artifact_root(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            actual = parent / "actual"
            actual.mkdir(mode=0o700)
            linked = parent / "linked"
            linked.symlink_to(actual, target_is_directory=True)

            with self.assertRaises(ArtifactStoreError):
                ContentAddressedArtifactStore(linked)

    def test_store_rejects_hard_linked_artifact_objects(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            store = ContentAddressedArtifactStore(parent / "artifacts")
            digest = store.put(b"immutable-artifact")
            external_link = parent / "external-hard-link"
            os.link(store._path(digest), external_link)

            with self.assertRaisesRegex(ArtifactStoreError, "exactly one"):
                store.read(digest)

            external_link.unlink()
            self.assertEqual(store.read(digest), b"immutable-artifact")

    def test_store_rejects_a_symlinked_artifact_root_ancestor(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            actual_parent = parent / "actual"
            actual_parent.mkdir(mode=0o700)
            linked_parent = parent / "linked"
            linked_parent.symlink_to(actual_parent, target_is_directory=True)

            with self.assertRaises(ArtifactStoreError):
                ContentAddressedArtifactStore(linked_parent / "artifacts")


class StoreTests(unittest.TestCase):
    def test_store_creates_private_database_under_permissive_umask(self) -> None:
        with TemporaryDirectory() as temporary:
            database = Path(temporary).resolve() / "private.sqlite3"
            previous_umask = os.umask(0)
            try:
                store = ProjectIntelligenceStore(database)
            finally:
                os.umask(previous_umask)
            try:
                store.register_project("tenant-a", "project-a")
                self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o600)
                for suffix in ("-wal", "-shm", "-journal"):
                    companion = Path(str(database) + suffix)
                    if companion.exists():
                        self.assertEqual(
                            stat.S_IMODE(companion.stat().st_mode),
                            0o600,
                            companion,
                        )
            finally:
                store.close()

    def test_store_rejects_public_database_and_companion_modes(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            database = parent / "public.sqlite3"
            database.touch(mode=0o600)
            database.chmod(0o644)
            with self.assertRaisesRegex(StoreError, "mode must be 0600"):
                ProjectIntelligenceStore(database)

            database.chmod(0o600)
            wal = Path(str(database) + "-wal")
            wal.touch(mode=0o600)
            wal.chmod(0o644)
            with self.assertRaisesRegex(StoreError, "companion -wal mode"):
                ProjectIntelligenceStore(database)

    def test_store_rejects_a_symlinked_database_ancestor(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            actual_parent = parent / "actual"
            actual_parent.mkdir(mode=0o700)
            linked_parent = parent / "linked"
            linked_parent.symlink_to(actual_parent, target_is_directory=True)

            with self.assertRaises(ValueError):
                ProjectIntelligenceStore(linked_parent / "state.sqlite3")

    def test_unrelated_private_database_is_not_mutated_before_rejection(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            database = parent / "unrelated.sqlite3"
            external = sqlite3.connect(database)
            try:
                external.execute("CREATE TABLE unrelated (value TEXT NOT NULL)")
                external.execute("INSERT INTO unrelated (value) VALUES ('original')")
                external.commit()
                self.assertEqual(
                    external.execute("PRAGMA journal_mode").fetchone()[0],
                    "delete",
                )
            finally:
                external.close()
            database.chmod(0o600)
            before = database.read_bytes()

            with self.assertRaisesRegex(StoreError, "schema attestation failed"):
                ProjectIntelligenceStore(database)

            self.assertEqual(database.read_bytes(), before)
            self.assertFalse(Path(str(database) + "-wal").exists())
            self.assertFalse(Path(str(database) + "-shm").exists())
            check = sqlite3.connect(database)
            try:
                self.assertEqual(
                    check.execute("PRAGMA journal_mode").fetchone()[0], "delete"
                )
                self.assertEqual(
                    check.execute("SELECT value FROM unrelated").fetchone()[0],
                    "original",
                )
            finally:
                check.close()

    def test_live_schema_and_version_drift_fail_before_reads_or_writes(self) -> None:
        with TemporaryDirectory() as temporary:
            database = Path(temporary).resolve() / "state.sqlite3"
            with ProjectIntelligenceStore(database) as store:
                store.register_project("tenant-a", "project-a")
                external = sqlite3.connect(database)
                try:
                    external.executescript(
                        "DROP TRIGGER events_no_delete;"
                        "CREATE TRIGGER events_no_delete BEFORE DELETE ON events "
                        "BEGIN SELECT 1; END;"
                    )
                    external.commit()
                finally:
                    external.close()

                with self.assertRaisesRegex(StoreError, "schema attestation failed"):
                    store.get_project("tenant-a", "project-a")
                with self.assertRaisesRegex(StoreError, "schema attestation failed"):
                    store.register_project("tenant-b", "project-b")

            version_database = Path(temporary).resolve() / "version.sqlite3"
            with ProjectIntelligenceStore(version_database) as store:
                store.register_project("tenant-a", "project-a")
                external = sqlite3.connect(version_database)
                try:
                    external.execute("UPDATE schema_metadata SET schema_version = 3")
                    external.commit()
                finally:
                    external.close()
                with self.assertRaisesRegex(StoreError, "unsupported.*version"):
                    store.get_project("tenant-a", "project-a")

    def test_live_database_path_replacement_is_detected(self) -> None:
        with TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            database = parent / "state.sqlite3"
            moved = parent / "state.original.sqlite3"
            store = ProjectIntelligenceStore(database)
            try:
                store.register_project("tenant-a", "project-a")
                database.rename(moved)
                database.touch(mode=0o600)
                database.chmod(0o600)
                with self.assertRaisesRegex(StoreError, "path identity changed"):
                    store.get_project("tenant-a", "project-a")
            finally:
                database.unlink(missing_ok=True)
                moved.rename(database)
                store.close()

    def test_scoped_idempotent_lifecycle_artifacts_evidence_and_checkpoints(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            database = Path(temporary).resolve() / "state.sqlite3"
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
            database = Path(temporary).resolve() / "state.sqlite3"
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

    def test_project_metadata_digest_drift_fails_closed(self) -> None:
        with TemporaryDirectory() as temporary:
            database = Path(temporary).resolve() / "state.sqlite3"
            with ProjectIntelligenceStore(database) as store:
                store.register_project(
                    "tenant-a", "project-a", metadata={"name": "original"}
                )

            external = sqlite3.connect(database)
            try:
                external.execute(
                    "UPDATE projects SET metadata_json = ? "
                    "WHERE tenant_id = ? AND project_id = ?",
                    ('{"name":"tampered"}', "tenant-a", "project-a"),
                )
                external.commit()
            finally:
                external.close()

            with ProjectIntelligenceStore(database) as reopened:
                with self.assertRaisesRegex(StoreError, "metadata digest mismatch"):
                    reopened.get_project("tenant-a", "project-a")
                with self.assertRaisesRegex(StoreError, "metadata digest mismatch"):
                    reopened.register_project(
                        "tenant-a", "project-a", metadata={"name": "original"}
                    )

    def test_store_rejects_counterfeit_repository_trigger(self) -> None:
        with TemporaryDirectory() as temporary:
            database = Path(temporary).resolve() / "state.sqlite3"
            with ProjectIntelligenceStore(database) as store:
                store.register_project("tenant-a", "project-a")

            external = sqlite3.connect(database)
            try:
                external.executescript(
                    "DROP TRIGGER events_no_delete;"
                    "CREATE TRIGGER events_no_delete BEFORE DELETE ON events "
                    "BEGIN SELECT 1; END;"
                )
                external.commit()
            finally:
                external.close()

            with self.assertRaisesRegex(StoreError, "schema attestation failed"):
                ProjectIntelligenceStore(database)

    def test_local_evidence_cannot_manufacture_verification_or_verifier(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceInput(
                evidence_id="evidence-a",
                kind="external-verification",
                subject_digest=canonical_digest({"artifact": "a"}),
                state=EvidenceState.VERIFIED,
                verifier=None,
            )
        for state in (EvidenceState.VERIFIED, EvidenceState.REJECTED):
            with self.subTest(state=state), self.assertRaises(ValueError):
                EvidenceInput(
                    evidence_id=f"evidence-{state.value.lower()}",
                    kind="external-verification",
                    subject_digest=canonical_digest({"artifact": "a"}),
                    state=state,
                    verifier="caller-supplied-verifier",
                )
        with self.assertRaisesRegex(ValueError, "cannot name an independent verifier"):
            EvidenceInput(
                evidence_id="evidence-collected",
                kind="bounded-local-read",
                subject_digest=canonical_digest({"artifact": "a"}),
                state=EvidenceState.COLLECTED,
                verifier="caller-supplied-verifier",
            )

        with TemporaryDirectory() as temporary:
            database = Path(temporary).resolve() / "state.sqlite3"
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
                before_events = store.list_events("tenant-a", "project-a", "run-a")
                forged = EvidenceInput(
                    evidence_id="evidence-forged",
                    kind="bounded-local-read",
                    subject_digest=canonical_digest({"artifact": "a"}),
                    state=EvidenceState.COLLECTED,
                )
                object.__setattr__(forged, "state", EvidenceState.VERIFIED)
                with self.assertRaisesRegex(ValueError, "cannot claim VERIFIED"):
                    store.put_evidence("tenant-a", "project-a", "run-a", forged)
                self.assertEqual(
                    store.list_evidence("tenant-a", "project-a", "run-a"), ()
                )
                self.assertEqual(
                    store.list_events("tenant-a", "project-a", "run-a"),
                    before_events,
                )

            external = sqlite3.connect(database)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    external.execute(
                        "INSERT INTO evidence "
                        "(tenant_id, project_id, run_id, evidence_id, kind, "
                        "subject_digest, state, details_json, details_digest, "
                        "artifact_id, verifier, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            "tenant-a",
                            "project-a",
                            "run-a",
                            "direct-forgery",
                            "external-verification",
                            canonical_digest({"artifact": "a"}),
                            "VERIFIED",
                            "{}",
                            canonical_digest({}),
                            None,
                            "caller-supplied-verifier",
                            "2026-08-24T00:00:00.000000Z",
                        ),
                    )
            finally:
                external.rollback()
                external.close()


if __name__ == "__main__":
    unittest.main()
