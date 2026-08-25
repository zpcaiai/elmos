#!/usr/bin/env python3
"""Resolve the five conflicts of origin/main -> fix/optional-source-package-guard.

Run from anywhere; pass the worktree path if it is not the default:

    python3 resolve-merge.py [/Users/stephen/DevProjects/AIProjects/elmos-merge]

It resolves each conflict *region* rather than taking whole files, so edits that
merged cleanly on either side survive. It does not stage and does not commit --
read the summary, look at the files, then commit yourself.

Per file, and why:

  OptionalSourcePackage.java   take main. Both sides added this file. main's
                               version validates path traversal, distinguishes a
                               missing bundle (skip) from a partial one (fail),
                               and uses NOFOLLOW_LINKS. Same signature, so the
                               branch's callers are unaffected.

  Makefile.batch29/33/35       take main, then re-apply the branch's whole point.
                               main added `include Makefile.external-gates`, the
                               external-gate-intake-test dependency, and dropped
                               `--with pyyaml` from 33 and 35. The branch replaced
                               the hardcoded /opt/homebrew/bin/uv with $(UV). The
                               two are independent; taking either side alone loses
                               real work. validate_makefile_portability.py is the
                               check for the half re-applied here.

  BUSINESS_LINE_CLOSURE_MATRIX take main for the conflicted row only. Both sides
                               rewrote the M29 row from 12 routes to 30; main's
                               wording says "逐功能" and describes the function
                               reports, which is the vocabulary the rest of main
                               now uses. The branch's other edits to this file are
                               outside the conflict and are kept.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_WORKTREE = Path("/Users/stephen/DevProjects/AIProjects/elmos-merge")

OURS = re.compile(r"^<<<<<<< ")
MID = re.compile(r"^=======\s*$")
THEIRS = re.compile(r"^>>>>>>> ")

TAKE_THEIRS = [
    "modules/architecture-tests/src/test/java/io/elmos/architecture/OptionalSourcePackage.java",
    "Makefile.batch29",
    "Makefile.batch33",
    "Makefile.batch35",
    "docs/BUSINESS_LINE_CLOSURE_MATRIX.md",
]

# Applied after the conflict regions are resolved, to put back the branch's
# portability change that taking main's side above would otherwise drop.
PORTABILITY = ("Makefile.batch29", "Makefile.batch33", "Makefile.batch35")
HARDCODED_UV = "/opt/homebrew/bin/uv"


def resolve_regions(text: str, keep: str) -> tuple[str, int]:
    """Keep one side of every conflict region; leave everything else alone."""
    out: list[str] = []
    state = "clean"
    count = 0
    for line in text.splitlines(keepends=True):
        if state == "clean" and OURS.match(line):
            state, count = "ours", count + 1
            continue
        if state == "ours" and MID.match(line):
            state = "theirs"
            continue
        if state == "theirs" and THEIRS.match(line):
            state = "clean"
            continue
        if state == "clean" or state == keep:
            out.append(line)
    if state != "clean":
        raise SystemExit("unbalanced conflict markers; refusing to guess")
    return "".join(out), count


def apply_portability(text: str, variable: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    if HARDCODED_UV in text:
        text = text.replace(HARDCODED_UV, "$(UV)")
        notes.append(f"{HARDCODED_UV} -> $(UV)")
    if not re.search(r"^UV \?= uv$", text, flags=re.M):
        # Put it immediately above the first use, after any include block.
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.startswith(f"{variable} ?="):
                lines.insert(index, "UV ?= uv\n")
                notes.append("added UV ?= uv")
                break
        else:
            raise SystemExit(f"no {variable} ?= line to anchor UV ?= uv above")
        text = "".join(lines)
    return text, notes


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORKTREE
    if not (root / ".git").exists():
        raise SystemExit(f"{root} is not a git worktree")

    for relative in TAKE_THEIRS:
        path = root / relative
        if not path.exists():
            raise SystemExit(f"missing: {relative}")
        original = path.read_text(encoding="utf-8")
        resolved, regions = resolve_regions(original, keep="theirs")
        notes = [f"{regions} conflict region(s) -> main"]
        name = Path(relative).name
        if name in PORTABILITY:
            variable = f"BATCH{name.removeprefix('Makefile.batch')}_PYTHON"
            resolved, extra = apply_portability(resolved, variable)
            notes.extend(extra)
        path.write_text(resolved, encoding="utf-8")
        print(f"  {relative}\n      {'; '.join(notes)}")

    print("\n== leftover conflict markers ==")
    stragglers = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git/" in str(path):
            continue
        try:
            head = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if OURS.search(head) and THEIRS.search(head):
            stragglers.append(str(path.relative_to(root)))
    print("  none" if not stragglers else "\n".join(f"  {s}" for s in stragglers))

    print("\nNothing was staged and nothing was committed. Read the three")
    print("Makefiles and the matrix row before you do either.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
