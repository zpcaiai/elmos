"""Industrial Delivery Maturity Evaluator (L1 to L5 Standard).

Implements the formal L1 to L5 maturity assessment conforming to
Elmos Commercial Maturity Specification (elmos-maturity-l1-l5 / ELMOS-GR-004).
Generates maturity-assessment.json and promotion-gaps.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .merkle_provenance import EvidenceBundle
from .native_toolchain_runner import ToolchainExecutionReport
from .verification_gate import VerificationReport


class MaturityLevel(Enum):
    L1_STATIC_SKELETON = "L1_STATIC_SKELETON"
    L2_IN_MEMORY_UNIT = "L2_IN_MEMORY_UNIT"
    L3_FRAMEWORK_SLICED = "L3_FRAMEWORK_SLICED"
    L4_NATIVE_EXECUTION_VERIFIED = "L4_NATIVE_EXECUTION_VERIFIED"
    L5_AUTONOMOUS_MERKLE_CERTIFIED = "L5_AUTONOMOUS_MERKLE_CERTIFIED"


@dataclass
class MaturityAssessment:
    current_level: MaturityLevel
    achieved_criteria: List[str]
    missing_criteria: List[str]
    evidence_digest: str
    timestamp_utc: str
    assessment_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec_id": "ELMOS-GR-004",
            "spec_name": "elmos-maturity-l1-l5",
            "current_maturity_level": self.current_level.value,
            "timestamp_utc": self.timestamp_utc,
            "evidence_digest": self.evidence_digest,
            "achieved_criteria": self.achieved_criteria,
            "missing_criteria": self.missing_criteria,
            "assessment_details": self.assessment_details
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


@dataclass
class PromotionGapsReport:
    current_level: MaturityLevel
    next_level: Optional[MaturityLevel]
    gaps: List[str]
    actionable_remediations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_level": self.current_level.value,
            "next_level": self.next_level.value if self.next_level else "MAX_MATURITY_REACHED",
            "gaps": self.gaps,
            "actionable_remediations": self.actionable_remediations
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


class IndustrialMaturityEvaluator:
    """Audits generated projects against L1–L5 industrial maturity standards."""

    @classmethod
    def evaluate(
        cls,
        project_files: Dict[str, str],
        verification_report: VerificationReport,
        toolchain_report: Optional[ToolchainExecutionReport] = None,
        evidence_bundle: Optional[EvidenceBundle] = None,
        context_compression_ratio: float = 0.0,
        self_healing_verified: bool = False
    ) -> tuple[MaturityAssessment, PromotionGapsReport]:
        achieved: List[str] = []
        missing: List[str] = []
        current_level = MaturityLevel.L1_STATIC_SKELETON

        # Level 1 Checks: Static skeleton
        if project_files and len(project_files) >= 5:
            achieved.append("L1: Multi-file project structure generated (>= 5 files)")
        else:
            missing.append("L1: Insufficient project file generation")

        # Level 2 Checks: Syntax & in-memory AST
        if verification_report.syntax_ok and verification_report.slots_fulfilled:
            achieved.append("L2: AST and brace-syntax validated; domain slots syntactically fulfilled")
            current_level = MaturityLevel.L2_IN_MEMORY_UNIT
        else:
            missing.append("L2: Syntax error or unfulfilled domain slots remain in source files")

        # Level 3 Checks: Framework slicing & 0-token scaffold
        if current_level == MaturityLevel.L2_IN_MEMORY_UNIT:
            if context_compression_ratio >= 0.70 and verification_report.tests_passed:
                achieved.append(f"L3: Context slicing achieved {context_compression_ratio*100:.1f}% token reduction; unit test structures verified")
                current_level = MaturityLevel.L3_FRAMEWORK_SLICED
            else:
                missing.append("L3: Context compression ratio below 70% or unit test fixtures incomplete")

        # Level 4 Checks: Real native toolchain execution on disk
        if current_level == MaturityLevel.L3_FRAMEWORK_SLICED:
            if toolchain_report and toolchain_report.passed:
                achieved.append(
                    f"L4: Real host toolchain ({toolchain_report.toolchain_binary} {toolchain_report.toolchain_version}) "
                    f"executed in hermetic workspace with exit_code=0 and test_count={toolchain_report.test_count}"
                )
                current_level = MaturityLevel.L4_NATIVE_EXECUTION_VERIFIED
            else:
                reason = toolchain_report.stderr if toolchain_report else "No native toolchain executed on disk"
                missing.append(f"L4: Native compiler/runner execution incomplete or failed ({reason})")

        # Level 5 Checks: Autonomous Self-Healing & Merkle DAG Evidence
        if current_level == MaturityLevel.L4_NATIVE_EXECUTION_VERIFIED:
            merkle_ok = evidence_bundle is not None and evidence_bundle.verify_integrity()
            if merkle_ok and self_healing_verified:
                achieved.append(
                    f"L5: Cryptographic Merkle root verified ({evidence_bundle.merkle_root[:16]}...); "
                    f"Closed-loop autonomous self-healing certified"
                )
                current_level = MaturityLevel.L5_AUTONOMOUS_MERKLE_CERTIFIED
            else:
                if not merkle_ok:
                    missing.append("L5: Cryptographic Merkle provenance ledger missing or integrity check failed")
                if not self_healing_verified:
                    missing.append("L5: Autonomous self-healing loop not executed or unverified")

        # Determine gaps to next level
        gaps: List[str] = []
        remediations: List[str] = []
        next_level: Optional[MaturityLevel] = None

        if current_level == MaturityLevel.L1_STATIC_SKELETON:
            next_level = MaturityLevel.L2_IN_MEMORY_UNIT
            gaps = ["Files contain syntax errors or unfulfilled placeholder slots."]
            remediations = ["Run AST parser and fulfill all domain slots with syntactically valid code."]
        elif current_level == MaturityLevel.L2_IN_MEMORY_UNIT:
            next_level = MaturityLevel.L3_FRAMEWORK_SLICED
            gaps = ["Context slicing compression ratio < 70% or missing unit test fixtures."]
            remediations = ["Compile minimal context slices and ensure test assertions exist for all domain logic."]
        elif current_level == MaturityLevel.L3_FRAMEWORK_SLICED:
            next_level = MaturityLevel.L4_NATIVE_EXECUTION_VERIFIED
            gaps = ["Project has only been verified in-memory; no real OS subprocess compiler was executed on disk."]
            remediations = ["Materialize project in HermeticWorkspace and run NativeToolchainRunner (pytest, javac, go test, etc.)."]
        elif current_level == MaturityLevel.L4_NATIVE_EXECUTION_VERIFIED:
            next_level = MaturityLevel.L5_AUTONOMOUS_MERKLE_CERTIFIED
            gaps = ["Evidence bundle lacks cryptographic Merkle DAG seal or autonomous self-healing is unverified."]
            remediations = ["Generate MerkleProvenanceLedger evidence bundle and execute closed-loop self-healing validation."]
        else:
            next_level = None
            gaps = []
            remediations = ["System has achieved maximum industrial maturity level L5 (Production Certified)."]

        ts = datetime.now(timezone.utc).isoformat()
        digest = evidence_bundle.bundle_digest if evidence_bundle else verification_report.evidence_hash

        assessment = MaturityAssessment(
            current_level=current_level,
            achieved_criteria=achieved,
            missing_criteria=missing,
            evidence_digest=digest,
            timestamp_utc=ts,
            assessment_details={
                "gate_decision": verification_report.gate_decision.value,
                "file_count": len(project_files),
                "native_toolchain_executed": toolchain_report is not None and toolchain_report.exit_code == 0
            }
        )

        promotion_gaps = PromotionGapsReport(
            current_level=current_level,
            next_level=next_level,
            gaps=gaps,
            actionable_remediations=remediations
        )

        return assessment, promotion_gaps
