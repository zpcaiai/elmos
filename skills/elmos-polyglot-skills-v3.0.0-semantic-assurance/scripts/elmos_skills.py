#!/usr/bin/env python3
"""ELMOS Polyglot Skills inspection, routing, scaffolding, and validation CLI."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def command_validate(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    from validate_bundle import validate_bundle  # type: ignore
    result = validate_bundle(ROOT, args.skills_root)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    else:
        for item in result.checks:
            print(f"PASS: {item}")
        for item in result.warnings:
            print(f"WARN: {item}")
        for item in result.errors:
            print(f"FAIL: {item}", file=sys.stderr)
        print(f"RESULT: {'PASS' if result.passed else 'FAIL'}")
    return 0 if result.passed else 1


def command_list_skills(args: argparse.Namespace) -> int:
    skills = load_json("manifest.json")["skills"]
    if args.batch:
        skills = [s for s in skills if s["batch"] == args.batch]
    if args.layer:
        skills = [s for s in skills if s["layer"] == args.layer]
    if args.json:
        print(json.dumps(skills, indent=2, ensure_ascii=False))
        return 0
    for skill in skills:
        deps = ",".join(skill["dependencies"]) if skill["dependencies"] else "-"
        print(f"{skill['id']}  {skill['name']:<48} batch={skill['batch']} layer={skill['layer']} deps={deps}")
    print(f"\n{len(skills)} Skill(s)")
    return 0


def command_technologies(args: argparse.Namespace) -> int:
    entries = load_json("technology-registry.json")["spec"]["technologies"]
    if args.json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0
    print("ID          KIND       DISPLAY          ADAPTER")
    print("-" * 86)
    for tech in entries:
        print(f"{tech['id']:<11} {tech['kind']:<10} {tech['display']:<16} {tech['adapter_skill']}")
    return 0


def matrix_rows() -> list[dict[str, str]]:
    with (ROOT / "route-matrix.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def command_routes(args: argparse.Namespace) -> int:
    rows = matrix_rows()
    if args.source:
        rows = [r for r in rows if r["source"] == args.source]
    if args.target:
        rows = [r for r in rows if r["target"] == args.target]
    if args.reference_only:
        rows = [r for r in rows if r["reference_profile"]]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    for row in rows:
        profile = row["reference_profile"] or "-"
        print(f"{row['source']:<11} -> {row['target']:<11} mode={row['route_mode']:<28} tier={row['support_tier']:<9} profile={profile}")
    print(f"\n{len(rows)} route cell(s)")
    return 0


def known_technology(value: str) -> str:
    ids = load_json("manifest.json")["technologies"]
    if value not in ids:
        raise argparse.ArgumentTypeError(f"unknown technology {value!r}; choose one of {', '.join(ids)}")
    return value


def find_route(source: str, target: str) -> dict[str, Any]:
    rows = [r for r in matrix_rows() if r["source"] == source and r["target"] == target]
    if len(rows) != 1:
        raise RuntimeError(f"route matrix invariant failed for {source}->{target}")
    row = rows[0]
    profiles = load_json("route-registry.json")["spec"]["profiles"]
    profile = next((p for p in profiles if p["id"] == row["reference_profile"]), None)
    return {"matrix": row, "profile": profile}


def command_route(args: argparse.Namespace) -> int:
    route = find_route(args.source, args.target)
    if args.json:
        print(json.dumps(route, indent=2, ensure_ascii=False))
        return 0
    row = route["matrix"]
    print(f"Source: {row['source']}")
    print(f"Target: {row['target']}")
    print(f"Mode: {row['route_mode']}")
    print(f"Support tier: {row['support_tier']}")
    print(f"Readiness: {row['readiness']}")
    if route["profile"]:
        print(f"Reference profile: {route['profile']['id']}")
        print(f"Profile file: {route['profile']['profile']}")
    else:
        print("Reference profile: none; create a route-specific profile before implementation-grade claims.")
    print("\nRequired shared entry Skill: elmos-polyglot-modernization-orchestrator")
    return 0


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def command_scaffold_job(args: argparse.Namespace) -> int:
    route = find_route(args.source, args.target)
    profile = route["profile"]["id"] if route["profile"] else ""
    content = f"""schemaVersion: elmos.migration-job/v1
jobId: {yaml_quote(args.job_id)}
mode: {args.mode}
source:
  technology: {args.source}
  location: {yaml_quote(args.source_location)}
  revision: REPLACE-WITH-IMMUTABLE-REVISION
target:
  technology: {args.target}
  profile: {yaml_quote(args.target_profile)}
routeProfile: {yaml_quote(profile)}
scope:
  include:
    - "**"
  exclude:
    - vendor/**
    - generated/**
policy:
  network:
    default: deny
    allow: []
  secrets:
    mode: runtime-handles-only
    allowedNames: []
  approvals:
    requiredFor:
      - production-write
      - irreversible-data-change
      - cryptographic-change
  budgets:
    wallTimeMinutes: {args.wall_time}
    cpu: "4"
    memoryMiB: 8192
    diskMiB: 20480
    maxPatchLines: 5000
readiness: not-run
"""
    output = args.output.resolve()
    if output.exists() and not args.force:
        print(f"refusing to overwrite {output}; use --force", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(output)
    return 0


def command_scaffold_project(args: argparse.Namespace) -> int:
    source = ROOT / "templates" / "project-generation-spec.yaml"
    output = args.output.resolve()
    if output.exists() and not args.force:
        print(f"refusing to overwrite {output}; use --force", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate the bundle")
    p.add_argument("--json", action="store_true")
    p.add_argument("--skills-root", type=Path)
    p.set_defaults(func=command_validate)

    p = sub.add_parser("list-skills", help="list Skills")
    p.add_argument("--batch", choices=["A", "B", "C", "D"])
    p.add_argument("--layer")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_list_skills)

    p = sub.add_parser("technologies", help="list technology adapters")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_technologies)

    p = sub.add_parser("routes", help="list route matrix cells")
    p.add_argument("--source", type=known_technology)
    p.add_argument("--target", type=known_technology)
    p.add_argument("--reference-only", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_routes)

    p = sub.add_parser("route", help="inspect one ordered route")
    p.add_argument("--source", required=True, type=known_technology)
    p.add_argument("--target", required=True, type=known_technology)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=command_route)

    p = sub.add_parser("scaffold-job", help="create a migration job")
    p.add_argument("--source", required=True, type=known_technology)
    p.add_argument("--target", required=True, type=known_technology)
    p.add_argument("--mode", choices=["generate-project", "modernize", "convert", "interop"], default="convert")
    p.add_argument("--job-id", default="REPLACE-ME")
    p.add_argument("--source-location", default="/absolute/path/or/repository-reference")
    p.add_argument("--target-profile", default="target-profile.yaml")
    p.add_argument("--wall-time", type=int, default=120)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=command_scaffold_job)

    p = sub.add_parser("scaffold-project-spec", help="copy a project-generation specification template")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=command_scaffold_project)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
