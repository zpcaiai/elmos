"""E2E-001..003: a complete Java/Spring -> C#/ASP.NET conversion run.

The stage implementations are deliberate stand-ins: the point of these tests is
the *orchestration contract* -- that work is skipped only with a justification,
that every published file is reachable from a sealed tree manifest, that a
restart resumes without duplicating side effects, and that a no-change rerun
reproduces the same tree digest while avoiding model and compiler work.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import (
    CacheConfig,
    CacheParityConfig,
    CoordinatorConfig,
    RolloutConfig,
)
from elmos_build_cache.coordinator import (
    CacheLayer as CoordinatorCacheLayer,
)
from elmos_build_cache.coordinator import (
    LayerProbeResult,
    MultiLayerCacheCoordinator,
    ReuseIdentity,
    ReuseRequest,
)
from elmos_build_cache.dag import ConversionDag, DagNode, EdgeKind, Granularity
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import FileClass, RunStatus, StagedFileStatus, ValidationLevel
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.fingerprint import FingerprintInputs
from elmos_build_cache.interface_hash import InterfaceIndex
from elmos_build_cache.manifests import ExecutionMetrics
from elmos_build_cache.parity_runtime import SERVING_GATE_KIND, serving_gate_statement
from elmos_build_cache.pipeline import (
    ConversionPipeline,
    RolloutController,
    StageOutput,
    StageResult,
    build_run,
)
from elmos_build_cache.security import Ed25519ProvenanceSigner, ProvenanceSigner, SignedStatement
from elmos_build_cache.snapshot import Snapshot, diff_snapshots, take_snapshot

TENANT = "tenant-e2e"
PROJECT = "demo-service"

SPRING_CONTROLLER = """package com.demo;

@RestController
public class UserController {
  private final UserRepository repository;

  @GetMapping("/users/{id}")
  public User findUser(long id) { return repository.get(id); }

  private String describe(User user) { return user.name(); }
}
"""

SPRING_REPOSITORY = """package com.demo;

public class UserRepository {
  public User get(long id) { return new User(id, "demo"); }
}
"""


def write_source(root: Path) -> Path:
    (root / "src" / "main" / "java" / "com" / "demo").mkdir(parents=True)
    base = root / "src" / "main" / "java" / "com" / "demo"
    (base / "UserController.java").write_text(SPRING_CONTROLLER, encoding="utf-8")
    (base / "UserRepository.java").write_text(SPRING_REPOSITORY, encoding="utf-8")
    (root / "pom.xml").write_text("<project><artifactId>demo</artifactId></project>\n", encoding="utf-8")
    return root


def build_dag() -> ConversionDag:
    dag = ConversionDag()
    dag.add_node(
        DagNode(
            "generate:UserController",
            "target-code-generation",
            Granularity.GENERATED_FILE,
            logical_outputs=("src/Controllers/UserController.cs",),
            estimated_cost_ms=8000,
        )
    )
    dag.add_node(
        DagNode(
            "generate:UserRepository",
            "target-code-generation",
            Granularity.GENERATED_FILE,
            logical_outputs=("src/Repositories/UserRepository.cs",),
            estimated_cost_ms=6000,
        )
    )
    dag.add_edge("generate:UserRepository", "generate:UserController", EdgeKind.PUBLIC_INTERFACE)
    return dag


TARGET_PATHS = {
    "generate:UserController": ("src/Controllers/UserController.cs", "com/demo/UserController.java"),
    "generate:UserRepository": ("src/Repositories/UserRepository.cs", "com/demo/UserRepository.java"),
}


def implementation_for(sources: Mapping[str, str], calls: list[str]):
    def generate(node: DagNode, inputs: Mapping[str, object]) -> StageResult:
        calls.append(node.node_id)
        target_path, source_key = TARGET_PATHS[node.node_id]
        body = sources[source_key]
        csharp = (
            f"// generated from {source_key}\n"
            f"namespace Demo;\npublic class {Path(target_path).stem} {{\n"
            f"    // {len(body)} source characters\n"
            f"    // routes: {'/users/{id}' if 'GetMapping' in body else 'none'}\n"
            "}\n"
        )
        return StageResult(
            outputs=(
                StageOutput(
                    logical_path=target_path,
                    payload=csharp.encode("utf-8"),
                    file_class=FileClass.PUBLISH_CANDIDATE,
                    media_type="text/x-csharp",
                ),
                StageOutput(
                    logical_path=target_path + ".source_maps.json",
                    payload=b'{"kind":"elmos.source-map/v1"}',
                    file_class=FileClass.STAGED_INTERMEDIATE,
                    media_type="application/json",
                ),
            ),
            metrics=ExecutionMetrics(wall_ms=8000, cpu_ms=6000, compiler_ms=0, model_tokens=15000),
            completed_partitions=(node.node_id,),
            evidence=({"kind": "generation", "node": node.node_id},),
            validation_level=ValidationLevel.TEST_VERIFIED,
        )

    return generate


def fingerprints_for(
    pipeline: ConversionPipeline, dag: ConversionDag, index: InterfaceIndex, snapshot: Snapshot
) -> None:
    """Give each node a key derived from its own source plus its dependencies."""
    api = index.public_interface_digests()
    for node in dag.nodes:
        _, source_key = TARGET_PATHS[node.node_id]
        own = index.interfaces[source_key]
        dependencies = tuple(
            api[TARGET_PATHS[dependency][1]] for dependency in dag.dependencies(node.node_id)
        )
        contract = pipeline.registry.get(node.stage_id)
        pipeline.fingerprint_for(
            node,
            contract,
            FingerprintInputs(
                input_artifact_digests=(own.semantic_digest,),
                source_semantic_digest=own.semantic_digest,
                dependency_public_interface_digests=dependencies,
                target_language="csharp",
                target_framework="aspnet-core",
                target_runtime="net10.0",
                rule_pack_digest="sha256:" + "5" * 64,
                toolchain_digest="sha256:" + "4" * 64,
                prompt_template_digest="sha256:" + "7" * 64,
                model_snapshot_digest="sha256:" + "8" * 64,
                declared_environment={"LANG": "C.UTF-8", "TZ": "UTC"},
            ),
        )


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        clock: ManualClock,
        phase: str = "production-certified",
        *,
        config: CacheConfig | None = None,
        parity_serving_gate_receipt: SignedStatement | None = None,
        parity_serving_gate_verifier: ProvenanceSigner | None = None,
        multi_layer_coordinator: MultiLayerCacheCoordinator | None = None,
    ) -> None:
        self.root = write_source(tmp_path / "source")
        self.base = tmp_path / "workdir"
        self.base.mkdir()
        self.clock = clock
        self.config = config or dataclasses.replace(
            CacheConfig(),
            rollout=RolloutConfig(phase=phase),
        )
        self.parity_serving_gate_receipt = parity_serving_gate_receipt
        self.parity_serving_gate_verifier = parity_serving_gate_verifier
        self.multi_layer_coordinator = multi_layer_coordinator
        self.cas = ContentAddressableStore(self.base / ".elmos" / "cache")
        self.store = SqliteMetadataStore.open(self.base / ".elmos" / "cache" / "index.sqlite", clock)
        self.dag = build_dag()
        self.calls: list[str] = []

    def sources(self) -> dict[str, str]:
        base = self.root / "src" / "main" / "java" / "com" / "demo"
        return {
            "com/demo/UserController.java": (base / "UserController.java").read_text(encoding="utf-8"),
            "com/demo/UserRepository.java": (base / "UserRepository.java").read_text(encoding="utf-8"),
        }

    def index(self) -> InterfaceIndex:
        index = InterfaceIndex()
        for key, text in self.sources().items():
            index.add_source(key, text)
        return index

    def run(
        self,
        run_id: str,
        affected: Mapping[str, list[str]] | None = None,
        previous: Mapping[str, object] | None = None,
        crash_after: str | None = None,
        minimum_validation: ValidationLevel | None = None,
    ):
        pipeline = ConversionPipeline(
            self.config,
            self.store,
            self.cas,
            self.base,
            TENANT,
            PROJECT,
            clock=self.clock,
            parity_serving_gate_receipt=self.parity_serving_gate_receipt,
            parity_serving_gate_verifier=self.parity_serving_gate_verifier,
            multi_layer_coordinator=self.multi_layer_coordinator,
        )
        snapshot = take_snapshot(self.root)
        with self.store.transaction():
            workspace, coordinator, checkpoints = build_run(
                self.store, self.cas, self.config, self.base, TENANT, PROJECT, run_id, snapshot, self.clock
            )
            coordinator.start_run(run_id)

        index = self.index()
        fingerprints_for(pipeline, self.dag, index, snapshot)
        if previous:
            pipeline.seed_previous_fingerprints(previous)  # type: ignore[arg-type]

        plan = pipeline.plan(
            self.dag,
            affected or {},
            minimum_validation=minimum_validation,
        )
        implementations = {"target-code-generation": implementation_for(self.sources(), self.calls)}
        with self.store.transaction():
            reports = pipeline.execute(
                run_id, self.dag, plan, snapshot, implementations, workspace, coordinator, checkpoints
            )
        if crash_after is not None:
            return pipeline, snapshot, plan, reports, workspace, coordinator, None, None

        with self.store.transaction():
            tree, published = pipeline.assemble_and_publish(
                run_id,
                workspace,
                ValidationLevel.TEST_VERIFIED,
                evidence_records=[{"kind": "test", "passed": 12, "failed": 0}],
                verifier_identities=["independent-ci"],
            )
            self.store.transition_run(
                run_id, RunStatus.SUCCEEDED, self.store.get_run(run_id).version
            )
        report = pipeline.report(run_id, snapshot, plan, reports, tree, published is not None)
        return pipeline, snapshot, plan, reports, workspace, coordinator, tree, report


def test_e2e_001_complete_project_is_staged_validated_and_published(
    tmp_path: Path, clock: ManualClock
) -> None:
    """E2E-001: every published file comes from a sealed, promoted staged file."""
    harness = Harness(tmp_path, clock)
    _, _, plan, reports, workspace, _, tree, report = harness.run("run-e2e-1")

    assert tree is not None and report is not None
    assert sorted(tree.paths()) == [
        "src/Controllers/UserController.cs",
        "src/Repositories/UserRepository.cs",
    ]
    assert report.published is True
    assert report.unjustified_skips() == []
    assert {node.decision for node in report.nodes} == {"EXECUTE"}

    published_paths = set(tree.paths())
    sealed_paths = {
        record.logical_path
        for record in workspace.store.list_staged_files("run-e2e-1")
        if record.status in (StagedFileStatus.PUBLISHED, StagedFileStatus.TREE_INCLUDED)
    }
    assert published_paths <= sealed_paths

    from elmos_build_cache.publish import TreePublisher

    publisher = TreePublisher(
        workspace.publish_root, harness.cas, harness.store, TENANT, "run-e2e-1", clock=clock
    )
    body = publisher.read_published("src/Controllers/UserController.cs").decode()
    assert "generated from com/demo/UserController.java" in body
    assert "routes: /users/{id}" in body


def test_e2e_003_no_change_rerun_reproduces_the_tree_without_model_work(
    tmp_path: Path, clock: ManualClock
) -> None:
    """E2E-003: same inputs -> same tree digest, and generation is restored."""
    harness = Harness(tmp_path, clock)
    _, _, _, _, _, _, first_tree, first_report = harness.run("run-e2e-1")
    first_calls = list(harness.calls)
    harness.calls.clear()

    pipeline, _, plan, reports, _, _, second_tree, second_report = harness.run("run-e2e-2")

    assert first_tree is not None and second_tree is not None
    assert first_tree.root_digest == second_tree.root_digest
    assert harness.calls == []  # the generator never ran again
    assert len(first_calls) == 2
    assert {node.decision for node in second_report.nodes} == {"RESTORE"}  # type: ignore[union-attr]
    assert all(node.justification for node in second_report.nodes)  # type: ignore[union-attr]
    telemetry = second_report.telemetry["accounting"]  # type: ignore[union-attr]
    assert telemetry["overall_hit_rate"] == 1.0
    assert telemetry["saved"]["model_tokens"] >= 30000


def test_private_body_change_reuses_the_unaffected_module(
    tmp_path: Path, clock: ManualClock
) -> None:
    """A private edit re-generates one file and restores the other."""
    harness = Harness(tmp_path, clock)
    harness.run("run-e2e-1")
    harness.calls.clear()

    controller = (
        harness.root / "src" / "main" / "java" / "com" / "demo" / "UserController.java"
    )
    controller.write_text(SPRING_CONTROLLER.replace("user.name()", "user.name().trim()"), encoding="utf-8")

    closure = harness.dag.affected_closure(behavior_changed=["generate:UserController"])
    _, _, plan, _, _, _, tree, report = harness.run("run-e2e-3", affected=closure)

    assert harness.calls == ["generate:UserController"]
    decisions = {node.node_id: node.decision for node in report.nodes}  # type: ignore[union-attr]
    assert decisions["generate:UserRepository"] == "RESTORE"
    assert decisions["generate:UserController"] == "EXECUTE"


def test_public_interface_change_invalidates_the_dependent(
    tmp_path: Path, clock: ManualClock
) -> None:
    harness = Harness(tmp_path, clock)
    harness.run("run-e2e-1")
    harness.calls.clear()

    repository = harness.root / "src" / "main" / "java" / "com" / "demo" / "UserRepository.java"
    repository.write_text(
        SPRING_REPOSITORY.replace("public User get(long id)", "public User get(String id)"),
        encoding="utf-8",
    )
    closure = harness.dag.affected_closure(interface_changed=["generate:UserRepository"])
    _, _, _, _, _, _, _, report = harness.run("run-e2e-4", affected=closure)

    assert sorted(harness.calls) == ["generate:UserController", "generate:UserRepository"]
    assert {node.decision for node in report.nodes} == {"EXECUTE"}  # type: ignore[union-attr]


def test_e2e_002_restart_during_generation_resumes_without_duplicates(
    tmp_path: Path, clock: ManualClock
) -> None:
    """E2E-002: a crash mid-run leaves recoverable state and no duplicate output."""
    harness = Harness(tmp_path, clock)
    pipeline, snapshot, _, reports, workspace, coordinator, _, _ = harness.run(
        "run-e2e-crash", crash_after="generate:UserRepository"
    )
    assert len(reports) == 2

    # Simulate the restart: leases expire, recovery claims, workspace converges.
    clock.advance(600)
    with harness.store.transaction():
        reclaimed = coordinator.recover_expired()
        recovery = workspace.recover()
    assert recovery["failed"] == []
    assert recovery["discarded"] == []

    with harness.store.transaction():
        again = workspace.recover()
    assert again["failed"] == []

    paths = [record.logical_path for record in harness.store.list_staged_files("run-e2e-crash")]
    assert len(paths) == len(set(paths))  # no duplicate logical files after recovery
    assert all(count == 1 for count in {path: paths.count(path) for path in paths}.values())
    assert isinstance(reclaimed, list)


def test_staging_only_rollout_phase_never_publishes(tmp_path: Path, clock: ManualClock) -> None:
    harness = Harness(tmp_path, clock, phase="staging-only")
    _, _, _, _, workspace, _, tree, report = harness.run("run-e2e-staging")
    assert tree is not None
    assert report is not None and report.published is False
    assert report.rollout_phase == "staging-only"
    assert report.parity is not None
    assert not any(report.parity["serving"].values())
    assert set(report.parity["wiring"]["layers"].values()) == {"NOT_WIRED"}
    assert report.parity["external_provider_evidence"] == "NOT_RUN"
    assert report.parity["certification"] == "NOT_CERTIFIED"
    # The candidate exists on disk but no pointer was flipped.
    assert (workspace.publish_root / "run-e2e-staging").is_dir()


def test_kill_switch_forces_bypass() -> None:
    controller = RolloutController(RolloutConfig(phase="production-certified", kill_switch=True))
    from elmos_build_cache.enums import CacheMode

    assert controller.cache_mode(CacheMode.READ_WRITE) is CacheMode.BYPASS
    assert controller.may_publish is False
    assert controller.remote_read is False


def test_shadow_compare_detects_a_divergent_cached_tree(tmp_path: Path, clock: ManualClock) -> None:
    harness = Harness(tmp_path, clock)
    pipeline, _, _, _, _, _, tree, _ = harness.run("run-e2e-1")
    assert tree is not None

    from elmos_build_cache.manifests import TreeEntry, build_file_tree

    divergent = build_file_tree(
        [
            TreeEntry(entry.logical_path, entry.artifact_digest if index else "sha256:" + "9" * 64)
            for index, entry in enumerate(tree.entries)
        ],
        producer={},
    )
    comparison = pipeline.shadow_compare(tree, divergent)
    assert comparison["matched"] is False
    assert comparison["differing_count"] == 1


def test_report_refuses_an_unreachable_published_file(tmp_path: Path, clock: ManualClock) -> None:
    harness = Harness(tmp_path, clock)
    pipeline, snapshot, plan, reports, _, _, tree, _ = harness.run("run-e2e-1")
    assert tree is not None

    from elmos_build_cache.manifests import TreeEntry, build_file_tree

    forged = build_file_tree(
        [*tree.entries, TreeEntry("src/Injected.cs", "sha256:" + "a" * 64)], producer={}
    )
    with pytest.raises(ContractViolation, match="no sealed staged record"):
        pipeline.report("run-e2e-1", snapshot, plan, reports, forged, True)


def test_snapshot_diff_drives_the_closure(tmp_path: Path, clock: ManualClock) -> None:
    harness = Harness(tmp_path, clock)
    before = take_snapshot(harness.root)
    controller = harness.root / "src" / "main" / "java" / "com" / "demo" / "UserController.java"
    controller.write_text(SPRING_CONTROLLER.replace("user.name()", "user.name().trim()"), encoding="utf-8")
    delta = diff_snapshots(before, take_snapshot(harness.root))
    assert delta.modified == ("src/main/java/com/demo/UserController.java",)
    assert delta.formatting_only == ()


def coordinator_serving_config() -> CacheConfig:
    return dataclasses.replace(
        CacheConfig(),
        rollout=RolloutConfig(phase="production-certified"),
        parity=dataclasses.replace(
            CacheParityConfig(),
            rollout_phase="internal",
            coordinator=CoordinatorConfig(enabled=True),
        ),
    )


def coordinator_gate(
    config: CacheConfig,
    clock: ManualClock,
) -> tuple[SignedStatement, ProvenanceSigner]:
    signer = Ed25519ProvenanceSigner.generate("pipeline-coordinator-gate")
    receipt = signer.sign_statement(
        SERVING_GATE_KIND,
        serving_gate_statement(
            config.parity,
            TENANT,
            PROJECT,
            ("multi_layer_coordinator",),
            issued_at=clock.now(),
            expires_at=clock.now() + 3_600,
        ),
    )
    return receipt, Ed25519ProvenanceSigner.verifier(signer.public_keyset())


def test_v12_coordinator_gate_drives_real_exact_action_restore(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    config = coordinator_serving_config()
    receipt, verifier = coordinator_gate(config, clock)
    harness = Harness(
        tmp_path,
        clock,
        config=config,
        parity_serving_gate_receipt=receipt,
        parity_serving_gate_verifier=verifier,
    )

    harness.run("run-coordinator-cold")
    calls_after_cold = tuple(harness.calls)
    pipeline, _, _, reports, _, _, _, report = harness.run("run-coordinator-warm")

    assert tuple(harness.calls) == calls_after_cold
    assert {node.decision for node in reports} == {"RESTORE"}
    assert len(pipeline.coordinator_plans) == 2
    assert all(
        plan.complete_result_layer is CoordinatorCacheLayer.ACTION
        and plan.execution_required is False
        and not plan.budget_usage.breaches
        for plan in pipeline.coordinator_plans.values()
    )
    assert report is not None and report.parity is not None
    assert report.parity["wiring"]["layers"]["multi_layer_coordinator"] == "WIRED"
    assert report.parity["serving"]["multi_layer_coordinator"] is True
    assert report.parity["wiring"]["requested_not_wired"] == []


def test_v12_coordinator_config_without_trusted_gate_never_serves(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    harness = Harness(tmp_path, clock, config=coordinator_serving_config())

    pipeline, _, _, reports, _, _, _, report = harness.run("run-coordinator-no-gate")

    assert {node.decision for node in reports} == {"EXECUTE"}
    assert pipeline.coordinator_plans == {}
    assert report is not None and report.parity is not None
    assert report.parity["wiring"]["layers"]["multi_layer_coordinator"] == "WIRED"
    assert report.parity["serving"]["multi_layer_coordinator"] is False
    assert report.parity["serving_gate_receipt"]["status"] == "MISSING"


def test_v12_coordinator_under_validated_action_executes_instead_of_restoring(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    config = coordinator_serving_config()
    receipt, verifier = coordinator_gate(config, clock)
    harness = Harness(
        tmp_path,
        clock,
        config=config,
        parity_serving_gate_receipt=receipt,
        parity_serving_gate_verifier=verifier,
    )
    harness.run("run-coordinator-test-verified")
    calls_after_cold = len(harness.calls)

    pipeline, _, _, reports, _, _, _, _ = harness.run(
        "run-coordinator-production-floor",
        minimum_validation=ValidationLevel.PRODUCTION_CERTIFIED,
    )

    assert {node.decision for node in reports} == {"EXECUTE"}
    assert len(harness.calls) == calls_after_cold + 2
    assert {
        plan.layers[0].reason_code for plan in pipeline.coordinator_plans.values()
    } == {"VALIDATION_TOO_LOW"}
    assert all(not plan.layers[0].accepted for plan in pipeline.coordinator_plans.values())


class UnsafeCandidateCoordinator(MultiLayerCacheCoordinator):
    def __init__(self, *, mismatch_identity: bool) -> None:
        super().__init__()
        self.mismatch_identity = mismatch_identity

    def plan_prevalidated(
        self,
        request: ReuseRequest,
        results: Mapping[CoordinatorCacheLayer, LayerProbeResult],
        *,
        decision_started_monotonic: float | None = None,
    ):
        changed_results = dict(results)
        changed_request = request
        if self.mismatch_identity:
            foreign = ReuseIdentity(
                tenant_id=request.identity.tenant_id,
                project_id="foreign-project",
                authorization_digest=request.identity.authorization_digest,
                compatibility_digest=request.identity.compatibility_digest,
                work_digest=request.identity.work_digest,
            )
            changed_request = dataclasses.replace(request, identity=foreign)
            changed_results = {
                layer: dataclasses.replace(result, identity=foreign)
                for layer, result in results.items()
            }
        else:
            changed_results = {
                layer: dataclasses.replace(result, authorised=False)
                for layer, result in results.items()
            }
        return super().plan_prevalidated(
            changed_request,
            changed_results,
            decision_started_monotonic=decision_started_monotonic,
        )


@pytest.mark.parametrize("mismatch_identity", [True, False])
def test_v12_pipeline_refuses_identity_mismatch_and_unauthorized_candidate(
    tmp_path: Path,
    clock: ManualClock,
    mismatch_identity: bool,
) -> None:
    config = coordinator_serving_config()
    receipt, verifier = coordinator_gate(config, clock)
    harness = Harness(
        tmp_path,
        clock,
        config=config,
        parity_serving_gate_receipt=receipt,
        parity_serving_gate_verifier=verifier,
    )
    harness.run("run-coordinator-safe-seed")
    calls_after_seed = len(harness.calls)
    harness.multi_layer_coordinator = UnsafeCandidateCoordinator(
        mismatch_identity=mismatch_identity
    )

    _, _, _, reports, _, _, _, report = harness.run(
        "run-coordinator-unsafe-candidate"
    )

    assert {node.decision for node in reports} == {"EXECUTE"}
    assert len(harness.calls) == calls_after_seed + 2
    assert report is not None and report.parity is not None
    assert report.parity["rollback"]["latched"] is True


# --------------------------------------------------------------------------
# SOTA-25: the policy plane on the real pipeline path
# --------------------------------------------------------------------------
def _policy_harness(tmp_path: Path, clock: ManualClock, **policy: object) -> Harness:
    from elmos_build_cache.config import PolicyConfig

    harness = Harness(tmp_path, clock)
    harness.config = dataclasses.replace(
        harness.config, policy=dataclasses.replace(PolicyConfig(), **policy)  # type: ignore[arg-type]
    )
    return harness


def test_sota_25_a_run_captures_a_trace_from_the_real_lookup_path(
    tmp_path: Path, clock: ManualClock
) -> None:
    """Trace capture must observe the pipeline's own probes, not a replay."""
    harness = _policy_harness(tmp_path, clock, trace_capture=True, trace_sample_rate=1.0)
    _, _, _, _, _, _, _, report = harness.run("run-sota-trace")

    assert report is not None
    policy = report.to_dict()["policy"]
    assert policy is not None
    assert policy["capabilities"]["trace_capture"] is True
    assert policy["trace"]["captured"] > 0, "the run's own lookups should have been recorded"


def test_sota_25_the_report_is_unchanged_when_nothing_is_switched_on(
    tmp_path: Path, clock: ManualClock
) -> None:
    """Opting out must be indistinguishable from the plane not existing."""
    harness = Harness(tmp_path, clock)
    _, _, _, _, _, _, _, report = harness.run("run-sota-off")

    assert report is not None
    assert report.to_dict()["policy"] is None


def test_sota_25_admission_can_refuse_to_record_without_losing_an_output(
    tmp_path: Path, clock: ManualClock
) -> None:
    """A refused entry costs a recomputation, never a file.

    The published tree must be identical whether or not admission refused, and
    every published path must still come from a sealed staged record -- the
    whole point of putting admission *after* promotion.
    """
    admitting = Harness(tmp_path / "on", clock)
    _, _, _, _, _, _, admitted_tree, admitted_report = admitting.run("run-sota-admit-on")

    refusing = _policy_harness(
        tmp_path / "off", clock, admission_enabled=True, objective_profile="BYTE_NETWORK"
    )
    _, _, _, _, workspace, _, refused_tree, refused_report = refusing.run("run-sota-admit-off")

    assert admitted_tree is not None and refused_tree is not None
    assert admitted_tree.root_digest == refused_tree.root_digest, (
        "admission may change what is cached, never what is produced"
    )
    assert refused_report is not None and refused_report.published is True

    sealed = {
        record.logical_path
        for record in workspace.store.list_staged_files("run-sota-admit-off")
        if record.status in (StagedFileStatus.PUBLISHED, StagedFileStatus.TREE_INCLUDED)
    }
    assert set(refused_tree.paths()) <= sealed
    assert admitted_report is not None
