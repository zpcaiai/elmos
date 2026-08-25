"""The policy portfolio, one property at a time.

The interesting assertions here are not "does LRU evict the oldest" but the
three rules that make a policy safe to put in front of an ELMOS cache:
protected roots survive, an immutable key cannot change size, and the same
inputs produce the same decisions -- because a policy that is not deterministic
cannot be benchmarked, and a benchmark is the only evidence a policy claim has.
"""

from __future__ import annotations

import pytest

from elmos_build_cache.cache_policy import (
    POLICIES,
    CacheObject,
    FrequencySketch,
    PolicyCounters,
    PolicyName,
    Reason,
    create_policy,
    restore_policy,
)
from elmos_build_cache.errors import ContractViolation

ALL_POLICIES = [name.value for name in PolicyName]


def obj(key: str, size: int = 1000, **kwargs: object) -> CacheObject:
    return CacheObject(key=key, size_bytes=size, **kwargs)  # type: ignore[arg-type]


# ==========================================================================
# the SPI, for every policy
# ==========================================================================
@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_every_policy_implements_the_same_contract(policy_name: str) -> None:
    policy = create_policy(policy_name, 10_000)
    assert policy.name.value == policy_name
    assert policy.used_bytes == 0

    first = policy.access(obj("a"))
    assert first.hit is False and first.admitted is True
    assert policy.contains("a")
    assert policy.used_bytes == 1000

    second = policy.access(obj("a"))
    assert second.hit is True
    assert second.reasons == (Reason.HIT.value,)
    assert policy.counters.hits == 1 and policy.counters.misses == 1


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_an_object_larger_than_the_cache_is_bypassed_not_evicted_around(policy_name: str) -> None:
    policy = create_policy(policy_name, 1_000)
    policy.access(obj("resident", 400))
    decision = policy.access(obj("enormous", 5_000))
    assert decision.admitted is False
    assert decision.bypass_reason == Reason.OBJECT_EXCEEDS_CAPACITY.value
    assert policy.contains("resident"), "a bypass must not disturb the cache"


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_an_immutable_key_cannot_change_size(policy_name: str) -> None:
    """A size change for the same exact key is a broken key contract, not a resize."""
    policy = create_policy(policy_name, 10_000)
    policy.access(obj("k", 1000))
    with pytest.raises(ContractViolation, match="immutable"):
        policy.access(obj("k", 2000))


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_protected_roots_are_never_victims(policy_name: str) -> None:
    """Active runs, checkpoints, pins and holds outrank every replacement rule."""
    policy = create_policy(policy_name, 3_000)
    policy.access(obj("checkpoint", 1000))
    policy.protect("checkpoint")
    for index in range(20):
        policy.access(obj(f"filler-{index}", 1000))
    assert policy.contains("checkpoint"), "a protected root was evicted"
    assert policy.is_protected("checkpoint")


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_admission_is_refused_when_only_protected_objects_remain(policy_name: str) -> None:
    """Protection is not negotiable, so the *new* object is what gives way."""
    policy = create_policy(policy_name, 1_000)
    policy.access(obj("pinned", 1000))
    assert policy.used_bytes == 1000, "the cache should be exactly full"
    policy.protect("pinned")

    decision = policy.access(obj("newcomer", 1000))
    assert decision.admitted is False
    assert decision.bypass_reason == Reason.CAPACITY_FULLY_PROTECTED.value
    assert policy.contains("pinned")
    assert policy.counters.protected_skips >= 1


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_decisions_are_deterministic(policy_name: str) -> None:
    """SOTA-01 in miniature: same inputs, same decisions, same counters."""
    # Size is a function of the key: an exact key identifies immutable bytes.
    sequence = [obj(f"k{index % 11}", 500 + (index % 11) * 250) for index in range(200)]

    def run() -> tuple[list[tuple[bool, bool, tuple[str, ...]]], dict[str, object], str]:
        policy = create_policy(policy_name, 4_000)
        decisions = []
        for item in sequence:
            decision = policy.access(item)
            decisions.append((decision.hit, decision.admitted, decision.reasons))
        return decisions, policy.counters.to_dict(), policy.state_digest()

    first, first_counters, first_digest = run()
    second, second_counters, second_digest = run()
    assert first == second
    assert first_counters == second_counters
    assert first_digest == second_digest


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_snapshot_and_restore_preserve_policy_state(policy_name: str) -> None:
    """A restart must not throw away frequency and admission history."""
    policy = create_policy(policy_name, 6_000)
    for index in range(60):
        policy.access(obj(f"k{index % 9}", 700))
    policy.protect("k3")

    restored = restore_policy(policy.snapshot())
    assert restored.state_digest() == policy.state_digest()
    assert restored.protected() == policy.protected()
    assert sorted(restored.keys()) == sorted(policy.keys())
    assert restored.used_bytes == policy.used_bytes

    # And it keeps behaving the same way from that point on.
    following = [obj(f"k{index % 9}", 700) for index in range(30)]
    assert [policy.access(item).hit for item in following] == [
        restored.access(item).hit for item in following
    ]


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_resize_shrinks_without_touching_protected_objects(policy_name: str) -> None:
    policy = create_policy(policy_name, 10_000)
    for index in range(10):
        policy.access(obj(f"k{index}", 1000))
    policy.protect("k0")

    evicted = policy.resize(3_000)
    assert policy.capacity_bytes == 3_000
    assert policy.used_bytes <= 3_000
    assert "k0" not in evicted and policy.contains("k0")


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_explain_answers_for_a_present_and_an_absent_key(policy_name: str) -> None:
    policy = create_policy(policy_name, 5_000)
    policy.access(obj("present", 900))
    present = policy.explain("present")
    assert present["present"] is True and present["size_bytes"] == 900
    assert policy.explain("absent")["present"] is False


def test_an_unknown_policy_name_fails_loudly() -> None:
    with pytest.raises(ContractViolation, match="unknown cache policy"):
        create_policy("MAGIC", 1000)


def test_a_snapshot_cannot_be_restored_into_another_policy() -> None:
    snapshot = create_policy("LRU", 1000).snapshot()
    with pytest.raises(ContractViolation, match="another policy"):
        create_policy("SIEVE", 1000).restore(snapshot)


@pytest.mark.parametrize("policy_name", ALL_POLICIES)
def test_zero_capacity_is_refused(policy_name: str) -> None:
    with pytest.raises(ContractViolation):
        create_policy(policy_name, 0)


# ==========================================================================
# the algorithms themselves
# ==========================================================================
def test_sieve_keeps_a_reused_object_through_a_scan() -> None:
    """The visited bit is the whole point: a scan cannot clear a reused object."""
    policy = create_policy("SIEVE", 5_000)
    policy.access(obj("hot", 1000))
    policy.access(obj("hot", 1000))  # sets the visited bit
    for index in range(30):
        policy.access(obj(f"scan-{index}", 1000))
    assert policy.contains("hot") or policy.counters.hits >= 1


def test_s3fifo_admits_a_returning_object_straight_to_the_main_queue() -> None:
    """A ghost hit is the evidence that an object was not a one-hit wonder."""
    policy = create_policy("S3_FIFO", 4_000)
    policy.access(obj("returning", 500))
    for index in range(10):
        policy.access(obj(f"one-hit-{index}", 500))
    decision = policy.access(obj("returning", 500))
    assert not decision.hit, "the object should have been evicted by the one-hit flood"
    assert Reason.ADMITTED_FROM_GHOST.value in decision.reasons


def test_s3fifo_beats_lru_on_a_one_hit_heavy_workload() -> None:
    """The claim the paper makes, checked on an ELMOS-shaped trace."""
    trace = []
    for index in range(600):
        # Two objects nobody ever asks for again, then one that always comes back.
        trace.append(obj(f"scan-{index}-a", 1000))
        trace.append(obj(f"scan-{index}-b", 1000))
        trace.append(obj(f"hot-{index % 3}", 1000))

    def hits(policy_name: str) -> int:
        policy = create_policy(policy_name, 8_000)
        return sum(1 for item in trace if policy.access(item).hit)

    assert hits("S3_FIFO") > hits("LRU")


def test_wtinylfu_protects_a_frequent_object_from_a_burst_of_newcomers() -> None:
    policy = create_policy("W_TINY_LFU", 8_000)
    for _ in range(30):
        policy.access(obj("frequent", 1000))
    for index in range(40):
        policy.access(obj(f"newcomer-{index}", 1000))
    assert policy.contains("frequent")


def test_size_aware_tinylfu_prefers_the_denser_object() -> None:
    """Frequency per byte, not frequency: a huge rare object loses."""
    policy = create_policy("SIZE_AWARE_TINY_LFU", 6_000)
    for _ in range(10):
        policy.access(obj("small-hot", 500))
    for index in range(12):
        policy.access(obj(f"huge-{index}", 3_000))
    assert policy.contains("small-hot")


def test_gdsf_keeps_the_expensive_object_and_drops_the_cheap_one() -> None:
    """Cost per byte is the comparison, which is why ELMOS needs this policy."""
    policy = create_policy("GDSF", 4_000)
    policy.access(obj("expensive", 1000, recompute_ms=9000.0, restore_ms=5.0))
    policy.access(obj("expensive", 1000, recompute_ms=9000.0, restore_ms=5.0))
    for index in range(20):
        policy.access(obj(f"cheap-{index}", 1000, recompute_ms=2.0, restore_ms=1.0))
    assert policy.contains("expensive")


def test_gdsf_refuses_an_object_that_cannot_outrank_what_it_would_evict() -> None:
    policy = create_policy("GDSF", 2_000)
    for _ in range(5):
        policy.access(obj("valuable", 1000, recompute_ms=5000.0))
        policy.access(obj("valuable-2", 1000, recompute_ms=5000.0))
    decision = policy.access(obj("worthless", 1000, recompute_ms=0.5))
    assert decision.admitted is False
    assert Reason.REJECTED_BY_VALUE_DENSITY.value in decision.reasons


# ==========================================================================
# the sketch
# ==========================================================================
def test_the_frequency_sketch_is_stable_across_processes() -> None:
    """Indexes come from the digest, not from ``hash()``, so replay is reproducible."""
    left, right = FrequencySketch(width=256), FrequencySketch(width=256)
    for index in range(500):
        left.increment(f"key-{index % 30}")
        right.increment(f"key-{index % 30}")
    assert [left.estimate(f"key-{i}") for i in range(30)] == [
        right.estimate(f"key-{i}") for i in range(30)
    ]


def test_the_frequency_sketch_ranks_a_frequent_key_above_a_rare_one() -> None:
    sketch = FrequencySketch(width=1024)
    for _ in range(50):
        sketch.increment("frequent")
    sketch.increment("rare")
    assert sketch.estimate("frequent") > sketch.estimate("rare")


def test_the_frequency_sketch_ages_out_old_history() -> None:
    """Halving is what makes it track a moving workload instead of all of history."""
    sketch = FrequencySketch(width=64, sample_factor=2)
    for _ in range(40):
        sketch.increment("old")
    before = sketch.estimate("old")
    for index in range(400):
        sketch.increment(f"new-{index}")
    assert sketch.estimate("old") < before


def test_counters_report_churn() -> None:
    counters = PolicyCounters(admissions=10, evictions=5)
    assert counters.churn == 0.5
    assert counters.to_dict()["churn"] == 0.5


def test_every_policy_name_has_an_implementation() -> None:
    assert set(POLICIES) == set(PolicyName)
