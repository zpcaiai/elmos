#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from common import load_manifest, package_root, sha256_file

MARKER = ".elmos-skill-install.json"


def runtime_roots(project: Path, runtime: str) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    if runtime in {"codex", "both"}:
        roots["codex"] = project / ".agents" / "skills"
    if runtime in {"claude", "both"}:
        roots["claude"] = project / ".claude" / "skills"
    return roots


def skill_fingerprint(skill_dir: Path) -> str:
    return sha256_file(skill_dir / "SKILL.md")


def install(project: Path, runtime: str, force: bool, dry_run: bool) -> dict:
    root = package_root()
    manifest = load_manifest(root)
    project = project.resolve()
    if not project.exists() or not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = project / ".elmos" / "skills-backups" / timestamp
    actions: list[dict] = []
    errors: list[str] = []

    for runtime_name, target_root in runtime_roots(project, runtime).items():
        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)
        for item in manifest["skills"]:
            source = root / item["path"]
            target = target_root / item["name"]
            in_place = False
            try:
                in_place = source.resolve() == target.resolve()
            except FileNotFoundError:
                pass

            if in_place:
                actions.append({"runtime": runtime_name, "skill": item["name"], "action": "in-place", "path": str(target)})
                continue

            if target.exists() or target.is_symlink():
                marker_path = target / MARKER if target.is_dir() and not target.is_symlink() else None
                owned = False
                if marker_path and marker_path.exists():
                    try:
                        marker = json.loads(marker_path.read_text(encoding="utf-8"))
                        owned = marker.get("package_id") == manifest["package"]["id"]
                    except Exception:
                        owned = False
                if not owned and not force:
                    errors.append(
                        f"{runtime_name}:{item['name']} already exists and is not owned by this package; use --force to back it up"
                    )
                    continue
                if not dry_run:
                    backup = backup_root / runtime_name / item["name"]
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(target), str(backup))
                    actions.append({"runtime": runtime_name, "skill": item["name"], "action": "backup", "path": str(backup)})

            if not dry_run:
                shutil.copytree(source, target)
                marker = {
                    "package_id": manifest["package"]["id"],
                    "package_version": manifest["package"]["version"],
                    "runtime": runtime_name,
                    "skill": item["name"],
                    "source_fingerprint": skill_fingerprint(source),
                    "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
                (target / MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            actions.append({"runtime": runtime_name, "skill": item["name"], "action": "install", "path": str(target)})

    if errors:
        return {"ok": False, "errors": errors, "actions": actions}

    install_record = {
        "package_id": manifest["package"]["id"],
        "package_version": manifest["package"]["version"],
        "runtime": runtime,
        "project": str(project),
        "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "skills": [s["name"] for s in manifest["skills"]],
        "actions": actions,
    }
    record_path = project / ".elmos" / "skills-installations" / f"{manifest['package']['name']}.json"
    if not dry_run:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(install_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "errors": [], "actions": actions, "record": str(record_path)}


def uninstall(project: Path, runtime: str, dry_run: bool) -> dict:
    root = package_root()
    manifest = load_manifest(root)
    project = project.resolve()
    actions: list[dict] = []
    errors: list[str] = []

    for runtime_name, target_root in runtime_roots(project, runtime).items():
        for item in manifest["skills"]:
            target = target_root / item["name"]
            if not target.exists() and not target.is_symlink():
                continue
            try:
                if (root / item["path"]).resolve() == target.resolve():
                    actions.append({"runtime": runtime_name, "skill": item["name"], "action": "skip-in-place", "path": str(target)})
                    continue
            except FileNotFoundError:
                pass

            marker_path = target / MARKER if target.is_dir() and not target.is_symlink() else None
            if not marker_path or not marker_path.exists():
                errors.append(f"{runtime_name}:{item['name']} has no package marker; left unchanged")
                continue
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except Exception:
                errors.append(f"{runtime_name}:{item['name']} has invalid marker; left unchanged")
                continue
            if marker.get("package_id") != manifest["package"]["id"]:
                errors.append(f"{runtime_name}:{item['name']} belongs to another package; left unchanged")
                continue

            if not dry_run:
                if target.is_symlink() or target.is_file():
                    target.unlink()
                else:
                    shutil.rmtree(target)
            actions.append({"runtime": runtime_name, "skill": item["name"], "action": "remove", "path": str(target)})

    record_path = project / ".elmos" / "skills-installations" / f"{manifest['package']['name']}.json"
    if record_path.exists() and not dry_run:
        record_path.unlink()
    return {"ok": not errors, "errors": errors, "actions": actions}


def status(project: Path, runtime: str) -> dict:
    root = package_root()
    manifest = load_manifest(root)
    project = project.resolve()
    rows: list[dict] = []
    for runtime_name, target_root in runtime_roots(project, runtime).items():
        for item in manifest["skills"]:
            target = target_root / item["name"]
            state = "missing"
            owned = False
            if target.exists():
                state = "present"
                marker_path = target / MARKER
                if marker_path.exists():
                    try:
                        marker = json.loads(marker_path.read_text(encoding="utf-8"))
                        owned = marker.get("package_id") == manifest["package"]["id"]
                    except Exception:
                        pass
            rows.append({"runtime": runtime_name, "skill": item["name"], "state": state, "owned": owned, "path": str(target)})
    return {"ok": True, "skills": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or uninstall Elmos miniapp skills")
    sub = parser.add_subparsers(dest="command", required=True)

    for command in ["install", "uninstall", "status"]:
        p = sub.add_parser(command)
        p.add_argument("--project", type=Path, required=True)
        p.add_argument("--runtime", choices=["codex", "claude", "both"], default="both")
        if command == "install":
            p.add_argument("--force", action="store_true")
        if command in {"install", "uninstall"}:
            p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "install":
            result = install(args.project, args.runtime, args.force, args.dry_run)
        elif args.command == "uninstall":
            result = uninstall(args.project, args.runtime, args.dry_run)
        else:
            result = status(args.project, args.runtime)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
