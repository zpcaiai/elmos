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
