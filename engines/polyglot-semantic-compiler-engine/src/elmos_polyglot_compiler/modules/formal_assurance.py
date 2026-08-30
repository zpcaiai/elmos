"""Batch Q formal-assurance obligations and external receipt validation.

This module does not embed a solver. It may create obligations and consume a
receipt that a trusted host has already verified; caller-selected booleans are
never proof evidence.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Any, Dict, List, Mapping, Optional

from ..contracts import ContractError, ExecutionAuthority, RuntimeRequest, digest_json
from ..evidence import validate_evidence_receipt
from ..models import (
    BatchType,
    Counterexample,
    EvidenceState,
    ObligationStatus,
    ProofObligation,
    SemanticObligation,
    SemanticRisk,
)


_MAX_FORMULA_BYTES = 1_048_576
_MAX_ASSUMPTIONS = 1_000


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{label} exceeds the bounded size")
    return value


class FormalAssuranceModule:
    """Creates proof obligations and validates host-verified solver receipts."""

    def __init__(self) -> None:
        self.proofs: Dict[str, ProofObligation] = {}
        # Kept for API compatibility. Counterexamples are never synthesized.
        self.counterexamples: List[Counterexample] = []

    @staticmethod
    def expected_evidence_type(proof_id: str) -> str:
        """Return the exact subject binding required on an external receipt."""

        _require_text(proof_id, "proof_id", maximum=160)
        return f"formal-proof/{proof_id}"

    @staticmethod
    def expected_subject_digest(proof: ProofObligation) -> str:
        """Bind evidence to the complete immutable proof obligation."""

        if not isinstance(proof, ProofObligation):
            raise ValueError("proof must be a ProofObligation")
        return digest_json(
            {
                "kind": "formal-proof-obligation",
                "proof_id": proof.proof_id,
                "formula_digest": proof.formula_digest,
                "solver_family": proof.solver_family,
                "assumptions": list(proof.assumptions),
                "timeout_ms": proof.timeout_ms,
            }
        )

    def create_proof_obligation(
        self,
        formula: str,
        solver_family: str = "SMT_Z3",
        assumptions: Optional[List[str]] = None,
        *,
        timeout_ms: int = 5_000,
    ) -> ProofObligation:
        """Create an immutable obligation without claiming solver execution."""

        formula = _require_text(formula, "formula", maximum=_MAX_FORMULA_BYTES)
        solver_family = _require_text(solver_family, "solver_family", maximum=64)
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool):
            raise ValueError("timeout_ms must be an integer")
        if timeout_ms < 1 or timeout_ms > 3_600_000:
            raise ValueError("timeout_ms must be between 1 and 3600000")
        raw_assumptions = assumptions or []
        if not isinstance(raw_assumptions, list) or len(raw_assumptions) > _MAX_ASSUMPTIONS:
            raise ValueError("assumptions must be a bounded list")
        normalized_assumptions = tuple(
            _require_text(item, "assumption", maximum=16_384)
            for item in raw_assumptions
        )
        formula_digest = _digest_text(formula)
        identity = "\0".join((solver_family, formula_digest, *normalized_assumptions))
        proof_id = f"proof-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
        proof = ProofObligation(
            proof_id=proof_id,
            formula_digest=formula_digest,
            solver_family=solver_family,
            assumptions=normalized_assumptions,
            timeout_ms=timeout_ms,
            status=ObligationStatus.NOT_RUN,
        )
        self.proofs[proof_id] = proof
        return proof

    def solve_proof(
        self,
        proof_id: str,
        simulated_pass: Optional[bool] = None,
        *,
        evidence_receipt: Optional[Mapping[str, Any]] = None,
        request: Optional[RuntimeRequest] = None,
        authority: Optional[ExecutionAuthority] = None,
    ) -> ProofObligation:
        """Validate an externally executed proof receipt.

        ``simulated_pass`` is retained solely so legacy callers fail closed
        instead of crashing. It is ignored and can never change an obligation
        from ``NOT_RUN``. A passing result requires an exact proof-subject
        receipt whose digest was verified and minted into host authority.
        """

        _ = simulated_pass
        proof = self.proofs.get(proof_id)
        if proof is None:
            raise KeyError(f"unknown proof obligation: {proof_id}")
        if evidence_receipt is None and request is None and authority is None:
            return proof
        if evidence_receipt is None or request is None or authority is None:
            proof = replace(proof, status=ObligationStatus.INVALID)
            self.proofs[proof_id] = proof
            return proof
        if not isinstance(evidence_receipt, Mapping):
            proof = replace(proof, status=ObligationStatus.INVALID)
            self.proofs[proof_id] = proof
            return proof
        if evidence_receipt.get("evidence_type") != self.expected_evidence_type(proof_id):
            proof = replace(proof, status=ObligationStatus.INVALID)
            self.proofs[proof_id] = proof
            return proof

        try:
            evidence_state, _, receipt_digest = validate_evidence_receipt(
                evidence_receipt,
                request=request,
                authority=authority,
                expected_subject_digest=self.expected_subject_digest(proof),
            )
        except (ContractError, TypeError, ValueError):
            proof = replace(proof, status=ObligationStatus.INVALID)
            self.proofs[proof_id] = proof
            return proof

        receipt_status = evidence_receipt.get("status")
        host_verified = (
            receipt_digest is not None
            and receipt_digest in authority.verified_evidence_digests
        )
        if (
            receipt_status == "PASSED"
            and evidence_state is EvidenceState.INDEPENDENTLY_VERIFIED
            and host_verified
        ):
            proof = replace(
                proof,
                status=ObligationStatus.PROVED_UNDER_ASSUMPTIONS,
                proof_receipt_digest=receipt_digest,
                counterexample_digest=None,
            )
        elif receipt_status == "FAILED" and host_verified:
            proof = replace(
                proof,
                status=ObligationStatus.DISPROVED,
                proof_receipt_digest=receipt_digest,
                counterexample_digest=str(evidence_receipt["artifact_digest"]),
            )
        elif evidence_state is EvidenceState.INVALID:
            proof = replace(
                proof,
                status=ObligationStatus.INVALID,
                proof_receipt_digest=receipt_digest,
            )
        elif receipt_status == "NOT_RUN":
            proof = replace(
                proof,
                status=ObligationStatus.NOT_RUN,
                proof_receipt_digest=receipt_digest,
            )
        else:
            proof = replace(
                proof,
                status=ObligationStatus.INCONCLUSIVE,
                proof_receipt_digest=receipt_digest,
            )
        self.proofs[proof_id] = proof
        return proof

    def create_formal_obligation(
        self,
        source_spec: str,
        target_spec: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emit a Batch Q obligation without asserting that it was evaluated."""

        source_spec = _require_text(source_spec, "source_spec", maximum=_MAX_FORMULA_BYTES)
        target_spec = _require_text(target_spec, "target_spec", maximum=_MAX_FORMULA_BYTES)
        property_name = _require_text(property_name, "property_name", maximum=512)
        material = "\0".join((source_spec, target_spec, property_name))
        digest = _digest_text(material)
        return SemanticObligation(
            obligation_id=f"obl-Q-{digest.removeprefix('sha256:')[:24]}",
            batch=BatchType.BATCH_Q,
            layer="formal-assurance",
            property_name=property_name,
            invariants=(
                "SMT_EQUIVALENCE_PROVED",
                "SOUND_REFINEMENT",
                "COUNTEREXAMPLE_REPRODUCIBILITY",
            ),
            input_digest=digest,
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
