#!/usr/bin/env python3
"""Build (and optionally smoke-test) the ELMOS generation workload image.

Produces the digest-pinned image reference that closes the control-plane
gap ``ELMOS_RUNNER_IMAGE_NOT_CONFIGURED`` for the GENERATION business line:

    ELMOS_RUNNER_IMAGE_GENERATION=<registry>/elmos-generation-workload@sha256:<digest>

The smoke test replicates the runner-agent sandbox exactly as
``ContainerRuntime.buildCommand`` assembles it: --network=none, --read-only,
--cap-drop=ALL, --security-opt=no-new-privileges, tmpfs /tmp, non-root user,
and the /elmos/in -> /elmos/out -> /elmos/tmp layout. A fixture request is
produced by the real engine (draft -> analyze), the same way the web console
produces a synthesis request, so the smoke run proves the whole chain:
payload parsing -> pipeline -> archive -> published artifacts -> progress
protocol.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = REPOSITORY_ROOT / "engines" / "project-synthesis-engine"
WORKLOAD_DIR = ENGINE_ROOT / "workload"


def container_engine() -> str:
    for name in (os.environ.get("ELMOS_CONTAINER_ENGINE"), "docker", "podman"):
        if name and shutil.which(name):
            return name
    print("CONTAINER_ENGINE_NOT_FOUND: install docker or podman (or set ELMOS_CONTAINER_ENGINE)")
    raise SystemExit(2)


def engine_version() -> str:
    text = (ENGINE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("ENGINE_VERSION_NOT_FOUND")
    return match.group(1)


def run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )
    return completed


def build(engine: str, tag: str) -> str:
    completed = run([engine, "build", "-t", tag, str(WORKLOAD_DIR)])
    if completed.returncode != 0:
        print(completed.stdout)
        raise SystemExit(f"IMAGE_BUILD_FAILED: exit {completed.returncode}")
    identity = run([engine, "inspect", "--format", "{{.Id}}", tag])
    if identity.returncode != 0 or not identity.stdout.strip():
        raise SystemExit("IMAGE_ID_NOT_RESOLVED")
    return identity.stdout.strip()


def fixture_request(python: str) -> dict:
    """Builds a hosted payload via the real engine draft/analyze commands."""
    with tempfile.TemporaryDirectory(prefix="elmos-workload-fixture-") as scratch:
        scratch_path = Path(scratch)
        intent = {
            "schema_version": "1.1.0",
            "name": "smoke-check",
            "namespace": "elmos-smoke",
            "description": "Workload smoke fixture with one integer-keyed entity.",
            "entity": "Widget",
            "languages": ["python"],
            "project_kind": "api",
            "persistence": "in-memory",
            "auth_mode": "none",
            "business_rules": [],
            "permissions": [],
        }
        intent_path = scratch_path / "project-intent.json"
        intent_path.write_text(json.dumps(intent), encoding="utf-8")
        analysis_path = scratch_path / "analysis.json"
        completed = subprocess.run(
            [
                python,
                "-m",
                "elmos_project_synthesis.cli",
                "analyze",
                "--intent",
                str(intent_path),
                "--output",
                str(analysis_path),
            ],
            cwd=str(ENGINE_ROOT),
            env={**os.environ, "PYTHONPATH": str(ENGINE_ROOT / "src")},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stderr)
            raise SystemExit(f"FIXTURE_ANALYZE_FAILED: exit {completed.returncode}")
        synthesis_request = json.loads(analysis_path.read_text(encoding="utf-8"))
    return {
        "jobKind": "project-synthesis",
        "actor": "smoke-actor",
        "tenantId": "smoke-tenant",
        "synthesisRequest": synthesis_request,
    }


def smoke(engine: str, image_id: str, python: str) -> None:
    payload = fixture_request(python)
    with tempfile.TemporaryDirectory(prefix="elmos-workload-smoke-") as scratch:
        root = Path(scratch)
        (root / "in").mkdir()
        (root / "out").mkdir()
        (root / "tmp").mkdir()
        (root / "in" / "request.json").write_text(json.dumps(payload), encoding="utf-8")
        uid = os.getuid() if hasattr(os, "getuid") else 65532
        gid = os.getgid() if hasattr(os, "getgid") else 65532
        command = [
            engine,
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user", f"{uid}:{gid}",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=256m",
            "--volume", f"{root / 'in'}:/elmos/in:ro",
            "--volume", f"{root / 'out'}:/elmos/out:rw",
            "--volume", f"{root / 'tmp'}:/elmos/tmp:rw",
            "--workdir=/elmos/tmp",
            image_id,
        ]
        completed = run(command)
        print(completed.stdout)
        if completed.returncode != 0:
            raise SystemExit(f"SMOKE_RUN_FAILED: exit {completed.returncode}")
        archive = root / "out" / "generated-project.zip"
        evidence = root / "out" / "evidence" / "verification.json"
        if not archive.is_file() or archive.stat().st_size <= 0:
            raise SystemExit("SMOKE_ARCHIVE_MISSING")
        if not evidence.is_file():
            raise SystemExit("SMOKE_EVIDENCE_MISSING")
        if "::elmos stage=complete progress=100" not in completed.stdout:
            raise SystemExit("SMOKE_PROGRESS_PROTOCOL_MISSING")
    print("smoke: archive, evidence and progress protocol verified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=None, help="image tag (default elmos-generation-workload:<engine version>)")
    parser.add_argument("--smoke", action="store_true", help="run the image once under the runner-agent sandbox flags")
    parser.add_argument("--python", default=sys.executable, help="interpreter used to build the smoke fixture")
    args = parser.parse_args()

    engine = container_engine()
    tag = args.tag or f"elmos-generation-workload:{engine_version()}"
    image_id = build(engine, tag)
    print(f"built: {tag}")
    print(f"image id: {image_id}")

    # A local image ID is directly runnable as a digest-pinned reference with
    # --pull=missing (what ContainerRuntime uses); after pushing to a
    # registry prefer the manifest RepoDigests instead.
    name, _, digest = image_id.partition(":")
    print(f"digest-pinned reference (local): {name}@{digest or image_id}")

    if args.smoke:
        smoke(engine, image_id, args.python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
