#!/usr/bin/env python3
"""Conservative Batch 46 runnable-smoke gate.

Only this script may state that a generated project is one-click runnable.
It refuses to derive that claim from the presence of files: there must be a
real executed run whose evidence is internally consistent with the pack that
produced it.

Status ladder (never raised by editing JSON):

    runnable     every required assertion passed in a real run, the lease
                 expired or released cleanly, teardown left no residue,
                 nothing unknown remains
    limited      the run passed but coverage is reduced — zero-dep substitution,
                 no functional endpoint, unresolved unsupported items
    blocked      anything else, including NOT_RUN

    python3 scripts/batch46/run_smoke_gate.py <project-root>
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from smoke_common import (
    SCHEMA_PREFIX,
    TRISTATE_NOT_RUN,
    TRISTATE_PASS,
    canonical_digest,
    read_json,
    smoke_dir,
    utc_now,
    write_json,
)
from smoke_lease import runtime_dir

REPORT_TEMPLATE = """# Batch 46 runnable-smoke gate report

- Project: `{project}`
- Status: **{status}**
- Evaluated: {evaluated}
- Entry executed: `{entry}`
- Required checks passed: {passed}/{total}
- Lease: free quota {quota}s, granted {ttl}s, billable {billable}s, ended `{end_reason}`

## Failures

{failures}

## Limitations

{limitations}

## Scope

A `runnable` status means the project starts from a clean checkout with one
command, serves at least one request against disposable seed data, and is fully
reclaimed when the runtime lease expires. It is not evidence of route, framework,
database, client, performance, security or certification quality.
"""


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- none"


def evaluate(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    smoke = smoke_dir(root)
    failures: list[str] = []
    limitations: list[str] = []

    validator = Path(__file__).resolve().parent / "validate_smoke_pack.py"
    completed = subprocess.run([sys.executable, str(validator), str(root)], capture_output=True, text=True)
    if completed.returncode != 0:
        failures.append("structural validation failed: " + completed.stdout.strip().replace("\n", " | "))

    result_path = runtime_dir(root) / "result.json"
    if not result_path.is_file():
        failures.append("no executed smoke result; the gate never infers runnability from files alone")
        result: dict[str, Any] = {}
    else:
        result = read_json(result_path)

    pack = read_json(smoke / "pack.json") if (smoke / "pack.json").is_file() else {}
    runner = read_json(smoke / "runner-manifest.json") if (smoke / "runner-manifest.json").is_file() else {}
    seed_manifest = read_json(smoke / "seed-manifest.json") if (smoke / "seed-manifest.json").is_file() else {}

    if result:
        if result.get("overall") == TRISTATE_NOT_RUN:
            failures.append("recorded run is NOT_RUN; NOT_RUN never passes")
        elif result.get("overall") != TRISTATE_PASS:
            failing = [c["id"] for c in result.get("checks", []) if c["required"] and c["status"] != TRISTATE_PASS]
            failures.append(f"required assertions failed: {', '.join(failing) or 'unspecified'}")
        lease = result.get("lease", {})
        if lease.get("teardown_complete") is not True:
            failures.append("teardown did not complete; an expired lease must leave nothing behind")
        if lease.get("end_reason") not in ("expired", "completed"):
            limitations.append(f"lease ended with reason '{lease.get('end_reason')}'")
        if lease.get("billable_seconds", 0) > 0:
            limitations.append(
                f"the run was extended {lease['billable_seconds']}s beyond the free quota; "
                "extension time is metered, not free"
            )
        teardown_check = next((c for c in result.get("checks", []) if c["id"] == "lease-teardown"), None)
        if teardown_check and teardown_check.get("status") != TRISTATE_PASS:
            failures.append("lease teardown assertion did not pass")
        if result.get("entry") == "zero-dep":
            limitations.append(
                "executed through the zero-dependency entry; an embedded substitute is not the declared engine"
            )
        functional = next((c for c in result.get("checks", []) if c["id"] == "http-functional"), None)
        if not functional or functional.get("status") != TRISTATE_PASS:
            limitations.append("no contract-declared functional endpoint was exercised")
        for note in result.get("notes", []):
            limitations.append(note)
        if result.get("result_digest"):
            recomputed = canonical_digest(
                {k: v for k, v in result.items() if k not in ("generated_at", "result_digest")}
            )
            if recomputed != result["result_digest"]:
                failures.append("smoke result digest does not match its content; evidence was edited after the run")

    if runner and result:
        entry = result.get("entry")
        if runner.get("entries", {}).get(entry, {}).get("status") != "available":
            failures.append(f"result claims entry '{entry}' which the runner manifest does not mark available")

    for item in (pack.get("unknown") or []):
        failures.append(f"unresolved unknown: {item.get('item')} — {item.get('reason')}")
    for item in (pack.get("unsupported") or []):
        limitations.append(f"unsupported: {item.get('item')} — {item.get('reason')}")
    if seed_manifest.get("production_data_used"):
        failures.append("production data was used as a seed source; this is never permitted")

    if failures:
        status = "blocked"
    elif limitations:
        status = "limited"
    else:
        status = "runnable"

    lease = result.get("lease", {}) if result else {}
    gate = {
        "schema": f"{SCHEMA_PREFIX}.smoke-gate-result/1",
        "evaluated_at": utc_now(),
        "project": str(root),
        "status": status,
        "entry": result.get("entry"),
        "required_passed": result.get("required_passed", 0),
        "required_total": result.get("required_total", 0),
        "failures": failures,
        "limitations": limitations,
        "result_digest": result.get("result_digest"),
        "pack_digest": pack.get("pack_digest"),
        "lease": lease,
        "gate_version": "1.0.0",
    }
    write_json(runtime_dir(root) / "gate-result.json", gate)
    (runtime_dir(root) / "gate-report.md").write_text(
        REPORT_TEMPLATE.format(
            project=root.name,
            status=status,
            evaluated=gate["evaluated_at"],
            entry=result.get("entry") or "none",
            passed=gate["required_passed"],
            total=gate["required_total"],
            quota=lease.get("free_quota_seconds", "-"),
            ttl=lease.get("ttl_seconds", "-"),
            billable=lease.get("billable_seconds", "-"),
            end_reason=lease.get("end_reason", "-"),
            failures=_bullets(failures),
            limitations=_bullets(limitations),
        ),
        encoding="utf-8",
    )
    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the conservative Batch 46 smoke gate")
    parser.add_argument("project_root")
    args = parser.parse_args()
    gate = evaluate(Path(args.project_root))
    print(f"batch46 smoke gate: {gate['status']}")
    for failure in gate["failures"]:
        print(f"  FAIL {failure}")
    for limitation in gate["limitations"]:
        print(f"  LIMIT {limitation}")
    print("wrote smoke/runtime/gate-result.json and gate-report.md")
    return 0 if gate["status"] in ("runnable", "limited") else 1


if __name__ == "__main__":
    raise SystemExit(main())
