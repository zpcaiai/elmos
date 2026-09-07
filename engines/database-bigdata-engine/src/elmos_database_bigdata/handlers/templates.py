"""Unique bounded handlers for the ten exact project-template Skills."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..catalog import SKILL_CONTRACT_BY_NAME
from ..contracts import RuntimeRequest
from .common import compile_bounded_plan


def _template(
    name: str, request: RuntimeRequest, record: Mapping[str, Any], profile: str
) -> dict[str, Any]:
    return compile_bounded_plan(
        SKILL_CONTRACT_BY_NAME[name],
        request,
        record,
        focus=("template-plan", profile, "external-runtime-gates"),
    )


def handle_elmos_template_cdc_migration_modernization(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template(
        "elmos-template-cdc-migration-modernization", request, record, "cdc-migration"
    )


def handle_elmos_template_data_governance_platform(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template(
        "elmos-template-data-governance-platform", request, record, "data-governance"
    )


def handle_elmos_template_fraud_risk(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template("elmos-template-fraud-risk", request, record, "fraud-risk")


def handle_elmos_template_iot_timeseries(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template("elmos-template-iot-timeseries", request, record, "iot-timeseries")


def handle_elmos_template_log_observability(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template(
        "elmos-template-log-observability", request, record, "log-observability"
    )


def handle_elmos_template_offline_warehouse(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template(
        "elmos-template-offline-warehouse", request, record, "offline-warehouse"
    )


def handle_elmos_template_realtime_analytics(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template(
        "elmos-template-realtime-analytics", request, record, "realtime-analytics"
    )


def handle_elmos_template_realtime_user_profile(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template(
        "elmos-template-realtime-user-profile", request, record, "customer-360"
    )


def handle_elmos_template_recommendation_system(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template(
        "elmos-template-recommendation-system", request, record, "recommendation"
    )


def handle_elmos_template_vector_knowledge_analytics(
    request: RuntimeRequest, record: Mapping[str, Any]
) -> dict[str, Any]:
    return _template(
        "elmos-template-vector-knowledge-analytics", request, record, "vector-knowledge"
    )


__all__ = [name for name in globals() if name.startswith("handle_elmos_")]
