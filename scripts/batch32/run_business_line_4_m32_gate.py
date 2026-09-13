#!/usr/bin/env python3
"""Read-only local qualification runner for Business Line 4 / Batch 32.

This command intentionally cannot certify a client route. It composes local
engine tests with the conservative, portable Batch 32 gate and reports the
strongest defensible local state. Official platform execution, independent
evidence and production certification remain the responsibility of
``run_client_gate.py`` and external truth runners.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ENGINE = REPO_ROOT / "engines" / "frontend-client-engine"
COMPONENT_ENGINE = REPO_ROOT / "engines" / "component-dialect-engine"
CONSERVATIVE_GATE = REPO_ROOT / "scripts" / "batch32" / "run_client_gate.py"
DEFAULT_PACKS = (
    "client-packs/frontend-to-miniapp-vue3-wechat-v1",
    "client-packs/web-console-next16-react19-wechat-v1",
    "client-packs/frontend-72-route-equivalence-v2",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: tuple[str, ...]
    exit_code: int
    duration_ms: int
    state: str
    output_tail: str


def run_check(name: str, command: Sequence[str], cwd: Path) -> CheckResult:
    started = time.monotonic()
    process = subprocess.run(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=900,
        check=False,
    )
    output = process.stdout or ""
    return CheckResult(
        name=name,
        command=tuple(command),
        exit_code=process.returncode,
        duration_ms=round((time.monotonic() - started) * 1000),
        state="PASSED_LOCAL" if process.returncode == 0 else "FAILED_LOCAL",
        output_tail=output[-4000:],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run read-only local Batch 32 qualification checks; never certify.",
    )
    parser.add_argument(
        "--pack",
        action="append",
        dest="packs",
        help="Repository-relative client pack path. May be repeated.",
    )
    parser.add_argument(
        "--skip-engine-tests",
        action="store_true",
        help="Run only conservative portable pack gates.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--certify", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.certify:
        print(
            "ERROR: local Business Line 4 checks cannot issue certification; "
            "use the conservative Batch 32 gate with independent evidence.",
            file=sys.stderr,
        )
        return 2

    checks: list[CheckResult] = []
    if not args.skip_engine_tests:
        checks.append(run_check("frontend-client-engine", ("pnpm", "test"), FRONTEND_ENGINE))
        checks.append(
            run_check(
                "component-dialect-engine",
                ("npm", "test", "--", "--runInBand"),
                COMPONENT_ENGINE,
            )
        )

    for relative in args.packs or DEFAULT_PACKS:
        pack = (REPO_ROOT / relative).resolve()
        try:
            pack.relative_to(REPO_ROOT)
        except ValueError:
            print(f"ERROR: pack escapes repository root: {relative}", file=sys.stderr)
            return 2
        if not pack.is_dir():
            checks.append(
                CheckResult(
                    name=f"client-gate:{relative}",
                    command=(),
                    exit_code=2,
                    duration_ms=0,
                    state="FAILED_LOCAL",
                    output_tail="pack directory does not exist",
                )
            )
            continue
        checks.append(
            run_check(
                f"client-gate:{relative}",
                (sys.executable, str(CONSERVATIVE_GATE), str(pack), "--portable"),
                REPO_ROOT,
            )
        )

    passed = all(check.exit_code == 0 for check in checks)
    result = {
        "schema_version": 1,
        "business_line": "4",
        "batch": 32,
        "purpose": "LOCAL_ENGINEERING_QUALIFICATION",
        "local_state": "PASSED_LOCAL" if passed else "FAILED_LOCAL",
        "external_evidence_state": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "writes_certification_artifacts": False,
        "checks": [asdict(check) for check in checks],
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for check in checks:
            print(f"{check.state}: {check.name} ({check.duration_ms} ms)")
            if check.exit_code != 0 and check.output_tail:
                print(check.output_tail, file=sys.stderr)
        print(
            f"LOCAL QUALIFICATION {'PASSED' if passed else 'FAILED'}; "
            "external=NOT_RUN certification=NOT_CERTIFIED"
        )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
