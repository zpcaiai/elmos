"""Digest-only adapter packaging and conservative local release promotion."""

from __future__ import annotations

from dataclasses import replace
import math
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .authorizations import AuthorizationBoundaryError, AuthorizationVerifier, require_authorization
from .canonical import canonical_digest, validate_digest
from .domain import (
    CertificationStatus,
    ContentDigest,
    EvidenceState,
    GateLevel,
    LifecycleState,
    ModelRelease,
    TenantScope,
)
from .evidence import EvidenceLedger
from .kernel import ExecutionKernel, KernelStateError
from .policies import PolicyEngine


class ModelFoundry:
    """Create immutable release metadata without training or storing weights."""

    def __init__(
        self,
        kernel: ExecutionKernel | None = None,
        *,
        evidence_ledger: EvidenceLedger | None = None,
        policy_engine: PolicyEngine | None = None,
        promotion_verifier: AuthorizationVerifier | None = None,
    ) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._evidence_ledger = evidence_ledger
        self._policy_engine = policy_engine or PolicyEngine(self.kernel.require_context)
        self._promotion_verifier = promotion_verifier
        self._releases: dict[tuple[str, str, str], ModelRelease] = {}
        self._lock = RLock()

    def generate_adapter_config(
        self,
        base_model: str,
        adapter_type: str = "lora",
        rank: int = 16,
        alpha: int = 32,
        dropout: float = 0.05,
        target_modules: Sequence[str] | None = None,
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.model.plan")
        if adapter_type not in {"lora", "qlora"}:
            raise ValueError("adapter_type must be lora or qlora")
        if not base_model.strip() or not 1 <= rank <= 4096 or not 1 <= alpha <= 65536:
            raise ValueError("adapter configuration is outside bounded limits")
        if not math.isfinite(dropout) or not 0 <= dropout < 1:
            raise ValueError("dropout must be finite and in [0, 1)")
        targets = tuple(target_modules or ())
        if not targets or len(targets) > 256 or len(set(targets)) != len(targets):
            raise ValueError("target_modules must be a non-empty unique bounded list")
        plan = {
            "adapter_type": adapter_type,
            "base_model": base_model,
            "rank": rank,
            "alpha": alpha,
            "dropout": dropout,
            "target_modules": sorted(targets),
            "quantization": "4bit-plan" if adapter_type == "qlora" else "none",
            "semantic_execution_status": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
        return MappingProxyType({**plan, "plan_digest": canonical_digest(plan)})

    def package_release(
        self,
        base_model: str,
        adapter_name: str,
        version: str,
        skill_set: Sequence[str],
        weights_digest: ContentDigest,
        knowledge_snapshot_digest: str,
        policy_bundle_digest: str,
        gate_level: GateLevel = GateLevel.E0_SYNTACTIC,
        tenant_scope: TenantScope | None = None,
    ) -> ModelRelease:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.model.package")
        validate_digest(knowledge_snapshot_digest, "knowledge_snapshot_digest")
        validate_digest(policy_bundle_digest, "policy_bundle_digest")
        if gate_level not in {GateLevel.E0_SYNTACTIC, GateLevel.E1_UNIT_EVAL}:
            raise KernelStateError("local packaging cannot claim an E2-E5 gate")
        if not skill_set or len(set(skill_set)) != len(skill_set):
            raise ValueError("skill_set must be non-empty and unique")
        identity = canonical_digest(
            {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "base_model": base_model,
                "adapter_name": adapter_name,
                "version": version,
                "skills": sorted(skill_set),
                "weights_digest": str(weights_digest),
                "knowledge_snapshot_digest": knowledge_snapshot_digest,
                "policy_bundle_digest": policy_bundle_digest,
            }
        )
        release = ModelRelease(
            release_id="rel-" + identity.removeprefix("sha256:")[:32],
            base_model=base_model,
            adapter_name=adapter_name,
            version=version,
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            weights_digest=weights_digest,
            skill_set=tuple(sorted(skill_set)),
            knowledge_snapshot_digest=knowledge_snapshot_digest,
            policy_bundle_digest=policy_bundle_digest,
            gate_level=gate_level,
            status=LifecycleState.PLANNED,
            evidence_state=EvidenceState.COLLECTED_SELF_ATTESTED,
            external_evidence_status="NOT_RUN",
            certification_status=CertificationStatus.NOT_CERTIFIED,
        )
        with self._lock:
            self._releases[(scope.tenant_id, scope.project_id, release.release_id)] = release
        return release

    def get_release(
        self, release_id: str, tenant_scope: TenantScope | None = None
    ) -> ModelRelease | None:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.model.read")
        with self._lock:
            return self._releases.get((scope.tenant_id, scope.project_id, release_id))

    def promote_release(
        self,
        release_id: str,
        new_gate: GateLevel,
        tenant_scope: TenantScope | None = None,
        *,
        evidence_bundle_id: str,
        promotion_authorization_digest: str,
    ) -> ModelRelease:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.model.promote")
        if new_gate is not GateLevel.E1_UNIT_EVAL:
            raise KernelStateError("E2-E5 promotion requires an external gate adapter")
        if self._evidence_ledger is None:
            raise AuthorizationBoundaryError(
                "model promotion requires a durable evidence ledger"
            )
        with self._lock:
            key = (scope.tenant_id, scope.project_id, release_id)
            current = self._releases.get(key)
            if current is None:
                raise ValueError("release not found in authenticated scope")
            if current.gate_level is not GateLevel.E0_SYNTACTIC:
                raise KernelStateError("only an E0 release may receive local E1 evidence")
            bundle = self._evidence_ledger.get_bundle(evidence_bundle_id, scope)
            if bundle is None:
                raise AuthorizationBoundaryError("promotion evidence bundle was not found")
            if (
                bundle.target_id != current.release_id
                or bundle.target_type != "model_release"
                or bundle.gate_level is not GateLevel.E1_UNIT_EVAL
                or bundle.verdict != "PASS"
                or bundle.tenant_id != scope.tenant_id
                or bundle.project_id != scope.project_id
                or not self._evidence_ledger.verify_bundle_integrity(bundle)
            ):
                raise AuthorizationBoundaryError(
                    "promotion evidence is invalid, mismatched, or non-passing"
                )
            obligations_satisfied = bool(bundle.proof_obligations) and all(
                item.get("status") == "SATISFIED_LOCAL"
                for item in bundle.proof_obligations
            )
            decision = self._policy_engine.evaluate_model_promotion(
                new_gate,
                bundle.metrics,
                obligations_satisfied,
            )
            if decision.get("approved") is not True:
                raise AuthorizationBoundaryError("model promotion policy denied the request")
            authorization = require_authorization(
                self._promotion_verifier,
                authorization_type="model-e1-promotion",
                receipt_digest=promotion_authorization_digest,
                request={
                    "release_id": current.release_id,
                    "current_gate": current.gate_level.value,
                    "target_gate": new_gate.value,
                    "evidence_bundle_digest": bundle.bundle_digest,
                    "policy_decision": decision,
                },
                scope=scope,
            )
            if self._evidence_ledger.store is None:
                raise AuthorizationBoundaryError(
                    "model promotion requires a durable event store"
                )
            self._evidence_ledger.store.append_event(
                scope,
                current.release_id,
                "model.release.promoted.local-e1",
                {
                    "from_gate": current.gate_level.value,
                    "to_gate": new_gate.value,
                    "evidence_bundle_digest": bundle.bundle_digest,
                    "authorization_request_digest": authorization.request_digest,
                    "certification_status": "NOT_CERTIFIED",
                },
            )
            updated = replace(
                current,
                gate_level=GateLevel.E1_UNIT_EVAL,
                status=LifecycleState.VERIFYING,
                evidence_state=EvidenceState.COLLECTED_SELF_ATTESTED,
            )
            self._releases[key] = updated
            return updated


__all__ = ["ModelFoundry"]
