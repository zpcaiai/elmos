"""Fail-closed Visual Basic 6.0 frontend for the bounded pure-function IR.

This is intentionally not a VB6 compiler.  It recognizes a small, explicit
module profile that is useful for deterministic repository migration while the
real VB6 compiler/runtime remains a Windows-only external evidence gate.
Forms, class modules, COM/ActiveX, ADO, default properties, ByRef parameters,
implicit variants and error handling are rejected rather than guessed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import types
from .models import RouteError, SemanticIR

ANALYZER_NAME = "elmos-vb6-bounded-parser"
ANALYZER_VERSION = "1.0.0;dialect=visual-basic-6.0;profile=typed-pure-module-v1"
MAX_SOURCE_BYTES = 2_000_000

_TYPE_MAP = {
    "long": "integer",
    "double": "number",
    "boolean": "boolean",
    "string": "string",
}
_FUNCTION_HEADER = re.compile(
    r"^\s*(?:(Public|Private|Friend)\s+)?(?:(Static)\s+)?Function\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s+As\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*$",
    re.IGNORECASE,
)
_END_FUNCTION = re.compile(r"^\s*End\s+Function\s*$", re.IGNORECASE)
_PARAMETER = re.compile(
    r"^\s*ByVal\s+([A-Za-z_][A-Za-z0-9_]*)\s+As\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*$",
    re.IGNORECASE,
)
_DIM = re.compile(
    r"^\s*Dim\s+([A-Za-z_][A-Za-z0-9_]*)\s+As\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*$",
    re.IGNORECASE,
)
_ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")
_IF = re.compile(r"^\s*If\s+(.+?)\s+Then\s*$", re.IGNORECASE)
_ELSE = re.compile(r"^\s*Else\s*$", re.IGNORECASE)
_END_IF = re.compile(r"^\s*End\s+If\s*$", re.IGNORECASE)
_WHILE = re.compile(r"^\s*While\s+(.+?)\s*$", re.IGNORECASE)
_WEND = re.compile(r"^\s*Wend\s*$", re.IGNORECASE)
_OPTION_EXPLICIT = re.compile(r"^\s*Option\s+Explicit\s*$", re.IGNORECASE)
_ATTRIBUTE_NAME = re.compile(r'^\s*Attribute\s+VB_Name\s*=\s*"[^"]+"\s*$', re.IGNORECASE)
_COMMENT_ONLY = re.compile(r"^\s*(?:'.*)?$")


@dataclass(frozen=True)
class _Line:
    number: int
    text: str
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    start: int
    end: int


def _decode_source(content: bytes) -> tuple[str, str]:
    """Decode the two source encodings admitted by the bounded adapter."""

    if content.startswith(b"\xef\xbb\xbf"):
        try:
            return content[3:].decode("utf-8"), "utf-8-sig"
        except UnicodeDecodeError as error:
            raise RouteError("VB6_SOURCE_ENCODING_INVALID:utf-8-sig") from error
    try:
        return content.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        try:
            return content.decode("cp1252"), "windows-1252"
        except UnicodeDecodeError as error:
            raise RouteError("VB6_SOURCE_ENCODING_UNSUPPORTED") from error


def _lines(text: str, encoding: str) -> list[_Line]:
    result: list[_Line] = []
    prefix = 3 if encoding == "utf-8-sig" else 0
    offset = prefix
    for number, raw in enumerate(text.splitlines(keepends=True), start=1):
        without_eol = raw.rstrip("\r\n")
        encoded = raw.encode("utf-8" if encoding == "utf-8-sig" else encoding)
        content_encoded = without_eol.encode("utf-8" if encoding == "utf-8-sig" else encoding)
        result.append(_Line(number, without_eol, offset, offset + len(content_encoded)))
        offset += len(encoded)
    if text and not result:
        encoded = text.encode("utf-8" if encoding == "utf-8-sig" else encoding)
        result.append(_Line(1, text, offset, offset + len(encoded)))
    return result


def _span(source: Path, start: int, end: int) -> dict[str, Any]:
    if end <= start:
        end = start + 1
    return {"file": source.name, "start_byte": start, "end_byte": end}


def _strip_comment(line: str) -> str:
    """Remove a VB apostrophe comment without treating apostrophes in strings as comments."""

    in_string = False
    index = 0
    while index < len(line):
        character = line[index]
        if character == '"':
            if in_string and index + 1 < len(line) and line[index + 1] == '"':
                index += 2
                continue
            in_string = not in_string
        elif character == "'" and not in_string:
            return line[:index]
        index += 1
    if in_string:
        raise RouteError("VB6_UNTERMINATED_STRING_LITERAL")
    return line


def _split_parameters(value: str) -> list[str]:
    if not value.strip():
        return []
    # The bounded profile admits no arrays, defaults or nested type syntax, so
    # a comma is always a parameter separator.  Refuse line continuations and
    # optional/default parameter syntax before splitting.
    if re.search(r"\s_\s*$", value) or "=" in value or "(" in value or ")" in value:
        raise RouteError("VB6_PARAMETER_SHAPE_OUTSIDE_CERTIFIED_SUBSET")
    return value.split(",")


def _canonical_type(value: str, *, context: str) -> str:
    result = _TYPE_MAP.get(value.casefold())
    if result is None:
        if value.casefold() in {"variant", "object", "currency", "date", "decimal", "integer", "byte"}:
            raise RouteError(f"VB6_TYPE_OUTSIDE_CERTIFIED_SUBSET:{context}:{value}")
        raise RouteError(f"VB6_UNSUPPORTED_TYPE:{context}:{value}")
    return result


_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<number>(?:[0-9]+\.[0-9]*(?:[Ee][+-]?[0-9]+)?|[0-9]+[Ee][+-]?[0-9]+|[0-9]+)(?:[&#!])?)|"
    r'(?P<string>"(?:[^"]|"")*")|'
    r"(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)|"
    r"(?P<operator><=|>=|<>|[=<>+\-*/\\&(),])"
    r")"
)


def _tokens(text: str, line: _Line, encoding: str) -> list[_Token]:
    tokens: list[_Token] = []
    cursor = 0
    byte_encoding = "utf-8" if encoding == "utf-8-sig" else encoding
    expression_column = line.text.find(text)
    if expression_column < 0:
        raise RouteError(f"VB6_EXPRESSION_SOURCE_SPAN_UNRESOLVED:line={line.number}")
    expression_start = line.start_byte + len(line.text[:expression_column].encode(byte_encoding))
    while cursor < len(text):
        match = _TOKEN.match(text, cursor)
        if match is None:
            raise RouteError(f"VB6_UNSUPPORTED_EXPRESSION_TOKEN:line={line.number}:column={cursor + 1}")
        if match.end() == cursor:
            raise RouteError("VB6_EXPRESSION_TOKENIZER_STALLED")
        kind = match.lastgroup
        assert kind is not None
        raw = match.group(kind)
        token_start_chars = match.start(kind)
        token_end_chars = match.end(kind)
        start = expression_start + len(text[:token_start_chars].encode(byte_encoding))
        end = expression_start + len(text[:token_end_chars].encode(byte_encoding))
        tokens.append(_Token(kind, raw, start, end))
        cursor = match.end()
    return tokens


class _ExpressionParser:
    def __init__(
        self,
        tokens: list[_Token],
        source: Path,
        names: dict[str, str],
        function_names: dict[str, str],
        emitted_target: bool,
    ) -> None:
        self.tokens = tokens
        self.source = source
        self.names = names
        self.function_names = function_names
        self.emitted_target = emitted_target
        self.index = 0

    def parse(self) -> dict[str, Any]:
        if not self.tokens:
            raise RouteError("VB6_EXPRESSION_REQUIRED")
        expression = self._parse_comparison()
        if self.index != len(self.tokens):
            raise RouteError(f"VB6_UNEXPECTED_EXPRESSION_TOKEN:{self.tokens[self.index].value}")
        return expression

    def _peek(self, value: str | None = None) -> _Token | None:
        if self.index >= len(self.tokens):
            return None
        token = self.tokens[self.index]
        if value is None or token.value.casefold() == value.casefold():
            return token
        return None

    def _take(self, value: str | None = None) -> _Token:
        token = self._peek(value)
        if token is None:
            expected = value if value is not None else "token"
            raise RouteError(f"VB6_EXPRESSION_TOKEN_REQUIRED:{expected}")
        self.index += 1
        return token

    def _binary(self, left: dict[str, Any], operator: str, right: dict[str, Any]) -> dict[str, Any]:
        left_span = left["source_span"]
        right_span = right["source_span"]
        return {
            "kind": "binary",
            "operator": operator,
            "left": left,
            "right": right,
            "source_span": _span(self.source, left_span["start_byte"], right_span["end_byte"]),
        }

    def _parse_comparison(self) -> dict[str, Any]:
        left = self._parse_concat()
        token = self._peek()
        if token is not None and token.value in {"=", "<>", "<", "<=", ">", ">="}:
            self.index += 1
            right = self._parse_concat()
            left = self._binary(left, {"=": "==", "<>": "!="}.get(token.value, token.value), right)
            following = self._peek()
            if following is not None and following.value in {"=", "<>", "<", "<=", ">", ">="}:
                raise RouteError("VB6_CHAINED_COMPARISON_OUTSIDE_CERTIFIED_SUBSET")
        return left

    def _parse_concat(self) -> dict[str, Any]:
        left = self._parse_additive()
        while self._peek("&") is not None:
            self.index += 1
            left = self._binary(left, "+", self._parse_additive())
        return left

    def _parse_additive(self) -> dict[str, Any]:
        left = self._parse_multiplicative()
        while self._peek("+") is not None or self._peek("-") is not None:
            operator = self._take().value
            left = self._binary(left, operator, self._parse_multiplicative())
        return left

    def _parse_multiplicative(self) -> dict[str, Any]:
        left = self._parse_primary()
        while True:
            token = self._peek()
            if token is None:
                break
            folded = token.value.casefold()
            if token.value not in {"*", "/", "\\"} and folded != "mod":
                break
            self.index += 1
            operator = "%" if folded == "mod" else "/" if token.value == "\\" else token.value
            left = self._binary(left, operator, self._parse_primary())
        return left

    def _parse_primary(self) -> dict[str, Any]:
        token = self._take()
        if token.value in {"+", "-"}:
            operand = self._take()
            if operand.kind != "number":
                raise RouteError("VB6_UNARY_SIGN_ON_EXPRESSION_OUTSIDE_CERTIFIED_SUBSET")
            token = _Token(operand.kind, token.value + operand.value, token.start, operand.end)
        if token.kind == "number":
            raw = token.value
            suffix = raw[-1] if raw and raw[-1] in "&#!" else ""
            value_text = raw[:-1] if suffix else raw
            try:
                numeric_value: int | float = (
                    float(value_text)
                    if "." in value_text or "e" in value_text.casefold() or suffix in {"#", "!"}
                    else int(value_text)
                )
            except ValueError as error:
                raise RouteError(f"VB6_INVALID_NUMERIC_LITERAL:{raw}") from error
            return {
                "kind": "literal",
                "value": numeric_value,
                "source_span": _span(self.source, token.start, token.end),
            }
        if token.kind == "string":
            string_value = token.value[1:-1].replace('""', '"')
            return {
                "kind": "literal",
                "value": string_value,
                "source_span": _span(self.source, token.start, token.end),
            }
        if token.value == "(":
            expression = self._parse_comparison()
            closing = self._take(")")
            expression["source_span"] = _span(self.source, token.start, closing.end)
            return expression
        if token.kind != "identifier":
            raise RouteError(f"VB6_UNSUPPORTED_EXPRESSION:{token.value}")
        folded = token.value.casefold()
        if folded in {"true", "false"}:
            return {
                "kind": "literal",
                "value": folded == "true",
                "source_span": _span(self.source, token.start, token.end),
            }
        if folded in {"and", "or", "not", "xor", "eqv", "imp", "is", "like"}:
            raise RouteError(f"VB6_BOOLEAN_OR_PATTERN_OPERATOR_OUTSIDE_CERTIFIED_SUBSET:{token.value}")
        if self._peek("(") is not None:
            self.index += 1
            arguments: list[dict[str, Any]] = []
            if self._peek(")") is None:
                while True:
                    arguments.append(self._parse_comparison())
                    if self._peek(",") is None:
                        break
                    self.index += 1
            closing = self._take(")")
            helpers = {
                "elmoscheckedadd": "+",
                "elmoscheckedsub": "-",
                "elmoscheckedmul": "*",
                "elmoscheckeddiv": "/",
                "elmoscheckedmod": "%",
            }
            if self.emitted_target and folded in helpers and len(arguments) == 2:
                expression = self._binary(arguments[0], helpers[folded], arguments[1])
                expression["source_span"] = _span(self.source, token.start, closing.end)
                return expression
            if self.emitted_target and folded == "elmosnonzero" and len(arguments) == 1:
                argument = arguments[0]
                argument["source_span"] = _span(self.source, token.start, closing.end)
                return argument
            if folded not in self.function_names:
                raise RouteError(f"VB6_EFFECTFUL_OR_UNKNOWN_CALL_OUTSIDE_CERTIFIED_SUBSET:{token.value}")
            # The route engine currently lowers one selected declaration at a
            # time. Admitting an intra-module call here would produce an IR
            # whose callee signature is absent and would falsely imply that
            # repository assembly had resolved that dependency. Keep it an
            # explicit repository-level gap until module IR is introduced.
            del arguments, closing
            raise RouteError(f"VB6_CROSS_FUNCTION_CALL_REQUIRES_MODULE_IR:{token.value}")
        name = self.names.get(folded)
        if name is None:
            raise RouteError(f"VB6_UNDECLARED_NAME:{token.value}")
        return {"kind": "name", "value": name, "source_span": _span(self.source, token.start, token.end)}


def _expression(
    text: str,
    line: _Line,
    source: Path,
    encoding: str,
    names: dict[str, str],
    function_names: dict[str, str],
    emitted_target: bool,
) -> dict[str, Any]:
    parser = _ExpressionParser(
        _tokens(text, line, encoding), source, names, function_names, emitted_target
    )
    return parser.parse()


def _default_literal(canonical_type: str, line: _Line, source: Path) -> dict[str, Any]:
    value: object = {
        "integer": 0,
        "number": 0.0,
        "boolean": False,
        "string": "",
    }[canonical_type]
    return {"kind": "literal", "value": value, "source_span": _span(source, line.start_byte, line.end_byte)}


def _reject_vb6_semantic_drift(ir: SemanticIR, source_bytes: bytes) -> None:
    """Reject source spellings whose VB6 meaning differs from canonical IR."""

    def visit(expression: Any, environment: dict[str, str]) -> None:
        if expression.kind != "binary" or expression.left is None or expression.right is None:
            for argument in expression.call_arguments:
                visit(argument, environment)
            return
        left_type = types.infer(expression.left, environment, functions_env=functions)
        right_type = types.infer(expression.right, environment, functions_env=functions)
        if expression.left.source_span is None or expression.right.source_span is None:
            raise RouteError("VB6_EXPRESSION_SOURCE_SPAN_REQUIRED")
        operator_bytes = source_bytes[
            expression.left.source_span.end_byte : expression.right.source_span.start_byte
        ]
        expression_bytes = (
            source_bytes[expression.source_span.start_byte : expression.source_span.end_byte]
            if expression.source_span is not None
            else operator_bytes
        ).lower()
        if expression.operator == "/" and left_type == right_type == "integer":
            if b"\\" not in operator_bytes and b"elmoscheckeddiv" not in expression_bytes:
                raise RouteError("VB6_FLOAT_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET")
        if expression.operator == "%" and (left_type != "integer" or right_type != "integer"):
            raise RouteError("VB6_MOD_COERCION_OUTSIDE_CERTIFIED_SUBSET")
        if expression.operator == "+" and left_type == right_type == "string":
            if b"&" not in operator_bytes:
                raise RouteError("VB6_PLUS_STRING_COERCION_OUTSIDE_CERTIFIED_SUBSET")
        visit(expression.left, environment)
        visit(expression.right, environment)

    functions = {function.name: function for function in ir.functions}
    def visit_statements(statements: tuple[Any, ...], environment: dict[str, str]) -> None:
        for statement in statements:
            if statement.expression is not None:
                visit(statement.expression, environment)
            if statement.condition is not None:
                visit(statement.condition, environment)
            if statement.start is not None:
                visit(statement.start, environment)
            if statement.end is not None:
                visit(statement.end, environment)
            if statement.step is not None:
                visit(statement.step, environment)
            if statement.kind == "let" and statement.name and statement.declared_type:
                environment[statement.name] = statement.declared_type
            if statement.then_body:
                visit_statements(statement.then_body, dict(environment))
            if statement.else_body:
                visit_statements(statement.else_body, dict(environment))
            if statement.body:
                visit_statements(statement.body, dict(environment))

    for function in ir.functions:
        environment = {parameter.name: parameter.type for parameter in function.parameters}
        visit_statements(function.body, environment)


def _analyze_function(
    source: Path,
    lines: list[_Line],
    start_index: int,
    end_index: int,
    header: re.Match[str],
    encoding: str,
    function_names: dict[str, str],
    emitted_target: bool,
) -> dict[str, Any]:
    function_name = header.group(3)
    return_type = _canonical_type(header.group(5), context=f"function:{function_name}")
    parameters: list[dict[str, Any]] = []
    names: dict[str, str] = {}
    for raw_parameter in _split_parameters(header.group(4)):
        match = _PARAMETER.fullmatch(raw_parameter)
        if match is None:
            if re.search(r"\bByRef\b", raw_parameter, re.IGNORECASE) or not re.search(
                r"\bByVal\b", raw_parameter, re.IGNORECASE
            ):
                raise RouteError(f"VB6_BYREF_PARAMETER_OUTSIDE_CERTIFIED_SUBSET:{function_name}")
            raise RouteError(f"VB6_PARAMETER_SHAPE_OUTSIDE_CERTIFIED_SUBSET:{function_name}")
        name = match.group(1)
        folded = name.casefold()
        if folded in names:
            raise RouteError(f"VB6_DUPLICATE_PARAMETER_CASE_INSENSITIVE:{name}")
        canonical_type = _canonical_type(match.group(2), context=f"parameter:{function_name}.{name}")
        names[folded] = name
        parameters.append({"name": name, "type": canonical_type})

    body_lines = lines[start_index + 1 : end_index]

    def parse_block(index: int, terminators: tuple[re.Pattern[str], ...]) -> tuple[list[dict[str, Any]], int]:
        statements: list[dict[str, Any]] = []
        while index < len(body_lines):
            line = body_lines[index]
            raw = _strip_comment(line.text).strip()
            if not raw:
                index += 1
                continue
            if any(pattern.fullmatch(raw) for pattern in terminators):
                return statements, index
            lowered = raw.casefold()
            if ":" in raw:
                raise RouteError(f"VB6_COLON_STATEMENTS_OUTSIDE_CERTIFIED_SUBSET:line={line.number}")
            if lowered.startswith(("on error", "resume", "err.", "declare ", "set ", "with ", "redim ", "erase ")):
                raise RouteError(f"VB6_EFFECT_OR_ERROR_SEMANTICS_OUTSIDE_CERTIFIED_SUBSET:line={line.number}")
            if lowered.startswith(("for ", "do ", "select ", "goto ", "gosub ", "raiseevent ", "call ")):
                raise RouteError(f"VB6_CONTROL_OR_EFFECT_SEMANTICS_OUTSIDE_CERTIFIED_SUBSET:line={line.number}")
            match = _DIM.fullmatch(raw)
            if match is not None:
                name = match.group(1)
                folded = name.casefold()
                if folded in names:
                    raise RouteError(f"VB6_LOCAL_NAME_ALREADY_BOUND:{name}")
                canonical_type = _canonical_type(match.group(2), context=f"local:{function_name}.{name}")
                names[folded] = name
                statements.append(
                    {
                        "kind": "let",
                        "name": name,
                        "type": canonical_type,
                        "expression": _default_literal(canonical_type, line, source),
                        "source_span": _span(source, line.start_byte, line.end_byte),
                    }
                )
                index += 1
                continue
            match = _IF.fullmatch(raw)
            if match is not None:
                condition_text = match.group(1)
                condition = _expression(
                    condition_text, line, source, encoding, names, function_names, emitted_target
                )
                then_body, stop = parse_block(index + 1, (_ELSE, _END_IF))
                if stop >= len(body_lines):
                    raise RouteError(f"VB6_END_IF_REQUIRED:line={line.number}")
                else_body: list[dict[str, Any]] = []
                if _ELSE.fullmatch(_strip_comment(body_lines[stop].text).strip()):
                    else_body, stop = parse_block(stop + 1, (_END_IF,))
                    if stop >= len(body_lines):
                        raise RouteError(f"VB6_END_IF_REQUIRED:line={line.number}")
                end_line = body_lines[stop]
                statements.append(
                    {
                        "kind": "if",
                        "condition": condition,
                        "then": then_body,
                        "else": else_body,
                        "source_span": _span(source, line.start_byte, end_line.end_byte),
                    }
                )
                index = stop + 1
                continue
            match = _WHILE.fullmatch(raw)
            if match is not None:
                condition = _expression(
                    match.group(1), line, source, encoding, names, function_names, emitted_target
                )
                loop_body, stop = parse_block(index + 1, (_WEND,))
                if stop >= len(body_lines):
                    raise RouteError(f"VB6_WEND_REQUIRED:line={line.number}")
                statements.append(
                    {
                        "kind": "while",
                        "condition": condition,
                        "body": loop_body,
                        "source_span": _span(source, line.start_byte, body_lines[stop].end_byte),
                    }
                )
                index = stop + 1
                continue
            match = _ASSIGN.fullmatch(raw)
            if match is not None:
                raw_name = match.group(1)
                expression_text = match.group(2)
                canonical_name = names.get(raw_name.casefold())
                is_return = raw_name.casefold() == function_name.casefold()
                if canonical_name is None and not is_return:
                    raise RouteError(f"VB6_ASSIGNMENT_TARGET_NOT_DECLARED:{raw_name}")
                if canonical_name is not None and canonical_name.casefold() in {
                    parameter["name"].casefold() for parameter in parameters
                }:
                    raise RouteError(f"VB6_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{raw_name}")
                # `+` is not a reliable string concatenation operator in VB6;
                # the exact string spelling is `&`.  Reject a string `+` after
                # type checking below if it entered as arithmetic syntax.
                expression = _expression(
                    expression_text, line, source, encoding, names, function_names, emitted_target
                )
                statements.append(
                    {
                        "kind": "return" if is_return else "assign",
                        **({} if is_return else {"name": canonical_name}),
                        "expression": expression,
                        "source_span": _span(source, line.start_byte, line.end_byte),
                    }
                )
                index += 1
                continue
            if lowered == "exit function":
                # A generated target writes this immediately after assigning
                # the function result. It adds no semantic node.
                if not statements or statements[-1].get("kind") != "return":
                    raise RouteError(f"VB6_EXIT_FUNCTION_WITHOUT_RETURN:line={line.number}")
                index += 1
                continue
            raise RouteError(f"VB6_UNSUPPORTED_STATEMENT:line={line.number}:{raw[:80]}")
        return statements, index

    body, consumed = parse_block(0, ())
    if consumed != len(body_lines) or not body:
        raise RouteError(f"VB6_FUNCTION_BODY_INVALID:{function_name}")
    def has_return(statements: list[dict[str, Any]]) -> bool:
        return any(
            statement["kind"] == "return"
            or has_return(statement.get("then", []))
            or has_return(statement.get("else", []))
            or has_return(statement.get("body", []))
            for statement in statements
        )

    if not has_return(body):
        raise RouteError(f"VB6_FUNCTION_RETURN_REQUIRED:{function_name}")
    return {
        "name": function_name,
        "parameters": parameters,
        "return_type": return_type,
        "body": body,
        "source_span": _span(source, lines[start_index].start_byte, lines[end_index].end_byte),
    }


def _module_functions(source: Path, content: bytes) -> tuple[list[_Line], str, list[tuple[int, int, re.Match[str]]]]:
    if len(content) > MAX_SOURCE_BYTES:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    text, encoding = _decode_source(content)
    lines = _lines(text, encoding)
    option_explicit = False
    functions: list[tuple[int, int, re.Match[str]]] = []
    index = 0
    while index < len(lines):
        raw = _strip_comment(lines[index].text).strip()
        if not raw:
            index += 1
            continue
        if _OPTION_EXPLICIT.fullmatch(raw):
            if functions:
                raise RouteError("VB6_OPTION_EXPLICIT_MUST_PRECEDE_DECLARATIONS")
            option_explicit = True
            index += 1
            continue
        if _ATTRIBUTE_NAME.fullmatch(raw):
            if functions:
                raise RouteError("VB6_ATTRIBUTE_MUST_PRECEDE_DECLARATIONS")
            index += 1
            continue
        header = _FUNCTION_HEADER.fullmatch(raw)
        if header is None:
            if re.search(r"\b(Sub|Property|Type|Enum|Declare|Event)\b", raw, re.IGNORECASE):
                raise RouteError(f"VB6_MODULE_DECLARATION_OUTSIDE_CERTIFIED_SUBSET:line={lines[index].number}")
            raise RouteError(f"VB6_TOP_LEVEL_STATEMENT_OUTSIDE_CERTIFIED_SUBSET:line={lines[index].number}")
        cursor = index + 1
        while cursor < len(lines) and not _END_FUNCTION.fullmatch(_strip_comment(lines[cursor].text).strip()):
            cursor += 1
        if cursor >= len(lines):
            raise RouteError(f"VB6_END_FUNCTION_REQUIRED:{header.group(3)}")
        functions.append((index, cursor, header))
        index = cursor + 1
    if not option_explicit:
        raise RouteError("VB6_OPTION_EXPLICIT_REQUIRED")
    if not functions:
        raise RouteError("VB6_FUNCTION_NOT_FOUND")
    return lines, encoding, functions


def analyze_vb6(source: Path, function_name: str, *, emitted_target: bool = False) -> SemanticIR:
    if source.suffix.casefold() != ".bas":
        raise RouteError(f"VB6_MODULE_KIND_OUTSIDE_CERTIFIED_SUBSET:{source.suffix.casefold() or '<none>'}")
    before = source.stat(follow_symlinks=False)
    content = source.read_bytes()
    after = source.stat(follow_symlinks=False)
    if source.is_symlink() or not source.is_file() or before.st_size != after.st_size or content != source.read_bytes():
        raise RouteError("VB6_SOURCE_CHANGED_DURING_READ")
    lines, encoding, declarations = _module_functions(source, content)
    function_names: dict[str, str] = {}
    for _, _, header in declarations:
        name = header.group(3)
        folded = name.casefold()
        if folded in function_names:
            raise RouteError(f"VB6_DUPLICATE_FUNCTION_CASE_INSENSITIVE:{name}")
        function_names[folded] = name
    selected = [item for item in declarations if item[2].group(3).casefold() == function_name.casefold()]
    if len(selected) != 1:
        raise RouteError(f"VB6_FUNCTION_NOT_FOUND:{function_name}")
    start, end, header = selected[0]
    function = _analyze_function(
        source, lines, start, end, header, encoding, function_names, emitted_target
    )
    ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "vb6",
            "source_file": source.name,
            "analyzer": ANALYZER_NAME,
            "analyzer_version": ANALYZER_VERSION + (";mode=emitted-target" if emitted_target else ""),
            "functions": [function],
            "diagnostics": [],
        }
    )
    types.check(ir)
    _reject_vb6_semantic_drift(ir, content)
    return ir


def analyze_many_vb6(
    source: Path,
    function_names: list[str],
    *,
    emitted_target: bool = False,
) -> dict[str, SemanticIR | RouteError]:
    result: dict[str, SemanticIR | RouteError] = {}
    for name in dict.fromkeys(function_names):
        try:
            result[name] = analyze_vb6(source, name, emitted_target=emitted_target)
        except RouteError as error:
            result[name] = error
    return result


def inventory_vb6_module(source: Path, *, emitted_target: bool = False) -> dict[str, Any]:
    if source.suffix.casefold() != ".bas":
        raise RouteError(f"VB6_MODULE_KIND_OUTSIDE_CERTIFIED_SUBSET:{source.suffix.casefold() or '<none>'}")
    content = source.read_bytes()
    lines, encoding, declarations = _module_functions(source, content)
    subjects: list[dict[str, Any]] = []
    occurrences: dict[str, int] = {}
    for start, end, header in declarations:
        name = header.group(3)
        folded = name.casefold()
        occurrences[folded] = occurrences.get(folded, 0) + 1
        parameter_types: list[str] = []
        analyzable = True
        for raw in _split_parameters(header.group(4)):
            match = _PARAMETER.fullmatch(raw)
            if match is None:
                analyzable = False
                parameter_types.append("unsupported")
            else:
                try:
                    parameter_types.append(_canonical_type(match.group(2), context=f"parameter:{name}"))
                except RouteError:
                    analyzable = False
                    parameter_types.append("unsupported")
        try:
            result_type = _canonical_type(header.group(5), context=f"function:{name}")
        except RouteError:
            analyzable = False
            result_type = "unsupported"
        subjects.append(
            {
                "name": name,
                "qualified_name": name,
                "declaration_kind": "function",
                "analyzable": analyzable,
                "source_span": _span(source, lines[start].start_byte, lines[end].end_byte),
                "signature": {"parameter_types": parameter_types, "return_type": result_type},
                "occurrence": occurrences[folded],
            }
        )
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-inventory",
        "profile": "typed-pure-module-v1",
        "source_language": "vb6",
        "source_file": source.name,
        "analyzer": ANALYZER_NAME,
        "analyzer_version": ANALYZER_VERSION + (";mode=emitted-target" if emitted_target else ""),
        "enumeration_status": "PASSED",
        "source_artifact_sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "source_artifact_bytes": len(content),
        "directives": [
            {
                "order": 0,
                "kind": "option",
                "value": "explicit",
                "source_span": next(
                    _span(source, line.start_byte, line.end_byte)
                    for line in lines
                    if _OPTION_EXPLICIT.fullmatch(_strip_comment(line.text).strip())
                ),
                "sha256": "sha256:" + hashlib.sha256(b"Option Explicit").hexdigest(),
            }
        ],
        "subjects": subjects,
        "diagnostics": [
            "VB6_VENDOR_COMPILER_RUNTIME_NOT_RUN",
            "VB6_COM_FORMS_ADO_OUTSIDE_BOUNDED_PROFILE",
            f"VB6_SOURCE_ENCODING:{encoding}",
        ],
    }


__all__ = ["analyze_many_vb6", "analyze_vb6", "inventory_vb6_module"]
