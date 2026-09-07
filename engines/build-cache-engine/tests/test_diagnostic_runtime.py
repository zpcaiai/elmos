from __future__ import annotations

import json
from typing import Any

import pytest

from elmos_build_cache.clock import ManualClock
from elmos_build_cache.diagnostic_runtime import IdentityDiagnosticRuntime, LostValue
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.miss_diagnostics import (
    CacheCohort,
    CacheLayer,
    CacheOutcomeReason,
    IdentityDimension,
)


class RecordingRepository:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Any,
    ) -> dict[str, Any]:
        key = (tenant_id, project_id, request_id, event_id)
        closed = json.loads(json.dumps(document))
        existing = self.documents.get(key)
        if existing is not None and existing != closed:
            raise AssertionError("event identity drifted")
        self.documents[key] = closed
        return closed

    def list_cache_outcomes(
        self, tenant_id: str, project_id: str, request_id: str
    ) -> list[dict[str, Any]]:
        return [
            document
            for (tenant, project, request, _), document in self.documents.items()
            if (tenant, project, request) == (tenant_id, project_id, request_id)
        ]


def runtime(repository: RecordingRepository) -> IdentityDiagnosticRuntime:
    return IdentityDiagnosticRuntime(
        repository,
        tenant_id="tenant-a",
        project_id="project-a",
        clock=ManualClock(1_777_000_000.0),
    )


@pytest.mark.parametrize(
    ("dimension", "reason"),
    [
        (IdentityDimension.TENANT, CacheOutcomeReason.TENANT_CHANGED),
        (IdentityDimension.TRUST_NAMESPACE, CacheOutcomeReason.TRUST_NAMESPACE_CHANGED),
        (IdentityDimension.MODEL, CacheOutcomeReason.MODEL_CHANGED),
        (IdentityDimension.TOOL_SCHEMA, CacheOutcomeReason.TOOL_SCHEMA_CHANGED),
        (IdentityDimension.LOCKFILE, CacheOutcomeReason.LOCKFILE_CHANGED),
        (IdentityDimension.ENVIRONMENT, CacheOutcomeReason.ENVIRONMENT_CHANGED),
        (IdentityDimension.VALIDATION, CacheOutcomeReason.VALIDATION_REQUIREMENT_CHANGED),
    ],
)
def test_real_identity_dimensions_persist_only_first_difference_digests(
    dimension: IdentityDimension,
    reason: CacheOutcomeReason,
) -> None:
    repository = RecordingRepository()
    raw_before = "raw-secret-before"
    raw_after = "raw-secret-after"
    document = runtime(repository).record_miss(
        request_id=f"request-{dimension.value}",
        layer=CacheLayer.ACTION,
        previous_identity={dimension.value: raw_before},
        current_identity={dimension.value: raw_after},
        lost_value=LostValue(compute_ms=12.5, model_tokens=7),
    )

    assert document["reason_code"] == reason.value
    assert document["outcome"] == "NECESSARY_MISS"
    assert document["first_difference"]["dimension"] == dimension.value
    encoded = json.dumps(document, sort_keys=True)
    assert raw_before not in encoded
    assert raw_after not in encoded


def test_shard_change_is_an_unexpected_miss_and_unknown_is_fail_closed() -> None:
    repository = RecordingRepository()
    service = runtime(repository)
    shard = service.record_miss(
        request_id="request-shard",
        layer=CacheLayer.COORDINATOR,
        previous_identity={"shard": "runner-a"},
        current_identity={"shard": "runner-b"},
    )
    unknown = service.record_miss(
        request_id="request-unknown",
        layer=CacheLayer.CONTEXT,
        previous_identity={"model": "same"},
        current_identity={"model": "same"},
    )

    assert shard["reason_code"] == "WRONG_SHARD"
    assert shard["outcome"] == "UNEXPECTED_MISS"
    assert unknown["reason_code"] == "UNKNOWN_MISS"
    assert unknown["outcome"] == "UNEXPECTED_MISS"


def test_unknown_dimension_and_invalid_value_refuse_before_persistence() -> None:
    repository = RecordingRepository()
    service = runtime(repository)
    with pytest.raises(ContractViolation):
        service.record_miss(
            request_id="request-open",
            layer=CacheLayer.ACTION,
            previous_identity={"raw_prompt": "secret"},
            current_identity={"raw_prompt": "changed"},
        )
    with pytest.raises(ContractViolation):
        service.record_miss(
            request_id="request-cost",
            layer=CacheLayer.ACTION,
            previous_identity={"model": "a"},
            current_identity={"model": "b"},
            lost_value=LostValue(compute_ms=-1),
        )
    assert repository.documents == {}


def test_summary_is_derived_from_durable_events_without_double_counting() -> None:
    repository = RecordingRepository()
    service = runtime(repository)
    for dimension, before, after, value in (
        ("model", "m1", "m2", LostValue(compute_ms=10, monetary_micros=3)),
        ("model", "m2", "m3", LostValue(compute_ms=4, monetary_micros=2)),
        ("environment", "e1", "e2", LostValue(bytes=128, critical_path_ms=7)),
    ):
        service.record_miss(
            request_id="request-summary",
            layer=CacheLayer.PROVIDER_PROMPT,
            previous_identity={dimension: before},
            current_identity={dimension: after},
            cohort=CacheCohort.INTERACTIVE,
            lost_value=value,
        )

    summary = service.summarize("request-summary")
    assert summary.events == 3
    assert summary.unknown_events == 0
    assert summary.by_reason == (("MODEL_CHANGED", 2), ("ENVIRONMENT_CHANGED", 1))
    assert summary.total_lost_value.compute_ms == 14
    assert summary.total_lost_value.bytes == 128
    assert summary.total_lost_value.monetary_micros == 5
    assert summary.to_dict()["summary_digest"].startswith("sha256:")


def test_same_event_is_retry_stable_across_runtime_reconstruction() -> None:
    repository = RecordingRepository()
    first = runtime(repository).record_miss(
        request_id="request-replay",
        layer=CacheLayer.ENVIRONMENT,
        previous_identity={"environment": {"digest": "old"}},
        current_identity={"environment": {"digest": "new"}},
    )
    second = runtime(repository).record_miss(
        request_id="request-replay",
        layer=CacheLayer.ENVIRONMENT,
        previous_identity={"environment": {"digest": "old"}},
        current_identity={"environment": {"digest": "new"}},
    )
    assert second == first
    assert len(repository.documents) == 1
