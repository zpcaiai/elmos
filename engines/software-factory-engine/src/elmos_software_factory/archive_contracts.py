"""Repository-owned safe equivalents for the two inert archive scripts.

The repository importer, this module, and the recorded qualification path do
not import, compile, or execute the original Python members.  This module reads
the neutralized canonical source as bounded data, reconstructs the logical
archive layout, implements the useful readiness and validation checks, and
emits a deterministic receipt with the original script byte identities.  No
claim is made about historical or manual activity outside those paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import canonical_digest


MAX_SOURCE_FILES = 1024
MAX_SOURCE_FILE_BYTES = 4 * 1024 * 1024
MAX_SOURCE_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SOURCE_DEPTH = 12
MAX_SOURCE_DIRECTORIES = 1024
MAX_SOURCE_ENTRIES = 2048
SCRIPT_CONTRACTS = {
    "scripts/score_readiness.py": {
        "sha256": "sha256:a17057412f9b574b5e1445cb6191ed4a4b0a8e1f09bcf59fb12cbbabb53c3dc7",
        "size_bytes": 1507,
        "source_mode": "0755",
        "materialized_path": "_neutralized-executable-data/scripts/score_readiness.py.source-data",
    },
    "scripts/validate_packages.py": {
        "sha256": "sha256:834aae29a1ba1ffc48d9ecf621b9e72e7a0e96e9cf74e255abf30f077921ad90",
        "size_bytes": 4743,
        "source_mode": "0755",
        "materialized_path": "_neutralized-executable-data/scripts/validate_packages.py.source-data",
    },
}
_ROOT_REQUIRED = (
    "README.md",
    "SKILL.md",
    "AGENTS.md",
    "ELMOS_WORKFLOW.md",
    "PHASE-MAP.md",
    "SOURCE-MANIFEST.md",
    "SOURCE-TO-CAPABILITY-MATRIX.md",
    "UPSTREAM-CAPABILITY-EXTRACTION.md",
    "DETAILED-PHASE-DELIVERY-PLAN.md",
    "ELMOS-REFERENCE-ARCHITECTURE.md",
    "KPI-AND-BENCHMARK-FRAMEWORK.md",
    "COMMERCIAL-GA-CHECKLIST.md",
    "LICENSE-AND-ATTRIBUTION.md",
    "manifest.json",
)
_PACKAGE_REQUIRED = (
    "README.md",
    "SKILL.md",
    "PRODUCT-CAPABILITY-SPEC.md",
    "ARCHITECTURE.md",
    "PHASE-PLAN.md",
    "INTERFACE-CONTRACTS.md",
    "DATA-AND-EVENT-MODEL.md",
    "SECURITY-AND-GOVERNANCE.md",
    "OBSERVABILITY-AND-SLO.md",
    "BENCHMARKS-AND-EVALS.md",
    "ACCEPTANCE-GATES.md",
    "FAILURE-MODES-AND-RECOVERY.md",
    "IMPLEMENTATION-BACKLOG.md",
    "examples/package-config.yaml",
    "schemas/package-config.schema.json",
    "manifest.json",
)
_SCHEMA_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "enum",
        "const",
        "pattern",
        "minLength",
        "maxLength",
        "format",
        "minimum",
        "maximum",
        "default",
    }
)
_PACKAGE_DIRECTORY = re.compile(r"^0[0-7]-[a-z0-9-]+$")
_FRONTMATTER_NAME = re.compile(r"(?m)^name:\s*[^\s].*$")
_FRONTMATTER_DESCRIPTION = re.compile(r"(?m)^description:\s*[^\s].*$")
_PLAIN_SCALAR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class ArchiveContractError(ValueError):
    """Raised when the neutralized archive data is unsafe or violates its contract."""


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveContractError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _json_bytes(value: bytes, label: str) -> Any:
    try:
        return json.loads(
            value.decode("utf-8"),
            object_pairs_hook=_duplicates,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ArchiveContractError(f"{label} contains invalid number {item}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArchiveContractError(f"{label} is not strict UTF-8 JSON: {exc}") from exc


def _required_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int):
        raise ArchiveContractError(f"safe archive inspection requires {name}")
    return value


def _binding_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)


def _stable_metadata(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _assert_entry_binding(
    directory_descriptor: int,
    name: str,
    expected: os.stat_result,
    label: str,
) -> None:
    try:
        observed = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except OSError as exc:
        raise ArchiveContractError(f"{label} changed during inspection") from exc
    if _stable_metadata(observed) != _stable_metadata(expected):
        raise ArchiveContractError(f"{label} changed during inspection")


def _read_regular_at(
    directory_descriptor: int,
    name: str,
    expected: os.stat_result,
    maximum: int,
    label: str,
) -> tuple[bytes, int]:
    flags = (
        os.O_RDONLY
        | _required_open_flag("O_NOFOLLOW")
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as exc:
        raise ArchiveContractError(f"{label} cannot be opened safely") from exc
    try:
        initial = os.fstat(descriptor)
        if _binding_identity(initial) != _binding_identity(expected):
            raise ArchiveContractError(f"{label} changed before it was opened")
        if not stat.S_ISREG(initial.st_mode) or initial.st_size < 0 or initial.st_size > maximum:
            raise ArchiveContractError(f"{label} must be a bounded regular file")
        if stat.S_IMODE(initial.st_mode) & 0o111:
            raise ArchiveContractError(f"canonical source contains an executable regular file: {label}")
        chunks: list[bytes] = []
        observed_size = 0
        try:
            while True:
                chunk = os.read(
                    descriptor,
                    min(1024 * 1024, maximum + 1 - observed_size),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                observed_size += len(chunk)
                if observed_size > maximum:
                    raise ArchiveContractError(f"{label} exceeded its byte budget")
        except OSError as exc:
            raise ArchiveContractError(f"{label} could not be read safely") from exc
        final = os.fstat(descriptor)
        if observed_size != initial.st_size or _stable_metadata(initial) != _stable_metadata(final):
            raise ArchiveContractError(f"{label} changed while being read")
        _assert_entry_binding(directory_descriptor, name, initial, label)
        return b"".join(chunks), stat.S_IMODE(initial.st_mode)
    finally:
        os.close(descriptor)


def _open_directory_at(
    directory_descriptor: int,
    name: str,
    expected: os.stat_result,
    label: str,
) -> tuple[int, os.stat_result]:
    flags = (
        os.O_RDONLY
        | _required_open_flag("O_NOFOLLOW")
        | _required_open_flag("O_DIRECTORY")
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as exc:
        raise ArchiveContractError(f"{label} cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise ArchiveContractError(f"{label} cannot be inspected safely") from exc
    if not stat.S_ISDIR(metadata.st_mode) or _binding_identity(metadata) != _binding_identity(expected):
        os.close(descriptor)
        raise ArchiveContractError(f"{label} changed before it was opened")
    return descriptor, metadata


def _open_root_directory(root: Path) -> tuple[int, os.stat_result]:
    flags = (
        os.O_RDONLY
        | _required_open_flag("O_NOFOLLOW")
        | _required_open_flag("O_DIRECTORY")
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        expected = os.stat(root, follow_symlinks=False)
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise ArchiveContractError("canonical source root cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise ArchiveContractError("canonical source root cannot be inspected safely") from exc
    if (
        not stat.S_ISDIR(expected.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or _binding_identity(expected) != _binding_identity(metadata)
    ):
        os.close(descriptor)
        raise ArchiveContractError("canonical source root changed while being opened")
    return descriptor, metadata


def _assert_root_binding(root: Path, expected: os.stat_result) -> None:
    try:
        observed = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        raise ArchiveContractError("canonical source root binding changed during inspection") from exc
    if _stable_metadata(observed) != _stable_metadata(expected):
        raise ArchiveContractError("canonical source root binding changed during inspection")


def _logical_path(physical: str) -> str:
    for logical, contract in SCRIPT_CONTRACTS.items():
        if physical == contract["materialized_path"]:
            return logical
    if physical == "_neutralized-instruction-data/AGENTS.md.source-data":
        return "AGENTS.md"
    if physical.endswith("/SKILL.md.source-data") or physical == "SKILL.md.source-data":
        return physical.removesuffix(".source-data")
    return physical


def _scan(root: Path) -> tuple[dict[str, tuple[bytes, int, str]], dict[str, str]]:
    supplied = root.expanduser()
    logical: dict[str, tuple[bytes, int, str]] = {}
    mapping: dict[str, str] = {}
    count = 0
    total = 0
    directory_count = 0
    entry_count = 0

    def visit(
        directory_descriptor: int,
        prefix: PurePosixPath,
        depth: int,
    ) -> None:
        nonlocal count, total, directory_count, entry_count
        if depth > MAX_SOURCE_DEPTH:
            raise ArchiveContractError("canonical source exceeds the directory depth budget")
        directory_count += 1
        if directory_count > MAX_SOURCE_DIRECTORIES:
            raise ArchiveContractError("canonical source exceeds the directory-count budget")
        try:
            names = sorted(os.listdir(directory_descriptor))
        except (OSError, TypeError) as exc:
            raise ArchiveContractError("canonical source cannot be enumerated") from exc
        entry_count += len(names)
        if entry_count > MAX_SOURCE_ENTRIES:
            raise ArchiveContractError("canonical source exceeds the entry-count budget")
        if len(names) != len(set(names)):
            raise ArchiveContractError("canonical source enumeration contains duplicates")
        for name in names:
            if (
                not isinstance(name, str)
                or name in {".", ".."}
                or "/" in name
                or "\\" in name
                or "\x00" in name
            ):
                raise ArchiveContractError("canonical source contains an unsafe name")
            relative = (prefix / name).as_posix()
            try:
                metadata = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise ArchiveContractError(
                    f"canonical source entry changed during inspection: {relative}"
                ) from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise ArchiveContractError(f"canonical source contains a symlink: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                child_descriptor, opened = _open_directory_at(
                    directory_descriptor,
                    name,
                    metadata,
                    relative,
                )
                try:
                    visit(child_descriptor, prefix / name, depth + 1)
                finally:
                    os.close(child_descriptor)
                _assert_entry_binding(
                    directory_descriptor,
                    name,
                    opened,
                    relative,
                )
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ArchiveContractError(f"canonical source contains a special file: {relative}")
            if stat.S_IMODE(metadata.st_mode) & 0o111:
                raise ArchiveContractError(
                    f"canonical source contains an executable regular file: {relative}"
                )
            count += 1
            if count > MAX_SOURCE_FILES:
                raise ArchiveContractError("canonical source exceeds the file-count budget")
            content, mode = _read_regular_at(
                directory_descriptor,
                name,
                metadata,
                MAX_SOURCE_FILE_BYTES,
                relative,
            )
            total += len(content)
            if total > MAX_SOURCE_TOTAL_BYTES:
                raise ArchiveContractError("canonical source exceeds the total-byte budget")
            logical_name = _logical_path(relative)
            if logical_name in logical:
                raise ArchiveContractError(f"canonical source logical path collision: {logical_name}")
            logical[logical_name] = (content, mode, relative)
            if logical_name != relative:
                mapping[logical_name] = relative
        try:
            final_names = sorted(os.listdir(directory_descriptor))
        except (OSError, TypeError) as exc:
            raise ArchiveContractError("canonical source changed during enumeration") from exc
        if final_names != names:
            raise ArchiveContractError("canonical source changed during enumeration")

    root_descriptor, root_metadata = _open_root_directory(supplied)
    try:
        visit(root_descriptor, PurePosixPath(), 0)
    finally:
        os.close(root_descriptor)
    _assert_root_binding(supplied, root_metadata)
    return logical, mapping


def _schema_meta(schema: object, label: str, *, root: bool = True) -> None:
    if not isinstance(schema, dict):
        raise ArchiveContractError(f"{label} schema node must be an object")
    unknown = sorted(set(schema) - _SCHEMA_KEYWORDS)
    if unknown:
        raise ArchiveContractError(f"{label} contains unsupported schema keywords: {unknown}")
    if root and schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ArchiveContractError(f"{label} must declare JSON Schema draft 2020-12")
    schema_type = schema.get("type")
    allowed_types = {"object", "array", "string", "integer", "number", "boolean", "null"}
    if isinstance(schema_type, list):
        if (
            not schema_type
            or any(item not in allowed_types for item in schema_type)
            or len(set(schema_type)) != len(schema_type)
        ):
            raise ArchiveContractError(f"{label}.type union is unsupported")
    elif schema_type is not None:
        if not isinstance(schema_type, str) or schema_type not in allowed_types:
            raise ArchiveContractError(f"{label}.type is unsupported")
    required = schema.get("required")
    if required is not None:
        if not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required):
            raise ArchiveContractError(f"{label}.required must be a string array")
        if len(set(required)) != len(required):
            raise ArchiveContractError(f"{label}.required contains duplicates")
    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            raise ArchiveContractError(f"{label}.properties must be an object")
        for name, child in properties.items():
            if not isinstance(name, str) or not name:
                raise ArchiveContractError(f"{label}.properties contains an invalid name")
            _schema_meta(child, f"{label}.properties.{name}", root=False)
    additional = schema.get("additionalProperties")
    if not isinstance(additional, (bool, dict)) and additional is not None:
        raise ArchiveContractError(f"{label}.additionalProperties is invalid")
    if isinstance(additional, dict):
        _schema_meta(additional, f"{label}.additionalProperties", root=False)
    items = schema.get("items")
    if items is not None:
        _schema_meta(items, f"{label}.items", root=False)
    for field in ("minItems", "maxItems", "minLength", "maxLength"):
        value = schema.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ArchiveContractError(f"{label}.{field} must be a non-negative integer")
    if "pattern" in schema:
        try:
            re.compile(schema["pattern"])
        except (TypeError, re.error) as exc:
            raise ArchiveContractError(f"{label}.pattern is invalid") from exc
    if schema.get("format") not in {None, "date-time"}:
        raise ArchiveContractError(f"{label}.format is unsupported")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ArchiveContractError(f"{label}.enum must be a non-empty array")


def _json_type(value: object, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[expected]


def _validate_instance(value: object, schema: dict[str, Any], label: str) -> None:
    expected_type = schema.get("type")
    expected_types = (
        expected_type
        if isinstance(expected_type, list)
        else ([expected_type] if isinstance(expected_type, str) else [])
    )
    if expected_type is not None and not any(_json_type(value, item) for item in expected_types):
        raise ArchiveContractError(f"{label} must have JSON type {expected_type}")
    if "const" in schema and value != schema["const"]:
        raise ArchiveContractError(f"{label} differs from const")
    if "enum" in schema and value not in schema["enum"]:
        raise ArchiveContractError(f"{label} is outside enum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = sorted(set(required) - set(value))
        if missing:
            raise ArchiveContractError(f"{label} is missing required fields: {missing}")
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            child = properties.get(key)
            if child is not None:
                _validate_instance(item, child, f"{label}.{key}")
            elif additional is False:
                raise ArchiveContractError(f"{label} contains unsupported field {key}")
            elif isinstance(additional, dict):
                _validate_instance(item, additional, f"{label}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 2**63 - 1):
            raise ArchiveContractError(f"{label} array length violates its bounds")
        if schema.get("uniqueItems") and len({canonical_digest(item) for item in value}) != len(value):
            raise ArchiveContractError(f"{label} array values must be unique")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_instance(item, schema["items"], f"{label}[{index}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 2**63 - 1):
            raise ArchiveContractError(f"{label} string length violates its bounds")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise ArchiveContractError(f"{label} does not match pattern")
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ArchiveContractError(f"{label} is not an ISO-8601 timestamp") from exc
            if parsed.tzinfo is None:
                raise ArchiveContractError(f"{label} timestamp lacks timezone")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ArchiveContractError(f"{label} number violates its bounds")


def _yaml_scalar(text: str, label: str) -> object:
    if text.startswith('"'):
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ArchiveContractError(f"{label} has an invalid quoted scalar") from exc
        if not isinstance(value, str):
            raise ArchiveContractError(f"{label} quoted scalar must be a string")
        return value
    if text in {"true", "false"}:
        return text == "true"
    if re.fullmatch(r"0|[1-9][0-9]*", text):
        return int(text)
    if _PLAIN_SCALAR.fullmatch(text) is None:
        raise ArchiveContractError(f"{label} contains unsupported YAML syntax")
    return text


def _yaml_subset(content: bytes, label: str) -> dict[str, Any]:
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise ArchiveContractError(f"{label} is not UTF-8") from exc
    if len(content) > 64 * 1024 or "\t" in text or "\x00" in text:
        raise ArchiveContractError(f"{label} exceeds the safe YAML subset")
    forbidden = ("&", "*", "!", "<<", "|", ">", "{", "}", "[", "]", "#")
    if any(item in text for item in forbidden):
        raise ArchiveContractError(f"{label} uses forbidden YAML features")
    result: dict[str, Any] = {}
    section: str | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            if ":" not in line:
                raise ArchiveContractError(f"{label}:{number} is not a mapping entry")
            key, scalar = line.split(":", 1)
            if not key or key in result:
                raise ArchiveContractError(f"{label}:{number} has duplicate or invalid key")
            scalar = scalar.strip()
            if scalar:
                result[key] = _yaml_scalar(scalar, f"{label}:{number}")
                section = None
            else:
                section = key
                result[key] = None
            continue
        if indent != 2 or section is None:
            raise ArchiveContractError(f"{label}:{number} exceeds the supported indentation")
        if line.startswith("- "):
            if result[section] is None:
                result[section] = []
            if not isinstance(result[section], list):
                raise ArchiveContractError(f"{label}:{number} mixes sequence and mapping")
            result[section].append(_yaml_scalar(line[2:].strip(), f"{label}:{number}"))
        else:
            if ":" not in line:
                raise ArchiveContractError(f"{label}:{number} is not a nested mapping entry")
            key, scalar = line.split(":", 1)
            if result[section] is None:
                result[section] = {}
            if not isinstance(result[section], dict) or key in result[section]:
                raise ArchiveContractError(f"{label}:{number} has duplicate or mixed nested key")
            result[section][key] = _yaml_scalar(scalar.strip(), f"{label}:{number}")
    if any(value is None for value in result.values()):
        raise ArchiveContractError(f"{label} contains an empty collection")
    return result


def _frontmatter(content: bytes, label: str) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise ArchiveContractError(f"{label} is not UTF-8") from exc
    if (
        not text.startswith("---\n")
        or _FRONTMATTER_NAME.search(text) is None
        or _FRONTMATTER_DESCRIPTION.search(text) is None
    ):
        raise ArchiveContractError(f"{label} has invalid Skill frontmatter")


def _validate_root_manifest(
    manifest: object,
    logical: dict[str, tuple[bytes, int, str]],
) -> None:
    if not isinstance(manifest, dict) or set(manifest) != {"files"}:
        raise ArchiveContractError("root manifest must contain only files")
    entries = manifest["files"]
    if not isinstance(entries, list) or len(entries) > MAX_SOURCE_FILES:
        raise ArchiveContractError("root manifest files must be a bounded array")
    observed: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ArchiveContractError(f"root manifest files[{index}] fields are invalid")
        path = entry["path"]
        expected = entry["sha256"]
        if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
            raise ArchiveContractError(f"root manifest files[{index}].path is unsafe")
        parsed = PurePosixPath(path)
        if any(part in {"", ".", ".."} for part in parsed.parts) or parsed.as_posix() != path:
            raise ArchiveContractError(f"root manifest files[{index}].path is unsafe")
        if path in observed:
            raise ArchiveContractError("root manifest contains duplicate paths")
        observed.add(path)
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ArchiveContractError(f"root manifest files[{index}].sha256 is invalid")
        record = logical.get(path)
        if record is None:
            raise ArchiveContractError(f"root manifest path is missing: {path}")
        if hashlib.sha256(record[0]).hexdigest() != expected:
            raise ArchiveContractError(f"root manifest digest mismatch: {path}")


def inspect_archive_contracts(source_root: Path) -> dict[str, Any]:
    logical, mapping = _scan(source_root)
    errors: list[str] = []
    scripts: list[dict[str, Any]] = []
    for path, expected in SCRIPT_CONTRACTS.items():
        record = logical.get(path)
        if record is None:
            raise ArchiveContractError(f"neutralized script source is missing: {path}")
        content, mode, physical = record
        observed = "sha256:" + hashlib.sha256(content).hexdigest()
        if observed != expected["sha256"] or len(content) != expected["size_bytes"]:
            raise ArchiveContractError(f"neutralized script bytes drifted: {path}")
        if physical != expected["materialized_path"] or mode & 0o111:
            raise ArchiveContractError(f"archive script was not neutralized as non-executable data: {path}")
        scripts.append(
            {
                "logical_path": path,
                "materialized_path": physical,
                "sha256": observed,
                "size_bytes": len(content),
                "source_mode": expected["source_mode"],
                "materialized_mode": f"{mode:04o}",
                "execution_state": "NOT_EXECUTED",
                "implementation_state": "REPOSITORY_OWNED_SAFE_REIMPLEMENTATION",
            }
        )
    package_roots = sorted(
        path
        for path in {PurePosixPath(name).parts[0] for name in logical}
        if _PACKAGE_DIRECTORY.fullmatch(path)
    )
    subskills = sorted(name for name in logical if re.fullmatch(r"0[0-7]-[^/]+/skills/[^/]+/SKILL\.md", name))
    package_manifests = sorted(name for name in logical if re.fullmatch(r"0[0-7]-[^/]+/manifest\.json", name))
    shared_schemas = sorted(name for name in logical if re.fullmatch(r"schemas/[^/]+\.json", name))
    readiness_checks = [
        ("8 top-level packages", len(package_roots) == 8, 15, f"{len(package_roots)} found"),
        ("shared schemas", len(shared_schemas) >= 10, 15, f"{len(shared_schemas)} found"),
        ("source pins", "SOURCE-MANIFEST.md" in logical, 10, "upstream isolation"),
        ("phase plan", "PHASE-MAP.md" in logical, 10, "implementation sequence"),
        ("benchmark framework", "KPI-AND-BENCHMARK-FRAMEWORK.md" in logical, 10, "quality measurement"),
        ("commercial GA checklist", "COMMERCIAL-GA-CHECKLIST.md" in logical, 10, "commercial operations"),
        ("on-demand subskills", len(subskills) >= 90, 15, f"{len(subskills)} found"),
        ("package manifests", len(package_manifests) == 8, 10, f"{len(package_manifests)} found"),
        ("integrity manifest", "manifest.json" in logical, 5, "root manifest presence"),
    ]
    score = sum(weight for _, passed, weight, _ in readiness_checks if passed)

    root_missing = sorted(path for path in _ROOT_REQUIRED if path not in logical)
    package_validation_count = 0
    schema_count = 0
    config_count = 0
    markdown_count = 0
    for name, (content, _, _) in logical.items():
        if name.endswith(".schema.json"):
            try:
                schema = _json_bytes(content, name)
                _schema_meta(schema, name)
                schema_count += 1
            except ArchiveContractError as exc:
                errors.append(str(exc))
        if name.endswith(".md"):
            markdown_count += 1
            try:
                text = content.decode("utf-8")
                if text.count("```") % 2:
                    errors.append(f"{name} has unbalanced Markdown code fences")
            except UnicodeError:
                errors.append(f"{name} is not UTF-8")
    for package in package_roots:
        missing = [relative for relative in _PACKAGE_REQUIRED if f"{package}/{relative}" not in logical]
        if missing:
            errors.append(f"{package} is missing package files: {missing}")
            continue
        try:
            _frontmatter(logical[f"{package}/SKILL.md"][0], f"{package}/SKILL.md")
            manifest = _json_bytes(logical[f"{package}/manifest.json"][0], f"{package}/manifest.json")
            package_manifest_schema = _json_bytes(
                logical["schemas/package-manifest.schema.json"][0],
                "schemas/package-manifest.schema.json",
            )
            _validate_instance(manifest, package_manifest_schema, f"{package}.manifest")
            package_schema = _json_bytes(
                logical[f"{package}/schemas/package-config.schema.json"][0],
                f"{package}/schemas/package-config.schema.json",
            )
            config = _yaml_subset(
                logical[f"{package}/examples/package-config.yaml"][0],
                f"{package}/examples/package-config.yaml",
            )
            _validate_instance(config, package_schema, f"{package}.package-config")
            config_count += 1
            expected_subskills = manifest.get("subskills") if isinstance(manifest, dict) else None
            if not isinstance(expected_subskills, list):
                raise ArchiveContractError(f"{package}/manifest.json subskills must be an array")
            observed_subskills = [name for name in subskills if name.startswith(f"{package}/skills/")]
            if len(expected_subskills) != len(observed_subskills):
                raise ArchiveContractError(f"{package} subskill count differs from manifest")
            for subskill in observed_subskills:
                _frontmatter(logical[subskill][0], subskill)
            package_validation_count += 1
        except ArchiveContractError as exc:
            errors.append(str(exc))
    examples = (
        ("examples/source-capability-ledger.example.json", "schemas/capability-ledger.schema.json"),
        ("examples/requirement-ledger.example.json", "schemas/requirement-ledger.schema.json"),
    )
    example_count = 0
    for example_path, schema_path in examples:
        try:
            example = _json_bytes(logical[example_path][0], example_path)
            schema = _json_bytes(logical[schema_path][0], schema_path)
            _validate_instance(example, schema, example_path)
            example_count += 1
        except (KeyError, ArchiveContractError) as exc:
            errors.append(f"example contract failed: {example_path}: {exc}")
    if "manifest.json" in logical:
        try:
            _validate_root_manifest(_json_bytes(logical["manifest.json"][0], "manifest.json"), logical)
        except ArchiveContractError as exc:
            errors.append(str(exc))
    tree_rows = [
        {
            "logical_path": name,
            "physical_path": record[2],
            "sha256": "sha256:" + hashlib.sha256(record[0]).hexdigest(),
            "size_bytes": len(record[0]),
            "materialized_mode": f"{record[1]:04o}",
        }
        for name, record in sorted(logical.items())
    ]
    body = {
        "schema_version": "1.0",
        "inspection_status": "PASSED" if not errors else "FAILED",
        "repository_reimplementation_state": "LOCAL_REIMPLEMENTED_AND_EXECUTED_SELF_ATTESTED",
        "source_validator_parity_state": (
            "SOURCE_LAYOUT_INCOMPATIBLE" if root_missing else ("PASSED" if not errors else "FAILED")
        ),
        "source_layout_incompatibilities": root_missing,
        "source_blueprint_presence_score": score,
        "source_blueprint_presence_score_maximum": 100,
        "source_blueprint_presence_score_authority": "NON_AUTHORITATIVE_BLUEPRINT_PRESENCE_ONLY",
        "readiness_checks": [
            {"name": name, "status": "PASSED" if passed else "FAILED", "weight": weight, "detail": detail}
            for name, passed, weight, detail in readiness_checks
        ],
        "safe_validation": {
            "package_count": len(package_roots),
            "package_validation_count": package_validation_count,
            "subskill_count": len(subskills),
            "schema_meta_validation_count": schema_count,
            "package_config_validation_count": config_count,
            "example_validation_count": example_count,
            "markdown_file_count": markdown_count,
            "errors": errors,
        },
        "source_tree_digest": canonical_digest(tree_rows),
        "source_file_count": len(tree_rows),
        "neutralized_path_mapping_count": len(mapping),
        "archive_scripts": scripts,
        "archive_scripts_executed": False,
        "active_archive_executables": [],
        "external_states": {
            "independent_holdout": "NOT_RUN",
            "provider_execution": "NOT_RUN",
            "production_execution": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
    }
    return {**body, "inspection_digest": canonical_digest(body)}
