#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_dirty(repo: Path) -> bool:
    if not (repo / ".git").exists():
        return False
    proc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git status failed: {proc.stderr.strip()}")
    return bool(proc.stdout.strip())


def selected_priorities(profile: str) -> set[str]:
    return {
        "p0": {"P0"},
        "p0p1": {"P0", "P1"},
        "all": {"P0", "P1", "P2"},
    }[profile]


def append_tree(plan: list[tuple[Path, Path]], package: Path, repo: Path, source_root: Path, target_root: Path) -> None:
    if not source_root.exists():
        return
    for src in sorted(source_root.rglob("*")):
        if src.is_file():
            plan.append((src, target_root / src.relative_to(source_root)))


def copy_plan(package: Path, repo: Path, host: str, profile: str) -> list[tuple[Path, Path]]:
    plan: list[tuple[Path, Path]] = []
    extension = repo / ".elmos/extensions" / package.name

    # Codex Skills require the package catalog, docs and selected atomic contracts,
    # so the read-only extension payload is installed for every host mode.
    core_dirs = [
        "catalog", "contracts", "docs", "adapters", "golden-routes", "workflows",
        "policies", "migrations", "templates", "reference", "evals", "fixtures",
        "implementation",
    ]
    core_files = [
        "README.md", "README_CN.md", "AGENTS.md", "PLANS.md", "SECURITY.md",
        "CHANGELOG.md", "PACKAGE_MANIFEST.json", "BUILD_REPORT.md",
    ]
    for rel in core_files:
        src = package / rel
        if src.exists():
            plan.append((src, extension / rel))
    for rel in core_dirs:
        append_tree(plan, package, repo, package / rel, extension / rel)

    priorities = selected_priorities(profile)
    for manifest in sorted((package / "skills/atomic").rglob("manifest.yaml")):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        if data["spec"]["priority"] not in priorities:
            continue
        source_dir = manifest.parent
        target_dir = extension / source_dir.relative_to(package)
        for src in sorted(source_dir.iterdir()):
            if src.is_file():
                plan.append((src, target_dir / src.name))

    if host in {"codex", "both"}:
        append_tree(plan, package, repo, package / ".agents/skills", repo / ".agents/skills")
        append_tree(plan, package, repo, package / ".codex/agents", repo / ".codex/agents")

    # Stable unique destinations; a duplicate destination is allowed only when source bytes match.
    unique: dict[str, tuple[Path, Path]] = {}
    for src, dst in plan:
        key = dst.relative_to(repo).as_posix()
        if key in unique and sha(unique[key][0]) != sha(src):
            raise RuntimeError(f"copy plan has conflicting sources for {key}")
        unique[key] = (src, dst)
    return [unique[k] for k in sorted(unique)]


def preflight(plan: Iterable[tuple[Path, Path]], repo: Path) -> tuple[list[str], list[dict]]:
    conflicts: list[str] = []
    actions: list[dict] = []
    for src, dst in plan:
        rel = dst.relative_to(repo).as_posix()
        src_hash = sha(src)
        if not dst.exists():
            action = "install"
        elif dst.is_file() and sha(dst) == src_hash:
            action = "unchanged"
        else:
            action = "replace"
            conflicts.append(rel)
        actions.append({"path": rel, "sourceHash": src_hash, "action": action})
    return conflicts, actions


def restore_transaction(repo: Path, entries: list[dict]) -> None:
    for entry in reversed(entries):
        dst = repo / entry["path"]
        if entry.get("action") == "install" and dst.is_file() and sha(dst) == entry["installedHash"]:
            dst.unlink()
        backup = entry.get("backup")
        if backup:
            src = repo / backup
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            elif src.exists():
                shutil.copy2(src, dst)


def atomic_copy(src: Path, dst: Path, nonce: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(f".{dst.name}.elmos-install-{nonce}.tmp")
    if temp.exists():
        temp.unlink()
    shutil.copy2(src, temp)
    os.replace(temp, dst)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--host", choices=["elmos", "codex", "both"], default="both")
    parser.add_argument("--profile", choices=["p0", "p0p1", "all"], default="p0")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow installation into a dirty Git worktree after the caller has accepted that risk.")
    args = parser.parse_args()

    package = Path(__file__).resolve().parents[1]
    repo = Path(args.repo).resolve()
    if not repo.exists() or not repo.is_dir():
        print("target repository does not exist", file=sys.stderr)
        return 2

    try:
        if git_dirty(repo) and not (args.dry_run or args.allow_dirty):
            print(json.dumps({"status": "DIRTY-WORKTREE", "hint": "commit/stash changes or explicitly pass --allow-dirty"}, indent=2))
            return 4
        plan = copy_plan(package, repo, args.host, args.profile)
        conflicts, actions = preflight(plan, repo)
    except Exception as exc:
        print(json.dumps({"status": "PREFLIGHT-FAILED", "error": str(exc)}, indent=2), file=sys.stderr)
        return 5

    if args.dry_run:
        print(json.dumps({
            "status": "DRY-RUN",
            "files": len(actions),
            "conflicts": conflicts,
            "forceRequired": bool(conflicts),
            "actions": actions,
        }, indent=2))
        return 0

    if conflicts and not args.force:
        print(json.dumps({
            "status": "CONFLICT",
            "conflicts": conflicts,
            "hint": "review the dry-run and rerun with --force only from a recoverable Git state",
        }, indent=2))
        return 3

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_root = repo / ".elmos/install-backups" / timestamp
    receipt_dir = repo / ".elmos/install-receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []

    try:
        for src, dst in plan:
            rel = dst.relative_to(repo).as_posix()
            src_hash = sha(src)
            if dst.exists() and dst.is_file() and sha(dst) == src_hash:
                entries.append({"path": rel, "installedHash": src_hash, "action": "unchanged", "backup": None})
                continue

            backup_rel = None
            action = "install"
            if dst.exists():
                action = "replace"
                backup_path = backup_root / rel
                backup_rel = backup_path.relative_to(repo).as_posix()
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if dst.is_dir():
                    shutil.copytree(dst, backup_path)
                    shutil.rmtree(dst)
                else:
                    shutil.copy2(dst, backup_path)
            atomic_copy(src, dst, timestamp)
            entries.append({"path": rel, "installedHash": src_hash, "action": action, "backup": backup_rel})
    except Exception as exc:
        restore_transaction(repo, entries)
        print(json.dumps({"status": "ROLLED-BACK", "error": str(exc), "completedEntries": len(entries)}, indent=2), file=sys.stderr)
        return 6

    package_meta = yaml.safe_load((package / "catalog/package.yaml").read_text(encoding="utf-8"))
    receipt = {
        "package": package.name,
        "packageVersion": package_meta["metadata"]["version"],
        "installedAt": timestamp,
        "host": args.host,
        "profile": args.profile,
        "entries": entries,
        "dryRun": False,
    }
    receipt_path = receipt_dir / f"{package.name}-{timestamp}.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "INSTALLED", "files": len(entries), "receipt": str(receipt_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
