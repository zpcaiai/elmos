"""`else if` chains, and the Go emission bug that lifting them uncovered.

The engine's frontends lift `else if` into the nested
`else: [if]` shape the IR has always carried -- CPython's ast gives it for free
because `elif` *is* that shape, SwiftSyntax recurses, and the TypeScript, JDT,
Roslyn, clang and ext/tokenizer frontends all wrap a non-block else. Go and
Rust rejected it outright instead, which cost twelve directed routes each for
no semantic reason: in both language specs `else if` is spelling, not a
construct.

Lifting it then exposed a defect the corpora had never reached. Go inserts a
semicolon at the newline after a closing brace, so the emitter's `}` / `else {`
on separate lines produced a file that does not parse. No fixture had an else
branch on a Go *target*, so nothing caught it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import ROUTED_LANGUAGES, Language, RouteError
from elmos_polyglot_route.native import SemanticIR

ENGINE_ROOT = Path(__file__).resolve().parents[1]

_BRACE_TARGETS: tuple[Language, ...] = tuple(
    language for language in ROUTED_LANGUAGES if language != "python"
)


def _chain_ir() -> SemanticIR:
    """`if a >= 90 {4} else if a >= 80 {3} else if a >= 70 {2} else {1}`."""

    def compare(bound: int) -> dict:
        return {
            "kind": "binary",
            "operator": ">=",
            "left": {"kind": "name", "value": "score"},
            "right": {"kind": "literal", "value": bound},
        }

    def returns(value: int) -> list[dict]:
        return [{"kind": "return", "expression": {"kind": "literal", "value": value}}]

    innermost = {
        "kind": "if",
        "condition": compare(70),
        "then": returns(2),
        "else": returns(1),
    }
    middle = {
        "kind": "if",
        "condition": compare(80),
        "then": returns(3),
        "else": [innermost],
    }
    outermost = {
        "kind": "if",
        "condition": compare(90),
        "then": returns(4),
        "else": [middle],
    }
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "go",
            "source_file": "sample.go",
            "analyzer": "test",
            "analyzer_version": "0",
            "diagnostics": [],
            "functions": [
                {
                    "name": "grade",
                    "return_type": "integer",
                    "parameters": [{"name": "score", "type": "integer"}],
                    "body": [outermost],
                }
            ],
        }
    )


def _simple_else_ir(source_language: Language = "go") -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": source_language,
            "source_file": "sample.go",
            "analyzer": "test",
            "analyzer_version": "0",
            "diagnostics": [],
            "functions": [
                {
                    "name": "pick",
                    "return_type": "integer",
                    "parameters": [{"name": "score", "type": "integer"}],
                    "body": [
                        {
                            "kind": "if",
                            "condition": {
                                "kind": "binary",
                                "operator": ">=",
                                "left": {"kind": "name", "value": "score"},
                                "right": {"kind": "literal", "value": 1},
                            },
                            "then": [
                                {"kind": "return", "expression": {"kind": "literal", "value": 4}}
                            ],
                            "else": [
                                {"kind": "return", "expression": {"kind": "literal", "value": 1}}
                            ],
                        }
                    ],
                }
            ],
        }
    )


def test_go_emission_keeps_the_closing_brace_and_else_on_one_line() -> None:
    """The exact defect: `}` then `else` on the next line does not parse.

    Go's spec inserts a semicolon at a newline that follows a closing brace,
    so the `else` is stranded and `go build` reports
    `syntax error: unexpected keyword else, expected }`.
    """
    content = emit(_simple_else_ir(), "go").content
    stripped = [line.strip() for line in content.splitlines()]

    assert "} else {" in stripped
    assert "else {" not in stripped, "a bare `else {` line makes the emitted Go unparseable"


def test_rust_emission_keeps_its_existing_else_shape() -> None:
    """The asymmetry with Go is deliberate, so it is asserted rather than assumed.

    Rust has no semicolon-insertion rule, so its two-line shape was already
    valid. Rewriting it would churn the emitted bytes -- and therefore the
    content-addressed evidence -- of every Rust emission with an else branch,
    for no correctness gain.
    """
    content = emit(_simple_else_ir(), "rust").content
    stripped = [line.strip() for line in content.splitlines()]

    assert "else {" in stripped
    assert "} else {" not in stripped


def test_python_emission_is_unaffected_by_the_brace_rule() -> None:
    content = emit(_simple_else_ir(), "python").content
    assert "else:" in [line.strip() for line in content.splitlines()]


@pytest.mark.parametrize("target", _BRACE_TARGETS)
def test_a_nested_else_chain_emits_three_branches_for_every_brace_target(
    target: Language,
) -> None:
    content = emit(_chain_ir(), target).content
    lines = [line.strip() for line in content.splitlines()]

    # Some targets prepend range-guard helpers that carry their own `if` and
    # `return` lines, and several alpha-rename the function, so the assertions
    # key on the chain's own thresholds rather than on line counts or the name.
    for threshold in ("90", "80", "70"):
        assert any(line.startswith("if") and threshold in line for line in lines), threshold
    assert sum(1 for line in lines if line.endswith("else {")) == 3
    # Every leaf of the chain has to survive; a chain that loses its tail would
    # still compile and would still be wrong. The literal may be wrapped by a
    # target's own range guard (`_elmosRequireSafeInteger(4)`, `Int64(4)`), so
    # the assertion is on the value reaching a return, not on its spelling.
    returns = [line for line in lines if line.startswith("return")]
    for value in ("4", "3", "2", "1"):
        assert any(value in line for line in returns), value


def test_the_go_frontend_no_longer_rejects_an_else_if_chain() -> None:
    source = (ENGINE_ROOT / "native" / "go" / "analyzer.go").read_text(encoding="utf-8")

    assert "GO_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET" not in source
    assert "func ifStatement(" in source
    assert "elseBody = []map[string]any{ifStatement(alternative, emittedTarget, records, functionNames)}" in source
    # The init-statement boundary is unchanged and must stay unchanged: hoisting
    # it needs a local-declaration IR kind that no target emitter has.
    assert "GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET" in source


def test_the_rust_frontend_no_longer_rejects_an_else_if_chain() -> None:
    source = (ENGINE_ROOT / "native" / "rust" / "src" / "main.rs").read_text(encoding="utf-8")

    assert "fn lift_if(" in source
    assert "Expr::If(chained) => vec![lift_if(chained, emitted_target)]" in source
    # Anything else in the else position is still outside the profile.
    assert "RUST_ELSE_IF_OUTSIDE_CERTIFIED_SUBSET" in source


def test_an_unknown_statement_kind_still_fails_closed() -> None:
    """The widened else branch must not widen anything else.

    The rejection lands at IR construction, before emission is ever reached,
    which is the boundary that keeps an unsupported construct from becoming a
    silently-dropped statement in a target file.
    """
    payload = (
        {
            "schema_version": "1.0.0",
            "source_language": "go",
            "source_file": "sample.go",
            "analyzer": "test",
            "analyzer_version": "0",
            "diagnostics": [],
            "functions": [
                {
                    "name": "pick",
                    "return_type": "integer",
                    "parameters": [{"name": "score", "type": "integer"}],
                    "body": [{"kind": "unsupported_statement", "condition": None}],
                }
            ],
        }
    )
    with pytest.raises(RouteError, match="UNSUPPORTED_STATEMENT:unsupported_statement"):
        emit(SemanticIR.from_mapping(payload), "go")


# --- frontend lifting: these need the pinned Go and Rust toolchains ---------


_GO_CHAIN = (
    "package sample\n\n"
    "func grade(score int64) int64 {\n"
    "\tif score >= 90 {\n\t\treturn 4\n"
    "\t} else if score >= 80 {\n\t\treturn 3\n"
    "\t} else if score >= 70 {\n\t\treturn 2\n"
    "\t} else {\n\t\treturn 1\n\t}\n}\n"
)

_RUST_CHAIN = (
    "pub fn grade(score: i64) -> i64 {\n"
    "    if score >= 90 {\n        return 4;\n"
    "    } else if score >= 80 {\n        return 3;\n"
    "    } else if score >= 70 {\n        return 2;\n"
    "    } else {\n        return 1;\n    }\n}\n"
)


def _assert_three_deep_chain(ir: SemanticIR) -> None:
    body = ir.functions[0].body
    assert len(body) == 1
    outermost = body[0]
    assert outermost.kind == "if"

    middle = outermost.else_body
    assert len(middle) == 1 and middle[0].kind == "if"

    innermost = middle[0].else_body
    assert len(innermost) == 1 and innermost[0].kind == "if"

    assert [item.kind for item in innermost[0].else_body] == ["return"]


def test_go_lifts_an_else_if_chain_into_nested_ifs(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "sample.go"
    source.write_text(_GO_CHAIN, encoding="utf-8")
    _assert_three_deep_chain(analyze(source, "go", "grade"))


def test_rust_lifts_an_else_if_chain_into_nested_ifs(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "sample.rs"
    source.write_text(_RUST_CHAIN, encoding="utf-8")
    _assert_three_deep_chain(analyze(source, "rust", "grade"))


def test_go_still_rejects_an_if_init_statement_at_the_top_level(tmp_path: Path) -> None:
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "sample.go"
    source.write_text(
        "package sample\n\n"
        "func bad(n int64) int64 {\n"
        "\tif x := n + 1; x > 0 {\n\t\treturn x\n\t}\n\treturn 0\n}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "go", "bad")


def test_go_still_rejects_an_if_init_statement_inside_an_else_if(tmp_path: Path) -> None:
    """The widened else branch must not smuggle an init past the check.

    The chain recurses through the same guard, so an init in the third link is
    rejected exactly like one in the first. Without that, widening `else if`
    would have quietly opened a construct no target emitter can express.
    """
    from elmos_polyglot_route.native import analyze

    source = tmp_path / "sample.go"
    source.write_text(
        "package sample\n\n"
        "func bad(n int64) int64 {\n"
        "\tif n > 0 {\n\t\treturn 1\n"
        "\t} else if x := n - 1; x < 0 {\n\t\treturn 2\n\t}\n\treturn 0\n}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="GO_IF_INIT_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "go", "bad")
