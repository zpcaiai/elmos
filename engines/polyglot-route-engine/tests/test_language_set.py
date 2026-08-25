"""Keep engine, repository-route and specialised-proof language sets explicit.

The route matrix has one route record for every ordered pair of the thirteen
supported languages.  That inventory breadth is deliberately separate from
three other things, and this module exists to keep them from collapsing into
each other:

* **Analyzability.**  ``PENDING_ANALYZER_LANGUAGES`` are declared matrix
  members with no analyzer.  They are routed; they cannot be lifted from.
* **Repository surface.**  ``REPOSITORY_SURFACE_LANGUAGES`` is what discovery,
  inventory, placement and build files actually handle.
* **Evidence strength.**  The native/JVM exact-eight profile carries additional
  module, span, behaviour and formal obligations, and no route becomes
  certified merely because it appears in the complete inventory.

``javascript`` is deprecated: absent from the supported set and from every
active route set, but its packs, its engine machinery and its provenance
partition are retained at their recorded values.
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
    DEPRECATED_DIRECTED_PAIRS,
    DEPRECATED_LANGUAGES,
    ENGINE_ONLY_LANGUAGES,
    NODEJS_DIRECTED_PAIRS,
    PENDING_ANALYZER_LANGUAGES,
    REPOSITORY_SURFACE_LANGUAGES,
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
    # A language the engine cannot analyse could not be a route source -- with
    # one explicit exception.  Kotlin, React and Flutter are declared in the
    # matrix ahead of their analyzers, so the old ``ROUTED <= ANALYZABLE``
    # invariant is now stated with that exception named rather than silently
    # weakened: everything routed and not pending must still be analyzable.
    assert set(ROUTED_LANGUAGES) - set(PENDING_ANALYZER_LANGUAGES) <= set(ANALYZABLE_LANGUAGES)
    assert not set(ANALYZABLE_LANGUAGES) & set(PENDING_ANALYZER_LANGUAGES)
    assert set(PENDING_ANALYZER_LANGUAGES) <= set(SUPPORTED_LANGUAGES)
    # Deprecation and support are disjoint states, not overlapping ones.
    assert not set(DEPRECATED_LANGUAGES) & set(SUPPORTED_LANGUAGES)


def test_pending_analyzer_languages_cannot_produce_a_semantic_ir() -> None:
    """A matrix member without an analyzer must fail closed, not lift."""

    for language in PENDING_ANALYZER_LANGUAGES:
        with pytest.raises(RouteError, match=rf"SOURCE_ANALYZER_NOT_IMPLEMENTED:{language}"):
            SemanticIR.from_mapping(
                {
                    "schema_version": "1.0.0",
                    "source_language": language,
                    "source_file": f"unit.{language}",
                    "analyzer": "test",
                    "analyzer_version": "1",
                    "functions": [
                        {
                            "name": "identity",
                            "parameters": [{"name": "value", "type": "integer"}],
                            "return_type": "integer",
                            "body": [{"kind": "return", "expression": {"kind": "name", "value": "value"}}],
                        }
                    ],
                    "diagnostics": [],
                }
            )


def test_deprecated_language_keeps_its_engine_machinery_but_leaves_the_matrix() -> None:
    assert DEPRECATED_LANGUAGES == ("javascript",)
    # Still liftable: the Node.js analyzer, emitter and filed evidence stay.
    assert "javascript" in REPOSITORY_SURFACE_LANGUAGES
    # No longer routed in either direction.
    assert not any("javascript" in pair for pair in ROUTED_PAIRS)
    assert not is_routed_pair("javascript", "java")
    assert not is_routed_pair("java", "javascript")
    # The retired directions are still enumerable under their own name.
    assert len(DEPRECATED_DIRECTED_PAIRS) == 20


def test_the_routed_set_is_not_empty_and_engine_only_is_not_everything() -> None:
    # Guards against a future edit that "fixes" this file by declaring every
    # language engine-only, which would make every check below vacuous.
    assert len(ROUTED_LANGUAGES) >= 6
    assert len(ENGINE_ONLY_LANGUAGES) < len(SUPPORTED_LANGUAGES)


def test_repository_orchestration_surface_is_exactly_the_supported_analyzable_set() -> None:
    source_inventory_languages = set(_EXTENSIONS.values())
    discovery_languages = {"python", *_DECLARATION_PATTERNS}
    target_project_languages = set(_PLACERS)
    target_build_languages = set(_BUILD_FILES)

    # Compared against REPOSITORY_SURFACE_LANGUAGES, not SUPPORTED_LANGUAGES.
    # A pending-analyzer language has no extension, no declaration pattern, no
    # placer and no build file, and adding stubs so this comparison passes
    # would assert support the engine does not have.
    assert source_inventory_languages == set(REPOSITORY_SURFACE_LANGUAGES)
    assert discovery_languages == set(REPOSITORY_SURFACE_LANGUAGES)
    assert target_project_languages == set(REPOSITORY_SURFACE_LANGUAGES)
    assert target_build_languages == set(REPOSITORY_SURFACE_LANGUAGES)
    assert set(REPOSITORY_SURFACE_LANGUAGES) == (
        set(SUPPORTED_LANGUAGES) | set(DEPRECATED_LANGUAGES)
    ) - set(PENDING_ANALYZER_LANGUAGES)

    directed_pairs = {
        (source, target) for source in SUPPORTED_LANGUAGES for target in SUPPORTED_LANGUAGES if source != target
    }
    assert len(directed_pairs) == 156


def test_route_contract_is_complete_thirteen_language_matrix_with_exact_subsets() -> None:
    assert ROUTED_LANGUAGES == COMPLETE_MATRIX_LANGUAGES
    assert len(COMPLETE_MATRIX_DIRECTED_PAIRS) == 156
    assert len(SPECIALIZED_DIRECTED_PAIRS) == 8
    # Pinned to a literal.  If this ever reads 0 the pin was reverted to a
    # comprehension over the language tuple and javascript's removal silently
    # emptied it -- which would flip requires_concrete_source_spans for all 20.
    assert len(NODEJS_DIRECTED_PAIRS) == 20
    assert len(COMPLETE_MATRIX_LANGUAGES) == 13
    assert len(ROUTED_PAIRS) == 156
    assert len(set(ROUTED_PAIRS)) == 156
    assert all(is_routed_pair(source, target) for source, target in ROUTED_PAIRS)

    assert is_routed_pair("php", "java")
    assert is_routed_pair("java", "php")
    assert is_routed_pair("php", "swift")
    assert not is_routed_pair("php", "php")
    assert is_routed_pair("java", "swift")
    assert is_routed_pair("swift", "java")
    assert is_routed_pair("java", "objc")
    assert is_routed_pair("objc", "java")
    assert is_routed_pair("cpp", "python")
    # The three new languages route against everything, in both directions.
    assert is_routed_pair("kotlin", "go")
    assert is_routed_pair("go", "kotlin")
    assert is_routed_pair("react", "swift")
    assert is_routed_pair("swift", "react")
    assert is_routed_pair("flutter", "php")
    assert is_routed_pair("php", "flutter")
    assert is_routed_pair("kotlin", "react")
    assert is_routed_pair("react", "flutter")
    assert is_routed_pair("flutter", "kotlin")
    assert not is_routed_pair("react", "react")
    # Deprecated: declared once, routed never again.
    assert not is_routed_pair("javascript", "java")
    assert not is_routed_pair("java", "javascript")
    assert not is_routed_pair("java", "java")
    assert not is_routed_pair("unknown", "java")


def test_concrete_span_policy_is_profile_and_route_specific() -> None:
    assert not requires_concrete_source_spans("python", "java", "typed-pure-function-v1")
    assert requires_concrete_source_spans("cpp", "java", "typed-pure-function-v1")
    assert requires_concrete_source_spans("java", "cpp", "typed-pure-function-v1")
    assert requires_concrete_source_spans("javascript", "java", "typed-pure-function-v1")
    assert requires_concrete_source_spans("java", "javascript", "typed-pure-function-v1")
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
    deprecated = {f"{source}-to-{target}" for source, target in DEPRECATED_DIRECTED_PAIRS}
    assert len(expected) == 156
    assert len(deprecated) == 20
    assert not expected & deprecated
    missing = sorted(expected - present)
    assert not missing, f"routed pairs with no pack: {missing}"
    # Deprecated packs stay on disk with their evidence.  They are not routed,
    # so they must not be silently accepted as "unexpected" either -- they are
    # allowed exactly because they are declared deprecated, and nothing else is.
    unexpected = sorted(present - expected - deprecated)
    assert not unexpected, f"packs for pairs the engine does not declare: {unexpected}"
    retired_without_pack = sorted(deprecated - present)
    assert not retired_without_pack, (
        f"deprecated packs were deleted instead of retained: {retired_without_pack}"
    )


def test_no_supported_language_remains_engine_only_after_explicit_matrix() -> None:
    assert ENGINE_ONLY_LANGUAGES == ()


@pytest.mark.skipif(not (ROUTES / "inventory.json").is_file(), reason="routes/inventory.json is not present")
def test_inventory_declares_the_complete_156_with_preserved_provenance_sets() -> None:
    """The inventory is generated by ``run_polyglot_routes.py --inventory-only``.

    That regeneration requires the pinned macOS toolchain, so after a matrix
    change this test is the thing that stays red until the inventory is
    rewritten on a machine that has it.  A red assertion here means "the
    inventory is stale", not "the matrix is wrong".
    """

    inventory = json.loads((ROUTES / "inventory.json").read_text(encoding="utf-8"))
    assert set(inventory["languages"]) == set(SUPPORTED_LANGUAGES)
    assert inventory["deprecated_languages"] == list(DEPRECATED_LANGUAGES)
    assert inventory["pending_analyzer_languages"] == list(PENDING_ANALYZER_LANGUAGES)
    assert inventory["route_count"] == 156
    assert len(inventory["routes"]) == 156
    assert inventory["route_policy"] == {
        "cartesian_expansion": "EXPLICIT_THIRTEEN_LANGUAGE_MATRIX",
        "complete_route_set": "thirteen-language-complete-156",
        "completion_route_set": "nine-language-completion-34",
        "deprecated_route_set": "javascript-node26-completion-18",
        "legacy_route_set": "legacy-complete-30",
        "mode": "complete-directed-matrix",
        "nodejs_route_set": "javascript-node26-completion-18",
        "php_route_set": "php-php85-completion-20",
        "preserved_eleven_language_route_set": "eleven-language-complete-110",
        "preserved_nine_language_route_set": "nine-language-complete-72",
        "preserved_ten_language_route_set": "ten-language-complete-90",
        "specialized_route_set": "cpp-objc-swift-java-exact-8",
        "v3_route_set": "kotlin-react-flutter-completion-66",
    }
    route_sets = inventory["route_sets"]

    # Derived here rather than imported so this file is an independent second
    # opinion on the shape of the matrix, not an echo of route_sets.py.
    legacy_languages = {"java", "python", "csharp", "typescript", "go", "rust"}
    eleven_languages = legacy_languages | {"javascript", "cpp", "objc", "swift", "php"}
    ten_languages = eleven_languages - {"php"}
    nine_languages = ten_languages - {"javascript"}
    v3_languages = set(PENDING_ANALYZER_LANGUAGES)

    def complete(languages: set[str]) -> set[str]:
        return {
            f"{source}-to-{target}"
            for source in languages
            for target in languages
            if source != target
        }

    core_keys = complete(legacy_languages)
    nine_language_keys = complete(nine_languages)
    ten_language_keys = complete(ten_languages)
    eleven_language_keys = complete(eleven_languages)
    active_keys = {f"{source}-to-{target}" for source, target in COMPLETE_MATRIX_DIRECTED_PAIRS}
    specialized_keys = {f"{source}-to-{target}" for source, target in SPECIALIZED_DIRECTED_PAIRS}
    php_keys = eleven_language_keys - ten_language_keys
    nodejs_keys = ten_language_keys - nine_language_keys
    completion_keys = nine_language_keys - core_keys - specialized_keys
    v3_keys = {key for key in active_keys if v3_languages & set(key.split("-to-"))}

    assert len(active_keys) == 156
    assert len(v3_keys) == 66
    assert len(eleven_language_keys) == 110
    assert active_keys - eleven_language_keys == v3_keys
    javascript_keys = {key for key in eleven_language_keys if "javascript" in key.split("-to-")}
    assert len(javascript_keys) == 20
    assert eleven_language_keys - active_keys == javascript_keys

    assert set(route_sets) == {
        "legacy-complete-30",
        "cpp-objc-swift-java-exact-8",
        "nine-language-completion-34",
        "nine-language-complete-72",
        "javascript-node26-completion-18",
        "ten-language-complete-90",
        "php-php85-completion-20",
        "eleven-language-complete-110",
        "kotlin-react-flutter-completion-66",
        "thirteen-language-complete-156",
    }
    assert route_sets["legacy-complete-30"]["policy"] == "complete-directed-permutation"
    assert set(route_sets["legacy-complete-30"]["route_keys"]) == core_keys
    assert route_sets["cpp-objc-swift-java-exact-8"]["policy"] == "exact-explicit-set"
    assert set(route_sets["cpp-objc-swift-java-exact-8"]["route_keys"]) == specialized_keys
    assert set(route_sets["nine-language-completion-34"]["route_keys"]) == completion_keys
    assert set(route_sets["nine-language-complete-72"]["route_keys"]) == nine_language_keys
    assert set(route_sets["javascript-node26-completion-18"]["route_keys"]) == nodejs_keys
    assert set(route_sets["ten-language-complete-90"]["route_keys"]) == ten_language_keys
    assert set(route_sets["php-php85-completion-20"]["route_keys"]) == php_keys
    # Frozen at its recorded value.  If this ever equals the active set, the
    # 110 was renamed onto the 156 and 110 routes' evidence lost its address.
    assert set(route_sets["eleven-language-complete-110"]["route_keys"]) == eleven_language_keys
    assert set(route_sets["kotlin-react-flutter-completion-66"]["route_keys"]) == v3_keys
    assert route_sets["kotlin-react-flutter-completion-66"]["analyzer_status"] == "PENDING_ANALYZER"
    assert set(route_sets["thirteen-language-complete-156"]["route_keys"]) == active_keys

    # The active inventory carries no deprecated direction.
    assert {route["route_key"] for route in inventory["routes"]} == active_keys
    assert not any(
        "javascript" in route["route_key"].split("-to-") for route in inventory["routes"]
    )
