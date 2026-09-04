from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, cast

from .models import Language, RouteError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_GO_TELEMETRY_MODE = b"off\n"


def _installer_bound_toolchain_root() -> Path:
    """Resolve the exact toolchain root selected by the CI installer.

    The byte/tree digests below are immutable route-contract inputs.  The
    filesystem location is deliberately relocatable so a GitHub-hosted runner
    does not inherit the developer's home directory from a captured receipt.
    """

    raw = os.environ.get("ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT", "").strip()
    if not raw:
        raw = os.environ.get("ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT", "").strip()
    candidate = Path(raw).expanduser() if raw else Path.home() / ".local/share/elmos/toolchains"
    normalized = Path(os.path.normpath(str(candidate)))
    if (
        not candidate.is_absolute()
        or candidate != normalized
        or candidate in {Path("/"), Path.home()}
        or any(part in {".", ".."} for part in candidate.parts)
    ):
        raise RouteError(f"EXACT_TOOLCHAIN_ROOT_UNSAFE:{candidate}")
    return candidate


_EXPECTED_TOOLCHAIN_ROOT = _installer_bound_toolchain_root()
_EXPECTED_HOMEBREW_PREFIX = Path(
    os.environ.get("ELMOS_POLYGLOT_ROUTE_HOMEBREW_PREFIX", "/opt/homebrew")
).expanduser()
if (
    not _EXPECTED_HOMEBREW_PREFIX.is_absolute()
    or _EXPECTED_HOMEBREW_PREFIX
    != Path(os.path.normpath(str(_EXPECTED_HOMEBREW_PREFIX)))
    or _EXPECTED_HOMEBREW_PREFIX in {Path("/"), Path.home()}
):
    raise RouteError(
        f"EXACT_TOOLCHAIN_HOMEBREW_PREFIX_UNSAFE:{_EXPECTED_HOMEBREW_PREFIX}"
    )
_EXPECTED_HOMEBREW_CELLAR = _EXPECTED_HOMEBREW_PREFIX / "Cellar"


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


@dataclass(frozen=True)
class _JavaContract:
    home: Path
    java_sha256: str
    javac_sha256: str
    modules_sha256: str
    jvm_sha256: str
    release_sha256: str
    bundle_cdhash_full: str
    team_identifier: str
    java_version: str
    distribution: str


def _output(
    command: list[str],
    *,
    executable_dirs: tuple[Path, ...] = (),
    include_stderr: bool = True,
    include_failure_diagnostic: bool = False,
) -> str:
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-toolchain-env-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            env = sanitized_subprocess_env(
                home=home,
                temp_dir=scratch,
                executable_dirs=(Path(command[0]).resolve().parent, *executable_dirs),
            )
            if platform.system() == "Darwin":
                current_user = os.environ.get("USER") or "nobody"
                env["USER"] = current_user
                env["LOGNAME"] = current_user
                if "__CF_USER_TEXT_ENCODING" in os.environ:
                    env["__CF_USER_TEXT_ENCODING"] = os.environ["__CF_USER_TEXT_ENCODING"]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{command[0]}") from error
    if completed.returncode != 0:
        detail = ""
        if include_failure_diagnostic:
            diagnostic = (completed.stderr or completed.stdout).strip()
            diagnostic = "".join(
                character if character.isprintable() else "?"
                for character in diagnostic[-1000:]
            )
            detail = f":diagnostic={diagnostic or 'EMPTY'}"
        raise RouteError(
            f"EXACT_TOOLCHAIN_UNAVAILABLE:{command[0]}:"
            f"exit={completed.returncode}{detail}"
        )
    return (completed.stdout + (completed.stderr if include_stderr else "")).strip()


_EXPECTED_JAVA_HOME = (
    _EXPECTED_HOMEBREW_CELLAR
    / "openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home"
)
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

# GitHub's macOS arm64 hosted image supplies the exact Temurin build through
# actions/setup-java.  It is a separate contract from the Homebrew route
# bundle above: the bytes, release metadata, and signed bundle identity all
# differ.  Keeping both contracts explicit prevents CI from silently accepting
# an arbitrary JAVA_HOME merely because it prints the right version.
_TEMURIN_JAVA_HOME_SUFFIXES = (
    "Java_Temurin-Hotspot_jdk/21.0.11-10.0/arm64/Contents/Home",
    "Java_Temurin-Hotspot_jdk/21.0.11-10.0.LTS/arm64/Contents/Home",
)
_TEMURIN_JAVA_SHA256 = "afb8ed976e06d85c89192312923301959535169abe087d70166cd00fb96de2e5"
_TEMURIN_JAVAC_SHA256 = "56d42d414a2dfb4ca26a67074ebc7c64271fcf37e5ca6f2d6db2f6c292b5daf1"
_TEMURIN_JAVA_MODULES_SHA256 = "915c525cd0b9d4db404cdc2368bfb4f3e0ab2a6a598b2d6a76d932de19dd2d33"
_TEMURIN_JAVA_JVM_SHA256 = "34bc0bc23d87abb85147409ccdbf604ccd3d2fe8b83ac567a966a5df8a81eded"
_TEMURIN_JAVA_RELEASE_SHA256 = "5fccc331767cf526748f17402c7355efb0d1c24f397c49ff9836760f4a3f3d17"
_TEMURIN_JAVA_BUNDLE_CDHASH_FULL = (
    "e392fdd40bd00e2e6a6986716901ee08ad1e0200e65bdafab50f70554364a5a2"
)
_TEMURIN_JAVA_TEAM_IDENTIFIER = "JCDTMS22B4"
_TEMURIN_JAVA_VERSION = (
    'openjdk version "21.0.11" 2026-04-21 LTS\n'
    "OpenJDK Runtime Environment Temurin-21.0.11+10 (build 21.0.11+10-LTS)\n"
    "OpenJDK 64-Bit Server VM Temurin-21.0.11+10 (build 21.0.11+10-LTS, mixed mode, sharing)"
)

_EXPECTED_DOTNET_VERSION = "10.0.301"
_EXPECTED_DOTNET_RUNTIME_VERSION = "10.0.9"
_EXPECTED_DOTNET_SHIM = _EXPECTED_HOMEBREW_PREFIX / "bin/dotnet"
_EXPECTED_DOTNET_CELLAR = _EXPECTED_HOMEBREW_CELLAR / "dotnet/10.0.301"
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
        raise RouteError(
            failure
            + ":expected="
            + json.dumps(expected, sort_keys=True, separators=(",", ":"))
            + ":observed="
            + json.dumps(identity, sort_keys=True, separators=(",", ":"))
        )


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
        diagnostic = {
            "bundle": observed,
            "hostfxr_binary": hostfxr_binary,
            "hostpolicy_binary": hostpolicy_binary,
        }
        raise RouteError(
            "EXACT_TOOLCHAIN_DOTNET_BUNDLE_MISMATCH:expected="
            + json.dumps(expected, sort_keys=True, separators=(",", ":"))
            + ":observed="
            + json.dumps(diagnostic, sort_keys=True, separators=(",", ":"))
        )
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


def _java_bundle_signature(bundle: Path) -> str:
    """Strictly verify and then display the pinned JDK bundle signature.

    Keep verification and receipt display as distinct fail-closed stages so a
    hosted-runner diagnostic cannot be mistaken for an identity mismatch.  The
    verification flags are part of the native receipt contract and must not be
    relaxed to make a runner pass.
    """

    codesign = Path("/usr/bin/codesign")
    try:
        _output(
            [str(codesign), "--verify", "--deep", "--strict", str(bundle)],
            include_failure_diagnostic=True,
        )
    except RouteError as error:
        raise RouteError(
            "EXACT_TOOLCHAIN_UNAVAILABLE:java:codesign-verify:"
            f"{error}"
        ) from error
    try:
        return _output(
            [str(codesign), "-d", "--verbose=4", str(bundle)],
            include_failure_diagnostic=True,
        )
    except RouteError as error:
        raise RouteError(
            "EXACT_TOOLCHAIN_UNAVAILABLE:java:codesign-display:"
            f"{error}"
        ) from error


def _java_contract() -> _JavaContract:
    """Select one fully pinned Java contract for this execution environment."""

    distribution = os.environ.get("ELMOS_JAVA21_DISTRIBUTION", "").strip().lower()
    if not distribution:
        distribution = "homebrew"
    if distribution == "homebrew":
        expected_home = _EXPECTED_JAVA_HOME.resolve(strict=True)
        return _JavaContract(
            home=expected_home,
            java_sha256=_EXPECTED_JAVA_SHA256,
            javac_sha256=_EXPECTED_JAVAC_SHA256,
            modules_sha256=_EXPECTED_JAVA_MODULES_SHA256,
            jvm_sha256=_EXPECTED_JAVA_JVM_SHA256,
            release_sha256=_EXPECTED_JAVA_RELEASE_SHA256,
            bundle_cdhash_full=_EXPECTED_JAVA_BUNDLE_CDHASH_FULL,
            team_identifier="not set",
            java_version=_EXPECTED_JAVA_VERSION,
            distribution="Homebrew-openjdk@21",
        )
    if distribution != "temurin":
        raise RouteError(f"EXACT_TOOLCHAIN_DISTRIBUTION_UNSUPPORTED:java:{distribution}")
    configured = os.environ.get("ELMOS_JAVA21_HOME", "").strip()
    if not configured:
        raise RouteError("EXACT_TOOLCHAIN_DECLARED_HOME_INVALID:java:temurin")
    try:
        expected_home = Path(configured).resolve(strict=True)
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_DECLARED_HOME_INVALID:java:temurin") from error
    if not expected_home.as_posix().endswith(_TEMURIN_JAVA_HOME_SUFFIXES):
        raise RouteError(
            "EXACT_TOOLCHAIN_DECLARED_HOME_INVALID:java:temurin:"
            f"expected_suffixes={','.join(_TEMURIN_JAVA_HOME_SUFFIXES)}"
        )
    return _JavaContract(
        home=expected_home,
        java_sha256=_TEMURIN_JAVA_SHA256,
        javac_sha256=_TEMURIN_JAVAC_SHA256,
        modules_sha256=_TEMURIN_JAVA_MODULES_SHA256,
        jvm_sha256=_TEMURIN_JAVA_JVM_SHA256,
        release_sha256=_TEMURIN_JAVA_RELEASE_SHA256,
        bundle_cdhash_full=_TEMURIN_JAVA_BUNDLE_CDHASH_FULL,
        team_identifier=_TEMURIN_JAVA_TEAM_IDENTIFIER,
        java_version=_TEMURIN_JAVA_VERSION,
        distribution="Temurin-21.0.11+10",
    )


def _java() -> ExactToolchain:
    try:
        contract = _java_contract()
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:java:expected-home") from error
    expected_home = contract.home
    configured = os.environ.get("ELMOS_JAVA21_HOME", "").strip()
    if configured and contract.distribution == "Homebrew-openjdk@21":
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
    signature = _java_bundle_signature(bundle)
    signature_lines = set(signature.splitlines())
    if (
        java_digest != contract.java_sha256
        or javac_digest != contract.javac_sha256
        or modules_digest != contract.modules_sha256
        or jvm_digest != contract.jvm_sha256
        or release_digest != contract.release_sha256
        or observed_java != contract.java_version
        or observed_javac != _EXPECTED_JAVAC_VERSION
        or "Identifier=net.java.openjdk.jdk" not in signature_lines
        or ("TeamIdentifier=" + contract.team_identifier not in signature_lines)
        or ("CandidateCDHashFull sha256=" + contract.bundle_cdhash_full not in signature_lines)
    ):
        raise RouteError(
            "EXACT_TOOLCHAIN_MISMATCH:java:expected=21.0.11/"
            f"java-sha256={contract.java_sha256}/javac-sha256={contract.javac_sha256}:"
            f"observed-java-sha256={java_digest}/observed-javac-sha256={javac_digest}"
        )
    return ExactToolchain(
        "java",
        "21.0.11",
        str(java),
        str(javac),
        profile=(
            "platform=Darwin/arm64",
            f"distribution={contract.distribution}",
            f"jdk-home={expected_home}",
            f"jdk-cdhash-full={contract.bundle_cdhash_full}",
            f"jdk-modules-sha256={modules_digest}",
            f"libjvm-sha256={jvm_digest}",
            f"release-sha256={release_digest}",
        ),
        executable_sha256=java_digest,
        auxiliary_sha256=javac_digest,
    )


_EXPECTED_PYTHON_LOCAL_ANCHOR = _EXPECTED_TOOLCHAIN_ROOT.parents[2]
_EXPECTED_PYTHON_ROOT = (
    _EXPECTED_TOOLCHAIN_ROOT
    / "python-build-standalone/runtimes/3.12.12+20260211-aarch64-apple-darwin/"
    "sha256-1400403c757cb4da3ce2df42d17d02e1368c54afd46bbed71ae84e25d081a154/python"
)
_EXPECTED_PYTHON_EXECUTABLE = _EXPECTED_PYTHON_ROOT / "bin" / "python3.12"
_EXPECTED_PYTHON_STDLIB = _EXPECTED_PYTHON_ROOT / "lib" / "python3.12"
_EXPECTED_PYTHON_LIBPYTHON = _EXPECTED_PYTHON_ROOT / "lib" / "libpython3.12.dylib"
_EXPECTED_PYTHON_ARCHIVE = (
    _EXPECTED_TOOLCHAIN_ROOT
    / "python-build-standalone/archives/"
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
_EXPECTED_PYTHON_RUNTIME_IDENTITY_SHA256 = "8776314c1c57bbf83332a98d947144d329c8e6e57d2fe1cd850875f27d807d0a"
_PYTHON_RUNTIME_PATH_FIELDS = (
    "executable",
    "prefix",
    "base_prefix",
    "stdlib",
    "platstdlib",
)
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


def _canonical_python_runtime_identity(runtime: dict[str, object]) -> str:
    """Bind the exact runtime identity without binding the account home path."""

    normalized = dict(runtime)
    root = str(_EXPECTED_PYTHON_ROOT)
    for field in _PYTHON_RUNTIME_PATH_FIELDS:
        value = normalized.get(field)
        if not isinstance(value, str):
            raise RouteError(
                f"EXACT_TOOLCHAIN_PYTHON_IDENTITY_PATH_MISMATCH:{field}"
            )
        if value == root:
            normalized[field] = "@PYTHON_ROOT@"
        elif value.startswith(root + os.sep):
            normalized[field] = "@PYTHON_ROOT@" + value[len(root) :]
        else:
            raise RouteError(
                f"EXACT_TOOLCHAIN_PYTHON_IDENTITY_PATH_MISMATCH:{field}"
            )
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


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
    if not isinstance(runtime, dict):
        raise RouteError("EXACT_TOOLCHAIN_PYTHON_IDENTITY_INVALID")
    canonical_runtime = _canonical_python_runtime_identity(runtime)
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
    mismatch_fields: list[str] = []
    if tree_before != tree_after:
        mismatch_fields.append("tree_changed")
    if archive_before != archive_after:
        mismatch_fields.append("archive_changed")
    if archive_chain_before != archive_chain_after:
        mismatch_fields.append("archive_chain_changed")
    if executable_before != executable_after:
        mismatch_fields.append("executable_changed")
    if libpython_before != libpython_after:
        mismatch_fields.append("libpython_changed")
    if executable_after.get("sha256") != _EXPECTED_PYTHON_EXECUTABLE_SHA256:
        mismatch_fields.append("executable_sha256")
    if executable_after.get("bytes") != _EXPECTED_PYTHON_EXECUTABLE_BYTES:
        mismatch_fields.append("executable_bytes")
    if libpython_after.get("sha256") != _EXPECTED_PYTHON_LIBPYTHON_SHA256:
        mismatch_fields.append("libpython_sha256")
    if libpython_after.get("bytes") != _EXPECTED_PYTHON_LIBPYTHON_BYTES:
        mismatch_fields.append("libpython_bytes")
    if archive_after.get("sha256") != _EXPECTED_PYTHON_SOURCE_ARCHIVE_SHA256:
        mismatch_fields.append("archive_sha256")
    if archive_after.get("bytes") != _EXPECTED_PYTHON_SOURCE_ARCHIVE_BYTES:
        mismatch_fields.append("archive_bytes")
    if (
        hashlib.sha256(canonical_runtime.encode("utf-8")).hexdigest()
        != _EXPECTED_PYTHON_RUNTIME_IDENTITY_SHA256
    ):
        mismatch_fields.append("runtime_identity_sha256")
    for key, expected in (
        ("version", "3.12.12"),
        ("implementation", "cpython"),
        ("executable", str(_EXPECTED_PYTHON_EXECUTABLE)),
        ("prefix", str(_EXPECTED_PYTHON_ROOT)),
        ("base_prefix", str(_EXPECTED_PYTHON_ROOT)),
        ("stdlib", str(_EXPECTED_PYTHON_STDLIB)),
        ("platstdlib", str(_EXPECTED_PYTHON_STDLIB)),
        ("math_origin", "built-in"),
    ):
        if runtime.get(key) != expected:
            mismatch_fields.append(f"runtime_{key}")
    if mismatch_fields:
        raise RouteError(
            "EXACT_TOOLCHAIN_MISMATCH:python:expected=3.12.12+20260211:"
            + ",".join(mismatch_fields)
        )
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
    node_profile_before = _verify_node_dependency_closure(node_before)
    compiler_before = _typescript_compiler_closure()
    _verify_typescript_compiler_closure(compiler_before)
    runtime_identity = _node_runtime_identity(node_profile_before)
    typescript_version = _output([str(_EXPECTED_NODE_EXECUTABLE), str(_EXPECTED_TYPESCRIPT_LAUNCHER), "--version"])
    compiler_after = _typescript_compiler_closure()
    _verify_typescript_compiler_closure(compiler_after)
    node_after = _node_dependency_closure()
    node_profile_after = _verify_node_dependency_closure(node_after)
    shim_after = _node_shim_identity()
    selected_node_profile = _node_profile(node_profile_after)
    if (
        shim_before != shim_after
        or node_before != node_after
        or node_profile_before != node_profile_after
        or runtime_identity["profile"] != node_profile_after
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
            f"node-closure-profile={node_profile_after}",
            f"node-topology-sha256={node_after['topology_sha256']}",
            f"node-closure-component-count={node_after['component_count']}",
            f"node-closure-edge-count={node_after['edge_count']}",
            f"node-closure-system-edge-count={node_after['system_edge_count']}",
            "otool-system-tool-content-soundness=NOT_RUN",
            "dyld-system-library-content-soundness=NOT_RUN",
            "typescript-compiler-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=str(selected_node_profile["node_sha256"]),
        auxiliary_sha256=_EXPECTED_TYPESCRIPT_LAUNCHER_SHA256,
    )


_EXPECTED_NODE_ROOT = _EXPECTED_HOMEBREW_CELLAR / "node" / "26.0.0"
_EXPECTED_NODE_SHIM = _EXPECTED_HOMEBREW_PREFIX / "bin" / "node"
_EXPECTED_NODE_EXECUTABLE = _EXPECTED_NODE_ROOT / "bin" / "node"
_EXPECTED_NODE_LIBNODE = _EXPECTED_NODE_ROOT / "lib" / "libnode.147.dylib"
_EXPECTED_NODE_LIBADA = (
    _EXPECTED_HOMEBREW_CELLAR / "ada-url" / "3.4.4" / "lib" / "libada.3.4.4.dylib"
)
_EXPECTED_NODE_OTOOL = Path("/usr/bin/otool")
_EXPECTED_NODE_SHIM_TARGET = "../Cellar/node/26.0.0/bin/node"
_NODE26_PROCESS_VERSIONS = (
    '{"acorn":"8.16.0","ada":"3.4.4","amaro":"1.1.8","ares":"1.34.6",'
    '"brotli":"1.2.0","cldr":"48.0","icu":"78.3","lief":"0.17.0",'
    '"llhttp":"9.4.1","merve":"1.2.2","modules":"147","napi":"10",'
    '"nbytes":"0.1.4","ncrypto":"0.0.1","nghttp2":"1.69.0","nghttp3":"",'
    '"ngtcp2":"","node":"26.0.0","openssl":"3.6.3","simdjson":"4.6.3",'
    '"simdutf":"7.7.0","sqlite":"3.53.0","tz":"2026a","undici":"8.0.2",'
    '"unicode":"17.0","uv":"1.52.1","uvwasi":"0.0.23",'
    '"v8":"14.6.202.33-node.19","zlib":"1.2.12","zstd":"1.5.7"}'
)
_NODE26_PROCESS_VERSIONS_SHA256 = (
    "3d1c55b1d3598ed3740b8d5461151069351d53495649a1efb718f6f858b48d52"
)
_NODE26_LEGACY_PROFILE_FIELDS: dict[str, str | int] = {
    "qualification_host": "legacy-homebrew-darwin-arm64",
    "node_version": "v26.0.0",
    "platform": "darwin",
    "arch": "arm64",
    "topology_sha256": "2a77ac1d4bcf11286a97e403060b6a6490d21127857b6d1ba21806f026451bfd",
    "component_count": 25,
    "edge_count": 49,
    "system_edge_count": 43,
    "system_edge_sha256": "74106326c0673ff63a85e6fbc892c55a7c7f329eaad0fd715817beae4ba2b6c4",
    "node_sha256": "73cc3e9b5d2b1753ea3395a5bf39787ef85f20f048a0f0744761860b81b8fbdb",
    "node_bytes": 68_672,
    "libnode_sha256": "24ff9dcc3d953532fde1e5270fab9331279fb60fcc5747bbb5cf1537cba20d47",
    "libnode_bytes": 70_843_136,
    "process_versions": _NODE26_PROCESS_VERSIONS,
    "process_versions_sha256": _NODE26_PROCESS_VERSIONS_SHA256,
}
# Each record is a complete, coherent Node runtime identity.  The first three
# preserve the previously qualified Homebrew closures.  The remaining records
# are independently observed GitHub macOS 26 image closures.  Image provenance
# names the host on which those bytes were measured; acceptance is still based
# on the complete content/topology/process record below, never on an
# environment label alone.  Historical profiles remain registered so an exact
# replay does not silently reinterpret old bytes as the current hosted image.
_EXPECTED_NODE_CLOSURE_PROFILES: tuple[dict[str, str | int], ...] = (
    {
        **_NODE26_LEGACY_PROFILE_FIELDS,
        "profile": "homebrew-node26-libada-77917065434c-616512",
        "sha256": "bd919085f8ae40bca10d5a2da36542eb90c5f18424dc60780c73c70b90d4244b",
        "bytes": 120_513_104,
        "closure_sha256": "bd919085f8ae40bca10d5a2da36542eb90c5f18424dc60780c73c70b90d4244b",
        "closure_bytes": 120_513_104,
        "libada_sha256": "77917065434cb8263f1bd0768b0e54cda7793269be8a4d11d4bf72a67211881c",
        "libada_bytes": 616_512,
    },
    {
        **_NODE26_LEGACY_PROFILE_FIELDS,
        "profile": "homebrew-node26-libada-e4b04b323411-613248",
        "sha256": "3139bcc0851234d404144c824707a1e7d17c2841ff8af0dac05d37ce36dccf4f",
        "bytes": 120_509_840,
        "closure_sha256": "3139bcc0851234d404144c824707a1e7d17c2841ff8af0dac05d37ce36dccf4f",
        "closure_bytes": 120_509_840,
        "libada_sha256": "e4b04b323411a5ca0f06086ad54378f21d02831fb571f09ea61db8f20dfdedc4",
        "libada_bytes": 613_248,
    },
    {
        **_NODE26_LEGACY_PROFILE_FIELDS,
        "profile": "homebrew-node26-libada-b39ba5c76cfa-598704",
        "sha256": "81c23d23750fdd04240bc4debddd6044d6466a7f1fb2993f34087b12162319b7",
        "bytes": 120_495_296,
        "closure_sha256": "81c23d23750fdd04240bc4debddd6044d6466a7f1fb2993f34087b12162319b7",
        "closure_bytes": 120_495_296,
        "libada_sha256": "b39ba5c76cfa9e8d7a37b51daf937414316b671f51360daae62b9885e9d089f8",
        "libada_bytes": 598_704,
    },
    {
        "profile": "github-macos26-20260728-node26-b39ba5c76cfa-598704",
        "sha256": "318b4e2a7f408f6e541a3ab0effe07b85df0d201999a377701cb20ba42556b65",
        "bytes": 119_975_888,
        "qualification_host": "github-macos-26-arm64@20260728.0273.1",
        "node_version": "v26.0.0",
        "platform": "darwin",
        "arch": "arm64",
        "topology_sha256": "4d2426eac17276f2bc4ec386d85660ecf5896cb4746fc1de87fbe4d7f2551e82",
        "component_count": 25,
        "edge_count": 49,
        "system_edge_count": 43,
        "system_edge_sha256": "495f6ba5eaf5ba5b2c1fa40a2325679d1823b279b06ed283a520706f02b28444",
        "closure_sha256": "318b4e2a7f408f6e541a3ab0effe07b85df0d201999a377701cb20ba42556b65",
        "closure_bytes": 119_975_888,
        "node_sha256": "542a44a023d27e626d79fbd646f3e2b898bd291b96028b3644795f21b5a43bc9",
        "node_bytes": 50_672,
        "libnode_sha256": "980e876ab7f53bacc6262e77c4ac96f60ca3bac4dd241b0cc6cdc945c4ecaf88",
        "libnode_bytes": 70_661_840,
        "libada_sha256": "b39ba5c76cfa9e8d7a37b51daf937414316b671f51360daae62b9885e9d089f8",
        "libada_bytes": 598_704,
        "process_versions": _NODE26_PROCESS_VERSIONS,
        "process_versions_sha256": _NODE26_PROCESS_VERSIONS_SHA256,
    },
    {
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
        "process_versions": _NODE26_PROCESS_VERSIONS,
        "process_versions_sha256": _NODE26_PROCESS_VERSIONS_SHA256,
    },
)


def node_closure_profile_id(closure_sha256: str) -> str | None:
    matches = [
        str(profile["profile"])
        for profile in _validated_node_profiles()
        if profile["closure_sha256"] == closure_sha256
    ]
    return matches[0] if len(matches) == 1 else None

# Backward-compatible aliases name the original local profile only.  Runtime
# selection below never uses these aliases; it uses the selected complete
# profile record so a hosted Node binary cannot be combined with legacy dylibs.
_EXPECTED_NODE_SHA256 = str(_EXPECTED_NODE_CLOSURE_PROFILES[0]["node_sha256"])
_EXPECTED_NODE_BYTES = int(_EXPECTED_NODE_CLOSURE_PROFILES[0]["node_bytes"])
_EXPECTED_NODE_LIBNODE_SHA256 = str(
    _EXPECTED_NODE_CLOSURE_PROFILES[0]["libnode_sha256"]
)
_EXPECTED_NODE_LIBNODE_BYTES = int(
    _EXPECTED_NODE_CLOSURE_PROFILES[0]["libnode_bytes"]
)
_EXPECTED_NODE_CLOSURE_COMPONENT_COUNT = int(
    _EXPECTED_NODE_CLOSURE_PROFILES[0]["component_count"]
)
_EXPECTED_NODE_CLOSURE_EDGE_COUNT = int(
    _EXPECTED_NODE_CLOSURE_PROFILES[0]["edge_count"]
)
_EXPECTED_NODE_CLOSURE_SYSTEM_EDGE_COUNT = int(
    _EXPECTED_NODE_CLOSURE_PROFILES[0]["system_edge_count"]
)
_EXPECTED_NODE_SYSTEM_EDGE_SHA256 = str(
    _EXPECTED_NODE_CLOSURE_PROFILES[0]["system_edge_sha256"]
)
_EXPECTED_NODE_TOPOLOGY_SHA256 = str(
    _EXPECTED_NODE_CLOSURE_PROFILES[0]["topology_sha256"]
)
_EXPECTED_NODE_PROCESS_VERSIONS = _NODE26_PROCESS_VERSIONS
_EXPECTED_NODE_PROCESS_VERSIONS_SHA256 = _NODE26_PROCESS_VERSIONS_SHA256
_NODE_TOPOLOGY_CACHE: dict[str, object] | None = None

_NODE26_PROFILE_FIELDS = frozenset(
    {
        "profile",
        "sha256",
        "bytes",
        "qualification_host",
        "node_version",
        "platform",
        "arch",
        "topology_sha256",
        "component_count",
        "edge_count",
        "system_edge_count",
        "system_edge_sha256",
        "closure_sha256",
        "closure_bytes",
        "node_sha256",
        "node_bytes",
        "libnode_sha256",
        "libnode_bytes",
        "libada_sha256",
        "libada_bytes",
        "process_versions",
        "process_versions_sha256",
    }
)
_NODE26_PROFILE_HASH_FIELDS = frozenset(
    {
        "topology_sha256",
        "system_edge_sha256",
        "closure_sha256",
        "sha256",
        "node_sha256",
        "libnode_sha256",
        "libada_sha256",
        "process_versions_sha256",
    }
)
_NODE26_PROFILE_INTEGER_FIELDS = frozenset(
    {
        "component_count",
        "edge_count",
        "system_edge_count",
        "closure_bytes",
        "bytes",
        "node_bytes",
        "libnode_bytes",
        "libada_bytes",
    }
)


def _validated_node_profiles() -> tuple[dict[str, str | int], ...]:
    """Return the exact profile registry after validating its own closure."""

    profiles = _EXPECTED_NODE_CLOSURE_PROFILES
    profile_ids: set[str] = set()
    closure_ids: set[str] = set()
    for profile in profiles:
        if set(profile) != _NODE26_PROFILE_FIELDS:
            raise RouteError("EXACT_TOOLCHAIN_NODE_PROFILE_REGISTRY_INVALID")
        if any(
            not isinstance(profile[field], str) or not str(profile[field])
            for field in _NODE26_PROFILE_FIELDS - _NODE26_PROFILE_INTEGER_FIELDS
        ) or any(
            type(profile[field]) is not int or int(profile[field]) <= 0
            for field in _NODE26_PROFILE_INTEGER_FIELDS
        ):
            raise RouteError("EXACT_TOOLCHAIN_NODE_PROFILE_REGISTRY_INVALID")
        if any(
            len(str(profile[field])) != 64
            or any(character not in "0123456789abcdef" for character in str(profile[field]))
            for field in _NODE26_PROFILE_HASH_FIELDS
        ):
            raise RouteError("EXACT_TOOLCHAIN_NODE_PROFILE_REGISTRY_INVALID")
        process_versions = str(profile["process_versions"])
        if (
            hashlib.sha256(process_versions.encode("ascii")).hexdigest()
            != profile["process_versions_sha256"]
            or profile["sha256"] != profile["closure_sha256"]
            or profile["bytes"] != profile["closure_bytes"]
            or profile["node_version"] != "v26.0.0"
            or profile["platform"] != "darwin"
            or profile["arch"] != "arm64"
        ):
            raise RouteError("EXACT_TOOLCHAIN_NODE_PROFILE_REGISTRY_INVALID")
        profile_id = str(profile["profile"])
        closure_id = str(profile["closure_sha256"])
        if profile_id in profile_ids or closure_id in closure_ids:
            raise RouteError("EXACT_TOOLCHAIN_NODE_PROFILE_REGISTRY_INVALID")
        profile_ids.add(profile_id)
        closure_ids.add(closure_id)
    return profiles


def _node_profile(profile_id: str) -> dict[str, str | int]:
    matches = [
        profile
        for profile in _validated_node_profiles()
        if profile["profile"] == profile_id
    ]
    if len(matches) != 1:
        raise RouteError("EXACT_TOOLCHAIN_NODE_PROFILE_REGISTRY_INVALID")
    return matches[0]


_EXPECTED_TYPESCRIPT_CACHE_ANCHOR = _EXPECTED_TOOLCHAIN_ROOT.parents[2]
_EXPECTED_TYPESCRIPT_ROOT = (
    _EXPECTED_TOOLCHAIN_ROOT
    / "typescript/5.9.2/"
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
# The compiler closure is relocatable, but its content identity predates that
# property and was captured at this path/owner on macOS.  Live manifests are
# still validated against the installer-selected root and the filesystem
# metadata observed there.  Only these host-placement fields are projected to
# their historical values before hashing; content, modes, roles, byte counts,
# and semantic status remain byte-for-byte identity inputs.
_TYPESCRIPT_IDENTITY_CANONICAL_ROOT = Path(
    "/Users/stephen/.local/share/elmos/toolchains/typescript/5.9.2/"
    "sha256-61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
_TYPESCRIPT_IDENTITY_CANONICAL_UID = 501
_TYPESCRIPT_IDENTITY_CANONICAL_GID = 20
_TYPESCRIPT_IDENTITY_CANONICAL_PACKAGE_NLINK = 6
_TYPESCRIPT_IDENTITY_CANONICAL_DIRECTORY_NLINKS = {"bin": 3, "lib": 107}
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


def _canonical_typescript_closure_manifest(
    manifest: dict[str, object],
) -> dict[str, object]:
    """Validate a live closure and return its host-independent identity view."""

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
        if (
            manifest["schema_version"] != 2
            or manifest["kind"]
            != "elmos.typescript-5.9.2-full-stdlib-compiler-closure"
            or manifest["semantic_soundness"] != "NOT_RUN"
        ):
            raise ValueError
        package = manifest["package_root"]
        directories = manifest["directories"]
        files = manifest["files"]
        if (
            not isinstance(package, dict)
            or set(package) != {"root", "mode", "uid", "gid", "nlink"}
            or not isinstance(directories, list)
            or not isinstance(files, list)
        ):
            raise ValueError
        directory_names: set[str] = set()
        directory_paths: set[str] = set()
        for item in directories:
            if (
                not isinstance(item, dict)
                or set(item)
                != {
                    "relative_path",
                    "resolved_path",
                    "mode",
                    "uid",
                    "gid",
                    "nlink",
                }
                or not isinstance(item.get("relative_path"), str)
                or not isinstance(item.get("resolved_path"), str)
                or not isinstance(item.get("mode"), str)
                or any(
                    type(item.get(field)) is not int
                    for field in ("uid", "gid", "nlink")
                )
                or cast(str, item["relative_path"]) in directory_names
                or cast(str, item["resolved_path"]) in directory_paths
            ):
                raise ValueError
            directory_names.add(cast(str, item["relative_path"]))
            directory_paths.add(cast(str, item["resolved_path"]))

        # Re-run the root and directory safety bindings before discarding host
        # placement from the digest.  This makes relocation portable without
        # allowing a caller to forge a path, owner, group, or link count.
        if package != _typescript_package_root_binding():
            raise ValueError
        expected_directories = [
            _typescript_package_directory_binding(relative)
            for relative in ("bin", "lib")
        ]
        if directories != expected_directories:
            raise ValueError

        roles: set[str] = set()
        paths: set[Path] = set()
        package_uid = cast(int, package["uid"])
        package_gid = cast(int, package["gid"])
        if any(
            directory["uid"] != package_uid or directory["gid"] != package_gid
            for directory in expected_directories
        ):
            raise ValueError
        for item in files:
            if (
                not isinstance(item, dict)
                or set(item)
                != {
                    "role",
                    "resolved_path",
                    "bytes",
                    "sha256",
                    "mode",
                    "uid",
                    "gid",
                    "nlink",
                }
                or not isinstance(item.get("role"), str)
                or not isinstance(item.get("resolved_path"), str)
                or type(item.get("bytes")) is not int
                or not isinstance(item.get("sha256"), str)
                or not isinstance(item.get("mode"), str)
                or type(item.get("uid")) is not int
                or type(item.get("gid")) is not int
                or type(item.get("nlink")) is not int
            ):
                raise ValueError
            role = cast(str, item["role"])
            path = Path(cast(str, item["resolved_path"]))
            if (
                role in roles
                or path in paths
                or not path.is_absolute()
                or str(path) != item["resolved_path"]
            ):
                raise ValueError
            roles.add(role)
            paths.add(path)
            relative = path.relative_to(_EXPECTED_TYPESCRIPT_ROOT)
            if not relative.parts or any(
                part in {"", ".", ".."} for part in relative.parts
            ):
                raise ValueError
            rebound = _typescript_file_binding(path, role)
            if (
                item != rebound
                or item["uid"] != package_uid
                or item["gid"] != package_gid
                or len(cast(str, item["sha256"])) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in cast(str, item["sha256"])
                )
            ):
                raise ValueError

        # Bind the enclosing directories again after every file has been
        # opened and hashed.  A caller cannot swap a root between the first
        # placement check and the last content read and still receive a
        # portable identity.
        if (
            _typescript_package_root_binding() != package
            or [
                _typescript_package_directory_binding(relative)
                for relative in ("bin", "lib")
            ]
            != directories
        ):
            raise ValueError

        copied = json.loads(json.dumps(manifest, sort_keys=True))
        if not isinstance(copied, dict):
            raise ValueError
        canonical_package = copied["package_root"]
        canonical_directories = copied["directories"]
        canonical_files = copied["files"]
        if (
            not isinstance(canonical_package, dict)
            or not isinstance(canonical_directories, list)
            or not isinstance(canonical_files, list)
        ):
            raise ValueError
        canonical_package["root"] = str(_TYPESCRIPT_IDENTITY_CANONICAL_ROOT)
        canonical_package["uid"] = _TYPESCRIPT_IDENTITY_CANONICAL_UID
        canonical_package["gid"] = _TYPESCRIPT_IDENTITY_CANONICAL_GID
        canonical_package["nlink"] = _TYPESCRIPT_IDENTITY_CANONICAL_PACKAGE_NLINK
        for item in canonical_directories:
            if not isinstance(item, dict):
                raise ValueError
            directory_relative = cast(str, item["relative_path"])
            item["resolved_path"] = str(
                _TYPESCRIPT_IDENTITY_CANONICAL_ROOT / directory_relative
            )
            item["uid"] = _TYPESCRIPT_IDENTITY_CANONICAL_UID
            item["gid"] = _TYPESCRIPT_IDENTITY_CANONICAL_GID
            item["nlink"] = _TYPESCRIPT_IDENTITY_CANONICAL_DIRECTORY_NLINKS[
                directory_relative
            ]
        for item in canonical_files:
            if not isinstance(item, dict):
                raise ValueError
            path = Path(cast(str, item["resolved_path"]))
            file_relative = path.relative_to(_EXPECTED_TYPESCRIPT_ROOT)
            item["resolved_path"] = str(
                _TYPESCRIPT_IDENTITY_CANONICAL_ROOT / file_relative
            )
            item["uid"] = _TYPESCRIPT_IDENTITY_CANONICAL_UID
            item["gid"] = _TYPESCRIPT_IDENTITY_CANONICAL_GID
            item["nlink"] = 1
        return cast(dict[str, object], copied)
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID") from error


def _raw_typescript_closure_identity(
    manifest: dict[str, object],
) -> dict[str, object]:
    """Hash an already validated/canonical manifest without filesystem access.

    Packed replay first rebinds its private extracted files and projects those
    bindings to the historical canonical placement.  Calling the live
    canonicalizer again would incorrectly interpret those projected paths as
    host files.  This deliberately narrow pure boundary avoids that second
    projection while retaining strict schema and scalar validation.
    """

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
        if (
            manifest["schema_version"] != 2
            or manifest["kind"]
            != "elmos.typescript-5.9.2-full-stdlib-compiler-closure"
            or manifest["semantic_soundness"] != "NOT_RUN"
        ):
            raise ValueError
        package = manifest["package_root"]
        directories = manifest["directories"]
        files = cast(list[dict[str, object]], manifest["files"])
        if (
            not isinstance(package, dict)
            or set(package) != {"root", "mode", "uid", "gid", "nlink"}
            or not isinstance(package.get("root"), str)
            or not isinstance(package.get("mode"), str)
            or any(type(package.get(field)) is not int for field in ("uid", "gid", "nlink"))
            or not isinstance(directories, list)
            or not isinstance(files, list)
        ):
            raise ValueError
        roles: set[str] = set()
        resolved_paths: set[str] = set()
        for item in files:
            if (
                not isinstance(item, dict)
                or set(item)
                != {
                    "role",
                    "resolved_path",
                    "bytes",
                    "sha256",
                    "mode",
                    "uid",
                    "gid",
                    "nlink",
                }
                or not isinstance(item.get("role"), str)
                or not isinstance(item.get("resolved_path"), str)
                or type(item.get("bytes")) is not int
                or not isinstance(item.get("sha256"), str)
                or not isinstance(item.get("mode"), str)
                or any(
                    type(item.get(field)) is not int
                    for field in ("uid", "gid", "nlink")
                )
                or cast(int, item["bytes"]) < 0
                or len(cast(str, item["sha256"])) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in cast(str, item["sha256"])
                )
                or cast(str, item["role"]) in roles
                or cast(str, item["resolved_path"]) in resolved_paths
            ):
                raise ValueError
            roles.add(cast(str, item["role"]))
            resolved_paths.add(cast(str, item["resolved_path"]))
        canonical = json.dumps(
            manifest, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {
            "manifest": manifest,
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "file_count": len(files),
            "bytes": sum(cast(int, item["bytes"]) for item in files),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise RouteError("EXACT_TOOLCHAIN_TYPESCRIPT_CLOSURE_INVALID") from error


def _typescript_closure_identity(manifest: dict[str, object]) -> dict[str, object]:
    canonical_manifest = _canonical_typescript_closure_manifest(manifest)
    canonical_identity = _raw_typescript_closure_identity(canonical_manifest)
    return {
        "manifest": manifest,
        "sha256": canonical_identity["sha256"],
        "file_count": canonical_identity["file_count"],
        "bytes": canonical_identity["bytes"],
    }


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
        topology = {
            "schema_version": 1,
            "kind": "elmos.node26-homebrew-macho-topology",
            "install_root": manifest["install_root"],
            "component_paths": sorted(
                cast(str, component["resolved_path"])
                for component in components
            ),
            "edges": edges,
            "system_edges": system_edges,
        }
        topology_identity = _node_topology_identity(topology)
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        system_canonical = json.dumps({"edges": system_edges}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            "manifest": manifest,
            "sha256": hashlib.sha256(canonical).hexdigest(),
            "topology_sha256": topology_identity["sha256"],
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


def _verify_node_topology_identity(identity: dict[str, object]) -> tuple[str, ...]:
    try:
        topology = cast(dict[str, object], identity["topology"])
        recomputed = _node_topology_identity(topology)
    except (KeyError, TypeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_INVALID") from error
    for field in ("sha256", "component_count", "edge_count", "system_edge_count"):
        if recomputed[field] != identity.get(field):
            raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_INVALID")
    matching_profiles = tuple(
        str(profile["profile"])
        for profile in _validated_node_profiles()
        if recomputed["sha256"] == profile["topology_sha256"]
        and recomputed["component_count"] == profile["component_count"]
        and recomputed["edge_count"] == profile["edge_count"]
        and recomputed["system_edge_count"] == profile["system_edge_count"]
    )
    if not matching_profiles:
        raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_MISMATCH")
    return matching_profiles


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
    identity = _node_closure_identity(manifest)
    if identity["topology_sha256"] != topology_identity["sha256"]:
        raise RouteError("EXACT_TOOLCHAIN_NODE_TOPOLOGY_CACHE_MISMATCH")
    return identity


def _verify_node_dependency_closure(identity: dict[str, object]) -> str:
    try:
        manifest = cast(dict[str, object], identity["manifest"])
        recomputed = _node_closure_identity(manifest)
        components = cast(list[dict[str, object]], manifest["components"])
        executable = next(item for item in components if item.get("resolved_path") == str(_EXPECTED_NODE_EXECUTABLE))
        libnode = next(item for item in components if item.get("resolved_path") == str(_EXPECTED_NODE_LIBNODE))
        libada = next(item for item in components if item.get("resolved_path") == str(_EXPECTED_NODE_LIBADA))
    except (KeyError, StopIteration, TypeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_NODE_CLOSURE_INVALID") from error
    for field in (
        "sha256",
        "topology_sha256",
        "component_count",
        "edge_count",
        "system_edge_count",
        "bytes",
        "system_edge_sha256",
    ):
        if recomputed[field] != identity.get(field):
            raise RouteError("EXACT_TOOLCHAIN_NODE_CLOSURE_IDENTITY_INVALID")

    executable_profiles = [
        profile
        for profile in _validated_node_profiles()
        if executable.get("sha256") == profile["node_sha256"]
        and executable.get("bytes") == profile["node_bytes"]
    ]
    if not executable_profiles:
        raise RouteError("EXACT_TOOLCHAIN_NODE_EXECUTABLE_MISMATCH")
    libnode_profiles = [
        profile
        for profile in executable_profiles
        if libnode.get("sha256") == profile["libnode_sha256"]
        and libnode.get("bytes") == profile["libnode_bytes"]
    ]
    if not libnode_profiles:
        raise RouteError("EXACT_TOOLCHAIN_NODE_LIBNODE_MISMATCH")
    libada_profiles = [
        profile
        for profile in libnode_profiles
        if libada.get("sha256") == profile["libada_sha256"]
        and libada.get("bytes") == profile["libada_bytes"]
    ]
    if not libada_profiles:
        raise RouteError("EXACT_TOOLCHAIN_NODE_LIBADA_MISMATCH")

    matching_profiles = [
        profile
        for profile in libada_profiles
        if recomputed["sha256"] == profile["closure_sha256"]
        and recomputed["topology_sha256"] == profile["topology_sha256"]
        and recomputed["component_count"] == profile["component_count"]
        and recomputed["edge_count"] == profile["edge_count"]
        and recomputed["system_edge_count"] == profile["system_edge_count"]
        and recomputed["bytes"] == profile["closure_bytes"]
        and recomputed["system_edge_sha256"] == profile["system_edge_sha256"]
    ]
    if len(matching_profiles) != 1:
        raise RouteError("EXACT_TOOLCHAIN_NODE_CLOSURE_MISMATCH")
    return str(matching_profiles[0]["profile"])


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


def _node_runtime_identity(profile_id: str) -> dict[str, object]:
    selected_profile = _node_profile(profile_id)
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
        observed_version != selected_profile["node_version"]
        or identity.get("execPath") != str(_EXPECTED_NODE_EXECUTABLE)
        or identity.get("platform") != selected_profile["platform"]
        or identity.get("arch") != selected_profile["arch"]
        or observed_versions != selected_profile["process_versions"]
        or hashlib.sha256(observed_versions.encode("ascii")).hexdigest()
        != selected_profile["process_versions_sha256"]
    ):
        raise RouteError(
            "EXACT_TOOLCHAIN_MISMATCH:node-runtime:"
            "expected=Node26.0.0/darwin-arm64/"
            f"profile={profile_id}/sha256={selected_profile['node_sha256']}:"
            f"observed={observed_version}/"
            f"{identity.get('platform')}-{identity.get('arch')}"
        )
    return {
        "profile": profile_id,
        "version": observed_version,
        "process": identity,
        "process_versions_sha256": selected_profile["process_versions_sha256"],
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
    closure_profile_before = _verify_node_dependency_closure(closure_before)
    runtime_identity = _node_runtime_identity(closure_profile_before)
    closure_after = _node_dependency_closure()
    closure_profile_after = _verify_node_dependency_closure(closure_after)
    shim_after = _node_shim_identity()
    selected_profile = _node_profile(closure_profile_after)
    if (
        closure_before != closure_after
        or closure_profile_before != closure_profile_after
        or runtime_identity["profile"] != closure_profile_after
        or shim_before != shim_after
    ):
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
            f"process-versions-sha256={selected_profile['process_versions_sha256']}",
            f"node-install-root={_EXPECTED_NODE_ROOT}",
            f"node-closure-sha256={closure_after['sha256']}",
            f"node-closure-profile={closure_profile_after}",
            f"node-topology-sha256={closure_after['topology_sha256']}",
            f"node-closure-component-count={closure_after['component_count']}",
            f"node-closure-edge-count={closure_after['edge_count']}",
            f"node-closure-system-edge-count={closure_after['system_edge_count']}",
            f"node-closure-bytes={closure_after['bytes']}",
            f"node-system-edge-sha256={closure_after['system_edge_sha256']}",
            f"libnode-sha256={selected_profile['libnode_sha256']}",
            f"libnode-bytes={selected_profile['libnode_bytes']}",
            "otool-system-tool-content-soundness=NOT_RUN",
            "dyld-system-library-content-soundness=NOT_RUN",
            "compiler-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=str(selected_profile["node_sha256"]),
    )


_EXPECTED_USER_LOCAL = _EXPECTED_TOOLCHAIN_ROOT.parents[2]

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
_EXPECTED_RUST_WRAPPER_TREE_SHA256 = "9535e5745dbb13f2573cff2e885c85e5ff178ea060d2ae598cdf3fe4c1e821e8"
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


@dataclass(frozen=True)
class AppleRouteHostProfile:
    """One indivisible, measured GitHub macOS/Xcode execution closure."""

    profile_id: str
    image_version: str
    product_version: str
    build_version: str
    xcode: str
    macos_sdk: str
    clang_sha256: str
    swiftc_sha256: str
    component_overrides: tuple[tuple[str, str, int], ...]
    tree_overrides: tuple[tuple[str, str, int, int], ...]
    apple_git_sha256: str
    apple_git_bytes: int
    sandbox_exec_sha256: str
    sandbox_exec_cdhash_full: str
    sandbox_exec_bytes: int
    codesign_sha256: str
    codesign_bytes: int


_APPLE_ROUTE_CURRENT_PROFILE = AppleRouteHostProfile(
    profile_id="github-macos26-20260831.0337.3",
    image_version="20260831.0337.3",
    product_version="26.6.2",
    build_version="25G83",
    xcode=_EXPECTED_XCODE,
    macos_sdk=_EXPECTED_MACOS_SDK,
    clang_sha256=_EXPECTED_CLANG_SHA256,
    swiftc_sha256=_EXPECTED_SWIFTC_SHA256,
    component_overrides=(),
    tree_overrides=(),
    apple_git_sha256="10f9c1df894525ae4c7454258febab6d3d25071062b42cb48dbb1842cdffd2a9",
    apple_git_bytes=3_704_880,
    sandbox_exec_sha256="abc5bb136d6b5cce8fa85d789f78e3326c51ca60cae637b2064adfb67a1dcd9a",
    sandbox_exec_cdhash_full="4828e16826baf4052b8212b82d1f3f2c13216303e062f0cc2b398f045d422625",
    sandbox_exec_bytes=102_368,
    codesign_sha256="844d30a12929b59c9f2215e2a308c3e1db572831a478f35906e452a54025603e",
    codesign_bytes=458_576,
)

_APPLE_ROUTE_LEGACY_PROFILE = AppleRouteHostProfile(
    profile_id="github-macos26-20260728.0273.1",
    image_version="20260728.0273.1",
    product_version="26.5.2",
    build_version="25F84",
    xcode=_EXPECTED_XCODE,
    macos_sdk=_EXPECTED_MACOS_SDK,
    clang_sha256="d2e4bf622758eee1bf7267c060497fb2c41e098d37b0fca8be73898dc7e14eda",
    swiftc_sha256="8a63cc031d970b57f03741ae83becbfb26f2b913565ac212b81b80bdcb35600f",
    component_overrides=(
        ("swift-dispatcher", "8a63cc031d970b57f03741ae83becbfb26f2b913565ac212b81b80bdcb35600f", 357_109_680),
        ("swiftc-dispatcher", "8a63cc031d970b57f03741ae83becbfb26f2b913565ac212b81b80bdcb35600f", 357_109_680),
        ("swift-build-dispatcher", "487af88e37990b089e4979b874bd7944aca0dba5ffb0cae6236aefd02b301f05", 48_459_440),
        ("swift-package", "487af88e37990b089e4979b874bd7944aca0dba5ffb0cae6236aefd02b301f05", 48_459_440),
        ("swift-driver", "65b741dd6274318d08d8d510b48b56fc718af418adc20c3913f68aea4b4e4d42", 6_305_152),
        ("swift-frontend", "8a63cc031d970b57f03741ae83becbfb26f2b913565ac212b81b80bdcb35600f", 357_109_680),
        ("clang", "d2e4bf622758eee1bf7267c060497fb2c41e098d37b0fca8be73898dc7e14eda", 290_664_032),
        ("clangxx-dispatcher", "d2e4bf622758eee1bf7267c060497fb2c41e098d37b0fca8be73898dc7e14eda", 290_664_032),
        ("linker", "e412b9f2af31b1567a9eabc28f553a8f1cf34127e2107cb39c2694cf147571a4", 4_953_232),
        ("archiver", "796d3d310da783252c83ae4a9a9f3c5c92dba0747bb81de3753ce61809be6947", 139_056),
        ("libtool", "0d41e97fd26c5dd2a268ddb1a5c07b7f8f9e6f0cd28922d92b5b19aec7c42849", 440_176),
        ("platform-swift-plugin-server", "7a9c12f5b6c5ad40f26b9e0e7767967cb7bd192a91532c4b915c0c01369e3e03", 137_056),
        ("in-process-plugin-server", "37b37b1eb1354c870910187fb3ac42414805da941c302f00d9be0b1017eb8eba", 173_344),
        ("swift-driver-library", "31136107cf83f639540d698016d69c861231d4282ea93ded7353e614a7c3b15c", 6_340_944),
        ("swift-tools-support-library", "728890c1f2e5fefd564247f1b5a350a441a26285d7c234b46f50819608ff3020", 2_419_296),
        ("build-server-protocol", "a05648ca25c2db07f4c2af84abd8eeb11c8debe76b8b5f8ffb68be2324c6a7f5", 963_248),
        ("language-server-protocol", "3593be35263b82a0cdd4a31ffcd77ba8fe9433aced80913b8a03bb78ab53a785", 5_343_632),
        (
            "language-server-protocol-transport",
            "bdc80c99e955ed599e1da3f4fdd1ec67aa5c7d58e504bb949070635e0aee6e8f",
            516_624,
        ),
        ("swb-build-service", "67e6b1bbcf34059fca5fa467f3b738a8c0823f28122ebfea719ce3e28c2f6e1c", 2_837_056),
        ("swb-project-model", "ac3bc1eb2eb6643b392d2bae16c818dca505a434586a25a13eeee1c18dde53bb", 1_113_584),
        ("swb-util", "92b7dcda84db6891a4f48bed7289750ff8481c270d6da8f2b8de1fcf01720218", 6_440_816),
        ("swift-build-framework", "fafeefff64776545195c6e41356ee76422ce2a66a0b64d796bb487677df08aa3", 6_935_776),
        (
            "tools-protocols-swift-extensions",
            "689e9f1c1ca838af83cc75bbf451b83f84d8bc3bfb5830c0e5d85a26d3f925c4",
            396_432,
        ),
        ("llbuild-framework", "0322414740fb02dd9f0bc0e238bd251d5dc9e58af43660eec7f5f0664ceb1b03", 2_890_784),
    ),
    tree_overrides=(
        ("toolchain-host-plugins", "4fa83d7d2c0246c4fbe83cc8d71fe26b8beacc27f2a650fb0945d23de0eacbcc", 4, 3_222_976),
        ("platform-host-plugins", "8d1463ff558fa7cdc81daabf20855fa6878e27716ca4874adf5f37824d2494ed", 15, 10_106_220),
    ),
    apple_git_sha256="e68bc9395203d8e1be47b98c374df67ccb45732379a9fdba94b56d861e5f648f",
    apple_git_bytes=7_604_272,
    sandbox_exec_sha256="8290e4be7387a0df83cd1559e86afd880464f269450573d012795761fe298f16",
    sandbox_exec_cdhash_full="2f619ca893522eb88a87dc31ddc1e8cad98f237d4672f6f9d0c9f05395572463",
    sandbox_exec_bytes=102_560,
    codesign_sha256="214d455584d19abc0d74d02b9cbc7d3da6bdcb0596c235e6156dd9ed2f4e1ba7",
    codesign_bytes=459_824,
)

_APPLE_ROUTE_HOST_PROFILES = (
    _APPLE_ROUTE_LEGACY_PROFILE,
    _APPLE_ROUTE_CURRENT_PROFILE,
)


def _select_apple_route_host_profile(
    *,
    image_version: str,
    product_version: str,
    build_version: str,
    xcode: str,
) -> AppleRouteHostProfile:
    matches = tuple(
        profile
        for profile in _APPLE_ROUTE_HOST_PROFILES
        if (
            profile.product_version,
            profile.build_version,
            profile.xcode,
        )
        == (product_version, build_version, xcode)
        and (not image_version or profile.image_version == image_version)
    )
    if len(matches) != 1:
        observed = "/".join(
            (image_version, product_version, build_version, xcode.replace("\n", "/"))
        )
        raise RouteError(f"EXACT_TOOLCHAIN_APPLE_HOST_PROFILE_MISMATCH:observed={observed}")
    return matches[0]


@cache
def apple_route_host_profile(language: Language) -> AppleRouteHostProfile:
    """Select one complete Apple closure; never accept per-file alternatives."""

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            f"EXACT_TOOLCHAIN_PLATFORM_MISMATCH:{language}:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    xcodebuild = Path("/usr/bin/xcodebuild")
    xcrun = Path("/usr/bin/xcrun")
    if not xcodebuild.is_file() or not xcrun.is_file():
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:xcodebuild/xcrun")
    observed_xcode = _output([str(xcodebuild), "-version"], include_stderr=False)
    image_version = os.environ.get("ImageVersion", "").strip()
    if image_version:
        required_environment = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_ENVIRONMENT": "github-hosted",
            "ImageOS": "macos26",
            "ELMOS_APPLE_ROUTE_XCODE_SEALED": "1",
            "ELMOS_APPLE_ROUTE_XCODE_PHYSICAL": "/Applications/Xcode.app",
        }
        drift = tuple(
            key
            for key, expected in required_environment.items()
            if os.environ.get(key, "").strip() != expected
        )
        if drift:
            raise RouteError(
                "EXACT_TOOLCHAIN_APPLE_HOST_PROVENANCE_MISMATCH:" + ",".join(drift)
            )
    product_version = _output(["/usr/bin/sw_vers", "-productVersion"], include_stderr=False)
    build_version = _output(["/usr/bin/sw_vers", "-buildVersion"], include_stderr=False)
    selected = _select_apple_route_host_profile(
        image_version=image_version,
        product_version=product_version,
        build_version=build_version,
        xcode=observed_xcode,
    )
    sdk_version = _output(
        [str(xcrun), "--sdk", "macosx", "--show-sdk-version"],
        include_stderr=False,
    )
    sdk_path = Path(
        _output(
            [str(xcrun), "--sdk", "macosx", "--show-sdk-path"],
            include_stderr=False,
        )
    )
    if sdk_version != selected.macos_sdk:
        raise RouteError(
            f"EXACT_TOOLCHAIN_APPLE_PROFILE_MISMATCH:{language}:"
            f"expected={selected.xcode.replace(chr(10), '/')}/sdk={selected.macos_sdk}:"
            f"observed={observed_xcode.replace(chr(10), '/')}/sdk={sdk_version}"
        )
    foundation = sdk_path / "System/Library/Frameworks/Foundation.framework/Headers/Foundation.h"
    objc_runtime = sdk_path / "usr/include/objc/objc.h"
    if sdk_path.name != "MacOSX26.5.sdk" or not foundation.is_file() or not objc_runtime.is_file():
        raise RouteError(f"EXACT_TOOLCHAIN_APPLE_SDK_INCOMPLETE:{language}:{sdk_path}")
    return selected


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
    selected = apple_route_host_profile(language)
    return (
        "platform=Darwin/arm64",
        f"apple-host-profile={selected.profile_id}",
        "xcode=26.6/17F113",
        "macosx-sdk=26.5",
        "sdk-path=/Applications/Xcode.app/Contents/Developer/Platforms/"
        "MacOSX.platform/Developer/SDKs/MacOSX26.5.sdk",
    )


def _clang(language: Language, executable_name: str) -> ExactToolchain:
    selected = apple_route_host_profile(language)
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
    if observed != expected or executable_digest != selected.clang_sha256:
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:{language}:expected={expected}/sha256={selected.clang_sha256}:"
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
    selected = apple_route_host_profile("swift")
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
        or executable_digest != selected.swiftc_sha256
        or driver_digest != selected.swiftc_sha256
        or driver_version != "\n".join((expected, _EXPECTED_SWIFT_TARGET, _EXPECTED_SWIFT_DRIVER_VERSION))
    ):
        raise RouteError(
            f"EXACT_TOOLCHAIN_MISMATCH:swift:expected={expected}/{_EXPECTED_SWIFT_TARGET}/"
            f"swiftc-sha256={selected.swiftc_sha256}/swift-driver-sha256={selected.swiftc_sha256}:"
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
_EXPECTED_PHP_ROOT = _EXPECTED_HOMEBREW_CELLAR / "php/8.5.9"
_EXPECTED_PHP_ANCHOR = _EXPECTED_HOMEBREW_CELLAR / "php"
_EXPECTED_PHP_EXECUTABLE = _EXPECTED_PHP_ROOT / "bin" / "php"
_EXPECTED_PHP_EXECUTABLE_SHA256 = '6e52a2c84ff356bfc670809b7b5923a05aa64b3c8bcdb6c4a9a6b257c3435218'
_EXPECTED_PHP_EXECUTABLE_BYTES = 23795728
_EXPECTED_PHP_TREE_SHA256 = '8c4459ea3d6603c87b85ca6c07fac8d255180f4404b59c3b778230edacd7fb0f'
_EXPECTED_PHP_TREE_RECORD_COUNT = 643
_EXPECTED_PHP_TREE_FILE_COUNT = 532
_EXPECTED_PHP_TREE_DIRECTORY_COUNT = 109
_EXPECTED_PHP_TREE_BYTES = 129952837
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
        if relative == "INSTALL_RECEIPT.json":
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RouteError(failure) from error
            if not isinstance(receipt, dict) or type(receipt.get("time")) is not int:
                raise RouteError(failure)
            # These fields identify the disposable installer invocation, not
            # the immutable bottle. Every bottle/source/dependency, target,
            # architecture, build-host and option field remains hash-bound.
            receipt["time"] = "<installation-time>"
            receipt["homebrew_version"] = "<homebrew-client-version>"
            normalized = json.dumps(
                receipt, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            record = {
                **record,
                "bytes": len(normalized),
                "sha256": hashlib.sha256(normalized).hexdigest(),
            }
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
        raise RouteError(
            "EXACT_TOOLCHAIN_PHP_TREE_MISMATCH:expected="
            + json.dumps(expected, sort_keys=True, separators=(",", ":"))
            + ":observed="
            + json.dumps(identity, sort_keys=True, separators=(",", ":"))
        )
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


# ---------------------------------------------------------------------------
# Kotlin
#
# Pinned as a plain versioned tree the way Go is -- a fixed root, a whole-tree
# manifest of it, file records for the parts a human would need named, and a
# before/after sandwich around the one subprocess the probe runs. Three things
# make it not simply Go with different constants:
#
#   * The tree is walked with `php_tree_identity`, not `_qualified_tree_manifest`.
#     Go and Rust are extracted tarballs of plain files, so the symlink-free
#     contract fits them; a Kotlin distribution laid down by Homebrew or npm
#     links its `bin` entries and sometimes a jar at a versioned sibling, and a
#     rule no real install satisfies is not a strict rule but an unusable one.
#     Links are therefore recorded into the identity rather than refused, and
#     repointing one is drift even when no file's content changed.
#   * An escaping link under `lib/`, or to anything named `*.jar`, is refused
#     outright. `php_tree_identity` refuses an escaping link only when it lands
#     on a `.so`/`.dylib`/`.bundle`, which is the whole rule for a C interpreter
#     and half of it for a JVM one: a jar on the compiler classpath is loadable
#     code exactly as much as a dylib is, and everything under `lib/` is on that
#     classpath by construction. `tools/pin_kotlin_toolchain.py` refuses to emit
#     a pin for such a tree, and the gate has to refuse to accept one, or the
#     pinning script would be stricter than the check it feeds -- meaning a pin
#     hand-edited or carried over from another host could pass a gate its own
#     generator would have rejected.
#   * The JVM is bound explicitly. `bin/kotlinc` and `bin/kotlin` are shell
#     scripts whose entire job is to exec a `java` they locate at run time --
#     `$JAVA_HOME/bin/java` if that is set, otherwise whatever `java` PATH
#     resolves to. Every digest in this block describes bytes that are *input*
#     to that JVM; none of them describes the JVM. Leave it unbound and an
#     "exact toolchain" claim reduces to "these jars, run by some Java" -- and
#     the JVM is not a neutral carrier for those jars. It fixes the bytecode
#     verifier, the class-file versions accepted, `strictfp`/FMA behaviour, the
#     default charset used to read sources, and the `java.*` implementations the
#     stdlib delegates to; a route's recorded evidence would then be reproducible
#     on paper and not on any second machine. This engine already pins a JDK for
#     `_java`, so the honest binding is that same one, reused rather than
#     re-derived: `_kotlin_jvm_binding` calls `_java()` and takes the home and
#     the `release` digest out of the toolchain `_java` returns, so the JDK
#     behind Kotlin is the JDK the Java route already verified -- digests of
#     `java`, `javac`, `lib/modules`, `lib/server/libjvm.dylib` and `release`,
#     plus the bundle's codesign identity -- and it cannot drift apart from it.
#     Both facts are surfaced in the profile (`kotlin-jvm-home`,
#     `kotlin-jvm-release-sha256`) so a route's evidence names the pair.
#
# The `_EXPECTED_KOTLIN_*` constants below are machine-specific, the same way
# `_EXPECTED_PHP_TREE_SHA256` and `_EXPECTED_GO_TREE_SHA256` are. Run
# `tools/pin_kotlin_toolchain.py` on the pinning host and paste its output here;
# the script emits exactly this block, with these names and these types. Until
# they are pinned the probe fails closed with EXACT_TOOLCHAIN_KOTLIN_NOT_PINNED
# rather than accepting whatever `kotlinc` happens to be on PATH.
_KOTLIN_VERSION_VARIABLE = "ELMOS_KOTLIN_VERSION"
_EXPECTED_KOTLIN_VERSION_BY_JAVA_DISTRIBUTION = {
    "homebrew": "kotlinc-jvm 2.2.20 (JRE 21.0.11)",
    "temurin": "kotlinc-jvm 2.2.20 (JRE 21.0.11+10-LTS)",
}


def configured_polyglot_toolchain_root() -> Path:
    """Return the exact shared route/synthesis toolchain installation root."""

    project = os.environ.get("ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT", "").strip()
    route = os.environ.get("ELMOS_POLYGLOT_ROUTE_TOOLCHAIN_ROOT", "").strip()
    if project and route and project != route:
        raise RouteError("EXACT_TOOLCHAIN_ROOT_CONFLICT")
    candidate = Path(route or project or "~/.local/share/elmos/toolchains").expanduser()
    normalized = Path(os.path.normpath(str(candidate)))
    if (
        not candidate.is_absolute()
        or candidate != normalized
        or candidate in {Path("/"), Path.home()}
    ):
        raise RouteError(f"EXACT_TOOLCHAIN_ROOT_UNSAFE:{candidate}")
    return candidate


_EXPECTED_KOTLIN_ANCHOR = configured_polyglot_toolchain_root() / "kotlin"
_EXPECTED_KOTLIN_ROOT = _EXPECTED_KOTLIN_ANCHOR / "2.2.20"
_EXPECTED_KOTLINC_EXECUTABLE = _EXPECTED_KOTLIN_ROOT / "bin" / "kotlinc"
_EXPECTED_KOTLINC_EXECUTABLE_SHA256 = "90750c977cc043dd2b05c69dd4e052c10377554925dd5a155e74ef732be28c7d"
_EXPECTED_KOTLINC_EXECUTABLE_BYTES = 3120
_EXPECTED_KOTLIN_COMPILER_JAR = _EXPECTED_KOTLIN_ROOT / "lib" / "kotlin-compiler.jar"
_EXPECTED_KOTLIN_COMPILER_JAR_SHA256 = "8546feb440ec2d59e00d475936523fcd3f528e21c7e8eb8a95e6de5044a6d496"
_EXPECTED_KOTLIN_COMPILER_JAR_BYTES = 58338619
_EXPECTED_KOTLIN_STDLIB_JAR = _EXPECTED_KOTLIN_ROOT / "lib" / "kotlin-stdlib.jar"
_EXPECTED_KOTLIN_STDLIB_JAR_SHA256 = "8836ccffd3585fadda9901244b20d42901d2f3cd581058d8434e2ffabcf3a3e7"
_EXPECTED_KOTLIN_STDLIB_JAR_BYTES = 1761444
_EXPECTED_KOTLIN_TREE_SHA256 = "0f6e2cea7d2dd94f63e84a3f4be5c8252cb3a53f2abbd19fa4165fc2665082b8"
_EXPECTED_KOTLIN_TREE_RECORD_COUNT = 123
_EXPECTED_KOTLIN_TREE_FILE_COUNT = 118
_EXPECTED_KOTLIN_TREE_DIRECTORY_COUNT = 5
_EXPECTED_KOTLIN_TREE_BYTES = 85861305
#: Symlinks whose target resolves *inside* the install root, as name -> raw link
#: text. Part of the tree's identity for the same reason PHP's are: the link is
#: what the distribution ships, and repointing one is drift.
_EXPECTED_KOTLIN_TREE_SYMLINKS: dict[str, str] = {}
#: Symlinks whose target resolves *outside* the install root. Their content is
#: NOT bound by this pin, which is why they are recorded separately instead of
#: folded in and implied otherwise. Pinning the exact set is what keeps the
#: admission honest: if a future distribution adds an escaping link, the set
#: changes and the probe fails rather than quietly widening what is unbound.
#: `_kotlin_classpath_binding` additionally refuses any entry here that is under
#: `lib/` or names a jar -- those are not merely unbound, they are unbindable.
_EXPECTED_KOTLIN_TREE_UNBOUND_SYMLINKS: dict[str, str] = {}
#: Contents of `build.txt`: Kotlin's own build identity, and the one field that
#: separates two distributions reporting the same marketing version.
_EXPECTED_KOTLIN_BUILD_NUMBER = "2.2.20-release-333"
#: `bin/kotlin`, the runtime launcher, reported as the toolchain's auxiliary
#: executable. It gets no digest constant of its own because the pin script
#: emits none: its bytes are covered by the tree manifest like every other file
#: under the root, and a second digest pinned in two places is a second thing to
#: keep in sync. `auxiliary_sha256` is therefore left unset rather than filled
#: from an observed read, which would look like a pin without being one.
_EXPECTED_KOTLIN_LAUNCHER = _EXPECTED_KOTLIN_ROOT / "bin" / "kotlin"


def _kotlin_classpath_binding() -> None:
    """Refuse a pin whose compiler classpath leaves the tree.

    Exactly the rule `tools/pin_kotlin_toolchain.py::_unbound_classpath_links`
    applies before it will emit a block, restated here because the generator and
    the gate must not be able to disagree: a pin produced elsewhere, or edited by
    hand, must fail the same way the generator would have refused to produce it.

    Distinct code from the tree mismatch on purpose. "The set of unbound links
    changed" and "a jar the compiler loads is not covered by this pin at all" are
    different problems with different fixes, and collapsing them would make the
    second read as ordinary drift.
    """
    escaping = sorted(
        (name, target)
        for name, target in _EXPECTED_KOTLIN_TREE_UNBOUND_SYMLINKS.items()
        if name.startswith("lib/") or name.endswith(".jar")
    )
    if escaping:
        raise RouteError(
            "EXACT_TOOLCHAIN_KOTLIN_CLASSPATH_UNBOUND:"
            + ",".join(f"{name}->{target}" for name, target in escaping)
        )


def _kotlin_tree_identity() -> dict[str, object]:
    identity = php_tree_identity(
        _EXPECTED_KOTLIN_ROOT,
        _EXPECTED_KOTLIN_ANCHOR,
        "EXACT_TOOLCHAIN_KOTLIN_TREE_UNSAFE",
    )
    expected = {
        "root": str(_EXPECTED_KOTLIN_ROOT),
        "sha256": _EXPECTED_KOTLIN_TREE_SHA256,
        "record_count": _EXPECTED_KOTLIN_TREE_RECORD_COUNT,
        "file_count": _EXPECTED_KOTLIN_TREE_FILE_COUNT,
        "directory_count": _EXPECTED_KOTLIN_TREE_DIRECTORY_COUNT,
        "bytes": _EXPECTED_KOTLIN_TREE_BYTES,
        "symlinks": _EXPECTED_KOTLIN_TREE_SYMLINKS,
        "unbound_symlinks": _EXPECTED_KOTLIN_TREE_UNBOUND_SYMLINKS,
    }
    if identity != expected:
        raise RouteError("EXACT_TOOLCHAIN_KOTLIN_TREE_MISMATCH")
    return identity


def _kotlin_file_records() -> tuple[dict[str, str | int], ...]:
    """Records for the launcher, the compiler jar and the stdlib jar.

    All three are inside the tree digest already. They are read again by name so
    that a swapped `lib/kotlin-compiler.jar` fails with that path in the error
    rather than as one changed record out of several thousand, and so that the
    before/after sandwich has something cheap to re-read around the subprocess
    without walking the whole tree twice for the parts that matter most.
    """
    return (
        _qualified_file_record(
            _EXPECTED_KOTLINC_EXECUTABLE,
            _EXPECTED_KOTLIN_ROOT,
            "EXACT_TOOLCHAIN_KOTLIN_EXECUTABLE_UNSAFE",
        ),
        _qualified_file_record(
            _EXPECTED_KOTLIN_COMPILER_JAR,
            _EXPECTED_KOTLIN_ROOT,
            "EXACT_TOOLCHAIN_KOTLIN_COMPILER_JAR_UNSAFE",
        ),
        _qualified_file_record(
            _EXPECTED_KOTLIN_STDLIB_JAR,
            _EXPECTED_KOTLIN_ROOT,
            "EXACT_TOOLCHAIN_KOTLIN_STDLIB_JAR_UNSAFE",
        ),
    )


def _kotlin_build_number() -> str:
    """`build.txt`, checked against the pin.

    Read after the tree manifest so the bytes quoted into the profile are bytes
    the tree digest already covers, rather than a second unbound read of the same
    path. The value is the distribution's own build identity: two Kotlin releases
    can print the same `kotlinc -version` banner and carry different build
    numbers, so this is checked by value in addition to being inside the digest.
    """
    try:
        observed = (_EXPECTED_KOTLIN_ROOT / "build.txt").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_KOTLIN_BUILD_NUMBER_UNREADABLE") from error
    if observed != _EXPECTED_KOTLIN_BUILD_NUMBER:
        raise RouteError(
            f"EXACT_TOOLCHAIN_KOTLIN_BUILD_NUMBER_MISMATCH:"
            f"expected={_EXPECTED_KOTLIN_BUILD_NUMBER}:observed={observed}"
        )
    return observed


def _kotlin_jvm_binding() -> tuple[Path, str]:
    """The JDK `kotlinc` will run under, taken from the JDK this engine already pins.

    `_java()` is called rather than `_EXPECTED_JAVA_HOME` being re-read here, and
    the difference is not stylistic. `_java` verifies the home resolves, that any
    declared `ELMOS_JAVA21_HOME` agrees with it, the digests of `java`, `javac`,
    `lib/modules`, `lib/server/libjvm.dylib` and `release`, both version banners
    and the bundle's codesign identity. Re-deriving the path here would bind the
    *location* of a JDK while inheriting none of that, and would let the Java
    route and the Kotlin route drift onto different JVMs while both still claimed
    to be exact.

    Returns the home and the `release` digest. `release` is the file that names
    the build -- version, build number, target platform, source revision -- so its
    digest is the shortest honest way for a Kotlin route's evidence to identify
    which JVM produced it.
    """
    try:
        jdk = _java()
    except RouteError as error:
        raise RouteError(f"EXACT_TOOLCHAIN_KOTLIN_JVM_UNPINNED:{error}") from error

    def profile_value(prefix: str) -> str:
        matches = [item[len(prefix):] for item in jdk.profile if item.startswith(prefix)]
        if len(matches) != 1:
            raise RouteError(f"EXACT_TOOLCHAIN_KOTLIN_JVM_UNPINNED:{prefix}")
        return matches[0]

    home = Path(profile_value("jdk-home="))
    release_digest = profile_value("release-sha256=")
    # The home is the parent of the launcher `_java` itself verified; if those two
    # ever disagree the profile is describing a different JDK from the one whose
    # digests were checked, and neither is then trustworthy.
    if Path(jdk.executable) != home / "bin" / "java" or not release_digest:
        raise RouteError(f"EXACT_TOOLCHAIN_KOTLIN_JVM_UNPINNED:{home}")
    return home, release_digest


def _kotlin_version_contract() -> tuple[str, str]:
    """Select the one exact Kotlin banner for the already pinned JDK distribution."""
    distribution = os.environ.get("ELMOS_JAVA21_DISTRIBUTION", "").strip().lower()
    if not distribution:
        distribution = "homebrew"
    expected = _EXPECTED_KOTLIN_VERSION_BY_JAVA_DISTRIBUTION.get(distribution)
    if expected is None:
        raise RouteError(
            "EXACT_TOOLCHAIN_KOTLIN_JVM_DISTRIBUTION_UNSUPPORTED:"
            f"{distribution}"
        )
    return distribution, expected


def _kotlin_version_banner(jvm_home: Path) -> str:
    """The `kotlinc -version` banner, run against the pinned JDK.

    Not `_output`, for three reasons that are all specific to this launcher.

    `kotlinc` prints its banner on *stderr* with an `info: ` prefix, and exits
    non-zero on builds that treat "no source files" as an error -- so the exit
    code is not the signal and `_output`'s "non-zero means unavailable" rule would
    reject a perfectly good compiler. The banner line's presence is the signal;
    its absence is the failure, and the exit code is reported with it because
    "no banner, exit 1" and "no banner, exit 0" are different faults.

    stdin is closed. A `kotlinc` that fails to parse its arguments falls through
    to the REPL, which on an inherited terminal would block until the 30-second
    `_output` timeout instead of failing.

    The JDK is bound two ways, deliberately redundantly, because the launcher
    picks its JVM with `${JAVA_HOME}/bin/java` if that is set and a bare `java`
    otherwise: `JAVA_HOME` is set to the pinned home, and the pinned home's `bin`
    is put first on PATH so even a launcher that ignores `JAVA_HOME` cannot reach
    `/usr/bin/java`. `sanitized_subprocess_env` drops the ambient environment
    entirely, so this is additive, not an override of the caller's intent.

    The timeout matches the pin script's rather than `_output`'s 30 seconds: a
    cold JVM loading a ~60MB compiler jar is not fast, and a gate that timed out
    where the generator did not would refuse pins it had just produced.
    """
    command = [str(_EXPECTED_KOTLINC_EXECUTABLE), "-version"]
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-toolchain-env-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            environment = sanitized_subprocess_env(
                home=home,
                temp_dir=scratch,
                executable_dirs=(jvm_home / "bin", _EXPECTED_KOTLINC_EXECUTABLE.parent),
            )
            environment["JAVA_HOME"] = str(jvm_home)
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
                stdin=subprocess.DEVNULL,
                env=environment,
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(f"EXACT_TOOLCHAIN_UNAVAILABLE:{command[0]}") from error
    printed = f"{completed.stderr}{completed.stdout}"
    for line in printed.splitlines():
        candidate = line.strip().removeprefix("info:").strip()
        if candidate.startswith("kotlinc"):
            return candidate
    raise RouteError(f"EXACT_TOOLCHAIN_KOTLIN_VERSION_BANNER_MISSING:returncode={completed.returncode}")


def _kotlin() -> ExactToolchain:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:kotlin:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    if not (
        _EXPECTED_KOTLIN_VERSION_BY_JAVA_DISTRIBUTION
        and _EXPECTED_KOTLINC_EXECUTABLE_SHA256
        and _EXPECTED_KOTLIN_COMPILER_JAR_SHA256
        and _EXPECTED_KOTLIN_STDLIB_JAR_SHA256
        and _EXPECTED_KOTLIN_TREE_SHA256
        and _EXPECTED_KOTLIN_BUILD_NUMBER
    ):
        # An unpinned digest must never degrade to "trust whatever is there".
        raise RouteError(
            "EXACT_TOOLCHAIN_KOTLIN_NOT_PINNED:run tools/pin_kotlin_toolchain.py on the pinning host"
        )
    _kotlin_classpath_binding()
    jvm_home, jvm_release_digest = _kotlin_jvm_binding()
    jvm_distribution, repository_version = _kotlin_version_contract()
    expected_version = _pinned(_KOTLIN_VERSION_VARIABLE, "kotlin", repository_version)
    tree_before = _kotlin_tree_identity()
    records_before = _kotlin_file_records()
    build_number = _kotlin_build_number()
    observed = _kotlin_version_banner(jvm_home)
    records_after = _kotlin_file_records()
    tree_after = _kotlin_tree_identity()
    executable_after, compiler_after, stdlib_after = records_after
    if (
        observed != expected_version
        or records_before != records_after
        or executable_after.get("sha256") != _EXPECTED_KOTLINC_EXECUTABLE_SHA256
        or executable_after.get("bytes") != _EXPECTED_KOTLINC_EXECUTABLE_BYTES
        or compiler_after.get("sha256") != _EXPECTED_KOTLIN_COMPILER_JAR_SHA256
        or compiler_after.get("bytes") != _EXPECTED_KOTLIN_COMPILER_JAR_BYTES
        or stdlib_after.get("sha256") != _EXPECTED_KOTLIN_STDLIB_JAR_SHA256
        or stdlib_after.get("bytes") != _EXPECTED_KOTLIN_STDLIB_JAR_BYTES
        or tree_before != tree_after
    ):
        raise RouteError(f"EXACT_TOOLCHAIN_MISMATCH:kotlin:expected={expected_version}:observed={observed}")
    return ExactToolchain(
        "kotlin",
        observed,
        str(_EXPECTED_KOTLINC_EXECUTABLE),
        str(_EXPECTED_KOTLIN_LAUNCHER),
        profile=(
            "kotlin-toolchain-closure-schema=v1",
            "platform=Darwin/arm64",
            f"kotlin-root={_EXPECTED_KOTLIN_ROOT}",
            f"kotlin-tree-sha256={tree_after['sha256']}",
            f"kotlin-tree-record-count={tree_after['record_count']}",
            f"kotlin-tree-file-count={tree_after['file_count']}",
            f"kotlin-tree-directory-count={tree_after['directory_count']}",
            f"kotlin-tree-bytes={tree_after['bytes']}",
            f"kotlin-tree-symlink-count={len(_EXPECTED_KOTLIN_TREE_SYMLINKS)}",
            f"kotlin-tree-unbound-symlink-count={len(_EXPECTED_KOTLIN_TREE_UNBOUND_SYMLINKS)}",
            *(
                f"kotlin-tree-unbound-symlink={name}->{target}"
                for name, target in sorted(_EXPECTED_KOTLIN_TREE_UNBOUND_SYMLINKS.items())
            ),
            f"kotlin-build-number={build_number}",
            f"kotlinc-sha256={executable_after['sha256']}",
            f"kotlin-compiler-jar-sha256={compiler_after['sha256']}",
            f"kotlin-stdlib-jar-sha256={stdlib_after['sha256']}",
            # The JVM the launcher will exec, and which build it is. Without these
            # two the rest of this profile describes bytes fed to an unnamed
            # interpreter, and `_toolchain_executable_dirs` has nothing to read to
            # put that JVM on PATH for the emit-time runs.
            f"kotlin-jvm-home={jvm_home}",
            f"kotlin-jvm-distribution={jvm_distribution}",
            f"kotlin-jvm-release-sha256={jvm_release_digest}",
            "integer=int64",
            "number=binary64",
            "kotlin-runtime-semantic-soundness=NOT_RUN",
        ),
        executable_sha256=_EXPECTED_KOTLINC_EXECUTABLE_SHA256,
    )


_EXPECTED_FLUTTER_ROOT = _EXPECTED_HOMEBREW_PREFIX / "share/flutter"
_EXPECTED_FLUTTER_EXECUTABLE = _EXPECTED_FLUTTER_ROOT / "bin" / "flutter"
_EXPECTED_FLUTTER_EXECUTABLE_SHA256 = "7d486c33b30a0cf1ea5146231c68bb8f966cdb4e087c5cd8b37e14513f536e7d"
_EXPECTED_FLUTTER_EXECUTABLE_BYTES = 2_385
_EXPECTED_FLUTTER_VERSION_FILE = _EXPECTED_FLUTTER_ROOT / "bin" / "cache" / "flutter.version.json"
_EXPECTED_FLUTTER_VERSION_FILE_SHA256 = "cd7d9dfc4e3c94acfd5b2c38b7afa6df2cb230843fdae864cec392a3a34d66ca"
_EXPECTED_FLUTTER_VERSION_FILE_BYTES = 559
_EXPECTED_FLUTTER_DART = _EXPECTED_FLUTTER_ROOT / "bin" / "cache" / "dart-sdk" / "bin" / "dart"
_EXPECTED_FLUTTER_DART_SHA256 = "657c6a1779596306b30c59e589762287ad75b5fd8f008c7873864622a8865152"
_EXPECTED_FLUTTER_DART_BYTES = 3_884_832
_EXPECTED_FLUTTER_VERSION_FIELDS = (
    "3.44.1",
    "924134a44c189315be2148659913dda1671cbe99",
    "c416acfeb8126e097f758c664aaa3da929e27da0",
    "3.12.1",
)
_EXPECTED_FLUTTER_DART_VERSION = (
    'Dart SDK version: 3.12.1 (stable) (Tue May 26 01:02:21 2026 -0700) on "macos_arm64"'
)

# Repository-build closure for the deliberately import-free pure-Dart subset
# emitted by the Flutter route. The AST frontend has a separate analyzer
# package closure in dart_analyzer.py. Repository assembly uses only the Dart
# SDK bundled inside the exact Flutter distribution; it does not invoke the
# ambient Flutter CLI/cache updater or claim Flutter framework/UI semantics.
_EXPECTED_FLUTTER_BUILD_CLOSURE_SCHEMA = "v1"
_EXPECTED_FLUTTER_DART_SDK_ROOT = _EXPECTED_FLUTTER_ROOT / "bin" / "cache" / "dart-sdk"
_EXPECTED_FLUTTER_DART_SDK_TREE_SHA256 = (
    "37a612c64172042f2386954429584d6c75edacff3097443d5b372ac5c9870f0e"
)
_EXPECTED_FLUTTER_DART_SDK_TREE_RECORD_COUNT = 1124
_EXPECTED_FLUTTER_DART_SDK_TREE_FILE_COUNT = 1012
_EXPECTED_FLUTTER_DART_SDK_TREE_DIRECTORY_COUNT = 112
_EXPECTED_FLUTTER_DART_SDK_TREE_BYTES = 607_877_856


def _expected_flutter_build_closure() -> dict[str, object]:
    return {
        "schema": _EXPECTED_FLUTTER_BUILD_CLOSURE_SCHEMA,
        "trees": {
            "dart_sdk": {
                "root": str(_EXPECTED_FLUTTER_DART_SDK_ROOT),
                "sha256": _EXPECTED_FLUTTER_DART_SDK_TREE_SHA256,
                "record_count": _EXPECTED_FLUTTER_DART_SDK_TREE_RECORD_COUNT,
                "file_count": _EXPECTED_FLUTTER_DART_SDK_TREE_FILE_COUNT,
                "directory_count": _EXPECTED_FLUTTER_DART_SDK_TREE_DIRECTORY_COUNT,
                "bytes": _EXPECTED_FLUTTER_DART_SDK_TREE_BYTES,
            },
        },
    }


def _flutter_build_closure_sha256() -> str:
    return hashlib.sha256(
        json.dumps(
            _expected_flutter_build_closure(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()


def _flutter_build_tree_identities() -> dict[str, dict[str, object]]:
    dart_sdk = _qualified_tree_manifest(
        _EXPECTED_FLUTTER_DART_SDK_ROOT,
        _EXPECTED_FLUTTER_ROOT,
        "EXACT_TOOLCHAIN_FLUTTER_DART_SDK_TREE_UNSAFE",
    )
    _verify_qualified_tree_manifest(
        dart_sdk,
        expected_root=_EXPECTED_FLUTTER_DART_SDK_ROOT,
        expected_sha256=_EXPECTED_FLUTTER_DART_SDK_TREE_SHA256,
        expected_record_count=_EXPECTED_FLUTTER_DART_SDK_TREE_RECORD_COUNT,
        expected_file_count=_EXPECTED_FLUTTER_DART_SDK_TREE_FILE_COUNT,
        expected_directory_count=_EXPECTED_FLUTTER_DART_SDK_TREE_DIRECTORY_COUNT,
        expected_bytes=_EXPECTED_FLUTTER_DART_SDK_TREE_BYTES,
        failure="EXACT_TOOLCHAIN_FLUTTER_DART_SDK_TREE_MISMATCH",
    )
    return {"dart_sdk": dart_sdk}


def _flutter() -> ExactToolchain:
    """Bind Flutter to its bundled Dart SDK before the AST frontend executes."""

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:flutter:expected=Darwin/arm64:"
            f"observed={platform.system()}/{platform.machine()}"
        )
    paths = (
        (_EXPECTED_FLUTTER_EXECUTABLE, _EXPECTED_FLUTTER_EXECUTABLE_BYTES, _EXPECTED_FLUTTER_EXECUTABLE_SHA256),
        (_EXPECTED_FLUTTER_DART, _EXPECTED_FLUTTER_DART_BYTES, _EXPECTED_FLUTTER_DART_SHA256),
        (
            _EXPECTED_FLUTTER_VERSION_FILE,
            _EXPECTED_FLUTTER_VERSION_FILE_BYTES,
            _EXPECTED_FLUTTER_VERSION_FILE_SHA256,
        ),
    )

    def bindings() -> tuple[dict[str, str | int], ...]:
        observed = tuple(
            _qualified_file_record(path, _EXPECTED_FLUTTER_ROOT, "EXACT_TOOLCHAIN_FLUTTER_CHANGED")
            for path, _, _ in paths
        )
        if any(
            record.get("bytes") != expected_bytes or record.get("sha256") != expected_digest
            for record, (_, expected_bytes, expected_digest) in zip(observed, paths, strict=True)
        ):
            raise RouteError("EXACT_TOOLCHAIN_FLUTTER_CHANGED")
        return observed

    before = bindings()
    try:
        version = json.loads(_EXPECTED_FLUTTER_VERSION_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_VERSION_INVALID") from error
    fields = (
        version.get("flutterVersion") if isinstance(version, dict) else None,
        version.get("frameworkRevision") if isinstance(version, dict) else None,
        version.get("engineRevision") if isinstance(version, dict) else None,
        version.get("dartSdkVersion") if isinstance(version, dict) else None,
    )
    observed_dart = _output([str(_EXPECTED_FLUTTER_DART), "--version"])
    after = bindings()
    if before != after or fields != _EXPECTED_FLUTTER_VERSION_FIELDS or observed_dart != _EXPECTED_FLUTTER_DART_VERSION:
        raise RouteError(
            "EXACT_TOOLCHAIN_MISMATCH:flutter:expected=Flutter-3.44.1/Dart-3.12.1:"
            f"observed={fields[0]}/{fields[3]}"
        )
    return ExactToolchain(
        "flutter",
        "Flutter 3.44.1 / Dart 3.12.1",
        str(_EXPECTED_FLUTTER_EXECUTABLE),
        str(_EXPECTED_FLUTTER_DART),
        profile=(
            "platform=Darwin/arm64",
            f"flutter-root={_EXPECTED_FLUTTER_ROOT}",
            f"flutter-revision={_EXPECTED_FLUTTER_VERSION_FIELDS[1]}",
            f"flutter-engine-revision={_EXPECTED_FLUTTER_VERSION_FIELDS[2]}",
            f"flutter-build-closure-schema={_EXPECTED_FLUTTER_BUILD_CLOSURE_SCHEMA}",
            f"flutter-build-closure-sha256={_flutter_build_closure_sha256()}",
            f"flutter-dart-sdk-tree-sha256={_EXPECTED_FLUTTER_DART_SDK_TREE_SHA256}",
            "dart-analyzer=10.1.0",
            "_fe_analyzer_shared=95.0.0",
            "repository-build=pure-dart-import-free",
            "flutter-ui-semantics=UNSUPPORTED",
        ),
        executable_sha256=_EXPECTED_FLUTTER_EXECUTABLE_SHA256,
        auxiliary_sha256=_EXPECTED_FLUTTER_DART_SHA256,
    )


def verify_flutter_build_toolchain(toolchain: ExactToolchain) -> dict[str, object]:
    """Freshly bind the bundled Dart SDK used by repository assembly.

    The base selector stays cheap enough for each AST lift. Repository assembly
    calls this stronger verifier immediately before and after analyze, compile,
    and execution. No Flutter CLI/cache updater or external package resolver is
    part of the bounded import-free build path.
    """

    if (
        toolchain.language != "flutter"
        or toolchain.auxiliary != str(_EXPECTED_FLUTTER_DART)
        or toolchain.executable != str(_EXPECTED_FLUTTER_EXECUTABLE)
        or toolchain != exact_toolchain("flutter")
    ):
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_BUILD_IDENTITY_MISMATCH")
    trees = _flutter_build_tree_identities()
    if toolchain != exact_toolchain("flutter"):
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_BUILD_CHANGED_DURING_VERIFICATION")
    profile_sha256 = hashlib.sha256(
        json.dumps(
            list(toolchain.profile),
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    return {
        "schema_version": 1,
        "kind": "elmos.flutter-dart-build-toolchain-receipt",
        "language": "flutter",
        "version": toolchain.version,
        "closure_sha256": _flutter_build_closure_sha256(),
        "profile_sha256": profile_sha256,
        "trees": trees,
    }


def flutter_build_command(toolchain: ExactToolchain, *arguments: str) -> list[str]:
    """Run the exact bundled Dart command for the pure-Dart Flutter subset.

    The caller never invokes ``bin/flutter`` or its mutable universal-cache
    updater. The complete Dart SDK is bound by
    ``verify_flutter_build_toolchain`` before and after the build.
    """

    if (
        toolchain.language != "flutter"
        or toolchain.auxiliary != str(_EXPECTED_FLUTTER_DART)
        or toolchain != exact_toolchain("flutter")
    ):
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_BUILD_IDENTITY_MISMATCH")
    if not arguments or any(not argument for argument in arguments):
        raise RouteError("EXACT_TOOLCHAIN_FLUTTER_BUILD_ARGUMENTS_INVALID")
    return [str(_EXPECTED_FLUTTER_DART), *arguments]


def _react() -> ExactToolchain:
    """Bind the React framework identity to Node, TS and package closure."""

    typescript = _typescript()
    # Lazy import avoids a module-initialization cycle: react_analyzer consumes
    # ExactToolchain, while this selector reuses its single package-closure
    # verifier only after toolchains.py has finished importing.
    from .react_analyzer import react_dependency_receipt

    receipt = react_dependency_receipt()
    portable = tuple(
        {key: value for key, value in identity.items() if key != "runtime_entry"}
        for identity in receipt
    )
    digest = hashlib.sha256(
        json.dumps(portable, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()
    return ExactToolchain(
        "react",
        "React 19.2.7 / React DOM 19.2.7 / TypeScript 5.9.2 / Node 26.0.0",
        typescript.executable,
        typescript.auxiliary,
        profile=(
            *typescript.profile,
            "react=19.2.7",
            "react-dom=19.2.7",
            "@types/react=19.1.10",
            "@types/react-dom=19.1.7",
            f"react-dependency-profile-sha256={digest}",
            "react-ui-semantics=UNSUPPORTED",
        ),
        executable_sha256=typescript.executable_sha256,
        auxiliary_sha256=typescript.auxiliary_sha256,
    )


def _toolchain_fingerprint() -> tuple[str, ...]:
    tsc = REPOSITORY_ROOT / "engines" / "frontend-client-engine" / "node_modules" / ".bin" / "tsc"
    try:
        tsc_stat = tsc.stat(follow_symlinks=True)
        tsc_identity = f"{tsc_stat.st_dev}:{tsc_stat.st_ino}:{tsc_stat.st_size}:{tsc_stat.st_mtime_ns}"
    except OSError:
        tsc_identity = "MISSING"
    return (
        os.environ.get("PATH", ""),
        os.environ.get("ELMOS_JAVA21_HOME", ""),
        os.environ.get("ELMOS_JAVA21_DISTRIBUTION", ""),
        os.environ.get("ELMOS_CLANG_HOME", ""),
        os.environ.get(_CLANG_VERSION_VARIABLE, ""),
        os.environ.get(_SWIFT_VERSION_VARIABLE, ""),
        tsc_identity,
    )


@lru_cache(maxsize=64)
def _cached_exact_toolchain(
    language: Language,
    _fingerprint: tuple[str, ...],
) -> ExactToolchain:
    selectors = {
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
        "kotlin": _kotlin,
        "react": _react,
        "flutter": _flutter,
    }
    try:
        selector = selectors[language]
    except KeyError as error:
        raise RouteError(f"EXACT_TOOLCHAIN_UNREGISTERED:{language}") from error
    return selector()


def clear_exact_toolchain_cache() -> None:
    _cached_exact_toolchain.cache_clear()


def exact_toolchain(language: Language) -> ExactToolchain:
    """Resolve one language's pinned toolchain, or fail with a code.

    A language absent from this table has no pinned toolchain at all, which
    is a property of the engine rather than of the machine asking: it cannot
    be a source anywhere. Letting the bare `KeyError` escape made that read
    as an internal fault at every call site -- and it is the one dict lookup
    in this package that did not convert. `emitter._type`,
    `identifier_hygiene.policy_for_language` and the pipeline's own lookup
    all raise a coded `RouteError` here.
    """
    return _cached_exact_toolchain(language, _toolchain_fingerprint())
