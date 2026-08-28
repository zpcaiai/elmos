#!/usr/bin/env python3
"""Safely integrate the pinned v3.1 harness-runtime-assurance delta.

The delta ZIP is untrusted source material.  This importer independently
validates its byte identity, ZIP metadata, checksums, manifest, registry and
JSON contracts.  It never imports or executes archive scripts, the reference
implementation, Rego, SQL, Markdown instructions, or installer workflows.
Only inert schemas/examples and repository-authored release assets are
materialized.  Skill wrappers point at :mod:`elmos_proof_harness.delta`, the
repository-owned implementation.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unicodedata
import uuid
import zipfile
from typing import Any, Iterator, Mapping, Sequence


PACKAGE_NAME = "elmos-v3-harness-runtime-assurance-delta"
PACKAGE_VERSION = "3.1.0"
ARCHIVE_ROOT = f"{PACKAGE_NAME}-v{PACKAGE_VERSION}"
ARCHIVE_RELATIVE_PATH = Path("skills/subskills") / f"{ARCHIVE_ROOT}.zip"
ARCHIVE_SHA256 = "13ba6f089d3c367affe3e03999418029873d842e07a8c80cfaeeffb4308a7a37"
ARCHIVE_BYTES = 339_731
EXPECTED_ENTRIES = 150
EXPECTED_FILES = 150
EXPECTED_UNCOMPRESSED_BYTES = 339_731
EXPECTED_CHECKSUM_ROWS = 149
EXPECTED_PAYLOAD_FILES = 130
EXPECTED_EXTENSION_SKILLS = 13
EXPECTED_SCHEMAS = 15
EXPECTED_ADAPTER_PROFILES = 4
EXPECTED_REGO_MODULES = 5
DELTA_API_VERSION = "elmos.ai/v3delta1"
BASE_PACKAGE = "elmos-proof-driven-agentic-harness-repository-semantic-compiler"
BASE_VERSION = "3.0.0"
DELTA_ROOT = Path("docs/proof-driven-harness-v3/delta-v3.1")
ENGINE_ROOT = Path("engines/proof-driven-harness-engine")
RECEIPT_PATH = ENGINE_ROOT / "qualification/delta-v3.1/local-qualification.json"
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024


class IntegrationError(RuntimeError):
    pass


def _strict_json(data: bytes, source: str) -> Any:
    def reject(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value}")

    try:
        return json.loads(data.decode("utf-8", "strict"), parse_constant=reject)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IntegrationError(f"invalid JSON in {source}: {exc}") from exc


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_stable(path: Path, *, expected_size: int | None = None, limit: int = MAX_MEMBER_BYTES) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise IntegrationError(f"cannot open archive safely: {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise IntegrationError("archive is not a regular file")
        if expected_size is not None and before.st_size != expected_size:
            raise IntegrationError(f"archive size mismatch: expected {expected_size}, got {before.st_size}")
        if before.st_size > limit:
            raise IntegrationError("archive exceeds bounded read limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            part = os.read(fd, min(1024 * 1024, limit - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
            if total > limit:
                raise IntegrationError("archive exceeded bounded read limit")
        after = os.fstat(fd)
        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if identity(before) != identity(after) or total != before.st_size:
            raise IntegrationError("archive changed while reading")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _relative_name(name: str) -> str:
    prefix = ARCHIVE_ROOT + "/"
    if not name.startswith(prefix):
        raise IntegrationError(f"member outside pinned archive root: {name!r}")
    value = name[len(prefix) :]
    if not value:
        raise IntegrationError("archive root entry is not a file")
    return value


def _validate_infos(infos: Sequence[zipfile.ZipInfo]) -> dict[str, zipfile.ZipInfo]:
    if len(infos) != EXPECTED_ENTRIES:
        raise IntegrationError(f"entry count mismatch: expected {EXPECTED_ENTRIES}, got {len(infos)}")
    files: dict[str, zipfile.ZipInfo] = {}
    folded: set[str] = set()
    total = 0
    for info in infos:
        raw = info.filename
        relative = _relative_name(raw)
        if "\x00" in raw or "\\" in raw or raw.endswith("/"):
            raise IntegrationError(f"unsafe ZIP member name: {raw!r}")
        if unicodedata.normalize("NFC", raw) != raw:
            raise IntegrationError(f"non-NFC ZIP member name: {raw!r}")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(not part or part in {".", ".."} for part in pure.parts):
            raise IntegrationError(f"unsafe ZIP path: {raw!r}")
        key = unicodedata.normalize("NFKC", relative).casefold()
        if key in folded:
            raise IntegrationError(f"ZIP path collision: {raw!r}")
        folded.add(key)
        if info.flag_bits & ((1 << 0) | (1 << 6)):
            raise IntegrationError(f"encrypted ZIP member: {raw!r}")
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise IntegrationError(f"unsupported ZIP compression: {raw!r}")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
            raise IntegrationError(f"special ZIP member: {raw!r}")
        if info.file_size > MAX_MEMBER_BYTES:
            raise IntegrationError(f"member too large: {raw!r}")
        total += info.file_size
        files[relative] = info
    if len(files) != EXPECTED_FILES or total != EXPECTED_UNCOMPRESSED_BYTES or total > MAX_TOTAL_BYTES:
        raise IntegrationError(f"member totals drifted: files={len(files)} bytes={total}")
    return files


def _member_bytes(archive: zipfile.ZipFile, files: Mapping[str, zipfile.ZipInfo], name: str, *, limit: int = MAX_MEMBER_BYTES) -> bytes:
    info = files.get(name)
    if info is None:
        raise IntegrationError(f"required archive member missing: {name}")
    if info.file_size > limit:
        raise IntegrationError(f"member exceeds bounded read limit: {name}")
    try:
        data = archive.read(info)
    except (RuntimeError, zipfile.BadZipFile) as exc:
        raise IntegrationError(f"cannot read ZIP member {name}: {exc}") from exc
    if len(data) != info.file_size:
        raise IntegrationError(f"short ZIP member read: {name}")
    return data


def _parse_checksums(data: bytes) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line_number, line in enumerate(data.decode("utf-8", "strict").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if match is None:
            raise IntegrationError(f"malformed FILES.sha256 row {line_number}")
        digest, name = match.groups()
        pure = PurePosixPath(name)
        if pure.is_absolute() or "\\" in name or any(part in {"", ".", ".."} for part in pure.parts):
            raise IntegrationError(f"unsafe checksum path: {name!r}")
        key = unicodedata.normalize("NFKC", name).casefold()
        if any(unicodedata.normalize("NFKC", old).casefold() == key for old in rows):
            raise IntegrationError(f"duplicate checksum path: {name!r}")
        rows[name] = digest
    if len(rows) != EXPECTED_CHECKSUM_ROWS:
        raise IntegrationError(f"checksum row mismatch: expected {EXPECTED_CHECKSUM_ROWS}, got {len(rows)}")
    return rows


def _validate_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$", *, root: Mapping[str, Any] | None = None) -> None:
    import math

    root = root or schema
    if "oneOf" in schema:
        errors = []
        for option in schema["oneOf"]:
            try:
                _validate_schema(value, option, path, root=root)
                break
            except IntegrationError as exc:
                errors.append(str(exc))
        else:
            raise IntegrationError(f"{path} does not match oneOf")
        return
    if "enum" in schema and value not in schema["enum"]:
        raise IntegrationError(f"{path} is not an allowed enum value")
    expected_type = schema.get("type")
    if expected_type is not None:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_validate_type(value, item) for item in types):
            raise IntegrationError(f"{path} has wrong type")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise IntegrationError(f"{path} is shorter than minLength")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise IntegrationError(f"{path} is not date-time") from exc
    if isinstance(value, int) and not isinstance(value, bool) and value < schema.get("minimum", value):
        raise IntegrationError(f"{path} is below minimum")
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise IntegrationError(f"{path} missing required property {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise IntegrationError(f"{path} has unknown properties: {sorted(unknown)}")
        for key, child in properties.items():
            if key in value:
                _validate_schema(value[key], child, f"{path}.{key}", root=root)
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                _validate_schema(item, items, f"{path}[{index}]", root=root)


def _validate_registry(manifest: Mapping[str, Any], registry: Mapping[str, Any], files: Mapping[str, zipfile.ZipInfo]) -> None:
    if manifest.get("apiVersion") != DELTA_API_VERSION or manifest.get("kind") != "KernelExtensionDeltaPackage":
        raise IntegrationError("delta manifest identity drifted")
    metadata = manifest.get("metadata")
    spec = manifest.get("spec")
    if not isinstance(metadata, Mapping) or not isinstance(spec, Mapping):
        raise IntegrationError("delta manifest shape is invalid")
    if metadata.get("version") != PACKAGE_VERSION or metadata.get("packageId") != f"{ARCHIVE_ROOT}" or metadata.get("incrementalOnly") is not True:
        raise IntegrationError("delta manifest version/package identity drifted")
    base = spec.get("base", {})
    scope = spec.get("scope", {})
    if base.get("name") != BASE_PACKAGE or base.get("exactVersion") != BASE_VERSION or base.get("compositeVersionAfterInstall") != PACKAGE_VERSION:
        raise IntegrationError("delta base contract is not exact v3.0.0")
    if scope.get("newKernels") != 0 or scope.get("newRoutableBusinessLines") != 0 or scope.get("kernelExtensionSkills") != EXPECTED_EXTENSION_SKILLS or scope.get("preservesRoutableSkillCount") != 16:
        raise IntegrationError("delta scope count drifted")
    if not isinstance(registry, Mapping) or registry.get("version") != PACKAGE_VERSION or registry.get("routable") is not False:
        raise IntegrationError("delta registry identity drifted")
    entries = registry.get("entries")
    if not isinstance(entries, list) or len(entries) != EXPECTED_EXTENSION_SKILLS:
        raise IntegrationError("delta registry entry count drifted")
    expected_ids = {f"ELMOS-V3D-{index:03d}" for index in range(1, EXPECTED_EXTENSION_SKILLS + 1)}
    actual_ids: set[str] = set()
    actual_names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise IntegrationError("delta registry entry is not an object")
        entry_id = entry.get("id")
        name = entry.get("name")
        path = entry.get("path")
        if not isinstance(entry_id, str) or entry_id in actual_ids or entry_id not in expected_ids:
            raise IntegrationError("delta registry IDs are not exact")
        if not isinstance(name, str) or name in actual_names or not name.startswith("elmos-"):
            raise IntegrationError("delta registry names are not exact")
        if entry.get("version") != PACKAGE_VERSION or entry.get("routable") is not False or entry.get("priority") not in {"P0", "P1"}:
            raise IntegrationError(f"delta registry entry flags drifted: {name}")
        if not isinstance(entry.get("ownerKernels"), list) or not entry["ownerKernels"] or any(owner not in {f"K{i}" for i in range(1, 9)} for owner in entry["ownerKernels"]):
            raise IntegrationError(f"delta registry owner drifted: {name}")
        if not isinstance(path, str) or f"payload/skills/extensions/{path}" not in files:
            raise IntegrationError(f"delta registry source path missing: {name}")
        actual_ids.add(entry_id)
        actual_names.add(name)
    if actual_ids != expected_ids:
        raise IntegrationError("delta registry ID set drifted")


@dataclass(frozen=True)
class ArchiveAudit:
    archive_sha256: str
    archive_bytes: int
    member_hashes: Mapping[str, str]
    payload_hashes: Mapping[str, str]
    manifest: Mapping[str, Any]
    registry: Mapping[str, Any]
    schemas: Mapping[str, Any]
    examples: Mapping[str, Any]

    @property
    def extension_count(self) -> int:
        return len(self.registry["entries"])

    def summary(self, *, implementation_status: str = "DECLARED_RUNTIME_UNQUALIFIED") -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
            "archive": {"sha256": self.archive_sha256, "bytes": self.archive_bytes, "entries": EXPECTED_ENTRIES, "files": EXPECTED_FILES, "uncompressed_bytes": EXPECTED_UNCOMPRESSED_BYTES, "checksum_rows": EXPECTED_CHECKSUM_ROWS},
            "counts": {"extensionSkills": self.extension_count, "P0": sum(entry["priority"] == "P0" for entry in self.registry["entries"]), "P1": sum(entry["priority"] == "P1" for entry in self.registry["entries"]), "schemas": len(self.schemas), "payloadFiles": len(self.payload_hashes), "adapterProfiles": EXPECTED_ADAPTER_PROFILES, "regoModules": EXPECTED_REGO_MODULES, "databaseMigrations": 1},
            "security": {"archiveContentExecuted": False, "archiveExecutableContentMaterialized": False, "archiveInstructionContentMaterialized": False, "referenceImplementationMaterialized": False, "checksumsVerified": EXPECTED_CHECKSUM_ROWS, "schemasValidated": len(self.schemas)},
            "implementation_status": implementation_status,
            "external_runtime_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }


def audit_archive(path: Path) -> ArchiveAudit:
    snapshot = _read_stable(path, expected_size=ARCHIVE_BYTES, limit=ARCHIVE_BYTES)
    archive_digest = _sha256(snapshot)
    if archive_digest != ARCHIVE_SHA256:
        raise IntegrationError(f"archive SHA-256 mismatch: expected {ARCHIVE_SHA256}, got {archive_digest}")
    try:
        archive = zipfile.ZipFile(io.BytesIO(snapshot), "r")
    except zipfile.BadZipFile as exc:
        raise IntegrationError(f"invalid ZIP: {exc}") from exc
    with archive:
        if archive.comment:
            raise IntegrationError("ZIP comments are forbidden")
        files = _validate_infos(archive.infolist())
        checksums = _parse_checksums(_member_bytes(archive, files, "FILES.sha256"))
        if set(checksums) != set(files) - {"FILES.sha256"}:
            raise IntegrationError("FILES.sha256 does not cover exactly all non-manifest members")
        member_hashes: dict[str, str] = {}
        for name, info in files.items():
            data = _member_bytes(archive, files, name)
            member_hashes[name] = _sha256(data)
            if name != "FILES.sha256" and checksums.get(name) != member_hashes[name]:
                raise IntegrationError(f"member checksum mismatch: {name}")
        payload_obj = _strict_json(_member_bytes(archive, files, "PAYLOAD_HASHES.json"), "PAYLOAD_HASHES.json")
        if not isinstance(payload_obj, Mapping) or len(payload_obj) != EXPECTED_PAYLOAD_FILES:
            raise IntegrationError("PAYLOAD_HASHES payload count drifted")
        payload_hashes = {str(key): str(value) for key, value in payload_obj.items()}
        for name, claimed in payload_hashes.items():
            archive_name = "payload/" + name
            if archive_name not in member_hashes or claimed != member_hashes[archive_name]:
                raise IntegrationError(f"payload hash mismatch: {name}")
        manifest = _strict_json(_member_bytes(archive, files, "DELTA_MANIFEST.json"), "DELTA_MANIFEST.json")
        registry = _strict_json(_member_bytes(archive, files, "payload/skills/extensions/registry.v3.1.json"), "registry.v3.1.json")
        _validate_registry(manifest, registry, files)
        schemas: dict[str, Any] = {}
        examples: dict[str, Any] = {}
        for name in files:
            if name.startswith("payload/contracts/schemas/delta-v3.1/") and name.endswith(".schema.json"):
                schema = _strict_json(_member_bytes(archive, files, name), name)
                if not isinstance(schema, Mapping) or schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                    raise IntegrationError(f"schema draft drifted: {name}")
                schemas[name.removeprefix("payload/contracts/schemas/delta-v3.1/")] = schema
            if name.startswith("payload/contracts/examples/delta-v3.1/") and name.endswith(".example.json"):
                examples[name.removeprefix("payload/contracts/examples/delta-v3.1/")] = _strict_json(_member_bytes(archive, files, name), name)
        if len(schemas) != EXPECTED_SCHEMAS or len(examples) != EXPECTED_SCHEMAS:
            raise IntegrationError("schema/example count drifted")
        for filename, example in examples.items():
            schema_name = filename.removesuffix(".example.json") + ".schema.json"
            schema = schemas.get(schema_name)
            if schema is None:
                raise IntegrationError(f"example has no matching schema: {filename}")
            _validate_schema(example, schema, filename)
        return ArchiveAudit(archive_digest, len(snapshot), member_hashes, payload_hashes, manifest, registry, schemas, examples)


def _receipt_status(repo_root: Path, audit: ArchiveAudit) -> str:
    path = repo_root / RECEIPT_PATH
    if not path.exists() or path.is_symlink() or not path.is_file():
        return "DECLARED_RUNTIME_UNQUALIFIED"
    try:
        receipt = _strict_json(_read_stable(path, limit=1024 * 1024), str(path))
    except IntegrationError:
        return "DECLARED_RUNTIME_UNQUALIFIED"
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != "1.0.0" or receipt.get("archive_sha256") != audit.archive_sha256 or receipt.get("status") != "PASS":
        return "DECLARED_RUNTIME_UNQUALIFIED"
    tests = receipt.get("tests")
    if not isinstance(tests, Mapping) or tests.get("failed", 1) != 0 or tests.get("passed", 0) < 25:
        return "DECLARED_RUNTIME_UNQUALIFIED"
    if receipt.get("adapter_profile_negotiation") != "PASS":
        return "DECLARED_RUNTIME_UNQUALIFIED"
    return "LOCAL_EXECUTED_SELF_ATTESTED"


def _wrapper_text(entry: Mapping[str, Any], audit: ArchiveAudit, status: str) -> str:
    name = str(entry["name"])
    path = str(entry["path"])
    source_sha = audit.member_hashes["payload/skills/extensions/" + path]
    owner = ", ".join(str(value) for value in entry["ownerKernels"])
    return f'''---
name: "{name}"
description: "Internal Elmos v3.1 runtime-assurance extension; not independently routable."
version: "{PACKAGE_VERSION}"
priority: "{entry["priority"]}"
kind: "kernel-extension"
routable: false
metadata:
  source_package: "{ARCHIVE_ROOT}"
  source_version: "{PACKAGE_VERSION}"
  source_path: "{path}"
  source_sha256: "sha256:{source_sha}"
  owner_kernels: "{owner}"
  runtime_module: "elmos_proof_harness.delta"
  runtime_registry: "DELTA_SKILL_REGISTRY"
  runtime_entrypoint: "DeltaSkillRuntime.execute"
  implementation_status: "{status}"
  external_evidence_status: "NOT_RUN"
  certification_status: "NOT_CERTIFIED"
---
# {name}

This repository-owned wrapper binds the exact non-routable `{entry["id"]}`
extension to `elmos_proof_harness.delta`. The source ZIP is untrusted data;
its scripts, reference implementation, policies and instructions are never
executed as authority. Provider, database, executor, customer and production
effects require separately authorized evidence and remain `NOT_RUN` here.

Owner kernels: `{owner}`. The extension cannot create a ninth kernel or a new
routable business line. Unknown, stale, lossy, conflicting and unsupported
states fail closed.
'''


def _compiled_contract(entry: Mapping[str, Any], audit: ArchiveAudit, status: str) -> bytes:
    value = {
        "schema_version": "1.0.0",
        "kind": "elmos.v3.1.delta-skill-contract",
        "name": entry["name"],
        "skill_id": entry["id"],
        "version": PACKAGE_VERSION,
        "priority": entry["priority"],
        "routable": False,
        "source": {"package": ARCHIVE_ROOT, "path": entry["path"], "sha256": "sha256:" + audit.member_hashes["payload/skills/extensions/" + entry["path"]]},
        "owners": entry["ownerKernels"],
        "runtime": {"module": "elmos_proof_harness.delta", "registry": "DELTA_SKILL_REGISTRY", "entrypoint": "DeltaSkillRuntime.execute"},
        "permissions": {"network": "default-deny", "secrets": "never-in-prompts-or-logs", "side_effects": "typed-authority-required"},
        "implementation_status": status,
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    return _json_bytes(value)


def _openai_yaml(entry: Mapping[str, Any], status: str) -> bytes:
    text = f'''interface:
  display_name: "{entry["name"]}"
  short_description: "Internal v3.1 runtime-assurance extension"
  default_prompt: "Invoke the exact non-routable {entry["id"]} handler with typed, tenant-bound input."
runtime:
  module: "elmos_proof_harness.delta"
  registry: "DELTA_SKILL_REGISTRY"
  entrypoint: "DeltaSkillRuntime.execute"
  routable: false
  implementation_status: "{status}"
security:
  network: "default-deny"
  external_effects: "not-authorized"
'''
    return text.encode()


def build_outputs(audit: ArchiveAudit, *, status: str) -> dict[Path, bytes]:
    outputs: dict[Path, bytes] = {}
    # JSON contracts and examples are inert, digest-bound source data.  API,
    # policy and adapter text is retained separately as data; no source
    # executable or instruction member is materialized.
    for filename in sorted(audit.schemas):
        outputs[ENGINE_ROOT / "schemas/delta-v3.1" / filename] = _json_bytes(audit.schemas[filename])
    for filename in sorted(audit.examples):
        outputs[ENGINE_ROOT / "examples/delta-v3.1" / filename] = _json_bytes(audit.examples[filename])
    with zipfile.ZipFile(io.BytesIO(_read_stable(Path.cwd() / ARCHIVE_RELATIVE_PATH, expected_size=ARCHIVE_BYTES, limit=ARCHIVE_BYTES))) as archive:
        # The second snapshot is checked by audit before this function is
        # called; read only bounded declarative assets and bind each to its
        # verified member digest.
        files = _validate_infos(archive.infolist())
        safe_assets = {
            "payload/api/delta-v3.1/": ENGINE_ROOT / "api/delta-v3.1",
            "payload/harness/adapters/delta-v3.1/": ENGINE_ROOT / "adapters/delta-v3.1",
            "payload/observability/delta-v3.1/": ENGINE_ROOT / "observability/delta-v3.1",
            "payload/policy/delta-rego/": ENGINE_ROOT / "policies/delta-v3.1",
            "payload/verification/": ENGINE_ROOT / "verification/delta-v3.1",
        }
        for prefix, target_root in safe_assets.items():
            for member in sorted(files):
                if not member.startswith(prefix) or member.endswith("/"):
                    continue
                relative = member.removeprefix(prefix)
                if not relative or PurePosixPath(relative).name in {"tests.yaml"}:
                    # Rego tests are source declarations, not a runtime input.
                    continue
                outputs[target_root / relative] = _member_bytes(archive, files, member)
        migration = _member_bytes(archive, files, "payload/database/delta-migrations/V304__harness_runtime_assurance_delta.sql")
        outputs[ENGINE_ROOT / "migrations/V304__harness_runtime_assurance_delta.sql"] = migration
    outputs[DELTA_ROOT / ".source-data/DELTA_MANIFEST.json"] = _json_bytes(audit.manifest)
    outputs[DELTA_ROOT / ".source-data/registry.v3.1.json"] = _json_bytes(audit.registry)
    outputs[DELTA_ROOT / ".source-data/PAYLOAD_HASHES.json"] = _json_bytes(audit.payload_hashes)
    boundary = {"schema_version": "1.0.0", "archive_sha256": audit.archive_sha256, "base_version": BASE_VERSION, "composite_version": PACKAGE_VERSION, "archive_content_executed": False, "instruction_content_materialized": False, "reference_implementation_materialized": False, "local_qualification": status, "external_runtime_status": "NOT_RUN", "certification_status": "NOT_CERTIFIED"}
    outputs[DELTA_ROOT / "source-boundary.json"] = _json_bytes(boundary)
    for entry in audit.registry["entries"]:
        for root in (Path(".agents/skills"), Path("agent-skills/runtime")):
            base = root / str(entry["name"])
            outputs[base / "SKILL.md"] = _wrapper_text(entry, audit, status).encode()
            outputs[base / "compiled-contract.json"] = _compiled_contract(entry, audit, status)
            outputs[base / "agents/openai.yaml"] = _openai_yaml(entry, status)
    return outputs


def _validate_output_path(path: Path) -> None:
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise IntegrationError(f"unsafe generated output path: {path}")
    allowed = (Path(".agents/skills"), Path("agent-skills/runtime"), DELTA_ROOT, ENGINE_ROOT / "schemas/delta-v3.1", ENGINE_ROOT / "examples/delta-v3.1", ENGINE_ROOT / "api/delta-v3.1", ENGINE_ROOT / "adapters/delta-v3.1", ENGINE_ROOT / "observability/delta-v3.1", ENGINE_ROOT / "policies/delta-v3.1", ENGINE_ROOT / "verification/delta-v3.1", ENGINE_ROOT / "migrations")
    if not any(path == root or root in path.parents for root in allowed):
        raise IntegrationError(f"generated output outside delta-owned roots: {path}")


def _parent_fd(root_fd: int, relative: Path, *, create: bool) -> tuple[int, str]:
    parts = list(relative.parts)
    if not parts:
        raise IntegrationError("empty output path")
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    raise IntegrationError(f"missing output directory: {relative}") from None
                os.mkdir(part, 0o755, dir_fd=current)
                metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise IntegrationError(f"unsafe output directory: {relative}")
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        return current, parts[-1]
    except BaseException:
        os.close(current)
        raise


def _read_at(root_fd: int, relative: Path) -> tuple[bytes, int] | None:
    parent, name = _parent_fd(root_fd, relative, create=False)
    try:
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
        except FileNotFoundError:
            return None
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise IntegrationError(f"existing output is not regular: {relative}")
            data = b"".join(iter(lambda: os.read(fd, MAX_MEMBER_BYTES), b""))
            if len(data) != metadata.st_size:
                raise IntegrationError(f"existing output changed while reading: {relative}")
            return data, stat.S_IMODE(metadata.st_mode)
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def _write_at(root_fd: int, relative: Path, data: bytes, mode: int = 0o644) -> None:
    parent, name = _parent_fd(root_fd, relative, create=True)
    temporary = f".{name}.delta-{uuid.uuid4().hex}"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary, flags, mode, dir_fd=parent)
        try:
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def install_outputs(repo_root: Path, outputs: Mapping[Path, bytes], *, failure_after: int | None = None) -> dict[str, Any]:
    for path, data in outputs.items():
        _validate_output_path(path)
        if not isinstance(data, bytes):
            raise IntegrationError(f"output must be bytes: {path}")
    root = repo_root.resolve(strict=True)
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    backups: dict[Path, tuple[bytes, int] | None] = {}
    published: list[Path] = []
    try:
        for path in sorted(outputs):
            backups[path] = _read_at(root_fd, path)
        for index, path in enumerate(sorted(outputs), 1):
            _write_at(root_fd, path, outputs[path])
            published.append(path)
            if failure_after is not None and index >= failure_after:
                raise IntegrationError("injected integration failure")
        for path, data in outputs.items():
            current = _read_at(root_fd, path)
            if current is None or current[0] != data:
                raise IntegrationError(f"output verification failed: {path}")
        return {"status": "PASS", "files": len(outputs), "sha256": _sha256(b"".join(outputs[path] for path in sorted(outputs)))}
    except BaseException as original:
        try:
            for path in reversed(published):
                prior = backups[path]
                if prior is None:
                    parent, name = _parent_fd(root_fd, path, create=False)
                    try:
                        try:
                            os.unlink(name, dir_fd=parent)
                        except FileNotFoundError:
                            pass
                    finally:
                        os.close(parent)
                else:
                    _write_at(root_fd, path, prior[0], prior[1])
        except BaseException as rollback_error:
            raise IntegrationError(f"delta install failed and rollback failed: {rollback_error}") from original
        raise
    finally:
        os.close(root_fd)


def verify_installation(repo_root: Path, outputs: Mapping[Path, bytes]) -> dict[str, Any]:
    root_fd = os.open(repo_root.resolve(strict=True), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        for path, data in outputs.items():
            current = _read_at(root_fd, path)
            if current is None or current[0] != data:
                raise IntegrationError(f"delta installation drifted: {path}")
        return {"status": "PASS", "files": len(outputs)}
    finally:
        os.close(root_fd)


def _lock_path(repo_root: Path) -> Path:
    return Path(tempfile.gettempdir()) / ("elmos-harness-runtime-delta-" + hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:24] + ".lock")


def run(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve(strict=True)
    archive_path = Path(args.archive)
    if not archive_path.is_absolute():
        archive_path = repo_root / archive_path
    audit = audit_archive(archive_path)
    status = _receipt_status(repo_root, audit)
    outputs = build_outputs(audit, status=status)
    if args.audit:
        return {"action": "audit", **audit.summary(implementation_status=status)}
    with _lock_path(repo_root).open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if args.install:
            result = install_outputs(repo_root, outputs)
            return {"action": "install", **audit.summary(implementation_status=status), "installation": result}
        result = verify_installation(repo_root, outputs)
        return {"action": "check", **audit.summary(implementation_status=status), "installation": result}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--archive", type=Path, default=ARCHIVE_RELATIVE_PATH)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--audit", action="store_true")
    action.add_argument("--install", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (IntegrationError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
