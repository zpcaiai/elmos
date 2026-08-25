from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from elmos_repository_orchestrator.catalog import MODEL_ALIASES


NOW = "2026-08-24T12:00:00Z"


def registry_payload(overrides: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    aliases: dict[str, Any] = {}
    for index, alias in enumerate(MODEL_ALIASES):
        quality = "0.80"
        affinity = "0.50"
        latency = str(900 + index * 10)
        input_price = str(5 + index)
        if index == 0:
            quality, affinity, latency, input_price = "0.80", "0.10", "500", "1"
        elif index == 1:
            quality, affinity, latency, input_price = "0.85", "1.00", "800", "2"
        elif index == 9:
            quality, affinity, latency, input_price = "0.99", "0.80", "50", "10"
        aliases[alias] = {
            "provider": f"provider-{index}",
            "provider_model_id": f"native-{index}",
            "deployment_id": f"deployment-{index}",
            "model_revision": f"revision-{index}",
            "enabled": True,
            "available": True,
            "capability_tier": "L4",
            "pricing": {
                "input_per_million": input_price,
                "cached_input_per_million": "0.1",
                "output_per_million": str(10 + index),
                "fixed_cost": "0",
                "currency": "USD",
                "effective_at": "2026-08-24T00:00:00Z",
            },
            "limits": {"context_tokens": 200000, "max_output_tokens": 32000, "concurrency": 10},
            "active_calls": 0,
            "quota_remaining": 100,
            "allowed_residencies": ["US", "CN"],
            "allowed_privacy_classes": ["public", "confidential"],
            "private_repository_allowed": True,
            "tools": ["code", "search"],
            "predicted_success": "0.90",
            "predicted_quality": quality,
            "cache_affinity": affinity,
            "latency_ms": latency,
            "integration_risk_cost": "0",
        }
    for alias, fields in (overrides or {}).items():
        for key, value in fields.items():
            if key == "pricing" and isinstance(value, Mapping):
                aliases[alias][key].update(value)
            elif key == "limits" and isinstance(value, Mapping):
                aliases[alias][key].update(value)
            else:
                aliases[alias][key] = deepcopy(value)
    return {
        "aliases": aliases,
        "observed_at": "2026-08-24T11:30:00Z",
        "max_age_seconds": 86400,
        "source": "test_fixture",
        "authorization_id": "AUTH-REGISTRY-001",
    }


def task_profile(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "task_id": "T001",
        "task_class": "backend_standard",
        "prompt_tokens": 10000,
        "cached_input_tokens": 5000,
        "output_tokens": 1000,
        "required_tools": ["code"],
        "residency": "US",
        "privacy_class": "confidential",
        "private_repository": True,
        "risk": {},
        "long_horizon": False,
        "minimum_quality": "0.70",
        "expected_escalation_cost": "0.10",
        "retry_penalty": "0.01",
        "task_budget_remaining": "100",
        "run_budget_remaining": "1000",
    }
    value.update(overrides)
    return value


def selection_payload(*, mode: str = "smart", profile: str = "cost_performance", **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "mode": mode,
        "selected_model": None if mode == "smart" else MODEL_ALIASES[0],
        "optimization_profile": profile,
        "fallback_policy": "strict",
        "verification_policy": "system_required_verifiers",
    }
    value.update(overrides)
    return value


def atomic_task(task_id: str = "T001", *, dependencies: list[str] | None = None, owned: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": f"Task {task_id}",
        "objective": f"Implement {task_id}",
        "task_class": "backend_standard",
        "owned_paths": owned if owned is not None else [f"src/{task_id.lower()}.py"],
        "read_paths": [],
        "forbidden_paths": ["secrets/**"],
        "dependencies": dependencies or [],
        "acceptance": [f"{task_id} focused test passes"],
        "risk": {},
        "complexity": {"state": "not_run"},
        "status": "planned",
    }
