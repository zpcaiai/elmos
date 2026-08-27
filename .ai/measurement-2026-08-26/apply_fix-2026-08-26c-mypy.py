"""Rename a shadowed local so `python_analyzer.py` passes mypy --strict again.

The 2026-08-26 analyzer pass introduced three strict-mode errors, all from one
mistake: `folded` is used twice in `_expression`. First for the signed-literal
fold (`ast.Constant | None`), then again as the accumulator of the boolean
left fold (`dict[str, Any]`). mypy takes the first assignment as the
variable's declared type and every later `dict` assignment conflicts with it.

Python does not care; the repository's mypy-strict gate does, and it is right
to -- two different things sharing a name inside one function is exactly the
kind of thing that reads fine and then confuses the next reader.

`models.py:698 unused-ignore` is NOT from this pass: it is present in the
untouched baseline and is left alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
PA = "engines/polyglot-route-engine/src/elmos_polyglot_route/python_analyzer.py"

path = ROOT / PA
src = path.read_text(encoding="utf-8")

old = '''        operator = "&&" if isinstance(node.op, ast.And) else "||"
        folded = _expression(node.values[0], emitted_target=emitted_target)
        for value in node.values[1:]:
            folded = {
                "kind": "binary",
                "operator": operator,
                "left": folded,
                "right": _expression(value, emitted_target=emitted_target),
            }
        return folded'''
new = '''        operator = "&&" if isinstance(node.op, ast.And) else "||"
        # NOT named `folded`: that name already holds the signed-literal fold
        # at the top of this function, and reusing it makes mypy read the two
        # as one variable of two incompatible types.
        chain = _expression(node.values[0], emitted_target=emitted_target)
        for value in node.values[1:]:
            chain = {
                "kind": "binary",
                "operator": operator,
                "left": chain,
                "right": _expression(value, emitted_target=emitted_target),
            }
        return chain'''

found = src.count(old)
if found != 1:
    raise SystemExit(f"ABORT {PA}: expected 1 match, found {found}")
path.write_text(src.replace(old, new, 1), encoding="utf-8")
print("  patched", PA)
print("mypy shadowing fix applied")
