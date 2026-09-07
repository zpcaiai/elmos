from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import _JAVASCRIPT_HELPERS, emit
from elmos_polyglot_route.models import RouteError, SemanticIR
from elmos_polyglot_route.native import analyze, inventory_module
from elmos_polyglot_route.toolchains import exact_toolchain
from elmos_polyglot_route.validation import validate, validate_source

ENGINE_ROOT = Path(__file__).resolve().parents[1]
JAVASCRIPT_FIXTURE = ENGINE_ROOT / "fixtures" / "javascript" / "pricing.mjs"


def _javascript_arithmetic_ir(
    value_type: str,
    operator: str,
    *,
    nested: bool = False,
    conditional: bool = False,
) -> SemanticIR:
    inner: dict[str, object] = {
        "kind": "binary",
        "operator": operator,
        "left": {"kind": "name", "value": "left"},
        "right": {"kind": "name", "value": "right"},
    }
    expression: dict[str, object] = (
        {
            "kind": "binary",
            "operator": "*",
            "left": inner,
            "right": {"kind": "name", "value": "right"},
        }
        if nested
        else inner
    )
    if conditional:
        body: list[dict[str, object]] = [
            {
                "kind": "if",
                "condition": {
                    "kind": "binary",
                    "operator": ">",
                    "left": inner,
                    "right": {"kind": "literal", "value": 0},
                },
                "then": [
                    {
                        "kind": "return",
                        "expression": {"kind": "name", "value": "left"},
                    }
                ],
                "else": [
                    {
                        "kind": "return",
                        "expression": {"kind": "name", "value": "right"},
                    }
                ],
            }
        ]
    else:
        body = [{"kind": "return", "expression": expression}]
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": "arithmetic.py",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "calculate",
                    "parameters": [
                        {"name": "left", "type": value_type},
                        {"name": "right", "type": value_type},
                    ],
                    "return_type": value_type,
                    "body": body,
                }
            ],
            "diagnostics": [],
        }
    )


def test_javascript_integer_parameter_normalizes_negative_zero_before_use(
    tmp_path: Path,
) -> None:
    semantic = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": "identity.py",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "identity",
                    "parameters": [{"name": "value", "type": "integer"}],
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
    emitted = emit(semantic, "javascript")
    assert "value = _elmosRequireSafeInteger(value);" in emitted.content
    assert "javascript.parameter.integer.negative-zero-normalized" in emitted.normalization_rules
    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    relifted = analyze(target, "javascript", "identity", emitted_target=True)
    assert relifted.functions[0].semantic_mapping() == semantic.functions[0].semantic_mapping()

    probe = tmp_path / "probe.mjs"
    probe.write_text(
        'import { identity } from "./migrated.mjs";\n'
        "const bytes = new ArrayBuffer(8);\n"
        "const view = new DataView(bytes);\n"
        "view.setFloat64(0, identity(-0), false);\n"
        'console.log(view.getBigUint64(0, false).toString(16).padStart(16, "0"));\n',
        encoding="utf-8",
    )
    private_home = tmp_path / "home"
    private_tmp = tmp_path / "tmp"
    private_home.mkdir(mode=0o700)
    private_tmp.mkdir(mode=0o700)
    completed = subprocess.run(
        [exact_toolchain("javascript").executable, str(probe)],
        cwd=tmp_path,
        env={
            "HOME": str(private_home),
            "TMPDIR": str(private_tmp),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "0000000000000000"

    target.write_text(
        emitted.content.replace(
            "value = _elmosRequireSafeInteger(value);",
            "_elmosRequireSafeInteger(value);",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        RouteError,
        match="JAVASCRIPT_EMITTED_PARAMETER_GUARD_INVALID:value",
    ):
        analyze(target, "javascript", "identity", emitted_target=True)


@pytest.mark.parametrize(
    ("semantic", "guarded", "unguarded"),
    [
        (
            _javascript_arithmetic_ir("integer", "+"),
            "_elmosRequireSafeInteger(left + right)",
            "(left + right)",
        ),
        (
            _javascript_arithmetic_ir("number", "+"),
            "_elmosRequireFiniteNumber((left + right))",
            "(left + right)",
        ),
        (
            _javascript_arithmetic_ir("integer", "+", nested=True),
            "_elmosRequireSafeInteger(left + right)",
            "(left + right)",
        ),
        (
            _javascript_arithmetic_ir("integer", "+", conditional=True),
            "_elmosRequireSafeInteger(left + right)",
            "(left + right)",
        ),
    ],
    ids=("integer-return", "number-return", "nested", "if-condition"),
)
def test_javascript_emitted_target_requires_per_binary_arithmetic_guards(
    tmp_path: Path,
    semantic: SemanticIR,
    guarded: str,
    unguarded: str,
) -> None:
    emitted = emit(semantic, "javascript")
    assert guarded in emitted.content
    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content.replace(guarded, unguarded, 1), encoding="utf-8")

    with pytest.raises(RouteError, match="JAVASCRIPT_EMITTED_ARITHMETIC_GUARD_MISSING"):
        analyze(target, "javascript", "calculate", emitted_target=True)


@pytest.mark.parametrize("value_type", ["integer", "number"])
@pytest.mark.parametrize("operator", ["/", "%"])
def test_javascript_emitted_target_requires_exact_nonzero_guard_per_division_node(
    tmp_path: Path,
    value_type: str,
    operator: str,
) -> None:
    semantic = _javascript_arithmetic_ir(value_type, operator)
    # Keep one independent, canonical use of the helper in the module.  This
    # makes the negative exercise the selected function's exact per-node AST
    # contract instead of being rejected earlier by the module-wide
    # used-helper/declaration closure after its only use disappears.
    emitted = emit(
        replace(
            semantic,
            functions=(
                semantic.functions[0],
                replace(semantic.functions[0], name="keepNonZeroGuard"),
            ),
        ),
        "javascript",
    )
    guarded = "_elmosRequireNonZero(right)"
    assert guarded in emitted.content
    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content.replace(guarded, "right", 1), encoding="utf-8")

    with pytest.raises(
        RouteError,
        match=("JAVASCRIPT_EMITTED_NON_ZERO_GUARD_MISSING:" + ("division" if operator == "/" else "remainder")),
    ):
        analyze(target, "javascript", "calculate", emitted_target=True)


def test_javascript_uses_independent_exact_node26_profile() -> None:
    toolchain = exact_toolchain("javascript")

    assert toolchain.language == "javascript"
    assert toolchain.version == "Node.js 26.0.0 / ES2022 / ESM"
    assert toolchain.auxiliary is None
    assert toolchain.executable.endswith("/node/26.0.0/bin/node")
    assert "compiler-runtime-semantic-soundness=NOT_RUN" in toolchain.profile


def test_javascript_analyzer_inventory_emit_relift_and_runtime(tmp_path: Path) -> None:
    semantic = analyze(JAVASCRIPT_FIXTURE, "javascript", "calculate")
    inventory = inventory_module(JAVASCRIPT_FIXTURE, "javascript")
    cases = [
        {"args": [10, 2], "expected": 12},
        {"args": [-1, 2], "expected": 0},
    ]

    assert semantic.source_language == "javascript"
    assert [item["name"] for item in inventory["subjects"]] == ["calculate"]
    assert inventory["subjects"][0]["analyzable"] is True
    assert inventory["enumeration_status"] == "PASSED"

    emitted = emit(semantic, "javascript")
    assert emitted.relative_path == "migrated.mjs"
    assert "@param {integer} subtotal" in emitted.content
    assert "_elmosRequireSafeInteger" in emitted.content
    assert "Object.is(value, -0) ? 0 : value" in emitted.content
    assert "export function calculate" in emitted.content

    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    relifted = analyze(target, "javascript", "calculate", emitted_target=True)
    assert [item.semantic_mapping() for item in relifted.functions] == [
        item.semantic_mapping() for item in semantic.functions
    ]

    source_report = validate_source(
        JAVASCRIPT_FIXTURE,
        "javascript",
        semantic.functions[0],
        cases,
        tmp_path / "source-runtime",
    )
    target_report = validate(
        emitted,
        "javascript",
        semantic.functions[0],
        cases,
        tmp_path / "target-runtime",
    )
    assert source_report["status"] == "PASSED"
    assert target_report["status"] == "PASSED"
    assert source_report["observations"] == target_report["observations"]


def test_javascript_inventory_only_trusts_exact_canonical_helper_declarations(
    tmp_path: Path,
) -> None:
    target = tmp_path / "helpers.mjs"
    target.write_text("\n\n".join(_JAVASCRIPT_HELPERS.values()) + "\n", encoding="utf-8")

    inventory = inventory_module(target, "javascript")
    subjects = {subject["name"]: subject for subject in inventory["subjects"]}
    expected = {
        "_elmosRequireSafeInteger": ("integer", "integer"),
        "_elmosRequireFiniteNumber": ("number", "number"),
        "_elmosRequireBoolean": ("boolean", "boolean"),
        "_elmosRequireString": ("string", "string"),
        "_elmosRequireNonZero": ("number", "number"),
        "_elmosRequireRecord": ("record", "record"),
    }

    assert set(subjects) == set(expected)
    for name, (parameter_type, return_type) in expected.items():
        subject = subjects[name]
        assert subject["declaration_kind"] == "FunctionDeclaration"
        assert subject["analyzable"] is True
        assert subject["occurrence"] == 1
        assert subject["signature"] == {
            "parameters": [{"name": "value", "source_type": parameter_type}],
            "source_return_type": return_type,
            "visibility": "internal",
            "storage": "file-scope",
        }


def test_javascript_ast_helper_binding_ignores_helper_like_comments_and_strings(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mjs"
    source.write_text(
        '/** @returns {string} */\nexport function helperText() { return "_elmosRequireSafeInteger("; }\n',
        encoding="utf-8",
    )
    semantic = analyze(source, "javascript", "helperText")
    emitted = emit(semantic, "javascript")
    target = tmp_path / emitted.relative_path
    target.write_text(
        "/* helper-like text: _elmosRequireSafeInteger( */\n" + emitted.content,
        encoding="utf-8",
    )

    relifted = analyze(target, "javascript", "helperText", emitted_target=True)

    assert relifted.functions[0].body[0].expression is not None
    assert relifted.functions[0].body[0].expression.value == "_elmosRequireSafeInteger("


def test_javascript_plain_js_without_a_bound_esm_descriptor_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "ambiguous.js"
    source.write_text(JAVASCRIPT_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(RouteError, match="^JAVASCRIPT_ESM_DESCRIPTOR_REQUIRED$"):
        analyze(source, "javascript", "calculate")


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (
            'import "node:fs";\n/** @param {integer} value @returns {integer} */\n'
            "export function identity(value) { return value; }\n",
            "JAVASCRIPT_MODULE_IMPORT_EXPORT_OUTSIDE_CERTIFIED_SUBSET",
        ),
        (
            "/** @param {integer} value @returns {integer} */\n"
            "export async function identity(value) { return value; }\n",
            "JAVASCRIPT_ASYNC_FUNCTION_OUTSIDE_CERTIFIED_SUBSET",
        ),
        (
            "module.exports = {};\n"
            "/** @param {integer} value @returns {integer} */\n"
            "export function identity(value) { return value; }\n",
            "JAVASCRIPT_TOP_LEVEL_STATEMENT_OUTSIDE_CERTIFIED_SUBSET",
        ),
        (
            "export function identity(value) { return value; }\n",
            "JAVASCRIPT_EXACT_JSDOC_TAG_SET_REQUIRED",
        ),
        (
            "/** @param {integer} left @param {integer} right @returns {boolean} */\n"
            "export function identity(left, right) { return left == right; }\n",
            "JAVASCRIPT_OPERATOR_UNSUPPORTED",
        ),
        (
            "/** @returns {integer} */\nexport function identity() { return 9007199254740993; }\n",
            "JAVASCRIPT_INTEGER_LITERAL_OUTSIDE_SAFE_SUBSET",
        ),
    ],
)
def test_javascript_dynamic_or_ambiguous_semantics_fail_closed(
    tmp_path: Path,
    body: str,
    reason: str,
) -> None:
    source = tmp_path / "unsafe.mjs"
    source.write_text(body, encoding="utf-8")

    with pytest.raises(RouteError, match=reason):
        analyze(source, "javascript", "identity")


def test_javascript_emitted_helper_comment_spoof_fails_closed(tmp_path: Path) -> None:
    semantic = analyze(JAVASCRIPT_FIXTURE, "javascript", "calculate")
    emitted = emit(semantic, "javascript")
    canonical = _JAVASCRIPT_HELPERS["safe_integer"]
    malicious = f"/*{canonical}*/\nfunction _elmosRequireSafeInteger(value) {{ return 0; }}"
    source = tmp_path / emitted.relative_path
    source.write_text(emitted.content.replace(canonical, malicious), encoding="utf-8")

    with pytest.raises(RouteError, match="JAVASCRIPT_EMITTED_HELPER_SOURCE_MISMATCH"):
        analyze(source, "javascript", "calculate", emitted_target=True)


@pytest.mark.parametrize("mutation", ["duplicate", "unknown"])
def test_javascript_emitted_helper_duplicate_or_unknown_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    semantic = analyze(JAVASCRIPT_FIXTURE, "javascript", "calculate")
    emitted = emit(semantic, "javascript")
    canonical = _JAVASCRIPT_HELPERS["safe_integer"]
    if mutation == "duplicate":
        content = emitted.content.replace(canonical, f"{canonical}\n\n{canonical}", 1)
    else:
        content = "function _elmosUnknown(value) { return value; }\n\n" + emitted.content
    source = tmp_path / emitted.relative_path
    source.write_text(content, encoding="utf-8")

    with pytest.raises(RouteError, match="JAVASCRIPT_EMITTED_HELPER_SOURCE_MISMATCH"):
        analyze(source, "javascript", "calculate", emitted_target=True)


def test_javascript_multifunction_relift_binds_helpers_used_by_the_whole_module(
    tmp_path: Path,
) -> None:
    module = ENGINE_ROOT / "fixtures" / "module" / "javascript" / "equivalence_module.mjs"
    integer = emit(analyze(module, "javascript", "calculate"), "javascript")
    number = emit(analyze(module, "javascript", "clampNumber"), "javascript")
    safe_integer = _JAVASCRIPT_HELPERS["safe_integer"]
    finite_number = _JAVASCRIPT_HELPERS["finite_number"]
    combined = "\n\n".join(
        (
            safe_integer,
            finite_number,
            integer.content.removeprefix(f"{safe_integer}\n\n"),
            number.content.removeprefix(f"{finite_number}\n\n"),
        )
    )
    source = tmp_path / "module.mjs"
    source.write_text(combined, encoding="utf-8")

    integer_relifted = analyze(source, "javascript", "calculate", emitted_target=True)
    number_relifted = analyze(source, "javascript", "clampNumber", emitted_target=True)

    assert integer_relifted.functions[0].name == "calculate"
    assert number_relifted.functions[0].name == "clampNumber"
