"""End-to-end orchestration and staged rollout.

The authoritative flow, in the order the specification fixes it:

    snapshot -> discover -> analyse -> Semantic IR -> plan -> resolve cache
    -> allocate workspace -> generate into staging -> seal -> promote
    -> assemble the complete tree -> build/test/behaviour-validate -> repair
    -> evidence bundle -> atomic publish

Two properties the pipeline is responsible for, which no single component can
guarantee on its own:

* **every skipped computation is justified** -- a node is only skipped or
  restored because a compatible cache entry said so, and the justification is
  recorded on the run report;
* **every final file is reachable from the sealed tree manifest** -- the
  publish step derives its file list from sealed staged files, never from
  whatever happens to be on disk.

Rollout is phased and reversible: staging-only, shadow-compare, local read,
shared read, limited write, production. The kill switch collapses to
``bypass`` without touching any other configuration.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .action_cache import ActionCache, CommitRequest, HotIndex, LookupRequest, LookupResult
from .cache_trace import Access, Tier
from .canonical import digest_of
from .cas import ContentAddressableStore
from .checkpoint import CheckpointService, CompatibilityProfile
from .clock import SYSTEM_CLOCK, Clock
from .config import CacheConfig, RolloutConfig
from .coordinator import (
    CacheLayer as CoordinatorCacheLayer,
)
from .coordinator import (
    LayerProbeResult,
    MultiLayerCacheCoordinator,
    ProbeOutcome,
    ReuseBudgets,
    ReuseDecision,
    ReuseIdentity,
    ReusePlan,
    ReuseRequest,
)
from .dag import CacheProbe, ConversionDag, DagNode, ExecutionPlan, NodeDecision, ProbeResult
from .dag_prefetch import Artifact
from .db import MetadataStore
from .db.records import StagedFileRecord
from .enums import (
    CacheMode,
    FileClass,
    MissReason,
    NodeStatus,
    Ownership,
    TrustNamespace,
    ValidationLevel,
)
from .errors import ContractViolation, ElmosCacheError, NotFound, PermissionDenied
from .fingerprint import Fingerprint, FingerprintInputs, build_action_key, explain_miss
from .journal import LeaseManager, RunCoordinator, RunJournal
from .manifests import ActionResultManifest, EvidenceBundle, ExecutionMetrics, FileTreeManifest
from .observability import CacheAccounting, MetricsRegistry, PerformanceGate, Tracer, summarize_run
from .parity_runtime import ParityRuntime
from .parity_store import ParityMetadataRepository
from .policy_plane import PolicyPlane
from .publish import PublishResult, TreePublisher
from .security import ProvenanceSigner, SecurityGate, SignedStatement
from .snapshot import Snapshot, SnapshotPolicy, take_snapshot
from .stage_contract import StageContract, StageContractRegistry, default_registry
from .staging import Workspace

SCHEMA_VERSION = "1.0.0"

ROLLOUT_PHASES: tuple[str, ...] = (
    "staging-only",
    "shadow-compare",
    "local-read",
    "shared-read",
    "limited-write",
    "production-certified",
)


@dataclass(frozen=True)
class StageOutput:
    """What a stage implementation returns to the pipeline."""

    logical_path: str
    payload: bytes
    file_class: FileClass = FileClass.PUBLISH_CANDIDATE
    media_type: str = "text/plain"
    ownership: Ownership = Ownership.GENERATED
    mode: int = 0o644
    source_map: dict[str, Any] | None = None


@dataclass(frozen=True)
class StageResult:
    outputs: tuple[StageOutput, ...]
    metrics: ExecutionMetrics = field(default_factory=ExecutionMetrics)
    completed_partitions: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    validation_level: ValidationLevel = ValidationLevel.UNVERIFIED


#: A stage implementation: given its node and inputs, produce outputs.
StageFunction = Callable[[DagNode, Mapping[str, Any]], StageResult]


@dataclass(frozen=True)
class NodeReport:
    node_id: str
    stage_id: str
    decision: str
    justification: tuple[str, ...]
    action_key: str | None
    miss_reasons: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    checkpoint_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "stage_id": self.stage_id,
            "decision": self.decision,
            "justification": list(self.justification),
            "action_key": self.action_key,
            "miss_reasons": list(self.miss_reasons),
            "outputs": list(self.outputs),
            "metrics": self.metrics,
            "checkpoint_id": self.checkpoint_id,
        }


@dataclass(frozen=True)
class RunReport:
    run_id: str
    snapshot_digest: str
    plan_digest: str
    tree_digest: str | None
    published: bool
    nodes: tuple[NodeReport, ...]
    telemetry: dict[str, Any]
    rollout_phase: str
    shadow: dict[str, Any] | None = None
    failures: tuple[dict[str, Any], ...] = ()
    #: What the policy plane did this run, and what it advises for the next.
    #: A recommendation, never an applied change -- see ``PolicyPlane``.
    policy: dict[str, Any] | None = None
    #: Observation-first v1.2 parity state. External/provider evidence remains
    #: explicit and no partial layer is allowed to authorise publication.
    parity: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "snapshot_digest": self.snapshot_digest,
            "plan_digest": self.plan_digest,
            "tree_digest": self.tree_digest,
            "published": self.published,
            "rollout_phase": self.rollout_phase,
            "nodes": [node.to_dict() for node in self.nodes],
            "telemetry": self.telemetry,
            "shadow": self.shadow,
            "failures": list(self.failures),
            "policy": self.policy,
            "parity": self.parity,
        }

    def unjustified_skips(self) -> list[str]:
        """Any skipped/restored node without a cache justification is a bug."""
        offenders: list[str] = []
        for node in self.nodes:
            if node.decision in ("RESTORE", "SKIP") and not node.justification:
                offenders.append(node.node_id)
        return offenders


class RolloutController:
    """Feature flags, phase gating and the kill switch."""

    def __init__(self, config: RolloutConfig) -> None:
        if config.phase not in ROLLOUT_PHASES:
            raise ContractViolation("unknown rollout phase", phase=config.phase)
        self.config = config

    @property
    def phase_index(self) -> int:
        return ROLLOUT_PHASES.index(self.config.phase)

    def cache_mode(self, declared: CacheMode) -> CacheMode:
        """Collapse the declared mode to whatever the current phase allows."""
        if self.config.kill_switch:
            return CacheMode.BYPASS
        if self.phase_index <= ROLLOUT_PHASES.index("shadow-compare"):
            return CacheMode.BYPASS if self.config.shadow_compare else CacheMode.WRITE_ONLY
        if self.phase_index < ROLLOUT_PHASES.index("limited-write"):
            return CacheMode.READ_ONLY if declared.may_read else CacheMode.BYPASS
        return declared

    @property
    def remote_read(self) -> bool:
        return (
            self.config.remote_cache_read
            and not self.config.kill_switch
            and self.phase_index >= ROLLOUT_PHASES.index("shared-read")
        )

    @property
    def remote_write(self) -> bool:
        return (
            self.config.remote_cache_write
            and not self.config.kill_switch
            and self.phase_index >= ROLLOUT_PHASES.index("limited-write")
        )

    @property
    def may_publish(self) -> bool:
        return not self.config.kill_switch and self.phase_index > ROLLOUT_PHASES.index("staging-only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.config.phase,
            "kill_switch": self.config.kill_switch,
            "shadow_compare": self.config.shadow_compare,
            "remote_read": self.remote_read,
            "remote_write": self.remote_write,
            "may_publish": self.may_publish,
        }


class _CoordinatorServingControl:
    """Runtime-owned rollback latch for the production coordinator seam."""

    def __init__(self) -> None:
        self._serving = True
        self.reason_code: str | None = None

    def is_serving(self) -> bool:
        return self._serving

    def latch_rollback(self, reason_code: str) -> None:
        self._serving = False
        self.reason_code = reason_code


class ConversionPipeline:
    """Wires contracts, DAG, cache, staging, checkpoints and publication."""

    def __init__(
        self,
        config: CacheConfig,
        store: MetadataStore,
        cas: ContentAddressableStore,
        base_path: Path,
        tenant_id: str,
        project_id: str,
        registry: StageContractRegistry | None = None,
        clock: Clock = SYSTEM_CLOCK,
        trust_namespace: TrustNamespace = TrustNamespace.BRANCH,
        producer_identity: str = "elmos-worker",
        signer: ProvenanceSigner | None = None,
        parity_serving_gate_receipt: SignedStatement | None = None,
        parity_serving_gate_verifier: ProvenanceSigner | None = None,
        multi_layer_coordinator: MultiLayerCacheCoordinator | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.cas = cas
        self.base_path = Path(base_path)
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.registry = registry or default_registry()
        self.clock = clock
        self.trust_namespace = trust_namespace
        self.producer_identity = producer_identity
        self.rollout = RolloutController(config.rollout)
        self.metrics = MetricsRegistry()
        self.tracer = Tracer(self.metrics, clock)
        self.accounting = CacheAccounting(self.metrics)
        self.action_cache = ActionCache(
            store,
            cas,
            clock,
            negative_ttl_seconds=config.validation.negative_cache_ttl_seconds,
            hot_index=HotIndex.from_config(config.policy),
        )
        self.security = SecurityGate(config=config.security)
        self.policy_plane = PolicyPlane.from_config(
            config.policy,
            tenant_id=tenant_id,
            capacity_bytes=config.local.max_size_gb * 1024**3,
            trace_salt=project_id,
            signer=signer,
        )
        self.multi_layer_cache_coordinator = multi_layer_coordinator or MultiLayerCacheCoordinator(
            max_parallel_probes=config.parity.coordinator.max_parallel_probes
        )
        self._coordinator_serving_control = (
            _CoordinatorServingControl() if config.parity.coordinator.enabled else None
        )
        coordinator_controls = (
            {"multi_layer_coordinator": self._coordinator_serving_control}
            if self._coordinator_serving_control is not None
            else {}
        )
        self._parity_serving_gate_receipt = parity_serving_gate_receipt
        self.parity_runtime = ParityRuntime(
            config.parity,
            tenant_id,
            project_id,
            sink=ParityMetadataRepository(store) if config.parity.enabled else None,
            clock=clock,
            # Only the exact Action Cache coordinator is a production path in
            # this pipeline. Other optional v1.2 layers remain explicitly
            # unwired rather than being represented by configuration booleans.
            serving_controls=coordinator_controls,
            serving_gate_receipt=parity_serving_gate_receipt,
            serving_gate_verifier=parity_serving_gate_verifier,
        )
        self._coordinator_plans: dict[str, ReusePlan] = {}
        self._fingerprints: dict[str, Fingerprint] = {}
        self._previous_fingerprints: dict[str, Fingerprint] = {}
        self._node_outputs: dict[str, dict[str, Any]] = {}

    # -- snapshot ---------------------------------------------------------
    def snapshot(self, source_root: Path, policy: SnapshotPolicy | None = None) -> Snapshot:
        with self.tracer.span("elmos.snapshot.take", stage_id="repository-snapshot"):
            snapshot = take_snapshot(source_root, policy)
        manifest_digest = self.cas.put_document(snapshot.to_manifest(), artifact_kind="snapshot-manifest")
        self.store.ensure_project(self.tenant_id, self.project_id)
        self.store.register_artifact(
            self.tenant_id,
            manifest_digest,
            size_bytes=self.cas.info(manifest_digest).size,
            media_type="application/json",
            artifact_kind="snapshot-manifest",
        )
        return snapshot

    # -- fingerprints -----------------------------------------------------
    def fingerprint_for(
        self, node: DagNode, contract: StageContract, inputs: FingerprintInputs
    ) -> Fingerprint:
        fingerprint = build_action_key(contract.fingerprint_spec(), inputs)
        self._fingerprints[node.node_id] = fingerprint
        document_digest = self.cas.put_document(fingerprint.document, artifact_kind="fingerprint")
        self.store.register_artifact(
            self.tenant_id,
            document_digest,
            size_bytes=self.cas.info(document_digest).size,
            media_type="application/json",
            artifact_kind="fingerprint",
        )
        return fingerprint

    def seed_previous_fingerprints(self, previous: Mapping[str, Fingerprint]) -> None:
        """Give the planner last run's keys so a miss can be attributed."""
        self._previous_fingerprints = dict(previous)

    # -- planning ---------------------------------------------------------
    def plan(
        self,
        dag: ConversionDag,
        affected: Mapping[str, Sequence[str]],
        minimum_validation: ValidationLevel | None = None,
    ) -> ExecutionPlan:
        minimum = minimum_validation or self.config.validation.default_minimum

        def probe(node: DagNode) -> ProbeResult:
            fingerprint = self._fingerprints.get(node.node_id)
            if fingerprint is None:
                return ProbeResult(False, None, (MissReason.NO_ENTRY,))
            mode = self.rollout.cache_mode(node.cache_mode)
            required_validation = max(
                minimum,
                node.validation_floor,
                key=lambda value: value.rank,
            )
            authorization_digest = self._coordinator_authorization_digest()
            coordinator_started = time.monotonic() if authorization_digest is not None else None
            lookup_started = time.monotonic()
            with self.tracer.span("elmos.cache.lookup", stage_id=node.stage_id):
                result = self.action_cache.lookup(
                    LookupRequest(
                        tenant_id=self.tenant_id,
                        action_key=fingerprint.action_key,
                        trust_namespace=self.trust_namespace,
                        minimum_validation=required_validation,
                        mode=mode,
                        estimated_recompute_ms=(
                            float(node.estimated_cost_ms)
                            if authorization_digest is not None
                            else None
                        ),
                    )
                )
            lookup_ms = max(0.0, (time.monotonic() - lookup_started) * 1_000.0)
            effective_hit = result.hit
            effective_reasons = result.reasons
            restore_ms = float(result.detail.get("restore_ms", 0.0) or 0.0)
            # A coordinator safety failure latches rollback for the whole
            # pipeline instance.  Subsequent nodes must recompute rather than
            # silently falling back to a cache restore after the new serving
            # path has declared the run unsafe.  A merely absent serving gate
            # does not set this latch, so the established Action Cache path is
            # left unchanged when the optional coordinator is not authorized.
            if (
                self._coordinator_serving_control is not None
                and self._coordinator_serving_control.reason_code is not None
            ):
                effective_hit = False
                effective_reasons = (MissReason.POLICY_BYPASS,)
            if authorization_digest is not None and coordinator_started is not None:
                try:
                    reuse_plan, identity, restore_ms = self._coordinate_action_lookup(
                        node,
                        fingerprint,
                        result,
                        required_validation,
                        authorization_digest,
                        lookup_ms,
                        coordinator_started,
                    )
                    self._coordinator_plans[node.node_id] = reuse_plan
                    effective_hit = self._coordinator_authorizes_restore(
                        reuse_plan,
                        identity,
                        result,
                    )
                    if result.hit and not effective_hit:
                        safety_failure = self._coordinator_safety_failure(
                            reuse_plan,
                            identity,
                        )
                        if safety_failure is not None:
                            self.parity_runtime.latch_rollback(safety_failure)
                        effective_reasons = (
                            self._coordinator_rejection_reason(reuse_plan),
                        )
                except Exception:  # noqa: BLE001 - optional planner must fail to recompute
                    self.parity_runtime.latch_rollback("COORDINATOR_PLANNING_FAILED")
                    effective_hit = False
                    effective_reasons = (MissReason.POLICY_BYPASS,)
            # Capture the access as the policy plane sees it. This is the
            # real lookup path, so a captured trace describes decisions the
            # deployment actually took rather than a replay of a guess.
            self.policy_plane.record_access(
                action_key=fingerprint.action_key,
                tier=Tier.L1_LOCAL_CAS,
                access=Access.GET,
                hit=effective_hit,
                size_bytes=int(result.detail.get("size_bytes", 0) or 0),
                stage_class=node.stage_id,
                recompute_ms=float(node.estimated_cost_ms),
                restore_ms=restore_ms,
                model_tokens=result.entry.saved_model_tokens if result.entry else 0,
                validation_level=(
                    str(result.entry.validation_level) if result.entry else "UNVERIFIED"
                ),
                trust_namespace=str(self.trust_namespace),
            )
            if self.config.parity.enabled:
                self.parity_runtime.observe_action(
                    node_id=node.node_id,
                    action_key=fingerprint.action_key,
                    hit=effective_hit,
                    miss_reasons=effective_reasons,
                )
            if effective_hit:
                return ProbeResult(True, fingerprint.action_key, ())
            reasons = effective_reasons
            previous = self._previous_fingerprints.get(node.node_id)
            if previous is not None:
                reasons = tuple(explain_miss(fingerprint, previous, effective_reasons).reasons)
            return ProbeResult(False, fingerprint.action_key, reasons)

        return dag.plan(affected, CacheProbe(probe))

    @property
    def coordinator_plans(self) -> Mapping[str, ReusePlan]:
        """Plans that actually participated in this pipeline instance."""

        return dict(self._coordinator_plans)

    def _coordinator_authorization_digest(self) -> str | None:
        if not self.config.parity.coordinator.enabled:
            return None
        try:
            self.parity_runtime.authorize_serving(
                "multi_layer_coordinator",
                self.tenant_id,
                self.project_id,
            )
        except PermissionDenied:
            return None
        receipt = self._parity_serving_gate_receipt
        if receipt is None:
            # ``authorize_serving`` cannot legally succeed without this, but
            # keep the composition boundary fail closed if that invariant ever
            # regresses.
            self.parity_runtime.latch_rollback("COORDINATOR_AUTHORIZATION_MISSING")
            return None
        return digest_of(receipt.to_dict())

    def _coordinate_action_lookup(
        self,
        node: DagNode,
        fingerprint: Fingerprint,
        result: LookupResult,
        minimum_validation: ValidationLevel,
        authorization_digest: str,
        lookup_ms: float,
        decision_started: float,
    ) -> tuple[ReusePlan, ReuseIdentity, float]:
        contract = self.registry.get(node.stage_id)
        identity = ReuseIdentity(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            authorization_digest=authorization_digest,
            compatibility_digest=digest_of(
                {
                    "stage_id": node.stage_id,
                    "stage_version": contract.stage_version,
                    "stage_contract_digest": contract.digest(),
                    "trust_namespace": str(self.trust_namespace),
                    "result_schema": "elmos.action-result/v1",
                }
            ),
            work_digest=fingerprint.action_key,
        )
        restore_ms = float(result.detail.get("restore_ms", 0.0) or 0.0)
        if result.hit:
            if result.entry is None or result.result is None or result.result_digest is None:
                raise ContractViolation("authoritative Action Cache hit is incomplete")
            artifacts = result.result.get("output_artifacts", ())
            if not isinstance(artifacts, list):
                raise ContractViolation("Action Result outputs must be a list")
            restore_ms = self._estimated_restore_ms(tuple(str(item) for item in artifacts))
            layer_result = LayerProbeResult(
                layer=CoordinatorCacheLayer.ACTION,
                outcome=ProbeOutcome.HIT,
                reason_code="HIT",
                identity=identity,
                artifact_digest=result.result_digest,
                validation_level=result.entry.validation_level,
                verified=True,
                authorised=True,
                compatible=True,
                complete_result=True,
                lookup_ms=lookup_ms,
                restore_ms=restore_ms,
                recompute_ms=float(node.estimated_cost_ms),
                avoided_work_ids=(node.node_id,),
            )
        else:
            reason = result.reasons[0].value if result.reasons else MissReason.NO_ENTRY.value
            layer_result = LayerProbeResult(
                layer=CoordinatorCacheLayer.ACTION,
                outcome=ProbeOutcome.MISS,
                reason_code=reason,
                identity=identity,
                validation_level=(
                    result.entry.validation_level
                    if result.entry is not None
                    else ValidationLevel.UNVERIFIED
                ),
                lookup_ms=lookup_ms,
                recompute_ms=float(node.estimated_cost_ms),
            )
        request = ReuseRequest(
            request_id="action-" + fingerprint.action_key.removeprefix("sha256:")[:32],
            identity=identity,
            minimum_validation=minimum_validation,
            allow_provider_prefix=False,
            budgets=ReuseBudgets(
                max_probes=self.config.parity.coordinator.max_parallel_probes,
            ),
        )
        plan = self.multi_layer_cache_coordinator.plan_prevalidated(
            request,
            {CoordinatorCacheLayer.ACTION: layer_result},
            decision_started_monotonic=decision_started,
        )
        return plan, identity, restore_ms

    @staticmethod
    def _coordinator_authorizes_restore(
        plan: ReusePlan,
        identity: ReuseIdentity,
        result: LookupResult,
    ) -> bool:
        action_layers = [layer for layer in plan.layers if layer.layer is CoordinatorCacheLayer.ACTION]
        return (
            result.hit
            and result.result_digest is not None
            and plan.identity_digest == identity.singleflight_key
            and plan.complete_result_layer is CoordinatorCacheLayer.ACTION
            and not plan.execution_required
            and ReuseDecision.REUSE_EXACT_RESULT in plan.decisions
            and not plan.budget_usage.breaches
            and len(action_layers) == 1
            and action_layers[0].accepted
            and action_layers[0].complete_result
            and action_layers[0].artifact_digest == result.result_digest
        )

    @staticmethod
    def _coordinator_rejection_reason(plan: ReusePlan) -> MissReason:
        action = next(
            (layer for layer in plan.layers if layer.layer is CoordinatorCacheLayer.ACTION),
            None,
        )
        reason = action.reason_code if action is not None else "POLICY_BYPASS"
        if reason == "VALIDATION_TOO_LOW":
            return MissReason.VALIDATION_TOO_LOW
        if reason == "IDENTITY_MISMATCH":
            return MissReason.TENANT_MISMATCH
        if reason in {"AUTHORIZATION_DENIED", "UNVERIFIED_MATERIAL"}:
            return MissReason.PROVENANCE_INVALID
        if reason in {
            "COMPATIBILITY_MISMATCH",
            "BOUNDARY_DEPENDENCY_MISMATCH",
            "BOUNDARY_GRAPH_MISSING",
        }:
            return MissReason.SCHEMA_INCOMPATIBLE
        if reason in {
            "RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE",
            "RESTORE_BUDGET_EXCEEDED",
        }:
            return MissReason.RESTORE_COST_EXCEEDS_RECOMPUTE
        return MissReason.POLICY_BYPASS

    @staticmethod
    def _coordinator_safety_failure(
        plan: ReusePlan,
        identity: ReuseIdentity,
    ) -> str | None:
        if plan.identity_digest != identity.singleflight_key:
            return "COORDINATOR_IDENTITY_MISMATCH"
        action = next(
            (layer for layer in plan.layers if layer.layer is CoordinatorCacheLayer.ACTION),
            None,
        )
        if action is not None and action.reason_code in {
            "AUTHORIZATION_DENIED",
            "COMPATIBILITY_MISMATCH",
            "UNVERIFIED_MATERIAL",
        }:
            return "COORDINATOR_UNSAFE_CANDIDATE"
        return None

    # -- execution --------------------------------------------------------
    def execute(
        self,
        run_id: str,
        dag: ConversionDag,
        plan: ExecutionPlan,
        snapshot: Snapshot,
        implementations: Mapping[str, StageFunction],
        workspace: Workspace,
        coordinator: RunCoordinator,
        checkpoints: CheckpointService,
        worker: str = "worker-1",
    ) -> list[NodeReport]:
        reports: list[NodeReport] = []
        self._prepare_prefetch(dag, plan)
        for position, wave in enumerate(plan.waves):
            # Prefetch is planned per wave, against the real DAG order, so a
            # decision can only ever be about work the plan already commits to.
            for decision in self.policy_plane.plan_prefetch(position):
                self.metrics.increment("elmos.cache.prefetch.issued", reason=decision.reason)
            for node_id in wave:
                node = dag.node(node_id)
                node_plan = plan.decision_of(node_id)
                if node_plan.decision is NodeDecision.BLOCKED:
                    reports.append(
                        NodeReport(node_id, node.stage_id, "BLOCKED", node_plan.reasons, node_plan.action_key)
                    )
                    continue
                if node_plan.decision is NodeDecision.RESTORE:
                    reports.append(
                        self._restore(
                            run_id,
                            node,
                            node_plan.action_key,
                            node_plan.reasons,
                            workspace,
                            coordinator,
                            worker,
                        )
                    )
                    continue
                if node_plan.decision is NodeDecision.SKIP:
                    reports.append(
                        NodeReport(node_id, node.stage_id, "SKIP", node_plan.reasons, node_plan.action_key)
                    )
                    continue
                reports.append(
                    self._execute_node(
                        run_id,
                        node,
                        node_plan.reasons,
                        node_plan.miss_reasons,
                        snapshot,
                        implementations,
                        workspace,
                        coordinator,
                        checkpoints,
                        worker,
                    )
                )
        return reports

    def _prepare_prefetch(self, dag: ConversionDag, plan: ExecutionPlan) -> None:
        """Describe the restorable artifacts to the prefetcher, once per run.

        Only nodes the plan decided to RESTORE are offered: a node that will be
        executed has nothing to fetch, and offering it would let the prefetcher
        spend budget on bytes nobody is going to read.
        """
        if not self.config.policy.prefetch_enabled:
            return
        artifacts: dict[str, Artifact] = {}
        for node in dag.nodes:
            decision = plan.decision_of(node.node_id)
            if decision.decision is not NodeDecision.RESTORE:
                continue
            for logical in node.logical_outputs:
                artifacts[logical] = Artifact(
                    key=logical,
                    size_bytes=1,
                    restore_ms=0.0,
                    recompute_ms=float(node.estimated_cost_ms),
                    resident=False,
                    remote=True,
                )
        self.policy_plane.prepare_prefetch(dag, artifacts)

    def _restore(
        self,
        run_id: str,
        node: DagNode,
        action_key: str | None,
        justification: Sequence[str],
        workspace: Workspace,
        coordinator: RunCoordinator,
        worker: str,
    ) -> NodeReport:
        """Restore outputs from a hit. Justification is required, not optional.

        A restored node still gets a node row, a lease and staged-file records,
        so the run's tree assembly, checkpoints and GC roots see exactly what a
        freshly executed node would have produced.
        """
        if action_key is None:
            raise ContractViolation("restore requires an ActionKey", node_id=node.node_id)
        contract = self.registry.get(node.stage_id)
        with self.tracer.span("elmos.cache.materialize", stage_id=node.stage_id):
            result = self.action_cache.lookup(
                LookupRequest(
                    tenant_id=self.tenant_id,
                    action_key=action_key,
                    trust_namespace=self.trust_namespace,
                    minimum_validation=node.validation_floor,
                    mode=CacheMode.READ_ONLY,
                )
            )
            if not result.hit or result.result is None:
                raise NotFound(
                    "cache entry disappeared between planning and restore",
                    node_id=node.node_id,
                    reasons=[str(reason) for reason in result.reasons],
                )
            outputs = list(result.result.get("output_artifacts", []))
            for digest in outputs:
                self.cas.verify(digest)

        self.store.upsert_node(run_id, node.node_id, node.stage_id, contract.stage_version)
        current = self.store.get_node(run_id, node.node_id, 1)
        if current.status is NodeStatus.PENDING:
            coordinator.mark_ready(run_id, node.node_id, 1)
        _, lease = coordinator.begin(run_id, node.node_id, 1, worker)

        restored_paths: list[str] = []
        for entry in result.result.get("outputs", []):
            record = workspace.restore_from_cache(
                node.node_id,
                1,
                lease.epoch,
                entry["logical_path"],
                entry["artifact_digest"],
                file_class=FileClass(entry.get("file_class", "PUBLISH_CANDIDATE")),
                media_type=entry.get("media_type"),
                artifact_kind=entry.get("artifact_kind", "generated-source"),
                action_key=action_key,
                ownership=Ownership(entry.get("ownership", "GENERATED")),
                mode=int(entry.get("mode", 0o644)),
            )
            restored_paths.append(record.logical_path)
        coordinator.succeed(lease, "RESTORED", action_key)

        entry_record = result.entry
        self.accounting.record_hit(
            node.stage_id,
            source="local",
            saved_cpu_ms=entry_record.saved_cpu_ms if entry_record else 0,
            saved_wall_ms=entry_record.saved_wall_ms if entry_record else 0,
            saved_compiler_ms=entry_record.saved_compiler_ms if entry_record else 0,
            saved_model_tokens=entry_record.saved_model_tokens if entry_record else 0,
        )
        self._node_outputs[node.node_id] = {"artifacts": outputs, "restored": True}
        return NodeReport(
            node_id=node.node_id,
            stage_id=node.stage_id,
            decision="RESTORE",
            justification=tuple(justification) or ("compatible cache entry",),
            action_key=action_key,
            outputs=tuple(outputs),
            metrics={"restored_artifacts": len(outputs), "restored_paths": restored_paths},
        )

    def _execute_node(
        self,
        run_id: str,
        node: DagNode,
        justification: Sequence[str],
        miss_reasons: Sequence[MissReason],
        snapshot: Snapshot,
        implementations: Mapping[str, StageFunction],
        workspace: Workspace,
        coordinator: RunCoordinator,
        checkpoints: CheckpointService,
        worker: str,
    ) -> NodeReport:
        contract = self.registry.get(node.stage_id)
        implementation = implementations.get(node.stage_id)
        if implementation is None:
            raise NotFound("no implementation registered for stage", stage_id=node.stage_id)

        self.store.upsert_node(run_id, node.node_id, node.stage_id, contract.stage_version)
        current = self.store.get_node(run_id, node.node_id, 1)
        if current.status is NodeStatus.PENDING:
            coordinator.mark_ready(run_id, node.node_id, 1)
        _, lease = coordinator.begin(run_id, node.node_id, 1, worker)

        guard = contract.guard()
        fingerprint = self._fingerprints.get(node.node_id)
        staged: list[StagedFileRecord] = []
        checkpoint_id: str | None = None
        try:
            with self.tracer.span("elmos.stage.execute", stage_id=node.stage_id) as span:
                result = implementation(node, self._inputs_for(node))
                span.attributes["outputs"] = len(result.outputs)

            declared = {port.name for port in contract.outputs}
            for output in result.outputs:
                port_name = _port_name_for(output, declared)
                guard.declare_output(port_name)
                with self.tracer.span("elmos.staging.write", stage_id=node.stage_id):
                    record = workspace.reserve(
                        node.node_id,
                        1,
                        output.logical_path,
                        lease.epoch,
                        file_class=output.file_class,
                        ownership=output.ownership,
                        media_type=output.media_type,
                        artifact_kind="generated-source",
                        action_key=fingerprint.action_key if fingerprint else None,
                        lease_id=lease.lease_id,
                        mode=output.mode,
                    )
                with self.tracer.span("elmos.staging.seal", stage_id=node.stage_id):
                    record = workspace.write_and_seal(record, output.payload, lease.epoch)
                with self.tracer.span("elmos.staging.promote", stage_id=node.stage_id):
                    record = workspace.promote(record)
                staged.append(record)
            guard.check_complete()
            workspace.handle_undeclared(node.node_id, 1)

            artifacts = tuple(record.artifact_digest for record in staged if record.artifact_digest)
            placements = tuple(
                {
                    "logical_path": record.logical_path,
                    "artifact_digest": record.artifact_digest,
                    "file_class": str(record.file_class),
                    "media_type": record.media_type,
                    "artifact_kind": record.artifact_kind,
                    "ownership": str(record.ownership),
                    "mode": record.mode,
                    "size": record.actual_size,
                }
                for record in staged
                if record.artifact_digest
            )
            admission = None
            if fingerprint is not None and self.rollout.cache_mode(node.cache_mode).may_write:
                # Admission decides whether this result is worth *recording* as
                # a reusable entry. It cannot affect the outputs: by this point
                # every one of them is sealed, promoted into CAS and in the
                # run's tree. A refusal costs a recomputation, never a file.
                admission = self.policy_plane.admit(
                    action_key=fingerprint.action_key,
                    size_bytes=sum(record.actual_size or 0 for record in staged),
                    stage_class=node.stage_id,
                    recompute_ms=float(result.metrics.wall_ms),
                    restore_ms=self._estimated_restore_ms(artifacts),
                    validation_level=str(result.validation_level),
                    model_tokens=result.metrics.model_tokens,
                    critical_path_weight=1.0 if contract.checkpoint_stage_boundary else 0.0,
                )
            if (
                fingerprint is not None
                and self.rollout.cache_mode(node.cache_mode).may_write
                and (admission is None or admission.admitted)
            ):
                manifest = ActionResultManifest(
                    action_key=fingerprint.action_key,
                    stage_id=node.stage_id,
                    stage_version=contract.stage_version,
                    output_artifacts=artifacts,
                    outputs=placements,
                    required_outputs=artifacts,
                    metrics=result.metrics,
                    determinism=str(contract.determinism),
                )
                self.action_cache.commit(
                    CommitRequest(
                        tenant_id=self.tenant_id,
                        action_key=fingerprint.action_key,
                        manifest=manifest,
                        trust_namespace=self.trust_namespace,
                        validation_level=result.validation_level,
                        producer_identity=self.producer_identity,
                        mode=self.rollout.cache_mode(node.cache_mode),
                    )
                )

            if contract.checkpoint_stage_boundary and fingerprint is not None:
                profile = CompatibilityProfile(
                    stage_id=node.stage_id,
                    stage_version=contract.stage_version,
                    stage_contract_digest=contract.digest(),
                    source_snapshot=snapshot.root_digest,
                    action_key=fingerprint.action_key,
                    pipeline_version=SCHEMA_VERSION,
                )
                with self.tracer.span("elmos.checkpoint.commit", stage_id=node.stage_id):
                    record_checkpoint, _ = checkpoints.commit(
                        lease, profile, completed_partitions=result.completed_partitions
                    )
                checkpoint_id = record_checkpoint.checkpoint_id
                coordinator.checkpointed(lease, checkpoint_id)

            coordinator.succeed(lease, "OK", fingerprint.action_key if fingerprint else None)
            self.accounting.record_miss(
                node.stage_id,
                miss_reasons,
                executed_cpu_ms=result.metrics.cpu_ms,
                executed_wall_ms=result.metrics.wall_ms,
            )
            self._node_outputs[node.node_id] = {
                "artifacts": list(artifacts),
                "restored": False,
                "evidence": list(result.evidence),
            }
            return NodeReport(
                node_id=node.node_id,
                stage_id=node.stage_id,
                decision="EXECUTE",
                justification=tuple(justification) or ("no compatible cache entry",),
                action_key=fingerprint.action_key if fingerprint else None,
                miss_reasons=tuple(str(reason) for reason in miss_reasons),
                outputs=artifacts,
                metrics=result.metrics.to_dict(),
                checkpoint_id=checkpoint_id,
            )
        except ElmosCacheError as exc:
            coordinator.fail(lease, exc.code, retryable=exc.code not in ("CONTRACT_VIOLATION",))
            raise

    def _estimated_restore_ms(self, artifacts: Sequence[str]) -> float:
        """What restoring these artifacts would cost, from the CAS itself.

        Falls back to zero rather than to a guess: a fabricated restore cost
        would flow straight into the admission value function, and a made-up
        number there is worse than an absent one.
        """
        total = 0.0
        for digest in artifacts:
            try:
                total += self.cas.estimate_restore(digest).estimated_restore_ms
            except ElmosCacheError:
                continue
        return total

    def _inputs_for(self, node: DagNode) -> dict[str, Any]:
        return {
            dependency: self._node_outputs.get(dependency, {})
            for dependency in sorted(self._node_outputs)
            if dependency != node.node_id
        }

    # -- publication ------------------------------------------------------
    def assemble_and_publish(
        self,
        run_id: str,
        workspace: Workspace,
        validation_level: ValidationLevel,
        evidence_records: Sequence[dict[str, Any]],
        verifier_identities: Sequence[str],
        publisher: TreePublisher | None = None,
    ) -> tuple[FileTreeManifest, PublishResult | None]:
        """Build the complete tree from sealed files, then flip the pointer."""
        publisher = publisher or TreePublisher(
            workspace.publish_root,
            self.cas,
            self.store,
            self.tenant_id,
            run_id,
            keep_previous=self.config.workspace.keep_previous_published_versions,
            clock=self.clock,
            secret_scanner=self.security.scanner
            if self.config.security.scan_secrets_before_publish
            else None,
        )
        publishable = workspace.publishable()
        tree = publisher.build_tree_manifest(publishable, validation_level=validation_level)

        evidence = EvidenceBundle(
            tree_digest=tree.root_digest,
            validation_level=validation_level,
            records=tuple(evidence_records),
            produced_by=self.producer_identity,
            verifier_identities=tuple(verifier_identities),
        )
        evidence_digest = evidence.store(self.cas)
        tree = replace(tree, evidence_bundle_ref=evidence_digest)

        with self.tracer.span("elmos.publish.tree", stage_id="target-tree-assembly"):
            candidate = publisher.materialize(tree)
            self.security.check_before_publish(candidate.directory)
            if not self.rollout.may_publish:
                return tree, None
            result = publisher.publish(candidate, evidence)
        return tree, result

    # -- shadow comparison ------------------------------------------------
    def shadow_compare(
        self, cached_tree: FileTreeManifest, reference_tree: FileTreeManifest
    ) -> dict[str, Any]:
        """Rollout safety net: cached output must equal a from-scratch build."""
        cached = {entry.logical_path: entry.artifact_digest for entry in cached_tree.entries}
        reference = {entry.logical_path: entry.artifact_digest for entry in reference_tree.entries}
        differing = sorted(path for path in set(cached) | set(reference) if cached.get(path) != reference.get(path))
        return {
            "matched": not differing,
            "cached_tree_digest": cached_tree.root_digest,
            "reference_tree_digest": reference_tree.root_digest,
            "differing_paths": differing[:50],
            "differing_count": len(differing),
        }

    # -- reporting --------------------------------------------------------
    def policy_report(self) -> dict[str, Any] | None:
        """What the policy plane did, plus its advice for the next run.

        ``None`` when nothing is switched on, so a report from a deployment
        that has not opted in is byte-identical to what it was before the
        policy plane existed.
        """
        if not self.policy_plane.active:
            return None
        payload = self.policy_plane.report()
        payload["recommendation"] = self.policy_plane.recommend()
        return payload

    def report(
        self,
        run_id: str,
        snapshot: Snapshot,
        plan: ExecutionPlan,
        nodes: Sequence[NodeReport],
        tree: FileTreeManifest | None,
        published: bool,
        shadow: dict[str, Any] | None = None,
        failures: Sequence[dict[str, Any]] = (),
    ) -> RunReport:
        report = RunReport(
            run_id=run_id,
            snapshot_digest=snapshot.root_digest,
            plan_digest=plan.plan_digest,
            tree_digest=tree.root_digest if tree else None,
            published=published,
            nodes=tuple(nodes),
            telemetry=summarize_run(self.accounting, self.tracer, PerformanceGate()),
            rollout_phase=self.config.rollout.phase,
            shadow=shadow,
            failures=tuple(failures),
            policy=self.policy_report(),
            parity=self.parity_runtime.report(),
        )
        unjustified = report.unjustified_skips()
        if unjustified:
            raise ContractViolation(
                "nodes were skipped without a cache justification", nodes=unjustified
            )
        if tree is not None:
            sealed = {record.logical_path for record in self.store.list_staged_files(run_id)}
            unreachable = sorted(set(tree.paths()) - sealed)
            if unreachable:
                raise ContractViolation(
                    "published tree contains files with no sealed staged record", paths=unreachable[:20]
                )
        return report


def _port_name_for(output: StageOutput, declared: Iterable[str]) -> str:
    """Map an output file to the contract port it satisfies."""
    names = list(declared)
    for name in names:
        if name in output.logical_path:
            return name
    if len(names) == 1:
        return names[0]
    if output.file_class is FileClass.PUBLISH_CANDIDATE and "generated_tree" in names:
        return "generated_tree"
    if output.source_map is not None and "source_maps" in names:
        return "source_maps"
    return names[0] if names else output.logical_path


def build_run(
    store: MetadataStore,
    cas: ContentAddressableStore,
    config: CacheConfig,
    base_path: Path,
    tenant_id: str,
    project_id: str,
    run_id: str,
    snapshot: Snapshot,
    clock: Clock = SYSTEM_CLOCK,
) -> tuple[Workspace, RunCoordinator, CheckpointService]:
    """Allocate the workspace, journal, leases and checkpoint service for a run."""
    store.ensure_project(tenant_id, project_id)
    snapshot_manifest = cas.put_document(snapshot.to_manifest(), artifact_kind="snapshot-manifest")
    snapshot_id = store.record_snapshot(
        tenant_id, project_id, snapshot.root_digest, snapshot_manifest, snapshot.policy_version
    )
    try:
        store.get_run(run_id)
    except NotFound:
        store.create_run(run_id, tenant_id, project_id, snapshot_id, SCHEMA_VERSION)

    workspace = Workspace(
        base_path / config.workspace.root,
        tenant_id,
        project_id,
        run_id,
        store,
        cas,
        config=config.workspace,
        clock=clock,
    )
    journal = RunJournal(workspace.root / "control" / "journal.ndjson", run_id, clock)
    leases = LeaseManager(store, clock)
    coordinator = RunCoordinator(store, journal, leases, clock=clock)
    checkpoints = CheckpointService(store, cas, workspace, journal, clock)
    return workspace, coordinator, checkpoints
