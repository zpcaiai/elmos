#!/usr/bin/env python3
"""Bounded local OCI concurrency qualification for hosted translation.

This is self-attested engineering evidence. It deliberately reports production
SLO, provider evidence, independent verification and certification as NOT_RUN.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import tempfile
import threading
import time
from typing import TypedDict


ROOT = Path(__file__).resolve().parents[2]
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")


class Sample(TypedDict):
    job: int
    seconds: float
    artifact_sha256: str
    artifact_bytes: int
    status: str


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def prepare_fixture(root: Path, index: int) -> tuple[Path, Path, Path]:
    input_dir = root / f"job-{index}" / "input"
    output_dir = root / f"job-{index}" / "output"
    temporary_dir = root / f"job-{index}" / "temporary"
    (input_dir / "source" / "src").mkdir(parents=True)
    (input_dir / "cases").mkdir()
    output_dir.mkdir()
    temporary_dir.mkdir()
    os.chmod(output_dir, 0o777)
    os.chmod(temporary_dir, 0o777)
    (input_dir / "source" / "src" / "math.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left + right\n",
        encoding="utf-8",
    )
    (input_dir / "cases" / "WU-00001.json").write_text(
        json.dumps([{"args": [index, 3], "expected": index + 3}]),
        encoding="utf-8",
    )
    subject = {
        "schemaVersion": "translation-input-v1",
        "tenantId": f"tenant-local-{index}",
        "actor": "local-qualification",
        "repositoryWorkspaceId": f"fixture-{index}",
        "repositoryRef": f"local:hosted-translation-{index}",
        "sourceCommit": f"{index + 1:040x}",
        "sourceLanguage": "python",
        "targetLanguage": "typescript",
        "casesBundleId": f"cases-{index}",
    }
    (input_dir / "manifest.json").write_text(
        json.dumps(subject, sort_keys=True), encoding="utf-8"
    )
    (input_dir / "request.json").write_text(
        json.dumps({**subject, "input": {"sha256": f"{index + 1:064x}"}}, sort_keys=True),
        encoding="utf-8",
    )
    return input_dir, output_dir, temporary_dir


def run_phase(
    docker_command: list[str],
    image_id: str,
    phase: str,
    input_dir: Path,
    output_dir: Path,
    temporary_dir: Path,
    timeout_seconds: int,
) -> None:
    command = [
        *docker_command, "run", "--rm", "--read-only", "--network", "none",
        "--cpus", "2", "--memory", "2g", "--pids-limit", "256",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "10001:10001",
        "--mount", f"type=bind,src={input_dir},dst=/elmos/input,readonly",
        "--mount", f"type=bind,src={output_dir},dst=/elmos/output",
        "--mount", f"type=bind,src={temporary_dir},dst=/elmos/tmp",
        "--env", f"ELMOS_JOB_KIND={phase}",
        "--env", "ELMOS_INPUT_DIR=/elmos/input",
        "--env", "ELMOS_OUTPUT_DIR=/elmos/output",
        image_id,
    ]
    subprocess.run(command, check=True, timeout=timeout_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--docker-context",
        help="explicit Docker context; omission uses the caller's current context",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not IMAGE_ID.fullmatch(args.image_id):
        parser.error("--image-id must be an immutable sha256 image id")
    if not 1 <= args.jobs <= 16 or not 1 <= args.concurrency <= 4:
        parser.error("bounded profile requires jobs=1..16 and concurrency=1..4")
    if not 60 <= args.timeout_seconds <= 3600:
        parser.error("timeout must be 60..3600 seconds")

    docker_command = ["docker"]
    if args.docker_context:
        docker_command.extend(["--context", args.docker_context])
    runtime = subprocess.run(
        [*docker_command, "version", "--format", "{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}"],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout.strip()
    inspect = json.loads(subprocess.run(
        [*docker_command, "image", "inspect", args.image_id], capture_output=True,
        text=True, check=True, timeout=30,
    ).stdout)[0]
    exact_id = inspect["Id"]
    if exact_id != args.image_id:
        raise RuntimeError("container image identity changed during admission")

    lock = threading.Lock()
    active = 0
    maximum_active = 0
    samples: list[Sample] = []
    with tempfile.TemporaryDirectory(prefix="elmos-hosted-translation-") as directory:
        root = Path(directory).resolve()
        fixtures = [prepare_fixture(root, index) for index in range(args.jobs)]

        def execute(index: int) -> Sample:
            nonlocal active, maximum_active
            input_dir, output_dir, temporary_dir = fixtures[index]
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            started = time.perf_counter()
            try:
                run_phase(docker_command, args.image_id, "translate-preflight-v1", input_dir,
                          output_dir, temporary_dir, args.timeout_seconds)
                run_phase(docker_command, args.image_id, "translate-pipeline-v1", input_dir,
                          output_dir, temporary_dir, args.timeout_seconds)
                result_path = output_dir / "gate" / "translation-job.json"
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if result.get("status") != "COMPLETE" or not result.get("artifactReady"):
                    raise RuntimeError("translation fixture did not produce a complete artifact")
                if result.get("certificationStatus") != "NOT_CERTIFIED":
                    raise RuntimeError("local fixture attempted to claim certification")
                if result.get("independentVerification") != "NOT_RUN":
                    raise RuntimeError("local fixture attempted to claim independent evidence")
                artifact_sha256 = result.get("artifactSha256")
                artifact_bytes = result.get("artifactSize")
                if (
                    not isinstance(artifact_sha256, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256)
                    or type(artifact_bytes) is not int
                    or artifact_bytes <= 0
                ):
                    raise RuntimeError("translation fixture returned an invalid artifact identity")
                return {
                    "job": index,
                    "seconds": time.perf_counter() - started,
                    "artifact_sha256": artifact_sha256,
                    "artifact_bytes": artifact_bytes,
                    "status": "COMPLETE",
                }
            finally:
                with lock:
                    active -= 1

        wall_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(execute, index) for index in range(args.jobs)]
            for future in as_completed(futures):
                samples.append(future.result())
        wall_seconds = time.perf_counter() - wall_started

    seconds = [sample["seconds"] for sample in samples]
    sources = [
        Path(__file__).resolve(),
        ROOT / "apps/translation-runtime-runner/Dockerfile",
        ROOT / "apps/translation-runtime-runner/Dockerfile.qualification-base",
        ROOT / "apps/translation-runtime-runner/entrypoint.mjs",
        ROOT / "contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json",
        ROOT / "engines/polyglot-route-engine/uv.lock",
        ROOT / "apps/web-console/pnpm-lock.yaml",
    ]
    report = {
        "schema_version": "hosted-translation-container-profile-v1",
        "evidence": "LOCAL_EXECUTED_SELF_ATTESTED",
        "production_slo": "NOT_RUN",
        "representative_production_environment": "NOT_RUN",
        "provider_evidence": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "host": platform.platform(),
        "docker_runtime": runtime,
        "docker_context": args.docker_context or "CURRENT",
        "image_id": exact_id,
        "image_repo_digests": inspect.get("RepoDigests") or [],
        "jobs": args.jobs,
        "requested_concurrency": args.concurrency,
        "observed_maximum_active": maximum_active,
        "container_policy": {
            "rootless_uid": 10001,
            "read_only_root": True,
            "network": "none",
            "capabilities": "ALL_DROPPED",
            "no_new_privileges": True,
            "memory_bytes": 2 * 1024 * 1024 * 1024,
            "cpus_per_job": 2,
            "pids_limit": 256,
        },
        "wall_seconds": wall_seconds,
        "throughput_jobs_per_second": args.jobs / wall_seconds,
        "latency_seconds": {
            "median": statistics.median(seconds),
            "p95_nearest_rank": percentile(seconds, 0.95),
            "maximum": max(seconds),
        },
        "samples": sorted(samples, key=lambda sample: sample["job"]),
        "source_sha256": {
            str(path.relative_to(ROOT)): sha256(path) for path in sources
        },
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
