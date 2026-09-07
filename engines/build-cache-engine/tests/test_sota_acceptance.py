"""SOTA-01 .. SOTA-18: the acceptance matrix, executed.

Each test is named for the row it discharges in
`tests/acceptance/sota-cache-acceptance-matrix.md`. Where a row asks for a
comparison, the comparison runs here at equal capacity on the same request
sequence; where it asks for a refusal, the refusal is triggered rather than
described.

Two rows -- correctness and staging -- are about the *correctness plane*, and
they are here on purpose: the whole premise of adding adaptive policy to ELMOS
is that it cannot touch what makes a cache entry valid. A policy that improved
the hit ratio by weakening any of these would be a regression, not a result.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from elmos_build_cache.action_cache import ActionCache, LookupRequest
from elmos_build_cache.cache_admission import AdmissionController, TenantQuota
from elmos_build_cache.cache_policy import (
    CacheObject,
    PolicyName,
    create_policy,
    restore_policy,
)
from elmos_build_cache.cache_simulator import (
    BenchmarkGates,
    ObjectiveProfile,
    benchmark,
    recommended_capacity,
    replay,
    weighted_value,
)
from elmos_build_cache.cache_trace import (
    GENERATORS,
    assert_privacy,
    detect_drift,
    generate_monorepo_scan,
    workload_features,
)
from elmos_build_cache.dag_prefetch import (
    Artifact,
    FutureUseIndex,
    PrefetchBudget,
    PrefetchPlanner,
    restore_or_recompute,
)
from elmos_build_cache.enums import CacheMode, TrustNamespace, ValidationLevel
from elmos_build_cache.learned_control import (
    S3FIFO_FALLBACK,
    ControlReason,
    LearnedModel,
    LearningAugmentedController,
    ModelRegistry,
    OutOfDistributionDetector,
)
from elmos_build_cache.policy_certification import (
    CertificationContext,
    CertificationGates,
    RolloutPhase,
    RolloutPlan,
    benchmark_matrix,
    certify_policy,
    expired_reasons,
    verify_certificate,
)
from elmos_build_cache.policy_orchestrator import (
    PINNED_FALLBACK,
    PolicyOrchestrator,
    SelectionReason,
)
from elmos_build_cache.security import Ed25519ProvenanceSigner

BASELINES = ("LRU", "SIEVE", "S3_FIFO", "W_TINY_LFU", "GDSF")


# ==========================================================================
# SOTA-01 deterministic replay
# ==========================================================================
def test_sota_01_the_same_trace_and_config_replay_identically_three_times() -> None:
    corpus = GENERATORS["interface-edit"]()
    capacity = recommended_capacity(corpus.events)
    runs = []
    for _ in range(3):
        result = replay("S3_FIFO", corpus.events, capacity)
        runs.append(
            (
                result.hits,
                result.misses,
                result.evictions,
                result.hit_bytes,
                round(result.avoided_recompute_ms, 6),
                dict(sorted(result.reasons.items())),
            )
        )
    assert runs[0] == runs[1] == runs[2]


# ==========================================================================
# SOTA-02 strong baselines
# ==========================================================================
@pytest.mark.parametrize("policy", BASELINES)
def test_sota_02_every_baseline_completes_without_a_correctness_failure(policy: str) -> None:
    for name in ("monorepo-scan", "large-binaries", "multi-tenant-burst", "identical-rerun"):
        corpus = GENERATORS[name]()
        result = replay(policy, corpus.events, recommended_capacity(corpus.events))
        assert result.correctness_failures == 0, f"{policy} on {name}"
        assert result.requests == len(corpus.events)


# ==========================================================================
# SOTA-03 one-hit scan
# ==========================================================================
def test_sota_03_the_selected_policy_does_not_underperform_on_a_scan() -> None:
    """A scan is where a recency-only cache collapses; the selection must not."""
    corpus = generate_monorepo_scan(files=4000)
    capacity = recommended_capacity(corpus.events, 0.05)
    results = {
        policy: replay(policy, corpus.events, capacity) for policy in ("LRU", "SIEVE", "S3_FIFO")
    }
    selection = workload_features(corpus.events)
    from elmos_build_cache.policy_orchestrator import RuleSelector

    chosen = RuleSelector().select(selection).policy
    chosen_value = weighted_value(replay(chosen, corpus.events, capacity), ObjectiveProfile.BALANCED)
    scan_resistant = max(
        weighted_value(results["SIEVE"], ObjectiveProfile.BALANCED),
        weighted_value(results["S3_FIFO"], ObjectiveProfile.BALANCED),
    )
    assert chosen_value >= scan_resistant * 0.95
    assert chosen_value > weighted_value(results["LRU"], ObjectiveProfile.BALANCED)


# ==========================================================================
# SOTA-04 high temporal reuse
# ==========================================================================
def test_sota_04_frequency_admission_beats_lru_on_repeated_reuse() -> None:
    corpus = GENERATORS["identical-rerun"]()
    capacity = recommended_capacity(corpus.events, 0.2)
    lru = weighted_value(replay("LRU", corpus.events, capacity), ObjectiveProfile.DEV_SPEED)
    best = max(
        weighted_value(replay(policy, corpus.events, capacity), ObjectiveProfile.DEV_SPEED)
        for policy in ("W_TINY_LFU", "GDSF")
    )
    assert best > lru


# ==========================================================================
# SOTA-05 heterogeneous size
# ==========================================================================
def test_sota_05_size_aware_policies_are_measured_at_equal_capacity() -> None:
    corpus = GENERATORS["large-binaries"]()
    capacity = recommended_capacity(corpus.events, 0.2)
    report = benchmark(corpus, capacity_bytes=capacity)
    capacities = {candidate["configuration"]["capacity_bytes"] for candidate in report["candidates"]}
    assert capacities == {capacity}, "a capacity mismatch would invalidate the comparison"
    for candidate in report["candidates"]:
        assert "byte_hit_ratio" in candidate["metrics"]
        assert "avoided_compute_ratio" in candidate["metrics"]
    sizes = workload_features(corpus.events)
    assert sizes["size_cv"] > 1.5, "this workload is supposed to be heterogeneous"


# ==========================================================================
# SOTA-06 expensive sparse reuse
# ==========================================================================
def test_sota_06_the_cost_aware_policy_keeps_the_expensive_artifacts() -> None:
    corpus = GENERATORS["identical-rerun"]()
    capacity = recommended_capacity(corpus.events, 0.2)
    gdsf = replay("GDSF", corpus.events, capacity)
    lru = replay("LRU", corpus.events, capacity)
    assert gdsf.avoided_compute_ratio > lru.avoided_compute_ratio
    # And it is avoided *work*, not merely more hits.
    assert gdsf.avoided_recompute_ms > lru.avoided_recompute_ms


def test_sota_06_admission_prefers_value_over_hit_count() -> None:
    control = AdmissionController(create_policy("S3_FIFO", 1_000_000))
    expensive = CacheObject(
        key="sha256:" + "1" * 64,
        size_bytes=96_000,
        recompute_ms=8_000.0,
        restore_ms=4.0,
        model_tokens=15_000,
        stage_class="generation",
    )
    cheap = CacheObject(
        key="sha256:" + "2" * 64, size_bytes=900_000, recompute_ms=2.0, restore_ms=1.0, stage_class="manifest"
    )
    assert control.admit(expensive).admitted is True
    assert control.admit(cheap).admitted is False


# ==========================================================================
# SOTA-07 DAG known future
# ==========================================================================
def test_sota_07_objects_needed_soon_are_protected_and_prefetched() -> None:
    from elmos_build_cache.dag import ConversionDag, DagNode, EdgeKind, Granularity

    dag = ConversionDag()
    for index in range(8):
        dag.add_node(
            DagNode(
                f"n{index}",
                "target-code-generation",
                Granularity.GENERATED_FILE,
                logical_outputs=(f"art{index}",),
                estimated_cost_ms=1000,
            )
        )
    for index in range(7):
        dag.add_edge(f"n{index}", f"n{index + 1}", EdgeKind.PUBLIC_INTERFACE)
    artifacts = {
        f"art{index}": Artifact(f"art{index}", 2_000_000, restore_ms=40.0, recompute_ms=2_000.0)
        for index in range(8)
    }
    index_ = FutureUseIndex.from_dag(dag, artifacts)

    # Protection: what a consumer needs soon cannot be evicted.
    policy = create_policy("SIEVE", 4_000_000)
    for key in index_.protected_keys(0, horizon=2):
        policy.protect(key)
    for key in sorted(artifacts):
        policy.access(CacheObject(key=key, size_bytes=2_000_000, recompute_ms=2_000.0, restore_ms=40.0))
    for key in index_.protected_keys(0, horizon=2):
        assert policy.contains(key), f"{key} was needed within the horizon and was evicted"

    # Prefetch: precision and critical-path savings are reported, not assumed.
    planner = PrefetchPlanner(index_, PrefetchBudget(horizon=3, max_in_flight=3))
    issued = planner.plan(0)
    assert issued
    for decision in issued:
        planner.observe_consumption(decision.key, arrived_in_time=True)
    metrics = planner.metrics.to_dict(opportunities=len(artifacts))
    assert metrics["precision"] == 1.0
    assert metrics["coverage"] > 0
    assert metrics["critical_path_saved_ms"] > 0


# ==========================================================================
# SOTA-08 restore slower than recompute
# ==========================================================================
def test_sota_08_a_slow_restore_is_bypassed_and_the_run_is_faster_for_it() -> None:
    slow = Artifact("build-output", 600_000_000, restore_ms=100.0, recompute_ms=5_000.0)
    decision, explanation = restore_or_recompute(slow, PrefetchBudget(bandwidth_bytes_per_ms=20_000.0))
    assert decision == "RECOMPUTE"
    saved = explanation["transfer_ms"] - explanation["recompute_ms"]
    assert saved > 0, "bypassing has to be the faster path or it is not a bypass"

    fast = dataclasses.replace(slow, size_bytes=4_000_000)
    assert restore_or_recompute(fast, PrefetchBudget(bandwidth_bytes_per_ms=20_000.0))[0] == "RESTORE"


# ==========================================================================
# SOTA-09 workload regime shift
# ==========================================================================
def test_sota_09_a_regime_shift_does_not_cause_oscillation() -> None:
    """Hysteresis is the difference between adapting and thrashing."""
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=5_000)
    phases = ["monorepo-scan", "identical-rerun", "large-binaries", "monorepo-scan"]
    switches = 0
    for name in phases:
        events = GENERATORS[name]().events
        orchestrator.observe(events)
        before = orchestrator.current_epoch.policy_epoch
        orchestrator.evaluate(events)
        if orchestrator.current_epoch.policy_epoch != before:
            switches += 1
    assert switches <= 2, "the selector oscillated with every phase"
    assert orchestrator.current_epoch.policy in {item.value for item in PolicyName}


# ==========================================================================
# SOTA-10 out of distribution and drift
# ==========================================================================
def test_sota_10_drift_disables_learning_and_selects_the_fixed_fallback() -> None:
    drift = detect_drift(
        GENERATORS["identical-rerun"]().events, GENERATORS["monorepo-scan"]().events
    )
    assert drift["drifted"] is True

    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=0)
    events = GENERATORS["monorepo-scan"]().events
    orchestrator.observe(events)
    epoch, selection = orchestrator.evaluate(events, drifted=drift["drifted"])
    assert epoch.policy == PINNED_FALLBACK.value
    assert SelectionReason.DRIFT_DETECTED.value in selection.reason_codes


def test_sota_10_out_of_distribution_features_disable_the_model() -> None:
    import random

    rnd = random.Random(5)
    rows = [
        {"one_hit_ratio": rnd.random() * 0.4, "reuse_ratio": rnd.random(), "size_cv": rnd.random()}
        for _ in range(20)
    ]
    model = LearnedModel.train(
        rows,
        {"small_ratio": [0.1] * 20, "ghost_ratio": [1.0] * 20},
        feature_names=("one_hit_ratio", "reuse_ratio", "size_cv"),
    )
    names = ("one_hit_ratio", "reuse_ratio", "size_cv")
    registry = ModelRegistry(Ed25519ProvenanceSigner.generate("k"))
    registry.register(model, OutOfDistributionDetector(rows, names), activate=True)
    control = LearningAugmentedController(registry, shadow_only=False, canary_fraction=1.0)

    proposal = control.propose({"one_hit_ratio": 0.99, "reuse_ratio": 0.5, "size_cv": 0.5})
    assert ControlReason.OUT_OF_DISTRIBUTION.value in proposal.reasons
    assert proposal.parameters == S3FIFO_FALLBACK


# ==========================================================================
# SOTA-11 model unavailable
# ==========================================================================
def test_sota_11_a_missing_model_does_not_take_the_cache_down() -> None:
    """The data plane never waits for inference, so it cannot fail with it."""
    registry = ModelRegistry(Ed25519ProvenanceSigner.generate("k"))  # nothing registered
    control = LearningAugmentedController(registry, shadow_only=False)
    proposal = control.propose({"one_hit_ratio": 0.5, "reuse_ratio": 0.5, "size_cv": 1.0})
    assert ControlReason.NO_MODEL.value in proposal.reasons

    policy = create_policy(proposal.parameters and "S3_FIFO", 1_000_000, **proposal.parameters)
    for index in range(200):
        decision = policy.access(CacheObject(key=f"k{index % 20}", size_bytes=10_000))
        assert decision.hit or decision.admitted or decision.bypass_reason
    assert policy.counters.hits > 0


# ==========================================================================
# SOTA-12 multi-tenant pressure
# ==========================================================================
def test_sota_12_a_tenant_burst_cannot_take_the_whole_cache() -> None:
    policy = create_policy("S3_FIFO", 3_000_000)
    control = AdmissionController(
        policy,
        quotas=[
            TenantQuota("sha256:" + "a" * 64, maximum_bytes=1_000_000),
            TenantQuota("sha256:" + "b" * 64, maximum_bytes=1_000_000),
        ],
    )
    policy.protect("active-run-root")
    control.admit(
        CacheObject(key="active-run-root", size_bytes=500_000, tenant_hash="sha256:" + "a" * 64)
    )
    for index in range(40):
        control.admit(
            CacheObject(
                key=f"loud-{index}",
                size_bytes=200_000,
                recompute_ms=500.0,
                tenant_hash="sha256:" + "a" * 64,
            )
        )
    quiet = control.admit(
        CacheObject(
            key="quiet", size_bytes=200_000, recompute_ms=500.0, tenant_hash="sha256:" + "b" * 64
        )
    )
    assert quiet.admitted is True, "the quiet tenant was starved"
    assert control.rejected_by_quota > 0
    assert policy.contains("active-run-root"), "an active run root was evicted under pressure"


def test_sota_12_fairness_is_reported_per_tenant() -> None:
    corpus = GENERATORS["multi-tenant-burst"]()
    result = replay("S3_FIFO", corpus.events, recommended_capacity(corpus.events))
    assert 0.0 <= result.tenant_fairness <= 1.0
    assert len([row for row in result.cohorts() if row["cohort"] == "tenant"]) >= 4


# ==========================================================================
# SOTA-13 cache restart
# ==========================================================================
@pytest.mark.parametrize("policy_name", [item.value for item in PolicyName])
def test_sota_13_policy_state_survives_a_restart_or_is_explicitly_reset(policy_name: str) -> None:
    policy = create_policy(policy_name, 4_000_000)
    for index in range(200):
        policy.access(CacheObject(key=f"k{index % 25}", size_bytes=100_000))
    policy.protect("k1")

    snapshot = policy.snapshot()
    restored = restore_policy(snapshot)
    assert restored.state_digest() == policy.state_digest()
    assert restored.protected() == policy.protected()

    # A reset is a decision somebody can see, not a silent difference.
    fresh = create_policy(policy_name, 4_000_000)
    assert fresh.state_digest() != policy.state_digest()
    assert fresh.keys() == ()


def test_sota_13_a_corrupted_snapshot_is_refused() -> None:
    from elmos_build_cache.errors import ContractViolation

    snapshot = create_policy("SIEVE", 1_000).snapshot()
    snapshot["schema_version"] = "0.0.1"
    with pytest.raises(ContractViolation):
        create_policy("SIEVE", 1_000).restore(snapshot)


# ==========================================================================
# SOTA-14 trace privacy
# ==========================================================================
def test_sota_14_no_generated_corpus_contains_anything_reversible() -> None:
    for name, generator in GENERATORS.items():
        corpus = generator()
        assert_privacy(corpus.events)  # raises on any violation
        for event in corpus.events[:50]:
            payload = " ".join(str(value) for value in event.to_dict().values())
            assert "/" not in payload.replace("sha256:", ""), name
            assert "tenant-" not in payload, name


# ==========================================================================
# SOTA-15 equal-capacity certification
# ==========================================================================
def test_sota_15_a_policy_is_certified_only_on_an_untouched_window() -> None:
    corpus = generate_monorepo_scan(files=6000)
    capacity = recommended_capacity(corpus.events, 0.05)
    signer = Ed25519ProvenanceSigner.generate("cert-key")
    context = CertificationContext(
        elmos_commit="commit-under-test",
        policy_digest="sha256:" + "1" * 64,
        configuration_digest="sha256:" + "2" * 64,
        capacity_bytes=capacity,
        objective_profile="BALANCED",
        protected_root_rules="active-runs+checkpoints+published-trees+pins",
        hardware_profile="linux-x86_64",
    )
    plan = RolloutPlan()
    for phase in ("shadow", "recommendation", "canary", "progressive"):
        plan.advance({"phase": phase})

    result = certify_policy(
        corpus,
        "SIEVE",
        context,
        signer,
        rollout=plan,
        shadow_evidence={"object_hit_ratio_delta": 0.08},
        canary_evidence={"tenants": 2, "regressions": 0},
        rollback_evidence={"exercised": True, "restored_epoch": "epoch-0001"},
    )
    assert result.certified is True, result.reasons
    assert result.signed is not None

    statement = verify_certificate(result.signed, signer)
    assert statement["measurements"]["weighted_improvement"] > 0
    assert statement["trace"]["split_digests"]
    assert statement["rollout"]["phase"] == RolloutPhase.PROGRESSIVE.value


def test_sota_15_certification_is_refused_without_the_evidence() -> None:
    corpus = generate_monorepo_scan(files=6000)
    signer = Ed25519ProvenanceSigner.generate("cert-key")
    context = CertificationContext(
        "commit", "sha256:" + "1" * 64, "sha256:" + "2" * 64,
        recommended_capacity(corpus.events, 0.05), "BALANCED", "roots", "linux",
    )
    result = certify_policy(corpus, "SIEVE", context, signer)
    assert result.certified is False
    assert "NO_ROLLBACK_EXERCISE" in result.reasons
    assert "NO_SHADOW_EVIDENCE" in result.reasons
    assert result.signed is None


def test_sota_15_a_certificate_expires_when_what_it_bound_moves() -> None:
    corpus = generate_monorepo_scan(files=6000)
    capacity = recommended_capacity(corpus.events, 0.05)
    signer = Ed25519ProvenanceSigner.generate("cert-key")
    context = CertificationContext(
        "commit", "sha256:" + "1" * 64, "sha256:" + "2" * 64, capacity, "BALANCED", "roots", "linux"
    )
    result = certify_policy(
        corpus, "SIEVE", context, signer,
        shadow_evidence={"x": 1}, rollback_evidence={"y": 1},
    )
    assert result.certified is True

    moved = dataclasses.replace(context, capacity_bytes=capacity * 4, model_digest="sha256:" + "9" * 64)
    reasons = expired_reasons(result.statement, moved)
    assert any("capacity_bytes" in reason for reason in reasons)
    assert any("model_digest" in reason for reason in reasons)

    drifted = expired_reasons(
        result.statement, context, drift={"drifted": True, "drifted_features": ["one_hit_ratio"]}
    )
    assert any("workload_regime" in reason for reason in drifted)


def test_sota_15_no_single_policy_wins_the_whole_matrix() -> None:
    """The claim the package makes, checked against this repository's own numbers."""
    matrix = benchmark_matrix(
        workloads={
            "monorepo-scan": GENERATORS["monorepo-scan"](),
            "identical-rerun": GENERATORS["identical-rerun"](),
            "multi-tenant-burst": GENERATORS["multi-tenant-burst"](),
        },
        capacity_fractions=(0.05, 0.2),
    )
    assert matrix["no_single_winner"] is True, matrix["wins"]
    assert len(matrix["cells"]) == 6


# ==========================================================================
# SOTA-16 cache correctness is not a policy decision
# ==========================================================================
def test_sota_16_a_policy_cannot_make_an_invalid_entry_reusable(tmp_path: Path, clock) -> None:
    """The correctness plane runs before any policy is consulted."""
    from elmos_build_cache.cas import ContentAddressableStore
    from elmos_build_cache.db import SqliteMetadataStore

    cas = ContentAddressableStore(tmp_path / "cas")
    store = SqliteMetadataStore.open(tmp_path / "index.sqlite", clock)
    cache = ActionCache(store, cas, clock=clock)
    with store.transaction():
        store.ensure_project("tenant-a", "project")

    # Nothing was ever committed, so no policy state can produce a hit.
    with store.transaction():
        result = cache.lookup(
            LookupRequest(
                tenant_id="tenant-a",
                action_key="sha256:" + "7" * 64,
                trust_namespace=TrustNamespace.BRANCH,
                minimum_validation=ValidationLevel.TEST_VERIFIED,
                mode=CacheMode.READ_ONLY,
            )
        )
    assert result.hit is False
    assert result.reasons

    # ``projects.project_id`` is a globally unique primary key, so a second
    # tenant cannot claim an identifier another tenant already owns. The store
    # fails closed on the attempt rather than quietly aliasing the two scopes.
    from elmos_build_cache.errors import ConflictError

    with pytest.raises(ConflictError), store.transaction():
        store.ensure_project("tenant-b", "project")
    owner = store.query_one(
        "SELECT tenant_id FROM projects WHERE project_id=?", ("project",)
    )
    assert owner is not None and str(owner[0]) == "tenant-a"

    # And a cross-tenant lookup of the same key, from tenant-b's own project,
    # is equally a miss.
    with store.transaction():
        store.ensure_project("tenant-b", "project-b")
        other = cache.lookup(
            LookupRequest(
                tenant_id="tenant-b",
                action_key="sha256:" + "7" * 64,
                trust_namespace=TrustNamespace.BRANCH,
                minimum_validation=ValidationLevel.TEST_VERIFIED,
                mode=CacheMode.READ_ONLY,
            )
        )
    assert other.hit is False
    store.close()


def test_sota_16_an_immutable_key_that_changes_size_is_a_failure_not_a_hit() -> None:
    result = replay(
        "LRU",
        [
            *GENERATORS["identical-rerun"]().events[:5],
        ],
        1_000_000,
    )
    assert result.correctness_failures == 0

    from elmos_build_cache.cache_trace import CacheTraceEvent, Tier, key_hash

    def event(size: int) -> CacheTraceEvent:
        return CacheTraceEvent(
            event_id=f"evt-{size}",
            timestamp_bucket=0,
            tier=Tier.L1_LOCAL_CAS.value,
            key_hash=key_hash("same-key"),
            namespace_hash=key_hash("tenant"),
            size_bytes=size,
            access="GET",
            stage_class="ir",
            recompute_ms=10.0,
            restore_ms=1.0,
        )

    tampered = replay("LRU", [event(1000), event(2000)], 1_000_000)
    assert tampered.correctness_failures == 1


# ==========================================================================
# SOTA-17 staging survives a crash
# ==========================================================================
def test_sota_17_a_crash_during_promotion_leaves_no_half_published_tree(
    workspace, store, coordinator, run: str
) -> None:
    """Adding a policy layer changes nothing about staged-file recovery."""
    from conftest import claim_node
    from elmos_build_cache.enums import FileClass, StagedFileStatus

    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        record = workspace.reserve(
            "gen", 1, "src/App.cs", lease.epoch, file_class=FileClass.PUBLISH_CANDIDATE
        )
        record = workspace.write_and_seal(record, b"public class App {}", lease.epoch)

    # Crash here: sealed, never promoted, nothing published.
    with store.transaction():
        recovery = workspace.recover()
    assert recovery["failed"] == []

    staged = [item for item in store.list_staged_files(run) if item.logical_path == "src/App.cs"]
    assert len(staged) == 1, "recovery duplicated a logical file"
    assert staged[0].status in (
        StagedFileStatus.SEALED,
        StagedFileStatus.CAS_PROMOTED,
        StagedFileStatus.ABORTED,
    )
    assert not list((workspace.publish_root).glob("current/**/*.cs")), "a partial tree was published"


# ==========================================================================
# SOTA-18 rollback
# ==========================================================================
def test_sota_18_an_induced_regression_rolls_back_to_the_certified_policy() -> None:
    orchestrator = PolicyOrchestrator(
        "L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=0, initial_policy="GDSF"
    )
    assert orchestrator.policy.name.value == "GDSF"
    epoch = orchestrator.fallback("HIT_RATE_REGRESSION")
    assert epoch.policy == PINNED_FALLBACK.value
    assert "HIT_RATE_REGRESSION" in epoch.reason_codes
    assert orchestrator.history()[-1]["policy"] == PINNED_FALLBACK.value

    plan = RolloutPlan()
    plan.advance({"phase": "shadow"})
    plan.advance({"phase": "recommendation"})
    plan.rollback("LATENCY_REGRESSION")
    assert plan.phase == RolloutPhase.SIMULATOR
    assert plan.rolled_back is True
    assert plan.history[-1]["reason"] == "LATENCY_REGRESSION"


def test_sota_18_the_gate_thresholds_are_part_of_the_certificate() -> None:
    gates = CertificationGates(minimum_weighted_improvement=0.05)
    assert gates.benchmark_gates().minimum_weighted_improvement == 0.05
    assert gates.to_dict()["require_rollback_exercise"] is True
    assert BenchmarkGates().require_zero_correctness_failures is True
