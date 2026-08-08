#!/usr/bin/env python3
"""Report whether an optional canonical Skill import package is present.

A normal source checkout intentionally does not contain the canonical import
bundles (see the module docstring of ``tooling/validate_batch97_104_installed``).
Where a tracked installed manifest exists, it validates the installed
distribution; it can never substitute for byte-level validation of an absent
source bundle.

This helper exists so every Makefile target expresses that rule the same way.
It never validates anything itself.  It exits ``0`` when the package is present
and ``1`` when it is absent, and in the absent case prints a single explicit

    SOURCE_PACKAGE_ABSENT=<package> reason=<manifest path> <hint>

line.  The marker is deliberately loud and machine-greppable: an absent source
package must never be readable as a validated one, and a skipped bundle-integrity
check must never be readable as a passed check.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MARKER = "SOURCE_PACKAGE_ABSENT"
INVALID_MARKER = "SOURCE_PACKAGE_INVALID"


def _confined_relative(value: str, *, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise ValueError(f"{label} must be a confined relative path")
    return relative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package",
        help="package directory name relative to the repository root",
    )
    parser.add_argument(
        "--manifest",
        default="manifest.json",
        help="manifest file that must exist inside the package (default: manifest.json)",
    )
    parser.add_argument(
        "--hint",
        default="",
        help="short operator hint appended to the absent marker",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress the marker line and only signal via the exit code",
    )
    arguments = parser.parse_args()

    try:
        package = _confined_relative(arguments.package, label="package")
        manifest_name = _confined_relative(arguments.manifest, label="manifest")
        manifest = (ROOT / package / manifest_name).resolve()
        manifest.relative_to(ROOT.resolve())
    except ValueError as exc:
        if not arguments.quiet:
            print(f"{INVALID_MARKER} reason={exc}", file=sys.stderr, flush=True)
        return 2

    if manifest.is_file():
        return 0

    if not arguments.quiet:
        hint = arguments.hint or (
            "skipping source-bundle integrity checks; "
            "installed distributions are validated separately where tracked"
        )
        print(
            f"{MARKER}={package.as_posix()} "
            f"reason=missing:{manifest.relative_to(ROOT)} {hint}",
            flush=True,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
