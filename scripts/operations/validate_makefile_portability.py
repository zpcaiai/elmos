#!/usr/bin/env python3
"""Fail closed when a Makefile bakes in a machine-specific absolute tool path.

Every build entry point must resolve its toolchain from PATH or from an
overridable variable. Hard-coding one developer's layout does not fail on that
developer's machine, so the breakage is invisible until somebody else — or CI —
runs the target. That is exactly how `make production-readiness-check` came to
depend on ``/opt/homebrew/bin/uv`` across seventeen included Makefiles while
every CI job stayed green: no job ran those targets through ``make``.

The rule enforced here is narrow on purpose. A machine-specific prefix is
allowed only as the default of an overridable ``VAR ?=`` assignment, because
that form both documents the assumption and lets any other environment replace
it. Using such a path directly in a recipe is rejected.

Run standalone or via ``make makefile-portability-check``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

# Prefixes that only exist on one packaging layout or one person's machine.
MACHINE_SPECIFIC = (
    "/opt/homebrew/",
    "/usr/local/Cellar/",
    "/home/",
    "/Users/",
    "/root/",
)

# `VAR ?= value` — the one form allowed to carry a machine-specific default,
# since any environment can override it without editing the file.
OVERRIDABLE_DEFAULT = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*\?=")


def makefiles() -> list[Path]:
    found = [ROOT / "Makefile"]
    found.extend(sorted(ROOT.glob("Makefile.*")))
    return [path for path in found if path.is_file()]


def offending_lines(path: Path) -> list[tuple[int, str]]:
    offences: list[tuple[int, str]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if not any(prefix in line for prefix in MACHINE_SPECIFIC):
            continue
        if OVERRIDABLE_DEFAULT.match(line):
            continue
        offences.append((number, stripped))
    return offences


def main() -> int:
    failures: list[str] = []
    checked = makefiles()
    for path in checked:
        for number, text in offending_lines(path):
            failures.append(f"{path.relative_to(ROOT)}:{number}: {text}")

    if failures:
        print(
            "FAIL: machine-specific absolute paths must be overridable `VAR ?=` "
            "defaults, never used directly in a recipe:",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"PASS: {len(checked)} Makefiles resolve their toolchains portably")
    return 0


if __name__ == "__main__":
    sys.exit(main())
