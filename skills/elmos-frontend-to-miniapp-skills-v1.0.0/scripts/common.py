from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


def package_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "skill-manifest.yaml").exists():
            return candidate
    raise RuntimeError("Could not locate package root containing skill-manifest.yaml")


def load_manifest(root: Path) -> dict[str, Any]:
    yaml_data = yaml.safe_load((root / "skill-manifest.yaml").read_text(encoding="utf-8"))
    json_data = json.loads((root / "skill-manifest.json").read_text(encoding="utf-8"))
    if yaml_data != json_data:
        raise ValueError("YAML and JSON manifests differ")
    return yaml_data


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Missing or invalid YAML frontmatter: {path}")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError(f"Frontmatter must be an object: {path}")
    return data, match.group(2)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_files(root: Path) -> list[Path]:
    excluded = {
        "CHECKSUMS.sha256",
    }
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in excluded or rel.startswith(".git/") or "__pycache__" in path.parts:
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())
