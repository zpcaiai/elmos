from __future__ import annotations

import base64
import hashlib
import json
import math
import platform
from pathlib import Path
from typing import Any

from . import canonical, types
from .emitter import EmittedFile, emit
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
from .native import analyze
from .validation import safe_output, validate, validate_source


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


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
    ]
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


def migrate_module(
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
    manifest = _load_module_manifest(manifest_path)
    symbols = _manifest_symbols(manifest)
    output = safe_output(output)
    output.mkdir(parents=True, exist_ok=True)

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

    emitted = emit(source_ir, target_language)
    target_path = output / emitted.relative_path
    target_path.write_text(emitted.content, encoding="utf-8")
    target_analyses = [
        analyze(target_path, target_language, symbol, emitted_target=True) for symbol in symbols
    ]
    target_ir = _combine_function_irs(target_analyses, symbols, target_language, "target")
    _enforce_specialized_semantic_domain(target_ir, source_language, target_language)
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
        source_artifact_sha256=_digest(source.read_bytes()),
        target_artifact_sha256=_digest(emitted.content.encode("utf-8")),
        corpus_sha256=_digest(manifest_path.read_bytes()),
        emitted=emitted,
        source_artifact_bytes=source.read_bytes(),
        source_logical_file=source.name,
        case_manifest_bytes=manifest_path.read_bytes(),
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
