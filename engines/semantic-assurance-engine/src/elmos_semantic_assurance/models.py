"""Domain models for Elmos Semantic Assurance Engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, List, Optional


class BatchType(str, Enum):
    BATCH_J = "J"
    BATCH_K = "K"
    BATCH_L = "L"
    BATCH_M = "M"
    BATCH_N = "N"
    BATCH_O = "O"
    BATCH_P = "P"
    BATCH_Q = "Q"
    BATCH_R = "R"


class SemanticRisk(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ObligationStatus(str, Enum):
    PROVED = "PROVED"
    DISPROVED = "DISPROVED"
    INCONCLUSIVE = "INCONCLUSIVE"
    TIMEOUT = "TIMEOUT"
    NOT_RUN = "NOT_RUN"


class VerdictStatus(str, Enum):
    EQUIVALENT = "EQUIVALENT"
    DIVERGENT = "DIVERGENT"
    UNDEFINED_BEHAVIOR = "UNDEFINED_BEHAVIOR"
    NOT_RUN = "NOT_RUN"


@dataclass
class SemanticObligation:
    obligation_id: str
    batch: BatchType
    layer: str
    source_construct: str
    target_construct: str
    property_name: str
    invariants: List[str] = field(default_factory=list)
    risk: SemanticRisk = SemanticRisk.CRITICAL
    status: ObligationStatus = ObligationStatus.NOT_RUN
    evidence_digest: str = ""
    evaluated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["batch"] = self.batch.value
        d["risk"] = self.risk.value
        d["status"] = self.status.value
        return d


@dataclass
class ProofObligation:
    proof_id: str
    formula: str
    solver_family: str  # SMT_Z3, LEAN_KERNEL, LLVM_REFINEMENT, CBMC
    assumptions: List[str] = field(default_factory=list)
    timeout_ms: int = 5000
    status: ObligationStatus = ObligationStatus.NOT_RUN
    proof_witness: Optional[str] = None
    evaluated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class BehaviorOracle:
    oracle_id: str
    scope: str
    observable_signals: List[str]
    input_domain_partitions: List[Dict[str, Any]] = field(default_factory=list)
    side_effect_channels: List[str] = field(default_factory=list)
    tolerance_epsilon: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Counterexample:
    counterexample_id: str
    obligation_id: str
    input_vector: Dict[str, Any]
    source_trace: Dict[str, Any]
    target_trace: Dict[str, Any]
    divergence_point: str
    minimized: bool = False
    reproduced: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
    wall_clock_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


@dataclass
class CertificationRun:
    certification_id: str
    route_id: str
    batch_coverage: Dict[str, int]
    total_obligations: int
    proved_obligations: int
    counterexamples_found: int
    overall_verdict: VerdictStatus
    receipt_digest: str = ""
    certified_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["overall_verdict"] = self.overall_verdict.value
        return d
