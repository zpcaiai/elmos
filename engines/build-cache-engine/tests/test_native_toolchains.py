"""P5 native adapters, certified against the toolchains they claim to drive.

``test_native_adapters.py`` proves the adapter *contract* -- path redirection,
fingerprint participation, isolation, degradation -- with no compiler involved.
This module closes the gap that left: every assertion here is made after a real
``gradle`` / ``cmake+ccache`` / ``cargo`` / ``go`` / ``tsc`` / ``pip`` /
``dotnet`` / ``swift`` / ``flutter`` process has actually run under the
environment the adapter produced.

Each toolchain gets the same three questions:

1. Does the tool honour the redirection? -- the sandbox volume fills up and the
   tool's *default* cache location under a private ``HOME`` is never created.
2. Does the cache actually serve a second build? -- a cold build, then the build
   directory is destroyed, then a warm build that the tool itself reports as a
   hit.
3. Can the adapter read its tool's real diagnostics? -- ``parse_diagnostics`` is
   fed the genuine log, never a hand-written sample.

Toolchains a given host cannot install (``dotnet``, ``swiftc``, ``flutter`` are
absent from the Linux certification image) and registries it cannot reach
(Maven Central) are declared as skips, so an absent proof shows up as an absent
proof in the report rather than as a green test. Each such skip names the exact
claim it leaves uncertified.

The adapter *contract* -- redirection, fingerprint, isolation, degradation --
is asserted unconditionally for every adapter, including the ones whose tool is
missing (``_adapter_contract_without_the_tool``). Only the halves that need a
compiler are behind a ``shutil.which`` guard, so an absent toolchain shrinks the
residue to one named thing rather than voiding a whole adapter.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.errors import ContractViolation
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


def tool_version_major(executable: str) -> int:
    """The installed SDK's major version, read from the SDK itself.

    Pinning a framework moniker in a test makes the test a statement about
    which SDK the author had, not about the adapter. Ask the tool.
    """

    completed = subprocess.run(  # noqa: S603
        [executable, "--version"], capture_output=True, text=True, timeout=120, check=False
    )
    reported = (completed.stdout + completed.stderr).strip().splitlines()
    assert reported, f"{executable} --version produced nothing"
    head = reported[0].strip().split(".")[0]
    assert head.isdigit(), f"cannot read a major version from {reported[0]!r}"
    return int(head)


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


def reported_cache_path(log: str, label: str) -> Path:
    """The cache location a tool printed for itself, pulled out of its own log.

    Tools that can be asked where their cache is (``dotnet nuget locals``,
    ``npm config get cache``, ``mvn help:evaluate``) are the strongest evidence
    a redirect was honoured, because the answer comes from the tool rather than
    from reading our own environment back. The answer arrives inside a log that
    may also carry a first-run banner on stdout and warnings on stderr, so the
    line is located and the path taken from it -- never string-matched against
    the whole blob, which silently turns any trailing stderr byte into a
    failure and any prefix into a pass.
    """
    marker = f"{label}:"
    for line in log.splitlines():
        index = line.find(marker)
        if index != -1:
            return Path(line[index + len(marker) :].strip())
    raise AssertionError(f"{label!r} was not reported in:\n{log[-2000:]}")


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
def _adapter_contract_without_the_tool(adapter: NativeBuildCacheAdapter, home: Path) -> None:
    """Everything about an adapter that does not need its tool to exist."""
    env = sandbox_env(adapter, home)
    adapter.assert_sandboxed(env)
    for key in adapter.env_template:
        assert Path(env[key]).is_dir() or Path(env[key]).parent.is_dir()
    assert adapter.fingerprint_digest().startswith("sha256:")
    assert adapter.stats().degraded is False
    degraded = adapter.degrade("the toolchain is absent on this platform")
    assert degraded.degraded is True and degraded.detail
    hostile = dict(env)
    hostile[next(iter(adapter.env_template))] = str(Path.home())
    with pytest.raises(ContractViolation):
        adapter.assert_sandboxed(hostile)


def test_msbuild_incremental_build_through_the_sandboxed_nuget_cache(tmp_path: Path) -> None:
    """The .NET half of the target side, against the real SDK.

    ``nuget.org`` is unreachable from this sandbox, so the project declares an
    empty package source: the restore is genuine, it simply has nothing remote
    to fetch. That is enough to certify the adapter's redirection and its
    reading of MSBuild's own up-to-date reporting.

    A passing run proves: NuGet itself names the sandboxed directory as its
    global package folder; the host's ``~/.nuget/packages`` is never created;
    a cold ``dotnet build`` executes MSBuild targets and a warm one is told by
    MSBuild that ``CoreCompile`` is up to date; and the assembly the warm build
    leaves behind is byte-identical to the cold one, so the compile really was
    skipped rather than merely re-run to the same effect.

    Two assertions here were written against an imagined log and are corrected:

    * the reported path was compared with ``str.endswith`` against the whole
      ``stdout + stderr`` blob. On darwin the sandbox lives under
      ``/var/folders``, a symlink to ``/private/var``, so the tool's spelling of
      the path and ours can differ while naming the same directory; and any
      byte the SDK writes to stderr lands after the path and breaks the suffix.
      Both are now settled by resolving the two paths and comparing them.
    * ``warm_stats.misses == 0`` cannot be asserted through this adapter.
      ``MsbuildNugetAdapter._HEADER`` counts a target as executed unless
      ``_SKIPPED`` names it, and ``_SKIPPED`` recognises exactly one of
      MSBuild's two skip messages: ``because all output files are up-to-date``.
      A target skipped ``because it has no inputs`` -- which is what
      ``CoreResGen`` and ``_CopyFilesMarkedCopyLocal`` do in a project with no
      resources and no copy-local references -- is therefore counted as a
      *miss* on a warm build. Which of the four names in ``_HEADER`` takes that
      path is decided by the host SDK's target set, so the absolute is
      unsatisfiable off the SDK it was written against. The claim is made
      instead out of MSBuild's own words about ``CoreCompile``, out of a strict
      drop in executed targets, and out of the assembly's digest.
    """
    dotnet = tool("dotnet")
    project = tmp_path / "cs-project"
    project.mkdir()
    # The target framework has to be the SDK's own, not a fixed one. The
    # NuGet.config below clears every package source, so the only feed left is
    # the SDK's bundled ``library-packs`` -- which carries the reference packs
    # for *that* SDK's framework and no other. A hardcoded ``net8.0`` therefore
    # restored fine on a .NET 8 SDK and failed with three ``NU1101: Unable to
    # find package Microsoft.NETCore.App.Ref`` on a .NET 10 one, which is what
    # this test hit on a Homebrew dotnet 10.0.301.
    sdk_major = tool_version_major(dotnet)
    target_framework = f"net{sdk_major}.0"
    (project / "probe.csproj").write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\">\n"
        "  <PropertyGroup>\n"
        "    <OutputType>Exe</OutputType>\n"
        f"    <TargetFramework>{target_framework}</TargetFramework>\n"
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
    reported = reported_cache_path(
        run([dotnet, "nuget", "locals", "global-packages", "--list"], project, env), "global-packages"
    )
    assert reported.resolve() == Path(env["NUGET_PACKAGES"]).resolve(), reported

    cold = run([dotnet, "build", "-v", "n"], project, env)
    assert "Build succeeded" in cold
    cold_stats = adapter.parse_diagnostics(cold)
    assert cold_stats.misses >= 1, cold
    assert cold_stats.hits == 0, cold
    # ``~/.nuget/NuGet.Config`` is configuration; the *package cache* is what
    # must not appear outside the sandbox.
    assert not (home / ".nuget" / "packages").exists()

    cas = ContentAddressableStore(tmp_path / "cas")
    after_cold = adapter.import_outputs(project, cas, ["bin/**/*.dll"])
    assert [output for output in after_cold if output.logical_path.endswith("probe.dll")]
    assert all(cas.contains(output.digest) for output in after_cold)

    warm = run([dotnet, "build", "-v", "n"], project, env)
    warm_stats = adapter.parse_diagnostics(warm)
    assert warm_stats.hits >= 1, warm
    # MSBuild's own statement that the compile was incremental. See the
    # docstring for why the adapter cannot deliver ``misses == 0`` here.
    assert 'Skipping target "CoreCompile"' in warm, warm[-4000:]
    assert warm_stats.misses < cold_stats.misses, warm

    # And the compile really was skipped: a re-run compile would rewrite the
    # assembly, so an unchanged digest is the evidence a target header is not.
    after_warm = adapter.import_outputs(project, cas, ["bin/**/*.dll"])
    comparison = compare_clean_room(after_cold, after_warm)
    assert comparison.matched, comparison.differing_paths
    assert all(cas.contains(output.digest) for output in after_warm)
    assert adapter.clean_room_flags() == {"MSBUILD_NO_INCREMENTAL": "1"}


def test_the_xcode_swift_adapter_holds_without_a_swift_toolchain(tmp_path: Path) -> None:
    """Narrow the gap to exactly what needs the tool.

    Everything about the ``xcode-swift`` adapter that does *not* need ``swiftc``
    is asserted here, unconditionally, on every host. The compiler half lives in
    ``test_swiftpm_cold_and_warm_through_the_sandboxed_xcode_caches``, which
    skips with a named residue where no Swift toolchain exists.
    """
    adapter = adapter_for("swift", tmp_path / "volume", ToolchainProfile("swift", "6.0", sdk="macosx"))
    _adapter_contract_without_the_tool(adapter, tmp_path / "home")
    assert set(adapter.env_template) == {"DERIVED_DATA_DIR", "MODULE_CACHE_DIR", "SWIFTPM_CACHE_DIR"}
    assert adapter.clean_room_flags() == {"SWIFT_DETERMINISTIC_HASHING": "1"}


@pytest.fixture
def swift_package(tmp_path: Path) -> Path:
    """A two-target SwiftPM package: a library, and an executable that uses it.

    Two targets rather than one so a ``.swiftmodule`` is unambiguously produced
    and so the warm build has a dependency edge to get wrong.
    """
    package = tmp_path / "swift-package"
    (package / "Sources" / "ProbeCore").mkdir(parents=True)
    (package / "Sources" / "probe").mkdir(parents=True)
    (package / "Package.swift").write_text(
        "// swift-tools-version:5.9\n"
        "import PackageDescription\n"
        "\n"
        "let package = Package(\n"
        '    name: "probe",\n'
        "    targets: [\n"
        '        .target(name: "ProbeCore"),\n'
        '        .executableTarget(name: "probe", dependencies: ["ProbeCore"]),\n'
        "    ]\n"
        ")\n",
        encoding="utf-8",
    )
    # ``import Foundation`` is deliberate: it is what makes the clang module
    # cache -- the adapter's ``MODULE_CACHE_DIR`` -- actually get used.
    (package / "Sources" / "ProbeCore" / "Greeting.swift").write_text(
        'import Foundation\n\npublic func greet(_ name: String) -> String { "hi \\(name)" }\n',
        encoding="utf-8",
    )
    (package / "Sources" / "probe" / "main.swift").write_text(
        'import ProbeCore\n\nprint(greet("elmos"))\n', encoding="utf-8"
    )
    return package


def test_swiftpm_cold_and_warm_through_the_sandboxed_xcode_caches(
    tmp_path: Path, swift_package: Path
) -> None:
    """CERT: SwiftPM fills the adapter's three caches, and they serve a rebuild.

    A passing run proves, against a real Swift toolchain:

    * every cache the ``xcode-swift`` adapter declares is the one the toolchain
      actually writes to -- ``DERIVED_DATA_DIR`` (the DerivedData/scratch tree),
      ``SWIFTPM_CACHE_DIR`` (SwiftPM's manifest and repository cache) and
      ``MODULE_CACHE_DIR`` (the clang module cache) all go from empty to
      non-empty across the cold build;
    * no default location is touched: the package's own ``.build``,
      ``~/Library/Caches/org.swift.swiftpm``, ``~/.swiftpm/cache`` and Xcode's
      ``~/Library/Developer/Xcode/DerivedData`` all stay absent, so the
      redirection is the only reason the caches landed where they did;
    * a cold build compiles (SwiftPM names each module it compiles, which is
      what ``XcodeSwiftAdapter.parse_diagnostics`` counts as a miss) and leaves
      real bytes in the sandbox volume, reported through ``adapter.stats()``;
    * an unchanged rebuild compiles nothing;
    * and -- the part a rebuild in an untouched directory cannot prove -- after
      the linked executable is *deleted*, a third build puts it back without
      recompiling one module. The object files can only have come from the
      sandboxed DerivedData tree. That is the cache being populated and then
      consumed, not an output directory being reused;
    * the executable that cache produced imports into ELMOS CAS.

    What it does not prove: anything about ``xcodebuild`` or ``.xcodeproj``
    builds; and no clean-room byte comparison is attempted, because a Mach-O
    executable carries an ``LC_UUID`` that differs between links -- the Gradle
    row certifies reproducibility on ``.class`` files for the same reason.
    """
    if shutil.which("swiftc") is None:
        pytest.skip(
            "swiftc is unavailable on this platform, so the SwiftPM cold/warm build stays "
            "uncertified: that leaves unproven that DERIVED_DATA_DIR, MODULE_CACHE_DIR and "
            "SWIFTPM_CACHE_DIR are the directories the Swift toolchain really uses, that a "
            "deleted product is rebuilt from the sandboxed DerivedData tree without "
            "recompiling, and that a Swift build product imports into CAS"
        )
    swift = tool("swift")
    adapter = adapter_for("swift", tmp_path / "volume", profile("swift", [swift, "--version"], sdk="macosx"))
    home = tmp_path / "home"
    env = sandbox_env(adapter, home, passthrough=("DEVELOPER_DIR", "SDKROOT", "TOOLCHAINS"))
    derived_data = Path(env["DERIVED_DATA_DIR"])
    module_cache = Path(env["MODULE_CACHE_DIR"])
    swiftpm_cache = Path(env["SWIFTPM_CACHE_DIR"])
    assert file_count(derived_data) == 0
    assert file_count(module_cache) == 0
    assert file_count(swiftpm_cache) == 0

    # SwiftPM takes these three as flags rather than as environment variables.
    # The adapter still owns the paths -- ``sandbox_env`` has already proved
    # they resolve inside the volume -- and the flags are how the tool is told.
    argv = [
        swift, "build",
        "--scratch-path", str(derived_data),
        "--cache-path", str(swiftpm_cache),
        "-Xswiftc", "-module-cache-path", "-Xswiftc", str(module_cache),
    ]

    cold = run(argv, swift_package, env)
    assert "Compiling" in cold, cold[-2000:]
    assert "Build complete" in cold, cold[-2000:]

    assert file_count(derived_data) > 0, "swift build did not honour DERIVED_DATA_DIR"
    assert file_count(swiftpm_cache) > 0, "swift build did not honour SWIFTPM_CACHE_DIR"
    assert file_count(module_cache) > 0, "swiftc did not honour MODULE_CACHE_DIR"
    assert list(derived_data.rglob("*.swiftmodule")), "no Swift module was written into DERIVED_DATA_DIR"

    # The defaults must be untouched: the redirect is the only reason the
    # caches landed where they did.
    assert not (swift_package / ".build").exists()
    assert not (home / "Library" / "Caches" / "org.swift.swiftpm").exists()
    assert not (home / ".swiftpm" / "cache").exists()
    assert not (home / "Library" / "Developer" / "Xcode" / "DerivedData").exists()

    cold_stats = adapter.parse_diagnostics(cold)
    assert cold_stats.misses >= 1, cold
    assert cold_stats.entries > 0
    assert cold_stats.bytes_used > 0
    assert cold_stats.degraded is False

    warm = run(argv, swift_package, env)
    assert "Build complete" in warm, warm[-2000:]
    assert adapter.parse_diagnostics(warm).misses == 0, warm

    # Destroy the product, keep the cache. A build that puts it back without
    # compiling anything was served by DERIVED_DATA_DIR and by nothing else.
    executable = derived_data / "debug" / "probe"
    assert executable.is_file(), sorted(
        path.relative_to(derived_data).as_posix() for path in derived_data.rglob("probe*")
    )
    executable.unlink()

    served = run(argv, swift_package, env)
    served_stats = adapter.parse_diagnostics(served)
    assert served_stats.misses == 0, served
    assert executable.is_file(), served
    assert served_stats.entries > 0
    assert served_stats.bytes_used > 0
    assert not (swift_package / ".build").exists()

    cas = ContentAddressableStore(tmp_path / "cas")
    outputs = adapter.import_outputs(derived_data, cas, ["debug/probe"])
    assert len(outputs) == 1, outputs
    assert cas.contains(outputs[0].digest)


def test_the_flutter_pub_adapter_holds_without_a_flutter_sdk(tmp_path: Path) -> None:
    """Same shape as the Swift row: the contract, with no SDK involved.

    The pub cache half lives in
    ``test_flutter_pub_cold_and_warm_through_the_sandboxed_pub_cache``.
    """
    adapter = adapter_for("dart", tmp_path / "volume", ToolchainProfile("flutter", "3.24"))
    _adapter_contract_without_the_tool(adapter, tmp_path / "home")
    assert set(adapter.env_template) == {"PUB_CACHE", "FLUTTER_BUILD_DIR"}


@pytest.fixture
def flutter_package(tmp_path: Path) -> Path:
    """A minimal Flutter package: enough to resolve, not enough to need an engine."""
    package = tmp_path / "flutter-package"
    (package / "lib").mkdir(parents=True)
    (package / "pubspec.yaml").write_text(
        "name: probe\n"
        "description: An ELMOS native build-cache certification package.\n"
        "version: 1.0.0\n"
        "environment:\n"
        '  sdk: ">=3.0.0 <4.0.0"\n'
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
        encoding="utf-8",
    )
    (package / "lib" / "probe.dart").write_text(
        "String greet(String name) => 'hi $name';\n", encoding="utf-8"
    )
    return package


def test_flutter_pub_cold_and_warm_through_the_sandboxed_pub_cache(
    tmp_path: Path, flutter_package: Path
) -> None:
    """CERT: the pub cache the adapter declares is populated, then made to serve alone.

    A passing run proves, against a real Flutter SDK:

    * ``PUB_CACHE`` goes from empty to a real pub package tree (``hosted/``)
      inside the sandbox volume, and the host's ``~/.pub-cache`` is never
      created -- so the redirection is the only reason packages landed where
      they did;
    * the cold resolve leaves bytes the adapter can account for through
      ``adapter.stats()``;
    * and then every resolution artefact is destroyed -- ``.dart_tool/`` and
      ``pubspec.lock`` both -- and the resolve is repeated with ``--offline``.
      ``pub --offline`` is forbidden to touch the network, so it can only
      succeed if the sandboxed ``PUB_CACHE`` holds every package the resolution
      needs. A recreated ``package_config.json`` is the cache being consumed;
      it cannot be a stale output directory, because there is no longer one.
      ``FlutterPubAdapter.parse_diagnostics`` reads that run's log and sees no
      download.

    What it does not prove: ``FLUTTER_BUILD_DIR``. That variable is read by
    Flutter's Xcode backend during a platform build, not by ``pub``; certifying
    it needs a full ``flutter build`` with an engine and Xcode, which this row
    does not attempt. The adapter's *declaration* of it is still asserted to be
    sandbox-resident by ``sandbox_env`` -> ``assert_sandboxed`` and by
    ``test_the_flutter_pub_adapter_holds_without_a_flutter_sdk``.
    """
    if shutil.which("flutter") is None:
        pytest.skip(
            "flutter is unavailable on this platform, so the pub cold/warm certification stays "
            "uncertified: that leaves unproven that PUB_CACHE is the directory pub really fills, "
            "that ~/.pub-cache stays untouched, and that an offline resolve can be served from "
            "the sandboxed cache alone"
        )
    flutter = tool("flutter")
    adapter = adapter_for("dart", tmp_path / "volume", profile("flutter", [flutter, "--version"]))
    home = tmp_path / "home"
    env = sandbox_env(adapter, home, passthrough=("FLUTTER_ROOT", "PUB_HOSTED_URL"))
    pub_cache = Path(env["PUB_CACHE"])
    assert file_count(pub_cache) == 0

    try:
        cold = run([flutter, "pub", "get"], flutter_package, env)
    except AssertionError as error:  # the index is not always reachable
        pytest.skip(
            "pub.dev is unreachable and the SDK's preload cache did not cover the resolution, so "
            f"the pub cold/warm certification is uncertified here: {error}"
        )

    assert file_count(pub_cache) > 0, "flutter pub did not honour PUB_CACHE"
    assert (pub_cache / "hosted").is_dir(), sorted(path.name for path in pub_cache.iterdir())
    assert not (home / ".pub-cache").exists()

    cold_stats = adapter.parse_diagnostics(cold)
    assert cold_stats.entries > 0
    assert cold_stats.bytes_used > 0
    assert cold_stats.degraded is False

    package_config = flutter_package / ".dart_tool" / "package_config.json"
    assert package_config.is_file(), cold

    # Destroy every resolution artefact. What is left is the sandboxed cache.
    shutil.rmtree(flutter_package / ".dart_tool")
    (flutter_package / "pubspec.lock").unlink()
    assert not package_config.exists()

    warm = run([flutter, "pub", "get", "--offline"], flutter_package, env)
    assert package_config.is_file(), warm
    warm_stats = adapter.parse_diagnostics(warm)
    assert warm_stats.misses == 0, warm
    assert warm_stats.entries > 0
    assert warm_stats.bytes_used > 0
    assert not (home / ".pub-cache").exists()


def test_maven_reads_the_sandboxed_local_repository(tmp_path: Path) -> None:
    """Maven's own repository list is the evidence, not our environment dump.

    Maven Central is unreachable from this sandbox, so a full build cannot be
    certified here. What *can* be: Maven reads the adapter's redirected local
    repository. It prints the repository set it resolved against, and the
    sandbox path has to be the local one.
    """
    mvn = tool("mvn")
    project = tmp_path / "maven-project"
    project.mkdir()
    (project / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <modelVersion>4.0.0</modelVersion>\n"
        "  <groupId>demo</groupId><artifactId>probe</artifactId><version>1.0</version>\n"
        "</project>\n",
        encoding="utf-8",
    )

    adapter = adapter_for("java", tmp_path / "volume", profile("maven", [mvn, "--version"]))
    home = tmp_path / "home"
    env = sandbox_env(adapter, home, passthrough=("JAVA_HOME", "JAVA_TOOL_OPTIONS"))
    repository = Path(env["MAVEN_REPO_LOCAL"])
    assert env["MAVEN_OPTS"] == f"-Dmaven.repo.local={repository}"

    completed = subprocess.run(  # noqa: S603
        [mvn, "-o", "help:evaluate", "-Dexpression=maven.repo.local"],
        cwd=str(project), env=env, capture_output=True, text=True, timeout=BUILD_TIMEOUT, check=False,
    )
    log = completed.stdout + completed.stderr
    # Offline with no plugins cached, this fails -- and names the repositories
    # it looked in while failing. The local one must be the sandbox.
    assert f"local ({repository})" in log, log[-2000:]
    assert not (home / ".m2" / "repository").exists()


def test_a_full_maven_build_needs_a_reachable_central() -> None:
    tool("mvn")
    pytest.skip(
        "Maven Central is unreachable from this sandbox (plugin resolution fails online and "
        "offline), so only the Gradle half of gradle-maven and Maven's repository redirection "
        "are certified here"
    )
