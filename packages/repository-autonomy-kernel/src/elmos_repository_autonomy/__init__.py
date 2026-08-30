"""Fail-closed implementation of the Elmos Repository Autonomy Kernel v2."""

from .adapters import ADAPTERS, CONFORMANCE_CASES, ConformanceHarness, all_local_conformance
from .catalog import PACKAGE_ID, PACKAGE_VERSION, SKILL_NAMES, SKILL_SPECS
from .certification import TEST_CASES, CertificationEngine, EvidenceTrustStore, TrustAnchor
from .deployment import FAILURE_SCENARIOS, KubernetesAdapter, KubernetesFailureAdapter, deployment_evidence_status
from .dispatcher import AutonomyRuntime, DispatchContext, dispatch
from .errors import ContractError, KernelError
from .external import (
    CanonicalSCMAdapter,
    DurableEventPublisher,
    EphemeralSecretsBroker,
    ExternalOperationCoordinator,
    ExternalOperationRequest,
    IdempotentEventConsumer,
    S3ObjectStoreAdapter,
    S3PresignService,
    provider_adapters,
)
from .external_runtime import (
    CommandBinding,
    CommandEventBusTransport,
    CommandIndependentVerifierTransport,
    CommandKubernetesTransport,
    CommandPostgresTransport,
    CommandProviderTransport,
    CommandS3Transport,
    CommandSCMTransport,
    CommandSecretsBrokerTransport,
    ExternalQualificationPreflight,
    JsonCommandRunner,
    load_qualification_manifest,
)
from .golden import CustomerAcceptanceRegistry, GoldenRouteEvaluator, RepositoryBinding
from .models import DispatchResult, Status
from .postgres import PostgresDisasterRecovery, PostgresMigrationRunner, PostgresSessionFactory
from .postgres_wave_store import PostgresWaveStore
from .routes import GOLDEN_ROUTES, route_definition
from .schema_registry import SCHEMA_NAMES, SchemaRegistry
from .storage import DurableStore

__version__ = PACKAGE_VERSION

__all__ = [
    "ADAPTERS",
    "CONFORMANCE_CASES",
    "FAILURE_SCENARIOS",
    "GOLDEN_ROUTES",
    "PACKAGE_ID",
    "PACKAGE_VERSION",
    "SCHEMA_NAMES",
    "SKILL_NAMES",
    "SKILL_SPECS",
    "TEST_CASES",
    "AutonomyRuntime",
    "CanonicalSCMAdapter",
    "CertificationEngine",
    "CommandBinding",
    "CommandEventBusTransport",
    "CommandIndependentVerifierTransport",
    "CommandKubernetesTransport",
    "CommandPostgresTransport",
    "CommandProviderTransport",
    "CommandS3Transport",
    "CommandSCMTransport",
    "CommandSecretsBrokerTransport",
    "ConformanceHarness",
    "ContractError",
    "CustomerAcceptanceRegistry",
    "DispatchContext",
    "DispatchResult",
    "DurableEventPublisher",
    "DurableStore",
    "EphemeralSecretsBroker",
    "EvidenceTrustStore",
    "ExternalOperationCoordinator",
    "ExternalOperationRequest",
    "ExternalQualificationPreflight",
    "GoldenRouteEvaluator",
    "IdempotentEventConsumer",
    "KernelError",
    "KubernetesAdapter",
    "KubernetesFailureAdapter",
    "JsonCommandRunner",
    "PostgresDisasterRecovery",
    "PostgresMigrationRunner",
    "PostgresSessionFactory",
    "PostgresWaveStore",
    "RepositoryBinding",
    "S3ObjectStoreAdapter",
    "S3PresignService",
    "SchemaRegistry",
    "Status",
    "TrustAnchor",
    "all_local_conformance",
    "deployment_evidence_status",
    "dispatch",
    "load_qualification_manifest",
    "provider_adapters",
    "route_definition",
]
