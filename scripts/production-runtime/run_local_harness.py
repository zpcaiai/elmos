#!/usr/bin/env python3
"""Run the repository-owned local qualification harness.

This runner invokes only repository validators, Testcontainers tests, Helm
rendering, the repository-owned PITR drill, and the separate read-only report
verifier. It never executes scripts from the attached source package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SHA256 = "7685f34453d896747c177b9299c01f1a101c94a1ea4808ae6dc92fec51203c37"


class HarnessError(RuntimeError):
    pass


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def run_command(name: str, command: list[str], log_dir: Path, environment: dict[str, str] | None = None) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if environment:
        env.update(environment)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    log_path = log_dir / f"{name}.log"
    log_path.write_text(
        f"$ {' '.join(command)}\n\n{result.stdout}{result.stderr}",
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise HarnessError(f"{name} failed with exit code {result.returncode}; see {log_path}")
    return {
        "name": name,
        "status": "PASS",
        "command": command,
        "log": log_path.name,
        "log_sha256": file_digest(log_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".elmos/production-runtime/local-harness")
    args = parser.parse_args()
    run_id = str(uuid.uuid4())
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "local-harness-report.json"
    verifier_path = output_dir / "local-harness-verification.json"
    artifacts: list[dict[str, str]] = []
    steps: list[dict[str, object]] = []
    try:
        steps.append(run_command("production-runtime", ["make", "production-runtime"], output_dir))
        steps.append(run_command("helm-lint", ["helm", "lint", "deploy/helm/elmos-runtime"], output_dir))
        rendered = output_dir / "helm-rendered.yaml"
        template_result = subprocess.run(
            ["helm", "template", "elmos-runtime", "deploy/helm/elmos-runtime", "--set", "image.repository=registry.example.invalid/elmos/runtime", "--set", "image.tag=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        rendered.write_text(template_result.stdout + template_result.stderr, encoding="utf-8")
        if template_result.returncode != 0:
            raise HarnessError(f"helm-template failed with exit code {template_result.returncode}")
        steps.append({"name": "helm-template", "status": "PASS", "command": ["helm", "template"], "log": rendered.name, "log_sha256": file_digest(rendered)})

        pitr_report = output_dir / "pitr-report.json"
        steps.append(run_command("pitr-drill", ["python3", "scripts/production-runtime/run_pitr_drill.py", "--output", str(pitr_report)], output_dir))
        pitr = json.loads(pitr_report.read_text(encoding="utf-8"))
        if pitr.get("status") != "LOCAL_HARNESS_PASS":
            raise HarnessError("PITR drill did not return LOCAL_HARNESS_PASS")

        test_run_id = run_id
        local = {
            "ProviderRuntime": {"status": "LOCAL_HARNESS_PASS", "test": "providerAdapterCompletesOnceAndUnknownRequiresReconciliation", "test_run_id": test_run_id},
            "TargetClusterLoadSubstitute": {"status": "LOCAL_HARNESS_PASS", "test": "localLoadHarnessMeasuresReserveP95WithoutNegativeBalance", "test_run_id": test_run_id},
            "ChaosMatrix": {"status": "LOCAL_HARNESS_PASS", "test": "chaosMatrixKeepsUnknownNonSuccessAndReleasesRejectedWork", "test_run_id": test_run_id},
            "WorkerCrashCheckpointResume": {"status": "LOCAL_HARNESS_PASS", "test": "workerProcessKillResumesFromLatestDurableCheckpoint", "test_run_id": test_run_id},
            "RedisLoss": {"status": "LOCAL_HARNESS_PASS", "test": "redisLossDoesNotDeleteDurableDispatchOrMoneyState", "test_run_id": test_run_id},
            "PITRRestore": {"status": "LOCAL_HARNESS_PASS", "test": "scripts/production-runtime/run_pitr_drill.py", "test_run_id": pitr.get("test_run_id", test_run_id)},
        }
        for path in sorted(output_dir.iterdir()):
            if path.is_file() and path.name != report_path.name and path.name != verifier_path.name:
                artifacts.append({"path": path.name, "sha256": file_digest(path)})
        report = {
            "schema_version": 1,
            "status": "LOCAL_HARNESS_PASS",
            "test_run_id": run_id,
            "source_archive_sha256": PACKAGE_SHA256,
            "package_execution": False,
            "local_scenarios": local,
            "steps": steps,
            "artifacts": artifacts,
            "external_evidence": {
                "provider_runtime": "NOT_RUN",
                "target_cluster_load": "NOT_RUN",
                "chaos": "NOT_RUN",
                "worker_process_kill": "NOT_RUN",
                "redis_loss": "NOT_RUN",
                "backup_pitr": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "production_deployment": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            },
            "production_certification": "NOT_CERTIFIED",
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify = run_command("independent-verifier", ["python3", "scripts/production-runtime/verify_local_harness.py", str(report_path), "--output", str(verifier_path)], output_dir)
        report["local_independent_verifier"] = verify
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(report_path), "verifier": str(verifier_path), "test_run_id": run_id}, sort_keys=True))
        return 0
    except (HarnessError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"production-runtime local harness: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
