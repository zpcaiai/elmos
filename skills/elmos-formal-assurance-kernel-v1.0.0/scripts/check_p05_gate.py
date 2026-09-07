#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

REQUIRED = [
  "imagesPinned","sbomVerified","signaturesVerified","vulnerabilityGatePassed",
  "databaseMigrationsApplied","backupRestoreRehearsed","livezPassed","readyzPassed",
  "metricsPassed","versionPassed","networkPolicyEnforced","solverSandboxVerified",
  "evidenceStoreIntegrityPassed","releaseManifestSigned"
]

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence",required=True,type=Path)
    args=parser.parse_args()
    data=json.loads(args.evidence.read_text(encoding="utf-8"))
    missing=[k for k in REQUIRED if data.get(k) is not True]
    synthetic=data.get("environment")=="SYNTHETIC"
    if missing:
        print(json.dumps({"decision":"DENY","missing":missing},indent=2))
        return 1
    if synthetic:
        print(json.dumps({"decision":"ADVISORY","reason":"synthetic evidence cannot complete P05"},indent=2))
        return 2
    print(json.dumps({"decision":"ALLOW","gate":"P05_DEPLOYMENT_COMPLETE"},indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
