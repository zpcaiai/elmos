"""Typed local runtime joining context events, prompt projection and compaction.

The durable ledger receives only paths, bounded identifiers and digests.  Raw
repository/tool content is resolved on demand through an injected resolver and
remains in transient ``ContextPromptFragment`` objects.  The default resolver is
deterministic and metadata-only; this module performs no network or provider
calls.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .canonical import (
    canonical_json_text,
    digest_of,
    normalize_logical_path,
    require_digest,
    sha256_bytes,
)
from .context_compaction import (
    CompactionNeed,
    CompactionPolicy,
    ContextCheckpoint,
)
from .context_ledger import (
    ContextEventType,
    ContextLedgerEvent,
    RepositoryContextLedger,
)
from .errors import ContractViolation, CorruptObject
from .prompt_runtime import ContextPromptFragment

CONTEXT_RUNTIME_SCHEMA_VERSION = "1.0.0"
MAX_RESOLVED_CONTEXT_BYTES = 1 * 1024 * 1024

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
# The projection is deliberately complete.  A checkpoint, summary, snapshot
# binding, or compaction decision is part of the replayable context history;
# silently dropping one would make a restarted worker produce a different
# prompt and would hide freshness/rollback evidence from the model turn.
_PROJECTED_EVENTS = frozenset(ContextEventType)


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _external_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 4_096:
        raise ContractViolation("context runtime idempotency key is invalid")
    return value


class FileObservationKind(StrEnum):
    READ = ContextEventType.FILE_READ.value
    REREAD = ContextEventType.CONTENT_REREAD.value


class ChangeObservationKind(StrEnum):
    CHANGED = ContextEventType.CONTENT_CHANGED.value
    STALE = ContextEventType.CONTEXT_STALE.value


@dataclass(frozen=True)
class FileContextObservation:
    kind: FileObservationKind
    logical_path: str
    content_digest: str
    idempotency_key: str
    supersedes_event_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FileObservationKind):
            raise ContractViolation("file observation kind is invalid")
        object.__setattr__(self, "logical_path", normalize_logical_path(self.logical_path))
        object.__setattr__(self, "content_digest", require_digest(self.content_digest))
        object.__setattr__(
            self,
            "idempotency_key",
            _external_idempotency_key(self.idempotency_key),
        )
        if self.supersedes_event_id is not None:
            object.__setattr__(
                self,
                "supersedes_event_id",
                _identifier(self.supersedes_event_id, "supersedes_event_id"),
            )


@dataclass(frozen=True)
class ToolContextObservation:
    tool: str
    idempotency_key: str
    result_digest: str | None = None
    status: str | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool", _identifier(self.tool, "tool"))
        object.__setattr__(
            self,
            "idempotency_key",
            _external_idempotency_key(self.idempotency_key),
        )
        if self.result_digest is not None:
            object.__setattr__(self, "result_digest", require_digest(self.result_digest))
        if self.status is not None:
            object.__setattr__(self, "status", _identifier(self.status, "status"))
        if self.duration_ms is not None and (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, int)
            or self.duration_ms < 0
        ):
            raise ContractViolation("tool duration must be a non-negative integer")


@dataclass(frozen=True)
class ValidationContextObservation:
    validation_level: str
    idempotency_key: str
    result_digest: str | None = None
    status: str | None = None
    suite_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "validation_level",
            _identifier(self.validation_level, "validation_level"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _external_idempotency_key(self.idempotency_key),
        )
        if self.result_digest is not None:
            object.__setattr__(self, "result_digest", require_digest(self.result_digest))
        if self.status is not None:
            object.__setattr__(self, "status", _identifier(self.status, "status"))
        if self.suite_id is not None:
            object.__setattr__(self, "suite_id", _identifier(self.suite_id, "suite_id"))


@dataclass(frozen=True)
class ChangeContextObservation:
    kind: ChangeObservationKind
    logical_path: str
    idempotency_key: str
    content_digest: str | None = None
    supersedes_event_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ChangeObservationKind):
            raise ContractViolation("change observation kind is invalid")
        object.__setattr__(self, "logical_path", normalize_logical_path(self.logical_path))
        object.__setattr__(
            self,
            "idempotency_key",
            _external_idempotency_key(self.idempotency_key),
        )
        if self.content_digest is not None:
            object.__setattr__(self, "content_digest", require_digest(self.content_digest))
        if self.supersedes_event_id is not None:
            object.__setattr__(
                self,
                "supersedes_event_id",
                _identifier(self.supersedes_event_id, "supersedes_event_id"),
            )


@dataclass(frozen=True)
class SnapshotBoundContextObservation:
    """Bind a stream to the repository snapshot used by the observation."""

    snapshot_digest: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_digest", require_digest(self.snapshot_digest))
        object.__setattr__(
            self,
            "idempotency_key",
            _external_idempotency_key(self.idempotency_key),
        )


@dataclass(frozen=True)
class SymbolContextObservation:
    """Record a symbol/public-interface read without persisting source text."""

    symbol_ref: str
    logical_path: str
    symbol_digest: str
    content_digest: str
    idempotency_key: str
    source_event_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol_ref", _identifier(self.symbol_ref, "symbol_ref"))
        object.__setattr__(self, "logical_path", normalize_logical_path(self.logical_path))
        object.__setattr__(self, "symbol_digest", require_digest(self.symbol_digest))
        object.__setattr__(self, "content_digest", require_digest(self.content_digest))
        object.__setattr__(
            self,
            "idempotency_key",
            _external_idempotency_key(self.idempotency_key),
        )
        object.__setattr__(self, "source_event_id", _identifier(self.source_event_id, "source_event_id"))


@dataclass(frozen=True)
class SummaryContextObservation:
    """Record a digest-bound summary and the events it summarizes."""

    summary_digest: str
    source_event_ids: tuple[str, ...]
    idempotency_key: str
    token_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary_digest", require_digest(self.summary_digest))
        source_ids = tuple(_identifier(item, "source_event_ids") for item in self.source_event_ids)
        if not source_ids or len(source_ids) != len(set(source_ids)):
            raise ContractViolation("summary source_event_ids must be non-empty and unique")
        object.__setattr__(self, "source_event_ids", source_ids)
        object.__setattr__(
            self,
            "idempotency_key",
            _external_idempotency_key(self.idempotency_key),
        )
        if isinstance(self.token_count, bool) or not isinstance(self.token_count, int) or self.token_count < 0:
            raise ContractViolation("summary token_count must be a non-negative integer")


@dataclass(frozen=True)
class CheckpointContextObservation:
    """Record a resumable context checkpoint with an exact ledger position."""

    checkpoint_id: str
    checkpoint_digest: str
    source_event_ids: tuple[str, ...]
    ledger_sequence: int
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "checkpoint_id", _identifier(self.checkpoint_id, "checkpoint_id"))
        object.__setattr__(self, "checkpoint_digest", require_digest(self.checkpoint_digest))
        source_ids = tuple(_identifier(item, "source_event_ids") for item in self.source_event_ids)
        if len(source_ids) != len(set(source_ids)):
            raise ContractViolation("checkpoint source_event_ids must be unique")
        object.__setattr__(self, "source_event_ids", source_ids)
        if (
            isinstance(self.ledger_sequence, bool)
            or not isinstance(self.ledger_sequence, int)
            or self.ledger_sequence < 0
        ):
            raise ContractViolation("checkpoint ledger_sequence must be a non-negative integer")
        object.__setattr__(
            self,
            "idempotency_key",
            _external_idempotency_key(self.idempotency_key),
        )


ContextObservation = (
    FileContextObservation
    | ToolContextObservation
    | ValidationContextObservation
    | ChangeContextObservation
    | SnapshotBoundContextObservation
    | SymbolContextObservation
    | SummaryContextObservation
    | CheckpointContextObservation
)


@dataclass(frozen=True)
class ResolvedContextContent:
    """Resolver result with all scope and resource bindings made explicit."""

    tenant_id: str
    project_id: str
    stream_id: str
    repository_snapshot_digest: str
    event_id: str
    event_digest: str
    content: str
    content_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _identifier(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "project_id", _identifier(self.project_id, "project_id"))
        object.__setattr__(self, "stream_id", _identifier(self.stream_id, "stream_id"))
        object.__setattr__(
            self,
            "repository_snapshot_digest",
            require_digest(self.repository_snapshot_digest),
        )
        object.__setattr__(self, "event_id", _identifier(self.event_id, "event_id"))
        object.__setattr__(self, "event_digest", require_digest(self.event_digest))
        if not isinstance(self.content, str):
            raise ContractViolation("resolved context content must be text")
        normalized = unicodedata.normalize(
            "NFC",
            self.content.replace("\r\n", "\n").replace("\r", "\n"),
        )
        if not normalized.strip() or len(normalized.encode("utf-8")) > MAX_RESOLVED_CONTEXT_BYTES:
            raise ContractViolation("resolved context content is empty or too large")
        object.__setattr__(self, "content", normalized)
        expected = sha256_bytes(normalized.encode("utf-8"))
        if require_digest(self.content_digest) != expected:
            raise ContractViolation("resolved context content digest does not match its bytes")

    @classmethod
    def for_event(cls, event: ContextLedgerEvent, content: str) -> ResolvedContextContent:
        normalized = unicodedata.normalize(
            "NFC",
            content.replace("\r\n", "\n").replace("\r", "\n"),
        )
        return cls(
            tenant_id=event.tenant_id,
            project_id=event.project_id,
            stream_id=event.stream_id,
            repository_snapshot_digest=event.repository_snapshot_digest,
            event_id=event.event_id,
            event_digest=event.event_digest,
            content=normalized,
            content_digest=sha256_bytes(normalized.encode("utf-8")),
        )


class ContextContentResolver(Protocol):
    def resolve(self, event: ContextLedgerEvent) -> ResolvedContextContent: ...


class MetadataContextResolver:
    """Deterministic offline fallback containing no repository source bytes."""

    def resolve(self, event: ContextLedgerEvent) -> ResolvedContextContent:
        content = canonical_json_text(
            {
                "event_type": event.event_type.value,
                "sequence": event.sequence,
                "subject_ref": event.subject_ref,
                "payload": event.payload,
                "event_digest": event.event_digest,
            }
        )
        return ResolvedContextContent.for_event(event, content)


@dataclass(frozen=True)
class ContextPromptProjection:
    tenant_id: str
    project_id: str
    stream_id: str
    repository_snapshot_digest: str
    ledger_sequence: int
    ledger_head_digest: str | None
    fragments: tuple[ContextPromptFragment, ...]

    def _manifest_body(self) -> dict[str, Any]:
        return {
            "schema_version": CONTEXT_RUNTIME_SCHEMA_VERSION,
            "kind": "elmos.context-prompt-projection/v1",
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "stream_id": self.stream_id,
            "repository_snapshot_digest": self.repository_snapshot_digest,
            "ledger_sequence": self.ledger_sequence,
            "ledger_head_digest": self.ledger_head_digest,
            "fragments": [fragment.manifest_entry() for fragment in self.fragments],
        }

    @property
    def context_digest(self) -> str:
        return digest_of(self._manifest_body())

    def manifest(self) -> dict[str, Any]:
        """Content-free replay metadata; fragment content is deliberately absent."""

        return {**self._manifest_body(), "context_digest": self.context_digest}

    @staticmethod
    def assert_append_only_successor(
        previous: ContextPromptProjection,
        current: ContextPromptProjection,
    ) -> None:
        if (
            previous.tenant_id,
            previous.project_id,
            previous.stream_id,
            previous.repository_snapshot_digest,
        ) != (
            current.tenant_id,
            current.project_id,
            current.stream_id,
            current.repository_snapshot_digest,
        ):
            raise ContractViolation("context projection scope changed across continuation")
        if current.fragments[: len(previous.fragments)] != previous.fragments:
            raise ContractViolation("context projection rewrote an append-only fragment")


class RepositoryContextRuntime:
    """Append typed observations and project their exact ledger replay to prompt context."""

    def __init__(
        self,
        ledger: RepositoryContextLedger,
        resolver: ContextContentResolver | None = None,
    ) -> None:
        if not isinstance(ledger, RepositoryContextLedger):
            raise ContractViolation("context runtime requires RepositoryContextLedger")
        self.ledger = ledger
        self.resolver = resolver or MetadataContextResolver()

    def record(
        self,
        observation: ContextObservation,
        *,
        expected_sequence: int | None = None,
        expected_head_digest: str | None = None,
    ) -> ContextLedgerEvent:
        event_type: ContextEventType
        payload: dict[str, Any]
        supersedes: str | None
        subject_ref: str | None = None
        if isinstance(observation, FileContextObservation):
            event_type = ContextEventType(observation.kind.value)
            payload = {
                "logical_path": observation.logical_path,
                "content_digest": observation.content_digest,
            }
            supersedes = observation.supersedes_event_id
        elif isinstance(observation, ToolContextObservation):
            event_type = ContextEventType.TOOL_OBSERVED
            payload = {"tool": observation.tool}
            for name in ("result_digest", "status", "duration_ms"):
                value = getattr(observation, name)
                if value is not None:
                    payload[name] = value
            supersedes = None
        elif isinstance(observation, ValidationContextObservation):
            event_type = ContextEventType.VALIDATION_OBSERVED
            payload = {"validation_level": observation.validation_level}
            for name in ("result_digest", "status", "suite_id"):
                value = getattr(observation, name)
                if value is not None:
                    payload[name] = value
            supersedes = None
        elif isinstance(observation, ChangeContextObservation):
            event_type = ContextEventType(observation.kind.value)
            payload = {"logical_path": observation.logical_path}
            if observation.content_digest is not None:
                payload["content_digest"] = observation.content_digest
            supersedes = observation.supersedes_event_id
        elif isinstance(observation, SnapshotBoundContextObservation):
            if observation.snapshot_digest != self.ledger.repository_snapshot_digest:
                raise ContractViolation("snapshot binding does not match the context ledger")
            event_type = ContextEventType.SNAPSHOT_BOUND
            payload = {"snapshot_digest": observation.snapshot_digest}
            supersedes = None
        elif isinstance(observation, SymbolContextObservation):
            existing_ids = {event.event_id for event in self.ledger.events()}
            if observation.source_event_id not in existing_ids:
                raise ContractViolation("symbol observation references an unknown source event")
            event_type = ContextEventType.SYMBOL_READ
            payload = {
                "logical_path": observation.logical_path,
                "symbol_digest": observation.symbol_digest,
                "content_digest": observation.content_digest,
                "source_event_id": observation.source_event_id,
            }
            supersedes = None
            subject_ref = observation.symbol_ref
        elif isinstance(observation, SummaryContextObservation):
            existing_ids = {event.event_id for event in self.ledger.events()}
            if any(source_id not in existing_ids for source_id in observation.source_event_ids):
                raise ContractViolation("summary observation references an unknown source event")
            event_type = ContextEventType.SUMMARY_WRITTEN
            payload = {
                "summary_digest": observation.summary_digest,
                "source_event_ids": list(observation.source_event_ids),
                "token_count": observation.token_count,
            }
            supersedes = None
        elif isinstance(observation, CheckpointContextObservation):
            if observation.ledger_sequence > self.ledger.position().sequence:
                raise ContractViolation("checkpoint ledger_sequence is ahead of the ledger")
            existing_ids = {event.event_id for event in self.ledger.events()}
            if any(source_id not in existing_ids for source_id in observation.source_event_ids):
                raise ContractViolation("checkpoint observation references an unknown source event")
            event_type = ContextEventType.CONTEXT_CHECKPOINT
            payload = {
                "checkpoint_id": observation.checkpoint_id,
                "checkpoint_digest": observation.checkpoint_digest,
                "source_event_ids": list(observation.source_event_ids),
                "ledger_sequence": observation.ledger_sequence,
            }
            supersedes = None
        else:
            raise ContractViolation("context runtime observation has an unknown type")

        stored_key = "ctxrt-" + digest_of(
            {
                "tenant_id": self.ledger.tenant_id,
                "project_id": self.ledger.project_id,
                "stream_id": self.ledger.stream_id,
                "external_idempotency_key": observation.idempotency_key,
            }
        ).removeprefix("sha256:")
        return self.ledger.append(
            event_type,
            payload,
            idempotency_key=stored_key,
            expected_sequence=expected_sequence,
            expected_head_digest=expected_head_digest,
            subject_ref=subject_ref,
            supersedes_event_id=supersedes,
        )

    def project(self) -> ContextPromptProjection:
        self.ledger.validate_chain()
        fragments: list[ContextPromptFragment] = []
        for event in self.ledger.events():
            if event.event_type not in _PROJECTED_EVENTS:
                continue
            resolved = self.resolver.resolve(event)
            if not isinstance(resolved, ResolvedContextContent):
                raise ContractViolation("context resolver returned an unknown type")
            self._verify_resolution(event, resolved)
            fragments.append(
                ContextPromptFragment(
                    sequence=event.sequence,
                    event_id=event.event_id,
                    repository_snapshot_digest=event.repository_snapshot_digest,
                    event_digest=event.event_digest,
                    content=resolved.content,
                )
            )
        position = self.ledger.position()
        return ContextPromptProjection(
            tenant_id=self.ledger.tenant_id,
            project_id=self.ledger.project_id,
            stream_id=self.ledger.stream_id,
            repository_snapshot_digest=self.ledger.repository_snapshot_digest,
            ledger_sequence=position.sequence,
            ledger_head_digest=position.head_event_digest,
            fragments=tuple(fragments),
        )

    def _verify_resolution(
        self,
        event: ContextLedgerEvent,
        resolved: ResolvedContextContent,
    ) -> None:
        if (
            resolved.tenant_id != self.ledger.tenant_id
            or resolved.project_id != self.ledger.project_id
            or resolved.stream_id != self.ledger.stream_id
            or resolved.repository_snapshot_digest
            != self.ledger.repository_snapshot_digest
            or resolved.event_id != event.event_id
            or resolved.event_digest != event.event_digest
        ):
            raise ContractViolation("context resolver crossed a scope or resource boundary")
        if sha256_bytes(resolved.content.encode("utf-8")) != resolved.content_digest:
            raise ContractViolation("context resolver bytes changed after verification")


@dataclass(frozen=True)
class PromptContextState:
    prompt_digest: str
    context_digest: str
    checkpoint_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt_digest", require_digest(self.prompt_digest))
        object.__setattr__(self, "context_digest", require_digest(self.context_digest))
        if self.checkpoint_id is not None:
            object.__setattr__(
                self,
                "checkpoint_id",
                _identifier(self.checkpoint_id, "checkpoint_id"),
            )


@dataclass(frozen=True)
class ShadowEquivalenceDecision:
    equivalent: bool
    reason_code: str
    evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.equivalent, bool):
            raise ContractViolation("shadow equivalence decision must be boolean")
        object.__setattr__(self, "reason_code", _identifier(self.reason_code, "reason_code"))
        object.__setattr__(self, "evidence_digest", require_digest(self.evidence_digest))


class ShadowEquivalenceComparator(Protocol):
    def compare(
        self,
        baseline: PromptContextState,
        candidate: PromptContextState,
    ) -> ShadowEquivalenceDecision: ...


class AdoptedContextVerifier(Protocol):
    def verify(self, candidate: PromptContextState) -> bool: ...


class ContextCompactionPort(Protocol):
    @property
    def policy(self) -> CompactionPolicy: ...

    def adopt(
        self,
        checkpoint_id: str,
        *,
        expected_active_checkpoint_id: str | None = None,
    ) -> ContextCheckpoint: ...

    def rollback(self, checkpoint_id: str) -> ContextCheckpoint: ...


class CompactionTransitionStatus(StrEnum):
    NOT_NEEDED = "NOT_NEEDED"
    EQUIVALENCE_REJECTED = "EQUIVALENCE_REJECTED"
    COMPARATOR_FAILED = "COMPARATOR_FAILED"
    ADOPTION_FAILED = "ADOPTION_FAILED"
    ADOPTED = "ADOPTED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class ContextCompactionTransition:
    need: CompactionNeed
    status: CompactionTransitionStatus
    baseline_prompt_digest: str
    candidate_prompt_digest: str
    active_prompt_digest: str
    active_checkpoint_id: str | None
    reason_code: str
    comparison_evidence_digest: str | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": CONTEXT_RUNTIME_SCHEMA_VERSION,
            "kind": "elmos.context-compaction-transition/v1",
            "need": self.need.value,
            "status": self.status.value,
            "baseline_prompt_digest": self.baseline_prompt_digest,
            "candidate_prompt_digest": self.candidate_prompt_digest,
            "active_prompt_digest": self.active_prompt_digest,
            "active_checkpoint_id": self.active_checkpoint_id,
            "reason_code": self.reason_code,
            "comparison_evidence_digest": self.comparison_evidence_digest,
        }


class ContextCompactionRuntime:
    """Threshold, shadow comparison, atomic adoption and rollback orchestration."""

    def __init__(
        self,
        service: ContextCompactionPort,
        comparator: ShadowEquivalenceComparator,
        *,
        adopted_verifier: AdoptedContextVerifier | None = None,
    ) -> None:
        self.service = service
        self.comparator = comparator
        self.adopted_verifier = adopted_verifier

    def transition(
        self,
        *,
        current_tokens: int,
        predicted_next_turn_tokens: int,
        baseline: PromptContextState,
        candidate: PromptContextState,
    ) -> ContextCompactionTransition:
        need = self.service.policy.assess(current_tokens, predicted_next_turn_tokens)
        if need is CompactionNeed.NONE:
            return self._result(
                need,
                CompactionTransitionStatus.NOT_NEEDED,
                baseline,
                candidate,
                baseline,
                "BELOW_COMPACTION_THRESHOLD",
            )
        if candidate.checkpoint_id is None:
            return self._result(
                need,
                CompactionTransitionStatus.ADOPTION_FAILED,
                baseline,
                candidate,
                baseline,
                "CANDIDATE_CHECKPOINT_REQUIRED",
            )
        try:
            comparison = self.comparator.compare(baseline, candidate)
        except Exception:  # noqa: BLE001 - a comparator cannot authorize adoption by failing
            return self._result(
                need,
                CompactionTransitionStatus.COMPARATOR_FAILED,
                baseline,
                candidate,
                baseline,
                "SHADOW_COMPARATOR_FAILED",
            )
        if not isinstance(comparison, ShadowEquivalenceDecision):
            return self._result(
                need,
                CompactionTransitionStatus.COMPARATOR_FAILED,
                baseline,
                candidate,
                baseline,
                "SHADOW_COMPARATOR_INVALID_RESULT",
            )
        if not comparison.equivalent:
            return self._result(
                need,
                CompactionTransitionStatus.EQUIVALENCE_REJECTED,
                baseline,
                candidate,
                baseline,
                comparison.reason_code,
                comparison.evidence_digest,
            )
        try:
            adopted = self.service.adopt(
                candidate.checkpoint_id,
                expected_active_checkpoint_id=baseline.checkpoint_id,
            )
        except Exception:  # noqa: BLE001 - the concrete service is transactionally atomic
            return self._result(
                need,
                CompactionTransitionStatus.ADOPTION_FAILED,
                baseline,
                candidate,
                baseline,
                "CHECKPOINT_ADOPTION_FAILED",
                comparison.evidence_digest,
            )
        if adopted.checkpoint_id != candidate.checkpoint_id:
            self._rollback_or_raise(candidate, baseline)
            return self._result(
                need,
                CompactionTransitionStatus.ROLLED_BACK,
                baseline,
                candidate,
                baseline,
                "ADOPTED_CHECKPOINT_ID_MISMATCH",
                comparison.evidence_digest,
            )
        verification_failed = False
        if self.adopted_verifier is not None:
            try:
                verification_failed = not self.adopted_verifier.verify(candidate)
            except Exception:  # noqa: BLE001 - post-adoption uncertainty requires rollback
                verification_failed = True
        if verification_failed:
            self._rollback_or_raise(candidate, baseline)
            return self._result(
                need,
                CompactionTransitionStatus.ROLLED_BACK,
                baseline,
                candidate,
                baseline,
                "POST_ADOPTION_VERIFICATION_FAILED",
                comparison.evidence_digest,
            )
        return self._result(
            need,
            CompactionTransitionStatus.ADOPTED,
            baseline,
            candidate,
            candidate,
            "SHADOW_EQUIVALENT_CHECKPOINT_ADOPTED",
            comparison.evidence_digest,
        )

    def _rollback_or_raise(
        self,
        candidate: PromptContextState,
        baseline: PromptContextState,
    ) -> None:
        assert candidate.checkpoint_id is not None
        try:
            restored = self.service.rollback(candidate.checkpoint_id)
        except Exception as exc:  # noqa: BLE001 - never claim the original digest if rollback is unknown
            raise CorruptObject(
                "context checkpoint adoption failed verification and rollback is unknown"
            ) from exc
        if baseline.checkpoint_id is None or restored.checkpoint_id != baseline.checkpoint_id:
            raise CorruptObject("context checkpoint rollback did not restore the baseline")

    @staticmethod
    def _result(
        need: CompactionNeed,
        status: CompactionTransitionStatus,
        baseline: PromptContextState,
        candidate: PromptContextState,
        active: PromptContextState,
        reason_code: str,
        evidence_digest: str | None = None,
    ) -> ContextCompactionTransition:
        return ContextCompactionTransition(
            need=need,
            status=status,
            baseline_prompt_digest=baseline.prompt_digest,
            candidate_prompt_digest=candidate.prompt_digest,
            active_prompt_digest=active.prompt_digest,
            active_checkpoint_id=active.checkpoint_id,
            reason_code=_identifier(reason_code, "reason_code"),
            comparison_evidence_digest=evidence_digest,
        )


__all__ = [
    "AdoptedContextVerifier",
    "ChangeContextObservation",
    "ChangeObservationKind",
    "CompactionTransitionStatus",
    "ContextCompactionPort",
    "ContextCompactionRuntime",
    "ContextCompactionTransition",
    "ContextContentResolver",
    "ContextObservation",
    "ContextPromptProjection",
    "CheckpointContextObservation",
    "FileContextObservation",
    "FileObservationKind",
    "MetadataContextResolver",
    "PromptContextState",
    "RepositoryContextRuntime",
    "ResolvedContextContent",
    "SnapshotBoundContextObservation",
    "ShadowEquivalenceComparator",
    "ShadowEquivalenceDecision",
    "SummaryContextObservation",
    "SymbolContextObservation",
    "ToolContextObservation",
    "ValidationContextObservation",
]
