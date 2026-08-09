from uuid import uuid4

from fastapi.testclient import TestClient

from migration_agent.app import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_high_risk_plan_requires_approval() -> None:
    response = client.post(
        "/v1/agents/repair/plan",
        json={
            "tenant_id": str(uuid4()),
            "migration_id": str(uuid4()),
            "diagnostics": [
                {"code": "AUTH-1", "category": "authorization", "message": "missing guard"}
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["requires_human_approval"] is True
