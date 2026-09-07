"""Durable self-attested evidence with a conservative local gate ceiling."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
import time
import uuid
from typing import Any, cast

from .artifacts import ContentAddressedArtifactStore
from .canonical import (
    canonical_digest,
    canonical_json_bytes,
    canonical_value,
    require_identifier,
    strict_json_loads,
)
from .domain import CertificationStatus, EvidenceBundle, EvidenceState, GateLevel, TenantScope
from .kernel import ExecutionKernel
from .store import FoundryStore, RecordNotFound


class EvidenceBoundaryError(RuntimeError):
    pass


class EvidenceIntegrityError(RuntimeError):
    pass


class EvidenceLedger:
    WRITE_CAPABILITY = "foundry.evidence.write"
    READ_CAPABILITY = "foundry.evidence.read"

    def __init__(
        self,
        kernel: ExecutionKernel | None = None,
        *,
        store: FoundryStore | None = None,
        artifact_store: ContentAddressedArtifactStore | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.kernel = kernel or ExecutionKernel(clock=clock)
        self.store = store
        self.artifact_store = artifact_store
        self._clock = clock

    def _scope(self, value: TenantScope | None, capability: str) -> TenantScope:
        return self.kernel.require_context(value or self.kernel.current_tenant, capability)

    def _now(self) -> str:
        return (
            datetime.fromtimestamp(self._clock(), timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _leaves(
        *,
        target_id: str,
        target_type: str,
        gate_level: GateLevel,
        verdict: str,
        tenant_id: str,
        project_id: str,
        context_digest: str,
        proof_obligations: Sequence[Mapping[str, Any]],
        metrics: Mapping[str, Any],
    ) -> list[str]:
        leaves = [
            canonical_digest(
                {
                    "kind": "target",
                    "target_id": target_id,
                    "target_type": target_type,
                    "gate_level": gate_level.value,
                    "verdict": verdict,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "context_digest": context_digest,
                }
            )
        ]
        leaves.extend(
            canonical_digest({"kind": "proof_obligation", "index": index, "value": item})
            for index, item in enumerate(proof_obligations)
        )
        leaves.append(canonical_digest({"kind": "metrics", "value": metrics}))
        return leaves

    @staticmethod
    def _body(bundle: EvidenceBundle) -> Mapping[str, Any]:
        return {
            "schema_version": "elmos.foundry.evidence-bundle.v1",
            "bundle_id": bundle.bundle_id,
            "target_id": bundle.target_id,
            "target_type": bundle.target_type,
            "gate_level": bundle.gate_level.value,
            "verdict": bundle.verdict,
            "proof_obligations": list(bundle.proof_obligations),
            "metrics": dict(bundle.metrics),
            "merkle_root": bundle.merkle_root,
            "created_at": bundle.created_at,
            "tenant_id": bundle.tenant_id,
            "project_id": bundle.project_id,
            "context_digest": bundle.context_digest,
            "evidence_state": bundle.evidence_state.value,
            "external_evidence_status": bundle.external_evidence_status,
            "certification_status": bundle.certification_status.value,
            "independent_verifier": bundle.independent_verifier,
        }

    def seal_evidence_bundle(
        self,
        target_id: str,
        target_type: str,
        gate_level: GateLevel,
        verdict: str,
        proof_obligations: Sequence[Mapping[str, Any]],
        metrics: Mapping[str, Any],
        tenant_scope: TenantScope | None = None,
    ) -> EvidenceBundle:
        scope = self._scope(tenant_scope, self.WRITE_CAPABILITY)
        if self.store is None or self.artifact_store is None:
            raise EvidenceBoundaryError(
                "evidence sealing requires durable SQLite and private CAS stores"
            )
        require_identifier(target_id, "target_id")
        require_identifier(target_type, "target_type")
        if not isinstance(gate_level, GateLevel):
            raise TypeError("gate_level must be GateLevel")
        if verdict not in {"PASS", "FAIL", "INCONCLUSIVE", "CONDITIONAL"}:
            raise ValueError("evidence verdict is not recognized")
        if verdict == "PASS" and gate_level in {
            GateLevel.E3_SHADOW_CANARY,
            GateLevel.E4_PRODUCTION_CERTIFIED,
            GateLevel.E5_FORMAL_PROVEN,
        }:
            raise EvidenceBoundaryError(
                "local evidence cannot pass an external or certification gate"
            )
        obligations, normalized_metrics = (
            canonical_value(proof_obligations),
            canonical_value(metrics),
        )
        if not isinstance(obligations, list) or not all(
            isinstance(item, dict) for item in obligations
        ):
            raise TypeError("proof_obligations must be objects")
        if not isinstance(normalized_metrics, dict):
            raise TypeError("metrics must be an object")
        normalized_obligations = cast(list[Mapping[str, Any]], obligations)
        identifier, created = f"ev-{uuid.uuid4().hex}", self._now()
        leaves = self._leaves(
            target_id=target_id,
            target_type=target_type,
            gate_level=gate_level,
            verdict=verdict,
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            context_digest=scope.binding_digest,
            proof_obligations=normalized_obligations,
            metrics=normalized_metrics,
        )
        provisional = EvidenceBundle(
            identifier,
            target_id,
            target_type,
            gate_level,
            verdict,
            normalized_obligations,
            normalized_metrics,
            "sha256:" + self.kernel.calculate_merkle_root(leaves),
            (),
            created,
            scope.tenant_id,
            scope.project_id,
            scope.binding_digest,
            "",
            EvidenceState.COLLECTED_SELF_ATTESTED,
            "NOT_RUN",
            CertificationStatus.NOT_CERTIFIED,
            False,
        )
        bundle = EvidenceBundle(
            provisional.bundle_id,
            provisional.target_id,
            provisional.target_type,
            provisional.gate_level,
            provisional.verdict,
            provisional.proof_obligations,
            provisional.metrics,
            provisional.merkle_root,
            (),
            provisional.created_at,
            provisional.tenant_id,
            provisional.project_id,
            provisional.context_digest,
            canonical_digest(self._body(provisional)),
            EvidenceState.COLLECTED_SELF_ATTESTED,
            "NOT_RUN",
            CertificationStatus.NOT_CERTIFIED,
            False,
        )
        document = {**self._body(bundle), "bundle_digest": bundle.bundle_digest, "signatures": []}
        artifact_digest = self.artifact_store.put(scope, canonical_json_bytes(document))
        self.store.append_evidence(
            scope,
            target_id,
            gate_level.value,
            verdict,
            {
                "bundle": document,
                "artifact_digest": str(artifact_digest),
                "trust_boundary": "LOCAL_SELF_ATTESTED",
            },
            evidence_id=identifier,
            evidence_state=EvidenceState.COLLECTED_SELF_ATTESTED,
            certification_status=CertificationStatus.NOT_CERTIFIED,
        )
        return bundle

    @staticmethod
    def _from_document(document: Mapping[str, Any]) -> EvidenceBundle:
        if document.get("signatures") != [] or document.get("independent_verifier") is not False:
            raise EvidenceIntegrityError("local evidence unexpectedly contains trust assertions")
        try:
            return EvidenceBundle(
                str(document["bundle_id"]),
                str(document["target_id"]),
                str(document["target_type"]),
                GateLevel(str(document["gate_level"])),
                str(document["verdict"]),
                document["proof_obligations"],
                document["metrics"],
                str(document["merkle_root"]),
                (),
                str(document["created_at"]),
                str(document["tenant_id"]),
                str(document["project_id"]),
                str(document["context_digest"]),
                str(document["bundle_digest"]),
                EvidenceState(str(document["evidence_state"])),
                str(document["external_evidence_status"]),
                CertificationStatus(str(document["certification_status"])),
                False,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceIntegrityError("persisted evidence document is invalid") from exc

    def get_bundle(
        self, bundle_id: str, tenant_scope: TenantScope | None = None
    ) -> EvidenceBundle | None:
        scope = self._scope(tenant_scope, self.READ_CAPABILITY)
        if self.store is None or self.artifact_store is None:
            raise EvidenceBoundaryError("durable evidence stores are not configured")
        require_identifier(bundle_id, "bundle_id")
        try:
            record = self.store.get_evidence(scope, bundle_id)
        except RecordNotFound:
            return None
        document, artifact_digest = (
            record.payload.get("bundle"),
            record.payload.get("artifact_digest"),
        )
        if not isinstance(document, Mapping) or not isinstance(artifact_digest, str):
            raise EvidenceIntegrityError("persisted evidence payload is incomplete")
        stored = strict_json_loads(self.artifact_store.read(scope, artifact_digest))
        if stored != canonical_value(document):
            raise EvidenceIntegrityError("CAS evidence differs from durable ledger")
        bundle = self._from_document(document)
        if not self.verify_bundle_integrity(bundle):
            raise EvidenceIntegrityError("persisted evidence failed integrity")
        return bundle

    def verify_bundle_integrity(self, bundle: EvidenceBundle) -> bool:
        if (
            bundle.signatures
            or bundle.independent_verifier
            or bundle.certification_status is not CertificationStatus.NOT_CERTIFIED
            or bundle.evidence_state is not EvidenceState.COLLECTED_SELF_ATTESTED
        ):
            return False
        leaves = self._leaves(
            target_id=bundle.target_id,
            target_type=bundle.target_type,
            gate_level=bundle.gate_level,
            verdict=bundle.verdict,
            tenant_id=bundle.tenant_id,
            project_id=bundle.project_id,
            context_digest=bundle.context_digest,
            proof_obligations=bundle.proof_obligations,
            metrics=bundle.metrics,
        )
        return bundle.merkle_root == "sha256:" + self.kernel.calculate_merkle_root(
            leaves
        ) and bundle.bundle_digest == canonical_digest(self._body(bundle))


__all__ = ["EvidenceBoundaryError", "EvidenceIntegrityError", "EvidenceLedger"]
