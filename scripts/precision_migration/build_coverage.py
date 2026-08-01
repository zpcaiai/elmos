#!/usr/bin/env python3
"""Build the exact 587-Skill multidimensional coverage matrix."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "precision-migration-b01-44" / "installed-manifest.json"
ADAPTERS = ROOT / "docs" / "precision-migration-b01-44" / "adapter-registry.json"
DEFAULT_OUTPUT = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "coverage" / "coverage-matrix.json"


def build() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    adapters = json.loads(ADAPTERS.read_text(encoding="utf-8"))
    by_skill = {item["skill"]: item for item in adapters["entries"]}
    locally_exercised = {
        "pm-b02-repository-modernization-assessment",
        *{
            item["skill"]
            for item in adapters["entries"]
            if item["handler_id"] == "batch29-route-validator-v1"
        },
    }
    rows = []
    for record in manifest["skills"]:
        if record["kind"] != "skill":
            continue
        adapter = by_skill[record["name"]]
        rows.append(
            {
                "skill": record["name"],
                "source_skill": record["source_name"],
                "batch": record["batch"],
                "risk_tier": "P0" if record["batch"] in {7, 19, 20, 21, 22, 23, 24, 25, 26, 30, 32, 33, 34, 35, 41, 42, 44} else "P1",
                "maturity": record["maturity"],
                "handler_id": adapter["handler_id"],
                "coverage": {
                    "source_contract": "PASSED",
                    "installed_identity": "PASSED",
                    "handler_contract": "DECLARED" if record["maturity"] == "ADAPTER_DECLARED" else "NOT_AVAILABLE",
                    "local_execution": "PASSED" if record["name"] in locally_exercised else "NOT_RUN",
                    "negative": "NOT_RUN",
                    "integration": "NOT_RUN",
                    "native_source_build": "NOT_RUN",
                    "native_target_build": "NOT_RUN",
                    "holdout": "NOT_RUN",
                    "representative_workload": "NOT_RUN",
                    "independent_verification": "NOT_RUN",
                    "external_evidence": "NOT_RUN",
                },
                "owner": "elmos-migration-platform-engineering",
                "limitations": [
                    "Cross-cutting runtime trust tests do not establish this Skill's domain semantics.",
                    "A PASSED local_execution row covers only the named allowlisted handler operation."
                ],
            }
        )
    if len(rows) != 587 or len({row["skill"] for row in rows}) != 587:
        raise ValueError("coverage matrix must contain exactly 587 unique child Skills")
    dimensions = [
        "source_contract", "installed_identity", "handler_contract", "local_execution",
        "negative", "integration", "native_source_build", "native_target_build", "holdout",
        "representative_workload", "independent_verification", "external_evidence",
    ]
    summaries = {
        dimension: dict(sorted(Counter(row["coverage"][dimension] for row in rows).items()))
        for dimension in dimensions
    }
    return {
        "schema_version": 1,
        "matrix_key": "precision-migration-b01-44-skill-coverage-v1",
        "scope": {
            "child_skill_count": 587,
            "source_tree_sha256": manifest["source_tree_sha256"],
            "installed_manifest": "docs/precision-migration-b01-44/installed-manifest.json",
            "adapter_registry": "docs/precision-migration-b01-44/adapter-registry.json",
        },
        "dimensions": dimensions,
        "summaries": summaries,
        "rows": rows,
        "release_rule": "No aggregate percentage may override a NOT_RUN or NOT_AVAILABLE P0 row.",
        "production_certification": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("coverage matrix drifted; regenerate it")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "rows": 587, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
