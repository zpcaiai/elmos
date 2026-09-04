"""PHP target and frontend behaviour that needs no PHP toolchain.

Everything here is a property of the emitter, the identifier policy or the
language tables. The parts that need a real interpreter -- the behaviour replay
and the analyzer round-trip -- live in the toolchain-bound suites, because a
host without the pinned PHP build must not be able to make them pass.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from elmos_polyglot_route import types as canonical_types
from elmos_polyglot_route.emitter import (
    _CHECKED_INTEGER_CALL,
    _FLOAT_NON_ZERO_GUARD,
    _HELPER_ORDER,
    _HELPERS,
    _PHP_HELPERS,
    _TYPE_SPELLING,
    emit,
)
from elmos_polyglot_route.identifier_hygiene import plan_identifiers, policy_for_language
from elmos_polyglot_route.models import (
    COMPLETE_MATRIX_LANGUAGES,
    SUPPORTED_LANGUAGES,
    RouteError,
    SemanticIR,
    is_routed_pair,
)


def _ir(
    *,
    name: str = "subject",
    parameters: list[tuple[str, str]],
    return_type: str,
    body: list[dict],
) -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Subject.java",
            "analyzer": "test",
            "analyzer_version": "0",
            "diagnostics": [],
            "functions": [
                {
                    "name": name,
                    "return_type": return_type,
                    "parameters": [{"name": item, "type": kind} for item, kind in parameters],
                    "body": body,
                }
            ],
        }
    )


def _name(value: str) -> dict:
    return {"kind": "name", "value": value}


def _literal(value: object) -> dict:
    return {"kind": "literal", "value": value}


def _binary(operator: str, left: dict, right: dict) -> dict:
    return {"kind": "binary", "operator": operator, "left": left, "right": right}


def _returns(expression: dict) -> list[dict]:
    return [{"kind": "return", "expression": expression}]


def test_php_is_a_declared_language_in_every_matrix() -> None:
    assert "php" in SUPPORTED_LANGUAGES
    assert "php" in COMPLETE_MATRIX_LANGUAGES
    for other in COMPLETE_MATRIX_LANGUAGES:
        if other == "php":
            continue
        assert is_routed_pair("php", other)
        assert is_routed_pair(other, "php")
    assert not is_routed_pair("php", "php")


def test_php_declares_every_canonical_type_and_every_arithmetic_operator() -> None:
    assert set(_TYPE_SPELLING["php"]) == canonical_types.CANONICAL_TYPES
    assert set(_CHECKED_INTEGER_CALL["php"]) == canonical_types.ARITHMETIC_OPERATORS
    assert "php" in _FLOAT_NON_ZERO_GUARD


def test_every_php_helper_key_is_declared_in_the_global_helper_order() -> None:
    # A key outside _HELPER_ORDER is silently unreachable through
    # _require_helper, which would leave a compensation registered but never
    # emitted.
    assert set(_PHP_HELPERS) <= set(_HELPER_ORDER)
    assert _HELPERS["php"] is _PHP_HELPERS


def test_every_php_helper_call_site_has_a_helper_that_defines_it() -> None:
    for operator, (call, helper_keys) in _CHECKED_INTEGER_CALL["php"].items():
        assert helper_keys, f"{operator} claims a native PHP builtin, which PHP does not have"
        for key in helper_keys:
            assert key in _PHP_HELPERS
        assert any(call in _PHP_HELPERS[key] for key in helper_keys)
    call, key = _FLOAT_NON_ZERO_GUARD["php"]
    assert call in _PHP_HELPERS[key]


def test_emitted_php_opens_with_a_strict_types_declaration() -> None:
    emitted = emit(_ir(parameters=[("a", "integer")], return_type="integer", body=_returns(_name("a"))), "php")
    assert emitted.relative_path == "migrated.php"
    assert emitted.content.startswith("<?php\n\ndeclare(strict_types=1);\n")


def test_variables_carry_the_dollar_sigil_and_function_names_do_not() -> None:
    emitted = emit(
        _ir(
            name="total",
            parameters=[("amount", "integer")],
            return_type="integer",
            body=_returns(_name("amount")),
        ),
        "php",
    )
    assert "function total(int $amount): int {" in emitted.content
    assert "return $amount;" in emitted.content


def test_integer_arithmetic_routes_through_the_checked_helpers() -> None:
    emitted = emit(
        _ir(
            parameters=[("a", "integer"), ("b", "integer")],
            return_type="integer",
            body=_returns(_binary("+", _name("a"), _name("b"))),
        ),
        "php",
    )
    assert "elmos_checked_add($a, $b)" in emitted.content
    assert "php.integer.+.call:elmos_checked_add" in emitted.normalization_rules
    # PHP promotes on overflow instead of wrapping, and the promotion is the
    # only signal, so the helper has to test the result's type.
    assert "!is_int($result)" in emitted.content
    assert "ELMOS_INTEGER_OVERFLOW" in emitted.content


def test_integer_division_uses_intdiv_not_the_slash_operator() -> None:
    emitted = emit(
        _ir(
            parameters=[("a", "integer"), ("b", "integer")],
            return_type="integer",
            body=_returns(_binary("/", _name("a"), _name("b"))),
        ),
        "php",
    )
    assert "elmos_checked_div($a, $b)" in emitted.content
    assert "intdiv($left, $right)" in emitted.content
    # `7 / 2` is 3.5 in PHP and is not even an int.
    assert "return $left / $right" not in emitted.content


def test_float_remainder_uses_fmod_because_php_modulo_is_integer_only() -> None:
    emitted = emit(
        _ir(
            parameters=[("a", "number"), ("b", "number")],
            return_type="number",
            body=_returns(_binary("%", _name("a"), _name("b"))),
        ),
        "php",
    )
    assert "fmod($a, elmos_non_zero_float($b))" in emitted.content
    assert "php.number.%.fmod" in emitted.normalization_rules


def test_string_equality_is_strict_because_php_equality_juggles_types() -> None:
    emitted = emit(
        _ir(
            parameters=[("a", "string"), ("b", "string")],
            return_type="boolean",
            body=_returns(_binary("==", _name("a"), _name("b"))),
        ),
        "php",
    )
    # `'1' == '01'` and `'10' == '1e1'` are both true on PHP 8.
    assert "($a === $b)" in emitted.content
    assert "php.equality.==.strict" in emitted.normalization_rules


def test_mixed_numeric_equality_widens_the_integer_side_before_comparing() -> None:
    emitted = emit(
        _ir(
            parameters=[("a", "integer"), ("b", "number")],
            return_type="boolean",
            body=_returns(_binary("==", _name("a"), _name("b"))),
        ),
        "php",
    )
    # `1 === 1.0` is false: `===` compares types as well as values.
    assert "((float)($a) === $b)" in emitted.content
    assert "php.equality.integer-to-number" in emitted.normalization_rules


def test_string_concatenation_uses_the_dot_operator() -> None:
    emitted = emit(
        _ir(
            parameters=[("a", "string"), ("b", "string")],
            return_type="string",
            body=_returns(_binary("+", _name("a"), _name("b"))),
        ),
        "php",
    )
    assert "($a . $b)" in emitted.content
    assert "php.string.+.concatenation" in emitted.normalization_rules


def test_minimum_integer_literal_is_spelled_php_int_min() -> None:
    emitted = emit(
        _ir(
            parameters=[("a", "integer")],
            return_type="integer",
            body=_returns(_binary("+", _name("a"), _literal(-(2**63)))),
        ),
        "php",
    )
    # A bare -9223372036854775808 is a float in PHP.
    assert "PHP_INT_MIN" in emitted.content
    assert "-9223372036854775808" not in emitted.content


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a$b", "'a$b'"),
        ("it's", "'it\\'s'"),
        ("back\\slash", "'back\\\\slash'"),
        ("héllo", "'héllo'"),
    ],
)
def test_string_literals_are_single_quoted_and_never_interpolate(value: str, expected: str) -> None:
    emitted = emit(
        _ir(parameters=[("a", "string")], return_type="string", body=_returns(_literal(value))),
        "php",
    )
    assert expected in emitted.content


def test_php_identifier_policy_is_registered_and_case_folds_reserved_words() -> None:
    policy = policy_for_language("php")
    assert policy.target_language == "php"
    assert policy.dialect.startswith("php-")
    assert "function" in policy.reserved
    assert policy.reserved_patterns


def test_a_reserved_word_in_any_casing_is_alpha_renamed() -> None:
    for spelling in ("function", "FUNCTION", "Function", "eLsE"):
        plan = plan_identifiers(
            _ir(name=spelling, parameters=[("a", "integer")], return_type="integer", body=_returns(_name("a"))),
            "php",
        )
        assert plan.bindings[0].target_name.lower() != spelling.lower()


def test_function_names_that_differ_only_in_case_cannot_both_survive() -> None:
    # PHP resolves function names case-insensitively; `Total` and `total` are
    # one symbol.
    ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Subject.java",
            "analyzer": "test",
            "analyzer_version": "0",
            "diagnostics": [],
            "functions": [
                {
                    "name": name,
                    "return_type": "integer",
                    "parameters": [{"name": "a", "type": "integer"}],
                    "body": _returns(_name("a")),
                }
                for name in ("total", "Total")
            ],
        }
    )
    plan = plan_identifiers(ir, "php")
    function_names = [binding.target_name for binding in plan.bindings if binding.role == "function"]
    assert len({name.lower() for name in function_names}) == len(function_names)


def test_parameters_that_differ_only_in_case_are_left_alone() -> None:
    # Variables *are* case-sensitive in PHP, so folding them too would rename
    # identifiers the language keeps distinct.
    plan = plan_identifiers(
        _ir(
            parameters=[("value", "integer"), ("Value", "integer")],
            return_type="integer",
            body=_returns(_name("value")),
        ),
        "php",
    )
    parameters = [binding.target_name for binding in plan.bindings if binding.role == "parameter"]
    assert parameters == ["value", "Value"]


def test_an_unsupported_emission_target_fails_closed_rather_than_defaulting() -> None:
    ir = _ir(parameters=[("a", "integer")], return_type="integer", body=_returns(_name("a")))
    with pytest.raises(RouteError, match="IDENTIFIER_POLICY_UNSUPPORTED:ruby"):
        emit(ir, "ruby")  # type: ignore[arg-type]


def test_the_php_analyzer_script_matches_its_recorded_pin() -> None:
    """The pinned digest is what `_run_trusted_php_analyzer` verifies before it
    hands the script to the interpreter. Editing the analyzer without re-pinning
    would make every PHP source analysis fail at run time with
    PHP_ANALYZER_ASSET_UNSAFE, which is safe but is a confusing way to find out.
    """
    import hashlib

    from elmos_polyglot_route.native import (
        _PHP_ANALYZER,
        _PHP_ANALYZER_BYTES,
        _PHP_ANALYZER_SHA256,
    )

    content = _PHP_ANALYZER.read_bytes()
    assert len(content) == _PHP_ANALYZER_BYTES, (
        f"native/php/analyzer.php is {len(content)} bytes, pinned at {_PHP_ANALYZER_BYTES}; "
        "update _PHP_ANALYZER_BYTES and _PHP_ANALYZER_SHA256 in native.py"
    )
    assert hashlib.sha256(content).hexdigest() == _PHP_ANALYZER_SHA256


def test_php_helper_sources_appear_exactly_once_in_an_emitted_file() -> None:
    """`engine._emitted_helper_regions` requires each helper's source text to
    occur byte-for-byte exactly once, and the PHP frontend's decision to skip
    helper bodies on relift rests on that same check.
    """
    emitted = emit(
        _ir(
            parameters=[("a", "integer"), ("b", "integer")],
            return_type="integer",
            body=_returns(_binary("%", _binary("*", _name("a"), _name("b")), _name("b"))),
        ),
        "php",
    )
    used = {helper_id for helper_id, _digest in emitted.helper_digests}
    assert used
    for helper_id in used:
        assert emitted.content.count(_PHP_HELPERS[helper_id]) == 1


def test_helper_class_references_are_fully_qualified() -> None:
    """`assembly._place_php` puts every assembled unit in its own namespace, and
    PHP does not fall back to the global namespace for a *class* the way it does
    for a function or a constant. An unqualified `new ArithmeticError` inside a
    namespace dies with "Class not found" instead of raising the canonical
    error -- and only on the error path, where it is least likely to be noticed.
    """
    for helper_id, source in _PHP_HELPERS.items():
        for spelling in ("ArithmeticError", "DivisionByZeroError"):
            if spelling in source:
                assert f"new \\{spelling}(" in source, (
                    f"{helper_id} names {spelling} without a leading backslash"
                )


def test_placing_two_units_gives_each_its_own_namespace(tmp_path) -> None:
    """Two units that both need `elmos_checked_add` must be loadable together.

    Without a per-unit namespace this is a fatal `Cannot redeclare function` the
    moment Composer autoloads the second unit -- a repository-level assembly
    with two PHP units and any integer arithmetic would never load at all.
    """
    from elmos_polyglot_route.assembly import _place_php

    body = _returns(_binary("+", _name("a"), _name("b")))
    parameters = [("a", "integer"), ("b", "integer")]
    first = _place_php(
        tmp_path,
        "wu00001",
        emit(_ir(name="addOne", parameters=parameters, return_type="integer", body=body), "php").content,
    )
    second = _place_php(
        tmp_path,
        "wu00002",
        emit(_ir(name="addTwo", parameters=parameters, return_type="integer", body=body), "php").content,
    )
    assert first == "src/wu00001/migrated.php"
    assert second == "src/wu00002/migrated.php"
    for relative, expected in ((first, "Wu00001"), (second, "Wu00002")):
        content = (tmp_path / relative).read_text()
        # declare must stay the first statement; the namespace comes next.
        assert content.index("declare(strict_types=1);") < content.index("namespace ")
        assert f"namespace Elmos\\Generated\\{expected};" in content
        assert content.count("namespace ") == 1


def test_php_ast_witness_is_pinned_to_one_version_and_fails_closed_if_unusable() -> None:
    """The optional Zend-AST cross-check reads version-dependent node shapes, so
    the version is pinned rather than "newest supported". An extension that is
    loaded but cannot supply the pinned version is a configuration error, not a
    reason to silently skip the witness.
    """
    from elmos_polyglot_route.native import _PHP_ANALYZER

    source = _PHP_ANALYZER.read_text(encoding="utf-8")
    assert "const PHP_AST_VERSION = " in source
    assert "PHP_ZEND_AST_VERSION_UNSUPPORTED" in source
    # An absent extension is the documented weaker mode, not a failure.
    assert "if (!extension_loaded('ast')) {\n        return null;\n    }" in source


def test_php_invocation_drops_ambient_configuration() -> None:
    """`sanitized_subprocess_env` already drops PHPRC and PHP_INI_SCAN_DIR; `-n`
    closes the remaining path, and the `-d` overrides pin the settings that can
    change an observed value rather than only a diagnostic.
    """
    from elmos_polyglot_route.toolchains import ExactToolchain, php_command

    toolchain = ExactToolchain("php", "x", "/opt/php/8.5.9/bin/php", profile=("php-tokenizer=builtin",))
    command = php_command(toolchain, "analyzer.php")
    assert command[1] == "-n"
    joined = " ".join(command)
    for setting in ("precision=17", "serialize_precision=-1", "opcache.enable_cli=0"):
        assert setting in joined
    assert command[-1] == "analyzer.php"


def test_a_shared_tokenizer_is_reloaded_by_absolute_path_from_inside_the_pin() -> None:
    """`-n` drops the ini, and a build that ships ext/tokenizer as a shared
    module loses `token_get_all` with it -- which is the entire PHP frontend.
    It is re-added by absolute path from inside the pinned install root, never
    by bare name, so the object being dlopen'd is the one the tree digest covers
    rather than whatever sits on the extension search path.
    """
    from elmos_polyglot_route.toolchains import ExactToolchain, php_command

    toolchain = ExactToolchain(
        "php", "x", "/opt/php/8.5.9/bin/php", profile=("php-tokenizer=lib/php/ext/tokenizer.so",)
    )
    command = php_command(toolchain, "analyzer.php")
    assert "extension=/opt/php/8.5.9/lib/php/ext/tokenizer.so" in command


def test_a_missing_tokenizer_binding_fails_closed() -> None:
    from elmos_polyglot_route.models import RouteError
    from elmos_polyglot_route.toolchains import ExactToolchain, php_command

    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_PHP_TOKENIZER_BINDING_MISSING"):
        php_command(ExactToolchain("php", "x", "/opt/php/8.5.9/bin/php"), "analyzer.php")


def test_the_php_tree_identity_records_symlinks_instead_of_refusing_them(tmp_path) -> None:
    """A stock Homebrew PHP ships `bin/phar -> bin/phar.phar` and
    `pecl -> /opt/homebrew/lib/php/pecl`, so the symlink-free tree contract that
    fits Go and Rust refuses every Homebrew PHP that will ever exist. Links are
    recorded as part of the pinned identity instead, and an escaping link is
    kept in a separate map because its content is genuinely not bound.
    """
    from elmos_polyglot_route.toolchains import php_tree_identity

    root = tmp_path / "php" / "8.5.9"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "phar.phar").write_text("#!/usr/bin/env php\n")
    (root / "bin" / "phar").symlink_to("phar.phar")
    outside = tmp_path / "shared"
    outside.mkdir()
    (outside / "pecl").write_text("installer\n")
    (root / "pecl").symlink_to(outside / "pecl")

    identity = php_tree_identity(root, root.parent, "TEST_UNSAFE")
    assert identity["symlinks"] == {"bin/phar": "phar.phar"}
    assert identity["unbound_symlinks"] == {"pecl": str(outside / "pecl")}


def test_php_tree_normalizes_only_install_invocation_receipt_fields(tmp_path) -> None:
    from elmos_polyglot_route.toolchains import php_tree_identity

    root = tmp_path / "php"
    root.mkdir()
    receipt = root / "INSTALL_RECEIPT.json"
    document = {
        "homebrew_version": "6.0.1",
        "time": 1,
        "arch": "arm64",
        "source": {"tap": "homebrew/core", "versions": {"stable": "8.5.9"}},
    }
    receipt.write_text(json.dumps(document), encoding="utf-8")
    baseline = php_tree_identity(root, tmp_path, "TEST_UNSAFE")

    document.update({"homebrew_version": "6.1.0", "time": 2})
    receipt.write_text(json.dumps(document), encoding="utf-8")
    invocation_drift = php_tree_identity(root, tmp_path, "TEST_UNSAFE")
    assert invocation_drift == baseline

    document["arch"] = "x86_64"
    receipt.write_text(json.dumps(document), encoding="utf-8")
    semantic_drift = php_tree_identity(root, tmp_path, "TEST_UNSAFE")
    assert semantic_drift["sha256"] != baseline["sha256"]


def test_an_escaping_symlink_to_a_loadable_object_is_refused(tmp_path) -> None:
    """Recording an unbound name is acceptable for an installer script. It is not
    acceptable for anything the interpreter could dlopen: that has to live inside
    the tree the pin actually binds.
    """
    from elmos_polyglot_route.models import RouteError
    from elmos_polyglot_route.toolchains import php_tree_identity

    root = tmp_path / "php" / "8.5.9"
    (root / "lib").mkdir(parents=True)
    outside = tmp_path / "shared"
    outside.mkdir()
    (outside / "evil.so").write_text("x")
    (root / "lib" / "escaped.so").symlink_to(outside / "evil.so")

    with pytest.raises(RouteError, match="ESCAPING_LOADABLE_OBJECT"):
        php_tree_identity(root, root.parent, "TEST_UNSAFE")


def test_the_php_toolchain_pin_is_filled_in() -> None:
    """`_php()` refuses to run until every digest is pinned, which is correct but
    only tells you at route time. This says it at test time instead.
    """
    from elmos_polyglot_route import toolchains

    for name in (
        "_EXPECTED_PHP_EXECUTABLE_SHA256",
        "_EXPECTED_PHP_TREE_SHA256",
        "_EXPECTED_PHP_RUNTIME_IDENTITY_SHA256",
        "_EXPECTED_PHP_TOKENIZER",
    ):
        assert getattr(toolchains, name), f"{name} is unpinned; run tools/pin_php_toolchain.py"
    assert toolchains._EXPECTED_PHP_EXECUTABLE_BYTES > 0
    assert toolchains._EXPECTED_PHP_TREE_FILE_COUNT > 0


def test_the_identifier_dialect_matches_the_pinned_interpreter() -> None:
    """The dialect string is part of the identifier-policy digest. If it and the
    pinned interpreter disagree, two different dialects share one recorded
    policy digest and the plans they produced become indistinguishable.
    """
    import re

    from elmos_polyglot_route import toolchains
    from elmos_polyglot_route.identifier_hygiene import _PHP_DIALECT

    match = re.search(r"PHP (\d+\.\d+\.\d+)", toolchains._EXPECTED_PHP_VERSION)
    assert match is not None, "the pinned version string is not in the expected shape"
    assert _PHP_DIALECT == f"php-{match.group(1)}-strict-types"


def test_php_module_inventory_is_wired_into_the_enumeration_surface() -> None:
    """PHP was the one routed language with no whole-file enumeration.

    `inventory_module` is what establishes file closure; a language missing
    from it raises `MODULE_INVENTORY_UNSUPPORTED` and every repository node
    with that language as its source is structurally blocked regardless of
    how many of its functions the named-function frontend could lift.
    """
    import inspect

    from elmos_polyglot_route.native import inventory_module

    source = inspect.getsource(inventory_module)
    assert 'elif language == "php":' in source
    assert '_run_trusted_php_analyzer(' in source
    php_branch = source.index('elif language == "php":')
    unsupported = source.index('MODULE_INVENTORY_UNSUPPORTED')
    assert php_branch < unsupported, "php must be handled before the fail-closed default"


def test_the_php_analyzer_exposes_an_inventory_mode_distinct_from_lifting() -> None:
    from elmos_polyglot_route.native import _PHP_ANALYZER

    script = _PHP_ANALYZER.read_text(encoding="utf-8")
    assert "function moduleInventory(" in script
    assert "function moduleInventorySubjects(" in script
    assert "$functionName === '--inventory'" in script
    # Enumeration reports; it must not borrow lift()'s rejection path.
    inventory_at = script.index("$functionName === '--inventory'")
    lift_at = script.index("$function = lift($cursor, $functionName")
    assert inventory_at < lift_at


def test_an_empty_php_subject_signature_survives_the_module_inventory_contract() -> None:
    """`[]` in PHP encodes as a JSON array, and the contract requires an object.

    This is the exact shape that made the first working enumeration fail
    validation, so it is locked here rather than left to the toolchain tests
    that only run on a machine with the pinned interpreter.
    """
    import json

    from elmos_polyglot_route.native import _PHP_ANALYZER

    script = _PHP_ANALYZER.read_text(encoding="utf-8")
    assert "$signature === [] ? new stdClass() : $signature" in script
    assert json.loads("{}") == {}


def test_the_php_module_inventory_contract_accepts_a_well_formed_enumeration(
    tmp_path,
) -> None:
    from elmos_polyglot_route.native import _validated_module_inventory

    source = tmp_path / "sample.php"
    body = b"<?php\n\ndeclare(strict_types=1);\n\nfunction clamp(int $v): int\n{\n    return $v;\n}\n"
    source.write_bytes(body)
    value = {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-inventory",
        "profile": "typed-pure-module-v1",
        "source_language": "php",
        "source_file": "sample.php",
        "analyzer": "php/ext-tokenizer Zend token stream",
        "analyzer_version": "php-8.5.9;tokenizer=8.5.9",
        "enumeration_status": "PASSED",
        "subjects": [
            {
                "name": "<strict-types>",
                "qualified_name": "<strict-types>",
                "declaration_kind": "php-profile-preamble",
                "analyzable": False,
                "source_span": {"file": "sample.php", "start_byte": 7, "end_byte": 31},
                "signature": {"directive": "strict_types", "value": 1},
            },
            {
                "name": "clamp",
                "qualified_name": "clamp",
                "declaration_kind": "function",
                "analyzable": True,
                "source_span": {"file": "sample.php", "start_byte": 33, "end_byte": len(body)},
                "signature": {
                    "source_parameters": "(int $v)",
                    "source_return_type": "int",
                    "by_reference": False,
                },
            },
        ],
        "diagnostics": [],
    }

    validated = _validated_module_inventory(value, "php", source, body)

    assert validated["source_artifact_bytes"] == len(body)
    assert validated["source_artifact_sha256"].startswith("sha256:")
    assert validated["directives"] == [
        {
            "order": 0,
            "kind": "declare",
            "value": "strict_types=1",
            "source_span": {"file": "sample.php", "start_byte": 7, "end_byte": 31},
            "sha256": "sha256:" + hashlib.sha256(b"declare(strict_types=1);").hexdigest(),
        }
    ]
    assert [subject["occurrence"] for subject in validated["subjects"]] == [1]
    assert [subject["analyzable"] for subject in validated["subjects"]] == [True]


def test_a_php_subject_signature_that_is_a_list_is_rejected() -> None:
    """The failure mode this whole shape exists to catch, asserted directly."""
    import tempfile
    from pathlib import Path

    from elmos_polyglot_route.models import RouteError
    from elmos_polyglot_route.native import _validated_module_inventory

    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "sample.php"
        body = b"<?php\n"
        source.write_bytes(body)
        value = {
            "schema_version": "1.0.0",
            "kind": "elmos.typed-pure-module-inventory",
            "profile": "typed-pure-module-v1",
            "source_language": "php",
            "source_file": "sample.php",
            "analyzer": "php/ext-tokenizer Zend token stream",
            "analyzer_version": "php-8.5.9;tokenizer=8.5.9",
            "enumeration_status": "PASSED",
            "subjects": [
                {
                    "name": "x",
                    "qualified_name": "x",
                    "declaration_kind": "constant",
                    "analyzable": False,
                    "source_span": None,
                    "signature": [],
                }
            ],
            "diagnostics": [],
        }
        with pytest.raises(RouteError, match="MODULE_INVENTORY_SUBJECT_INVALID"):
            _validated_module_inventory(value, "php", source, body)


def test_the_php_lifter_no_longer_decides_file_closure() -> None:
    """Enumeration and lifting had contradictory answers for the same file.

    `lift()` failed on any top-level token that was not `function`, so a file
    with a `const` above the target was unliftable -- while `--inventory` was
    simultaneously reporting that target as analyzable. File closure is
    enumeration's question; this asserts the lifter stopped answering it.
    """
    from elmos_polyglot_route.native import _PHP_ANALYZER

    script = _PHP_ANALYZER.read_text(encoding="utf-8")

    assert "function skipTopLevelDeclaration(" in script
    assert "skipTopLevelDeclaration($cursor);" in script
    # The body parser is what keeps skipping safe, so it must still be strict.
    assert "PHP_CALL_OUTSIDE_CERTIFIED_SUBSET" in script
