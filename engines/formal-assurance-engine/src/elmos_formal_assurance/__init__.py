"""Repository-owned runtime for the ELMOS Formal Assurance Kernel."""

from .canonical import canonical_json, digest_bytes, digest_value, proof_cache_key
from .artifact_store import ArtifactStore, ContentAddressedArtifactStore
from .bundles import EvidenceBundleService, HmacEvidenceBundleSigner
from .contracts import (
    AssuranceLevel,
    Criticality,
    ProofResult,
    ProofStatus,
    ProofRunState,
    Scope,
    TrustedIdentity,
)
from .gate import evaluate_release_gate, validate_result
from .executor import LocalBoundedExecutor, LocalEvaluationError
from .execution import (
    ExecutionPermit,
    ExecutionPermitSigner,
    NativeVerificationExecutor,
    ResourceLimits,
    SandboxKind,
    ToolchainRegistration,
    TrustedToolFile,
    execution_binding_digest,
    load_toolchain_registry,
)
from .database import SQLiteDifferentialExecutor
from .events import DigestReceiptPublisher, EventPublisher, OutboxDispatcher
from .governance import GovernanceService
from .observability import FormalObservabilityService, OtlpHttpJsonExporter
from .postgres import Postgres17MigrationManager
from .registry import SkillRegistry
from .runtime import FormalAssuranceRuntime, RuntimeConfig
from .lean_dafny_bridge import (
    Lean4Generator,
    DafnyGenerator,
    FormalProofKernelBridge,
    get_formal_proof_bridge,
    generate_lean4_proof,
)
from .hermetic_environment_builder import (
    HermeticToolchainBuilder,
    ToolchainManifest,
    export_hermetic_toolchain,
)

__version__ = "1.0.0"

__all__ = [
    "AssuranceLevel",
    "ArtifactStore",
    "ContentAddressedArtifactStore",
    "Criticality",
    "DigestReceiptPublisher",
    "EvidenceBundleService",
    "EventPublisher",
    "FormalAssuranceRuntime",
    "RuntimeConfig",
    "LocalBoundedExecutor",
    "LocalEvaluationError",
    "ExecutionPermit",
    "ExecutionPermitSigner",
    "FormalObservabilityService",
    "GovernanceService",
    "HmacEvidenceBundleSigner",
    "NativeVerificationExecutor",
    "OtlpHttpJsonExporter",
    "OutboxDispatcher",
    "Postgres17MigrationManager",
    "ProofResult",
    "ProofRunState",
    "ProofStatus",
    "Scope",
    "ResourceLimits",
    "SandboxKind",
    "SQLiteDifferentialExecutor",
    "SkillRegistry",
    "TrustedIdentity",
    "ToolchainRegistration",
    "TrustedToolFile",
    "canonical_json",
    "digest_bytes",
    "digest_value",
    "proof_cache_key",
    "evaluate_release_gate",
    "execution_binding_digest",
    "load_toolchain_registry",
    "validate_result",
    "Lean4Generator",
    "DafnyGenerator",
    "FormalProofKernelBridge",
    "get_formal_proof_bridge",
    "generate_lean4_proof",
    "HermeticToolchainBuilder",
    "ToolchainManifest",
    "export_hermetic_toolchain",
]


