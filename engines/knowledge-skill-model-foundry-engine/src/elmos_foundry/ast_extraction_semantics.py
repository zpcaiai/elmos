"""Real bounded Python/ECMAScript 2017 AST extraction, without executing source.

CPython's current grammar and esprima-python 4.0.1 are exact parser surfaces.
TypeScript, JSX, newer ECMAScript syntax, symbol resolution, and native builds
are not implemented here. Parser configuration never comes from source files.
"""

from __future__ import annotations

import ast
from bisect import bisect_right
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import importlib
import importlib.metadata
import io
from pathlib import PurePosixPath
import sys
import tokenize
from types import ModuleType
from typing import Any

from .canonical import (
    canonical_digest,
    canonical_json_bytes,
    digest_bytes,
    require_identifier,
    validate_digest,
)
from .domain import TenantScope
from .local_semantics import CatalogView, LocalHandler, _exact_mapping, _response, _sequence, _text
from .store import FoundryStore, RunState, StoreError

SKILLS = frozenset({"multi-language-ast-extraction"})
INPUTS = frozenset(
    {"normalized repository artifact", "build metadata", "runtime trace", "test result"}
)
MAX_FILE_BYTES = 16_384
MAX_TOTAL_BYTES = 65_536
MAX_FILES = 16
MAX_TOKENS = 4096
MAX_DEPTH = 64
MAX_NODES = 1024
ESPRIMA_VERSION = "4.0.1"
PYTHON_VERSION = ".".join(str(value) for value in sys.version_info[:3])
PYTHON_GRAMMAR = ".".join(str(value) for value in sys.version_info[:2])


@dataclass(frozen=True)
class SourceSpan:
    start_byte: int
    end_byte: int
    start_line: int
    start_column_utf8: int
    end_line: int
    end_column_utf8: int
    precision: str


@dataclass(frozen=True)
class AstNode:
    node_id: str
    path: str
    language: str
    kind: str
    source_span: SourceSpan
    attributes: Mapping[str, Any]


@dataclass(frozen=True)
class AstEdge:
    parent_id: str
    child_id: str
    field: str
    index: int | None


class Source:
    def __init__(self, content: str, language: str) -> None:
        self.content = content
        self.data = content.encode("utf-8", "strict")
        self.offsets = [0]
        self.lines = [0]
        for index, character in enumerate(content):
            self.offsets.append(self.offsets[-1] + len(character.encode("utf-8")))
            if character == "\n" or (character == "\r" and content[index + 1 : index + 2] != "\n"):
                self.lines.append(self.offsets[-1])
            elif language == "javascript" and character in {"\u2028", "\u2029"}:
                self.lines.append(self.offsets[-1])
        self.boundaries = frozenset(self.offsets)

    def span(self, start: int, end: int, precision: str = "PARSER_EXACT") -> SourceSpan:
        if not 0 <= start <= end <= len(self.data):
            raise ValueError("parser returned an invalid UTF-8 source range")
        if start not in self.boundaries or end not in self.boundaries:
            raise ValueError("parser returned a range inside a UTF-8 code point")
        first, last = bisect_right(self.lines, start), bisect_right(self.lines, end)
        return SourceSpan(
            start,
            end,
            first,
            start - self.lines[first - 1],
            last,
            end - self.lines[last - 1],
            precision,
        )

    def python_span(self, node: ast.AST, enclosing: SourceSpan) -> SourceSpan:
        if not hasattr(node, "lineno"):
            return self.span(enclosing.start_byte, enclosing.end_byte, "ENCLOSING_STRUCTURAL_RANGE")
        start_line, end_line = node.lineno, getattr(node, "end_lineno", None)
        if isinstance(start_line, int) and end_line is None:
            return self.span(
                self.lines[start_line - 1],
                self.lines[start_line] if start_line < len(self.lines) else len(self.data),
                "LINE_RANGE_STRUCTURAL",
            )
        if not isinstance(start_line, int) or not isinstance(end_line, int):
            raise ValueError("Python AST node lacks end position")
        start_column, end_column = (
            getattr(node, "col_offset", None),
            getattr(node, "end_col_offset", None),
        )
        if not isinstance(start_column, int) or not isinstance(end_column, int):
            raise ValueError("Python AST node lacks byte column positions")
        return self.span(
            self.lines[start_line - 1] + start_column, self.lines[end_line - 1] + end_column
        )


def _path(value: Any) -> str:
    path = _text(value, "path", maximum=512)
    parts = PurePosixPath(path)
    if (
        parts.is_absolute()
        or "\\" in path
        or ":" in path
        or "\x00" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError("source path must be a normalized relative repository path")
    return path


def _parser_version(language: str) -> Mapping[str, str]:
    if language == "python":
        return {"language": language, "parser": "CPython.ast", "version": PYTHON_VERSION}
    if language == "javascript":
        return {"language": language, "parser": "esprima-python", "version": ESPRIMA_VERSION}
    raise ValueError("unsupported language; only Python and ECMAScript 2017 are implemented")


def _esprima() -> ModuleType:
    try:
        version = importlib.metadata.version("esprima")
        if version != ESPRIMA_VERSION:
            raise ValueError("esprima parser version differs from pinned 4.0.1")
        module = importlib.import_module("esprima")
    except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
        raise ValueError("esprima==4.0.1 is required for ECMAScript 2017 parsing") from exc
    if tuple(module.__version__) != (4, 0, 1):
        raise ValueError("loaded esprima parser identity differs from the pinned distribution")
    return module


def _token_limits(tokens: Sequence[tuple[str, str]]) -> None:
    if len(tokens) > MAX_TOKENS:
        raise ValueError("source exceeds the parser token budget")
    depth = 0
    for kind, value in tokens:
        if kind == "punctuator" and value in {"(", "[", "{"} or kind == "indent":
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError("source exceeds the parser nesting budget")
        elif kind == "punctuator" and value in {")", "]", "}"} or kind == "dedent":
            depth = max(0, depth - 1)


def _python_tree(source: Source) -> ast.AST:
    if sys.implementation.name != "cpython":
        raise ValueError("Python extraction requires the exact CPython AST implementation")
    tokens = []
    for token in tokenize.generate_tokens(io.StringIO(source.content).readline):
        kind = {
            tokenize.OP: "punctuator",
            tokenize.INDENT: "indent",
            tokenize.DEDENT: "dedent",
        }.get(token.type, "other")
        tokens.append((kind, token.string))
        if len(tokens) > MAX_TOKENS:
            raise ValueError("source exceeds the parser token budget")
    _token_limits(tokens)
    return ast.parse(
        source.content, mode="exec", type_comments=True, feature_version=sys.version_info[:2]
    )


def _literal(value: Any, source: Source, span: SourceSpan) -> Mapping[str, Any]:
    # Lexemes preserve large integers, string escapes, regexes and non-finite
    # numeric spellings without lossy conversion or serializing parser objects.
    lexeme = source.data[span.start_byte : span.end_byte].decode("utf-8")
    return {
        "literal_type": type(value).__name__,
        "lexeme": lexeme,
        "lexeme_digest": digest_bytes(lexeme.encode("utf-8")),
    }


def _python_nodes(tree: ast.AST, source: Source, path: str) -> tuple[list[AstNode], list[AstEdge]]:
    nodes: list[AstNode] = []
    edges: list[AstEdge] = []
    root_span = source.span(0, len(source.data), "FILE_RANGE")
    stack: list[tuple[ast.AST, str | None, str, int | None, SourceSpan, int]] = [
        (tree, None, "root", None, root_span, 0)
    ]
    marker_types = (ast.expr_context, ast.operator, ast.boolop, ast.unaryop, ast.cmpop)
    while stack:
        node, parent, field, index, enclosing, depth = stack.pop()
        if len(nodes) >= MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("AST exceeds its node or depth budget")
        identity = f"{path}#n{len(nodes)}"
        span = root_span if parent is None else source.python_span(node, enclosing)
        attributes: dict[str, Any] = {}
        children: list[tuple[ast.AST, str | None, str, int | None, SourceSpan, int]] = []
        for name, value in ast.iter_fields(node):
            if isinstance(value, marker_types):
                attributes[name] = {"ast_kind": type(value).__name__}
            elif isinstance(value, ast.AST):
                children.append((value, identity, name, None, span, depth + 1))
            elif isinstance(value, list):
                entries: list[Any] = []
                for child_index, child in enumerate(value):
                    if isinstance(child, marker_types):
                        entries.append({"ast_kind": type(child).__name__})
                    elif isinstance(child, ast.AST):
                        entries.append({"child_edge_index": child_index})
                        children.append((child, identity, name, child_index, span, depth + 1))
                    else:
                        entries.append(child)
                attributes[name] = entries
            elif isinstance(node, ast.Constant) and name == "value":
                attributes[name] = _literal(value, source, span)
            else:
                attributes[name] = value
        nodes.append(AstNode(identity, path, "python", type(node).__name__, span, attributes))
        if parent is not None:
            edges.append(AstEdge(parent, identity, field, index))
        stack.extend(reversed(children))
    return nodes, edges


def _javascript_tree(module: ModuleType, source: Source, source_type: str) -> Mapping[str, Any]:
    tokens = module.tokenize(source.content, {"jsx": False})
    _token_limits(
        [
            ("punctuator" if token.type == "Punctuator" else "other", str(token.value))
            for token in tokens
        ]
    )
    parse = module.parseModule if source_type == "module" else module.parseScript
    tree = parse(source.content, {"loc": True, "range": True, "tolerant": True, "jsx": False})
    result = tree.toDict()
    if not isinstance(result, Mapping):
        raise ValueError("esprima did not return its declared ESTree object")
    return result


def _javascript_nodes(
    tree: Mapping[str, Any], source: Source, path: str
) -> tuple[list[AstNode], list[AstEdge]]:
    nodes: list[AstNode] = []
    edges: list[AstEdge] = []
    stack: list[tuple[Mapping[str, Any], str | None, str, int | None, int]] = [
        (tree, None, "root", None, 0)
    ]
    while stack:
        node, parent, field, index, depth = stack.pop()
        if node["type"] in {"ObjectExpression", "ObjectPattern"} and any(
            child.get("type") in {"SpreadElement", "RestElement"}
            for child in node.get("properties", ())
        ):
            raise ValueError("object rest/spread requires unsupported ECMAScript 2018 semantics")
        if node["type"] == "Literal" and "regex" in node:
            regex = node["regex"]
            flags, pattern = str(regex["flags"]), str(regex["pattern"])
            if (
                not set(flags).issubset(set("gimuy"))
                or len(set(flags)) != len(flags)
                or any(extension in pattern for extension in ("(?<", "\\p{", "\\P{"))
            ):
                raise ValueError("regular expression requires unsupported ECMAScript extensions")
        if len(nodes) >= MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("AST exceeds its node or depth budget")
        identity = f"{path}#n{len(nodes)}"
        bounds = node.get("range")
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in bounds)
            or not 0 <= bounds[0] <= bounds[1] <= len(source.content)
        ):
            raise ValueError("esprima node is missing its exact character range")
        span = source.span(source.offsets[bounds[0]], source.offsets[bounds[1]])
        attributes: dict[str, Any] = {}
        children: list[tuple[Mapping[str, Any], str | None, str, int | None, int]] = []
        for name, value in node.items():
            if name in {"type", "range", "loc", "errors", "raw"}:
                continue
            if isinstance(value, Mapping) and "type" in value:
                children.append((value, identity, name, None, depth + 1))
            elif isinstance(value, list):
                entries: list[Any] = []
                for child_index, child in enumerate(value):
                    if isinstance(child, Mapping) and "type" in child:
                        entries.append({"child_edge_index": child_index})
                        children.append((child, identity, name, child_index, depth + 1))
                    else:
                        entries.append(child)
                attributes[name] = entries
            elif node["type"] == "Literal" and name == "value":
                attributes[name] = _literal(value, source, span)
            else:
                attributes[name] = value
        nodes.append(AstNode(identity, path, "javascript", str(node["type"]), span, attributes))
        if parent is not None:
            edges.append(AstEdge(parent, identity, field, index))
        stack.extend(reversed(children))
    return nodes, edges


def _diagnostic(error: BaseException | Mapping[str, Any], path: str) -> Mapping[str, Any]:
    if isinstance(error, Mapping):
        message = str(error.get("description", error.get("message", "parser error")))
        line, column = error.get("lineNumber"), error.get("column")
    else:
        message = str(getattr(error, "description", None) or str(error))
        line = getattr(error, "lineno", None) or getattr(error, "lineNumber", None)
        column = getattr(error, "offset", None) or getattr(error, "column", None)
    return {
        "path": path,
        "severity": "ERROR",
        "message": message[:512],
        "parser_line": line,
        "parser_column": column,
        "column_unit": "PARSER_NATIVE",
        "source_executed": False,
    }


class AstExtractionSemantics:
    def __init__(self, catalog: CatalogView, store: FoundryStore | None) -> None:
        self.catalog, self.store = catalog, store

    def extract(
        self, skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str
    ) -> Mapping[str, Any]:
        if skill not in SKILLS:
            raise ValueError("AST handler Skill identity is not exact")
        if self.store is None:
            raise StoreError("AST extraction requires a trusted checkpoint store")
        require_identifier(invocation, "invocation")
        values = _exact_mapping(payload.get("inputs"), "inputs", set(INPUTS))
        artifact = _exact_mapping(
            values["normalized repository artifact"],
            "artifact",
            {
                "tenant_id",
                "project_id",
                "purpose",
                "revision_set_id",
                "files",
                "baseline",
            },
        )
        for key in ("tenant_id", "project_id", "purpose", "revision_set_id"):
            if artifact[key] != getattr(scope, key):
                raise ValueError(f"artifact {key} differs from authenticated context")
        metadata = _exact_mapping(
            values["build metadata"], "build metadata", {"parser_versions", "source_configuration"}
        )
        if metadata["source_configuration"] != "NOT_EXECUTED":
            raise ValueError("source build configuration never authorizes execution")
        for name in ("runtime trace", "test result"):
            claim = _exact_mapping(values[name], name, {"status", "reason"})
            if claim["status"] != "NOT_RUN":
                raise ValueError("AST extraction cannot assert runtime/test execution")
            _text(claim["reason"], name + ".reason", maximum=512)
        raw_files = _sequence(artifact["files"], "files", maximum=MAX_FILES)
        files: list[Mapping[str, Any]] = []
        paths: set[str] = set()
        total = 0
        for raw in raw_files:
            item = _exact_mapping(
                raw,
                "file",
                {
                    "path",
                    "language",
                    "language_version",
                    "source_type",
                    "content",
                    "content_digest",
                },
            )
            path = _path(item["path"])
            if path.casefold() in paths:
                raise ValueError("source paths contain a duplicate or case collision")
            paths.add(path.casefold())
            language = item["language"]
            _parser_version(language)
            if language == "python":
                valid = (
                    item["language_version"] == PYTHON_GRAMMAR and item["source_type"] == "module"
                )
            else:
                valid = item["language_version"] == "ECMAScript2017" and item["source_type"] in {
                    "script",
                    "module",
                }
            if not valid:
                raise ValueError(
                    "language version or source mode is outside the exact parser surface"
                )
            if not isinstance(item["content"], str):
                raise ValueError("source content must be UTF-8 text")
            data = item["content"].encode("utf-8", "strict")
            total += len(data)
            if len(data) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                raise ValueError("source exceeds its per-file or invocation byte budget")
            if item["content_digest"] != digest_bytes(data):
                raise ValueError("source content digest mismatch")
            files.append(dict(item))
        expected = sorted(
            (_parser_version(language) for language in {item["language"] for item in files}),
            key=lambda item: item["language"],
        )
        claimed = _sequence(metadata["parser_versions"], "parser_versions", maximum=2)
        if canonical_digest(claimed) != canonical_digest(expected):
            raise ValueError("build metadata does not bind exact installed parser identities")
        baseline = artifact["baseline"]
        if not isinstance(baseline, Mapping):
            raise ValueError("baseline must be a path-to-content-digest object")
        for path, digest in baseline.items():
            _path(path)
            validate_digest(digest, "baseline digest")
        if len(baseline) > MAX_FILES:
            raise ValueError("baseline exceeds the file bound")
        module = _esprima() if any(item["language"] == "javascript" for item in files) else None
        request_digest = canonical_digest(values)
        decision = self.store.begin_run(
            scope,
            "foundry.ast.extract",
            invocation,
            {
                "request_digest": request_digest,
                "parser_versions": expected,
                "purpose": scope.purpose,
                "actor_id": scope.actor_id,
                "workspace_digest": scope.workspace_digest,
                "revision_set_id": scope.revision_set_id,
                "environment_id": scope.environment_id,
                "read_only_checkpoint": [
                    {"path": item["path"], "content_digest": item["content_digest"]}
                    for item in files
                ],
            },
        )
        run = decision.record
        if decision.replayed and run.response is not None:
            return run.response
        if run.state == RunState.PENDING:
            self.store.transition_run(
                scope,
                run.run_id,
                RunState.PENDING,
                RunState.RUNNING,
                reason="bounded-parser-started",
            )
        elif run.state != RunState.RUNNING:
            raise StoreError("AST run cannot be resumed from its stored state")
        nodes: list[AstNode] = []
        edges: list[AstEdge] = []
        reports: list[Mapping[str, Any]] = []
        diagnostics: list[Mapping[str, Any]] = []
        for item in sorted(files, key=lambda entry: entry["path"]):
            path, language = str(item["path"]), str(item["language"])
            source = Source(item["content"], language)
            try:
                if language == "python":
                    found_nodes, found_edges = _python_nodes(_python_tree(source), source, path)
                    errors: Sequence[Mapping[str, Any]] = ()
                else:
                    assert module is not None
                    tree = _javascript_tree(module, source, str(item["source_type"]))
                    found_nodes, found_edges = _javascript_nodes(tree, source, path)
                    errors = tree.get("errors", ())
                if len(nodes) + len(found_nodes) > MAX_NODES:
                    raise ValueError("invocation exceeds the AST node budget")
                nodes.extend(found_nodes)
                edges.extend(found_edges)
                diagnostics.extend(_diagnostic(error, path) for error in errors)
                status = "PARSED" if not errors else "RECOVERED_WITH_ERRORS"
            except (SyntaxError, tokenize.TokenError, ValueError, RecursionError) as exc:
                diagnostics.append(_diagnostic(exc, path))
                status = "REJECTED"
            except Exception as exc:
                if module is None or not isinstance(exc, module.Error):
                    raise
                diagnostics.append(_diagnostic(exc, path))
                status = "REJECTED"
            reports.append(
                {
                    "path": path,
                    "language": language,
                    "status": status,
                    "content_digest": item["content_digest"],
                    "source_bytes": len(source.data),
                    "parser": _parser_version(language),
                }
            )
        node_ids = {node.node_id for node in nodes}
        if len(node_ids) != len(nodes) or any(
            edge.parent_id not in node_ids or edge.child_id not in node_ids for edge in edges
        ):
            raise StoreError("AST graph identity/edge consistency failed")
        parsed_count = sum(report["status"] == "PARSED" for report in reports)
        graph = {
            "schema_version": "elmos.foundry.ast.v1",
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "revision_set_id": scope.revision_set_id,
            "files": reports,
            "nodes": [asdict(node) for node in nodes],
            "edges": [asdict(edge) for edge in edges],
            "diagnostics": diagnostics,
        }
        graph_digest = canonical_digest(graph)
        current = {str(item["path"]): item["content_digest"] for item in files}
        result = _response(
            {
                "semantic graph": {**graph, "graph_digest": graph_digest},
                "architecture model": {
                    "scope": "SYNTAX_ONLY",
                    "node_kind_counts": dict(sorted(Counter(node.kind for node in nodes).items())),
                    "inter_file_resolution": "NOT_RUN",
                    "graph_digest": graph_digest,
                },
                "semantic diff": {
                    "comparison": "CONTENT_DIGEST_ONLY_NO_SEMANTIC_EQUIVALENCE",
                    "changes": [
                        {
                            "path": path,
                            "change": "REMOVED"
                            if path not in current
                            else "ADDED"
                            if path not in baseline
                            else "UNCHANGED"
                            if current[path] == baseline[path]
                            else "MODIFIED",
                        }
                        for path in sorted(set(current) | set(baseline))
                    ],
                },
                "confidence report": {
                    "parsed_files": parsed_count,
                    "input_files": len(files),
                    "parse_coverage": parsed_count / len(files),
                    "graph_consistency": "PASS_LOCAL",
                    "parser_exact_spans": sum(
                        node.source_span.precision == "PARSER_EXACT" for node in nodes
                    ),
                    "structural_enclosing_spans": sum(
                        node.source_span.precision
                        in {"ENCLOSING_STRUCTURAL_RANGE", "LINE_RANGE_STRUCTURAL"}
                        for node in nodes
                    ),
                    "source_map_complete": "MAPPED_WITH_EXPLICIT_PRECISION"
                    if parsed_count == len(files)
                    else "INCOMPLETE",
                    "symbol_resolution": "NOT_RUN",
                    "source_executed": False,
                    "source_configuration_executed": False,
                    "checkpoint_status": "LOCAL_IMMUTABLE_RUN_BASELINE",
                    "checkpoint_digest": canonical_digest(run.request),
                    "input_digest": request_digest,
                    "runtime_trace": "NOT_RUN",
                    "caller_test_execution": "NOT_RUN",
                    "independent_verification": "NOT_RUN",
                    "production_gate": "BLOCKED",
                    "unsupported": [
                        "TypeScript",
                        "JSX",
                        "ECMAScript_after_2017",
                        "cross-file-symbol-resolution",
                    ],
                    "parser_versions": expected,
                    "external_evidence_status": "NOT_RUN",
                    "certification_status": "NOT_CERTIFIED",
                },
            },
            status="SUCCEEDED" if not diagnostics else "BLOCKED",
        )
        canonical_json_bytes(result)
        self.store.transition_run(
            scope,
            run.run_id,
            RunState.RUNNING,
            RunState.SUCCEEDED if not diagnostics else RunState.BLOCKED,
            reason="AST-extraction-completed" if not diagnostics else "AST-parser-diagnostics",
            response=result,
        )
        return result


def build_ast_extraction_handlers(
    catalog: CatalogView, store: FoundryStore | None
) -> dict[str, LocalHandler]:
    if SKILLS - set(catalog.atomic_skills):
        raise ValueError("multi-language-ast-extraction is absent from the exact catalog")
    runtime = AstExtractionSemantics(catalog, store)
    return {"multi-language-ast-extraction": runtime.extract}
