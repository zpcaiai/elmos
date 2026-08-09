from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import platform
import stat
import tempfile
from pathlib import Path
from typing import Any

from . import canonical, types
from .emitter import (
    _CHECKED_INTEGER_CALL,
    _FLOAT_NON_ZERO_GUARD,
    _HELPERS,
    EmittedFile,
    emit,
)
from .equivalence import (
    L1_PLUS_UNSUPPORTED,
    SPECIALIZED_INPUT_DOMAIN,
    DirectedRouteKey,
    behavior_equivalence,
    canonical_json_bytes,
    chunk_equivalence,
    compose_layered_report,
    formal_environment_assumptions,
    formal_equivalence,
    formal_solver_identity,
    module_equivalence,
    normalize_pure_module_case_manifest,
    semantic_equivalence,
    sha256_bytes,
    validate_pure_module_manifest_shape,
    verify_content_reference,
    verify_formal_input_closure,
    write_json,
)
from .models import (
    SUPPORTED_LANGUAGES,
    TYPED_PURE_FUNCTION_PROFILE,
    Expression,
    Function,
    Language,
    RouteError,
    SemanticIR,
    SourceSpan,
    Statement,
    is_routed_pair,
    is_specialized_pair,
    requires_concrete_source_spans,
)
from .native import analyze, inventory_module
from .validation import safe_output, validate, validate_source


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _private_input_snapshot(
    root: Path,
    role: str,
    logical_name: str,
    content: bytes,
) -> Path:
    role_root = root / role
    role_root.mkdir(mode=0o700)
    path = role_root / logical_name
    path.write_bytes(content)
    path.chmod(0o600)
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size != len(content)
        or path.read_bytes() != content
    ):
        raise RouteError(f"PRIVATE_INPUT_SNAPSHOT_INVALID:{role}")
    return path


def _file_identity(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": f"src/elmos_polyglot_route/{path.name}",
        "sha256": _digest(content),
        "byte_count": len(content),
    }


def _artifact_binding(
    role: str,
    path: str,
    content: bytes,
    evidence_path: str,
) -> dict[str, Any]:
    digest = _digest(content)
    return {
        "role": role,
        "path": path,
        "sha256": digest,
        "byte_count": len(content),
        "content_base64": base64.b64encode(content).decode("ascii"),
        "content_reference": {"path": evidence_path, "sha256": digest},
    }


def _normalized_ir_binding(
    role: str,
    artifact_reference: dict[str, str],
    ir: SemanticIR,
    function: Function,
) -> dict[str, Any]:
    # Source spans remain in `semantic_ir` as concrete evidence bindings, but
    # the theorem term is location independent.
    function_mapping = function.semantic_mapping()
    return {
        "role": role,
        "artifact": artifact_reference,
        "semantic_ir": ir.to_mapping(),
        "semantic_ir_sha256": sha256_bytes(canonical_json_bytes(ir.to_mapping())),
        "formal_function": function_mapping,
        "formal_function_sha256": sha256_bytes(canonical_json_bytes(function_mapping)),
    }


def _formal_input_payload(
    *,
    source_language: Language,
    target_language: Language,
    source_path: str,
    source_bytes: bytes,
    target_path: str,
    target_bytes: bytes,
    source_ir: SemanticIR,
    target_ir: SemanticIR,
    source_ir_reference: dict[str, str],
    target_ir_reference: dict[str, str],
    emitted: EmittedFile,
) -> dict[str, Any]:
    module_root = Path(__file__).resolve().parent
    assumptions = formal_environment_assumptions(source_language, target_language)
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.formal-equivalence-input",
        "route": {
            "source_language": source_language,
            "target_language": target_language,
            "profile": "typed-pure-function-v1",
        },
        "claim_scope": {
            "relation": "canonical-normalized-source-ir-to-target-relift-ir",
            "source_term": "source_normalized_ir.formal_function",
            "target_term": "target_relift_normalized_ir.formal_function",
            "original_source_bytes_theorem": False,
            "input_domain": (
                SPECIALIZED_INPUT_DOMAIN
                if is_specialized_pair(source_language, target_language)
                else "profile-total-domain"
            ),
            "source_compiler_runtime_soundness": "NOT_RUN",
            "target_compiler_runtime_soundness": "NOT_RUN",
        },
        "source_artifact": _artifact_binding(
            "original-source-analyzer-input",
            source_path,
            source_bytes,
            f"source-runtime/{source_path}",
        ),
        "target_artifact": _artifact_binding(
            "emitted-target-analyzer-input",
            target_path,
            target_bytes,
            target_path,
        ),
        "source_normalized_ir": _normalized_ir_binding(
            "canonical-source-normalized-ir",
            source_ir_reference,
            source_ir,
            source_ir.functions[0],
        ),
        "target_relift_normalized_ir": _normalized_ir_binding(
            "emitted-target-relift-normalized-ir",
            target_ir_reference,
            target_ir,
            target_ir.functions[0],
        ),
        "implementation_identity": {
            "engine": _file_identity(module_root / "engine.py"),
            "equivalence_encoder": _file_identity(module_root / "equivalence.py"),
            "emitter": _file_identity(module_root / "emitter.py"),
        },
        "analyzer_identity": {
            "source": {
                "name": source_ir.analyzer,
                "version": source_ir.analyzer_version,
                "language": source_language,
            },
            "target_relift": {
                "name": target_ir.analyzer,
                "version": target_ir.analyzer_version,
                "language": target_language,
                "mode": "emitted-target",
            },
        },
        "emitter_identity": {
            "target_language": target_language,
            "normalization_rules": list(emitted.normalization_rules),
            "helper_digests": [
                {"helper_id": helper_id, "sha256": digest} for helper_id, digest in emitted.helper_digests
            ],
        },
        "solver": formal_solver_identity(),
        "environment": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "environment_assumptions": assumptions,
        "unsupported_semantics": list(L1_PLUS_UNSUPPORTED),
    }


def _load_cases(path: Path, parameter_count: int) -> list[dict[str, Any]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list) or not loaded:
        raise RouteError("BEHAVIOR_CASES_REQUIRED")
    result: list[dict[str, Any]] = []
    for item in loaded:
        if not isinstance(item, dict) or not isinstance(item.get("args"), list) or "expected" not in item:
            raise RouteError("INVALID_BEHAVIOR_CASE")
        if len(item["args"]) != parameter_count:
            raise RouteError("BEHAVIOR_ARGUMENT_COUNT_MISMATCH")
        result.append(item)
    return result


def _expression_uses_string(expression: Expression) -> bool:
    if expression.kind == "literal" and isinstance(expression.value, str):
        return True
    return any(
        nested is not None and _expression_uses_string(nested)
        for nested in (expression.left, expression.right)
    )


def _expression_uses_non_finite_number(expression: Expression) -> bool:
    return (
        expression.kind == "literal"
        and isinstance(expression.value, float)
        and not math.isfinite(expression.value)
    ) or any(
        nested is not None and _expression_uses_non_finite_number(nested)
        for nested in (expression.left, expression.right)
    )


def _expression_uses_number_arithmetic(
    expression: Expression,
    environment: dict[str, str],
) -> bool:
    if (
        expression.kind == "binary"
        and expression.operator in types.ARITHMETIC_OPERATORS
        and types.infer(expression, environment) == "number"
    ):
        return True
    return any(
        nested is not None and _expression_uses_number_arithmetic(nested, environment)
        for nested in (expression.left, expression.right)
    )


def _statement_uses_string(statement: Statement) -> bool:
    return any(
        expression is not None and _expression_uses_string(expression)
        for expression in (statement.expression, statement.condition)
    ) or any(
        _statement_uses_string(nested)
        for nested in (*statement.then_body, *statement.else_body)
    )


def _statement_uses_non_finite_number(statement: Statement) -> bool:
    return any(
        expression is not None and _expression_uses_non_finite_number(expression)
        for expression in (statement.expression, statement.condition)
    ) or any(
        _statement_uses_non_finite_number(nested)
        for nested in (*statement.then_body, *statement.else_body)
    )


def _statement_uses_number_arithmetic(
    statement: Statement,
    environment: dict[str, str],
) -> bool:
    return any(
        expression is not None
        and _expression_uses_number_arithmetic(expression, environment)
        for expression in (statement.expression, statement.condition)
    ) or any(
        _statement_uses_number_arithmetic(nested, environment)
        for nested in (*statement.then_body, *statement.else_body)
    )


def _enforce_specialized_semantic_domain(
    ir: SemanticIR,
    source_language: Language,
    target_language: Language,
) -> None:
    """Reject string semantics that are not shared by the native exact eight.

    Swift string equality uses Unicode canonical equivalence, Java compares
    UTF-16 code units, and C++ compares bytes. Objective-C adds a Foundation
    representation boundary. Until a versioned encoding and normalization
    contract is enforced at every call boundary, accepting canonical
    ``string`` would create a false equivalence claim. The original complete
    30-route matrix retains its existing contract; this restriction belongs
    only to the explicitly declared native exact-eight set.
    """

    if not is_specialized_pair(source_language, target_language):
        return
    for function in ir.functions:
        environment = {parameter.name: parameter.type for parameter in function.parameters}
        if (
            function.return_type == "string"
            or any(parameter.type == "string" for parameter in function.parameters)
            or any(_statement_uses_string(statement) for statement in function.body)
        ):
            raise RouteError(
                "SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED:"
                f"{source_language}-to-{target_language}:{function.name}"
            )
        if any(
            _statement_uses_non_finite_number(statement)
            for statement in function.body
        ):
            raise RouteError(
                "SPECIALIZED_NON_FINITE_NUMBER_UNSUPPORTED:"
                f"{source_language}-to-{target_language}:{function.name}"
            )
        if any(
            _statement_uses_number_arithmetic(statement, environment)
            for statement in function.body
        ):
            raise RouteError(
                "SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED:"
                f"{source_language}-to-{target_language}:{function.name}"
            )


def _enforce_specialized_case_domain(
    function: Function,
    cases: list[dict[str, Any]],
    source_language: Language,
    target_language: Language,
) -> None:
    """Block native execution before an exact-eight case reaches an error domain."""

    if not is_specialized_pair(source_language, target_language):
        return
    for case_index, case in enumerate(cases):
        values = [*case["args"], case["expected"]]
        if any(isinstance(value, float) and not math.isfinite(value) for value in values):
            raise RouteError(
                "SPECIALIZED_CASE_NON_FINITE_NUMBER_UNSUPPORTED:"
                f"{source_language}-to-{target_language}:{function.name}:{case_index}"
            )
        try:
            evaluation = canonical.evaluate(function, list(case["args"]))
        except canonical.CanonicalError as error:
            raise RouteError(
                "SPECIALIZED_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN:"
                f"{source_language}-to-{target_language}:{function.name}:{case_index}:"
                f"{type(error).__name__}"
            ) from error
        if isinstance(evaluation.value, float) and not math.isfinite(evaluation.value):
            raise RouteError(
                "SPECIALIZED_CASE_NON_FINITE_RESULT_UNSUPPORTED:"
                f"{source_language}-to-{target_language}:{function.name}:{case_index}"
            )


def _require_sha256(value: str, label: str) -> None:
    if (
        len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise RouteError(f"INVALID_SHA256:{label}")


def _artifact_ref(root: Path, path: Path, role: str) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_root not in resolved_path.parents or not path.is_file() or path.is_symlink():
        raise RouteError(f"MODULE_ARTIFACT_PATH_INVALID:{role}")
    content = path.read_bytes()
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "sha256": _digest(content),
        "bytes": len(content),
    }


def verify_pure_module(
    *,
    source_ir: SemanticIR,
    target_ir: SemanticIR,
    case_manifest: dict[str, Any],
    source_observations: dict[str, list[dict[str, Any]]],
    target_observations: dict[str, list[dict[str, Any]]],
    source_artifact_sha256: str,
    target_artifact_sha256: str,
    corpus_sha256: str,
    emitted: EmittedFile,
    source_artifact_bytes: bytes,
    source_logical_file: str,
    case_manifest_bytes: bytes,
    source_inventory: dict[str, Any],
    target_inventory: dict[str, Any],
    whole_file_closure: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    """Persist a content-bound typed-pure-module equivalence composition.

    Callers supply observations produced by real source and target executions;
    :func:`migrate_module` below is the end-to-end entry point that creates
    those observations.  This lower-level function is useful to route runners
    that already own isolated compilation/execution.
    """

    source_language = source_ir.source_language
    target_language = target_ir.source_language
    if not is_routed_pair(source_language, target_language):
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    _enforce_specialized_semantic_domain(source_ir, source_language, target_language)
    _enforce_specialized_semantic_domain(target_ir, source_language, target_language)
    source_functions = {function.name: function for function in source_ir.functions}
    cases_by_symbol = normalize_pure_module_case_manifest(case_manifest, source_functions)
    for symbol, cases in cases_by_symbol.items():
        _enforce_specialized_case_domain(
            source_functions[symbol], cases, source_language, target_language
        )
    for label, digest in (
        ("source_artifact", source_artifact_sha256),
        ("target_artifact", target_artifact_sha256),
        ("corpus", corpus_sha256),
    ):
        _require_sha256(digest, label)
    emitted_bytes = emitted.content.encode("utf-8")
    if _digest(source_artifact_bytes) != source_artifact_sha256:
        raise RouteError("SOURCE_MODULE_ARTIFACT_DIGEST_MISMATCH")
    if _digest(case_manifest_bytes) != corpus_sha256:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_DIGEST_MISMATCH")
    if _digest(emitted_bytes) != target_artifact_sha256:
        raise RouteError("TARGET_MODULE_ARTIFACT_DIGEST_MISMATCH")
    # Reuse the span path contract before constructing a destination path.
    SourceSpan.from_mapping(
        {"file": source_logical_file, "start_byte": 0, "end_byte": 1}
    )

    output = safe_output(output)
    output.mkdir(parents=True, exist_ok=True)
    source_inventory_path = output / "source-module-inventory.json"
    target_inventory_path = output / "target-module-inventory.json"
    whole_file_closure_path = output / "whole-file-module-closure.json"
    source_inventory_sha256 = write_json(source_inventory_path, source_inventory)
    target_inventory_sha256 = write_json(target_inventory_path, target_inventory)
    whole_file_closure_sha256 = write_json(whole_file_closure_path, whole_file_closure)
    if whole_file_closure.get("source_inventory_sha256") != source_inventory_sha256:
        raise RouteError("PURE_MODULE_SOURCE_INVENTORY_BACKLINK_MISMATCH")
    if whole_file_closure.get("target_inventory_sha256") != target_inventory_sha256:
        raise RouteError("PURE_MODULE_TARGET_INVENTORY_BACKLINK_MISMATCH")
    if whole_file_closure.get("status") != "PASSED":
        raise RouteError("PURE_MODULE_WHOLE_FILE_CLOSURE_NOT_PASSED")
    source_ir_path = output / "source-module-semantic-ir.json"
    target_ir_path = output / "target-module-semantic-ir.json"
    source_observations_path = output / "source-module-observations.json"
    target_observations_path = output / "target-module-observations.json"
    target_artifact_path = output / emitted.relative_path
    source_artifact_path = output / "source-module-artifact" / source_logical_file
    case_manifest_path = output / "module-case-manifest.json"
    write_json(source_ir_path, source_ir.to_mapping())
    write_json(target_ir_path, target_ir.to_mapping())
    write_json(source_observations_path, source_observations)
    write_json(target_observations_path, target_observations)
    source_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    source_artifact_path.write_bytes(source_artifact_bytes)
    case_manifest_path.write_bytes(case_manifest_bytes)
    target_artifact_path.write_bytes(emitted_bytes)

    report, proof_closures_by_symbol = module_equivalence(
        source=source_ir,
        target=target_ir,
        case_manifest=case_manifest,
        source_observations=source_observations,
        target_observations=target_observations,
        source_artifact_sha256=source_artifact_sha256,
        target_artifact_sha256=target_artifact_sha256,
        corpus_sha256=corpus_sha256,
        emitted=emitted,
        source_artifact_bytes=source_artifact_bytes,
        source_logical_file=source_logical_file,
        source_inventory_sha256=source_inventory_sha256,
        source_inventory_byte_count=source_inventory_path.stat().st_size,
        target_inventory_sha256=target_inventory_sha256,
        target_inventory_byte_count=target_inventory_path.stat().st_size,
        whole_file_closure=whole_file_closure,
    )
    formal_input_path = output / "module-formal-input.json"
    formal_input_sha256 = write_json(formal_input_path, report["module_input"])
    if formal_input_sha256 != report["module_input_sha256"]:
        raise RouteError("PURE_MODULE_FORMAL_INPUT_DIGEST_MISMATCH")

    artifact_refs = [
        _artifact_ref(output, source_ir_path, "source-module-semantic-ir"),
        _artifact_ref(output, target_ir_path, "target-module-semantic-ir"),
        _artifact_ref(output, source_observations_path, "source-module-observations"),
        _artifact_ref(output, target_observations_path, "target-module-observations"),
        _artifact_ref(output, source_artifact_path, "original-source-module-artifact"),
        _artifact_ref(output, target_artifact_path, "emitted-target-module-artifact"),
        _artifact_ref(output, case_manifest_path, "module-case-manifest"),
        _artifact_ref(output, formal_input_path, "module-formal-input"),
        _artifact_ref(output, source_inventory_path, "source-module-inventory"),
        _artifact_ref(output, target_inventory_path, "target-module-inventory"),
        _artifact_ref(output, whole_file_closure_path, "whole-file-module-closure"),
    ]
    if artifact_refs[-1]["sha256"] != whole_file_closure_sha256:
        raise RouteError("PURE_MODULE_WHOLE_FILE_CLOSURE_DIGEST_MISMATCH")
    report["whole_file_closure"] = whole_file_closure
    for function_report in report["functions"]:
        symbol = function_report["symbol"]
        closure = proof_closures_by_symbol[symbol]
        formal_input_path = output / closure["formal_input_path"]
        solver_input_path = output / closure["solver_input_path"]
        formal_result_path = output / closure["formal_result_path"]

        observed_formal_input_sha256 = write_json(formal_input_path, closure["formal_input"])
        if observed_formal_input_sha256 != closure["formal_input_sha256"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_INPUT_DIGEST_MISMATCH:{symbol}")
        solver_input_path.write_text(closure["solver_input"], encoding="utf-8")
        solver_reference = _artifact_ref(output, solver_input_path, "formal-function-smt2")
        if solver_reference["sha256"] != closure["solver_input_sha256"]:
            raise RouteError(f"PURE_MODULE_SOLVER_INPUT_DIGEST_MISMATCH:{symbol}")
        formal_result_sha256 = write_json(formal_result_path, closure["formal_result"])
        if formal_result_sha256 != closure["formal_result_sha256"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_RESULT_DIGEST_MISMATCH:{symbol}")

        formal_input_reference = _artifact_ref(
            output,
            formal_input_path,
            "formal-function-input",
        )
        formal_result_reference = _artifact_ref(
            output,
            formal_result_path,
            "formal-function-result",
        )
        formal_layer = function_report["layers"]["formal"]
        if formal_input_reference["sha256"] != formal_layer["formal_input_digest"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_INPUT_BACKLINK_MISMATCH:{symbol}")
        if solver_reference["sha256"] != formal_layer["solver_input_digest"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_SOLVER_INPUT_BACKLINK_MISMATCH:{symbol}")
        if formal_result_reference["sha256"] != formal_layer["formal_result_sha256"]:
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_RESULT_BACKLINK_MISMATCH:{symbol}")
        expected_header = f"; formal_input_digest: {formal_input_reference['sha256']}"
        if expected_header not in closure["solver_input"]:
            raise RouteError(f"PURE_MODULE_SOLVER_INPUT_HEADER_MISMATCH:{symbol}")
        persisted_result = closure["formal_result"]
        if (
            persisted_result.get("formal_input_digest") != formal_input_reference["sha256"]
            or persisted_result.get("solver_input_digest") != solver_reference["sha256"]
            or persisted_result.get("proof_strength") != "THEOREM_UNDER_ASSUMPTIONS"
            or not persisted_result.get("assumptions")
            or persisted_result.get("countermodel") is not None
            or persisted_result.get("external_soundness_boundary", {}).get(
                "source_compiler_runtime_soundness"
            )
            != "NOT_RUN"
            or persisted_result.get("external_soundness_boundary", {}).get(
                "target_compiler_runtime_soundness"
            )
            != "NOT_RUN"
        ):
            raise RouteError(f"PURE_MODULE_FUNCTION_FORMAL_RESULT_NOT_CLOSED:{symbol}")
        replay_contract = persisted_result.get("replay_contract")
        if not isinstance(replay_contract, dict) or replay_contract != {
            "kind": "z3-cli-check-sat",
            "argv": ["z3", "-smt2", solver_reference["path"]],
            "working_directory": ".",
            "expected_exit_code": 0,
            "expected_stdout": "unsat",
        }:
            raise RouteError(f"PURE_MODULE_FUNCTION_REPLAY_CONTRACT_INVALID:{symbol}")
        artifact_refs.extend(
            [formal_input_reference, solver_reference, formal_result_reference]
        )
    report["artifact_refs"] = artifact_refs
    write_json(output / "typed-pure-module-equivalence.json", report)
    return report


def _load_module_manifest(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RouteError(f"PURE_MODULE_CASE_MANIFEST_DUPLICATE_KEY:{key}")
            result[key] = value
        return result

    try:
        loaded = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_JSON_INVALID") from error
    if not isinstance(loaded, dict):
        raise RouteError("PURE_MODULE_CASE_MANIFEST_MAPPING_REQUIRED")
    return loaded


def _manifest_symbols(manifest: dict[str, Any]) -> list[str]:
    validate_pure_module_manifest_shape(manifest)
    entries = manifest.get("functions")
    if not isinstance(entries, list) or len(entries) < 3:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_AT_LEAST_THREE_FUNCTIONS_REQUIRED")
    symbols: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise RouteError("PURE_MODULE_CASE_MANIFEST_ENTRY_INVALID")
        symbol = str(entry.get("symbol", "")).strip()
        if not symbol or symbol in symbols:
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_DUPLICATE_SYMBOL:{symbol}")
        symbols.append(symbol)
    return sorted(symbols)


def _combine_function_irs(
    analyzed: list[SemanticIR],
    expected_symbols: list[str],
    language: Language,
    role: str,
) -> SemanticIR:
    if len(analyzed) != len(expected_symbols) or not analyzed:
        raise RouteError(f"PURE_MODULE_ANALYSIS_SET_INCOMPLETE:{role}")
    first = analyzed[0]
    functions: dict[str, Function] = {}
    diagnostics: list[str] = []
    for ir in analyzed:
        if ir.source_language != language or len(ir.functions) != 1:
            raise RouteError(f"PURE_MODULE_ANALYSIS_FUNCTION_SET_INVALID:{role}")
        if ir.analyzer != first.analyzer or ir.analyzer_version != first.analyzer_version:
            raise RouteError(f"PURE_MODULE_ANALYZER_IDENTITY_MISMATCH:{role}")
        function = ir.functions[0]
        if function.name in functions:
            raise RouteError(f"PURE_MODULE_DUPLICATE_SYMBOL:{role}:{function.name}")
        functions[function.name] = function
        diagnostics.extend(ir.diagnostics)
    if sorted(functions) != expected_symbols:
        raise RouteError(f"PURE_MODULE_ANALYZED_SYMBOL_SET_MISMATCH:{role}")
    return SemanticIR(
        source_language=language,
        source_file=first.source_file,
        analyzer=first.analyzer,
        analyzer_version=first.analyzer_version,
        functions=tuple(functions[symbol] for symbol in expected_symbols),
        diagnostics=tuple(diagnostics),
    )


def _module_manifest_signatures(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = manifest.get("functions")
    if not isinstance(entries, list):
        raise RouteError("PURE_MODULE_CASE_MANIFEST_FUNCTIONS_REQUIRED")
    contracts: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RouteError("PURE_MODULE_CASE_MANIFEST_ENTRY_INVALID")
        symbol = entry.get("symbol")
        signature = entry.get("signature")
        if not isinstance(symbol, str) or not symbol or not isinstance(signature, dict):
            raise RouteError("PURE_MODULE_CASE_MANIFEST_ENTRY_INVALID")
        if symbol in contracts:
            raise RouteError(f"PURE_MODULE_CASE_MANIFEST_DUPLICATE_SYMBOL:{symbol}")
        contracts[symbol] = signature
    return contracts


def _inventory_span(subject: dict[str, Any], role: str) -> tuple[int, int]:
    span = subject.get("source_span")
    qualified_name = str(subject.get("qualified_name", subject.get("name", "unknown")))
    if not isinstance(span, dict):
        raise RouteError(f"PURE_MODULE_INVENTORY_SPAN_REQUIRED:{role}:{qualified_name}")
    start = span.get("start_byte")
    end = span.get("end_byte")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        raise RouteError(f"PURE_MODULE_INVENTORY_SPAN_REQUIRED:{role}:{qualified_name}")
    return start, end


def _verify_inventory_analyzer_build_receipt(
    inventory: dict[str, Any],
    *,
    role: str,
    language: Language,
) -> None:
    """Fail closed around the private Swift analyzer build provenance.

    The complete receipt remains in the inventory object.  Consequently its
    exact bytes are covered by the inventory digest, whole-file-closure digest,
    and canonical module input below.  A fresh verifier compares only the
    receipt's stable build-input projection; the scratch-built Mach-O identity
    is deliberately evidence about that one build rather than a cross-build
    reproducibility claim.
    """

    receipt = inventory.get("analyzer_build_receipt")
    if language != "swift":
        if "analyzer_build_receipt" in inventory:
            raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_UNEXPECTED:{role}:{language}")
        return
    if not isinstance(receipt, dict) or set(receipt) != {
        "schema_version",
        "kind",
        "source_inputs",
        "dependency",
        "toolchain",
        "build",
        "binary",
    }:
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    if (
        receipt.get("schema_version") != "1.0.0"
        or receipt.get("kind") != "elmos.swift-analyzer-build-receipt"
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")

    source_inputs = receipt.get("source_inputs")
    dependency = receipt.get("dependency")
    toolchain = receipt.get("toolchain")
    build = receipt.get("build")
    binary = receipt.get("binary")
    if (
        not isinstance(source_inputs, dict)
        or set(source_inputs) != {"sha256", "files"}
        or not isinstance(dependency, dict)
        or set(dependency)
        != {
            "identity",
            "version",
            "revision",
            "sha256",
            "file_count",
            "bytes",
            "mirror",
        }
        or not isinstance(toolchain, dict)
        or set(toolchain)
        != {
            "swiftc",
            "swiftc_sha256",
            "swift_driver",
            "swift_driver_sha256",
            "version",
            "profile",
        }
        or not isinstance(build, dict)
        or set(build)
        != {
            "configuration",
            "automatic_resolution",
            "manifest_cache",
            "environment_policy",
            "argv",
        }
        or not isinstance(binary, dict)
        or set(binary) != {"name", "sha256", "bytes", "mode"}
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")

    files = source_inputs.get("files")
    if not isinstance(files, list) or not files:
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    file_paths: list[str] = []
    for item in files:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "sha256", "bytes"}
            or not isinstance(item.get("path"), str)
            or not item["path"]
            or Path(item["path"]).is_absolute()
            or ".." in Path(item["path"]).parts
            or not isinstance(item.get("bytes"), int)
            or item["bytes"] <= 0
        ):
            raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
        file_paths.append(item["path"])
        _require_sha256(str(item.get("sha256")), f"{role}_swift_analyzer_input")
    if (
        len(set(file_paths)) != len(file_paths)
        or file_paths[:2] != ["Package.swift", "Package.resolved"]
        or file_paths[2:] != sorted(file_paths[2:])
        or not all(path.startswith("Sources/") and path.endswith(".swift") for path in file_paths[2:])
        or source_inputs.get("sha256")
        != _digest(
            json.dumps(
                {"files": files},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INPUT_CLOSURE_MISMATCH:{role}:swift")

    mirror = dependency.get("mirror")
    if (
        dependency.get("identity") != "swift-syntax"
        or not isinstance(dependency.get("version"), str)
        or not dependency["version"]
        or not isinstance(dependency.get("revision"), str)
        or len(dependency["revision"]) != 40
        or any(character not in "0123456789abcdef" for character in dependency["revision"])
        or not isinstance(dependency.get("file_count"), int)
        or dependency["file_count"] <= 0
        or not isinstance(dependency.get("bytes"), int)
        or dependency["bytes"] <= 0
        or not isinstance(mirror, dict)
        or set(mirror) != {"seed", "git", "sha256", "file_count", "bytes"}
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    _require_sha256(str(source_inputs.get("sha256")), f"{role}_swift_analyzer_inputs")
    _require_sha256(str(dependency.get("sha256")), f"{role}_swift_analyzer_dependency")
    _require_sha256(str(mirror.get("sha256")), f"{role}_swift_analyzer_mirror")
    git = mirror.get("git")
    if (
        mirror.get("seed")
        not in {
            "verified-package-source-mirror",
            "verified-user-git-cache",
            "network-exact-revision",
        }
        or not isinstance(mirror.get("file_count"), int)
        or mirror["file_count"] <= 0
        or not isinstance(mirror.get("bytes"), int)
        or mirror["bytes"] <= 0
        or not isinstance(git, dict)
        or set(git) != {"path", "sha256", "version"}
        or git.get("path") != "/usr/bin/git"
        or not isinstance(git.get("version"), str)
        or not git["version"]
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    _require_sha256(str(git.get("sha256")), f"{role}_swift_analyzer_git")
    if (
        dependency["sha256"] != mirror["sha256"]
        or dependency["file_count"] != mirror["file_count"]
        or dependency["bytes"] != mirror["bytes"]
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_DEPENDENCY_MISMATCH:{role}:swift")

    if (
        not isinstance(toolchain.get("swiftc"), str)
        or not toolchain["swiftc"]
        or not isinstance(toolchain.get("swift_driver"), str)
        or not toolchain["swift_driver"]
        or not isinstance(toolchain.get("version"), str)
        or not toolchain["version"]
        or not isinstance(toolchain.get("profile"), list)
        or not toolchain["profile"]
        or not all(isinstance(item, str) and item for item in toolchain["profile"])
        or build.get("configuration") != "release"
        or build.get("automatic_resolution") is not False
        or build.get("manifest_cache") != "none"
        or build.get("environment_policy") != "minimal-empty-home-v1"
        or not isinstance(build.get("argv"), list)
        or not build["argv"]
        or not all(isinstance(item, str) and item for item in build["argv"])
        or binary.get("name") != "ElmosSwiftAnalyzer"
        or not isinstance(binary.get("bytes"), int)
        or not 0 < binary["bytes"] <= 100_000_000
        or binary.get("mode") not in {"0500", "0700", "0755"}
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_INVALID:{role}:swift")
    _require_sha256(str(toolchain.get("swiftc_sha256")), f"{role}_swiftc")
    _require_sha256(str(toolchain.get("swift_driver_sha256")), f"{role}_swift_driver")
    _require_sha256(str(binary.get("sha256")), f"{role}_swift_analyzer_binary")

    analyzer_version = inventory.get("analyzer_version")
    stable_bindings = (
        f"source-inputs={source_inputs['sha256']}",
        f"swift-driver={toolchain['swift_driver_sha256']}",
        f"swift-syntax-tree={dependency['sha256']}",
    )
    if not isinstance(analyzer_version, str) or not all(
        binding in analyzer_version for binding in stable_bindings
    ):
        raise RouteError(f"PURE_MODULE_ANALYZER_BUILD_RECEIPT_BINDING_MISMATCH:{role}:swift")


def _verify_inventory_artifact(
    inventory: dict[str, Any],
    *,
    role: str,
    language: Language,
    logical_file: str,
    artifact_bytes: bytes,
) -> None:
    expected_keys = {
        "schema_version",
        "kind",
        "profile",
        "source_language",
        "source_file",
        "analyzer",
        "analyzer_version",
        "enumeration_status",
        "subjects",
        "diagnostics",
        "source_artifact_sha256",
        "source_artifact_bytes",
        "directives",
    }
    if language == "swift":
        expected_keys.add("analyzer_build_receipt")
    if set(inventory) != expected_keys:
        raise RouteError(f"PURE_MODULE_INVENTORY_KEYS_INVALID:{role}:{language}")
    if inventory.get("enumeration_status") != "PASSED":
        raise RouteError(f"PURE_MODULE_INVENTORY_STATUS_NOT_PASSED:{role}")
    if inventory.get("diagnostics") != []:
        raise RouteError(f"PURE_MODULE_INVENTORY_DIAGNOSTICS_PRESENT:{role}")
    if (
        inventory.get("source_language") != language
        or inventory.get("source_file") != logical_file
        or inventory.get("source_artifact_sha256") != _digest(artifact_bytes)
        or inventory.get("source_artifact_bytes") != len(artifact_bytes)
    ):
        raise RouteError(f"PURE_MODULE_INVENTORY_ARTIFACT_MISMATCH:{role}")
    _verify_inventory_analyzer_build_receipt(inventory, role=role, language=language)


def _verify_language_prelude(
    inventory: dict[str, Any],
    *,
    role: str,
    language: Language,
    artifact_bytes: bytes,
) -> dict[str, Any]:
    expected_raw = {
        ("cpp", "source"): [b"#include <cstdint>"],
        ("cpp", "target"): [
            b"#include <cstdint>",
            b"#include <stdexcept>",
            b"#include <string>",
        ],
        ("objc", "source"): [b"#import <Foundation/Foundation.h>"],
        ("objc", "target"): [b"#import <Foundation/Foundation.h>"],
    }.get((language, role), [])
    directives = inventory.get("directives")
    if not isinstance(directives, list):
        raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_INVENTORY_INVALID:{role}")
    if len(directives) != len(expected_raw):
        raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_MISMATCH:{role}:{language}")
    for order, (directive, expected) in enumerate(zip(directives, expected_raw, strict=True)):
        if not isinstance(directive, dict) or set(directive) != {
            "order",
            "kind",
            "value",
            "source_span",
            "sha256",
        }:
            raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_INVENTORY_INVALID:{role}")
        source_span = directive.get("source_span")
        if not isinstance(source_span, dict):
            raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_INVENTORY_INVALID:{role}")
        start = source_span.get("start_byte")
        end = source_span.get("end_byte")
        observed = (
            artifact_bytes[start:end]
            if isinstance(start, int) and isinstance(end, int)
            else b""
        )
        expected_kind, expected_value = expected[1:].split(maxsplit=1)
        if (
            directive.get("order") != order
            or directive.get("kind") != expected_kind.decode("ascii")
            or directive.get("value") != expected_value.decode("utf-8")
            or source_span.get("file") != inventory.get("source_file")
            or observed != expected
            or directive.get("sha256") != _digest(expected)
        ):
            raise RouteError(f"PURE_MODULE_LANGUAGE_PRELUDE_MISMATCH:{role}:{language}")
    return {
        "status": "EXACT_AND_CLOSED",
        "role": role,
        "language": language,
        "directives": directives,
    }


def _separate_verified_language_wrapper(
    inventory: dict[str, Any],
    *,
    role: str,
    language: Language,
) -> tuple[dict[str, Any], dict[str, Any]]:
    subjects = inventory.get("subjects")
    if not isinstance(subjects, list):
        raise RouteError(f"PURE_MODULE_INVENTORY_SUBJECTS_INVALID:{role}")
    wrappers = [
        subject
        for subject in subjects
        if isinstance(subject, dict)
        and subject.get("declaration_kind") == "top-level-class-wrapper"
    ]
    if language != "java":
        if wrappers:
            raise RouteError(f"PURE_MODULE_LANGUAGE_WRAPPER_UNEXPECTED:{role}:{language}")
        return inventory, {
            "status": "NOT_APPLICABLE",
            "role": role,
            "language": language,
            "file": inventory.get("source_file"),
        }
    if len(wrappers) != 1:
        raise RouteError(f"PURE_MODULE_LANGUAGE_WRAPPER_COUNT_MISMATCH:{role}:{len(wrappers)}")
    wrapper = wrappers[0]
    expected_name = Path(str(inventory.get("source_file"))).stem
    if (
        wrapper.get("name") != expected_name
        or wrapper.get("qualified_name") != expected_name
        or wrapper.get("analyzable") is not False
        or wrapper.get("occurrence") != 1
    ):
        raise RouteError(f"PURE_MODULE_LANGUAGE_WRAPPER_IDENTITY_MISMATCH:{role}")
    expected_signature = {
        "type_kind": "CLASS",
        "visibility": "public",
        "storage": "top-level",
        "modifiers": ["final", "public"],
        "final": True,
        "abstract": False,
        "extends": "",
        "implements": [],
        "type_parameters": [],
        "annotations": [],
        "permits": [],
    }
    if wrapper.get("signature") != expected_signature:
        raise RouteError(f"PURE_MODULE_LANGUAGE_WRAPPER_SIGNATURE_MISMATCH:{role}")
    wrapper_start, wrapper_end = _inventory_span(wrapper, role)
    members: list[dict[str, Any]] = []
    member_kinds = {
        "constructor",
        "field",
        "instance-initializer",
        "method",
        "nested-type",
        "static-initializer",
    }
    for subject in subjects:
        if subject is wrapper or not isinstance(subject, dict):
            continue
        if subject.get("declaration_kind") not in member_kinds:
            continue
        start, end = _inventory_span(subject, role)
        if not (wrapper_start <= start and end <= wrapper_end):
            raise RouteError(
                "PURE_MODULE_LANGUAGE_WRAPPER_SPAN_CONTAINMENT_MISMATCH:"
                f"{role}:{subject.get('qualified_name')}"
            )
        members.append(
            {
                "name": subject["name"],
                "qualified_name": subject["qualified_name"],
                "declaration_kind": subject["declaration_kind"],
                "occurrence": subject["occurrence"],
                "source_span": subject["source_span"],
            }
        )
    filtered_inventory = {
        **inventory,
        "subjects": [subject for subject in subjects if subject is not wrapper],
    }
    return filtered_inventory, {
        "status": "EXACT_AND_CLOSED",
        "role": role,
        "language": language,
        "file": inventory["source_file"],
        "name": wrapper["name"],
        "qualified_name": wrapper["qualified_name"],
        "declaration_kind": wrapper["declaration_kind"],
        "analyzable": wrapper["analyzable"],
        "occurrence": wrapper["occurrence"],
        "source_span": wrapper["source_span"],
        "signature": wrapper["signature"],
        "member_span_status": "ALL_CONTAINED",
        "member_subjects": sorted(
            members,
            key=lambda item: (
                int(item["source_span"]["start_byte"]),
                str(item["qualified_name"]),
            ),
        ),
    }


def _verify_profile_subject_contract(
    language: Language,
    subject: dict[str, Any],
    *,
    role: str,
    symbol: str,
) -> None:
    expected = {
        "cpp": ("FunctionDecl", "external", "none"),
        "objc": ("FunctionDecl", "external", "none"),
        "swift": ("FunctionDeclSyntax", "internal", "file-scope"),
        "java": ("method", "public", "static"),
    }.get(language)
    if expected is None:
        return
    signature = subject.get("signature")
    if not isinstance(signature, dict):
        raise RouteError(f"PURE_MODULE_PROFILE_SIGNATURE_MISMATCH:{role}:{symbol}")
    declaration_kind, visibility, storage = expected
    if (
        subject.get("declaration_kind") != declaration_kind
        or signature.get("visibility") != visibility
        or signature.get("storage") != storage
    ):
        raise RouteError(f"PURE_MODULE_PROFILE_DECLARATION_CONTRACT_MISMATCH:{role}:{symbol}")
    if language == "java" and signature.get("modifiers") != ["public", "static"]:
        raise RouteError(f"PURE_MODULE_PROFILE_DECLARATION_CONTRACT_MISMATCH:{role}:{symbol}")


def _profile_symbol_record(
    subject: dict[str, Any],
    function: Function,
    *,
    role: str,
) -> dict[str, Any]:
    signature = subject.get("signature")
    assert isinstance(signature, dict)
    raw_parameters = signature.get("parameters")
    if not isinstance(raw_parameters, list):
        raw_parameters = []
    if function.source_span is None or function.source_span.to_mapping() != subject.get(
        "source_span"
    ):
        raise RouteError(f"PURE_MODULE_PROFILE_SPAN_MISMATCH:{role}:{function.name}")
    return {
        "symbol": function.name,
        "qualified_name": subject["qualified_name"],
        "declaration_kind": subject["declaration_kind"],
        "occurrence": subject["occurrence"],
        "source_span": subject["source_span"],
        "raw_signature": signature,
        "raw_parameter_names": [
            parameter.get("name") for parameter in raw_parameters if isinstance(parameter, dict)
        ],
        "canonical_signature": function.signature_mapping(),
    }


def _close_profile_inventory(
    inventory: dict[str, Any],
    ir: SemanticIR,
    manifest_signatures: dict[str, dict[str, Any]],
    *,
    role: str,
    helper_regions: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    functions = {function.name: function for function in ir.functions}
    if set(functions) != set(manifest_signatures):
        raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_SET_MISMATCH:{role}")
    for symbol, function in functions.items():
        if function.signature_mapping() != manifest_signatures[symbol]:
            raise RouteError(f"PURE_MODULE_PROFILE_SIGNATURE_MISMATCH:{role}:{symbol}")

    profile_subjects: dict[str, dict[str, Any]] = {}
    helper_subjects: list[dict[str, Any]] = []
    subjects = inventory.get("subjects")
    if not isinstance(subjects, list):
        raise RouteError(f"PURE_MODULE_INVENTORY_SUBJECTS_INVALID:{role}")
    for subject in subjects:
        if not isinstance(subject, dict):
            raise RouteError(f"PURE_MODULE_INVENTORY_SUBJECTS_INVALID:{role}")
        start, end = _inventory_span(subject, role)
        matched_helpers = [
            region
            for region in helper_regions or []
            if region["start_byte"] <= start and end <= region["end_byte"]
        ]
        if len(matched_helpers) > 1:
            raise RouteError("PURE_MODULE_TARGET_HELPER_REGION_OVERLAP")
        if matched_helpers:
            helper_subjects.append({**subject, "helper_id": matched_helpers[0]["helper_id"]})
            continue

        raw_symbol = subject.get("name")
        qualified_name = str(subject.get("qualified_name", raw_symbol or "unknown"))
        declaration_kind = str(subject.get("declaration_kind", "unknown"))
        if not isinstance(raw_symbol, str) or raw_symbol not in manifest_signatures:
            raise RouteError(
                "PURE_MODULE_WHOLE_FILE_DECLARATION_NOT_ALLOWED:"
                f"{role}:{declaration_kind}:{qualified_name}"
            )
        symbol = raw_symbol
        if subject.get("analyzable") is not True:
            raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_NOT_ANALYZABLE:{role}:{qualified_name}")
        if symbol in profile_subjects:
            raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_DUPLICATED:{role}:{symbol}")
        _verify_profile_subject_contract(
            ir.source_language,
            subject,
            role=role,
            symbol=symbol,
        )
        profile_subjects[symbol] = subject

    if set(profile_subjects) != set(manifest_signatures):
        raise RouteError(f"PURE_MODULE_PROFILE_SYMBOL_SET_MISMATCH:{role}")

    records: list[dict[str, Any]] = []
    for symbol in sorted(manifest_signatures):
        function = functions[symbol]
        subject = profile_subjects[symbol]
        record = _profile_symbol_record(subject, function, role=role)
        expected_parameter_names = [parameter.name for parameter in function.parameters]
        if record["raw_parameter_names"] != expected_parameter_names:
            raise RouteError(f"PURE_MODULE_PROFILE_SIGNATURE_MISMATCH:{role}:{symbol}")
        records.append(record)
    return records, helper_subjects


def _emitted_helper_regions(emitted: EmittedFile, target_language: Language) -> list[dict[str, Any]]:
    registry = _HELPERS.get(target_language, {})
    emitted_bytes = emitted.content.encode("utf-8")
    regions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for helper_id, claimed_digest in emitted.helper_digests:
        if helper_id in seen:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_DUPLICATED:{helper_id}")
        seen.add(helper_id)
        helper_source = registry.get(helper_id)
        if helper_source is None:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_UNREGISTERED:{helper_id}")
        helper_bytes = helper_source.encode("utf-8")
        observed_digest = _digest(helper_bytes)
        if claimed_digest != observed_digest:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_DIGEST_MISMATCH:{helper_id}")
        if emitted_bytes.count(helper_bytes) != 1:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_SOURCE_COUNT_INVALID:{helper_id}")
        start = emitted_bytes.index(helper_bytes)
        regions.append(
            {
                "helper_id": helper_id,
                "sha256": observed_digest,
                "bytes": len(helper_bytes),
                "start_byte": start,
                "end_byte": start + len(helper_bytes),
            }
        )
    return sorted(regions, key=lambda item: (item["start_byte"], item["helper_id"]))


def _verify_helper_visibility(language: Language, subject: dict[str, Any]) -> tuple[str, str]:
    signature = subject.get("signature")
    if not isinstance(signature, dict):
        raise RouteError("PURE_MODULE_TARGET_HELPER_SIGNATURE_INVALID")
    visibility = signature.get("visibility")
    storage = signature.get("storage")
    allowed = {
        "cpp": {("internal", "static")},
        "objc": {("internal", "static")},
        "java": {("private", "static")},
        "swift": {("private", "file-scope"), ("fileprivate", "file-scope")},
    }.get(language, set())
    if (visibility, storage) not in allowed:
        raise RouteError(
            "PURE_MODULE_TARGET_HELPER_VISIBILITY_INVALID:"
            f"{subject.get('helper_id')}:{subject.get('qualified_name')}"
        )
    return str(visibility), str(storage)


def _specialized_helper_contract(
    language: Language,
    helper_id: str,
) -> tuple[str, str, int]:
    candidates: set[tuple[str, int]] = set()
    for callee, helper_ids in _CHECKED_INTEGER_CALL.get(language, {}).values():
        if helper_id in helper_ids:
            candidates.add((callee, 2))
    float_guard = _FLOAT_NON_ZERO_GUARD.get(language)
    if float_guard is not None and helper_id == float_guard[1]:
        candidates.add((float_guard[0], 1))
    if len(candidates) != 1:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_CONTRACT_MISSING:{helper_id}")
    qualified_name, arity = candidates.pop()
    return qualified_name.rsplit(".", 1)[-1], qualified_name, arity


def _verify_specialized_helper_subject(
    *,
    language: Language,
    region: dict[str, Any],
    symbols: list[dict[str, Any]],
    target_bytes: bytes,
) -> None:
    helper_id = str(region["helper_id"])
    if len(symbols) != 1:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SUBJECT_SET_MISMATCH:{helper_id}")
    symbol = symbols[0]
    if symbol.get("analyzable") is not True:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_NOT_ANALYZABLE:{helper_id}")
    expected_kinds = {
        "cpp": "FunctionDecl",
        "objc": "FunctionDecl",
        "java": "method",
        "swift": "FunctionDeclSyntax",
    }
    if symbol.get("declaration_kind") != expected_kinds[language]:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_DECLARATION_KIND_INVALID:{helper_id}")
    expected_name, expected_qualified_name, expected_arity = _specialized_helper_contract(
        language, helper_id
    )
    if (
        symbol.get("name") != expected_name
        or symbol.get("qualified_name") not in {expected_name, expected_qualified_name}
    ):
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_NAME_MISMATCH:{helper_id}")
    signature = symbol.get("raw_signature")
    parameters = signature.get("parameters") if isinstance(signature, dict) else None
    if not isinstance(parameters, list) or len(parameters) != expected_arity:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SIGNATURE_MISMATCH:{helper_id}")
    if symbol.get("occurrence") != 1:
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_OCCURRENCE_INVALID:{helper_id}")
    source_span = symbol.get("source_span")
    if not isinstance(source_span, dict):
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SPAN_COVERAGE_INVALID:{helper_id}")
    start = source_span.get("start_byte")
    end = source_span.get("end_byte")
    if not isinstance(start, int) or not isinstance(end, int):
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SPAN_COVERAGE_INVALID:{helper_id}")
    prefix = target_bytes[int(region["start_byte"]):start]
    suffix = target_bytes[end:int(region["end_byte"])]
    if prefix.strip() or suffix.strip():
        raise RouteError(f"PURE_MODULE_TARGET_HELPER_SPAN_COVERAGE_INVALID:{helper_id}")


def _function_operator_uses(function: Function) -> set[tuple[str, str]]:
    environment = types.check_function(function)
    uses: set[tuple[str, str]] = set()

    def expression_uses(expression: Expression) -> None:
        if expression.kind != "binary" or expression.left is None or expression.right is None:
            return
        left_type = types.infer(expression.left, environment)
        right_type = types.infer(expression.right, environment)
        domain = "integer" if left_type == right_type == "integer" else "number"
        uses.add((domain, str(expression.operator)))
        expression_uses(expression.left)
        expression_uses(expression.right)

    def statement_uses(statement: Statement) -> None:
        if statement.expression is not None:
            expression_uses(statement.expression)
        if statement.condition is not None:
            expression_uses(statement.condition)
        for nested in (*statement.then_body, *statement.else_body):
            statement_uses(nested)

    for statement in function.body:
        statement_uses(statement)
    return uses


def _target_call_graph(
    target_ir: SemanticIR,
    emitted: EmittedFile,
    target_helper_symbols: list[dict[str, Any]],
) -> dict[str, Any]:
    helper_identifiers = {
        str(identifier)
        for symbol in target_helper_symbols
        for identifier in (symbol["name"], symbol["qualified_name"])
    }
    helper_ids = {str(symbol["helper_id"]) for symbol in target_helper_symbols}
    registered_rules: dict[str, tuple[str, str, str, tuple[str, ...]]] = {}
    for operator, (callee, required_helpers) in _CHECKED_INTEGER_CALL.get(
        target_ir.source_language, {}
    ).items():
        rule = f"{target_ir.source_language}.integer.{operator}.call:{callee}"
        registered_rules[rule] = ("integer", operator, callee, required_helpers)
    float_guard = _FLOAT_NON_ZERO_GUARD.get(target_ir.source_language)
    if float_guard is not None:
        callee, helper_id = float_guard
        for operator in ("/", "%"):
            rule = f"{target_ir.source_language}.number.{operator}.non-zero:{callee}"
            registered_rules[rule] = ("number", operator, callee, (helper_id,))

    call_rules = {
        rule
        for rule in emitted.normalization_rules
        if ".call:" in rule or ".non-zero:" in rule
    }
    if not call_rules <= set(registered_rules):
        raise RouteError("PURE_MODULE_TARGET_CALL_NORMALIZATION_INVALID")

    edges: list[dict[str, Any]] = []
    matched_rules: set[str] = set()
    for rule in sorted(call_rules):
        domain, operator, callee, required_helpers = registered_rules[rule]
        if required_helpers:
            if not set(required_helpers) <= helper_ids or callee not in helper_identifiers:
                raise RouteError(f"PURE_MODULE_TARGET_CALL_GRAPH_HELPER_MISMATCH:{rule}")
            callee_kind = "exact-generated-helper"
        else:
            if callee in helper_identifiers:
                raise RouteError(f"PURE_MODULE_TARGET_CALL_GRAPH_BUILTIN_MISMATCH:{rule}")
            callee_kind = "pinned-target-builtin"
        for function in target_ir.functions:
            if (domain, operator) not in _function_operator_uses(function):
                continue
            matched_rules.add(rule)
            edges.append(
                {
                    "caller": function.name,
                    "callee": callee,
                    "callee_kind": callee_kind,
                    "canonical_domain": domain,
                    "canonical_operator": operator,
                    "normalization_rule": rule,
                }
            )
    if matched_rules != call_rules:
        raise RouteError("PURE_MODULE_TARGET_CALL_GRAPH_NOT_CLOSED")
    return {
        "status": "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS",
        "scope": "profile-functions-to-emitted-callees",
        "edges": sorted(
            edges,
            key=lambda edge: (
                edge["caller"],
                edge["callee"],
                edge["canonical_domain"],
                edge["canonical_operator"],
            ),
        ),
        "helper_internal_calls": {
            "status": "CONTENT_BOUND_NOT_EDGE_ENUMERATED",
            "binding": "verified_generated_helpers-exact-bytes-and-digests",
        },
    }


def _build_whole_file_closure(
    *,
    source_inventory: dict[str, Any],
    target_inventory: dict[str, Any],
    source_ir: SemanticIR,
    target_ir: SemanticIR,
    manifest: dict[str, Any],
    source_bytes: bytes,
    emitted: EmittedFile,
) -> dict[str, Any]:
    manifest_signatures = _module_manifest_signatures(manifest)
    target_bytes = emitted.content.encode("utf-8")
    _verify_inventory_artifact(
        source_inventory,
        role="source",
        language=source_ir.source_language,
        logical_file=source_ir.source_file,
        artifact_bytes=source_bytes,
    )
    _verify_inventory_artifact(
        target_inventory,
        role="target",
        language=target_ir.source_language,
        logical_file=target_ir.source_file,
        artifact_bytes=target_bytes,
    )
    source_prelude = _verify_language_prelude(
        source_inventory,
        role="source",
        language=source_ir.source_language,
        artifact_bytes=source_bytes,
    )
    target_prelude = _verify_language_prelude(
        target_inventory,
        role="target",
        language=target_ir.source_language,
        artifact_bytes=target_bytes,
    )
    source_profile_inventory, source_wrapper = _separate_verified_language_wrapper(
        source_inventory,
        role="source",
        language=source_ir.source_language,
    )
    target_profile_inventory, target_wrapper = _separate_verified_language_wrapper(
        target_inventory,
        role="target",
        language=target_ir.source_language,
    )
    source_profile_symbols, source_helpers = _close_profile_inventory(
        source_profile_inventory,
        source_ir,
        manifest_signatures,
        role="source",
    )
    if source_helpers:
        raise RouteError("PURE_MODULE_SOURCE_HELPER_EXCEPTION_FORBIDDEN")

    helper_regions = _emitted_helper_regions(emitted, target_ir.source_language)
    target_profile_symbols, raw_helper_subjects = _close_profile_inventory(
        target_profile_inventory,
        target_ir,
        manifest_signatures,
        role="target",
        helper_regions=helper_regions,
    )
    helpers_by_id: dict[str, list[dict[str, Any]]] = {
        str(region["helper_id"]): [] for region in helper_regions
    }
    target_helper_symbols: list[dict[str, Any]] = []
    for subject in raw_helper_subjects:
        helper_id = str(subject["helper_id"])
        visibility, storage = _verify_helper_visibility(target_ir.source_language, subject)
        signature = subject["signature"]
        parameters = signature.get("parameters")
        arity = len(parameters) if isinstance(parameters, list) else 0
        symbol = {
            "helper_id": helper_id,
            "name": subject["name"],
            "qualified_name": subject["qualified_name"],
            "declaration_kind": subject["declaration_kind"],
            "analyzable": subject["analyzable"],
            "occurrence": subject["occurrence"],
            "arity": arity,
            "visibility": visibility,
            "storage": storage,
            "source_span": subject["source_span"],
            "raw_signature": signature,
        }
        helpers_by_id[helper_id].append(symbol)
        target_helper_symbols.append(symbol)

    verified_helpers: list[dict[str, Any]] = []
    for region in helper_regions:
        helper_id = str(region["helper_id"])
        symbols = sorted(helpers_by_id[helper_id], key=lambda item: item["qualified_name"])
        if not symbols:
            raise RouteError(f"PURE_MODULE_TARGET_HELPER_INVENTORY_MISSING:{helper_id}")
        if is_specialized_pair(source_ir.source_language, target_ir.source_language):
            _verify_specialized_helper_subject(
                language=target_ir.source_language,
                region=region,
                symbols=symbols,
                target_bytes=target_bytes,
            )
        verified_helpers.append(
            {
                **region,
                "source_span": {
                    "file": emitted.relative_path,
                    "start_byte": region["start_byte"],
                    "end_byte": region["end_byte"],
                },
                "symbols": symbols,
            }
        )

    source_inventory_bytes = canonical_json_bytes(source_inventory)
    target_inventory_bytes = canonical_json_bytes(target_inventory)
    target_call_graph = _target_call_graph(target_ir, emitted, target_helper_symbols)
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-whole-file-closure",
        "profile": "typed-pure-module-v1",
        "route": {
            "source_language": source_ir.source_language,
            "target_language": target_ir.source_language,
        },
        "status": "PASSED",
        "source_inventory_sha256": _digest(source_inventory_bytes),
        "source_inventory_bytes": len(source_inventory_bytes),
        "target_inventory_sha256": _digest(target_inventory_bytes),
        "target_inventory_bytes": len(target_inventory_bytes),
        "manifest_symbols": sorted(manifest_signatures),
        "source_profile_symbols": source_profile_symbols,
        "target_profile_symbols": target_profile_symbols,
        "target_helper_symbols": sorted(
            target_helper_symbols, key=lambda item: (item["helper_id"], item["qualified_name"])
        ),
        "verified_generated_helpers": verified_helpers,
        "verified_language_prelude": {
            "source": source_prelude,
            "target": target_prelude,
        },
        "verified_language_wrapper": {
            "source": source_wrapper,
            "target": target_wrapper,
        },
        "blocked_declarations": {"source": [], "target": []},
        "source_user_call_graph": {"edges": [], "status": "EMPTY_AND_CLOSED"},
        "target_call_graph_policy": "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS",
        "target_call_graph": target_call_graph,
        "target_builtin_normalizations": list(emitted.normalization_rules),
    }


def migrate_module(
    source: Path,
    source_language: Language,
    target_language: Language,
    manifest_path: Path,
    output: Path,
) -> dict[str, Any]:
    """Snapshot immutable module inputs, then run the closed migration."""

    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    if not is_routed_pair(source_language, target_language):
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    resolved_source = source.resolve()
    resolved_manifest = manifest_path.resolve()
    source_bytes = resolved_source.read_bytes()
    manifest_bytes = resolved_manifest.read_bytes()
    with tempfile.TemporaryDirectory(prefix="elmos-module-input-snapshot-") as temporary:
        snapshot_root = Path(temporary)
        snapshot_root.chmod(0o700)
        source_snapshot = _private_input_snapshot(
            snapshot_root,
            "source",
            resolved_source.name,
            source_bytes,
        )
        manifest_snapshot = _private_input_snapshot(
            snapshot_root,
            "manifest",
            resolved_manifest.name,
            manifest_bytes,
        )
        return _migrate_module_snapshot(
            source_snapshot,
            source_language,
            target_language,
            manifest_snapshot,
            output,
        )


def _migrate_module_snapshot(
    source: Path,
    source_language: Language,
    target_language: Language,
    manifest_path: Path,
    output: Path,
) -> dict[str, Any]:
    """Analyze, emit, relift, execute, and compose a real pure module."""

    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    if not is_routed_pair(source_language, target_language):
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    source = source.resolve()
    manifest_path = manifest_path.resolve()
    source_bytes = source.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    manifest = _load_module_manifest(manifest_path)
    symbols = _manifest_symbols(manifest)

    # Whole-file closure is a precondition, not evidence appended after the
    # conversion has already emitted output. The real compiler inventory runs
    # before any caller-owned output directory is created.
    source_inventory = inventory_module(source, source_language)
    source_analyses = [analyze(source, source_language, symbol) for symbol in symbols]
    source_ir = _combine_function_irs(source_analyses, symbols, source_language, "source")
    _enforce_specialized_semantic_domain(source_ir, source_language, target_language)
    cases_by_symbol = normalize_pure_module_case_manifest(
        manifest,
        {function.name: function for function in source_ir.functions},
    )
    for function in source_ir.functions:
        _enforce_specialized_case_domain(
            function,
            cases_by_symbol[function.name],
            source_language,
            target_language,
        )
    emitted = emit(source_ir, target_language)
    with tempfile.TemporaryDirectory(prefix="elmos-module-closure-") as temporary:
        target_path = Path(temporary) / emitted.relative_path
        target_path.write_text(emitted.content, encoding="utf-8")
        target_inventory = inventory_module(target_path, target_language)
        target_analyses = [
            analyze(target_path, target_language, symbol, emitted_target=True)
            for symbol in symbols
        ]
    target_ir = _combine_function_irs(target_analyses, symbols, target_language, "target")
    _enforce_specialized_semantic_domain(target_ir, source_language, target_language)
    whole_file_closure = _build_whole_file_closure(
        source_inventory=source_inventory,
        target_inventory=target_inventory,
        source_ir=source_ir,
        target_ir=target_ir,
        manifest=manifest,
        source_bytes=source_bytes,
        emitted=emitted,
    )
    if source.read_bytes() != source_bytes:
        raise RouteError("PURE_MODULE_SOURCE_CHANGED_DURING_CLOSURE")
    if manifest_path.read_bytes() != manifest_bytes:
        raise RouteError("PURE_MODULE_CASE_MANIFEST_CHANGED_DURING_CLOSURE")

    output = safe_output(output)
    output.mkdir(parents=True, exist_ok=True)
    source_validation: dict[str, Any] = {}
    source_observations: dict[str, list[dict[str, Any]]] = {}
    for index, symbol in enumerate(symbols):
        function = next(item for item in source_ir.functions if item.name == symbol)
        validation = validate_source(
            source,
            source_language,
            function,
            cases_by_symbol[symbol],
            output / "source-runtime" / f"{index:03d}",
        )
        source_validation[symbol] = validation
        source_observations[symbol] = list(validation.get("observations", []))

    target_validation: dict[str, Any] = {}
    target_observations: dict[str, list[dict[str, Any]]] = {}
    for index, symbol in enumerate(symbols):
        function = next(item for item in source_ir.functions if item.name == symbol)
        validation = validate(
            emitted,
            target_language,
            function,
            cases_by_symbol[symbol],
            output / "target-runtime" / f"{index:03d}",
        )
        target_validation[symbol] = validation
        target_observations[symbol] = list(validation.get("observations", []))

    report = verify_pure_module(
        source_ir=source_ir,
        target_ir=target_ir,
        case_manifest=manifest,
        source_observations=source_observations,
        target_observations=target_observations,
        source_artifact_sha256=_digest(source_bytes),
        target_artifact_sha256=_digest(emitted.content.encode("utf-8")),
        corpus_sha256=_digest(manifest_bytes),
        emitted=emitted,
        source_artifact_bytes=source_bytes,
        source_logical_file=source.name,
        case_manifest_bytes=manifest_bytes,
        source_inventory=source_inventory,
        target_inventory=target_inventory,
        whole_file_closure=whole_file_closure,
        output=output,
    )
    source_validation_path = output / "source-module-validation.json"
    target_validation_path = output / "target-module-validation.json"
    write_json(source_validation_path, source_validation)
    write_json(target_validation_path, target_validation)
    report["source_validation"] = source_validation
    report["target_validation"] = target_validation
    report["artifact_refs"].extend(
        [
            _artifact_ref(output, source_validation_path, "source-module-validation"),
            _artifact_ref(output, target_validation_path, "target-module-validation"),
        ]
    )
    write_json(output / "typed-pure-module-equivalence.json", report)
    if report["status"] != "PASSED":
        raise RouteError("PURE_MODULE_EQUIVALENCE_FAILED")
    return report


def migrate(
    source: Path,
    source_language: Language,
    target_language: Language,
    function_name: str,
    cases_path: Path,
    output: Path,
    *,
    repository_execution_mode: bool = False,
) -> dict[str, Any]:
    """Snapshot immutable single-function inputs before any compiler phase."""

    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    routed_pair = is_routed_pair(source_language, target_language)
    if not routed_pair and not repository_execution_mode:
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    resolved_source = source.resolve()
    resolved_cases = cases_path.resolve()
    source_bytes = resolved_source.read_bytes()
    cases_bytes = resolved_cases.read_bytes()
    with tempfile.TemporaryDirectory(prefix="elmos-function-input-snapshot-") as temporary:
        snapshot_root = Path(temporary)
        snapshot_root.chmod(0o700)
        source_snapshot = _private_input_snapshot(
            snapshot_root,
            "source",
            resolved_source.name,
            source_bytes,
        )
        cases_snapshot = _private_input_snapshot(
            snapshot_root,
            "cases",
            resolved_cases.name,
            cases_bytes,
        )
        return _migrate_from_snapshot(
            source_snapshot,
            source_language,
            target_language,
            function_name,
            cases_snapshot,
            output,
            repository_execution_mode=repository_execution_mode,
        )


def _migrate_from_snapshot(
    source: Path,
    source_language: Language,
    target_language: Language,
    function_name: str,
    cases_path: Path,
    output: Path,
    *,
    repository_execution_mode: bool = False,
) -> dict[str, Any]:
    """Translate and execute one bounded function.

    ``repository_execution_mode`` is deliberately non-certifying. It opens
    every distinct pair in ``SUPPORTED_LANGUAGES`` for source/target compiler
    and behavior execution so repository orchestration has a complete 72-pair
    local surface, while skipping route-pack layered/formal claims. The report
    remains ``PASSED_LOCAL_UNCERTIFIED`` with critical unknown semantics until
    the exact directed route has independent repository evidence.
    """
    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    routed_pair = is_routed_pair(source_language, target_language)
    if not routed_pair and not repository_execution_mode:
        raise RouteError(f"UNSUPPORTED_DIRECTED_ROUTE:{source_language}-to-{target_language}")
    output = safe_output(output)
    ir = analyze(source, source_language, function_name)
    if len(ir.functions) != 1:
        raise RouteError("EXACTLY_ONE_FUNCTION_REQUIRED")
    _enforce_specialized_semantic_domain(ir, source_language, target_language)
    function = ir.functions[0]
    cases = _load_cases(cases_path, len(function.parameters))
    _enforce_specialized_case_domain(
        function, cases, source_language, target_language
    )
    source_runtime_evidence: dict[str, Any] | None = None
    if routed_pair or repository_execution_mode:
        source_runtime_evidence = validate_source(
            source,
            source_language,
            function,
            cases,
            output / "source-runtime",
        )
    emitted = emit(ir, target_language)
    evidence = validate(emitted, target_language, function, cases, output)
    ir_path = output / "semantic-ir.json"
    source_ir_path = output / "source-semantic-ir.json"
    source_ir_bytes = canonical_json_bytes(ir.to_mapping())
    ir_path.write_bytes(source_ir_bytes)
    source_ir_path.write_bytes(source_ir_bytes)
    source_bytes = source.read_bytes()
    emitted_bytes = (output / emitted.relative_path).read_bytes()
    layered_refs: dict[str, Any] | None = None
    semantic_summary: dict[str, Any] | None = None
    chunk_summary: dict[str, Any] | None = None
    behavior_summary: dict[str, Any] | None = None
    formal_summary: dict[str, Any] | None = None
    layered_summary: dict[str, Any] | None = None
    if routed_pair and not repository_execution_mode:
        target_ir = analyze(
            output / emitted.relative_path,
            target_language,
            function_name,
            emitted_target=True,
        )
        if len(target_ir.functions) != 1:
            raise RouteError("TARGET_REANALYSIS_EXACTLY_ONE_FUNCTION_REQUIRED")
        target_ir_path = output / "target-semantic-ir.normalized.json"
        target_ir_sha256 = write_json(target_ir_path, target_ir.to_mapping())
        source_ir_sha256 = sha256_bytes(source_ir_path.read_bytes())
        semantic_summary = semantic_equivalence(ir, target_ir)
        semantic_artifact = output / "semantic-equivalence.json"
        semantic_artifact_sha256 = write_json(semantic_artifact, semantic_summary)
        chunk_summary = chunk_equivalence(
            ir,
            target_ir,
            _digest(source_bytes),
            _digest(emitted_bytes),
            emitted,
            source_artifact_bytes=source_bytes,
            target_artifact_bytes=emitted_bytes,
            source_logical_file=source.name,
            target_logical_file=emitted.relative_path,
            require_concrete_spans=requires_concrete_source_spans(
                source_language,
                target_language,
                TYPED_PURE_FUNCTION_PROFILE,
            ),
        )
        chunk_artifact = output / "chunk-map.json"
        chunk_artifact_sha256 = write_json(chunk_artifact, chunk_summary)
        behavior_summary = behavior_equivalence(
            function,
            cases,
            list(source_runtime_evidence.get("observations", [])) if source_runtime_evidence else [],
            list(evidence.get("observations", [])),
        )
        behavior_artifact = output / "behavior-equivalence.json"
        behavior_artifact_sha256 = write_json(behavior_artifact, behavior_summary)
        source_ir_reference = {
            "path": source_ir_path.name,
            "sha256": source_ir_sha256,
        }
        target_ir_reference = {
            "path": target_ir_path.name,
            "sha256": target_ir_sha256,
        }
        formal_input_path = output / "formal-input.json"
        formal_input_digest = write_json(
            formal_input_path,
            _formal_input_payload(
                source_language=source_language,
                target_language=target_language,
                source_path=source.name,
                source_bytes=source_bytes,
                target_path=emitted.relative_path,
                target_bytes=emitted_bytes,
                source_ir=ir,
                target_ir=target_ir,
                source_ir_reference=source_ir_reference,
                target_ir_reference=target_ir_reference,
                emitted=emitted,
            ),
        )
        formal_input_reference = {
            "path": formal_input_path.name,
            "sha256": formal_input_digest,
        }
        verify_formal_input_closure(output, formal_input_reference)
        formal_result, smt2 = formal_equivalence(
            function,
            target_ir.functions[0],
            source_language,
            target_language,
            formal_input_digest,
            formal_input_reference=formal_input_reference,
        )
        smt2_path = output / "formal-equivalence.smt2"
        smt2_path.write_text(smt2, encoding="utf-8")
        smt2_sha256 = sha256_bytes(smt2_path.read_bytes())
        formal_result["formal_input_digest"] = formal_input_digest
        formal_result["solver_input_digest"] = smt2_sha256
        proof_result_path = output / "formal-proof-result.json"
        proof_result_sha256 = write_json(proof_result_path, formal_result)
        formal_summary = {
            **formal_result,
            "proof_artifact_digests": [
                {
                    "property_id": formal_result["property_id"],
                    "path": smt2_path.name,
                    "sha256": smt2_sha256,
                    "strength": formal_result["proof_strength"],
                    "status": formal_result["property_status"],
                    "formal_input_sha256": formal_input_digest,
                },
                {
                    "property_id": formal_result["property_id"],
                    "path": proof_result_path.name,
                    "sha256": proof_result_sha256,
                    "strength": formal_result["proof_strength"],
                    "status": formal_result["property_status"],
                    "formal_input_sha256": formal_input_digest,
                },
            ],
        }
        verify_content_reference(
            output,
            {"path": smt2_path.name, "sha256": smt2_sha256},
        )
        verify_content_reference(
            output,
            {"path": proof_result_path.name, "sha256": proof_result_sha256},
        )
        formal_artifact = output / "formal-composition.json"
        formal_artifact_sha256 = write_json(formal_artifact, formal_summary)
        route_key = DirectedRouteKey(
            source_language=source_language,
            target_language=target_language,
            profile="typed-pure-function-v1",
            source_artifact_sha256=_digest(source_bytes),
            target_artifact_sha256=_digest(emitted_bytes),
            corpus_sha256=_digest(cases_path.read_bytes()),
            source_analyzer=ir.analyzer,
            source_analyzer_version=ir.analyzer_version,
            target_analyzer=target_ir.analyzer,
            target_analyzer_version=target_ir.analyzer_version,
        )
        layered_refs = {
            "semantic": {
                "artifact_path": semantic_artifact.name,
                "artifact_sha256": semantic_artifact_sha256,
                "source_ir_path": source_ir_path.name,
                "source_ir_sha256": source_ir_sha256,
                "target_ir_path": target_ir_path.name,
                "target_ir_sha256": target_ir_sha256,
            },
            "chunk": {
                "artifact_path": chunk_artifact.name,
                "artifact_sha256": chunk_artifact_sha256,
            },
            "behavior": {
                "artifact_path": behavior_artifact.name,
                "artifact_sha256": behavior_artifact_sha256,
            },
            "formal": {
                "artifact_path": formal_artifact.name,
                "artifact_sha256": formal_artifact_sha256,
                "formal_input_path": formal_input_path.name,
                "formal_input_sha256": formal_input_digest,
                "proof_artifact_digests": formal_summary["proof_artifact_digests"],
            },
        }
        layered_summary = compose_layered_report(
            route_key,
            semantic_summary,
            chunk_summary,
            behavior_summary,
            formal_summary,
            layered_refs,
        )
        layered_artifact = output / "layered-equivalence.json"
        layered_artifact_sha256 = write_json(layered_artifact, layered_summary)
        layered_refs["layered"] = {
            "artifact_path": layered_artifact.name,
            "artifact_sha256": layered_artifact_sha256,
        }
    report = {
        "schema_version": "1.0.0",
        "status": (
            "PASSED"
            if layered_summary is not None and layered_summary["status"] == "PASSED"
            else "PASSED_LOCAL_UNCERTIFIED"
            if repository_execution_mode
            and source_runtime_evidence is not None
            and source_runtime_evidence.get("status") == "PASSED"
            and evidence.get("status") == "PASSED"
            else "BLOCKED"
            if layered_summary is None
            else "FAILED"
        ),
        "route": f"{source_language}-to-{target_language}",
        "route_pack_status": "DECLARED" if routed_pair else "NOT_AVAILABLE",
        "repository_execution_mode": repository_execution_mode,
        "scope": "typed-pure-function-v1",
        "source": {
            "path": source.name,
            "sha256": _digest(source_bytes),
            "language": source_language,
            "analyzer": ir.analyzer,
            "analyzer_version": ir.analyzer_version,
        },
        "target": {
            "path": emitted.relative_path,
            "sha256": _digest(emitted_bytes),
            "language": target_language,
        },
        "semantic_ir_sha256": _digest(ir_path.read_bytes()),
        "source_map_coverage": chunk_summary["coverage"] if chunk_summary else 0.0,
        "behavior_case_count": len(cases),
        "behavior_pass_rate": (
            behavior_summary["pass_count"] / behavior_summary["case_count"]
            if behavior_summary and behavior_summary["case_count"]
            else 1.0
            if repository_execution_mode
            and source_runtime_evidence is not None
            and source_runtime_evidence.get("status") == "PASSED"
            and source_runtime_evidence.get("case_count") == len(cases)
            and evidence.get("status") == "PASSED"
            and evidence.get("case_count") == len(cases)
            else 0.0
        ),
        "critical_unknown_semantics": (
            0 if layered_summary is not None and layered_summary["status"] == "PASSED" else 1
        ),
        "limitations": [
            "Only typed, side-effect-free functions using return, if, literals, names, "
            "and supported binary operators are in scope.",
            "Object graphs, exceptions, async, reflection, I/O, framework, database, "
            "and concurrency semantics remain outside this route profile.",
        ],
        "validation": evidence,
        "source_validation": source_runtime_evidence
        if source_runtime_evidence
        else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"},
        "semantic_equivalence": (
            {
                "status": semantic_summary["status"],
                "difference_count": semantic_summary["difference_count"],
                **layered_refs["semantic"],
            }
            if layered_refs and semantic_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "chunk_equivalence": (
            {
                "status": chunk_summary["status"],
                "required_source_chunk_count": chunk_summary["required_source_chunk_count"],
                "mapped_source_chunk_count": chunk_summary["mapped_source_chunk_count"],
                "unexpected_target_chunk_count": chunk_summary["unexpected_target_chunk_count"],
                "coverage": chunk_summary["coverage"],
                **layered_refs["chunk"],
            }
            if layered_refs and chunk_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "behavior_equivalence": (
            {
                "status": behavior_summary["status"],
                "case_count": behavior_summary["case_count"],
                "pass_count": behavior_summary["pass_count"],
                "source_runtime_passed": behavior_summary["source_runtime_passed"],
                "target_runtime_passed": behavior_summary["target_runtime_passed"],
                "oracle_conflict_count": behavior_summary["oracle_conflict_count"],
                **layered_refs["behavior"],
            }
            if layered_refs and behavior_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "formal_composition": (
            {
                "status": formal_summary["status"],
                "property_status": formal_summary["property_status"],
                "formal_input_digest": formal_summary["formal_input_digest"],
                "solver_input_digest": formal_summary["solver_input_digest"],
                "assumption_boundary": formal_summary["assumption_boundary"],
                "unsupported_semantics": formal_summary["unsupported_semantics"],
                **layered_refs["formal"],
            }
            if layered_refs and formal_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "layered_equivalence": (
            {"status": layered_summary["status"], **layered_refs["layered"]}
            if layered_refs and layered_summary
            else {"status": "UNSUPPORTED", "reason": "directed-route-has-no-layered-route-pack"}
        ),
        "certification_status": "EXPERIMENTAL",
        "external_certification_status": "NOT_RUN",
    }
    (output / "route-evidence.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if layered_summary is not None and layered_summary["status"] != "PASSED":
        raise RouteError(
            "LAYERED_EQUIVALENCE_FAILED:"
            f"semantic={semantic_summary['status'] if semantic_summary else 'NOT_RUN'}:"
            f"chunk={chunk_summary['status'] if chunk_summary else 'NOT_RUN'}:"
            f"behavior={behavior_summary['status'] if behavior_summary else 'NOT_RUN'}:"
            f"formal={formal_summary['status'] if formal_summary else 'NOT_RUN'}"
        )
    return report
