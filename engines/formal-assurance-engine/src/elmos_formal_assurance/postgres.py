from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import digest_bytes
from .contracts import TrustedIdentity, utc_now


class PostgresMigrationError(RuntimeError):
    """Raised when the exact PostgreSQL 17 migration cannot be applied safely."""


class Postgres17MigrationManager:
    """Authorized, transactional installer for repository-owned SQL extensions.

    A successful return is a self-attested engineering receipt. It is not proof
    that a production cluster, RLS role design, backup, failover, or workload has
    been independently validated.
    """

    REQUIRED_RELATIONS = (
        "formal_assurance.proof_revalidation_queue",
        "formal_assurance.security_audit_event",
        "formal_assurance.event_outbox",
    )
    REQUIRED_ROLES = frozenset(
        {"formal-assurance-schema-admin", "formal-assurance-admin", "admin"}
    )

    def __init__(self, migration_path: str | Path | None = None) -> None:
        path = (
            Path(migration_path)
            if migration_path is not None
            else Path(__file__).resolve().parents[2]
            / "sql/postgresql/V005__formal_assurance_runtime_extensions.sql"
        )
        if path.is_symlink() or not path.is_file():
            raise PostgresMigrationError(
                "PostgreSQL migration path is missing or unsafe"
            )
        data = path.read_bytes()
        if not data or len(data) > 1024 * 1024:
            raise PostgresMigrationError("PostgreSQL migration size is outside policy")
        try:
            sql = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PostgresMigrationError("PostgreSQL migration is not UTF-8") from exc
        required_fragments = {
            "ENABLE ROW LEVEL SECURITY",
            "security audit events are append-only",
            "proof_revalidation_queue",
            "event_outbox",
            "trg_proof_event_outbox",
            "trg_gate_event_outbox",
        }
        missing = sorted(
            fragment for fragment in required_fragments if fragment not in sql
        )
        if missing:
            raise PostgresMigrationError(
                "PostgreSQL migration contract is incomplete: " + ", ".join(missing)
            )
        self.path = path.resolve(strict=True)
        self.sql = sql
        self.digest = digest_bytes(data)

    def plan(self) -> dict[str, Any]:
        return {
            "format": "elmos-formal-postgres-migration-plan/v1",
            "engine": "PostgreSQL",
            "requiredMajorVersion": 17,
            "migration": self.path.name,
            "migrationSha256": self.digest,
            "requiredRelations": list(self.REQUIRED_RELATIONS),
            "executionStatus": "NOT_RUN",
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
        }

    def apply(self, connection: Any, identity: TrustedIdentity) -> dict[str, Any]:
        if not set(identity.roles) & self.REQUIRED_ROLES:
            raise PostgresMigrationError(
                "PostgreSQL migration requires an explicit schema-admin role"
            )
        if identity.authorization_ref is None:
            raise PostgresMigrationError(
                "PostgreSQL migration requires an authorization reference"
            )
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SHOW server_version_num")
            version_row = cursor.fetchone()
            version = self._scalar(version_row, "server_version_num")
            try:
                version_number = int(version)
            except (TypeError, ValueError) as exc:
                raise PostgresMigrationError(
                    "PostgreSQL server_version_num is invalid"
                ) from exc
            if not 170000 <= version_number < 180000:
                raise PostgresMigrationError(
                    "the Formal Assurance production contract requires PostgreSQL 17"
                )
            cursor.execute(self.sql)
            verified: list[str] = []
            for relation in self.REQUIRED_RELATIONS:
                cursor.execute("SELECT to_regclass(%s)", (relation,))
                observed = self._scalar(cursor.fetchone(), "to_regclass")
                if observed != relation:
                    raise PostgresMigrationError(
                        f"PostgreSQL relation verification failed: {relation}"
                    )
                verified.append(relation)
            connection.commit()
        except Exception as exc:
            try:
                connection.rollback()
            except Exception as rollback_exc:
                raise PostgresMigrationError(
                    "PostgreSQL migration failed and rollback was not confirmed"
                ) from rollback_exc
            if isinstance(exc, PostgresMigrationError):
                raise
            raise PostgresMigrationError(
                f"PostgreSQL migration failed: {type(exc).__name__}"
            ) from exc
        finally:
            if cursor is not None:
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()
        return {
            "format": "elmos-formal-postgres-migration-receipt/v1",
            "engine": "PostgreSQL",
            "serverMajorVersion": 17,
            "migration": self.path.name,
            "migrationSha256": self.digest,
            "verifiedRelations": verified,
            "authorizationRef": identity.authorization_ref,
            "executedBy": identity.actor_id,
            "executedAt": utc_now(),
            "executionStatus": "LOCAL_EXECUTED_SELF_ATTESTED",
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
        }

    @staticmethod
    def _scalar(row: Any, field: str) -> Any:
        if row is None:
            raise PostgresMigrationError(f"PostgreSQL query returned no {field}")
        if isinstance(row, dict):
            if field in row:
                return row[field]
            if len(row) == 1:
                return next(iter(row.values()))
        if isinstance(row, (tuple, list)) and len(row) == 1:
            return row[0]
        try:
            return row[0]
        except (KeyError, IndexError, TypeError) as exc:
            raise PostgresMigrationError(
                f"PostgreSQL query returned an invalid {field} row"
            ) from exc


__all__ = ["Postgres17MigrationManager", "PostgresMigrationError"]
