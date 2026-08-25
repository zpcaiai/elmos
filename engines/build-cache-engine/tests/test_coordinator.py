from __future__ import annotations

import multiprocessing
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from elmos_build_cache.canonical import sha256_bytes
from elmos_build_cache.coordinator import (
    AttributionLedger,
    CacheLayer,
    DagWorkUnit,
    LayerProbeResult,
    MultiLayerCacheCoordinator,
    NegativeBackoffPolicy,
    PlanRealization,
    ProbeOutcome,
    RealizedLayer,
    ReconciliationStatus,
    ReuseBudgets,
    ReuseDecision,
    ReuseIdentity,
    ReuseRequest,
    VerifiedBoundary,
    WaiterCancelled,
    WorkDependency,
    accepted_layers,
    predicted_savings,
    reconcile_plan,
)
from elmos_build_cache.enums import ValidationLevel
from elmos_build_cache.errors import ContractViolation


def identity(tenant: str = "tenant-a", work: bytes = b"work-1") -> ReuseIdentity:
    return ReuseIdentity(
        tenant_id=tenant,
        project_id="project-1",
        authorization_digest=sha256_bytes(f"auth:{tenant}".encode()),
        compatibility_digest=sha256_bytes(b"compat-v1"),
        work_digest=sha256_bytes(work),
    )


def request() -> ReuseRequest:
    return ReuseRequest("request-1", identity(), ValidationLevel.TEST_VERIFIED)


def hit(
    layer: CacheLayer,
    *,
    complete: bool = False,
    request_identity: ReuseIdentity | None = None,
    validation: ValidationLevel = ValidationLevel.TEST_VERIFIED,
    authorised: bool = True,
    compatible: bool = True,
    verified: bool = True,
    recompute_ms: float = 100.0,
    restore_ms: float = 5.0,
    lookup_ms: float = 0.0,
    remote_bytes: int = 0,
    provider_write_tokens: int = 0,
    prefetch_bytes: int = 0,
    avoided_work_ids: tuple[str, ...] | None = None,
    verified_boundaries: tuple[VerifiedBoundary, ...] = (),
) -> LayerProbeResult:
    return LayerProbeResult(
        layer=layer,
        outcome=ProbeOutcome.HIT,
        reason_code="HIT",
        identity=request_identity or identity(),
        artifact_digest=sha256_bytes(str(layer).encode()),
        validation_level=validation,
        verified=verified,
        authorised=authorised,
        compatible=compatible,
        complete_result=complete,
        lookup_ms=lookup_ms,
        restore_ms=restore_ms,
        verify_ms=1.0,
        recompute_ms=recompute_ms,
        remote_bytes=remote_bytes,
        provider_write_tokens=provider_write_tokens,
        prefetch_bytes=prefetch_bytes,
        avoided_work_ids=avoided_work_ids or (f"work:{layer}",),
        verified_boundaries=verified_boundaries,
    )


def probe(result: LayerProbeResult) -> Callable[[], LayerProbeResult]:
    return lambda: result


def test_exact_checkpoint_supersedes_every_lower_layer() -> None:
    coordinator = MultiLayerCacheCoordinator()
    plan = coordinator.plan(
        request(),
        {
            CacheLayer.PROVIDER_PREFIX: probe(hit(CacheLayer.PROVIDER_PREFIX)),
            CacheLayer.ACTION: probe(hit(CacheLayer.ACTION, complete=True)),
            CacheLayer.CHECKPOINT: probe(hit(CacheLayer.CHECKPOINT, complete=True)),
            CacheLayer.CAS: probe(hit(CacheLayer.CAS)),
        },
    )
    assert plan.complete_result_layer is CacheLayer.CHECKPOINT
    assert plan.execution_required is False
    assert [layer.layer for layer in accepted_layers(plan)] == [CacheLayer.CHECKPOINT]
    assert all(
        layer.reason_code == "SUPERSEDED_BY_EXACT_RESULT"
        for layer in plan.layers
        if layer.layer is not CacheLayer.CHECKPOINT
    )


def test_partial_layers_can_stack_but_still_require_execution() -> None:
    plan = MultiLayerCacheCoordinator().plan(
        request(),
        {
            CacheLayer.CAS: probe(hit(CacheLayer.CAS, recompute_ms=80, restore_ms=5)),
            CacheLayer.ENVIRONMENT: probe(
                hit(CacheLayer.ENVIRONMENT, recompute_ms=50, restore_ms=10)
            ),
            CacheLayer.PROVIDER_PREFIX: probe(
                hit(CacheLayer.PROVIDER_PREFIX, recompute_ms=40, restore_ms=2)
            ),
        },
    )
    assert plan.execution_required is True
    assert [layer.layer for layer in accepted_layers(plan)] == [
        CacheLayer.CAS,
        CacheLayer.ENVIRONMENT,
        CacheLayer.PROVIDER_PREFIX,
    ]


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"authorised": False}, "AUTHORIZATION_DENIED"),
        ({"compatible": False}, "COMPATIBILITY_MISMATCH"),
        ({"verified": False}, "UNVERIFIED_MATERIAL"),
        ({"validation": ValidationLevel.COMPILE_VERIFIED}, "VALIDATION_TOO_LOW"),
        ({"recompute_ms": 5.0, "restore_ms": 10.0}, "RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE"),
    ],
)
def test_unsafe_or_uneconomic_hits_fail_closed(kwargs: dict[str, object], reason: str) -> None:
    plan = MultiLayerCacheCoordinator().plan(
        request(), {CacheLayer.ACTION: probe(hit(CacheLayer.ACTION, complete=True, **kwargs))}
    )
    assert plan.execution_required
    assert plan.layers[0].accepted is False
    assert plan.layers[0].reason_code == reason


def test_cross_tenant_identity_never_coalesces_or_reuses() -> None:
    plan = MultiLayerCacheCoordinator().plan(
        request(),
        {
            CacheLayer.ACTION: probe(
                hit(CacheLayer.ACTION, complete=True, request_identity=identity("tenant-b"))
            )
        },
    )
    assert plan.execution_required
    assert plan.layers[0].reason_code == "IDENTITY_MISMATCH"
    assert identity("tenant-a").singleflight_key != identity("tenant-b").singleflight_key


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (hit(CacheLayer.ACTION, complete=True, authorised=False), "AUTHORIZATION_DENIED"),
        (
            hit(
                CacheLayer.ACTION,
                complete=True,
                request_identity=identity("tenant-b"),
            ),
            "IDENTITY_MISMATCH",
        ),
        (
            hit(
                CacheLayer.ACTION,
                complete=True,
                validation=ValidationLevel.COMPILE_VERIFIED,
            ),
            "VALIDATION_TOO_LOW",
        ),
    ],
)
def test_prevalidated_results_still_enforce_every_authority_boundary(
    candidate: LayerProbeResult,
    reason: str,
) -> None:
    plan = MultiLayerCacheCoordinator().plan_prevalidated(
        request(),
        {CacheLayer.ACTION: candidate},
    )

    assert plan.execution_required is True
    assert plan.complete_result_layer is None
    assert plan.layers[0].accepted is False
    assert plan.layers[0].reason_code == reason


def test_prevalidated_result_exceeding_total_deadline_fails_closed() -> None:
    coordinator = MultiLayerCacheCoordinator()
    plan = coordinator.plan_prevalidated(
        request(),
        {CacheLayer.ACTION: hit(CacheLayer.ACTION, complete=True)},
        decision_started_monotonic=time.monotonic() - 2.0,
    )

    assert plan.execution_required is True
    assert plan.layers[0].accepted is False
    assert plan.layers[0].reason_code == "DECISION_DEADLINE_EXCEEDED"
    assert plan.budget_usage.breaches == ("DECISION_DEADLINE_EXCEEDED",)


def test_probe_failure_is_an_explicit_lookup_error() -> None:
    def broken() -> LayerProbeResult:
        raise OSError("offline")

    plan = MultiLayerCacheCoordinator().plan(request(), {CacheLayer.CAS: broken})
    assert plan.layers[0].outcome is ProbeOutcome.ERROR
    assert plan.layers[0].reason_code == "LOOKUP_ERROR_OSError"


def test_provider_layer_can_be_disabled_without_probing_it() -> None:
    called = False

    def provider() -> LayerProbeResult:
        nonlocal called
        called = True
        return hit(CacheLayer.PROVIDER_PREFIX)

    req = ReuseRequest("request-1", identity(), ValidationLevel.TEST_VERIFIED, False)
    plan = MultiLayerCacheCoordinator().plan(req, {CacheLayer.PROVIDER_PREFIX: provider})
    assert not called
    assert plan.layers == ()


def test_singleflight_runs_identical_authorised_work_once() -> None:
    coordinator = MultiLayerCacheCoordinator()
    barrier = threading.Barrier(5)
    lock = threading.Lock()
    calls = 0
    values: list[str] = []

    def operation() -> str:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.03)
        return "result"

    def worker() -> None:
        barrier.wait()
        values.append(coordinator.execute_singleflight(identity(), operation))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls == 1
    assert values == ["result"] * 5


def test_singleflight_propagates_the_same_failure_and_then_allows_retry() -> None:
    coordinator = MultiLayerCacheCoordinator()
    attempts = 0

    def broken() -> str:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        coordinator.execute_singleflight(identity(), broken)
    with pytest.raises(RuntimeError, match="boom"):
        coordinator.execute_singleflight(identity(), broken)
    assert attempts == 2


def test_attribution_refuses_double_counting() -> None:
    ledger = AttributionLedger()
    ledger.record(CacheLayer.ACTION, "compile:one", 25.0)
    with pytest.raises(ContractViolation, match="attributed twice"):
        ledger.record(CacheLayer.PROVIDER_PREFIX, "compile:one", 10.0)
    assert ledger.to_dict()["total_saved_ms"] == 25.0


def test_plan_digest_is_independent_of_probe_mapping_order() -> None:
    coordinator = MultiLayerCacheCoordinator()
    left = coordinator.plan(
        request(),
        {
            CacheLayer.CAS: probe(hit(CacheLayer.CAS)),
            CacheLayer.ENVIRONMENT: probe(hit(CacheLayer.ENVIRONMENT)),
        },
    )
    right = coordinator.plan(
        request(),
        {
            CacheLayer.ENVIRONMENT: probe(hit(CacheLayer.ENVIRONMENT)),
            CacheLayer.CAS: probe(hit(CacheLayer.CAS)),
        },
    )
    assert left.plan_digest == right.plan_digest


def test_non_exact_layers_cannot_claim_a_complete_result() -> None:
    with pytest.raises(ContractViolation, match="only checkpoint"):
        hit(CacheLayer.PROVIDER_PREFIX, complete=True)


def test_decision_vocabulary_and_plan_paths_are_closed() -> None:
    assert set(ReuseDecision) == {
        ReuseDecision.RESUME_CHECKPOINT,
        ReuseDecision.REUSE_EXACT_RESULT,
        ReuseDecision.RESTORE_ARTIFACTS,
        ReuseDecision.WARM_ENVIRONMENT,
        ReuseDecision.USE_NATIVE_BUILD,
        ReuseDecision.USE_PROMPT_PREFIX,
        ReuseDecision.EXECUTE_REMAINDER,
        ReuseDecision.FULL_RECOMPUTE,
    }
    exact = MultiLayerCacheCoordinator().plan(
        request(),
        {CacheLayer.ACTION: probe(hit(CacheLayer.ACTION, complete=True))},
    )
    assert exact.decisions == (ReuseDecision.REUSE_EXACT_RESULT,)

    partial = MultiLayerCacheCoordinator().plan(
        request(),
        {
            CacheLayer.CAS: probe(hit(CacheLayer.CAS)),
            CacheLayer.ENVIRONMENT: probe(hit(CacheLayer.ENVIRONMENT)),
            CacheLayer.NATIVE_BUILD: probe(hit(CacheLayer.NATIVE_BUILD)),
            CacheLayer.PROVIDER_PREFIX: probe(hit(CacheLayer.PROVIDER_PREFIX)),
        },
    )
    assert partial.decisions == (
        ReuseDecision.RESTORE_ARTIFACTS,
        ReuseDecision.WARM_ENVIRONMENT,
        ReuseDecision.USE_NATIVE_BUILD,
        ReuseDecision.USE_PROMPT_PREFIX,
        ReuseDecision.EXECUTE_REMAINDER,
    )
    miss = MultiLayerCacheCoordinator().plan(request(), {})
    assert miss.decisions == (ReuseDecision.FULL_RECOMPUTE,)


@pytest.mark.parametrize(
    ("layer", "hit_kwargs", "budgets", "reason"),
    [
        (
            CacheLayer.CAS,
            {"lookup_ms": 2.0},
            ReuseBudgets(max_lookup_ms=1.0),
            "LOOKUP_BUDGET_EXCEEDED",
        ),
        (
            CacheLayer.CAS,
            {"remote_bytes": 2},
            ReuseBudgets(max_remote_bytes=1),
            "REMOTE_BYTES_BUDGET_EXCEEDED",
        ),
        (
            CacheLayer.PROVIDER_PREFIX,
            {"provider_write_tokens": 2},
            ReuseBudgets(max_provider_write_tokens=1),
            "PROVIDER_WRITE_BUDGET_EXCEEDED",
        ),
        (
            CacheLayer.CAS,
            {"prefetch_bytes": 2},
            ReuseBudgets(max_prefetch_bytes=1),
            "PREFETCH_BUDGET_EXCEEDED",
        ),
        (
            CacheLayer.CAS,
            {"restore_ms": 5.0},
            ReuseBudgets(max_restore_ms=5.0),
            "RESTORE_BUDGET_EXCEEDED",
        ),
    ],
)
def test_lookup_and_reuse_resource_budgets_fail_to_full_recompute(
    layer: CacheLayer,
    hit_kwargs: dict[str, object],
    budgets: ReuseBudgets,
    reason: str,
) -> None:
    req = ReuseRequest("request-budget", identity(), ValidationLevel.TEST_VERIFIED, budgets=budgets)
    plan = MultiLayerCacheCoordinator().plan(req, {layer: probe(hit(layer, **hit_kwargs))})
    assert plan.execution_required is True
    assert plan.decisions == (ReuseDecision.FULL_RECOMPUTE,)
    assert plan.layers[0].accepted is False
    assert plan.layers[0].reason_code == reason
    assert reason in plan.budget_usage.breaches


#: A probe slow enough that "the timeout fired" and "we waited it out" cannot be
#: confused: three orders of magnitude past the 5 ms per-probe budget below.
SLOW_PROBE_SECONDS = 5.0

#: Any constant will do; the point is that it does not move while ``plan`` runs.
FROZEN_MONOTONIC = 1_000.0


def test_probe_timeout_and_expired_decision_deadline_degrade_safely(tmp_path: Path) -> None:
    """The per-probe timeout fires *and* the planner returns without the probe.

    This used to be ``elapsed < 0.04`` against a probe that slept 0.05 -- a
    40 ms wall-clock budget that a loaded machine misses, and that did not
    actually test the intent either way: ``_poll_probe_worker`` also reports
    ``LOOKUP_TIMEOUT`` from ``envelope.completed_monotonic`` when it *did* wait
    for a late probe, so the reason code alone cannot tell "gave up at 5 ms"
    from "waited 5 s and then complained".

    Two changes make the intent testable without a wall-clock margin:

    * the probe leaves a marker only if it runs to completion, so the marker's
      absence is direct proof the planner returned while it was still sleeping
      and reclaimed the worker rather than waiting;
    * the coordinator gets a frozen ``monotonic``, which pins the *budget
      arithmetic* (the 20 ms decision deadline can no longer expire under load
      and rewrite the reason code) while the deadline the worker is actually
      held to stays real wall clock -- ``_start_probe_worker`` computes
      ``deadline_wall`` from ``time.monotonic()``, so the 5 ms per-probe
      timeout is still genuinely enforced by the code under test.
    """
    finished = tmp_path / "probe-ran-to-completion"

    def slow() -> LayerProbeResult:
        time.sleep(SLOW_PROBE_SECONDS)
        finished.write_bytes(b"the probe was waited for")
        return hit(CacheLayer.CAS)

    budgets = ReuseBudgets(decision_timeout_ms=20.0, per_probe_timeout_ms=5.0)
    req = ReuseRequest("request-timeout", identity(), ValidationLevel.TEST_VERIFIED, budgets=budgets)
    timed_out = MultiLayerCacheCoordinator(monotonic=lambda: FROZEN_MONOTONIC).plan(
        req, {CacheLayer.CAS: slow}
    )

    assert not finished.exists(), "the planner waited for the slow probe instead of timing it out"
    assert timed_out.layers[0].outcome is ProbeOutcome.ERROR
    assert timed_out.layers[0].reason_code == "LOOKUP_TIMEOUT"
    assert timed_out.layers[0].accepted is False
    assert timed_out.decisions == (ReuseDecision.FULL_RECOMPUTE,)

    # An already-expired decision deadline is refused before any probe starts:
    # frozen clock, deadline in its past, so this is exact rather than raced.
    already_expired = ReuseRequest(
        "request-deadline",
        identity(),
        ValidationLevel.TEST_VERIFIED,
        budgets=budgets,
        decision_deadline_monotonic=FROZEN_MONOTONIC - 0.001,
    )
    expired = MultiLayerCacheCoordinator(monotonic=lambda: FROZEN_MONOTONIC).plan(
        already_expired,
        {CacheLayer.CAS: slow},
    )
    assert expired.layers[0].reason_code == "DECISION_DEADLINE_EXCEEDED"
    assert "DECISION_DEADLINE_EXCEEDED" in expired.budget_usage.breaches
    assert not finished.exists(), "an expired decision deadline must not start a probe at all"


def test_never_returning_probe_is_hard_reclaimed_without_worker_or_thread_leak() -> None:
    def never_returns() -> LayerProbeResult:
        while True:
            time.sleep(60)

    child_pids_before = {
        process.pid for process in multiprocessing.active_children() if process.pid is not None
    }
    non_daemon_threads_before = {
        thread.ident for thread in threading.enumerate() if not thread.daemon
    }
    req = ReuseRequest(
        "request-never-return",
        identity(),
        ValidationLevel.TEST_VERIFIED,
        budgets=ReuseBudgets(decision_timeout_ms=100.0, per_probe_timeout_ms=20.0),
    )

    started = time.monotonic()
    plan = MultiLayerCacheCoordinator().plan(req, {CacheLayer.CAS: never_returns})

    assert time.monotonic() - started < 0.2
    assert plan.layers[0].outcome is ProbeOutcome.ERROR
    assert plan.layers[0].reason_code == "LOOKUP_TIMEOUT"
    assert {
        process.pid for process in multiprocessing.active_children() if process.pid is not None
    } <= child_pids_before
    assert {
        thread.ident for thread in threading.enumerate() if not thread.daemon
    } <= non_daemon_threads_before


@pytest.mark.parametrize("start_methods", [[], ["spawn"]])
def test_probe_fails_closed_without_reclaimable_or_transportable_process(
    monkeypatch: pytest.MonkeyPatch,
    start_methods: list[str],
) -> None:
    monkeypatch.setattr(multiprocessing, "get_all_start_methods", lambda: start_methods)

    plan = MultiLayerCacheCoordinator().plan(
        request(),
        {CacheLayer.CAS: probe(hit(CacheLayer.CAS))},
    )

    assert plan.layers[0].outcome is ProbeOutcome.ERROR
    assert plan.layers[0].reason_code == "PROBE_ISOLATION_UNAVAILABLE"
    assert plan.decisions == (ReuseDecision.FULL_RECOMPUTE,)


def _typed_graph() -> tuple[DagWorkUnit, ...]:
    parse = DagWorkUnit("parse", sha256_bytes(b"parse"), minimum_validation=ValidationLevel.TEST_VERIFIED)
    ir = DagWorkUnit(
        "ir",
        sha256_bytes(b"ir"),
        (WorkDependency("parse", parse.work_digest),),
        ValidationLevel.TEST_VERIFIED,
    )
    generate = DagWorkUnit(
        "generate",
        sha256_bytes(b"generate"),
        (WorkDependency("ir", ir.work_digest),),
        ValidationLevel.TEST_VERIFIED,
    )
    test = DagWorkUnit(
        "test",
        sha256_bytes(b"test"),
        (WorkDependency("generate", generate.work_digest),),
        ValidationLevel.TEST_VERIFIED,
    )
    return (parse, ir, generate, test)


def test_partial_dag_remainder_stops_only_at_exact_verified_boundaries() -> None:
    graph = _typed_graph()
    generate = next(unit for unit in graph if unit.work_id == "generate")
    boundary = VerifiedBoundary(
        "generate",
        generate.work_digest,
        generate.dependencies,
        ValidationLevel.TEST_VERIFIED,
        sha256_bytes(b"generate-evidence"),
    )
    req = ReuseRequest(
        "request-dag",
        identity(),
        ValidationLevel.TEST_VERIFIED,
        work_graph=graph,
        requested_work_ids=("test",),
    )
    plan = MultiLayerCacheCoordinator().plan(
        req,
        {
            CacheLayer.CAS: probe(
                hit(
                    CacheLayer.CAS,
                    avoided_work_ids=("generate",),
                    verified_boundaries=(boundary,),
                )
            )
        },
    )
    assert plan.verified_boundary_ids == ("generate",)
    assert plan.remaining_work_ids == ("test",)
    assert plan.decisions == (
        ReuseDecision.RESTORE_ARTIFACTS,
        ReuseDecision.EXECUTE_REMAINDER,
    )

    bad_boundary = VerifiedBoundary(
        "generate",
        generate.work_digest,
        (WorkDependency("ir", sha256_bytes(b"wrong-ir")),),
        ValidationLevel.TEST_VERIFIED,
        sha256_bytes(b"bad-evidence"),
    )
    rejected = MultiLayerCacheCoordinator().plan(
        req,
        {
            CacheLayer.CAS: probe(
                hit(
                    CacheLayer.CAS,
                    avoided_work_ids=("generate",),
                    verified_boundaries=(bad_boundary,),
                )
            )
        },
    )
    assert rejected.layers[0].reason_code == "BOUNDARY_DEPENDENCY_MISMATCH"
    assert rejected.remaining_work_ids == ("generate", "ir", "parse", "test")
    assert rejected.decisions == (ReuseDecision.FULL_RECOMPUTE,)


def test_plan_attribution_deduplicates_overlapping_avoided_work() -> None:
    plan = MultiLayerCacheCoordinator().plan(
        request(),
        {
            CacheLayer.CAS: probe(
                hit(
                    CacheLayer.CAS,
                    recompute_ms=102.0,
                    restore_ms=1.0,
                    avoided_work_ids=("compile", "model"),
                )
            ),
            CacheLayer.ENVIRONMENT: probe(
                hit(
                    CacheLayer.ENVIRONMENT,
                    recompute_ms=62.0,
                    restore_ms=1.0,
                    avoided_work_ids=("compile", "setup"),
                )
            ),
        },
    )
    owners = {item.work_id: item for item in plan.attributions}
    assert owners["compile"].primary_layer is CacheLayer.CAS
    assert owners["compile"].supporting_layers == (CacheLayer.ENVIRONMENT,)
    assert len(owners) == 3
    # CAS owns two 50ms units; ENVIRONMENT owns only its new 30ms unit.
    assert predicted_savings(plan) == 130.0
    environment = next(item for item in plan.layers if item.layer is CacheLayer.ENVIRONMENT)
    assert environment.attributed_work_ids == ("setup",)
    assert environment.supporting_work_ids == ("compile",)
    assert sum(item.predicted_saved_ms for item in plan.layers) == predicted_savings(plan)


def test_negative_backoff_is_exact_identity_and_failure_class_scoped() -> None:
    class FakeMonotonic:
        value = 10.0

        def __call__(self) -> float:
            return self.value

    clock = FakeMonotonic()
    coordinator = MultiLayerCacheCoordinator(
        monotonic=clock,
        negative_backoff_policy=NegativeBackoffPolicy(0.5, 2.0),
    )
    def broken() -> LayerProbeResult:
        raise OSError("remote unavailable")

    first = coordinator.plan(request(), {CacheLayer.CAS: broken})
    assert first.layers[0].outcome is ProbeOutcome.ERROR
    second = coordinator.plan(request(), {CacheLayer.CAS: probe(hit(CacheLayer.CAS))})
    assert second.layers[0].outcome is ProbeOutcome.BYPASS
    assert second.layers[0].reason_code == "NEGATIVE_BACKOFF_ACTIVE"

    changed_identity = ReuseRequest(
        "request-changed",
        identity(work=b"work-2"),
        ValidationLevel.TEST_VERIFIED,
    )
    changed = coordinator.plan(
        changed_identity,
        {
            CacheLayer.CAS: probe(
                hit(CacheLayer.CAS, request_identity=changed_identity.identity)
            )
        },
    )
    assert changed.layers[0].outcome is ProbeOutcome.HIT

    clock.value += 0.5
    recovered = coordinator.plan(request(), {CacheLayer.CAS: probe(hit(CacheLayer.CAS))})
    assert recovered.layers[0].outcome is ProbeOutcome.HIT


def test_singleflight_waiter_timeout_and_cancellation_do_not_cancel_shared_execution() -> None:
    coordinator = MultiLayerCacheCoordinator()
    release = threading.Event()
    operation_started = threading.Event()
    lock = threading.Lock()
    calls = 0

    def operation() -> str:
        nonlocal calls
        with lock:
            calls += 1
        operation_started.set()
        release.wait(timeout=1)
        return "shared-result"

    timed_out: list[bool] = []
    values: list[str] = []

    def impatient() -> None:
        try:
            coordinator.execute_singleflight(identity(), operation, timeout_seconds=0.01)
        except TimeoutError:
            timed_out.append(True)

    impatient_thread = threading.Thread(target=impatient)
    impatient_thread.start()
    assert operation_started.wait(timeout=1)

    patient_thread = threading.Thread(
        target=lambda: values.append(coordinator.execute_singleflight(identity(), operation))
    )
    patient_thread.start()
    impatient_thread.join(timeout=1)
    assert timed_out == [True]
    release.set()
    patient_thread.join(timeout=1)
    assert values == ["shared-result"]
    assert calls == 1

    cancel = threading.Event()
    cancel.set()
    release.clear()
    operation_started.clear()
    with pytest.raises(WaiterCancelled):
        coordinator.execute_singleflight(identity(work=b"cancel-work"), operation, cancel_event=cancel)
    assert operation_started.wait(timeout=1)
    follower = threading.Thread(
        target=lambda: values.append(
            coordinator.execute_singleflight(identity(work=b"cancel-work"), operation)
        )
    )
    follower.start()
    release.set()
    follower.join(timeout=1)
    assert values[-1] == "shared-result"
    assert calls == 2


def test_singleflight_owner_lease_reaps_hung_owner_without_deleting_replacement() -> None:
    coordinator = MultiLayerCacheCoordinator(singleflight_owner_lease_seconds=0.25)
    old_started = threading.Event()
    old_release = threading.Event()
    old_completed = threading.Event()
    old_errors: list[type[BaseException]] = []

    def old_operation() -> str:
        old_started.set()
        old_release.wait()
        old_completed.set()
        return "stale-result"

    def old_waiter() -> None:
        try:
            coordinator.execute_singleflight(identity(), old_operation)
        except TimeoutError as exc:
            old_errors.append(type(exc))

    old_waiter_thread = threading.Thread(target=old_waiter)
    old_waiter_thread.start()
    assert old_started.wait(timeout=1)
    old_waiter_thread.join(timeout=0.75)
    assert not old_waiter_thread.is_alive()
    assert old_errors == [TimeoutError]
    assert coordinator.singleflight.active_count == 0

    fresh_started = threading.Event()
    fresh_release = threading.Event()
    fresh_calls = 0
    lock = threading.Lock()
    values: list[str] = []

    def fresh_operation() -> str:
        nonlocal fresh_calls
        with lock:
            fresh_calls += 1
        fresh_started.set()
        assert fresh_release.wait(timeout=1)
        return "fresh-result"

    fresh_owner = threading.Thread(
        target=lambda: values.append(
            coordinator.execute_singleflight(identity(), fresh_operation)
        )
    )
    fresh_owner.start()
    assert fresh_started.wait(timeout=1)

    follower = threading.Thread(
        target=lambda: values.append(
            coordinator.execute_singleflight(
                identity(),
                lambda: "must-not-run",
            )
        )
    )
    follower.start()

    deadline = time.monotonic() + 0.2
    while (
        time.monotonic() < deadline
        and coordinator.singleflight.active_waiter_count(identity()) != 2
    ):
        time.sleep(0.001)
    assert coordinator.singleflight.active_waiter_count(identity()) == 2

    # Completion of the detached stale owner must not remove the replacement.
    old_release.set()
    assert old_completed.wait(timeout=1)
    assert coordinator.singleflight.active_count == 1
    assert coordinator.singleflight.active_waiter_count(identity()) == 2
    fresh_release.set()
    fresh_owner.join(timeout=1)
    follower.join(timeout=1)

    assert not fresh_owner.is_alive()
    assert not follower.is_alive()
    assert sorted(values) == ["fresh-result", "fresh-result"]
    assert fresh_calls == 1
    assert coordinator.singleflight.active_count == 0

    deadline = time.monotonic() + 0.2
    while time.monotonic() < deadline and any(
        thread.name.startswith("elmos-singleflight") for thread in threading.enumerate()
    ):
        time.sleep(0.005)
    assert not any(
        thread.name.startswith("elmos-singleflight") for thread in threading.enumerate()
    )


@pytest.mark.parametrize("lease_seconds", [0.0, -1.0, 301.0, float("inf")])
def test_singleflight_owner_lease_is_strictly_bounded(lease_seconds: float) -> None:
    with pytest.raises(ContractViolation):
        MultiLayerCacheCoordinator(singleflight_owner_lease_seconds=lease_seconds)


def test_singleflight_bounds_detached_hung_owners_and_recovers_capacity() -> None:
    coordinator = MultiLayerCacheCoordinator(
        singleflight_owner_lease_seconds=0.1,
        singleflight_orphan_limit=1,
    )
    started = threading.Event()
    release = threading.Event()
    waiter_errors: list[type[BaseException]] = []

    def hung() -> str:
        started.set()
        release.wait()
        return "eventually-finished"

    def wait_for_hung() -> None:
        try:
            coordinator.execute_singleflight(identity(), hung)
        except TimeoutError as exc:
            waiter_errors.append(type(exc))

    waiter = threading.Thread(target=wait_for_hung)
    waiter.start()
    assert started.wait(timeout=1)
    waiter.join(timeout=1)
    assert not waiter.is_alive()
    assert waiter_errors == [TimeoutError]
    assert coordinator.singleflight.orphaned_owner_count == 1

    with pytest.raises(TimeoutError, match="orphan capacity"):
        coordinator.execute_singleflight(
            identity(work=b"second-owner"),
            lambda: "must-not-start",
        )

    release.set()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and coordinator.singleflight.orphaned_owner_count:
        time.sleep(0.005)
    assert coordinator.singleflight.orphaned_owner_count == 0
    assert (
        coordinator.execute_singleflight(
            identity(work=b"capacity-restored"),
            lambda: "restored",
        )
        == "restored"
    )


@pytest.mark.parametrize("orphan_limit", [0, -1, 1025, True])
def test_singleflight_orphan_capacity_is_strictly_bounded(
    orphan_limit: int,
) -> None:
    with pytest.raises(ContractViolation):
        MultiLayerCacheCoordinator(singleflight_orphan_limit=orphan_limit)


def test_planned_vs_realized_reconciliation_binds_plan_owner_and_dag_remainder() -> None:
    plan = MultiLayerCacheCoordinator().plan(
        request(),
        {
            CacheLayer.CAS: probe(
                hit(
                    CacheLayer.CAS,
                    recompute_ms=100.0,
                    restore_ms=5.0,
                    avoided_work_ids=("compile",),
                )
            )
        },
    )
    realization = PlanRealization(
        plan.request_id,
        plan.plan_digest,
        (RealizedLayer(CacheLayer.CAS, True, ("compile",), 94.0),),
    )
    reconciled = reconcile_plan(plan, realization)
    assert reconciled.status is ReconciliationStatus.RECONCILED
    assert reconciled.relative_error == 0.0

    wrong_owner = PlanRealization(
        plan.request_id,
        plan.plan_digest,
        (RealizedLayer(CacheLayer.ENVIRONMENT, True, ("compile",), 94.0),),
    )
    diverged = reconcile_plan(plan, wrong_owner)
    assert diverged.status is ReconciliationStatus.DIVERGED
    assert diverged.wrong_owner_work_ids == ("compile",)

    with pytest.raises(ContractViolation, match="attributed twice"):
        PlanRealization(
            plan.request_id,
            plan.plan_digest,
            (
                RealizedLayer(CacheLayer.CAS, True, ("compile",), 50.0),
                RealizedLayer(CacheLayer.ENVIRONMENT, True, ("compile",), 44.0),
            ),
        )
