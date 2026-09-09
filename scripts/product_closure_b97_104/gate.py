#!/usr/bin/env python3
"""Conservative Quality Gate for Batch 97-104 Product Closure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from scripts.product_closure_b97_104.canonical import digest, format_instant
from scripts.product_closure_b97_104.orchestrator import ClosureBatchReceipt


@dataclass(frozen=True)
class ClosureGateVerdict:
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


class ProductClosureGate:
    """Enforces strict closure boundaries across batches 97-104."""

    def evaluate(
        self,
        receipt: ClosureBatchReceipt,
        findings: Sequence[str] = (),
    ) -> ClosureGateVerdict:
        blockers: list[str] = []
        clean_findings = list(findings)

        if receipt.certification == "CERTIFIED":
            blockers.append("Self-claimed CERTIFIED is prohibited without external independent auditor")

        for f in clean_findings:
            fl = f.lower()
            if any(k in fl for k in ["leak", "tamper", "bypass", "privilege_escalation"]):
                blockers.append(f"Zero-tolerance security finding: {f}")

        if receipt.skills_executed < 16:
            blockers.append(f"Batch {receipt.batch} requires 16 executed skills (got {receipt.skills_executed})")

        decision = "BLOCKED" if blockers else "LOCAL_PASSED"

        verdict_payload = {
            "batch": receipt.batch,
            "decision": decision,
            "certification": "NOT_CERTIFIED",
            "blockers": blockers,
            "timestamp": format_instant(),
        }

        return ClosureGateVerdict(
            batch=receipt.batch,
            decision=decision,
            certification="NOT_CERTIFIED",
            external_evidence_status="NOT_RUN",
            skills_executed=receipt.skills_executed,
            findings=clean_findings,
            blockers=blockers,
            verdict_digest=digest(verdict_payload),
        )
