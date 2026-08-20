"""Admission by value, and the guard rails around it.

The tests that matter here are the ones where hit count and value disagree: a
big cheap object that a hit-rate cache would love, an expensive small one it
would throw away, and a tenant whose burst would take the whole cache if
nothing stopped it.
"""

from __future__ import annotations

from elmos_build_cache.cache_admission import (
    VALIDATION_VALUE,
    AdmissionController,
    AdmissionReason,
    CostModel,
    CostSource,
    ReuseEstimator,
    TenantQuota,
)
from elmos_build_cache.cache_policy import CacheObject, create_policy

TENANT = "sha256:" + "e" * 64
OTHER = "sha256:" + "f" * 64


def controller(capacity: int = 4_000_000, **kwargs: object) -> AdmissionController:
    return AdmissionController(create_policy("S3_FIFO", capacity), **kwargs)  # type: ignore[arg-type]


def obj(key: str, **kwargs: object) -> CacheObject:
    base: dict[str, object] = {
        "key": key,
        "size_bytes": 100_000,
        "recompute_ms": 100.0,
        "restore_ms": 5.0,
        "tenant_hash": TENANT,
    }
    base.update(kwargs)
    return CacheObject(**base)  # type: ignore[arg-type]


# ==========================================================================
# the objective
# ==========================================================================
def test_an_expensive_small_object_beats_a_cheap_large_one() -> None:
    """The comparison a hit-count cache gets backwards."""
    control = controller()
    expensive = obj(
        "generation",
        size_bytes=96_000,
        recompute_ms=8_000.0,
        model_tokens=15_000,
        critical_path_weight=1.0,
        stage_class="generation",
        validation_level="TEST_VERIFIED",
    )
    cheap = obj("manifest", size_bytes=2_000_000, recompute_ms=3.0, restore_ms=1.0, stage_class="manifest")

    assert control.evaluate(expensive).value > control.evaluate(cheap).value
    assert control.admit(expensive).admitted is True
    assert control.admit(cheap).admitted is False


def test_every_term_of_the_objective_is_reported() -> None:
    breakdown = controller().evaluate(obj("k", model_tokens=1_000, critical_path_weight=0.5))
    payload = breakdown.to_dict()
    for term in (
        "reuse_probability",
        "avoided_work_ms",
        "critical_path_ms",
        "validation_value",
        "storage_cost_ms",
        "restore_cost_ms",
        "pollution_cost_ms",
        "trust_risk_ms",
        "value",
    ):
        assert term in payload


def test_validation_level_raises_retention_value_but_not_authority() -> None:
    """A certified artifact is worth keeping; it is not thereby more reusable."""
    control = controller()
    unverified = control.evaluate(obj("a", validation_level="UNVERIFIED")).value
    certified = control.evaluate(obj("a", validation_level="PRODUCTION_CERTIFIED")).value
    assert certified > unverified
    assert VALIDATION_VALUE["QUARANTINED"] == 0.0


def test_a_quarantined_object_carries_a_trust_penalty() -> None:
    control = controller(cost_model=CostModel(trust_risk_ms=10_000.0))
    breakdown = control.evaluate(obj("q", validation_level="QUARANTINED"))
    assert breakdown.trust_risk_ms == 10_000.0
    assert breakdown.value < 0


def test_cost_sources_are_never_confused_with_each_other() -> None:
    """A number nobody measured is never presented as a measurement."""
    estimator = ReuseEstimator()
    control = controller(estimator=estimator)
    assert control.evaluate(obj("fresh")).reuse_source == CostSource.FALLBACK.value

    for _ in range(10):
        estimator.observe("seen", "ir", reused=True)
    assert control.evaluate(obj("seen")).reuse_source == CostSource.OBSERVED.value

    for index in range(10):
        estimator.observe(f"other-{index}", "compile", reused=True)
    assert control.evaluate(obj("unseen", stage_class="compile")).reuse_source == CostSource.PREDICTED.value


def test_a_planned_next_use_is_knowledge_not_a_guess() -> None:
    breakdown = controller().evaluate(obj("planned", next_use_distance=3))
    assert breakdown.reuse_probability == 1.0
    assert breakdown.reuse_source == CostSource.OBSERVED.value


# ==========================================================================
# bypass
# ==========================================================================
def test_an_object_slower_to_restore_than_to_rebuild_is_bypassed() -> None:
    decision = controller().admit(obj("slow", recompute_ms=100.0, restore_ms=99.0))
    assert decision.admitted is False
    assert AdmissionReason.BYPASS_RESTORE_SLOWER_THAN_RECOMPUTE.value in decision.reasons


def test_a_planned_consumer_changes_which_rule_refuses_a_bad_object() -> None:
    """Knowing it will be needed does not make a pointless cache entry worth it.

    With a restore that costs almost as much as the rebuild, the object is
    refused either way -- but the *reason* differs, and the reason is what an
    operator acts on: the bypass rule is about the ratio, the value rule is
    about the whole objective.
    """
    unplanned = controller().admit(obj("slow", recompute_ms=100.0, restore_ms=99.0))
    planned = controller().admit(obj("slow", recompute_ms=100.0, restore_ms=99.0, next_use_distance=1))
    assert unplanned.admitted is False and planned.admitted is False
    assert AdmissionReason.BYPASS_RESTORE_SLOWER_THAN_RECOMPUTE.value in unplanned.reasons
    assert AdmissionReason.REJECTED_NEGATIVE_VALUE.value in planned.reasons


def test_a_planned_consumer_makes_reuse_certain() -> None:
    decision = controller().admit(obj("planned", recompute_ms=900.0, restore_ms=5.0, next_use_distance=2))
    assert decision.admitted is True
    assert decision.breakdown.reuse_probability == 1.0


# ==========================================================================
# tenants
# ==========================================================================
def test_a_tenant_cannot_exceed_its_ceiling() -> None:
    control = controller(quotas=[TenantQuota(TENANT, maximum_bytes=250_000, burst_bytes=0)])
    assert control.admit(obj("a")).admitted is True
    assert control.admit(obj("b")).admitted is True
    third = control.admit(obj("c"))
    assert third.admitted is False
    assert AdmissionReason.REJECTED_TENANT_QUOTA.value in third.reasons
    assert control.rejected_by_quota == 1


def test_a_burst_allowance_is_separate_from_the_steady_ceiling() -> None:
    """The burst is extra headroom, and it too runs out."""
    steady = controller(quotas=[TenantQuota(TENANT, maximum_bytes=100_000, burst_bytes=0)])
    assert steady.admit(obj("a")).admitted is True
    assert steady.admit(obj("b")).admitted is False

    bursting = controller(quotas=[TenantQuota(TENANT, maximum_bytes=100_000, burst_bytes=200_000)])
    assert [bursting.admit(obj(name)).admitted for name in ("a", "b", "c", "d")] == [
        True,
        True,
        True,
        False,
    ]


def test_a_reservation_admits_an_object_the_value_function_would_reject() -> None:
    """A tenant's protected floor is not subject to the global objective."""
    control = controller(quotas=[TenantQuota(TENANT, maximum_bytes=1_000_000, reserved_bytes=500_000)])
    worthless = obj("cheap", size_bytes=200_000, recompute_ms=1.0, restore_ms=0.5)
    decision = control.admit(worthless)
    assert decision.admitted is True
    assert AdmissionReason.ADMITTED_WITHIN_RESERVATION.value in decision.reasons


def test_one_tenant_cannot_starve_another() -> None:
    control = controller(
        quotas=[
            TenantQuota(TENANT, maximum_bytes=300_000),
            TenantQuota(OTHER, maximum_bytes=300_000),
        ]
    )
    for index in range(10):
        control.admit(obj(f"loud-{index}"))
    quiet = control.admit(obj("quiet", tenant_hash=OTHER))
    assert quiet.admitted is True


# ==========================================================================
# protection and explanation
# ==========================================================================
def test_a_protected_object_is_admitted_whatever_its_value() -> None:
    control = controller()
    control.policy.protect("checkpoint")
    decision = control.admit(obj("checkpoint", recompute_ms=0.1, restore_ms=0.0, size_bytes=2_000_000))
    assert decision.admitted is True
    assert AdmissionReason.ADMITTED_PROTECTED.value in decision.reasons


def test_explain_is_a_dry_run_that_changes_nothing() -> None:
    control = controller(quotas=[TenantQuota(TENANT, maximum_bytes=1_000_000)])
    before = control.stats()
    explanation = control.explain(obj("k"))
    assert explanation["would_admit"] is True
    assert explanation["quota"]["maximum_bytes"] == 1_000_000
    assert explanation["value"]["value"] > 0
    assert control.stats() == before


def test_decisions_are_deterministic_for_the_same_state_and_input() -> None:
    def run() -> list[tuple[bool, tuple[str, ...]]]:
        control = controller()
        return [
            (control.admit(obj(f"k{index}", recompute_ms=10.0 * (index % 5))).admitted,
             control.decisions[-1].reasons)
            for index in range(25)
        ]

    assert run() == run()
