"""A total, side-effect-free predicate language for policies and Recipes.

Policy ``when`` clauses, Recipe ``applicability`` / ``preconditions`` /
``negativeGuards`` / ``postconditions`` and acceptance predicates all evaluate
through this one interpreter.  Requirements that shaped it:

* **Three-valued.**  A missing fact yields :data:`UNKNOWN`, never ``false``.
  The package-wide invariant "unknown is not no-impact" only holds if the
  expression layer refuses to invent a negative.
* **Total and bounded.**  No user input can make evaluation loop, recurse
  without limit, allocate unboundedly or take more than linear time in the
  expression length.  There is no ``eval``, no attribute access on Python
  objects, no comprehension, no function call except a fixed allowlist.
* **Deterministic.**  No clock, no randomness, no environment.

Grammar (LL(1), whitespace insignificant)::

    expr    := or_expr
    or_expr := and_expr ( "or" and_expr )*
    and_expr:= unary ( "and" unary )*
    unary   := "not" unary | comparison
    compare := primary [ op primary ]
    op      := "==" | "!=" | ">=" | "<=" | ">" | "<"
             | "in" | "not in" | "contains" | "matches" | "startswith" | "endswith"
    primary := "(" expr ")" | call | literal | path
    call    := IDENT "(" [ expr ( "," expr )* ] ")"
    path    := IDENT ( "." IDENT | "[" INT "]" )*
    literal := STRING | NUMBER | "true" | "false" | "null" | "[" [ expr ("," expr)* ] "]"
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .contracts import ContractError, match_path_glob


#: Sentinel for "the context does not know".  Distinct from ``None``, which is
#: a *known* null.
class _Unknown:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNKNOWN"

    def __bool__(self) -> bool:
        raise ContractError("unknown_truth_value", "UNKNOWN has no boolean value; handle it explicitly")


UNKNOWN = _Unknown()

#: Public alias for the sentinel's type, so callers can narrow with isinstance
#: without reaching for a private name.
UnknownType = _Unknown

MAX_EXPRESSION_LENGTH = 4096
MAX_DEPTH = 32
MAX_LIST_ITEMS = 512


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<string>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<op><=|>=|==|!=|<|>)
  | (?P<punct>[()\[\],.])
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)

_KEYWORDS = {"and", "or", "not", "in", "contains", "matches", "startswith", "endswith", "true", "false", "null"}


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    position: int


def _tokenize(source: str) -> tuple[_Token, ...]:
    if len(source) > MAX_EXPRESSION_LENGTH:
        raise ContractError("expression_too_long", f"expression exceeds {MAX_EXPRESSION_LENGTH} characters")
    tokens: list[_Token] = []
    index = 0
    while index < len(source):
        match = _TOKEN_RE.match(source, index)
        if match is None:
            raise ContractError("invalid_expression", f"unexpected character at offset {index}")
        index = match.end()
        kind = match.lastgroup or ""
        text = match.group()
        if kind == "ws":
            continue
        if kind == "ident" and text in _KEYWORDS:
            kind = "keyword"
        tokens.append(_Token(kind, text, match.start()))
    tokens.append(_Token("eof", "", len(source)))
    return tuple(tokens)


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Node:
    kind: str
    value: Any = None
    children: tuple[_Node, ...] = ()


class _Parser:
    __slots__ = ("_tokens", "_index", "_depth")

    def __init__(self, tokens: Sequence[_Token]) -> None:
        self._tokens = tokens
        self._index = 0
        self._depth = 0

    # -- helpers ---------------------------------------------------------

    @property
    def _current(self) -> _Token:
        return self._tokens[self._index]

    def _advance(self) -> _Token:
        token = self._tokens[self._index]
        self._index += 1
        return token

    def _expect(self, kind: str, value: str | None = None) -> _Token:
        token = self._current
        if token.kind != kind or (value is not None and token.value != value):
            expected = value or kind
            raise ContractError("invalid_expression", f"expected '{expected}' at offset {token.position}")
        return self._advance()

    def _accept(self, kind: str, value: str | None = None) -> _Token | None:
        token = self._current
        if token.kind == kind and (value is None or token.value == value):
            return self._advance()
        return None

    # -- grammar ---------------------------------------------------------

    def parse(self) -> _Node:
        node = self._or_expr()
        if self._current.kind != "eof":
            raise ContractError("invalid_expression", f"unexpected trailing input at offset {self._current.position}")
        return node

    def _guard(self) -> None:
        if self._depth > MAX_DEPTH:
            raise ContractError("expression_too_deep", f"expression nests deeper than {MAX_DEPTH}")

    def _or_expr(self) -> _Node:
        self._depth += 1
        self._guard()
        node = self._and_expr()
        while self._accept("keyword", "or"):
            node = _Node("or", None, (node, self._and_expr()))
        self._depth -= 1
        return node

    def _and_expr(self) -> _Node:
        node = self._unary()
        while self._accept("keyword", "and"):
            node = _Node("and", None, (node, self._unary()))
        return node

    def _unary(self) -> _Node:
        if self._accept("keyword", "not"):
            self._depth += 1
            self._guard()
            node = _Node("not", None, (self._unary(),))
            self._depth -= 1
            return node
        return self._comparison()

    def _comparison(self) -> _Node:
        left = self._primary()
        token = self._current
        if token.kind == "op":
            self._advance()
            return _Node("compare", token.value, (left, self._primary()))
        if token.kind == "keyword" and token.value in {"in", "contains", "matches", "startswith", "endswith"}:
            self._advance()
            return _Node("compare", token.value, (left, self._primary()))
        if token.kind == "keyword" and token.value == "not":
            # "x not in y"
            save = self._index
            self._advance()
            if self._accept("keyword", "in"):
                return _Node("compare", "not in", (left, self._primary()))
            self._index = save
        return left

    def _primary(self) -> _Node:
        token = self._current
        if token.kind == "punct" and token.value == "(":
            self._advance()
            self._depth += 1
            self._guard()
            node = self._or_expr()
            self._depth -= 1
            self._expect("punct", ")")
            return node
        if token.kind == "punct" and token.value == "[":
            self._advance()
            items: list[_Node] = []
            if not (self._current.kind == "punct" and self._current.value == "]"):
                while True:
                    if len(items) >= MAX_LIST_ITEMS:
                        raise ContractError("expression_too_large", "list literal has too many items")
                    items.append(self._or_expr())
                    if not self._accept("punct", ","):
                        break
            self._expect("punct", "]")
            return _Node("list", None, tuple(items))
        if token.kind == "string":
            self._advance()
            return _Node("literal", _decode_string(token.value))
        if token.kind == "number":
            self._advance()
            return _Node("literal", Decimal(token.value))
        if token.kind == "keyword" and token.value in {"true", "false", "null"}:
            self._advance()
            return _Node("literal", {"true": True, "false": False, "null": None}[token.value])
        if token.kind == "ident":
            self._advance()
            if self._current.kind == "punct" and self._current.value == "(":
                self._advance()
                args: list[_Node] = []
                if not (self._current.kind == "punct" and self._current.value == ")"):
                    while True:
                        args.append(self._or_expr())
                        if not self._accept("punct", ","):
                            break
                self._expect("punct", ")")
                return _Node("call", token.value, tuple(args))
            segments: list[Any] = [token.value]
            while True:
                if self._accept("punct", "."):
                    part = self._current
                    if part.kind not in ("ident", "keyword"):
                        raise ContractError("invalid_expression", f"expected a field name at offset {part.position}")
                    self._advance()
                    segments.append(part.value)
                elif self._accept("punct", "["):
                    number = self._expect("number")
                    self._expect("punct", "]")
                    segments.append(int(number.value))
                else:
                    break
            return _Node("path", tuple(segments))
        raise ContractError("invalid_expression", f"unexpected token at offset {token.position}")


def _decode_string(raw: str) -> str:
    body = raw[1:-1]
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            nxt = body[index + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"'}.get(nxt, nxt))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Built-in functions
# ---------------------------------------------------------------------------


def _fn_len(args: Sequence[Any]) -> Any:
    if len(args) != 1:
        raise ContractError("invalid_expression", "len() takes exactly one argument")
    value = args[0]
    if value is UNKNOWN:
        return UNKNOWN
    if isinstance(value, (str, Sequence, Mapping)):
        return Decimal(len(value))
    return UNKNOWN


def _fn_any(args: Sequence[Any]) -> Any:
    if any(arg is UNKNOWN for arg in args):
        return UNKNOWN
    return any(bool(arg) for arg in args)


def _fn_all(args: Sequence[Any]) -> Any:
    if any(arg is UNKNOWN for arg in args):
        return UNKNOWN
    return all(bool(arg) for arg in args)


def _fn_defined(args: Sequence[Any]) -> Any:
    if len(args) != 1:
        raise ContractError("invalid_expression", "defined() takes exactly one argument")
    return args[0] is not UNKNOWN


def _fn_coalesce(args: Sequence[Any]) -> Any:
    for arg in args:
        if arg is not UNKNOWN and arg is not None:
            return arg
    return UNKNOWN if any(arg is UNKNOWN for arg in args) else None


def _fn_glob(args: Sequence[Any]) -> Any:
    if len(args) != 2:
        raise ContractError("invalid_expression", "glob() takes exactly two arguments")
    subject, pattern = args
    if subject is UNKNOWN or pattern is UNKNOWN:
        return UNKNOWN
    if not isinstance(subject, str) or not isinstance(pattern, str):
        return UNKNOWN
    return match_path_glob(subject, pattern)


def _fn_lower(args: Sequence[Any]) -> Any:
    if len(args) != 1:
        raise ContractError("invalid_expression", "lower() takes exactly one argument")
    value = args[0]
    return value.lower() if isinstance(value, str) else (UNKNOWN if value is UNKNOWN else UNKNOWN)


def _fn_count(args: Sequence[Any]) -> Any:
    """count(collection, predicate_value) is intentionally absent; use len()."""

    raise ContractError("unknown_function", "count() is not available; use len()")


_FUNCTIONS: Mapping[str, Callable[[Sequence[Any]], Any]] = {
    "len": _fn_len,
    "any": _fn_any,
    "all": _fn_all,
    "defined": _fn_defined,
    "coalesce": _fn_coalesce,
    "glob": _fn_glob,
    "lower": _fn_lower,
    "count": _fn_count,
}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _resolve_path(segments: Sequence[Any], context: Mapping[str, Any]) -> Any:
    current: Any = context
    for segment in segments:
        if current is UNKNOWN:
            return UNKNOWN
        if isinstance(segment, int):
            if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
                if 0 <= segment < len(current):
                    current = current[segment]
                    continue
            return UNKNOWN
        if isinstance(current, Mapping):
            if segment in current:
                current = current[segment]
                continue
            return UNKNOWN
        return UNKNOWN
    return current


def _coerce_number(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    return None


def _compare(op: str, left: Any, right: Any) -> Any:
    if left is UNKNOWN or right is UNKNOWN:
        return UNKNOWN
    if op in ("==", "!="):
        left_num, right_num = _coerce_number(left), _coerce_number(right)
        if left_num is not None and right_num is not None:
            equal = left_num == right_num
        else:
            equal = left == right
        return equal if op == "==" else not equal
    if op in ("<", "<=", ">", ">="):
        left_num, right_num = _coerce_number(left), _coerce_number(right)
        if left_num is None or right_num is None:
            if isinstance(left, str) and isinstance(right, str):
                left_num, right_num = None, None
            else:
                return UNKNOWN
        if left_num is not None and right_num is not None:
            comparison = (left_num > right_num) - (left_num < right_num)
        elif isinstance(left, str) and isinstance(right, str):
            comparison = (left > right) - (left < right)
        else:
            return UNKNOWN
        return {"<": comparison < 0, "<=": comparison <= 0, ">": comparison > 0, ">=": comparison >= 0}[op]
    if op in ("in", "not in"):
        if isinstance(right, Mapping):
            contained = left in right
        elif isinstance(right, str):
            contained = isinstance(left, str) and left in right
        elif isinstance(right, Sequence):
            contained = any(_compare("==", left, item) is True for item in right)
        else:
            return UNKNOWN
        return contained if op == "in" else not contained
    if op == "contains":
        return _compare("in", right, left)
    if op == "matches":
        if not isinstance(left, str) or not isinstance(right, str):
            return UNKNOWN
        return match_path_glob(left, right)
    if op == "startswith":
        if not isinstance(left, str) or not isinstance(right, str):
            return UNKNOWN
        return left.startswith(right)
    if op == "endswith":
        if not isinstance(left, str) or not isinstance(right, str):
            return UNKNOWN
        return left.endswith(right)
    raise ContractError("invalid_expression", f"unsupported operator '{op}'")


def _truthy(value: Any) -> Any:
    if value is UNKNOWN:
        return UNKNOWN
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, Decimal):
        return value != 0
    if isinstance(value, (str, Sequence, Mapping)):
        return len(value) > 0
    return bool(value)


def _evaluate(node: _Node, context: Mapping[str, Any]) -> Any:
    kind = node.kind
    if kind == "literal":
        return node.value
    if kind == "path":
        return _resolve_path(node.value, context)
    if kind == "list":
        return [_evaluate(child, context) for child in node.children]
    if kind == "call":
        function = _FUNCTIONS.get(node.value)
        if function is None:
            raise ContractError("unknown_function", f"unknown function '{node.value}'")
        return function([_evaluate(child, context) for child in node.children])
    if kind == "not":
        inner = _truthy(_evaluate(node.children[0], context))
        return UNKNOWN if inner is UNKNOWN else not inner
    if kind == "and":
        left = _truthy(_evaluate(node.children[0], context))
        if left is False:
            return False  # short-circuit keeps `false and unknown` decidable
        right = _truthy(_evaluate(node.children[1], context))
        if right is False:
            return False
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        return True
    if kind == "or":
        left = _truthy(_evaluate(node.children[0], context))
        if left is True:
            return True
        right = _truthy(_evaluate(node.children[1], context))
        if right is True:
            return True
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN
        return False
    if kind == "compare":
        return _compare(node.value, _evaluate(node.children[0], context), _evaluate(node.children[1], context))
    raise ContractError("invalid_expression", f"unsupported node '{kind}'")  # pragma: no cover


@dataclass(frozen=True, slots=True)
class Expression:
    """A parsed, reusable predicate."""

    source: str
    _root: _Node

    def evaluate(self, context: Mapping[str, Any]) -> Any:
        """Return ``True``, ``False`` or :data:`UNKNOWN`."""

        return _truthy(_evaluate(self._root, context))

    def evaluate_value(self, context: Mapping[str, Any]) -> Any:
        """Return the raw value (not coerced to a truth value)."""

        return _evaluate(self._root, context)

    @property
    def referenced_paths(self) -> tuple[str, ...]:
        """Every context path the expression reads, for coverage reporting."""

        found: set[str] = set()

        def walk(node: _Node) -> None:
            if node.kind == "path":
                found.add(".".join(str(part) for part in node.value))
            for child in node.children:
                walk(child)

        walk(self._root)
        return tuple(sorted(found))


_CACHE: dict[str, Expression] = {}
_CACHE_LIMIT = 2048


def compile_expression(source: str) -> Expression:
    """Parse ``source`` once and memoise it (bounded cache)."""

    if not isinstance(source, str):
        raise ContractError("invalid_expression", "expression must be a string")
    text = source.strip()
    if not text:
        raise ContractError("invalid_expression", "expression must not be empty")
    cached = _CACHE.get(text)
    if cached is not None:
        return cached
    expression = Expression(text, _Parser(_tokenize(text)).parse())
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[text] = expression
    return expression


def evaluate_expression(source: str, context: Mapping[str, Any]) -> Any:
    return compile_expression(source).evaluate(context)


__all__ = [
    "Expression",
    "MAX_DEPTH",
    "MAX_EXPRESSION_LENGTH",
    "UNKNOWN",
    "UnknownType",
    "compile_expression",
    "evaluate_expression",
]
