#!/usr/bin/env python3
"""Install or uninstall the Elmos Database & Big Data skill pack.

Examples:
  python3 scripts/install_skillpack.py install --target both --profile full
  python3 scripts/install_skillpack.py install --target custom --dest /tmp/skills --profile database
  python3 scripts/install_skillpack.py uninstall --target custom --dest /tmp/skills --profile database

Safety properties:
- profiles expand transitive dependencies;
- all destinations are preflighted before changes;
- conflicts fail by default;
- --force uses sibling temporary/backup directories and rollback;
- uninstall removes only receipt-tracked `elmos-*` skills;
- source symlinks and unsafe skill names are rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Set, Tuple

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PACKAGE_ROOT / "skills"
PROFILES_ROOT = PACKAGE_ROOT / "profiles"
RECEIPT_NAME = ".elmos-database-bigdata-skills.receipt.json"
PACKAGE_NAME = "elmos-database-bigdata-skills"
PACKAGE_VERSION = "1.0.0"
SAFE_SKILL = re.compile(r"^elmos-[a-z0-9][a-z0-9-]*$")


class InstallError(RuntimeError):
    """Expected operational error with a user-actionable message."""


@dataclass
class AppliedChange:
    root: Path
    destination: Path
    backup: Path | None
    created_new: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InstallError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InstallError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError(f"Expected a JSON object in {path}")
    return data


def atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def directory_checksum(path: Path) -> str:
    if not path.is_dir():
        raise InstallError(f"Expected directory for checksum: {path}")
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda p: p.as_posix()):
        if item.is_symlink():
            raise InstallError(f"Symlinks are not allowed in skill directories: {item}")
        if item.is_file():
            rel = item.relative_to(path).as_posix().encode("utf-8")
            digest.update(len(rel).to_bytes(8, "big"))
            digest.update(rel)
            content = item.read_bytes()
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    return digest.hexdigest()


def parse_frontmatter(skill_md: Path) -> Dict[str, Any]:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        raise InstallError(f"Cannot read {skill_md}: {exc}") from exc
    if not text.startswith("---\n"):
        raise InstallError(f"Missing YAML frontmatter in {skill_md}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise InstallError(f"Unterminated YAML frontmatter in {skill_md}")
    result: Dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise InstallError(f"Unsupported frontmatter line in {skill_md}: {line}")
        key, raw = line.split(":", 1)
        key, raw = key.strip(), raw.strip()
        if raw.startswith("["):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise InstallError(f"Frontmatter list must be JSON-compatible in {skill_md}: {line}") from exc
        elif raw in {"true", "false"}:
            value = raw == "true"
        elif raw in {"null", "~"}:
            value = None
        else:
            value = raw.strip('"\'')
        result[key] = value
    return result


def load_skill_graph() -> Dict[str, Dict[str, Any]]:
    if not SKILLS_ROOT.is_dir():
        raise InstallError(f"Skills directory does not exist: {SKILLS_ROOT}")
    graph: Dict[str, Dict[str, Any]] = {}
    for directory in sorted(SKILLS_ROOT.iterdir()):
        if not directory.is_dir():
            continue
        name = directory.name
        if not SAFE_SKILL.fullmatch(name):
            raise InstallError(f"Unsafe skill directory name: {name}")
        meta = parse_frontmatter(directory / "SKILL.md")
        if meta.get("name") != name:
            raise InstallError(f"Frontmatter name mismatch: {directory}")
        dependencies = meta.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(isinstance(x, str) for x in dependencies):
            raise InstallError(f"dependencies must be a string array: {directory / 'SKILL.md'}")
        graph[name] = {"path": directory, "dependencies": dependencies, "checksum": directory_checksum(directory)}
    for name, data in graph.items():
        missing = sorted(set(data["dependencies"]) - set(graph))
        if missing:
            raise InstallError(f"Skill {name} has missing dependencies: {', '.join(missing)}")
    return graph


def expand_dependencies(requested: Iterable[str], graph: Mapping[str, Mapping[str, Any]]) -> List[str]:
    requested_list = list(dict.fromkeys(requested))
    unknown = sorted(set(requested_list) - set(graph))
    if unknown:
        raise InstallError(f"Unknown skills: {', '.join(unknown)}")
    visiting: Set[str] = set()
    visited: Set[str] = set()
    ordered: List[str] = []

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise InstallError(f"Dependency cycle detected at {name}")
        visiting.add(name)
        for dependency in graph[name]["dependencies"]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(name)

    for skill in requested_list:
        visit(skill)
    return ordered


def load_profile(name: str) -> Dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise InstallError(f"Unsafe profile name: {name}")
    data = load_json(PROFILES_ROOT / f"{name}.json")
    if data.get("profile") != name:
        raise InstallError(f"Profile name mismatch in {name}.json")
    skills = data.get("skills")
    if not isinstance(skills, list) or not all(isinstance(x, str) for x in skills):
        raise InstallError(f"Profile {name} must contain a skills string array")
    return data


def target_roots(target: str, destinations: Sequence[Path]) -> List[Path]:
    home = Path.home()
    if target == "codex":
        if destinations:
            raise InstallError("--dest is only valid with --target custom")
        roots = [home / ".codex" / "skills"]
    elif target == "claude":
        if destinations:
            raise InstallError("--dest is only valid with --target custom")
        roots = [home / ".claude" / "skills"]
    elif target == "both":
        if destinations:
            raise InstallError("--dest is only valid with --target custom")
        roots = [home / ".codex" / "skills", home / ".claude" / "skills"]
    elif target == "custom":
        if not destinations:
            raise InstallError("--target custom requires at least one --dest PATH")
        roots = list(destinations)
    else:
        raise InstallError(f"Unsupported target: {target}")
    normalized = []
    seen: Set[str] = set()
    for root in roots:
        resolved = root.expanduser().resolve()
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            normalized.append(resolved)
    return normalized


def empty_receipt(root: Path) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "target_root": str(root),
        "updated_at": utc_now(),
        "profiles": {},
        "skills": {},
    }


def read_receipt(root: Path) -> Dict[str, Any]:
    path = root / RECEIPT_NAME
    if not path.exists():
        return empty_receipt(root)
    data = load_json(path)
    if data.get("package") != PACKAGE_NAME:
        raise InstallError(f"Receipt belongs to another package: {path}")
    if data.get("target_root") not in {None, str(root)}:
        raise InstallError(f"Receipt target mismatch: {path}")
    data.setdefault("profiles", {})
    data.setdefault("skills", {})
    if not isinstance(data["profiles"], dict) or not isinstance(data["skills"], dict):
        raise InstallError(f"Malformed receipt: {path}")
    return data


def validate_child(root: Path, name: str) -> Path:
    if not SAFE_SKILL.fullmatch(name):
        raise InstallError(f"Unsafe skill name: {name}")
    destination = (root / name).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise InstallError(f"Destination escapes target root: {destination}") from exc
    return destination


def preflight_install(
    roots: Sequence[Path], skills: Sequence[str], graph: Mapping[str, Mapping[str, Any]], force: bool
) -> Dict[Path, Dict[str, str]]:
    actions: Dict[Path, Dict[str, str]] = {}
    conflicts: List[str] = []
    for root in roots:
        receipt = read_receipt(root)
        owned = receipt.get("skills", {})
        root_actions: Dict[str, str] = {}
        for name in skills:
            destination = validate_child(root, name)
            expected = str(graph[name]["checksum"])
            if not destination.exists():
                root_actions[name] = "install"
                continue
            if not destination.is_dir() or destination.is_symlink():
                if force:
                    root_actions[name] = "replace"
                else:
                    conflicts.append(f"{destination} exists and is not a safe managed directory")
                continue
            owned_checksum = (owned.get(name) or {}).get("checksum") if isinstance(owned.get(name), dict) else None
            try:
                actual_checksum = directory_checksum(destination)
            except InstallError as exc:
                if force:
                    root_actions[name] = "replace"
                else:
                    conflicts.append(str(exc))
                continue
            if owned_checksum == expected == actual_checksum:
                root_actions[name] = "noop"
            elif force:
                root_actions[name] = "replace"
            else:
                owner = "receipt-owned but changed" if owned_checksum else "untracked"
                conflicts.append(f"{destination} conflicts ({owner}); use --force for explicit replacement")
        actions[root] = root_actions
    if conflicts:
        raise InstallError("Install preflight failed:\n- " + "\n- ".join(conflicts))
    return actions


def copy_to_temporary(source: Path, destination: Path) -> Path:
    temporary = destination.parent / f".{destination.name}.tmp.{uuid.uuid4().hex}"
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(source, temporary, symlinks=False)
    if directory_checksum(temporary) != directory_checksum(source):
        shutil.rmtree(temporary, ignore_errors=True)
        raise InstallError(f"Checksum mismatch after copying {source}")
    return temporary


def apply_install(
    roots: Sequence[Path],
    profile: str,
    skills: Sequence[str],
    graph: Mapping[str, Mapping[str, Any]],
    actions: Mapping[Path, Mapping[str, str]],
    dry_run: bool,
) -> None:
    for root in roots:
        print(f"[{root}] profile={profile} skills={len(skills)}")
        for name in skills:
            print(f"  {actions[root][name]:>7}  {name}")
    if dry_run:
        print("Dry run: no files changed.")
        return

    applied: List[AppliedChange] = []
    previous_receipts: Dict[Path, bytes | None] = {}
    temporary_paths: List[Path] = []
    try:
        for root in roots:
            root.mkdir(parents=True, exist_ok=True)
            receipt_path = root / RECEIPT_NAME
            previous_receipts[root] = receipt_path.read_bytes() if receipt_path.exists() else None
            for name in skills:
                action = actions[root][name]
                if action == "noop":
                    continue
                destination = validate_child(root, name)
                temporary = copy_to_temporary(Path(graph[name]["path"]), destination)
                temporary_paths.append(temporary)
                backup: Path | None = None
                if destination.exists():
                    backup = destination.parent / f".{destination.name}.bak.{uuid.uuid4().hex}"
                    os.replace(destination, backup)
                try:
                    os.replace(temporary, destination)
                    temporary_paths.remove(temporary)
                except Exception:
                    if backup and backup.exists() and not destination.exists():
                        os.replace(backup, destination)
                    raise
                applied.append(AppliedChange(root, destination, backup, backup is None))

        for root in roots:
            receipt = read_receipt(root)
            receipt["schema_version"] = 1
            receipt["package"] = PACKAGE_NAME
            receipt["package_version"] = PACKAGE_VERSION
            receipt["target_root"] = str(root)
            receipt["updated_at"] = utc_now()
            profiles = receipt.setdefault("profiles", {})
            profiles[profile] = list(skills)
            skill_records = receipt.setdefault("skills", {})
            for name in skills:
                skill_records[name] = {
                    "checksum": graph[name]["checksum"],
                    "installed_at": utc_now(),
                    "source": f"skills/{name}",
                }
            atomic_write_json(root / RECEIPT_NAME, receipt)

        for change in applied:
            if change.backup and change.backup.exists():
                shutil.rmtree(change.backup)
        print(f"Installed profile '{profile}' to {len(roots)} target(s).")
    except Exception:
        for temporary in temporary_paths:
            shutil.rmtree(temporary, ignore_errors=True)
        for change in reversed(applied):
            if change.destination.exists():
                shutil.rmtree(change.destination, ignore_errors=True)
            if change.backup and change.backup.exists():
                os.replace(change.backup, change.destination)
        for root, previous in previous_receipts.items():
            receipt_path = root / RECEIPT_NAME
            if previous is None:
                receipt_path.unlink(missing_ok=True)
            else:
                receipt_path.write_bytes(previous)
        raise


def preflight_uninstall(roots: Sequence[Path], profile: str, remove_all: bool) -> Dict[Path, Dict[str, Any]]:
    plans: Dict[Path, Dict[str, Any]] = {}
    errors: List[str] = []
    for root in roots:
        receipt_path = root / RECEIPT_NAME
        if not receipt_path.exists():
            errors.append(f"No receipt found at {receipt_path}")
            continue
        receipt = read_receipt(root)
        profiles = dict(receipt.get("profiles", {}))
        if remove_all:
            selected_profiles = list(profiles)
        else:
            if profile not in profiles:
                errors.append(f"Profile '{profile}' is not recorded in {receipt_path}")
                continue
            selected_profiles = [profile]
        remaining_profiles = {k: v for k, v in profiles.items() if k not in selected_profiles}
        referenced = {name for values in remaining_profiles.values() for name in values}
        selected_skills = {name for p in selected_profiles for name in profiles.get(p, [])}
        removable = sorted(selected_skills - referenced)
        tracked = set(receipt.get("skills", {}))
        unsafe = sorted(name for name in removable if name not in tracked or not SAFE_SKILL.fullmatch(name))
        if unsafe:
            errors.append(f"Receipt contains unsafe or untracked removable skills in {receipt_path}: {', '.join(unsafe)}")
            continue
        plans[root] = {
            "receipt": receipt,
            "remaining_profiles": remaining_profiles,
            "removable": removable,
            "selected_profiles": selected_profiles,
        }
    if errors:
        raise InstallError("Uninstall preflight failed:\n- " + "\n- ".join(errors))
    return plans


def apply_uninstall(roots: Sequence[Path], plans: Mapping[Path, Mapping[str, Any]], dry_run: bool) -> None:
    for root in roots:
        plan = plans[root]
        print(f"[{root}] remove profiles={','.join(plan['selected_profiles']) or '(none)'}")
        for name in plan["removable"]:
            destination = validate_child(root, name)
            state = "remove" if destination.exists() else "missing"
            print(f"  {state:>7}  {name}")
    if dry_run:
        print("Dry run: no files changed.")
        return

    staged: List[Tuple[Path, Path]] = []
    previous_receipts: Dict[Path, bytes] = {}
    try:
        for root in roots:
            receipt_path = root / RECEIPT_NAME
            previous_receipts[root] = receipt_path.read_bytes()
            for name in plans[root]["removable"]:
                destination = validate_child(root, name)
                if not destination.exists():
                    continue
                if not destination.is_dir() or destination.is_symlink():
                    raise InstallError(f"Refusing to remove non-directory or symlink: {destination}")
                staged_path = destination.parent / f".{destination.name}.remove.{uuid.uuid4().hex}"
                os.replace(destination, staged_path)
                staged.append((destination, staged_path))

        for root in roots:
            plan = plans[root]
            receipt = dict(plan["receipt"])
            receipt["profiles"] = plan["remaining_profiles"]
            referenced = {name for values in receipt["profiles"].values() for name in values}
            receipt["skills"] = {k: v for k, v in receipt.get("skills", {}).items() if k in referenced}
            receipt["updated_at"] = utc_now()
            receipt_path = root / RECEIPT_NAME
            if receipt["profiles"] or receipt["skills"]:
                atomic_write_json(receipt_path, receipt)
            else:
                receipt_path.unlink(missing_ok=True)

        for _, staged_path in staged:
            shutil.rmtree(staged_path, ignore_errors=True)
        print(f"Uninstalled requested profile(s) from {len(roots)} target(s).")
    except Exception:
        for destination, staged_path in reversed(staged):
            if staged_path.exists() and not destination.exists():
                os.replace(staged_path, destination)
        for root, content in previous_receipts.items():
            (root / RECEIPT_NAME).write_bytes(content)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("install", "uninstall"):
        command = sub.add_parser(action)
        command.add_argument("--target", choices=["codex", "claude", "both", "custom"], default="both")
        command.add_argument("--dest", type=Path, action="append", default=[], help="Repeatable; only for --target custom")
        command.add_argument("--profile", default="full")
        command.add_argument("--dry-run", action="store_true")
        if action == "install":
            command.add_argument("--force", action="store_true", help="Explicitly replace conflicting same-name skills")
        else:
            command.add_argument("--all", action="store_true", help="Remove every profile recorded by this package receipt")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        roots = target_roots(args.target, args.dest)
        if args.action == "install":
            graph = load_skill_graph()
            profile = load_profile(args.profile)
            skills = expand_dependencies(profile["skills"], graph)
            actions = preflight_install(roots, skills, graph, args.force)
            apply_install(roots, args.profile, skills, graph, actions, args.dry_run)
        else:
            plans = preflight_uninstall(roots, args.profile, args.all)
            apply_uninstall(roots, plans, args.dry_run)
        return 0
    except InstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: filesystem operation failed: {exc}", file=sys.stderr)
        return 3


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
