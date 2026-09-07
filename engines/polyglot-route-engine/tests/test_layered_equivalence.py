from __future__ import annotations

import json
import struct
from dataclasses import replace
from pathlib import Path

import pytest
import z3

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.engine import declared_formal_input_domain, migrate
from elmos_polyglot_route.equivalence import (
    _Encoder,
    behavior_equivalence,
    canonical_json_bytes,
    chunk_equivalence,
    formal_equivalence,
    resolve_json_pointer,
    semantic_chunks,
    semantic_equivalence,
    sha256_bytes,
    verify_formal_input_closure,
    write_json,
)
from elmos_polyglot_route.identifier_hygiene import (
    alpha_normalize_target,
    plan_identifiers,
    target_ir_view,
)
from elmos_polyglot_route.models import REPOSITORY_SURFACE_LANGUAGES, Language, RouteError, SemanticIR
from elmos_polyglot_route.source_analyzer import analyze

ROOT = Path(__file__).resolve().parents[1]


def _integer_ir(operator: str = "+") -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": "source.py",
            "analyzer": "test-source-analyzer",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "calculate",
                    "parameters": [
                        {"name": "left", "type": "integer"},
                        {"name": "right", "type": "integer"},
                    ],
                    "return_type": "integer",
                    "body": [
                        {
                            "kind": "if",
                            "condition": {
                                "kind": "binary",
                                "operator": "<",
                                "left": {"kind": "name", "value": "left"},
                                "right": {"kind": "literal", "value": 0},
                            },
                            "then": [
                                {
                                    "kind": "return",
                                    "expression": {"kind": "literal", "value": 0},
                                }
                            ],
                            "else": [],
                        },
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": operator,
                                "left": {"kind": "name", "value": "left"},
                                "right": {"kind": "name", "value": "right"},
                            },
                        },
                    ],
                }
            ],
            "diagnostics": [],
        }
    )


def _number_identity_ir() -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "cpp",
            "source_file": "source.cpp",
            "analyzer": "test-source-analyzer",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "identityNumber",
                    "parameters": [{"name": "value", "type": "number"}],
                    "return_type": "number",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {"kind": "name", "value": "value"},
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )


def _target_path(root: Path, target: Language, content: str, relative_path: str) -> Path:
    directory = root / target
    directory.mkdir(exist_ok=True)
    path = directory / relative_path
    path.write_text(content, encoding="utf-8")
    return path


# Parametrised over REPOSITORY_SURFACE_LANGUAGES, not ROUTED_LANGUAGES: this
# test relifts real emitter output for every active identity plus retained
# deprecated-JavaScript compatibility. A future repository-pending identity
# must stay outside this tuple until both emitter and relifter exist.
@pytest.mark.parametrize("target", REPOSITORY_SURFACE_LANGUAGES)
def test_each_routed_target_relifts_exact_emitter_compensation(tmp_path: Path, target: Language) -> None:
    source = _integer_ir()
    # Five of the routed targets refuse the source spelling for a function name
    # -- cpp and objc because their global symbol namespace is open, java,
    # csharp and swift because of the runtime function namespace -- so the
    # emitted file does not declare `calculate`. Relifting has to ask for the
    # symbol that is there, and the recovered IR has to come back through the
    # plan's alpha map before it can be compared with the source. This is the
    # exact pairing `engine.migrate` uses; doing it any other way here would
    # either fail to find the function or assert that hygiene never happened.
    plan = plan_identifiers(source, target)
    symbol = target_ir_view(source, plan).functions[0].name
    emitted = emit(source, target, identifier_plan=plan)
    path = _target_path(tmp_path, target, emitted.content, emitted.relative_path)

    raw_target_ir = analyze(path, target, symbol, emitted_target=True)
    target_ir = alpha_normalize_target(source, raw_target_ir, plan)

    assert target_ir.functions[0].semantic_mapping() == source.functions[0].semantic_mapping()
    assert semantic_equivalence(source, target_ir)["status"] == "PASSED"


@pytest.mark.parametrize(
    ("target", "old", "new"),
    [
        ("java", "Math.addExact", "Math.max"),
        ("python", "_elmos_checked_add", "_elmos_lookalike_add"),
        ("csharp", "checked(left + right)", "unchecked(left + right)"),
        ("typescript", "_elmosRequireSafeInteger", "_elmosLookalikeSafeInteger"),
        ("go", "elmosCheckedAdd", "elmosLookalikeAdd"),
        ("rust", "ELMOS_INTEGER_OVERFLOW", "LOOKALIKE_OVERFLOW"),
    ],
)
def test_emitted_target_relift_rejects_lookalike_compensation(
    tmp_path: Path,
    target: Language,
    old: str,
    new: str,
) -> None:
    emitted = emit(_integer_ir(), target)
    assert old in emitted.content
    tampered = emitted.content.replace(old, new)
    path = _target_path(tmp_path, target, tampered, emitted.relative_path)

    with pytest.raises(RouteError):
        analyze(path, target, "calculate", emitted_target=True)


def test_source_mode_does_not_trust_python_emitter_helpers(tmp_path: Path) -> None:
    emitted = emit(_integer_ir(), "python")
    path = _target_path(tmp_path, "python", emitted.content, emitted.relative_path)

    with pytest.raises(RouteError, match="PYTHON_UNSUPPORTED_STATEMENT"):
        analyze(path, "python", "calculate")


def test_chunk_paths_survive_formatting_but_not_semantic_mutation(tmp_path: Path) -> None:
    source = _integer_ir()
    emitted = emit(source, "python")
    unformatted_path = _target_path(tmp_path, "python", emitted.content, emitted.relative_path)
    unformatted = analyze(unformatted_path, "python", "calculate", emitted_target=True)
    formatted = emitted.content.replace("def calculate", "# formatter-only change\n\ndef calculate")
    path = _target_path(tmp_path, "python", formatted, emitted.relative_path)
    target = analyze(path, "python", "calculate", emitted_target=True)
    source_bytes = emitted.content.encode("utf-8")
    target_bytes = formatted.encode("utf-8")

    report = chunk_equivalence(
        unformatted,
        target,
        sha256_bytes(source_bytes),
        sha256_bytes(target_bytes),
        emitted,
        source_artifact_bytes=source_bytes,
        target_artifact_bytes=target_bytes,
        source_logical_file=emitted.relative_path,
        target_logical_file=emitted.relative_path,
    )
    assert report["status"] == "PASSED"
    assert report["coverage"] == 1.0

    mutated = _integer_ir("-")
    assert semantic_equivalence(source, mutated)["status"] == "FAILED"


def test_chunk_paths_are_rfc6901_pointers_to_the_hashed_canonical_subtree() -> None:
    source = _integer_ir()
    canonical_view = {"functions": [source.functions[0].to_mapping()]}
    chunks = semantic_chunks(source, "sha256:" + "a" * 64)

    assert chunks[0]["semantic_path"] == "/functions/0"
    assert resolve_json_pointer(canonical_view, chunks[0]["semantic_path"]) == source.functions[0].to_mapping()
    for chunk in chunks:
        subtree = resolve_json_pointer(canonical_view, chunk["semantic_path"])
        assert chunk["semantic_hash"] == sha256_bytes(canonical_json_bytes(subtree))
        assert chunk["artifact_pointer"] == f"{'sha256:' + 'a' * 64}#{chunk['semantic_path']}"
        assert ":" not in chunk["semantic_path"]


def test_behavior_requires_canonical_expected_source_and_target_to_agree() -> None:
    function = _integer_ir().functions[0]
    cases = [{"args": [2, 3], "expected": 5}]
    source = [{"case_id": 0, "status": "RETURNED", "value": 5}]
    target = [{"case_id": 0, "status": "RETURNED", "value": 6}]

    report = behavior_equivalence(function, cases, source, target)

    assert report["status"] == "FAILED"
    assert report["source_runtime_passed"] is True
    assert report["target_runtime_passed"] is False
    assert report["counterexample_count"] == 1


def test_behavior_normalizes_json_integer_expected_to_exact_fp64_evidence() -> None:
    function = _number_identity_ir().functions[0]
    cases = [{"args": [5.0], "expected": 5}]
    source = [{"case_id": 0, "status": "RETURNED", "value": 5.0}]
    target = [{"case_id": 0, "status": "RETURNED", "value": 5.0}]

    report = behavior_equivalence(function, cases, source, target)

    assert report["status"] == "PASSED"
    assert report["source_runtime_passed"] is True
    assert report["target_runtime_passed"] is True
    result = report["results"][0]
    assert type(result["independent_expected"]) is float
    assert canonical_json_bytes(result["canonical"]["value"]) == canonical_json_bytes(
        result["independent_expected"]
    )


@pytest.mark.parametrize(
    ("return_type", "expected"),
    [
        ("number", True),
        ("number", 2**53 + 1),
        ("integer", 5.0),
        ("boolean", 1),
        ("string", 5),
    ],
)
def test_behavior_rejects_expected_values_that_cannot_preserve_the_declared_type(
    return_type: str,
    expected: object,
) -> None:
    function = replace(_integer_ir().functions[0], return_type=return_type)

    with pytest.raises(RouteError, match="BEHAVIOR_EXPECTED_(TYPE_MISMATCH|NUMBER_NOT_EXACT_BINARY64)"):
        behavior_equivalence(
            function,
            [{"args": [2, 3], "expected": expected}],
            [{"case_id": 0, "status": "RETURNED", "value": expected}],
            [{"case_id": 0, "status": "RETURNED", "value": expected}],
        )


def test_behavior_preserves_negative_zero_bits_in_result_and_counterexample() -> None:
    function = _number_identity_ir().functions[0]
    passing = behavior_equivalence(
        function,
        [{"args": [-0.0], "expected": -0.0}],
        [{"case_id": 0, "status": "RETURNED", "value": -0.0}],
        [{"case_id": 0, "status": "RETURNED", "value": -0.0}],
    )
    report = behavior_equivalence(
        function,
        [{"args": [0.0], "expected": -0.0}],
        [{"case_id": 0, "status": "RETURNED", "value": 0.0}],
        [{"case_id": 0, "status": "RETURNED", "value": 0.0}],
    )

    assert passing["status"] == "PASSED"
    passing_expected = passing["results"][0]["independent_expected"]
    assert struct.pack(">d", passing_expected) == struct.pack(">d", -0.0)
    assert report["status"] == "FAILED"
    result_expected = report["results"][0]["independent_expected"]
    counterexample_expected = report["counterexamples"][0]["expected"]
    assert struct.pack(">d", result_expected) == struct.pack(">d", -0.0)
    assert struct.pack(">d", counterexample_expected) == struct.pack(">d", -0.0)
    assert canonical_json_bytes(result_expected) == canonical_json_bytes(counterexample_expected)


def test_artifact_specific_formal_proof_uses_independent_encodings() -> None:
    source = _integer_ir().functions[0]
    equivalent = _integer_ir().functions[0]

    result, smt2 = formal_equivalence(
        source,
        equivalent,
        "python",
        "java",
        "sha256:" + "3" * 64,
    )

    assert result["status"] == "PROVED_UNDER_ASSUMPTIONS"
    assert result["property_status"] == "PROVED"
    assert "source_left" in smt2
    assert "target_left" in smt2
    assert "same-input:left:left" in result["assumptions"]
    assert "source-compiler-runtime-soundness-not-discharged:python" in result["assumptions"]
    assert "target-language-primitive-compensation-soundness:java" in result["assumptions"]
    assert result["certification_status"] == "NOT_CERTIFIED"


def test_specialized_formal_proof_binds_a_satisfiable_no_error_domain() -> None:
    function = _integer_ir().functions[0]

    result, smt2 = formal_equivalence(
        function,
        function,
        "cpp",
        "java",
        "sha256:" + "9" * 64,
    )

    assert result["status"] == "PROVED_UNDER_ASSUMPTIONS"
    assert result["claim_scope"]["input_domain"] == "canonical-finite-no-error-input-domain"
    assert "canonical-no-error-domain:source" in result["assumptions"]
    assert "canonical-no-error-domain:target" in result["assumptions"]
    assert "; input-domain: canonical-finite-no-error-input-domain" in smt2


def test_specialized_number_proof_excludes_nan_and_infinity() -> None:
    function = _number_identity_ir().functions[0]

    result, smt2 = formal_equivalence(
        function,
        function,
        "cpp",
        "java",
        "sha256:" + "8" * 64,
    )

    assert result["status"] == "PROVED_UNDER_ASSUMPTIONS"
    assert "canonical-finite-input-domain:source:value" in result["assumptions"]
    assert "canonical-finite-input-domain:target:value" in result["assumptions"]
    assert "fp.isNaN" in smt2
    assert "fp.isInfinite" in smt2


def test_formal_proof_returns_replayable_countermodel_for_operator_drift() -> None:
    source = _integer_ir("+").functions[0]
    target = _integer_ir("-").functions[0]

    result, _ = formal_equivalence(
        source,
        target,
        "python",
        "java",
        "sha256:" + "4" * 64,
    )

    assert result["status"] == "FAILED"
    assert result["property_status"] == "COUNTEREXAMPLE"
    assert result["countermodel"]
    assert "source_value" in result["countermodel"]
    assert "target_value" in result["countermodel"]
    assert result["countermodel"]["replay"]["kind"] == "formal-countermodel"


def test_typescript_formal_result_exposes_safe_integer_assumptions() -> None:
    function = _integer_ir().functions[0]

    result, _ = formal_equivalence(
        function,
        function,
        "python",
        "typescript",
        "sha256:" + "5" * 64,
    )

    assert result["status"] == "PROVED_UNDER_ASSUMPTIONS"
    assert any("typescript-safe-integer:parameter:left" in item for item in result["assumptions"])
    assert "async-and-concurrency" in result["unsupported_semantics"]


def test_javascript_formal_result_binds_nodejs_safe_integer_domain() -> None:
    function = _integer_ir().functions[0]

    result, smt2 = formal_equivalence(
        function,
        function,
        "java",
        "javascript",
        "sha256:" + "6" * 64,
        input_domain="nodejs-es2022-esm-safe-integer-finite-v1",
    )

    assert result["status"] == "PROVED_UNDER_ASSUMPTIONS"
    assert result["claim_scope"]["input_domain"] == "nodejs-es2022-esm-safe-integer-finite-v1"
    assert any("javascript-safe-integer:parameter:left" in item for item in result["assumptions"])
    assert not any("typescript-safe-integer" in item for item in result["assumptions"])
    assert "; input-domain: nodejs-es2022-esm-safe-integer-finite-v1" in smt2


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    [
        ("python", "typescript"),
        ("typescript", "python"),
        ("java", "javascript"),
        ("javascript", "go"),
    ],
)
def test_node_runtime_routes_declare_the_same_explicit_formal_domain(
    source_language: Language,
    target_language: Language,
) -> None:
    assert declared_formal_input_domain(source_language, target_language) == "nodejs-es2022-esm-safe-integer-finite-v1"


def test_non_node_runtime_route_keeps_profile_total_formal_domain() -> None:
    assert declared_formal_input_domain("python", "java") == "profile-total-domain"


def test_javascript_formal_domain_excludes_intermediate_safe_integer_escape() -> None:
    ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "javascript",
            "source_file": "recover.mjs",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "recover",
                    "parameters": [{"name": "value", "type": "integer"}],
                    "return_type": "integer",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": "-",
                                "left": {
                                    "kind": "binary",
                                    "operator": "+",
                                    "left": {"kind": "name", "value": "value"},
                                    "right": {"kind": "literal", "value": 1},
                                },
                                "right": {"kind": "literal", "value": 1},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )
    encoder = _Encoder("target", ir.functions[0], "javascript")
    encoder.encode()
    value = encoder.environment["value"]

    at_boundary = z3.Solver()
    at_boundary.add(*encoder.assumptions, value == z3.BitVecVal(2**53 - 1, 64))
    inside_boundary = z3.Solver()
    inside_boundary.add(*encoder.assumptions, value == z3.BitVecVal(2**53 - 2, 64))

    assert any("javascript-safe-integer:expression:+" in item for item in encoder.assumption_labels)
    assert any("javascript-safe-integer:expression:-" in item for item in encoder.assumption_labels)
    assert at_boundary.check() == z3.unsat
    assert inside_boundary.check() == z3.sat


@pytest.mark.parametrize("runtime_language", ["typescript", "javascript"])
def test_node_formal_domain_excludes_intermediate_non_finite_number(
    runtime_language: Language,
) -> None:
    ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "javascript",
            "source_file": "overflow.mjs",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "square",
                    "parameters": [{"name": "value", "type": "number"}],
                    "return_type": "number",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": "*",
                                "left": {"kind": "name", "value": "value"},
                                "right": {"kind": "name", "value": "value"},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )
    encoder = _Encoder("target", ir.functions[0], runtime_language)
    encoded = encoder.encode()
    value = encoder.environment["value"]

    overflow_without_domain = z3.Solver()
    overflow_without_domain.add(
        z3.fpEQ(value, z3.FPVal(1e308, z3.Float64())),
        z3.fpIsInf(encoded.value),
    )
    overflow_inside_domain = z3.Solver()
    overflow_inside_domain.add(
        *encoder.assumptions,
        z3.fpEQ(value, z3.FPVal(1e308, z3.Float64())),
    )
    finite_inside_domain = z3.Solver()
    finite_inside_domain.add(
        *encoder.assumptions,
        z3.fpEQ(value, z3.FPVal(2.0, z3.Float64())),
    )

    assert any(f"{runtime_language}-finite-number:expression:*" in item for item in encoder.assumption_labels)
    assert f"{runtime_language}-finite-number:return" in encoder.assumption_labels
    assert overflow_without_domain.check() == z3.sat
    assert overflow_inside_domain.check() == z3.unsat
    assert finite_inside_domain.check() == z3.sat


@pytest.mark.parametrize("runtime_language", ["typescript", "javascript"])
def test_node_formal_encoder_refuses_negative_zero_semantic_literal(
    runtime_language: Language,
) -> None:
    ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": runtime_language,
            "source_file": "negative-zero",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "negative_zero",
                    "parameters": [],
                    "return_type": "number",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {"kind": "literal", "value": -0.0},
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )

    result, _smt2 = formal_equivalence(
        ir.functions[0],
        ir.functions[0],
        runtime_language,
        runtime_language,
        "sha256:" + "7" * 64,
    )

    assert result["status"] == "UNSUPPORTED"
    assert result["reason"] == f"{runtime_language.upper()}_NEGATIVE_ZERO_LITERAL_UNSUPPORTED"


def test_migrate_persists_and_backlinks_content_addressed_formal_input(tmp_path: Path) -> None:
    output = tmp_path / "route"
    report = migrate(
        ROOT / "fixtures" / "python" / "pricing.py",
        "python",
        "java",
        "calculate",
        ROOT / "fixtures" / "behavior-cases.json",
        output,
    )
    reference = {
        "path": report["formal_composition"]["formal_input_path"],
        "sha256": report["formal_composition"]["formal_input_sha256"],
    }

    formal_input = verify_formal_input_closure(output, reference)
    proof_result = json.loads((output / "formal-proof-result.json").read_text(encoding="utf-8"))
    composition = json.loads((output / "formal-composition.json").read_text(encoding="utf-8"))
    smt2 = (output / "formal-equivalence.smt2").read_text(encoding="utf-8")
    assert proof_result["formal_input"] == reference
    assert proof_result["input_digest"] == reference["sha256"]
    assert proof_result["formal_input_digest"] == reference["sha256"]
    assert proof_result["solver_input_digest"] == sha256_bytes((output / "formal-equivalence.smt2").read_bytes())
    assert composition["formal_input"] == reference
    assert composition["formal_input_digest"] == reference["sha256"]
    assert composition["solver_input_digest"] == proof_result["solver_input_digest"]
    assert f"; formal_input_digest: {reference['sha256']}" in smt2
    assert f"; formal-input-sha256: {reference['sha256']}" in smt2
    assert "; formal-input-path: formal-input.json" in smt2
    assert formal_input["claim_scope"]["relation"] == "canonical-normalized-source-ir-to-target-relift-ir"
    assert formal_input["claim_scope"]["original_source_bytes_theorem"] is False
    assert formal_input["claim_scope"]["source_compiler_runtime_soundness"] == "NOT_RUN"


def test_formal_input_closure_rejects_tamper_and_artifact_drift(tmp_path: Path) -> None:
    output = tmp_path / "route"
    report = migrate(
        ROOT / "fixtures" / "python" / "pricing.py",
        "python",
        "java",
        "calculate",
        ROOT / "fixtures" / "behavior-cases.json",
        output,
    )
    reference = {
        "path": report["formal_composition"]["formal_input_path"],
        "sha256": report["formal_composition"]["formal_input_sha256"],
    }
    formal_path = output / "formal-input.json"
    original_formal_input = formal_path.read_bytes()
    target_path = output / "Migrated.java"
    original_target = target_path.read_bytes()

    target_path.write_bytes(original_target + b"\n")
    with pytest.raises(RouteError, match="CONTENT_REFERENCE_DIGEST_MISMATCH:Migrated.java"):
        verify_formal_input_closure(output, reference)
    target_path.write_bytes(original_target)

    tampered = json.loads(original_formal_input)
    tampered["source_artifact"]["content_base64"] = "AA=="
    tampered_reference = {
        "path": formal_path.name,
        "sha256": write_json(formal_path, tampered),
    }
    with pytest.raises(RouteError, match="FORMAL_INPUT_ARTIFACT_DIGEST_MISMATCH:source"):
        verify_formal_input_closure(output, tampered_reference)

    formal_path.write_bytes(original_formal_input)
    verify_formal_input_closure(output, reference)
