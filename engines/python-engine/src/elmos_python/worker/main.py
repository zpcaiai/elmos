from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status

from elmos_python.contracts import ErrorCode, ExecuteStepRequest, JobRequest, JobResponse
from elmos_python.engine import PythonEngine

approved_root = Path(os.environ.get("ELMOS_PYTHON_WORKSPACE_ROOT", "/workspaces"))
engine = PythonEngine(approved_root)
app = FastAPI(title="ELMOS Python Engine", version="1.0.0")


@app.get("/engine/v1/capabilities")
def capabilities() -> object:
    return engine.capabilities()


@app.post("/engine/v1/scan", status_code=status.HTTP_202_ACCEPTED)
def scan(request: JobRequest) -> JobResponse:
    return _accepted(engine.scan(request))


@app.post("/engine/v1/plan", status_code=status.HTTP_202_ACCEPTED)
def plan(request: JobRequest) -> JobResponse:
    return _accepted(engine.plan(request))


@app.post("/engine/v1/execute-step", status_code=status.HTTP_202_ACCEPTED)
def execute_step(request: ExecuteStepRequest) -> JobResponse:
    return _accepted(engine.execute_step(request))


@app.post("/engine/v1/validate", status_code=status.HTTP_202_ACCEPTED)
def validate(request: JobRequest) -> JobResponse:
    return _accepted(engine.validate(request))


@app.get("/engine/v1/jobs/{job_id}")
def get_job(job_id: str, organization_id: str = Query(alias="organizationId")) -> JobResponse:
    return _visible(engine.get_job(organization_id, job_id))


@app.post("/engine/v1/jobs/{job_id}/cancel")
def cancel(job_id: str, organization_id: str = Query(alias="organizationId")) -> JobResponse:
    return _visible(engine.cancel(organization_id, job_id))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "UP", "engine": "ELMOS_PYTHON"}


def _visible(response: JobResponse) -> JobResponse:
    if response.error and response.error.error_code == ErrorCode.POLICY_BLOCKED:
        if response.error.message.startswith("Job is not visible"):
            raise HTTPException(status_code=404, detail=response.model_dump(mode="json", by_alias=True))
        raise HTTPException(status_code=409, detail=response.model_dump(mode="json", by_alias=True))
    return response


def _accepted(response: JobResponse) -> JobResponse:
    if response.error and response.error.error_code == ErrorCode.POLICY_BLOCKED:
        if "idempotency" in response.error.message.lower():
            raise HTTPException(status_code=409, detail=response.model_dump(mode="json", by_alias=True))
    return response
