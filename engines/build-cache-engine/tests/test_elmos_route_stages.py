"""The cache, driven by ELMOS's own conversion engine.

`test_e2e_real_stages.py` proves the orchestration survives contact with *a*
real stage. This file goes one step further and uses **the conversion engine
ELMOS ships**: `engines/polyglot-route-engine`, whose analyzer lifts a real
semantic IR out of the source and whose emitter produces overflow-checked
target code. Nothing here is written for the test -- the IR, the identifier
plan and the emitted file all come out of that engine.

Two properties are what the bridge exists to establish:

1. **Generation is keyed by the IR, not by the file.** A comment-only edit to
   the Python source produces a byte-identical IR, so the emitter never runs
   again. That is the payoff of bridging at the IR boundary rather than at the
   file boundary, and it is asserted below on real analyzer output.
2. **A toolchain identity is never invented.** The route engine pins its
   toolchains to an exact platform-specific tree. On a host that does not match
   the pin, the bridge refuses rather than substituting a plausible digest --
   because a forged toolchain digest is how two different compilers come to
   share one cache entry.

The suite skips (loudly) when the route engine is not importable, which is the
case for anyone who has this package without the rest of the ELMOS repository.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import CacheConfig, RolloutConfig
from elmos_build_cache.dag import ConversionDag, DagNode, EdgeKind, Granularity
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.elmos_route_stages import (
    RouteEngineUnavailable,
    RouteStages,
    RouteUnit,
    available,
    rule_pack_digest,
)
from elmos_build_cache.enums import RunStatus, ValidationLevel
from elmos_build_cache.pipeline import ConversionPipeline, build_run
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.snapshot import take_snapshot

pytestmark = pytest.mark.skipif(
    not available(),
    reason="the ELMOS polyglot route engine is not importable (set ELMOS_POLYGLOT_ROUTE_SRC)",
)

TENANT = "tenant-route"
PROJECT = "polyglot-demo"

TAX = '''def total_price(amount: int, quantity: int) -> int:
    if quantity > 0:
        return amount * quantity
    return 0
'''

DISCOUNT = '''def discounted(amount: int, percent: int) -> int:
    if percent > 0:
        return amount - percent
    return amount
'''

SOURCES = {"billing/tax.py": TAX, "billing/discount.py": DISCOUNT}

UNITS = (
    RouteUnit("billing/tax.py", "total_price", "python", "java"),
    RouteUnit("billing/discount.py", "discounted", "python", "java"),
)


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    for logical, text in SOURCES.items():
        path = root / logical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def stages(source_root: Path) -> RouteStages:
    # This host is not the route engine's pinned Darwin/arm64 toolchain host,
    # so the unpinned identity is used -- and is *marked* unpinned in the key.
    return RouteStages(source_root, strict_toolchain=False)


# ==========================================================================
# the engine itself
# ==========================================================================
def test_the_real_analyzer_produces_a_semantic_ir(stages: RouteStages) -> None:
    ir = stages.analyze(UNITS[0])
    assert ir.source_language == "python"
    assert [function.name for function in ir.functions] == ["total_price"]
    assert ir.analyzer.startswith("CPython ast"), ir.analyzer
    mapping = ir.to_mapping()
    assert mapping["schema_version"] == "1.0.0"
    assert mapping["functions"][0]["parameters"][0]["type"] == "integer"


def test_the_real_emitter_produces_overflow_checked_java(stages: RouteStages) -> None:
    ir = stages.analyze(UNITS[0])
    emitted = stages.emit(ir, "java")
    assert emitted.relative_path.endswith(".java")
    # The route engine refuses silent integer overflow; this is its output, not
    # a template we wrote.
    assert "Math.multiplyExact" in emitted.content
    assert "public static long" in emitted.content


@pytest.mark.parametrize("target", ["java", "typescript", "go"])
def test_the_emitter_serves_every_bridged_target(stages: RouteStages, target: str) -> None:
    emitted = stages.emit(stages.analyze(UNITS[0]), target)
    assert emitted.content.strip()
    assert emitted.relative_path


def test_the_emitted_java_compiles_with_a_real_compiler(
    stages: RouteStages, tmp_path: Path
) -> None:
    if shutil.which("javac") is None:
        pytest.skip("javac is not available in this environment")
    emitted = stages.emit(stages.analyze(UNITS[0]), "java")
    path = tmp_path / emitted.relative_path
    path.write_text(emitted.content, encoding="utf-8")
    ok, log = stages.compile_target("java", path, tmp_path / "classes")
    assert ok, log
    assert list((tmp_path / "classes").glob("*.class"))


def test_the_emitted_go_compiles_with_a_real_compiler(
    stages: RouteStages, tmp_path: Path
) -> None:
    if shutil.which("go") is None:
        pytest.skip("go is not available in this environment")
    emitted = stages.emit(stages.analyze(UNITS[0]), "go")
    path = tmp_path / emitted.relative_path
    path.write_text(emitted.content, encoding="utf-8")
    ok, log = stages.compile_target("go", path, tmp_path / "gobuild")
    assert ok, log


# ==========================================================================
# identity: nothing is invented
# ==========================================================================
def test_strict_mode_refuses_an_unpinned_toolchain(source_root: Path) -> None:
    """On a host the route engine does not pin, the bridge stops.

    This is the honest half of the integration: the pinned toolchain tree is
    Darwin/arm64 and this suite usually runs on Linux. Rather than substituting
    a plausible digest, the bridge propagates the engine's own refusal.
    """
    strict = RouteStages(source_root, strict_toolchain=True)
    try:
        identity = strict.toolchain_identity("python")
    except RouteEngineUnavailable as error:
        assert "toolchain" in str(error).lower()
        return
    # On the pinned host the identity must be real, and must say so.
    assert identity.pinned is True
    assert identity.detail["version"]


def test_an_unpinned_identity_cannot_collide_with_a_pinned_one(
    stages: RouteStages, monkeypatch: pytest.MonkeyPatch
) -> None:
    from elmos_polyglot_route.models import RouteError

    monkeypatch.setattr(
        "elmos_polyglot_route.toolchains.exact_toolchain",
        lambda _language: (_ for _ in ()).throw(RouteError("HOST_TOOLCHAIN_UNPINNED")),
    )
    identity = stages.toolchain_identity("java")
    assert identity.pinned is False
    assert "host" in identity.detail
    pinned = dataclasses.replace(identity, pinned=True)
    assert identity.digest() != pinned.digest()


def test_the_rule_pack_digest_follows_the_emitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """An emitter edit has to be a cache miss, so the emitter is in the key."""
    from elmos_build_cache import elmos_route_stages

    first = rule_pack_digest()
    assert first.startswith("sha256:")
    elmos_route_stages.rule_pack_digest.cache_clear()
    assert rule_pack_digest() == first  # deterministic

    original = elmos_route_stages.RULE_PACK_MODULES
    monkeypatch.setattr(elmos_route_stages, "RULE_PACK_MODULES", original[:-1])
    elmos_route_stages.rule_pack_digest.cache_clear()
    narrowed = rule_pack_digest()
    elmos_route_stages.rule_pack_digest.cache_clear()
    assert narrowed != first, "the digest ignored one of its inputs"


# ==========================================================================
# the cache, over real conversions
# ==========================================================================
def build_dag() -> ConversionDag:
    dag = ConversionDag()
    for unit in UNITS:
        dag.add_node(
            DagNode(
                unit.node_id,
                "target-code-generation",
                Granularity.GENERATED_FILE,
                logical_outputs=(f"{unit.target_language}/{Path(unit.logical_source).stem}/",),
                estimated_cost_ms=400,
            )
        )
    dag.add_edge(UNITS[1].node_id, UNITS[0].node_id, EdgeKind.PUBLIC_INTERFACE)
    return dag


class Harness:
    def __init__(self, tmp_path: Path, clock: ManualClock, source_root: Path) -> None:
        self.root = source_root
        self.base = tmp_path / "workdir"
        self.base.mkdir()
        self.clock = clock
        self.config = dataclasses.replace(
            CacheConfig(), rollout=RolloutConfig(phase="production-certified")
        )
        self.cas = ContentAddressableStore(self.base / ".elmos" / "cache")
        self.store = SqliteMetadataStore.open(self.base / ".elmos" / "cache" / "index.sqlite", clock)
        self.dag = build_dag()
        self.stages = RouteStages(source_root, strict_toolchain=False)

    def ir_digests(self) -> dict[str, str]:
        return {unit.node_id: self.stages.ir_digest(self.stages.analyze(unit)) for unit in UNITS}

    def run(self, run_id: str, affected: dict[str, list[str]] | None = None) -> dict[str, object]:
        pipeline = ConversionPipeline(
            self.config, self.store, self.cas, self.base, TENANT, PROJECT, clock=self.clock
        )
        snapshot = take_snapshot(self.root)
        with self.store.transaction():
            workspace, coordinator, checkpoints = build_run(
                self.store, self.cas, self.config, self.base, TENANT, PROJECT, run_id,
                snapshot, self.clock,
            )
            coordinator.start_run(run_id)

        digests = self.ir_digests()
        for unit in UNITS:
            node = self.dag.node(unit.node_id)
            pipeline.fingerprint_for(
                node,
                pipeline.registry.get(node.stage_id),
                self.stages.generation_fingerprint(
                    unit,
                    digests[unit.node_id],
                    dependency_interfaces=tuple(
                        digests[dependency] for dependency in self.dag.dependencies(unit.node_id)
                    ),
                ),
            )

        plan = pipeline.plan(self.dag, affected or {})
        implementations = {
            "target-code-generation": self._dispatch(),
        }
        with self.store.transaction():
            reports = pipeline.execute(
                run_id, self.dag, plan, snapshot, implementations, workspace, coordinator, checkpoints
            )
        with self.store.transaction():
            tree, published = pipeline.assemble_and_publish(
                run_id,
                workspace,
                ValidationLevel.TEST_VERIFIED,
                evidence_records=[{"kind": "differential", "tool": "javac+java"}],
                verifier_identities=["independent-ci"],
            )
            self.store.transition_run(run_id, RunStatus.SUCCEEDED, self.store.get_run(run_id).version)
        report = pipeline.report(run_id, snapshot, plan, reports, tree, published is not None)
        return {"tree": tree, "report": report, "workspace": workspace}

    def _dispatch(self):  # noqa: ANN202 - a StageFunction
        by_node = {
            unit.node_id: self.stages.generation_stage(unit, work_root=self.base / "differential")
            for unit in UNITS
        }

        def run(node, inputs):  # noqa: ANN001, ANN202
            return by_node[node.node_id](node, inputs)

        return run

    def published(self, run_id: str, workspace, logical: str) -> str:
        publisher = TreePublisher(
            workspace.publish_root, self.cas, self.store, TENANT, run_id, clock=self.clock
        )
        return publisher.read_published(logical).decode("utf-8")


@pytest.fixture
def harness(tmp_path: Path, clock: ManualClock, source_root: Path) -> Harness:
    return Harness(tmp_path, clock, source_root)


def test_the_pipeline_publishes_what_the_route_engine_emitted(harness: Harness) -> None:
    result = harness.run("route-run-1")
    tree = result["tree"]
    report = result["report"]
    assert tree is not None and report is not None
    assert report.published is True
    assert {node.decision for node in report.nodes} == {"EXECUTE"}
    assert sorted(harness.stages.emitted) == sorted(unit.node_id for unit in UNITS)

    paths = sorted(tree.paths())
    assert any(path.endswith(".java") for path in paths), paths
    body = harness.published("route-run-1", result["workspace"], paths[0])
    assert "Math.multiplyExact" in body or "public final class" in body


def test_a_comment_only_edit_does_not_re_emit(harness: Harness) -> None:
    """The reason to key on the IR: the analyzer discards what did not change.

    A comment is not in the semantic IR, so the ActionKey does not move and the
    emitter is never asked to run again -- even though the source file's bytes,
    and therefore the snapshot, did change.
    """
    first = harness.run("route-run-1")
    before = harness.ir_digests()
    harness.stages.emitted.clear()

    path = harness.root / "billing" / "tax.py"
    path.write_text("# a note the analyzer will discard\n" + TAX, encoding="utf-8")

    after = harness.ir_digests()
    assert after == before, "the IR moved on a comment-only edit"

    second = harness.run("route-run-2")
    assert harness.stages.emitted == []
    assert {node.decision for node in second["report"].nodes} == {"RESTORE"}
    assert first["tree"].root_digest == second["tree"].root_digest


def test_a_real_body_change_re_emits_only_that_unit(harness: Harness) -> None:
    """``tax`` depends on ``discount``, so editing ``tax`` must not disturb it."""
    harness.run("route-run-1")
    harness.stages.emitted.clear()

    path = harness.root / "billing" / "tax.py"
    path.write_text(TAX.replace("return amount * quantity", "return amount * quantity + 1"), encoding="utf-8")

    closure = harness.dag.affected_closure(behavior_changed=[UNITS[0].node_id])
    result = harness.run("route-run-3", affected=closure)

    decisions = {node.node_id: node.decision for node in result["report"].nodes}
    assert decisions[UNITS[0].node_id] == "EXECUTE"
    assert decisions[UNITS[1].node_id] == "RESTORE"
    assert harness.stages.emitted == [UNITS[0].node_id]
    body = harness.published(
        "route-run-3",
        result["workspace"],
        next(path for path in result["tree"].paths() if "tax" in path),
    )
    assert "addExact" in body or "+ 1" in body


def test_editing_a_dependency_re_emits_the_dependent(harness: Harness) -> None:
    """And the other direction: the interface edge is not decorative.

    ``discount``'s IR digest is part of ``tax``'s ActionKey, so a change to the
    dependency invalidates the dependent even though the dependent's own source
    is untouched.
    """
    harness.run("route-run-1")
    harness.stages.emitted.clear()

    path = harness.root / "billing" / "discount.py"
    path.write_text(DISCOUNT.replace("amount - percent", "amount - percent - 1"), encoding="utf-8")

    closure = harness.dag.affected_closure(interface_changed=[UNITS[1].node_id])
    result = harness.run("route-run-4", affected=closure)

    decisions = {node.node_id: node.decision for node in result["report"].nodes}
    assert decisions[UNITS[1].node_id] == "EXECUTE"
    assert decisions[UNITS[0].node_id] == "EXECUTE"
    assert sorted(harness.stages.emitted) == sorted(unit.node_id for unit in UNITS)


def test_the_staged_ir_is_the_engines_own_document(harness: Harness, tmp_path: Path) -> None:
    """The intermediate the cache stages is the engine's IR, byte for byte."""
    unit = UNITS[0]
    stage = harness.stages.semantic_ir_stage(unit)
    result = stage(harness.dag.node(unit.node_id), {})
    document = json.loads(result.outputs[0].payload)
    assert document == harness.stages.analyze(unit).to_mapping()
    assert result.outputs[0].logical_path == unit.ir_path
    assert result.evidence[0]["analyzer"].startswith("CPython ast")


def test_a_wrong_translation_cannot_claim_test_verified(
    stages: RouteStages, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The differential runner has teeth.

    A translation that disagrees with the source on one input must not be able
    to claim ``TEST_VERIFIED`` -- and because the stage contract's reuse floor
    is exactly that level, a wrong result is produced but never restored.
    """
    unit = UNITS[0]
    ir = stages.analyze(unit)
    honest = stages.emit(ir, "java")
    assert stages.differential_check(unit, ir, honest, tmp_path / "honest", ((7, 3), (-5, 4))).passed

    sabotaged = dataclasses.replace(
        honest, content=honest.content.replace("Math.multiplyExact(amount, quantity)", "0L")
    )
    verdict = stages.differential_check(unit, ir, sabotaged, tmp_path / "wrong", ((7, 3),))
    assert verdict.passed is False
    assert "python=21" in verdict.detail, verdict.detail

    monkeypatch.setattr(stages, "emit", lambda ir, language: sabotaged)
    result = stages.generation_stage(unit, work_root=tmp_path / "stage")(None, {})
    assert result.validation_level is ValidationLevel.COMPILE_VERIFIED
    assert result.evidence[1]["passed"] is False
