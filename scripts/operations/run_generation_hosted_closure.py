#!/usr/bin/env python3
"""Run the hosted-generation closure that can execute in this repository.

External IdP registration, public managed PostgreSQL, independent human
signature, and certification stay NOT_RUN. This script must not rewrite those
fields to PASSED.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engines" / "project-synthesis-engine"


def run(command: list[str], cwd: Path | None = None) -> None:
    completed = subprocess.run(command, cwd=cwd or ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> int:
    run(
        [
            "uv",
            "--directory",
            str(ENGINE),
            "run",
            "--locked",
            "pytest",
            "tests/test_hosted_production_runtime.py",
        ]
    )
    work = Path(tempfile.mkdtemp(prefix="elmos-generation-hosted-"))
    try:
        sys.path.insert(0, str(ENGINE / "src"))
        from elmos_project_synthesis.hosted_independent_replay import (  # noqa: E402
            build_independent_replay_bundle,
        )

        matrix = ROOT / "docs" / "project-synthesis" / "local-production-profile-matrix.json"
        bundle = build_independent_replay_bundle(
            matrix_path=matrix,
            output_dir=work / "independent",
            producer="repository-executor",
        )
        receipt = {
            "hosted_runner_job_tokens": "PASSED_LOCAL",
            "organization_self_service": "PASSED_LOCAL",
            "hosted_postgres_binding": "CODE_READY",
            "hosted_postgres_external_provider": "NOT_RUN",
            "real_idp_public_issuer": "NOT_RUN",
            "independent_verification_status": bundle["independent_verification_status"],
            "certification_status": bundle["certification_status"],
            "restore_drill": "PENDING_OPERATOR_POSTGRES",
        }
        target = ROOT / "docs" / "project-synthesis" / "hosted-generation-closure.json"
        target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        if shutil.which("node"):
            run(
                [
                    "node",
                    "--experimental-strip-types",
                    str(
                        ROOT
                        / "apps"
                        / "web-console"
                        / "app"
                        / "lib"
                        / "server"
                        / "hostedJobToken.verify.mjs"
                    ),
                ]
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
