"""Data models and enums for ELMOS Polyglot Repository Semantic Compiler Engine v3.0.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class BatchType(str, Enum):
    BATCH_A = "A"  # Discovery & Ingestion
    BATCH_B = "B"  # IR & Normalization
    BATCH_C = "C"  # Adapters & Frontends
    BATCH_D = "D"  # Core Transformation
    BATCH_E = "E"  # Systems & UI Transformation
    BATCH_F = "F"  # Database & Numerical Transformation
    BATCH_G = "G"  # Integration & Specialized Transformation
    BATCH_H = "H"  # Verification & Oracles
    BATCH_I = "I"  # Delivery & Orchestration
    BATCH_J = "J"  # Frontend Syntax Semantics
    BATCH_K = "K"  # Type & Contract Semantics
    BATCH_L = "L"  # Control & Data Flow Semantics
    BATCH_M = "M"  # Runtime & Memory Semantics
    BATCH_N = "N"  # Observable Behavior Oracles
    BATCH_O = "O"  # Certification Corpora
    BATCH_P = "P"  # Native Runtime Labs
    BATCH_Q = "Q"  # Formal Assurance & SMT
    BATCH_R = "R"  # Semantic Stress & Differential Fuzzing


class SemanticRisk(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ObligationStatus(str, Enum):
    NOT_RUN = "not-run"
    PROVED = "proved"
    DISPROVED = "disproved"
    INCONCLUSIVE = "inconclusive"
    WAIVED = "waived"


class VerdictStatus(str, Enum):
    EQUIVALENT = "EQUIVALENT"
    DIVERGENT = "DIVERGENT"
    UNDETERMINED = "UNDETERMINED"


@dataclass
class TechnologySurface:
    surface_id: str
    name: str
    ecosystem: str
    primary_file_extensions: List[str]
    standard_versions: List[str]
    runtime_engine: str


@dataclass
class RouteCell:
    route_id: str
    source_language: str
    target_language: str
    tier: str  # Tier 1 (Golden), Tier 2 (Standard), Tier 3 (Extended)
    is_supported: bool = True
    readiness: str = "not-run"


@dataclass
class RouteCertificationPlan:
    plan_id: str
    route_id: str
    source_language: str
    target_language: str
    obligations_count: int
    required_layers: List[str]
    golden_fixtures: List[str]
    status: str = "not-run"


@dataclass
class SemanticObligation:
    obligation_id: str
    batch: BatchType
    layer: str
    source_construct: str
    target_construct: str
    property_name: str
    invariants: List[str]
    risk: SemanticRisk = SemanticRisk.HIGH
    status: ObligationStatus = ObligationStatus.NOT_RUN
    evidence_receipt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "batch": self.batch.value,
            "layer": self.layer,
            "source_construct": self.source_construct,
            "target_construct": self.target_construct,
            "property_name": self.property_name,
            "invariants": self.invariants,
            "risk": self.risk.value,
            "status": self.status.value,
            "evidence_receipt": self.evidence_receipt,
        }


@dataclass
class ProofObligation:
    proof_id: str
    formula: str
    solver_family: str
    assumptions: List[str] = field(default_factory=list)
    timeout_ms: int = 5000
    status: ObligationStatus = ObligationStatus.NOT_RUN
    proof_witness: Optional[str] = None
    evaluated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "formula": self.formula,
            "solver_family": self.solver_family,
            "assumptions": self.assumptions,
            "timeout_ms": self.timeout_ms,
            "status": self.status.value,
            "proof_witness": self.proof_witness,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class BehaviorOracle:
    oracle_id: str
    scope: str
    observable_signals: List[str]
    input_domain_partitions: List[Dict[str, Any]]
    side_effect_channels: List[str]
    tolerance_epsilon: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "oracle_id": self.oracle_id,
            "scope": self.scope,
            "observable_signals": self.observable_signals,
            "input_domain_partitions": self.input_domain_partitions,
            "side_effect_channels": self.side_effect_channels,
            "tolerance_epsilon": self.tolerance_epsilon,
        }


@dataclass
class Counterexample:
    counterexample_id: str
    obligation_id: str
    input_vector: Dict[str, Any]
    source_trace: Dict[str, Any]
    target_trace: Dict[str, Any]
    divergence_point: str
    minimized: bool = True
    reproduced: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "counterexample_id": self.counterexample_id,
            "obligation_id": self.obligation_id,
            "input_vector": self.input_vector,
            "source_trace": self.source_trace,
            "target_trace": self.target_trace,
            "divergence_point": self.divergence_point,
            "minimized": self.minimized,
            "reproduced": self.reproduced,
        }


@dataclass
class DifferentialResult:
    run_id: str
    source_language: str
    target_language: str
    test_case_id: str
    verdict: VerdictStatus
    source_output: Any
    target_output: Any
    divergence_summary: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "test_case_id": self.test_case_id,
            "verdict": self.verdict.value,
            "source_output": str(self.source_output),
            "target_output": str(self.target_output),
            "divergence_summary": self.divergence_summary,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class CertificationRun:
    certification_id: str
    route_id: str
    batch_coverage: Dict[str, int]
    total_obligations: int
    proved_obligations: int
    counterexamples_found: int
    overall_verdict: VerdictStatus
    receipt_digest: str
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "certification_id": self.certification_id,
            "route_id": self.route_id,
            "batch_coverage": self.batch_coverage,
            "total_obligations": self.total_obligations,
            "proved_obligations": self.proved_obligations,
            "counterexamples_found": self.counterexamples_found,
            "overall_verdict": self.overall_verdict.value,
            "receipt_digest": self.receipt_digest,
            "timestamp": self.timestamp,
        }
