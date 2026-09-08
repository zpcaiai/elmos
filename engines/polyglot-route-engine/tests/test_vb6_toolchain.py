from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.vb6_toolchain import resolve_vb6_toolchain


def _pe32(path: Path, marker: bytes) -> str:
    content = bytearray(256)
    content[:2] = b"MZ"
    struct.pack_into("<I", content, 0x3C, 0x80)
    content[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", content, 0x84, 0x014C)
    content[0x90 : 0x90 + len(marker)] = marker
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _binding(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repository = tmp_path / "repo"
    repository.mkdir()
    compiler = tmp_path / "vendor" / "VB6.EXE"
    runtime = tmp_path / "windows" / "MSVBVM60.DLL"
    compiler.parent.mkdir()
    runtime.parent.mkdir()
    compiler_digest = _pe32(compiler, b"compiler")
    runtime_digest = _pe32(runtime, b"runtime")
    manifest = {
        "schema_version": 1,
        "kind": "elmos.vb6-sp6-toolchain-binding",
        "product": "Microsoft Visual Basic 6.0 SP6",
        "service_pack": 6,
        "host_os": "Windows",
        "host_architecture": "amd64",
        "compiler_architecture": "x86",
        "compiler_path": str(compiler),
        "compiler_sha256": compiler_digest,
        "compiler_version": "6.0.97.82",
        "runtime_path": str(runtime),
        "runtime_sha256": runtime_digest,
        "runtime_version": "6.0.98.48",
        "runner_id": "windows-vb6-lab-01",
        "authorization_ref": "change-1234",
        "evidence_class": "GOVERNED_EXTERNAL_SELF_ATTESTED",
    }
    manifest_path = tmp_path / "governed-vb6-binding.json"
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)
    environment = {
        "ELMOS_VB6_TOOLCHAIN_MANIFEST": str(manifest_path),
        "ELMOS_VB6_TOOLCHAIN_MANIFEST_SHA256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    return repository, environment


def test_governed_binding_verifies_manifest_files_digests_and_pe_architecture(
    tmp_path: Path,
) -> None:
    repository, environment = _binding(tmp_path)

    binding = resolve_vb6_toolchain(
        repository,
        environ=environment,
        host_system="Windows",
        host_machine="AMD64",
    )

    assert binding.compiler.name == "VB6.EXE"
    assert binding.runtime.name == "MSVBVM60.DLL"
    assert binding.host_architecture == "amd64"
    assert binding.runner_id == "windows-vb6-lab-01"


def test_binding_rejects_non_windows_hosts_before_accepting_manifest(tmp_path: Path) -> None:
    repository, environment = _binding(tmp_path)

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_PLATFORM_MISMATCH:vb6"):
        resolve_vb6_toolchain(
            repository,
            environ=environment,
            host_system="Darwin",
            host_machine="arm64",
        )


def test_binding_rejects_changed_vendor_bytes(tmp_path: Path) -> None:
    repository, environment = _binding(tmp_path)
    manifest = json.loads(Path(environment["ELMOS_VB6_TOOLCHAIN_MANIFEST"]).read_text())
    Path(manifest["runtime_path"]).write_bytes(b"changed")

    with pytest.raises(RouteError, match="VB6_RUNTIME_DIGEST_MISMATCH"):
        resolve_vb6_toolchain(
            repository,
            environ=environment,
            host_system="Windows",
            host_machine="AMD64",
        )


def test_binding_manifest_cannot_be_repository_controlled(tmp_path: Path) -> None:
    repository, environment = _binding(tmp_path)
    source = Path(environment["ELMOS_VB6_TOOLCHAIN_MANIFEST"])
    inside = repository / "binding.json"
    inside.write_bytes(source.read_bytes())
    environment["ELMOS_VB6_TOOLCHAIN_MANIFEST"] = str(inside)
    environment["ELMOS_VB6_TOOLCHAIN_MANIFEST_SHA256"] = hashlib.sha256(
        inside.read_bytes()
    ).hexdigest()

    with pytest.raises(RouteError, match="VB6_TOOLCHAIN_MANIFEST_MUST_BE_EXTERNAL"):
        resolve_vb6_toolchain(
            repository,
            environ=environment,
            host_system="Windows",
            host_machine="AMD64",
        )
