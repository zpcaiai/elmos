"""Safe package/suite I/O helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

import yaml

from .package import PACKAGE_ROOT_NAME


def package_root() -> Path:
    configured = os.environ.get("ELMOS_ETGB_PACKAGE_ROOT")
    if configured:
        return Path(configured).resolve(strict=True)
    return Path(__file__).resolve().parents[4] / "skills" / "subskills" / PACKAGE_ROOT_NAME


def suite_manifest(root: Path | None = None) -> dict[str, Any]:
    value = yaml.safe_load((root or package_root()) .joinpath("suites/suite.yaml").read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("suite manifest must be an object")
    return value


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip(): continue
            value = json.loads(line)
            if not isinstance(value, dict): raise ValueError(f"JSONL record is not an object: {path}:{number}")
            yield value


def iter_cases(root: Path | None = None) -> Iterator[dict[str, Any]]:
    base = (root or package_root()).resolve(strict=True)
    for relative in suite_manifest(base).get("case_files", []):
        path = (base / str(relative)).resolve(strict=True)
        path.relative_to(base)
        yield from iter_jsonl(path)


def case_by_id(case_id: str, root: Path | None = None) -> dict[str, Any] | None:
    return next((case for case in iter_cases(root) if case.get("id") == case_id), None)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text("".join(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n" for value in values), encoding="utf-8")
