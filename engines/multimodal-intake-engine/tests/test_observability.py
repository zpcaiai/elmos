from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from elmos_multimodal_intake.skill_runtime import dispatch_skill


def request(inputs: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_id": "request-observability",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "inputs": dict(inputs),
        **extra,
    }


def json_sha(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def test_cost_eta_requires_trusted_provenance_and_uses_critical_path() -> None:
    skill = "elmos-processing-cost-and-eta-estimation"
    inputs = {
        "history": [],
        "prices": [{"provider": "provider-a", "unit": "page", "price_per_unit": "0.125", "currency": "USD"}],
        "stages": [
            {
                "stage_id": "ocr-a",
                "stage": "ocr",
                "provider": "provider-a",
                "file_type": "image/png",
                "progress": 0,
                "elapsed_machine_seconds": 0,
                "declared_upper_bound_seconds": 10,
                "quantity": "2",
                "unit": "page",
                "depends_on": [],
            },
            {
                "stage_id": "ocr-b",
                "stage": "ocr-secondary",
                "provider": "provider-a",
                "file_type": "image/png",
                "progress": 0,
                "elapsed_machine_seconds": 0,
                "declared_upper_bound_seconds": 20,
                "quantity": "1",
                "unit": "page",
                "depends_on": [],
            },
            {
                "stage_id": "merge",
                "stage": "merge",
                "provider": "local",
                "file_type": "application/json",
                "progress": 0,
                "elapsed_machine_seconds": 0,
                "declared_upper_bound_seconds": 5,
                "quantity": "0",
                "unit": "none",
                "depends_on": ["ocr-a", "ocr-b"],
            },
        ],
    }
    missing_policy = dispatch_skill(skill, request(inputs))
    assert missing_policy["state"] == "BLOCKED"
    assert missing_policy["code"] == "TRUSTED_ESTIMATION_POLICY_REQUIRED"

    policy = {
        "observability": {
            "history_digest": json_sha(inputs["history"]),
            "prices_digest": json_sha(inputs["prices"]),
            "calibration_version": "calibration-v1",
            "default_currency": "USD",
        }
    }
    result = dispatch_skill(skill, request(inputs, policy=policy))
    assert result["state"] == "SUCCEEDED"
    assert result["outputs"]["remaining_seconds_p50"] == 15.0
    assert result["outputs"]["remaining_seconds_p95"] == 25.0
    assert result["outputs"]["estimated_cost"] == "0.375000"


def test_observability_uses_trusted_required_stages_and_redacts_nested_sequences() -> None:
    result = dispatch_skill(
        "elmos-multimodal-observability",
        request(
            {
                "events": [
                    {
                        "event_id": "event-a",
                        "event_type": "stage.complete",
                        "labels": {"stage": "upload", "status": "ready"},
                        "attributes": {"nested": [{"message": "do not retain this"}]},
                    }
                ]
            },
            trace_id="trace-observability",
            policy={
                "observability": {
                    "required_stages": ["upload", "parse"],
                    "label_cardinality_limit": 10,
                    "policy_version": "telemetry-v1",
                }
            },
        ),
    )
    assert result["state"] == "PARTIAL"
    assert result["outputs"]["missing_stages"] == ["parse"]
    assert result["outputs"]["events"][0]["attributes"]["nested"][0]["message"] == "[REDACTED]"
    assert result["outputs"]["secrets_redacted"] == "DEFAULT_DENY_UNAPPROVED_TEXT"
    assert result["outputs"]["attribute_string_policy"] == "REDACT_ALL_UNTYPED_STRINGS"


def test_observability_identifiers_labels_and_parents_fail_closed_without_secret_echo() -> None:
    policy = {
        "observability": {
            "required_stages": ["upload"],
            "label_cardinality_limit": 10,
            "policy_version": "telemetry-v1",
        }
    }
    base_event = {
        "event_id": "event-a",
        "event_type": "stage.complete",
        "labels": {"stage": "upload", "status": "ready"},
        "attributes": {},
    }
    sensitive = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    bearer_secret = "Bearer secret-token-value"
    invalid_events = [
        ({**base_event, "event_id": sensitive}, sensitive),
        ({**base_event, "event_type": bearer_secret}, bearer_secret),
        ({**base_event, "parent_event_id": sensitive}, sensitive),
        ({**base_event, "labels": {"stage": "upload", "provider": sensitive}}, sensitive),
        (
            {**base_event, "labels": {"stage": "upload", "status": "x" * 129}},
            "x" * 129,
        ),
    ]
    for event, forbidden_value in invalid_events:
        result = dispatch_skill(
            "elmos-multimodal-observability",
            request(
                {"events": [event]},
                trace_id="trace-observability",
                policy=policy,
            ),
        )
        assert result["state"] == "BLOCKED"
        assert forbidden_value not in json.dumps(result)

    dangling_parent = dispatch_skill(
        "elmos-multimodal-observability",
        request(
            {
                "events": [
                    {**base_event, "event_id": "child", "parent_event_id": "future-parent"},
                    {**base_event, "event_id": "future-parent"},
                ]
            },
            trace_id="trace-observability",
            policy=policy,
        ),
    )
    assert dangling_parent["state"] == "BLOCKED"


def test_observability_redaction_covers_sensitive_values_outside_sensitive_keys() -> None:
    secrets = {
        "authorization_value": "Bearer abcdefghijklmnopqrstuvwxyz",
        "api_credential": "sk-proj-abcdefghijklmnopqrstuvwxyz012345",
        "owner_address": "private.person@example.test",
        "database_location": "postgres://private-user:private-pass@example.test/db",
    }
    result = dispatch_skill(
        "elmos-multimodal-observability",
        request(
            {
                "events": [
                    {
                        "event_id": "event-a",
                        "event_type": "stage.complete",
                        "labels": {"stage": "upload", "status": "ready"},
                        "attributes": {"details": list(secrets.values())},
                    },
                    {
                        "event_id": "event-b",
                        "event_type": "stage.persisted",
                        "parent_event_id": "event-a",
                        "labels": {"stage": "upload", "status": "ready"},
                        "attributes": {},
                    },
                ]
            },
            trace_id="trace-observability",
            policy={
                "observability": {
                    "required_stages": ["upload"],
                    "label_cardinality_limit": 10,
                    "policy_version": "telemetry-v1",
                }
            },
        ),
    )
    assert result["state"] == "SUCCEEDED"
    serialized = json.dumps(result["outputs"], ensure_ascii=False)
    assert result["outputs"]["redaction_applied"] is True
    for secret in secrets.values():
        assert secret not in serialized
    assert "[REDACTED_UNAPPROVED_TEXT]" in serialized


def test_observability_default_denies_arbitrary_unapproved_text() -> None:
    raw_values = [
        "custom-secret-with-no-known-prefix",
        "ordinary prose copied from a private source document",
        "low-entropy-password-value",
    ]
    result = dispatch_skill(
        "elmos-multimodal-observability",
        request(
            {
                "events": [
                    {
                        "event_id": "event-a",
                        "event_type": "stage.complete",
                        "labels": {"stage": "upload", "status": "ready"},
                        "attributes": {
                            "note": raw_values[0],
                            "nested": [raw_values[1], {"detail": raw_values[2]}],
                            "attempt_count": 2,
                            "cache_hit": False,
                        },
                    }
                ]
            },
            trace_id="trace-observability",
            policy={
                "observability": {
                    "required_stages": ["upload"],
                    "label_cardinality_limit": 10,
                    "policy_version": "telemetry-v1",
                }
            },
        ),
    )
    assert result["state"] == "SUCCEEDED"
    attributes = result["outputs"]["events"][0]["attributes"]
    assert attributes == {
        "note": "[REDACTED_UNAPPROVED_TEXT]",
        "nested": [
            "[REDACTED_UNAPPROVED_TEXT]",
            {"detail": "[REDACTED_UNAPPROVED_TEXT]"},
        ],
        "attempt_count": 2,
        "cache_hit": False,
    }
    encoded = json.dumps(result, ensure_ascii=False)
    for raw in raw_values:
        assert raw not in encoded
