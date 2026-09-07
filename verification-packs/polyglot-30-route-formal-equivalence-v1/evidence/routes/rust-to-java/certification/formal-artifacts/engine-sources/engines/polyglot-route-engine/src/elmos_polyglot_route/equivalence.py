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
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import z3  # type: ignore[import-untyped]

from . import canonical, types
from .emitter import EmittedFile
from .models import Expression, Function, Language, RouteError, SemanticIR, Statement

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
        functions = semantic_ir.get("functions")
        if not isinstance(functions, list) or len(functions) != 1:
            raise RouteError(f"FORMAL_INPUT_FUNCTION_SET_INVALID:{label}")
        formal_function = _mapping(binding.get("formal_function"), f"{label}.formal_function")
        if formal_function != functions[0]:
            raise RouteError(f"FORMAL_INPUT_FUNCTION_DRIFT:{label}")
        if binding.get("semantic_ir_sha256") != sha256_bytes(canonical_json_bytes(semantic_ir)):
            raise RouteError(f"FORMAL_INPUT_SEMANTIC_IR_DIGEST_MISMATCH:{label}")
        if binding.get("formal_function_sha256") != sha256_bytes(canonical_json_bytes(formal_function)):
            raise RouteError(f"FORMAL_INPUT_FUNCTION_DIGEST_MISMATCH:{label}")
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
    return {"functions": [function.to_mapping() for function in ir.functions]}


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


def _chunk(path: str, kind: str, canonical_view: dict[str, Any], artifact_sha256: str) -> dict[str, Any]:
    subtree = resolve_json_pointer(canonical_view, path)
    semantic_hash = sha256_bytes(canonical_json_bytes(subtree))
    return {
        "semantic_path": path,
        "kind": kind,
        "semantic_hash": semantic_hash,
        "chunk_id": sha256_bytes(f"{artifact_sha256}\0{path}\0{semantic_hash}".encode()),
        "artifact_sha256": artifact_sha256,
        "artifact_pointer": f"{artifact_sha256}#{path}",
    }


def _expression_chunks(
    expression: Expression,
    path: str,
    artifact_sha256: str,
    canonical_view: dict[str, Any],
    result: list[dict[str, Any]],
) -> None:
    result.append(_chunk(path, f"expression:{expression.kind}", canonical_view, artifact_sha256))
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
        result.append(_chunk(statement_path, f"statement:{statement.kind}", canonical_view, artifact_sha256))
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
        result.append(_chunk(function_path, "function", canonical_view, artifact_sha256))
        for parameter_index, _parameter in enumerate(function.parameters):
            result.append(
                _chunk(
                    f"{function_path}/parameters/{parameter_index}",
                    "parameter",
                    canonical_view,
                    artifact_sha256,
                )
            )
        _statement_chunks(function.body, f"{function_path}/body", artifact_sha256, canonical_view, result)
    return result


def chunk_equivalence(
    source: SemanticIR,
    target: SemanticIR,
    source_artifact_sha256: str,
    target_artifact_sha256: str,
    emitted: EmittedFile,
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
                "semantic_hash": source_chunk["semantic_hash"],
            }
        )
    unexpected = sorted(set(target_by_path) - set(source_by_path))
    mapped = sum(1 for item in mappings if item["status"] == "EXACT")
    required = len(source_chunks)
    coverage = mapped / required if required else 0.0
    status = (
        EvidenceStatus.PASSED
        if required > 0 and mismatch_count == 0 and not unexpected and coverage == 1.0
        else EvidenceStatus.FAILED
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.chunk-equivalence",
        "status": status,
        "path_scheme": "rfc6901-json-pointer-v1",
        "hash_scheme": "sha256-canonical-semantic-subtree-v1",
        "required_source_chunk_count": required,
        "mapped_source_chunk_count": mapped,
        "mismatch_count": mismatch_count,
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
        expected = case["expected"]
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
            if runtime_language == "typescript" and parameter.type == "integer":
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
        self.assumption_labels.append(f"typescript-safe-integer:{label}")

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
                if self.runtime_language == "typescript":
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
        return self.statements(self.function.body, "/body")


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
) -> tuple[dict[str, Any], str]:
    formal_input = dict(formal_input_reference) if formal_input_reference else None
    input_reference_valid = formal_input is None or (
        isinstance(formal_input.get("path"), str) and formal_input.get("sha256") == input_digest
    )
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.formal-equivalence-result",
        "property_id": "L0-DENOTATIONAL-EQUIVALENCE",
        "proof_strength": "THEOREM",
        "input_digest": input_digest,
        "formal_input_digest": input_digest,
        "formal_input": formal_input,
        "claim_scope": {
            "relation": FORMAL_RELATION_SCOPE,
            "source_term": "source normalized Function from canonical IR",
            "target_term": "independently re-lifted target normalized Function",
            "original_source_bytes_theorem": False,
        },
        "solver": formal_solver_identity(),
        "assumption_boundary": "typed-pure-function-v1 / L0 only",
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
