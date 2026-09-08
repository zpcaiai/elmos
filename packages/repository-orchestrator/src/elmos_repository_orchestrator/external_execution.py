"""Explicitly authorized real Elasticsearch and Dify execution.

The entrypoint deliberately has no retry loop.  A provider timeout or ambiguous
transport failure is returned as UNKNOWN to the operator, who must reconcile the
provider before issuing a new authorization and idempotency key.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .contracts import (
    ContractError,
    parse_timestamp,
    require_mapping,
    require_string,
    require_string_sequence,
    sha256_payload,
)
from .integrations import (
    DifySettings,
    DifyWorkflowClient,
    ElasticsearchProjection,
    ElasticsearchSettings,
    integration_fingerprint,
)
from .retrieval import RetrievalQuery, SearchDocument, SourceAnchor


def _anchor(value: Any) -> SourceAnchor:
    item = require_mapping(value, "document.anchor")
    locator = require_mapping(item.get("locator", {}), "document.anchor.locator")
    return SourceAnchor(
        uri=require_string(item.get("uri"), "document.anchor.uri"),
        kind=require_string(item.get("kind"), "document.anchor.kind"),
        content_sha256=require_string(item.get("content_sha256"), "document.anchor.content_sha256"),
        start=item.get("start"),
        end=item.get("end"),
        locator=locator,
    )


def _documents(value: Any, *, tenant_id: str, project_id: str, actor_id: str) -> tuple[SearchDocument, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise ContractError("documents_required", "elasticsearch.documents must be a non-empty array")
    if len(value) > 10_000:
        raise ContractError("documents_too_large", "elasticsearch.documents exceeds 10000 items")
    result: list[SearchDocument] = []
    for raw in value:
        item = require_mapping(raw, "elasticsearch.documents[]")
        principals = frozenset(require_string_sequence(item.get("allowed_principals"), "allowed_principals"))
        document = SearchDocument(
            document_id=require_string(item.get("document_id"), "document.document_id"),
            tenant_id=require_string(item.get("tenant_id"), "document.tenant_id"),
            project_id=require_string(item.get("project_id"), "document.project_id"),
            revision_id=require_string(item.get("revision_id"), "document.revision_id"),
            content=require_string(item.get("content"), "document.content"),
            anchor=_anchor(item.get("anchor")),
            allowed_principals=principals,
            vector=tuple(item.get("vector", ())),
            modality=require_string(item.get("modality", "text"), "document.modality"),
            metadata=require_mapping(item.get("metadata", {}), "document.metadata"),
        )
        if document.tenant_id != tenant_id or document.project_id != project_id:
            raise ContractError("document_scope_violation", "all documents must match the authorized tenant/project")
        if actor_id not in document.allowed_principals:
            raise ContractError("document_acl_violation", "the authorized actor must be able to verify every document")
        result.append(document)
    return tuple(result)


def _authorization(request: Mapping[str, Any], environment: Mapping[str, str]) -> Mapping[str, Any]:
    authorization = require_mapping(request.get("authorization"), "authorization")
    authorization_id = require_string(authorization.get("authorization_id"), "authorization.authorization_id")
    if environment.get("ELMOS_EXTERNAL_EXECUTION_ACK", "").strip() != authorization_id:
        raise ContractError("execution_not_acknowledged", "ELMOS_EXTERNAL_EXECUTION_ACK must equal authorization_id")
    approved = set(require_string_sequence(authorization.get("approved_operations"), "approved_operations"))
    if approved != {"elasticsearch", "dify"}:
        raise ContractError("operation_not_authorized", "authorization must cover exactly elasticsearch and dify")
    expires_at = parse_timestamp(authorization.get("expires_at"), "authorization.expires_at")
    now = datetime.now(timezone.utc)
    if expires_at <= now:
        raise ContractError("authorization_expired", "external execution authorization has expired")
    if (expires_at - now).total_seconds() > 1800:
        raise ContractError("authorization_too_long", "external execution authorization may last at most 30 minutes")
    return authorization


def execute_external_integrations(
    request_value: Any,
    *,
    environment: Mapping[str, str] | None = None,
    elastic_client: Any | None = None,
    dify_client: Any | None = None,
) -> Mapping[str, Any]:
    """Execute one bounded Elastic projection/search and one Dify Workflow call."""

    request = require_mapping(request_value, "external_execution_request")
    if request.get("schema_version") != 1:
        raise ContractError("execution_schema", "external execution schema_version must be 1")
    values = os.environ if environment is None else environment
    authorization = _authorization(request, values)
    authorization_id = require_string(authorization.get("authorization_id"), "authorization.authorization_id")
    actor_id = require_string(authorization.get("actor_id"), "authorization.actor_id")
    tenant_id = require_string(authorization.get("tenant_id"), "authorization.tenant_id")
    project_id = require_string(authorization.get("project_id"), "authorization.project_id")
    purpose = require_string(authorization.get("purpose"), "authorization.purpose")
    idempotency_key = require_string(authorization.get("idempotency_key"), "authorization.idempotency_key")
    synthetic = authorization.get("synthetic")
    if synthetic is not True:
        raise ContractError("synthetic_only", "external qualification accepts only synthetic data")

    elastic_input = require_mapping(request.get("elasticsearch"), "elasticsearch")
    documents = _documents(
        elastic_input.get("documents"), tenant_id=tenant_id, project_id=project_id, actor_id=actor_id
    )
    revisions = {document.revision_id for document in documents}
    if len(revisions) != 1:
        raise ContractError("revision_scope", "one execution may project exactly one revision")
    revision_id = next(iter(revisions))
    query_input = require_mapping(elastic_input.get("query"), "elasticsearch.query")
    query = RetrievalQuery(
        tenant_id=tenant_id,
        project_id=project_id,
        revision_id=revision_id,
        principal_ids=frozenset({actor_id}),
        text=require_string(query_input.get("text"), "elasticsearch.query.text"),
        vector=tuple(query_input.get("vector", ())),
        top_k=query_input.get("top_k", 10),
        modalities=frozenset(require_string_sequence(query_input.get("modalities", ()), "query.modalities")),
    )
    elastic_settings = ElasticsearchSettings.from_environment(values)
    elastic = ElasticsearchProjection(elastic_settings, client=elastic_client)

    elastic_started = time.monotonic()
    server_profile = elastic.server_profile()
    created = elastic.ensure_index()
    bulk = elastic.upsert(documents)
    elastic.refresh()
    hits = elastic.search(query)
    if not hits:
        raise ContractError("elasticsearch_no_visible_hit", "authorized Elasticsearch query returned no visible hit")
    deleted = None
    if elastic_input.get("cleanup_revision") is True:
        deleted = elastic.delete_revision(
            tenant_id=tenant_id, project_id=project_id, revision_id=revision_id
        ).get("deleted")
        elastic.refresh()
        if elastic.search(query):
            raise ContractError("elasticsearch_cleanup_failed", "revision remained visible after cleanup")
    elastic_duration_ms = round((time.monotonic() - elastic_started) * 1000, 3)

    dify_input = require_mapping(request.get("dify"), "dify")
    dify_settings = DifySettings.from_environment(
        tenant_id=tenant_id,
        project_id=project_id,
        purpose=purpose,
        environment=values,
    )
    dify = DifyWorkflowClient(dify_settings, client=dify_client)
    dify_started = time.monotonic()
    application_profile = dify.application_profile()
    dify_receipt = dify.run(
        require_mapping(dify_input.get("inputs"), "dify.inputs"),
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    dify_duration_ms = round((time.monotonic() - dify_started) * 1000, 3)

    request_digest = sha256_payload(request)
    return {
        "schema_version": 1,
        "status": "EXECUTED_UNVERIFIED",
        "external_execution": "EXECUTED_UNVERIFIED",
        "production_certification": "NOT_CERTIFIED",
        "authorization_id": authorization_id,
        "synthetic": synthetic,
        "request_digest": request_digest,
        "operations": {
            "elasticsearch": {
                "status": "EXECUTED_UNVERIFIED",
                "configuration_digest": integration_fingerprint(elastic_settings),
                "server_profile": server_profile,
                "index_created": created,
                "documents_submitted": len(documents),
                "bulk_items": len(bulk.get("items", ())),
                "visible_hits": len(hits),
                "cleanup_deleted": deleted,
                "duration_ms": elastic_duration_ms,
            },
            "dify": {
                "status": "EXECUTED_UNVERIFIED",
                "configuration_digest": integration_fingerprint(dify_settings),
                "application_profile": application_profile,
                "workflow_receipt": dify_receipt,
                "duration_ms": dify_duration_ms,
            },
        },
        "independent_verification": "NOT_RUN",
        "eligible_for_production_certification": False,
    }
