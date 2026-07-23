#!/usr/bin/env python3
"""Install a complete Batch 97-104 Skill subset with recoverable replacement."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any


def load_items(root: Path, batch: int | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("package") != "elmos-codex-skills-batch97-104-complete":
        raise ValueError("unexpected package identity")
    items = [entry for entry in manifest.get("skills", []) if batch is None or entry.get("batch") == batch]
    expected = 128 if batch is None else 16
    if len(items) != expected:
        raise ValueError(f"expected {expected} Skills, found {len(items)}")
    return manifest, items


def install(root: Path, target: Path, batch: int | None, overwrite: bool) -> dict[str, Any]:
    root = root.resolve()
    target.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or not target.is_dir():
        raise ValueError("installation target must be a real directory")
    target = target.resolve()
    manifest, items = load_items(root, batch)
    destinations = [target / entry["name"] for entry in items]
    collisions = [path for path in destinations if path.exists() or path.is_symlink()]
    if collisions and not overwrite:
        rendered = "\n".join(str(path) for path in collisions)
        raise ValueError(
            "destination already exists; review it and use --overwrite for recoverable backup:\n"
            + rendered
        )

    transaction = uuid.uuid4().hex
    stage = target / f".elmos-batch97-104-stage-{transaction}"
    backup = target / ".elmos-backups" / f"batch97-104-{transaction}"
    receipt_path = target / ".elmos-install-receipts" / f"batch97-104-{transaction}.json"
    installed: list[Path] = []
    backed_up: list[tuple[Path, Path]] = []
    try:
        stage.mkdir()
        for entry in items:
            raw_skill_file = root / entry["path"]
            if raw_skill_file.is_symlink():
                raise ValueError(f"Skill source cannot be a symlink: {entry['name']}")
            skill_file = raw_skill_file.resolve()
            skill_file.relative_to(root)
            source = skill_file.parent
            if not skill_file.is_file() or not (source / "agents" / "openai.yaml").is_file():
                raise ValueError(f"Skill source is incomplete: {entry['name']}")
            shutil.copytree(source, stage / entry["name"], symlinks=False)
        if collisions:
            backup.mkdir(parents=True)
            for destination in collisions:
                saved = backup / destination.name
                shutil.move(str(destination), str(saved))
                backed_up.append((destination, saved))
        for entry in items:
            destination = target / entry["name"]
            shutil.move(str(stage / entry["name"]), str(destination))
            installed.append(destination)
        receipt = {
            "schema_version": "elmos.batch97-104-install-receipt.v1",
            "transaction": transaction,
            "package": manifest["package"],
            "package_version": manifest["version"],
            "batch": batch,
            "skill_count": len(items),
            "installed_names": [entry["name"] for entry in items],
            "backup_path": str(backup) if backed_up else None,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    except Exception:
        for destination in reversed(installed):
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            elif destination.exists() or destination.is_symlink():
                destination.unlink()
        for destination, saved in reversed(backed_up):
            if saved.exists() or saved.is_symlink():
                shutil.move(str(saved), str(destination))
        receipt_path.unlink(missing_ok=True)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {
        "installed": len(items),
        "target": str(target),
        "backup": str(backup) if backed_up else None,
        "receipt": str(receipt_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--batch", type=int, choices=range(97, 105))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        result = install(Path(args.root), Path(args.target), args.batch, args.overwrite)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"installation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
