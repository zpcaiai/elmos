#!/usr/bin/env python3
"""Deterministic reference quote calculator for examples and tests.

This is not a production pricing engine. It demonstrates integer/Decimal
arithmetic, BYOK split billing, quality modes, P50/P80/P90 ranges, cap creation,
and separation of machine runtime from human effort.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Any

QUALITY_BP = {
    "economy": 8500,
    "balanced": 10000,
    "best_quality": 13500,
}
DEFAULT_INTERVAL_BP = {"p50": 10000, "p80": 11500, "p90": 13000}


def ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def scaled(amount: int, basis_points: int) -> int:
    return ceil_decimal(Decimal(amount) * Decimal(basis_points) / Decimal(10000))


def rate_resource(resource: dict[str, Any], *, byok: bool) -> tuple[int, int, dict[str, Any]]:
    quantity = Decimal(str(resource["quantity"]))
    unit_size = Decimal(str(resource.get("unit_size", 1)))
    if quantity < 0 or unit_size <= 0:
        raise ValueError("quantity must be >= 0 and unit_size must be > 0")

    units = quantity / unit_size
    customer_rate = int(resource.get("customer_rate_minor_per_unit", 0))
    vendor_rate = int(resource.get("vendor_cost_minor_per_unit", 0))
    category = str(resource.get("category", "other"))
    customer_owned = bool(resource.get("customer_owned_provider", False))

    customer_charge = ceil_decimal(units * customer_rate)
    vendor_cost = ceil_decimal(units * vendor_rate)

    # BYOK excludes the customer-owned model-provider component only.
    if byok and customer_owned and category == "managed_model":
        customer_charge = 0
        vendor_cost = 0

    detail = {
        "code": resource["code"],
        "category": category,
        "quantity": str(quantity),
        "unit_size": str(unit_size),
        "customer_charge_minor": customer_charge,
        "internal_cost_minor": vendor_cost,
        "byok_excluded": bool(byok and customer_owned and category == "managed_model"),
    }
    return customer_charge, vendor_cost, detail


def calculate_machine_runtime(components: list[dict[str, Any]]) -> int:
    """Sum sequential groups; use max duration within the same parallel group."""
    groups: dict[str, int] = {}
    for item in components:
        group = str(item.get("parallel_group", item.get("name", "default")))
        seconds = int(item.get("seconds", 0))
        if seconds < 0:
            raise ValueError("runtime seconds must be >= 0")
        groups[group] = max(groups.get(group, 0), seconds)
    return sum(groups.values())


def calculate_quote(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("quality_mode", "balanced"))
    if mode not in QUALITY_BP:
        raise ValueError(f"unsupported quality_mode: {mode}")
    byok = bool(payload.get("byok", False))

    base_customer = int(payload.get("platform_fixed_minor", 0))
    base_internal = int(payload.get("platform_internal_cost_minor", 0))
    if base_customer < 0 or base_internal < 0:
        raise ValueError("fixed amounts must be >= 0")

    details = []
    for resource in payload.get("resources", []):
        charge, cost, detail = rate_resource(resource, byok=byok)
        base_customer += charge
        base_internal += cost
        details.append(detail)

    quality_bp = int(payload.get("quality_multiplier_basis_points", QUALITY_BP[mode]))
    p50 = scaled(base_customer, quality_bp)

    interval_bp = payload.get("interval_basis_points", DEFAULT_INTERVAL_BP)
    p80 = scaled(p50, int(interval_bp.get("p80", 11500)))
    p90 = scaled(p50, int(interval_bp.get("p90", 13000)))
    p80 = max(p50, p80)
    p90 = max(p80, p90)

    acceptance = int(payload.get("acceptance_cost_minor", 0))
    support = int(payload.get("support_cost_minor", 0))
    risk_reserve = int(payload.get("scope_risk_reserve_minor", 0))
    if min(acceptance, support, risk_reserve) < 0:
        raise ValueError("project add-ons must be >= 0")

    recommended_cap = p90 + acceptance + support + risk_reserve
    requested_cap = payload.get("requested_hard_cap_minor")
    hard_cap = recommended_cap if requested_cap is None else int(requested_cap)
    if hard_cap < p50:
        raise ValueError("requested hard cap is below P50 estimate")

    p50_runtime = calculate_machine_runtime(payload.get("runtime_components", []))
    runtime_risk_bp = int(payload.get("runtime_p90_basis_points", 18000))
    p90_runtime = max(p50_runtime, scaled(p50_runtime, runtime_risk_bp))

    currency = str(payload.get("currency", "CNY"))
    human_reference = payload.get("human_effort_reference")

    return {
        "currency": currency,
        "quality_mode": mode,
        "byok": byok,
        "estimated_cost": {
            "p50_minor": p50,
            "p80_minor": p80,
            "p90_minor": p90,
        },
        "recommended_hard_cap_minor": recommended_cap,
        "hard_cap_minor": hard_cap,
        "estimated_internal_cost_minor": base_internal,
        "machine_runtime": {
            "p50_seconds": p50_runtime,
            "p90_seconds": p90_runtime,
        },
        "human_effort_reference": human_reference,
        "resource_breakdown": details,
        "assumptions": {
            "quality_multiplier_basis_points": quality_bp,
            "interval_basis_points": interval_bp,
            "runtime_p90_basis_points": runtime_risk_bp,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Input JSON file")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = calculate_quote(json.loads(args.input.read_text(encoding="utf-8")))
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
