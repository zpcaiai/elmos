"""Unified Semantic IR (UIR) for cross-language migration.

Design rules that the rest of the engine depends on:

1.  Every node is a frozen dataclass with an explicit ``KIND``.  There is no
    "generic node with a dict of attributes" escape hatch, because that is how
    unsupported constructs get silently smuggled through a front end.
2.  Serialization is *canonical*: sorted keys, no insignificant whitespace,
    UTF-8, and floats are rejected outright (they have no single textual
    representation that survives a round trip on every platform).  The digest of
    a UIR module is therefore a stable content address.
3.  Every node carries an ``Origin`` (file, line, column) so that any downstream
    finding can be traced back to a concrete source location.  Emitters are
    required to preserve it; the source-map test enforces that.

The IR is deliberately *typed at the Java level of detail* for primitives.  A
front end that erases ``int`` into "number" makes it impossible to reproduce
32-bit wrapping downstream, and 32-bit wrapping is exactly the class of bug a
migration is supposed to not introduce.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Iterable, Sequence

UIR_VERSION = "1.0.0"


class UirError(Exception):
    """Raised when the IR is constructed or consumed in an invalid way."""


# ---------------------------------------------------------------------------
# Origin
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Origin:
    """A source location.  Line and column are 1-based, matching javac."""

    file: str
    line: int
    column: int

    def __post_init__(self) -> None:
        if self.line < 1 or self.column < 1:
            raise UirError(f"origin must be 1-based, got {self.line}:{self.column}")


UNKNOWN_ORIGIN = Origin(file="<unknown>", line=1, column=1)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PRIMITIVE_NAMES = (
    "boolean",
    "byte",
    "char",
    "double",
    "float",
    "int",
    "long",
    "short",
    "void",
)

#: Width in bits of each integral primitive.  Used by the emitter to pick the
#: correct wrapping helper.  ``char`` is unsigned; everything else is signed.
INTEGRAL_WIDTH = {"byte": 8, "short": 16, "char": 16, "int": 32, "long": 64}
UNSIGNED_INTEGRAL = frozenset({"char"})
FLOATING = frozenset({"float", "double"})


@dataclass(frozen=True)
class Type:
    KIND = "Type"


@dataclass(frozen=True)
class PrimitiveType(Type):
    KIND = "PrimitiveType"
    name: str

    def __post_init__(self) -> None:
        if self.name not in PRIMITIVE_NAMES:
            raise UirError(f"unknown primitive type: {self.name!r}")

    @property
    def is_integral(self) -> bool:
        return self.name in INTEGRAL_WIDTH

    @property
    def is_floating(self) -> bool:
        return self.name in FLOATING

    @property
    def is_numeric(self) -> bool:
        return self.is_integral or self.is_floating


@dataclass(frozen=True)
class ClassType(Type):
    KIND = "ClassType"
    name: str
    args: tuple["Type", ...] = ()


@dataclass(frozen=True)
class ArrayType(Type):
    KIND = "ArrayType"
    element: Type


#: The type assigned when the front end genuinely cannot determine one.  It is a
#: distinct node rather than ``None`` so that "we did not infer this" is visible
#: in the serialized IR and can be counted, reported and gated on.
@dataclass(frozen=True)
class UnknownType(Type):
    KIND = "UnknownType"
    reason: str = "not-inferred"


T_INT = PrimitiveType("int")
T_LONG = PrimitiveType("long")
T_DOUBLE = PrimitiveType("double")
T_FLOAT = PrimitiveType("float")
T_BOOLEAN = PrimitiveType("boolean")
T_CHAR = PrimitiveType("char")
T_BYTE = PrimitiveType("byte")
T_SHORT = PrimitiveType("short")
T_VOID = PrimitiveType("void")
T_STRING = ClassType("String")


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Expr:
    KIND = "Expr"
    origin: Origin
    type: Type


@dataclass(frozen=True)
class IntLiteral(Expr):
    KIND = "IntLiteral"
    value: int


@dataclass(frozen=True)
class FloatLiteral(Expr):
    KIND = "FloatLiteral"
    #: Held as the *exact source text* rather than a Python float, so that the
    #: canonical form has one representation and no rounding happens in the IR.
    text: str


@dataclass(frozen=True)
class BoolLiteral(Expr):
    KIND = "BoolLiteral"
    value: bool


@dataclass(frozen=True)
class CharLiteral(Expr):
    KIND = "CharLiteral"
    #: Code point, not the character, so surrogates survive serialization.
    value: int


@dataclass(frozen=True)
class StringLiteral(Expr):
    KIND = "StringLiteral"
    value: str


@dataclass(frozen=True)
class NullLiteral(Expr):
    KIND = "NullLiteral"


@dataclass(frozen=True)
class Name(Expr):
    KIND = "Name"
    ident: str


@dataclass(frozen=True)
class This(Expr):
    KIND = "This"


@dataclass(frozen=True)
class FieldAccess(Expr):
    KIND = "FieldAccess"
    target: Expr
    name: str


@dataclass(frozen=True)
class StaticFieldAccess(Expr):
    KIND = "StaticFieldAccess"
    owner: str
    name: str


@dataclass(frozen=True)
class ArrayAccess(Expr):
    KIND = "ArrayAccess"
    array: Expr
    index: Expr


@dataclass(frozen=True)
class ArrayLength(Expr):
    KIND = "ArrayLength"
    array: Expr


BINARY_OPS = (
    "+", "-", "*", "/", "%",
    "<", "<=", ">", ">=", "==", "!=",
    "&&", "||",
    "&", "|", "^", "<<", ">>", ">>>",
)

UNARY_OPS = ("+", "-", "!", "~")


@dataclass(frozen=True)
class Binary(Expr):
    KIND = "Binary"
    op: str
    left: Expr
    right: Expr

    def __post_init__(self) -> None:
        if self.op not in BINARY_OPS:
            raise UirError(f"unknown binary operator: {self.op!r}")


@dataclass(frozen=True)
class Unary(Expr):
    KIND = "Unary"
    op: str
    operand: Expr

    def __post_init__(self) -> None:
        if self.op not in UNARY_OPS:
            raise UirError(f"unknown unary operator: {self.op!r}")


@dataclass(frozen=True)
class StringConcat(Expr):
    KIND = "StringConcat"
    #: Distinct from ``Binary('+')`` because Java's ``+`` on a String operand is
    #: a different operation with its own conversion rules (null -> "null",
    #: char -> the character, double -> Java's Double.toString spelling).
    parts: tuple[Expr, ...]


@dataclass(frozen=True)
class Ternary(Expr):
    KIND = "Ternary"
    cond: Expr
    then: Expr
    other: Expr


@dataclass(frozen=True)
class Cast(Expr):
    KIND = "Cast"
    target: Type
    operand: Expr


@dataclass(frozen=True)
class InstanceOf(Expr):
    KIND = "InstanceOf"
    operand: Expr
    target: Type


@dataclass(frozen=True)
class Assign(Expr):
    KIND = "Assign"
    #: "=" or a compound operator such as "+=".  Compound assignment in Java
    #: carries an *implicit narrowing cast* back to the target type, which is a
    #: classic source of migration bugs; the emitter is required to honour it.
    op: str
    target: Expr
    value: Expr


@dataclass(frozen=True)
class IncDec(Expr):
    KIND = "IncDec"
    op: str  # "++" or "--"
    prefix: bool
    target: Expr

    def __post_init__(self) -> None:
        if self.op not in ("++", "--"):
            raise UirError(f"unknown inc/dec operator: {self.op!r}")


@dataclass(frozen=True)
class Call(Expr):
    KIND = "Call"
    #: ``None`` for an unqualified call on the enclosing instance/class.
    target: Expr | None
    name: str
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class StaticCall(Expr):
    KIND = "StaticCall"
    owner: str
    name: str
    args: tuple[Expr, ...]


#: Java's functional interfaces and their single abstract method.  A call to the
#: SAM on a value holding a lambda is a *call of that lambda*, not a method
#: lookup, and the emitter needs this table to tell the two apart.
FUNCTIONAL_INTERFACES: dict[str, str] = {
    "BiConsumer": "accept",
    "BiFunction": "apply",
    "BiPredicate": "test",
    "BinaryOperator": "apply",
    "BooleanSupplier": "getAsBoolean",
    "Callable": "call",
    "Comparator": "compare",
    "Consumer": "accept",
    "Function": "apply",
    "IntBinaryOperator": "applyAsInt",
    "IntPredicate": "test",
    "IntSupplier": "getAsInt",
    "IntUnaryOperator": "applyAsInt",
    "Predicate": "test",
    "Runnable": "run",
    "Supplier": "get",
    "ToIntFunction": "applyAsInt",
    "UnaryOperator": "apply",
}


@dataclass(frozen=True)
class Lambda(Expr):
    KIND = "Lambda"
    params: tuple["Param", ...]
    #: Exactly one of these is populated.
    body_expr: "Expr | None" = None
    body_block: "Block | None" = None

    def __post_init__(self) -> None:
        if (self.body_expr is None) == (self.body_block is None):
            raise UirError("a lambda has exactly one of an expression or a block body")


#: How a ``::`` reference names its target.  The distinction matters for
#: evaluation order: a *bound* reference evaluates its receiver once, when the
#: reference is created, not on each call.  ``unresolved`` means the owner is
#: declared outside this compilation unit, so the front end can record *what*
#: was written without claiming to know whether it is static or unbound; the
#: emitter decides whether it can be translated.
METHOD_REF_KINDS = ("static", "bound", "unbound", "constructor", "unresolved")


@dataclass(frozen=True)
class MethodRef(Expr):
    KIND = "MethodRef"
    ref_kind: str
    name: str
    owner: str | None = None
    target: "Expr | None" = None

    def __post_init__(self) -> None:
        if self.ref_kind not in METHOD_REF_KINDS:
            raise UirError(f"unknown method reference kind: {self.ref_kind!r}")


@dataclass(frozen=True)
class New(Expr):
    KIND = "New"
    type: Type
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class NewArray(Expr):
    KIND = "NewArray"
    element: Type
    #: Exactly one of ``dims`` (sized) or ``init`` (literal) is populated.
    dims: tuple[Expr, ...] = ()
    init: tuple[Expr, ...] | None = None


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stmt:
    KIND = "Stmt"
    origin: Origin


@dataclass(frozen=True)
class Block(Stmt):
    KIND = "Block"
    body: tuple[Stmt, ...]


@dataclass(frozen=True)
class LocalVar(Stmt):
    KIND = "LocalVar"
    name: str
    type: Type
    init: Expr | None


@dataclass(frozen=True)
class ExprStmt(Stmt):
    KIND = "ExprStmt"
    expr: Expr


@dataclass(frozen=True)
class If(Stmt):
    KIND = "If"
    cond: Expr
    then: Stmt
    other: Stmt | None


@dataclass(frozen=True)
class While(Stmt):
    KIND = "While"
    cond: Expr
    body: Stmt


@dataclass(frozen=True)
class DoWhile(Stmt):
    KIND = "DoWhile"
    body: Stmt
    cond: Expr


@dataclass(frozen=True)
class For(Stmt):
    KIND = "For"
    init: tuple[Stmt, ...]
    cond: Expr | None
    update: tuple[Expr, ...]
    body: Stmt


@dataclass(frozen=True)
class ForEach(Stmt):
    KIND = "ForEach"
    var_name: str
    var_type: Type
    iterable: Expr
    body: Stmt


@dataclass(frozen=True)
class Return(Stmt):
    KIND = "Return"
    value: Expr | None


@dataclass(frozen=True)
class Break(Stmt):
    KIND = "Break"


@dataclass(frozen=True)
class Continue(Stmt):
    KIND = "Continue"


@dataclass(frozen=True)
class Throw(Stmt):
    KIND = "Throw"
    value: Expr


@dataclass(frozen=True)
class CatchClause:
    KIND = "CatchClause"
    origin: Origin
    types: tuple[Type, ...]
    name: str
    body: Stmt


@dataclass(frozen=True)
class Try(Stmt):
    KIND = "Try"
    body: Stmt
    catches: tuple[CatchClause, ...]
    finally_: Stmt | None
    #: try-with-resources declarations, in source order.  They are closed in
    #: *reverse* order, before any catch or finally runs.
    resources: tuple["LocalVar", ...] = ()


@dataclass(frozen=True)
class SwitchCase:
    KIND = "SwitchCase"
    origin: Origin
    #: Empty tuple means ``default``.
    labels: tuple[Expr, ...]
    body: tuple[Stmt, ...]


@dataclass(frozen=True)
class SwitchExprCase:
    KIND = "SwitchExprCase"
    origin: Origin
    #: Empty tuple means ``default``.
    labels: tuple[Expr, ...]
    value: Expr


@dataclass(frozen=True)
class SwitchExpr(Expr):
    KIND = "SwitchExpr"
    #: A switch used as a value.  Distinct from the ``Switch`` statement
    #: because it must produce a result and, unlike the statement form, cannot
    #: fall through.
    subject: Expr
    cases: tuple[SwitchExprCase, ...]


@dataclass(frozen=True)
class ThrowExpr(Expr):
    KIND = "ThrowExpr"
    #: ``case X -> throw ...`` inside a switch *expression*.  Java allows a
    #: throwing rule there; Python has no raise expression, so this is a
    #: distinct node the emitter routes through a helper call.
    value: Expr


@dataclass(frozen=True)
class ClassLiteral(Expr):
    KIND = "ClassLiteral"
    #: ``Foo.class``.  Representable in the IR; whether it can be *translated*
    #: is a separate question the emitter answers.
    name: str


@dataclass(frozen=True)
class ConstructorCall(Stmt):
    KIND = "ConstructorCall"
    #: ``this(...)`` or ``super(...)`` as the first statement of a constructor.
    kind: str
    args: tuple[Expr, ...]

    def __post_init__(self) -> None:
        if self.kind not in ("this", "super"):
            raise UirError(f"unknown constructor call kind: {self.kind!r}")


@dataclass(frozen=True)
class Switch(Stmt):
    KIND = "Switch"
    subject: Expr
    cases: tuple[SwitchCase, ...]


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Param:
    KIND = "Param"
    origin: Origin
    name: str
    type: Type
    #: ``int... xs``.  The parameter's type is the array; the flag records that
    #: call sites pack their trailing arguments into it.
    is_varargs: bool = False


@dataclass(frozen=True)
class Method:
    KIND = "Method"
    origin: Origin
    name: str
    params: tuple[Param, ...]
    return_type: Type
    modifiers: tuple[str, ...]
    body: Block | None
    is_constructor: bool = False

    @property
    def is_static(self) -> bool:
        return "static" in self.modifiers


@dataclass(frozen=True)
class Field:
    KIND = "Field"
    origin: Origin
    name: str
    type: Type
    modifiers: tuple[str, ...]
    init: Expr | None

    @property
    def is_static(self) -> bool:
        return "static" in self.modifiers


@dataclass(frozen=True)
class TypeDecl:
    KIND = "TypeDecl"
    origin: Origin
    name: str
    kind: str  # "class" | "interface" | "enum" | "record"
    modifiers: tuple[str, ...]
    superclass: Type | None
    interfaces: tuple[Type, ...]
    fields: tuple[Field, ...]
    methods: tuple[Method, ...]
    #: Enum constant names in declaration order; empty for non-enums.
    enum_constants: tuple[str, ...] = ()
    #: Record components in declaration order; empty for non-records.  Kept
    #: separate from ``fields`` because a record's accessor method shares its
    #: component's name, and the emitter has to resolve that collision.
    record_components: tuple[Param, ...] = ()
    #: A record's compact constructor.  Its parameters *are* the components:
    #: the body may reassign them, and whatever they hold at the end is what
    #: gets stored.  Modelling it as an ordinary constructor would lose that.
    compact_constructor: "Method | None" = None
    #: Name of the lexically enclosing type, for a nested declaration.
    enclosing: str | None = None


@dataclass(frozen=True)
class Module:
    KIND = "Module"
    origin: Origin
    package: str | None
    imports: tuple[str, ...]
    types: tuple[TypeDecl, ...]
    source_language: str = "java"
    uir_version: str = UIR_VERSION


# ---------------------------------------------------------------------------
# Canonical serialization
# ---------------------------------------------------------------------------


def to_canonical(node: Any) -> Any:
    """Convert a UIR node into a canonical, JSON-safe structure.

    Rejects ``float`` and ``set``: neither has a single deterministic textual
    representation across platforms, and a content address computed over a
    non-deterministic encoding is worse than no content address at all.
    """

    if isinstance(node, bool):
        return node
    if isinstance(node, float):
        raise UirError(
            "float is not permitted in canonical UIR; use FloatLiteral.text"
        )
    if isinstance(node, (int, str)) or node is None:
        return node
    if isinstance(node, (set, frozenset)):
        raise UirError("set has no deterministic order; use a tuple")
    if isinstance(node, (list, tuple)):
        return [to_canonical(item) for item in node]
    if isinstance(node, dict):
        return {str(k): to_canonical(v) for k, v in sorted(node.items())}
    if is_dataclass(node):
        out: dict[str, Any] = {"k": getattr(type(node), "KIND", type(node).__name__)}
        for f in fields(node):
            out[f.name] = to_canonical(getattr(node, f.name))
        return out
    raise UirError(f"cannot canonicalize {type(node).__name__}")


def canonical_json(node: Any) -> str:
    """Serialize the canonical form.

    Key ordering is established once, in :func:`to_canonical`.  ``json.dumps``
    is deliberately *not* asked to sort again: a second, redundant enforcement
    point cannot fail, so it cannot be tested, and an untestable rule is
    indistinguishable from no rule at all.
    """

    return json.dumps(
        to_canonical(node),
        separators=(",", ":"),
        ensure_ascii=False,
    )


def digest(node: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(node).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------


def walk(node: Any) -> Iterable[Any]:
    """Yield ``node`` and every nested dataclass, depth first."""

    if is_dataclass(node):
        yield node
        for f in fields(node):
            yield from walk(getattr(node, f.name))
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from walk(item)


def origins(node: Any) -> list[Origin]:
    return [n for n in walk(node) if isinstance(n, Origin)]


def type_of(expr: Expr) -> Type:
    return expr.type


#: Java's boxed types and the primitives they unbox to.
BOXED = {
    "Boolean": "boolean",
    "Byte": "byte",
    "Character": "char",
    "Double": "double",
    "Float": "float",
    "Integer": "int",
    "Long": "long",
    "Short": "short",
}


def unbox(t: "Type") -> "Type":
    """Unbox ``Integer`` to ``int`` and so on, for arithmetic contexts.

    Only for arithmetic.  ``==`` on two boxed values is *reference* comparison
    in Java, so unboxing there would change the answer; the emitter refuses that
    case instead.
    """

    if isinstance(t, ClassType) and t.name in BOXED:
        return PrimitiveType(BOXED[t.name])
    return t


def is_reference(t: "Type") -> bool:
    """True when ``==`` on this type compares identity rather than value."""

    return not isinstance(t, PrimitiveType)


def sam_of(t: "Type") -> str | None:
    """The single abstract method name of ``t``, if it is a functional interface."""

    if isinstance(t, ClassType):
        return FUNCTIONAL_INTERFACES.get(t.name)
    return None


def unary_promote(t: "Type") -> "Type":
    """Java unary numeric promotion: anything narrower than int becomes int."""

    t = unbox(t)
    if isinstance(t, PrimitiveType) and t.name in ("byte", "short", "char", "int"):
        return T_INT
    return t


def binary_promote(a: "Type", b: "Type") -> "Type":
    """Java binary numeric promotion.

    Lives here rather than in the front end because the emitter needs the same
    answer when it desugars ``x += y`` into ``x = (T)(x + y)``: the intermediate
    ``x + y`` is promoted, and only the store narrows.  Two copies of this rule
    would drift, and the drift would show up as an int being computed in double
    precision or vice versa.
    """

    a, b = unbox(a), unbox(b)
    if not isinstance(a, PrimitiveType) or not isinstance(b, PrimitiveType):
        return UnknownType("non-primitive-operand")
    names = {a.name, b.name}
    if "double" in names:
        return T_DOUBLE
    if "float" in names:
        return T_FLOAT
    if "long" in names:
        return T_LONG
    return T_INT


def unknown_types(node: Any) -> list[UnknownType]:
    """Every place the front end admitted it could not infer a type.

    Gates read this: a module whose IR is full of ``UnknownType`` has not been
    understood, and claiming a verified translation of it would be dishonest.
    """

    return [n for n in walk(node) if isinstance(n, UnknownType)]
