#!/usr/bin/env python3
"""Fail-closed Batch 56A product-closure readiness gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "product-closure-convergence"))
from evidence_integrity import verify_file_descriptor, verify_independent_record  # noqa: E402


PROGRAMS = ("canonicalKernel", "goldenJourneys", "providers")


def evaluate(request: dict[str, Any], evidence_root: Path) -> dict[str, Any]:
    reasons: list[str] = []
    if request.get("schemaVersion") != "1.0":
        reasons.append("schemaVersion must be 1.0")
    programs = request.get("programs")
    if not isinstance(programs, dict) or any(programs.get(name) != "COMPLETED" for name in PROGRAMS):
        reasons.append("canonical kernel, Golden Journeys and providers must all be COMPLETED")
    p0_failures = request.get("p0Failures")
    if not isinstance(p0_failures, list) or p0_failures:
        reasons.append("P0 failures are non-waivable and must be empty")
    if request.get("decision") not in {"RELEASE_CANDIDATE", "GA"}:
        reasons.append("request decision must explicitly seek release readiness")

    repository_evidence = request.get("repositoryEvidence")
    if not isinstance(repository_evidence, dict):
        reasons.append("repositoryEvidence is required")
        repository_evidence = {}
    for field in ("artifactManifest", "environmentManifest"):
        ok, reason = verify_file_descriptor(repository_evidence.get(field), evidence_root, field)
        if not ok:
            reasons.append(reason)
    artifact_manifest = repository_evidence.get("artifactManifest")
    if not isinstance(artifact_manifest, dict) or request.get("artifactDigest") != artifact_manifest.get("sha256"):
        reasons.append("artifactDigest must exactly bind artifactManifest.sha256")
    records = repository_evidence.get("programEvidence")
    if not isinstance(records, list):
        records = []
        reasons.append("programEvidence must be a list")
    completed_programs: set[str] = set()
    for index, record in enumerate(records):
        label = f"programEvidence[{index}]"
        if not isinstance(record, dict) or record.get("program") not in PROGRAMS:
            reasons.append(f"{label}.program must name an exact closure program")
            continue
        ok, reason = verify_independent_record(
            record,
            evidence_root,
            label,
            organization_required=False,
        )
        if not ok:
            reasons.append(reason)
        else:
            completed_programs.add(record["program"])
    if completed_programs != set(PROGRAMS):
        reasons.append("each closure program requires independently verified evidence")

    decision = "BLOCKED" if reasons else "READY_FOR_EXTERNAL_GATE"
    return {
        "schemaVersion": "1.0",
        "decision": decision,
        "requestedDecision": request.get("decision", "UNKNOWN"),
        "maximumDecision": "READY_FOR_EXTERNAL_GATE",
        "gaApproved": False,
        "productionCertified": False,
        "externalEvidence": "NOT_RUN" if reasons else "BOUND_FOR_EXTERNAL_REVIEW",
        "programsWithValidEvidence": sorted(completed_programs),
        "reasons": sorted(set(reasons)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    root = (args.evidence_root or args.request.parent).resolve()
    result = evaluate(request, root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if result["decision"] == "READY_FOR_EXTERNAL_GATE" else 2)


if __name__ == "__main__":
    main()
