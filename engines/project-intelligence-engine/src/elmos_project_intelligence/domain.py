"""Deterministic bounded operations for the fifty Project Intelligence Skills.

These operations consume only caller-supplied, already-authorized local data.
They never execute repository code, invoke a provider, mutate Git, start a
debug adapter, deploy infrastructure, or claim certification.  Each function
implements a distinct local analysis, artifact, policy, or planning contract;
shared helpers only normalize immutable inputs.
"""

from __future__ import annotations

import base64
import binascii
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import math
from pathlib import PurePosixPath
import re
from typing import Any

from .canonical import canonical_digest, canonical_json_bytes, validate_digest
from .flowgraph import function_control_flow
from .java_structure import is_java_path, java_structure
from .python_structure import (
    ORIGIN_PARSED,
    ORIGIN_REGEX,
    is_python_path,
    module_structure,
)


JsonObject = Mapping[str, Any]

CACHE_KEY_SCHEMA_VERSION = "elmos.project-intelligence.analysis-cache-key.v1"
CACHE_IMPLEMENTATION_VERSION = "elmos-project-intelligence-engine/1.1.0"


@dataclass(frozen=True, slots=True)
class TrustedRuntimeScope:
    """Authenticated request scope passed by the dispatcher, never caller inputs."""

    tenant_id: str
    project_id: str
    revision: str

    def __post_init__(self) -> None:
        for field_name in ("tenant_id", "project_id", "revision"):
            _identifier(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class CapabilityOutcome:
    state: str
    code: str
    outputs: Mapping[str, Any]
    unavailable: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    external_effects_performed: bool = False
    external_evidence: str = "NOT_RUN"
    certification: str = "NOT_CERTIFIED"

    def __post_init__(self) -> None:
        if self.state not in {
            "LOCAL_EXECUTED",
            "PARTIAL_LOCAL_EXECUTED",
            "PLANNING_ONLY",
            "BLOCKED",
        }:
            raise ValueError(f"unsupported capability state: {self.state}")
        if self.external_effects_performed:
            raise ValueError(
                "bounded Project Intelligence handlers cannot perform external effects"
            )
        if self.external_evidence != "NOT_RUN" or self.certification != "NOT_CERTIFIED":
            raise ValueError(
                "local handlers cannot manufacture external evidence or certification"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "code": self.code,
            "outputs": dict(self.outputs),
            "unavailable": list(self.unavailable),
            "warnings": list(self.warnings),
            "external_effects_performed": False,
            "external_evidence": self.external_evidence,
            "certification": self.certification,
        }


def _outcome(
    state: str,
    code: str,
    outputs: Mapping[str, Any],
    *,
    unavailable: Sequence[str] = (),
    warnings: Sequence[str] = (),
) -> CapabilityOutcome:
    return CapabilityOutcome(
        state=state,
        code=code,
        outputs=outputs,
        unavailable=tuple(unavailable),
        warnings=tuple(warnings),
    )


def _identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(
            f"{field_name} must be a non-empty string of at most 256 characters"
        )
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{field_name} contains a control character")
    return value


def _safe_path(value: Any) -> str:
    path = _identifier(value, "path")
    if "\\" in path:
        raise ValueError("paths must use POSIX separators")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError(f"unsafe repository-relative path: {path}")
    return parsed.as_posix()


_MERMAID_LABEL_MAX_CHARACTERS = 160
_MERMAID_LABEL_PUNCTUATION = frozenset(" _-.,()")

#: Mermaid delimiters per node kind.  The opening token always ends with a
#: double quote and the closing token always begins with one, so every label
#: sits inside a quoted string.  ``_safe_mermaid_label`` strips the quote
#: character itself, which is what makes the shape impossible to escape --
#: adding a shape here therefore cannot widen the injection surface.
_MERMAID_SHAPE_BY_KIND: dict[str, tuple[str, str]] = {
    "start": ('(["', '"])'),
    "end": ('(["', '"])'),
    "decision": ('{"', '"}'),
    "loop": ('[["', '"]]'),
    "merge": ('(("', '"))'),
}

#: Every other kind, including every component-diagram kind, keeps the plain
#: rectangle the renderer has always drawn.
_MERMAID_DEFAULT_SHAPE: tuple[str, str] = ('["', '"]')
_MARKDOWN_TEXT_MAX_CHARACTERS = 160
_MARKDOWN_TEXT_PUNCTUATION = frozenset(" _-.,():@")

_CONNECTOR_READ_SCOPE_ALLOWLIST = frozenset(
    {
        "read:artifacts",
        "read:ci",
        "read:docs",
        "read:evidence",
        "read:issues",
        "read:observability",
        "read:project",
        "read:repository",
    }
)
_DEBUG_CAPABILITY_ALLOWLIST = frozenset(
    {
        "breakpoints",
        "conditional_breakpoints",
        "console",
        "disassembly_optional",
        "exception_breakpoints",
        "goroutines",
        "hot_reload_optional",
        "isolate_threads",
        "line_breakpoints",
        "logpoints",
        "memory_optional",
        "network_timeline",
        "page_target",
        "scopes",
        "source_maps",
        "stack",
        "step",
        "threads",
        "variables",
    }
)

_DEBUG_MAX_EVENTS = 1_000
_DEBUG_MAX_DEPTH = 8
_DEBUG_MAX_MAPPING_FIELDS = 128
_DEBUG_MAX_SEQUENCE_ITEMS = 256
_DEBUG_MAX_STRING_CHARACTERS = 4_096
_DEBUG_SENSITIVE_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "authorization",
    "apikey",
    "privatekey",
    "accesskey",
    "rawmemory",
    "cookie",
    "authoriz",
    "approv",
    "certif",
)
_DEBUG_INLINE_SECRET_KEYS = (
    "access[_-]?key",
    "access[_-]?token",
    "api[_-]?key",
    "auth[_-]?token",
    "client[_-]?secret",
    "cookie",
    "credential",
    "password",
    "passwd",
    "private[_-]?key",
    "pwd",
    "secret",
    "set-cookie",
    "token",
    "x-api-key",
)
_DEBUG_AUTHORIZATION_HEADER = re.compile(
    r"(?i)(\bauthorization\s*[:=]\s*)(?:(?:basic|bearer|digest)\s+)?"
    r"[^\s,;\r\n]+"
)
_DEBUG_INLINE_SECRET = re.compile(
    r"(?i)\b(" + "|".join(_DEBUG_INLINE_SECRET_KEYS) + r")\b"
    r"(\s*[:=]\s*)"
    r"(?:[\"'][^\"'\r\n]+[\"']|[^\s,;&}\]\r\n]+)"
)
_DEBUG_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{1,4096}")
_DEBUG_URI_USERINFO = re.compile(
    r"(?i)(\b(?:[a-z][a-z0-9+.-]*:)?//)[^\s/:@]+:[^\s/@]+@"
)
_DEBUG_EVENT_STRUCTURAL_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "kind",
        "occurred_at",
        "timestamp",
        "tenant_id",
        "project_id",
        "revision_id",
        "debug_session_id",
        "sequence",
        "traceparent",
        "redaction_profile",
        "payload",
    }
)


def _safe_mermaid_label(value: Any) -> tuple[str, bool]:
    """Return a bounded label that cannot escape a quoted Mermaid node.

    Mermaid flowcharts accept directives, links, and HTML-like content.  The
    renderer therefore uses a deliberately small character allowlist instead
    of trying to escape an evolving grammar.  Whitespace is collapsed so line
    separators cannot create a second statement.
    """

    original = str(value)
    allowed = "".join(
        character
        if character.isalnum() or character in _MERMAID_LABEL_PUNCTUATION
        else " "
        for character in original
    )
    collapsed = " ".join(allowed.split())
    bounded = collapsed[:_MERMAID_LABEL_MAX_CHARACTERS].rstrip() or "node"
    return bounded, bounded != original


def _safe_markdown_text(value: Any) -> tuple[str, bool]:
    """Return bounded plain text that cannot introduce Markdown structure."""

    original = str(value)
    allowed = "".join(
        character
        if character.isalnum() or character in _MARKDOWN_TEXT_PUNCTUATION
        else " "
        for character in original
    )
    collapsed = " ".join(allowed.split())
    bounded = collapsed[:_MARKDOWN_TEXT_MAX_CHARACTERS].rstrip() or "unknown"
    return bounded, bounded != original


def _canonical_allowlisted_values(
    value: Any,
    *,
    field_name: str,
    allowlist: frozenset[str],
) -> tuple[list[str], list[str]]:
    accepted: set[str] = set()
    rejected: set[str] = set()
    for item in _sequence(value, field_name):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} must contain non-empty strings")
        canonical = item.strip().lower()
        if item != canonical or canonical not in allowlist:
            rejected.add(item)
            continue
        accepted.add(canonical)
    return sorted(accepted), sorted(rejected)


def _debug_key_is_sensitive(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(marker in normalized for marker in _DEBUG_SENSITIVE_KEY_MARKERS)


def _sanitize_debug_value(
    value: Any,
    *,
    depth: int,
    stats: Counter[str],
) -> Any:
    if depth > _DEBUG_MAX_DEPTH:
        raise ValueError("debug event nesting exceeds the configured limit")
    if isinstance(value, Mapping):
        if len(value) > _DEBUG_MAX_MAPPING_FIELDS:
            raise ValueError("debug event mapping exceeds the configured field limit")
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("debug event mapping keys must be strings")
            if _debug_key_is_sensitive(key):
                stats["sensitive_fields_omitted"] += 1
                continue
            sanitized[key] = _sanitize_debug_value(
                item,
                depth=depth + 1,
                stats=stats,
            )
        return sanitized
    if isinstance(value, list):
        if len(value) > _DEBUG_MAX_SEQUENCE_ITEMS:
            raise ValueError("debug event sequence exceeds the configured item limit")
        return [
            _sanitize_debug_value(item, depth=depth + 1, stats=stats) for item in value
        ]
    if isinstance(value, str):
        sanitized_text = value
        if len(sanitized_text) > _DEBUG_MAX_STRING_CHARACTERS:
            sanitized_text = sanitized_text[:_DEBUG_MAX_STRING_CHARACTERS]
            stats["strings_truncated"] += 1
        redacted_text = _DEBUG_URI_USERINFO.sub(r"\1[REDACTED]@", sanitized_text)
        redacted_text = _DEBUG_AUTHORIZATION_HEADER.sub(r"\1[REDACTED]", redacted_text)
        redacted_text = _DEBUG_INLINE_SECRET.sub(r"\1\2[REDACTED]", redacted_text)
        redacted_text = _DEBUG_BEARER_TOKEN.sub("Bearer [REDACTED]", redacted_text)
        if redacted_text != sanitized_text:
            stats["inline_secret_values_redacted"] += 1
        return redacted_text
    if value is None or isinstance(value, (bool, int)):
        return value
    raise ValueError(f"unsupported debug event value: {type(value).__name__}")


def _sanitized_debug_events(
    inputs: JsonObject,
    *,
    runtime_scope: TrustedRuntimeScope,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    events = _records(inputs, "debug_events")
    if len(events) > _DEBUG_MAX_EVENTS:
        raise ValueError("debug event count exceeds the configured hard limit")
    stats: Counter[str] = Counter()
    debug_session_id = _debug_session_id(inputs, runtime_scope)
    sanitized: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    sequences: set[int] = set()
    for index, event in enumerate(events):
        event_id = _identifier(event.get("event_id"), f"debug_events[{index}].event_id")
        if event_id in event_ids:
            raise ValueError(f"duplicate debug event id: {event_id}")
        event_ids.add(event_id)
        sequence = event.get("sequence")
        if type(sequence) is not int or sequence <= 0:
            raise ValueError("debug event sequence must be a positive integer")
        if sequence in sequences:
            raise ValueError(f"duplicate debug event sequence: {sequence}")
        sequences.add(sequence)

        event_type_value = event.get("event_type", event.get("kind"))
        if (
            "event_type" in event
            and "kind" in event
            and event["event_type"] != event["kind"]
        ):
            raise ValueError("debug event_type and legacy kind disagree")
        event_type = _identifier(
            event_type_value, f"debug_events[{index}].event_type"
        )
        occurred_at_value = event.get("occurred_at", event.get("timestamp"))
        if (
            "occurred_at" in event
            and "timestamp" in event
            and event["occurred_at"] != event["timestamp"]
        ):
            raise ValueError("debug occurred_at and legacy timestamp disagree")
        occurred_at = _validated_rfc3339(
            occurred_at_value, f"debug_events[{index}].occurred_at"
        )
        for field_name, expected in (
            ("tenant_id", runtime_scope.tenant_id),
            ("project_id", runtime_scope.project_id),
            ("revision_id", runtime_scope.revision),
            ("debug_session_id", debug_session_id),
        ):
            if field_name in event and event[field_name] != expected:
                raise ValueError(
                    f"debug_events[{index}].{field_name} does not match trusted scope"
                )
        if event.get("redaction_profile", "recursive-field-policy-v2") != (
            "recursive-field-policy-v2"
        ):
            raise ValueError("debug event redaction_profile is not supported")

        raw_payload = event.get("payload", {})
        if not isinstance(raw_payload, Mapping):
            raise ValueError(f"debug_events[{index}].payload must be an object")
        payload = dict(raw_payload)
        for key, value in event.items():
            if key in _DEBUG_EVENT_STRUCTURAL_FIELDS:
                continue
            if key in payload:
                raise ValueError(
                    f"debug_events[{index}] duplicates payload field {key}"
                )
            payload[key] = value
        clean_payload = _sanitize_debug_value(payload, depth=0, stats=stats)
        if not isinstance(clean_payload, dict):
            raise ValueError("sanitized debug event payload must remain an object")
        normalized: dict[str, Any] = {
            "event_id": event_id,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "tenant_id": runtime_scope.tenant_id,
            "project_id": runtime_scope.project_id,
            "revision_id": runtime_scope.revision,
            "debug_session_id": debug_session_id,
            "sequence": sequence,
            "redaction_profile": "recursive-field-policy-v2",
            "payload": clean_payload,
        }
        traceparent = event.get("traceparent")
        if traceparent is not None:
            normalized["traceparent"] = _identifier(
                traceparent, f"debug_events[{index}].traceparent"
            )
        sanitized.append(normalized)
    return sorted(sanitized, key=lambda item: int(item["sequence"])), stats


def _debug_sanitization_warnings(stats: Counter[str]) -> tuple[str, ...]:
    warnings: list[str] = []
    if stats["sensitive_fields_omitted"] or stats["inline_secret_values_redacted"]:
        warnings.append("debug-data-redacted-by-field-policy")
    if stats["nonessential_fields_omitted"]:
        warnings.append("nonessential-debug-fields-omitted")
    if stats["strings_truncated"]:
        warnings.append("debug-strings-truncated")
    return tuple(warnings)


def _sequence(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return list(value)


def _records(inputs: JsonObject, key: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, value in enumerate(_sequence(inputs.get(key), key)):
        if not isinstance(value, Mapping):
            raise ValueError(f"{key}[{index}] must be an object")
        records.append(dict(value))
    return records


def _files(inputs: JsonObject) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(_records(inputs, "files")):
        path = _safe_path(record.get("path"))
        if path in seen:
            raise ValueError(f"duplicate file path: {path}")
        seen.add(path)
        text = record.get("text", "")
        if not isinstance(text, str):
            raise ValueError(f"files[{index}].text must be a string")
        raw = text.encode("utf-8")
        supplied = record.get("sha256")
        observed = hashlib.sha256(raw).hexdigest()
        if supplied is not None and supplied not in {observed, f"sha256:{observed}"}:
            raise ValueError(f"files[{index}] content digest mismatch")
        files.append(
            {
                "path": path,
                "text": text,
                "bytes": len(raw),
                "sha256": f"sha256:{observed}",
            }
        )
    return sorted(files, key=lambda item: item["path"])


def _extension(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    if name in {"dockerfile", "makefile", "jenkinsfile"}:
        return name
    return PurePosixPath(path).suffix.lower()


LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "CSharp",
    ".c": "C",
    ".h": "C",
    ".cc": "CPlusPlus",
    ".cpp": "CPlusPlus",
    ".hpp": "CPlusPlus",
    ".php": "PHP",
    ".rb": "Ruby",
    ".sql": "SQL",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".md": "Markdown",
    "dockerfile": "Dockerfile",
    "makefile": "Make",
}


def _language(path: str) -> str:
    return LANGUAGE_BY_EXTENSION.get(_extension(path), "Unknown")


def _symbol_node(
    file: Mapping[str, Any],
    *,
    kind: str,
    name: str,
    line: int,
    origin: str,
    qualified_name: str | None = None,
) -> dict[str, Any]:
    """Build one declaration node.

    The identity recipe is shared by both extraction paths on purpose: the
    same declaration keeps the same id whether a parser or the regex scan
    found it, so switching a file between the two does not churn the graph.
    """

    node = {
        "id": canonical_digest(
            {"path": file["path"], "kind": kind, "name": name, "line": line}
        ),
        "path": file["path"],
        "line": line,
        "kind": kind,
        "name": name,
        "language": _language(str(file["path"])),
        "origin": origin,
    }
    if qualified_name is not None:
        node["qualified_name"] = qualified_name
    return node


def _regex_symbols(file: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Scan one file's lines for declarations.

    This is the original heuristic and stays the path for every language that
    has no parser here.  It reads one physical line at a time, so it cannot
    see nesting, cannot tell a declaration from the same words inside a
    string, and stops at the first pattern that matches a line.  Facts it
    produces are marked ``REGEX`` for exactly that reason.
    """

    patterns = (
        ("class", re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)")),
        (
            "function",
            re.compile(r"^\s*(?:export\s+)?(?:async\s+)?def\s+([A-Za-z_]\w*)"),
        ),
        (
            "function",
            re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"),
        ),
        (
            "function",
            re.compile(
                r"^\s*(?:public|private|protected|static|final|suspend|async|virtual|override|inline|extern|const|\s)*\s*(?:fun|func)\s+([A-Za-z_]\w*)"
            ),
        ),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)")),
    )
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(str(file["text"]).splitlines(), 1):
        for kind, pattern in patterns:
            match = pattern.search(line)
            if match:
                values.append(
                    _symbol_node(
                        file,
                        kind=kind,
                        name=match.group(1),
                        line=line_number,
                        origin=ORIGIN_REGEX,
                    )
                )
                break
    return values


def _parsed_file_structure(file: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the parsed structure of a Python or Java file, or ``None``.

    ``None`` means either unsupported language or syntax that does not parse.
    Both send the caller to the regex fallback, and both are recorded, so a
    reader is never left guessing which scan produced a given fact.
    """

    path = str(file["path"])
    if is_python_path(path):
        return module_structure(str(file["text"]), path)
    if is_java_path(path):
        return java_structure(str(file["text"]), path)
    return None


def _symbols(files: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return declaration nodes, preferring a real parser over the regex scan."""

    values: list[dict[str, Any]] = []
    for file in files:
        structure = _parsed_file_structure(file)
        if structure is None:
            values.extend(_regex_symbols(file))
            continue
        for symbol in structure["symbols"]:
            values.append(
                _symbol_node(
                    file,
                    kind=str(symbol["kind"]),
                    name=str(symbol["name"]),
                    line=int(symbol["line"]),
                    origin=ORIGIN_PARSED,
                    qualified_name=str(symbol["qualified_name"]),
                )
            )
    return values


def _regex_imports(file: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Scan one file's lines for imports; the fallback for every unparsed file."""

    patterns = (
        re.compile(r"^\s*from\s+([\w.]+)\s+import\s+"),
        re.compile(r"^\s*import\s+([\w.]+)"),
        re.compile(r"(?:import|require)\s*\(?[\"']([^\"']+)[\"']"),
        re.compile(r"^\s*use\s+([\w:]+)"),
    )
    edges: list[dict[str, Any]] = []
    for line_number, line in enumerate(str(file["text"]).splitlines(), 1):
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                edges.append(
                    {
                        "from": file["path"],
                        "to": match.group(1),
                        "kind": "imports",
                        "line": line_number,
                        "origin": ORIGIN_REGEX,
                    }
                )
                break
    return edges


def _imports(files: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return import edges, preferring a real parser over the regex scan.

    The parser path also reports relative imports and Java static imports, which
    the regex never matched, and never mistakes the word ``import`` inside a
    string or comment for a real one.
    """

    edges: list[dict[str, Any]] = []
    for file in files:
        structure = _parsed_file_structure(file)
        if structure is None:
            edges.extend(_regex_imports(file))
            continue
        for imported in structure["imports"]:
            edges.append(
                {
                    "from": file["path"],
                    "to": str(imported["to"]),
                    "kind": "imports",
                    "line": int(imported["line"]),
                    "origin": ORIGIN_PARSED,
                }
            )
    return edges


def _file_nodes(files: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": canonical_digest({"path": file["path"], "sha256": file["sha256"]}),
            "kind": "file",
            "name": file["path"],
            "path": file["path"],
            "language": _language(str(file["path"])),
            "evidence": file["sha256"],
        }
        for file in files
    ]


def _top_words(text: str, limit: int = 12) -> list[str]:
    ignored = {
        "this",
        "that",
        "with",
        "from",
        "into",
        "return",
        "class",
        "function",
        "import",
        "const",
        "public",
        "private",
        "true",
        "false",
        "none",
        "null",
    }
    counts = Counter(
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
        if token.lower() not in ignored
    )
    return [word for word, _ in counts.most_common(limit)]


def _edge_endpoints(edge: Mapping[str, Any]) -> tuple[Any, Any]:
    """Return one edge's ``(source, target)`` in whichever vocabulary it uses.

    Two spellings reach these handlers and both are legitimate.  ``_graph``
    builds import edges as ``from``/``to``; a caller that has already compiled
    a Diagram Spec passes the canonical ``source``/``target``, which
    ``compile_diagram_spec`` has accepted from the start.

    Every handler that reads an edge must go through this function.  Three of
    them used to read ``from``/``to`` directly and each failed differently on
    canonical edges: two printed ``None``, and ``analyze_impact`` returned a
    correctly shaped answer that was simply wrong -- it reported nothing
    downstream of a changed file because it had matched no edges at all.  A
    single reader is what stops that from being reintroduced one handler at a
    time.

    Preference order matches ``compile_diagram_spec``: canonical keys win, and
    an edge that mixes the two is not something this function has to decide
    about because the compiler already rejects it.
    """

    if "source" in edge or "target" in edge:
        return edge.get("source"), edge.get("target")
    return edge.get("from"), edge.get("to")


def _graph(inputs: JsonObject) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = _records(inputs, "nodes")
    edges = _records(inputs, "edges")
    if not nodes:
        files = _files(inputs)
        nodes = _file_nodes(files) + _symbols(files)
    if not edges:
        edges = _imports(_files(inputs))
    return nodes, edges


def _redacted_secret_findings(
    files: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    patterns = {
        "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "token-assignment": re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*[\"']?([^\s\"']{8,})"
        ),
    }
    findings: list[dict[str, Any]] = []
    for file in files:
        for kind, pattern in patterns.items():
            for match in pattern.finditer(str(file["text"])):
                material = match.group(0).encode("utf-8")
                findings.append(
                    {
                        "path": file["path"],
                        "kind": kind,
                        "fingerprint": "sha256:" + hashlib.sha256(material).hexdigest(),
                    }
                )
    return findings


def orchestrate_analysis(inputs: JsonObject) -> CapabilityOutcome:
    requested = [
        str(item)
        for item in _sequence(inputs.get("requested_skills"), "requested_skills")
    ]
    dependencies = _records(inputs, "dependency_edges")
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree: Counter[str] = Counter()
    nodes = set(requested)
    for edge in dependencies:
        parent = _identifier(edge.get("dependency"), "dependency")
        child = _identifier(edge.get("skill"), "skill")
        adjacency[parent].append(child)
        indegree[child] += 1
        nodes.update((parent, child))
    queue = deque(sorted(node for node in nodes if indegree[node] == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for child in sorted(adjacency[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(nodes):
        return _outcome(
            "BLOCKED",
            "DEPENDENCY_CYCLE_REJECTED",
            {
                "execution_order": [],
                "requested_skills": requested,
                "automatic_effects": False,
            },
        )
    return _outcome(
        "LOCAL_EXECUTED",
        "ANALYSIS_PLAN_COMPILED",
        {
            "execution_order": order,
            "requested_skills": requested,
            "automatic_effects": False,
        },
    )


def baseline_product_scope(inputs: JsonObject) -> CapabilityOutcome:
    requirements = _records(inputs, "requirements")
    files = _files(inputs)
    capabilities = sorted(
        {word for file in files for word in _top_words(str(file["text"]), 8)}
    )[:24]
    unknown = [item for item in requirements if not item.get("evidence_refs")]
    return _outcome(
        "LOCAL_EXECUTED",
        "PRODUCT_SCOPE_BASELINED",
        {
            "requirement_count": len(requirements),
            "candidate_capabilities": capabilities,
            "unconfirmed_requirement_ids": [item.get("id") for item in unknown],
            "scope_digest": canonical_digest(
                {"requirements": requirements, "capabilities": capabilities}
            ),
        },
    )


def compile_reference_architecture(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    roots = Counter(PurePosixPath(str(file["path"])).parts[0] for file in files)
    components = [
        {"name": name, "file_count": count, "confidence": "INFERRED"}
        for name, count in sorted(roots.items())
    ]
    return _outcome(
        "LOCAL_EXECUTED",
        "REFERENCE_ARCHITECTURE_COMPILED",
        {
            "components": components,
            "boundaries": _imports(files),
            "deployment_verified": False,
        },
    )


def freeze_revision(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    revision = _identifier(inputs.get("revision", "local-content"), "revision")
    manifest = [
        {"path": file["path"], "sha256": file["sha256"], "bytes": file["bytes"]}
        for file in files
    ]
    digest = canonical_digest({"revision": revision, "files": manifest})
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "LOCAL_REVISION_FROZEN",
        {
            "revision": revision,
            "manifest": manifest,
            "manifest_digest": digest,
            "code_executed": False,
        },
        unavailable=(
            "remote-git-provider",
            "git-lfs-hydration",
            "submodule-authorization",
        ),
    )


def fingerprint_revision(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    language_counts = Counter(_language(str(file["path"])) for file in files)
    build_markers = sorted(
        file["path"]
        for file in files
        if PurePosixPath(str(file["path"])).name.lower()
        in {
            "pyproject.toml",
            "package.json",
            "pom.xml",
            "build.gradle",
            "cargo.toml",
            "go.mod",
            "dockerfile",
            "makefile",
        }
    )
    return _outcome(
        "LOCAL_EXECUTED",
        "REVISION_FINGERPRINTED",
        {
            "languages": dict(sorted(language_counts.items())),
            "build_markers": build_markers,
            "fingerprint_digest": canonical_digest(
                {"languages": language_counts, "markers": build_markers}
            ),
        },
    )


def parse_revision(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    symbols = _symbols(files)
    parseable = [file for file in files if _language(str(file["path"])) != "Unknown"]
    unsupported = sorted(file["path"] for file in files if file not in parseable)
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "BOUNDED_CODE_IR_PARSED",
        {
            "symbols": symbols,
            "imports": _imports(files),
            "parsed_file_count": len(parseable),
            "unsupported_paths": unsupported,
        },
        unavailable=("native-language-parser-adapters",),
    )


def build_symbol_graph(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    symbols = _symbols(files)
    nodes = _file_nodes(files) + symbols
    edges = _imports(files)
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "SYMBOL_GRAPH_BUILT",
        {
            "nodes": nodes,
            "edges": edges,
            "graph_digest": canonical_digest({"nodes": nodes, "edges": edges}),
        },
        unavailable=("compiler-semantic-models", "cross-language-resolution"),
    )


def build_intelligence_graph(inputs: JsonObject) -> CapabilityOutcome:
    nodes, edges = _graph(inputs)
    claims = _records(inputs, "claims")
    graph = {"nodes": nodes, "edges": edges, "claims": claims}
    return _outcome(
        "LOCAL_EXECUTED",
        "INTELLIGENCE_GRAPH_SNAPSHOT_BUILT",
        {**graph, "graph_digest": canonical_digest(graph)},
    )


def bind_claim_evidence(inputs: JsonObject) -> CapabilityOutcome:
    claims = _records(inputs, "claims")
    evidence = {str(item.get("id")): item for item in _records(inputs, "evidence")}
    bound: list[dict[str, Any]] = []
    for claim in claims:
        refs = [
            str(item) for item in _sequence(claim.get("evidence_refs"), "evidence_refs")
        ]
        existing = [reference for reference in refs if reference in evidence]
        bound.append(
            {
                "claim_id": claim.get("id"),
                "evidence_refs": existing,
                "confidence": "REFERENCED_UNVERIFIED" if existing else "UNKNOWN",
                "verification_state": "NOT_RUN",
            }
        )
    return _outcome(
        "LOCAL_EXECUTED",
        "CLAIMS_BOUND_TO_EVIDENCE",
        {
            "bindings": bound,
            "unbound_claim_count": sum(not item["evidence_refs"] for item in bound),
        },
        warnings=("caller-supplied-evidence-references-unverified",)
        if any(item["evidence_refs"] for item in bound)
        else (),
    )


def read_revision_slice(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    requested = inputs.get("path")
    selected = (
        files
        if requested is None
        else [file for file in files if file["path"] == _safe_path(requested)]
    )
    max_lines = int(inputs.get("max_lines", 200))
    if max_lines < 1 or max_lines > 2_000:
        raise ValueError("max_lines must be between 1 and 2000")
    slices = [
        {
            "path": file["path"],
            "lines": str(file["text"]).splitlines()[:max_lines],
            "sha256": file["sha256"],
        }
        for file in selected[:20]
    ]
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "CODE_READER_SLICE_READY",
        {"files": slices, "truncated": len(selected) > 20},
        unavailable=("browser-workbench",),
    )


def navigate_graph(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    symbols = _records(inputs, "symbols") or _symbols(files)
    query = _identifier(inputs.get("symbol", "main"), "symbol")
    definitions = [item for item in symbols if item.get("name") == query]
    references = []
    pattern = re.compile(rf"\b{re.escape(query)}\b")
    for file in files:
        for line, value in enumerate(str(file["text"]).splitlines(), 1):
            if pattern.search(value):
                references.append({"path": file["path"], "line": line})
    return _outcome(
        "LOCAL_EXECUTED",
        "SEMANTIC_NAVIGATION_RESOLVED"
        if definitions
        else "SEMANTIC_NAVIGATION_ABSTAINED",
        {
            "symbol": query,
            "definitions": definitions,
            "references": references,
            "confidence": "INFERRED" if definitions else "UNKNOWN",
        },
        warnings=("static-or-caller-supplied-symbols-unverified",)
        if definitions
        else (),
    )


def explain_from_evidence(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    target = _safe_path(inputs.get("path", files[0]["path"] if files else "unknown"))
    selected = next((file for file in files if file["path"] == target), None)
    if selected is None:
        return _outcome(
            "BLOCKED",
            "EXPLANATION_TARGET_NOT_FOUND",
            {
                "facts": {"path": target, "found": False},
                "narrative_model_used": False,
                "evidence_refs": [],
            },
            unavailable=("model-narrative-adapter",),
        )
    facts = {
        "path": target,
        "language": _language(target),
        "bytes": selected["bytes"],
        "symbols": [item for item in _symbols([selected])],
        "imports": [item for item in _imports([selected])],
        "keywords": _top_words(str(selected["text"])),
    }
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "EVIDENCE_FACT_SHEET_GENERATED",
        {
            "facts": facts,
            "narrative_model_used": False,
            "evidence_refs": [selected["sha256"]],
        },
        unavailable=("model-narrative-adapter",),
    )


def compile_onboarding_path(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    scored = sorted(
        files,
        key=lambda file: (
            0
            if PurePosixPath(str(file["path"])).name.lower().startswith("readme")
            else 1,
            0
            if any(
                token in str(file["path"]).lower() for token in ("main", "app", "index")
            )
            else 1,
            file["path"],
        ),
    )
    steps = [
        {
            "order": index,
            "path": file["path"],
            "reason": "evidence-backed repository entry",
        }
        for index, file in enumerate(scored[:12], 1)
    ]
    return _outcome("LOCAL_EXECUTED", "ONBOARDING_PATH_COMPILED", {"steps": steps})


def discover_architecture(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    components: dict[str, list[str]] = defaultdict(list)
    for file in files:
        parts = PurePosixPath(str(file["path"])).parts
        components[parts[0]].append(str(file["path"]))
    result = [
        {"component": name, "paths": sorted(paths), "confidence": "INFERRED"}
        for name, paths in sorted(components.items())
    ]
    return _outcome(
        "LOCAL_EXECUTED",
        "STATIC_ARCHITECTURE_DISCOVERED",
        {"components": result, "runtime_verified": False},
    )


def map_capabilities(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    candidates: list[dict[str, Any]] = []
    for file in files:
        for word in _top_words(str(file["text"]), 5):
            candidates.append(
                {"name": word, "source_path": file["path"], "confidence": "INFERRED"}
            )
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        unique.setdefault(str(candidate["name"]), candidate)
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "CAPABILITY_CANDIDATES_MAPPED",
        {
            "capabilities": list(unique.values())[:30],
            "human_confirmation_required": True,
        },
        unavailable=("domain-owner-confirmation",),
    )


def discover_flows(inputs: JsonObject) -> CapabilityOutcome:
    """Discover flow candidates between and, on request, inside modules.

    Two kinds of flow live in the one ``flows`` list the capability contract
    pins:

    ``import``
        The original module-to-module edges.  Still ``INFERRED`` -- an import
        is not proof that control ever crosses it.

    ``control-flow``
        A drawable graph of one named function's branches, loops and merge
        points, produced only when the caller names a function in
        ``flow_function``.  These come from the parser, so they are not
        guesses about what the source *says*.

    What stays unknown either way is which paths actually execute.  That is
    why ``unknown_runtime_branches`` remains true and the runtime observer
    stays declared unavailable: seeing every branch is not the same as knowing
    which one runs.
    """

    files = _files(inputs)
    imports = _imports(files)
    flows: list[dict[str, Any]] = [
        {
            "step": index,
            "kind": "import",
            "from": edge["from"],
            "to": edge["to"],
            "confidence": "INFERRED",
            "origin": edge.get("origin", ORIGIN_REGEX),
        }
        for index, edge in enumerate(imports, 1)
    ]

    function_name = inputs.get("flow_function")
    if function_name is not None:
        function_name = _identifier(function_name, "flow_function")
        requested_path = inputs.get("path")
        step = len(flows)
        for file in files:
            path = str(file["path"])
            if not is_python_path(path):
                continue
            if requested_path is not None and path != str(requested_path):
                continue
            step += 1
            graph = function_control_flow(str(file["text"]), function_name)
            if graph is None:
                # The file did not parse. Say so rather than emitting an empty
                # graph, which would read as "this function has no branches".
                flows.append(
                    {
                        "step": step,
                        "kind": "control-flow",
                        "path": path,
                        "function": function_name,
                        "origin": ORIGIN_REGEX,
                        "parse_status": "FAILED",
                        "nodes": [],
                        "edges": [],
                        "diagnostics": ["source did not parse"],
                    }
                )
                continue
            flows.append(
                {
                    "step": step,
                    "kind": "control-flow",
                    "path": path,
                    "function": function_name,
                    "origin": ORIGIN_PARSED,
                    "parse_status": "PASSED",
                    "nodes": graph["nodes"],
                    "edges": graph["edges"],
                    "diagnostics": graph["diagnostics"],
                }
            )

    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "STATIC_FLOW_CANDIDATES_DISCOVERED",
        {"flows": flows, "unknown_runtime_branches": True},
        unavailable=("runtime-path-observations",),
    )


def derive_data_lineage(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    patterns = (
        re.compile(r"(?i)\b(?:from|join|into|update)\s+([A-Za-z_][\w.]*)"),
        re.compile(r"(?i)\btable\s*[:=]\s*[\"']([A-Za-z_][\w.]*)"),
    )
    assets: list[dict[str, Any]] = []
    for file in files:
        for line, text in enumerate(str(file["text"]).splitlines(), 1):
            for pattern in patterns:
                for match in pattern.finditer(text):
                    assets.append(
                        {
                            "asset": match.group(1),
                            "path": file["path"],
                            "line": line,
                            "confidence": "INFERRED",
                        }
                    )
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "STATIC_DATA_LINEAGE_DERIVED",
        {"assets": assets, "runtime_lineage_verified": False},
        unavailable=("database-catalog-adapter", "runtime-lineage-collector"),
    )


def reconcile_api_event_topology(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    endpoints: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    endpoint_pattern = re.compile(
        r"(?i)(?:@(?:get|post|put|delete|patch)|\b(?:GET|POST|PUT|DELETE|PATCH))\s*\(?[\"']?(/[^\s\"')]+)"
    )
    event_pattern = re.compile(
        r"(?i)\b(?:publish|subscribe|topic|queue)\s*\(?[\"']([\w./:-]+)"
    )
    for file in files:
        for line, text in enumerate(str(file["text"]).splitlines(), 1):
            if match := endpoint_pattern.search(text):
                endpoints.append(
                    {"path": match.group(1), "source": file["path"], "line": line}
                )
            if match := event_pattern.search(text):
                events.append(
                    {"channel": match.group(1), "source": file["path"], "line": line}
                )
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "DECLARED_API_EVENT_TOPOLOGY_RECONCILED",
        {"endpoints": endpoints, "events": events, "runtime_activity": "NOT_RUN"},
        unavailable=("runtime-traffic-observer",),
    )


def fuse_runtime_observations(inputs: JsonObject) -> CapabilityOutcome:
    traces = _records(inputs, "traces")
    nodes, _ = _graph(inputs)
    known = {str(node.get("name", node.get("id"))) for node in nodes}
    fused = []
    for trace in traces:
        target = str(trace.get("component", ""))
        fused.append(
            {**trace, "graph_match": target in known, "source": "SUPPLIED_OBSERVATION"}
        )
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "SUPPLIED_RUNTIME_OBSERVATIONS_FUSED",
        {"observations": fused, "collector_executed": False},
        unavailable=("trace-collector", "log-provider"),
    )


def _diagram_evidence_ids(inputs: JsonObject) -> set[str]:
    evidence_ids: set[str] = set()
    for index, evidence in enumerate(_records(inputs, "evidence")):
        evidence_id = _identifier(evidence.get("id"), f"evidence[{index}].id")
        if evidence_id in evidence_ids:
            raise ValueError(f"duplicate evidence id: {evidence_id}")
        evidence_ids.add(evidence_id)
    return evidence_ids


def _diagram_evidence_refs(
    value: Any,
    *,
    field_name: str,
    evidence_ids: set[str],
) -> list[str]:
    refs = [_identifier(item, field_name) for item in _sequence(value, field_name)]
    if len(refs) != len(set(refs)):
        raise ValueError(f"{field_name} cannot contain duplicate references")
    unknown = sorted(set(refs) - evidence_ids)
    if unknown:
        raise ValueError(f"{field_name} contains dangling evidence references")
    return sorted(refs)


def _diagram_confidence(value: Any, field_name: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number between 0 and 1")
    if not math.isfinite(value) or value < 0 or value > 1:
        raise ValueError(f"{field_name} must be a finite number between 0 and 1")
    return value


def _validate_diagram_spec(
    spec: Mapping[str, Any],
    *,
    runtime_scope: TrustedRuntimeScope,
    evidence_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if type(spec.get("schema_version")) is not int or spec["schema_version"] != 1:
        raise ValueError("diagram_spec.schema_version must be integer 1")
    _identifier(spec.get("diagram_id"), "diagram_spec.diagram_id")
    _identifier(spec.get("type"), "diagram_spec.type")
    if spec.get("project_id") != runtime_scope.project_id:
        raise ValueError("diagram_spec.project_id must match the trusted request scope")
    if spec.get("revision_id") != runtime_scope.revision:
        raise ValueError("diagram_spec.revision_id must match the trusted revision")
    if "title" in spec and not isinstance(spec["title"], str):
        raise ValueError("diagram_spec.title must be a string")
    for field_name in ("view", "theme", "layout"):
        if field_name in spec and not isinstance(spec[field_name], Mapping):
            raise ValueError(f"diagram_spec.{field_name} must be an object")

    nodes = _records(spec, "nodes")
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        node_id = _identifier(node.get("id"), f"diagram_spec.nodes[{index}].id")
        _identifier(node.get("kind"), f"diagram_spec.nodes[{index}].kind")
        if not isinstance(node.get("label"), str):
            raise ValueError(f"diagram_spec.nodes[{index}].label must be a string")
        if node_id in node_ids:
            raise ValueError(f"duplicate diagram node id: {node_id}")
        node_ids.add(node_id)
        _diagram_evidence_refs(
            node.get("evidence_refs"),
            field_name=f"diagram_spec.nodes[{index}].evidence_refs",
            evidence_ids=evidence_ids,
        )
        if "confidence" in node:
            _diagram_confidence(
                node["confidence"], f"diagram_spec.nodes[{index}].confidence"
            )
        if "group_id" in node and node["group_id"] is not None:
            _identifier(node["group_id"], f"diagram_spec.nodes[{index}].group_id")
        if "semantic" in node and not isinstance(node["semantic"], Mapping):
            raise ValueError(f"diagram_spec.nodes[{index}].semantic must be an object")
        if (
            "position" in node
            and node["position"] is not None
            and not isinstance(node["position"], Mapping)
        ):
            raise ValueError(f"diagram_spec.nodes[{index}].position must be an object")
        if "lock" in node:
            lock = node["lock"]
            if not isinstance(lock, Mapping) or any(
                key not in {"semantic", "layout"} or type(value) is not bool
                for key, value in lock.items()
            ):
                raise ValueError(f"diagram_spec.nodes[{index}].lock is invalid")

    edges = _records(spec, "edges")
    edge_ids: set[str] = set()
    for index, edge in enumerate(edges):
        if "from" in edge or "to" in edge:
            raise ValueError(
                "diagram_spec edges must use source/target, not legacy from/to"
            )
        edge_id = _identifier(edge.get("id"), f"diagram_spec.edges[{index}].id")
        source = _identifier(edge.get("source"), f"diagram_spec.edges[{index}].source")
        target = _identifier(edge.get("target"), f"diagram_spec.edges[{index}].target")
        _identifier(edge.get("kind"), f"diagram_spec.edges[{index}].kind")
        if "label" in edge and not isinstance(edge["label"], str):
            raise ValueError(f"diagram_spec.edges[{index}].label must be a string")
        if edge_id in edge_ids:
            raise ValueError(f"duplicate diagram edge id: {edge_id}")
        edge_ids.add(edge_id)
        if source not in node_ids or target not in node_ids:
            raise ValueError("diagram_spec contains a dangling edge endpoint")
        _diagram_evidence_refs(
            edge.get("evidence_refs"),
            field_name=f"diagram_spec.edges[{index}].evidence_refs",
            evidence_ids=evidence_ids,
        )
        if "confidence" in edge:
            _diagram_confidence(
                edge["confidence"], f"diagram_spec.edges[{index}].confidence"
            )
    return nodes, edges


def compile_diagram_spec(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    if "nodes" in inputs or "edges" in inputs:
        nodes = _records(inputs, "nodes")
        edges = _records(inputs, "edges")
    else:
        nodes, edges = _graph(inputs)
    evidence_ids = _diagram_evidence_ids(inputs)
    compiled_nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        kind = _identifier(node.get("kind", "component"), f"nodes[{index}].kind")
        label = _identifier(
            node.get("label", node.get("name", node.get("id", "node"))),
            f"nodes[{index}].label",
        )
        evidence_refs = _diagram_evidence_refs(
            node.get("evidence_refs"),
            field_name=f"nodes[{index}].evidence_refs",
            evidence_ids=evidence_ids,
        )
        node_id_value = node.get("id")
        node_id = (
            _identifier(node_id_value, f"nodes[{index}].id")
            if node_id_value is not None
            else canonical_digest(
                {
                    "kind": kind,
                    "label": label,
                    "semantic": node.get("semantic", {}),
                    "evidence_refs": evidence_refs,
                }
            )
        )
        if node_id in node_ids:
            raise ValueError(f"duplicate diagram node id: {node_id}")
        node_ids.add(node_id)
        compiled_node: dict[str, Any] = {
            "id": node_id,
            "kind": kind,
            "label": label,
        }
        if evidence_refs:
            compiled_node["evidence_refs"] = evidence_refs
        if "semantic" in node:
            if not isinstance(node["semantic"], Mapping):
                raise ValueError(f"nodes[{index}].semantic must be an object")
            compiled_node["semantic"] = dict(node["semantic"])
        if "confidence" in node:
            compiled_node["confidence"] = _diagram_confidence(
                node["confidence"], f"nodes[{index}].confidence"
            )
        compiled_nodes.append(compiled_node)

    compiled_edges: list[dict[str, Any]] = []
    edge_ids: set[str] = set()
    for index, edge in enumerate(edges):
        has_canonical_endpoints = "source" in edge or "target" in edge
        has_legacy_endpoints = "from" in edge or "to" in edge
        if has_canonical_endpoints and has_legacy_endpoints:
            raise ValueError("edges cannot mix source/target with from/to")
        source_key, target_key = (
            ("source", "target") if has_canonical_endpoints else ("from", "to")
        )
        source = _identifier(edge.get(source_key), f"edges[{index}].{source_key}")
        target = _identifier(edge.get(target_key), f"edges[{index}].{target_key}")
        if source not in node_ids or target not in node_ids:
            raise ValueError("diagram projection contains a dangling edge endpoint")
        kind = _identifier(edge.get("kind", "relates"), f"edges[{index}].kind")
        evidence_refs = _diagram_evidence_refs(
            edge.get("evidence_refs"),
            field_name=f"edges[{index}].evidence_refs",
            evidence_ids=evidence_ids,
        )
        edge_id_value = edge.get("id")
        edge_identity = {
            "source": source,
            "target": target,
            "kind": kind,
            "label": edge.get("label"),
            "evidence_refs": evidence_refs,
        }
        edge_id = (
            _identifier(edge_id_value, f"edges[{index}].id")
            if edge_id_value is not None
            else canonical_digest(edge_identity)
        )
        if edge_id in edge_ids:
            raise ValueError(f"duplicate diagram edge id: {edge_id}")
        edge_ids.add(edge_id)
        compiled_edge: dict[str, Any] = {
            "id": edge_id,
            "source": source,
            "target": target,
            "kind": kind,
        }
        if "label" in edge:
            compiled_edge["label"] = _identifier(edge["label"], f"edges[{index}].label")
        if evidence_refs:
            compiled_edge["evidence_refs"] = evidence_refs
        if "confidence" in edge:
            compiled_edge["confidence"] = _diagram_confidence(
                edge["confidence"], f"edges[{index}].confidence"
            )
        compiled_edges.append(compiled_edge)

    diagram_type = _identifier(inputs.get("diagram_type", "component"), "diagram_type")
    diagram_key = _identifier(inputs.get("diagram_key", diagram_type), "diagram_key")
    spec = {
        "schema_version": 1,
        "diagram_id": canonical_digest(
            {
                "tenant_id": runtime_scope.tenant_id,
                "project_id": runtime_scope.project_id,
                "diagram_key": diagram_key,
            }
        ),
        "type": diagram_type,
        "project_id": runtime_scope.project_id,
        "revision_id": runtime_scope.revision,
        "nodes": sorted(compiled_nodes, key=lambda item: str(item["id"])),
        "edges": sorted(compiled_edges, key=lambda item: str(item["id"])),
    }
    if "title" in inputs:
        # ``title`` is a documented property of the published Diagram Spec
        # schema and both exporters already read it.  The compiler used to drop
        # it, so every diagram that reached a report or a deck through dispatch
        # was called "Diagram" and the reader had to guess which one they were
        # looking at.
        spec["title"] = _identifier(inputs["title"], "title")
    _validate_diagram_spec(
        spec,
        runtime_scope=runtime_scope,
        evidence_ids=evidence_ids,
    )
    return _outcome(
        "LOCAL_EXECUTED",
        "DIAGRAM_SPEC_COMPILED",
        {"diagram_spec": spec, "digest": canonical_digest(spec)},
    )


def render_diagram(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    spec = inputs.get("diagram_spec")
    if not isinstance(spec, Mapping):
        raise ValueError("diagram_spec must be an object")
    nodes, edges = _validate_diagram_spec(
        spec,
        runtime_scope=runtime_scope,
        evidence_ids=_diagram_evidence_ids(inputs),
    )
    ids: dict[str, str] = {}
    lines = ["flowchart TD"]
    labels_normalized = False
    for index, node in enumerate(nodes):
        original = str(node.get("id", node.get("name", index)))
        identifier = f"n{index}"
        ids[original] = identifier
        label, was_normalized = _safe_mermaid_label(
            node.get("label", node.get("name", original))
        )
        labels_normalized = labels_normalized or was_normalized
        open_token, close_token = _MERMAID_SHAPE_BY_KIND.get(
            str(node.get("kind", "")), _MERMAID_DEFAULT_SHAPE
        )
        lines.append(f"  {identifier}{open_token}{label}{close_token}")
    for edge in edges:
        source = ids[str(edge["source"])]
        target = ids[str(edge["target"])]
        if "label" not in edge:
            lines.append(f"  {source} --> {target}")
            continue
        # An edge label goes through the same allowlist as a node label. The
        # allowlist has no pipe in it, so a label cannot close the |...|
        # delimiter and start a new statement.
        edge_label, edge_normalized = _safe_mermaid_label(edge["label"])
        labels_normalized = labels_normalized or edge_normalized
        lines.append(f"  {source} -->|{edge_label}| {target}")
    mermaid = "\n".join(lines) + "\n"
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "SAFE_MERMAID_RENDERED",
        {
            "media_type": "text/vnd.mermaid",
            "content": mermaid,
            "digest": canonical_digest(mermaid),
        },
        unavailable=("svg-renderer", "png-renderer"),
        warnings=("diagram-labels-normalized",) if labels_normalized else (),
    )


def apply_diagram_patch(inputs: JsonObject) -> CapabilityOutcome:
    spec = inputs.get("diagram_spec")
    if not isinstance(spec, Mapping):
        raise ValueError("diagram_spec must be an object")
    patch = _records(inputs, "patch")
    locked = {
        str(item)
        for item in _sequence(inputs.get("locked_node_ids"), "locked_node_ids")
    }
    nodes = {str(node.get("id")): dict(node) for node in _records(spec, "nodes")}
    rejected: list[dict[str, Any]] = []
    for operation in patch:
        node_id = _identifier(operation.get("node_id"), "node_id")
        if node_id in locked:
            rejected.append({"node_id": node_id, "reason": "HUMAN_LOCKED"})
            continue
        if node_id not in nodes:
            rejected.append({"node_id": node_id, "reason": "UNKNOWN_NODE"})
            continue
        if "label" in operation:
            nodes[node_id]["label"] = str(operation["label"])
    updated = {**dict(spec), "nodes": list(nodes.values())}
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "DIAGRAM_PATCH_APPLIED",
        {
            "diagram_spec": updated,
            "rejected_operations": rejected,
            "locked_node_ids": sorted(locked),
        },
        unavailable=("browser-diagram-editor",),
    )


def generate_document(inputs: JsonObject) -> CapabilityOutcome:
    nodes, edges = _graph(inputs)
    normalized = False
    component_lines: list[str] = []
    for node in nodes[:50]:
        name, name_normalized = _safe_markdown_text(node.get("name", node.get("id")))
        kind, kind_normalized = _safe_markdown_text(node.get("kind", "component"))
        normalized = normalized or name_normalized or kind_normalized
        component_lines.append(f"- {name} ({kind})")

    relationship_lines: list[str] = []
    for edge in edges[:100]:
        edge_source, edge_target = _edge_endpoints(edge)
        source, source_normalized = _safe_markdown_text(edge_source)
        target, target_normalized = _safe_markdown_text(edge_target)
        kind, kind_normalized = _safe_markdown_text(edge.get("kind", "relates"))
        normalized = (
            normalized or source_normalized or target_normalized or kind_normalized
        )
        relationship_lines.append(f"- {source} -> {target} ({kind})")

    lines = ["# Architecture Evidence Report", "", "## Components", ""]
    lines.extend(component_lines)
    lines.extend(["", "## Relationships", ""])
    lines.extend(relationship_lines)
    lines.extend(
        [
            "",
            "## Evidence Boundary",
            "",
            "Runtime and external evidence: NOT_RUN. Certification: NOT_CERTIFIED.",
            "",
        ]
    )
    content = "\n".join(lines)
    return _outcome(
        "LOCAL_EXECUTED",
        "ARCHITECTURE_DOCUMENT_GENERATED",
        {
            "media_type": "text/markdown",
            "content": content,
            "digest": canonical_digest(content),
        },
        warnings=("markdown-fields-normalized",) if normalized else (),
    )


def generate_presentation(inputs: JsonObject) -> CapabilityOutcome:
    nodes, edges = _graph(inputs)
    slides = [
        {
            "title": "Project evidence boundary",
            "bullets": [
                "Static/local observations only",
                "External evidence NOT_RUN",
                "NOT_CERTIFIED",
            ],
        },
        {
            "title": "Components",
            "bullets": [str(node.get("name", node.get("id"))) for node in nodes[:8]],
        },
        {
            "title": "Relationships",
            "bullets": [
                # Two edge vocabularies reach this handler.  ``_graph`` builds
                # import edges as from/to, while a caller that already compiled
                # a Diagram Spec passes the canonical source/target -- which
                # ``compile_diagram_spec`` has accepted from the start.  Reading
                # only from/to printed a deck full of "None -> None" for the
                # second case: a wrong slide, silently, with no rejection.
                "{} -> {}".format(*_edge_endpoints(edge))
                for edge in edges[:8]
            ],
        },
    ]
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "PRESENTATION_MANIFEST_GENERATED",
        {"slides": slides, "digest": canonical_digest(slides), "pptx_generated": False},
        unavailable=("pptx-renderer", "pdf-renderer"),
    )


def bundle_report(inputs: JsonObject) -> CapabilityOutcome:
    artifacts = _records(inputs, "artifacts")
    index: list[dict[str, Any]] = []
    artifact_ids: set[str] = set()
    for item in artifacts:
        artifact_id = _identifier(item.get("artifact_id"), "artifact_id")
        if artifact_id in artifact_ids:
            raise ValueError("artifact_id values must be unique")
        artifact_ids.add(artifact_id)
        supplied_digest = item.get("digest")
        if not isinstance(supplied_digest, str):
            raise ValueError("artifact digest must be a canonical sha256 digest")
        normalized_digest = validate_digest(supplied_digest)
        if supplied_digest != normalized_digest:
            raise ValueError("artifact digest must use canonical lowercase sha256 form")
        has_text = "content_text" in item
        has_base64 = "content_base64" in item
        if has_text == has_base64:
            raise ValueError(
                "artifact must supply exactly one of content_text or content_base64"
            )
        if has_text:
            content_text = item["content_text"]
            if not isinstance(content_text, str):
                raise ValueError("artifact content_text must be a string")
            content_bytes = content_text.encode("utf-8", errors="strict")
            content_encoding = "utf-8"
        else:
            content_base64 = item["content_base64"]
            if not isinstance(content_base64, str):
                raise ValueError("artifact content_base64 must be a string")
            try:
                encoded = content_base64.encode("ascii", errors="strict")
                content_bytes = base64.b64decode(encoded, validate=True)
            except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
                raise ValueError("artifact content_base64 must be strict base64") from exc
            if base64.b64encode(content_bytes).decode("ascii") != content_base64:
                raise ValueError("artifact content_base64 must use canonical encoding")
            content_encoding = "base64"
        observed_digest = (
            "sha256:" + hashlib.sha256(content_bytes).hexdigest()
        )
        if observed_digest != normalized_digest:
            raise ValueError("artifact digest does not bind the supplied content bytes")
        media_type = item.get("media_type", "application/octet-stream")
        if not isinstance(media_type, str) or not media_type:
            raise ValueError("artifact media_type must be a non-empty string")
        index.append(
            {
                "artifact_id": artifact_id,
                "digest": normalized_digest,
                "media_type": media_type,
                "byte_count": len(content_bytes),
                "content_encoding": content_encoding,
            }
        )
    index.sort(key=lambda item: item["artifact_id"])
    return _outcome(
        "LOCAL_EXECUTED",
        "REPORT_BUNDLE_INDEXED",
        {
            "artifacts": index,
            "bundle_digest": canonical_digest(index),
            "content_addressed": True,
            "artifact_bytes_verified": True,
        },
    )


def answer_project_query(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    query = _identifier(inputs.get("query", "project"), "query")
    tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9_]{2,}", query)]
    matches: list[dict[str, Any]] = []
    for file in files:
        for line, text in enumerate(str(file["text"]).splitlines(), 1):
            score = sum(token in text.lower() for token in tokens)
            if score:
                matches.append(
                    {
                        "path": file["path"],
                        "line": line,
                        "score": score,
                        "excerpt": text[:240],
                        "evidence": file["sha256"],
                    }
                )
    matches.sort(key=lambda item: (-item["score"], item["path"], item["line"]))
    code = "PROJECT_QUERY_ANSWERED" if matches else "PROJECT_QUERY_ABSTAINED"
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        code,
        {
            "query": query,
            "matches": matches[:20],
            "answer": matches[0]["excerpt"] if matches else None,
            "confidence": "LEXICAL_MATCH" if matches else "UNKNOWN",
        },
        unavailable=("semantic-vector-provider", "model-answer-adapter"),
        warnings=("lexical-match-is-not-semantic-confirmation",) if matches else (),
    )


def analyze_impact(inputs: JsonObject) -> CapabilityOutcome:
    changed = {
        _safe_path(item)
        for item in _sequence(inputs.get("changed_paths"), "changed_paths")
    }
    _, edges = _graph(inputs)
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        edge_source, edge_target = _edge_endpoints(edge)
        reverse[str(edge_target)].add(str(edge_source))
    impacted = set(changed)
    queue = deque(sorted(changed))
    while queue and len(impacted) < 10_000:
        node = queue.popleft()
        for parent in sorted(reverse[node]):
            if parent not in impacted:
                impacted.add(parent)
                queue.append(parent)
    return _outcome(
        "LOCAL_EXECUTED",
        "CHANGE_IMPACT_ANALYZED",
        {
            "changed": sorted(changed),
            "impacted": sorted(impacted),
            "bounded": len(impacted) < 10_000,
        },
    )


def evaluate_architecture_rules(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    rules = _records(inputs, "rules")
    findings: list[dict[str, Any]] = []
    for rule in rules:
        rule_id = _identifier(rule.get("id"), "rule.id")
        pattern = str(rule.get("pattern", ""))
        if not pattern or len(pattern) > 256:
            raise ValueError("rule pattern must be 1..256 characters")
        compiled = re.compile(re.escape(pattern), re.IGNORECASE)
        for file in files:
            for line, text in enumerate(str(file["text"]).splitlines(), 1):
                if compiled.search(text):
                    findings.append(
                        {
                            "rule_id": rule_id,
                            "path": file["path"],
                            "line": line,
                            "evidence": file["sha256"],
                        }
                    )
    return _outcome(
        "LOCAL_EXECUTED",
        "ARCHITECTURE_RULES_EVALUATED",
        {"findings": findings, "rule_count": len(rules)},
    )


def detect_architecture_drift(inputs: JsonObject) -> CapabilityOutcome:
    declared = {
        str(item)
        for item in _sequence(inputs.get("declared_components"), "declared_components")
    }
    files = _files(inputs)
    discovered = {PurePosixPath(str(file["path"])).parts[0] for file in files}
    return _outcome(
        "LOCAL_EXECUTED",
        "ARCHITECTURE_DRIFT_DETECTED",
        {
            "missing_declared": sorted(declared - discovered),
            "undeclared_discovered": sorted(discovered - declared),
            "coverage": "STATIC_ONLY",
        },
    )


def score_risk_and_debt(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    risks: list[dict[str, Any]] = []
    for file in files:
        text = str(file["text"])
        lines = text.splitlines()
        markers = len(re.findall(r"(?i)\b(?:TODO|FIXME|HACK|XXX)\b", text))
        branches = len(
            re.findall(r"\b(?:if|elif|else|for|while|case|catch|except)\b", text)
        )
        score = min(
            100, int(math.log2(max(len(lines), 1)) * 8 + markers * 10 + branches * 2)
        )
        risks.append(
            {
                "path": file["path"],
                "score": score,
                "todo_markers": markers,
                "branch_tokens": branches,
                "confidence": "INFERRED",
            }
        )
    risks.sort(key=lambda item: (-item["score"], item["path"]))
    return _outcome(
        "LOCAL_EXECUTED",
        "RISK_AND_TECHNICAL_DEBT_SCORED",
        {"hotspots": risks, "model_version": "bounded-static-v1"},
    )


def build_threat_model(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    secret_findings = _redacted_secret_findings(files)
    nodes, edges = _graph(inputs)
    threats = [
        {
            "id": f"secret-{index}",
            "category": finding["kind"],
            "asset": finding["path"],
            "evidence_fingerprint": finding["fingerprint"],
            "secret_redacted": True,
        }
        for index, finding in enumerate(secret_findings, 1)
    ]
    if any("api" in str(node.get("name", "")).lower() for node in nodes):
        threats.append(
            {
                "id": "api-auth-boundary",
                "category": "authorization-review",
                "asset": "api",
                "confidence": "INFERRED",
            }
        )
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "BOUNDED_THREAT_MODEL_BUILT",
        {
            "threats": threats,
            "graph_edge_count": len(edges),
            "secrets_disclosed": False,
        },
        unavailable=("sast-scanner", "dependency-scanner", "human-threat-review"),
    )


def cache_analysis_stage(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    stage = _identifier(inputs.get("stage", "analysis"), "stage")
    input_digest = canonical_digest(inputs.get("stage_inputs", {}))
    existing = inputs.get("existing_cache_key")
    if existing is not None:
        existing = validate_digest(existing)
    key_payload = {
        "schema_version": CACHE_KEY_SCHEMA_VERSION,
        "implementation_version": CACHE_IMPLEMENTATION_VERSION,
        "tenant_id": runtime_scope.tenant_id,
        "project_id": runtime_scope.project_id,
        "revision": runtime_scope.revision,
        "stage": stage,
        "input_digest": input_digest,
    }
    key = canonical_digest(key_payload)
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "ANALYSIS_CACHE_KEY_DERIVED",
        {
            "cache_key": key,
            "caller_reported_key_match": existing == key,
            "stage": stage,
            "input_digest": input_digest,
            "schema_version": CACHE_KEY_SCHEMA_VERSION,
            "implementation_version": CACHE_IMPLEMENTATION_VERSION,
        },
        unavailable=(
            "durable-scoped-cache-store",
            "cache-entry-content-verification",
        ),
        warnings=("caller-supplied-cache-key-not-content-verified",),
    )


def validate_artifact_version_proposal(inputs: JsonObject) -> CapabilityOutcome:
    artifact_id = _identifier(inputs.get("artifact_id", "artifact"), "artifact_id")
    content = inputs.get("content")
    locked = bool(inputs.get("human_locked", False))
    proposed = inputs.get("proposed_content", content)
    previous_version = inputs.get("previous_version", 0)
    if type(previous_version) is not int or previous_version < 0:
        raise ValueError("previous_version must be a non-negative integer")
    version = previous_version + 1
    content_digest = canonical_digest(proposed)
    if locked and proposed != content:
        return _outcome(
            "BLOCKED",
            "HUMAN_LOCK_PREVENTED_OVERWRITE",
            {
                "artifact_id": artifact_id,
                "proposed_version": version,
                "content_digest": content_digest,
                "caller_reported_human_locked": True,
                "authoritative_lock_verified": False,
                "version_persisted": False,
            },
            unavailable=("authoritative-human-lock-store", "artifact-version-store"),
            warnings=("caller-supplied-lock-state-unverified",),
        )
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "ARTIFACT_VERSION_PROPOSAL_VALIDATED",
        {
            "artifact_id": artifact_id,
            "proposed_version": version,
            "content_digest": content_digest,
            "caller_reported_human_locked": locked,
            "authoritative_lock_verified": False,
            "version_persisted": False,
        },
        unavailable=("authoritative-human-lock-store", "artifact-version-store"),
        warnings=("caller-supplied-lock-state-unverified",),
    )


def plan_draft_pr(inputs: JsonObject) -> CapabilityOutcome:
    changed = [
        _safe_path(item)
        for item in _sequence(inputs.get("changed_paths"), "changed_paths")
    ]
    return _outcome(
        "PLANNING_ONLY",
        "DRAFT_PR_PLAN_VALIDATED",
        {
            "title": str(inputs.get("title", "Project Intelligence artifacts")),
            "changed_paths": changed,
            "draft": True,
            "git_mutated": False,
            "push_performed": False,
        },
        unavailable=("scm-credential-adapter", "remote-pr-provider"),
    )


def authorize_and_audit(inputs: JsonObject) -> CapabilityOutcome:
    actor_tenant = _identifier(inputs.get("actor_tenant_id"), "actor_tenant_id")
    resource_tenant = _identifier(
        inputs.get("resource_tenant_id"), "resource_tenant_id"
    )
    roles = {str(item) for item in _sequence(inputs.get("roles"), "roles")}
    required = {
        str(item) for item in _sequence(inputs.get("required_roles"), "required_roles")
    }
    candidate_match = actor_tenant == resource_tenant and required.issubset(roles)
    if not candidate_match:
        return _outcome(
            "BLOCKED",
            "LOCAL_POLICY_DENIED",
            {
                "enforcement_authorized": False,
                "simulated_tenant_match": actor_tenant == resource_tenant,
                "simulated_missing_roles": sorted(required - roles),
                "audit_digest": canonical_digest(inputs),
            },
            unavailable=("enterprise-identity-provider", "scim-adapter"),
        )
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "LOCAL_POLICY_SIMULATED",
        {
            "enforcement_authorized": False,
            "simulated_tenant_match": actor_tenant == resource_tenant,
            "simulated_missing_roles": sorted(required - roles),
            "audit_digest": canonical_digest(inputs),
        },
        unavailable=("enterprise-identity-provider", "scim-adapter"),
        warnings=("caller-supplied-identity-and-roles-not-enforcement-authority",),
    )


def validate_connector_contract(inputs: JsonObject) -> CapabilityOutcome:
    connector = inputs.get("connector")
    if not isinstance(connector, Mapping):
        raise ValueError("connector must be an object")
    connector_id = _identifier(connector.get("id"), "connector.id")
    scopes, forbidden = _canonical_allowlisted_values(
        connector.get("scopes"),
        field_name="connector.scopes",
        allowlist=_CONNECTOR_READ_SCOPE_ALLOWLIST,
    )
    return _outcome(
        "PLANNING_ONLY" if not forbidden else "BLOCKED",
        "CONNECTOR_CONTRACT_VALIDATED" if not forbidden else "CONNECTOR_SCOPE_REJECTED",
        {
            "connector_id": connector_id,
            "scopes": scopes,
            "forbidden_scopes": forbidden,
            "connector_called": False,
            "enforcement_authorized": False,
        },
        unavailable=("mcp-connector-runtime", "oauth-broker", "scope-authority"),
        warnings=("caller-supplied-connector-descriptor-unverified",),
    )


def plan_repository_shards(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    max_bytes = int(inputs.get("max_shard_bytes", 256 * 1024))
    if max_bytes < 1:
        raise ValueError("max_shard_bytes must be positive")
    oversized_paths = [
        str(file["path"]) for file in files if int(file["bytes"]) > max_bytes
    ]
    if oversized_paths:
        return _outcome(
            "BLOCKED",
            "SHARD_SIZE_LIMIT_EXCEEDED",
            {
                "shards": [],
                "total_files": len(files),
                "oversized_paths": oversized_paths,
                "distributed_execution": False,
            },
            unavailable=("oversized-file-partitioning", "distributed-runner-fleet"),
        )
    shards: list[dict[str, Any]] = []
    current: list[str] = []
    size = 0
    for file in files:
        if current and size + int(file["bytes"]) > max_bytes:
            shards.append({"paths": current, "bytes": size})
            current, size = [], 0
        current.append(str(file["path"]))
        size += int(file["bytes"])
    if current:
        shards.append({"paths": current, "bytes": size})
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "REPOSITORY_SHARDS_PLANNED",
        {
            "shards": shards,
            "total_files": len(files),
            "oversized_paths": [],
            "distributed_execution": False,
        },
        unavailable=("distributed-runner-fleet",),
    )


def evaluate_slo(inputs: JsonObject) -> CapabilityOutcome:
    observations = _records(inputs, "observations")
    target_token = str(inputs.get("success_rate_target", "0.99"))
    if len(target_token.encode("utf-8", errors="strict")) > 64:
        raise ValueError("success_rate_target decimal token exceeds 64 UTF-8 bytes")
    try:
        target = Decimal(target_token)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            "success_rate_target must be an exact decimal between 0 and 1"
        ) from exc
    if not target.is_finite() or target < Decimal("0") or target > Decimal("1"):
        raise ValueError(
            "success_rate_target must be a finite exact decimal between 0 and 1"
        )
    _sign, digits, exponent = target.as_tuple()
    if len(digits) > 18 or exponent < -18 or exponent > 0:
        raise ValueError(
            "success_rate_target supports at most 18 significant and fractional digits"
        )
    successes = sum(item.get("status") == "SUCCEEDED" for item in observations)
    rate = (
        Decimal(successes) / Decimal(len(observations))
        if observations
        else Decimal("0")
    )
    return _outcome(
        "LOCAL_EXECUTED",
        "SLO_EVALUATED",
        {
            "sample_count": len(observations),
            "success_rate": format(rate, "f"),
            "target": format(target, "f"),
            "met": bool(observations) and rate >= target,
            "production_slo_claimed": False,
        },
    )


def evaluate_quality(inputs: JsonObject) -> CapabilityOutcome:
    results = _records(inputs, "test_results")
    required = [item for item in results if item.get("required", True)]
    failed = [item for item in required if item.get("status") not in {"PASSED", "PASS"}]
    return _outcome(
        "LOCAL_EXECUTED",
        "LOCAL_QUALITY_EVALUATED",
        {
            "required_count": len(required),
            "failed": failed,
            "local_pass": bool(required) and not failed,
            "external_evidence": "NOT_RUN",
        },
    )


def validate_conversion_mapping(inputs: JsonObject) -> CapabilityOutcome:
    mappings = _records(inputs, "mappings")
    invalid = [
        item
        for item in mappings
        if not item.get("source_ref")
        or not item.get("target_ref")
        or not item.get("evidence_ref")
    ]
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED" if not invalid else "BLOCKED",
        "CONVERSION_MAPPING_VALIDATED"
        if not invalid
        else "CONVERSION_MAPPING_INCOMPLETE",
        {
            "mapping_count": len(mappings),
            "invalid_mappings": invalid,
            "conversion_executed": False,
        },
        unavailable=("conversion-route-runtime",),
    )


_RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _validated_rfc3339(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _RFC3339_DATE_TIME.fullmatch(value):
        raise ValueError(
            f"{field_name} must be an RFC 3339 date-time with an explicit offset"
        )
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid RFC 3339 date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


def _estimate_number(value: Decimal) -> int:
    """Return an exact JSON number accepted by the float-free canonical encoder."""

    return int(value.to_integral_value(rounding=ROUND_CEILING))


def estimate_runtime_cost(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    files = _files(inputs)
    workers = inputs.get("workers", 1)
    if type(workers) is not int or not 1 <= workers <= 128:
        raise ValueError("workers must be an integer between 1 and 128")
    review_seconds = inputs.get("human_review_effort_seconds", 0)
    if (
        type(review_seconds) is not int
        or review_seconds < 0
        or review_seconds > 315_576_000
    ):
        raise ValueError(
            "human_review_effort_seconds must be an integer between 0 and 315576000"
        )
    as_of = _validated_rfc3339(inputs.get("as_of"), "as_of")
    total_bytes = sum(int(file["bytes"]) for file in files)
    effective_workers = Decimal(min(workers, max(len(files), 1)))
    parse_p50 = Decimal(total_bytes) / Decimal(250_000) / effective_workers
    graph_p50 = Decimal(len(files)) * Decimal("0.002") / effective_workers
    parse_p90 = parse_p50 * Decimal("1.8")
    graph_p90 = graph_p50 * Decimal("1.8")
    p50 = parse_p50 + graph_p50
    p90 = parse_p90 + graph_p90
    review_p50_hours = Decimal(review_seconds) / Decimal(3_600)
    review_p90_hours = review_p50_hours * Decimal("1.5")
    stages = [
        {
            "name": "parse",
            "p50_seconds": _estimate_number(parse_p50),
            "p90_seconds": _estimate_number(parse_p90),
            "queue_seconds": 0,
        },
        {
            "name": "graph",
            "p50_seconds": _estimate_number(graph_p50),
            "p90_seconds": _estimate_number(graph_p90),
            "queue_seconds": 0,
        },
    ]
    estimate_id = canonical_digest(
        {
            "tenant_id": runtime_scope.tenant_id,
            "project_id": runtime_scope.project_id,
            "revision": runtime_scope.revision,
            "as_of": as_of,
            "workers": workers,
            "files": [
                {"path": file["path"], "sha256": file["sha256"]} for file in files
            ],
            "human_review_effort_seconds": review_seconds,
            "model_version": "local-linear-v2",
        }
    )
    return _outcome(
        "LOCAL_EXECUTED",
        "RUNTIME_COST_ESTIMATED",
        {
            "estimate_id": estimate_id,
            "as_of": as_of,
            "project_revision_id": runtime_scope.revision,
            "pipeline": ["parse", "graph"],
            "system_wall_clock_eta": {
                "p50_seconds": _estimate_number(p50),
                "p90_seconds": _estimate_number(p90),
                "confidence": 0,
            },
            "stages": stages,
            "human_review_effort": {
                "p50_hours": _estimate_number(review_p50_hours),
                "p90_hours": _estimate_number(review_p90_hours),
            },
            "assumptions": [
                "local linear model without historical calibration",
                "queue delay and provider costs are not estimated",
                "durations are rounded up to whole seconds and review hours",
            ],
        },
    )


def plan_deployment(inputs: JsonObject) -> CapabilityOutcome:
    topology = str(inputs.get("topology", "self-hosted"))
    requirements = [
        "immutable-image-digest",
        "secret-reference-only",
        "backup-restore-plan",
        "tenant-isolation",
        "rollback-plan",
    ]
    supplied = {str(item) for item in _sequence(inputs.get("controls"), "controls")}
    return _outcome(
        "PLANNING_ONLY",
        "DEPLOYMENT_READINESS_PLANNED",
        {
            "topology": topology,
            "missing_controls": sorted(set(requirements) - supplied),
            "deployment_performed": False,
        },
        unavailable=(
            "container-build",
            "signer",
            "cluster-provider",
            "deployment-authority",
        ),
    )


def evaluate_release_readiness(inputs: JsonObject) -> CapabilityOutcome:
    gates = _records(inputs, "gates")
    failing = [
        item
        for item in gates
        if item.get("required", True) and item.get("status") not in {"PASSED", "PASS"}
    ]
    decision = "EXTERNAL_GATE_REQUIRED" if gates and not failing else "BLOCKED"
    return _outcome(
        "PLANNING_ONLY",
        "RELEASE_READINESS_PLANNED",
        {
            "decision": decision,
            "failing_gates": failing,
            "certified": False,
            "release_authorized": False,
        },
        unavailable=("independent-certification-authority", "production-evidence"),
        warnings=("caller-supplied-gate-statuses-unverified",),
    )


def evaluate_entitlement_usage(inputs: JsonObject) -> CapabilityOutcome:
    edition = str(inputs.get("edition", "community"))
    requested = {
        str(item)
        for item in _sequence(inputs.get("requested_features"), "requested_features")
    }
    entitled = {
        str(item)
        for item in _sequence(inputs.get("entitled_features"), "entitled_features")
    }
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "LOCAL_ENTITLEMENT_EVALUATED",
        {
            "edition": edition,
            "caller_reported_entitled_features": sorted(entitled),
            "caller_reported_allowed_features": sorted(requested & entitled),
            "caller_reported_denied_features": sorted(requested - entitled),
            "enforcement_authorized": False,
            "usage_record_digest": canonical_digest(inputs),
            "billing_performed": False,
        },
        unavailable=("billing-provider", "license-authority"),
        warnings=("caller-supplied-entitlements-unverified",),
    )


def negotiate_debug_adapter(inputs: JsonObject) -> CapabilityOutcome:
    descriptor = inputs.get("adapter")
    if not isinstance(descriptor, Mapping):
        raise ValueError("adapter must be an object")
    _identifier(descriptor.get("id"), "adapter.id")
    requested, rejected_requested = _canonical_allowlisted_values(
        inputs.get("requested_capabilities"),
        field_name="requested_capabilities",
        allowlist=_DEBUG_CAPABILITY_ALLOWLIST,
    )
    supported, rejected_supported = _canonical_allowlisted_values(
        descriptor.get("capabilities"),
        field_name="adapter.capabilities",
        allowlist=_DEBUG_CAPABILITY_ALLOWLIST,
    )
    requested_set = set(requested)
    supported_set = set(supported)
    forbidden = sorted(set(rejected_requested) | set(rejected_supported))
    negotiated = sorted(requested_set & supported_set)
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED" if not forbidden else "BLOCKED",
        "DEBUG_CAPABILITIES_NEGOTIATED"
        if not forbidden
        else "DEBUG_CAPABILITY_REJECTED",
        {
            "negotiated": negotiated,
            "unsupported": sorted(requested_set - supported_set),
            "forbidden": forbidden,
            "adapter_started": False,
            "enforcement_authorized": False,
        },
        unavailable=("dap-process-adapter", "adapter-capability-attestation"),
        warnings=("caller-supplied-adapter-capabilities-unverified",),
    )


_DEBUG_SESSION_MODES = frozenset({"observe", "guided", "challenge", "free", "compare"})
_DEBUG_TARGET_KINDS = frozenset(
    {"test", "main", "api", "cli", "cron", "consumer", "browser_scenario", "replay"}
)
_DEBUG_DIFFICULTIES = frozenset({"beginner", "intermediate", "advanced"})


def _debug_runtime_profile(inputs: JsonObject) -> dict[str, Any]:
    profile = inputs.get("runtime_profile")
    if not isinstance(profile, Mapping):
        raise ValueError("runtime_profile must be an object")
    runtime_profile_id = _identifier(
        profile.get("runtime_profile_id"), "runtime_profile.runtime_profile_id"
    )
    image_digest = validate_digest(profile.get("image_digest"))
    if profile.get("image_digest") != image_digest:
        raise ValueError("runtime_profile.image_digest must be canonical")
    normalized: dict[str, Any] = {
        "runtime_profile_id": runtime_profile_id,
        "image_digest": image_digest,
    }
    if "toolchain" in profile:
        if not isinstance(profile["toolchain"], Mapping):
            raise ValueError("runtime_profile.toolchain must be an object")
        normalized["toolchain"] = dict(profile["toolchain"])
    return normalized


def _debug_target(inputs: JsonObject) -> dict[str, str]:
    target = inputs.get("debug_target")
    if not isinstance(target, Mapping):
        raise ValueError("debug_target must be an object")
    kind = _identifier(target.get("kind"), "debug_target.kind")
    if kind not in _DEBUG_TARGET_KINDS:
        raise ValueError("debug_target.kind is not allowlisted")
    return {"kind": kind, "ref": _identifier(target.get("ref"), "debug_target.ref")}


def _debug_mode(inputs: JsonObject) -> str:
    mode = _identifier(inputs.get("debug_mode", "guided"), "debug_mode")
    if mode not in _DEBUG_SESSION_MODES:
        raise ValueError("debug_mode is not allowlisted")
    return mode


def _debug_session_adapter(inputs: JsonObject) -> dict[str, str]:
    adapter = inputs.get("adapter")
    if not isinstance(adapter, Mapping):
        raise ValueError("adapter must be an object")
    adapter_id = _identifier(
        adapter.get("adapter_id", adapter.get("id")), "adapter.adapter_id"
    )
    version = _identifier(adapter.get("version"), "adapter.version")
    digest = validate_digest(adapter.get("digest"))
    if adapter.get("digest") != digest:
        raise ValueError("adapter.digest must be canonical")
    return {"adapter_id": adapter_id, "version": version, "digest": digest}


def _debug_session_id(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> str:
    derived = canonical_digest(
        {
            "tenant_id": runtime_scope.tenant_id,
            "project_id": runtime_scope.project_id,
            "revision": runtime_scope.revision,
            "runtime_profile": _debug_runtime_profile(inputs),
            "target": _debug_target(inputs),
            "mode": _debug_mode(inputs),
        }
    )
    supplied = inputs.get("debug_session_id")
    if supplied is not None and supplied != derived:
        raise ValueError("debug_session_id does not match the bound session plan")
    return derived


def plan_debug_session(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    ttl_seconds = inputs.get("ttl_seconds", 900)
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3_600:
        raise ValueError("ttl_seconds must be an integer between 1 and 3600")
    capabilities, forbidden = _canonical_allowlisted_values(
        inputs.get("requested_capabilities"),
        field_name="requested_capabilities",
        allowlist=_DEBUG_CAPABILITY_ALLOWLIST,
    )
    if forbidden:
        raise ValueError("requested_capabilities contains a forbidden capability")
    session = {
        "debug_session_id": _debug_session_id(inputs, runtime_scope),
        "tenant_id": runtime_scope.tenant_id,
        "project_id": runtime_scope.project_id,
        "revision_id": runtime_scope.revision,
        "runtime_profile": _debug_runtime_profile(inputs),
        "target": _debug_target(inputs),
        "mode": _debug_mode(inputs),
        "state": "requested",
        "adapter": _debug_session_adapter(inputs),
        "capabilities": capabilities,
        "policy": {
            "policy_id": canonical_digest(
                {
                    "tenant_id": runtime_scope.tenant_id,
                    "project_id": runtime_scope.project_id,
                    "policy": "bounded-local-debug-plan-v1",
                }
            ),
            "environment": "isolated-local-plan",
            "evaluate_mode": "read_only",
        },
        "ttl_seconds": ttl_seconds,
    }
    return _outcome(
        "PLANNING_ONLY",
        "DEBUG_SANDBOX_SESSION_PLANNED",
        {"debug_session": session, "sandbox_started": False},
        unavailable=("container-or-microvm-runner", "debug-adapter-process"),
    )


def reduce_debug_view(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    events, sanitization = _sanitized_debug_events(
        inputs, runtime_scope=runtime_scope
    )
    threads: dict[str, dict[str, Any]] = {}
    for event in events:
        payload = event["payload"]
        thread = str(payload.get("thread_id", "main"))
        threads[thread] = {
            "last_event": event["event_type"],
            "sequence": event["sequence"],
            "frame": payload.get("frame"),
        }
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "DEBUG_VIEW_STATE_REDUCED",
        {"threads": threads, "event_count": len(events), "ui_rendered": False},
        unavailable=("browser-debug-workbench",),
        warnings=_debug_sanitization_warnings(sanitization),
    )


def build_debug_mission(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    frames = _records(inputs, "frames")
    if not frames:
        raise ValueError("frames must contain at least one learning step")
    difficulty = _identifier(
        inputs.get("debug_difficulty", "beginner"), "debug_difficulty"
    )
    if difficulty not in _DEBUG_DIFFICULTIES:
        raise ValueError("debug_difficulty is not allowlisted")
    steps: list[dict[str, Any]] = []
    for index, frame in enumerate(frames, 1):
        frame_id = _identifier(frame.get("frame_id"), f"frames[{index - 1}].frame_id")
        evidence_ref = _identifier(
            frame.get("evidence_ref"), f"frames[{index - 1}].evidence_ref"
        )
        function_name, _ = _safe_markdown_text(frame.get("function", "frame"))
        steps.append(
            {
                "step_id": canonical_digest(
                    {
                        "tenant_id": runtime_scope.tenant_id,
                        "project_id": runtime_scope.project_id,
                        "revision": runtime_scope.revision,
                        "frame_id": frame_id,
                        "ordinal": index,
                    }
                ),
                "breakpoint_ref": frame_id,
                "prompt": f"Inspect {function_name} and cite {evidence_ref}.",
                "hints": ["Use only the supplied frame and evidence reference."],
                "completion": f"evidence-cited:{evidence_ref}",
            }
        )
    target = _debug_target(inputs)
    mission = {
        "mission_id": canonical_digest(
            {
                "debug_session_id": _debug_session_id(inputs, runtime_scope),
                "steps": [step["step_id"] for step in steps],
            }
        ),
        "tenant_id": runtime_scope.tenant_id,
        "project_id": runtime_scope.project_id,
        "revision_id": runtime_scope.revision,
        "title": "Evidence-bound local debugging mission",
        "mode": _debug_mode(inputs),
        "difficulty": difficulty,
        "entry": target,
        "learning_objectives": [
            "Trace the supplied control-flow frame.",
            "Cite the supplied evidence reference before completion.",
        ],
        "steps": steps,
        "assessment": {"type": "evidence-citation", "pass_score": 1},
        "stale": False,
        "redaction_profile": "recursive-field-policy-v2",
    }
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "DEBUG_LEARNING_MISSION_BUILT",
        {"mission": mission, "model_used": False, "side_effects": False},
        unavailable=("learning-model-adapter", "interactive-debug-ui"),
    )


def build_replay_bundle(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    events, sanitization = _sanitized_debug_events(
        inputs, runtime_scope=runtime_scope
    )
    debug_session_id = _debug_session_id(inputs, runtime_scope)
    chunks: list[dict[str, Any]] = []
    previous_sha256: str | None = None
    for event in events:
        event_bytes = canonical_json_bytes(event)
        event_sha256 = hashlib.sha256(event_bytes).hexdigest()
        chunks.append(
            {
                "chunk_id": canonical_digest(
                    {
                        "debug_session_id": debug_session_id,
                        "event_id": event["event_id"],
                        "event_sha256": event_sha256,
                    }
                ),
                "kind": "debug-event",
                "sha256": event_sha256,
                "size_bytes": len(event_bytes),
                "previous_sha256": previous_sha256,
                "event": event,
            }
        )
        previous_sha256 = event_sha256
    replay_bundle_id = canonical_digest(
        {
            "debug_session_id": debug_session_id,
            "chunks": [chunk["sha256"] for chunk in chunks],
            "replay_level": "R0",
        }
    )
    manifest_body = {
        "replay_bundle_id": replay_bundle_id,
        "tenant_id": runtime_scope.tenant_id,
        "project_id": runtime_scope.project_id,
        "revision_id": runtime_scope.revision,
        "source_debug_session_id": debug_session_id,
        "replay_level": "R0",
        "runtime_profile": _debug_runtime_profile(inputs),
        "reproducibility": {
            "event_order": "positive-unique-sequence",
            "terminal_event_sha256": previous_sha256,
            "native_runtime_reexecution": "NOT_RUN",
        },
        "chunks": chunks,
        "redaction": {
            "profile": "recursive-field-policy-v2",
            "scan_status": "review_required",
            "omitted_fields": [
                "inline-credential-values",
                "sensitive-keyed-fields",
            ],
            "sensitive_fields_omitted": sanitization["sensitive_fields_omitted"],
            "inline_secret_values_redacted": sanitization[
                "inline_secret_values_redacted"
            ],
            "strings_truncated": sanitization["strings_truncated"],
        },
        "native_reverse_debug": False,
    }
    bundle = {
        **manifest_body,
        "integrity": {
            "manifest_sha256": hashlib.sha256(
                canonical_json_bytes(manifest_body)
            ).hexdigest(),
            "signature_ref": "NOT_RUN",
            "signature_status": "NOT_RUN",
            "manifest_digest_scope": "bundle-without-integrity",
        },
    }
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "R0_REPLAY_BUNDLE_BUILT",
        {"bundle": bundle, "digest": canonical_digest(bundle)},
        unavailable=(
            "r1-input-replay",
            "r2-checkpoint-replay",
            "r3-native-reverse-debug",
            "replay-bundle-signing",
            "replay-bundle-encryption",
            "replay-bundle-retention-policy",
        ),
        warnings=_debug_sanitization_warnings(sanitization),
    )


def correlate_debug_events(
    inputs: JsonObject, runtime_scope: TrustedRuntimeScope
) -> CapabilityOutcome:
    events, sanitization = _sanitized_debug_events(
        inputs, runtime_scope=runtime_scope
    )
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    gaps: list[dict[str, Any]] = []
    for event in events:
        payload = event["payload"]
        correlation = (
            payload.get("trace_id")
            or payload.get("correlation_id")
            or event.get("traceparent")
        )
        if not correlation:
            gaps.append(
                {"event_id": event.get("event_id"), "reason": "MISSING_CORRELATION_ID"}
            )
            continue
        groups[str(correlation)].append(event)
    timelines = [
        {
            "correlation_id": key,
            "events": sorted(
                value,
                key=lambda item: (
                    str(item["occurred_at"]),
                    int(item.get("sequence", 0)),
                ),
            ),
        }
        for key, value in sorted(groups.items())
    ]
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "DEBUG_EVENTS_CORRELATED",
        {
            "timelines": timelines,
            "causal_gaps": gaps,
            "distributed_pause_performed": False,
        },
        unavailable=("distributed-debug-controller", "dual-run-runtime"),
        warnings=_debug_sanitization_warnings(sanitization),
    )


__all__ = ["CapabilityOutcome"]
