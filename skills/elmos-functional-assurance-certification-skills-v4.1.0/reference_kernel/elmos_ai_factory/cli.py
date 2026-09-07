from __future__ import annotations
import argparse, json
from pathlib import Path
from .capability import FeatureRequirement, TargetProfile, negotiate
from .trace import compare_traces

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    n = sub.add_parser("negotiate")
    n.add_argument("input")
    t = sub.add_parser("compare-traces")
    t.add_argument("reference")
    t.add_argument("candidate")
    args = parser.parse_args()

    if args.command == "negotiate":
        raw = json.loads(Path(args.input).read_text())
        reqs = [FeatureRequirement(r["name"], r.get("critical", True),
                                  frozenset(r.get("acceptedStatuses", ["supported","conditional","external-runtime","external-policy"])))
                for r in raw["requirements"]]
        profiles = [TargetProfile(p["target"], p["features"], p["exactVersion"], p["adapterDigest"])
                    for p in raw["profiles"]]
        result = negotiate(reqs, profiles)
        print(json.dumps(result, default=lambda o: o.__dict__, indent=2))
        return 0 if result.overall != "BLOCKED" else 2
    ref = json.loads(Path(args.reference).read_text())
    cand = json.loads(Path(args.candidate).read_text())
    result = compare_traces(ref, cand)
    print(json.dumps(result, indent=2))
    return 0 if result["equivalent"] else 3

if __name__ == "__main__":
    raise SystemExit(main())
