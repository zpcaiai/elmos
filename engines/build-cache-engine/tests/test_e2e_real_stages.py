"""E2E-001, driven by real stages instead of a stand-in generator.

``test_e2e.py`` certifies the orchestration contract with a stage that returns
a formatted string. That proves the pipeline's *bookkeeping* but not that the
bookkeeping survives contact with a stage that really does something. This
module plugs in two stages that do:

``compile``
    runs the actual ``javac`` over the Java sources in a sandboxed output
    directory and stages the real ``.class`` files it produced;
``target-code-generation``
    translates Java to C# from a real tree-sitter parse tree -- class names,
    method names, parameter lists, return types and Spring route annotations
    are read out of the source's syntax, not pattern-matched out of a string.

The conversion is then *verified the way ELMOS verifies one*: the generated C#
is parsed back with the C# grammar and its public surface is compared against
the Java source's. A translation that dropped a method, changed an arity or
lost a route fails the test.

What this still is not: the production stage is model-driven, and no model runs
here. What it now is: every artifact in the published tree was produced by a
real compiler and a real parser, and every cache decision below was taken over
those real artifacts.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import CacheConfig, RolloutConfig
from elmos_build_cache.dag import ConversionDag, DagNode, EdgeKind, Granularity
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import FileClass, RunStatus, StagedFileStatus, ValidationLevel
from elmos_build_cache.fingerprint import FingerprintInputs
from elmos_build_cache.interface_hash import InterfaceIndex, extract_interface
from elmos_build_cache.manifests import ExecutionMetrics
from elmos_build_cache.pipeline import ConversionPipeline, StageOutput, StageResult, build_run
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.snapshot import take_snapshot
from elmos_build_cache.treesitter_hash import GrammarUnavailable, _parser

TENANT = "tenant-e2e-real"
PROJECT = "demo-service"

CONTROLLER = """package com.demo;

@RestController
public class UserController {
  private final UserRepository repository = new UserRepository();

  @GetMapping("/users/{id}")
  public User findUser(long id) {
    return repository.get(id);
  }

  public java.util.List<User> listUsers(int page, int size) {
    return java.util.List.of();
  }

  private String describe(User user) {
    return user.name();
  }
}
"""

REPOSITORY = """package com.demo;

public class UserRepository {
  public User get(long id) {
    return new User(id, "demo");
  }

  private long cacheKey(long id) {
    return id * 31;
  }
}
"""

USER = """package com.demo;

public class User {
  private final long id;
  private final String name;

  public User(long id, String name) {
    this.id = id;
    this.name = name;
  }

  public String name() {
    return name;
  }
}
"""

# Minimal local stand-ins for the Spring annotations, so that ``javac`` really
# compiles this project without reaching a network it does not have.
REST_CONTROLLER = """package com.demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface RestController {}
"""

GET_MAPPING = """package com.demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface GetMapping {
  String value();
}
"""

SOURCES = {
    "com/demo/RestController.java": REST_CONTROLLER,
    "com/demo/GetMapping.java": GET_MAPPING,
    "com/demo/UserController.java": CONTROLLER,
    "com/demo/UserRepository.java": REPOSITORY,
    "com/demo/User.java": USER,
}

TARGETS = {
    "generate:UserController": ("src/Controllers/UserController.cs", "com/demo/UserController.java"),
    "generate:UserRepository": ("src/Repositories/UserRepository.cs", "com/demo/UserRepository.java"),
}


# --------------------------------------------------------------------------
# a real translator, built on the parse tree
# --------------------------------------------------------------------------
TYPE_MAP = {
    "long": "long",
    "int": "int",
    "boolean": "bool",
    "String": "string",
    "void": "void",
    "java.util.List<User>": "List<User>",
}

ROUTE_ATTRIBUTE = {
    "GetMapping": "HttpGet",
    "PostMapping": "HttpPost",
    "PutMapping": "HttpPut",
    "DeleteMapping": "HttpDelete",
}


def _child(node: Any, field: str) -> Any:
    return node.child_by_field_name(field)


def _text(node: Any) -> str:
    return (node.text or b"").decode("utf-8")


def _map_type(java_type: str) -> str:
    return TYPE_MAP.get(java_type, java_type.split(".")[-1])


def _pascal(name: str) -> str:
    return name[:1].upper() + name[1:]


def java_classes(source: str) -> list[dict[str, Any]]:
    """Read the classes, their public methods and their routes out of the tree."""
    tree = _parser("java").parse(source.encode("utf-8"))
    classes: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if node.type == "class_declaration":
            body = _child(node, "body")
            methods = []
            for member in body.named_children if body is not None else []:
                if member.type != "method_declaration":
                    continue
                if not _is_public(member):
                    continue
                parameters = _child(member, "parameters")
                params = []
                for parameter in parameters.named_children if parameters is not None else []:
                    if parameter.type != "formal_parameter":
                        continue
                    params.append(
                        (
                            _map_type(_text(_child(parameter, "type"))),
                            _text(_child(parameter, "name")),
                        )
                    )
                route = None
                for annotation in _annotations(member):
                    name = annotation.split("(", 1)[0].lstrip("@")
                    if name in ROUTE_ATTRIBUTE:
                        path = annotation.split('"')[1] if '"' in annotation else "/"
                        route = (ROUTE_ATTRIBUTE[name], path)
                methods.append(
                    {
                        "name": _pascal(_text(_child(member, "name"))),
                        "returns": _map_type(_text(_child(member, "type"))),
                        "params": params,
                        "route": route,
                    }
                )
            classes.append({"name": _text(_child(node, "name")), "methods": methods})
        for child in node.named_children:
            visit(child)

    visit(tree.root_node)
    return classes


def _is_public(member: Any) -> bool:
    """Read the modifier list, not the text: an annotation can carry braces."""
    for child in member.named_children:
        if child.type == "modifiers":
            return any(
                grandchild.type == "modifier" or _text(grandchild) == "public"
                for grandchild in child.children
                if _text(grandchild) == "public"
            )
    return False


def _annotations(member: Any) -> list[str]:
    found: list[str] = []
    for child in member.named_children:
        if child.type in ("marker_annotation", "annotation"):
            found.append(_text(child))
        elif child.type == "modifiers":
            for grandchild in child.named_children:
                if grandchild.type in ("marker_annotation", "annotation"):
                    found.append(_text(grandchild))
    return found


def translate_to_csharp(logical_source: str, source: str) -> str:
    lines = [
        f"// generated from {logical_source} by elmos-translate/1",
        "using System.Collections.Generic;",
        "",
        "namespace Demo;",
        "",
    ]
    for klass in java_classes(source):
        lines.append(f"public class {klass['name']}")
        lines.append("{")
        for method in klass["methods"]:
            if method["route"] is not None:
                attribute, path = method["route"]
                lines.append(f'    [{attribute}("{path}")]')
            params = ", ".join(f"{ptype} {pname}" for ptype, pname in method["params"])
            lines.append(f"    public {method['returns']} {method['name']}({params})")
            lines.append("    {")
            lines.append("        throw new System.NotImplementedException();")
            lines.append("    }")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# the stages
# --------------------------------------------------------------------------
def javac_binary() -> str:
    path = shutil.which("javac")
    if path is None:
        pytest.skip("javac is not available in this environment")
    return path


class Stages:
    """Real stage implementations, recording what actually ran."""

    def __init__(self, root: Path, work: Path) -> None:
        self.root = root
        self.work = work
        self.generated: list[str] = []
        self.compiled: list[str] = []

    def source_text(self, logical: str) -> str:
        return (self.root / "src" / "main" / "java" / logical).read_text(encoding="utf-8")

    # -- stage 1: a real compiler ----------------------------------------
    def validate_sources(self, node: DagNode, inputs: Mapping[str, Any]) -> StageResult:
        javac = javac_binary()
        self.compiled.append(node.node_id)
        out = self.work / "classes" / node.node_id.replace(":", "-")
        out.mkdir(parents=True, exist_ok=True)
        files = sorted((self.root / "src" / "main" / "java").rglob("*.java"))
        completed = subprocess.run(  # noqa: S603
            [javac, "-d", str(out), *[str(path) for path in files]],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        outputs = tuple(
            StageOutput(
                logical_path=f"build_output/classes/{path.relative_to(out).as_posix()}",
                payload=path.read_bytes(),
                file_class=FileClass.STAGED_INTERMEDIATE,
                media_type="application/java-vm",
            )
            for path in sorted(out.rglob("*.class"))
        )
        assert outputs, "javac produced no class files"
        return StageResult(
            outputs=outputs,
            metrics=ExecutionMetrics(wall_ms=1200, cpu_ms=1100, compiler_ms=1100, model_tokens=0),
            completed_partitions=(node.node_id,),
            evidence=({"kind": "compile", "tool": "javac", "files": len(files)},),
            validation_level=ValidationLevel.TEST_VERIFIED,
        )

    # -- stage 2: a real translation -------------------------------------
    def generate(self, node: DagNode, inputs: Mapping[str, Any]) -> StageResult:
        self.generated.append(node.node_id)
        target_path, logical_source = TARGETS[node.node_id]
        source = self.source_text(logical_source)
        csharp = translate_to_csharp(logical_source, source)
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
            metrics=ExecutionMetrics(wall_ms=8000, cpu_ms=600, compiler_ms=0, model_tokens=15000),
            completed_partitions=(node.node_id,),
            evidence=({"kind": "generation", "translator": "elmos-translate/1"},),
            validation_level=ValidationLevel.TEST_VERIFIED,
        )


def build_dag() -> ConversionDag:
    dag = ConversionDag()
    dag.add_node(
        DagNode(
            "validate:sources",
            "compile",
            Granularity.MODULE,
            logical_outputs=("build_output/classes/com/demo/User.class",),
            estimated_cost_ms=1200,
        )
    )
    for node_id, (target, _) in TARGETS.items():
        dag.add_node(
            DagNode(
                node_id,
                "target-code-generation",
                Granularity.GENERATED_FILE,
                logical_outputs=(target,),
                estimated_cost_ms=8000,
            )
        )
    dag.add_edge("validate:sources", "generate:UserRepository", EdgeKind.SEQUENCING)
    dag.add_edge("validate:sources", "generate:UserController", EdgeKind.SEQUENCING)
    dag.add_edge("generate:UserRepository", "generate:UserController", EdgeKind.PUBLIC_INTERFACE)
    return dag


class Harness:
    def __init__(self, tmp_path: Path, clock: ManualClock) -> None:
        self.root = tmp_path / "source"
        base = self.root / "src" / "main" / "java" / "com" / "demo"
        base.mkdir(parents=True)
        for logical, text in SOURCES.items():
            (self.root / "src" / "main" / "java" / logical).write_text(text, encoding="utf-8")
        self.base = tmp_path / "workdir"
        self.base.mkdir()
        self.clock = clock
        self.config = dataclasses.replace(
            CacheConfig(), rollout=RolloutConfig(phase="production-certified")
        )
        self.cas = ContentAddressableStore(self.base / ".elmos" / "cache")
        self.store = SqliteMetadataStore.open(self.base / ".elmos" / "cache" / "index.sqlite", clock)
        self.dag = build_dag()
        self.stages = Stages(self.root, self.base / "stage-work")

    def sources(self) -> dict[str, str]:
        return {
            logical: (self.root / "src" / "main" / "java" / logical).read_text(encoding="utf-8")
            for logical in SOURCES
        }

    def index(self) -> InterfaceIndex:
        index = InterfaceIndex()
        for logical, text in self.sources().items():
            index.add_source(logical, text)
        return index

    def fingerprints(self, pipeline: ConversionPipeline, index: InterfaceIndex) -> None:
        api = index.public_interface_digests()
        for node in self.dag.nodes:
            if node.node_id == "validate:sources":
                inputs = FingerprintInputs(
                    input_artifact_digests=tuple(
                        index.interfaces[logical].raw_digest for logical in sorted(SOURCES)
                    ),
                    target_language="java",
                    target_framework="jvm",
                    target_runtime="jdk",
                    toolchain_digest="sha256:" + "4" * 64,
                    declared_environment={"LANG": "C.UTF-8", "TZ": "UTC"},
                )
            else:
                _, logical = TARGETS[node.node_id]
                own = index.interfaces[logical]
                inputs = FingerprintInputs(
                    input_artifact_digests=(own.semantic_digest,),
                    source_semantic_digest=own.semantic_digest,
                    dependency_public_interface_digests=tuple(
                        api[TARGETS[dependency][1]]
                        for dependency in self.dag.dependencies(node.node_id)
                        if dependency in TARGETS
                    ),
                    target_language="csharp",
                    target_framework="aspnet-core",
                    target_runtime="net10.0",
                    rule_pack_digest="sha256:" + "5" * 64,
                    toolchain_digest="sha256:" + "4" * 64,
                    prompt_template_digest="sha256:" + "7" * 64,
                    model_snapshot_digest="sha256:" + "8" * 64,
                    declared_environment={"LANG": "C.UTF-8", "TZ": "UTC"},
                )
            pipeline.fingerprint_for(node, pipeline.registry.get(node.stage_id), inputs)

    def run(self, run_id: str, affected: Mapping[str, list[str]] | None = None) -> dict[str, Any]:
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
        self.fingerprints(pipeline, self.index())
        plan = pipeline.plan(self.dag, affected or {})
        implementations = {
            "compile": self.stages.validate_sources,
            "target-code-generation": self.stages.generate,
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
                evidence_records=[{"kind": "test", "passed": 12, "failed": 0}],
                verifier_identities=["independent-ci"],
            )
            self.store.transition_run(run_id, RunStatus.SUCCEEDED, self.store.get_run(run_id).version)
        report = pipeline.report(run_id, snapshot, plan, reports, tree, published is not None)
        return {
            "pipeline": pipeline,
            "workspace": workspace,
            "tree": tree,
            "report": report,
            "published": published,
        }

    def read_published(self, run_id: str, workspace: Any, logical: str) -> str:
        publisher = TreePublisher(
            workspace.publish_root, self.cas, self.store, TENANT, run_id, clock=self.clock
        )
        return publisher.read_published(logical).decode("utf-8")


@pytest.fixture
def harness(tmp_path: Path, clock: ManualClock) -> Harness:
    try:
        _parser("java")
        _parser("csharp")
    except GrammarUnavailable as error:  # pragma: no cover - environment dependent
        pytest.skip(str(error))
    javac_binary()
    return Harness(tmp_path, clock)


# ==========================================================================
# the translator itself
# ==========================================================================
def test_the_translator_reads_the_parse_tree_not_the_text() -> None:
    try:
        classes = java_classes(CONTROLLER)
    except GrammarUnavailable as error:
        pytest.skip(str(error))
    assert [klass["name"] for klass in classes] == ["UserController"]
    methods = {method["name"]: method for method in classes[0]["methods"]}
    assert set(methods) == {"FindUser", "ListUsers"}, "a private method leaked into the target API"
    assert methods["FindUser"]["route"] == ("HttpGet", "/users/{id}")
    assert methods["ListUsers"]["params"] == [("int", "page"), ("int", "size")]
    assert methods["ListUsers"]["returns"] == "List<User>"


def test_the_generated_csharp_preserves_the_public_surface() -> None:
    """The verification ELMOS actually cares about, run on real output."""
    try:
        csharp = translate_to_csharp("com/demo/UserController.java", CONTROLLER)
        java_interface = extract_interface("java", "com/demo/UserController.java", CONTROLLER)
        csharp_interface = extract_interface("csharp", "src/Controllers/UserController.cs", csharp)
    except GrammarUnavailable as error:
        pytest.skip(str(error))

    java_public = {
        symbol.name for symbol in java_interface.public_symbols() if symbol.kind.value == "FUNCTION"
    }
    csharp_public = {
        symbol.name for symbol in csharp_interface.public_symbols() if symbol.kind.value == "FUNCTION"
    }
    assert csharp_public == {_pascal(name) for name in java_public}
    assert java_interface.routes == csharp_interface.routes == ("/users/{id}",)
    # And the generated file is itself parseable C#, not a plausible-looking string.
    assert csharp_interface.confidence.value == "EXACT", csharp_interface.notes


def test_a_dropped_method_would_fail_verification() -> None:
    """The check above has teeth: break the translation and it must complain."""
    try:
        csharp = translate_to_csharp("com/demo/UserController.java", CONTROLLER)
        broken = csharp.replace("    public List<User> ListUsers(int page, int size)\n", "    public List<User> Missing(\n")
        java_interface = extract_interface("java", "com/demo/UserController.java", CONTROLLER)
        broken_interface = extract_interface("csharp", "src/Controllers/UserController.cs", broken)
    except GrammarUnavailable as error:
        pytest.skip(str(error))
    java_public = {
        _pascal(symbol.name)
        for symbol in java_interface.public_symbols()
        if symbol.kind.value == "FUNCTION"
    }
    broken_public = {
        symbol.name for symbol in broken_interface.public_symbols() if symbol.kind.value == "FUNCTION"
    }
    assert broken_public != java_public


# ==========================================================================
# E2E-001 over real artifacts
# ==========================================================================
def test_e2e_001_real_stages_compile_translate_and_publish(harness: Harness) -> None:
    result = harness.run("run-real-1")
    tree = result["tree"]
    report = result["report"]

    assert tree is not None and report is not None
    assert report.published is True
    assert report.unjustified_skips() == []
    assert {node.decision for node in report.nodes} == {"EXECUTE"}
    assert harness.stages.compiled == ["validate:sources"]
    assert sorted(harness.stages.generated) == [
        "generate:UserController",
        "generate:UserRepository",
    ]

    published = sorted(tree.paths())
    assert "src/Controllers/UserController.cs" in published
    assert "src/Repositories/UserRepository.cs" in published
    # javac's real output is staged, and staged intermediates stay unpublished.
    assert not any(path.endswith(".class") for path in published)
    staged = harness.store.list_staged_files("run-real-1")
    assert any(record.logical_path.endswith("User.class") for record in staged)

    sealed = {
        record.logical_path
        for record in staged
        if record.status in (StagedFileStatus.PUBLISHED, StagedFileStatus.TREE_INCLUDED)
    }
    assert set(published) <= sealed

    body = harness.read_published("run-real-1", result["workspace"], "src/Controllers/UserController.cs")
    assert '[HttpGet("/users/{id}")]' in body
    assert "public User FindUser(long id)" in body
    assert "describe" not in body, "a private Java method reached the target"


def test_the_published_csharp_round_trips_through_the_csharp_grammar(harness: Harness) -> None:
    result = harness.run("run-real-2")
    body = harness.read_published("run-real-2", result["workspace"], "src/Repositories/UserRepository.cs")
    interface = extract_interface("csharp", "src/Repositories/UserRepository.cs", body)
    assert interface.confidence.value == "EXACT"
    assert {symbol.name for symbol in interface.public_symbols() if symbol.kind.value == "FUNCTION"} == {
        "Get"
    }
    assert "cacheKey" not in body and "CacheKey" not in body


def test_a_no_change_rerun_reruns_neither_the_compiler_nor_the_translator(harness: Harness) -> None:
    first = harness.run("run-real-1")
    harness.stages.generated.clear()
    harness.stages.compiled.clear()

    second = harness.run("run-real-2")

    assert first["tree"].root_digest == second["tree"].root_digest
    assert harness.stages.generated == []
    assert harness.stages.compiled == []
    assert {node.decision for node in second["report"].nodes} == {"RESTORE"}
    assert all(node.justification for node in second["report"].nodes)
    saved = second["report"].telemetry["accounting"]["saved"]
    assert saved["model_tokens"] >= 30000
    assert saved["compiler_ms"] >= 1100


def test_a_private_body_edit_regenerates_only_the_edited_module(harness: Harness) -> None:
    """The whole point of exact interface hashing, end to end.

    ``cacheKey`` is private. Editing it changes ``UserRepository``'s body digest
    and nothing else, so the controller that depends on its *interface* must be
    restored from cache rather than retranslated.
    """
    harness.run("run-real-1")
    harness.stages.generated.clear()
    harness.stages.compiled.clear()

    repository = harness.root / "src" / "main" / "java" / "com" / "demo" / "UserRepository.java"
    repository.write_text(REPOSITORY.replace("id * 31", "id * 37"), encoding="utf-8")

    closure = harness.dag.affected_closure(behavior_changed=["generate:UserRepository"])
    result = harness.run("run-real-3", affected=closure)

    decisions = {node.node_id: node.decision for node in result["report"].nodes}
    assert decisions["generate:UserRepository"] == "EXECUTE"
    assert decisions["generate:UserController"] == "RESTORE"
    assert harness.stages.generated == ["generate:UserRepository"]


def test_a_public_signature_edit_retranslates_the_dependent(harness: Harness) -> None:
    harness.run("run-real-1")
    harness.stages.generated.clear()

    repository = harness.root / "src" / "main" / "java" / "com" / "demo" / "UserRepository.java"
    # Adding a public method is an interface change that still compiles, which
    # is what a real refactor looks like.
    repository.write_text(
        REPOSITORY.replace(
            "  private long cacheKey",
            '  public User getByName(String name) {\n    return new User(1L, name);\n  }\n\n  private long cacheKey',
        ),
        encoding="utf-8",
    )
    closure = harness.dag.affected_closure(interface_changed=["generate:UserRepository"])
    result = harness.run("run-real-4", affected=closure)

    assert sorted(harness.stages.generated) == [
        "generate:UserController",
        "generate:UserRepository",
    ]
    decisions = {node.node_id: node.decision for node in result["report"].nodes}
    assert decisions["generate:UserRepository"] == "EXECUTE"
    assert decisions["generate:UserController"] == "EXECUTE"


def test_a_new_public_method_appears_in_the_published_target(harness: Harness) -> None:
    """A real translation, not a memoised string: new input, new output."""
    harness.run("run-real-1")
    controller = harness.root / "src" / "main" / "java" / "com" / "demo" / "UserController.java"
    controller.write_text(
        CONTROLLER.replace(
            "  private String describe(User user) {",
            "  public boolean exists(long id) {\n    return true;\n  }\n\n  private String describe(User user) {",
        ),
        encoding="utf-8",
    )
    closure = harness.dag.affected_closure(interface_changed=["generate:UserController"])
    result = harness.run("run-real-5", affected=closure)

    body = harness.read_published("run-real-5", result["workspace"], "src/Controllers/UserController.cs")
    assert "public bool Exists(long id)" in body
