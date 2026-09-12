from __future__ import annotations

import json
from pathlib import Path

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest
from elmos_project_synthesis.rendering import openapi_yaml, target_readme
from elmos_project_synthesis.verification import verify_workspace
from elmos_project_synthesis.workspace import _render_blueprint, generate_workspace, render_workspace


def _allow_crud(*resources: str) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "actor": "worker-admin",
            "action": action,
            "resource": resource,
            "effect": "allow",
        }
        for resource in resources
        for action in ("create", "read", "update", "delete")
    )


def _worker_request(*, language: str = "python", auth_mode: str = "jwt") -> SynthesisRequest:
    draft = create_draft(
        name="worker-pipeline",
        description="Background task processing worker pipeline",
        entities=(
            {
                "singular": "task",
                "plural": "tasks",
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "status", "type": "string", "required": True},
                ],
            },
        ),
        languages=(language,),
        project_kind="worker",
        persistence="sqlite",
        auth_mode=auth_mode,
        permissions=_allow_crud("task"),
    )
    approved = approve_request(draft, actor="user:ethan-certifier")
    return SynthesisRequest.from_mapping(approved)


def test_worker_draft_intake_requirements_and_criteria() -> None:
    draft = create_draft(
        name="batch-worker",
        description="Batch data processing worker",
        entity="job",
        languages=("python",),
        project_kind="worker",
        persistence="in-memory",
        auth_mode="none",
    )
    assert draft["project"]["kind"] == "worker"
    req_ids = {r["id"] for r in draft["requirements"]}
    assert "REQ-WORKER-001" in req_ids
    assert "REQ-HEALTH-001" in req_ids

    criteria_ids = {c["id"] for c in draft["acceptance_criteria"]}
    assert "AC-WORKER-001" in criteria_ids
    assert "AC-HEALTH-001" in criteria_ids


def test_worker_blueprint_and_generation_units() -> None:
    request = _worker_request(language="python", auth_mode="jwt")
    assert request.is_worker is True
    assert request.is_api is False

    blueprint = _render_blueprint(request)
    assert blueprint["project"]["kind"] == "worker"
    assert blueprint["applications"][0]["kind"] == "worker"
    unit = blueprint["generation_units"][0]
    assert "REQ-WORKER-001" in unit["source_refs"]


def test_worker_openapi_and_readme() -> None:
    request = _worker_request(language="python", auth_mode="jwt")
    spec = openapi_yaml(request, server_port=8080)
    assert "/api/v1/worker/status:" in spec
    assert "/api/v1/worker/trigger:" in spec
    assert "getWorkerStatus" in spec
    assert "triggerWorkerCycle" in spec

    readme = target_readme(
        request,
        language="Python 3.12",
        framework="FastAPI 0.116.1",
        port=8080,
        commands="make run",
    )
    assert "The service kind is `worker`." in readme
    assert "GET /api/v1/worker/status" in readme
    assert "POST /api/v1/worker/trigger" in readme


def test_worker_workspace_generation_structure() -> None:
    request = _worker_request(language="python", auth_mode="jwt")
    files = render_workspace(request)

    assert "python/src/worker_pipeline/worker.py" in files
    assert "python/tests/test_worker_lifecycle.py" in files

    worker_code = files["python/src/worker_pipeline/worker.py"]
    assert "class BackgroundWorker:" in worker_code
    assert "class WorkerStatus:" in worker_code
    assert "WORKER_CYCLES" in worker_code
    assert "WORKER_JOBS_PROCESSED" in worker_code

    lifecycle_test = files["python/tests/test_worker_lifecycle.py"]
    assert "test_worker_cycle_execution" in lifecycle_test
    assert "test_worker_run_loop_and_stop" in lifecycle_test

    sec_test = files["python/tests/test_security.py"]
    assert "test_worker_status_unauthenticated_is_denied" in sec_test
    assert "test_worker_trigger_unauthenticated_is_denied" in sec_test

    int_test = files["python/tests/test_sqlite_integration.py"]
    assert "test_worker_authenticated_journey" in int_test

    blueprint = json.loads(files["requirements/project-blueprint.json"])
    assert blueprint["project"]["kind"] == "worker"


def test_worker_python_sqlite_verification(tmp_path: Path) -> None:
    request = _worker_request(language="python", auth_mode="jwt")
    workspace = tmp_path / "workspace"
    generate_workspace(request.raw, workspace)

    evidence = verify_workspace(workspace, use_ephemeral_runtime_ports=True)
    python_results = [r for r in evidence["results"] if r.get("language") == "python"]
    assert len(python_results) >= 2
    assert all(r["status"] == "PASSED" for r in python_results), python_results
    assert evidence["status"] == "PASSED"
