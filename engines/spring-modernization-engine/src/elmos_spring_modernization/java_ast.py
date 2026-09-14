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
class JavaASTNode:
    parent: Optional[JavaASTNode] = field(default=None, repr=False)
    leading_trivia: str = ""
    trailing_trivia: str = ""
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


@dataclass
class MethodDeclaration(JavaASTNode):
    annotations: List[AnnotationNode] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    name: str = ""
    parameters: List[MethodParameter] = field(default_factory=list)
    throws_types: List[str] = field(default_factory=list)
    body: Optional[str] = None


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

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.length = len(tokens)
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
                if depth == 1 and t.type == TokenType.ANNOTATION_AT:
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
        while self.pos < self.length and param_depth > 0:
            t = self._peek()
            if t.value == "(":
                param_depth += 1
            elif t.value == ")":
                param_depth -= 1
            self.pos += 1

        method_end = self.pos
        # Skip throws or body
        while self.pos < self.length:
            t = self._peek()
            if not t or t.value in (";", "{"):
                if t and t.value == "{":
                    body_depth = 1
                    self.pos += 1
                    while self.pos < self.length and body_depth > 0:
                        bt = self._peek()
                        if bt.value == "{":
                            body_depth += 1
                        elif bt.value == "}":
                            body_depth -= 1
                        method_end = bt.end
                        self.pos += 1
                elif t and t.value == ";":
                    method_end = t.end
                    self.pos += 1
                break
            self.pos += 1

        return MethodDeclaration(
            annotations=annotations,
            modifiers=modifiers,
            return_type="".join(type_parts).strip(),
            name=method_name,
            leading_trivia=leading_trivia,
            start_offset=method_start or 0,
            end_offset=method_end
        )


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
