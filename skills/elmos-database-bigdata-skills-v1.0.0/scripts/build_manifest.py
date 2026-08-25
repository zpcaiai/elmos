#!/usr/bin/env python3
"""Build a reproducible checksum manifest for this skill package."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_FILES = {"MANIFEST.json", "VALIDATION-REPORT.md"}
SAFE_SKILL = re.compile(r"^elmos-[a-z0-9][a-z0-9-]*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_directory(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda p: p.as_posix()):
        if item.is_symlink():
            raise RuntimeError(f"Symlink is not allowed: {item}")
        if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc":
            rel = item.relative_to(path).as_posix().encode("utf-8")
            content = item.read_bytes()
            digest.update(len(rel).to_bytes(8, "big"))
            digest.update(rel)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    return digest.hexdigest()


def parse_frontmatter(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise RuntimeError(f"Invalid frontmatter in {path}")
    end = text.find("\n---\n", 4)
    result: Dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, raw = line.split(":", 1)
        raw = raw.strip()
        result[key.strip()] = json.loads(raw) if raw.startswith("[") else raw.strip('"\'')
    return result


def included_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if rel.as_posix() in EXCLUDED_FILES or "__pycache__" in rel.parts or path.suffix == ".pyc":
            continue
        files.append(path)
    return files


def build(root: Path) -> Dict[str, Any]:
    skills: List[Dict[str, Any]] = []
    groups: Counter[str] = Counter()
    for directory in sorted((root / "skills").iterdir()):
        if not directory.is_dir():
            continue
        if not SAFE_SKILL.fullmatch(directory.name):
            raise RuntimeError(f"Unsafe skill name: {directory.name}")
        meta = parse_frontmatter(directory / "SKILL.md")
        groups[str(meta.get("group"))] += 1
        skills.append({
            "name": directory.name,
            "group": meta.get("group"),
            "version": meta.get("version"),
            "dependencies": meta.get("dependencies", []),
            "path": f"skills/{directory.name}",
            "sha256": hash_directory(directory),
        })

    profiles: Dict[str, Dict[str, Any]] = {}
    for path in sorted((root / "profiles").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        profiles[path.stem] = {
            "declared_skill_count": len(data.get("skills", [])),
            "path": path.relative_to(root).as_posix(),
        }

    checksums = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in included_files(root)
    }
    return {
        "manifest_schema_version": 1,
        "package": "elmos-database-bigdata-skills",
        "package_version": "1.0.0",
        "generated_on": date.today().isoformat(),
        "description": "Database intelligence and production-grade big-data project generation skills for Elmos, Codex and Claude Code.",
        "skill_count": len(skills),
        "group_counts": dict(sorted(groups.items())),
        "profile_count": len(profiles),
        "profiles": profiles,
        "skills": skills,
        "checksums_sha256": checksums,
        "checksum_exclusions": sorted(EXCLUDED_FILES | {"**/__pycache__/**", "**/*.pyc"}),
        "trust_boundary": {
            "catalog_is_seed_evidence": True,
            "catalog_entry_does_not_equal_verified_adapter": True,
            "production_requires_repository_specific_tests": True
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve() if args.output else root / "MANIFEST.json"
    manifest = build(root)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output} with {manifest['skill_count']} skills and {len(manifest['checksums_sha256'])} file checksums.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
