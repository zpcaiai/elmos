"""Elmos PI Harness 5.1.

The package contains the repository-owned runtime boundary for the attached
architecture package. Production adapters and evidence-verification interfaces
are implemented, while external execution and production certification remain
outside the authority of this package.
"""

from .models import (
    AuthoritySnapshot,
    EnvironmentRef,
    ExecutorIdentity,
    InstructionEnvelope,
    ProtocolCapabilities,
    ToolInvocation,
    ToolResult,
    WorkspaceLease,
)
from .external_gates import ExternalGateLedger, GateExecution, ReleaseCandidate
from .immutable_evidence import (
    S3ImmutableEvidenceArchive,
    S3ImmutableEvidenceConfig,
)
from .persistence import DurableStore
from .postgres import PostgresConfig, PostgresMigrator, PostgresStore
from .qualification import implementation_inventory

__all__ = [
    "AuthoritySnapshot",
    "DurableStore",
    "ExternalGateLedger",
    "EnvironmentRef",
    "ExecutorIdentity",
    "InstructionEnvelope",
    "GateExecution",
    "PostgresConfig",
    "PostgresMigrator",
    "PostgresStore",
    "ProtocolCapabilities",
    "ReleaseCandidate",
    "S3ImmutableEvidenceArchive",
    "S3ImmutableEvidenceConfig",
    "ToolInvocation",
    "ToolResult",
    "WorkspaceLease",
    "implementation_inventory",
]
