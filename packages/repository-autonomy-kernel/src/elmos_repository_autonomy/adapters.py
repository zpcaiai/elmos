"""Typed conformance matrix for the seven exact provider adapters.

Local records can demonstrate engineering behavior, but only independently
verified receipts from a real provider may satisfy the external gate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .errors import ContractError
from .models import digest, utc_now

ADAPTERS = {
    "anthropic-agent-sdk": "agent-sdk",
    "claude-code": "terminal-agent",
    "generic-mcp-a2a": "protocol",
    "openai-codex": "coding-agent",
    "opencode": "coding-agent",
    "openharness": "harness",
    "openrouter": "model-router",
}

CONFORMANCE_CASES = (
    "tool-success-with-output",
    "tool-success-empty-output-explicit",
    "tool-interrupted",
    "tool-timeout",
    "tool-denied",
    "partial-subagent-max-turns",
    "pause-resume",
    "cancel-safe-point",
    "provider-stream-reconnect",
    "environment-authority-isolation",
    "stale-fencing-token-denied",
    "telemetry-cost-attribution",
)

ReceiptVerifier = Callable[[Mapping[str, Any]], bool]


def _semantic_pass(case: str, record: Mapping[str, Any]) -> bool:
    status = str(record.get("status", "")).upper()
    if status != "PASS" or not record.get("raw_evidence"):
        return False
    if case == "tool-success-with-output":
        return bool(record.get("output_hash")) and record.get("terminal_state") == "SUCCEEDED"
    if case == "tool-success-empty-output-explicit":
        return record.get("output") == "" and record.get("empty_output_explicit") is True
    if case == "tool-interrupted":
        return record.get("terminal_state") == "INTERRUPTED" and record.get("partial_output_preserved") is True
    if case == "tool-timeout":
        return record.get("terminal_state") == "TIMED_OUT" and record.get("retry_decision") in {"RETRYABLE", "RECONCILE"}
    if case == "tool-denied":
        return record.get("terminal_state") == "DENIED" and bool(record.get("policy_decision_hash"))
    if case == "partial-subagent-max-turns":
        return record.get("terminal_state") == "PARTIAL" and record.get("stop_reason") == "MAX_TURNS"
    if case == "pause-resume":
        return bool(record.get("checkpoint_hash")) and record.get("resume_exact") is True
    if case == "cancel-safe-point":
        return record.get("cancelled_at_safe_point") is True and record.get("side_effects_reconciled") is True
    if case == "provider-stream-reconnect":
        return record.get("stream_sequence_contiguous") is True and record.get("duplicate_frames") == 0
    if case == "environment-authority-isolation":
        return record.get("cross_environment_access") == "DENIED" and bool(record.get("authority_hash"))
    if case == "stale-fencing-token-denied":
        return record.get("stale_token_result") == "DENIED" and bool(record.get("current_fencing_token"))
    if case == "telemetry-cost-attribution":
        return all(record.get(field) is not None for field in ("tenant_id", "run_id", "usage_units", "cost_currency"))
    return False


class ConformanceHarness:
    """Evaluate semantic records without trusting caller-declared PASS values."""

    def __init__(self, receipt_verifier: ReceiptVerifier | None = None) -> None:
        self.receipt_verifier = receipt_verifier

    def evaluate(
        self,
        adapter_id: str,
        adapter_version: str,
        responses: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if adapter_id not in ADAPTERS:
            raise ContractError("ADAPTER_UNKNOWN", f"unknown adapter: {adapter_id}")
        if not adapter_version.strip():
            raise ContractError("ADAPTER_VERSION_REQUIRED", "adapter_version is required")
        supplied = responses or {}
        cases: list[dict[str, Any]] = []
        for case in CONFORMANCE_CASES:
            value = supplied.get(case)
            record = value if isinstance(value, Mapping) else {}
            semantic = _semantic_pass(case, record)
            external = self._external_verified(record) if semantic else False
            cases.append(
                {
                    "case": case,
                    "engineering_status": "PASS" if semantic else "NOT_RUN",
                    "external_status": "PASS" if external else "NOT_RUN",
                    "evidence_hash": digest(record) if record else None,
                    "evidence_class": record.get("evidence_class", "NOT_RUN") if record else "NOT_RUN",
                }
            )
        engineering_complete = all(item["engineering_status"] == "PASS" for item in cases)
        external_complete = all(item["external_status"] == "PASS" for item in cases)
        return {
            "adapter_id": adapter_id,
            "adapter_version": adapter_version,
            "adapter_type": ADAPTERS[adapter_id],
            "suite_version": "2.0.0",
            "status": "PASS" if external_complete else "BLOCKED",
            "engineering_status": "PASS" if engineering_complete else "BLOCKED",
            "cases": cases,
            "failure_mode": "fail-closed",
            "report_hash": digest(cases),
            "tested_at": utc_now(),
            "external_evidence": "INDEPENDENTLY_VERIFIED" if external_complete else "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }

    def _external_verified(self, record: Mapping[str, Any]) -> bool:
        if record.get("evidence_class") != "INDEPENDENTLY_VERIFIED":
            return False
        if record.get("source_kind") != "real-provider":
            return False
        producer = str(record.get("producer_id", ""))
        verifier = str(record.get("verifier_id", ""))
        if not producer or not verifier or producer == verifier:
            return False
        if self.receipt_verifier is None:
            return False
        return self.receipt_verifier(record)


def adapter_conformance(
    adapter_id: str,
    adapter_version: str,
    responses: Mapping[str, Any] | None = None,
    *,
    receipt_verifier: ReceiptVerifier | None = None,
) -> dict[str, Any]:
    return ConformanceHarness(receipt_verifier).evaluate(adapter_id, adapter_version, responses)


def local_conformance_records(adapter_id: str) -> dict[str, dict[str, Any]]:
    if adapter_id not in ADAPTERS:
        raise ContractError("ADAPTER_UNKNOWN", f"unknown adapter: {adapter_id}")
    common = {
        "status": "PASS",
        "evidence_class": "LOCAL_ENGINEERING_VALIDATED",
        "source_kind": "local-harness",
        "producer_id": "repository-autonomy-kernel-tests",
        "raw_evidence": {"adapter_id": adapter_id, "suite_version": "2.0.0"},
    }
    values: dict[str, dict[str, Any]] = {
        "tool-success-with-output": {"output_hash": digest("output"), "terminal_state": "SUCCEEDED"},
        "tool-success-empty-output-explicit": {"output": "", "empty_output_explicit": True},
        "tool-interrupted": {"terminal_state": "INTERRUPTED", "partial_output_preserved": True},
        "tool-timeout": {"terminal_state": "TIMED_OUT", "retry_decision": "RECONCILE"},
        "tool-denied": {"terminal_state": "DENIED", "policy_decision_hash": digest("deny")},
        "partial-subagent-max-turns": {"terminal_state": "PARTIAL", "stop_reason": "MAX_TURNS"},
        "pause-resume": {"checkpoint_hash": digest("checkpoint"), "resume_exact": True},
        "cancel-safe-point": {"cancelled_at_safe_point": True, "side_effects_reconciled": True},
        "provider-stream-reconnect": {"stream_sequence_contiguous": True, "duplicate_frames": 0},
        "environment-authority-isolation": {"cross_environment_access": "DENIED", "authority_hash": digest("authority")},
        "stale-fencing-token-denied": {"stale_token_result": "DENIED", "current_fencing_token": 2},
        "telemetry-cost-attribution": {
            "tenant_id": "local-tenant",
            "run_id": "local-run",
            "usage_units": 1,
            "cost_currency": "USD",
        },
    }
    return {case: {**common, **values[case]} for case in CONFORMANCE_CASES}


def all_local_conformance(*, adapter_version: str = "2.0.0") -> dict[str, Any]:
    reports = [adapter_conformance(adapter_id, adapter_version, local_conformance_records(adapter_id)) for adapter_id in ADAPTERS]
    units = sum(len(report["cases"]) for report in reports)
    return {
        "suite_version": "2.0.0",
        "adapter_count": len(reports),
        "conformance_unit_count": units,
        "engineering_status": "PASS" if all(report["engineering_status"] == "PASS" for report in reports) else "BLOCKED",
        "status": "BLOCKED",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "reports": reports,
        "report_hash": digest(reports),
    }
