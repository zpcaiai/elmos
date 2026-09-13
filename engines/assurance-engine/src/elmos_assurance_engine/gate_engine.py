"""Implementation of B02: Deterministic tri-state gate engine under elmos.assurance/v4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import GATE_LEVELS, GateDecision, sha256_digest
from .evidence_graph import EvidenceEnvelope, TrustedKey


@dataclass(frozen=True)
class GateEvaluationResult:
    target_level: str
    verdict: GateDecision
    status: str
    reasons: tuple[str, ...]
    verified_evidence_ids: tuple[str, ...]
    production_signing_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_level": self.target_level,
            "verdict": self.verdict.value,
            "status": self.status,
            "reasons": list(self.reasons),
            "verified_evidence_ids": list(self.verified_evidence_ids),
            "production_signing_allowed": self.production_signing_allowed,
        }


class GateEngine:
    """Evaluates multi-level E0..E5 gates strictly fail-closed."""

    @classmethod
    def evaluate_gate(
        cls,
        request: Mapping[str, Any],
        envelopes: Sequence[EvidenceEnvelope],
        blobs: Mapping[str, bytes],
        trusted_keys: Mapping[str, TrustedKey],
        now: int,
        approved_request_digest: str,
        ethen_configured: bool = False,
    ) -> GateEvaluationResult:
        reasons: list[str] = []
        target_level = request.get("target_level", "E2")

        if target_level not in GATE_LEVELS:
            return GateEvaluationResult(
                target_level=target_level,
                verdict=GateDecision.FAIL,
                status="INVALID_TARGET_LEVEL",
                reasons=(f"UNKNOWN_GATE_LEVEL: {target_level}",),
                verified_evidence_ids=(),
            )

        # 1. Verify request matches approved digest
        actual_req_digest = sha256_digest(request)
        if actual_req_digest != approved_request_digest:
            return GateEvaluationResult(
                target_level=target_level,
                verdict=GateDecision.FAIL,
                status="REQUEST_NOT_APPROVED",
                reasons=(f"REQUEST_APPROVAL_MISMATCH: expected {approved_request_digest}, got {actual_req_digest}",),
                verified_evidence_ids=(),
            )

        rev_set_digest = sha256_digest(request.get("revision_set", {}))
        required_kinds = GATE_LEVELS[target_level]

        # 2. Map envelopes by kind
        verified_ids: list[str] = []
        envelopes_by_kind: dict[str, EvidenceEnvelope] = {}
        for env in envelopes:
            kind = env.payload.get("kind")
            eid = env.payload.get("evidence_id", env.envelope_id)

            ok, errs = env.verify(
                trusted_keys=trusted_keys,
                blobs=blobs,
                expected_revision_digest=rev_set_digest,
                now=now,
            )
            if not ok:
                reasons.extend(f"{eid}:{err}" for err in errs)
            else:
                verified_ids.append(eid)
                if kind:
                    envelopes_by_kind[kind] = env

        # 3. Check all required kinds present
        missing_kinds = required_kinds - set(envelopes_by_kind.keys())
        if missing_kinds:
            reasons.append(f"MISSING_REQUIRED_EVIDENCE_KINDS: {', '.join(sorted(missing_kinds))}")

        # 4. Check for test case failures inside regression envelope
        if "regression" in envelopes_by_kind:
            reg_payload = envelopes_by_kind["regression"].payload
            failed_count = reg_payload.get("failed_count", 0)
            if failed_count > 0:
                reasons.append(f"REGRESSION_CONTAINED_{failed_count}_FAILURES")

        # 5. Check E5 prerequisites
        if target_level == "E5":
            if not ethen_configured:
                reasons.append("AUDITOR_NOT_CONFIGURED: real Ethen external auditor identity is required for E5")
                return GateEvaluationResult(
                    target_level=target_level,
                    verdict=GateDecision.INCONCLUSIVE,
                    status="AUDITOR_NOT_CONFIGURED",
                    reasons=tuple(reasons),
                    verified_evidence_ids=tuple(verified_ids),
                    production_signing_allowed=False,
                )

            # Check formal proof status
            if "proof" in envelopes_by_kind:
                proof_status = envelopes_by_kind["proof"].payload.get("proof_status")
                if proof_status not in ("PROVED", "PROVED_SOLVER_TRUSTED"):
                    reasons.append(f"FORMAL_PROOF_NOT_SATISFIED: {proof_status}")

        if reasons:
            verdict = GateDecision.FAIL if any("FAIL" in r or "MISMATCH" in r for r in reasons) else GateDecision.INCONCLUSIVE
            return GateEvaluationResult(
                target_level=target_level,
                verdict=verdict,
                status="GATE_BLOCKED",
                reasons=tuple(reasons),
                verified_evidence_ids=tuple(verified_ids),
                production_signing_allowed=False,
            )

        return GateEvaluationResult(
            target_level=target_level,
            verdict=GateDecision.PASS,
            status="READY_FOR_EXTERNAL_GATE",
            reasons=("ALL_MANDATORY_EVIDENCE_VERIFIED",),
            verified_evidence_ids=tuple(verified_ids),
            production_signing_allowed=False,  # Local engine never self-signs production certificates
        )
