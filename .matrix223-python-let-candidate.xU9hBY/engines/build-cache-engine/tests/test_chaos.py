"""CHAOS-001..002 and CERT-001: kill points, controlled failure, certification."""

from __future__ import annotations

import dataclasses

import pytest

from conftest import TENANT, claim_node, digest
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.chaos import (
    ALL_FAULT_KINDS,
    ALL_KILL_POINTS,
    CertificationScope,
    CertificationService,
    DigestComparison,
    FaultInjector,
    FaultKind,
    FaultSpec,
    InjectedFault,
    InvariantReport,
    KillPoint,
    RegressionCorpus,
    check_at_most_once_side_effects,
    check_no_partial_publication,
    check_recovery_converges,
    kill_point_matrix,
    require_all_invariants,
    run_fault_campaign,
)
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import FileClass, ValidationLevel
from elmos_build_cache.errors import CertificateInvalid, ContractViolation, QuotaExceeded, StaleLease
from elmos_build_cache.journal import RunCoordinator
from elmos_build_cache.manifests import EvidenceBundle
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.security import Ed25519ProvenanceSigner
from elmos_build_cache.staging import Workspace


def test_all_declared_kill_points_and_fault_kinds_exist() -> None:
    assert len(ALL_KILL_POINTS) == 17
    assert len(ALL_FAULT_KINDS) == 13
    assert len(kill_point_matrix()) == len(ALL_KILL_POINTS) * len(ALL_FAULT_KINDS)


def test_injection_is_deterministic_and_reproducible() -> None:
    spec = FaultSpec(KillPoint.AFTER_SEAL, FaultKind.PROCESS_KILL, seed=7)
    first = FaultInjector((spec,), seed=99)
    with pytest.raises(InjectedFault):
        first.maybe_fail(KillPoint.AFTER_SEAL, node_id="gen")
    replay = first.report()["reproduce"]

    second = FaultInjector((spec,), seed=99)
    with pytest.raises(InjectedFault):
        second.maybe_fail(KillPoint.AFTER_SEAL, node_id="gen")
    assert second.report()["reproduce"] == replay
    # A single-shot fault does not fire twice.
    second.maybe_fail(KillPoint.AFTER_SEAL)


def test_fault_kinds_map_to_meaningful_errors() -> None:
    for kind, expected in (
        (FaultKind.DISK_FULL, QuotaExceeded),
        (FaultKind.INODE_EXHAUSTION, QuotaExceeded),
        (FaultKind.STALE_LEASE, StaleLease),
    ):
        injector = FaultInjector((FaultSpec(KillPoint.DURING_WRITE, kind),))
        with pytest.raises(expected):
            injector.maybe_fail(KillPoint.DURING_WRITE)


def test_chaos_001_kill_at_every_write_boundary_never_publishes_partially(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    publisher: TreePublisher,
    cas: ContentAddressableStore,
    run: str,
) -> None:
    """CHAOS-001: at every kill point, nothing partial becomes visible."""
    write_points = [
        KillPoint.BEFORE_RESERVATION,
        KillPoint.AFTER_RESERVATION,
        KillPoint.AFTER_TEMP_CREATE,
        KillPoint.DURING_WRITE,
        KillPoint.AFTER_FSYNC_BEFORE_RENAME,
        KillPoint.AFTER_RENAME_BEFORE_METADATA,
        KillPoint.AFTER_SEAL,
        KillPoint.BEFORE_CAS_PUT,
        KillPoint.AFTER_CAS_PUT,
        KillPoint.BEFORE_TREE_SWITCH,
    ]
    _, lease = claim_node(store, coordinator, run, "gen")

    def scenario(injector: FaultInjector) -> dict[str, object]:
        injector.maybe_fail(KillPoint.BEFORE_RESERVATION)
        with store.transaction():
            record = workspace.reserve(
                "gen", 1, f"src/{injector.seed}.cs", lease.epoch, file_class=FileClass.PUBLISH_CANDIDATE
            )
            injector.maybe_fail(KillPoint.AFTER_RESERVATION, staged_file_id=record.staged_file_id)
            injector.maybe_fail(KillPoint.AFTER_TEMP_CREATE)
            injector.maybe_fail(KillPoint.DURING_WRITE)
            record = workspace.write_and_seal(record, b"class Generated {}", lease.epoch)
            injector.maybe_fail(KillPoint.AFTER_SEAL)
            injector.maybe_fail(KillPoint.BEFORE_CAS_PUT)
            record = workspace.promote(record)
            injector.maybe_fail(KillPoint.AFTER_CAS_PUT)
        return {"staged_file_id": record.staged_file_id}

    results = run_fault_campaign(
        scenario, [FaultSpec(point, FaultKind.PROCESS_KILL, seed=index) for index, point in enumerate(write_points)]
    )
    assert all(item["status"] in ("RAISED", "SURVIVED") for item in results), results
    assert check_no_partial_publication(publisher).held

    with store.transaction():
        first = workspace.recover()
    with store.transaction():
        workspace.recover()
    assert first["failed"] == []
    assert check_recovery_converges(lambda: _recover(store, workspace)).held


def _recover(store: SqliteMetadataStore, workspace: Workspace) -> dict[str, object]:
    with store.transaction():
        return workspace.recover()


def test_chaos_002_disk_full_is_a_controlled_failure(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    """CHAOS-002: exhaustion fails cleanly; canonical state stays consistent."""
    _, lease = claim_node(store, coordinator, run, "gen")
    injector = FaultInjector((FaultSpec(KillPoint.DURING_WRITE, FaultKind.DISK_FULL),))

    with pytest.raises(QuotaExceeded), store.transaction():
        record = workspace.reserve("gen", 1, "src/Big.cs", lease.epoch)
        injector.maybe_fail(KillPoint.DURING_WRITE, staged_file_id=record.staged_file_id)
        workspace.write_and_seal(record, b"payload", lease.epoch)

    assert not (workspace.sealed_root / "src" / "Big.cs").exists()
    with store.transaction():
        summary = workspace.recover()
    assert summary["failed"] == []


def test_at_most_once_side_effects_invariant(
    store: SqliteMetadataStore, run: str
) -> None:
    with store.transaction():
        store.claim_side_effect(TENANT, run, "gen", "idem-1", "publish", digest("a"))
        store.complete_side_effect(TENANT, "idem-1", "COMMITTED", "ext-1")
        store.claim_side_effect(TENANT, run, "gen", "idem-1", "publish", digest("a"))
    assert check_at_most_once_side_effects(store, run).held


def test_digest_comparison_detects_divergence() -> None:
    matching = DigestComparison(clean=digest("a"), cached=digest("a"), resumed=digest("a"))
    assert matching.all_match
    diverging = DigestComparison(clean=digest("a"), cached=digest("b"))
    assert not diverging.all_match
    assert diverging.divergences()


def scope() -> CertificationScope:
    return CertificationScope(
        stage_ids=("target-code-generation", "compile", "test"),
        schema_version="1.0.0",
        toolchain_digest=digest("4"),
        rule_pack_digest=digest("5"),
        storage_profile="local-sqlite-filesystem",
        platform="linux-x86_64",
        trust_namespace="official",
    )


def full_evidence(tree_digest: str) -> EvidenceBundle:
    return EvidenceBundle(
        tree_digest=tree_digest,
        validation_level=ValidationLevel.PRODUCTION_CERTIFIED,
        records=tuple({"kind": kind, "passed": True} for kind in
                      ("determinism", "recovery", "security", "behavior", "performance")),
        produced_by="worker-1",
        verifier_identities=("independent-ci",),
    )


def test_cert_001_expired_revoked_and_scope_mismatch_are_rejected(
    store: SqliteMetadataStore, clock: ManualClock
) -> None:
    """CERT-001: production reuse is refused unless the certificate still fits."""
    service = CertificationService(
        store, Ed25519ProvenanceSigner.generate("cert-signing-1"), clock, validity_seconds=3600
    )
    tree = digest("e")
    certificate = service.issue(
        TENANT,
        scope(),
        tree,
        full_evidence(tree),
        DigestComparison(clean=tree, cached=tree, resumed=tree, remote=tree, fault_injected=tree),
        [InvariantReport("no-partial-publication", True)],
        action_key=digest("7"),
        producer_identity="worker-1",
        verifier_identities=("independent-ci",),
    )
    assert service.verify(certificate.certificate_id, scope(), tree)["valid"] is True

    with pytest.raises(CertificateInvalid, match="different output tree"):
        service.verify(certificate.certificate_id, scope(), digest("f"))
    other_scope = dataclasses.replace(scope(), platform="darwin-arm64")
    with pytest.raises(CertificateInvalid, match="scope"):
        service.verify(certificate.certificate_id, other_scope, tree)

    clock.advance(7200)
    with pytest.raises(CertificateInvalid, match="expired"):
        service.verify(certificate.certificate_id, scope(), tree)


def test_certificate_revocation_blocks_reuse(store: SqliteMetadataStore, clock: ManualClock) -> None:
    service = CertificationService(store, Ed25519ProvenanceSigner.generate("cert-signing-1"), clock)
    tree = digest("e")
    certificate = service.issue(
        TENANT,
        scope(),
        tree,
        full_evidence(tree),
        DigestComparison(clean=tree, cached=tree),
        [],
        digest("7"),
        "worker-1",
        ("independent-ci",),
    )
    with store.transaction():
        service.revoke(certificate.certificate_id, "toolchain compromise")
    with pytest.raises(CertificateInvalid):
        service.verify(certificate.certificate_id, scope(), tree)


def test_certification_requires_matching_digests_and_complete_evidence(
    store: SqliteMetadataStore, clock: ManualClock
) -> None:
    service = CertificationService(store, Ed25519ProvenanceSigner.generate("cert-signing-1"), clock)
    tree = digest("e")
    with pytest.raises(CertificateInvalid, match="diverge"):
        service.issue(
            TENANT, scope(), tree, full_evidence(tree),
            DigestComparison(clean=tree, resumed=digest("f")), [], digest("7"), "worker-1", ("ci",),
        )
    thin = EvidenceBundle(tree, ValidationLevel.PRODUCTION_CERTIFIED, ({"kind": "behavior"},), "w", ("ci",))
    with pytest.raises(CertificateInvalid, match="incomplete"):
        service.issue(
            TENANT, scope(), tree, thin, DigestComparison(clean=tree), [], digest("7"), "worker-1", ("ci",)
        )
    with pytest.raises(CertificateInvalid, match="independent verifier"):
        service.issue(
            TENANT, scope(), tree, full_evidence(tree), DigestComparison(clean=tree), [],
            digest("7"), "worker-1", ("worker-1",),
        )
    with pytest.raises(CertificateInvalid, match="invariants"):
        service.issue(
            TENANT, scope(), tree, full_evidence(tree), DigestComparison(clean=tree),
            [InvariantReport("no-partial-publication", False, "pointer dangling")],
            digest("7"), "worker-1", ("ci",),
        )


def test_discovered_failures_become_replayable_regressions() -> None:
    injector = FaultInjector((FaultSpec(KillPoint.AFTER_CAS_PUT, FaultKind.PROCESS_KILL, seed=3),), seed=42)
    with pytest.raises(InjectedFault):
        injector.maybe_fail(KillPoint.AFTER_CAS_PUT)
    corpus = RegressionCorpus()
    corpus.record("kill-after-cas-put", injector, [InvariantReport("recovery-converges", True)])

    name, replay = corpus.replay_specs()[0]
    assert name == "kill-after-cas-put"
    with pytest.raises(InjectedFault):
        replay.maybe_fail(KillPoint.AFTER_CAS_PUT)


def test_require_all_invariants_raises_on_a_violation() -> None:
    with pytest.raises(ContractViolation):
        require_all_invariants([InvariantReport("no-partial-publication", False, "dangling pointer")])
