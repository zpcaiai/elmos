#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-implementation"))

from elmos_cache_ref.policies import PolicyRouter  # noqa: E402
from elmos_cache_ref.simulator import compare, load_jsonl, workload_features  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay an ELMOS cache trace against equal-capacity policies"
    )
    parser.add_argument("trace", type=Path)
    parser.add_argument("--capacity-bytes", type=int, required=True)
    parser.add_argument(
        "--policies",
        default="LRU,SIEVE,S3_FIFO,W_TINY_LFU,SIZE_AWARE_TINY_LFU,GDSF",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.capacity_bytes <= 0:
        raise SystemExit("--capacity-bytes must be positive")
    events = load_jsonl(args.trace)
    names = [name.strip() for name in args.policies.split(",") if name.strip()]
    reports = compare(names, args.capacity_bytes, events)
    features = workload_features(events)
    choice = PolicyRouter().choose(features)

    payload = {
        "schema_version": "1.1.0",
        "report_id": "cache-benchmark-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trace_corpus_digest": sha256_file(args.trace),
        "capacity_bytes": args.capacity_bytes,
        "baseline": "LRU",
        "workload_features": {
            field: getattr(features, field)
            for field in features.__dataclass_fields__
        },
        "selector_recommendation": {
            "policy": choice.policy,
            "confidence": choice.confidence,
            "reason_codes": list(choice.reason_codes),
        },
        "candidates": [
            {
                "policy": report.policy,
                "metrics": {
                    key: value
                    for key, value in report.to_dict().items()
                    if isinstance(value, (int, float)) and key not in {"capacity_bytes"}
                },
                "configuration": {"capacity_bytes": report.capacity_bytes},
            }
            for report in reports
        ],
        "gates": {
            "correctness_failures": 0,
            "selected": None,
            "reasons": [
                "Reference simulator output only; production selection requires representative ELMOS holdout traces."
            ],
        },
    }

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
