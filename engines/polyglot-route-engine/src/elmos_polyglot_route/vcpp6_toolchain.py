"""Fail-closed binding for a governed Microsoft Visual C++ 6.0 SP6 install."""

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
        "linker_path",
        "linker_sha256",
        "linker_version",
        "runtime_path",
        "runtime_sha256",
        "runtime_version",
        "runner_id",
        "authorization_ref",
        "evidence_class",
    }
)


@dataclass(frozen=True)
class VCpp6ToolchainBinding:
    compiler: Path
    linker: Path
    runtime: Path
    compiler_sha256: str
    linker_sha256: str
    runtime_sha256: str
    compiler_version: str
    linker_version: str
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
    if (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) or len(content) != after.st_size:
        raise RouteError(code)
    return content


def _pe_machine(content: bytes, code: str) -> int:
    if len(content) < 0x40 or content[:2] != b"MZ":
        raise RouteError(code)
    pe_offset = struct.unpack_from("<I", content, 0x3C)[0]
    if pe_offset > len(content) - 6 or content[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        raise RouteError(code)
    return int(struct.unpack_from("<H", content, pe_offset + 4)[0])


def _required_text(manifest: Mapping[str, object], key: str) -> str:
    value = manifest.get(key)
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise RouteError(f"VCPP6_TOOLCHAIN_MANIFEST_FIELD_INVALID:{key}")
    return value.strip()


def binding_fingerprint(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    values = os.environ if environ is None else environ
    raw_path = values.get("ELMOS_VCPP6_TOOLCHAIN_MANIFEST", "").strip()
    expected = values.get("ELMOS_VCPP6_TOOLCHAIN_MANIFEST_SHA256", "").strip().lower()
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


def resolve_vcpp6_toolchain(
    repository_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
    host_system: str | None = None,
    host_machine: str | None = None,
) -> VCpp6ToolchainBinding:
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
            "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:vcpp6:expected=Windows/x86-compatible:"
            f"observed={system}/{machine}"
        )

    raw_manifest = values.get("ELMOS_VCPP6_TOOLCHAIN_MANIFEST", "").strip()
    expected_manifest_sha256 = values.get(
        "ELMOS_VCPP6_TOOLCHAIN_MANIFEST_SHA256", ""
    ).strip().lower()
    if not raw_manifest or _SHA256.fullmatch(expected_manifest_sha256) is None:
        raise RouteError("VCPP6_VENDOR_COMPILER_RUNTIME_REQUIRED")
    manifest_path = Path(raw_manifest)
    if not manifest_path.is_absolute():
        raise RouteError("VCPP6_TOOLCHAIN_MANIFEST_PATH_UNSAFE")
    try:
        repository = repository_root.resolve(strict=True)
        manifest_resolved = manifest_path.resolve(strict=True)
        manifest_resolved.relative_to(repository)
    except ValueError:
        pass
    except OSError as error:
        raise RouteError("VCPP6_TOOLCHAIN_MANIFEST_PATH_UNSAFE") from error
    else:
        raise RouteError("VCPP6_TOOLCHAIN_MANIFEST_MUST_BE_EXTERNAL")

    manifest_bytes = _stable_file(manifest_path, "VCPP6_TOOLCHAIN_MANIFEST_UNSAFE")
    observed_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if observed_manifest_sha256 != expected_manifest_sha256:
        raise RouteError("VCPP6_TOOLCHAIN_MANIFEST_DIGEST_MISMATCH")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("VCPP6_TOOLCHAIN_MANIFEST_INVALID") from error
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        raise RouteError("VCPP6_TOOLCHAIN_MANIFEST_INVALID")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "elmos.vcpp6-sp6-toolchain-binding"
        or manifest.get("product") != "Microsoft Visual C++ 6.0 SP6"
        or manifest.get("service_pack") != 6
        or manifest.get("host_os") != "Windows"
        or manifest.get("compiler_architecture") != "x86"
        or manifest.get("evidence_class") != "GOVERNED_EXTERNAL_SELF_ATTESTED"
    ):
        raise RouteError("VCPP6_TOOLCHAIN_MANIFEST_INVALID")
    declared_host = _required_text(manifest, "host_architecture").lower()
    if declared_host != normalized_machine:
        raise RouteError("VCPP6_TOOLCHAIN_HOST_IDENTITY_MISMATCH")

    paths = {
        "compiler": Path(_required_text(manifest, "compiler_path")),
        "linker": Path(_required_text(manifest, "linker_path")),
        "runtime": Path(_required_text(manifest, "runtime_path")),
    }
    if any(not path.is_absolute() for path in paths.values()) or len(set(paths.values())) != 3:
        raise RouteError("VCPP6_TOOLCHAIN_PATH_INVALID")
    contents = {
        name: _stable_file(path, f"VCPP6_{name.upper()}_UNSAFE_OR_MISSING")
        for name, path in paths.items()
    }
    digests = {
        name: _required_text(manifest, f"{name}_sha256").lower()
        for name in paths
    }
    for name in paths:
        if (
            _SHA256.fullmatch(digests[name]) is None
            or hashlib.sha256(contents[name]).hexdigest() != digests[name]
        ):
            raise RouteError(f"VCPP6_{name.upper()}_DIGEST_MISMATCH")
        if _pe_machine(contents[name], f"VCPP6_{name.upper()}_PE_IDENTITY_INVALID") != 0x014C:
            raise RouteError(f"VCPP6_{name.upper()}_ARCHITECTURE_MISMATCH")

    return VCpp6ToolchainBinding(
        compiler=paths["compiler"].resolve(strict=True),
        linker=paths["linker"].resolve(strict=True),
        runtime=paths["runtime"].resolve(strict=True),
        compiler_sha256=digests["compiler"],
        linker_sha256=digests["linker"],
        runtime_sha256=digests["runtime"],
        compiler_version=_required_text(manifest, "compiler_version"),
        linker_version=_required_text(manifest, "linker_version"),
        runtime_version=_required_text(manifest, "runtime_version"),
        host_architecture=declared_host,
        runner_id=_required_text(manifest, "runner_id"),
        authorization_ref=_required_text(manifest, "authorization_ref"),
        manifest_sha256=observed_manifest_sha256,
    )


__all__ = ["VCpp6ToolchainBinding", "binding_fingerprint", "resolve_vcpp6_toolchain"]
