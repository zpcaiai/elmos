"""Repository-owned runtime for the ELMOS Formal Assurance Kernel."""

from .canonical import canonical_json, digest_bytes, digest_value, proof_cache_key
from .artifact_store import ContentAddressedArtifactStore
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
from .observability import FormalObservabilityService, OtlpHttpJsonExporter
from .registry import SkillRegistry
from .runtime import FormalAssuranceRuntime, RuntimeConfig

__version__ = "1.0.0"

__all__ = [
    "AssuranceLevel",
    "ContentAddressedArtifactStore",
    "Criticality",
    "FormalAssuranceRuntime",
    "RuntimeConfig",
    "LocalBoundedExecutor",
    "LocalEvaluationError",
    "ExecutionPermit",
    "ExecutionPermitSigner",
    "FormalObservabilityService",
    "NativeVerificationExecutor",
    "OtlpHttpJsonExporter",
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
]
