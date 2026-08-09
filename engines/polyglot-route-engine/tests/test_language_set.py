"""Keep engine, repository-route and specialised-proof language sets explicit.

The repository orchestration surface has one route record for every ordered
pair of the nine supported languages.  That inventory breadth is deliberately
separate from evidence strength: the native/JVM exact-eight profile carries
additional module, span, behaviour and formal obligations, and no route becomes
certified merely because it appears in the complete inventory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_polyglot_route.assembly import _BUILD_FILES, _PLACERS
from elmos_polyglot_route.discovery import _DECLARATION_PATTERNS
from elmos_polyglot_route.engine import (
    _enforce_specialized_case_domain,
    _enforce_specialized_semantic_domain,
)
from elmos_polyglot_route.models import (
    ANALYZABLE_LANGUAGES,
    COMPLETE_MATRIX_DIRECTED_PAIRS,
    COMPLETE_MATRIX_LANGUAGES,
    ENGINE_ONLY_LANGUAGES,
    ROUTED_LANGUAGES,
    ROUTED_PAIRS,
    SPECIALIZED_DIRECTED_PAIRS,
    SUPPORTED_LANGUAGES,
    RouteError,
    SemanticIR,
    is_routed_pair,
    requires_concrete_source_spans,
)
from elmos_polyglot_route.repository import _EXTENSIONS

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parents[1]
ROUTES = REPOSITORY_ROOT / "routes"


def test_the_split_is_a_partition_of_the_supported_set() -> None:
    assert set(ROUTED_LANGUAGES) | set(ENGINE_ONLY_LANGUAGES) == set(SUPPORTED_LANGUAGES)
    assert not set(ROUTED_LANGUAGES) & set(ENGINE_ONLY_LANGUAGES)
    # A language the engine cannot analyse could not be a route source.
    assert set(ROUTED_LANGUAGES) <= set(ANALYZABLE_LANGUAGES)


def test_the_routed_set_is_not_empty_and_engine_only_is_not_everything() -> None:
    # Guards against a future edit that "fixes" this file by declaring every
    # language engine-only, which would make every check below vacuous.
    assert len(ROUTED_LANGUAGES) >= 6
    assert len(ENGINE_ONLY_LANGUAGES) < len(SUPPORTED_LANGUAGES)


def test_repository_orchestration_has_a_complete_nine_language_surface() -> None:
    source_inventory_languages = set(_EXTENSIONS.values())
    discovery_languages = {"python", *_DECLARATION_PATTERNS}
    target_project_languages = set(_PLACERS)
    target_build_languages = set(_BUILD_FILES)

    assert source_inventory_languages == set(SUPPORTED_LANGUAGES)
    assert discovery_languages == set(SUPPORTED_LANGUAGES)
    assert target_project_languages == set(SUPPORTED_LANGUAGES)
    assert target_build_languages == set(SUPPORTED_LANGUAGES)

    directed_pairs = {
        (source, target) for source in SUPPORTED_LANGUAGES for target in SUPPORTED_LANGUAGES if source != target
    }
    assert len(directed_pairs) == 72


def test_route_contract_is_complete_nine_language_matrix_with_specialized_subset() -> None:
    assert ROUTED_LANGUAGES == COMPLETE_MATRIX_LANGUAGES
    assert len(COMPLETE_MATRIX_DIRECTED_PAIRS) == 72
    assert len(SPECIALIZED_DIRECTED_PAIRS) == 8
    assert len(COMPLETE_MATRIX_LANGUAGES) == 9
    assert len(ROUTED_PAIRS) == 72
    assert len(set(ROUTED_PAIRS)) == 72
    assert all(is_routed_pair(source, target) for source, target in ROUTED_PAIRS)

    assert is_routed_pair("java", "swift")
    assert is_routed_pair("swift", "java")
    assert is_routed_pair("java", "objc")
    assert is_routed_pair("objc", "java")
    assert is_routed_pair("cpp", "python")
    assert not is_routed_pair("java", "java")
    assert not is_routed_pair("unknown", "java")


def test_concrete_span_policy_is_profile_and_route_specific() -> None:
    assert not requires_concrete_source_spans("python", "java", "typed-pure-function-v1")
    assert requires_concrete_source_spans("cpp", "java", "typed-pure-function-v1")
    assert requires_concrete_source_spans("java", "cpp", "typed-pure-function-v1")
    assert requires_concrete_source_spans("python", "java", "typed-pure-module-v1")
    assert requires_concrete_source_spans("python", "java", "unknown-profile")


def test_specialized_routes_reject_cross_language_string_semantics() -> None:
    string_ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Identity.java",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "identity",
                    "parameters": [{"name": "value", "type": "string"}],
                    "return_type": "string",
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

    with pytest.raises(
        RouteError,
        match=r"SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED:java-to-cpp:identity",
    ):
        _enforce_specialized_semantic_domain(string_ir, "java", "cpp")

    # The restriction is exact-route policy, not a silent global analyzer
    # regression for the original complete matrix.
    _enforce_specialized_semantic_domain(string_ir, "java", "python")


def test_specialized_native_execution_rejects_overflow_cases_before_runtime() -> None:
    integer_ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "cpp",
            "source_file": "add.cpp",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "add",
                    "parameters": [
                        {"name": "left", "type": "integer"},
                        {"name": "right", "type": "integer"},
                    ],
                    "return_type": "integer",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": "+",
                                "left": {"kind": "name", "value": "left"},
                                "right": {"kind": "name", "value": "right"},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )

    with pytest.raises(
        RouteError,
        match=(
            r"SPECIALIZED_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN:"
            r"cpp-to-java:add:0:IntegerOverflow"
        ),
    ):
        _enforce_specialized_case_domain(
            integer_ir.functions[0],
            [{"args": [2**63 - 1, 1], "expected": -(2**63)}],
            "cpp",
            "java",
        )


def test_specialized_routes_reject_number_arithmetic_but_allow_transport() -> None:
    number_ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "cpp",
            "source_file": "number.cpp",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "addNumber",
                    "parameters": [
                        {"name": "left", "type": "number"},
                        {"name": "right", "type": "number"},
                    ],
                    "return_type": "number",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": "+",
                                "left": {"kind": "name", "value": "left"},
                                "right": {"kind": "name", "value": "right"},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )

    with pytest.raises(
        RouteError,
        match=r"SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED:cpp-to-java:addNumber",
    ):
        _enforce_specialized_semantic_domain(number_ir, "cpp", "java")

    identity_ir = SemanticIR.from_mapping(
        {
            **number_ir.to_mapping(),
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
        }
    )
    _enforce_specialized_semantic_domain(identity_ir, "cpp", "java")


def test_specialized_routes_reject_non_finite_number_cases() -> None:
    number_identity = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "cpp",
            "source_file": "number.cpp",
            "analyzer": "test",
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
    ).functions[0]

    with pytest.raises(
        RouteError,
        match=(
            r"SPECIALIZED_CASE_NON_FINITE_NUMBER_UNSUPPORTED:"
            r"cpp-to-java:identityNumber:0"
        ),
    ):
        _enforce_specialized_case_domain(
            number_identity,
            [{"args": [float("inf")], "expected": float("inf")}],
            "cpp",
            "java",
        )


@pytest.mark.skipif(not ROUTES.is_dir(), reason="routes/ is not present in this checkout")
def test_every_declared_routed_pair_has_a_pack_and_nothing_else_does() -> None:
    present = {path.name for path in ROUTES.iterdir() if path.is_dir()}
    expected = {f"{source}-to-{target}" for source, target in ROUTED_PAIRS}
    assert len(expected) == 72
    missing = sorted(expected - present)
    assert not missing, f"routed pairs with no pack: {missing}"
    unexpected = sorted(present - expected)
    assert not unexpected, f"packs for pairs the engine does not declare as routed: {unexpected}"


def test_no_supported_language_remains_engine_only_after_explicit_matrix() -> None:
    assert ENGINE_ONLY_LANGUAGES == ()


@pytest.mark.skipif(not (ROUTES / "inventory.json").is_file(), reason="routes/inventory.json is not present")
def test_inventory_declares_the_complete_72_with_provenance_sets() -> None:
    inventory = json.loads((ROUTES / "inventory.json").read_text(encoding="utf-8"))
    assert set(inventory["languages"]) == set(SUPPORTED_LANGUAGES)
    assert inventory["route_count"] == 72
    assert len(inventory["routes"]) == 72
    assert inventory["route_policy"] == {
        "cartesian_expansion": "EXPLICIT_NINE_LANGUAGE_MATRIX",
        "complete_route_set": "nine-language-complete-72",
        "completion_route_set": "nine-language-completion-34",
        "legacy_route_set": "legacy-complete-30",
        "mode": "complete-directed-matrix",
        "specialized_route_set": "cpp-objc-swift-java-exact-8",
    }
    route_sets = inventory["route_sets"]
    legacy_languages = {"java", "python", "csharp", "typescript", "go", "rust"}
    core_keys = {
        f"{source}-to-{target}" for source in legacy_languages for target in legacy_languages if source != target
    }
    complete_keys = {f"{source}-to-{target}" for source, target in COMPLETE_MATRIX_DIRECTED_PAIRS}
    specialized_keys = {f"{source}-to-{target}" for source, target in SPECIALIZED_DIRECTED_PAIRS}
    completion_keys = complete_keys - core_keys - specialized_keys
    assert set(route_sets) == {
        "legacy-complete-30",
        "cpp-objc-swift-java-exact-8",
        "nine-language-completion-34",
        "nine-language-complete-72",
    }
    assert route_sets["legacy-complete-30"]["policy"] == "complete-directed-permutation"
    assert set(route_sets["legacy-complete-30"]["route_keys"]) == core_keys
    assert route_sets["cpp-objc-swift-java-exact-8"]["policy"] == "exact-explicit-set"
    assert set(route_sets["cpp-objc-swift-java-exact-8"]["route_keys"]) == specialized_keys
    assert set(route_sets["nine-language-completion-34"]["route_keys"]) == completion_keys
    assert set(route_sets["nine-language-complete-72"]["route_keys"]) == complete_keys
    assert {route["route_key"] for route in inventory["routes"]} == complete_keys
