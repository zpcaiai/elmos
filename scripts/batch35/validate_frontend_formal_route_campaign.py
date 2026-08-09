#!/usr/bin/env python3
"""Batch 35 entry point for the independent frontend formal campaign."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    parser.add_argument("--campaign")
    parser.add_argument("--no-replay-execute", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve()
    batch32_path = (
        here.parents[1] / "batch32" / "validate_frontend_formal_route_campaign.py"
    )
    namespace = runpy.run_path(
        str(batch32_path), run_name="elmos_batch35_frontend_formal_validator"
    )
    validate_campaign = namespace.get("validate_campaign")
    if not callable(validate_campaign):
        result = {
            "status": "invalid",
            "formal_ready": False,
            "certification_ready": False,
            "errors": ["Batch 32 frontend validator is unavailable"],
        }
    else:
        repo_root = here.parents[2]
        result = validate_campaign(
            Path(args.pack_dir),
            campaign_relative=args.campaign,
            schema_path=repo_root
            / "schemas/batch32/frontend-formal-route-campaign.schema.json",
            route_schema_path=repo_root
            / "schemas/batch32/frontend-formal-route-evidence.schema.json",
            execute_replay=not args.no_replay_execute,
        )
        result["batch35_frontend_profile"] = "frontend-72-route-formal-equivalence-v1"
        try:
            manifest = load(Path(args.pack_dir) / "pack.json")
            if manifest.get("pack_key") != "frontend-72-route-formal-equivalence-v1":
                result.setdefault("errors", []).append(
                    "Batch 35 frontend campaign pack_key must be exact"
                )
                result["status"] = "invalid"
                result["formal_ready"] = False
                result["certification_ready"] = False
                result["structural_status"] = "FAILED"
        except Exception as exc:
            result.setdefault("errors", []).append(
                f"cannot load Batch 35 pack manifest: {exc}"
            )
            result["status"] = "invalid"
            result["formal_ready"] = False
            result["certification_ready"] = False
            result["structural_status"] = "FAILED"
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif result.get("status") == "valid":
        print(
            "OK: Batch 35 frontend formal campaign "
            f"formal_ready={str(result.get('formal_ready')).lower()} "
            f"certification_ready={str(result.get('certification_ready')).lower()}"
        )
    else:
        print(
            "\n".join("ERROR: " + item for item in result.get("errors", [])),
            file=sys.stderr,
        )
    return 0 if result.get("status") == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
