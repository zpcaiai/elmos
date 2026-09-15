"""ELMOS proof-driven agentic harness and repository semantic compiler."""

from .adapters import (
    DECLARED_ADAPTER_REGISTRY,
    HARNESS_ADAPTER_REGISTRY,
    VERIFIER_ADAPTER_REGISTRY,
    AdapterInvocation,
    AdapterManifest,
    AdapterRegistry,
    AdapterResult,
    AdapterStatus,
    DeclaredAdapterDescriptor,
)
from .architecture import ArchitectureDiff, ArchitectureExtractor, ArchitectureGraph
from .assurance_policies import (
    HostSecurityContextSigner,
    ManagedWorktreeIdentity,
    ManagedWorktreeRegistry,
    PrivilegedPathContract,
    PrivilegedPathPolicy,
    SkillTrustDomainPolicy,
)
from .control_plane import DurableControlPlane
from .domains import DOMAIN_PACKS, DomainPackOrchestrator
from .delta_storage import HostSignedEnvelope
from .repository import RepositoryEvidenceGraph, RepositorySnapshotter, SnapshotLimits
from .runtime_assurance import (
    EvidenceBackedDeltaStore,
    RegisteredRuntimeAssuranceAuthorityProvider,
    RuntimeAssuranceControlPlane,
)
from .semantic import (
    FRAMEWORK_PROFILES,
    LANGUAGE_PROFILES,
    SemanticBundle,
    SemanticCompiler,
)
from .service import (
    AuthenticationError,
    Authenticator,
    AuthPrincipal,
    HarnessService,
    SERVICE_VERSION,
    StaticTokenAuthenticator,
)
from .skills import COMPONENT_REGISTRY, SKILL_REGISTRY, SkillRuntime
from .transformation import ChangeSet, FileChange, WorkspaceTransformer

from . import delta_v32

from .hermetic_container import (
    EnvironmentFingerprint,
    HermeticContainerSandbox,
    HermeticExecutionReceipt,
    IsolationLevel,
)
from .resilience_channel import (
    ChaosConfig,
    ChaosFaultInjector,
    ChaosFaultType,
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    NonRetryableError,
    ResilientDatabaseChannel,
    RetryMetrics,
)
from .soak_auditor import (
    LeakReport,
    ResourceAuditSnapshot,
    ResourceLeakAuditor,
    ResourceLeakError,
    SoakTestRunner,
)
from .independent_audit_gate import (
    AuthoritativeAuditReceipt,
    CandidateEvidenceBundle,
    GateDecision,
    GateViolationReason,
    IndependentAuditGateRunner,
)
from .host_broker import (
    CapabilityLease,
    CapabilityLeaseVerifier,
    EffectSettlementReceipt,
    HostBrokerChannel,
    SettlementLedger,
    SettlementStatus,
)
from .postgres_lifecycle import (
    EphemeralPostgresCluster,
    PostgresBinaryDiscovery,
    PostgresVersionInfo,
    ReversibleMigrationEngine,
)
from .tenant_scheduler import (
    PriorityPreemptionQueue,
    PriorityTier,
    QueuedTask,
    TenantConcurrencyPool,
    TenantFairScheduler,
    TenantQuotaExceededError,
)
from .crash_recovery import (
    InFlightOrphanReconciler,
    JournalEvent,
    TaskExecutionJournal,
    TaskLifecycleState,
    TimeTravelReplayer,
)
from .tsa_notary import (
    MerkleTransparencyLog,
    TSANotaryAuthority,
    TimeStampToken,
)

__version__ = SERVICE_VERSION

__all__ = [
    "delta_v32",
    "AdapterInvocation",
    "AdapterManifest",
    "AdapterRegistry",
    "AdapterResult",
    "AdapterStatus",
    "DECLARED_ADAPTER_REGISTRY",
    "DeclaredAdapterDescriptor",
    "HARNESS_ADAPTER_REGISTRY",
    "ArchitectureDiff",
    "ArchitectureExtractor",
    "ArchitectureGraph",
    "AuthenticationError",
    "Authenticator",
    "AuthPrincipal",
    "COMPONENT_REGISTRY",
    "ChangeSet",
    "DOMAIN_PACKS",
    "DurableControlPlane",
    "EvidenceBackedDeltaStore",
    "DomainPackOrchestrator",
    "FRAMEWORK_PROFILES",
    "FileChange",
    "HarnessService",
    "HostSecurityContextSigner",
    "HostSignedEnvelope",
    "LANGUAGE_PROFILES",
    "ManagedWorktreeIdentity",
    "ManagedWorktreeRegistry",
    "PrivilegedPathContract",
    "PrivilegedPathPolicy",
    "RepositoryEvidenceGraph",
    "RepositorySnapshotter",
    "RegisteredRuntimeAssuranceAuthorityProvider",
    "RuntimeAssuranceControlPlane",
    "SERVICE_VERSION",
    "SKILL_REGISTRY",
    "SemanticBundle",
    "SemanticCompiler",
    "SkillRuntime",
    "SkillTrustDomainPolicy",
    "SnapshotLimits",
    "StaticTokenAuthenticator",
    "VERIFIER_ADAPTER_REGISTRY",
    "WorkspaceTransformer",
    "EnvironmentFingerprint",
    "HermeticContainerSandbox",
    "HermeticExecutionReceipt",
    "IsolationLevel",
    "ChaosConfig",
    "ChaosFaultInjector",
    "ChaosFaultType",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "NonRetryableError",
    "ResilientDatabaseChannel",
    "RetryMetrics",
    "LeakReport",
    "ResourceAuditSnapshot",
    "ResourceLeakAuditor",
    "ResourceLeakError",
    "SoakTestRunner",
    "AuthoritativeAuditReceipt",
    "CandidateEvidenceBundle",
    "GateDecision",
    "GateViolationReason",
    "IndependentAuditGateRunner",
    "CapabilityLease",
    "CapabilityLeaseVerifier",
    "EffectSettlementReceipt",
    "HostBrokerChannel",
    "SettlementLedger",
    "SettlementStatus",
    "EphemeralPostgresCluster",
    "PostgresBinaryDiscovery",
    "PostgresVersionInfo",
    "ReversibleMigrationEngine",
    "PriorityPreemptionQueue",
    "PriorityTier",
    "QueuedTask",
    "TenantConcurrencyPool",
    "TenantFairScheduler",
    "TenantQuotaExceededError",
    "InFlightOrphanReconciler",
    "JournalEvent",
    "TaskExecutionJournal",
    "TaskLifecycleState",
    "TimeTravelReplayer",
    "MerkleTransparencyLog",
    "TSANotaryAuthority",
    "TimeStampToken",
    "__version__",
]
