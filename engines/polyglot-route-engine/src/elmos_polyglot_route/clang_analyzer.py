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
from pathlib import Path
from typing import Any

from .models import Language, RouteError, SemanticIR

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

#: Canonical type per resolved clang type name, after `const`/`&` stripping.
#: `short`/`int`/`long` widen to the canonical 64-bit integer exactly; only
#: 32-bit overflow wraparound differs, which is the same documented boundary
#: the Java and C# analyzers carry.
_INTEGER_TYPES = frozenset(
    {
        "short",
        "int",
        "long",
        "long long",
        "int16_t",
        "int32_t",
        "int64_t",
        "std::int16_t",
        "std::int32_t",
        "std::int64_t",
        "NSInteger",
    }
)
_STRING_TYPES = frozenset({"std::string", "string", "NSString *", "NSString"})
_BOOLEAN_TYPES = frozenset({"bool", "BOOL", "signed char"})

_OPERATOR_METHOD = re.compile(r"^operator(==|!=|\+|-|\*|/|%|<=|>=|<|>)$")


def _run_clang(executable: str, source: Path, language: Language) -> dict[str, Any]:
    mode = "c++" if language == "cpp" else "objective-c"
    standard = "-std=c++17" if language == "cpp" else "-std=c17"
    command = [
        executable,
        "-x",
        mode,
        standard,
        "-Xclang",
        "-ast-dump=json",
        "-fsyntax-only",
        str(source),
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=120)
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
    cleaned = type_name.replace("const", " ").replace("&", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned.endswith(" *"):
        return cleaned
    return cleaned.replace(" *", " *").strip()


def _canonical_type(type_name: str, language: Language) -> str:
    cleaned = _strip(type_name)
    if cleaned in _INTEGER_TYPES:
        return "integer"
    if cleaned == "double":
        return "number"
    if cleaned in _BOOLEAN_TYPES:
        return "boolean"
    if cleaned in _STRING_TYPES:
        return "string"
    if cleaned == "float":
        raise RouteError(f"{language.upper()}_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET:{type_name}")
    raise RouteError(f"{language.upper()}_UNSUPPORTED_TYPE:{type_name}")


def _qual_type(node: dict[str, Any]) -> str:
    value = node.get("type")
    if not isinstance(value, dict) or "qualType" not in value:
        raise RouteError("CLANG_NODE_WITHOUT_TYPE")
    return str(value["qualType"])


def _return_type(function: dict[str, Any]) -> str:
    signature = _qual_type(function)
    head = signature.split("(")[0].strip()
    if not head:
        raise RouteError("CLANG_UNREADABLE_RETURN_TYPE")
    return head


def _inner(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in node.get("inner", []) if isinstance(item, dict)]


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


def _expression(node: dict[str, Any], language: Language) -> dict[str, Any]:
    node = _unwrap(node)
    kind = node.get("kind")

    if kind == "DeclRefExpr":
        referenced = node.get("referencedDecl")
        if not isinstance(referenced, dict) or not referenced.get("name"):
            raise RouteError("CLANG_UNRESOLVED_NAME")
        return {"kind": "name", "value": str(referenced["name"])}

    if kind == "IntegerLiteral":
        return {"kind": "literal", "value": int(str(node["value"]))}
    if kind == "FloatingLiteral":
        return {"kind": "literal", "value": float(str(node["value"]))}
    if kind in ("CXXBoolLiteralExpr", "ObjCBoolLiteralExpr"):
        return {"kind": "literal", "value": bool(node.get("value"))}
    if kind == "StringLiteral":
        return {"kind": "literal", "value": json.loads(str(node["value"]))}
    if kind == "ObjCStringLiteral":
        children = _inner(node)
        if len(children) == 1:
            return _expression(children[0], language)

    if kind == "BinaryOperator":
        operator = str(node.get("opcode", ""))
        if operator not in _BINARY_OPERATORS:
            raise RouteError(f"{language.upper()}_UNSUPPORTED_OPERATOR:{operator}")
        operands = _inner(node)
        if len(operands) != 2:
            raise RouteError("CLANG_MALFORMED_BINARY_OPERATOR")
        if operator in ("==", "!=") and language == "objc":
            left_type = _strip(_qual_type(_unwrap(operands[0])))
            if left_type in _STRING_TYPES:
                # Pointer identity, not value equality -- see the module
                # docstring.
                raise RouteError("OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET")
        return {
            "kind": "binary",
            "operator": operator,
            "left": _expression(operands[0], language),
            "right": _expression(operands[1], language),
        }

    if kind == "CXXOperatorCallExpr":
        children = _inner(node)
        if len(children) == 3:
            callee = _unwrap(children[0])
            referenced = callee.get("referencedDecl")
            name = str(referenced.get("name", "")) if isinstance(referenced, dict) else ""
            match = _OPERATOR_METHOD.match(name)
            if match:
                return {
                    "kind": "binary",
                    "operator": match.group(1),
                    "left": _expression(children[1], language),
                    "right": _expression(children[2], language),
                }

    if kind == "ObjCMessageExpr":
        lifted = _string_message(node)
        if lifted is not None:
            operator, left, right = lifted
            return {
                "kind": "binary",
                "operator": operator,
                "left": _expression(left, language),
                "right": _expression(right, language),
            }

    raise RouteError(f"{language.upper()}_UNSUPPORTED_EXPRESSION:{kind}")


def _statements(nodes: list[dict[str, Any]], language: Language) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        kind = node.get("kind")
        if kind == "ReturnStmt":
            children = _inner(node)
            if len(children) != 1:
                raise RouteError("CLANG_RETURN_WITHOUT_VALUE")
            result.append({"kind": "return", "expression": _expression(children[0], language)})
            continue
        if kind == "IfStmt":
            children = _inner(node)
            if node.get("hasInit") or node.get("isConstexpr") or len(children) < 2:
                raise RouteError(f"{language.upper()}_UNSUPPORTED_STATEMENT:IfStmt")
            condition, then_branch = children[0], children[1]
            else_branch = children[2] if node.get("hasElse") and len(children) > 2 else None
            result.append(
                {
                    "kind": "if",
                    "condition": _expression(condition, language),
                    "then": _statement_body(then_branch, language),
                    "else": _statement_body(else_branch, language) if else_branch else [],
                }
            )
            continue
        raise RouteError(f"{language.upper()}_UNSUPPORTED_STATEMENT:{kind}")
    return result


def _statement_body(node: dict[str, Any], language: Language) -> list[dict[str, Any]]:
    if node.get("kind") == "CompoundStmt":
        return _statements(_inner(node), language)
    return _statements([node], language)


def _function(node: dict[str, Any], language: Language) -> dict[str, Any]:
    parameters = []
    body: dict[str, Any] | None = None
    for child in _inner(node):
        if child.get("kind") == "ParmVarDecl":
            name = str(child.get("name", "")).strip()
            if not name:
                raise RouteError(f"{language.upper()}_PARAMETER_NAME_REQUIRED")
            parameters.append(
                {"name": name, "type": _canonical_type(_qual_type(child), language)}
            )
        elif child.get("kind") == "CompoundStmt":
            body = child
    if body is None:
        raise RouteError(f"{language.upper()}_FUNCTION_BODY_REQUIRED")
    return {
        "name": str(node["name"]),
        "parameters": parameters,
        "return_type": _canonical_type(_return_type(node), language),
        "body": _statements(_inner(body), language),
    }


def analyze_clang(
    source: Path,
    language: Language,
    function_name: str,
    executable: str,
    version: str,
) -> SemanticIR:
    """Lift one named C++/Objective-C function into the semantic IR."""
    if language not in ("cpp", "objc"):
        raise RouteError(f"UNSUPPORTED_SOURCE_LANGUAGE:{language}")
    tree = _run_clang(executable, source, language)
    candidates = [
        node
        for node in _inner(tree)
        if node.get("kind") == "FunctionDecl"
        and node.get("name") == function_name
        and not node.get("isImplicit")
        and any(child.get("kind") == "CompoundStmt" for child in _inner(node))
    ]
    if not candidates:
        raise RouteError(f"FUNCTION_NOT_FOUND:{function_name}")
    if len(candidates) > 1:
        raise RouteError(f"AMBIGUOUS_FUNCTION_DEFINITION:{function_name}")
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": language,
            "source_file": source.name,
            "analyzer": "clang AST (JSON)",
            "analyzer_version": version,
            "functions": [_function(candidates[0], language)],
            "diagnostics": [],
        }
    )
