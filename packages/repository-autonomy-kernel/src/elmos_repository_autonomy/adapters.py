"""Provider-neutral harness adapter conformance boundary."""

from __future__ import annotations

from collections.abc import Mapping
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
    "tool-success-with-output", "tool-success-empty-output-explicit", "tool-interrupted", "tool-timeout",
    "tool-denied", "partial-subagent-max-turns", "pause-resume", "cancel-safe-point",
    "provider-stream-reconnect", "environment-authority-isolation", "stale-fencing-token-denied",
    "telemetry-cost-attribution",
)


def adapter_conformance(adapter_id: str, adapter_version: str, responses: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if adapter_id not in ADAPTERS:
        raise ContractError("ADAPTER_UNKNOWN", f"unknown adapter: {adapter_id}")
    supplied = responses or {}
    cases = []
    for case in CONFORMANCE_CASES:
        value = supplied.get(case)
        status = "PASS" if value is True or (isinstance(value, Mapping) and str(value.get("status", "")).upper() == "PASS") else "NOT_RUN"
        cases.append({"case": case, "status": status, "evidence": value if isinstance(value, Mapping) else None})
    overall = "PASS" if all(item["status"] == "PASS" for item in cases) else "BLOCKED"
    return {"adapter_id": adapter_id, "adapter_version": adapter_version, "adapter_type": ADAPTERS[adapter_id], "suite_version": "2.0.0", "status": overall, "cases": cases, "failure_mode": "fail-closed", "report_hash": digest(cases), "tested_at": utc_now(), "external_evidence": "NOT_RUN" if overall != "PASS" else "LOCAL_ENGINEERING_VALIDATED"}
