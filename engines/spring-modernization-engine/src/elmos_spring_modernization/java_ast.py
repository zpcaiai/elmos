from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# ==============================================================================
# 1. Lexical Token Definitions & Tokenizer
# ==============================================================================

class TokenType(enum.Enum):
    KEYWORD = "KEYWORD"
    IDENTIFIER = "IDENTIFIER"
    ANNOTATION_AT = "ANNOTATION_AT"
    STRING_LITERAL = "STRING_LITERAL"
    CHAR_LITERAL = "CHAR_LITERAL"
    NUMBER_LITERAL = "NUMBER_LITERAL"
    OPERATOR = "OPERATOR"
    SEPARATOR = "SEPARATOR"
    COMMENT_LINE = "COMMENT_LINE"
    COMMENT_BLOCK = "COMMENT_BLOCK"
    WHITESPACE = "WHITESPACE"
    EOF = "EOF"


@dataclass
class Token:
    type: TokenType
    value: str
    start: int
    end: int
    line: int = 1
    col: int = 1
    leading_trivia: str = ""
    trailing_trivia: str = ""


JAVA_KEYWORDS: Set[str] = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "record", "return", "short",
    "static", "strictfp", "super", "switch", "synchronized", "this", "throw",
    "throws", "transient", "try", "void", "volatile", "while", "yield", "sealed",
    "permits", "non-sealed"
}


class JavaLexer:
    """
    Compiler-grade Java Lexer that tracks exact token character spans and trivia
    (comments and whitespace) attached to tokens for lossless AST reconstruction.
    """

    def __init__(self, source: str):
        self.source = source
        self.length = len(source)
        self.cursor = 0
        self.line = 1
        self.col = 1

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        pending_trivia = ""

        while self.cursor < self.length:
            char = self.source[self.cursor]

            # Whitespace
            if char.isspace():
                start = self.cursor
                while self.cursor < self.length and self.source[self.cursor].isspace():
                    if self.source[self.cursor] == "\n":
                        self.line += 1
                        self.col = 1
                    else:
                        self.col += 1
                    self.cursor += 1
                pending_trivia += self.source[start:self.cursor]
                continue

            # Line Comment
            if char == "/" and self.cursor + 1 < self.length and self.source[self.cursor + 1] == "/":
                start = self.cursor
                while self.cursor < self.length and self.source[self.cursor] != "\n":
                    self.cursor += 1
                    self.col += 1
                pending_trivia += self.source[start:self.cursor]
                continue

            # Block Comment
            if char == "/" and self.cursor + 1 < self.length and self.source[self.cursor + 1] == "*":
                start = self.cursor
                self.cursor += 2
                self.col += 2
                while self.cursor < self.length:
                    if self.source[self.cursor] == "\n":
                        self.line += 1
                        self.col = 1
                    else:
                        self.col += 1
                    if (
                        self.source[self.cursor] == "*"
                        and self.cursor + 1 < self.length
                        and self.source[self.cursor + 1] == "/"
                    ):
                        self.cursor += 2
                        self.col += 2
                        break
                    self.cursor += 1
                pending_trivia += self.source[start:self.cursor]
                continue

            # String literal
            if char == '"':
                token = self._read_string_literal()
                token.leading_trivia = pending_trivia
                pending_trivia = ""
                tokens.append(token)
                continue

            # Char literal
            if char == "'":
                token = self._read_char_literal()
                token.leading_trivia = pending_trivia
                pending_trivia = ""
                tokens.append(token)
                continue

            # Annotation marker '@'
            if char == "@":
                start = self.cursor
                line = self.line
                col = self.col
                self.cursor += 1
                self.col += 1
                token = Token(TokenType.ANNOTATION_AT, "@", start, self.cursor, line, col, leading_trivia=pending_trivia)
                pending_trivia = ""
                tokens.append(token)
                continue

            # Numbers
            if char.isdigit():
                token = self._read_number()
                token.leading_trivia = pending_trivia
                pending_trivia = ""
                tokens.append(token)
                continue

            # Identifiers and keywords
            if char.isalpha() or char in ("_", "$"):
                token = self._read_identifier_or_keyword()
                token.leading_trivia = pending_trivia
                pending_trivia = ""
                tokens.append(token)
                continue

            # Separators and Operators
            start = self.cursor
            line = self.line
            col = self.col
            if char in "{}();,.[][]":
                self.cursor += 1
                self.col += 1
                token = Token(TokenType.SEPARATOR, char, start, self.cursor, line, col, leading_trivia=pending_trivia)
                pending_trivia = ""
                tokens.append(token)
                continue

            # Multi-character or single operators
            op = self._read_operator()
            token = Token(TokenType.OPERATOR, op, start, self.cursor, line, col, leading_trivia=pending_trivia)
            pending_trivia = ""
            tokens.append(token)

        eof_token = Token(TokenType.EOF, "", self.length, self.length, self.line, self.col, leading_trivia=pending_trivia)
        tokens.append(eof_token)
        return tokens

    def _read_string_literal(self) -> Token:
        start = self.cursor
        line = self.line
        col = self.col
        # Check text block """
        if self.source[self.cursor:self.cursor + 3] == '"""':
            self.cursor += 3
            self.col += 3
            while self.cursor < self.length:
                if self.source[self.cursor:self.cursor + 3] == '"""':
                    self.cursor += 3
                    self.col += 3
                    break
                if self.source[self.cursor] == "\\":
                    self.cursor += 2
                    self.col += 2
                else:
                    if self.source[self.cursor] == "\n":
                        self.line += 1
                        self.col = 1
                    else:
                        self.col += 1
                    self.cursor += 1
        else:
            self.cursor += 1
            self.col += 1
            while self.cursor < self.length:
                c = self.source[self.cursor]
                if c == "\\":
                    self.cursor += 2
                    self.col += 2
                elif c == '"':
                    self.cursor += 1
                    self.col += 1
                    break
                else:
                    if c == "\n":
                        self.line += 1
                        self.col = 1
                    else:
                        self.col += 1
                    self.cursor += 1

        val = self.source[start:self.cursor]
        return Token(TokenType.STRING_LITERAL, val, start, self.cursor, line, col)

    def _read_char_literal(self) -> Token:
        start = self.cursor
        line = self.line
        col = self.col
        self.cursor += 1
        self.col += 1
        while self.cursor < self.length:
            c = self.source[self.cursor]
            if c == "\\":
                self.cursor += 2
                self.col += 2
            elif c == "'":
                self.cursor += 1
                self.col += 1
                break
            else:
                self.cursor += 1
                self.col += 1
        return Token(TokenType.CHAR_LITERAL, self.source[start:self.cursor], start, self.cursor, line, col)

    def _read_number(self) -> Token:
        start = self.cursor
        line = self.line
        col = self.col
        while self.cursor < self.length and (self.source[self.cursor].isalnum() or self.source[self.cursor] in "._-"):
            self.cursor += 1
            self.col += 1
        return Token(TokenType.NUMBER_LITERAL, self.source[start:self.cursor], start, self.cursor, line, col)

    def _read_identifier_or_keyword(self) -> Token:
        start = self.cursor
        line = self.line
        col = self.col
        while self.cursor < self.length and (self.source[self.cursor].isalnum() or self.source[self.cursor] in "_$"):
            self.cursor += 1
            self.col += 1
        val = self.source[start:self.cursor]
        ttype = TokenType.KEYWORD if val in JAVA_KEYWORDS else TokenType.IDENTIFIER
        return Token(ttype, val, start, self.cursor, line, col)

    def _read_operator(self) -> str:
        start = self.cursor
        two_char = self.source[self.cursor:self.cursor + 2]
        if two_char in ("==", "!=", "<=", ">=", "&&", "||", "++", "--", "->", "::", "+=", "-=", "*=", "/="):
            self.cursor += 2
            self.col += 2
            return two_char
        self.cursor += 1
        self.col += 1
        return self.source[start:self.cursor]


# ==============================================================================
# 2. Typed AST Node Hierarchy & Attribute Model
# ==============================================================================

@dataclass
class Comment:
    is_multiline: bool
    text: str
    trailing_newline: bool = False


@dataclass
class Space:
    whitespace: str = ""
    comments: List[Comment] = field(default_factory=list)

    @classmethod
    def build(cls, raw: str) -> "Space":
        if not raw:
            return cls()
        comments: List[Comment] = []
        i = 0
        n = len(raw)
        ws_buf: List[str] = []
        while i < n:
            if raw[i:i+2] == "//":
                end = raw.find("\n", i + 2)
                if end == -1:
                    comments.append(Comment(is_multiline=False, text=raw[i:], trailing_newline=False))
                    i = n
                else:
                    comments.append(Comment(is_multiline=False, text=raw[i:end], trailing_newline=True))
                    i = end + 1
                    ws_buf.append("\n")
            elif raw[i:i+2] == "/*":
                end = raw.find("*/", i + 2)
                if end == -1:
                    comments.append(Comment(is_multiline=True, text=raw[i:], trailing_newline=False))
                    i = n
                else:
                    comments.append(Comment(is_multiline=True, text=raw[i:end+2], trailing_newline=False))
                    i = end + 2
            else:
                ws_buf.append(raw[i])
                i += 1
        return cls(whitespace="".join(ws_buf), comments=comments)

    def print(self) -> str:
        parts = []
        if self.comments:
            for c in self.comments:
                parts.append(c.text + ("\n" if c.trailing_newline else ""))
        if self.whitespace:
            parts.append(self.whitespace)
        return "".join(parts)


@dataclass
class JavaASTNode:
    parent: Optional[JavaASTNode] = field(default=None, repr=False)
    leading_trivia: str = ""
    trailing_trivia: str = ""
    prefix_space: Space = field(default_factory=Space)
    suffix_space: Space = field(default_factory=Space)
    start_offset: int = 0
    end_offset: int = 0
    symbol_attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnnotationArgument(JavaASTNode):
    name: Optional[str] = None
    value: str = ""
    resolved_symbol: Optional[str] = None


@dataclass
class AnnotationNode(JavaASTNode):
    name: str = ""
    arguments: List[AnnotationArgument] = field(default_factory=list)
    resolved_type: Optional[str] = None

    def get_arg(self, name: str) -> Optional[AnnotationArgument]:
        for arg in self.arguments:
            if arg.name == name:
                return arg
        return None

    def get_value_arg(self) -> Optional[AnnotationArgument]:
        for arg in self.arguments:
            if arg.name in ("value", "path") or arg.name is None:
                return arg
        return None


@dataclass
class TypeReference(JavaASTNode):
    name: str = ""
    resolved_type: Optional[str] = None


@dataclass
class ImportDeclaration(JavaASTNode):
    name: str = ""
    is_static: bool = False
    is_wildcard: bool = False


@dataclass
class PackageDeclaration(JavaASTNode):
    name: str = ""


@dataclass
class MethodParameter(JavaASTNode):
    annotations: List[AnnotationNode] = field(default_factory=list)
    type_name: str = ""
    name: str = ""


# ==============================================================================
# Statement and Expression AST Hierarchy (Compiler-grade LST)
# ==============================================================================

@dataclass
class Statement(JavaASTNode):
    pass


@dataclass
class Expression(JavaASTNode):
    pass


@dataclass
class Block(Statement):
    statements: List[Statement] = field(default_factory=list)


@dataclass
class ExpressionStatement(Statement):
    expression: Expression = field(default_factory=Expression)


@dataclass
class VariableDeclarationStatement(Statement):
    type_name: str = ""
    variable_name: str = ""
    initializer: Optional[Expression] = None


@dataclass
class IfStatement(Statement):
    condition: Expression = field(default_factory=Expression)
    then_branch: Statement = field(default_factory=Statement)
    else_branch: Optional[Statement] = None


@dataclass
class WhileStatement(Statement):
    condition: Expression = field(default_factory=Expression)
    body: Statement = field(default_factory=Statement)


@dataclass
class ForStatement(Statement):
    init: Optional[Statement] = None
    condition: Optional[Expression] = None
    update: Optional[Expression] = None
    body: Statement = field(default_factory=Statement)


@dataclass
class CatchClause(JavaASTNode):
    param_type: str = ""
    param_name: str = ""
    body: Block = field(default_factory=Block)


@dataclass
class TryCatchFinallyStatement(Statement):
    try_block: Block = field(default_factory=Block)
    catch_clauses: List[CatchClause] = field(default_factory=list)
    finally_block: Optional[Block] = None


@dataclass
class ReturnStatement(Statement):
    expression: Optional[Expression] = None


@dataclass
class IdentifierExpression(Expression):
    name: str = ""


@dataclass
class LiteralExpression(Expression):
    value: str = ""
    literal_type: str = "STRING"


@dataclass
class FieldAccessExpression(Expression):
    target: Expression = field(default_factory=Expression)
    field_name: str = ""


@dataclass
class MethodInvocation(Expression):
    select: Optional[Expression] = None  # None indicates implicit `this`
    method_name: str = ""
    arguments: List[Expression] = field(default_factory=list)


@dataclass
class BinaryExpression(Expression):
    left: Expression = field(default_factory=Expression)
    operator: str = ""
    right: Expression = field(default_factory=Expression)


@dataclass
class MethodDeclaration(JavaASTNode):
    annotations: List[AnnotationNode] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    name: str = ""
    parameters: List[MethodParameter] = field(default_factory=list)
    throws_types: List[str] = field(default_factory=list)
    body: Optional[str] = None
    body_block: Optional[Block] = None
    statements: List[Statement] = field(default_factory=list)


@dataclass
class TypeDeclaration(JavaASTNode):
    annotations: List[AnnotationNode] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)
    kind: str = "class"  # class, interface, enum, record
    name: str = ""
    extends_clause_start: Optional[int] = None
    extends_clause_end: Optional[int] = None
    implements_clause_start: Optional[int] = None
    implements_clause_end: Optional[int] = None
    extends_types: List[TypeReference] = field(default_factory=list)
    implements_types: List[TypeReference] = field(default_factory=list)
    members: List[JavaASTNode] = field(default_factory=list)


@dataclass
class CompilationUnit(JavaASTNode):
    package_decl: Optional[PackageDeclaration] = None
    imports: List[ImportDeclaration] = field(default_factory=list)
    type_declarations: List[TypeDeclaration] = field(default_factory=list)


# ==============================================================================
# 3. Symbol Resolution Context (Type & Symbol Attribution)
# ==============================================================================

class SymbolResolutionContext:
    """
    Maintains imported packages and type hierarchies to resolve unqualified symbols
    to canonical Spring, Jakarta, and Java symbols.
    """

    KNOWN_CANONICAL_SYMBOLS: Dict[str, str] = {
        "RequestMapping": "org.springframework.web.bind.annotation.RequestMapping",
        "GetMapping": "org.springframework.web.bind.annotation.GetMapping",
        "PostMapping": "org.springframework.web.bind.annotation.PostMapping",
        "PutMapping": "org.springframework.web.bind.annotation.PutMapping",
        "DeleteMapping": "org.springframework.web.bind.annotation.DeleteMapping",
        "PatchMapping": "org.springframework.web.bind.annotation.PatchMapping",
        "RequestMethod": "org.springframework.web.bind.annotation.RequestMethod",
        "RequestMethod.GET": "org.springframework.web.bind.annotation.RequestMethod.GET",
        "RequestMethod.POST": "org.springframework.web.bind.annotation.RequestMethod.POST",
        "RequestMethod.PUT": "org.springframework.web.bind.annotation.RequestMethod.PUT",
        "RequestMethod.DELETE": "org.springframework.web.bind.annotation.RequestMethod.DELETE",
        "RequestMethod.PATCH": "org.springframework.web.bind.annotation.RequestMethod.PATCH",
        "WebMvcConfigurerAdapter": "org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter",
        "WebMvcConfigurer": "org.springframework.web.servlet.config.annotation.WebMvcConfigurer",
        "RestController": "org.springframework.web.bind.annotation.RestController",
        "Controller": "org.springframework.stereotype.Controller",
        "Configuration": "org.springframework.context.annotation.Configuration",
    }

    def __init__(self, imports: Sequence[ImportDeclaration] = ()):
        self.explicit_imports: Dict[str, str] = {}
        self.wildcard_imports: List[str] = []
        for imp in imports:
            if imp.is_wildcard:
                self.wildcard_imports.append(imp.name)
            else:
                simple = imp.name.split(".")[-1]
                self.explicit_imports[simple] = imp.name

    def resolve(self, symbol: str) -> str:
        if "." in symbol:
            prefix = symbol.split(".")[0]
            if prefix in self.explicit_imports:
                return self.explicit_imports[prefix] + symbol[len(prefix):]
        if symbol in self.explicit_imports:
            return self.explicit_imports[symbol]
        if symbol in self.KNOWN_CANONICAL_SYMBOLS:
            return self.KNOWN_CANONICAL_SYMBOLS[symbol]
        return symbol


# ==============================================================================
# 4. Compiler-grade Parser
# ==============================================================================

class JavaASTParser:
    """
    Parses Java source tokens into a strongly typed, attribute-resolved CompilationUnit AST.
    """

    def __init__(self, tokens: List[Token], source: str = ""):
        self.tokens = tokens
        self.length = len(tokens)
        self.source = source
        self.pos = 0

    def parse(self) -> CompilationUnit:
        unit = CompilationUnit()

        # Parse Package
        if self._peek_keyword("package"):
            unit.package_decl = self._parse_package()

        # Parse Imports
        while True:
            if self._peek_keyword("import"):
                unit.imports.append(self._parse_import())
            else:
                break

        ctx = SymbolResolutionContext(unit.imports)

        # Parse Type Declarations
        while self.pos < self.length:
            if self._peek_token(TokenType.EOF):
                break
            type_decl = self._parse_type_declaration(ctx)
            if type_decl:
                unit.type_declarations.append(type_decl)
            else:
                self.pos += 1

        return unit

    def _peek(self, offset: int = 0) -> Optional[Token]:
        idx = self.pos + offset
        return self.tokens[idx] if idx < self.length else None

    def _peek_token(self, ttype: TokenType, offset: int = 0) -> bool:
        tok = self._peek(offset)
        return tok is not None and tok.type == ttype

    def _peek_keyword(self, kw: str, offset: int = 0) -> bool:
        tok = self._peek(offset)
        return tok is not None and tok.type == TokenType.KEYWORD and tok.value == kw

    def _parse_package(self) -> PackageDeclaration:
        pkg_tok = self.tokens[self.pos]
        start_offset = pkg_tok.start
        self.pos += 1  # 'package'
        parts = []
        end_offset = pkg_tok.end
        while self.pos < self.length:
            tok = self.tokens[self.pos]
            if tok.value == ";":
                end_offset = tok.end
                self.pos += 1
                break
            parts.append(tok.value)
            self.pos += 1
        name = "".join(parts).strip()
        decl = PackageDeclaration(name=name, start_offset=start_offset, end_offset=end_offset)
        decl.leading_trivia = pkg_tok.leading_trivia
        decl.prefix_space = Space.build(pkg_tok.leading_trivia)
        return decl

    def _parse_import(self) -> ImportDeclaration:
        imp_tok = self.tokens[self.pos]
        start_offset = imp_tok.start
        self.pos += 1  # 'import'
        is_static = False
        if self._peek_keyword("static"):
            is_static = True
            self.pos += 1

        parts = []
        is_wildcard = False
        end_offset = imp_tok.end
        while self.pos < self.length:
            tok = self.tokens[self.pos]
            if tok.value == ";":
                end_offset = tok.end
                self.pos += 1
                break
            if tok.value == "*":
                is_wildcard = True
            parts.append(tok.value)
            self.pos += 1

        name = "".join(parts).strip()
        decl = ImportDeclaration(
            name=name,
            is_static=is_static,
            is_wildcard=is_wildcard,
            start_offset=start_offset,
            end_offset=end_offset
        )
        decl.leading_trivia = imp_tok.leading_trivia
        decl.prefix_space = Space.build(imp_tok.leading_trivia)
        return decl

    def _parse_type_declaration(self, ctx: SymbolResolutionContext) -> Optional[TypeDeclaration]:
        annotations: List[AnnotationNode] = []
        leading_trivia = ""
        type_start_offset = None

        # Read annotations preceding type
        while self._peek_token(TokenType.ANNOTATION_AT):
            anno = self._parse_annotation(ctx)
            if type_start_offset is None:
                type_start_offset = anno.start_offset
            if not leading_trivia:
                leading_trivia = anno.leading_trivia
            annotations.append(anno)

        modifiers: List[str] = []
        while self.pos < self.length:
            tok = self._peek()
            if not tok:
                break
            if tok.type == TokenType.KEYWORD and tok.value in (
                "public", "protected", "private", "static", "final", "abstract", "strictfp", "sealed", "non-sealed"
            ):
                if type_start_offset is None:
                    type_start_offset = tok.start
                if not leading_trivia and tok.leading_trivia:
                    leading_trivia = tok.leading_trivia
                modifiers.append(tok.value)
                self.pos += 1
            else:
                break

        tok = self._peek()
        if not tok or tok.type != TokenType.KEYWORD or tok.value not in ("class", "interface", "enum", "record"):
            return None

        if type_start_offset is None:
            type_start_offset = tok.start

        kind = tok.value
        self.pos += 1  # class/interface/enum/record

        name_tok = self._peek()
        name = name_tok.value if name_tok else ""
        if name_tok:
            self.pos += 1

        # Extends & Implements
        extends_types: List[TypeReference] = []
        implements_types: List[TypeReference] = []
        extends_clause_start = None
        extends_clause_end = None
        implements_clause_start = None
        implements_clause_end = None

        while self.pos < self.length:
            tok = self._peek()
            if not tok or tok.value == "{":
                break
            if tok.type == TokenType.KEYWORD and tok.value == "extends":
                extends_clause_start = tok.start
                self.pos += 1
                while self.pos < self.length:
                    t = self._peek()
                    if not t or t.value in ("{", "implements"):
                        break
                    if t.type == TokenType.IDENTIFIER:
                        resolved = ctx.resolve(t.value)
                        extends_types.append(TypeReference(
                            name=t.value,
                            resolved_type=resolved,
                            start_offset=t.start,
                            end_offset=t.end
                        ))
                    extends_clause_end = t.end
                    self.pos += 1
                continue

            if tok.type == TokenType.KEYWORD and tok.value == "implements":
                implements_clause_start = tok.start
                self.pos += 1
                while self.pos < self.length:
                    t = self._peek()
                    if not t or t.value in ("{", "extends"):
                        break
                    if t.type == TokenType.IDENTIFIER:
                        resolved = ctx.resolve(t.value)
                        implements_types.append(TypeReference(
                            name=t.value,
                            resolved_type=resolved,
                            start_offset=t.start,
                            end_offset=t.end
                        ))
                    implements_clause_end = t.end
                    self.pos += 1
                continue

            self.pos += 1

        # Body parsing
        members: List[JavaASTNode] = []
        type_end_offset = self.pos

        if self._peek() and self._peek().value == "{":
            depth = 1
            self.pos += 1
            while self.pos < self.length and depth > 0:
                t = self._peek()
                if t.value == "{":
                    depth += 1
                elif t.value == "}":
                    depth -= 1
                    if depth == 0:
                        type_end_offset = t.end
                        self.pos += 1
                        break

                # Parse method declarations inside class body
                # Parse method declarations inside class body (annotated or unannotated)
                if depth == 1 and (
                    t.type == TokenType.ANNOTATION_AT
                    or (t.type == TokenType.KEYWORD and t.value in (
                        "public", "protected", "private", "static", "final", "abstract", "default", "synchronized", "void"
                    ))
                    or t.type == TokenType.IDENTIFIER
                ):
                    method_decl = self._try_parse_method(ctx)
                    if method_decl:
                        members.append(method_decl)
                        continue
                self.pos += 1

        type_node = TypeDeclaration(
            annotations=annotations,
            modifiers=modifiers,
            kind=kind,
            name=name,
            extends_clause_start=extends_clause_start,
            extends_clause_end=extends_clause_end,
            implements_clause_start=implements_clause_start,
            implements_clause_end=implements_clause_end,
            extends_types=extends_types,
            implements_types=implements_types,
            members=members,
            leading_trivia=leading_trivia,
            start_offset=type_start_offset or 0,
            end_offset=type_end_offset
        )
        type_node.prefix_space = Space.build(leading_trivia)
        for anno in annotations:
            anno.parent = type_node
        for m in members:
            m.parent = type_node
        return type_node

    def _parse_annotation(self, ctx: SymbolResolutionContext) -> AnnotationNode:
        at_tok = self.tokens[self.pos]
        start_offset = at_tok.start
        self.pos += 1  # '@'
        name_tok = self.tokens[self.pos]
        end_offset = name_tok.end
        self.pos += 1  # annotation name

        resolved_type = ctx.resolve(name_tok.value)
        arguments: List[AnnotationArgument] = []

        if self._peek() and self._peek().value == "(":
            self.pos += 1  # '('
            current_arg_name: Optional[str] = None
            current_arg_tokens: List[str] = []

            while self.pos < self.length:
                tok = self._peek()
                if not tok or tok.value == ")":
                    if current_arg_tokens:
                        val = "".join(current_arg_tokens).strip()
                        arguments.append(AnnotationArgument(
                            name=current_arg_name,
                            value=val,
                            resolved_symbol=ctx.resolve(val)
                        ))
                    if tok and tok.value == ")":
                        end_offset = tok.end
                        self.pos += 1
                    break

                if tok.value == "=" and len(current_arg_tokens) == 1 and current_arg_tokens[0].isidentifier():
                    current_arg_name = current_arg_tokens[0]
                    current_arg_tokens = []
                    self.pos += 1
                    continue

                if tok.value == ",":
                    val = "".join(current_arg_tokens).strip()
                    arguments.append(AnnotationArgument(
                        name=current_arg_name,
                        value=val,
                        resolved_symbol=ctx.resolve(val)
                    ))
                    current_arg_name = None
                    current_arg_tokens = []
                    self.pos += 1
                    continue

                current_arg_tokens.append(tok.value)
                self.pos += 1

        anno = AnnotationNode(
            name=name_tok.value,
            arguments=arguments,
            resolved_type=resolved_type,
            start_offset=start_offset,
            end_offset=end_offset
        )
        anno.leading_trivia = at_tok.leading_trivia
        anno.prefix_space = Space.build(at_tok.leading_trivia)
        for arg in arguments:
            arg.parent = anno
        return anno

    def _try_parse_method(self, ctx: SymbolResolutionContext) -> Optional[MethodDeclaration]:
        save_pos = self.pos
        annotations: List[AnnotationNode] = []
        leading_trivia = ""
        method_start = None

        while self._peek_token(TokenType.ANNOTATION_AT):
            anno = self._parse_annotation(ctx)
            if method_start is None:
                method_start = anno.start_offset
            if not leading_trivia:
                leading_trivia = anno.leading_trivia
            annotations.append(anno)

        modifiers: List[str] = []
        while self.pos < self.length:
            t = self._peek()
            if not t:
                break
            if t.type == TokenType.KEYWORD and t.value in (
                "public", "protected", "private", "static", "final", "abstract", "synchronized", "default"
            ):
                if method_start is None:
                    method_start = t.start
                modifiers.append(t.value)
                self.pos += 1
            else:
                break

        # Return type (may include generics, e.g. List<Order>)
        type_parts = []
        while self.pos < self.length:
            t = self._peek()
            if not t or t.value in ("(", "{", ";"):
                break
            if len(type_parts) >= 1 and self._peek(1) and self._peek(1).value == "(":
                break
            type_parts.append(t.value)
            self.pos += 1

        method_name_tok = self._peek()
        if not method_name_tok or method_name_tok.type != TokenType.IDENTIFIER:
            self.pos = save_pos
            return None

        method_name = method_name_tok.value
        self.pos += 1

        if not self._peek() or self._peek().value != "(":
            self.pos = save_pos
            return None

        self.pos += 1  # '('
        param_depth = 1
        param_tokens: List[Token] = []
        parameters: List[MethodParameter] = []

        while self.pos < self.length and param_depth > 0:
            t = self._peek()
            if not t:
                break
            if t.value == "(":
                param_depth += 1
                param_tokens.append(t)
            elif t.value == ")":
                param_depth -= 1
                if param_depth == 0:
                    if param_tokens:
                        parameters.append(self._build_method_param(param_tokens))
                    self.pos += 1
                    break
                else:
                    param_tokens.append(t)
            elif t.value == "," and param_depth == 1:
                if param_tokens:
                    parameters.append(self._build_method_param(param_tokens))
                param_tokens = []
            else:
                param_tokens.append(t)
            self.pos += 1

        method_end = self.pos
        # Parse body and structured statements
        body_content = None
        body_tokens: List[Token] = []
        while self.pos < self.length:
            t = self._peek()
            if not t or t.value in (";", "{"):
                if t and t.value == "{":
                    body_start_offset = t.start
                    body_depth = 1
                    self.pos += 1
                    while self.pos < self.length and body_depth > 0:
                        bt = self._peek()
                        if not bt:
                            break
                        if bt.value == "{":
                            body_depth += 1
                        elif bt.value == "}":
                            body_depth -= 1
                            if body_depth == 0:
                                method_end = bt.end
                                self.pos += 1
                                break
                        body_tokens.append(bt)
                        method_end = bt.end
                        self.pos += 1
                    if self.source:
                        body_content = self.source[body_start_offset:method_end]
                elif t and t.value == ";":
                    method_end = t.end
                    self.pos += 1
                break
            self.pos += 1

        parsed_statements: List[Statement] = []
        parsed_block: Optional[Block] = None
        if body_tokens:
            stmt_parser = JavaStatementParser(body_tokens)
            parsed_block = stmt_parser.parse_block()
            parsed_statements = parsed_block.statements

        decl = MethodDeclaration(
            annotations=annotations,
            modifiers=modifiers,
            return_type="".join(type_parts).strip(),
            name=method_name,
            parameters=parameters,
            leading_trivia=leading_trivia,
            start_offset=method_start or 0,
            end_offset=method_end,
            body=body_content,
            body_block=parsed_block,
            statements=parsed_statements
        )
        decl.prefix_space = Space.build(leading_trivia)
        if parsed_block:
            parsed_block.parent = decl
        for s in parsed_statements:
            s.parent = decl
        for param in parameters:
            param.parent = decl
        for anno in annotations:
            anno.parent = decl
        return decl

    def _build_method_param(self, tokens: List[Token]) -> MethodParameter:
        if not tokens:
            return MethodParameter(type_name="", name="")
        name = tokens[-1].value
        type_parts = [t.value for t in tokens[:-1] if t.type != TokenType.ANNOTATION_AT]
        type_name = "".join(type_parts).strip()
        param = MethodParameter(type_name=type_name, name=name)
        param.start_offset = tokens[0].start
        param.end_offset = tokens[-1].end
        return param


# ==============================================================================
# 5. Compiler-grade Recursive Descent Statement & Expression Parser
# ==============================================================================

class JavaStatementParser:
    """
    Compiler-grade recursive descent parser for Java method bodies,
    constructing strongly typed Statement and Expression AST nodes.
    """

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.length = len(tokens)
        self.pos = 0

    def _peek(self, offset: int = 0) -> Optional[Token]:
        idx = self.pos + offset
        return self.tokens[idx] if idx < self.length else None

    def _consume(self, val: Optional[str] = None) -> Optional[Token]:
        if self.pos < self.length:
            t = self.tokens[self.pos]
            if val is None or t.value == val:
                self.pos += 1
                return t
        return None

    def parse_block(self) -> Block:
        block = Block()
        while self.pos < self.length:
            tok = self._peek()
            if not tok or tok.value == "}":
                break
            stmt = self.parse_statement()
            if stmt:
                stmt.parent = block
                block.statements.append(stmt)
            else:
                self.pos += 1
        return block

    def parse_statement(self) -> Optional[Statement]:
        tok = self._peek()
        if not tok:
            return None

        # 1. Nested Block { ... }
        if tok.value == "{":
            self._consume("{")
            inner_block = self.parse_block()
            self._consume("}")
            return inner_block

        # 2. if (...) stmt [else stmt]
        if tok.value == "if":
            return self._parse_if()

        # 3. while (...) stmt
        if tok.value == "while":
            return self._parse_while()

        # 4. for (...) stmt
        if tok.value == "for":
            return self._parse_for()

        # 5. try { ... } catch (...) { ... } finally { ... }
        if tok.value == "try":
            return self._parse_try()

        # 6. return [expr];
        if tok.value == "return":
            return self._parse_return()

        # 7. Semicolon empty statement
        if tok.value == ";":
            self._consume(";")
            return None

        # 8. Variable declaration or Expression statement
        return self._parse_var_or_expression_statement()

    def _parse_if(self) -> IfStatement:
        self._consume("if")
        self._consume("(")
        cond_tokens: List[Token] = []
        paren_depth = 1
        while self.pos < self.length and paren_depth > 0:
            t = self._consume()
            if not t:
                break
            if t.value == "(":
                paren_depth += 1
                cond_tokens.append(t)
            elif t.value == ")":
                paren_depth -= 1
                if paren_depth > 0:
                    cond_tokens.append(t)
            else:
                cond_tokens.append(t)

        cond_expr = self._parse_expression_from_tokens(cond_tokens)
        then_stmt = self._parse_sub_statement()

        else_stmt: Optional[Statement] = None
        if self._peek() and self._peek().value == "else":
            self._consume("else")
            else_stmt = self._parse_sub_statement()

        if_node = IfStatement(condition=cond_expr, then_branch=then_stmt, else_branch=else_stmt)
        cond_expr.parent = if_node
        if then_stmt:
            then_stmt.parent = if_node
        if else_stmt:
            else_stmt.parent = if_node
        return if_node

    def _parse_while(self) -> WhileStatement:
        self._consume("while")
        self._consume("(")
        cond_tokens: List[Token] = []
        paren_depth = 1
        while self.pos < self.length and paren_depth > 0:
            t = self._consume()
            if not t:
                break
            if t.value == "(":
                paren_depth += 1
                cond_tokens.append(t)
            elif t.value == ")":
                paren_depth -= 1
                if paren_depth > 0:
                    cond_tokens.append(t)
            else:
                cond_tokens.append(t)

        cond_expr = self._parse_expression_from_tokens(cond_tokens)
        body = self._parse_sub_statement()
        while_node = WhileStatement(condition=cond_expr, body=body)
        cond_expr.parent = while_node
        if body:
            body.parent = while_node
        return while_node

    def _parse_for(self) -> ForStatement:
        self._consume("for")
        self._consume("(")
        paren_depth = 1
        while self.pos < self.length and paren_depth > 0:
            t = self._consume()
            if not t:
                break
            if t.value == "(":
                paren_depth += 1
            elif t.value == ")":
                paren_depth -= 1

        body = self._parse_sub_statement()
        for_node = ForStatement(body=body)
        if body:
            body.parent = for_node
        return for_node

    def _parse_try(self) -> TryCatchFinallyStatement:
        self._consume("try")
        # Handle optional try-with-resources: try (Resource r = ...) { ... }
        if self._peek() and self._peek().value == "(":
            self._consume("(")
            pdepth = 1
            while self.pos < self.length and pdepth > 0:
                t = self._consume()
                if not t:
                    break
                if t.value == "(":
                    pdepth += 1
                elif t.value == ")":
                    pdepth -= 1

        self._consume("{")
        try_block = self.parse_block()
        self._consume("}")

        catch_clauses: List[CatchClause] = []
        while self._peek() and self._peek().value == "catch":
            self._consume("catch")
            self._consume("(")
            c_tokens: List[Token] = []
            pdepth = 1
            while self.pos < self.length and pdepth > 0:
                t = self._consume()
                if not t:
                    break
                if t.value == "(":
                    pdepth += 1
                elif t.value == ")":
                    pdepth -= 1
                    if pdepth == 0:
                        break
                else:
                    c_tokens.append(t)

            param_type = "".join(t.value for t in c_tokens[:-1]) if len(c_tokens) > 1 else (c_tokens[0].value if c_tokens else "")
            param_name = c_tokens[-1].value if c_tokens else ""

            self._consume("{")
            catch_block = self.parse_block()
            self._consume("}")
            clause = CatchClause(param_type=param_type, param_name=param_name, body=catch_block)
            catch_clauses.append(clause)

        finally_block: Optional[Block] = None
        if self._peek() and self._peek().value == "finally":
            self._consume("finally")
            self._consume("{")
            finally_block = self.parse_block()
            self._consume("}")

        try_node = TryCatchFinallyStatement(
            try_block=try_block,
            catch_clauses=catch_clauses,
            finally_block=finally_block
        )
        try_block.parent = try_node
        for c in catch_clauses:
            c.parent = try_node
        if finally_block:
            finally_block.parent = try_node
        return try_node

    def _parse_return(self) -> ReturnStatement:
        self._consume("return")
        expr_tokens: List[Token] = []
        while self.pos < self.length:
            t = self._peek()
            if not t or t.value == ";":
                self._consume(";")
                break
            expr_tokens.append(self._consume())

        expr = self._parse_expression_from_tokens(expr_tokens) if expr_tokens else None
        ret_node = ReturnStatement(expression=expr)
        if expr:
            expr.parent = ret_node
        return ret_node

    def _parse_sub_statement(self) -> Statement:
        if self._peek() and self._peek().value == "{":
            self._consume("{")
            b = self.parse_block()
            self._consume("}")
            return b
        else:
            s = self.parse_statement()
            return s or Block()

    def _parse_var_or_expression_statement(self) -> Statement:
        stmt_tokens: List[Token] = []
        depth = 0
        while self.pos < self.length:
            t = self._peek()
            if not t:
                break
            if t.value in ("{", "(", "["):
                depth += 1
            elif t.value in ("}", ")", "]"):
                depth -= 1

            if t.value == ";" and depth <= 0:
                self._consume(";")
                break
            stmt_tokens.append(self._consume())

        if not stmt_tokens:
            return ExpressionStatement()

        # Variable declaration: Type varName [= expr];
        if len(stmt_tokens) >= 2 and stmt_tokens[0].value not in ("this", "super", "return", "throw", "log"):
            if len(stmt_tokens) == 2 and stmt_tokens[1].type == TokenType.IDENTIFIER:
                return VariableDeclarationStatement(
                    type_name=stmt_tokens[0].value,
                    variable_name=stmt_tokens[1].value
                )
            if len(stmt_tokens) >= 3 and stmt_tokens[1].type == TokenType.IDENTIFIER and stmt_tokens[2].value == "=":
                init_expr = self._parse_expression_from_tokens(stmt_tokens[3:])
                return VariableDeclarationStatement(
                    type_name=stmt_tokens[0].value,
                    variable_name=stmt_tokens[1].value,
                    initializer=init_expr
                )

        expr = self._parse_expression_from_tokens(stmt_tokens)
        return ExpressionStatement(expression=expr)

    def _parse_expression_from_tokens(self, tokens: List[Token]) -> Expression:
        if not tokens:
            return LiteralExpression(value="", literal_type="EMPTY")

        # Scan for method invocation: [target .] method_name ( [args] )
        if tokens[-1].value == ")" and any(t.value == "(" for t in tokens):
            pdepth = 0
            open_idx = -1
            for i in range(len(tokens) - 1, -1, -1):
                if tokens[i].value == ")":
                    pdepth += 1
                elif tokens[i].value == "(":
                    pdepth -= 1
                    if pdepth == 0:
                        open_idx = i
                        break

            if open_idx > 0:
                caller_tokens = tokens[:open_idx]
                arg_tokens = tokens[open_idx + 1:-1]

                args: List[Expression] = []
                curr_arg: List[Token] = []
                arg_depth = 0
                for at in arg_tokens:
                    if at.value in ("(", "{", "["):
                        arg_depth += 1
                    elif at.value in (")", "}", "]"):
                        arg_depth -= 1
                    if at.value == "," and arg_depth == 0:
                        if curr_arg:
                            args.append(self._parse_expression_from_tokens(curr_arg))
                        curr_arg = []
                    else:
                        curr_arg.append(at)
                if curr_arg:
                    args.append(self._parse_expression_from_tokens(curr_arg))

                method_name = caller_tokens[-1].value
                select_expr: Optional[Expression] = None
                if len(caller_tokens) >= 3 and caller_tokens[-2].value == ".":
                    select_expr = self._parse_expression_from_tokens(caller_tokens[:-2])

                return MethodInvocation(
                    select=select_expr,
                    method_name=method_name,
                    arguments=args
                )

        if len(tokens) == 1:
            tok = tokens[0]
            if tok.type == TokenType.IDENTIFIER or tok.value in ("this", "super"):
                return IdentifierExpression(name=tok.value)
            return LiteralExpression(value=tok.value, literal_type="LITERAL")

        if len(tokens) >= 3 and tokens[-2].value == ".":
            return FieldAccessExpression(
                target=self._parse_expression_from_tokens(tokens[:-2]),
                field_name=tokens[-1].value
            )

        return LiteralExpression(value=" ".join(t.value for t in tokens), literal_type="COMPOUND")


# ==============================================================================
# 5. Precise AST Tree Replacement Model
# ==============================================================================

@dataclass
class AstEdit:
    start: int
    end: int
    replacement: str


class JavaASTVisitor:
    """
    Structured AST Visitor. Concrete visitors register precision AstEdits during traversal.
    """

    def __init__(self):
        self.edits: List[AstEdit] = []
        self.rewrites_count: int = 0

    def visit(self, node: JavaASTNode) -> None:
        if isinstance(node, CompilationUnit):
            self.visit_compilation_unit(node)
        elif isinstance(node, ImportDeclaration):
            self.visit_import(node)
        elif isinstance(node, TypeDeclaration):
            self.visit_type_declaration(node)
        elif isinstance(node, MethodDeclaration):
            self.visit_method_declaration(node)
        elif isinstance(node, AnnotationNode):
            self.visit_annotation(node)

    def visit_compilation_unit(self, unit: CompilationUnit) -> None:
        for imp in unit.imports:
            self.visit_import(imp)
        for t in unit.type_declarations:
            self.visit_type_declaration(t)

    def visit_import(self, node: ImportDeclaration) -> None:
        pass

    def visit_type_declaration(self, node: TypeDeclaration) -> None:
        for a in node.annotations:
            self.visit_annotation(a)
        for m in node.members:
            self.visit(m)

    def visit_method_declaration(self, node: MethodDeclaration) -> None:
        for a in node.annotations:
            self.visit_annotation(a)

    def visit_annotation(self, node: AnnotationNode) -> None:
        pass


# ==============================================================================
# 6. Production AST Modernization Visitors
# ==============================================================================

class SpringMvcAnnotationVisitor(JavaASTVisitor):
    """
    Transforms @RequestMapping into modern composed annotations (@GetMapping, @PostMapping, etc.)
    using strongly typed AST node inspection, never regular expressions.
    """

    METHOD_MAP = {
        "GET": "GetMapping",
        "POST": "PostMapping",
        "PUT": "PutMapping",
        "DELETE": "DeleteMapping",
        "PATCH": "PatchMapping",
    }

    def visit_annotation(self, node: AnnotationNode) -> None:
        if node.name != "RequestMapping" and node.resolved_type != "org.springframework.web.bind.annotation.RequestMapping":
            return

        method_arg = node.get_arg("method")
        method_val = None

        if method_arg:
            val_str = method_arg.value.strip()
            if "." in val_str:
                method_val = val_str.split(".")[-1].upper()
            else:
                method_val = val_str.upper()

        if method_val and method_val in self.METHOD_MAP:
            composed_name = self.METHOD_MAP[method_val]
            path_arg = node.get_value_arg()

            # Preserve other arguments (e.g. consumes, produces, headers, params)
            other_args = [a for a in node.arguments if a.name not in ("method", "value", "path") and a is not path_arg]

            new_args_str = []
            if path_arg and path_arg.value:
                if other_args or path_arg.name in ("value", "path"):
                    new_args_str.append(path_arg.value if not other_args else f"value = {path_arg.value}")
                else:
                    new_args_str.append(path_arg.value)

            for oa in other_args:
                new_args_str.append(f"{oa.name} = {oa.value}" if oa.name else oa.value)

            args_content = f"({', '.join(new_args_str)})" if new_args_str else ""
            replacement = f"@{composed_name}{args_content}"

            self.edits.append(AstEdit(start=node.start_offset, end=node.end_offset, replacement=replacement))
            self.rewrites_count += 1


class WebMvcConfigurerAdapterVisitor(JavaASTVisitor):
    """
    Transforms 'extends WebMvcConfigurerAdapter' to 'implements WebMvcConfigurer'
    at the AST TypeDeclaration level and updates import declarations.
    """

    def visit_type_declaration(self, node: TypeDeclaration) -> None:
        super().visit_type_declaration(node)

        adapter_ext = None
        for ext in node.extends_types:
            if ext.name == "WebMvcConfigurerAdapter" or (ext.resolved_type and ext.resolved_type.endswith("WebMvcConfigurerAdapter")):
                adapter_ext = ext
                break

        if adapter_ext and node.extends_clause_start is not None and node.extends_clause_end is not None:
            # Check if class already had other implements
            if node.implements_types and node.implements_clause_start is not None:
                # Replace extends clause entirely, add WebMvcConfigurer to implements
                self.edits.append(AstEdit(
                    start=node.extends_clause_start,
                    end=node.extends_clause_end,
                    replacement=""
                ))
                self.edits.append(AstEdit(
                    start=node.implements_clause_start,
                    end=node.implements_clause_start + len("implements"),
                    replacement="implements WebMvcConfigurer,"
                ))
            else:
                # Replace extends WebMvcConfigurerAdapter with implements WebMvcConfigurer
                self.edits.append(AstEdit(
                    start=node.extends_clause_start,
                    end=node.extends_clause_end,
                    replacement="implements WebMvcConfigurer"
                ))
            self.rewrites_count += 1

    def visit_import(self, node: ImportDeclaration) -> None:
        if node.name == "org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter":
            self.edits.append(AstEdit(
                start=node.start_offset,
                end=node.end_offset,
                replacement="import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;"
            ))
            self.rewrites_count += 1


# ==============================================================================
# 7. AST Rewriter Engine (Non-destructive Precision Transformation)
# ==============================================================================

class JavaASTRewriter:
    """
    Executes visitors against a Java source string and applies precision AST edits.
    """

    @classmethod
    def rewrite_spring_mvc_annotations(cls, code: str) -> Tuple[str, int]:
        lexer = JavaLexer(code)
        tokens = lexer.tokenize()
        parser = JavaASTParser(tokens)
        unit = parser.parse()

        visitor = SpringMvcAnnotationVisitor()
        visitor.visit(unit)

        if visitor.rewrites_count == 0:
            return code, 0

        # Apply edits backwards to preserve offsets
        res = code
        for edit in sorted(visitor.edits, key=lambda e: e.start, reverse=True):
            res = res[:edit.start] + edit.replacement + res[edit.end:]

        return res, visitor.rewrites_count

    @classmethod
    def rewrite_webmvc_configurer_adapter(cls, code: str) -> Tuple[str, int]:
        lexer = JavaLexer(code)
        tokens = lexer.tokenize()
        parser = JavaASTParser(tokens)
        unit = parser.parse()

        visitor = WebMvcConfigurerAdapterVisitor()
        visitor.visit(unit)

        if visitor.rewrites_count == 0:
            return code, 0

        res = code
        for edit in sorted(visitor.edits, key=lambda e: e.start, reverse=True):
            res = res[:edit.start] + edit.replacement + res[edit.end:]

        return res, visitor.rewrites_count

    @classmethod
    def rewrite_with_lst(
        cls,
        code: str,
        mutator_fn: Any
    ) -> Tuple[str, int]:
        """
        Parses source code into a CompilationUnit LST, executes in-memory tree mutations
        via JavaLSTMutator, and formats the output via AutoFormatVisitor.
        Completely immune to coordinate drift, string scanning, and regular expressions.
        """
        lexer = JavaLexer(code)
        tokens = lexer.tokenize()
        parser = JavaASTParser(tokens, source=code)
        unit = parser.parse()

        mutator = JavaLSTMutator(unit)
        mutator_fn(mutator)

        if mutator.mutations_count == 0:
            return code, 0

        formatter = AutoFormatVisitor()
        formatted_code = formatter.format(unit)
        return formatted_code, mutator.mutations_count


# ==============================================================================
# 8. LST Mutator & AutoFormat Engine (Pure Tree Mutation & Reconstruction)
# ==============================================================================

class JavaLSTMutator:
    """
    Direct in-memory tree mutator for Lossless Semantic Trees (LST).
    Executes node additions, removals, and replacements without textual coordinates.
    """

    def __init__(self, unit: CompilationUnit):
        self.unit = unit
        self.mutations_count = 0

    def add_import(self, import_fqcn: str, is_static: bool = False) -> None:
        for imp in self.unit.imports:
            if imp.name == import_fqcn and imp.is_static == is_static:
                return
        decl = ImportDeclaration(name=import_fqcn, is_static=is_static)
        decl.prefix_space = Space(whitespace="\n")
        self.unit.imports.append(decl)
        self.mutations_count += 1

    def remove_import(self, import_fqcn: str) -> None:
        orig_len = len(self.unit.imports)
        self.unit.imports = [imp for imp in self.unit.imports if imp.name != import_fqcn]
        if len(self.unit.imports) != orig_len:
            self.mutations_count += 1

    def replace_import(self, old_fqcn: str, new_fqcn: str) -> bool:
        for imp in self.unit.imports:
            if imp.name == old_fqcn:
                imp.name = new_fqcn
                self.mutations_count += 1
                return True
        return False

    def replace_annotation(self, holder: JavaASTNode, old_anno_name: str, new_anno: AnnotationNode) -> bool:
        if not hasattr(holder, "annotations"):
            return False
        replaced = False
        new_annos: List[AnnotationNode] = []
        for anno in getattr(holder, "annotations"):
            if anno.name == old_anno_name or (anno.resolved_type and anno.resolved_type.endswith(old_anno_name)):
                new_annos.append(new_anno)
                new_anno.parent = holder
                replaced = True
                self.mutations_count += 1
            else:
                new_annos.append(anno)
        setattr(holder, "annotations", new_annos)
        return replaced

    def replace_extends(self, type_decl: TypeDeclaration, old_extends: str, new_implements: Optional[str] = None) -> bool:
        orig_len = len(type_decl.extends_types)
        type_decl.extends_types = [
            ext for ext in type_decl.extends_types
            if ext.name != old_extends and not (ext.resolved_type and ext.resolved_type.endswith(old_extends))
        ]
        if len(type_decl.extends_types) != orig_len:
            if new_implements:
                if not any(imp.name == new_implements for imp in type_decl.implements_types):
                    type_decl.implements_types.append(TypeReference(name=new_implements, parent=type_decl))
            self.mutations_count += 1
            return True
        return False

    def add_implements(self, type_decl: TypeDeclaration, iface_name: str) -> None:
        if not any(imp.name == iface_name for imp in type_decl.implements_types):
            type_decl.implements_types.append(TypeReference(name=iface_name, parent=type_decl))
            self.mutations_count += 1

    def replace_method_body(self, method_decl: MethodDeclaration, new_body: str) -> None:
        method_decl.body = new_body
        self.mutations_count += 1


class AutoFormatVisitor:
    """
    Renders an in-memory CompilationUnit LST back into formatted Java source text,
    adhering to standard 4-space indentation, preserving attached comments,
    and rendering clean class/method structures without coordinate drift.
    """

    def __init__(self, indent_size: int = 4):
        self.indent_size = indent_size

    def format(self, unit: CompilationUnit) -> str:
        lines: List[str] = []

        # 1. Package
        if unit.package_decl:
            if unit.package_decl.prefix_space.comments:
                for c in unit.package_decl.prefix_space.comments:
                    lines.append(c.text)
            lines.append(f"package {unit.package_decl.name};")
            lines.append("")

        # 2. Imports
        if unit.imports:
            static_imports = [imp for imp in unit.imports if imp.is_static]
            normal_imports = [imp for imp in unit.imports if not imp.is_static]
            for imp in static_imports:
                lines.append(f"import static {imp.name};")
            if static_imports and normal_imports:
                lines.append("")
            for imp in normal_imports:
                lines.append(f"import {imp.name};")
            lines.append("")

        # 3. Types
        for i, type_decl in enumerate(unit.type_declarations):
            if i > 0:
                lines.append("")
            lines.extend(self._format_type_declaration(type_decl, indent_level=0))

        return "\n".join(lines).strip() + "\n"

    def _format_type_declaration(self, decl: TypeDeclaration, indent_level: int) -> List[str]:
        indent = " " * (indent_level * self.indent_size)
        lines: List[str] = []

        if decl.prefix_space.comments:
            for c in decl.prefix_space.comments:
                lines.append(f"{indent}{c.text}")

        for anno in decl.annotations:
            lines.append(f"{indent}{self._format_annotation(anno)}")

        mods = (" ".join(decl.modifiers) + " ") if decl.modifiers else ""
        header_parts = [f"{indent}{mods}{decl.kind} {decl.name}"]

        if decl.extends_types:
            ext_names = ", ".join(ext.name for ext in decl.extends_types)
            header_parts.append(f"extends {ext_names}")

        if decl.implements_types:
            imp_names = ", ".join(imp.name for imp in decl.implements_types)
            header_parts.append(f"implements {imp_names}")

        header = " ".join(header_parts) + " {"
        lines.append(header)

        # Members
        for idx, member in enumerate(decl.members):
            if idx > 0:
                lines.append("")
            if isinstance(member, MethodDeclaration):
                lines.extend(self._format_method(member, indent_level + 1))
            elif isinstance(member, TypeDeclaration):
                lines.extend(self._format_type_declaration(member, indent_level + 1))

        lines.append(f"{indent}}}")
        return lines

    def _format_annotation(self, anno: AnnotationNode) -> str:
        if not anno.arguments:
            return f"@{anno.name}"
        args_str: List[str] = []
        for arg in anno.arguments:
            if arg.name and arg.name != "value":
                args_str.append(f"{arg.name} = {arg.value}")
            elif arg.name == "value" and len(anno.arguments) > 1:
                args_str.append(f"value = {arg.value}")
            else:
                args_str.append(arg.value)
        return f"@{anno.name}({', '.join(args_str)})"

    def _format_method(self, method: MethodDeclaration, indent_level: int) -> List[str]:
        indent = " " * (indent_level * self.indent_size)
        lines: List[str] = []

        if method.prefix_space.comments:
            for c in method.prefix_space.comments:
                lines.append(f"{indent}{c.text}")

        for anno in method.annotations:
            lines.append(f"{indent}{self._format_annotation(anno)}")

        mods = (" ".join(method.modifiers) + " ") if method.modifiers else ""
        ret = (method.return_type + " ") if method.return_type else ""
        params_str = ", ".join(f"{p.type_name} {p.name}" for p in method.parameters)
        throws_str = (" throws " + ", ".join(method.throws_types)) if method.throws_types else ""

        sig = f"{indent}{mods}{ret}{method.name}({params_str}){throws_str}"

        if method.body is None:
            lines.append(f"{sig};")
        else:
            raw_body = method.body.strip()
            # If body already starts and ends with braces, strip outer braces
            if raw_body.startswith("{") and raw_body.endswith("}"):
                inner = raw_body[1:-1].strip()
            else:
                inner = raw_body

            lines.append(f"{sig} {{")
            body_indent = " " * ((indent_level + 1) * self.indent_size)
            for bl in inner.splitlines():
                sbl = bl.strip()
                if sbl:
                    lines.append(f"{body_indent}{sbl}")
            lines.append(f"{indent}}}")

        return lines
