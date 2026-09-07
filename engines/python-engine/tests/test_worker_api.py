from __future__ import annotations

from fastapi.testclient import TestClient

from elmos_python.worker.main import app

client = TestClient(app)


def test_missing_and_terminal_jobs_use_typed_404_and_409_contracts() -> None:
    missing = client.get("/engine/v1/jobs/missing", params={"organizationId": "org-api"})
    assert missing.status_code == 404
    assert missing.json()["errorCode"] == "JOB_NOT_FOUND"

    created = client.post(
        "/engine/v1/plan",
        json={
            "organizationId": "org-api",
            "repositorySnapshotRef": "snapshot-api",
            "workspaceRef": "missing-workspace",
            "profile": "STANDARD",
            "correlationId": "corr-api",
            "idempotencyKey": "terminal-api",
            "options": {},
        },
    )
    assert created.status_code == 202
    job_id = created.json()["jobId"]
    terminal = client.post(f"/engine/v1/jobs/{job_id}/cancel", params={"organizationId": "org-api"})
    assert terminal.status_code == 409
    assert terminal.json()["errorCode"] == "JOB_TERMINAL"
