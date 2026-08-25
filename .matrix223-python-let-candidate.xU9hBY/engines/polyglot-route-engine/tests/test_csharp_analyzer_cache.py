from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import pytest

from elmos_polyglot_route import native
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.toolchains import ExactToolchain


@pytest.fixture(autouse=True)
def _isolated_analyzer_binary_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give every test in this file its own cross-process analyzer cache.

    `_persistent_analyzer_root` resolves under the account's real home
    directory, deliberately -- it must not be redirectable by editing `HOME`.
    That is right in production and wrong in a test, which would otherwise read
    and write the developer's actual cache and let one test's build satisfy the
    next test's call.

    Two tests below assert how many build commands a single call issues.  That
    assertion is correct, and enabling the cache does not make it incorrect;
    what makes it incorrect is a cache shared across tests.  So the fix here is
    isolation, not a weaker assertion.
    """
    root = tmp_path / "analyzer-binary-cache"

    def isolated_root(kind: str, key: str) -> Path | None:
        if not native._analyzer_binary_cache_enabled():
            return None
        directory = root / kind / key
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        return directory

    def isolated_cache(kind: str, key: str, names: Sequence[str]) -> tuple[Path, ...] | None:
        directories = []
        for name in names:
            directory = root / kind / key / name
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directories.append(directory)
        return tuple(directories)

    # Both entry points, not just one.  `_csharp_package_restore_cache` reaches
    # `_toolchain_build_cache` directly rather than going through
    # `_persistent_analyzer_root`, so patching only the latter would leave the
    # NuGet restore cache writing into the real home directory -- which is the
    # exact cross-test leakage this fixture exists to prevent.
    monkeypatch.setattr(native, "_persistent_analyzer_root", isolated_root)
    monkeypatch.setattr(native, "_toolchain_build_cache", isolated_cache)
    monkeypatch.delenv(native._ANALYZER_BINARY_CACHE_ENV, raising=False)


def _fake_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, ExactToolchain, Path]:
    repository = tmp_path / "repository"
    engine = repository / "engines" / "dotnet-engine"
    package_id = "Example.Package"
    normalized_id = package_id.casefold()
    version = "1.2.3"
    package_bytes = b"verified-fake-nupkg"
    raw_sha512 = base64.b64encode(hashlib.sha512(package_bytes).digest()).decode("ascii")
    lock_content_hash = base64.b64encode(b"L" * hashlib.sha512().digest_size).decode("ascii")
    lock = {
        "version": 2,
        "dependencies": {
            "net10.0": {
                package_id: {
                    "type": "Direct",
                    "resolved": version,
                    "contentHash": lock_content_hash,
                }
            }
        },
    }
    inputs = {
        "global.json": '{"sdk":{"version":"10.0.301","rollForward":"latestPatch"}}\n',
        "Directory.Build.props": (
            "<Project>\n  <PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup>\n</Project>\n"
        ),
        "Directory.Packages.props": (
            '<Project><ItemGroup><PackageVersion Include="Microsoft.CodeAnalysis.CSharp.Workspaces" '
            'Version="5.6.0" /></ItemGroup></Project>\n'
        ),
        "src/Elmos.Dotnet.SemanticCli/Elmos.Dotnet.SemanticCli.csproj": (
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType></PropertyGroup>'
            '<ItemGroup><PackageReference Include="Microsoft.CodeAnalysis.CSharp.Workspaces" /></ItemGroup>'
            "</Project>\n"
        ),
        "src/Elmos.Dotnet.SemanticCli/Program.cs": 'Console.WriteLine("semantic-cli");\n',
        "src/Elmos.Dotnet.SemanticCli/packages.lock.json": json.dumps(lock, sort_keys=True) + "\n",
    }
    for relative, content in inputs.items():
        path = engine / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
    for relative, binary_content in (
        ("src/Elmos.Dotnet.SemanticCli/bin/poison.dll", b"repository-bin-must-not-run"),
        ("src/Elmos.Dotnet.SemanticCli/obj/poison.targets", b"repository-obj-must-not-load"),
    ):
        path = engine / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(binary_content)
    dotnet = tmp_path / "dotnet"
    dotnet_bytes = b"exact-dotnet-10.0.301"
    dotnet.write_bytes(dotnet_bytes)
    dotnet.chmod(0o500)
    package_cache = tmp_path / "package-cache"
    package_directory = package_cache / normalized_id / version
    package_directory.mkdir(parents=True)
    filename = f"{normalized_id}.{version}.nupkg"
    (package_directory / filename).write_bytes(package_bytes)
    (package_directory / f"{filename}.sha512").write_text(raw_sha512 + "\n", encoding="ascii")
    (package_directory / ".nupkg.metadata").write_text(
        json.dumps(
            {
                "version": 2,
                "contentHash": lock_content_hash,
                "source": "https://api.nuget.org/v3/index.json",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(native, "REPOSITORY_ROOT", repository)
    monkeypatch.setattr(native, "_csharp_package_cache_root", lambda: package_cache)
    toolchain = ExactToolchain(
        "csharp",
        "10.0.301",
        str(dotnet),
        profile=("fake-dotnet-bundle=v1",),
        executable_sha256=hashlib.sha256(dotnet_bytes).hexdigest(),
    )
    bundle = {
        "muxer": {"sha256": toolchain.executable_sha256},
        "sdk": {"sha256": "fake-sdk-v1"},
        "hostfxr": {"sha256": "fake-hostfxr-v1"},
        "runtime": {"sha256": "fake-runtime-v1"},
        "reference_pack": {"sha256": "fake-reference-pack-v1"},
        "apphost_pack": {"sha256": "fake-apphost-pack-v1"},
    }

    def verify(candidate: ExactToolchain) -> dict[str, object]:
        if candidate != toolchain:
            raise RouteError("EXACT_TOOLCHAIN_DOTNET_IDENTITY_MISMATCH")
        return cast(dict[str, object], json.loads(json.dumps(bundle)))

    monkeypatch.setattr(native, "verify_csharp_toolchain", verify)
    native._cleanup_csharp_analyzer()
    return engine, toolchain, package_directory


def _successful_build_runner(commands: list[list[str]]) -> Any:
    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "build" in command:
            output = Path(command[command.index("--output") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / native._CSHARP_ANALYZER_ENTRYPOINT).write_bytes(b"private-semantic-cli")
            (output / "Elmos.Dotnet.SemanticCli.deps.json").write_bytes(b'{"runtimeTarget":{}}\n')
            (output / "Elmos.Dotnet.SemanticCli.runtimeconfig.json").write_bytes(b'{"runtimeOptions":{}}\n')
            dependency = output / "runtimes" / "test" / "dependency.dll"
            dependency.parent.mkdir(parents=True)
            dependency.write_bytes(b"private-dependency")
        return subprocess.CompletedProcess(command, 0, "", "")

    return run


def test_csharp_analyzer_concurrent_first_use_builds_once_and_runs_private_dll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, toolchain, _ = _fake_engine(tmp_path, monkeypatch)
    commands: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _successful_build_runner(commands))

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: native._csharp_analyzer(toolchain), range(8)))
        binaries = {binary for binary, _ in results}
        assert len(binaries) == 1
        binary = binaries.pop()
        assert not binary.is_relative_to(engine.resolve())
        assert [command[1] for command in commands] == ["restore", "build"]
        assert "--locked-mode" in commands[0]
        assert "--disable-parallel" in commands[0]
        assert "--no-restore" in commands[1]
        assert "--no-incremental" in commands[1]
        assert "--disable-build-servers" in commands[1]
        assert all("/bin/" not in argument and "/obj/" not in argument for command in commands for argument in command)
        receipt = results[0][1]
        assert [item["path"] for item in receipt["source_inputs"]["files"]] == list(native._CSHARP_ANALYZER_INPUTS)
        assert receipt["toolchain"]["executable_sha256"].startswith("sha256:")
        assert set(receipt["toolchain"]["bundle"]) >= {
            "sdk",
            "hostfxr",
            "runtime",
            "reference_pack",
            "apphost_pack",
        }
        assert receipt["build"]["repository_bin_obj_used"] is False
        assert receipt["output"]["file_count"] == 4

        executions: list[list[str]] = []

        def execute(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
            assert cwd == binary.parent
            assert timeout == 120
            executions.append(command)
            return {"analyzer_version": "5.6.0"}

        monkeypatch.setattr(native, "_run", execute)
        first, _ = native._run_csharp_semantic_cli(toolchain, ["source.cs", "--inventory"])
        second, _ = native._run_csharp_semantic_cli(toolchain, ["source.cs", "Add"])
        assert first["analyzer_version"] == second["analyzer_version"]
        assert "dotnet-bundle=sha256:" in first["analyzer_version"]
        assert len(commands) == 2
        assert len(executions) == 2
        assert all(command[:2] == [toolchain.executable, str(binary)] for command in executions)
        assert all("run" not in command and "--project" not in command for command in executions)
        assert (engine / "src/Elmos.Dotnet.SemanticCli/bin/poison.dll").read_bytes() == b"repository-bin-must-not-run"
        assert (
            engine / "src/Elmos.Dotnet.SemanticCli/obj/poison.targets"
        ).read_bytes() == b"repository-obj-must-not-load"
    finally:
        temporary_root = native._CSHARP_ANALYZER_BINARY.parent.parent if native._CSHARP_ANALYZER_BINARY else None
        native._cleanup_csharp_analyzer()
    assert temporary_root is not None
    assert not temporary_root.exists()


@pytest.mark.parametrize("binary_cache", (False, True), ids=("cache-off", "cache-on"))
@pytest.mark.parametrize(
    ("drift", "error"),
    (
        ("input", "CSHARP_ANALYZER_INPUT_CHANGED_DURING_PROCESS"),
        ("output", "CSHARP_ANALYZER_OUTPUT_CHANGED"),
        ("toolchain", "CSHARP_ANALYZER_TOOLCHAIN_DIGEST_MISMATCH"),
    ),
)
def test_csharp_analyzer_cache_rejects_content_drift_without_rebuilding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
    error: str,
    binary_cache: bool,
) -> None:
    # Drift detection is the property under test, and it must hold identically
    # whether or not the analyzer binary came from a cross-process cache.
    if binary_cache:
        monkeypatch.setenv(native._ANALYZER_BINARY_CACHE_ENV, "1")
    engine, toolchain, _ = _fake_engine(tmp_path, monkeypatch)
    commands: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _successful_build_runner(commands))

    try:
        binary, _ = native._csharp_analyzer(toolchain)
        if drift == "input":
            program = engine / "src/Elmos.Dotnet.SemanticCli/Program.cs"
            content = program.read_bytes()
            program.write_bytes(b"X" + content[1:])
        elif drift == "output":
            content = binary.read_bytes()
            binary.write_bytes(b"X" + content[1:])
        else:
            executable = Path(toolchain.executable)
            content = executable.read_bytes()
            executable.chmod(0o700)
            executable.write_bytes(b"X" + content[1:])
            executable.chmod(0o500)

        with pytest.raises(RouteError, match=error):
            native._csharp_analyzer(toolchain)
        assert len(commands) == 2
    finally:
        native._cleanup_csharp_analyzer()


@pytest.mark.parametrize("binary_cache", (False, True), ids=("cache-off", "cache-on"))
def test_csharp_analyzer_cache_rejects_same_version_bundle_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    binary_cache: bool,
) -> None:
    if binary_cache:
        monkeypatch.setenv(native._ANALYZER_BINARY_CACHE_ENV, "1")
    _, toolchain, _ = _fake_engine(tmp_path, monkeypatch)
    commands: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _successful_build_runner(commands))

    try:
        native._csharp_analyzer(toolchain)
        original = cast(
            Callable[[ExactToolchain], dict[str, object]],
            native.__dict__["verify_csharp_toolchain"],
        )

        def replaced(candidate: ExactToolchain) -> dict[str, object]:
            bundle = original(candidate)
            changed = cast(dict[str, Any], json.loads(json.dumps(bundle)))
            changed["sdk"]["sha256"] = "same-version-replacement"
            return cast(dict[str, object], changed)

        monkeypatch.setattr(native, "verify_csharp_toolchain", replaced)
        with pytest.raises(RouteError, match="CSHARP_ANALYZER_TOOLCHAIN_CHANGED_DURING_PROCESS"):
            native._csharp_analyzer(toolchain)
        assert len(commands) == 2
    finally:
        native._cleanup_csharp_analyzer()


def test_csharp_analyzer_build_failure_is_terminal_for_the_process_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, toolchain, _ = _fake_engine(tmp_path, monkeypatch)
    commands: list[list[str]] = []

    def rejected_restore(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, "", "locked restore rejected")

    monkeypatch.setattr(subprocess, "run", rejected_restore)
    try:
        for _ in range(2):
            with pytest.raises(RouteError, match="CSHARP_ANALYZER_RESTORE_FAILED:locked restore rejected"):
                native._csharp_analyzer(toolchain)
        assert len(commands) == 1
        assert native._CSHARP_ANALYZER_BINARY is None
        assert native._CSHARP_ANALYZER_RECEIPT is None
    finally:
        native._cleanup_csharp_analyzer()


@pytest.mark.parametrize(
    ("package_failure", "error"),
    (
        ("missing", "CSHARP_ANALYZER_PACKAGE_CACHE_MISSING"),
        ("digest", "CSHARP_ANALYZER_PACKAGE_NUPKG_SHA512_MISMATCH"),
    ),
)
def test_csharp_analyzer_rejects_unverified_cached_package_before_dotnet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package_failure: str,
    error: str,
) -> None:
    _, toolchain, package_directory = _fake_engine(tmp_path, monkeypatch)
    nupkg = next(package_directory.glob("*.nupkg"))
    if package_failure == "missing":
        nupkg.unlink()
    else:
        content = nupkg.read_bytes()
        nupkg.write_bytes(b"X" + content[1:])
    calls = 0

    def should_not_run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise AssertionError("dotnet must not run")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    try:
        with pytest.raises(RouteError, match=error):
            native._csharp_analyzer(toolchain)
        assert calls == 0
    finally:
        native._cleanup_csharp_analyzer()


def test_csharp_analyzer_rejects_symlinked_build_input_before_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, toolchain, _ = _fake_engine(tmp_path, monkeypatch)
    program = engine / "src/Elmos.Dotnet.SemanticCli/Program.cs"
    target = tmp_path / "outside.cs"
    target.write_text('Console.WriteLine("outside");\n', encoding="utf-8")
    program.unlink()
    program.symlink_to(target)
    calls = 0

    def should_not_run(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise AssertionError("dotnet must not run")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    try:
        with pytest.raises(RouteError, match="CSHARP_ANALYZER_INPUT_UNSAFE"):
            native._csharp_analyzer(toolchain)
        assert calls == 0
    finally:
        native._cleanup_csharp_analyzer()


def test_csharp_analyzer_reuses_a_verified_cross_process_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A warm cache skips the build, and only ever after re-verifying it.

    This is the path the build-count assertions above deliberately do not
    cover: they each start from a cold, per-test cache, so they still see two
    build commands.  Here the second process is simulated by clearing the
    process-local globals, which is the only reason the first call's build was
    remembered at all.
    """
    monkeypatch.setenv(native._ANALYZER_BINARY_CACHE_ENV, "1")
    _, toolchain, _ = _fake_engine(tmp_path, monkeypatch)
    commands: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _successful_build_runner(commands))

    try:
        first_binary, first_receipt = native._csharp_analyzer(toolchain)
        built = len(commands)
        assert built > 0

        # Stand in for a fresh process: same machine, same inputs, no globals.
        native._cleanup_csharp_analyzer()
        second_binary, second_receipt = native._csharp_analyzer(toolchain)

        assert len(commands) == built, "a warm cache must not issue another build"
        assert second_receipt["output"]["sha256"] == first_receipt["output"]["sha256"]
        assert second_binary.name == first_binary.name
        assert second_binary.is_file()
    finally:
        native._cleanup_csharp_analyzer()


def test_csharp_analyzer_cross_process_cache_refuses_a_tampered_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache hit is a re-verification, not an act of trust.

    If a cached output could be swapped for different bytes and still be
    executed, the cache would be a way to defeat exactly the output binding
    `_verify_csharp_analyzer_output` exists to enforce.  So a tampered entry
    must not be reused -- rebuilding instead is the correct outcome.
    """
    monkeypatch.setenv(native._ANALYZER_BINARY_CACHE_ENV, "1")
    _, toolchain, _ = _fake_engine(tmp_path, monkeypatch)
    commands: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _successful_build_runner(commands))

    try:
        native._csharp_analyzer(toolchain)
        built = len(commands)
        native._cleanup_csharp_analyzer()

        # The first call missed and therefore built into a temporary directory,
        # which cleanup has now removed; the copy that matters is the published
        # one, so find it in this test's isolated cache.
        cached = sorted(
            (tmp_path / "analyzer-binary-cache").rglob(native._CSHARP_ANALYZER_ENTRYPOINT)
        )
        assert len(cached) == 1, f"expected exactly one published analyzer, found {cached}"
        target = cached[0]
        honest = target.read_bytes()
        target.write_bytes(b"X" + honest[1:])

        binary, _ = native._csharp_analyzer(toolchain)
        assert len(commands) > built, "a tampered cache entry must be rebuilt, never reused"
        assert binary.read_bytes() == honest, "the tampered bytes must never be handed back"
    finally:
        native._cleanup_csharp_analyzer()
