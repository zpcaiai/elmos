"""P5 native adapters, certified against the toolchains they claim to drive.

``test_native_adapters.py`` proves the adapter *contract* -- path redirection,
fingerprint participation, isolation, degradation -- with no compiler involved.
This module closes the gap that left: every assertion here is made after a real
``gradle`` / ``cmake+ccache`` / ``cargo`` / ``go`` / ``tsc`` / ``pip`` process
has actually run under the environment the adapter produced.

Each toolchain gets the same three questions:

1. Does the tool honour the redirection? -- the sandbox volume fills up and the
   tool's *default* cache location under a private ``HOME`` is never created.
2. Does the cache actually serve a second build? -- a cold build, then the build
   directory is destroyed, then a warm build that the tool itself reports as a
   hit.
3. Can the adapter read its tool's real diagnostics? -- ``parse_diagnostics`` is
   fed the genuine log, never a hand-written sample.

Toolchains this sandbox cannot install (``dotnet``, ``swiftc``, ``flutter``) and
registries it cannot reach (Maven Central) are declared as skips, so an absent
proof shows up as an absent proof in the report rather than as a green test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.native_adapters import (
    NativeBuildCacheAdapter,
    ToolchainProfile,
    adapter_for,
    compare_clean_room,
)

pytestmark = pytest.mark.toolchain

BUILD_TIMEOUT = 900


def tool(name: str) -> str:
    """Absolute path to a toolchain binary, or an explicit skip."""
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"{name} is not available in this environment")
    return path


def profile(name: str, version_argv: Sequence[str], **kwargs: object) -> ToolchainProfile:
    """A toolchain identity taken from the installed compiler, not invented."""
    completed = subprocess.run(  # noqa: S603
        list(version_argv), capture_output=True, text=True, timeout=120, check=False
    )
    reported = (completed.stdout + completed.stderr).strip()
    version = reported.splitlines()[0] if reported else "unknown"
    return ToolchainProfile(name=name, version=version, target_triple="x86_64-linux", **kwargs)  # type: ignore[arg-type]


def sandbox_env(adapter: NativeBuildCacheAdapter, home: Path, passthrough: Sequence[str] = ()) -> dict[str, str]:
    """A minimal environment: PATH, a private HOME, and the adapter's redirections."""
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "TERM": "dumb",
    }
    for key in passthrough:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env.update(adapter.environment())
    adapter.assert_sandboxed(env)
    return env


def run(argv: Sequence[str], cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(  # noqa: S603
        list(argv), cwd=str(cwd), env=env, capture_output=True, text=True, timeout=BUILD_TIMEOUT, check=False
    )
    log = completed.stdout + completed.stderr
    assert completed.returncode == 0, f"{argv[0]} failed ({completed.returncode}):\n{log[-4000:]}"
    return log


def file_count(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file())


# ==========================================================================
# JVM: gradle, with its own build cache
# ==========================================================================
@pytest.fixture
def java_project(tmp_path: Path) -> Path:
    project = tmp_path / "java-project"
    (project / "src/main/java/app").mkdir(parents=True)
    (project / "settings.gradle").write_text("rootProject.name = 'probe'\n", encoding="utf-8")
    (project / "build.gradle").write_text("plugins { id 'java' }\n", encoding="utf-8")
    (project / "src/main/java/app/Hello.java").write_text(
        "package app;\npublic class Hello { public static String greet() { return \"hi\"; } }\n",
        encoding="utf-8",
    )
    return project


def test_gradle_build_cache_is_redirected_and_actually_hits(
    tmp_path: Path, java_project: Path
) -> None:
    """The full loop: cold build, destroy the outputs, warm build served FROM-CACHE."""
    gradle = tool("gradle")
    tool("javac")
    adapter = adapter_for(
        "java",
        tmp_path / "volume",
        profile("gradle", [gradle, "--version"], lockfile_digests={"build.gradle": "sha256:" + "a" * 64}),
    )
    home = tmp_path / "home"
    env = sandbox_env(adapter, home, passthrough=("JAVA_HOME", "JAVA_TOOL_OPTIONS"))
    gradle_home = Path(env["GRADLE_USER_HOME"])
    build_cache = gradle_home / "caches" / "build-cache-1"
    assert not build_cache.exists()

    argv = [gradle, "--offline", "--no-daemon", "--build-cache", "build"]
    cold = run(argv, java_project, env)
    assert "BUILD SUCCESSFUL" in cold
    assert build_cache.is_dir(), "gradle did not honour GRADLE_USER_HOME"
    assert file_count(build_cache) > 0

    # Gradle's default location must be untouched: the redirect is the only reason
    # the cache landed where it did.
    assert not (home / ".gradle").exists()

    run([gradle, "--offline", "--no-daemon", "clean"], java_project, env)
    assert not (java_project / "build" / "classes").exists()

    warm = run(argv, java_project, env)
    assert "FROM-CACHE" in warm, warm[-2000:]
    stats = adapter.parse_diagnostics(warm)
    assert stats.hits > 0
    assert stats.bytes_used > 0
    assert stats.entries > 0
    assert stats.degraded is False


def test_gradle_outputs_import_into_cas_and_survive_a_clean_room(
    tmp_path: Path, java_project: Path
) -> None:
    """CERT: the cache-served build and a cache-free build agree byte for byte."""
    gradle = tool("gradle")
    tool("javac")
    toolchain = profile("gradle", [gradle, "--version"])
    cas = ContentAddressableStore(tmp_path / "cas")

    cached = adapter_for("java", tmp_path / "volume", toolchain)
    env = sandbox_env(cached, tmp_path / "home", passthrough=("JAVA_HOME", "JAVA_TOOL_OPTIONS"))
    run([gradle, "--offline", "--no-daemon", "--build-cache", "build"], java_project, env)
    run([gradle, "--offline", "--no-daemon", "clean"], java_project, env)
    run([gradle, "--offline", "--no-daemon", "--build-cache", "build"], java_project, env)
    # Class files are deterministic; jars carry timestamps, so they are not the
    # thing to certify reproducibility with.
    cached_outputs = cached.import_outputs(java_project, cas, ["build/classes/**/*.class"])
    assert cached_outputs, "no compiled classes were imported"
    assert cas.contains(cached_outputs[0].digest)

    # A clean room: a different volume, an empty gradle home, caching disabled.
    clean = adapter_for("java", tmp_path / "clean-volume", toolchain, trust_domain="clean-room")
    clean_env = sandbox_env(clean, tmp_path / "clean-home", passthrough=("JAVA_HOME", "JAVA_TOOL_OPTIONS"))
    clean_env.update(clean.clean_room_flags())
    assert clean_env["GRADLE_OPTS"] == "-Dorg.gradle.caching=false"
    run([gradle, "--offline", "--no-daemon", "clean"], java_project, clean_env)
    run([gradle, "--offline", "--no-daemon", "build"], java_project, clean_env)
    clean_outputs = clean.import_outputs(java_project, cas, ["build/classes/**/*.class"])

    comparison = compare_clean_room(cached_outputs, clean_outputs)
    assert comparison.matched, comparison.differing_paths
    assert comparison.cached_tree_digest == comparison.clean_tree_digest


# ==========================================================================
# C/C++: cmake driving ccache
# ==========================================================================
@pytest.fixture
def c_project(tmp_path: Path) -> Path:
    project = tmp_path / "c-project"
    project.mkdir()
    (project / "main.c").write_text(
        '#include <stdio.h>\nint main(void){ printf("hi\\n"); return 0; }\n', encoding="utf-8"
    )
    (project / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\nproject(probe C)\nadd_executable(probe main.c)\n",
        encoding="utf-8",
    )
    return project


def test_ccache_hits_a_recompilation_through_the_sandboxed_cache(tmp_path: Path, c_project: Path) -> None:
    cmake = tool("cmake")
    ccache = tool("ccache")
    tool("gcc")
    adapter = adapter_for("cpp", tmp_path / "volume", profile("gcc", [tool("gcc"), "--version"]))
    home = tmp_path / "home"
    env = sandbox_env(adapter, home)
    ccache_dir = Path(env["CCACHE_DIR"])
    build_dir = Path(env["CMAKE_BUILD_DIR"])

    configure = [cmake, "-S", ".", "-B", str(build_dir), f"-DCMAKE_C_COMPILER_LAUNCHER={ccache}"]
    run(configure, c_project, env)
    run([cmake, "--build", str(build_dir)], c_project, env)
    assert file_count(ccache_dir) > 0, "ccache did not honour CCACHE_DIR"
    assert not (home / ".ccache").exists() and not (home / ".cache" / "ccache").exists()

    shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)
    run(configure, c_project, env)
    run([cmake, "--build", str(build_dir)], c_project, env)

    stats_log = run([ccache, "-s"], c_project, env)
    stats = adapter.parse_diagnostics(stats_log)
    assert stats.hits >= 1, stats_log
    assert stats.misses >= 1, stats_log
    assert stats.bytes_used > 0

    # And the executable the cached compile produced imports into CAS.
    cas = ContentAddressableStore(tmp_path / "cas")
    outputs = adapter.import_outputs(build_dir, cas, ["probe"])
    assert len(outputs) == 1
    assert cas.contains(outputs[0].digest)


# ==========================================================================
# Rust: cargo
# ==========================================================================
def test_cargo_reuses_a_fresh_crate_from_the_sandboxed_target_dir(tmp_path: Path) -> None:
    cargo = tool("cargo")
    project = tmp_path / "rust-project"
    (project / "src").mkdir(parents=True)
    (project / "Cargo.toml").write_text(
        '[package]\nname = "probe"\nversion = "0.1.0"\nedition = "2021"\n', encoding="utf-8"
    )
    (project / "src" / "main.rs").write_text('fn main(){ println!("hi"); }\n', encoding="utf-8")

    adapter = adapter_for("rust", tmp_path / "volume", profile("cargo", [cargo, "--version"]))
    home = tmp_path / "home"
    env = sandbox_env(adapter, home, passthrough=("RUSTUP_HOME", "RUSTUP_TOOLCHAIN"))
    target_dir = Path(env["CARGO_TARGET_DIR"])

    cold = run([cargo, "build", "--offline", "-v"], project, env)
    assert "Compiling probe" in cold
    assert file_count(target_dir) > 0, "cargo did not honour CARGO_TARGET_DIR"
    assert not (home / ".cargo" / "registry").exists()

    warm = run([cargo, "build", "--offline", "-v"], project, env)
    stats = adapter.parse_diagnostics(warm)
    assert stats.hits >= 1, warm
    assert stats.misses == 0, warm

    cold_stats = adapter.parse_diagnostics(cold)
    assert cold_stats.misses >= 1 and cold_stats.hits == 0


# ==========================================================================
# Go: the compiler's own build cache
# ==========================================================================
@pytest.fixture
def go_project(tmp_path: Path) -> Path:
    project = tmp_path / "go-project"
    project.mkdir()
    (project / "go.mod").write_text("module probe\n\ngo 1.21\n", encoding="utf-8")
    (project / "main.go").write_text(
        'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("hi") }\n', encoding="utf-8"
    )
    return project


def test_go_build_cache_is_redirected_and_silences_a_rebuild(tmp_path: Path, go_project: Path) -> None:
    go = tool("go")
    adapter = adapter_for("go", tmp_path / "volume", profile("go", [go, "version"]))
    home = tmp_path / "home"
    env = sandbox_env(adapter, home)
    gocache = Path(env["GOCACHE"])

    cold = run([go, "build", "-v", "-o", "bin/probe", "."], go_project, env)
    assert "probe" in cold
    assert file_count(gocache) > 0, "go did not honour GOCACHE"
    assert not (home / ".cache" / "go-build").exists()
    assert adapter.parse_diagnostics(cold).misses >= 1

    warm = run([go, "build", "-v", "-o", "bin/probe2", "."], go_project, env)
    assert warm.strip() == "", warm
    stats = adapter.parse_diagnostics(warm)
    assert stats.hits == 1 and stats.misses == 0


def test_a_second_trust_domain_starts_from_a_cold_go_cache(tmp_path: Path, go_project: Path) -> None:
    """Isolation is physical, not advisory: a fork cannot warm itself on official work."""
    go = tool("go")
    toolchain = profile("go", [go, "version"])
    official = adapter_for("go", tmp_path / "volume", toolchain, trust_domain="official")
    fork = adapter_for("go", tmp_path / "volume", toolchain, trust_domain="fork")
    assert official.root != fork.root

    official_env = sandbox_env(official, tmp_path / "home-official")
    run([go, "build", "-v", "-o", "bin/probe", "."], go_project, official_env)
    assert file_count(Path(official_env["GOCACHE"])) > 0

    fork_env = sandbox_env(fork, tmp_path / "home-fork")
    assert file_count(Path(fork_env["GOCACHE"])) == 0
    fork_log = run([go, "build", "-v", "-o", "bin/probe-fork", "."], go_project, fork_env)
    assert adapter_for("go", tmp_path / "volume", toolchain, trust_domain="fork").parse_diagnostics(
        fork_log
    ).misses >= 1, "the fork was served by the official cache"


# ==========================================================================
# TypeScript / node
# ==========================================================================
def test_tsc_incremental_build_and_the_npm_cache_redirect(tmp_path: Path) -> None:
    tsc = tool("tsc")
    npm = tool("npm")
    project = tmp_path / "ts-project"
    (project / "src").mkdir(parents=True)
    (project / "tsconfig.json").write_text(
        '{"compilerOptions":{"target":"ES2020","module":"commonjs","outDir":"dist",'
        '"declaration":true,"composite":true,"tsBuildInfoFile":"dist/.tsbuildinfo"},"include":["src"]}\n',
        encoding="utf-8",
    )
    (project / "src" / "index.ts").write_text(
        "export const greet = (name: string): string => `hi ${name}`;\n", encoding="utf-8"
    )

    adapter = adapter_for("typescript", tmp_path / "volume", profile("tsc", [tsc, "--version"]))
    env = sandbox_env(adapter, tmp_path / "home")

    # npm itself reports where its cache is; that is the redirect, verified by npm.
    reported = run([npm, "config", "get", "cache"], project, env).strip()
    assert reported == env["npm_config_cache"], reported

    cold = run([tsc, "--build", "--verbose"], project, env)
    assert "is out of date" in cold
    assert adapter.parse_diagnostics(cold).misses >= 1

    warm = run([tsc, "--build", "--verbose"], project, env)
    assert "is up to date" in warm
    stats = adapter.parse_diagnostics(warm)
    assert stats.hits >= 1 and stats.misses == 0

    cas = ContentAddressableStore(tmp_path / "cas")
    outputs = adapter.import_outputs(project, cas)
    assert [output.logical_path for output in outputs if output.logical_path.endswith(".js")]
    assert all(cas.contains(output.digest) for output in outputs)


# ==========================================================================
# Python wheels
# ==========================================================================
def test_pip_serves_the_second_download_from_the_sandboxed_cache(tmp_path: Path) -> None:
    pip_argv = [shutil.which("python3") or "python3", "-m", "pip"]
    adapter = adapter_for("python", tmp_path / "volume", profile("pip", [*pip_argv, "--version"]))
    home = tmp_path / "home"
    env = sandbox_env(adapter, home)
    cache_dir = Path(env["PIP_CACHE_DIR"])

    argv = [*pip_argv, "download", "six==1.16.0", "--no-deps", "-d"]
    try:
        cold = run([*argv, str(tmp_path / "d1")], tmp_path, env)
    except AssertionError as error:  # the index is not always reachable
        pytest.skip(f"PyPI is not reachable from this sandbox: {error}")
    assert "Downloading" in cold or "Using cached" in cold
    assert file_count(cache_dir) > 0, "pip did not honour PIP_CACHE_DIR"
    assert not (home / ".cache" / "pip").exists()

    warm = run([*argv, str(tmp_path / "d2")], tmp_path, env)
    assert "Using cached" in warm, warm
    stats = adapter.parse_diagnostics(warm)
    assert stats.hits >= 1
    assert adapter.clean_room_flags() == {"PIP_NO_CACHE_DIR": "1"}


# ==========================================================================
# Declared, unprovable here
# ==========================================================================
def test_msbuild_incremental_build_through_the_sandboxed_nuget_cache(tmp_path: Path) -> None:
    """The .NET half of the target side, against the real SDK.

    ``nuget.org`` is unreachable from this sandbox, so the project declares an
    empty package source: the restore is genuine, it simply has nothing remote
    to fetch. That is enough to certify the adapter's redirection and its
    reading of MSBuild's own up-to-date reporting.
    """
    dotnet = tool("dotnet")
    project = tmp_path / "cs-project"
    project.mkdir()
    (project / "probe.csproj").write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\">\n"
        "  <PropertyGroup>\n"
        "    <OutputType>Exe</OutputType>\n"
        "    <TargetFramework>net8.0</TargetFramework>\n"
        "  </PropertyGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    (project / "NuGet.config").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<configuration><packageSources><clear /></packageSources></configuration>\n",
        encoding="utf-8",
    )
    (project / "Program.cs").write_text('System.Console.WriteLine("hi");\n', encoding="utf-8")

    adapter = adapter_for("csharp", tmp_path / "volume", profile("dotnet", [dotnet, "--version"]))
    home = tmp_path / "home"
    env = sandbox_env(adapter, home)
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    env["DOTNET_NOLOGO"] = "1"

    # NuGet reports where its global package folder is; that is the redirect,
    # verified by the tool rather than by reading our own environment back.
    reported = run([dotnet, "nuget", "locals", "global-packages", "--list"], project, env)
    assert reported.strip().endswith(env["NUGET_PACKAGES"]), reported

    cold = run([dotnet, "build", "-v", "n"], project, env)
    assert "Build succeeded" in cold
    cold_stats = adapter.parse_diagnostics(cold)
    assert cold_stats.misses >= 1, cold
    assert cold_stats.hits == 0, cold
    # ``~/.nuget/NuGet.Config`` is configuration; the *package cache* is what
    # must not appear outside the sandbox.
    assert not (home / ".nuget" / "packages").exists()

    warm = run([dotnet, "build", "-v", "n"], project, env)
    warm_stats = adapter.parse_diagnostics(warm)
    assert warm_stats.hits >= 1, warm
    assert warm_stats.misses == 0, warm

    cas = ContentAddressableStore(tmp_path / "cas")
    outputs = adapter.import_outputs(project, cas, ["bin/**/*.dll"])
    assert [output for output in outputs if output.logical_path.endswith("probe.dll")]
    assert all(cas.contains(output.digest) for output in outputs)
    assert adapter.clean_room_flags() == {"MSBUILD_NO_INCREMENTAL": "1"}


def test_xcode_swift_adapter_needs_a_swift_toolchain() -> None:
    tool("swiftc")
    pytest.fail("swiftc appeared: this skip should be replaced with a real Xcode/SwiftPM certification")


def test_flutter_pub_adapter_needs_a_flutter_sdk() -> None:
    tool("flutter")
    pytest.fail("flutter appeared: this skip should be replaced with a real pub certification")


def test_the_maven_half_of_the_jvm_adapter_needs_a_reachable_central() -> None:
    tool("mvn")
    pytest.skip(
        "Maven Central is unreachable from this sandbox (plugin resolution fails online and "
        "offline), so only the Gradle half of gradle-maven is certified here"
    )
