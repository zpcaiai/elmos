"""Durable, fail-closed local knowledge and project-memory persistence.

This module is deliberately independent from the Skill request envelope.  Its public
methods accept a validated :class:`TenantContext` and derive authorization only from
``project_acl``.  Callers must never translate permissions asserted by input content
into ACL rows or into an authorization decision.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from .canonical import (
    canonical_digest,
    canonical_json,
    normalize_sha256,
    require_idempotency_key,
    require_resource_id,
    sha256_bytes,
    utc_now,
)
from .errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    ValidationError,
)
from .models import TenantContext
from ._migrations import migrate_connection
from .store import IntakeStore


_TOKEN = re.compile(r"[\w-]+", re.UNICODE)
_MAX_TEXT_BYTES = 4 * 1024 * 1024
_MAX_VALUE_BYTES = 256 * 1024
_MAX_ANCHOR_BYTES = 64 * 1024
_MAX_QUERY_BYTES = 16 * 1024
_MAX_PERMISSION_COUNT = 32
_MAX_CANDIDATES = 1_000
_MAX_RESULTS = 100
_MAX_DOCUMENT_TERMS = 8_192
_MAX_QUERY_TERMS = 64
_MAX_TERM_CHARACTERS = 128
_MAX_EXCERPT_CHARACTERS = 4_096
_MAX_QUERY_OUTPUT_BYTES = 4 * 1024 * 1024
_MAX_REBUILD_RECORDS = 10_000
_MAX_REBUILD_TERMS = 200_000
_MAX_OUTBOX_DELIVERY_ATTEMPTS = 10
_MAX_OUTBOX_LEASE_SECONDS = 3_600
_OUTBOX_ACTIVE_PHASES = frozenset({"CLAIMED", "DISPATCHING"})
_OUTBOX_TERMINAL_PHASES = frozenset({"PUBLISHED", "BLOCKED"})
_OUTBOX_PHASES = frozenset(
    {"PENDING", "CLAIMED", "DISPATCHING", "UNKNOWN", "PUBLISHED", "BLOCKED"}
)
_EXPECTED_SCHEMA_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "project_acl": (
        "tenant_id", "project_id", "principal_id", "permission", "granted_by", "granted_at",
    ),
    "knowledge_documents": (
        "tenant_id", "project_id", "actor_id", "branch", "package_version", "document_id",
        "version", "status", "text_content", "content_digest", "source_digest",
        "source_anchor_json", "source_anchor_digest", "required_permissions_json",
        "required_permissions_digest", "confidence", "created_at", "updated_at",
    ),
    "knowledge_document_terms": (
        "tenant_id", "project_id", "actor_id", "branch", "package_version", "document_id",
        "version", "term",
    ),
    "project_memory_records": (
        "tenant_id", "project_id", "actor_id", "branch", "package_version", "memory_key",
        "memory_id", "version", "status", "memory_kind", "semantic_state", "value_json",
        "value_digest", "source_digest", "source_anchor_json", "source_anchor_digest",
        "required_permissions_json", "required_permissions_digest", "confidence", "created_at",
        "updated_at",
    ),
    "project_memory_terms": (
        "tenant_id", "project_id", "actor_id", "branch", "package_version", "memory_key",
        "version", "term",
    ),
    "knowledge_operation_receipts": (
        "tenant_id", "project_id", "actor_id", "operation", "idempotency_key",
        "request_digest", "response_json", "response_digest", "created_at",
    ),
    "knowledge_rebuild_jobs": (
        "tenant_id", "project_id", "actor_id", "branch", "package_version", "rebuild_id",
        "target", "cause_digest", "status", "attempt", "failure_code", "created_at",
        "updated_at",
    ),
    "knowledge_outbox_events": (
        "tenant_id", "project_id", "actor_id", "event_id", "event_type", "aggregate_id",
        "payload_json", "payload_digest", "idempotency_key", "occurred_at", "published_at",
    ),
    "knowledge_outbox_publications": (
        "tenant_id", "project_id", "actor_id", "event_id", "delivery_receipt_json",
        "delivery_receipt_digest", "published_at",
    ),
    "knowledge_outbox_delivery_states": (
        "tenant_id", "project_id", "actor_id", "event_id", "event_type",
        "aggregate_id", "payload_digest", "phase", "attempt", "claim_token_digest",
        "executor_id", "lease_expires_at", "last_claim_token_digest",
        "last_executor_id", "last_error_code", "transport_receipt_json",
        "transport_receipt_digest", "reconciliation_receipt_json",
        "reconciliation_receipt_digest", "created_at", "updated_at",
    ),
    "knowledge_source_tombstones": (
        "tenant_id", "project_id", "actor_id", "branch", "package_version",
        "source_digest", "generation", "record_count", "record_set_digest",
        "deletion_generation_digest", "event_id", "created_at",
    ),
    "knowledge_rebuild_completions": (
        "tenant_id", "project_id", "actor_id", "rebuild_id", "target", "cause_digest",
        "rebuilt_digest", "record_count", "term_count", "completion_event_id", "completed_at",
    ),
}
_EXPECTED_SCHEMA_INDEXES = frozenset(
    {
        "knowledge_documents_current_idx",
        "knowledge_documents_source_idx",
        "knowledge_document_terms_lookup_idx",
        "project_memory_current_idx",
        "project_memory_source_idx",
        "project_memory_terms_lookup_idx",
        "knowledge_rebuild_pending_idx",
        "knowledge_outbox_unpublished_idx",
        "knowledge_outbox_delivery_phase_idx",
        "knowledge_source_tombstones_generation_idx",
        "knowledge_rebuild_completions_digest_idx",
    }
)
_SOURCE_SCHEMA_TABLES = frozenset(
    {"project_acl", "input_sessions", "input_assets", "content_blocks", "source_anchors"}
)


class PersistentKnowledgeStore:
    """SQLite implementation for Skill20 retrieval and Skill37 project memory.

    The actor is part of the physical logical key.  This conservative boundary
    prevents one project member from observing another member's stored material;
    a future shared-project layer must use an explicit, separately authorized
    promotion operation rather than relaxing these predicates.
    """

    READ = "intake:read"
    WRITE = "intake:write"
    ADMIN = "intake:admin"

    def __init__(
        self,
        store_or_connection: IntakeStore | sqlite3.Connection,
        *,
        worker_capability: object | None = None,
    ) -> None:
        if isinstance(store_or_connection, IntakeStore):
            self._store: IntakeStore | None = store_or_connection
            self._connection = store_or_connection._connection
            self._lock = store_or_connection._lock
        elif isinstance(store_or_connection, sqlite3.Connection):
            self._store = None
            self._connection = store_or_connection
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._lock = threading.RLock()
        else:
            raise TypeError("PersistentKnowledgeStore requires IntakeStore or sqlite3.Connection")
        self._worker_capability = worker_capability
        self._install_schema()

    def _install_schema(self) -> None:
        with self._lock:
            installed_version = migrate_connection(self._connection, target_version=24)
            foreign_keys = int(
                self._connection.execute("PRAGMA foreign_keys").fetchone()[0]
            )
            if installed_version != 24:
                raise IntegrityError("KNOWLEDGE_SCHEMA_VERSION_UNSUPPORTED")
            if foreign_keys != 1:
                raise IntegrityError("KNOWLEDGE_SCHEMA_INCOMPLETE")
            for table, expected_columns in _EXPECTED_SCHEMA_COLUMNS.items():
                actual_columns = tuple(
                    str(row[1])
                    for row in self._connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                )
                if actual_columns != expected_columns:
                    raise IntegrityError(
                        "KNOWLEDGE_SCHEMA_INCOMPLETE", details={"table": table}
                    )
            present_indexes = {
                str(row[0])
                for row in self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
            if not _EXPECTED_SCHEMA_INDEXES.issubset(present_indexes):
                raise IntegrityError(
                    "KNOWLEDGE_SCHEMA_INCOMPLETE", details={"component": "indexes"}
                )
            managed_tables = frozenset(_EXPECTED_SCHEMA_COLUMNS) | _SOURCE_SCHEMA_TABLES
            reference = sqlite3.connect(":memory:", isolation_level=None)
            try:
                reference.execute("PRAGMA foreign_keys = ON")
                migrate_connection(reference, target_version=24)

                def schema_signature(connection: sqlite3.Connection) -> tuple[tuple[str, ...], ...]:
                    placeholders = ",".join("?" for _ in managed_tables)
                    rows = connection.execute(
                        f"""
                        SELECT type,name,tbl_name,sql
                          FROM sqlite_schema
                         WHERE (type='table' AND name IN ({placeholders}))
                            OR (type IN ('index','trigger')
                                AND tbl_name IN ({placeholders}) AND sql IS NOT NULL)
                         ORDER BY type,name
                        """,
                        (*sorted(managed_tables), *sorted(managed_tables)),
                    ).fetchall()
                    return tuple(
                        (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
                        for row in rows
                    )

                expected_signature = schema_signature(reference)
                actual_signature = schema_signature(self._connection)
            finally:
                reference.close()
            if actual_signature != expected_signature:
                raise IntegrityError("KNOWLEDGE_SCHEMA_DEFINITION_DRIFT")
            if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise IntegrityError("KNOWLEDGE_SCHEMA_FOREIGN_KEY_VIOLATION")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self._store is not None:
            with self._store.transaction() as connection:
                yield connection
            return
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _scope_text(value: object, field: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValidationError("KNOWLEDGE_SCOPE_INVALID", f"{field} must be a string")
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValidationError("KNOWLEDGE_SCOPE_INVALID", f"{field} is not valid UTF-8") from error
        if (
            not value
            or len(encoded) > maximum
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValidationError("KNOWLEDGE_SCOPE_INVALID", f"{field} is outside its bound")
        return value

    @staticmethod
    def _bounded_canonical(value: Any, field: str, maximum: int) -> tuple[str, str]:
        encoded = canonical_json(value)
        if len(encoded.encode("utf-8")) > maximum:
            raise ValidationError("KNOWLEDGE_JSON_LIMIT_EXCEEDED", f"{field} exceeds its byte limit")
        return encoded, sha256_bytes(encoded.encode("utf-8"))

    @classmethod
    def _anchor(cls, value: Mapping[str, Any]) -> tuple[str, str]:
        if not isinstance(value, Mapping) or not value:
            raise ValidationError("KNOWLEDGE_SOURCE_ANCHOR_REQUIRED")
        return cls._bounded_canonical(dict(value), "source_anchor", _MAX_ANCHOR_BYTES)

    @classmethod
    def _permissions(cls, values: Sequence[str]) -> tuple[tuple[str, ...], str, str]:
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ValidationError("KNOWLEDGE_PERMISSIONS_INVALID")
        if len(values) > _MAX_PERMISSION_COUNT:
            raise ValidationError("KNOWLEDGE_PERMISSIONS_LIMIT_EXCEEDED")
        normalized: list[str] = []
        for value in values:
            normalized.append(cls._scope_text(value, "required permission", 128))
        if len(set(normalized)) != len(normalized):
            raise ValidationError("KNOWLEDGE_PERMISSIONS_DUPLICATE")
        ordered = tuple(sorted(normalized))
        encoded, digest = cls._bounded_canonical(list(ordered), "required_permissions", 8 * 1024)
        return ordered, encoded, digest

    @staticmethod
    def _effective_permissions(connection: sqlite3.Connection, context: TenantContext) -> frozenset[str]:
        try:
            rows = connection.execute(
                """
                SELECT permission FROM project_acl
                 WHERE tenant_id=? AND project_id=? AND principal_id=?
                """,
                (context.tenant_id, context.project_id, context.actor_id),
            ).fetchall()
        except sqlite3.OperationalError as error:
            raise AuthorizationError("KNOWLEDGE_ACL_UNAVAILABLE") from error
        return frozenset(str(row["permission"]) for row in rows)

    @classmethod
    def _authorize(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        permission: str,
    ) -> frozenset[str]:
        granted = cls._effective_permissions(connection, context)
        if cls.ADMIN not in granted and permission not in granted:
            raise AuthorizationError("KNOWLEDGE_PROJECT_ACCESS_DENIED")
        return granted

    @classmethod
    def _require_record_permissions(
        cls,
        required: Sequence[str],
        granted: frozenset[str],
    ) -> None:
        if cls.ADMIN not in granted and not set(required).issubset(granted):
            raise AuthorizationError("KNOWLEDGE_REQUIRED_PERMISSION_DENIED")

    @staticmethod
    def _validate_source_provenance(
        connection: sqlite3.Connection,
        context: TenantContext,
        source_digest: str,
        source_anchor: Mapping[str, Any],
        *,
        allow_revoked: bool = False,
    ) -> bool:
        anchor_keys = set(source_anchor) if isinstance(source_anchor, Mapping) else set()
        if anchor_keys not in ({"asset_id"}, {"asset_id", "anchor_id"}):
            raise ValidationError("KNOWLEDGE_SOURCE_ANCHOR_FIELDS_INVALID")
        asset_id = source_anchor.get("asset_id") if isinstance(source_anchor, Mapping) else None
        if not isinstance(asset_id, str):
            raise ValidationError("KNOWLEDGE_SOURCE_ASSET_REQUIRED")
        asset_id = require_resource_id(asset_id, "source_anchor.asset_id")
        row = connection.execute(
            """
            SELECT a.sha256,a.cas_digest,a.status,a.security_decision,s.created_by
              FROM input_assets AS a
              JOIN input_sessions AS s
                ON s.tenant_id=a.tenant_id AND s.project_id=a.project_id
               AND s.session_id=a.session_id
             WHERE a.tenant_id=? AND a.project_id=? AND a.asset_id=?
            """,
            (context.tenant_id, context.project_id, asset_id),
        ).fetchone()
        if row is None:
            if allow_revoked:
                return False
            raise IntegrityError("KNOWLEDGE_SOURCE_ASSET_NOT_FOUND")
        if str(row["created_by"]) != context.actor_id:
            raise IntegrityError("KNOWLEDGE_SOURCE_ASSET_NOT_FOUND")
        bound_digests = {
            str(value)
            for value in (row["sha256"], row["cas_digest"])
            if isinstance(value, str)
        }
        if source_digest not in bound_digests:
            raise IntegrityError("KNOWLEDGE_SOURCE_DIGEST_MISMATCH")
        if row["status"] != "READY" or row["security_decision"] != "ALLOW":
            if allow_revoked:
                return False
            raise AuthorizationError("KNOWLEDGE_SOURCE_ASSET_NOT_CLEARED")
        if "anchor_id" in source_anchor:
            raw_anchor_id = source_anchor.get("anchor_id")
            if not isinstance(raw_anchor_id, str):
                raise IntegrityError("KNOWLEDGE_SOURCE_ANCHOR_INVALID")
            anchor_id = require_resource_id(raw_anchor_id, "source_anchor.anchor_id")
            anchor = connection.execute(
                """
                SELECT s.source_sha256,b.asset_version,a.version AS current_asset_version
                  FROM source_anchors AS s
                  JOIN content_blocks AS b
                    ON b.tenant_id=s.tenant_id AND b.project_id=s.project_id
                   AND b.block_id=s.block_id AND b.asset_id=s.asset_id
                  JOIN input_assets AS a
                    ON a.tenant_id=s.tenant_id AND a.project_id=s.project_id
                   AND a.asset_id=s.asset_id
                 WHERE s.tenant_id=? AND s.project_id=? AND s.asset_id=? AND s.anchor_id=?
                """,
                (context.tenant_id, context.project_id, asset_id, anchor_id),
            ).fetchone()
            if anchor is None:
                if allow_revoked:
                    return False
                raise IntegrityError("KNOWLEDGE_SOURCE_ANCHOR_NOT_FOUND")
            if (
                str(anchor["source_sha256"]) != source_digest
                or int(anchor["asset_version"]) != int(anchor["current_asset_version"])
            ):
                raise IntegrityError("KNOWLEDGE_SOURCE_ANCHOR_BINDING_MISMATCH")
        return True

    def _require_worker_capability(self, supplied: object) -> None:
        if self._worker_capability is None or supplied is not self._worker_capability:
            raise AuthorizationError("KNOWLEDGE_WORKER_AUTHORITY_REQUIRED")

    def require_worker_admin(
        self,
        context: TenantContext,
        *,
        worker_capability: object,
    ) -> None:
        """Require both runtime composition authority and current project ADMIN."""

        self._require_worker_capability(worker_capability)
        with self._lock:
            self._authorize(self._connection, context, self.ADMIN)

    @classmethod
    def _authorize_worker_admin(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
    ) -> None:
        cls._authorize(connection, context, cls.ADMIN)

    @staticmethod
    def _claim_token(value: object) -> tuple[str, str]:
        if not isinstance(value, str):
            raise ValidationError("KNOWLEDGE_OUTBOX_CLAIM_TOKEN_INVALID")
        try:
            normalized = require_idempotency_key(value)
        except ValidationError as error:
            raise ValidationError("KNOWLEDGE_OUTBOX_CLAIM_TOKEN_INVALID") from error
        return normalized, sha256_bytes(normalized.encode("utf-8"))

    @staticmethod
    def _lease_seconds(value: int) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= _MAX_OUTBOX_LEASE_SECONDS
        ):
            raise ValidationError("KNOWLEDGE_OUTBOX_LEASE_INVALID")
        return value

    @staticmethod
    def _outbox_now() -> tuple[datetime, str]:
        value = datetime.now(UTC).replace(microsecond=0)
        return value, value.isoformat()

    @classmethod
    def _worker_receipt(
        cls,
        receipt: Mapping[str, Any],
        binding: Mapping[str, Any],
        *,
        require_fresh: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(receipt, Mapping):
            raise ValidationError("KNOWLEDGE_WORKER_RECEIPT_INVALID")
        expected_keys = set(binding) | {
            "schema_version",
            "executor_id",
            "completed_at",
            "receipt_digest",
        }
        if set(receipt) != expected_keys or receipt.get("schema_version") != "1.0.0":
            raise ValidationError("KNOWLEDGE_WORKER_RECEIPT_INVALID")
        executor_id = cls._scope_text(receipt.get("executor_id"), "executor_id", 256)
        completed_at_value = receipt.get("completed_at")
        if not isinstance(completed_at_value, str):
            raise ValidationError("KNOWLEDGE_WORKER_RECEIPT_INVALID")
        try:
            completed_at = datetime.fromisoformat(completed_at_value)
        except ValueError as error:
            raise ValidationError("KNOWLEDGE_WORKER_RECEIPT_INVALID") from error
        now = datetime.now(UTC)
        if completed_at.tzinfo is None or require_fresh and (
            completed_at > now + timedelta(minutes=5)
            or completed_at < now - timedelta(hours=24)
        ):
            raise ValidationError("KNOWLEDGE_WORKER_RECEIPT_INVALID")
        for key, expected in binding.items():
            if receipt.get(key) != expected:
                raise IntegrityError(
                    "KNOWLEDGE_WORKER_RECEIPT_BINDING_MISMATCH",
                    details={"field": key},
                )
        body = {
            "schema_version": "1.0.0",
            **dict(binding),
            "executor_id": executor_id,
            "completed_at": completed_at_value,
        }
        raw_receipt_digest = receipt.get("receipt_digest")
        if not isinstance(raw_receipt_digest, str):
            raise ValidationError("KNOWLEDGE_WORKER_RECEIPT_INVALID")
        try:
            claimed_digest = normalize_sha256(raw_receipt_digest)
        except (TypeError, ValueError, ValidationError) as error:
            raise ValidationError("KNOWLEDGE_WORKER_RECEIPT_INVALID") from error
        expected_digest = canonical_digest(body)
        if claimed_digest != expected_digest:
            raise IntegrityError("KNOWLEDGE_WORKER_RECEIPT_DIGEST_MISMATCH")
        return {**body, "receipt_digest": expected_digest}

    @staticmethod
    def _decode_json(encoded: str, digest: str, field: str, maximum: int) -> Any:
        if not isinstance(encoded, str):
            raise IntegrityError(
                "KNOWLEDGE_STORED_JSON_INVALID", details={"field": field}
            )
        try:
            encoded_bytes = encoded.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise IntegrityError(
                "KNOWLEDGE_STORED_JSON_INVALID", details={"field": field}
            ) from error
        if len(encoded_bytes) > maximum:
            raise IntegrityError(
                "KNOWLEDGE_STORED_JSON_INVALID", details={"field": field}
            )
        try:
            value = json.loads(encoded)
        except (TypeError, json.JSONDecodeError) as error:
            raise IntegrityError(
                "KNOWLEDGE_STORED_JSON_INVALID", details={"field": field}
            ) from error
        try:
            normalized = canonical_json(value)
        except ValidationError as error:
            raise IntegrityError(
                "KNOWLEDGE_STORED_JSON_INVALID", details={"field": field}
            ) from error
        if normalized != encoded or sha256_bytes(encoded_bytes) != digest:
            raise IntegrityError(
                "KNOWLEDGE_STORED_DIGEST_MISMATCH", details={"field": field}
            )
        return value

    @staticmethod
    def _receipt(
        connection: sqlite3.Connection,
        context: TenantContext,
        operation: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT request_digest,response_json,response_digest
              FROM knowledge_operation_receipts
             WHERE tenant_id=? AND project_id=? AND actor_id=?
               AND operation=? AND idempotency_key=?
            """,
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                operation,
                idempotency_key,
            ),
        ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise ConflictError("KNOWLEDGE_IDEMPOTENCY_CONFLICT")
        value = PersistentKnowledgeStore._decode_json(
            str(row["response_json"]),
            str(row["response_digest"]),
            "operation receipt",
            _MAX_VALUE_BYTES,
        )
        if not isinstance(value, dict):
            raise IntegrityError("KNOWLEDGE_OPERATION_RECEIPT_INVALID")
        return value

    @staticmethod
    def _save_receipt(
        connection: sqlite3.Connection,
        context: TenantContext,
        operation: str,
        idempotency_key: str,
        request_digest: str,
        response: Mapping[str, Any],
    ) -> None:
        encoded = canonical_json(dict(response))
        if len(encoded.encode("utf-8")) > _MAX_VALUE_BYTES:
            raise IntegrityError("KNOWLEDGE_OPERATION_RECEIPT_LIMIT_EXCEEDED")
        connection.execute(
            """
            INSERT INTO knowledge_operation_receipts VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                operation,
                idempotency_key,
                request_digest,
                encoded,
                sha256_bytes(encoded.encode("utf-8")),
                utc_now(),
            ),
        )

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        event_type: str,
        aggregate_id: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
    ) -> str:
        encoded = canonical_json(dict(payload))
        payload_digest = sha256_bytes(encoded.encode("utf-8"))
        event_id = f"kevt-{canonical_digest([context.tenant_id, context.project_id, context.actor_id, idempotency_key])[:32]}"
        now = utc_now()
        connection.execute(
            """
            INSERT INTO knowledge_outbox_events VALUES (?,?,?,?,?,?,?,?,?,?,NULL)
            """,
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                event_id,
                event_type,
                aggregate_id,
                encoded,
                payload_digest,
                idempotency_key,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO knowledge_outbox_delivery_states (
                tenant_id,project_id,actor_id,event_id,event_type,aggregate_id,payload_digest,
                phase,attempt,claim_token_digest,executor_id,lease_expires_at,
                last_claim_token_digest,last_executor_id,last_error_code,
                transport_receipt_json,transport_receipt_digest,
                reconciliation_receipt_json,reconciliation_receipt_digest,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,'PENDING',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,?,?)
            """,
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                event_id,
                event_type,
                aggregate_id,
                payload_digest,
                now,
                now,
            ),
        )
        return event_id

    @staticmethod
    def _schedule_rebuild(
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        target: str,
        cause_digest: str,
    ) -> str:
        rebuild_id = f"rebuild-{canonical_digest([context.tenant_id, context.project_id, context.actor_id, branch, package_version, target, cause_digest])[:32]}"
        now = utc_now()
        connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_rebuild_jobs
            (tenant_id,project_id,actor_id,branch,package_version,rebuild_id,target,
             cause_digest,status,attempt,failure_code,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?, 'PENDING',0,NULL,?,?)
            """,
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                branch,
                package_version,
                rebuild_id,
                target,
                cause_digest,
                now,
                now,
            ),
        )
        return rebuild_id

    @staticmethod
    def _clear_source_tombstone(
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        source_digest: str,
    ) -> bool:
        cursor = connection.execute(
            """
            DELETE FROM knowledge_source_tombstones
             WHERE tenant_id=? AND project_id=? AND actor_id=?
               AND branch=? AND package_version=? AND source_digest=?
            """,
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                branch,
                package_version,
                source_digest,
            ),
        )
        return cursor.rowcount > 0

    @staticmethod
    def _terms(value: str) -> frozenset[str]:
        return frozenset(term for term in _TOKEN.findall(value.casefold()) if len(term) > 1)

    @classmethod
    def _bounded_terms(cls, value: str, field: str, maximum: int) -> tuple[str, ...]:
        terms = cls._terms(value)
        if any(len(term) > _MAX_TERM_CHARACTERS for term in terms):
            raise ValidationError("KNOWLEDGE_LEXICAL_TERM_LENGTH_EXCEEDED", field)
        if len(terms) > maximum:
            raise ValidationError("KNOWLEDGE_LEXICAL_TERM_LIMIT_EXCEEDED", field)
        return tuple(sorted(terms))

    @staticmethod
    def _excerpt(text: str, query_terms: frozenset[str]) -> tuple[str, bool]:
        folded = text.casefold()
        positions = [folded.find(term) for term in query_terms]
        hits = [position for position in positions if position >= 0]
        center = min(hits) if hits else 0
        start = max(0, center - (_MAX_EXCERPT_CHARACTERS // 4))
        end = min(len(text), start + _MAX_EXCERPT_CHARACTERS)
        excerpt = text[start:end]
        return excerpt, start > 0 or end < len(text)

    def _validate_current_document(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        expected_terms: Sequence[str],
    ) -> None:
        text = str(row["text_content"])
        try:
            text_bytes = text.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise IntegrityError("KNOWLEDGE_STORED_CONTENT_INVALID") from error
        if sha256_bytes(text_bytes) != row["content_digest"]:
            raise IntegrityError("KNOWLEDGE_STORED_CONTENT_DIGEST_MISMATCH")
        normalize_sha256(row["source_digest"])
        self._decode_json(
            str(row["source_anchor_json"]),
            str(row["source_anchor_digest"]),
            "document source anchor",
            _MAX_ANCHOR_BYTES,
        )
        self._decode_json(
            str(row["required_permissions_json"]),
            str(row["required_permissions_digest"]),
            "document permissions",
            8 * 1024,
        )
        stored_terms = tuple(
            str(term_row["term"])
            for term_row in connection.execute(
                """
                SELECT term FROM knowledge_document_terms
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND document_id=? AND version=?
                 ORDER BY term ASC
                """,
                (
                    row["tenant_id"],
                    row["project_id"],
                    row["actor_id"],
                    row["branch"],
                    row["package_version"],
                    row["document_id"],
                    row["version"],
                ),
            ).fetchall()
        )
        if stored_terms != tuple(expected_terms):
            raise IntegrityError("KNOWLEDGE_LEXICAL_INDEX_CORRUPT")

    def _validate_current_memory(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        expected_terms: Sequence[str],
    ) -> None:
        self._decode_json(
            str(row["value_json"]),
            str(row["value_digest"]),
            "memory value",
            _MAX_VALUE_BYTES,
        )
        normalize_sha256(row["source_digest"])
        self._decode_json(
            str(row["source_anchor_json"]),
            str(row["source_anchor_digest"]),
            "memory source anchor",
            _MAX_ANCHOR_BYTES,
        )
        self._decode_json(
            str(row["required_permissions_json"]),
            str(row["required_permissions_digest"]),
            "memory permissions",
            8 * 1024,
        )
        stored_terms = tuple(
            str(term_row["term"])
            for term_row in connection.execute(
                """
                SELECT term FROM project_memory_terms
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND memory_key=? AND version=?
                 ORDER BY term ASC
                """,
                (
                    row["tenant_id"],
                    row["project_id"],
                    row["actor_id"],
                    row["branch"],
                    row["package_version"],
                    row["memory_key"],
                    row["version"],
                ),
            ).fetchall()
        )
        if stored_terms != tuple(expected_terms):
            raise IntegrityError("PROJECT_MEMORY_LEXICAL_INDEX_CORRUPT")

    def upsert_document(
        self,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        document_id: str,
        text: str,
        content_digest: str,
        source_digest: str,
        source_anchor: Mapping[str, Any],
        required_permissions: Sequence[str],
        idempotency_key: str,
        expected_version: int | None = None,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        """Insert or version one lexical document and durably request an index rebuild."""

        branch = self._scope_text(branch, "branch", 256)
        package_version = self._scope_text(package_version, "package_version", 128)
        document_id = require_resource_id(document_id, "document_id")
        idempotency_key = require_idempotency_key(idempotency_key)
        if not isinstance(text, str):
            raise ValidationError("KNOWLEDGE_DOCUMENT_TEXT_INVALID")
        try:
            text_bytes = text.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValidationError("KNOWLEDGE_DOCUMENT_TEXT_INVALID") from error
        if len(text_bytes) > _MAX_TEXT_BYTES:
            raise ValidationError("KNOWLEDGE_DOCUMENT_TEXT_INVALID")
        normalized_digest = normalize_sha256(content_digest)
        if sha256_bytes(text_bytes) != normalized_digest:
            raise IntegrityError("KNOWLEDGE_DOCUMENT_DIGEST_MISMATCH")
        normalized_source = normalize_sha256(source_digest)
        indexed_terms = self._bounded_terms(text, "document text", _MAX_DOCUMENT_TERMS)
        if not indexed_terms:
            raise ValidationError("KNOWLEDGE_LEXICAL_TERMS_REQUIRED", "document text")
        anchor_json, anchor_digest = self._anchor(source_anchor)
        required, permissions_json, permissions_digest = self._permissions(required_permissions)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValidationError("KNOWLEDGE_CONFIDENCE_INVALID")
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValidationError("KNOWLEDGE_CONFIDENCE_INVALID")
        if expected_version is not None and (
            isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0
        ):
            raise ValidationError("KNOWLEDGE_EXPECTED_VERSION_INVALID")
        request_digest = canonical_digest(
            {
                "branch": branch,
                "package_version": package_version,
                "document_id": document_id,
                "text": text,
                "content_digest": normalized_digest,
                "source_digest": normalized_source,
                "source_anchor_digest": anchor_digest,
                "required_permissions": list(required),
                "expected_version": expected_version,
                "confidence": confidence,
                "term_digest": canonical_digest(indexed_terms),
            }
        )
        operation = "DOCUMENT_UPSERT"
        with self._transaction() as connection:
            granted = self._authorize(connection, context, self.WRITE)
            self._require_record_permissions(required, granted)
            replay = self._receipt(connection, context, operation, idempotency_key, request_digest)
            if replay is not None:
                return replay
            self._validate_source_provenance(
                connection,
                context,
                normalized_source,
                source_anchor,
            )
            source_tombstone_cleared = self._clear_source_tombstone(
                connection,
                context,
                branch=branch,
                package_version=package_version,
                source_digest=normalized_source,
            )
            current = connection.execute(
                """
                SELECT * FROM knowledge_documents
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND document_id=? AND status='CURRENT'
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    document_id,
                ),
            ).fetchone()
            latest_version = int(
                connection.execute(
                    """
                    SELECT coalesce(max(version),0) FROM knowledge_documents
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND branch=? AND package_version=? AND document_id=?
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        document_id,
                    ),
                ).fetchone()[0]
            )
            current_version = int(current["version"]) if current is not None else latest_version
            if expected_version is not None and expected_version != current_version:
                raise ConflictError("KNOWLEDGE_DOCUMENT_VERSION_CONFLICT")
            unchanged = bool(
                current is not None
                and current["content_digest"] == normalized_digest
                and current["source_digest"] == normalized_source
                and current["source_anchor_digest"] == anchor_digest
                and current["required_permissions_digest"] == permissions_digest
                and float(current["confidence"]) == confidence
            )
            if unchanged:
                self._validate_current_document(connection, current, indexed_terms)
                response = {
                    "document_id": document_id,
                    "version": current_version,
                    "content_digest": normalized_digest,
                    "source_digest": normalized_source,
                    "source_tombstone_cleared": source_tombstone_cleared,
                    "persisted": True,
                    "changed": False,
                    "retrieval_mode": "LEXICAL_LOCAL_SQLITE",
                    "local_index_state": "COMPLETE",
                    "rebuild_state": "UNCHANGED",
                }
                self._save_receipt(connection, context, operation, idempotency_key, request_digest, response)
                return response
            next_version = latest_version + 1
            now = utc_now()
            if current is not None:
                connection.execute(
                    """
                    UPDATE knowledge_documents SET status='SUPERSEDED',updated_at=?
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND branch=? AND package_version=? AND document_id=? AND version=?
                    """,
                    (
                        now,
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        document_id,
                        current_version,
                    ),
                )
            connection.execute(
                """
                INSERT INTO knowledge_documents VALUES
                (?,?,?,?,?,?,?,'CURRENT',?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    document_id,
                    next_version,
                    text,
                    normalized_digest,
                    normalized_source,
                    anchor_json,
                    anchor_digest,
                    permissions_json,
                    permissions_digest,
                    confidence,
                    now,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO knowledge_document_terms VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        document_id,
                        next_version,
                        term,
                    )
                    for term in indexed_terms
                ],
            )
            rebuild_cause_digest = canonical_digest(
                {
                    "request_digest": request_digest,
                    "document_id": document_id,
                    "version": next_version,
                    "content_digest": normalized_digest,
                }
            )
            rebuild_id = self._schedule_rebuild(
                connection,
                context,
                branch=branch,
                package_version=package_version,
                target="content-index",
                cause_digest=rebuild_cause_digest,
            )
            event_payload = {
                "branch": branch,
                "package_version": package_version,
                "document_id": document_id,
                "version": next_version,
                "content_digest": normalized_digest,
                "source_digest": normalized_source,
                "source_tombstone_cleared": source_tombstone_cleared,
                "rebuild_id": rebuild_id,
            }
            event_id = self._event(
                connection,
                context,
                event_type="KNOWLEDGE_DOCUMENT_UPSERTED",
                aggregate_id=document_id,
                idempotency_key=f"document-upsert:{idempotency_key}",
                payload=event_payload,
            )
            response = {
                **event_payload,
                "event_id": event_id,
                "persisted": True,
                "changed": True,
                "retrieval_mode": "LEXICAL_LOCAL_SQLITE",
                "local_index_state": "COMPLETE",
                "rebuild_state": "PENDING",
            }
            self._save_receipt(connection, context, operation, idempotency_key, request_digest, response)
            return response

    def query_documents(
        self,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        query: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Query only the caller's exact scope using deterministic lexical overlap."""

        branch = self._scope_text(branch, "branch", 256)
        package_version = self._scope_text(package_version, "package_version", 128)
        if not isinstance(query, str) or not query.strip():
            raise ValidationError("KNOWLEDGE_QUERY_INVALID")
        try:
            query_bytes = query.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValidationError("KNOWLEDGE_QUERY_INVALID") from error
        if len(query_bytes) > _MAX_QUERY_BYTES:
            raise ValidationError("KNOWLEDGE_QUERY_INVALID")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_RESULTS:
            raise ValidationError("KNOWLEDGE_QUERY_LIMIT_INVALID")
        query_terms = frozenset(self._bounded_terms(query, "document query", _MAX_QUERY_TERMS))
        if not query_terms:
            raise ValidationError("KNOWLEDGE_QUERY_TERMS_REQUIRED")
        with self._lock:
            granted = self._authorize(self._connection, context, self.READ)
            placeholders = ",".join("?" for _ in query_terms)
            rows = self._connection.execute(
                f"""
                SELECT d.tenant_id,d.project_id,d.actor_id,d.branch,d.package_version,
                       d.document_id,d.version,d.content_digest,d.source_digest,
                       d.source_anchor_json,d.source_anchor_digest,
                       d.required_permissions_json,d.required_permissions_digest,
                       d.confidence,count(t.term) AS matched_term_count
                  FROM knowledge_documents AS d
                  JOIN knowledge_document_terms AS t
                    ON t.tenant_id=d.tenant_id AND t.project_id=d.project_id
                   AND t.actor_id=d.actor_id AND t.branch=d.branch
                   AND t.package_version=d.package_version AND t.document_id=d.document_id
                   AND t.version=d.version
                 WHERE d.tenant_id=? AND d.project_id=? AND d.actor_id=?
                   AND d.branch=? AND d.package_version=? AND d.status='CURRENT'
                   AND NOT EXISTS (
                       SELECT 1 FROM knowledge_source_tombstones AS s
                        WHERE s.tenant_id=d.tenant_id AND s.project_id=d.project_id
                          AND s.actor_id=d.actor_id AND s.branch=d.branch
                          AND s.package_version=d.package_version
                          AND s.source_digest=d.source_digest
                   )
                   AND t.term IN ({placeholders})
                 GROUP BY d.tenant_id,d.project_id,d.actor_id,d.branch,d.package_version,
                          d.document_id,d.version
                 ORDER BY matched_term_count DESC,d.document_id ASC LIMIT ?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    *sorted(query_terms),
                    _MAX_CANDIDATES,
                ),
            ).fetchall()
        results: list[dict[str, Any]] = []
        permission_filtered = 0
        source_filtered = 0
        output_bytes = 0
        output_truncated = False
        for row in rows:
            required_value = self._decode_json(
                str(row["required_permissions_json"]),
                str(row["required_permissions_digest"]),
                "document permissions",
                8 * 1024,
            )
            if not isinstance(required_value, list) or any(not isinstance(item, str) for item in required_value):
                raise IntegrityError("KNOWLEDGE_STORED_PERMISSIONS_INVALID")
            if self.ADMIN not in granted and not set(required_value).issubset(granted):
                permission_filtered += 1
                continue
            with self._lock:
                content_row = self._connection.execute(
                    """
                    SELECT text_content FROM knowledge_documents
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND branch=? AND package_version=? AND document_id=? AND version=?
                       AND status='CURRENT'
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        row["document_id"],
                        row["version"],
                    ),
                ).fetchone()
            if content_row is None:
                continue
            text = str(content_row["text_content"])
            try:
                text_bytes = text.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise IntegrityError("KNOWLEDGE_STORED_CONTENT_INVALID") from error
            if sha256_bytes(text_bytes) != row["content_digest"]:
                raise IntegrityError("KNOWLEDGE_STORED_CONTENT_DIGEST_MISMATCH")
            overlap = query_terms & self._terms(text)
            if not overlap:
                raise IntegrityError("KNOWLEDGE_LEXICAL_INDEX_CORRUPT")
            excerpt, truncated = self._excerpt(text, query_terms)
            anchor = self._decode_json(
                str(row["source_anchor_json"]),
                str(row["source_anchor_digest"]),
                "document source anchor",
                _MAX_ANCHOR_BYTES,
            )
            if not isinstance(anchor, Mapping):
                raise IntegrityError("KNOWLEDGE_STORED_SOURCE_ANCHOR_INVALID")
            with self._lock:
                source_active = self._validate_source_provenance(
                    self._connection,
                    context,
                    str(row["source_digest"]),
                    anchor,
                    allow_revoked=True,
                )
            if not source_active:
                source_filtered += 1
                continue
            result = {
                "document_id": str(row["document_id"]),
                "version": int(row["version"]),
                "score": round(len(overlap) / len(query_terms), 6),
                "content_digest": str(row["content_digest"]),
                "source_digest": str(row["source_digest"]),
                "source_anchor": anchor,
                "text_excerpt": excerpt,
                "excerpt_digest": sha256_bytes(excerpt.encode("utf-8")),
                "excerpt_truncated": truncated,
                "required_permissions": required_value,
                "permission_context": {
                    "required": required_value,
                    "decision": "ALLOW",
                    "authority": "project_acl",
                },
                "confidence": float(row["confidence"]),
            }
            result_bytes = len(canonical_json(result).encode("utf-8"))
            if output_bytes + result_bytes > _MAX_QUERY_OUTPUT_BYTES:
                output_truncated = True
                break
            results.append(result)
            output_bytes += result_bytes
            if len(results) >= limit:
                break
        results.sort(key=lambda item: (-float(item["score"]), str(item["document_id"])))
        selected = results
        return {
            "results": selected,
            "result_digest": canonical_digest(selected),
            "scope": {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "branch": branch,
                "package_version": package_version,
            },
            "retrieval_mode": "LEXICAL_LOCAL_SQLITE",
            "vector_execution": "NOT_RUN",
            "persistence_state": "LOCAL_DURABLE",
            "candidate_count": len(rows),
            "candidate_window_truncated": len(rows) == _MAX_CANDIDATES,
            "output_truncated": output_truncated,
            "output_bytes": output_bytes,
            "permission_filtered_count": permission_filtered,
            "source_revoked_filtered_count": source_filtered,
        }

    def write_memory(
        self,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        memory_key: str,
        value: Any,
        source_digest: str,
        source_anchor: Mapping[str, Any],
        required_permissions: Sequence[str],
        idempotency_key: str,
        expected_version: int | None = None,
        memory_kind: str = "FACT",
        semantic_state: str = "ACTIVE",
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        """Persist one versioned project-memory value with exact provenance."""

        branch = self._scope_text(branch, "branch", 256)
        package_version = self._scope_text(package_version, "package_version", 128)
        memory_key = self._scope_text(memory_key, "memory_key", 512)
        idempotency_key = require_idempotency_key(idempotency_key)
        normalized_source = normalize_sha256(source_digest)
        value_json, value_digest = self._bounded_canonical(value, "memory value", _MAX_VALUE_BYTES)
        indexed_terms = self._bounded_terms(
            f"{memory_key} {value_json}", "memory value", _MAX_DOCUMENT_TERMS
        )
        if not indexed_terms:
            raise ValidationError("KNOWLEDGE_LEXICAL_TERMS_REQUIRED", "memory value")
        anchor_json, anchor_digest = self._anchor(source_anchor)
        required, permissions_json, permissions_digest = self._permissions(required_permissions)
        if memory_kind not in {
            "FACT",
            "DECISION",
            "REQUIREMENT",
            "PREFERENCE",
            "TASK_STATE",
            "TEST_EVIDENCE",
        }:
            raise ValidationError("PROJECT_MEMORY_KIND_INVALID")
        if semantic_state not in {"ACTIVE", "REJECTED", "EXPIRED", "CONFLICTING"}:
            raise ValidationError("PROJECT_MEMORY_SEMANTIC_STATE_INVALID")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValidationError("PROJECT_MEMORY_CONFIDENCE_INVALID")
        confidence = float(confidence)
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValidationError("PROJECT_MEMORY_CONFIDENCE_INVALID")
        if expected_version is not None and (
            isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0
        ):
            raise ValidationError("KNOWLEDGE_EXPECTED_VERSION_INVALID")
        request_digest = canonical_digest(
            {
                "branch": branch,
                "package_version": package_version,
                "memory_key": memory_key,
                "value_digest": value_digest,
                "source_digest": normalized_source,
                "source_anchor_digest": anchor_digest,
                "required_permissions": list(required),
                "expected_version": expected_version,
                "term_digest": canonical_digest(indexed_terms),
                "memory_kind": memory_kind,
                "semantic_state": semantic_state,
                "confidence": confidence,
            }
        )
        operation = "MEMORY_WRITE"
        with self._transaction() as connection:
            granted = self._authorize(connection, context, self.WRITE)
            self._require_record_permissions(required, granted)
            replay = self._receipt(connection, context, operation, idempotency_key, request_digest)
            if replay is not None:
                return replay
            self._validate_source_provenance(
                connection,
                context,
                normalized_source,
                source_anchor,
            )
            source_tombstone_cleared = self._clear_source_tombstone(
                connection,
                context,
                branch=branch,
                package_version=package_version,
                source_digest=normalized_source,
            )
            current = connection.execute(
                """
                SELECT * FROM project_memory_records
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND memory_key=? AND status='CURRENT'
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    memory_key,
                ),
            ).fetchone()
            latest_version = int(
                connection.execute(
                    """
                    SELECT coalesce(max(version),0) FROM project_memory_records
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND branch=? AND package_version=? AND memory_key=?
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        memory_key,
                    ),
                ).fetchone()[0]
            )
            current_version = int(current["version"]) if current is not None else latest_version
            if expected_version is not None and expected_version != current_version:
                raise ConflictError("PROJECT_MEMORY_VERSION_CONFLICT")
            unchanged = bool(
                current is not None
                and current["value_digest"] == value_digest
                and current["source_digest"] == normalized_source
                and current["source_anchor_digest"] == anchor_digest
                and current["required_permissions_digest"] == permissions_digest
                and current["memory_kind"] == memory_kind
                and current["semantic_state"] == semantic_state
                and float(current["confidence"]) == confidence
            )
            memory_id = f"memory-{canonical_digest([context.tenant_id, context.project_id, context.actor_id, branch, package_version, memory_key])[:32]}"
            if unchanged:
                self._validate_current_memory(connection, current, indexed_terms)
                response = {
                    "memory_id": memory_id,
                    "memory_key": memory_key,
                    "version": current_version,
                    "value_digest": value_digest,
                    "memory_kind": memory_kind,
                    "semantic_state": semantic_state,
                    "confidence": confidence,
                    "source_tombstone_cleared": source_tombstone_cleared,
                    "persisted": True,
                    "changed": False,
                    "local_index_state": "COMPLETE",
                    "rebuild_state": "UNCHANGED",
                }
                self._save_receipt(connection, context, operation, idempotency_key, request_digest, response)
                return response
            next_version = latest_version + 1
            now = utc_now()
            if current is not None:
                connection.execute(
                    """
                    UPDATE project_memory_records SET status='SUPERSEDED',updated_at=?
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND branch=? AND package_version=? AND memory_key=? AND version=?
                    """,
                    (
                        now,
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        memory_key,
                        current_version,
                    ),
                )
            connection.execute(
                """
                INSERT INTO project_memory_records VALUES
                (?,?,?,?,?,?,?,?, 'CURRENT',?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    memory_key,
                    memory_id,
                    next_version,
                    memory_kind,
                    semantic_state,
                    value_json,
                    value_digest,
                    normalized_source,
                    anchor_json,
                    anchor_digest,
                    permissions_json,
                    permissions_digest,
                    confidence,
                    now,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO project_memory_terms VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        memory_key,
                        next_version,
                        term,
                    )
                    for term in indexed_terms
                ],
            )
            rebuild_cause_digest = canonical_digest(
                {
                    "request_digest": request_digest,
                    "memory_id": memory_id,
                    "version": next_version,
                    "value_digest": value_digest,
                }
            )
            rebuild_id = self._schedule_rebuild(
                connection,
                context,
                branch=branch,
                package_version=package_version,
                target="project-memory",
                cause_digest=rebuild_cause_digest,
            )
            event_payload = {
                "branch": branch,
                "package_version": package_version,
                "memory_id": memory_id,
                "memory_key": memory_key,
                "version": next_version,
                "value_digest": value_digest,
                "source_digest": normalized_source,
                "memory_kind": memory_kind,
                "semantic_state": semantic_state,
                "confidence": confidence,
                "source_tombstone_cleared": source_tombstone_cleared,
                "rebuild_id": rebuild_id,
            }
            event_id = self._event(
                connection,
                context,
                event_type="PROJECT_MEMORY_WRITTEN",
                aggregate_id=memory_id,
                idempotency_key=f"memory-write:{idempotency_key}",
                payload=event_payload,
            )
            response = {
                **event_payload,
                "event_id": event_id,
                "persisted": True,
                "changed": True,
                "local_index_state": "COMPLETE",
                "rebuild_state": "PENDING",
            }
            self._save_receipt(connection, context, operation, idempotency_key, request_digest, response)
            return response

    def query_memory(
        self,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        query: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Read current memory from an exact scope; ACL grants come only from SQLite."""

        branch = self._scope_text(branch, "branch", 256)
        package_version = self._scope_text(package_version, "package_version", 128)
        if not isinstance(query, str) or not query.strip():
            raise ValidationError("PROJECT_MEMORY_QUERY_INVALID")
        try:
            query_bytes = query.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValidationError("PROJECT_MEMORY_QUERY_INVALID") from error
        if len(query_bytes) > _MAX_QUERY_BYTES:
            raise ValidationError("PROJECT_MEMORY_QUERY_INVALID")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_RESULTS:
            raise ValidationError("PROJECT_MEMORY_QUERY_LIMIT_INVALID")
        query_terms = frozenset(self._bounded_terms(query, "memory query", _MAX_QUERY_TERMS))
        if not query_terms:
            raise ValidationError("PROJECT_MEMORY_QUERY_TERMS_REQUIRED")
        with self._lock:
            granted = self._authorize(self._connection, context, self.READ)
            placeholders = ",".join("?" for _ in query_terms)
            rows = self._connection.execute(
                f"""
                SELECT m.tenant_id,m.project_id,m.actor_id,m.branch,m.package_version,
                       m.memory_key,m.memory_id,m.version,m.value_digest,m.source_digest,
                       m.memory_kind,m.semantic_state,m.confidence,
                       m.source_anchor_json,m.source_anchor_digest,
                       m.required_permissions_json,m.required_permissions_digest,
                       count(t.term) AS matched_term_count
                  FROM project_memory_records AS m
                  JOIN project_memory_terms AS t
                    ON t.tenant_id=m.tenant_id AND t.project_id=m.project_id
                   AND t.actor_id=m.actor_id AND t.branch=m.branch
                   AND t.package_version=m.package_version AND t.memory_key=m.memory_key
                   AND t.version=m.version
                 WHERE m.tenant_id=? AND m.project_id=? AND m.actor_id=?
                   AND m.branch=? AND m.package_version=? AND m.status='CURRENT'
                   AND NOT EXISTS (
                       SELECT 1 FROM knowledge_source_tombstones AS s
                        WHERE s.tenant_id=m.tenant_id AND s.project_id=m.project_id
                          AND s.actor_id=m.actor_id AND s.branch=m.branch
                          AND s.package_version=m.package_version
                          AND s.source_digest=m.source_digest
                   )
                   AND t.term IN ({placeholders})
                 GROUP BY m.tenant_id,m.project_id,m.actor_id,m.branch,m.package_version,
                          m.memory_key,m.version
                 ORDER BY matched_term_count DESC,m.memory_key ASC LIMIT ?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    *sorted(query_terms),
                    _MAX_CANDIDATES,
                ),
            ).fetchall()
        results: list[dict[str, Any]] = []
        permission_filtered = 0
        source_filtered = 0
        output_bytes = 0
        output_truncated = False
        for row in rows:
            required_value = self._decode_json(
                str(row["required_permissions_json"]),
                str(row["required_permissions_digest"]),
                "memory permissions",
                8 * 1024,
            )
            if not isinstance(required_value, list) or any(not isinstance(item, str) for item in required_value):
                raise IntegrityError("PROJECT_MEMORY_STORED_PERMISSIONS_INVALID")
            if self.ADMIN not in granted and not set(required_value).issubset(granted):
                permission_filtered += 1
                continue
            with self._lock:
                value_row = self._connection.execute(
                    """
                    SELECT value_json FROM project_memory_records
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND branch=? AND package_version=? AND memory_key=? AND version=?
                       AND status='CURRENT'
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        row["memory_key"],
                        row["version"],
                    ),
                ).fetchone()
            if value_row is None:
                continue
            value = self._decode_json(
                str(value_row["value_json"]),
                str(row["value_digest"]),
                "memory value",
                _MAX_VALUE_BYTES,
            )
            searchable = f"{row['memory_key']} {canonical_json(value)}"
            overlap = query_terms & self._terms(searchable)
            if not overlap:
                raise IntegrityError("PROJECT_MEMORY_LEXICAL_INDEX_CORRUPT")
            anchor = self._decode_json(
                str(row["source_anchor_json"]),
                str(row["source_anchor_digest"]),
                "memory source anchor",
                _MAX_ANCHOR_BYTES,
            )
            if not isinstance(anchor, Mapping):
                raise IntegrityError("PROJECT_MEMORY_STORED_SOURCE_ANCHOR_INVALID")
            with self._lock:
                source_active = self._validate_source_provenance(
                    self._connection,
                    context,
                    str(row["source_digest"]),
                    anchor,
                    allow_revoked=True,
                )
            if not source_active:
                source_filtered += 1
                continue
            result = {
                "memory_id": str(row["memory_id"]),
                "memory_key": str(row["memory_key"]),
                "version": int(row["version"]),
                "value": value,
                "value_digest": str(row["value_digest"]),
                "source_digest": str(row["source_digest"]),
                "source_anchor": anchor,
                "required_permissions": required_value,
                "permission_context": {
                    "required": required_value,
                    "decision": "ALLOW",
                    "authority": "project_acl",
                },
                "memory_kind": str(row["memory_kind"]),
                "semantic_state": str(row["semantic_state"]),
                "confidence": float(row["confidence"]),
                "score": round(len(overlap) / len(query_terms), 6),
            }
            result_bytes = len(canonical_json(result).encode("utf-8"))
            if output_bytes + result_bytes > _MAX_QUERY_OUTPUT_BYTES:
                output_truncated = True
                break
            results.append(result)
            output_bytes += result_bytes
            if len(results) >= limit:
                break
        results.sort(key=lambda item: (-float(item["score"]), str(item["memory_key"])))
        selected = results
        return {
            "results": selected,
            "result_digest": canonical_digest(selected),
            "scope": {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "branch": branch,
                "package_version": package_version,
            },
            "retrieval_mode": "LEXICAL_LOCAL_SQLITE",
            "vector_execution": "NOT_RUN",
            "persistent_read_performed": True,
            "candidate_count": len(rows),
            "candidate_window_truncated": len(rows) == _MAX_CANDIDATES,
            "output_truncated": output_truncated,
            "output_bytes": output_bytes,
            "permission_filtered_count": permission_filtered,
            "source_revoked_filtered_count": source_filtered,
        }

    def delete_by_source_digest(
        self,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        source_digest: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Atomically hide all exact-source records and queue both rebuild targets."""

        branch = self._scope_text(branch, "branch", 256)
        package_version = self._scope_text(package_version, "package_version", 128)
        source_digest = normalize_sha256(source_digest)
        idempotency_key = require_idempotency_key(idempotency_key)
        request_digest = canonical_digest(
            {
                "branch": branch,
                "package_version": package_version,
                "source_digest": source_digest,
            }
        )
        operation = "SOURCE_DELETE"
        with self._transaction() as connection:
            self._authorize(connection, context, self.WRITE)
            replay = self._receipt(connection, context, operation, idempotency_key, request_digest)
            if replay is not None:
                return replay
            prior_tombstone = connection.execute(
                """
                SELECT generation FROM knowledge_source_tombstones
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND source_digest=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    source_digest,
                ),
            ).fetchone()
            generation = (int(prior_tombstone["generation"]) + 1) if prior_tombstone else 1
            records = connection.execute(
                """
                SELECT 'document' AS record_kind,document_id AS record_id,version
                  FROM knowledge_documents
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND source_digest=? AND status='CURRENT'
                UNION ALL
                SELECT 'memory' AS record_kind,memory_id AS record_id,version
                  FROM project_memory_records
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND source_digest=? AND status='CURRENT'
                 ORDER BY record_kind,record_id,version
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    source_digest,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    source_digest,
                ),
            )
            record_hasher = hashlib.sha256(b"elmos-knowledge-source-record-set-v1\x00")
            affected_document_count = 0
            affected_memory_count = 0
            for record in records:
                kind = str(record["record_kind"])
                if kind == "document":
                    affected_document_count += 1
                elif kind == "memory":
                    affected_memory_count += 1
                else:
                    raise IntegrityError("KNOWLEDGE_DELETE_RECORD_KIND_INVALID")
                encoded_record = canonical_json(
                    {
                        "kind": kind,
                        "record_id": str(record["record_id"]),
                        "version": int(record["version"]),
                    }
                ).encode("utf-8")
                record_hasher.update(len(encoded_record).to_bytes(8, "big"))
                record_hasher.update(encoded_record)
            affected_record_count = affected_document_count + affected_memory_count
            record_set_digest = record_hasher.hexdigest()
            now = utc_now()
            connection.execute(
                """
                UPDATE knowledge_documents SET status='DELETED',updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND source_digest=? AND status='CURRENT'
                """,
                (
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    source_digest,
                ),
            )
            connection.execute(
                """
                UPDATE project_memory_records SET status='DELETED',updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND source_digest=? AND status='CURRENT'
                """,
                (
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    source_digest,
                ),
            )
            connection.execute(
                """
                DELETE FROM knowledge_document_terms
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=?
                   AND EXISTS (
                       SELECT 1 FROM knowledge_documents AS d
                        WHERE d.tenant_id=knowledge_document_terms.tenant_id
                          AND d.project_id=knowledge_document_terms.project_id
                          AND d.actor_id=knowledge_document_terms.actor_id
                          AND d.branch=knowledge_document_terms.branch
                          AND d.package_version=knowledge_document_terms.package_version
                          AND d.document_id=knowledge_document_terms.document_id
                          AND d.version=knowledge_document_terms.version
                          AND d.source_digest=?
                   )
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    source_digest,
                ),
            )
            connection.execute(
                """
                DELETE FROM project_memory_terms
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=?
                   AND EXISTS (
                       SELECT 1 FROM project_memory_records AS m
                        WHERE m.tenant_id=project_memory_terms.tenant_id
                          AND m.project_id=project_memory_terms.project_id
                          AND m.actor_id=project_memory_terms.actor_id
                          AND m.branch=project_memory_terms.branch
                          AND m.package_version=project_memory_terms.package_version
                          AND m.memory_key=project_memory_terms.memory_key
                          AND m.version=project_memory_terms.version
                          AND m.source_digest=?
                   )
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    source_digest,
                ),
            )
            changed = affected_record_count > 0
            deletion_generation_digest = canonical_digest(
                {
                    "scope": {
                        "tenant_id": context.tenant_id,
                        "project_id": context.project_id,
                        "actor_id": context.actor_id,
                        "branch": branch,
                        "package_version": package_version,
                    },
                    "source_digest": source_digest,
                    "generation": generation,
                    "affected_document_count": affected_document_count,
                    "affected_memory_count": affected_memory_count,
                    "record_set_digest": record_set_digest,
                }
            )
            rebuild_ids: list[str] = []
            if changed:
                rebuild_ids = [
                    self._schedule_rebuild(
                        connection,
                        context,
                        branch=branch,
                        package_version=package_version,
                        target=target,
                        cause_digest=canonical_digest(
                            {
                                "request_digest": request_digest,
                                "deletion_generation_digest": deletion_generation_digest,
                                "target": target,
                            }
                        ),
                    )
                    for target in ("content-index", "project-memory")
                ]
            event_id = self._event(
                connection,
                context,
                event_type="KNOWLEDGE_SOURCE_TOMBSTONED",
                aggregate_id=source_digest,
                idempotency_key=f"source-delete:{idempotency_key}",
                payload={
                    "branch": branch,
                    "package_version": package_version,
                    "source_digest": source_digest,
                    "tombstone_generation": generation,
                    "affected_document_count": affected_document_count,
                    "affected_memory_count": affected_memory_count,
                    "affected_record_count": affected_record_count,
                    "record_set_digest": record_set_digest,
                    "deletion_generation_digest": deletion_generation_digest,
                    "rebuild_ids": rebuild_ids,
                },
            )
            connection.execute(
                """
                INSERT INTO knowledge_source_tombstones VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT (tenant_id,project_id,actor_id,branch,package_version,source_digest)
                DO UPDATE SET generation=excluded.generation,
                              record_count=excluded.record_count,
                              record_set_digest=excluded.record_set_digest,
                              deletion_generation_digest=excluded.deletion_generation_digest,
                              event_id=excluded.event_id,
                              created_at=excluded.created_at
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    source_digest,
                    generation,
                    affected_record_count,
                    record_set_digest,
                    deletion_generation_digest,
                    event_id,
                    now,
                ),
            )
            response = {
                "source_digest": source_digest,
                "affected_document_count": affected_document_count,
                "affected_memory_count": affected_memory_count,
                "affected_record_count": affected_record_count,
                "record_set_digest": record_set_digest,
                "tombstone_generation": generation,
                "source_tombstone_state": "ACTIVE",
                "changed": changed,
                "deletion_generation_digest": deletion_generation_digest,
                "local_visibility_state": "COMPLETE",
                "deletion_propagation_state": "PENDING" if changed else "COMPLETE",
                "rebuild_ids": rebuild_ids,
                "event_id": event_id,
            }
            self._save_receipt(connection, context, operation, idempotency_key, request_digest, response)
            return response

    def list_rebuild_jobs(
        self,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        branch = self._scope_text(branch, "branch", 256)
        package_version = self._scope_text(package_version, "package_version", 128)
        if status is not None and status not in {"PENDING", "RUNNING", "SUCCEEDED", "FAILED"}:
            raise ValidationError("KNOWLEDGE_REBUILD_STATUS_INVALID")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_RESULTS:
            raise ValidationError("KNOWLEDGE_REBUILD_LIMIT_INVALID")
        with self._lock:
            self._authorize(self._connection, context, self.READ)
            predicate = " AND j.status=?" if status is not None else ""
            parameters: list[Any] = [
                context.tenant_id,
                context.project_id,
                context.actor_id,
                branch,
                package_version,
            ]
            if status is not None:
                parameters.append(status)
            parameters.append(limit)
            rows = self._connection.execute(
                f"""
                SELECT j.rebuild_id,j.target,j.cause_digest,j.status,j.attempt,j.failure_code,
                       j.created_at,j.updated_at,c.rebuilt_digest,c.record_count,c.term_count,
                       c.completion_event_id,c.completed_at
                  FROM knowledge_rebuild_jobs AS j
                  LEFT JOIN knowledge_rebuild_completions AS c
                    ON c.tenant_id=j.tenant_id AND c.project_id=j.project_id
                   AND c.actor_id=j.actor_id AND c.rebuild_id=j.rebuild_id
                 WHERE j.tenant_id=? AND j.project_id=? AND j.actor_id=?
                   AND j.branch=? AND j.package_version=?{predicate}
                 ORDER BY j.created_at ASC,j.rebuild_id ASC LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def rebuild_lexical_index(
        self,
        context: TenantContext,
        *,
        branch: str,
        package_version: str,
        target: str,
        idempotency_key: str,
        worker_capability: object | None = None,
    ) -> dict[str, Any]:
        """Rebuild one exact local lexical index and reconcile its queued jobs."""

        if worker_capability is not None:
            self._require_worker_capability(worker_capability)
        branch = self._scope_text(branch, "branch", 256)
        package_version = self._scope_text(package_version, "package_version", 128)
        if target not in {"content-index", "project-memory"}:
            raise ValidationError("KNOWLEDGE_REBUILD_TARGET_INVALID")
        idempotency_key = require_idempotency_key(idempotency_key)
        request_digest = canonical_digest(
            {"branch": branch, "package_version": package_version, "target": target}
        )
        operation = "LEXICAL_INDEX_REBUILD"
        with self._transaction() as connection:
            if worker_capability is None:
                self._authorize(connection, context, self.WRITE)
            else:
                self._authorize_worker_admin(connection, context)
            replay = self._receipt(connection, context, operation, idempotency_key, request_digest)
            if replay is not None:
                return replay
            if target == "content-index":
                records = connection.execute(
                    """
                    SELECT document_id,version,text_content,content_digest
                      FROM knowledge_documents
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND branch=? AND package_version=? AND status='CURRENT'
                     ORDER BY document_id ASC LIMIT ?
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        _MAX_REBUILD_RECORDS + 1,
                    ),
                ).fetchall()
                if len(records) > _MAX_REBUILD_RECORDS:
                    raise ValidationError("KNOWLEDGE_REBUILD_RECORD_LIMIT_EXCEEDED")
                term_rows: list[tuple[Any, ...]] = []
                for row in records:
                    text = str(row["text_content"])
                    try:
                        text_bytes = text.encode("utf-8", errors="strict")
                    except UnicodeEncodeError as error:
                        raise IntegrityError("KNOWLEDGE_STORED_CONTENT_INVALID") from error
                    if sha256_bytes(text_bytes) != row["content_digest"]:
                        raise IntegrityError("KNOWLEDGE_STORED_CONTENT_DIGEST_MISMATCH")
                    terms = self._bounded_terms(text, "document text", _MAX_DOCUMENT_TERMS)
                    if not terms:
                        raise IntegrityError("KNOWLEDGE_STORED_LEXICAL_TERMS_MISSING")
                    if len(term_rows) + len(terms) > _MAX_REBUILD_TERMS:
                        raise ValidationError("KNOWLEDGE_REBUILD_TERM_LIMIT_EXCEEDED")
                    term_rows.extend(
                        (
                            context.tenant_id,
                            context.project_id,
                            context.actor_id,
                            branch,
                            package_version,
                            str(row["document_id"]),
                            int(row["version"]),
                            term,
                        )
                        for term in terms
                    )
                term_table = "knowledge_document_terms"
            else:
                records = connection.execute(
                    """
                    SELECT memory_key,version,value_json,value_digest
                      FROM project_memory_records
                     WHERE tenant_id=? AND project_id=? AND actor_id=?
                       AND branch=? AND package_version=? AND status='CURRENT'
                     ORDER BY memory_key ASC LIMIT ?
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        branch,
                        package_version,
                        _MAX_REBUILD_RECORDS + 1,
                    ),
                ).fetchall()
                if len(records) > _MAX_REBUILD_RECORDS:
                    raise ValidationError("KNOWLEDGE_REBUILD_RECORD_LIMIT_EXCEEDED")
                term_rows = []
                for row in records:
                    value = self._decode_json(
                        str(row["value_json"]),
                        str(row["value_digest"]),
                        "memory value",
                        _MAX_VALUE_BYTES,
                    )
                    memory_key = str(row["memory_key"])
                    terms = self._bounded_terms(
                        f"{memory_key} {canonical_json(value)}",
                        "memory value",
                        _MAX_DOCUMENT_TERMS,
                    )
                    if not terms:
                        raise IntegrityError("PROJECT_MEMORY_STORED_LEXICAL_TERMS_MISSING")
                    if len(term_rows) + len(terms) > _MAX_REBUILD_TERMS:
                        raise ValidationError("KNOWLEDGE_REBUILD_TERM_LIMIT_EXCEEDED")
                    term_rows.extend(
                        (
                            context.tenant_id,
                            context.project_id,
                            context.actor_id,
                            branch,
                            package_version,
                            memory_key,
                            int(row["version"]),
                            term,
                        )
                        for term in terms
                    )
                term_table = "project_memory_terms"
            if len(term_rows) > _MAX_REBUILD_TERMS:
                raise ValidationError("KNOWLEDGE_REBUILD_TERM_LIMIT_EXCEEDED")
            connection.execute(
                f"""
                DELETE FROM {term_table}
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                ),
            )
            if term_rows:
                connection.executemany(
                    f"INSERT INTO {term_table} VALUES (?,?,?,?,?,?,?,?)",
                    term_rows,
                )
            rebuilt_hasher = hashlib.sha256()
            rebuilt_hasher.update(
                canonical_json(
                    {
                        "tenant_id": context.tenant_id,
                        "project_id": context.project_id,
                        "actor_id": context.actor_id,
                        "branch": branch,
                        "package_version": package_version,
                        "target": target,
                    }
                ).encode("utf-8")
            )
            for term_row in term_rows:
                rebuilt_hasher.update(b"\n")
                rebuilt_hasher.update(canonical_json(term_row).encode("utf-8"))
            rebuilt_digest = rebuilt_hasher.hexdigest()
            jobs = connection.execute(
                """
                SELECT rebuild_id,cause_digest FROM knowledge_rebuild_jobs
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND target=?
                   AND status IN ('PENDING','RUNNING','FAILED')
                 ORDER BY created_at ASC,rebuild_id ASC
                 LIMIT ?
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    target,
                    _MAX_REBUILD_RECORDS + 1,
                ),
            ).fetchall()
            if len(jobs) > _MAX_REBUILD_RECORDS:
                raise ValidationError("KNOWLEDGE_REBUILD_JOB_LIMIT_EXCEEDED")
            now = utc_now()
            completed_job_set_digest = canonical_digest(
                [
                    {
                        "rebuild_id": str(job["rebuild_id"]),
                        "cause_digest": str(job["cause_digest"]),
                    }
                    for job in jobs
                ]
            )
            for job in jobs:
                rebuild_id = str(job["rebuild_id"])
                cause_digest = str(job["cause_digest"])
                completion_event_id = self._event(
                    connection,
                    context,
                    event_type="KNOWLEDGE_REBUILD_JOB_COMPLETED",
                    aggregate_id=rebuild_id,
                    idempotency_key=f"lexical-rebuild-job:{idempotency_key}:{rebuild_id}",
                    payload={
                        "rebuild_id": rebuild_id,
                        "cause_digest": cause_digest,
                        "target": target,
                        "rebuilt_digest": rebuilt_digest,
                        "record_count": len(records),
                        "term_count": len(term_rows),
                    },
                )
                connection.execute(
                    """
                    INSERT INTO knowledge_rebuild_completions VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        rebuild_id,
                        target,
                        cause_digest,
                        rebuilt_digest,
                        len(records),
                        len(term_rows),
                        completion_event_id,
                        now,
                    ),
                )
            connection.execute(
                """
                UPDATE knowledge_rebuild_jobs
                   SET status='SUCCEEDED',failure_code=NULL,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND branch=? AND package_version=? AND target=?
                   AND status IN ('PENDING','RUNNING','FAILED')
                """,
                (
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    branch,
                    package_version,
                    target,
                ),
            )
            event_id = self._event(
                connection,
                context,
                event_type="KNOWLEDGE_LEXICAL_INDEX_REBUILT",
                aggregate_id=target,
                idempotency_key=f"lexical-rebuild:{idempotency_key}",
                payload={
                    "branch": branch,
                    "package_version": package_version,
                    "target": target,
                    "record_count": len(records),
                    "term_count": len(term_rows),
                    "rebuilt_digest": rebuilt_digest,
                    "completed_job_count": len(jobs),
                    "completed_job_set_digest": completed_job_set_digest,
                },
            )
            response = {
                "target": target,
                "record_count": len(records),
                "term_count": len(term_rows),
                "rebuilt_digest": rebuilt_digest,
                "completed_job_count": len(jobs),
                "completed_job_set_digest": completed_job_set_digest,
                "rebuild_state": "SUCCEEDED",
                "event_id": event_id,
                "retrieval_mode": "LEXICAL_LOCAL_SQLITE",
                "vector_execution": "NOT_RUN",
            }
            self._save_receipt(connection, context, operation, idempotency_key, request_digest, response)
            return response

    def transition_rebuild(
        self,
        context: TenantContext,
        *,
        rebuild_id: str,
        target_state: str,
        idempotency_key: str,
        worker_capability: object,
        execution_receipt: Mapping[str, Any],
        failure_code: str | None = None,
    ) -> dict[str, Any]:
        self._require_worker_capability(worker_capability)
        rebuild_id = require_resource_id(rebuild_id, "rebuild_id")
        idempotency_key = require_idempotency_key(idempotency_key)
        transitions = {
            "PENDING": {"RUNNING"},
            "RUNNING": {"FAILED"},
            "FAILED": {"RUNNING"},
            "SUCCEEDED": set(),
        }
        if target_state == "SUCCEEDED":
            raise AuthorizationError("KNOWLEDGE_REBUILD_COMPLETION_REQUIRES_EXECUTION")
        if target_state not in transitions:
            raise ValidationError("KNOWLEDGE_REBUILD_STATUS_INVALID")
        if failure_code is not None:
            failure_code = self._scope_text(failure_code, "failure_code", 128)
        if target_state == "FAILED" and failure_code is None:
            raise ValidationError("KNOWLEDGE_REBUILD_FAILURE_CODE_REQUIRED")
        if target_state != "FAILED" and failure_code is not None:
            raise ValidationError("KNOWLEDGE_REBUILD_FAILURE_CODE_UNEXPECTED")
        operation = "REBUILD_TRANSITION"
        with self._transaction() as connection:
            self._authorize_worker_admin(connection, context)
            row = connection.execute(
                """
                SELECT * FROM knowledge_rebuild_jobs
                 WHERE tenant_id=? AND project_id=? AND actor_id=? AND rebuild_id=?
                """,
                (context.tenant_id, context.project_id, context.actor_id, rebuild_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("KNOWLEDGE_REBUILD_NOT_FOUND")
            current = str(row["status"])
            receipt_from_state = execution_receipt.get("from_state")
            if not isinstance(receipt_from_state, str) or receipt_from_state not in transitions:
                raise ValidationError("KNOWLEDGE_WORKER_RECEIPT_INVALID")
            if target_state not in transitions[receipt_from_state]:
                raise ConflictError("KNOWLEDGE_REBUILD_TRANSITION_INVALID")
            verified_receipt = self._worker_receipt(
                execution_receipt,
                {
                    "rebuild_id": rebuild_id,
                    "cause_digest": str(row["cause_digest"]),
                    "from_state": receipt_from_state,
                    "target_state": target_state,
                    "failure_code": failure_code,
                },
                require_fresh=False,
            )
            request_digest = canonical_digest(
                {
                    "rebuild_id": rebuild_id,
                    "target_state": target_state,
                    "failure_code": failure_code,
                    "worker_receipt_digest": verified_receipt["receipt_digest"],
                }
            )
            replay = self._receipt(
                connection,
                context,
                operation,
                idempotency_key,
                request_digest,
            )
            if replay is not None:
                return replay
            self._worker_receipt(
                execution_receipt,
                {
                    "rebuild_id": rebuild_id,
                    "cause_digest": str(row["cause_digest"]),
                    "from_state": receipt_from_state,
                    "target_state": target_state,
                    "failure_code": failure_code,
                },
                require_fresh=True,
            )
            if current != receipt_from_state:
                raise ConflictError("KNOWLEDGE_REBUILD_TRANSITION_INVALID")
            attempt = int(row["attempt"]) + (1 if target_state == "RUNNING" else 0)
            connection.execute(
                """
                UPDATE knowledge_rebuild_jobs
                   SET status=?,attempt=?,failure_code=?,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=? AND rebuild_id=?
                """,
                (
                    target_state,
                    attempt,
                    failure_code,
                    utc_now(),
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    rebuild_id,
                ),
            )
            event_id = self._event(
                connection,
                context,
                event_type="KNOWLEDGE_REBUILD_TRANSITIONED",
                aggregate_id=rebuild_id,
                idempotency_key=f"rebuild-transition:{idempotency_key}",
                payload={
                    "rebuild_id": rebuild_id,
                    "from_state": current,
                    "target_state": target_state,
                    "attempt": attempt,
                    "failure_code": failure_code,
                    "worker_receipt": verified_receipt,
                },
            )
            response = {
                "rebuild_id": rebuild_id,
                "from_state": current,
                "status": target_state,
                "attempt": attempt,
                "failure_code": failure_code,
                "worker_receipt_digest": verified_receipt["receipt_digest"],
                "event_id": event_id,
            }
            self._save_receipt(connection, context, operation, idempotency_key, request_digest, response)
            return response

    @staticmethod
    def _outbox_select() -> str:
        return """
            SELECT e.tenant_id,e.project_id,e.actor_id,e.event_id,e.event_type,
                   e.aggregate_id,e.payload_json,e.payload_digest,e.idempotency_key,
                   e.occurred_at,e.published_at,
                   d.event_id AS delivery_event_id,d.event_type AS delivery_event_type,
                   d.aggregate_id AS delivery_aggregate_id,
                   d.payload_digest AS delivery_payload_digest,d.phase,d.attempt,
                   d.claim_token_digest,d.executor_id,d.lease_expires_at,
                   d.last_claim_token_digest,d.last_executor_id,d.last_error_code,
                   d.transport_receipt_json,d.transport_receipt_digest,
                   d.reconciliation_receipt_json,d.reconciliation_receipt_digest,
                   d.created_at AS delivery_created_at,d.updated_at AS delivery_updated_at,
                   p.delivery_receipt_json,p.delivery_receipt_digest,p.published_at AS evidence_published_at
              FROM knowledge_outbox_events AS e
              LEFT JOIN knowledge_outbox_delivery_states AS d
                ON d.tenant_id=e.tenant_id AND d.project_id=e.project_id
               AND d.actor_id=e.actor_id AND d.event_id=e.event_id
              LEFT JOIN knowledge_outbox_publications AS p
                ON p.tenant_id=e.tenant_id AND p.project_id=e.project_id
               AND p.actor_id=e.actor_id AND p.event_id=e.event_id
        """

    @classmethod
    def _materialize_outbox_row(cls, row: sqlite3.Row) -> dict[str, Any]:
        if row["delivery_event_id"] is None:
            raise IntegrityError("KNOWLEDGE_OUTBOX_DELIVERY_STATE_MISSING")
        event_id = require_resource_id(str(row["event_id"]), "event_id")
        event_type = cls._scope_text(str(row["event_type"]), "event_type", 128)
        aggregate_id = require_resource_id(str(row["aggregate_id"]), "aggregate_id")
        payload_digest = normalize_sha256(str(row["payload_digest"]))
        if (
            str(row["delivery_event_id"]) != event_id
            or str(row["delivery_event_type"]) != event_type
            or str(row["delivery_aggregate_id"]) != aggregate_id
            or str(row["delivery_payload_digest"]) != payload_digest
        ):
            raise IntegrityError("KNOWLEDGE_OUTBOX_DELIVERY_BINDING_MISMATCH")
        phase = str(row["phase"])
        attempt = row["attempt"]
        if (
            phase not in _OUTBOX_PHASES
            or isinstance(attempt, bool)
            or not isinstance(attempt, int)
            or not 0 <= attempt <= _MAX_OUTBOX_DELIVERY_ATTEMPTS
        ):
            raise IntegrityError("KNOWLEDGE_OUTBOX_DELIVERY_STATE_INVALID")
        active_values = (
            row["claim_token_digest"],
            row["executor_id"],
            row["lease_expires_at"],
        )
        if phase in _OUTBOX_ACTIVE_PHASES:
            if any(value is None for value in active_values):
                raise IntegrityError("KNOWLEDGE_OUTBOX_DELIVERY_STATE_INVALID")
            normalize_sha256(str(row["claim_token_digest"]))
            cls._scope_text(str(row["executor_id"]), "executor_id", 256)
            cls._stored_outbox_timestamp(row["lease_expires_at"], "lease_expires_at")
        elif any(value is not None for value in active_values):
            raise IntegrityError("KNOWLEDGE_OUTBOX_DELIVERY_STATE_INVALID")
        if row["last_claim_token_digest"] is not None:
            normalize_sha256(str(row["last_claim_token_digest"]))
        if row["last_executor_id"] is not None:
            cls._scope_text(str(row["last_executor_id"]), "last_executor_id", 256)
        published_at = row["published_at"]
        publication_evidence_present = row["delivery_receipt_json"] is not None
        if phase == "PUBLISHED":
            if published_at is None or not publication_evidence_present:
                raise IntegrityError("KNOWLEDGE_OUTBOX_PUBLICATION_EVIDENCE_MISSING")
            if str(row["evidence_published_at"]) != str(published_at):
                raise IntegrityError("KNOWLEDGE_OUTBOX_PUBLICATION_BINDING_MISMATCH")
        elif published_at is not None or publication_evidence_present:
            raise IntegrityError("KNOWLEDGE_OUTBOX_PUBLICATION_STATE_MISMATCH")
        payload = cls._decode_json(
            str(row["payload_json"]),
            payload_digest,
            "knowledge outbox payload",
            _MAX_VALUE_BYTES,
        )
        if not isinstance(payload, dict):
            raise IntegrityError("KNOWLEDGE_OUTBOX_STORED_PAYLOAD_INVALID")
        publication_receipt = None
        if publication_evidence_present:
            publication_receipt = cls._decode_json(
                str(row["delivery_receipt_json"]),
                str(row["delivery_receipt_digest"]),
                "knowledge outbox publication receipt",
                _MAX_VALUE_BYTES,
            )
            if not isinstance(publication_receipt, dict):
                raise IntegrityError("KNOWLEDGE_OUTBOX_PUBLICATION_EVIDENCE_INVALID")
        transport_receipt = None
        if row["transport_receipt_json"] is not None:
            transport_receipt = cls._decode_json(
                str(row["transport_receipt_json"]),
                str(row["transport_receipt_digest"]),
                "knowledge outbox transport receipt",
                _MAX_VALUE_BYTES,
            )
            if not isinstance(transport_receipt, dict):
                raise IntegrityError("KNOWLEDGE_OUTBOX_TRANSPORT_RECEIPT_INVALID")
        reconciliation_receipt = None
        if row["reconciliation_receipt_json"] is not None:
            reconciliation_receipt = cls._decode_json(
                str(row["reconciliation_receipt_json"]),
                str(row["reconciliation_receipt_digest"]),
                "knowledge outbox reconciliation receipt",
                _MAX_VALUE_BYTES,
            )
            if not isinstance(reconciliation_receipt, dict):
                raise IntegrityError("KNOWLEDGE_OUTBOX_RECONCILIATION_RECEIPT_INVALID")
        return {
            "tenant_id": str(row["tenant_id"]),
            "project_id": str(row["project_id"]),
            "actor_id": str(row["actor_id"]),
            "event_id": event_id,
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "payload": payload,
            "payload_digest": payload_digest,
            "idempotency_key": str(row["idempotency_key"]),
            "occurred_at": str(row["occurred_at"]),
            "published_at": str(published_at) if published_at is not None else None,
            "publication_receipt": publication_receipt,
            "delivery_receipt_digest": (
                str(row["delivery_receipt_digest"])
                if row["delivery_receipt_digest"] is not None
                else None
            ),
            "delivery_phase": phase,
            "delivery_attempt": int(attempt),
            "claim_token_digest": (
                str(row["claim_token_digest"])
                if row["claim_token_digest"] is not None
                else None
            ),
            "executor_id": str(row["executor_id"]) if row["executor_id"] is not None else None,
            "lease_expires_at": (
                str(row["lease_expires_at"])
                if row["lease_expires_at"] is not None
                else None
            ),
            "last_claim_token_digest": (
                str(row["last_claim_token_digest"])
                if row["last_claim_token_digest"] is not None
                else None
            ),
            "last_executor_id": (
                str(row["last_executor_id"])
                if row["last_executor_id"] is not None
                else None
            ),
            "last_error_code": (
                str(row["last_error_code"])
                if row["last_error_code"] is not None
                else None
            ),
            "transport_receipt": transport_receipt,
            "transport_receipt_digest": (
                str(row["transport_receipt_digest"])
                if row["transport_receipt_digest"] is not None
                else None
            ),
            "reconciliation_receipt": reconciliation_receipt,
            "reconciliation_receipt_digest": (
                str(row["reconciliation_receipt_digest"])
                if row["reconciliation_receipt_digest"] is not None
                else None
            ),
        }

    @staticmethod
    def _stored_outbox_timestamp(value: Any, field: str) -> datetime:
        if not isinstance(value, str):
            raise IntegrityError(
                "KNOWLEDGE_OUTBOX_STORED_TIMESTAMP_INVALID",
                details={"field": field},
            )
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise IntegrityError(
                "KNOWLEDGE_OUTBOX_STORED_TIMESTAMP_INVALID",
                details={"field": field},
            ) from error
        if parsed.tzinfo is None:
            raise IntegrityError(
                "KNOWLEDGE_OUTBOX_STORED_TIMESTAMP_INVALID",
                details={"field": field},
            )
        return parsed.astimezone(UTC)

    def _outbox_row(
        self,
        connection: sqlite3.Connection,
        context: TenantContext,
        event_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            self._outbox_select()
            + """
             WHERE e.tenant_id=? AND e.project_id=? AND e.actor_id=? AND e.event_id=?
            """,
            (context.tenant_id, context.project_id, context.actor_id, event_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("KNOWLEDGE_OUTBOX_EVENT_NOT_FOUND")
        return self._materialize_outbox_row(row)

    @staticmethod
    def _public_outbox_event(event: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: event[key]
            for key in (
                "event_id",
                "event_type",
                "aggregate_id",
                "payload",
                "payload_digest",
                "idempotency_key",
                "occurred_at",
                "published_at",
                "publication_receipt",
            )
        }

    def outbox_events(
        self,
        context: TenantContext,
        *,
        unpublished_only: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not isinstance(unpublished_only, bool):
            raise ValidationError("KNOWLEDGE_OUTBOX_FILTER_INVALID")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_RESULTS:
            raise ValidationError("KNOWLEDGE_OUTBOX_LIMIT_INVALID")
        with self._lock:
            self._authorize(self._connection, context, self.READ)
            predicate = " AND e.published_at IS NULL" if unpublished_only else ""
            rows = self._connection.execute(
                self._outbox_select()
                + f"""
                 WHERE e.tenant_id=? AND e.project_id=? AND e.actor_id=?{predicate}
                 ORDER BY e.occurred_at ASC,e.event_id ASC LIMIT ?
                """,
                (context.tenant_id, context.project_id, context.actor_id, limit),
            ).fetchall()
            return [self._public_outbox_event(self._materialize_outbox_row(row)) for row in rows]

    def outbox_delivery_state(
        self,
        context: TenantContext,
        event_id: str,
    ) -> dict[str, Any]:
        event_id = require_resource_id(event_id, "event_id")
        with self._lock:
            self._authorize(self._connection, context, self.READ)
            event = self._outbox_row(self._connection, context, event_id)
        return {
            "tenant_id": event["tenant_id"],
            "project_id": event["project_id"],
            "actor_id": event["actor_id"],
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "aggregate_id": event["aggregate_id"],
            "payload_digest": event["payload_digest"],
            "delivery_phase": event["delivery_phase"],
            "delivery_attempt": event["delivery_attempt"],
            "lease_expires_at": event["lease_expires_at"],
            "executor_id": event["executor_id"],
            "last_executor_id": event["last_executor_id"],
            "last_error_code": event["last_error_code"],
            "published_at": event["published_at"],
            "delivery_receipt_digest": event["delivery_receipt_digest"],
            "reconciliation_receipt_digest": event["reconciliation_receipt_digest"],
        }

    def claim_next_outbox_event(
        self,
        context: TenantContext,
        *,
        worker_capability: object,
        claim_token: str,
        executor_id: str,
        lease_seconds: int = 300,
    ) -> dict[str, Any] | None:
        self._require_worker_capability(worker_capability)
        _claim_token, claim_token_digest = self._claim_token(claim_token)
        executor_id = self._scope_text(executor_id, "executor_id", 256)
        lease_seconds = self._lease_seconds(lease_seconds)
        now_value, now = self._outbox_now()
        lease_expires_at = (now_value + timedelta(seconds=lease_seconds)).isoformat()
        with self._transaction() as connection:
            self._authorize_worker_admin(connection, context)
            scope = (context.tenant_id, context.project_id, context.actor_id)
            connection.execute(
                """
                UPDATE knowledge_outbox_delivery_states
                   SET phase='UNKNOWN',
                       last_claim_token_digest=claim_token_digest,
                       last_executor_id=executor_id,
                       claim_token_digest=NULL,executor_id=NULL,lease_expires_at=NULL,
                       last_error_code='KNOWLEDGE_OUTBOX_DISPATCH_OUTCOME_UNKNOWN',
                       updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND phase='DISPATCHING' AND lease_expires_at<=?
                """,
                (now, *scope, now),
            )
            connection.execute(
                """
                UPDATE knowledge_outbox_delivery_states
                   SET phase='BLOCKED',
                       last_claim_token_digest=coalesce(claim_token_digest,last_claim_token_digest),
                       last_executor_id=coalesce(executor_id,last_executor_id),
                       claim_token_digest=NULL,executor_id=NULL,lease_expires_at=NULL,
                       last_error_code='KNOWLEDGE_OUTBOX_ATTEMPT_LIMIT_EXCEEDED',
                       updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=?
                   AND attempt>=?
                   AND (phase='PENDING' OR (phase='CLAIMED' AND lease_expires_at<=?))
                """,
                (now, *scope, _MAX_OUTBOX_DELIVERY_ATTEMPTS, now),
            )
            candidate = connection.execute(
                """
                SELECT d.event_id
                  FROM knowledge_outbox_delivery_states AS d
                  JOIN knowledge_outbox_events AS e
                    ON e.tenant_id=d.tenant_id AND e.project_id=d.project_id
                   AND e.actor_id=d.actor_id AND e.event_id=d.event_id
                 WHERE d.tenant_id=? AND d.project_id=? AND d.actor_id=?
                   AND e.published_at IS NULL AND d.attempt<?
                   AND (d.phase='PENDING'
                        OR (d.phase='CLAIMED' AND d.lease_expires_at<=?))
                 ORDER BY e.occurred_at ASC,e.event_id ASC LIMIT 1
                """,
                (*scope, _MAX_OUTBOX_DELIVERY_ATTEMPTS, now),
            ).fetchone()
            if candidate is None:
                return None
            event_id = str(candidate["event_id"])
            prior = self._outbox_row(connection, context, event_id)
            if prior["delivery_phase"] == "CLAIMED":
                prior_last_token = prior["claim_token_digest"]
                prior_last_executor = prior["executor_id"]
            elif prior["delivery_phase"] == "PENDING":
                prior_last_token = prior["last_claim_token_digest"]
                prior_last_executor = prior["last_executor_id"]
            else:
                raise IntegrityError("KNOWLEDGE_OUTBOX_CLAIM_STATE_DRIFT")
            updated = connection.execute(
                """
                UPDATE knowledge_outbox_delivery_states
                   SET phase='CLAIMED',attempt=attempt+1,claim_token_digest=?,
                       executor_id=?,lease_expires_at=?,last_claim_token_digest=?,
                       last_executor_id=?,last_error_code=NULL,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=? AND event_id=?
                   AND attempt<?
                   AND (phase='PENDING' OR (phase='CLAIMED' AND lease_expires_at<=?))
                """,
                (
                    claim_token_digest,
                    executor_id,
                    lease_expires_at,
                    prior_last_token,
                    prior_last_executor,
                    now,
                    *scope,
                    event_id,
                    _MAX_OUTBOX_DELIVERY_ATTEMPTS,
                    now,
                ),
            )
            if updated.rowcount != 1:
                raise ConflictError("KNOWLEDGE_OUTBOX_CLAIM_CONFLICT")
            claimed = self._outbox_row(connection, context, event_id)
            return {
                **self._public_outbox_event(claimed),
                "delivery_phase": claimed["delivery_phase"],
                "delivery_attempt": claimed["delivery_attempt"],
                "claim_token_digest": claimed["claim_token_digest"],
                "executor_id": claimed["executor_id"],
                "lease_expires_at": claimed["lease_expires_at"],
            }

    def mark_outbox_dispatching(
        self,
        context: TenantContext,
        event_id: str,
        *,
        worker_capability: object,
        claim_token: str,
    ) -> dict[str, Any]:
        self._require_worker_capability(worker_capability)
        event_id = require_resource_id(event_id, "event_id")
        _claim_token, claim_token_digest = self._claim_token(claim_token)
        now_value, now = self._outbox_now()
        with self._transaction() as connection:
            self._authorize_worker_admin(connection, context)
            event = self._outbox_row(connection, context, event_id)
            if event["delivery_phase"] != "CLAIMED":
                raise ConflictError("KNOWLEDGE_OUTBOX_DISPATCH_TRANSITION_INVALID")
            if not hmac.compare_digest(str(event["claim_token_digest"]), claim_token_digest):
                raise AuthorizationError("KNOWLEDGE_OUTBOX_CLAIM_FENCE_MISMATCH")
            lease_expires_at = self._stored_outbox_timestamp(
                event["lease_expires_at"],
                "lease_expires_at",
            )
            if lease_expires_at <= now_value:
                raise ConflictError("KNOWLEDGE_OUTBOX_CLAIM_LEASE_EXPIRED")
            updated = connection.execute(
                """
                UPDATE knowledge_outbox_delivery_states SET phase='DISPATCHING',updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=? AND event_id=?
                   AND phase='CLAIMED' AND claim_token_digest=? AND lease_expires_at>?
                """,
                (
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    event_id,
                    claim_token_digest,
                    now,
                ),
            )
            if updated.rowcount != 1:
                raise ConflictError("KNOWLEDGE_OUTBOX_DISPATCH_TRANSITION_INVALID")
            return {
                "event_id": event_id,
                "delivery_phase": "DISPATCHING",
                "delivery_attempt": event["delivery_attempt"],
                "claim_token_digest": claim_token_digest,
                "executor_id": event["executor_id"],
                "lease_expires_at": event["lease_expires_at"],
            }

    def mark_outbox_unknown(
        self,
        context: TenantContext,
        event_id: str,
        *,
        worker_capability: object,
        claim_token: str,
        error_code: str,
    ) -> dict[str, Any]:
        self._require_worker_capability(worker_capability)
        event_id = require_resource_id(event_id, "event_id")
        _claim_token, claim_token_digest = self._claim_token(claim_token)
        error_code = self._scope_text(error_code, "error_code", 128)
        _now_value, now = self._outbox_now()
        with self._transaction() as connection:
            self._authorize_worker_admin(connection, context)
            event = self._outbox_row(connection, context, event_id)
            if event["delivery_phase"] == "UNKNOWN":
                if (
                    not hmac.compare_digest(
                        str(event["last_claim_token_digest"]),
                        claim_token_digest,
                    )
                    or event["last_error_code"] != error_code
                ):
                    raise ConflictError("KNOWLEDGE_OUTBOX_UNKNOWN_RECEIPT_CONFLICT")
                return {
                    "event_id": event_id,
                    "delivery_phase": "UNKNOWN",
                    "delivery_attempt": event["delivery_attempt"],
                    "last_error_code": error_code,
                }
            if event["delivery_phase"] == "PUBLISHED":
                if event["last_claim_token_digest"] is not None and hmac.compare_digest(
                    str(event["last_claim_token_digest"]),
                    claim_token_digest,
                ):
                    return {
                        "event_id": event_id,
                        "delivery_phase": "PUBLISHED",
                        "delivery_attempt": event["delivery_attempt"],
                        "published_at": event["published_at"],
                    }
                raise ConflictError("KNOWLEDGE_OUTBOX_UNKNOWN_TRANSITION_INVALID")
            if event["delivery_phase"] != "DISPATCHING":
                raise ConflictError("KNOWLEDGE_OUTBOX_UNKNOWN_TRANSITION_INVALID")
            if not hmac.compare_digest(str(event["claim_token_digest"]), claim_token_digest):
                raise AuthorizationError("KNOWLEDGE_OUTBOX_CLAIM_FENCE_MISMATCH")
            updated = connection.execute(
                """
                UPDATE knowledge_outbox_delivery_states
                   SET phase='UNKNOWN',last_claim_token_digest=claim_token_digest,
                       last_executor_id=executor_id,claim_token_digest=NULL,
                       executor_id=NULL,lease_expires_at=NULL,last_error_code=?,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=? AND event_id=?
                   AND phase='DISPATCHING' AND claim_token_digest=?
                """,
                (
                    error_code,
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    event_id,
                    claim_token_digest,
                ),
            )
            if updated.rowcount != 1:
                raise ConflictError("KNOWLEDGE_OUTBOX_UNKNOWN_TRANSITION_INVALID")
            return {
                "event_id": event_id,
                "delivery_phase": "UNKNOWN",
                "delivery_attempt": event["delivery_attempt"],
                "last_error_code": error_code,
            }

    @classmethod
    def _transport_receipt(
        cls,
        receipt: object,
        *,
        event_id: str,
        payload_digest: str,
    ) -> dict[str, Any]:
        expected_keys = {
            "event_id",
            "payload_digest",
            "delivery_state",
            "provider_message_id",
        }
        if not isinstance(receipt, Mapping) or set(receipt) != expected_keys:
            raise ValidationError("KNOWLEDGE_OUTBOX_TRANSPORT_RECEIPT_INVALID")
        if (
            receipt.get("event_id") != event_id
            or receipt.get("payload_digest") != payload_digest
            or receipt.get("delivery_state") != "DELIVERED"
        ):
            raise IntegrityError("KNOWLEDGE_OUTBOX_TRANSPORT_RECEIPT_BINDING_MISMATCH")
        provider_message_id = cls._scope_text(
            receipt.get("provider_message_id"),
            "provider_message_id",
            512,
        )
        return {
            "event_id": event_id,
            "payload_digest": payload_digest,
            "delivery_state": "DELIVERED",
            "provider_message_id": provider_message_id,
        }

    @staticmethod
    def _delivery_binding(
        context: TenantContext,
        event: Mapping[str, Any],
        *,
        delivery_state: str,
        provider_message_id: str | None,
        claim_token_digest: str | None = None,
        transport_receipt_digest: str | None = None,
        reconciliation_receipt_digest: str | None = None,
        from_phase: str | None = None,
    ) -> dict[str, Any]:
        binding: dict[str, Any] = {
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "actor_id": context.actor_id,
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "aggregate_id": event["aggregate_id"],
            "payload_digest": event["payload_digest"],
            "delivery_state": delivery_state,
            "provider_message_id": provider_message_id,
            "attempt": event["delivery_attempt"],
        }
        if claim_token_digest is not None:
            binding["claim_token_digest"] = claim_token_digest
        if transport_receipt_digest is not None:
            binding["transport_receipt_digest"] = transport_receipt_digest
        if reconciliation_receipt_digest is not None:
            binding["reconciliation_receipt_digest"] = reconciliation_receipt_digest
        if from_phase is not None:
            binding["from_phase"] = from_phase
        return binding

    def mark_outbox_published(
        self,
        context: TenantContext,
        event_id: str,
        *,
        worker_capability: object,
        delivery_receipt: Mapping[str, Any],
        claim_token: str | None = None,
        transport_receipt: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_worker_capability(worker_capability)
        event_id = require_resource_id(event_id, "event_id")
        _claim_token, claim_token_digest = self._claim_token(claim_token)
        _now_value, now = self._outbox_now()
        with self._transaction() as connection:
            self._authorize_worker_admin(connection, context)
            event = self._outbox_row(connection, context, event_id)
            verified_transport = self._transport_receipt(
                transport_receipt,
                event_id=event_id,
                payload_digest=event["payload_digest"],
            )
            transport_json = canonical_json(verified_transport)
            transport_digest = sha256_bytes(transport_json.encode("utf-8"))
            binding = self._delivery_binding(
                context,
                event,
                delivery_state="DELIVERED",
                provider_message_id=verified_transport["provider_message_id"],
                claim_token_digest=claim_token_digest,
                transport_receipt_digest=transport_digest,
            )
            replay = event["delivery_phase"] == "PUBLISHED"
            if replay:
                if event["last_claim_token_digest"] is None or not hmac.compare_digest(
                    str(event["last_claim_token_digest"]),
                    claim_token_digest,
                ):
                    raise ConflictError("KNOWLEDGE_OUTBOX_PUBLICATION_FENCE_CONFLICT")
            elif event["delivery_phase"] != "DISPATCHING":
                raise ConflictError("KNOWLEDGE_OUTBOX_PUBLICATION_TRANSITION_INVALID")
            elif not hmac.compare_digest(
                str(event["claim_token_digest"]),
                claim_token_digest,
            ):
                raise AuthorizationError("KNOWLEDGE_OUTBOX_CLAIM_FENCE_MISMATCH")
            verified_receipt = self._worker_receipt(
                delivery_receipt,
                binding,
                require_fresh=not replay,
            )
            expected_executor = event["last_executor_id"] if replay else event["executor_id"]
            if verified_receipt["executor_id"] != expected_executor:
                raise IntegrityError(
                    "KNOWLEDGE_WORKER_RECEIPT_BINDING_MISMATCH",
                    details={"field": "executor_id"},
                )
            if replay:
                if event["transport_receipt"] != verified_transport:
                    raise ConflictError("KNOWLEDGE_OUTBOX_TRANSPORT_RECEIPT_CONFLICT")
                if event["publication_receipt"] != verified_receipt:
                    raise ConflictError("KNOWLEDGE_OUTBOX_PUBLICATION_RECEIPT_CONFLICT")
                return {
                    "event_id": event_id,
                    "published_at": event["published_at"],
                    "delivery_phase": "PUBLISHED",
                    "delivery_attempt": event["delivery_attempt"],
                    "delivery_receipt_digest": verified_receipt["receipt_digest"],
                    "transport_receipt_digest": transport_digest,
                }
            encoded_receipt = canonical_json(verified_receipt)
            receipt_digest = sha256_bytes(encoded_receipt.encode("utf-8"))
            connection.execute(
                """
                INSERT INTO knowledge_outbox_publications VALUES (?,?,?,?,?,?,?)
                """,
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    event_id,
                    encoded_receipt,
                    receipt_digest,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE knowledge_outbox_events SET published_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=? AND event_id=?
                   AND published_at IS NULL
                """,
                (now, context.tenant_id, context.project_id, context.actor_id, event_id),
            )
            updated = connection.execute(
                """
                UPDATE knowledge_outbox_delivery_states
                   SET phase='PUBLISHED',last_claim_token_digest=claim_token_digest,
                       last_executor_id=executor_id,claim_token_digest=NULL,
                       executor_id=NULL,lease_expires_at=NULL,last_error_code=NULL,
                       transport_receipt_json=?,transport_receipt_digest=?,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=? AND event_id=?
                   AND phase='DISPATCHING' AND claim_token_digest=?
                """,
                (
                    transport_json,
                    transport_digest,
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    event_id,
                    claim_token_digest,
                ),
            )
            if updated.rowcount != 1:
                raise ConflictError("KNOWLEDGE_OUTBOX_PUBLICATION_TRANSITION_INVALID")
            return {
                "event_id": event_id,
                "published_at": now,
                "delivery_phase": "PUBLISHED",
                "delivery_attempt": event["delivery_attempt"],
                "delivery_receipt_digest": verified_receipt["receipt_digest"],
                "transport_receipt_digest": transport_digest,
            }

    @classmethod
    def _reconciliation_receipt(
        cls,
        context: TenantContext,
        event: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected_keys = {
            "tenant_id",
            "project_id",
            "actor_id",
            "event_id",
            "event_type",
            "aggregate_id",
            "payload_digest",
            "delivery_state",
            "provider_message_id",
            "reconciliation_id",
        }
        if not isinstance(receipt, Mapping) or set(receipt) != expected_keys:
            raise ValidationError("KNOWLEDGE_OUTBOX_RECONCILIATION_RECEIPT_INVALID")
        expected_values = {
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "actor_id": context.actor_id,
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "aggregate_id": event["aggregate_id"],
            "payload_digest": event["payload_digest"],
        }
        for key, expected in expected_values.items():
            if receipt.get(key) != expected:
                raise IntegrityError(
                    "KNOWLEDGE_OUTBOX_RECONCILIATION_BINDING_MISMATCH",
                    details={"field": key},
                )
        delivery_state = receipt.get("delivery_state")
        if delivery_state not in {"DELIVERED", "NOT_DELIVERED"}:
            raise ValidationError("KNOWLEDGE_OUTBOX_RECONCILIATION_STATE_INVALID")
        provider_message_id = receipt.get("provider_message_id")
        if delivery_state == "DELIVERED":
            provider_message_id = cls._scope_text(
                provider_message_id,
                "provider_message_id",
                512,
            )
        elif provider_message_id is not None:
            raise ValidationError("KNOWLEDGE_OUTBOX_RECONCILIATION_RECEIPT_INVALID")
        raw_reconciliation_id = receipt.get("reconciliation_id")
        if not isinstance(raw_reconciliation_id, str):
            raise ValidationError("KNOWLEDGE_OUTBOX_RECONCILIATION_RECEIPT_INVALID")
        try:
            reconciliation_id = require_idempotency_key(raw_reconciliation_id)
        except ValidationError as error:
            raise ValidationError("KNOWLEDGE_OUTBOX_RECONCILIATION_RECEIPT_INVALID") from error
        return {
            **expected_values,
            "delivery_state": delivery_state,
            "provider_message_id": provider_message_id,
            "reconciliation_id": reconciliation_id,
        }

    def reconcile_outbox_delivery(
        self,
        context: TenantContext,
        event_id: str,
        *,
        worker_capability: object,
        reconciliation_receipt: Mapping[str, Any],
        execution_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._require_worker_capability(worker_capability)
        event_id = require_resource_id(event_id, "event_id")
        _now_value, now = self._outbox_now()
        with self._transaction() as connection:
            self._authorize_worker_admin(connection, context)
            event = self._outbox_row(connection, context, event_id)
            verified_reconciliation = self._reconciliation_receipt(
                context,
                event,
                reconciliation_receipt,
            )
            reconciliation_json = canonical_json(verified_reconciliation)
            reconciliation_digest = sha256_bytes(reconciliation_json.encode("utf-8"))
            binding = self._delivery_binding(
                context,
                event,
                delivery_state=str(verified_reconciliation["delivery_state"]),
                provider_message_id=verified_reconciliation["provider_message_id"],
                reconciliation_receipt_digest=reconciliation_digest,
                from_phase="UNKNOWN",
            )
            expected_phase = (
                "PUBLISHED"
                if verified_reconciliation["delivery_state"] == "DELIVERED"
                else "PENDING"
            )
            replay = event["delivery_phase"] == expected_phase and event[
                "reconciliation_receipt"
            ] is not None
            if not replay and event["delivery_phase"] != "UNKNOWN":
                raise ConflictError("KNOWLEDGE_OUTBOX_RECONCILIATION_TRANSITION_INVALID")
            verified_execution = self._worker_receipt(
                execution_receipt,
                binding,
                require_fresh=True,
            )
            envelope = {
                "provider_receipt": verified_reconciliation,
                "worker_receipt": verified_execution,
            }
            envelope_json = canonical_json(envelope)
            envelope_digest = sha256_bytes(envelope_json.encode("utf-8"))
            if replay:
                prior_envelope = event["reconciliation_receipt"]
                if (
                    not isinstance(prior_envelope, dict)
                    or set(prior_envelope) != {"provider_receipt", "worker_receipt"}
                    or prior_envelope["provider_receipt"] != verified_reconciliation
                    or not isinstance(prior_envelope["worker_receipt"], Mapping)
                ):
                    raise ConflictError("KNOWLEDGE_OUTBOX_RECONCILIATION_RECEIPT_CONFLICT")
                prior_execution = self._worker_receipt(
                    prior_envelope["worker_receipt"],
                    binding,
                    require_fresh=False,
                )
                if expected_phase == "PUBLISHED" and event["publication_receipt"] != prior_execution:
                    raise ConflictError("KNOWLEDGE_OUTBOX_PUBLICATION_RECEIPT_CONFLICT")
                return {
                    "event_id": event_id,
                    "delivery_phase": expected_phase,
                    "delivery_attempt": event["delivery_attempt"],
                    "reconciliation_state": verified_reconciliation["delivery_state"],
                    "reconciliation_receipt_digest": event[
                        "reconciliation_receipt_digest"
                    ],
                    "delivery_receipt_digest": (
                        prior_execution["receipt_digest"]
                        if expected_phase == "PUBLISHED"
                        else None
                    ),
                    "published_at": event["published_at"],
                }
            published_at: str | None = None
            if expected_phase == "PUBLISHED":
                encoded_execution = canonical_json(verified_execution)
                connection.execute(
                    """
                    INSERT INTO knowledge_outbox_publications VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        context.tenant_id,
                        context.project_id,
                        context.actor_id,
                        event_id,
                        encoded_execution,
                        sha256_bytes(encoded_execution.encode("utf-8")),
                        now,
                    ),
                )
                connection.execute(
                    """
                    UPDATE knowledge_outbox_events SET published_at=?
                     WHERE tenant_id=? AND project_id=? AND actor_id=? AND event_id=?
                       AND published_at IS NULL
                    """,
                    (now, context.tenant_id, context.project_id, context.actor_id, event_id),
                )
                published_at = now
            updated = connection.execute(
                """
                UPDATE knowledge_outbox_delivery_states
                   SET phase=?,last_error_code=?,reconciliation_receipt_json=?,
                       reconciliation_receipt_digest=?,updated_at=?
                 WHERE tenant_id=? AND project_id=? AND actor_id=? AND event_id=?
                   AND phase='UNKNOWN'
                """,
                (
                    expected_phase,
                    (
                        "KNOWLEDGE_OUTBOX_RECONCILED_DELIVERED"
                        if expected_phase == "PUBLISHED"
                        else None
                    ),
                    envelope_json,
                    envelope_digest,
                    now,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    event_id,
                ),
            )
            if updated.rowcount != 1:
                raise ConflictError("KNOWLEDGE_OUTBOX_RECONCILIATION_TRANSITION_INVALID")
            return {
                "event_id": event_id,
                "delivery_phase": expected_phase,
                "delivery_attempt": event["delivery_attempt"],
                "reconciliation_state": verified_reconciliation["delivery_state"],
                "reconciliation_receipt_digest": envelope_digest,
                "delivery_receipt_digest": (
                    verified_execution["receipt_digest"]
                    if expected_phase == "PUBLISHED"
                    else None
                ),
                "published_at": published_at,
            }
