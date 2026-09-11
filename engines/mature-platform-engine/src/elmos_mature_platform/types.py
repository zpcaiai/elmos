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
    component_id: str = ""
    name: str = ""
    version: str = ""
    purl: str = ""
    sha256: str = ""
    license: str = ""
    cves: List[str] = field(default_factory=list)
    license_id: str = ""
    direct: bool = True
    checksum_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.component_id and self.purl:
            self.component_id = self.purl
        if not self.purl and self.component_id:
            self.purl = self.component_id
        if not self.license_id and self.license:
            self.license_id = self.license
        if not self.license and self.license_id:
            self.license = self.license_id
        if not self.checksum_sha256 and self.sha256:
            self.checksum_sha256 = self.sha256
        if not self.sha256 and self.checksum_sha256:
            self.sha256 = self.checksum_sha256


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

    @property
    def mismatched_keys(self) -> List[str]:
        return self.divergent_keys


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

    @property
    def invoice_id(self) -> str:
        return self.item_id


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


# ─── Incident Command & On-Call Models ───────────────────────────────

class IncidentSeverity(str, Enum):
    """Incident severity levels per SRE classification."""
    SEV1 = "sev1"  # Critical: complete service outage
    SEV2 = "sev2"  # Major: significant degradation
    SEV3 = "sev3"  # Minor: limited impact
    SEV4 = "sev4"  # Low: cosmetic or informational

class IncidentStatus(str, Enum):
    """Lifecycle states of an incident."""
    DECLARED = "declared"
    TRIAGING = "triaging"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"
    POST_MORTEM = "post_mortem"
    CLOSED = "closed"

class EscalationTier(str, Enum):
    """On-call escalation tiers."""
    TIER_1 = "tier_1"  # First responder
    TIER_2 = "tier_2"  # Senior engineer
    TIER_3 = "tier_3"  # Domain expert / architect
    MANAGEMENT = "management"  # VP/Director escalation

class OnCallShift(str, Enum):
    """Follow-the-sun rotation shifts."""
    APAC = "apac"      # UTC+8 to UTC+12
    EMEA = "emea"      # UTC+0 to UTC+3  
    AMERICAS = "americas"  # UTC-8 to UTC-5

@dataclass
class OnCallEngineer:
    """An engineer in the on-call rotation."""
    engineer_id: str
    name: str
    email: str
    tier: EscalationTier
    shift: OnCallShift
    is_available: bool = True
    max_concurrent_incidents: int = 3
    current_incident_count: int = 0

@dataclass
class IncidentRecord:
    """A tracked incident record with full lifecycle."""
    incident_id: str
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    declared_at: str
    declaring_user: str
    tenant_id: str
    affected_regions: List[RegionId] = field(default_factory=list)
    assigned_commander: Optional[str] = None
    assigned_responders: List[str] = field(default_factory=list)
    status_updates: List[Dict[str, str]] = field(default_factory=list)
    mitigation_actions: List[str] = field(default_factory=list)
    resolved_at: Optional[str] = None
    root_cause: Optional[str] = None
    post_mortem_url: Optional[str] = None
    customer_communication_sent: bool = False
    sla_breach: bool = False
    error_budget_impact_percent: float = 0.0
    escalation_log: List[Dict[str, str]] = field(default_factory=list)

@dataclass
class StatusPageUpdate:
    """A customer-facing status page update."""
    update_id: str
    incident_id: str
    timestamp: str
    component: str
    status: str  # operational, degraded_performance, partial_outage, major_outage
    message: str
    is_public: bool = True

@dataclass
class ServiceCatalogEntry:
    """A service in the platform service catalog with SLI/SLO definitions."""
    service_id: str
    name: str
    owner_team: str
    tier: str  # critical, standard, best-effort
    slo_ids: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    regions: List[RegionId] = field(default_factory=list)
    health_check_url: str = ""
    runbook_url: str = ""

@dataclass
class ChangeFreeze:
    """A change freeze window."""
    freeze_id: str
    reason: str
    started_at: str
    ends_at: str
    scope: str  # global, region, service
    approved_by: str
    exceptions: List[str] = field(default_factory=list)  # service_ids exempt
    is_active: bool = True

@dataclass
class CapacityPlan:
    """Autoscaling capacity plan for a service."""
    plan_id: str
    service_id: str
    region: RegionId
    min_replicas: int
    max_replicas: int
    current_replicas: int
    target_cpu_percent: float = 70.0
    target_memory_percent: float = 80.0
    scale_up_cooldown_seconds: int = 300
    scale_down_cooldown_seconds: int = 600
    last_scale_event: Optional[str] = None


# ─── Supply Chain Security Models ────────────────────────────────────

class ScanType(str, Enum):
    """Types of security scans."""
    SAST = "sast"  # Static Application Security Testing
    DAST = "dast"  # Dynamic Application Security Testing  
    SCA = "sca"    # Software Composition Analysis
    CONTAINER = "container"  # Container image scanning
    IAC = "iac"    # Infrastructure as Code scanning
    SECRET = "secret"  # Secret detection (already exists partially)

class ScanStatus(str, Enum):
    """Status of a security scan."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class VexJustification(str, Enum):
    """VEX justification for not-affected status."""
    COMPONENT_NOT_PRESENT = "component_not_present"
    VULNERABLE_CODE_NOT_PRESENT = "vulnerable_code_not_present"
    VULNERABLE_CODE_NOT_IN_EXECUTE_PATH = "vulnerable_code_not_in_execute_path"
    VULNERABLE_CODE_CANNOT_BE_CONTROLLED_BY_ADVERSARY = "vulnerable_code_cannot_be_controlled_by_adversary"
    INLINE_MITIGATIONS_EXIST = "inline_mitigations_exist"

class ArtifactType(str, Enum):
    """Types of build artifacts."""
    CONTAINER_IMAGE = "container_image"
    BINARY = "binary"
    LIBRARY = "library"
    HELM_CHART = "helm_chart"
    TERRAFORM_MODULE = "terraform_module"

@dataclass
class ScanResult:
    """Result of a single security scan."""
    scan_id: str
    scan_type: ScanType
    target: str  # file path, image ref, or URL
    status: ScanStatus
    started_at: str
    completed_at: Optional[str] = None
    findings_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    findings: List[Dict[str, Any]] = field(default_factory=list)
    tool_name: str = ""
    tool_version: str = ""

@dataclass  
class SlsaProvenance:
    """SLSA provenance attestation for a build artifact."""
    artifact_id: str
    artifact_type: ArtifactType
    sha256_digest: str
    builder_id: str
    build_type: str
    source_repo: str
    source_commit: str
    source_branch: str
    build_timestamp: str
    slsa_level: int  # 1-4
    reproducible: bool = False
    hermetic: bool = False
    entry_point: str = ""
    parameters: Dict[str, str] = field(default_factory=dict)
    materials: List[Dict[str, str]] = field(default_factory=list)
    signature: str = ""

@dataclass
class ArtifactSignature:
    """Cryptographic signature for a build artifact."""
    artifact_id: str
    sha256_digest: str
    signature_b64: str
    signer_identity: str
    signing_key_id: str
    signing_timestamp: str
    certificate_chain: List[str] = field(default_factory=list)
    verified: bool = False

@dataclass
class ThreatModelEntry:
    """An entry in a threat model."""
    threat_id: str
    category: str  # STRIDE: Spoofing, Tampering, Repudiation, Info Disclosure, DoS, EoP
    title: str
    description: str
    attack_vector: str
    severity: SeverityLevel
    mitigations: List[str] = field(default_factory=list)
    residual_risk: str = "low"
    review_status: str = "open"  # open, mitigated, accepted, transferred

@dataclass
class VexStatement:
    """Vulnerability Exploitability eXchange statement."""
    vex_id: str
    cve_id: str = ""
    product_id: str = ""
    status: Any = "under_investigation"  # not_affected, affected, fixed, under_investigation, or VulnStatus
    justification: Optional[SbomVexJustification] = None
    impact_statement: str = ""
    action_statement: str = ""
    timestamp: str = ""
    vuln_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.cve_id and self.vuln_id:
            self.cve_id = self.vuln_id
        if not self.vuln_id and self.cve_id:
            self.vuln_id = self.cve_id
        if not self.timestamp and self.created_at:
            self.timestamp = self.created_at
        if not self.created_at and self.timestamp:
            self.created_at = self.timestamp

@dataclass
class ComplianceControlMapping:
    """Mapping of compliance controls to evidence."""
    control_id: str
    framework: str  # SOC2, ISO27001, NIST-CSF, etc.
    control_name: str
    evidence_refs: List[str] = field(default_factory=list)
    status: str = "not_assessed"  # not_assessed, compliant, non_compliant, partially_compliant
    last_assessed: Optional[str] = None
    assessor: str = ""
    notes: str = ""

# ─── Knowledge Flywheel Models ─────────────────────────────────────

class KnowledgeConfidence(str, Enum):
    """Confidence level for knowledge entries."""
    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"

@dataclass
class KnowledgeEntry:
    """A single entry in the migration knowledge graph."""
    entry_id: str
    category: str  # pattern, anti-pattern, recipe, decision, risk
    source_technology: str
    target_technology: str
    title: str
    description: str
    confidence: KnowledgeConfidence
    evidence_refs: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    usage_count: int = 0
    success_rate: float = 0.0
    tenant_id: Optional[str] = None  # None = shared, else tenant-isolated

@dataclass
class MigrationPattern:
    """A reusable migration pattern extracted from successful migrations."""
    pattern_id: str
    name: str
    source_stack: str
    target_stack: str
    complexity: str  # low, medium, high, critical
    estimated_effort_hours: float
    success_count: int = 0
    failure_count: int = 0
    recipe_ids: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)

@dataclass
class PredictionResult:
    """Result of a migration prediction (risk, effort, duration)."""
    prediction_id: str
    prediction_type: str  # risk, effort, duration, success_probability
    predicted_value: float
    confidence_interval_low: float
    confidence_interval_high: float
    model_version: str
    features_used: List[str] = field(default_factory=list)
    calibration_score: float = 0.0  # 0-1, how well-calibrated the model is

# ─── Product Lifecycle Models ─────────────────────────────────────

class ApiChangeType(str, Enum):
    """Types of API changes."""
    ADDITION = "addition"
    DEPRECATION = "deprecation"
    BREAKING = "breaking"
    REMOVAL = "removal"
    MODIFICATION = "modification"

class ReleaseChannel(str, Enum):
    """Release channels for product versions."""
    NIGHTLY = "nightly"
    BETA = "beta"
    RC = "rc"  # Release Candidate
    STABLE = "stable"
    LTS = "lts"  # Long Term Support

class SupportStatus(str, Enum):
    """Support lifecycle status."""
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    SECURITY_ONLY = "security_only"
    END_OF_LIFE = "end_of_life"

@dataclass
class ApiCompatibilityCheck:
    """Result of an API compatibility check between versions."""
    check_id: str
    api_surface: str  # REST, gRPC, SDK, event-schema, PSP, UIR
    from_version: str
    to_version: str
    changes: List[Dict[str, Any]] = field(default_factory=list)  # {type, path, detail}
    breaking_changes_count: int = 0
    backward_compatible: bool = True
    forward_compatible: bool = False

@dataclass
class DeprecationRecord:
    """Tracks a deprecation notice."""
    deprecation_id: str
    feature: str
    deprecated_in: str  # version
    removal_target: str  # version
    migration_guide: str
    replacement: Optional[str] = None
    affected_customers: int = 0
    customer_ack_count: int = 0

@dataclass
class ReleaseCandidate:
    """A release candidate with quality gates."""
    rc_id: str
    version: str
    channel: ReleaseChannel
    build_sha: str
    gates_passed: Dict[str, bool] = field(default_factory=dict)
    # gates: unit_tests, integration_tests, security_scan, performance_baseline, api_compat, ...
    overall_status: str = "pending"  # pending, approved, rejected, released
    created_at: str = ""
    approved_by: Optional[str] = None

@dataclass
class SupportPolicy:
    """Support policy for a version."""
    version: str
    channel: ReleaseChannel
    status: SupportStatus
    release_date: str
    active_support_end: str
    security_support_end: str
    eol_date: str
    lts_extended: bool = False


# ─── Edition Deployment Models ──────────────────────────────────────

class EditionType(str, Enum):
    """Platform edition deployment types."""
    MULTITENANT_SAAS = "multitenant_saas"
    DEDICATED_SAAS = "dedicated_saas"
    CUSTOMER_VPC = "customer_vpc"
    SELF_HOSTED = "self_hosted"
    PRIVATE_SOVEREIGN = "private_sovereign"
    AIR_GAPPED = "air_gapped"
    EDGE_RESTRICTED = "edge_restricted"
    MULTIREGION_ACTIVE = "multiregion_active"

class UpgradePhase(str, Enum):
    """Phases of an upgrade lifecycle."""
    PRE_CHECK = "pre_check"
    BACKUP = "backup"
    EXPAND = "expand"
    MIGRATE = "migrate"
    VERIFY = "verify"
    CONTRACT = "contract"
    ROLLBACK = "rollback"
    COMPLETE = "complete"

class PlaneType(str, Enum):
    """Control/data plane topology."""
    CONTROL_PLANE = "control_plane"
    DATA_PLANE = "data_plane"
    MANAGEMENT_PLANE = "management_plane"
    OBSERVABILITY_PLANE = "observability_plane"

@dataclass
class EditionDeployment:
    """A deployed edition instance."""
    deployment_id: str
    edition_type: EditionType
    tenant_id: str
    region: RegionId
    version: str
    previous_version: Optional[str] = None
    planes: List[PlaneType] = field(default_factory=lambda: [PlaneType.CONTROL_PLANE, PlaneType.DATA_PLANE])
    is_active: bool = True
    upgrade_strategy: UpgradeStrategy = UpgradeStrategy.ROLLING_UPDATE
    network_isolated: bool = False  # True for air-gapped
    data_residency_region: Optional[str] = None  # For sovereign
    max_tenants: int = 1  # >1 for multitenant
    resource_limits: Dict[str, Any] = field(default_factory=dict)

@dataclass
class UpgradeExecution:
    """Tracks execution of a version upgrade."""
    upgrade_id: str
    deployment_id: str
    from_version: str
    to_version: str
    strategy: UpgradeStrategy
    phase: UpgradePhase = UpgradePhase.PRE_CHECK
    started_at: str = ""
    completed_at: Optional[str] = None
    backup_id: Optional[str] = None
    rollback_available: bool = True
    pre_check_passed: bool = False
    verify_passed: bool = False
    migration_log: List[str] = field(default_factory=list)
    error: Optional[str] = None

@dataclass
class VersionCompatibility:
    """Version compatibility matrix entry."""
    source_version: str
    target_version: str
    compatible: bool
    requires_migration: bool = False
    breaking_changes: List[str] = field(default_factory=list)
    deprecated_features: List[str] = field(default_factory=list)
    minimum_runner_version: Optional[str] = None

@dataclass 
class PlaneTopology:
    """Plane topology for an edition."""
    topology_id: str
    deployment_id: str
    planes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # planes maps plane_type -> {region, replicas, version, health}
    cross_plane_connectivity: List[Tuple[str, str]] = field(default_factory=list)
    last_health_check: Optional[str] = None


# ─── Maturity Certification Models ──────────────────────────────────

class MaturityDimension(str, Enum):
    """Dimensions of product maturity assessment."""
    FUNCTIONAL_DEPTH = "functional_depth"
    SEMANTIC_BEHAVIOR = "semantic_behavior"
    ROUTE_BREADTH = "route_breadth"
    SCALE_PERFORMANCE = "scale_performance"
    SECURITY_DATA = "security_data"
    SRE_RELIABILITY = "sre_reliability"
    DEVELOPER_EXPERIENCE = "developer_experience"
    ECONOMICS_PROFITABILITY = "economics_profitability"
    DEPLOYMENT_MATRIX = "deployment_matrix"
    ECOSYSTEM_MARKETPLACE = "ecosystem_marketplace"
    TARGET_MAINTAINABILITY = "target_maintainability"
    CUSTOMER_VALUE = "customer_value"

class MaturityLevel(str, Enum):
    """Maturity levels."""
    L0_ABSENT = "l0_absent"
    L1_INITIAL = "l1_initial"
    L2_DEVELOPING = "l2_developing"
    L3_DEFINED = "l3_defined"
    L4_MEASURED = "l4_measured"
    L5_OPTIMIZING = "l5_optimizing"

class CertificationDecision(str, Enum):
    """Certification gate decisions."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    CONDITIONALLY_APPROVED = "conditionally_approved"
    APPROVED = "approved"
    REJECTED = "rejected"

@dataclass
class DimensionAssessment:
    """Assessment of a single maturity dimension."""
    dimension: MaturityDimension
    level: MaturityLevel
    score: float  # 0.0 - 100.0
    evidence_count: int = 0
    passing_tests: int = 0
    total_tests: int = 0
    gaps: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    notes: str = ""

@dataclass
class ResidualRisk:
    """A residual risk that cannot be fully mitigated."""
    risk_id: str
    dimension: MaturityDimension
    title: str
    description: str
    severity: SeverityLevel
    probability: str  # low, medium, high
    impact: str  # low, medium, high, critical
    mitigation: str
    accepted_by: Optional[str] = None
    accepted_at: Optional[str] = None
    expiry_date: Optional[str] = None  # Risk acceptance expires

@dataclass
class MaturityReport:
    """Complete maturity assessment report."""
    report_id: str
    product_version: str
    assessment_date: str
    assessor: str
    dimensions: List[DimensionAssessment] = field(default_factory=list)
    overall_score: float = 0.0
    overall_level: MaturityLevel = MaturityLevel.L0_ABSENT
    residual_risks: List[ResidualRisk] = field(default_factory=list)
    certification_decision: CertificationDecision = CertificationDecision.NOT_STARTED
    blocking_dimensions: List[MaturityDimension] = field(default_factory=list)
    gate_results: Dict[str, bool] = field(default_factory=dict)

@dataclass
class ProductionReadinessChecklist:
    """Production readiness review checklist."""
    checklist_id: str
    service_name: str
    items: Dict[str, bool] = field(default_factory=dict)
    reviewed_by: Optional[str] = None
    review_date: Optional[str] = None
    overall_ready: bool = False

# ─── Cost Economics & FinOps Advanced Models ─────────────────────

class CostCategory(str, Enum):
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK_EGRESS = "network_egress"
    MODEL_INFERENCE = "model_inference"
    HUMAN_REVIEW = "human_review"
    SUPPORT = "support"
    LICENSING = "licensing"
    RUNNER_FLEET = "runner_fleet"

@dataclass
class CostLineItem:
    item_id: str
    category: CostCategory
    description: str = ""
    quantity: float = 0.0
    unit_price: float = 0.0
    total_cost: float = 0.0
    currency: str = "USD"
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    timestamp: str = ""
    name: str = ""
    monthly_cost: float = 0.0
    unit_cost: float = 0.0
    growth_rate_pct: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass
class CostScenarioForecast:
    scenario_id: str
    scenario_name: str  # baseline, growth_10pct, growth_50pct, etc.
    time_horizon_months: int
    projected_monthly_costs: List[float] = field(default_factory=list)
    assumptions: Dict[str, str] = field(default_factory=dict)
    confidence_interval_pct: float = 90.0

@dataclass
class ROIAnalysis:
    analysis_id: str
    migration_cost: float
    annual_savings: float
    payback_period_months: float
    three_year_roi_pct: float
    risk_adjusted_roi_pct: float
    assumptions: Dict[str, str] = field(default_factory=dict)

@dataclass
class UnitEconomics:
    unit_type: str  # per_migration, per_repository, per_route, per_tenant
    cost_per_unit: float
    revenue_per_unit: float
    margin_per_unit: float
    margin_pct: float
    breakeven_units: int = 0

@dataclass
class BudgetAlert:
    alert_id: str
    tenant_id: str
    budget_limit: float
    current_spend: float
    utilization_pct: float
    threshold_breached: str  # 80pct_warning, 90pct_critical, 100pct_exceeded
    projected_overage: float = 0.0


# ─── Tenant Isolation Models ─────────────────────────────────────

class TenantIsolationLevel(str, Enum):
    SHARED_CLUSTER = "shared_cluster"
    CONTAINER_HARDENED = "container_hardened"
    ROW_LEVEL_SECURITY = "row_level_security"
    SCHEMA_PER_TENANT = "schema_per_tenant"
    DEDICATED_INSTANCE = "dedicated_instance"

@dataclass
class TenantDescriptor:
    tenant_id: str
    name: str
    edition: str
    isolation_level: TenantIsolationLevel
    residency_region: RegionId
    kms_key_arn: str
    status: str  # ACTIVE, SUSPENDED, TERMINATED
    max_concurrent_runners: int = 10
    cpu_cores_limit: float = 8.0
    memory_gb_limit: float = 32.0
    storage_gb_limit: float = 100.0
    rate_limit_rps: float = 100.0

@dataclass
class TenantResourceUsage:
    tenant_id: str
    active_runners: int = 0
    allocated_cpu_cores: float = 0.0
    allocated_memory_gb: float = 0.0
    current_storage_bytes: int = 0
    period_egress_bytes: int = 0
    request_count: int = 0

@dataclass
class TenantWorkspaceBinding:
    workspace_id: str
    tenant_id: str
    cgroup_path: str
    network_namespace: str
    fs_mounts: Dict[str, str] = field(default_factory=dict)
    container_security_profile: str = "no-new-privileges"
    read_only_rootfs: bool = True

@dataclass
class IsolationEnforcementResult:
    allowed: bool
    tenant_id: str
    resource_target: str
    boundary_type: str  # COMPUTE, STORAGE, NETWORK, CRYPTO
    violation_code: Optional[str] = None
    audit_message: str = ""

# ─── Rolling Upgrade Models ──────────────────────────────────────

class CanaryDecision(str, Enum):
    PROCEED = "proceed"
    HOLD = "hold"
    ROLLBACK = "rollback"

@dataclass
class CanaryWaveSpec:
    wave_number: int
    traffic_percentage: float  # 5.0, 25.0, 100.0
    observation_window_seconds: float = 300.0
    max_error_rate: float = 0.001  # 0.1%
    max_p99_latency_ms: float = 100.0

@dataclass
class RollingUpgradePlan:
    plan_id: str
    source_version: str
    target_version: str
    waves: List[CanaryWaveSpec] = field(default_factory=list)
    draining_timeout_seconds: float = 30.0
    auto_rollback_on_breach: bool = True

@dataclass
class CanaryObservation:
    wave_number: int
    total_requests: int
    error_requests: int
    p95_latency_ms: float
    p99_latency_ms: float
    error_rate: float = 0.0
    observation_duration_seconds: float = 0.0

@dataclass
class DrainingStatus:
    instance_id: str
    deregistered: bool
    inflight_requests: int
    drained_successfully: bool
    elapsed_seconds: float = 0.0

@dataclass
class RollbackRecord:
    rollback_id: str
    plan_id: str
    trigger_reason: str
    initiated_at: str
    completed_at: str
    rollback_duration_ms: float
    restored_version: str
    success: bool

# ─── Agent Red Team & Governance Models ──────────────────────────

class AgentTestCategory(str, Enum):
    PROMPT_INJECTION = "prompt_injection"
    TOOL_ABUSE = "tool_abuse"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    RUNAWAY_LOOP = "runaway_loop"
    BUDGET_EXHAUSTION = "budget_exhaustion"
    INSTRUCTION_OVERRIDE = "instruction_override"
    CROSS_TENANT_LEAK = "cross_tenant_leak"

class AgentTestVerdict(str, Enum):
    DEFENDED = "defended"
    VULNERABLE = "vulnerable"
    PARTIAL = "partial"
    INCONCLUSIVE = "inconclusive"

@dataclass
class RedTeamScenario:
    scenario_id: str
    category: AgentTestCategory
    attack_description: str
    attack_payload: str
    expected_defense: str
    severity: SeverityLevel = SeverityLevel.HIGH

@dataclass
class RedTeamResult:
    scenario_id: str
    verdict: AgentTestVerdict
    defense_triggered: bool
    attack_blocked: bool
    response_contained: bool
    details: str = ""
    elapsed_ms: float = 0.0

@dataclass
class AgentShadowResult:
    shadow_id: str
    agent_id: str
    production_output: Dict[str, Any] = field(default_factory=dict)
    shadow_output: Dict[str, Any] = field(default_factory=dict)
    divergence_score: float = 0.0
    divergent_fields: List[str] = field(default_factory=list)
    safe_to_promote: bool = True

@dataclass
class AgentConsensusResult:
    decision_id: str
    agent_votes: Dict[str, str] = field(default_factory=dict)
    consensus_reached: bool = False
    winning_decision: str = ""
    agreement_ratio: float = 0.0
    requires_human_arbitration: bool = False


# ─── Version Compatibility Models ────────────────────────────────

@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str = ""
    
    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base
    
    def __lt__(self, other: 'SemVer') -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other: 'SemVer') -> bool:
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)

@dataclass
class ComponentVersionMatrix:
    control_plane_version: SemVer
    min_runner_version: SemVer
    max_runner_version: SemVer
    supported_api_versions: List[str] = field(default_factory=list)
    supported_schema_versions: List[str] = field(default_factory=list)
    deprecated_features: List[str] = field(default_factory=list)

@dataclass
class RunnerHandshakeRequest:
    runner_id: str
    runner_version: SemVer
    protocol_version: int
    capabilities: List[str] = field(default_factory=list)
    runtime_env: str = "linux-amd64"

@dataclass
class RunnerHandshakeResponse:
    accepted: bool
    negotiated_protocol: int = 0
    rejection_reason: str = ""
    lease_duration_seconds: float = 300.0

@dataclass
class WireCompatibilityResult:
    message_type: str
    backward_compatible: bool
    forward_compatible: bool
    unknown_fields_preserved: bool
    breaking_changes: List[str] = field(default_factory=list)

@dataclass
class SchemaBreakingChange:
    change_type: str  # FIELD_REMOVED, TYPE_CHANGED, REQUIRED_ADDED
    field_path: str
    description: str
    severity: str  # breaking, deprecated, compatible


# ─── Backup & Restore Models ──────────────────────────────────────────

class BackupType(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"
    SNAPSHOT = "snapshot"

class RestoreVerdict(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    INTEGRITY_MISMATCH = "integrity_mismatch"

@dataclass
class BackupRecord:
    backup_id: str
    backup_type: BackupType
    source_name: str
    size_bytes: int
    checksum_sha256: str
    created_at: str
    retention_days: int = 90
    encrypted: bool = True
    kms_key_id: str = ""
    region: str = ""
    parent_backup_id: Optional[str] = None  # For incremental

@dataclass
class RestoreRequest:
    restore_id: str
    backup_id: str
    target_name: str
    point_in_time: Optional[str] = None  # ISO datetime for PITR
    isolated_environment: bool = True

@dataclass
class RestoreResult:
    restore_id: str
    verdict: RestoreVerdict
    restored_rows: int = 0
    elapsed_seconds: float = 0.0
    checksum_verified: bool = False
    integrity_errors: List[str] = field(default_factory=list)
    rto_met: bool = False
    rpo_met: bool = False
    actual_rto_seconds: float = 0.0
    actual_rpo_seconds: float = 0.0

@dataclass
class DrDrillResult:
    drill_id: str
    drill_type: str  # restore_drill, failover_drill, pitr_drill
    target_rto_seconds: float
    target_rpo_seconds: float
    actual_rto_seconds: float
    actual_rpo_seconds: float
    rto_met: bool
    rpo_met: bool
    passed: bool
    findings: List[str] = field(default_factory=list)



# ─── Error Budget Governance Models ───────────────────────────────────

class BurnRateWindow(str, Enum):
    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    ONE_DAY = "1d"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"

class ReleaseFreezeAction(str, Enum):
    FREEZE = "freeze"
    WARN = "warn"
    ALLOW = "allow"

@dataclass
class ErrorBudgetSlo:
    slo_id: str
    service_name: str
    indicator: str  # availability, latency_p99, error_rate
    target: float  # 99.9, 99.95, etc.
    window_days: int = 30
    budget_remaining_pct: float = 100.0
    consumed_budget_pct: float = 0.0

@dataclass
class BurnRateAlert:
    slo_id: str
    window: BurnRateWindow
    burn_rate: float  # >1.0 means burning faster than budget allows
    remaining_budget_pct: float
    alert_severity: str  # page, ticket, log
    projected_exhaustion_hours: float = 0.0

@dataclass
class ReleaseFreezeDecision:
    service_name: str
    action: ReleaseFreezeAction
    reason: str
    remaining_budget_pct: float
    override_allowed: bool = False
    waiver_id: Optional[str] = None

@dataclass
class ErrorBudgetWaiver:
    waiver_id: str
    service_name: str
    reason: str
    approved_by: str
    expires_at: str
    max_deploys: int = 1
    deploys_used: int = 0


# ─── Autoscaling & Capacity Control Models ────────────────────────────

class ScalingDirection(str, Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    NO_CHANGE = "no_change"

class ScalingTrigger(str, Enum):
    CPU_THRESHOLD = "cpu_threshold"
    MEMORY_THRESHOLD = "memory_threshold"
    QUEUE_DEPTH = "queue_depth"
    REQUEST_RATE = "request_rate"
    SCHEDULE = "schedule"
    MANUAL = "manual"

@dataclass
class ScalingPolicy:
    policy_id: str
    service_name: str
    trigger: ScalingTrigger
    threshold_value: float
    min_instances: int = 1
    max_instances: int = 100
    cooldown_seconds: float = 300.0
    scale_up_increment: int = 1
    scale_down_increment: int = 1

@dataclass
class ScalingDecision:
    decision_id: str
    service_name: str
    direction: ScalingDirection
    current_instances: int
    target_instances: int
    trigger: ScalingTrigger
    trigger_value: float
    policy_id: str
    timestamp: str = ""
    blocked: bool = False
    block_reason: str = ""

@dataclass
class AutoscalingCapacityPlan:
    plan_id: str
    service_name: str
    current_capacity: int
    projected_peak_load: float
    recommended_capacity: int
    headroom_pct: float = 20.0
    estimated_monthly_cost: float = 0.0

@dataclass
class FairSchedulingQuota:
    tenant_id: str
    service_name: str
    guaranteed_instances: int
    max_burst_instances: int
    current_usage: int = 0
    weight: float = 1.0

# ─── API Compatibility Gate Models ────────────────────────────────────

class ApiCompatChangeType(str, Enum):
    ENDPOINT_ADDED = "endpoint_added"
    ENDPOINT_REMOVED = "endpoint_removed"
    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_TYPE_CHANGED = "field_type_changed"
    REQUIRED_FIELD_ADDED = "required_field_added"
    ENUM_VALUE_ADDED = "enum_value_added"
    ENUM_VALUE_REMOVED = "enum_value_removed"
    RESPONSE_CODE_CHANGED = "response_code_changed"

class CompatibilityVerdict(str, Enum):
    COMPATIBLE = "compatible"
    BREAKING = "breaking"
    DEPRECATED = "deprecated"
    REQUIRES_MIGRATION = "requires_migration"

@dataclass
class ApiChange:
    change_id: str
    change_type: ApiCompatChangeType
    path: str  # /api/v2/users, field: user.email
    description: str
    verdict: CompatibilityVerdict
    migration_guide: str = ""

@dataclass
class SdkCompatibilityMatrix:
    sdk_name: str
    sdk_version: str
    api_versions_supported: List[str] = field(default_factory=list)
    deprecated_apis_used: List[str] = field(default_factory=list)
    breaking_changes_affected: List[str] = field(default_factory=list)

@dataclass
class EventSchemaChange:
    event_type: str
    field_path: str
    change: ApiCompatChangeType
    backward_compatible: bool
    forward_compatible: bool

@dataclass
class CompatibilityGateResult:
    gate_id: str
    passed: bool
    total_changes: int = 0
    breaking_changes: int = 0
    compatible_changes: int = 0
    deprecated_changes: int = 0
    blocking_changes: List[ApiChange] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ─── Compliance & Audit Evidence Models ───────────────────────────────

class ComplianceFramework(str, Enum):
    SOC2_TYPE2 = "soc2_type2"
    ISO27001 = "iso27001"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    GDPR = "gdpr"
    NIST_CSF = "nist_csf"
    FedRAMP = "fedramp"

class ControlStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    PLANNED = "planned"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"

@dataclass
class ComplianceControl:
    control_id: str
    framework: ComplianceFramework
    title: str
    description: str
    status: ControlStatus
    evidence_ids: List[str] = field(default_factory=list)
    owner: str = ""
    last_assessed: str = ""

@dataclass
class AuditEvidence:
    evidence_id: str
    control_id: str
    evidence_type: str  # screenshot, log, config, test_result, document
    description: str
    content_hash: str
    collected_at: str
    collector: str  # automated, manual
    retention_days: int = 365

@dataclass
class AuditFinding:
    finding_id: str
    control_id: str
    severity: str  # critical, high, medium, low, informational
    description: str
    remediation_plan: str = ""
    due_date: str = ""
    status: str = "open"  # open, in_progress, remediated, accepted_risk

@dataclass
class ComplianceReport:
    report_id: str
    framework: ComplianceFramework
    assessment_date: str
    total_controls: int = 0
    implemented: int = 0
    partially_implemented: int = 0
    failed: int = 0
    not_applicable: int = 0
    coverage_pct: float = 0.0
    findings: List[AuditFinding] = field(default_factory=list)

# ─── Isolated Trusted Builder Models ──────────────────────────────────

class BuildIsolationLevel(str, Enum):
    SHARED = "shared"
    TENANT_ISOLATED = "tenant_isolated"
    HERMETIC = "hermetic"
    AIR_GAPPED = "air_gapped"

class BuildVerdict(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    TAINTED = "tainted"  # build succeeded but integrity check failed
    TIMEOUT = "timeout"

class SlsaLevel(str, Enum):
    LEVEL_0 = "L0"  # no provenance
    LEVEL_1 = "L1"  # build exists
    LEVEL_2 = "L2"  # hosted build, signed provenance
    LEVEL_3 = "L3"  # hardened builds, non-falsifiable provenance
    LEVEL_4 = "L4"  # hermetic, reproducible builds

@dataclass
class BuildRequest:
    build_id: str
    source_repo: str
    source_commit: str
    builder_image: str
    isolation_level: BuildIsolationLevel
    tenant_id: str = ""
    timeout_seconds: int = 3600
    network_allowed: bool = False  # hermetic = no network
    env_vars: Dict[str, str] = field(default_factory=dict)

@dataclass
class BuildAttestation:
    build_id: str
    verdict: BuildVerdict
    artifact_digest: str = ""  # SHA-256 of produced artifact
    builder_digest: str = ""  # SHA-256 of builder image
    slsa_level: SlsaLevel = SlsaLevel.LEVEL_0
    reproducible: bool = False
    provenance_signed: bool = False
    started_at: str = ""
    completed_at: str = ""
    log_digest: str = ""  # SHA-256 of build log
    network_accessed: bool = False

@dataclass
class BuildPolicy:
    policy_id: str
    min_isolation: BuildIsolationLevel
    min_slsa_level: SlsaLevel
    require_reproducible: bool = False
    require_signed_provenance: bool = True
    allowed_builder_digests: List[str] = field(default_factory=list)
    max_build_duration_seconds: int = 7200

# ─── Agent Shadow/Canary Models ───────────────────────────────────────

class AgentDeploymentMode(str, Enum):
    PRODUCTION = "production"
    SHADOW = "shadow"
    CANARY = "canary"
    BLUE_GREEN = "blue_green"

class AgentComparisonVerdict(str, Enum):
    EQUIVALENT = "equivalent"
    DIVERGENT = "divergent"
    IMPROVED = "improved"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

@dataclass
class AgentDeployment:
    deployment_id: str
    agent_id: str
    agent_version: str
    mode: AgentDeploymentMode
    traffic_pct: float = 0.0  # 0-100
    started_at: str = ""
    is_active: bool = True
    model_id: str = ""
    tool_permissions: List[str] = field(default_factory=list)

@dataclass
class ShadowComparison:
    comparison_id: str
    production_deployment_id: str
    shadow_deployment_id: str
    request_count: int = 0
    match_count: int = 0
    divergence_count: int = 0
    avg_latency_diff_ms: float = 0.0
    verdict: AgentComparisonVerdict = AgentComparisonVerdict.UNKNOWN
    divergence_examples: List[str] = field(default_factory=list)

@dataclass
class CanaryMetrics:
    deployment_id: str
    success_rate: float = 0.0
    p50_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    error_count: int = 0
    total_requests: int = 0
    cost_per_request: float = 0.0

@dataclass
class CanaryPromotionDecision:
    deployment_id: str
    promote: bool
    reason: str
    metrics: Optional[CanaryMetrics] = None
    rollback_recommended: bool = False


# ─── Feature Flag Governance Models ───────────────────────────────────

class FlagState(str, Enum):
    DISABLED = "disabled"
    PERCENTAGE_ROLLOUT = "percentage_rollout"
    TENANT_TARGETED = "tenant_targeted"
    ENABLED = "enabled"
    KILL_SWITCHED = "kill_switched"

class FlagLifecycleStage(str, Enum):
    CREATED = "created"
    TESTING = "testing"
    ROLLING_OUT = "rolling_out"
    FULLY_ENABLED = "fully_enabled"
    STALE = "stale"
    RETIRED = "retired"

@dataclass
class FeatureFlag:
    flag_id: str
    name: str
    description: str
    state: FlagState = FlagState.DISABLED
    lifecycle: FlagLifecycleStage = FlagLifecycleStage.CREATED
    rollout_percentage: float = 0.0  # 0-100
    targeted_tenants: List[str] = field(default_factory=list)
    owner: str = ""
    created_at: str = ""
    stale_after_days: int = 90
    kill_switch_reason: str = ""
    dependencies: List[str] = field(default_factory=list)  # other flag_ids

@dataclass
class FlagEvaluation:
    flag_id: str
    tenant_id: str
    enabled: bool
    reason: str  # targeted, percentage, global, disabled, kill_switched
    evaluated_at: str = ""

@dataclass
class FlagAuditEntry:
    flag_id: str
    action: str  # created, updated, enabled, disabled, kill_switched, retired
    actor: str
    previous_state: str
    new_state: str
    timestamp: str = ""
    reason: str = ""

# ─── Portable Control Plane Models ────────────────────────────────────

class PortablePlaneType(str, Enum):
    CONTROL = "control"
    DATA = "data"
    MANAGEMENT = "management"
    OBSERVABILITY = "observability"

class DeploymentTopology(str, Enum):
    SINGLE_REGION = "single_region"
    MULTI_REGION = "multi_region"
    HYBRID = "hybrid"
    EDGE = "edge"
    AIR_GAPPED = "air_gapped"

class PlaneHealthState(str, Enum):
    RUNNING = "running"
    DEGRADED = "degraded"
    STARTING = "starting"
    STOPPED = "stopped"
    UNREACHABLE = "unreachable"

@dataclass
class ControlPlaneComponent:
    component_id: str
    plane_type: PortablePlaneType
    version: str
    topology: DeploymentTopology
    health: PlaneHealthState = PlaneHealthState.STOPPED
    region: str = ""
    endpoint_url: str = ""
    dependencies: List[str] = field(default_factory=list)
    resource_cpu_millicores: int = 500
    resource_memory_mb: int = 512

@dataclass
class TopologyValidation:
    topology: DeploymentTopology
    valid: bool
    missing_components: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    resource_total_cpu: int = 0
    resource_total_memory: int = 0

@dataclass
class PlaneGovernanceRule:
    rule_id: str
    plane_type: PortablePlaneType
    max_instances: int = 3
    min_instances: int = 1
    allowed_topologies: List[str] = field(default_factory=list)
    requires_encryption: bool = True
    requires_auth: bool = True

# ─── Multiregion Failover Models ──────────────────────────────────────

class FailoverMode(str, Enum):
    ACTIVE_PASSIVE = "active_passive"
    ACTIVE_ACTIVE = "active_active"
    PILOT_LIGHT = "pilot_light"
    WARM_STANDBY = "warm_standby"

class RegionHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    DRAINING = "draining"
    RECOVERING = "recovering"

class FailoverTrigger(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    SCHEDULED = "scheduled"
    DR_DRILL = "dr_drill"

@dataclass
class RegionConfig:
    region_id: str
    is_primary: bool
    failover_mode: FailoverMode
    health_status: RegionHealthStatus = RegionHealthStatus.HEALTHY
    traffic_weight: float = 0.0  # 0-100
    replication_lag_ms: float = 0.0
    last_health_check: str = ""
    data_residency_zone: str = ""

@dataclass
class FailoverEvent:
    event_id: str
    source_region: str
    target_region: str
    trigger: FailoverTrigger
    started_at: str
    completed_at: str = ""
    rto_seconds: float = 0.0
    rpo_data_loss_bytes: int = 0
    success: bool = False
    rollback_available: bool = True
    dns_propagation_complete: bool = False

@dataclass
class TrafficShift:
    shift_id: str
    from_region: str
    to_region: str
    percentage: float  # 0-100
    reason: str
    started_at: str
    completed: bool = False


# ─── Knowledge Marketplace Models ─────────────────────────────────────

class KnowledgeAssetType(str, Enum):
    PATTERN = "pattern"
    RECIPE = "recipe"
    RULE_PACK = "rule_pack"
    MIGRATION_MAP = "migration_map"
    BENCHMARK = "benchmark"
    CORPUS = "corpus"

class AssetQualityTier(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    CERTIFIED = "certified"
    DEPRECATED = "deprecated"

class SharingScope(str, Enum):
    PRIVATE = "private"
    TENANT = "tenant"
    ORGANIZATION = "organization"
    PUBLIC = "public"

@dataclass
class KnowledgeAsset:
    asset_id: str
    name: str
    asset_type: KnowledgeAssetType
    quality_tier: AssetQualityTier = AssetQualityTier.DRAFT
    sharing_scope: SharingScope = SharingScope.PRIVATE
    owner_tenant_id: str = ""
    version: str = "1.0.0"
    description: str = ""
    usage_count: int = 0
    rating: float = 0.0  # 0-5
    rating_count: int = 0
    created_at: str = ""
    tags: List[str] = field(default_factory=list)
    content_digest: str = ""
    license: str = "proprietary"

@dataclass
class AssetReview:
    review_id: str
    asset_id: str
    reviewer_id: str
    rating: float  # 1-5
    comment: str
    approved: bool = False
    timestamp: str = ""

@dataclass
class AssetUsageRecord:
    asset_id: str
    tenant_id: str
    used_at: str
    success: bool = True
    feedback: str = ""

# ─── Change Management Models ─────────────────────────────────────────

class ChangeRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ChangeStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class FreezeScope(str, Enum):
    GLOBAL = "global"
    REGION = "region"
    SERVICE = "service"
    TENANT = "tenant"

@dataclass
class ChangeRequest:
    change_id: str
    title: str
    description: str
    service_name: str
    risk_level: ChangeRiskLevel
    status: ChangeStatus = ChangeStatus.DRAFT
    requester: str = ""
    approver: str = ""
    scheduled_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    rollback_plan: str = ""
    impact_services: List[str] = field(default_factory=list)
    region: str = ""

@dataclass
class ChangeFreezeWindow:
    freeze_id: str
    reason: str
    scope: FreezeScope
    scope_value: str = ""  # region name, service name, etc.
    starts_at: str = ""
    ends_at: str = ""
    is_active: bool = True
    exceptions: List[str] = field(default_factory=list)  # change_ids exempt
    created_by: str = ""

@dataclass
class ChangeAuditEntry:
    change_id: str
    action: str
    actor: str
    timestamp: str = ""
    details: str = ""

# ─── Release Channel Governance Models ────────────────────────────────

class ChannelStability(str, Enum):
    NIGHTLY = "nightly"
    ALPHA = "alpha"
    BETA = "beta"
    RC = "rc"
    STABLE = "stable"
    LTS = "lts"

class PromotionVerdict(str, Enum):
    APPROVED = "approved"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"
    ROLLED_BACK = "rolled_back"

@dataclass
class ChannelReleaseCandidate:
    rc_id: str
    version: str
    channel: ChannelStability
    artifact_digest: str
    created_at: str
    promoted_at: str = ""
    promoted_to: str = ""  # target channel
    test_pass_rate: float = 0.0
    security_scan_clean: bool = False
    breaking_changes: List[str] = field(default_factory=list)
    rollback_version: str = ""

@dataclass
class ChannelPolicy:
    channel: ChannelStability
    min_test_pass_rate: float = 95.0
    require_security_scan: bool = True
    require_zero_breaking_changes: bool = False
    min_soak_hours: int = 0
    max_rollback_window_hours: int = 72
    auto_promote: bool = False

@dataclass
class PromotionRecord:
    promotion_id: str
    rc_id: str
    from_channel: ChannelStability
    to_channel: ChannelStability
    verdict: PromotionVerdict
    reason: str
    actor: str
    timestamp: str = ""

# ─── Model/Agent Economics Models ─────────────────────────────────────

class ModelProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"
    SELF_HOSTED = "self_hosted"

class AgentCostType(str, Enum):
    MODEL_INFERENCE = "model_inference"
    TOOL_EXECUTION = "tool_execution"
    HUMAN_REVIEW = "human_review"
    STORAGE = "storage"
    COMPUTE = "compute"
    EGRESS = "egress"

@dataclass
class ModelPricing:
    model_id: str
    provider: ModelProvider
    input_cost_per_1k_tokens: float
    output_cost_per_1k_tokens: float
    context_window: int = 128000
    max_output_tokens: int = 4096
    cached_input_discount_pct: float = 0.0

@dataclass
class AgentInvocation:
    invocation_id: str
    agent_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    tool_calls: int = 0
    tool_cost: float = 0.0
    human_review_cost: float = 0.0
    duration_seconds: float = 0.0
    success: bool = True
    tenant_id: str = ""
    timestamp: str = ""

@dataclass
class AgentROI:
    agent_id: str
    total_cost: float
    total_value_generated: float  # estimated value of successful outputs
    roi_percentage: float = 0.0
    break_even_invocations: int = 0
    cost_per_success: float = 0.0
    invocation_count: int = 0
    success_count: int = 0

@dataclass
class CostForecast:
    agent_id: str
    period_days: int
    projected_invocations: int
    projected_cost: float
    projected_value: float
    confidence_level: float = 0.0

# ─── Database Expand-Contract Models ──────────────────────────────────

class DbMigrationPhase(str, Enum):
    PENDING = "pending"
    EXPAND = "expand"  # Add new columns/tables (backward compatible)
    MIGRATE = "migrate"  # Copy data from old to new
    CONTRACT = "contract"  # Remove old columns/tables
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"

class SchemaChangeType(str, Enum):
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    ADD_TABLE = "add_table"
    DROP_TABLE = "drop_table"
    RENAME_COLUMN = "rename_column"
    ALTER_TYPE = "alter_type"
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"
    ADD_CONSTRAINT = "add_constraint"
    DROP_CONSTRAINT = "drop_constraint"

@dataclass
class SchemaChange:
    change_id: str
    change_type: SchemaChangeType
    table_name: str
    column_name: str = ""
    new_column_name: str = ""  # for renames
    data_type: str = ""
    nullable: bool = True
    default_value: str = ""
    backward_compatible: bool = True

@dataclass
class ExpandContractPlan:
    plan_id: str
    description: str
    phase: DbMigrationPhase = DbMigrationPhase.PENDING
    expand_changes: List[SchemaChange] = field(default_factory=list)
    contract_changes: List[SchemaChange] = field(default_factory=list)
    data_migration_queries: List[str] = field(default_factory=list)
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    rows_migrated: int = 0
    rollback_plan: List[str] = field(default_factory=list)

@dataclass
class SchemaValidation:
    plan_id: str
    valid: bool
    breaking_changes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    estimated_downtime_seconds: int = 0

# ─── Design Partner Validation Models ─────────────────────────────────

class PartnerEngagementStatus(str, Enum):
    PROSPECT = "prospect"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    FEEDBACK = "feedback"
    GRADUATED = "graduated"
    CHURNED = "churned"

class ValidationOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    DEFERRED = "deferred"

@dataclass
class DesignPartner:
    partner_id: str
    company_name: str
    contact_name: str
    industry: str
    engagement_status: PartnerEngagementStatus = PartnerEngagementStatus.PROSPECT
    use_case: str = ""
    repository_url: str = ""
    started_at: str = ""
    nps_score: int = 0  # -100 to 100
    features_requested: List[str] = field(default_factory=list)
    features_validated: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)

@dataclass
class ValidationScenario:
    scenario_id: str
    partner_id: str
    feature: str
    description: str
    outcome: ValidationOutcome = ValidationOutcome.DEFERRED
    feedback: str = ""
    time_to_complete_hours: float = 0.0
    validated_at: str = ""

@dataclass
class PartnerReport:
    total_partners: int = 0
    active_count: int = 0
    graduated_count: int = 0
    average_nps: float = 0.0
    top_requested_features: List[Dict[str, int]] = field(default_factory=list)
    validation_pass_rate: float = 0.0
    blockers: List[str] = field(default_factory=list)

# ─── Air-Gap Bundle Models ────────────────────────────────────────────

class BundleStatus(str, Enum):
    BUILDING = "building"
    READY = "ready"
    SIGNED = "signed"
    DEPLOYED = "deployed"
    EXPIRED = "expired"
    REVOKED = "revoked"

class BundleComponentType(str, Enum):
    CONTAINER_IMAGE = "container_image"
    HELM_CHART = "helm_chart"
    CONFIG_MAP = "config_map"
    DATABASE_MIGRATION = "database_migration"
    BINARY = "binary"
    CERTIFICATE = "certificate"
    LICENSE = "license"

@dataclass
class BundleComponent:
    component_id: str
    component_type: BundleComponentType
    name: str
    version: str
    size_bytes: int = 0
    checksum_sha256: str = ""
    signed: bool = False
    signature: str = ""

@dataclass
class AirgapBundle:
    bundle_id: str
    target_version: str
    target_edition: str
    status: BundleStatus = BundleStatus.BUILDING
    components: List[BundleComponent] = field(default_factory=list)
    total_size_bytes: int = 0
    created_at: str = ""
    signed_at: str = ""
    deployed_at: str = ""
    manifest_digest: str = ""
    signing_key_id: str = ""
    expiry_date: str = ""
    upgrade_from_version: str = ""

@dataclass
class BundleVerification:
    bundle_id: str
    all_components_present: bool = False
    all_checksums_valid: bool = False
    signature_valid: bool = False
    not_expired: bool = False
    overall_valid: bool = False
    errors: List[str] = field(default_factory=list)


# ─── Service Catalog SLO Models ───────────────────────────────────────

class ServiceTier(str, Enum):
    TIER_0 = "tier_0"  # Business critical
    TIER_1 = "tier_1"  # Customer facing
    TIER_2 = "tier_2"  # Internal
    TIER_3 = "tier_3"  # Best effort

class SliType(str, Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    SATURATION = "saturation"

@dataclass
class ServiceEntry:
    service_id: str
    name: str
    tier: ServiceTier
    owner_team: str
    description: str = ""
    repository: str = ""
    dependencies: List[str] = field(default_factory=list)  # service_ids
    oncall_schedule_id: str = ""
    runbook_url: str = ""
    created_at: str = ""

@dataclass
class SliDefinition:
    sli_id: str
    service_id: str
    sli_type: SliType
    measurement_query: str = ""  # how to measure
    good_event_query: str = ""
    total_event_query: str = ""

@dataclass
class SloTarget:
    slo_id: str
    sli_id: str
    service_id: str
    target_percentage: float  # 99.9, 99.95, etc.
    window_days: int = 30
    burn_rate_threshold: float = 1.0
    alerting_enabled: bool = True

@dataclass
class SloMeasurement:
    slo_id: str
    good_events: int
    total_events: int
    measured_at: str
    measured_percentage: float = 0.0
    budget_remaining_pct: float = 100.0

# ─── Residual Risk Register Models ────────────────────────────────────

class RiskSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

class RiskTreatment(str, Enum):
    MITIGATE = "mitigate"
    ACCEPT = "accept"
    TRANSFER = "transfer"
    AVOID = "avoid"

class RiskStatus(str, Enum):
    OPEN = "open"
    MITIGATING = "mitigating"
    ACCEPTED = "accepted"
    CLOSED = "closed"
    ESCALATED = "escalated"

@dataclass
class ResidualRiskEntry:
    risk_id: str
    title: str
    description: str
    category: str  # security, reliability, performance, compliance, data
    severity: RiskSeverity
    likelihood: float  # 0.0-1.0
    impact_score: float  # 0.0-10.0
    risk_score: float = 0.0  # likelihood * impact
    treatment: RiskTreatment = RiskTreatment.MITIGATE
    status: RiskStatus = RiskStatus.OPEN
    owner: str = ""
    mitigation_plan: str = ""
    acceptance_justification: str = ""
    accepted_by: str = ""
    review_date: str = ""
    created_at: str = ""
    related_findings: List[str] = field(default_factory=list)

@dataclass
class RiskAssessment:
    assessment_id: str
    assessed_at: str
    total_risks: int = 0
    critical_count: int = 0
    high_count: int = 0
    accepted_count: int = 0
    overall_risk_score: float = 0.0
    release_recommended: bool = False
    blockers: List[str] = field(default_factory=list)

@dataclass
class RiskWaiver:
    waiver_id: str
    risk_id: str
    approved_by: str
    reason: str
    expires_at: str
    conditions: List[str] = field(default_factory=list)

# ─── On-Call Rotation Models ──────────────────────────────────────────

class OncallShiftType(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ESCALATION = "escalation"
    SHADOW = "shadow"  # training

@dataclass
class OncallEngineer:
    engineer_id: str
    name: str
    timezone: str  # e.g. "UTC+8", "UTC-5"
    region: str
    skills: List[str] = field(default_factory=list)
    max_consecutive_shifts: int = 7
    current_consecutive: int = 0
    total_shifts: int = 0
    available: bool = True

@dataclass
class OncallShift:
    shift_id: str
    engineer_id: str
    shift_type: OncallShiftType
    service_name: str
    starts_at: str
    ends_at: str
    handoff_notes: str = ""
    incidents_handled: int = 0
    acknowledged: bool = False

@dataclass
class OncallSchedule:
    schedule_id: str
    service_name: str
    rotation_period_hours: int = 12  # follow-the-sun
    shifts: List[OncallShift] = field(default_factory=list)
    regions: List[str] = field(default_factory=list)
    created_at: str = ""

@dataclass
class OncallOverride:
    override_id: str
    original_engineer_id: str
    replacement_engineer_id: str
    service_name: str
    starts_at: str
    ends_at: str
    reason: str = ""

# ─── Multi-Agent Consensus Models ─────────────────────────────────────

class ConsensusStrategy(str, Enum):
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"
    WEIGHTED = "weighted"
    QUORUM = "quorum"
    ARBITER = "arbiter"

class VoteValue(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"

class ProposalStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ARBITRATED = "arbitrated"

@dataclass
class ConsensusAgent:
    agent_id: str
    name: str
    weight: float = 1.0  # for weighted voting
    trust_score: float = 1.0  # 0-1
    specialization: str = ""
    vote_count: int = 0
    correct_predictions: int = 0

@dataclass
class ConsensusProposal:
    proposal_id: str
    topic: str
    description: str
    strategy: ConsensusStrategy
    proposer_id: str
    status: ProposalStatus = ProposalStatus.OPEN
    quorum_threshold: float = 0.5  # for quorum strategy
    deadline: str = ""
    created_at: str = ""
    resolved_at: str = ""
    arbiter_id: str = ""  # for arbiter strategy

@dataclass
class AgentVote:
    vote_id: str
    proposal_id: str
    agent_id: str
    value: VoteValue
    confidence: float = 1.0  # 0-1
    reasoning: str = ""
    timestamp: str = ""

@dataclass
class ConsensusResult:
    proposal_id: str
    outcome: VoteValue  # APPROVE or REJECT
    approve_count: int = 0
    reject_count: int = 0
    abstain_count: int = 0
    weighted_approve: float = 0.0
    weighted_reject: float = 0.0
    strategy_used: ConsensusStrategy = ConsensusStrategy.MAJORITY
    decided_by: str = ""  # agent_id if arbiter

# ─── Tenant Edition Migration Models ─────────────────────────────────

class TenantMigrationStatus(str, Enum):
    PLANNED = "planned"
    VALIDATING = "validating"
    MIGRATING = "migrating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"

@dataclass
class TenantEditionMapping:
    mapping_id: str
    tenant_id: str
    source_edition: str
    target_edition: str
    status: TenantMigrationStatus = TenantMigrationStatus.PLANNED
    data_size_gb: float = 0.0
    feature_gaps: List[str] = field(default_factory=list)
    config_changes: Dict[str, str] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    rollback_deadline: str = ""
    validation_passed: bool = False

@dataclass
class MigrationPrecheck:
    mapping_id: str
    edition_compatible: bool = False
    data_exportable: bool = False
    features_available: bool = False
    capacity_sufficient: bool = False
    overall_ready: bool = False
    blockers: List[str] = field(default_factory=list)

@dataclass
class MigrationWave:
    wave_id: str
    wave_name: str
    mappings: List[str] = field(default_factory=list)  # mapping_ids
    max_parallel: int = 5
    started_at: str = ""
    completed_at: str = ""

# ─── Workflow Version Recovery Models ─────────────────────────────────

class WorkflowState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"
    CANCELLED = "cancelled"

class CheckpointType(str, Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    PRE_UPGRADE = "pre_upgrade"
    POST_ROLLBACK = "post_rollback"

@dataclass
class WorkflowCheckpoint:
    checkpoint_id: str
    workflow_id: str
    step_index: int
    checkpoint_type: CheckpointType
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    version: str = ""
    checksum: str = ""

@dataclass
class WorkflowExecution:
    workflow_id: str
    workflow_name: str
    version: str
    state: WorkflowState = WorkflowState.PENDING
    current_step: int = 0
    total_steps: int = 0
    started_at: str = ""
    completed_at: str = ""
    checkpoints: List[str] = field(default_factory=list)  # checkpoint_ids
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3
    idempotency_key: str = ""

@dataclass
class RecoveryPlan:
    workflow_id: str
    from_checkpoint_id: str
    resume_step: int
    version_compatible: bool = True
    migration_needed: bool = False
    estimated_steps_remaining: int = 0

# ─── DAST/IAST Security Models ────────────────────────────────────────

class SecurityScanType(str, Enum):
    DAST = "dast"
    IAST = "iast"
    SAST = "sast"
    SCA = "sca"
    CONTAINER = "container"

class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class FindingStatus(str, Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    REMEDIATED = "remediated"
    ACCEPTED_RISK = "accepted_risk"
    REOPENED = "reopened"

@dataclass
class SecurityScan:
    scan_id: str
    scan_type: SecurityScanType
    target: str  # URL, image, or repo path
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    findings_count: int = 0
    scanner_name: str = ""
    scanner_version: str = ""
    policy_id: str = ""

@dataclass
class SecurityFinding:
    finding_id: str
    scan_id: str
    severity: FindingSeverity
    status: FindingStatus = FindingStatus.NEW
    title: str = ""
    description: str = ""
    location: str = ""  # file:line or URL
    cwe_id: str = ""  # CWE-79, etc.
    cvss_score: float = 0.0
    remediation: str = ""
    first_seen: str = ""
    last_seen: str = ""
    false_positive_reason: str = ""
    sla_deadline: str = ""

@dataclass
class SecurityPolicy:
    policy_id: str
    name: str
    max_critical: int = 0  # 0 = no critical allowed
    max_high: int = 0
    sla_critical_hours: int = 24
    sla_high_hours: int = 72
    sla_medium_hours: int = 168
    block_on_critical: bool = True
    require_scan_types: List[str] = field(default_factory=list)
# ─── Customer ROI/TCO Models ──────────────────────────────────────────

class CostDriver(str, Enum):
    LABOR = "labor"
    INFRASTRUCTURE = "infrastructure"
    LICENSE = "license"
    TRAINING = "training"
    MIGRATION = "migration"
    MAINTENANCE = "maintenance"
    DOWNTIME = "downtime"
    OPPORTUNITY = "opportunity"

class ValueDriver(str, Enum):
    PRODUCTIVITY = "productivity"
    QUALITY = "quality"
    SPEED = "speed"
    RISK_REDUCTION = "risk_reduction"
    COMPLIANCE = "compliance"
    INNOVATION = "innovation"

@dataclass
class TcoCostItem:
    item_id: str
    driver: CostDriver
    description: str
    amount: float
    recurring: bool = True  # True = annual, False = one-time
    period_years: int = 3

@dataclass
class ValueItem:
    item_id: str
    driver: ValueDriver
    description: str
    annual_value: float
    confidence: float = 0.8  # 0-1
    realization_month: int = 6  # months until value realized

@dataclass
class RoiAnalysis:
    analysis_id: str
    customer_name: str
    period_years: int = 3
    total_cost: float = 0.0
    total_value: float = 0.0
    net_value: float = 0.0
    roi_percentage: float = 0.0
    payback_months: float = 0.0
    npv: float = 0.0  # net present value
    irr: float = 0.0  # internal rate of return
    risk_adjusted_roi: float = 0.0
    created_at: str = ""

@dataclass
class TcoComparison:
    current_state: str  # "manual", "competitor", etc.
    proposed_state: str  # "elmos"
    current_tco: float = 0.0
    proposed_tco: float = 0.0
    savings: float = 0.0
    savings_percentage: float = 0.0

# ─── Problem Root Cause Models ──────────────────────────────────────

class ProblemStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    ROOT_CAUSE_IDENTIFIED = "root_cause_identified"
    FIX_IN_PROGRESS = "fix_in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

class ProblemPriority(str, Enum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"

@dataclass
class ProblemRecord:
    problem_id: str
    title: str
    description: str
    priority: ProblemPriority
    status: ProblemStatus = ProblemStatus.OPEN
    affected_services: List[str] = field(default_factory=list)
    related_incidents: List[str] = field(default_factory=list)
    root_cause: str = ""
    fix_description: str = ""
    owner: str = ""
    created_at: str = ""
    resolved_at: str = ""
    recurrence_count: int = 0

@dataclass
class RcaFinding:
    finding_id: str
    problem_id: str
    category: str  # human, process, technology, external
    description: str
    evidence: List[str] = field(default_factory=list)
    contributing_factor: bool = False
    root_cause: bool = False

@dataclass
class CorrectiveAction:
    action_id: str
    problem_id: str
    description: str
    owner: str
    deadline: str = ""
    completed: bool = False
    verified: bool = False
    effectiveness_score: float = 0.0  # 0-1

# ─── Agent Budget & Resource Limits Models ──────────────────────────

class ResourceType(str, Enum):
    TOKENS = "tokens"
    API_CALLS = "api_calls"
    COMPUTE_SECONDS = "compute_seconds"
    STORAGE_BYTES = "storage_bytes"
    TOOL_INVOCATIONS = "tool_invocations"

class BudgetPeriod(str, Enum):
    PER_REQUEST = "per_request"
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"

class BudgetAction(str, Enum):
    ALLOW = "allow"
    THROTTLE = "throttle"
    DENY = "deny"
    ALERT = "alert"

@dataclass
class AgentBudget:
    budget_id: str
    agent_id: str
    resource_type: ResourceType
    period: BudgetPeriod
    limit: float
    used: float = 0.0
    remaining: float = 0.0
    warning_threshold_pct: float = 80.0
    hard_limit: bool = True
    created_at: str = ""
    reset_at: str = ""

@dataclass
class ResourceConsumption:
    consumption_id: str
    agent_id: str
    resource_type: ResourceType
    amount: float
    task_id: str = ""
    timestamp: str = ""

@dataclass
class BudgetDecision:
    agent_id: str
    resource_type: ResourceType
    requested: float
    action: BudgetAction
    remaining_after: float = 0.0
    reason: str = ""

# ─── Pattern & Antipattern Models ───────────────────────────────────

class PatternType(str, Enum):
    DESIGN = "design"
    ARCHITECTURE = "architecture"
    CODE = "code"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    DATA = "data"

class PatternConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    EXPERIMENTAL = "experimental"

@dataclass
class PatternRecord:
    pattern_id: str
    name: str
    pattern_type: PatternType
    description: str
    is_antipattern: bool = False
    confidence: PatternConfidence = PatternConfidence.MEDIUM
    occurrences: int = 0
    tags: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    example_code: str = ""
    fix_suggestion: str = ""  # for antipatterns
    first_seen: str = ""
    last_seen: str = ""
    source_repos: List[str] = field(default_factory=list)

@dataclass
class PatternMatch:
    match_id: str
    pattern_id: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    snippet: str = ""
    confidence_score: float = 0.0
    repo_name: str = ""

@dataclass
class PatternRule:
    rule_id: str
    pattern_id: str
    detector_type: str = ""  # regex, ast, semantic
    detector_config: str = ""
    enabled: bool = True
    severity: str = "info"  # error, warning, info


# ─── SBOM & Vulnerability Models ────────────────────────────────────

class SbomFormat(str, Enum):
    SPDX = "spdx"
    CYCLONEDX = "cyclonedx"
    SWID = "swid"

class VulnStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PATCHED = "patched"
    MITIGATED = "mitigated"
    WONT_FIX = "wont_fix"
    FALSE_POSITIVE = "false_positive"

class SbomVexJustification(str, Enum):
    COMPONENT_NOT_PRESENT = "component_not_present"
    VULNERABLE_CODE_NOT_PRESENT = "vulnerable_code_not_present"
    VULNERABLE_CODE_NOT_IN_EXECUTE_PATH = "vulnerable_code_not_in_execute_path"
    VULNERABLE_CODE_CANNOT_BE_CONTROLLED = "vulnerable_code_cannot_be_controlled"
    INLINE_MITIGATIONS_ALREADY_EXIST = "inline_mitigations_already_exist"

@dataclass
class SbomPackageComponent:
    purl: str  # pkg:npm/express@4.18.2
    name: str
    version: str
    license_id: str = ""
    direct: bool = True
    checksum_sha256: str = ""

@dataclass
class SbomDocument:
    sbom_id: str
    format: SbomFormat
    artifact_name: str
    artifact_version: str
    components: List[str] = field(default_factory=list)  # purls
    created_at: str = ""
    tool_name: str = ""
    tool_version: str = ""

@dataclass
class VulnerabilityRecord:
    vuln_id: str  # CVE-2024-XXXX
    affected_purl: str
    severity: str = ""  # critical, high, medium, low
    cvss_score: float = 0.0
    status: VulnStatus = VulnStatus.OPEN
    fixed_version: str = ""
    patch_available: bool = False
    exploitability: str = ""  # active, proof_of_concept, unproven
    first_detected: str = ""
    sla_deadline: str = ""
@dataclass
class SbomVexStatement:
    vex_id: str
    vuln_id: str
    status: VulnStatus
    justification: Optional[SbomVexJustification] = None
    impact_statement: str = ""
    action_statement: str = ""
    created_at: str = ""


# ─── Zero Downtime Upgrade Models ───────────────────────────────────

class ZDUpgradeStrategy(str, Enum):
    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    IN_PLACE = "in_place"

class ZDUpgradePhase(str, Enum):
    PLANNING = "planning"
    PRE_CHECK = "pre_check"
    DEPLOYING = "deploying"
    VERIFYING = "verifying"
    DRAINING = "draining"
    SWITCHING = "switching"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"

@dataclass
class UpgradeTarget:
    target_id: str
    service_name: str
    current_version: str
    target_version: str
    strategy: ZDUpgradeStrategy
    phase: ZDUpgradePhase = ZDUpgradePhase.PLANNING
    instances_total: int = 1
    instances_upgraded: int = 0
    health_check_url: str = ""
    drain_timeout_seconds: int = 30
    max_unavailable_pct: float = 25.0
    started_at: str = ""
    completed_at: str = ""
    error_message: str = ""

@dataclass
class UpgradeHealthCheck:
    target_id: str
    instance_id: str
    healthy: bool
    response_time_ms: float = 0.0
    error_rate_pct: float = 0.0
    checked_at: str = ""

# ─── Migration Risk Prediction Models ────────────────────────────────

class MigrationRiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"

class MigrationRiskCategory(str, Enum):
    DATA_LOSS = "data_loss"
    DOWNTIME = "downtime"
    PERFORMANCE = "performance"
    COMPATIBILITY = "compatibility"
    SECURITY = "security"
    COST_OVERRUN = "cost_overrun"
    SCHEDULE = "schedule"
    SKILL_GAP = "skill_gap"

@dataclass
class MigrationRiskFactor:
    factor_id: str
    category: MigrationRiskCategory
    description: str
    likelihood: float = 0.5  # 0-1
    impact: float = 0.5  # 0-1
    risk_score: float = 0.0  # likelihood * impact
    mitigation: str = ""
    mitigated: bool = False
    data_points: int = 0  # historical observations supporting this

@dataclass 
class MigrationProject:
    project_id: str
    name: str
    source_system: str
    target_system: str
    data_size_gb: float = 0.0
    complexity_score: float = 0.0  # 0-10
    team_experience_score: float = 0.0  # 0-10
    overall_risk_level: MigrationRiskLevel = MigrationRiskLevel.MEDIUM
    overall_risk_score: float = 0.0
    estimated_duration_days: int = 0
    actual_duration_days: int = 0
    succeeded: Optional[bool] = None

@dataclass
class RiskPrediction:
    project_id: str
    predicted_risk_level: MigrationRiskLevel
    confidence: float = 0.0  # 0-1
    predicted_success_probability: float = 0.0
    top_risk_factors: List[str] = field(default_factory=list)
    recommended_mitigations: List[str] = field(default_factory=list)


# ─── Deprecation & Removal Lifecycle Models ──────────────────────────

class DeprecationPhase(str, Enum):
    ANNOUNCED = "announced"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    REMOVED = "removed"

@dataclass
class DeprecatedItem:
    item_id: str
    name: str
    item_type: str  # api, feature, config, dependency
    phase: DeprecationPhase = DeprecationPhase.ANNOUNCED
    replacement: str = ""
    announced_at: str = ""
    deprecated_at: str = ""
    sunset_at: str = ""  # planned removal date
    removed_at: str = ""
    migration_guide_url: str = ""
    affected_consumers: List[str] = field(default_factory=list)
    usage_count: int = 0

@dataclass
class DeprecationPolicy:
    policy_id: str
    min_notice_days: int = 90
    max_sunset_days: int = 365
    require_replacement: bool = True
    require_migration_guide: bool = True
    block_removal_with_active_consumers: bool = True



# ─── Deployment Matrix Certification Models ──────────────────────────

class DeploymentEnvironment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"
    DR = "dr"
    EDGE = "edge"

class CertificationStatus(str, Enum):
    NOT_TESTED = "not_tested"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"

@dataclass
class DeploymentCell:
    cell_id: str
    environment: DeploymentEnvironment
    platform: str  # kubernetes, ecs, vm, bare_metal
    region: str
    version: str
    status: CertificationStatus = CertificationStatus.NOT_TESTED
    test_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    last_tested: str = ""
    certified_by: str = ""
    waiver_reason: str = ""

@dataclass
class DeploymentMatrix:
    matrix_id: str
    product_name: str
    version: str
    cells: List[str] = field(default_factory=list)  # cell_ids
    required_environments: List[str] = field(default_factory=list)
    required_platforms: List[str] = field(default_factory=list)
    overall_status: CertificationStatus = CertificationStatus.NOT_TESTED
    coverage_pct: float = 0.0
    created_at: str = ""

@dataclass
class MatrixTestResult:
    result_id: str
    cell_id: str
    test_name: str
    passed: bool
    duration_seconds: float = 0.0
    error_message: str = ""
    timestamp: str = ""

# ─── Container Scanning Models ───────────────────────────────────────

class ContainerScanStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"

class ContainerFindingType(str, Enum):
    OS_VULNERABILITY = "os_vulnerability"
    APP_VULNERABILITY = "app_vulnerability"
    MISCONFIG = "misconfig"
    SECRET = "secret"
    LICENSE = "license"
    MALWARE = "malware"

@dataclass
class ContainerImage:
    image_id: str
    registry: str
    repository: str
    tag: str
    digest_sha256: str
    size_mb: float = 0.0
    os_family: str = ""
    created_at: str = ""
    layers_count: int = 0

@dataclass
class ContainerScanResult:
    scan_id: str
    image_id: str
    status: ContainerScanStatus = ContainerScanStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    misconfig_count: int = 0
    secret_count: int = 0
    passed_policy: bool = False

@dataclass
class ContainerFinding:
    finding_id: str
    scan_id: str
    finding_type: ContainerFindingType
    severity: str = ""  # critical, high, medium, low
    package_name: str = ""
    installed_version: str = ""
    fixed_version: str = ""
    cve_id: str = ""
    title: str = ""
    description: str = ""
    layer_index: int = 0

@dataclass
class ContainerPolicy:
    policy_id: str
    name: str
    max_critical: int = 0
    max_high: int = 5
    block_secrets: bool = True
    block_malware: bool = True
    allowed_registries: List[str] = field(default_factory=list)
    required_labels: List[str] = field(default_factory=list)

# ─── Deterministic Execution Models ──────────────────────────────────

class ExecutionMode(str, Enum):
    DETERMINISTIC = "deterministic"
    BEST_EFFORT = "best_effort"
    REPLAY = "replay"

class StepOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    RETRIED = "retried"

@dataclass
class ExecutionStep:
    step_id: str
    execution_id: str
    step_index: int
    action: str
    input_hash: str = ""
    output_hash: str = ""
    outcome: StepOutcome = StepOutcome.SUCCESS
    duration_ms: float = 0.0
    deterministic: bool = True
    timestamp: str = ""
    retry_count: int = 0

@dataclass
class DeterministicExecution:
    execution_id: str
    agent_id: str
    mode: ExecutionMode = ExecutionMode.DETERMINISTIC
    seed: int = 42
    total_steps: int = 0
    completed_steps: int = 0
    determinism_score: float = 1.0  # 0-1, fraction of steps that are deterministic
    started_at: str = ""
    completed_at: str = ""
    replay_source_id: str = ""  # for REPLAY mode

@dataclass
class ReplayVerification:
    execution_id: str
    replay_id: str
    steps_matched: int = 0
    steps_diverged: int = 0
    divergence_points: List[int] = field(default_factory=list)  # step indices
    fully_deterministic: bool = False

# ─── Rolling Mixed Version Models ──────────────────────────────────

class MixedVersionState(str, Enum):
    HOMOGENEOUS = "homogeneous"
    MIXED = "mixed"
    ROLLING = "rolling"
    PAUSED = "paused"
    ROLLBACK = "rollback"
    COMPLETED = "completed"

@dataclass
class ClusterNode:
    node_id: str
    cluster_id: str
    current_version: str
    target_version: str = ""
    healthy: bool = True
    upgraded: bool = False
    upgraded_at: str = ""
    drain_status: str = ""  # draining, drained, active

@dataclass
class MixedVersionCluster:
    cluster_id: str
    name: str
    state: MixedVersionState = MixedVersionState.HOMOGENEOUS
    source_version: str = ""
    target_version: str = ""
    total_nodes: int = 0
    upgraded_nodes: int = 0
    max_unavailable: int = 1
    max_surge: int = 0
    compatibility_verified: bool = False
    started_at: str = ""
    completed_at: str = ""

@dataclass
class VersionCompatibilityCheck:
    check_id: str
    cluster_id: str
    source_version: str
    target_version: str
    api_compatible: bool = False
    schema_compatible: bool = False
    wire_compatible: bool = False
    overall_compatible: bool = False
    issues: List[str] = field(default_factory=list)

# ─── Functional Depth Certification Models ──────────────────────────

class FunctionalArea(str, Enum):
    DATA_INGESTION = "data_ingestion"
    TRANSFORMATION = "transformation"
    VALIDATION = "validation"
    ROUTING = "routing"
    STORAGE = "storage"
    QUERYING = "querying"
    REPORTING = "reporting"
    NOTIFICATION = "notification"

class DepthLevel(str, Enum):
    BASIC = "basic"      # Happy path only
    STANDARD = "standard" # + error handling + edge cases
    ADVANCED = "advanced"  # + performance + concurrency
    COMPLETE = "complete"  # + fault tolerance + recovery

@dataclass
class FunctionalRequirement:
    req_id: str
    area: FunctionalArea
    description: str
    depth: DepthLevel = DepthLevel.BASIC
    test_count: int = 0
    pass_count: int = 0
    implemented: bool = False
    certified: bool = False

@dataclass
class DepthCertification:
    cert_id: str
    product_name: str
    area: FunctionalArea
    target_depth: DepthLevel
    achieved_depth: DepthLevel = DepthLevel.BASIC
    requirements_total: int = 0
    requirements_met: int = 0
    coverage_pct: float = 0.0
    certified: bool = False
    certified_at: str = ""
    certifier: str = ""

@dataclass
class DepthGap:
    area: FunctionalArea
    target_depth: DepthLevel
    current_depth: DepthLevel
    missing_requirements: List[str] = field(default_factory=list)
    effort_estimate_hours: float = 0.0

# ─── Agent Eval Benchmark Models ────────────────────────────────────

class BenchmarkDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"

class EvalMetricType(str, Enum):
    ACCURACY = "accuracy"
    LATENCY = "latency"
    COST = "cost"
    SAFETY = "safety"
    TOOL_USE = "tool_use"
    REASONING = "reasoning"

@dataclass
class BenchmarkTask:
    task_id: str
    name: str
    difficulty: BenchmarkDifficulty
    category: str  # coding, research, debugging, planning
    expected_output: str = ""
    max_steps: int = 50
    max_cost_usd: float = 1.0
    timeout_seconds: int = 300

@dataclass
class AgentEvalRun:
    run_id: str
    agent_id: str
    task_id: str
    actual_output: str = ""
    steps_taken: int = 0
    cost_usd: float = 0.0
    latency_seconds: float = 0.0
    success: bool = False
    safety_violations: int = 0
    tool_calls: int = 0
    started_at: str = ""
    completed_at: str = ""

@dataclass
class BenchmarkSuite:
    suite_id: str
    name: str
    task_ids: List[str] = field(default_factory=list)
    version: str = "1.0"
    created_at: str = ""

# ─── Secret Credential Scanning Models ──────────────────────────────

class SecretType(str, Enum):
    API_KEY = "api_key"
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"
    TOKEN = "token"
    CONNECTION_STRING = "connection_string"
    CERTIFICATE = "certificate"
    CLOUD_CREDENTIAL = "cloud_credential"
    GENERIC = "generic"

class SecretFindingStatus(str, Enum):
    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"
    FALSE_POSITIVE = "false_positive"
    ACKNOWLEDGED = "acknowledged"

@dataclass
class SecretScanFinding:
    finding_id: str
    secret_type: SecretType
    file_path: str
    line_number: int = 0
    commit_sha: str = ""
    author: str = ""
    status: SecretFindingStatus = SecretFindingStatus.ACTIVE
    severity: str = "high"  # critical, high, medium, low
    entropy: float = 0.0  # Shannon entropy
    verified: bool = False  # Was the secret tested against the service?
    rotated_at: str = ""
    detected_at: str = ""

@dataclass
class SecretScanPolicy:
    policy_id: str
    block_on_active_secrets: bool = True
    max_allowed_findings: int = 0
    require_rotation_within_hours: int = 24
    excluded_paths: List[str] = field(default_factory=list)  # paths to skip
    excluded_types: List[str] = field(default_factory=list)  # secret types to skip

# ─── Packaging & Pricing Models ─────────────────────────────────────

class PricingModel(str, Enum):
    FLAT_RATE = "flat_rate"
    PER_SEAT = "per_seat"
    USAGE_BASED = "usage_based"
    TIERED = "tiered"
    FREEMIUM = "freemium"
    HYBRID = "hybrid"

class PackageTier(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"

@dataclass
class PricingPlan:
    plan_id: str
    name: str
    tier: PackageTier
    pricing_model: PricingModel
    base_price_monthly: float = 0.0
    per_seat_price: float = 0.0
    included_units: int = 0  # included usage units
    overage_price_per_unit: float = 0.0
    max_seats: int = 0  # 0 = unlimited
    features: List[str] = field(default_factory=list)
    active: bool = True

@dataclass
class PricingSubscription:
    subscription_id: str
    customer_id: str
    plan_id: str
    seats: int = 1
    usage_units: int = 0
    monthly_total: float = 0.0
    started_at: str = ""
    billing_cycle_start: str = ""
    discount_pct: float = 0.0

@dataclass
class PricingSimulation:
    simulation_id: str
    plan_id: str
    seats: int = 1
    projected_usage: int = 0
    monthly_cost: float = 0.0
    annual_cost: float = 0.0
    cost_per_seat: float = 0.0


# ─── SAST Integration Models ─────────────────────────────────────────

class SastSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class SastCategory(str, Enum):
    INJECTION = "injection"
    XSS = "xss"
    AUTH_BYPASS = "auth_bypass"
    CRYPTO = "crypto"
    PATH_TRAVERSAL = "path_traversal"
    SSRF = "ssrf"
    DESERIALIZATION = "deserialization"
    HARDCODED_SECRET = "hardcoded_secret"
    BUFFER_OVERFLOW = "buffer_overflow"
    RACE_CONDITION = "race_condition"

class SastFindingState(str, Enum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    FIXED = "fixed"
    ACCEPTED_RISK = "accepted_risk"

@dataclass
class SastFinding:
    finding_id: str
    category: SastCategory
    severity: SastSeverity
    file_path: str
    line_number: int
    code_snippet: str = ""
    description: str = ""
    cwe_id: str = ""  # CWE-79 etc.
    state: SastFindingState = SastFindingState.OPEN
    tool_name: str = ""
    confidence: float = 0.0  # 0-1
    remediation: str = ""
    detected_at: str = ""
    resolved_at: str = ""

@dataclass
class SastScanRun:
    scan_id: str
    project_name: str
    branch: str = "main"
    commit_sha: str = ""
    tool_name: str = ""
    started_at: str = ""
    completed_at: str = ""
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0

@dataclass
class SastPolicy:
    policy_id: str
    max_critical: int = 0
    max_high: int = 0
    block_on_new_critical: bool = True
    require_cwe_mapping: bool = True
    min_confidence: float = 0.5


# ─── Economics Profitability Certification Models ──────────────────

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional

class ProfitabilityMetric(str, Enum):
    GROSS_MARGIN = "gross_margin"
    CONTRIBUTION_MARGIN = "contribution_margin"
    UNIT_ECONOMICS = "unit_economics"
    CAC_PAYBACK = "cac_payback"
    LTV_CAC_RATIO = "ltv_cac_ratio"
    BURN_RATE = "burn_rate"

class EconCertLevel(str, Enum):
    NOT_VIABLE = "not_viable"
    MARGINAL = "marginal"
    VIABLE = "viable"
    PROFITABLE = "profitable"
    HIGHLY_PROFITABLE = "highly_profitable"

@dataclass
class RevenueRecord:
    record_id: str
    product_id: str
    period: str
    revenue: float = 0.0
    cogs: float = 0.0
    gross_profit: float = 0.0
    customers: int = 0
    churn_count: int = 0
    cac: float = 0.0
    ltv: float = 0.0

@dataclass
class EconCertification:
    cert_id: str
    product_id: str
    level: EconCertLevel = EconCertLevel.NOT_VIABLE
    gross_margin_pct: float = 0.0
    ltv_cac_ratio: float = 0.0
    unit_economics_positive: bool = False
    burn_rate_monthly: float = 0.0
    months_to_profitability: int = 0
    certified: bool = False
    certified_at: str = ""
    notes: str = ""


# ─── Plane Topology Governance Models ───────────────────────────────

class PlaneFunction(str, Enum):
    CONTROL = "control"
    DATA = "data"
    MANAGEMENT = "management"
    OBSERVABILITY = "observability"
    SECURITY = "security"

class PlaneIsolation(str, Enum):
    DEDICATED = "dedicated"
    SHARED = "shared"
    HYBRID = "hybrid"

@dataclass
class PlaneDefinition:
    plane_id: str
    name: str
    function: PlaneFunction
    isolation: PlaneIsolation = PlaneIsolation.DEDICATED
    components: List[str] = field(default_factory=list)
    allowed_dependencies: List[str] = field(default_factory=list)  # plane_ids this plane may call
    forbidden_dependencies: List[str] = field(default_factory=list)
    max_latency_ms: float = 0.0
    requires_mtls: bool = False

@dataclass
class PlaneGovernanceTopology:
    topology_id: str
    name: str
    plane_ids: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    compliant: bool = False
    evaluated_at: str = ""

@dataclass
class PlaneViolation:
    violation_id: str
    source_plane: str
    target_plane: str
    rule: str  # e.g. 'forbidden_dependency', 'missing_mtls', 'circular'
    description: str = ""
    severity: str = "high"

# ─── Customer Status Communication Models ───────────────────────────

class StatusPageState(str, Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"
    MAINTENANCE = "maintenance"

class CommunicationType(str, Enum):
    STATUS_UPDATE = "status_update"
    INCIDENT_NOTICE = "incident_notice"
    MAINTENANCE_NOTICE = "maintenance_notice"
    RESOLUTION_NOTICE = "resolution_notice"
    RCA_REPORT = "rca_report"

@dataclass
class ServiceStatus:
    service_id: str
    service_name: str
    state: StatusPageState = StatusPageState.OPERATIONAL
    message: str = ""
    updated_at: str = ""
    incident_id: str = ""

@dataclass
class StatusCommunication:
    comm_id: str
    comm_type: CommunicationType
    title: str
    body: str
    affected_services: List[str] = field(default_factory=list)
    audience: str = "all"  # all, affected, internal
    published: bool = False
    published_at: str = ""
    author: str = ""

@dataclass
class MaintenanceWindow:
    window_id: str
    title: str
    service_ids: List[str] = field(default_factory=list)
    scheduled_start: str = ""
    scheduled_end: str = ""
    actual_start: str = ""
    actual_end: str = ""
    status: str = "scheduled"  # scheduled, in_progress, completed, cancelled

# ─── Budget Quota Guardrail Models ──────────────────────────────────

class QuotaResourceType(str, Enum):
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    API_CALLS = "api_calls"
    MODEL_TOKENS = "model_tokens"
    SEATS = "seats"
    PROJECTS = "projects"

class GuardrailAction(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    THROTTLE = "throttle"
    DENY = "deny"
    NOTIFY = "notify"

@dataclass
class QuotaDefinition:
    quota_id: str
    resource_type: QuotaResourceType
    tenant_id: str
    limit: float
    current_usage: float = 0.0
    warn_threshold_pct: float = 80.0
    hard_limit_pct: float = 100.0
    period: str = "monthly"  # daily, weekly, monthly, annual
    rollover: bool = False

@dataclass
class BudgetAllocation:
    budget_id: str
    tenant_id: str
    total_budget: float
    spent: float = 0.0
    reserved: float = 0.0
    currency: str = "USD"
    period: str = "monthly"
    alert_threshold_pct: float = 80.0

@dataclass
class GuardrailDecision:
    decision_id: str
    tenant_id: str
    resource_type: QuotaResourceType
    requested_amount: float
    action: GuardrailAction
    reason: str = ""
    remaining_quota: float = 0.0
    remaining_budget: float = 0.0
    timestamp: str = ""

# ─── Knowledge Freshness Versioning Models ──────────────────────────

class KnowledgeSourceType(str, Enum):
    DOCUMENTATION = "documentation"
    API_SPEC = "api_spec"
    CODEBASE = "codebase"
    TRAINING_DATA = "training_data"
    EXTERNAL_FEED = "external_feed"
    MANUAL_ENTRY = "manual_entry"

class FreshnessStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"
    REFRESHING = "refreshing"

@dataclass
class KnowledgeArticle:
    article_id: str
    title: str
    source_type: KnowledgeSourceType
    content_hash: str = ""
    version: int = 1
    freshness_status: FreshnessStatus = FreshnessStatus.CURRENT
    created_at: str = ""
    updated_at: str = ""
    expires_at: str = ""  # ISO datetime
    ttl_seconds: int = 86400  # default 24h
    source_url: str = ""
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # article_ids this depends on
    superseded_by: str = ""  # article_id of newer version

@dataclass
class KnowledgeVersion:
    version_id: str
    article_id: str
    version_number: int
    content_hash: str
    created_at: str = ""
    change_summary: str = ""
    author: str = ""

# ─── Offline Signed Bundle Models ───────────────────────────────────

class OfflineBundleStatus(str, Enum):
    DRAFT = "draft"
    BUILDING = "building"
    SIGNING = "signing"
    SIGNED = "signed"
    DISTRIBUTING = "distributing"
    INSTALLED = "installed"
    REVOKED = "revoked"
    FAILED = "failed"

class BundleArtifactType(str, Enum):
    CONTAINER_IMAGE = "container_image"
    HELM_CHART = "helm_chart"
    BINARY = "binary"
    CONFIG = "config"
    DATABASE_MIGRATION = "database_migration"
    CERTIFICATE = "certificate"

@dataclass
class BundleArtifact:
    artifact_id: str
    artifact_type: BundleArtifactType
    name: str
    version: str
    size_bytes: int = 0
    sha256_digest: str = ""
    signed: bool = False
    signature: str = ""

@dataclass
class OfflineBundle:
    bundle_id: str
    name: str
    target_version: str
    status: OfflineBundleStatus = OfflineBundleStatus.DRAFT
    artifacts: List[str] = field(default_factory=list)  # artifact_ids
    total_size_bytes: int = 0
    created_at: str = ""
    signed_at: str = ""
    signer_identity: str = ""
    bundle_signature: str = ""
    expiry_date: str = ""
    target_environments: List[str] = field(default_factory=list)
    install_order: List[str] = field(default_factory=list)  # ordered artifact_ids
    rollback_supported: bool = True
    min_platform_version: str = ""

# ─── Threat Modeling Models ─────────────────────────────────────────

class ThreatCategory(str, Enum):
    SPOOFING = "spoofing"
    TAMPERING = "tampering"
    REPUDIATION = "repudiation"
    INFORMATION_DISCLOSURE = "information_disclosure"
    DENIAL_OF_SERVICE = "denial_of_service"
    ELEVATION_OF_PRIVILEGE = "elevation_of_privilege"

class ThreatSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class ThreatStatus(str, Enum):
    IDENTIFIED = "identified"
    ANALYZED = "analyzed"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"
    TRANSFERRED = "transferred"

@dataclass
class ThreatModelAsset:
    asset_id: str
    name: str
    asset_type: str  # service, database, api, network, storage
    trust_level: str = "internal"  # public, dmz, internal, restricted
    data_classification: str = "internal"  # public, internal, confidential, restricted
    protocols: List[str] = field(default_factory=list)

@dataclass
class DataFlow:
    flow_id: str
    source_asset: str
    target_asset: str
    protocol: str = "https"
    data_classification: str = "internal"
    authenticated: bool = True
    encrypted: bool = True

@dataclass
class ThreatRecord:
    threat_id: str
    title: str
    category: ThreatCategory
    severity: ThreatSeverity
    status: ThreatStatus = ThreatStatus.IDENTIFIED
    affected_assets: List[str] = field(default_factory=list)
    affected_flows: List[str] = field(default_factory=list)
    attack_vector: str = ""
    mitigation: str = ""
    risk_score: float = 0.0  # 0-10
    stride_elements: List[str] = field(default_factory=list)


# ─── Agent Team Topology Models ─────────────────────────────────────

class AgentTeamRole(str, Enum):
    SUPERVISOR = "supervisor"
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    SPECIALIST = "specialist"
    OBSERVER = "observer"

class DelegationPolicy(str, Enum):
    ROUND_ROBIN = "round_robin"
    CAPABILITY_MATCH = "capability_match"
    LEAST_LOADED = "least_loaded"
    PRIORITY_BASED = "priority_based"
    STICKY = "sticky"  # same agent for same task type

class TeamAgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OVERLOADED = "overloaded"
    OFFLINE = "offline"
    DRAINING = "draining"

@dataclass
class TeamAgent:
    agent_id: str
    name: str
    role: AgentTeamRole
    capabilities: List[str] = field(default_factory=list)
    status: TeamAgentStatus = TeamAgentStatus.IDLE
    max_concurrent_tasks: int = 5
    current_task_count: int = 0
    success_rate: float = 1.0
    avg_task_duration_seconds: float = 0.0
    total_tasks_completed: int = 0
    parent_agent_id: str = ""  # supervisor

@dataclass
class TaskDelegation:
    delegation_id: str
    task_id: str
    delegated_to: str  # agent_id
    delegated_by: str  # agent_id
    required_capabilities: List[str] = field(default_factory=list)
    delegated_at: str = ""
    completed_at: str = ""
    success: bool = False
    retry_count: int = 0
    max_retries: int = 3

# ─── Job Fairness and Tenant Isolation Models ───────────────────────

class FairnessPolicy(str, Enum):
    EQUAL_SHARE = "equal_share"
    WEIGHTED = "weighted"
    PRIORITY_BASED = "priority_based"
    BURST_ALLOWED = "burst_allowed"

class JobQueueStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    THROTTLED = "throttled"
    PREEMPTED = "preempted"
    FAILED = "failed"

@dataclass
class TenantQuota:
    tenant_id: str
    max_concurrent_jobs: int = 10
    max_cpu_cores: int = 100
    max_memory_gb: int = 256
    max_gpu_count: int = 0
    priority_weight: float = 1.0
    burst_multiplier: float = 1.5
    current_running_jobs: int = 0
    current_cpu_used: int = 0
    current_memory_used: int = 0
    current_gpu_used: int = 0

@dataclass
class FairnessJob:
    job_id: str
    tenant_id: str
    cpu_requested: int = 1
    memory_gb_requested: int = 1
    gpu_requested: int = 0
    priority: int = 5  # 1-10, 10=highest
    status: JobQueueStatus = JobQueueStatus.QUEUED
    queued_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    preempted_by: str = ""  # job_id that caused preemption
    wait_time_seconds: float = 0.0


# ─── AI Model Supply Chain Models ───────────────────────────────────
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict

class ModelProvenance(str, Enum):
    FIRST_PARTY = "first_party"
    OPEN_SOURCE = "open_source"
    COMMERCIAL = "commercial"
    FINE_TUNED = "fine_tuned"
    UNKNOWN = "unknown"

class ModelRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNASSESSED = "unassessed"

@dataclass
class AiModelRecord:
    model_id: str
    name: str
    version: str
    provenance: ModelProvenance
    framework: str = ""
    parameters_count: int = 0
    training_data_hash: str = ""
    model_hash: str = ""
    license_type: str = ""
    risk_level: ModelRiskLevel = ModelRiskLevel.UNASSESSED
    vulnerabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    approved: bool = False
    approved_by: str = ""
    registered_at: str = ""

@dataclass
class ModelScanResult:
    scan_id: str
    model_id: str
    scanner: str
    passed: bool = False
    findings: List[str] = field(default_factory=list)
    scanned_at: str = ""
    confidence: float = 0.0

# ─── Human Approval Takeover Models ─────────────────────────────────

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"

class TakeoverReason(str, Enum):
    SAFETY = "safety"
    COST_THRESHOLD = "cost_threshold"
    POLICY_VIOLATION = "policy_violation"
    ERROR_RATE = "error_rate"
    MANUAL_REQUEST = "manual_request"
    COMPLIANCE = "compliance"

@dataclass
class ApprovalRequest:
    request_id: str
    action_description: str
    requester: str  # agent or system
    approver: str = ""  # human approver
    status: ApprovalStatus = ApprovalStatus.PENDING
    risk_level: str = "medium"  # low, medium, high, critical
    auto_approve_threshold: str = "low"  # auto-approve if risk <= threshold
    created_at: str = ""
    decided_at: str = ""
    expires_at: str = ""
    decision_reason: str = ""
    context: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TakeoverEvent:
    event_id: str
    reason: TakeoverReason
    triggered_by: str  # human who took over
    agent_id: str  # agent being taken over
    started_at: str = ""
    ended_at: str = ""
    actions_taken: List[str] = field(default_factory=list)
    outcome: str = ""  # resolved, escalated, rollback


# ─── Privacy Preserving Learning Models ─────────────────────────────

class PrivacyMechanism(str, Enum):
    DIFFERENTIAL_PRIVACY = "differential_privacy"
    FEDERATED_AVERAGING = "federated_averaging"
    SECURE_AGGREGATION = "secure_aggregation"
    HOMOMORPHIC = "homomorphic"
    LOCAL_DP = "local_dp"

class FederatedRoundStatus(str, Enum):
    INITIALIZED = "initialized"
    DISTRIBUTING = "distributing"
    TRAINING = "training"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class PrivacyBudget:
    budget_id: str
    tenant_id: str
    epsilon_total: float = 10.0
    epsilon_used: float = 0.0
    delta: float = 1e-5
    mechanism: PrivacyMechanism = PrivacyMechanism.DIFFERENTIAL_PRIVACY
    queries_allowed: int = 1000
    queries_used: int = 0
    reset_interval_hours: int = 24
    created_at: str = ""

@dataclass
class FederatedParticipant:
    participant_id: str
    tenant_id: str
    data_size: int = 0
    model_version: int = 0
    last_contribution_at: str = ""
    contribution_count: int = 0
    dropped_rounds: int = 0
    active: bool = True

@dataclass
class FederatedRound:
    round_id: str
    round_number: int
    status: FederatedRoundStatus = FederatedRoundStatus.INITIALIZED
    participants: List[str] = field(default_factory=list)
    min_participants: int = 2
    model_version_in: int = 0
    model_version_out: int = 0
    epsilon_spent: float = 0.0
    noise_multiplier: float = 1.0
    started_at: str = ""
    completed_at: str = ""
    aggregation_weights: Dict[str, float] = field(default_factory=dict)


# ─── Automated Upgrade Tooling Models ───────────────────────────────

class UpgradeToolAction(str, Enum):
    PRE_CHECK = "pre_check"
    BACKUP = "backup"
    SCHEMA_MIGRATE = "schema_migrate"
    CODE_PATCH = "code_patch"
    CONFIG_UPDATE = "config_update"
    RESTART = "restart"
    HEALTH_CHECK = "health_check"
    ROLLBACK = "rollback"
    POST_CHECK = "post_check"

class UpgradeToolStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"

@dataclass
class UpgradeStep:
    step_id: str
    action: UpgradeToolAction
    description: str
    order: int = 0
    status: UpgradeToolStatus = UpgradeToolStatus.PENDING
    duration_seconds: float = 0.0
    error_message: str = ""
    rollback_step_id: str = ""
    preconditions: List[str] = field(default_factory=list)
    idempotent: bool = True
    timeout_seconds: int = 300

@dataclass
class UpgradePlaybook:
    playbook_id: str
    name: str
    from_version: str
    to_version: str
    steps: List[str] = field(default_factory=list)
    current_step_index: int = 0
    status: UpgradeToolStatus = UpgradeToolStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    dry_run: bool = False
    auto_rollback: bool = True
    total_duration_seconds: float = 0.0

# ─── Database Migration Compatibility Models ────────────────────────

class MigrationCompatLevel(str, Enum):
    FULLY_COMPATIBLE = "fully_compatible"
    BACKWARD_COMPATIBLE = "backward_compatible"
    BREAKING = "breaking"
    UNKNOWN = "unknown"

class MigrationSchemaChangeType(str, Enum):
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    MODIFY_COLUMN = "modify_column"
    ADD_TABLE = "add_table"
    DROP_TABLE = "drop_table"
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"
    ADD_CONSTRAINT = "add_constraint"
    DROP_CONSTRAINT = "drop_constraint"
    RENAME = "rename"

@dataclass
class MigrationSchemaChange:
    change_id: str
    change_type: MigrationSchemaChangeType
    table_name: str
    column_name: str = ""
    old_type: str = ""
    new_type: str = ""
    nullable: bool = True
    has_default: bool = False
    compatibility: MigrationCompatLevel = MigrationCompatLevel.UNKNOWN

@dataclass
class DbMigrationScript:
    script_id: str
    version: str
    description: str
    changes: List[str] = field(default_factory=list)  # change_ids
    up_sql: str = ""
    down_sql: str = ""
    estimated_duration_seconds: int = 0
    requires_downtime: bool = False
    reviewed: bool = False
    applied: bool = False
    applied_at: str = ""
    rollback_tested: bool = False

# ─── Independent Expert Validation Models ───────────────────────────

class ExpertDomain(str, Enum):
    SECURITY = "security"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    DATABASE = "database"
    COMPLIANCE = "compliance"
    ACCESSIBILITY = "accessibility"
    DATA_PRIVACY = "data_privacy"

class ExpertValidationOutcome(str, Enum):
    APPROVED = "approved"
    CONDITIONALLY_APPROVED = "conditionally_approved"
    REJECTED = "rejected"
    NEEDS_REWORK = "needs_rework"
    DEFERRED = "deferred"

@dataclass
class ExpertValidator:
    validator_id: str
    name: str
    domain: ExpertDomain
    organization: str = ""
    credentials: List[str] = field(default_factory=list)
    active: bool = True
    total_reviews: int = 0
    approval_rate: float = 0.0
    avg_review_hours: float = 0.0
    conflicts_of_interest: List[str] = field(default_factory=list)  # org names

@dataclass
class ExpertReview:
    review_id: str
    validator_id: str
    subject_id: str  # what is being reviewed
    domain: ExpertDomain
    outcome: ExpertValidationOutcome = ExpertValidationOutcome.DEFERRED
    findings: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)  # for conditional approval
    score: float = 0.0  # 0-10
    submitted_at: str = ""
    reviewed_at: str = ""
    review_hours: float = 0.0
    independent: bool = True  # no conflict of interest


# ─── Scale Performance Certification Models ─────────────────────────

class PerformanceTestType(str, Enum):
    LOAD = "load"
    STRESS = "stress"
    SPIKE = "spike"
    SOAK = "soak"
    BASELINE = "baseline"

class PerformanceVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    DEGRADED = "degraded"
    INCONCLUSIVE = "inconclusive"

@dataclass
class PerformanceBenchmark:
    benchmark_id: str
    name: str
    test_type: PerformanceTestType
    target_rps: int = 0  # requests per second
    target_p99_ms: float = 0.0
    target_p95_ms: float = 0.0
    target_error_rate_pct: float = 1.0
    max_cpu_pct: float = 80.0
    max_memory_pct: float = 80.0
    duration_minutes: int = 30
    concurrent_users: int = 100

@dataclass
class PerformanceResult:
    result_id: str
    benchmark_id: str
    actual_rps: int = 0
    actual_p99_ms: float = 0.0
    actual_p95_ms: float = 0.0
    actual_error_rate_pct: float = 0.0
    actual_cpu_pct: float = 0.0
    actual_memory_pct: float = 0.0
    duration_minutes: int = 0
    verdict: PerformanceVerdict = PerformanceVerdict.INCONCLUSIVE
    tested_at: str = ""
    environment: str = ""
    notes: str = ""


# ─── Security Data Certification Models ─────────────────────────────

class SecurityControlStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    PARTIAL = "partial"
    IMPLEMENTED = "implemented"
    VERIFIED = "verified"
    FAILED = "failed"

class DataProtectionLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    TOP_SECRET = "top_secret"

@dataclass
class SecurityControl:
    control_id: str
    framework: str  # SOC2, ISO27001, NIST, etc.
    control_name: str
    description: str = ""
    status: SecurityControlStatus = SecurityControlStatus.NOT_IMPLEMENTED
    evidence_ids: List[str] = field(default_factory=list)
    verified_by: str = ""
    verified_at: str = ""
    last_tested: str = ""
    test_frequency_days: int = 90
    compensating_control: str = ""

@dataclass
class DataClassification:
    classification_id: str
    data_type: str  # PII, PHI, PCI, financial, etc.
    protection_level: DataProtectionLevel
    storage_location: str = ""
    encrypted_at_rest: bool = False
    encrypted_in_transit: bool = False
    retention_days: int = 365
    cross_border: bool = False
    compliant: bool = False
    owner: str = ""

# ─── PSIRT Security Incident Models ─────────────────────────────────

class PsirtSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class PsirtStatus(str, Enum):
    REPORTED = "reported"
    TRIAGED = "triaged"
    INVESTIGATING = "investigating"
    FIX_DEVELOPING = "fix_developing"
    FIX_AVAILABLE = "fix_available"
    DISCLOSED = "disclosed"
    CLOSED = "closed"

@dataclass
class SecurityVulnerability:
    vuln_id: str
    title: str
    description: str
    severity: PsirtSeverity
    status: PsirtStatus = PsirtStatus.REPORTED
    cve_id: str = ""
    cvss_score: float = 0.0  # 0-10
    affected_versions: List[str] = field(default_factory=list)
    fixed_version: str = ""
    reporter: str = ""
    assignee: str = ""
    reported_at: str = ""
    disclosed_at: str = ""
    sla_hours: int = 72  # response SLA
    patch_url: str = ""
    workaround: str = ""
    exploited_in_wild: bool = False

@dataclass
class PsirtAdvisory:
    advisory_id: str
    vuln_id: str
    title: str
    summary: str = ""
    affected_products: List[str] = field(default_factory=list)
    remediation: str = ""
    published: bool = False
    published_at: str = ""

# ─── Human Curation Governance Models ───────────────────────────────

class CurationAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    FLAG = "flag"
    DEFER = "defer"

class ContentCategory(str, Enum):
    KNOWLEDGE = "knowledge"
    RECIPE = "recipe"
    RULE = "rule"
    PATTERN = "pattern"
    TRAINING_DATA = "training_data"
    POLICY = "policy"

@dataclass
class CurationItem:
    item_id: str
    category: ContentCategory
    title: str
    content_hash: str = ""
    source: str = ""  # ai_generated, human_authored, imported
    quality_score: float = 0.0  # 0-1
    curator: str = ""
    action: CurationAction = CurationAction.DEFER
    review_notes: str = ""
    created_at: str = ""
    curated_at: str = ""
    auto_generated: bool = False
    conflicts_with: List[str] = field(default_factory=list)  # item_ids

@dataclass
class CurationPolicy:
    policy_id: str
    name: str
    category: ContentCategory
    auto_approve_threshold: float = 0.9  # quality_score threshold
    require_human_review: bool = True
    min_reviewers: int = 1
    max_age_days: int = 90
    created_at: str = ""

# ─── Platform Version Compatibility Models ───────────────────────────

class CompatibilityStatus(str, Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    DEPRECATED = "deprecated"
    UNTESTED = "untested"
    CONDITIONAL = "conditional"

class PlatformComponent(str, Enum):
    RUNNER = "runner"
    CONTROL_PLANE = "control_plane"
    DATABASE = "database"
    SDK = "sdk"
    CLI = "cli"
    AGENT = "agent"
    PLUGIN = "plugin"
    API = "api"

@dataclass
class VersionEntry:
    component: PlatformComponent
    version: str
    release_date: str = ""
    eol_date: str = ""
    supported: bool = True
    breaking_changes: List[str] = field(default_factory=list)
    min_compatible_versions: Dict[str, str] = field(default_factory=dict)  # component->min_version

@dataclass
class CompatibilityRecord:
    record_id: str
    component_a: PlatformComponent
    version_a: str
    component_b: PlatformComponent
    version_b: str
    status: CompatibilityStatus = CompatibilityStatus.UNTESTED
    notes: str = ""
    tested_at: str = ""
    conditions: List[str] = field(default_factory=list)

# ─── Chaos Resilience Fault Injection Models ──────────────────────────

class ChaosFaultType(str, Enum):
    LATENCY = "latency"
    ERROR = "error"
    PARTITION = "partition"
    CPU_STRESS = "cpu_stress"
    MEMORY_PRESSURE = "memory_pressure"
    DISK_FILL = "disk_fill"
    DNS_FAILURE = "dns_failure"
    PROCESS_KILL = "process_kill"
    CLOCK_SKEW = "clock_skew"

class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    ROLLED_BACK = "rolled_back"

@dataclass
class FaultInjectionRule:
    rule_id: str
    fault_type: ChaosFaultType
    target_service: str
    target_instance: str = ""  # empty = all instances
    parameters: Dict[str, str] = field(default_factory=dict)  # e.g. latency_ms=500
    probability: float = 1.0  # 0-1 injection probability
    duration_seconds: int = 60

@dataclass
class ChaosExperiment:
    experiment_id: str
    name: str
    hypothesis: str  # what we expect to happen
    rules: List[str] = field(default_factory=list)  # rule_ids
    status: ExperimentStatus = ExperimentStatus.DRAFT
    steady_state_checks: List[str] = field(default_factory=list)  # health checks
    abort_conditions: List[str] = field(default_factory=list)
    blast_radius: str = "single_service"  # single_service, zone, region
    approved_by: str = ""
    started_at: str = ""
    completed_at: str = ""
    result_summary: str = ""
    hypothesis_confirmed: bool = False

# ─── Event Schema Compatibility Models ───────────────────────────────

class EventSchemaChangeType(str, Enum):
    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_RENAMED = "field_renamed"
    TYPE_CHANGED = "type_changed"
    REQUIRED_ADDED = "required_added"
    REQUIRED_REMOVED = "required_removed"
    ENUM_VALUE_ADDED = "enum_value_added"
    ENUM_VALUE_REMOVED = "enum_value_removed"

class SchemaCompatResult(str, Enum):
    FULLY_COMPATIBLE = "fully_compatible"
    BACKWARD_COMPATIBLE = "backward_compatible"
    FORWARD_COMPATIBLE = "forward_compatible"
    BREAKING = "breaking"
    UNKNOWN = "unknown"

@dataclass
class EventSchemaVersion:
    schema_id: str
    event_type: str
    version: str
    fields: Dict[str, str] = field(default_factory=dict)  # field_name -> type
    required_fields: List[str] = field(default_factory=list)
    enum_fields: Dict[str, List[str]] = field(default_factory=dict)  # field_name -> values
    registered_at: str = ""
    deprecated: bool = False

@dataclass
class EvolutionSchemaChange:
    change_id: str
    schema_id: str
    change_type: EventSchemaChangeType
    field_name: str
    old_value: str = ""
    new_value: str = ""
    breaking: bool = False

# ─── Knowledge Isolation Models ──────────────────────────────────────

class KnowledgeBoundary(str, Enum):
    TENANT = "tenant"
    PROJECT = "project"
    TEAM = "team"
    PUBLIC = "public"
    SHARED = "shared"

class KnowledgeAccessLevel(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

@dataclass
class KnowledgePartition:
    partition_id: str
    name: str
    boundary: KnowledgeBoundary
    owner: str = ""  # tenant_id, project_id, team_id
    item_count: int = 0
    size_bytes: int = 0
    created_at: str = ""
    encrypted: bool = False
    retention_days: int = 365

@dataclass
class KnowledgeAccessGrant:
    grant_id: str
    partition_id: str
    principal: str  # user_id, team_id, service_account
    access_level: KnowledgeAccessLevel
    granted_by: str = ""
    granted_at: str = ""
    expires_at: str = ""
    revoked: bool = False

# ─── Feature Flag Progressive Enable Models ──────────────────────────

class FlagRolloutStrategy(str, Enum):
    PERCENTAGE = "percentage"
    USER_LIST = "user_list"
    REGION = "region"
    TENANT = "tenant"
    CANARY = "canary"
    ALL = "all"
    NONE = "none"

class ProgressiveFlagStatus(str, Enum):
    DISABLED = "disabled"
    CANARY = "canary"
    ROLLING = "rolling"
    FULLY_ENABLED = "fully_enabled"
    PAUSED = "paused"
    ROLLED_BACK = "rolled_back"

@dataclass
class ProgressiveFlag:
    flag_id: str
    name: str
    description: str = ""
    status: ProgressiveFlagStatus = ProgressiveFlagStatus.DISABLED
    strategy: FlagRolloutStrategy = FlagRolloutStrategy.NONE
    percentage: float = 0.0  # 0-100
    target_users: List[str] = field(default_factory=list)
    target_regions: List[str] = field(default_factory=list)
    target_tenants: List[str] = field(default_factory=list)
    error_rate_threshold: float = 5.0  # auto-rollback if error_rate > threshold
    current_error_rate: float = 0.0
    created_at: str = ""
    last_updated: str = ""
    rollout_history: List[str] = field(default_factory=list)  # status transitions

@dataclass
class RolloutStep:
    step_id: str
    flag_id: str
    from_percentage: float = 0.0
    to_percentage: float = 0.0
    executed_at: str = ""
    success: bool = True
    error_rate_at_execution: float = 0.0

# ─── Security Fix Backport Models ────────────────────────────────────

class BackportPriority(str, Enum):
    EMERGENCY = "emergency"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class BackportStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPLIED = "applied"
    VERIFIED = "verified"
    SKIPPED = "skipped"
    FAILED = "failed"

@dataclass
class SecurityFix:
    fix_id: str
    cve_id: str
    title: str
    priority: BackportPriority
    original_version: str  # version where fix was first applied
    patch_hash: str = ""
    created_at: str = ""
    affects_versions: List[str] = field(default_factory=list)

@dataclass
class BackportRecord:
    backport_id: str
    fix_id: str
    target_version: str
    status: BackportStatus = BackportStatus.PENDING
    applied_at: str = ""
    verified_at: str = ""
    verified_by: str = ""
    skip_reason: str = ""
    failure_reason: str = ""
    test_passed: bool = False

# ─── Scheduled Restore DR Exercise Models ────────────────────────────

class DrExerciseType(str, Enum):
    FULL_RESTORE = "full_restore"
    PARTIAL_RESTORE = "partial_restore"
    FAILOVER = "failover"
    TABLETOP = "tabletop"
    COMMUNICATION = "communication"

class DrExerciseStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class DrExercise:
    exercise_id: str
    name: str
    exercise_type: DrExerciseType
    status: DrExerciseStatus = DrExerciseStatus.SCHEDULED
    scheduled_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    target_rto_minutes: int = 60
    target_rpo_minutes: int = 15
    actual_rto_minutes: int = 0
    actual_rpo_minutes: int = 0
    participants: List[str] = field(default_factory=list)
    services_tested: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    passed: bool = False
    lead: str = ""

@dataclass
class DrSchedule:
    schedule_id: str
    exercise_type: DrExerciseType
    frequency_days: int = 90  # how often to run
    last_executed: str = ""
    next_scheduled: str = ""
    mandatory: bool = True


# ─── Artifact Retention Economics Models ─────────────────────────────

class ArtifactTier(str, Enum):
    HOT = 'hot'
    WARM = 'warm'
    COLD = 'cold'
    ARCHIVE = 'archive'
    DELETED = 'deleted'

class RetentionPolicyAction(str, Enum):
    KEEP = 'keep'
    TIER_DOWN = 'tier_down'
    DELETE = 'delete'
    COMPRESS = 'compress'

@dataclass
class StoredArtifact:
    artifact_id: str
    name: str
    size_bytes: int
    tier: ArtifactTier = ArtifactTier.HOT
    created_at: str = ''
    last_accessed: str = ''
    access_count: int = 0
    cost_per_gb_month: float = 0.023
    owner: str = ''
    tags: Dict[str, str] = field(default_factory=dict)
    legal_hold: bool = False

@dataclass
class RetentionRule:
    rule_id: str
    name: str
    max_age_days: int = 90
    min_access_count: int = 0
    action: RetentionPolicyAction = RetentionPolicyAction.TIER_DOWN
    target_tier: ArtifactTier = ArtifactTier.COLD
    applies_to_tags: Dict[str, str] = field(default_factory=dict)

# ─── Agent Incident Killswitch Models ────────────────────────────────

class KillswitchAction(str, Enum):
    PAUSE = "pause"
    TERMINATE = "terminate"
    ROLLBACK = "rollback"
    ISOLATE = "isolate"
    THROTTLE = "throttle"

class KillswitchTrigger(str, Enum):
    MANUAL = "manual"
    ERROR_RATE = "error_rate"
    COST_LIMIT = "cost_limit"
    SAFETY_VIOLATION = "safety_violation"
    TIMEOUT = "timeout"
    ANOMALY = "anomaly"

@dataclass
class KillswitchRule:
    rule_id: str
    agent_id: str
    trigger: KillswitchTrigger
    action: KillswitchAction
    threshold: float = 0.0  # trigger-specific threshold
    cooldown_seconds: int = 300
    enabled: bool = True
    last_triggered: str = ""
    trigger_count: int = 0

@dataclass
class KillswitchEvent:
    event_id: str
    rule_id: str
    agent_id: str
    trigger: KillswitchTrigger
    action: KillswitchAction
    triggered_at: str = ""
    resolved_at: str = ""
    resolved: bool = False
    resolution_notes: str = ""
    metric_value: float = 0.0  # the value that triggered killswitch

# ─── Vulnerability Patch SLA Models ──────────────────────────────────

class VulnPatchSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

class VulnPatchStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    PATCH_AVAILABLE = "patch_available"
    PATCH_APPLIED = "patch_applied"
    MITIGATED = "mitigated"
    ACCEPTED_RISK = "accepted_risk"
    CLOSED = "closed"

@dataclass
class VulnerabilityPatch:
    vuln_id: str
    title: str
    severity: VulnPatchSeverity
    status: VulnPatchStatus = VulnPatchStatus.OPEN
    cve_id: str = ""
    cvss_score: float = 0.0
    discovered_at: str = ""
    sla_hours: int = 0  # auto-set based on severity
    patched_at: str = ""
    affected_systems: List[str] = field(default_factory=list)
    assignee: str = ""
    patch_version: str = ""
    risk_acceptance_reason: str = ""
    exploitable: bool = False

@dataclass
class PatchSlaPolicy:
    policy_id: str
    name: str
    critical_sla_hours: int = 24
    high_sla_hours: int = 72
    medium_sla_hours: int = 168  # 7 days
    low_sla_hours: int = 720  # 30 days
    informational_sla_hours: int = 2160  # 90 days

# ─── Agent Tool Permissions Models ───────────────────────────────────

class ToolPermissionLevel(str, Enum):
    DENY = "deny"
    READ_ONLY = "read_only"
    EXECUTE = "execute"
    ADMIN = "admin"

class PermissionScope(str, Enum):
    GLOBAL = "global"
    PROJECT = "project"
    REPOSITORY = "repository"
    ENVIRONMENT = "environment"

@dataclass
class ToolDefinition:
    tool_id: str
    name: str
    description: str = ""
    risk_level: str = "low"  # low, medium, high, critical
    requires_approval: bool = False
    side_effects: bool = False
    categories: List[str] = field(default_factory=list)

@dataclass
class ToolPermissionGrant:
    grant_id: str
    agent_id: str
    tool_id: str
    level: ToolPermissionLevel = ToolPermissionLevel.DENY
    scope: PermissionScope = PermissionScope.GLOBAL
    scope_value: str = ""  # project/repo/env name
    granted_by: str = ""
    granted_at: str = ""
    expires_at: str = ""
    conditions: List[str] = field(default_factory=list)
    revoked: bool = False

# ─── SRE Reliability DR Certification Models ─────────────────────────

class ReliabilityDomain(str, Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    DISASTER_RECOVERY = "disaster_recovery"
    BACKUP = "backup"
    FAILOVER = "failover"

class CertificationLevel(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"

@dataclass
class ReliabilityMetric:
    metric_id: str
    domain: ReliabilityDomain
    name: str
    target_value: float = 0.0
    actual_value: float = 0.0
    unit: str = ""
    met: bool = False
    measured_at: str = ""
    measurement_window_hours: int = 720  # 30 days default

@dataclass
class ReliabilityCertification:
    cert_id: str
    service_name: str
    level: CertificationLevel = CertificationLevel.BRONZE
    metrics: List[str] = field(default_factory=list)  # metric_ids
    certified: bool = False
    certified_at: str = ""
    expires_at: str = ""
    certifier: str = ""
    gaps: List[str] = field(default_factory=list)

# ─── Customer Upgrade Readiness Models ───────────────────────────────

class ReadinessLevel(str, Enum):
    READY = "ready"
    READY_WITH_ACTIONS = "ready_with_actions"
    NOT_READY = "not_ready"
    BLOCKED = "blocked"

class UpgradeCheckCategory(str, Enum):
    COMPATIBILITY = "compatibility"
    DEPENDENCY = "dependency"
    CONFIGURATION = "configuration"
    DATA_MIGRATION = "data_migration"
    CUSTOM_CODE = "custom_code"
    INFRASTRUCTURE = "infrastructure"

@dataclass
class UpgradeCheck:
    check_id: str
    category: UpgradeCheckCategory
    name: str
    description: str = ""
    passed: bool = False
    blocking: bool = True
    remediation: str = ""
    effort_hours: float = 0.0

@dataclass
class UpgradeReadinessAssessment:
    assessment_id: str
    customer_id: str
    current_version: str
    target_version: str
    readiness: ReadinessLevel = ReadinessLevel.NOT_READY
    checks: List[str] = field(default_factory=list)  # check_ids
    overall_score: float = 0.0  # 0-100
    total_effort_hours: float = 0.0
    assessed_at: str = ""
    recommended_upgrade_date: str = ""

# ─── Mature Product Final Gate Models ────────────────────────────────

class FinalGateMaturityDimension(str, Enum):
    FUNCTIONAL = "functional"
    SECURITY = "security"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    OPERABILITY = "operability"
    SCALABILITY = "scalability"
    COMPLIANCE = "compliance"
    ECONOMICS = "economics"
    DOCUMENTATION = "documentation"
    SUPPORT = "support"

class DimensionVerdict(str, Enum):
    PASS = "pass"
    CONDITIONAL_PASS = "conditional_pass"
    FAIL = "fail"
    NOT_EVALUATED = "not_evaluated"

@dataclass
class FinalGateDimensionAssessment:
    dimension: FinalGateMaturityDimension
    verdict: DimensionVerdict = DimensionVerdict.NOT_EVALUATED
    score: float = 0.0  # 0-100
    evidence_refs: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)  # for conditional_pass
    blockers: List[str] = field(default_factory=list)  # for fail
    assessed_at: str = ""
    assessor: str = ""

@dataclass
class FinalGateDecision:
    gate_id: str
    product_name: str
    version: str
    overall_verdict: DimensionVerdict = DimensionVerdict.NOT_EVALUATED
    assessments: Dict[str, FinalGateDimensionAssessment] = field(default_factory=dict)
    mandatory_dimensions: List[str] = field(default_factory=list)
    decision_made_at: str = ""
    decision_maker: str = ""
    release_authorized: bool = False
    conditions_for_release: List[str] = field(default_factory=list)
    next_review_date: str = ""


# ─── Cost Scenario Forecast Models ───────────────────────────────────

class ForecastCostCategory(str, Enum):
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    LICENSE = "license"
    SUPPORT = "support"
    PERSONNEL = "personnel"

class ScenarioType(str, Enum):
    BASELINE = "baseline"
    GROWTH = "growth"
    OPTIMIZATION = "optimization"
    WORST_CASE = "worst_case"
    BEST_CASE = "best_case"

@dataclass
class ForecastCostLineItem:
    item_id: str
    category: ForecastCostCategory
    name: str
    monthly_cost: float = 0.0
    unit_cost: float = 0.0
    quantity: float = 0.0
    growth_rate_pct: float = 0.0  # monthly growth %
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass
class CostScenario:
    scenario_id: str
    name: str
    scenario_type: ScenarioType = ScenarioType.BASELINE
    line_items: List[str] = field(default_factory=list)  # item_ids
    forecast_months: int = 12
    created_at: str = ""
    assumptions: List[str] = field(default_factory=list)
    total_monthly: float = 0.0
    total_annual: float = 0.0


# ─── Edition Deployment Upgrade Factory Models ───────────────────────

@dataclass
class EditionProvisioningSpec:
    spec_id: str
    tenant_id: str
    edition_type: EditionType
    target_region: RegionId
    topology_tier: str = "standard"  # standard, ha, multi_region, distributed
    isolated_network: bool = True
    dedicated_kms: bool = False
    custom_domain: str = ""
    resource_quota: Dict[str, Any] = field(default_factory=dict)
    compliance_tags: List[str] = field(default_factory=list)
    created_at: str = ""

@dataclass
class EditionUpgradeRecord:
    record_id: str
    deployment_id: str
    from_version: str
    to_version: str
    phase: UpgradePhase = UpgradePhase.PRE_CHECK
    started_at: str = ""
    completed_at: str = ""
    success: bool = False
    error_message: str = ""
    rollback_performed: bool = False

@dataclass
class EditionUpgradeCampaign:
    campaign_id: str
    name: str
    target_version: str
    allowed_editions: List[EditionType] = field(default_factory=list)
    target_deployments: List[str] = field(default_factory=list)
    max_parallel: int = 5
    rollback_on_failure: bool = True
    records: Dict[str, EditionUpgradeRecord] = field(default_factory=dict)
    status: str = "pending"  # pending, in_progress, completed, failed, paused
    created_at: str = ""
    completed_at: str = ""


# ─── Global Observability Telemetry Models ───────────────────────────

class TelemetryMetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

class TelemetryAnomalySeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    WARNING = "warning"

@dataclass
class TelemetryDataPoint:
    point_id: str
    metric_name: str
    metric_type: TelemetryMetricType
    value: float
    timestamp: str = ""
    region: str = "global"
    tenant_id: str = ""
    service: str = ""
    tags: Dict[str, str] = field(default_factory=dict)

@dataclass
class TelemetryAnomalyAlert:
    alert_id: str
    metric_name: str
    observed_value: float
    baseline_value: float
    deviation_pct: float
    severity: TelemetryAnomalySeverity
    detected_at: str = ""
    region: str = ""
    service: str = ""
    acknowledged: bool = False
    resolution_notes: str = ""

@dataclass
class ObservabilityExportReport:
    report_id: str
    generated_at: str
    time_window_hours: int
    total_datapoints: int
    anomalies_detected: int
    services_monitored: List[str] = field(default_factory=list)
    regional_breakdown: Dict[str, int] = field(default_factory=dict)


# ─── SLSA Provenance Models ──────────────────────────────────────────

class ProvenanceAttestationStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    SIGNED = "signed"
    VERIFIED = "verified"
    TAMPERED = "tampered"
    REJECTED = "rejected"

@dataclass
class InTotoStatement:
    statement_id: str
    predicate_type: str = "https://slsa.dev/provenance/v1"
    subject_name: str = ""
    subject_sha256: str = ""
    slsa_level: SlsaLevel = SlsaLevel.LEVEL_1
    builder_id: str = "elmos-trusted-builder"
    build_type: str = "https://elmos.dev/build/v1"
    invocation_id: str = ""
    source_repo: str = ""
    source_commit: str = ""
    status: ProvenanceAttestationStatus = ProvenanceAttestationStatus.GENERATED
    signature: str = ""
    signer_key_id: str = ""
    created_at: str = ""
    verified_at: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SlsaVerificationResult:
    verification_id: str
    statement_id: str
    target_slsa_level: SlsaLevel
    achieved_slsa_level: SlsaLevel
    passed: bool = False
    tamper_detected: bool = False
    verified_at: str = ""
    verification_details: Dict[str, Any] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)


# ─── Knowledge Graph Ontology Models ─────────────────────────────────

class OntologyNodeType(str, Enum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    LIBRARY = "library"
    CODE_PATTERN = "code_pattern"
    MIGRATION_RULE = "migration_rule"
    FAILURE_SIGNATURE = "failure_signature"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    PROJECT = "project"

class OntologyEdgeType(str, Enum):
    DEPENDS_ON = "depends_on"
    MIGRATES_TO = "migrates_to"
    REPLACES = "replaces"
    COMPATIBLE_WITH = "compatible_with"
    MUTUALLY_EXCLUSIVE = "mutually_exclusive"
    CAUSES_ERROR = "causes_error"
    RESOLVED_BY = "resolved_by"
    EXTENDS = "extends"

@dataclass
class OntologyNode:
    node_id: str
    node_type: OntologyNodeType
    name: str
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    created_at: str = ""
    tags: List[str] = field(default_factory=list)

@dataclass
class OntologyEdge:
    edge_id: str
    source_id: str
    target_id: str
    edge_type: OntologyEdgeType
    weight: float = 1.0
    provenance_doc: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GraphQueryResult:
    query_id: str
    matched_nodes: List[OntologyNode] = field(default_factory=list)
    matched_edges: List[OntologyEdge] = field(default_factory=list)
    traversal_depth: int = 1
    execution_time_ms: float = 0.0


# ─── Agent Autonomy Levels Models ────────────────────────────────────

class AutonomyReviewDecision(str, Enum):
    PROMOTED = "promoted"
    DEMOTED = "demoted"
    MAINTAINED = "maintained"
    RESTRICTED = "restricted"

@dataclass
class AgentAutonomyProfile:
    agent_id: str
    agent_name: str
    current_tier: AgentAutonomyLevel = AgentAutonomyLevel.L0_MANUAL
    max_permitted_tier: AgentAutonomyLevel = AgentAutonomyLevel.L2_SUPERVISED
    evaluation_score: float = 0.0  # 0 - 100
    successful_runs: int = 0
    failed_runs: int = 0
    consecutive_successes: int = 0
    policy_violations: int = 0
    intervention_rate: float = 1.0  # human intervention frequency (0.0 - 1.0)
    allowed_actions: List[str] = field(default_factory=list)
    last_evaluated_at: str = ""

@dataclass
class AutonomyLevelTransition:
    transition_id: str
    agent_id: str
    from_tier: AgentAutonomyLevel
    to_tier: AgentAutonomyLevel
    decision: AutonomyReviewDecision
    reason: str
    reviewer: str
    evaluated_at: str = ""
    audit_receipt: str = ""

@dataclass
class AutonomyEnforcementGate:
    gate_id: str
    agent_id: str
    action_name: str
    required_level: AgentAutonomyLevel
    agent_level: AgentAutonomyLevel
    allowed: bool = False
    requires_human_approval: bool = False
    evaluated_at: str = ""


# ─── Public API Compatibility Models ─────────────────────────────────

class ApiChangeKind(str, Enum):
    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
    DEPRECATION = "deprecation"
    SECURITY_PATCH = "security_patch"

@dataclass
class ApiEndpointSpec:
    endpoint_id: str
    method: str  # GET, POST, PUT, DELETE
    path: str
    version: str
    parameters: Dict[str, str] = field(default_factory=dict)
    response_schema_hash: str = ""
    is_deprecated: bool = False
    deprecated_in: str = ""
    removal_in: str = ""

@dataclass
class ApiCompatibilityAssessment:
    assessment_id: str
    base_version: str
    target_version: str
    change_kind: ApiChangeKind
    endpoint_id: str
    breaking_changes: List[str] = field(default_factory=list)
    compatible: bool = True
    assessed_at: str = ""
    notes: str = ""

@dataclass
class SdkVersionMatrix:
    matrix_id: str
    platform_version: str
    language: str  # python, java, go, typescript, csharp
    sdk_version: str
    supported: bool = True
    min_platform_version: str = ""
    max_platform_version: str = ""


# ─── Operations Evidence Reporting Models ────────────────────────────

class EvidenceReportType(str, Enum):
    DAILY_OPS = "daily_ops"
    SLA_AUDIT = "sla_audit"
    INCIDENT_POSTMORTEM = "incident_postmortem"
    CUSTOMER_QUARTERLY = "customer_quarterly"

@dataclass
class OperationalEvidenceItem:
    item_id: str
    report_id: str
    evidence_type: str  # metric, log_snippet, incident_ref, runbook_exec
    source_system: str
    payload: Dict[str, Any] = field(default_factory=dict)
    collected_at: str = ""
    verified: bool = True
    provenance_hash: str = ""

@dataclass
class CustomerOperationsReport:
    report_id: str
    customer_id: str
    report_type: EvidenceReportType
    time_window_start: str
    time_window_end: str
    overall_uptime_pct: float = 99.9
    sla_violations_count: int = 0
    incident_count: int = 0
    evidence_items: List[str] = field(default_factory=list)  # item_ids
    generated_at: str = ""
    published: bool = False
    signoff_by: str = ""


# ─── Dependency SCA Governance Models ────────────────────────────────

class LicenseRiskLevel(str, Enum):
    PERMISSIVE = "permissive"
    WEAK_COPYLEFT = "weak_copyleft"
    STRONG_COPYLEFT = "strong_copyleft"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"

@dataclass
class ScaDependencyRecord:
    dependency_id: str
    package_name: str
    version: str
    ecosystem: str  # npm, pypi, maven, nuget, golang
    license_spdx: str = "UNKNOWN"
    license_risk: LicenseRiskLevel = LicenseRiskLevel.UNKNOWN
    vulnerabilities: List[str] = field(default_factory=list)  # cve_ids
    direct: bool = True
    reachable: bool = True
    is_quarantined: bool = False

@dataclass
class LicenseComplianceVerdict:
    verdict_id: str
    project_id: str
    passed: bool = True
    disallowed_licenses_found: List[str] = field(default_factory=list)
    quarantined_packages: List[str] = field(default_factory=list)
    reviewed_at: str = ""
    reviewer: str = ""

@dataclass
class ScaGovernanceSummary:
    summary_id: str
    project_id: str
    total_dependencies: int = 0
    direct_dependencies: int = 0
    transitive_dependencies: int = 0
    vulnerable_dependencies: int = 0
    high_risk_licenses_count: int = 0
    overall_compliant: bool = True


# ─── Similar Project Retrieval Models ────────────────────────────────

@dataclass
class ProjectFingerprint:
    project_id: str
    project_name: str
    source_language: str
    source_framework: str
    target_language: str
    target_framework: str
    loc_count: int = 0
    module_count: int = 0
    architectural_pattern: str = ""  # monolith, microservices, modular_monolith
    tags: List[str] = field(default_factory=list)
    feature_vector: List[float] = field(default_factory=list)

@dataclass
class SimilarityMatchResult:
    matched_project_id: str
    similarity_score: float  # 0.0 - 1.0
    shared_tags: List[str] = field(default_factory=list)
    recommended_recipes: List[str] = field(default_factory=list)
    estimated_duration_days: float = 0.0

@dataclass
class TargetStackRecommendation:
    recommendation_id: str
    source_framework: str
    recommended_target_framework: str
    confidence_score: float = 0.0
    rationale: str = ""
    alternatives: List[str] = field(default_factory=list)


# ─── Route Breadth Certification Models ──────────────────────────────

class RouteCertificationStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    CANDIDATE = "candidate"
    CERTIFIED = "certified"
    PROVISIONAL = "provisional"
    DEPRECATED = "deprecated"

@dataclass
class MigrationRouteCell:
    route_id: str
    source_language: str
    target_language: str
    source_framework: str = ""
    target_framework: str = ""
    status: RouteCertificationStatus = RouteCertificationStatus.NOT_EVALUATED
    test_coverage_pct: float = 0.0
    syntax_fidelity_score: float = 0.0
    semantic_equivalence_score: float = 0.0
    certified_at: str = ""
    certifier: str = ""
    known_limitations: List[str] = field(default_factory=list)

@dataclass
class RouteBreadthMatrixReport:
    report_id: str
    total_routes: int = 0
    certified_routes_count: int = 0
    candidate_routes_count: int = 0
    provisional_routes_count: int = 0
    coverage_breadth_pct: float = 0.0
    language_pairs_supported: List[str] = field(default_factory=list)
    generated_at: str = ""


# ─── Runner Version Compatibility Models (B38) ──────────────────────

class RunnerProtocolVersion(str, Enum):
    V1_LEGACY = "1.0.0"
    V2_STABLE = "2.0.0"
    V2_1_STREAMING = "2.1.0"
    V3_HERMETIC = "3.0.0"
    V3_1_ASYNC = "3.1.0"

class RunnerStatus(str, Enum):
    ACTIVE = "active"
    DRAINING = "draining"
    DRAINED = "drained"
    DEPRECATED = "deprecated"
    INCOMPATIBLE = "incompatible"
    OFFLINE = "offline"

class RunnerCapability(str, Enum):
    DOCKER_SANDBOX = "docker_sandbox"
    EBPF_TRACING = "ebpf_tracing"
    AIRGAP_BUNDLE = "airgap_bundle"
    GPU_PASSTHROUGH = "gpu_passthrough"
    DISTRIBUTED_CACHE = "distributed_cache"
    WASM_RUNTIME = "wasm_runtime"
    HSM_SIGNING = "hsm_signing"

@dataclass
class RunnerRegistration:
    runner_id: str
    hostname: str
    runner_version: str  # e.g. "3.1.0"
    protocol_version: str  # e.g. "3.0.0"
    supported_capabilities: List[RunnerCapability] = field(default_factory=list)
    status: RunnerStatus = RunnerStatus.ACTIVE
    active_jobs_count: int = 0
    last_heartbeat: str = ""
    drain_requested_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CompatibilityCheckResult:
    compatible: bool
    control_plane_version: str
    runner_version: str
    version_relation: str  # "exact", "n_minus_1", "n_plus_1", "incompatible_major", "too_old", "too_new"
    unsupported_capabilities: List[str] = field(default_factory=list)
    upgrade_required: bool = False
    details: str = ""

@dataclass
class RunnerDrainUpgradePlan:
    plan_id: str
    runner_id: str
    current_version: str
    target_version: str
    drain_timeout_seconds: int = 300
    status: str = "pending"  # pending, draining, ready_for_upgrade, completed, aborted
    created_at: str = ""
    completed_at: str = ""


# ─── Platform Cost Anomaly Monitoring Models (B39) ──────────────────

class CostMetricType(str, Enum):
    LLM_TOKENS = "llm_tokens"
    COMPUTE_CPU_HOURS = "compute_cpu_hours"
    MEMORY_GB_HOURS = "memory_gb_hours"
    STORAGE_GB_MONTHS = "storage_gb_months"
    NETWORK_EGRESS_GB = "network_egress_gb"
    CACHE_OPERATIONS = "cache_operations"

class CostAnomalySeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class CostMitigationAction(str, Enum):
    NOTIFY_ONLY = "notify_only"
    ALERT_ONCALL = "alert_oncall"
    THROTTLE_RATE_LIMIT = "throttle_rate_limit"
    TRIP_CIRCUIT_BREAKER = "trip_circuit_breaker"
    SUSPEND_WORKLOAD = "suspend_workload"

@dataclass
class CostDataPoint:
    point_id: str
    tenant_id: str
    metric_type: CostMetricType
    timestamp: str
    amount_usd: float
    quantity: float
    unit: str

@dataclass
class CostAnomalyAlert:
    alert_id: str
    tenant_id: str
    metric_type: CostMetricType
    current_amount_usd: float
    baseline_mean_usd: float
    baseline_std_usd: float
    z_score: float
    severity: CostAnomalySeverity
    recommended_action: CostMitigationAction
    triggered_at: str
    anomaly_reason: str = ""
    is_resolved: bool = False
    resolved_at: str = ""

@dataclass
class CostThrottlePolicy:
    policy_id: str
    tenant_id: str
    metric_type: CostMetricType
    hourly_spend_cap_usd: float
    daily_spend_cap_usd: float
    current_hourly_spend_usd: float = 0.0
    current_daily_spend_usd: float = 0.0
    circuit_breaker_tripped: bool = False


# ─── Artifact Container Signing Models (B40) ────────────────────────

class SignatureAlgorithm(str, Enum):
    RS256 = "RS256"
    ES256 = "ES256"
    ED25519 = "ED25519"
    HMAC_SHA256 = "HMAC_SHA256"

class ArtifactKind(str, Enum):
    OCI_CONTAINER_IMAGE = "oci_container_image"
    MIGRATION_RECIPE_BUNDLE = "migration_recipe_bundle"
    RUNNER_BINARY = "runner_binary"
    MODEL_WEIGHT_BUNDLE = "model_weight_bundle"
    PROVENANCE_ATTESTATION = "provenance_attestation"

@dataclass
class ArtifactSignatureRecord:
    signature_id: str
    key_id: str
    signer_identity: str
    algorithm: SignatureAlgorithm
    signature_base64: str
    signed_digest: str  # sha256:...
    timestamp: str
    certificate_pem: str = ""
    in_toto_statement_digest: str = ""
    is_revoked: bool = False

@dataclass
class SignedArtifactManifest:
    artifact_id: str
    artifact_kind: ArtifactKind
    artifact_digest: str  # sha256:...
    artifact_size_bytes: int
    signatures: List[ArtifactSignatureRecord] = field(default_factory=list)
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SigningAdmissionVerdict:
    verdict_id: str
    artifact_id: str
    artifact_digest: str
    admitted: bool = True
    required_signers_satisfied: bool = True
    signature_valid: bool = True
    not_revoked: bool = True
    rejection_reasons: List[str] = field(default_factory=list)
    evaluated_at: str = ""


# ─── Compatibility Test Matrix Models (B43) ─────────────────────────

class MatrixCellStatus(str, Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    DEGRADED = "degraded"
    UNTESTED = "untested"
    DEPRECATED = "deprecated"

@dataclass
class CompatibilityCell:
    cell_id: str
    language_runtime: str  # e.g. "java@21"
    framework: str         # e.g. "spring-boot@3.2.0"
    database: str          # e.g. "postgresql@16"
    cloud_profile: str     # e.g. "aws-standard"
    status: MatrixCellStatus = MatrixCellStatus.UNTESTED
    broken_features: List[str] = field(default_factory=list)
    test_run_id: str = ""
    latency_p95_ms: float = 0.0
    evaluated_at: str = ""

@dataclass
class CompatibilityTestMatrixReport:
    report_id: str
    target_profile: str
    total_cells: int = 0
    compatible_cells_count: int = 0
    incompatible_cells_count: int = 0
    degraded_cells_count: int = 0
    untested_cells_count: int = 0
    compatibility_score_pct: float = 0.0
    breaking_pairwise_combinations: List[str] = field(default_factory=list)
    lts_ready: bool = True
    generated_at: str = ""


# ─── Usage Billing Reconciliation Models (B44) ──────────────────────

class BillingItemType(str, Enum):
    TOKEN_INFERENCE = "token_inference"
    RUNNER_EXECUTION = "runner_execution"
    STORAGE_PERSISTENCE = "storage_persistence"
    RECIPE_USAGE = "recipe_usage"
    PLATFORM_LICENSE = "platform_license"

class DiscrepancyType(str, Enum):
    UNDERBILLING = "underbilling"
    OVERBILLING = "overbilling"
    UNMETERED_USAGE = "unmetered_usage"
    DUPLICATE_INVOICE_LINE = "duplicate_invoice_line"
    ROUNDING_ERROR = "rounding_error"

@dataclass
class MeteredUsageRecord:
    meter_id: str
    tenant_id: str
    item_type: BillingItemType
    quantity: float
    unit_price_usd: float
    subtotal_usd: float
    timestamp: str
    hash_prev: str = ""
    hash_curr: str = ""

@dataclass
class InvoiceLineItemRecord:
    line_id: str
    invoice_id: str
    item_type: BillingItemType
    quantity: float
    unit_price_usd: float
    total_billed_usd: float

@dataclass
class BillingDiscrepancy:
    discrepancy_id: str
    tenant_id: str
    item_type: BillingItemType
    metered_amount_usd: float
    invoiced_amount_usd: float
    variance_usd: float
    discrepancy_type: DiscrepancyType
    resolved: bool = False
    adjustment_credit_usd: float = 0.0

@dataclass
class BillingReconciliationStatement:
    statement_id: str
    tenant_id: str
    period_start: str
    period_end: str
    total_metered_usd: float = 0.0
    total_invoiced_usd: float = 0.0
    variance_total_usd: float = 0.0
    discrepancies: List[BillingDiscrepancy] = field(default_factory=list)
    balanced: bool = True
    tolerance_threshold_usd: float = 0.01
    audit_hash: str = ""
    reconciled_at: str = ""


# ─── Multiregion Active-Active Edition Models (B38) ──────────────────

class SyncReplicationState(str, Enum):
    IN_SYNC = "in_sync"
    SYNCING = "syncing"
    DEGRADED = "degraded"
    SPLIT_BRAIN = "split_brain"
    DESYNCHRONIZED = "desynchronized"

class QuorumStrategy(str, Enum):
    MAJORITY = "majority"
    WEIGHTED = "weighted"
    STRICT_LOCAL = "strict_local"
    OBSERVER_ASSISTED = "observer_assisted"

@dataclass
class ActiveActiveRegionNode:
    region_id: str
    cluster_name: str
    endpoint: str
    weight: float = 1.0
    is_leader: bool = False
    sync_state: SyncReplicationState = SyncReplicationState.IN_SYNC
    latency_p99_ms: float = 20.0
    replication_lag_bytes: int = 0
    last_sync_time: str = ""

@dataclass
class ActiveActiveTopologyPlan:
    plan_id: str
    edition_id: str
    quorum_strategy: QuorumStrategy = QuorumStrategy.MAJORITY
    nodes: Dict[str, ActiveActiveRegionNode] = field(default_factory=dict)
    max_tolerable_lag_ms: float = 100.0
    split_brain_detected: bool = False
    created_at: str = ""


# ─── Global Operations Gate Models (B39) ────────────────────────────

class GateCheckCategory(str, Enum):
    SLO_HEALTH = "slo_health"
    CHANGE_FREEZE = "change_freeze"
    ONCALL_ROSTER = "oncall_roster"
    PENDING_INCIDENTS = "pending_incidents"
    DR_COMPLIANCE = "dr_compliance"
    CAPACITY_MARGIN = "capacity_margin"

class GateVerdict(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CONDITIONAL_APPROVAL = "conditional_approval"
    OVERRIDE_APPROVED = "override_approved"

@dataclass
class OperationsGateCheck:
    check_id: str
    category: GateCheckCategory
    name: str
    passed: bool = False
    current_value: float = 0.0
    threshold_value: float = 0.0
    details: str = ""
    blocking: bool = True

@dataclass
class GlobalOperationsGateDecision:
    decision_id: str
    release_id: str
    target_environment: str
    overall_verdict: GateVerdict = GateVerdict.REJECTED
    checks: List[OperationsGateCheck] = field(default_factory=list)
    approved_by: str = ""
    emergency_override: bool = False
    override_reason: str = ""
    timestamp: str = ""


# ─── Supply Chain Compliance Factory Models (B40) ───────────────────

class ComplianceStandard(str, Enum):
    SLSA_LEVEL_3 = "slsa_level_3"
    NIST_SP_800_218 = "nist_sp_800_218"
    CIS_BENCHMARK = "cis_benchmark"
    OPENSSF_SCORECARD = "openssf_scorecard"
    SOC2_TYPE2 = "soc2_type2"

class PolicyEnforcementMode(str, Enum):
    AUDIT_ONLY = "audit_only"
    WARN = "warn"
    BLOCK = "block"
    STRICT = "strict"

@dataclass
class SupplyChainComplianceRule:
    rule_id: str
    standard: ComplianceStandard
    name: str
    description: str
    enforcement_mode: PolicyEnforcementMode = PolicyEnforcementMode.BLOCK
    required_attestations: List[str] = field(default_factory=list)
    max_cve_severity: str = "medium"
    enabled: bool = True

@dataclass
class ComplianceEvaluationReport:
    report_id: str
    artifact_id: str
    target_standard: ComplianceStandard
    passed: bool = False
    score_pct: float = 0.0
    satisfied_rules: List[str] = field(default_factory=list)
    violated_rules: List[str] = field(default_factory=list)
    remediations: List[str] = field(default_factory=list)
    evaluated_at: str = ""


# ─── Target Stack Recommendation Extensions (B41) ───────────────────

class StackArchitectureTier(str, Enum):
    MONOLITH = "monolith"
    MODULAR_MONOLITH = "modular_monolith"
    MICROSERVICES = "microservices"
    SERVERLESS = "serverless"
    EDGE = "edge"

class ModernizationStrategy(str, Enum):
    REHOST = "rehost"
    REPLATFORM = "replatform"
    REFACTOR = "refactor"
    REARCHITECT = "rearchitect"
    RETIRE = "retire"

@dataclass
class StackFeasibilityScore:
    score_id: str
    source_tech: str
    target_tech: str
    syntactic_overlap_pct: float = 0.0
    library_parity_pct: float = 0.0
    complexity_discount_factor: float = 1.0
    total_score: float = 0.0

@dataclass
class ComprehensiveStackRecommendation:
    recommendation_id: str
    project_name: str
    source_stack: List[str] = field(default_factory=list)
    recommended_target: Optional[TargetStackRecommendation] = None
    architecture_tier: StackArchitectureTier = StackArchitectureTier.MODULAR_MONOLITH
    strategy: ModernizationStrategy = ModernizationStrategy.REFACTOR
    estimated_effort_months: float = 3.0
    risk_factors: List[str] = field(default_factory=list)
    evaluated_at: str = ""


# ─── Customer Value Certification Models (B45) ──────────────────────

class ValueMetricCategory(str, Enum):
    TCO_REDUCTION = "tco_reduction"
    LATENCY_IMPROVEMENT = "latency_improvement"
    CODE_QUALITY_SCORE = "code_quality_score"
    LICENSING_SAVINGS = "licensing_savings"
    DEVELOPER_VELOCITY = "developer_velocity"

class MilestoneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ACHIEVED = "achieved"
    MISSED = "missed"
    WAIVED = "waived"

@dataclass
class ValueMilestone:
    milestone_id: str
    category: ValueMetricCategory
    name: str
    baseline_value: float = 0.0
    target_value: float = 0.0
    actual_value: float = 0.0
    achieved: bool = False
    unit: str = ""
    status: MilestoneStatus = MilestoneStatus.PENDING

@dataclass
class CustomerValueCertificate:
    certificate_id: str
    customer_id: str
    project_name: str
    contract_reference: str
    certified_at: str = ""
    certifier: str = ""
    milestones: List[ValueMilestone] = field(default_factory=list)
    overall_roi_pct: float = 0.0
    customer_signoff: bool = False
    customer_signoff_date: str = ""
    notes: str = ""


# ─── Private Sovereign Cloud Edition Models (B38) ───────────────────

class SovereignJurisdiction(str, Enum):
    EU_GDPR = "eu_gdpr"
    US_FEDRAMP = "us_fedramp"
    CN_MLPS = "cn_mlps"
    SG_MAS = "sg_mas"
    GLOBAL_STRICT = "global_strict"

class AirgapEnclaveType(str, Enum):
    HARDWARE_AIRGAP = "hardware_airgap"
    LOGICAL_ENCLAVE = "logical_enclave"
    BASTION_FEDERATED = "bastion_federated"
    AIRGAP_BUNDLE = "airgap_bundle"

@dataclass
class SovereignEnclaveSpec:
    enclave_id: str
    edition_id: str
    jurisdiction: SovereignJurisdiction
    enclave_type: AirgapEnclaveType
    cryptographic_boundary: str
    local_kms_endpoint: str
    allow_egress: bool = False
    registered_at: str = ""

@dataclass
class SovereignAuditReceipt:
    receipt_id: str
    enclave_id: str
    data_residency_verified: bool
    egress_attempt_blocked_count: int
    signature_digest: str
    generated_at: str


# ─── Customer Status Communication Models (B39) ─────────────────────

class IncidentImpactLevel(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"

class NotificationChannel(str, Enum):
    STATUS_PAGE = "status_page"
    WEBHOOK = "webhook"
    EMAIL_PAGER = "email_pager"
    SLACK_COMMUNITY = "slack_community"
    SMS = "sms"

@dataclass
class StatusCommunicationMessage:
    message_id: str
    incident_id: str
    impact_level: IncidentImpactLevel
    title: str
    body: str
    affected_components: List[str] = field(default_factory=list)
    channels: List[NotificationChannel] = field(default_factory=list)
    posted_at: str = ""
    posted_by: str = ""

@dataclass
class CustomerStatusReport:
    report_id: str
    active_incidents_count: int = 0
    current_global_status: IncidentImpactLevel = IncidentImpactLevel.NONE
    past_30_days_uptime_pct: float = 99.99
    messages: List[StatusCommunicationMessage] = field(default_factory=list)


# ─── Compliance Control Crosswalk Models (B40) ──────────────────────

class CrosswalkMappingType(str, Enum):
    EXACT_EQUIVALENT = "exact_equivalent"
    SUPERSET = "superset"
    SUBSET = "subset"
    PARTIAL_OVERLAP = "partial_overlap"

@dataclass
class ControlCrosswalkRecord:
    mapping_id: str
    source_framework: ComplianceFramework
    source_control_id: str
    target_framework: ComplianceFramework
    target_control_id: str
    mapping_type: CrosswalkMappingType
    rationale: str = ""

@dataclass
class CrosswalkGapAnalysis:
    analysis_id: str
    from_framework: ComplianceFramework
    to_framework: ComplianceFramework
    covered_controls_count: int = 0
    gap_controls: List[str] = field(default_factory=list)
    crosswalk_coverage_pct: float = 0.0


# ─── Effort Duration Cost Prediction Models (B41) ───────────────────

class MigrationComplexityClass(str, Enum):
    TRIVIAL = "trivial"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"
    UNKNOWN = "unknown"

@dataclass
class RepoComplexityVector:
    vector_id: str
    kloc: float
    ast_depth: int
    external_dependency_count: int
    database_routines_count: int
    business_rules_count: int

@dataclass
class EffortPredictionResult:
    prediction_id: str
    repo_id: str
    complexity_class: MigrationComplexityClass
    predicted_person_months: float
    predicted_cost_usd: float
    confidence_interval_low: float
    confidence_interval_high: float
    generated_at: str = ""


# ─── Mature Product Evidence Pack Models (B45) ──────────────────────

class EvidenceBundleStatus(str, Enum):
    DRAFT = "draft"
    SEALED = "sealed"
    ATTESTED = "attested"
    EXPIRED = "expired"
    TAMPERED = "tampered"

@dataclass
class EvidenceArtifactEntry:
    entry_id: str
    category: str
    artifact_sha256: str
    size_bytes: int
    attestation_signer: str = ""
    verified: bool = True

@dataclass
class ComprehensiveEvidencePack:
    pack_id: str
    product_name: str
    version: str
    status: EvidenceBundleStatus = EvidenceBundleStatus.DRAFT
    merkle_root_sha256: str = ""
    total_artifacts: int = 0
    artifacts: List[EvidenceArtifactEntry] = field(default_factory=list)
    release_gate_passed: bool = False
    sealed_at: str = ""
    certified_by: str = ""


# ─── Recipe, Pack and Extension Upgrade Models (B38) ────────────────

class ArtifactPackageType(str, Enum):
    RECIPE = "recipe"
    PACK = "pack"
    EXTENSION = "extension"

class PackageUpgradeStrategy(str, Enum):
    ROLLING = "rolling"
    ATOMIC = "atomic"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"

class PackageUpgradeStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"

@dataclass
class PackageDependency:
    name: str
    version_constraint: str
    package_type: ArtifactPackageType = ArtifactPackageType.PACK
    mandatory: bool = True

@dataclass
class PackageArtifact:
    package_id: str
    name: str
    version: str
    package_type: ArtifactPackageType
    sha256: str
    dependencies: List[PackageDependency] = field(default_factory=list)
    supported_editions: List[str] = field(default_factory=list)
    deprecated: bool = False
    created_at: str = ""

@dataclass
class PackageUpgradePlan:
    plan_id: str
    package_name: str
    package_type: ArtifactPackageType
    from_version: str
    to_version: str
    strategy: PackageUpgradeStrategy = PackageUpgradeStrategy.ROLLING
    status: PackageUpgradeStatus = PackageUpgradeStatus.PENDING
    target_deployments: List[str] = field(default_factory=list)
    applied_deployments: List[str] = field(default_factory=list)
    rollback_on_failure: bool = True
    error_message: str = ""
    started_at: str = ""
    completed_at: str = ""

# ─── Enterprise Support SLA Models (B39) ────────────────────────────

class SupportTierLevel(str, Enum):
    COMMUNITY = "community"
    STANDARD = "standard"
    PREMIER = "premier"
    MISSION_CRITICAL = "mission_critical"

class TicketPriority(str, Enum):
    P1_CRITICAL = "p1_critical"
    P2_HIGH = "p2_high"
    P3_MEDIUM = "p3_medium"
    P4_LOW = "p4_low"

class TicketStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

@dataclass
class SupportSlaTarget:
    tier: SupportTierLevel
    priority: TicketPriority
    response_time_minutes: int
    resolution_time_minutes: int
    twenty_four_seven: bool = True
    dedicated_tam: bool = False

@dataclass
class SupportTicket:
    ticket_id: str
    customer_id: str
    support_tier: SupportTierLevel
    priority: TicketPriority
    status: TicketStatus = TicketStatus.OPEN
    created_at: str = ""
    first_response_at: str = ""
    resolved_at: str = ""
    assigned_engineer: str = ""
    response_breached: bool = False
    resolution_breached: bool = False
    service_credit_eligible: bool = False
    summary: str = ""

# ─── Independent Security Assessment Models (B40) ───────────────────

class AssessmentType(str, Enum):
    PENETRATION_TEST = "penetration_test"
    THIRD_PARTY_CODE_AUDIT = "third_party_code_audit"
    RED_TEAM_ENGAGEMENT = "red_team_engagement"
    CRYPTO_REVIEW = "crypto_review"

class AssessorType(str, Enum):
    EXTERNAL_ACCREDITED = "external_accredited"
    REGULATORY_BODY = "regulatory_body"
    INDEPENDENT_AUDITOR = "independent_auditor"

class AssessmentStatus(str, Enum):
    SCOPING = "scoping"
    FIELDWORK = "fieldwork"
    REPORT_DRAFT = "report_draft"
    REMEDIATION = "remediation"
    CERTIFIED_CLOSED = "certified_closed"

@dataclass
class IndependentAuditFinding:
    finding_id: str
    assessment_id: str
    title: str
    severity: str  # critical, high, medium, low, info
    cwe_id: str = ""
    remediation_notes: str = ""
    verified_closed: bool = False
    closed_at: str = ""
    verified_by: str = ""

@dataclass
class IndependentAssessmentRecord:
    assessment_id: str
    target_release: str
    assessment_type: AssessmentType
    assessor_firm: str
    assessor_type: AssessorType = AssessorType.EXTERNAL_ACCREDITED
    status: AssessmentStatus = AssessmentStatus.SCOPING
    findings: List[IndependentAuditFinding] = field(default_factory=list)
    total_findings: int = 0
    open_blockers: int = 0
    started_at: str = ""
    completed_at: str = ""
    sign_off_attestation: str = ""
    passed_gate: bool = False

# ─── Migration Run Ingestion Models (B41) ───────────────────────────

class IngestedAssetType(str, Enum):
    RULE = "rule"
    PATTERN = "pattern"
    ERROR_SOLUTION = "error_solution"
    FIXTURE = "fixture"
    REGRESSION_TEST = "regression_test"

class IngestionQualityScore(str, Enum):
    VERIFIED = "verified"
    HIGH = "high"
    MEDIUM = "medium"
    REJECTED = "rejected"

@dataclass
class RunIngestionArtifact:
    artifact_id: str
    run_id: str
    asset_type: IngestedAssetType
    source_language: str
    target_language: str
    content: str
    quality: IngestionQualityScore = IngestionQualityScore.HIGH
    confidence_score: float = 0.8
    approved_by: str = ""
    ingested_at: str = ""
    provenance_run_id: str = ""

@dataclass
class MigrationRunSummary:
    run_id: str
    project_name: str
    source_tech: str
    target_tech: str
    success: bool
    files_migrated: int = 0
    transformations_applied: int = 0
    errors_encountered: List[str] = field(default_factory=list)
    completed_at: str = ""

# ─── Mature Release Readiness Models (B45) ──────────────────────────

class ReleasePillar(str, Enum):
    FUNCTIONAL = "functional"
    SECURITY = "security"
    SRE_RELIABILITY = "sre_reliability"
    PERFORMANCE = "performance"
    COMPLIANCE = "compliance"
    CUSTOMER_OUTCOME = "customer_outcome"
    ECONOMICS = "economics"

class PillarStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_REVIEW = "in_review"
    PASSED = "passed"
    BLOCKED = "blocked"
    WAIVED = "waived"

@dataclass
class PillarEvaluation:
    pillar: ReleasePillar
    status: PillarStatus = PillarStatus.NOT_STARTED
    score: float = 0.0
    blocking_issues: List[str] = field(default_factory=list)
    lead_owner: str = ""
    evidence_hashes: List[str] = field(default_factory=list)
    notes: str = ""

@dataclass
class MatureReleaseReadinessRecord:
    review_id: str
    target_release: str
    pillars: Dict[str, PillarEvaluation] = field(default_factory=dict)
    overall_score: float = 0.0
    ready_for_general_availability: bool = False
    sign_off_director: str = ""
    reviewed_at: str = ""


# ─── Edition Responsibility Matrix Models (B38) ────────────────────

class ResponsibilityArea(str, Enum):
    INFRASTRUCTURE_HARDWARE = "infrastructure_hardware"
    OS_CONTAINER_RUNTIME = "os_container_runtime"
    PLATFORM_SOFTWARE = "platform_software"
    SECURITY_PATCHING = "security_patching"
    BACKUP_AND_RESTORE = "backup_and_restore"
    DISASTER_RECOVERY = "disaster_recovery"
    DATA_PRIVACY_RESIDENCY = "data_privacy_residency"
    UPGRADE_EXECUTION = "upgrade_execution"

class ResponsibleParty(str, Enum):
    PLATFORM_PROVIDER = "platform_provider"
    CUSTOMER = "customer"
    SHARED = "shared"

@dataclass
class EditionResponsibilityRecord:
    area: ResponsibilityArea
    party: ResponsibleParty
    sla_guaranteed: bool = True
    notes: str = ""

@dataclass
class EditionResponsibilityMatrix:
    matrix_id: str
    edition: EditionType
    responsibilities: Dict[str, EditionResponsibilityRecord] = field(default_factory=dict)
    last_reviewed: str = ""
    approved_by: str = ""

# ─── Production Readiness Review Models (B39) ───────────────────────

class PrrCategory(str, Enum):
    MONITORING_ALERTS = "monitoring_alerts"
    CAPACITY_SCALING = "capacity_scaling"
    DISASTER_RECOVERY = "disaster_recovery"
    SECURITY_COMPLIANCE = "security_compliance"
    INCIDENT_RUNBOOKS = "incident_runbooks"
    DEPLOYMENT_ROLLBACK = "deployment_rollback"
    DEPENDENCY_RESILIENCE = "dependency_resilience"

class PrrItemStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    WAIVED = "waived"

@dataclass
class PrrChecklistItem:
    item_id: str
    category: PrrCategory
    title: str
    status: PrrItemStatus = PrrItemStatus.FAIL
    owner: str = ""
    remediation: str = ""
    blocking: bool = True

@dataclass
class ProductionReadinessReviewRecord:
    review_id: str
    service_name: str
    target_environment: str
    checklist: List[PrrChecklistItem] = field(default_factory=list)
    approved: bool = False
    readiness_score: float = 0.0
    sign_off_sre: str = ""
    reviewed_at: str = ""

# ─── Customer Audit Evidence Models (B40) ───────────────────────────

class AuditEvidenceType(str, Enum):
    ACCESS_LOGS = "access_logs"
    VULNERABILITY_SCANS = "vulnerability_scans"
    CHANGE_RECORDS = "change_records"
    ENCRYPTION_CERTS = "encryption_certs"
    BACKUP_LOGS = "backup_logs"
    INCIDENT_REPORTS = "incident_reports"

@dataclass
class CustomerAuditArtifact:
    artifact_id: str
    evidence_type: AuditEvidenceType
    title: str
    checksum_sha256: str
    collected_at: str = ""
    file_size_bytes: int = 0

@dataclass
class CustomerAuditEvidencePackage:
    package_id: str
    customer_id: str
    framework: ComplianceFramework
    artifacts: List[CustomerAuditArtifact] = field(default_factory=list)
    status: str = "preparing"
    merkle_root: str = ""
    download_expiry: str = ""
    generated_at: str = ""

# ─── Knowledge Confidence and Provenance Models (B41) ────────────────

class KnowledgeConfidenceLevel(str, Enum):
    UNVERIFIED = "unverified"
    EXPERIMENTAL = "experimental"
    PRODUCTION_PROVEN = "production_proven"
    GOLD_CERTIFIED = "gold_certified"
    DEPRECATED = "deprecated"

@dataclass
class EvidenceProvenanceRecord:
    provenance_id: str
    knowledge_id: str
    source_run_id: str
    author: str
    empirical_success_count: int = 0
    empirical_failure_count: int = 0
    confidence_score: float = 0.5
    confidence_level: KnowledgeConfidenceLevel = KnowledgeConfidenceLevel.EXPERIMENTAL
    last_empirically_verified: str = ""
    citation_urls: List[str] = field(default_factory=list)

@dataclass
class KnowledgeDecayPolicy:
    policy_id: str
    half_life_days: int = 90
    min_confidence_floor: float = 0.2

# ─── Design Partner Reference Validation Models (B45) ───────────────

class DesignPartnerPhase(str, Enum):
    ONBOARDING = "onboarding"
    PILOT_EXECUTION = "pilot_execution"
    UAT_VALIDATION = "uat_validation"
    ACCEPTANCE_SIGNED = "acceptance_signed"
    REFERENCE_PUBLISHED = "reference_published"

@dataclass
class PartnerAcceptanceCriteria:
    criterion_id: str
    description: str
    target_metric: str
    actual_metric: str = ""
    passed: bool = False

@dataclass
class DesignPartnerValidationStudy:
    study_id: str
    partner_name: str
    industry: str
    source_platform: str
    target_platform: str
    phase: DesignPartnerPhase = DesignPartnerPhase.ONBOARDING
    criteria: List[PartnerAcceptanceCriteria] = field(default_factory=list)
    roi_savings_pct: float = 0.0
    testimonial_quote: str = ""
    formal_acceptance_signed: bool = False
    lead_sponsor: str = ""
    signed_at: str = ""


# ─── Multitenant SaaS Edition Models (B38) ──────────────────────────

class SaasTenantTier(str, Enum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

class TenantIsolationMode(str, Enum):
    POOLED = "pooled"
    SILOED = "siloed"
    HYBRID = "hybrid"

@dataclass
class SaasTenantConfig:
    tenant_id: str
    name: str
    tier: SaasTenantTier = SaasTenantTier.STANDARD
    isolation_mode: TenantIsolationMode = TenantIsolationMode.POOLED
    storage_quota_gb: float = 50.0
    rps_limit: int = 100
    enabled_features: List[str] = field(default_factory=list)
    custom_domain: str = ""
    is_suspended: bool = False
    created_at: str = ""

@dataclass
class SaasClusterResourceQuota:
    cluster_id: str
    max_tenants: int = 500
    allocated_storage_gb: float = 0.0
    total_storage_gb: float = 10000.0
    active_tenant_count: int = 0


# ─── On-Call Follow-The-Sun Models (B39) ─────────────────────────────

class SunRegion(str, Enum):
    APAC = "apac"
    EMEA = "emea"
    AMER = "amer"

class HandoverStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MISSED = "missed"

@dataclass
class HandoverBriefing:
    handover_id: str
    outgoing_region: SunRegion
    incoming_region: SunRegion
    outgoing_engineer: str
    incoming_engineer: str
    active_incidents: List[str] = field(default_factory=list)
    watch_items: List[str] = field(default_factory=list)
    status: HandoverStatus = HandoverStatus.SCHEDULED
    handover_time: str = ""
    acknowledged_at: str = ""
    notes: str = ""

@dataclass
class FollowTheSunSchedule:
    schedule_id: str
    date: str
    region_shifts: Dict[str, str] = field(default_factory=dict)


# ─── Runner Update Supply Chain Models (B40) ─────────────────────────

class RunnerChannel(str, Enum):
    CANARY = "canary"
    STABLE = "stable"
    LTS = "lts"

class RunnerUpdateStatus(str, Enum):
    DRAFT = "draft"
    SIGNED = "signed"
    STAGED = "staged"
    DEPLOYED = "deployed"
    REVOKED = "revoked"

@dataclass
class RunnerReleasePackage:
    release_id: str
    version: str
    channel: RunnerChannel
    binary_digest_sha256: str
    signature: str = ""
    cosign_attestation_ref: str = ""
    status: RunnerUpdateStatus = RunnerUpdateStatus.DRAFT
    released_at: str = ""
    minimum_agent_version: str = "1.0.0"
    revocation_reason: str = ""

@dataclass
class RunnerNodeFleetStatus:
    node_id: str
    current_version: str
    target_version: str
    update_in_progress: bool = False
    last_heartbeat: str = ""
    update_failed: bool = False


# ─── Automation Buildgreen Prediction Models (B41) ───────────────────

class BuildPredictionVerdict(str, Enum):
    HIGH_CONFIDENCE_GREEN = "high_confidence_green"
    PROBABLE_GREEN = "probable_green"
    RISKY_RED = "risky_red"
    HIGH_RISK_RED = "high_risk_red"

@dataclass
class CommitRiskFactor:
    factor_name: str
    weight: float
    score: float
    detail: str = ""

@dataclass
class BuildgreenPrediction:
    prediction_id: str
    commit_sha: str
    branch: str
    author: str
    predicted_verdict: BuildPredictionVerdict
    green_probability: float
    risk_factors: List[CommitRiskFactor] = field(default_factory=list)
    actual_build_passed: Optional[bool] = None
    predicted_at: str = ""


# ─── Ecosystem Certification Models (B45) ────────────────────────────

class EcosystemPartnerTier(str, Enum):
    COMMUNITY = "community"
    VERIFIED_INTEGRATOR = "verified_integrator"
    STRATEGIC_PARTNER = "strategic_partner"
    GLOBAL_ALLIANCE = "global_alliance"

class EcosystemCertificationScope(str, Enum):
    PLUGIN_ADAPTER = "plugin_adapter"
    RUNTIME_CONNECTOR = "runtime_connector"
    DATA_PLATFORM_PACK = "data_platform_pack"
    SOLUTION_BLUEPRINT = "solution_blueprint"

@dataclass
class EcosystemCertificationRecord:
    cert_id: str
    partner_id: str
    extension_name: str
    version: str
    scope: EcosystemCertificationScope
    tier: EcosystemPartnerTier
    is_certified: bool = False
    compliance_score: float = 0.0
    certified_at: str = ""
    expires_at: str = ""
    signature: str = ""
    badges: List[str] = field(default_factory=list)


# ─── Customer VPC Edition Models (B38) ──────────────────────────────

class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    ALIBABA = "alibaba"

class VpcPeeringStatus(str, Enum):
    REQUESTED = "requested"
    ACTIVE = "active"
    REJECTED = "rejected"
    EXPIRED = "expired"

@dataclass
class CustomerVpcConfig:
    vpc_id: str
    customer_id: str
    provider: CloudProvider
    cidr_block: str
    private_subnet_ids: List[str] = field(default_factory=list)
    egress_mode: str = "nat_gateway"
    kms_key_arn: str = ""
    peering_connection_id: str = ""
    peering_status: VpcPeeringStatus = VpcPeeringStatus.REQUESTED
    is_deployed: bool = False
    created_at: str = ""

@dataclass
class VpcDeploymentVerification:
    verification_id: str
    vpc_id: str
    subnets_reachable: bool = False
    kms_encrypt_decrypt_ok: bool = False
    egress_connectivity_ok: bool = False
    passed: bool = False
    verified_at: str = ""


# ─── Tenant Project Migration Health Models (B39) ───────────────────

class MigrationHealthState(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    PAUSED = "paused"

@dataclass
class MigrationHealthMetric:
    metric_name: str
    current_value: float
    warning_threshold: float
    critical_threshold: float
    is_healthy: bool = True

@dataclass
class TenantMigrationHealthRecord:
    record_id: str
    tenant_id: str
    project_id: str
    state: MigrationHealthState = MigrationHealthState.HEALTHY
    replication_lag_seconds: float = 0.0
    error_rate_pct: float = 0.0
    throughput_items_per_sec: float = 0.0
    metrics: List[MigrationHealthMetric] = field(default_factory=list)
    last_health_check: str = ""
    health_summary: str = ""


# ─── License IP Provenance Models (B40) ─────────────────────────────

class LicenseType(str, Enum):
    PERMISSIVE = "permissive"
    WEAK_COPYLEFT = "weak_copyleft"
    STRONG_COPYLEFT = "strong_copyleft"
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"

class IpContaminationRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    CRITICAL = "critical"

@dataclass
class CodeArtifactLicenseRecord:
    record_id: str
    artifact_name: str
    spdx_identifier: str
    license_type: LicenseType
    contamination_risk: IpContaminationRisk
    copyright_holder: str
    license_file_digest: str = ""
    is_approved_for_commercial_use: bool = False
    scanned_at: str = ""


# ─── Diagnostic Root Cause Recommendation Models (B41) ──────────────

class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"

class RemediationEffort(str, Enum):
    IMMEDIATE_RETRY = "immediate_retry"
    AUTOMATIC_PATCH = "automatic_patch"
    CONFIG_UPDATE = "config_update"
    MANUAL_REFACTOR = "manual_refactor"

@dataclass
class RootCauseHypothesis:
    hypothesis_id: str
    cause_name: str
    confidence_score: float
    matching_error_pattern: str
    recommended_action: str
    effort: RemediationEffort
    automated_fix_available: bool = False

@dataclass
class DiagnosticReport:
    report_id: str
    run_id: str
    error_signature: str
    primary_root_cause: Optional[RootCauseHypothesis] = None
    secondary_hypotheses: List[RootCauseHypothesis] = field(default_factory=list)
    generated_at: str = ""


# ─── Functional Depth Certification Models (B45) ─────────────────────

class FunctionalCategory(str, Enum):
    AUTH_SECURITY = "auth_security"
    DATA_VALIDATION = "data_validation"
    BUSINESS_LOGIC = "business_logic"
    TRANSACTION_INTEGRITY = "transaction_integrity"
    STATE_TRANSITIONS = "state_transitions"
    ASYNC_PROCESSING = "async_processing"
    REPORTING_ANALYTICS = "reporting_analytics"
    EVENT_EMISSION = "event_emission"
    EXTERNAL_INTEGRATIONS = "external_integrations"
    EDGE_CASE_HANDLING = "edge_case_handling"

@dataclass
class FunctionalTestCaseResult:
    test_id: str
    category: FunctionalCategory
    name: str
    passed: bool
    depth_weight: float = 1.0
    execution_time_ms: float = 0.0

@dataclass
class FunctionalDepthCertificationRecord:
    cert_id: str
    application_id: str
    version: str
    depth_score: float = 0.0
    is_certified: bool = False
    test_results: List[FunctionalTestCaseResult] = field(default_factory=list)
    certified_at: str = ""
    certified_by: str = ""
    min_depth_threshold: float = 95.0
