#!/usr/bin/env python3
"""Report whether an optional canonical Skill import package is present.

A normal source checkout intentionally does not contain the canonical import
bundles (see the module docstring of ``tooling/validate_batch97_104_installed``).
Their byte identities live in the tracked installed manifests, so the installed
distribution — not the absent bundle — is what a checkout validates.

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

    manifest = ROOT / arguments.package / arguments.manifest
    if manifest.is_file():
        return 0

    if not arguments.quiet:
        hint = arguments.hint or (
            "skipping source-bundle integrity checks; "
            "the tracked installed distribution is validated separately"
        )
        print(
            f"{MARKER}={arguments.package} "
            f"reason=missing:{manifest.relative_to(ROOT)} {hint}",
            flush=True,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
