"""Common types, enums, and data models for Elmos Mature Platform Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple


class RegionId(str, Enum):
    US_EAST_1 = "us-east-1"
    EU_WEST_1 = "eu-west-1"
    AP_SOUTHEAST_1 = "ap-southeast-1"
    CN_NORTH_1 = "cn-north-1"
    AIRGAP_SOVEREIGN_1 = "airgap-sovereign-1"


class NodeRole(str, Enum):
    LEADER = "LEADER"
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    OBSERVER = "OBSERVER"
    ARBITER = "ARBITER"


class NodeStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    PARTITIONED = "PARTITIONED"
    TERMINATED = "TERMINATED"
    RECOVERING = "RECOVERING"


class FaultType(str, Enum):
    NETWORK_PARTITION = "NETWORK_PARTITION"
    LATENCY_INJECTION = "LATENCY_INJECTION"
    PACKET_DROP_CORRUPT = "PACKET_DROP_CORRUPT"
    CPU_EXHAUSTION = "CPU_EXHAUSTION"
    MEMORY_LEAK_PRESSURE = "MEMORY_LEAK_PRESSURE"
    DISK_IO_FAILURE = "DISK_IO_FAILURE"
    DISK_SPACE_EXHAUSTION = "DISK_SPACE_EXHAUSTION"
    PROCESS_CRASH_ZOMBIE = "PROCESS_CRASH_ZOMBIE"
    CLOCK_SKEW_DRIFT = "CLOCK_SKEW_DRIFT"
    POISON_MESSAGE_QUEUE = "POISON_MESSAGE_QUEUE"
    CASCADING_DEPENDENCY = "CASCADING_DEPENDENCY"
    SPLIT_BRAIN_PARTITION = "SPLIT_BRAIN_PARTITION"


class FaultState(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REVERTED = "REVERTED"
    FAILED = "FAILED"
    ABORTED_BY_GOVERNOR = "ABORTED_BY_GOVERNOR"


class SeverityLevel(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AgentAutonomyLevel(str, Enum):
    L0_MANUAL = "L0_MANUAL"
    L1_SUGGESTION = "L1_SUGGESTION"
    L2_SUPERVISED = "L2_SUPERVISED"
    L3_BOUNDED_AUTONOMOUS = "L3_BOUNDED_AUTONOMOUS"
    L4_FULL_AUTONOMOUS = "L4_FULL_AUTONOMOUS"


class UpgradeStrategy(str, Enum):
    ROLLING_UPDATE = "ROLLING_UPDATE"
    EXPAND_CONTRACT = "EXPAND_CONTRACT"
    BLUE_GREEN = "BLUE_GREEN"
    CANARY_PROGRESSIVE = "CANARY_PROGRESSIVE"
    SHADOW_MIRROR = "SHADOW_MIRROR"


class MigrationPhase(str, Enum):
    EXPAND = "EXPAND"
    DUAL_WRITE = "DUAL_WRITE"
    BACKFILL = "BACKFILL"
    CONTRACT = "CONTRACT"
    ROLLBACK = "ROLLBACK"


class TriageStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    REVOCATION_DISPATCHED = "REVOCATION_DISPATCHED"
    ROTATION_COMPLETED = "ROTATION_COMPLETED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class ZeroToleranceCategory(str, Enum):
    CROSS_TENANT_ACCESS = "cross_tenant_access"
    DATA_LOSS = "data_loss"
    UNAUTHORIZED_PUBLIC_EGRESS = "unauthorized_public_egress"
    SIGNATURE_BYPASS = "signature_bypass"
    CRITICAL_SECURITY_FINDING = "critical_security_finding"
    CRITICAL_UNKNOWN = "critical_unknown"
    KILL_SWITCH_FAILURE = "kill_switch_failure"
    BILLING_UNRECONCILED = "billing_unreconciled"
    TEST_INTEGRITY_VIOLATION = "test_integrity_violation"
    EVIDENCE_TAMPER = "evidence_tamper"
    STALE_MANDATORY_EVIDENCE = "stale_mandatory_evidence"
    UNREPLAYED_CRITICAL_FAILURE = "unreplayed_critical_failure"


@dataclass
class NodeInfo:
    node_id: str
    region_id: RegionId
    zone: str
    ip_address: str
    role: NodeRole = NodeRole.FOLLOWER
    status: NodeStatus = NodeStatus.HEALTHY
    term: int = 1
    voted_for: Optional[str] = None
    commit_index: int = 0
    fencing_token: int = 1000
    heartbeat_received_at: float = 0.0
    storage_used_bytes: int = 0
    storage_total_bytes: int = 100 * 1024 * 1024 * 1024  # 100 GB


@dataclass
class ConsensusState:
    term: int
    leader_id: Optional[str]
    commit_index: int
    fencing_token: int
    nodes_count: int


@dataclass
class LatencySpec:
    mean_ms: float
    jitter_ms: float
    packet_loss_rate: float = 0.0
    corruption_rate: float = 0.0


@dataclass
class RegionTopology:
    region_id: RegionId
    is_primary: bool
    nodes: Dict[str, NodeInfo] = field(default_factory=dict)
    wan_latency_matrix: Dict[RegionId, LatencySpec] = field(default_factory=dict)
    partitioned_peers: Set[RegionId] = field(default_factory=set)


@dataclass
class JwtClaims:
    iss: str
    sub: str
    aud: str
    exp: int
    nbf: int
    iat: int
    jti: str
    tenant_id: str
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    scope: str = "enterprise.mature.platform"


@dataclass
class OidcTokenResult:
    token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    claims: Optional[JwtClaims] = None
    signature_valid: bool = True
    revoked: bool = False


@dataclass
class TokenRevocationRecord:
    jti: str
    revoked_at: str
    tenant_id: str
    reason: str
    actor: str


@dataclass
class RbacRule:
    role: str
    allowed_actions: List[str]
    allowed_resources: List[str]
    tenant_bound: bool = True


@dataclass
class KmsKeyDescriptor:
    key_id: str
    version: int
    algorithm: str = "AES-256-GCM"
    created_at: str = ""
    is_revoked: bool = False
    is_shredded: bool = False
    rotation_interval_days: int = 90
    raw_key_bytes: bytes = field(default_factory=bytes)


@dataclass
class EncryptedPayload:
    key_id: str
    key_version: int
    algorithm: str
    ciphertext_b64: str
    iv_b64: str
    tag_b64: str
    aad_b64: str
    encrypted_dek_b64: str
    sha256_ciphertext: str


@dataclass
class CryptoAuditEntry:
    entry_id: str
    timestamp: str
    operation: str
    key_id: str
    key_version: int
    tenant_id: str
    actor: str
    status: str
    prev_hash: str
    entry_hash: str


@dataclass
class FaultDescriptor:
    fault_id: str
    fault_type: FaultType
    target_region: RegionId
    target_node_ids: List[str]
    parameters: Dict[str, Any] = field(default_factory=dict)
    state: FaultState = FaultState.PENDING
    started_at: Optional[str] = None
    reverted_at: Optional[str] = None
    impact_summary: str = ""


@dataclass
class ChaosExperimentConfig:
    experiment_id: str
    title: str
    target_faults: List[FaultDescriptor]
    max_duration_seconds: float = 60.0
    allowed_error_rate_threshold: float = 0.05
    allowed_latency_p99_ms_threshold: float = 500.0
    abort_on_zero_tolerance: bool = True


@dataclass
class ChaosExecutionResult:
    experiment_id: str
    success: bool
    faults_executed: int
    faults_reverted: int
    governor_interventions: int
    zero_tolerance_violations: int
    telemetry_summary: Dict[str, Any] = field(default_factory=dict)
    log_traces: List[str] = field(default_factory=list)


@dataclass
class MetricSample:
    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class HistogramSnapshot:
    count: int
    total_sum: float
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    p999: float
    min_val: float
    max_val: float


@dataclass
class SloDefinition:
    slo_id: str
    name: str
    target_percentage: float  # e.g. 99.9%
    metric_name: str
    threshold_value: float  # e.g. latency < 100ms
    window_seconds: int = 3600


@dataclass
class SloEvaluationResult:
    slo_id: str
    target_percentage: float
    actual_percentage: float
    is_compliant: bool
    error_budget_remaining: float
    burn_rate_1h: float
    burn_rate_6h: float


@dataclass
class AlertRecord:
    alert_id: str
    slo_id: str
    severity: SeverityLevel
    message: str
    triggered_at: str
    resolved_at: Optional[str] = None
    acknowledged: bool = False


@dataclass
class SecretFinding:
    rule_id: str
    path: str
    line_number: int
    entropy: float
    secret_type: str
    snippet_masked: str
    severity: SeverityLevel


@dataclass
class CredentialTriageCase:
    triage_id: str
    secret_type: str
    compromised_credential: str
    tenant_id: str
    status: TriageStatus
    detected_at: str
    revocation_timestamp: Optional[str] = None
    affected_assets: List[str] = field(default_factory=list)
    remediation_log: List[str] = field(default_factory=list)


@dataclass
class SbomComponent:
    component_id: str
    name: str
    version: str
    purl: str
    sha256: str
    license: str
    cves: List[str] = field(default_factory=list)


@dataclass
class VulnerabilityFinding:
    cve_id: str
    component_name: str
    installed_version: str
    fixed_version: str
    cvss_score: float
    severity: SeverityLevel
    has_exploit: bool = False
    vex_status: str = "under_investigation"  # affected, not_affected, under_investigation


@dataclass
class DrPlan:
    plan_id: str
    primary_region: RegionId
    secondary_regions: List[RegionId]
    rto_target_seconds: float
    rpo_target_seconds: float
    expand_contract_required: bool = False


@dataclass
class MerkleNode:
    hash_value: str
    left: Optional[MerkleNode] = None
    right: Optional[MerkleNode] = None
    data_block: Optional[bytes] = None


@dataclass
class ReconciliationResult:
    reconciled: bool
    source_records_count: int
    target_records_count: int
    divergent_keys: List[str]
    rpo_divergence_seconds: float
    data_loss_detected: bool = False
    primary_root_hash: str = ""
    replica_root_hash: str = ""


@dataclass
class DrDrillExecution:
    drill_id: str
    plan_id: str
    triggered_at: str
    completed_at: str
    rto_measured_seconds: float
    rpo_measured_seconds: float
    rto_met: bool
    rpo_met: bool
    data_reconciliation: ReconciliationResult
    failover_status: str
    drill_logs: List[str] = field(default_factory=list)


@dataclass
class AgentDescriptor:
    agent_id: str
    name: str
    role: str
    autonomy_level: AgentAutonomyLevel
    permissions: List[str] = field(default_factory=list)
    active_lease_id: Optional[str] = None
    is_killed: bool = False


@dataclass
class ToolPermissionBoundary:
    tool_name: str
    allowed_autonomy_levels: List[AgentAutonomyLevel]
    allowed_tenants: List[str]
    rate_limit_per_minute: int
    requires_human_approval: bool = False
    sandbox_required: bool = True


@dataclass
class KillSwitchEvent:
    event_id: str
    target_agent_id: str
    reason: str
    initiated_by: str
    timestamp: str
    confirmed_killed: bool
    rollback_applied: bool


@dataclass
class UsageRecord:
    tenant_id: str
    resource_type: str  # cpu_hours, memory_gb_hours, storage_gb_months, egress_gb, token_count
    quantity: float
    unit_price: float
    total_cost: float
    recorded_at: str


@dataclass
class InvoiceLineItem:
    item_id: str
    tenant_id: str
    period: str
    resource_type: str
    billed_units: float
    billed_amount: float
    metered_units: float
    reconciled: bool
    discrepancy: float = 0.0


@dataclass
class MarginReport:
    period: str
    total_revenue: float
    infra_costs: float
    third_party_costs: float
    gross_margin_percentage: float
    margin_threshold_compliant: bool


@dataclass
class ScenarioContext:
    case_id: str
    batch: int
    title: str
    category: str
    priority: str
    skill_name: str
    started_at: str
    environment_digest: str
    artifact_digest: str
    executor_id: str = "elmos-b38-45-platform-executor"
    verifier_id: str = "ethan-independent-certifier"


@dataclass
class ScenarioAssertion:
    name: str
    passed: bool
    details: str
    zero_tolerance_category: Optional[ZeroToleranceCategory] = None


@dataclass
class ScenarioExecutionReport:
    case_id: str
    status: str  # passed, failed, blocked
    started_at: str
    finished_at: str
    duration_seconds: float
    assertions: List[ScenarioAssertion] = field(default_factory=list)
    zero_tolerance_counters: Dict[str, int] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    log_traces: List[str] = field(default_factory=list)
    trace_coverage: float = 1.0

    @property
    def has_zero_tolerance_violations(self) -> bool:
        return any(v > 0 for v in self.zero_tolerance_counters.values())
