#!/usr/bin/env python3
"""ELMOS generation workload entrypoint.

This is the process the runner-agent starts inside the digest-pinned
generation workload container. The container contract is fixed by
``apps/runner-agent/.../ContainerRuntime.java`` and is not negotiable from
here:

* ``/elmos/in`` (read-only)  holds ``request.json`` and ``checkpoint.json``;
* ``/elmos/out`` (read-write) receives the artifacts to publish;
* ``/elmos/tmp`` (read-write) is scratch space and the working directory;
* the root filesystem is read-only, the network is disabled, and stdout
  lines of the exact form ``::elmos stage=<stage> progress=<0-100>`` are the
  only progress channel;
* exit code 0 means the engine pipeline produced a verifiable archive.

Artifact placement follows the runner-agent's role mapping
(``ArtifactPublisher.roleFor``): the project zip at the output root becomes
``PROJECT_ARCHIVE``; everything under ``evidence/`` becomes
``EVIDENCE_PACK``; ``logs/`` becomes ``BUILD_LOG``.

The payload written by ``apps/web-console/.../hostedExecutionClient.ts``
carries the same synthesis request the local runner persists as
``synthesis-request.json``, so a hosted job and a local job execute the
identical engine pipeline with identical inputs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

INPUT_DIR = Path(os.environ.get("ELMOS_INPUT_DIR", "/elmos/in"))
OUTPUT_DIR = Path(os.environ.get("ELMOS_OUTPUT_DIR", "/elmos/out"))
WORK_DIR = Path(os.environ.get("ELMOS_WORKLOAD_WORK_DIR", "/elmos/tmp"))

EXIT_REQUEST_INVALID = 2
EXIT_PIPELINE_FAILED = 4
EXIT_RESULT_INVALID = 5
EXIT_ARTIFACT_INVALID = 6

_MAX_ACTOR_LENGTH = 200


def emit(stage: str, progress: int) -> None:
    """Reports one progress line. Runner-agent ignores everything else."""
    sys.stdout.write(f"::elmos stage={stage} progress={max(0, min(100, progress))}\n")
    sys.stdout.flush()


def log(message: str) -> None:
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


def load_payload() -> dict:
    request_path = INPUT_DIR / "request.json"
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        log(f"WORKLOAD_REQUEST_UNREADABLE: {error}")
        raise SystemExit(EXIT_REQUEST_INVALID) from error
    if not isinstance(payload, dict):
        log("WORKLOAD_REQUEST_INVALID: payload is not an object")
        raise SystemExit(EXIT_REQUEST_INVALID)

    actor = payload.get("actor")
    synthesis_request = payload.get("synthesisRequest")
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or len(actor) > _MAX_ACTOR_LENGTH
    ):
        log("WORKLOAD_REQUEST_INVALID: actor missing or malformed")
        raise SystemExit(EXIT_REQUEST_INVALID)
    if not isinstance(synthesis_request, dict) or not synthesis_request:
        log("WORKLOAD_REQUEST_INVALID: synthesisRequest missing")
        raise SystemExit(EXIT_REQUEST_INVALID)
    return payload


def run_pipeline(request_path: Path, actor: str) -> tuple[int, str, str]:
    """Runs the engine pipeline; stdout is the machine-readable result JSON."""
    emit("pipeline", 10)
    workspace = WORK_DIR / "workspace"
    evidence = WORK_DIR / "verification.json"
    archive = WORK_DIR / "generated-project.zip"
    for stale in (workspace, evidence, archive):
        if stale.is_dir():
            shutil.rmtree(stale)
        elif stale.exists():
            stale.unlink()
    command = [
        sys.executable,
        "-m",
        "elmos_project_synthesis.cli",
        "pipeline",
        "--request",
        str(request_path),
        "--actor",
        actor,
        "--output",
        str(workspace),
        "--evidence",
        str(evidence),
        "--archive",
        str(archive),
    ]
    completed = subprocess.run(  # noqa: S603 - fixed interpreter, repository-owned engine module.
        command,
        cwd=str(WORK_DIR),
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout, completed.stderr


def parse_result(stdout: str) -> dict:
    """Parses the pipeline result document from stdout."""
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as error:
        log(f"WORKLOAD_RESULT_UNPARSEABLE: {error}")
        raise SystemExit(EXIT_RESULT_INVALID) from error
    if not isinstance(result, dict):
        log("WORKLOAD_RESULT_INVALID: result is not an object")
        raise SystemExit(EXIT_RESULT_INVALID)
    return result


def publish_artifacts(result: dict, pipeline_log: str) -> None:
    """Copies the evidence-bounded artifact set into the output directory."""
    emit("archiving", 90)
    evidence_dir = OUTPUT_DIR / "evidence"
    logs_dir = OUTPUT_DIR / "logs"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    archive = WORK_DIR / "generated-project.zip"
    if not archive.is_file() or archive.stat().st_size <= 0:
        log("WORKLOAD_ARCHIVE_MISSING")
        raise SystemExit(EXIT_ARTIFACT_INVALID)
    shutil.copy2(archive, OUTPUT_DIR / "generated-project.zip")

    verification = WORK_DIR / "verification.json"
    if verification.is_file():
        shutil.copy2(verification, evidence_dir / "verification.json")

    insights = WORK_DIR / "workspace" / "requirements" / "project-insights.json"
    if insights.is_file():
        shutil.copy2(insights, evidence_dir / "project-insights.json")

    (evidence_dir / "pipeline-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (logs_dir / "pipeline.log").write_text(pipeline_log, encoding="utf-8")


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = load_payload()
    actor = str(payload["actor"])
    request_path = WORK_DIR / "synthesis-request.json"
    request_path.write_text(
        json.dumps(payload["synthesisRequest"], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    log(
        "generation workload: job_kind="
        f"{json.dumps(os.environ.get('ELMOS_JOB_KIND', 'project-synthesis'))}"
    )

    checkpoint = INPUT_DIR / "checkpoint.json"
    if checkpoint.is_file():
        # The pipeline is deterministic and rebuilds its workspace from the
        # request, so a retry cursor never changes what this workload does -
        # it only documents that this attempt is not the first.
        log("generation workload: retry checkpoint observed, rerunning full pipeline")

    exit_code, stdout, stderr = run_pipeline(request_path, actor)
    pipeline_log = (
        "--- engine stderr ---\n"
        f"{stderr}"
        "--- engine result ---\n"
        f"{stdout}"
    )
    if exit_code != 0:
        emit("blocked", 100)
        log(f"WORKLOAD_PIPELINE_FAILED: exit {exit_code}")
        (OUTPUT_DIR / "logs").mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "logs" / "pipeline.log").write_text(pipeline_log, encoding="utf-8")
        return EXIT_PIPELINE_FAILED

    result = parse_result(stdout)
    status = result.get("status")
    if status not in ("PASSED", "PARTIAL"):
        # The local runner accepts exactly PASSED and PARTIAL as terminal
        # success states; anything else must never exit 0 here.
        log(f"WORKLOAD_RESULT_REJECTED: status {status!r}")
        emit("blocked", 100)
        return EXIT_RESULT_INVALID

    publish_artifacts(result, pipeline_log)
    emit("complete", 100)
    log(f"generation workload: pipeline {status}")
    return 0


def self_check() -> int:
    """Build-time integrity probe: the image must contain a runnable engine."""
    from elmos_project_synthesis import cli  # noqa: F401  (import is the check)

    print(f"elmos generation workload self-check ok: {cli.__name__}")
    return 0


if __name__ == "__main__":
    if "--self-check" in sys.argv[1:]:
        raise SystemExit(self_check())
    raise SystemExit(main())
