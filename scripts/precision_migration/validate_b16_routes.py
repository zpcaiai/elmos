#!/usr/bin/env python3
"""Validate all 30 exact B16 directed backend routes and persisted local evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LANGUAGES = ("java", "csharp", "go", "rust", "python", "typescript")


def main() -> int:
    failures: list[str] = []
    passed = 0
    for source in LANGUAGES:
        for target in LANGUAGES:
            if source == target:
                continue
            route = ROOT / "routes" / f"{source}-to-{target}"
            evidence_path = route / "certification" / "evidence.json"
            if not evidence_path.is_file():
                failures.append(f"missing evidence: {route.name}")
                continue
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            if evidence.get("execution_status") != "PASSED_LOCAL" or len(evidence.get("runs", [])) != 3:
                failures.append(f"incomplete local corpora: {route.name}")
                continue
            print(f"[{passed + len(failures) + 1}/30] validating {route.name}...", file=sys.stderr, flush=True)
            try:
                completed = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "batch29" / "run_route_gate.py"), str(route)],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                failures.append(f"gate timed out: {route.name} after 300s")
                continue
            if completed.returncode:
                failures.append(f"gate failed: {route.name}: {(completed.stderr or completed.stdout)[-500:]}")
                continue
            passed += 1
    payload = {
        "status": "PASS" if not failures and passed == 30 else "FAIL",
        "routes": 30,
        "passed": passed,
        "corpora_per_route": 3,
        "native_build_and_behavior": "PASSED_LOCAL" if passed == 30 else "INCOMPLETE",
        "independent_verification": "NOT_RUN",
        "external_certification": "NOT_RUN",
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
