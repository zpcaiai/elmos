"""Re-appliable patch set for the 2026-08-25 fix pass.

Every replacement asserts an exact match count first, so a silent no-op is
impossible if the upstream file has moved (this repository has concurrent
sessions writing to it -- a `str.replace` that matches nothing looks like
success).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def patch(relative: str, old: str, new: str, *, expect: int = 1) -> None:
    path = ROOT / relative
    src = path.read_text(encoding="utf-8")
    found = src.count(old)
    if found != expect:
        raise SystemExit(f"ABORT {relative}: expected {expect} match(es), found {found}")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  patched {relative}")


PG = "engines/polyglot-route-engine/src/elmos_polyglot_route"
TR = "engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler"

# =============================================================================
# FIX 1 -- sql-transpiler: unexpected emission faults must fail closed
# =============================================================================
print("FIX 1  target emission fail-closed backstop")
patch(
    f"{TR}/transpiler.py",
    '''            syntax_parse="PASSED",
            target_emit="FAILED",
            target_reparse="FAILED" if code == "TARGET_REPARSE_FAILED" else "NOT_RUN",
        )
''',
    '''            syntax_parse="PASSED",
            target_emit="FAILED",
            target_reparse="FAILED" if code == "TARGET_REPARSE_FAILED" else "NOT_RUN",
        )
    except RuntimeError:
        # Adapter-identity integrity violations are not subset boundaries. They
        # mean the registry and the emission disagree about who produced the SQL,
        # so they must stay loud instead of being laundered into a BLOCKED result.
        raise
    except Exception as error:  # noqa: BLE001 - deliberate fail-closed backstop
        # Anything else escaping emission or reparse is a DEFECT, in this path or
        # in the pinned parser. Batch 31 requires target emission to fail closed,
        # so it is reported as a blocked result with its own code rather than
        # propagating a raw exception to the caller -- and with a code distinct
        # from UNSUPPORTED_SEMANTICS, so a defect can never be counted as a
        # declared boundary.
        #
        # Real instance this guards: an aggregate FILTER combined with an explicit
        # window frame reaches sqlglot's `ordered_sql`, which calls `sql_name()` on
        # a `Filter` node that does not have it. Reproduced in bare sqlglot at both
        # 30.13.0 and 30.14.0, so pinning forward does not remove the need for this.
        #
        # Only the exception TYPE is recorded: a message could carry fragments of
        # the customer's SQL, and `rawSourceSqlPersisted` is false by contract.
        return _blocked_result(
            request,
            diagnostic=Diagnostic(
                code="TARGET_EMISSION_FAULTED",
                severity="ERROR",
                statement_index=len(statement_irs),
                message=(
                    f"Target emission raised an unexpected {type(error).__name__} and was "
                    "failed closed. This is a defect in the emission path or its pinned "
                    "parser, not a declared subset boundary; please report it."
                ),
            ),
            syntax_parse="PASSED",
            target_emit="FAILED",
            target_reparse="NOT_RUN",
        )
''',
)

patch(
    f"{TR}/commercial.py",
    '''    except (ParseError, TokenError):
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_PARSE_FAILED",
                    severity="ERROR",
                    statement_index=None,
                    message="The exact source profile parser rejected the SQL.",
                ),
            ),
            source_parse="FAILED",
        )
''',
    '''    except (ParseError, TokenError):
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_PARSE_FAILED",
                    severity="ERROR",
                    statement_index=None,
                    message="The exact source profile parser rejected the SQL.",
                ),
            ),
            source_parse="FAILED",
        )
    except Exception as error:  # noqa: BLE001 - deliberate fail-closed backstop
        # Same discipline as transpiler.transpile: anything the pinned parser
        # raises that is not a declared parse rejection is a DEFECT, and it gets
        # its own code so it can never be counted as a source-side boundary.
        # Only the exception type is recorded -- a message could carry fragments
        # of the customer's SQL.
        return _result(
            request,
            target,
            route_id=route_id,
            statements=(),
            blockers=(
                CommercialBlocker(
                    code="SOURCE_PARSE_FAULTED",
                    severity="ERROR",
                    statement_index=None,
                    message=(
                        f"The exact source profile parser raised an unexpected "
                        f"{type(error).__name__} and was failed closed. This is a defect, "
                        "not a declared boundary; please report it."
                    ),
                ),
            ),
            source_parse="FAILED",
        )
''',
)

# =============================================================================
# FIX 2 -- polyglot frontend: a docstring must not reject the function
# =============================================================================
print("FIX 2  Python docstrings enter the bounded subset as provenance")
patch(
    f"{PG}/models.py",
    '''class Function:
    name: str
    parameters: tuple[Parameter, ...]
    return_type: str
    body: tuple[Statement, ...]
    source_span: SourceSpan | None = None
''',
    '''class Function:
    name: str
    parameters: tuple[Parameter, ...]
    return_type: str
    body: tuple[Statement, ...]
    source_span: SourceSpan | None = None
    #: Source-language documentation attached to the declaration (a Python
    #: docstring; the equivalent in other frontends can follow).
    #:
    #: This is PROVENANCE, not semantics, and the distinction is load-bearing:
    #: it appears in `to_mapping` -- so nothing the source carried is silently
    #: dropped and the artifact digest reflects it -- and NOT in
    #: `semantic_mapping`, so source/target equivalence is never asked to
    #: compare a Python `__doc__` against a Java method that has no such
    #: concept. Functions without documentation serialize byte-identically to
    #: before this field existed, so previously recorded IR digests still hold.
    documentation: str | None = None
''',
)

patch(
    f"{PG}/models.py",
    '''        _require_exact_keys(
            value,
            frozenset({"name", "parameters", "return_type", "body"}),
            frozenset({"source_span"}),
            _path,
        )
        name = _require_string(value["name"], f"{_path}.name", nonempty=True)
        return_type = _require_string(value["return_type"], f"{_path}.return_type")''',
    '''        _require_exact_keys(
            value,
            frozenset({"name", "parameters", "return_type", "body"}),
            frozenset({"source_span", "documentation"}),
            _path,
        )
        name = _require_string(value["name"], f"{_path}.name", nonempty=True)
        return_type = _require_string(value["return_type"], f"{_path}.return_type")
        documentation = (
            # An empty docstring is legal Python and stays distinguishable from
            # "no docstring at all", so `nonempty` is deliberately not required.
            _require_string(value["documentation"], f"{_path}.documentation")
            if "documentation" in value
            else None
        )''',
)

patch(
    f"{PG}/models.py",
    '''            body=tuple(Statement.from_mapping(item, _path=f"{_path}.body[{index}]") for index, item in enumerate(body)),
            source_span=_optional_source_span(value, _path),
        )''',
    '''            body=tuple(Statement.from_mapping(item, _path=f"{_path}.body[{index}]") for index, item in enumerate(body)),
            source_span=_optional_source_span(value, _path),
            documentation=documentation,
        )''',
)

patch(
    f"{PG}/models.py",
    '''    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "parameters": [parameter.to_mapping() for parameter in self.parameters],
            "return_type": self.return_type,
            "body": [statement.to_mapping() for statement in self.body],
        }
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_mapping()
        return result''',
    '''    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "parameters": [parameter.to_mapping() for parameter in self.parameters],
            "return_type": self.return_type,
            "body": [statement.to_mapping() for statement in self.body],
        }
        if self.source_span is not None:
            result["source_span"] = self.source_span.to_mapping()
        if self.documentation is not None:
            result["documentation"] = self.documentation
        return result''',
)

patch(
    f"{PG}/python_analyzer.py",
    "def analyze_python(path: Path, function_name: str, *, emitted_target: bool = False) -> SemanticIR:",
    '''def _split_leading_docstring(nodes: list[ast.stmt]) -> tuple[list[ast.stmt], str | None]:
    """Separate a leading docstring from the statements that follow it.

    A docstring is a bare string expression, so before this it hit the generic
    `PYTHON_UNSUPPORTED_STATEMENT:Expr` rejection and took the whole function
    with it. Measured on 20 real PyPI projects, 94 of the 109 functions whose
    signature was already fully inside the profile died on exactly this -- the
    single largest avoidable rejection in the frontend.

    Only the FIRST statement qualifies. A bare string anywhere else is a no-op
    expression, not documentation, and keeping it rejected is correct.

    The text is not discarded: `analyze_python` carries it into the IR as
    `Function.documentation` (provenance, not semantics), so the conversion
    never silently loses something the source declared.
    """

    if not nodes:
        return nodes, None
    first = nodes[0]
    if not (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return nodes, None
    remaining = nodes[1:]
    if not remaining:
        # A function whose entire body is its docstring has no behaviour to
        # convert. Fail closed with its own code rather than falling through to
        # a confusing empty-body error.
        raise RouteError("PYTHON_FUNCTION_BODY_IS_ONLY_DOCUMENTATION")
    return remaining, first.value.value


def analyze_python(path: Path, function_name: str, *, emitted_target: bool = False) -> SemanticIR:''',
)

patch(
    f"{PG}/python_analyzer.py",
    '''    body = _emitted_body(candidate.body, parameters) if emitted_target else candidate.body
    semantic = SemanticIR.from_mapping(
        {''',
    '''    documentation: str | None = None
    if emitted_target:
        # Deliberately NOT applied to the emitted-target re-analysis. This
        # engine's emitters never produce a docstring, so one appearing there
        # means the target did not come from them -- and the re-analysis gate
        # exists to catch exactly that. Accepting it would weaken the gate.
        body = _emitted_body(candidate.body, parameters)
    else:
        body, documentation = _split_leading_docstring(candidate.body)
    function_mapping: dict[str, Any] = {
        "name": candidate.name,
        "parameters": parameters,
        "return_type": return_type,
        "body": _statements(body, emitted_target=emitted_target),
    }
    if documentation is not None:
        function_mapping["documentation"] = documentation
    semantic = SemanticIR.from_mapping(
        {''',
)

patch(
    f"{PG}/python_analyzer.py",
    '''            "functions": [
                {
                    "name": candidate.name,
                    "parameters": parameters,
                    "return_type": return_type,
                    "body": _statements(body, emitted_target=emitted_target),
                }
            ],''',
    '''            "functions": [function_mapping],''',
)

print("all patches applied cleanly")
