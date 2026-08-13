"""Fail-closed, artifact-specific layered equivalence for directed routes.

The source and emitted target are independently analysed.  This module then
compares their normalized semantic slices, maps path-stable semantic chunks,
compares canonical and native observations, and discharges an L0 denotational
equivalence obligation with Z3.  The proof deliberately stops at the
``typed-pure-function-v1`` boundary: compiler/analyzer soundness, emitter-rule
soundness, and target-specific domains remain explicit assumptions, and L1+
semantics never get silently approximated.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import struct
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import z3  # type: ignore[import-untyped]

from . import canonical, types
from .emitter import EmittedFile
from .identifier_hygiene import (
    IdentifierPlan,
    IdentifierUnitNamespace,
    alpha_normalize_target,
)
from .models import (
    TYPED_PURE_MODULE_PROFILE,
    Expression,
    Function,
    Language,
    RouteError,
    SemanticIR,
    SourceSpan,
    Statement,
    is_specialized_pair,
)

SCHEMA_VERSION = "1.0.0"
FORMAL_TIMEOUT_MS = 30_000
SAFE_INTEGER_MAX = 2**53 - 1
L1_PLUS_UNSUPPORTED = (
    "heap-and-object-identity",
    "mutable-state-and-aliasing",
    "exceptions-as-user-visible-control-flow",
    "async-and-concurrency",
    "io-network-database-and-framework-effects",
    "reflection-dynamic-loading-and-native-interop",
)
FORMAL_RELATION_SCOPE = "canonical-normalized-source-ir-to-target-relift-ir"
PURE_MODULE_PROFILE = TYPED_PURE_MODULE_PROFILE
SPECIALIZED_INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
NODEJS_INPUT_DOMAIN = "nodejs-es2022-esm-safe-integer-finite-v1"
SPECIALIZED_OUT_OF_DOMAIN_BEHAVIOR = "BLOCKED_NOT_EQUIVALENTLY_MODELED"
NODEJS_OUT_OF_DOMAIN_BEHAVIOR = "BLOCKED_OUTSIDE_NODEJS_ES2022_ESM_SAFE_INTEGER_FINITE_V1"


class EvidenceStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID = "INVALID"
    VACUOUS = "VACUOUS"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class DirectedRouteKey:
    source_language: Language
    target_language: Language
    profile: str
    source_artifact_sha256: str
    target_artifact_sha256: str
    corpus_sha256: str
    source_analyzer: str
    source_analyzer_version: str
    target_analyzer: str
    target_analyzer_version: str

    @property
    def route_id(self) -> str:
        return f"{self.source_language}-to-{self.target_language}"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "profile": self.profile,
            "source_artifact_sha256": self.source_artifact_sha256,
            "target_artifact_sha256": self.target_artifact_sha256,
            "corpus_sha256": self.corpus_sha256,
            "source_analyzer": self.source_analyzer,
            "source_analyzer_version": self.source_analyzer_version,
            "target_analyzer": self.target_analyzer,
            "target_analyzer_version": self.target_analyzer_version,
        }


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> str:
    path.write_bytes(canonical_json_bytes(value))
    return sha256_bytes(path.read_bytes())


def verify_content_reference(root: Path, reference: dict[str, Any]) -> None:
    """Fail closed when a relative artifact reference no longer matches bytes."""

    relative_path = reference.get("path")
    expected_digest = reference.get("sha256")
    if not isinstance(relative_path, str) or not relative_path or not isinstance(expected_digest, str):
        raise RouteError("CONTENT_REFERENCE_INVALID")
    resolved_root = root.resolve()
    candidate_path = resolved_root / relative_path
    resolved_path = candidate_path.resolve()
    if resolved_root not in resolved_path.parents or not candidate_path.is_file() or candidate_path.is_symlink():
        raise RouteError(f"CONTENT_REFERENCE_PATH_INVALID:{relative_path}")
    observed_digest = sha256_bytes(resolved_path.read_bytes())
    if observed_digest != expected_digest:
        raise RouteError(f"CONTENT_REFERENCE_DIGEST_MISMATCH:{relative_path}")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RouteError(f"FORMAL_INPUT_MAPPING_REQUIRED:{label}")
    return value


def _without_source_spans(value: Any) -> Any:
    """Return the semantic value used by hashes/proofs, excluding locations."""

    if isinstance(value, dict):
        return {key: _without_source_spans(item) for key, item in value.items() if key != "source_span"}
    if isinstance(value, list):
        return [_without_source_spans(item) for item in value]
    return value


def _verify_embedded_artifact(binding: dict[str, Any], label: str) -> None:
    encoded = binding.get("content_base64")
    expected_digest = binding.get("sha256")
    expected_bytes = binding.get("byte_count")
    if not isinstance(encoded, str) or not isinstance(expected_digest, str) or not isinstance(expected_bytes, int):
        raise RouteError(f"FORMAL_INPUT_ARTIFACT_INVALID:{label}")
    try:
        content = base64.b64decode(encoded, validate=True)
    except binascii.Error as error:
        raise RouteError(f"FORMAL_INPUT_ARTIFACT_BASE64_INVALID:{label}") from error
    if len(content) != expected_bytes or sha256_bytes(content) != expected_digest:
        raise RouteError(f"FORMAL_INPUT_ARTIFACT_DIGEST_MISMATCH:{label}")


def verify_formal_input_closure(root: Path, reference: dict[str, Any]) -> dict[str, Any]:
    """Verify the persisted formal input and every content-addressed child."""

    verify_content_reference(root, reference)
    relative_path = reference["path"]
    path = root.resolve() / str(relative_path)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("FORMAL_INPUT_JSON_INVALID") from error
    payload = _mapping(loaded, "root")
    if payload.get("kind") != "elmos.formal-equivalence-input":
        raise RouteError("FORMAL_INPUT_KIND_INVALID")
    claim_scope = _mapping(payload.get("claim_scope"), "claim_scope")
    if (
        claim_scope.get("relation") != FORMAL_RELATION_SCOPE
        or claim_scope.get("original_source_bytes_theorem") is not False
        or claim_scope.get("source_compiler_runtime_soundness") != "NOT_RUN"
    ):
        raise RouteError("FORMAL_INPUT_CLAIM_SCOPE_INVALID")
    _verify_embedded_artifact(_mapping(payload.get("source_artifact"), "source_artifact"), "source")
    _verify_embedded_artifact(_mapping(payload.get("target_artifact"), "target_artifact"), "target")
    artifact_roles = {
        "source_artifact": "original-source-analyzer-input",
        "target_artifact": "emitted-target-analyzer-input",
    }
    for label, expected_role in artifact_roles.items():
        binding = _mapping(payload.get(label), label)
        if binding.get("role") != expected_role:
            raise RouteError(f"FORMAL_INPUT_ARTIFACT_ROLE_INVALID:{label}")
        artifact_reference = _mapping(binding.get("content_reference"), f"{label}.content_reference")
        if artifact_reference.get("sha256") != binding.get("sha256"):
            raise RouteError(f"FORMAL_INPUT_ARTIFACT_REFERENCE_DRIFT:{label}")
        verify_content_reference(root, artifact_reference)
    ir_roles = {
        "source_normalized_ir": "canonical-source-normalized-ir",
        "target_relift_normalized_ir": "emitted-target-relift-normalized-ir",
    }
    for label, expected_role in ir_roles.items():
        binding = _mapping(payload.get(label), label)
        if binding.get("role") != expected_role:
            raise RouteError(f"FORMAL_INPUT_IR_ROLE_INVALID:{label}")
        artifact_reference = _mapping(binding.get("artifact"), f"{label}.artifact")
        verify_content_reference(root, artifact_reference)
        semantic_ir = _mapping(binding.get("semantic_ir"), f"{label}.semantic_ir")
        artifact_path = root.resolve() / str(artifact_reference["path"])
        try:
            persisted_semantic_ir_bytes = artifact_path.read_bytes()
            persisted_semantic_ir = json.loads(persisted_semantic_ir_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RouteError(f"FORMAL_INPUT_IR_ARTIFACT_JSON_INVALID:{label}") from error
        if persisted_semantic_ir != semantic_ir:
            raise RouteError(f"FORMAL_INPUT_IR_ARTIFACT_CONTENT_MISMATCH:{label}")
        canonical_semantic_ir_bytes = canonical_json_bytes(semantic_ir)
        canonical_semantic_ir_sha256 = sha256_bytes(canonical_semantic_ir_bytes)
        if artifact_reference.get("sha256") != canonical_semantic_ir_sha256:
            raise RouteError(f"FORMAL_INPUT_IR_ARTIFACT_DIGEST_MISMATCH:{label}")
        if persisted_semantic_ir_bytes != canonical_semantic_ir_bytes:
            raise RouteError(f"FORMAL_INPUT_IR_ARTIFACT_BYTES_MISMATCH:{label}")
        functions = semantic_ir.get("functions")
        if not isinstance(functions, list) or len(functions) != 1:
            raise RouteError(f"FORMAL_INPUT_FUNCTION_SET_INVALID:{label}")
        formal_function = _mapping(binding.get("formal_function"), f"{label}.formal_function")
        if formal_function != _without_source_spans(functions[0]):
            raise RouteError(f"FORMAL_INPUT_FUNCTION_DRIFT:{label}")
        if binding.get("semantic_ir_sha256") != canonical_semantic_ir_sha256:
            raise RouteError(f"FORMAL_INPUT_SEMANTIC_IR_DIGEST_MISMATCH:{label}")
        if binding.get("formal_function_sha256") != sha256_bytes(canonical_json_bytes(formal_function)):
            raise RouteError(f"FORMAL_INPUT_FUNCTION_DIGEST_MISMATCH:{label}")

    hygiene = _mapping(payload.get("identifier_hygiene"), "identifier_hygiene")
    if hygiene.get("kind") != "elmos.verified-alpha-normalization":
        raise RouteError("FORMAL_INPUT_IDENTIFIER_HYGIENE_KIND_INVALID")
    plan_reference = _mapping(hygiene.get("plan"), "identifier_hygiene.plan")
    verify_content_reference(root, plan_reference)
    plan_path = root.resolve() / str(plan_reference["path"])
    try:
        plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("FORMAL_INPUT_IDENTIFIER_PLAN_JSON_INVALID") from error
    plan = IdentifierPlan.from_mapping(_mapping(plan_payload, "identifier_hygiene.plan_payload"))
    unit_namespace = IdentifierUnitNamespace.from_mapping(
        _mapping(hygiene.get("unit_namespace"), "identifier_hygiene.unit_namespace")
    )
    if (
        hygiene.get("plan_digest") != plan.digest
        or plan_reference.get("sha256") != plan.digest
        or hygiene.get("policy_id") != plan.policy_id
        or hygiene.get("policy_sha256") != plan.policy_sha256
        or hygiene.get("unit_namespace_sha256") != unit_namespace.digest
        or plan.unit_namespace.to_mapping() != unit_namespace.to_mapping()
    ):
        raise RouteError("FORMAL_INPUT_IDENTIFIER_PLAN_BINDING_MISMATCH")

    source_binding = _mapping(payload.get("source_normalized_ir"), "source_normalized_ir")
    target_binding = _mapping(payload.get("target_relift_normalized_ir"), "target_relift_normalized_ir")
    source_ir = SemanticIR.from_mapping(_mapping(source_binding.get("semantic_ir"), "source_semantic_ir"))
    target_ir = SemanticIR.from_mapping(_mapping(target_binding.get("semantic_ir"), "target_semantic_ir"))
    raw_binding = _mapping(hygiene.get("raw_target_relift_ir"), "identifier_hygiene.raw_target_relift_ir")
    if raw_binding.get("role") != "emitted-target-relift-raw-ir":
        raise RouteError("FORMAL_INPUT_RAW_TARGET_IR_ROLE_INVALID")
    raw_reference = _mapping(raw_binding.get("artifact"), "identifier_hygiene.raw_target_relift_ir.artifact")
    verify_content_reference(root, raw_reference)
    raw_mapping = _mapping(raw_binding.get("semantic_ir"), "identifier_hygiene.raw_target_relift_ir.semantic_ir")
    raw_path = root.resolve() / str(raw_reference["path"])
    try:
        persisted_raw_bytes = raw_path.read_bytes()
        persisted_raw_mapping = json.loads(persisted_raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("FORMAL_INPUT_RAW_TARGET_IR_ARTIFACT_JSON_INVALID") from error
    if persisted_raw_mapping != raw_mapping:
        raise RouteError("FORMAL_INPUT_RAW_TARGET_IR_ARTIFACT_CONTENT_MISMATCH")
    canonical_raw_bytes = canonical_json_bytes(raw_mapping)
    canonical_raw_sha256 = sha256_bytes(canonical_raw_bytes)
    if raw_reference.get("sha256") != canonical_raw_sha256:
        raise RouteError("FORMAL_INPUT_RAW_TARGET_IR_ARTIFACT_DIGEST_MISMATCH")
    if persisted_raw_bytes != canonical_raw_bytes:
        raise RouteError("FORMAL_INPUT_RAW_TARGET_IR_ARTIFACT_BYTES_MISMATCH")
    raw_functions = raw_mapping.get("functions")
    if not isinstance(raw_functions, list) or len(raw_functions) != 1:
        raise RouteError("FORMAL_INPUT_RAW_TARGET_FUNCTION_SET_INVALID")
    raw_function = _mapping(raw_binding.get("formal_function"), "identifier_hygiene.raw_target_relift_ir.function")
    if (
        raw_function != _without_source_spans(raw_functions[0])
        or raw_binding.get("semantic_ir_sha256") != canonical_raw_sha256
        or raw_binding.get("formal_function_sha256") != sha256_bytes(canonical_json_bytes(raw_function))
    ):
        raise RouteError("FORMAL_INPUT_RAW_TARGET_IR_DRIFT")
    raw_target_ir = SemanticIR.from_mapping(raw_mapping)
    normalized = alpha_normalize_target(source_ir, raw_target_ir, plan)
    if normalized.to_mapping() != target_ir.to_mapping():
        raise RouteError("FORMAL_INPUT_ALPHA_NORMALIZATION_MISMATCH")
    normalized_reference = _mapping(hygiene.get("normalized_target_ir"), "identifier_hygiene.normalized_target_ir")
    if normalized_reference != _mapping(target_binding.get("artifact"), "target_relift_normalized_ir.artifact"):
        raise RouteError("FORMAL_INPUT_NORMALIZED_TARGET_REFERENCE_MISMATCH")
    if (
        hygiene.get("source_function_name") != source_ir.functions[0].name
        or hygiene.get("target_function_name") != raw_target_ir.functions[0].name
    ):
        raise RouteError("FORMAL_INPUT_IDENTIFIER_FUNCTION_BINDING_MISMATCH")
    return payload


def formal_solver_identity() -> dict[str, Any]:
    return {
        "name": "z3",
        "version": z3.get_version_string(),
        "timeout_ms": FORMAL_TIMEOUT_MS,
        "random_seed": 0,
        "theories": ["QF_BV", "FP", "Seq", "Bool", "Int"],
    }


def formal_environment_assumptions(
    source_language: Language,
    target_language: Language,
) -> list[str]:
    return [
        f"source-analyzer-soundness:{source_language}",
        f"target-analyzer-soundness:{target_language}",
        f"source-compiler-runtime-soundness-not-discharged:{source_language}",
        f"target-compiler-runtime-soundness-not-discharged:{target_language}",
        "canonical-semantics-encoding-soundness:z3-l0-v1",
        f"target-language-primitive-compensation-soundness:{target_language}",
        f"emitter-normalization-soundness:{target_language}",
    ]


def _canonical_view(ir: SemanticIR) -> dict[str, Any]:
    # Concrete source positions differ by language and formatting.  They are
    # evidence bindings, never semantic input to equivalence or SMT hashes.
    return {"functions": [function.semantic_mapping() for function in ir.functions]}


def semantic_equivalence(source: SemanticIR, target: SemanticIR) -> dict[str, Any]:
    source_view = _canonical_view(source)
    target_view = _canonical_view(target)
    differences: list[dict[str, Any]] = []
    if source.diagnostics:
        differences.append({"path": "/source/diagnostics", "value": list(source.diagnostics)})
    if target.diagnostics:
        differences.append({"path": "/target/diagnostics", "value": list(target.diagnostics)})
    if source_view != target_view:
        differences.append(
            {
                "path": "/functions",
                "source_sha256": sha256_bytes(canonical_json_bytes(source_view)),
                "target_sha256": sha256_bytes(canonical_json_bytes(target_view)),
            }
        )
    status = EvidenceStatus.PASSED if not differences else EvidenceStatus.FAILED
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.semantic-equivalence",
        "status": status,
        "source_view_sha256": sha256_bytes(canonical_json_bytes(source_view)),
        "target_view_sha256": sha256_bytes(canonical_json_bytes(target_view)),
        "difference_count": len(differences),
        "differences": differences,
    }


def _json_pointer_token(token: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(token):
        if token[index] != "~":
            result.append(token[index])
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise RouteError(f"INVALID_JSON_POINTER_ESCAPE:{token}")
        result.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(result)


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON Pointer against the canonical IR view."""

    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise RouteError(f"INVALID_JSON_POINTER:{pointer}")
    current = document
    for encoded_token in pointer[1:].split("/"):
        segment = _json_pointer_token(encoded_token)
        if isinstance(current, list):
            if segment != "0" and (not segment or segment.startswith("0") or not segment.isdecimal()):
                raise RouteError(f"INVALID_JSON_POINTER_ARRAY_INDEX:{pointer}")
            index = int(segment)
            if index >= len(current):
                raise RouteError(f"JSON_POINTER_NOT_FOUND:{pointer}")
            current = current[index]
        elif isinstance(current, dict):
            if segment not in current:
                raise RouteError(f"JSON_POINTER_NOT_FOUND:{pointer}")
            current = current[segment]
        else:
            raise RouteError(f"JSON_POINTER_NOT_CONTAINER:{pointer}")
    return current


def _chunk(
    path: str,
    kind: str,
    canonical_view: dict[str, Any],
    artifact_sha256: str,
    source_span: SourceSpan | None,
) -> dict[str, Any]:
    subtree = resolve_json_pointer(canonical_view, path)
    semantic_hash = sha256_bytes(canonical_json_bytes(subtree))
    return {
        "semantic_path": path,
        "kind": kind,
        "semantic_hash": semantic_hash,
        "chunk_id": sha256_bytes(f"{artifact_sha256}\0{path}\0{semantic_hash}".encode()),
        "artifact_sha256": artifact_sha256,
        "artifact_pointer": f"{artifact_sha256}#{path}",
        "concrete_span": source_span.to_mapping() if source_span is not None else None,
    }


def _expression_chunks(
    expression: Expression,
    path: str,
    artifact_sha256: str,
    canonical_view: dict[str, Any],
    result: list[dict[str, Any]],
) -> None:
    result.append(
        _chunk(
            path,
            f"expression:{expression.kind}",
            canonical_view,
            artifact_sha256,
            expression.source_span,
        )
    )
    if expression.kind == "binary" and expression.left is not None and expression.right is not None:
        _expression_chunks(expression.left, f"{path}/left", artifact_sha256, canonical_view, result)
        _expression_chunks(expression.right, f"{path}/right", artifact_sha256, canonical_view, result)


def _statement_chunks(
    statements: tuple[Statement, ...],
    path: str,
    artifact_sha256: str,
    canonical_view: dict[str, Any],
    result: list[dict[str, Any]],
) -> None:
    for index, statement in enumerate(statements):
        statement_path = f"{path}/{index}"
        result.append(
            _chunk(
                statement_path,
                f"statement:{statement.kind}",
                canonical_view,
                artifact_sha256,
                statement.source_span,
            )
        )
        if statement.expression is not None:
            _expression_chunks(
                statement.expression,
                f"{statement_path}/expression",
                artifact_sha256,
                canonical_view,
                result,
            )
        if statement.condition is not None:
            _expression_chunks(
                statement.condition,
                f"{statement_path}/condition",
                artifact_sha256,
                canonical_view,
                result,
            )
        _statement_chunks(statement.then_body, f"{statement_path}/then", artifact_sha256, canonical_view, result)
        _statement_chunks(statement.else_body, f"{statement_path}/else", artifact_sha256, canonical_view, result)


def semantic_chunks(ir: SemanticIR, artifact_sha256: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    canonical_view = _canonical_view(ir)
    for function_index, function in enumerate(ir.functions):
        function_path = f"/functions/{function_index}"
        result.append(
            _chunk(
                function_path,
                "function",
                canonical_view,
                artifact_sha256,
                function.source_span,
            )
        )
        for parameter_index, parameter in enumerate(function.parameters):
            result.append(
                _chunk(
                    f"{function_path}/parameters/{parameter_index}",
                    "parameter",
                    canonical_view,
                    artifact_sha256,
                    parameter.source_span,
                )
            )
        _statement_chunks(function.body, f"{function_path}/body", artifact_sha256, canonical_view, result)
    return result


@dataclass(frozen=True)
class _SpanTree:
    label: str
    span: SourceSpan | None
    children: tuple[_SpanTree, ...] = ()


def _expression_span_tree(expression: Expression, label: str) -> _SpanTree:
    children: tuple[_SpanTree, ...] = ()
    if expression.kind == "binary" and expression.left is not None and expression.right is not None:
        children = (
            _expression_span_tree(expression.left, f"{label}/left"),
            _expression_span_tree(expression.right, f"{label}/right"),
        )
    return _SpanTree(label, expression.source_span, children)


def _statement_span_tree(statement: Statement, label: str) -> _SpanTree:
    children: list[_SpanTree] = []
    if statement.expression is not None:
        children.append(_expression_span_tree(statement.expression, f"{label}/expression"))
    if statement.condition is not None:
        children.append(_expression_span_tree(statement.condition, f"{label}/condition"))
    children.extend(
        _statement_span_tree(child, f"{label}/then/{index}") for index, child in enumerate(statement.then_body)
    )
    children.extend(
        _statement_span_tree(child, f"{label}/else/{index}") for index, child in enumerate(statement.else_body)
    )
    return _SpanTree(label, statement.source_span, tuple(children))


def _function_span_tree(function: Function, index: int) -> _SpanTree:
    label = f"/functions/{index}"
    children = [
        _SpanTree(f"{label}/parameters/{parameter_index}", parameter.source_span)
        for parameter_index, parameter in enumerate(function.parameters)
    ]
    children.extend(
        _statement_span_tree(statement, f"{label}/body/{statement_index}")
        for statement_index, statement in enumerate(function.body)
    )
    return _SpanTree(label, function.source_span, tuple(children))


def _span_trees(ir: SemanticIR) -> tuple[_SpanTree, ...]:
    return tuple(_function_span_tree(function, index) for index, function in enumerate(ir.functions))


def validate_ir_source_spans(
    ir: SemanticIR,
    *,
    logical_file: str,
    artifact_bytes: bytes,
    role: str,
) -> dict[str, Any]:
    """Bind every syntax-node span to real bytes and validate its topology."""

    trees = _span_trees(ir)
    node_count = 0

    def validate_siblings(children: tuple[_SpanTree, ...], parent: SourceSpan | None) -> None:
        nonlocal node_count
        ranged: list[tuple[int, int, str]] = []
        for child in children:
            span = child.span
            if span is None:
                raise RouteError(f"SOURCE_SPAN_REQUIRED:{role}:{child.label}")
            node_count += 1
            if span.file != logical_file:
                raise RouteError(f"SOURCE_SPAN_FILE_MISMATCH:{role}:{child.label}")
            if span.end_byte > len(artifact_bytes):
                raise RouteError(f"SOURCE_SPAN_OUT_OF_BOUNDS:{role}:{child.label}")
            if parent is not None and (span.start_byte < parent.start_byte or span.end_byte > parent.end_byte):
                raise RouteError(f"SOURCE_SPAN_PARENT_COVERAGE_INVALID:{role}:{child.label}")
            ranged.append((span.start_byte, span.end_byte, child.label))
            validate_siblings(child.children, span)
        ranged.sort()
        for previous, current in zip(ranged, ranged[1:], strict=False):
            if previous[1] > current[0]:
                raise RouteError(f"SOURCE_SPAN_SIBLING_OVERLAP:{role}:{previous[2]}:{current[2]}")

    validate_siblings(trees, None)
    return {
        "status": EvidenceStatus.PASSED,
        "logical_file": logical_file,
        "artifact_sha256": sha256_bytes(artifact_bytes),
        "artifact_byte_count": len(artifact_bytes),
        "node_count": node_count,
        "rules": [
            "utf8-byte-offset-end-exclusive",
            "exact-logical-file",
            "within-artifact-bounds",
            "parent-covers-child",
            "siblings-do-not-overlap",
        ],
    }


def chunk_equivalence(
    source: SemanticIR,
    target: SemanticIR,
    source_artifact_sha256: str,
    target_artifact_sha256: str,
    emitted: EmittedFile,
    *,
    source_artifact_bytes: bytes | None = None,
    target_artifact_bytes: bytes | None = None,
    source_logical_file: str | None = None,
    target_logical_file: str | None = None,
    require_concrete_spans: bool = False,
) -> dict[str, Any]:
    source_chunks = semantic_chunks(source, source_artifact_sha256)
    target_chunks = semantic_chunks(target, target_artifact_sha256)
    source_by_path = {item["semantic_path"]: item for item in source_chunks}
    target_by_path = {item["semantic_path"]: item for item in target_chunks}
    mappings: list[dict[str, Any]] = []
    mismatch_count = 0
    for path, source_chunk in source_by_path.items():
        target_chunk = target_by_path.get(path)
        if target_chunk is None:
            mapping_status = "UNMAPPED"
            mismatch_count += 1
        elif target_chunk["semantic_hash"] != source_chunk["semantic_hash"]:
            mapping_status = "HASH_MISMATCH"
            mismatch_count += 1
        elif require_concrete_spans and source_chunk["concrete_span"] is None:
            mapping_status = "SOURCE_SPAN_MISSING"
            mismatch_count += 1
        elif require_concrete_spans and target_chunk["concrete_span"] is None:
            mapping_status = "TARGET_SPAN_MISSING"
            mismatch_count += 1
        else:
            mapping_status = "EXACT"
        mappings.append(
            {
                "semantic_path": path,
                "status": mapping_status,
                "source_chunk_id": source_chunk["chunk_id"],
                "target_chunk_id": target_chunk["chunk_id"] if target_chunk else None,
                "source_artifact_pointer": source_chunk["artifact_pointer"],
                "target_artifact_pointer": target_chunk["artifact_pointer"] if target_chunk else None,
                "source_semantic_pointer": path,
                "target_semantic_pointer": path if target_chunk else None,
                "source_span": source_chunk["concrete_span"],
                "target_span": target_chunk["concrete_span"] if target_chunk else None,
                "semantic_hash": source_chunk["semantic_hash"],
            }
        )
    unexpected = sorted(set(target_by_path) - set(source_by_path))
    mapped = sum(1 for item in mappings if item["status"] == "EXACT")
    required = len(source_chunks)
    coverage = mapped / required if required else 0.0
    span_validation: dict[str, Any] = {
        "status": EvidenceStatus.NOT_RUN if require_concrete_spans else "NOT_REQUIRED",
        "reason": (
            "CONCRETE_ARTIFACT_BYTES_AND_LOGICAL_PATHS_REQUIRED"
            if require_concrete_spans
            else "LEGACY_COMPLETE_MATRIX_SEMANTIC_POINTER_PROFILE"
        ),
    }
    spans_complete = all(item["concrete_span"] is not None for item in (*source_chunks, *target_chunks))
    if (
        require_concrete_spans
        and spans_complete
        and all(
            item is not None
            for item in (
                source_artifact_bytes,
                target_artifact_bytes,
                source_logical_file,
                target_logical_file,
            )
        )
    ):
        assert source_artifact_bytes is not None
        assert target_artifact_bytes is not None
        assert source_logical_file is not None
        assert target_logical_file is not None
        if sha256_bytes(source_artifact_bytes) != source_artifact_sha256:
            raise RouteError("SOURCE_CHUNK_ARTIFACT_DIGEST_MISMATCH")
        if sha256_bytes(target_artifact_bytes) != target_artifact_sha256:
            raise RouteError("TARGET_CHUNK_ARTIFACT_DIGEST_MISMATCH")
        span_validation = {
            "status": EvidenceStatus.PASSED,
            "source": validate_ir_source_spans(
                source,
                logical_file=source_logical_file,
                artifact_bytes=source_artifact_bytes,
                role="source",
            ),
            "target": validate_ir_source_spans(
                target,
                logical_file=target_logical_file,
                artifact_bytes=target_artifact_bytes,
                role="target",
            ),
        }
    status = (
        EvidenceStatus.PASSED
        if (
            required > 0
            and mismatch_count == 0
            and not unexpected
            and coverage == 1.0
            and (not require_concrete_spans or span_validation["status"] == EvidenceStatus.PASSED)
        )
        else EvidenceStatus.FAILED
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.chunk-equivalence",
        "status": status,
        "path_scheme": "rfc6901-json-pointer-v1",
        "hash_scheme": "sha256-canonical-semantic-subtree-v1",
        "span_scheme": "relative-file-utf8-byte-range-end-exclusive-v1",
        "concrete_spans_required": require_concrete_spans,
        "span_validation": span_validation,
        "required_source_chunk_count": required,
        "mapped_source_chunk_count": mapped,
        "mismatch_count": mismatch_count,
        "missing_source_span_count": sum(1 for item in source_chunks if item["concrete_span"] is None),
        "missing_target_span_count": sum(1 for item in target_chunks if item["concrete_span"] is None),
        "unexpected_target_chunk_count": len(unexpected),
        "unexpected_target_paths": unexpected,
        "coverage": coverage,
        "normalization_rules": list(emitted.normalization_rules),
        "helper_digests": [{"helper_id": helper_id, "sha256": digest} for helper_id, digest in emitted.helper_digests],
        "mappings": mappings,
    }


def _same_value(left: object, right: object, value_type: str) -> bool:
    """Compare observations using the UIR type, not the JSON host type.

    JSON has only one numeric production, so an FP64 value such as ``120.0``
    may be decoded as either ``120`` or ``120.0`` depending on the runtime's
    serializer.  The declared ``number`` contract is the authority: normalize
    both observations to binary64 and compare the exact bits.  Integer,
    boolean, and string observations remain type-strict.
    """

    if value_type == "number":
        if isinstance(left, bool) or isinstance(right, bool):
            return False
        if not isinstance(left, int | float) or not isinstance(right, int | float):
            return False
        left_float = float(left)
        right_float = float(right)
        if math.isnan(left_float) and math.isnan(right_float):
            return True
        return struct.pack(">d", left_float) == struct.pack(">d", right_float)
    if value_type == "integer":
        return (
            isinstance(left, int)
            and not isinstance(left, bool)
            and isinstance(right, int)
            and not isinstance(right, bool)
            and left == right
        )
    if value_type == "boolean":
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if value_type == "string":
        return isinstance(left, str) and isinstance(right, str) and left == right
    return False


def _normalize_independent_expected(value: object, value_type: str) -> object:
    """Normalize only the representation of a typed independent oracle value.

    JSON does not retain the distinction between an integer token used for a
    canonical ``number`` and an FP64 value such as ``5.0``.  Persist behavior
    evidence in the representation required by the declared return type so
    downstream byte-level closure checks compare like with like.  This must
    remain independent of canonical and native observations: an integer is
    widened only when the conversion is exact, while every other type remains
    strict.  Existing floats are returned unchanged, preserving negative-zero
    and their binary64 bit pattern.
    """

    if value_type == "number":
        if type(value) is float:
            return value
        if type(value) is int:
            try:
                normalized = float(value)
            except OverflowError as error:
                raise RouteError("BEHAVIOR_EXPECTED_NUMBER_NOT_EXACT_BINARY64") from error
            if not math.isfinite(normalized) or int(normalized) != value:
                raise RouteError("BEHAVIOR_EXPECTED_NUMBER_NOT_EXACT_BINARY64")
            return normalized
        raise RouteError("BEHAVIOR_EXPECTED_TYPE_MISMATCH:number")
    if value_type == "integer":
        if type(value) is int:
            return value
        raise RouteError("BEHAVIOR_EXPECTED_TYPE_MISMATCH:integer")
    if value_type == "boolean":
        if type(value) is bool:
            return value
        raise RouteError("BEHAVIOR_EXPECTED_TYPE_MISMATCH:boolean")
    if value_type == "string":
        if type(value) is str:
            return value
        raise RouteError("BEHAVIOR_EXPECTED_TYPE_MISMATCH:string")
    raise RouteError(f"BEHAVIOR_EXPECTED_TYPE_UNSUPPORTED:{value_type}")


def behavior_equivalence(
    function: Function,
    cases: list[dict[str, Any]],
    source_observations: list[dict[str, Any]],
    target_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    source_by_case = {int(item["case_id"]): item for item in source_observations}
    target_by_case = {int(item["case_id"]): item for item in target_observations}
    results: list[dict[str, Any]] = []
    pass_count = 0
    source_pass_count = 0
    target_pass_count = 0
    oracle_conflicts = 0
    counterexamples: list[dict[str, Any]] = []
    for case_id, case in enumerate(cases):
        canonical_status = "RETURNED"
        canonical_value: object | None = None
        canonical_error: str | None = None
        try:
            canonical_value = canonical.evaluate(function, list(case["args"])).value
        except canonical.CanonicalError as error:
            canonical_status = "ERROR"
            canonical_error = type(error).__name__
        source_native = source_by_case.get(case_id)
        target_native = target_by_case.get(case_id)
        expected = _normalize_independent_expected(case["expected"], function.return_type)
        oracle_agrees = canonical_status == "RETURNED" and _same_value(
            canonical_value,
            expected,
            function.return_type,
        )
        if not oracle_agrees:
            oracle_conflicts += 1
        source_agrees = (
            source_native is not None
            and source_native.get("status") == canonical_status
            and canonical_status == "RETURNED"
            and _same_value(canonical_value, source_native.get("value"), function.return_type)
        )
        target_agrees = (
            target_native is not None
            and target_native.get("status") == canonical_status
            and canonical_status == "RETURNED"
            and _same_value(canonical_value, target_native.get("value"), function.return_type)
        )
        if source_agrees:
            source_pass_count += 1
        if target_agrees:
            target_pass_count += 1
        passed = oracle_agrees and source_agrees and target_agrees
        if passed:
            pass_count += 1
        else:
            counterexamples.append(
                {
                    "counterexample_id": sha256_bytes(
                        canonical_json_bytes(
                            {
                                "case_id": case_id,
                                "args": case["args"],
                                "canonical": canonical_value,
                                "source_native": source_native,
                                "target_native": target_native,
                                "expected": expected,
                            }
                        )
                    ),
                    "layer": "behavior",
                    "case_id": case_id,
                    "arguments": case["args"],
                    "canonical": {"status": canonical_status, "value": canonical_value, "error": canonical_error},
                    "source_native": source_native,
                    "target_native": target_native,
                    "expected": expected,
                    "replay": {"kind": "case-index", "case_id": case_id},
                }
            )
        results.append(
            {
                "case_id": case_id,
                "arguments_sha256": sha256_bytes(canonical_json_bytes(case["args"])),
                "canonical": {"status": canonical_status, "value": canonical_value, "error": canonical_error},
                "source_native": source_native,
                "target_native": target_native,
                "independent_expected": expected,
                "status": EvidenceStatus.PASSED if passed else EvidenceStatus.FAILED,
            }
        )
    status = EvidenceStatus.PASSED if pass_count == len(cases) and cases else EvidenceStatus.FAILED
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.behavior-equivalence",
        "status": status,
        "case_count": len(cases),
        "pass_count": pass_count,
        "source_runtime_pass_count": source_pass_count,
        "target_runtime_pass_count": target_pass_count,
        "source_runtime_passed": bool(cases) and source_pass_count == len(cases),
        "target_runtime_passed": bool(cases) and target_pass_count == len(cases),
        "oracle_conflict_count": oracle_conflicts,
        "counterexample_count": len(counterexamples),
        "results": results,
        "counterexamples": counterexamples,
    }


@dataclass
class _ExpressionDenotation:
    value: Any
    value_type: str
    error: Any


@dataclass
class _FunctionDenotation:
    returned: Any
    value: Any
    error: Any
    path: Any
    value_type: str


class _UnsupportedFormal(RouteError):
    pass


class _Encoder:
    def __init__(self, role: str, function: Function, runtime_language: Language) -> None:
        self.role = role
        self.function = function
        self.runtime_language = runtime_language
        self.environment_types = types.environment_of(function)
        self.environment: dict[str, Any] = {}
        self.assumptions: list[Any] = []
        self.assumption_labels: list[str] = []
        for parameter in function.parameters:
            variable = self._variable(f"{role}_{parameter.name}", parameter.type)
            self.environment[parameter.name] = variable
            if runtime_language in {"typescript", "javascript"} and parameter.type == "integer":
                self._safe_integer_assumption(variable, f"parameter:{parameter.name}")

    @staticmethod
    def _variable(name: str, value_type: str) -> Any:
        if value_type == "integer":
            return z3.BitVec(name, 64)
        if value_type == "boolean":
            return z3.Bool(name)
        if value_type == "string":
            return z3.String(name)
        if value_type == "number":
            return z3.FP(name, z3.Float64())
        raise _UnsupportedFormal(f"FORMAL_TYPE_UNSUPPORTED:{value_type}")

    @staticmethod
    def _default(value_type: str) -> Any:
        if value_type == "integer":
            return z3.BitVecVal(0, 64)
        if value_type == "boolean":
            return z3.BoolVal(False)
        if value_type == "string":
            return z3.StringVal("")
        if value_type == "number":
            return z3.FPVal(0.0, z3.Float64())
        raise _UnsupportedFormal(f"FORMAL_TYPE_UNSUPPORTED:{value_type}")

    def _safe_integer_assumption(self, value: Any, label: str) -> None:
        signed = z3.BV2Int(value, is_signed=True)
        self.assumptions.append(z3.And(signed >= -SAFE_INTEGER_MAX, signed <= SAFE_INTEGER_MAX))
        self.assumption_labels.append(f"{self.runtime_language}-safe-integer:{label}")

    def _finite_number_assumption(self, value: Any, label: str) -> None:
        self.assumptions.append(
            z3.And(
                z3.Not(z3.fpIsNaN(value)),
                z3.Not(z3.fpIsInf(value)),
            )
        )
        self.assumption_labels.append(f"{self.runtime_language}-finite-number:{label}")

    @staticmethod
    def _first_error(left: Any, right: Any) -> Any:
        return z3.If(left != 0, left, right)

    @staticmethod
    def _overflow(operator: str, left: Any, right: Any) -> tuple[Any, Any]:
        left_wide = z3.SignExt(64, left)
        right_wide = z3.SignExt(64, right)
        if operator == "+":
            wide = left_wide + right_wide
        elif operator == "-":
            wide = left_wide - right_wide
        elif operator == "*":
            wide = left_wide * right_wide
        else:
            raise _UnsupportedFormal(f"FORMAL_INTEGER_OPERATOR_UNSUPPORTED:{operator}")
        value = z3.Extract(63, 0, wide)
        return value, wide != z3.SignExt(64, value)

    @staticmethod
    def _numeric_value(value: Any, source_type: str, target_type: str) -> Any:
        if source_type == target_type:
            return value
        if source_type == "integer" and target_type == "number":
            return z3.fpSignedToFP(z3.RNE(), value, z3.Float64())
        raise _UnsupportedFormal(f"FORMAL_NUMERIC_COERCION_UNSUPPORTED:{source_type}:{target_type}")

    def expression(self, expression: Expression) -> _ExpressionDenotation:
        if expression.kind == "name":
            name = str(expression.value)
            if name not in self.environment:
                raise _UnsupportedFormal(f"FORMAL_UNDECLARED_NAME:{name}")
            return _ExpressionDenotation(self.environment[name], self.environment_types[name], z3.IntVal(0))
        if expression.kind == "literal":
            value_type = types.literal_type(expression.value)
            if value_type == "integer":
                if not isinstance(expression.value, int) or isinstance(expression.value, bool):
                    raise _UnsupportedFormal("FORMAL_INTEGER_LITERAL_INVALID")
                value = z3.BitVecVal(expression.value, 64)
            elif value_type == "number":
                if not isinstance(expression.value, float):
                    raise _UnsupportedFormal("FORMAL_NUMBER_LITERAL_INVALID")
                if (
                    self.runtime_language in {"typescript", "javascript"}
                    and expression.value == 0.0
                    and math.copysign(1.0, expression.value) < 0
                ):
                    raise _UnsupportedFormal(f"{self.runtime_language.upper()}_NEGATIVE_ZERO_LITERAL_UNSUPPORTED")
                value = z3.FPVal(expression.value, z3.Float64())
            elif value_type == "boolean":
                value = z3.BoolVal(bool(expression.value))
            elif value_type == "string":
                value = z3.StringVal(str(expression.value))
            else:
                raise _UnsupportedFormal(f"FORMAL_LITERAL_UNSUPPORTED:{value_type}")
            return _ExpressionDenotation(value, value_type, z3.IntVal(0))
        if expression.kind != "binary" or expression.left is None or expression.right is None:
            raise _UnsupportedFormal(f"FORMAL_EXPRESSION_UNSUPPORTED:{expression.kind}")
        operator = expression.operator or ""
        left = self.expression(expression.left)
        right = self.expression(expression.right)
        if operator in {"&&", "||"}:
            if left.value_type != "boolean" or right.value_type != "boolean":
                raise _UnsupportedFormal("FORMAL_LOGICAL_TYPE_MISMATCH")
            if operator == "&&":
                value = z3.And(left.value, right.value)
                right_error = z3.If(left.value, right.error, z3.IntVal(0))
            else:
                value = z3.Or(left.value, right.value)
                right_error = z3.If(left.value, z3.IntVal(0), right.error)
            return _ExpressionDenotation(value, "boolean", self._first_error(left.error, right_error))
        prior_error = self._first_error(left.error, right.error)
        result_type = types.infer(expression, self.environment_types)
        if operator in types.ARITHMETIC_OPERATORS:
            if operator == "+" and result_type == "string":
                return _ExpressionDenotation(z3.Concat(left.value, right.value), "string", prior_error)
            if result_type == "integer":
                if operator in {"+", "-", "*"}:
                    value, overflow = self._overflow(operator, left.value, right.value)
                    operation_error = z3.If(overflow, z3.IntVal(1), z3.IntVal(0))
                elif operator in {"/", "%"}:
                    minimum = z3.BitVecVal(-(2**63), 64)
                    negative_one = z3.BitVecVal(-1, 64)
                    zero = z3.BitVecVal(0, 64)
                    divide_error = z3.Or(
                        right.value == zero,
                        z3.And(left.value == minimum, right.value == negative_one),
                    )
                    operation_error = z3.If(divide_error, z3.IntVal(2), z3.IntVal(0))
                    value = left.value / right.value if operator == "/" else z3.SRem(left.value, right.value)
                else:
                    raise _UnsupportedFormal(f"FORMAL_INTEGER_OPERATOR_UNSUPPORTED:{operator}")
                if self.runtime_language in {"typescript", "javascript"}:
                    self._safe_integer_assumption(value, f"expression:{operator}:{len(self.assumptions)}")
                error = z3.If(prior_error != 0, prior_error, operation_error)
                return _ExpressionDenotation(value, "integer", error)
            if result_type == "number":
                left_value = self._numeric_value(left.value, left.value_type, "number")
                right_value = self._numeric_value(right.value, right.value_type, "number")
                if operator == "+":
                    value = z3.fpAdd(z3.RNE(), left_value, right_value)
                elif operator == "-":
                    value = z3.fpSub(z3.RNE(), left_value, right_value)
                elif operator == "*":
                    value = z3.fpMul(z3.RNE(), left_value, right_value)
                elif operator == "/":
                    value = z3.fpDiv(z3.RNE(), left_value, right_value)
                elif operator == "%":
                    value = z3.fpRem(left_value, right_value)
                else:
                    raise _UnsupportedFormal(f"FORMAL_FLOAT_OPERATOR_UNSUPPORTED:{operator}")
                zero_error = z3.fpIsZero(right_value) if operator in {"/", "%"} else z3.BoolVal(False)
                operation_error = z3.If(zero_error, z3.IntVal(2), z3.IntVal(0))
                if self.runtime_language in {"typescript", "javascript"}:
                    self._finite_number_assumption(
                        value,
                        f"expression:{operator}:{len(self.assumptions)}",
                    )
                return _ExpressionDenotation(
                    value,
                    "number",
                    z3.If(prior_error != 0, prior_error, operation_error),
                )
            raise _UnsupportedFormal(f"FORMAL_ARITHMETIC_TYPE_UNSUPPORTED:{result_type}")
        if operator in types.ORDERING_OPERATORS | types.EQUALITY_OPERATORS:
            if left.value_type in types.NUMERIC_TYPES and right.value_type in types.NUMERIC_TYPES:
                comparison_type = "number" if "number" in {left.value_type, right.value_type} else "integer"
                left_value = self._numeric_value(left.value, left.value_type, comparison_type)
                right_value = self._numeric_value(right.value, right.value_type, comparison_type)
                if comparison_type == "number":
                    value = {
                        "<": z3.fpLT(left_value, right_value),
                        "<=": z3.fpLEQ(left_value, right_value),
                        ">": z3.fpGT(left_value, right_value),
                        ">=": z3.fpGEQ(left_value, right_value),
                        "==": z3.fpEQ(left_value, right_value),
                        "!=": z3.Not(z3.fpEQ(left_value, right_value)),
                    }[operator]
                else:
                    value = {
                        "<": left_value < right_value,
                        "<=": left_value <= right_value,
                        ">": left_value > right_value,
                        ">=": left_value >= right_value,
                        "==": left_value == right_value,
                        "!=": left_value != right_value,
                    }[operator]
            elif operator in types.EQUALITY_OPERATORS and left.value_type == right.value_type:
                value = left.value == right.value
                if operator == "!=":
                    value = z3.Not(value)
            else:
                raise _UnsupportedFormal(f"FORMAL_COMPARISON_TYPE_UNSUPPORTED:{operator}")
            return _ExpressionDenotation(value, "boolean", prior_error)
        raise _UnsupportedFormal(f"FORMAL_OPERATOR_UNSUPPORTED:{operator}")

    def _coerce_return(self, expression: _ExpressionDenotation) -> Any:
        return self._numeric_value(expression.value, expression.value_type, self.function.return_type)

    @staticmethod
    def _branch_token(path: str, taken: bool) -> int:
        digest = hashlib.sha256(f"{path}:{taken}".encode()).digest()
        return int.from_bytes(digest[:7], "big")

    def statements(
        self,
        statements: tuple[Statement, ...],
        path: str,
        fallback: _FunctionDenotation | None = None,
    ) -> _FunctionDenotation:
        current = fallback or _FunctionDenotation(
            z3.BoolVal(False),
            self._default(self.function.return_type),
            z3.IntVal(0),
            z3.IntVal(0),
            self.function.return_type,
        )
        for index in range(len(statements) - 1, -1, -1):
            statement = statements[index]
            statement_path = f"{path}/{index}:{statement.kind}"
            if statement.kind == "return" and statement.expression is not None:
                expression = self.expression(statement.expression)
                current = _FunctionDenotation(
                    z3.BoolVal(True),
                    self._coerce_return(expression),
                    expression.error,
                    z3.IntVal(0),
                    self.function.return_type,
                )
                continue
            if statement.kind == "if" and statement.condition is not None:
                condition = self.expression(statement.condition)
                if condition.value_type != "boolean":
                    raise _UnsupportedFormal("FORMAL_CONDITION_NOT_BOOLEAN")
                then_value = self.statements(statement.then_body, f"{statement_path}/then", current)
                else_value = self.statements(statement.else_body, f"{statement_path}/else", current)
                branch_error = z3.If(condition.value, then_value.error, else_value.error)
                branch_path = z3.If(
                    condition.value,
                    z3.IntVal(self._branch_token(statement_path, True)) + then_value.path * 131,
                    z3.IntVal(self._branch_token(statement_path, False)) + else_value.path * 131,
                )
                current = _FunctionDenotation(
                    z3.If(condition.value, then_value.returned, else_value.returned),
                    z3.If(condition.value, then_value.value, else_value.value),
                    z3.If(condition.error != 0, condition.error, branch_error),
                    branch_path,
                    self.function.return_type,
                )
                continue
            raise _UnsupportedFormal(f"FORMAL_STATEMENT_UNSUPPORTED:{statement.kind}")
        return current

    def encode(self) -> _FunctionDenotation:
        denotation = self.statements(self.function.body, "/body")
        if self.runtime_language in {"typescript", "javascript"} and self.function.return_type == "number":
            self._finite_number_assumption(denotation.value, "return")
        return denotation


def _value_divergence(left: _FunctionDenotation, right: _FunctionDenotation) -> Any:
    if left.value_type != right.value_type:
        return z3.BoolVal(True)
    if left.value_type == "number":
        return z3.fpToIEEEBV(left.value) != z3.fpToIEEEBV(right.value)
    return left.value != right.value


def _substitute_denotation(
    denotation: _FunctionDenotation,
    substitutions: list[tuple[Any, Any]],
) -> _FunctionDenotation:
    if not substitutions:
        return denotation
    pairs = tuple(substitutions)
    return _FunctionDenotation(
        returned=z3.substitute(denotation.returned, *pairs),
        value=z3.substitute(denotation.value, *pairs),
        error=z3.substitute(denotation.error, *pairs),
        path=z3.substitute(denotation.path, *pairs),
        value_type=denotation.value_type,
    )


def _denotation_digest(denotation: _FunctionDenotation) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "returned": denotation.returned.sexpr(),
                "value": denotation.value.sexpr(),
                "error": denotation.error.sexpr(),
                "path": denotation.path.sexpr(),
                "value_type": denotation.value_type,
            }
        )
    )


def _solver_unknown_status(reason: str) -> EvidenceStatus:
    return EvidenceStatus.TIMEOUT if "timeout" in reason.lower() else EvidenceStatus.UNKNOWN


def formal_equivalence(
    source: Function,
    target: Function,
    source_language: Language,
    target_language: Language,
    input_digest: str,
    *,
    formal_input_reference: dict[str, str] | None = None,
    input_domain: str | None = None,
) -> tuple[dict[str, Any], str]:
    formal_input = dict(formal_input_reference) if formal_input_reference else None
    specialized_pair = is_specialized_pair(source_language, target_language)
    selected_input_domain = input_domain or (SPECIALIZED_INPUT_DOMAIN if specialized_pair else "profile-total-domain")
    if selected_input_domain not in {
        SPECIALIZED_INPUT_DOMAIN,
        NODEJS_INPUT_DOMAIN,
        "profile-total-domain",
    }:
        raise RouteError(f"FORMAL_INPUT_DOMAIN_UNSUPPORTED:{selected_input_domain}")
    no_error_domain = selected_input_domain in {SPECIALIZED_INPUT_DOMAIN, NODEJS_INPUT_DOMAIN}
    input_reference_valid = formal_input is None or (
        isinstance(formal_input.get("path"), str) and formal_input.get("sha256") == input_digest
    )
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.formal-equivalence-result",
        "property_id": "L0-DENOTATIONAL-EQUIVALENCE",
        "proof_strength": "THEOREM_UNDER_ASSUMPTIONS",
        "input_digest": input_digest,
        "formal_input_digest": input_digest,
        "formal_input": formal_input,
        "claim_scope": {
            "relation": FORMAL_RELATION_SCOPE,
            "source_term": "source normalized Function from canonical IR",
            "target_term": "independently re-lifted target normalized Function",
            "original_source_bytes_theorem": False,
            "input_domain": selected_input_domain,
        },
        "solver": formal_solver_identity(),
        "assumption_boundary": (
            f"typed-pure-function-v1 / L0 / {selected_input_domain}"
            if no_error_domain
            else "typed-pure-function-v1 / L0 only"
        ),
        "external_soundness_boundary": {
            "source_compiler_runtime_soundness": "NOT_RUN",
            "target_compiler_runtime_soundness": "NOT_RUN",
            "analyzer_and_emitter_soundness": "ASSUMPTION",
        },
        "unsupported_semantics": list(L1_PLUS_UNSUPPORTED),
        "certification_status": "NOT_CERTIFIED",
    }
    smt2_header = (
        f"; formal_input_digest: {input_digest}\n"
        f"; formal-input-sha256: {input_digest}\n"
        f"; claim-scope: {FORMAL_RELATION_SCOPE}\n"
        f"; input-domain: {selected_input_domain}\n"
        "; original-source-bytes-theorem: false\n"
    )
    if formal_input is not None:
        smt2_header += f"; formal-input-path: {formal_input['path']}\n"
    if not input_reference_valid:
        result = {
            **base,
            "status": EvidenceStatus.INVALID,
            "property_status": EvidenceStatus.INVALID,
            "reason": "FORMAL_INPUT_REFERENCE_DIGEST_MISMATCH",
            "assumptions": formal_environment_assumptions(source_language, target_language),
            "countermodel": None,
        }
        return result, smt2_header + "; formal input reference invalid\n"
    try:
        source_encoder = _Encoder("source", source, source_language)
        target_encoder = _Encoder("target", target, target_language)
        source_value = source_encoder.encode()
        target_value = target_encoder.encode()
    except (_UnsupportedFormal, RouteError, z3.Z3Exception) as error:
        result = {
            **base,
            "status": EvidenceStatus.UNSUPPORTED,
            "property_status": EvidenceStatus.UNSUPPORTED,
            "reason": str(error),
            "assumptions": [],
            "countermodel": None,
        }
        return result, smt2_header + "; formal encoding unsupported\n"

    encoded_assumptions: list[Any] = []
    input_substitutions: list[tuple[Any, Any]] = []
    assumption_labels = formal_environment_assumptions(source_language, target_language)
    if len(source.parameters) != len(target.parameters):
        result = {
            **base,
            "status": EvidenceStatus.UNSUPPORTED,
            "property_status": EvidenceStatus.UNSUPPORTED,
            "reason": "FORMAL_PARAMETER_COUNT_MISMATCH",
            "assumptions": assumption_labels,
            "countermodel": None,
        }
        return result, smt2_header + "; parameter count mismatch\n"
    for source_parameter, target_parameter in zip(source.parameters, target.parameters, strict=True):
        if source_parameter.type != target_parameter.type:
            result = {
                **base,
                "status": EvidenceStatus.UNSUPPORTED,
                "property_status": EvidenceStatus.UNSUPPORTED,
                "reason": "FORMAL_PARAMETER_TYPE_MISMATCH",
                "assumptions": assumption_labels,
                "countermodel": None,
            }
            return result, smt2_header + "; parameter type mismatch\n"
        source_variable = source_encoder.environment[source_parameter.name]
        target_variable = target_encoder.environment[target_parameter.name]
        input_substitutions.append((target_variable, source_variable))
        if source_parameter.type == "number":
            encoded_assumptions.append(z3.fpToIEEEBV(source_variable) == z3.fpToIEEEBV(target_variable))
            if no_error_domain:
                encoded_assumptions.extend(
                    [
                        z3.Not(z3.fpIsNaN(source_variable)),
                        z3.Not(z3.fpIsInf(source_variable)),
                        z3.Not(z3.fpIsNaN(target_variable)),
                        z3.Not(z3.fpIsInf(target_variable)),
                    ]
                )
                assumption_labels.extend(
                    [
                        f"canonical-finite-input-domain:source:{source_parameter.name}",
                        f"canonical-finite-input-domain:target:{target_parameter.name}",
                    ]
                )
        else:
            encoded_assumptions.append(source_variable == target_variable)
        assumption_labels.append(f"same-input:{source_parameter.name}:{target_parameter.name}")
    encoded_assumptions.extend(source_encoder.assumptions)
    encoded_assumptions.extend(
        z3.substitute(assumption, *tuple(input_substitutions)) if input_substitutions else assumption
        for assumption in target_encoder.assumptions
    )
    assumption_labels.extend(source_encoder.assumption_labels)
    assumption_labels.extend(target_encoder.assumption_labels)
    aligned_target_value = _substitute_denotation(target_value, input_substitutions)
    if no_error_domain:
        # Raw integer error behavior differs across these source languages:
        # Java wraps, Swift traps, and C++/Objective-C signed overflow is
        # undefined, while emitted targets use explicit checked helpers.  The
        # only behavior theorem that can honestly bridge this exact route set
        # is therefore the machine-checkable domain on which neither
        # canonical denotation raises an arithmetic error.  Satisfiability is
        # checked below, so an empty safe domain cannot pass vacuously.
        encoded_assumptions.extend([source_value.error == 0, aligned_target_value.error == 0])
        assumption_labels.extend(
            [
                "canonical-no-error-domain:source",
                "canonical-no-error-domain:target",
            ]
        )
    divergence = z3.simplify(
        z3.Or(
            source_value.error != aligned_target_value.error,
            source_value.returned != aligned_target_value.returned,
            source_value.path != aligned_target_value.path,
            z3.And(
                source_value.error == 0,
                aligned_target_value.error == 0,
                source_value.returned,
                aligned_target_value.returned,
                _value_divergence(source_value, aligned_target_value),
            ),
        )
    )
    encoding_evidence = {
        "source_denotation_sha256": _denotation_digest(source_value),
        "target_denotation_sha256": _denotation_digest(target_value),
        "input_alignment": "positional-substitution-after-independent-encoding",
        "source_symbol_prefix": "source_",
        "target_symbol_prefix": "target_",
    }
    satisfiability = z3.Solver()
    satisfiability.set(timeout=FORMAL_TIMEOUT_MS, random_seed=0)
    satisfiability.add(*encoded_assumptions)
    assumption_verdict = satisfiability.check()
    if assumption_verdict != z3.sat:
        unknown_reason = satisfiability.reason_unknown()
        assumption_status = (
            EvidenceStatus.VACUOUS if assumption_verdict == z3.unsat else _solver_unknown_status(unknown_reason)
        )
        result = {
            **base,
            "status": assumption_status,
            "property_status": assumption_status,
            "reason": "ASSUMPTIONS_NOT_SATISFIABLE" if assumption_status == EvidenceStatus.VACUOUS else unknown_reason,
            "assumptions": assumption_labels,
            "countermodel": None,
            "independent_encodings": encoding_evidence,
        }
        return result, smt2_header + satisfiability.sexpr()

    solver = z3.Solver()
    solver.set(timeout=FORMAL_TIMEOUT_MS, random_seed=0)
    solver.add(*encoded_assumptions)
    solver.add(divergence)
    smt2 = (
        smt2_header + f"; independent-source-denotation-sha256: {encoding_evidence['source_denotation_sha256']}\n"
        f"; independent-target-denotation-sha256: {encoding_evidence['target_denotation_sha256']}\n"
        f"; input-alignment: {encoding_evidence['input_alignment']}\n" + solver.to_smt2()
    )
    verdict = solver.check()
    countermodel: dict[str, Any] | None = None
    if verdict == z3.unsat:
        property_status: str = "PROVED"
        status: str = "PROVED_UNDER_ASSUMPTIONS"
        reason = "divergence formula is UNSAT under the recorded assumptions"
    elif verdict == z3.sat:
        property_status = "COUNTEREXAMPLE"
        status = EvidenceStatus.FAILED
        reason = "divergence formula is SAT"
        model = solver.model()
        countermodel = {
            "inputs": [
                {
                    "source_parameter": source_parameter.name,
                    "target_parameter": target_parameter.name,
                    "source_value": str(
                        model.eval(source_encoder.environment[source_parameter.name], model_completion=True)
                    ),
                    "target_value": str(
                        model.eval(target_encoder.environment[target_parameter.name], model_completion=True)
                    ),
                }
                for source_parameter, target_parameter in zip(source.parameters, target.parameters, strict=True)
            ],
            "source_error": str(model.eval(source_value.error, model_completion=True)),
            "target_error": str(model.eval(target_value.error, model_completion=True)),
            "source_returned": str(model.eval(source_value.returned, model_completion=True)),
            "target_returned": str(model.eval(target_value.returned, model_completion=True)),
            "source_value": str(model.eval(source_value.value, model_completion=True)),
            "target_value": str(model.eval(target_value.value, model_completion=True)),
            "source_path": str(model.eval(source_value.path, model_completion=True)),
            "target_path": str(model.eval(target_value.path, model_completion=True)),
            "replay": {"kind": "formal-countermodel", "input_digest": input_digest},
        }
    else:
        reason = solver.reason_unknown()
        property_status = _solver_unknown_status(reason)
        status = property_status
    result = {
        **base,
        "status": status,
        "property_status": property_status,
        "reason": reason,
        "assumptions": assumption_labels,
        "countermodel": countermodel,
        "independent_encodings": encoding_evidence,
    }
    return result, smt2


def _module_function_index(ir: SemanticIR, role: str) -> dict[str, Function]:
    """Validate and index an independent typed-pure module.

    The current IR has no call, assignment, field, heap, or I/O node.  This
    traversal is still explicit so manually constructed dataclasses cannot
    bypass the profile by smuggling an unknown node kind past ``from_mapping``.
    """

    if ir.diagnostics:
        raise RouteError(f"PURE_MODULE_DIAGNOSTICS:{role}")
    if len(ir.functions) < 3:
        raise RouteError(f"PURE_MODULE_AT_LEAST_THREE_FUNCTIONS_REQUIRED:{role}")
    index: dict[str, Function] = {}

    def validate_expression(expression: Expression, symbol: str) -> None:
        if expression.kind not in {"name", "literal", "binary"}:
            if expression.kind in {"call", "invoke"}:
                raise RouteError(f"PURE_MODULE_CALLS_UNSUPPORTED:{role}:{symbol}")
            raise RouteError(f"PURE_MODULE_EXPRESSION_UNSUPPORTED:{role}:{symbol}:{expression.kind}")
        if expression.kind == "binary":
            if expression.left is None or expression.right is None:
                raise RouteError(f"PURE_MODULE_BINARY_INVALID:{role}:{symbol}")
            validate_expression(expression.left, symbol)
            validate_expression(expression.right, symbol)

    def validate_statements(statements: tuple[Statement, ...], symbol: str) -> None:
        for statement in statements:
            if statement.kind not in {"return", "if"}:
                if statement.kind in {"assign", "assignment", "variable", "field-write"}:
                    raise RouteError(f"PURE_MODULE_STATE_UNSUPPORTED:{role}:{symbol}")
                raise RouteError(f"PURE_MODULE_STATEMENT_UNSUPPORTED:{role}:{symbol}:{statement.kind}")
            if statement.expression is not None:
                validate_expression(statement.expression, symbol)
            if statement.condition is not None:
                validate_expression(statement.condition, symbol)
            validate_statements(statement.then_body, symbol)
            validate_statements(statement.else_body, symbol)

    for function in ir.functions:
        if function.name in index:
            raise RouteError(f"PURE_MODULE_DUPLICATE_SYMBOL:{role}:{function.name}")
        validate_statements(function.body, function.name)
        types.check_function(function)
        index[function.name] = function
    return index


def _case_value_matches_type(value: Any, expected_type: str) -> bool:
    try:
        actual_type = types.literal_type(value)
    except RouteError:
        return False
    return actual_type == expected_type or (actual_type == "integer" and expected_type == "number")


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = ",".join(sorted(expected - observed))
        extra = ",".join(sorted(observed - expected))
        raise RouteError(f"PURE_MODULE_MANIFEST_KEYS_INVALID:{label}:missing={missing}:extra={extra}")


def validate_pure_module_manifest_shape(manifest: dict[str, Any]) -> None:
    """Reject ambiguous or extensible-looking module manifests.

    The profile is intentionally closed.  A future field changes the contract
    and therefore requires a new profile/schema instead of being ignored.
    """

    _require_exact_keys(
        manifest,
        {"schema_version", "profile", "composition", "functions"},
        "root",
    )
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("profile") != PURE_MODULE_PROFILE:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_PROFILE_INVALID")
    composition = manifest.get("composition")
    expected_compositions = (
        {
            "call_graph": [],
            "global_state": "none",
            "effects": "none",
            "exceptions": "canonical-arithmetic-errors-only",
            "input_domain": SPECIALIZED_INPUT_DOMAIN,
        },
        {
            "call_graph": [],
            "global_state": "none",
            "effects": "none",
            "exceptions": "domain-guards-fail-closed-before-execution",
            "input_domain": NODEJS_INPUT_DOMAIN,
        },
    )
    if not isinstance(composition, dict) or composition not in expected_compositions:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_COMPOSITION_INVALID")
    entries = manifest.get("functions")
    if not isinstance(entries, list):
        raise RouteError("PURE_MODULE_CASE_MANIFEST_FUNCTIONS_REQUIRED")
    for entry_index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise RouteError("PURE_MODULE_CASE_MANIFEST_ENTRY_INVALID")
        _require_exact_keys(entry, {"symbol", "signature", "cases"}, f"function:{entry_index}")
        signature = entry.get("signature")
        if not isinstance(signature, dict):
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_SIGNATURE_INVALID:{entry_index}")
        _require_exact_keys(signature, {"parameters", "return_type"}, f"signature:{entry_index}")
        parameters = signature.get("parameters")
        if not isinstance(parameters, list):
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_PARAMETERS_INVALID:{entry_index}")
        for parameter_index, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                raise RouteError(f"PURE_MODULE_CASE_MANIFEST_PARAMETER_INVALID:{entry_index}:{parameter_index}")
            _require_exact_keys(
                parameter,
                {"name", "type"},
                f"parameter:{entry_index}:{parameter_index}",
            )
        cases = entry.get("cases")
        if not isinstance(cases, list):
            raise RouteError(f"PURE_MODULE_CASES_REQUIRED:{entry_index}")
        for case_index, case in enumerate(cases):
            if not isinstance(case, dict):
                raise RouteError(f"PURE_MODULE_CASE_INVALID:{entry_index}:{case_index}")
            _require_exact_keys(case, {"args", "expected"}, f"case:{entry_index}:{case_index}")


def normalize_pure_module_case_manifest(
    manifest: dict[str, Any],
    functions: dict[str, Function],
) -> dict[str, list[dict[str, Any]]]:
    """Validate an exact, signature-bound case set for every module symbol."""

    validate_pure_module_manifest_shape(manifest)
    entries = manifest.get("functions")
    if not isinstance(entries, list) or not entries:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_FUNCTIONS_REQUIRED")
    normalized: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RouteError("PURE_MODULE_CASE_MANIFEST_ENTRY_INVALID")
        symbol = str(entry.get("symbol", "")).strip()
        if not symbol or symbol in normalized:
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_DUPLICATE_SYMBOL:{symbol}")
        function = functions.get(symbol)
        if function is None:
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_UNKNOWN_SYMBOL:{symbol}")
        signature = entry.get("signature")
        if not isinstance(signature, dict) or signature != function.signature_mapping():
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_SIGNATURE_MISMATCH:{symbol}")
        cases = entry.get("cases")
        if not isinstance(cases, list) or not cases:
            raise RouteError(f"PURE_MODULE_CASES_REQUIRED:{symbol}")
        normalized_cases: list[dict[str, Any]] = []
        case_digests: set[str] = set()
        for case_index, case in enumerate(cases):
            if not isinstance(case, dict) or not isinstance(case.get("args"), list) or "expected" not in case:
                raise RouteError(f"PURE_MODULE_CASE_INVALID:{symbol}:{case_index}")
            arguments = case["args"]
            if len(arguments) != len(function.parameters):
                raise RouteError(f"PURE_MODULE_CASE_ARGUMENT_COUNT_MISMATCH:{symbol}:{case_index}")
            for parameter, argument in zip(function.parameters, arguments, strict=True):
                if not _case_value_matches_type(argument, parameter.type):
                    raise RouteError(f"PURE_MODULE_CASE_ARGUMENT_TYPE_MISMATCH:{symbol}:{case_index}:{parameter.name}")
            if not _case_value_matches_type(case["expected"], function.return_type):
                raise RouteError(f"PURE_MODULE_CASE_EXPECTED_TYPE_MISMATCH:{symbol}:{case_index}")
            normalized_case = {"args": list(arguments), "expected": case["expected"]}
            case_digest = sha256_bytes(canonical_json_bytes(normalized_case))
            if case_digest in case_digests:
                raise RouteError(f"PURE_MODULE_DUPLICATE_CASE:{symbol}:{case_index}")
            case_digests.add(case_digest)
            normalized_cases.append(normalized_case)
        normalized[symbol] = normalized_cases
    if set(normalized) != set(functions):
        missing = ",".join(sorted(set(functions) - set(normalized)))
        extra = ",".join(sorted(set(normalized) - set(functions)))
        raise RouteError(f"PURE_MODULE_CASE_MANIFEST_SYMBOL_SET_MISMATCH:missing={missing}:extra={extra}")
    return normalized


def module_equivalence(
    *,
    source: SemanticIR,
    target: SemanticIR,
    case_manifest: dict[str, Any],
    source_observations: dict[str, list[dict[str, Any]]],
    target_observations: dict[str, list[dict[str, Any]]],
    source_artifact_sha256: str,
    target_artifact_sha256: str,
    corpus_sha256: str,
    emitted: EmittedFile,
    source_artifact_bytes: bytes,
    source_logical_file: str,
    source_inventory_sha256: str,
    source_inventory_byte_count: int,
    target_inventory_sha256: str,
    target_inventory_byte_count: int,
    whole_file_closure: dict[str, Any],
    identifier_hygiene: dict[str, Any],
    javascript_esm_descriptor: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compose per-function layers for one independent pure-function module.

    This is a conjunction over the source module's empty user call graph plus
    the target emitter's exact profile-to-helper/builtin call edges. Helper
    internals are content-bound, not modeled as a raw transitive call graph.
    It is deliberately not a theorem about original source bytes or either
    compiler/runtime.
    """

    source_index = _module_function_index(source, "source")
    target_index = _module_function_index(target, "target")
    source_symbols = sorted(source_index)
    target_symbols = sorted(target_index)
    if source_symbols != target_symbols:
        raise RouteError(
            f"PURE_MODULE_SYMBOL_SET_MISMATCH:source={','.join(source_symbols)}:target={','.join(target_symbols)}"
        )
    for symbol in source_symbols:
        if source_index[symbol].signature_mapping() != target_index[symbol].signature_mapping():
            raise RouteError(f"PURE_MODULE_SIGNATURE_MISMATCH:{symbol}")
    cases_by_symbol = normalize_pure_module_case_manifest(case_manifest, source_index)
    if set(source_observations) != set(source_index):
        raise RouteError("PURE_MODULE_SOURCE_OBSERVATION_SYMBOL_SET_MISMATCH")
    if set(target_observations) != set(source_index):
        raise RouteError("PURE_MODULE_TARGET_OBSERVATION_SYMBOL_SET_MISMATCH")

    composition_contract = case_manifest.get("composition")
    if not isinstance(composition_contract, dict):
        raise RouteError("PURE_MODULE_CASE_MANIFEST_COMPOSITION_INVALID")
    input_domain = str(composition_contract.get("input_domain"))
    out_of_domain_behavior = (
        NODEJS_OUT_OF_DOMAIN_BEHAVIOR if input_domain == NODEJS_INPUT_DOMAIN else SPECIALIZED_OUT_OF_DOMAIN_BEHAVIOR
    )
    module_input = {
        "profile": PURE_MODULE_PROFILE,
        "route": {
            "source_language": source.source_language,
            "target_language": target.source_language,
        },
        "input_domain": input_domain,
        "source_artifact_sha256": source_artifact_sha256,
        "target_artifact_sha256": target_artifact_sha256,
        "source_artifact_byte_count": len(source_artifact_bytes),
        "target_artifact_byte_count": len(emitted.content.encode("utf-8")),
        "source_logical_file": source_logical_file,
        "target_logical_file": emitted.relative_path,
        "corpus_sha256": corpus_sha256,
        "source_semantic_ir_sha256": sha256_bytes(canonical_json_bytes(source.to_mapping())),
        "target_semantic_ir_sha256": sha256_bytes(canonical_json_bytes(target.to_mapping())),
        "case_manifest_sha256": sha256_bytes(canonical_json_bytes(case_manifest)),
        "source_inventory_sha256": source_inventory_sha256,
        "source_inventory_byte_count": source_inventory_byte_count,
        "target_inventory_sha256": target_inventory_sha256,
        "target_inventory_byte_count": target_inventory_byte_count,
        "whole_file_closure_sha256": sha256_bytes(canonical_json_bytes(whole_file_closure)),
        "identifier_hygiene": identifier_hygiene,
    }
    if javascript_esm_descriptor is not None:
        module_input["javascript_esm_descriptor"] = javascript_esm_descriptor
    module_input_sha256 = sha256_bytes(canonical_json_bytes(module_input))
    function_reports: list[dict[str, Any]] = []
    proof_closures_by_symbol: dict[str, dict[str, Any]] = {}
    for function_index, symbol in enumerate(source_symbols):
        source_function = source_index[symbol]
        target_function = target_index[symbol]
        source_slice = replace(source, functions=(source_function,))
        target_slice = replace(target, functions=(target_function,))
        cases = cases_by_symbol[symbol]
        case_manifest_sha256 = sha256_bytes(canonical_json_bytes(cases))
        semantic = semantic_equivalence(source_slice, target_slice)
        chunks = chunk_equivalence(
            source_slice,
            target_slice,
            source_artifact_sha256,
            target_artifact_sha256,
            emitted,
            source_artifact_bytes=source_artifact_bytes,
            target_artifact_bytes=emitted.content.encode("utf-8"),
            source_logical_file=source_logical_file,
            target_logical_file=emitted.relative_path,
            require_concrete_spans=True,
        )
        behavior = behavior_equivalence(
            source_function,
            cases,
            source_observations[symbol],
            target_observations[symbol],
        )
        source_function_mapping = source_function.semantic_mapping()
        target_function_mapping = target_function.semantic_mapping()
        formal_input = {
            "schema_version": SCHEMA_VERSION,
            "kind": "typed-pure-module-function-formal-input",
            "profile": PURE_MODULE_PROFILE,
            "route": {
                "route_key": f"{source.source_language}-to-{target.source_language}",
                "source_language": source.source_language,
                "target_language": target.source_language,
            },
            "input_domain": input_domain,
            "module_input_sha256": module_input_sha256,
            "symbol": symbol,
            "signature": source_function.signature_mapping(),
            "source_function": source_function_mapping,
            "source_function_sha256": sha256_bytes(canonical_json_bytes(source_function_mapping)),
            "target_function": target_function_mapping,
            "target_function_sha256": sha256_bytes(canonical_json_bytes(target_function_mapping)),
            "case_manifest_sha256": case_manifest_sha256,
            "identifier_hygiene": {
                "plan": identifier_hygiene["plan"],
                "unit_namespace": identifier_hygiene["unit_namespace"],
                "unit_namespace_sha256": identifier_hygiene["unit_namespace_sha256"],
                "raw_target_ir": identifier_hygiene["raw_target_ir"],
                "normalized_target_ir": identifier_hygiene["normalized_target_ir"],
                "function": next(
                    function_mapping
                    for function_mapping in identifier_hygiene["functions"]
                    if function_mapping["canonical_symbol"] == symbol
                ),
            },
        }
        formal_input_sha256 = sha256_bytes(canonical_json_bytes(formal_input))
        formal_input_path = f"formal-function-{function_index:03d}-input.json"
        solver_input_path = f"formal-function-{function_index:03d}.smt2"
        formal_result_path = f"formal-function-{function_index:03d}-result.json"
        formal_input_reference = {
            "path": formal_input_path,
            "sha256": formal_input_sha256,
        }
        formal, smt2 = formal_equivalence(
            source_function,
            target_function,
            source.source_language,
            target.source_language,
            formal_input_sha256,
            formal_input_reference=formal_input_reference,
            input_domain=input_domain,
        )
        solver_input_sha256 = sha256_bytes(smt2.encode("utf-8"))
        assumptions = formal.get("assumptions")
        soundness = formal.get("external_soundness_boundary")
        proof_closed = (
            formal.get("status") == "PROVED_UNDER_ASSUMPTIONS"
            and formal.get("property_status") == "PROVED"
            and formal.get("proof_strength") == "THEOREM_UNDER_ASSUMPTIONS"
            and isinstance(assumptions, list)
            and bool(assumptions)
            and all(isinstance(assumption, str) and assumption for assumption in assumptions)
            and formal.get("countermodel") is None
            and isinstance(soundness, dict)
            and soundness.get("source_compiler_runtime_soundness") == "NOT_RUN"
            and soundness.get("target_compiler_runtime_soundness") == "NOT_RUN"
        )
        if not proof_closed:
            raise RouteError(f"PURE_MODULE_FORMAL_PROOF_NOT_CLOSED:{symbol}")
        solver_identity = formal.get("solver")
        if (
            not isinstance(solver_identity, dict)
            or solver_identity.get("name") != "z3"
            or not isinstance(solver_identity.get("version"), str)
            or not solver_identity.get("version")
            or not isinstance(solver_identity.get("timeout_ms"), int)
            or solver_identity.get("random_seed") != 0
            or not isinstance(solver_identity.get("theories"), list)
            or not solver_identity.get("theories")
        ):
            raise RouteError(f"PURE_MODULE_SOLVER_IDENTITY_INVALID:{symbol}")
        formal_result = {
            "schema_version": SCHEMA_VERSION,
            "kind": "typed-pure-module-function-formal-result",
            "profile": PURE_MODULE_PROFILE,
            "symbol": symbol,
            "status": formal["status"],
            "property_status": formal["property_status"],
            "proof_strength": formal["proof_strength"],
            "solver": solver_identity.get("name"),
            "version": solver_identity.get("version"),
            "options": {
                "timeout_ms": solver_identity.get("timeout_ms"),
                "random_seed": solver_identity.get("random_seed"),
                "theories": solver_identity.get("theories"),
            },
            "assumptions": assumptions,
            "countermodel": formal.get("countermodel"),
            "formal_input_digest": formal_input_sha256,
            "solver_input_digest": solver_input_sha256,
            "formal_input": formal_input_reference,
            "solver_input": {
                "path": solver_input_path,
                "sha256": solver_input_sha256,
            },
            "replay_contract": {
                "kind": "z3-cli-check-sat",
                "argv": ["z3", "-smt2", solver_input_path],
                "working_directory": ".",
                "expected_exit_code": 0,
                "expected_stdout": "unsat",
            },
            "claim_scope": formal.get("claim_scope"),
            "reason": formal.get("reason"),
            "external_soundness_boundary": soundness,
            "independent_encodings": formal.get("independent_encodings"),
            "certification_status": formal.get("certification_status"),
        }
        formal_result_sha256 = sha256_bytes(canonical_json_bytes(formal_result))
        formal_layer = {
            **formal_result,
            "formal_input_path": formal_input_path,
            "formal_input_sha256": formal_input_sha256,
            "solver_input_path": solver_input_path,
            "solver_input_sha256": solver_input_sha256,
            "formal_result_path": formal_result_path,
            "formal_result_sha256": formal_result_sha256,
        }
        proof_closures_by_symbol[symbol] = {
            "formal_input": formal_input,
            "formal_input_sha256": formal_input_sha256,
            "formal_input_path": formal_input_path,
            "solver_input": smt2,
            "solver_input_sha256": solver_input_sha256,
            "solver_input_path": solver_input_path,
            "formal_result": formal_result,
            "formal_result_sha256": formal_result_sha256,
            "formal_result_path": formal_result_path,
        }
        passed = (
            semantic["status"] == EvidenceStatus.PASSED
            and chunks["status"] == EvidenceStatus.PASSED
            and behavior["status"] == EvidenceStatus.PASSED
            and proof_closed
        )
        function_reports.append(
            {
                "symbol": symbol,
                "signature": source_function.signature_mapping(),
                "status": EvidenceStatus.PASSED if passed else EvidenceStatus.FAILED,
                "case_manifest_sha256": case_manifest_sha256,
                "layers": {
                    "semantic": semantic,
                    "chunk": chunks,
                    "behavior": behavior,
                    "formal": formal_layer,
                },
            }
        )
    passed_function_count = sum(
        1 for function_report in function_reports if function_report["status"] == EvidenceStatus.PASSED
    )
    passed = passed_function_count == len(function_reports) and bool(function_reports)
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "typed-pure-module-equivalence",
        "profile": PURE_MODULE_PROFILE,
        "status": EvidenceStatus.PASSED if passed else EvidenceStatus.FAILED,
        "local_verification_status": "PASSED" if passed else "BLOCKED",
        "route": {
            "route_key": f"{source.source_language}-to-{target.source_language}",
            "source_language": source.source_language,
            "target_language": target.source_language,
        },
        "module_input_sha256": module_input_sha256,
        "module_input": module_input,
        "module_contract": {
            "source_profile_symbols": source_symbols,
            "target_profile_symbols": target_symbols,
            "target_helper_symbols": whole_file_closure["target_helper_symbols"],
            "verified_language_prelude": whole_file_closure["verified_language_prelude"],
            "verified_language_wrapper": whole_file_closure["verified_language_wrapper"],
            "manifest_symbols": sorted(cases_by_symbol),
            "exact_profile_symbol_set": True,
            "exact_generated_helper_symbol_set": True,
            "exact_profile_signature_set": True,
            "whole_file_closure_sha256": module_input["whole_file_closure_sha256"],
            "independence": {
                "source_user_call_graph_edges": [],
                "source_user_call_graph_closure": "EMPTY_AND_CLOSED",
                "target_call_graph_policy": whole_file_closure["target_call_graph_policy"],
                "target_call_graph": whole_file_closure["target_call_graph"],
                "target_generated_helper_symbols": whole_file_closure["target_helper_symbols"],
                "target_builtin_normalizations": whole_file_closure["target_builtin_normalizations"],
                "function_calls": "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS",
                "mutable_state": "UNSUPPORTED",
                "shared_state": "ABSENT_BY_IR_CONSTRUCTION",
            },
        },
        "functions": function_reports,
        "composition": {
            "rule": "per-function-denotation-plus-exact-emitter-helper-closure",
            "function_count": len(function_reports),
            "passed_function_count": passed_function_count,
            "status": EvidenceStatus.PASSED if passed else EvidenceStatus.FAILED,
            "proof_strength": "COMPOSED_THEOREMS_UNDER_ASSUMPTIONS",
            "input_domain": module_input["input_domain"],
            "out_of_domain_arithmetic_behavior": out_of_domain_behavior,
            "original_source_bytes_theorem": False,
            "source_compiler_runtime_soundness": "NOT_RUN",
            "target_compiler_runtime_soundness": "NOT_RUN",
            "analyzer_and_emitter_soundness": "ASSUMPTION",
            "source_user_call_graph": "EMPTY_AND_CLOSED",
            "target_call_graph": "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS",
            "target_profile_to_emitted_call_graph_status": whole_file_closure["target_call_graph"]["status"],
            "target_profile_to_emitted_call_graph_scope": whole_file_closure["target_call_graph"]["scope"],
        },
        "unsupported_semantics": list(L1_PLUS_UNSUPPORTED),
        "certification_status": "NOT_CERTIFIED",
        "external_verification_status": "NOT_RUN",
    }
    return report, proof_closures_by_symbol


def compose_layered_report(
    route: DirectedRouteKey,
    semantic: dict[str, Any],
    chunks: dict[str, Any],
    behavior: dict[str, Any],
    formal: dict[str, Any],
    artifact_refs: dict[str, Any],
) -> dict[str, Any]:
    formal_passed = formal.get("status") == "PROVED_UNDER_ASSUMPTIONS"
    passed = all(item.get("status") == EvidenceStatus.PASSED for item in (semantic, chunks, behavior)) and formal_passed
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.layered-equivalence-report",
        "status": EvidenceStatus.PASSED if passed else EvidenceStatus.FAILED,
        "local_verification_status": "PASSED_LOCAL" if passed else "BLOCKED",
        "route": route.to_mapping(),
        "layers": {
            "semantic": {
                "status": semantic["status"],
                "difference_count": semantic["difference_count"],
                **artifact_refs["semantic"],
            },
            "chunk": {
                "status": chunks["status"],
                "required_source_chunk_count": chunks["required_source_chunk_count"],
                "mapped_source_chunk_count": chunks["mapped_source_chunk_count"],
                "coverage": chunks["coverage"],
                **artifact_refs["chunk"],
            },
            "behavior": {
                "status": behavior["status"],
                "case_count": behavior["case_count"],
                "pass_count": behavior["pass_count"],
                "source_runtime_passed": behavior["source_runtime_passed"],
                "target_runtime_passed": behavior["target_runtime_passed"],
                "oracle_conflict_count": behavior["oracle_conflict_count"],
                **artifact_refs["behavior"],
            },
            "formal": {
                "status": formal["status"],
                "property_status": formal["property_status"],
                **artifact_refs["formal"],
            },
        },
        "assumption_boundary": formal["assumption_boundary"],
        "assumptions": formal.get("assumptions", []),
        "unsupported_semantics": list(L1_PLUS_UNSUPPORTED),
        "counterexamples": behavior.get("counterexamples", [])
        + ([formal["countermodel"]] if formal.get("countermodel") else []),
        "certification_status": "NOT_CERTIFIED",
        "external_verification_status": "NOT_RUN",
    }
