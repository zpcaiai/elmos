"""Unique bounded handlers for the twenty-two Big Data core Skills."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..catalog import SKILL_CONTRACT_BY_NAME
from ..contracts import RuntimeRequest
from .common import compile_bounded_plan


def _plan(
    name: str,
    request: RuntimeRequest,
    record: Mapping[str, Any],
    focus: tuple[str, ...],
) -> dict[str, Any]:
    return compile_bounded_plan(
        SKILL_CONTRACT_BY_NAME[name], request, record, focus=focus
    )


def handle_elmos_batch_processing_generator(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-batch-processing-generator",
        request,
        record,
        ("batch-ir", "incremental-dag", "provider-neutral-output"),
    )


def handle_elmos_bigdata_api_dashboard(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-api-dashboard",
        request,
        record,
        ("serving-contract", "api-spec", "dashboard-spec"),
    )


def handle_elmos_bigdata_auto_repair(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-auto-repair",
        request,
        record,
        ("root-cause-plan", "approval-gate", "no-repair-write"),
    )


def handle_elmos_bigdata_cost_autotuning(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-cost-autotuning",
        request,
        record,
        ("optimization-plan", "guardrails", "rollback-threshold"),
    )


def handle_elmos_bigdata_evidence_certification(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-evidence-certification",
        request,
        record,
        ("evidence-gap", "conservative-gate", "not-certified"),
    )


def handle_elmos_bigdata_infra_deployment(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-infra-deployment",
        request,
        record,
        ("provider-neutral-iac", "least-privilege", "no-apply"),
    )


def handle_elmos_bigdata_pattern_selector(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-pattern-selector",
        request,
        record,
        ("pattern-rules", "alternatives", "reconsideration"),
    )


def handle_elmos_bigdata_performance_chaos(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-performance-chaos",
        request,
        record,
        ("workload-plan", "fault-plan", "no-chaos-execution"),
    )


def handle_elmos_bigdata_project_classifier(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-project-classifier",
        request,
        record,
        ("project-class", "scenario-map", "capability-needs"),
    )


def handle_elmos_bigdata_security_governance(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-security-governance",
        request,
        record,
        ("classification", "retention", "access-review"),
    )


def handle_elmos_bigdata_test_validation(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-bigdata-test-validation",
        request,
        record,
        ("traceability", "independent-corpora", "defect-ledger"),
    )


def handle_elmos_cdc_event_backbone(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-cdc-event-backbone",
        request,
        record,
        ("event-contract", "snapshot-stream-boundary", "replay-policy"),
    )


def handle_elmos_data_modeling_semantic_layer(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-data-modeling-semantic-layer",
        request,
        record,
        ("semantic-model", "metric-grain", "temporal-semantics"),
    )


def handle_elmos_data_quality_observability(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-data-quality-observability",
        request,
        record,
        ("data-contract", "quality-rule", "data-slo"),
    )


def handle_elmos_feature_store_ml_pipeline(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-feature-store-ml-pipeline",
        request,
        record,
        ("feature-contract", "point-in-time-correctness", "online-offline-parity"),
    )


def handle_elmos_federated_query_data_fabric(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-federated-query-data-fabric",
        request,
        record,
        ("federation-topology", "pushdown-policy", "connector-evidence"),
    )


def handle_elmos_ingestion_connector_planner(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-ingestion-connector-planner",
        request,
        record,
        ("source-mode", "connector-matrix", "schema-contract"),
    )


def handle_elmos_lakehouse_generator(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-lakehouse-generator",
        request,
        record,
        ("table-layout", "catalog-plan", "maintenance-dag"),
    )


def handle_elmos_metadata_catalog_lineage(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-metadata-catalog-lineage",
        request,
        record,
        ("asset-identity", "lineage-policy", "ownership"),
    )


def handle_elmos_orchestration_backfill_replay(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-orchestration-backfill-replay",
        request,
        record,
        ("checkpoint", "idempotency", "bounded-replay"),
    )


def handle_elmos_stream_processing_generator(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-stream-processing-generator",
        request,
        record,
        ("stream-ir", "watermark", "checkpoint-policy"),
    )


def handle_elmos_warehouse_olap_serving(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _plan(
        "elmos-warehouse-olap-serving",
        request,
        record,
        ("olap-model", "materialization", "query-slo"),
    )


__all__ = [name for name in globals() if name.startswith("handle_elmos_")]
