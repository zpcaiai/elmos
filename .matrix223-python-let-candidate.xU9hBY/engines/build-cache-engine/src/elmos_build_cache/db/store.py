"""Metadata store: transactional, tenant-scoped, optimistic-versioned.

Every mutation that can race carries either an expected ``version`` or a lease
epoch, and every guarded transition is expressed as a single conditional
``UPDATE`` so two workers cannot both believe they won. A stale worker whose
lease epoch was bumped by recovery therefore cannot commit, which is the
property that makes crash recovery safe.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..canonical import canonical_json_text, digest_of, require_digest
from ..clock import SYSTEM_CLOCK, Clock, iso
from ..enums import (
    NODE_TRANSITIONS,
    RUN_TRANSITIONS,
    STAGED_FILE_TRANSITIONS,
    ArtifactStorageState,
    CacheEntryStatus,
    CheckpointStatus,
    FileClass,
    NodeStatus,
    Ownership,
    RunStatus,
    SecretScanStatus,
    StagedFileStatus,
    TrustNamespace,
    ValidationLevel,
)
from ..errors import (
    ConflictError,
    IdempotencyConflict,
    InvalidTransition,
    NotFound,
    StaleLease,
    VersionConflict,
)
from .records import (
    ActionCacheRecord,
    ArtifactRecord,
    CheckpointRecord,
    NodeRecord,
    RunRecord,
    StagedFileRecord,
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "_data" / "migrations"

SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
)


def _json(value: Any) -> str:
    return canonical_json_text(value)


def _unjson(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, dict | list):
        return value
    return json.loads(value)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class MetadataStore:
    """Base store. :class:`SqliteMetadataStore` is the local profile."""

    paramstyle = "?"

    def __init__(self, connection: Any, clock: Clock = SYSTEM_CLOCK) -> None:
        self._connection = connection
        self._clock = clock
        self._lock = threading.RLock()

    # -- plumbing ---------------------------------------------------------
    def _sql(self, statement: str) -> str:
        if self.paramstyle == "?":
            return statement
        return statement.replace("?", "%s")

    def execute(self, statement: str, params: Sequence[Any] = ()) -> Any:
        return self._connection.execute(self._sql(statement), tuple(params))

    def query(self, statement: str, params: Sequence[Any] = ()) -> list[Any]:
        return list(self.execute(statement, params).fetchall())

    def query_one(self, statement: str, params: Sequence[Any] = ()) -> Any | None:
        rows = self.query(statement, params)
        return rows[0] if rows else None

    @contextmanager
    def transaction(self) -> Iterator[MetadataStore]:
        with self._lock:
            try:
                yield self
            except BaseException:
                self._connection.rollback()
                raise
            self._connection.commit()

    def commit(self) -> None:
        """Force-durable commit.

        Used by the few operations that must survive the failure they are
        reporting -- notably nondeterminism quarantine, where the caller raises
        and the enclosing transaction would otherwise roll the quarantine back.
        """
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def now(self) -> float:
        return self._clock.now()

    # -- tenancy ----------------------------------------------------------
    def ensure_tenant(self, tenant_id: str) -> None:
        self.execute(
            "INSERT INTO tenants (tenant_id, created_at) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (tenant_id, iso(self.now())),
        )

    def ensure_project(self, tenant_id: str, project_id: str, name: str | None = None) -> None:
        self.ensure_tenant(tenant_id)
        self.execute(
            "INSERT INTO projects (project_id, tenant_id, name, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            (project_id, tenant_id, name or project_id, iso(self.now())),
        )

    def record_snapshot(
        self,
        tenant_id: str,
        project_id: str,
        root_digest: str,
        manifest_digest: str,
        policy_version: str,
    ) -> str:
        self.ensure_project(tenant_id, project_id)
        row = self.query_one(
            "SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND project_id=? "
            "AND root_digest=? AND policy_version=?",
            (tenant_id, project_id, root_digest, policy_version),
        )
        if row is not None:
            return str(row[0])
        snapshot_id = new_id("snap")
        self.execute(
            "INSERT INTO snapshots (snapshot_id, tenant_id, project_id, root_digest, manifest_digest,"
            " policy_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                tenant_id,
                project_id,
                require_digest(root_digest),
                require_digest(manifest_digest),
                policy_version,
                iso(self.now()),
            ),
        )
        return snapshot_id

    # -- runs -------------------------------------------------------------
    def create_run(
        self,
        run_id: str,
        tenant_id: str,
        project_id: str,
        snapshot_id: str,
        pipeline_version: str,
        source_profile: dict[str, Any] | None = None,
        target_profile: dict[str, Any] | None = None,
        trust_namespace: TrustNamespace = TrustNamespace.BRANCH,
    ) -> RunRecord:
        stamp = iso(self.now())
        self.execute(
            "INSERT INTO runs (run_id, tenant_id, project_id, snapshot_id, pipeline_version,"
            " source_profile, target_profile, trust_namespace, status, version, journal_sequence,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
            (
                run_id,
                tenant_id,
                project_id,
                snapshot_id,
                pipeline_version,
                _json(source_profile or {}),
                _json(target_profile or {}),
                str(trust_namespace),
                str(RunStatus.PENDING),
                stamp,
                stamp,
            ),
        )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunRecord:
        row = self.query_one(
            "SELECT run_id, tenant_id, project_id, snapshot_id, pipeline_version, status, version,"
            " journal_sequence, trust_namespace, source_profile, target_profile,"
            " published_tree_digest, evidence_bundle_digest FROM runs WHERE run_id=?",
            (run_id,),
        )
        if row is None:
            raise NotFound(f"run {run_id} does not exist", run_id=run_id)
        return RunRecord(
            run_id=row[0],
            tenant_id=row[1],
            project_id=row[2],
            snapshot_id=row[3],
            pipeline_version=row[4],
            status=RunStatus(row[5]),
            version=int(row[6]),
            journal_sequence=int(row[7]),
            trust_namespace=TrustNamespace(row[8]),
            source_profile=_unjson(row[9]) or {},
            target_profile=_unjson(row[10]) or {},
            published_tree_digest=row[11],
            evidence_bundle_digest=row[12],
        )

    def transition_run(self, run_id: str, target: RunStatus, expected_version: int) -> RunRecord:
        current = self.get_run(run_id)
        if current.version != expected_version:
            raise VersionConflict(
                "run version conflict", run_id=run_id, expected=expected_version, actual=current.version
            )
        if target is not current.status and target not in RUN_TRANSITIONS[current.status]:
            raise InvalidTransition(
                f"run {current.status} -> {target} is not a legal transition",
                run_id=run_id,
                current=str(current.status),
                target=str(target),
            )
        cursor = self.execute(
            "UPDATE runs SET status=?, version=version+1, updated_at=? WHERE run_id=? AND version=?",
            (str(target), iso(self.now()), run_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise VersionConflict("run version conflict", run_id=run_id)
        return self.get_run(run_id)

    def set_run_published_tree(self, run_id: str, tree_digest: str, evidence_digest: str | None) -> None:
        self.execute(
            "UPDATE runs SET published_tree_digest=?, evidence_bundle_digest=?, version=version+1,"
            " updated_at=? WHERE run_id=?",
            (require_digest(tree_digest), evidence_digest, iso(self.now()), run_id),
        )

    def list_runs(self, tenant_id: str, statuses: Sequence[RunStatus] | None = None) -> list[RunRecord]:
        rows = self.query("SELECT run_id FROM runs WHERE tenant_id=? ORDER BY created_at", (tenant_id,))
        runs = [self.get_run(row[0]) for row in rows]
        if statuses is None:
            return runs
        wanted = set(statuses)
        return [run for run in runs if run.status in wanted]

    # -- nodes ------------------------------------------------------------
    def upsert_node(
        self,
        run_id: str,
        node_id: str,
        stage_id: str,
        stage_version: str,
        attempt: int = 1,
        status: NodeStatus = NodeStatus.PENDING,
        action_key: str | None = None,
        retry_budget: int = 3,
    ) -> NodeRecord:
        existing = self.try_get_node(run_id, node_id, attempt)
        if existing is not None:
            return existing
        self.execute(
            "INSERT INTO run_nodes (run_id, node_id, attempt, stage_id, stage_version, action_key,"
            " status, lease_epoch, retries, retry_budget, version) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 0)",
            (run_id, node_id, attempt, stage_id, stage_version, action_key, str(status), retry_budget),
        )
        return self.get_node(run_id, node_id, attempt)

    def try_get_node(self, run_id: str, node_id: str, attempt: int) -> NodeRecord | None:
        row = self.query_one(
            "SELECT run_id, node_id, attempt, stage_id, stage_version, status, version, lease_id,"
            " lease_epoch, lease_expires_at, heartbeat_at, retries, retry_budget, action_key, outcome,"
            " error_code, error_details FROM run_nodes WHERE run_id=? AND node_id=? AND attempt=?",
            (run_id, node_id, attempt),
        )
        if row is None:
            return None
        return NodeRecord(
            run_id=row[0],
            node_id=row[1],
            attempt=int(row[2]),
            stage_id=row[3],
            stage_version=row[4],
            status=NodeStatus(row[5]),
            version=int(row[6]),
            lease_id=row[7],
            lease_epoch=int(row[8]),
            lease_expires_at=row[9],
            heartbeat_at=row[10],
            retries=int(row[11]),
            retry_budget=int(row[12]),
            action_key=row[13],
            outcome=row[14],
            error_code=row[15],
            error_details=_unjson(row[16]),
        )

    def get_node(self, run_id: str, node_id: str, attempt: int) -> NodeRecord:
        node = self.try_get_node(run_id, node_id, attempt)
        if node is None:
            raise NotFound("run node does not exist", run_id=run_id, node_id=node_id, attempt=attempt)
        return node

    def latest_attempt(self, run_id: str, node_id: str) -> int:
        row = self.query_one(
            "SELECT MAX(attempt) FROM run_nodes WHERE run_id=? AND node_id=?", (run_id, node_id)
        )
        return int(row[0]) if row and row[0] is not None else 0

    def list_nodes(self, run_id: str) -> list[NodeRecord]:
        rows = self.query(
            "SELECT node_id, attempt FROM run_nodes WHERE run_id=? ORDER BY node_id, attempt", (run_id,)
        )
        return [self.get_node(run_id, row[0], int(row[1])) for row in rows]

    def claim_node(
        self,
        run_id: str,
        node_id: str,
        attempt: int,
        lease_id: str,
        lease_seconds: float,
        expected_version: int,
        bump_epoch: bool = True,
    ) -> NodeRecord:
        """Take ownership. Bumping the epoch is what invalidates a stale worker."""
        node = self.get_node(run_id, node_id, attempt)
        if node.version != expected_version:
            raise VersionConflict("node version conflict", node_id=node_id, actual=node.version)
        now = self.now()
        cursor = self.execute(
            "UPDATE run_nodes SET lease_id=?, lease_epoch=lease_epoch+?, lease_expires_at=?,"
            " heartbeat_at=?, version=version+1 WHERE run_id=? AND node_id=? AND attempt=? AND version=?",
            (
                lease_id,
                1 if bump_epoch else 0,
                now + lease_seconds,
                now,
                run_id,
                node_id,
                attempt,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise VersionConflict("node version conflict", node_id=node_id)
        return self.get_node(run_id, node_id, attempt)

    def heartbeat_node(
        self, run_id: str, node_id: str, attempt: int, lease_id: str, lease_epoch: int, lease_seconds: float
    ) -> NodeRecord:
        now = self.now()
        cursor = self.execute(
            "UPDATE run_nodes SET heartbeat_at=?, lease_expires_at=? WHERE run_id=? AND node_id=?"
            " AND attempt=? AND lease_id=? AND lease_epoch=?",
            (now, now + lease_seconds, run_id, node_id, attempt, lease_id, lease_epoch),
        )
        if cursor.rowcount != 1:
            raise StaleLease("heartbeat rejected: lease is no longer current", node_id=node_id)
        return self.get_node(run_id, node_id, attempt)

    def assert_lease(self, run_id: str, node_id: str, attempt: int, lease_epoch: int) -> NodeRecord:
        node = self.get_node(run_id, node_id, attempt)
        if node.lease_epoch != lease_epoch:
            raise StaleLease(
                "lease epoch has moved; this worker no longer owns the node",
                node_id=node_id,
                held=lease_epoch,
                current=node.lease_epoch,
            )
        return node

    def transition_node(
        self,
        run_id: str,
        node_id: str,
        attempt: int,
        target: NodeStatus,
        expected_version: int,
        lease_epoch: int | None = None,
        error_code: str | None = None,
        error_details: dict[str, Any] | None = None,
        outcome: str | None = None,
    ) -> NodeRecord:
        node = self.get_node(run_id, node_id, attempt)
        if lease_epoch is not None and node.lease_epoch != lease_epoch:
            raise StaleLease("stale lease epoch", node_id=node_id, held=lease_epoch, current=node.lease_epoch)
        if node.version != expected_version:
            raise VersionConflict("node version conflict", node_id=node_id, actual=node.version)
        if target is not node.status and target not in NODE_TRANSITIONS[node.status]:
            raise InvalidTransition(
                f"node {node.status} -> {target} is not a legal transition",
                node_id=node_id,
                current=str(node.status),
                target=str(target),
            )
        stamp = iso(self.now())
        cursor = self.execute(
            "UPDATE run_nodes SET status=?, version=version+1, error_code=?, error_details=?, outcome=?,"
            " started_at=COALESCE(started_at, ?), finished_at=? WHERE run_id=? AND node_id=? AND attempt=?"
            " AND version=?",
            (
                str(target),
                error_code,
                _json(error_details) if error_details else None,
                outcome,
                stamp if target is NodeStatus.RUNNING else None,
                stamp if target in (NodeStatus.SUCCEEDED, NodeStatus.FAILED_FINAL, NodeStatus.CANCELED) else None,
                run_id,
                node_id,
                attempt,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise VersionConflict("node version conflict", node_id=node_id)
        return self.get_node(run_id, node_id, attempt)

    def expired_nodes(self, now: float | None = None) -> list[NodeRecord]:
        moment = self.now() if now is None else now
        rows = self.query(
            "SELECT run_id, node_id, attempt FROM run_nodes WHERE status IN (?, ?, ?)"
            " AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
            (str(NodeStatus.RUNNING), str(NodeStatus.CHECKPOINTED), str(NodeStatus.RECOVERING), moment),
        )
        return [self.get_node(row[0], row[1], int(row[2])) for row in rows]

    # -- artifacts --------------------------------------------------------
    def register_artifact(
        self,
        tenant_id: str,
        digest: str,
        size_bytes: int,
        media_type: str,
        artifact_kind: str,
        storage_state: ArtifactStorageState = ArtifactStorageState.LOCAL,
        validation_level: ValidationLevel = ValidationLevel.UNVERIFIED,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        require_digest(digest)
        self.ensure_tenant(tenant_id)
        existing = self.get_artifact(tenant_id, digest)
        stamp = iso(self.now())
        if existing is None:
            self.execute(
                "INSERT INTO artifacts (tenant_id, digest, size_bytes, media_type, artifact_kind,"
                " storage_state, validation_level, metadata, created_at, last_accessed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    digest,
                    size_bytes,
                    media_type,
                    artifact_kind,
                    str(storage_state),
                    str(validation_level),
                    _json(metadata or {}),
                    stamp,
                    stamp,
                ),
            )
        elif validation_level.satisfies(existing.validation_level) and validation_level != existing.validation_level:
            # Validation may only ratchet upward, and never out of quarantine.
            if existing.validation_level is not ValidationLevel.QUARANTINED:
                self.execute(
                    "UPDATE artifacts SET validation_level=?, last_accessed_at=? WHERE tenant_id=? AND digest=?",
                    (str(validation_level), stamp, tenant_id, digest),
                )
        result = self.get_artifact(tenant_id, digest)
        assert result is not None
        return result

    def get_artifact(self, tenant_id: str, digest: str) -> ArtifactRecord | None:
        row = self.query_one(
            "SELECT tenant_id, digest, size_bytes, media_type, artifact_kind, storage_state,"
            " validation_level, metadata FROM artifacts WHERE tenant_id=? AND digest=?",
            (tenant_id, digest),
        )
        if row is None:
            return None
        return ArtifactRecord(
            tenant_id=row[0],
            digest=row[1],
            size_bytes=int(row[2]),
            media_type=row[3],
            artifact_kind=row[4],
            storage_state=ArtifactStorageState(row[5]),
            validation_level=ValidationLevel(row[6]),
            metadata=_unjson(row[7]) or {},
        )

    def set_artifact_state(self, tenant_id: str, digest: str, state: ArtifactStorageState) -> None:
        self.execute(
            "UPDATE artifacts SET storage_state=? WHERE tenant_id=? AND digest=?",
            (str(state), tenant_id, digest),
        )

    def touch_artifact(self, tenant_id: str, digest: str) -> None:
        self.execute(
            "UPDATE artifacts SET last_accessed_at=? WHERE tenant_id=? AND digest=?",
            (iso(self.now()), tenant_id, digest),
        )

    def add_artifact_ref(
        self, tenant_id: str, source_kind: str, source_id: str, target_digest: str, ref_kind: str
    ) -> None:
        self.execute(
            "INSERT INTO artifact_refs (tenant_id, source_kind, source_id, target_digest, ref_kind,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (tenant_id, source_kind, source_id, require_digest(target_digest), ref_kind, iso(self.now())),
        )

    def artifact_referrers(self, tenant_id: str, digest: str) -> list[tuple[str, str, str]]:
        return [
            (row[0], row[1], row[2])
            for row in self.query(
                "SELECT source_kind, source_id, ref_kind FROM artifact_refs WHERE tenant_id=?"
                " AND target_digest=?",
                (tenant_id, digest),
            )
        ]

    def artifact_targets(self, tenant_id: str, source_kind: str, source_id: str) -> list[str]:
        return [
            row[0]
            for row in self.query(
                "SELECT target_digest FROM artifact_refs WHERE tenant_id=? AND source_kind=? AND source_id=?",
                (tenant_id, source_kind, source_id),
            )
        ]

    def list_artifacts(self, tenant_id: str) -> list[ArtifactRecord]:
        rows = self.query("SELECT digest FROM artifacts WHERE tenant_id=? ORDER BY digest", (tenant_id,))
        out = []
        for row in rows:
            record = self.get_artifact(tenant_id, row[0])
            if record is not None:
                out.append(record)
        return out

    def delete_artifact_row(self, tenant_id: str, digest: str) -> None:
        self.execute("DELETE FROM artifact_refs WHERE tenant_id=? AND target_digest=?", (tenant_id, digest))
        self.execute("DELETE FROM artifacts WHERE tenant_id=? AND digest=?", (tenant_id, digest))

    # -- action cache -----------------------------------------------------
    def get_action_entry(
        self, tenant_id: str, trust_namespace: TrustNamespace, action_key: str
    ) -> ActionCacheRecord | None:
        row = self.query_one(
            "SELECT tenant_id, trust_namespace, action_key, result_manifest_digest, validation_level,"
            " producer_identity, provenance_digest, status, entry_kind, failure_code, expires_at,"
            " hit_count, saved_cpu_ms, saved_wall_ms, saved_compiler_ms, saved_model_tokens,"
            " quarantine_reason"
            " FROM action_cache_entries WHERE tenant_id=? AND trust_namespace=? AND action_key=?",
            (tenant_id, str(trust_namespace), action_key),
        )
        if row is None:
            return None
        return ActionCacheRecord(
            tenant_id=row[0],
            trust_namespace=TrustNamespace(row[1]),
            action_key=row[2],
            result_manifest_digest=row[3],
            validation_level=ValidationLevel(row[4]),
            producer_identity=row[5],
            provenance_digest=row[6],
            status=CacheEntryStatus(row[7]),
            entry_kind=row[8],
            failure_code=row[9],
            expires_at=row[10],
            hit_count=int(row[11]),
            saved_cpu_ms=int(row[12]),
            saved_wall_ms=int(row[13]),
            saved_compiler_ms=int(row[14]),
            saved_model_tokens=int(row[15]),
            quarantine_reason=row[16],
        )

    def put_action_entry(self, record: ActionCacheRecord) -> ActionCacheRecord:
        self.ensure_tenant(record.tenant_id)
        existing = self.get_action_entry(record.tenant_id, record.trust_namespace, record.action_key)
        if existing is None:
            self.execute(
                "INSERT INTO action_cache_entries (tenant_id, trust_namespace, action_key,"
                " result_manifest_digest, validation_level, producer_identity, provenance_digest, status,"
                " entry_kind, failure_code, expires_at, created_at, last_accessed_at, hit_count,"
                " saved_cpu_ms, saved_wall_ms, saved_compiler_ms, saved_model_tokens,"
                " quarantine_reason)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.tenant_id,
                    str(record.trust_namespace),
                    record.action_key,
                    record.result_manifest_digest,
                    str(record.validation_level),
                    record.producer_identity,
                    record.provenance_digest,
                    str(record.status),
                    record.entry_kind,
                    record.failure_code,
                    record.expires_at,
                    iso(self.now()),
                    iso(self.now()),
                    record.hit_count,
                    record.saved_cpu_ms,
                    record.saved_wall_ms,
                    record.saved_compiler_ms,
                    record.saved_model_tokens,
                    record.quarantine_reason,
                ),
            )
            return record
        raise ConflictError(
            "action cache entry already exists; use update_action_entry",
            action_key=record.action_key,
        )

    def update_action_entry(self, record: ActionCacheRecord) -> ActionCacheRecord:
        self.execute(
            "UPDATE action_cache_entries SET result_manifest_digest=?, validation_level=?,"
            " producer_identity=?, provenance_digest=?, status=?, entry_kind=?, failure_code=?,"
            " expires_at=?, hit_count=?, saved_cpu_ms=?, saved_wall_ms=?, saved_compiler_ms=?,"
            " saved_model_tokens=?,"
            " quarantine_reason=? WHERE tenant_id=? AND trust_namespace=? AND action_key=?",
            (
                record.result_manifest_digest,
                str(record.validation_level),
                record.producer_identity,
                record.provenance_digest,
                str(record.status),
                record.entry_kind,
                record.failure_code,
                record.expires_at,
                record.hit_count,
                record.saved_cpu_ms,
                record.saved_wall_ms,
                record.saved_compiler_ms,
                record.saved_model_tokens,
                record.quarantine_reason,
                record.tenant_id,
                str(record.trust_namespace),
                record.action_key,
            ),
        )
        return record

    def record_action_hit(
        self, tenant_id: str, trust_namespace: TrustNamespace, action_key: str
    ) -> None:
        self.execute(
            "UPDATE action_cache_entries SET hit_count=hit_count+1, last_accessed_at=?"
            " WHERE tenant_id=? AND trust_namespace=? AND action_key=?",
            (iso(self.now()), tenant_id, str(trust_namespace), action_key),
        )

    def list_action_entries(self, tenant_id: str) -> list[ActionCacheRecord]:
        rows = self.query(
            "SELECT trust_namespace, action_key FROM action_cache_entries WHERE tenant_id=?"
            " ORDER BY action_key",
            (tenant_id,),
        )
        out = []
        for row in rows:
            entry = self.get_action_entry(tenant_id, TrustNamespace(row[0]), row[1])
            if entry is not None:
                out.append(entry)
        return out

    # -- staged files -----------------------------------------------------
    def insert_staged_file(self, record: StagedFileRecord) -> StagedFileRecord:
        self.execute(
            "INSERT INTO staged_files (staged_file_id, tenant_id, project_id, run_id, node_id, attempt,"
            " logical_path, file_class, status, overwrite_policy, ownership, internal_temp_path,"
            " internal_sealed_path, lease_id, lease_epoch, version, expected_size, actual_size, digest,"
            " media_type, artifact_kind, action_key, artifact_digest, source_map_digest, mode,"
            " validation_level, secret_scan_status, quarantine_reason, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.staged_file_id,
                record.tenant_id,
                record.project_id,
                record.run_id,
                record.node_id,
                record.attempt,
                record.logical_path,
                str(record.file_class),
                str(record.status),
                record.overwrite_policy,
                str(record.ownership),
                record.internal_temp_path,
                record.internal_sealed_path,
                record.lease_id,
                record.lease_epoch,
                record.version,
                record.expected_size,
                record.actual_size,
                record.digest,
                record.media_type,
                record.artifact_kind,
                record.action_key,
                record.artifact_digest,
                record.source_map_digest,
                record.mode,
                str(record.validation_level),
                str(record.secret_scan_status),
                record.quarantine_reason,
                iso(self.now()),
            ),
        )
        return record

    def get_staged_file(self, staged_file_id: str) -> StagedFileRecord:
        row = self.query_one(
            "SELECT staged_file_id, tenant_id, project_id, run_id, node_id, attempt, logical_path,"
            " file_class, status, lease_epoch, version, overwrite_policy, ownership, internal_temp_path,"
            " internal_sealed_path, lease_id, expected_size, actual_size, digest, media_type,"
            " artifact_kind, action_key, artifact_digest, source_map_digest, mode, validation_level,"
            " secret_scan_status, quarantine_reason FROM staged_files WHERE staged_file_id=?",
            (staged_file_id,),
        )
        if row is None:
            raise NotFound("staged file does not exist", staged_file_id=staged_file_id)
        return StagedFileRecord(
            staged_file_id=row[0],
            tenant_id=row[1],
            project_id=row[2],
            run_id=row[3],
            node_id=row[4],
            attempt=int(row[5]),
            logical_path=row[6],
            file_class=FileClass(row[7]),
            status=StagedFileStatus(row[8]),
            lease_epoch=int(row[9]),
            version=int(row[10]),
            overwrite_policy=row[11],
            ownership=Ownership(row[12]),
            internal_temp_path=row[13],
            internal_sealed_path=row[14],
            lease_id=row[15],
            expected_size=row[16],
            actual_size=row[17],
            digest=row[18],
            media_type=row[19],
            artifact_kind=row[20],
            action_key=row[21],
            artifact_digest=row[22],
            source_map_digest=row[23],
            mode=int(row[24]),
            validation_level=ValidationLevel(row[25]),
            secret_scan_status=SecretScanStatus(row[26]),
            quarantine_reason=row[27],
        )

    def list_staged_files(
        self, run_id: str, statuses: Sequence[StagedFileStatus] | None = None
    ) -> list[StagedFileRecord]:
        rows = self.query(
            "SELECT staged_file_id FROM staged_files WHERE run_id=? ORDER BY logical_path, staged_file_id",
            (run_id,),
        )
        records = [self.get_staged_file(row[0]) for row in rows]
        if statuses is None:
            return records
        wanted = set(statuses)
        return [record for record in records if record.status in wanted]

    def find_staged_file(
        self, run_id: str, node_id: str, attempt: int, logical_path: str
    ) -> StagedFileRecord | None:
        """Look up by the natural key the unique index enforces."""
        row = self.query_one(
            "SELECT staged_file_id FROM staged_files WHERE run_id=? AND node_id=? AND attempt=?"
            " AND logical_path=?",
            (run_id, node_id, attempt, logical_path),
        )
        return None if row is None else self.get_staged_file(row[0])

    def find_live_staged_file(self, run_id: str, logical_path: str) -> StagedFileRecord | None:
        for record in self.list_staged_files(run_id):
            if record.logical_path == logical_path and record.status not in (
                StagedFileStatus.ABORTED,
                StagedFileStatus.QUARANTINED,
            ):
                return record
        return None

    def update_staged_file(
        self,
        record: StagedFileRecord,
        target: StagedFileStatus,
        expected_version: int,
        lease_epoch: int | None = None,
        **columns: Any,
    ) -> StagedFileRecord:
        """Guarded staged-file transition.

        The ``UPDATE`` is conditional on both version and status, so a second
        writer that read the same row loses deterministically instead of
        double-sealing a logical path.
        """
        if lease_epoch is not None and record.lease_epoch != lease_epoch:
            raise StaleLease(
                "stale lease epoch for staged file",
                staged_file_id=record.staged_file_id,
                held=lease_epoch,
                current=record.lease_epoch,
            )
        if target is not record.status and target not in STAGED_FILE_TRANSITIONS[record.status]:
            raise InvalidTransition(
                f"staged file {record.status} -> {target} is not a legal transition",
                staged_file_id=record.staged_file_id,
                current=str(record.status),
                target=str(target),
            )
        allowed = {
            "internal_temp_path",
            "internal_sealed_path",
            "actual_size",
            "digest",
            "artifact_digest",
            "source_map_digest",
            "media_type",
            "artifact_kind",
            "action_key",
            "validation_level",
            "secret_scan_status",
            "quarantine_reason",
            "file_class",
            "mode",
        }
        unknown = sorted(set(columns) - allowed)
        if unknown:
            raise ConflictError("unknown staged-file columns", columns=unknown)

        assignments = ["status=?", "version=version+1"]
        params: list[Any] = [str(target)]
        for name, value in sorted(columns.items()):
            assignments.append(f"{name}=?")
            enum_value = isinstance(value, FileClass | ValidationLevel | SecretScanStatus)
            params.append(str(value) if enum_value else value)

        stamp_column = {
            StagedFileStatus.SEALED: "sealed_at",
            StagedFileStatus.CAS_PROMOTED: "promoted_at",
            StagedFileStatus.TREE_INCLUDED: "tree_included_at",
            StagedFileStatus.PUBLISHED: "published_at",
        }.get(target)
        if stamp_column:
            assignments.append(f"{stamp_column}=?")
            params.append(iso(self.now()))

        params.extend([record.staged_file_id, expected_version, str(record.status)])
        # Column names come from the ``allowed`` allowlist above, never from
        # caller-supplied text; values stay parameterised.
        clause = ", ".join(assignments)
        statement = (
            f"UPDATE staged_files SET {clause} WHERE staged_file_id=? AND version=? AND status=?"  # noqa: S608
        )
        cursor = self.execute(statement, params)
        if cursor.rowcount != 1:
            raise VersionConflict(
                "staged file version conflict", staged_file_id=record.staged_file_id, expected=expected_version
            )
        return self.get_staged_file(record.staged_file_id)

    # -- trees ------------------------------------------------------------
    def record_tree(
        self,
        tenant_id: str,
        tree_digest: str,
        run_id: str,
        manifest_digest: str,
        entry_count: int,
        total_bytes: int,
        validation_level: ValidationLevel,
        evidence_digest: str | None,
        previous_tree: str | None,
        status: str = "CANDIDATE",
    ) -> None:
        existing = self.query_one(
            "SELECT status FROM file_trees WHERE tenant_id=? AND tree_digest=?", (tenant_id, tree_digest)
        )
        if existing is not None:
            return
        self.execute(
            "INSERT INTO file_trees (tenant_id, tree_digest, run_id, manifest_digest, entry_count,"
            " total_bytes, validation_level, evidence_digest, previous_tree, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                tree_digest,
                run_id,
                manifest_digest,
                entry_count,
                total_bytes,
                str(validation_level),
                evidence_digest,
                previous_tree,
                status,
                iso(self.now()),
            ),
        )

    def mark_tree_published(self, tenant_id: str, tree_digest: str) -> None:
        self.execute(
            "UPDATE file_trees SET status='SUPERSEDED' WHERE tenant_id=? AND status='PUBLISHED'",
            (tenant_id,),
        )
        self.execute(
            "UPDATE file_trees SET status='PUBLISHED', published_at=? WHERE tenant_id=? AND tree_digest=?",
            (iso(self.now()), tenant_id, tree_digest),
        )

    def published_trees(self, tenant_id: str) -> list[str]:
        return [
            row[0]
            for row in self.query(
                "SELECT tree_digest FROM file_trees WHERE tenant_id=? AND status IN ('PUBLISHED','SUPERSEDED')"
                " ORDER BY created_at DESC",
                (tenant_id,),
            )
        ]

    # -- checkpoints ------------------------------------------------------
    def insert_checkpoint(self, record: CheckpointRecord) -> CheckpointRecord:
        self.execute(
            "UPDATE checkpoints SET status=? WHERE run_id=? AND node_id=? AND attempt=? AND status=?",
            (
                str(CheckpointStatus.SUPERSEDED),
                record.run_id,
                record.node_id,
                record.attempt,
                str(CheckpointStatus.ACTIVE),
            ),
        )
        self.execute(
            "INSERT INTO checkpoints (checkpoint_id, tenant_id, project_id, run_id, node_id, attempt,"
            " sequence, lease_epoch, manifest_digest, journal_sequence, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.checkpoint_id,
                record.tenant_id,
                record.project_id,
                record.run_id,
                record.node_id,
                record.attempt,
                record.sequence,
                record.lease_epoch,
                record.manifest_digest,
                record.journal_sequence,
                str(record.status),
                iso(self.now()),
            ),
        )
        return record

    def list_checkpoints(self, run_id: str, node_id: str | None = None) -> list[CheckpointRecord]:
        if node_id is None:
            rows = self.query(
                "SELECT checkpoint_id, tenant_id, project_id, run_id, node_id, attempt, sequence,"
                " lease_epoch, manifest_digest, journal_sequence, status FROM checkpoints WHERE run_id=?"
                " ORDER BY node_id, attempt, sequence",
                (run_id,),
            )
        else:
            rows = self.query(
                "SELECT checkpoint_id, tenant_id, project_id, run_id, node_id, attempt, sequence,"
                " lease_epoch, manifest_digest, journal_sequence, status FROM checkpoints WHERE run_id=?"
                " AND node_id=? ORDER BY attempt, sequence",
                (run_id, node_id),
            )
        return [
            CheckpointRecord(
                checkpoint_id=row[0],
                tenant_id=row[1],
                project_id=row[2],
                run_id=row[3],
                node_id=row[4],
                attempt=int(row[5]),
                sequence=int(row[6]),
                lease_epoch=int(row[7]),
                manifest_digest=row[8],
                journal_sequence=int(row[9]),
                status=CheckpointStatus(row[10]),
            )
            for row in rows
        ]

    def set_checkpoint_status(self, checkpoint_id: str, status: CheckpointStatus) -> None:
        self.execute(
            "UPDATE checkpoints SET status=? WHERE checkpoint_id=?", (str(status), checkpoint_id)
        )

    # -- side effects -----------------------------------------------------
    def claim_side_effect(
        self,
        tenant_id: str,
        run_id: str,
        node_id: str,
        idempotency_key: str,
        effect_type: str,
        payload_digest: str,
    ) -> tuple[bool, str | None]:
        """Return ``(already_committed, external_reference)``.

        Insert-if-absent makes the caller's side effect at-most-once even when a
        crash happens between the external call and the local commit.
        """
        row = self.query_one(
            "SELECT status, external_reference, payload_digest FROM side_effect_receipts"
            " WHERE tenant_id=? AND idempotency_key=?",
            (tenant_id, idempotency_key),
        )
        if row is not None:
            if row[2] != payload_digest:
                raise IdempotencyConflict(
                    "idempotency key reused with a different payload",
                    idempotency_key=idempotency_key,
                )
            return row[0] == "COMMITTED", row[1]
        stamp = iso(self.now())
        self.execute(
            "INSERT INTO side_effect_receipts (tenant_id, run_id, node_id, idempotency_key, effect_type,"
            " status, external_reference, payload_digest, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'PENDING', NULL, ?, ?, ?)",
            (tenant_id, run_id, node_id, idempotency_key, effect_type, payload_digest, stamp, stamp),
        )
        return False, None

    def complete_side_effect(
        self, tenant_id: str, idempotency_key: str, status: str, external_reference: str | None
    ) -> None:
        self.execute(
            "UPDATE side_effect_receipts SET status=?, external_reference=?, updated_at=?"
            " WHERE tenant_id=? AND idempotency_key=?",
            (status, external_reference, iso(self.now()), tenant_id, idempotency_key),
        )

    def list_side_effects(self, run_id: str) -> list[dict[str, Any]]:
        return [
            {
                "idempotency_key": row[0],
                "effect_type": row[1],
                "status": row[2],
                "external_reference": row[3],
                "payload_digest": row[4],
                "node_id": row[5],
            }
            for row in self.query(
                "SELECT idempotency_key, effect_type, status, external_reference, payload_digest, node_id"
                " FROM side_effect_receipts WHERE run_id=? ORDER BY idempotency_key",
                (run_id,),
            )
        ]

    # -- journal materialisation -----------------------------------------
    def append_event(
        self,
        tenant_id: str,
        run_id: str | None,
        node_id: str | None,
        sequence: int | None,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        lease_epoch: int | None = None,
        project_id: str | None = None,
    ) -> bool:
        """Insert an event. Returns ``False`` when it was a duplicate delivery."""
        payload_digest = digest_of(payload)
        if run_id is not None and sequence is not None:
            existing = self.query_one(
                "SELECT payload_digest FROM cache_events WHERE run_id=? AND sequence=?", (run_id, sequence)
            )
            if existing is not None:
                if existing[0] != payload_digest:
                    raise ConflictError(
                        "journal sequence reused with different payload", run_id=run_id, sequence=sequence
                    )
                return False
        self.execute(
            "INSERT INTO cache_events (event_id, tenant_id, project_id, run_id, node_id, sequence,"
            " event_type, actor, lease_epoch, payload, payload_digest, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("evt"),
                tenant_id,
                project_id,
                run_id,
                node_id,
                sequence,
                event_type,
                actor,
                lease_epoch,
                _json(payload),
                payload_digest,
                iso(self.now()),
            ),
        )
        if run_id is not None and sequence is not None:
            self.execute(
                "UPDATE runs SET journal_sequence=? WHERE run_id=? AND journal_sequence<?",
                (sequence, run_id, sequence),
            )
        return True

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return [
            {
                "sequence": row[0],
                "event_type": row[1],
                "actor": row[2],
                "node_id": row[3],
                "lease_epoch": row[4],
                "payload": _unjson(row[5]),
                "payload_digest": row[6],
            }
            for row in self.query(
                "SELECT sequence, event_type, actor, node_id, lease_epoch, payload, payload_digest"
                " FROM cache_events WHERE run_id=? ORDER BY sequence",
                (run_id,),
            )
        ]

    # -- pins, certificates, revocations ---------------------------------
    def add_pin(
        self, tenant_id: str, source_kind: str, source_id: str, reason: str, expires_at: float | None = None
    ) -> str:
        pin_id = new_id("pin")
        self.execute(
            "INSERT INTO pins (pin_id, tenant_id, source_kind, source_id, reason, expires_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pin_id, tenant_id, source_kind, source_id, reason, expires_at, iso(self.now())),
        )
        return pin_id

    def remove_pin(self, pin_id: str) -> bool:
        cursor = self.execute("DELETE FROM pins WHERE pin_id=?", (pin_id,))
        return bool(cursor.rowcount)

    def list_pins(self, tenant_id: str, now: float | None = None) -> list[dict[str, Any]]:
        moment = self.now() if now is None else now
        return [
            {
                "pin_id": row[0],
                "source_kind": row[1],
                "source_id": row[2],
                "reason": row[3],
                "expires_at": row[4],
            }
            for row in self.query(
                "SELECT pin_id, source_kind, source_id, reason, expires_at FROM pins WHERE tenant_id=?",
                (tenant_id,),
            )
            if row[4] is None or float(row[4]) > moment
        ]

    def add_certificate(self, record: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO certificates (certificate_id, tenant_id, scope_digest, tree_digest,"
            " evidence_digest, validation_level, signature, issuer, status, issued_at, expires_at,"
            " limitations) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["certificate_id"],
                record["tenant_id"],
                record["scope_digest"],
                record["tree_digest"],
                record["evidence_digest"],
                str(record["validation_level"]),
                record["signature"],
                record["issuer"],
                record.get("status", "VALID"),
                record["issued_at"],
                record["expires_at"],
                _json(record.get("limitations", [])),
            ),
        )

    def get_certificate(self, certificate_id: str) -> dict[str, Any] | None:
        row = self.query_one(
            "SELECT certificate_id, tenant_id, scope_digest, tree_digest, evidence_digest,"
            " validation_level, signature, issuer, status, issued_at, expires_at, limitations"
            " FROM certificates WHERE certificate_id=?",
            (certificate_id,),
        )
        if row is None:
            return None
        return {
            "certificate_id": row[0],
            "tenant_id": row[1],
            "scope_digest": row[2],
            "tree_digest": row[3],
            "evidence_digest": row[4],
            "validation_level": ValidationLevel(row[5]),
            "signature": row[6],
            "issuer": row[7],
            "status": row[8],
            "issued_at": float(row[9]),
            "expires_at": float(row[10]),
            "limitations": _unjson(row[11]) or [],
        }

    def set_certificate_status(self, certificate_id: str, status: str) -> None:
        self.execute("UPDATE certificates SET status=? WHERE certificate_id=?", (status, certificate_id))

    def certificates_for_tree(self, tenant_id: str, tree_digest: str) -> list[str]:
        return [
            row[0]
            for row in self.query(
                "SELECT certificate_id FROM certificates WHERE tenant_id=? AND tree_digest=?",
                (tenant_id, tree_digest),
            )
        ]

    def add_revocation(self, tenant_id: str, subject_kind: str, subject_id: str, reason: str) -> str:
        revocation_id = new_id("rev")
        self.execute(
            "INSERT INTO revocations (revocation_id, tenant_id, subject_kind, subject_id, reason,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (revocation_id, tenant_id, subject_kind, subject_id, reason, iso(self.now())),
        )
        return revocation_id

    def is_revoked(self, tenant_id: str, subject_kind: str, subject_id: str) -> bool:
        return (
            self.query_one(
                "SELECT 1 FROM revocations WHERE tenant_id=? AND subject_kind=? AND subject_id=?",
                (tenant_id, subject_kind, subject_id),
            )
            is not None
        )

    # -- gc ---------------------------------------------------------------
    def create_gc_plan(self, tenant_id: str, payload: dict[str, Any]) -> str:
        plan_id = new_id("gcp")
        self.execute(
            "INSERT INTO gc_plans (plan_id, tenant_id, status, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (plan_id, tenant_id, "DRY_RUN", _json(payload), self.now()),
        )
        return plan_id

    def get_gc_plan(self, plan_id: str) -> dict[str, Any] | None:
        row = self.query_one(
            "SELECT plan_id, tenant_id, status, payload, created_at, applied_at FROM gc_plans WHERE plan_id=?",
            (plan_id,),
        )
        if row is None:
            return None
        return {
            "plan_id": row[0],
            "tenant_id": row[1],
            "status": row[2],
            "payload": _unjson(row[3]),
            "created_at": float(row[4]),
            "applied_at": row[5],
        }

    def set_gc_plan_status(self, plan_id: str, status: str, applied_at: float | None = None) -> None:
        self.execute(
            "UPDATE gc_plans SET status=?, applied_at=? WHERE plan_id=?", (status, applied_at, plan_id)
        )

    def add_gc_receipt(self, plan_id: str, digest: str, outcome: str, detail: str | None = None) -> None:
        self.execute(
            "INSERT INTO gc_receipts (plan_id, digest, outcome, detail, created_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT DO NOTHING",
            (plan_id, digest, outcome, detail, self.now()),
        )

    def gc_receipts(self, plan_id: str) -> list[dict[str, Any]]:
        return [
            {"digest": row[0], "outcome": row[1], "detail": row[2]}
            for row in self.query(
                "SELECT digest, outcome, detail FROM gc_receipts WHERE plan_id=? ORDER BY digest", (plan_id,)
            )
        ]

    # -- idempotency and outbox ------------------------------------------
    def remember_idempotent(
        self, tenant_id: str, key: str, operation: str, request: Any, response: Any
    ) -> Any:
        request_digest = digest_of(request)
        row = self.query_one(
            "SELECT operation, request_digest, response FROM idempotency_records"
            " WHERE tenant_id=? AND idempotency_key=?",
            (tenant_id, key),
        )
        if row is not None:
            if row[0] != operation or row[1] != request_digest:
                raise IdempotencyConflict("idempotency key reused for a different request", key=key)
            return _unjson(row[2])
        self.execute(
            "INSERT INTO idempotency_records (tenant_id, idempotency_key, operation, request_digest,"
            " response, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, key, operation, request_digest, _json(response), self.now()),
        )
        return response

    def replay_idempotent(self, tenant_id: str, key: str, operation: str, request: Any) -> Any | None:
        row = self.query_one(
            "SELECT operation, request_digest, response FROM idempotency_records"
            " WHERE tenant_id=? AND idempotency_key=?",
            (tenant_id, key),
        )
        if row is None:
            return None
        if row[0] != operation or row[1] != digest_of(request):
            raise IdempotencyConflict("idempotency key reused for a different request", key=key)
        return _unjson(row[2])

    #: SQLite exposes the generated key through ``lastrowid``; PostgreSQL needs
    #: ``RETURNING``. The dialect supplies the clause and the reader.
    returning_clause: str = ""

    def enqueue_outbox(self, tenant_id: str, topic: str, event_key: str, payload: dict[str, Any]) -> int:
        cursor = self.execute(
            # ``returning_clause`` is a class constant per dialect, never input.
            "INSERT INTO outbox_events (tenant_id, topic, event_key, payload, attempts, created_at)"  # noqa: S608
            f" VALUES (?, ?, ?, ?, 0, ?){self.returning_clause}",
            (tenant_id, topic, event_key, _json(payload), self.now()),
        )
        return self._generated_key(cursor)

    def _generated_key(self, cursor: Any) -> int:
        return int(cursor.lastrowid or 0)

    def pending_outbox(self, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "outbox_id": int(row[0]),
                "tenant_id": row[1],
                "topic": row[2],
                "event_key": row[3],
                "payload": _unjson(row[4]),
                "attempts": int(row[5]),
            }
            for row in self.query(
                "SELECT outbox_id, tenant_id, topic, event_key, payload, attempts FROM outbox_events"
                " WHERE published_at IS NULL ORDER BY outbox_id LIMIT ?",
                (limit,),
            )
        ]

    def mark_outbox_published(self, outbox_id: int) -> None:
        self.execute(
            "UPDATE outbox_events SET published_at=? WHERE outbox_id=?", (self.now(), outbox_id)
        )

    def mark_outbox_attempt(self, outbox_id: int) -> None:
        self.execute("UPDATE outbox_events SET attempts=attempts+1 WHERE outbox_id=?", (outbox_id,))


#: Applied in order, once each. ``0001`` is written with ``IF NOT EXISTS``
#: throughout, so a database created before the ledger existed converges.
SQLITE_MIGRATIONS: tuple[str, ...] = (
    "0001_init.sql",
    "0002_saved_compiler_ms.sql",
)


class SqliteMetadataStore(MetadataStore):
    paramstyle = "?"

    @classmethod
    def open(cls, path: Path | str, clock: Clock = SYSTEM_CLOCK) -> SqliteMetadataStore:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(target), timeout=30.0, isolation_level="DEFERRED")
        for pragma in SQLITE_PRAGMAS:
            connection.execute(pragma)
        store = cls(connection, clock)
        store.migrate()
        return store

    def migrate(self) -> None:
        """Apply pending migrations exactly once.

        ``ALTER TABLE ADD COLUMN`` is not idempotent, so which migrations have
        run has to be recorded rather than inferred.
        """
        self._connection.executescript(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name TEXT PRIMARY KEY, applied_at TEXT NOT NULL);"
        )
        applied = {
            str(row[0]) for row in self._connection.execute("SELECT name FROM schema_migrations")
        }
        for name in SQLITE_MIGRATIONS:
            if name in applied:
                continue
            script = (MIGRATIONS_DIR / "sqlite" / name).read_text(encoding="utf-8")
            self._connection.executescript(script)
            self._connection.execute(
                "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (name, iso(self.now())),
            )
        # ``executescript`` commits, but the ledger INSERT opens a transaction
        # of its own; leaving it open would block the PRAGMAs the caller sets.
        self._connection.commit()
        for pragma in SQLITE_PRAGMAS:
            self._connection.execute(pragma)
        self._connection.commit()


POSTGRES_MIGRATIONS: tuple[str, ...] = (
    "0001_init.sql",
    "0002_elmos_extensions.sql",
    "0003_column_types.sql",
    "0004_saved_compiler_ms.sql",
)


class PostgresMetadataStore(MetadataStore):
    """Production profile. Requires the ``postgres`` extra (``psycopg``)."""

    paramstyle = "%s"
    returning_clause = " RETURNING outbox_id"

    @classmethod
    def open(cls, dsn: str, clock: Clock = SYSTEM_CLOCK, migrate: bool = True) -> PostgresMetadataStore:
        import psycopg

        connection = psycopg.connect(dsn, autocommit=False)
        store = cls(connection, clock)
        if migrate:
            store.migrate()
        return store

    def migrate(self) -> None:
        for name in POSTGRES_MIGRATIONS:
            script = (MIGRATIONS_DIR / "postgres" / name).read_text(encoding="utf-8")
            with self._connection.cursor() as cursor:
                cursor.execute(script)
        self._connection.commit()

    def execute(self, statement: str, params: Sequence[Any] = ()) -> Any:
        cursor = self._connection.cursor()
        cursor.execute(self._sql(statement), tuple(params))
        return cursor

    def _generated_key(self, cursor: Any) -> int:
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def reset(self) -> None:
        """Drop every table this schema owns. Used by contract tests only."""
        tables = [
            "gc_receipts",
            "gc_plans",
            "idempotency_records",
            "outbox_events",
            "revocations",
            "certificates",
            "pins",
            "cache_events",
            "side_effect_receipts",
            "checkpoints",
            "file_trees",
            "staged_files",
            "action_cache_entries",
            "artifact_refs",
            "artifacts",
            "run_nodes",
            "runs",
            "snapshots",
            "projects",
            "tenants",
        ]
        with self._connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS " + ", ".join(tables) + " CASCADE")
        self._connection.commit()


def open_store(target: str | Path, clock: Clock = SYSTEM_CLOCK) -> MetadataStore:
    """Open SQLite for a filesystem path, PostgreSQL for a ``postgres[ql]://`` DSN."""
    text = str(target)
    if text.startswith("postgres://") or text.startswith("postgresql://"):
        return PostgresMetadataStore.open(text, clock)
    return SqliteMetadataStore.open(text, clock)


__all__ = [
    "MetadataStore",
    "PostgresMetadataStore",
    "SqliteMetadataStore",
    "new_id",
    "open_store",
    "replace",
]
