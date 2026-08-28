from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from .io import iter_cases


def feature_coverage_report(root: Path) -> dict[str, Any]:
    registry = yaml.safe_load((root / "matrices/feature-registry.yaml").read_text(encoding="utf-8"))
    full = yaml.safe_load((root / "matrices/full-product.yaml").read_text(encoding="utf-8"))
    expected_per_feature: dict[str, int] = {}
    adapter_by_domain: dict[str, str] = {}
    for domain in full["domains"]:
        adapter_by_domain[domain["id"]] = domain["adapter"]
        expected = len(domain["contexts"]) * len(full["variants"])
        for capability in domain["capabilities"]:
            expected_per_feature[f"{domain['id']}.{capability['id']}"] = expected

    case_counts: Counter[str] = Counter()
    adapters: dict[str, set[str]] = defaultdict(set)
    variants: dict[str, set[str]] = defaultdict(set)
    contexts: dict[str, set[str]] = defaultdict(set)
    for case in iter_cases(root):
        capability_id = case.get("coverage", {}).get("capability_id", "")
        if not capability_id.startswith("FP."):
            continue
        feature_id = capability_id[3:]
        # Smoke capabilities intentionally do not exist in the formal feature registry.
        if feature_id.endswith(".smoke"):
            continue
        case_counts[feature_id] += 1
        adapters[feature_id].add(case.get("execution", {}).get("adapter", ""))
        dims = case.get("coverage", {}).get("dimensions", {})
        variants[feature_id].add(str(dims.get("variant", "")))
        contexts[feature_id].add(str(dims.get("context", "")))

    errors: list[str] = []
    warnings: list[str] = []
    by_domain: Counter[str] = Counter()
    binding_rows: list[dict[str, Any]] = []
    registry_ids: set[str] = set()
    for feature in registry["features"]:
        feature_id = feature["feature_id"]
        registry_ids.add(feature_id)
        by_domain[feature["domain"]] += 1
        expected = expected_per_feature.get(feature_id)
        actual = case_counts.get(feature_id, 0)
        expected_adapter = feature["required_adapter"]
        actual_adapters = sorted(a for a in adapters.get(feature_id, set()) if a)
        if expected is None:
            errors.append(f"feature missing from full-product matrix: {feature_id}")
        elif actual != expected:
            errors.append(f"feature case count mismatch {feature_id}: expected {expected}, got {actual}")
        if actual_adapters != [expected_adapter]:
            errors.append(
                f"feature adapter mismatch {feature_id}: expected {expected_adapter}, got {actual_adapters}"
            )
        if feature["priority"] == "P0":
            required_variants = {"nominal", "boundary", "negative-security", "concurrent-recovery"}
            missing_variants = required_variants - variants.get(feature_id, set())
            if missing_variants:
                errors.append(f"P0 feature missing variants {feature_id}: {sorted(missing_variants)}")
        binding_rows.append(
            {
                "feature_id": feature_id,
                "domain": feature["domain"],
                "priority": feature["priority"],
                "expected_cases": expected or 0,
                "actual_cases": actual,
                "adapter": expected_adapter,
                "variants": sorted(v for v in variants.get(feature_id, set()) if v),
                "contexts": sorted(c for c in contexts.get(feature_id, set()) if c),
            }
        )

    unexpected = sorted(set(case_counts) - registry_ids)
    if unexpected:
        errors.extend(f"case capability not in feature registry: {item}" for item in unexpected[:25])
    declared_domain_adapters = {item["id"]: item["adapter"] for item in full["domains"]}
    for domain, adapter in adapter_by_domain.items():
        if declared_domain_adapters.get(domain) != adapter:
            errors.append(f"domain adapter drift: {domain}")

    total_expected = sum(row["expected_cases"] for row in binding_rows)
    total_actual = sum(row["actual_cases"] for row in binding_rows)
    return {
        "schema_version": "2.0",
        "registry_id": registry["registry_id"],
        "complete": not errors,
        "feature_count": len(registry["features"]),
        "domain_count": len(by_domain),
        "expected_case_bindings": total_expected,
        "actual_case_bindings": total_actual,
        "coverage_ratio": total_actual / total_expected if total_expected else 1.0,
        "features_by_domain": dict(sorted(by_domain.items())),
        "errors": errors,
        "warnings": warnings,
        "bindings": binding_rows,
    }
