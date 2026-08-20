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

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .action_cache import ActionCache, CommitRequest, HotIndex, LookupRequest
from .cas import ContentAddressableStore
from .checkpoint import CheckpointService, CompatibilityProfile
from .clock import SYSTEM_CLOCK, Clock
from .config import CacheConfig, RolloutConfig
from .dag import CacheProbe, ConversionDag, DagNode, ExecutionPlan, NodeDecision, ProbeResult
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
from .errors import ContractViolation, ElmosCacheError, NotFound
from .fingerprint import Fingerprint, FingerprintInputs, build_action_key, explain_miss
from .journal import LeaseManager, RunCoordinator, RunJournal
from .manifests import ActionResultManifest, EvidenceBundle, ExecutionMetrics, FileTreeManifest
from .observability import CacheAccounting, MetricsRegistry, PerformanceGate, Tracer, summarize_run
from .publish import PublishResult, TreePublisher
from .security import SecurityGate
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
            with self.tracer.span("elmos.cache.lookup", stage_id=node.stage_id):
                result = self.action_cache.lookup(
                    LookupRequest(
                        tenant_id=self.tenant_id,
                        action_key=fingerprint.action_key,
                        trust_namespace=self.trust_namespace,
                        minimum_validation=max(minimum, node.validation_floor, key=lambda v: v.rank),
                        mode=mode,
                    )
                )
            if result.hit:
                return ProbeResult(True, fingerprint.action_key, ())
            reasons = result.reasons
            previous = self._previous_fingerprints.get(node.node_id)
            if previous is not None:
                reasons = tuple(explain_miss(fingerprint, previous, result.reasons).reasons)
            return ProbeResult(False, fingerprint.action_key, reasons)

        return dag.plan(affected, CacheProbe(probe))

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
        for wave in plan.waves:
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
            if fingerprint is not None and self.rollout.cache_mode(node.cache_mode).may_write:
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
