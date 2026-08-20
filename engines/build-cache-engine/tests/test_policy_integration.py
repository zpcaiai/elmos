"""SOTA-19..27: the portfolio wired into the engine, not sitting beside it.

Each test here answers the question "does this actually take effect on a real
call path?" -- configuration that a loader accepts, an in-process index whose
evictions are the policy's evictions, a GC plan whose ordering the policy
decided, and a CLI an operator can get evidence out of.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from conftest import TENANT
from elmos_build_cache.action_cache import ActionCache, HotIndex
from elmos_build_cache.cache_policy import CacheObject, PolicyName, create_policy
from elmos_build_cache.cache_trace import Access, Tier, key_hash
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.cli import main
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import CacheConfig, PolicyConfig, load_config, load_config_mapping
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.gc import GarbageCollector, RetentionPolicy

ALL_POLICIES = tuple(name.value for name in PolicyName)
REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# SOTA-19: configuration
# --------------------------------------------------------------------------
def test_sota_19_policy_section_is_typed_and_total() -> None:
    """A policy nobody can name is a policy nobody can typo into production."""
    default = CacheConfig().policy
    assert default.l1_policy in ALL_POLICIES
    assert default.adaptive_selection is False, "adaptive switching must be opt-in"
    assert default.learned_tuning is False, "learned tuning must be opt-in"
    assert default.learned_shadow_only is True

    loaded = load_config_mapping(
        {"policy": {"l1_policy": "S3_FIFO", "trace_sample_rate": 0.5, "adaptive_selection": True}}
    )
    assert loaded.policy.l1_policy == "S3_FIFO"
    assert loaded.policy.trace_sample_rate == pytest.approx(0.5)
    assert loaded.policy.l0_policy == default.l0_policy, "unset keys keep their defaults"


@pytest.mark.parametrize(
    "section",
    [
        {"l1_policy": "NOT_A_POLICY"},
        {"objective_profile": "FAST"},
        {"trace_sample_rate": 2.0},
        {"learned_canary_fraction": -0.1},
        {"learned_canary_fraction": 0.1},  # shadow_only is still true
        {"minimum_dwell_events": 0},
        {"prefetch_horizon": 0},
        {"improvement_margin": -0.01},
        {"typo_key": True},
        {"trace_sample_rate": "0.5"},
    ],
)
def test_sota_19_bad_policy_configuration_is_refused(section: dict[str, object]) -> None:
    with pytest.raises(ContractViolation):
        load_config_mapping({"policy": section})


def test_sota_19_shipped_configuration_carries_the_policy_section() -> None:
    """The default deployment ships the section, so it is reviewable in git."""
    config = load_config(REPO_ROOT / "config" / "elmos-cache.yaml")
    assert config.policy.enabled is True
    assert config.policy.l0_policy in ALL_POLICIES
    assert config.policy.fallback == PolicyName.SIEVE.value


# --------------------------------------------------------------------------
# SOTA-20: invalidation is not eviction
# --------------------------------------------------------------------------
@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_sota_20_forget_is_accounted_separately_from_eviction(policy_name: str) -> None:
    """The correctness plane removing an entry is not a capacity decision."""
    policy = create_policy(policy_name, 10_000)
    policy.access(CacheObject("revoked", 1_000))
    assert policy.contains("revoked")
    before = policy.counters.evictions

    assert policy.forget("revoked") is True
    assert policy.contains("revoked") is False
    assert policy.used_bytes == 0
    assert policy.counters.evictions == before, "an invalidation is not an eviction"
    assert policy.counters.invalidations == 1
    assert policy.forget("revoked") is False, "forgetting twice is a no-op"


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_sota_20_a_half_empty_cache_admits(policy_name: str) -> None:
    """No policy may reject a newcomer while it still has room.

    W-TinyLFU got this wrong once: it ran the frequency contest against an
    incumbent that was not competing for the slot, so a cold cache never warmed.
    """
    policy = create_policy(policy_name, 100)
    for index in range(50):
        policy.access(CacheObject(f"k{index}", 1))
    assert len(policy.keys()) == 50, "50 one-byte objects fit in 100 bytes"


# --------------------------------------------------------------------------
# SOTA-21: the hot index is a real call path
# --------------------------------------------------------------------------
@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_sota_21_hot_index_never_drifts_from_its_policy(policy_name: str) -> None:
    """If the index held a key the policy evicted, the policy would be fiction."""
    policy = create_policy(policy_name, 16)
    index = HotIndex(capacity=16, policy=policy)
    for step in range(200):
        key = f"key-{step % 40}"
        if index.get(TENANT, "branch", key) is None:
            index.put(TENANT, "branch", key, f"sha256:{step:064d}")

    held = {index._policy_key((TENANT, "branch", f"key-{n}")) for n in range(40)}
    resident_in_index = {
        index._policy_key(composite) for composite in index._entries
    }
    assert resident_in_index <= held
    assert resident_in_index == set(policy.keys())
    assert len(index._entries) <= 16
    assert index.statistics()["policy"] == policy_name


def test_sota_21_hot_index_invalidation_reaches_the_policy() -> None:
    policy = create_policy("SIEVE", 64)
    index = HotIndex(capacity=64, policy=policy)
    index.put(TENANT, "branch", "action", "sha256:" + "a" * 64)
    assert policy.contains(key_hash("\x1f".join((TENANT, "branch", "action"))))

    index.invalidate(TENANT, "branch", "action")
    assert policy.contains(key_hash("\x1f".join((TENANT, "branch", "action")))) is False
    assert policy.counters.invalidations == 1


def test_sota_21_disabled_policy_gives_back_the_built_in_lru() -> None:
    """Off must be off, not a differently-shaped policy."""
    disabled = HotIndex.from_config(dataclasses.replace(PolicyConfig(), enabled=False))
    assert disabled.policy is None
    assert disabled.statistics()["policy"] == "LRU_BUILTIN"
    assert HotIndex.from_config(PolicyConfig()).statistics()["policy"] == PolicyConfig().l0_policy


def test_sota_21_action_cache_lookup_still_works_under_every_policy(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    """The index is an accelerator: swapping its policy cannot change answers."""
    from elmos_build_cache.action_cache import LookupRequest
    from elmos_build_cache.enums import TrustNamespace

    results = []
    for policy_name in ALL_POLICIES:
        cache = ActionCache(
            store, cas, clock, hot_index=HotIndex(8, create_policy(policy_name, 8))
        )
        request = LookupRequest(TENANT, "sha256:" + "b" * 64, TrustNamespace.BRANCH)
        results.append(cache.lookup(request).missed)
    assert results == [True] * len(ALL_POLICIES)


# --------------------------------------------------------------------------
# SOTA-22: GC ordering
# --------------------------------------------------------------------------
def _register(store: SqliteMetadataStore, cas: ContentAddressableStore, payload: bytes, **metadata):
    digest = cas.put_bytes(payload)
    with store.transaction():
        store.register_artifact(
            TENANT,
            digest,
            cas.info(digest).size,
            "application/octet-stream",
            "blob",
            metadata=metadata,
        )
    return digest


def test_sota_22_replacement_policy_orders_but_never_protects(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock, run: str
) -> None:
    """The policy reorders deletion candidates; the root set decides membership."""
    digests = [
        _register(store, cas, f"artifact-{n}".encode() * (n + 1) * 64, recompute_cost_ms=10 * n)
        for n in range(6)
    ]
    retention = RetentionPolicy(grace_hours=1, quota_bytes=1024**3)

    plain = GarbageCollector(store, cas, TENANT, retention, clock)
    with store.transaction():
        baseline = plain.plan()

    ranked = GarbageCollector(
        store, cas, TENANT, retention, clock, replacement=create_policy("GDSF", 4_096)
    )
    with store.transaction():
        with_policy = ranked.plan()

    assert {c.digest for c in baseline.candidates} == {c.digest for c in with_policy.candidates}
    assert set(with_policy.candidates and digests) == set(digests)
    assert all("policy=GDSF" in candidate.reason for candidate in with_policy.candidates)
    assert with_policy.reclaimable_bytes == baseline.reclaimable_bytes


def test_sota_22_protected_roots_are_fed_to_the_policy_first(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock, run: str
) -> None:
    """A protected digest is never a candidate, whatever the policy thinks of it."""
    from elmos_build_cache.db.records import CheckpointRecord
    from elmos_build_cache.enums import CheckpointStatus

    keep = _register(store, cas, b"referenced by a checkpoint")
    drop = _register(store, cas, b"orphan" * 400, recompute_cost_ms=1, expected_reuse=0.001)
    with store.transaction():
        store.insert_checkpoint(
            CheckpointRecord(
                "cp-policy", TENANT, "project-test", run, "gen", 1, 1, 1, keep, 10, CheckpointStatus.ACTIVE
            )
        )
        store.add_artifact_ref(TENANT, "checkpoint", "cp-policy", keep, "artifact")

    policy = create_policy("SIEVE", 4_096)
    gc = GarbageCollector(
        store, cas, TENANT, RetentionPolicy(grace_hours=1, quota_bytes=1024**3), clock,
        replacement=policy,
    )
    with store.transaction():
        plan = gc.plan()

    assert keep not in {candidate.digest for candidate in plan.candidates}
    assert drop in {candidate.digest for candidate in plan.candidates}
    assert policy.is_protected(keep), "the root set is declared to the policy before it is asked"


# --------------------------------------------------------------------------
# SOTA-23: the operator surface
# --------------------------------------------------------------------------
def _cli(capsys: pytest.CaptureFixture[str], base: Path, *argv: str) -> dict:
    assert main(["--base", str(base), "--tenant", TENANT, *argv]) == 0
    return json.loads(capsys.readouterr().out)


def test_sota_23_policy_show_reports_what_is_configured(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    payload = _cli(capsys, tmp_path, "policy", "show")
    assert payload["tiers"]["L1"] in ALL_POLICIES
    assert payload["available_policies"] == list(ALL_POLICIES)
    assert payload["configuration_digest"].startswith("sha256:")


def test_sota_23_policy_benchmark_produces_a_comparable_report(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    payload = _cli(
        capsys, tmp_path, "policy", "benchmark", "--workload", "monorepo-scan",
        "--capacity-fraction", "0.05",
    )
    policies = {candidate["policy"] for candidate in payload["candidates"]}
    assert policies == set(ALL_POLICIES)
    capacities = {candidate["configuration"]["capacity_bytes"] for candidate in payload["candidates"]}
    assert len(capacities) == 1, "every arm must be measured at the same capacity"


def test_sota_23_policy_select_explains_itself(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    payload = _cli(capsys, tmp_path, "policy", "select", "--workload", "monorepo-scan")
    assert payload["policy"] in ALL_POLICIES
    assert payload["reason_codes"], "a recommendation with no reason is not usable at 3am"
    assert "request_count" in payload["features"]
    assert isinstance(payload["agrees_with_configuration"], bool)


def test_sota_23_certification_refuses_without_the_rollout_evidence(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    refused = _cli(
        capsys, tmp_path, "policy", "certify", "--workload", "monorepo-scan",
        "--candidate", "W_TINY_LFU", "--capacity-fraction", "0.05", "--elmos-commit", "deadbeef",
    )
    assert refused["certified"] is False
    assert "NO_ROLLBACK_EXERCISE" in refused["reasons"]
    assert refused["ephemeral_signing_key"] is True

    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"events": 12_000, "divergences": 0}), encoding="utf-8")
    granted = _cli(
        capsys, tmp_path, "policy", "certify", "--workload", "monorepo-scan",
        "--candidate", "W_TINY_LFU", "--capacity-fraction", "0.05", "--elmos-commit", "deadbeef",
        "--shadow-evidence", str(evidence),
        "--canary-evidence", str(evidence),
        "--rollback-evidence", str(evidence),
    )
    assert granted["certified"] is True
    assert granted["signed"]["algorithm"] == "ed25519"


def test_sota_23_trace_round_trips_through_the_operator_surface(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "trace.jsonl"
    written = _cli(
        capsys, tmp_path, "trace", "generate", "--workload", "monorepo-scan", "--out", str(out)
    )
    assert out.exists()
    verified = _cli(capsys, tmp_path, "trace", "verify", "--trace", str(out))
    assert verified["privacy_clean"] is True
    assert verified["leakage"] == []
    # The label differs (workload name vs file stem), so compare the events
    # themselves: a round trip that changed one byte would move these.
    assert verified["manifest"]["split_digests"] == written["manifest"]["split_digests"]
    assert verified["manifest"]["events"] == written["manifest"]["events"]


def test_sota_23_workloads_are_discoverable(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    payload = _cli(capsys, tmp_path, "trace", "workloads")
    names = {entry["name"] for entry in payload["workloads"]}
    assert {"identical-rerun", "monorepo-scan", "dag-known-future"} <= names


# --------------------------------------------------------------------------
# SOTA-24: the configuration switches drive real behaviour, not a display
# --------------------------------------------------------------------------
def _plane(**overrides: object):
    from elmos_build_cache.policy_plane import PolicyPlane
    from elmos_build_cache.security import Ed25519ProvenanceSigner

    config = dataclasses.replace(PolicyConfig(), **overrides)  # type: ignore[arg-type]
    return PolicyPlane.from_config(
        config,
        tenant_id=TENANT,
        capacity_bytes=1_000_000,
        signer=Ed25519ProvenanceSigner.generate(),
    )


def test_sota_24_every_switch_is_off_by_default_and_the_plane_is_inert() -> None:
    """The shipped default must behave exactly as it did before the plane existed."""
    plane = _plane()
    assert plane.active is False
    assert plane.record_access(
        action_key="sha256:" + "a" * 64,
        tier=Tier.L1_LOCAL_CAS,
        access=Access.GET,
        hit=True,
        size_bytes=1,
        stage_class="gen",
        recompute_ms=1.0,
        restore_ms=0.0,
    ) is None
    assert plane.admit(
        action_key="sha256:" + "a" * 64,
        size_bytes=1,
        stage_class="gen",
        recompute_ms=1.0,
        restore_ms=0.0,
        validation_level="UNVERIFIED",
    ) is None
    assert plane.plan_prefetch(0) == []


@pytest.mark.parametrize(
    ("switch", "capability"),
    [
        ("trace_capture", "trace_capture"),
        ("admission_enabled", "admission"),
        ("adaptive_selection", "adaptive_selection"),
        ("learned_tuning", "learned_tuning"),
    ],
)
def test_sota_24_each_switch_turns_on_exactly_its_own_capability(
    switch: str, capability: str
) -> None:
    """A switch that reports itself on but does nothing is worse than no switch."""
    plane = _plane(**{switch: True})
    capabilities = plane.report()["capabilities"]
    assert capabilities[capability] is True
    assert plane.active is True
    assert [name for name, on in capabilities.items() if on] == [capability]


def test_sota_24_admission_refuses_an_entry_that_is_not_worth_recording() -> None:
    """Restore costing as much as recompute means the entry buys nothing."""
    plane = _plane(admission_enabled=True)
    worthwhile = plane.admit(
        action_key="sha256:" + "a" * 64,
        size_bytes=50_000,
        stage_class="target-code-generation",
        recompute_ms=9_000.0,
        restore_ms=20.0,
        validation_level="TEST_VERIFIED",
    )
    pointless = plane.admit(
        action_key="sha256:" + "b" * 64,
        size_bytes=50_000,
        stage_class="target-code-generation",
        recompute_ms=100.0,
        restore_ms=95.0,
        validation_level="UNVERIFIED",
    )
    assert worthwhile is not None and worthwhile.admitted is True
    assert pointless is not None and pointless.admitted is False
    assert "BYPASS_RESTORE_SLOWER_THAN_RECOMPUTE" in pointless.reasons
    assert plane.report()["admission"]["rejected_by_value"] == 1


def test_sota_24_learned_tuning_without_a_signer_is_refused() -> None:
    """An unsigned model registry cannot verify what it loads, so it is refused."""
    from elmos_build_cache.policy_plane import PolicyPlane

    with pytest.raises(ContractViolation):
        PolicyPlane.from_config(
            dataclasses.replace(PolicyConfig(), learned_tuning=True), tenant_id=TENANT
        )


def test_sota_24_a_trace_captured_here_is_usable_downstream() -> None:
    """Capture has to produce a corpus the rest of the plane can actually read."""
    plane = _plane(trace_capture=True, trace_sample_rate=1.0, adaptive_selection=True)
    for step in range(300):
        plane.record_access(
            action_key=f"sha256:{step % 40:064d}",
            tier=Tier.L1_LOCAL_CAS,
            access=Access.GET,
            hit=step % 3 != 0,
            size_bytes=4096,
            stage_class="target-code-generation",
            recompute_ms=900.0,
            restore_ms=12.0,
        )
    assert plane.report()["trace"]["captured"] == 300

    recommendation = plane.recommend()
    assert recommendation["features"]["request_count"] == 300
    assert recommendation["selection"]["policy"] in ALL_POLICIES
    assert recommendation["selection"]["reason_codes"]


def test_sota_24_the_plane_recommends_but_never_switches_a_live_policy() -> None:
    """Changing a replacement algorithm mid-run makes the run uninterpretable."""
    plane = _plane(trace_capture=True, trace_sample_rate=1.0, adaptive_selection=True)
    assert plane.orchestrator is not None
    before = plane.orchestrator.policy.name.value
    for step in range(400):
        plane.record_access(
            action_key=f"sha256:{step:064d}",
            tier=Tier.L1_LOCAL_CAS,
            access=Access.GET,
            hit=False,
            size_bytes=4096,
            stage_class="scan",
            recompute_ms=10.0,
            restore_ms=1.0,
        )
    plane.recommend()
    assert plane.orchestrator.policy.name.value == before, (
        "the live policy must not move during a run"
    )
