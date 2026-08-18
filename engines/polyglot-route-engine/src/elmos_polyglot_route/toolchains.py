from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from .models import Language, RouteError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_GO_TELEMETRY_MODE = b"off\n"


def _disabled_go_telemetry_directory(home: Path) -> Path:
    """Create a private Go telemetry directory that cannot spawn a sidecar."""

    failure = "SUBPROCESS_GO_TELEMETRY_ISOLATION_FAILED"

    def stable_directory_identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
        )

    def exact_identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    def bounded_read(descriptor: int) -> bytes:
        content = bytearray()
        maximum = len(_GO_TELEMETRY_MODE) + 1
        while len(content) < maximum:
            chunk = os.read(descriptor, maximum - len(content))
            if not chunk:
                break
            content.extend(chunk)
        return bytes(content)

    try:
        resolved_home = home.resolve(strict=True)
        if home.is_symlink() or not home.is_dir():
            raise OSError(failure)
        telemetry = resolved_home / ".elmos-go-telemetry"
        telemetry.mkdir(mode=0o700, exist_ok=True)
        telemetry_metadata = telemetry.lstat()
        if (
            telemetry.is_symlink()
            or not stat.S_ISDIR(telemetry_metadata.st_mode)
            or telemetry_metadata.st_uid != os.getuid()
            or stat.S_IMODE(telemetry_metadata.st_mode) != 0o700
            or telemetry.resolve(strict=True) != telemetry
        ):
            raise OSError(failure)

        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        directory_descriptor = os.open(telemetry, directory_flags)
        try:
            opened_directory = os.fstat(directory_descriptor)
            if exact_identity(opened_directory) != exact_identity(telemetry_metadata):
                raise OSError(failure)

            mode_file = telemetry / "mode"
            write_flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                write_descriptor = os.open(
                    mode_file.name,
                    write_flags,
                    0o600,
                    dir_fd=directory_descriptor,
                )
            except FileExistsError:
                pass
            else:
                try:
                    written = 0
                    while written < len(_GO_TELEMETRY_MODE):
                        byte_count = os.write(write_descriptor, _GO_TELEMETRY_MODE[written:])
                        if byte_count <= 0:
                            raise OSError(failure)
                        written += byte_count
                    os.fsync(write_descriptor)
                finally:
                    os.close(write_descriptor)

            directory_after_create = os.fstat(directory_descriptor)
            rebound_directory = telemetry.lstat()
            if (
                stable_directory_identity(directory_after_create)
                != stable_directory_identity(opened_directory)
                or exact_identity(rebound_directory) != exact_identity(directory_after_create)
                or os.listdir(directory_descriptor) != [mode_file.name]
                or telemetry.is_symlink()
                or not stat.S_ISDIR(rebound_directory.st_mode)
                or rebound_directory.st_uid != os.getuid()
                or stat.S_IMODE(rebound_directory.st_mode) != 0o700
                or telemetry.resolve(strict=True) != telemetry
            ):
                raise OSError(failure)
            directory_seal = exact_identity(directory_after_create)

            mode_before = mode_file.lstat()
            read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            read_descriptor = os.open(
                mode_file.name,
                read_flags,
                dir_fd=directory_descriptor,
            )
            try:
                opened_before = os.fstat(read_descriptor)
                first_content = bounded_read(read_descriptor)
                opened_middle = os.fstat(read_descriptor)
                os.lseek(read_descriptor, 0, os.SEEK_SET)
                second_content = bounded_read(read_descriptor)
                opened_after = os.fstat(read_descriptor)
            finally:
                os.close(read_descriptor)
            mode_after = mode_file.lstat()
            mode_identity = exact_identity(mode_before)
            if (
                first_content != _GO_TELEMETRY_MODE
                or second_content != _GO_TELEMETRY_MODE
                or mode_identity != exact_identity(opened_before)
                or mode_identity != exact_identity(opened_middle)
                or mode_identity != exact_identity(opened_after)
                or mode_identity != exact_identity(mode_after)
                or mode_file.is_symlink()
                or not stat.S_ISREG(mode_after.st_mode)
                or mode_after.st_uid != os.getuid()
                or stat.S_IMODE(mode_after.st_mode) != 0o600
                or mode_after.st_nlink != 1
                or mode_after.st_size != len(_GO_TELEMETRY_MODE)
            ):
                raise OSError(failure)

            final_opened_directory = os.fstat(directory_descriptor)
            final_rebound_directory = telemetry.lstat()
            if (
                exact_identity(final_opened_directory) != directory_seal
                or exact_identity(final_rebound_directory) != directory_seal
                or telemetry.is_symlink()
                or telemetry.resolve(strict=True) != telemetry
            ):
                raise OSError(failure)
        finally:
            os.close(directory_descriptor)
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    return telemetry


def sanitized_subprocess_env(
    *,
    home: Path,
    temp_dir: Path,
    executable_dirs: tuple[Path, ...] = (),
) -> dict[str, str]:
    """Return a deterministic subprocess environment with no ambient hooks."""

    go_telemetry = _disabled_go_telemetry_directory(home)
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
        "TEST_TELEMETRY_DIR": str(go_telemetry),
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


def _qualified_directory_chain(
    directory: Path,
    anchor: Path,
    failure: str,
) -> tuple[tuple[object, ...], ...]:
    """Seal one fixed user-owned toolchain path without following directories."""

    try:
        directory.relative_to(anchor)
    except ValueError as error:
        raise RouteError(failure) from error
    cursor = anchor
    identities: list[tuple[object, ...]] = []
    try:
        relative = directory.relative_to(anchor)
        for part in ("", *relative.parts):
            if part:
                cursor = cursor / part
            metadata = cursor.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
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
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    return tuple(identities)


def _qualified_file_record(path: Path, root: Path, failure: str) -> dict[str, str | int]:
    try:
        relative = path.relative_to(root).as_posix()
        if path.resolve(strict=True) != path:
            raise RouteError(failure)
        before = path.lstat()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened_before = os.fstat(descriptor)
            digest = hashlib.sha256()
            byte_count = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
                byte_count += len(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
        or identity
        != (
            opened_before.st_dev,
            opened_before.st_ino,
            opened_before.st_mode,
            opened_before.st_size,
            opened_before.st_uid,
            opened_before.st_gid,
            opened_before.st_nlink,
            opened_before.st_mtime_ns,
        )
        or identity
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_size,
            opened_after.st_uid,
            opened_after.st_gid,
            opened_after.st_nlink,
            opened_after.st_mtime_ns,
        )
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(after.st_mode) & 0o022
        or after.st_nlink != 1
        or byte_count != after.st_size
    ):
        raise RouteError(failure)
    return {
        "path": relative,
        "kind": "file",
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "uid": after.st_uid,
        "gid": after.st_gid,
        "nlink": after.st_nlink,
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
    }


def _qualified_tree_manifest(root: Path, anchor: Path, failure: str) -> dict[str, object]:
    """Return a complete immutable manifest for a symlink-free toolchain tree."""

    root_chain = _qualified_directory_chain(root, anchor, failure)

    def discover() -> list[Path]:
        try:
            paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
            for path in paths:
                metadata = path.lstat()
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or metadata.st_uid not in {0, os.getuid()}
                    or stat.S_IMODE(metadata.st_mode) & 0o022
                    or not path.resolve(strict=True).is_relative_to(root)
                    or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode))
                ):
                    raise RouteError(failure)
            return paths
        except OSError as error:
            raise RouteError(failure) from error

    paths = discover()
    if not paths:
        raise RouteError(failure)
    records: list[dict[str, object]] = []
    file_bytes = 0
    file_count = 0
    directory_count = 0
    for path in paths:
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            directory_count += 1
            records.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "kind": "directory",
                    "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                    "uid": metadata.st_uid,
                    "gid": metadata.st_gid,
                }
            )
            continue
        record = _qualified_file_record(path, root, failure)
        records.append(cast(dict[str, object], record))
        file_count += 1
        file_bytes += cast(int, record["bytes"])
    if [path.relative_to(root).as_posix() for path in discover()] != [
        str(item["path"]) for item in records
    ] or _qualified_directory_chain(root, anchor, failure) != root_chain:
        raise RouteError(failure + ":TREE_CHANGED")
    encoded = json.dumps(
        {"records": records},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "root": str(root),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "record_count": len(records),
        "file_count": file_count,
        "directory_count": directory_count,
        "bytes": file_bytes,
    }


def _verify_qualified_tree_manifest(
    identity: dict[str, object],
    *,
    expected_root: Path,
    expected_sha256: str,
    expected_record_count: int,
    expected_file_count: int,
    expected_directory_count: int,
    expected_bytes: int,
    failure: str,
) -> None:
    expected: dict[str, object] = {
        "root": str(expected_root),
        "sha256": expected_sha256,
        "record_count": expected_record_count,
        "file_count": expected_file_count,
        "directory_count": expected_directory_count,
        "bytes": expected_bytes,
    }
    if identity != expected:
        raise RouteError(failure)


def _qualified_fixed_symlink(
    declared: Path,
    *,
    anchor: Path,
    expected_target: str,
    expected_resolved: Path,
    failure: str,
) -> tuple[object, ...]:
    """Bind an exact public selector symlink and its non-writable parent chain."""

    parent_chain = _qualified_directory_chain(declared.parent, anchor, failure)
    try:
        before = declared.lstat()
        target_before = declared.readlink()
        resolved = declared.resolve(strict=True)
        after = declared.lstat()
        target_after = declared.readlink()
    except OSError as error:
        raise RouteError(failure) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    if (
        not stat.S_ISLNK(before.st_mode)
        or before.st_uid not in {0, os.getuid()}
        or before.st_nlink != 1
        or str(target_before) != expected_target
        or target_before != target_after
        or resolved != expected_resolved
        or identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
        or _qualified_directory_chain(declared.parent, anchor, failure) != parent_chain
    ):
        raise RouteError(failure)
    return (str(declared), str(target_before), str(resolved), *identity, parent_chain)


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


_EXPECTED_PYTHON_LOCAL_ANCHOR = Path("/Users/stephen/.local")
_EXPECTED_PYTHON_ROOT = Path(
    "/Users/stephen/.local/share/elmos/toolchains/python-build-standalone/"
    "runtimes/3.12.12+20260211-aarch64-apple-darwin/"
    "sha256-1400403c757cb4da3ce2df42d17d02e1368c54afd46bbed71ae84e25d081a154/python"
)
_EXPECTED_PYTHON_EXECUTABLE = _EXPECTED_PYTHON_ROOT / "bin" / "python3.12"
_EXPECTED_PYTHON_STDLIB = _EXPECTED_PYTHON_ROOT / "lib" / "python3.12"
_EXPECTED_PYTHON_LIBPYTHON = _EXPECTED_PYTHON_ROOT / "lib" / "libpython3.12.dylib"
_EXPECTED_PYTHON_ARCHIVE = Path(
    "/Users/stephen/.local/share/elmos/toolchains/python-build-standalone/archives/"
    "sha256-22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84.tar.gz"
)
_EXPECTED_PYTHON_EXECUTABLE_SHA256 = "3874a935f7242b660e652d35c25a1b87415fcfea3ee191ff262fcca5c50102c5"
_EXPECTED_PYTHON_EXECUTABLE_BYTES = 49_968
_EXPECTED_PYTHON_LIBPYTHON_SHA256 = "6eaf8b75978a525dd85d04f34053fe33bd7fdc4b684ce991417f7d019d9b2f6e"
_EXPECTED_PYTHON_LIBPYTHON_BYTES = 17_865_200
_EXPECTED_PYTHON_SOURCE_ARCHIVE_SHA256 = "22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84"
_EXPECTED_PYTHON_SOURCE_ARCHIVE_BYTES = 17_667_661
_EXPECTED_PYTHON_CAPTURE_RELATIVE = (
    "runtime/python/sha256-"
    + _EXPECTED_PYTHON_SOURCE_ARCHIVE_SHA256
    + ".tar.gz"
)
_EXPECTED_PYTHON_SOURCE_TREE_SHA256 = "1400403c757cb4da3ce2df42d17d02e1368c54afd46bbed71ae84e25d081a154"
_EXPECTED_PYTHON_RUNTIME_TREE_SHA256 = "49eb47a1e6f1a8803ef3686da328abf2e18f1d31b6447190c3455640e4df9adf"
_EXPECTED_PYTHON_RUNTIME_RECORD_COUNT = 1_899
_EXPECTED_PYTHON_RUNTIME_FILE_COUNT = 1_890
_EXPECTED_PYTHON_RUNTIME_BYTES = 47_880_708
_EXPECTED_PYTHON_SYMLINKS = {
    "bin/2to3": "2to3-3.12",
    "bin/idle3": "idle3.12",
    "bin/pydoc3": "pydoc3.12",
    "bin/python": "python3.12",
    "bin/python3": "python3.12",
    "bin/python3-config": "python3.12-config",
    "lib/pkgconfig/python3-embed.pc": "python-3.12-embed.pc",
    "lib/pkgconfig/python3.pc": "python-3.12.pc",
    "share/man/man1/python3.1": "python3.12.1",
}
_EXPECTED_PYTHON_RUNTIME_IDENTITY_SHA256 = "07be3b00a639caff021e966cccbfe8d52b943e4aabe9630fcaa62c777610acfa"
_PYTHON_RUNTIME_IDENTITY_SCRIPT = (
    "import importlib.util,json,platform,sys,sysconfig;"
    "print(json.dumps({'version':platform.python_version(),'sys_version':sys.version,"
    "'implementation':sys.implementation.name,'cache_tag':sys.implementation.cache_tag,"
    "'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix,"
    "'stdlib':sysconfig.get_path('stdlib'),'platstdlib':sysconfig.get_path('platstdlib'),"
    "'soabi':sysconfig.get_config_var('SOABI'),'multiarch':sysconfig.get_config_var('MULTIARCH'),"
    "'py_debug':sysconfig.get_config_var('Py_DEBUG'),"
    "'with_pymalloc':sysconfig.get_config_var('WITH_PYMALLOC'),"
    "'config_args':sysconfig.get_config_var('CONFIG_ARGS'),"
    "'math_origin':importlib.util.find_spec('math').origin},sort_keys=True,separators=(',',':')))"
)


def python_source_archive_receipt() -> dict[str, object]:
    """Return the exact source archive contract for route-local capture."""

    failure = "EXACT_TOOLCHAIN_PYTHON_ARCHIVE_UNSAFE"
    chain_before = _qualified_directory_chain(
        _EXPECTED_PYTHON_ARCHIVE.parent,
        _EXPECTED_PYTHON_LOCAL_ANCHOR,
        failure,
    )
    archive_before = _qualified_file_record(
        _EXPECTED_PYTHON_ARCHIVE,
        _EXPECTED_PYTHON_ARCHIVE.parent,
        failure,
    )
    archive_after = _qualified_file_record(
        _EXPECTED_PYTHON_ARCHIVE,
        _EXPECTED_PYTHON_ARCHIVE.parent,
        failure,
    )
    chain_after = _qualified_directory_chain(
        _EXPECTED_PYTHON_ARCHIVE.parent,
        _EXPECTED_PYTHON_LOCAL_ANCHOR,
        failure,
    )
    if (
        chain_before != chain_after
        or archive_before != archive_after
        or archive_after.get("sha256") != _EXPECTED_PYTHON_SOURCE_ARCHIVE_SHA256
        or archive_after.get("bytes") != _EXPECTED_PYTHON_SOURCE_ARCHIVE_BYTES
    ):
        raise RouteError("EXACT_TOOLCHAIN_PYTHON_ARCHIVE_MISMATCH")
    return {
        "schema_version": 1,
        "source_path": str(_EXPECTED_PYTHON_ARCHIVE),
        "capture_relative_path": _EXPECTED_PYTHON_CAPTURE_RELATIVE,
        "sha256": _EXPECTED_PYTHON_SOURCE_ARCHIVE_SHA256,
        "bytes": _EXPECTED_PYTHON_SOURCE_ARCHIVE_BYTES,
        "mode": archive_after["mode"],
        "uid": archive_after["uid"],
        "gid": archive_after["gid"],
        "nlink": archive_after["nlink"],
        "source_tree_sha256": _EXPECTED_PYTHON_SOURCE_TREE_SHA256,
        "source_tree_record_count": _EXPECTED_PYTHON_RUNTIME_RECORD_COUNT,
        "source_tree_file_count": _EXPECTED_PYTHON_RUNTIME_FILE_COUNT,
        "source_tree_bytes": _EXPECTED_PYTHON_RUNTIME_BYTES,
    }


def _verify_python_runtime_tree(identity: dict[str, object]) -> None:
    expected = {
        "root": str(_EXPECTED_PYTHON_ROOT),
        "sha256": _EXPECTED_PYTHON_RUNTIME_TREE_SHA256,
        "record_count": _EXPECTED_PYTHON_RUNTIME_RECORD_COUNT,
        "file_count": _EXPECTED_PYTHON_RUNTIME_FILE_COUNT,
        "bytes": _EXPECTED_PYTHON_RUNTIME_BYTES,
        "symlinks": _EXPECTED_PYTHON_SYMLINKS,
    }
    if identity != expected:
        raise RouteError("EXACT_TOOLCHAIN_PYTHON_TREE_MISMATCH")


def _python_runtime_tree() -> dict[str, object]:
    failure = "EXACT_TOOLCHAIN_PYTHON_TREE_UNSAFE"
    root_chain = _qualified_directory_chain(
        _EXPECTED_PYTHON_ROOT,
        _EXPECTED_PYTHON_LOCAL_ANCHOR,
        failure,
    )
    try:
        root_metadata = _EXPECTED_PYTHON_ROOT.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o555
    ):
        raise RouteError(failure)

    def discover() -> list[Path]:
        try:
            return sorted(
                _EXPECTED_PYTHON_ROOT.rglob("*"),
                key=lambda item: item.relative_to(_EXPECTED_PYTHON_ROOT).as_posix(),
            )
        except OSError as error:
            raise RouteError(failure) from error

    paths = discover()
    records: list[dict[str, object]] = []
    symlinks: dict[str, str] = {}
    file_count = 0
    total_bytes = 0
    for path in paths:
        relative = path.relative_to(_EXPECTED_PYTHON_ROOT).as_posix()
        try:
            metadata = path.lstat()
        except OSError as error:
            raise RouteError(failure) from error
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
            raise RouteError(failure)
        if stat.S_ISDIR(metadata.st_mode):
            if stat.S_IMODE(metadata.st_mode) != 0o555:
                raise RouteError(failure)
            continue
        if stat.S_ISLNK(metadata.st_mode):
            try:
                target = os.readlink(path)
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise RouteError(failure) from error
            if metadata.st_nlink != 1 or not resolved.is_relative_to(_EXPECTED_PYTHON_ROOT):
                raise RouteError(failure)
            symlinks[relative] = target
            records.append({"path": relative, "kind": "symlink", "target": target})
            continue
        record = _qualified_file_record(path, _EXPECTED_PYTHON_ROOT, failure)
        if record["mode"] not in {"0444", "0555"}:
            raise RouteError(failure)
        file_count += 1
        total_bytes += cast(int, record["bytes"])
        records.append(
            {
                "path": relative,
                "kind": "file",
                "mode": record["mode"],
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            }
        )
    if [path.relative_to(_EXPECTED_PYTHON_ROOT).as_posix() for path in discover()] != [
        path.relative_to(_EXPECTED_PYTHON_ROOT).as_posix() for path in paths
    ] or _qualified_directory_chain(
        _EXPECTED_PYTHON_ROOT,
        _EXPECTED_PYTHON_LOCAL_ANCHOR,
        failure,
    ) != root_chain:
        raise RouteError("EXACT_TOOLCHAIN_PYTHON_TREE_CHANGED")
    identity = {
        "root": str(_EXPECTED_PYTHON_ROOT),
        "sha256": hashlib.sha256(
            json.dumps(
                {"records": records},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "record_count": len(records),
        "file_count": file_count,
        "bytes": total_bytes,
        "symlinks": symlinks,
    }
    _verify_python_runtime_tree(identity)
    return identity


def _python() -> ExactToolchain:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:python:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    tree_before = _python_runtime_tree()
    archive_chain_before = _qualified_directory_chain(
        _EXPECTED_PYTHON_ARCHIVE.parent,
        _EXPECTED_PYTHON_LOCAL_ANCHOR,
        "EXACT_TOOLCHAIN_PYTHON_ARCHIVE_UNSAFE",
    )
    archive_before = _qualified_file_record(
        _EXPECTED_PYTHON_ARCHIVE,
        _EXPECTED_PYTHON_ARCHIVE.parent,
        "EXACT_TOOLCHAIN_PYTHON_ARCHIVE_UNSAFE",
    )
    executable_before = _qualified_file_record(
        _EXPECTED_PYTHON_EXECUTABLE,
        _EXPECTED_PYTHON_ROOT,
        "EXACT_TOOLCHAIN_PYTHON_EXECUTABLE_UNSAFE",
    )
    libpython_before = _qualified_file_record(
        _EXPECTED_PYTHON_LIBPYTHON,
        _EXPECTED_PYTHON_ROOT,
        "EXACT_TOOLCHAIN_PYTHON_LIBPYTHON_UNSAFE",
    )
    observed = _output([str(_EXPECTED_PYTHON_EXECUTABLE), "-I", "-B", "-c", _PYTHON_RUNTIME_IDENTITY_SCRIPT])
    try:
        runtime = json.loads(observed)
    except json.JSONDecodeError as error:
        raise RouteError("EXACT_TOOLCHAIN_PYTHON_IDENTITY_INVALID") from error
    libpython_after = _qualified_file_record(
        _EXPECTED_PYTHON_LIBPYTHON,
        _EXPECTED_PYTHON_ROOT,
        "EXACT_TOOLCHAIN_PYTHON_LIBPYTHON_UNSAFE",
    )
    executable_after = _qualified_file_record(
        _EXPECTED_PYTHON_EXECUTABLE,
        _EXPECTED_PYTHON_ROOT,
        "EXACT_TOOLCHAIN_PYTHON_EXECUTABLE_UNSAFE",
    )
    archive_after = _qualified_file_record(
        _EXPECTED_PYTHON_ARCHIVE,
        _EXPECTED_PYTHON_ARCHIVE.parent,
        "EXACT_TOOLCHAIN_PYTHON_ARCHIVE_UNSAFE",
    )
    archive_chain_after = _qualified_directory_chain(
        _EXPECTED_PYTHON_ARCHIVE.parent,
        _EXPECTED_PYTHON_LOCAL_ANCHOR,
        "EXACT_TOOLCHAIN_PYTHON_ARCHIVE_UNSAFE",
    )
    tree_after = _python_runtime_tree()
    if (
        tree_before != tree_after
        or archive_before != archive_after
        or archive_chain_before != archive_chain_after
        or executable_before != executable_after
        or libpython_before != libpython_after
        or executable_after.get("sha256") != _EXPECTED_PYTHON_EXECUTABLE_SHA256
        or executable_after.get("bytes") != _EXPECTED_PYTHON_EXECUTABLE_BYTES
        or libpython_after.get("sha256") != _EXPECTED_PYTHON_LIBPYTHON_SHA256
        or libpython_after.get("bytes") != _EXPECTED_PYTHON_LIBPYTHON_BYTES
        or archive_after.get("sha256") != _EXPECTED_PYTHON_SOURCE_ARCHIVE_SHA256
        or archive_after.get("bytes") != _EXPECTED_PYTHON_SOURCE_ARCHIVE_BYTES
        or hashlib.sha256(observed.encode("utf-8")).hexdigest() != _EXPECTED_PYTHON_RUNTIME_IDENTITY_SHA256
        or runtime.get("version") != "3.12.12"
        or runtime.get("implementation") != "cpython"
        or runtime.get("executable") != str(_EXPECTED_PYTHON_EXECUTABLE)
        or runtime.get("prefix") != str(_EXPECTED_PYTHON_ROOT)
        or runtime.get("base_prefix") != str(_EXPECTED_PYTHON_ROOT)
        or runtime.get("stdlib") != str(_EXPECTED_PYTHON_STDLIB)
        or runtime.get("math_origin") != "built-in"
    ):
        raise RouteError("EXACT_TOOLCHAIN_MISMATCH:python:expected=3.12.12+20260211")
    return ExactToolchain(
        "python",
        "3.12.12+20260211",
        str(_EXPECTED_PYTHON_EXECUTABLE),
        str(_EXPECTED_PYTHON_LIBPYTHON),
        profile=(
            "python-toolchain-closure-schema=v1",
            "platform=Darwin/arm64",
            "distribution=python-build-standalone-20260211-install-only-stripped",
            f"python-root={_EXPECTED_PYTHON_ROOT}",
            f"python-source-archive-sha256={_EXPECTED_PYTHON_SOURCE_ARCHIVE_SHA256}",
            f"python-source-archive-bytes={_EXPECTED_PYTHON_SOURCE_ARCHIVE_BYTES}",
            f"python-source-tree-sha256={_EXPECTED_PYTHON_SOURCE_TREE_SHA256}",
            f"python-runtime-tree-sha256={tree_after['sha256']}",
            f"python-runtime-tree-record-count={tree_after['record_count']}",
            f"python-runtime-tree-file-count={tree_after['file_count']}",
            f"python-runtime-tree-bytes={tree_after['bytes']}",
            f"python-runtime-identity-sha256={_EXPECTED_PYTHON_RUNTIME_IDENTITY_SHA256}",
            f"libpython-sha256={_EXPECTED_PYTHON_LIBPYTHON_SHA256}",
            "math-runtime=built-in-via-libpython3.12.dylib",
            "python-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=_EXPECTED_PYTHON_EXECUTABLE_SHA256,
        auxiliary_sha256=_EXPECTED_PYTHON_LIBPYTHON_SHA256,
    )


def _csharp() -> ExactToolchain:
    # The exact .NET distribution is selected by fixed identity, not by the
    # caller's ambient PATH.  This keeps the fresh Batch 29 child usable while
    # its PATH intentionally excludes user and Homebrew tool directories.
    declared = _EXPECTED_DOTNET_SHIM
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
    shim_before = _node_shim_identity()
    node_before = _node_dependency_closure()
    _verify_node_dependency_closure(node_before)
    compiler_before = _typescript_compiler_closure()
    _verify_typescript_compiler_closure(compiler_before)
    _node_runtime_identity()
    typescript_version = _output([str(_EXPECTED_NODE_EXECUTABLE), str(_EXPECTED_TYPESCRIPT_LAUNCHER), "--version"])
    compiler_after = _typescript_compiler_closure()
    _verify_typescript_compiler_closure(compiler_after)
    node_after = _node_dependency_closure()
    _verify_node_dependency_closure(node_after)
    shim_after = _node_shim_identity()
    if (
        shim_before != shim_after
        or node_before != node_after
        or compiler_before != compiler_after
        or typescript_version != "Version 5.9.2"
    ):
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:typescript:expected=Node26.0.0/TypeScript5.9.2:observed={typescript_version}"
        )
    return ExactToolchain(
        "typescript",
        "5.9.2 / Node 26.0.0",
        str(_EXPECTED_NODE_EXECUTABLE),
        str(_EXPECTED_TYPESCRIPT_LAUNCHER),
        profile=(
            "typescript-toolchain-closure-schema=v1",
            "platform=Darwin/arm64",
            "typescript-language-version=5.9.2",
            f"typescript-package-root={_EXPECTED_TYPESCRIPT_ROOT}",
            f"typescript-closure-sha256={compiler_after['sha256']}",
            f"typescript-closure-file-count={compiler_after['file_count']}",
            f"typescript-closure-bytes={compiler_after['bytes']}",
            f"typescript-source-manifest-sha256={_EXPECTED_TYPESCRIPT_SOURCE_MANIFEST_SHA256}",
            f"typescript-standard-library-file-count={_EXPECTED_TYPESCRIPT_LIBRARY_FILE_COUNT}",
            f"typescript-launcher-sha256={_EXPECTED_TYPESCRIPT_LAUNCHER_SHA256}",
            f"typescript-tsc-shim-sha256={_EXPECTED_TYPESCRIPT_TSC_SHIM_SHA256}",
            f"typescript-compiler-sha256={_EXPECTED_TYPESCRIPT_COMPILER_SHA256}",
            f"typescript-parser-sha256={_EXPECTED_TYPESCRIPT_PARSER_SHA256}",
            f"typescript-package-json-sha256={_EXPECTED_TYPESCRIPT_PACKAGE_SHA256}",
            f"typescript-license-sha256={_EXPECTED_TYPESCRIPT_LICENSE_SHA256}",
            f"node-closure-sha256={node_after['sha256']}",
            f"node-closure-component-count={node_after['component_count']}",
            f"node-closure-edge-count={node_after['edge_count']}",
            f"node-closure-system-edge-count={node_after['system_edge_count']}",
            "otool-system-tool-content-soundness=NOT_RUN",
            "dyld-system-library-content-soundness=NOT_RUN",
            "typescript-compiler-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=_EXPECTED_NODE_SHA256,
        auxiliary_sha256=_EXPECTED_TYPESCRIPT_LAUNCHER_SHA256,
    )


_EXPECTED_HOMEBREW_PREFIX = Path("/opt/homebrew")
_EXPECTED_HOMEBREW_CELLAR = _EXPECTED_HOMEBREW_PREFIX / "Cellar"
_EXPECTED_NODE_ROOT = _EXPECTED_HOMEBREW_CELLAR / "node" / "26.0.0"
_EXPECTED_NODE_SHIM = _EXPECTED_HOMEBREW_PREFIX / "bin" / "node"
_EXPECTED_NODE_EXECUTABLE = _EXPECTED_NODE_ROOT / "bin" / "node"
_EXPECTED_NODE_LIBNODE = _EXPECTED_NODE_ROOT / "lib" / "libnode.147.dylib"
_EXPECTED_NODE_OTOOL = Path("/usr/bin/otool")
_EXPECTED_NODE_SHIM_TARGET = "../Cellar/node/26.0.0/bin/node"
_EXPECTED_NODE_SHA256 = "73cc3e9b5d2b1753ea3395a5bf39787ef85f20f048a0f0744761860b81b8fbdb"
_EXPECTED_NODE_BYTES = 68_672
_EXPECTED_NODE_LIBNODE_SHA256 = "24ff9dcc3d953532fde1e5270fab9331279fb60fcc5747bbb5cf1537cba20d47"
_EXPECTED_NODE_LIBNODE_BYTES = 70_843_136
# This digest is over the canonical recursive ``otool`` manifest, including
# every non-system component's resolved path, bytes, SHA-256, mode, uid, gid,
# and link count; every loader/load-path/resolved-path edge; and every declared
# system-library edge.  It is intentionally a fixed repository expectation,
# not a digest copied from the observed closure at runtime.
_EXPECTED_NODE_CLOSURE_SHA256 = "bd919085f8ae40bca10d5a2da36542eb90c5f18424dc60780c73c70b90d4244b"
_EXPECTED_NODE_CLOSURE_COMPONENT_COUNT = 25
_EXPECTED_NODE_CLOSURE_EDGE_COUNT = 49
_EXPECTED_NODE_CLOSURE_SYSTEM_EDGE_COUNT = 43
_EXPECTED_NODE_CLOSURE_BYTES = 120_513_104
_EXPECTED_NODE_SYSTEM_EDGE_SHA256 = "74106326c0673ff63a85e6fbc892c55a7c7f329eaad0fd715817beae4ba2b6c4"
_EXPECTED_NODE_TOPOLOGY_SHA256 = (
    "2a77ac1d4bcf11286a97e403060b6a6490d21127857b6d1ba21806f026451bfd"
)
_EXPECTED_NODE_PROCESS_VERSIONS = (
    '{"acorn":"8.16.0","ada":"3.4.4","amaro":"1.1.8","ares":"1.34.6",'
    '"brotli":"1.2.0","cldr":"48.0","icu":"78.3","lief":"0.17.0",'
    '"llhttp":"9.4.1","merve":"1.2.2","modules":"147","napi":"10",'
    '"nbytes":"0.1.4","ncrypto":"0.0.1","nghttp2":"1.69.0","nghttp3":"",'
    '"ngtcp2":"","node":"26.0.0","openssl":"3.6.3","simdjson":"4.6.3",'
    '"simdutf":"7.7.0","sqlite":"3.53.0","tz":"2026a","undici":"8.0.2",'
    '"unicode":"17.0","uv":"1.52.1","uvwasi":"0.0.23",'
    '"v8":"14.6.202.33-node.19","zlib":"1.2.12","zstd":"1.5.7"}'
)
_EXPECTED_NODE_PROCESS_VERSIONS_SHA256 = "3d1c55b1d3598ed3740b8d5461151069351d53495649a1efb718f6f858b48d52"
_NODE_TOPOLOGY_CACHE: dict[str, object] | None = None


_EXPECTED_TYPESCRIPT_CACHE_ANCHOR = Path("/Users/stephen/.local")
_EXPECTED_TYPESCRIPT_ROOT = Path(
    "/Users/stephen/.local/share/elmos/toolchains/typescript/5.9.2/"
    "sha256-61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
_EXPECTED_TYPESCRIPT_LAUNCHER = _EXPECTED_TYPESCRIPT_ROOT / "bin" / "tsc"
_EXPECTED_TYPESCRIPT_TSC_SHIM = _EXPECTED_TYPESCRIPT_ROOT / "lib" / "tsc.js"
_EXPECTED_TYPESCRIPT_COMPILER = _EXPECTED_TYPESCRIPT_ROOT / "lib" / "_tsc.js"
_EXPECTED_TYPESCRIPT_PARSER = _EXPECTED_TYPESCRIPT_ROOT / "lib" / "typescript.js"
_EXPECTED_TYPESCRIPT_PACKAGE = _EXPECTED_TYPESCRIPT_ROOT / "package.json"
_EXPECTED_TYPESCRIPT_LICENSE = _EXPECTED_TYPESCRIPT_ROOT / "LICENSE.txt"
_EXPECTED_TYPESCRIPT_LAUNCHER_SHA256 = "8d5fa5bd883fec0979fc2004f1fe1d99aef40570155d550eadc0b03b55513bf0"
_EXPECTED_TYPESCRIPT_LAUNCHER_BYTES = 45
_EXPECTED_TYPESCRIPT_TSC_SHIM_SHA256 = "2cffde0b8c6760dfb0b5b0382bbb7e00ba6a8b2d981b9205b256a700a481d983"
_EXPECTED_TYPESCRIPT_TSC_SHIM_BYTES = 267
_EXPECTED_TYPESCRIPT_COMPILER_SHA256 = "a040f97c9d0223f64c8ebc380c5e48eb7945f1142f7c1dc9c3ec4acdb6c1c613"
_EXPECTED_TYPESCRIPT_COMPILER_BYTES = 6_211_917
_EXPECTED_TYPESCRIPT_PARSER_SHA256 = "e5f1f6b3e82228a89873cc7b941b2465185e839c0692860f83e3e63e53f94c2b"
_EXPECTED_TYPESCRIPT_PARSER_BYTES = 9_111_680
_EXPECTED_TYPESCRIPT_PACKAGE_SHA256 = "5a0bb7f286c4b3f1413a42c05f902311b161f70e5f52d9da10490443bfd595a3"
_EXPECTED_TYPESCRIPT_PACKAGE_BYTES = 3_620
_EXPECTED_TYPESCRIPT_LICENSE_SHA256 = "a7d00bfd54525bc694b6e32f64c7ebcf5e6b7ae3657be5cc12767bce74654a47"
_EXPECTED_TYPESCRIPT_LICENSE_BYTES = 9_197
_EXPECTED_TYPESCRIPT_SOURCE_MANIFEST_SHA256 = (
    "61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
_EXPECTED_TYPESCRIPT_RUNTIME_MANIFEST_SHA256 = (
    "2157e43e757e433c733e144df7409a54f5040faa22af4a9b13de977a663fd939"
)
_EXPECTED_TYPESCRIPT_CAPTURE_RELATIVE = (
    "runtime/typescript/sha256-" + _EXPECTED_TYPESCRIPT_SOURCE_MANIFEST_SHA256
)
_EXPECTED_TYPESCRIPT_CLOSURE_SHA256 = (
    "aaab28fada5888d767a49f86d40e5a0c9073b23412257ccb3755e9c8fb8080d9"
)
_EXPECTED_TYPESCRIPT_CLOSURE_FILE_COUNT = 108
_EXPECTED_TYPESCRIPT_LIBRARY_FILE_COUNT = 102
_EXPECTED_TYPESCRIPT_CLOSURE_BYTES = 19_067_381


def _typescript_directory_chain(directory: Path, failure: str) -> tuple[tuple[object, ...], ...]:
    try:
        relative = directory.relative_to(_EXPECTED_TYPESCRIPT_CACHE_ANCHOR)
    except ValueError as error:
        raise RouteError(failure) from error
    cursor = _EXPECTED_TYPESCRIPT_CACHE_ANCHOR
    identities: list[tuple[object, ...]] = []
    try:
        for part in ("", *relative.parts):
            if part:
                cursor = cursor / part
            metadata = cursor.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
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
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    return tuple(identities)


def _typescript_file_binding(path: Path, role: str) -> dict[str, str | int]:
    failure = f"EXACT_TOOLCHAIN_TYPESCRIPT_{role.upper().replace('-', '_')}_UNSAFE"
    try:
        path.relative_to(_EXPECTED_TYPESCRIPT_ROOT)
    except ValueError as error:
        raise RouteError(failure) from error
    directory_chain = _typescript_directory_chain(path.parent, failure)
    try:
        if path.resolve(strict=True) != path:
            raise RouteError(failure)
        before = path.lstat()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened_before = os.fstat(descriptor)
            digest = hashlib.sha256()
            byte_count = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
                byte_count += len(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    if (
        before_identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
        or before_identity
        != (
            opened_before.st_dev,
            opened_before.st_ino,
            opened_before.st_mode,
            opened_before.st_size,
            opened_before.st_uid,
            opened_before.st_gid,
            opened_before.st_nlink,
            opened_before.st_mtime_ns,
        )
        or before_identity
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_size,
            opened_after.st_uid,
            opened_after.st_gid,
            opened_after.st_nlink,
            opened_after.st_mtime_ns,
        )
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(after.st_mode) & 0o022
        or after.st_nlink != 1
        or byte_count != after.st_size
        or _typescript_directory_chain(path.parent, failure) != directory_chain
    ):
        raise RouteError(failure)
    return {
        "role": role,
        "resolved_path": str(path),
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "uid": after.st_uid,
        "gid": after.st_gid,
        "nlink": after.st_nlink,
    }


def _typescript_package_root_binding() -> dict[str, str | int]:
    failure = "EXACT_TOOLCHAIN_TYPESCRIPT_PACKAGE_ROOT_UNSAFE"
    chain_before = _typescript_directory_chain(_EXPECTED_TYPESCRIPT_ROOT, failure)
    try:
        before = _EXPECTED_TYPESCRIPT_ROOT.lstat()
        resolved = _EXPECTED_TYPESCRIPT_ROOT.resolve(strict=True)
        after = _EXPECTED_TYPESCRIPT_ROOT.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    if (
        not stat.S_ISDIR(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o555
        or before.st_uid != os.getuid()
        or resolved != _EXPECTED_TYPESCRIPT_ROOT
        or identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
        or _typescript_directory_chain(_EXPECTED_TYPESCRIPT_ROOT, failure) != chain_before
    ):
        raise RouteError(failure)
    return {
        "root": str(resolved),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "uid": after.st_uid,
        "gid": after.st_gid,
        "nlink": after.st_nlink,
    }


def _typescript_closure_identity(manifest: dict[str, object]) -> dict[str, object]:
    try:
        if set(manifest) != {
            "schema_version",
            "kind",
            "package_root",
            "directories",
            "files",
            "semantic_soundness",
        }:
            raise ValueError
        files = cast(list[dict[str, object]], manifest["files"])
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            "manifest": manifest,
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "file_count": len(files),
            "bytes": sum(cast(int, item["bytes"]) for item in files),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID") from error


def _typescript_package_directory_binding(relative: str) -> dict[str, str | int]:
    failure = "EXACT_TOOLCHAIN_TYPESCRIPT_PACKAGE_DIRECTORY_UNSAFE"
    directory = _EXPECTED_TYPESCRIPT_ROOT / relative
    chain_before = _typescript_directory_chain(directory, failure)
    try:
        before = directory.lstat()
        resolved = directory.resolve(strict=True)
        after = directory.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    if (
        not stat.S_ISDIR(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o555
        or before.st_uid != os.getuid()
        or resolved != directory
        or identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
        or _typescript_directory_chain(directory, failure) != chain_before
    ):
        raise RouteError(failure)
    return {
        "relative_path": relative,
        "resolved_path": str(resolved),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "uid": after.st_uid,
        "gid": after.st_gid,
        "nlink": after.st_nlink,
    }


def _typescript_compiler_paths() -> tuple[Path, ...]:
    failure = "EXACT_TOOLCHAIN_TYPESCRIPT_PACKAGE_INVENTORY_INVALID"
    try:
        descendants = sorted(
            _EXPECTED_TYPESCRIPT_ROOT.rglob("*"),
            key=lambda item: item.relative_to(_EXPECTED_TYPESCRIPT_ROOT).as_posix(),
        )
    except OSError as error:
        raise RouteError(failure) from error
    directories: set[str] = set()
    files: list[Path] = []
    try:
        for item in descendants:
            relative = item.relative_to(_EXPECTED_TYPESCRIPT_ROOT).as_posix()
            metadata = item.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                directories.add(relative)
            elif stat.S_ISREG(metadata.st_mode):
                files.append(item)
            else:
                raise RouteError(failure)
    except OSError as error:
        raise RouteError(failure) from error
    if directories != {"bin", "lib"}:
        raise RouteError(failure)
    core = {
        _EXPECTED_TYPESCRIPT_LAUNCHER,
        _EXPECTED_TYPESCRIPT_TSC_SHIM,
        _EXPECTED_TYPESCRIPT_COMPILER,
        _EXPECTED_TYPESCRIPT_PARSER,
        _EXPECTED_TYPESCRIPT_PACKAGE,
        _EXPECTED_TYPESCRIPT_LICENSE,
    }
    observed = set(files)
    libraries = observed - core
    if (
        not core <= observed
        or len(observed) != _EXPECTED_TYPESCRIPT_CLOSURE_FILE_COUNT
        or len(libraries) != _EXPECTED_TYPESCRIPT_LIBRARY_FILE_COUNT
        or any(
            path.parent != _EXPECTED_TYPESCRIPT_ROOT / "lib"
            or not path.name.endswith(".d.ts")
            for path in libraries
        )
    ):
        raise RouteError(failure)
    return tuple(files)


def _typescript_compiler_closure() -> dict[str, object]:
    role_by_path = {
        _EXPECTED_TYPESCRIPT_LAUNCHER: "launcher",
        _EXPECTED_TYPESCRIPT_TSC_SHIM: "tsc-shim",
        _EXPECTED_TYPESCRIPT_COMPILER: "compiler",
        _EXPECTED_TYPESCRIPT_PARSER: "parser",
        _EXPECTED_TYPESCRIPT_PACKAGE: "package-json",
        _EXPECTED_TYPESCRIPT_LICENSE: "license",
    }
    paths_before = _typescript_compiler_paths()
    directories_before = [
        _typescript_package_directory_binding(relative)
        for relative in ("bin", "lib")
    ]
    files = [
        _typescript_file_binding(
            path,
            role_by_path.get(path, f"standard-library:{path.name}"),
        )
        for path in paths_before
    ]
    directories_after = [
        _typescript_package_directory_binding(relative)
        for relative in ("bin", "lib")
    ]
    if (
        paths_before != _typescript_compiler_paths()
        or directories_before != directories_after
    ):
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_CHANGED_DURING_PROBE")
    manifest: dict[str, object] = {
        "schema_version": 2,
        "kind": "elmos.typescript-5.9.2-full-stdlib-compiler-closure",
        "package_root": _typescript_package_root_binding(),
        "directories": directories_after,
        "files": sorted(files, key=lambda item: str(item["role"])),
        "semantic_soundness": "NOT_RUN",
    }
    return _typescript_closure_identity(manifest)


def _verify_typescript_compiler_closure(identity: dict[str, object]) -> None:
    try:
        manifest = cast(dict[str, object], identity["manifest"])
        recomputed = _typescript_closure_identity(manifest)
        files = cast(list[dict[str, object]], manifest["files"])
        observed = {str(item["role"]): item for item in files}
    except (KeyError, TypeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID") from error
    for field in ("sha256", "file_count", "bytes"):
        if recomputed[field] != identity.get(field):
            raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_IDENTITY_INVALID")
    expected = {
        "launcher": (
            _EXPECTED_TYPESCRIPT_LAUNCHER,
            _EXPECTED_TYPESCRIPT_LAUNCHER_SHA256,
            _EXPECTED_TYPESCRIPT_LAUNCHER_BYTES,
        ),
        "tsc-shim": (
            _EXPECTED_TYPESCRIPT_TSC_SHIM,
            _EXPECTED_TYPESCRIPT_TSC_SHIM_SHA256,
            _EXPECTED_TYPESCRIPT_TSC_SHIM_BYTES,
        ),
        "compiler": (
            _EXPECTED_TYPESCRIPT_COMPILER,
            _EXPECTED_TYPESCRIPT_COMPILER_SHA256,
            _EXPECTED_TYPESCRIPT_COMPILER_BYTES,
        ),
        "parser": (
            _EXPECTED_TYPESCRIPT_PARSER,
            _EXPECTED_TYPESCRIPT_PARSER_SHA256,
            _EXPECTED_TYPESCRIPT_PARSER_BYTES,
        ),
        "package-json": (
            _EXPECTED_TYPESCRIPT_PACKAGE,
            _EXPECTED_TYPESCRIPT_PACKAGE_SHA256,
            _EXPECTED_TYPESCRIPT_PACKAGE_BYTES,
        ),
        "license": (
            _EXPECTED_TYPESCRIPT_LICENSE,
            _EXPECTED_TYPESCRIPT_LICENSE_SHA256,
            _EXPECTED_TYPESCRIPT_LICENSE_BYTES,
        ),
    }
    if len(observed) != len(files) or not set(expected) <= set(observed):
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_MISMATCH")
    for role, (path, digest, byte_count) in expected.items():
        item = observed[role]
        if item.get("resolved_path") != str(path) or item.get("sha256") != digest or item.get("bytes") != byte_count:
            label = {
                "launcher": "LAUNCHER",
                "parser": "PARSER",
            }.get(role, "COMPILER_CLOSURE")
            raise RouteError(f"EXACT_TOOLCHAIN_TYPESCRIPT_{label}_MISMATCH")
    source_records: list[dict[str, object]] = []
    runtime_records: list[dict[str, object]] = []
    standard_library_count = 0
    for role, item in observed.items():
        try:
            resolved = Path(cast(str, item["resolved_path"]))
            relative = resolved.relative_to(_EXPECTED_TYPESCRIPT_ROOT).as_posix()
            byte_count = cast(int, item["bytes"])
            digest = cast(str, item["sha256"])
            mode = cast(str, item["mode"])
        except (KeyError, TypeError, ValueError) as error:
            raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_MISMATCH") from error
        if role.startswith("standard-library:"):
            if (
                role != f"standard-library:{resolved.name}"
                or resolved.parent != _EXPECTED_TYPESCRIPT_ROOT / "lib"
                or not resolved.name.endswith(".d.ts")
            ):
                raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_STDLIB_MISMATCH")
            standard_library_count += 1
        elif role not in expected:
            raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_MISMATCH")
        source_records.append(
            {"path": relative, "bytes": byte_count, "sha256": digest}
        )
        runtime_records.append(
            {
                "path": relative,
                "bytes": byte_count,
                "sha256": digest,
                "mode": mode,
            }
        )
    source_records.sort(key=lambda item: cast(str, item["path"]))
    runtime_records.sort(key=lambda item: cast(str, item["path"]))
    if (
        standard_library_count != _EXPECTED_TYPESCRIPT_LIBRARY_FILE_COUNT
        or hashlib.sha256(
            json.dumps(
                {"files": source_records}, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        != _EXPECTED_TYPESCRIPT_SOURCE_MANIFEST_SHA256
        or hashlib.sha256(
            json.dumps(
                {"files": runtime_records}, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        != _EXPECTED_TYPESCRIPT_RUNTIME_MANIFEST_SHA256
    ):
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_STDLIB_MISMATCH")
    if (
        recomputed["sha256"] != _EXPECTED_TYPESCRIPT_CLOSURE_SHA256
        or recomputed["file_count"] != _EXPECTED_TYPESCRIPT_CLOSURE_FILE_COUNT
        or recomputed["bytes"] != _EXPECTED_TYPESCRIPT_CLOSURE_BYTES
    ):
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_MISMATCH")


def typescript_compiler_capture_receipt() -> dict[str, object]:
    """Return the exact full compiler closure for route-local capture."""

    before = _typescript_compiler_closure()
    _verify_typescript_compiler_closure(before)
    after = _typescript_compiler_closure()
    _verify_typescript_compiler_closure(after)
    if before != after:
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_CHANGED_DURING_PROBE")
    manifest = cast(dict[str, object], after["manifest"])
    files = cast(list[dict[str, object]], manifest["files"])
    records = []
    for item in files:
        resolved = Path(cast(str, item["resolved_path"]))
        records.append(
            {
                "path": resolved.relative_to(_EXPECTED_TYPESCRIPT_ROOT).as_posix(),
                "source_path": str(resolved),
                "sha256": cast(str, item["sha256"]),
                "bytes": cast(int, item["bytes"]),
                "mode": cast(str, item["mode"]),
            }
        )
    records.sort(key=lambda item: cast(str, item["path"]))
    return {
        "schema_version": 1,
        "capture_relative_path": _EXPECTED_TYPESCRIPT_CAPTURE_RELATIVE,
        "source_root": str(_EXPECTED_TYPESCRIPT_ROOT),
        "source_manifest_sha256": _EXPECTED_TYPESCRIPT_SOURCE_MANIFEST_SHA256,
        "runtime_manifest_sha256": _EXPECTED_TYPESCRIPT_RUNTIME_MANIFEST_SHA256,
        "compiler_closure_sha256": cast(str, after["sha256"]),
        "file_count": cast(int, after["file_count"]),
        "bytes": cast(int, after["bytes"]),
        "files": records,
        "semantic_soundness": "NOT_RUN",
    }


def typescript_parser_receipt() -> dict[str, str | int]:
    """Return the stable parser only after sealing the full compiler closure.

    Native analyzers use this public boundary instead of knowing the cache
    layout or reaching into a live frontend ``node_modules`` tree.  Calling it
    before and after an analysis provides an independently recomputed receipt.
    """

    before = _typescript_compiler_closure()
    _verify_typescript_compiler_closure(before)
    after = _typescript_compiler_closure()
    _verify_typescript_compiler_closure(after)
    if before != after:
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_CHANGED_DURING_PROBE")
    try:
        manifest = cast(dict[str, object], after["manifest"])
        files = cast(list[dict[str, object]], manifest["files"])
        parser = next(item for item in files if item.get("role") == "parser")
    except (KeyError, StopIteration, TypeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_PARSER_RECEIPT_INVALID") from error
    return {
        "schema_version": 1,
        "path": cast(str, parser["resolved_path"]),
        "sha256": cast(str, parser["sha256"]),
        "bytes": cast(int, parser["bytes"]),
        "mode": cast(str, parser["mode"]),
        "uid": cast(int, parser["uid"]),
        "gid": cast(int, parser["gid"]),
        "nlink": cast(int, parser["nlink"]),
        "compiler_root": str(_EXPECTED_TYPESCRIPT_ROOT),
        "compiler_closure_sha256": cast(str, after["sha256"]),
        "compiler_closure_file_count": cast(int, after["file_count"]),
        "compiler_closure_bytes": cast(int, after["bytes"]),
        "semantic_soundness": "NOT_RUN",
    }


def _node_directory_chain(directory: Path, failure: str) -> tuple[tuple[object, ...], ...]:
    """Validate one resolved Homebrew Cellar directory chain without following links."""

    try:
        directory.relative_to(_EXPECTED_HOMEBREW_CELLAR)
    except ValueError as error:
        raise RouteError(failure) from error
    cursor = Path("/")
    identities: list[tuple[object, ...]] = []
    try:
        for part in directory.parts[1:]:
            cursor = cursor / part
            metadata = cursor.lstat()
            below_cellar = cursor != _EXPECTED_HOMEBREW_CELLAR and cursor.is_relative_to(_EXPECTED_HOMEBREW_CELLAR)
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or (below_cellar and stat.S_IMODE(metadata.st_mode) & 0o022)
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
    except (OSError, ValueError) as error:
        raise RouteError(failure) from error
    return tuple(identities)


def _node_file_binding(path: Path, failure: str) -> dict[str, str | int]:
    """Read and seal one resolved Node/Homebrew component without following links."""

    try:
        path.relative_to(_EXPECTED_HOMEBREW_CELLAR)
    except ValueError as error:
        raise RouteError(failure) from error
    directory_chain = _node_directory_chain(path.parent, failure)
    try:
        if path.resolve(strict=True) != path:
            raise RouteError(failure)
        before = path.lstat()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened_before = os.fstat(descriptor)
            digest = hashlib.sha256()
            byte_count = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
                byte_count += len(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    if (
        before_identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
        or before_identity
        != (
            opened_before.st_dev,
            opened_before.st_ino,
            opened_before.st_mode,
            opened_before.st_size,
            opened_before.st_uid,
            opened_before.st_gid,
            opened_before.st_nlink,
            opened_before.st_mtime_ns,
        )
        or before_identity
        != (
            opened_after.st_dev,
            opened_after.st_ino,
            opened_after.st_mode,
            opened_after.st_size,
            opened_after.st_uid,
            opened_after.st_gid,
            opened_after.st_nlink,
            opened_after.st_mtime_ns,
        )
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(after.st_mode) & 0o022
        or after.st_nlink != 1
        or byte_count != after.st_size
        or _node_directory_chain(path.parent, failure) != directory_chain
    ):
        raise RouteError(failure)
    return {
        "resolved_path": str(path),
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "uid": after.st_uid,
        "gid": after.st_gid,
        "nlink": after.st_nlink,
    }


def _node_otool_lines(flag: str, path: Path) -> list[str]:
    if not _EXPECTED_NODE_OTOOL.is_file():
        raise RouteError("EXACT_TOOLCHAIN_NODE_OTOOL_UNAVAILABLE")
    output = _output([str(_EXPECTED_NODE_OTOOL), flag, str(path)])
    lines = output.splitlines()
    if not lines or lines[0] != f"{path}:":
        raise RouteError("EXACT_TOOLCHAIN_NODE_OTOOL_INVALID")
    return lines[1:]


def _node_otool_dependencies(path: Path) -> tuple[str, ...]:
    dependencies: list[str] = []
    for line in _node_otool_lines("-L", path):
        stripped = line.strip()
        marker = " (compatibility version "
        if marker not in stripped:
            raise RouteError("EXACT_TOOLCHAIN_NODE_OTOOL_INVALID")
        dependencies.append(stripped.split(marker, 1)[0])
    install_ids = tuple(line.strip() for line in _node_otool_lines("-D", path) if line.strip())
    if len(install_ids) > 1:
        raise RouteError("EXACT_TOOLCHAIN_NODE_OTOOL_INVALID")
    filtered = tuple(item for item in dependencies if item not in install_ids)
    if len(filtered) != len(set(filtered)):
        raise RouteError("EXACT_TOOLCHAIN_NODE_DUPLICATE_LOAD_COMMAND")
    return filtered


def _node_otool_rpaths(path: Path) -> tuple[str, ...]:
    lines = _node_otool_lines("-l", path)
    rpaths: list[str] = []
    for index, line in enumerate(lines):
        if line.strip() != "cmd LC_RPATH":
            continue
        for candidate in lines[index + 1 : index + 5]:
            stripped = candidate.strip()
            if stripped.startswith("path ") and " (offset " in stripped:
                rpaths.append(stripped[5:].rsplit(" (offset ", 1)[0])
                break
        else:
            raise RouteError("EXACT_TOOLCHAIN_NODE_OTOOL_INVALID")
    if len(rpaths) != len(set(rpaths)):
        raise RouteError("EXACT_TOOLCHAIN_NODE_DUPLICATE_RPATH")
    return tuple(rpaths)


def _node_expand_anchor(value: str, loader: Path) -> Path:
    anchors = {
        "@loader_path": loader.parent,
        "@executable_path": _EXPECTED_NODE_EXECUTABLE.parent,
    }
    for token, root in anchors.items():
        if value == token:
            return root
        prefix = token + "/"
        if value.startswith(prefix):
            return root / value[len(prefix) :]
    if value.startswith("/"):
        return Path(value)
    raise RouteError("EXACT_TOOLCHAIN_NODE_LOAD_PATH_UNSUPPORTED")


def _node_resolve_homebrew_path(candidate: Path) -> Path:
    """Resolve an ``otool`` path and require its target to be a safe Cellar file."""

    candidate = Path(os.path.normpath(str(candidate)))
    try:
        if candidate.is_relative_to(_EXPECTED_HOMEBREW_PREFIX / "opt"):
            relative = candidate.relative_to(_EXPECTED_HOMEBREW_PREFIX / "opt")
            if len(relative.parts) < 2:
                raise RouteError("EXACT_TOOLCHAIN_NODE_LOAD_PATH_UNSAFE")
            formula_link = _EXPECTED_HOMEBREW_PREFIX / "opt" / relative.parts[0]
            link_before = formula_link.lstat()
            target_before = formula_link.readlink()
            resolved = candidate.resolve(strict=True)
            link_after = formula_link.lstat()
            target_after = formula_link.readlink()
            link_identity = (
                link_before.st_dev,
                link_before.st_ino,
                link_before.st_mode,
                link_before.st_uid,
                link_before.st_gid,
                link_before.st_nlink,
                link_before.st_mtime_ns,
            )
            if (
                not stat.S_ISLNK(link_before.st_mode)
                or link_before.st_uid not in {0, os.getuid()}
                or link_before.st_nlink != 1
                or target_before.is_absolute()
                or link_identity
                != (
                    link_after.st_dev,
                    link_after.st_ino,
                    link_after.st_mode,
                    link_after.st_uid,
                    link_after.st_gid,
                    link_after.st_nlink,
                    link_after.st_mtime_ns,
                )
                or target_before != target_after
            ):
                raise RouteError("EXACT_TOOLCHAIN_NODE_LOAD_PATH_UNSAFE")
        else:
            relative = candidate.relative_to(_EXPECTED_HOMEBREW_CELLAR)
            if len(relative.parts) < 3:
                raise RouteError("EXACT_TOOLCHAIN_NODE_LOAD_PATH_UNSAFE")
            formula_root = _EXPECTED_HOMEBREW_CELLAR.joinpath(*relative.parts[:2])
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(formula_root):
                raise RouteError("EXACT_TOOLCHAIN_NODE_LOAD_PATH_UNSAFE")
        resolved.relative_to(_EXPECTED_HOMEBREW_CELLAR)
        _node_directory_chain(resolved.parent, "EXACT_TOOLCHAIN_NODE_LOAD_PATH_UNSAFE")
        metadata = resolved.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.getuid()}
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or metadata.st_nlink != 1
        ):
            raise RouteError("EXACT_TOOLCHAIN_NODE_LOAD_PATH_UNSAFE")
    except (OSError, ValueError) as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_LOAD_PATH_UNSAFE") from error
    return resolved


def _node_resolve_dependency(load_path: str, loader: Path) -> Path:
    if load_path.startswith("@rpath/"):
        suffix = load_path[len("@rpath/") :]
        matches: set[Path] = set()
        for rpath in _node_otool_rpaths(loader):
            candidate = _node_expand_anchor(rpath, loader) / suffix
            normalized = Path(os.path.normpath(str(candidate)))
            if not normalized.exists() and not normalized.is_symlink():
                continue
            # An existing but unsafe earlier RPATH candidate must fail rather
            # than be ignored in favor of a later safe path: dyld would select
            # the earlier candidate.
            matches.add(_node_resolve_homebrew_path(normalized))
        if len(matches) != 1:
            raise RouteError("EXACT_TOOLCHAIN_NODE_RPATH_AMBIGUOUS")
        return next(iter(matches))
    return _node_resolve_homebrew_path(_node_expand_anchor(load_path, loader))


def _node_closure_identity(manifest: dict[str, object]) -> dict[str, object]:
    try:
        if set(manifest) != {
            "schema_version",
            "kind",
            "install_root",
            "discovery",
            "components",
            "edges",
            "system_edges",
            "system_content_boundary",
        }:
            raise ValueError
        components = cast(list[dict[str, object]], manifest["components"])
        edges = cast(list[dict[str, object]], manifest["edges"])
        system_edges = cast(list[dict[str, object]], manifest["system_edges"])
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        system_canonical = json.dumps({"edges": system_edges}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            "manifest": manifest,
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "component_count": len(components),
            "edge_count": len(edges),
            "system_edge_count": len(system_edges),
            "bytes": sum(cast(int, item["bytes"]) for item in components),
            "system_edge_sha256": hashlib.sha256(system_canonical).hexdigest(),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_CLOSURE_INVALID") from error


def _node_topology_identity(topology: dict[str, object]) -> dict[str, object]:
    try:
        if set(topology) != {
            "schema_version",
            "kind",
            "install_root",
            "component_paths",
            "edges",
            "system_edges",
        }:
            raise ValueError
        component_paths = cast(list[str], topology["component_paths"])
        edges = cast(list[dict[str, str]], topology["edges"])
        system_edges = cast(list[dict[str, str]], topology["system_edges"])
        if (
            topology["schema_version"] != 1
            or topology["kind"] != "elmos.node26-homebrew-macho-topology"
            or topology["install_root"] != str(_EXPECTED_NODE_ROOT)
            or len(component_paths) != len(set(component_paths))
            or len(edges)
            != len(
                {
                    (item["loader"], item["load_path"], item["resolved_path"])
                    for item in edges
                }
            )
            or len(system_edges)
            != len(
                {(item["loader"], item["load_path"]) for item in system_edges}
            )
        ):
            raise ValueError
        component_set = set(component_paths)
        if str(_EXPECTED_NODE_EXECUTABLE) not in component_set:
            raise ValueError
        for value in component_paths:
            Path(value).relative_to(_EXPECTED_HOMEBREW_CELLAR)
        if any(
            item["loader"] not in component_set
            or item["resolved_path"] not in component_set
            or item["load_path"].startswith(("/usr/lib/", "/System/Library/"))
            for item in edges
        ):
            raise ValueError
        if any(
            item["loader"] not in component_set
            or not item["load_path"].startswith(
                ("/usr/lib/", "/System/Library/")
            )
            for item in system_edges
        ):
            raise ValueError
        canonical = json.dumps(
            topology, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {
            "topology": topology,
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "component_count": len(component_paths),
            "edge_count": len(edges),
            "system_edge_count": len(system_edges),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_INVALID") from error


def _verify_node_topology_identity(identity: dict[str, object]) -> None:
    try:
        topology = cast(dict[str, object], identity["topology"])
        recomputed = _node_topology_identity(topology)
    except (KeyError, TypeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_INVALID") from error
    for field in ("sha256", "component_count", "edge_count", "system_edge_count"):
        if recomputed[field] != identity.get(field):
            raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_INVALID")
    if (
        recomputed["sha256"] != _EXPECTED_NODE_TOPOLOGY_SHA256
        or recomputed["component_count"] != _EXPECTED_NODE_CLOSURE_COMPONENT_COUNT
        or recomputed["edge_count"] != _EXPECTED_NODE_CLOSURE_EDGE_COUNT
        or recomputed["system_edge_count"]
        != _EXPECTED_NODE_CLOSURE_SYSTEM_EDGE_COUNT
    ):
        raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_MISMATCH")


def _discover_node_topology() -> dict[str, object]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:javascript:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    queue = [_EXPECTED_NODE_EXECUTABLE]
    seen: set[Path] = set()
    edges: set[tuple[str, str, str]] = set()
    system_edges: set[tuple[str, str]] = set()
    while queue:
        loader = queue.pop(0)
        if loader in seen:
            continue
        loader.relative_to(_EXPECTED_HOMEBREW_CELLAR)
        seen.add(loader)
        for load_path in _node_otool_dependencies(loader):
            if load_path.startswith(("/usr/lib/", "/System/Library/")):
                system_edges.add((str(loader), load_path))
                continue
            resolved = _node_resolve_dependency(load_path, loader)
            edges.add((str(loader), load_path, str(resolved)))
            if resolved not in seen and resolved not in queue:
                queue.append(resolved)
    topology: dict[str, object] = {
        "schema_version": 1,
        "kind": "elmos.node26-homebrew-macho-topology",
        "install_root": str(_EXPECTED_NODE_ROOT),
        "component_paths": sorted(str(item) for item in seen),
        "edges": [
            {"loader": loader, "load_path": load_path, "resolved_path": resolved}
            for loader, load_path, resolved in sorted(edges)
        ],
        "system_edges": [
            {"loader": loader, "load_path": load_path}
            for loader, load_path in sorted(system_edges)
        ],
    }
    return _node_topology_identity(topology)


def _node_cached_topology() -> dict[str, object]:
    global _NODE_TOPOLOGY_CACHE

    if _NODE_TOPOLOGY_CACHE is None:
        identity = _discover_node_topology()
        _verify_node_topology_identity(identity)
        topology = cast(dict[str, object], identity["topology"])
        _NODE_TOPOLOGY_CACHE = cast(
            dict[str, object],
            json.loads(json.dumps(topology, sort_keys=True, separators=(",", ":"))),
        )
        return identity
    try:
        snapshot = cast(
            dict[str, object],
            json.loads(
                json.dumps(
                    _NODE_TOPOLOGY_CACHE,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
        )
    except (TypeError, ValueError) as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_INVALID") from error
    identity = _node_topology_identity(snapshot)
    _verify_node_topology_identity(identity)
    return identity


def _node_dependency_closure() -> dict[str, object]:
    """Content-bind every component using an exact cached Mach-O topology."""

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:javascript:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    topology_identity = _node_cached_topology()
    topology = cast(dict[str, object], topology_identity["topology"])
    component_paths = cast(list[str], topology["component_paths"])
    components = [
        _node_file_binding(
            Path(path),
            "EXACT_TOOLCHAIN_NODE_COMPONENT_UNSAFE",
        )
        for path in component_paths
    ]
    manifest: dict[str, object] = {
        "schema_version": 1,
        "kind": "elmos.node26-homebrew-macho-closure",
        "install_root": str(_EXPECTED_NODE_ROOT),
        "discovery": {
            "tool": str(_EXPECTED_NODE_OTOOL),
            "commands": ["-L", "-D", "-l"],
            "system_tool_content_soundness": "NOT_RUN",
        },
        "components": sorted(components, key=lambda item: str(item["resolved_path"])),
        "edges": cast(list[dict[str, str]], topology["edges"]),
        "system_edges": cast(list[dict[str, str]], topology["system_edges"]),
        "system_content_boundary": {
            "scope": "dyld-shared-cache-and-system-libraries",
            "status": "NOT_RUN",
        },
    }
    return _node_closure_identity(manifest)


def _verify_node_dependency_closure(identity: dict[str, object]) -> None:
    try:
        manifest = cast(dict[str, object], identity["manifest"])
        recomputed = _node_closure_identity(manifest)
        components = cast(list[dict[str, object]], manifest["components"])
        executable = next(item for item in components if item.get("resolved_path") == str(_EXPECTED_NODE_EXECUTABLE))
        libnode = next(item for item in components if item.get("resolved_path") == str(_EXPECTED_NODE_LIBNODE))
    except (KeyError, StopIteration, TypeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_CLOSURE_INVALID") from error
    if executable.get("sha256") != _EXPECTED_NODE_SHA256 or executable.get("bytes") != _EXPECTED_NODE_BYTES:
        raise RouteError("EXACT_TOOLCHAIN_NODE_EXECUTABLE_MISMATCH")
    if libnode.get("sha256") != _EXPECTED_NODE_LIBNODE_SHA256 or libnode.get("bytes") != _EXPECTED_NODE_LIBNODE_BYTES:
        raise RouteError("EXACT_TOOLCHAIN_NODE_LIBNODE_MISMATCH")
    for field in (
        "sha256",
        "component_count",
        "edge_count",
        "system_edge_count",
        "bytes",
        "system_edge_sha256",
    ):
        if recomputed[field] != identity.get(field):
            raise RouteError("EXACT_TOOLCHAIN_NODE_CLOSURE_IDENTITY_INVALID")
    expected = {
        "sha256": _EXPECTED_NODE_CLOSURE_SHA256,
        "component_count": _EXPECTED_NODE_CLOSURE_COMPONENT_COUNT,
        "edge_count": _EXPECTED_NODE_CLOSURE_EDGE_COUNT,
        "system_edge_count": _EXPECTED_NODE_CLOSURE_SYSTEM_EDGE_COUNT,
        "bytes": _EXPECTED_NODE_CLOSURE_BYTES,
        "system_edge_sha256": _EXPECTED_NODE_SYSTEM_EDGE_SHA256,
    }
    if any(recomputed[field] != value for field, value in expected.items()):
        raise RouteError("EXACT_TOOLCHAIN_NODE_CLOSURE_MISMATCH")


def _node_shim_identity() -> tuple[object, ...]:
    # The selected runtime is a fixed repository-qualified Homebrew asset, so
    # replay must not depend on whether an outer sandbox happens to expose the
    # Homebrew shim through its ambient PATH.
    declared = _EXPECTED_NODE_SHIM
    try:
        before = declared.lstat()
        target_before = declared.readlink()
        resolved = declared.resolve(strict=True)
        after = declared.lstat()
        target_after = declared.readlink()
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_SHIM_UNSAFE") from error
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_mtime_ns,
    )
    if (
        declared != _EXPECTED_NODE_SHIM
        or not stat.S_ISLNK(before.st_mode)
        or before.st_uid not in {0, os.getuid()}
        or before.st_nlink != 1
        or str(target_before) != _EXPECTED_NODE_SHIM_TARGET
        or target_before != target_after
        or resolved != _EXPECTED_NODE_EXECUTABLE
        or identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_mtime_ns,
        )
    ):
        raise RouteError("EXACT_TOOLCHAIN_NODE_SHIM_UNSAFE")
    return (str(declared), str(target_before), str(resolved), *identity)


def _node_runtime_identity() -> dict[str, object]:
    observed_version = _output([str(_EXPECTED_NODE_EXECUTABLE), "--version"])
    observed_identity = _output(
        [
            str(_EXPECTED_NODE_EXECUTABLE),
            "-p",
            "JSON.stringify({execPath:process.execPath,platform:process.platform,"
            "arch:process.arch,versions:Object.fromEntries(Object.entries(process.versions)"
            ".sort(([a],[b])=>a.localeCompare(b)))})",
        ]
    )
    try:
        identity = json.loads(observed_identity)
    except json.JSONDecodeError as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_IDENTITY_INVALID") from error
    observed_versions = json.dumps(identity.get("versions"), separators=(",", ":"), ensure_ascii=True)
    if (
        observed_version != "v26.0.0"
        or identity.get("execPath") != str(_EXPECTED_NODE_EXECUTABLE)
        or identity.get("platform") != "darwin"
        or identity.get("arch") != "arm64"
        or observed_versions != _EXPECTED_NODE_PROCESS_VERSIONS
        or hashlib.sha256(observed_versions.encode("ascii")).hexdigest() != _EXPECTED_NODE_PROCESS_VERSIONS_SHA256
    ):
        raise RouteError(
            "EXACT_TOOLCHAIN_MISMATCH:node-runtime:"
            "expected=Node26.0.0/darwin-arm64/"
            f"sha256={_EXPECTED_NODE_SHA256}:observed={observed_version}/"
            f"{identity.get('platform')}-{identity.get('arch')}"
        )
    return {
        "version": observed_version,
        "process": identity,
        "process_versions_sha256": _EXPECTED_NODE_PROCESS_VERSIONS_SHA256,
    }


def _javascript() -> ExactToolchain:
    """Select the exact Node.js runtime for the JavaScript language ID.

    JavaScript is intentionally independent of the TypeScript target: there
    is no ``tsc`` auxiliary and no TypeScript language identity.  This binds
    the launcher, the recursive non-system Mach-O closure, and the complete
    ``process.versions`` surface on the qualified host.  System libraries and
    compiler/runtime semantic soundness remain explicit ``NOT_RUN`` boundaries.
    """

    shim_before = _node_shim_identity()
    closure_before = _node_dependency_closure()
    _verify_node_dependency_closure(closure_before)
    _node_runtime_identity()
    closure_after = _node_dependency_closure()
    _verify_node_dependency_closure(closure_after)
    shim_after = _node_shim_identity()
    if closure_before != closure_after or shim_before != shim_after:
        raise RouteError("EXACT_TOOLCHAIN_NODE_CLOSURE_CHANGED_DURING_PROBE")
    return ExactToolchain(
        "javascript",
        "Node.js 26.0.0 / ES2022 / ESM",
        str(_EXPECTED_NODE_EXECUTABLE),
        profile=(
            "node-toolchain-closure-schema=v1",
            "platform=Darwin/arm64",
            "ecmascript=ES2022",
            "module=ESM",
            "syntax-check=node--check",
            "integer=IEEE-754-safe-integer-subset",
            "number=finite-binary64",
            f"process-versions-sha256={_EXPECTED_NODE_PROCESS_VERSIONS_SHA256}",
            f"node-install-root={_EXPECTED_NODE_ROOT}",
            f"node-closure-sha256={closure_after['sha256']}",
            f"node-closure-component-count={closure_after['component_count']}",
            f"node-closure-edge-count={closure_after['edge_count']}",
            f"node-closure-system-edge-count={closure_after['system_edge_count']}",
            f"node-closure-bytes={closure_after['bytes']}",
            f"node-system-edge-sha256={closure_after['system_edge_sha256']}",
            f"libnode-sha256={_EXPECTED_NODE_LIBNODE_SHA256}",
            f"libnode-bytes={_EXPECTED_NODE_LIBNODE_BYTES}",
            "otool-system-tool-content-soundness=NOT_RUN",
            "dyld-system-library-content-soundness=NOT_RUN",
            "compiler-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=_EXPECTED_NODE_SHA256,
    )


_EXPECTED_USER_LOCAL = Path("/Users/stephen/.local")

_EXPECTED_GO_ROOT = _EXPECTED_USER_LOCAL / "share" / "elmos" / "toolchains" / "go" / "1.25.0"
_EXPECTED_GO_PUBLIC = _EXPECTED_USER_LOCAL / "bin" / "go"
_EXPECTED_GO_EXECUTABLE = _EXPECTED_GO_ROOT / "bin" / "go"
_EXPECTED_GO_PUBLIC_TARGET = str(_EXPECTED_GO_EXECUTABLE)
_EXPECTED_GO_EXECUTABLE_SHA256 = "c812de5f1e8307431c5bce8ebc4887c180827abc5834a72cd640a8a14200a93b"
_EXPECTED_GO_EXECUTABLE_BYTES = 14_117_888
_EXPECTED_GO_TREE_SHA256 = "877afe68674e435643c86dcbb546ec9d441f636962068ac7b63d3ced854c2704"
_EXPECTED_GO_TREE_RECORD_COUNT = 16_087
_EXPECTED_GO_TREE_FILE_COUNT = 14_496
_EXPECTED_GO_TREE_DIRECTORY_COUNT = 1_591
_EXPECTED_GO_TREE_BYTES = 202_722_007
_EXPECTED_GO_VERSION = "go version go1.25.0 darwin/arm64"

_EXPECTED_RUST_ROOT = _EXPECTED_USER_LOCAL / "share" / "elmos" / "toolchains" / "rust" / "1.89.0"
_EXPECTED_RUST_WRAPPER_ROOT = _EXPECTED_RUST_ROOT / "bin"
_EXPECTED_RUST_RUSTUP_HOME = _EXPECTED_RUST_ROOT / "rustup"
_EXPECTED_RUST_CARGO_HOME = _EXPECTED_RUST_ROOT / "cargo"
_EXPECTED_RUST_SYSROOT = _EXPECTED_RUST_RUSTUP_HOME / "toolchains" / "1.89.0-aarch64-apple-darwin"
_EXPECTED_RUST_EXECUTABLE = _EXPECTED_RUST_SYSROOT / "bin" / "rustc"
_EXPECTED_RUST_CARGO = _EXPECTED_RUST_SYSROOT / "bin" / "cargo"
_EXPECTED_RUST_SETTINGS = _EXPECTED_RUST_RUSTUP_HOME / "settings.toml"
_EXPECTED_RUST_RUSTUP = _EXPECTED_RUST_CARGO_HOME / "bin" / "rustup"
_EXPECTED_RUST_PUBLIC_RUSTC = _EXPECTED_USER_LOCAL / "bin" / "rustc"
_EXPECTED_RUST_PUBLIC_CARGO = _EXPECTED_USER_LOCAL / "bin" / "cargo"
_EXPECTED_RUST_PUBLIC_RUSTUP = _EXPECTED_USER_LOCAL / "bin" / "rustup"
_EXPECTED_RUST_PUBLIC_TARGETS = {
    _EXPECTED_RUST_PUBLIC_RUSTC: str(_EXPECTED_RUST_WRAPPER_ROOT / "rustc"),
    _EXPECTED_RUST_PUBLIC_CARGO: str(_EXPECTED_RUST_WRAPPER_ROOT / "cargo"),
    _EXPECTED_RUST_PUBLIC_RUSTUP: str(_EXPECTED_RUST_WRAPPER_ROOT / "rustup"),
}
_EXPECTED_RUST_WRAPPER_TREE_SHA256 = "f74538687384c432f46553dbee0ecddf732c7bcae239aadcf94ad090056ab8c8"
_EXPECTED_RUST_WRAPPER_TREE_RECORD_COUNT = 3
_EXPECTED_RUST_WRAPPER_TREE_FILE_COUNT = 3
_EXPECTED_RUST_WRAPPER_TREE_DIRECTORY_COUNT = 0
_EXPECTED_RUST_WRAPPER_TREE_BYTES = 790
_EXPECTED_RUST_SYSROOT_TREE_SHA256 = "cb6193d1c822b49b839033b69a850b049ecf525feac88bfe0d08829f0aea268b"
_EXPECTED_RUST_SYSROOT_TREE_RECORD_COUNT = 157
_EXPECTED_RUST_SYSROOT_TREE_FILE_COUNT = 135
_EXPECTED_RUST_SYSROOT_TREE_DIRECTORY_COUNT = 22
_EXPECTED_RUST_SYSROOT_TREE_BYTES = 531_383_469
_EXPECTED_RUST_EXECUTABLE_SHA256 = "af4a9eb303553510e9d74220636dc4b21f8574ddeab73741bf6b892adc49c21c"
_EXPECTED_RUST_EXECUTABLE_BYTES = 414_776
_EXPECTED_RUST_CARGO_SHA256 = "798a97c06e6fc3a63f1b7e3141f87e515e6bc8da1527bc32e19ba27d86bb89c5"
_EXPECTED_RUST_CARGO_BYTES = 28_655_992
_EXPECTED_RUST_SETTINGS_SHA256 = "df6dfe670d4ac04d7d34712faaa4e51abd9636f7b5e9a2b338f2efec1c08eb7c"
_EXPECTED_RUST_SETTINGS_BYTES = 143
_EXPECTED_RUST_RUSTUP_SHA256 = "aeb4105778ca1bd3c6b0e75768f581c656633cd51368fa61289b6a71696ac7e1"
_EXPECTED_RUST_RUSTUP_BYTES = 11_053_296
_EXPECTED_RUST_VERSION = "rustc 1.89.0 (29483883e 2025-08-04)"
_EXPECTED_RUST_CARGO_VERSION = "cargo 1.89.0 (c24e10642 2025-06-23)"


def _go_tree_identity() -> dict[str, object]:
    identity = _qualified_tree_manifest(
        _EXPECTED_GO_ROOT,
        _EXPECTED_USER_LOCAL,
        "EXACT_TOOLCHAIN_GO_TREE_UNSAFE",
    )
    _verify_qualified_tree_manifest(
        identity,
        expected_root=_EXPECTED_GO_ROOT,
        expected_sha256=_EXPECTED_GO_TREE_SHA256,
        expected_record_count=_EXPECTED_GO_TREE_RECORD_COUNT,
        expected_file_count=_EXPECTED_GO_TREE_FILE_COUNT,
        expected_directory_count=_EXPECTED_GO_TREE_DIRECTORY_COUNT,
        expected_bytes=_EXPECTED_GO_TREE_BYTES,
        failure="EXACT_TOOLCHAIN_GO_TREE_MISMATCH",
    )
    return identity


def _go() -> ExactToolchain:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:go:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    selector_before = _qualified_fixed_symlink(
        _EXPECTED_GO_PUBLIC,
        anchor=_EXPECTED_USER_LOCAL,
        expected_target=_EXPECTED_GO_PUBLIC_TARGET,
        expected_resolved=_EXPECTED_GO_EXECUTABLE,
        failure="EXACT_TOOLCHAIN_GO_SELECTOR_UNSAFE",
    )
    tree_before = _go_tree_identity()
    executable_before = _qualified_file_record(
        _EXPECTED_GO_EXECUTABLE,
        _EXPECTED_GO_ROOT,
        "EXACT_TOOLCHAIN_GO_EXECUTABLE_UNSAFE",
    )
    observed = _output([str(_EXPECTED_GO_EXECUTABLE), "version"])
    executable_after = _qualified_file_record(
        _EXPECTED_GO_EXECUTABLE,
        _EXPECTED_GO_ROOT,
        "EXACT_TOOLCHAIN_GO_EXECUTABLE_UNSAFE",
    )
    tree_after = _go_tree_identity()
    selector_after = _qualified_fixed_symlink(
        _EXPECTED_GO_PUBLIC,
        anchor=_EXPECTED_USER_LOCAL,
        expected_target=_EXPECTED_GO_PUBLIC_TARGET,
        expected_resolved=_EXPECTED_GO_EXECUTABLE,
        failure="EXACT_TOOLCHAIN_GO_SELECTOR_UNSAFE",
    )
    if (
        observed != _EXPECTED_GO_VERSION
        or executable_before != executable_after
        or executable_after.get("sha256") != _EXPECTED_GO_EXECUTABLE_SHA256
        or executable_after.get("bytes") != _EXPECTED_GO_EXECUTABLE_BYTES
        or tree_before != tree_after
        or selector_before != selector_after
    ):
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:go:expected={_EXPECTED_GO_VERSION}:observed={observed}")
    return ExactToolchain(
        "go",
        "1.25.0",
        str(_EXPECTED_GO_EXECUTABLE),
        profile=(
            "go-toolchain-closure-schema=v1",
            "platform=Darwin/arm64",
            f"go-root={_EXPECTED_GO_ROOT}",
            f"go-tree-sha256={tree_after['sha256']}",
            f"go-tree-record-count={tree_after['record_count']}",
            f"go-tree-file-count={tree_after['file_count']}",
            f"go-tree-directory-count={tree_after['directory_count']}",
            f"go-tree-bytes={tree_after['bytes']}",
            "go-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=_EXPECTED_GO_EXECUTABLE_SHA256,
    )


def _rust_tree_identities() -> tuple[dict[str, object], dict[str, object]]:
    wrappers = _qualified_tree_manifest(
        _EXPECTED_RUST_WRAPPER_ROOT,
        _EXPECTED_USER_LOCAL,
        "EXACT_TOOLCHAIN_RUST_WRAPPER_TREE_UNSAFE",
    )
    _verify_qualified_tree_manifest(
        wrappers,
        expected_root=_EXPECTED_RUST_WRAPPER_ROOT,
        expected_sha256=_EXPECTED_RUST_WRAPPER_TREE_SHA256,
        expected_record_count=_EXPECTED_RUST_WRAPPER_TREE_RECORD_COUNT,
        expected_file_count=_EXPECTED_RUST_WRAPPER_TREE_FILE_COUNT,
        expected_directory_count=_EXPECTED_RUST_WRAPPER_TREE_DIRECTORY_COUNT,
        expected_bytes=_EXPECTED_RUST_WRAPPER_TREE_BYTES,
        failure="EXACT_TOOLCHAIN_RUST_WRAPPER_TREE_MISMATCH",
    )
    sysroot = _qualified_tree_manifest(
        _EXPECTED_RUST_SYSROOT,
        _EXPECTED_USER_LOCAL,
        "EXACT_TOOLCHAIN_RUST_SYSROOT_TREE_UNSAFE",
    )
    _verify_qualified_tree_manifest(
        sysroot,
        expected_root=_EXPECTED_RUST_SYSROOT,
        expected_sha256=_EXPECTED_RUST_SYSROOT_TREE_SHA256,
        expected_record_count=_EXPECTED_RUST_SYSROOT_TREE_RECORD_COUNT,
        expected_file_count=_EXPECTED_RUST_SYSROOT_TREE_FILE_COUNT,
        expected_directory_count=_EXPECTED_RUST_SYSROOT_TREE_DIRECTORY_COUNT,
        expected_bytes=_EXPECTED_RUST_SYSROOT_TREE_BYTES,
        failure="EXACT_TOOLCHAIN_RUST_SYSROOT_TREE_MISMATCH",
    )
    return wrappers, sysroot


def _rust_auxiliary_bindings() -> tuple[dict[str, str | int], ...]:
    bindings = (
        _qualified_file_record(
            _EXPECTED_RUST_EXECUTABLE,
            _EXPECTED_RUST_SYSROOT,
            "EXACT_TOOLCHAIN_RUSTC_UNSAFE",
        ),
        _qualified_file_record(
            _EXPECTED_RUST_CARGO,
            _EXPECTED_RUST_SYSROOT,
            "EXACT_TOOLCHAIN_CARGO_UNSAFE",
        ),
        _qualified_file_record(
            _EXPECTED_RUST_SETTINGS,
            _EXPECTED_RUST_ROOT,
            "EXACT_TOOLCHAIN_RUST_SETTINGS_UNSAFE",
        ),
        _qualified_file_record(
            _EXPECTED_RUST_RUSTUP,
            _EXPECTED_RUST_ROOT,
            "EXACT_TOOLCHAIN_RUSTUP_UNSAFE",
        ),
    )
    expected = (
        (_EXPECTED_RUST_EXECUTABLE_SHA256, _EXPECTED_RUST_EXECUTABLE_BYTES),
        (_EXPECTED_RUST_CARGO_SHA256, _EXPECTED_RUST_CARGO_BYTES),
        (_EXPECTED_RUST_SETTINGS_SHA256, _EXPECTED_RUST_SETTINGS_BYTES),
        (_EXPECTED_RUST_RUSTUP_SHA256, _EXPECTED_RUST_RUSTUP_BYTES),
    )
    if any(
        binding.get("sha256") != digest or binding.get("bytes") != byte_count
        for binding, (digest, byte_count) in zip(bindings, expected, strict=True)
    ):
        raise RouteError("EXACT_TOOLCHAIN_RUST_AUXILIARY_MISMATCH")
    return bindings


def _rust() -> ExactToolchain:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:rust:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    selectors_before = tuple(
        _qualified_fixed_symlink(
            declared,
            anchor=_EXPECTED_USER_LOCAL,
            expected_target=target,
            expected_resolved=Path(target),
            failure="EXACT_TOOLCHAIN_RUST_SELECTOR_UNSAFE",
        )
        for declared, target in _EXPECTED_RUST_PUBLIC_TARGETS.items()
    )
    trees_before = _rust_tree_identities()
    auxiliary_before = _rust_auxiliary_bindings()
    observed = _output([str(_EXPECTED_RUST_EXECUTABLE), "--version"])
    cargo_observed = _output([str(_EXPECTED_RUST_CARGO), "--version"])
    auxiliary_after = _rust_auxiliary_bindings()
    trees_after = _rust_tree_identities()
    selectors_after = tuple(
        _qualified_fixed_symlink(
            declared,
            anchor=_EXPECTED_USER_LOCAL,
            expected_target=target,
            expected_resolved=Path(target),
            failure="EXACT_TOOLCHAIN_RUST_SELECTOR_UNSAFE",
        )
        for declared, target in _EXPECTED_RUST_PUBLIC_TARGETS.items()
    )
    if (
        observed != _EXPECTED_RUST_VERSION
        or cargo_observed != _EXPECTED_RUST_CARGO_VERSION
        or auxiliary_before != auxiliary_after
        or trees_before != trees_after
        or selectors_before != selectors_after
    ):
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:rust:expected={_EXPECTED_RUST_VERSION}:observed={observed}")
    wrappers, sysroot = trees_after
    return ExactToolchain(
        "rust",
        "1.89.0",
        str(_EXPECTED_RUST_EXECUTABLE),
        str(_EXPECTED_RUST_CARGO),
        profile=(
            "rust-toolchain-closure-schema=v1",
            "platform=Darwin/arm64",
            f"rustup-home={_EXPECTED_RUST_RUSTUP_HOME}",
            f"cargo-home={_EXPECTED_RUST_CARGO_HOME}",
            f"rust-sysroot={_EXPECTED_RUST_SYSROOT}",
            f"rust-wrapper-tree-sha256={wrappers['sha256']}",
            f"rust-wrapper-tree-record-count={wrappers['record_count']}",
            f"rust-wrapper-tree-bytes={wrappers['bytes']}",
            f"rust-sysroot-tree-sha256={sysroot['sha256']}",
            f"rust-sysroot-tree-record-count={sysroot['record_count']}",
            f"rust-sysroot-tree-file-count={sysroot['file_count']}",
            f"rust-sysroot-tree-bytes={sysroot['bytes']}",
            f"rustup-sha256={_EXPECTED_RUST_RUSTUP_SHA256}",
            "rust-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=_EXPECTED_RUST_EXECUTABLE_SHA256,
        auxiliary_sha256=_EXPECTED_RUST_CARGO_SHA256,
    )


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


# ---------------------------------------------------------------------------
# PHP
#
# The install is pinned the same way Go's is: a fixed root under the user-local
# anchor, a whole-tree manifest of that root, an executable file record, and a
# before/after sandwich around the one subprocess the probe runs. PHP adds one
# obligation the compiled targets do not have, because two PHP builds that
# report the same `php --version` can still disagree semantically:
#
#   * `PHP_INT_SIZE` decides whether `int` is the canonical 64-bit signed
#     integer at all. A 32-bit build would silently make every emitted `int`
#     a 32-bit value and turn R1's overflow-to-float check into a check at the
#     wrong boundary. The probe refuses anything but 8.
#   * The loaded extension set is part of the language. `php -n` is not enough:
#     an extension can be compiled in, and a compiled-in `bcmath` or `gmp` does
#     not change arithmetic but a compiled-in userland override could. The
#     manifest of the extension directory is folded into the tree digest and
#     the runtime-reported list is folded into the profile.
#   * A thread-safe (ZTS) build has a different `php.ini` search order and a
#     different binary; it is recorded rather than refused, so a route's
#     evidence names which one produced it.
#
# The four `_EXPECTED_PHP_*` digest constants below are machine-specific, the
# same way `_EXPECTED_GO_TREE_SHA256` and `_EXPECTED_SWIFTC_SHA256` are. Run
# `tools/pin_php_toolchain.py` on the pinning host and paste its output here;
# the script emits exactly this block. Until they are pinned the probe fails
# closed with EXACT_TOOLCHAIN_PHP_NOT_PINNED rather than accepting whatever
# `php` happens to be on PATH.
_PHP_VERSION_VARIABLE = "ELMOS_PHP_VERSION"
_EXPECTED_PHP_VERSION = 'PHP 8.5.9 (cli) (built: Jul 28 2026 13:06:52) (NTS)'
_EXPECTED_PHP_ROOT = Path('/opt/homebrew/Cellar/php/8.5.9')
_EXPECTED_PHP_ANCHOR = Path('/opt/homebrew/Cellar/php')
_EXPECTED_PHP_EXECUTABLE = _EXPECTED_PHP_ROOT / "bin" / "php"
_EXPECTED_PHP_EXECUTABLE_SHA256 = '6e52a2c84ff356bfc670809b7b5923a05aa64b3c8bcdb6c4a9a6b257c3435218'
_EXPECTED_PHP_EXECUTABLE_BYTES = 23795728
_EXPECTED_PHP_TREE_SHA256 = '4d1c6db642797e84f37e736da203423f013807abf5a334f7ba59ae99e4badefb'
_EXPECTED_PHP_TREE_RECORD_COUNT = 643
_EXPECTED_PHP_TREE_FILE_COUNT = 532
_EXPECTED_PHP_TREE_DIRECTORY_COUNT = 109
_EXPECTED_PHP_TREE_BYTES = 129955913
#: Symlinks whose target resolves *inside* the install root. Pinned as
#: name -> raw link text, exactly as `_EXPECTED_PYTHON_SYMLINKS` is: the link is
#: part of the tree's identity, and a link that starts pointing somewhere else
#: is drift even when every file's content is unchanged.
_EXPECTED_PHP_TREE_SYMLINKS: dict[str, str] = {
    'bin/phar': 'phar.phar',
}
#: Symlinks whose target resolves *outside* the install root. Their content is
#: NOT bound by this pin -- that is the whole point of recording them separately
#: rather than folding them in and implying otherwise. A stock Homebrew PHP has
#: `pecl` and `pear` pointing at `/opt/homebrew/lib/php/...`, a deliberately
#: mutable location holding user-installed PECL state. Those two are installer
#: scripts the engine never invokes; what it does invoke, `bin/php`, and
#: everything that lives under the root, is bound. Pinning the exact set is what
#: keeps that true: if a future formula adds an escaping link to something
#: load-bearing, the set changes and the probe fails.
_EXPECTED_PHP_TREE_UNBOUND_SYMLINKS: dict[str, str] = {
    'pecl': '/opt/homebrew/lib/php/pecl',
}
#: sha256 over the canonical JSON the identity script prints. Pinning the digest
#: rather than the document keeps this block readable while still failing closed
#: on any drift in the extension set, the int width or the float model.
_EXPECTED_PHP_RUNTIME_IDENTITY_SHA256 = '4d932570ac531f0886895fe7be8440ba5764c7db61446c4f3f1d90a12f002f5e'
#: How this build provides `ext/tokenizer`, which the PHP frontend is entirely
#: built on. Either the string "builtin" -- the extension is compiled into the
#: interpreter and is present with no php.ini at all -- or a path relative to
#: the install root naming the shared object to load.
#:
#: This has to be pinned rather than discovered because the engine runs PHP with
#: `-n`, which drops every php.ini. On a build that ships tokenizer as a shared
#: module activated through conf.d (Debian and Ubuntu do), `-n` removes
#: `token_get_all` and the analyzer cannot run at all. Loading it explicitly
#: restores it *without* restoring the rest of the machine's configuration,
#: and requiring the object to live inside the pinned root is what keeps the
#: thing being dlopen'd bound by the tree digest.
_EXPECTED_PHP_TOKENIZER = 'builtin'

#: Printed as one canonical JSON object on stdout. `-n` suppresses every php.ini
#: so the answer describes the *build*, not the machine's configuration; the
#: configuration that will actually be used at emit time is captured separately
#: through the tree manifest, which covers the ini files under the root.
_PHP_RUNTIME_IDENTITY_SCRIPT = (
    "$d=["
    "'php_version'=>PHP_VERSION,"
    "'php_version_id'=>PHP_VERSION_ID,"
    "'zts'=>PHP_ZTS,"
    "'debug'=>PHP_DEBUG,"
    "'int_size'=>PHP_INT_SIZE,"
    "'int_max'=>(string)PHP_INT_MAX,"
    "'int_min'=>(string)PHP_INT_MIN,"
    "'float_dig'=>PHP_FLOAT_DIG,"
    "'float_epsilon'=>bin2hex(pack('E',PHP_FLOAT_EPSILON)),"
    "'float_max'=>bin2hex(pack('E',PHP_FLOAT_MAX)),"
    "'float_min'=>bin2hex(pack('E',PHP_FLOAT_MIN)),"
    "'os_family'=>PHP_OS_FAMILY,"
    "'extension_dir'=>ini_get('extension_dir'),"
    "'precision'=>ini_get('precision'),"
    "'serialize_precision'=>ini_get('serialize_precision'),"
    "'zend_assertions'=>ini_get('zend.assertions'),"
    "'extensions'=>get_loaded_extensions(),"
    "];"
    "sort($d['extensions']);"
    "echo json_encode($d,JSON_UNESCAPED_SLASHES|JSON_PRESERVE_ZERO_FRACTION);"
)


def php_tree_identity(root: Path, anchor: Path, failure: str) -> dict[str, object]:
    """Content identity of one PHP install tree, symlinks included.

    Deliberately *not* `_qualified_tree_manifest`, which requires a symlink-free
    tree. That contract fits Go and Rust, whose installs are extracted tarballs
    of plain files, and it fits nothing that a package manager laid down: a
    stock Homebrew PHP ships `bin/phar -> bin/phar.phar` and
    `pecl -> /opt/homebrew/lib/php/pecl`, so the symlink-free rule refuses every
    Homebrew PHP that will ever exist. A rule no real install can satisfy is not
    a strict rule, it is an unusable one.

    The Python probe already resolved this the right way and this follows it:
    symlinks are *recorded* rather than refused, so the link itself becomes part
    of the pinned identity and repointing one is drift even when no file's
    content changed.

    Where this goes further than the Python probe is escaping links. Python
    refuses any link resolving outside its root; PHP cannot, because `pecl` and
    `pear` point into Homebrew's shared, mutable `lib/php`. Those are recorded
    in a separate `unbound_symlinks` map and named as unbound in the toolchain
    profile, because saying "this pin does not cover these two names" is honest
    and folding them in silently would not be. One thing is still refused
    outright: an escaping link to a loadable object. Anything the interpreter
    could `dlopen` has to be inside the tree the pin actually binds.

    Exported without an underscore because `tools/pin_php_toolchain.py` has to
    compute exactly this, and a pin generator that reimplements the rule it is
    generating a pin for is a rule with two definitions.
    """
    _qualified_directory_chain(root, anchor, failure)
    try:
        root_metadata = root.lstat()
    except OSError as error:
        raise RouteError(failure) from error
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) & 0o022
    ):
        raise RouteError(failure)

    def discover() -> list[Path]:
        try:
            return sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        except OSError as error:
            raise RouteError(failure) from error

    paths = discover()
    records: list[dict[str, object]] = []
    symlinks: dict[str, str] = {}
    unbound: dict[str, str] = {}
    file_count = 0
    directory_count = 0
    total_bytes = 0
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            metadata = path.lstat()
        except OSError as error:
            raise RouteError(failure) from error
        # Homebrew lays its Cellar down 0755/0644 owned by the installing user,
        # so the fixed 0555/0444 the Python probe asserts is not applicable. The
        # property that matters is unchanged: nobody but the owner can write it.
        #
        # The mode is checked for files and directories only. A symlink's own
        # mode is not a permission on POSIX -- the target's mode governs access,
        # and replacing a link needs write on its *directory*, which the parent
        # entry already covers. The value is also not portable: macOS reports
        # 0755 for a link and Linux reports 0777, so testing it here would make
        # the rule accept or reject the same tree depending on the host.
        if metadata.st_uid != os.getuid():
            raise RouteError(failure)
        if not stat.S_ISLNK(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) & 0o022:
            raise RouteError(failure)
        if stat.S_ISLNK(metadata.st_mode):
            try:
                target = os.readlink(path)
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise RouteError(failure) from error
            if resolved.is_relative_to(root):
                symlinks[relative] = target
                records.append({"path": relative, "kind": "symlink", "target": target})
            else:
                if resolved.suffix in {".so", ".dylib", ".bundle"}:
                    raise RouteError(f"{failure}:ESCAPING_LOADABLE_OBJECT:{relative}")
                unbound[relative] = target
                records.append({"path": relative, "kind": "unbound-symlink", "target": target})
            continue
        if stat.S_ISDIR(metadata.st_mode):
            directory_count += 1
            records.append({"path": relative, "kind": "directory"})
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise RouteError(failure)
        record = _qualified_file_record(path, root, failure)
        file_count += 1
        total_bytes += cast(int, record["bytes"])
        records.append(
            {
                "path": relative,
                "kind": "file",
                "mode": record["mode"],
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            }
        )
    if [item.relative_to(root).as_posix() for item in discover()] != [
        item.relative_to(root).as_posix() for item in paths
    ]:
        raise RouteError(f"{failure}:TREE_CHANGED")
    digest = hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "root": str(root),
        "sha256": digest,
        "record_count": len(records),
        "file_count": file_count,
        "directory_count": directory_count,
        "bytes": total_bytes,
        "symlinks": symlinks,
        "unbound_symlinks": unbound,
    }


def _php_tree_identity() -> dict[str, object]:
    identity = php_tree_identity(
        _EXPECTED_PHP_ROOT,
        _EXPECTED_PHP_ANCHOR,
        "EXACT_TOOLCHAIN_PHP_TREE_UNSAFE",
    )
    expected = {
        "root": str(_EXPECTED_PHP_ROOT),
        "sha256": _EXPECTED_PHP_TREE_SHA256,
        "record_count": _EXPECTED_PHP_TREE_RECORD_COUNT,
        "file_count": _EXPECTED_PHP_TREE_FILE_COUNT,
        "directory_count": _EXPECTED_PHP_TREE_DIRECTORY_COUNT,
        "bytes": _EXPECTED_PHP_TREE_BYTES,
        "symlinks": _EXPECTED_PHP_TREE_SYMLINKS,
        "unbound_symlinks": _EXPECTED_PHP_TREE_UNBOUND_SYMLINKS,
    }
    if identity != expected:
        raise RouteError("EXACT_TOOLCHAIN_PHP_TREE_MISMATCH")
    return identity


def _php_runtime_identity() -> dict[str, object]:
    raw = _output([str(_EXPECTED_PHP_EXECUTABLE), "-n", "-r", _PHP_RUNTIME_IDENTITY_SCRIPT])
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RouteError("EXACT_TOOLCHAIN_PHP_RUNTIME_IDENTITY_INVALID") from error
    if type(document) is not dict:
        raise RouteError("EXACT_TOOLCHAIN_PHP_RUNTIME_IDENTITY_INVALID")
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    # These four are checked by value as well as by digest. The digest alone
    # would already fail on a mismatch, but it would fail with "something
    # changed"; naming the semantic preconditions makes the failure legible and
    # keeps them true even if the digest is ever re-pinned carelessly.
    if document.get("int_size") != 8:
        raise RouteError(f"EXACT_TOOLCHAIN_PHP_INT_WIDTH_UNSUPPORTED:{document.get('int_size')}")
    if document.get("int_max") != "9223372036854775807" or document.get("int_min") != "-9223372036854775808":
        raise RouteError("EXACT_TOOLCHAIN_PHP_INT_RANGE_UNSUPPORTED")
    if document.get("float_dig") != 15:
        raise RouteError("EXACT_TOOLCHAIN_PHP_FLOAT_MODEL_UNSUPPORTED")
    extensions = document.get("extensions")
    if type(extensions) is not list:
        raise RouteError("EXACT_TOOLCHAIN_PHP_RUNTIME_IDENTITY_INVALID")
    # Recorded under `-n`, so this is the set the build carries with no php.ini
    # at all -- which is also the set that decides whether `php-tokenizer` has
    # to name a shared object.
    if ("tokenizer" in extensions) != (_EXPECTED_PHP_TOKENIZER == "builtin"):
        raise RouteError(
            "EXACT_TOOLCHAIN_PHP_TOKENIZER_BINDING_MISMATCH:"
            f"builtin={'tokenizer' in extensions}:pinned={_EXPECTED_PHP_TOKENIZER}"
        )
    if digest != _EXPECTED_PHP_RUNTIME_IDENTITY_SHA256:
        raise RouteError(
            f"EXACT_TOOLCHAIN_PHP_RUNTIME_IDENTITY_MISMATCH:"
            f"expected={_EXPECTED_PHP_RUNTIME_IDENTITY_SHA256}:observed={digest}"
        )
    return {"digest": digest, "document": document}


def php_command(toolchain: ExactToolchain, *arguments: str) -> list[str]:
    """One PHP invocation with this machine's ambient configuration removed.

    `-n` drops every php.ini, so the interpreter behaves as the pinned build
    rather than as this host has configured it, and `sanitized_subprocess_env`
    has already dropped PHPRC and PHP_INI_SCAN_DIR. The three `-d` overrides pin
    the settings that can change an observed *value* rather than only a
    diagnostic: `precision` and `serialize_precision` govern float-to-string,
    and OPcache is disabled so a stale cached compilation can never be executed
    in place of the file just written.

    `-n` has one consequence that has to be undone deliberately. A build that
    ships `ext/tokenizer` as a shared module loses it along with the ini, and
    the PHP frontend is nothing without `token_get_all`. The extension is
    therefore re-added by absolute path from inside the pinned install root --
    never by bare name, which would search an extension_dir the pin does not
    bind.

    Single definition on purpose: the analyzer runner, the behaviour harness and
    the assembly build check must not be able to drift into configuring the
    interpreter three different ways.
    """
    command = [
        toolchain.executable,
        "-n",
        "-d",
        "error_reporting=E_ALL",
        "-d",
        "precision=17",
        "-d",
        "serialize_precision=-1",
        "-d",
        "opcache.enable_cli=0",
    ]
    prefix = "php-tokenizer="
    tokenizer = next(
        (entry[len(prefix):] for entry in toolchain.profile if entry.startswith(prefix)),
        None,
    )
    if tokenizer is None:
        raise RouteError("EXACT_TOOLCHAIN_PHP_TOKENIZER_BINDING_MISSING")
    if tokenizer != "builtin":
        # Absolute, and resolved from the install root rather than from an
        # extension_dir, so what gets dlopen'd is the object the tree digest
        # covers and not whatever happens to sit on the search path.
        root = Path(toolchain.executable).parent.parent
        command.extend(("-d", f"extension={root / tokenizer}"))
    return [*command, *arguments]


def _php_tokenizer_binding(root: Path) -> str:
    """Resolve, and validate, how this build provides ext/tokenizer."""
    if _EXPECTED_PHP_TOKENIZER == "builtin":
        return "builtin"
    if not _EXPECTED_PHP_TOKENIZER:
        raise RouteError("EXACT_TOOLCHAIN_PHP_NOT_PINNED:_EXPECTED_PHP_TOKENIZER")
    relative = PurePosixPath(_EXPECTED_PHP_TOKENIZER)
    if relative.is_absolute() or ".." in relative.parts:
        raise RouteError(f"EXACT_TOOLCHAIN_PHP_TOKENIZER_UNBINDABLE:{_EXPECTED_PHP_TOKENIZER}")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        # Loading a shared object the tree manifest does not cover would put the
        # frontend's own parser outside the pin, which is the one component that
        # must not be.
        raise RouteError(f"EXACT_TOOLCHAIN_PHP_TOKENIZER_UNBINDABLE:{_EXPECTED_PHP_TOKENIZER}")
    return _EXPECTED_PHP_TOKENIZER


def _php() -> ExactToolchain:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:php:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    if not (
        _EXPECTED_PHP_EXECUTABLE_SHA256
        and _EXPECTED_PHP_TREE_SHA256
        and _EXPECTED_PHP_RUNTIME_IDENTITY_SHA256
    ):
        # An unpinned digest must never degrade to "trust whatever is there".
        raise RouteError("EXACT_TOOLCHAIN_PHP_NOT_PINNED:run tools/pin_php_toolchain.py on the pinning host")
    expected_version = _pinned(_PHP_VERSION_VARIABLE, "php", _EXPECTED_PHP_VERSION)
    tokenizer = _php_tokenizer_binding(_EXPECTED_PHP_ROOT)
    tree_before = _php_tree_identity()
    executable_before = _qualified_file_record(
        _EXPECTED_PHP_EXECUTABLE,
        _EXPECTED_PHP_ROOT,
        "EXACT_TOOLCHAIN_PHP_EXECUTABLE_UNSAFE",
    )
    version_lines = _output([str(_EXPECTED_PHP_EXECUTABLE), "-n", "--version"]).splitlines()
    observed = version_lines[0].strip() if version_lines else ""
    runtime = _php_runtime_identity()
    executable_after = _qualified_file_record(
        _EXPECTED_PHP_EXECUTABLE,
        _EXPECTED_PHP_ROOT,
        "EXACT_TOOLCHAIN_PHP_EXECUTABLE_UNSAFE",
    )
    tree_after = _php_tree_identity()
    if (
        observed != expected_version
        or executable_before != executable_after
        or executable_after.get("sha256") != _EXPECTED_PHP_EXECUTABLE_SHA256
        or executable_after.get("bytes") != _EXPECTED_PHP_EXECUTABLE_BYTES
        or tree_before != tree_after
    ):
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:php:expected={expected_version}:observed={observed}")
    document = runtime["document"]
    assert type(document) is dict
    return ExactToolchain(
        "php",
        observed,
        str(_EXPECTED_PHP_EXECUTABLE),
        profile=(
            "php-toolchain-closure-schema=v1",
            "platform=Darwin/arm64",
            f"php-root={_EXPECTED_PHP_ROOT}",
            f"php-tree-sha256={tree_after['sha256']}",
            f"php-tree-record-count={tree_after['record_count']}",
            f"php-tree-file-count={tree_after['file_count']}",
            f"php-tree-directory-count={tree_after['directory_count']}",
            f"php-tree-bytes={tree_after['bytes']}",
            f"php-tree-symlink-count={len(_EXPECTED_PHP_TREE_SYMLINKS)}",
            f"php-tree-unbound-symlink-count={len(_EXPECTED_PHP_TREE_UNBOUND_SYMLINKS)}",
            *(
                f"php-tree-unbound-symlink={name}->{target}"
                for name, target in sorted(_EXPECTED_PHP_TREE_UNBOUND_SYMLINKS.items())
            ),
            f"php-runtime-identity-sha256={runtime['digest']}",
            "integer=int64",
            "number=binary64",
            "strict-types=1",
            f"php-zts={document['zts']}",
            f"php-debug={document['debug']}",
            f"php-extensions={','.join(document['extensions'])}",
            f"php-tokenizer={tokenizer}",
            "php-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=_EXPECTED_PHP_EXECUTABLE_SHA256,
    )


def exact_toolchain(language: Language) -> ExactToolchain:
    return {
        "java": _java,
        "python": _python,
        "csharp": _csharp,
        "typescript": _typescript,
        "javascript": _javascript,
        "go": _go,
        "rust": _rust,
        "cpp": _cpp,
        "objc": _objc,
        "swift": _swift,
        "php": _php,
    }[language]()
