"""PUB-001..003: complete-tree publication, atomic switch and rollback."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import claim_node
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import FileClass, StagedFileStatus, ValidationLevel
from elmos_build_cache.errors import ConflictError, NotFound, ValidationTooLow
from elmos_build_cache.journal import RunCoordinator
from elmos_build_cache.manifests import EvidenceBundle, TreeEntry, build_file_tree
from elmos_build_cache.publish import MANIFEST_NAME, POINTER_NAME, TreePublisher
from elmos_build_cache.staging import Workspace, stage_all


def evidence_for(tree, level=ValidationLevel.TEST_VERIFIED) -> EvidenceBundle:
    return EvidenceBundle(
        tree_digest=tree.root_digest,
        validation_level=level,
        records=({"kind": "test", "passed": 42, "failed": 0},),
        produced_by="worker-1",
        verifier_identities=("independent-ci",),
    )


def stage(workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str, files):
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        return stage_all(
            workspace, "gen", 1, lease.epoch, files, file_class=FileClass.PUBLISH_CANDIDATE
        )


def test_pub_002_pointer_switch_exposes_only_complete_trees(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    run: str,
) -> None:
    """PUB-002: readers see the old complete tree or the new one, never both."""
    records = stage(
        workspace, store, coordinator, run, [("src/Main.cs", b"class Main {}"), ("App.csproj", b"<Project/>")]
    )
    tree = publisher.build_tree_manifest(records, validation_level=ValidationLevel.TEST_VERIFIED)
    evidence = evidence_for(tree)
    with store.transaction():
        evidence.store(workspace.cas)
        candidate = publisher.materialize(tree)
        assert publisher.current_tree_digest() is None  # not visible before the flip
        result = publisher.publish(candidate, evidence)

    assert result.tree_digest == tree.root_digest
    assert publisher.read_published("src/Main.cs") == b"class Main {}"
    assert publisher.read_published("App.csproj") == b"<Project/>"
    published = workspace.publish_root / run / result.tree_digest.split(":", 1)[1]
    assert (published / MANIFEST_NAME).is_file()
    assert (workspace.publish_root / run / POINTER_NAME).exists()


def test_pub_001_failed_materialisation_leaves_the_active_tree_untouched(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    cas: ContentAddressableStore,
    run: str,
) -> None:
    """PUB-001: a kill while building a candidate cannot disturb what is live."""
    records = stage(workspace, store, coordinator, run, [("src/Main.cs", b"v1")])
    tree = publisher.build_tree_manifest(records, validation_level=ValidationLevel.TEST_VERIFIED)
    evidence = evidence_for(tree)
    with store.transaction():
        evidence.store(cas)
        published = publisher.publish(publisher.materialize(tree), evidence)

    # A second tree whose artifact has gone missing cannot be materialised.
    broken = build_file_tree(
        [TreeEntry("src/Broken.cs", "sha256:" + "c" * 64, size=3)], producer={"run_id": run}
    )
    with pytest.raises(NotFound):
        publisher.materialize(broken)

    assert publisher.current_tree_digest() == published.tree_digest
    assert publisher.read_published("src/Main.cs") == b"v1"


def test_pub_003_evidence_bound_to_another_tree_blocks_publication(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    run: str,
) -> None:
    """PUB-003: evidence must bind to the exact tree digest being published."""
    records = stage(workspace, store, coordinator, run, [("a.cs", b"a"), ("b.cs", b"b")])
    first = publisher.build_tree_manifest(records, validation_level=ValidationLevel.TEST_VERIFIED)
    second = publisher.build_tree_manifest(records[:1], validation_level=ValidationLevel.TEST_VERIFIED)
    mismatched = evidence_for(first)

    with store.transaction():
        candidate = publisher.materialize(second)
    with pytest.raises(ConflictError), store.transaction():
        publisher.publish(candidate, mismatched)
    assert publisher.current_tree_digest() is None


def test_validation_above_unverified_requires_evidence(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    run: str,
) -> None:
    records = stage(workspace, store, coordinator, run, [("a.cs", b"a")])
    tree = publisher.build_tree_manifest(records, validation_level=ValidationLevel.TEST_VERIFIED)
    with store.transaction():
        candidate = publisher.materialize(tree)
    with pytest.raises(ValidationTooLow), store.transaction():
        publisher.publish(candidate, None)


def test_test_verified_requires_an_independent_verifier(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    run: str,
) -> None:
    records = stage(workspace, store, coordinator, run, [("a.cs", b"a")])
    tree = publisher.build_tree_manifest(records, validation_level=ValidationLevel.TEST_VERIFIED)
    weak = EvidenceBundle(tree.root_digest, ValidationLevel.TEST_VERIFIED, (), "worker-1", ())
    with store.transaction():
        candidate = publisher.materialize(tree)
    with pytest.raises(ValidationTooLow), store.transaction():
        publisher.publish(candidate, weak)


def test_rollback_returns_to_the_retained_tree(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    cas: ContentAddressableStore,
    run: str,
) -> None:
    records = stage(workspace, store, coordinator, run, [("a.cs", b"a"), ("b.cs", b"b")])
    first = publisher.build_tree_manifest(records, validation_level=ValidationLevel.TEST_VERIFIED)
    second = publisher.build_tree_manifest(records[:1], validation_level=ValidationLevel.TEST_VERIFIED)
    with store.transaction():
        evidence_for(first).store(cas)
        original = publisher.publish(publisher.materialize(first), evidence_for(first))
    with store.transaction():
        evidence_for(second).store(cas)
        publisher.publish(publisher.materialize(second), evidence_for(second))

    assert publisher.current_tree_digest() != original.tree_digest
    with store.transaction():
        publisher.rollback(original.tree_digest)
    assert publisher.current_tree_digest() == original.tree_digest
    assert publisher.read_published("b.cs") == b"b"


def test_rollback_to_an_evicted_tree_is_refused(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    run: str,
) -> None:
    with pytest.raises(NotFound):
        publisher.rollback("sha256:" + "d" * 64)


def test_only_promoted_files_enter_a_tree(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, publisher: TreePublisher, run: str
) -> None:
    from elmos_build_cache.errors import ContractViolation

    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        record = workspace.reserve("gen", 1, "a.cs", lease.epoch, file_class=FileClass.PUBLISH_CANDIDATE)
        sealed = workspace.write_and_seal(record, b"a", lease.epoch)
    assert sealed.status is StagedFileStatus.SEALED
    with pytest.raises(ContractViolation):
        publisher.build_tree_manifest([sealed])


def test_tree_manifest_rejects_conflicting_paths() -> None:
    with pytest.raises(ConflictError):
        build_file_tree(
            [
                TreeEntry("Src/App.cs", "sha256:" + "a" * 64),
                TreeEntry("src/App.cs", "sha256:" + "b" * 64),
            ],
            producer={},
        )


def test_publication_marks_staged_files_published(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    cas: ContentAddressableStore,
    run: str,
) -> None:
    records = stage(workspace, store, coordinator, run, [("a.cs", b"a")])
    tree = publisher.build_tree_manifest(records, validation_level=ValidationLevel.TEST_VERIFIED)
    with store.transaction():
        evidence_for(tree).store(cas)
        publisher.publish(publisher.materialize(tree), evidence_for(tree))
    assert all(
        record.status is StagedFileStatus.PUBLISHED for record in store.list_staged_files(run)
    )
    assert store.get_run(run).published_tree_digest == tree.root_digest


def test_materialised_tree_is_byte_exact(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    run: str,
    tmp_path: Path,
) -> None:
    payloads = {"src/A.cs": b"alpha", "src/nested/B.cs": b"beta", "root.txt": b"gamma"}
    records = stage(workspace, store, coordinator, run, list(payloads.items()))
    tree = publisher.build_tree_manifest(records)
    with store.transaction():
        candidate = publisher.materialize(tree)
    for logical_path, payload in payloads.items():
        assert (candidate.directory / logical_path).read_bytes() == payload
    assert os.path.isdir(candidate.directory)
