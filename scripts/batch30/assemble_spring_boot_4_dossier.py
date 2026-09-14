#!/usr/bin/env python3
"""Prepare the Spring Boot 4 business line for independent external review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.batch30.assemble_spring_external_request import assemble_request


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
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = assemble_request(
        output_dir=args.output_dir,
        dossier_id="spring-boot-4-modernization-v1",
        pack_keys=PACK_KEYS,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
