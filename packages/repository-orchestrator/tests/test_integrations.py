from __future__ import annotations

import unittest

from elmos_repository_orchestrator.contracts import ContractError, sha256_payload
from elmos_repository_orchestrator.integrations import (
    DifySettings,
    DifyWorkflowClient,
    ElasticsearchProjection,
    ElasticsearchSettings,
    TraceRecorder,
    integration_fingerprint,
)
from elmos_repository_orchestrator.retrieval import RetrievalQuery, SearchDocument, SourceAnchor

class FakeIndices:
    def __init__(self) -> None:
        self.created = None

    def exists(self, **kwargs):
        return False

    def create(self, **kwargs):
        self.created = kwargs
        return {"acknowledged": True}

    def get_mapping(self, **kwargs):
        dimensions = self.created["mappings"]["properties"]["vector"]["dims"] if self.created else 3
        return {
            kwargs["index"]: {
                "mappings": {
                    "properties": {
                        "document_id": {"type": "keyword"},
                        "tenant_id": {"type": "keyword"},
                        "project_id": {"type": "keyword"},
                        "revision_id": {"type": "keyword"},
                        "allowed_principals": {"type": "keyword"},
                        "content": {"type": "text"},
                        "modality": {"type": "keyword"},
                        "source_digest": {"type": "keyword"},
                        "vector": {"type": "dense_vector", "dims": dimensions},
                    }
                }
            }
        }

    def refresh(self, **kwargs):
        return {"_shards": {"successful": 1}}


class FakeElastic:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.bulk_request = None
        self.search_request = None
        self.delete_request = None
        self.hits = []

    def bulk(self, **kwargs):
        self.bulk_request = kwargs
        return {"errors": False, "items": [{"index": {"status": 201}}]}

    def search(self, **kwargs):
        self.search_request = kwargs
        return {"hits": {"hits": self.hits}}

    def delete_by_query(self, **kwargs):
        self.delete_request = kwargs
        return {"deleted": 1, "timed_out": False, "failures": []}

    def info(self):
        return {"version": {"number": "8.19.3", "distribution": "elasticsearch", "build_flavor": "default"}}


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeHttpClient:
    def __init__(self) -> None:
        self.request = None

    def post(self, path, **kwargs):
        self.request = (path, kwargs)
        return FakeResponse({
            "workflow_run_id": "run-123",
            "task_id": "task-123",
            "data": {"status": "succeeded", "outputs": {"answer": "ok"}},
        })

    def get(self, path, **kwargs):
        self.request = (path, kwargs)
        return FakeResponse({"name": "ELMOS governed workflow", "mode": "workflow"})


def source_document() -> SearchDocument:
    content = "hybrid retrieval with exact access filters"
    return SearchDocument(
        document_id="doc-1",
        tenant_id="tenant-a",
        project_id="project-a",
        revision_id="rev-1",
        content=content,
        anchor=SourceAnchor("repo://docs/a.md", "text-lines", sha256_payload(content), 1, 2),
        allowed_principals=frozenset({"alice"}),
        vector=(1.0, 0.0, 0.0),
    )


def query() -> RetrievalQuery:
    return RetrievalQuery(
        tenant_id="tenant-a",
        project_id="project-a",
        revision_id="rev-1",
        principal_ids=frozenset({"alice"}),
        text="hybrid retrieval",
        vector=(1.0, 0.0, 0.0),
        top_k=10,
    )


class ElasticsearchProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeElastic()
        self.settings = ElasticsearchSettings("https://elastic.example", "elmos-project-v1", 3, "real-key")
        self.projection = ElasticsearchProjection(self.settings, client=self.client)

    def test_mapping_bulk_hybrid_query_and_delete_are_scope_bound(self) -> None:
        self.assertTrue(self.projection.ensure_index())
        vector_mapping = self.client.indices.created["mappings"]["properties"]["vector"]
        self.assertEqual((vector_mapping["type"], vector_mapping["dims"]), ("dense_vector", 3))
        anchor_mapping = self.client.indices.created["mappings"]["properties"]["anchor"]
        self.assertEqual(anchor_mapping["properties"]["locator"]["type"], "flattened")
        self.assertEqual(self.projection.server_profile()["version"], "8.19.3")
        result = self.projection.upsert([source_document()])
        self.assertFalse(result["errors"])
        self.assertEqual(len(self.client.bulk_request["operations"]), 2)
        self.projection.refresh()

        self.client.hits = [{"_source": ElasticsearchProjection._source(source_document()), "_score": 1.0}]
        hits = self.projection.search(query())
        self.assertEqual(len(hits), 1)
        request = self.client.search_request
        self.assertEqual(request["rank"], {"rrf": {}})
        lexical_filters = request["query"]["bool"]["filter"]
        self.assertIn({"term": {"tenant_id": "tenant-a"}}, lexical_filters)
        self.assertEqual(request["knn"]["filter"], lexical_filters)

        deleted = self.projection.delete_revision(tenant_id="tenant-a", project_id="project-a", revision_id="rev-1")
        self.assertEqual(deleted["deleted"], 1)
        self.assertIn({"term": {"tenant_id": "tenant-a"}}, self.client.delete_request["query"]["bool"]["filter"])

    def test_scope_violation_dimension_and_insecure_endpoint_fail_closed(self) -> None:
        self.client.hits = [
            {
                "_source": {
                    **ElasticsearchProjection._source(source_document()),
                    "tenant_id": "tenant-b",
                }
            }
        ]
        with self.assertRaisesRegex(ContractError, "out-of-scope"):
            self.projection.search(query())
        with self.assertRaisesRegex(ContractError, "does not match"):
            self.projection.upsert(
                [
                    SearchDocument(
                        document_id="bad",
                        tenant_id="tenant-a",
                        project_id="project-a",
                        revision_id="rev-1",
                        content="bad vector",
                        anchor=SourceAnchor("repo://bad", "text", sha256_payload("bad")),
                        allowed_principals=frozenset({"alice"}),
                        vector=(1.0, 0.0),
                    )
                ]
            )
        with self.assertRaisesRegex(ContractError, "must use HTTPS"):
            ElasticsearchSettings("http://elastic.example", "idx", 3, "key")

    def test_environment_binding_and_existing_mapping_are_validated(self) -> None:
        settings = ElasticsearchSettings.from_environment({
            "ELMOS_ELASTICSEARCH_URL": "https://elastic.example",
            "ELMOS_ELASTICSEARCH_API_KEY": "real-key",
            "ELMOS_ELASTICSEARCH_INDEX": "elmos-v1",
            "ELMOS_ELASTICSEARCH_VECTOR_DIMENSIONS": "3",
            "ELMOS_ELASTICSEARCH_EXPECTED_VERSION": "8.19.3",
        })
        self.assertEqual(settings.vector_dimensions, 3)
        self.projection.ensure_index()
        self.client.indices.exists = lambda **kwargs: True
        self.assertFalse(self.projection.ensure_index())
        bad_mapping = self.client.indices.get_mapping
        self.client.indices.get_mapping = lambda **kwargs: {
            kwargs["index"]: {"mappings": {"properties": {
                **bad_mapping(**kwargs)[kwargs["index"]]["mappings"]["properties"],
                "vector": {"type": "dense_vector", "dims": 2},
            }}}
        }
        with self.assertRaisesRegex(ContractError, "vector mapping"):
            self.projection.ensure_index()


class DifyAndTelemetryTests(unittest.TestCase):
    def test_dify_contract_preserves_scope_idempotency_and_hides_secret(self) -> None:
        settings = DifySettings(
            "https://dify.example",
            "secret-api-key",
            "workflow-123",
            "1.10.1",
            "tenant-a",
            "project-a",
            "rag-experiment",
        )
        client = FakeHttpClient()
        receipt = DifyWorkflowClient(settings, client=client).run(
            {"question": "where is the queue?"}, actor_id="alice", idempotency_key="req-1"
        )
        path, request = client.request
        self.assertEqual(path, "/v1/workflows/run")
        self.assertEqual(request["headers"]["Idempotency-Key"], "req-1")
        self.assertEqual(request["json"]["inputs"]["_elmos_tenant_id"], "tenant-a")
        self.assertFalse(receipt["policy_authority"])
        self.assertEqual(receipt["workflow_id"], "workflow-123")
        self.assertEqual(receipt["status"], "succeeded")
        self.assertNotIn("answer", str(receipt))
        self.assertNotIn("secret-api-key", str(receipt))
        self.assertNotIn("secret-api-key", integration_fingerprint(settings))
        with self.assertRaisesRegex(ContractError, "reserved context"):
            DifyWorkflowClient(settings, client=client).run(
                {"_elmos_tenant_id": "tenant-b"}, actor_id="alice", idempotency_key="req-2"
            )

        profile = DifyWorkflowClient(settings, client=client).application_profile()
        self.assertEqual(profile["workflow_id"], "workflow-123")
        self.assertEqual(profile["mode"], "workflow")
        self.assertNotIn("ELMOS governed workflow", str(profile))

        from_environment = DifySettings.from_environment(
            tenant_id="tenant-a",
            project_id="project-a",
            purpose="rag-experiment",
            environment={
                "ELMOS_DIFY_URL": "https://dify.example",
                "ELMOS_DIFY_API_KEY": "secret-api-key",
                "ELMOS_DIFY_WORKFLOW_ID": "workflow-123",
                "ELMOS_DIFY_EXPECTED_VERSION": "1.10.1",
            },
        )
        self.assertEqual(from_environment.workflow_id, "workflow-123")

    def test_otel_records_safe_attributes_and_rejects_content(self) -> None:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        recorder = TraceRecorder(provider.get_tracer("test"))
        with recorder.span("retrieval.search", {"tenant.id": "tenant-a", "result.count": 2}):
            pass
        spans = exporter.get_finished_spans()
        self.assertEqual(spans[0].attributes["result.count"], 2)
        with self.assertRaisesRegex(ContractError, "forbidden"):
            with recorder.span("bad", {"prompt.content": "source code"}):
                pass


if __name__ == "__main__":
    unittest.main()
