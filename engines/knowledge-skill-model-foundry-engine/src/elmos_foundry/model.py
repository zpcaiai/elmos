"""Private adapter foundry, LoRA configuration, parameter provenance, and release packaging.

Manages adapter training specs and whole-combination immutable release packaging.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Mapping, Sequence

from .domain import (
    ContentDigest,
    GateLevel,
    LifecycleState,
    ModelRelease,
    TenantScope,
)
from .kernel import ExecutionKernel


class ModelFoundry:
    """Enterprise private model and adapter release factory."""

    def __init__(self, kernel: ExecutionKernel | None = None) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._releases: dict[str, ModelRelease] = {}

    def generate_adapter_config(
        self,
        base_model: str,
        adapter_type: str = "lora",
        rank: int = 16,
        alpha: int = 32,
        dropout: float = 0.05,
        target_modules: Sequence[str] | None = None,
    ) -> Mapping[str, Any]:
        """Generate PEFT-compatible LoRA/QLoRA training configuration."""
        targets = target_modules or ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
        return {
            "adapter_type": adapter_type,
            "base_model": base_model,
            "r": rank,
            "lora_alpha": alpha,
            "lora_dropout": dropout,
            "target_modules": list(targets),
            "bias": "none",
            "task_type": "CAUSAL_LM",
            "quantization": "4bit" if adapter_type == "qlora" else "none",
        }

    def package_release(
        self,
        base_model: str,
        adapter_name: str,
        version: str,
        skill_set: Sequence[str],
        weights_bytes: bytes,
        knowledge_snapshot_digest: str,
        policy_bundle_digest: str,
        gate_level: GateLevel = GateLevel.E0_SYNTACTIC,
        tenant_scope: TenantScope | None = None,
    ) -> ModelRelease:
        """Create an immutable whole-combination release bundle."""
        scope = tenant_scope or self.kernel.current_tenant
        release_id = f"rel-{uuid.uuid4().hex[:12]}"
        weights_digest = ContentDigest.of(weights_bytes)

        release = ModelRelease(
            release_id=release_id,
            base_model=base_model,
            adapter_name=adapter_name,
            version=version,
            tenant_id=scope.tenant_id,
            weights_digest=weights_digest,
            skill_set=list(skill_set),
            knowledge_snapshot_digest=knowledge_snapshot_digest,
            policy_bundle_digest=policy_bundle_digest,
            gate_level=gate_level,
            status=LifecycleState.PLANNED,
        )
        self._releases[release_id] = release
        return release

    def get_release(self, release_id: str, tenant_scope: TenantScope | None = None) -> ModelRelease | None:
        scope = tenant_scope or self.kernel.current_tenant
        rel = self._releases.get(release_id)
        if rel is not None and rel.tenant_id == scope.tenant_id:
            return rel
        return None

    def promote_release(
        self,
        release_id: str,
        new_gate: GateLevel,
        tenant_scope: TenantScope | None = None,
    ) -> ModelRelease:
        scope = tenant_scope or self.kernel.current_tenant
        rel = self.get_release(release_id, scope)
        if rel is None:
            raise ValueError(f"Release {release_id} not found")

        updated = ModelRelease(
            release_id=rel.release_id,
            base_model=rel.base_model,
            adapter_name=rel.adapter_name,
            version=rel.version,
            tenant_id=rel.tenant_id,
            weights_digest=rel.weights_digest,
            skill_set=rel.skill_set,
            knowledge_snapshot_digest=rel.knowledge_snapshot_digest,
            policy_bundle_digest=rel.policy_bundle_digest,
            gate_level=new_gate,
            status=LifecycleState.CERTIFIED if new_gate == GateLevel.E4_PRODUCTION_CERTIFIED else LifecycleState.VERIFYING,
            created_at=rel.created_at,
        )
        self._releases[release_id] = updated
        return updated
