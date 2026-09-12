"""C++ and Objective-C source analysis, backed by clang's own AST.

Same posture as the other analyzers in this engine: a real compiler frontend,
never string matching. `clang -Xclang -ast-dump=json -fsyntax-only` gives the
same tree the compiler type-checked, so the lifted semantic IR carries clang's
resolved types rather than a guess at them.

One module serves both languages because for the certified
`typed-pure-function-v1` subset they differ in exactly three places, all of
them explicit below: the boolean spelling (`bool` vs `BOOL`), the string type
(`std::string` vs `NSString *`), and how a string operation appears in the
tree (`CXXOperatorCallExpr` vs `ObjCMessageExpr`).

Two source spellings are refused rather than lifted, for the same reason the
Java analyzer refuses `float` and the boxed wrappers:

* `float` -- a 24-bit significand does not round-trip through the canonical
  `number` (binary64): `0.1f + 0.2f != 0.1 + 0.2`.
* `==` / `!=` on `NSString *` -- that is a *pointer* comparison in
  Objective-C. Two equal strings at different addresses answer NO, so lifting
  it as canonical equality would change the program's meaning on every other
  target. `isEqualToString:` is the value comparison and is lifted.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .models import Language, RouteError, SemanticIR
from .toolchains import sanitized_subprocess_env

#: Nodes that wrap a value without changing it in the certified subset.
_TRANSPARENT = frozenset(
    {
        "ImplicitCastExpr",
        "CStyleCastExpr",
        "ParenExpr",
        "ExprWithCleanups",
        "MaterializeTemporaryExpr",
        "CXXBindTemporaryExpr",
        "ConstantExpr",
        "NoOp",
    }
)

_BINARY_OPERATORS = frozenset({"+", "-", "*", "/", "%", "<", "<=", ">", ">=", "==", "!=", "&&", "||"})

#: Canonical integer is signed and exactly 64 bits. Narrow or platform-sized
#: integer spellings are rejected: widening a source `int` would erase its
#: overflow behaviour, while `long`/`NSInteger` change width across targets.
_CPP_INTEGER_TYPES = frozenset({"int64_t", "std::int64_t"})
_OBJC_INTEGER_TYPES = frozenset({"long long", "int64_t"})
_NON_CANONICAL_INTEGER_TYPES = frozenset(
    {
        "short",
        "int",
        "long",
        "int8_t",
        "int16_t",
        "int32_t",
        "std::int8_t",
        "std::int16_t",
        "std::int32_t",
        "NSInteger",
    }
)
_STRING_TYPES = frozenset({"std::string", "string", "NSString *", "NSString"})
_BOOLEAN_TYPES = frozenset({"bool", "BOOL"})

_OPERATOR_METHOD = re.compile(r"^operator(==|!=|\+|-|\*|/|%|<=|>=|<|>)$")

_EMITTED_HELPERS: dict[Language, dict[str, tuple[str, int]]] = {
    "cpp": {
        "elmos_checked_add": ("+", 2),
        "elmos_checked_sub": ("-", 2),
        "elmos_checked_mul": ("*", 2),
        "elmos_checked_div": ("/", 2),
        "elmos_checked_mod": ("%", 2),
        "elmos_non_zero": ("identity", 1),
    },
    "objc": {
        "ElmosCheckedAdd": ("+", 2),
        "ElmosCheckedSub": ("-", 2),
        "ElmosCheckedMul": ("*", 2),
        "ElmosCheckedDiv": ("/", 2),
        "ElmosCheckedMod": ("%", 2),
        "ElmosNonZero": ("identity", 1),
    },
}


def _position(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RouteError("CLANG_SOURCE_POSITION_REQUIRED")
    position: dict[str, Any] = value
    for nested in ("expansionLoc", "spellingLoc"):
        nested_position = position.get(nested)
        if isinstance(nested_position, dict):
            position = nested_position
            break
    if not isinstance(position.get("offset"), int):
        raise RouteError("CLANG_SOURCE_OFFSET_REQUIRED")
    return position


def _source_span(node: dict[str, Any], source_file: str) -> dict[str, object]:
    source_range = node.get("range")
    if not isinstance(source_range, dict):
        location = _position(node.get("loc"))
        start = int(location["offset"])
        end = start + int(location.get("tokLen", 0))
    else:
        begin = _position(source_range.get("begin"))
        finish = _position(source_range.get("end"))
        start = int(begin["offset"])
        end = int(finish["offset"]) + int(finish.get("tokLen", 0))
    if start < 0 or end <= start:
        raise RouteError("CLANG_SOURCE_SPAN_INVALID")
    return {"file": source_file, "start_byte": start, "end_byte": end}


def _sdk_path(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit)
    else:
        xcrun = Path("/usr/bin/xcrun")
        if not xcrun.is_file():
            raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:xcrun")
        with tempfile.TemporaryDirectory(prefix="elmos-clang-sdk-env-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            completed = subprocess.run(
                [str(xcrun), "--sdk", "macosx", "--show-sdk-path"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=sanitized_subprocess_env(
                    home=home,
                    temp_dir=scratch,
                    executable_dirs=(xcrun.parent,),
                ),
            )
        path = Path(completed.stdout.strip())
        if completed.returncode != 0:
            raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:macosx-sdk")
    # Xcode exposes versioned SDK names as trusted in-bundle symlinks (for
    # example MacOSX26.5.sdk -> MacOSX.sdk); the exact-toolchain gate already
    # pins and verifies the containing Xcode/SDK tuple.
    if not path.is_dir():
        raise RouteError(f"EXACT_TOOLCHAIN_APPLE_SDK_INVALID:{path}")
    return str(path)


def _run_clang(
    executable: str,
    source: Path,
    language: Language,
    sdk_path: str | None,
    timeout: int = 600,
) -> dict[str, Any]:
    mode = "c++" if language == "cpp" else "objective-c"
    standard = "-std=c++20" if language == "cpp" else "-std=c17"
    command = [
        executable,
        "-x",
        mode,
        standard,
        "-isysroot",
        _sdk_path(sdk_path),
        "-Xclang",
        "-ast-dump=json",
        "-fsyntax-only",
        str(source),
    ]
    if language == "objc":
        command[4:4] = ["-fobjc-arc", "-framework", "Foundation"]
    with tempfile.TemporaryDirectory(prefix="elmos-clang-env-") as temporary:
        root = Path(temporary)
        home = root / "home"
        scratch = root / "tmp"
        home.mkdir(mode=0o700)
        scratch.mkdir(mode=0o700)
        try:
            completed = subprocess.run(
                command,
                cwd=source.parent,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=sanitized_subprocess_env(
                    home=home,
                    temp_dir=scratch,
                    executable_dirs=(Path(executable).resolve().parent,),
                ),
            )
        except subprocess.TimeoutExpired as error:
            raise RouteError(f"NATIVE_ANALYZER_TIMEOUT:{executable}") from error
    errors = [
        line
        for line in completed.stderr.splitlines()
        if ": error:" in line or ": fatal error:" in line
    ]
    if errors:
        raise RouteError("SOURCE_DIAGNOSTICS_BLOCK_ANALYSIS:" + "; ".join(errors[:5])[:2_000])
    if completed.returncode != 0 or not completed.stdout.strip():
        detail = (completed.stderr or completed.stdout).strip()[-2_000:]
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{executable}:{detail}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RouteError(f"NATIVE_ANALYZER_INVALID_JSON:{executable}") from error
    if not isinstance(value, dict):
        raise RouteError("NATIVE_ANALYZER_OBJECT_REQUIRED")
    return value


def _strip(type_name: str) -> str:
    """Drop the qualifiers the canonical model has no notion of.

    `const std::string &` is the idiomatic way to pass a string by value in
    C++; for a pure function it reads exactly like the canonical `string`.
    """
    cleaned = type_name.replace("const", " ").replace("__strong", " ").replace("&", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned.endswith(" *"):
        return cleaned
    return cleaned.replace(" *", " *").strip()


def _canonical_type(type_name: str, language: Language, record_names: set[str] | None = None) -> str:
    cleaned = _strip(type_name)
    if cleaned.startswith("struct "):
        cleaned = cleaned[7:].strip()
    if record_names and cleaned in record_names:
        return cleaned
    integer_types = _CPP_INTEGER_TYPES if language == "cpp" else _OBJC_INTEGER_TYPES
    if cleaned in integer_types:
        return "integer"
    if language == "cpp" and cleaned == "long long":
        raise RouteError(f"CPP_INTEGER_SPELLING_OUTSIDE_EXACT_PROFILE:{type_name}")
    if cleaned in _NON_CANONICAL_INTEGER_TYPES:
        raise RouteError(f"{language.upper()}_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:{type_name}")
    if cleaned == "double":
        return "number"
    if cleaned in _BOOLEAN_TYPES:
        return "boolean"
    if cleaned in _STRING_TYPES:
        return "string"
    if cleaned == "float":
        raise RouteError(f"{language.upper()}_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET:{type_name}")
    if record_names and cleaned in record_names:
        return cleaned
    raise RouteError(f"{language.upper()}_UNSUPPORTED_TYPE:{type_name}")


def _qual_type(node: dict[str, Any]) -> str:
    value = node.get("type")
    if not isinstance(value, dict) or "qualType" not in value:
        raise RouteError("CLANG_NODE_WITHOUT_TYPE")
    return str(value["qualType"])


def _desugared_type(node: dict[str, Any]) -> str | None:
    value = node.get("type")
    if not isinstance(value, dict) or not value.get("desugaredQualType"):
        return None
    return str(value["desugaredQualType"])


def _canonical_node_type(node: dict[str, Any], language: Language, record_names: set[str] | None = None) -> str:
    source_type = _qual_type(node)
    canonical = _canonical_type(source_type, language, record_names)
    if canonical != "integer":
        return canonical
    cleaned = _strip(source_type)
    direct_type = language == "objc" and cleaned == "long long"
    if direct_type:
        return canonical
    desugared = _desugared_type(node)
    if desugared is None or _strip(desugared) != "long long":
        raise RouteError(
            f"{language.upper()}_INTEGER_TYPEDEF_NOT_EXACT_INT64:{source_type}:{desugared or 'missing-desugared-type'}"
        )
    return canonical


def _return_type(function: dict[str, Any]) -> str:
    signature = _qual_type(function)
    head = signature.split("(")[0].strip()
    if not head:
        raise RouteError("CLANG_UNREADABLE_RETURN_TYPE")
    return head


def _verify_integer_return_width(
    body: dict[str, Any],
    language: Language,
    canonical_return_type: str,
) -> None:
    if canonical_return_type != "integer":
        return
    returns: list[dict[str, Any]] = []

    def visit(node: dict[str, Any]) -> None:
        if node.get("kind") == "ReturnStmt":
            returns.append(node)
        for child in _inner(node):
            visit(child)

    visit(body)
    if not returns:
        raise RouteError(f"{language.upper()}_INTEGER_FUNCTION_RETURN_REQUIRED")
    for returning in returns:
        children = _inner(returning)
        if len(children) != 1:
            raise RouteError(f"{language.upper()}_INTEGER_RETURN_EXPRESSION_REQUIRED")
        expression = children[0]
        source_type = _qual_type(expression)
        direct_type = language == "objc" and _strip(source_type) == "long long"
        desugared = _desugared_type(expression)
        if not direct_type and (desugared is None or _strip(desugared) != "long long"):
            raise RouteError(
                f"{language.upper()}_INTEGER_RETURN_NOT_EXACT_INT64:"
                f"{source_type}:{desugared or 'missing-desugared-type'}"
            )


def _inner(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in node.get("inner", []) if isinstance(item, dict)]


def _mapped(node: dict[str, Any], source_file: str, value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "source_span": _source_span(node, source_file)}


def _boolean_literal_value(node: dict[str, Any], language: Language) -> bool:
    raw = node.get("value")
    if node.get("kind") == "CXXBoolLiteralExpr" and language == "cpp":
        if isinstance(raw, bool):
            return raw
        if raw == "true":
            return True
        if raw == "false":
            return False
        raise RouteError(f"CPP_BOOLEAN_LITERAL_AST_VALUE_INVALID:{raw!r}")
    if node.get("kind") == "ObjCBoolLiteralExpr" and language == "objc":
        if raw == "__objc_yes":
            return True
        if raw == "__objc_no":
            return False
        raise RouteError(f"OBJC_BOOLEAN_LITERAL_AST_VALUE_INVALID:{raw!r}")
    raise RouteError(f"{language.upper()}_BOOLEAN_LITERAL_AST_KIND_INVALID:{node.get('kind')}")


def _objc_stdbool_macro_value(node: dict[str, Any]) -> bool | None:
    source_range = node.get("range")
    begin = source_range.get("begin") if isinstance(source_range, dict) else None
    spelling = begin.get("spellingLoc") if isinstance(begin, dict) else None
    expansion = begin.get("expansionLoc") if isinstance(begin, dict) else None
    if not isinstance(spelling, dict) or not isinstance(expansion, dict):
        return None
    spelling_file = str(spelling.get("file", ""))
    if Path(spelling_file).name != "stdbool.h" or not isinstance(expansion.get("offset"), int):
        return None
    raw = str(node.get("value", ""))
    if raw == "0":
        return False
    if raw == "1":
        return True
    raise RouteError(f"OBJC_STDBOOL_LITERAL_AST_VALUE_INVALID:{raw!r}")


def _unwrap(node: dict[str, Any]) -> dict[str, Any]:
    while node.get("kind") in _TRANSPARENT:
        children = _inner(node)
        if len(children) != 1:
            raise RouteError(f"CPP_UNSUPPORTED_EXPRESSION:{node.get('kind')}")
        node = children[0]
    return node


def _string_message(node: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """`[a isEqualToString:b]` / `[a stringByAppendingString:b]` -> canonical."""
    selector = str(node.get("selector", ""))
    operands = [_unwrap(item) for item in _inner(node)]
    if len(operands) != 2:
        return None
    if selector == "isEqualToString:":
        return "==", operands[0], operands[1]
    if selector == "stringByAppendingString:":
        return "+", operands[0], operands[1]
    return None


def _callee_name(node: dict[str, Any]) -> str:
    node = _unwrap(node)
    if node.get("kind") == "DeclRefExpr":
        referenced = node.get("referencedDecl")
        if isinstance(referenced, dict) and referenced.get("name"):
            return str(referenced["name"])
    children = _inner(node)
    return _callee_name(children[0]) if len(children) == 1 else ""


def _expression(
    node: dict[str, Any],
    language: Language,
    source_file: str,
    emitted_target: bool,
    expected_type: str | None = None,
) -> dict[str, Any]:
    node = _unwrap(node)
    kind = node.get("kind")

    if kind == "DeclRefExpr":
        referenced = node.get("referencedDecl")
        if not isinstance(referenced, dict) or not referenced.get("name"):
            raise RouteError("CLANG_UNRESOLVED_NAME")
        return _mapped(node, source_file, {"kind": "name", "value": str(referenced["name"])})

    if kind == "IntegerLiteral":
        if expected_type == "boolean":
            if language == "objc":
                value = _objc_stdbool_macro_value(node)
                if value is not None:
                    return _mapped(node, source_file, {"kind": "literal", "value": value})
            raise RouteError(f"{language.upper()}_BOOLEAN_INTEGER_COERCION_OUTSIDE_CERTIFIED_SUBSET")
        return _mapped(node, source_file, {"kind": "literal", "value": int(str(node["value"]))})
    if kind == "FloatingLiteral":
        return _mapped(node, source_file, {"kind": "literal", "value": float(str(node["value"]))})
    if kind in ("CXXBoolLiteralExpr", "ObjCBoolLiteralExpr"):
        if expected_type not in (None, "boolean"):
            raise RouteError(f"{language.upper()}_BOOLEAN_LITERAL_TYPE_MISMATCH:{expected_type}")
        return _mapped(
            node,
            source_file,
            {"kind": "literal", "value": _boolean_literal_value(node, language)},
        )
    if kind == "StringLiteral":
        return _mapped(node, source_file, {"kind": "literal", "value": json.loads(str(node["value"]))})
    if kind == "ObjCStringLiteral":
        children = _inner(node)
        if len(children) == 1:
            mapped_expression = _expression(children[0], language, source_file, emitted_target)
            return {**mapped_expression, "source_span": _source_span(node, source_file)}

    if kind == "CXXConstructExpr" and language == "cpp":
        children = _inner(node)
        if _strip(_qual_type(node)) != "std::string" or len(children) != 1:
            raise RouteError("CPP_STRING_CONSTRUCTION_OUTSIDE_CERTIFIED_SUBSET")
        child = _unwrap(children[0])
        if _strip(_qual_type(child)) not in _STRING_TYPES and child.get("kind") != "StringLiteral":
            raise RouteError("CPP_STRING_CONSTRUCTION_OUTSIDE_CERTIFIED_SUBSET")
        mapped_expression = _expression(child, language, source_file, emitted_target)
        return {**mapped_expression, "source_span": _source_span(node, source_file)}

    if kind == "BinaryOperator":
        operator = str(node.get("opcode", ""))
        if operator not in _BINARY_OPERATORS:
            raise RouteError(f"{language.upper()}_UNSUPPORTED_OPERATOR:{operator}")
        operands = _inner(node)
        if len(operands) != 2:
            raise RouteError("CLANG_MALFORMED_BINARY_OPERATOR")
        if emitted_target and operator in {"+", "-", "*", "/", "%"}:
            integer_types = _CPP_INTEGER_TYPES if language == "cpp" else _OBJC_INTEGER_TYPES

            def emitted_integer_operand(operand: dict[str, Any]) -> bool:
                unwrapped = _unwrap(operand)
                return _strip(_qual_type(unwrapped)) in integer_types or unwrapped.get("kind") == "IntegerLiteral"

            if all(emitted_integer_operand(operand) for operand in operands):
                raise RouteError(f"{language.upper()}_EMITTED_INTEGER_OPERATOR_WITHOUT_EXACT_HELPER:{operator}")
            if operator == "/":
                right = _unwrap(operands[1])
                expected_guard = "elmos_non_zero" if language == "cpp" else "ElmosNonZero"
                right_children = _inner(right)
                if _strip(_qual_type(_unwrap(operands[0]))) == "double" and (
                    right.get("kind") != "CallExpr"
                    or not right_children
                    or _callee_name(right_children[0]) != expected_guard
                ):
                    raise RouteError(f"{language.upper()}_EMITTED_FLOAT_DIVISOR_WITHOUT_EXACT_HELPER")
        if operator in ("==", "!=") and language == "objc":
            left_type = _strip(_qual_type(_unwrap(operands[0])))
            if left_type in _STRING_TYPES:
                # Pointer identity, not value equality -- see the module
                # docstring.
                raise RouteError("OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET")
        return _mapped(
            node,
            source_file,
            {
                "kind": "binary",
                "operator": operator,
                "left": _expression(
                    operands[0],
                    language,
                    source_file,
                    emitted_target,
                    "boolean" if operator in {"&&", "||"} else None,
                ),
                "right": _expression(
                    operands[1],
                    language,
                    source_file,
                    emitted_target,
                    "boolean" if operator in {"&&", "||"} else None,
                ),
            },
        )

    if kind == "CXXOperatorCallExpr":
        children = _inner(node)
        if len(children) == 3:
            callee = _unwrap(children[0])
            referenced = callee.get("referencedDecl")
            name = str(referenced.get("name", "")) if isinstance(referenced, dict) else ""
            match = _OPERATOR_METHOD.match(name)
            if match:
                return _mapped(
                    node,
                    source_file,
                    {
                        "kind": "binary",
                        "operator": match.group(1),
                        "left": _expression(children[1], language, source_file, emitted_target),
                        "right": _expression(children[2], language, source_file, emitted_target),
                    },
                )

    if kind == "ObjCMessageExpr":
        lifted = _string_message(node)
        if lifted is not None:
            operator, left, right = lifted
            return _mapped(
                node,
                source_file,
                {
                    "kind": "binary",
                    "operator": operator,
                    "left": _expression(left, language, source_file, emitted_target),
                    "right": _expression(right, language, source_file, emitted_target),
                },
            )

    if kind == "MemberExpr":
        member_name = str(node.get("name", "")).strip()
        children = _inner(node)
        if not member_name or len(children) != 1:
            raise RouteError(f"{language.upper()}_MALFORMED_MEMBER_EXPR")
        target_expr = _expression(children[0], language, source_file, emitted_target)
        return _mapped(
            node,
            source_file,
            {
                "kind": "member_access",
                "target": target_expr,
                "member": member_name,
            },
        )

    if kind == "CallExpr":
        children = _inner(node)
        if not children:
            raise RouteError(f"{language.upper()}_CALL_CALLEE_REQUIRED")
        callee_name = _callee_name(children[0])
        if emitted_target:
            helper = _EMITTED_HELPERS[language].get(callee_name)
            if helper is None:
                raise RouteError(f"{language.upper()}_EMITTED_HELPER_UNRECOGNIZED:{callee_name}")
            operator, arity = helper
            arguments = children[1:]
            if len(arguments) != arity:
                raise RouteError(f"{language.upper()}_EMITTED_HELPER_ARITY:{callee_name}")
            if operator == "identity":
                mapped_expression = _expression(arguments[0], language, source_file, emitted_target)
                return {**mapped_expression, "source_span": _source_span(node, source_file)}
            return _mapped(
                node,
                source_file,
                {
                    "kind": "binary",
                    "operator": operator,
                    "left": _expression(arguments[0], language, source_file, emitted_target),
                    "right": _expression(arguments[1], language, source_file, emitted_target),
                },
            )
        if not callee_name:
            raise RouteError(f"{language.upper()}_CALL_WITHOUT_NAME")
        call_arguments = [
            _expression(arg, language, source_file, emitted_target)
            for arg in children[1:]
        ]
        return _mapped(
            node,
            source_file,
            {
                "kind": "call",
                "function_name": callee_name,
                "arguments": call_arguments,
            },
        )

    raise RouteError(f"{language.upper()}_UNSUPPORTED_EXPRESSION:{kind}")


def _statements(
    nodes: list[dict[str, Any]],
    language: Language,
    source_file: str,
    emitted_target: bool,
    return_type: str,
    known_variables: set[str] | None = None,
    parameter_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    known = set(known_variables) if known_variables is not None else set()
    params = set(parameter_names) if parameter_names is not None else set()
    for node in nodes:
        kind = node.get("kind")
        if kind == "ReturnStmt":
            children = _inner(node)
            if len(children) != 1:
                raise RouteError("CLANG_RETURN_WITHOUT_VALUE")
            result.append(
                _mapped(
                    node,
                    source_file,
                    {
                        "kind": "return",
                        "expression": _expression(
                            children[0],
                            language,
                            source_file,
                            emitted_target,
                            return_type,
                        ),
                    },
                )
            )
            continue
        if kind == "IfStmt":
            children = _inner(node)
            if node.get("hasInit") or node.get("isConstexpr") or len(children) < 2:
                raise RouteError(f"{language.upper()}_UNSUPPORTED_STATEMENT:IfStmt")
            condition, then_branch = children[0], children[1]
            else_branch = children[2] if node.get("hasElse") and len(children) > 2 else None
            result.append(
                _mapped(
                    node,
                    source_file,
                    {
                        "kind": "if",
                        "condition": _expression(
                            condition,
                            language,
                            source_file,
                            emitted_target,
                            "boolean",
                        ),
                        "then": _statement_body(
                            then_branch,
                            language,
                            source_file,
                            emitted_target,
                            return_type,
                            known_variables=set(known),
                            parameter_names=params,
                        ),
                        "else": (
                            _statement_body(
                                else_branch,
                                language,
                                source_file,
                                emitted_target,
                                return_type,
                                known_variables=set(known),
                                parameter_names=params,
                            )
                            if else_branch
                            else []
                        ),
                    },
                )
            )
            continue
        if kind == "DeclStmt":
            var_decls = [child for child in _inner(node) if child.get("kind") == "VarDecl"]
            if not var_decls:
                raise RouteError(f"{language.upper()}_UNSUPPORTED_DECLARATION:DeclStmt")
            for var_decl in var_decls:
                var_name = str(var_decl.get("name", "")).strip()
                if not var_name:
                    raise RouteError(f"{language.upper()}_LOCAL_VARIABLE_NAME_REQUIRED")
                declared_type = _canonical_node_type(var_decl, language)
                inits = _inner(var_decl)
                if len(inits) != 1:
                    raise RouteError(f"{language.upper()}_LOCAL_VARIABLE_INITIALIZER_REQUIRED:{var_name}")
                init_expr = _expression(inits[0], language, source_file, emitted_target, declared_type)
                known.add(var_name)
                result.append(
                    _mapped(
                        var_decl,
                        source_file,
                        {
                            "kind": "let",
                            "name": var_name,
                            "type": declared_type,
                            "expression": init_expr,
                        },
                    )
                )
            continue
        if kind == "BinaryOperator" and node.get("opcode") == "=":
            operands = _inner(node)
            if len(operands) != 2:
                raise RouteError("CLANG_MALFORMED_ASSIGNMENT")
            left = _unwrap(operands[0])
            if left.get("kind") != "DeclRefExpr":
                raise RouteError(f"{language.upper()}_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET")
            ref = left.get("referencedDecl")
            target_name = str(ref.get("name", "")).strip() if isinstance(ref, dict) else ""
            if not target_name:
                raise RouteError(f"{language.upper()}_ASSIGNMENT_TARGET_NAME_REQUIRED")
            if target_name in params:
                raise RouteError(f"{language.upper()}_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{target_name}")
            if target_name not in known:
                raise RouteError(f"{language.upper()}_ASSIGNMENT_TARGET_NOT_DECLARED:{target_name}")
            assigned_expr = _expression(operands[1], language, source_file, emitted_target)
            result.append(
                _mapped(
                    node,
                    source_file,
                    {
                        "kind": "assign",
                        "name": target_name,
                        "expression": assigned_expr,
                    },
                )
            )
            continue
        if kind == "CompoundAssignOperator":
            opcode = str(node.get("opcode", ""))
            if opcode not in {"+=", "-=", "*=", "/=", "%="}:
                raise RouteError(f"{language.upper()}_UNSUPPORTED_COMPOUND_ASSIGN_OPERATOR:{opcode}")
            operands = _inner(node)
            if len(operands) != 2:
                raise RouteError("CLANG_MALFORMED_COMPOUND_ASSIGNMENT")
            left = _unwrap(operands[0])
            if left.get("kind") != "DeclRefExpr":
                raise RouteError(f"{language.upper()}_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET")
            ref = left.get("referencedDecl")
            target_name = str(ref.get("name", "")).strip() if isinstance(ref, dict) else ""
            if not target_name:
                raise RouteError(f"{language.upper()}_ASSIGNMENT_TARGET_NAME_REQUIRED")
            if target_name in params:
                raise RouteError(f"{language.upper()}_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{target_name}")
            if target_name not in known:
                raise RouteError(f"{language.upper()}_ASSIGNMENT_TARGET_NOT_DECLARED:{target_name}")
            rhs_expr = _expression(operands[1], language, source_file, emitted_target)
            lhs_ref = _mapped(left, source_file, {"kind": "name", "value": target_name})
            binary_expr = _mapped(
                node,
                source_file,
                {
                    "kind": "binary",
                    "operator": opcode[:-1],
                    "left": lhs_ref,
                    "right": rhs_expr,
                },
            )
            result.append(
                _mapped(
                    node,
                    source_file,
                    {
                        "kind": "assign",
                        "name": target_name,
                        "expression": binary_expr,
                    },
                )
            )
            continue
        if kind == "WhileStmt":
            children = _inner(node)
            if len(children) != 2:
                raise RouteError(f"{language.upper()}_MALFORMED_WHILE_STMT")
            condition, body = children[0], children[1]
            result.append(
                _mapped(
                    node,
                    source_file,
                    {
                        "kind": "while",
                        "condition": _expression(
                            condition,
                            language,
                            source_file,
                            emitted_target,
                            "boolean",
                        ),
                        "body": _statement_body(
                            body,
                            language,
                            source_file,
                            emitted_target,
                            return_type,
                            known_variables=set(known),
                            parameter_names=params,
                        ),
                    },
                )
            )
            continue
        if kind == "ForStmt":
            raw_children = node.get("inner", [])
            if len(raw_children) < 5:
                raise RouteError(f"{language.upper()}_MALFORMED_FOR_STMT")
            init, cond, inc, body = raw_children[0], raw_children[2], raw_children[3], raw_children[4]
            if not isinstance(init, dict) or init.get("kind") != "DeclStmt":
                raise RouteError(f"{language.upper()}_FOR_INIT_MUST_BE_DECL_STMT")
            var_decls = [c for c in _inner(init) if c.get("kind") == "VarDecl"]
            if len(var_decls) != 1:
                raise RouteError(f"{language.upper()}_FOR_INIT_SINGLE_VAR_REQUIRED")
            for_var = var_decls[0]
            var_name = str(for_var.get("name", "")).strip()
            if not var_name:
                raise RouteError(f"{language.upper()}_FOR_VAR_NAME_REQUIRED")
            var_type = _canonical_node_type(for_var, language)
            if var_type != "integer":
                raise RouteError(f"{language.upper()}_FOR_NON_INTEGER_TYPE:{var_type}")
            init_children = _inner(for_var)
            if len(init_children) != 1:
                raise RouteError(f"{language.upper()}_FOR_INIT_VALUE_REQUIRED")
            start_expr = _expression(init_children[0], language, source_file, emitted_target, var_type)

            if not isinstance(cond, dict) or cond.get("kind") != "BinaryOperator":
                raise RouteError(f"{language.upper()}_FOR_COND_BINARY_OPERATOR_REQUIRED")
            if cond.get("opcode") != "<":
                raise RouteError(f"{language.upper()}_FOR_COND_OPCODE_MUST_BE_LESS_THAN:{cond.get('opcode')}")
            cond_operands = _inner(cond)
            if len(cond_operands) != 2:
                raise RouteError(f"{language.upper()}_FOR_COND_MALFORMED")
            cond_lhs = _unwrap(cond_operands[0])
            if (
                cond_lhs.get("kind") != "DeclRefExpr"
                or str(cond_lhs.get("referencedDecl", {}).get("name", ""))
                != var_name
            ):
                raise RouteError(f"{language.upper()}_FOR_COND_LHS_MUST_BE_LOOP_VAR")
            end_expr = _expression(cond_operands[1], language, source_file, emitted_target, var_type)

            if not isinstance(inc, dict):
                raise RouteError(f"{language.upper()}_FOR_INC_REQUIRED")
            inc_kind = inc.get("kind")
            step_expr: dict[str, Any] | None = None
            if inc_kind == "UnaryOperator" and inc.get("opcode") == "++":
                step_expr = None
            elif inc_kind == "CompoundAssignOperator" and inc.get("opcode") == "+=":
                inc_operands = _inner(inc)
                if len(inc_operands) != 2:
                    raise RouteError(f"{language.upper()}_FOR_INC_MALFORMED")
                step_expr = _expression(inc_operands[1], language, source_file, emitted_target, var_type)
            elif inc_kind == "BinaryOperator" and inc.get("opcode") == "=":
                inc_operands = _inner(inc)
                if len(inc_operands) != 2:
                    raise RouteError(f"{language.upper()}_FOR_INC_MALFORMED")
                rhs_op = _unwrap(inc_operands[1])
                if rhs_op.get("kind") != "BinaryOperator" or rhs_op.get("opcode") != "+":
                    raise RouteError(f"{language.upper()}_FOR_INC_OP_UNSUPPORTED")
                rhs_children = _inner(rhs_op)
                if len(rhs_children) != 2:
                    raise RouteError(f"{language.upper()}_FOR_INC_MALFORMED")
                step_expr = _expression(rhs_children[1], language, source_file, emitted_target, var_type)
            else:
                raise RouteError(f"{language.upper()}_FOR_INC_UNSUPPORTED:{inc_kind}")

            loop_known = set(known)
            loop_known.add(var_name)
            parsed_body = _statement_body(
                body,
                language,
                source_file,
                emitted_target,
                return_type,
                known_variables=loop_known,
                parameter_names=params,
            )
            for_dict: dict[str, Any] = {
                "kind": "for",
                "name": var_name,
                "type": var_type,
                "start": start_expr,
                "end": end_expr,
                "body": parsed_body,
            }
            if step_expr is not None:
                for_dict["step"] = step_expr
            result.append(_mapped(node, source_file, for_dict))
            continue
        if kind == "BreakStmt":
            result.append(_mapped(node, source_file, {"kind": "break"}))
            continue
        if kind == "ContinueStmt":
            result.append(_mapped(node, source_file, {"kind": "continue"}))
            continue
        raise RouteError(f"{language.upper()}_UNSUPPORTED_STATEMENT:{kind}")
    return result


def _statement_body(
    node: dict[str, Any],
    language: Language,
    source_file: str,
    emitted_target: bool,
    return_type: str,
    known_variables: set[str] | None = None,
    parameter_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    if node.get("kind") == "CompoundStmt":
        return _statements(
            _inner(node),
            language,
            source_file,
            emitted_target,
            return_type,
            known_variables=known_variables,
            parameter_names=parameter_names,
        )
    return _statements(
        [node],
        language,
        source_file,
        emitted_target,
        return_type,
        known_variables=known_variables,
        parameter_names=parameter_names,
    )


def _function(
    node: dict[str, Any],
    language: Language,
    source_file: str,
    emitted_target: bool,
    record_names: set[str] | None = None,
) -> dict[str, Any]:
    parameters = []
    param_names: set[str] = set()
    body: dict[str, Any] | None = None
    for child in _inner(node):
        if child.get("kind") == "ParmVarDecl":
            name = str(child.get("name", "")).strip()
            if not name:
                raise RouteError(f"{language.upper()}_PARAMETER_NAME_REQUIRED")
            param_names.add(name)
            parameters.append(
                _mapped(
                    child,
                    source_file,
                    {"name": name, "type": _canonical_node_type(child, language, record_names)},
                )
            )
        elif child.get("kind") == "CompoundStmt":
            body = child
    if body is None:
        raise RouteError(f"{language.upper()}_FUNCTION_BODY_REQUIRED")
    canonical_return_type = _canonical_type(_return_type(node), language, record_names)
    _verify_integer_return_width(body, language, canonical_return_type)
    return _mapped(
        node,
        source_file,
        {
            "name": str(node["name"]),
            "parameters": parameters,
            "return_type": canonical_return_type,
            "body": _statements(
                _inner(body),
                language,
                source_file,
                emitted_target,
                canonical_return_type,
                known_variables=set(),
                parameter_names=param_names,
            ),
        },
    )


def analyze_clang(
    source: Path,
    language: Language,
    function_name: str,
    executable: str,
    version: str,
    *,
    emitted_target: bool = False,
    sdk_path: str | None = None,
) -> SemanticIR:
    """Lift one named C++/Objective-C function into the semantic IR."""
    if language not in ("cpp", "objc"):
        raise RouteError(f"UNSUPPORTED_SOURCE_LANGUAGE:{language}")
    tree = _run_clang(executable, source, language, sdk_path)
    def _is_in_source_file(node: dict[str, Any]) -> bool:
        loc = node.get("loc")
        if not isinstance(loc, dict):
            return False
        for nested in ("expansionLoc", "spellingLoc"):
            nested_loc = loc.get(nested)
            if isinstance(nested_loc, dict):
                loc = nested_loc
                break
        if "includedFrom" in loc:
            return False
        file_path = loc.get("file")
        if isinstance(file_path, str):
            return Path(file_path).name == source.name
        return True

    candidates = [
        node
        for node in _inner(tree)
        if node.get("kind") == "FunctionDecl"
        and node.get("name") == function_name
        and not node.get("isImplicit")
        and _is_in_source_file(node)
        and any(child.get("kind") == "CompoundStmt" for child in _inner(node))
    ]
    if not candidates:
        raise RouteError(f"FUNCTION_NOT_FOUND:{function_name}")
    if len(candidates) > 1:
        raise RouteError(f"AMBIGUOUS_FUNCTION_DEFINITION:{function_name}")
    semantic_markers = _function_semantic_markers(candidates[0])
    if semantic_markers:
        raise RouteError(
            f"{language.upper()}_FUNCTION_SEMANTIC_MARKERS_OUTSIDE_CERTIFIED_SUBSET:"
            + ",".join(semantic_markers)
        )
    record_candidates = [
        node
        for node in _inner(tree)
        if node.get("kind") in ("CXXRecordDecl", "RecordDecl")
        and node.get("name")
        and not node.get("isImplicit")
        and _is_in_source_file(node)
        and any(child.get("kind") == "FieldDecl" for child in _inner(node))
    ]
    record_names = {str(rec["name"]).strip() for rec in record_candidates}
    records = []
    for rec in record_candidates:
        rec_name = str(rec["name"]).strip()
        fields = []
        for field in _inner(rec):
            if field.get("kind") == "FieldDecl" and not field.get("isImplicit"):
                field_name = str(field.get("name", "")).strip()
                field_type = _canonical_node_type(field, language, record_names)
                fields.append(_mapped(field, source.name, {"name": field_name, "type": field_type}))
        records.append(_mapped(rec, source.name, {"name": rec_name, "fields": fields}))

    mapping: dict[str, Any] = {
        "schema_version": "1.0.0",
        "source_language": language,
        "source_file": source.name,
        "analyzer": "clang AST (JSON)",
        "analyzer_version": version,
        "functions": [_function(candidates[0], language, source.name, emitted_target, record_names)],
        "diagnostics": [],
    }
    if records:
        mapping["records"] = records
    return SemanticIR.from_mapping(mapping)


def _inventory_span(
    node: dict[str, Any],
    source: Path,
) -> dict[str, object] | None:
    try:
        span = _source_span(node, source.name)
    except (KeyError, RouteError, TypeError, ValueError):
        return None
    end_byte = span.get("end_byte")
    if not isinstance(end_byte, int) or end_byte > source.stat().st_size:
        return None
    locations: list[object] = [node.get("loc")]
    source_range = node.get("range")
    if isinstance(source_range, dict):
        locations.extend((source_range.get("begin"), source_range.get("end")))
    for raw_location in locations:
        if not isinstance(raw_location, dict):
            continue
        location = raw_location
        for nested in ("expansionLoc", "spellingLoc"):
            if isinstance(location.get(nested), dict):
                location = location[nested]
                break
        if isinstance(location.get("includedFrom"), dict):
            return None
        explicit_file = location.get("file")
        if isinstance(explicit_file, str) and Path(explicit_file).name != source.name:
            return None
    return span


def _function_semantic_markers(node: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    for child in _inner(node):
        kind = str(child.get("kind", ""))
        if kind == "ParmVarDecl" and (
            child.get("init") is not None or child.get("hasInheritedDefaultArg") is True
        ):
            markers.append("default-argument")
        elif kind.endswith("Attr"):
            markers.append(f"attribute:{kind}")
    for field, marker in (
        ("storageClass", "storage-class"),
        ("inline", "inline"),
        ("constexpr", "constexpr"),
        ("variadic", "variadic"),
    ):
        value = node.get(field)
        if value not in (None, False, ""):
            markers.append(f"{marker}:{value}" if not isinstance(value, bool) else marker)
    return sorted(set(markers))


def _inventory_signature(node: dict[str, Any]) -> dict[str, object]:
    parameters: list[dict[str, object]] = []
    for child in _inner(node):
        if child.get("kind") != "ParmVarDecl":
            continue
        raw_type = child.get("type")
        parameters.append(
            {
                "name": str(child.get("name", "")),
                "source_type": (
                    str(raw_type.get("qualType", "")) if isinstance(raw_type, dict) else ""
                ),
            }
        )
    raw_type = node.get("type")
    storage_class = str(node.get("storageClass", "none"))
    return {
        "parameters": parameters,
        "source_type": str(raw_type.get("qualType", "")) if isinstance(raw_type, dict) else "",
        "storage": storage_class,
        "visibility": "internal" if storage_class == "static" else "external",
        "semantic_markers": _function_semantic_markers(node),
    }


def _inventory_node_is_external(node: dict[str, Any], source: Path) -> bool:
    locations: list[object] = [node.get("loc")]
    source_range = node.get("range")
    if isinstance(source_range, dict):
        locations.extend((source_range.get("begin"), source_range.get("end")))

    def external(location: object) -> bool:
        if not isinstance(location, dict):
            return False
        if isinstance(location.get("includedFrom"), dict):
            return True
        explicit_file = location.get("file")
        if isinstance(explicit_file, str) and Path(explicit_file).name != source.name:
            return True
        return any(
            external(location.get(key))
            for key in ("expansionLoc", "spellingLoc", "includedFrom")
        )

    return any(external(location) for location in locations)


def inventory_clang_module(
    source: Path,
    language: Language,
    executable: str,
    version: str,
    *,
    sdk_path: str | None = None,
) -> dict[str, Any]:
    """Enumerate main-file declarations from clang's type-checked JSON AST."""

    if language not in ("cpp", "objc"):
        raise RouteError(f"UNSUPPORTED_SOURCE_LANGUAGE:{language}")
    tree = _run_clang(executable, source, language, sdk_path)
    subjects: list[dict[str, object]] = []
    diagnostics: list[str] = []
    scope_kinds = {
        "CXXRecordDecl",
        "ClassTemplateDecl",
        "EnumDecl",
        "FunctionTemplateDecl",
        "LinkageSpecDecl",
        "NamespaceDecl",
        "ObjCImplementationDecl",
        "ObjCInterfaceDecl",
        "RecordDecl",
        "TypeAliasDecl",
        "TypedefDecl",
        "VarDecl",
    }

    def visit(node: dict[str, Any], scope: tuple[str, ...], *, top_level: bool) -> None:
        kind = str(node.get("kind", ""))
        name = str(node.get("name", "")).strip()
        span = _inventory_span(node, source)
        explicit_declaration = (
            kind != "TranslationUnitDecl"
            and kind.endswith("Decl")
            and not node.get("isImplicit")
        )
        if span is not None and explicit_declaration:
            if kind == "FunctionDecl" and name:
                has_body = any(child.get("kind") == "CompoundStmt" for child in _inner(node))
                semantic_markers = _function_semantic_markers(node)
                unsupported_markers = [
                    marker
                    for marker in semantic_markers
                    if marker != "storage-class:static"
                ]
                qualified_name = "::".join((*scope, name))
                subjects.append(
                    {
                        "name": name,
                        "qualified_name": qualified_name,
                        "declaration_kind": kind,
                        "analyzable": (
                            kind == "FunctionDecl"
                            and top_level
                            and has_body
                            and not unsupported_markers
                        ),
                        "source_span": span,
                        "signature": _inventory_signature(node),
                    }
                )
            else:
                obligation_name = name or f"<{kind}>"
                subjects.append(
                    {
                        "name": obligation_name,
                        "qualified_name": "::".join((*scope, obligation_name)),
                        "declaration_kind": kind,
                        "analyzable": False,
                        "source_span": span,
                        "signature": _inventory_signature(node),
                    }
                )
        elif (
            explicit_declaration
            and top_level
            and not _inventory_node_is_external(node, source)
        ):
            diagnostics.append(
                f"MAIN_FILE_DECLARATION_SPAN_INVALID:{kind}:{name or '<unnamed>'}"
            )
        child_scope = (*scope, name) if name and kind in scope_kinds else scope
        for child in _inner(node):
            if kind == "TranslationUnitDecl":
                visit(child, scope, top_level=True)
            elif kind in scope_kinds:
                visit(child, child_scope, top_level=False)

    visit(tree, (), top_level=True)
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-inventory",
        "profile": "typed-pure-module-v1",
        "source_language": language,
        "source_file": source.name,
        "analyzer": "clang AST (JSON)",
        "analyzer_version": version,
        "enumeration_status": "PASSED" if not diagnostics else "FAILED",
        "subjects": subjects,
        "diagnostics": sorted(set(diagnostics)),
    }
