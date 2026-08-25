#!/usr/bin/env python3
"""Read-only tombstone for the superseded PHP route-pack writer.

This former eleven-language generator cloned route directories and rewrote
``routes/inventory.json`` from a second authority. Keeping even unreachable
writer code here made it too easy to restore a command that silently regressed
the active thirteen-language inventory. Batch 29 route metadata is now owned
only by ``scripts/batch29/run_polyglot_routes.py``.
"""

from __future__ import annotations

import argparse


def generate(write: bool, overwrite: bool) -> int:
    """Refuse every legacy dry-run/write/overwrite invocation."""

    del write, overwrite
    raise RuntimeError(
        "SUPERSEDED_PHP_ROUTE_WRITER_DISABLED:"
        "use_scripts/batch29/run_polyglot_routes.py_--inventory-only"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--overwrite", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    return generate(arguments.write, arguments.overwrite)


if __name__ == "__main__":
    raise SystemExit(main())
