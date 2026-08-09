#!/usr/bin/env python3
"""Batch 35 entry point for the exact frontend interaction v2 campaign."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any


PACK_KEY = "frontend-72-route-formal-equivalence-v2"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def fail(result: dict[str, Any], message: str) -> None:
    result.setdefault("errors", []).append(message)
    result.update(
        {
            "status": "invalid",
            "structural_status": "FAILED",
            "model_formal_ready": False,
            "formal_ready": False,
            "browser_ready": False,
            "native_ready": False,
            "runtime_ready": False,
            "independent_ready": False,
            "certification_ready": False,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    parser.add_argument("--campaign")
    parser.add_argument("--no-replay-execute", action="store_true")
    parser.add_argument("--external-trust-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    batch32_dir = here.parents[1] / "batch32"
    sys.path.insert(0, str(batch32_dir))
    namespace = runpy.run_path(
        str(batch32_dir / "validate_frontend_formal_route_campaign_v2.py"),
        run_name="elmos_batch35_frontend_formal_validator_v2",
    )
    validate_campaign = namespace.get("validate_campaign")
    if not callable(validate_campaign):
        result: dict[str, Any] = {}
        fail(result, "Batch 32 frontend v2 validator is unavailable")
    else:
        result = validate_campaign(
            Path(args.pack_dir),
            campaign_relative=args.campaign,
            schema_path=repo_root
            / "schemas/batch32/frontend-formal-route-campaign-v2.schema.json",
            route_schema_path=repo_root
            / "schemas/batch32/frontend-formal-route-evidence-v2.schema.json",
            execute_replay=not args.no_replay_execute,
            external_trust_root_path=(
                args.external_trust_root
                if args.external_trust_root is not None
                else Path(os.environ["ELMOS_FRONTEND_EXTERNAL_TRUST_ROOT"])
                if os.environ.get("ELMOS_FRONTEND_EXTERNAL_TRUST_ROOT")
                else None
            ),
        )
        result["batch35_frontend_profile"] = PACK_KEY
        try:
            manifest = load(Path(args.pack_dir) / "pack.json")
            if manifest.get("pack_key") != PACK_KEY:
                fail(result, "Batch 35 frontend v2 campaign pack_key must be exact")
        except Exception as exc:
            fail(result, f"cannot load Batch 35 v2 pack manifest: {exc}")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif result.get("status") == "valid":
        print(
            "OK: Batch 35 frontend v2 formal campaign "
            f"model_formal_ready={str(result.get('model_formal_ready')).lower()} "
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
