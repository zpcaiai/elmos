from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Sequence

STATUSES = {
    "PROVED", "TESTED", "BOUNDED", "RUNTIME_MONITORED",
    "WAIVED", "UNKNOWN", "UNSUPPORTED", "REFUTED",
}

@dataclass(frozen=True)
class ProofResult:
    obligation_id: str
    criticality: str
    status: str
    evidence_hash: str
    verifier_digest: str
    revision_set_id: str

@dataclass(frozen=True)
class CertificationInput:
    revision_set_id: str
    proof_results: Sequence[ProofResult]
    gates: Mapping[str, str]
    p05: str
    certifier_independent: bool
    evidence_bundle_sealed: bool
    evidence_revision_set_id: str
    side_effects_settled: bool
    production: bool = True

@dataclass(frozen=True)
class CertificationDecision:
    decision: str
    reasons: tuple[str, ...]
    certified_revision_set_id: str | None = None

def certify(value: CertificationInput) -> CertificationDecision:
    reasons: list[str] = []
    if not value.certifier_independent:
        reasons.append("certifier is not independent")
    if not value.evidence_bundle_sealed:
        reasons.append("evidence bundle is not sealed")
    if value.evidence_revision_set_id != value.revision_set_id:
        reasons.append("evidence revision mismatch")
    if not value.side_effects_settled:
        reasons.append("side effects are not settled")

    expected_gates = [f"E{i}" for i in range(6)]
    for gate in expected_gates:
        if value.gates.get(gate) != "PASS":
            reasons.append(f"{gate} is not PASS")
    if value.production and value.p05 != "PASS":
        reasons.append("P05 is not PASS for production")

    seen: set[str] = set()
    for result in value.proof_results:
        if result.obligation_id in seen:
            reasons.append(f"duplicate proof result {result.obligation_id}")
        seen.add(result.obligation_id)
        if result.status not in STATUSES:
            reasons.append(f"invalid proof status {result.status}")
        if result.revision_set_id != value.revision_set_id:
            reasons.append(f"proof revision mismatch {result.obligation_id}")
        if not result.evidence_hash or not result.verifier_digest.startswith("sha256:"):
            reasons.append(f"unbound proof evidence {result.obligation_id}")
        if result.criticality == "critical" and result.status not in {"PROVED", "TESTED"}:
            reasons.append(
                f"critical obligation {result.obligation_id} has non-certifiable status {result.status}"
            )
        if result.status == "REFUTED":
            reasons.append(f"refuted obligation {result.obligation_id}")

    if not value.proof_results:
        reasons.append("no proof results")
    if reasons:
        return CertificationDecision("BLOCKED", tuple(sorted(set(reasons))))
    return CertificationDecision("CERTIFIED", (), value.revision_set_id)
