"""CACHE-001..003 plus validation, trust and negative-cache policy."""

from __future__ import annotations

import pytest

from conftest import TENANT, digest
from elmos_build_cache.action_cache import ActionCache, CommitRequest, LookupRequest
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import CacheMode, MissReason, TrustNamespace, ValidationLevel
from elmos_build_cache.errors import ConflictError, NondeterministicStage
from elmos_build_cache.manifests import ActionResultManifest, ExecutionMetrics

KEY = digest("7")


def commit(
    action_cache: ActionCache,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    payload: bytes = b"generated output",
    key: str = KEY,
    level: ValidationLevel = ValidationLevel.TEST_VERIFIED,
    namespace: TrustNamespace = TrustNamespace.BRANCH,
    producer: str = "worker-1",
) -> str:
    output = cas.put_bytes(payload)
    manifest = ActionResultManifest(
        action_key=key,
        stage_id="target-code-generation",
        stage_version="1.0.0",
        output_artifacts=(output,),
        required_outputs=(output,),
        metrics=ExecutionMetrics(wall_ms=5000, cpu_ms=4200, compiler_ms=900, model_tokens=12000),
    )
    with store.transaction():
        action_cache.commit(
            CommitRequest(
                tenant_id=TENANT,
                action_key=key,
                manifest=manifest,
                trust_namespace=namespace,
                validation_level=level,
                producer_identity=producer,
            )
        )
    return output


def test_cache_001_exact_repeat_restores_without_execution(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    """CACHE-001: the same ActionKey returns the same immutable outputs."""
    output = commit(action_cache, store, cas)
    result = action_cache.lookup(
        LookupRequest(TENANT, KEY, minimum_validation=ValidationLevel.COMPILE_VERIFIED)
    )
    assert result.hit
    assert result.result is not None
    assert result.result["output_artifacts"] == [output]
    assert cas.get_bytes(output) == b"generated output"
    assert action_cache.statistics(TENANT)["total_hits"] == 1


def test_cache_002_validation_floor_is_enforced(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    """CACHE-002: a lower-validation entry cannot satisfy a stricter consumer."""
    commit(action_cache, store, cas, level=ValidationLevel.COMPILE_VERIFIED)
    result = action_cache.lookup(
        LookupRequest(TENANT, KEY, minimum_validation=ValidationLevel.BEHAVIOR_VERIFIED)
    )
    assert not result.hit
    assert MissReason.VALIDATION_TOO_LOW in result.reasons


def test_cache_003_nondeterminism_quarantines_both_results(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    """CACHE-003: one key, two results -> both quarantined, key poisoned."""
    first = commit(action_cache, store, cas, payload=b"result A")
    second_output = cas.put_bytes(b"result B")
    manifest = ActionResultManifest(KEY, "target-code-generation", "1.0.0", (second_output,))

    with pytest.raises(NondeterministicStage):
        with store.transaction():
            action_cache.commit(
                CommitRequest(TENANT, KEY, manifest, validation_level=ValidationLevel.TEST_VERIFIED)
            )

    # The quarantine survived the rolled-back transaction.
    result = action_cache.lookup(
        LookupRequest(TENANT, KEY, minimum_validation=ValidationLevel.UNVERIFIED)
    )
    assert not result.hit
    assert MissReason.ENTRY_QUARANTINED in result.reasons
    assert cas.is_quarantined(first) is False  # the outputs themselves are untouched
    entry = store.get_action_entry(TENANT, TrustNamespace.BRANCH, KEY)
    assert entry is not None and str(entry.status) == "QUARANTINED"


def test_idempotent_recommit_is_accepted(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    commit(action_cache, store, cas)
    commit(action_cache, store, cas)
    assert action_cache.lookup(LookupRequest(TENANT, KEY)).hit


def test_cross_tenant_lookup_reveals_nothing(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    commit(action_cache, store, cas)
    result = action_cache.lookup(LookupRequest("other-tenant", KEY))
    assert not result.hit
    assert result.reasons == (MissReason.NO_ENTRY,)  # identical to a genuine absence


def test_untrusted_namespace_cannot_satisfy_official_consumer(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    commit(action_cache, store, cas, namespace=TrustNamespace.FORK)
    result = action_cache.lookup(
        LookupRequest(TENANT, KEY, trust_namespace=TrustNamespace.OFFICIAL)
    )
    assert not result.hit
    assert MissReason.TRUST_NAMESPACE_MISMATCH in result.reasons


def test_missing_artifact_is_a_miss_not_a_crash(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    output = commit(action_cache, store, cas)
    cas.delete(output)
    result = action_cache.lookup(LookupRequest(TENANT, KEY))
    assert not result.hit
    assert MissReason.ARTIFACT_MISSING in result.reasons


def test_corrupt_artifact_is_reported_as_corrupt(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    output = commit(action_cache, store, cas)
    cas.quarantine(output, "test corruption")
    result = action_cache.lookup(LookupRequest(TENANT, KEY))
    assert MissReason.ARTIFACT_CORRUPT in result.reasons


def test_restore_cost_can_exceed_recompute(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    commit(action_cache, store, cas, payload=b"z" * 5_000_000)
    result = action_cache.lookup(LookupRequest(TENANT, KEY, estimated_recompute_ms=0.01))
    assert not result.hit
    assert MissReason.RESTORE_COST_EXCEEDS_RECOMPUTE in result.reasons


@pytest.mark.parametrize("mode", [CacheMode.BYPASS, CacheMode.WRITE_ONLY, CacheMode.REFRESH])
def test_modes_that_must_not_read(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore, mode: CacheMode
) -> None:
    commit(action_cache, store, cas)
    result = action_cache.lookup(LookupRequest(TENANT, KEY, mode=mode))
    assert not result.hit
    assert MissReason.POLICY_BYPASS in result.reasons


def test_read_only_mode_forbids_commit(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    manifest = ActionResultManifest(KEY, "s", "1", (cas.put_bytes(b"x"),))
    with store.transaction():
        outcome = action_cache.commit(
            CommitRequest(TENANT, KEY, manifest, mode=CacheMode.READ_ONLY)
        )
    assert not outcome.committed


def test_negative_cache_is_bounded_and_deterministic_only(
    action_cache: ActionCache, store: SqliteMetadataStore, clock: ManualClock
) -> None:
    with store.transaction():
        assert action_cache.commit_negative(
            TENANT, digest("9"), "PARSE_ERROR", deterministic=True, ttl_seconds=60
        ).committed
        assert not action_cache.commit_negative(
            TENANT, digest("a"), "NETWORK_TIMEOUT", deterministic=False
        ).committed

    cached = action_cache.lookup(LookupRequest(TENANT, digest("9")))
    assert cached.detail["negative_cache"] is True
    assert cached.detail["failure_code"] == "PARSE_ERROR"

    clock.advance(120)
    assert MissReason.ENTRY_EXPIRED in action_cache.lookup(LookupRequest(TENANT, digest("9"))).reasons


def test_real_result_supersedes_a_negative_entry(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    with store.transaction():
        action_cache.commit_negative(TENANT, KEY, "PARSE_ERROR", deterministic=True)
    commit(action_cache, store, cas)
    assert action_cache.lookup(LookupRequest(TENANT, KEY)).hit


def test_revocation_makes_an_entry_unusable(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    commit(action_cache, store, cas)
    with store.transaction():
        action_cache.revoke(TENANT, TrustNamespace.BRANCH, KEY, "compromised toolchain")
    assert MissReason.ENTRY_REVOKED in action_cache.lookup(LookupRequest(TENANT, KEY)).reasons


def test_producer_cannot_certify_its_own_output(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    commit(action_cache, store, cas, level=ValidationLevel.COMPILE_VERIFIED, producer="worker-1")
    with pytest.raises(ConflictError), store.transaction():
        action_cache.promote_validation(
            TENANT, TrustNamespace.BRANCH, KEY, ValidationLevel.TEST_VERIFIED, "worker-1"
        )
    with store.transaction():
        promoted = action_cache.promote_validation(
            TENANT, TrustNamespace.BRANCH, KEY, ValidationLevel.TEST_VERIFIED, "independent-ci"
        )
    assert promoted is not None and promoted.validation_level is ValidationLevel.TEST_VERIFIED


def test_manifest_must_declare_the_key_it_is_committed_under(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    manifest = ActionResultManifest(digest("b"), "s", "1", (cas.put_bytes(b"x"),))
    with pytest.raises(ConflictError), store.transaction():
        action_cache.commit(CommitRequest(TENANT, KEY, manifest))


def test_hot_index_is_not_authoritative(
    action_cache: ActionCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    commit(action_cache, store, cas)
    action_cache.lookup(LookupRequest(TENANT, KEY))
    with store.transaction():
        action_cache.quarantine(TENANT, TrustNamespace.BRANCH, KEY, "manual")
    # Even though the hot index saw a hit, the store decides.
    assert not action_cache.lookup(LookupRequest(TENANT, KEY)).hit
