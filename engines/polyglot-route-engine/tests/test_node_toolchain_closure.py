from __future__ import annotations

import copy
import hashlib
import json
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


def test_node26_profile_registry_is_complete_and_includes_the_hosted_image() -> None:
    profiles = toolchains._validated_node_profiles()
    assert [profile["profile"] for profile in profiles] == [
        "homebrew-node26-libada-77917065434c-616512",
        "homebrew-node26-libada-e4b04b323411-613248",
        "homebrew-node26-libada-b39ba5c76cfa-598704",
        "github-macos26-20260728-node26-b39ba5c76cfa-598704",
        "github-macos26-20260831-node26-b39ba5c76cfa-598704",
    ]
    assert all(set(profile) == toolchains._NODE26_PROFILE_FIELDS for profile in profiles)
    hosted = profiles[-1]
    assert hosted == {
        "profile": "github-macos26-20260831-node26-b39ba5c76cfa-598704",
        "sha256": "8dcb3a6d571df541adccec54feca18ec6a4074d232d68397ffca9bdec0b5ce07",
        "bytes": 119_975_888,
        "qualification_host": "github-macos-26-arm64@20260831.0337.3",
        "node_version": "v26.0.0",
        "platform": "darwin",
        "arch": "arm64",
        "topology_sha256": "4d2426eac17276f2bc4ec386d85660ecf5896cb4746fc1de87fbe4d7f2551e82",
        "component_count": 25,
        "edge_count": 49,
        "system_edge_count": 43,
        "system_edge_sha256": "495f6ba5eaf5ba5b2c1fa40a2325679d1823b279b06ed283a520706f02b28444",
        "closure_sha256": "8dcb3a6d571df541adccec54feca18ec6a4074d232d68397ffca9bdec0b5ce07",
        "closure_bytes": 119_975_888,
        "node_sha256": "542a44a023d27e626d79fbd646f3e2b898bd291b96028b3644795f21b5a43bc9",
        "node_bytes": 50_672,
        "libnode_sha256": "980e876ab7f53bacc6262e77c4ac96f60ca3bac4dd241b0cc6cdc945c4ecaf88",
        "libnode_bytes": 70_661_840,
        "libada_sha256": "b39ba5c76cfa9e8d7a37b51daf937414316b671f51360daae62b9885e9d089f8",
        "libada_bytes": 598_704,
        "process_versions": toolchains._NODE26_PROCESS_VERSIONS,
        "process_versions_sha256": toolchains._NODE26_PROCESS_VERSIONS_SHA256,
    }
    assert all(
        toolchains.node_closure_profile_id(str(profile["closure_sha256"]))
        == profile["profile"]
        for profile in profiles
    )


@pytest.mark.parametrize("profile", toolchains._EXPECTED_NODE_CLOSURE_PROFILES)
def test_node_runtime_identity_is_bound_to_the_selected_complete_profile(
    profile: dict[str, str | int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_identity = json.dumps(
        {
            "execPath": str(toolchains._EXPECTED_NODE_EXECUTABLE),
            "platform": profile["platform"],
            "arch": profile["arch"],
            "versions": json.loads(str(profile["process_versions"])),
        },
        separators=(",", ":"),
    )
    outputs = iter((str(profile["node_version"]), observed_identity))
    monkeypatch.setattr(toolchains, "_output", lambda _command: next(outputs))

    identity = toolchains._node_runtime_identity(str(profile["profile"]))

    assert identity["profile"] == profile["profile"]
    assert identity["process_versions_sha256"] == profile["process_versions_sha256"]


def test_node_runtime_identity_rejects_process_from_another_complete_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_id = "github-macos26-20260728-node26-b39ba5c76cfa-598704"
    profiles = copy.deepcopy(toolchains._EXPECTED_NODE_CLOSURE_PROFILES)
    hosted = next(profile for profile in profiles if profile["profile"] == profile_id)
    hosted_process = '{"node":"26.0.0","profile":"hosted-only"}'
    hosted["process_versions"] = hosted_process
    hosted["process_versions_sha256"] = hashlib.sha256(
        hosted_process.encode("ascii")
    ).hexdigest()
    monkeypatch.setattr(toolchains, "_EXPECTED_NODE_CLOSURE_PROFILES", profiles)
    legacy = toolchains._EXPECTED_NODE_CLOSURE_PROFILES[0]
    observed_identity = json.dumps(
        {
            "execPath": str(toolchains._EXPECTED_NODE_EXECUTABLE),
            "platform": legacy["platform"],
            "arch": legacy["arch"],
            "versions": json.loads(str(legacy["process_versions"])),
        },
        separators=(",", ":"),
    )
    outputs = iter((str(hosted["node_version"]), observed_identity))
    monkeypatch.setattr(toolchains, "_output", lambda _command: next(outputs))

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_MISMATCH:node-runtime"):
        toolchains._node_runtime_identity(profile_id)


def _synthetic_profile_identity(
    node_profile: dict[str, str | int],
    libnode_profile: dict[str, str | int],
    libada_profile: dict[str, str | int],
    summary_profile: dict[str, str | int],
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "components": [
            {
                "resolved_path": str(toolchains._EXPECTED_NODE_EXECUTABLE),
                "sha256": node_profile["node_sha256"],
                "bytes": node_profile["node_bytes"],
            },
            {
                "resolved_path": str(toolchains._EXPECTED_NODE_LIBNODE),
                "sha256": libnode_profile["libnode_sha256"],
                "bytes": libnode_profile["libnode_bytes"],
            },
            {
                "resolved_path": str(toolchains._EXPECTED_NODE_LIBADA),
                "sha256": libada_profile["libada_sha256"],
                "bytes": libada_profile["libada_bytes"],
            },
        ]
    }
    return {
        "manifest": manifest,
        "sha256": summary_profile["closure_sha256"],
        "topology_sha256": summary_profile["topology_sha256"],
        "component_count": summary_profile["component_count"],
        "edge_count": summary_profile["edge_count"],
        "system_edge_count": summary_profile["system_edge_count"],
        "bytes": summary_profile["closure_bytes"],
        "system_edge_sha256": summary_profile["system_edge_sha256"],
    }


def test_node_profile_selection_rejects_cross_profile_component_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = toolchains._EXPECTED_NODE_CLOSURE_PROFILES[0]
    hosted = toolchains._EXPECTED_NODE_CLOSURE_PROFILES[-1]
    mixed = _synthetic_profile_identity(legacy, hosted, legacy, legacy)
    monkeypatch.setattr(toolchains, "_node_closure_identity", lambda _manifest: mixed)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_NODE_LIBNODE_MISMATCH"):
        toolchains._verify_node_dependency_closure(mixed)


def test_node_profile_selection_rejects_cross_profile_topology_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = toolchains._EXPECTED_NODE_CLOSURE_PROFILES[2]
    hosted = toolchains._EXPECTED_NODE_CLOSURE_PROFILES[-1]
    mixed = _synthetic_profile_identity(legacy, legacy, legacy, hosted)
    monkeypatch.setattr(toolchains, "_node_closure_identity", lambda _manifest: mixed)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_NODE_CLOSURE_MISMATCH"):
        toolchains._verify_node_dependency_closure(mixed)


def test_node_profile_selection_rejects_previous_manifest_with_current_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_hosted = toolchains._EXPECTED_NODE_CLOSURE_PROFILES[-2]
    current_hosted = toolchains._EXPECTED_NODE_CLOSURE_PROFILES[-1]
    previous_identity = _synthetic_profile_identity(
        previous_hosted,
        previous_hosted,
        previous_hosted,
        previous_hosted,
    )
    claimed_current_identity = {
        **previous_identity,
        "sha256": current_hosted["closure_sha256"],
    }
    monkeypatch.setattr(
        toolchains,
        "_node_closure_identity",
        lambda _manifest: previous_identity,
    )

    with pytest.raises(
        RouteError,
        match="EXACT_TOOLCHAIN_NODE_CLOSURE_IDENTITY_INVALID",
    ):
        toolchains._verify_node_dependency_closure(claimed_current_identity)


def test_node_dependency_closure_rejects_cached_topology_identity_mix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(toolchains.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(toolchains.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        toolchains,
        "_node_cached_topology",
        lambda: {
            "sha256": "a" * 64,
            "topology": {
                "component_paths": [],
                "edges": [],
                "system_edges": [],
            },
        },
    )
    monkeypatch.setattr(
        toolchains,
        "_node_closure_identity",
        lambda _manifest: {"topology_sha256": "b" * 64},
    )

    with pytest.raises(
        RouteError,
        match="EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_MISMATCH",
    ):
        toolchains._node_dependency_closure()


def test_javascript_exact_toolchain_binds_recursive_node26_closure_without_ambient_path(
    monkeypatch: pytest.MonkeyPatch,
    node_closure: dict[str, object],
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    selected = toolchains.exact_toolchain("javascript")
    closure_profile = toolchains._verify_node_dependency_closure(node_closure)
    profile = toolchains._node_profile(closure_profile)

    assert selected.executable == str(toolchains._EXPECTED_NODE_EXECUTABLE)
    assert selected.executable_sha256 == profile["node_sha256"]
    assert {
        "node-toolchain-closure-schema=v1",
        f"node-install-root={toolchains._EXPECTED_NODE_ROOT}",
        f"node-closure-sha256={node_closure['sha256']}",
        f"node-closure-profile={closure_profile}",
        f"node-topology-sha256={profile['topology_sha256']}",
        f"node-closure-component-count={profile['component_count']}",
        f"node-closure-edge-count={profile['edge_count']}",
        f"node-closure-system-edge-count={profile['system_edge_count']}",
        f"node-closure-bytes={node_closure['bytes']}",
        f"node-system-edge-sha256={profile['system_edge_sha256']}",
        f"libnode-sha256={profile['libnode_sha256']}",
        f"libnode-bytes={profile['libnode_bytes']}",
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
    profile = toolchains._node_profile(closure_profile)

    assert selected.executable == str(toolchains._EXPECTED_NODE_EXECUTABLE)
    assert selected.executable_sha256 == profile["node_sha256"]
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
        f"node-topology-sha256={profile['topology_sha256']}",
        "typescript-compiler-runtime-semantic-soundness=NOT_RUN",
    } <= set(selected.profile)
    assert (
        toolchains._output(
            [selected.auxiliary, "--version"],
            executable_dirs=(Path(selected.executable).parent,),
        )
        == "Version 5.9.2"
    )


def test_typescript_closure_identity_is_relocatable_after_live_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        toolchains,
        "_EXPECTED_TYPESCRIPT_CACHE_ANCHOR",
        tmp_path,
    )
    identities: list[dict[str, object]] = []
    manifests: list[dict[str, object]] = []
    roots: list[Path] = []
    try:
        for name in ("runner-a", "runner-b"):
            root = tmp_path / name / "typescript" / "5.9.2" / "sha256-capture"
            library = root / "lib"
            binary = root / "bin"
            library.mkdir(parents=True)
            binary.mkdir()
            declaration = library / "lib.example.d.ts"
            declaration.write_text("declare const example: number;\n", encoding="utf-8")
            declaration.chmod(0o444)
            binary.chmod(0o555)
            library.chmod(0o555)
            root.chmod(0o555)
            roots.append(root)

            monkeypatch.setattr(toolchains, "_EXPECTED_TYPESCRIPT_ROOT", root)
            manifest: dict[str, object] = {
                "schema_version": 2,
                "kind": "elmos.typescript-5.9.2-full-stdlib-compiler-closure",
                "package_root": toolchains._typescript_package_root_binding(),
                "directories": [
                    toolchains._typescript_package_directory_binding(relative)
                    for relative in ("bin", "lib")
                ],
                "files": [
                    toolchains._typescript_file_binding(
                        declaration,
                        "standard-library:lib.example.d.ts",
                    )
                ],
                "semantic_soundness": "NOT_RUN",
            }
            manifests.append(manifest)
            identities.append(toolchains._typescript_closure_identity(manifest))

        assert manifests[0]["package_root"] != manifests[1]["package_root"]
        assert identities[0]["sha256"] == identities[1]["sha256"]
        assert identities[0]["bytes"] == identities[1]["bytes"]
        assert identities[0]["file_count"] == identities[1]["file_count"] == 1
        assert identities[0]["manifest"] is manifests[0]
        projected = toolchains._canonical_typescript_closure_manifest(manifests[1])
        raw_identity = toolchains._raw_typescript_closure_identity(projected)
        assert raw_identity["sha256"] == identities[1]["sha256"]
        assert raw_identity["file_count"] == identities[1]["file_count"]
        assert raw_identity["bytes"] == identities[1]["bytes"]
        package = projected["package_root"]
        directories = projected["directories"]
        files = projected["files"]
        assert isinstance(package, dict)
        assert isinstance(directories, list)
        assert isinstance(files, list)
        assert package == {
            "root": str(toolchains._TYPESCRIPT_IDENTITY_CANONICAL_ROOT),
            "mode": "0555",
            "uid": toolchains._TYPESCRIPT_IDENTITY_CANONICAL_UID,
            "gid": toolchains._TYPESCRIPT_IDENTITY_CANONICAL_GID,
            "nlink": toolchains._TYPESCRIPT_IDENTITY_CANONICAL_PACKAGE_NLINK,
        }
        assert [item["nlink"] for item in directories] == [3, 107]
        assert files[0]["resolved_path"] == str(
            toolchains._TYPESCRIPT_IDENTITY_CANONICAL_ROOT
            / "lib/lib.example.d.ts"
        )
    finally:
        for root in roots:
            for path in (root / "bin", root / "lib"):
                path.chmod(0o755)
            for path in (root / "lib").glob("*"):
                path.chmod(0o644)
            root.chmod(0o755)


def test_typescript_canonical_identity_rejects_same_size_content_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "typescript" / "5.9.2" / "sha256-capture"
    library = root / "lib"
    binary = root / "bin"
    library.mkdir(parents=True)
    binary.mkdir()
    declaration = library / "lib.example.d.ts"
    declaration.write_bytes(b"declare const answer: 1;\n")
    declaration.chmod(0o444)
    binary.chmod(0o555)
    library.chmod(0o555)
    root.chmod(0o555)
    monkeypatch.setattr(toolchains, "_EXPECTED_TYPESCRIPT_CACHE_ANCHOR", tmp_path)
    monkeypatch.setattr(toolchains, "_EXPECTED_TYPESCRIPT_ROOT", root)
    manifest: dict[str, object] = {
        "schema_version": 2,
        "kind": "elmos.typescript-5.9.2-full-stdlib-compiler-closure",
        "package_root": toolchains._typescript_package_root_binding(),
        "directories": [
            toolchains._typescript_package_directory_binding(relative)
            for relative in ("bin", "lib")
        ],
        "files": [
            toolchains._typescript_file_binding(
                declaration,
                "standard-library:lib.example.d.ts",
            )
        ],
        "semantic_soundness": "NOT_RUN",
    }
    declaration.chmod(0o644)
    declaration.write_bytes(b"declare const answer: 2;\n")
    declaration.chmod(0o444)

    with pytest.raises(
        RouteError,
        match="EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID",
    ):
        toolchains._typescript_closure_identity(manifest)

    declaration.chmod(0o644)
    binary.chmod(0o755)
    library.chmod(0o755)
    root.chmod(0o755)


@pytest.mark.parametrize("placement", ["package-owner", "directory-links", "file-owner"])
def test_typescript_canonical_identity_rejects_forged_live_placement(
    typescript_closure: dict[str, object],
    placement: str,
) -> None:
    manifest = copy.deepcopy(typescript_closure["manifest"])
    assert isinstance(manifest, dict)
    package = manifest["package_root"]
    directories = manifest["directories"]
    files = manifest["files"]
    assert isinstance(package, dict)
    assert isinstance(directories, list)
    assert isinstance(files, list)
    if placement == "package-owner":
        package["uid"] = int(package["uid"]) + 1
    elif placement == "directory-links":
        directories[0]["nlink"] = int(directories[0]["nlink"]) + 1
    else:
        files[0]["uid"] = int(files[0]["uid"]) + 1

    with pytest.raises(
        RouteError,
        match="EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID",
    ):
        toolchains._typescript_closure_identity(manifest)


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
    assert node_closure["sha256"] == expected_profile["closure_sha256"]
    assert node_closure["topology_sha256"] == expected_profile["topology_sha256"]
    assert len(components) == expected_profile["component_count"]
    assert len(edges) == expected_profile["edge_count"]
    assert len(system_edges) == expected_profile["system_edge_count"]
    assert node_closure["bytes"] == expected_profile["closure_bytes"]
    assert node_closure["system_edge_sha256"] == expected_profile["system_edge_sha256"]
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


@pytest.mark.parametrize(
    "profile",
    tuple(
        profile
        for profile in toolchains._EXPECTED_NODE_CLOSURE_PROFILES
        if str(profile["qualification_host"]).startswith("legacy-")
    ),
)
def test_node_closure_accepts_each_complete_legacy_profile(
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

    assert candidate["sha256"] == profile["closure_sha256"]
    assert candidate["bytes"] == profile["closure_bytes"]
    assert toolchains._verify_node_dependency_closure(candidate) == profile["profile"]


def test_ci_installer_preserves_the_legacy_libada_profile_matrix() -> None:
    installer = (
        Path(__file__).resolve().parents[3]
        / "scripts/toolchains/install_polyglot_route_ci_toolchains.sh"
    ).read_text(encoding="utf-8")
    for profile in toolchains._EXPECTED_NODE_CLOSURE_PROFILES:
        if not str(profile["qualification_host"]).startswith("legacy-"):
            continue
        identity = f"{profile['libada_bytes']}:{profile['libada_sha256']}"
        assert identity in installer
        assert str(profile["profile"]) in installer


def test_ci_installer_pins_every_node_formula_for_each_host_profile() -> None:
    installer = (
        Path(__file__).resolve().parents[3]
        / "scripts/toolchains/install_polyglot_route_ci_toolchains.sh"
    ).read_text(encoding="utf-8")
    closure_body = installer.split("install_pinned_node26_closure() {", 1)[1].split(
        "\npreflight_exact_route_toolchain() {", 1
    )[0]
    formula_table = closure_body.rsplit("done <<EOF", 1)[1].split("\nEOF", 1)[0]
    observed = {
        tuple(line.split("|", 1))
        for line in formula_table.splitlines()
        if "|" in line
    }
    expected = {
        ("fmt", "12.2.0"),
        ("ca-certificates", "2026-08-13"),
        ("readline", "8.3.3"),
        ("lz4", "1.10.0"),
        ("xz", "5.8.3"),
        ("brotli", "1.2.0"),
        ("c-ares", "1.34.8"),
        ("hdrhistogram_c", "${hdrhistogram_version}"),
        ("icu4c@78", "78.3"),
        ("libnghttp2", "1.69.0"),
        ("libnghttp3", "1.18.0"),
        ("libngtcp2", "1.25.0"),
        ("libuv", "1.52.1"),
        ("merve", "1.2.2_1"),
        ("nbytes", "0.1.4"),
        ("openssl@3", "3.6.3"),
        ("simdjson", "4.6.4"),
        ("simdutf", "9.0.0"),
        ("sqlite", "3.53.3"),
        ("uvwasi", "0.0.23"),
        ("zstd", "1.5.7_1"),
        ("ada-url", "3.4.4"),
        ("llhttp", "9.4.1"),
        ("node", "26.0.0"),
    }
    assert observed == expected
    assert "HOMEBREW_NO_INSTALL_UPGRADE=1" in installer
    assert "brew install \\\n    brotli" not in closure_body
    assert (
        'HOST_PROFILE="${ImageVersion:-}:$(sw_vers -productVersion):'
        '$(sw_vers -buildVersion)"'
        in installer
    )
    assert '"20260728.0273.1:26.5.2:25F84"' in installer
    assert '"20260831.0337.3:26.6.2:25G83"' in installer

    frontend = installer.split('if [[ "${CI_PROFILE}" == "frontend-formal" ]]', 1)[
        1
    ].split("\n  exit 0\nfi", 1)[0]
    assert frontend.index("preflight_exact_route_toolchain javascript") < frontend.index(
        '>>"${GITHUB_PATH}"'
    )
    full_preflight = installer.rindex("preflight_exact_route_toolchain javascript")
    environment_export = installer.index('} >>"${GITHUB_ENV}"', full_preflight)
    assert full_preflight < environment_export


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
        ("launcher", "EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID"),
        ("parser", "EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID"),
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
    with pytest.raises(RouteError, match=failure):
        toolchains._typescript_closure_identity(manifest)


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
    expected_failure = (
        "EXACT_TOOLCHAIN_TYPESCRIPT_STDLIB_MISMATCH"
        if mutation == "missing"
        else "EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID"
    )
    with pytest.raises(RouteError, match=expected_failure):
        forged = toolchains._typescript_closure_identity(manifest)
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
