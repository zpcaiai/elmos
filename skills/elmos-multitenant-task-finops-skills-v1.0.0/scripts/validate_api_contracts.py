#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def resolve_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("#/"):
        raise ValueError(f"only internal references are allowed: {pointer}")
    current = document
    for raw in pointer[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise KeyError(pointer)
        current = current[token]
    return current


def walk_refs(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            else:
                yield from walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_refs(child)


def validate_file(path: Path, kind: str) -> list[str]:
    errors: list[str] = []
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path.name}: YAML parse error: {exc}"]
    if not isinstance(doc, dict):
        return [f"{path.name}: document must be an object"]

    if kind == "openapi":
        if doc.get("openapi") != "3.1.0":
            errors.append(f"{path.name}: expected OpenAPI 3.1.0")
        if not isinstance(doc.get("paths"), dict) or not doc["paths"]:
            errors.append(f"{path.name}: paths are missing")
        required_ops = {"createTask", "pauseTask", "resumeTask", "cancelTask", "getTaskFinancialSummary"}
        operation_ids = set()
        for path_item in doc.get("paths", {}).values():
            if isinstance(path_item, dict):
                for op in path_item.values():
                    if isinstance(op, dict) and isinstance(op.get("operationId"), str):
                        operation_ids.add(op["operationId"])
        missing = required_ops - operation_ids
        if missing:
            errors.append(f"{path.name}: missing operations: {sorted(missing)}")
    else:
        if doc.get("asyncapi") != "2.6.0":
            errors.append(f"{path.name}: expected AsyncAPI 2.6.0")
        channels = doc.get("channels")
        if not isinstance(channels, dict) or len(channels) < 7:
            errors.append(f"{path.name}: expected lifecycle/progress/checkpoint/slot/usage/revenue/financial channels")

    for ref in walk_refs(doc):
        try:
            resolve_pointer(doc, ref)
        except Exception:
            errors.append(f"{path.name}: unresolved reference {ref}")
    return errors


def main() -> int:
    errors = []
    errors += validate_file(ROOT / "api" / "openapi.yaml", "openapi")
    errors += validate_file(ROOT / "events" / "asyncapi.yaml", "asyncapi")
    for path in sorted((ROOT / "config").glob("*.yaml")):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                errors.append(f"{path.name}: config must be a mapping")
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        print("API/config contract validation FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("API/config contract validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
