"""Typed contracts for the repository-owned polyglot semantic runtime.

The source ZIP is a declarative requirements package. These models are owned
by the repository and deliberately separate local execution, external
execution, independent verification, readiness, and certification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class BatchType(str, Enum):
    BATCH_A = "A"
    BATCH_B = "B"
    BATCH_C = "C"
    BATCH_D = "D"
    BATCH_E = "E"
    BATCH_F = "F"
    BATCH_G = "G"
    BATCH_H = "H"
    BATCH_I = "I"
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


class CapabilityMode(str, Enum):
    """Maximum effect a repository-owned handler can perform locally."""

    LOCAL_ANALYSIS = "LOCAL_ANALYSIS"
    LOCAL_CONTROL_PLANE = "LOCAL_CONTROL_PLANE"
    EXTERNAL_ADAPTER_REQUIRED = "EXTERNAL_ADAPTER_REQUIRED"
    INDEPENDENT_GATE_REQUIRED = "INDEPENDENT_GATE_REQUIRED"


class ExecutionState(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    READY_FOR_EXTERNAL_GATE = "READY_FOR_EXTERNAL_GATE"
    READY_FOR_HUMAN_DECISION = "READY_FOR_HUMAN_DECISION"


class EvidenceState(str, Enum):
    NOT_RUN = "NOT_RUN"
    LOCAL_EXECUTED_SELF_ATTESTED = "LOCAL_EXECUTED_SELF_ATTESTED"
    EXTERNAL_EXECUTED_UNVERIFIED = "EXTERNAL_EXECUTED_UNVERIFIED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    INVALID = "INVALID"


class CertificationState(str, Enum):
    NOT_CERTIFIED = "NOT_CERTIFIED"
    READY_FOR_EXTERNAL_GATE = "READY_FOR_EXTERNAL_GATE"
    CERTIFIED = "CERTIFIED"


class ObligationStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    PROVED_UNDER_ASSUMPTIONS = "PROVED_UNDER_ASSUMPTIONS"
    DISPROVED = "DISPROVED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID = "INVALID"


class VerdictStatus(str, Enum):
    EQUIVALENT = "EQUIVALENT"
    DIVERGENT = "DIVERGENT"
    UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True)
class SkillDefinition:
    ordinal: int
    source_id: str
    name: str
    batch: BatchType
    layer: str
    risk: SemanticRisk
    description: str
    dependencies: tuple[str, ...]
    outputs: tuple[str, ...]
    source_path: str
    source_sha256: str
    operation_family: str
    capability_mode: CapabilityMode

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SkillDefinition":
        return cls(
            ordinal=int(value["ordinal"]),
            source_id=str(value["source_id"]),
            name=str(value["name"]),
            batch=BatchType(str(value["batch"])),
            layer=str(value["layer"]),
            risk=SemanticRisk(str(value["risk"])),
            description=str(value["description"]),
            dependencies=tuple(str(item) for item in value.get("dependencies", ())),
            outputs=tuple(str(item) for item in value.get("outputs", ())),
            source_path=str(value["source_path"]),
            source_sha256=str(value["source_sha256"]),
            operation_family=str(value["operation_family"]),
            capability_mode=CapabilityMode(str(value["capability_mode"])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "source_id": self.source_id,
            "name": self.name,
            "batch": self.batch.value,
            "layer": self.layer,
            "risk": self.risk.value,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "outputs": list(self.outputs),
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "operation_family": self.operation_family,
            "capability_mode": self.capability_mode.value,
        }


@dataclass(frozen=True)
class TechnologySurface:
    surface_id: str
    name: str
    ecosystem: str
    primary_file_extensions: tuple[str, ...] = ()
    standard_versions: tuple[str, ...] = ()
    runtime_engine: str = ""


@dataclass(frozen=True)
class RouteCell:
    route_id: str
    source_language: str
    target_language: str
    route_class: str
    default_mode: str
    minimum_gate: str
    readiness: str = "not-run"
    reference_profile: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "route_class": self.route_class,
            "default_mode": self.default_mode,
            "minimum_gate": self.minimum_gate,
            "readiness": self.readiness,
            "reference_profile": self.reference_profile,
        }


@dataclass(frozen=True)
class RouteCertificationPlan:
    plan_id: str
    route_id: str
    source_language: str
    target_language: str
    required_skills: tuple[str, ...]
    required_labs: tuple[str, ...]
    target_levels: tuple[str, ...]
    status: str = "not-run"


@dataclass(frozen=True)
class SemanticObligation:
    obligation_id: str
    batch: BatchType
    layer: str
    property_name: str
    invariants: tuple[str, ...]
    # ``source_construct`` / ``target_construct`` are retained for the bounded
    # legacy analysis facades.  Security-sensitive runtime handlers use the
    # digest-bound ``input_digest`` instead.
    source_construct: str = ""
    target_construct: str = ""
    input_digest: str = ""
    risk: SemanticRisk = SemanticRisk.HIGH
    status: ObligationStatus = ObligationStatus.NOT_RUN
    evidence_digest: str | None = None
    evidence_receipt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "batch": self.batch.value,
            "layer": self.layer,
            "property_name": self.property_name,
            "invariants": list(self.invariants),
            "source_construct": self.source_construct,
            "target_construct": self.target_construct,
            "input_digest": self.input_digest,
            "risk": self.risk.value,
            "status": self.status.value,
            "evidence_digest": self.evidence_digest,
            "evidence_receipt": self.evidence_receipt,
        }


@dataclass(frozen=True)
class ProofObligation:
    proof_id: str
    formula_digest: str
    solver_family: str
    assumptions: tuple[str, ...] = ()
    timeout_ms: int = 5_000
    status: ObligationStatus = ObligationStatus.NOT_RUN
    proof_receipt_digest: str | None = None
    counterexample_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "formula_digest": self.formula_digest,
            "solver_family": self.solver_family,
            "assumptions": list(self.assumptions),
            "timeout_ms": self.timeout_ms,
            "status": self.status.value,
            "proof_receipt_digest": self.proof_receipt_digest,
            "counterexample_digest": self.counterexample_digest,
        }


@dataclass(frozen=True)
class BehaviorOracle:
    oracle_id: str
    scope: str
    observable_signals: tuple[str, ...]
    input_domain_partitions: tuple[Mapping[str, Any], ...]
    side_effect_channels: tuple[str, ...]
    tolerance_epsilon: float = 0.0
    tolerance: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle_id": self.oracle_id,
            "scope": self.scope,
            "observable_signals": list(self.observable_signals),
            "input_domain_partitions": [dict(item) for item in self.input_domain_partitions],
            "side_effect_channels": list(self.side_effect_channels),
            "tolerance_epsilon": self.tolerance_epsilon,
            "tolerance": dict(self.tolerance),
        }


@dataclass(frozen=True)
class DifferentialResult:
    """Compatibility result for a caller-supplied bounded comparison.

    This structure is not external execution evidence and cannot be promoted
    to certification by itself.
    """

    run_id: str
    source_language: str
    target_language: str
    test_case_id: str
    verdict: VerdictStatus
    source_output: Any
    target_output: Any
    divergence_summary: str | None = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "test_case_id": self.test_case_id,
            "verdict": self.verdict.value,
            "source_output": self.source_output,
            "target_output": self.target_output,
            "divergence_summary": self.divergence_summary,
            "execution_time_ms": self.execution_time_ms,
            "evidence_state": EvidenceState.LOCAL_EXECUTED_SELF_ATTESTED.value,
            "certification": CertificationState.NOT_CERTIFIED.value,
        }


@dataclass(frozen=True)
class Counterexample:
    counterexample_id: str
    obligation_id: str
    input_digest: str
    source_trace_digest: str
    target_trace_digest: str
    divergence_path: str
    minimized: bool
    independently_reproduced: bool


@dataclass(frozen=True)
class CertificationRun:
    """Compatibility model for a conservative route decision."""

    certification_id: str
    route_id: str
    batch_coverage: Mapping[str, int]
    total_obligations: int
    proved_obligations: int
    counterexamples_found: int
    overall_verdict: VerdictStatus
    receipt_digest: str
    certification: CertificationState = CertificationState.NOT_CERTIFIED
    missing_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "certification_id": self.certification_id,
            "route_id": self.route_id,
            "batch_coverage": dict(self.batch_coverage),
            "total_obligations": self.total_obligations,
            "proved_obligations": self.proved_obligations,
            "counterexamples_found": self.counterexamples_found,
            "overall_verdict": self.overall_verdict.value,
            "receipt_digest": self.receipt_digest,
            "certification": self.certification.value,
            "missing_evidence": list(self.missing_evidence),
        }
