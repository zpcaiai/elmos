"""Dependency-free projections for the Project Intelligence source schemas.

The source package is an untrusted declarative specification.  This module
does not import or execute anything from that package.  It implements the
small, deterministic subset needed by the bounded local engine and validates
the resulting JSON values without depending on ``jsonschema``.

Builders deliberately accept authenticated scope as a separate object.  A
caller payload therefore cannot replace tenant, project, or revision identity.
Wall-clock values are never sampled here: when a schema contains a timestamp,
the caller must supply the observed value explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import math
from pathlib import PurePosixPath
import re
from typing import Any, Protocol


class SchemaProjectionError(ValueError):
    """Raised when a source-schema projection would be ambiguous or invalid."""


class TrustedScope(Protocol):
    """Structural protocol implemented by ``TrustedRuntimeScope``."""

    tenant_id: str
    project_id: str
    revision: str


_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SOURCE_TYPES = frozenset(
    {"git", "zip", "directory", "elmos-generated", "elmos-converted"}
)
_FILE_KINDS = frozenset(
    {
        "source",
        "test",
        "config",
        "schema",
        "doc",
        "generated",
        "vendor",
        "binary",
        "other",
    }
)
_CLAIM_STATUSES = frozenset(
    {"confirmed", "inferred", "unknown", "recommended", "contradicted", "stale"}
)
_EVIDENCE_KINDS = frozenset(
    {"source", "ast", "config", "schema", "test", "trace", "log", "manual", "document"}
)
_JOB_STATES = frozenset(
    {
        "queued",
        "running",
        "pausing",
        "paused",
        "resuming",
        "retrying",
        "succeeded",
        "failed_retryable",
        "failed_final",
        "cancelling",
        "cancelled",
    }
)
_MAPPING_STATUSES = frozenset({"mapped", "partial", "unsupported", "manual"})
_SKILL_STATUSES = frozenset({"completed", "partial", "failed", "blocked"})
_TEST_RESULTS = frozenset({"passed", "failed", "not_run"})

_PROJECT_KEYS = frozenset(
    {
        "schema_version",
        "tenant_id",
        "project_id",
        "revision_id",
        "source_type",
        "repository",
        "content_hash",
        "files",
        "submodules",
        "created_at",
    }
)
_PROJECT_REQUIRED = frozenset(
    {
        "schema_version",
        "project_id",
        "revision_id",
        "source_type",
        "content_hash",
        "files",
        "created_at",
    }
)
_PROJECT_FILE_KEYS = frozenset(
    {"path", "sha256", "size", "kind", "language", "excluded"}
)
_REPOSITORY_KEYS = frozenset({"provider", "remote_ref", "branch", "commit_sha"})
_EVIDENCE_BUNDLE_KEYS = frozenset(
    {
        "schema_version",
        "bundle_id",
        "tenant_id",
        "project_id",
        "revision_id",
        "analysis_run_id",
        "claims",
        "evidence",
    }
)
_CONVERSION_KEYS = frozenset(
    {
        "mapping_id",
        "source_revision_id",
        "target_revision_id",
        "semantic_ir_version",
        "entries",
    }
)
_TRACE_KEYS = frozenset(
    {
        "link_id",
        "project_id",
        "revision_id",
        "environment",
        "time_window",
        "sampling",
        "span_ref",
        "target_refs",
        "confidence",
        "method",
    }
)

_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 250_000
_MAX_SEQUENCE_ITEMS = 100_000
_MAX_STRING_BYTES = 16 * 1024 * 1024


def _fail(message: str) -> SchemaProjectionError:
    return SchemaProjectionError(message)


def _object(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise _fail(f"{field_name} keys must be strings")
    return value


def _sequence(value: Any, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        raise _fail(f"{field_name} must be an array")
    if len(value) > _MAX_SEQUENCE_ITEMS:
        raise _fail(f"{field_name} exceeds the {_MAX_SEQUENCE_ITEMS}-item limit")
    return value


def _string(
    value: Any,
    field_name: str,
    *,
    nonempty: bool = False,
    max_bytes: int = 4_096,
) -> str:
    if not isinstance(value, str):
        raise _fail(f"{field_name} must be a string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise _fail(f"{field_name} contains an invalid Unicode scalar") from exc
    if nonempty and not value:
        raise _fail(f"{field_name} must be non-empty")
    if not encoded and nonempty:
        raise _fail(f"{field_name} must be non-empty")
    if len(encoded) > max_bytes:
        raise _fail(f"{field_name} exceeds {max_bytes} UTF-8 bytes")
    if "\x00" in value or any(ord(character) < 32 for character in value):
        raise _fail(f"{field_name} contains a control character")
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _string(value, field_name)


def _integer(value: Any, field_name: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise _fail(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise _fail(f"{field_name} must be at least {minimum}")
    return value


def _number(value: Any, field_name: str, *, bounded: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(f"{field_name} must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise _fail(f"{field_name} must be finite")
    if bounded and not 0 <= value <= 1:
        raise _fail(f"{field_name} must be between 0 and 1")
    return 0 if value == 0 else value


def _date_time(value: Any, field_name: str) -> str:
    text = _string(value, field_name, nonempty=True, max_bytes=64)
    if _RFC3339.fullmatch(text) is None:
        raise _fail(f"{field_name} must be an RFC 3339 date-time with an offset")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise _fail(f"{field_name} is not a valid RFC 3339 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _fail(f"{field_name} must include an explicit UTC offset")
    return text


def _parsed_date_time(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)


def _relative_path(value: Any, field_name: str) -> str:
    text = _string(value, field_name, nonempty=True, max_bytes=4_096)
    if text.startswith("/") or "\\" in text:
        raise _fail(f"{field_name} must be a relative POSIX path")
    parsed = PurePosixPath(text)
    if parsed.as_posix() != text or any(part in {"", ".", ".."} for part in parsed.parts):
        raise _fail(f"{field_name} contains an unsafe path component")
    return text


def _sha256(value: Any, field_name: str, *, accept_prefix: bool = False) -> str:
    text = _string(value, field_name, nonempty=True, max_bytes=72)
    if accept_prefix and text.startswith("sha256:"):
        text = text[7:]
    text = text.lower()
    if _SHA256.fullmatch(text) is None:
        raise _fail(f"{field_name} must be a lowercase SHA-256 hexadecimal digest")
    return text


def _json_clone(value: Any, field_name: str) -> Any:
    """Validate and detach an untrusted JSON-compatible value."""

    active: set[int] = set()
    nodes = 0

    def visit(item: Any, location: str, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise _fail(f"{field_name} exceeds the JSON node limit")
        if depth > _MAX_JSON_DEPTH:
            raise _fail(f"{field_name} exceeds the JSON nesting limit")
        if item is None or isinstance(item, bool) or type(item) is int:
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise _fail(f"{location} must be finite")
            return 0 if item == 0 else item
        if isinstance(item, str):
            return _string(item, location, max_bytes=_MAX_STRING_BYTES)
        identity = id(item)
        if identity in active:
            raise _fail(f"{location} contains a cycle")
        if isinstance(item, Mapping):
            active.add(identity)
            try:
                result: dict[str, Any] = {}
                for key, child in item.items():
                    key = _string(key, f"{location} key", max_bytes=4_096)
                    result[key] = visit(child, f"{location}.{key}", depth + 1)
                return result
            finally:
                active.remove(identity)
        if isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray, memoryview)
        ):
            if len(item) > _MAX_SEQUENCE_ITEMS:
                raise _fail(f"{location} exceeds the sequence item limit")
            active.add(identity)
            try:
                return [
                    visit(child, f"{location}[{index}]", depth + 1)
                    for index, child in enumerate(item)
                ]
            finally:
                active.remove(identity)
        raise _fail(f"{location} contains unsupported {type(item).__name__}")

    return visit(value, field_name, 0)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        _json_clone(value, "stable identity"),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scope(scope: TrustedScope) -> tuple[str, str, str]:
    try:
        tenant_id = scope.tenant_id
        project_id = scope.project_id
        revision = scope.revision
    except AttributeError as exc:
        raise _fail("scope must provide tenant_id, project_id, and revision") from exc
    return (
        _string(tenant_id, "scope.tenant_id", nonempty=True, max_bytes=256),
        _string(project_id, "scope.project_id", nonempty=True, max_bytes=256),
        _string(revision, "scope.revision", nonempty=True, max_bytes=256),
    )


def _unique_strings(value: Any, field_name: str, *, nonempty: bool = True) -> list[str]:
    values = [
        _string(item, f"{field_name}[{index}]", nonempty=nonempty)
        for index, item in enumerate(_sequence(value, field_name))
    ]
    if len(values) != len(set(values)):
        raise _fail(f"{field_name} cannot contain duplicates")
    return values


def _unexpected(value: Mapping[str, Any], allowed: frozenset[str], field_name: str) -> None:
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        raise _fail(f"{field_name} contains unsupported fields: {', '.join(unexpected)}")


_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cc": "c++",
    ".cpp": "c++",
    ".hpp": "c++",
    ".php": "php",
    ".rb": "ruby",
    ".sql": "sql",
    ".sh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
}
_SOURCE_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".mjs",
        ".ts",
        ".tsx",
        ".java",
        ".kt",
        ".kts",
        ".go",
        ".rs",
        ".cs",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".php",
        ".rb",
        ".sh",
    }
)
_BINARY_SUFFIXES = frozenset(
    {".a", ".bin", ".class", ".dll", ".dylib", ".exe", ".jar", ".o", ".so", ".wasm"}
)
_CONFIG_NAMES = frozenset(
    {"dockerfile", "makefile", "package.json", "pyproject.toml", "pom.xml", "go.mod", "cargo.toml"}
)


def _infer_file_kind(path: str) -> str:
    parsed = PurePosixPath(path)
    lower_parts = tuple(part.lower() for part in parsed.parts)
    name = parsed.name.lower()
    suffix = parsed.suffix.lower()
    if "vendor" in lower_parts:
        return "vendor"
    if any(part in {"generated", "dist"} for part in lower_parts):
        return "generated"
    if suffix in _BINARY_SUFFIXES:
        return "binary"
    if "schemas" in lower_parts or suffix in {".xsd", ".proto"} or name.endswith(".schema.json"):
        return "schema"
    if (
        "tests" in lower_parts
        or "test" in lower_parts
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    ):
        return "test"
    if suffix in {".md", ".rst", ".adoc"} or name.startswith(("readme", "license")):
        return "doc"
    if name in _CONFIG_NAMES or suffix in {".json", ".toml", ".yaml", ".yml"}:
        return "config"
    if suffix in _SOURCE_SUFFIXES:
        return "source"
    return "other"


def _normalise_project_file(value: Any, index: int) -> dict[str, Any]:
    record = _object(value, f"files[{index}]")
    path = _relative_path(record.get("path"), f"files[{index}].path")
    text = record.get("text")
    if text is not None:
        text = _string(text, f"files[{index}].text", max_bytes=_MAX_STRING_BYTES)
        observed_bytes = text.encode("utf-8")
    else:
        observed_bytes = None

    supplied_digest = record.get("sha256")
    if supplied_digest is None:
        if observed_bytes is None:
            raise _fail(f"files[{index}] requires sha256 or text")
        digest = hashlib.sha256(observed_bytes).hexdigest()
    else:
        digest = _sha256(supplied_digest, f"files[{index}].sha256", accept_prefix=True)
        if observed_bytes is not None and hashlib.sha256(observed_bytes).hexdigest() != digest:
            raise _fail(f"files[{index}] text does not match sha256")

    size_values = [record[key] for key in ("size", "bytes") if key in record]
    if len(size_values) == 2 and size_values[0] != size_values[1]:
        raise _fail(f"files[{index}].size and bytes disagree")
    if size_values:
        size = _integer(size_values[0], f"files[{index}].size", minimum=0)
    elif observed_bytes is not None:
        size = len(observed_bytes)
    else:
        raise _fail(f"files[{index}] requires size/bytes when text is absent")
    if observed_bytes is not None and size != len(observed_bytes):
        raise _fail(f"files[{index}].size does not match text")

    kind = record.get("kind", _infer_file_kind(path))
    if kind not in _FILE_KINDS:
        raise _fail(f"files[{index}].kind is unsupported")
    language = record.get("language", _LANGUAGES.get(PurePosixPath(path).suffix.lower()))
    if language is not None:
        language = _string(language, f"files[{index}].language", max_bytes=128)
    excluded = record.get("excluded", False)
    if type(excluded) is not bool:
        raise _fail(f"files[{index}].excluded must be a boolean")
    return {
        "path": path,
        "sha256": digest,
        "size": size,
        "kind": kind,
        "language": language,
        "excluded": excluded,
    }


def _normalise_repository(value: Any) -> dict[str, Any]:
    repository = _object(value, "repository")
    _unexpected(repository, _REPOSITORY_KEYS, "repository")
    result: dict[str, Any] = {}
    for key in ("provider", "remote_ref"):
        if key in repository:
            result[key] = _string(repository[key], f"repository.{key}")
    for key in ("branch", "commit_sha"):
        if key in repository:
            result[key] = _optional_string(repository[key], f"repository.{key}")
    return result


def _normalise_submodules(value: Any) -> list[dict[str, str]]:
    submodules: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(_sequence(value, "submodules")):
        record = _object(item, f"submodules[{index}]")
        path = _relative_path(record.get("path"), f"submodules[{index}].path")
        if path in seen:
            raise _fail(f"duplicate submodule path: {path}")
        seen.add(path)
        submodules.append(
            {
                "path": path,
                "commit_sha": _string(
                    record.get("commit_sha"),
                    f"submodules[{index}].commit_sha",
                    nonempty=True,
                ),
            }
        )
    return sorted(submodules, key=lambda item: item["path"])


def build_project_manifest(
    scope: TrustedScope,
    files: Sequence[Mapping[str, Any]],
    *,
    observed_at: str,
    source_type: str = "directory",
    repository: Mapping[str, Any] | None = None,
    submodules: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build an exact ``project-manifest.schema.json`` projection.

    ``observed_at`` becomes the schema's ``created_at`` field.  Requiring it
    prevents a hidden clock read from changing an otherwise identical result.
    The aggregate content hash excludes scope and time and is therefore stable
    for byte-identical file/submodule content.
    """

    tenant_id, project_id, revision = _scope(scope)
    if source_type not in _SOURCE_TYPES:
        raise _fail("source_type is unsupported")
    normalised_files = [
        _normalise_project_file(item, index)
        for index, item in enumerate(_sequence(files, "files"))
    ]
    normalised_files.sort(key=lambda item: item["path"])
    paths = [item["path"] for item in normalised_files]
    if len(paths) != len(set(paths)):
        raise _fail("files cannot contain duplicate paths")
    normalised_submodules = _normalise_submodules(submodules)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "revision_id": revision,
        "source_type": source_type,
        "content_hash": _stable_hash(
            {"files": normalised_files, "submodules": normalised_submodules}
        ),
        "files": normalised_files,
        "submodules": normalised_submodules,
        "created_at": _date_time(observed_at, "observed_at"),
    }
    if repository is not None:
        manifest["repository"] = _normalise_repository(repository)
    validate_project_manifest(manifest)
    return manifest


def validate_project_manifest(value: Any) -> dict[str, Any]:
    """Validate and detach a project-manifest value."""

    manifest = _object(value, "project_manifest")
    _unexpected(manifest, _PROJECT_KEYS, "project_manifest")
    missing = sorted(_PROJECT_REQUIRED - set(manifest))
    if missing:
        raise _fail(f"project_manifest is missing fields: {', '.join(missing)}")
    if _integer(manifest["schema_version"], "schema_version") != 1:
        raise _fail("schema_version must equal 1")
    if "tenant_id" in manifest:
        _string(manifest["tenant_id"], "tenant_id", nonempty=True)
    _string(manifest["project_id"], "project_id", nonempty=True)
    _string(manifest["revision_id"], "revision_id", nonempty=True)
    if manifest["source_type"] not in _SOURCE_TYPES:
        raise _fail("source_type is unsupported")
    _sha256(manifest["content_hash"], "content_hash")
    files = _sequence(manifest["files"], "files")
    paths: list[str] = []
    for index, item in enumerate(files):
        record = _object(item, f"files[{index}]")
        _unexpected(record, _PROJECT_FILE_KEYS, f"files[{index}]")
        required = {"path", "sha256", "size", "kind"}
        missing_file = sorted(required - set(record))
        if missing_file:
            raise _fail(f"files[{index}] is missing fields: {', '.join(missing_file)}")
        paths.append(_relative_path(record["path"], f"files[{index}].path"))
        _sha256(record["sha256"], f"files[{index}].sha256")
        _integer(record["size"], f"files[{index}].size", minimum=0)
        if record["kind"] not in _FILE_KINDS:
            raise _fail(f"files[{index}].kind is unsupported")
        if "language" in record:
            _optional_string(record["language"], f"files[{index}].language")
        if "excluded" in record and type(record["excluded"]) is not bool:
            raise _fail(f"files[{index}].excluded must be a boolean")
    if len(paths) != len(set(paths)):
        raise _fail("files cannot contain duplicate paths")
    if "repository" in manifest and manifest["repository"] is not None:
        _normalise_repository(manifest["repository"])
    if "submodules" in manifest:
        _normalise_submodules(manifest["submodules"])
    _date_time(manifest["created_at"], "created_at")
    return _json_clone(manifest, "project_manifest")


def _evidence_refs(
    value: Any,
    field_name: str,
    known_evidence_ids: set[str] | None,
) -> list[str]:
    refs = sorted(_unique_strings(value, field_name))
    if known_evidence_ids is not None:
        dangling = sorted(set(refs) - known_evidence_ids)
        if dangling:
            raise _fail(f"{field_name} contains dangling evidence references")
    return refs


def _normalise_graph_node(
    value: Any,
    index: int,
    known_evidence_ids: set[str],
) -> tuple[dict[str, Any], set[str]]:
    record = _object(value, f"nodes[{index}]")
    kind = _string(record.get("kind"), f"nodes[{index}].kind", nonempty=True)
    if "properties" in record:
        properties = _json_clone(
            _object(record["properties"], f"nodes[{index}].properties"),
            f"nodes[{index}].properties",
        )
    else:
        properties = _json_clone(
            {
                key: child
                for key, child in record.items()
                if key not in {"id", "kind", "stable_key", "evidence_refs"}
            },
            f"nodes[{index}].properties",
        )
    stable_key = record.get("stable_key")
    aliases: set[str] = set()
    if stable_key is not None:
        stable_key = _string(stable_key, f"nodes[{index}].stable_key", nonempty=True)
        aliases.add(stable_key)
    if "id" in record:
        node_id = _string(record["id"], f"nodes[{index}].id", nonempty=True)
    else:
        node_id = "node:" + _stable_hash(
            {"kind": kind, "stable_key": stable_key, "properties": properties}
        )
    aliases.add(node_id)
    refs = _evidence_refs(
        record.get("evidence_refs", []),
        f"nodes[{index}].evidence_refs",
        known_evidence_ids,
    )
    return (
        {"id": node_id, "kind": kind, "properties": properties, "evidence_refs": refs},
        aliases,
    )


def build_graph_snapshot(
    scope: TrustedScope,
    *,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    evidence_ids: Sequence[str] = (),
    projection_id: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Build a stable graph projection with closed endpoints and evidence refs."""

    _tenant_id, project_id, revision = _scope(scope)
    known_evidence_ids = set(_unique_strings(evidence_ids, "evidence_ids"))
    normalised_nodes: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    for index, item in enumerate(_sequence(nodes, "nodes")):
        node, node_aliases = _normalise_graph_node(item, index, known_evidence_ids)
        if node["id"] in {existing["id"] for existing in normalised_nodes}:
            raise _fail(f"duplicate node id: {node['id']}")
        for alias in node_aliases:
            existing = aliases.get(alias)
            if existing is not None and existing != node["id"]:
                raise _fail(f"ambiguous node alias: {alias}")
            aliases[alias] = node["id"]
        normalised_nodes.append(node)
    normalised_nodes.sort(key=lambda item: item["id"])

    normalised_edges: list[dict[str, Any]] = []
    seen_edges: set[str] = set()
    for index, item in enumerate(_sequence(edges, "edges")):
        record = _object(item, f"edges[{index}]")
        raw_source = record.get("source", record.get("from"))
        raw_target = record.get("target", record.get("to"))
        source_alias = _string(raw_source, f"edges[{index}].source", nonempty=True)
        target_alias = _string(raw_target, f"edges[{index}].target", nonempty=True)
        try:
            source = aliases[source_alias]
            target = aliases[target_alias]
        except KeyError as exc:
            raise _fail(f"edges[{index}] contains a dangling endpoint") from exc
        kind = _string(record.get("kind"), f"edges[{index}].kind", nonempty=True)
        refs = _evidence_refs(
            record.get("evidence_refs", []),
            f"edges[{index}].evidence_refs",
            known_evidence_ids,
        )
        edge_id = (
            _string(record["id"], f"edges[{index}].id", nonempty=True)
            if "id" in record
            else "edge:" + _stable_hash({"source": source, "target": target, "kind": kind})
        )
        if edge_id in seen_edges:
            raise _fail(f"duplicate edge id: {edge_id}")
        seen_edges.add(edge_id)
        edge: dict[str, Any] = {
            "id": edge_id,
            "source": source,
            "target": target,
            "kind": kind,
            "evidence_refs": refs,
        }
        if "confidence" in record:
            edge["confidence"] = _number(
                record["confidence"], f"edges[{index}].confidence", bounded=True
            )
        normalised_edges.append(edge)
    normalised_edges.sort(key=lambda item: item["id"])

    incident = {edge["source"] for edge in normalised_edges} | {
        edge["target"] for edge in normalised_edges
    }
    orphan_count = sum(node["id"] not in incident for node in normalised_nodes)
    evidence_backed = sum(bool(node["evidence_refs"]) for node in normalised_nodes)
    evidence_backed += sum(bool(edge["evidence_refs"]) for edge in normalised_edges)
    entity_count = len(normalised_nodes) + len(normalised_edges)
    quality = {
        "state": "STRUCTURALLY_VALIDATED_LOCAL",
        "verification_state": "NOT_RUN",
        "node_count": len(normalised_nodes),
        "edge_count": len(normalised_edges),
        "orphan_node_count": orphan_count,
        "orphan_rate_basis_points": (
            orphan_count * 10_000 // len(normalised_nodes) if normalised_nodes else 0
        ),
        "evidence_backed_entity_count": evidence_backed,
        "evidence_coverage_basis_points": (
            evidence_backed * 10_000 // entity_count if entity_count else 0
        ),
        "dangling_endpoint_count": 0,
        "dangling_evidence_reference_count": 0,
    }
    identity = {
        "project_id": project_id,
        "revision_id": revision,
        "nodes": normalised_nodes,
        "edges": normalised_edges,
        "quality": quality,
    }
    graph: dict[str, Any] = {
        "schema_version": 1,
        "project_id": project_id,
        "revision_id": revision,
        "projection_id": (
            _string(projection_id, "projection_id", nonempty=True)
            if projection_id is not None
            else "projection:" + _stable_hash(identity)
        ),
        "nodes": normalised_nodes,
        "edges": normalised_edges,
        "quality": quality,
    }
    if observed_at is not None:
        graph["created_at"] = _date_time(observed_at, "observed_at")
    validate_graph_snapshot(graph, evidence_ids=known_evidence_ids)
    return graph


def validate_graph_snapshot(
    value: Any,
    *,
    evidence_ids: Sequence[str] | set[str] | None = None,
) -> dict[str, Any]:
    graph = _object(value, "graph_snapshot")
    required = {"schema_version", "project_id", "revision_id", "projection_id", "nodes", "edges", "quality"}
    missing = sorted(required - set(graph))
    if missing:
        raise _fail(f"graph_snapshot is missing fields: {', '.join(missing)}")
    if _integer(graph["schema_version"], "schema_version") != 1:
        raise _fail("schema_version must equal 1")
    for key in ("project_id", "revision_id", "projection_id"):
        _string(graph[key], key, nonempty=True)
    known = None if evidence_ids is None else set(_unique_strings(list(evidence_ids), "evidence_ids"))
    node_ids: set[str] = set()
    for index, item in enumerate(_sequence(graph["nodes"], "nodes")):
        node = _object(item, f"nodes[{index}]")
        for key in ("id", "kind"):
            if key not in node:
                raise _fail(f"nodes[{index}] is missing {key}")
        node_id = _string(node["id"], f"nodes[{index}].id", nonempty=True)
        if node_id in node_ids:
            raise _fail(f"duplicate node id: {node_id}")
        node_ids.add(node_id)
        _string(node["kind"], f"nodes[{index}].kind", nonempty=True)
        if "properties" in node:
            _json_clone(_object(node["properties"], f"nodes[{index}].properties"), f"nodes[{index}].properties")
        if "evidence_refs" in node:
            _evidence_refs(node["evidence_refs"], f"nodes[{index}].evidence_refs", known)
    edge_ids: set[str] = set()
    for index, item in enumerate(_sequence(graph["edges"], "edges")):
        edge = _object(item, f"edges[{index}]")
        for key in ("id", "source", "target", "kind"):
            if key not in edge:
                raise _fail(f"edges[{index}] is missing {key}")
        edge_id = _string(edge["id"], f"edges[{index}].id", nonempty=True)
        if edge_id in edge_ids:
            raise _fail(f"duplicate edge id: {edge_id}")
        edge_ids.add(edge_id)
        source = _string(edge["source"], f"edges[{index}].source", nonempty=True)
        target = _string(edge["target"], f"edges[{index}].target", nonempty=True)
        if source not in node_ids or target not in node_ids:
            raise _fail(f"edges[{index}] contains a dangling endpoint")
        _string(edge["kind"], f"edges[{index}].kind", nonempty=True)
        if "confidence" in edge:
            _number(edge["confidence"], f"edges[{index}].confidence", bounded=True)
        if "evidence_refs" in edge:
            _evidence_refs(edge["evidence_refs"], f"edges[{index}].evidence_refs", known)
    _json_clone(_object(graph["quality"], "quality"), "quality")
    if "created_at" in graph:
        _date_time(graph["created_at"], "created_at")
    return _json_clone(graph, "graph_snapshot")


def _assert_unverified(record: Mapping[str, Any], field_name: str) -> None:
    for key in ("verified", "independently_verified", "certified"):
        if key in record and record[key] not in {False, None}:
            raise _fail(f"{field_name}.{key} would promote unverified evidence")
    if record.get("verifier") is not None or record.get("independent_verifier") is not None:
        raise _fail(f"{field_name} cannot name a verifier")
    if "verification_state" in record and record["verification_state"] not in {
        None,
        "NOT_RUN",
        "COLLECTED",
        "INCONCLUSIVE",
        "UNKNOWN",
        "REFERENCED_UNVERIFIED",
    }:
        raise _fail(f"{field_name}.verification_state promotes unavailable evidence")


def _normalise_evidence_record(value: Any, index: int) -> dict[str, Any]:
    record = _object(value, f"evidence[{index}]")
    _assert_unverified(record, f"evidence[{index}]")
    evidence_id = _string(
        record.get("evidence_id", record.get("id")),
        f"evidence[{index}].evidence_id",
        nonempty=True,
    )
    kind = record.get("kind", "source")
    if kind not in _EVIDENCE_KINDS:
        raise _fail(f"evidence[{index}].kind is unsupported")
    if "locator" in record:
        locator = _json_clone(
            _object(record["locator"], f"evidence[{index}].locator"),
            f"evidence[{index}].locator",
        )
    elif "path" in record:
        locator = {"path": _relative_path(record["path"], f"evidence[{index}].path")}
    else:
        raise _fail(f"evidence[{index}] requires locator or path")
    digest_value = record.get("hash", record.get("digest"))
    result: dict[str, Any] = {
        "evidence_id": evidence_id,
        "kind": kind,
        "locator": locator,
        "hash": _sha256(digest_value, f"evidence[{index}].hash", accept_prefix=True),
    }
    if "strength" in record:
        result["strength"] = _number(
            record["strength"], f"evidence[{index}].strength", bounded=True
        )
    if "classification" in record:
        result["classification"] = _string(
            record["classification"], f"evidence[{index}].classification"
        )
    return result


def _normalise_claim(
    value: Any,
    index: int,
    known_evidence_ids: set[str],
) -> dict[str, Any]:
    record = _object(value, f"claims[{index}]")
    _assert_unverified(record, f"claims[{index}]")
    claim_id = _string(
        record.get("claim_id", record.get("id")),
        f"claims[{index}].claim_id",
        nonempty=True,
    )
    text = _string(
        record.get("text", record.get("statement")),
        f"claims[{index}].text",
        nonempty=True,
        max_bytes=_MAX_STRING_BYTES,
    )
    evidence_refs = _evidence_refs(
        record.get("evidence_refs", []),
        f"claims[{index}].evidence_refs",
        known_evidence_ids,
    )
    counter_refs = _evidence_refs(
        record.get("counter_evidence_refs", []),
        f"claims[{index}].counter_evidence_refs",
        known_evidence_ids,
    )
    status = record.get("status", "inferred" if evidence_refs else "unknown")
    if status not in _CLAIM_STATUSES:
        raise _fail(f"claims[{index}].status is unsupported")
    if status == "confirmed" and not evidence_refs:
        raise _fail(f"claims[{index}] cannot be confirmed without evidence")
    result: dict[str, Any] = {
        "claim_id": claim_id,
        "text": text,
        "status": status,
        "confidence": _number(record.get("confidence", 0), f"claims[{index}].confidence", bounded=True),
        "evidence_refs": evidence_refs,
        "counter_evidence_refs": counter_refs,
    }
    if "generator" in record:
        result["generator"] = _json_clone(
            _object(record["generator"], f"claims[{index}].generator"),
            f"claims[{index}].generator",
        )
    return result


def build_evidence_bundle(
    scope: TrustedScope,
    *,
    claims: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    bundle_id: str | None = None,
    analysis_run_id: str | None = None,
) -> dict[str, Any]:
    """Map local claim/evidence records without manufacturing verification."""

    tenant_id, project_id, revision = _scope(scope)
    normalised_evidence = [
        _normalise_evidence_record(item, index)
        for index, item in enumerate(_sequence(evidence, "evidence"))
    ]
    evidence_ids = [item["evidence_id"] for item in normalised_evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise _fail("evidence cannot contain duplicate evidence_id values")
    normalised_evidence.sort(key=lambda item: item["evidence_id"])
    known_evidence_ids = set(evidence_ids)
    normalised_claims = [
        _normalise_claim(item, index, known_evidence_ids)
        for index, item in enumerate(_sequence(claims, "claims"))
    ]
    claim_ids = [item["claim_id"] for item in normalised_claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise _fail("claims cannot contain duplicate claim_id values")
    normalised_claims.sort(key=lambda item: item["claim_id"])
    identity = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "revision_id": revision,
        "analysis_run_id": analysis_run_id,
        "claims": normalised_claims,
        "evidence": normalised_evidence,
    }
    bundle: dict[str, Any] = {
        "schema_version": 1,
        "bundle_id": (
            _string(bundle_id, "bundle_id", nonempty=True)
            if bundle_id is not None
            else "bundle:" + _stable_hash(identity)
        ),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "revision_id": revision,
        "claims": normalised_claims,
        "evidence": normalised_evidence,
    }
    if analysis_run_id is not None:
        bundle["analysis_run_id"] = _string(
            analysis_run_id, "analysis_run_id", nonempty=True
        )
    validate_evidence_bundle(bundle)
    return bundle


def validate_evidence_bundle(value: Any) -> dict[str, Any]:
    bundle = _object(value, "evidence_bundle")
    _unexpected(bundle, _EVIDENCE_BUNDLE_KEYS, "evidence_bundle")
    required = {"schema_version", "bundle_id", "project_id", "revision_id", "claims", "evidence"}
    missing = sorted(required - set(bundle))
    if missing:
        raise _fail(f"evidence_bundle is missing fields: {', '.join(missing)}")
    if _integer(bundle["schema_version"], "schema_version") != 1:
        raise _fail("schema_version must equal 1")
    for key in ("bundle_id", "project_id", "revision_id"):
        _string(bundle[key], key, nonempty=True)
    for key in ("tenant_id", "analysis_run_id"):
        if key in bundle:
            _string(bundle[key], key, nonempty=True)
    evidence_ids: set[str] = set()
    for index, item in enumerate(_sequence(bundle["evidence"], "evidence")):
        record = _object(item, f"evidence[{index}]")
        for key in ("evidence_id", "kind", "locator", "hash"):
            if key not in record:
                raise _fail(f"evidence[{index}] is missing {key}")
        evidence_id = _string(record["evidence_id"], f"evidence[{index}].evidence_id", nonempty=True)
        if evidence_id in evidence_ids:
            raise _fail(f"duplicate evidence_id: {evidence_id}")
        evidence_ids.add(evidence_id)
        if record["kind"] not in _EVIDENCE_KINDS:
            raise _fail(f"evidence[{index}].kind is unsupported")
        _json_clone(_object(record["locator"], f"evidence[{index}].locator"), f"evidence[{index}].locator")
        _string(record["hash"], f"evidence[{index}].hash")
        if "strength" in record:
            _number(record["strength"], f"evidence[{index}].strength", bounded=True)
        if "classification" in record:
            _string(record["classification"], f"evidence[{index}].classification")
        _assert_unverified(record, f"evidence[{index}]")
    claim_ids: set[str] = set()
    for index, item in enumerate(_sequence(bundle["claims"], "claims")):
        record = _object(item, f"claims[{index}]")
        for key in ("claim_id", "text", "status", "confidence", "evidence_refs"):
            if key not in record:
                raise _fail(f"claims[{index}] is missing {key}")
        claim_id = _string(record["claim_id"], f"claims[{index}].claim_id", nonempty=True)
        if claim_id in claim_ids:
            raise _fail(f"duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        _string(record["text"], f"claims[{index}].text")
        if record["status"] not in _CLAIM_STATUSES:
            raise _fail(f"claims[{index}].status is unsupported")
        _number(record["confidence"], f"claims[{index}].confidence", bounded=True)
        _evidence_refs(record["evidence_refs"], f"claims[{index}].evidence_refs", evidence_ids)
        if "counter_evidence_refs" in record:
            _evidence_refs(record["counter_evidence_refs"], f"claims[{index}].counter_evidence_refs", evidence_ids)
        if "generator" in record:
            _json_clone(_object(record["generator"], f"claims[{index}].generator"), f"claims[{index}].generator")
        _assert_unverified(record, f"claims[{index}]")
    return _json_clone(bundle, "evidence_bundle")


def build_analysis_job_plan(
    scope: TrustedScope,
    stages: Sequence[str | Mapping[str, Any]],
    *,
    job_type: str,
    job_id: str | None = None,
    workflow_version: str | None = None,
) -> dict[str, Any]:
    """Build a queued analysis plan, never a durable lifecycle receipt."""

    tenant_id, project_id, revision = _scope(scope)
    normalised_stages: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, item in enumerate(_sequence(stages, "stages")):
        if isinstance(item, str):
            name = _string(item, f"stages[{index}]", nonempty=True)
            total_units = None
        else:
            record = _object(item, f"stages[{index}]")
            name = _string(record.get("name"), f"stages[{index}].name", nonempty=True)
            input_state = record.get("state")
            if input_state not in {None, "planned", "queued", "not_run", "NOT_RUN"}:
                raise _fail(f"stages[{index}].state would claim lifecycle progress")
            total_units = record.get("total_units")
            if total_units is not None:
                total_units = _integer(total_units, f"stages[{index}].total_units", minimum=0)
        if name in names:
            raise _fail(f"duplicate analysis stage: {name}")
        names.add(name)
        normalised_stages.append(
            {
                "name": name,
                "state": "queued",
                "attempt": 0,
                "checkpoint_id": None,
                "completed_units": 0,
                "total_units": total_units,
            }
        )
    job_type = _string(job_type, "job_type", nonempty=True)
    identity = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "revision_id": revision,
        "job_type": job_type,
        "workflow_version": workflow_version,
        "stages": normalised_stages,
    }
    plan: dict[str, Any] = {
        "job_id": (
            _string(job_id, "job_id", nonempty=True)
            if job_id is not None
            else "job:" + _stable_hash(identity)
        ),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "revision_id": revision,
        "job_type": job_type,
        "state": "queued",
        "stages": normalised_stages,
    }
    if workflow_version is not None:
        plan["workflow_version"] = _string(
            workflow_version, "workflow_version", nonempty=True
        )
    validate_analysis_job(plan, require_queued_plan=True)
    return plan


def validate_analysis_job(
    value: Any,
    *,
    require_queued_plan: bool = False,
) -> dict[str, Any]:
    job = _object(value, "analysis_job")
    required = {"job_id", "tenant_id", "project_id", "revision_id", "job_type", "state", "stages"}
    missing = sorted(required - set(job))
    if missing:
        raise _fail(f"analysis_job is missing fields: {', '.join(missing)}")
    for key in ("job_id", "tenant_id", "project_id", "revision_id", "job_type"):
        _string(job[key], key, nonempty=True)
    if job["state"] not in _JOB_STATES:
        raise _fail("analysis_job.state is unsupported")
    stage_names: set[str] = set()
    for index, item in enumerate(_sequence(job["stages"], "stages")):
        stage = _object(item, f"stages[{index}]")
        if "name" not in stage or "state" not in stage:
            raise _fail(f"stages[{index}] requires name and state")
        name = _string(stage["name"], f"stages[{index}].name", nonempty=True)
        if name in stage_names:
            raise _fail(f"duplicate analysis stage: {name}")
        stage_names.add(name)
        _string(stage["state"], f"stages[{index}].state")
        if "attempt" in stage:
            _integer(stage["attempt"], f"stages[{index}].attempt")
        if "checkpoint_id" in stage:
            _optional_string(stage["checkpoint_id"], f"stages[{index}].checkpoint_id")
        if "completed_units" in stage:
            _integer(stage["completed_units"], f"stages[{index}].completed_units")
        if "total_units" in stage and stage["total_units"] is not None:
            _integer(stage["total_units"], f"stages[{index}].total_units")
    for key in ("idempotency_key", "workflow_version"):
        if key in job:
            _string(job[key], key)
    if "estimate_ref" in job:
        _optional_string(job["estimate_ref"], "estimate_ref")
    for key in ("created_at", "updated_at"):
        if key in job:
            _date_time(job[key], key)
    if require_queued_plan:
        forbidden = {"idempotency_key", "estimate_ref", "created_at", "updated_at"} & set(job)
        if forbidden:
            raise _fail("queued plan cannot claim persisted lifecycle metadata")
        if job["state"] != "queued":
            raise _fail("queued plan state must be queued")
        for index, stage in enumerate(job["stages"]):
            if (
                stage.get("state") != "queued"
                or stage.get("attempt") != 0
                or stage.get("checkpoint_id") is not None
                or stage.get("completed_units") != 0
            ):
                raise _fail(f"stages[{index}] claims lifecycle progress")
    return _json_clone(job, "analysis_job")


def validate_conversion_mapping(value: Any) -> dict[str, Any]:
    """Validate ``conversion-mapping.schema.json`` plus identifier uniqueness."""

    mapping = _object(value, "conversion_mapping")
    _unexpected(mapping, _CONVERSION_KEYS, "conversion_mapping")
    required = {"mapping_id", "source_revision_id", "target_revision_id", "entries"}
    missing = sorted(required - set(mapping))
    if missing:
        raise _fail(f"conversion_mapping is missing fields: {', '.join(missing)}")
    for key in ("mapping_id", "source_revision_id", "target_revision_id"):
        _string(mapping[key], key, nonempty=True)
    if "semantic_ir_version" in mapping:
        _string(mapping["semantic_ir_version"], "semantic_ir_version")
    entry_ids: set[str] = set()
    for index, item in enumerate(_sequence(mapping["entries"], "entries")):
        entry = _object(item, f"entries[{index}]")
        required_entry = {"entry_id", "source_ref", "status", "confidence"}
        missing_entry = sorted(required_entry - set(entry))
        if missing_entry:
            raise _fail(f"entries[{index}] is missing fields: {', '.join(missing_entry)}")
        entry_id = _string(entry["entry_id"], f"entries[{index}].entry_id", nonempty=True)
        if entry_id in entry_ids:
            raise _fail(f"duplicate conversion entry_id: {entry_id}")
        entry_ids.add(entry_id)
        _string(entry["source_ref"], f"entries[{index}].source_ref", nonempty=True)
        for key in ("semantic_ir_ref", "target_ref"):
            if key in entry:
                _optional_string(entry[key], f"entries[{index}].{key}")
        for key in ("rule_ids", "repair_attempt_ids", "evidence_refs"):
            if key in entry:
                _unique_strings(entry[key], f"entries[{index}].{key}")
        if entry["status"] not in _MAPPING_STATUSES:
            raise _fail(f"entries[{index}].status is unsupported")
        _number(entry["confidence"], f"entries[{index}].confidence", bounded=True)
        _json_clone(entry, f"entries[{index}]")
    return _json_clone(mapping, "conversion_mapping")


def validate_trace_link(value: Any) -> dict[str, Any]:
    """Validate a trace link and require an ordered, offset-aware time window."""

    link = _object(value, "trace_link")
    _unexpected(link, _TRACE_KEYS, "trace_link")
    required = {"link_id", "project_id", "environment", "time_window", "span_ref", "target_refs", "confidence"}
    missing = sorted(required - set(link))
    if missing:
        raise _fail(f"trace_link is missing fields: {', '.join(missing)}")
    for key in ("link_id", "project_id", "environment", "span_ref"):
        _string(link[key], key, nonempty=True)
    if "revision_id" in link:
        _optional_string(link["revision_id"], "revision_id")
    window = _object(link["time_window"], "time_window")
    if "from" not in window or "to" not in window:
        raise _fail("time_window requires from and to")
    start = _date_time(window["from"], "time_window.from")
    end = _date_time(window["to"], "time_window.to")
    if _parsed_date_time(start) > _parsed_date_time(end):
        raise _fail("time_window.from must not be after time_window.to")
    targets = _unique_strings(link["target_refs"], "target_refs")
    if not targets:
        raise _fail("target_refs must contain at least one target")
    _number(link["confidence"], "confidence", bounded=True)
    if "sampling" in link:
        _json_clone(_object(link["sampling"], "sampling"), "sampling")
    if "method" in link:
        _string(link["method"], "method")
    return _json_clone(link, "trace_link")


def build_skill_output(
    *,
    skill: str,
    revision: str,
    known_limitations: Sequence[str],
    test_commands: Sequence[str] = (),
    changed_files: Sequence[str] = (),
    status: str = "partial",
    resume_checkpoint: str | None = None,
) -> dict[str, Any]:
    """Build an honest source ``skill-output`` local-planning projection."""

    skill = _string(skill, "skill", nonempty=True)
    if not skill.startswith("elmos-"):
        raise _fail("skill must start with elmos-")
    revision = _string(revision, "revision", nonempty=True)
    if status not in {"partial", "failed", "blocked"}:
        raise _fail("a local not-run projection cannot have completed status")
    limitations = _unique_strings(known_limitations, "known_limitations")
    if not limitations:
        raise _fail("known_limitations must explicitly describe remaining work")
    commands = _unique_strings(test_commands, "test_commands")
    files = sorted(
        _relative_path(item, f"changed_files[{index}]")
        for index, item in enumerate(_sequence(changed_files, "changed_files"))
    )
    if len(files) != len(set(files)):
        raise _fail("changed_files cannot contain duplicates")
    output: dict[str, Any] = {
        "skill": skill,
        "status": status,
        "revision": revision,
        "completed_tasks": [],
        "changed_files": files,
        "tests": [
            {"command": command, "result": "not_run", "output_ref": None}
            for command in commands
        ],
        "evidence": [],
        "known_limitations": limitations,
    }
    if resume_checkpoint is not None:
        output["resume_checkpoint"] = _string(
            resume_checkpoint, "resume_checkpoint", nonempty=True
        )
    validate_skill_output(output, require_safe_projection=True)
    return output


def validate_skill_output(
    value: Any,
    *,
    require_safe_projection: bool = False,
) -> dict[str, Any]:
    output = _object(value, "skill_output")
    required = {"skill", "status", "revision", "completed_tasks", "tests", "evidence", "known_limitations"}
    missing = sorted(required - set(output))
    if missing:
        raise _fail(f"skill_output is missing fields: {', '.join(missing)}")
    skill = _string(output["skill"], "skill", nonempty=True)
    if not skill.startswith("elmos-"):
        raise _fail("skill must start with elmos-")
    if output["status"] not in _SKILL_STATUSES:
        raise _fail("skill_output.status is unsupported")
    _string(output["revision"], "revision")
    completed = _unique_strings(output["completed_tasks"], "completed_tasks")
    if "changed_files" in output:
        _unique_strings(output["changed_files"], "changed_files")
    test_results: list[str] = []
    for index, item in enumerate(_sequence(output["tests"], "tests")):
        test = _object(item, f"tests[{index}]")
        if "command" not in test or "result" not in test:
            raise _fail(f"tests[{index}] requires command and result")
        _string(test["command"], f"tests[{index}].command")
        if test["result"] not in _TEST_RESULTS:
            raise _fail(f"tests[{index}].result is unsupported")
        test_results.append(test["result"])
        if "output_ref" in test:
            _optional_string(test["output_ref"], f"tests[{index}].output_ref")
    evidence = _unique_strings(output["evidence"], "evidence")
    limitations = _unique_strings(output["known_limitations"], "known_limitations")
    if "resume_checkpoint" in output:
        _optional_string(output["resume_checkpoint"], "resume_checkpoint")
    for key in ("system_wall_clock_eta", "human_review_effort"):
        if key in output and output[key] is not None:
            _json_clone(_object(output[key], key), key)
    if require_safe_projection:
        if output["status"] == "completed":
            raise _fail("safe projection cannot claim completed status")
        if completed:
            raise _fail("safe projection cannot claim completed tasks")
        if any(result != "not_run" for result in test_results):
            raise _fail("safe projection tests must remain not_run")
        if evidence:
            raise _fail("safe projection cannot manufacture evidence")
        if not limitations:
            raise _fail("safe projection must state known limitations")
    return _json_clone(output, "skill_output")


__all__ = [
    "SchemaProjectionError",
    "TrustedScope",
    "build_analysis_job_plan",
    "build_evidence_bundle",
    "build_graph_snapshot",
    "build_project_manifest",
    "build_skill_output",
    "validate_analysis_job",
    "validate_conversion_mapping",
    "validate_evidence_bundle",
    "validate_graph_snapshot",
    "validate_project_manifest",
    "validate_skill_output",
    "validate_trace_link",
]
