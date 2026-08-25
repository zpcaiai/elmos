#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def install(source: Path, destination: Path, overwrite: bool) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for skill_dir in sorted(path for path in source.iterdir() if path.is_dir()):
        target = destination / skill_dir.name
        if target.exists():
            if not overwrite:
                raise SystemExit(
                    f"Refusing to overwrite existing skill: {target}. "
                    "Use --overwrite explicitly."
                )
            shutil.rmtree(target)
        shutil.copytree(skill_dir, target)
        print(f"installed {skill_dir.name} -> {target}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install ELMOS cache/staging/SOTA/parity skills for Codex or Claude Code"
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--codex", action="store_true")
    target.add_argument("--claude", action="store_true")
    target.add_argument("--all", action="store_true")
    target.add_argument("--dest", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    source = root / "agent-skills/runtime"
    destinations: list[Path] = []

    if args.codex or args.all:
        destinations.append(Path.home() / ".codex/skills")
    if args.claude or args.all:
        destinations.append(Path.home() / ".claude/skills")
    if args.dest is not None:
        destinations.append(args.dest.expanduser().resolve())

    for destination in destinations:
        install(source, destination, args.overwrite)


if __name__ == "__main__":
    main()
