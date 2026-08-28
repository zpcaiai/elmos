from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict

from .engine import PricingBillingEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elmos-pricing-billing",
        description="Run deterministic local pricing/billing reference behavior; never a production charge.",
    )
    parser.add_argument("command", choices=("demo", "scenario", "qualify", "manifest"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = PricingBillingEngine()
    report, observations = engine.run_local_demo()
    manifest = engine.local_qualification_manifest()
    payload: dict[str, object] = {
        "qualification": asdict(report),
        "authority": "LOCAL_REFERENCE_ONLY",
        "external_side_effects": False,
        "persistence_scope": "IN_MEMORY_SAME_PROCESS_ONLY",
    }
    if args.command == "manifest":
        payload["implementation_manifest"] = asdict(manifest)
    else:
        payload["implementation_manifest"] = {
            "authority": manifest.authority,
            "maximum_readiness": manifest.maximum_readiness,
            "skill_count": manifest.skill_count,
            "requirement_count": manifest.requirement_count,
            "persistence_scope": manifest.persistence_scope,
        }
    if args.command == "demo":
        payload["observations"] = observations
    elif args.command == "scenario":
        payload["scenario"] = PricingBillingEngine.run_local_budget_scenario()
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if engine.external_boundaries_are_unexecuted(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
