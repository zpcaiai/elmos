from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from elmos_polyglot_route import native, toolchains
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze, swift_analyzer_build_receipt
from elmos_polyglot_route.validation import validate_source


def test_minimal_subprocess_environment_drops_all_supported_injection_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hostile_root = tmp_path / "hostile"
    hostile = {
        "JAVA_TOOL_OPTIONS": f"-javaagent:{hostile_root / 'agent.jar'}",
        "_JAVA_OPTIONS": f"-Xbootclasspath/a:{hostile_root / 'classes'}",
        "JDK_JAVA_OPTIONS": f"--class-path={hostile_root / 'classes'}",
        "CPATH": str(hostile_root / "headers"),
        "CPLUS_INCLUDE_PATH": str(hostile_root / "cpp-headers"),
        "OBJC_INCLUDE_PATH": str(hostile_root / "objc-headers"),
        "SDKROOT": str(hostile_root / "fake-sdk"),
        "DEVELOPER_DIR": str(hostile_root / "fake-xcode"),
        "TOOLCHAINS": "fake",
        "SWIFT_EXEC": str(hostile_root / "fake-swift"),
        "SWIFTPM_MODULECACHE_OVERRIDE": str(hostile_root / "fake-cache"),
        "CC": str(hostile_root / "fake-cc"),
        "CXX": str(hostile_root / "fake-cxx"),
        "DYLD_INSERT_LIBRARIES": str(hostile_root / "fake.dylib"),
        "LD_LIBRARY_PATH": str(hostile_root / "fake-libs"),
        "LIBRARY_PATH": str(hostile_root / "fake-libs"),
        "PYTHONPATH": str(hostile_root / "fake-python"),
        "VIRTUAL_ENV": str(hostile_root / "fake-venv"),
        "DOTNET_ROOT": str(hostile_root / "fake-dotnet"),
        "DOTNET_ADDITIONAL_DEPS": str(hostile_root / "fake-dotnet-deps"),
        "DOTNET_SHARED_STORE": str(hostile_root / "fake-dotnet-store"),
        "DOTNET_STARTUP_HOOKS": str(hostile_root / "fake-dotnet-hook.dll"),
        "MSBuildSDKsPath": str(hostile_root / "fake-msbuild-sdks"),
    }
    for key, value in hostile.items():
        monkeypatch.setenv(key, value)
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    home.mkdir()
    scratch.mkdir()

    environment = toolchains.sanitized_subprocess_env(home=home, temp_dir=scratch)

    assert not set(hostile).intersection(environment)
    assert environment["HOME"] == str(home.resolve())
    assert environment["TMPDIR"] == str(scratch.resolve())
    assert environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert environment["PYTHONNOUSERSITE"] == "1"


def test_java_declared_home_cannot_replace_the_pinned_distribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "fake-jdk"
    (fake / "bin").mkdir(parents=True)
    for name in ("java", "javac"):
        path = fake / "bin" / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o700)
    monkeypatch.setenv("ELMOS_JAVA21_HOME", str(fake))

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_DECLARED_HOME_MISMATCH:java"):
        toolchains.exact_toolchain("java")


def test_java_toolchain_binds_launchers_runtime_modules_and_bundle_signature() -> None:
    selected = toolchains.exact_toolchain("java")

    assert selected.executable_sha256 == toolchains._EXPECTED_JAVA_SHA256
    assert selected.auxiliary_sha256 == toolchains._EXPECTED_JAVAC_SHA256
    assert f"jdk-cdhash-full={toolchains._EXPECTED_JAVA_BUNDLE_CDHASH_FULL}" in selected.profile
    assert f"jdk-modules-sha256={toolchains._EXPECTED_JAVA_MODULES_SHA256}" in selected.profile
    assert f"libjvm-sha256={toolchains._EXPECTED_JAVA_JVM_SHA256}" in selected.profile


def test_typescript_toolchain_resolves_pinned_node_in_minimal_environment() -> None:
    selected = toolchains.exact_toolchain("typescript")

    assert selected.version == "5.9.2 / Node 26.0.0"
    assert Path(selected.executable).name == "node"
    assert selected.auxiliary is not None
    assert Path(selected.auxiliary).name == "tsc"


def test_csharp_toolchain_binds_full_console_build_and_runtime_bundle() -> None:
    selected = toolchains.exact_toolchain("csharp")

    assert selected.executable == str(toolchains._EXPECTED_DOTNET_MUXER)
    assert selected.executable_sha256 == toolchains._EXPECTED_DOTNET_MUXER_SHA256
    expected_fields = {
        "dotnet-profile-schema=v1",
        "sdk-version=10.0.301",
        "hostfxr-version=10.0.9",
        "runtime-version=10.0.9",
        "rid=osx-arm64",
        f"sdk-tree-sha256={toolchains._EXPECTED_DOTNET_SDK_TREE_SHA256}",
        f"hostfxr-tree-sha256={toolchains._EXPECTED_DOTNET_HOSTFXR_TREE_SHA256}",
        f"runtime-tree-sha256={toolchains._EXPECTED_DOTNET_RUNTIME_TREE_SHA256}",
        f"reference-pack-tree-sha256={toolchains._EXPECTED_DOTNET_REFERENCE_PACK_TREE_SHA256}",
        f"apphost-pack-tree-sha256={toolchains._EXPECTED_DOTNET_APPHOST_PACK_TREE_SHA256}",
        f"hostfxr-sha256={toolchains._EXPECTED_DOTNET_HOSTFXR_SHA256}",
        f"hostpolicy-sha256={toolchains._EXPECTED_DOTNET_HOSTPOLICY_SHA256}",
    }
    assert expected_fields <= set(selected.profile)
    assert toolchains.verify_csharp_toolchain(selected)["muxer"]

    tampered = replace(selected, profile=(*selected.profile[:-1], "hostpolicy-sha256=same-version-replacement"))
    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_DOTNET_IDENTITY_MISMATCH"):
        toolchains.verify_csharp_toolchain(tampered)


def test_dotnet_tree_rejects_parent_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cellar = tmp_path / "Cellar" / "dotnet" / "10.0.301"
    outside = tmp_path / "outside"
    (outside / "sdk").mkdir(parents=True)
    (outside / "sdk" / "payload.dll").write_bytes(b"payload")
    cellar.mkdir(parents=True)
    (cellar / "libexec").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(toolchains, "_EXPECTED_DOTNET_CELLAR", cellar)

    with pytest.raises(RouteError, match="TEST_DOTNET_TREE_UNSAFE"):
        toolchains._dotnet_tree_manifest(cellar / "libexec" / "sdk", "TEST_DOTNET_TREE_UNSAFE")


def test_dotnet_tree_rejects_group_writable_build_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cellar = tmp_path / "Cellar" / "dotnet" / "10.0.301"
    root = cellar / "libexec" / "sdk"
    root.mkdir(parents=True)
    payload = root / "payload.dll"
    payload.write_bytes(b"payload")
    payload.chmod(0o664)
    monkeypatch.setattr(toolchains, "_EXPECTED_DOTNET_CELLAR", cellar)

    with pytest.raises(RouteError, match="TEST_DOTNET_TREE_UNSAFE"):
        toolchains._dotnet_tree_manifest(root, "TEST_DOTNET_TREE_UNSAFE")


def test_java_analysis_and_native_replay_ignore_ambient_vm_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-javaagent:/does/not/exist.jar")
    monkeypatch.setenv("_JAVA_OPTIONS", "-Xbootclasspath/a:/does/not/exist")
    monkeypatch.setenv("JDK_JAVA_OPTIONS", "--class-path=/does/not/exist")
    source = tmp_path / "Identity.java"
    source.write_text(
        "public final class Identity {\n  public static long identity(long value) { return value; }\n}\n",
        encoding="utf-8",
    )

    semantic = analyze(source, "java", "identity")
    report = validate_source(
        source,
        "java",
        semantic.functions[0],
        [{"args": [7], "expected": 7}],
        tmp_path / "runtime",
    )

    assert report["status"] == "PASSED"
    assert report["toolchain"]["executable_sha256"] == toolchains._EXPECTED_JAVA_SHA256
    assert report["toolchain"]["auxiliary_sha256"] == toolchains._EXPECTED_JAVAC_SHA256


@pytest.mark.skipif(os.uname().sysname != "Darwin", reason="exact Swift evidence is Darwin-only")
def test_swift_analyzer_is_fresh_built_outside_repository_build_cache() -> None:
    receipt = swift_analyzer_build_receipt()
    binary = native._SWIFT_ANALYZER_BINARY
    repository_package = native.ENGINE_ROOT / "native" / "swift"
    repository_binary = repository_package / ".build" / "release" / "ElmosSwiftAnalyzer"

    assert binary is not None
    assert not binary.is_relative_to(repository_package.resolve())
    assert binary.resolve() != repository_binary.resolve()
    assert receipt["kind"] == "elmos.swift-analyzer-build-receipt"
    assert receipt["build"]["environment_policy"] == "minimal-empty-home-deterministic-v1"
    assert receipt["build"]["deterministic_environment"] == {
        "SOURCE_DATE_EPOCH": "0",
        "SWIFT_DETERMINISTIC_HASHING": "1",
        "ZERO_AR_DATE": "1",
    }
    assert receipt["build"]["mtime_normalization"] == {
        "epoch_nanoseconds": 0,
        "scope": ["source-snapshot", "dependency-mirror"],
    }
    build_closure = receipt["toolchain"]["build_closure"]
    assert build_closure["compiler_runtime_soundness"] == "NOT_RUN"
    assert build_closure["certification"] == "NOT_CERTIFIED"
    assert len(build_closure["components"]) == 28
    assert len(build_closure["trees"]) == 13
    assert receipt["build"]["automatic_resolution"] is False
    assert receipt["dependency"]["revision"] == native._SWIFT_SYNTAX_REVISION
    assert receipt["dependency"]["sha256"] == "sha256:" + native._SWIFT_SYNTAX_TREE_SHA256
    assert receipt["dependency"]["mirror"]["sha256"] == "sha256:" + native._SWIFT_SYNTAX_TREE_SHA256
    dependency_cache = receipt["dependency"]["mirror"]["cache"]
    assert "absolute_path" not in dependency_cache
    assert set(dependency_cache) == {
        "cache_key",
        "cache_schema",
        "identity",
        "version",
        "revision",
        "seed",
        "sha256",
        "file_count",
        "bytes",
    }
    assert dependency_cache["cache_key"] == native._swift_dependency_cache_key()
    assert dependency_cache["version"] == native._SWIFT_SYNTAX_VERSION
    assert dependency_cache["revision"] == native._SWIFT_SYNTAX_REVISION
    assert dependency_cache["sha256"] == "sha256:" + native._SWIFT_SYNTAX_TREE_SHA256
    assert dependency_cache["file_count"] == native._SWIFT_SYNTAX_TREE_FILE_COUNT
    assert dependency_cache["bytes"] == native._SWIFT_SYNTAX_TREE_BYTES
    assert receipt["toolchain"]["swiftc_sha256"] == "sha256:" + toolchains._EXPECTED_SWIFTC_SHA256
    assert receipt["toolchain"]["swift_driver_sha256"] == "sha256:" + toolchains._EXPECTED_SWIFTC_SHA256
    assert receipt["binary"]["sha256"] == "sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest()
    assert receipt["binary"]["bytes"] == binary.stat().st_size
    assert set(receipt) == {
        "schema_version",
        "kind",
        "source_inputs",
        "dependency",
        "toolchain",
        "network_isolation",
        "build",
        "binary",
        "execution_seal",
        "canonical_identity",
    }
