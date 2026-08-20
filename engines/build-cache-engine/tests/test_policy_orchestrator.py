"""Choosing a policy, and refusing to choose one.

The selector is the easy half. The half that decides whether this is safe to
run is everything around it: dwell time, an improvement margin backed by shadow
evidence, and the four conditions -- small sample, out-of-distribution, drift,
degraded telemetry -- that all resolve to the same pinned fixed policy.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from elmos_build_cache.cache_policy import PolicyName
from elmos_build_cache.cache_trace import GENERATORS, workload_features
from elmos_build_cache.policy_orchestrator import (
    PINNED_FALLBACK,
    PolicyOrchestrator,
    RuleSelector,
    SelectionReason,
    configuration_digest,
)

POLICY_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "cache-policy.schema.json"


def features_of(name: str) -> dict[str, float]:
    return workload_features(GENERATORS[name]().events)


# ==========================================================================
# the rules
# ==========================================================================
def test_a_one_hit_heavy_workload_selects_the_one_hit_filter() -> None:
    selection = RuleSelector().select(features_of("monorepo-scan"))
    assert selection.policy == PolicyName.S3_FIFO.value
    assert SelectionReason.ONE_HIT_HEAVY.value in selection.reason_codes


def test_heterogeneous_size_and_cost_selects_the_cost_aware_policy() -> None:
    selection = RuleSelector().select(features_of("large-binaries"))
    assert selection.policy == PolicyName.GDSF.value
    assert SelectionReason.EXPENSIVE_SPARSE_REUSE.value in selection.reason_codes


def test_a_planned_dag_selects_a_scan_resistant_policy() -> None:
    """With the future known, protection does the work; the policy just has to not thrash."""
    selection = RuleSelector(minimum_requests=10, minimum_unique=5).select(
        features_of("dag-known-future")
    )
    assert selection.policy == PolicyName.SIEVE.value
    assert SelectionReason.KNOWN_FUTURE.value in selection.reason_codes


def test_a_tiny_sample_falls_back_rather_than_guessing() -> None:
    selection = RuleSelector().select({"request_count": 12.0, "unique_count": 3.0})
    assert selection.policy == PINNED_FALLBACK.value
    assert SelectionReason.INSUFFICIENT_SAMPLE.value in selection.reason_codes
    assert selection.confidence < 0.3


def test_no_features_at_all_falls_back() -> None:
    assert RuleSelector().select({}).policy == PINNED_FALLBACK.value


def test_features_outside_the_certified_range_fall_back() -> None:
    selector = RuleSelector(certified_ranges={"one_hit_ratio": (0.0, 0.5)})
    selection = selector.select({**features_of("monorepo-scan"), "one_hit_ratio": 0.99})
    assert selection.policy == PINNED_FALLBACK.value
    assert SelectionReason.OUT_OF_DISTRIBUTION.value in selection.reason_codes
    assert "OOD:one_hit_ratio" in selection.reason_codes


def test_every_selection_carries_a_reason() -> None:
    for name in GENERATORS:
        selection = RuleSelector(minimum_requests=10, minimum_unique=3).select(features_of(name))
        assert selection.reason_codes, name
        assert selection.policy in {item.value for item in PolicyName}


# ==========================================================================
# epochs
# ==========================================================================
def test_an_epoch_validates_against_the_packaged_schema() -> None:
    schema = json.loads(POLICY_SCHEMA.read_text(encoding="utf-8"))
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 8_000_000)
    jsonschema.validate(orchestrator.current_epoch.to_dict(), schema)


def test_the_first_epoch_records_that_an_operator_pinned_it() -> None:
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 1_000_000)
    assert orchestrator.current_epoch.reason_codes == (SelectionReason.OPERATOR_PINNED.value,)
    assert orchestrator.current_epoch.policy == PINNED_FALLBACK.value


def test_switching_opens_a_new_epoch_with_its_reasons() -> None:
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=0)
    events = GENERATORS["monorepo-scan"]().events
    orchestrator.observe(events)
    epoch, selection = orchestrator.evaluate(events)
    assert epoch.policy == selection.policy == PolicyName.S3_FIFO.value
    assert len(orchestrator.epochs) == 2
    assert epoch.configuration_digest.startswith("sha256:")
    assert epoch.selector is not None and "features" in epoch.selector


def test_the_configuration_digest_follows_the_configuration() -> None:
    first = configuration_digest("SIEVE", 1000, "BALANCED", {})
    assert first != configuration_digest("SIEVE", 2000, "BALANCED", {})
    assert first != configuration_digest("SIEVE", 1000, "DEV_SPEED", {})
    assert first != configuration_digest("SIEVE", 1000, "BALANCED", {"small_ratio": 0.2})


# ==========================================================================
# hysteresis
# ==========================================================================
def test_a_switch_is_refused_inside_the_dwell_window() -> None:
    """Oscillation costs more than the difference between two good policies."""
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=1_000_000)
    events = GENERATORS["monorepo-scan"]().events
    orchestrator.observe(events)
    epoch, selection = orchestrator.evaluate(events)
    assert epoch.policy == PINNED_FALLBACK.value
    assert SelectionReason.WITHIN_DWELL_TIME.value in selection.reason_codes
    assert len(orchestrator.epochs) == 1


def test_shadow_evidence_can_veto_a_switch_the_rules_wanted() -> None:
    orchestrator = PolicyOrchestrator(
        "L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=0, improvement_margin=0.99
    )
    events = GENERATORS["monorepo-scan"]().events
    orchestrator.add_shadow(PINNED_FALLBACK.value)
    orchestrator.add_shadow(PolicyName.S3_FIFO.value)
    orchestrator.observe(events)
    epoch, selection = orchestrator.evaluate(events)
    assert epoch.policy == PINNED_FALLBACK.value
    assert SelectionReason.IMPROVEMENT_BELOW_MARGIN.value in selection.reason_codes


def test_shadow_evidence_raises_confidence_when_it_agrees() -> None:
    orchestrator = PolicyOrchestrator(
        "L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=0, improvement_margin=-1.0
    )
    events = GENERATORS["monorepo-scan"]().events
    orchestrator.add_shadow(PINNED_FALLBACK.value)
    orchestrator.add_shadow(PolicyName.S3_FIFO.value)
    orchestrator.observe(events)
    epoch, selection = orchestrator.evaluate(events)
    assert epoch.policy == PolicyName.S3_FIFO.value
    assert SelectionReason.SHADOW_EVIDENCE.value in selection.reason_codes


def test_shadows_never_touch_the_real_cache() -> None:
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 4_000_000)
    shadow = orchestrator.add_shadow(PolicyName.GDSF.value)
    before = orchestrator.policy.state_digest()
    orchestrator.observe(GENERATORS["identical-rerun"]().events)
    assert orchestrator.policy.state_digest() == before
    assert shadow.hits + shadow.misses > 0


# ==========================================================================
# the four ways to fall back
# ==========================================================================
def test_degraded_telemetry_pins_the_fallback() -> None:
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=0)
    events = GENERATORS["monorepo-scan"]().events
    orchestrator.observe(events)
    epoch, selection = orchestrator.evaluate(events, telemetry_healthy=False)
    assert epoch.policy == PINNED_FALLBACK.value
    assert SelectionReason.TELEMETRY_DEGRADED.value in selection.reason_codes


def test_drift_pins_the_fallback() -> None:
    orchestrator = PolicyOrchestrator(
        "L1_LOCAL_CAS", 8_000_000, minimum_dwell_events=0, initial_policy=PolicyName.GDSF.value
    )
    events = GENERATORS["monorepo-scan"]().events
    orchestrator.observe(events)
    epoch, selection = orchestrator.evaluate(events, drifted=True)
    assert epoch.policy == PINNED_FALLBACK.value
    assert SelectionReason.DRIFT_DETECTED.value in selection.reason_codes


def test_an_explicit_fallback_is_immediate_and_recorded() -> None:
    orchestrator = PolicyOrchestrator(
        "L1_LOCAL_CAS", 8_000_000, initial_policy=PolicyName.GDSF.value
    )
    epoch = orchestrator.fallback("REMOTE_OUTAGE")
    assert epoch.policy == PINNED_FALLBACK.value
    assert "REMOTE_OUTAGE" in epoch.reason_codes
    assert epoch.confidence == 0.0


# ==========================================================================
# state across a switch
# ==========================================================================
def test_protected_roots_survive_a_policy_switch() -> None:
    """A switch may reset frequency history; it may never unprotect a root."""
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 4_000_000)
    orchestrator.policy.protect("checkpoint-1")
    orchestrator.switch(PolicyName.GDSF.value, reasons=("TEST",))
    assert orchestrator.policy.is_protected("checkpoint-1")


def test_state_is_either_carried_or_reset_and_the_epoch_says_which() -> None:
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 4_000_000)
    from elmos_build_cache.cache_policy import CacheObject

    for index in range(30):
        orchestrator.policy.access(CacheObject(key=f"k{index % 5}", size_bytes=1000))

    carried = orchestrator.switch(PINNED_FALLBACK.value, reasons=("TEST",), carry_state=True)
    assert carried.state_carried is True
    assert orchestrator.policy.keys(), "carrying state should keep the resident set"

    reset = orchestrator.switch(PolicyName.LRU.value, reasons=("TEST",))
    assert reset.state_carried is False
    assert orchestrator.policy.keys() == ()


def test_the_history_is_an_audit_trail() -> None:
    orchestrator = PolicyOrchestrator("L1_LOCAL_CAS", 4_000_000)
    orchestrator.switch(PolicyName.GDSF.value, reasons=("ONE",))
    orchestrator.fallback("TWO")
    history = orchestrator.history()
    assert [entry["policy"] for entry in history] == [
        PINNED_FALLBACK.value,
        PolicyName.GDSF.value,
        PINNED_FALLBACK.value,
    ]
    assert history[-1]["reason_codes"][0] == "TWO"
    assert len({entry["policy_epoch"] for entry in history}) == 3


def test_the_state_report_names_the_epoch_and_digests_the_policy() -> None:
    orchestrator = PolicyOrchestrator("L2_REMOTE_CAS", 4_000_000)
    state = orchestrator.state()
    assert state["tier"] == "L2_REMOTE_CAS"
    assert state["epoch"] == orchestrator.current_epoch.policy_epoch
    assert state["policy_state_digest"].startswith("sha256:")
