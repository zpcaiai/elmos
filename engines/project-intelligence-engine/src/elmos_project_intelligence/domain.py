"""Deterministic bounded operations for the fifty Project Intelligence Skills.

These operations consume only caller-supplied, already-authorized local data.
They never execute repository code, invoke a provider, mutate Git, start a
debug adapter, deploy infrastructure, or claim certification.  Each function
implements a distinct local analysis, artifact, policy, or planning contract;
shared helpers only normalize immutable inputs.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import math
from pathlib import PurePosixPath
import re
from typing import Any

from .canonical import canonical_digest, validate_digest


JsonObject = Mapping[str, Any]


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
_DEBUG_INLINE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|secret|authorization)\b(\s*[:=]\s*)"
    r"(?:bearer\s+)?(?:[\"'][^\"'\r\n]{1,4096}[\"']|[^\s,;}\]]{8,4096})"
)
_DEBUG_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,4096}")
_CORRELATION_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "sequence",
        "kind",
        "thread_id",
        "frame",
        "trace_id",
        "correlation_id",
        "timestamp",
        "service",
        "component",
        "parent_id",
        "span_id",
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
        redacted_text = _DEBUG_INLINE_SECRET.sub(r"\1\2[REDACTED]", sanitized_text)
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
    allowed_fields: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    events = _records(inputs, "debug_events")
    if len(events) > _DEBUG_MAX_EVENTS:
        raise ValueError("debug event count exceeds the configured hard limit")
    stats: Counter[str] = Counter()
    sanitized: list[dict[str, Any]] = []
    for event in events:
        selected = event
        if allowed_fields is not None:
            selected = {
                key: value for key, value in event.items() if key in allowed_fields
            }
            stats["nonessential_fields_omitted"] += len(event) - len(selected)
        clean = _sanitize_debug_value(selected, depth=0, stats=stats)
        if not isinstance(clean, dict):
            raise ValueError("sanitized debug event must remain an object")
        sanitized.append(clean)
    return sanitized, stats


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


def _symbols(files: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
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
    for file in files:
        for line_number, line in enumerate(str(file["text"]).splitlines(), 1):
            for kind, pattern in patterns:
                match = pattern.search(line)
                if match:
                    symbol = match.group(1)
                    stable_id = canonical_digest(
                        {
                            "path": file["path"],
                            "kind": kind,
                            "name": symbol,
                            "line": line_number,
                        }
                    )
                    values.append(
                        {
                            "id": stable_id,
                            "path": file["path"],
                            "line": line_number,
                            "kind": kind,
                            "name": symbol,
                            "language": _language(str(file["path"])),
                        }
                    )
                    break
    return values


def _imports(files: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    patterns = (
        re.compile(r"^\s*from\s+([\w.]+)\s+import\s+"),
        re.compile(r"^\s*import\s+([\w.]+)"),
        re.compile(r"(?:import|require)\s*\(?[\"']([^\"']+)[\"']"),
        re.compile(r"^\s*use\s+([\w:]+)"),
    )
    edges: list[dict[str, Any]] = []
    for file in files:
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
                        }
                    )
                    break
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
            "BLOCKED", "DEPENDENCY_CYCLE_REJECTED", {"requested_skills": requested}
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
        return _outcome("BLOCKED", "EXPLANATION_TARGET_NOT_FOUND", {"path": target})
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
    files = _files(inputs)
    imports = _imports(files)
    flows = [
        {
            "step": index,
            "from": edge["from"],
            "to": edge["to"],
            "confidence": "INFERRED",
        }
        for index, edge in enumerate(imports, 1)
    ]
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


def compile_diagram_spec(inputs: JsonObject) -> CapabilityOutcome:
    nodes, edges = _graph(inputs)
    spec = {
        "schema_version": "elmos.diagram.v1",
        "diagram_type": str(inputs.get("diagram_type", "component")),
        "nodes": [
            {
                "id": str(node.get("id", canonical_digest(node))),
                "label": str(node.get("name", node.get("id", "node"))),
                "kind": str(node.get("kind", "component")),
            }
            for node in nodes
        ],
        "edges": [
            {
                "from": str(edge.get("from")),
                "to": str(edge.get("to")),
                "kind": str(edge.get("kind", "relates")),
            }
            for edge in edges
        ],
    }
    return _outcome(
        "LOCAL_EXECUTED",
        "DIAGRAM_SPEC_COMPILED",
        {"diagram_spec": spec, "digest": canonical_digest(spec)},
    )


def render_diagram(inputs: JsonObject) -> CapabilityOutcome:
    spec = inputs.get("diagram_spec")
    if not isinstance(spec, Mapping):
        nodes, edges = _graph(inputs)
    else:
        nodes = _records(spec, "nodes")
        edges = _records(spec, "edges")
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
        lines.append(f'  {identifier}["{label}"]')
    for edge in edges:
        source = ids.get(str(edge.get("from")))
        target = ids.get(str(edge.get("to")))
        if source and target:
            lines.append(f"  {source} --> {target}")
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
        source, source_normalized = _safe_markdown_text(edge.get("from"))
        target, target_normalized = _safe_markdown_text(edge.get("to"))
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
                f"{edge.get('from')} -> {edge.get('to')}" for edge in edges[:8]
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
        index.append(
            {
                "artifact_id": artifact_id,
                "digest": normalized_digest,
                "media_type": str(item.get("media_type", "application/octet-stream")),
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
        reverse[str(edge.get("to"))].add(str(edge.get("from")))
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


def cache_analysis_stage(inputs: JsonObject) -> CapabilityOutcome:
    stage = _identifier(inputs.get("stage", "analysis"), "stage")
    input_digest = canonical_digest(inputs.get("stage_inputs", {}))
    existing = inputs.get("existing_cache_key")
    key = canonical_digest(
        {"stage": stage, "inputs": input_digest, "engine": "project-intelligence-v1"}
    )
    return _outcome(
        "LOCAL_EXECUTED",
        "ANALYSIS_CACHE_KEY_RESOLVED",
        {
            "cache_key": key,
            "hit": existing == key,
            "stage": stage,
            "input_digest": input_digest,
        },
    )


def validate_artifact_version_proposal(inputs: JsonObject) -> CapabilityOutcome:
    artifact_id = _identifier(inputs.get("artifact_id", "artifact"), "artifact_id")
    content = inputs.get("content")
    locked = bool(inputs.get("human_locked", False))
    proposed = inputs.get("proposed_content", content)
    previous_version = inputs.get("previous_version", 0)
    if type(previous_version) is not int or previous_version < 0:
        raise ValueError("previous_version must be a non-negative integer")
    if locked and proposed != content:
        return _outcome(
            "BLOCKED",
            "HUMAN_LOCK_PREVENTED_OVERWRITE",
            {
                "artifact_id": artifact_id,
                "caller_reported_human_locked": True,
                "authoritative_lock_verified": False,
                "version_persisted": False,
            },
        )
    version = previous_version + 1
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "ARTIFACT_VERSION_PROPOSAL_VALIDATED",
        {
            "artifact_id": artifact_id,
            "proposed_version": version,
            "content_digest": canonical_digest(proposed),
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
    target = Decimal(str(inputs.get("success_rate_target", "0.99")))
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


def estimate_runtime_cost(inputs: JsonObject) -> CapabilityOutcome:
    files = _files(inputs)
    workers = max(1, min(int(inputs.get("workers", 1)), 128))
    total_bytes = sum(int(file["bytes"]) for file in files)
    parse_seconds = Decimal(total_bytes) / Decimal(250_000)
    graph_seconds = Decimal(len(files)) * Decimal("0.002")
    p50 = (
        (parse_seconds + graph_seconds) / Decimal(min(workers, max(len(files), 1)))
    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    p90 = max(p50, p50 * Decimal("1.8")).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    return _outcome(
        "LOCAL_EXECUTED",
        "RUNTIME_COST_ESTIMATED",
        {
            "system_wall_clock_eta_p50_seconds": format(p50, "f"),
            "system_wall_clock_eta_p90_seconds": format(p90, "f"),
            "human_review_effort_seconds": int(
                inputs.get("human_review_effort_seconds", 0)
            ),
            "model_version": "local-linear-v1",
            "currency_cost": None,
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


def plan_debug_session(inputs: JsonObject) -> CapabilityOutcome:
    revision = _identifier(inputs.get("revision", "local-content"), "revision")
    policy = {
        "read_only_source": True,
        "network": "deny",
        "evaluate": "side-effect-free-only",
        "ttl_seconds": min(int(inputs.get("ttl_seconds", 900)), 3600),
        "revision": revision,
    }
    return _outcome(
        "PLANNING_ONLY",
        "DEBUG_SANDBOX_SESSION_PLANNED",
        {"policy": policy, "sandbox_started": False},
        unavailable=("container-or-microvm-runner", "debug-adapter-process"),
    )


def reduce_debug_view(inputs: JsonObject) -> CapabilityOutcome:
    events, sanitization = _sanitized_debug_events(
        inputs,
        allowed_fields=_CORRELATION_EVENT_FIELDS,
    )
    ordered = sorted(
        events,
        key=lambda item: (int(item.get("sequence", 0)), str(item.get("event_id", ""))),
    )
    threads: dict[str, dict[str, Any]] = {}
    for event in ordered:
        thread = str(event.get("thread_id", "main"))
        threads[thread] = {
            "last_event": event.get("kind"),
            "sequence": event.get("sequence"),
            "frame": event.get("frame"),
        }
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "DEBUG_VIEW_STATE_REDUCED",
        {"threads": threads, "event_count": len(ordered), "ui_rendered": False},
        unavailable=("browser-debug-workbench",),
        warnings=_debug_sanitization_warnings(sanitization),
    )


def build_debug_mission(inputs: JsonObject) -> CapabilityOutcome:
    frames = _records(inputs, "frames")
    mission = [
        {
            "step": index,
            "frame_id": frame.get("frame_id"),
            "prompt": f"Inspect {frame.get('function', 'frame')} and cite its evidence.",
            "evidence_ref": frame.get("evidence_ref"),
        }
        for index, frame in enumerate(frames, 1)
    ]
    return _outcome(
        "PARTIAL_LOCAL_EXECUTED",
        "DEBUG_LEARNING_MISSION_BUILT",
        {"mission": mission, "model_used": False, "side_effects": False},
        unavailable=("learning-model-adapter", "interactive-debug-ui"),
    )


def build_replay_bundle(inputs: JsonObject) -> CapabilityOutcome:
    events, sanitization = _sanitized_debug_events(inputs)
    redacted: list[dict[str, Any]] = []
    previous = None
    for event in sorted(events, key=lambda item: int(item.get("sequence", 0))):
        clean = dict(event)
        clean["previous_event_digest"] = previous
        clean["event_digest"] = canonical_digest(clean)
        previous = clean["event_digest"]
        redacted.append(clean)
    bundle = {
        "replay_level": "R0",
        "events": redacted,
        "terminal_digest": previous,
        "native_reverse_debug": False,
        "redaction": {
            "policy": "recursive-field-policy-v1",
            "sensitive_fields_omitted": sanitization["sensitive_fields_omitted"],
            "inline_secret_values_redacted": sanitization[
                "inline_secret_values_redacted"
            ],
            "strings_truncated": sanitization["strings_truncated"],
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
        ),
        warnings=_debug_sanitization_warnings(sanitization),
    )


def correlate_debug_events(inputs: JsonObject) -> CapabilityOutcome:
    events, sanitization = _sanitized_debug_events(
        inputs,
        allowed_fields=_CORRELATION_EVENT_FIELDS,
    )
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    gaps: list[dict[str, Any]] = []
    for event in events:
        correlation = event.get("trace_id") or event.get("correlation_id")
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
                    str(item.get("timestamp", "")),
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
