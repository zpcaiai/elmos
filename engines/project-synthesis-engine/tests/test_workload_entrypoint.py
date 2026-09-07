"""Workload entrypoint contract tests.

Covers ``workload/entrypoint.py`` - the process the runner-agent starts in
the generation workload container - without docker: the entrypoint is plain
Python and honours ELMOS_INPUT_DIR/ELMOS_OUTPUT_DIR/ELMOS_WORKLOAD_WORK_DIR,
so a subprocess run against temp directories exercises exactly the container
contract (payload parsing, progress protocol, artifact placement, exit
codes).
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from elmos_project_synthesis.intake import approve_request, create_draft

ENGINE_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ENGINE_ROOT / "workload" / "entrypoint.py"

EXIT_OK = 0
EXIT_REQUEST_INVALID = 2
EXIT_PIPELINE_FAILED = 4
EXIT_RESULT_INVALID = 5
EXIT_ARTIFACT_INVALID = 6


def approved_synthesis_request() -> dict[str, object]:
    draft = create_draft(
        name="work-order-service",
        description="维修工单创建、查询和健康检查服务。",
        entity="work_order",
        languages=["php"],
    )
    return approve_request(draft, actor="user:test")


def hosted_payload(synthesis_request: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "jobKind": "project-synthesis",
        "actor": "user:test",
        "tenantId": "tenant-test",
        "intent": {"schema_version": "1.1.0"},
        "synthesisRequest": synthesis_request
        if synthesis_request is not None
        else approved_synthesis_request(),
    }


def run_entrypoint(
    payload: object,
    work_dir: Path,
    pythonpath: str | None = None,
    raw_request: str | None = None,
) -> subprocess.CompletedProcess[str]:
    input_dir = work_dir / "in"
    output_dir = work_dir / "out"
    scratch = work_dir / "tmp"
    for directory in (input_dir, output_dir, scratch):
        directory.mkdir(parents=True, exist_ok=True)
    if raw_request is not None:
        (input_dir / "request.json").write_text(raw_request, encoding="utf-8")
    elif payload is not None:
        (input_dir / "request.json").write_text(json.dumps(payload), encoding="utf-8")
    environment = {
        "PATH": "/usr/bin:/bin",
        "ELMOS_INPUT_DIR": str(input_dir),
        "ELMOS_OUTPUT_DIR": str(output_dir),
        "ELMOS_WORKLOAD_WORK_DIR": str(scratch),
        "ELMOS_JOB_KIND": "project-synthesis",
        "PYTHONPATH": pythonpath or str(ENGINE_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(  # noqa: S603 - fixed interpreter, repository-owned entrypoint.
        [sys.executable, str(ENTRYPOINT)],
        env=environment,
        cwd=str(scratch),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=300,
    )


def fake_engine(work_dir: Path, cli_body: str) -> str:
    """A minimal elmos_project_synthesis.cli shim placed ahead of the real
    engine on PYTHONPATH so the guard branches can be forced deterministically."""
    package = work_dir / "fake-engine" / "elmos_project_synthesis"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(cli_body, encoding="utf-8")
    return str(work_dir / "fake-engine")


def test_success_publishes_archive_evidence_and_progress(tmp_path: Path) -> None:
    completed = run_entrypoint(hosted_payload(), tmp_path)
    assert completed.returncode == EXIT_OK, completed.stdout

    stages = [line for line in completed.stdout.splitlines() if line.startswith("::elmos")]
    assert "::elmos stage=pipeline progress=10" in stages
    assert "::elmos stage=archiving progress=90" in stages
    assert stages[-1] == "::elmos stage=complete progress=100"

    out = tmp_path / "out"
    archive = out / "generated-project.zip"
    assert archive.is_file() and archive.stat().st_size > 0
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist()

    verification = json.loads(
        (out / "evidence" / "verification.json").read_text(encoding="utf-8")
    )
    assert verification["status"] in {"PASSED", "PARTIAL"}
    result = json.loads(
        (out / "evidence" / "pipeline-result.json").read_text(encoding="utf-8")
    )
    assert result["status"] in {"PASSED", "PARTIAL"}
    assert (out / "logs" / "pipeline.log").is_file()


def test_payload_without_synthesis_request_fails_closed(tmp_path: Path) -> None:
    completed = run_entrypoint({"actor": "user:test"}, tmp_path)
    assert completed.returncode == EXIT_REQUEST_INVALID
    assert "::elmos stage=blocked" not in completed.stdout


def test_unparseable_request_fails_closed(tmp_path: Path) -> None:
    completed = run_entrypoint(None, tmp_path, raw_request="{not json")
    assert completed.returncode == EXIT_REQUEST_INVALID


def test_pipeline_failure_publishes_log_and_reports_blocked(tmp_path: Path) -> None:
    # A request with an unsupported target language never passes pipeline
    # admission; the workload must surface the engine failure with the
    # diagnostic log and exit non-zero.
    rejected = create_draft(
        name="work-order-service",
        description="维修工单创建、查询和健康检查服务。",
        entity="work_order",
    )
    rejected["languages"] = ["cobol"]
    completed = run_entrypoint(hosted_payload(rejected), tmp_path)
    assert completed.returncode == EXIT_PIPELINE_FAILED
    assert "::elmos stage=blocked progress=100" in completed.stdout
    assert (tmp_path / "out" / "logs" / "pipeline.log").is_file()
    assert not (tmp_path / "out" / "generated-project.zip").exists()


def test_unparseable_pipeline_result_is_rejected(tmp_path: Path) -> None:
    shim = fake_engine(
        tmp_path,
        "import sys\n"
        "sys.stdout.write('not-json\\n')\n"
        "sys.exit(0)\n",
    )
    completed = run_entrypoint(hosted_payload(), tmp_path, pythonpath=shim)
    assert completed.returncode == EXIT_RESULT_INVALID
    assert "WORKLOAD_RESULT_UNPARSEABLE" in completed.stdout


def test_pipeline_result_status_outside_accepted_set_is_rejected(tmp_path: Path) -> None:
    shim = fake_engine(
        tmp_path,
        "import sys\n"
        "sys.stdout.write('{\"status\": \"FAILED\"}\\n')\n"
        "sys.exit(0)\n",
    )
    completed = run_entrypoint(hosted_payload(), tmp_path, pythonpath=shim)
    assert completed.returncode == EXIT_RESULT_INVALID
    assert "WORKLOAD_RESULT_REJECTED" in completed.stdout


def test_missing_archive_after_passing_result_is_rejected(tmp_path: Path) -> None:
    shim = fake_engine(
        tmp_path,
        "import sys\n"
        "sys.stdout.write('{\"status\": \"PASSED\"}\\n')\n"
        "sys.exit(0)\n",
    )
    completed = run_entrypoint(hosted_payload(), tmp_path, pythonpath=shim)
    assert completed.returncode == EXIT_ARTIFACT_INVALID
    assert "WORKLOAD_ARCHIVE_MISSING" in completed.stdout
