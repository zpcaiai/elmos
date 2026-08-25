from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from typing import Any, cast

import pytest

from elmos_polyglot_route import identifier_hygiene as hygiene
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import (
    MAX_IDENTIFIER_CANDIDATES,
    IdentifierPlan,
    IdentifierUnitNamespace,
    alpha_normalize_target,
    identifier_plan_bytes,
    plan_identifiers,
    policy_for_language,
    repository_work_unit_namespace,
    target_function_view,
    target_ir_view,
    validate_identifier_plan,
)
from elmos_polyglot_route.models import Language, RouteError, SemanticIR


def _function(name: str, parameters: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "name": name,
        "parameters": [{"name": parameter, "type": parameter_type} for parameter, parameter_type in parameters],
        "return_type": parameters[0][1],
        "body": [
            {
                "kind": "return",
                "expression": {"kind": "name", "value": parameters[0][0]},
            }
        ],
    }


def _ir(
    name: str = "calculate",
    parameters: list[tuple[str, str]] | None = None,
    *,
    functions: list[dict[str, Any]] | None = None,
) -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Fixture.java",
            "analyzer": "test-source-analyzer",
            "analyzer_version": "1",
            "functions": functions or [_function(name, parameters or [("value", "integer")])],
            "diagnostics": [],
        }
    )


def _raw_target(source: SemanticIR, target: Language, plan: IdentifierPlan) -> SemanticIR:
    functions = tuple(target_function_view(source, function, plan) for function in source.functions)
    return SemanticIR(
        source_language=target,
        source_file=f"migrated.{target}",
        analyzer="test-target-relifter",
        analyzer_version="1",
        functions=functions,
        diagnostics=(),
    )


def _binding(plan: IdentifierPlan, role: str, ordinal: int = 0) -> Any:
    matches = [item for item in plan.bindings if item.role == role and item.ordinal == ordinal]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize(
    ("target", "function_name", "parameter_name"),
    [
        ("java", "class", "package"),
        ("python", "lambda", "nonlocal"),
        ("csharp", "namespace", "delegate"),
        ("typescript", "interface", "package"),
        ("javascript", "enum", "await"),
        ("go", "defer", "range"),
        ("rust", "match", "self"),
        ("cpp", "template", "concept"),
        ("objc", "typedef", "restrict"),
        ("swift", "protocol", "inout"),
    ],
)
def test_all_ten_target_policies_alpha_rename_reserved_function_and_parameter(
    target: str,
    function_name: str,
    parameter_name: str,
) -> None:
    language = cast(Language, target)
    source = _ir(function_name, [(parameter_name, "integer")])
    plan = plan_identifiers(source, language)

    function_binding = _binding(plan, "function")
    parameter_binding = _binding(plan, "parameter")
    assert function_binding.decision == "ALPHA_RENAMED"
    assert parameter_binding.decision == "ALPHA_RENAMED"
    assert "TARGET_RESERVED" in function_binding.candidates_examined[0].reasons
    assert "TARGET_RESERVED" in parameter_binding.candidates_examined[0].reasons
    assert re.fullmatch(r"elmos_fn_[0-9a-f]{16}", function_binding.target_name)
    assert re.fullmatch(r"elmos_p000_[0-9a-f]{16}", parameter_binding.target_name)
    validate_identifier_plan(source, plan)

    raw = _raw_target(source, language, plan)
    assert raw.functions[0].name == function_binding.target_name
    assert raw.functions[0].parameters[0].name == parameter_binding.target_name
    assert raw.functions[0].body[0].expression is not None
    assert raw.functions[0].body[0].expression.value == parameter_binding.target_name

    normalized = alpha_normalize_target(source, raw, plan)
    assert normalized.functions[0].semantic_mapping() == source.functions[0].semantic_mapping()
    assert normalized.source_language == language
    assert normalized.analyzer == "test-target-relifter"


@pytest.mark.parametrize(
    ("target", "collision"),
    [
        ("java", "elmosCheckedDiv"),
        ("python", "math"),
        ("csharp", "Migrated"),
        ("typescript", "_elmosRequireSafeInteger"),
        ("javascript", "Number"),
        ("go", "main"),
        ("rust", "elmos_non_zero_f64"),
        ("cpp", "elmos_harness_fp64"),
        ("objc", "ElmosCheckedAdd"),
        ("swift", "elmosHarnessFP64"),
    ],
)
def test_all_ten_target_policies_protect_helper_harness_wrapper_and_import_names(
    target: str,
    collision: str,
) -> None:
    source = _ir(collision)
    plan = plan_identifiers(source, cast(Language, target))
    binding = _binding(plan, "function")

    assert binding.decision == "ALPHA_RENAMED"
    assert "POLICY_FORBIDDEN" in binding.candidates_examined[0].reasons
    validate_identifier_plan(source, plan)


def test_javascript_esm_strict_policy_protects_eval_and_arguments_parameters() -> None:
    source = _ir("identity", [("eval", "integer"), ("arguments", "integer")])
    plan = plan_identifiers(source, "javascript")
    parameters = [binding for binding in plan.bindings if binding.role == "parameter"]

    assert [binding.source_name for binding in parameters] == ["eval", "arguments"]
    assert all(binding.decision == "ALPHA_RENAMED" for binding in parameters)
    assert all("POLICY_FORBIDDEN" in binding.candidates_examined[0].reasons for binding in parameters)


@pytest.mark.parametrize("target", ["javascript", "typescript"])
@pytest.mark.parametrize("collision", ["Object", "TypeError"])
def test_node_policy_renames_runtime_names_before_helpers_can_be_shadowed(
    target: Language,
    collision: str,
) -> None:
    plan = plan_identifiers(_ir(collision), target)
    binding = _binding(plan, "function")

    assert binding.decision == "ALPHA_RENAMED"
    assert "POLICY_FORBIDDEN" in binding.candidates_examined[0].reasons


def test_safe_names_are_preserved_without_abi_churn() -> None:
    source = _ir("calculate", [("subtotal", "integer"), ("tax", "integer")])
    for language in cast(tuple[Language, ...], tuple(hygiene._DIALECT)):
        plan = plan_identifiers(source, language)
        if language in {"cpp", "objc"}:
            assert [binding.decision for binding in plan.bindings] == ["ALPHA_RENAMED"] * 3
            assert "TARGET_OPEN_GLOBAL_SYMBOL_NAMESPACE" in plan.bindings[0].candidates_examined[0].reasons
            assert all(
                "TARGET_OPEN_PREPROCESSOR_IDENTIFIER_NAMESPACE" in binding.candidates_examined[0].reasons
                for binding in plan.bindings[1:]
            )
            assert [binding.target_name for binding in plan.bindings] != ["calculate", "subtotal", "tax"]
        elif language in {"java", "csharp", "swift"}:
            assert [binding.decision for binding in plan.bindings] == [
                "ALPHA_RENAMED",
                "PRESERVED",
                "PRESERVED",
            ]
            assert "TARGET_RUNTIME_FUNCTION_NAMESPACE" in plan.bindings[0].candidates_examined[0].reasons
            assert [binding.target_name for binding in plan.bindings] != ["calculate", "subtotal", "tax"]
            assert [binding.target_name for binding in plan.bindings[1:]] == ["subtotal", "tax"]
        else:
            assert [binding.decision for binding in plan.bindings] == ["PRESERVED", "PRESERVED", "PRESERVED"]
            assert [binding.selected_candidate_index for binding in plan.bindings] == [0, 0, 0]
            assert all(len(binding.candidates_examined) == 1 for binding in plan.bindings)
            assert [binding.target_name for binding in plan.bindings] == ["calculate", "subtotal", "tax"]


def test_safe_identifier_target_views_preserve_closed_namespace_outputs_byte_for_byte() -> None:
    source = _ir("calculate", [("subtotal", "integer"), ("tax", "integer")])
    for language in cast(tuple[Language, ...], tuple(hygiene._DIALECT)):
        if language in {"java", "csharp", "cpp", "objc", "swift"}:
            continue
        plan = plan_identifiers(source, language)
        target_ir = replace(
            source,
            functions=tuple(target_function_view(source, function, plan) for function in source.functions),
        )

        before = emit(source, language)
        after = emit(target_ir, language)

        assert after.relative_path == before.relative_path
        assert after.content.encode("utf-8") == before.content.encode("utf-8")


def test_plan_policy_and_candidate_output_is_deterministic_and_round_trips() -> None:
    source = _ir("class", [("package", "integer")])
    first = plan_identifiers(source, "java")
    second = plan_identifiers(source, "java")

    assert first == second
    assert first.digest == second.digest
    assert hashlib.sha256(identifier_plan_bytes(first)).hexdigest() == first.digest.removeprefix("sha256:")
    assert first.policy_sha256 == policy_for_language("java").digest
    policy_digests = {
        policy_for_language(language).digest for language in cast(tuple[Language, ...], tuple(hygiene._DIALECT))
    }
    # Every registered dialect must hash to its own policy: the assertion is
    # distinctness, and pinning it to a literal count only meant the test had
    # to be edited each time a language landed -- which is exactly when a
    # collision would matter most.
    assert len(policy_digests) == len(hygiene._DIALECT)

    decoded = json.loads(json.dumps(first.to_mapping(), ensure_ascii=False))
    restored = IdentifierPlan.from_mapping(decoded)
    assert restored == first
    assert restored.digest == first.digest
    validate_identifier_plan(source, restored)


def test_generated_target_names_ignore_ephemeral_source_paths_but_plans_bind_them() -> None:
    first_source = _ir("class", [("package", "integer")])
    second_source = replace(
        first_source,
        source_file="/private/tmp/another-snapshot/Fixture.java",
        analyzer_version="2",
    )

    first = plan_identifiers(first_source, "java")
    second = plan_identifiers(second_source, "java")

    assert first.source_ir_sha256 != second.source_ir_sha256
    assert first.source_semantic_sha256 == second.source_semantic_sha256
    assert [binding.target_name for binding in first.bindings] == [binding.target_name for binding in second.bindings]
    assert first.digest != second.digest


def test_unicode_and_reserved_implementation_patterns_are_not_emitted_raw() -> None:
    unicode_source = _ir("café")
    unicode_plan = plan_identifiers(unicode_source, "go")
    assert "INVALID_TARGET_IDENTIFIER" in _binding(unicode_plan, "function").candidates_examined[0].reasons

    implementation_reserved = _ir("__implementation")
    cpp_plan = plan_identifiers(implementation_reserved, "cpp")
    reasons = _binding(cpp_plan, "function").candidates_examined[0].reasons
    assert r"TARGET_RESERVED_PATTERN:^__" in reasons


def test_plan_recomputation_rejects_policy_source_and_candidate_tampering() -> None:
    source = _ir("class", [("value", "integer")])
    plan = plan_identifiers(source, "java")

    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_POLICY_MISMATCH"):
        validate_identifier_plan(source, replace(plan, policy_sha256="sha256:" + "0" * 64))

    changed_source = _ir("class", [("other", "integer")])
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_SOURCE_BINDING_MISMATCH"):
        validate_identifier_plan(changed_source, plan)

    first = plan.bindings[0]
    forged_binding = replace(first, target_name="forged")
    forged_plan = replace(plan, bindings=(forged_binding, *plan.bindings[1:]))
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_RECOMPUTATION_MISMATCH"):
        validate_identifier_plan(source, forged_plan)

    forged_candidate = replace(first.candidates_examined[0], reasons=("POLICY_FORBIDDEN",))
    forged_history = replace(first, candidates_examined=(forged_candidate, *first.candidates_examined[1:]))
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_RECOMPUTATION_MISMATCH"):
        validate_identifier_plan(source, replace(plan, bindings=(forged_history, *plan.bindings[1:])))


def test_plan_parser_rejects_unknown_fields_and_inconsistent_binding_count() -> None:
    source = _ir()
    mapping = plan_identifiers(source, "java").to_mapping()
    mapping["forged"] = True
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_KEYS_INVALID:plan"):
        IdentifierPlan.from_mapping(mapping)

    mapping = plan_identifiers(source, "java").to_mapping()
    mapping["binding_count"] = 999
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_INVALID"):
        IdentifierPlan.from_mapping(mapping)


def test_target_function_view_renames_nested_references_by_typed_scope() -> None:
    source = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Fixture.java",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "class",
                    "parameters": [
                        {"name": "package", "type": "integer"},
                        {"name": "switch", "type": "integer"},
                    ],
                    "return_type": "integer",
                    "body": [
                        {
                            "kind": "if",
                            "condition": {
                                "kind": "binary",
                                "operator": ">",
                                "left": {"kind": "name", "value": "package"},
                                "right": {"kind": "literal", "value": 0},
                            },
                            "then": [
                                {
                                    "kind": "return",
                                    "expression": {"kind": "name", "value": "switch"},
                                }
                            ],
                            "else": [
                                {
                                    "kind": "return",
                                    "expression": {"kind": "name", "value": "package"},
                                }
                            ],
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )
    plan = plan_identifiers(source, "java")
    view = target_function_view(source, source.functions[0], plan)
    target_parameters = {
        binding.source_name: binding.target_name for binding in plan.bindings if binding.role == "parameter"
    }

    condition = view.body[0].condition
    assert condition is not None and condition.left is not None
    assert condition.left.value == target_parameters["package"]
    assert view.body[0].then_body[0].expression is not None
    assert view.body[0].then_body[0].expression.value == target_parameters["switch"]
    assert view.body[0].else_body[0].expression is not None
    assert view.body[0].else_body[0].expression.value == target_parameters["package"]


def test_alpha_normalizer_rejects_raw_function_parameter_reference_and_language_tampering() -> None:
    source = _ir("class", [("package", "integer"), ("switch", "integer")])
    plan = plan_identifiers(source, "java")
    raw = _raw_target(source, "java", plan)

    with pytest.raises(RouteError, match="IDENTIFIER_TARGET_LANGUAGE_MISMATCH"):
        alpha_normalize_target(source, replace(raw, source_language="python"), plan)

    with pytest.raises(RouteError, match="IDENTIFIER_RAW_TARGET_FUNCTION_SET_MISMATCH"):
        alpha_normalize_target(
            source,
            replace(raw, functions=(replace(raw.functions[0], name="forged"),)),
            plan,
        )

    swapped_parameters = tuple(reversed(raw.functions[0].parameters))
    with pytest.raises(RouteError, match="IDENTIFIER_RAW_TARGET_PARAMETER_BINDING_MISMATCH"):
        alpha_normalize_target(
            source,
            replace(raw, functions=(replace(raw.functions[0], parameters=swapped_parameters),)),
            plan,
        )

    statement = raw.functions[0].body[0]
    assert statement.expression is not None
    bad_statement = replace(statement, expression=replace(statement.expression, value="forged"))
    with pytest.raises(RouteError, match="IDENTIFIER_TARGET_REFERENCE_UNMAPPED:forged"):
        alpha_normalize_target(
            source,
            replace(raw, functions=(replace(raw.functions[0], body=(bad_statement,)),)),
            plan,
        )


def test_candidate_policy_retries_deterministically_and_exhausts_at_sixteen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _ir("class")
    original = hygiene._generated_candidate_name

    def reject_first_generated_candidate(**arguments: Any) -> str:
        if arguments["candidate_index"] == 1:
            return "Math"
        return original(**arguments)

    monkeypatch.setattr(hygiene, "_generated_candidate_name", reject_first_generated_candidate)
    plan = plan_identifiers(source, "java")
    binding = _binding(plan, "function")
    assert binding.selected_candidate_index == 2
    assert len(binding.candidates_examined) == 3
    assert binding.candidates_examined[1].reasons == ("POLICY_FORBIDDEN",)

    monkeypatch.setattr(hygiene, "_generated_candidate_name", lambda **_arguments: "Math")
    with pytest.raises(RouteError, match="IDENTIFIER_CANDIDATE_EXHAUSTED:function"):
        plan_identifiers(source, "java")
    assert MAX_IDENTIFIER_CANDIDATES == 16


@pytest.mark.parametrize("target", ["java", "csharp", "swift", "typescript", "cpp", "objc"])
def test_multi_function_module_alpha_renames_every_binding_with_exact_scope(
    target: Language,
) -> None:
    source = _ir(
        functions=[
            _function("add", [("left", "integer")]),
            _function("class", [("value", "integer")]),
            _function("subtract", [("right", "integer")]),
        ]
    )
    plan = plan_identifiers(source, target)
    target_view = target_ir_view(source, plan)

    assert len(plan.bindings) == 6
    assert len({binding.binding_id for binding in plan.bindings}) == 6
    assert len({function.name for function in target_view.functions}) == 3
    for ordinal, (source_function, target_function) in enumerate(
        zip(source.functions, target_view.functions, strict=True)
    ):
        function_binding = _binding(plan, "function", ordinal)
        parameter_binding = next(
            binding
            for binding in plan.bindings
            if binding.role == "parameter" and binding.scope_id == function_binding.binding_id
        )
        assert function_binding.source_name == source_function.name
        assert function_binding.target_name == target_function.name
        assert parameter_binding.source_name == source_function.parameters[0].name
        assert parameter_binding.target_name == target_function.parameters[0].name

    if target == "typescript":
        forbidden_binding = _binding(plan, "function", 1)
        assert forbidden_binding.decision == "ALPHA_RENAMED"
        assert "TARGET_RESERVED" in forbidden_binding.candidates_examined[0].reasons

    normalized = alpha_normalize_target(source, _raw_target(source, target, plan), plan)
    assert [function.semantic_mapping() for function in normalized.functions] == [
        function.semantic_mapping() for function in source.functions
    ]

    duplicate = replace(plan, bindings=(plan.bindings[0], plan.bindings[0], *plan.bindings[2:]))
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_RECOMPUTATION_MISMATCH"):
        validate_identifier_plan(source, duplicate)

    wrong_ordinal = replace(plan.bindings[1], ordinal=99)
    forged = replace(plan, bindings=(plan.bindings[0], wrong_ordinal, *plan.bindings[2:]))
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_RECOMPUTATION_MISMATCH"):
        validate_identifier_plan(source, forged)


def test_multi_function_module_with_preserved_names_remains_supported() -> None:
    source = _ir(
        functions=[
            _function("add", [("left", "integer")]),
            _function("multiply", [("value", "integer")]),
            _function("subtract", [("right", "integer")]),
        ]
    )
    plan = plan_identifiers(source, "go")
    assert all(binding.decision == "PRESERVED" for binding in plan.bindings)
    assert target_ir_view(source, plan).functions == source.functions
    normalized = alpha_normalize_target(source, _raw_target(source, "go", plan), plan)
    assert [function.semantic_mapping() for function in normalized.functions] == [
        function.semantic_mapping() for function in source.functions
    ]


def test_duplicate_source_function_identity_is_not_treated_as_overload_support() -> None:
    source = _ir(
        functions=[
            _function("same", [("left", "integer")]),
            _function("same", [("right", "integer")]),
        ]
    )
    with pytest.raises(RouteError, match="IDENTIFIER_SOURCE_FUNCTION_DUPLICATED"):
        plan_identifiers(source, "java")


def _repository_unit_namespace(work_unit_id: str, source_path: str) -> IdentifierUnitNamespace:
    return repository_work_unit_namespace(
        repository_snapshot_sha256="sha256:" + "1" * 64,
        work_unit_id=work_unit_id,
        source_logical_path=source_path,
        source_sha256="sha256:" + "2" * 64,
    )


@pytest.mark.parametrize("target", ["cpp", "objc"])
def test_repository_unit_namespace_separates_identical_external_symbols(target: Language) -> None:
    source = _ir("same")
    left_namespace = _repository_unit_namespace("WU-00001", "left/Fixture.java")
    right_namespace = _repository_unit_namespace("WU-00002", "right/Fixture.java")

    left = plan_identifiers(source, target, unit_namespace=left_namespace)
    repeated_left = plan_identifiers(source, target, unit_namespace=left_namespace)
    right = plan_identifiers(source, target, unit_namespace=right_namespace)

    assert left.to_mapping() == repeated_left.to_mapping()
    assert left.unit_namespace.digest != right.unit_namespace.digest
    assert _binding(left, "function").target_name != _binding(right, "function").target_name
    assert _binding(left, "parameter").target_name != _binding(right, "parameter").target_name
    validate_identifier_plan(source, left, expected_unit_namespace=left_namespace)
    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_UNIT_NAMESPACE_MISMATCH"):
        validate_identifier_plan(source, right, expected_unit_namespace=left_namespace)


def test_repository_unit_namespace_tamper_cannot_reuse_old_bindings() -> None:
    source = _ir("same")
    namespace = _repository_unit_namespace("WU-00001", "left/Fixture.java")
    plan = plan_identifiers(source, "cpp", unit_namespace=namespace)
    mapping = plan.to_mapping()
    namespace_mapping = cast(dict[str, Any], mapping["unit_namespace"])
    namespace_mapping["work_unit_id"] = "WU-00002"
    rewritten_namespace = IdentifierUnitNamespace.from_mapping(namespace_mapping)
    mapping["unit_namespace_sha256"] = rewritten_namespace.digest
    rewritten = IdentifierPlan.from_mapping(mapping)

    with pytest.raises(RouteError, match="IDENTIFIER_PLAN_RECOMPUTATION_MISMATCH"):
        validate_identifier_plan(source, rewritten)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("source_logical_path", "../escape.cpp", "IDENTIFIER_UNIT_NAMESPACE_LOGICAL_PATH_INVALID"),
        ("work_unit_id", "WU-1", "IDENTIFIER_REPOSITORY_UNIT_NAMESPACE_INVALID"),
        ("source_sha256", "sha256:invalid", "IDENTIFIER_PLAN_DIGEST_INVALID"),
    ],
)
def test_repository_unit_namespace_shape_fails_closed(
    field: str,
    value: str,
    reason: str,
) -> None:
    mapping = _repository_unit_namespace("WU-00001", "source/Fixture.java").to_mapping()
    mapping[field] = value
    with pytest.raises(RouteError, match=reason):
        IdentifierUnitNamespace.from_mapping(mapping)
