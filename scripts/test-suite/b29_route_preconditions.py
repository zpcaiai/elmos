#!/usr/bin/env python3
"""Establish the declared preconditions of the Batch 29 directed-route cases.

The catalog preconditions are "Batch 29实现与契约可定位" and "输入、版本、Owner和
环境已锁定". Two things have to hold before a route case may execute:

  1. the route contract validates and its gate runs (contract locatable), and
  2. the exact pinned toolchain for both directions is present (environment
     locked -- the route asserts 真实编译 / 版本精确, which a mismatched
     toolchain cannot establish).

Exit 0 only when both hold. Failing here means the case is blocked, not failed:
nothing about the product's correctness has been observed either way.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POLYGLOT = REPO / "engines/polyglot-route-engine"

checks: list[dict] = []


def record(name: str, ok: bool, detail: str) -> None:
    checks.append({"check": name, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'BLOCK'}] {name}: {detail}")


def run(command: list[str], cwd: Path = REPO) -> tuple[int, str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def check_contract(route_dir: Path) -> dict:
    route_json = route_dir / "route.json"
    if not route_json.is_file():
        record("route-contract-present", False, f"{route_dir}/route.json missing")
        return {}
    route = json.loads(route_json.read_text(encoding="utf-8"))
    record(
        "route-contract-present",
        True,
        f"route_key={route.get('route_key')} status={route.get('status')} "
        f"profile={route.get('profiles', {}).get('semantic_profile')}",
    )
    code, output = run([sys.executable, "scripts/batch29/validate_route.py", str(route_dir.relative_to(REPO))])
    record("route-contract-validates", code == 0, output.splitlines()[-1] if output else f"exit={code}")
    code, output = run([sys.executable, "scripts/batch29/run_route_gate.py", str(route_dir.relative_to(REPO))])
    record("route-gate-runs", code == 0, output.splitlines()[-1] if output else f"exit={code}")

    corpus_root = route_dir / "corpus"
    present = sorted(p.name for p in corpus_root.iterdir() if p.is_dir()) if corpus_root.is_dir() else []
    record(
        "route-corpora-present",
        {"development", "holdout", "real-repository"} <= set(present),
        f"corpora on disk: {present}",
    )
    return route


def check_toolchain(route: dict) -> None:
    languages = [route.get("source", {}).get("language"), route.get("target", {}).get("language")]
    for language in [l for l in languages if l]:
        probe = (
            "import sys; sys.path.insert(0, 'src')\n"
            "from elmos_polyglot_route import toolchains\n"
            "from elmos_polyglot_route.models import RouteError\n"
            f"fn = getattr(toolchains, '_{language}')\n"
            "try:\n"
            "    tc = fn()\n"
            "    print('OK', tc.version)\n"
            "except RouteError as exc:\n"
            "    print('REFUSED', exc)\n"
        )
        code, output = run([sys.executable, "-c", probe], cwd=POLYGLOT)
        last = output.splitlines()[-1] if output else f"exit={code}"
        record(f"exact-toolchain::{language}", last.startswith("OK"), last)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", default="routes/java-to-csharp")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    route_dir = REPO / args.route
    print(f"=== Batch 29 route preconditions: {args.route} ===\n")
    route = check_contract(route_dir)
    if route:
        check_toolchain(route)

    blocked = [c for c in checks if not c["ok"]]
    print(f"\n{len(checks) - len(blocked)}/{len(checks)} preconditions hold")
    for item in blocked:
        print(f"  BLOCKED BY {item['check']}")
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {"route": args.route, "preconditions_met": not blocked,
                 "checks_total": len(checks), "blocked_by": [c["check"] for c in blocked],
                 "checks": checks},
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"report written to {args.report}")
    return 0 if not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
