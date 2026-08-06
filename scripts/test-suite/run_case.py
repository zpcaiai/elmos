#!/usr/bin/env python3
"""Execute strict-suite cases for real and emit schema-conforming evidence.

For each case this runner:
  1. freezes the artifact under test and records its digest,
  2. records the execution environment and binds its digest,
  3. runs every declared step and captures the raw combined log,
  4. writes an evidence manifest whose file digests are computed from the
     bytes actually written, and
  5. writes the case result with a status derived from what happened.

A case only reaches `passed` when every step met its declared expectation AND
an independent verifier identity was supplied. Without a verifier the runner
writes `blocked`, because the strict profile forbids self-approved results.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    load_json,
    sha256_file,
    sha256_json,
    validate_evidence_manifest_shape,
    validate_result_shape,
)

REPO = Path(__file__).resolve().parents[2]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or "unknown"


def git_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, check=False
    )
    return bool(result.stdout.strip())


def build_artifact_manifest(scope: list[str]) -> dict:
    entries = []
    for pattern in scope:
        for path in sorted(REPO.glob(pattern)):
            if path.is_file():
                entries.append(
                    {
                        "path": path.relative_to(REPO).as_posix(),
                        "sha256": sha256_file(path),
                        "bytes": path.stat().st_size,
                    }
                )
    return {
        "artifact_manifest_version": 1,
        "scope": scope,
        "file_count": len(entries),
        "files": entries,
    }


def build_environment_manifest() -> dict:
    return {
        "environment_manifest_version": 1,
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "repository_commit": git_commit(),
        "repository_dirty": git_dirty(),
        "locale": os.environ.get("LANG", ""),
        "timezone": "UTC",
        "network": "not-required",
    }


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def evidence_entry(role: str, path: Path, base: Path) -> dict:
    return {
        "role": role,
        "path": path.relative_to(base).as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "immutable": True,
    }


def run_case(
    case: dict,
    binding: dict,
    suite: Path,
    bindings: dict,
    args: argparse.Namespace,
) -> dict:
    case_id = case["id"]
    run_dir = suite / "evidence" / case_id / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = now_iso()

    log_lines = [f"# case {case_id}", f"# started_at {started}", f"# run_id {args.run_id}", ""]
    step_results = []
    for step in binding["steps"]:
        command = step["command"]
        log_lines.append(f"$ {' '.join(command)}")
        completed = subprocess.run(command, cwd=REPO, capture_output=True, text=True, check=False)
        log_lines.append(completed.stdout.rstrip())
        if completed.stderr.strip():
            log_lines.append("--- stderr ---")
            log_lines.append(completed.stderr.rstrip())
        expect = step.get("expect", "exit-zero")
        met = completed.returncode == 0 if expect == "exit-zero" else completed.returncode != 0
        log_lines.append(f"# exit={completed.returncode} expect={expect} met={met}\n")
        step_results.append(
            {
                "id": step["id"],
                "command": command,
                "expect": expect,
                "exit_code": completed.returncode,
                "met_expectation": met,
            }
        )
    finished = now_iso()
    all_met = all(step["met_expectation"] for step in step_results)

    raw_log = run_dir / "raw-log.txt"
    raw_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    artifact_file = write_json(run_dir / "artifact-manifest.json", build_artifact_manifest(bindings["artifact_scope"]))
    artifact_digest = "sha256:" + sha256_file(artifact_file)

    environment_file = write_json(run_dir / "environment-manifest.json", build_environment_manifest())
    binding_file = write_json(
        run_dir / "environment-binding.json",
        {
            "environment_binding_version": 1,
            "environment_manifest": "environment-manifest.json",
            "environment_manifest_sha256": sha256_file(environment_file),
        },
    )
    environment_digest = "sha256:" + sha256_file(binding_file)

    assertions = case.get("assertions", [])
    executed_ids = {step["id"] for step in step_results if step["met_expectation"]}
    mapped = 0
    assertion_trace = []
    for index, assertion in enumerate(assertions):
        steps_for_assertion = binding.get("assertion_map", {}).get(str(index), [])
        covered = [s for s in steps_for_assertion if s in executed_ids]
        if covered:
            mapped += 1
        assertion_trace.append({"index": index, "assertion": assertion, "established_by": covered})
    source_target_trace_coverage = round(mapped / len(assertions), 4) if assertions else 0.0

    case_result_file = write_json(
        run_dir / "case-result.json",
        {
            "case_id": case_id,
            "severity": case["severity"],
            "test_type": case["test_type"],
            "steps": step_results,
            "assertion_trace": assertion_trace,
            "all_steps_met_expectation": all_met,
        },
    )

    gate_out = run_dir / "gate-decision.json"
    subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/test-suite/run_strict_test_gate.py"),
            str(suite),
            "--output",
            str(gate_out),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    files = [
        evidence_entry("raw-log", raw_log, run_dir),
        evidence_entry("artifact-digest", artifact_file, run_dir),
        evidence_entry("environment-manifest", environment_file, run_dir),
        evidence_entry("environment-binding", binding_file, run_dir),
        evidence_entry("case-result", case_result_file, run_dir),
        evidence_entry("gate-decision", gate_out, run_dir),
    ]
    required_roles = set(case.get("evidence_required", []))
    present_roles = {entry["role"] for entry in files}
    trace_coverage = round(len(required_roles & present_roles) / len(required_roles), 4) if required_roles else 0.0

    corpora = [
        {
            "kind": "development",
            "digest": "sha256:" + sha256_file(REPO / bindings["corpora"]["development"]),
        }
    ]
    if case["test_type"] in {"negative", "security"}:
        corpora.append(
            {
                "kind": "negative",
                "digest": "sha256:" + sha256_file(REPO / bindings["corpora"]["negative"]),
            }
        )

    manifest = {
        "manifest_version": 2,
        "manifest_id": f"{case_id}-{args.run_id}",
        "case_id": case_id,
        "case_digest": sha256_json(case),
        "catalog_digest": "sha256:" + sha256_file(suite / "cases/catalog.json"),
        "artifact_digest": artifact_digest,
        "environment_digest": environment_digest,
        "execution_kind": "real",
        "started_at": started,
        "finished_at": finished,
        "executor": {"id": args.executor_id, "role": "executor"},
        "authorization_refs": args.authorization_ref,
        "files": files,
        "corpora": corpora,
    }
    if args.verifier_id:
        manifest["verifier"] = {
            "id": args.verifier_id,
            "role": "independent-verifier",
            "independent": True,
            "note": args.verifier_note or "",
        }
    else:
        manifest["verification_status"] = "pending-independent-verifier"

    manifest_file = write_json(run_dir / "manifest.json", manifest)

    if not all_met:
        status = "failed"
    elif not args.verifier_id:
        status = "blocked"
    else:
        status = "passed"

    replay = (
        f"python3 scripts/test-suite/run_case.py --suite {suite.relative_to(REPO).as_posix()} "
        f"--run-id <new-run-id> --executor-id {args.executor_id} {case_id}"
    )
    result = {
        "case_id": case_id,
        "status": status,
        "artifact_digest": artifact_digest,
        "environment_digest": environment_digest,
        "started_at": started,
        "finished_at": finished,
        "execution_kind": "real",
        "replay_command": replay,
        "trace_coverage": trace_coverage,
        "source_target_trace_coverage": source_target_trace_coverage,
        "evidence": [manifest_file.relative_to(suite).as_posix()],
    }
    if status == "blocked":
        result["blocked_reason"] = (
            "execution complete and evidence collected; awaiting an independent verifier "
            "identity (rerun with --verifier-id) as required by the strict profile"
        )

    manifest_errors = validate_evidence_manifest_shape(manifest)
    if status != "passed" and not args.verifier_id:
        # A not-yet-verified run legitimately has no verifier identity. Every other
        # integrity rule still applies; only the verifier requirement is deferred.
        manifest_errors = [e for e in manifest_errors if "verifier" not in e]
    result_errors = validate_result_shape(result)
    return {
        "result": result,
        "manifest_errors": manifest_errors,
        "result_errors": result_errors,
        "run_dir": run_dir,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", help="case ids; default is every bound case")
    parser.add_argument("--suite", default="test-suites/batch1-37-strict")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--executor-id", required=True)
    parser.add_argument("--verifier-id", default="")
    parser.add_argument("--verifier-note", default="")
    parser.add_argument("--authorization-ref", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.authorization_ref:
        args.authorization_ref = ["local-development-run"]

    suite = (REPO / args.suite).resolve()
    bindings = load_json(suite / "execution-bindings.json")
    catalog = {case["id"]: case for case in load_json(suite / "cases/catalog.json")["cases"]}
    selected = args.cases or sorted(bindings["cases"])

    unknown = [c for c in selected if c not in bindings["cases"]]
    if unknown:
        print(f"no execution binding for: {unknown}", file=sys.stderr)
        return 2

    summary = []
    for case_id in selected:
        outcome = run_case(catalog[case_id], bindings["cases"][case_id], suite, bindings, args)
        result = outcome["result"]
        problems = outcome["manifest_errors"] + outcome["result_errors"]
        if problems:
            print(f"{case_id}: refusing to write, evidence is not schema-valid: {problems}", file=sys.stderr)
            return 3
        if not args.dry_run:
            write_json(suite / "results" / f"{case_id}.json", result)
        summary.append(
            f"{case_id}  {result['status']:<8} trace={result['trace_coverage']} "
            f"src-trace={result['source_target_trace_coverage']}  {outcome['run_dir'].relative_to(suite)}"
        )

    print("\n".join(summary))
    print(f"\n{len(summary)} case(s) executed; results {'NOT ' if args.dry_run else ''}written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
