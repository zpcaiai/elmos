from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from elmos_polyglot_route import native, toolchains
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze, swift_analyzer_build_receipt
from elmos_polyglot_route.validation import validate_source


def test_toolchain_build_cache_write_probes_root_and_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        native.pwd,
        "getpwuid",
        lambda _uid: SimpleNamespace(pw_dir=str(tmp_path)),
    )

    directories = native._toolchain_build_cache(
        "go",
        "content-key",
        ("gocache", "gopath"),
    )

    expected_root = (
        tmp_path
        / ".cache"
        / "elmos-polyglot-route-engine"
        / "toolchain-build-cache-v1"
        / "go"
        / "content-key"
    )
    assert directories == (expected_root / "gocache", expected_root / "gopath")
    assert list(expected_root.rglob(".elmos-cache-write-probe-*")) == []


@pytest.mark.parametrize("failure_call", (1, 2, 3), ids=("root", "first-child", "second-child"))
def test_toolchain_build_cache_falls_back_when_any_cache_directory_is_not_writable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
) -> None:
    monkeypatch.setattr(
        native.pwd,
        "getpwuid",
        lambda _uid: SimpleNamespace(pw_dir=str(tmp_path)),
    )
    real_temporary_file = native.tempfile.TemporaryFile
    calls = 0

    def probed_temporary_file(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise PermissionError("sandbox denied cache write")
        return real_temporary_file(*args, **kwargs)

    monkeypatch.setattr(native.tempfile, "TemporaryFile", probed_temporary_file)

    assert (
        native._toolchain_build_cache(
            "go",
            "content-key",
            ("gocache", "gopath"),
        )
        is None
    )


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
        "TEST_TELEMETRY_DIR": str(hostile_root / "go-telemetry"),
    }
    for key, value in hostile.items():
        monkeypatch.setenv(key, value)
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    home.mkdir()
    scratch.mkdir()

    environment = toolchains.sanitized_subprocess_env(home=home, temp_dir=scratch)

    assert not (set(hostile) - {"TEST_TELEMETRY_DIR"}).intersection(environment)
    assert environment["TEST_TELEMETRY_DIR"] != hostile["TEST_TELEMETRY_DIR"]
    assert environment["HOME"] == str(home.resolve())
    assert environment["TMPDIR"] == str(scratch.resolve())
    assert environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert environment["PYTHONNOUSERSITE"] == "1"
    telemetry = home.resolve() / ".elmos-go-telemetry"
    assert environment["TEST_TELEMETRY_DIR"] == str(telemetry)
    assert (telemetry / "mode").read_bytes() == b"off\n"
    assert stat.S_IMODE(telemetry.stat().st_mode) == 0o700
    assert stat.S_IMODE((telemetry / "mode").stat().st_mode) == 0o600


def test_minimal_subprocess_environment_rejects_tampered_go_telemetry_mode(tmp_path: Path) -> None:
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    telemetry = home / ".elmos-go-telemetry"
    telemetry.mkdir(mode=0o700, parents=True)
    (telemetry / "mode").write_text("local\n", encoding="ascii")
    (telemetry / "mode").chmod(0o600)
    scratch.mkdir()

    with pytest.raises(RouteError, match="SUBPROCESS_GO_TELEMETRY_ISOLATION_FAILED"):
        toolchains.sanitized_subprocess_env(home=home, temp_dir=scratch)


def test_minimal_subprocess_environment_rejects_symlinked_go_telemetry_directory(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    outside = tmp_path / "outside-telemetry"
    home.mkdir()
    scratch.mkdir()
    outside.mkdir(mode=0o700)
    (home / ".elmos-go-telemetry").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RouteError, match="SUBPROCESS_GO_TELEMETRY_ISOLATION_FAILED"):
        toolchains.sanitized_subprocess_env(home=home, temp_dir=scratch)


@pytest.mark.parametrize("entry_kind", ("symlink", "hardlink"))
def test_minimal_subprocess_environment_rejects_linked_go_telemetry_mode(
    tmp_path: Path,
    entry_kind: str,
) -> None:
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    telemetry = home / ".elmos-go-telemetry"
    telemetry.mkdir(mode=0o700, parents=True)
    scratch.mkdir()
    outside = tmp_path / "outside-mode"
    outside.write_bytes(b"off\n")
    outside.chmod(0o600)
    mode = telemetry / "mode"
    if entry_kind == "symlink":
        mode.symlink_to(outside)
    else:
        os.link(outside, mode)

    with pytest.raises(RouteError, match="SUBPROCESS_GO_TELEMETRY_ISOLATION_FAILED"):
        toolchains.sanitized_subprocess_env(home=home, temp_dir=scratch)


def test_minimal_subprocess_environment_rejects_go_telemetry_directory_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    telemetry = home / ".elmos-go-telemetry"
    telemetry.mkdir(mode=0o700, parents=True)
    mode = telemetry / "mode"
    mode.write_bytes(b"off\n")
    mode.chmod(0o600)
    scratch.mkdir()
    displaced = home / ".elmos-go-telemetry-displaced"
    real_open = os.open
    replaced = False

    def replacing_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        file_mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if path == "mode" and dir_fd is not None and not replaced:
            replaced = True
            telemetry.rename(displaced)
            telemetry.mkdir(mode=0o700)
            replacement_mode = telemetry / "mode"
            replacement_mode.write_bytes(b"off\n")
            replacement_mode.chmod(0o600)
        return real_open(path, flags, file_mode, dir_fd=dir_fd)

    monkeypatch.setattr(toolchains.os, "open", replacing_open)

    with pytest.raises(RouteError, match="SUBPROCESS_GO_TELEMETRY_ISOLATION_FAILED"):
        toolchains.sanitized_subprocess_env(home=home, temp_dir=scratch)

    assert replaced


def test_minimal_subprocess_environment_rejects_equal_size_go_telemetry_mode_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    scratch = tmp_path / "tmp"
    telemetry = home / ".elmos-go-telemetry"
    telemetry.mkdir(mode=0o700, parents=True)
    mode = telemetry / "mode"
    mode.write_bytes(b"off\n")
    mode.chmod(0o600)
    scratch.mkdir()
    real_read = os.read
    raced = False

    def racing_read(descriptor: int, byte_count: int) -> bytes:
        nonlocal raced
        content = real_read(descriptor, byte_count)
        if content == b"off\n" and not raced:
            raced = True
            mode.write_bytes(b"on \n")
        return content

    monkeypatch.setattr(toolchains.os, "read", racing_read)

    with pytest.raises(RouteError, match="SUBPROCESS_GO_TELEMETRY_ISOLATION_FAILED"):
        toolchains.sanitized_subprocess_env(home=home, temp_dir=scratch)

    assert raced


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


def test_java_codesign_receipt_keeps_strict_verify_and_display_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = Path("/fixed/openjdk.jdk")
    commands: list[list[str]] = []

    def output(command: list[str], **_: object) -> str:
        commands.append(command)
        return "Identifier=net.java.openjdk.jdk"

    monkeypatch.setattr(toolchains, "_output", output)

    assert toolchains._java_bundle_signature(bundle) == (
        "Identifier=net.java.openjdk.jdk"
    )
    assert commands == [
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            str(bundle),
        ],
        ["/usr/bin/codesign", "-d", "--verbose=4", str(bundle)],
    ]


@pytest.mark.parametrize(
    ("failed_flag", "diagnostic"),
    [
        ("--verify", "EXACT_TOOLCHAIN_UNAVAILABLE:java:codesign-verify"),
        ("-d", "EXACT_TOOLCHAIN_UNAVAILABLE:java:codesign-display"),
    ],
)
def test_java_codesign_receipt_reports_the_exact_failed_stage(
    monkeypatch: pytest.MonkeyPatch,
    failed_flag: str,
    diagnostic: str,
) -> None:
    def output(command: list[str], **_: object) -> str:
        if failed_flag in command:
            raise RouteError(
                "EXACT_TOOLCHAIN_UNAVAILABLE:/usr/bin/codesign:"
                "exit=1:diagnostic=strict verification failed"
            )
        return ""

    monkeypatch.setattr(toolchains, "_output", output)

    with pytest.raises(RouteError, match=diagnostic) as caught:
        toolchains._java_bundle_signature(Path("/fixed/openjdk.jdk"))
    assert "exit=1:diagnostic=strict verification failed" in str(caught.value)


def test_temurin_contract_is_explicitly_selected_for_ci_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = (
        tmp_path
        / "hostedtoolcache"
        / "Java_Temurin-Hotspot_jdk"
        / "21.0.11-10.0"
        / "arm64"
        / "Contents"
        / "Home"
    )
    home.mkdir(parents=True)
    monkeypatch.setenv("ELMOS_JAVA21_DISTRIBUTION", "temurin")
    monkeypatch.setenv("ELMOS_JAVA21_HOME", str(home))

    contract = toolchains._java_contract()

    assert contract.home == home.resolve()
    assert contract.distribution == "Temurin-21.0.11+10"
    assert contract.java_sha256 == toolchains._TEMURIN_JAVA_SHA256
    assert contract.team_identifier == toolchains._TEMURIN_JAVA_TEAM_IDENTIFIER
    assert contract.bundle_cdhash_full == toolchains._TEMURIN_JAVA_BUNDLE_CDHASH_FULL


def test_temurin_contract_rejects_an_unpinned_setup_java_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "java" / "Contents" / "Home"
    home.mkdir(parents=True)
    monkeypatch.setenv("ELMOS_JAVA21_DISTRIBUTION", "temurin")
    monkeypatch.setenv("ELMOS_JAVA21_HOME", str(home))

    with pytest.raises(
        RouteError,
        match="EXACT_TOOLCHAIN_DECLARED_HOME_INVALID:java:temurin",
    ):
        toolchains._java_contract()


@pytest.mark.parametrize(
    ("distribution", "expected"),
    (
        ("homebrew", "kotlinc-jvm 2.2.20 (JRE 21.0.11)"),
        ("temurin", "kotlinc-jvm 2.2.20 (JRE 21.0.11+10-LTS)"),
    ),
)
def test_kotlin_banner_contract_is_exact_for_the_selected_java_distribution(
    distribution: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELMOS_JAVA21_DISTRIBUTION", distribution)

    assert toolchains._kotlin_version_contract() == (distribution, expected)


def test_kotlin_banner_contract_rejects_an_unknown_java_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELMOS_JAVA21_DISTRIBUTION", "untrusted")

    with pytest.raises(
        RouteError,
        match="EXACT_TOOLCHAIN_KOTLIN_JVM_DISTRIBUTION_UNSUPPORTED:untrusted",
    ):
        toolchains._kotlin_version_contract()


def test_java_toolchain_binds_launchers_runtime_modules_and_bundle_signature() -> None:
    contract = toolchains._java_contract()
    selected = toolchains.exact_toolchain("java")

    assert selected.executable_sha256 == contract.java_sha256
    assert selected.auxiliary_sha256 == contract.javac_sha256
    assert f"jdk-cdhash-full={contract.bundle_cdhash_full}" in selected.profile
    assert f"jdk-modules-sha256={contract.modules_sha256}" in selected.profile
    assert f"libjvm-sha256={contract.jvm_sha256}" in selected.profile


def test_python_runtime_identity_is_root_portable_and_path_confined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = toolchains._output(
        [
            str(toolchains._EXPECTED_PYTHON_EXECUTABLE),
            "-I",
            "-B",
            "-c",
            toolchains._PYTHON_RUNTIME_IDENTITY_SCRIPT,
        ]
    )
    identity = json.loads(raw)
    canonical = toolchains._canonical_python_runtime_identity(identity)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == (
        toolchains._EXPECTED_PYTHON_RUNTIME_IDENTITY_SHA256
    )

    local_root = str(toolchains._EXPECTED_PYTHON_ROOT)
    runner_root = "/Users/runner/.local/share/elmos/toolchains/python-build-standalone/" + (
        local_root.split("/python-build-standalone/", 1)[1]
    )
    runner_identity = dict(identity)
    for field in toolchains._PYTHON_RUNTIME_PATH_FIELDS:
        runner_identity[field] = runner_identity[field].replace(
            local_root,
            runner_root,
            1,
        )
    monkeypatch.setattr(toolchains, "_EXPECTED_PYTHON_ROOT", Path(runner_root))
    assert toolchains._canonical_python_runtime_identity(runner_identity) == canonical

    runner_identity["executable"] = "/private/tmp/forged-python"
    with pytest.raises(
        RouteError,
        match="EXACT_TOOLCHAIN_PYTHON_IDENTITY_PATH_MISMATCH:executable",
    ):
        toolchains._canonical_python_runtime_identity(runner_identity)


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
    contract = toolchains._java_contract()
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
    assert report["toolchain"]["executable_sha256"] == contract.java_sha256
    assert report["toolchain"]["auxiliary_sha256"] == contract.javac_sha256


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
