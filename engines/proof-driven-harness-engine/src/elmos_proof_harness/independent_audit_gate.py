"""Industrial-grade Independent Audit Gate and Non-Self-Certification Verification Runner (E0-E5)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .notary import CryptographicNotary, NotarizedEvidenceEnvelope, SignatureVerificationError

logger = logging.getLogger("elmos_proof_harness.independent_audit_gate")


class GateDecision(str, Enum):
    REJECTED = "REJECTED"
    LOCAL_ENGINEERING_PASSED = "LOCAL_ENGINEERING_PASSED"
    READY_FOR_E4_GATE = "READY_FOR_E4_GATE"
    CERTIFIED_E4 = "CERTIFIED_E4"


class GateViolationReason(str, Enum):
    ZERO_TEST_RULE = "ZERO_TEST_RULE"
    DURATION_ZERO_FABRICATION = "DURATION_ZERO_FABRICATION"
    COUNT_INCONSISTENCY = "COUNT_INCONSISTENCY"
    NON_ZERO_EXIT_CODE = "NON_ZERO_EXIT_CODE"
    SIGNATURE_TAMPERED = "SIGNATURE_TAMPERED"
    MISSING_PHYSICAL_ARTIFACTS = "MISSING_PHYSICAL_ARTIFACTS"
    UNAUTHORIZED_SELF_CERTIFICATION = "UNAUTHORIZED_SELF_CERTIFICATION"


@dataclass(frozen=True)
class CandidateEvidenceBundle:
    """Submitted by developers/workers. Must contain objective, un-tampered execution proof."""

    task_id: str
    executed_command: str
    exit_code: int
    duration_ms: int
    test_count: int
    pass_count: int
    fail_count: int
    stdout_digest: str
    stderr_digest: str
    artifact_digests: Mapping[str, str] = field(default_factory=dict)
    self_attested_claim: str = "DECLARED"  # Must NOT claim 'CERTIFIED'


@dataclass(frozen=True)
class AuthoritativeAuditReceipt:
    """Authoritative non-self-certified receipt signed by the independent gate runner."""

    receipt_id: str
    task_id: str
    gate_decision: GateDecision
    audited_at: str
    passed_invariants: Sequence[str]
    violations: Sequence[str]
    notary_envelope: NotarizedEvidenceEnvelope | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "task_id": self.task_id,
            "gate_decision": self.gate_decision.value,
            "audited_at": self.audited_at,
            "passed_invariants": list(self.passed_invariants),
            "violations": list(self.violations),
            "notary_envelope": self.notary_envelope.to_dict() if self.notary_envelope else None,
        }


class IndependentAuditGateRunner:
    """Strict external gate that evaluates candidate evidence bundles against non-self-certification policies."""

    def __init__(
        self,
        notary: CryptographicNotary | None = None,
        allow_e4_promotion: bool = False,
    ) -> None:
        self.notary = notary or CryptographicNotary(notary_id="elmos-independent-gate-authority")
        self.allow_e4 = allow_e4_promotion

    def evaluate_bundle(
        self,
        bundle: CandidateEvidenceBundle,
        notarized_envelope: NotarizedEvidenceEnvelope | None = None,
    ) -> AuthoritativeAuditReceipt:
        """Audits candidate execution evidence and produces a tamper-evident decision receipt."""
        passed_invariants: list[str] = []
        violations: list[str] = []

        # 1. Non-Self-Certification Check: Workers cannot pre-claim 'CERTIFIED' or 'PRODUCTION_READY'
        if bundle.self_attested_claim in ("CERTIFIED", "PRODUCTION_READY", "PASSED_CERTIFIED"):
            violations.append(
                f"{GateViolationReason.UNAUTHORIZED_SELF_CERTIFICATION}: "
                f"Worker illegal attempt to claim '{bundle.self_attested_claim}'. Only gate runner can certify."
            )
        else:
            passed_invariants.append("NON_SELF_CERTIFICATION_HONORED")

        # 2. Zero-Test Rule Check: 0 tests is an automatic rejection
        if bundle.test_count == 0:
            violations.append(
                f"{GateViolationReason.ZERO_TEST_RULE}: Zero tests were executed, violating testing adequacy policy."
            )
        else:
            passed_invariants.append("TESTS_COUNT_GREATER_THAN_ZERO")

        # 3. Anti-Fabrication Duration Check: No real execution has 0ms duration
        if bundle.duration_ms <= 0 and bundle.test_count > 0:
            violations.append(
                f"{GateViolationReason.DURATION_ZERO_FABRICATION}: Reported execution duration {bundle.duration_ms}ms "
                "is physically impossible for real process execution. Rejected as fabricated."
            )
        else:
            passed_invariants.append("PHYSICAL_EXECUTION_DURATION_VERIFIED")

        # 4. Count Consistency Check: pass + fail == test
        if bundle.pass_count + bundle.fail_count != bundle.test_count or bundle.fail_count > 0:
            violations.append(
                f"{GateViolationReason.COUNT_INCONSISTENCY}: Test counts invalid: "
                f"total={bundle.test_count}, pass={bundle.pass_count}, fail={bundle.fail_count}"
            )
        else:
            passed_invariants.append("TEST_COUNTS_CONSISTENT_AND_ZERO_FAILURES")

        # 5. Exit Code Check: Process exit code must be strictly 0
        if bundle.exit_code != 0:
            violations.append(
                f"{GateViolationReason.NON_ZERO_EXIT_CODE}: Process exit code was {bundle.exit_code}, expected 0."
            )
        else:
            passed_invariants.append("PROCESS_EXIT_CODE_ZERO")

        # 6. Cryptographic Envelope Verification
        if notarized_envelope is not None:
            try:
                self.notary.verify_envelope(notarized_envelope)
                passed_invariants.append("CRYPTOGRAPHIC_SIGNATURE_VERIFIED")
            except SignatureVerificationError as sve:
                violations.append(f"{GateViolationReason.SIGNATURE_TAMPERED}: {sve}")

        # Final Decision Assembly
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        receipt_id = f"audit-rcpt-{hashlib.sha256((bundle.task_id + ts).encode('utf-8')).hexdigest()[:16]}"

        if violations:
            decision = GateDecision.REJECTED
        elif not self.allow_e4:
            decision = GateDecision.LOCAL_ENGINEERING_PASSED
        else:
            decision = GateDecision.CERTIFIED_E4

        receipt_payload = {
            "receipt_id": receipt_id,
            "task_id": bundle.task_id,
            "decision": decision.value,
            "invariants": passed_invariants,
            "violations": violations,
            "timestamp": ts,
        }

        # Seal final authoritative receipt with independent gate notary
        sealed_envelope = self.notary.notarize_evidence(
            evidence_id=receipt_id,
            evidence_type="AUTHORITATIVE_GATE_RECEIPT",
            payload=receipt_payload,
        )

        return AuthoritativeAuditReceipt(
            receipt_id=receipt_id,
            task_id=bundle.task_id,
            gate_decision=decision,
            audited_at=ts,
            passed_invariants=tuple(passed_invariants),
            violations=tuple(violations),
            notary_envelope=sealed_envelope,
        )
