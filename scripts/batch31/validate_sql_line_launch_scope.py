#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def validate_scope(repo: Path, scope_path: Path) -> list[str]:
    failures: list[str] = []
    scope = _load(scope_path)
    schema = _load(repo / "schemas/batch31/sql-line-launch-scope.schema.json")
    for error in sorted(
        Draft202012Validator(schema).iter_errors(scope),
        key=lambda item: list(item.path),
    ):
        location = "/".join(str(part) for part in error.path) or "$"
        failures.append(f"launch scope schema {location}: {error.message}")

    route_ids: set[str] = set()
    pack_keys: set[str] = set()
    for route in scope.get("routes", []):
        if not isinstance(route, dict):
            continue
        route_id = route.get("route_id")
        pack_key = route.get("pack_key")
        if route_id in route_ids:
            failures.append(f"duplicate launch route: {route_id}")
        if pack_key in pack_keys:
            failures.append(f"duplicate launch pack: {pack_key}")
        route_ids.add(str(route_id))
        pack_keys.add(str(pack_key))
        if not isinstance(pack_key, str) or Path(pack_key).name != pack_key:
            failures.append(f"unsafe launch pack key: {pack_key!r}")
            continue
        pack_dir = repo / "database-packs" / pack_key
        try:
            manifest = _load(pack_dir / "pack.json")
            gate = _load(pack_dir / "certification/gate-result.json")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            failures.append(f"{pack_key}: {error}")
            continue
        if manifest.get("source") != route.get("source"):
            failures.append(f"{pack_key}: launch source tuple differs from pack")
        if manifest.get("target") != route.get("target"):
            failures.append(f"{pack_key}: launch target tuple differs from pack")
        if manifest.get("status") != route.get("status"):
            failures.append(f"{pack_key}: launch status differs from pack")
        if gate.get("release_eligible") is not route.get("release_eligible"):
            failures.append(f"{pack_key}: launch release eligibility differs from gate")
        if route.get("release_eligible") and gate.get("derived_status") not in {
            "limited",
            "certified",
        }:
            failures.append(
                f"{pack_key}: release-eligible route was not derived as limited or certified"
            )
        if (
            scope.get("release_channel") == "GA"
            and route.get("release_eligible")
            and gate.get("certification_decision") != "CERTIFIED"
        ):
            failures.append(f"{pack_key}: GA route is not certified by the gate")
    if scope.get("release_channel") == "GA" and any(
        not route.get("release_eligible")
        for route in scope.get("routes", [])
        if isinstance(route, dict)
    ):
        failures.append("GA scope contains a route that is not release eligible")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scope", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    try:
        failures = validate_scope(repo, args.scope.resolve())
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        failures = [str(error)]
    if failures:
        print(
            "\n".join(f"LAUNCH SCOPE FAIL: {failure}" for failure in failures),
            file=sys.stderr,
        )
        return 1
    print(f"LAUNCH SCOPE VALID: {args.scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
