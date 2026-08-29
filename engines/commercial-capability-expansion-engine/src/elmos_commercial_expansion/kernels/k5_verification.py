"""K5: Verification Kernel for Elmos Commercial Capability Expansion."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from ..models import (
    DecisionStatus,
    E0E5GateDecision,
    EvidenceRecord,
    GateLevel,
    TaskContext,
)


class VerificationKernel:
    """Orchestrates compiler gates, differential oracles, fuzzing, property tests, and E0-E5 evidence gates."""

    def __init__(self):
        self.evidence_store: Dict[str, List[EvidenceRecord]] = {}
        self.gate_decisions: List[E0E5GateDecision] = []

    def record_evidence(
        self,
        task_id: str,
        category: str,
        source_skill: str,
        metrics: Dict[str, Any],
        raw_payload: str = "",
    ) -> EvidenceRecord:
        """Records an immutable evidence item tied to a task."""
        digest = hashlib.sha256((category + source_skill + json.dumps(metrics, sort_keys=True) + raw_payload).encode("utf-8")).hexdigest()
        rec_id = f"ev-{task_id}-{category[:4]}-{digest[:8]}"

        rec = EvidenceRecord(
            evidence_id=rec_id,
            category=category,
            source_skill=source_skill,
            digest=digest,
            metrics=metrics,
            status="COLLECTED",
        )
        if task_id not in self.evidence_store:
            self.evidence_store[task_id] = []
        self.evidence_store[task_id].append(rec)
        return rec

    def run_differential_oracle(
        self,
        source_output: Any,
        target_output: Any,
        tolerance_epsilon: float = 1e-6,
    ) -> Dict[str, Any]:
        """Compares output equivalence between source and modernized implementation."""
        if source_output == target_output:
            equivalent = True
            diff_summary = "Exact match"
        elif isinstance(source_output, (int, float)) and isinstance(target_output, (int, float)):
            diff = abs(source_output - target_output)
            equivalent = diff <= tolerance_epsilon
            diff_summary = f"Numeric diff: {diff} (tolerance {tolerance_epsilon})"
        else:
            equivalent = False
            diff_summary = f"Output mismatch: source={repr(source_output)[:100]}, target={repr(target_output)[:100]}"

        return {
            "is_equivalent": equivalent,
            "diff_summary": diff_summary,
            "status": "PASS" if equivalent else "FAIL",
        }

    def evaluate_e0_e5_gate(
        self,
        task_id: str,
        target_gate: GateLevel,
        required_evidence_categories: Optional[List[str]] = None,
    ) -> E0E5GateDecision:
        """Evaluates formal promotion gate E0-E5 against collected evidence bundle."""
        default_gate_requirements = {
            GateLevel.E0_INGESTION: ["INGESTION", "FINGERPRINT"],
            GateLevel.E1_SYNTAX_COMPILE: ["INGESTION", "SYNTAX_PARSE", "BUILD_COMPILE"],
            GateLevel.E2_UNIT_INTEGRATION: ["BUILD_COMPILE", "UNIT_TEST", "INTEGRATION_TEST"],
            GateLevel.E3_SECURITY_ISOLATION: ["UNIT_TEST", "SECURITY_SCAN", "POLICY_EVALUATION", "SANDBOX_ISOLATION"],
            GateLevel.E4_DIFFERENTIAL_RUNTIME: ["SECURITY_SCAN", "DIFFERENTIAL_RUNTIME", "FUZZ_TESTING", "PERFORMANCE_BENCH"],
            GateLevel.E5_FORMAL_PROVENANCE: ["DIFFERENTIAL_RUNTIME", "FORMAL_PROOF", "SLSA_PROVENANCE", "ARTIFACT_SIGNATURE"],
        }

        reqs = required_evidence_categories or default_gate_requirements.get(target_gate, ["BUILD_COMPILE"])
        collected = self.evidence_store.get(task_id, [])
        collected_categories = {ev.category for ev in collected}

        missing = [r for r in reqs if r not in collected_categories]
        passed = len(missing) == 0
        status = DecisionStatus.APPROVED if passed else DecisionStatus.DENIED

        evaluated_criteria = [f"{req}: {'PRESENT' if req in collected_categories else 'MISSING'}" for req in reqs]
        bundle_digest = hashlib.sha256("".join(ev.digest for ev in collected).encode("utf-8")).hexdigest()
        residual_risk = "NONE" if passed else f"Missing evidence for: {', '.join(missing)}"

        decision = E0E5GateDecision(
            target_gate=target_gate,
            status=status,
            passed=passed,
            evaluated_criteria=evaluated_criteria,
            evidence_bundle_ref=f"bundle-{task_id}-{bundle_digest[:8]}",
            residual_risk=residual_risk,
        )
        self.gate_decisions.append(decision)
        return decision
