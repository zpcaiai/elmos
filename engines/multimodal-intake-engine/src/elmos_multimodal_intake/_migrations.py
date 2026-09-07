"""Bounded access to SQL migrations shipped inside the Python package."""

from __future__ import annotations

from importlib.resources import files
import sqlite3

from .errors import IntegrityError


_MIGRATIONS = frozenset(
    {
        "001_initial.sql",
        "004_persistent_knowledge.sql",
        "005_knowledge_worker_evidence.sql",
        "006_knowledge_source_tombstones.sql",
        "007_progress_job_version.sql",
        "008_knowledge_outbox_delivery_state.sql",
        "009_skill_execution_dispatch_phase.sql",
        "010_human_review_corrections.sql",
        "011_human_review_workflow.sql",
        "012_skill_execution_response_digest.sql",
        "013_core_outbox_payload_integrity.sql",
        "014_human_review_authoritative_sources.sql",
        "015_human_review_enqueue_recovery.sql",
        "016_human_review_target_head_reservations.sql",
        "017_archive_expansion_lineage.sql",
        "018_governance_deletion_workflow.sql",
        "019_context_lifecycle.sql",
        "020_project_package_lifecycle.sql",
        "021_telemetry_cost_ledger.sql",
        "022_downstream_agent_integration.sql",
        "023_processing_job_cancellation.sql",
        "024_core_outbox_delivery_receipts.sql",
    }
)
_MAX_MIGRATION_BYTES = 1024 * 1024
_MIGRATION_CHAIN = (
    (0, 1, "001_initial.sql"),
    (1, 4, "004_persistent_knowledge.sql"),
    (4, 5, "005_knowledge_worker_evidence.sql"),
    (5, 6, "006_knowledge_source_tombstones.sql"),
    (6, 7, "007_progress_job_version.sql"),
    (7, 8, "008_knowledge_outbox_delivery_state.sql"),
    (8, 9, "009_skill_execution_dispatch_phase.sql"),
    (9, 10, "010_human_review_corrections.sql"),
    (10, 11, "011_human_review_workflow.sql"),
    (11, 12, "012_skill_execution_response_digest.sql"),
    (12, 13, "013_core_outbox_payload_integrity.sql"),
    (13, 14, "014_human_review_authoritative_sources.sql"),
    (14, 15, "015_human_review_enqueue_recovery.sql"),
    (15, 16, "016_human_review_target_head_reservations.sql"),
    (16, 17, "017_archive_expansion_lineage.sql"),
    (17, 18, "018_governance_deletion_workflow.sql"),
    (18, 19, "019_context_lifecycle.sql"),
    (19, 20, "020_project_package_lifecycle.sql"),
    (20, 21, "021_telemetry_cost_ledger.sql"),
    (21, 22, "022_downstream_agent_integration.sql"),
    (22, 23, "023_processing_job_cancellation.sql"),
    (23, 24, "024_core_outbox_delivery_receipts.sql"),
)


def migration_sql(name: str) -> str:
    if name not in _MIGRATIONS:
        raise IntegrityError("MIGRATION_RESOURCE_UNKNOWN")
    try:
        data = (
            files("elmos_multimodal_intake")
            .joinpath("migrations", name)
            .read_bytes()
        )
    except (FileNotFoundError, OSError) as error:
        raise IntegrityError("MIGRATION_RESOURCE_UNAVAILABLE") from error
    if not data or len(data) > _MAX_MIGRATION_BYTES or b"\x00" in data:
        raise IntegrityError("MIGRATION_RESOURCE_INVALID")
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise IntegrityError("MIGRATION_RESOURCE_INVALID") from error


def migrate_connection(connection: sqlite3.Connection, *, target_version: int) -> int:
    """Apply the one exact migration chain without committing caller work."""

    if not isinstance(connection, sqlite3.Connection):
        raise IntegrityError("MIGRATION_CONNECTION_INVALID")
    if target_version not in {1, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24}:
        raise IntegrityError("MIGRATION_TARGET_INVALID")
    if connection.in_transaction:
        raise IntegrityError("MIGRATION_ACTIVE_TRANSACTION_FORBIDDEN")
    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current > target_version:
        return current
    while current < target_version:
        migration = next(
            (item for item in _MIGRATION_CHAIN if item[0] == current and item[1] <= target_version),
            None,
        )
        if migration is None:
            raise IntegrityError("MIGRATION_VERSION_PATH_UNSUPPORTED")
        _source_version, next_version, name = migration
        try:
            connection.executescript(migration_sql(name))
        except sqlite3.DatabaseError as error:
            if connection.in_transaction:
                connection.rollback()
            raise IntegrityError("MIGRATION_EXECUTION_FAILED") from error
        if connection.in_transaction:
            connection.rollback()
            raise IntegrityError("MIGRATION_TRANSACTION_INCOMPLETE")
        observed = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if observed != next_version:
            raise IntegrityError("MIGRATION_VERSION_BINDING_MISMATCH")
        current = observed
    return current
