#!/usr/bin/env python3
"""Bind scaffolded Batch 29 routes to exact local engines without claiming support."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROFILES: dict[str, dict[str, str]] = {
    "java": {"version": "21", "engine_path": "apps/java-engine-worker"},
    "csharp": {"version": "10.0.301", "engine_path": "engines/dotnet-engine"},
    "python": {"version": "3.14", "engine_path": "engines/python-engine"},
    "typescript": {"version": "5.9.2", "engine_path": "engines/frontend-client-engine"},
}
OWNER = "ELMOS Migration Platform"
REVIEW_DATE = "2026-10-26"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def configure(route: Path) -> dict[str, Any]:
    manifest_path = route / "route.json"
    manifest = load(manifest_path)
    source = str(manifest.get("source", {}).get("language", ""))
    target = str(manifest.get("target", {}).get("language", ""))
    if source not in PROFILES or target not in PROFILES or source == target:
        raise ValueError(f"UNSUPPORTED_ROUTE:{route.name}")
    if manifest.get("route_key") != f"{source}-to-{target}":
        raise ValueError(f"ROUTE_KEY_MISMATCH:{route.name}")

    manifest.update(
        {
            "status": "research",
            "owner": OWNER,
            "review_date": REVIEW_DATE,
            "source": {
                "language": source,
                "versions": [PROFILES[source]["version"]],
                "engine_path": PROFILES[source]["engine_path"],
            },
            "target": {
                "language": target,
                "versions": [PROFILES[target]["version"]],
                "engine_path": PROFILES[target]["engine_path"],
            },
            "profiles": {
                "semantic_profile": "psp-1.0-uir-1.0",
                "target_profile": f"{target}-{PROFILES[target]['version']}",
            },
        }
    )
    write(manifest_path, manifest)

    support_path = route / "support-matrix.json"
    support = load(support_path)
    for capability in support.get("capabilities", []):
        if capability.get("status") == "experimental":
            capability["status"] = "detected-only"
        if capability.get("status") == "detected-only":
            capability["reason"] = (
                "Shared PSP/UIR discovery exists; this directed route has no real "
                "source/target build or behavior evidence."
            )
            capability["evidence_refs"] = []
    write(support_path, support)

    evidence_path = route / "certification" / "evidence.json"
    evidence = load(evidence_path)
    evidence["execution_status"] = "NOT_RUN"
    evidence["critical_unknown_semantics"] = max(
        1, int(evidence.get("critical_unknown_semantics", 0))
    )
    evidence["notes"] = [
        "Research inventory only; no development, negative, holdout, or representative workload executed.",
        "All target build, behavior equivalence, economics, and independent verification evidence is NOT_RUN.",
    ]
    write(evidence_path, evidence)

    certification_path = route / "certification" / "certification.json"
    certification = load(certification_path)
    certification["status"] = "NOT_CERTIFIED"
    certification["gate_results"] = {"external_execution": "NOT_RUN"}
    certification["evidence_refs"] = []
    write(certification_path, certification)

    readme = (
        f"# {source} to {target}\n\n"
        "Directional Batch 29 research route. The reverse direction is a separate route.\n\n"
        f"- Source: {source} {PROFILES[source]['version']} via `{PROFILES[source]['engine_path']}`\n"
        f"- Target: {target} {PROFILES[target]['version']} via `{PROFILES[target]['engine_path']}`\n"
        "- Status: `research`; execution `NOT_RUN`; certification `NOT_CERTIFIED`\n"
        "- Boundary: shared PSP/UIR/lowering code is discovery infrastructure, not route support evidence.\n\n"
        "Validate the structural contract with:\n\n"
        f"`python3 scripts/batch29/validate_route.py routes/{route.name}`\n\n"
        "Only the Batch 29 route certification gate may raise the status after real source and target "
        "builds, behavior comparison, independent holdout, representative workloads, traceability, "
        "economics, and review evidence exist.\n"
    )
    (route / "README.md").write_text(readme, encoding="utf-8")
    return {
        "route_key": route.name,
        "source": source,
        "source_version": PROFILES[source]["version"],
        "target": target,
        "target_version": PROFILES[target]["version"],
        "status": "research",
        "execution_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes-root", type=Path, default=Path("routes"))
    args = parser.parse_args()
    root = args.routes_root.resolve()
    configured = [
        configure(path)
        for path in sorted(root.iterdir())
        if path.is_dir() and (path / "route.json").is_file()
    ]
    if len(configured) != 12:
        raise ValueError(f"EXPECTED_12_DIRECTED_ROUTES_FOUND:{len(configured)}")
    inventory = {
        "schema_version": "1.0.0",
        "languages": {
            language: {
                "version": profile["version"],
                "engine_path": profile["engine_path"],
            }
            for language, profile in sorted(PROFILES.items())
        },
        "route_count": len(configured),
        "supported_route_count": 0,
        "certified_route_count": 0,
        "external_execution_evidence": "NOT_RUN",
        "routes": configured,
    }
    write(root / "inventory.json", inventory)
    print(f"CONFIGURED: {len(configured)} research routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
