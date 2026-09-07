from __future__ import annotations

import base64
import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from .emitter import EmittedFile, emit
from .equivalence import (
    L1_PLUS_UNSUPPORTED,
    DirectedRouteKey,
    behavior_equivalence,
    canonical_json_bytes,
    chunk_equivalence,
    compose_layered_report,
    formal_environment_assumptions,
    formal_equivalence,
    formal_solver_identity,
    semantic_equivalence,
    sha256_bytes,
    verify_content_reference,
    verify_formal_input_closure,
    write_json,
)
from .models import ROUTED_LANGUAGES, SUPPORTED_LANGUAGES, Function, Language, RouteError, SemanticIR
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
    function_mapping = function.to_mapping()
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


def migrate(
    source: Path,
    source_language: Language,
    target_language: Language,
    function_name: str,
    cases_path: Path,
    output: Path,
) -> dict[str, Any]:
    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_ROUTE_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    output = safe_output(output)
    ir = analyze(source, source_language, function_name)
    if len(ir.functions) != 1:
        raise RouteError("EXACTLY_ONE_FUNCTION_REQUIRED")
    function = ir.functions[0]
    cases = _load_cases(cases_path, len(function.parameters))
    source_runtime_evidence: dict[str, Any] | None = None
    if source_language in ROUTED_LANGUAGES and target_language in ROUTED_LANGUAGES:
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
    if source_language in ROUTED_LANGUAGES and target_language in ROUTED_LANGUAGES:
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
        "status": ("PASSED" if layered_summary is None or layered_summary["status"] == "PASSED" else "FAILED"),
        "route": f"{source_language}-to-{target_language}",
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
        "source_map_coverage": chunk_summary["coverage"] if chunk_summary else 1.0,
        "behavior_case_count": len(cases),
        "behavior_pass_rate": (
            behavior_summary["pass_count"] / behavior_summary["case_count"]
            if behavior_summary and behavior_summary["case_count"]
            else 1.0
        ),
        "critical_unknown_semantics": (0 if layered_summary is None or layered_summary["status"] == "PASSED" else 1),
        "limitations": [
            "Only typed, side-effect-free functions using return, if, literals, names, "
            "and supported binary operators are in scope.",
            "Object graphs, exceptions, async, reflection, I/O, framework, database, "
            "and concurrency semantics remain outside this route profile.",
        ],
        "validation": evidence,
        "source_validation": source_runtime_evidence
        if source_runtime_evidence
        else {"status": "UNSUPPORTED", "reason": "route-is-not-in-the-six-language-routed-matrix"},
        "semantic_equivalence": (
            {
                "status": semantic_summary["status"],
                "difference_count": semantic_summary["difference_count"],
                **layered_refs["semantic"],
            }
            if layered_refs and semantic_summary
            else {"status": "UNSUPPORTED", "reason": "route-is-not-in-the-six-language-routed-matrix"}
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
            else {"status": "UNSUPPORTED", "reason": "route-is-not-in-the-six-language-routed-matrix"}
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
            else {"status": "UNSUPPORTED", "reason": "route-is-not-in-the-six-language-routed-matrix"}
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
            else {"status": "UNSUPPORTED", "reason": "route-is-not-in-the-six-language-routed-matrix"}
        ),
        "layered_equivalence": (
            {"status": layered_summary["status"], **layered_refs["layered"]}
            if layered_refs and layered_summary
            else {"status": "UNSUPPORTED", "reason": "route-is-not-in-the-six-language-routed-matrix"}
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
