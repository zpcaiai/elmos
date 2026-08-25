"""The policy plane, assembled from configuration and wired into the engine.

Every capability the ``policy`` configuration section names is switched on
here and nowhere else, so there is exactly one place to read when the question
is "what is this deployment actually doing?".

The rule the whole plane obeys: **it may change what is kept, fetched early or
recorded -- never what is valid.**

* Admission may refuse to *record a cache entry*. It can never refuse to write,
  seal, promote or publish an output: by the time it is consulted the artifact
  is already in content-addressable storage and already in the run's tree. The
  worst a refusal costs is a recomputation next time.
* Prefetch may warm a cache. It never decides reuse; the action cache's own
  policy checks are untouched by it.
* The orchestrator and the learned controller only ever produce a
  *recommendation*, recorded in the run report. Neither can switch a live
  policy mid-run, because a cache that changes its replacement algorithm
  half-way through a run cannot be reasoned about afterwards.

Each capability is independently switchable and every one of them defaults to
off, so an operator can turn on exactly the thing they have evidence for.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from typing import Any

from .cache_admission import AdmissionController, AdmissionDecision, CostModel, ReuseEstimator
from .cache_policy import CacheObject, create_policy
from .cache_simulator import ObjectiveProfile
from .cache_trace import Access, CacheTraceEvent, Tier, TraceRecorder, key_hash, workload_features
from .config import PolicyConfig
from .dag import ConversionDag
from .dag_prefetch import Artifact, FutureUseIndex, PrefetchBudget, PrefetchDecision, PrefetchPlanner
from .errors import ContractViolation
from .learned_control import LearningAugmentedController, ModelRegistry
from .policy_orchestrator import PolicyOrchestrator, RuleSelector
from .security import ProvenanceSigner

SCHEMA_VERSION = "1.1.0"

#: Capacity assumed for the admission/orchestration view when the deployment
#: has not sized a tier explicitly. Only ever used to make relative decisions.
DEFAULT_CAPACITY_BYTES = 8 * 1024 * 1024 * 1024


def derive_trace_secret(tenant_id: str, salt: str) -> bytes:
    """A stable pseudonymisation key that is not, and cannot become, a credential.

    Derived rather than configured on purpose: a trace's tenant pseudonyms must
    be stable across runs so reuse chains join up, but the value must never be
    something an operator is tempted to reuse as a real secret. It is derived
    from identifiers that are already public inside the deployment.
    """
    return sha256(f"elmos.cache.trace/{salt}\x00{tenant_id}".encode()).digest()


class PolicyPlane:
    """One object holding every switched-on policy capability for one run."""

    def __init__(
        self,
        config: PolicyConfig,
        *,
        tenant_id: str,
        capacity_bytes: int = DEFAULT_CAPACITY_BYTES,
        trace_salt: str = "default",
        signer: ProvenanceSigner | None = None,
    ) -> None:
        self.config = config
        self.tenant_id = tenant_id
        self.capacity_bytes = max(capacity_bytes, 1)
        self.objective = ObjectiveProfile(config.objective_profile)

        self.recorder: TraceRecorder | None = None
        self.admission: AdmissionController | None = None
        self.orchestrator: PolicyOrchestrator | None = None
        self.learned: LearningAugmentedController | None = None
        self.prefetcher: PrefetchPlanner | None = None

        self.admission_refusals: list[dict[str, Any]] = []
        self.prefetch_decisions: list[PrefetchDecision] = []

        if not config.enabled:
            return

        if config.trace_capture:
            self.recorder = TraceRecorder(
                derive_trace_secret(tenant_id, trace_salt),
                sample_rate=config.trace_sample_rate or 1.0,
                per_tenant_budget=config.trace_per_tenant_budget,
            )

        if config.admission_enabled:
            # The admission controller needs a policy to consult for protection
            # and residency. It is given the L1 policy, which is the tier an
            # action-cache entry actually lives in.
            self.admission = AdmissionController(
                create_policy(config.l1_policy, self.capacity_bytes),
                cost_model=CostModel(),
                estimator=ReuseEstimator(),
            )

        if config.adaptive_selection:
            self.orchestrator = PolicyOrchestrator(
                "L1",
                self.capacity_bytes,
                objective=self.objective,
                selector=RuleSelector(),
                initial_policy=config.l1_policy,
                minimum_dwell_events=config.minimum_dwell_events,
                improvement_margin=config.improvement_margin,
                fallback_policy=config.fallback,
            )

        if config.learned_tuning:
            if signer is None:
                # An unsigned model registry would make every safety property
                # downstream of it unenforceable, so this is refused rather
                # than degraded.
                raise ContractViolation(
                    "policy.learned_tuning requires a provenance signer; "
                    "an unsigned model registry cannot verify what it loads"
                )
            self.learned = LearningAugmentedController(
                ModelRegistry(signer),
                shadow_only=config.learned_shadow_only,
                canary_fraction=config.learned_canary_fraction,
            )

    @classmethod
    def from_config(
        cls,
        config: PolicyConfig,
        *,
        tenant_id: str,
        capacity_bytes: int = DEFAULT_CAPACITY_BYTES,
        trace_salt: str = "default",
        signer: ProvenanceSigner | None = None,
    ) -> PolicyPlane:
        return cls(
            config,
            tenant_id=tenant_id,
            capacity_bytes=capacity_bytes,
            trace_salt=trace_salt,
            signer=signer,
        )

    # -- capability flags --------------------------------------------------
    @property
    def active(self) -> bool:
        return any(
            (self.recorder, self.admission, self.orchestrator, self.learned, self.prefetcher)
        )

    # -- trace capture -----------------------------------------------------
    def record_access(
        self,
        *,
        action_key: str,
        tier: Tier,
        access: Access,
        hit: bool,
        size_bytes: int,
        stage_class: str,
        recompute_ms: float,
        restore_ms: float,
        validation_level: str = "UNVERIFIED",
        model_tokens: int = 0,
        trust_namespace: str = "",
        dag_step: int | None = None,
    ) -> CacheTraceEvent | None:
        """Record one access if capture is on. Returns ``None`` when it is off.

        The ActionKey is hashed again here even though it is already a digest,
        because a trace must not carry a value that can be joined back to a
        live cache entry by anyone who obtains the trace.
        """
        if self.recorder is None:
            return None
        return self.recorder.record(
            key_hash=key_hash(action_key),
            tenant_id=self.tenant_id,
            tier=tier,
            access=access,
            hit=hit,
            size_bytes=max(size_bytes, 0),
            stage_class=stage_class,
            recompute_ms=max(recompute_ms, 0.0),
            restore_ms=max(restore_ms, 0.0),
            validation_level=validation_level,
            model_tokens=max(model_tokens, 0),
            trust_namespace=trust_namespace,
            dag_step=dag_step,
        )

    # -- admission ---------------------------------------------------------
    def admit(
        self,
        *,
        action_key: str,
        size_bytes: int,
        stage_class: str,
        recompute_ms: float,
        restore_ms: float,
        validation_level: str,
        model_tokens: int = 0,
        critical_path_weight: float = 0.0,
    ) -> AdmissionDecision | None:
        """Should this result be *recorded* as a reusable cache entry?

        ``None`` means admission is switched off, which the caller must treat
        as "record it" -- the historical behaviour. A refusal is never a
        failure: the outputs are already promoted and published, and refusing
        only means the next identical run recomputes instead of restoring.
        """
        if self.admission is None:
            return None
        decision = self.admission.admit(
            CacheObject(
                key=key_hash(action_key),
                size_bytes=max(size_bytes, 0),
                recompute_ms=max(recompute_ms, 0.0),
                restore_ms=max(restore_ms, 0.0),
                model_tokens=max(model_tokens, 0),
                critical_path_weight=critical_path_weight,
                stage_class=stage_class,
                validation_level=validation_level,
                tenant_hash=key_hash(self.tenant_id),
            )
        )
        if not decision.admitted:
            self.admission_refusals.append(
                {"stage_class": stage_class, "reasons": list(decision.reasons)}
            )
        return decision

    # -- prefetch ----------------------------------------------------------
    def prepare_prefetch(self, dag: ConversionDag, artifacts: Mapping[str, Artifact]) -> None:
        """Build the next-use index from the real DAG, once per run."""
        if not self.config.enabled or not self.config.prefetch_enabled:
            return
        if not artifacts:
            return
        self.prefetcher = PrefetchPlanner(
            FutureUseIndex.from_dag(dag, artifacts),
            PrefetchBudget(
                horizon=self.config.prefetch_horizon,
                max_in_flight=self.config.prefetch_max_in_flight,
                max_bytes=self.config.prefetch_max_bytes,
            ),
        )

    def plan_prefetch(self, position: int, resident: Iterable[str] = ()) -> list[PrefetchDecision]:
        if self.prefetcher is None:
            return []
        issued = self.prefetcher.plan(position, resident)
        self.prefetch_decisions.extend(issued)
        return issued

    def observe_consumption(self, keys: Iterable[str], *, arrived_in_time: bool = True) -> None:
        """Tell the prefetcher which of its guesses were actually consumed.

        Precision is only meaningful if the misses are counted too, so this is
        called for every consumed key, not only the prefetched ones -- the
        planner ignores keys it never issued.
        """
        if self.prefetcher is None:
            return
        for key in keys:
            self.prefetcher.observe_consumption(key, arrived_in_time=arrived_in_time)

    # -- end-of-run recommendations ---------------------------------------
    def recommend(self) -> dict[str, Any]:
        """What the plane would advise for the *next* run. Never applied here.

        Deliberately end-of-run: a replacement policy that changes half-way
        through a run makes every number collected during that run
        uninterpretable, and a parameter that moves under a live workload is
        indistinguishable from the workload moving.
        """
        events: Sequence[CacheTraceEvent] = self.recorder.events if self.recorder else ()
        out: dict[str, Any] = {"schema_version": SCHEMA_VERSION}

        if not events:
            out["features"] = {}
        else:
            out["features"] = workload_features(events)

        if self.orchestrator is not None and events:
            self.orchestrator.observe(events)
            epoch, selection = self.orchestrator.evaluate(events)
            out["selection"] = selection.to_dict()
            out["epoch"] = epoch.policy_epoch
            out["orchestrator"] = self.orchestrator.state()
        elif self.orchestrator is not None:
            out["selection"] = None
            out["orchestrator_note"] = "no trace events; adaptive selection needs trace_capture on"

        if self.learned is not None:
            proposal = self.learned.propose(out["features"], feature_age_seconds=0.0)
            out["parameters"] = proposal.to_dict()

        return out

    # -- reporting ---------------------------------------------------------
    def report(self) -> dict[str, Any]:
        """Exactly which capabilities ran, and what they did."""
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "enabled": self.config.enabled,
            "capabilities": {
                "trace_capture": self.recorder is not None,
                "admission": self.admission is not None,
                "prefetch": self.prefetcher is not None,
                "adaptive_selection": self.orchestrator is not None,
                "learned_tuning": self.learned is not None,
            },
            "tiers": {
                "L0": self.config.l0_policy,
                "L1": self.config.l1_policy,
                "L2": self.config.l2_policy,
            },
            "objective_profile": self.objective.value,
        }
        if self.recorder is not None:
            payload["trace"] = self.recorder.stats()
        if self.admission is not None:
            payload["admission"] = self.admission.stats()
            payload["admission_refusals"] = self.admission_refusals
        if self.prefetcher is not None:
            payload["prefetch"] = self.prefetcher.metrics.to_dict()
        return payload
