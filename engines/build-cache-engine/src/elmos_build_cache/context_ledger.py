"""Durable, append-only repository context with exact replay semantics.

The ledger stores no source bytes.  It stores immutable, hash-linked facts that
bind an observation to one tenant, project, branch lineage and repository
snapshot.  Content remains in the repository or CAS; the ledger is the durable
provenance and freshness truth used to decide what must be read again.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from .canonical import canonical_json_text, digest_of, normalize_logical_path, require_digest
from .db.store import MetadataStore
from .errors import (
    ConflictError,
    ContractViolation,
    CorruptObject,
    IdempotencyConflict,
    NotFound,
    VersionConflict,
)

LEDGER_SCHEMA_VERSION = "1.2.0"


class ContextEventType(StrEnum):
    SNAPSHOT_BOUND = "SNAPSHOT_BOUND"
    FILE_READ = "FILE_READ"
    SYMBOL_READ = "SYMBOL_READ"
    SUMMARY_WRITTEN = "SUMMARY_WRITTEN"
    CONTENT_CHANGED = "CONTENT_CHANGED"
    CONTEXT_STALE = "CONTEXT_STALE"
    CONTENT_REREAD = "CONTENT_REREAD"
    TOOL_OBSERVED = "TOOL_OBSERVED"
    VALIDATION_OBSERVED = "VALIDATION_OBSERVED"
    CONTEXT_CHECKPOINT = "CONTEXT_CHECKPOINT"
    COMPACTION_COMPLETED = "COMPACTION_COMPLETED"
    COMPACTION_ROLLBACK = "COMPACTION_ROLLBACK"


_EVENT_PAYLOAD_FIELDS: dict[ContextEventType, frozenset[str]] = {
    ContextEventType.SNAPSHOT_BOUND: frozenset({"snapshot_digest"}),
    ContextEventType.FILE_READ: frozenset({"logical_path", "content_digest"}),
    ContextEventType.SYMBOL_READ: frozenset({"logical_path", "symbol_digest", "content_digest", "source_event_id"}),
    ContextEventType.SUMMARY_WRITTEN: frozenset({"summary_digest", "source_event_ids", "token_count"}),
    ContextEventType.CONTENT_CHANGED: frozenset({"logical_path", "content_digest"}),
    ContextEventType.CONTEXT_STALE: frozenset({"logical_path", "content_digest"}),
    ContextEventType.CONTENT_REREAD: frozenset({"logical_path", "content_digest"}),
    ContextEventType.TOOL_OBSERVED: frozenset({"tool", "result_digest", "status", "duration_ms"}),
    ContextEventType.VALIDATION_OBSERVED: frozenset({"validation_level", "result_digest", "status", "suite_id"}),
    ContextEventType.CONTEXT_CHECKPOINT: frozenset(
        {"checkpoint_id", "checkpoint_digest", "source_event_ids", "ledger_sequence"}
    ),
    ContextEventType.COMPACTION_COMPLETED: frozenset(
        {
            "checkpoint_id",
            "checkpoint_digest",
            "source_event_ids",
            "previous_checkpoint_id",
            "tokens_before",
            "tokens_after",
        }
    ),
    ContextEventType.COMPACTION_ROLLBACK: frozenset({"checkpoint_id", "checkpoint_digest", "rollback_event_ids"}),
}
_REQUIRED_EVENT_PAYLOAD_FIELDS: dict[ContextEventType, frozenset[str]] = {
    ContextEventType.SNAPSHOT_BOUND: frozenset({"snapshot_digest"}),
    ContextEventType.FILE_READ: frozenset({"logical_path", "content_digest"}),
    ContextEventType.CONTENT_CHANGED: frozenset({"logical_path"}),
    ContextEventType.CONTEXT_STALE: frozenset({"logical_path"}),
    ContextEventType.CONTENT_REREAD: frozenset({"logical_path", "content_digest"}),
    ContextEventType.TOOL_OBSERVED: frozenset({"tool"}),
    ContextEventType.VALIDATION_OBSERVED: frozenset({"validation_level"}),
    ContextEventType.SUMMARY_WRITTEN: frozenset({"summary_digest", "source_event_ids"}),
    ContextEventType.CONTEXT_CHECKPOINT: frozenset(
        {"checkpoint_id", "checkpoint_digest", "source_event_ids", "ledger_sequence"}
    ),
    ContextEventType.COMPACTION_COMPLETED: frozenset({"checkpoint_id", "checkpoint_digest", "source_event_ids"}),
    ContextEventType.COMPACTION_ROLLBACK: frozenset({"checkpoint_id", "checkpoint_digest", "rollback_event_ids"}),
    # SYMBOL_READ is bound by ``subject_ref`` and may carry any subset of the
    # closed digest/path/source-reference metadata above.
    ContextEventType.SYMBOL_READ: frozenset(),
}
_SAFE_PAYLOAD_KEYS = frozenset().union(*_EVENT_PAYLOAD_FIELDS.values())
_RAW_CONTENT_KEY_TERMS = (
    "raw",
    "source",
    "prompt",
    "secret",
    "credential",
    "token",
    "value",
    "content",
    "text",
    "body",
    "bytes",
    "code",
)
_INTEGER_PAYLOAD_FIELDS = frozenset({"duration_ms", "ledger_sequence", "token_count", "tokens_before", "tokens_after"})
_EVENT_ID_LIST_FIELDS = frozenset({"source_event_ids", "rollback_event_ids"})
_CONTENT_FREE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")


@dataclass(frozen=True)
class ContextLedgerEvent:
    tenant_id: str
    project_id: str
    stream_id: str
    sequence: int
    event_id: str
    idempotency_key: str
    event_type: ContextEventType
    branch_lineage: str
    repository_snapshot_digest: str
    subject_ref: str | None
    payload: dict[str, Any]
    payload_digest: str
    previous_event_digest: str | None
    event_digest: str
    supersedes_event_id: str | None
    occurred_at: float


@dataclass(frozen=True)
class ContextLedgerPosition:
    sequence: int
    head_event_digest: str | None


@dataclass(frozen=True)
class FileContextState:
    logical_path: str
    content_digest: str
    repository_snapshot_digest: str
    source_event_id: str
    stale: bool = False
    stale_event_id: str | None = None
    changed_content_digest: str | None = None


@dataclass(frozen=True)
class ContextProjection:
    fresh: tuple[FileContextState, ...]
    stale: tuple[FileContextState, ...]
    ledger_sequence: int
    ledger_head_digest: str | None


def _required_text(value: str, field: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ContractViolation(f"{field} must be non-blank and at most {maximum} characters")
    return value


def _content_free_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _CONTENT_FREE_IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded content-free identifier")
    return value


def _assert_content_free_payload(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        if path != "$":
            raise ContractViolation(
                "context event payload must not contain nested content objects",
                path=path,
            )
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise ContractViolation("context event payload keys must be strings", path=path)
            compact_key = "".join(character for character in raw_key.lower() if character.isalnum())
            if raw_key not in _SAFE_PAYLOAD_KEYS and any(term in compact_key for term in _RAW_CONTENT_KEY_TERMS):
                raise ContractViolation(
                    "context event payload contains a forbidden content field",
                    field=raw_key,
                    path=path,
                )
            _assert_content_free_payload(item, f"{path}.{raw_key}")
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _assert_content_free_payload(item, f"{path}[{index}]")
        return
    if isinstance(value, bytes | bytearray | memoryview):
        raise ContractViolation("context event payload must not contain raw bytes", path=path)


def _mapping(value: dict[str, Any]) -> dict[str, Any]:
    _assert_content_free_payload(value)
    normalized = json.loads(canonical_json_text(value))
    if not isinstance(normalized, dict):  # defensive: the public type is still runtime input
        raise ContractViolation("context event payload must be an object")
    return normalized


class RepositoryContextLedger:
    """Tenant-scoped persistent context stream.

    Each append compare-and-swaps the stream sequence.  A caller may provide
    ``expected_sequence`` to fence concurrent writers explicitly; even without
    it, the database CAS makes one competing append lose rather than fork the
    chain.  Idempotency is checked before the sequence fence so an exact retry
    returns the original event after a crash or ambiguous response.
    """

    def __init__(
        self,
        store: MetadataStore,
        tenant_id: str,
        project_id: str,
        stream_id: str,
        branch_lineage: str,
        repository_snapshot_digest: str,
        *,
        create_if_missing: bool = True,
    ) -> None:
        self.store = store
        self.tenant_id = _required_text(tenant_id, "tenant_id", 128)
        self.project_id = _required_text(project_id, "project_id", 128)
        self.stream_id = _required_text(stream_id, "stream_id", 256)
        self.branch_lineage = _required_text(branch_lineage, "branch_lineage", 512)
        self.repository_snapshot_digest = require_digest(repository_snapshot_digest)
        if create_if_missing:
            with self.store.transaction():
                self.store.ensure_project(self.tenant_id, self.project_id)
                self._ensure_stream()
        else:
            self._require_stream_binding()

    def _scope(self) -> tuple[str, str, str]:
        return self.tenant_id, self.project_id, self.stream_id

    def _ensure_stream(self) -> None:
        stamp = self.store.now()
        self.store.execute(
            "INSERT INTO context_ledger_streams (tenant_id, project_id, stream_id,"
            " branch_lineage, repository_snapshot_digest, current_sequence,"
            " head_event_digest, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, NULL, ?, ?)"
            " ON CONFLICT DO NOTHING",
            (*self._scope(), self.branch_lineage, self.repository_snapshot_digest, stamp, stamp),
        )
        self._require_stream_binding()

    def _require_stream_binding(self) -> None:
        """Read and verify one exact stream without creating scoped state.

        This is the constructor path for inspection and operational CLI
        commands.  A stream owned by another tenant/project is intentionally
        indistinguishable from a missing stream because the lookup is scoped
        before any global identifier is dereferenced.
        """

        row = self.store.query_one(
            "SELECT branch_lineage, repository_snapshot_digest FROM context_ledger_streams"
            " WHERE tenant_id=? AND project_id=? AND stream_id=?",
            self._scope(),
        )
        if row is None:
            raise NotFound("context ledger stream does not exist in this scope")
        if str(row[0]) != self.branch_lineage or str(row[1]) != self.repository_snapshot_digest:
            raise ConflictError(
                "context stream is bound to another branch or repository snapshot",
                stream_id=self.stream_id,
            )

    def position(self) -> ContextLedgerPosition:
        row = self.store.query_one(
            "SELECT current_sequence, head_event_digest FROM context_ledger_streams"
            " WHERE tenant_id=? AND project_id=? AND stream_id=?",
            self._scope(),
        )
        if row is None:
            raise NotFound("context ledger stream does not exist", stream_id=self.stream_id)
        return ContextLedgerPosition(int(row[0]), None if row[1] is None else str(row[1]))

    def append(
        self,
        event_type: ContextEventType | str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        expected_sequence: int | None = None,
        expected_head_digest: str | None = None,
        subject_ref: str | None = None,
        supersedes_event_id: str | None = None,
    ) -> ContextLedgerEvent:
        kind = ContextEventType(event_type)
        key = _required_text(idempotency_key, "idempotency_key", 256)
        normalized = _mapping(payload)
        normalized_subject = self._validate_event_payload(kind, normalized, subject_ref)
        payload_digest = digest_of(normalized)

        with self.store.transaction():
            self._ensure_stream()
            existing = self._find_idempotent(key)
            if existing is not None:
                if (
                    existing.event_type is not kind
                    or existing.payload_digest != payload_digest
                    or existing.subject_ref != normalized_subject
                    or existing.supersedes_event_id != supersedes_event_id
                ):
                    raise IdempotencyConflict(
                        "context idempotency key was reused for a different event",
                        stream_id=self.stream_id,
                        idempotency_key=key,
                    )
                return existing

            position = self.position()
            if expected_sequence is not None and position.sequence != expected_sequence:
                raise VersionConflict(
                    "context ledger sequence conflict",
                    stream_id=self.stream_id,
                    expected=expected_sequence,
                    actual=position.sequence,
                )
            if expected_head_digest is not None and position.head_event_digest != expected_head_digest:
                raise VersionConflict(
                    "context ledger head conflict",
                    stream_id=self.stream_id,
                    expected=expected_head_digest,
                    actual=position.head_event_digest,
                )
            if supersedes_event_id is not None and not self._event_id_exists(supersedes_event_id):
                raise NotFound(
                    "superseded context event does not exist in this stream",
                    event_id=supersedes_event_id,
                )

            sequence = position.sequence + 1
            occurred_at = self.store.now()
            event_id = "ctxevt_" + digest_of({"scope": self._scope(), "idempotency_key": key}).removeprefix("sha256:")
            envelope = self._event_envelope(
                sequence=sequence,
                event_id=event_id,
                idempotency_key=key,
                event_type=kind,
                subject_ref=normalized_subject,
                payload_digest=payload_digest,
                previous_event_digest=position.head_event_digest,
                supersedes_event_id=supersedes_event_id,
                occurred_at=occurred_at,
            )
            event_digest = digest_of(envelope)
            cursor = self.store.execute(
                "UPDATE context_ledger_streams SET current_sequence=?, head_event_digest=?,"
                " updated_at=? WHERE tenant_id=? AND project_id=? AND stream_id=?"
                " AND current_sequence=?",
                (
                    sequence,
                    event_digest,
                    occurred_at,
                    *self._scope(),
                    position.sequence,
                ),
            )
            if cursor.rowcount != 1:
                raise VersionConflict(
                    "context ledger lost a concurrent append race",
                    stream_id=self.stream_id,
                    expected=position.sequence,
                )
            self.store.execute(
                "INSERT INTO context_ledger_events (tenant_id, project_id, stream_id, sequence,"
                " event_id, idempotency_key, event_type, branch_lineage,"
                " repository_snapshot_digest, subject_ref, payload, payload_digest,"
                " previous_event_digest, event_digest, supersedes_event_id, occurred_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    *self._scope(),
                    sequence,
                    event_id,
                    key,
                    kind.value,
                    self.branch_lineage,
                    self.repository_snapshot_digest,
                    normalized_subject,
                    canonical_json_text(normalized),
                    payload_digest,
                    position.head_event_digest,
                    event_digest,
                    supersedes_event_id,
                    occurred_at,
                ),
            )
            return ContextLedgerEvent(
                self.tenant_id,
                self.project_id,
                self.stream_id,
                sequence,
                event_id,
                key,
                kind,
                self.branch_lineage,
                self.repository_snapshot_digest,
                normalized_subject,
                normalized,
                payload_digest,
                position.head_event_digest,
                event_digest,
                supersedes_event_id,
                occurred_at,
            )

    def events(self, *, after_sequence: int = 0) -> tuple[ContextLedgerEvent, ...]:
        if after_sequence < 0:
            raise ContractViolation("after_sequence must not be negative")
        rows = self.store.query(
            "SELECT sequence, event_id, idempotency_key, event_type, branch_lineage,"
            " repository_snapshot_digest, subject_ref, payload, payload_digest,"
            " previous_event_digest, event_digest, supersedes_event_id, occurred_at"
            " FROM context_ledger_events WHERE tenant_id=? AND project_id=? AND stream_id=?"
            " AND sequence>? ORDER BY sequence",
            (*self._scope(), after_sequence),
        )
        return tuple(self._from_row(row) for row in rows)

    def validate_chain(self, events: tuple[ContextLedgerEvent, ...] | None = None) -> None:
        chain = self.events() if events is None else events
        previous: str | None = None
        for expected_sequence, event in enumerate(chain, start=1):
            if event.sequence != expected_sequence or event.previous_event_digest != previous:
                raise CorruptObject(
                    "context ledger sequence or previous digest is invalid",
                    stream_id=self.stream_id,
                    sequence=event.sequence,
                )
            if (
                event.tenant_id != self.tenant_id
                or event.project_id != self.project_id
                or event.stream_id != self.stream_id
                or event.branch_lineage != self.branch_lineage
                or event.repository_snapshot_digest != self.repository_snapshot_digest
            ):
                raise CorruptObject("context ledger scope binding is invalid", event_id=event.event_id)
            if digest_of(event.payload) != event.payload_digest:
                raise CorruptObject("context ledger payload digest is invalid", event_id=event.event_id)
            envelope = self._event_envelope(
                sequence=event.sequence,
                event_id=event.event_id,
                idempotency_key=event.idempotency_key,
                event_type=event.event_type,
                subject_ref=event.subject_ref,
                payload_digest=event.payload_digest,
                previous_event_digest=event.previous_event_digest,
                supersedes_event_id=event.supersedes_event_id,
                occurred_at=event.occurred_at,
            )
            if digest_of(envelope) != event.event_digest:
                raise CorruptObject("context ledger event digest is invalid", event_id=event.event_id)
            previous = event.event_digest
        position = self.position()
        if position.sequence != len(chain) or position.head_event_digest != previous:
            raise CorruptObject("context ledger stream head does not match its events")

    def chain_is_valid(self) -> bool:
        try:
            self.validate_chain()
        except CorruptObject:
            return False
        return True

    def project_files(self) -> ContextProjection:
        self.validate_chain()
        state: dict[str, FileContextState] = {}
        for event in self.events():
            if event.event_type in {ContextEventType.FILE_READ, ContextEventType.CONTENT_REREAD}:
                path = normalize_logical_path(str(event.payload["logical_path"]))
                state[path] = FileContextState(
                    logical_path=path,
                    content_digest=require_digest(str(event.payload["content_digest"])),
                    repository_snapshot_digest=event.repository_snapshot_digest,
                    source_event_id=event.event_id,
                )
            elif event.event_type in {
                ContextEventType.CONTENT_CHANGED,
                ContextEventType.CONTEXT_STALE,
            }:
                path = normalize_logical_path(str(event.payload["logical_path"]))
                current = state.get(path)
                if current is not None:
                    changed = event.payload.get("content_digest")
                    state[path] = replace(
                        current,
                        stale=True,
                        stale_event_id=event.event_id,
                        changed_content_digest=(None if changed is None else require_digest(str(changed))),
                    )
        ordered = tuple(state[path] for path in sorted(state))
        position = self.position()
        return ContextProjection(
            fresh=tuple(item for item in ordered if not item.stale),
            stale=tuple(item for item in ordered if item.stale),
            ledger_sequence=position.sequence,
            ledger_head_digest=position.head_event_digest,
        )

    def _validate_event_payload(
        self,
        event_type: ContextEventType,
        payload: dict[str, Any],
        subject_ref: str | None,
    ) -> str | None:
        allowed = _EVENT_PAYLOAD_FIELDS[event_type]
        unexpected = sorted(set(payload).difference(allowed))
        if unexpected:
            raise ContractViolation(
                "context event payload has fields outside its closed contract",
                event_type=event_type.value,
                fields=unexpected,
            )
        missing = sorted(_REQUIRED_EVENT_PAYLOAD_FIELDS[event_type].difference(payload))
        if missing:
            raise ContractViolation(
                "context event payload is missing required fields",
                event_type=event_type.value,
                fields=missing,
            )

        for name, value in tuple(payload.items()):
            if name.endswith("_digest"):
                payload[name] = require_digest(str(value))
            elif name in _EVENT_ID_LIST_FIELDS:
                if not isinstance(value, list):
                    raise ContractViolation(f"{name} must be an array of event identifiers")
                identifiers: list[str] = []
                for item in value:
                    identifiers.append(_content_free_identifier(item, name))
                payload[name] = identifiers
            elif name in _INTEGER_PAYLOAD_FIELDS:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ContractViolation(f"{name} must be a non-negative integer")
            elif name == "logical_path":
                payload[name] = normalize_logical_path(str(value))
            else:
                payload[name] = _content_free_identifier(value, name)

        file_events = {
            ContextEventType.FILE_READ,
            ContextEventType.CONTENT_CHANGED,
            ContextEventType.CONTEXT_STALE,
            ContextEventType.CONTENT_REREAD,
        }
        if event_type in file_events:
            path = str(payload["logical_path"])
            if subject_ref is not None and subject_ref != path:
                raise ContractViolation("subject_ref does not match logical_path")
            subject_ref = path
        if event_type is ContextEventType.SYMBOL_READ and not subject_ref:
            raise ContractViolation("SYMBOL_READ requires subject_ref")
        if subject_ref is None:
            return None
        reference = _required_text(subject_ref, "subject_ref", 1024)
        if any(character.isspace() for character in reference) or "\x00" in reference:
            raise ContractViolation("subject_ref must be a content-free reference")
        return reference

    def _event_envelope(
        self,
        *,
        sequence: int,
        event_id: str,
        idempotency_key: str,
        event_type: ContextEventType,
        subject_ref: str | None,
        payload_digest: str,
        previous_event_digest: str | None,
        supersedes_event_id: str | None,
        occurred_at: float,
    ) -> dict[str, Any]:
        return {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "stream_id": self.stream_id,
            "branch_lineage": self.branch_lineage,
            "repository_snapshot_digest": self.repository_snapshot_digest,
            "sequence": sequence,
            "event_id": event_id,
            "idempotency_key": idempotency_key,
            "event_type": event_type.value,
            "subject_ref": subject_ref,
            "payload_digest": payload_digest,
            "previous_event_digest": previous_event_digest,
            "supersedes_event_id": supersedes_event_id,
            "occurred_at": occurred_at,
        }

    def _find_idempotent(self, key: str) -> ContextLedgerEvent | None:
        row = self.store.query_one(
            "SELECT sequence, event_id, idempotency_key, event_type, branch_lineage,"
            " repository_snapshot_digest, subject_ref, payload, payload_digest,"
            " previous_event_digest, event_digest, supersedes_event_id, occurred_at"
            " FROM context_ledger_events WHERE tenant_id=? AND project_id=? AND stream_id=?"
            " AND idempotency_key=?",
            (*self._scope(), key),
        )
        return None if row is None else self._from_row(row)

    def _event_id_exists(self, event_id: str) -> bool:
        return (
            self.store.query_one(
                "SELECT 1 FROM context_ledger_events WHERE tenant_id=? AND project_id=? AND stream_id=? AND event_id=?",
                (*self._scope(), event_id),
            )
            is not None
        )

    def _from_row(self, row: Any) -> ContextLedgerEvent:
        payload = row[7] if isinstance(row[7], dict) else json.loads(str(row[7]))
        if not isinstance(payload, dict):
            raise CorruptObject("context ledger payload is not an object")
        return ContextLedgerEvent(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            stream_id=self.stream_id,
            sequence=int(row[0]),
            event_id=str(row[1]),
            idempotency_key=str(row[2]),
            event_type=ContextEventType(str(row[3])),
            branch_lineage=str(row[4]),
            repository_snapshot_digest=str(row[5]),
            subject_ref=None if row[6] is None else str(row[6]),
            payload=payload,
            payload_digest=str(row[8]),
            previous_event_digest=None if row[9] is None else str(row[9]),
            event_digest=str(row[10]),
            supersedes_event_id=None if row[11] is None else str(row[11]),
            occurred_at=float(row[12]),
        )


__all__ = [
    "ContextEventType",
    "ContextLedgerEvent",
    "ContextLedgerPosition",
    "ContextProjection",
    "FileContextState",
    "RepositoryContextLedger",
]
