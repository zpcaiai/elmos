"""Durable, cache-aware context checkpoints with atomic adoption and rollback.

A provider prefix cache is only a performance layer. The imported v1.2
checkpoint schema leaves section objects open, so this module applies a strict
internal overlay: the metadata row contains only a typed, content-free CAS
reference while the bounded structured state lives in a tenant-owned typed CAS
manifest and is verified on every restore. Provider warm-up evidence is a
prerequisite for switching, never the source of truth that is switched to.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .canonical import canonical_json_bytes, canonical_json_text, digest_of, require_digest
from .cas import ContentAddressableStore
from .context_ledger import RepositoryContextLedger
from .errors import ConflictError, ContractViolation, CorruptObject, NotFound, VersionConflict
from .security import ProvenanceSigner, SignedStatement

CHECKPOINT_SCHEMA_VERSION = "1.2.0"
CHECKPOINT_SECTIONS_KIND = "elmos.context-checkpoint-sections/v1.2"
CHECKPOINT_SECTIONS_REF_KIND = "elmos.context-checkpoint-sections-ref/v1.2"
WARM_RESULT_KIND = "elmos.context-checkpoint-warm-result/v1.2"
WARM_ATTESTATION_KIND = "elmos.context-checkpoint-warm-attestation/v1.2"
CHECKPOINT_ARTIFACT_SOURCE_KIND = "context-checkpoint"
WARM_ARTIFACT_SOURCE_KIND = "context-warm-authorization"
MAX_SECTIONS_BYTES = 2 * 1024 * 1024
MAX_SECTION_TEXT_BYTES = 16 * 1024
MAX_SECTION_NODES = 20_000

_SENSITIVE_KEY_TERMS = (
    "api_key",
    "authorization",
    "body",
    "bytes",
    "content",
    "credential",
    "password",
    "private_key",
    "prompt",
    "raw",
    "secret",
    "source_code",
    "source_text",
    "token",
    "value",
)
_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:api[-_ ]?key|access[-_ ]?token|credential|password|private[-_ ]?key|secret)"
    r"\s*[:=]\s*\S+"
)
_DIGEST_KEY_SUFFIXES = ("_digest", "_digests", "_ref", "_refs", "_reference")
_SECTION_ALLOWED_KEYS: dict[str, frozenset[str]] = {
    "task_contract": frozenset({"request", "scope", "requirements", "constraints", "version", "task_digest"}),
    "repository_state": frozenset(
        {
            "repository_snapshot_digest",
            "branch_lineage",
            "changed_files",
            "commit_digest",
            "dirty_state_digest",
            "worktree_digest",
        }
    ),
    "dag_state": frozenset({"phase", "pending_nodes", "completed_nodes", "failed_nodes", "graph_digest"}),
    "staged_state": frozenset({"files", "manifest_digest", "pending_files"}),
    "build_test_state": frozenset({"pytest", "status", "checks", "failures", "evidence_ref", "evidence_refs"}),
}


class ArtifactRegistration(Protocol):
    @property
    def tenant_id(self) -> str: ...

    @property
    def digest(self) -> str: ...

    @property
    def size_bytes(self) -> int: ...

    @property
    def storage_state(self) -> Any: ...

    @property
    def validation_level(self) -> Any: ...


class ContextArtifactOwnershipReader(Protocol):
    def get_artifact(self, tenant_id: str, digest: str) -> ArtifactRegistration | None: ...

    def artifact_referrers(self, tenant_id: str, digest: str) -> list[tuple[str, str, str]]: ...


class ContextWarmTrustVerifier(Protocol):
    def verify(
        self,
        signed: SignedStatement,
        *,
        expected_verifier_identity: str,
    ) -> None: ...


class Ed25519ContextWarmTrustVerifier:
    """Verify-only Ed25519 trust set with key identity and revocation binding."""

    def __init__(
        self,
        verifier: ProvenanceSigner,
        trusted_key_identities: Mapping[str, str],
        *,
        revoked_key_ids: frozenset[str] = frozenset(),
    ) -> None:
        if verifier.algorithm != "ed25519":
            raise ContractViolation("context warm evidence requires an Ed25519 verifier")
        self.verifier = verifier
        self.trusted_key_identities = dict(trusted_key_identities)
        self.revoked_key_ids = frozenset(revoked_key_ids)
        if not self.trusted_key_identities or any(
            not key_id or not identity for key_id, identity in self.trusted_key_identities.items()
        ):
            raise ContractViolation("trusted context warm verifier identities are incomplete")

    def verify(
        self,
        signed: SignedStatement,
        *,
        expected_verifier_identity: str,
    ) -> None:
        if signed.algorithm != "ed25519":
            raise ContractViolation("context warm evidence signature is not Ed25519")
        if signed.key_id in self.revoked_key_ids:
            raise ContractViolation("context warm evidence signing key is revoked")
        if self.trusted_key_identities.get(signed.key_id) != expected_verifier_identity:
            raise ContractViolation("context warm evidence key identity is not trusted")
        self.verifier.verify_statement(signed)


def context_warm_ref_kind(project_id: str, stream_id: str, checkpoint_id: str) -> str:
    for value, field_name in (
        (project_id, "project_id"),
        (stream_id, "stream_id"),
        (checkpoint_id, "checkpoint_id"),
    ):
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ContractViolation(f"{field_name} must be a bounded non-empty identifier")
    return f"checkpoint:{project_id}:{stream_id}:{checkpoint_id}"


def context_warm_attestation_statement(body: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact statement an independent verifier must sign."""

    raw_evidence = body.get("raw_evidence")
    if not isinstance(raw_evidence, list):
        raise ContractViolation("context warm result raw evidence must be an array")
    raw_digests: list[str] = []
    for item in raw_evidence:
        if not isinstance(item, Mapping) or not isinstance(item.get("digest"), str):
            raise ContractViolation("context warm result raw evidence is malformed")
        raw_digests.append(require_digest(str(item["digest"])))
    required = (
        "tenant_scope_digest",
        "authorization_digest",
        "checkpoint_digest",
        "executor_identity",
        "verifier_identity",
    )
    if any(name not in body for name in required):
        raise ContractViolation("context warm result body is incomplete")
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "warm_result_body_digest": digest_of(dict(body)),
        "tenant_scope_digest": require_digest(str(body["tenant_scope_digest"])),
        "authorization_digest": require_digest(str(body["authorization_digest"])),
        "checkpoint_digest": require_digest(str(body["checkpoint_digest"])),
        "raw_evidence_digests": sorted(raw_digests),
        "executor_identity": str(body["executor_identity"]),
        "verifier_identity": str(body["verifier_identity"]),
    }


def _sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    if normalized.endswith(_DIGEST_KEY_SUFFIXES) or normalized.endswith(("_count", "_counts")):
        return False
    return any(term in normalized for term in _SENSITIVE_KEY_TERMS)


def _validate_content_free(
    value: Any,
    path: str = "sections",
    *,
    _count: list[int] | None = None,
) -> None:
    count = [0] if _count is None else _count
    count[0] += 1
    if count[0] > MAX_SECTION_NODES:
        raise ContractViolation("context checkpoint sections exceed the bounded node count")
    if isinstance(value, Mapping):
        if len(value) > 2_048:
            raise ContractViolation("context checkpoint section object is too large", path=path)
        for key, child in value.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise ContractViolation("context checkpoint section key is invalid", path=path)
            if _sensitive_key(key):
                raise ContractViolation(
                    "raw prompt/source/secret/token material is forbidden in checkpoint state",
                    path=f"{path}.{key}",
                )
            _validate_content_free(child, f"{path}.{key}", _count=count)
    elif isinstance(value, list | tuple):
        if len(value) > 10_000:
            raise ContractViolation("context checkpoint section array is too large", path=path)
        for index, child in enumerate(value):
            _validate_content_free(child, f"{path}[{index}]", _count=count)
    elif isinstance(value, bytes | bytearray | memoryview):
        raise ContractViolation("checkpoint state cannot persist raw bytes", path=path)
    elif isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_SECTION_TEXT_BYTES:
            raise ContractViolation("context checkpoint section text is too large", path=path)
        if _SENSITIVE_TEXT.search(value):
            raise ContractViolation("secret-shaped text is forbidden in checkpoint state", path=path)
    elif value is None or isinstance(value, bool | int):
        return
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ContractViolation("checkpoint state numbers must be finite", path=path)
    else:
        raise ContractViolation("checkpoint state contains an unsupported value", path=path)


def _validate_sections_contract(document: Mapping[str, Any]) -> None:
    expected_root = {
        "task_contract",
        "repository_state",
        "decisions",
        "unresolved",
        "approvals",
        "dag_state",
        "staged_state",
        "build_test_state",
        "evidence_refs",
        "pending_side_effects",
        "safety_constraints",
    }
    if set(document) != expected_root:
        raise ContractViolation("context checkpoint sections have an unexpected closed shape")
    for section_name, allowed in _SECTION_ALLOWED_KEYS.items():
        section = document.get(section_name)
        if not isinstance(section, Mapping) or set(section) - allowed:
            raise ContractViolation(
                "context checkpoint section has an unexpected closed shape",
                section=section_name,
                unknown=sorted(set(section) - allowed) if isinstance(section, Mapping) else [],
            )
    staged_files = document["staged_state"].get("files", [])
    if not isinstance(staged_files, list):
        raise ContractViolation("context checkpoint staged files must be an array")
    for item in staged_files:
        if not isinstance(item, Mapping) or set(item) - {"path", "digest", "status"}:
            raise ContractViolation("context checkpoint staged file has an unexpected shape")
        if "digest" in item:
            require_digest(str(item["digest"]))
    for name in (
        "decisions",
        "unresolved",
        "approvals",
        "pending_side_effects",
        "safety_constraints",
    ):
        items = document[name]
        if not isinstance(items, list):
            raise ContractViolation("context checkpoint source-linked items must be arrays")
        for item in items:
            if not isinstance(item, Mapping) or set(item) != {
                "statement",
                "source_event_ids",
                "artifact_refs",
                "freshness",
            }:
                raise ContractViolation("context checkpoint source-linked item shape is invalid")
    _validate_content_free(document)
    if len(canonical_json_bytes(document)) > MAX_SECTIONS_BYTES:
        raise ContractViolation("context checkpoint sections exceed the bounded byte size")


class CompactionNeed(StrEnum):
    NONE = "NONE"
    PLAN = "PLAN"
    REQUIRED = "REQUIRED"


class ContextCheckpointStatus(StrEnum):
    PREPARED = "PREPARED"
    WARMED = "WARMED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class CompactionPolicy:
    soft_limit_tokens: int
    hard_limit_tokens: int
    reserved_future_tokens: int

    def __post_init__(self) -> None:
        if (
            self.soft_limit_tokens < 1
            or self.hard_limit_tokens <= self.soft_limit_tokens
            or self.reserved_future_tokens < 0
            or self.reserved_future_tokens >= self.hard_limit_tokens
        ):
            raise ContractViolation("compaction token limits are inconsistent")

    def assess(self, current_tokens: int, predicted_next_turn_tokens: int = 0) -> CompactionNeed:
        if current_tokens < 0 or predicted_next_turn_tokens < 0:
            raise ContractViolation("token estimates must not be negative")
        projected = current_tokens + predicted_next_turn_tokens + self.reserved_future_tokens
        if projected >= self.hard_limit_tokens:
            return CompactionNeed.REQUIRED
        if projected >= self.soft_limit_tokens:
            return CompactionNeed.PLAN
        return CompactionNeed.NONE


@dataclass(frozen=True)
class SourceLinkedItem:
    statement: str
    source_event_ids: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    freshness: str = "CURRENT"

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise ContractViolation("source-linked statement must not be blank")
        if not self.source_event_ids and not self.artifact_refs:
            raise ContractViolation("a checkpoint statement must link to a ledger event or CAS artifact")
        for reference in self.artifact_refs:
            require_digest(reference)
        if self.freshness not in {"CURRENT", "STALE", "UNKNOWN"}:
            raise ContractViolation("checkpoint statement freshness is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "source_event_ids": list(self.source_event_ids),
            "artifact_refs": list(self.artifact_refs),
            "freshness": self.freshness,
        }


@dataclass(frozen=True)
class ContextCheckpointSections:
    task_contract: dict[str, Any]
    repository_state: dict[str, Any]
    decisions: tuple[SourceLinkedItem, ...] = ()
    unresolved: tuple[SourceLinkedItem, ...] = ()
    approvals: tuple[SourceLinkedItem, ...] = ()
    dag_state: dict[str, Any] = field(default_factory=dict)
    staged_state: dict[str, Any] = field(default_factory=dict)
    build_test_state: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    pending_side_effects: tuple[SourceLinkedItem, ...] = ()
    safety_constraints: tuple[SourceLinkedItem, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_contract:
            raise ContractViolation("context checkpoint must retain the task contract")
        if not self.repository_state:
            raise ContractViolation("context checkpoint must retain repository state")
        for reference in self.evidence_refs:
            require_digest(reference)
        # Validate at the typed boundary, before protocol surfaces can claim
        # an idempotency key or write a CAS object.
        _validate_sections_contract(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_contract": self.task_contract,
            "repository_state": self.repository_state,
            "decisions": [item.to_dict() for item in self.decisions],
            "unresolved": [item.to_dict() for item in self.unresolved],
            "approvals": [item.to_dict() for item in self.approvals],
            "dag_state": self.dag_state,
            "staged_state": self.staged_state,
            "build_test_state": self.build_test_state,
            "evidence_refs": list(self.evidence_refs),
            "pending_side_effects": [item.to_dict() for item in self.pending_side_effects],
            "safety_constraints": [item.to_dict() for item in self.safety_constraints],
        }

    def source_event_ids(self) -> frozenset[str]:
        items = self.decisions + self.unresolved + self.approvals + self.pending_side_effects + self.safety_constraints
        return frozenset(event_id for item in items for event_id in item.source_event_ids)

    def external_artifact_refs(self) -> tuple[str, ...]:
        items = self.decisions + self.unresolved + self.approvals + self.pending_side_effects + self.safety_constraints
        references = set(self.evidence_refs)
        references.update(reference for item in items for reference in item.artifact_refs)
        return tuple(sorted(references))


@dataclass(frozen=True)
class ContextCheckpoint:
    tenant_id: str
    project_id: str
    stream_id: str
    checkpoint_id: str
    ledger_sequence: int
    ledger_head_digest: str | None
    repository_snapshot_digest: str
    compatibility_group: str
    source_sequence_start: int
    source_sequence_end: int
    sections: dict[str, Any]
    external_artifact_refs: tuple[str, ...]
    checkpoint_digest: str
    previous_checkpoint_id: str | None
    status: ContextCheckpointStatus
    warm_evidence_digest: str | None
    created_at: float
    warmed_at: float | None
    adopted_at: float | None
    rolled_back_at: float | None


class ContextCompactionService:
    """Prepare, warm, atomically adopt and roll back durable checkpoints."""

    def __init__(
        self,
        ledger: RepositoryContextLedger,
        policy: CompactionPolicy,
        *,
        cas: ContentAddressableStore | None = None,
        ownership: ContextArtifactOwnershipReader | None = None,
        warm_trust_verifier: ContextWarmTrustVerifier | None = None,
    ) -> None:
        self.ledger = ledger
        self.store = ledger.store
        self.policy = policy
        self.cas = cas
        self.ownership = ownership
        self.warm_trust_verifier = warm_trust_verifier

    def prepare(
        self,
        sections: ContextCheckpointSections,
        *,
        compatibility_group: str,
        expected_sequence: int | None = None,
    ) -> ContextCheckpoint:
        group = self._required_text(compatibility_group, "compatibility_group")
        if self.cas is None or self.ownership is None:
            raise ContractViolation("context checkpoint preparation requires explicit tenant CAS ownership")
        self.ledger.validate_chain()
        position = self.ledger.position()
        if position.sequence < 1:
            raise ContractViolation("a context checkpoint requires at least one ledger event")
        if expected_sequence is not None and expected_sequence != position.sequence:
            raise VersionConflict(
                "context changed before checkpoint preparation",
                expected=expected_sequence,
                actual=position.sequence,
            )
        repository_digest = sections.repository_state.get("repository_snapshot_digest")
        if repository_digest != self.ledger.repository_snapshot_digest:
            raise ConflictError("checkpoint repository state is bound to another snapshot")

        event_ids = {event.event_id for event in self.ledger.events()}
        missing = sorted(sections.source_event_ids() - event_ids)
        if missing:
            raise NotFound("checkpoint references context events outside this stream", event_ids=missing)

        previous = self.active()
        section_document = self._normalized_mapping(sections.to_dict(), "checkpoint sections")
        _validate_sections_contract(section_document)
        section_manifest = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "kind": CHECKPOINT_SECTIONS_KIND,
            "tenant_id": self.ledger.tenant_id,
            "project_id": self.ledger.project_id,
            "stream_id": self.ledger.stream_id,
            "repository_snapshot_digest": self.ledger.repository_snapshot_digest,
            "compatibility_group": group,
            "sections": section_document,
        }
        section_bytes = canonical_json_bytes(section_manifest)
        section_digest = self.cas.put_bytes(
            section_bytes,
            artifact_kind="context-checkpoint-sections",
        )
        metadata_sections = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "kind": CHECKPOINT_SECTIONS_REF_KIND,
            "manifest_digest": section_digest,
            "size_bytes": len(section_bytes),
        }
        external_refs = tuple(sorted({*sections.external_artifact_refs(), section_digest}))
        body = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "tenant_id": self.ledger.tenant_id,
            "project_id": self.ledger.project_id,
            "stream_id": self.ledger.stream_id,
            "branch_lineage": self.ledger.branch_lineage,
            "ledger_sequence": position.sequence,
            "ledger_head_digest": position.head_event_digest,
            "repository_snapshot_digest": self.ledger.repository_snapshot_digest,
            "compatibility_group": group,
            "source_sequence_range": [1, position.sequence],
            "sections": metadata_sections,
            "external_artifact_refs": list(external_refs),
            "previous_checkpoint_id": None if previous is None else previous.checkpoint_id,
        }
        checkpoint_digest = digest_of(body)
        checkpoint_id = "ctxcp_" + checkpoint_digest.removeprefix("sha256:")
        now = self.store.now()

        with self.store.transaction():
            existing = self._find_by_digest(checkpoint_digest)
            if existing is not None:
                return existing
            self.store.execute(
                "INSERT INTO context_checkpoints (tenant_id, project_id, stream_id, checkpoint_id,"
                " ledger_sequence, ledger_head_digest, repository_snapshot_digest,"
                " compatibility_group, source_sequence_start, source_sequence_end, sections,"
                " external_artifact_refs, checkpoint_digest, previous_checkpoint_id, status,"
                " warm_evidence_digest, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
                (
                    *self._scope(),
                    checkpoint_id,
                    position.sequence,
                    position.head_event_digest,
                    self.ledger.repository_snapshot_digest,
                    group,
                    1,
                    position.sequence,
                    canonical_json_text(metadata_sections),
                    canonical_json_text(list(external_refs)),
                    checkpoint_digest,
                    None if previous is None else previous.checkpoint_id,
                    ContextCheckpointStatus.PREPARED.value,
                    now,
                ),
            )
            self.store.register_artifact(
                self.ledger.tenant_id,
                section_digest,
                len(section_bytes),
                "application/json",
                "context-checkpoint-sections",
                metadata={
                    "project_id": self.ledger.project_id,
                    "stream_id": self.ledger.stream_id,
                    "checkpoint_id": checkpoint_id,
                },
            )
            self.store.add_artifact_ref(
                self.ledger.tenant_id,
                CHECKPOINT_ARTIFACT_SOURCE_KIND,
                checkpoint_id,
                section_digest,
                "sections-manifest",
            )
        return self.get(checkpoint_id)

    def mark_warmed(self, checkpoint_id: str, warm_evidence_digest: str) -> ContextCheckpoint:
        evidence = require_digest(warm_evidence_digest)
        with self.store.transaction():
            checkpoint = self.get(checkpoint_id)
            self._verify_warm_evidence(checkpoint, evidence)
            if checkpoint.status in {
                ContextCheckpointStatus.WARMED,
                ContextCheckpointStatus.ACTIVE,
                ContextCheckpointStatus.SUPERSEDED,
            }:
                if checkpoint.warm_evidence_digest != evidence:
                    raise ConflictError("checkpoint was warmed with different evidence")
                return checkpoint
            if checkpoint.status is not ContextCheckpointStatus.PREPARED:
                raise ConflictError("only a prepared checkpoint can be warmed")
            cursor = self.store.execute(
                "UPDATE context_checkpoints SET status=?, warm_evidence_digest=?, warmed_at=?"
                " WHERE tenant_id=? AND project_id=? AND stream_id=? AND checkpoint_id=?"
                " AND status=?",
                (
                    ContextCheckpointStatus.WARMED.value,
                    evidence,
                    self.store.now(),
                    *self._scope(),
                    checkpoint_id,
                    ContextCheckpointStatus.PREPARED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise VersionConflict("checkpoint warm-up lost a concurrent race")
        return self.get(checkpoint_id)

    def adopt(
        self,
        checkpoint_id: str,
        *,
        expected_active_checkpoint_id: str | None = None,
    ) -> ContextCheckpoint:
        with self.store.transaction():
            checkpoint = self.get(checkpoint_id)
            if checkpoint.status is not ContextCheckpointStatus.WARMED:
                raise ConflictError("checkpoint must be durably warmed before adoption")
            if checkpoint.warm_evidence_digest is None:
                raise CorruptObject("warmed checkpoint is missing immutable warm evidence")
            self._verify_warm_evidence(checkpoint, checkpoint.warm_evidence_digest)
            stream = self._stream_state()
            active_id = None if stream[2] is None else str(stream[2])
            if expected_active_checkpoint_id != active_id:
                raise VersionConflict(
                    "active context checkpoint changed before adoption",
                    expected=expected_active_checkpoint_id,
                    actual=active_id,
                )
            if checkpoint.previous_checkpoint_id != active_id:
                raise VersionConflict("checkpoint was prepared against another active checkpoint")
            if int(stream[0]) != checkpoint.ledger_sequence or stream[1] != checkpoint.ledger_head_digest:
                raise VersionConflict("context ledger advanced after checkpoint preparation")

            cursor = self.store.execute(
                "UPDATE context_ledger_streams SET active_checkpoint_id=?, updated_at=?"
                " WHERE tenant_id=? AND project_id=? AND stream_id=? AND current_sequence=?"
                " AND (active_checkpoint_id=? OR (active_checkpoint_id IS NULL AND ? IS NULL))",
                (
                    checkpoint_id,
                    self.store.now(),
                    *self._scope(),
                    checkpoint.ledger_sequence,
                    active_id,
                    active_id,
                ),
            )
            if cursor.rowcount != 1:
                raise VersionConflict("checkpoint adoption lost a concurrent race")
            if active_id is not None:
                superseded = self.store.execute(
                    "UPDATE context_checkpoints SET status=? WHERE tenant_id=? AND project_id=?"
                    " AND stream_id=? AND checkpoint_id=? AND status=?",
                    (
                        ContextCheckpointStatus.SUPERSEDED.value,
                        *self._scope(),
                        active_id,
                        ContextCheckpointStatus.ACTIVE.value,
                    ),
                )
                if superseded.rowcount != 1:
                    raise VersionConflict("previous checkpoint status changed during adoption")
            updated = self.store.execute(
                "UPDATE context_checkpoints SET status=?, adopted_at=? WHERE tenant_id=?"
                " AND project_id=? AND stream_id=? AND checkpoint_id=? AND status=?",
                (
                    ContextCheckpointStatus.ACTIVE.value,
                    self.store.now(),
                    *self._scope(),
                    checkpoint_id,
                    ContextCheckpointStatus.WARMED.value,
                ),
            )
            if updated.rowcount != 1:
                raise VersionConflict("checkpoint status changed during adoption")
        return self.get(checkpoint_id)

    def rollback(self, checkpoint_id: str) -> ContextCheckpoint:
        with self.store.transaction():
            current, previous = self.validate_rollback(checkpoint_id)
            cursor = self.store.execute(
                "UPDATE context_ledger_streams SET active_checkpoint_id=?, updated_at=?"
                " WHERE tenant_id=? AND project_id=? AND stream_id=? AND active_checkpoint_id=?",
                (
                    previous.checkpoint_id,
                    self.store.now(),
                    *self._scope(),
                    checkpoint_id,
                ),
            )
            if cursor.rowcount != 1:
                raise VersionConflict("checkpoint rollback lost a concurrent race")
            rolled_back = self.store.execute(
                "UPDATE context_checkpoints SET status=?, rolled_back_at=? WHERE tenant_id=?"
                " AND project_id=? AND stream_id=? AND checkpoint_id=? AND status=?",
                (
                    ContextCheckpointStatus.ROLLED_BACK.value,
                    self.store.now(),
                    *self._scope(),
                    checkpoint_id,
                    ContextCheckpointStatus.ACTIVE.value,
                ),
            )
            if rolled_back.rowcount != 1:
                raise VersionConflict("active checkpoint status changed during rollback")
            restored = self.store.execute(
                "UPDATE context_checkpoints SET status=?, adopted_at=? WHERE tenant_id=?"
                " AND project_id=? AND stream_id=? AND checkpoint_id=? AND status=?",
                (
                    ContextCheckpointStatus.ACTIVE.value,
                    self.store.now(),
                    *self._scope(),
                    previous.checkpoint_id,
                    ContextCheckpointStatus.SUPERSEDED.value,
                ),
            )
            if restored.rowcount != 1:
                raise VersionConflict("rollback predecessor changed concurrently")
        return self.get(previous.checkpoint_id)

    def validate_rollback(
        self,
        checkpoint_id: str,
    ) -> tuple[ContextCheckpoint, ContextCheckpoint]:
        """Verify a rollback target and its independently warmed predecessor.

        This read-only preflight is intentionally public so protocol surfaces
        can reject missing, cross-scope, stale or untrusted targets before
        claiming an idempotency key.  :meth:`rollback` repeats it inside the
        transaction to close the time-of-check/time-of-use race.
        """

        current = self.get(checkpoint_id)
        if current.status is not ContextCheckpointStatus.ACTIVE:
            raise ConflictError("only the active checkpoint can be rolled back")
        if current.previous_checkpoint_id is None:
            raise ConflictError("the initial checkpoint has no rollback predecessor")
        previous = self.get(current.previous_checkpoint_id)
        if previous.status is not ContextCheckpointStatus.SUPERSEDED:
            raise ConflictError("rollback predecessor is not recoverable")
        self.verify_warm_evidence(previous.checkpoint_id)
        stream = self._stream_state()
        if stream[2] != checkpoint_id:
            raise VersionConflict("stream active checkpoint changed before rollback")
        return current, previous

    def verify_warm_evidence(self, checkpoint_id: str) -> ContextCheckpoint:
        """Revalidate a checkpoint's immutable warm evidence without mutation."""

        checkpoint = self.get(checkpoint_id)
        if checkpoint.warm_evidence_digest is None:
            raise CorruptObject("checkpoint is missing immutable warm evidence")
        self._verify_warm_evidence(checkpoint, checkpoint.warm_evidence_digest)
        return checkpoint

    def verify_artifact_reference(self, artifact_digest: str) -> str:
        """Verify one referenced artifact is tenant-owned and byte-correct."""

        normalized = require_digest(artifact_digest)
        self._tenant_registered_bytes(normalized)
        return normalized

    def active(self) -> ContextCheckpoint | None:
        row = self.store.query_one(
            "SELECT active_checkpoint_id FROM context_ledger_streams WHERE tenant_id=?"
            " AND project_id=? AND stream_id=?",
            self._scope(),
        )
        if row is None:
            raise NotFound("context stream does not exist")
        return None if row[0] is None else self.get(str(row[0]))

    def get(self, checkpoint_id: str) -> ContextCheckpoint:
        row = self.store.query_one(
            "SELECT checkpoint_id, ledger_sequence, ledger_head_digest,"
            " repository_snapshot_digest, compatibility_group, source_sequence_start,"
            " source_sequence_end, sections, external_artifact_refs, checkpoint_digest,"
            " previous_checkpoint_id, status, warm_evidence_digest, created_at, warmed_at,"
            " adopted_at, rolled_back_at FROM context_checkpoints WHERE tenant_id=?"
            " AND project_id=? AND stream_id=? AND checkpoint_id=?",
            (*self._scope(), checkpoint_id),
        )
        if row is None:
            raise NotFound("context checkpoint does not exist", checkpoint_id=checkpoint_id)
        stored_sections = self._decode_mapping(row[7], "checkpoint sections")
        references = self._decode_list(row[8], "external artifact refs")
        if any(not isinstance(value, str) for value in references):
            raise CorruptObject("context checkpoint artifact references are malformed")
        normalized_references = tuple(require_digest(str(value)) for value in references)
        stored_checkpoint_id = str(row[0])
        ledger_sequence = int(row[1])
        source_start = int(row[5])
        source_end = int(row[6])
        checkpoint_digest = require_digest(str(row[9]))
        previous_checkpoint_id = None if row[10] is None else str(row[10])
        checkpoint_body = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "tenant_id": self.ledger.tenant_id,
            "project_id": self.ledger.project_id,
            "stream_id": self.ledger.stream_id,
            "branch_lineage": self.ledger.branch_lineage,
            "ledger_sequence": ledger_sequence,
            "ledger_head_digest": None if row[2] is None else str(row[2]),
            "repository_snapshot_digest": str(row[3]),
            "compatibility_group": str(row[4]),
            "source_sequence_range": [source_start, source_end],
            "sections": stored_sections,
            "external_artifact_refs": list(normalized_references),
            "previous_checkpoint_id": previous_checkpoint_id,
        }
        if digest_of(checkpoint_body) != checkpoint_digest:
            raise CorruptObject("context checkpoint digest does not bind the stored contract")
        expected_checkpoint_id = "ctxcp_" + checkpoint_digest.removeprefix("sha256:")
        if stored_checkpoint_id != expected_checkpoint_id:
            raise CorruptObject("context checkpoint identifier does not match its digest")
        sections = self._resolve_sections(
            stored_checkpoint_id,
            str(row[3]),
            str(row[4]),
            stored_sections,
        )
        return ContextCheckpoint(
            tenant_id=self.ledger.tenant_id,
            project_id=self.ledger.project_id,
            stream_id=self.ledger.stream_id,
            checkpoint_id=stored_checkpoint_id,
            ledger_sequence=ledger_sequence,
            ledger_head_digest=None if row[2] is None else str(row[2]),
            repository_snapshot_digest=str(row[3]),
            compatibility_group=str(row[4]),
            source_sequence_start=source_start,
            source_sequence_end=source_end,
            sections=sections,
            external_artifact_refs=normalized_references,
            checkpoint_digest=checkpoint_digest,
            previous_checkpoint_id=previous_checkpoint_id,
            status=ContextCheckpointStatus(str(row[11])),
            warm_evidence_digest=None if row[12] is None else str(row[12]),
            created_at=float(row[13]),
            warmed_at=None if row[14] is None else float(row[14]),
            adopted_at=None if row[15] is None else float(row[15]),
            rolled_back_at=None if row[16] is None else float(row[16]),
        )

    def _resolve_sections(
        self,
        checkpoint_id: str,
        repository_snapshot_digest: str,
        compatibility_group: str,
        stored: dict[str, Any],
    ) -> dict[str, Any]:
        if stored.get("kind") != CHECKPOINT_SECTIONS_REF_KIND:
            _validate_sections_contract(stored)
            return stored
        if set(stored) != {"schema_version", "kind", "manifest_digest", "size_bytes"}:
            raise CorruptObject("context checkpoint sections reference has an invalid shape")
        if stored.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            raise CorruptObject("context checkpoint sections reference version is unsupported")
        manifest_digest = require_digest(str(stored.get("manifest_digest")))
        size = stored.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise CorruptObject("context checkpoint sections reference size is invalid")
        raw = self._tenant_registered_bytes(manifest_digest)
        self._require_artifact_ref(
            manifest_digest,
            (
                CHECKPOINT_ARTIFACT_SOURCE_KIND,
                checkpoint_id,
                "sections-manifest",
            ),
        )
        if len(raw) != size:
            raise CorruptObject("context checkpoint sections manifest size does not match")
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorruptObject("context checkpoint sections manifest is not JSON") from exc
        expected_fields = {
            "schema_version",
            "kind",
            "tenant_id",
            "project_id",
            "stream_id",
            "repository_snapshot_digest",
            "compatibility_group",
            "sections",
        }
        if not isinstance(manifest, dict) or set(manifest) != expected_fields:
            raise CorruptObject("context checkpoint sections manifest has an invalid shape")
        if (
            manifest.get("schema_version") != CHECKPOINT_SCHEMA_VERSION
            or manifest.get("kind") != CHECKPOINT_SECTIONS_KIND
            or manifest.get("tenant_id") != self.ledger.tenant_id
            or manifest.get("project_id") != self.ledger.project_id
            or manifest.get("stream_id") != self.ledger.stream_id
            or manifest.get("repository_snapshot_digest") != repository_snapshot_digest
            or manifest.get("compatibility_group") != compatibility_group
            or not isinstance(manifest.get("sections"), dict)
        ):
            raise CorruptObject("context checkpoint sections manifest binding is invalid")
        sections = dict(manifest["sections"])
        _validate_sections_contract(sections)
        return sections

    def _verify_warm_evidence(
        self,
        checkpoint: ContextCheckpoint,
        warm_evidence_digest: str,
    ) -> None:
        if self.cas is None or self.ownership is None:
            raise ContractViolation("context warm evidence requires explicit tenant CAS ownership")
        if self.warm_trust_verifier is None:
            raise ContractViolation("context warm evidence trust verifier is unavailable")
        raw_manifest = self._tenant_registered_bytes(warm_evidence_digest)
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractViolation("context warm evidence manifest is not JSON") from exc
        body_fields = {
            "schema_version",
            "kind",
            "tenant_id",
            "project_id",
            "stream_id",
            "checkpoint_id",
            "checkpoint_digest",
            "compatibility_group",
            "tenant_scope_digest",
            "authorization_digest",
            "executor_identity",
            "verifier_identity",
            "status",
            "raw_evidence",
            "issued_at",
            "expires_at",
        }
        if not isinstance(manifest, dict) or set(manifest) != body_fields | {"attestation"}:
            raise ContractViolation("context warm evidence manifest has an invalid closed shape")
        body = {name: manifest[name] for name in body_fields}
        expected_scope = digest_of({"tenant_id": self.ledger.tenant_id, "project_id": self.ledger.project_id})
        if (
            body["schema_version"] != CHECKPOINT_SCHEMA_VERSION
            or body["kind"] != WARM_RESULT_KIND
            or body["tenant_id"] != self.ledger.tenant_id
            or body["project_id"] != self.ledger.project_id
            or body["stream_id"] != self.ledger.stream_id
            or body["checkpoint_id"] != checkpoint.checkpoint_id
            or body["checkpoint_digest"] != checkpoint.checkpoint_digest
            or body["compatibility_group"] != checkpoint.compatibility_group
            or body["tenant_scope_digest"] != expected_scope
            or body["status"] != "PASS"
        ):
            raise ContractViolation("context warm evidence binding does not match the checkpoint")
        authorization_digest = require_digest(str(body["authorization_digest"]))
        executor_identity = self._required_text(str(body["executor_identity"]), "executor_identity")
        verifier_identity = self._required_text(str(body["verifier_identity"]), "verifier_identity")
        if executor_identity == verifier_identity:
            raise ContractViolation("context warm executor and verifier must be independent")
        issued_at = body["issued_at"]
        expires_at = body["expires_at"]
        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, int | float)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int | float)
            or not math.isfinite(float(issued_at))
            or not math.isfinite(float(expires_at))
            or float(expires_at) <= float(issued_at)
            or self.store.now() < float(issued_at) - 300.0
            or self.store.now() >= float(expires_at)
        ):
            raise ContractViolation("context warm evidence is expired or not yet valid")
        evidence_ref = (
            WARM_ARTIFACT_SOURCE_KIND,
            authorization_digest,
            context_warm_ref_kind(
                self.ledger.project_id,
                self.ledger.stream_id,
                checkpoint.checkpoint_id,
            ),
        )
        self._require_artifact_ref(warm_evidence_digest, evidence_ref)
        self._tenant_registered_bytes(authorization_digest)
        self._require_artifact_ref(authorization_digest, evidence_ref)

        raw_evidence = body["raw_evidence"]
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise ContractViolation("context warm evidence requires real raw evidence")
        roles: set[str] = set()
        raw_digests: set[str] = set()
        for item in raw_evidence:
            if not isinstance(item, dict) or set(item) != {
                "role",
                "media_type",
                "digest",
                "size",
            }:
                raise ContractViolation("context warm raw evidence has an invalid shape")
            role = item["role"]
            media_type = item["media_type"]
            digest = require_digest(str(item["digest"]))
            size = item["size"]
            if (
                not isinstance(role, str)
                or not role
                or role in roles
                or not isinstance(media_type, str)
                or not media_type
                or isinstance(size, bool)
                or not isinstance(size, int)
                or size < 1
                or digest in raw_digests
                or digest in {authorization_digest, warm_evidence_digest}
            ):
                raise ContractViolation("context warm raw evidence is invalid")
            raw = self._tenant_registered_bytes(digest)
            self._require_artifact_ref(digest, evidence_ref)
            if len(raw) != size:
                raise ContractViolation("context warm raw evidence size does not match")
            roles.add(role)
            raw_digests.add(digest)

        attestation_value = manifest["attestation"]
        if not isinstance(attestation_value, dict) or set(attestation_value) != {
            "kind",
            "statement",
            "signature",
            "key_id",
            "algorithm",
        }:
            raise ContractViolation("context warm evidence attestation has an invalid shape")
        try:
            signed = SignedStatement.from_dict(attestation_value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractViolation("context warm evidence attestation is malformed") from exc
        if signed.kind != WARM_ATTESTATION_KIND or signed.algorithm != "ed25519":
            raise ContractViolation("context warm evidence requires an Ed25519 attestation")
        expected_statement = context_warm_attestation_statement(body)
        if signed.statement != expected_statement:
            raise ContractViolation("context warm evidence attestation binding is invalid")
        try:
            self.warm_trust_verifier.verify(
                signed,
                expected_verifier_identity=verifier_identity,
            )
        except Exception as exc:  # noqa: BLE001 - trust failures are fail-closed
            raise ContractViolation("context warm evidence attestation is untrusted") from exc

    def _tenant_registered_bytes(self, digest: str) -> bytes:
        if self.cas is None or self.ownership is None:
            raise ContractViolation("context artifact access requires explicit tenant ownership")
        normalized = require_digest(digest)
        try:
            registration = self.ownership.get_artifact(self.ledger.tenant_id, normalized)
        except Exception as exc:  # noqa: BLE001 - ownership failures are non-success
            raise ContractViolation("context artifact ownership lookup failed") from exc
        if (
            registration is None
            or registration.tenant_id != self.ledger.tenant_id
            or registration.digest != normalized
            or str(registration.storage_state) not in {"LOCAL", "REMOTE"}
            or str(registration.validation_level) == "QUARANTINED"
        ):
            raise ContractViolation("context artifact is not owned and usable in this tenant")
        try:
            raw = self.cas.get_bytes(normalized, verify=True)
        except Exception as exc:  # noqa: BLE001 - corrupt/missing CAS fails closed
            raise CorruptObject("context artifact failed CAS verification", digest=normalized) from exc
        if not raw or registration.size_bytes != len(raw):
            raise CorruptObject("context artifact registration size does not match CAS bytes")
        return raw

    def _require_artifact_ref(
        self,
        digest: str,
        expected: tuple[str, str, str],
    ) -> None:
        assert self.ownership is not None
        try:
            references = self.ownership.artifact_referrers(self.ledger.tenant_id, digest)
        except Exception as exc:  # noqa: BLE001 - ownership failures are non-success
            raise ContractViolation("context artifact reference lookup failed") from exc
        if expected not in references:
            raise ContractViolation("context artifact lacks the exact tenant authorization reference")

    def _find_by_digest(self, checkpoint_digest: str) -> ContextCheckpoint | None:
        row = self.store.query_one(
            "SELECT checkpoint_id FROM context_checkpoints WHERE tenant_id=? AND project_id=?"
            " AND stream_id=? AND checkpoint_digest=?",
            (*self._scope(), checkpoint_digest),
        )
        return None if row is None else self.get(str(row[0]))

    def _stream_state(self) -> Any:
        row = self.store.query_one(
            "SELECT current_sequence, head_event_digest, active_checkpoint_id"
            " FROM context_ledger_streams WHERE tenant_id=? AND project_id=? AND stream_id=?",
            self._scope(),
        )
        if row is None:
            raise NotFound("context ledger stream does not exist")
        return row

    def _scope(self) -> tuple[str, str, str]:
        return self.ledger.tenant_id, self.ledger.project_id, self.ledger.stream_id

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ContractViolation(f"{field_name} must be non-blank and at most 512 characters")
        return value

    @staticmethod
    def _normalized_mapping(value: dict[str, Any], label: str) -> dict[str, Any]:
        try:
            normalized = json.loads(canonical_json_text(value))
        except (TypeError, ValueError) as exc:
            raise ContractViolation(f"{label} must be JSON serializable and cannot contain raw bytes") from exc
        if not isinstance(normalized, dict):
            raise ContractViolation(f"{label} must be an object")
        return normalized

    @staticmethod
    def _decode_mapping(value: Any, label: str) -> dict[str, Any]:
        decoded = value if isinstance(value, dict) else json.loads(str(value))
        if not isinstance(decoded, dict):
            raise ContractViolation(f"{label} is not an object")
        return decoded

    @staticmethod
    def _decode_list(value: Any, label: str) -> list[Any]:
        decoded = value if isinstance(value, list) else json.loads(str(value))
        if not isinstance(decoded, list):
            raise ContractViolation(f"{label} is not an array")
        return decoded


__all__ = [
    "CHECKPOINT_SECTIONS_KIND",
    "CHECKPOINT_SECTIONS_REF_KIND",
    "WARM_ATTESTATION_KIND",
    "WARM_RESULT_KIND",
    "CompactionNeed",
    "CompactionPolicy",
    "ContextArtifactOwnershipReader",
    "ContextCheckpoint",
    "ContextCheckpointSections",
    "ContextCheckpointStatus",
    "ContextCompactionService",
    "ContextWarmTrustVerifier",
    "Ed25519ContextWarmTrustVerifier",
    "SourceLinkedItem",
    "context_warm_attestation_statement",
    "context_warm_ref_kind",
]
