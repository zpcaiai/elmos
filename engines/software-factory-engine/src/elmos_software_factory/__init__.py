"""Public API for the bounded ELMOS software-factory runtime."""

from .archive_contracts import ArchiveContractError, inspect_archive_contracts
from .artifact_binding import (
    ArtifactBindingError,
    ContentReference,
    read_content_reference,
)
from .canonical import CanonicalValueError, canonical_digest, canonical_json
from .campaigns import (
    campaign_corpus_digest,
    rehearse_canary,
    replay_campaign,
    run_campaign,
    run_local_holdout,
    simulate_provider_contract,
)
from .capabilities import (
    CAPABILITY_CONTRACTS,
    CAPABILITY_REGISTRY_DIGEST,
    CapabilityContract,
    CapabilityRegistryError,
    capability_contract,
    load_capability_registry,
)
from .models import (
    ContractError,
    ExecutionError,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExternalObservation,
    ScopeEnvelope,
)
from .evidence_intake import evaluate_external_preflight, ingest_external_receipt
from .evidence_models import (
    CampaignReceipt,
    CampaignScope,
    EvidenceContractError,
)
from .public_methods import (
    PUBLIC_METHODS,
    PUBLIC_METHOD_REGISTRY_DIGEST,
    PLATFORM_ERRORS,
    PublicMethodBinding,
    PublicMethodRegistryError,
    load_public_method_registry,
    public_method,
)
from .registry import RegistryError, SkillBinding, SkillRegistry, load_registry
from .runtime import SoftwareFactoryEngine, dispatch_skill

__all__ = [
    "ArchiveContractError",
    "ArtifactBindingError",
    "CanonicalValueError",
    "CAPABILITY_CONTRACTS",
    "CAPABILITY_REGISTRY_DIGEST",
    "CapabilityContract",
    "CapabilityRegistryError",
    "CampaignReceipt",
    "CampaignScope",
    "ContentReference",
    "ContractError",
    "EvidenceContractError",
    "ExecutionError",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "ExternalObservation",
    "PUBLIC_METHODS",
    "PUBLIC_METHOD_REGISTRY_DIGEST",
    "PLATFORM_ERRORS",
    "PublicMethodBinding",
    "PublicMethodRegistryError",
    "RegistryError",
    "ScopeEnvelope",
    "SkillBinding",
    "SkillRegistry",
    "SoftwareFactoryEngine",
    "canonical_digest",
    "canonical_json",
    "campaign_corpus_digest",
    "capability_contract",
    "dispatch_skill",
    "evaluate_external_preflight",
    "ingest_external_receipt",
    "inspect_archive_contracts",
    "load_registry",
    "load_capability_registry",
    "load_public_method_registry",
    "public_method",
    "read_content_reference",
    "rehearse_canary",
    "replay_campaign",
    "run_campaign",
    "run_local_holdout",
    "simulate_provider_contract",
]
