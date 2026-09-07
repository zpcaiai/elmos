"""The generated `scripts/` root has no classification, so NOTHING generates.

`workspace.render_workspace` always emits `scripts/projectctl.py` (the
one-command controller; `cli.py` even lists it among the four files an archive
is REQUIRED to contain), and the dotnet target adds `scripts/local_runtime.py`.
`project_graphs._SHARED_ROOT_KINDS` never learned about that root, so
`render_project_structure` -- which `render_workspace` calls on every path --
raises `PROJECT_STRUCTURE_UNCLASSIFIED_ROOT:scripts` for every request.

Two lists that must agree, don't. Same shape as the 08-25 relation gate defect,
and the fail-closed guard is doing its job: it is refusing to describe a
workspace it cannot classify. The bug is the missing entry, not the guard.

Kind is `operations` rather than a new vocabulary entry: the controller is the
operations entry point (`operations/` already carries the performance budget),
and `_STRUCTURE_KINDS` is derived from these values, so inventing a kind would
widen a vocabulary other consumers read.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
PG = "engines/project-synthesis-engine/src/elmos_project_synthesis/project_graphs.py"


def patch(relative: str, old: str, new: str, *, expect: int = 1) -> None:
    path = ROOT / relative
    src = path.read_text(encoding="utf-8")
    found = src.count(old)
    if found != expect:
        raise SystemExit(f"ABORT {relative}: expected {expect} match(es), found {found}")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  patched {relative}")


patch(
    PG,
    '''    "requirements": "requirements",
    "security": "security",
}''',
    '''    "requirements": "requirements",
    # `scripts/projectctl.py` is emitted for every request and is one of the
    # four files `cli.py` requires an archive to contain; `scripts/` was simply
    # never classified, which failed every `render_workspace` closed.
    "scripts": "operations",
    "security": "security",
}''',
)

print("scripts-root classification applied")
