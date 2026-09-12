#!/usr/bin/env python3
"""Conservative Quality Gate for Batch 81-95 Language Packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from scripts.language_packs_b81_95.canonical import digest, format_instant
from scripts.language_packs_b81_95.errors import GateBlockedError
from scripts.language_packs_b81_95.orchestrator import BatchRunReceipt


@dataclass(frozen=True)
class GateVerdict:
    batch: int
    decision: str
    certification: str
    external_evidence_status: str
    skills_executed: int
    findings: list[str]
    blockers: list[str]
    verdict_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch": self.batch,
            "decision": self.decision,
            "certification": self.certification,
            "external_evidence_status": self.external_evidence_status,
            "skills_executed": self.skills_executed,
            "findings": self.findings,
            "blockers": self.blockers,
            "verdict_digest": self.verdict_digest,
        }


class LanguagePackGate:
    """Evaluates execution receipts and enforces fail-closed boundary."""

    def evaluate(
        self,
        receipt: BatchRunReceipt,
        findings: Sequence[str] = (),
        allow_unverified_claims: bool = False,
    ) -> GateVerdict:
        blockers: list[str] = []
        clean_findings = list(findings)

        if not allow_unverified_claims:
            # Self-certification without independent audit is strictly prohibited by AGENTS.md
            if receipt.certification == "CERTIFIED":
                blockers.append("Self-claimed CERTIFIED is prohibited without independent external verification")

        # Check for zero-tolerance security/tamper findings
        for f in clean_findings:
            fl = f.lower()
            if any(k in fl for k in ["leak", "tamper", "forgery", "injection", "bypass"]):
                blockers.append(f"Zero-tolerance security finding: {f}")

        if receipt.skills_executed < 12:
            blockers.append(f"Batch {receipt.batch} must execute all 12 skills (got {receipt.skills_executed})")

        decision = "BLOCKED" if blockers else "LOCAL_PASSED"
        certification = "NOT_CERTIFIED"
        ext_status = "NOT_RUN"

        verdict_payload = {
            "batch": receipt.batch,
            "decision": decision,
            "certification": certification,
            "blockers": blockers,
            "timestamp": format_instant(),
        }

        return GateVerdict(
            batch=receipt.batch,
            decision=decision,
            certification=certification,
            external_evidence_status=ext_status,
            skills_executed=receipt.skills_executed,
            findings=clean_findings,
            blockers=blockers,
            verdict_digest=digest(verdict_payload),
        )
