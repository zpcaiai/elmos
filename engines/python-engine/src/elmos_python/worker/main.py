from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Query, status
from fastapi.responses import JSONResponse

from elmos_python.contracts import ErrorCode, ExecuteStepRequest, JobRequest, JobResponse
from elmos_python.engine import PythonEngine

approved_root = Path(os.environ.get("ELMOS_PYTHON_WORKSPACE_ROOT", "/workspaces"))
engine = PythonEngine(approved_root)
app = FastAPI(title="ELMOS Python Engine", version="1.0.0")


@app.get("/engine/v1/capabilities")
def capabilities() -> object:
    return engine.capabilities()


@app.post("/engine/v1/scan", status_code=status.HTTP_202_ACCEPTED)
def scan(request: JobRequest) -> object:
    return _accepted(engine.scan(request))


@app.post("/engine/v1/plan", status_code=status.HTTP_202_ACCEPTED)
def plan(request: JobRequest) -> object:
    return _accepted(engine.plan(request))


@app.post("/engine/v1/execute-step", status_code=status.HTTP_202_ACCEPTED)
def execute_step(request: ExecuteStepRequest) -> object:
    return _accepted(engine.execute_step(request))


@app.post("/engine/v1/validate", status_code=status.HTTP_202_ACCEPTED)
def validate(request: JobRequest) -> object:
    return _accepted(engine.validate(request))


@app.get("/engine/v1/jobs/{job_id}")
def get_job(job_id: str, organization_id: str = Query(alias="organizationId")) -> object:
    return _visible(engine.get_job(organization_id, job_id))


@app.post("/engine/v1/jobs/{job_id}/cancel")
def cancel(job_id: str, organization_id: str = Query(alias="organizationId")) -> object:
    return _visible(engine.cancel(organization_id, job_id))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "UP", "engine": "ELMOS_PYTHON"}


def _visible(response: JobResponse) -> object:
    if response.error:
        if response.error.error_code == ErrorCode.JOB_NOT_FOUND:
            return _problem(response, 404)
        if response.error.error_code == ErrorCode.JOB_TERMINAL:
            return _problem(response, 409)
        if response.error.error_code == ErrorCode.POLICY_BLOCKED:
            # A non-lifecycle policy failure still cannot be presented as a visible successful transition.
            return _problem(response, 409)
    return response


def _accepted(response: JobResponse) -> object:
    if response.error and response.error.error_code == ErrorCode.IDEMPOTENCY_CONFLICT:
        return _problem(response, 409)
    return response


def _problem(response: JobResponse, status_code: int) -> JSONResponse:
    assert response.error is not None
    return JSONResponse(status_code=status_code, content=response.error.model_dump(mode="json", by_alias=True))
