"""Project-package, archive-safety, profiling, and repository-map operations."""

from __future__ import annotations

import ast
import base64
import bisect
import binascii
import fnmatch
import hashlib
import json
import math
import posixpath
import re
import struct
import tempfile
import unicodedata
import zipfile
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from typing import Any, BinaryIO, cast, overload


class ProjectContractError(ValueError):
    """Raised for unsafe or ambiguous project input."""


_DRIVE = re.compile(r"^[A-Za-z]:")
_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".gz")
_WINDOWS_RESERVED_COMPONENTS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_LANGUAGE_EXTENSIONS: dict[str, frozenset[str]] = {
    "Java": frozenset({".java"}),
    "Kotlin": frozenset({".kt", ".kts"}),
    "Python": frozenset({".py", ".pyi"}),
    "CSharp": frozenset({".cs"}),
    "Go": frozenset({".go"}),
    "Rust": frozenset({".rs"}),
    "Cpp": frozenset({".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"}),
    "PHP": frozenset({".php"}),
    "TypeScript": frozenset({".ts", ".tsx"}),
    "JavaScript": frozenset({".js", ".jsx", ".mjs", ".cjs"}),
    "ObjectiveC": frozenset({".m", ".mm"}),
    "Swift": frozenset({".swift"}),
    "Dart": frozenset({".dart"}),
}
_VENDORED = ("node_modules/**", "vendor/**", "third_party/**", "Pods/**", ".venv/**")
_GENERATED = ("dist/**", "build/**", "target/**", "out/**", "coverage/**", "*.min.js", "*.generated.*")
_CACHE = (".git/**", ".idea/**", ".vscode/**", "__pycache__/**", ".pytest_cache/**", ".mypy_cache/**")
_SECRET = re.compile(r"(?:^|/)(?:\.env(?:\..*)?|id_rsa|id_ed25519|.*\.(?:p12|pfx|pem|key|jks|keystore))$", re.I)
_MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVE_ENCODED_CHARS = ((_MAX_ARCHIVE_BYTES + 2) // 3) * 4
_MAX_ARCHIVE_ENTRIES = 10_000
_MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
_MAX_ARCHIVE_ENTRY_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
_MAX_ARCHIVE_COMPRESSION_RATIO = 100.0
# This implementation extracts one layer only. Nested containers are preserved
# as opaque, scanned first-layer assets and must enter a new intake operation
# before any further expansion.
_DEFAULT_ARCHIVE_NESTED_DEPTH = 1
_MAX_ARCHIVE_NESTED_DEPTH = 8
_ARCHIVE_STREAM_CHUNK_BYTES = 1024 * 1024
_MAX_REVIEW_ENTRIES = 50_000
_MAX_SECURITY_FINDINGS_PER_ENTRY = 1_000
_REVIEW_STATES = frozenset({"READY", "PENDING", "NEEDS_REVIEW", "BLOCKED", "QUARANTINED"})
_MAX_PROJECT_ENTRIES = 50_000
_MAX_PROJECT_ENTRY_BYTES = 1024 * 1024 * 1024 * 1024
_MAX_PROJECT_TOTAL_BYTES = 8 * 1024 * 1024 * 1024 * 1024
_MAX_SOURCE_FILES = 5_000
_MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024
_MAX_SOURCE_TOTAL_BYTES = 16 * 1024 * 1024
_MAX_AST_NODES_PER_FILE = 100_000
_MAX_SYMBOLS = 100_000
_MAX_SYMBOLS_PER_FILE = 20_000
_MAX_REPOSITORY_EDGES = 100_000
_MAX_REPOSITORY_MAP_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"sha256:[a-f0-9]{64}")


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProjectContractError("value must be finite JSON data") from exc


def _digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else _canonical(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _inputs(request: Mapping[str, Any]) -> Mapping[str, Any]:
    value = request.get("inputs")
    if not isinstance(value, Mapping):
        raise ProjectContractError("inputs must be an object")
    return value


def _sequence(value: Any, field: str, *, maximum: int = 200_000) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ProjectContractError(f"{field} must be an array")
    if len(value) > maximum:
        raise ProjectContractError(f"{field} exceeds the bounded item limit")
    return list(value)


def _bounded_int(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectContractError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise ProjectContractError(f"{field} is outside the supported bounds")
    return value


def _finite_number(
    value: Any,
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectContractError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ProjectContractError(f"{field} is outside the supported bounds")
    return number


def _trusted_mapping(request: Mapping[str, Any], root: str, field: str) -> Mapping[str, Any] | None:
    container = request.get(root, {})
    if not isinstance(container, Mapping):
        raise ProjectContractError(f"trusted {root} must be an object")
    value = container.get(field)
    return value if isinstance(value, Mapping) else None


def _require_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ProjectContractError(f"{field} must be a sha256 digest")
    return value


def _bounded_string(value: Any, field: str, *, maximum_bytes: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ProjectContractError(f"{field} must be a string")
    if len(value.encode("utf-8")) > maximum_bytes:
        raise ProjectContractError(f"{field} exceeds the bounded length")
    return value


def _archive_limits(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return hard caps optionally tightened, never loosened, by trusted policy."""

    policy_root = request.get("policy", {})
    if not isinstance(policy_root, Mapping):
        raise ProjectContractError("trusted policy must be an object")
    raw_policy = policy_root.get("archive")
    if raw_policy is None:
        policy: Mapping[str, Any] = {}
    elif isinstance(raw_policy, Mapping):
        policy = raw_policy
    else:
        raise ProjectContractError("policy.archive must be an object")
    supported = {
        "max_archive_bytes",
        "max_entries",
        "max_total_uncompressed_bytes",
        "max_entry_uncompressed_bytes",
        "max_compression_ratio",
        "max_nested_depth",
        "version",
    }
    if set(policy) - supported:
        raise ProjectContractError("policy.archive contains unsupported fields")

    def tightened_int(name: str, hard_limit: int) -> int:
        raw = policy.get(name, hard_limit)
        value = _bounded_int(raw, f"policy.archive.{name}", minimum=1, maximum=hard_limit)
        return min(value, hard_limit)

    raw_ratio = policy.get("max_compression_ratio", _MAX_ARCHIVE_COMPRESSION_RATIO)
    ratio = _finite_number(
        raw_ratio,
        "policy.archive.max_compression_ratio",
        minimum=1.0,
        maximum=_MAX_ARCHIVE_COMPRESSION_RATIO,
    )
    version = policy.get("version", "built-in-1")
    if not isinstance(version, str) or not version or len(version.encode("utf-8")) > 128:
        raise ProjectContractError("policy.archive.version must be a bounded non-empty string")
    return {
        "max_archive_bytes": tightened_int("max_archive_bytes", _MAX_ARCHIVE_BYTES),
        "max_entries": tightened_int("max_entries", _MAX_ARCHIVE_ENTRIES),
        "max_total_uncompressed_bytes": tightened_int(
            "max_total_uncompressed_bytes", _MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES
        ),
        "max_entry_uncompressed_bytes": tightened_int(
            "max_entry_uncompressed_bytes", _MAX_ARCHIVE_ENTRY_UNCOMPRESSED_BYTES
        ),
        "max_compression_ratio": ratio,
        "max_nested_depth": _bounded_int(
            policy.get("max_nested_depth", _DEFAULT_ARCHIVE_NESTED_DEPTH),
            "policy.archive.max_nested_depth",
            minimum=0,
            maximum=_MAX_ARCHIVE_NESTED_DEPTH,
        ),
        "version": version,
    }


def _reject_input_archive_authority(values: Mapping[str, Any]) -> None:
    forbidden = {
        "policy",
        "max_archive_bytes",
        "max_entries",
        "max_total_uncompressed_bytes",
        "max_entry_uncompressed_bytes",
        "max_compression_ratio",
        "max_nested_depth",
        "archive_root_digest",
        "archive_node_digest",
        "archive_parent_node_digest",
        "archive_depth",
        "archive_budget",
        "parent_node_digest",
        "consent",
        "authorization",
        "receipts",
    }
    present = sorted(forbidden & set(values))
    if present:
        raise ProjectContractError(f"archive authority must not be supplied in inputs: {present}")


def normalize_relative_path(value: Any) -> str:
    """Normalize an archive/folder path and reject every absolute/escape form."""

    if not isinstance(value, str) or not value or len(value) > 4_096:
        raise ProjectContractError("path must be a non-empty string of at most 4096 characters")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ProjectContractError("path must be valid UTF-8 text") from exc
    if len(encoded) > 4_096:
        raise ProjectContractError("path exceeds the portable UTF-8 byte limit")
    if any(
        ord(character) == 0x7F or unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in value
    ):
        raise ProjectContractError("path contains a control, surrogate, or formatting character")
    candidate = unicodedata.normalize("NFC", value.replace("\\", "/"))
    if candidate.startswith(("/", "//")) or _DRIVE.match(candidate):
        raise ProjectContractError("absolute, drive-letter, and UNC paths are forbidden")
    components = candidate.split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise ProjectContractError("empty, dot, and parent path components are forbidden")
    for component in components:
        if ":" in component:
            raise ProjectContractError("alternate data stream path components are forbidden")
        if component.endswith((".", " ")):
            raise ProjectContractError("path components with trailing dots or spaces are forbidden")
        windows_stem = component.split(".", 1)[0].upper()
        if windows_stem in _WINDOWS_RESERVED_COMPONENTS:
            raise ProjectContractError("Windows reserved path components are forbidden")
    normalized = posixpath.normpath(candidate)
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise ProjectContractError("path escapes the package root")
    return normalized


def _tar_header_is_valid(header: bytes) -> bool:
    """Validate the checksum of one fixed POSIX tar header without invoking a parser."""

    if len(header) < 512 or header == b"\x00" * 512:
        return False
    checksum_field = header[148:156]
    try:
        expected_text = checksum_field.rstrip(b"\x00 ").lstrip(b" ")
        if not expected_text or any(byte not in b"01234567" for byte in expected_text):
            return False
        expected = int(expected_text, 8)
    except ValueError:
        return False
    unsigned = sum(header[:148]) + (8 * 0x20) + sum(header[156:512])
    signed = sum(byte if byte < 128 else byte - 256 for byte in header[:148])
    signed += 8 * 0x20
    signed += sum(byte if byte < 128 else byte - 256 for byte in header[156:512])
    return expected in {unsigned, signed}


def detect_archive_container(prefix: bytes) -> str:
    """Classify only exact allowlisted outer containers from fixed bytes.

    The signature must start at byte zero, deliberately rejecting SFX and
    request-labelled polyglots.  This helper never invokes a decompressor or
    archive parser and is safe to use before malware clearance.
    """

    if not isinstance(prefix, bytes):
        raise ProjectContractError("archive signature input must be bytes")
    if prefix.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return "zip"
    if len(prefix) >= 10 and prefix[:3] == b"\x1f\x8b\x08" and prefix[3] & 0xE0 == 0:
        return "gzip"
    if _tar_header_is_valid(prefix[:512]):
        return "tar"
    return "unknown"


def _normalized_entry(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    path = normalize_relative_path(raw.get("path"))
    kind = _bounded_string(raw.get("kind", "file"), f"entry {path} kind", maximum_bytes=32).lower()
    if kind not in {"file", "directory", "symlink", "hardlink", "special"}:
        raise ProjectContractError(f"entry {path} has an unsupported kind")
    size_value = raw.get("size") if kind == "file" else raw.get("size", 0)
    size = _bounded_int(
        size_value,
        f"entry {path} size",
        minimum=0,
        maximum=_MAX_PROJECT_ENTRY_BYTES,
    )
    content_digest = raw.get("content_digest")
    if kind == "file":
        content_digest = _require_digest(content_digest, f"entry {path} content_digest")
    elif content_digest is not None:
        raise ProjectContractError(f"non-file entry {path} must not claim a content digest")
    if kind != "file" and size != 0:
        raise ProjectContractError(f"non-file entry {path} must have zero size")
    link_target = raw.get("link_target")
    if kind in {"symlink", "hardlink"}:
        link_target = normalize_relative_path(link_target)
    elif link_target is not None:
        raise ProjectContractError(f"non-link entry {path} must not claim a link target")
    default_entry_id = "entry_" + _digest({"path": path, "kind": kind})[7:31]
    entry_id = _bounded_string(
        raw.get("entry_id", default_entry_id),
        f"entry {path} entry_id",
        maximum_bytes=256,
    )
    return {
        "entry_id": entry_id,
        "path": path,
        "display_path": path,
        "kind": kind,
        "size": size,
        "content_digest": content_digest,
        "media_type": _bounded_string(
            raw.get("media_type", "application/octet-stream"),
            f"entry {path} media_type",
            maximum_bytes=256,
        ),
        "role": _bounded_string(raw.get("role", "UNCLASSIFIED"), f"entry {path} role", maximum_bytes=128),
        "security_state": "UNVERIFIED",
        "link_target": link_target,
    }


def _collisions(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    exact: dict[str, list[str]] = defaultdict(list)
    portable: dict[str, list[str]] = defaultdict(list)
    identities: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        path = str(entry["path"])
        exact[path].append(str(entry["entry_id"]))
        portable[unicodedata.normalize("NFKC", path).casefold()].append(path)
        identities[str(entry["entry_id"])].append(path)
    collisions = [
        {"type": "DUPLICATE_PATH", "key": path, "members": members}
        for path, members in sorted(exact.items())
        if len(members) > 1
    ]
    collisions.extend(
        {"type": "UNICODE_OR_CASE_COLLISION", "key": key, "members": sorted(set(paths))}
        for key, paths in sorted(portable.items())
        if len(set(paths)) > 1
    )
    collisions.extend(
        {"type": "DUPLICATE_ENTRY_ID", "key": entry_id, "members": sorted(paths)}
        for entry_id, paths in sorted(identities.items())
        if len(paths) > 1
    )
    return collisions


def _normalized_entries(value: Any, field: str) -> list[dict[str, Any]]:
    raw_entries = _sequence(value, field, maximum=_MAX_PROJECT_ENTRIES)
    entries: list[dict[str, Any]] = []
    total = 0
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"{field}[{index}] must be an object")
        entry = _normalized_entry(raw, index)
        if entry["size"] > _MAX_PROJECT_TOTAL_BYTES - total:
            raise ProjectContractError("project entries exceed the cumulative byte limit")
        total += int(entry["size"])
        entries.append(entry)
    return entries


def _validated_roots(value: Any, entries: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, str]]:
    raw_roots = _sequence(value, field, maximum=100)
    roots: list[dict[str, str]] = []
    names: set[str] = set()
    paths: set[str] = set()
    portable_paths: set[str] = set()
    entry_paths = [str(entry["path"]) for entry in entries]
    for index, raw in enumerate(raw_roots):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"{field}[{index}] must be an object")
        name = _bounded_string(raw.get("name", f"root-{index + 1}"), f"{field}[{index}].name", maximum_bytes=256)
        path = normalize_relative_path(raw.get("path"))
        portable_path = unicodedata.normalize("NFKC", path).casefold()
        role = _bounded_string(raw.get("role", "PROJECT"), f"{field}[{index}].role", maximum_bytes=128)
        if name in names or path in paths or portable_path in portable_paths:
            raise ProjectContractError("root names and paths must be unique")
        if not any(entry_path.startswith(path + "/") for entry_path in entry_paths):
            raise ProjectContractError(f"root {path} does not contain a manifest entry")
        names.add(name)
        paths.add(path)
        portable_paths.add(portable_path)
        roots.append({"name": name, "path": path, "role": role})
    roots.sort(key=lambda item: (item["path"], item["name"]))
    return roots


def _merkle_root(entries: Sequence[Mapping[str, Any]]) -> str:
    layer = [_digest({"path": item["path"], "kind": item["kind"], "size": item["size"], "digest": item.get("content_digest")}) for item in entries]
    if not layer:
        return _digest([])
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [_digest({"left": layer[index], "right": layer[index + 1]}) for index in range(0, len(layer), 2)]
    return layer[0]


def build_folder_manifest(request: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic folder manifest without persisting local absolute paths."""

    values = _inputs(request)
    entries = _normalized_entries(values.get("entries", []), "inputs.entries")
    entries.sort(key=lambda item: item["path"])
    collisions = _collisions(entries)
    unsafe = [item["path"] for item in entries if item["kind"] == "special"]
    links = [item for item in entries if item["kind"] in {"symlink", "hardlink"}]
    for item in links:
        item["followed"] = False
        item["security_state"] = "METADATA_ONLY"
    roots = _validated_roots(values.get("roots", []), entries, "inputs.roots")
    body = {"schema_version": "1.0.0", "entries": entries, "roots": roots}
    blocked = not entries or bool(collisions) or bool(unsafe)
    code = "FOLDER_MANIFEST_EMPTY" if not entries else "FOLDER_UNSAFE_ENTRY" if unsafe else "FOLDER_PATH_COLLISION" if collisions else "FOLDER_MANIFEST_CREATED"
    return {
        "state": "BLOCKED" if blocked else "SUCCEEDED",
        "code": code,
        "outputs": {**body, "collisions": collisions, "unsafe_entry_paths": unsafe, "manifest_digest": _digest(body), "local_absolute_paths_retained": False},
    }


def _validated_file_records(value: Any, field: str) -> list[dict[str, Any]]:
    raw_records = _sequence(value, field, maximum=_MAX_PROJECT_ENTRIES)
    records: list[dict[str, Any]] = []
    exact: set[str] = set()
    portable: set[str] = set()
    total = 0
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"{field}[{index}] must be an object")
        path = normalize_relative_path(raw.get("path"))
        portable_path = unicodedata.normalize("NFKC", path).casefold()
        if path in exact or portable_path in portable:
            raise ProjectContractError(f"{field} contains a duplicate or portable path collision")
        exact.add(path)
        portable.add(portable_path)
        size = _bounded_int(
            raw.get("size"),
            f"{field}[{index}].size",
            minimum=0,
            maximum=_MAX_PROJECT_ENTRY_BYTES,
        )
        if size > _MAX_PROJECT_TOTAL_BYTES - total:
            raise ProjectContractError(f"{field} exceeds the cumulative byte limit")
        total += size
        records.append(
            {
                "path": path,
                "content_digest": _require_digest(raw.get("content_digest"), f"{field}[{index}].content_digest"),
                "size": size,
            }
        )
    records.sort(key=lambda item: item["path"])
    return records


def resume_folder_upload(request: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile server-confirmed file progress and detect mixed file versions."""

    values = _inputs(request)
    if "received_files" in values or "receipt" in values or "receipts" in values:
        return {"state": "BLOCKED", "code": "UPLOAD_STATE_INPUT_UNTRUSTED", "outputs": {"completed": [], "missing": [], "failed": []}}
    expected = _validated_file_records(values.get("expected_files", []), "inputs.expected_files")
    if not expected:
        return {"state": "BLOCKED", "code": "UPLOAD_EXPECTED_FILES_EMPTY", "outputs": {"completed": [], "missing": [], "failed": []}}
    upload_session_id = _bounded_string(
        values.get("upload_session_id"),
        "upload_session_id",
        maximum_bytes=256,
    )
    expected_manifest_digest = _digest(expected)
    tenant_id = request.get("tenant_id")
    project_id = request.get("project_id")
    if not isinstance(tenant_id, str) or not tenant_id or not isinstance(project_id, str) or not project_id:
        return {"state": "BLOCKED", "code": "UPLOAD_STATE_UNAVAILABLE", "outputs": {"completed": [], "missing": [], "failed": []}}
    trusted_state = _trusted_mapping(request, "capabilities", "folder_upload_state")
    if (
        trusted_state is None
        or trusted_state.get("verified") is not True
        or str(trusted_state.get("tenant_id", "")) != tenant_id
        or str(trusted_state.get("project_id", "")) != project_id
        or str(trusted_state.get("upload_session_id", "")) != upload_session_id
    ):
        return {"state": "BLOCKED", "code": "UPLOAD_STATE_UNAVAILABLE", "outputs": {"completed": [], "missing": [], "failed": []}}
    if trusted_state.get("expected_manifest_digest") != expected_manifest_digest:
        return {"state": "BLOCKED", "code": "UPLOAD_EXPECTED_MANIFEST_MISMATCH", "outputs": {"completed": [], "missing": [], "failed": []}}
    raw_received = trusted_state.get("received_files", [])
    received = _validated_file_records(raw_received, "capabilities.folder_upload_state.received_files")
    state_binding = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "upload_session_id": upload_session_id,
        "expected_manifest_digest": expected_manifest_digest,
        "received_files": received,
    }
    if trusted_state.get("state_digest") != _digest(state_binding):
        return {"state": "BLOCKED", "code": "UPLOAD_STATE_DIGEST_MISMATCH", "outputs": {"completed": [], "missing": [], "failed": []}}
    received_by_path = {item["path"]: item for item in received}
    expected_by_path = {item["path"]: item for item in expected}
    completed: list[str] = []
    missing: list[str] = []
    failed: list[dict[str, str]] = []
    for item in expected:
        path = item["path"]
        actual = received_by_path.get(path)
        if actual is None:
            missing.append(path)
            continue
        if actual["content_digest"] != item["content_digest"] or actual["size"] != item["size"]:
            failed.append({"path": path, "code": "FILE_CHANGED_DURING_UPLOAD"})
        else:
            completed.append(path)
    unexpected = sorted(set(received_by_path) - set(expected_by_path))
    failed.extend({"path": path, "code": "UNEXPECTED_RECEIVED_FILE"} for path in unexpected)
    state = "BLOCKED" if failed else "PARTIAL" if missing else "SUCCEEDED"
    code = "MIXED_FILE_VERSION_BLOCKED" if failed else "FOLDER_UPLOAD_INCOMPLETE" if missing else "FOLDER_UPLOAD_VERIFIED"
    receipt = {
        "completed": sorted(completed),
        "missing": sorted(missing),
        "failed": failed,
        "trusted_state_digest": trusted_state.get("state_digest"),
        "expected_manifest_digest": expected_manifest_digest,
        "upload_session_id": upload_session_id,
        "external_state_verified": True,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return {"state": state, "code": code, "outputs": receipt}


def build_project_manifest(request: Mapping[str, Any]) -> dict[str, Any]:
    """Build a stable immutable manifest and Merkle root."""

    values = _inputs(request)
    entries = _normalized_entries(values.get("entries", []), "inputs.entries")
    entries.sort(key=lambda item: item["path"])
    collisions = _collisions(entries)
    unsafe = [item["path"] for item in entries if item["kind"] == "special"]
    roots = _validated_roots(values.get("roots", []), entries, "inputs.roots")
    parent_digest = values.get("parent_manifest_digest")
    if parent_digest is not None:
        parent_digest = _require_digest(parent_digest, "parent_manifest_digest")
    package_id = _bounded_string(values.get("package_id"), "package_id", maximum_bytes=256)
    package_version = _bounded_string(values.get("package_version"), "package_version", maximum_bytes=256)
    body = {
        "schema_version": "1.0.0",
        "package_id": package_id,
        "package_version": package_version,
        "entries": entries,
        "roots": roots,
        "parent_manifest_digest": parent_digest,
    }
    manifest_digest = _digest(body)
    blocked = not entries or bool(collisions) or bool(unsafe)
    code = "PROJECT_MANIFEST_EMPTY" if not entries else "MANIFEST_UNSAFE_ENTRY" if unsafe else "MANIFEST_PATH_COLLISION" if collisions else "PROJECT_MANIFEST_CREATED"
    return {
        "state": "BLOCKED" if blocked else "SUCCEEDED",
        "code": code,
        "outputs": {**body, "manifest_digest": manifest_digest, "merkle_root": _merkle_root(entries), "collisions": collisions, "unsafe_entry_paths": unsafe, "immutable": True},
        "metrics": {"entry_count": len(entries), "total_bytes": sum(item["size"] for item in entries)},
    }


def _archive_safety_report(
    entries: Sequence[Any],
    limits: Mapping[str, Any],
) -> dict[str, Any]:
    max_entries = int(limits["max_entries"])
    max_total = int(limits["max_total_uncompressed_bytes"])
    max_entry = int(limits["max_entry_uncompressed_bytes"])
    max_ratio = float(limits["max_compression_ratio"])
    max_depth = int(limits["max_nested_depth"])
    findings: list[dict[str, Any]] = []
    total = 0
    normalized_paths: set[str] = set()
    normalized_kinds: dict[str, str] = {}
    portable_kinds: dict[str, str] = {}
    if not entries:
        findings.append({"code": "ARCHIVE_EMPTY", "severity": "CRITICAL"})
    if len(entries) > max_entries:
        findings.append(
            {
                "code": "ARCHIVE_ENTRY_LIMIT_EXCEEDED",
                "severity": "CRITICAL",
                "observed": len(entries),
                "limit": max_entries,
            }
        )
        report = {
            "decision": "REJECT",
            "findings": findings,
            "resource_usage": {"entries": len(entries), "uncompressed_bytes": 0},
            "decision_scope": "DECLARED_LAYER_ONLY",
            "global_budget_state": "NOT_EVALUATED",
            "policy_version": str(limits["version"]),
        }
        report["report_digest"] = _digest(report)
        return report
    for index, raw in enumerate(entries):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"inputs.entries[{index}] must be an object")
        original = str(raw.get("path", ""))
        try:
            path = normalize_relative_path(original)
        except ProjectContractError:
            findings.append({"code": "ARCHIVE_PATH_TRAVERSAL", "severity": "CRITICAL", "entry_index": index})
            continue
        if path in normalized_paths:
            findings.append({"code": "ARCHIVE_DUPLICATE_PATH", "severity": "HIGH", "path": path})
        normalized_paths.add(path)
        kind = str(raw.get("kind", "file")).lower()
        normalized_kinds[path] = kind
        portable_kinds[unicodedata.normalize("NFKC", path).casefold()] = kind
        if kind in {"symlink", "hardlink", "device", "fifo", "socket", "special"}:
            findings.append({"code": "ARCHIVE_SPECIAL_ENTRY_BLOCKED", "severity": "CRITICAL", "path": path, "kind": kind})
        unpacked_raw = raw.get("uncompressed_size", raw.get("size", 0))
        compressed_raw = raw.get("compressed_size", 0)
        depth_raw = raw.get("nested_depth", 0)
        if (
            isinstance(unpacked_raw, bool)
            or not isinstance(unpacked_raw, int)
            or unpacked_raw < 0
            or isinstance(compressed_raw, bool)
            or not isinstance(compressed_raw, int)
            or compressed_raw < 0
            or isinstance(depth_raw, bool)
            or not isinstance(depth_raw, int)
            or depth_raw < 0
        ):
            findings.append({"code": "ARCHIVE_SIZE_INVALID", "severity": "CRITICAL", "path": path})
            continue
        unpacked = unpacked_raw
        compressed = compressed_raw
        depth = depth_raw
        if unpacked > max_entry:
            findings.append({"code": "ARCHIVE_ENTRY_SIZE_LIMIT", "severity": "CRITICAL", "path": path})
        ratio = math.inf if compressed == 0 and unpacked > 0 else unpacked / max(1, compressed)
        if ratio > max_ratio:
            findings.append({"code": "ARCHIVE_COMPRESSION_RATIO_LIMIT", "severity": "CRITICAL", "path": path})
        if depth > max_depth:
            findings.append({"code": "ARCHIVE_NESTED_DEPTH_LIMIT", "severity": "CRITICAL", "path": path})
        if unpacked > max_total - total:
            findings.append({"code": "ARCHIVE_TOTAL_SIZE_LIMIT", "severity": "CRITICAL", "observed": total + unpacked})
            break
        total += unpacked
    for path in sorted(normalized_paths):
        components = path.split("/")
        for boundary in range(1, len(components)):
            ancestor = "/".join(components[:boundary])
            if ancestor in normalized_paths and normalized_kinds.get(ancestor) != "directory":
                findings.append(
                    {
                        "code": "ARCHIVE_FILE_DIRECTORY_CONFLICT",
                        "severity": "CRITICAL",
                        "path": path,
                        "ancestor": ancestor,
                    }
                )
                break
            portable_ancestor = unicodedata.normalize("NFKC", ancestor).casefold()
            if portable_ancestor in portable_kinds and portable_kinds[portable_ancestor] != "directory":
                findings.append(
                    {
                        "code": "ARCHIVE_PORTABLE_FILE_DIRECTORY_CONFLICT",
                        "severity": "CRITICAL",
                        "path": path,
                        "ancestor": ancestor,
                    }
                )
                break
    collisions = _collisions([{"path": path, "entry_id": path} for path in sorted(normalized_paths)])
    findings.extend({"code": item["type"], "severity": "HIGH", "members": item["members"]} for item in collisions)
    decision = "REJECT" if any(item["severity"] == "CRITICAL" for item in findings) else "QUARANTINE" if findings else "ALLOW"
    report = {
        "decision": decision,
        "findings": findings,
        "resource_usage": {"entries": len(entries), "uncompressed_bytes": total},
        "decision_scope": "DECLARED_LAYER_ONLY",
        "global_budget_state": "NOT_EVALUATED",
        "policy_version": str(limits["version"]),
    }
    report["report_digest"] = _digest(report)
    return report


def inspect_archive_safety(request: Mapping[str, Any]) -> dict[str, Any]:
    """Inspect declared archive entries against immutable or trusted tighter limits."""

    values = _inputs(request)
    _reject_input_archive_authority(values)
    raw_entries = values.get("entries", [])
    if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, (str, bytes, bytearray)):
        raise ProjectContractError("inputs.entries must be an array")
    limits = _archive_limits(request)
    report = _archive_safety_report(raw_entries, limits)
    decision = report["decision"]
    return {
        "state": "SUCCEEDED" if decision == "ALLOW" else "BLOCKED",
        "code": f"ARCHIVE_{decision}",
        "outputs": report,
    }


def _stream_digest(
    stream: BinaryIO,
    *,
    entry_limit: int,
    total_limit: int,
    counter: list[int],
) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = stream.read(_ARCHIVE_STREAM_CHUNK_BYTES)
        if not chunk:
            break
        if len(chunk) > entry_limit - size:
            raise ProjectContractError("archive entry exceeded the actual streamed byte limit")
        if len(chunk) > total_limit - counter[0]:
            raise ProjectContractError("archive actual cumulative resource limit exceeded")
        size += len(chunk)
        counter[0] += len(chunk)
        digest.update(chunk)
    return "sha256:" + digest.hexdigest(), size


def _decode_base64_bounded(encoded: str, *, decoded_limit: int) -> tuple[BinaryIO, int]:
    encoded_limit = min(_MAX_ARCHIVE_ENCODED_CHARS, ((decoded_limit + 2) // 3) * 4)
    if not encoded or len(encoded) > encoded_limit or len(encoded) % 4:
        raise ProjectContractError("archive input exceeds the encoded or decoded byte limit")
    padding = encoded.find("=")
    if padding != -1 and padding < len(encoded) - 2:
        raise ProjectContractError("archive_bytes_b64 has invalid padding")
    stream = tempfile.SpooledTemporaryFile(max_size=_ARCHIVE_STREAM_CHUNK_BYTES, mode="w+b")
    total = 0
    encoded_chunk = 64 * 1024
    try:
        for offset in range(0, len(encoded), encoded_chunk):
            chunk = encoded[offset : offset + encoded_chunk]
            decoded = base64.b64decode(chunk, validate=True)
            if len(decoded) > decoded_limit - total:
                raise ProjectContractError("archive input exceeds the decoded byte limit")
            stream.write(decoded)
            total += len(decoded)
        if total == 0:
            raise ProjectContractError("archive content is empty")
        stream.seek(0)
        return cast(BinaryIO, stream), total
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        stream.close()
        raise ProjectContractError("archive_bytes_b64 is invalid") from exc
    except Exception:
        stream.close()
        raise


def _archive_depth(path: str) -> int:
    return sum(
        1
        for component in path.lower().split("/")
        if any(component.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)
    )


def _zip_declared_entry_count(stream: BinaryIO, *, archive_size: int) -> int:
    """Read the bounded EOCD tail before ZipFile materializes central-directory entries."""

    tail_size = min(archive_size, 65_557)
    stream.seek(archive_size - tail_size)
    tail = stream.read(tail_size)
    marker = tail.rfind(b"PK\x05\x06")
    if marker < 0 or len(tail) - marker < 22:
        raise ProjectContractError("zip end-of-central-directory record is missing")
    disk_number, central_disk, entries_on_disk, total_entries = struct.unpack_from("<HHHH", tail, marker + 4)
    comment_length = struct.unpack_from("<H", tail, marker + 20)[0]
    if marker + 22 + comment_length != len(tail):
        raise ProjectContractError("zip end-of-central-directory record is ambiguous")
    if disk_number != 0 or central_disk != 0 or entries_on_disk != total_entries:
        raise ProjectContractError("multi-disk zip archives are unsupported")
    if total_entries == 0xFFFF:
        raise ProjectContractError("ZIP64 entry counts require an unavailable bounded parser")
    stream.seek(0)
    return int(total_entries)


class _ZipEntryView(Sequence[Mapping[str, Any]]):
    """Lazily project ZipInfo metadata without a second materialized entry list."""

    def __init__(self, entries: Sequence[zipfile.ZipInfo]) -> None:
        self._entries = entries

    def __len__(self) -> int:
        return len(self._entries)

    @overload
    def __getitem__(self, index: int) -> Mapping[str, Any]: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[Mapping[str, Any]]: ...

    def __getitem__(self, index: int | slice) -> Mapping[str, Any] | Sequence[Mapping[str, Any]]:
        if isinstance(index, slice):
            return [self._entry(position) for position in range(*index.indices(len(self)))]
        return self._entry(index)

    def _entry(self, index: int) -> Mapping[str, Any]:
        info = self._entries[index]
        unix_type = (info.external_attr >> 16) & 0o170000
        special = unix_type in {0o120000, 0o060000, 0o020000, 0o010000, 0o140000}
        path = info.filename.rstrip("/")
        return {
            "path": path,
            "kind": "special" if special else "directory" if info.is_dir() else "file",
            "uncompressed_size": info.file_size,
            "compressed_size": info.compress_size,
            # Metadata and suffixes cannot establish nested-archive content.
            # The capability-injected publisher performs bounded byte sniffing
            # after the original archive has malware clearance.
            "nested_depth": 0,
        }


def extract_archive_safely(request: Mapping[str, Any]) -> dict[str, Any]:
    """Perform only bounded fixed-byte intake before trusted malware clearance.

    This pure handler intentionally never opens ZIP, TAR, or GZIP parsers.  It
    proves the byte identity and the allowlisted outer-container signature, then
    delegates all parsing and publication to the capability-injected adapter.
    """

    values = _inputs(request)
    try:
        _reject_input_archive_authority(values)
    except ProjectContractError as exc:
        return {
            "state": "BLOCKED",
            "code": "DOMAIN_INPUT_REJECTED",
            "outputs": {"objects": [], "safe_reason": str(exc)},
        }
    encoded = values.get("archive_bytes_b64")
    if not isinstance(encoded, str):
        return {"state": "BLOCKED", "code": "ARCHIVE_CONTENT_REQUIRED", "outputs": {"objects": []}}
    archive_format = str(values.get("format", "zip")).lower()
    allowed_formats = {"zip", "tar", "tar.gz", "tgz", "gz", "gzip"}
    if archive_format not in allowed_formats:
        return {"state": "BLOCKED", "code": "ARCHIVE_FORMAT_UNSUPPORTED", "outputs": {"objects": []}}
    limits = _archive_limits(request)
    try:
        raw_stream, archive_size = _decode_base64_bounded(
            encoded,
            decoded_limit=int(limits["max_archive_bytes"]),
        )
    except ProjectContractError as exc:
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_INPUT_SIZE_LIMIT",
            "outputs": {"objects": [], "safe_reason": str(exc)},
        }
    try:
        with raw_stream:
            prefix = raw_stream.read(min(archive_size, 512))
            detected = detect_archive_container(prefix)
            expected = "gzip" if archive_format in {"tar.gz", "tgz", "gz", "gzip"} else archive_format
            if detected == "unknown" or detected != expected:
                return {
                    "state": "BLOCKED",
                    "code": "ARCHIVE_FORMAT_SIGNATURE_MISMATCH",
                    "outputs": {
                        "objects": [],
                        "declared_format": archive_format,
                        "detected_container": detected,
                        "parser_execution": "NOT_RUN",
                        "publication_state": "NOT_RUN",
                    },
                }
            measured = hashlib.sha256()
            measured_bytes = 0
            raw_stream.seek(0)
            while chunk := raw_stream.read(_ARCHIVE_STREAM_CHUNK_BYTES):
                measured.update(chunk)
                measured_bytes += len(chunk)
            if measured_bytes != archive_size:
                raise ProjectContractError("archive byte stream changed during bounded intake")
    except (OSError, ProjectContractError) as exc:
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_INTAKE_BLOCKED",
            "outputs": {"objects": [], "safe_reason": str(exc)},
        }
    return {
        "state": "PARTIAL",
        "code": "ARCHIVE_MALWARE_CLEARANCE_REQUIRED",
        "outputs": {
            "objects": [],
            "archive_digest": "sha256:" + measured.hexdigest(),
            "archive_bytes": archive_size,
            "declared_format": archive_format,
            "detected_container": detected,
            "scanner_status": "NOT_RUN",
            "parser_execution": "NOT_RUN",
            "host_files_created": False,
            "readable_cas_objects": [],
            "publication_state": "NOT_RUN",
            "required_capabilities": ["MALWARE_SCAN", "TENANT_SCOPED_CAS"],
        },
    }


def detect_project_profile(request: Mapping[str, Any]) -> dict[str, Any]:
    """Detect roots and frameworks without treating a generic marker as framework proof."""

    values = _inputs(request)
    raw_entries = _sequence(values.get("entries", []), "inputs.entries", maximum=_MAX_PROJECT_ENTRIES)
    if not raw_entries:
        return {"state": "BLOCKED", "code": "PROJECT_PROFILE_INPUT_EMPTY", "outputs": {"roots": [], "languages": {}, "frameworks": []}}
    records: dict[str, Mapping[str, Any]] = {}
    portable_paths: set[str] = set()
    verified_content: dict[str, tuple[str, str]] = {}
    unverified_evidence: list[dict[str, str]] = []
    cumulative_content_bytes = 0
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"inputs.entries[{index}] must be an object")
        path = normalize_relative_path(raw.get("path"))
        portable = unicodedata.normalize("NFKC", path).casefold()
        if path in records or portable in portable_paths:
            raise ProjectContractError("profile entries contain a duplicate or portable path collision")
        records[path] = raw
        portable_paths.add(portable)
        content = raw.get("content")
        if content is None:
            continue
        if not isinstance(content, str):
            raise ProjectContractError("profile evidence content must be text")
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_SOURCE_FILE_BYTES or len(encoded) > _MAX_SOURCE_TOTAL_BYTES - cumulative_content_bytes:
            raise ProjectContractError("profile evidence exceeds the bounded source byte limit")
        cumulative_content_bytes += len(encoded)
        claimed = raw.get("content_digest")
        observed = _digest(encoded)
        if claimed != observed:
            unverified_evidence.append({"path": path, "code": "CONTENT_DIGEST_MISSING_OR_MISMATCH"})
            continue
        verified_content[path] = (content, observed)
    paths = sorted(records)
    relevant = [path for path in paths if not any(fnmatch.fnmatch(path, pattern) for pattern in _VENDORED + _GENERATED + _CACHE)]
    language_counts: dict[str, int] = {}
    for language, extensions in _LANGUAGE_EXTENSIONS.items():
        count = sum(any(path.lower().endswith(extension) for extension in extensions) for path in relevant)
        if count:
            language_counts[language] = count
    frameworks: list[dict[str, Any]] = []
    framework_uncertainty: list[dict[str, str]] = list(unverified_evidence)
    package_paths = [path for path in relevant if path == "package.json" or path.endswith("/package.json")]
    for package_path in package_paths:
        verified = verified_content.get(package_path)
        if verified is None:
            framework_uncertainty.append({"path": package_path, "code": "PACKAGE_JSON_CONTENT_UNVERIFIED"})
            continue
        try:
            package = json.loads(verified[0])
        except (TypeError, ValueError, RecursionError):
            framework_uncertainty.append({"path": package_path, "code": "PACKAGE_JSON_INVALID"})
            continue
        if not isinstance(package, Mapping):
            framework_uncertainty.append({"path": package_path, "code": "PACKAGE_JSON_NOT_OBJECT"})
            continue
        dependencies: dict[str, Any] = {}
        for field in ("dependencies", "devDependencies", "peerDependencies"):
            section = package.get(field)
            if section is None:
                continue
            if isinstance(section, Mapping):
                dependencies.update({str(key): value for key, value in section.items()})
            else:
                framework_uncertainty.append(
                    {"path": package_path, "code": f"PACKAGE_JSON_{field.upper()}_INVALID"}
                )
        for framework, dependency in (("React", "react"), ("Vue", "vue")):
            if dependency in dependencies:
                frameworks.append(
                    {
                        "framework": framework,
                        "confidence": 0.99,
                        "evidence": [f"{package_path}#dependencies.{dependency}"],
                        "content_digest": verified[1],
                    }
                )
    spring_markers = [
        path
        for path in relevant
        if path.rsplit("/", 1)[-1] in {"pom.xml", "build.gradle", "build.gradle.kts"}
    ]
    spring_evidence = [
        path
        for path in spring_markers
        if path in verified_content
        and ("spring-boot" in verified_content[path][0] or "org.springframework.boot" in verified_content[path][0])
    ]
    if spring_evidence:
        frameworks.append({"framework": "Spring", "confidence": 0.95, "evidence": sorted(spring_evidence)})
    else:
        framework_uncertainty.extend({"path": path, "code": "GENERIC_BUILD_MARKER_NOT_FRAMEWORK_PROOF"} for path in spring_markers)
    unique_framework_markers = {
        "Django": ("manage.py",),
        "Flutter": ("pubspec.yaml", "lib/main.dart"),
        "GoModules": ("go.mod",),
        "Cargo": ("Cargo.toml",),
        "SwiftPM": ("Package.swift",),
    }
    for framework, markers in unique_framework_markers.items():
        evidence = sorted(
            path
            for path in relevant
            if any(path == marker or path.endswith("/" + marker) for marker in markers)
        )
        if evidence:
            frameworks.append({"framework": framework, "confidence": 0.85, "evidence": evidence})
            framework_uncertainty.extend(
                {"path": path, "code": "FRAMEWORK_MARKER_CONTENT_UNVERIFIED"}
                for path in evidence
                if path not in verified_content
            )
    merged_frameworks: dict[str, dict[str, Any]] = {}
    for item in frameworks:
        name = str(item["framework"])
        current = merged_frameworks.setdefault(
            name,
            {"framework": name, "confidence": 0.0, "evidence": [], "content_digests": []},
        )
        current["confidence"] = max(float(current["confidence"]), float(item["confidence"]))
        current["evidence"] = sorted(set(current["evidence"]) | set(item["evidence"]))
        if item.get("content_digest"):
            current["content_digests"] = sorted(set(current["content_digests"]) | {str(item["content_digest"])})
    frameworks = list(merged_frameworks.values())
    root_markers = {"pom.xml", "build.gradle", "build.gradle.kts", "package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pubspec.yaml", "Package.swift", "*.sln"}
    root_evidence: dict[str, list[str]] = defaultdict(list)
    for path in relevant:
        name = path.rsplit("/", 1)[-1]
        if name in root_markers or name.endswith(".sln"):
            root = path.rsplit("/", 1)[0] if "/" in path else "."
            root_evidence[root].append(path)
    roots: list[dict[str, Any]] = [
        {
            "path": root,
            "confidence": min(0.99, 0.5 + len(evidence) * 0.12),
            "evidence": sorted(evidence),
            "status": "CANDIDATE",
        }
        for root, evidence in sorted(root_evidence.items())
    ]
    framework_names = [str(item["framework"]) for item in frameworks]
    ambiguous = len([root for root in roots if root["confidence"] >= 0.62]) > 1
    if "React" in framework_names and "Vue" in framework_names:
        ambiguous = True
    partial = ambiguous or not roots or bool(framework_uncertainty)
    profile = {
        "roots": roots,
        "languages": language_counts,
        "frameworks": sorted(frameworks, key=lambda item: (item["framework"], item["evidence"])),
        "ambiguous": ambiguous,
        "unverified_evidence": framework_uncertainty,
    }
    profile["profile_digest"] = _digest(profile)
    return {
        "state": "PARTIAL" if partial else "SUCCEEDED",
        "code": "PROJECT_PROFILE_REVIEW_REQUIRED" if partial else "PROJECT_PROFILE_DETECTED",
        "outputs": profile,
    }


def classify_project_entries(request: Mapping[str, Any]) -> dict[str, Any]:
    """Classify with code rules plus trusted policy/security assessment only."""

    values = _inputs(request)
    if {"ignore_rules", "policy", "policy_version", "security_state"} & set(values):
        return {"state": "BLOCKED", "code": "CLASSIFICATION_POLICY_INPUT_UNTRUSTED", "outputs": {"entries": []}}
    entries = _sequence(values.get("entries", []), "inputs.entries", maximum=_MAX_PROJECT_ENTRIES)
    if not entries:
        return {"state": "BLOCKED", "code": "CLASSIFICATION_INPUT_EMPTY", "outputs": {"entries": []}}
    if any(isinstance(raw, Mapping) and "security_state" in raw for raw in entries):
        return {"state": "BLOCKED", "code": "CLASSIFICATION_SECURITY_INPUT_UNTRUSTED", "outputs": {"entries": []}}
    policy_root = request.get("policy", {})
    if not isinstance(policy_root, Mapping):
        raise ProjectContractError("trusted policy must be an object")
    raw_policy = policy_root.get("project_classification")
    if raw_policy is None:
        policy: Mapping[str, Any] = {"version": "built-in-1", "ignore_rules": []}
    elif isinstance(raw_policy, Mapping):
        policy = raw_policy
    else:
        raise ProjectContractError("policy.project_classification must be an object")
    if set(policy) - {"version", "ignore_rules"}:
        raise ProjectContractError("policy.project_classification contains unsupported fields")
    version = policy.get("version", "built-in-1")
    if not isinstance(version, str) or not version or len(version.encode("utf-8")) > 128:
        raise ProjectContractError("classification policy version is invalid")
    rules = _sequence(policy.get("ignore_rules", []), "policy.project_classification.ignore_rules", maximum=10_000)
    trusted_assessment = _trusted_mapping(request, "capabilities", "project_security_assessment")
    security_states: dict[str, str] = {}
    assessment_verified = False
    if trusted_assessment is not None:
        raw_states = trusted_assessment.get("states")
        if not isinstance(raw_states, Mapping):
            raise ProjectContractError("project security assessment states must be an object")
        if len(raw_states) > _MAX_PROJECT_ENTRIES:
            raise ProjectContractError("project security assessment exceeds the bounded item limit")
        if len(_canonical(raw_states).encode("utf-8")) > _MAX_REPOSITORY_MAP_BYTES:
            raise ProjectContractError("project security assessment exceeds the bounded JSON size")
        if (
            trusted_assessment.get("verified") is not True
            or str(trusted_assessment.get("tenant_id", "")) != str(request.get("tenant_id", ""))
            or str(trusted_assessment.get("project_id", "")) != str(request.get("project_id", ""))
            or trusted_assessment.get("assessment_digest") != _digest(raw_states)
        ):
            return {"state": "BLOCKED", "code": "CLASSIFICATION_SECURITY_ASSESSMENT_INVALID", "outputs": {"entries": []}}
        portable_assessment_paths: set[str] = set()
        for raw_path, raw_state in raw_states.items():
            path = normalize_relative_path(raw_path)
            portable = unicodedata.normalize("NFKC", path).casefold()
            if path in security_states or portable in portable_assessment_paths:
                raise ProjectContractError("security assessment paths must be unique")
            state = _bounded_string(raw_state, f"security assessment state for {path}", maximum_bytes=32).upper()
            if state not in {"UNKNOWN", "CLEAR", "APPROVED", "QUARANTINED", "BLOCKED"}:
                raise ProjectContractError("trusted security assessment contains an invalid state")
            portable_assessment_paths.add(portable)
            security_states[path] = state
        assessment_verified = True
    classifications: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    portable_paths: set[str] = set()
    unknown_security = False
    for index, raw in enumerate(entries):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"inputs.entries[{index}] must be an object")
        path = normalize_relative_path(raw.get("path"))
        portable = unicodedata.normalize("NFKC", path).casefold()
        if path in seen_paths or portable in portable_paths:
            raise ProjectContractError("classification entries must have unique portable paths")
        seen_paths.add(path)
        portable_paths.add(portable)
        security = security_states.get(path, "UNKNOWN")
        unknown_security = unknown_security or security == "UNKNOWN"
        matched: list[dict[str, Any]] = []
        included = True
        for rule_index, rule in enumerate(rules):
            if not isinstance(rule, Mapping):
                raise ProjectContractError(f"ignore_rules[{rule_index}] must be an object")
            pattern = _bounded_string(
                rule.get("pattern"),
                f"classification ignore rule {rule_index} pattern",
                maximum_bytes=4_096,
            )
            negate = pattern.startswith("!")
            candidate = pattern[1:] if negate else pattern
            if not candidate:
                raise ProjectContractError("classification ignore rule pattern is invalid")
            if fnmatch.fnmatch(path, candidate):
                included = negate
                matched.append({"rule_index": rule_index, "pattern": pattern, "source": rule.get("source"), "line": rule.get("line")})
        category = "SOURCE"
        if any(fnmatch.fnmatch(path, pattern) for pattern in _VENDORED):
            category = "VENDORED"
        elif any(fnmatch.fnmatch(path, pattern) for pattern in _GENERATED):
            category = "GENERATED"
        elif any(fnmatch.fnmatch(path, pattern) for pattern in _CACHE):
            category = "CACHE"
        elif _SECRET.search(path):
            category = "SUSPECTED_SECRET"
        if category == "SUSPECTED_SECRET" or security in {"QUARANTINED", "BLOCKED"}:
            classification = "QUARANTINED"
            included = False
            reason = "SECURITY_POLICY_PRECEDENCE"
        elif security == "UNKNOWN":
            classification = "PENDING_REVIEW"
            included = False
            reason = "SECURITY_ASSESSMENT_REQUIRED"
        elif not included:
            classification = "EXCLUDED"
            reason = "IGNORE_RULE"
        elif category in {"VENDORED", "GENERATED", "CACHE", "SUSPECTED_SECRET"}:
            classification = "METADATA_ONLY"
            reason = category
        else:
            classification = "INCLUDED"
            reason = "SOURCE_DEFAULT"
        classifications.append({"path": path, "classification": classification, "category": category, "reason": reason, "matched_rules": matched, "security_state": security})
    extra_states = sorted(str(path) for path in security_states if str(path) not in seen_paths)
    if extra_states:
        raise ProjectContractError("security assessment contains paths outside the classification inventory")
    view = {"policy_version": version, "security_assessment_verified": assessment_verified, "entries": classifications}
    view["view_digest"] = _digest(view)
    return {"state": "PARTIAL" if unknown_security else "SUCCEEDED", "code": "PACKAGE_ANALYSIS_REVIEW_REQUIRED" if unknown_security else "PACKAGE_ANALYSIS_VIEW_CREATED", "outputs": view}


def _python_symbols(
    path: str,
    source: str,
    *,
    source_digest: str,
    source_version: str,
    source_anchor: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tree = ast.parse(source, filename=path)
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_count = 0
    for node in ast.walk(tree):
        node_count += 1
        if node_count > _MAX_AST_NODES_PER_FILE:
            raise ProjectContractError("python AST exceeds the bounded node limit")
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            line_end = getattr(node, "end_lineno", node.lineno)
            symbols.append(
                {
                    "name": node.name,
                    "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "path": path,
                    "line_start": node.lineno,
                    "line_end": line_end,
                    "parser": "python-ast",
                    "source_digest": source_digest,
                    "source_version": source_version,
                    "anchor": {
                        **dict(source_anchor),
                        "path": path,
                        "line_start": node.lineno,
                        "line_end": line_end,
                    },
                }
            )
        elif isinstance(node, ast.Import):
            line_end = getattr(node, "end_lineno", node.lineno)
            edges.extend(
                {
                    "source": path,
                    "target": alias.name,
                    "kind": "import",
                    "confidence": 1.0,
                    "source_digest": source_digest,
                    "source_version": source_version,
                    "anchor": {
                        **dict(source_anchor),
                        "path": path,
                        "line_start": node.lineno,
                        "line_end": line_end,
                    },
                }
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            line_end = getattr(node, "end_lineno", node.lineno)
            edges.append(
                {
                    "source": path,
                    "target": node.module,
                    "kind": "import",
                    "confidence": 1.0,
                    "source_digest": source_digest,
                    "source_version": source_version,
                    "anchor": {
                        **dict(source_anchor),
                        "path": path,
                        "line_start": node.lineno,
                        "line_end": line_end,
                    },
                }
            )
        if len(symbols) > _MAX_SYMBOLS_PER_FILE:
            raise ProjectContractError("python symbols exceed the bounded per-file limit")
        if len(edges) > _MAX_SYMBOLS_PER_FILE:
            raise ProjectContractError("python dependency edges exceed the bounded per-file limit")
    return symbols, edges


_DECLARATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("class", re.compile(r"^\s*(?:export\s+|public\s+|private\s+|protected\s+|abstract\s+)*(?:class|interface|enum|struct|trait|protocol)\s+([A-Za-z_][\w$]*)", re.M)),
    ("function", re.compile(r"^\s*(?:export\s+|public\s+|private\s+|protected\s+|static\s+|async\s+)*(?:function|func|fn|fun|def)\s+([A-Za-z_][\w$]*)", re.M)),
)


def index_repository_symbols(request: Mapping[str, Any]) -> dict[str, Any]:
    """Index Python with AST and other text languages with explicit partial heuristics."""

    values = _inputs(request)
    files = _sequence(values.get("files", []), "inputs.files", maximum=_MAX_SOURCE_FILES)
    if not files:
        return {"state": "BLOCKED", "code": "REPOSITORY_SOURCE_FILES_EMPTY", "outputs": {"symbols": [], "edges": [], "failures": []}}
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    source_inventory: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, int | str]] = defaultdict(lambda: {"files": 0, "parsed": 0, "parser": "unavailable"})
    seen_paths: set[str] = set()
    portable_paths: set[str] = set()
    cumulative_bytes = 0
    for index, raw in enumerate(files):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"inputs.files[{index}] must be an object")
        path = normalize_relative_path(raw.get("path"))
        portable = unicodedata.normalize("NFKC", path).casefold()
        if path in seen_paths or portable in portable_paths:
            raise ProjectContractError("repository source files contain a duplicate or portable path collision")
        seen_paths.add(path)
        portable_paths.add(portable)
        source = raw.get("content")
        if not isinstance(source, str):
            raise ProjectContractError("repository source content must be text")
        encoded = source.encode("utf-8")
        if len(encoded) > _MAX_SOURCE_FILE_BYTES or len(encoded) > _MAX_SOURCE_TOTAL_BYTES - cumulative_bytes:
            raise ProjectContractError("repository sources exceed the bounded parse byte limit")
        cumulative_bytes += len(encoded)
        source_digest = _require_digest(raw.get("content_digest"), f"inputs.files[{index}].content_digest")
        if source_digest != _digest(encoded):
            raise ProjectContractError("repository source digest does not match content")
        source_version = _bounded_string(
            raw.get("source_version"),
            f"inputs.files[{index}].source_version",
            maximum_bytes=256,
        )
        source_anchor = raw.get("anchor")
        if not isinstance(source_anchor, Mapping) or not source_anchor:
            raise ProjectContractError("repository source provenance anchor is required")
        encoded_anchor = _canonical(source_anchor).encode("utf-8")
        if len(encoded_anchor) > 64 * 1024:
            raise ProjectContractError("repository source provenance anchor exceeds the bounded size")
        source_inventory.append(
            {
                "path": path,
                "content_digest": source_digest,
                "source_version": source_version,
                "anchor": dict(source_anchor),
                "byte_count": len(encoded),
                "provenance_state": "INPUT_BOUND",
            }
        )
        language = next((name for name, extensions in _LANGUAGE_EXTENSIONS.items() if any(path.lower().endswith(extension) for extension in extensions)), "Unknown")
        coverage[language]["files"] = int(coverage[language]["files"]) + 1
        try:
            if language == "Python":
                discovered, dependencies = _python_symbols(
                    path,
                    source,
                    source_digest=source_digest,
                    source_version=source_version,
                    source_anchor=source_anchor,
                )
                coverage[language]["parser"] = "python-ast"
            elif language != "Unknown":
                discovered = []
                line_offsets = [position for position, character in enumerate(source) if character == "\n"]
                for kind, pattern in _DECLARATION_PATTERNS:
                    for match in pattern.finditer(source):
                        if len(discovered) >= _MAX_SYMBOLS_PER_FILE:
                            raise ProjectContractError("heuristic symbols exceed the bounded per-file limit")
                        line = bisect.bisect_right(line_offsets, match.start()) + 1
                        discovered.append({"name": match.group(1), "kind": kind, "path": path, "line_start": line, "line_end": line, "parser": "bounded-declaration-heuristic", "confidence": 0.55, "source_digest": source_digest, "source_version": source_version, "anchor": {**dict(source_anchor), "path": path, "line_start": line, "line_end": line}})
                dependencies = []
                coverage[language]["parser"] = "bounded-declaration-heuristic-partial"
            else:
                failures.append({"path": path, "code": "LANGUAGE_ADAPTER_UNAVAILABLE"})
                continue
            coverage[language]["parsed"] = int(coverage[language]["parsed"]) + 1
            if len(discovered) > _MAX_SYMBOLS - len(symbols):
                raise ProjectContractError("repository symbols exceed the cumulative limit")
            if len(dependencies) > _MAX_REPOSITORY_EDGES - len(edges):
                raise ProjectContractError("repository dependency edges exceed the cumulative limit")
            symbols.extend(discovered)
            edges.extend(dependencies)
        except ProjectContractError:
            raise
        except (SyntaxError, ValueError, RecursionError) as exc:
            failures.append({"path": path, "code": "PARSER_FAILED", "detail": str(exc)[:200]})
    for symbol in symbols:
        symbol["symbol_id"] = "symbol_" + _digest(symbol)[7:31]
    symbols.sort(key=lambda item: (item["path"], item["line_start"], item["name"]))
    edges.sort(key=lambda item: (item["source"], item["target"], item["kind"]))
    report = {
        "symbols": symbols,
        "edges": edges,
        "failures": failures,
        "coverage": dict(sorted(coverage.items())),
        "source_inventory": sorted(source_inventory, key=lambda item: item["path"]),
        "source_file_count": len(files),
        "source_bytes": cumulative_bytes,
        "parse_limits": {
            "per_file_bytes": _MAX_SOURCE_FILE_BYTES,
            "total_bytes": _MAX_SOURCE_TOTAL_BYTES,
            "ast_nodes_per_file": _MAX_AST_NODES_PER_FILE,
            "symbols_per_file": _MAX_SYMBOLS_PER_FILE,
            "symbols_total": _MAX_SYMBOLS,
            "edges_total": _MAX_REPOSITORY_EDGES,
        },
        "user_code_executed": False,
    }
    report["repository_map_digest"] = _digest(report)
    partial = bool(failures) or any("partial" in str(item["parser"]) for item in coverage.values())
    return {"state": "PARTIAL" if partial else "SUCCEEDED", "code": "REPOSITORY_SYMBOL_INDEX_PARTIAL" if partial else "REPOSITORY_SYMBOL_INDEXED", "outputs": report}


def build_repository_context_map(request: Mapping[str, Any]) -> dict[str, Any]:
    """Build a layered graph and an explicit, confidence-aware impact set."""

    values = _inputs(request)
    modules = _sequence(values.get("modules", []), "inputs.modules", maximum=_MAX_PROJECT_ENTRIES)
    symbols = _sequence(values.get("symbols", []), "inputs.symbols", maximum=_MAX_SYMBOLS)
    edges = _sequence(values.get("edges", []), "inputs.edges", maximum=_MAX_SYMBOLS)
    nodes: dict[str, dict[str, Any]] = {}
    map_bytes = 0
    for index, raw in enumerate(modules + symbols):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"repository map node {index} must be an object")
        node_id_value = raw.get("node_id")
        if node_id_value is None:
            node_id_value = raw.get("symbol_id")
        if node_id_value is None:
            node_id_value = raw.get("path")
        node_id = _bounded_string(
            node_id_value,
            f"repository map node {index} identity",
            maximum_bytes=512,
        )
        if node_id in nodes:
            raise ProjectContractError("repository map node identities must be unique")
        encoded_node = _canonical(raw).encode("utf-8")
        if len(encoded_node) > _MAX_REPOSITORY_MAP_BYTES - map_bytes:
            raise ProjectContractError("repository map exceeds the bounded JSON size")
        map_bytes += len(encoded_node)
        nodes[node_id] = dict(raw)
    if not nodes:
        return {"state": "BLOCKED", "code": "REPOSITORY_MAP_NODES_EMPTY", "outputs": {"nodes": [], "edges": []}}
    adjacency: dict[str, set[str]] = defaultdict(set)
    uncertain: list[dict[str, Any]] = []
    normalized_edges: list[dict[str, Any]] = []
    edge_ids: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(edges):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"repository map edge {index} must be an object")
        encoded_edge = _canonical(raw).encode("utf-8")
        if len(encoded_edge) > _MAX_REPOSITORY_MAP_BYTES - map_bytes:
            raise ProjectContractError("repository map exceeds the bounded JSON size")
        map_bytes += len(encoded_edge)
        source = _bounded_string(raw.get("source"), f"repository map edge {index} source", maximum_bytes=512)
        target = _bounded_string(raw.get("target"), f"repository map edge {index} target", maximum_bytes=512)
        kind = _bounded_string(raw.get("kind", "dependency"), f"repository map edge {index} kind", maximum_bytes=128)
        if source not in nodes or target not in nodes:
            raise ProjectContractError("repository map edges must reference existing endpoints")
        edge_id = (source, target, kind)
        if edge_id in edge_ids:
            raise ProjectContractError("repository map edges must be unique")
        edge_ids.add(edge_id)
        confidence = _finite_number(raw.get("confidence"), "edge.confidence", minimum=0.0, maximum=1.0)
        edge = {"source": source, "target": target, "kind": kind, "confidence": confidence}
        normalized_edges.append(edge)
        if confidence < 0.6:
            uncertain.append(edge)
        else:
            adjacency[source].add(target)
    raw_changed = _sequence(values.get("changed_node_ids", []), "inputs.changed_node_ids", maximum=_MAX_PROJECT_ENTRIES)
    changed: list[str] = []
    changed_seen: set[str] = set()
    for index, raw in enumerate(raw_changed):
        node_id = _bounded_string(raw, f"changed_node_ids[{index}]", maximum_bytes=512)
        if node_id not in nodes or node_id in changed_seen:
            raise ProjectContractError("changed_node_ids must be unique existing node identities")
        changed_seen.add(node_id)
        changed.append(node_id)
    impacted: set[str] = set(changed)
    queue = deque(changed)
    reverse: dict[str, set[str]] = defaultdict(set)
    for source, targets in adjacency.items():
        for target in targets:
            reverse[target].add(source)
    while queue:
        current = queue.popleft()
        for dependent in sorted(reverse.get(current, set())):
            if dependent not in impacted:
                impacted.add(dependent)
                queue.append(dependent)
    context_map = {
        "nodes": [nodes[key] for key in sorted(nodes)],
        "edges": sorted(normalized_edges, key=lambda item: (item["source"], item["target"], item["kind"])),
        "uncertain_edges": sorted(uncertain, key=lambda item: (item["source"], item["target"], item["kind"])),
        "impact_candidates": sorted(impacted),
    }
    context_map["map_digest"] = _digest(context_map)
    return {"state": "PARTIAL" if uncertain else "SUCCEEDED", "code": "REPOSITORY_MAP_HAS_UNCERTAINTY" if uncertain else "REPOSITORY_CONTEXT_MAP_CREATED", "outputs": context_map}


def _validated_diff_entries(value: Any, field: str) -> dict[str, dict[str, Any]]:
    raw_entries = _sequence(value, field, maximum=_MAX_PROJECT_ENTRIES)
    result: dict[str, dict[str, Any]] = {}
    portable_paths: set[str] = set()
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"{field}[{index}] must be an object")
        path = normalize_relative_path(raw.get("path"))
        portable = unicodedata.normalize("NFKC", path).casefold()
        if path in result or portable in portable_paths:
            raise ProjectContractError(f"{field} contains a duplicate or portable path collision")
        portable_paths.add(portable)
        entry = dict(raw)
        entry["path"] = path
        entry["content_digest"] = _require_digest(raw.get("content_digest"), f"{field}[{index}].content_digest")
        if "size" in raw:
            entry["size"] = _bounded_int(
                raw.get("size"),
                f"{field}[{index}].size",
                minimum=0,
                maximum=_MAX_PROJECT_ENTRY_BYTES,
            )
        result[path] = entry
    return result


def plan_incremental_update(request: Mapping[str, Any]) -> dict[str, Any]:
    """Diff immutable manifests with validated digests and one-to-one renames."""

    values = _inputs(request)
    old = _validated_diff_entries(values.get("previous_entries", []), "inputs.previous_entries")
    new = _validated_diff_entries(values.get("current_entries", []), "inputs.current_entries")
    if not old and not new:
        return {"state": "BLOCKED", "code": "PACKAGE_DIFF_INPUT_EMPTY", "outputs": {"rename_candidates": []}}
    digest_sizes: dict[str, set[int]] = defaultdict(set)
    for entry in (*old.values(), *new.values()):
        if entry.get("size") is not None:
            digest_sizes[str(entry["content_digest"])].add(int(entry["size"]))
    if any(len(sizes) > 1 for sizes in digest_sizes.values()):
        raise ProjectContractError("equal content digests cannot have contradictory sizes")
    unchanged = sorted(path for path in old.keys() & new.keys() if old[path].get("content_digest") == new[path].get("content_digest"))
    modified = sorted(path for path in old.keys() & new.keys() if old[path].get("content_digest") != new[path].get("content_digest"))
    deleted = sorted(old.keys() - new.keys())
    added = sorted(new.keys() - old.keys())
    renames: list[dict[str, Any]] = []
    matched_deleted: set[str] = set()
    matched_added: set[str] = set()
    old_by_digest: dict[str, list[str]] = defaultdict(list)
    new_by_digest: dict[str, list[str]] = defaultdict(list)
    for path in deleted:
        old_by_digest[str(old[path]["content_digest"])].append(path)
    for path in added:
        new_by_digest[str(new[path]["content_digest"])].append(path)
    ambiguous_renames: list[dict[str, Any]] = []
    for digest in sorted(old_by_digest.keys() & new_by_digest.keys()):
        sources = sorted(old_by_digest[digest])
        targets = sorted(new_by_digest[digest])
        if len(sources) == 1 and len(targets) == 1:
            source, target = sources[0], targets[0]
            renames.append({"from": source, "to": target, "confidence": 1.0, "basis": "IDENTICAL_CONTENT_DIGEST"})
            matched_deleted.add(source)
            matched_added.add(target)
        else:
            ambiguous_renames.append({"content_digest": digest, "deleted_paths": sources, "added_paths": targets, "reason": "RENAME_NOT_ONE_TO_ONE"})
    diff = {"added": [path for path in added if path not in matched_added], "modified": modified, "deleted": [path for path in deleted if path not in matched_deleted], "unchanged": unchanged, "rename_candidates": renames, "ambiguous_rename_groups": ambiguous_renames, "reparse_paths": sorted(set(modified) | (set(added) - matched_added)), "reuse_paths": unchanged + sorted(matched_added)}
    diff["diff_digest"] = _digest(diff)
    return {"state": "PARTIAL" if ambiguous_renames else "SUCCEEDED", "code": "PACKAGE_RENAME_REVIEW_REQUIRED" if ambiguous_renames else "PACKAGE_INCREMENTAL_UPDATE_PLANNED", "outputs": diff}


def _review_override_authorized(
    request: Mapping[str, Any],
    *,
    path: str,
    before: str,
    after: str,
    package_version: str,
    package_digest: str,
    review_snapshot_digest: str,
) -> bool:
    if not package_version or not package_digest or not review_snapshot_digest:
        return False
    authorization = _trusted_mapping(request, "capabilities", "review_override_authorization")
    if authorization is None:
        return False
    allowed = authorization.get("allowed_overrides")
    if not isinstance(allowed, Mapping):
        return False
    transition = allowed.get(path)
    if not isinstance(transition, Mapping):
        return False
    return bool(
        authorization.get("verified") is True
        and authorization.get("consent_granted") is True
        and str(authorization.get("receipt_id", ""))
        and str(authorization.get("tenant_id", "")) == str(request.get("tenant_id", ""))
        and str(authorization.get("project_id", "")) == str(request.get("project_id", ""))
        and str(authorization.get("actor_id", "")) == str(request.get("actor_id", ""))
        and str(request.get("actor_id", ""))
        and str(authorization.get("package_version", "")) == package_version
        and str(authorization.get("package_digest", "")) == package_digest
        and str(authorization.get("review_snapshot_digest", "")) == review_snapshot_digest
        and str(transition.get("from", "")).upper() == before
        and str(transition.get("to", "")).upper() == after
    )


def _safe_review_findings(value: Any, field: str) -> list[dict[str, str]]:
    findings = _sequence(
        value,
        field,
        maximum=_MAX_SECURITY_FINDINGS_PER_ENTRY,
    )
    _canonical(findings)
    safe: list[dict[str, str]] = []
    for finding in findings:
        if isinstance(finding, Mapping):
            code = str(finding.get("code", "UNSPECIFIED"))[:128]
            severity = str(finding.get("severity", "UNKNOWN"))[:32]
        else:
            code = str(finding)[:128]
            severity = "UNKNOWN"
        safe.append({"code": code, "severity": severity})
    return safe


def _review_snapshot_candidates(request: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    candidates: list[tuple[str, Mapping[str, Any]]] = []
    for root_name in ("policy", "capabilities"):
        root = request.get(root_name, {})
        if not isinstance(root, Mapping):
            raise ProjectContractError(f"trusted {root_name} must be an object")
        snapshot = root.get("package_review_snapshot")
        if snapshot is not None:
            if not isinstance(snapshot, Mapping):
                raise ProjectContractError(
                    f"{root_name}.package_review_snapshot must be an object"
                )
            candidates.append((f"{root_name}.package_review_snapshot", snapshot))
        registry = root.get("package_review_registry")
        if registry is not None:
            if not isinstance(registry, Mapping):
                raise ProjectContractError(
                    f"{root_name}.package_review_registry must be an object"
                )
            snapshots = _sequence(
                registry.get("snapshots", []),
                f"{root_name}.package_review_registry.snapshots",
                maximum=10_000,
            )
            for index, item in enumerate(snapshots):
                if not isinstance(item, Mapping):
                    raise ProjectContractError(
                        f"{root_name}.package_review_registry.snapshots[{index}] must be an object"
                    )
                candidates.append(
                    (f"{root_name}.package_review_registry.snapshots[{index}]", item)
                )
    return candidates


def _trusted_package_review_snapshot(
    request: Mapping[str, Any],
    *,
    package_version: str,
    package_digest: str,
    entry_identities: list[dict[str, str]],
) -> tuple[str, str, dict[str, Mapping[str, Any]]] | None:
    """Resolve one exact host-owned review snapshot for the requested package."""

    entries_digest = _digest(entry_identities)
    tenant_id = str(request.get("tenant_id", ""))
    project_id = str(request.get("project_id", ""))
    if not tenant_id or not project_id:
        raise ProjectContractError("review scope requires tenant_id and project_id")
    matching: list[tuple[str, Mapping[str, Any]]] = []
    for source, snapshot in _review_snapshot_candidates(request):
        if (
            str(snapshot.get("tenant_id", "")) == tenant_id
            and str(snapshot.get("project_id", "")) == project_id
            and str(snapshot.get("package_version", "")) == package_version
            and str(snapshot.get("package_digest", "")) == package_digest
            and str(snapshot.get("entries_digest", "")) == entries_digest
        ):
            matching.append((source, snapshot))
    if not matching:
        return None
    if len(matching) != 1:
        raise ProjectContractError("package review authority is ambiguous")

    source, snapshot = matching[0]
    if snapshot.get("verified") is not True or snapshot.get("authorized") is not True:
        raise ProjectContractError("package review snapshot is not verified and authorized")
    _bounded_string(snapshot.get("receipt_id"), "review receipt_id", maximum_bytes=512)
    _bounded_string(snapshot.get("registry_version"), "review registry_version", maximum_bytes=256)
    snapshot_digest = _require_digest(snapshot.get("snapshot_digest"), "review snapshot_digest")
    digest_payload = {key: value for key, value in snapshot.items() if key != "snapshot_digest"}
    if _digest(digest_payload) != snapshot_digest:
        raise ProjectContractError("package review snapshot digest does not match its content")

    raw_entries = _sequence(
        snapshot.get("entries", []),
        "trusted package review entries",
        maximum=_MAX_REVIEW_ENTRIES,
    )
    authoritative: dict[str, Mapping[str, Any]] = {}
    trusted_identities: list[dict[str, str]] = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"trusted review entries[{index}] must be an object")
        path = normalize_relative_path(raw.get("path"))
        if path in authoritative:
            raise ProjectContractError("trusted review entries contain a duplicate path")
        content_digest = _require_digest(
            raw.get("content_digest"),
            f"trusted review entries[{index}].content_digest",
        )
        state = str(raw.get("state", "")).upper()
        if state not in _REVIEW_STATES:
            raise ProjectContractError("trusted review entry state is unsupported")
        _bounded_string(
            raw.get("classification"),
            f"trusted review entries[{index}].classification",
            maximum_bytes=128,
        )
        _bounded_string(
            raw.get("role"),
            f"trusted review entries[{index}].role",
            maximum_bytes=128,
        )
        _safe_review_findings(
            raw.get("security_findings", []),
            f"trusted review entries[{index}].security_findings",
        )
        authoritative[path] = raw
        trusted_identities.append({"path": path, "content_digest": content_digest})
    trusted_identities.sort(key=lambda item: item["path"])
    if trusted_identities != entry_identities or _digest(trusted_identities) != entries_digest:
        raise ProjectContractError("package review snapshot entries do not match the request")
    return source, snapshot_digest, authoritative


def build_package_review_view(request: Mapping[str, Any]) -> dict[str, Any]:
    """Create a bounded review model from host-owned, digest-bound decisions."""

    values = _inputs(request)
    untrusted_authority = {
        "authorized_tools",
        "consent",
        "authorization",
        "override_authorization",
        "receipt",
        "receipts",
        "policy",
    }
    if untrusted_authority & set(values):
        raise ProjectContractError("review authority must be supplied by trusted context")
    entries = _sequence(values.get("entries", []), "inputs.entries", maximum=_MAX_REVIEW_ENTRIES)
    offset = _bounded_int(values.get("offset", 0), "offset", minimum=0, maximum=_MAX_REVIEW_ENTRIES)
    limit = _bounded_int(values.get("limit", 100), "limit", minimum=1, maximum=500)
    overrides = values.get("overrides", {})
    if not isinstance(overrides, Mapping) or len(overrides) > _MAX_REVIEW_ENTRIES:
        raise ProjectContractError("overrides must be a bounded object")
    input_entries: list[tuple[str, str | None]] = []
    known_paths: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, Mapping):
            raise ProjectContractError(f"inputs.entries[{index}] must be an object")
        path = normalize_relative_path(raw.get("path"))
        if path in known_paths:
            raise ProjectContractError("review entries contain a duplicate path")
        known_paths.add(path)
        raw_digest = raw.get("content_digest")
        content_digest = (
            _require_digest(raw_digest, f"inputs.entries[{index}].content_digest")
            if raw_digest is not None
            else None
        )
        input_entries.append((path, content_digest))

    package_version_raw = values.get("package_version")
    package_digest_raw = values.get("package_digest")
    has_package_scope = package_version_raw is not None or package_digest_raw is not None
    if has_package_scope:
        package_version = _bounded_string(
            package_version_raw,
            "inputs.package_version",
            maximum_bytes=256,
        )
        package_digest = _require_digest(package_digest_raw, "inputs.package_digest")
    else:
        package_version = ""
        package_digest = ""
    entry_identities = [
        {"path": path, "content_digest": content_digest}
        for path, content_digest in input_entries
        if content_digest is not None
    ]
    entry_identities.sort(key=lambda item: item["path"])
    trusted_review = None
    if entries and has_package_scope:
        if len(entry_identities) != len(entries):
            raise ProjectContractError(
                "all review entries require content_digest when package scope is supplied"
            )
        trusted_review = _trusted_package_review_snapshot(
            request,
            package_version=package_version,
            package_digest=package_digest,
            entry_identities=entry_identities,
        )

    rows: list[dict[str, Any]] = []
    rejected_overrides: list[dict[str, str]] = []
    authority_source = "NONE"
    review_snapshot_digest = ""
    authoritative_entries: dict[str, Mapping[str, Any]] = {}
    if trusted_review is not None:
        authority_source, review_snapshot_digest, authoritative_entries = trusted_review
    for path, _content_digest in input_entries:
        authoritative = authoritative_entries.get(path)
        if authoritative is None:
            state = "PENDING"
            classification = "UNCLASSIFIED"
            role = "UNCLASSIFIED"
            safe_findings: list[dict[str, str]] = []
        else:
            state = str(authoritative["state"]).upper()
            classification = str(authoritative["classification"])
            role = str(authoritative["role"])
            safe_findings = _safe_review_findings(
                authoritative.get("security_findings", []),
                f"trusted review entry {path}.security_findings",
            )
        if safe_findings and state == "READY":
            state = "BLOCKED"
        requested_raw = overrides.get(path)
        override_applied = False
        if requested_raw is not None:
            requested = str(requested_raw).upper()
            if requested not in _REVIEW_STATES:
                rejected_overrides.append({"path": path, "code": "OVERRIDE_STATE_INVALID"})
            elif state == "QUARANTINED":
                rejected_overrides.append({"path": path, "code": "QUARANTINE_OVERRIDE_FORBIDDEN"})
            elif not _review_override_authorized(
                request,
                path=path,
                before=state,
                after=requested,
                package_version=package_version,
                package_digest=package_digest,
                review_snapshot_digest=review_snapshot_digest,
            ):
                rejected_overrides.append({"path": path, "code": "OVERRIDE_AUTHORIZATION_REQUIRED"})
            elif safe_findings and requested == "READY":
                rejected_overrides.append({"path": path, "code": "SECURITY_FINDINGS_OVERRIDE_FORBIDDEN"})
            else:
                state = requested
                override_applied = True
        rows.append(
            {
                "path": path,
                "state": state,
                "classification": classification,
                "role": role,
                "security_findings": safe_findings,
                "override_allowed": override_applied,
            }
        )
    for raw_path in overrides:
        path = normalize_relative_path(raw_path)
        if path not in known_paths:
            rejected_overrides.append({"path": path, "code": "OVERRIDE_TARGET_NOT_FOUND"})
    rows.sort(key=lambda item: item["path"])
    page = rows[offset : offset + limit]
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["state"]] += 1
    ready_count = counts.get("READY", 0)
    incomplete = not rows or ready_count != len(rows)
    readiness = "PARTIALLY_READY" if incomplete and ready_count else "NOT_READY" if incomplete else "READY"
    view = {
        "entries": page,
        "offset": offset,
        "limit": limit,
        "total": len(rows),
        "has_more": offset + limit < len(rows),
        "counts": dict(sorted(counts.items())),
        "readiness": readiness,
        "rejected_overrides": rejected_overrides,
        "virtualized": True,
        "secret_values_included": False,
        "review_authority": authority_source,
        "review_snapshot_digest": review_snapshot_digest or None,
        "external_evidence": "NOT_RUN",
    }
    view["view_digest"] = _digest(view)
    if not rows:
        state, code = "BLOCKED", "PACKAGE_REVIEW_EMPTY"
    elif rejected_overrides:
        state, code = "BLOCKED", "PACKAGE_REVIEW_OVERRIDE_BLOCKED"
    elif trusted_review is None:
        state, code = "PARTIAL", "PACKAGE_REVIEW_TRUSTED_SNAPSHOT_REQUIRED"
    else:
        state, code = "SUCCEEDED", "PACKAGE_REVIEW_VIEW_CREATED"
    return {"state": state, "code": code, "outputs": view}
