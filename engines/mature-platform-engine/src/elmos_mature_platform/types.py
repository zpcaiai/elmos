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
    cve_id: str
    product_id: str
    status: str  # not_affected, affected, fixed, under_investigation
    justification: Optional[VexJustification] = None
    impact_statement: str = ""
    action_statement: str = ""
    timestamp: str = ""

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
    description: str
    quantity: float
    unit_price: float
    total_cost: float
    currency: str = "USD"
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    timestamp: str = ""

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
