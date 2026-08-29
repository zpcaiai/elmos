"""Strongly typed domain models for Elmos Commercial Capability Expansion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, List, Optional


class KernelType(str, Enum):
    K1_SKILL_RUNTIME = "K1-skill-runtime"
    K2_REPOSITORY_INTELLIGENCE = "K2-repository-intelligence"
    K3_TRANSFORMATION = "K3-transformation"
    K4_BUILD_EXECUTION = "K4-build-execution"
    K5_VERIFICATION = "K5-verification"
    K6_SECURITY_GOVERNANCE = "K6-security-governance"
    K7_DATABASE_DATA = "K7-database-data"
    K8_OBSERVABILITY_EVOLUTION = "K8-observability-evolution"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class GateLevel(str, Enum):
    E0_INGESTION = "E0"
    E1_SYNTAX_COMPILE = "E1"
    E2_UNIT_INTEGRATION = "E2"
    E3_SECURITY_ISOLATION = "E3"
    E4_DIFFERENTIAL_RUNTIME = "E4"
    E5_FORMAL_PROVENANCE = "E5"


class DecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CONDITIONAL = "CONDITIONAL"
    REVISE = "REVISE"
    NOT_RUN = "NOT_RUN"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class TaskContext:
    tenant_id: str
    repository_id: str
    objective: str
    branch: str = "main"
    commit_sha: str = "HEAD"
    budget_tokens: int = 100_000
    budget_usd: float = 5.0
    timeout_seconds: int = 600
    user_id: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillDefinition:
    id: str
    name: str
    kernel: KernelType
    priority: Priority
    objective: str
    path: str
    kind: str = "production-skill"
    inspirations: List[str] = field(default_factory=list)
    activation_conditions: List[str] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kernel"] = self.kernel.value
        d["priority"] = self.priority.value
        return d


@dataclass
class PolicyDecision:
    decision_id: str
    principal: str
    action: str
    resource: str
    allowed: bool
    status: DecisionStatus
    obligations: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class RiskAssessment:
    assessment_id: str
    blast_radius: int
    affected_modules: List[str]
    risk_score: float
    risk_level: RiskLevel
    mandatory_obligations: List[str]
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        return d


@dataclass
class EvidenceRecord:
    evidence_id: str
    category: str
    source_skill: str
    digest: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    status: str = "COLLECTED"
    collected_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProvenanceAttestation:
    attestation_id: str
    subject_name: str
    subject_digest: str
    predicate_type: str = "https://slsa.dev/provenance/v1"
    builder_id: str = "https://elmos.ai/builder/commercial-expansion@v2.0.0"
    invocation: Dict[str, Any] = field(default_factory=dict)
    materials: List[Dict[str, str]] = field(default_factory=list)
    slsa_level: str = "SLSA_BUILD_LEVEL_3"
    signature: str = ""
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def compute_signature(self, secret_key: str = "elmos-internal-signing-key") -> str:
        payload = f"{self.subject_name}:{self.subject_digest}:{self.builder_id}:{self.created_at}:{secret_key}"
        self.signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self.signature

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class E0E5GateDecision:
    target_gate: GateLevel
    status: DecisionStatus
    passed: bool
    evaluated_criteria: List[str]
    evidence_bundle_ref: str
    residual_risk: str
    evaluated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["target_gate"] = self.target_gate.value
        d["status"] = self.status.value
        return d


@dataclass
class Checkpoint:
    checkpoint_id: str
    task_id: str
    step_number: int
    state_snapshot: Dict[str, Any]
    completed_steps: List[str]
    next_step: str
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrajectoryRecord:
    trajectory_id: str
    task_id: str
    steps_executed: int
    tool_calls_count: int
    outcome: str
    tokens_consumed: int
    wall_clock_ms: int
    evidence_refs: List[str] = field(default_factory=list)
    recorded_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
