"""Fail-closed external projections for Elastic, Dify, and OpenTelemetry."""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import urlparse

from .contracts import ContractError, require_mapping, require_string, sha256_payload
from .retrieval import RetrievalQuery, SearchDocument


_INDEX_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,254}$")
_SENSITIVE_ATTRIBUTE = re.compile(r"(api.?key|authorization|credential|secret|password|prompt|content|source)", re.I)


def _endpoint(value: str, field_name: str) -> str:
    raw = require_string(value, field_name).rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ContractError("invalid_endpoint", f"{field_name} must be an HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ContractError("insecure_endpoint", f"{field_name} must use HTTPS outside loopback")
    if parsed.username or parsed.password:
        raise ContractError("credential_in_url", f"{field_name} must not contain credentials")
    return raw


@dataclass(frozen=True, slots=True)
class ElasticsearchSettings:
    endpoint: str
    index_name: str
    vector_dimensions: int
    api_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", _endpoint(self.endpoint, "elasticsearch.endpoint"))
        if not _INDEX_NAME.fullmatch(self.index_name):
            raise ContractError("invalid_index_name", "Elasticsearch index name is invalid")
        if not 1 <= self.vector_dimensions <= 4096:
            raise ContractError("invalid_vector_dimensions", "vector_dimensions must be between 1 and 4096")
        key = require_string(self.api_key, "elasticsearch.api_key")
        if key.upper() in {"SET_ME", "CHANGEME", "PLACEHOLDER"}:
            raise ContractError("elasticsearch_not_configured", "Elasticsearch API key is not configured")


class ElasticsearchProjection:
    """Disposable Elastic projection; source documents remain authoritative."""

    def __init__(self, settings: ElasticsearchSettings, *, client: Any | None = None):
        self.settings = settings
        if client is None:
            try:
                from elasticsearch import Elasticsearch
            except ImportError as exc:
                raise ContractError(
                    "elasticsearch_client_not_configured",
                    "install the repository-orchestrator integrations extra",
                ) from exc
            client = Elasticsearch(settings.endpoint, api_key=settings.api_key, request_timeout=30)
        self.client = client

    @property
    def mapping(self) -> dict[str, Any]:
        return {
            "dynamic": "strict",
            "properties": {
                "document_id": {"type": "keyword"},
                "tenant_id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "revision_id": {"type": "keyword"},
                "allowed_principals": {"type": "keyword"},
                "content": {"type": "text"},
                "modality": {"type": "keyword"},
                "vector": {
                    "type": "dense_vector",
                    "dims": self.settings.vector_dimensions,
                    "index": True,
                    "similarity": "cosine",
                },
                "anchor": {"type": "object", "enabled": True},
                "source_digest": {"type": "keyword"},
            },
        }

    def ensure_index(self) -> bool:
        if bool(self.client.indices.exists(index=self.settings.index_name)):
            return False
        self.client.indices.create(index=self.settings.index_name, mappings=self.mapping)
        return True

    @staticmethod
    def _source(document: SearchDocument) -> dict[str, Any]:
        if document.vector is None:
            raise ContractError("embedding_missing", "Elastic vector projection requires an embedding")
        return {
            "document_id": document.document_id,
            "tenant_id": document.tenant_id,
            "project_id": document.project_id,
            "revision_id": document.revision_id,
            "allowed_principals": sorted(document.allowed_principals),
            "content": document.content,
            "modality": document.modality,
            "vector": list(document.vector),
            "anchor": {
                "uri": document.anchor.uri,
                "kind": document.anchor.kind,
                "content_sha256": document.anchor.content_sha256,
                "start": document.anchor.start,
                "end": document.anchor.end,
                "locator": dict(document.anchor.locator),
            },
            "source_digest": document.digest,
        }

    def upsert(self, documents: Sequence[SearchDocument]) -> Mapping[str, Any]:
        operations: list[dict[str, Any]] = []
        for document in documents:
            if len(document.vector or ()) != self.settings.vector_dimensions:
                raise ContractError("vector_dimension_mismatch", "document vector does not match index mapping")
            external_id = sha256_payload(document.identity)
            operations.extend(({"index": {"_id": external_id}}, self._source(document)))
        if not operations:
            return {"errors": False, "items": []}
        response = self.client.bulk(index=self.settings.index_name, operations=operations, refresh=False)
        body = response.body if hasattr(response, "body") else response
        if not isinstance(body, Mapping) or body.get("errors") is not False:
            raise ContractError("elasticsearch_bulk_failed", "Elasticsearch bulk projection failed")
        return body

    @staticmethod
    def _scope_filters(query: RetrievalQuery) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [
            {"term": {"tenant_id": query.tenant_id}},
            {"term": {"project_id": query.project_id}},
            {"term": {"revision_id": query.revision_id}},
            {"terms": {"allowed_principals": sorted(query.principal_ids)}},
        ]
        if query.modalities:
            filters.append({"terms": {"modality": sorted(query.modalities)}})
        return filters

    def search(self, query: RetrievalQuery) -> tuple[Mapping[str, Any], ...]:
        filters = self._scope_filters(query)
        kwargs: dict[str, Any] = {
            "index": self.settings.index_name,
            "size": query.top_k,
            "query": {"bool": {"must": [{"match": {"content": query.text}}], "filter": filters}},
        }
        if query.vector is not None:
            if len(query.vector) != self.settings.vector_dimensions:
                raise ContractError("vector_dimension_mismatch", "query vector does not match index mapping")
            kwargs["knn"] = {
                "field": "vector",
                "query_vector": list(query.vector),
                "k": query.top_k,
                "num_candidates": min(max(query.top_k * 10, 100), 10_000),
                "filter": filters,
            }
            kwargs["rank"] = {"rrf": {}}
        response = self.client.search(**kwargs)
        body = response.body if hasattr(response, "body") else response
        hits = require_mapping(require_mapping(body, "elasticsearch.response").get("hits"), "elasticsearch.hits").get("hits", ())
        if not isinstance(hits, Sequence) or isinstance(hits, (str, bytes, bytearray)):
            raise ContractError("invalid_elasticsearch_response", "Elasticsearch hits must be an array")
        scoped: list[Mapping[str, Any]] = []
        for item in hits:
            source = require_mapping(require_mapping(item, "elasticsearch.hit").get("_source"), "elasticsearch.hit._source")
            principals = source.get("allowed_principals", ())
            if (
                source.get("tenant_id") != query.tenant_id
                or source.get("project_id") != query.project_id
                or source.get("revision_id") != query.revision_id
                or not isinstance(principals, Sequence)
                or not set(principals) & query.principal_ids
            ):
                raise ContractError("elasticsearch_scope_violation", "Elasticsearch returned an out-of-scope hit")
            scoped.append(item)
        return tuple(scoped)

    def delete_revision(self, *, tenant_id: str, project_id: str, revision_id: str) -> Mapping[str, Any]:
        response = self.client.delete_by_query(
            index=self.settings.index_name,
            query={
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": require_string(tenant_id, "tenant_id")}},
                        {"term": {"project_id": require_string(project_id, "project_id")}},
                        {"term": {"revision_id": require_string(revision_id, "revision_id")}},
                    ]
                }
            },
            conflicts="proceed",
            refresh=True,
        )
        return response.body if hasattr(response, "body") else response


@dataclass(frozen=True, slots=True)
class DifySettings:
    endpoint: str
    api_key: str
    tenant_id: str
    project_id: str
    purpose: str
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", _endpoint(self.endpoint, "dify.endpoint"))
        for field_name in ("api_key", "tenant_id", "project_id", "purpose"):
            value = require_string(getattr(self, field_name), f"dify.{field_name}")
            if field_name == "api_key" and value.upper() in {"SET_ME", "CHANGEME", "PLACEHOLDER"}:
                raise ContractError("dify_not_configured", "Dify API key is not configured")
        if not 1 <= self.timeout_seconds <= 300:
            raise ContractError("invalid_timeout", "Dify timeout_seconds must be between 1 and 300")


class DifyWorkflowClient:
    """Dify is an experiment/workbench adapter, never ELMOS policy authority."""

    def __init__(self, settings: DifySettings, *, client: Any | None = None):
        self.settings = settings
        if client is None:
            try:
                import httpx
            except ImportError as exc:
                raise ContractError("dify_client_not_configured", "install the integrations extra") from exc
            client = httpx.Client(base_url=settings.endpoint, timeout=settings.timeout_seconds)
        self.client = client

    def run(self, inputs: Mapping[str, Any], *, actor_id: str, idempotency_key: str) -> Mapping[str, Any]:
        payload_inputs = dict(require_mapping(inputs, "dify.inputs"))
        reserved = sorted(key for key in payload_inputs if key.startswith("_elmos_"))
        if reserved:
            raise ContractError("trusted_context_forgery", "Dify inputs contain reserved context keys")
        actor = require_string(actor_id, "actor_id")
        request_key = require_string(idempotency_key, "idempotency_key")
        payload_inputs.update(
            {
                "_elmos_tenant_id": self.settings.tenant_id,
                "_elmos_project_id": self.settings.project_id,
                "_elmos_purpose": self.settings.purpose,
            }
        )
        payload = {"inputs": payload_inputs, "response_mode": "blocking", "user": actor}
        response = self.client.post(
            "/v1/workflows/run",
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": request_key,
            },
            json=payload,
        )
        response.raise_for_status()
        body = require_mapping(response.json(), "dify.response")
        run_id = body.get("workflow_run_id") or body.get("task_id")
        require_string(run_id, "dify.response.workflow_run_id")
        return {
            "workflow_run_id": run_id,
            "task_id": body.get("task_id"),
            "data": body.get("data"),
            "request_digest": sha256_payload({"payload": payload, "idempotency_key": request_key}),
            "policy_authority": False,
            "external_execution": "EXECUTED_UNVERIFIED",
            "certification": "NOT_CERTIFIED",
        }


class TraceRecorder:
    """OTel wrapper that rejects source, prompt, credential, and secret attributes."""

    def __init__(self, tracer: Any | None = None):
        if tracer is None:
            try:
                from opentelemetry import trace
            except ImportError as exc:
                raise ContractError("opentelemetry_not_configured", "install the integrations extra") from exc
            tracer = trace.get_tracer("elmos.repository-orchestrator")
        self.tracer = tracer

    @contextlib.contextmanager
    def span(self, name: str, attributes: Mapping[str, Any]) -> Iterator[Any]:
        safe: dict[str, Any] = {}
        for key, value in attributes.items():
            normalized = require_string(key, "trace.attribute.name")
            if _SENSITIVE_ATTRIBUTE.search(normalized):
                raise ContractError("sensitive_trace_attribute", f"trace attribute is forbidden: {normalized}")
            if not isinstance(value, (str, bool, int, float)):
                raise ContractError("invalid_trace_attribute", f"trace attribute has unsupported type: {normalized}")
            safe[normalized] = value
        with self.tracer.start_as_current_span(require_string(name, "span.name"), attributes=safe) as current:
            yield current


def integration_fingerprint(settings: ElasticsearchSettings | DifySettings) -> str:
    """Return a safe configuration fingerprint without credential material."""

    if isinstance(settings, ElasticsearchSettings):
        return sha256_payload(
            {
                "kind": "elasticsearch",
                "endpoint": settings.endpoint,
                "index_name": settings.index_name,
                "vector_dimensions": settings.vector_dimensions,
            }
        )
    return sha256_payload(
        {
            "kind": "dify",
            "endpoint": settings.endpoint,
            "tenant_id": settings.tenant_id,
            "project_id": settings.project_id,
            "purpose": settings.purpose,
        }
    )
