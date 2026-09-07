#!/usr/bin/env python3
"""Remove only Elmos pricing/billing skills recorded by the installer."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HOST_DIRS = {"codex": Path(".agents/skills"), "claude": Path(".claude/skills")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--yes", action="store_true", help="Required for destructive removal")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target = args.target.resolve()
    kit = target / ".elmos-billing-kit"
    manifest_path = kit / "install-manifest.json"
    if not manifest_path.exists():
        print("No installer manifest found; refusing to guess installed paths.", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not args.yes and not args.dry_run:
        print("Use --yes after reviewing the dry run.", file=sys.stderr)
        return 3

    paths: list[Path] = []
    for host in manifest.get("hosts", []):
        for skill in manifest.get("skills", []):
            paths.append(target / HOST_DIRS[host] / skill)
    paths.append(kit)

    for path in paths:
        if args.dry_run:
            print(f"REMOVE {path}")
        elif path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    print("Uninstall complete" if not args.dry_run else "Dry run complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
