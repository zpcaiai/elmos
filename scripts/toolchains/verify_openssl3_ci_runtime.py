#!/usr/bin/env python3
"""Verify the exact hosted OpenSSL 3 runtime used by frontend formal gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Final


OPENSSL: Final = Path("/opt/homebrew/Cellar/openssl@3/3.6.3/bin/openssl")
LIBSSL: Final = Path("/opt/homebrew/Cellar/openssl@3/3.6.3/lib/libssl.3.dylib")
LIBCRYPTO: Final = Path(
    "/opt/homebrew/Cellar/openssl@3/3.6.3/lib/libcrypto.3.dylib"
)
EXPECTED_VERSION: Final = (
    "OpenSSL 3.6.3 9 Jun 2026 (Library: OpenSSL 3.6.3 9 Jun 2026)"
)
EXPECTED_IMAGE: Final = ("macos15", "20260829.0321.1")
EXPECTED_MACOS_PRODUCT_VERSION: Final = "15.7.9"
EXPECTED_MACOS_BUILD_VERSION: Final = "24G830"
OPT_LINK: Final = Path("/opt/homebrew/opt/openssl@3")
OPT_LINK_TARGET: Final = "../Cellar/openssl@3/3.6.3"

UNSEALED_DIRECTORY_PROFILES: Final = {
    Path("/opt"): {"mode": "0755", "uid": 0, "gid": 0},
    # github-actions macos-15 image 20260829.0321.1 exposes the Homebrew
    # prefix itself as runner-owned but already non-group-writable.  Keep this
    # exact pre-seal identity separate from the root-owned post-seal profile.
    Path("/opt/homebrew"): {"mode": "0755", "uid": 501, "gid": 80},
    Path("/opt/homebrew/Cellar"): {"mode": "0775", "uid": 501, "gid": 80},
    Path("/opt/homebrew/Cellar/openssl@3"): {
        "mode": "0755",
        "uid": 501,
        "gid": 80,
    },
    Path("/opt/homebrew/Cellar/openssl@3/3.6.3"): {
        "mode": "0755",
        "uid": 501,
        "gid": 80,
    },
    Path("/opt/homebrew/Cellar/openssl@3/3.6.3/bin"): {
        "mode": "0755",
        "uid": 501,
        "gid": 80,
    },
    Path("/opt/homebrew/Cellar/openssl@3/3.6.3/lib"): {
        "mode": "0755",
        "uid": 501,
        "gid": 80,
    },
    Path("/opt/homebrew/opt"): {"mode": "0775", "uid": 501, "gid": 80},
}

SEALABLE_DIRECTORIES: Final = tuple(
    path for path in UNSEALED_DIRECTORY_PROFILES if path != Path("/opt")
)
SEALED_DIRECTORY_PROFILES: Final = {
    path: {"mode": "0755", "uid": 0, "gid": 0}
    for path in UNSEALED_DIRECTORY_PROFILES
}

UNSEALED_OPT_LINK_PROFILE: Final = {
    "mode": "0755",
    "uid": 501,
    "gid": 80,
    "nlink": 1,
    "target": OPT_LINK_TARGET,
}
SEALED_OPT_LINK_PROFILE: Final = {
    **UNSEALED_OPT_LINK_PROFILE,
    "uid": 0,
    "gid": 0,
}

UNSEALED_FILE_PROFILES: Final = {
    OPENSSL: {
        "role": "openssl",
        "mode": "0555",
        "uid": 501,
        "gid": 80,
        "nlink": 1,
        "bytes": 878_752,
        "sha256": "fac6e4f037e8e9c184485de80f23df3816c0c6d8428b20a7703b6f339a72a83c",
    },
    LIBSSL: {
        "role": "libssl",
        "mode": "0444",
        "uid": 501,
        "gid": 80,
        "nlink": 1,
        "bytes": 887_984,
        "sha256": "5f15ad8c8519304aad18b06105f367e21d75e0812eb300e904bb3b9271ce0d0d",
    },
    LIBCRYPTO: {
        "role": "libcrypto",
        "mode": "0444",
        "uid": 501,
        "gid": 80,
        "nlink": 1,
        "bytes": 4_870_832,
        "sha256": "256172ed0500c7af6f9d633b317fffe6efae0cae456eacc283a87cb2474317fb",
    },
}

FILE_PROFILES: Final = {
    path: {**profile, "uid": 0, "gid": 0}
    for path, profile in UNSEALED_FILE_PROFILES.items()
}

SIGNATURE_PROFILES: Final = {
    LIBSSL: {
        "Identifier=libssl.3",
        "Format=Mach-O thin (arm64)",
        "CodeDirectory v=20400 size=7073 flags=0x2(adhoc) hashes=216+2 location=embedded",
        "Hash type=sha256 size=32",
        "CandidateCDHashFull sha256=b2920ada65fae0087ed680e1cfc58c8e21a20a9a41cfc068ef4cff31eac43bd3",
        "CMSDigest=b2920ada65fae0087ed680e1cfc58c8e21a20a9a41cfc068ef4cff31eac43bd3",
        "CDHash=b2920ada65fae0087ed680e1cfc58c8e21a20a9a",
        "Signature=adhoc",
        "TeamIdentifier=not set",
        "Sealed Resources=none",
        "Internal requirements count=0 size=12",
    },
    LIBCRYPTO: {
        "Identifier=libcrypto.3",
        "Format=Mach-O thin (arm64)",
        "CodeDirectory v=20400 size=37924 flags=0x2(adhoc) hashes=1180+2 location=embedded",
        "Hash type=sha256 size=32",
        "CandidateCDHashFull sha256=30bbb115d12435513d93702de62223c174b521940829125684a5f0aa5e7f68d7",
        "CMSDigest=30bbb115d12435513d93702de62223c174b521940829125684a5f0aa5e7f68d7",
        "CDHash=30bbb115d12435513d93702de62223c174b52194",
        "Signature=adhoc",
        "TeamIdentifier=not set",
        "Sealed Resources=none",
        "Internal requirements count=0 size=12",
    },
}

DEPENDENCIES: Final = {
    OPENSSL: (
        str(LIBSSL),
        str(LIBCRYPTO),
        "/usr/lib/libSystem.B.dylib",
    ),
    LIBSSL: (
        "/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib",
        str(LIBCRYPTO),
        "/usr/lib/libSystem.B.dylib",
    ),
    LIBCRYPTO: (
        "/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib",
        "/usr/lib/libSystem.B.dylib",
    ),
}

DYLIB_IDS: Final = {
    LIBSSL: "/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib",
    LIBCRYPTO: "/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib",
}


def _run(command: list[str], *, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {command!r}: "
            f"{completed.stdout[-1000:]}{completed.stderr[-1000:]}"
        )
    return completed


def _directory_receipt(
    path: Path,
    expected: Mapping[str, object],
) -> dict[str, object]:
    before = path.lstat()
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise RuntimeError("host does not provide no-follow directory opens")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_NOFOLLOW
        | os.O_DIRECTORY,
    )
    try:
        opened = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = path.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    for observed in (opened, after):
        if identity != (
            observed.st_dev,
            observed.st_ino,
            observed.st_mode,
            observed.st_nlink,
            observed.st_uid,
            observed.st_gid,
            observed.st_size,
            observed.st_mtime_ns,
            observed.st_ctime_ns,
        ):
            raise RuntimeError(f"OpenSSL directory changed while inspected: {path}")
    if not stat.S_ISDIR(after.st_mode) or path.resolve(strict=True) != path:
        raise RuntimeError(f"OpenSSL authority path is not a direct directory: {path}")
    receipt: dict[str, object] = {
        "path": str(path),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "uid": after.st_uid,
        "gid": after.st_gid,
    }
    if receipt != {"path": str(path), **expected}:
        raise RuntimeError(f"OpenSSL directory identity mismatch: {receipt!r}")
    return {
        **receipt,
        "device": after.st_dev,
        "inode": after.st_ino,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
    }


def _directory_receipts(
    profiles: Mapping[Path, Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    return tuple(
        _directory_receipt(path, expected) for path, expected in profiles.items()
    )


def _opt_link_receipt(expected: Mapping[str, object]) -> dict[str, object]:
    before = OPT_LINK.lstat()
    target = os.readlink(OPT_LINK)
    after = OPT_LINK.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if identity != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_uid,
        after.st_gid,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise RuntimeError("OpenSSL opt symlink changed while inspected")
    if (
        not stat.S_ISLNK(after.st_mode)
        or OPT_LINK.resolve(strict=True)
        != Path("/opt/homebrew/Cellar/openssl@3/3.6.3")
    ):
        raise RuntimeError("OpenSSL opt link does not resolve to the pinned keg")
    receipt: dict[str, object] = {
        "path": str(OPT_LINK),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "uid": after.st_uid,
        "gid": after.st_gid,
        "nlink": after.st_nlink,
        "target": target,
    }
    if receipt != {"path": str(OPT_LINK), **expected}:
        raise RuntimeError(f"OpenSSL opt symlink identity mismatch: {receipt!r}")
    return {
        **receipt,
        "device": after.st_dev,
        "inode": after.st_ino,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
    }


def _secure_parent_chain(path: Path) -> None:
    cursor = Path(path.anchor)
    for component in path.parent.parts[1:]:
        cursor /= component
        expected = SEALED_DIRECTORY_PROFILES.get(cursor)
        if expected is None:
            raise RuntimeError(f"unprofiled OpenSSL parent directory: {cursor}")
        _directory_receipt(cursor, expected)
    if path.parent.resolve(strict=True) != path.parent:
        raise RuntimeError(f"OpenSSL parent directory resolves elsewhere: {path.parent}")


def _stable_file_receipt(
    path: Path,
    profiles: Mapping[Path, Mapping[str, object]] = FILE_PROFILES,
    *,
    validate_parent_chain: bool = True,
    validate_expected: bool = True,
) -> dict[str, object]:
    expected = profiles[path]
    if validate_parent_chain:
        _secure_parent_chain(path)
    before = path.lstat()
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("host does not provide no-follow file opens")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
    )
    try:
        opened_before = os.fstat(descriptor)
        digest = hashlib.sha256()
        total = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            total += len(chunk)
            if total > 8 * 1024 * 1024:
                raise RuntimeError(f"OpenSSL component exceeds safe read limit: {path}")
            digest.update(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = path.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    for observed in (opened_before, opened_after, after):
        if identity != (
            observed.st_dev,
            observed.st_ino,
            observed.st_mode,
            observed.st_nlink,
            observed.st_uid,
            observed.st_gid,
            observed.st_size,
            observed.st_mtime_ns,
            observed.st_ctime_ns,
        ):
            raise RuntimeError(f"OpenSSL component changed while read: {path}")
    if path.resolve(strict=True) != path or not stat.S_ISREG(after.st_mode):
        raise RuntimeError(f"OpenSSL component is not a direct regular file: {path}")
    profile_receipt: dict[str, object] = {
        "role": expected["role"],
        "path": str(path),
        "mode": f"{stat.S_IMODE(after.st_mode):04o}",
        "uid": after.st_uid,
        "gid": after.st_gid,
        "nlink": after.st_nlink,
        "bytes": total,
        "sha256": digest.hexdigest(),
    }
    if validate_expected and profile_receipt != {"path": str(path), **expected}:
        raise RuntimeError(
            f"OpenSSL component identity mismatch: {profile_receipt!r}"
        )
    return {
        **profile_receipt,
        "device": after.st_dev,
        "inode": after.st_ino,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
    }


def _integer_field(receipt: Mapping[str, object], name: str) -> int:
    value = receipt.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"OpenSSL receipt field is not an integer: {name}")
    return value


def _mode_field(receipt: Mapping[str, object], name: str = "mode") -> int:
    value = receipt.get(name)
    if not isinstance(value, str) or len(value) != 4 or any(
        character not in "01234567" for character in value
    ):
        raise RuntimeError(f"OpenSSL receipt field is not an octal mode: {name}")
    return int(value, 8)


def _seal_directory(
    path: Path,
    initial: Mapping[str, object],
) -> dict[str, object]:
    immediate = _directory_receipt(path, UNSEALED_DIRECTORY_PROFILES[path])
    if immediate != initial:
        raise RuntimeError(f"OpenSSL directory changed before root sealing: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_NOFOLLOW
        | os.O_DIRECTORY,
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (
            _integer_field(initial, "device"),
            _integer_field(initial, "inode"),
        ):
            raise RuntimeError(
                f"OpenSSL directory changed while opened for root sealing: {path}"
            )
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o755)
        sealed = os.fstat(descriptor)
        if (
            sealed.st_dev,
            sealed.st_ino,
            stat.S_IMODE(sealed.st_mode),
            sealed.st_uid,
            sealed.st_gid,
        ) != (
            _integer_field(initial, "device"),
            _integer_field(initial, "inode"),
            0o755,
            0,
            0,
        ):
            raise RuntimeError(f"OpenSSL directory root sealing failed: {path}")
    finally:
        os.close(descriptor)
    receipt = _directory_receipt(path, SEALED_DIRECTORY_PROFILES[path])
    if (receipt["device"], receipt["inode"]) != (
        initial["device"],
        initial["inode"],
    ):
        raise RuntimeError(f"OpenSSL directory identity changed after sealing: {path}")
    return receipt


def _seal_opt_link(initial: Mapping[str, object]) -> dict[str, object]:
    immediate = _opt_link_receipt(UNSEALED_OPT_LINK_PROFILE)
    if immediate != initial:
        raise RuntimeError("OpenSSL opt symlink changed before root sealing")
    os.chown(OPT_LINK, 0, 0, follow_symlinks=False)
    receipt = _opt_link_receipt(SEALED_OPT_LINK_PROFILE)
    if (receipt["device"], receipt["inode"], receipt["target"]) != (
        initial["device"],
        initial["inode"],
        initial["target"],
    ):
        raise RuntimeError("OpenSSL opt symlink identity changed after sealing")
    return receipt


def _seal_file(
    path: Path,
    initial: Mapping[str, object],
) -> dict[str, object]:
    immediate = _stable_file_receipt(path, UNSEALED_FILE_PROFILES)
    if immediate != initial:
        raise RuntimeError(f"OpenSSL component changed before root sealing: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW,
    )
    try:
        opened = os.fstat(descriptor)
        opened_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_nlink,
            opened.st_uid,
            opened.st_gid,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        initial_identity = (
            _integer_field(initial, "device"),
            _integer_field(initial, "inode"),
            stat.S_IFREG | _mode_field(initial),
            _integer_field(initial, "nlink"),
            _integer_field(initial, "uid"),
            _integer_field(initial, "gid"),
            _integer_field(initial, "bytes"),
            _integer_field(initial, "mtime_ns"),
            _integer_field(initial, "ctime_ns"),
        )
        if opened_identity != initial_identity:
            raise RuntimeError(
                f"OpenSSL component changed while opened for root sealing: {path}"
            )
        os.fchown(descriptor, 0, 0)
        sealed_mode = _mode_field(FILE_PROFILES[path])
        os.fchmod(descriptor, sealed_mode)
        sealed = os.fstat(descriptor)
        if (
            sealed.st_dev,
            sealed.st_ino,
            stat.S_IMODE(sealed.st_mode),
            sealed.st_nlink,
            sealed.st_uid,
            sealed.st_gid,
            sealed.st_size,
        ) != (
            _integer_field(initial, "device"),
            _integer_field(initial, "inode"),
            sealed_mode,
            _integer_field(initial, "nlink"),
            0,
            0,
            _integer_field(initial, "bytes"),
        ):
            raise RuntimeError(f"OpenSSL component root sealing failed: {path}")
    finally:
        os.close(descriptor)
    receipt = _stable_file_receipt(path)
    for key in ("role", "path", "nlink", "bytes", "sha256", "device", "inode"):
        if receipt[key] != initial[key]:
            raise RuntimeError(
                f"OpenSSL component identity changed after root sealing: {path}"
            )
    return receipt


def _reject_inherited_writable_file_descriptors() -> None:
    command = [
        "/usr/sbin/lsof",
        "-nP",
        "-F",
        "pfan",
        "--",
        *(str(path) for path in FILE_PROFILES),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
    )
    if completed.returncode == 1:
        if completed.stdout != "" or completed.stderr != "":
            raise RuntimeError(
                "writable-descriptor scan failed closed with rc=1 output: "
                f"{completed.stdout[-1000:]}{completed.stderr[-1000:]}"
            )
        return
    if completed.returncode != 0 or completed.stderr != "":
        raise RuntimeError(
            f"writable-descriptor scan failed ({completed.returncode}): "
            f"{completed.stdout[-1000:]}{completed.stderr[-1000:]}"
        )
    access: str | None = None
    observed_paths: set[str] = set()
    expected_paths = {str(path) for path in FILE_PROFILES}
    for line in completed.stdout.splitlines():
        if not line:
            continue
        field, value = line[0], line[1:]
        if field == "f":
            access = None
        elif field == "a":
            access = value
        elif field == "n" and value in expected_paths:
            observed_paths.add(value)
            if access not in {"r", "w", "u"}:
                raise RuntimeError(
                    f"unparseable OpenSSL descriptor access mode: {value}: {access!r}"
                )
            if access in {"w", "u"}:
                raise RuntimeError(
                    f"writable OpenSSL descriptor survived root sealing: {value}"
                )
    if completed.returncode == 0 and not observed_paths:
        raise RuntimeError("OpenSSL descriptor scan returned unrelated records")


def _sealed_authority_receipt() -> dict[str, object]:
    return {
        "directories": list(_directory_receipts(SEALED_DIRECTORY_PROFILES)),
        "opt_link": _opt_link_receipt(SEALED_OPT_LINK_PROFILE),
    }


def _seal_runtime() -> dict[str, object]:
    if os.geteuid() != 0:
        raise RuntimeError("OpenSSL runtime root sealing requires effective uid 0")
    directories_before = _directory_receipts(UNSEALED_DIRECTORY_PROFILES)
    opt_link_before = _opt_link_receipt(UNSEALED_OPT_LINK_PROFILE)
    files_before = tuple(
        _stable_file_receipt(
            path,
            UNSEALED_FILE_PROFILES,
            validate_parent_chain=False,
            validate_expected=False,
        )
        for path in UNSEALED_FILE_PROFILES
    )
    mismatches = [
        receipt
        # Root sealing deliberately uses the immutable macOS system Python,
        # which is older than the project toolchain and does not implement
        # zip(strict=...). Both sequences are built from the same mapping, so
        # their cardinality is already identical by construction.
        for path, receipt in zip(UNSEALED_FILE_PROFILES, files_before)
        if {
            key: receipt[key]
            for key in ("role", "path", "mode", "uid", "gid", "nlink", "bytes", "sha256")
        }
        != {"path": str(path), **UNSEALED_FILE_PROFILES[path]}
    ]
    if mismatches:
        raise RuntimeError(f"OpenSSL component identity mismatches: {mismatches!r}")
    directory_initial = {
        Path(str(receipt["path"])): receipt for receipt in directories_before
    }
    for path in SEALABLE_DIRECTORIES:
        _seal_directory(path, directory_initial[path])
    _directory_receipt(Path("/opt"), SEALED_DIRECTORY_PROFILES[Path("/opt")])
    _seal_opt_link(opt_link_before)
    file_initial = {Path(str(receipt["path"])): receipt for receipt in files_before}
    for path in UNSEALED_FILE_PROFILES:
        _seal_file(path, file_initial[path])
    _reject_inherited_writable_file_descriptors()
    authority_after = _sealed_authority_receipt()
    files_after = _stable_runtime_file_receipts()
    return {
        "schema_version": 1,
        "kind": "elmos.hosted-openssl3-root-seal-receipt",
        "image_os": EXPECTED_IMAGE[0],
        "image_version": EXPECTED_IMAGE[1],
        "macos_product_version": EXPECTED_MACOS_PRODUCT_VERSION,
        "macos_build_version": EXPECTED_MACOS_BUILD_VERSION,
        "authority": authority_after,
        "files": list(files_after),
    }


def _stable_runtime_file_receipts() -> tuple[dict[str, object], ...]:
    _sealed_authority_receipt()
    receipts = tuple(_stable_file_receipt(path) for path in FILE_PROFILES)
    expected_paths = tuple(str(path) for path in FILE_PROFILES)
    observed_paths = tuple(str(receipt.get("path")) for receipt in receipts)
    if len(receipts) != 3 or observed_paths != expected_paths:
        raise RuntimeError("OpenSSL runtime file receipt set is incomplete")
    return receipts


def _run_with_runtime_guard(
    command: list[str],
    *,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    before = _stable_runtime_file_receipts()
    try:
        return _run(command, environment=environment)
    finally:
        after = _stable_runtime_file_receipts()
        if before != after:
            raise RuntimeError(
                "OpenSSL runtime files changed during guarded external command"
            )


def _codesign_receipt(path: Path, *, validate_expected: bool = True) -> dict[str, object]:
    environment = _clean_environment()
    _run_with_runtime_guard(
        ["/usr/bin/codesign", "--verify", "--strict", "--verbose=2", str(path)],
        environment=environment,
    )
    details = _run_with_runtime_guard(
        ["/usr/bin/codesign", "-d", "--verbose=4", str(path)],
        environment=environment,
    )
    lines = set((details.stdout + details.stderr).splitlines())
    expected = SIGNATURE_PROFILES.get(path)
    if expected is not None:
        prefixes = (
            "Identifier=",
            "Format=",
            "CodeDirectory ",
            "Hash type=",
            "CandidateCDHashFull ",
            "CMSDigest=",
            "CDHash=",
            "Signature=",
            "TeamIdentifier=",
            "Sealed Resources=",
            "Internal requirements ",
        )
        observed = sorted(line for line in lines if line.startswith(prefixes))
    else:
        observed = []
    if validate_expected and expected is not None and not expected.issubset(lines):
        missing = sorted(expected - lines)
        raise RuntimeError(
            f"OpenSSL signature identity mismatch for {path}: "
            f"missing={missing!r}, observed={observed!r}"
        )
    return {
        "path": str(path),
        "details": sorted(expected or ()) if validate_expected else observed,
    }


def _dependency_paths(path: Path) -> tuple[str, ...]:
    output = _run_with_runtime_guard(
        ["/usr/bin/otool", "-L", str(path)],
        environment=_clean_environment(),
    ).stdout.splitlines()
    if not output or output[0] != f"{path}:":
        raise RuntimeError(f"invalid otool dependency header: {path}")
    dependencies = tuple(
        line.strip().split(" (compatibility version ", 1)[0]
        for line in output[1:]
    )
    if dependencies != DEPENDENCIES[path]:
        raise RuntimeError(
            f"OpenSSL dependency closure mismatch for {path}: {dependencies!r}"
        )
    return dependencies


def _dylib_id(path: Path) -> str:
    output = _run_with_runtime_guard(
        ["/usr/bin/otool", "-D", str(path)],
        environment=_clean_environment(),
    ).stdout.splitlines()
    if output != [f"{path}:", DYLIB_IDS[path]]:
        raise RuntimeError(f"OpenSSL dylib ID mismatch for {path}: {output!r}")
    return output[1]


def _runtime_receipt() -> dict[str, object]:
    authority_before = _sealed_authority_receipt()
    files_before = _stable_runtime_file_receipts()
    observed_signatures = [
        _codesign_receipt(path, validate_expected=False) for path in FILE_PROFILES
    ]
    signature_mismatches = []
    for receipt in observed_signatures:
        path = Path(str(receipt["path"]))
        expected = SIGNATURE_PROFILES.get(path)
        observed = set(receipt["details"])
        if expected is not None and not expected.issubset(observed):
            signature_mismatches.append(
                {
                    "path": str(path),
                    "missing": sorted(expected - observed),
                    "observed": sorted(observed),
                }
            )
    if signature_mismatches:
        raise RuntimeError(
            f"OpenSSL signature identity mismatches: {signature_mismatches!r}"
        )
    signatures = [
        {"path": str(path), "details": sorted(SIGNATURE_PROFILES.get(path, ()))}
        for path in FILE_PROFILES
    ]
    dependencies = {
        str(path): list(_dependency_paths(path)) for path in FILE_PROFILES
    }
    dylib_ids = {str(path): _dylib_id(path) for path in DYLIB_IDS}
    version = _run_with_runtime_guard(
        [str(OPENSSL), "version"], environment=_clean_environment()
    ).stdout.strip()
    files_after = _stable_runtime_file_receipts()
    authority_after = _sealed_authority_receipt()
    if files_before != files_after or authority_before != authority_after:
        raise RuntimeError("OpenSSL runtime authority changed while building receipt")
    return {
        "schema_version": 1,
        "kind": "elmos.hosted-openssl3-runtime-receipt",
        "image_os": os.environ.get("ImageOS"),
        "image_version": os.environ.get("ImageVersion"),
        "macos_product_version": EXPECTED_MACOS_PRODUCT_VERSION,
        "macos_build_version": EXPECTED_MACOS_BUILD_VERSION,
        "version": version,
        "authority": authority_after,
        "files": list(files_after),
        "signatures": signatures,
        "dependencies": dependencies,
        "dylib_ids": dylib_ids,
    }


def _clean_environment(*, trace_libraries: bool = False) -> dict[str, str]:
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(runner_temp),
        "TMPDIR": str(runner_temp),
        "LANG": "C",
        "LC_ALL": "C",
        "OPENSSL_CONF": "/dev/null",
    }
    if trace_libraries:
        environment["DYLD_PRINT_LIBRARIES"] = "1"
    return environment


def _verify_actual_load_trace(stderr: str) -> None:
    loaded_openssl_libraries = {
        token
        for line in stderr.splitlines()
        for token in line.split()
        if token.endswith(("/libssl.3.dylib", "/libcrypto.3.dylib"))
    }
    expected = {str(LIBSSL), str(LIBCRYPTO)}
    if loaded_openssl_libraries != expected:
        raise RuntimeError(
            "OpenSSL actual-load closure mismatch: "
            f"{sorted(loaded_openssl_libraries)!r}"
        )


def _verify_actual_load() -> None:
    environment = _clean_environment(trace_libraries=True)
    completed = _run_with_runtime_guard(
        [str(OPENSSL), "version"], environment=environment
    )
    if completed.stdout.strip() != EXPECTED_VERSION:
        raise RuntimeError("clean-environment OpenSSL version mismatch")
    _verify_actual_load_trace(completed.stderr)


def _verify_ed25519() -> None:
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix="elmos-openssl3-probe.", dir=runner_temp))
    try:
        root.chmod(0o700)
        environment = _clean_environment()
        payload = root / "payload"
        private = root / "private.pem"
        public = root / "public.pem"
        signature = root / "signature"
        payload.write_bytes(b"elmos-openssl3-ed25519-probe\n")
        _run_with_runtime_guard(
            [str(OPENSSL), "genpkey", "-algorithm", "ed25519", "-out", str(private)],
            environment=environment,
        )
        _run_with_runtime_guard(
            [str(OPENSSL), "pkey", "-in", str(private), "-pubout", "-out", str(public)],
            environment=environment,
        )
        _run_with_runtime_guard(
            [
                str(OPENSSL),
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private),
                "-rawin",
                "-in",
                str(payload),
                "-out",
                str(signature),
            ],
            environment=environment,
        )
        _run_with_runtime_guard(
            [
                str(OPENSSL),
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public),
                "-rawin",
                "-in",
                str(payload),
                "-sigfile",
                str(signature),
            ],
            environment=environment,
        )
    finally:
        shutil.rmtree(root)


def _forbidden_environment_names(environment: Mapping[str, str]) -> set[str]:
    return {
        name
        for name in environment
        if name.startswith("DYLD_")
        or name
        in {
            "CODESIGN_ALLOCATE",
            "OPENSSL_CONF",
            "OPENSSL_MODULES",
            "OPENSSL_ENGINES",
            "RANDFILE",
        }
    }


def _verify_host(image_os: str | None, image_version: str | None) -> None:
    if sys.platform != "darwin" or os.uname().machine != "arm64":
        raise RuntimeError("OpenSSL runtime verifier requires Darwin arm64")
    if (image_os, image_version) != EXPECTED_IMAGE:
        raise RuntimeError("GitHub hosted image identity mismatch")
    if (
        _run(["/usr/bin/sw_vers", "-productVersion"]).stdout.strip()
        != EXPECTED_MACOS_PRODUCT_VERSION
    ):
        raise RuntimeError("hosted macOS product version mismatch")
    if (
        _run(["/usr/bin/sw_vers", "-buildVersion"]).stdout.strip()
        != EXPECTED_MACOS_BUILD_VERSION
    ):
        raise RuntimeError("hosted macOS build version mismatch")


def _parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify or root-seal the pinned hosted OpenSSL 3 runtime."
    )
    parser.add_argument("--seal", action="store_true")
    parser.add_argument("--image-os")
    parser.add_argument("--image-version")
    arguments = parser.parse_args(argv)
    supplied_image = arguments.image_os is not None or arguments.image_version is not None
    if arguments.seal and (
        arguments.image_os is None or arguments.image_version is None
    ):
        parser.error("--seal requires --image-os and --image-version")
    if not arguments.seal and supplied_image:
        parser.error("explicit image arguments are accepted only with --seal")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    forbidden_environment = _forbidden_environment_names(os.environ)
    if forbidden_environment:
        raise RuntimeError(
            "inherited OpenSSL or dynamic-loader override is forbidden: "
            + ",".join(sorted(forbidden_environment))
        )
    image = (
        (arguments.image_os, arguments.image_version)
        if arguments.seal
        else (os.environ.get("ImageOS"), os.environ.get("ImageVersion"))
    )
    _verify_host(*image)
    if arguments.seal:
        receipt = _seal_runtime()
        print(
            "OPENSSL3_ROOT_SEAL_RECEIPT "
            + json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        )
        return 0

    before = _runtime_receipt()
    if before["version"] != EXPECTED_VERSION:
        raise RuntimeError("OpenSSL runtime version mismatch")
    _verify_actual_load()
    _verify_ed25519()
    after = _runtime_receipt()
    if before != after:
        raise RuntimeError("OpenSSL runtime changed during verification")
    print("OPENSSL3_RUNTIME_RECEIPT " + json.dumps(after, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
