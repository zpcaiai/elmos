from __future__ import annotations

import copy
import time
from pathlib import Path

import pytest

from elmos_polyglot_route import toolchains
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.validation import validate


@pytest.fixture(scope="module")
def node_closure() -> dict[str, object]:
    return toolchains._node_dependency_closure()


@pytest.fixture(scope="module")
def typescript_closure() -> dict[str, object]:
    return toolchains._typescript_compiler_closure()


def test_javascript_exact_toolchain_binds_recursive_node26_closure_without_ambient_path(
    monkeypatch: pytest.MonkeyPatch,
    node_closure: dict[str, object],
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    selected = toolchains.exact_toolchain("javascript")
    closure_profile = toolchains._verify_node_dependency_closure(node_closure)

    assert selected.executable == str(toolchains._EXPECTED_NODE_EXECUTABLE)
    assert selected.executable_sha256 == toolchains._EXPECTED_NODE_SHA256
    assert {
        "node-toolchain-closure-schema=v1",
        f"node-install-root={toolchains._EXPECTED_NODE_ROOT}",
        f"node-closure-sha256={node_closure['sha256']}",
        f"node-closure-profile={closure_profile}",
        f"node-closure-component-count={toolchains._EXPECTED_NODE_CLOSURE_COMPONENT_COUNT}",
        f"node-closure-edge-count={toolchains._EXPECTED_NODE_CLOSURE_EDGE_COUNT}",
        f"node-closure-system-edge-count={toolchains._EXPECTED_NODE_CLOSURE_SYSTEM_EDGE_COUNT}",
        f"node-closure-bytes={node_closure['bytes']}",
        f"node-system-edge-sha256={toolchains._EXPECTED_NODE_SYSTEM_EDGE_SHA256}",
        f"libnode-sha256={toolchains._EXPECTED_NODE_LIBNODE_SHA256}",
        f"libnode-bytes={toolchains._EXPECTED_NODE_LIBNODE_BYTES}",
        "otool-system-tool-content-soundness=NOT_RUN",
        "dyld-system-library-content-soundness=NOT_RUN",
        "compiler-runtime-semantic-soundness=NOT_RUN",
    } <= set(selected.profile)


def test_typescript_exact_toolchain_binds_node_and_compiler_closures_without_ambient_path(
    monkeypatch: pytest.MonkeyPatch,
    node_closure: dict[str, object],
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    selected = toolchains.exact_toolchain("typescript")
    closure_profile = toolchains._verify_node_dependency_closure(node_closure)

    assert selected.executable == str(toolchains._EXPECTED_NODE_EXECUTABLE)
    assert selected.executable_sha256 == toolchains._EXPECTED_NODE_SHA256
    assert selected.auxiliary == str(toolchains._EXPECTED_TYPESCRIPT_LAUNCHER)
    assert selected.auxiliary_sha256 == toolchains._EXPECTED_TYPESCRIPT_LAUNCHER_SHA256
    assert {
        "typescript-toolchain-closure-schema=v1",
        f"typescript-package-root={toolchains._EXPECTED_TYPESCRIPT_ROOT}",
        f"typescript-closure-sha256={toolchains._EXPECTED_TYPESCRIPT_CLOSURE_SHA256}",
        f"typescript-closure-file-count={toolchains._EXPECTED_TYPESCRIPT_CLOSURE_FILE_COUNT}",
        f"typescript-closure-bytes={toolchains._EXPECTED_TYPESCRIPT_CLOSURE_BYTES}",
        f"typescript-source-manifest-sha256={toolchains._EXPECTED_TYPESCRIPT_SOURCE_MANIFEST_SHA256}",
        f"typescript-standard-library-file-count={toolchains._EXPECTED_TYPESCRIPT_LIBRARY_FILE_COUNT}",
        f"typescript-compiler-sha256={toolchains._EXPECTED_TYPESCRIPT_COMPILER_SHA256}",
        f"typescript-parser-sha256={toolchains._EXPECTED_TYPESCRIPT_PARSER_SHA256}",
        f"node-closure-sha256={node_closure['sha256']}",
        f"node-closure-profile={closure_profile}",
        "typescript-compiler-runtime-semantic-soundness=NOT_RUN",
    } <= set(selected.profile)
    assert (
        toolchains._output(
            [selected.auxiliary, "--version"],
            executable_dirs=(Path(selected.executable).parent,),
        )
        == "Version 5.9.2"
    )


def test_typescript_full_stdlib_compiles_and_validates_es2022_with_scrubbed_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    source = tmp_path / "identity.ts"
    source.write_text(
        "export function identity(value: number): number { return value; }\n",
        encoding="utf-8",
    )
    semantic = analyze(source, "typescript", "identity")

    report = validate(
        emit(semantic, "typescript"),
        "typescript",
        semantic.functions[0],
        [{"args": [1.5], "expected": 1.5}],
        tmp_path / "validated",
    )

    assert report["status"] == "PASSED"
    assert report["case_count"] == 1


def test_node_closure_binds_every_component_edge_and_explicit_system_boundary(
    node_closure: dict[str, object],
) -> None:
    closure_profile = toolchains._verify_node_dependency_closure(node_closure)
    manifest = node_closure["manifest"]
    assert isinstance(manifest, dict)
    components = manifest["components"]
    edges = manifest["edges"]
    system_edges = manifest["system_edges"]
    assert isinstance(components, list)
    assert isinstance(edges, list)
    assert isinstance(system_edges, list)

    expected_profile = next(
        profile
        for profile in toolchains._EXPECTED_NODE_CLOSURE_PROFILES
        if profile["profile"] == closure_profile
    )
    assert node_closure["sha256"] == expected_profile["sha256"]
    assert len(components) == toolchains._EXPECTED_NODE_CLOSURE_COMPONENT_COUNT
    assert len(edges) == toolchains._EXPECTED_NODE_CLOSURE_EDGE_COUNT
    assert len(system_edges) == toolchains._EXPECTED_NODE_CLOSURE_SYSTEM_EDGE_COUNT
    assert node_closure["bytes"] == expected_profile["bytes"]
    assert node_closure["system_edge_sha256"] == toolchains._EXPECTED_NODE_SYSTEM_EDGE_SHA256
    assert manifest["system_content_boundary"] == {
        "scope": "dyld-shared-cache-and-system-libraries",
        "status": "NOT_RUN",
    }
    assert all(
        set(component)
        == {
            "resolved_path",
            "bytes",
            "sha256",
            "mode",
            "uid",
            "gid",
            "nlink",
        }
        for component in components
    )
    assert all(str(component["resolved_path"]).startswith("/opt/homebrew/Cellar/") for component in components)
    assert all(component["nlink"] == 1 for component in components)
    assert any(
        edge
        == {
            "loader": str(toolchains._EXPECTED_NODE_EXECUTABLE),
            "load_path": "@rpath/libnode.147.dylib",
            "resolved_path": str(toolchains._EXPECTED_NODE_LIBNODE),
        }
        for edge in edges
    )
    assert any(
        component["resolved_path"] == str(toolchains._EXPECTED_NODE_LIBADA)
        and component["sha256"] == expected_profile["libada_sha256"]
        and component["bytes"] == expected_profile["libada_bytes"]
        for component in components
    )


def test_node_closure_rejects_libnode_content_drift_even_with_recomputed_identity(
    node_closure: dict[str, object],
) -> None:
    manifest = copy.deepcopy(node_closure["manifest"])
    assert isinstance(manifest, dict)
    components = manifest["components"]
    assert isinstance(components, list)
    libnode = next(
        component for component in components if component["resolved_path"] == str(toolchains._EXPECTED_NODE_LIBNODE)
    )
    libnode["sha256"] = "0" * 64
    forged = toolchains._node_closure_identity(manifest)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_NODE_LIBNODE_MISMATCH"):
        toolchains._verify_node_dependency_closure(forged)


def test_node_closure_rejects_executable_drift_even_with_recomputed_identity(
    node_closure: dict[str, object],
) -> None:
    manifest = copy.deepcopy(node_closure["manifest"])
    assert isinstance(manifest, dict)
    components = manifest["components"]
    assert isinstance(components, list)
    executable = next(
        component for component in components if component["resolved_path"] == str(toolchains._EXPECTED_NODE_EXECUTABLE)
    )
    executable["sha256"] = "1" * 64
    forged = toolchains._node_closure_identity(manifest)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_NODE_EXECUTABLE_MISMATCH"):
        toolchains._verify_node_dependency_closure(forged)


def test_node_closure_rejects_libada_content_drift_even_with_recomputed_identity(
    node_closure: dict[str, object],
) -> None:
    manifest = copy.deepcopy(node_closure["manifest"])
    assert isinstance(manifest, dict)
    components = manifest["components"]
    assert isinstance(components, list)
    libada = next(
        component
        for component in components
        if component["resolved_path"] == str(toolchains._EXPECTED_NODE_LIBADA)
    )
    libada["sha256"] = "4" * 64
    forged = toolchains._node_closure_identity(manifest)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_NODE_LIBADA_MISMATCH"):
        toolchains._verify_node_dependency_closure(forged)


@pytest.mark.parametrize("profile", toolchains._EXPECTED_NODE_CLOSURE_PROFILES)
def test_node_closure_accepts_each_complete_declared_libada_profile(
    node_closure: dict[str, object],
    profile: dict[str, str | int],
) -> None:
    manifest = copy.deepcopy(node_closure["manifest"])
    assert isinstance(manifest, dict)
    components = manifest["components"]
    assert isinstance(components, list)
    libada = next(
        component
        for component in components
        if component["resolved_path"] == str(toolchains._EXPECTED_NODE_LIBADA)
    )
    libada["sha256"] = profile["libada_sha256"]
    libada["bytes"] = profile["libada_bytes"]
    candidate = toolchains._node_closure_identity(manifest)

    assert candidate["sha256"] == profile["sha256"]
    assert candidate["bytes"] == profile["bytes"]
    assert toolchains._verify_node_dependency_closure(candidate) == profile["profile"]


def test_ci_installer_and_runtime_share_the_exact_libada_profile_matrix() -> None:
    installer = (
        Path(__file__).resolve().parents[3]
        / "scripts/toolchains/install_polyglot_route_ci_toolchains.sh"
    ).read_text(encoding="utf-8")
    for profile in toolchains._EXPECTED_NODE_CLOSURE_PROFILES:
        identity = f"{profile['libada_bytes']}:{profile['libada_sha256']}"
        assert identity in installer
        assert str(profile["profile"]) in installer


def test_node_closure_rejects_self_consistent_non_libnode_forgery(
    node_closure: dict[str, object],
) -> None:
    manifest = copy.deepcopy(node_closure["manifest"])
    assert isinstance(manifest, dict)
    components = manifest["components"]
    assert isinstance(components, list)
    dependency = next(
        component for component in components if component["resolved_path"].endswith("libsimdutf.34.0.0.dylib")
    )
    dependency["sha256"] = "f" * 64
    forged = toolchains._node_closure_identity(manifest)
    assert forged["sha256"] != node_closure["sha256"]

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_NODE_CLOSURE_MISMATCH"):
        toolchains._verify_node_dependency_closure(forged)


def test_node_cached_topology_skips_otool_but_rebinds_every_component(
    node_closure: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchains._verify_node_dependency_closure(node_closure)
    otool_calls = 0
    binding_calls = 0
    original_binding = toolchains._node_file_binding

    def reject_otool(_flag: str, _path: Path) -> list[str]:
        nonlocal otool_calls
        otool_calls += 1
        raise AssertionError("validated topology cache must not rerun otool")

    def count_binding(path: Path, failure: str) -> dict[str, str | int]:
        nonlocal binding_calls
        binding_calls += 1
        return original_binding(path, failure)

    monkeypatch.setattr(toolchains, "_node_otool_lines", reject_otool)
    monkeypatch.setattr(toolchains, "_node_file_binding", count_binding)
    started = time.monotonic()
    cached = toolchains._node_dependency_closure()
    elapsed = time.monotonic() - started
    toolchains._verify_node_dependency_closure(cached)

    assert cached == node_closure
    assert otool_calls == 0
    assert binding_calls == toolchains._EXPECTED_NODE_CLOSURE_COMPONENT_COUNT
    assert elapsed < 5.0


def test_node_cached_topology_rejects_self_consistent_poison(
    node_closure: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchains._verify_node_dependency_closure(node_closure)
    poisoned = copy.deepcopy(toolchains._NODE_TOPOLOGY_CACHE)
    assert isinstance(poisoned, dict)
    system_edges = poisoned["system_edges"]
    component_paths = poisoned["component_paths"]
    assert isinstance(system_edges, list)
    assert isinstance(component_paths, list)
    system_edges.append(
        {
            "loader": component_paths[0],
            "load_path": "/usr/lib/libSelfConsistentForgery.dylib",
        }
    )
    monkeypatch.setattr(toolchains, "_NODE_TOPOLOGY_CACHE", poisoned)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_MISMATCH"):
        toolchains._node_dependency_closure()


def test_node_cached_topology_still_rejects_component_content_drift(
    node_closure: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchains._verify_node_dependency_closure(node_closure)
    original_binding = toolchains._node_file_binding

    def forged_binding(path: Path, failure: str) -> dict[str, str | int]:
        record = original_binding(path, failure)
        if path.name.startswith("libsimdutf"):
            record["sha256"] = "0" * 64
        return record

    monkeypatch.setattr(toolchains, "_node_file_binding", forged_binding)
    cached = toolchains._node_dependency_closure()

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_NODE_CLOSURE_MISMATCH"):
        toolchains._verify_node_dependency_closure(cached)


@pytest.mark.parametrize(
    ("role", "failure"),
    [
        ("launcher", "EXACT_TOOLCHAIN_TYPESCRIPT_LAUNCHER_MISMATCH"),
        ("parser", "EXACT_TOOLCHAIN_TYPESCRIPT_PARSER_MISMATCH"),
    ],
)
def test_typescript_closure_rejects_tsc_or_parser_drift_with_recomputed_identity(
    typescript_closure: dict[str, object],
    role: str,
    failure: str,
) -> None:
    manifest = copy.deepcopy(typescript_closure["manifest"])
    assert isinstance(manifest, dict)
    files = manifest["files"]
    assert isinstance(files, list)
    selected = next(item for item in files if item["role"] == role)
    selected["sha256"] = "2" * 64
    forged = toolchains._typescript_closure_identity(manifest)

    with pytest.raises(RouteError, match=failure):
        toolchains._verify_typescript_compiler_closure(forged)


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_typescript_closure_rejects_missing_or_tampered_stdlib_with_recomputed_identity(
    typescript_closure: dict[str, object],
    mutation: str,
) -> None:
    manifest = copy.deepcopy(typescript_closure["manifest"])
    assert isinstance(manifest, dict)
    files = manifest["files"]
    assert isinstance(files, list)
    selected = next(
        item
        for item in files
        if item["role"] == "standard-library:lib.es2022.full.d.ts"
    )
    if mutation == "missing":
        files.remove(selected)
    else:
        selected["sha256"] = "3" * 64
    forged = toolchains._typescript_closure_identity(manifest)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_TYPESCRIPT_STDLIB_MISMATCH"):
        toolchains._verify_typescript_compiler_closure(forged)


def test_node_rpath_does_not_skip_an_existing_unsafe_earlier_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loader = tmp_path / "bin" / "node"
    loader.parent.mkdir()
    loader.write_bytes(b"loader")
    unsafe_root = tmp_path / "unsafe"
    safe_root = tmp_path / "safe"
    unsafe_root.mkdir()
    safe_root.mkdir()
    (unsafe_root / "libnode.dylib").write_bytes(b"unsafe")
    (safe_root / "libnode.dylib").write_bytes(b"safe")
    monkeypatch.setattr(
        toolchains,
        "_node_otool_rpaths",
        lambda path: (str(unsafe_root), str(safe_root)),
    )

    def resolve(candidate: Path) -> Path:
        if candidate == unsafe_root / "libnode.dylib":
            raise RouteError("TEST_NODE_EARLY_RPATH_UNSAFE")
        return candidate

    monkeypatch.setattr(toolchains, "_node_resolve_homebrew_path", resolve)

    with pytest.raises(RouteError, match="TEST_NODE_EARLY_RPATH_UNSAFE"):
        toolchains._node_resolve_dependency("@rpath/libnode.dylib", loader)


@pytest.mark.parametrize("unsafe_kind", ["symlink", "writable", "hardlink"])
def test_node_component_binding_rejects_symlink_writable_or_multiply_linked_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_kind: str,
) -> None:
    cellar = tmp_path / "Cellar"
    library = cellar / "dependency" / "1.0.0" / "lib"
    library.mkdir(parents=True)
    payload = library / "payload.dylib"
    payload.write_bytes(b"fixed dependency")
    candidate = payload
    if unsafe_kind == "symlink":
        candidate = library / "linked.dylib"
        candidate.symlink_to(payload.name)
    elif unsafe_kind == "writable":
        payload.chmod(0o664)
    else:
        (library / "second-name.dylib").hardlink_to(payload)
    monkeypatch.setattr(toolchains, "_EXPECTED_HOMEBREW_CELLAR", cellar)

    with pytest.raises(RouteError, match="TEST_NODE_COMPONENT_UNSAFE"):
        toolchains._node_file_binding(candidate, "TEST_NODE_COMPONENT_UNSAFE")
