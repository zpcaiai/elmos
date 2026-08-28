"""Typed, source-linked repository semantic compilation.

Only frontends that produce a compiler or parser result may be authoritative.
The built-in Python frontend uses CPython's AST.  JSON and TOML use their
standard-library parsers.  YAML remains unsupported until an alias-safe,
bounded, JSON-compatible adapter is installed.  Other language profiles remain
``UNSUPPORTED`` until an exact, digest-bound compiler adapter is registered;
lexical guesses are never upgraded to semantic evidence.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
from pathlib import PurePosixPath
import tomllib
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Protocol, Sequence
import unicodedata

from .repository import FileEvidence, RepositoryEvidenceGraph


PROFILE_VERSION = "3.0.0"


class CapabilityState(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    name: str
    version: str
    extensions: tuple[str, ...]
    semantic_frontend: str
    integer_model: str
    null_model: str
    exception_model: str
    resource_model: str
    concurrency_model: str
    dynamic_boundaries: tuple[str, ...]
    proof_encodings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "extensions": list(self.extensions),
            "semantic_frontend": self.semantic_frontend,
            "integer_model": self.integer_model,
            "null_model": self.null_model,
            "exception_model": self.exception_model,
            "resource_model": self.resource_model,
            "concurrency_model": self.concurrency_model,
            "dynamic_boundaries": list(self.dynamic_boundaries),
            "proof_encodings": list(self.proof_encodings),
        }


def _profile(
    name: str,
    extensions: Sequence[str],
    frontend: str,
    integer: str,
    nulls: str,
    exceptions: str,
    resources: str,
    concurrency: str,
    dynamic: Sequence[str] = (),
    proofs: Sequence[str] = ("smt", "differential"),
) -> LanguageProfile:
    return LanguageProfile(
        name,
        PROFILE_VERSION,
        tuple(extensions),
        frontend,
        integer,
        nulls,
        exceptions,
        resources,
        concurrency,
        tuple(dynamic),
        tuple(proofs),
    )


LANGUAGE_PROFILES: dict[str, LanguageProfile] = {
    "java": _profile("java", (".java",), "javac compiler bridge", "fixed-width signed wrap", "nullable references", "checked and unchecked", "gc/autocloseable", "JMM threads/futures", ("reflection", "JNI")),
    "kotlin": _profile("kotlin", (".kt", ".kts"), "Kotlin Analysis API bridge", "fixed-width signed wrap", "typed nullable", "unchecked", "gc/use scope", "JMM coroutines", ("reflection", "JNI")),
    "csharp": _profile("csharp", (".cs",), "Roslyn semantic model", "fixed-width checked-context dependent", "nullable annotations", "unchecked", "gc/IDisposable", ".NET memory model/tasks", ("reflection", "PInvoke")),
    "typescript": _profile("typescript", (".ts", ".tsx"), "TypeScript compiler API", "IEEE-754 number/bigint", "null and undefined", "unchecked", "gc", "event loop/promises", ("any", "eval", "dynamic import")),
    "javascript": _profile("javascript", (".js", ".jsx", ".mjs", ".cjs"), "JavaScript parser plus runtime evidence", "IEEE-754 number/bigint", "null and undefined", "unchecked", "gc", "event loop/promises", ("eval", "prototype mutation", "dynamic import")),
    "python": _profile("python", (".py", ".pyi"), "CPython ast plus optional type/runtime evidence", "arbitrary precision", "None/open world", "unchecked", "gc/context manager", "GIL implementation dependent/asyncio", ("eval", "reflection", "monkey patching")),
    "rust": _profile("rust", (".rs",), "rustc HIR/MIR bridge", "fixed-width debug/release overflow dependent", "Option", "Result/panic", "ownership/RAII", "Rust memory model/async", ("unsafe", "FFI", "macros")),
    "go": _profile("go", (".go",), "go/packages and go/types", "fixed-width wrap", "nil", "panic/error values", "gc/defer", "goroutines/channels", ("reflection", "cgo")),
    "c": _profile("c", (".c", ".h"), "Clang AST/CFG", "fixed-width with undefined signed overflow", "null pointer", "return/longjmp", "manual", "C memory model/threads", ("undefined behavior", "preprocessor", "ABI")),
    "cpp": _profile("cpp", (".cc", ".cpp", ".cxx", ".hpp"), "Clang AST/CFG", "fixed-width with undefined signed overflow", "pointer/optional", "exceptions/result", "RAII/manual", "C++ memory model/coroutines", ("undefined behavior", "templates", "macros", "ABI")),
    "objective-c": _profile("objective-c", (".m", ".mm"), "Clang AST/CFG", "fixed-width C semantics", "nullable annotations", "exceptions/NSError", "ARC/manual", "C/Objective-C memory model/GCD", ("runtime messaging", "C ABI")),
    "swift": _profile("swift", (".swift",), "SwiftSyntax plus SIL", "fixed-width trapping", "Optional", "throws/Result", "ARC", "Swift concurrency/actors", ("Objective-C bridge", "unsafe")),
    "dart": _profile("dart", (".dart",), "Dart analyzer kernel", "arbitrary precision on VM/JS target variance", "sound nullable types", "unchecked", "gc", "isolates/futures", ("mirrors", "platform channels")),
    "php": _profile("php", (".php",), "php-parser plus runtime evidence", "platform-width integer", "null/dynamic", "unchecked", "gc", "request/process/fibers", ("dynamic calls", "eval", "extensions")),
    "sql": _profile("sql", (".sql",), "dialect-specific parser and engine catalog", "exact/provider types", "SQL NULL/three-valued logic", "provider exceptions", "transaction/cursor", "transactions/isolation/locks", ("dynamic SQL", "extensions", "collation"), ("relational", "smt", "differential")),
}


@dataclass(frozen=True, slots=True)
class FrameworkProfile:
    name: str
    version: str
    languages: tuple[str, ...]
    semantic_surfaces: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "languages": list(self.languages),
            "semantic_surfaces": list(self.semantic_surfaces),
        }


FRAMEWORK_PROFILES: dict[str, FrameworkProfile] = {
    "servlet-jsp": FrameworkProfile("servlet-jsp", "3.0.0", ("java",), ("routes", "filters", "sessions", "views")),
    "struts1": FrameworkProfile("struts1", "3.0.0", ("java",), ("actions", "forwards", "forms", "plugins")),
    "struts2": FrameworkProfile("struts2", "3.0.0", ("java",), ("actions", "interceptors", "value-stack", "results")),
    "spring-boot-4": FrameworkProfile("spring-boot-4", "4.x", ("java", "kotlin"), ("routes", "binding", "DI", "security", "transactions", "lifecycle")),
    "dotnet-aspnet": FrameworkProfile("dotnet-aspnet", "3.0.0", ("csharp",), ("routes", "middleware", "DI", "identity", "persistence")),
    "node-web": FrameworkProfile("node-web", "3.0.0", ("typescript", "javascript"), ("routes", "middleware", "async", "serialization")),
    "react-vue": FrameworkProfile("react-vue", "3.0.0", ("typescript", "javascript"), ("components", "routes", "state", "rendering", "hydration")),
    "flutter": FrameworkProfile("flutter", "3.0.0", ("dart",), ("widgets", "navigation", "state", "platform-channels")),
    "miniapp": FrameworkProfile("miniapp", "3.0.0", ("typescript", "javascript"), ("pages", "lifecycle", "permissions", "platform-api")),
}


@dataclass(frozen=True, slots=True)
class FrontendCapability:
    language: str
    provider: str
    state: CapabilityState
    authoritative: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "provider": self.provider,
            "state": self.state.value,
            "authoritative": self.authoritative,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SourceSpan:
    path: str
    start_byte: int
    end_byte: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "start_line": self.start_line,
            "start_column": self.start_column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


@dataclass(frozen=True, slots=True)
class SourceMapEntry:
    node_id: str
    span: SourceSpan
    source_digest: str
    segment_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "span": self.span.to_dict(),
            "source_digest": self.source_digest,
            "segment_digest": self.segment_digest,
        }


@dataclass(frozen=True, slots=True)
class SemanticNode:
    id: str
    kind: str
    name: str
    language: str
    source_span: SourceSpan
    symbol_identity: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    authoritative: bool = False
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "language": self.language,
            "source_span": self.source_span.to_dict(),
            "symbol_identity": self.symbol_identity,
            "attributes": dict(self.attributes),
            "authoritative": self.authoritative,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class SemanticEdge:
    source: str
    target: str
    kind: str
    authoritative: bool
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "authoritative": self.authoritative,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class SemanticGap:
    id: str
    family: str
    severity: str
    description: str
    source_profile: str
    target_profile: str | None
    policy: str
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family,
            "severity": self.severity,
            "description": self.description,
            "source_profile": self.source_profile,
            "target_profile": self.target_profile,
            "policy": self.policy,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class SemanticShard:
    path: str
    language: str
    profile_version: str
    source_digest: str
    shard_digest: str
    capability: FrontendCapability
    nodes: tuple[SemanticNode, ...]
    edges: tuple[SemanticEdge, ...]
    source_map: tuple[SourceMapEntry, ...]
    gaps: tuple[SemanticGap, ...]
    dependencies: tuple[str, ...]
    dependency_fingerprint: str
    invalidation_dependencies: tuple[str, ...]

    @property
    def authoritative(self) -> bool:
        return self.capability.authoritative and all(node.authoritative for node in self.nodes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "profile_version": self.profile_version,
            "source_digest": self.source_digest,
            "shard_digest": self.shard_digest,
            "capability": self.capability.to_dict(),
            "authoritative": self.authoritative,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "source_map": [entry.to_dict() for entry in self.source_map],
            "gaps": [gap.to_dict() for gap in self.gaps],
            "dependencies": list(self.dependencies),
            "dependency_fingerprint": self.dependency_fingerprint,
            "invalidation_dependencies": list(self.invalidation_dependencies),
        }


@dataclass(frozen=True, slots=True)
class SemanticBundle:
    snapshot_id: str
    bundle_digest: str
    shards: tuple[SemanticShard, ...]
    invalidated_paths: tuple[str, ...]
    reused_paths: tuple[str, ...]
    completeness: Mapping[str, Any]

    def shard(self, path: str) -> SemanticShard | None:
        return next((item for item in self.shards if item.path == path), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_version": "elmos.ai/v3",
            "kind": "RepositorySemanticIR",
            "snapshot_id": self.snapshot_id,
            "bundle_digest": self.bundle_digest,
            "invalidated_paths": list(self.invalidated_paths),
            "reused_paths": list(self.reused_paths),
            "completeness": dict(self.completeness),
            "shards": [shard.to_dict() for shard in self.shards],
        }


class SemanticFrontend(Protocol):
    capability: FrontendCapability

    def compile(self, evidence: FileEvidence) -> SemanticShard: ...


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _full_span(evidence: FileEvidence) -> SourceSpan:
    text = evidence.content.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    if not lines:
        return SourceSpan(evidence.path, 0, 0, 1, 0, 1, 0)
    last = lines[-1].rstrip("\r\n")
    return SourceSpan(
        evidence.path,
        0,
        len(evidence.content),
        1,
        0,
        len(lines),
        len(last.encode("utf-8")),
    )


def _line_offsets(content: bytes) -> list[int]:
    offsets = [0]
    for index, byte in enumerate(content):
        if byte == 10:
            offsets.append(index + 1)
    return offsets


def _ast_span(evidence: FileEvidence, node: ast.AST, offsets: Sequence[int]) -> SourceSpan:
    start_line = int(getattr(node, "lineno", 1))
    start_column = int(getattr(node, "col_offset", 0))
    end_line = int(getattr(node, "end_lineno", start_line))
    end_column = int(getattr(node, "end_col_offset", start_column))
    start_base = offsets[min(max(start_line - 1, 0), len(offsets) - 1)]
    end_base = offsets[min(max(end_line - 1, 0), len(offsets) - 1)]
    return SourceSpan(
        evidence.path,
        min(start_base + start_column, len(evidence.content)),
        min(end_base + end_column, len(evidence.content)),
        start_line,
        start_column,
        end_line,
        end_column,
    )


def _node_name(node: ast.AST, path: str) -> str:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return getattr(node, "module", None) or ",".join(alias.name for alias in node.names)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.arg):
        return node.arg
    return path if isinstance(node, ast.Module) else type(node).__name__


def _ast_kind(node: ast.AST) -> str:
    if isinstance(node, ast.Module):
        return "module"
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, ast.AsyncFunctionDef):
        return "async-function"
    if isinstance(node, ast.FunctionDef):
        return "function"
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return "import"
    if isinstance(node, ast.Raise):
        return "raise"
    if isinstance(node, ast.Await):
        return "await"
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return "resource-scope"
    if isinstance(node, ast.Try):
        return "exception-scope"
    if isinstance(node, ast.Call):
        return "call"
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        return "assignment"
    return type(node).__name__.lower()


class PythonAstFrontend:
    capability = FrontendCapability(
        "python", "cpython.ast", CapabilityState.SUPPORTED, True
    )

    def compile(self, evidence: FileEvidence) -> SemanticShard:
        try:
            text = evidence.content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            return _unsupported_shard(evidence, "python", "source is not valid UTF-8", str(exc))
        try:
            tree = ast.parse(text, filename=evidence.path, type_comments=True)
        except SyntaxError as exc:
            return _unsupported_shard(
                evidence,
                "python",
                "CPython parser rejected source",
                f"{exc.msg} at {exc.lineno}:{exc.offset}",
            )

        offsets = _line_offsets(evidence.content)
        nodes: list[SemanticNode] = []
        edges: list[SemanticEdge] = []
        maps: list[SourceMapEntry] = []
        identities: dict[int, str] = {}
        counter: MutableMapping[str, int] = {}

        def visit(node: ast.AST, parent: str | None, scope: tuple[str, ...]) -> None:
            span = _full_span(evidence) if isinstance(node, ast.Module) else _ast_span(evidence, node, offsets)
            kind = _ast_kind(node)
            name = _node_name(node, evidence.path)
            next_scope = scope
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                next_scope = (*scope, node.name)
            symbol = f"python:{evidence.path}:{'.'.join(next_scope) or '<module>'}:{kind}:{name}"
            base = f"{symbol}:{span.start_byte}:{span.end_byte}"
            duplicate = counter.get(base, 0)
            counter[base] = duplicate + 1
            node_id = f"sem:{hashlib.sha256(f'{base}:{duplicate}'.encode()).hexdigest()}"
            identities[id(node)] = node_id
            attributes: dict[str, Any] = {}
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                attributes = {
                    "arguments": [argument.arg for argument in node.args.args],
                    "decorators": [ast.dump(item, include_attributes=False) for item in node.decorator_list],
                    "async": isinstance(node, ast.AsyncFunctionDef),
                }
            elif isinstance(node, ast.ClassDef):
                attributes = {
                    "bases": [ast.dump(item, include_attributes=False) for item in node.bases],
                    "decorators": [ast.dump(item, include_attributes=False) for item in node.decorator_list],
                }
            elif isinstance(node, ast.Import):
                attributes = {"modules": [alias.name for alias in node.names]}
            elif isinstance(node, ast.ImportFrom):
                attributes = {
                    "module": node.module or "",
                    "level": node.level,
                    "names": [alias.name for alias in node.names],
                }
            semantic_node = SemanticNode(
                node_id,
                kind,
                name,
                "python",
                span,
                symbol,
                attributes,
                True,
                (evidence.evidence_id,),
            )
            nodes.append(semantic_node)
            segment = evidence.content[span.start_byte : span.end_byte]
            maps.append(
                SourceMapEntry(
                    node_id,
                    span,
                    evidence.digest,
                    hashlib.sha256(segment).hexdigest(),
                )
            )
            if parent is not None:
                edges.append(SemanticEdge(parent, node_id, "contains", True, (evidence.evidence_id,)))
            for child in ast.iter_child_nodes(node):
                visit(child, node_id, next_scope)

        visit(tree, None, ())
        dependencies: set[str] = set()
        for node in ast.walk(tree):
            source_id = identities[id(node)]
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dependencies.add(alias.name)
                    edges.append(
                        SemanticEdge(source_id, f"external:python:{alias.name}", "imports", True, (evidence.evidence_id,))
                    )
            elif isinstance(node, ast.ImportFrom):
                module = ("." * node.level) + (node.module or "")
                dependencies.add(module)
                edges.append(
                    SemanticEdge(source_id, f"external:python:{module}", "imports", True, (evidence.evidence_id,))
                )
            elif isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name):
                    target = function.id
                elif isinstance(function, ast.Attribute):
                    target = function.attr
                else:
                    target = "<dynamic>"
                edges.append(
                    SemanticEdge(source_id, f"call-target:python:{target}", "calls", target != "<dynamic>", (evidence.evidence_id,))
                )
        return _finalize_shard(
            evidence,
            "python",
            self.capability,
            nodes,
            edges,
            maps,
            (),
            tuple(sorted(dependencies)),
            (),
        )


class JsonFrontend:
    capability = FrontendCapability("json", "python.json", CapabilityState.SUPPORTED, True)

    def compile(self, evidence: FileEvidence) -> SemanticShard:
        duplicates: list[str] = []

        def preserve_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            normalized: set[str] = set()
            for key, value in pairs:
                canonical_key = unicodedata.normalize("NFC", key)
                if key != canonical_key:
                    duplicates.append(f"non-NFC:{key}")
                if key in result or canonical_key in normalized:
                    duplicates.append(key)
                result[key] = value
                normalized.add(canonical_key)
            return result

        def reject_constant(value: str) -> Any:
            raise ValueError(f"non-finite JSON number is forbidden: {value}")

        try:
            value = json.loads(
                evidence.content.decode("utf-8"),
                object_pairs_hook=preserve_pairs,
                parse_constant=reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return _unsupported_shard(evidence, "json", "JSON parser rejected source", str(exc))
        gap_items = tuple(
            _gap(evidence, "duplicate-key", "critical", f"duplicate JSON key: {key}", "json", None)
            for key in sorted(set(duplicates))
        )
        authoritative = not duplicates
        return _structured_shard(evidence, "json", self.capability, value, authoritative, gap_items)


class TomlFrontend:
    capability = FrontendCapability("toml", "python.tomllib", CapabilityState.SUPPORTED, True)

    def compile(self, evidence: FileEvidence) -> SemanticShard:
        try:
            value = tomllib.loads(evidence.content.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            return _unsupported_shard(evidence, "toml", "TOML parser rejected source", str(exc))
        return _structured_shard(evidence, "toml", self.capability, value, True, ())


class YamlFrontend:
    def __init__(self) -> None:
        self.capability = FrontendCapability(
            "yaml",
            "strict-json-compatible-yaml-adapter",
            CapabilityState.UNSUPPORTED,
            False,
            (
                "a bounded alias-safe, JSON-compatible YAML adapter with NFC "
                "key enforcement is not installed"
            ),
        )

    def compile(self, evidence: FileEvidence) -> SemanticShard:
        return _unsupported_shard(
            evidence,
            "yaml",
            "strict bounded YAML frontend unavailable",
            self.capability.reason,
        )


def _yaml_duplicate_keys(node: Any) -> set[str]:
    """Detect duplicate mapping keys in a composed PyYAML node tree."""

    if node is None:
        return set()
    duplicates: set[str] = set()
    node_kind = getattr(node, "id", None)
    value = getattr(node, "value", ())
    if node_kind == "mapping":
        seen: set[str] = set()
        for key_node, value_node in value:
            key = f"{getattr(key_node, 'tag', '')}:{getattr(key_node, 'value', '')}"
            if key in seen:
                duplicates.add(str(getattr(key_node, "value", key)))
            seen.add(key)
            duplicates.update(_yaml_duplicate_keys(key_node))
            duplicates.update(_yaml_duplicate_keys(value_node))
    elif node_kind == "sequence":
        for child in value:
            duplicates.update(_yaml_duplicate_keys(child))
    return duplicates


class ExternalFrontend:
    """Non-authoritative callback bridge pending typed frontend attestation."""

    def __init__(
        self,
        language: str,
        provider: str,
        callback: Callable[[FileEvidence], Mapping[str, Any]],
    ) -> None:
        if language not in LANGUAGE_PROFILES:
            raise ValueError(f"unknown language profile: {language}")
        self.language = language
        self.callback = callback
        self.capability = FrontendCapability(
            language,
            provider,
            CapabilityState.PARTIAL,
            False,
            (
                "external callback has no durable executable/toolchain/manifest/"
                "environment attestation"
            ),
        )

    def compile(self, evidence: FileEvidence) -> SemanticShard:
        payload = self.callback(evidence)
        if payload.get("source_digest") != evidence.digest:
            raise ValueError("external frontend result is not bound to the exact source digest")
        if payload.get("language") != self.language:
            raise ValueError("external frontend language mismatch")
        raw_nodes = payload.get("nodes")
        if not isinstance(raw_nodes, list):
            raise ValueError("external frontend must return typed nodes")
        nodes: list[SemanticNode] = []
        maps: list[SourceMapEntry] = []
        for index, item in enumerate(raw_nodes):
            if not isinstance(item, Mapping):
                raise ValueError("external frontend node must be an object")
            start = int(item["start_byte"])
            end = int(item["end_byte"])
            if start < 0 or end < start or end > evidence.size:
                raise ValueError("external frontend returned an invalid source span")
            span = SourceSpan(evidence.path, start, end, int(item.get("start_line", 1)), int(item.get("start_column", 0)), int(item.get("end_line", 1)), int(item.get("end_column", 0)))
            node_id = str(item.get("id") or f"sem:{_digest([evidence.digest, index, start, end])}")
            node = SemanticNode(node_id, str(item["kind"]), str(item.get("name", item["kind"])), self.language, span, str(item.get("symbol_identity", node_id)), dict(item.get("attributes", {})), True, (evidence.evidence_id,))
            nodes.append(node)
            maps.append(SourceMapEntry(node_id, span, evidence.digest, hashlib.sha256(evidence.content[start:end]).hexdigest()))
        raw_edges = payload.get("edges", [])
        edges = tuple(SemanticEdge(str(item["source"]), str(item["target"]), str(item["kind"]), True, (evidence.evidence_id,)) for item in raw_edges)
        gaps = (
            _gap(
                evidence,
                "frontend-attestation-missing",
                "critical",
                "external frontend result is self-attested and non-authoritative",
                self.language,
                None,
            ),
        )
        return _finalize_shard(evidence, self.language, self.capability, nodes, edges, maps, gaps, tuple(str(item) for item in payload.get("dependencies", [])), ())


def _structured_shard(
    evidence: FileEvidence,
    language: str,
    capability: FrontendCapability,
    value: Any,
    authoritative: bool,
    gaps: Sequence[SemanticGap],
) -> SemanticShard:
    span = _full_span(evidence)
    node_id = f"sem:{_digest([language, evidence.path, evidence.digest])}"
    node = SemanticNode(
        node_id,
        "document",
        evidence.path,
        language,
        span,
        f"{language}:{evidence.path}:document",
        {"value": value},
        authoritative,
        (evidence.evidence_id,),
    )
    source_map = SourceMapEntry(node_id, span, evidence.digest, evidence.digest)
    actual_capability = capability if authoritative else replace(capability, state=CapabilityState.PARTIAL, authoritative=False, reason="ambiguous source structure")
    return _finalize_shard(evidence, language, actual_capability, (node,), (), (source_map,), gaps, (), ())


def _unsupported_shard(evidence: FileEvidence, language: str, description: str, detail: str) -> SemanticShard:
    profile = LANGUAGE_PROFILES.get(language)
    provider = profile.semantic_frontend if profile else f"{language}-parser"
    capability = FrontendCapability(language, provider, CapabilityState.UNSUPPORTED, False, detail)
    span = _full_span(evidence)
    node_id = f"raw:{_digest([language, evidence.path, evidence.digest])}"
    node = SemanticNode(node_id, "raw-source", evidence.path, language, span, f"{language}:{evidence.path}:raw", {"reason": detail}, False, (evidence.evidence_id,))
    mapping = SourceMapEntry(node_id, span, evidence.digest, evidence.digest)
    gap = _gap(evidence, "frontend-unavailable", "critical", description + (f": {detail}" if detail else ""), language, None)
    return _finalize_shard(evidence, language, capability, (node,), (), (mapping,), (gap,), (), ())


def _gap(
    evidence: FileEvidence,
    family: str,
    severity: str,
    description: str,
    source_profile: str,
    target_profile: str | None,
) -> SemanticGap:
    identity = _digest([evidence.digest, family, description, source_profile, target_profile])
    return SemanticGap(f"gap:sha256:{identity}", family, severity, description, source_profile, target_profile, "BLOCK" if severity == "critical" else "REVIEW", (evidence.evidence_id,))


def _finalize_shard(
    evidence: FileEvidence,
    language: str,
    capability: FrontendCapability,
    nodes: Iterable[SemanticNode],
    edges: Iterable[SemanticEdge],
    source_map: Iterable[SourceMapEntry],
    gaps: Iterable[SemanticGap],
    dependencies: Sequence[str],
    invalidation_dependencies: Sequence[str],
) -> SemanticShard:
    node_items = tuple(nodes)
    edge_items = tuple(sorted(edges, key=lambda item: (item.source, item.target, item.kind)))
    map_items = tuple(sorted(source_map, key=lambda item: (item.span.start_byte, item.span.end_byte, item.node_id)))
    gap_items = tuple(sorted(gaps, key=lambda item: item.id))
    deps = tuple(sorted(set(dependencies)))
    invalidation = tuple(sorted(set(invalidation_dependencies)))
    fingerprint = _digest(invalidation)
    body = {
        "path": evidence.path,
        "language": language,
        "profile_version": PROFILE_VERSION,
        "source_digest": evidence.digest,
        "capability": capability.to_dict(),
        "nodes": [item.to_dict() for item in node_items],
        "edges": [item.to_dict() for item in edge_items],
        "source_map": [item.to_dict() for item in map_items],
        "gaps": [item.to_dict() for item in gap_items],
        "dependencies": deps,
        "invalidation_dependencies": invalidation,
    }
    return SemanticShard(evidence.path, language, PROFILE_VERSION, evidence.digest, _digest(body), capability, node_items, edge_items, map_items, gap_items, deps, fingerprint, invalidation)


class SemanticCompiler:
    def __init__(self, external_frontends: Mapping[str, SemanticFrontend] | None = None) -> None:
        self._frontends: dict[str, SemanticFrontend] = {
            "python": PythonAstFrontend(),
            "json": JsonFrontend(),
            "toml": TomlFrontend(),
            "yaml": YamlFrontend(),
        }
        if external_frontends:
            for language, frontend in external_frontends.items():
                self.register_frontend(language, frontend)

    def register_frontend(self, language: str, frontend: SemanticFrontend) -> None:
        if language not in LANGUAGE_PROFILES and language not in {"json", "yaml", "toml"}:
            raise ValueError(f"unknown language: {language}")
        if frontend.capability.language != language:
            raise ValueError("frontend capability language mismatch")
        self._frontends[language] = frontend

    def capabilities(self) -> tuple[FrontendCapability, ...]:
        results: list[FrontendCapability] = []
        for language, profile in sorted(LANGUAGE_PROFILES.items()):
            frontend = self._frontends.get(language)
            results.append(frontend.capability if frontend else FrontendCapability(language, profile.semantic_frontend, CapabilityState.UNSUPPORTED, False, "exact compiler adapter is not registered"))
        for language in ("json", "toml", "yaml"):
            results.append(self._frontends[language].capability)
        return tuple(results)

    def compile(
        self,
        repository: RepositoryEvidenceGraph,
        *,
        previous: SemanticBundle | None = None,
    ) -> SemanticBundle:
        candidates = {
            item.path: item
            for item in repository.files
            if item.language is not None and not item.binary
        }
        invalidated = self.plan_invalidation(repository, previous)
        previous_by_path = {item.path: item for item in previous.shards} if previous else {}
        preliminary: dict[str, SemanticShard] = {}
        reused: list[str] = []
        for path, evidence in sorted(candidates.items()):
            old = previous_by_path.get(path)
            if old and path not in invalidated and old.source_digest == evidence.digest and old.profile_version == PROFILE_VERSION:
                preliminary[path] = old
                reused.append(path)
                continue
            language = evidence.language or "unknown"
            frontend = self._frontends.get(language)
            preliminary[path] = frontend.compile(evidence) if frontend else _unsupported_shard(evidence, language, "exact compiler-grade frontend is unavailable", LANGUAGE_PROFILES.get(language, _profile(language, (), "unregistered", "unknown", "unknown", "unknown", "unknown", "unknown")).semantic_frontend)

        module_paths = _module_path_index(candidates)
        linked: dict[str, SemanticShard] = {}
        for path, shard in sorted(preliminary.items()):
            resolved = _resolve_dependencies(path, shard.language, shard.dependencies, module_paths)
            dependency_evidence = tuple(
                f"{dependency}:{candidates[dependency].digest}"
                for dependency in resolved
                if dependency in candidates
            )
            dependency_fingerprint = _digest(dependency_evidence)
            if shard.invalidation_dependencies == dependency_evidence and shard.dependency_fingerprint == dependency_fingerprint:
                linked[path] = shard
            else:
                body = shard.to_dict()
                body.pop("shard_digest", None)
                body["invalidation_dependencies"] = list(dependency_evidence)
                body["dependency_fingerprint"] = dependency_fingerprint
                linked[path] = replace(shard, shard_digest=_digest(body), dependency_fingerprint=dependency_fingerprint, invalidation_dependencies=dependency_evidence)

        shards = tuple(linked[path] for path in sorted(linked))
        authoritative = sum(item.authoritative for item in shards)
        unsupported = sum(item.capability.state == CapabilityState.UNSUPPORTED for item in shards)
        partial = sum(item.capability.state == CapabilityState.PARTIAL for item in shards)
        parsed_complete = len(shards) == len(candidates)
        candidate_semantics_authoritative = parsed_complete and all(
            item.authoritative
            and item.capability.state == CapabilityState.SUPPORTED
            for item in shards
        )
        semantic_authoritative_complete = (
            repository.whole_repository_complete
            and candidate_semantics_authoritative
        )
        completeness = {
            "eligible_files": len(candidates),
            "compiled_shards": len(shards),
            "authoritative_shards": authoritative,
            "unsupported_shards": unsupported,
            "partial_shards": partial,
            "authoritative_ratio": authoritative / len(shards) if shards else 1.0,
            "repository_declared_scope_complete": repository.declared_scope_complete,
            "repository_whole_complete": repository.whole_repository_complete,
            "parsed_complete": parsed_complete,
            "candidate_semantics_authoritative": candidate_semantics_authoritative,
            "semantic_authoritative_complete": semantic_authoritative_complete,
            "complete": semantic_authoritative_complete,
        }
        bundle_digest = _digest({"snapshot_id": repository.snapshot_id, "shards": [item.shard_digest for item in shards], "completeness": completeness})
        return SemanticBundle(repository.snapshot_id, bundle_digest, shards, tuple(sorted(invalidated & set(candidates))), tuple(sorted(reused)), completeness)

    @staticmethod
    def plan_invalidation(
        repository: RepositoryEvidenceGraph,
        previous: SemanticBundle | None,
    ) -> set[str]:
        current = {item.path: item.digest for item in repository.files if item.language and not item.binary}
        if previous is None:
            return set(current)
        old = {item.path: item.source_digest for item in previous.shards}
        changed = {path for path in set(current) | set(old) if current.get(path) != old.get(path)}
        reverse: dict[str, set[str]] = {}
        for shard in previous.shards:
            for dependency in shard.invalidation_dependencies:
                dependency_path = dependency.rsplit(":", 1)[0]
                reverse.setdefault(dependency_path, set()).add(shard.path)
        queue = list(changed)
        invalidated = set(changed)
        while queue:
            dependency = queue.pop()
            for dependent in reverse.get(dependency, ()):
                if dependent not in invalidated:
                    invalidated.add(dependent)
                    queue.append(dependent)
        return invalidated


def _module_path_index(files: Mapping[str, FileEvidence]) -> dict[str, str]:
    index: dict[str, str] = {}
    for path, evidence in files.items():
        if evidence.language == "python":
            pure = PurePosixPath(path)
            if pure.name == "__init__.py":
                module = ".".join(pure.parent.parts)
            else:
                module = ".".join(pure.with_suffix("").parts)
            if module:
                index[module] = path
    return index


def _resolve_dependencies(
    path: str,
    language: str,
    dependencies: Sequence[str],
    module_paths: Mapping[str, str],
) -> tuple[str, ...]:
    if language != "python":
        return ()
    result: set[str] = set()
    current_parts = list(PurePosixPath(path).with_suffix("").parts[:-1])
    for dependency in dependencies:
        if dependency.startswith("."):
            level = len(dependency) - len(dependency.lstrip("."))
            suffix = dependency[level:]
            base = current_parts[: max(0, len(current_parts) - level + 1)]
            module = ".".join([*base, *([suffix] if suffix else [])])
        else:
            module = dependency
        candidates = [module]
        parts = module.split(".")
        candidates.extend(".".join(parts[:index]) for index in range(len(parts) - 1, 0, -1))
        for candidate in candidates:
            resolved = module_paths.get(candidate)
            if resolved:
                result.add(resolved)
                break
    return tuple(sorted(result))


_GAP_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("integer_model", "numeric", "critical", "integer overflow and precision models differ"),
    ("null_model", "nullability", "critical", "null/undefined/open-world models differ"),
    ("exception_model", "exceptions", "critical", "exception and effect propagation models differ"),
    ("resource_model", "resources", "high", "resource ownership and finalization models differ"),
    ("concurrency_model", "concurrency", "high", "concurrency, cancellation, or memory models differ"),
)


def analyze_semantic_gaps(source: str, target: str) -> tuple[SemanticGap, ...]:
    if source not in LANGUAGE_PROFILES or target not in LANGUAGE_PROFILES:
        raise ValueError("source and target must name registered language profiles")
    source_profile = LANGUAGE_PROFILES[source]
    target_profile = LANGUAGE_PROFILES[target]
    evidence = FileEvidence("<profile-comparison>", _digest([source, target, PROFILE_VERSION]), 0, 0, source, False, False, False, 0, 0, 0, b"")
    gaps: list[SemanticGap] = []
    for attribute, family, severity, description in _GAP_RULES:
        left = getattr(source_profile, attribute)
        right = getattr(target_profile, attribute)
        if left != right:
            gaps.append(_gap(evidence, family, severity, f"{description}: {left!r} -> {right!r}", source, target))
    if source_profile.dynamic_boundaries != target_profile.dynamic_boundaries:
        gaps.append(_gap(evidence, "dynamic-reflection-ffi", "high", "dynamic, reflection, macro, FFI, or ABI boundaries require explicit closure", source, target))
    if source == "sql" or target == "sql":
        gaps.append(_gap(evidence, "sql-semantics", "critical", "SQL bag/order/NULL/collation/transaction semantics require engine-bound evidence", source, target))
    return tuple(sorted(gaps, key=lambda item: (item.severity, item.family, item.id)))


__all__ = [
    "CapabilityState",
    "ExternalFrontend",
    "FRAMEWORK_PROFILES",
    "FrameworkProfile",
    "FrontendCapability",
    "LANGUAGE_PROFILES",
    "LanguageProfile",
    "PROFILE_VERSION",
    "SemanticBundle",
    "SemanticCompiler",
    "SemanticEdge",
    "SemanticGap",
    "SemanticNode",
    "SemanticShard",
    "SourceMapEntry",
    "SourceSpan",
    "analyze_semantic_gaps",
]
