from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from elmos_repository_orchestrator.contracts import ContractError, sha256_payload
from elmos_repository_orchestrator.external_execution import execute_external_integrations


class FakeIndices:
    def __init__(self) -> None:
        self.mapping = None

    def exists(self, **kwargs):
        return self.mapping is not None

    def create(self, **kwargs):
        self.mapping = kwargs["mappings"]
        return {"acknowledged": True}

    def get_mapping(self, **kwargs):
        return {kwargs["index"]: {"mappings": self.mapping}}

    def refresh(self, **kwargs):
        return {"_shards": {"successful": 1}}


class FakeElastic:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.sources = []

    def info(self):
        return {"version": {"number": "8.19.3", "distribution": "elasticsearch"}}

    def bulk(self, **kwargs):
        operations = kwargs["operations"]
        self.sources = list(operations[1::2])
        return {"errors": False, "items": [{"index": {"status": 201}} for _ in self.sources]}

    def search(self, **kwargs):
        return {"hits": {"hits": [{"_source": source, "_score": 1.0} for source in self.sources]}}

    def delete_by_query(self, **kwargs):
        deleted = len(self.sources)
        self.sources = []
        return {"deleted": deleted, "timed_out": False, "failures": []}


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeDify:
    def __init__(self, status: str = "succeeded") -> None:
        self.status = status

    def get(self, path, **kwargs):
        return FakeResponse({"name": "private workflow", "mode": "workflow"})

    def post(self, path, **kwargs):
        return FakeResponse({
            "workflow_run_id": "run-1",
            "task_id": "task-1",
            "data": {"status": self.status, "outputs": {"answer": "private output"}},
        })


def environment(authorization_id: str) -> dict[str, str]:
    return {
        "ELMOS_EXTERNAL_EXECUTION_ACK": authorization_id,
        "ELMOS_ELASTICSEARCH_URL": "https://elastic.example",
        "ELMOS_ELASTICSEARCH_API_KEY": "elastic-secret-value",
        "ELMOS_ELASTICSEARCH_INDEX": "elmos-qualification-v1",
        "ELMOS_ELASTICSEARCH_VECTOR_DIMENSIONS": "3",
        "ELMOS_ELASTICSEARCH_EXPECTED_VERSION": "8.19.3",
        "ELMOS_DIFY_URL": "https://dify.example",
        "ELMOS_DIFY_API_KEY": "dify-secret-value",
        "ELMOS_DIFY_WORKFLOW_ID": "workflow-1",
        "ELMOS_DIFY_EXPECTED_VERSION": "1.10.1",
    }


def request() -> dict:
    content = "production-shaped hybrid retrieval fixture"
    return {
        "schema_version": 1,
        "authorization": {
            "authorization_id": "auth-1",
            "approved_operations": ["elasticsearch", "dify"],
            "actor_id": "actor-1",
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "purpose": "provider-qualification",
            "idempotency_key": "idem-1",
            "synthetic": True,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        },
        "elasticsearch": {
            "documents": [{
                "document_id": "doc-1",
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "revision_id": "revision-1",
                "content": content,
                "anchor": {
                    "uri": "repo://docs/runtime.md",
                    "kind": "text-lines",
                    "content_sha256": sha256_payload(content),
                    "start": 1,
                    "end": 1,
                    "locator": {"line": 1},
                },
                "allowed_principals": ["actor-1"],
                "vector": [1.0, 0.0, 0.0],
                "modality": "text",
            }],
            "query": {
                "text": "hybrid retrieval",
                "vector": [1.0, 0.0, 0.0],
                "top_k": 5,
                "modalities": ["text"],
            },
            "cleanup_revision": True,
        },
        "dify": {"inputs": {"question": "is the runtime ready?"}},
    }


def test_real_execution_contract_is_bounded_sanitized_and_not_certified() -> None:
    result = execute_external_integrations(
        request(),
        environment=environment("auth-1"),
        elastic_client=FakeElastic(),
        dify_client=FakeDify(),
    )
    assert result["status"] == "EXECUTED_UNVERIFIED"
    assert result["operations"]["elasticsearch"]["visible_hits"] == 1
    assert result["operations"]["elasticsearch"]["cleanup_deleted"] == 1
    assert result["operations"]["dify"]["workflow_receipt"]["status"] == "succeeded"
    assert result["independent_verification"] == "NOT_RUN"
    assert result["production_certification"] == "NOT_CERTIFIED"
    serialized = str(result)
    assert "elastic-secret-value" not in serialized
    assert "dify-secret-value" not in serialized
    assert "private output" not in serialized
    assert "production-shaped hybrid retrieval fixture" not in serialized


def test_execution_requires_exact_ack_scope_and_successful_workflow() -> None:
    with pytest.raises(ContractError, match="must equal authorization_id"):
        execute_external_integrations(
            request(),
            environment=environment("wrong"),
            elastic_client=FakeElastic(),
            dify_client=FakeDify(),
        )
    cross_tenant = deepcopy(request())
    cross_tenant["elasticsearch"]["documents"][0]["tenant_id"] = "tenant-other"
    with pytest.raises(ContractError, match="authorized tenant/project"):
        execute_external_integrations(
            cross_tenant,
            environment=environment("auth-1"),
            elastic_client=FakeElastic(),
            dify_client=FakeDify(),
        )
    with pytest.raises(ContractError, match="ended with status failed"):
        execute_external_integrations(
            request(),
            environment=environment("auth-1"),
            elastic_client=FakeElastic(),
            dify_client=FakeDify("failed"),
        )


def test_execution_requires_synthetic_data_and_short_lived_authorization() -> None:
    non_synthetic = deepcopy(request())
    non_synthetic["authorization"]["synthetic"] = False
    with pytest.raises(ContractError, match="only synthetic data"):
        execute_external_integrations(
            non_synthetic,
            environment=environment("auth-1"),
            elastic_client=FakeElastic(),
            dify_client=FakeDify(),
        )

    long_lived = deepcopy(request())
    long_lived["authorization"]["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(hours=1)
    ).isoformat()
    with pytest.raises(ContractError, match="at most 30 minutes"):
        execute_external_integrations(
            long_lived,
            environment=environment("auth-1"),
            elastic_client=FakeElastic(),
            dify_client=FakeDify(),
        )
