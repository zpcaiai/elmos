"""Bounded reconciliation of typed parser facts, source spans, CFG and evidence.

The explicit facts follow the repository's typed IR approach: named node kinds,
exact types and source origins, with unknown constructs preserved. This consumes
normalized parser projections; it does not import sibling engines, parse source,
or assert that their full native SemanticIR schemas are interchangeable.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any

from .canonical import (
    canonical_digest,
    canonical_value,
    digest_bytes,
    require_identifier,
    validate_digest,
)
from .domain import TenantScope
from .local_semantics import (
    CatalogView,
    LocalHandler,
    _exact_mapping,
    _mapping,
    _number,
    _response,
    _sequence,
    _text,
)
from .store import FoundryStore

SKILLS = frozenset({"semantic-ir-reconciliation"})
_INPUTS = {"normalized repository artifact", "build metadata", "runtime trace", "test result"}
_KINDS = {"symbol", "type", "control-node", "control-edge", "call"}
_NODE_KINDS = {"entry", "branch", "statement", "return", "exit", "throw"}
_PINNED_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}(?:[-+][A-Za-z0-9][A-Za-z0-9.-]*)?")


def _enum(value: Any, label: str, choices: set[str]) -> str:
    result = require_identifier(value, label)
    if result not in choices:
        raise ValueError(f"unsupported {label}: {result}")
    return result


def _integer(value: Any, label: str, *, minimum: int = 1, maximum: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return int(value)


def _path(value: Any) -> str:
    path = _text(value, "source path", maximum=512)
    normalized = PurePosixPath(path)
    if (
        normalized.is_absolute()
        or not normalized.parts
        or str(normalized) != path
        or ".." in normalized.parts
        or "\\" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        raise ValueError("source path must be an exact relative POSIX path")
    return path


def _typed_value(kind: str, value: Any, subject: str) -> Mapping[str, Any]:
    if kind == "symbol":
        obj = _exact_mapping(value, "symbol", {"qualified_name", "symbol_kind"})
        if obj["qualified_name"] != subject:
            raise ValueError("symbol identity differs from its qualified name")
        _enum(obj["symbol_kind"], "symbol_kind", {"function", "variable", "class"})
    elif kind == "type":
        obj = _mapping(value, "type")
        type_kind = _enum(
            obj.get("kind"),
            "type kind",
            {"integer", "float", "boolean", "string", "void", "nominal", "unknown"},
        )
        keys = {"kind", "nullable"}
        if type_kind == "integer":
            keys |= {"bits", "signed", "overflow"}
        elif type_kind == "float":
            keys |= {"bits", "format"}
        elif type_kind == "string":
            keys |= {"encoding"}
        elif type_kind == "nominal":
            keys |= {"language", "name"}
        elif type_kind == "unknown":
            keys |= {"reason"}
        _exact_mapping(obj, "type", keys)
        if type(obj["nullable"]) is not bool:
            raise ValueError("type.nullable must be boolean")
        if type_kind == "integer":
            if type(obj["signed"]) is not bool:
                raise ValueError("integer.signed must be boolean")
            overflow = _enum(obj["overflow"], "overflow", {"wrap", "trap", "unbounded"})
            if obj["bits"] == "unbounded":
                if overflow != "unbounded" or not obj["signed"]:
                    raise ValueError("unbounded integer type must be signed and unbounded")
            else:
                bits = _integer(obj["bits"], "integer.bits", maximum=128)
                if bits not in {8, 16, 32, 64, 128} or overflow == "unbounded":
                    raise ValueError("integer width and overflow semantics disagree")
        elif type_kind == "float":
            if (
                _integer(obj["bits"], "float.bits", maximum=64) not in {32, 64}
                or obj["format"] != "ieee754"
            ):
                raise ValueError("float requires exact IEEE754 width")
        elif type_kind == "string":
            _enum(
                obj["encoding"],
                "string encoding",
                {"unicode-codepoints", "utf16-codeunits", "utf8-bytes"},
            )
        elif type_kind == "nominal":
            require_identifier(obj["language"], "nominal.language")
            require_identifier(obj["name"], "nominal.name")
        elif type_kind == "unknown":
            _text(obj["reason"], "unknown type reason", maximum=1024)
        elif type_kind == "void" and obj["nullable"]:
            raise ValueError("void cannot be nullable")
    elif kind == "control-node":
        obj = _exact_mapping(value, "control node", {"function", "node_kind"})
        require_identifier(obj["function"], "function")
        _enum(obj["node_kind"], "node_kind", _NODE_KINDS)
    elif kind == "control-edge":
        obj = _exact_mapping(value, "control edge", {"function", "from", "to", "edge_kind"})
        for key in ("function", "from", "to"):
            require_identifier(obj[key], key)
        _enum(obj["edge_kind"], "edge_kind", {"next", "true", "false", "exception"})
    elif kind == "call":
        obj = _exact_mapping(value, "call", {"caller", "callee_file", "callee"})
        require_identifier(obj["caller"], "caller")
        require_identifier(obj["callee"], "callee")
        _path(obj["callee_file"])
    else:
        raise ValueError("unsupported typed fact kind")
    return dict(obj)


@dataclass(frozen=True)
class _Fact:
    parser: str
    file: str
    kind: str
    subject: str
    value: Mapping[str, Any]
    confidence: float
    status: str
    origin: Mapping[str, Any]

    @property
    def key(self) -> tuple[str, str, str]:
        return self.file, self.kind, self.subject

    @property
    def identity(self) -> str:
        return canonical_digest({"file": self.file, "kind": self.kind, "subject": self.subject})


def _source_files(
    value: Any, scope: TenantScope
) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]]]:
    artifact = _exact_mapping(
        value,
        "repository artifact",
        {
            "schema_version",
            "tenant_id",
            "project_id",
            "repository_id",
            "workspace_digest",
            "revision_set_id",
            "files",
        },
    )
    if artifact["schema_version"] != "elmos.foundry.reconciliation-input.v1":
        raise ValueError("unsupported reconciliation artifact schema")
    for key in ("tenant_id", "project_id", "workspace_digest", "revision_set_id"):
        if artifact[key] != getattr(scope, key):
            raise ValueError(f"repository artifact is outside authenticated {key}")
    require_identifier(artifact["repository_id"], "repository_id")
    files: dict[str, Mapping[str, Any]] = {}
    for raw in _sequence(artifact["files"], "files", maximum=64):
        item = _exact_mapping(raw, "file", {"path", "language", "source", "content_digest"})
        path = _path(item["path"])
        if path in files:
            raise ValueError("duplicate repository source path")
        require_identifier(item["language"], "source language")
        source = _text(item["source"], "source", maximum=65_536)
        if validate_digest(item["content_digest"]) != digest_bytes(source.encode("utf-8")):
            raise ValueError("repository source digest mismatch")
        files[path] = item
    return artifact, files


def _parsers(
    value: Any, artifact: Mapping[str, Any], files: Mapping[str, Mapping[str, Any]]
) -> tuple[
    list[_Fact],
    dict[str, Mapping[str, Any]],
    float,
]:
    metadata = _exact_mapping(
        value, "build metadata", {"repository_digest", "minimum_confidence", "parsers"}
    )
    if metadata["repository_digest"] != canonical_digest(artifact):
        raise ValueError("build metadata does not bind the repository artifact")
    threshold = _number(metadata["minimum_confidence"], "minimum_confidence")
    if not 0 <= threshold <= 1:
        raise ValueError("minimum confidence must be in [0,1]")
    parsers: dict[str, Mapping[str, Any]] = {}
    facts: list[_Fact] = []
    for raw in _sequence(metadata["parsers"], "parsers", maximum=8):
        parser = _exact_mapping(
            raw,
            "parser",
            {
                "parser_id",
                "version",
                "implementation_digest",
                "covered_files",
                "coverage_status",
                "facts",
            },
        )
        identity = require_identifier(parser["parser_id"], "parser_id")
        version = require_identifier(parser["version"], "parser version")
        if version.startswith("sha256:"):
            validate_digest(version, "parser version")
        elif _PINNED_VERSION.fullmatch(version) is None:
            raise ValueError("parser version must be pinned")
        validate_digest(parser["implementation_digest"], "implementation_digest")
        _enum(parser["coverage_status"], "coverage_status", {"COMPLETE", "PARTIAL", "NOT_RUN"})
        covered = [
            _path(item) for item in _sequence(parser["covered_files"], "covered_files", maximum=64)
        ]
        if len(covered) != len(set(covered)) or not set(covered) <= set(files):
            raise ValueError("parser coverage contains unknown or duplicate source files")
        if identity in parsers:
            raise ValueError("duplicate parser identity")
        parsers[identity] = {key: item for key, item in parser.items() if key != "facts"}
        seen: set[tuple[str, str, str]] = set()
        for raw_fact in _sequence(parser["facts"], "facts", minimum=0, maximum=1000):
            fact = _exact_mapping(
                raw_fact,
                "fact",
                {"file", "kind", "subject", "value", "status", "confidence", "origin"},
            )
            path = _path(fact["file"])
            if path not in covered:
                raise ValueError("fact lies outside its parser coverage")
            kind = _enum(fact["kind"], "fact kind", _KINDS)
            subject = require_identifier(fact["subject"], "fact subject")
            status = _enum(fact["status"], "fact status", {"OBSERVED", "UNKNOWN", "UNSUPPORTED"})
            confidence = _number(fact["confidence"], "fact confidence")
            if not 0 <= confidence <= 1:
                raise ValueError("fact confidence must be in [0,1]")
            origin = _exact_mapping(
                fact["origin"],
                "origin",
                {"content_digest", "start_line", "start_column", "end_line", "end_column"},
            )
            if origin["content_digest"] != files[path]["content_digest"]:
                raise ValueError("fact origin is bound to different source bytes")
            lines = str(files[path]["source"]).splitlines()
            start = (
                _integer(origin["start_line"], "start_line", maximum=len(lines)),
                _integer(origin["start_column"], "start_column"),
            )
            end = (
                _integer(origin["end_line"], "end_line", maximum=len(lines)),
                _integer(origin["end_column"], "end_column"),
            )
            if (
                start >= end
                or start[1] > len(lines[start[0] - 1]) + 1
                or end[1] > len(lines[end[0] - 1]) + 1
            ):
                raise ValueError("fact source span is reversed or out of bounds")
            if status == "OBSERVED":
                normalized = _typed_value(kind, fact["value"], subject)
                if (
                    kind == "type"
                    and normalized["kind"] == "nominal"
                    and normalized["language"] != files[path]["language"]
                ):
                    raise ValueError("nominal type language differs from its source language")
            else:
                normalized = dict(_exact_mapping(fact["value"], "unresolved fact", {"reason"}))
                _text(normalized["reason"], "unresolved reason", maximum=1024)
            parsed = _Fact(
                identity, path, kind, subject, normalized, confidence, status, dict(origin)
            )
            if parsed.key in seen:
                raise ValueError("a parser cannot assert two facts for the same semantic identity")
            seen.add(parsed.key)
            facts.append(parsed)
            if len(facts) > 2000:
                raise ValueError("reconciliation exceeds its 2000-fact budget")
        if parser["coverage_status"] == "NOT_RUN" and seen:
            raise ValueError("NOT_RUN parser cannot supply observed facts")
    return facts, parsers, threshold


def _graph_issues(resolved: Mapping[tuple[str, str, str], _Fact]) -> list[Mapping[str, Any]]:
    issues: list[Mapping[str, Any]] = []
    symbols = {
        (fact.file, fact.subject): fact for fact in resolved.values() if fact.kind == "symbol"
    }
    nodes = {
        (fact.file, fact.subject): fact for fact in resolved.values() if fact.kind == "control-node"
    }
    outgoing: dict[tuple[str, str], list[_Fact]] = defaultdict(list)
    groups: dict[tuple[str, str], list[_Fact]] = defaultdict(list)

    def problem(code: str, fact: _Fact) -> None:
        issues.append({"code": code, "fact_id": fact.identity})

    for fact in resolved.values():
        value = fact.value
        if fact.kind == "type" and (fact.file, fact.subject) not in symbols:
            problem("TYPE_WITHOUT_RESOLVED_SYMBOL", fact)
        elif fact.kind == "control-node":
            symbol = symbols.get((fact.file, str(value["function"])))
            if symbol is None or symbol.value["symbol_kind"] != "function":
                problem("CFG_WITHOUT_RESOLVED_FUNCTION", fact)
            groups[(fact.file, str(value["function"]))].append(fact)
        elif fact.kind == "control-edge":
            source, target = (
                nodes.get((fact.file, str(value["from"]))),
                nodes.get((fact.file, str(value["to"]))),
            )
            if source is None or target is None:
                problem("DANGLING_CONTROL_EDGE", fact)
            elif (
                source.value["function"] != value["function"]
                or target.value["function"] != value["function"]
            ):
                problem("CROSS_FUNCTION_CONTROL_EDGE", fact)
            else:
                outgoing[(fact.file, str(value["from"]))].append(fact)
        elif fact.kind == "call":
            caller = symbols.get((fact.file, str(value["caller"])))
            callee = symbols.get((str(value["callee_file"]), str(value["callee"])))
            if (
                caller is None
                or callee is None
                or caller.value["symbol_kind"] != "function"
                or callee.value["symbol_kind"] != "function"
            ):
                problem("UNRESOLVED_CALL_TARGET", fact)
    for (path, function), members in sorted(groups.items()):
        entries = [node for node in members if node.value["node_kind"] == "entry"]
        if len(entries) != 1:
            for node in members:
                problem("CFG_REQUIRES_ONE_ENTRY", node)
            continue
        reached = {entries[0].subject}
        queue = deque([entries[0].subject])
        while queue:
            for edge in outgoing[(path, queue.popleft())]:
                successor = str(edge.value["to"])
                if successor not in reached:
                    reached.add(successor)
                    queue.append(successor)
        for node in members:
            if node.subject not in reached:
                problem("UNREACHABLE_CONTROL_NODE", node)
            edges = outgoing[(path, node.subject)]
            kinds = [edge.value["edge_kind"] for edge in edges]
            if node.value["node_kind"] == "branch" and sorted(kinds) != ["false", "true"]:
                problem("BRANCH_REQUIRES_TRUE_AND_FALSE", node)
            elif node.value["node_kind"] in {"return", "exit", "throw"} and edges:
                problem("TERMINAL_CONTROL_NODE_HAS_OUTGOING_EDGE", node)
            elif node.value["node_kind"] in {"entry", "statement"} and (
                len(edges) != 1 or kinds != ["next"]
            ):
                problem("SEQUENTIAL_NODE_REQUIRES_ONE_NEXT_EDGE", node)
    return sorted(issues, key=canonical_digest)


def _evidence(
    raw: Any,
    label: str,
    artifact_digest: str,
    known: Mapping[str, Sequence[_Fact]],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    obj = _exact_mapping(raw, label, {"repository_digest", "status", "records"})
    if obj["repository_digest"] != artifact_digest:
        raise ValueError(f"{label} repository binding mismatch")
    status = _enum(obj["status"], f"{label} status", {"NOT_RUN", "COLLECTED_SELF_ATTESTED"})
    records = _sequence(obj["records"], f"{label} records", minimum=0, maximum=2000)
    if (status == "NOT_RUN") != (len(records) == 0):
        raise ValueError(f"{label} status and records disagree")
    result: list[Mapping[str, Any]] = []
    issues: list[Mapping[str, Any]] = []
    identities: set[str] = set()
    for raw_record in records:
        record = _exact_mapping(
            raw_record, "evidence record", {"record_id", "fact_id", "artifact", "artifact_digest"}
        )
        identity = require_identifier(record["record_id"], "record_id")
        if identity in identities:
            raise ValueError("duplicate evidence record identity")
        identities.add(identity)
        fact_id = validate_digest(record["fact_id"], "fact_id")
        if fact_id not in known:
            raise ValueError("evidence refers to an unknown semantic fact")
        artifact = _mapping(record["artifact"], "evidence artifact")
        if validate_digest(record["artifact_digest"], "artifact_digest") != canonical_digest(
            artifact
        ):
            raise ValueError("evidence artifact digest mismatch")
        if label == "runtime trace":
            sample = _exact_mapping(
                artifact, "trace observation", {"observed_value", "occurrences"}
            )
            _integer(sample["occurrences"], "occurrences")
            fact = known[fact_id][0]
            observed = _typed_value(fact.kind, sample["observed_value"], fact.subject)
            observed_digest = canonical_digest(observed)
            candidates = {
                canonical_digest(item.value) for item in known[fact_id] if item.status == "OBSERVED"
            }
            if observed_digest not in candidates:
                issues.append(
                    {
                        "code": "TRACE_CONTRADICTS_ALL_PARSER_FACTS",
                        "fact_id": fact_id,
                        "record_id": identity,
                    }
                )
            disposition = (
                "MATCHES_DECLARED_VARIANT" if observed_digest in candidates else "CONTRADICTS"
            )
        else:
            sample = _exact_mapping(
                artifact, "test observation", {"command", "exit_code", "outcome"}
            )
            for argument in _sequence(sample["command"], "test command", maximum=64):
                _text(argument, "test argument", maximum=2048)
            outcome = _enum(sample["outcome"], "test outcome", {"PASS", "FAIL", "NOT_RUN"})
            if outcome == "NOT_RUN":
                if sample["exit_code"] is not None:
                    raise ValueError("NOT_RUN test cannot have an exit code")
                issues.append({"code": "TEST_NOT_RUN", "fact_id": fact_id, "record_id": identity})
            else:
                exit_code = _integer(sample["exit_code"], "test exit_code", minimum=0, maximum=255)
                if (exit_code == 0) != (outcome == "PASS"):
                    raise ValueError("test outcome conflicts with its exit code")
                if outcome == "FAIL":
                    issues.append(
                        {"code": "TEST_FAILED", "fact_id": fact_id, "record_id": identity}
                    )
            disposition = outcome
        result.append(
            {
                "record_id": identity,
                "fact_id": fact_id,
                "artifact_digest": record["artifact_digest"],
                "disposition": disposition,
            }
        )
    return sorted(result, key=lambda row: str(row["record_id"])), issues


def _reconcile(
    skill: str,
    payload: Mapping[str, Any],
    scope: TenantScope,
    invocation: str,
) -> Mapping[str, Any]:
    if skill not in SKILLS:
        raise ValueError("unsupported exact IR reconciliation Skill")
    values = _exact_mapping(payload.get("inputs"), "inputs", _INPUTS)
    canonical_value(values)
    if any(not _mapping(values[key], key) for key in _INPUTS):
        raise ValueError("all required reconciliation inputs must be nonempty")
    artifact, files = _source_files(values["normalized repository artifact"], scope)
    facts, parsers, threshold = _parsers(values["build metadata"], artifact, files)
    grouped: dict[tuple[str, str, str], list[_Fact]] = defaultdict(list)
    known: dict[str, list[_Fact]] = defaultdict(list)
    for fact in facts:
        grouped[fact.key].append(fact)
        known[fact.identity].append(fact)
    reconciled: list[dict[str, Any]] = []
    resolved: dict[tuple[str, str, str], _Fact] = {}
    differences_by_id: dict[str, dict[str, Any]] = {}
    for key, assertions in sorted(grouped.items()):
        applicable = {name for name, parser in parsers.items() if key[0] in parser["covered_files"]}
        present = {fact.parser for fact in assertions}
        incomplete = sorted(
            name for name in applicable if parsers[name]["coverage_status"] != "COMPLETE"
        )
        variants: dict[str, list[_Fact]] = defaultdict(list)
        for fact in assertions:
            variants[canonical_digest({"status": fact.status, "value": fact.value})].append(fact)
        unresolved = any(
            fact.status != "OBSERVED"
            or (fact.kind == "type" and fact.value.get("kind") == "unknown")
            for fact in assertions
        )
        confidence = min(fact.confidence for fact in assertions)
        reasons = []
        if present != applicable:
            reasons.append("MISSING_PARSER_FACT")
        if incomplete:
            reasons.append("PARSER_COVERAGE_INCOMPLETE")
        if len(variants) > 1:
            reasons.append("CONFLICTING_FACT_VALUES")
        if len({canonical_digest(fact.origin) for fact in assertions}) > 1:
            reasons.append("SOURCE_ORIGIN_MISMATCH")
        if unresolved:
            reasons.append("UNKNOWN_OR_UNSUPPORTED_FACT")
        if confidence < threshold:
            reasons.append("BELOW_DECLARED_CONFIDENCE_THRESHOLD")
        state = "RESOLVED_LOCAL" if not reasons else "UNRESOLVED"
        first = assertions[0]
        row = {
            "fact_id": first.identity,
            "file": key[0],
            "kind": key[1],
            "subject": key[2],
            "state": state,
            "declared_confidence_floor": confidence,
            "variants": [
                {
                    "value": items[0].value,
                    "status": items[0].status,
                    "parser_ids": sorted(item.parser for item in items),
                    "origins": [
                        {"parser_id": item.parser, **item.origin}
                        for item in sorted(items, key=lambda item: item.parser)
                    ],
                }
                for _, items in sorted(variants.items())
            ],
        }
        reconciled.append(row)
        if reasons:
            differences_by_id[first.identity] = {
                "fact_id": first.identity,
                "reason_codes": reasons,
                "missing_parsers": sorted(applicable - present),
                "incomplete_parsers": incomplete,
            }
        else:
            resolved[key] = first
    artifact_digest = canonical_digest(artifact)
    traces, trace_issues = _evidence(
        values["runtime trace"], "runtime trace", artifact_digest, known
    )
    checks, test_issues = _evidence(values["test result"], "test result", artifact_digest, known)
    # Evidence and structural failures invalidate the affected facts themselves.
    # Repeat after removal so dependent types, calls and CFG references cannot
    # remain resolved through an already-unresolved fact. Each productive pass
    # removes at least one of the bounded input facts; facts are never restored.
    issues_by_digest: dict[str, Mapping[str, Any]] = {}
    pending_issues = trace_issues + test_issues + _graph_issues(resolved)
    while pending_issues:
        invalidated: set[str] = set()
        for issue in pending_issues:
            issues_by_digest[canonical_digest(issue)] = issue
            fact_id = str(issue["fact_id"])
            invalidated.add(fact_id)
            difference = differences_by_id.setdefault(
                fact_id,
                {
                    "fact_id": fact_id,
                    "reason_codes": [],
                    "missing_parsers": [],
                    "incomplete_parsers": [],
                },
            )
            if issue["code"] not in difference["reason_codes"]:
                difference["reason_codes"].append(issue["code"])
        retained = {key: fact for key, fact in resolved.items() if fact.identity not in invalidated}
        if len(retained) == len(resolved):
            break
        resolved = retained
        pending_issues = _graph_issues(resolved)
    for row in reconciled:
        if row["fact_id"] in differences_by_id:
            row["state"] = "UNRESOLVED"
    differences = [
        {**difference, "reason_codes": sorted(difference["reason_codes"])}
        for _, difference in sorted(differences_by_id.items())
    ]
    issues = list(issues_by_digest.values())
    uncovered_files = sorted(
        path
        for path in files
        if not any(path in parser["covered_files"] for parser in parsers.values())
    )
    if uncovered_files:
        issues.append({"code": "SOURCE_FILES_WITHOUT_PARSER", "files": uncovered_files})
    empty_coverage = sorted(
        name for name in parsers if not any(fact.parser == name for fact in facts)
    )
    if empty_coverage:
        issues.append({"code": "PARSER_HAS_NO_SEMANTIC_FACTS", "parser_ids": empty_coverage})
    factless_files = sorted(set(files) - {fact.file for fact in facts})
    if factless_files:
        issues.append({"code": "SOURCE_FILES_WITHOUT_SEMANTIC_FACTS", "files": factless_files})
    status = "RECONCILED_LOCAL" if reconciled and not differences and not issues else "PARTIAL"
    calls = [fact for fact in resolved.values() if fact.kind == "call"]
    modules = [
        {
            "path": path,
            "language": files[path]["language"],
            "resolved_symbol_count": sum(
                fact.file == path and fact.kind == "symbol" for fact in resolved.values()
            ),
            "resolved_type_count": sum(
                fact.file == path and fact.kind == "type" for fact in resolved.values()
            ),
        }
        for path in sorted(files)
    ]
    outputs: dict[str, Mapping[str, Any]] = {
        "semantic graph": {
            "repository_digest": artifact_digest,
            "facts": reconciled,
            "reconciliation_status": status,
            "source_executed": False,
        },
        "architecture model": {
            "modules": modules,
            "calls": [
                {"caller_file": fact.file, **fact.value, "fact_id": fact.identity}
                for fact in sorted(calls, key=lambda item: item.key)
            ],
            "architecture_recovered_from": "DECLARED_TYPED_FACTS_ONLY",
        },
        "semantic diff": {
            "fact_differences": differences,
            "consistency_issues": sorted(issues, key=canonical_digest),
            "trace_reconciliation": traces,
            "test_reconciliation": checks,
        },
        "confidence report": {
            "input_digest": canonical_digest(values),
            "reconciliation_status": status,
            "source_file_count": len(files),
            "input_fact_count": len(facts),
            "distinct_fact_count": len(grouped),
            "resolved_fact_count": len(resolved),
            "unresolved_fact_count": len(differences),
            "parser_count": len(parsers),
            "parser_versions": [parsers[name] for name in sorted(parsers)],
            "confidence_semantics": "minimum caller-declared confidence; never an independent probability",
            "source_span_convention": "one-based Unicode code points; end exclusive; nonempty",
            "minimum_declared_confidence": threshold,
            "observed_parse_coverage": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "language_equivalence_proven": False,
            "effects_authorized": False,
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
            "limitations": [
                "Normalized projections require stable semantic identities across parsers.",
                "No parser, compiler, runtime or replay command is executed.",
                "Agreement and supplied evidence do not establish native semantic or source completeness.",
                "Type aliases, subtyping, cross-language coercion and unsupported constructs are not inferred.",
            ],
        },
    }
    return _response(
        {
            name: {**output, "content_digest": canonical_digest(output)}
            for name, output in outputs.items()
        }
    )


def build_ir_reconciliation_handlers(
    catalog: CatalogView, store: FoundryStore | None
) -> dict[str, LocalHandler]:
    if not SKILLS <= set(catalog.atomic_skills):
        raise ValueError("semantic-ir-reconciliation is absent from the exact catalog")
    return {"semantic-ir-reconciliation": _reconcile}
