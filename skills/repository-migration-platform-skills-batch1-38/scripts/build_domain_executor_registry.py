#!/usr/bin/env python3
"""Build the immutable Batch 1-38 domain-executor registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDLERS = (
    "source-baseline", "differential-replay", "semantic-frontend", "directional-routes",
    "framework-adapters", "supply-chain", "data-messaging", "api-mesh",
    "concurrency-native", "test-mutation-fuzz", "domain-journey", "production-migration",
    "evidence-certification", "formal-proof", "counterexample-repair", "architecture-search",
    "workflow-execution", "project-generation", "generator-routes", "skill-runtime",
    "capability-closure", "business-line", "cross-domain-journey", "data-lineage",
    "data-reconciliation", "admin-control-plane", "identity-authorization", "usability-operations",
    "regression-assurance", "ha-dr", "transaction-correctness", "performance-capacity",
    "security-protection", "provider-reliability", "go-live", "production-operations",
    "source-retirement", "final-assurance",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    titles = {item["batch"]: item["name"] for item in manifest["skills"] if isinstance(item.get("batch"), int)}
    entries = []
    for batch, handler in enumerate(HANDLERS, 1):
        entries.append({
            "batch": batch,
            "executor_id": f"b{batch:02d}-domain-executor-v1",
            "handler": handler,
            "skill": titles[batch],
            "implementation": "typed-native-result-validator",
            "allowed_corpora": ["development", "negative", "holdout", "representative", "production"],
            "requires_actual_toolchain": True,
            "requires_raw_evidence": True,
            "repository_commands_allowed": False,
            "status_boundary": "A validated domain result is eligible for signed Claim-Oracle review; it is not certification.",
        })
    payload = {
        "schema_version": "1.0",
        "namespace": "repository-migration-platform-b01-38",
        "executor_count": len(entries),
        "entries": entries,
    }
    output = ROOT / "domain-executor-registry.json"
    if args.check:
        if json.loads(output.read_text(encoding="utf-8")) != payload:
            raise SystemExit("domain-executor-registry.json is stale")
        print("PASS: 38 domain executors are current")
        return 0
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
