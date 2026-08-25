"""Native build-cache adapters.

Gradle, MSBuild, Cargo, ccache, TypeScript, pip, Xcode and pub all have their
own incremental caches. Using them makes the underlying build faster; it never
makes an ELMOS result trustworthy. Three rules follow:

* every native cache path is redirected into a sandbox-approved volume, so a
  build cannot read or poison the host's caches;
* compiler, SDK, target triple, lockfiles, flags and the adapter's own
  configuration all participate in the ELMOS fingerprint, so a toolchain bump
  cannot be masked by a warm native cache;
* a clean-room rebuild with every native cache disabled remains a required
  certification check.

An adapter that fails degrades to a clean build. It never fails the run.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .canonical import digest_of, sha256_bytes
from .cas import ContentAddressableStore
from .errors import ContractViolation

SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class ToolchainProfile:
    """The identity a native cache must be keyed by, not merely described with."""

    name: str
    version: str
    target_triple: str = ""
    sdk: str = ""
    flags: tuple[str, ...] = ()
    lockfile_digests: Mapping[str, str] = field(default_factory=dict)

    def digest(self) -> str:
        return digest_of(
            {
                "name": self.name,
                "version": self.version,
                "target_triple": self.target_triple,
                "sdk": self.sdk,
                "flags": sorted(self.flags),
                "lockfile_digests": dict(sorted(self.lockfile_digests.items())),
            }
        )


@dataclass(frozen=True)
class NativeCacheStats:
    adapter: str
    hits: int = 0
    misses: int = 0
    entries: int = 0
    bytes_used: int = 0
    degraded: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "hits": self.hits,
            "misses": self.misses,
            "entries": self.entries,
            "bytes_used": self.bytes_used,
            "degraded": self.degraded,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BuildOutput:
    """What an adapter imports back into ELMOS after a build."""

    logical_path: str
    digest: str
    size: int
    media_type: str = "application/octet-stream"

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_path": self.logical_path,
            "digest": self.digest,
            "size": self.size,
            "media_type": self.media_type,
        }


class NativeBuildCacheAdapter:
    """Base adapter. Subclasses declare paths, env and output patterns."""

    #: Stable adapter identifier; participates in the fingerprint.
    adapter_id: str = "generic"
    #: Environment variables that redirect the tool's cache into the sandbox.
    env_template: dict[str, str] = {}
    #: Directories the adapter owns inside the sandbox volume.
    cache_subdirs: tuple[str, ...] = ("cache",)
    #: Glob patterns for build artifacts worth importing into ELMOS.
    output_patterns: tuple[str, ...] = ()
    #: Files whose digests invalidate this adapter's cache.
    lockfile_names: tuple[str, ...] = ()

    def __init__(self, volume_root: Path, toolchain: ToolchainProfile, trust_domain: str = "default") -> None:
        self.toolchain = toolchain
        self.trust_domain = trust_domain
        # Writable native caches are isolated per trust domain *and* toolchain:
        # a fork's build must not warm the official cache, and a compiler bump
        # must not reuse objects built by the previous one.
        self.root = (
            Path(volume_root) / self.adapter_id / trust_domain / toolchain.digest().split(":", 1)[1][:16]
        )
        self.degraded = False
        self.degraded_reason = ""
        for name in self.cache_subdirs:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    # -- sandboxing -------------------------------------------------------
    def environment(self) -> dict[str, str]:
        """Environment that pins every cache path inside the sandbox volume."""
        env: dict[str, str] = {}
        for key, relative in self.env_template.items():
            env[key] = str((self.root / relative).resolve())
        env.update(self.derived_environment())
        return dict(sorted(env.items()))

    def derived_environment(self) -> dict[str, str]:
        """Variables whose value is not a bare path.

        Some tools take their cache location as a flag rather than as a path
        variable -- Maven's ``-Dmaven.repo.local`` is the one that matters here.
        These are derived from the path variables above, so they are sandboxed
        by construction, but they cannot be checked by ``assert_sandboxed``'s
        path rule and are kept separate for that reason.
        """
        return {}

    def assert_sandboxed(self, environment: Mapping[str, str]) -> None:
        """Fail loudly if any declared cache path escaped the volume."""
        root = self.root.resolve()
        for key in self.env_template:
            value = environment.get(key)
            if value is None:
                raise ContractViolation("native cache variable is unset", adapter=self.adapter_id, key=key)
            resolved = Path(value).resolve()
            if root != resolved and root not in resolved.parents:
                raise ContractViolation(
                    "native cache path escapes the sandbox volume",
                    adapter=self.adapter_id,
                    key=key,
                    path=str(resolved),
                )

    # -- fingerprint ------------------------------------------------------
    def fingerprint(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": SCHEMA_VERSION,
            "toolchain_digest": self.toolchain.digest(),
            "trust_domain": self.trust_domain,
            "env_keys": sorted(self.env_template),
            "lockfiles": sorted(self.lockfile_names),
        }

    def fingerprint_digest(self) -> str:
        return digest_of(self.fingerprint())

    # -- lifecycle --------------------------------------------------------
    def invalidate_if_incompatible(self, previous: Mapping[str, Any] | None) -> bool:
        """Wipe the native cache when the toolchain or lockfiles moved."""
        if previous is None:
            return False
        if previous.get("toolchain_digest") == self.toolchain.digest():
            return False
        for name in self.cache_subdirs:
            target = self.root / name
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
        return True

    def degrade(self, reason: str) -> NativeCacheStats:
        """Fall back to a clean build rather than failing the run."""
        self.degraded = True
        self.degraded_reason = reason
        return NativeCacheStats(self.adapter_id, degraded=True, detail=reason)

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        """Adapters override to read their tool's own hit/miss reporting."""
        return NativeCacheStats(self.adapter_id, detail="no diagnostics parser for this adapter")

    def usage(self) -> tuple[int, int]:
        total = 0
        count = 0
        for path in self.root.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
                count += 1
        return total, count

    def stats(self, hits: int = 0, misses: int = 0) -> NativeCacheStats:
        total, count = self.usage()
        return NativeCacheStats(
            adapter=self.adapter_id,
            hits=hits,
            misses=misses,
            entries=count,
            bytes_used=total,
            degraded=self.degraded,
            detail=self.degraded_reason,
        )

    # -- import -----------------------------------------------------------
    def import_outputs(
        self, build_dir: Path, cas: ContentAddressableStore, patterns: Sequence[str] | None = None
    ) -> list[BuildOutput]:
        """Bring build artifacts into ELMOS CAS so they can be manifested."""
        build_dir = Path(build_dir)
        outputs: list[BuildOutput] = []
        for pattern in patterns or self.output_patterns:
            for path in sorted(build_dir.glob(pattern)):
                if not path.is_file() or path.is_symlink():
                    continue
                digest = cas.put_file(path, artifact_kind="build-output")
                outputs.append(
                    BuildOutput(
                        logical_path=path.relative_to(build_dir).as_posix(),
                        digest=digest,
                        size=path.stat().st_size,
                    )
                )
        return outputs

    def clean_room_environment(self) -> dict[str, str]:
        """Environment for the mandatory no-native-cache certification build."""
        env = {key: os.devnull for key in self.env_template}
        env.update(self.clean_room_flags())
        return dict(sorted(env.items()))

    def clean_room_flags(self) -> dict[str, str]:
        return {}


# --------------------------------------------------------------------------
# concrete adapters
# --------------------------------------------------------------------------
class GradleMavenAdapter(NativeBuildCacheAdapter):
    adapter_id = "gradle-maven"
    env_template = {
        "GRADLE_USER_HOME": "gradle-home",
        "MAVEN_REPO_LOCAL": "maven-repo",
    }
    cache_subdirs = ("gradle-home", "maven-repo", "build-cache")
    output_patterns = ("build/libs/*.jar", "target/*.jar", "build/classes/**/*.class")
    lockfile_names = ("gradle.lockfile", "pom.xml", "build.gradle", "build.gradle.kts")

    def derived_environment(self) -> dict[str, str]:
        # ``MAVEN_REPO_LOCAL`` is this adapter's own name for the directory;
        # ``MAVEN_OPTS`` is what Maven itself reads, and Maven prints the
        # resulting path in its own repository list.
        return {"MAVEN_OPTS": f"-Dmaven.repo.local={(self.root / 'maven-repo').resolve()}"}

    _GRADLE_HIT = re.compile(r"FROM-CACHE|UP-TO-DATE")
    _GRADLE_MISS = re.compile(r"Task .* executed|EXECUTED")

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        hits = len(self._GRADLE_HIT.findall(build_log))
        misses = len(self._GRADLE_MISS.findall(build_log))
        return self.stats(hits, misses)

    def clean_room_flags(self) -> dict[str, str]:
        return {"GRADLE_OPTS": "-Dorg.gradle.caching=false"}


class MsbuildNugetAdapter(NativeBuildCacheAdapter):
    adapter_id = "msbuild-nuget"
    env_template = {"NUGET_PACKAGES": "nuget", "MSBUILDDEBUGPATH": "msbuild"}
    cache_subdirs = ("nuget", "msbuild", "obj")
    output_patterns = ("**/bin/**/*.dll", "**/bin/**/*.exe", "**/*.nupkg")
    lockfile_names = ("packages.lock.json", "Directory.Packages.props")

    # MSBuild at normal verbosity prints a ``TargetName:`` header for every
    # target it *considers*, then -- if it was up to date -- a "Skipping target"
    # line underneath. So the header alone is not a miss: a target counts as
    # executed only when no skip line names it.
    _HIT = re.compile(r"skipping target .* because all output files are up-to-date", re.IGNORECASE)
    _HEADER = re.compile(r"^\s*(CoreCompile|CoreResGen|_CreateAppHost|_CopyFilesMarkedCopyLocal):\s*$", re.MULTILINE)
    _SKIPPED = re.compile(r'Skipping target "(\w+)" because all output files are up-to-date', re.IGNORECASE)

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        skipped = set(self._SKIPPED.findall(build_log))
        executed = [name for name in self._HEADER.findall(build_log) if name not in skipped]
        misses = len(executed) + build_log.count("Building target")
        return self.stats(len(self._HIT.findall(build_log)), misses)

    def clean_room_flags(self) -> dict[str, str]:
        return {"MSBUILD_NO_INCREMENTAL": "1"}


class CargoSccacheAdapter(NativeBuildCacheAdapter):
    adapter_id = "cargo-sccache"
    env_template = {"CARGO_HOME": "cargo-home", "SCCACHE_DIR": "sccache", "CARGO_TARGET_DIR": "target"}
    cache_subdirs = ("cargo-home", "sccache", "target")
    output_patterns = ("target/release/*.rlib", "target/release/*.so", "target/release/*")
    lockfile_names = ("Cargo.lock",)

    _SCCACHE = re.compile(r"Cache hits\s+(\d+)[\s\S]*?Cache misses\s+(\d+)")
    # Cargo's own incremental signal: a crate it did not have to rebuild is
    # reported as ``Fresh``, one it did as ``Compiling``.
    _CARGO_FRESH = re.compile(r"^\s*Fresh\s+\S+", re.MULTILINE)
    _CARGO_COMPILING = re.compile(r"^\s*Compiling\s+\S+", re.MULTILINE)

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        match = self._SCCACHE.search(build_log)
        if match is not None:
            return self.stats(int(match.group(1)), int(match.group(2)))
        return self.stats(
            len(self._CARGO_FRESH.findall(build_log)),
            len(self._CARGO_COMPILING.findall(build_log)),
        )

    def clean_room_flags(self) -> dict[str, str]:
        return {"RUSTC_WRAPPER": "", "SCCACHE_RECACHE": "1"}


class CMakeCcacheAdapter(NativeBuildCacheAdapter):
    adapter_id = "cmake-ccache"
    env_template = {"CCACHE_DIR": "ccache", "CMAKE_BUILD_DIR": "build"}
    cache_subdirs = ("ccache", "build")
    output_patterns = ("build/**/*.a", "build/**/*.so", "build/**/*.o")
    lockfile_names = ("CMakeLists.txt", "conan.lock", "vcpkg.json")

    # ccache 4 reports ``Hits: 1 / 2 (50.00%)``; ccache 3 reports
    # ``cache hit (direct) 1``. Both formats are in the field, so both parse.
    _STATS_V4 = re.compile(r"^\s*Hits:\s+(\d+)\s*/\s*\d+[\s\S]*?^\s*Misses:\s+(\d+)\s*/", re.MULTILINE)
    _STATS_V3 = re.compile(r"cache hit \(direct\)\s+(\d+)[\s\S]*?cache miss\s+(\d+)")

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        for pattern in (self._STATS_V4, self._STATS_V3):
            match = pattern.search(build_log)
            if match is not None:
                return self.stats(int(match.group(1)), int(match.group(2)))
        return self.stats()

    def clean_room_flags(self) -> dict[str, str]:
        return {"CCACHE_DISABLE": "1"}


class TypeScriptNodeAdapter(NativeBuildCacheAdapter):
    adapter_id = "typescript-node"
    env_template = {
        "npm_config_cache": "npm",
        "PNPM_STORE_PATH": "pnpm-store",
        "VITE_CACHE_DIR": "vite",
        "TSBUILDINFO_DIR": "tsbuildinfo",
    }
    cache_subdirs = ("npm", "pnpm-store", "vite", "tsbuildinfo")
    output_patterns = ("dist/**/*.js", "dist/**/*.d.ts", "dist/**/*.map")
    lockfile_names = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json")

    # ``tsc --build --verbose`` says either "is up to date" or "is out of date".
    _UP_TO_DATE = re.compile(r"is up to date", re.IGNORECASE)
    _OUT_OF_DATE = re.compile(r"is out of date|Building project", re.IGNORECASE)
    _NPM_CACHED = re.compile(r"\badded \d+ packages?.*from cache|\bcache hit\b", re.IGNORECASE)

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        return self.stats(
            len(self._UP_TO_DATE.findall(build_log)) + len(self._NPM_CACHED.findall(build_log)),
            len(self._OUT_OF_DATE.findall(build_log)),
        )

    def clean_room_flags(self) -> dict[str, str]:
        return {"TSC_FORCE": "1"}


class PythonWheelAdapter(NativeBuildCacheAdapter):
    adapter_id = "python-wheel"
    env_template = {"PIP_CACHE_DIR": "pip", "UV_CACHE_DIR": "uv"}
    cache_subdirs = ("pip", "uv", "wheels")
    output_patterns = ("dist/*.whl", "dist/*.tar.gz")
    lockfile_names = ("requirements.txt", "poetry.lock", "uv.lock", "Pipfile.lock")

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        return self.stats(build_log.count("Using cached"), build_log.count("Downloading"))

    def clean_room_flags(self) -> dict[str, str]:
        return {"PIP_NO_CACHE_DIR": "1"}


class XcodeSwiftAdapter(NativeBuildCacheAdapter):
    adapter_id = "xcode-swift"
    env_template = {
        "DERIVED_DATA_DIR": "derived-data",
        "MODULE_CACHE_DIR": "module-cache",
        "SWIFTPM_CACHE_DIR": "swiftpm",
    }
    cache_subdirs = ("derived-data", "module-cache", "swiftpm")
    output_patterns = ("**/*.framework/**", "**/*.swiftmodule", ".build/release/*")
    lockfile_names = ("Package.resolved", "Podfile.lock")

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        return self.stats(build_log.count("Cached"), build_log.count("Compiling"))

    def clean_room_flags(self) -> dict[str, str]:
        return {"SWIFT_DETERMINISTIC_HASHING": "1"}


class FlutterPubAdapter(NativeBuildCacheAdapter):
    adapter_id = "flutter-pub"
    env_template = {"PUB_CACHE": "pub-cache", "FLUTTER_BUILD_DIR": "build"}
    cache_subdirs = ("pub-cache", "build")
    output_patterns = ("build/**/*.aab", "build/**/*.apk", "build/**/*.app/**")
    lockfile_names = ("pubspec.lock",)

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        return self.stats(build_log.count("(cached)"), build_log.count("Downloading"))


class GoBuildCacheAdapter(NativeBuildCacheAdapter):
    """Go's own build and module caches.

    ``go build`` is silent on a cache hit and names each package it rebuilds
    under ``-v``, so absence of output *is* the hit signal.
    """

    adapter_id = "go-build"
    env_template = {"GOCACHE": "gocache", "GOMODCACHE": "gomodcache", "GOPATH": "gopath"}
    cache_subdirs = ("gocache", "gomodcache", "gopath", "bin")
    output_patterns = ("bin/*", "*.a", "**/*.test")
    lockfile_names = ("go.mod", "go.sum")

    def parse_diagnostics(self, build_log: str) -> NativeCacheStats:
        rebuilt = [line for line in build_log.splitlines() if line and not line.startswith(("#", " "))]
        return self.stats(hits=0 if rebuilt else 1, misses=len(rebuilt))

    def clean_room_flags(self) -> dict[str, str]:
        return {"GOFLAGS": "-a"}


ADAPTERS: dict[str, type[NativeBuildCacheAdapter]] = {
    adapter.adapter_id: adapter
    for adapter in (
        GradleMavenAdapter,
        MsbuildNugetAdapter,
        CargoSccacheAdapter,
        CMakeCcacheAdapter,
        TypeScriptNodeAdapter,
        PythonWheelAdapter,
        XcodeSwiftAdapter,
        FlutterPubAdapter,
        GoBuildCacheAdapter,
    )
}

#: Target language -> the adapter that usually serves it.
LANGUAGE_ADAPTERS: dict[str, str] = {
    "java": "gradle-maven",
    "kotlin": "gradle-maven",
    "csharp": "msbuild-nuget",
    "rust": "cargo-sccache",
    "cpp": "cmake-ccache",
    "typescript": "typescript-node",
    "javascript": "typescript-node",
    "python": "python-wheel",
    "swift": "xcode-swift",
    "objectivec": "xcode-swift",
    "dart": "flutter-pub",
    "go": "go-build",
    "php": "generic",
}


def adapter_for(
    language: str, volume_root: Path, toolchain: ToolchainProfile, trust_domain: str = "default"
) -> NativeBuildCacheAdapter:
    adapter_id = LANGUAGE_ADAPTERS.get(language, "generic")
    factory = ADAPTERS.get(adapter_id, NativeBuildCacheAdapter)
    return factory(volume_root, toolchain, trust_domain)


class NativeCacheRegistry:
    """Owns adapter lifecycle and the fingerprint contribution they make."""

    def __init__(self, volume_root: Path, trust_domain: str = "default") -> None:
        self.volume_root = Path(volume_root)
        self.trust_domain = trust_domain
        self._adapters: dict[str, NativeBuildCacheAdapter] = {}

    def get(self, language: str, toolchain: ToolchainProfile) -> NativeBuildCacheAdapter:
        key = f"{language}:{toolchain.digest()}"
        if key not in self._adapters:
            self._adapters[key] = adapter_for(language, self.volume_root, toolchain, self.trust_domain)
        return self._adapters[key]

    def fingerprint_contribution(self) -> dict[str, str]:
        return {
            adapter.adapter_id: adapter.fingerprint_digest()
            for adapter in sorted(self._adapters.values(), key=lambda a: a.adapter_id)
        }

    def report(self) -> list[dict[str, Any]]:
        return [adapter.stats().to_dict() for adapter in sorted(self._adapters.values(), key=lambda a: a.adapter_id)]


@dataclass(frozen=True)
class CleanRoomComparison:
    """The certification check native caches can never substitute for."""

    cached_tree_digest: str
    clean_tree_digest: str
    matched: bool
    differing_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cached_tree_digest": self.cached_tree_digest,
            "clean_tree_digest": self.clean_tree_digest,
            "matched": self.matched,
            "differing_paths": list(self.differing_paths),
        }


def compare_clean_room(
    cached_outputs: Iterable[BuildOutput], clean_outputs: Iterable[BuildOutput]
) -> CleanRoomComparison:
    cached = {output.logical_path: output.digest for output in cached_outputs}
    clean = {output.logical_path: output.digest for output in clean_outputs}
    differing = sorted(
        path for path in set(cached) | set(clean) if cached.get(path) != clean.get(path)
    )
    return CleanRoomComparison(
        cached_tree_digest=sha256_bytes(digest_of(cached).encode("utf-8")),
        clean_tree_digest=sha256_bytes(digest_of(clean).encode("utf-8")),
        matched=not differing,
        differing_paths=tuple(differing),
    )
