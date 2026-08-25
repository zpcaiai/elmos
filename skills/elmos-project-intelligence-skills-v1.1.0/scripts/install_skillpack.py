#!/usr/bin/env python3
"""Install selected Elmos skills into a Codex and/or Claude Code repository."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required. Run: python3 -m pip install -r scripts/requirements.txt") from exc


def parse_frontmatter(skill_file: Path) -> dict:
    text = skill_file.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Missing YAML frontmatter: {skill_file}")
    return yaml.safe_load(parts[1])


def discover_skills(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for directory in sorted((root / "skills").iterdir()):
        if not directory.is_dir() or not (directory / "SKILL.md").is_file():
            continue
        metadata = parse_frontmatter(directory / "SKILL.md")
        name = metadata.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", name):
            raise ValueError(f"Invalid skill name in {directory}: {name!r}")
        if name in result:
            raise ValueError(f"Duplicate skill name: {name}")
        result[name] = directory
    return result


def atomic_copytree(source: Path, destination: Path, force: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise FileExistsError(f"Destination exists: {destination}; review it or pass --force")
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}.install-", dir=destination.parent) as td:
        staging = Path(td) / destination.name
        shutil.copytree(source, staging, symlinks=False)
        if not (staging / "SKILL.md").is_file():
            raise RuntimeError(f"Staged skill is incomplete: {staging}")
        backup = None
        if destination.exists():
            backup = destination.with_name(destination.name + ".backup-install")
            if backup.exists():
                shutil.rmtree(backup)
            destination.rename(backup)
        try:
            staging.rename(destination)
        except Exception:
            if backup and backup.exists() and not destination.exists():
                backup.rename(destination)
            raise
        else:
            if backup and backup.exists():
                shutil.rmtree(backup)


def copy_shared(root: Path, repo: Path, force: bool) -> Path:
    destination = repo / ".elmos" / "skillpacks" / "elmos-project-intelligence"
    include = [
        "README.md", "INSTALL.md", "SKILLS_INDEX.md", "skillpack.yaml", "AGENTS.md", "CLAUDE.md",
        "docs", "batches", "schemas", "contracts", "templates", "examples", "backlog",
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise FileExistsError(f"Shared package already exists: {destination}; pass --force to update")
    with tempfile.TemporaryDirectory(prefix=".elmos-pi-shared-", dir=destination.parent) as td:
        staging = Path(td) / destination.name
        staging.mkdir()
        for rel in include:
            source = root / rel
            target = staging / rel
            if source.is_dir():
                shutil.copytree(source, target)
            elif source.is_file():
                shutil.copy2(source, target)
        backup = None
        if destination.exists():
            backup = destination.with_name(destination.name + ".backup-install")
            if backup.exists():
                shutil.rmtree(backup)
            destination.rename(backup)
        try:
            staging.rename(destination)
        except Exception:
            if backup and backup.exists() and not destination.exists():
                backup.rename(destination)
            raise
        else:
            if backup and backup.exists():
                shutil.rmtree(backup)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path, help="Target Elmos repository")
    parser.add_argument("--target", choices=("codex", "claude", "both"), default="both")
    parser.add_argument("--profile", default="full", help="Profile name from skillpack.yaml")
    parser.add_argument("--force", action="store_true", help="Replace existing same-name skills/shared package")
    parser.add_argument("--no-shared", action="store_true", help="Do not copy docs/batches/contracts into .elmos")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    repo = args.repo.expanduser().resolve()
    if not repo.exists() or not repo.is_dir():
        parser.error(f"Repository directory does not exist: {repo}")

    manifest = yaml.safe_load((root / "skillpack.yaml").read_text(encoding="utf-8"))
    profiles = manifest.get("profiles", {})
    if args.profile not in profiles:
        parser.error(f"Unknown profile {args.profile!r}; choose one of: {', '.join(sorted(profiles))}")

    available = discover_skills(root)
    requested = profiles[args.profile]
    missing = [name for name in requested if name not in available]
    if missing:
        raise SystemExit(f"Manifest references missing skills: {missing}")

    target_roots: list[tuple[str, Path]] = []
    if args.target in ("codex", "both"):
        target_roots.append(("codex", repo / manifest["install_targets"]["codex_repo"]))
    if args.target in ("claude", "both"):
        target_roots.append(("claude", repo / manifest["install_targets"]["claude_repo"]))

    operations = []
    for host, base in target_roots:
        for name in requested:
            operations.append((host, available[name], base / name))

    print(json.dumps({
        "repo": str(repo),
        "target": args.target,
        "profile": args.profile,
        "skill_count": len(requested),
        "operations": [{"host": h, "source": str(s), "destination": str(d)} for h, s, d in operations],
    }, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    completed = []
    try:
        for host, source, destination in operations:
            atomic_copytree(source, destination, args.force)
            completed.append(destination)
        shared = None
        if not args.no_shared:
            shared = copy_shared(root, repo, args.force)
    except Exception as exc:
        raise SystemExit(f"Installation failed after {len(completed)} skill copies: {exc}") from exc

    print(f"Installed {len(requested)} skills to {len(target_roots)} host target(s).")
    if shared:
        print(f"Shared specifications: {shared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
