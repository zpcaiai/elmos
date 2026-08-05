"""UIR -> Python emitter that preserves Java semantics.

The emitter never uses a bare Python arithmetic operator on a value whose Java
type is integral.  ``a + b`` becomes ``rt.jint(a + b)``, ``a / b`` becomes
``rt.idiv('int', a, b)``, and so on.  That looks noisier than a naive
translation, and that noise is the entire point: Python's ``+`` does not
overflow, its ``//`` floors, and its ``%`` takes the sign of the divisor.  A
translation that reads more naturally would be wrong on exactly the inputs a
migration is least likely to test.

Like the front end, the emitter fails closed.  Anything it cannot express with
Java's semantics intact raises :class:`EmitError` with a source location rather
than producing plausible-looking Python.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import uir
from ..uir import (
    ArrayAccess,
    ArrayLength,
    ArrayType,
    Assign,
    Binary,
    Block,
    BoolLiteral,
    Break,
    Call,
    Cast,
    CharLiteral,
    ClassLiteral,
    ClassType,
    ConstructorCall,
    Continue,
    DoWhile,
    Expr,
    ExprStmt,
    Field,
    FieldAccess,
    FloatLiteral,
    For,
    ForEach,
    If,
    IncDec,
    InstanceOf,
    IntLiteral,
    Lambda,
    LocalVar,
    MethodRef,
    Method,
    Module,
    Param,
    Name,
    New,
    NewArray,
    NullLiteral,
    Origin,
    PrimitiveType,
    Return,
    StaticCall,
    StaticFieldAccess,
    Stmt,
    StringConcat,
    StringLiteral,
    Switch,
    SwitchExpr,
    Ternary,
    This,
    Throw,
    ThrowExpr,
    Try,
    TypeDecl,
    Unary,
    UnknownType,
    While,
)

RUNTIME_ALIAS = "rt"

#: java.time types the runtime reproduces.
_TIME_OWNERS = frozenset({
    "Instant", "Duration", "LocalDate", "LocalTime", "LocalDateTime",
    "ZoneOffset", "Clock", "DateTimeFormatter", "ChronoUnit",
})

_TIME_STATIC_METHODS = {
    "Instant": frozenset({"ofEpochSecond", "ofEpochMilli", "parse", "now"}),
    "Duration": frozenset({
        "ofSeconds", "ofMillis", "ofNanos", "ofMinutes", "ofHours", "ofDays",
        "between",
    }),
    "LocalDate": frozenset({"of", "parse", "ofEpochDay"}),
    "LocalTime": frozenset({"of"}),
    "LocalDateTime": frozenset({"of", "ofEpochSecond"}),
    "ZoneOffset": frozenset({"ofHours", "ofHoursMinutes"}),
    "Clock": frozenset({"fixed", "systemUTC"}),
    "DateTimeFormatter": frozenset({"ofPattern"}),
}

_TIME_INSTANCE_METHODS = {
    "Instant": frozenset({
        "getEpochSecond", "getNano", "toEpochMilli", "plusSeconds",
        "minusSeconds", "plusMillis", "plusNanos", "plus", "minus", "isBefore",
        "isAfter", "compareTo", "toString",
    }),
    "Duration": frozenset({
        "getSeconds", "getNano", "toMillis", "toNanos", "toSeconds",
        "toMinutes", "toHours", "toDays", "isZero", "isNegative", "plus",
        "minus", "plusSeconds", "plusMillis", "multipliedBy", "negated", "abs",
        "compareTo", "toString",
    }),
    "LocalDate": frozenset({
        "getYear", "getMonthValue", "getDayOfMonth", "toEpochDay",
        "isLeapYear", "lengthOfMonth", "plusDays", "minusDays", "plusMonths",
        "minusMonths", "plusYears", "isBefore", "isAfter", "compareTo",
        "atStartOfDay", "toString",
    }),
    "LocalTime": frozenset({
        "getHour", "getMinute", "getSecond", "toSecondOfDay", "toString",
    }),
    "LocalDateTime": frozenset({
        "toLocalDate", "toLocalTime", "getYear", "getHour", "toEpochSecond",
        "toInstant", "plusDays", "isBefore", "isAfter", "toString",
    }),
    "ZoneOffset": frozenset({"getTotalSeconds", "toString"}),
    "Clock": frozenset({"instant", "millis"}),
    "DateTimeFormatter": frozenset({"format"}),
    "ChronoUnit": frozenset({"between", "toString"}),
}

_CHRONO_UNITS = frozenset({
    "NANOS", "MILLIS", "SECONDS", "MINUTES", "HOURS", "DAYS", "WEEKS",
    "MONTHS", "YEARS",
})

#: Java static fields the runtime exposes as factories.
_TIME_CONSTANTS = frozenset({
    ("Instant", "EPOCH"), ("Duration", "ZERO"), ("ZoneOffset", "UTC"),
})

INTEGRAL = ("byte", "short", "char", "int", "long")


class EmitError(Exception):
    def __init__(self, message: str, origin: Origin) -> None:
        super().__init__(f"{origin.file}:{origin.line}:{origin.column}: {message}")
        self.origin = origin
        self.reason = message


@dataclass
class SourceMapEntry:
    python_line: int
    java_file: str
    java_line: int
    java_column: int


def _module_stem(path: str) -> str:
    """The generated Python module name for a Java source file.

    Kept identical to what :mod:`j2p.program` records as ``TypeInfo.module`` so
    an emitted import names the module the other file actually becomes.
    """

    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-5] if name.endswith(".java") else name


#: Enum members every constant has, provided by the runtime's JEnum.  `values`
#: and `valueOf` are deliberately absent: they need the constant list, which the
#: generated class does not carry in an ordered form.
_ENUM_METHODS = frozenset({"name", "ordinal", "toString", "compareTo"})


#: A placeholder substituted for an expression that could not be emitted, used
#: only while surveying.  It is deliberately not valid Python: code produced in
#: survey mode must never be mistaken for a translation.
BLOCKED_PLACEHOLDER = "<<blocked>>"


_BACKTICKED = __import__("re").compile(r"`[^`]*`")
_PARENTHESISED = __import__("re").compile(r"\s*\([^()]*\)")
_WHITESPACE = __import__("re").compile(r"\s+")


def blocker_category(reason: str) -> str:
    """Normalise a refusal message into a comparable category.

    Messages embed the specific name or type that triggered them, which is what
    makes them useful to a human and useless to a histogram: ``T.class`` and
    ``Foo.class`` are the same missing capability.  Quoted names and
    parenthesised detail are therefore stripped before grouping, so the counts
    are per *capability* rather than per occurrence.
    """

    text = reason.split(";")[0]
    text = _BACKTICKED.sub("_", text)
    text = _PARENTHESISED.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:110]


@dataclass(frozen=True)
class Blocker:
    """One reason a file cannot be translated, with where it was found."""

    category: str
    reason: str
    file: str
    line: int
    column: int


class SurveyModeError(Exception):
    """Raised when survey-mode output is mistaken for a translation."""


class PythonEmitter:
    def __init__(
        self, module: Module, survey: bool = False, index=None
    ) -> None:
        self.module = module
        #: The whole-program symbol index, when the caller has one.  Without it
        #: the emitter can only translate calls into classes declared in this
        #: same file, which measurement showed is the single limitation blocking
        #: 94% of files.  With it, a call into another file resolves, is checked
        #: against that class's real signature, and the generated module gets an
        #: import for it.
        self.index = index
        #: simple class name -> generated Python module it must be imported from.
        self._program_imports: dict[str, str] = {}
        self._program_cache: dict[str, object] = {}
        #: In survey mode the emitter records refusals and keeps going, so a
        #: file's *whole* blocker set becomes visible instead of just whichever
        #: one happened to come first.  The resulting text is not a translation
        #: and `emit()` refuses to return it.
        self.survey = survey
        self.blockers: list[Blocker] = []
        #: Types whose emission was abandoned at the *declaration* level while
        #: surveying.  Nothing inside them was measured, so their blocker count
        #: is a floor, not a total -- see `survey_report`.
        self.truncated_types: list[str] = []
        self.lines: list[str] = []
        self.source_map: list[SourceMapEntry] = []
        self._static_methods: set[str] = set()
        self._instance_methods: set[str] = set()
        self._static_fields: set[str] = set()
        self._instance_fields: set[str] = set()
        self._record_components: set[str] = set()
        #: Definitions that must be written immediately before the statement
        #: currently being emitted.  A block-bodied lambda becomes a nested
        #: `def`, and Python has no expression form for that.
        self._hoisted: list[tuple[int, str, "Origin | None"]] = []
        self._temp_index = 0
        self._class_names: set[str] = {t.name for t in module.types}
        self._enum_names: set[str] = {
            t.name for t in module.types if t.kind == "enum"
        }
        #: The generated module this file becomes, so a resolved type that lives
        #: here is used without importing it from itself.
        self._module_name = _module_stem(module.origin.file)

    # -- public -----------------------------------------------------------

    def emit(self) -> str:
        text = self._emit_text()
        if self.survey:
            raise SurveyModeError(
                "survey mode substitutes placeholders for what it could not "
                "translate; its output is a measurement, not runnable code. "
                "Use survey_blockers() instead."
            )
        return text

    def _emit_text(self) -> str:
        # The body is emitted first because the header cannot be written until
        # it is known which other generated modules this one references, and
        # that is only known once every call site has been visited.
        for decl in self.module.types:
            if not self._guard(lambda d=decl: self._type_decl(d), decl.origin):
                self.truncated_types.append(decl.name)
        self._main_entry()
        body = self.lines
        self.lines = []
        self._header()
        offset = len(self.lines)
        self.lines = self.lines + body
        self.source_map = [
            SourceMapEntry(
                python_line=e.python_line + offset,
                java_file=e.java_file,
                java_line=e.java_line,
                java_column=e.java_column,
            )
            for e in self.source_map
        ]
        return "\n".join(self.lines) + "\n"

    # -- whole-program resolution ----------------------------------------

    def _program_type(self, name: str):
        """The indexed declaration for a type named in another file, if any.

        Types declared in *this* file are excluded: the local declaration is
        authoritative and needs no import.
        """

        if self.index is None or not name or name in self._class_names:
            return None
        if name in self._program_cache:
            return self._program_cache[name]
        info = self.index.resolve(name, self.module.package, self.module.imports)
        self._program_cache[name] = info
        return info

    def _program_ref(self, info) -> str:
        """How this module refers to ``info``'s class, recording the import.

        The import is written as ``import Other as _m_Other`` and the class is
        reached through it, rather than ``from Other import Other``.  Java has
        no import cycles to speak of -- two classes may freely call each other
        -- but ``from X import Y`` does: the second module to start importing
        finds the first only partly initialised and the class name is not bound
        yet.  A plain module import binds the (possibly partial) module object
        and the attribute is looked up at call time, by which point both modules
        are complete.  The ``_m_`` prefix keeps the module distinct from the
        class, which usually has the same name.
        """

        if info.module == self._module_name:
            return info.simple_name
        self._program_imports[info.simple_name] = info.module
        return f"_m_{info.module}.{info.simple_name}"

    def _program_method(self, info, name: str, origin: Origin):
        """A method of an indexed type, refusing what cannot be dispatched.

        Overloads are refused rather than guessed at: picking one needs argument
        types the front end does not always have, and picking the wrong one is a
        silent behaviour change.
        """

        overloads = info.methods.get(name)
        if not overloads:
            inherited = self._inherited_method(info, name)
            if inherited is not None:
                return inherited
            raise EmitError(
                f"{info.qualified_name}.{name} is not declared in the scanned "
                f"program",
                origin,
            )
        if len(overloads) > 1:
            raise EmitError(
                f"{info.qualified_name}.{name} has {len(overloads)} overloads; "
                f"selecting one needs argument types the front end does not "
                f"always have, so the call is refused rather than guessed",
                origin,
            )
        return overloads[0]

    def _inherited_method(self, info, name: str):
        seen = set()
        current = info
        while current is not None and current.superclass_text:
            if current.superclass_text in seen:
                break
            seen.add(current.superclass_text)
            parent = self._program_type(current.superclass_text)
            if parent is None:
                return None
            overloads = parent.methods.get(name)
            if overloads and len(overloads) == 1:
                return overloads[0]
            if overloads:
                return None
            current = parent
        return None

    def _record(self, exc: "EmitError") -> None:
        self.blockers.append(
            Blocker(
                category=blocker_category(exc.reason),
                reason=exc.reason,
                file=exc.origin.file,
                line=exc.origin.line,
                column=exc.origin.column,
            )
        )

    def _guard(self, run, origin: Origin) -> bool:
        """Run ``run``; in survey mode record a refusal instead of raising."""

        if not self.survey:
            run()
            return True
        try:
            run()
            return True
        except EmitError as exc:
            self._record(exc)
            return False

    def source_map_entries(self) -> list[SourceMapEntry]:
        return list(self.source_map)

    # -- infrastructure ---------------------------------------------------

    def _write(self, indent: int, text: str, origin: Origin | None = None) -> None:
        self.lines.append("    " * indent + text if text else "")
        if origin is not None:
            self.source_map.append(
                SourceMapEntry(
                    python_line=len(self.lines),
                    java_file=origin.file,
                    java_line=origin.line,
                    java_column=origin.column,
                )
            )

    def _fresh(self, stem: str) -> str:
        self._temp_index += 1
        return f"_{stem}_{self._temp_index}"

    def _line(self, indent: int, build, origin: Origin | None = None) -> None:
        """Emit one statement line, writing any hoisted definitions above it.

        ``build`` is called first so that expression emission can queue nested
        definitions; those are written at the same indent, immediately before
        the statement that uses them.
        """

        saved, self._hoisted = self._hoisted, []
        try:
            text = build()
            hoisted = self._hoisted
        finally:
            self._hoisted = saved
        for rel, line, hoist_origin in hoisted:
            self._write(indent + rel, line, hoist_origin)
        self._write(indent, text, origin)

    def _line_evaluated_once(
        self, indent: int, build, origin: Origin, position: str
    ) -> None:
        """Emit a line whose expression must NOT need a hoisted definition.

        A loop condition is re-evaluated on every iteration.  A hoisted
        statement placed above the loop would run once, so any expression that
        needs one is refused here rather than silently changing how many times
        it is evaluated.
        """

        saved, self._hoisted = self._hoisted, []
        try:
            text = build()
            hoisted = self._hoisted
        finally:
            self._hoisted = saved
        if hoisted:
            raise EmitError(
                f"this expression needs a statement emitted before it, but it "
                f"appears in {position}, which is evaluated more than once",
                origin,
            )
        self._write(indent, text, origin)

    def _sub_emit(self, fn) -> list[tuple[int, str, "Origin | None"]]:
        """Emit statements into a detached buffer, returning relative lines.

        Used for a lambda body, which becomes a nested `def` written above the
        statement that referenced it.  Source-map entries produced inside are
        re-based by the caller, so a lambda body stays traceable to its Java
        line.
        """

        saved_lines, saved_map, saved_hoist = self.lines, self.source_map, self._hoisted
        self.lines, self.source_map, self._hoisted = [], [], []
        try:
            fn()
            produced, produced_map = self.lines, self.source_map
        finally:
            self.lines, self.source_map, self._hoisted = (
                saved_lines,
                saved_map,
                saved_hoist,
            )
        origin_by_line = {e.python_line: e for e in produced_map}
        out: list[tuple[int, str, "Origin | None"]] = []
        for index, raw in enumerate(produced, start=1):
            stripped = raw.lstrip(" ")
            rel = (len(raw) - len(stripped)) // 4
            entry = origin_by_line.get(index)
            out.append(
                (
                    rel,
                    stripped,
                    Origin(entry.java_file, entry.java_line, entry.java_column)
                    if entry
                    else None,
                )
            )
        return out

    def _header(self) -> None:
        self._write(0, '"""Generated from Java by the UIR java->python route.')
        self._write(0, "")
        self._write(0, f"Source module: {self.module.package or '<default>'}")
        self._write(0, "Do not edit: regenerate from the Java source instead.")
        self._write(0, '"""')
        self._write(0, "")
        self._write(0, "import j2p_runtime as rt")
        for module in sorted(set(self._program_imports.values())):
            self._write(0, f"import {module} as _m_{module}")
        self._write(0, "")

    # -- declarations -----------------------------------------------------

    def _type_decl(self, decl: TypeDecl) -> None:
        if decl.kind == "interface":
            # A pure abstract interface carries no behaviour, so an empty class
            # reproduces it exactly.  One with default or static methods does
            # carry behaviour, and dispatching that correctly needs an
            # inheritance model this emitter does not have.
            with_bodies = [m for m in decl.methods if m.body is not None]
            if with_bodies or decl.fields:
                raise EmitError(
                    "interface with default/static methods or constants is not "
                    "supported; only pure abstract interfaces are",
                    with_bodies[0].origin if with_bodies else decl.origin,
                )
            self._write(0, f"class {decl.name}:", decl.origin)
            self._write(1, '"""Pure abstract interface; carries no behaviour."""')
            self._write(1, "pass")
            self._write(0, "")
            return

        self._static_methods = {m.name for m in decl.methods if m.is_static}
        self._instance_methods = {
            m.name for m in decl.methods if not m.is_static and not m.is_constructor
        }
        self._static_fields = {f.name for f in decl.fields if f.is_static}
        self._instance_fields = {f.name for f in decl.fields if not f.is_static}
        # A record component is reachable as both `x` (the field) and `x()` (the
        # accessor).  Python has one namespace per object, so the field is stored
        # under a leading underscore and the accessor keeps the Java name.
        self._record_components = {p.name for p in decl.record_components}

        if decl.kind != "record":
            # Java keeps fields and methods in separate namespaces, so
            # `int factor; int factor()` is ordinary code.  Python has one
            # namespace per object, and `self.factor = factor` in __init__ would
            # overwrite the method -- the call then fails with a TypeError far
            # from the declaration that caused it.  A record is exempt because
            # its components are stored under a leading underscore.
            clash = sorted(
                {f.name for f in decl.fields}
                & {m.name for m in decl.methods if not m.is_constructor}
            )
            if clash:
                raise EmitError(
                    f"{decl.name} declares both a field and a method named "
                    f"{clash[0]!r}; Java gives them separate namespaces and "
                    f"Python does not, so one would silently overwrite the other",
                    decl.origin,
                )

        self._write(0, f"class {decl.name}:", decl.origin)

        body_started = False

        for f in decl.fields:
            if f.is_static:
                value = self._expr(f.init) if f.init is not None else self._zero(f.type)
                self._write(1, f"{f.name} = {value}", f.origin)
                body_started = True

        if decl.kind == "enum":
            for index, constant in enumerate(decl.enum_constants):
                self._write(
                    1,
                    f"{constant} = {RUNTIME_ALIAS}.JEnum("
                    f"{decl.name!r}, {constant!r}, {index})",
                    decl.origin,
                )
                body_started = True

        if decl.kind == "record":
            self._emit_record(decl)
            return

        constructors = [m for m in decl.methods if m.is_constructor]
        self._write(0, "")
        if len(constructors) > 1:
            self._check_overloaded_init(decl, constructors)
            self._emit_overloaded_init(decl, constructors)
        else:
            self._emit_init(decl, constructors[0] if constructors else None)
        body_started = True

        for method in decl.methods:
            if method.is_constructor:
                continue
            self._write(0, "")
            if not self._guard(lambda m=method: self._emit_method(m), method.origin):
                self._write(1, "pass")
            body_started = True

        if not body_started:  # pragma: no cover - defensive
            self._write(1, "pass")
        self._write(0, "")

    def _emit_record(self, decl: TypeDecl) -> None:
        names = [p.name for p in decl.record_components]
        explicit = [m for m in decl.methods if m.is_constructor]
        if len(explicit) > 1:
            raise EmitError(
                "a record may declare only one canonical constructor",
                explicit[1].origin,
            )
        if explicit and decl.compact_constructor is not None:
            raise EmitError(
                "a record cannot have both a canonical and a compact constructor",
                explicit[0].origin,
            )

        if explicit:
            # The canonical constructor assigns every field itself, so nothing
            # is appended after its body.
            ctor = explicit[0]
            params = ", ".join(["self"] + [p.name for p in ctor.params])
            self._write(1, f"def __init__({params}):", ctor.origin)
            if ctor.body is None or not ctor.body.body:
                self._write(2, "pass")
            else:
                for stmt in ctor.body.body:
                    self._stmt(stmt, 2)
        else:
            params = ", ".join(["self"] + names)
            self._write(1, f"def __init__({params}):", decl.origin)
            compact = decl.compact_constructor
            if compact is not None and compact.body is not None:
                # The compact body runs first and may reassign the parameters;
                # the fields are written from whatever they hold afterwards.
                for stmt in compact.body.body:
                    self._stmt(stmt, 2)
            if names:
                for p in decl.record_components:
                    self._write(2, f"self._{p.name} = {p.name}", p.origin)
            elif compact is None or compact.body is None or not compact.body.body:
                self._write(2, "pass")

        for p in decl.record_components:
            self._write(0, "")
            self._write(1, f"def {p.name}(self):", p.origin)
            self._write(2, f"return self._{p.name}")

        declared = {m.name for m in decl.methods}

        if "toString" not in declared:
            self._write(0, "")
            self._write(1, "def toString(self):", decl.origin)
            pieces: list[str] = [repr(decl.name + "[")]
            for index, p in enumerate(decl.record_components):
                prefix = ("" if index == 0 else ", ") + p.name + "="
                pieces.append(repr(prefix))
                pieces.append(f"self._{p.name}")
            pieces.append(repr("]"))
            self._write(2, f"return {RUNTIME_ALIAS}.concat({', '.join(pieces)})")

        self._write(0, "")
        self._write(1, "def __eq__(self, other):", decl.origin)
        self._write(2, "if not isinstance(other, type(self)):")
        self._write(3, "return NotImplemented")
        if names:
            comparison = " and ".join(
                f"self._{n} == other._{n}" for n in names
            )
            self._write(2, f"return {comparison}")
        else:
            self._write(2, "return True")

        self._write(0, "")
        self._write(1, "def __hash__(self):", decl.origin)
        tup = ", ".join(f"self._{n}" for n in names)
        self._write(2, f"return hash(({tup}{',' if len(names) == 1 else ''}))")

        for method in decl.methods:
            if method.is_constructor:
                continue
            self._write(0, "")
            self._emit_method(method)
        self._write(0, "")

    def _emit_init(self, decl: TypeDecl, ctor: Method | None) -> None:
        params = ", ".join(["self"] + [p.name for p in ctor.params]) if ctor else "self"
        self._write(1, f"def __init__({params}):", (ctor or decl).origin)
        wrote = False
        for f in decl.fields:
            if f.is_static:
                continue
            value = self._expr(f.init) if f.init is not None else self._zero(f.type)
            self._write(2, f"self.{f.name} = {value}", f.origin)
            wrote = True
        if ctor is not None and ctor.body is not None:
            for stmt in ctor.body.body:
                self._stmt(stmt, 2)
                wrote = True
        if not wrote:
            self._write(2, "pass")

    def _emit_overloaded_init(self, decl: TypeDecl, ctors: list[Method]) -> None:
        """One ``__init__`` dispatching on argument count.

        Java picks a constructor by the static types of the arguments; Python
        has one ``__init__`` and no static types.  Where the overloads differ in
        *arity* the choice is fully determined by the call and can be reproduced
        exactly, so those are emitted.  Where two overloads share an arity the
        choice depends on types that are not present at run time, so
        :meth:`_check_overloaded_init` refuses the class before reaching here.

        Field initialisers run once, before the dispatch, because Java runs them
        before whichever constructor body was selected.
        """

        self._write(1, "def __init__(self, *_args):", decl.origin)
        for f in decl.fields:
            if f.is_static:
                continue
            value = self._expr(f.init) if f.init is not None else self._zero(f.type)
            self._write(2, f"self.{f.name} = {value}", f.origin)
        for ctor in sorted(ctors, key=lambda c: len(c.params)):
            self._write(2, f"if len(_args) == {len(ctor.params)}:", ctor.origin)
            if ctor.params:
                names = ", ".join(p.name for p in ctor.params)
                comma = "," if len(ctor.params) == 1 else ""
                self._write(3, f"({names}{comma}) = _args")
            body_written = False
            if ctor.body is not None:
                for stmt in ctor.body.body:
                    self._stmt(stmt, 3)
                    body_written = True
            self._write(3, "return" if body_written else "return")
        self._write(
            2,
            "raise rt.IllegalArgumentExceptionJ("
            "'no constructor takes ' + str(len(_args)) + ' arguments')",
            decl.origin,
        )

    @staticmethod
    def _check_overloaded_init(decl: TypeDecl, ctors: list[Method]) -> None:
        arities = [len(c.params) for c in ctors]
        duplicated = sorted({a for a in arities if arities.count(a) > 1})
        if duplicated:
            raise EmitError(
                f"{decl.name} declares {arities.count(duplicated[0])} constructors "
                f"taking {duplicated[0]} arguments; Java selects between them by "
                f"the static types of the arguments, which are not present at "
                f"run time",
                ctors[1].origin,
            )
        varargs = [c for c in ctors if c.params and c.params[-1].is_varargs]
        if varargs:
            raise EmitError(
                f"{decl.name} has an overloaded varargs constructor; its arity "
                f"is not fixed, so dispatching on argument count would pick the "
                f"wrong one",
                varargs[0].origin,
            )

    def _emit_method(self, method: Method) -> None:
        name = method.name
        if method.is_static:
            self._write(1, "@staticmethod", method.origin)
            params = ", ".join(p.name for p in method.params)
        else:
            params = ", ".join(["self"] + [p.name for p in method.params])
        self._write(1, f"def {name}({params}):", method.origin)
        if method.body is None:
            self._write(2, "raise rt.UnsupportedOperationExceptionJ('abstract method')")
            return
        if not method.body.body:
            self._write(2, "pass")
            return
        for stmt in method.body.body:
            self._stmt(stmt, 2)

    def _main_entry(self) -> None:
        main_owner = None
        for decl in self.module.types:
            for method in decl.methods:
                if method.name == "main" and method.is_static:
                    main_owner = decl.name
        if main_owner is None:
            return
        self._write(0, "")
        self._write(0, 'if __name__ == "__main__":')
        self._write(1, "import sys")
        self._write(1, "try:")
        self._write(2, f"{main_owner}.main(rt.array_of('String', sys.argv[1:]))")
        self._write(1, "except rt.JavaThrowable as _exc:")
        self._write(2, "sys.stdout.flush()")
        self._write(
            2,
            'sys.stderr.write(\'Exception in thread "main" \' + _exc.java_name + '
            "((': ' + _exc.message) if _exc.message else '') + '\\n')",
        )
        self._write(2, "sys.exit(1)")

    # -- statements -------------------------------------------------------

    def _stmt(self, stmt: Stmt, indent: int) -> None:
        if self.survey:
            # A statement is a recovery point: one untranslatable statement must
            # not hide the rest of the file.
            depth = len(self.lines)
            try:
                self._stmt_inner(stmt, indent)
            except EmitError as exc:
                self._record(exc)
                del self.lines[depth:]
                self._write(indent, "pass", stmt.origin)
            return
        self._stmt_inner(stmt, indent)

    def _stmt_inner(self, stmt: Stmt, indent: int) -> None:
        if isinstance(stmt, Block):
            if not stmt.body:
                self._write(indent, "pass", stmt.origin)
                return
            for inner in stmt.body:
                self._stmt(inner, indent)
            return

        if isinstance(stmt, LocalVar):
            self._line(
                indent,
                lambda: f"{stmt.name} = "
                + (
                    self._expr(stmt.init)
                    if stmt.init is not None
                    else self._zero(stmt.type)
                ),
                stmt.origin,
            )
            return

        if isinstance(stmt, ExprStmt):
            self._expr_stmt(stmt.expr, indent, stmt.origin)
            return

        if isinstance(stmt, If):
            self._line(indent, lambda: f"if {self._cond(stmt.cond)}:", stmt.origin)
            self._body(stmt.then, indent + 1)
            if stmt.other is not None:
                self._write(indent, "else:", stmt.origin)
                self._body(stmt.other, indent + 1)
            return

        if isinstance(stmt, While):
            self._line_evaluated_once(
                indent, lambda: f"while {self._cond(stmt.cond)}:", stmt.origin,
                "a while condition",
            )
            self._body(stmt.body, indent + 1)
            return

        if isinstance(stmt, DoWhile):
            self._write(indent, "while True:", stmt.origin)
            self._body(stmt.body, indent + 1)
            self._line_evaluated_once(
                indent + 1, lambda: f"if not ({self._cond(stmt.cond)}):", stmt.origin,
                "a do/while condition",
            )
            self._write(indent + 2, "break")
            return

        if isinstance(stmt, For):
            # A Java `for` is emitted as an explicit while loop rather than a
            # Python `for ... in range(...)`, because the update clause must run
            # on `continue` and range() would silently skip it.
            for init in stmt.init:
                self._stmt(init, indent)
            cond = self._cond(stmt.cond) if stmt.cond is not None else "True"
            if stmt.update:
                self._write(indent, "while True:", stmt.origin)
                self._line_evaluated_once(
                    indent + 1, lambda: f"if not ({cond}):", stmt.origin,
                    "a for condition",
                )
                self._write(indent + 2, "break")
                self._write(indent + 1, "try:")
                self._body(stmt.body, indent + 2)
                self._write(indent + 1, "finally:")
                for update in stmt.update:
                    self._expr_stmt(update, indent + 2, stmt.origin)
            else:
                self._line_evaluated_once(
                    indent, lambda: f"while {cond}:", stmt.origin, "a for condition"
                )
                self._body(stmt.body, indent + 1)
            return

        if isinstance(stmt, ForEach):
            self._line(
                indent,
                lambda: f"for {stmt.var_name} in {self._expr(stmt.iterable)}:",
                stmt.origin,
            )
            self._body(stmt.body, indent + 1)
            return

        if isinstance(stmt, Return):
            if stmt.value is None:
                self._write(indent, "return", stmt.origin)
            else:
                self._line(
                    indent, lambda: f"return {self._expr(stmt.value)}", stmt.origin
                )
            return

        if isinstance(stmt, Break):
            self._write(indent, "break", stmt.origin)
            return

        if isinstance(stmt, Continue):
            self._write(indent, "continue", stmt.origin)
            return

        if isinstance(stmt, Throw):
            self._line(indent, lambda: f"raise {self._expr(stmt.value)}", stmt.origin)
            return

        if isinstance(stmt, Try):
            self._emit_try(stmt, indent)
            return

        if isinstance(stmt, Switch):
            self._emit_switch(stmt, indent)
            return

        if isinstance(stmt, ConstructorCall):
            if stmt.kind == "super" and not stmt.args:
                # An implicit Object superclass constructor does nothing.
                self._write(indent, "pass", stmt.origin)
                return
            raise EmitError(
                f"`{stmt.kind}(...)` constructor delegation is not supported; "
                f"it requires constructor overloading or a modelled superclass",
                stmt.origin,
            )

        raise EmitError(f"cannot emit statement {type(stmt).__name__}", stmt.origin)

    def _body(self, stmt: Stmt, indent: int) -> None:
        before = len(self.lines)
        self._stmt(stmt, indent)
        if len(self.lines) == before:
            self._write(indent, "pass")

    def _emit_try(self, stmt: Try, indent: int) -> None:
        if not stmt.catches and stmt.finally_ is None and not stmt.resources:
            raise EmitError("try with neither catch nor finally", stmt.origin)

        if stmt.resources:
            if not stmt.catches and stmt.finally_ is None:
                self._emit_resources(stmt, 0, indent)
                return
            # `try (r) {...} catch/finally` is `try { try (r) {...} } catch/finally`:
            # resources close *before* the handler runs.
            self._write(indent, "try:", stmt.origin)
            self._emit_resources(stmt, 0, indent + 1)
            self._emit_handlers(stmt, indent)
            return

        self._write(indent, "try:", stmt.origin)
        self._body(stmt.body, indent + 1)
        self._emit_handlers(stmt, indent)

    def _emit_resources(self, stmt: Try, index: int, indent: int) -> None:
        """Emit one resource level, recursing so the last opened closes first.

        Java closes resources in reverse declaration order, before any catch or
        finally runs, and a failure in ``close()`` while another exception is in
        flight is *suppressed* rather than propagated.  Python's plain
        ``finally`` does the opposite: the close failure would replace the real
        exception and the original would be lost.
        """

        if index >= len(stmt.resources):
            self._body(stmt.body, indent)
            return

        resource = stmt.resources[index]
        self._require_closeable(resource)
        self._line(
            indent,
            lambda: f"{resource.name} = "
            + (self._expr(resource.init) if resource.init is not None else "None"),
            resource.origin,
        )
        primary = self._fresh("primary")
        caught = self._fresh("in_flight")
        self._write(indent, f"{primary} = None", resource.origin)
        self._write(indent, "try:")
        self._emit_resources(stmt, index + 1, indent + 1)
        self._write(indent, f"except {RUNTIME_ALIAS}.JavaThrowable as {caught}:")
        self._write(indent + 1, f"{primary} = {caught}")
        self._write(indent + 1, "raise")
        self._write(indent, "finally:")
        self._write(indent + 1, "try:")
        self._write(indent + 2, f"{resource.name}.close()")
        self._write(indent + 1, f"except {RUNTIME_ALIAS}.JavaThrowable:")
        self._write(indent + 2, f"if {primary} is None:")
        self._write(indent + 3, "raise")

    def _require_closeable(self, resource) -> None:
        declared = resource.type
        if not isinstance(declared, ClassType):
            raise EmitError(
                "a try-with-resources resource must have a class type",
                resource.origin,
            )
        decl = next(
            (d for d in self.module.types if d.name == declared.name), None
        )
        if decl is None or not any(m.name == "close" for m in decl.methods):
            raise EmitError(
                f"`{declared.name}` is not declared in this compilation unit "
                f"with a close() method, so its closing behaviour is unknown",
                resource.origin,
            )

    def _emit_handlers(self, stmt: Try, indent: int) -> None:
        for catch in stmt.catches:
            names = []
            for ty in catch.types:
                if not isinstance(ty, ClassType):
                    raise EmitError("catch of a non-class type", catch.origin)
                names.append(self._throwable(ty.name, catch.origin))
            joined = names[0] if len(names) == 1 else "(" + ", ".join(names) + ")"
            self._write(indent, f"except {joined} as {catch.name}:", catch.origin)
            self._body(catch.body, indent + 1)
        if stmt.finally_ is not None:
            self._write(indent, "finally:", stmt.origin)
            self._body(stmt.finally_, indent + 1)

    def _throwable(self, simple_name: str, origin: Origin) -> str:
        cls = self._throwable_class(simple_name)
        if cls is None:
            raise EmitError(
                f"catch of unsupported exception type {simple_name}; the "
                f"runtime has no equivalent, so the handler would not fire on "
                f"the same conditions Java fires it on",
                origin,
            )
        return f"{RUNTIME_ALIAS}.{cls}"

    def _emit_switch(self, stmt: Switch, indent: int) -> None:
        # Java switch falls through; Python if/elif does not.  Rather than
        # emitting a structure that is wrong for fall-through, reject any switch
        # whose cases do not all terminate.
        for case in stmt.cases:
            self._require_terminated_case(case, stmt.origin)

        tmp = "_switch_subject"
        self._line(indent, lambda: f"{tmp} = {self._expr(stmt.subject)}", stmt.origin)
        first = True
        default_case = None
        for case in stmt.cases:
            if not case.labels:
                default_case = case
                continue
            keyword = "if" if first else "elif"
            self._line(
                indent,
                lambda case=case, keyword=keyword: f"{keyword} "
                + " or ".join(
                    f"{tmp} == {self._expr(label)}" for label in case.labels
                )
                + ":",
                case.origin,
            )
            self._emit_case_body(case, indent + 1)
            first = False
        if default_case is not None:
            if first:
                self._emit_case_body(default_case, indent)
            else:
                self._write(indent, "else:", default_case.origin)
                self._emit_case_body(default_case, indent + 1)

    def _emit_case_body(self, case, indent: int) -> None:
        body = list(case.body)
        # A trailing `break` means "leave the switch".  Emitting a Python
        # `break` here would leave the *enclosing loop* instead.
        if body and isinstance(body[-1], Break):
            body = body[:-1]
        if not body:
            self._write(indent, "pass", case.origin)
            return
        for inner in body:
            self._stmt(inner, indent)

    def _require_terminated_case(self, case, origin: Origin) -> None:
        if not case.body:
            raise EmitError(
                "switch case with an empty body falls through; not supported",
                case.origin,
            )
        last = case.body[-1]
        if not isinstance(last, (Break, Return, Throw)):
            raise EmitError(
                "switch case does not end in break/return/throw, so it falls "
                "through; fall-through is not supported",
                case.origin,
            )
        for stmt in case.body[:-1]:
            if self._contains_free_break(stmt):
                raise EmitError(
                    "break inside a switch case body cannot be distinguished "
                    "from a loop break; not supported",
                    case.origin,
                )

    def _contains_free_break(self, stmt: Stmt) -> bool:
        if isinstance(stmt, Break):
            return True
        if isinstance(stmt, (While, DoWhile, For, ForEach, Switch)):
            return False
        if isinstance(stmt, Block):
            return any(self._contains_free_break(s) for s in stmt.body)
        if isinstance(stmt, If):
            return self._contains_free_break(stmt.then) or (
                stmt.other is not None and self._contains_free_break(stmt.other)
            )
        if isinstance(stmt, Try):
            return (
                self._contains_free_break(stmt.body)
                or any(self._contains_free_break(c.body) for c in stmt.catches)
                or (stmt.finally_ is not None and self._contains_free_break(stmt.finally_))
            )
        return False

    def _expr_stmt(self, expr: Expr, indent: int, origin: Origin) -> None:
        """Statement-position expressions.

        Assignment and ``++`` are statements in Python, not expressions, so they
        are only legal here.  Using them in expression position is rejected by
        :meth:`_expr` instead of being silently reordered.
        """

        if isinstance(expr, Assign):
            saved, self._hoisted = self._hoisted, []
            target = self._lvalue_read(expr.target)
            if expr.op == "=":
                value = self._expr(expr.value)
            else:
                op = expr.op[:-1]
                self._check_compound_target(expr.target, expr.origin)
                if op == "+" and self._is_string(expr.target.type):
                    combined = StringConcat(
                        origin=expr.origin,
                        type=expr.target.type,
                        parts=(expr.target, expr.value),
                    )
                else:
                    # The intermediate `x + y` is promoted; only the store
                    # narrows.  Typing it as the target type would compute an
                    # int addition in double precision, or worse.
                    combined = Binary(
                        origin=expr.origin,
                        type=uir.binary_promote(expr.target.type, expr.value.type),
                        op=op,
                        left=expr.target,
                        right=expr.value,
                    )
                # Java's compound assignment applies an implicit cast back to
                # the target type: `int i; i += 3.5;` keeps i an int.
                value = self._expr(
                    Cast(
                        origin=expr.origin,
                        type=expr.target.type,
                        target=expr.target.type,
                        operand=combined,
                    )
                )
            hoisted, self._hoisted = self._hoisted, saved
            for rel, line, hoist_origin in hoisted:
                self._write(indent + rel, line, hoist_origin)
            self._emit_store(expr.target, value, indent, origin)
            return

        if isinstance(expr, IncDec):
            self._check_compound_target(expr.target, expr.origin)
            one = IntLiteral(origin=expr.origin, type=uir.T_INT, value=1)
            combined = Binary(
                origin=expr.origin,
                type=uir.binary_promote(expr.target.type, uir.T_INT),
                op="+" if expr.op == "++" else "-",
                left=expr.target,
                right=one,
            )
            value = self._expr(
                Cast(
                    origin=expr.origin,
                    type=expr.target.type,
                    target=expr.target.type,
                    operand=combined,
                )
            )
            self._emit_store(expr.target, value, indent, origin)
            return

        self._line(indent, lambda: self._expr(expr), origin)

    def _check_compound_target(self, target: Expr, origin: Origin) -> None:
        """A read-modify-write target must be safe to evaluate twice.

        Java evaluates the array reference and index of ``a[i()] += 1`` once.
        The emitted Python evaluates the target expression twice, so anything
        whose evaluation could observe or cause a side effect is refused rather
        than silently double-evaluated.
        """

        if isinstance(target, ArrayAccess):
            if not isinstance(target.index, (Name, IntLiteral)):
                raise EmitError(
                    "compound assignment to an array element with a computed "
                    "index would evaluate the index twice",
                    origin,
                )
            if not isinstance(target.array, (Name, FieldAccess, StaticFieldAccess)):
                raise EmitError(
                    "compound assignment to an array element of a computed "
                    "array would evaluate the array expression twice",
                    origin,
                )
            return
        if isinstance(target, (Name, StaticFieldAccess)):
            return
        if isinstance(target, FieldAccess) and isinstance(
            target.target, (This, Name, StaticFieldAccess)
        ):
            return
        raise EmitError(
            "compound assignment to this target would evaluate it twice", origin
        )

    def _emit_store(self, target: Expr, value: str, indent: int, origin: Origin) -> None:
        if isinstance(target, Name):
            self._write(indent, f"{self._name_ref(target)} = {value}", origin)
            return
        if isinstance(target, FieldAccess):
            self._write(
                indent,
                f"{self._expr(target.target)}.{self._field_attr(target)} = {value}",
                origin,
            )
            return
        if isinstance(target, StaticFieldAccess):
            self._write(indent, f"{target.owner}.{target.name} = {value}", origin)
            return
        if isinstance(target, ArrayAccess):
            array = self._expr(target.array)
            index = self._num(target.index)
            self._write(indent, f"{array}.set({index}, {value})", origin)
            return
        raise EmitError("unsupported assignment target", origin)

    def _lvalue_read(self, target: Expr) -> str:
        return self._expr(target)

    # -- expressions ------------------------------------------------------

    def _expr(self, expr: Expr) -> str:
        if self.survey:
            # Expressions are the finer recovery point: `foo(a.bad(), b.alsoBad())`
            # has two blockers, and stopping at the first would report one.
            try:
                return self._expr_inner(expr)
            except EmitError as exc:
                self._record(exc)
                return BLOCKED_PLACEHOLDER
        return self._expr_inner(expr)

    def _expr_inner(self, expr: Expr) -> str:
        if isinstance(expr, IntLiteral):
            return repr(expr.value)
        if isinstance(expr, FloatLiteral):
            return f"float({expr.text!r})"
        if isinstance(expr, BoolLiteral):
            return "True" if expr.value else "False"
        if isinstance(expr, CharLiteral):
            return f"{RUNTIME_ALIAS}.JChar({expr.value})"
        if isinstance(expr, StringLiteral):
            return repr(expr.value)
        if isinstance(expr, NullLiteral):
            return "None"
        if isinstance(expr, This):
            return "self"
        if isinstance(expr, Name):
            return self._name_ref(expr)
        if isinstance(expr, FieldAccess):
            return f"{self._expr(expr.target)}.{self._field_attr(expr)}"
        if isinstance(expr, StaticFieldAccess):
            return self._static_field(expr)
        if isinstance(expr, ArrayLength):
            return f"{self._expr(expr.array)}.length"
        if isinstance(expr, ArrayAccess):
            return f"{self._expr(expr.array)}.get({self._num(expr.index)})"
        if isinstance(expr, Binary):
            return self._binary(expr)
        if isinstance(expr, Unary):
            return self._unary(expr)
        if isinstance(expr, StringConcat):
            parts = ", ".join(self._expr(p) for p in expr.parts)
            return f"{RUNTIME_ALIAS}.concat({parts})"
        if isinstance(expr, Ternary):
            return (
                f"({self._expr(expr.then)} if {self._cond(expr.cond)} "
                f"else {self._expr(expr.other)})"
            )
        if isinstance(expr, Cast):
            return self._cast(expr)
        if isinstance(expr, InstanceOf):
            return self._instanceof(expr)
        if isinstance(expr, New):
            return self._new(expr)
        if isinstance(expr, NewArray):
            return self._new_array(expr)
        if isinstance(expr, ThrowExpr):
            return f"{RUNTIME_ALIAS}.throw({self._expr(expr.value)})"
        if isinstance(expr, SwitchExpr):
            return self._switch_expr(expr)
        if isinstance(expr, ClassLiteral):
            raise EmitError(
                f"`{expr.name}.class` has no translation: it denotes a runtime "
                f"class object, and reflection over it cannot be reproduced",
                expr.origin,
            )
        if isinstance(expr, Lambda):
            return self._lambda(expr)
        if isinstance(expr, MethodRef):
            return self._method_ref(expr)
        if isinstance(expr, Call):
            return self._call(expr)
        if isinstance(expr, StaticCall):
            return self._static_call(expr)
        if isinstance(expr, Assign):
            raise EmitError(
                "assignment used as a value; Python has no assignment "
                "expression with Java's semantics here",
                expr.origin,
            )
        if isinstance(expr, IncDec):
            raise EmitError(
                "++/-- used as a value; the surrounding expression's evaluation "
                "order cannot be preserved",
                expr.origin,
            )
        raise EmitError(f"cannot emit expression {type(expr).__name__}", expr.origin)

    def _field_attr(self, expr: FieldAccess) -> str:
        if isinstance(expr.target, This) and expr.name in self._record_components:
            return f"_{expr.name}"
        return expr.name

    # -- lambdas -----------------------------------------------------------

    @staticmethod
    def _bound_names(node) -> set[str]:
        """Names a subtree introduces: locals, loop variables, catch bindings."""

        bound: set[str] = set()
        for n in uir.walk(node):
            if isinstance(n, LocalVar):
                bound.add(n.name)
            elif isinstance(n, ForEach):
                bound.add(n.var_name)
            elif isinstance(n, uir.CatchClause):
                bound.add(n.name)
            elif isinstance(n, Param):
                bound.add(n.name)
        return bound

    def _captures(self, body, params: tuple[Param, ...]) -> list[str]:
        """Locals the lambda body reads from its enclosing scope.

        Java only permits capture of *effectively final* locals, so their value
        cannot change after the lambda is created.  Python closures capture by
        reference and read the variable's value at call time.  For an ordinary
        capture the two agree; for a variable that is rebound each iteration of
        an enclosing loop they do not, and every lambda created in that loop
        would see the final value.  Capturing by value removes the difference.
        """

        used = {n.ident for n in uir.walk(body) if isinstance(n, Name)}
        return sorted(used - self._bound_names(body) - {p.name for p in params})

    def _lambda(self, expr: Lambda) -> str:
        params = [p.name for p in expr.params]
        captures = self._captures(
            expr.body_expr if expr.body_expr is not None else expr.body_block,
            expr.params,
        )
        # `n=n` binds the *current* value as a default argument: evaluated once,
        # when the lambda is created, exactly as Java captures it.
        signature = ", ".join(params + [f"{name}={name}" for name in captures])

        if expr.body_expr is not None:
            saved, self._hoisted = self._hoisted, []
            try:
                body = self._expr(expr.body_expr)
                nested = self._hoisted
            finally:
                self._hoisted = saved
            if nested:
                raise EmitError(
                    "a lambda whose body needs a nested definition cannot be "
                    "emitted as a Python lambda expression; the definition "
                    "would be hoisted out of the scope it captures",
                    expr.origin,
                )
            return f"(lambda {signature}: {body})" if signature else f"(lambda: {body})"

        name = self._fresh("lambda")
        block = expr.body_block
        lines = self._sub_emit(lambda: self._body(block, 1))
        self._hoisted.append((0, f"def {name}({signature}):", expr.origin))
        self._hoisted.extend(lines)
        return name

    def _switch_expr(self, expr: SwitchExpr) -> str:
        """A switch used as a value becomes a chained conditional.

        The subject is hoisted into a temporary first: writing it inline would
        re-evaluate it once per comparison, and Java evaluates it exactly once.
        """

        tmp = self._fresh("switch_value")
        self._hoisted.append((0, f"{tmp} = {self._expr(expr.subject)}", expr.origin))

        default = next((c for c in expr.cases if not c.labels), None)
        if default is None:  # pragma: no cover - the front end already refuses
            raise EmitError("switch expression without a default", expr.origin)

        text = self._expr(default.value)
        for case in reversed([c for c in expr.cases if c.labels]):
            tests = " or ".join(
                f"{tmp} == {self._expr(label)}" for label in case.labels
            )
            text = f"({self._expr(case.value)} if {tests} else {text})"
        return text

    #: Unbound references whose receiver method the runtime actually implements.
    _RUNTIME_UNBOUND = {
        "String": {
            "length", "charAt", "substring", "indexOf", "isEmpty",
            "toUpperCase", "toLowerCase", "trim",
        },
    }

    def _method_ref(self, expr: MethodRef) -> str:
        if expr.ref_kind == "unresolved":
            supported = self._RUNTIME_UNBOUND.get(expr.owner or "", set())
            if expr.name in supported:
                return (
                    f"(lambda _r, *_a: {RUNTIME_ALIAS}.JString.{expr.name}(_r, *_a))"
                )
            raise EmitError(
                f"`{expr.owner}::{expr.name}` refers to a type declared outside "
                f"this compilation unit; the runtime has no equivalent, so the "
                f"reference cannot be given the same behaviour",
                expr.origin,
            )
        if expr.ref_kind == "constructor":
            return f"(lambda *_a: {expr.owner}(*_a))"
        if expr.ref_kind == "static":
            return f"{expr.owner}.{expr.name}"
        if expr.ref_kind == "unbound":
            return f"(lambda _r, *_a: _r.{expr.name}(*_a))"
        # A bound reference evaluates its receiver once, at creation.  The
        # default argument is what makes that true here.
        target = self._expr(expr.target) if expr.target is not None else "self"
        return f"(lambda *_a, _t={target}: _t.{expr.name}(*_a))"

    def _name_ref(self, expr: Name) -> str:
        # Field references were already resolved by the front end into
        # FieldAccess/StaticFieldAccess, so anything still called a Name here is
        # a local or a parameter.
        return expr.ident

    def _owner_of_static(self, field_name: str) -> str:
        for decl in self.module.types:
            if any(f.name == field_name and f.is_static for f in decl.fields):
                return decl.name
        return self.module.types[0].name  # pragma: no cover - defensive

    def _static_field(self, expr: StaticFieldAccess) -> str:
        if expr.owner == "ChronoUnit":
            if expr.name not in _CHRONO_UNITS:
                raise EmitError(
                    f"ChronoUnit.{expr.name} is not supported", expr.origin
                )
            return f"{RUNTIME_ALIAS}.ChronoUnit.{expr.name}"
        if (expr.owner, expr.name) in _TIME_CONSTANTS:
            # These are static *fields* in Java and factory calls here, because
            # a mutable module-level instance would be shared across uses.
            return f"{RUNTIME_ALIAS}.{expr.owner}.{expr.name}()"
        if expr.owner in ("Integer", "Long", "Math") and expr.owner not in self._class_names:
            return f"{RUNTIME_ALIAS}.{expr.owner}.{expr.name}"
        if expr.owner in self._class_names:
            return f"{expr.owner}.{expr.name}"
        info = self._program_type(expr.owner)
        if info is not None:
            if expr.name in info.enum_constants:
                return f"{self._program_ref(info)}.{expr.name}"
            declared = info.fields.get(expr.name)
            if declared is None or not declared.is_static:
                raise EmitError(
                    f"{info.qualified_name}.{expr.name} is not a static field "
                    f"of the scanned declaration",
                    expr.origin,
                )
            return f"{self._program_ref(info)}.{expr.name}"
        raise EmitError(
            f"unsupported static field {expr.owner}.{expr.name}", expr.origin
        )

    def _cond(self, expr: Expr) -> str:
        return self._expr(expr)

    def _num(self, expr: Expr) -> str:
        """Emit an expression as a plain number, unwrapping ``char``."""

        text = self._expr(expr)
        if isinstance(expr.type, PrimitiveType) and expr.type.name == "char":
            return f"{RUNTIME_ALIAS}.num({text})"
        if isinstance(expr.type, UnknownType):
            return f"{RUNTIME_ALIAS}.num({text})"
        return text

    @staticmethod
    def _kind(t: uir.Type) -> str | None:
        if isinstance(t, PrimitiveType) and t.name in INTEGRAL:
            return t.name
        return None

    def _binary(self, expr: Binary) -> str:
        op = expr.op
        left = self._num(expr.left)
        right = self._num(expr.right)

        if op in ("&&", "||"):
            py = "and" if op == "&&" else "or"
            return f"({left} {py} {right})"

        if op in ("==", "!="):
            return self._equality(expr, left, right)

        if op in ("<", "<=", ">", ">="):
            return f"({left} {op} {right})"

        if op in ("&", "|", "^") and self._is_bool(expr.type):
            py = {"&": "and", "|": "or", "^": "!="}[op]
            return f"(bool({left}) {py} bool({right}))"

        kind = self._kind(expr.type)

        if op in ("<<", ">>", ">>>"):
            if kind is None:
                raise EmitError("shift on a non-integral type", expr.origin)
            fn = {"<<": "shl", ">>": "shr", ">>>": "ushr"}[op]
            return f"{RUNTIME_ALIAS}.{fn}({kind!r}, {left}, {right})"

        if kind is not None:
            if op == "/":
                return f"{RUNTIME_ALIAS}.idiv({kind!r}, {left}, {right})"
            if op == "%":
                return f"{RUNTIME_ALIAS}.irem({kind!r}, {left}, {right})"
            if op in ("+", "-", "*", "&", "|", "^"):
                return f"{RUNTIME_ALIAS}.{self._wrapper(kind)}({left} {op} {right})"
            raise EmitError(f"unsupported integral operator {op}", expr.origin)

        if isinstance(expr.type, PrimitiveType) and expr.type.name == "double":
            if op == "/":
                return f"{RUNTIME_ALIAS}.ddiv({left}, {right})"
            if op == "%":
                return f"{RUNTIME_ALIAS}.drem({left}, {right})"
            return f"({left} {op} {right})"

        raise EmitError(
            f"operator {op} on unresolved type {expr.type}", expr.origin
        )

    def _equality(self, expr: Binary, left: str, right: str) -> str:
        """``==`` in Java is value comparison only for primitives.

        On any reference type it compares identity, which is why
        ``Integer.valueOf(1000) == Integer.valueOf(1000)`` is false and why
        comparing Strings with ``==`` is a bug rather than a style choice.
        Emitting Python's ``==`` for those would turn a false into a true.
        """

        if isinstance(expr.left, NullLiteral) or isinstance(expr.right, NullLiteral):
            return f"({left} is {'not None' if expr.op == '!=' else 'None'})" if isinstance(
                expr.right, NullLiteral
            ) else f"({right} is {'not None' if expr.op == '!=' else 'None'})"

        # Java unboxes only when at least one operand is already primitive.
        # Testing the *unboxed* types here would treat `Integer == Integer` as a
        # value comparison, which is exactly the bug this guard exists to catch.
        if self._is_enum_type(expr.left.type) and self._is_enum_type(expr.right.type):
            # Enum constants are singletons on both sides, so Java's identity
            # comparison -- which is how enums are meant to be compared -- is
            # reproduced exactly by `is`.
            return f"({left} {'is not' if expr.op == '!=' else 'is'} {right})"

        left_ref = uir.is_reference(expr.left.type)
        right_ref = uir.is_reference(expr.right.type)
        if left_ref and right_ref:
            raise EmitError(
                f"`{expr.op}` between two reference types "
                f"({expr.left.type} and {expr.right.type}) compares identity in "
                f"Java, not value; use .equals() or compare a primitive",
                expr.origin,
            )
        return f"({left} {expr.op} {right})"

    def _is_enum_type(self, t: uir.Type) -> bool:
        if not isinstance(t, ClassType):
            return False
        if t.name in self._enum_names:
            return True
        info = self._program_type(t.name)
        return info is not None and info.kind == "enum"

    @staticmethod
    def _wrapper(kind: str) -> str:
        return {"int": "jint", "long": "jlong", "byte": "jbyte", "short": "jshort", "char": "jchar"}[kind]

    @staticmethod
    def _is_bool(t: uir.Type) -> bool:
        return isinstance(t, PrimitiveType) and t.name == "boolean"

    @staticmethod
    def _is_string(t: uir.Type) -> bool:
        return isinstance(t, ClassType) and t.name == "String"

    def _unary(self, expr: Unary) -> str:
        operand = self._num(expr.operand)
        if expr.op == "!":
            return f"(not {operand})"
        if expr.op == "+":
            return f"(+{operand})"
        kind = self._kind(expr.type)
        if expr.op == "-":
            if kind is not None:
                return f"{RUNTIME_ALIAS}.{self._wrapper(kind)}(-{operand})"
            return f"(-{operand})"
        if expr.op == "~":
            if kind is None:
                raise EmitError("~ on a non-integral type", expr.origin)
            return f"{RUNTIME_ALIAS}.{self._wrapper(kind)}(~{operand})"
        raise EmitError(f"unsupported unary operator {expr.op}", expr.origin)

    def _cast(self, expr: Cast) -> str:
        target = expr.target
        operand = expr.operand
        if not isinstance(target, PrimitiveType):
            # A reference cast has no runtime effect on the values this
            # translation produces.
            return self._expr(operand)

        source = operand.type
        text = self._num(operand)

        if target.name == "boolean":
            return self._expr(operand)

        source_is_float = (
            isinstance(source, PrimitiveType) and source.name in ("double", "float")
        )

        if target.name == "double":
            return f"{RUNTIME_ALIAS}.i2d({text})" if not source_is_float else text
        if target.name == "float":
            raise EmitError("float is not supported", expr.origin)

        if source_is_float:
            if target.name == "int":
                return f"{RUNTIME_ALIAS}.d2i({text})"
            if target.name == "long":
                return f"{RUNTIME_ALIAS}.d2l({text})"
            inner = f"{RUNTIME_ALIAS}.d2i({text})"
            if target.name == "char":
                return f"{RUNTIME_ALIAS}.JChar({RUNTIME_ALIAS}.jchar({inner}))"
            return f"{RUNTIME_ALIAS}.{self._wrapper(target.name)}({inner})"

        if target.name == "char":
            return f"{RUNTIME_ALIAS}.JChar({RUNTIME_ALIAS}.jchar({text}))"
        if target.name in INTEGRAL:
            return f"{RUNTIME_ALIAS}.{self._wrapper(target.name)}({text})"

        raise EmitError(f"unsupported cast to {target.name}", expr.origin)

    def _instanceof(self, expr: InstanceOf) -> str:
        if not isinstance(expr.target, ClassType):
            raise EmitError("instanceof on a non-class type", expr.origin)
        name = expr.target.name
        mapping = {
            "String": "str",
            "Integer": "int",
            "Double": "float",
            "Boolean": "bool",
        }
        if name in mapping:
            return f"isinstance({self._expr(expr.operand)}, {mapping[name]})"
        if name in self._class_names:
            return f"isinstance({self._expr(expr.operand)}, {name})"
        info = self._program_type(name)
        if info is not None:
            return f"isinstance({self._expr(expr.operand)}, {self._program_ref(info)})"
        raise EmitError(f"instanceof {name} is not supported", expr.origin)

    def _new(self, expr: New) -> str:
        if not isinstance(expr.type, ClassType):
            raise EmitError("new of a non-class type", expr.origin)
        name = expr.type.name
        args = ", ".join(self._expr(a) for a in expr.args)
        if name in self._class_names:
            return f"{name}({args})"
        if name == "StringBuilder":
            return f"{RUNTIME_ALIAS}.StringBuilder({args})"
        if name in ("ArrayList", "List"):
            return f"{RUNTIME_ALIAS}.JArrayList({args})" if args else f"{RUNTIME_ALIAS}.JArrayList()"
        if name in ("HashMap", "Map", "HashSet", "Set", "LinkedHashMap",
                    "TreeMap", "ConcurrentHashMap"):
            raise EmitError(
                f"new {name} is not supported: Java's iteration order for this "
                f"collection is either unspecified or insertion/comparator "
                f"defined, and no Python built-in reproduces it in every case",
                expr.origin,
            )
        cls = self._throwable_class(name)
        if cls is not None:
            return f"{RUNTIME_ALIAS}.{cls}({args})"
        info = self._program_type(name)
        if info is not None:
            self._check_constructible(info, expr)
            return f"{self._program_ref(info)}({args})"
        raise EmitError(f"unsupported class instantiation: new {name}", expr.origin)

    def _check_constructible(self, info, expr: New) -> None:
        """Refuse `new` on an indexed type whose construction is not faithful."""

        if info.kind == "interface":
            raise EmitError(
                f"new {info.simple_name}() on an interface is an anonymous "
                f"class; its body is not in the index",
                expr.origin,
            )
        if "abstract" in info.modifiers:
            raise EmitError(
                f"new {info.simple_name}() on an abstract class is an anonymous "
                f"subclass; its body is not in the index",
                expr.origin,
            )
        constructors = info.methods.get("<init>", [])
        if info.kind == "record":
            expected = len(info.record_components) if not constructors else None
            if expected is not None and len(expr.args) != expected:
                raise EmitError(
                    f"new {info.simple_name} passes {len(expr.args)} arguments "
                    f"to a record with {expected} components",
                    expr.origin,
                )
            return
        if not constructors:
            if expr.args:
                raise EmitError(
                    f"new {info.simple_name} passes {len(expr.args)} arguments "
                    f"but the class declares only the default constructor",
                    expr.origin,
                )
            return
        arities = {
            (len(c.param_types) - 1 if c.is_varargs else len(c.param_types))
            for c in constructors
        }
        fits = any(
            len(expr.args) == len(c.param_types)
            or (c.is_varargs and len(expr.args) >= len(c.param_types) - 1)
            for c in constructors
        )
        if not fits:
            raise EmitError(
                f"new {info.simple_name} passes {len(expr.args)} arguments; the "
                f"declared constructors take {sorted(arities)}",
                expr.origin,
            )
        matching = [
            c
            for c in constructors
            if len(expr.args) == len(c.param_types)
            or (c.is_varargs and len(expr.args) >= len(c.param_types) - 1)
        ]
        if len(matching) > 1:
            # The generated class dispatches on argument *count*.  Two overloads
            # that this call could reach with the same count are separated in
            # Java by the static types of the arguments, which are gone at run
            # time; guessing is worse than refusing.
            raise EmitError(
                f"new {info.simple_name} could reach {len(matching)} "
                f"constructors with {len(expr.args)} arguments; Java separates "
                f"them by static argument types, which are not present at run "
                f"time",
                expr.origin,
            )

    @staticmethod
    def _throwable_class(simple_name: str) -> str | None:
        from ..runtime_ref import supported_throwables

        return supported_throwables().get(simple_name)

    def _new_array(self, expr: NewArray) -> str:
        element = expr.element
        if isinstance(element, ArrayType):
            raise EmitError("multi-dimensional arrays are not supported", expr.origin)
        element_name = element.name if isinstance(element, PrimitiveType) else "ref"
        if expr.init is not None:
            values = ", ".join(self._expr(v) for v in expr.init)
            return f"{RUNTIME_ALIAS}.array_of({element_name!r}, [{values}])"
        if len(expr.dims) != 1:
            raise EmitError(
                "only one-dimensional array creation is supported", expr.origin
            )
        return f"{RUNTIME_ALIAS}.new_array({element_name!r}, {self._num(expr.dims[0])})"

    def _call(self, expr: Call) -> str:
        args = [self._expr(a) for a in expr.args]

        if expr.target is None:
            args = self._pack_varargs(expr.name, expr, args)
            if expr.name in self._static_methods:
                owner = self._owner_of_method(expr.name)
                return f"{owner}.{expr.name}({', '.join(args)})"
            if expr.name in self._instance_methods:
                return f"self.{expr.name}({', '.join(args)})"
            raise EmitError(f"call to unknown method {expr.name}", expr.origin)

        target_type = expr.target.type
        target = self._expr(expr.target)

        sam = uir.sam_of(target_type) or self._user_sam(target_type)
        if sam is not None:
            if expr.name != sam:
                raise EmitError(
                    f"{target_type.name}.{expr.name} is not the single abstract "
                    f"method ({sam}); default methods such as andThen/negate are "
                    f"not supported",
                    expr.origin,
                )
            # The value is a Python callable, so the SAM call *is* the call.
            return f"{target}({', '.join(args)})"

        if isinstance(target_type, ClassType) and target_type.name == "String":
            return self._string_method(target, expr, args)

        if isinstance(target_type, ClassType) and target_type.name == "StringBuilder":
            return f"{target}.{expr.name}({', '.join(args)})"

        if isinstance(target_type, ClassType) and target_type.name in _TIME_OWNERS:
            supported = _TIME_INSTANCE_METHODS.get(target_type.name, frozenset())
            if expr.name not in supported:
                raise EmitError(
                    f"{target_type.name}.{expr.name} is not supported",
                    expr.origin,
                )
            return f"{target}.{expr.name}({', '.join(args)})"

        if isinstance(target_type, ClassType) and self._throwable_class(target_type.name):
            # A caught exception's message is observable; its stack trace is
            # not, so only the message-shaped accessors are supported.
            if expr.name in ("getMessage", "getLocalizedMessage"):
                return f"{target}.message"
            if expr.name == "toString":
                return f"{RUNTIME_ALIAS}.throwable_to_string({target})"
            raise EmitError(
                f"{target_type.name}.{expr.name} is not supported; stack traces "
                f"and causes cannot be reproduced",
                expr.origin,
            )

        if isinstance(target_type, ClassType) and target_type.name in ("List", "ArrayList"):
            supported = {
                "size", "isEmpty", "add", "get", "set", "contains", "indexOf",
                "clear", "toString",
            }
            if expr.name not in supported:
                raise EmitError(
                    f"List.{expr.name} is not supported", expr.origin
                )
            return f"{target}.{expr.name}({', '.join(args)})"

        if isinstance(target_type, ClassType) and target_type.name in self._class_names:
            args = self._pack_varargs(expr.name, expr, args)
            return self._user_object_method(target, target_type.name, expr, args)

        if isinstance(target_type, ClassType):
            info = self._program_type(target_type.name)
            if info is not None:
                return self._program_object_method(target, info, expr, args)

        if isinstance(expr.target, This):
            return f"self.{expr.name}({', '.join(args)})"

        raise EmitError(
            f"call {expr.name} on unresolved receiver type {target_type}", expr.origin
        )

    def _program_object_method(
        self, target: str, info, expr: Call, args: list[str]
    ) -> str:
        """A call on an object whose class is declared in another file.

        Dispatch itself needs no import -- Python looks the method up on the
        instance -- so this deliberately does *not* record one.  What it does do
        is check the call against the scanned declaration, so a name that does
        not exist over there is refused here rather than becoming an
        AttributeError at run time.
        """

        components = {name for name, _ in info.record_components}

        if info.kind == "enum" and expr.name in _ENUM_METHODS:
            return f"{target}.{expr.name}({', '.join(args)})"

        if expr.name == "equals" and len(args) == 1 and not self._program_declares(info, "equals"):
            return f"({target} == {args[0]})"
        if expr.name == "hashCode" and not args and not self._program_declares(info, "hashCode"):
            if info.kind == "record":
                return f"hash({target})"
            raise EmitError(
                f"hashCode() on {info.simple_name}, which does not declare one, "
                f"is identity based in Java and cannot be reproduced",
                expr.origin,
            )
        if expr.name == "toString" and not args and not self._program_declares(info, "toString"):
            if info.kind == "record":
                return f"{target}.toString()"
            raise EmitError(
                f"toString() on {info.simple_name}, which does not declare one, "
                f"prints an identity hash in Java and cannot be reproduced",
                expr.origin,
            )

        if expr.name in components and not args:
            return f"{target}.{expr.name}()"

        method = self._program_method(info, expr.name, expr.origin)
        if method.is_static:
            raise EmitError(
                f"{info.simple_name}.{expr.name} is static but is called on an "
                f"instance",
                expr.origin,
            )
        args = self._pack_program_varargs(method, expr, args)
        return f"{target}.{expr.name}({', '.join(args)})"

    def _program_declares(self, info, name: str) -> bool:
        """Whether ``info`` or one of its indexed superclasses declares ``name``."""

        current = info
        seen: set[str] = set()
        while current is not None:
            if name in current.methods:
                return True
            parent_text = current.superclass_text
            if not parent_text or parent_text in seen:
                return False
            seen.add(parent_text)
            current = self._program_type(parent_text)
        return False

    def _pack_program_varargs(
        self, method, expr: "Call | StaticCall", args: list[str]
    ) -> list[str]:
        """Call-site varargs packing against an indexed signature.

        Same rule as for a local declaration: Java builds the array at the call
        site, so passing the trailing arguments through individually would give
        the callee a different arity than it declares.
        """

        if not method.is_varargs or not method.param_types:
            return args
        fixed = len(method.param_types) - 1
        if len(args) == len(method.param_types) and isinstance(
            expr.args[-1].type, ArrayType
        ):
            return args
        if len(args) < fixed:
            raise EmitError(
                f"{method.name} takes at least {fixed} arguments, {len(args)} "
                f"given",
                expr.origin,
            )
        declared = method.param_types[-1]
        element = declared.element if isinstance(declared, ArrayType) else declared
        element_name = element.name if isinstance(element, PrimitiveType) else "ref"
        rest = ", ".join(args[fixed:])
        return args[:fixed] + [
            f"{RUNTIME_ALIAS}.array_of({element_name!r}, [{rest}])"
        ]

    def _user_object_method(
        self, target: str, class_name: str, expr: Call, args: list[str]
    ) -> str:
        """Calls on an object of a class declared in this compilation unit.

        ``equals``/``hashCode`` are mapped onto Python's protocol rather than
        emitted as method calls, because the emitter generates ``__eq__`` and
        ``__hash__``.  ``toString`` on a class that does not declare one would be
        Java's identity-based default, which no translation can reproduce, so it
        is refused instead of approximated.
        """

        decl = next((d for d in self.module.types if d.name == class_name), None)
        if decl is not None and decl.kind == "enum" and expr.name in _ENUM_METHODS:
            return f"{target}.{expr.name}({', '.join(args)})"
        declared = {m.name for m in decl.methods} if decl is not None else set()
        components = {p.name for p in decl.record_components} if decl is not None else set()

        if expr.name == "equals" and len(args) == 1 and "equals" not in declared:
            return f"({target} == {args[0]})"
        if expr.name == "hashCode" and not args and "hashCode" not in declared:
            if decl is not None and decl.kind == "record":
                return f"hash({target})"
            raise EmitError(
                "hashCode() on a class that does not declare one is identity "
                "based in Java and cannot be reproduced",
                expr.origin,
            )
        if expr.name == "toString" and not args and "toString" not in declared:
            if decl is not None and decl.kind == "record":
                return f"{target}.toString()"
            raise EmitError(
                "toString() on a class that does not declare one prints an "
                "identity hash in Java and cannot be reproduced",
                expr.origin,
            )
        if expr.name not in declared and expr.name not in components:
            raise EmitError(
                f"{class_name}.{expr.name} is not declared in this compilation unit",
                expr.origin,
            )
        return f"{target}.{expr.name}({', '.join(args)})"

    def _user_sam(self, t: uir.Type) -> str | None:
        """The SAM of an interface declared in this compilation unit."""

        if not isinstance(t, ClassType):
            return None
        decl = next(
            (d for d in self.module.types if d.name == t.name and d.kind == "interface"),
            None,
        )
        if decl is None:
            info = self._program_type(t.name)
            if info is None:
                return None
            functional = info.is_functional_interface()
            return functional[0] if functional is not None else None
        abstract = [m for m in decl.methods if m.body is None]
        return abstract[0].name if len(abstract) == 1 else None

    def _find_method(self, name: str) -> Method | None:
        for decl in self.module.types:
            for method in decl.methods:
                if method.name == name:
                    return method
        return None

    def _pack_varargs(self, name: str, expr: Call | StaticCall, args: list[str]) -> list[str]:
        """Collect the trailing arguments of a varargs call into one array.

        Java builds the array at the call site.  Passing the arguments through
        individually would give the callee a different arity than it declares.
        """

        method = self._find_method(name)
        if method is None or not method.params or not method.params[-1].is_varargs:
            return args
        fixed = len(method.params) - 1
        if len(args) == len(method.params) and isinstance(
            expr.args[-1].type, ArrayType
        ):
            # Already an array: Java passes it straight through.
            return args
        element = method.params[-1].type.element
        element_name = element.name if isinstance(element, PrimitiveType) else "ref"
        rest = ", ".join(args[fixed:])
        return args[:fixed] + [
            f"{RUNTIME_ALIAS}.array_of({element_name!r}, [{rest}])"
        ]

    def _owner_of_method(self, name: str) -> str:
        for decl in self.module.types:
            if any(m.name == name and m.is_static for m in decl.methods):
                return decl.name
        return self.module.types[0].name  # pragma: no cover - defensive

    #: String methods the runtime reproduces exactly.
    _STRING_METHODS = frozenset({
        "length", "charAt", "substring", "indexOf", "lastIndexOf", "isEmpty",
        "isBlank", "equals", "equalsIgnoreCase", "toUpperCase", "toLowerCase",
        "trim", "strip", "startsWith", "endsWith", "contains", "replace",
        "repeat", "concat", "compareTo", "hashCode", "split",
    })

    #: Characters that make a `split` argument a regex rather than a literal.
    _REGEX_METACHARACTERS = set(".^$*+?()[]{}|\\")

    def _string_method(self, target: str, expr: Call, args: list[str]) -> str:
        if expr.name not in self._STRING_METHODS:
            raise EmitError(
                f"String.{expr.name} is not supported", expr.origin
            )
        if expr.name == "split":
            self._check_literal_separator(expr)
        joined = ", ".join([target] + args)
        return f"{RUNTIME_ALIAS}.JString.{expr.name}({joined})"

    def _check_literal_separator(self, expr: Call) -> None:
        """``String.split`` takes a *regex*, and the dialects do not agree.

        Java and Python differ on named groups, ``\\p{...}`` classes, and
        possessive quantifiers, so only a literal separator can be translated
        with confidence.
        """

        if len(expr.args) != 1 or not isinstance(expr.args[0], StringLiteral):
            raise EmitError(
                "String.split with a non-literal or limited pattern is not "
                "supported: it takes a regex, and Java's dialect is not "
                "Python's",
                expr.origin,
            )
        pattern = expr.args[0].value
        if any(ch in self._REGEX_METACHARACTERS for ch in pattern):
            raise EmitError(
                f"String.split({pattern!r}) uses regex syntax; only a literal "
                f"separator can be translated with the same meaning",
                expr.origin,
            )

    def _static_call(self, expr: StaticCall) -> str:
        args = [self._expr(a) for a in expr.args]

        if expr.owner in ("System.out", "System.err"):
            if expr.name not in ("println", "print"):
                raise EmitError(f"System.out.{expr.name} is not supported", expr.origin)
            stream = "out" if expr.owner == "System.out" else "err"
            return f"{RUNTIME_ALIAS}.System.{stream}.{expr.name}({', '.join(args)})"

        if expr.owner in ("ZoneId", "ZonedDateTime"):
            raise EmitError(
                f"{expr.owner} resolves through the tz database, and the JVM's "
                f"bundled copy and Python's zoneinfo are versioned separately; "
                f"the two can disagree about a past or future offset. Use a "
                f"fixed ZoneOffset, which has no such dependency",
                expr.origin,
            )

        if expr.owner in _TIME_OWNERS:
            supported = _TIME_STATIC_METHODS.get(expr.owner, frozenset())
            if expr.name not in supported:
                raise EmitError(
                    f"{expr.owner}.{expr.name} is not supported", expr.origin
                )
            return f"{RUNTIME_ALIAS}.{expr.owner}.{expr.name}({', '.join(args)})"

        if expr.owner == "Objects":
            supported = {
                "requireNonNull", "requireNonNullElse", "equals", "isNull",
                "nonNull", "toString", "hash", "hashCode",
            }
            if expr.name not in supported:
                raise EmitError(
                    f"Objects.{expr.name} is not supported", expr.origin
                )
            return f"{RUNTIME_ALIAS}.Objects.{expr.name}({', '.join(args)})"

        if expr.owner == "List":
            if expr.name not in ("of", "copyOf"):
                raise EmitError(f"List.{expr.name} is not supported", expr.origin)
            return f"{RUNTIME_ALIAS}.JavaList.{expr.name}({', '.join(args)})"

        if expr.owner in ("Set", "Map"):
            # Java does not specify the iteration order of Set.of/Map.of, and
            # randomises it per JVM run.  There is no Python structure whose
            # iteration matches, so no translation can be correct.
            raise EmitError(
                f"{expr.owner}.{expr.name} has an unspecified iteration order "
                f"that Java randomises per run; it cannot be reproduced",
                expr.origin,
            )

        if expr.owner == "Math":
            exact = {
                "addExact": "addExact",
                "subtractExact": "subtractExact",
                "multiplyExact": "multiplyExact",
                "negateExact": "negateExact",
            }
            if expr.name in exact and expr.args:
                kind = self._kind(
                    uir.binary_promote(
                        expr.args[0].type,
                        expr.args[-1].type if len(expr.args) > 1 else expr.args[0].type,
                    )
                )
                if kind is None:
                    raise EmitError(
                        f"Math.{expr.name} on a non-integral type", expr.origin
                    )
                return (
                    f"{RUNTIME_ALIAS}.{exact[expr.name]}({kind!r}, {', '.join(args)})"
                )
            if expr.name == "toIntExact":
                return f"{RUNTIME_ALIAS}.toIntExact({', '.join(args)})"
            if expr.name == "abs" and expr.args:
                kind = self._kind(expr.args[0].type)
                if kind is not None:
                    return f"{RUNTIME_ALIAS}.iabs({kind!r}, {args[0]})"
            if expr.name not in (
                "abs", "max", "min", "floor", "ceil", "sqrt", "pow",
                "round", "signum", "floorDiv", "floorMod", "hypot",
            ):
                raise EmitError(f"Math.{expr.name} is not supported", expr.origin)
            return f"{RUNTIME_ALIAS}.Math.{expr.name}({', '.join(args)})"

        if expr.owner in ("Integer", "Long", "Double"):
            return f"{RUNTIME_ALIAS}.{expr.owner}.{expr.name}({', '.join(args)})"

        if expr.owner == "String":
            if expr.name != "valueOf":
                raise EmitError(f"String.{expr.name} is not supported", expr.origin)
            return f"{RUNTIME_ALIAS}.JString.valueOf({', '.join(args)})"

        if expr.owner in self._class_names:
            args = self._pack_varargs(expr.name, expr, args)
            return f"{expr.owner}.{expr.name}({', '.join(args)})"

        info = self._program_type(expr.owner)
        if info is not None:
            method = self._program_method(info, expr.name, expr.origin)
            if not method.is_static:
                raise EmitError(
                    f"{info.simple_name}.{expr.name} is an instance method but "
                    f"is called as a static one",
                    expr.origin,
                )
            args = self._pack_program_varargs(method, expr, args)
            ref = self._program_ref(info)
            return f"{ref}.{expr.name}({', '.join(args)})"

        raise EmitError(
            f"static call {expr.owner}.{expr.name} is not supported", expr.origin
        )

    # -- defaults ---------------------------------------------------------

    def _zero(self, t: uir.Type) -> str:
        if isinstance(t, PrimitiveType):
            if t.name in ("int", "long", "short", "byte"):
                return "0"
            if t.name in ("double", "float"):
                return "0.0"
            if t.name == "boolean":
                return "False"
            if t.name == "char":
                return f"{RUNTIME_ALIAS}.JChar(0)"
        return "None"


def emit_python(module: Module) -> str:
    return PythonEmitter(module).emit()


def survey_blockers(module: Module, index=None) -> list[Blocker]:
    """Every distinct reason ``module`` cannot be translated.

    This is a *projection*, not a proof: where an expression could not be
    emitted, a placeholder took its place, and a construct that consumed that
    value may not have been reached.  Fixing everything listed here therefore
    makes a file *likely* to translate, not certain to.  Types come from the
    front end rather than from emission, so the common cascade -- a wrong type
    inventing a second, spurious blocker -- does not occur.
    """

    return survey_report(module, index).blockers


@dataclass
class SurveyResult:
    blockers: list[Blocker]
    #: Types abandoned at the declaration level.  When this is non-empty the
    #: blocker set is a *floor*: a refusal on the class itself (an interface
    #: with default methods, a field/method name clash, two constructors of the
    #: same arity) stops emission before any method body is walked, so every
    #: blocker inside those bodies is missing from the count.  Treating such a
    #: file as "one capability away" is how a projection ends up promising more
    #: than the work delivers.
    truncated_types: list[str]

    @property
    def truncated(self) -> bool:
        return bool(self.truncated_types)


def survey_report(module: Module, index=None) -> SurveyResult:
    """Blockers plus whether the measurement was cut short. See SurveyResult."""

    emitter = PythonEmitter(module, survey=True, index=index)
    try:
        emitter.emit()
    except SurveyModeError:
        pass
    return SurveyResult(
        blockers=emitter.blockers, truncated_types=list(emitter.truncated_types)
    )
