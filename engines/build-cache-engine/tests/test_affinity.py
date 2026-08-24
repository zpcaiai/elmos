from __future__ import annotations

import pytest

from elmos_build_cache.affinity import (
    AffinityAuthorizationContext,
    AffinityCandidate,
    AffinityRequest,
    AttestedAffinityCandidate,
    AttestedAffinityRegistry,
    HardRejection,
    RoutingReason,
    StaticAffinityAuthorizationResolver,
    TargetHealth,
    route_affinity,
)
from elmos_build_cache.canonical import digest_of
from elmos_build_cache.errors import ContractViolation, PermissionDenied, ProvenanceInvalid
from elmos_build_cache.prompt_cache import PromptProvider
from elmos_build_cache.security import Ed25519ProvenanceSigner


def d(character: str) -> str:
    return "sha256:" + character * 64


def request(**changes: object) -> AffinityRequest:
    values: dict[str, object] = {
        "tenant_scope_digest": d("1"),
        "authorization_scope_digest": d("2"),
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


def candidate(target_id: str, **changes: object) -> AffinityCandidate:
    values: dict[str, object] = {
        "target_id": target_id,
        "tenant_scope_digest": d("1"),
        "authorization_scope_digest": d("2"),
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


def test_every_compatibility_and_authorization_boundary_is_a_hard_filter() -> None:
    req = request()
    variants = (
        (candidate("tenant", tenant_scope_digest=d("a")), HardRejection.TENANT_MISMATCH),
        (candidate("denied", authorized=False), HardRejection.AUTHORIZATION_DENIED),
        (
            candidate("auth-scope", authorization_scope_digest=d("a")),
            HardRejection.AUTHORIZATION_SCOPE_MISMATCH,
        ),
        (
            candidate("trust", trust_namespace="experimental"),
            HardRejection.TRUST_NAMESPACE_MISMATCH,
        ),
        (
            candidate("provider", provider=PromptProvider.ANTHROPIC),
            HardRejection.PROVIDER_MISMATCH,
        ),
        (candidate("model", model="model-v2"), HardRejection.MODEL_MISMATCH),
        (candidate("effort", effort_profile="low"), HardRejection.EFFORT_MISMATCH),
        (
            candidate("tools", tool_schema_digest=d("a")),
            HardRejection.TOOL_SCHEMA_MISMATCH,
        ),
        (
            candidate("prefix", prefix_compatibility_digest=d("a")),
            HardRejection.PREFIX_COMPATIBILITY_MISMATCH,
        ),
        (candidate("platform", platform_digest=d("a")), HardRejection.PLATFORM_MISMATCH),
        (candidate("capacity", available_capacity=3), HardRejection.INSUFFICIENT_CAPACITY),
        (
            candidate("health", health=TargetHealth.DEGRADED),
            HardRejection.TARGET_NOT_HEALTHY,
        ),
    )
    for item, reason in variants:
        assert reason in item.hard_rejections(req)


def test_cache_value_cannot_override_a_hard_security_filter() -> None:
    denied = candidate(
        "denied",
        authorized=False,
        prompt_cache_value_ms=1_000_000.0,
        environment_value_ms=1_000_000.0,
    )
    safe = candidate("safe", prompt_cache_value_ms=10.0)
    decision = route_affinity(request(), (denied, safe))

    assert decision.selected_target == "safe"
    assert decision.compatible_targets == 1
    assert dict(decision.rejection_counts)[HardRejection.AUTHORIZATION_DENIED.value] == 1


def test_soft_score_is_value_minus_queue_transfer_failure_and_fairness() -> None:
    high_raw_but_slow = candidate(
        "slow",
        prompt_cache_value_ms=100.0,
        queue_delay_ms=80.0,
        transfer_cost_ms=10.0,
    )
    lower_raw_but_fast = candidate(
        "fast",
        environment_value_ms=60.0,
        queue_delay_ms=5.0,
    )
    decision = route_affinity(request(), (high_raw_but_slow, lower_raw_but_fast))

    assert decision.selected_target == "fast"
    assert decision.reason is RoutingReason.ENVIRONMENT_LOCAL
    assert decision.selected_score is not None
    assert decision.selected_score.total_ms == 55.0


def test_equal_scores_use_stable_rendezvous_tie_break_independent_of_input_order() -> None:
    req = request()
    candidates = (
        candidate("worker-a", artifact_value_ms=25.0),
        candidate("worker-b", artifact_value_ms=25.0),
        candidate("worker-c", artifact_value_ms=25.0),
    )
    forward = route_affinity(req, candidates)
    reverse = route_affinity(req, reversed(candidates))
    assert forward.selected_target == reverse.selected_target
    assert [item.target_id for item in forward.scores] == [item.target_id for item in reverse.scores]


def test_no_compatible_target_has_an_explicit_reason_and_rejection_summary() -> None:
    decision = route_affinity(
        request(),
        (
            candidate("wrong-tenant", tenant_scope_digest=d("a")),
            candidate("unhealthy", health=TargetHealth.UNHEALTHY),
        ),
    )
    assert decision.selected_target is None
    assert decision.reason is RoutingReason.NO_COMPATIBLE_TARGET
    assert decision.compatible_targets == 0
    assert decision.rejected_targets == 2
    assert dict(decision.rejection_counts) == {
        HardRejection.TARGET_NOT_HEALTHY.value: 1,
        HardRejection.TENANT_MISMATCH.value: 1,
    }


def test_affinity_key_binds_every_hard_request_identity() -> None:
    baseline = request().affinity_key
    variants = (
        {"tenant_scope_digest": d("a")},
        {"authorization_scope_digest": d("a")},
        {"trust_namespace": "official"},
        {"provider": PromptProvider.ANTHROPIC},
        {"model": "model-v2"},
        {"effort_profile": "low"},
        {"tool_schema_digest": d("a")},
        {"prefix_compatibility_digest": d("a")},
        {"platform_digest": d("a")},
    )
    assert all(request(**change).affinity_key != baseline for change in variants)


def test_duplicate_target_ids_are_rejected_before_routing() -> None:
    with pytest.raises(ContractViolation, match="target IDs must be unique"):
        route_affinity(request(), (candidate("same"), candidate("same")))


def attested(
    target_id: str,
    *,
    signer: Ed25519ProvenanceSigner,
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
    attested_at: float = 10.0,
    expires_at: float = 20.0,
    revoked: bool = False,
) -> AttestedAffinityCandidate:
    item = candidate(target_id)
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


def test_attested_registry_filters_exact_scope_expiry_and_revocation() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    registry = AttestedAffinityRegistry(
        (
            attested("eligible", signer=signer),
            attested("other-tenant", signer=signer, tenant_id="tenant-b"),
            attested("other-project", signer=signer, project_id="project-b"),
            attested("expired", signer=signer, attested_at=1.0, expires_at=9.0),
            attested("revoked", signer=signer, revoked=True),
        ),
        trust_verifier=Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
    )

    selected = registry.candidates("tenant-a", "project-a", request(), now=15.0)

    assert [item.target_id for item in selected] == ["eligible"]


def test_attested_registry_rejects_duplicate_scoped_targets() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    with pytest.raises(ContractViolation, match="duplicate scoped target IDs"):
        AttestedAffinityRegistry(
            (attested("same", signer=signer), attested("same", signer=signer)),
            trust_verifier=Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
        )


def test_attested_record_rejects_caller_style_unauthorized_candidate() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    denied = candidate("denied", authorized=False)
    statement = {
        "schema_version": "1.2.0",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "candidate": denied.attestation_document(),
        "attested_at": 10.0,
        "expires_at": 20.0,
    }
    signed = signer.sign_statement(
        "elmos.cache-affinity-runner-attestation/v1.2",
        statement,
    )
    with pytest.raises(ContractViolation, match="policy-authorized"):
        AttestedAffinityCandidate(
            tenant_id="tenant-a",
            project_id="project-a",
            candidate=denied,
            attestation_digest=digest_of(signed.to_dict()),
            verifier_identity="inventory-verifier",
            attested_at=10.0,
            expires_at=20.0,
            signed_attestation=signed,
        )


def test_registry_rejects_attestation_from_an_untrusted_key() -> None:
    trusted = Ed25519ProvenanceSigner.generate("trusted-inventory")
    attacker = Ed25519ProvenanceSigner.generate("attacker-inventory")
    forged = attested("forged", signer=attacker)

    with pytest.raises(ProvenanceInvalid, match="unknown signing key"):
        AttestedAffinityRegistry(
            (forged,),
            trust_verifier=Ed25519ProvenanceSigner.verifier(trusted.public_keyset()),
        )


def test_registry_revocation_digest_and_authorization_resolver_fail_closed() -> None:
    signer = Ed25519ProvenanceSigner.generate("inventory-verifier")
    record = attested("revoked-by-digest", signer=signer)
    registry = AttestedAffinityRegistry(
        (record,),
        trust_verifier=Ed25519ProvenanceSigner.verifier(signer.public_keyset()),
        revoked_attestation_digests=(record.attestation_digest,),
    )
    assert registry.candidates("tenant-a", "project-a", request(), now=15.0) == ()

    context = AffinityAuthorizationContext(
        tenant_id="tenant-a",
        project_id="project-a",
        principal_digest=d("8"),
        authorization_scope_digest=d("2"),
        allowed=True,
    )
    resolver = StaticAffinityAuthorizationResolver(
        {(d("8"), "tenant-a", "project-a"): context}
    )
    assert resolver.resolve(d("8"), "tenant-a", "project-a", "request-1") == context
    with pytest.raises(PermissionDenied, match="not authorized"):
        resolver.resolve(d("8"), "tenant-a", "project-b", "request-2")
    with pytest.raises(PermissionDenied, match="not authorized"):
        resolver.resolve(d("9"), "tenant-a", "project-a", "request-3")
