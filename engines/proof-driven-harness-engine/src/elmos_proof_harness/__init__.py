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

__version__ = SERVICE_VERSION

__all__ = [
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
    "__version__",
]
