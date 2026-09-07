#!/usr/bin/env python3
"""Versioned compatibility entrypoint for Batch 29 route metadata.

The historical command owned a four-language/12-direction contract.  It may
still verify that immutable contract read-only, but it cannot silently reinterpret
it as the active 13-language/156-direction matrix.  Active synchronization is a
separate, explicit operation delegated to the one authoritative generator.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_ROUTES_ROOT = (REPOSITORY_ROOT / "routes").resolve(strict=True)
LEGACY_LANGUAGES = ("java", "csharp", "python", "typescript")
LEGACY_ROUTE_KEYS = tuple(
    f"{source}-to-{target}"
    for source in LEGACY_LANGUAGES
    for target in LEGACY_LANGUAGES
    if source != target
)


def _canonical_routes_root(value: Path) -> Path:
    try:
        resolved = value.expanduser().resolve(strict=True)
    except OSError as error:
        raise ValueError(f"ROUTES_ROOT_INVALID:{value}") from error
    if resolved != CANONICAL_ROUTES_ROOT:
        raise ValueError(f"ROUTES_ROOT_NOT_CANONICAL:{resolved}")
    return resolved


def verify_legacy_twelve(routes_root: Path) -> None:
    inventory = json.loads((routes_root / "inventory.json").read_text(encoding="utf-8"))
    inventory_routes = {
        entry.get("route_key"): entry
        for entry in inventory.get("routes", [])
        if isinstance(entry, dict)
    }
    for route_key in LEGACY_ROUTE_KEYS:
        route_root = routes_root / route_key
        manifest = json.loads((route_root / "route.json").read_text(encoding="utf-8"))
        source, target = route_key.split("-to-", 1)
        if (
            manifest.get("route_key") != route_key
            or manifest.get("source", {}).get("language") != source
            or manifest.get("target", {}).get("language") != target
            or manifest.get("status") not in {"limited", "certified"}
            or route_key not in inventory_routes
        ):
            raise ValueError(f"LEGACY_12_ROUTE_CONTRACT_DRIFT:{route_key}")
    print("VERIFIED_READ_ONLY: legacy four-language/12-direction contract")


def main() -> int:
    parser = argparse.ArgumentParser()
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--verify-legacy-12", action="store_true")
    operation.add_argument("--synchronize-active-156", action="store_true")
    parser.add_argument("--routes-root", type=Path, default=CANONICAL_ROUTES_ROOT)
    args = parser.parse_args()
    routes_root = _canonical_routes_root(args.routes_root)
    if args.verify_legacy_12:
        verify_legacy_twelve(routes_root)
        return 0
    generator = REPOSITORY_ROOT / "scripts" / "batch29" / "run_polyglot_routes.py"
    if generator.is_symlink() or not generator.is_file():
        raise ValueError(f"POLYGLOT_ROUTE_GENERATOR_MISSING:{generator}")
    completed = subprocess.run(
        [
            sys.executable,
            str(generator),
            "--repo-root",
            str(REPOSITORY_ROOT),
            "--inventory-only",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
