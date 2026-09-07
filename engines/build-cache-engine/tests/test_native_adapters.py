"""Native build-cache adapters: sandboxing, isolation and clean-room checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.native_adapters import (
    ADAPTERS,
    LANGUAGE_ADAPTERS,
    NativeCacheRegistry,
    ToolchainProfile,
    adapter_for,
    compare_clean_room,
)

TOOLCHAIN = ToolchainProfile(
    name="dotnet",
    version="10.0.100",
    target_triple="x86_64-linux",
    sdk="net10.0",
    flags=("-c", "Release"),
    lockfile_digests={"packages.lock.json": "sha256:" + "1" * 64},
)


def test_all_declared_adapters_exist() -> None:
    assert set(ADAPTERS) == {
        "gradle-maven",
        "msbuild-nuget",
        "cargo-sccache",
        "cmake-ccache",
        "typescript-node",
        "python-wheel",
        "xcode-swift",
        "flutter-pub",
        "go-build",
    }
    for language in (
        "java", "kotlin", "csharp", "rust", "cpp", "typescript", "javascript",
        "python", "swift", "objectivec", "dart", "go",
    ):
        assert LANGUAGE_ADAPTERS[language] in ADAPTERS or LANGUAGE_ADAPTERS[language] == "generic"


def test_cache_paths_are_redirected_into_the_sandbox(tmp_path: Path) -> None:
    adapter = adapter_for("csharp", tmp_path / "volume", TOOLCHAIN)
    environment = adapter.environment()
    assert environment
    adapter.assert_sandboxed(environment)
    for value in environment.values():
        assert str(adapter.root) in value


def test_an_escaping_cache_path_is_a_contract_violation(tmp_path: Path) -> None:
    adapter = adapter_for("csharp", tmp_path / "volume", TOOLCHAIN)
    hostile = dict(adapter.environment())
    hostile["NUGET_PACKAGES"] = str(Path.home() / ".nuget")
    with pytest.raises(ContractViolation, match="escapes the sandbox"):
        adapter.assert_sandboxed(hostile)


def test_unset_cache_variable_is_rejected(tmp_path: Path) -> None:
    adapter = adapter_for("rust", tmp_path / "volume", ToolchainProfile("cargo", "1.80"))
    partial = dict(adapter.environment())
    partial.pop("CARGO_HOME")
    with pytest.raises(ContractViolation, match="is unset"):
        adapter.assert_sandboxed(partial)


def test_toolchain_and_trust_domain_isolate_writable_caches(tmp_path: Path) -> None:
    registry = NativeCacheRegistry(tmp_path / "volume", "official")
    baseline = registry.get("csharp", TOOLCHAIN)
    upgraded = registry.get(
        "csharp", ToolchainProfile("dotnet", "10.0.200", "x86_64-linux", "net10.0", ("-c", "Release"))
    )
    fork = NativeCacheRegistry(tmp_path / "volume", "fork").get("csharp", TOOLCHAIN)

    assert baseline.root != upgraded.root
    assert baseline.root != fork.root


def test_adapter_participates_in_the_fingerprint(tmp_path: Path) -> None:
    registry = NativeCacheRegistry(tmp_path / "volume")
    first = registry.get("rust", ToolchainProfile("cargo", "1.80"))
    contribution = registry.fingerprint_contribution()
    assert contribution["cargo-sccache"] == first.fingerprint_digest()

    other = NativeCacheRegistry(tmp_path / "volume").get("rust", ToolchainProfile("cargo", "1.81"))
    assert other.fingerprint_digest() != first.fingerprint_digest()


def test_incompatible_cache_is_wiped_on_a_toolchain_change(tmp_path: Path) -> None:
    adapter = adapter_for("rust", tmp_path / "volume", ToolchainProfile("cargo", "1.81"))
    artefact = adapter.root / "sccache" / "object.bin"
    artefact.parent.mkdir(parents=True, exist_ok=True)
    artefact.write_bytes(b"stale object")

    assert adapter.invalidate_if_incompatible({"toolchain_digest": "sha256:" + "9" * 64}) is True
    assert not artefact.exists()
    assert adapter.invalidate_if_incompatible({"toolchain_digest": adapter.toolchain.digest()}) is False


@pytest.mark.parametrize(
    ("language", "log", "hits", "misses"),
    [
        ("rust", "Cache hits         42\nCache misses       7\n", 42, 7),
        ("cpp", "cache hit (direct)                 12\ncache miss                          3\n", 12, 3),
        ("python", "Using cached wheel\nUsing cached sdist\nDownloading pkg\n", 2, 1),
        ("dart", "pkg 1.0 (cached)\nDownloading other\n", 1, 1),
    ],
)
def test_native_diagnostics_are_parsed(
    tmp_path: Path, language: str, log: str, hits: int, misses: int
) -> None:
    adapter = adapter_for(language, tmp_path / "volume", ToolchainProfile("tool", "1"))
    stats = adapter.parse_diagnostics(log)
    assert stats.hits == hits
    assert stats.misses == misses


def test_build_outputs_are_imported_into_cas(tmp_path: Path, cas: ContentAddressableStore) -> None:
    adapter = adapter_for("typescript", tmp_path / "volume", ToolchainProfile("tsc", "5.6"))
    build = tmp_path / "build"
    (build / "dist").mkdir(parents=True)
    (build / "dist" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (build / "dist" / "app.d.ts").write_text("export {}", encoding="utf-8")

    outputs = adapter.import_outputs(build, cas)
    assert {output.logical_path for output in outputs} == {"dist/app.js", "dist/app.d.ts"}
    for output in outputs:
        assert cas.contains(output.digest)


def test_clean_room_environment_disables_every_cache(tmp_path: Path) -> None:
    adapter = adapter_for("java", tmp_path / "volume", ToolchainProfile("gradle", "8.9"))
    environment = adapter.clean_room_environment()
    assert environment["GRADLE_OPTS"] == "-Dorg.gradle.caching=false"
    assert environment["GRADLE_USER_HOME"].endswith("null")


def test_clean_room_comparison_detects_divergence(tmp_path: Path, cas: ContentAddressableStore) -> None:
    adapter = adapter_for("typescript", tmp_path / "volume", ToolchainProfile("tsc", "5.6"))
    build = tmp_path / "build"
    (build / "dist").mkdir(parents=True)
    (build / "dist" / "app.js").write_text("console.log(1)", encoding="utf-8")
    cached = adapter.import_outputs(build, cas)

    assert compare_clean_room(cached, cached).matched
    (build / "dist" / "app.js").write_text("console.log(2)", encoding="utf-8")
    clean = adapter.import_outputs(build, cas)
    comparison = compare_clean_room(cached, clean)
    assert not comparison.matched
    assert comparison.differing_paths == ("dist/app.js",)


def test_adapter_failure_degrades_to_a_clean_build(tmp_path: Path) -> None:
    adapter = adapter_for("rust", tmp_path / "volume", ToolchainProfile("cargo", "1.80"))
    stats = adapter.degrade("sccache socket unavailable")
    assert stats.degraded is True
    assert adapter.stats().degraded is True
    assert "sccache" in adapter.stats().detail


def test_msbuild_counts_both_of_msbuilds_skip_messages_as_not_a_miss(tmp_path: Path) -> None:
    """A target that did nothing did not miss the cache.

    MSBuild emits two different skip lines and only one of them is incremental
    reuse. ``because all output files are up-to-date`` is a genuine cache hit;
    ``because it has no inputs`` means the target had nothing to do at all --
    which is what ``CoreResGen`` does in a project with no resources, and what
    ``_CopyFilesMarkedCopyLocal`` does with no copy-local references.

    Counting only the first as a skip made those no-op targets register as
    *misses on a warm build*. Worse, which of the four headers takes that path
    is decided by the host SDK's target set, so an ``assert misses == 0`` was
    satisfiable on the SDK the adapter was written against and unsatisfiable on
    another -- a platform-dependent failure with no product cause.

    ``hits`` deliberately still counts only the up-to-date message: a no-op
    target is not evidence the cache served anything.
    """

    # Reached through the registry rather than ``adapter_for``, which takes a
    # *language* and would silently hand back the generic adapter for an
    # adapter id -- and a generic adapter parses nothing, so the assertions
    # below would pass vacuously.
    adapter = ADAPTERS["msbuild-nuget"](tmp_path / "volume", TOOLCHAIN, "default")
    assert adapter.adapter_id == "msbuild-nuget"
    warm_log = (
        "  CoreCompile:\n"
        '    Skipping target "CoreCompile" because all output files are up-to-date.\n'
        "  CoreResGen:\n"
        '    Skipping target "CoreResGen" because it has no inputs.\n'
        "  _CopyFilesMarkedCopyLocal:\n"
        '    Skipping target "_CopyFilesMarkedCopyLocal" because it has no inputs.\n'
    )

    warm = adapter.parse_diagnostics(warm_log)

    assert warm.misses == 0
    assert warm.hits == 1

    # And the inverse still reads as work: a header with no skip line under it
    # is an executed target, so the parser has not been blunted into always
    # answering zero.
    cold = adapter.parse_diagnostics("  CoreCompile:\n  CoreResGen:\n")
    assert cold.misses == 2
    assert cold.hits == 0


def test_flutter_pub_does_not_read_its_own_banner_as_a_download(tmp_path: Path) -> None:
    """``Downloading packages...`` is a banner, not evidence of a fetch.

    ``pub get --offline`` is forbidden to touch the network, yet it still prints
    that header above the ``+ pkg`` lines. Counting the bare word therefore
    scored a miss on a resolve served entirely from the sandboxed cache -- which
    is exactly what the Flutter certification hit on a real SDK: an offline
    resolve, seven packages restored from cache, ``misses=1``.

    Same shape as the MSBuild ``_SKIPPED`` defect: a parser reading a banner
    instead of a signal. A genuine fetch names the package.
    """

    adapter = ADAPTERS["flutter-pub"](
        tmp_path / "volume", ToolchainProfile("flutter", "3.44.1"), "default"
    )

    offline = (
        "Resolving dependencies...\n"
        "Downloading packages...\n"
        "+ characters 1.4.1\n"
        "+ collection 1.19.1\n"
        "+ flutter 0.0.0 from sdk flutter\n"
        "Changed 7 dependencies!\n"
    )
    assert adapter.parse_diagnostics(offline).misses == 0

    # And a real fetch still registers, so the parser was not blunted into
    # always answering zero.
    fetched = (
        "Resolving dependencies...\n"
        "Downloading packages...\n"
        "Downloading collection 1.19.1...\n"
        "Downloading meta 1.18.0...\n"
        "Changed 2 dependencies!\n"
    )
    assert adapter.parse_diagnostics(fetched).misses == 2
