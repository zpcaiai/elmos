from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from elmos_polyglot_route.canonical import evaluate
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.engine import (
    _enforce_nodejs_case_domain,
    _enforce_nodejs_semantic_domain,
    _target_call_graph,
    migrate,
)
from elmos_polyglot_route.equivalence import sha256_bytes, verify_formal_input_closure
from elmos_polyglot_route.identifier_hygiene import (
    IdentifierPlan,
    IdentifierUnitNamespace,
    alpha_normalize_target,
    plan_identifiers,
    repository_work_unit_namespace,
    target_function_view,
    target_ir_view,
)
from elmos_polyglot_route.models import (
    REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY,
    Language,
    RouteError,
    SemanticIR,
)
from elmos_polyglot_route.toolchains import exact_toolchain
from elmos_polyglot_route.validation import _apple_sdk, validate


def _cases(path: Path, values: list[int]) -> Path:
    path.write_text(
        json.dumps(
            [
                {
                    "args": [value],
                    "expected": value,
                }
                for value in values
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _repository_namespace(source: Path, work_unit_id: str = "WU-00001") -> IdentifierUnitNamespace:
    return repository_work_unit_namespace(
        repository_snapshot_sha256=sha256_bytes(b"identifier-integration-repository-snapshot"),
        work_unit_id=work_unit_id,
        source_logical_path=source.name,
        source_sha256=sha256_bytes(source.read_bytes()),
    )


def _integer_ir(name: str, *, divide: bool = False) -> SemanticIR:
    parameters = (
        [{"name": "left", "type": "integer"}, {"name": "right", "type": "integer"}]
        if divide
        else [{"name": "value", "type": "integer"}]
    )
    expression = (
        {
            "kind": "binary",
            "operator": "/",
            "left": {"kind": "name", "value": "left"},
            "right": {"kind": "name", "value": "right"},
        }
        if divide
        else {"kind": "name", "value": "value"}
    )
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Source.java",
            "analyzer": "identifier-integration-test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": name,
                    "parameters": parameters,
                    "return_type": "integer",
                    "body": [{"kind": "return", "expression": expression}],
                }
            ],
            "diagnostics": [],
        }
    )


def _integer_parameter_ir(parameter_name: str) -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Source.java",
            "analyzer": "identifier-integration-test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "identity",
                    "parameters": [{"name": parameter_name, "type": "integer"}],
                    "return_type": "integer",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {"kind": "name", "value": parameter_name},
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )


def _typescript_collision_module() -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Source.java",
            "analyzer": "identifier-integration-test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "TypeError",
                    "parameters": [{"name": "value", "type": "number"}],
                    "return_type": "number",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": "+",
                                "left": {"kind": "name", "value": "value"},
                                "right": {"kind": "literal", "value": 1.0},
                            },
                        }
                    ],
                },
                {
                    "name": "identity",
                    "parameters": [{"name": "value", "type": "number"}],
                    "return_type": "number",
                    "body": [{"kind": "return", "expression": {"kind": "name", "value": "value"}}],
                },
                {
                    "name": "positive",
                    "parameters": [{"name": "value", "type": "number"}],
                    "return_type": "boolean",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": ">",
                                "left": {"kind": "name", "value": "value"},
                                "right": {"kind": "literal", "value": 0.0},
                            },
                        }
                    ],
                },
            ],
            "diagnostics": [],
        }
    )


def _explicit_raw_target_view(source: SemanticIR, plan: IdentifierPlan) -> SemanticIR:
    target_view = target_ir_view(source, plan)
    return SemanticIR(
        source_language=plan.target_language,
        source_file="migrated.ts",
        analyzer="explicit-target-relift-fixture",
        analyzer_version="1",
        functions=target_view.functions,
        diagnostics=(),
    )


def _typescript_guard_module() -> SemanticIR:
    def binary(operator: str, left: str, right: str) -> dict[str, object]:
        return {
            "kind": "binary",
            "operator": operator,
            "left": {"kind": "name", "value": left},
            "right": {"kind": "name", "value": right},
        }

    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Source.java",
            "analyzer": "identifier-integration-test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "TypeError",
                    "parameters": [
                        {"name": "left", "type": "integer"},
                        {"name": "right", "type": "integer"},
                    ],
                    "return_type": "integer",
                    "body": [{"kind": "return", "expression": binary("+", "left", "right")}],
                },
                {
                    "name": "ratio",
                    "parameters": [
                        {"name": "left", "type": "integer"},
                        {"name": "right", "type": "integer"},
                    ],
                    "return_type": "number",
                    "body": [{"kind": "return", "expression": binary("/", "left", "right")}],
                },
                {
                    "name": "remainder",
                    "parameters": [
                        {"name": "left", "type": "number"},
                        {"name": "right", "type": "number"},
                    ],
                    "return_type": "number",
                    "body": [{"kind": "return", "expression": binary("%", "left", "right")}],
                },
            ],
            "diagnostics": [],
        }
    )


def test_typescript_target_call_graph_binds_every_guard_domain_to_raw_and_canonical_names() -> None:
    semantic = _typescript_guard_module()
    plan = plan_identifiers(semantic, "typescript")
    raw_target = _explicit_raw_target_view(semantic, plan)
    emitted = emit(semantic, "typescript", identifier_plan=plan)
    canonical_by_raw = {
        raw.name: canonical for raw, canonical in zip(raw_target.functions, semantic.functions, strict=True)
    }
    helper_names = {
        "safe_integer": "_elmosRequireSafeInteger",
        "finite_number": "_elmosRequireFiniteNumber",
        "non_zero": "_elmosRequireNonZero",
    }
    call_graph = _target_call_graph(
        raw_target,
        canonical_by_raw,
        emitted,
        [
            {
                "helper_id": helper_id,
                "name": helper_names[helper_id],
                "qualified_name": helper_names[helper_id],
            }
            for helper_id, _digest in emitted.helper_digests
        ],
    )

    edges = call_graph["edges"]
    rules = {edge["normalization_rule"] for edge in edges}
    assert {
        "typescript.parameter.integer.safe-integer",
        "typescript.return.integer.safe-integer",
        "typescript.return.number.finite",
        "typescript.integer.+.safe-integer",
        "typescript.integer./.safe-integer",
        "typescript.integer./.truncating-non-zero",
        "typescript.number.%.finite-result",
        "typescript.number.%.non-zero:_elmosRequireNonZero",
    } <= rules
    renamed = next(edge for edge in edges if edge["guard_scope"] == "signature-parameter")
    assert renamed["caller"] == raw_target.functions[0].name
    assert renamed["canonical_caller"] == "TypeError"
    for edge in edges:
        if edge.get("guard_scope", "").startswith("arithmetic-"):
            assert "canonical_guard_subject" not in edge


def test_typescript_typeerror_multi_function_plan_normalizes_and_runs(
    tmp_path: Path,
) -> None:
    semantic = _typescript_collision_module()
    plan = plan_identifiers(semantic, "typescript")
    raw_target = _explicit_raw_target_view(semantic, plan)
    normalized = alpha_normalize_target(semantic, raw_target, plan)
    target_function = target_function_view(semantic, semantic.functions[0], plan)

    assert target_function.name != "TypeError"
    assert raw_target.functions[0].name == target_function.name
    assert [function.semantic_mapping() for function in normalized.functions] == [
        function.semantic_mapping() for function in semantic.functions
    ]
    emitted = emit(semantic, "typescript", identifier_plan=plan)
    assert "export function TypeError(" not in emitted.content
    assert "_elmosRequireFiniteNumber((value + 1.0))" in emitted.content

    report = validate(
        emitted,
        "typescript",
        target_function,
        [{"args": [2.5], "expected": 3.5}],
        tmp_path / "typescript",
    )

    assert report["status"] == "PASSED"
    assert report["case_count"] == 1

    tampered = IdentifierPlan.from_mapping(plan.to_mapping())
    tampered_mapping = tampered.to_mapping()
    tampered_mapping["bindings"][0]["ordinal"] = 2
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_RECOMPUTATION_MISMATCH"):
        target_ir_view(semantic, IdentifierPlan.from_mapping(tampered_mapping))


def test_identifier_plan_drives_emission_target_runtime_relift_and_formal_closure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("def main(type: int) -> int:\n    return type\n", encoding="utf-8")
    cases = _cases(tmp_path / "cases.json", [0, 7])
    output = tmp_path / "output"

    report = migrate(source, "python", "go", "main", cases, output)

    assert report["status"] == "PASSED"
    hygiene = report["identifier_hygiene"]
    assert hygiene["status"] == "PASSED"
    assert hygiene["renamed"] is True
    assert hygiene["source_function_name"] == "main"
    assert hygiene["target_function_name"] != "main"
    plan_path = output / hygiene["plan_path"]
    plan = IdentifierPlan.from_mapping(json.loads(plan_path.read_text(encoding="utf-8")))
    assert hygiene["plan_sha256"] == plan.digest
    assert report["target"]["function_name"] == hygiene["target_function_name"]
    emitted = (output / report["target"]["path"]).read_text(encoding="utf-8")
    assert f"func {hygiene['target_function_name']}(" in emitted
    assert "func main(" not in emitted

    raw_target = json.loads((output / hygiene["raw_target_relift"]["path"]).read_text(encoding="utf-8"))
    normalized_target = json.loads((output / hygiene["normalized_target_ir"]["path"]).read_text(encoding="utf-8"))
    assert raw_target["functions"][0]["name"] == hygiene["target_function_name"]
    assert raw_target["functions"][0]["parameters"][0]["name"] != "type"
    assert normalized_target["functions"][0]["name"] == "main"
    assert normalized_target["functions"][0]["parameters"][0]["name"] == "type"

    formal_reference = {
        "path": report["formal_composition"]["formal_input_path"],
        "sha256": report["formal_composition"]["formal_input_sha256"],
    }
    verified = verify_formal_input_closure(output, formal_reference)
    assert verified["identifier_hygiene"]["plan_digest"] == plan.digest

    formal_input_path = output / formal_reference["path"]
    original_formal_input = formal_input_path.read_bytes()
    for binding_path, reason in (
        (("source_normalized_ir",), "FORMAL_INPUT_IR_ARTIFACT_DIGEST_MISMATCH:source_normalized_ir"),
        (
            ("target_relift_normalized_ir",),
            "FORMAL_INPUT_IR_ARTIFACT_DIGEST_MISMATCH:target_relift_normalized_ir",
        ),
        (
            ("identifier_hygiene", "raw_target_relift_ir"),
            "FORMAL_INPUT_RAW_TARGET_IR_ARTIFACT_DIGEST_MISMATCH",
        ),
    ):
        whitespace_payload = json.loads(original_formal_input)
        binding = whitespace_payload
        for key in binding_path:
            binding = binding[key]
        artifact_reference = binding["artifact"]
        artifact_path = output / artifact_reference["path"]
        original_artifact = artifact_path.read_bytes()
        whitespace_artifact = b" \n" + original_artifact
        artifact_path.write_bytes(whitespace_artifact)
        artifact_reference["sha256"] = sha256_bytes(whitespace_artifact)
        rewritten_formal_input = (json.dumps(whitespace_payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        formal_input_path.write_bytes(rewritten_formal_input)
        with pytest.raises(RouteError, match=reason):
            verify_formal_input_closure(
                output,
                {
                    "path": formal_reference["path"],
                    "sha256": sha256_bytes(rewritten_formal_input),
                },
            )
        artifact_path.write_bytes(original_artifact)
        formal_input_path.write_bytes(original_formal_input)

    formal_payload = json.loads(original_formal_input)
    raw_reference = formal_payload["identifier_hygiene"]["raw_target_relift_ir"]["artifact"]
    raw_path = output / raw_reference["path"]
    original_raw = raw_path.read_bytes()
    detached_raw = json.loads(original_raw)
    detached_raw["analyzer_version"] = "detached-rewrite"
    detached_raw_bytes = json.dumps(detached_raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    raw_path.write_bytes(detached_raw_bytes)
    raw_reference["sha256"] = sha256_bytes(detached_raw_bytes)
    rewritten_formal_input = json.dumps(formal_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    formal_input_path.write_bytes(rewritten_formal_input)
    with pytest.raises(RouteError, match="FORMAL_INPUT_RAW_TARGET_IR_ARTIFACT_CONTENT_MISMATCH"):
        verify_formal_input_closure(
            output,
            {
                "path": formal_reference["path"],
                "sha256": sha256_bytes(rewritten_formal_input),
            },
        )
    raw_path.write_bytes(original_raw)
    formal_input_path.write_bytes(original_formal_input)

    for binding_name, rewritten_version, expected_error in (
        (
            "source_normalized_ir",
            "self-consistent-source-rewrite",
            "IDENTIFIER_PLAN_SOURCE_BINDING_MISMATCH",
        ),
        (
            "target_relift_normalized_ir",
            "self-consistent-normalized-target-rewrite",
            "FORMAL_INPUT_ALPHA_NORMALIZATION_MISMATCH",
        ),
    ):
        rewritten_payload = json.loads(original_formal_input)
        rewritten_binding = rewritten_payload[binding_name]
        rewritten_reference = rewritten_binding["artifact"]
        rewritten_path = output / rewritten_reference["path"]
        original_rewritten_artifact = rewritten_path.read_bytes()
        rewritten_semantic_ir = json.loads(original_rewritten_artifact)
        rewritten_semantic_ir["analyzer_version"] = rewritten_version
        rewritten_artifact_bytes = (
            json.dumps(rewritten_semantic_ir, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        rewritten_artifact_sha256 = sha256_bytes(rewritten_artifact_bytes)
        rewritten_path.write_bytes(rewritten_artifact_bytes)
        rewritten_reference["sha256"] = rewritten_artifact_sha256
        rewritten_binding["semantic_ir"] = rewritten_semantic_ir
        rewritten_binding["semantic_ir_sha256"] = rewritten_artifact_sha256
        if binding_name == "target_relift_normalized_ir":
            rewritten_payload["identifier_hygiene"]["normalized_target_ir"]["sha256"] = rewritten_artifact_sha256
        rewritten_formal_input = (json.dumps(rewritten_payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        formal_input_path.write_bytes(rewritten_formal_input)

        with pytest.raises(RouteError, match=expected_error):
            verify_formal_input_closure(
                output,
                {
                    "path": formal_reference["path"],
                    "sha256": sha256_bytes(rewritten_formal_input),
                },
            )

        rewritten_path.write_bytes(original_rewritten_artifact)
        formal_input_path.write_bytes(original_formal_input)

    plan_path.write_bytes(plan_path.read_bytes() + b" ")
    with pytest.raises(RouteError, match="CONTENT_REFERENCE_DIGEST_MISMATCH:identifier-plan.json"):
        verify_formal_input_closure(output, formal_reference)


def test_repository_local_target_rename_prevents_javascript_object_shadowing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("def Object(value: int) -> int:\n    return value\n", encoding="utf-8")
    cases = _cases(tmp_path / "cases.json", [0, 9])
    output = tmp_path / "output"

    report = migrate(
        source,
        "python",
        "javascript",
        "Object",
        cases,
        output,
        repository_execution_mode=True,
        repository_language_lifecycle=REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY,
        identifier_unit_namespace=_repository_namespace(source),
    )

    assert report["status"] == "PASSED_LOCAL_UNCERTIFIED"
    hygiene = report["identifier_hygiene"]
    assert hygiene["renamed"] is True
    assert hygiene["target_function_name"] != "Object"
    assert hygiene["raw_target_relift"]["status"] == "NOT_RUN"
    assert report["validation"]["status"] == "PASSED"
    emitted = (output / "migrated.mjs").read_text(encoding="utf-8")
    assert "export function Object(" not in emitted
    assert "Object.is(value, -0)" in emitted


def test_repository_execution_requires_exact_identifier_unit_namespace_before_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("def identity(value: int) -> int:\n    return value\n", encoding="utf-8")
    cases = _cases(tmp_path / "cases.json", [7])
    output = tmp_path / "output"

    with pytest.raises(RouteError, match="IDENTIFIER_REPOSITORY_UNIT_NAMESPACE_REQUIRED"):
        migrate(
            source,
            "python",
            "cpp",
            "identity",
            cases,
            output,
            repository_execution_mode=True,
        )

    assert not output.exists()


def test_node_route_rejects_unsafe_integer_intermediate_before_output(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text(
        "def cancel(left: int, right: int) -> int:\n    return (left + right) - right\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps([{"args": [1, 2**53 - 1], "expected": 1}]) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"

    with pytest.raises(RouteError, match="NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED"):
        migrate(
            source,
            "python",
            "javascript",
            "cancel",
            cases,
            output,
            repository_execution_mode=True,
            repository_language_lifecycle=REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY,
            identifier_unit_namespace=_repository_namespace(source),
        )

    assert not output.exists()


@pytest.mark.parametrize(
    ("function_name", "source_text", "expected"),
    [
        (
            "positive_after_overflow",
            "def positive_after_overflow(value: float) -> bool:\n    return value * 2.0 > 0.0\n",
            True,
        ),
        (
            "finite_after_overflow",
            "def finite_after_overflow(value: float) -> float:\n"
            "    if value * 2.0 > 0.0:\n"
            "        return 1.0\n"
            "    return 0.0\n",
            1.0,
        ),
    ],
)
def test_typescript_route_rejects_non_finite_number_intermediates_before_output(
    tmp_path: Path,
    function_name: str,
    source_text: str,
    expected: object,
) -> None:
    source = tmp_path / "source.py"
    source.write_text(source_text, encoding="utf-8")
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps([{"args": [float.fromhex("0x1.fffffffffffffp+1023")], "expected": expected}]) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"

    with pytest.raises(
        RouteError,
        match=rf"NODEJS_CASE_NON_FINITE_INTERMEDIATE_UNSUPPORTED:python-to-typescript:{function_name}:0",
    ):
        migrate(
            source,
            "python",
            "typescript",
            function_name,
            cases,
            output,
            repository_execution_mode=True,
            identifier_unit_namespace=_repository_namespace(source),
        )

    assert not output.exists()


def test_typescript_route_accepts_finite_python_number_arithmetic(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text(
        "def shift(value: float) -> float:\n    return value + 1.5\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps([{"args": [2.0], "expected": 3.5}]) + "\n",
        encoding="utf-8",
    )

    report = migrate(
        source,
        "python",
        "typescript",
        "shift",
        cases,
        tmp_path / "output",
        repository_execution_mode=True,
        identifier_unit_namespace=_repository_namespace(source),
    )

    assert report["status"] == "PASSED_LOCAL_UNCERTIFIED"
    assert report["validation"]["status"] == "PASSED"


def test_non_finite_remainder_intermediate_is_tracked_without_host_value_error(
    tmp_path: Path,
) -> None:
    semantic = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Source.java",
            "analyzer": "identifier-integration-test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "recover",
                    "parameters": [{"name": "value", "type": "number"}],
                    "return_type": "boolean",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": ">",
                                "left": {
                                    "kind": "binary",
                                    "operator": "%",
                                    "left": {
                                        "kind": "binary",
                                        "operator": "*",
                                        "left": {"kind": "name", "value": "value"},
                                        "right": {"kind": "literal", "value": 2.0},
                                    },
                                    "right": {"kind": "literal", "value": 3.0},
                                },
                                "right": {"kind": "literal", "value": 0.0},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )
    function = semantic.functions[0]
    case = {
        "args": [float.fromhex("0x1.fffffffffffffp+1023")],
        "expected": False,
    }

    evaluation = evaluate(function, list(case["args"]))
    assert evaluation.value is False
    assert evaluation.within_finite_numbers is False
    with pytest.raises(RouteError, match="NODEJS_CASE_NON_FINITE_INTERMEDIATE_UNSUPPORTED"):
        _enforce_nodejs_case_domain(function, [case], "java", "typescript")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("runtime", ["javascript", "typescript"])
def test_node_negative_zero_semantic_literal_is_rejected_before_output(
    tmp_path: Path,
    runtime: Language,
) -> None:
    semantic = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Source.java",
            "analyzer": "identifier-integration-test",
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

    with pytest.raises(RouteError, match=rf"{runtime.upper()}_NEGATIVE_ZERO_LITERAL_UNSUPPORTED"):
        _enforce_nodejs_semantic_domain(semantic, "java", runtime)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    ("function_name", "source_text", "case"),
    [
        (
            "positive_after_add",
            "def positive_after_add(left: int, right: int) -> bool:\n    return left + right > 0\n",
            {"args": [2**53 - 1, 1], "expected": True},
        ),
        (
            "choose_after_add",
            "def choose_after_add(left: int, right: int, positive: float, negative: float) -> float:\n"
            "    if left + right > 0:\n"
            "        return positive\n"
            "    return negative\n",
            {"args": [2**53 - 1, 1, 1.5, -1.5], "expected": 1.5},
        ),
    ],
)
def test_node_route_rejects_unsafe_integer_intermediates_for_every_return_type(
    tmp_path: Path,
    function_name: str,
    source_text: str,
    case: dict[str, object],
) -> None:
    source = tmp_path / "source.py"
    source.write_text(source_text, encoding="utf-8")
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps([case]) + "\n", encoding="utf-8")
    output = tmp_path / "output"

    with pytest.raises(RouteError, match="NODEJS_CASE_UNSAFE_INTEGER_INTERMEDIATE_UNSUPPORTED"):
        migrate(
            source,
            "python",
            "javascript",
            function_name,
            cases,
            output,
            repository_execution_mode=True,
            repository_language_lifecycle=REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY,
            identifier_unit_namespace=_repository_namespace(source),
        )

    assert not output.exists()


@pytest.mark.parametrize(
    ("function_name", "source_text", "case", "error_type"),
    [
        (
            "divide",
            "public final class Source {\n"
            "  public static long divide(long left, long right) { return left / right; }\n"
            "}\n",
            {"args": [7, 0], "expected": 0},
            "DivideByZero",
        ),
        (
            "remainder",
            "public final class Source {\n"
            "  public static long remainder(long left, long right) { return left % right; }\n"
            "}\n",
            {"args": [7, 0], "expected": 0},
            "DivideByZero",
        ),
        (
            "multiply",
            "public final class Source {\n"
            "  public static long multiply(long left, long right) { return left * right; }\n"
            "}\n",
            {"args": [2**27, 2**36], "expected": 0},
            "IntegerOverflow",
        ),
    ],
)
def test_node_route_wraps_canonical_errors_before_any_output(
    tmp_path: Path,
    function_name: str,
    source_text: str,
    case: dict[str, object],
    error_type: str,
) -> None:
    source = tmp_path / "Source.java"
    source.write_text(source_text, encoding="utf-8")
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps([case]) + "\n", encoding="utf-8")
    output = tmp_path / "output"

    with pytest.raises(
        RouteError,
        match=rf"NODEJS_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN:java-to-javascript:{function_name}:0:{error_type}",
    ):
        migrate(
            source,
            "java",
            "javascript",
            function_name,
            cases,
            output,
            repository_execution_mode=True,
            repository_language_lifecycle=REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY,
            identifier_unit_namespace=_repository_namespace(source),
        )

    assert not output.exists()


@pytest.mark.parametrize(
    ("name", "target_language", "divide", "cases"),
    [
        ("toString", "java", False, [{"args": [7], "expected": 7}]),
        ("abs", "python", True, [{"args": [7, 2], "expected": 3}]),
        ("ToString", "csharp", False, [{"args": [7], "expected": 7}]),
        ("std", "cpp", False, [{"args": [7], "expected": 7}]),
        ("malloc", "cpp", False, [{"args": [7], "expected": 7}]),
        ("size_t", "cpp", False, [{"args": [7], "expected": 7}]),
        ("uint64_t", "cpp", False, [{"args": [7], "expected": 7}]),
        ("errno", "cpp", False, [{"args": [7], "expected": 7}]),
        ("isnan", "cpp", False, [{"args": [7], "expected": 7}]),
        ("BOOL", "objc", False, [{"args": [7], "expected": 7}]),
        ("printf", "objc", False, [{"args": [7], "expected": 7}]),
        ("memcpy", "objc", False, [{"args": [7], "expected": 7}]),
        ("isnan", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSUTF8StringEncoding", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSObject", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSArray", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSDictionary", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSNumber", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSError", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSDate", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSURL", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSSet", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSValue", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSNull", "objc", False, [{"args": [7], "expected": 7}]),
        ("NSLog", "objc", False, [{"args": [7], "expected": 7}]),
        ("malloc", "objc", False, [{"args": [7], "expected": 7}]),
        ("free", "objc", False, [{"args": [7], "expected": 7}]),
        ("pow", "objc", False, [{"args": [7], "expected": 7}]),
        ("print", "swift", False, [{"args": [7], "expected": 7}]),
    ],
)
def test_target_runtime_renames_names_that_shadow_language_runtime_bindings(
    tmp_path: Path,
    name: str,
    target_language: Language,
    divide: bool,
    cases: list[dict[str, object]],
) -> None:
    semantic = _integer_ir(name, divide=divide)
    plan = plan_identifiers(semantic, target_language)
    target_function = target_function_view(semantic, semantic.functions[0], plan)

    assert target_function.name != name
    report = validate(
        emit(semantic, target_language, identifier_plan=plan),
        target_language,
        target_function,
        cases,
        tmp_path / target_language,
    )

    assert report["status"] == "PASSED"
    assert report["case_count"] == len(cases)


@pytest.mark.parametrize("target_language", ["cpp", "objc"])
def test_open_preprocessor_targets_always_alpha_rename_errno_parameters(
    tmp_path: Path,
    target_language: Language,
) -> None:
    semantic = _integer_parameter_ir("errno")
    plan = plan_identifiers(semantic, target_language)
    target_function = target_function_view(semantic, semantic.functions[0], plan)

    assert target_function.name != "identity"
    assert target_function.parameters[0].name != "errno"
    assert "TARGET_OPEN_GLOBAL_SYMBOL_NAMESPACE" in plan.bindings[0].candidates_examined[0].reasons
    assert "TARGET_OPEN_PREPROCESSOR_IDENTIFIER_NAMESPACE" in plan.bindings[1].candidates_examined[0].reasons

    report = validate(
        emit(semantic, target_language, identifier_plan=plan),
        target_language,
        target_function,
        [{"args": [7], "expected": 7}],
        tmp_path / target_language,
    )

    assert report["status"] == "PASSED"
    assert report["case_count"] == 1


@pytest.mark.parametrize("target_language", ["cpp", "objc"])
def test_identical_repository_units_link_with_distinct_planned_symbols(
    tmp_path: Path,
    target_language: Language,
) -> None:
    source = tmp_path / "Source.java"
    source.write_text(
        "public final class Source { public static long same(long value) { return value; } }\n",
        encoding="utf-8",
    )
    semantic = _integer_ir("same")
    left_plan = plan_identifiers(
        semantic,
        target_language,
        unit_namespace=_repository_namespace(source, "WU-00001"),
    )
    right_plan = plan_identifiers(
        semantic,
        target_language,
        unit_namespace=_repository_namespace(source, "WU-00002"),
    )
    left_function = target_function_view(semantic, semantic.functions[0], left_plan)
    right_function = target_function_view(semantic, semantic.functions[0], right_plan)
    assert left_function.name != right_function.name

    suffix = ".cpp" if target_language == "cpp" else ".m"
    left = tmp_path / f"left{suffix}"
    right = tmp_path / f"right{suffix}"
    library = tmp_path / "libunits.dylib"
    left.write_text(
        emit(semantic, target_language, identifier_plan=left_plan).content,
        encoding="utf-8",
    )
    right.write_text(
        emit(semantic, target_language, identifier_plan=right_plan).content,
        encoding="utf-8",
    )
    toolchain = exact_toolchain(target_language)
    command = [toolchain.executable]
    if target_language == "cpp":
        command.extend(
            [
                "-std=c++20",
                "-isysroot",
                _apple_sdk(toolchain.profile),
                "-Wall",
                "-Wextra",
                "-Werror",
                "-dynamiclib",
            ]
        )
    else:
        command.extend(
            [
                "-x",
                "objective-c",
                "-std=c17",
                "-isysroot",
                _apple_sdk(toolchain.profile),
                "-fobjc-arc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-framework",
                "Foundation",
                "-dynamiclib",
            ]
        )
    completed = subprocess.run(
        [*command, str(left), str(right), "-o", str(library)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert library.is_file()
