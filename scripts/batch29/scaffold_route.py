#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from route_sets import EVIDENCED_ROUTE_KEYS, SUPPORTED_ROUTE_LANGUAGES

LANGUAGES = set(SUPPORTED_ROUTE_LANGUAGES)


def main() -> int:
    p = argparse.ArgumentParser(description="Scaffold a directed Batch 29 route package.")
    p.add_argument("--source", required=True, choices=sorted(LANGUAGES))
    p.add_argument("--target", required=True, choices=sorted(LANGUAGES))
    p.add_argument("--repo-root", default=".")
    p.add_argument(
        "--force",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    a = p.parse_args()
    if a.force:
        p.error(
            "--force is disabled: existing route packs are immutable; use the "
            "canonical inventory synchronizer for governed metadata updates"
        )
    if a.source == a.target:
        p.error("source and target must differ")
    root = Path(a.repo_root).resolve()
    route_key = f"{a.source}-to-{a.target}"
    if route_key not in EVIDENCED_ROUTE_KEYS:
        p.error("route is outside the approved explicit thirteen-language directed matrix")
    routes_root = root / "routes"
    if routes_root.exists() or routes_root.is_symlink():
        metadata = routes_root.lstat()
        if routes_root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            p.error("routes root must be a real in-repository directory")
    else:
        routes_root.mkdir(mode=0o755, parents=True)
    if routes_root.resolve(strict=True).parent != root:
        p.error("routes root escapes the resolved repository root")
    route = routes_root / route_key
    if route.exists() or route.is_symlink():
        print(f"EXISTS: {route}")
        return 0
    route.mkdir(mode=0o755, exist_ok=False)
    for rel in [
        "lowering",
        "mappings",
        "compat-runtime",
        "corpus/development/smoke",
        "corpus/development/semantic",
        "corpus/development/negative",
        "corpus/holdout",
        "corpus/real-repository",
        "certification",
    ]:
        (route / rel).mkdir(parents=True, exist_ok=True)
    template_root = root / "templates" / "batch29"
    if not template_root.exists():
        template_root = Path(__file__).resolve().parents[2] / "templates" / "batch29"
    route_data = json.loads((template_root / "route.json").read_text())
    route_data["route_key"] = route_key
    route_data["source"] = {"language": a.source, "versions": [], "engine_path": f"engines/{a.source}-engine"}
    route_data["target"] = {"language": a.target, "versions": [], "engine_path": f"engines/{a.target}-engine"}
    support = json.loads((template_root / "support-matrix.json").read_text())
    support["route_key"] = route_key
    evidence = json.loads((template_root / "evidence.json").read_text())
    evidence["route_key"] = route_key
    certification = json.loads((template_root / "certification.json").read_text())
    certification["route_key"] = route_key
    certification["status"] = route_data["status"]
    certification["certification_decision"] = "NOT_CERTIFIED"
    files = {
        route / "route.json": route_data,
        route / "support-matrix.json": support,
        route / "compat-runtime" / "manifest.json": {
            "schema_version": 1,
            "route_key": route_key,
            "components": [],
            "budget": {
                "max_components": 5,
                "max_wrapped_callable_ratio": 0.10,
                "prohibited_domains": ["authentication", "authorization", "transaction-core", "money-calculation"],
            },
        },
        route / "certification" / "evidence.json": evidence,
        route / "certification" / "certification.json": certification,
    }
    for path, data in files.items():
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path, flags, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(data, indent=2) + "\n")
    readme = route / "README.md"
    descriptor = os.open(
        readme,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o644,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(
            f"# {route_key}\n\nDirected Batch 29 migration route. Reverse direction is a separate route.\n"
        )
    print(route)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
