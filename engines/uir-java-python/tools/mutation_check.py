#!/usr/bin/env python3
"""Mutation testing: delete each enforced rule and require the suite to go red.

A passing test suite proves nothing on its own.  It proves something once you
have shown that removing any single rule the code enforces makes the suite fail.
Each mutation below deletes exactly one rule — the 32-bit wrap, the truncating
division, the bounds check, the emitter's routing through the runtime — and the
suite must catch it.

A *surviving* mutant is not a nuisance to be suppressed.  It is a statement that
some rule in this codebase is either untested or has no effect, and both of those
are defects.  The tool exits non-zero when any mutant survives.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Mutation:
    id: str
    file: str
    rule: str
    old: str
    new: str


MUTATIONS: list[Mutation] = [
    # ---- runtime: integral wrapping -------------------------------------
    Mutation(
        "M01",
        "runtime/j2p_runtime.py",
        "int arithmetic wraps at 32 bits",
        "    return ((value + 2 ** 31) & (2 ** 32 - 1)) - 2 ** 31",
        "    return value",
    ),
    Mutation(
        "M02",
        "runtime/j2p_runtime.py",
        "long arithmetic wraps at 64 bits",
        "def jlong(value: int) -> int:\n    return ((value + 2 ** 63) & (2 ** 64 - 1)) - 2 ** 63",
        "def jlong(value: int) -> int:\n    return value",
    ),
    Mutation(
        "M03",
        "runtime/j2p_runtime.py",
        "char is unsigned 16-bit",
        "def jchar(value: int) -> int:\n    \"\"\"``char`` is the one unsigned integral type in Java.\"\"\"\n\n    return value & CHAR_MAX",
        "def jchar(value: int) -> int:\n    \"\"\"``char`` is the one unsigned integral type in Java.\"\"\"\n\n    return value",
    ),
    Mutation(
        "M04",
        "runtime/j2p_runtime.py",
        "byte narrows to 8 bits",
        "def jbyte(value: int) -> int:\n    return ((value + 2 ** 7) & (2 ** 8 - 1)) - 2 ** 7",
        "def jbyte(value: int) -> int:\n    return value",
    ),
    # ---- runtime: division and remainder --------------------------------
    Mutation(
        "M05",
        "runtime/j2p_runtime.py",
        "integer division truncates toward zero",
        "    q = abs(a) // abs(b)\n    if (a < 0) != (b < 0):\n        q = -q\n    return WRAP[kind](q)",
        "    return WRAP[kind](a // b)",
    ),
    Mutation(
        "M06",
        "runtime/j2p_runtime.py",
        "remainder takes the sign of the dividend",
        "    r = abs(a) % abs(b)\n    if a < 0:\n        r = -r\n    return WRAP[kind](r)",
        "    return WRAP[kind](a % b)",
    ),
    Mutation(
        "M07",
        "runtime/j2p_runtime.py",
        "integer division by zero raises ArithmeticException",
        "    if b == 0:\n        raise ArithmeticExceptionJ(\"/ by zero\")\n    q = abs(a)",
        "    q = abs(a)",
    ),
    Mutation(
        "M08",
        "runtime/j2p_runtime.py",
        "floating division by zero yields infinity instead of raising",
        "    if b == 0.0:\n        if a == 0.0 or math.isnan(a):\n            return math.nan\n        sign = math.copysign(1.0, a) * math.copysign(1.0, b)\n        return math.inf if sign > 0 else -math.inf\n",
        "",
    ),
    # ---- runtime: shifts -------------------------------------------------
    Mutation(
        "M09",
        "runtime/j2p_runtime.py",
        "shift distance is masked",
        "    b &= 63 if kind == \"long\" else 31\n    return WRAP[kind](a << b)",
        "    return WRAP[kind](a << b)",
    ),
    Mutation(
        "M10",
        "runtime/j2p_runtime.py",
        "unsigned right shift fills with zeros",
        "    width = 64 if kind == \"long\" else 32\n    b &= width - 1\n    return WRAP[kind]((a & (2 ** width - 1)) >> b)",
        "    return WRAP[kind](a >> b)",
    ),
    # ---- runtime: narrowing ---------------------------------------------
    Mutation(
        "M11",
        "runtime/j2p_runtime.py",
        "double-to-int cast maps NaN to zero",
        "    if math.isnan(value):\n        return 0\n    if value >= INT_MAX:",
        "    if value >= INT_MAX:",
    ),
    Mutation(
        "M12",
        "runtime/j2p_runtime.py",
        "double-to-int cast saturates instead of overflowing",
        "    if value >= INT_MAX:\n        return INT_MAX\n    if value <= INT_MIN:\n        return INT_MIN\n    return int(value)",
        "    return int(value)",
    ),
    Mutation(
        "M13",
        "runtime/j2p_runtime.py",
        "Math.abs of MIN_VALUE wraps rather than widening",
        "    return WRAP[kind](value if value >= 0 else -value)",
        "    return abs(value)",
    ),
    # ---- runtime: string conversion --------------------------------------
    Mutation(
        "M14",
        "runtime/j2p_runtime.py",
        "Double.toString uses Java's notation thresholds",
        "    if 1e-3 <= magnitude < 1e7:\n        text = _plain_decimal(digits, exponent)\n    else:\n        text = _scientific(digits, exponent)",
        "    text = repr(magnitude)",
    ),
    Mutation(
        "M15",
        "runtime/j2p_runtime.py",
        "null converts to the string \"null\"",
        "    if value is None:\n        return \"null\"",
        "    if value is None:\n        return \"None\"",
    ),
    Mutation(
        "M16",
        "runtime/j2p_runtime.py",
        "booleans convert to lowercase true/false",
        "        return \"true\" if value else \"false\"",
        "        return str(value)",
    ),
    # ---- runtime: arrays and strings -------------------------------------
    Mutation(
        "M17",
        "runtime/j2p_runtime.py",
        "array index bounds are checked on both sides",
        "        if index < 0 or index >= len(self.data):",
        "        if index >= len(self.data):",
    ),
    Mutation(
        "M18",
        "runtime/j2p_runtime.py",
        "Integer.parseInt rejects values outside int range",
        "        if value < INT_MIN or value > INT_MAX:\n            raise NumberFormatExceptionJ(f'For input string: \"{text}\"')\n        return value",
        "        return value",
    ),
    # ---- emitter ---------------------------------------------------------
    Mutation(
        "M19",
        "j2p/emit/python.py",
        "integer division is emitted through the truncating helper",
        "            if op == \"/\":\n                return f\"{RUNTIME_ALIAS}.idiv({kind!r}, {left}, {right})\"",
        "            if op == \"/\":\n                return f\"({left} // {right})\"",
    ),
    Mutation(
        "M20",
        "j2p/emit/python.py",
        "integral arithmetic is emitted through the wrapping helper",
        "            if op in (\"+\", \"-\", \"*\", \"&\", \"|\", \"^\"):\n                return f\"{RUNTIME_ALIAS}.{self._wrapper(kind)}({left} {op} {right})\"",
        "            if op in (\"+\", \"-\", \"*\", \"&\", \"|\", \"^\"):\n                return f\"({left} {op} {right})\"",
    ),
    Mutation(
        "M21",
        "j2p/emit/python.py",
        "compound assignment casts back to the target type",
        "                value = self._expr(\n                    Cast(\n                        origin=expr.origin,\n                        type=expr.target.type,\n                        target=expr.target.type,\n                        operand=combined,\n                    )\n                )\n            hoisted, self._hoisted = self._hoisted, saved",
        "                value = self._expr(combined)\n            hoisted, self._hoisted = self._hoisted, saved",
    ),
    Mutation(
        "M22",
        "j2p/emit/python.py",
        "switch fall-through is refused rather than mistranslated",
        "        for case in stmt.cases:\n            self._require_terminated_case(case, stmt.origin)",
        "        pass",
    ),
    Mutation(
        "M23",
        "j2p/emit/python.py",
        "string concatenation uses Java's conversion rules",
        "            parts = \", \".join(self._expr(p) for p in expr.parts)\n            return f\"{RUNTIME_ALIAS}.concat({parts})\"",
        "            parts = \" + \".join(f\"str({self._expr(p)})\" for p in expr.parts)\n            return f\"({parts})\"",
    ),
    Mutation(
        "M24",
        "j2p/emit/python.py",
        "the for-loop update runs even when the body continues",
        "                self._write(indent + 1, \"try:\")\n                self._body(stmt.body, indent + 2)\n                self._write(indent + 1, \"finally:\")\n                for update in stmt.update:\n                    self._expr_stmt(update, indent + 2, stmt.origin)",
        "                self._body(stmt.body, indent + 1)\n                for update in stmt.update:\n                    self._expr_stmt(update, indent + 1, stmt.origin)",
    ),
    Mutation(
        "M25",
        "j2p/emit/python.py",
        "a record component and its accessor are kept distinct",
        "        if isinstance(expr.target, This) and expr.name in self._record_components:\n            return f\"_{expr.name}\"",
        "        pass",
    ),
    Mutation(
        "M26",
        "j2p/emit/python.py",
        "++ in expression position is refused",
        "        if isinstance(expr, IncDec):\n            raise EmitError(",
        "        if isinstance(expr, IncDec) and False:\n            raise EmitError(",
    ),
    # ---- front end -------------------------------------------------------
    Mutation(
        "M27",
        "j2p/frontend/java.py",
        "assignment inserts Java's implicit widening conversion",
        "        if target.name == expr.type.name:\n            return expr\n        if target.name == \"boolean\" or expr.type.name == \"boolean\":\n            return expr\n        return Cast(origin=expr.origin, type=target, target=target, operand=expr)",
        "        return expr",
    ),
    Mutation(
        "M28",
        "j2p/frontend/java.py",
        "shift result type comes from the left operand alone",
        "            return Binary(\n                origin=origin,\n                type=self._unary_promote(left.type),\n                op=op,\n                left=left,\n                right=right,\n            )",
        "            return Binary(\n                origin=origin,\n                type=self._binary_promote(left.type, right.type),\n                op=op,\n                left=left,\n                right=right,\n            )",
    ),
    Mutation(
        "M29",
        "j2p/frontend/java.py",
        "String + x is concatenation, not addition",
        "        if op == \"+\" and (self._is_string(left.type) or self._is_string(right.type)):",
        "        if False:",
    ),
    Mutation(
        "M30",
        "j2p/frontend/java.py",
        "a parameter shadows a field of the same name",
        "                if not is_field:\n                    return Name(origin=origin, type=declared, ident=name)",
        "                if False:\n                    return Name(origin=origin, type=declared, ident=name)",
    ),
    # ---- records and switch expressions ----------------------------------
    Mutation(
        "M40",
        "j2p/emit/python.py",
        "a compact constructor body runs before the fields are stored",
        "            if compact is not None and compact.body is not None:\n                # The compact body runs first and may reassign the parameters;\n                # the fields are written from whatever they hold afterwards.\n                for stmt in compact.body.body:\n                    self._stmt(stmt, 2)\n",
        "",
    ),
    Mutation(
        "M41",
        "j2p/frontend/java.py",
        "compact constructor parameters shadow the record's components",
        "        for component in components:\n            scope.names[component.name] = component.type",
        "        pass",
    ),
    Mutation(
        "M42",
        "j2p/emit/python.py",
        "a switch expression evaluates its subject exactly once",
        '        tmp = self._fresh("switch_value")\n        self._hoisted.append((0, f"{tmp} = {self._expr(expr.subject)}", expr.origin))',
        '        tmp = f"({self._expr(expr.subject)})"',
    ),
    Mutation(
        "M43",
        "j2p/emit/python.py",
        "a hoisted statement is refused where it would be evaluated once instead of many times",
        '        if hoisted:\n            raise EmitError(',
        '        if False:\n            raise EmitError(',
    ),
    Mutation(
        "M44",
        "j2p/frontend/java.py",
        "an arrow switch case is terminated so it cannot read as fall-through",
        "        if not body or not isinstance(body[-1], (Return, Throw, Break)):\n            body.append(Break(origin=origin))",
        "        pass",
    ),
    Mutation(
        "M45",
        "j2p/frontend/java.py",
        "a switch expression without a default is refused",
        '        if not any(not case.labels for case in cases):\n            self._reject(',
        '        if False:\n            self._reject(',
    ),
    Mutation(
        "M46",
        "j2p/emit/python.py",
        "a class literal is refused rather than invented",
        '        if isinstance(expr, ClassLiteral):\n            raise EmitError(',
        '        if isinstance(expr, ClassLiteral) and False:\n            raise EmitError(',
    ),
    # ---- standard library ------------------------------------------------
    Mutation(
        "M47",
        "runtime/j2p_runtime.py",
        "Math.round is floor(x+0.5), not Python's banker's rounding",
        "        return int(math.floor(value + 0.5))",
        "        return round(value)",
    ),
    Mutation(
        "M48",
        "runtime/j2p_runtime.py",
        "Math.*Exact raises on overflow instead of wrapping",
        '    if value < low or value > high:\n        raise ArithmeticExceptionJ(f"{what} overflow")\n    return value',
        "    return value",
    ),
    Mutation(
        "M49",
        "runtime/j2p_runtime.py",
        "String.hashCode wraps at every step of the 31-based algorithm",
        "            h = jint(31 * h + ord(ch))",
        "            h = 31 * h + ord(ch)",
    ),
    Mutation(
        "M50",
        "runtime/j2p_runtime.py",
        "String.compareTo returns the character difference, not its sign",
        "                return jint(ord(a) - ord(b))",
        "                return 1 if a > b else -1",
    ),
    Mutation(
        "M51",
        "runtime/j2p_runtime.py",
        "String.split drops trailing empty strings",
        '        while len(parts) > 1 and parts[-1] == "":\n            parts.pop()',
        "        pass",
    ),
    Mutation(
        "M52",
        "runtime/j2p_runtime.py",
        "isBlank uses Java's whitespace set, not Python's",
        "    if code_point in (0xA0, 0x2007, 0x202F):\n        return False  # non-breaking: whitespace to Python, not to Java",
        "    if code_point in (0xA0, 0x2007, 0x202F):\n        return True",
    ),
    Mutation(
        "M53",
        "runtime/j2p_runtime.py",
        "Integer.toHexString formats the unsigned 32-bit pattern",
        '        return format(value & 0xFFFFFFFF, "x")',
        '        return format(value, "x")',
    ),
    Mutation(
        "M54",
        "runtime/j2p_runtime.py",
        "List.of is immutable",
        "    def add(self, *_args):\n        raise UnsupportedOperationExceptionJ(None)",
        "    def add(self, value):\n        self._items.append(value)\n        return True",
    ),
    Mutation(
        "M55",
        "runtime/j2p_runtime.py",
        "List.of rejects null elements",
        '        for item in self._items:\n            if item is None:\n                raise NullPointerExceptionJ("element is null")',
        "        pass",
    ),
    Mutation(
        "M56",
        "runtime/j2p_runtime.py",
        "list indices are bounds-checked on both sides",
        "    def get(self, index: int):\n        index = num(index)\n        if index < 0 or index >= len(self._items):\n            raise IndexOutOfBoundsExceptionJ(\n                f\"Index {index} out of bounds for length {len(self._items)}\"\n            )\n        return self._items[index]\n\n    def contains",
        "    def get(self, index: int):\n        return self._items[num(index)]\n\n    def contains",
    ),
    Mutation(
        "M57",
        "runtime/j2p_runtime.py",
        "Objects.requireNonNull raises rather than returning null",
        "        if value is None:\n            raise NullPointerExceptionJ(message)\n        return value",
        "        return value",
    ),
    # ---- try-with-resources and varargs ----------------------------------
    Mutation(
        "M58",
        "j2p/emit/python.py",
        "a close() failure during an in-flight exception is suppressed",
        '        self._write(indent + 1, f"except {RUNTIME_ALIAS}.JavaThrowable:")\n        self._write(indent + 2, f"if {primary} is None:")\n        self._write(indent + 3, "raise")',
        '        self._write(indent + 1, f"except {RUNTIME_ALIAS}.JavaThrowable:")\n        self._write(indent + 2, "raise")',
    ),
    Mutation(
        "M59",
        "j2p/emit/python.py",
        "resources are closed in reverse declaration order",
        "        self._write(indent, \"try:\")\n        self._emit_resources(stmt, index + 1, indent + 1)",
        "        self._emit_resources(stmt, index + 1, indent)\n        self._write(indent, \"try:\")\n        self._write(indent + 1, \"pass\")",
    ),
    Mutation(
        "M60",
        "j2p/emit/python.py",
        "varargs arguments are packed into an array at the call site",
        '        return args[:fixed] + [\n            f"{RUNTIME_ALIAS}.array_of({element_name!r}, [{rest}])"\n        ]',
        "        return args",
    ),
    Mutation(
        "M61",
        "j2p/emit/python.py",
        "String.split refuses a regex separator",
        "        if any(ch in self._REGEX_METACHARACTERS for ch in pattern):\n            raise EmitError(",
        "        if False:\n            raise EmitError(",
    ),
    # ---- java.time -------------------------------------------------------
    Mutation(
        "M62",
        "runtime/j2p_time.py",
        "month arithmetic clamps the day to the target month's length",
        "        return LocalDate(year, month, min(self.day, length_of_month(year, month)))",
        "        return LocalDate(year, month, self.day)",
    ),
    Mutation(
        "M63",
        "runtime/j2p_time.py",
        "Instant prints its fraction in groups of three digits",
        '    if nanos % 1_000_000 == 0:\n        return str(nanos // 1_000_000).rjust(3, "0")\n    if nanos % 1000 == 0:\n        return str(nanos // 1000).rjust(6, "0")',
        '    if False:\n        return ""\n    if False:\n        return ""',
    ),
    Mutation(
        "M64",
        "runtime/j2p_time.py",
        "Duration.toString drops trailing zeros from the fraction",
        '            out += ("." + str(self.nanos).rjust(9, "0")).rstrip("0")',
        '            out += "." + str(self.nanos).rjust(9, "0")',
    ),
    Mutation(
        "M65",
        "runtime/j2p_time.py",
        "LocalTime omits seconds when they are zero, unlike Instant",
        "        if self.second != 0 or self.nano != 0:",
        "        if True:",
    ),
    Mutation(
        "M66",
        "runtime/j2p_time.py",
        "ChronoUnit truncates toward zero rather than flooring",
        "        return _truncate_div(delta_nanos, self.seconds * NANOS_PER_SECOND)",
        "        return delta_nanos // (self.seconds * NANOS_PER_SECOND)",
    ),
    Mutation(
        "M67",
        "runtime/j2p_time.py",
        "an impossible date raises rather than being silently accepted",
        "    if day > length_of_month(year, month):",
        "    if False:",
    ),
    Mutation(
        "M68",
        "runtime/j2p_time.py",
        "years beyond four digits are printed with Java's + prefix",
        '    if year > 9999:\n        return "+" + str(year)',
        '    if year > 9999:\n        return str(year)',
    ),
    Mutation(
        "M69",
        "j2p/emit/python.py",
        "named time zones are refused because the tz database is not pinned",
        '        if expr.owner in ("ZoneId", "ZonedDateTime"):\n            raise EmitError(',
        '        if False:\n            raise EmitError(',
    ),
    # ---- blocker survey ---------------------------------------------------
    Mutation(
        "M70",
        "j2p/emit/python.py",
        "survey-mode output is refused as a translation",
        '        if self.survey:\n            raise SurveyModeError(',
        '        if False:\n            raise SurveyModeError(',
    ),
    Mutation(
        "M71",
        "j2p/emit/python.py",
        "an untranslatable expression does not hide the rest of the statement",
        "            try:\n                return self._expr_inner(expr)\n            except EmitError as exc:\n                self._record(exc)\n                return BLOCKED_PLACEHOLDER",
        "            return self._expr_inner(expr)",
    ),
    Mutation(
        "M72",
        "j2p/emit/python.py",
        "an untranslatable statement does not hide the rest of the file",
        "            except EmitError as exc:\n                self._record(exc)\n                del self.lines[depth:]\n                self._write(indent, \"pass\", stmt.origin)\n            return",
        "            except EmitError:\n                raise\n            return",
    ),
    Mutation(
        "M73",
        "j2p/emit/python.py",
        "blocker categories group by capability, not by occurrence",
        '    text = _BACKTICKED.sub("_", text)\n    text = _PARENTHESISED.sub("", text)',
        "    pass",
    ),
    # ---- whole-program symbol resolution ---------------------------------
    Mutation(
        "M74",
        "j2p/program.py",
        "a nested type is qualified through its enclosing type",
        '    if enclosing is not None:',
        '    if False:',
    ),
    Mutation(
        "M75",
        "j2p/program.py",
        "a duplicate qualified name is reported, not silently overwritten",
        "            existing = self.types.get(info.qualified_name)\n            if existing is not None:",
        "            existing = None\n            if existing is not None:",
    ),
    Mutation(
        "M76",
        "j2p/program.py",
        "an unlowerable parameter type does not erase the whole signature",
        "    except (UnsupportedConstruct, RecursionError):\n        return UnknownType(\"scan:unsupported-type\")",
        "    except (UnsupportedConstruct, RecursionError):\n        raise",
    ),
    Mutation(
        "M77",
        "j2p/emit/python.py",
        "a cross-file class is reached through its module, not imported by name",
        '        self._program_imports[info.simple_name] = info.module\n        return f"_m_{info.module}.{info.simple_name}"',
        '        self._program_imports[info.simple_name] = info.module\n        return info.simple_name',
    ),
    Mutation(
        "M78",
        "j2p/emit/python.py",
        "same-arity overloads in another file are refused, not guessed",
        "        raise EmitError(\n            f\"{info.qualified_name}.{name} has {len(matching)} overloads taking \"",
        "        return matching[0]\n        raise EmitError(\n            f\"{info.qualified_name}.{name} has {len(matching)} overloads taking \"",
    ),
    Mutation(
        "M79",
        "j2p/emit/python.py",
        "a method that does not exist in the scanned program is refused",
        '            raise EmitError(\n                f"{info.qualified_name}.{name} is not declared in the scanned "\n                f"program",\n                origin,\n            )',
        "            return None",
    ),
    Mutation(
        "M80",
        "j2p/emit/python.py",
        "an instance method called statically is refused",
        '            if not method.is_static:\n                raise EmitError(',
        "            if False:\n                raise EmitError(",
    ),
    Mutation(
        "M81",
        "j2p/emit/python.py",
        "a cross-file constructor call is checked against the declared arity",
        "        if not fits:\n            raise EmitError(",
        "        if False:\n            raise EmitError(",
    ),
    Mutation(
        "M82",
        "j2p/emit/python.py",
        "a cross-file call reaching two same-arity constructors is refused",
        "        if len(matching) > 1:",
        "        if False:",
    ),
    Mutation(
        "M83",
        "j2p/emit/python.py",
        "new on an abstract class in another file is refused",
        '        if "abstract" in info.modifiers:',
        "        if False:",
    ),
    Mutation(
        "M84",
        "j2p/emit/python.py",
        "a non-static field accessed statically across files is refused",
        "            if declared is None or not declared.is_static:",
        "            if declared is None:",
    ),
    Mutation(
        "M85",
        "j2p/emit/python.py",
        "varargs are packed at the call site against the indexed signature",
        "        if not method.is_varargs or not method.param_types:\n            return args",
        "        if True:\n            return args",
    ),
    Mutation(
        "M86",
        "j2p/emit/python.py",
        "a method inherited from an indexed superclass resolves",
        "            inherited = self._inherited_method(info, name)",
        "            inherited = None",
    ),
    Mutation(
        "M87",
        "j2p/emit/python.py",
        "a field and a method of the same name are refused",
        "            if clash:\n                raise EmitError(",
        "            if False:\n                raise EmitError(",
    ),
    Mutation(
        "M98",
        "j2p/emit/python.py",
        "a class-level refusal marks the survey measurement as truncated",
        "            if not self._guard(lambda d=decl: self._type_decl(d), decl.origin):\n                self.truncated_types.append(decl.name)",
        "            self._guard(lambda d=decl: self._type_decl(d), decl.origin)",
    ),
    # ---- var, scoping and charsets ----------------------------------------
    Mutation(
        "M129",
        "j2p/frontend/java.py",
        "`var` takes the initialiser's type, not a class named var",
        "                    if inferred:\n                        init = self._expr(value_node, scope)\n                        var_type = init.type",
        "                    if inferred:\n                        init = self._expr(value_node, scope)",
    ),
    Mutation(
        "M130",
        "j2p/frontend/java.py",
        "`var` in a for-each takes the element type of what is iterated",
        '            if self._text(type_node) == "var":\n                # `for (var w : words)` takes the element type of what is being\n                # iterated, the same way `var w = words.get(0)` would.\n                var_type = self._element_type(iterable.type)',
        '            if self._text(type_node) == "var":\n                var_type = UnknownType("foreach-element")',
    ),
    Mutation(
        "M131",
        "j2p/frontend/java.py",
        "List.of/Set.of carry the element type of their arguments",
        "                element = self._common_type([a.type for a in args])\n                return ClassType(\"List\" if owner == \"List\" else \"Set\", (element,))",
        "                return ClassType(\"List\" if owner == \"List\" else \"Set\")",
    ),
    Mutation(
        "M132",
        "j2p/frontend/java.py",
        "a factory with mixed element types does not claim one of them",
        "        return first if all(t == first for t in types[1:]) else UnknownType(\n            \"mixed-factory-elements\"\n        )",
        "        return first",
    ),
    Mutation(
        "M133",
        "j2p/frontend/java.py",
        "a file's own declarations resolve before the global table",
        "        own = self.index.resolve_in_file(name, self.filename)\n        if own is not None:\n            return own",
        "        own = None",
    ),
    Mutation(
        "M134",
        "j2p/emit/python.py",
        "cross-file overloads are selected by argument count",
        "        matching = [\n            m\n            for m in overloads\n            if len(m.param_types) == argc\n            or (m.is_varargs and argc >= len(m.param_types) - 1)\n        ]",
        "        matching = list(overloads)",
    ),
    Mutation(
        "M135",
        "j2p/emit/python.py",
        "String.getBytes() without a charset is refused",
        '        if not expr.args:\n            raise EmitError(\n                "String.getBytes() without a charset uses the platform default, "',
        '        if False:\n            raise EmitError(\n                "String.getBytes() without a charset uses the platform default, "',
    ),
    Mutation(
        "M136",
        "runtime/j2p_runtime.py",
        "getBytes replaces unencodable characters instead of raising",
        '        raw = s.encode(codec, errors="replace")',
        "        raw = s.encode(codec)",
    ),
    Mutation(
        "M137",
        "runtime/j2p_runtime.py",
        "getBytes returns signed bytes",
        '        return array_of("byte", [jbyte(b) for b in raw])',
        '        return array_of("byte", list(raw))',
    ),
    # ---- regex ------------------------------------------------------------
    Mutation(
        "M119",
        "j2p/emit/regex.py",
        "`.` is rewritten to exclude Java's five line terminators, not Python's one",
        '        if ch == ".":\n            out.append(JAVA_DOT)',
        '        if ch == ".":\n            out.append(".")',
    ),
    Mutation(
        "M120",
        "runtime/j2p_runtime.py",
        "regex is compiled ASCII, because Java's \\d and \\w are ASCII-only",
        "        found = re.compile(pattern, re.ASCII)",
        "        found = re.compile(pattern)",
    ),
    Mutation(
        "M121",
        "runtime/j2p_runtime.py",
        "String.matches requires the whole string to match",
        "        return _compiled(translated_pattern).fullmatch(s) is not None",
        "        return _compiled(translated_pattern).match(s) is not None",
    ),
    Mutation(
        "M122",
        "j2p/emit/regex.py",
        "\\p{...} Unicode property classes are refused",
        '            if nxt in "pP":\n                raise UnsupportedRegex(',
        '            if False:\n                raise UnsupportedRegex(',
    ),
    Mutation(
        "M123",
        "j2p/emit/regex.py",
        "possessive quantifiers are refused",
        '            if ch in "*+?" and i + 1 < n and pattern[i + 1] == "+":\n                raise UnsupportedRegex(',
        '            if False:\n                raise UnsupportedRegex(',
    ),
    Mutation(
        "M124",
        "j2p/emit/regex.py",
        "(?<name>...) named groups are refused",
        '                if rest.startswith("<"):\n                    raise UnsupportedRegex(',
        '                if False:\n                    raise UnsupportedRegex(',
    ),
    Mutation(
        "M125",
        "j2p/emit/regex.py",
        "a character class swallows metacharacters instead of rewriting them",
        '        if in_class:\n            if ch == "]":',
        '        if False:\n            if ch == "]":',
    ),
    Mutation(
        "M126",
        "j2p/emit/python.py",
        "a non-literal matches() pattern is refused",
        '        if len(expr.args) != 1 or not isinstance(expr.args[0], StringLiteral):\n            raise EmitError(\n                "String.matches with a non-literal pattern is not supported: "',
        '        if False:\n            raise EmitError(\n                "String.matches with a non-literal pattern is not supported: "',
    ),
    # ---- unqualified calls into the enclosing class ------------------------
    Mutation(
        "M127",
        "j2p/emit/python.py",
        "an unqualified call resolves to the enclosing class's static method",
        "            enclosing = self._enclosing_static_owner(expr.name, expr.origin)",
        "            enclosing = None",
    ),
    Mutation(
        "M128",
        "j2p/emit/python.py",
        "an ambiguous unqualified static call is refused, not guessed",
        "        if len(owners) > 1:\n            raise EmitError(",
        "        if False:\n            raise EmitError(",
    ),
    # ---- collections: iteration order ------------------------------------
    Mutation(
        "M99",
        "j2p/emit/python.py",
        "an unordered map's keySet/entrySet/toString is refused",
        "            if name not in _ORDERED_COLLECTION_TYPES:\n                raise EmitError(",
        "            if False:\n                raise EmitError(",
    ),
    Mutation(
        "M100",
        "j2p/emit/python.py",
        "iterating an unordered collection is refused",
        '            self._reject_unordered(stmt.iterable, "iterated by a for-each loop")',
        "            pass",
    ),
    Mutation(
        "M101",
        "j2p/emit/python.py",
        "printing an unordered collection is refused",
        '            for arg in expr.args:\n                self._reject_unordered(arg, "printed")',
        "            for arg in expr.args:\n                pass",
    ),
    Mutation(
        "M102",
        "j2p/emit/python.py",
        "concatenating an unordered collection into a string is refused",
        '            for part in expr.parts:\n                self._reject_unordered(part, "converted to a string")',
        "            for part in expr.parts:\n                pass",
    ),
    Mutation(
        "M103",
        "j2p/emit/python.py",
        "an order-sensitive stream terminal needs an ordered source",
        "        if expr.name in _STREAM_ORDER_SENSITIVE and not self._stream_is_ordered(\n            expr.target\n        ):",
        "        if False:",
    ),
    Mutation(
        "M104",
        "j2p/emit/python.py",
        "sorted() establishes an encounter order for what follows it",
        '            if source.name == "sorted":\n                return True',
        '            if source.name == "sorted":\n                return False',
    ),
    Mutation(
        "M105",
        "j2p/emit/python.py",
        "only the order-defined Collectors are accepted",
        '        if collector.owner != "Collectors" or collector.name not in _COLLECTORS:',
        "        if False:",
    ),
    Mutation(
        "M106",
        "j2p/emit/python.py",
        "collect() refuses a hand-written Collector",
        "        if len(expr.args) != 1 or not isinstance(expr.args[0], StaticCall):",
        "        if False:",
    ),
    # ---- collections: runtime semantics -----------------------------------
    Mutation(
        "M107",
        "runtime/j2p_runtime.py",
        "map keys compare by Java's type-sensitive equality, not Python's",
        "        if self._kind != other._kind:\n            return False",
        "        if False:\n            return False",
    ),
    Mutation(
        "M108",
        "runtime/j2p_runtime.py",
        "Map.of rejects a duplicate key",
        "                    if _JKey(key) in self._data:\n                        raise IllegalArgumentExceptionJ(f\"duplicate key: {jstr(key)}\")",
        "                    pass",
    ),
    Mutation(
        "M109",
        "runtime/j2p_runtime.py",
        "Map.of rejects null keys and values",
        "                    if key is None or value is None:\n                        raise NullPointerExceptionJ(None)",
        "                    pass",
    ),
    Mutation(
        "M110",
        "runtime/j2p_runtime.py",
        "an immutable map refuses to be mutated",
        "    def _check_mutable(self) -> None:\n        if self._immutable:\n            raise UnsupportedOperationExceptionJ(None)",
        "    def _check_mutable(self) -> None:\n        return None",
    ),
    Mutation(
        "M111",
        "runtime/j2p_runtime.py",
        "Map.equals compares entry sets, not order",
        "        for key, value in self._data.items():\n            if key not in other._data:\n                return False",
        "        if list(self._data) != list(other._data):\n            return False\n        for key, value in self._data.items():\n            if key not in other._data:\n                return False",
    ),
    Mutation(
        "M112",
        "runtime/j2p_runtime.py",
        "a TreeMap iterates in key order",
        "        keys = list(self._data)\n        if self._sorted:\n            keys.sort(key=lambda k: _sort_key(k.value))\n        return keys",
        "        return list(self._data)",
    ),
    Mutation(
        "M113",
        "runtime/j2p_runtime.py",
        "Stream.anyMatch short-circuits at the first match",
        "    def anyMatch(self, predicate) -> bool:\n        for value in self._items:\n            if predicate(value):\n                return True\n        return False",
        "    def anyMatch(self, predicate) -> bool:\n        return any([predicate(v) for v in self._items])",
    ),
    Mutation(
        "M114",
        "runtime/j2p_runtime.py",
        "Stream.distinct keeps the first occurrence of each element",
        "        seen: dict = {}\n        for value in self._items:\n            seen.setdefault(_JKey(value), value)\n        return JStream(list(seen.values()))",
        "        return JStream(sorted(set(self._items), key=str))",
    ),
    Mutation(
        "M115",
        "runtime/j2p_runtime.py",
        "Stream.sum wraps at 32 bits like Java's IntStream",
        "        return jint(total)",
        "        return total",
    ),
    Mutation(
        "M116",
        "runtime/j2p_runtime.py",
        "Optional.get on an empty Optional throws",
        '        if not self._present:\n            raise NoSuchElementExceptionJ("No value present")\n        return self._value',
        "        return self._value",
    ),
    Mutation(
        "M117",
        "runtime/j2p_runtime.py",
        "Optional.of rejects null",
        "        if value is None:\n            raise NullPointerExceptionJ(None)\n        return JOptional(value, True)",
        "        return JOptional(value, True)",
    ),
    Mutation(
        "M118",
        "j2p/frontend/java.py",
        "the stream element type flows through the chain so lambdas stay typed",
        "        if not isinstance(t, ClassType) or t.name not in (\"Stream\", \"Optional\"):\n            return None",
        "        return None",
    ),
    # ---- overloaded constructors -----------------------------------------
    Mutation(
        "M94",
        "j2p/emit/python.py",
        "two constructors of the same arity are refused",
        "        if duplicated:\n            raise EmitError(",
        "        if False:\n            raise EmitError(",
    ),
    Mutation(
        "M95",
        "j2p/emit/python.py",
        "an overloaded varargs constructor is refused",
        "        if varargs:\n            raise EmitError(",
        "        if False:\n            raise EmitError(",
    ),
    Mutation(
        "M96",
        "j2p/emit/python.py",
        "field initialisers run before the constructor dispatch",
        '        self._write(1, "def __init__(self, *_args):", decl.origin)\n        for f in decl.fields:',
        '        self._write(1, "def __init__(self, *_args):", decl.origin)\n        for f in []:',
    ),
    Mutation(
        "M97",
        "j2p/frontend/java.py",
        "a multi-dimensional array type is refused, not flattened to one dimension",
        '            if dimensions is not None and self._text(dimensions).count("[") > 1:',
        "            if False:",
    ),
    # ---- enums -----------------------------------------------------------
    Mutation(
        "M88",
        "j2p/emit/python.py",
        "an enum constant is a named singleton, not its ordinal",
        'f"{constant} = {RUNTIME_ALIAS}.JEnum("\n                    f"{decl.name!r}, {constant!r}, {index})"',
        'f"{constant} = {index}"',
    ),
    Mutation(
        "M89",
        "j2p/emit/python.py",
        "two enum constants compare by identity instead of being refused",
        "        if self._is_enum_type(expr.left.type) and self._is_enum_type(expr.right.type):",
        "        if False:",
    ),
    Mutation(
        "M90",
        "j2p/emit/python.py",
        "name/ordinal/toString dispatch to the runtime enum",
        '        if info.kind == "enum" and expr.name in _ENUM_METHODS:',
        "        if False:",
    ),
    Mutation(
        "M91",
        "j2p/frontend/java.py",
        "an enum's inherited members have their java.lang.Enum result types",
        "            if name in enum_members and self._is_enum(target.name):",
        "            if False:",
    ),
    Mutation(
        "M92",
        "runtime/j2p_runtime.py",
        "an enum constant prints its name",
        "    def toString(self) -> str:\n        return self._name",
        "    def toString(self) -> str:\n        return str(self._ordinal)",
    ),
    Mutation(
        "M93",
        "j2p/frontend/java.py",
        "a call on a class name resolves as a static call, not on an instance",
        "                or self._is_program_type(obj_text)\n            ):",
        "                or False\n            ):",
    ),
    # ---- IR --------------------------------------------------------------
    # ---- lambdas ---------------------------------------------------------
    Mutation(
        "M33",
        "j2p/emit/python.py",
        "captured locals are bound by value, not by closure reference",
        '        signature = ", ".join(params + [f"{name}={name}" for name in captures])',
        '        signature = ", ".join(params)',
    ),
    Mutation(
        "M34",
        "j2p/emit/python.py",
        "a lambda parameter is not treated as a capture",
        "        return sorted(used - self._bound_names(body) - {p.name for p in params})",
        "        return sorted(used - self._bound_names(body))",
    ),
    Mutation(
        "M35",
        "j2p/emit/python.py",
        "locals declared inside a lambda body are not captured",
        "        used = {n.ident for n in uir.walk(body) if isinstance(n, Name)}\n        return sorted(used - self._bound_names(body) - {p.name for p in params})",
        "        used = {n.ident for n in uir.walk(body) if isinstance(n, Name)}\n        return sorted(used - {p.name for p in params})",
    ),
    Mutation(
        "M36",
        "j2p/emit/python.py",
        "== between two reference types is refused",
        "        if left_ref and right_ref:\n            raise EmitError(",
        "        if False:\n            raise EmitError(",
    ),
    Mutation(
        "M37",
        "j2p/emit/python.py",
        "only the single abstract method may be called on a lambda value",
        '            if expr.name != sam:\n                raise EmitError(',
        '            if False:\n                raise EmitError(',
    ),
    Mutation(
        "M38",
        "j2p/frontend/java.py",
        "a lambda's result takes the conversion its interface declares",
        '        sam = self._sam_name(expected) if expected is not None else None',
        '        sam = None',
    ),
    Mutation(
        "M39",
        "j2p/frontend/java.py",
        "lambda parameter types come from the target functional interface",
        "        params = self._infer_lambda_param_types(params, expected)",
        "        params = params",
    ),
    Mutation(
        "M31",
        "j2p/uir.py",
        "dict keys are ordered before serialization",
        "        return {str(k): to_canonical(v) for k, v in sorted(node.items())}",
        "        return {str(k): to_canonical(v) for k, v in node.items()}",
    ),
    Mutation(
        "M32",
        "j2p/uir.py",
        "floats are refused in the canonical form",
        "    if isinstance(node, float):\n        raise UirError(\n            \"float is not permitted in canonical UIR; use FloatLiteral.text\"\n        )",
        "    if isinstance(node, float):\n        return node",
    ),
]


def _run_suite(workdir: Path, timeout: float) -> tuple[bool, str]:
    env = {**os.environ, "J2P_FAST": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        # A mutant that hangs the suite is still a mutant the suite noticed.
        return False, "timeout"
    return proc.returncode == 0, (proc.stderr or proc.stdout)[-400:]


def _materialize(workdir: Path) -> None:
    for item in ("j2p", "runtime", "tests", "corpus"):
        src = ROOT / item
        dst = workdir / item
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="run just these mutation ids")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)

    selected = [
        m for m in MUTATIONS if not args.only or m.id in set(args.only)
    ]
    if not selected:
        print("no mutations selected", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="j2p-mutation-") as tmp:
        base = Path(tmp) / "baseline"
        base.mkdir()
        _materialize(base)
        ok, detail = _run_suite(base, args.timeout)
        if not ok:
            print("BASELINE FAILED — fix the suite before running mutations")
            print(detail)
            return 2
        print(f"baseline: {len(selected)} mutations to apply, suite green\n")

        results = []
        survivors = []
        for mutation in selected:
            work = Path(tmp) / mutation.id
            work.mkdir()
            _materialize(work)
            target = work / mutation.file
            text = target.read_text(encoding="utf-8")
            if mutation.old not in text:
                print(f"{mutation.id}  ERROR   anchor not found in {mutation.file}")
                results.append(
                    {
                        "id": mutation.id,
                        "rule": mutation.rule,
                        "status": "ANCHOR_NOT_FOUND",
                    }
                )
                survivors.append(mutation.id)
                shutil.rmtree(work)
                continue
            target.write_text(
                text.replace(mutation.old, mutation.new, 1), encoding="utf-8"
            )

            passed, detail = _run_suite(work, args.timeout)
            killed = not passed
            status = "KILLED" if killed else "SURVIVED"
            print(f"{mutation.id}  {status:9} {mutation.rule}")
            if not killed:
                survivors.append(mutation.id)
            results.append(
                {
                    "id": mutation.id,
                    "file": mutation.file,
                    "rule": mutation.rule,
                    "status": status,
                }
            )
            shutil.rmtree(work)

    killed_count = sum(1 for r in results if r["status"] == "KILLED")
    print(f"\n{killed_count}/{len(results)} mutants killed")
    if survivors:
        print("SURVIVORS (each is an untested or ineffective rule): " + ", ".join(survivors))

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "total": len(results),
                    "killed": killed_count,
                    "survivors": survivors,
                    "results": results,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0 if not survivors else 1


if __name__ == "__main__":
    raise SystemExit(main())
