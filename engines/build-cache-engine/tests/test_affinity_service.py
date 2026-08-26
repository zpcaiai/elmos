"""Focused affinity decision-to-placement tests with a local recording sink."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import pytest

from elmos_build_cache.affinity import (
    AffinityAuthorizationContext,
    AffinityCandidate,
    AffinityRequest,
    AttestedAffinityCandidate,
    AttestedAffinityRegistry,
    StaticAffinityAuthorizationResolver,
    TargetHealth,
)
from elmos_build_cache.affinity_service import (
    AffinityPlacementService,
    AttestedRegistryInventorySource,
    PlacementCommand,
    PlacementDisposition,
    PlacementOutcome,
    PlacementSinkResult,
    RunnerInventorySnapshot,
    verify_affinity_placement_receipt,
)
from elmos_build_cache.canonical import digest_of
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.errors import ContractViolation, IdempotencyConflict, PermissionDenied
from elmos_build_cache.prompt_cache import PromptProvider
from elmos_build_cache.security import Ed25519ProvenanceSigner

TENANT = "tenant-a"
PROJECT = "project-a"
PRINCIPAL = "sha256:" + "8" * 64
AUTHORIZATION = "sha256:" + "2" * 64
NOW = 1_760_000_000.0


def d(character: str) -> str:
    return "sha256:" + character * 64


def tenant_scope(tenant_id: str = TENANT, project_id: str = PROJECT) -> str:
    return digest_of({"tenant_id": tenant_id, "project_id": project_id})


def request(**changes: object) -> AffinityRequest:
    values: dict[str, object] = {
        "tenant_scope_digest": tenant_scope(),
        "authorization_scope_digest": AUTHORIZATION,
        "trust_namespace": "branch",
        "provider": PromptProvider.OPENAI,
        "model": "model-v1",
        "effort_profile": "high",
        "tool_schema_digest": d("3"),
        "prefix_compatibility_digest": d("4"),
        "platform_digest": d("5"),
        "required_capacity": 4,
    }
    values.update(changes)
    return AffinityRequest(**values)  # type: ignore[arg-type]


def candidate(
    target_id: str,
    *,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    **changes: object,
) -> AffinityCandidate:
    values: dict[str, object] = {
        "target_id": target_id,
        "tenant_scope_digest": tenant_scope(tenant_id, project_id),
        "authorization_scope_digest": AUTHORIZATION,
        "authorized": True,
        "trust_namespace": "branch",
        "provider": PromptProvider.OPENAI,
        "model": "model-v1",
        "effort_profile": "high",
        "tool_schema_digest": d("3"),
        "prefix_compatibility_digest": d("4"),
        "platform_digest": d("5"),
        "available_capacity": 8,
        "health": TargetHealth.HEALTHY,
    }
    values.update(changes)
    return AffinityCandidate(**values)  # type: ignore[arg-type]


def attested(
    target_id: str,
    *,
    signer: Ed25519ProvenanceSigner,
    tenant_id: str = TENANT,
    project_id: str = PROJECT,
    attested_at: float = NOW - 60.0,
    expires_at: float = NOW + 60.0,
    revoked: bool = False,
    **changes: object,
) -> AttestedAffinityCandidate:
    item = candidate(
        target_id,
        tenant_id=tenant_id,
        project_id=project_id,
        **changes,
    )
    statement = {
        "schema_version": "1.2.0",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "candidate": item.attestation_document(),
        "attested_at": attested_at,
        "expires_at": expires_at,
    }
    signed = signer.sign_statement(
        "elmos.cache-affinity-runner-attestation/v1.2",
        statement,
    )
    return AttestedAffinityCandidate(
        tenant_id=tenant_id,
        project_id=project_id,
        candidate=item,
        attestation_digest=digest_of(signed.to_dict()),
        verifier_identity=signed.key_id,
        attested_at=attested_at,
        expires_at=expires_at,
        signed_attestation=signed,
        revoked=revoked,
    )


def resolver() -> StaticAffinityAuthorizationResolver:
    context = AffinityAuthorizationContext(
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        authorization_scope_digest=AUTHORIZATION,
        allowed=True,
    )
    return StaticAffinityAuthorizationResolver({(PRINCIPAL, TENANT, PROJECT): context})


def inventory_source(
    records: tuple[AttestedAffinityCandidate, ...],
    signer: Ed25519ProvenanceSigner,
    *,
    revoked_digests: tuple[str, ...] = (),
) -> AttestedRegistryInventorySource:
    registry = AttestedAffinityRegistry(
        records,
        trust_verifier=Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
        revoked_attestation_digests=revoked_digests,
    )
    return AttestedRegistryInventorySource(
        registry,
        source_identity_digest=d("f"),
    )


@dataclass
class RecordingPlacementSink:
    retryable_rejections: set[str] = field(default_factory=set)
    final_rejections: set[str] = field(default_factory=set)
    commands: list[PlacementCommand] = field(default_factory=list)

    def place(self, command: PlacementCommand) -> PlacementSinkResult:
        self.commands.append(command)
        if command.target_id in self.retryable_rejections:
            disposition = PlacementDisposition.REJECTED
            retryable = True
            placement_id = None
            reason = "TARGET_BUSY"
        elif command.target_id in self.final_rejections:
            disposition = PlacementDisposition.REJECTED
            retryable = False
            placement_id = None
            reason = "TARGET_REFUSED"
        else:
            disposition = PlacementDisposition.ACCEPTED
            retryable = False
            placement_id = f"placement-{command.attempt}"
            reason = "PLACEMENT_ACCEPTED"
        receipt_digest = digest_of(
            {
                "command": command.to_dict(),
                "disposition": disposition.value,
                "reason": reason,
                "placement_id": placement_id,
            }
        )
        return PlacementSinkResult(
            disposition=disposition,
            reason_code=reason,
            command_digest=command.command_digest,
            sink_receipt_digest=receipt_digest,
            placement_id=placement_id,
            retryable=retryable,
        )


def service(
    source: AttestedRegistryInventorySource,
    sink: RecordingPlacementSink,
    *,
    max_attempts: int = 3,
) -> AffinityPlacementService:
    return AffinityPlacementService(
        inventory_source=source,
        placement_sink=sink,
        authorization_resolver=resolver(),
        clock=ManualClock(NOW),
        max_attempts=max_attempts,
    )


def place(runtime: AffinityPlacementService, routing: AffinityRequest | None = None):
    return runtime.place(
        tenant_id=TENANT,
        project_id=PROJECT,
        principal_digest=PRINCIPAL,
        request_id="request-1",
        request=request() if routing is None else routing,
    )


def test_selected_candidate_is_the_candidate_the_sink_actually_places() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    high = attested("worker-high", signer=signer, prompt_cache_value_ms=90.0)
    low = attested("worker-low", signer=signer, environment_value_ms=20.0)
    sink = RecordingPlacementSink()

    result = place(service(inventory_source((high, low), signer), sink))

    assert result.placed is True
    assert result.receipt.outcome is PlacementOutcome.PLACED
    assert result.receipt.selected_target == "worker-high"
    assert [item.target_id for item in sink.commands] == ["worker-high"]
    assert sink.commands[0].inventory_digest == result.receipt.inventory_digest
    verify_affinity_placement_receipt(result.receipt.to_dict())


def test_replaying_a_placement_request_is_side_effect_free() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    eligible = attested("worker", signer=signer, prompt_cache_value_ms=20.0)
    sink = RecordingPlacementSink()
    runtime = service(inventory_source((eligible,), signer), sink)

    first = place(runtime)
    replay = place(runtime)

    assert replay == first
    assert len(sink.commands) == 1

    changed = request(required_capacity=2)
    with pytest.raises(IdempotencyConflict, match="different routing inputs"):
        place(runtime, changed)


def test_expired_revoked_and_foreign_inventory_yields_zero_dispatch() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    expired = attested(
        "expired",
        signer=signer,
        attested_at=NOW - 120.0,
        expires_at=NOW - 1.0,
    )
    revoked = attested("revoked", signer=signer, revoked=True)
    foreign_tenant = attested("foreign-tenant", signer=signer, tenant_id="tenant-b")
    foreign_project = attested("foreign-project", signer=signer, project_id="project-b")
    sink = RecordingPlacementSink()

    result = place(
        service(
            inventory_source(
                (expired, revoked, foreign_tenant, foreign_project),
                signer,
            ),
            sink,
        )
    )

    assert result.placed is False
    assert result.receipt.outcome is PlacementOutcome.NO_COMPATIBLE_TARGET
    assert result.receipt.attempts == ()
    assert sink.commands == []


def test_retryable_sink_rejection_reroutes_to_a_distinct_candidate() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    first = attested("worker-first", signer=signer, prompt_cache_value_ms=100.0)
    second = attested("worker-second", signer=signer, prompt_cache_value_ms=50.0)
    sink = RecordingPlacementSink(retryable_rejections={"worker-first"})

    result = place(service(inventory_source((first, second), signer), sink, max_attempts=2))

    assert [item.target_id for item in sink.commands] == ["worker-first", "worker-second"]
    assert result.receipt.outcome is PlacementOutcome.PLACED
    assert result.receipt.selected_target == "worker-second"
    assert [item.disposition for item in result.receipt.attempts] == [
        PlacementDisposition.REJECTED,
        PlacementDisposition.ACCEPTED,
    ]
    assert len({item.target_id for item in result.receipt.attempts}) == 2


def test_retry_is_bounded_and_no_candidate_is_dispatched_twice() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    records = tuple(
        attested(
            f"worker-{index}",
            signer=signer,
            prompt_cache_value_ms=100.0 - index,
        )
        for index in range(3)
    )
    sink = RecordingPlacementSink(retryable_rejections={item.candidate.target_id for item in records})

    result = place(service(inventory_source(records, signer), sink, max_attempts=2))

    assert result.receipt.outcome is PlacementOutcome.RETRY_EXHAUSTED
    assert result.receipt.selected_target is None
    assert len(sink.commands) == 2
    assert len({item.target_id for item in sink.commands}) == 2


def test_cross_tenant_request_and_foreign_source_candidate_fail_before_dispatch() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    eligible = attested("worker", signer=signer)
    sink = RecordingPlacementSink()
    runtime = service(inventory_source((eligible,), signer), sink)

    with pytest.raises(PermissionDenied, match="tenant scope"):
        place(runtime, request(tenant_scope_digest=tenant_scope("tenant-b", PROJECT)))
    assert sink.commands == []

    foreign = candidate("foreign", tenant_id="tenant-b")

    class ForeignSource:
        def snapshot(
            self,
            tenant_id: str,
            project_id: str,
            routing: AffinityRequest,
            *,
            now: float,
        ) -> RunnerInventorySnapshot:
            return RunnerInventorySnapshot(
                tenant_id=tenant_id,
                project_id=project_id,
                source_identity_digest=d("e"),
                observed_at=now,
                affinity_key=routing.affinity_key,
                candidates=(foreign,),
            )

    runtime_with_bad_source = AffinityPlacementService(
        inventory_source=ForeignSource(),
        placement_sink=sink,
        authorization_resolver=resolver(),
        clock=ManualClock(NOW),
    )
    with pytest.raises(ContractViolation, match="foreign"):
        place(runtime_with_bad_source)
    assert sink.commands == []


def test_placement_receipt_tampering_is_rejected() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    eligible = attested("worker", signer=signer, prompt_cache_value_ms=20.0)
    sink = RecordingPlacementSink()
    result = place(service(inventory_source((eligible,), signer), sink))
    tampered = copy.deepcopy(result.receipt.to_dict())
    tampered["inventory_digest"] = d("0")

    with pytest.raises(ContractViolation, match="receipt digest"):
        verify_affinity_placement_receipt(tampered)


def test_nested_attempt_command_tampering_is_rejected_even_with_rehashed_receipt() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    eligible = attested("worker", signer=signer, prompt_cache_value_ms=20.0)
    result = place(service(inventory_source((eligible,), signer), RecordingPlacementSink()))
    tampered = copy.deepcopy(result.receipt.to_dict())
    tampered["attempts"][0]["target_id"] = "worker-forged"
    tampered["receipt_digest"] = digest_of(
        {key: value for key, value in tampered.items() if key != "receipt_digest"}
    )

    with pytest.raises(ContractViolation, match="command binding"):
        verify_affinity_placement_receipt(tampered)
