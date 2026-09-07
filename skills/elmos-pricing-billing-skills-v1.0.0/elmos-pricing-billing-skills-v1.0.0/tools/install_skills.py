#!/usr/bin/env python3
"""Install Elmos billing skills into Codex and/or Claude Code project paths."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HOST_DIRS = {
    "codex": Path(".agents/skills"),
    "claude": Path(".claude/skills"),
}
SHARED_DIRS = ["docs", "schemas", "policies", "manifests", "tests", "templates", "examples", "tools"]
SHARED_FILES = [
    "README.md", "SKILL_INDEX.md", "BATCH_INDEX.md", "IMPLEMENTATION_CHECKLIST.md",
    "CODEX_IMPLEMENTATION_PROMPT.md", "CLAUDE_CODE_IMPLEMENTATION_PROMPT.md",
    "PACKAGE_MANIFEST.json", "VALIDATION_REPORT.md", "VERSION"
]


def copy_atomic(src: Path, dst: Path, force: bool, dry_run: bool) -> None:
    if dst.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {dst}; use --force")
    if dry_run:
        print(f"COPY {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="elmos-billing-install-", dir=str(dst.parent)) as tmp:
        staged = Path(tmp) / dst.name
        if src.is_dir():
            shutil.copytree(src, staged)
        else:
            shutil.copy2(src, staged)
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        staged.replace(dst)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=Path.cwd(), help="Target repository root")
    parser.add_argument("--host", choices=["codex", "claude", "both"], default="both")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    package_root = Path(__file__).resolve().parents[1]
    target = args.target.resolve()
    if not target.exists() or not target.is_dir():
        print(f"Target directory does not exist: {target}", file=sys.stderr)
        return 2

    hosts = ["codex", "claude"] if args.host == "both" else [args.host]
    skill_names = sorted(p.name for p in (package_root / "skills").iterdir() if (p / "SKILL.md").exists())
    destinations: list[tuple[Path, Path]] = []
    for host in hosts:
        for name in skill_names:
            destinations.append((package_root / "skills" / name, target / HOST_DIRS[host] / name))

    shared_dst = target / ".elmos-billing-kit"
    destinations.append((package_root, shared_dst))

    conflicts = [dst for _, dst in destinations if dst.exists()]
    if conflicts and not args.force:
        print("Conflicts detected; nothing installed:", file=sys.stderr)
        for item in conflicts:
            print(f"  - {item}", file=sys.stderr)
        print("Re-run with --force only after reviewing existing files.", file=sys.stderr)
        return 3

    # Skills first after full preflight.
    for host in hosts:
        for name in skill_names:
            copy_atomic(package_root / "skills" / name, target / HOST_DIRS[host] / name, args.force, args.dry_run)

    if args.dry_run:
        print(f"BUILD shared kit -> {shared_dst}")
    else:
        if shared_dst.exists():
            shutil.rmtree(shared_dst)
        shared_dst.mkdir(parents=True)
        for directory in SHARED_DIRS:
            src = package_root / directory
            if src.exists():
                shutil.copytree(src, shared_dst / directory)
        for filename in SHARED_FILES:
            src = package_root / filename
            if src.exists():
                shutil.copy2(src, shared_dst / filename)
        install_manifest = {
            "package": "elmos-pricing-billing-skills",
            "version": (package_root / "VERSION").read_text(encoding="utf-8").strip(),
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "target": str(target),
            "hosts": hosts,
            "skills": skill_names,
        }
        (shared_dst / "install-manifest.json").write_text(json.dumps(install_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Installed {len(skill_names)} skills for {', '.join(hosts)} into {target}")
    print("Shared implementation kit: .elmos-billing-kit/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
