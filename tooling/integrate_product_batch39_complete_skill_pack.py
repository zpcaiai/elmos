#!/usr/bin/env python3
"""Normalize and install the submitted Product B39 complete Codex Skill pack."""

from __future__ import annotations

import json
from pathlib import Path

from integrate_product_batch34_38_complete_skill_packs import (
    ROOT,
    RUNTIME,
    load_official_validator,
    normalize_pack,
)


PRIOR_COMPLETE = ROOT / "docs" / "product-batches34-38-complete" / "skill-source-manifest.json"
LEGACY = ROOT / "docs" / "product-batches33-38" / "skill-source-manifest.json"
OUTPUT = ROOT / "docs" / "product-batches39-complete" / "skill-source-manifest.json"


def main() -> None:
    validate_skill = load_official_validator()
    package, records = normalize_pack(39, validate_skill)
    if len(records) != 48 or len({record["name"] for record in records}) != 48:
        raise SystemExit("Product B39 complete pack must contain 48 unique normalized Skills")

    legacy_names = {
        record["name"]
        for record in json.loads(LEGACY.read_text(encoding="utf-8"))["records"]
    }
    prior_names = {
        record["name"]
        for record in json.loads(PRIOR_COMPLETE.read_text(encoding="utf-8"))["records"]
    }
    names = {record["name"] for record in records}
    superseded = sorted((legacy_names | prior_names).intersection(names))
    canonical = legacy_names | prior_names | names
    if superseded or len(canonical) != 339:
        raise SystemExit(
            f"Product B39 expected 0 superseded names and 339 canonical Product Skills; "
            f"found {len(superseded)} and {len(canonical)}"
        )

    for record in records:
        record["family"] = "elmos-product-commercialization-b39-complete"
    payload = {
        "namespace_policy": {
            "product_commercialization": "Product Batch B39 Finance",
            "migration_pack": "Migration Pack M39 Global SRE",
        },
        "generated_by": "tooling/integrate_product_batch39_complete_skill_pack.py",
        "external_execution_evidence": "NOT_RUN",
        "pack_skill_count": 48,
        "canonical_product_skill_count_with_prior_families": len(canonical),
        "superseded_prior_record_count": len(superseded),
        "superseded_prior_records": superseded,
        "packages": [package],
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "complete_pack_skills": len(records),
                "normalized_names": package["renamed_for_codex"],
                "superseded_prior_records": len(superseded),
                "canonical_product_skills": len(canonical),
                "runtime_skill_total": len(list(RUNTIME.glob("*/SKILL.md"))),
                "external_execution_evidence": "NOT_RUN",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
