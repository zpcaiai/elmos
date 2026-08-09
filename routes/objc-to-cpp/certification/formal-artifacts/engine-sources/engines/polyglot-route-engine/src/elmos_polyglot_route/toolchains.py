from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .models import Language, RouteError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def sanitized_subprocess_env(
    *,
    home: Path,
    temp_dir: Path,
    executable_dirs: tuple[Path, ...] = (),
) -> dict[str, str]:
    """Return a deterministic subprocess environment with no ambient hooks."""

    fixed_paths = [
        *executable_dirs,
        Path("/usr/bin"),
        Path("/bin"),
        Path("/usr/sbin"),
        Path("/sbin"),
    ]
    path = os.pathsep.join(str(item) for item in dict.fromkeys(item.resolve() for item in fixed_paths if item.is_dir()))
    return {
        "PATH": path,
        "HOME": str(home.resolve()),
        "TMPDIR": str(temp_dir.resolve()),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "NO_COLOR": "1",
        "CLICOLOR": "0",
        "SOURCE_DATE_EPOCH": "0",
        "ZERO_AR_DATE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "XDG_CACHE_HOME": str((home / ".cache").resolve()),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


@dataclass(frozen=True)
class ExactToolchain:
    language: Language
    version: str
    executable: str
    auxiliary: str | None = None
    profile: tuple[str, ...] = ()
    executable_sha256: str | None = None
    auxiliary_sha256: str | None = None


def _output(
    command: list[str],
    *,
    executable_dirs: tuple[Path, ...] = (),
) -> str:
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-toolchain-env-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=sanitized_subprocess_env(
                    home=home,
                    temp_dir=scratch,
                    executable_dirs=(Path(command[0]).resolve().parent, *executable_dirs),
                ),
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{command[0]}") from error
    if completed.returncode != 0:
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{command[0]}")
    return (completed.stdout + completed.stderr).strip()


_EXPECTED_JAVA_HOME = Path("/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home")
_EXPECTED_JAVA_SHA256 = "2c2aca8d8796794fd92ad9ca0c544e91dfd77487b34dd7f2b1ba0b29d6e57d42"
_EXPECTED_JAVAC_SHA256 = "c4a7ba406f2c6d4f11723954b0070509606b6f016433975d3283105c9acb43db"
_EXPECTED_JAVA_MODULES_SHA256 = "5c27cfb52071cf24c5dbd9823027143c235bcb2e182dce708fd58c4ea49bfbee"
_EXPECTED_JAVA_JVM_SHA256 = "bbe54637903f04770492627e8d4f6051d79bc8591cab70e02dc3b4a9575d0588"
_EXPECTED_JAVA_RELEASE_SHA256 = "7befd86565133fbebfa54138e55ec5b03bb59649ea5dda35d9f9b95265226756"
_EXPECTED_JAVA_BUNDLE_CDHASH_FULL = "5a88122cc14733538f6b92d150fafb7f5b560455bfda0ae83c93a34eef2887e8"
_EXPECTED_JAVA_VERSION = (
    'openjdk version "21.0.11" 2026-04-21\n'
    "OpenJDK Runtime Environment Homebrew (build 21.0.11)\n"
    "OpenJDK 64-Bit Server VM Homebrew (build 21.0.11, mixed mode, sharing)"
)
_EXPECTED_JAVAC_VERSION = "javac 21.0.11"

_EXPECTED_DOTNET_VERSION = "10.0.301"
_EXPECTED_DOTNET_RUNTIME_VERSION = "10.0.9"
_EXPECTED_DOTNET_SHIM = Path("/opt/homebrew/bin/dotnet")
_EXPECTED_DOTNET_CELLAR = Path("/opt/homebrew/Cellar/dotnet/10.0.301")
_EXPECTED_DOTNET_WRAPPER = _EXPECTED_DOTNET_CELLAR / "bin" / "dotnet"
_EXPECTED_DOTNET_ROOT = _EXPECTED_DOTNET_CELLAR / "libexec"
_EXPECTED_DOTNET_MUXER = _EXPECTED_DOTNET_ROOT / "dotnet"
_EXPECTED_DOTNET_SDK = _EXPECTED_DOTNET_ROOT / "sdk" / _EXPECTED_DOTNET_VERSION
_EXPECTED_DOTNET_HOSTFXR = _EXPECTED_DOTNET_ROOT / "host" / "fxr" / _EXPECTED_DOTNET_RUNTIME_VERSION
_EXPECTED_DOTNET_RUNTIME = _EXPECTED_DOTNET_ROOT / "shared" / "Microsoft.NETCore.App" / _EXPECTED_DOTNET_RUNTIME_VERSION
_EXPECTED_DOTNET_REFERENCE_PACK = (
    _EXPECTED_DOTNET_ROOT / "packs" / "Microsoft.NETCore.App.Ref" / _EXPECTED_DOTNET_RUNTIME_VERSION
)
_EXPECTED_DOTNET_APPHOST_PACK = (
    _EXPECTED_DOTNET_ROOT / "packs" / "Microsoft.NETCore.App.Host.osx-arm64" / _EXPECTED_DOTNET_RUNTIME_VERSION
)
_EXPECTED_DOTNET_WRAPPER_SHA256 = "135ed085e642e17a1cf55cd61a039c53d79998579b5fafa607e8e731d18ab85e"
_EXPECTED_DOTNET_WRAPPER_BYTES = 136
_EXPECTED_DOTNET_MUXER_SHA256 = "b8195397b57f7df4e4f2c8626c9613738c9e57311d9b23f689846e88d616cbb2"
_EXPECTED_DOTNET_MUXER_BYTES = 140_432
_EXPECTED_DOTNET_SDK_TREE_SHA256 = "bef3d3ea1d59cea9886bb8b9bc5c52174da2d923fdaa634e98395250b2d274ab"
_EXPECTED_DOTNET_SDK_TREE_BYTES = 360_219_604
_EXPECTED_DOTNET_SDK_TREE_FILE_COUNT = 3_031
_EXPECTED_DOTNET_HOSTFXR_TREE_SHA256 = "617b873814d0013e3005da134b7b1432c91d8a42407cd4554ceabc29cc0a0f3c"
_EXPECTED_DOTNET_HOSTFXR_TREE_BYTES = 449_376
_EXPECTED_DOTNET_HOSTFXR_TREE_FILE_COUNT = 1
_EXPECTED_DOTNET_RUNTIME_TREE_SHA256 = "bd69ee3fb7f237deedb6f99532afc8023a9b8ab016dd60b101e4f5a95e0884b9"
_EXPECTED_DOTNET_RUNTIME_TREE_BYTES = 81_526_751
_EXPECTED_DOTNET_RUNTIME_TREE_FILE_COUNT = 188
_EXPECTED_DOTNET_REFERENCE_PACK_TREE_SHA256 = "da4febffbad4f86171e05436ad91885096c9a7d8a177a5480c1b4856e1d6e845"
_EXPECTED_DOTNET_REFERENCE_PACK_TREE_BYTES = 40_730_732
_EXPECTED_DOTNET_REFERENCE_PACK_TREE_FILE_COUNT = 348
_EXPECTED_DOTNET_APPHOST_PACK_TREE_SHA256 = "af2915a0316b1a6715304aaebd2b6dadda66463cdd296eeff42977cb2ace0789"
_EXPECTED_DOTNET_APPHOST_PACK_TREE_BYTES = 11_573_800
_EXPECTED_DOTNET_APPHOST_PACK_TREE_FILE_COUNT = 7
_EXPECTED_DOTNET_HOSTFXR_SHA256 = "9387e328807ac3d29fb0f203bbefdf07d10d4e2200e307515ac16273657267a2"
_EXPECTED_DOTNET_HOSTPOLICY_SHA256 = "145952fb2f06831089127216152a3e4c47ab7ffb74ddaaf4cd06410314de57ff"


def _dotnet_directory_chain(directory: Path, failure: str) -> tuple[tuple[object, ...], ...]:
    """Bind the fixed Homebrew path lexically, before any path resolution."""

    try:
        directory.relative_to(_EXPECTED_DOTNET_CELLAR)
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    cursor = Path("/")
    identities: list[tuple[object, ...]] = []
    try:
        for part in directory.parts[1:]:
            cursor = cursor / part
            metadata = cursor.lstat()
            # Homebrew's shared Cellar is group-writable on the pinned host.
            # The formula root and every bundle component below it are not.
            formula_root = _EXPECTED_DOTNET_CELLAR.parent
            reject_writable = cursor == formula_root or cursor.is_relative_to(formula_root)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or (reject_writable and stat.S_IMODE(metadata.st_mode) & 0o022)
            ):
                raise RouteError(failure)
            identities.append(
                (
                    str(cursor),
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_mode,
                    metadata.st_uid,
                    metadata.st_gid,
                    metadata.st_mtime_ns,
                )
            )
        if directory.resolve(strict=True) != directory:
            raise RouteError(failure)
    except ValueError as error:
        raise RouteError(failure) from error
    except OSError as error:
        raise RouteError(failure) from error
    return tuple(identities)


def _dotnet_file_binding(
    path: Path,
    root: Path,
    failure: str,
    *,
    directory_chain_validated: bool = False,
) -> dict[str, str | int]:
    try:
        path.relative_to(root)
        root.relative_to(_EXPECTED_DOTNET_CELLAR)
    except ValueError as error:
        raise RouteError(failure) from error
    root_chain = () if directory_chain_validated else _dotnet_directory_chain(root, failure)
    cursor = root
    try:
        for part in path.relative_to(root).parts[:-1]:
            cursor = cursor / part
            metadata = cursor.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise RouteError(failure)
        before = path.lstat()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened_before = os.fstat(descriptor)
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        content = b"".join(chunks)
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    if (
        before_identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        )
        or before_identity
        != (
            opened_before.st_dev,
            opened_before.st_ino,
            opened_before.st_mode,
            opened_before.st_size,
            opened_before.st_mtime_ns,
        )
        or before_identity
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_size,
            opened_after.st_mtime_ns,
        )
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(after.st_mode) & 0o022
        or len(content) != after.st_size
        or (root_chain and _dotnet_directory_chain(root, failure) != root_chain)
    ):
        raise RouteError(failure)
    return {
        "path": str(path),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _dotnet_tree_manifest(root: Path, failure: str) -> dict[str, str | int]:
    root_chain = _dotnet_directory_chain(root, failure)
    try:
        resolved_root = root.resolve(strict=True)
        root_metadata = root.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_IMODE(root_metadata.st_mode) & 0o022:
        raise RouteError(failure)

    def discover() -> list[Path]:
        files: list[Path] = []
        try:
            paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
            for path in paths:
                metadata = path.lstat()
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or stat.S_IMODE(metadata.st_mode) & 0o022
                    or metadata.st_uid not in {0, os.getuid()}
                    or not path.resolve(strict=True).is_relative_to(resolved_root)
                ):
                    raise RouteError(failure)
                if stat.S_ISDIR(metadata.st_mode):
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise RouteError(failure)
                files.append(path)
        except OSError as error:
            raise RouteError(failure) from error
        return files

    paths = discover()
    if not paths:
        raise RouteError(failure)
    files: list[dict[str, str | int]] = []
    total_bytes = 0
    for path in paths:
        binding = _dotnet_file_binding(path, root, failure, directory_chain_validated=True)
        binding["path"] = path.relative_to(root).as_posix()
        total_bytes += int(binding["bytes"])
        files.append(binding)
    if [path.relative_to(root).as_posix() for path in discover()] != [str(item["path"]) for item in files]:
        raise RouteError(failure + ":PATH_SET_CHANGED")
    if _dotnet_directory_chain(root, failure) != root_chain:
        raise RouteError(failure + ":DIRECTORY_CHAIN_CHANGED")
    encoded = json.dumps(
        {"files": files},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "path": str(root),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": total_bytes,
        "file_count": len(files),
    }


def _dotnet_bundle_identity() -> dict[str, object]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:csharp:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    wrapper = _dotnet_file_binding(
        _EXPECTED_DOTNET_WRAPPER,
        _EXPECTED_DOTNET_CELLAR,
        "EXACT_TOOLCHAIN_DOTNET_WRAPPER_UNSAFE",
    )
    muxer = _dotnet_file_binding(
        _EXPECTED_DOTNET_MUXER,
        _EXPECTED_DOTNET_ROOT,
        "EXACT_TOOLCHAIN_DOTNET_MUXER_UNSAFE",
    )
    sdk = _dotnet_tree_manifest(_EXPECTED_DOTNET_SDK, "EXACT_TOOLCHAIN_DOTNET_SDK_UNSAFE")
    hostfxr = _dotnet_tree_manifest(
        _EXPECTED_DOTNET_HOSTFXR,
        "EXACT_TOOLCHAIN_DOTNET_HOSTFXR_UNSAFE",
    )
    runtime = _dotnet_tree_manifest(
        _EXPECTED_DOTNET_RUNTIME,
        "EXACT_TOOLCHAIN_DOTNET_RUNTIME_UNSAFE",
    )
    reference_pack = _dotnet_tree_manifest(
        _EXPECTED_DOTNET_REFERENCE_PACK,
        "EXACT_TOOLCHAIN_DOTNET_REFERENCE_PACK_UNSAFE",
    )
    apphost_pack = _dotnet_tree_manifest(
        _EXPECTED_DOTNET_APPHOST_PACK,
        "EXACT_TOOLCHAIN_DOTNET_APPHOST_PACK_UNSAFE",
    )
    hostfxr_binary = _dotnet_file_binding(
        _EXPECTED_DOTNET_HOSTFXR / "libhostfxr.dylib",
        _EXPECTED_DOTNET_HOSTFXR,
        "EXACT_TOOLCHAIN_DOTNET_HOSTFXR_BINARY_UNSAFE",
    )
    hostpolicy_binary = _dotnet_file_binding(
        _EXPECTED_DOTNET_RUNTIME / "libhostpolicy.dylib",
        _EXPECTED_DOTNET_RUNTIME,
        "EXACT_TOOLCHAIN_DOTNET_HOSTPOLICY_BINARY_UNSAFE",
    )
    expected = {
        "wrapper": {
            "path": str(_EXPECTED_DOTNET_WRAPPER),
            "bytes": _EXPECTED_DOTNET_WRAPPER_BYTES,
            "sha256": _EXPECTED_DOTNET_WRAPPER_SHA256,
        },
        "muxer": {
            "path": str(_EXPECTED_DOTNET_MUXER),
            "bytes": _EXPECTED_DOTNET_MUXER_BYTES,
            "sha256": _EXPECTED_DOTNET_MUXER_SHA256,
        },
        "sdk": {
            "path": str(_EXPECTED_DOTNET_SDK),
            "bytes": _EXPECTED_DOTNET_SDK_TREE_BYTES,
            "file_count": _EXPECTED_DOTNET_SDK_TREE_FILE_COUNT,
            "sha256": _EXPECTED_DOTNET_SDK_TREE_SHA256,
        },
        "hostfxr": {
            "path": str(_EXPECTED_DOTNET_HOSTFXR),
            "bytes": _EXPECTED_DOTNET_HOSTFXR_TREE_BYTES,
            "file_count": _EXPECTED_DOTNET_HOSTFXR_TREE_FILE_COUNT,
            "sha256": _EXPECTED_DOTNET_HOSTFXR_TREE_SHA256,
        },
        "runtime": {
            "path": str(_EXPECTED_DOTNET_RUNTIME),
            "bytes": _EXPECTED_DOTNET_RUNTIME_TREE_BYTES,
            "file_count": _EXPECTED_DOTNET_RUNTIME_TREE_FILE_COUNT,
            "sha256": _EXPECTED_DOTNET_RUNTIME_TREE_SHA256,
        },
        "reference_pack": {
            "path": str(_EXPECTED_DOTNET_REFERENCE_PACK),
            "bytes": _EXPECTED_DOTNET_REFERENCE_PACK_TREE_BYTES,
            "file_count": _EXPECTED_DOTNET_REFERENCE_PACK_TREE_FILE_COUNT,
            "sha256": _EXPECTED_DOTNET_REFERENCE_PACK_TREE_SHA256,
        },
        "apphost_pack": {
            "path": str(_EXPECTED_DOTNET_APPHOST_PACK),
            "bytes": _EXPECTED_DOTNET_APPHOST_PACK_TREE_BYTES,
            "file_count": _EXPECTED_DOTNET_APPHOST_PACK_TREE_FILE_COUNT,
            "sha256": _EXPECTED_DOTNET_APPHOST_PACK_TREE_SHA256,
        },
    }
    observed = {
        "wrapper": {key: wrapper[key] for key in ("path", "bytes", "sha256")},
        "muxer": {key: muxer[key] for key in ("path", "bytes", "sha256")},
        "sdk": {key: sdk[key] for key in ("path", "bytes", "file_count", "sha256")},
        "hostfxr": {key: hostfxr[key] for key in ("path", "bytes", "file_count", "sha256")},
        "runtime": {key: runtime[key] for key in ("path", "bytes", "file_count", "sha256")},
        "reference_pack": {key: reference_pack[key] for key in ("path", "bytes", "file_count", "sha256")},
        "apphost_pack": {key: apphost_pack[key] for key in ("path", "bytes", "file_count", "sha256")},
    }
    if (
        observed != expected
        or hostfxr_binary["sha256"] != _EXPECTED_DOTNET_HOSTFXR_SHA256
        or hostpolicy_binary["sha256"] != _EXPECTED_DOTNET_HOSTPOLICY_SHA256
    ):
        raise RouteError("EXACT_TOOLCHAIN_DOTNET_BUNDLE_MISMATCH")
    return {
        **observed,
        "hostfxr_binary": hostfxr_binary,
        "hostpolicy_binary": hostpolicy_binary,
    }


def _dotnet_profile(identity: dict[str, object]) -> tuple[str, ...]:
    wrapper = cast(dict[str, Any], identity["wrapper"])
    muxer = cast(dict[str, Any], identity["muxer"])
    sdk = cast(dict[str, Any], identity["sdk"])
    hostfxr = cast(dict[str, Any], identity["hostfxr"])
    runtime = cast(dict[str, Any], identity["runtime"])
    reference_pack = cast(dict[str, Any], identity["reference_pack"])
    apphost_pack = cast(dict[str, Any], identity["apphost_pack"])
    hostfxr_binary = cast(dict[str, Any], identity["hostfxr_binary"])
    hostpolicy_binary = cast(dict[str, Any], identity["hostpolicy_binary"])
    return (
        "dotnet-profile-schema=v1",
        "platform=Darwin/arm64",
        "distribution=Homebrew-dotnet",
        f"dotnet-root={_EXPECTED_DOTNET_ROOT}",
        f"sdk-version={_EXPECTED_DOTNET_VERSION}",
        f"hostfxr-version={_EXPECTED_DOTNET_RUNTIME_VERSION}",
        "runtime-framework=Microsoft.NETCore.App",
        f"runtime-version={_EXPECTED_DOTNET_RUNTIME_VERSION}",
        "rid=osx-arm64",
        f"targeting-pack-version={_EXPECTED_DOTNET_RUNTIME_VERSION}",
        f"apphost-pack-version={_EXPECTED_DOTNET_RUNTIME_VERSION}",
        f"wrapper-path={wrapper['path']}",
        f"wrapper-sha256={wrapper['sha256']}",
        f"wrapper-bytes={wrapper['bytes']}",
        f"muxer-path={muxer['path']}",
        f"muxer-sha256={muxer['sha256']}",
        f"muxer-bytes={muxer['bytes']}",
        f"sdk-path={sdk['path']}",
        f"sdk-tree-sha256={sdk['sha256']}",
        f"sdk-tree-file-count={sdk['file_count']}",
        f"sdk-tree-bytes={sdk['bytes']}",
        f"hostfxr-path={hostfxr['path']}",
        f"hostfxr-tree-sha256={hostfxr['sha256']}",
        f"hostfxr-tree-file-count={hostfxr['file_count']}",
        f"hostfxr-tree-bytes={hostfxr['bytes']}",
        f"runtime-path={runtime['path']}",
        f"runtime-tree-sha256={runtime['sha256']}",
        f"runtime-tree-file-count={runtime['file_count']}",
        f"runtime-tree-bytes={runtime['bytes']}",
        f"reference-pack-path={reference_pack['path']}",
        f"reference-pack-tree-sha256={reference_pack['sha256']}",
        f"reference-pack-tree-file-count={reference_pack['file_count']}",
        f"reference-pack-tree-bytes={reference_pack['bytes']}",
        f"apphost-pack-path={apphost_pack['path']}",
        f"apphost-pack-tree-sha256={apphost_pack['sha256']}",
        f"apphost-pack-tree-file-count={apphost_pack['file_count']}",
        f"apphost-pack-tree-bytes={apphost_pack['bytes']}",
        f"hostfxr-sha256={hostfxr_binary['sha256']}",
        f"hostpolicy-sha256={hostpolicy_binary['sha256']}",
    )


def verify_csharp_toolchain(toolchain: ExactToolchain) -> dict[str, object]:
    """Freshly re-hash the fixed .NET bundle and match one toolchain receipt."""

    identity = _dotnet_bundle_identity()
    muxer = identity["muxer"]
    assert isinstance(muxer, dict)
    if (
        toolchain.language != "csharp"
        or toolchain.version != _EXPECTED_DOTNET_VERSION
        or toolchain.executable != str(_EXPECTED_DOTNET_MUXER)
        or toolchain.auxiliary is not None
        or toolchain.profile != _dotnet_profile(identity)
        or toolchain.executable_sha256 != muxer["sha256"]
        or toolchain.auxiliary_sha256 is not None
    ):
        raise RouteError("EXACT_TOOLCHAIN_DOTNET_IDENTITY_MISMATCH")
    return identity


def _java() -> ExactToolchain:
    try:
        expected_home = _EXPECTED_JAVA_HOME.resolve(strict=True)
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:java:expected-home") from error
    configured = os.environ.get("ELMOS_JAVA21_HOME", "").strip()
    if configured:
        try:
            configured_home = Path(configured).resolve(strict=True)
        except OSError as error:
            raise RouteError("EXACT_TOOLCHAIN_DECLARED_HOME_INVALID:java") from error
        if configured_home != expected_home:
            raise RouteError(
                f"EXACT_TOOLCHAIN_DECLARED_HOME_MISMATCH:java:expected={expected_home}:declared={configured_home}"
            )
    java = expected_home / "bin" / "java"
    javac = expected_home / "bin" / "javac"
    modules = expected_home / "lib" / "modules"
    jvm = expected_home / "lib" / "server" / "libjvm.dylib"
    release = expected_home / "release"
    if not all(item.is_file() for item in (java, javac, modules, jvm, release)):
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:java/javac")
    java_digest = _sha256(java)
    javac_digest = _sha256(javac)
    modules_digest = _sha256(modules)
    jvm_digest = _sha256(jvm)
    release_digest = _sha256(release)
    observed_java = _output([str(java), "-version"])
    observed_javac = _output([str(javac), "-version"])
    bundle = expected_home.parents[1]
    codesign = Path("/usr/bin/codesign")
    _output([str(codesign), "--verify", "--deep", "--strict", str(bundle)])
    signature = _output([str(codesign), "-d", "--verbose=4", str(bundle)])
    signature_lines = set(signature.splitlines())
    if (
        java_digest != _EXPECTED_JAVA_SHA256
        or javac_digest != _EXPECTED_JAVAC_SHA256
        or modules_digest != _EXPECTED_JAVA_MODULES_SHA256
        or jvm_digest != _EXPECTED_JAVA_JVM_SHA256
        or release_digest != _EXPECTED_JAVA_RELEASE_SHA256
        or observed_java != _EXPECTED_JAVA_VERSION
        or observed_javac != _EXPECTED_JAVAC_VERSION
        or "Identifier=net.java.openjdk.jdk" not in signature_lines
        or "TeamIdentifier=not set" not in signature_lines
        or ("CandidateCDHashFull sha256=" + _EXPECTED_JAVA_BUNDLE_CDHASH_FULL not in signature_lines)
    ):
        raise RouteError(
            "EXACT_TOOLCHAIN_MISMATCH:java:expected=21.0.11/"
            f"java-sha256={_EXPECTED_JAVA_SHA256}/javac-sha256={_EXPECTED_JAVAC_SHA256}:"
            f"observed-java-sha256={java_digest}/observed-javac-sha256={javac_digest}"
        )
    return ExactToolchain(
        "java",
        "21.0.11",
        str(java),
        str(javac),
        profile=(
            "platform=Darwin/arm64",
            "distribution=Homebrew-openjdk@21",
            f"jdk-home={expected_home}",
            f"jdk-cdhash-full={_EXPECTED_JAVA_BUNDLE_CDHASH_FULL}",
            f"jdk-modules-sha256={modules_digest}",
            f"libjvm-sha256={jvm_digest}",
            f"release-sha256={release_digest}",
        ),
        executable_sha256=java_digest,
        auxiliary_sha256=javac_digest,
    )


def _python() -> ExactToolchain:
    observed = platform.python_version()
    if observed != "3.12.12":
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:python:expected=3.12.12:observed={observed}")
    return ExactToolchain("python", observed, sys.executable)


def _csharp() -> ExactToolchain:
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:dotnet")
    declared = Path(dotnet)
    try:
        before = declared.lstat()
        resolved = declared.resolve(strict=True)
        link_target = declared.readlink()
        after = declared.lstat()
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_DOTNET_SHIM_UNSAFE") from error
    if (
        declared != _EXPECTED_DOTNET_SHIM
        or not stat.S_ISLNK(before.st_mode)
        or resolved != _EXPECTED_DOTNET_WRAPPER
        or str(link_target) != "../Cellar/dotnet/10.0.301/bin/dotnet"
        or (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
        )
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        )
    ):
        raise RouteError("EXACT_TOOLCHAIN_DOTNET_SHIM_UNSAFE")
    identity = _dotnet_bundle_identity()
    muxer = identity["muxer"]
    assert isinstance(muxer, dict)
    observed = _output([str(_EXPECTED_DOTNET_MUXER), "--version"])
    if observed != _EXPECTED_DOTNET_VERSION:
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:csharp:expected={_EXPECTED_DOTNET_VERSION}:observed={observed}")
    return ExactToolchain(
        "csharp",
        observed,
        str(_EXPECTED_DOTNET_MUXER),
        profile=_dotnet_profile(identity),
        executable_sha256=str(muxer["sha256"]),
    )


def _typescript() -> ExactToolchain:
    node = shutil.which("node")
    tsc = REPOSITORY_ROOT / "engines" / "frontend-client-engine" / "node_modules" / ".bin" / "tsc"
    if not node or not tsc.is_file():
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:typescript")
    node_version = _output([node, "--version"])
    # pnpm installs ``tsc`` as a shell launcher which dispatches to ``node``.
    # The exact-toolchain probe intentionally runs with a minimal PATH, so the
    # already-selected Node directory must be admitted explicitly.  Relying on
    # the caller's ambient Homebrew PATH would make the probe non-replayable.
    typescript_version = _output(
        [str(tsc), "--version"],
        executable_dirs=(Path(node).resolve().parent,),
    )
    if node_version != "v26.0.0" or typescript_version != "Version 5.9.2":
        raise RouteError(
            "EXACT_TOOLCHAIN_MISMATCH:typescript:"
            f"expected=Node26.0.0/TypeScript5.9.2:observed={node_version}/{typescript_version}"
        )
    return ExactToolchain("typescript", "5.9.2 / Node 26.0.0", node, str(tsc))


def _go() -> ExactToolchain:
    executable = shutil.which("go")
    if not executable:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:go")
    observed = _output([executable, "version"])
    parts = observed.split()
    supported_platforms = {"darwin/arm64", "linux/amd64"}
    if (
        len(parts) != 4
        or parts[:2] != ["go", "version"]
        or parts[2] != "go1.25.0"
        or parts[3] not in supported_platforms
    ):
        expected = "go version go1.25.0 {darwin/arm64|linux/amd64}"
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:go:expected={expected}:observed={observed}")
    return ExactToolchain("go", "1.25.0", executable)


def _rust() -> ExactToolchain:
    executable = shutil.which("rustc")
    cargo = shutil.which("cargo")
    if not executable or not cargo:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:rust")
    observed = _output([executable, "--version"])
    expected = "rustc 1.89.0 (29483883e 2025-08-04)"
    if observed != expected:
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:rust:expected={expected}:observed={observed}")
    return ExactToolchain("rust", "1.89.0", executable, cargo)


#: Native evidence is pinned to the exact Xcode toolchain used to qualify this
#: engine.  Environment variables may repeat these values for CI clarity, but
#: cannot replace them with a host-local declaration.  A different Xcode,
#: SDK, architecture, binary digest, or language profile fails closed.
_CLANG_VERSION_VARIABLE = "ELMOS_CLANG_VERSION"
_SWIFT_VERSION_VARIABLE = "ELMOS_SWIFT_VERSION"
_EXPECTED_CLANG_VERSION = "Apple clang version 21.0.0 (clang-2100.1.1.101)"
_EXPECTED_SWIFT_VERSION = "Apple Swift version 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101)"
_EXPECTED_SWIFT_TARGET = "Target: arm64-apple-macosx26.0"
_EXPECTED_SWIFT_DRIVER_VERSION = "swift-driver version: 1.148.6"
_EXPECTED_XCODE = "Xcode 26.6\nBuild version 17F113"
_EXPECTED_MACOS_SDK = "26.5"
_EXPECTED_CLANG_SHA256 = "7def90dd8829726686213a747fc5bff1583df933dae5edc55d755479e0bfe00a"
_EXPECTED_SWIFTC_SHA256 = "2ed38571e92c0283091838c1649e27650ad9c99950288e883c7b2dc6c4ce89fb"


def _pinned(variable: str, language: Language, repository_pin: str) -> str:
    declared = os.environ.get(variable, repository_pin).strip()
    if declared != repository_pin:
        raise RouteError(
            f"EXACT_TOOLCHAIN_DECLARED_PIN_MISMATCH:{language}:expected={repository_pin}:declared={declared}"
        )
    return repository_pin


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apple_profile(language: Language) -> tuple[str, ...]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            f"EXACT_TOOLCHAIN_PLATFORM_MISMATCH:{language}:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    xcodebuild = Path("/usr/bin/xcodebuild")
    xcrun = Path("/usr/bin/xcrun")
    if not xcodebuild.is_file() or not xcrun.is_file():
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:xcodebuild/xcrun")
    observed_xcode = _output([str(xcodebuild), "-version"])
    sdk_version = _output([str(xcrun), "--sdk", "macosx", "--show-sdk-version"])
    sdk_path = Path(_output([str(xcrun), "--sdk", "macosx", "--show-sdk-path"]))
    if observed_xcode != _EXPECTED_XCODE or sdk_version != _EXPECTED_MACOS_SDK:
        raise RouteError(
            f"EXACT_TOOLCHAIN_APPLE_PROFILE_MISMATCH:{language}:"
            f"expected={_EXPECTED_XCODE.replace(chr(10), '/')}/sdk={_EXPECTED_MACOS_SDK}:"
            f"observed={observed_xcode.replace(chr(10), '/')}/sdk={sdk_version}"
        )
    foundation = sdk_path / "System/Library/Frameworks/Foundation.framework/Headers/Foundation.h"
    objc_runtime = sdk_path / "usr/include/objc/objc.h"
    if sdk_path.name != "MacOSX26.5.sdk" or not foundation.is_file() or not objc_runtime.is_file():
        raise RouteError(f"EXACT_TOOLCHAIN_APPLE_SDK_INCOMPLETE:{language}:{sdk_path}")
    return (
        "platform=Darwin/arm64",
        "xcode=26.6/17F113",
        "macosx-sdk=26.5",
        f"sdk-path={sdk_path}",
    )


def _clang(language: Language, executable_name: str) -> ExactToolchain:
    xcrun = Path("/usr/bin/xcrun")
    executable = _output([str(xcrun), "--find", executable_name]) if xcrun.is_file() else None
    if not executable or not Path(executable).is_file():
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{executable_name}")
    configured = os.environ.get("ELMOS_CLANG_HOME", "").strip()
    if configured:
        try:
            declared = (Path(configured) / "bin" / executable_name).resolve(strict=True)
            discovered = Path(executable).resolve(strict=True)
        except OSError as error:
            raise RouteError(f"EXACT_TOOLCHAIN_DECLARED_HOME_INVALID:{language}") from error
        if declared != discovered:
            raise RouteError(
                f"EXACT_TOOLCHAIN_DECLARED_HOME_MISMATCH:{language}:expected={discovered}:declared={declared}"
            )
    expected = _pinned(_CLANG_VERSION_VARIABLE, language, _EXPECTED_CLANG_VERSION)
    observed = _output([executable, "--version"]).splitlines()[0].strip()
    executable_digest = _sha256(Path(executable).resolve())
    if observed != expected or executable_digest != _EXPECTED_CLANG_SHA256:
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:{language}:expected={expected}/sha256={_EXPECTED_CLANG_SHA256}:"
            f"observed={observed}/sha256={executable_digest}"
        )
    standard = "c++20" if language == "cpp" else "c17/objc-arc/Foundation/Apple-runtime"
    return ExactToolchain(
        language,
        observed,
        executable,
        profile=(*_apple_profile(language), standard),
        executable_sha256=executable_digest,
    )


def _cpp() -> ExactToolchain:
    return _clang("cpp", "clang++")


def _objc() -> ExactToolchain:
    # The same clang drives Objective-C; `-x objective-c` selects the mode
    # (see clang_analyzer.py), so the C driver is the right executable.
    return _clang("objc", "clang")


def _swift() -> ExactToolchain:
    xcrun = Path("/usr/bin/xcrun")
    executable = _output([str(xcrun), "--find", "swiftc"]) if xcrun.is_file() else None
    driver = _output([str(xcrun), "--find", "swift"]) if xcrun.is_file() else None
    if not executable or not driver:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:swiftc")
    expected = _pinned(_SWIFT_VERSION_VARIABLE, "swift", _EXPECTED_SWIFT_VERSION)
    version_lines = _output([executable, "--version"]).splitlines()
    observed = version_lines[0].strip() if version_lines else ""
    observed_target = version_lines[1].strip() if len(version_lines) > 1 else ""
    executable_digest = _sha256(Path(executable).resolve())
    driver_digest = _sha256(Path(driver).resolve())
    driver_version = _output([driver, "--version"])
    if (
        observed != expected
        or observed_target != _EXPECTED_SWIFT_TARGET
        or executable_digest != _EXPECTED_SWIFTC_SHA256
        or driver_digest != _EXPECTED_SWIFTC_SHA256
        or driver_version != "\n".join((expected, _EXPECTED_SWIFT_TARGET, _EXPECTED_SWIFT_DRIVER_VERSION))
    ):
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:swift:expected={expected}/{_EXPECTED_SWIFT_TARGET}/"
            f"swiftc-sha256={_EXPECTED_SWIFTC_SHA256}/swift-driver-sha256={_EXPECTED_SWIFTC_SHA256}:"
            f"observed={observed}/{observed_target}/swiftc-sha256={executable_digest}/"
            f"swift-driver-sha256={driver_digest}"
        )
    return ExactToolchain(
        "swift",
        observed,
        executable,
        driver,
        profile=(*_apple_profile("swift"), "swift-language-mode=6", "integer=Int64"),
        executable_sha256=executable_digest,
        auxiliary_sha256=driver_digest,
    )


def exact_toolchain(language: Language) -> ExactToolchain:
    return {
        "java": _java,
        "python": _python,
        "csharp": _csharp,
        "typescript": _typescript,
        "go": _go,
        "rust": _rust,
        "cpp": _cpp,
        "objc": _objc,
        "swift": _swift,
    }[language]()
