from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.vcpp6_toolchain import resolve_vcpp6_toolchain


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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
    vendor = tmp_path / "vendor"
    runtime_dir = tmp_path / "windows"
    vendor.mkdir()
    runtime_dir.mkdir()
    compiler = vendor / "CL.EXE"
    linker = vendor / "LINK.EXE"
    runtime = runtime_dir / "MSVCP60.DLL"
    compiler_digest = _pe32(compiler, b"compiler")
    linker_digest = _pe32(linker, b"linker")
    runtime_digest = _pe32(runtime, b"runtime")
    manifest = {
        "schema_version": 1,
        "kind": "elmos.vcpp6-sp6-toolchain-binding",
        "product": "Microsoft Visual C++ 6.0 SP6",
        "service_pack": 6,
        "host_os": "Windows",
        "host_architecture": "amd64",
        "compiler_architecture": "x86",
        "compiler_path": str(compiler),
        "compiler_sha256": compiler_digest,
        "compiler_version": "12.00.9782",
        "linker_path": str(linker),
        "linker_sha256": linker_digest,
        "linker_version": "6.00.9782",
        "runtime_path": str(runtime),
        "runtime_sha256": runtime_digest,
        "runtime_version": "6.00.8972.0",
        "runner_id": "windows-vcpp6-lab-01",
        "authorization_ref": "change-5678",
        "evidence_class": "GOVERNED_EXTERNAL_SELF_ATTESTED",
    }
    manifest_path = tmp_path / "governed-vcpp6-binding.json"
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)
    return repository, {
        "ELMOS_VCPP6_TOOLCHAIN_MANIFEST": str(manifest_path),
        "ELMOS_VCPP6_TOOLCHAIN_MANIFEST_SHA256": hashlib.sha256(manifest_bytes).hexdigest(),
    }


def test_governed_binding_verifies_all_vendor_files_and_pe_architecture(tmp_path: Path) -> None:
    repository, environment = _binding(tmp_path)
    binding = resolve_vcpp6_toolchain(
        repository, environ=environment, host_system="Windows", host_machine="AMD64"
    )
    assert binding.compiler.name == "CL.EXE"
    assert binding.linker.name == "LINK.EXE"
    assert binding.runtime.name == "MSVCP60.DLL"
    assert binding.runner_id == "windows-vcpp6-lab-01"


def test_binding_rejects_non_windows_hosts(tmp_path: Path) -> None:
    repository, environment = _binding(tmp_path)
    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_PLATFORM_MISMATCH:vcpp6"):
        resolve_vcpp6_toolchain(
            repository, environ=environment, host_system="Darwin", host_machine="arm64"
        )


def test_binding_rejects_changed_vendor_bytes(tmp_path: Path) -> None:
    repository, environment = _binding(tmp_path)
    manifest = json.loads(Path(environment["ELMOS_VCPP6_TOOLCHAIN_MANIFEST"]).read_text())
    Path(manifest["linker_path"]).write_bytes(b"changed")
    with pytest.raises(RouteError, match="VCPP6_LINKER_DIGEST_MISMATCH"):
        resolve_vcpp6_toolchain(
            repository, environ=environment, host_system="Windows", host_machine="AMD64"
        )


def test_binding_manifest_cannot_be_repository_controlled(tmp_path: Path) -> None:
    repository, environment = _binding(tmp_path)
    source = Path(environment["ELMOS_VCPP6_TOOLCHAIN_MANIFEST"])
    inside = repository / "binding.json"
    inside.write_bytes(source.read_bytes())
    environment["ELMOS_VCPP6_TOOLCHAIN_MANIFEST"] = str(inside)
    environment["ELMOS_VCPP6_TOOLCHAIN_MANIFEST_SHA256"] = hashlib.sha256(inside.read_bytes()).hexdigest()
    with pytest.raises(RouteError, match="VCPP6_TOOLCHAIN_MANIFEST_MUST_BE_EXTERNAL"):
        resolve_vcpp6_toolchain(
            repository, environ=environment, host_system="Windows", host_machine="AMD64"
        )


def test_vcpp6_binding_schema_accepts_the_exact_runtime_contract(tmp_path: Path) -> None:
    _, environment = _binding(tmp_path)
    schema = json.loads(
        (REPOSITORY_ROOT / "schemas" / "batch29" / "vcpp6-toolchain-binding.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    manifest = json.loads(
        Path(environment["ELMOS_VCPP6_TOOLCHAIN_MANIFEST"]).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(manifest)
