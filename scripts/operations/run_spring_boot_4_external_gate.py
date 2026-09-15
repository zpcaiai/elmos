#!/usr/bin/env python3
"""Run the Spring Boot 4 gate against externally mounted evidence only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.operations.spring_external_gate_common import ExternalGateError, run_gate


PACK_KEYS = (
    "spring-boot-1-5-to-4-1-0",
    "spring-boot-2-0-2-6-to-4-1-0",
    "spring-boot-2-7-18-to-4-1-0",
    "spring-boot-3-0-3-4-to-4-1-0",
    "spring-boot-3-5-to-4-1-0",
    "spring-boot-2-x-gradle-to-4-1-0",
    "spring-framework-5-3-mvc-to-boot-4-1-0",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        status, result = run_gate(
            label="spring-boot-4-modernization",
            pack_keys=PACK_KEYS,
            dossier_id="spring-boot-4-modernization-v1",
            mounted=args.external_root,
        )
    except (ExternalGateError, OSError, ValueError) as exc:
        print(f"SPRING BOOT 4 EXTERNAL GATE FAIL: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
