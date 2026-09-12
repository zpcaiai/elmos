#!/usr/bin/env python3
"""Run legacy web modernization pipeline on sample eCommerce app and export semantic correspondence ledger."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
LEGACY_ENGINE_SRC = ROOT / "engines/legacy-web-modernization-engine/src"
if str(LEGACY_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(LEGACY_ENGINE_SRC))

from elmos_legacy_web_modernization.runtime import dispatch
from elmos_legacy_web_modernization.canonical import canonical_digest

FIXTURE_ROOT = ROOT / "engines/legacy-web-modernization-engine/fixtures/sample_struts_spring_ecommerce"
OUTPUT_DIR = ROOT / "docs/live-workbench"
OUTPUT_FILE = OUTPUT_DIR / "sample-semantic-correspondence-ledger.json"


def run_pipeline():
    print(f"Loading fixture from: {FIXTURE_ROOT}")
    if not FIXTURE_ROOT.is_dir():
        print(f"Error: Fixture root does not exist: {FIXTURE_ROOT}", file=sys.stderr)
        sys.exit(1)

    # 1. Dispatch 51-struts1-to-springmvc-generator
    req_gen = {
        "request_id": "req-gen-1",
        "tenant_id": "tenant-ecommerce",
        "project_id": "proj-legacy-shop",
        "job_id": "job-modernize-1",
        "skill_id": "51-struts1-to-springmvc-generator",
        "idempotency_key": "idemp-gen-1",
        "inputs": {"repository_root": str(FIXTURE_ROOT)},
        "policy": {"mode": "preserve-first", "equivalence": "strict"},
        "authority": {
            "environment_id": "env-local",
            "profile": "transform",
            "scopes": ["repository-read", "transform"],
            "fencing_token": 10,
        },
    }
    print("Running 51-struts1-to-springmvc-generator...")
    res_gen = dispatch(req_gen)
    print(f"Generator State: {res_gen['state']}, Code: {res_gen['code']}")

    # 2. Dispatch 57-source-map-change-provenance
    req_map = {
        "request_id": "req-map-1",
        "tenant_id": "tenant-ecommerce",
        "project_id": "proj-legacy-shop",
        "job_id": "job-modernize-1",
        "skill_id": "57-source-map-change-provenance",
        "idempotency_key": "idemp-map-1",
        "inputs": {"repository_root": str(FIXTURE_ROOT)},
        "policy": {"mode": "preserve-first", "equivalence": "strict"},
        "authority": {
            "environment_id": "env-local",
            "profile": "transform",
            "scopes": ["repository-read", "transform"],
            "fencing_token": 10,
        },
    }
    print("Running 57-source-map-change-provenance...")
    res_map = dispatch(req_map)
    print(f"Source Map State: {res_map['state']}, Code: {res_map['code']}")

    # 3. Assemble and persist semantic correspondence ledger
    ledger = {
        "schema_version": "semantic-correspondence.v1",
        "fixture_repository": str(FIXTURE_ROOT.relative_to(ROOT)),
        "generation_result": res_gen.get("artifacts", [{}])[0].get("payload", {}),
        "correspondence_ledger": res_map.get("artifacts", [{}])[0].get("payload", {}),
        "source_snapshot_digest": res_map.get("artifacts", [{}])[0].get("payload", {}).get("repositorySnapshotId"),
        "target_digest": res_map.get("artifacts", [{}])[0].get("payload", {}).get("targetDigest"),
        "mappings": res_map.get("artifacts", [{}])[0].get("payload", {}).get("mappings", []),
    }
    ledger["ledger_digest"] = canonical_digest(ledger)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Successfully exported semantic correspondence ledger to: {OUTPUT_FILE}")
    print(f"Total Mappings Generated: {len(ledger['mappings'])}")
    for m in ledger['mappings']:
        print(f" - {m['id']}: target={m['targetLocations'][0]['uri']}")


if __name__ == "__main__":
    run_pipeline()
