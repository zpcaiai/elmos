"""Incremental semantic index: an index whose increment provably equals a rebuild.

The defining property of this module is that ``incremental(prior, reader,
changed)`` and ``build(reader)`` produce byte-identical indexes.  That is not
achieved by hoping the two code paths agree — there is only *one* code path
that produces an index.  Extraction is a pure function of ``(path, bytes)`` that
yields per-file facts; assembly is a pure function of the complete set of facts.
``build`` extracts every file and assembles; ``incremental`` reuses prior facts
for untouched files, re-extracts the touched ones, and assembles.  Cross-file
resolution therefore happens in assembly, where it sees the whole world, so a
change in one file can correctly add or remove an edge in another without the
two entry points ever diverging.

Reuse of prior facts is only sound if the untouched files really are untouched,
and file mtime is not evidence of that.  Every reused fact is re-checked against
the snapshot's *content digest*, and an undeclared change — or an added or
deleted path the caller did not list — raises ``INVALIDATION_MISS`` instead of
producing an index that is quietly wrong.

**Which languages get real parsing, and which get heuristics.** This is stated
plainly because an over-claimed index is worse than a small one:

* Real parsers (stdlib, full-fidelity):
  ``.py``/``.pyi`` via :mod:`ast`, ``.json`` via :mod:`json`, ``.toml`` via
  :mod:`tomllib`.  Only Python produces ``calls`` edges.
* Bounded heuristics (line-anchored regex plus brace matching):
  ``.js``/``.jsx``/``.mjs``/``.cjs``/``.ts``/``.tsx``, ``.java``, ``.go``.
  These find declarations, imports and route markers.  They emit **no** call
  edges at all, because a regex cannot tell a call from a mention, and a
  low-confidence edge is omitted rather than guessed.
* Everything else is listed in ``unindexed`` with reason ``no-extractor``.  It
  is not silently treated as empty.

Coverage is reported per file as ``unknownRegions``: the line ranges the
extractor did not understand.  A consumer that does not know how much the index
cannot see will trust it uniformly, which is exactly how a shallow index becomes
dangerous.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import (
    Status,
    canonical_json,
    digest,
    reject_unknown_fields,
    require_identifier,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import RepositoryReader
from .registry import register

register_codes(
    Category.SEMANTIC,
    "INDEX_INCONSISTENT",
    "INVALIDATION_MISS",
    "ADAPTER_UNSUPPORTED",
    "SYMBOL_COLLISION",
)

__all__ = [
    "INDEX_VERSION",
    "Delta",
    "Entity",
    "FileExtract",
    "Index",
    "Relationship",
    "build",
    "handle",
    "incremental",
    "validate_index",
]

INDEX_VERSION = "2.0.0"

ENTITY_KINDS = ("module", "class", "function", "constant", "import", "route", "config_key")
RELATIONSHIP_KINDS = ("contains", "imports", "calls")

#: extension -> (language, extractor).  ``extractor`` is either a real parser
#: name or ``heuristic-*``; it is carried into every output so a consumer can
#: weight the evidence.
_EXTRACTORS: Mapping[str, tuple[str, str]] = {
    "py": ("Python", "ast"), "pyi": ("Python", "ast"),
    "js": ("JavaScript", "heuristic-regex"), "jsx": ("JavaScript", "heuristic-regex"),
    "mjs": ("JavaScript", "heuristic-regex"), "cjs": ("JavaScript", "heuristic-regex"),
    "ts": ("TypeScript", "heuristic-regex"), "tsx": ("TypeScript", "heuristic-regex"),
    "java": ("Java", "heuristic-regex"), "go": ("Go", "heuristic-regex"),
    "json": ("JSON", "json"), "toml": ("TOML", "tomllib"),
}

_LINE_COMMENT: Mapping[str, str] = {
    "Python": "#", "JavaScript": "//", "TypeScript": "//", "Java": "//", "Go": "//",
}
_BLOCK_COMMENT_LANGUAGES = frozenset({"JavaScript", "TypeScript", "Java", "Go"})

_JS_MODULE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

_MAX_UNKNOWN_REGIONS = 64
_MAX_CONFIG_KEYS = 512
_MAX_BRACE_SPAN_LINES = 4000

_TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__)/|(^|/)test_[^/]+$|_test\.[^./]+$"
    r"|\.test\.[^./]+$|\.spec\.[^./]+$|Test\.java$"
)


# --- raw, per-file facts -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawEntity:
    """A declaration found in one file, before repository-wide identity is assigned."""

    kind: str
    name: str
    qualified_name: str
    line_start: int
    line_end: int
    parent_qualified_name: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RawCall:
    """A call site.  ``attribute`` marks ``x.y()``, which is never resolved."""

    caller_qualified_name: str
    callee_name: str
    line: int
    attribute: bool
    imported_from: str = ""


@dataclass(frozen=True, slots=True)
class RawImport:
    """An import statement: ``module`` plus the symbol bound, when there is one."""

    module: str
    symbol: str
    line: int
    relative_level: int = 0


@dataclass(frozen=True, slots=True)
class FileExtract:
    """Everything one file contributes, computed without seeing any other file.

    Purity here is what makes an incremental update equal a full rebuild: the
    same bytes at the same path always yield the same ``FileExtract``, so reusing
    one from a prior index is indistinguishable from recomputing it.
    """

    path: str
    language: str
    extractor: str
    content_digest: str
    line_count: int | None
    lines_measured: bool
    unindexed_reason: str
    module_qualified_name: str
    entities: tuple[RawEntity, ...] = ()
    calls: tuple[RawCall, ...] = ()
    imports: tuple[RawImport, ...] = ()
    understood_lines: tuple[tuple[int, int], ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "extractor": self.extractor,
            "contentDigest": self.content_digest,
            "lineCount": self.line_count,
            "linesMeasured": self.lines_measured,
            "unindexedReason": self.unindexed_reason,
            "moduleQualifiedName": self.module_qualified_name,
            "entities": [
                {"kind": e.kind, "name": e.name, "qualifiedName": e.qualified_name,
                 "lineStart": e.line_start, "lineEnd": e.line_end,
                 "parentQualifiedName": e.parent_qualified_name, "detail": e.detail}
                for e in self.entities
            ],
            "calls": [
                {"caller": c.caller_qualified_name, "callee": c.callee_name,
                 "line": c.line, "attribute": c.attribute, "importedFrom": c.imported_from}
                for c in self.calls
            ],
            "imports": [
                {"module": i.module, "symbol": i.symbol, "line": i.line,
                 "relativeLevel": i.relative_level}
                for i in self.imports
            ],
            "understoodLines": [
                {"start": start, "end": end} for start, end in self.understood_lines
            ],
        }


# --- assembled index ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Entity:
    """A repository-wide symbol with a stable identity.

    ``entity_id`` is ``digest(repo_id, kind, qualified_name, path)`` and nothing
    else — deliberately not the line range, so moving a function within its file
    does not invent a new symbol and evict every edge pointing at it.
    """

    entity_id: str
    kind: str
    name: str
    qualified_name: str
    path: str
    language: str
    extractor: str
    line_start: int
    line_end: int
    detail: str
    symbol_uri: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "entityId": self.entity_id,
            "kind": self.kind,
            "name": self.name,
            "qualifiedName": self.qualified_name,
            "path": self.path,
            "language": self.language,
            "extractor": self.extractor,
            "lineStart": self.line_start,
            "lineEnd": self.line_end,
            "detail": self.detail,
            "symbolUri": self.symbol_uri,
        }


@dataclass(frozen=True, slots=True)
class Relationship:
    """A directed edge whose endpoints must both exist in the same index."""

    relationship_id: str
    kind: str
    source_id: str
    target_id: str
    evidence: tuple[tuple[str, int], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "relationshipId": self.relationship_id,
            "kind": self.kind,
            "sourceId": self.source_id,
            "targetId": self.target_id,
            "evidence": [{"path": path, "line": line} for path, line in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class Index:
    """A snapshot-bound semantic index that carries its own digest and coverage.

    The payload contains no trace of *how* it was built.  If it recorded that it
    came from an incremental update, an incremental index could never be
    byte-identical to a rebuild, and the property this capability exists to
    guarantee would be untestable.
    """

    repo_id: str
    snapshot_sha: str
    entities: tuple[Entity, ...]
    relationships: tuple[Relationship, ...]
    files: tuple[FileExtract, ...]
    unresolved_imports: tuple[tuple[str, str, int], ...]

    @property
    def status(self) -> Status:
        return Status.PARTIAL if self.unreadable() else Status.SUCCEEDED

    def unreadable(self) -> tuple[FileExtract, ...]:
        """Files the snapshot would not let us read; their content is unmeasured."""

        return tuple(f for f in self.files if not f.lines_measured)

    def entity_by_id(self, entity_id: str) -> Entity | None:
        for entity in self.entities:
            if entity.entity_id == entity_id:
                return entity
        return None

    def entities_for_path(self, path: str) -> tuple[Entity, ...]:
        return tuple(e for e in self.entities if e.path == path)

    def to_payload(self) -> dict[str, Any]:
        coverage = self._coverage()
        payload: dict[str, Any] = {
            "indexId": f"{self.repo_id}:{self.snapshot_sha}",
            "version": INDEX_VERSION,
            "repoId": self.repo_id,
            "repoSnapshotSha": self.snapshot_sha,
            "graphs": {
                "entities": [entity.to_payload() for entity in self.entities],
                "relationships": [rel.to_payload() for rel in self.relationships],
            },
            "files": [extract.to_payload() for extract in self.files],
            "unresolvedImports": [
                {"path": path, "module": module, "line": line}
                for path, module, line in self.unresolved_imports
            ],
            "unindexed": [
                {"path": f.path, "reason": f.unindexed_reason, "language": f.language}
                for f in self.files if f.unindexed_reason
            ],
            "quality": coverage,
            "testImpactMap": self._test_impact_map(),
            "status": str(self.status),
        }
        payload["indexDigest"] = digest(payload)
        return payload

    def _coverage(self) -> dict[str, Any]:
        per_file: list[dict[str, Any]] = []
        total_lines = 0
        understood_total = 0
        measured = True
        for extract in self.files:
            if not extract.lines_measured or extract.line_count is None:
                measured = False
                per_file.append({
                    "path": extract.path,
                    "language": extract.language,
                    "extractor": extract.extractor,
                    "measured": False,
                    "reason": extract.unindexed_reason,
                    "lineCount": None,
                    "understoodLineCount": None,
                    "unknownLineCount": None,
                    "unknownFractionPpm": None,
                    "unknownRegions": [],
                    "unknownRegionsTruncated": False,
                })
                continue
            understood = _line_set(extract.understood_lines)
            unknown = [n for n in range(1, extract.line_count + 1) if n not in understood]
            regions = _merge_lines(unknown)
            truncated = len(regions) > _MAX_UNKNOWN_REGIONS
            total_lines += extract.line_count
            understood_total += extract.line_count - len(unknown)
            per_file.append({
                "path": extract.path,
                "language": extract.language,
                "extractor": extract.extractor,
                "measured": True,
                "reason": extract.unindexed_reason,
                "lineCount": extract.line_count,
                "understoodLineCount": extract.line_count - len(unknown),
                "unknownLineCount": len(unknown),
                "unknownFractionPpm": _ppm(len(unknown), extract.line_count),
                "unknownRegions": [
                    {"start": start, "end": end}
                    for start, end in regions[:_MAX_UNKNOWN_REGIONS]
                ],
                "unknownRegionsTruncated": truncated,
            })
        return {
            "files": per_file,
            "lineCount": total_lines,
            "understoodLineCount": understood_total,
            "unknownLineCount": total_lines - understood_total,
            "unknownFractionPpm": _ppm(total_lines - understood_total, total_lines),
            "coverageMeasured": measured,
            "unmeasuredPaths": [f.path for f in self.files if not f.lines_measured],
            "realParserLanguages": ["JSON", "Python", "TOML"],
            "heuristicLanguages": ["Go", "Java", "JavaScript", "TypeScript"],
            "callEdgeLanguages": ["Python"],
            "definitions": {
                "understoodLineCount": "lines inside an extracted entity span, on an import "
                                       "or call site, blank, or a comment in that language",
                "unknownLineCount": "lineCount minus understoodLineCount; the part of the "
                                    "file this index does not see",
                "unknownFractionPpm": "unknownLineCount / lineCount in parts per million "
                                      "(integer; floats are not canonically hashable)",
                "coverageMeasured": "false when any file could not be read, making the "
                                    "aggregate a lower bound rather than a total",
                "callEdgeLanguages": "languages for which 'calls' edges are emitted at all; "
                                     "for every other language the absence of a call edge is "
                                     "not evidence that no call exists",
            },
        }

    def _test_impact_map(self) -> dict[str, Any]:
        """Which test files transitively import each module path.

        The closure is complete with respect to *resolved* imports, and the
        count of unresolved imports is published alongside it, because a recall
        claim that hides its own blind spot is not a recall claim.
        """

        module_by_id = {
            e.entity_id: e for e in self.entities if e.kind == "module"
        }
        importers: dict[str, set[str]] = {}
        for rel in self.relationships:
            if rel.kind != "imports":
                continue
            source = module_by_id.get(rel.source_id)
            target = module_by_id.get(rel.target_id)
            if source is None or target is None:
                continue
            importers.setdefault(target.path, set()).add(source.path)

        impacted: dict[str, list[str]] = {}
        for entity in module_by_id.values():
            seen: set[str] = set()
            frontier = [entity.path]
            while frontier:
                current = frontier.pop()
                for importer in sorted(importers.get(current, ())):
                    if importer not in seen:
                        seen.add(importer)
                        frontier.append(importer)
            tests = sorted(path for path in seen | {entity.path} if _is_test_path(path))
            if tests:
                impacted[entity.path] = tests
        return {
            "method": "static-import-closure",
            "impactedTestsByPath": [
                {"path": path, "tests": impacted[path]} for path in sorted(impacted)
            ],
            "unresolvedImportCount": len(self.unresolved_imports),
            "recall": {
                "measured": True,
                "scope": "complete over resolved import edges",
                "blindSpot": "unresolved imports and dynamic imports are not in the closure",
            },
        }


@dataclass(frozen=True, slots=True)
class Delta:
    """What changed between two indexes, and why each path was reconsidered.

    Every entry is a set difference against the prior index, so the delta cannot
    contain an item that did not actually change; minimality is structural
    rather than a promise.
    """

    prior_digest: str
    new_digest: str
    reindexed_paths: tuple[tuple[str, str], ...]
    evicted_paths: tuple[str, ...]
    added_entity_ids: tuple[str, ...]
    removed_entity_ids: tuple[str, ...]
    added_relationship_ids: tuple[str, ...]
    removed_relationship_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "priorIndexDigest": self.prior_digest,
            "newIndexDigest": self.new_digest,
            "reindexedPaths": [
                {"path": path, "reason": reason} for path, reason in self.reindexed_paths
            ],
            "evictedPaths": list(self.evicted_paths),
            "addedEntityIds": list(self.added_entity_ids),
            "removedEntityIds": list(self.removed_entity_ids),
            "addedRelationshipIds": list(self.added_relationship_ids),
            "removedRelationshipIds": list(self.removed_relationship_ids),
        }


# --- small helpers -----------------------------------------------------------


def _ppm(part: int, whole: int) -> int:
    return 0 if whole <= 0 else (part * 1_000_000) // whole


def _line_set(ranges: Iterable[tuple[int, int]]) -> set[int]:
    out: set[int] = set()
    for start, end in ranges:
        if end >= start:
            out.update(range(start, end + 1))
    return out


def _merge_lines(lines: Sequence[int]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for line in sorted(lines):
        if merged and line == merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], line)
        else:
            merged.append((line, line))
    return merged


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


def _extension(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[1].lower() if "." in name[1:] else ""


def _ignorable_lines(lines: Sequence[str], language: str) -> list[tuple[int, int]]:
    """Blank and comment lines — understood in the sense that nothing was missed."""

    marker = _LINE_COMMENT.get(language, "")
    in_block = False
    out: list[int] = []
    for number, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text:
            out.append(number)
            continue
        if language in _BLOCK_COMMENT_LANGUAGES:
            if in_block:
                out.append(number)
                if "*/" in text:
                    in_block = False
                continue
            if text.startswith("/*"):
                out.append(number)
                if "*/" not in text[2:]:
                    in_block = True
                continue
        if marker and text.startswith(marker):
            out.append(number)
    return _merge_lines(out)


def _brace_span(lines: Sequence[str], start_index: int) -> int | None:
    """Return the 1-based line closing the block opened at ``start_index``.

    Returns ``None`` when the block does not close within the bound.  The caller
    then drops the declaration entirely: an entity with a guessed end line would
    claim coverage over lines nobody parsed.
    """

    depth = 0
    opened = False
    limit = min(len(lines), start_index + _MAX_BRACE_SPAN_LINES)
    for index in range(start_index, limit):
        for char in lines[index]:
            if char == "{":
                depth += 1
                opened = True
            elif char == "}":
                depth -= 1
                if opened and depth <= 0:
                    return index + 1
        if opened and depth <= 0:
            return index + 1
    return None


def _module_qualified_name(path: str, language: str, text: str | None) -> str:
    stem = path.rsplit(".", 1)[0] if "." in path.rsplit("/", 1)[-1] else path
    if language == "Python":
        parts = [part for part in stem.split("/") if part]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) or "__root__"
    if language == "Java" and text:
        match = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.MULTILINE)
        if match:
            return f"{match.group(1)}.{stem.rsplit('/', 1)[-1]}"
    if language == "Go":
        # A Go package spans every file in its directory, so naming the module
        # entity after the directory made all of them claim one qualified name
        # and aborted the WHOLE repository index with SYMBOL_COLLISION — for the
        # most ordinary Go layout there is.  The module entity is per file (as it
        # already is for Python and Java); the package stays visible as the
        # prefix, so import resolution can still group by it.
        directory, _, filename = stem.rpartition("/")
        return f"{directory or '.'}.{filename}"
    return stem


# --- Python: real parsing ----------------------------------------------------


def _is_constant_name(name: str) -> bool:
    return name.isupper() and any(char.isalpha() for char in name)


def _decorator_route(node: ast.AST) -> tuple[str, str] | None:
    """Return ``(method, route)`` for a decorator that literally declares one."""

    if not isinstance(node, ast.Call) or not node.args:
        return None
    first = node.args[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
        return None
    func = node.func
    if isinstance(func, ast.Attribute):
        attribute = func.attr.lower()
        if attribute in {"route", "get", "post", "put", "delete", "patch"}:
            method = "ANY" if attribute == "route" else attribute.upper()
            return method, first.value
    return None


def _extract_python(path: str, text: str, module_qname: str) -> tuple[
        list[RawEntity], list[RawCall], list[RawImport], list[tuple[int, int]]]:
    tree = ast.parse(text)
    entities: list[RawEntity] = []
    calls: list[RawCall] = []
    imports: list[RawImport] = []
    understood: list[tuple[int, int]] = []
    symbol_origin: dict[str, str] = {}

    def walk(node: ast.AST, scope: str, is_class_body: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = f"{scope}.{child.name}"
                entities.append(RawEntity(
                    kind="function", name=child.name, qualified_name=qname,
                    line_start=child.lineno, line_end=child.end_lineno or child.lineno,
                    parent_qualified_name=scope,
                    detail="method" if is_class_body else "function",
                ))
                for decorator in child.decorator_list:
                    route = _decorator_route(decorator)
                    if route is not None:
                        method, target = route
                        entities.append(RawEntity(
                            kind="route", name=f"{method} {target}",
                            qualified_name=f"{qname}#route:{method}:{target}",
                            line_start=decorator.lineno,
                            line_end=decorator.end_lineno or decorator.lineno,
                            parent_qualified_name=qname, detail="decorator-literal",
                        ))
                walk(child, qname, False)
            elif isinstance(child, ast.ClassDef):
                qname = f"{scope}.{child.name}"
                entities.append(RawEntity(
                    kind="class", name=child.name, qualified_name=qname,
                    line_start=child.lineno, line_end=child.end_lineno or child.lineno,
                    parent_qualified_name=scope, detail="class",
                ))
                walk(child, qname, True)
            elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    if isinstance(target, ast.Name) and _is_constant_name(target.id):
                        entities.append(RawEntity(
                            kind="constant", name=target.id,
                            qualified_name=f"{scope}.{target.id}",
                            line_start=child.lineno,
                            line_end=child.end_lineno or child.lineno,
                            parent_qualified_name=scope, detail="upper-case-binding",
                        ))
                        understood.append((child.lineno, child.end_lineno or child.lineno))
                walk(child, scope, is_class_body)
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    imports.append(RawImport(alias.name, "", child.lineno))
                    symbol_origin[alias.asname or alias.name.split(".")[0]] = alias.name
                    entities.append(RawEntity(
                        kind="import", name=alias.asname or alias.name,
                        qualified_name=f"{module_qname}#import:{alias.name}",
                        line_start=child.lineno, line_end=child.lineno,
                        parent_qualified_name=module_qname, detail=f"import {alias.name}",
                    ))
                understood.append((child.lineno, child.end_lineno or child.lineno))
            elif isinstance(child, ast.ImportFrom):
                module = child.module or ""
                for alias in child.names:
                    imports.append(RawImport(module, alias.name, child.lineno,
                                             child.level or 0))
                    symbol_origin[alias.asname or alias.name] = module
                    entities.append(RawEntity(
                        kind="import", name=alias.asname or alias.name,
                        qualified_name=f"{module_qname}#import:{module}.{alias.name}",
                        line_start=child.lineno, line_end=child.lineno,
                        parent_qualified_name=module_qname,
                        detail=f"from {'.' * (child.level or 0)}{module} import {alias.name}",
                    ))
                understood.append((child.lineno, child.end_lineno or child.lineno))
            elif isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Name):
                    calls.append(RawCall(scope, func.id, child.lineno, False,
                                         symbol_origin.get(func.id, "")))
                elif isinstance(func, ast.Attribute):
                    calls.append(RawCall(scope, func.attr, child.lineno, True))
                walk(child, scope, False)
            else:
                walk(child, scope, is_class_body)

    walk(tree, module_qname, False)
    for entity in entities:
        understood.append((entity.line_start, entity.line_end))
    for call in calls:
        understood.append((call.line, call.line))
    return entities, calls, imports, understood


def _extract_config(path: str, text: str, language: str,
                    module_qname: str) -> tuple[list[RawEntity], list[tuple[int, int]]]:
    """Config keys from a real parser; keys are flattened to a bounded depth."""

    if language == "JSON":
        document = json.loads(text)
    else:
        document = tomllib.loads(text)
    entities: list[RawEntity] = []

    def visit(node: Any, prefix: str, depth: int) -> None:
        if depth > 3 or len(entities) >= _MAX_CONFIG_KEYS:
            return
        if isinstance(node, Mapping):
            for key in sorted(node):
                if not isinstance(key, str):
                    continue
                dotted = f"{prefix}.{key}" if prefix else key
                entities.append(RawEntity(
                    kind="config_key", name=key,
                    qualified_name=f"{module_qname}#config:{dotted}",
                    line_start=0, line_end=0,
                    parent_qualified_name=module_qname, detail=dotted,
                ))
                visit(node[key], dotted, depth + 1)

    visit(document, "", 0)
    return entities, []


# --- bounded heuristics: JS/TS, Java, Go -------------------------------------

_JS_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)")
_JS_FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)")
_JS_ARROW = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*"
    r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")
_JS_CONST = re.compile(r"^\s*(?:export\s+)?const\s+([A-Z][A-Z0-9_]*)\s*(?::[^=]+)?=")
_JS_IMPORT_FROM = re.compile(r"^\s*import\s+(?:[^'\"]*?\s+from\s+)?['\"]([^'\"]+)['\"]")
_JS_REQUIRE = re.compile(
    r"^\s*(?:const|let|var)\s+[^=]+=\s*require\(\s*['\"]([^'\"]+)['\"]\s*\)")
_JS_ROUTE = re.compile(
    r"\b(?:app|router|server)\.(get|post|put|delete|patch|all)\(\s*['\"]([^'\"]+)['\"]")

_JAVA_TYPE = re.compile(
    r"^\s*(?:@\w+\s+)*(?:public|protected|private|abstract|final|static|sealed|\s)*"
    r"\b(class|interface|enum|record)\s+(\w+)")
_JAVA_METHOD = re.compile(
    r"^\s+(?:@\w+\s+)*(?:public|protected|private)\s+(?:static\s+|final\s+|synchronized\s+"
    r"|abstract\s+|native\s+)*[\w<>\[\],.\s]+\s+(\w+)\s*\([^;{]*\)\s*(?:throws [\w,.\s]+)?\{")
_JAVA_CONST = re.compile(
    r"^\s*(?:public|protected|private)?\s*static\s+final\s+[\w<>\[\].]+\s+([A-Z][A-Z0-9_]*)\s*=")
_JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;")
_JAVA_ROUTE = re.compile(
    r"@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']")

_GO_FUNC = re.compile(r"^func\s+(\w+)\s*\(")
_GO_METHOD = re.compile(r"^func\s+\(\s*\w+\s+\*?(\w+)\s*\)\s*(\w+)\s*\(")
_GO_TYPE = re.compile(r"^type\s+(\w+)\s+(struct|interface)\b")
_GO_CONST = re.compile(r"^const\s+(\w+)\s*=")
_GO_IMPORT_SINGLE = re.compile(r"^import\s+(?:\w+\s+)?\"([^\"]+)\"")
_GO_IMPORT_BLOCK_ENTRY = re.compile(r"^\s*(?:\w+\s+)?\"([^\"]+)\"")
_GO_ROUTE = re.compile(r"\.HandleFunc\(\s*\"([^\"]+)\"")


def _extract_js(lines: Sequence[str], module_qname: str) -> tuple[
        list[RawEntity], list[RawImport], list[tuple[int, int]]]:
    entities: list[RawEntity] = []
    imports: list[RawImport] = []
    understood: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        number = index + 1
        for pattern, kind in ((_JS_CLASS, "class"), (_JS_FUNCTION, "function"),
                              (_JS_ARROW, "function")):
            match = pattern.match(line)
            if match is None:
                continue
            end = _brace_span(lines, index)
            if end is None:
                # Unbalanced braces: drop the declaration rather than guess a span.
                continue
            name = match.group(1)
            entities.append(RawEntity(
                kind=kind, name=name, qualified_name=f"{module_qname}.{name}",
                line_start=number, line_end=end, parent_qualified_name=module_qname,
                detail="heuristic-declaration",
            ))
            understood.append((number, end))
            break
        else:
            const = _JS_CONST.match(line)
            if const is not None:
                entities.append(RawEntity(
                    kind="constant", name=const.group(1),
                    qualified_name=f"{module_qname}.{const.group(1)}",
                    line_start=number, line_end=number,
                    parent_qualified_name=module_qname, detail="heuristic-const",
                ))
                understood.append((number, number))
        for pattern in (_JS_IMPORT_FROM, _JS_REQUIRE):
            match = pattern.match(line)
            if match is not None:
                imports.append(RawImport(match.group(1), "", number))
                entities.append(RawEntity(
                    kind="import", name=match.group(1),
                    qualified_name=f"{module_qname}#import:{match.group(1)}",
                    line_start=number, line_end=number,
                    parent_qualified_name=module_qname, detail="heuristic-import",
                ))
                understood.append((number, number))
                break
        route = _JS_ROUTE.search(line)
        if route is not None:
            method, target = route.group(1).upper(), route.group(2)
            entities.append(RawEntity(
                kind="route", name=f"{method} {target}",
                qualified_name=f"{module_qname}#route:{method}:{target}",
                line_start=number, line_end=number,
                parent_qualified_name=module_qname, detail="heuristic-route-literal",
            ))
            understood.append((number, number))
    return entities, imports, understood


def _extract_java(lines: Sequence[str], module_qname: str) -> tuple[
        list[RawEntity], list[RawImport], list[tuple[int, int]]]:
    entities: list[RawEntity] = []
    imports: list[RawImport] = []
    understood: list[tuple[int, int]] = []
    current_type = module_qname
    for index, line in enumerate(lines):
        number = index + 1
        if line.strip().startswith("package "):
            understood.append((number, number))
        type_match = _JAVA_TYPE.match(line)
        if type_match is not None:
            end = _brace_span(lines, index)
            if end is not None:
                name = type_match.group(2)
                current_type = f"{module_qname}.{name}"
                entities.append(RawEntity(
                    kind="class", name=name, qualified_name=current_type,
                    line_start=number, line_end=end,
                    parent_qualified_name=module_qname,
                    detail=f"heuristic-{type_match.group(1)}",
                ))
                understood.append((number, end))
            continue
        method = _JAVA_METHOD.match(line)
        if method is not None:
            end = _brace_span(lines, index)
            if end is not None:
                name = method.group(1)
                entities.append(RawEntity(
                    kind="function", name=name,
                    qualified_name=f"{current_type}.{name}",
                    line_start=number, line_end=end,
                    parent_qualified_name=current_type, detail="heuristic-method",
                ))
                understood.append((number, end))
            continue
        const = _JAVA_CONST.match(line)
        if const is not None:
            entities.append(RawEntity(
                kind="constant", name=const.group(1),
                qualified_name=f"{current_type}.{const.group(1)}",
                line_start=number, line_end=number,
                parent_qualified_name=current_type, detail="heuristic-static-final",
            ))
            understood.append((number, number))
        imported = _JAVA_IMPORT.match(line)
        if imported is not None:
            imports.append(RawImport(imported.group(1), "", number))
            entities.append(RawEntity(
                kind="import", name=imported.group(1),
                qualified_name=f"{module_qname}#import:{imported.group(1)}",
                line_start=number, line_end=number,
                parent_qualified_name=module_qname, detail="heuristic-import",
            ))
            understood.append((number, number))
        route = _JAVA_ROUTE.search(line)
        if route is not None:
            verb = route.group(1).upper()
            method_name = "ANY" if verb == "REQUEST" else verb
            entities.append(RawEntity(
                kind="route", name=f"{method_name} {route.group(2)}",
                qualified_name=f"{module_qname}#route:{method_name}:{route.group(2)}",
                line_start=number, line_end=number,
                parent_qualified_name=module_qname, detail="heuristic-annotation",
            ))
            understood.append((number, number))
    return entities, imports, understood


def _extract_go(lines: Sequence[str], module_qname: str) -> tuple[
        list[RawEntity], list[RawImport], list[tuple[int, int]]]:
    entities: list[RawEntity] = []
    imports: list[RawImport] = []
    understood: list[tuple[int, int]] = []
    in_import_block = False
    for index, line in enumerate(lines):
        number = index + 1
        stripped = line.strip()
        if stripped.startswith("package "):
            understood.append((number, number))
            continue
        if in_import_block:
            understood.append((number, number))
            if stripped == ")":
                in_import_block = False
                continue
            entry = _GO_IMPORT_BLOCK_ENTRY.match(line)
            if entry is not None:
                imports.append(RawImport(entry.group(1), "", number))
                entities.append(RawEntity(
                    kind="import", name=entry.group(1),
                    qualified_name=f"{module_qname}#import:{entry.group(1)}",
                    line_start=number, line_end=number,
                    parent_qualified_name=module_qname, detail="heuristic-import",
                ))
            continue
        if stripped.startswith("import (") or stripped == "import(":
            in_import_block = True
            understood.append((number, number))
            continue
        single = _GO_IMPORT_SINGLE.match(line)
        if single is not None:
            imports.append(RawImport(single.group(1), "", number))
            entities.append(RawEntity(
                kind="import", name=single.group(1),
                qualified_name=f"{module_qname}#import:{single.group(1)}",
                line_start=number, line_end=number,
                parent_qualified_name=module_qname, detail="heuristic-import",
            ))
            understood.append((number, number))
            continue
        method = _GO_METHOD.match(line)
        function = _GO_FUNC.match(line)
        type_match = _GO_TYPE.match(line)
        if method is not None or function is not None or type_match is not None:
            end = _brace_span(lines, index)
            if end is None:
                continue
            if method is not None:
                name = method.group(2)
                qname = f"{module_qname}.{method.group(1)}.{name}"
                kind, detail = "function", "heuristic-method"
            elif function is not None:
                name = function.group(1)
                qname = f"{module_qname}.{name}"
                kind, detail = "function", "heuristic-func"
            else:
                name = type_match.group(1)
                qname = f"{module_qname}.{name}"
                kind, detail = "class", f"heuristic-{type_match.group(2)}"
            entities.append(RawEntity(
                kind=kind, name=name, qualified_name=qname,
                line_start=number, line_end=end,
                parent_qualified_name=module_qname, detail=detail,
            ))
            understood.append((number, end))
            continue
        const = _GO_CONST.match(line)
        if const is not None:
            entities.append(RawEntity(
                kind="constant", name=const.group(1),
                qualified_name=f"{module_qname}.{const.group(1)}",
                line_start=number, line_end=number,
                parent_qualified_name=module_qname, detail="heuristic-const",
            ))
            understood.append((number, number))
        route = _GO_ROUTE.search(line)
        if route is not None:
            entities.append(RawEntity(
                kind="route", name=f"ANY {route.group(1)}",
                qualified_name=f"{module_qname}#route:ANY:{route.group(1)}",
                line_start=number, line_end=number,
                parent_qualified_name=module_qname, detail="heuristic-handlefunc",
            ))
            understood.append((number, number))
    return entities, imports, understood


# --- extraction entry point --------------------------------------------------


def extract_file(reader: RepositoryReader, path: str) -> FileExtract:
    """Extract one file's facts.  Pure with respect to ``(path, bytes)``."""

    meta = reader.stat(path)
    content_digest = str(meta.get("digest") or "")
    extension = _extension(path)
    language, extractor = _EXTRACTORS.get(extension, ("", "none"))

    if meta.get("oversized"):
        return FileExtract(
            path=path, language=language or "unknown", extractor="none",
            content_digest=content_digest, line_count=None, lines_measured=False,
            unindexed_reason="oversized-in-snapshot", module_qualified_name="",
        )
    try:
        data = reader.read_bytes(path)
    except KernelError as exc:
        if exc.code in {"INPUT_TOO_LARGE", "MISSING_REQUIRED_INPUT"}:
            return FileExtract(
                path=path, language=language or "unknown", extractor="none",
                content_digest=content_digest, line_count=None, lines_measured=False,
                unindexed_reason=f"unreadable:{exc.code}", module_qualified_name="",
            )
        raise
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return FileExtract(
            path=path, language=language or "binary", extractor="none",
            content_digest=content_digest, line_count=None, lines_measured=False,
            unindexed_reason="undecodable-utf8", module_qualified_name="",
        )

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    line_count = len(lines)

    if extractor == "none":
        return FileExtract(
            path=path, language=language or "unknown", extractor="none",
            content_digest=content_digest, line_count=line_count, lines_measured=True,
            unindexed_reason=f"no-extractor:{extension or 'no-extension'}",
            module_qualified_name="",
        )

    module_qname = _module_qualified_name(path, language, text)
    entities: list[RawEntity] = [RawEntity(
        kind="module", name=path.rsplit("/", 1)[-1], qualified_name=module_qname,
        line_start=1, line_end=max(line_count, 1),
        parent_qualified_name="", detail=f"{language} module",
    )]
    calls: list[RawCall] = []
    imports: list[RawImport] = []
    understood: list[tuple[int, int]] = list(_ignorable_lines(lines, language))

    try:
        if extractor == "ast":
            found, calls_found, imports_found, spans = _extract_python(
                path, text, module_qname)
            entities.extend(found)
            calls.extend(calls_found)
            imports.extend(imports_found)
            understood.extend(spans)
        elif extractor in {"json", "tomllib"}:
            found, spans = _extract_config(path, text, language, module_qname)
            entities.extend(found)
            understood.extend(spans)
            understood.append((1, max(line_count, 1)))
        elif language in {"JavaScript", "TypeScript"}:
            found, imports_found, spans = _extract_js(lines, module_qname)
            entities.extend(found)
            imports.extend(imports_found)
            understood.extend(spans)
        elif language == "Java":
            found, imports_found, spans = _extract_java(lines, module_qname)
            entities.extend(found)
            imports.extend(imports_found)
            understood.extend(spans)
        elif language == "Go":
            found, imports_found, spans = _extract_go(lines, module_qname)
            entities.extend(found)
            imports.extend(imports_found)
            understood.extend(spans)
    except (SyntaxError, ValueError, tomllib.TOMLDecodeError) as exc:
        # A file that does not parse contributes nothing but its own admission.
        # Emitting the entities found before the error would publish a truncated
        # view of the file as if it were complete.
        return FileExtract(
            path=path, language=language, extractor=extractor,
            content_digest=content_digest, line_count=line_count, lines_measured=True,
            unindexed_reason=f"parse-error:{type(exc).__name__}",
            module_qualified_name="",
        )

    return FileExtract(
        path=path, language=language, extractor=extractor,
        content_digest=content_digest, line_count=line_count, lines_measured=True,
        unindexed_reason="", module_qualified_name=module_qname,
        entities=tuple(entities), calls=tuple(calls), imports=tuple(imports),
        understood_lines=tuple(_merge_lines(sorted(_line_set(understood)))),
    )


# --- assembly ----------------------------------------------------------------


def _entity_id(repo_id: str, kind: str, qualified_name: str, path: str) -> str:
    return digest({
        "repoId": repo_id,
        "kind": kind,
        "qualifiedName": qualified_name,
        "path": path,
    })


def _symbol_uri(repo_id: str, language: str, kind: str, qualified_name: str,
                path: str) -> str:
    return f"elmos://symbol/{repo_id}/{language}/{kind}/{qualified_name}#{path}"


def _resolve_js_import(target: str, from_path: str, module_paths: Mapping[str, str]) -> str:
    if not target.startswith("."):
        return ""
    base = from_path.rsplit("/", 1)[0] if "/" in from_path else ""
    parts = [part for part in (base.split("/") if base else []) if part]
    for segment in target.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if not parts:
                return ""
            parts.pop()
        else:
            parts.append(segment)
    stem = "/".join(parts)
    for candidate in (stem, *(f"{stem}{ext}" for ext in _JS_MODULE_EXTENSIONS),
                      *(f"{stem}/index{ext}" for ext in _JS_MODULE_EXTENSIONS)):
        if candidate in module_paths:
            return module_paths[candidate]
    return ""


def _resolve_python_import(raw: RawImport, from_module: str) -> str:
    if raw.relative_level:
        parts = from_module.split(".")
        base = parts[: max(len(parts) - raw.relative_level, 0)]
        target = ".".join([*base, raw.module] if raw.module else base)
        return target
    return raw.module


def assemble(repo_id: str, snapshot_sha: str,
             extracts: Sequence[FileExtract]) -> Index:
    """Build the index from a complete set of per-file facts.

    All cross-file resolution lives here.  ``build`` and ``incremental`` differ
    only in how they obtain ``extracts``, which is why an incremental update can
    be byte-identical to a rebuild rather than merely similar to one.
    """

    files = tuple(sorted(extracts, key=lambda item: item.path))
    entities: dict[str, Entity] = {}
    module_entity_by_qname: dict[str, Entity] = {}
    module_entity_by_path: dict[str, Entity] = {}
    module_path_stem: dict[str, str] = {}

    for extract in files:
        for raw in extract.entities:
            entity_id = _entity_id(repo_id, raw.kind, raw.qualified_name, extract.path)
            if entity_id in entities:
                continue
            entity = Entity(
                entity_id=entity_id, kind=raw.kind, name=raw.name,
                qualified_name=raw.qualified_name, path=extract.path,
                language=extract.language, extractor=extract.extractor,
                line_start=raw.line_start, line_end=raw.line_end, detail=raw.detail,
                symbol_uri=_symbol_uri(repo_id, extract.language, raw.kind,
                                       raw.qualified_name, extract.path),
            )
            entities[entity_id] = entity
            if raw.kind == "module":
                previous = module_entity_by_qname.get(raw.qualified_name)
                if previous is not None and previous.path != extract.path:
                    raise KernelError(
                        code="SYMBOL_COLLISION",
                        message=(
                            f"module qualified name {raw.qualified_name!r} is claimed by "
                            f"both {previous.path!r} and {extract.path!r}"
                        ),
                        retryable=False,
                        recommended_action=(
                            "disambiguate the module paths; import resolution cannot be "
                            "correct while one name means two files"
                        ),
                        details={"qualifiedName": raw.qualified_name,
                                 "paths": sorted([previous.path, extract.path])},
                    )
                module_entity_by_qname[raw.qualified_name] = entity
                module_entity_by_path[extract.path] = entity
                stem = (extract.path.rsplit(".", 1)[0]
                        if "." in extract.path.rsplit("/", 1)[-1] else extract.path)
                module_path_stem[stem] = raw.qualified_name

    # Symbol tables used only for *confident* resolution.
    top_level_by_module: dict[str, dict[str, list[Entity]]] = {}
    for extract in files:
        table: dict[str, list[Entity]] = {}
        for raw in extract.entities:
            if raw.kind not in {"function", "class"}:
                continue
            if raw.parent_qualified_name != extract.module_qualified_name:
                continue
            entity = entities[_entity_id(repo_id, raw.kind, raw.qualified_name, extract.path)]
            table.setdefault(raw.name, []).append(entity)
        top_level_by_module[extract.module_qualified_name] = table

    edges: dict[tuple[str, str, str], list[tuple[str, int]]] = {}

    def add_edge(kind: str, source: str, target: str, path: str, line: int) -> None:
        edges.setdefault((kind, source, target), []).append((path, line))

    # contains
    for extract in files:
        by_qname = {raw.qualified_name: raw for raw in extract.entities}
        for raw in extract.entities:
            if not raw.parent_qualified_name:
                continue
            parent = by_qname.get(raw.parent_qualified_name)
            if parent is None:
                continue
            source = _entity_id(repo_id, parent.kind, parent.qualified_name, extract.path)
            target = _entity_id(repo_id, raw.kind, raw.qualified_name, extract.path)
            add_edge("contains", source, target, extract.path, raw.line_start)

    # imports (module -> module), only when the target resolves to an indexed module
    unresolved: list[tuple[str, str, int]] = []
    for extract in files:
        source_entity = module_entity_by_path.get(extract.path)
        if source_entity is None:
            continue
        for raw in extract.imports:
            target_qname = ""
            if extract.language == "Python":
                target_qname = _resolve_python_import(raw, extract.module_qualified_name)
            elif extract.language in {"JavaScript", "TypeScript"}:
                target_qname = _resolve_js_import(raw.module, extract.path, module_path_stem)
            elif extract.language == "Java":
                target_qname = raw.module
            target_entity = module_entity_by_qname.get(target_qname) if target_qname else None
            if target_entity is None or target_entity.entity_id == source_entity.entity_id:
                unresolved.append((extract.path, raw.module, raw.line))
                continue
            add_edge("imports", source_entity.entity_id, target_entity.entity_id,
                     extract.path, raw.line)

    # calls (Python only, and only where the callee is unambiguous)
    for extract in files:
        if extract.extractor != "ast":
            continue
        local_table = top_level_by_module.get(extract.module_qualified_name, {})
        for call in extract.calls:
            if call.attribute:
                continue
            caller_id = _caller_entity_id(repo_id, extract, call)
            if caller_id is None:
                continue
            candidates = local_table.get(call.callee_name, [])
            if len(candidates) != 1 and call.imported_from:
                target_module = _resolve_python_import(
                    RawImport(call.imported_from, "", call.line), extract.module_qualified_name)
                candidates = top_level_by_module.get(target_module, {}).get(
                    call.callee_name, [])
            if len(candidates) != 1:
                continue
            add_edge("calls", caller_id, candidates[0].entity_id, extract.path, call.line)

    relationships: list[Relationship] = []
    for (kind, source, target) in sorted(edges):
        evidence = tuple(sorted(set(edges[(kind, source, target)])))
        relationships.append(Relationship(
            relationship_id=digest({"kind": kind, "source": source, "target": target}),
            kind=kind, source_id=source, target_id=target, evidence=evidence,
        ))

    index = Index(
        repo_id=repo_id,
        snapshot_sha=snapshot_sha,
        entities=tuple(sorted(entities.values(), key=lambda e: e.entity_id)),
        relationships=tuple(relationships),
        files=files,
        unresolved_imports=tuple(sorted(set(unresolved))),
    )
    validate_index(index)
    return index


def _caller_entity_id(repo_id: str, extract: FileExtract, call: RawCall) -> str | None:
    for raw in extract.entities:
        if raw.qualified_name != call.caller_qualified_name:
            continue
        if raw.kind not in {"module", "function", "class"}:
            continue
        return _entity_id(repo_id, raw.kind, raw.qualified_name, extract.path)
    return None


def validate_index(index: Index) -> None:
    """Reject an index that cannot be true.

    A dangling edge is the signature failure of an incremental index: the file
    was evicted and something still points at its symbols.  It is raised as
    ``INDEX_INCONSISTENT`` rather than filtered out, because filtering would
    hide the eviction bug that produced it.
    """

    known = {entity.entity_id for entity in index.entities}
    dangling = [
        rel.relationship_id for rel in index.relationships
        if rel.source_id not in known or rel.target_id not in known
    ]
    if dangling:
        raise KernelError(
            code="INDEX_INCONSISTENT",
            message=f"{len(dangling)} relationship(s) reference an absent entity",
            retryable=False,
            recommended_action="rebuild the index; eviction did not remove all edges",
            details={"relationshipIds": sorted(dangling)[:32]},
        )
    seen: dict[str, str] = {}
    for entity in index.entities:
        previous = seen.get(entity.symbol_uri)
        if previous is not None and previous != entity.entity_id:
            raise KernelError(
                code="SYMBOL_COLLISION",
                message=f"symbol uri {entity.symbol_uri!r} maps to two entities",
                retryable=False,
                recommended_action="disambiguate the qualified names",
            )
        seen[entity.symbol_uri] = entity.entity_id


# --- public entry points -----------------------------------------------------


def _snapshot_sha(reader: RepositoryReader) -> str:
    sha = getattr(reader, "snapshot_sha", None)
    if not isinstance(sha, str) or not sha:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="reader does not expose a snapshot_sha",
            recommended_action="pass a RepositoryReader bound to an immutable snapshot",
        )
    return sha


def build(reader: RepositoryReader, *, repo_id: str = "repo") -> Index:
    """Full rebuild: extract every path in the snapshot, then assemble."""

    require_identifier(repo_id, "repo_id")
    sha = _snapshot_sha(reader)
    extracts = [extract_file(reader, path) for path in sorted(reader.list_paths())]
    return assemble(repo_id, sha, extracts)


def incremental(prior: Index, reader: RepositoryReader,
                changed_paths: Sequence[str]) -> tuple[Index, Delta]:
    """Reuse prior facts for untouched files; re-extract the rest; reassemble.

    Every reused fact is verified against the snapshot's content digest, and the
    path sets are reconciled, so an incomplete ``changed_paths`` raises
    ``INVALIDATION_MISS`` rather than producing an index that silently describes
    a repository state that never existed.
    """

    sha = _snapshot_sha(reader)
    changed = set(changed_paths)
    current = set(reader.list_paths())
    prior_by_path = {extract.path: extract for extract in prior.files}

    missing_declaration = sorted(
        (current - set(prior_by_path)) - changed
    ) + sorted((set(prior_by_path) - current) - changed)
    if missing_declaration:
        raise KernelError(
            code="INVALIDATION_MISS",
            message=(
                f"{len(missing_declaration)} path(s) were added or removed without being "
                "declared in changed_paths"
            ),
            retryable=False,
            recommended_action="recompute the change set or run a full rebuild",
            details={"paths": missing_declaration[:32]},
        )

    reindexed: list[tuple[str, str]] = []
    evicted: list[str] = []
    extracts: list[FileExtract] = []
    for path in sorted(current):
        if path in changed:
            extract = extract_file(reader, path)
            previous = prior_by_path.get(path)
            if previous is None:
                reason = "added"
            elif previous.content_digest != extract.content_digest:
                reason = "content-digest-changed"
            else:
                reason = "declared-changed-without-content-change"
            reindexed.append((path, reason))
            extracts.append(extract)
            continue
        previous = prior_by_path[path]
        observed = str(reader.stat(path).get("digest") or "")
        if observed != previous.content_digest:
            raise KernelError(
                code="INVALIDATION_MISS",
                message=(
                    f"{path!r} changed content but was not declared in changed_paths; "
                    "file timestamps are not a freshness signal, content digests are"
                ),
                retryable=False,
                recommended_action="recompute the change set or run a full rebuild",
                details={"path": path},
            )
        extracts.append(previous)

    for path in sorted(changed):
        if path in current:
            continue
        if path in prior_by_path:
            evicted.append(path)
            continue
        raise KernelError(
            code="INVALIDATION_MISS",
            message=f"{path!r} is in neither the snapshot nor the prior index",
            retryable=False,
            recommended_action="drop the path from the change set or re-snapshot",
            details={"path": path},
        )

    new_index = assemble(prior.repo_id, sha, extracts)
    prior_entities = {entity.entity_id for entity in prior.entities}
    new_entities = {entity.entity_id for entity in new_index.entities}
    prior_edges = {rel.relationship_id for rel in prior.relationships}
    new_edges = {rel.relationship_id for rel in new_index.relationships}
    delta = Delta(
        prior_digest=prior.to_payload()["indexDigest"],
        new_digest=new_index.to_payload()["indexDigest"],
        reindexed_paths=tuple(reindexed),
        evicted_paths=tuple(evicted),
        added_entity_ids=tuple(sorted(new_entities - prior_entities)),
        removed_entity_ids=tuple(sorted(prior_entities - new_entities)),
        added_relationship_ids=tuple(sorted(new_edges - prior_edges)),
        removed_relationship_ids=tuple(sorted(prior_edges - new_edges)),
    )
    return new_index, delta


_REQUEST_FIELDS = frozenset({"reader", "repoId", "priorIndex", "changedPaths", "snapshotSha"})


@register("incremental-semantic-index")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``incremental-semantic-index``.

    Passing ``priorIndex`` without ``changedPaths`` (or the reverse) is rejected
    rather than silently downgraded to a full rebuild: a caller who thinks an
    incremental update happened must not be handed a rebuild's cost, and a
    caller who thinks a rebuild happened must not be handed reused facts.
    """

    payload = require_mapping(request, "request")
    reject_unknown_fields(payload, _REQUEST_FIELDS,
                          field_name="incremental-semantic-index request")
    reader = payload.get("reader")
    if reader is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="incremental-semantic-index requires a 'reader'",
            recommended_action="pass adapters.filestore.SnapshotRepositoryReader",
        )
    if not isinstance(reader, RepositoryReader):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"'reader' of type {type(reader).__name__} is not a RepositoryReader",
            recommended_action="pass an object implementing the RepositoryReader port",
        )
    repo_id = require_identifier(payload.get("repoId", "repo"), "repoId")
    expected = payload.get("snapshotSha")
    if expected is not None and require_str(expected, "snapshotSha") != _snapshot_sha(reader):
        raise KernelError(
            code="STALE_SNAPSHOT",
            message="reader is bound to a different snapshot than the caller expected",
            retryable=False,
            recommended_action="re-take the snapshot and rebuild",
        )

    prior = payload.get("priorIndex")
    changed = payload.get("changedPaths")
    if (prior is None) != (changed is None):
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="priorIndex and changedPaths must be supplied together",
            recommended_action="supply both for an incremental update, or neither for a build",
        )

    if prior is None:
        index = build(reader, repo_id=repo_id)
        delta_payload: Mapping[str, Any] | None = None
    else:
        if not isinstance(prior, Index):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="priorIndex must be a semindex.Index produced by this kernel",
                recommended_action="pass the Index object, not its serialised payload",
            )
        if prior.repo_id != repo_id:
            raise KernelError(
                code="INDEX_INCONSISTENT",
                message=f"priorIndex is for repo {prior.repo_id!r}, request says {repo_id!r}",
                retryable=False,
                recommended_action="rebuild for the requested repository",
            )
        index, delta = incremental(
            prior, reader, require_str_seq(changed, "changedPaths"))
        delta_payload = delta.to_payload()

    body = index.to_payload()
    outputs: dict[str, Any] = {
        "status": index.status,
        "semanticIndex": body,
        "index": index,
        "symbolGraph": body["graphs"]["entities"],
        "callGraph": [
            rel for rel in body["graphs"]["relationships"] if rel["kind"] == "calls"
        ],
        "dependencyGraph": [
            rel for rel in body["graphs"]["relationships"] if rel["kind"] == "imports"
        ],
        "testImpactMap": body["testImpactMap"],
        "indexDigest": body["indexDigest"],
        "quality": body["quality"],
    }
    if delta_payload is not None:
        outputs["indexDelta"] = delta_payload
        outputs["invalidationSet"] = {
            "reindexed": delta_payload["reindexedPaths"],
            "evicted": delta_payload["evictedPaths"],
        }
    return outputs


def index_canonical_json(index: Index) -> str:
    """Canonical text of an index — the byte-level comparison used by the tests."""

    return canonical_json(index.to_payload())
