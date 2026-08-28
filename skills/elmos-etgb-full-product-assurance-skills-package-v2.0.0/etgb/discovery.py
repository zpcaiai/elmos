from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

SURFACE_KINDS = (
    "api_operations",
    "ui_actions",
    "commands",
    "jobs",
    "event_types",
    "webhooks",
    "feature_flags",
    "entitlements",
    "billing_meters",
    "admin_operations",
    "agent_routes",
    "artifact_formats",
    "deployment_modes",
)


def load_surface(path: Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def surface_coverage_report(root: Path, surface: dict[str, Any]) -> dict[str, Any]:
    registry = yaml.safe_load((root / "matrices/feature-registry.yaml").read_text(encoding="utf-8"))
    known = {item["feature_id"]: item for item in registry["features"]}
    errors: list[str] = []
    warnings: list[str] = []
    seen_surface_ids: set[str] = set()
    mapped_features: set[str] = set()
    by_kind: Counter[str] = Counter()
    by_domain: Counter[str] = Counter()
    entries = 0

    for kind in SURFACE_KINDS:
        values = surface.get(kind, []) or []
        if not isinstance(values, list):
            errors.append(f"surface section must be a list: {kind}")
            continue
        for index, item in enumerate(values):
            entries += 1
            by_kind[kind] += 1
            if not isinstance(item, dict):
                errors.append(f"{kind}[{index}] must be an object")
                continue
            surface_id = str(item.get("id", "")).strip()
            feature_id = str(item.get("feature_id", "")).strip()
            if not surface_id:
                errors.append(f"{kind}[{index}] missing id")
            elif surface_id in seen_surface_ids:
                errors.append(f"duplicate implemented surface id: {surface_id}")
            else:
                seen_surface_ids.add(surface_id)
            if not feature_id:
                errors.append(f"implemented surface missing feature_id: {kind}/{surface_id or index}")
                continue
            if feature_id not in known:
                errors.append(f"undeclared feature binding: {kind}/{surface_id} -> {feature_id}")
                continue
            mapped_features.add(feature_id)
            by_domain[known[feature_id]["domain"]] += 1
            if item.get("release_policy") and item["release_policy"] != known[feature_id]["release_policy"]:
                warnings.append(f"surface release policy differs from registry: {surface_id}")

    return {
        "schema_version": "2.0",
        "surface_id": surface.get("surface_id"),
        "candidate_digest": surface.get("candidate_digest"),
        "complete": not errors,
        "implemented_surface_count": entries,
        "mapped_feature_count": len(mapped_features),
        "mapping_ratio": len(mapped_features) / entries if entries else 1.0,
        "registry_feature_count": len(known),
        "by_surface_kind": dict(sorted(by_kind.items())),
        "by_domain": dict(sorted(by_domain.items())),
        "errors": errors,
        "warnings": warnings,
    }
