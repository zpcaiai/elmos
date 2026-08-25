"""Trusted local delivery boundary for Skills 37, 38, and 39.

The service accepts content and metadata, never caller-selected filesystem
locations.  Administrator-owned roots are pinned at construction time; staged
sessions and operation receipts are persisted in an exact SQLite schema.
"""

from __future__ import annotations

import base64
import binascii
import os
import sqlite3
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from . import artifacts as artifact_module
from . import delivery_skills
from .artifacts import (
    ArtifactLifecycleStore,
    ArtifactPublisher,
    ArtifactRecord,
    ArtifactValidationError,
    LifecycleError,
    OutputMode,
    OutputPlan,
    PublishedOutput,
    PublicationError,
)
from .canonical import (
    canonical_digest,
    canonical_json_bytes,
    normalize_relative_path,
    parse_json_strict,
    path_collision_key,
    require_sha256,
    safe_join,
    sha256_bytes,
)
from .contracts import ContractError, RuntimeRequest, require_resource_id, require_text


_SCHEMA_VERSION = 1
_SCHEMA_KEY = "elmos.autonomous-qa.trusted-delivery"
_SESSION_STATES = frozenset(
    {
        "STAGED",
        "STAGE_DURABILITY_UNKNOWN",
        "PUBLISHING",
        "PUBLISHED",
        "PARTIAL",
        "DURABILITY_UNKNOWN",
        "FAILED",
    }
)
_RUN_MODES = frozenset(
    {"plan-only", "generate", "verify", "repair", "certify", "continuous"}
)
_LIFECYCLE_ACTIONS = frozenset(
    {
        "register",
        "mark_stale",
        "supersede",
        "legal_hold",
        "reference",
        "candidates",
        "recover",
        "collect",
    }
)
_ARTIFACT_FIELDS = frozenset(
    {
        "artifact_id",
        "path",
        "category",
        "role",
        "producer",
        "source_bytes",
        "required",
        "validation_status",
        "requirement_refs",
        "test_case_refs",
        "risk_justification",
    }
)
_ARTIFACT_REQUIRED_FIELDS = frozenset(
    {"artifact_id", "path", "category", "role", "producer", "source_bytes"}
)
_RUNTIME_CONTEXT_FIELDS = frozenset(
    {"tenant_id", "project_id", "actor_id", "request_id", "idempotency_key"}
)
_EMITTER_ARTIFACT_FIELDS = frozenset(
    {
        "artifact_id",
        "path",
        "category",
        "role",
        "source_text",
        "content_base64",
        "encoding",
        "sha256",
        "size_bytes",
        "producer",
        "required",
        "validation_status",
        "test_case_refs",
        "requirement_refs",
        "lineage",
        "quality_scan",
        "diff",
        "replay_argv",
        "replay_commands",
        "object_key_draft",
    }
)
_EMITTER_MAPPING: Mapping[str, tuple[str, str, str]] = {
    "test-source": ("generated-test-source", "test_source", "application"),
    "fixture-data": ("generated-fixture-data", "test_fixture", "fixture"),
    "mock-data": ("generated-mock-data", "test_mock", "mock"),
    "synthetic-data": ("generated-synthetic-data", "test_data", "test_data"),
    "config": ("generated-runtime-config", "test_config", "configuration"),
}
_EMITTER_PRODUCER = "elmos.autonomous-qa.test-source-emitter.v1"


class DeliveryError(RuntimeError):
    """Base failure for the trusted delivery boundary."""


class DeliveryContractError(ContractError):
    """Caller input is not exact, bounded, or canonical."""


class DeliveryAuthorizationError(PermissionError):
    """The requested tenant/project scope is not administrator configured."""


class DeliveryStateError(DeliveryError):
    """Persisted state is missing, conflicting, or tampered."""


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


@dataclass(frozen=True, slots=True)
class _ArtifactInput:
    metadata: Mapping[str, Any]
    source_bytes: bytes


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _exact_object(
    value: Any,
    *,
    label: str,
    allowed: frozenset[str],
    required: frozenset[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise DeliveryContractError(f"{label} must be an exact string-keyed object")
    extra = sorted(set(value).difference(allowed))
    missing = sorted(required.difference(value))
    if extra:
        raise DeliveryContractError(f"{label} has unsupported fields: {extra}")
    if missing:
        raise DeliveryContractError(f"{label} is missing required fields: {missing}")
    return value


def _resource_id(value: Any, field: str) -> str:
    try:
        return require_resource_id(value, field)
    except ContractError as exc:
        raise DeliveryContractError(str(exc)) from exc


def _digest(value: Any, field: str) -> str:
    try:
        return require_sha256(value, field=field)
    except (AttributeError, TypeError, ValueError) as exc:
        raise DeliveryContractError(f"{field} must be a SHA-256 digest") from exc


def _external_boundaries() -> dict[str, str]:
    return {
        "object_upload": "NOT_RUN",
        "signing": "NOT_RUN",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def _runtime_context(value: Any) -> Mapping[str, Any]:
    context = _exact_object(
        value,
        label="_runtime_context",
        allowed=_RUNTIME_CONTEXT_FIELDS,
        required=_RUNTIME_CONTEXT_FIELDS,
    )
    for field in ("tenant_id", "project_id", "actor_id", "request_id"):
        _resource_id(context[field], f"_runtime_context.{field}")
    try:
        require_text(
            context["idempotency_key"],
            "_runtime_context.idempotency_key",
            maximum=200,
        )
    except ContractError as exc:
        raise DeliveryContractError(str(exc)) from exc
    return context


def _lifecycle_payload(
    inputs: Any, *, runtime_context_required: bool
) -> tuple[str, Mapping[str, Any]]:
    if not isinstance(inputs, Mapping) or any(type(key) is not str for key in inputs):
        raise DeliveryContractError("lifecycle inputs must be an exact object")
    action = inputs.get("action")
    if not isinstance(action, str) or action not in _LIFECYCLE_ACTIONS:
        raise DeliveryContractError("lifecycle action is unsupported")
    allowed_by_action = {
        "register": {"session_id"},
        "mark_stale": {"output_id"},
        "supersede": {"old_output_id", "new_output_id"},
        "legal_hold": {"output_id", "enabled"},
        "reference": {"output_id", "reference_id", "present"},
        "candidates": set(),
        "recover": set(),
        "collect": {"dry_run"},
    }
    base_fields = {"action"}
    if runtime_context_required:
        base_fields.add("_runtime_context")
    expected = base_fields | allowed_by_action[action]
    exact = _exact_object(
        inputs,
        label="lifecycle inputs",
        allowed=frozenset(expected),
        required=frozenset(expected),
    )
    if runtime_context_required:
        _runtime_context(exact["_runtime_context"])
    normalized = {"action": action}
    for field in (
        "session_id",
        "output_id",
        "old_output_id",
        "new_output_id",
        "reference_id",
    ):
        if field in exact:
            normalized[field] = _resource_id(exact[field], field)
    for field in ("enabled", "present", "dry_run"):
        if field in exact:
            if type(exact[field]) is not bool:
                raise DeliveryContractError(f"{field} must be an exact boolean")
            normalized[field] = exact[field]
    return action, normalized


def publishing_operation_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Pure Skill 38 contract used when no trusted delivery binder is present."""

    exact = _exact_object(
        inputs,
        label="publishing inputs",
        allowed=frozenset({"session_id", "_runtime_context"}),
        required=frozenset({"session_id", "_runtime_context"}),
    )
    session_id = _resource_id(exact["session_id"], "session_id")
    _runtime_context(exact["_runtime_context"])
    return {
        "state": "BLOCKED",
        "code": "TRUSTED_DELIVERY_BINDER_REQUIRED",
        "outputs": {
            "session_id": session_id,
            "trusted_service": "TrustedDeliveryService.execute_publishing",
            "publication_performed": False,
            "external_adapter": "EXTERNAL_ADAPTER_REQUIRED",
            **_external_boundaries(),
        },
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


def lifecycle_operation_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Pure Skill 39 contract used when no trusted delivery binder is present."""

    action, normalized = _lifecycle_payload(inputs, runtime_context_required=True)
    return {
        "state": "BLOCKED",
        "code": "TRUSTED_DELIVERY_BINDER_REQUIRED",
        "outputs": {
            "action": action,
            "validated_request": normalized,
            "trusted_service": "TrustedDeliveryService.execute_lifecycle",
            "mutation_performed": False,
            "external_adapter": "EXTERNAL_ADAPTER_REQUIRED",
            **_external_boundaries(),
        },
        "implementation_state": "EXTERNAL_ADAPTER_REQUIRED",
    }


class TrustedDeliveryService:
    """Persist and execute trusted local artifact delivery operations."""

    _SCHEMA_METADATA_SQL = f"""
        CREATE TABLE delivery_schema (
            schema_key TEXT NOT NULL PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            physical_fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (schema_key = '{_SCHEMA_KEY}'),
            CHECK (schema_version = {_SCHEMA_VERSION}),
            CHECK (
                length(physical_fingerprint) = 64
                AND physical_fingerprint NOT GLOB '*[^0-9a-f]*'
            ),
            CHECK (length(created_at) > 0)
        )
    """
    _SCHEMA_SESSIONS_SQL = """
        CREATE TABLE delivery_sessions (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            output_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            input_digest TEXT NOT NULL,
            plan_json BLOB NOT NULL,
            plan_digest TEXT NOT NULL,
            artifact_manifest_json BLOB NOT NULL,
            artifact_manifest_digest TEXT NOT NULL,
            stage_durability_status TEXT NOT NULL,
            published_output_json BLOB,
            published_output_digest TEXT,
            lifecycle_registered INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, project_id, session_id),
            UNIQUE (tenant_id, project_id, idempotency_key),
            CHECK (length(tenant_id) > 0 AND length(project_id) > 0),
            CHECK (length(session_id) > 0 AND length(output_id) > 0),
            CHECK (length(idempotency_key) > 0),
            CHECK (length(input_digest) = 64 AND input_digest NOT GLOB '*[^0-9a-f]*'),
            CHECK (typeof(plan_json) = 'blob' AND length(plan_json) > 0),
            CHECK (length(plan_digest) = 64 AND plan_digest NOT GLOB '*[^0-9a-f]*'),
            CHECK (typeof(artifact_manifest_json) = 'blob' AND length(artifact_manifest_json) > 0),
            CHECK (length(artifact_manifest_digest) = 64 AND artifact_manifest_digest NOT GLOB '*[^0-9a-f]*'),
            CHECK (stage_durability_status IN ('DURABLE', 'COMMITTED_DURABILITY_UNKNOWN')),
            CHECK (lifecycle_registered IN (0, 1)),
            CHECK (status IN ('STAGED', 'STAGE_DURABILITY_UNKNOWN', 'PUBLISHING', 'PUBLISHED', 'PARTIAL', 'DURABILITY_UNKNOWN', 'FAILED')),
            CHECK (version >= 1),
            CHECK (
                (published_output_json IS NULL AND published_output_digest IS NULL)
                OR
                (typeof(published_output_json) = 'blob'
                    AND length(published_output_json) > 0
                    AND length(published_output_digest) = 64
                    AND published_output_digest NOT GLOB '*[^0-9a-f]*')
            ),
            CHECK (length(created_at) > 0 AND length(updated_at) > 0)
        )
    """
    _SCHEMA_RECEIPTS_SQL = """
        CREATE TABLE delivery_receipts (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            input_digest TEXT NOT NULL,
            result_json BLOB NOT NULL,
            result_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
            CHECK (length(tenant_id) > 0 AND length(project_id) > 0),
            CHECK (length(operation) > 0 AND length(idempotency_key) > 0),
            CHECK (length(input_digest) = 64 AND input_digest NOT GLOB '*[^0-9a-f]*'),
            CHECK (typeof(result_json) = 'blob' AND length(result_json) > 0),
            CHECK (length(result_digest) = 64 AND result_digest NOT GLOB '*[^0-9a-f]*'),
            CHECK (length(created_at) > 0)
        )
    """
    _SCHEMA_PUBLISHED_INDEX_SQL = """
        CREATE UNIQUE INDEX delivery_published_output_scope
        ON delivery_sessions (tenant_id, project_id, output_id)
        WHERE status IN ('PUBLISHING', 'PUBLISHED', 'PARTIAL', 'DURABILITY_UNKNOWN')
    """

    def __init__(
        self,
        *,
        staging_root: str | Path,
        publication_root: str | Path,
        lifecycle_root: str | Path,
        state_root: str | Path,
        database_path: str | Path,
        embedded_roots: Mapping[tuple[str, str], str | Path],
    ) -> None:
        self.staging_root = self._prepare_private_root(staging_root, "staging_root")
        self.publication_root = self._prepare_private_root(
            publication_root, "publication_root"
        )
        self.lifecycle_root = self._prepare_private_root(
            lifecycle_root, "lifecycle_root"
        )
        self.state_root = self._prepare_private_root(state_root, "state_root")
        service_roots = (
            self.staging_root,
            self.publication_root,
            self.lifecycle_root,
            self.state_root,
        )
        self._reject_overlapping_roots(service_roots, "service roots")
        self.database_path = Path(os.path.abspath(database_path))
        if self.database_path.parent != self.state_root:
            raise DeliveryContractError("database_path must be directly under state_root")
        try:
            normalize_relative_path(self.database_path.name)
        except ValueError as exc:
            raise DeliveryContractError("database_path has an unsafe filename") from exc
        if self.database_path.exists():
            metadata = self.database_path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise DeliveryStateError("delivery database must be one regular file")
        if not isinstance(embedded_roots, Mapping) or not embedded_roots:
            raise DeliveryContractError("embedded_roots must authorize at least one scope")
        normalized_embedded: dict[tuple[str, str], Path] = {}
        for raw_scope, raw_root in embedded_roots.items():
            if (
                not isinstance(raw_scope, tuple)
                or len(raw_scope) != 2
                or any(not isinstance(item, str) for item in raw_scope)
            ):
                raise DeliveryContractError(
                    "embedded_roots keys must be exact (tenant_id, project_id) tuples"
                )
            tenant_id = _resource_id(raw_scope[0], "embedded tenant_id")
            project_id = _resource_id(raw_scope[1], "embedded project_id")
            root = artifact_module._safe_root(Path(raw_root), "embedded_root")
            if root.is_symlink() or not root.is_dir():
                raise DeliveryContractError(
                    "embedded roots must be existing non-symlink directories"
                )
            scope = (tenant_id, project_id)
            if scope in normalized_embedded:
                raise DeliveryContractError("embedded scope is duplicated")
            normalized_embedded[scope] = root
        self._reject_overlapping_roots(
            (*service_roots, *normalized_embedded.values()), "configured roots"
        )
        self._embedded_roots = normalized_embedded
        self.lifecycle_database_path = self.lifecycle_root / "lifecycle.sqlite3"
        self._initialize_database()
        self.lifecycle_store = ArtifactLifecycleStore(
            self.lifecycle_database_path, self.publication_root
        )

    @staticmethod
    def _prepare_private_root(raw: str | Path, field: str) -> Path:
        root = artifact_module._safe_root(Path(raw), field)
        descriptors: list[int] = []
        try:
            descriptors = artifact_module._open_directory_chain_nofollow(
                root, create=True
            )
            os.fchmod(descriptors[-1], 0o700)
            artifact_module._require_private_directory_descriptor(
                descriptors[-1], field
            )
            for descriptor in reversed(descriptors):
                artifact_module._fsync_directory_descriptor(descriptor)
        except OSError as exc:
            raise DeliveryStateError(f"cannot establish private {field}") from exc
        finally:
            artifact_module._close_descriptors(descriptors)
        return root

    @staticmethod
    def _reject_overlapping_roots(roots: tuple[Path, ...], label: str) -> None:
        resolved = [root.resolve(strict=False) for root in roots]
        for index, left in enumerate(resolved):
            for right in resolved[index + 1 :]:
                if left == right or left in right.parents or right in left.parents:
                    raise DeliveryContractError(f"{label} may not overlap")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=30, factory=_ClosingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA trusted_schema = OFF")
        return connection

    @classmethod
    def _normalized_sql(cls, value: str) -> str:
        return " ".join(value.strip().rstrip(";").split())

    @classmethod
    def _expected_schema_objects(cls) -> list[dict[str, str]]:
        objects = [
            {
                "type": "table",
                "name": name,
                "table": name,
                "sql": cls._normalized_sql(sql),
            }
            for name, sql in (
                ("delivery_receipts", cls._SCHEMA_RECEIPTS_SQL),
                ("delivery_schema", cls._SCHEMA_METADATA_SQL),
                ("delivery_sessions", cls._SCHEMA_SESSIONS_SQL),
            )
        ]
        objects.append(
            {
                "type": "index",
                "name": "delivery_published_output_scope",
                "table": "delivery_sessions",
                "sql": cls._normalized_sql(cls._SCHEMA_PUBLISHED_INDEX_SQL),
            }
        )
        return sorted(objects, key=lambda item: (item["type"], item["name"]))

    @classmethod
    def _schema_fingerprint(cls) -> str:
        return canonical_digest(
            {"schema_version": _SCHEMA_VERSION, "objects": cls._expected_schema_objects()}
        )

    def _physical_schema_objects(
        self, connection: sqlite3.Connection
    ) -> list[dict[str, str]]:
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name LIMIT 5"
        ).fetchall()
        result: list[dict[str, str]] = []
        for row in rows:
            if not all(
                isinstance(row[field], str)
                for field in ("type", "name", "tbl_name", "sql")
            ):
                raise DeliveryStateError("delivery database schema is invalid")
            result.append(
                {
                    "type": str(row["type"]),
                    "name": str(row["name"]),
                    "table": str(row["tbl_name"]),
                    "sql": self._normalized_sql(str(row["sql"])),
                }
            )
        return result

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            objects = self._physical_schema_objects(connection)
            if not objects:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(self._SCHEMA_METADATA_SQL)
                connection.execute(self._SCHEMA_SESSIONS_SQL)
                connection.execute(self._SCHEMA_RECEIPTS_SQL)
                connection.execute(self._SCHEMA_PUBLISHED_INDEX_SQL)
                connection.execute(
                    "INSERT INTO delivery_schema "
                    "(schema_key, schema_version, physical_fingerprint, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (_SCHEMA_KEY, _SCHEMA_VERSION, self._schema_fingerprint(), _now()),
                )
            self._assert_schema(connection)
        try:
            artifact_module._fsync_directory(self.state_root)
        except OSError as exc:
            raise DeliveryStateError("delivery database durability is unknown") from exc

    def _assert_schema(self, connection: sqlite3.Connection) -> None:
        if self._physical_schema_objects(connection) != self._expected_schema_objects():
            raise DeliveryStateError("delivery database physical schema drift detected")
        rows = connection.execute(
            "SELECT schema_key, schema_version, physical_fingerprint "
            "FROM delivery_schema LIMIT 2"
        ).fetchall()
        if (
            len(rows) != 1
            or rows[0]["schema_key"] != _SCHEMA_KEY
            or rows[0]["schema_version"] != _SCHEMA_VERSION
            or rows[0]["physical_fingerprint"] != self._schema_fingerprint()
        ):
            raise DeliveryStateError("delivery database schema receipt is invalid")

    def _assert_database(self) -> None:
        if self.database_path.is_symlink():
            raise DeliveryStateError("delivery database path may not be a symlink")
        metadata = self.database_path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise DeliveryStateError("delivery database identity is unsafe")
        with self._connect() as connection:
            self._assert_schema(connection)

    def _authorize_scope(self, tenant: Any, project: Any) -> tuple[str, str]:
        tenant_id = _resource_id(tenant, "tenant_id")
        project_id = _resource_id(project, "project_id")
        if (tenant_id, project_id) not in self._embedded_roots:
            raise DeliveryAuthorizationError(
                "tenant/project scope is not administrator configured"
            )
        return tenant_id, project_id

    def _bound_runtime_request(
        self, request: RuntimeRequest
    ) -> tuple[str, str, str]:
        if type(request) is not RuntimeRequest:
            raise DeliveryContractError("trusted binder requires an exact RuntimeRequest")
        if request.policy or request.capabilities:
            raise DeliveryContractError(
                "delivery policy/capability envelopes require an explicit trusted evaluator"
            )
        if request.actor_id is None:
            raise DeliveryAuthorizationError("mutating delivery requires an actor")
        _resource_id(request.actor_id, "actor_id")
        _resource_id(request.request_id, "request_id")
        _resource_id(request.trace_id, "trace_id")
        if request.idempotency_key is None:
            raise DeliveryContractError("mutating delivery requires idempotency_key")
        try:
            idempotency_key = require_text(
                request.idempotency_key, "idempotency_key", maximum=200
            )
        except ContractError as exc:
            raise DeliveryContractError(str(exc)) from exc
        tenant_id, project_id = self._authorize_scope(
            request.tenant_id, request.project_id
        )
        if not isinstance(request.inputs, Mapping) or any(
            type(key) is not str for key in request.inputs
        ):
            raise DeliveryContractError("RuntimeRequest.inputs must be an exact object")
        return tenant_id, project_id, idempotency_key

    @staticmethod
    def _runtime_operation_key(idempotency_key: str, operation: str) -> str:
        return "idem-" + canonical_digest(
            {"idempotency_key": idempotency_key, "operation": operation}
        )[:48]

    @staticmethod
    def _emitted_artifacts(
        emission: Mapping[str, Any], *, suite_id: str, adapter_key: str
    ) -> tuple[list[dict[str, Any]], str]:
        if set(emission) != {"state", "code", "outputs", "implementation_state"}:
            raise DeliveryStateError("Skill 37 emission envelope fields drifted")
        if (
            emission.get("state") != "PARTIAL"
            or emission.get("code")
            != "TEST_SOURCES_EMITTED_EXTERNAL_VALIDATION_REQUIRED"
            or emission.get("implementation_state") != "LOCAL_EXECUTED"
        ):
            raise DeliveryStateError("Skill 37 emission did not reach its exact local state")
        outputs = emission.get("outputs")
        expected_output_fields = {
            "contract_schema_version",
            "suite_id",
            "adapter_key",
            "supported_adapter_profiles",
            "dsl_digest",
            "dsl_validation_state",
            "artifacts",
            "source_artifact_count",
            "fixture_artifact_count",
            "mock_artifact_count",
            "synthetic_data_artifact_count",
            "config_artifact_count",
            "manifest_draft",
            "quality_scan",
            "diff_state",
            "replay_commands",
            "collision_policy",
            "execution_boundary",
        }
        if not isinstance(outputs, Mapping) or set(outputs) != expected_output_fields:
            raise DeliveryStateError("Skill 37 output fields drifted")
        if outputs["suite_id"] != suite_id or outputs["adapter_key"] != adapter_key:
            raise DeliveryStateError("Skill 37 output identity differs from its request")
        artifacts = outputs["artifacts"]
        if (
            not isinstance(artifacts, list)
            or not artifacts
            or len(artifacts) > artifact_module.MAX_REGISTERED_ARTIFACTS
        ):
            raise DeliveryStateError("Skill 37 emitted artifact inventory is invalid")
        normalized: list[dict[str, Any]] = []
        emission_identity: list[dict[str, Any]] = []
        observed_counts = {category: 0 for category in _EMITTER_MAPPING}
        for index, raw in enumerate(artifacts):
            try:
                item = _exact_object(
                    raw,
                    label=f"Skill 37 artifacts[{index}]",
                    allowed=_EMITTER_ARTIFACT_FIELDS,
                    required=_EMITTER_ARTIFACT_FIELDS,
                )
            except DeliveryContractError as exc:
                raise DeliveryStateError("Skill 37 artifact fields drifted") from exc
            category = item["category"]
            if type(category) is not str or category not in _EMITTER_MAPPING:
                raise DeliveryStateError("Skill 37 artifact category is unsupported")
            observed_counts[category] += 1
            emitted_role, category_value, role_value = _EMITTER_MAPPING[category]
            if (
                item["role"] != emitted_role
                or item["producer"] != _EMITTER_PRODUCER
                or item["validation_status"] != "generated-unvalidated"
                or item["required"] is not True
                or item["encoding"] != "utf-8"
                or type(item["source_text"]) is not str
                or type(item["content_base64"]) is not str
                or type(item["sha256"]) is not str
                or type(item["size_bytes"]) is not int
            ):
                raise DeliveryStateError("Skill 37 artifact metadata is invalid")
            try:
                source_bytes = item["source_text"].encode("utf-8", errors="strict")
                encoded = item["content_base64"].encode("ascii", errors="strict")
                decoded = base64.b64decode(encoded, validate=True)
            except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, ValueError) as exc:
                raise DeliveryStateError("Skill 37 artifact encoding is invalid") from exc
            source_digest = "sha256:" + sha256_bytes(source_bytes)
            if (
                decoded != source_bytes
                or base64.b64encode(decoded) != encoded
                or item["sha256"] != source_digest
                or item["size_bytes"] != len(source_bytes)
            ):
                raise DeliveryStateError("Skill 37 artifact content envelope is invalid")
            requirement_refs = item["requirement_refs"]
            test_case_refs = item["test_case_refs"]
            if not isinstance(requirement_refs, list) or not isinstance(
                test_case_refs, list
            ):
                raise DeliveryStateError("Skill 37 artifact references are invalid")
            try:
                normalized_requirements = artifact_module._bounded_metadata_refs(
                    tuple(requirement_refs), "requirement_refs"
                )
                normalized_cases = artifact_module._bounded_metadata_refs(
                    tuple(test_case_refs), "test_case_refs"
                )
            except ArtifactValidationError as exc:
                raise DeliveryStateError("Skill 37 artifact references are invalid") from exc
            lineage = item["lineage"]
            if not isinstance(lineage, Mapping) or set(lineage) != {
                "suite_id",
                "dsl_digest",
                "adapter_key",
                "emitter_version",
                "content_sha256",
                "test_case_refs",
                "requirement_refs",
            }:
                raise DeliveryStateError("Skill 37 artifact lineage fields drifted")
            if (
                lineage["suite_id"] != suite_id
                or lineage["adapter_key"] != adapter_key
                or lineage["emitter_version"] != _EMITTER_PRODUCER
                or lineage["content_sha256"] != source_digest
                or lineage["dsl_digest"] != outputs["dsl_digest"]
                or lineage["test_case_refs"] != list(normalized_cases)
                or lineage["requirement_refs"] != list(normalized_requirements)
            ):
                raise DeliveryStateError("Skill 37 artifact lineage is invalid")
            quality = item["quality_scan"]
            if (
                not isinstance(quality, Mapping)
                or quality.get("status") != "LOCAL_EXECUTED"
                or quality.get("findings") != []
            ):
                raise DeliveryStateError("Skill 37 artifact quality scan did not pass")
            try:
                artifact_id = _resource_id(item["artifact_id"], "artifact_id")
            except DeliveryContractError as exc:
                raise DeliveryStateError("Skill 37 artifact identity is invalid") from exc
            if type(item["path"]) is not str:
                raise DeliveryStateError("Skill 37 artifact path is invalid")
            try:
                path = normalize_relative_path(item["path"])
            except (TypeError, ValueError) as exc:
                raise DeliveryStateError("Skill 37 artifact path is invalid") from exc
            normalized.append(
                {
                    "artifact_id": artifact_id,
                    "path": path,
                    "category": category_value,
                    "role": role_value,
                    "producer": "test-generator-v1",
                    "source_bytes": source_bytes,
                    "required": True,
                    "validation_status": "generated",
                    "requirement_refs": list(normalized_requirements),
                    "test_case_refs": list(normalized_cases),
                }
            )
            emission_identity.append(
                {
                    "artifact_id": artifact_id,
                    "path": path,
                    "sha256": source_digest,
                    "size_bytes": len(source_bytes),
                }
            )
        expected_counts = {
            "test-source": outputs["source_artifact_count"],
            "fixture-data": outputs["fixture_artifact_count"],
            "mock-data": outputs["mock_artifact_count"],
            "synthetic-data": outputs["synthetic_data_artifact_count"],
            "config": outputs["config_artifact_count"],
        }
        if any(type(value) is not int or value < 0 for value in expected_counts.values()):
            raise DeliveryStateError("Skill 37 artifact counts are invalid")
        if observed_counts != expected_counts:
            raise DeliveryStateError("Skill 37 artifact counts differ from inventory")
        return normalized, canonical_digest(
            {
                "schema_version": "elmos.autonomous-qa.skill37-stage-binding.v1",
                "suite_id": suite_id,
                "adapter_key": adapter_key,
                "dsl_digest": outputs["dsl_digest"],
                "artifacts": emission_identity,
            }
        )

    @staticmethod
    def _document(payload: object, digest: object, label: str) -> Mapping[str, Any]:
        if not isinstance(payload, bytes):
            raise DeliveryStateError(f"{label} is not stored as exact bytes")
        try:
            expected = _digest(digest, f"{label} digest")
        except DeliveryContractError as exc:
            raise DeliveryStateError(f"{label} digest is invalid") from exc
        if sha256_bytes(payload) != expected:
            raise DeliveryStateError(f"{label} digest mismatch")
        try:
            document = parse_json_strict(payload)
        except ValueError as exc:
            raise DeliveryStateError(f"{label} is invalid JSON") from exc
        if not isinstance(document, dict) or canonical_json_bytes(document) != payload:
            raise DeliveryStateError(f"{label} is not canonical")
        return document

    def _receipt(
        self,
        *,
        tenant_id: str,
        project_id: str,
        operation: str,
        idempotency_key: str,
        input_digest: str,
    ) -> Mapping[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT input_digest, result_json, result_digest "
                "FROM delivery_receipts WHERE tenant_id = ? AND project_id = ? "
                "AND operation = ? AND idempotency_key = ?",
                (tenant_id, project_id, operation, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        if row["input_digest"] != input_digest:
            raise DeliveryStateError("idempotency key was reused with different input")
        return self._document(row["result_json"], row["result_digest"], "receipt")

    @staticmethod
    def _store_receipt(
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        project_id: str,
        operation: str,
        idempotency_key: str,
        input_digest: str,
        result: Mapping[str, Any],
    ) -> None:
        payload = canonical_json_bytes(result)
        connection.execute(
            "INSERT INTO delivery_receipts "
            "(tenant_id, project_id, operation, idempotency_key, input_digest, "
            "result_json, result_digest, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                project_id,
                operation,
                idempotency_key,
                input_digest,
                sqlite3.Binary(payload),
                sha256_bytes(payload),
                _now(),
            ),
        )

    @staticmethod
    def _normalize_artifacts(value: Any) -> tuple[_ArtifactInput, ...]:
        if (
            not isinstance(value, list)
            or not value
            or len(value) > artifact_module.MAX_REGISTERED_ARTIFACTS
        ):
            raise DeliveryContractError("artifacts must be a bounded non-empty array")
        normalized: list[_ArtifactInput] = []
        path_keys: dict[str, str] = {}
        artifact_ids: set[str] = set()
        total_bytes = 0
        for index, raw in enumerate(value):
            item = _exact_object(
                raw,
                label=f"artifacts[{index}]",
                allowed=_ARTIFACT_FIELDS,
                required=_ARTIFACT_REQUIRED_FIELDS,
            )
            if type(item["path"]) is not str:
                raise DeliveryContractError("artifact path must be an exact string")
            try:
                path = normalize_relative_path(item["path"])
            except (TypeError, ValueError) as exc:
                raise DeliveryContractError("artifact path is unsafe") from exc
            collision = path_collision_key(path)
            if collision in path_keys:
                raise DeliveryContractError("artifact paths collide")
            path_keys[collision] = path
            try:
                artifact_id = artifact_module._metadata_value(
                    item["artifact_id"], "artifact_id"
                )
                category = artifact_module._metadata_value(
                    item["category"], "category"
                )
                role = artifact_module._metadata_value(item["role"], "role")
                producer = artifact_module._metadata_value(
                    item["producer"], "producer"
                )
                validation_status = artifact_module._metadata_value(
                    item.get("validation_status", "generated"),
                    "validation_status",
                )
            except ArtifactValidationError as exc:
                raise DeliveryContractError(str(exc)) from exc
            if artifact_id in artifact_ids:
                raise DeliveryContractError("artifact_id is duplicated")
            artifact_ids.add(artifact_id)
            if category not in artifact_module._ARTIFACT_CATEGORIES:
                raise DeliveryContractError("artifact category is unsupported")
            if category == "certificate":
                raise DeliveryContractError("certificate material requires an external gate")
            if role not in artifact_module._ARTIFACT_ROLES:
                raise DeliveryContractError("artifact role is unsupported")
            if producer not in artifact_module._ARTIFACT_PRODUCERS:
                raise DeliveryContractError("artifact producer is unsupported")
            if (
                validation_status in artifact_module._FORBIDDEN_EVIDENCE_LABELS
                or validation_status not in artifact_module._ARTIFACT_VALIDATION_STATUSES
            ):
                raise DeliveryContractError("artifact validation status is unsupported")
            required = item.get("required", True)
            if not isinstance(required, bool):
                raise DeliveryContractError("artifact required must be boolean")
            raw_requirement_refs = item.get("requirement_refs", [])
            raw_test_case_refs = item.get("test_case_refs", [])
            if not isinstance(raw_requirement_refs, list) or not isinstance(
                raw_test_case_refs, list
            ):
                raise DeliveryContractError("artifact references must be arrays")
            try:
                requirement_refs = artifact_module._bounded_metadata_refs(
                    tuple(raw_requirement_refs), "requirement_refs"
                )
                test_case_refs = artifact_module._bounded_metadata_refs(
                    tuple(raw_test_case_refs), "test_case_refs"
                )
            except ArtifactValidationError as exc:
                raise DeliveryContractError(str(exc)) from exc
            risk = item.get("risk_justification")
            if risk is not None:
                try:
                    risk = artifact_module._metadata_value(
                        risk, "risk_justification"
                    )
                except ArtifactValidationError as exc:
                    raise DeliveryContractError(str(exc)) from exc
            if category == "test_source" and not test_case_refs:
                raise DeliveryContractError("test source requires test-case references")
            if category == "test_source" and not requirement_refs and risk is None:
                raise DeliveryContractError("test source requires traceability")
            if required and not (requirement_refs or test_case_refs or risk):
                raise DeliveryContractError("required artifact requires traceability")
            source = item["source_bytes"]
            if type(source) is not bytes:
                raise DeliveryContractError("source_bytes must be exact bytes")
            try:
                source.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise DeliveryContractError("source_bytes must be valid UTF-8") from exc
            if len(source) > artifact_module.MAX_ARTIFACT_BYTES:
                raise DeliveryContractError("artifact source exceeds the byte limit")
            total_bytes += len(source)
            if total_bytes > artifact_module.MAX_REGISTERED_ARTIFACT_BYTES:
                raise DeliveryContractError("artifact aggregate exceeds the byte limit")
            try:
                artifact_module._scan_artifact_content(category, path, source)
            except ArtifactValidationError as exc:
                raise DeliveryContractError(str(exc)) from exc
            metadata: dict[str, Any] = {
                "artifact_id": artifact_id,
                "path": path,
                "category": category,
                "role": role,
                "producer": producer,
                "required": required,
                "validation_status": validation_status,
                "requirement_refs": list(requirement_refs),
                "test_case_refs": list(test_case_refs),
            }
            if risk is not None:
                metadata["risk_justification"] = risk
            normalized.append(_ArtifactInput(metadata=metadata, source_bytes=source))
        return tuple(sorted(normalized, key=lambda artifact: artifact.metadata["path"]))

    def _create_session_root(self, session_id: str) -> tuple[Path, bool]:
        directory_name = f"stage-{canonical_digest({'session_id': session_id})}"
        descriptors: list[int] = []
        child = -1
        durable = True
        try:
            descriptors = artifact_module._open_directory_chain_nofollow(
                self.staging_root
            )
            parent = descriptors[-1]
            artifact_module._require_private_directory_descriptor(
                parent, "delivery staging root"
            )
            try:
                os.mkdir(directory_name, mode=0o700, dir_fd=parent)
            except FileExistsError as exc:
                raise DeliveryStateError(
                    "reserved staging session already exists without a receipt"
                ) from exc
            child = os.open(
                directory_name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent,
            )
            os.fchmod(child, 0o700)
            artifact_module._require_private_directory_descriptor(
                child, "delivery staging session"
            )
            try:
                artifact_module._fsync_directory_descriptor(parent)
            except OSError:
                durable = False
            return self.staging_root / directory_name, durable
        except OSError as exc:
            raise DeliveryStateError("cannot create private staging session") from exc
        finally:
            if child >= 0:
                os.close(child)
            artifact_module._close_descriptors(descriptors)

    @staticmethod
    def _sync_staging_tree(root: Path, paths: tuple[str, ...]) -> bool:
        directories = {""}
        for path in paths:
            parent = PurePosixPath(path).parent
            while parent.as_posix() not in {"", "."}:
                directories.add(parent.as_posix())
                parent = parent.parent
        try:
            for relative in sorted(
                directories,
                key=lambda item: len(PurePosixPath(item).parts),
                reverse=True,
            ):
                target = root if not relative else safe_join(root, relative)
                descriptors = artifact_module._open_directory_chain_nofollow(target)
                try:
                    artifact_module._require_private_directory_descriptor(
                        descriptors[-1], "staging directory"
                    )
                    artifact_module._fsync_directory_descriptor(descriptors[-1])
                finally:
                    artifact_module._close_descriptors(descriptors)
            parent_descriptors = artifact_module._open_directory_chain_nofollow(
                root.parent
            )
            try:
                artifact_module._fsync_directory_descriptor(parent_descriptors[-1])
            finally:
                artifact_module._close_descriptors(parent_descriptors)
            return True
        except OSError:
            return False

    def _plan_document(
        self,
        *,
        tenant_id: str,
        project_id: str,
        revision_id: str,
        run_id: str,
        run_mode: str,
        output_mode: OutputMode,
        source_snapshot_digest: str,
        session_id: str,
        created_at: str,
    ) -> tuple[OutputPlan, dict[str, Any]]:
        embedded = (
            self._embedded_roots[(tenant_id, project_id)]
            if output_mode in {OutputMode.EMBEDDED, OutputMode.BOTH}
            else None
        )
        staging = self.staging_root / (
            f"stage-{canonical_digest({'session_id': session_id})}"
        )
        plan = OutputPlan(
            tenant_id=tenant_id,
            project_id=project_id,
            revision_id=revision_id,
            run_id=run_id,
            run_mode=run_mode,
            output_mode=output_mode,
            source_snapshot_digest=source_snapshot_digest,
            staging_root=staging,
            publication_root=self.publication_root,
            embedded_root=embedded,
            created_at=created_at,
        )
        document = {
            "schema_version": "elmos.autonomous-qa.delivery-plan.v1",
            "session_id": session_id,
            "output_id": plan.output_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "revision_id": revision_id,
            "run_id": run_id,
            "run_mode": run_mode,
            "output_mode": output_mode.value,
            "source_snapshot_digest": source_snapshot_digest,
            "created_at": created_at,
        }
        return plan, document

    def execute_materialization(
        self, request: RuntimeRequest
    ) -> Mapping[str, Any]:
        """Bind Skill 37 emission to private, durable, no-replace staging."""

        tenant_id, project_id, raw_idempotency = self._bound_runtime_request(request)
        exact = _exact_object(
            request.inputs,
            label="materialization inputs",
            allowed=frozenset(
                {
                    "suite_id",
                    "adapter_key",
                    "test_cases",
                    "fixture_records",
                    "mock_records",
                    "synthetic_data_records",
                    "config",
                    "revision_id",
                    "run_id",
                    "run_mode",
                    "output_mode",
                    "source_snapshot_digest",
                }
            ),
            required=frozenset(
                {
                    "suite_id",
                    "adapter_key",
                    "test_cases",
                    "revision_id",
                    "run_id",
                    "run_mode",
                    "output_mode",
                    "source_snapshot_digest",
                }
            ),
        )
        suite_id = _resource_id(exact["suite_id"], "suite_id")
        adapter_key = _resource_id(exact["adapter_key"], "adapter_key")
        emitter_fields = {
            "suite_id",
            "adapter_key",
            "test_cases",
            "fixture_records",
            "mock_records",
            "synthetic_data_records",
            "config",
        }
        emitter_inputs = {
            field: exact[field] for field in emitter_fields if field in exact
        }
        emitter_inputs["_runtime_context"] = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "actor_id": request.actor_id,
            "request_id": request.request_id,
            "idempotency_key": raw_idempotency,
        }
        try:
            emission = delivery_skills.emit_test_sources(emitter_inputs)
        except ContractError as exc:
            raise DeliveryContractError(str(exc)) from exc
        mapped_artifacts, emission_digest = self._emitted_artifacts(
            emission, suite_id=suite_id, adapter_key=adapter_key
        )
        stage_result = self.stage(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "revision_id": _resource_id(exact["revision_id"], "revision_id"),
                "run_id": _resource_id(exact["run_id"], "run_id"),
                "run_mode": exact["run_mode"],
                "output_mode": exact["output_mode"],
                "source_snapshot_digest": _digest(
                    exact["source_snapshot_digest"], "source_snapshot_digest"
                ),
                "idempotency_key": self._runtime_operation_key(
                    raw_idempotency, "materialization"
                ),
                "artifacts": mapped_artifacts,
            }
        )
        stage_outputs = stage_result.get("outputs")
        if (
            stage_result.get("state") not in {"SUCCEEDED", "PARTIAL"}
            or not isinstance(stage_outputs, Mapping)
        ):
            raise DeliveryStateError("staging result has no output envelope")
        durable = stage_outputs.get("stage_durability_status") == "DURABLE"
        return {
            "state": "PARTIAL",
            "code": (
                "TEST_SOURCES_STAGED_NATIVE_VALIDATION_REQUIRED"
                if durable
                else "STAGE_DURABILITY_UNKNOWN"
            ),
            "outputs": {
                **dict(stage_outputs),
                "skill37_emission_digest": emission_digest,
                "skill37_artifact_count": len(mapped_artifacts),
                "native_parser": "NOT_RUN",
                "native_linter": "NOT_RUN",
                "native_test_discovery": "NOT_RUN",
                "native_build": "NOT_RUN",
                "native_smoke": "NOT_RUN",
                "external_adapter": "EXTERNAL_ADAPTER_REQUIRED",
            },
            "implementation_state": "LOCAL_EXECUTED",
        }

    def execute_publishing(self, request: RuntimeRequest) -> Mapping[str, Any]:
        """Bind Skill 38 to deterministic build, verification, and publication."""

        tenant_id, project_id, raw_idempotency = self._bound_runtime_request(request)
        exact = _exact_object(
            request.inputs,
            label="publishing inputs",
            allowed=frozenset({"session_id"}),
            required=frozenset({"session_id"}),
        )
        return self.publish(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "session_id": _resource_id(exact["session_id"], "session_id"),
                "idempotency_key": self._runtime_operation_key(
                    raw_idempotency, "publishing"
                ),
            }
        )

    def execute_lifecycle(self, request: RuntimeRequest) -> Mapping[str, Any]:
        """Bind Skill 39 to tenant/project-authorized lifecycle operations."""

        tenant_id, project_id, raw_idempotency = self._bound_runtime_request(request)
        action, payload = _lifecycle_payload(
            request.inputs, runtime_context_required=False
        )
        return self.lifecycle(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "idempotency_key": self._runtime_operation_key(
                    raw_idempotency, f"lifecycle:{action}"
                ),
                **payload,
            }
        )

    def stage(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        exact = _exact_object(
            request,
            label="stage request",
            allowed=frozenset(
                {
                    "tenant_id",
                    "project_id",
                    "revision_id",
                    "run_id",
                    "run_mode",
                    "output_mode",
                    "source_snapshot_digest",
                    "idempotency_key",
                    "artifacts",
                }
            ),
            required=frozenset(
                {
                    "tenant_id",
                    "project_id",
                    "revision_id",
                    "run_id",
                    "run_mode",
                    "output_mode",
                    "source_snapshot_digest",
                    "idempotency_key",
                    "artifacts",
                }
            ),
        )
        tenant_id, project_id = self._authorize_scope(
            exact["tenant_id"], exact["project_id"]
        )
        self._assert_database()
        revision_id = _resource_id(exact["revision_id"], "revision_id")
        run_id = _resource_id(exact["run_id"], "run_id")
        idempotency_key = _resource_id(
            exact["idempotency_key"], "idempotency_key"
        )
        run_mode = exact["run_mode"]
        if not isinstance(run_mode, str) or run_mode not in _RUN_MODES:
            raise DeliveryContractError("run_mode is unsupported")
        try:
            output_mode = OutputMode(exact["output_mode"])
        except (TypeError, ValueError) as exc:
            raise DeliveryContractError("output_mode is unsupported") from exc
        source_snapshot_digest = _digest(
            exact["source_snapshot_digest"], "source_snapshot_digest"
        )
        artifacts = self._normalize_artifacts(exact["artifacts"])
        input_document = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "revision_id": revision_id,
            "run_id": run_id,
            "run_mode": run_mode,
            "output_mode": output_mode.value,
            "source_snapshot_digest": source_snapshot_digest,
            "artifacts": [
                {
                    **dict(artifact.metadata),
                    "source_sha256": sha256_bytes(artifact.source_bytes),
                    "size_bytes": len(artifact.source_bytes),
                }
                for artifact in artifacts
            ],
        }
        input_digest = canonical_digest(input_document)
        replay = self._receipt(
            tenant_id=tenant_id,
            project_id=project_id,
            operation="stage",
            idempotency_key=idempotency_key,
            input_digest=input_digest,
        )
        if replay is not None:
            self._verify_staged_session(
                tenant_id=tenant_id,
                project_id=project_id,
                session_id=str(replay["outputs"]["session_id"]),
            )
            return replay
        session_id = "delivery-" + canonical_digest(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "idempotency_key": idempotency_key,
            }
        )[:32]
        created_at = _now()
        plan, plan_document = self._plan_document(
            tenant_id=tenant_id,
            project_id=project_id,
            revision_id=revision_id,
            run_id=run_id,
            run_mode=run_mode,
            output_mode=output_mode,
            source_snapshot_digest=source_snapshot_digest,
            session_id=session_id,
            created_at=created_at,
        )
        stage_root, durable = self._create_session_root(session_id)
        if stage_root != plan.staging_root:
            raise DeliveryStateError("staging namespace identity mismatch")
        for artifact in artifacts:
            artifact_module._write_bytes_atomic(
                safe_join(stage_root, str(artifact.metadata["path"])),
                artifact.source_bytes,
                mode=0o600,
            )
        publisher = ArtifactPublisher(plan)
        records: list[ArtifactRecord] = []
        for artifact in artifacts:
            metadata = artifact.metadata
            records.append(
                publisher.register_file(
                    str(metadata["path"]),
                    artifact_id=str(metadata["artifact_id"]),
                    category=str(metadata["category"]),
                    role=str(metadata["role"]),
                    producer=str(metadata["producer"]),
                    required=bool(metadata["required"]),
                    validation_status=str(metadata["validation_status"]),
                    requirement_refs=tuple(metadata["requirement_refs"]),
                    test_case_refs=tuple(metadata["test_case_refs"]),
                    risk_justification=metadata.get("risk_justification"),
                )
            )
        publisher.validate()
        durable = durable and self._sync_staging_tree(
            stage_root, tuple(record.path for record in records)
        )
        manifest_document = {
            "schema_version": "elmos.autonomous-qa.delivery-stage.v1",
            "session_id": session_id,
            "output_id": plan.output_id,
            "input_digest": input_digest,
            "artifacts": [record.as_dict() for record in records],
            "artifact_count": len(records),
            "total_size_bytes": sum(record.size_bytes for record in records),
        }
        plan_bytes = canonical_json_bytes(plan_document)
        manifest_bytes = canonical_json_bytes(manifest_document)
        stage_durability = (
            "DURABLE" if durable else "COMMITTED_DURABILITY_UNKNOWN"
        )
        status = "STAGED" if durable else "STAGE_DURABILITY_UNKNOWN"
        result = {
            "state": "SUCCEEDED" if durable else "PARTIAL",
            "code": "ARTIFACTS_STAGED" if durable else "STAGE_DURABILITY_UNKNOWN",
            "outputs": {
                "session_id": session_id,
                "output_id": plan.output_id,
                "plan_digest": sha256_bytes(plan_bytes),
                "artifact_manifest": manifest_document,
                "artifact_manifest_digest": sha256_bytes(manifest_bytes),
                "stage_durability_status": stage_durability,
                "caller_paths_accepted": False,
                "overwrite_performed": False,
                **_external_boundaries(),
            },
            "implementation_state": "LOCAL_EXECUTED",
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO delivery_sessions "
                "(tenant_id, project_id, session_id, output_id, idempotency_key, "
                "input_digest, plan_json, plan_digest, artifact_manifest_json, "
                "artifact_manifest_digest, stage_durability_status, status, version, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    tenant_id,
                    project_id,
                    session_id,
                    plan.output_id,
                    idempotency_key,
                    input_digest,
                    sqlite3.Binary(plan_bytes),
                    sha256_bytes(plan_bytes),
                    sqlite3.Binary(manifest_bytes),
                    sha256_bytes(manifest_bytes),
                    stage_durability,
                    status,
                    created_at,
                    _now(),
                ),
            )
            self._store_receipt(
                connection,
                tenant_id=tenant_id,
                project_id=project_id,
                operation="stage",
                idempotency_key=idempotency_key,
                input_digest=input_digest,
                result=result,
            )
        return result

    def _session_row(
        self, *, tenant_id: str, project_id: str, session_id: str
    ) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM delivery_sessions WHERE tenant_id = ? "
                "AND project_id = ? AND session_id = ?",
                (tenant_id, project_id, session_id),
            ).fetchone()
        if row is None:
            raise DeliveryAuthorizationError(
                "delivery session is unavailable in the authorized scope"
            )
        if row["status"] not in _SESSION_STATES:
            raise DeliveryStateError("delivery session state is invalid")
        return row

    def _plan_from_row(self, row: sqlite3.Row) -> OutputPlan:
        document = self._document(row["plan_json"], row["plan_digest"], "plan")
        expected_fields = {
            "schema_version",
            "session_id",
            "output_id",
            "tenant_id",
            "project_id",
            "revision_id",
            "run_id",
            "run_mode",
            "output_mode",
            "source_snapshot_digest",
            "created_at",
        }
        if set(document) != expected_fields:
            raise DeliveryStateError("persisted plan fields are not exact")
        if (
            document["session_id"] != row["session_id"]
            or document["output_id"] != row["output_id"]
            or document["tenant_id"] != row["tenant_id"]
            or document["project_id"] != row["project_id"]
        ):
            raise DeliveryStateError("persisted plan identity mismatch")
        try:
            plan, rebuilt = self._plan_document(
                tenant_id=str(document["tenant_id"]),
                project_id=str(document["project_id"]),
                revision_id=str(document["revision_id"]),
                run_id=str(document["run_id"]),
                run_mode=str(document["run_mode"]),
                output_mode=OutputMode(document["output_mode"]),
                source_snapshot_digest=str(document["source_snapshot_digest"]),
                session_id=str(document["session_id"]),
                created_at=str(document["created_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DeliveryStateError("persisted plan is invalid") from exc
        if rebuilt != document:
            raise DeliveryStateError("persisted plan is not canonical")
        return plan

    def _publisher_from_row(
        self, row: sqlite3.Row
    ) -> tuple[ArtifactPublisher, Mapping[str, Any]]:
        plan = self._plan_from_row(row)
        manifest = self._document(
            row["artifact_manifest_json"],
            row["artifact_manifest_digest"],
            "artifact manifest",
        )
        if set(manifest) != {
            "schema_version",
            "session_id",
            "output_id",
            "input_digest",
            "artifacts",
            "artifact_count",
            "total_size_bytes",
        }:
            raise DeliveryStateError("artifact manifest fields are not exact")
        if (
            manifest["schema_version"] != "elmos.autonomous-qa.delivery-stage.v1"
            or manifest["session_id"] != row["session_id"]
            or manifest["output_id"] != row["output_id"]
            or manifest["input_digest"] != row["input_digest"]
            or not isinstance(manifest["artifacts"], list)
            or not manifest["artifacts"]
            or len(manifest["artifacts"])
            > artifact_module.MAX_REGISTERED_ARTIFACTS
            or type(manifest["artifact_count"]) is not int
            or manifest["artifact_count"] != len(manifest["artifacts"])
            or type(manifest["total_size_bytes"]) is not int
            or manifest["total_size_bytes"] < 0
            or manifest["total_size_bytes"]
            > artifact_module.MAX_REGISTERED_ARTIFACT_BYTES
        ):
            raise DeliveryStateError("artifact manifest identity is invalid")
        publisher = ArtifactPublisher(plan)
        total_size = 0
        for item in manifest["artifacts"]:
            if not isinstance(item, dict):
                raise DeliveryStateError("artifact manifest record is invalid")
            allowed = {
                "artifact_id",
                "path",
                "category",
                "role",
                "sha256",
                "size_bytes",
                "producer",
                "required",
                "validation_status",
                "requirement_refs",
                "test_case_refs",
                "risk_justification",
            }
            required = allowed - {"risk_justification"}
            if not required <= set(item) or not set(item) <= allowed:
                raise DeliveryStateError("artifact manifest record fields are invalid")
            string_fields = (
                "artifact_id",
                "path",
                "category",
                "role",
                "sha256",
                "producer",
                "validation_status",
            )
            if any(type(item[field]) is not str for field in string_fields):
                raise DeliveryStateError("artifact manifest strings are invalid")
            if (
                type(item["required"]) is not bool
                or type(item["size_bytes"]) is not int
                or item["size_bytes"] < 0
                or item["size_bytes"] > artifact_module.MAX_ARTIFACT_BYTES
                or not isinstance(item["requirement_refs"], list)
                or not isinstance(item["test_case_refs"], list)
                or any(
                    type(reference) is not str
                    for reference in (
                        *item["requirement_refs"],
                        *item["test_case_refs"],
                    )
                )
                or (
                    item.get("risk_justification") is not None
                    and type(item.get("risk_justification")) is not str
                )
            ):
                raise DeliveryStateError("artifact manifest metadata is invalid")
            try:
                _digest(item["sha256"], "artifact sha256")
                record = publisher.register_file(
                    item["path"],
                    artifact_id=item["artifact_id"],
                    category=item["category"],
                    role=item["role"],
                    producer=item["producer"],
                    required=item["required"],
                    validation_status=item["validation_status"],
                    requirement_refs=tuple(item["requirement_refs"]),
                    test_case_refs=tuple(item["test_case_refs"]),
                    risk_justification=item.get("risk_justification"),
                )
            except (
                ArtifactValidationError,
                DeliveryContractError,
                PublicationError,
                TypeError,
                ValueError,
            ) as exc:
                raise DeliveryStateError(
                    "artifact manifest registration is invalid"
                ) from exc
            if record.as_dict() != item:
                raise DeliveryStateError("staged artifact differs from its manifest")
            total_size += record.size_bytes
        try:
            publisher.validate()
        except (ArtifactValidationError, PublicationError) as exc:
            raise DeliveryStateError("staged artifact inventory is invalid") from exc
        if manifest["total_size_bytes"] != total_size:
            raise DeliveryStateError("artifact manifest byte total is invalid")
        return publisher, manifest

    def _verify_staged_session(
        self, *, tenant_id: str, project_id: str, session_id: str
    ) -> sqlite3.Row:
        row = self._session_row(
            tenant_id=tenant_id, project_id=project_id, session_id=session_id
        )
        self._publisher_from_row(row)
        return row

    @staticmethod
    def _published_document(output: PublishedOutput) -> dict[str, Any]:
        return {
            "schema_version": "elmos.autonomous-qa.published-output.v1",
            "tenant_id": output.tenant_id,
            "project_id": output.project_id,
            "revision_id": output.revision_id,
            "run_id": output.run_id,
            "output_id": output.output_id,
            "status": output.status,
            "manifest_digest": output.manifest_digest,
            "bundle_digests": dict(sorted(output.bundle_digests.items())),
            "durability_status": output.durability_status,
            "failure": None if output.failure is None else dict(output.failure),
        }

    def _published_from_row(
        self, row: sqlite3.Row, plan: OutputPlan | None = None
    ) -> PublishedOutput:
        if row["published_output_json"] is None:
            raise DeliveryStateError("delivery session has no published output")
        document = self._document(
            row["published_output_json"],
            row["published_output_digest"],
            "published output",
        )
        if set(document) != {
            "schema_version",
            "tenant_id",
            "project_id",
            "revision_id",
            "run_id",
            "output_id",
            "status",
            "manifest_digest",
            "bundle_digests",
            "durability_status",
            "failure",
        } or document["schema_version"] != "elmos.autonomous-qa.published-output.v1":
            raise DeliveryStateError("published output fields are not exact")
        plan = self._plan_from_row(row) if plan is None else plan
        plan_identity = {
            "tenant_id": plan.tenant_id,
            "project_id": plan.project_id,
            "revision_id": plan.revision_id,
            "run_id": plan.run_id,
            "output_id": plan.output_id,
        }
        if any(document[field] != value for field, value in plan_identity.items()):
            raise DeliveryStateError("published output identity mismatch")
        bundle_digests = document["bundle_digests"]
        if (
            document["status"] not in {"verified", "partial", "failed"}
            or document["durability_status"]
            not in {"DURABLE", "COMMITTED_DURABILITY_UNKNOWN"}
            or not isinstance(bundle_digests, dict)
            or any(type(kind) is not str for kind in bundle_digests)
        ):
            raise DeliveryStateError("published bundle envelope is invalid")
        failure = document["failure"]
        if failure is not None and (
            not isinstance(failure, dict)
            or set(failure) != {"type", "message"}
            or any(type(value) is not str for value in failure.values())
        ):
            raise DeliveryStateError("published failure envelope is invalid")
        if (document["status"] == "verified") != (failure is None):
            raise DeliveryStateError("published status and failure disagree")
        normalized_bundles: dict[str, str] = {}
        try:
            for kind, digest in bundle_digests.items():
                if kind not in artifact_module._BUNDLE_CATEGORIES:
                    raise DeliveryStateError("published bundle kind is invalid")
                normalized_bundles[kind] = _digest(digest, "bundle digest")
        except DeliveryContractError as exc:
            raise DeliveryStateError("published bundle digest is invalid") from exc
        return PublishedOutput(
            tenant_id=plan.tenant_id,
            project_id=plan.project_id,
            revision_id=plan.revision_id,
            run_id=plan.run_id,
            output_id=plan.output_id,
            status=document["status"],
            root=plan.final_root,
            manifest_digest=self._state_digest(
                document["manifest_digest"], "manifest_digest"
            ),
            bundle_digests=normalized_bundles,
            durability_status=document["durability_status"],
            failure=failure,
        )

    @staticmethod
    def _state_digest(value: object, field: str) -> str:
        try:
            return _digest(value, field)
        except DeliveryContractError as exc:
            raise DeliveryStateError(f"persisted {field} is invalid") from exc

    def _publication_result(self, output: PublishedOutput) -> Mapping[str, Any]:
        durable = output.durability_status == "DURABLE"
        verified = output.status == "verified" and durable
        return {
            "state": "SUCCEEDED" if verified else "PARTIAL",
            "code": (
                "OUTPUT_PUBLISHED"
                if verified
                else "PUBLICATION_DURABILITY_UNKNOWN"
                if not durable
                else "OUTPUT_PARTIALLY_PUBLISHED"
            ),
            "outputs": {
                "output_id": output.output_id,
                "status": output.status,
                "manifest_digest": output.manifest_digest,
                "bundle_digests": dict(sorted(output.bundle_digests.items())),
                "durability_status": output.durability_status,
                "failure": None if output.failure is None else dict(output.failure),
                "atomic_publish": True,
                "lifecycle_registered": False,
                **_external_boundaries(),
            },
            "implementation_state": "LOCAL_EXECUTED",
        }

    def _blocked_result(self, code: str, **outputs: Any) -> Mapping[str, Any]:
        return {
            "state": "BLOCKED",
            "code": code,
            "outputs": {**outputs, **_external_boundaries()},
            "implementation_state": "LOCAL_VALIDATED",
        }

    def _record_standalone_receipt(
        self,
        *,
        tenant_id: str,
        project_id: str,
        operation: str,
        idempotency_key: str,
        input_digest: str,
        result: Mapping[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._store_receipt(
                connection,
                tenant_id=tenant_id,
                project_id=project_id,
                operation=operation,
                idempotency_key=idempotency_key,
                input_digest=input_digest,
                result=result,
            )

    def publish(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        exact = _exact_object(
            request,
            label="publish request",
            allowed=frozenset(
                {"tenant_id", "project_id", "session_id", "idempotency_key"}
            ),
            required=frozenset(
                {"tenant_id", "project_id", "session_id", "idempotency_key"}
            ),
        )
        tenant_id, project_id = self._authorize_scope(
            exact["tenant_id"], exact["project_id"]
        )
        self._assert_database()
        session_id = _resource_id(exact["session_id"], "session_id")
        idempotency_key = _resource_id(
            exact["idempotency_key"], "idempotency_key"
        )
        input_digest = canonical_digest({"session_id": session_id})
        replay = self._receipt(
            tenant_id=tenant_id,
            project_id=project_id,
            operation="publish",
            idempotency_key=idempotency_key,
            input_digest=input_digest,
        )
        if replay is not None:
            return replay
        row = self._session_row(
            tenant_id=tenant_id, project_id=project_id, session_id=session_id
        )
        if row["stage_durability_status"] != "DURABLE":
            result = self._blocked_result(
                "STAGE_DURABILITY_NOT_ESTABLISHED",
                session_id=session_id,
                durability_status=row["stage_durability_status"],
            )
            self._record_standalone_receipt(
                tenant_id=tenant_id,
                project_id=project_id,
                operation="publish",
                idempotency_key=idempotency_key,
                input_digest=input_digest,
                result=result,
            )
            return result
        if row["published_output_json"] is not None:
            output = self._published_from_row(row)
            result = self._publication_result(output)
            self._record_standalone_receipt(
                tenant_id=tenant_id,
                project_id=project_id,
                operation="publish",
                idempotency_key=idempotency_key,
                input_digest=input_digest,
                result=result,
            )
            return result
        if row["status"] == "PUBLISHING":
            result = self._blocked_result(
                "PUBLICATION_OUTCOME_UNKNOWN",
                session_id=session_id,
                durability_status="UNKNOWN",
                lifecycle_registered=False,
            )
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    "UPDATE delivery_sessions SET status = 'DURABILITY_UNKNOWN', "
                    "version = version + 1, updated_at = ? WHERE tenant_id = ? "
                    "AND project_id = ? AND session_id = ? AND status = 'PUBLISHING' "
                    "AND version = ?",
                    (_now(), tenant_id, project_id, session_id, row["version"]),
                )
                if updated.rowcount != 1:
                    raise DeliveryStateError("publication CAS was lost")
                self._store_receipt(
                    connection,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    operation="publish",
                    idempotency_key=idempotency_key,
                    input_digest=input_digest,
                    result=result,
                )
            return result
        if row["status"] != "STAGED":
            result = self._blocked_result(
                "DELIVERY_SESSION_NOT_PUBLISHABLE",
                session_id=session_id,
                session_status=row["status"],
            )
            self._record_standalone_receipt(
                tenant_id=tenant_id,
                project_id=project_id,
                operation="publish",
                idempotency_key=idempotency_key,
                input_digest=input_digest,
                result=result,
            )
            return result
        try:
            publisher, _ = self._publisher_from_row(row)
            preflight_digests = {
                kind: publisher.build_bundle(kind)[1]
                for kind in publisher._required_bundle_kinds()
            }
        except (
            ArtifactValidationError,
            DeliveryError,
            PublicationError,
            TypeError,
            ValueError,
        ) as exc:
            result = self._blocked_result(
                "STAGED_ARTIFACT_VERIFICATION_FAILED",
                session_id=session_id,
                error_type=type(exc).__name__,
            )
            self._record_standalone_receipt(
                tenant_id=tenant_id,
                project_id=project_id,
                operation="publish",
                idempotency_key=idempotency_key,
                input_digest=input_digest,
                result=result,
            )
            return result
        with self._connect() as connection:
            existing_claim = connection.execute(
                "SELECT session_id FROM delivery_sessions WHERE tenant_id = ? "
                "AND project_id = ? AND output_id = ? AND session_id <> ? "
                "AND status IN ('PUBLISHING', 'PUBLISHED', 'PARTIAL', "
                "'DURABILITY_UNKNOWN') LIMIT 1",
                (
                    tenant_id,
                    project_id,
                    publisher.plan.output_id,
                    session_id,
                ),
            ).fetchone()
        if (
            existing_claim is not None
            or publisher.plan.final_root.exists()
            or publisher.plan.final_root.is_symlink()
        ):
            result = self._blocked_result(
                "IMMUTABLE_OUTPUT_ALREADY_EXISTS",
                session_id=session_id,
                output_id=publisher.plan.output_id,
                output_identity_reserved=existing_claim is not None,
                overwrite_performed=False,
            )
            self._record_standalone_receipt(
                tenant_id=tenant_id,
                project_id=project_id,
                operation="publish",
                idempotency_key=idempotency_key,
                input_digest=input_digest,
                result=result,
            )
            return result
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    "UPDATE delivery_sessions SET status = 'PUBLISHING', "
                    "version = version + 1, updated_at = ? WHERE tenant_id = ? "
                    "AND project_id = ? AND session_id = ? AND status = 'STAGED' "
                    "AND version = ?",
                    (_now(), tenant_id, project_id, session_id, row["version"]),
                )
                if updated.rowcount != 1:
                    raise DeliveryStateError("publication CAS was lost")
        except sqlite3.IntegrityError:
            result = self._blocked_result(
                "IMMUTABLE_OUTPUT_ALREADY_EXISTS",
                session_id=session_id,
                output_id=publisher.plan.output_id,
                output_identity_reserved=True,
                overwrite_performed=False,
            )
            self._record_standalone_receipt(
                tenant_id=tenant_id,
                project_id=project_id,
                operation="publish",
                idempotency_key=idempotency_key,
                input_digest=input_digest,
                result=result,
            )
            return result
        expected_version = int(row["version"]) + 1
        output: PublishedOutput | None = None
        try:
            output = publisher.publish(requested_status="verified", partial_on_failure=True)
            if output.status == "verified" and dict(output.bundle_digests) != preflight_digests:
                raise DeliveryStateError("published bundle digests differ from preflight")
            output_document = self._published_document(output)
            output_bytes = canonical_json_bytes(output_document)
            new_status = (
                "DURABILITY_UNKNOWN"
                if output.durability_status != "DURABLE"
                else "PUBLISHED"
                if output.status == "verified"
                else "PARTIAL"
            )
            result = self._publication_result(output)
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    "UPDATE delivery_sessions SET status = ?, published_output_json = ?, "
                    "published_output_digest = ?, version = version + 1, updated_at = ? "
                    "WHERE tenant_id = ? AND project_id = ? AND session_id = ? "
                    "AND status = 'PUBLISHING' AND version = ?",
                    (
                        new_status,
                        sqlite3.Binary(output_bytes),
                        sha256_bytes(output_bytes),
                        _now(),
                        tenant_id,
                        project_id,
                        session_id,
                        expected_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise DeliveryStateError("published-output CAS was lost")
                self._store_receipt(
                    connection,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    operation="publish",
                    idempotency_key=idempotency_key,
                    input_digest=input_digest,
                    result=result,
                )
            return result
        except Exception as exc:
            committed_or_unknown = output is not None
            if not committed_or_unknown:
                try:
                    committed_or_unknown = (
                        publisher.plan.final_root.exists()
                        or publisher.plan.final_root.is_symlink()
                    )
                except OSError:
                    committed_or_unknown = True
            terminal_status = (
                "DURABILITY_UNKNOWN" if committed_or_unknown else "FAILED"
            )
            result = {
                "state": "BLOCKED" if committed_or_unknown else "FAILED",
                "code": (
                    "PUBLICATION_OUTCOME_UNKNOWN"
                    if committed_or_unknown
                    else "LOCAL_PUBLICATION_FAILED"
                ),
                "outputs": {
                    "session_id": session_id,
                    "error_type": type(exc).__name__,
                    "outcome": "UNKNOWN" if committed_or_unknown else "NOT_COMMITTED",
                    "durability_status": (
                        "UNKNOWN" if committed_or_unknown else "NOT_COMMITTED"
                    ),
                    "lifecycle_registered": False,
                    **_external_boundaries(),
                },
                "implementation_state": "LOCAL_VALIDATED",
            }
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    "UPDATE delivery_sessions SET status = ?, "
                    "version = version + 1, updated_at = ? WHERE tenant_id = ? "
                    "AND project_id = ? AND session_id = ? AND status = 'PUBLISHING' "
                    "AND version = ?",
                    (
                        terminal_status,
                        _now(),
                        tenant_id,
                        project_id,
                        session_id,
                        expected_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise DeliveryStateError(
                        "publication failed and its CAS outcome is unknown"
                    ) from exc
                self._store_receipt(
                    connection,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    operation="publish",
                    idempotency_key=idempotency_key,
                    input_digest=input_digest,
                    result=result,
                )
            return result

    def _published_session_for_output(
        self,
        *,
        tenant_id: str,
        project_id: str,
        output_id: str,
        require_registered: bool,
    ) -> sqlite3.Row:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM delivery_sessions WHERE tenant_id = ? AND project_id = ? "
                "AND output_id = ? AND published_output_json IS NOT NULL LIMIT 2",
                (tenant_id, project_id, output_id),
            ).fetchall()
        if len(rows) != 1:
            raise DeliveryAuthorizationError(
                "published output is unavailable in the authorized scope"
            )
        row = rows[0]
        output = self._published_from_row(row)
        if output.durability_status != "DURABLE":
            raise DeliveryStateError("published output durability is not established")
        if require_registered and row["lifecycle_registered"] != 1:
            raise DeliveryStateError("published output is not lifecycle registered")
        return row

    def _lifecycle_project(self, tenant_id: str, output_id: str) -> str | None:
        with self.lifecycle_store._connect() as connection:
            rows = connection.execute(
                "SELECT project_id FROM lifecycle_outputs WHERE tenant_id = ? "
                "AND output_id = ? LIMIT 2",
                (tenant_id, output_id),
            ).fetchall()
        if len(rows) != 1:
            return None
        return str(rows[0]["project_id"])

    def _reconcile_lifecycle_registration(self, output: PublishedOutput) -> bool:
        """Verify an exact Store write left by a crash before session CAS."""

        with self.lifecycle_store._connect() as connection:
            rows = connection.execute(
                "SELECT tenant_id, output_id, project_id, revision_id, run_id, "
                "output_path, manifest_digest, fs_device, fs_inode, state "
                "FROM lifecycle_outputs WHERE tenant_id = ? AND output_id = ? LIMIT 2",
                (output.tenant_id, output.output_id),
            ).fetchall()
        if not rows:
            return False
        if len(rows) != 1:
            raise DeliveryStateError("lifecycle registration is ambiguous")
        row = rows[0]
        expected = {
            "tenant_id": output.tenant_id,
            "output_id": output.output_id,
            "project_id": output.project_id,
            "revision_id": output.revision_id,
            "run_id": output.run_id,
            "output_path": str(output.root),
            "manifest_digest": output.manifest_digest,
            "state": "active",
        }
        if any(row[field] != value for field, value in expected.items()):
            raise DeliveryStateError("lifecycle registration identity mismatch")
        try:
            if type(row["fs_device"]) is not int or type(row["fs_inode"]) is not int:
                raise TypeError
            fs_device = row["fs_device"]
            fs_inode = row["fs_inode"]
            if fs_device < 0 or fs_inode <= 0:
                raise ValueError
            self.lifecycle_store._verify_output_identity(
                output.root,
                tenant_id=output.tenant_id,
                output_id=output.output_id,
                project_id=output.project_id,
                revision_id=output.revision_id,
                run_id=output.run_id,
                manifest_digest=output.manifest_digest,
                fs_device=fs_device,
                fs_inode=fs_inode,
                normal_path=True,
                status=output.status,
                bundle_digests=output.bundle_digests,
                published_failure=output.failure,
                verify_envelope=True,
            )
        except (LifecycleError, TypeError, ValueError) as exc:
            raise DeliveryStateError(
                "lifecycle registration cannot be reconciled"
            ) from exc
        return True

    def lifecycle(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(request, Mapping) or any(
            type(key) is not str for key in request
        ):
            raise DeliveryContractError("lifecycle request must be an exact object")
        tenant_id, project_id = self._authorize_scope(
            request.get("tenant_id"), request.get("project_id")
        )
        action = request.get("action")
        if not isinstance(action, str) or action not in _LIFECYCLE_ACTIONS:
            raise DeliveryContractError("lifecycle action is unsupported")
        allowed_by_action = {
            "register": {"session_id"},
            "mark_stale": {"output_id"},
            "supersede": {"old_output_id", "new_output_id"},
            "legal_hold": {"output_id", "enabled"},
            "reference": {"output_id", "reference_id", "present"},
            "candidates": set(),
            "recover": set(),
            "collect": {"dry_run"},
        }
        fields = {"tenant_id", "project_id", "action", "idempotency_key"}
        action_fields = allowed_by_action[action]
        exact = _exact_object(
            request,
            label="lifecycle request",
            allowed=frozenset(fields | action_fields),
            required=frozenset(fields | action_fields),
        )
        self._assert_database()
        idempotency_key = _resource_id(
            exact["idempotency_key"], "idempotency_key"
        )
        normalized_request = dict(exact)
        for field in ("session_id", "output_id", "old_output_id", "new_output_id", "reference_id"):
            if field in normalized_request:
                normalized_request[field] = _resource_id(
                    normalized_request[field], field
                )
        for field in ("enabled", "present", "dry_run"):
            if field in normalized_request and not isinstance(
                normalized_request[field], bool
            ):
                raise DeliveryContractError(f"{field} must be boolean")
        input_digest = canonical_digest(normalized_request)
        operation = f"lifecycle:{action}"
        replay = self._receipt(
            tenant_id=tenant_id,
            project_id=project_id,
            operation=operation,
            idempotency_key=idempotency_key,
            input_digest=input_digest,
        )
        if replay is not None:
            return replay
        try:
            result = self._run_lifecycle_action(
                tenant_id=tenant_id,
                project_id=project_id,
                action=action,
                request=normalized_request,
            )
        except LifecycleError as exc:
            result = self._blocked_result(
                "LIFECYCLE_OPERATION_BLOCKED",
                action=action,
                error_type=type(exc).__name__,
                mutation_outcome="UNKNOWN",
            )
        self._record_standalone_receipt(
            tenant_id=tenant_id,
            project_id=project_id,
            operation=operation,
            idempotency_key=idempotency_key,
            input_digest=input_digest,
            result=result,
        )
        return result

    def _run_lifecycle_action(
        self,
        *,
        tenant_id: str,
        project_id: str,
        action: str,
        request: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if action == "register":
            session_id = str(request["session_id"])
            row = self._session_row(
                tenant_id=tenant_id,
                project_id=project_id,
                session_id=session_id,
            )
            if row["published_output_json"] is None:
                return self._blocked_result(
                    "PUBLISHED_OUTPUT_REQUIRED", session_id=session_id
                )
            output = self._published_from_row(row)
            if output.durability_status != "DURABLE":
                return self._blocked_result(
                    "PUBLISHED_OUTPUT_DURABILITY_UNKNOWN",
                    session_id=session_id,
                    output_id=output.output_id,
                    lifecycle_registered=False,
                )
            if row["lifecycle_registered"] != 1:
                if not self._reconcile_lifecycle_registration(output):
                    try:
                        self.lifecycle_store.register_output(output)
                    except (LifecycleError, sqlite3.IntegrityError):
                        if not self._reconcile_lifecycle_registration(output):
                            raise
                with self._connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    updated = connection.execute(
                        "UPDATE delivery_sessions SET lifecycle_registered = 1, "
                        "version = version + 1, updated_at = ? WHERE tenant_id = ? "
                        "AND project_id = ? AND session_id = ? "
                        "AND lifecycle_registered = 0 AND version = ?",
                        (
                            _now(),
                            tenant_id,
                            project_id,
                            session_id,
                            row["version"],
                        ),
                    )
                    if updated.rowcount != 1:
                        raise DeliveryStateError("lifecycle registration CAS was lost")
            details: dict[str, Any] = {
                "output_id": output.output_id,
                "lifecycle_registered": True,
            }
        elif action == "mark_stale":
            output_id = str(request["output_id"])
            self._published_session_for_output(
                tenant_id=tenant_id,
                project_id=project_id,
                output_id=output_id,
                require_registered=True,
            )
            self.lifecycle_store.mark_stale(
                tenant_id=tenant_id, output_id=output_id
            )
            details = {"output_id": output_id, "lifecycle_state": "stale"}
        elif action == "supersede":
            old_output_id = str(request["old_output_id"])
            new_output_id = str(request["new_output_id"])
            for output_id in (old_output_id, new_output_id):
                self._published_session_for_output(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    output_id=output_id,
                    require_registered=True,
                )
            self.lifecycle_store.supersede(
                tenant_id=tenant_id,
                old_output_id=old_output_id,
                new_output_id=new_output_id,
            )
            details = {
                "old_output_id": old_output_id,
                "new_output_id": new_output_id,
                "lifecycle_state": "superseded",
            }
        elif action == "legal_hold":
            output_id = str(request["output_id"])
            self._published_session_for_output(
                tenant_id=tenant_id,
                project_id=project_id,
                output_id=output_id,
                require_registered=True,
            )
            enabled = bool(request["enabled"])
            self.lifecycle_store.set_legal_hold(
                tenant_id=tenant_id, output_id=output_id, enabled=enabled
            )
            details = {"output_id": output_id, "legal_hold": enabled}
        elif action == "reference":
            output_id = str(request["output_id"])
            self._published_session_for_output(
                tenant_id=tenant_id,
                project_id=project_id,
                output_id=output_id,
                require_registered=True,
            )
            reference_id = str(request["reference_id"])
            present = bool(request["present"])
            if present:
                self.lifecycle_store.add_reference(
                    tenant_id=tenant_id,
                    output_id=output_id,
                    reference_id=reference_id,
                )
            else:
                self.lifecycle_store.remove_reference(
                    tenant_id=tenant_id,
                    output_id=output_id,
                    reference_id=reference_id,
                )
            details = {
                "output_id": output_id,
                "reference_id": reference_id,
                "reference_present": present,
            }
        elif action == "candidates":
            candidates = self.lifecycle_store.gc_candidates(tenant_id=tenant_id)
            selected = [
                output_id
                for output_id in candidates
                if self._lifecycle_project(tenant_id, output_id) == project_id
            ]
            details = {"gc_candidates": selected, "deletion_performed": False}
        elif action == "recover":
            fence = self.lifecycle_store._acquire_gc_fence()
            if fence is None:
                return self._blocked_result("LIFECYCLE_FENCE_UNAVAILABLE")
            try:
                with self.lifecycle_store._connect() as connection:
                    foreign = connection.execute(
                        "SELECT 1 FROM lifecycle_outputs WHERE tenant_id = ? "
                        "AND state = 'collecting' AND project_id <> ? LIMIT 1",
                        (tenant_id, project_id),
                    ).fetchone()
                if foreign is not None:
                    return self._blocked_result(
                        "PROJECT_SCOPED_RECOVERY_BLOCKED"
                    )
                recovered = self.lifecycle_store._recover_collecting_locked(
                    tenant_id=tenant_id, fence=fence
                )
            finally:
                self.lifecycle_store._release_gc_fence(fence)
            details = {"recovered_output_ids": list(recovered)}
        else:
            dry_run = bool(request["dry_run"])
            fence = self.lifecycle_store._acquire_gc_fence()
            if fence is None:
                return self._blocked_result("LIFECYCLE_FENCE_UNAVAILABLE")
            try:
                candidates = self.lifecycle_store.gc_candidates(tenant_id=tenant_id)
                selected = tuple(
                    output_id
                    for output_id in candidates
                    if self._lifecycle_project(tenant_id, output_id) == project_id
                )
                collected = (
                    selected
                    if dry_run
                    else self.lifecycle_store._collect_garbage_locked(
                        tenant_id=tenant_id,
                        candidates=selected,
                        fence=fence,
                    )
                )
            finally:
                self.lifecycle_store._release_gc_fence(fence)
            details = {
                "gc_candidates": list(selected),
                "collected_output_ids": [] if dry_run else list(collected),
                "deletion_performed": not dry_run and bool(collected),
                "dry_run": dry_run,
            }
        return {
            "state": "SUCCEEDED",
            "code": "LIFECYCLE_OPERATION_COMPLETED",
            "outputs": {"action": action, **details, **_external_boundaries()},
            "implementation_state": "LOCAL_EXECUTED",
        }


__all__ = [
    "DeliveryAuthorizationError",
    "DeliveryContractError",
    "DeliveryError",
    "DeliveryStateError",
    "TrustedDeliveryService",
    "lifecycle_operation_contract",
    "publishing_operation_contract",
]
