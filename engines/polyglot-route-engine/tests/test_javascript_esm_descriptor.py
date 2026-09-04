"""Repository-level closure for Node's ``.js`` ESM interpretation.

``javascript`` is a deprecated language: it is absent from the active route
matrix, so ``engine.migrate`` and ``engine.migrate_module`` reject every
javascript direction with ``UNSUPPORTED_DIRECTED_ROUTE`` before any Node.js
specific logic runs.  The descriptor machinery below is unchanged and still
ships; three route-level tests that used to drive it through ``migrate`` are
therefore skipped under ``JAVASCRIPT_ROUTE_RETIRED``.  That is a real, recorded
coverage loss of the deprecation -- not a test that passes.  Reviving
javascript means putting it back in ``SUPPORTED_LANGUAGES`` and un-skipping
them; deleting them instead would erase the record that the guards exist.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest

from elmos_polyglot_route import engine, native
from elmos_polyglot_route.batch import run_batch
from elmos_polyglot_route.discovery import discover_repository
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.pipeline import run_repository_pipeline
from elmos_polyglot_route.project_graph import build_project_graph
from elmos_polyglot_route.repository import plan_repository
from elmos_polyglot_route.toolchains import ExactToolchain
from elmos_polyglot_route.validation import validate_source

JAVASCRIPT_ROUTE_RETIRED = pytest.mark.skip(
    reason=(
        "javascript is deprecated; engine.migrate rejects the direction with "
        "UNSUPPORTED_DIRECTED_ROUTE before the descriptor guard can run"
    )
)

SOURCE = "/** @param {integer} value @returns {integer} */\nexport function identity(value) { return value; }\n"


def _repository(tmp_path: Path, package: str | None = '{"type":"module"}\n') -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "identity.js"
    source.write_text(SOURCE, encoding="utf-8")
    if package is not None:
        (repository / "package.json").write_text(package, encoding="utf-8")
    return repository, source


def test_plain_js_binds_nearest_byte_addressed_esm_descriptor_across_all_stages(tmp_path: Path) -> None:
    repository, source = _repository(tmp_path)
    package = (repository / "package.json").read_bytes()
    expected = {
        "path": "package.json",
        "sha256": hashlib.sha256(package).hexdigest(),
        "bytes": len(package),
        "type": "module",
    }

    plan = plan_repository(
        repository,
        "local:javascript-esm-descriptor",
        "javascript",
        "python",
        allow_deprecated_replay=True,
    )
    assert plan["work_units"][0]["javascript_esm_descriptor"] == expected
    assert plan["javascript_esm_descriptors"] == [{"source_path": "identity.js", **expected}]

    discovery = discover_repository(plan, repository)
    assert discovery["module_inventories"][0]["javascript_esm_descriptor"] == expected
    graph = build_project_graph(repository, "local:javascript-esm-descriptor", discovery)
    nodes = cast(list[dict[str, Any]], graph["nodes"])
    source_node = next(node for node in nodes if node["path"] == "identity.js")
    assert source_node["attributes"]["javascript_esm_descriptor"] == expected
    assert graph["javascript_esm_descriptors"] == [{"source_path": "identity.js", **expected}]

    semantic = analyze(source, "javascript", "identity")
    report = validate_source(
        source,
        "javascript",
        semantic.functions[0],
        [{"args": [3], "expected": 3}],
        tmp_path / "run",
    )
    assert report["status"] == "PASSED"
    assert report["javascript_esm_descriptor"] == {
        "logical_path": "package.json",
        "sha256": "sha256:" + expected["sha256"],
        "bytes": expected["bytes"],
        "type": "module",
    }
    assert report["javascript_esm_descriptor_observation"] == {"observed_origin_path": str(repository / "package.json")}
    assert (tmp_path / "run" / "package.json").read_bytes() == package


def test_plain_js_validation_descriptor_is_stable_across_absolute_roots(
    tmp_path: Path,
) -> None:
    reports: list[dict[str, Any]] = []
    for name in ("first", "second"):
        root = tmp_path / name
        root.mkdir()
        repository, source = _repository(root)
        semantic = analyze(source, "javascript", "identity")
        reports.append(
            validate_source(
                source,
                "javascript",
                semantic.functions[0],
                [{"args": [3], "expected": 3}],
                tmp_path / f"run-{name}",
            )
        )

    assert reports[0]["javascript_esm_descriptor"] == reports[1]["javascript_esm_descriptor"]
    assert reports[0]["javascript_esm_descriptor_observation"] != reports[1]["javascript_esm_descriptor_observation"]


def test_engine_binds_descriptor_observation_to_the_executed_private_snapshot(
    tmp_path: Path,
) -> None:
    snapshot = (tmp_path / "source" / "package.json").resolve()
    snapshot.parent.mkdir()
    snapshot.write_text('{"type":"module"}\n', encoding="utf-8")
    binding = {
        "logical_path": "package.json",
        "sha256": "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "bytes": snapshot.stat().st_size,
        "type": "module",
    }
    runtime = {
        "javascript_esm_descriptor": binding,
        "javascript_esm_descriptor_observation": {
            "observed_origin_path": str(snapshot)
        },
    }

    second_runtime = json.loads(json.dumps(runtime))
    assert engine._bound_javascript_runtime_descriptor_observation(
        binding,
        snapshot,
        [runtime, second_runtime],
    ) == {"observed_origin_path": str(snapshot)}

    runtime["javascript_esm_descriptor_observation"] = {
        "observed_origin_path": str(tmp_path / "live" / "package.json")
    }
    with pytest.raises(
        RouteError,
        match="^JAVASCRIPT_ESM_RUNTIME_DESCRIPTOR_EVIDENCE_MISMATCH$",
    ):
        engine._bound_javascript_runtime_descriptor_observation(
            binding,
            snapshot,
            [runtime, second_runtime],
        )


def test_private_js_snapshot_preserves_nested_descriptor_topology(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "src" / "lib" / "identity.js"
    source.parent.mkdir(parents=True)
    source.write_text(SOURCE, encoding="utf-8")
    package = repository / "package.json"
    package.write_text('{"type":"module"}\n', encoding="utf-8")
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)

    source_snapshot, binding, descriptor_bytes, descriptor_snapshot = (
        engine._private_javascript_source_snapshot(
            private_root,
            source,
            "javascript",
            source.read_bytes(),
        )
    )

    assert binding is not None
    assert descriptor_bytes == package.read_bytes()
    assert descriptor_snapshot is not None
    assert binding["logical_path"] == "../../package.json"
    assert Path(os.path.relpath(descriptor_snapshot, source_snapshot.parent)).as_posix() == binding[
        "logical_path"
    ]
    observed = engine.javascript_esm_descriptor(source_snapshot)
    assert observed is not None
    assert observed["path"] == str(descriptor_snapshot)
    assert observed["sha256"] == hashlib.sha256(package.read_bytes()).hexdigest()
    assert (
        engine._javascript_descriptor_snapshot_for_source(source_snapshot, binding)
        == descriptor_snapshot
    )


@pytest.mark.parametrize(
    "module",
    [False, pytest.param(True, marks=JAVASCRIPT_ROUTE_RETIRED)],
)
def test_nested_descriptor_snapshot_reaches_single_and_module_inner_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: bool,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "src" / "lib" / "identity.js"
    source.parent.mkdir(parents=True)
    source.write_text(SOURCE, encoding="utf-8")
    (repository / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    source_snapshot, binding, descriptor_bytes, descriptor_snapshot = (
        engine._private_javascript_source_snapshot(
            private_root,
            source,
            "javascript",
            source.read_bytes(),
        )
    )
    assert binding is not None
    assert descriptor_bytes is not None
    assert descriptor_snapshot is not None
    seen: list[Path | None] = []

    def probe(
        expected: dict[str, Any] | None,
        snapshot: Path | None,
        expected_bytes: bytes | None,
    ) -> None:
        assert expected == binding
        assert expected_bytes == descriptor_bytes
        seen.append(snapshot)
        raise RouteError("DESCRIPTOR_SNAPSHOT_PROBE")

    monkeypatch.setattr(engine, "_require_javascript_descriptor_snapshot", probe)
    namespace = engine.standalone_artifact_unit_namespace(
        source.name,
        "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    if module:
        manifest = private_root / "manifest.json"
        manifest.write_text("{}\n", encoding="utf-8")
        call = lambda: engine._migrate_module_snapshot(  # noqa: E731
            source_snapshot,
            "javascript",
            "python",
            manifest,
            tmp_path / "output",
            identifier_unit_namespace=namespace,
            javascript_descriptor=binding,
            javascript_descriptor_bytes=descriptor_bytes,
        )
    else:
        cases = private_root / "cases.json"
        cases.write_text("[]\n", encoding="utf-8")
        call = lambda: engine._migrate_from_snapshot(  # noqa: E731
            source_snapshot,
            "javascript",
            "python",
            "identity",
            cases,
            tmp_path / "output",
            identifier_unit_namespace=namespace,
            javascript_descriptor=binding,
            javascript_descriptor_bytes=descriptor_bytes,
        )
    with pytest.raises(RouteError, match="^DESCRIPTOR_SNAPSHOT_PROBE$"):
        call()
    assert seen == [descriptor_snapshot]


@pytest.mark.parametrize(
    ("package", "suffix", "error"),
    [
        (None, ".js", "JAVASCRIPT_ESM_DESCRIPTOR_REQUIRED"),
        ('{"type":"commonjs"}\n', ".js", "JAVASCRIPT_ESM_DESCRIPTOR_TYPE_MODULE_REQUIRED"),
        ('{"type":"module","type":"commonjs"}\n', ".js", "JAVASCRIPT_ESM_DESCRIPTOR_AMBIGUOUS"),
        ('{"type":"module"}\n', ".cjs", "JAVASCRIPT_CJS_SOURCE_BLOCKED"),
    ],
)
def test_node_descriptor_negative_inputs_never_create_target_artifacts(
    tmp_path: Path,
    package: str | None,
    suffix: str,
    error: str,
) -> None:
    repository, source = _repository(tmp_path, package)
    if suffix != ".js":
        cjs = source.with_suffix(suffix)
        source.rename(cjs)
    cases = tmp_path / "cases"
    cases.mkdir()
    output = tmp_path / "output"

    with pytest.raises(RouteError, match=f"^{error}"):
        plan_repository(
            repository,
            "local:javascript-esm-negative",
            "javascript",
            "python",
            allow_deprecated_replay=True,
        )

    assert not (output / "repository-migration-artifact.zip").exists()
    assert not (output / "assembled").exists()


def test_descriptor_drift_between_plan_and_discovery_fails_closed(tmp_path: Path) -> None:
    repository, _source = _repository(tmp_path)
    plan = plan_repository(
        repository,
        "local:javascript-esm-drift",
        "javascript",
        "python",
        allow_deprecated_replay=True,
    )
    (repository / "package.json").write_text('{"type":"module","name":"drift"}\n', encoding="utf-8")

    with pytest.raises(RouteError, match="^JAVASCRIPT_ESM_DESCRIPTOR_CHANGED:identity\\.js$"):
        discover_repository(plan, repository)


def test_descriptor_drift_during_native_execution_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, source = _repository(tmp_path)
    toolchain = ExactToolchain(
        language="javascript",
        version="Node.js 26.0.0 / ES2022 / ESM",
        executable="/private/exact/node",
        profile=(
            "node-toolchain-closure-schema=v1",
            "node-closure-sha256=bd919085f8ae40bca10d5a2da36542eb90c5f18424dc60780c73c70b90d4244b",
            "node-closure-profile=homebrew-node26-libada-77917065434c-616512",
            "platform=Darwin/arm64",
            "module=ESM",
        ),
        executable_sha256="1" * 64,
    )

    def mutate_descriptor(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, str]:
        del command, cwd, timeout
        (repository / "package.json").write_text('{"type":"module","name":"drift"}\n', encoding="utf-8")
        return {"analyzer_version": "typescript-ast-test"}

    monkeypatch.setattr(native, "_run", mutate_descriptor)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)

    with pytest.raises(RouteError, match="^JAVASCRIPT_ANALYZER_INPUT_CHANGED_DURING_EXECUTION$"):
        native._run_trusted_javascript_analyzer(toolchain, source, "identity")


def test_plain_js_to_python_repository_pipeline_is_retired_before_artifacts(tmp_path: Path) -> None:
    repository, _source = _repository(tmp_path)
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "WU-00001.json").write_text('[{"args":[3],"expected":3}]\n', encoding="utf-8")
    output = tmp_path / "output"

    with pytest.raises(RouteError, match="^UNSUPPORTED_LANGUAGE$"):
        run_repository_pipeline(
            repository,
            "local:javascript-esm-positive",
            "javascript",
            "python",
            cases,
            output,
        )

    assert not (output / "repository-migration-artifact.zip").exists()
    assert not (output / "repository-pipeline-report.json").exists()


def test_historical_javascript_discovery_cannot_enter_repository_batch(
    tmp_path: Path,
) -> None:
    repository, _source = _repository(tmp_path)
    plan = plan_repository(
        repository,
        "local:javascript-explicit-historical-replay",
        "javascript",
        "python",
        allow_deprecated_replay=True,
    )
    discovery = discover_repository(plan, repository)
    cases = tmp_path / "cases"
    cases.mkdir()
    output = tmp_path / "batch-output"

    with pytest.raises(
        RouteError,
        match="^DEPRECATED_REPLAY_AGGREGATION_FORBIDDEN$",
    ):
        run_batch(discovery, repository, cases, output)

    assert not output.exists()


@JAVASCRIPT_ROUTE_RETIRED
def test_engine_rejects_origin_descriptor_drift_after_private_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, source = _repository(tmp_path)
    cases = tmp_path / "cases.json"
    cases.write_text('[{"args":[3],"expected":3}]\n', encoding="utf-8")

    def mutate_origin(snapshot: Path, *args: object, **kwargs: object) -> dict[str, object]:
        del snapshot, args
        descriptor = cast(dict[str, Any], kwargs["javascript_descriptor"])
        assert descriptor["snapshot_path"] == "source/package.json"
        (repository / "package.json").write_text('{"type":"module","name":"drift"}\n', encoding="utf-8")
        return {}

    monkeypatch.setattr(engine, "_migrate_from_snapshot", mutate_origin)

    with pytest.raises(RouteError, match="^JAVASCRIPT_ESM_DESCRIPTOR_ORIGIN_CHANGED_DURING_MIGRATION$"):
        engine.migrate(source, "javascript", "python", "identity", cases, tmp_path / "output")


@JAVASCRIPT_ROUTE_RETIRED
def test_engine_rejects_private_descriptor_snapshot_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repository_root, source = _repository(tmp_path)
    cases = tmp_path / "cases.json"
    cases.write_text('[{"args":[3],"expected":3}]\n', encoding="utf-8")

    def tamper_snapshot(snapshot: Path, *args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        (snapshot.parent / "package.json").write_text('{"type":"module","name":"tampered"}\n', encoding="utf-8")
        return {}

    monkeypatch.setattr(engine, "_migrate_from_snapshot", tamper_snapshot)

    with pytest.raises(RouteError, match="^JAVASCRIPT_ESM_DESCRIPTOR_SNAPSHOT_CHANGED_DURING_MIGRATION$"):
        engine.migrate(source, "javascript", "python", "identity", cases, tmp_path / "output")


def test_every_javascript_direction_is_retired_at_the_route_boundary(tmp_path: Path) -> None:
    """The deprecation itself, asserted where it takes effect.

    This replaces the end-to-end reach of the three skipped tests above: it
    proves the direction is refused, and refused *early*, which is why their
    descriptor assertions can no longer be reached.
    """

    _repository_root, source = _repository(tmp_path)
    cases = tmp_path / "cases.json"
    cases.write_text('[{"args":[3],"expected":3}]\n', encoding="utf-8")

    for target in ("python", "java", "typescript"):
        with pytest.raises(RouteError, match=f"^UNSUPPORTED_DIRECTED_ROUTE:javascript-to-{target}$"):
            engine.migrate(source, "javascript", target, "identity", cases, tmp_path / f"out-{target}")
