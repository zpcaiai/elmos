#!/usr/bin/env python3
"""Install a validated combined ELMOS Skill pack with collision preflight."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SAFE_EDITIONS = {
    "repository-contract",
    "complete-source-contract",
    "approved-conversation-design",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path, help="explicit Codex Skills directory")
    parser.add_argument("--pack", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--include-non-authoritative", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pack = args.pack.resolve()
    target = args.target.resolve()
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    selected = [
        record
        for record in manifest["skills"]
        if args.include_non_authoritative or record["editionStatus"] in SAFE_EDITIONS
    ]
    collisions = sorted(record["name"] for record in selected if (target / record["name"]).exists())
    if collisions and not args.overwrite:
        raise SystemExit(
            f"Refusing partial install; {len(collisions)} destinations already exist. "
            "Review collisions or pass --overwrite for recoverable backups."
        )
    if args.dry_run:
        print(json.dumps({"selected": len(selected), "collisions": collisions}, indent=2))
        return

    target.mkdir(parents=True, exist_ok=True)
    backup_root = target / ".elmos-skill-backups" / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    if collisions:
        backup_root.mkdir(parents=True, exist_ok=False)
        for name in collisions:
            shutil.move(str(target / name), str(backup_root / name))

    installed = 0
    try:
        for record in selected:
            source = pack / Path(record["path"]).parent
            destination = target / record["name"]
            with tempfile.TemporaryDirectory(prefix=f".{record['name']}-", dir=target) as tmp:
                staged = Path(tmp) / record["name"]
                shutil.copytree(source, staged)
                staged.rename(destination)
            installed += 1
    except Exception:
        for name in collisions:
            current = target / name
            if current.exists():
                shutil.rmtree(current)
            backup = backup_root / name
            if backup.exists():
                shutil.move(str(backup), str(current))
        raise

    print(
        json.dumps(
            {
                "installed": installed,
                "non_authoritative_included": args.include_non_authoritative,
                "backups": str(backup_root) if collisions else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
