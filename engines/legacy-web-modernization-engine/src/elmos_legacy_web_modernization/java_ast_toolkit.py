"""Robust Java AST / CST parsing and manipulation toolkit.

Provides token-level and syntax-level structural representation for Java source files,
enabling compiler-grade transformations for Spring Security, JPA/Hibernate, and
general enterprise Java refactorings without fragile regex search-and-replace.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Iterator, Sequence


class TokenType(Enum):
    KEYWORD = auto()
    IDENTIFIER = auto()
    LITERAL_STRING = auto()
    LITERAL_CHAR = auto()
    LITERAL_NUMBER = auto()
    OPERATOR = auto()
    PUNCTUATION = auto()
    LINE_COMMENT = auto()
    BLOCK_COMMENT = auto()
    WHITESPACE = auto()
    EOF = auto()


@dataclass
class JavaToken:
    type: TokenType
    value: str
    start_pos: int
    end_pos: int
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, line={self.line})"


class JavaLexer:
    """Tokenizer capable of preserving trivia (whitespace and comments)."""

    KEYWORDS = {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
        "class", "const", "continue", "default", "do", "double", "else", "enum",
        "extends", "final", "finally", "float", "for", "goto", "if", "implements",
        "import", "instanceof", "int", "interface", "long", "native", "new",
        "package", "private", "protected", "public", "return", "short", "static",
        "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
        "transient", "try", "void", "volatile", "while", "record", "sealed",
        "non-sealed", "permits", "var", "yield",
    }

    PUNCTUATIONS = set("(){}[];,.:?@")
    MULTI_CHAR_OPS = {
        "->", "::", "==", "!=", "<=", ">=", "&&", "||", "++", "--", "+=", "-=",
        "*=", "/=", "%=", "&=", "|=", "^=", "<<", ">>", ">>>", "<<=", ">>=", ">>>="
    }

    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.pos = 0
        self.line = 1
        self.col = 1

    def tokenize(self, include_trivia: bool = True) -> list[JavaToken]:
        tokens: list[JavaToken] = []
        while self.pos < self.length:
            tok = self._next_token()
            if tok.type == TokenType.EOF:
                break
            if include_trivia or tok.type not in (
                TokenType.WHITESPACE,
                TokenType.LINE_COMMENT,
                TokenType.BLOCK_COMMENT,
            ):
                tokens.append(tok)
        return tokens

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < self.length else ""

    def _advance(self, count: int = 1) -> str:
        res = self.source[self.pos : self.pos + count]
        for ch in res:
            if ch == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
        self.pos += count
        return res

    def _next_token(self) -> JavaToken:
        if self.pos >= self.length:
            return JavaToken(TokenType.EOF, "", self.pos, self.pos, self.line, self.col)

        start_pos = self.pos
        start_line = self.line
        start_col = self.col
        ch = self._peek()

        # Whitespace
        if ch.isspace():
            val = []
            while self.pos < self.length and self._peek().isspace():
                val.append(self._advance())
            return JavaToken(TokenType.WHITESPACE, "".join(val), start_pos, self.pos, start_line, start_col)

        # Line comment or block comment or slash operator
        if ch == "/":
            next_ch = self._peek(1)
            if next_ch == "/":
                val = [self._advance(2)]
                while self.pos < self.length and self._peek() != "\n":
                    val.append(self._advance())
                return JavaToken(TokenType.LINE_COMMENT, "".join(val), start_pos, self.pos, start_line, start_col)
            elif next_ch == "*":
                val = [self._advance(2)]
                while self.pos < self.length:
                    if self._peek() == "*" and self._peek(1) == "/":
                        val.append(self._advance(2))
                        break
                    val.append(self._advance())
                return JavaToken(TokenType.BLOCK_COMMENT, "".join(val), start_pos, self.pos, start_line, start_col)

        # String literal (including text blocks """ ... """)
        if ch == '"':
            if self._peek(1) == '"' and self._peek(2) == '"':
                val = [self._advance(3)]
                while self.pos < self.length:
                    if self._peek() == '"' and self._peek(1) == '"' and self._peek(2) == '"':
                        val.append(self._advance(3))
                        break
                    if self._peek() == "\\":
                        val.append(self._advance(2))
                    else:
                        val.append(self._advance())
                return JavaToken(TokenType.LITERAL_STRING, "".join(val), start_pos, self.pos, start_line, start_col)
            else:
                val = [self._advance()]
                while self.pos < self.length:
                    c = self._peek()
                    if c == '"':
                        val.append(self._advance())
                        break
                    elif c == "\\":
                        val.append(self._advance(2))
                    elif c == "\n":
                        break
                    else:
                        val.append(self._advance())
                return JavaToken(TokenType.LITERAL_STRING, "".join(val), start_pos, self.pos, start_line, start_col)

        # Char literal
        if ch == "'":
            val = [self._advance()]
            while self.pos < self.length:
                c = self._peek()
                if c == "'":
                    val.append(self._advance())
                    break
                elif c == "\\":
                    val.append(self._advance(2))
                elif c == "\n":
                    break
                else:
                    val.append(self._advance())
            return JavaToken(TokenType.LITERAL_CHAR, "".join(val), start_pos, self.pos, start_line, start_col)

        # Multi-char operator
        for op in sorted(self.MULTI_CHAR_OPS, key=len, reverse=True):
            if self.source.startswith(op, self.pos):
                val = self._advance(len(op))
                return JavaToken(TokenType.OPERATOR, val, start_pos, self.pos, start_line, start_col)

        # Punctuation
        if ch in self.PUNCTUATIONS:
            val = self._advance()
            return JavaToken(TokenType.PUNCTUATION, val, start_pos, self.pos, start_line, start_col)

        # Number literal
        if ch.isdigit() or (ch == "." and self._peek(1).isdigit()):
            val = []
            while self.pos < self.length:
                c = self._peek()
                if c.isalnum() or c in (".", "_", "x", "X", "f", "F", "d", "D", "l", "L"):
                    val.append(self._advance())
                else:
                    break
            return JavaToken(TokenType.LITERAL_NUMBER, "".join(val), start_pos, self.pos, start_line, start_col)

        # Identifier or Keyword
        if ch.isalpha() or ch in ("_", "$"):
            val = []
            while self.pos < self.length:
                c = self._peek()
                if c.isalnum() or c in ("_", "$"):
                    val.append(self._advance())
                else:
                    break
            id_str = "".join(val)
            tok_type = TokenType.KEYWORD if id_str in self.KEYWORDS else TokenType.IDENTIFIER
            return JavaToken(tok_type, id_str, start_pos, self.pos, start_line, start_col)

        # Fallback single operator/char
        val = self._advance()
        return JavaToken(TokenType.OPERATOR, val, start_pos, self.pos, start_line, start_col)


@dataclass
class JavaAnnotationAst:
    name: str
    args: str = ""
    raw: str = ""

    def __repr__(self) -> str:
        return f"@{self.name}({self.args})" if self.args else f"@{self.name}"


@dataclass
class JavaParameterAst:
    type_name: str
    name: str
    annotations: list[JavaAnnotationAst] = field(default_factory=list)


@dataclass
class JavaMethodAst:
    name: str
    return_type: str
    parameters: list[JavaParameterAst] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    annotations: list[JavaAnnotationAst] = field(default_factory=list)
    throws_types: list[str] = field(default_factory=list)
    body: str = ""
    start_pos: int = 0
    end_pos: int = 0

    def has_annotation(self, name: str) -> bool:
        return any(a.name == name or a.name.endswith(f".{name}") for a in self.annotations)


@dataclass
class JavaFieldAst:
    name: str
    type_name: str
    modifiers: list[str] = field(default_factory=list)
    annotations: list[JavaAnnotationAst] = field(default_factory=list)
    initial_value: str | None = None
    start_pos: int = 0
    end_pos: int = 0


@dataclass
class JavaClassAst:
    name: str
    kind: str  # class, interface, enum, record
    modifiers: list[str] = field(default_factory=list)
    annotations: list[JavaAnnotationAst] = field(default_factory=list)
    extends_type: str | None = None
    implements_types: list[str] = field(default_factory=list)
    fields: list[JavaFieldAst] = field(default_factory=list)
    methods: list[JavaMethodAst] = field(default_factory=list)
    body_start: int = 0
    body_end: int = 0
    start_pos: int = 0
    end_pos: int = 0

    def has_annotation(self, name: str) -> bool:
        return any(a.name == name or a.name.endswith(f".{name}") for a in self.annotations)


@dataclass
class JavaCompilationUnitAst:
    source_code: str
    package_name: str | None = None
    imports: list[str] = field(default_factory=list)
    classes: list[JavaClassAst] = field(default_factory=list)

    def has_import(self, imp: str) -> bool:
        return any(i == imp or i.endswith(f".{imp}") or i.endswith(".*") for i in self.imports)


class JavaAstParser:
    """Parses Java source code into structural CompilationUnit, Classes, and Methods."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.lexer = JavaLexer(source)
        self.all_tokens = self.lexer.tokenize(include_trivia=True)
        self.code_tokens = [
            t for t in self.all_tokens
            if t.type not in (TokenType.WHITESPACE, TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT)
        ]
        self.idx = 0
        self.total = len(self.code_tokens)

    def _curr(self) -> JavaToken:
        if self.idx < self.total:
            return self.code_tokens[self.idx]
        return JavaToken(TokenType.EOF, "", len(self.source), len(self.source), 0, 0)

    def _peek(self, offset: int = 1) -> JavaToken:
        pos = self.idx + offset
        if pos < self.total:
            return self.code_tokens[pos]
        return JavaToken(TokenType.EOF, "", len(self.source), len(self.source), 0, 0)

    def _consume(self, expected: str | None = None) -> JavaToken:
        tok = self._curr()
        if expected and tok.value != expected:
            pass  # tolerant parsing
        self.idx += 1
        return tok

    def parse(self) -> JavaCompilationUnitAst:
        unit = JavaCompilationUnitAst(source_code=self.source)

        # Parse package and imports
        while self.idx < self.total:
            tok = self._curr()
            if tok.value == "package":
                self._consume("package")
                pkg_parts = []
                while self.idx < self.total and self._curr().value != ";":
                    pkg_parts.append(self._consume().value)
                if self._curr().value == ";":
                    self._consume(";")
                unit.package_name = "".join(pkg_parts)
            elif tok.value == "import":
                self._consume("import")
                imp_parts = []
                while self.idx < self.total and self._curr().value != ";":
                    imp_parts.append(self._consume().value)
                if self._curr().value == ";":
                    self._consume(";")
                unit.imports.append("".join(imp_parts))
            else:
                break

        # Parse classes / interfaces
        while self.idx < self.total:
            cls_ast = self._parse_class_declaration()
            if cls_ast:
                unit.classes.append(cls_ast)
            else:
                self.idx += 1

        return unit

    def _parse_annotations(self) -> list[JavaAnnotationAst]:
        annotations: list[JavaAnnotationAst] = []
        while self.idx < self.total and self._curr().value == "@":
            self._consume("@")
            ann_name_parts = [self._consume().value]
            while self.idx < self.total and self._curr().value == ".":
                self._consume(".")
                ann_name_parts.append(self._consume().value)
            ann_name = ".".join(ann_name_parts)
            args = ""
            if self._curr().value == "(":
                self._consume("(")
                paren_count = 1
                arg_tokens = []
                while self.idx < self.total and paren_count > 0:
                    t = self._consume()
                    if t.value == "(":
                        paren_count += 1
                    elif t.value == ")":
                        paren_count -= 1
                    if paren_count > 0:
                        arg_tokens.append(t.value)
                args = " ".join(arg_tokens)
            annotations.append(JavaAnnotationAst(name=ann_name, args=args))
        return annotations

    def _parse_class_declaration(self) -> JavaClassAst | None:
        annotations = self._parse_annotations()
        modifiers = []
        while self._curr().type == TokenType.KEYWORD and self._curr().value in (
            "public", "protected", "private", "static", "final", "abstract", "sealed", "non-sealed"
        ):
            modifiers.append(self._consume().value)

        tok = self._curr()
        if tok.value not in ("class", "interface", "enum", "record"):
            return None

        kind = self._consume().value
        class_name = self._consume().value

        extends_type: str | None = None
        implements_types: list[str] = []

        if self._curr().value == "extends":
            self._consume("extends")
            parts = []
            while self.idx < self.total and self._curr().value not in ("implements", "{"):
                parts.append(self._consume().value)
            extends_type = "".join(parts)

        if self._curr().value == "implements":
            self._consume("implements")
            parts = []
            while self.idx < self.total and self._curr().value != "{":
                if self._curr().value == ",":
                    implements_types.append("".join(parts))
                    parts = []
                    self._consume(",")
                else:
                    parts.append(self._consume().value)
            if parts:
                implements_types.append("".join(parts))

        if self._curr().value != "{":
            return None

        body_start_tok = self._consume("{")
        body_start = body_start_tok.end_pos

        brace_count = 1
        methods: list[JavaMethodAst] = []
        body_end = len(self.source)

        while self.idx < self.total and brace_count > 0:
            if self._curr().value == "{":
                brace_count += 1
                self._consume()
            elif self._curr().value == "}":
                brace_count -= 1
                if brace_count == 0:
                    body_end = self._curr().start_pos
                    self._consume("}")
                    break
                self._consume()
            else:
                method = self._try_parse_method()
                if method:
                    methods.append(method)
                else:
                    self.idx += 1

        return JavaClassAst(
            name=class_name,
            kind=kind,
            modifiers=modifiers,
            annotations=annotations,
            extends_type=extends_type,
            implements_types=implements_types,
            methods=methods,
            body_start=body_start,
            body_end=body_end,
            start_pos=tok.start_pos,
            end_pos=self.idx,
        )

    def _try_parse_method(self) -> JavaMethodAst | None:
        save_idx = self.idx
        annotations = self._parse_annotations()
        modifiers = []
        while self.idx < self.total and self._curr().value in (
            "public", "protected", "private", "static", "final", "synchronized", "default"
        ):
            modifiers.append(self._consume().value)

        if self.idx >= self.total:
            self.idx = save_idx
            return None

        return_type_parts = []
        if self._curr().value == "<":
            bracket = 1
            return_type_parts.append(self._consume().value)
            while self.idx < self.total and bracket > 0:
                t = self._consume()
                if t.value == "<":
                    bracket += 1
                elif t.value == ">":
                    bracket -= 1
                return_type_parts.append(t.value)

        if self._curr().type not in (TokenType.IDENTIFIER, TokenType.KEYWORD):
            self.idx = save_idx
            return None

        return_type_parts.append(self._consume().value)
        while self.idx < self.total and self._curr().value in ("<", "["):
            if self._curr().value == "<":
                bracket = 1
                return_type_parts.append(self._consume().value)
                while self.idx < self.total and bracket > 0:
                    t = self._consume()
                    if t.value == "<":
                        bracket += 1
                    elif t.value == ">":
                        bracket -= 1
                    return_type_parts.append(t.value)
            elif self._curr().value == "[":
                return_type_parts.append(self._consume().value)
                if self._curr().value == "]":
                    return_type_parts.append(self._consume().value)

        return_type = "".join(return_type_parts)

        if self.idx >= self.total or self._curr().type != TokenType.IDENTIFIER:
            self.idx = save_idx
            return None

        method_name = self._consume().value

        if self.idx >= self.total or self._curr().value != "(":
            self.idx = save_idx
            return None

        self._consume("(")
        parameters: list[JavaParameterAst] = []
        while self.idx < self.total and self._curr().value != ")":
            param_ann = self._parse_annotations()
            param_type_parts = []
            while self.idx < self.total and self._curr().type in (TokenType.IDENTIFIER, TokenType.KEYWORD) and self._curr().value not in (",", ")"):
                param_type_parts.append(self._consume().value)
                if self._curr().value == "<":
                    bracket = 1
                    param_type_parts.append(self._consume().value)
                    while self.idx < self.total and bracket > 0:
                        t = self._consume()
                        if t.value == "<":
                            bracket += 1
                        elif t.value == ">":
                            bracket -= 1
                        param_type_parts.append(t.value)
                elif self._curr().value == "[":
                    param_type_parts.append(self._consume().value)
                    if self._curr().value == "]":
                        param_type_parts.append(self._consume().value)
            
            if param_type_parts:
                param_name = param_type_parts.pop()
                param_type = "".join(param_type_parts)
                parameters.append(JavaParameterAst(type_name=param_type, name=param_name, annotations=param_ann))

            if self._curr().value == ",":
                self._consume(",")

        self._consume(")")

        throws_types = []
        if self._curr().value == "throws":
            self._consume("throws")
            while self.idx < self.total and self._curr().value not in (";", "{"):
                if self._curr().value == ",":
                    self._consume(",")
                else:
                    throws_types.append(self._consume().value)

        body = ""
        if self._curr().value == ";":
            self._consume(";")
            body = ""
        elif self._curr().value == "{":
            body_start_tok = self._consume("{")
            b_count = 1
            body_start = body_start_tok.end_pos
            body_end = body_start
            while self.idx < self.total and b_count > 0:
                t = self._curr()
                if t.value == "{":
                    b_count += 1
                elif t.value == "}":
                    b_count -= 1
                    if b_count == 0:
                        body_end = t.start_pos
                        self._consume("}")
                        break
                self._consume()
            body = self.source[body_start:body_end]
        else:
            self.idx = save_idx
            return None

        return JavaMethodAst(
            name=method_name,
            return_type=return_type,
            parameters=parameters,
            modifiers=modifiers,
            annotations=annotations,
            throws_types=throws_types,
            body=body,
        )


class MethodInvocationChainParser:
    """Parses builder call chains such as `http.authorizeRequests().antMatchers(...).permitAll()`."""

    @dataclass
    class CallNode:
        method_name: str
        args_text: str
        start: int
        end: int

    @staticmethod
    def parse_chain(expression: str) -> list[CallNode]:
        nodes: list[CallNode] = []
        lexer = JavaLexer(expression)
        tokens = [t for t in lexer.tokenize() if t.type not in (TokenType.WHITESPACE, TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT)]
        
        i = 0
        while i < len(tokens):
            if tokens[i].type == TokenType.IDENTIFIER and i + 1 < len(tokens) and tokens[i + 1].value == "(":
                m_name = tokens[i].value
                start_p = tokens[i].start_pos
                i += 2  # skip name and '('
                paren = 1
                arg_tokens = []
                while i < len(tokens) and paren > 0:
                    if tokens[i].value == "(":
                        paren += 1
                    elif tokens[i].value == ")":
                        paren -= 1
                    if paren > 0:
                        arg_tokens.append(tokens[i].value)
                    i += 1
                end_p = tokens[i - 1].end_pos if i > 0 else start_p
                nodes.append(MethodInvocationChainParser.CallNode(
                    method_name=m_name,
                    args_text=" ".join(arg_tokens),
                    start=start_p,
                    end=end_p,
                ))
            else:
                i += 1
        return nodes
