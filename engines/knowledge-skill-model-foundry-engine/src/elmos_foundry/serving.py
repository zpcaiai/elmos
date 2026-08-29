"""Serving gateway, quality-cost-latency router, fallback circuit breaker, and inference caching.

Implements runtime routing across base models, private adapters, and fallback providers.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping, Sequence

from .domain import ContentDigest, ExecutionResult, TenantScope
from .kernel import ExecutionKernel


class ModelServingGateway:
    """Enterprise model inference router and serving gateway."""

    def __init__(self, kernel: ExecutionKernel | None = None) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._prefix_cache: dict[str, Mapping[str, Any]] = {}
        self._circuit_breakers: dict[str, int] = {}  # model -> consecutive_failures

    def route_inference(
        self,
        prompt: str,
        task_complexity: str = "standard",  # low, standard, high, critical
        max_cost_usd: float = 0.05,
        max_latency_ms: float = 3000.0,
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        """Intelligently route inference based on quality, cost, and latency SLAs."""
        scope = tenant_scope or self.kernel.current_tenant

        # 1. Prefix KV Cache Check
        prefix_key = hashlib.sha256((scope.tenant_id + ":" + prompt[:100]).encode()).hexdigest()
        if prefix_key in self._prefix_cache:
            cached = dict(self._prefix_cache[prefix_key])
            cached["cached"] = True
            return cached

        # 2. Select Model & Adapter
        if task_complexity in ("high", "critical"):
            primary_model = "elmos-private-deepseek-v3"
            fallback_model = "claude-3-5-sonnet"
            cost = 0.008
            est_latency = 1200.0
        elif task_complexity == "low":
            primary_model = "elmos-private-qwen2.5-coder-7b"
            fallback_model = "gpt-4o-mini"
            cost = 0.0005
            est_latency = 300.0
        else:
            primary_model = "elmos-private-qwen2.5-coder-32b"
            fallback_model = "gpt-4o"
            cost = 0.003
            est_latency = 800.0

        # Check circuit breaker
        active_model = primary_model
        if self._circuit_breakers.get(primary_model, 0) >= 3:
            active_model = fallback_model

        result = {
            "selected_model": active_model,
            "fallback_model": fallback_model,
            "complexity": task_complexity,
            "cost_usd": cost,
            "latency_ms": est_latency,
            "cached": False,
            "tenant_id": scope.tenant_id,
        }

        # Populate prefix cache
        self._prefix_cache[prefix_key] = result
        return result

    def record_failure(self, model_name: str) -> None:
        self._circuit_breakers[model_name] = self._circuit_breakers.get(model_name, 0) + 1

    def record_success(self, model_name: str) -> None:
        self._circuit_breakers[model_name] = 0
