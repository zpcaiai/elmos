"""Build the fail-closed SQL route closure plan from raw scan evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

TARGETS = ("postgres", "mysql", "oracle", "tsql")
TERMINAL_STATES = (
    "RUNTIME_VERIFIED",
    "MANUAL_RUNTIME_VERIFIED",
    "APPROVED_TIME_BOUNDED_WAIVER",
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def build(reachability_path: Path, backlog_path: Path) -> dict[str, Any]:
    reachability = _load(reachability_path)
    backlog = _load(backlog_path)
    units = reachability.get("routeUnits")
    if not isinstance(units, list) or len(units) != reachability.get(
        "admitted_source_side"
    ):
        raise ValueError(
            "reachability routeUnits must exactly cover admitted_source_side"
        )
    if len({unit.get("unitId") for unit in units if isinstance(unit, dict)}) != len(
        units
    ):
        raise ValueError("reachability routeUnits must have unique unitId values")

    blocked: dict[str, Counter[str]] = {target: Counter() for target in TARGETS}
    emittable: Counter[str] = Counter()
    common = 0
    for unit in units:
        if not isinstance(unit, dict) or set(unit.get("targets", {})) != set(TARGETS):
            raise ValueError("each route unit must contain exactly four target states")
        common += int(unit.get("allFourReachable") is True)
        for target in TARGETS:
            state = unit["targets"][target]
            if state.get("state") == "REACHABLE" and state.get("refusalCode") is None:
                emittable[target] += 1
            elif state.get("state") == "BLOCKED" and isinstance(
                state.get("refusalCode"), str
            ):
                blocked[target][state["refusalCode"]] += 1
            else:
                raise ValueError(
                    f"invalid target state for {unit.get('unitId')}:{target}"
                )

    expected = reachability.get("reachable_per_target")
    if not isinstance(expected, dict) or any(
        expected.get(t) != emittable[t] for t in TARGETS
    ):
        raise ValueError("route-unit details disagree with reachable_per_target")
    if common != reachability.get("translatable_to_all_four"):
        raise ValueError("route-unit details disagree with all-four intersection")

    backlog_items = backlog.get("items")
    if not isinstance(backlog_items, list) or len(backlog_items) != backlog.get(
        "summary", {}
    ).get("total"):
        raise ValueError("manual backlog summary must exactly cover its items")
    manual_by_reason = Counter(
        str(item.get("reason_code")) for item in backlog_items if isinstance(item, dict)
    )
    admitted = len(units)
    cells = admitted * len(TARGETS)
    emittable_cells = sum(emittable.values())
    workstreams = []
    for target in TARGETS:
        for reason, count in blocked[target].most_common():
            workstreams.append(
                {
                    "workstreamId": f"route-{target}-{reason.lower().replace('_', '-')}",
                    "target": target,
                    "blockerCode": reason,
                    "routeCellCount": count,
                    "status": "OPEN",
                    "requiredClosure": [
                        "typed implementation or explicit unsupported decision",
                        "negative and independent holdout cases",
                        "real disposable target execution",
                        "digest-bound revalidation evidence",
                    ],
                }
            )

    return {
        "schemaVersion": "1.0",
        "kind": "elmos.batch31.sql-route-closure-plan",
        "inputs": {
            "reachabilityEvidence": reachability_path.as_posix(),
            "reachabilityDigest": _digest(reachability_path),
            "manualBacklogEvidence": backlog_path.as_posix(),
            "manualBacklogDigest": _digest(backlog_path),
        },
        "definitionOf100Percent": {
            "unitOfAccount": "source-statement-by-launch-target",
            "terminalStates": list(TERMINAL_STATES),
            "rule": (
                "Every frozen source statement must have a terminal state for every launch "
                "target; syntax emission alone is not runtime verification."
            ),
            "sloPolicy": "75 ms p95 is unchanged",
            "retryPolicy": "at most two bounded measurement attempts; no infinite retry",
        },
        "current": {
            "admittedCandidateUnits": admitted,
            "commonFourTargetEmittableUnits": common,
            "commonFourTargetImplementationRate": round(common / admitted, 4)
            if admitted
            else 0.0,
            "commonFourTargetOpenUnits": admitted - common,
            "targetRouteCells": cells,
            "emittableRouteCells": emittable_cells,
            "blockedRouteCells": cells - emittable_cells,
            "runtimeVerifiedRouteCells": 0,
            "manualMigrationItems": len(backlog_items),
            "manualMigrationOpen": sum(
                1
                for item in backlog_items
                if item.get("status") not in {"RESOLVED", "WAIVED"}
            ),
            "externalExecution": "NOT_RUN",
            "independentVerification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "perTarget": {
            target: {
                "emittable": emittable[target],
                "blocked": admitted - emittable[target],
                "runtimeVerified": 0,
                "blockers": dict(blocked[target].most_common()),
            }
            for target in TARGETS
        },
        "manualBacklogByReason": dict(manual_by_reason.most_common()),
        "workstreams": workstreams,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reachability", type=Path, required=True)
    parser.add_argument("--backlog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = (
        json.dumps(
            build(args.reachability, args.backlog),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    if args.check:
        if (
            not args.output.exists()
            or args.output.read_text(encoding="utf-8") != rendered
        ):
            raise SystemExit(f"stale SQL route closure plan: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
