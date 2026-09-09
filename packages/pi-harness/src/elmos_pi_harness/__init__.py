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
from .bridges import ClaudeHarnessBridge, CodexHarnessBridge, MCPHarnessBridge
from .external_gates import ExternalGateLedger, GateExecution, ReleaseCandidate
from .immutable_evidence import (
    S3ImmutableEvidenceArchive,
    S3ImmutableEvidenceConfig,
)
from .persistence import DurableStore
from .postgres import PostgresConfig, PostgresMigrator, PostgresStore
from .qualification import implementation_inventory
from .repair import (
    CounterexampleShrinker,
    FailureClassification,
    FailureClassifier,
    RepairProposal,
    SelfHealingController,
    admit_repair,
)
from .runtime import ExecutionRuntime

__all__ = [
    "AuthoritySnapshot",
    "ClaudeHarnessBridge",
    "CodexHarnessBridge",
    "CounterexampleShrinker",
    "DurableStore",
    "EnvironmentRef",
    "ExecutionRuntime",
    "ExecutorIdentity",
    "ExternalGateLedger",
    "FailureClassification",
    "FailureClassifier",
    "GateExecution",
    "InstructionEnvelope",
    "MCPHarnessBridge",
    "PostgresConfig",
    "PostgresMigrator",
    "PostgresStore",
    "ProtocolCapabilities",
    "ReleaseCandidate",
    "RepairProposal",
    "S3ImmutableEvidenceArchive",
    "S3ImmutableEvidenceConfig",
    "SelfHealingController",
    "ToolInvocation",
    "ToolResult",
    "WorkspaceLease",
    "admit_repair",
    "implementation_inventory",
]
