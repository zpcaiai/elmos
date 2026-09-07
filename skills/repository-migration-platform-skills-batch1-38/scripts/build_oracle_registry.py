#!/usr/bin/env python3
"""Deterministically build the immutable Batch 1-38 Claim Oracle registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def section(text: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else ""


def items(text: str, heading: str) -> list[str]:
    return [match.group(1).strip().rstrip("；;") for match in re.finditer(r"^-\s+(.+?)\s*$", section(text, heading), re.M)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    entries = []
    for skill in manifest["skills"]:
        batch = skill.get("batch")
        if not isinstance(batch, int):
            continue
        text = (ROOT / skill["path"]).read_text(encoding="utf-8")
        claims = {
            "output": items(text, "## Required Outputs"),
            "test": items(text, "## Required Tests"),
        }
        external = {
            2: ["independent clean-environment replay"], 4: ["real source and target toolchain execution for each claimed route"],
            7: ["real source and target database/messaging reconciliation"], 11: ["representative domain journey execution"],
            12: ["authorized shadow/canary/rollback exercise"], 13: ["independent verifier and certificate-authority review"],
            14: ["kernel-checked proof bound to exact artifacts"], 19: ["real toolchain execution over independent route corpora"],
            30: ["authorized restore/failover/DR exercise"], 32: ["representative production-equivalent workload evidence"],
            33: ["independent security assessment"], 34: ["real provider sandbox or authorized endpoint evidence"],
            35: ["accountable production go/no-go approval"], 36: ["real operational period, incident and support evidence"],
            37: ["authorized source retirement and final reconciliation evidence"],
            38: ["independent final assurance review and external CA decision"],
        }.get(batch, [])
        claims["external"] = external
        family = "b%02d-domain-executor-v1" % batch
        for claim_type in ("output", "test", "external"):
            for index, claim in enumerate(claims[claim_type]):
                corpora = (["development", "holdout"] if claim_type == "output" else
                           ["development", "negative", "holdout"] if claim_type == "test" else
                           ["production"])
                entries.append({
                    "batch": batch,
                    "claim_type": claim_type,
                    "claim_index": index,
                    "claim": claim,
                    "claim_sha256": digest(claim),
                    "oracle_id": f"rmp-b{batch:02d}-{claim_type}-{index}-oracle-v1",
                    "executor_id": family,
                    "required_corpora": corpora,
                    "subject_type": "claim-oracle-result",
                })
    payload = {
        "schema_version": "1.0",
        "namespace": "repository-migration-platform-b01-38",
        "entry_count": len(entries),
        "entries": entries,
        "status_boundary": "Registry coverage is executable policy, not evidence that a domain Claim passed.",
    }
    if len(entries) != 347:
        raise SystemExit(f"expected 347 Claim obligations, observed {len(entries)}")
    output = ROOT / "oracle-registry.json"
    if args.check:
        if json.loads(output.read_text(encoding="utf-8")) != payload:
            raise SystemExit("oracle-registry.json is stale")
        print("PASS: 347 Claim Oracle obligations are current")
        return 0
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
