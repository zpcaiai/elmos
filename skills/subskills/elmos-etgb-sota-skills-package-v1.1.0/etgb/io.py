from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import yaml


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def suite_manifest(root: Path | None = None) -> dict[str, Any]:
    root = root or package_root()
    return yaml.safe_load((root / "suites/suite.yaml").read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{number}: {exc}") from exc


def iter_cases(root: Path | None = None) -> Iterator[dict[str, Any]]:
    root = root or package_root()
    manifest = suite_manifest(root)
    for rel in manifest["case_files"]:
        yield from iter_jsonl(root / rel)


def case_by_id(case_id: str, root: Path | None = None) -> dict[str, Any] | None:
    for case in iter_cases(root):
        if case["id"] == case_id:
            return case
    return None


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for value in values:
            fh.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
