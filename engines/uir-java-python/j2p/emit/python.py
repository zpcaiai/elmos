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
    ClassType,
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
    LocalVar,
    Method,
    Module,
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
    Ternary,
    This,
    Throw,
    Try,
    TypeDecl,
    Unary,
    UnknownType,
    While,
)

RUNTIME_ALIAS = "rt"

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


class PythonEmitter:
    def __init__(self, module: Module) -> None:
        self.module = module
        self.lines: list[str] = []
        self.source_map: list[SourceMapEntry] = []
        self._static_methods: set[str] = set()
        self._instance_methods: set[str] = set()
        self._static_fields: set[str] = set()
        self._instance_fields: set[str] = set()
        self._record_components: set[str] = set()
        self._class_names: set[str] = {t.name for t in module.types}
        self._enum_names: set[str] = {
            t.name for t in module.types if t.kind == "enum"
        }

    # -- public -----------------------------------------------------------

    def emit(self) -> str:
        self._header()
        for decl in self.module.types:
            self._type_decl(decl)
        self._main_entry()
        return "\n".join(self.lines) + "\n"

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

    def _header(self) -> None:
        self._write(0, '"""Generated from Java by the UIR java->python route.')
        self._write(0, "")
        self._write(0, f"Source module: {self.module.package or '<default>'}")
        self._write(0, "Do not edit: regenerate from the Java source instead.")
        self._write(0, '"""')
        self._write(0, "")
        self._write(0, "import j2p_runtime as rt")
        self._write(0, "")

    # -- declarations -----------------------------------------------------

    def _type_decl(self, decl: TypeDecl) -> None:
        if decl.kind == "interface":
            raise EmitError("interface declarations are not supported", decl.origin)

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

        self._write(0, f"class {decl.name}:", decl.origin)

        body_started = False

        for f in decl.fields:
            if f.is_static:
                value = self._expr(f.init) if f.init is not None else self._zero(f.type)
                self._write(1, f"{f.name} = {value}", f.origin)
                body_started = True

        if decl.kind == "enum":
            for index, constant in enumerate(decl.enum_constants):
                self._write(1, f"{constant} = {index}", decl.origin)
                body_started = True

        if decl.kind == "record":
            self._emit_record(decl)
            return

        constructors = [m for m in decl.methods if m.is_constructor]
        if len(constructors) > 1:
            raise EmitError(
                "overloaded constructors are not supported", constructors[1].origin
            )

        self._write(0, "")
        self._emit_init(decl, constructors[0] if constructors else None)
        body_started = True

        for method in decl.methods:
            if method.is_constructor:
                continue
            self._write(0, "")
            self._emit_method(method)
            body_started = True

        if not body_started:  # pragma: no cover - defensive
            self._write(1, "pass")
        self._write(0, "")

    def _emit_record(self, decl: TypeDecl) -> None:
        names = [p.name for p in decl.record_components]
        params = ", ".join(["self"] + names)
        self._write(1, f"def __init__({params}):", decl.origin)
        if names:
            for p in decl.record_components:
                self._write(2, f"self._{p.name} = {p.name}", p.origin)
        else:
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
                raise EmitError(
                    "explicit record constructors are not supported", method.origin
                )
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
        if isinstance(stmt, Block):
            if not stmt.body:
                self._write(indent, "pass", stmt.origin)
                return
            for inner in stmt.body:
                self._stmt(inner, indent)
            return

        if isinstance(stmt, LocalVar):
            value = (
                self._expr(stmt.init)
                if stmt.init is not None
                else self._zero(stmt.type)
            )
            self._write(indent, f"{stmt.name} = {value}", stmt.origin)
            return

        if isinstance(stmt, ExprStmt):
            self._expr_stmt(stmt.expr, indent, stmt.origin)
            return

        if isinstance(stmt, If):
            self._write(indent, f"if {self._cond(stmt.cond)}:", stmt.origin)
            self._body(stmt.then, indent + 1)
            if stmt.other is not None:
                self._write(indent, "else:", stmt.origin)
                self._body(stmt.other, indent + 1)
            return

        if isinstance(stmt, While):
            self._write(indent, f"while {self._cond(stmt.cond)}:", stmt.origin)
            self._body(stmt.body, indent + 1)
            return

        if isinstance(stmt, DoWhile):
            self._write(indent, "while True:", stmt.origin)
            self._body(stmt.body, indent + 1)
            self._write(indent + 1, f"if not ({self._cond(stmt.cond)}):", stmt.origin)
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
                self._write(indent + 1, f"if not ({cond}):", stmt.origin)
                self._write(indent + 2, "break")
                self._write(indent + 1, "try:")
                self._body(stmt.body, indent + 2)
                self._write(indent + 1, "finally:")
                for update in stmt.update:
                    self._expr_stmt(update, indent + 2, stmt.origin)
            else:
                self._write(indent, f"while {cond}:", stmt.origin)
                self._body(stmt.body, indent + 1)
            return

        if isinstance(stmt, ForEach):
            iterable = self._expr(stmt.iterable)
            self._write(indent, f"for {stmt.var_name} in {iterable}:", stmt.origin)
            self._body(stmt.body, indent + 1)
            return

        if isinstance(stmt, Return):
            if stmt.value is None:
                self._write(indent, "return", stmt.origin)
            else:
                self._write(indent, f"return {self._expr(stmt.value)}", stmt.origin)
            return

        if isinstance(stmt, Break):
            self._write(indent, "break", stmt.origin)
            return

        if isinstance(stmt, Continue):
            self._write(indent, "continue", stmt.origin)
            return

        if isinstance(stmt, Throw):
            self._write(indent, f"raise {self._expr(stmt.value)}", stmt.origin)
            return

        if isinstance(stmt, Try):
            self._emit_try(stmt, indent)
            return

        if isinstance(stmt, Switch):
            self._emit_switch(stmt, indent)
            return

        raise EmitError(f"cannot emit statement {type(stmt).__name__}", stmt.origin)

    def _body(self, stmt: Stmt, indent: int) -> None:
        before = len(self.lines)
        self._stmt(stmt, indent)
        if len(self.lines) == before:
            self._write(indent, "pass")

    def _emit_try(self, stmt: Try, indent: int) -> None:
        if not stmt.catches and stmt.finally_ is None:
            raise EmitError("try with neither catch nor finally", stmt.origin)
        self._write(indent, "try:", stmt.origin)
        self._body(stmt.body, indent + 1)
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

        subject = self._expr(stmt.subject)
        tmp = "_switch_subject"
        self._write(indent, f"{tmp} = {subject}", stmt.origin)
        first = True
        default_case = None
        for case in stmt.cases:
            if not case.labels:
                default_case = case
                continue
            tests = " or ".join(
                f"{tmp} == {self._expr(label)}" for label in case.labels
            )
            keyword = "if" if first else "elif"
            self._write(indent, f"{keyword} {tests}:", case.origin)
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

        self._write(indent, self._expr(expr), origin)

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
        if expr.owner in ("Integer", "Long", "Math") and expr.owner not in self._class_names:
            return f"{RUNTIME_ALIAS}.{expr.owner}.{expr.name}"
        if expr.owner in self._class_names:
            return f"{expr.owner}.{expr.name}"
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
            # Reference identity vs value equality: both operands here are
            # either primitives or Strings, for which Java's == on the values
            # produced by this translation matches Python's ==.
            return f"({left} {op} {right})"

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
            if args:
                raise EmitError("new ArrayList with arguments", expr.origin)
            return "[]"
        if name in ("HashMap", "Map"):
            if args:
                raise EmitError("new HashMap with arguments", expr.origin)
            return "{}"
        if name in ("HashSet", "Set"):
            if args:
                raise EmitError("new HashSet with arguments", expr.origin)
            return "set()"
        cls = self._throwable_class(name)
        if cls is not None:
            return f"{RUNTIME_ALIAS}.{cls}({args})"
        raise EmitError(f"unsupported class instantiation: new {name}", expr.origin)

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
            if expr.name in self._static_methods:
                owner = self._owner_of_method(expr.name)
                return f"{owner}.{expr.name}({', '.join(args)})"
            if expr.name in self._instance_methods:
                return f"self.{expr.name}({', '.join(args)})"
            raise EmitError(f"call to unknown method {expr.name}", expr.origin)

        target_type = expr.target.type
        target = self._expr(expr.target)

        if isinstance(target_type, ClassType) and target_type.name == "String":
            return self._string_method(target, expr, args)

        if isinstance(target_type, ClassType) and target_type.name == "StringBuilder":
            return f"{target}.{expr.name}({', '.join(args)})"

        if isinstance(target_type, ClassType) and target_type.name in self._class_names:
            return self._user_object_method(target, target_type.name, expr, args)

        if isinstance(expr.target, This):
            return f"self.{expr.name}({', '.join(args)})"

        raise EmitError(
            f"call {expr.name} on unresolved receiver type {target_type}", expr.origin
        )

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

    def _owner_of_method(self, name: str) -> str:
        for decl in self.module.types:
            if any(m.name == name and m.is_static for m in decl.methods):
                return decl.name
        return self.module.types[0].name  # pragma: no cover - defensive

    def _string_method(self, target: str, expr: Call, args: list[str]) -> str:
        supported = {
            "length",
            "charAt",
            "substring",
            "indexOf",
            "isEmpty",
            "equals",
            "toUpperCase",
            "toLowerCase",
            "trim",
        }
        if expr.name not in supported:
            raise EmitError(
                f"String.{expr.name} is not supported", expr.origin
            )
        joined = ", ".join([target] + args)
        return f"{RUNTIME_ALIAS}.JString.{expr.name}({joined})"

    def _static_call(self, expr: StaticCall) -> str:
        args = [self._expr(a) for a in expr.args]

        if expr.owner in ("System.out", "System.err"):
            if expr.name not in ("println", "print"):
                raise EmitError(f"System.out.{expr.name} is not supported", expr.origin)
            stream = "out" if expr.owner == "System.out" else "err"
            return f"{RUNTIME_ALIAS}.System.{stream}.{expr.name}({', '.join(args)})"

        if expr.owner == "Math":
            if expr.name == "abs" and expr.args:
                kind = self._kind(expr.args[0].type)
                if kind is not None:
                    return f"{RUNTIME_ALIAS}.iabs({kind!r}, {args[0]})"
            if expr.name not in ("abs", "max", "min", "floor", "ceil", "sqrt", "pow"):
                raise EmitError(f"Math.{expr.name} is not supported", expr.origin)
            return f"{RUNTIME_ALIAS}.Math.{expr.name}({', '.join(args)})"

        if expr.owner in ("Integer", "Long", "Double"):
            return f"{RUNTIME_ALIAS}.{expr.owner}.{expr.name}({', '.join(args)})"

        if expr.owner == "String":
            if expr.name != "valueOf":
                raise EmitError(f"String.{expr.name} is not supported", expr.origin)
            return f"{RUNTIME_ALIAS}.JString.valueOf({', '.join(args)})"

        if expr.owner in self._class_names:
            return f"{expr.owner}.{expr.name}({', '.join(args)})"

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
