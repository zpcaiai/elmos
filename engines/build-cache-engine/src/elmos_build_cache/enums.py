"""Closed vocabularies for the cache/staging subsystem.

Every enum here is part of the persisted contract: values are written to
SQLite/PostgreSQL rows, CAS manifests and API payloads. They are ``str``
subclasses so serialisation is transparent, and they never gain values without
a schema version bump.
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class ValidationLevel(_StrEnum):
    """Trust ladder for cache entries, artifacts and trees."""

    UNVERIFIED = "UNVERIFIED"
    COMPILE_VERIFIED = "COMPILE_VERIFIED"
    TEST_VERIFIED = "TEST_VERIFIED"
    BEHAVIOR_VERIFIED = "BEHAVIOR_VERIFIED"
    PRODUCTION_CERTIFIED = "PRODUCTION_CERTIFIED"
    QUARANTINED = "QUARANTINED"

    @property
    def rank(self) -> int:
        return _VALIDATION_RANK[self]

    def satisfies(self, minimum: ValidationLevel) -> bool:
        """QUARANTINED never satisfies anything, including itself."""
        if self is ValidationLevel.QUARANTINED or minimum is ValidationLevel.QUARANTINED:
            return False
        return self.rank >= minimum.rank


_VALIDATION_RANK: dict[ValidationLevel, int] = {
    ValidationLevel.QUARANTINED: -1,
    ValidationLevel.UNVERIFIED: 0,
    ValidationLevel.COMPILE_VERIFIED: 1,
    ValidationLevel.TEST_VERIFIED: 2,
    ValidationLevel.BEHAVIOR_VERIFIED: 3,
    ValidationLevel.PRODUCTION_CERTIFIED: 4,
}


class FileClass(_StrEnum):
    SCRATCH = "SCRATCH"
    STAGED_INTERMEDIATE = "STAGED_INTERMEDIATE"
    SEALED_ARTIFACT = "SEALED_ARTIFACT"
    PUBLISH_CANDIDATE = "PUBLISH_CANDIDATE"
    QUARANTINED = "QUARANTINED"


class StagedFileStatus(_StrEnum):
    RESERVED = "RESERVED"
    WRITING = "WRITING"
    SEALED = "SEALED"
    CAS_PROMOTED = "CAS_PROMOTED"
    TREE_INCLUDED = "TREE_INCLUDED"
    PUBLISHED = "PUBLISHED"
    ABORTED = "ABORTED"
    QUARANTINED = "QUARANTINED"


#: Legal staged-file transitions. Anything absent is an INVALID_TRANSITION.
STAGED_FILE_TRANSITIONS: dict[StagedFileStatus, frozenset[StagedFileStatus]] = {
    StagedFileStatus.RESERVED: frozenset(
        {StagedFileStatus.WRITING, StagedFileStatus.ABORTED, StagedFileStatus.QUARANTINED}
    ),
    StagedFileStatus.WRITING: frozenset(
        {StagedFileStatus.SEALED, StagedFileStatus.ABORTED, StagedFileStatus.QUARANTINED}
    ),
    StagedFileStatus.SEALED: frozenset({StagedFileStatus.CAS_PROMOTED, StagedFileStatus.QUARANTINED}),
    StagedFileStatus.CAS_PROMOTED: frozenset({StagedFileStatus.TREE_INCLUDED, StagedFileStatus.QUARANTINED}),
    StagedFileStatus.TREE_INCLUDED: frozenset({StagedFileStatus.PUBLISHED, StagedFileStatus.QUARANTINED}),
    StagedFileStatus.PUBLISHED: frozenset(),
    # ABORTED -> RESERVED is the *only* backwards edge, and it exists so the
    # same producer can retry its own failed write for the same logical path
    # without inventing a second staged-file row for it.
    StagedFileStatus.ABORTED: frozenset({StagedFileStatus.RESERVED}),
    StagedFileStatus.QUARANTINED: frozenset(),
}


class NodeStatus(_StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    PAUSED = "PAUSED"
    CANCELED = "CANCELED"
    RECOVERING = "RECOVERING"
    STALE = "STALE"


NODE_TRANSITIONS: dict[NodeStatus, frozenset[NodeStatus]] = {
    NodeStatus.PENDING: frozenset({NodeStatus.READY, NodeStatus.CANCELED, NodeStatus.PAUSED}),
    NodeStatus.READY: frozenset({NodeStatus.RUNNING, NodeStatus.CANCELED, NodeStatus.PAUSED}),
    NodeStatus.RUNNING: frozenset(
        {
            NodeStatus.CHECKPOINTED,
            NodeStatus.SUCCEEDED,
            NodeStatus.FAILED_RETRYABLE,
            NodeStatus.FAILED_FINAL,
            NodeStatus.PAUSED,
            NodeStatus.CANCELED,
            NodeStatus.STALE,
            NodeStatus.RECOVERING,
        }
    ),
    NodeStatus.CHECKPOINTED: frozenset(
        {
            NodeStatus.RUNNING,
            NodeStatus.SUCCEEDED,
            NodeStatus.FAILED_RETRYABLE,
            NodeStatus.FAILED_FINAL,
            NodeStatus.PAUSED,
            NodeStatus.CANCELED,
            NodeStatus.STALE,
            NodeStatus.RECOVERING,
        }
    ),
    NodeStatus.FAILED_RETRYABLE: frozenset({NodeStatus.READY, NodeStatus.FAILED_FINAL, NodeStatus.CANCELED}),
    NodeStatus.PAUSED: frozenset({NodeStatus.READY, NodeStatus.CANCELED, NodeStatus.RECOVERING}),
    NodeStatus.STALE: frozenset({NodeStatus.RECOVERING, NodeStatus.CANCELED, NodeStatus.FAILED_FINAL}),
    NodeStatus.RECOVERING: frozenset(
        {NodeStatus.READY, NodeStatus.RUNNING, NodeStatus.FAILED_FINAL, NodeStatus.CANCELED}
    ),
    NodeStatus.SUCCEEDED: frozenset(),
    NodeStatus.FAILED_FINAL: frozenset(),
    NodeStatus.CANCELED: frozenset(),
}

TERMINAL_NODE_STATES = frozenset({NodeStatus.SUCCEEDED, NodeStatus.FAILED_FINAL, NodeStatus.CANCELED})


class RunStatus(_StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    RECOVERING = "RECOVERING"
    STALE = "STALE"


RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.CANCELED, RunStatus.PAUSED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.PAUSED,
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELED,
            RunStatus.RECOVERING,
            RunStatus.STALE,
        }
    ),
    RunStatus.PAUSED: frozenset({RunStatus.RUNNING, RunStatus.CANCELED, RunStatus.RECOVERING}),
    RunStatus.RECOVERING: frozenset({RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELED}),
    RunStatus.STALE: frozenset({RunStatus.RECOVERING, RunStatus.FAILED, RunStatus.CANCELED}),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset({RunStatus.RECOVERING}),
    RunStatus.CANCELED: frozenset(),
}


class ArtifactStorageState(_StrEnum):
    LOCAL = "LOCAL"
    REMOTE_PENDING = "REMOTE_PENDING"
    REMOTE = "REMOTE"
    QUARANTINED = "QUARANTINED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class CacheEntryStatus(_StrEnum):
    ACTIVE = "ACTIVE"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class CacheMode(_StrEnum):
    BYPASS = "bypass"
    READ_ONLY = "read-only"
    WRITE_ONLY = "write-only"
    READ_WRITE = "read-write"
    REFRESH = "refresh"

    @property
    def may_read(self) -> bool:
        return self in {CacheMode.READ_ONLY, CacheMode.READ_WRITE}

    @property
    def may_write(self) -> bool:
        return self in {CacheMode.WRITE_ONLY, CacheMode.READ_WRITE, CacheMode.REFRESH}


class Determinism(_StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    SEEDED = "SEEDED"
    ENVIRONMENT_SENSITIVE = "ENVIRONMENT_SENSITIVE"
    NONDETERMINISTIC_CANDIDATE_ONLY = "NONDETERMINISTIC_CANDIDATE_ONLY"


class Ownership(_StrEnum):
    GENERATED = "GENERATED"
    GENERATED_PROTECTED = "GENERATED_PROTECTED"
    USER = "USER"
    SHARED = "SHARED"
    EXTERNAL = "EXTERNAL"


class SecretScanStatus(_StrEnum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"  # noqa: S105 - a scan verdict, not a credential
    FAIL = "FAIL"
    ERROR = "ERROR"


class SideEffectStatus(_StrEnum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


class CheckpointStatus(_StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"
    QUARANTINED = "QUARANTINED"


class TrustNamespace(_StrEnum):
    """Producer trust domains. Lower domains never satisfy higher ones."""

    OFFICIAL = "official"
    BRANCH = "branch"
    FORK = "fork"
    EXPERIMENTAL = "experimental"
    QUARANTINE = "quarantine"

    @property
    def rank(self) -> int:
        return _TRUST_RANK[self]

    def satisfies(self, required: TrustNamespace) -> bool:
        if self is TrustNamespace.QUARANTINE:
            return False
        return self.rank >= required.rank


_TRUST_RANK: dict[TrustNamespace, int] = {
    TrustNamespace.QUARANTINE: -1,
    TrustNamespace.EXPERIMENTAL: 0,
    TrustNamespace.FORK: 1,
    TrustNamespace.BRANCH: 2,
    TrustNamespace.OFFICIAL: 3,
}


class MissReason(_StrEnum):
    """Structured cache-miss taxonomy (``references/cache-miss-reasons.md``)."""

    NO_ENTRY = "NO_ENTRY"
    SOURCE_DIGEST_CHANGED = "SOURCE_DIGEST_CHANGED"
    PUBLIC_INTERFACE_CHANGED = "PUBLIC_INTERFACE_CHANGED"
    DEPENDENCY_LOCK_CHANGED = "DEPENDENCY_LOCK_CHANGED"
    RULE_PACK_CHANGED = "RULE_PACK_CHANGED"
    STAGE_VERSION_CHANGED = "STAGE_VERSION_CHANGED"
    STAGE_CONTRACT_CHANGED = "STAGE_CONTRACT_CHANGED"
    TOOLCHAIN_CHANGED = "TOOLCHAIN_CHANGED"
    TARGET_PROFILE_CHANGED = "TARGET_PROFILE_CHANGED"
    COMPILER_FLAGS_CHANGED = "COMPILER_FLAGS_CHANGED"
    DECLARED_ENVIRONMENT_CHANGED = "DECLARED_ENVIRONMENT_CHANGED"
    PROMPT_TEMPLATE_CHANGED = "PROMPT_TEMPLATE_CHANGED"
    MODEL_SNAPSHOT_CHANGED = "MODEL_SNAPSHOT_CHANGED"
    TOOL_OUTPUT_CHANGED = "TOOL_OUTPUT_CHANGED"
    FEATURE_FLAG_CHANGED = "FEATURE_FLAG_CHANGED"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
    VALIDATION_TOO_LOW = "VALIDATION_TOO_LOW"
    TRUST_NAMESPACE_MISMATCH = "TRUST_NAMESPACE_MISMATCH"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    ENTRY_EXPIRED = "ENTRY_EXPIRED"
    ENTRY_REVOKED = "ENTRY_REVOKED"
    ENTRY_QUARANTINED = "ENTRY_QUARANTINED"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    ARTIFACT_CORRUPT = "ARTIFACT_CORRUPT"
    RESTORE_COST_EXCEEDS_RECOMPUTE = "RESTORE_COST_EXCEEDS_RECOMPUTE"
    POLICY_BYPASS = "POLICY_BYPASS"
    NONDETERMINISTIC_STAGE = "NONDETERMINISTIC_STAGE"


#: Fingerprint dimension -> miss reason. Used to explain exactly why a key moved.
DIMENSION_MISS_REASON: dict[str, MissReason] = {
    "stage_version": MissReason.STAGE_VERSION_CHANGED,
    "stage_contract_schema": MissReason.STAGE_CONTRACT_CHANGED,
    "input_artifact_digests": MissReason.SOURCE_DIGEST_CHANGED,
    "source_semantic_digest": MissReason.SOURCE_DIGEST_CHANGED,
    "dependency_public_interface_digests": MissReason.PUBLIC_INTERFACE_CHANGED,
    "target_language": MissReason.TARGET_PROFILE_CHANGED,
    "target_framework": MissReason.TARGET_PROFILE_CHANGED,
    "target_runtime": MissReason.TARGET_PROFILE_CHANGED,
    "target_triple": MissReason.TARGET_PROFILE_CHANGED,
    "rule_pack_digest": MissReason.RULE_PACK_CHANGED,
    "toolchain_digest": MissReason.TOOLCHAIN_CHANGED,
    "compiler_flags": MissReason.COMPILER_FLAGS_CHANGED,
    "dependency_lock_digests": MissReason.DEPENDENCY_LOCK_CHANGED,
    "declared_environment": MissReason.DECLARED_ENVIRONMENT_CHANGED,
    "prompt_template_digest": MissReason.PROMPT_TEMPLATE_CHANGED,
    "model_snapshot_digest": MissReason.MODEL_SNAPSHOT_CHANGED,
    "decoding_parameters": MissReason.MODEL_SNAPSHOT_CHANGED,
    "tool_output_digests": MissReason.TOOL_OUTPUT_CHANGED,
    "feature_flags": MissReason.FEATURE_FLAG_CHANGED,
}
