#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etgb.evidence import EvidenceStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a redacted, content-addressed ETGB evidence bundle")
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/etgb-evidence-bundle"))
    parser.add_argument("--archive", type=Path, default=Path("reports/etgb-evidence.tar.gz"))
    parser.add_argument("--producer-environment", default="local-validation")
    parser.add_argument("--run-id", default="package-validation")
    parser.add_argument("--candidate-digest", default="sha256:" + "0" * 64)
    parser.add_argument("--plan-digest", default="sha256:" + "0" * 64)
    parser.add_argument("--hmac-key-file", type=Path)
    args = parser.parse_args()

    reports = args.reports.resolve()
    output_dir = args.output_dir.resolve()
    archive = args.archive.resolve()
    key = args.hmac_key_file.read_bytes().strip() if args.hmac_key_file else None
    if output_dir.exists():
        shutil.rmtree(output_dir)
    store = EvidenceStore(output_dir, hmac_key=key)
    excluded = {output_dir, archive}
    for path in sorted(p for p in reports.rglob("*") if p.is_file()):
        if any(parent == path or parent in path.parents for parent in excluded):
            continue
        logical = str(path.relative_to(reports))
        redact = path.suffix.lower() in {".txt", ".log", ".json", ".jsonl", ".yaml", ".yml", ".md", ".xml"}
        store.add_file(path, logical_name=logical, producer_environment=args.producer_environment, redact=redact)
    store.seal({
        "run_id": args.run_id,
        "candidate_digest": args.candidate_digest,
        "plan_digest": args.plan_digest,
        "producer_environment": args.producer_environment,
    })
    verification = store.verify()
    if archive.exists():
        archive.unlink()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(output_dir, arcname=output_dir.name)
    print(json.dumps({"bundle": str(output_dir), "archive": str(archive), "verification": verification}, indent=2))
    return 0 if verification["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
