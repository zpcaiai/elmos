"""Fail-closed Visual C++ 6.0 frontend for the bounded pure-module IR.

The adapter deliberately recognizes a small C++98-era subset rather than
pretending that a modern C++ parser proves VC6 compatibility.  Free functions,
``__int64``/``double``/``bool``/``std::string`` scalars, local bindings,
assignment, return, if/else and while are admitted.  MFC, ATL, COM, Win32,
preprocessor macros, pointers/references, templates, exceptions and inline
assembly remain explicit gaps until a governed VC6 SP6 campaign supplies real
compiler and runtime evidence.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import types
from .models import RouteError, SemanticIR

ANALYZER_NAME = "elmos-vcpp6-bounded-parser"
ANALYZER_VERSION = "1.0.0;dialect=visual-cpp-6.0-sp6;profile=typed-pure-module-v1"
MAX_SOURCE_BYTES = 2_000_000

_TYPE_MAP = {
    "__int64": "integer",
    "double": "number",
    "bool": "boolean",
    "std::string": "string",
}
_TYPE_PATTERN = r"(?:__int64|double|bool|std::string)"
_FUNCTION_HEADER = re.compile(
    rf"^\s*(?:(static)\s+)?({_TYPE_PATTERN})\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\{\s*$"
)
_PARAMETER = re.compile(
    rf"^\s*(?:const\s+)?({_TYPE_PATTERN})\s+([A-Za-z_][A-Za-z0-9_]*)\s*$"
)
_LET = re.compile(
    rf"^\s*(?:(const)\s+)?({_TYPE_PATTERN})\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*;\s*$"
)
_ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*;\s*$")
_RETURN = re.compile(r"^\s*return\s+(.+?)\s*;\s*$")
_IF = re.compile(r"^\s*if\s*\((.+)\)\s*\{\s*$")
_ELSE = re.compile(r"^\s*(?:}\s*)?else\s*\{\s*$")
_WHILE = re.compile(r"^\s*while\s*\((.+)\)\s*\{\s*$")
_CLOSE = re.compile(r"^\s*}\s*$")
_CLOSE_ELSE = re.compile(r"^\s*}\s*else\s*\{\s*$")
_INCLUDE = re.compile(r"^\s*#\s*include\s*<\s*(limits\.h|string)\s*>\s*$")


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
    if content.startswith(b"\xef\xbb\xbf"):
        try:
            return content[3:].decode("utf-8"), "utf-8-sig"
        except UnicodeDecodeError as error:
            raise RouteError("VCPP6_SOURCE_ENCODING_INVALID:utf-8-sig") from error
    try:
        return content.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        try:
            return content.decode("cp1252"), "windows-1252"
        except UnicodeDecodeError as error:
            raise RouteError("VCPP6_SOURCE_ENCODING_UNSUPPORTED") from error


def _lines(text: str, encoding: str) -> list[_Line]:
    result: list[_Line] = []
    prefix = 3 if encoding == "utf-8-sig" else 0
    offset = prefix
    byte_encoding = "utf-8" if encoding == "utf-8-sig" else encoding
    for number, raw in enumerate(text.splitlines(keepends=True), start=1):
        without_eol = raw.rstrip("\r\n")
        result.append(
            _Line(
                number,
                without_eol,
                offset,
                offset + len(without_eol.encode(byte_encoding)),
            )
        )
        offset += len(raw.encode(byte_encoding))
    return result


def _span(source: Path, start: int, end: int) -> dict[str, Any]:
    return {
        "file": source.name,
        "start_byte": start,
        "end_byte": max(end, start + 1),
    }


def _strip_comment(value: str) -> str:
    if "/*" in value or "*/" in value:
        raise RouteError("VCPP6_BLOCK_COMMENT_OUTSIDE_BOUNDED_PARSER")
    in_string = False
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and in_string:
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
            continue
        if not in_string and value[index : index + 2] == "//":
            return value[:index]
    if in_string:
        raise RouteError("VCPP6_UNTERMINATED_STRING_LITERAL")
    return value


def _brace_delta(value: str) -> int:
    stripped = _strip_comment(value)
    in_string = False
    escaped = False
    delta = 0
    for character in stripped:
        if escaped:
            escaped = False
        elif character == "\\" and in_string:
            escaped = True
        elif character == '"':
            in_string = not in_string
        elif not in_string and character == "{":
            delta += 1
        elif not in_string and character == "}":
            delta -= 1
    return delta


def _split_parameters(value: str) -> list[str]:
    if not value.strip() or value.strip() == "void":
        return []
    if any(marker in value for marker in ("*", "&", "=", "[", "]", "...")):
        raise RouteError("VCPP6_PARAMETER_SHAPE_OUTSIDE_CERTIFIED_SUBSET")
    return value.split(",")


def _canonical_type(value: str, *, context: str) -> str:
    canonical = _TYPE_MAP.get(" ".join(value.split()))
    if canonical is not None:
        return canonical
    raise RouteError(f"VCPP6_TYPE_OUTSIDE_CERTIFIED_SUBSET:{context}:{value}")


_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<number>(?:[0-9]+\.[0-9]*(?:[Ee][+-]?[0-9]+)?|"
    r"[0-9]+[Ee][+-]?[0-9]+|[0-9]+)(?:(?:i64)|LL|L)?)|"
    r'(?P<string>"(?:[^"\\]|\\.)*")|'
    r"(?P<identifier>[A-Za-z_][A-Za-z0-9_:]*)|"
    r"(?P<operator><=|>=|==|!=|&&|\|\||[=<>+\-*/%(),!])"
    r")",
    re.IGNORECASE,
)


def _tokens(text: str, line: _Line, encoding: str) -> list[_Token]:
    tokens: list[_Token] = []
    cursor = 0
    byte_encoding = "utf-8" if encoding == "utf-8-sig" else encoding
    expression_column = line.text.find(text)
    if expression_column < 0:
        raise RouteError(f"VCPP6_EXPRESSION_SOURCE_SPAN_UNRESOLVED:line={line.number}")
    expression_start = line.start_byte + len(line.text[:expression_column].encode(byte_encoding))
    while cursor < len(text):
        match = _TOKEN.match(text, cursor)
        if match is None:
            raise RouteError(
                f"VCPP6_UNSUPPORTED_EXPRESSION_TOKEN:line={line.number}:column={cursor + 1}"
            )
        kind = match.lastgroup
        assert kind is not None
        raw = match.group(kind)
        start = expression_start + len(text[: match.start(kind)].encode(byte_encoding))
        end = expression_start + len(text[: match.end(kind)].encode(byte_encoding))
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
            raise RouteError("VCPP6_EXPRESSION_REQUIRED")
        expression = self._parse_or()
        if self.index != len(self.tokens):
            raise RouteError(
                f"VCPP6_UNEXPECTED_EXPRESSION_TOKEN:{self.tokens[self.index].value}"
            )
        return expression

    def _peek(self, value: str | None = None) -> _Token | None:
        if self.index >= len(self.tokens):
            return None
        token = self.tokens[self.index]
        return token if value is None or token.value.casefold() == value.casefold() else None

    def _take(self, value: str | None = None) -> _Token:
        token = self._peek(value)
        if token is None:
            raise RouteError(f"VCPP6_EXPRESSION_TOKEN_REQUIRED:{value or 'token'}")
        self.index += 1
        return token

    def _binary(self, left: dict[str, Any], operator: str, right: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "binary",
            "operator": operator,
            "left": left,
            "right": right,
            "source_span": _span(
                self.source,
                left["source_span"]["start_byte"],
                right["source_span"]["end_byte"],
            ),
        }

    def _parse_or(self) -> dict[str, Any]:
        left = self._parse_and()
        while self._peek("||") is not None:
            self.index += 1
            left = self._binary(left, "||", self._parse_and())
        return left

    def _parse_and(self) -> dict[str, Any]:
        left = self._parse_comparison()
        while self._peek("&&") is not None:
            self.index += 1
            left = self._binary(left, "&&", self._parse_comparison())
        return left

    def _parse_comparison(self) -> dict[str, Any]:
        left = self._parse_additive()
        token = self._peek()
        if token is not None and token.value in {"==", "!=", "<", "<=", ">", ">="}:
            self.index += 1
            left = self._binary(left, token.value, self._parse_additive())
            following = self._peek()
            if following is not None and following.value in {"==", "!=", "<", "<=", ">", ">="}:
                raise RouteError("VCPP6_CHAINED_COMPARISON_OUTSIDE_CERTIFIED_SUBSET")
        return left

    def _parse_additive(self) -> dict[str, Any]:
        left = self._parse_multiplicative()
        while self._peek("+") is not None or self._peek("-") is not None:
            operator = self._take().value
            left = self._binary(left, operator, self._parse_multiplicative())
        return left

    def _parse_multiplicative(self) -> dict[str, Any]:
        left = self._parse_primary()
        while self._peek("*") is not None or self._peek("/") is not None or self._peek("%") is not None:
            operator = self._take().value
            left = self._binary(left, operator, self._parse_primary())
        return left

    def _parse_primary(self) -> dict[str, Any]:
        token = self._take()
        if token.value == "!":
            operand = self._parse_primary()
            false_literal = {
                "kind": "literal",
                "value": False,
                "source_span": _span(self.source, token.start, token.end),
            }
            return self._binary(operand, "==", false_literal)
        if token.value in {"+", "-"}:
            operand = self._take()
            if operand.kind != "number":
                raise RouteError("VCPP6_UNARY_SIGN_ON_EXPRESSION_OUTSIDE_CERTIFIED_SUBSET")
            token = _Token(operand.kind, token.value + operand.value, token.start, operand.end)
        if token.kind == "number":
            raw = token.value
            value_text = re.sub(r"(?i)(?:i64|ll|l)$", "", raw)
            try:
                value: int | float = (
                    float(value_text)
                    if "." in value_text or "e" in value_text.casefold()
                    else int(value_text)
                )
            except ValueError as error:
                raise RouteError(f"VCPP6_INVALID_NUMERIC_LITERAL:{raw}") from error
            return {
                "kind": "literal",
                "value": value,
                "source_span": _span(self.source, token.start, token.end),
            }
        if token.kind == "string":
            try:
                value = bytes(token.value[1:-1], "utf-8").decode("unicode_escape")
            except UnicodeDecodeError as error:
                raise RouteError("VCPP6_STRING_ESCAPE_OUTSIDE_CERTIFIED_SUBSET") from error
            if any(ord(character) > 127 for character in value):
                raise RouteError("VCPP6_STRING_OUTSIDE_ASCII_PROFILE")
            return {
                "kind": "literal",
                "value": value,
                "source_span": _span(self.source, token.start, token.end),
            }
        if token.value == "(":
            expression = self._parse_or()
            closing = self._take(")")
            expression["source_span"] = _span(self.source, token.start, closing.end)
            return expression
        if token.kind != "identifier":
            raise RouteError(f"VCPP6_UNSUPPORTED_EXPRESSION:{token.value}")
        folded = token.value.casefold()
        if folded in {"new", "delete", "throw", "sizeof", "typeid"}:
            raise RouteError(
                f"VCPP6_CONTROL_OR_EFFECT_SEMANTICS_OUTSIDE_CERTIFIED_SUBSET:{token.value}"
            )
        if folded in {"true", "false"}:
            return {
                "kind": "literal",
                "value": folded == "true",
                "source_span": _span(self.source, token.start, token.end),
            }
        if self._peek("(") is not None:
            self.index += 1
            arguments: list[dict[str, Any]] = []
            if self._peek(")") is None:
                while True:
                    arguments.append(self._parse_or())
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
                raise RouteError(
                    f"VCPP6_EFFECTFUL_OR_UNKNOWN_CALL_OUTSIDE_CERTIFIED_SUBSET:{token.value}"
                )
            raise RouteError(f"VCPP6_CROSS_FUNCTION_CALL_REQUIRES_MODULE_IR:{token.value}")
        name = self.names.get(folded)
        if name is None:
            raise RouteError(f"VCPP6_UNDECLARED_NAME:{token.value}")
        return {
            "kind": "name",
            "value": name,
            "source_span": _span(self.source, token.start, token.end),
        }


def _expression(
    text: str,
    line: _Line,
    source: Path,
    encoding: str,
    names: dict[str, str],
    function_names: dict[str, str],
    emitted_target: bool,
) -> dict[str, Any]:
    return _ExpressionParser(
        _tokens(text, line, encoding), source, names, function_names, emitted_target
    ).parse()


def _read_source(source: Path) -> bytes:
    if source.suffix.casefold() != ".cpp":
        raise RouteError(
            f"VCPP6_TRANSLATION_UNIT_KIND_OUTSIDE_CERTIFIED_SUBSET:{source.suffix.casefold() or '<none>'}"
        )
    before = source.stat(follow_symlinks=False)
    content = source.read_bytes()
    after = source.stat(follow_symlinks=False)
    if (
        source.is_symlink()
        or not source.is_file()
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(content) != after.st_size
    ):
        raise RouteError("VCPP6_SOURCE_CHANGED_DURING_READ")
    if len(content) > MAX_SOURCE_BYTES:
        raise RouteError("SOURCE_FILE_UNSAFE_OR_TOO_LARGE")
    return content


def _module_functions(
    source: Path, content: bytes
) -> tuple[list[_Line], str, list[tuple[int, int, re.Match[str]]], list[_Line]]:
    text, encoding = _decode_source(content)
    lines = _lines(text, encoding)
    declarations: list[tuple[int, int, re.Match[str]]] = []
    directives: list[_Line] = []
    index = 0
    while index < len(lines):
        raw = _strip_comment(lines[index].text).strip()
        if not raw:
            index += 1
            continue
        if raw.startswith("#"):
            if _INCLUDE.fullmatch(raw) is None:
                raise RouteError(
                    f"VCPP6_PREPROCESSOR_DIRECTIVE_OUTSIDE_CERTIFIED_SUBSET:line={lines[index].number}"
                )
            directives.append(lines[index])
            index += 1
            continue
        header = _FUNCTION_HEADER.fullmatch(raw)
        if header is None:
            markers = ("class ", "struct ", "template", "namespace ", "__declspec", "extern ")
            if raw.casefold().startswith(markers):
                raise RouteError(
                    f"VCPP6_MODULE_DECLARATION_OUTSIDE_CERTIFIED_SUBSET:line={lines[index].number}"
                )
            raise RouteError(
                f"VCPP6_TOP_LEVEL_STATEMENT_OUTSIDE_CERTIFIED_SUBSET:line={lines[index].number}"
            )
        depth = _brace_delta(lines[index].text)
        cursor = index + 1
        while cursor < len(lines) and depth > 0:
            depth += _brace_delta(lines[cursor].text)
            if depth < 0:
                raise RouteError(f"VCPP6_BRACE_STRUCTURE_INVALID:line={lines[cursor].number}")
            cursor += 1
        if depth != 0:
            raise RouteError(f"VCPP6_FUNCTION_CLOSE_REQUIRED:{header.group(3)}")
        declarations.append((index, cursor - 1, header))
        index = cursor
    if not declarations:
        raise RouteError("VCPP6_FUNCTION_NOT_FOUND")
    return lines, encoding, declarations, directives


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
    return_type = _canonical_type(header.group(2), context=f"function:{function_name}")
    parameters: list[dict[str, Any]] = []
    names: dict[str, str] = {}
    for raw_parameter in _split_parameters(header.group(4)):
        match = _PARAMETER.fullmatch(raw_parameter)
        if match is None:
            raise RouteError(f"VCPP6_PARAMETER_SHAPE_OUTSIDE_CERTIFIED_SUBSET:{function_name}")
        name = match.group(2)
        folded = name.casefold()
        if folded in names:
            raise RouteError(f"VCPP6_DUPLICATE_PARAMETER_CASE_INSENSITIVE:{name}")
        canonical_type = _canonical_type(match.group(1), context=f"parameter:{function_name}.{name}")
        names[folded] = name
        parameters.append({"name": name, "type": canonical_type})

    body_lines = lines[start_index + 1 : end_index]

    def parse_block(index: int, *, nested: bool) -> tuple[list[dict[str, Any]], int, str | None]:
        statements: list[dict[str, Any]] = []
        while index < len(body_lines):
            line = body_lines[index]
            raw = _strip_comment(line.text).strip()
            if not raw:
                index += 1
                continue
            if nested and _CLOSE_ELSE.fullmatch(raw):
                return statements, index, "else"
            if nested and _CLOSE.fullmatch(raw):
                return statements, index, "close"
            lowered = raw.casefold()
            forbidden = (
                "try", "catch", "throw", "new ", "delete ", "asm", "__asm",
                "goto ", "switch ", "do ", "for ", "typedef ", "using ",
            )
            if lowered.startswith(forbidden):
                raise RouteError(
                    f"VCPP6_CONTROL_OR_EFFECT_SEMANTICS_OUTSIDE_CERTIFIED_SUBSET:line={line.number}"
                )
            match = _LET.fullmatch(raw)
            if match is not None:
                name = match.group(3)
                folded = name.casefold()
                if folded in names:
                    raise RouteError(f"VCPP6_LOCAL_NAME_ALREADY_BOUND:{name}")
                canonical_type = _canonical_type(
                    match.group(2), context=f"local:{function_name}.{name}"
                )
                initializer = _expression(
                    match.group(4), line, source, encoding, names, function_names, emitted_target
                )
                names[folded] = name
                statements.append(
                    {
                        "kind": "let",
                        "name": name,
                        "type": canonical_type,
                        "expression": initializer,
                        "source_span": _span(source, line.start_byte, line.end_byte),
                    }
                )
                index += 1
                continue
            match = _IF.fullmatch(raw)
            if match is not None:
                condition = _expression(
                    match.group(1), line, source, encoding, names, function_names, emitted_target
                )
                then_body, stop, terminator = parse_block(index + 1, nested=True)
                if stop >= len(body_lines):
                    raise RouteError(f"VCPP6_IF_CLOSE_REQUIRED:line={line.number}")
                else_body: list[dict[str, Any]] = []
                if terminator == "else":
                    else_body, stop, terminator = parse_block(stop + 1, nested=True)
                elif stop + 1 < len(body_lines) and _ELSE.fullmatch(
                    _strip_comment(body_lines[stop + 1].text).strip()
                ):
                    else_body, stop, terminator = parse_block(stop + 2, nested=True)
                if terminator != "close":
                    raise RouteError(f"VCPP6_IF_CLOSE_REQUIRED:line={line.number}")
                statements.append(
                    {
                        "kind": "if",
                        "condition": condition,
                        "then": then_body,
                        "else": else_body,
                        "source_span": _span(source, line.start_byte, body_lines[stop].end_byte),
                    }
                )
                index = stop + 1
                continue
            match = _WHILE.fullmatch(raw)
            if match is not None:
                condition = _expression(
                    match.group(1), line, source, encoding, names, function_names, emitted_target
                )
                loop_body, stop, terminator = parse_block(index + 1, nested=True)
                if stop >= len(body_lines) or terminator != "close":
                    raise RouteError(f"VCPP6_WHILE_CLOSE_REQUIRED:line={line.number}")
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
            match = _RETURN.fullmatch(raw)
            if match is not None:
                statements.append(
                    {
                        "kind": "return",
                        "expression": _expression(
                            match.group(1), line, source, encoding, names, function_names, emitted_target
                        ),
                        "source_span": _span(source, line.start_byte, line.end_byte),
                    }
                )
                index += 1
                continue
            match = _ASSIGN.fullmatch(raw)
            if match is not None:
                raw_name = match.group(1)
                canonical_name = names.get(raw_name.casefold())
                if canonical_name is None:
                    raise RouteError(f"VCPP6_ASSIGNMENT_TARGET_NOT_DECLARED:{raw_name}")
                if any(parameter["name"].casefold() == canonical_name.casefold() for parameter in parameters):
                    raise RouteError(
                        f"VCPP6_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{raw_name}"
                    )
                statements.append(
                    {
                        "kind": "assign",
                        "name": canonical_name,
                        "expression": _expression(
                            match.group(2), line, source, encoding, names, function_names, emitted_target
                        ),
                        "source_span": _span(source, line.start_byte, line.end_byte),
                    }
                )
                index += 1
                continue
            if raw in {"break;", "continue;"}:
                statements.append(
                    {
                        "kind": raw[:-1],
                        "source_span": _span(source, line.start_byte, line.end_byte),
                    }
                )
                index += 1
                continue
            raise RouteError(f"VCPP6_UNSUPPORTED_STATEMENT:line={line.number}:{raw[:80]}")
        return statements, index, None

    body, consumed, terminator = parse_block(0, nested=False)
    if consumed != len(body_lines) or terminator is not None or not body:
        raise RouteError(f"VCPP6_FUNCTION_BODY_INVALID:{function_name}")

    def has_return(statements: list[dict[str, Any]]) -> bool:
        return any(
            statement["kind"] == "return"
            or has_return(statement.get("then", []))
            or has_return(statement.get("else", []))
            or has_return(statement.get("body", []))
            for statement in statements
        )

    if not has_return(body):
        raise RouteError(f"VCPP6_FUNCTION_RETURN_REQUIRED:{function_name}")
    return {
        "name": function_name,
        "parameters": parameters,
        "return_type": return_type,
        "body": body,
        "source_span": _span(source, lines[start_index].start_byte, lines[end_index].end_byte),
    }


def analyze_vcpp6(
    source: Path, function_name: str, *, emitted_target: bool = False
) -> SemanticIR:
    content = _read_source(source)
    lines, encoding, declarations, _directives = _module_functions(source, content)
    function_names: dict[str, str] = {}
    for _, _, header in declarations:
        name = header.group(3)
        folded = name.casefold()
        if folded in function_names:
            raise RouteError(f"VCPP6_DUPLICATE_FUNCTION_CASE_INSENSITIVE:{name}")
        function_names[folded] = name
    selected = [
        item for item in declarations if item[2].group(3).casefold() == function_name.casefold()
    ]
    if len(selected) != 1:
        raise RouteError(f"VCPP6_FUNCTION_NOT_FOUND:{function_name}")
    start, end, header = selected[0]
    function = _analyze_function(
        source,
        lines,
        start,
        end,
        header,
        encoding,
        function_names,
        emitted_target,
    )
    ir = SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "vcpp6",
            "source_file": source.name,
            "analyzer": ANALYZER_NAME,
            "analyzer_version": ANALYZER_VERSION
            + (";mode=emitted-target" if emitted_target else ""),
            "functions": [function],
            "diagnostics": [],
        }
    )
    types.check(ir)
    return ir


def analyze_many_vcpp6(
    source: Path,
    function_names: list[str],
    *,
    emitted_target: bool = False,
) -> dict[str, SemanticIR | RouteError]:
    outcomes: dict[str, SemanticIR | RouteError] = {}
    for name in dict.fromkeys(function_names):
        try:
            outcomes[name] = analyze_vcpp6(
                source, name, emitted_target=emitted_target
            )
        except RouteError as error:
            outcomes[name] = error
    return outcomes


def inventory_vcpp6_module(
    source: Path, *, emitted_target: bool = False
) -> dict[str, Any]:
    content = _read_source(source)
    lines, encoding, declarations, directives = _module_functions(source, content)
    subjects: list[dict[str, Any]] = []
    occurrences: dict[str, int] = {}
    for start, end, header in declarations:
        name = header.group(3)
        folded = name.casefold()
        occurrences[folded] = occurrences.get(folded, 0) + 1
        parameter_types: list[str] = []
        analyzable = header.group(1) is None
        for raw_parameter in _split_parameters(header.group(4)):
            match = _PARAMETER.fullmatch(raw_parameter)
            if match is None:
                analyzable = False
                parameter_types.append("unsupported")
            else:
                parameter_types.append(
                    _canonical_type(match.group(1), context=f"parameter:{name}")
                )
        result_type = _canonical_type(header.group(2), context=f"function:{name}")
        subjects.append(
            {
                "name": name,
                "qualified_name": name,
                "declaration_kind": "function",
                "analyzable": analyzable,
                "source_span": _span(
                    source, lines[start].start_byte, lines[end].end_byte
                ),
                "signature": {
                    "parameter_types": parameter_types,
                    "return_type": result_type,
                    "storage": "internal" if header.group(1) else "external",
                },
                "occurrence": occurrences[folded],
            }
        )
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.typed-pure-module-inventory",
        "profile": "typed-pure-module-v1",
        "source_language": "vcpp6",
        "source_file": source.name,
        "analyzer": ANALYZER_NAME,
        "analyzer_version": ANALYZER_VERSION
        + (";mode=emitted-target" if emitted_target else ""),
        "enumeration_status": "PASSED",
        "source_artifact_sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "source_artifact_bytes": len(content),
        "directives": [
            {
                "order": index,
                "kind": "include",
                "value": _strip_comment(line.text).strip(),
                "source_span": _span(source, line.start_byte, line.end_byte),
                "sha256": "sha256:"
                + hashlib.sha256(_strip_comment(line.text).strip().encode("ascii")).hexdigest(),
            }
            for index, line in enumerate(directives)
        ],
        "subjects": subjects,
        "diagnostics": [
            "VCPP6_VENDOR_COMPILER_RUNTIME_NOT_RUN",
            "VCPP6_MFC_ATL_COM_WIN32_OUTSIDE_BOUNDED_PROFILE",
            f"VCPP6_SOURCE_ENCODING:{encoding}",
        ],
    }


__all__ = [
    "analyze_many_vcpp6",
    "analyze_vcpp6",
    "inventory_vcpp6_module",
]
