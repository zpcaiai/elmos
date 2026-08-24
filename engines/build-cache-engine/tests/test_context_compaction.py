"""Durable, cache-preserving context checkpoint tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.canonical import digest_of
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.context_compaction import (
    WARM_ATTESTATION_KIND,
    WARM_RESULT_KIND,
    CompactionNeed,
    CompactionPolicy,
    ContextCheckpointSections,
    ContextCheckpointStatus,
    ContextCompactionService,
    Ed25519ContextWarmTrustVerifier,
    SourceLinkedItem,
    context_warm_attestation_statement,
    context_warm_ref_kind,
)
from elmos_build_cache.context_ledger import ContextEventType, RepositoryContextLedger
from elmos_build_cache.db.store import SqliteMetadataStore
from elmos_build_cache.enums import ArtifactStorageState
from elmos_build_cache.errors import (
    ConflictError,
    ContractViolation,
    CorruptObject,
    NotFound,
    VersionConflict,
)
from elmos_build_cache.security import (
    Ed25519ProvenanceSigner,
    HmacProvenanceSigner,
    ProvenanceSigner,
)


def open_service(
    path: Path,
    clock: ManualClock,
    *,
    cas: ContentAddressableStore | None = None,
    signer: Ed25519ProvenanceSigner | None = None,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    stream_id: str = "persistent-context",
    trust: bool = True,
    revoked_key_ids: frozenset[str] = frozenset(),
) -> tuple[
    SqliteMetadataStore,
    ContentAddressableStore,
    Ed25519ProvenanceSigner,
    ContextCompactionService,
]:
    store = SqliteMetadataStore.open(path, clock)
    resolved_cas = cas or ContentAddressableStore(path.parent / f"{path.stem}-cas")
    resolved_signer = signer or Ed25519ProvenanceSigner.generate("context-warm-key")
    ledger = RepositoryContextLedger(
        store,
        tenant_id,
        project_id,
        stream_id,
        "refs/heads/main@abc123",
        digest("1"),
    )
    verifier = Ed25519ContextWarmTrustVerifier(
        Ed25519ProvenanceSigner.verifier(resolved_signer.public_keyset()),
        {resolved_signer.active_key_id: "warm-verifier"},
        revoked_key_ids=revoked_key_ids,
    )
    return (
        store,
        resolved_cas,
        resolved_signer,
        ContextCompactionService(
            ledger,
            CompactionPolicy(
                soft_limit_tokens=8_000,
                hard_limit_tokens=10_000,
                reserved_future_tokens=1_000,
            ),
            cas=resolved_cas,
            ownership=store,
            warm_trust_verifier=verifier if trust else None,
        ),
    )


def retained_sections(source_event_id: str, *, phase: str = "implement") -> ContextCheckpointSections:
    source = SourceLinkedItem(
        f"retain decision for {phase}",
        source_event_ids=(source_event_id,),
        artifact_refs=(digest("c"),),
    )
    return ContextCheckpointSections(
        task_contract={"request": "upgrade the cache completely", "scope": "persistent-context"},
        repository_state={
            "repository_snapshot_digest": digest("1"),
            "branch_lineage": "refs/heads/main@abc123",
            "changed_files": ["src/main.py"],
        },
        decisions=(source,),
        unresolved=(source,),
        approvals=(source,),
        dag_state={"phase": phase, "pending_nodes": ["verify"]},
        staged_state={"files": [{"path": "src/main.py", "digest": digest("d")}]},
        build_test_state={"pytest": "FAILED", "evidence_ref": digest("e")},
        evidence_refs=(digest("f"),),
        pending_side_effects=(source,),
        safety_constraints=(source,),
    )


def append_source_event(service: ContextCompactionService, key: str = "source-1") -> str:
    event = service.ledger.append(
        ContextEventType.FILE_READ,
        {"logical_path": "src/main.py", "content_digest": digest("a")},
        idempotency_key=key,
    )
    return str(event.event_id)


def create_warm_evidence(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    service: ContextCompactionService,
    checkpoint_id: str,
    signer: ProvenanceSigner,
    clock: ManualClock,
    *,
    body_overrides: dict[str, object] | None = None,
    register_tenant_id: str | None = None,
    add_refs: bool = True,
) -> tuple[str, str, str]:
    checkpoint = service.get(checkpoint_id)
    authorization = b'{"kind":"context-warm-authorization","decision":"ALLOW"}'
    authorization_digest = cas.put_bytes(authorization)
    raw = b'{"kind":"provider-prefix-warm-observation","cache_write_tokens":1024}'
    raw_digest = cas.put_bytes(raw)
    body: dict[str, object] = {
        "schema_version": "1.2.0",
        "kind": WARM_RESULT_KIND,
        "tenant_id": service.ledger.tenant_id,
        "project_id": service.ledger.project_id,
        "stream_id": service.ledger.stream_id,
        "checkpoint_id": checkpoint.checkpoint_id,
        "checkpoint_digest": checkpoint.checkpoint_digest,
        "compatibility_group": checkpoint.compatibility_group,
        "tenant_scope_digest": digest_of(
            {
                "tenant_id": service.ledger.tenant_id,
                "project_id": service.ledger.project_id,
            }
        ),
        "authorization_digest": authorization_digest,
        "executor_identity": "warm-executor",
        "verifier_identity": "warm-verifier",
        "status": "PASS",
        "raw_evidence": [
            {
                "role": "provider-cache-observation",
                "media_type": "application/json",
                "digest": raw_digest,
                "size": len(raw),
            }
        ],
        "issued_at": clock.now() - 1,
        "expires_at": clock.now() + 3_600,
    }
    body.update(body_overrides or {})
    signed = signer.sign_statement(
        WARM_ATTESTATION_KIND,
        context_warm_attestation_statement(body),
    )
    manifest = {**body, "attestation": signed.to_dict()}
    warm_digest = cas.put_document(manifest, artifact_kind="context-warm-result")
    tenant_id = register_tenant_id or service.ledger.tenant_id
    reference = (
        "context-warm-authorization",
        str(body["authorization_digest"]),
        context_warm_ref_kind(
            service.ledger.project_id,
            service.ledger.stream_id,
            checkpoint.checkpoint_id,
        ),
    )
    for artifact_digest in (authorization_digest, raw_digest, warm_digest):
        artifact = cas.get_bytes(artifact_digest, verify=True)
        store.register_artifact(
            tenant_id,
            artifact_digest,
            len(artifact),
            "application/octet-stream",
            "context-warm-evidence",
        )
        if add_refs:
            store.add_artifact_ref(
                tenant_id,
                reference[0],
                reference[1],
                artifact_digest,
                reference[2],
            )
    return warm_digest, raw_digest, authorization_digest


def corrupt_cas_object(cas: ContentAddressableStore, artifact_digest: str) -> None:
    path = cas.path_for(artifact_digest)
    path.chmod(0o644)
    path.write_bytes(b"tampered-context-evidence")


def test_soft_and_hard_compaction_limits_reserve_future_capacity() -> None:
    policy = CompactionPolicy(soft_limit_tokens=8_000, hard_limit_tokens=10_000, reserved_future_tokens=1_000)

    assert policy.assess(6_999) is CompactionNeed.NONE
    assert policy.assess(7_000) is CompactionNeed.PLAN
    assert policy.assess(8_500, predicted_next_turn_tokens=500) is CompactionNeed.REQUIRED


def test_read_only_ledger_open_does_not_create_missing_or_foreign_scope(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store = SqliteMetadataStore.open(tmp_path / "context.sqlite", clock)
    RepositoryContextLedger(
        store,
        "foreign-tenant",
        "foreign-project",
        "global-stream-id",
        "refs/heads/main@abc123",
        digest("1"),
    )
    before_projects = store.query_one("SELECT COUNT(*) FROM projects")
    before_streams = store.query_one("SELECT COUNT(*) FROM context_ledger_streams")

    failures: list[dict[str, object]] = []
    for stream_id in ("global-stream-id", "missing-stream-id"):
        with pytest.raises(NotFound) as captured:
            RepositoryContextLedger(
                store,
                TENANT,
                PROJECT,
                stream_id,
                "refs/heads/main@abc123",
                digest("1"),
                create_if_missing=False,
            )
        failures.append(captured.value.to_dict())
    assert failures[0] == failures[1]
    assert store.query_one("SELECT COUNT(*) FROM projects") == before_projects
    assert store.query_one("SELECT COUNT(*) FROM context_ledger_streams") == before_streams
    store.close()


def test_checkpoint_retains_full_task_state_and_cas_references(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    database = tmp_path / "context.sqlite"
    store, cas, signer, service = open_service(database, clock)
    source_event_id = append_source_event(service)
    sections = retained_sections(source_event_id)

    prepared = service.prepare(sections, compatibility_group="model-family/v1", expected_sequence=1)
    replay = service.prepare(sections, compatibility_group="model-family/v1", expected_sequence=1)

    assert replay == prepared
    assert prepared.status is ContextCheckpointStatus.PREPARED
    assert prepared.source_sequence_start == 1
    assert prepared.source_sequence_end == 1
    assert prepared.sections == sections.to_dict()
    assert {digest("c"), digest("f")} <= set(prepared.external_artifact_refs)
    assert len(prepared.external_artifact_refs) == 3
    stored_sections = store.query_one(
        "SELECT sections FROM context_checkpoints WHERE checkpoint_id=?",
        (prepared.checkpoint_id,),
    )
    assert stored_sections is not None
    stored_document = json.loads(str(stored_sections[0]))
    assert stored_document["kind"].endswith("sections-ref/v1.2")
    assert "upgrade the cache completely" not in str(stored_sections[0])
    store.close()

    # A fresh process recovers the complete checkpoint without any provider cache.
    reopened, _, _, restarted = open_service(database, clock, cas=cas, signer=signer)
    durable = restarted.get(prepared.checkpoint_id)
    assert durable.sections["task_contract"] == sections.task_contract
    assert durable.sections["unresolved"]
    assert durable.sections["approvals"]
    assert durable.sections["dag_state"] == sections.dag_state
    assert durable.sections["staged_state"] == sections.staged_state
    assert durable.sections["build_test_state"] == sections.build_test_state
    assert durable.sections["evidence_refs"] == [digest("f")]
    assert durable.warm_evidence_digest is None
    reopened.close()


def test_adoption_requires_warm_evidence_and_an_unchanged_ledger(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, cas, signer, service = open_service(tmp_path / "context.sqlite", clock)
    source_event_id = append_source_event(service)
    prepared = service.prepare(retained_sections(source_event_id), compatibility_group="model-family/v1")

    with pytest.raises(ConflictError, match="warmed"):
        service.adopt(prepared.checkpoint_id)

    first_warm, _, _ = create_warm_evidence(store, cas, service, prepared.checkpoint_id, signer, clock)
    warmed = service.mark_warmed(prepared.checkpoint_id, first_warm)
    assert warmed.status is ContextCheckpointStatus.WARMED
    assert warmed.warm_evidence_digest == first_warm
    active = service.adopt(warmed.checkpoint_id)
    assert active.status is ContextCheckpointStatus.ACTIVE
    assert service.active() == active

    later_event_id = append_source_event(service, "source-2")
    stale = service.prepare(
        retained_sections(later_event_id, phase="verify"),
        compatibility_group="model-family/v1",
    )
    stale_warm, _, _ = create_warm_evidence(store, cas, service, stale.checkpoint_id, signer, clock)
    service.mark_warmed(stale.checkpoint_id, stale_warm)
    append_source_event(service, "source-3")
    with pytest.raises(VersionConflict, match="advanced"):
        service.adopt(stale.checkpoint_id, expected_active_checkpoint_id=active.checkpoint_id)
    store.close()


def test_atomic_adoption_retains_and_rolls_back_the_previous_checkpoint(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, cas, signer, service = open_service(tmp_path / "context.sqlite", clock)
    first_event_id = append_source_event(service)
    first = service.prepare(retained_sections(first_event_id), compatibility_group="model-family/v1")
    first_warm, _, _ = create_warm_evidence(store, cas, service, first.checkpoint_id, signer, clock)
    service.mark_warmed(first.checkpoint_id, first_warm)
    first = service.adopt(first.checkpoint_id)

    second_event_id = append_source_event(service, "source-2")
    second = service.prepare(
        retained_sections(second_event_id, phase="test"),
        compatibility_group="model-family/v1",
    )
    assert second.previous_checkpoint_id == first.checkpoint_id
    second_warm, _, _ = create_warm_evidence(store, cas, service, second.checkpoint_id, signer, clock)
    service.mark_warmed(second.checkpoint_id, second_warm)
    second = service.adopt(
        second.checkpoint_id,
        expected_active_checkpoint_id=first.checkpoint_id,
    )

    assert second.status is ContextCheckpointStatus.ACTIVE
    assert service.get(first.checkpoint_id).status is ContextCheckpointStatus.SUPERSEDED

    untrusted = ContextCompactionService(
        service.ledger,
        service.policy,
        cas=cas,
        ownership=store,
    )
    with pytest.raises(ContractViolation, match="trust verifier"):
        untrusted.rollback(second.checkpoint_id)
    assert service.active() == second

    restored = service.rollback(second.checkpoint_id)
    assert restored.checkpoint_id == first.checkpoint_id
    assert restored.status is ContextCheckpointStatus.ACTIVE
    assert service.active() == restored
    rolled_back = service.get(second.checkpoint_id)
    assert rolled_back.status is ContextCheckpointStatus.ROLLED_BACK
    assert rolled_back.rolled_back_at is not None
    store.close()


def test_checkpoint_rejects_wrong_snapshot_or_foreign_source_event(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, _, _, service = open_service(tmp_path / "context.sqlite", clock)
    source_event_id = append_source_event(service)
    wrong_snapshot = retained_sections(source_event_id)
    wrong_snapshot.repository_state["repository_snapshot_digest"] = digest("2")
    with pytest.raises(ConflictError, match="another snapshot"):
        service.prepare(wrong_snapshot, compatibility_group="model-family/v1")

    foreign = retained_sections("ctxevt_not_in_this_stream")
    with pytest.raises(NotFound, match="outside this stream"):
        service.prepare(foreign, compatibility_group="model-family/v1")
    store.close()


def test_digest_format_alone_and_default_missing_trust_ownership_cannot_warm(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, cas, signer, service = open_service(tmp_path / "context.sqlite", clock)
    prepared = service.prepare(
        retained_sections(append_source_event(service)),
        compatibility_group="model-family/v1",
    )
    with pytest.raises(ContractViolation, match="owned|ownership"):
        service.mark_warmed(prepared.checkpoint_id, digest("9"))
    assert service.get(prepared.checkpoint_id).status is ContextCheckpointStatus.PREPARED

    warm_digest, _, _ = create_warm_evidence(store, cas, service, prepared.checkpoint_id, signer, clock)
    no_trust = ContextCompactionService(
        service.ledger,
        service.policy,
        cas=cas,
        ownership=store,
    )
    with pytest.raises(ContractViolation, match="trust verifier"):
        no_trust.mark_warmed(prepared.checkpoint_id, warm_digest)
    no_ownership = ContextCompactionService(service.ledger, service.policy)
    with pytest.raises(ContractViolation, match="ownership"):
        no_ownership.mark_warmed(prepared.checkpoint_id, warm_digest)
    store.close()


def test_warm_evidence_requires_exact_tenant_registration_and_refs(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, cas, signer, service = open_service(
        tmp_path / "context.sqlite",
        clock,
        tenant_id="tenant-other",
        project_id="project-other",
    )
    prepared = service.prepare(
        retained_sections(append_source_event(service)),
        compatibility_group="model-family/v1",
    )
    cross_tenant, _, _ = create_warm_evidence(
        store,
        cas,
        service,
        prepared.checkpoint_id,
        signer,
        clock,
        register_tenant_id=TENANT,
    )
    with pytest.raises(ContractViolation, match="owned"):
        service.mark_warmed(prepared.checkpoint_id, cross_tenant)

    no_ref, _, _ = create_warm_evidence(
        store,
        cas,
        service,
        prepared.checkpoint_id,
        signer,
        clock,
        add_refs=False,
    )
    with pytest.raises(ContractViolation, match="authorization reference"):
        service.mark_warmed(prepared.checkpoint_id, no_ref)
    store.close()


def test_warm_evidence_rejects_fake_authorization_hmac_and_unknown_key(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, cas, signer, service = open_service(tmp_path / "context.sqlite", clock)
    prepared = service.prepare(
        retained_sections(append_source_event(service)),
        compatibility_group="model-family/v1",
    )
    fake_authorization, _, _ = create_warm_evidence(
        store,
        cas,
        service,
        prepared.checkpoint_id,
        signer,
        clock,
        body_overrides={"authorization_digest": digest("9")},
    )
    with pytest.raises(ContractViolation, match="owned"):
        service.mark_warmed(prepared.checkpoint_id, fake_authorization)

    hmac = HmacProvenanceSigner({"dev": b"shared-secret"}, "dev")
    hmac_evidence, _, _ = create_warm_evidence(store, cas, service, prepared.checkpoint_id, hmac, clock)
    with pytest.raises(ContractViolation, match="Ed25519"):
        service.mark_warmed(prepared.checkpoint_id, hmac_evidence)

    attacker = Ed25519ProvenanceSigner.generate("unknown-context-key")
    unknown_key, _, _ = create_warm_evidence(store, cas, service, prepared.checkpoint_id, attacker, clock)
    with pytest.raises(ContractViolation, match="untrusted"):
        service.mark_warmed(prepared.checkpoint_id, unknown_key)
    store.close()


def test_expired_and_revoked_warm_attestations_fail_closed(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    signer = Ed25519ProvenanceSigner.generate("revocable-context-key")
    store, cas, _, service = open_service(
        tmp_path / "context.sqlite",
        clock,
        signer=signer,
        revoked_key_ids=frozenset({signer.active_key_id}),
    )
    prepared = service.prepare(
        retained_sections(append_source_event(service)),
        compatibility_group="model-family/v1",
    )
    expired, _, _ = create_warm_evidence(
        store,
        cas,
        service,
        prepared.checkpoint_id,
        signer,
        clock,
        body_overrides={"issued_at": clock.now() - 10, "expires_at": clock.now() - 1},
    )
    with pytest.raises(ContractViolation, match="expired"):
        service.mark_warmed(prepared.checkpoint_id, expired)

    current, _, _ = create_warm_evidence(store, cas, service, prepared.checkpoint_id, signer, clock)
    with pytest.raises(ContractViolation, match="untrusted"):
        service.mark_warmed(prepared.checkpoint_id, current)
    store.close()


def test_corrupt_raw_warm_evidence_is_quarantined_before_warming(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, cas, signer, service = open_service(tmp_path / "context.sqlite", clock)
    prepared = service.prepare(
        retained_sections(append_source_event(service)),
        compatibility_group="model-family/v1",
    )
    warm_digest, raw_digest, _ = create_warm_evidence(store, cas, service, prepared.checkpoint_id, signer, clock)
    corrupt_cas_object(cas, raw_digest)
    with pytest.raises(CorruptObject, match="CAS verification"):
        service.mark_warmed(prepared.checkpoint_id, warm_digest)
    assert cas.is_quarantined(raw_digest)
    assert service.get(prepared.checkpoint_id).status is ContextCheckpointStatus.PREPARED
    store.close()


def test_adopt_reverifies_warm_evidence_inside_the_transaction(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, cas, signer, service = open_service(tmp_path / "context.sqlite", clock)
    prepared = service.prepare(
        retained_sections(append_source_event(service)),
        compatibility_group="model-family/v1",
    )
    warm_digest, raw_digest, _ = create_warm_evidence(store, cas, service, prepared.checkpoint_id, signer, clock)
    service.mark_warmed(prepared.checkpoint_id, warm_digest)
    corrupt_cas_object(cas, raw_digest)
    with pytest.raises(CorruptObject, match="CAS verification"):
        service.adopt(prepared.checkpoint_id)
    assert service.get(prepared.checkpoint_id).status is ContextCheckpointStatus.WARMED
    assert service.active() is None
    store.close()


def test_checkpoint_sections_reject_raw_secret_and_unbounded_bytes(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, _, _, service = open_service(tmp_path / "context.sqlite", clock)
    source_event = append_source_event(service)
    secret_sections = retained_sections(source_event)
    secret_sections.task_contract["requirements"] = [{"credential": "customer-production-password"}]
    with pytest.raises(ContractViolation, match="raw prompt/source/secret/token"):
        service.prepare(secret_sections, compatibility_group="model-family/v1")

    byte_sections = retained_sections(source_event)
    byte_sections.build_test_state["checks"] = [b"raw tool output"]
    with pytest.raises(ContractViolation, match="JSON|bytes|serial"):
        service.prepare(byte_sections, compatibility_group="model-family/v1")
    store.close()


def test_restart_recovery_fails_closed_when_sections_cas_is_corrupt(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    database = tmp_path / "context.sqlite"
    store, cas, signer, service = open_service(database, clock)
    prepared = service.prepare(
        retained_sections(append_source_event(service)),
        compatibility_group="model-family/v1",
    )
    stored = store.query_one(
        "SELECT sections FROM context_checkpoints WHERE checkpoint_id=?",
        (prepared.checkpoint_id,),
    )
    assert stored is not None
    section_digest = str(json.loads(str(stored[0]))["manifest_digest"])
    store.close()
    corrupt_cas_object(cas, section_digest)

    reopened, _, _, restarted = open_service(database, clock, cas=cas, signer=signer)
    with pytest.raises(CorruptObject, match="CAS verification"):
        restarted.get(prepared.checkpoint_id)
    assert cas.is_quarantined(section_digest)
    reopened.close()


def test_quarantined_authorization_artifact_revokes_warm_result(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    store, cas, signer, service = open_service(tmp_path / "context.sqlite", clock)
    prepared = service.prepare(
        retained_sections(append_source_event(service)),
        compatibility_group="model-family/v1",
    )
    warm_digest, _, authorization_digest = create_warm_evidence(
        store, cas, service, prepared.checkpoint_id, signer, clock
    )
    store.set_artifact_state(TENANT, authorization_digest, ArtifactStorageState.QUARANTINED)
    with pytest.raises(ContractViolation, match="owned and usable"):
        service.mark_warmed(prepared.checkpoint_id, warm_digest)
    store.close()
