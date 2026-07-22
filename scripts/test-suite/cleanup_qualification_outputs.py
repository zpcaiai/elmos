#!/usr/bin/env python3
"""Remove only allowlisted, reproducible build outputs after qualification stages."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def target_directories(root: Path, group: str) -> list[Path]:
    if group == "all":
        return sorted(
            {
                path
                for scoped_group in ("java", "dotnet", "frontend", "web")
                for path in target_directories(root, scoped_group)
            }
        )
    if group == "java":
        return sorted(
            path
            for path in root.rglob("target")
            if path.is_dir()
            and not any(part in {".git", "artifacts", "node_modules"} for part in path.parts)
        )
    if group == "dotnet":
        engine = root / "engines/dotnet-engine"
        return sorted(
            path
            for path in engine.rglob("*")
            if path.is_dir() and path.name in {"bin", "obj", "TestResults"}
        )
    if group == "frontend":
        return [root / "engines/frontend-client-engine/node_modules"]
    if group == "web":
        return [root / "apps/web-console/node_modules", root / "apps/web-console/.next"]
    raise ValueError(f"unsupported cleanup group: {group}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=("all", "java", "dotnet", "frontend", "web"))
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "pom.xml").is_file():
        raise SystemExit(f"refusing cleanup outside an ELMOS repository: {root}")

    removed = 0
    freed = 0
    for candidate in target_directories(root, args.group):
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SystemExit(f"refusing path outside repository: {path}") from exc
        if not path.is_dir():
            continue
        freed += directory_bytes(path)
        removed += 1
        if not args.dry_run:
            shutil.rmtree(path)
    print(f"cleanup_group={args.group} directories={removed} bytes={freed} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
