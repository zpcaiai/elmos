"""Fail-closed binding for an externally governed Visual Basic 6.0 SP6 install.

VB6 is proprietary and Windows-only, so it cannot be vendored with the other
repository toolchains.  A Windows runner may inject one exact installation via
an out-of-repository manifest.  The manifest is self-attested input: byte and
PE identities are verified here, while independent verification and route
certification remain separate gates.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .models import RouteError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "product",
        "service_pack",
        "host_os",
        "host_architecture",
        "compiler_architecture",
        "compiler_path",
        "compiler_sha256",
        "compiler_version",
        "runtime_path",
        "runtime_sha256",
        "runtime_version",
        "runner_id",
        "authorization_ref",
        "evidence_class",
    }
)


@dataclass(frozen=True)
class VB6ToolchainBinding:
    compiler: Path
    runtime: Path
    compiler_sha256: str
    runtime_sha256: str
    compiler_version: str
    runtime_version: str
    host_architecture: str
    runner_id: str
    authorization_ref: str
    manifest_sha256: str


def _stable_file(path: Path, code: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise OSError(code)
        content = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise RouteError(code) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity or len(content) != after.st_size:
        raise RouteError(code)
    return content


def _pe_machine(content: bytes, code: str) -> int:
    """Read the COFF machine field without executing an untrusted binary."""

    if len(content) < 0x40 or content[:2] != b"MZ":
        raise RouteError(code)
    pe_offset = struct.unpack_from("<I", content, 0x3C)[0]
    if pe_offset > len(content) - 6 or content[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        raise RouteError(code)
    return int(struct.unpack_from("<H", content, pe_offset + 4)[0])


def _required_text(manifest: Mapping[str, object], key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 for char in value):
        raise RouteError(f"VB6_TOOLCHAIN_MANIFEST_FIELD_INVALID:{key}")
    return value.strip()


def binding_fingerprint(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Cheap cache key; full content checks still run inside the selector."""

    values = os.environ if environ is None else environ
    raw_path = values.get("ELMOS_VB6_TOOLCHAIN_MANIFEST", "").strip()
    expected = values.get("ELMOS_VB6_TOOLCHAIN_MANIFEST_SHA256", "").strip().lower()
    identity = "MISSING"
    if raw_path:
        try:
            metadata = Path(raw_path).lstat()
            identity = ":".join(
                str(value)
                for value in (
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    metadata.st_ctime_ns,
                )
            )
        except OSError:
            pass
    return raw_path, expected, identity


def resolve_vb6_toolchain(
    repository_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
    host_system: str | None = None,
    host_machine: str | None = None,
) -> VB6ToolchainBinding:
    """Resolve and verify one exact external VB6 installation or fail closed."""

    values = os.environ if environ is None else environ
    system = platform.system() if host_system is None else host_system
    machine = platform.machine() if host_machine is None else host_machine
    normalized_machine = machine.strip().lower()
    if system != "Windows" or normalized_machine not in {
        "x86",
        "i386",
        "i686",
        "amd64",
        "x86_64",
    }:
        raise RouteError(
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:vb6:expected=Windows/x86-compatible:"
            f"observed={system}/{machine}"
        )

    raw_manifest = values.get("ELMOS_VB6_TOOLCHAIN_MANIFEST", "").strip()
    expected_manifest_sha256 = values.get(
        "ELMOS_VB6_TOOLCHAIN_MANIFEST_SHA256", ""
    ).strip().lower()
    if not raw_manifest or _SHA256.fullmatch(expected_manifest_sha256) is None:
        raise RouteError("VB6_VENDOR_COMPILER_RUNTIME_REQUIRED")
    manifest_path = Path(raw_manifest)
    if not manifest_path.is_absolute():
        raise RouteError("VB6_TOOLCHAIN_MANIFEST_PATH_UNSAFE")
    try:
        repository = repository_root.resolve(strict=True)
        manifest_resolved = manifest_path.resolve(strict=True)
        manifest_resolved.relative_to(repository)
    except ValueError:
        pass
    except OSError as error:
        raise RouteError("VB6_TOOLCHAIN_MANIFEST_PATH_UNSAFE") from error
    else:
        raise RouteError("VB6_TOOLCHAIN_MANIFEST_MUST_BE_EXTERNAL")

    manifest_bytes = _stable_file(manifest_path, "VB6_TOOLCHAIN_MANIFEST_UNSAFE")
    observed_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if observed_manifest_sha256 != expected_manifest_sha256:
        raise RouteError("VB6_TOOLCHAIN_MANIFEST_DIGEST_MISMATCH")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("VB6_TOOLCHAIN_MANIFEST_INVALID") from error
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        raise RouteError("VB6_TOOLCHAIN_MANIFEST_INVALID")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "elmos.vb6-sp6-toolchain-binding"
        or manifest.get("product") != "Microsoft Visual Basic 6.0 SP6"
        or manifest.get("service_pack") != 6
        or manifest.get("host_os") != "Windows"
        or manifest.get("compiler_architecture") != "x86"
        or manifest.get("evidence_class") != "GOVERNED_EXTERNAL_SELF_ATTESTED"
    ):
        raise RouteError("VB6_TOOLCHAIN_MANIFEST_INVALID")
    declared_host = _required_text(manifest, "host_architecture").lower()
    if declared_host != normalized_machine:
        raise RouteError("VB6_TOOLCHAIN_HOST_IDENTITY_MISMATCH")

    compiler = Path(_required_text(manifest, "compiler_path"))
    runtime = Path(_required_text(manifest, "runtime_path"))
    if not compiler.is_absolute() or not runtime.is_absolute() or compiler == runtime:
        raise RouteError("VB6_TOOLCHAIN_PATH_INVALID")
    compiler_bytes = _stable_file(compiler, "VB6_COMPILER_UNSAFE_OR_MISSING")
    runtime_bytes = _stable_file(runtime, "VB6_RUNTIME_UNSAFE_OR_MISSING")
    compiler_sha256 = _required_text(manifest, "compiler_sha256").lower()
    runtime_sha256 = _required_text(manifest, "runtime_sha256").lower()
    if (
        _SHA256.fullmatch(compiler_sha256) is None
        or hashlib.sha256(compiler_bytes).hexdigest() != compiler_sha256
    ):
        raise RouteError("VB6_COMPILER_DIGEST_MISMATCH")
    if (
        _SHA256.fullmatch(runtime_sha256) is None
        or hashlib.sha256(runtime_bytes).hexdigest() != runtime_sha256
    ):
        raise RouteError("VB6_RUNTIME_DIGEST_MISMATCH")
    if _pe_machine(compiler_bytes, "VB6_COMPILER_PE_IDENTITY_INVALID") != 0x014C:
        raise RouteError("VB6_COMPILER_ARCHITECTURE_MISMATCH")
    if _pe_machine(runtime_bytes, "VB6_RUNTIME_PE_IDENTITY_INVALID") != 0x014C:
        raise RouteError("VB6_RUNTIME_ARCHITECTURE_MISMATCH")

    return VB6ToolchainBinding(
        compiler=compiler.resolve(strict=True),
        runtime=runtime.resolve(strict=True),
        compiler_sha256=compiler_sha256,
        runtime_sha256=runtime_sha256,
        compiler_version=_required_text(manifest, "compiler_version"),
        runtime_version=_required_text(manifest, "runtime_version"),
        host_architecture=declared_host,
        runner_id=_required_text(manifest, "runner_id"),
        authorization_ref=_required_text(manifest, "authorization_ref"),
        manifest_sha256=observed_manifest_sha256,
    )


__all__ = ["VB6ToolchainBinding", "binding_fingerprint", "resolve_vb6_toolchain"]
