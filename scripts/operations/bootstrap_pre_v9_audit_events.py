#!/usr/bin/env python3
"""Safely prepare pre-V9 ``audit_events`` rows for Flyway V9.

V9 installs the append-only trigger before its tenant-column backfill.  A
database with rows written by V1 through V8 therefore needs a narrowly scoped
preparation step before Flyway is allowed to execute V9.  This command is
read-only unless ``--apply`` plus target-bound and V9-source-bound environment
confirmations are supplied.

The emitted receipt is redacted, digest-bound, local self-attested engineering
evidence.  It is never production certification and it never edits Flyway
history.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import zlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIRECTORY = (
    ROOT
    / "modules"
    / "persistence"
    / "src"
    / "main"
    / "resources"
    / "db"
    / "migration"
)
DATABASE_URL_ENV = "ELMOS_DATABASE_URL"
CONFIRMATION_ENV = "ELMOS_PRE_V9_AUDIT_BOOTSTRAP_CONFIRM"
CONFIRMATION_PREFIX = "APPLY_PRE_V9_AUDIT_ORG_SYSTEM:"
V9_SOURCE_CONFIRMATION_ENV = "ELMOS_PRE_V9_SOURCE_CONFIRM"
V9_SOURCE_CONFIRMATION_PREFIX = "APPLY_WITH_V9_SOURCE_SHA256:"
SYSTEM_ORGANIZATION = "org-system"
ADVISORY_LOCK_KEY = 0x454C4D4F535F5639
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,95}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MIGRATION_NAME_PATTERN = re.compile(
    r"^V(?P<version>[1-8])__(?P<description>[A-Za-z0-9_]+)\.sql$"
)


class BootstrapBlocked(RuntimeError):
    """A fail-closed condition safe to expose without database details."""

    def __init__(self, code: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", code):
            raise ValueError("invalid bootstrap blocker code")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class MigrationSpec:
    installed_rank: int
    version: str
    description: str
    script: str
    checksum: int
    source_sha256: str


@dataclasses.dataclass(frozen=True)
class V9SourceGuard:
    script: str
    source_sha256: str
    trigger_offset: int
    tenant_backfill_offset: int


@dataclasses.dataclass(frozen=True)
class ReceiptReservation:
    path: Path
    device: int
    inode: int


@dataclasses.dataclass(frozen=True)
class HistoryRow:
    installed_rank: int
    version: str | None
    description: str
    migration_type: str
    script: str
    checksum: int | None
    success: bool


@dataclasses.dataclass(frozen=True)
class ColumnState:
    ordinal_position: int
    name: str
    data_type: str
    udt_name: str
    maximum_length: int | None
    nullable: bool
    default: str | None
    identity: bool
    generated: str


@dataclasses.dataclass(frozen=True)
class TriggerState:
    name: str
    function_schema: str
    function_name: str
    definition: str


@dataclasses.dataclass(frozen=True)
class CatalogSnapshot:
    target_material: str
    server_version_num: str
    history_table_present: bool
    audit_table_present: bool
    history: tuple[HistoryRow, ...]
    columns: tuple[ColumnState, ...]
    primary_key_columns: tuple[str, ...]
    triggers: tuple[TriggerState, ...]
    organization_null_exists: bool
    organization_non_system_exists: bool


@dataclasses.dataclass(frozen=True)
class Assessment:
    snapshot: CatalogSnapshot
    state: str
    blockers: tuple[str, ...]


class Cursor(Protocol):
    rowcount: int

    def execute(self, query: str, parameters: Sequence[Any] | None = None) -> Any: ...

    def fetchone(self) -> Sequence[Any] | None: ...

    def fetchall(self) -> Sequence[Sequence[Any]]: ...

    def close(self) -> None: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...

    def close(self) -> None: ...


Connector = Callable[[str, int], Connection]


EXPECTED_BASE_COLUMNS = (
    ColumnState(1, "audit_id", "character varying", "varchar", 64, False, None, False, "NEVER"),
    ColumnState(2, "actor_type", "character varying", "varchar", 32, False, None, False, "NEVER"),
    ColumnState(3, "actor_id", "text", "text", None, False, None, False, "NEVER"),
    ColumnState(4, "action", "text", "text", None, False, None, False, "NEVER"),
    ColumnState(5, "resource_type", "character varying", "varchar", 64, False, None, False, "NEVER"),
    ColumnState(6, "resource_id", "text", "text", None, False, None, False, "NEVER"),
    ColumnState(7, "before_hash", "text", "text", None, True, None, False, "NEVER"),
    ColumnState(8, "after_hash", "text", "text", None, True, None, False, "NEVER"),
    ColumnState(9, "occurred_at", "timestamp with time zone", "timestamptz", None, False, None, False, "NEVER"),
    ColumnState(10, "request_id", "character varying", "varchar", 128, False, None, False, "NEVER"),
    ColumnState(11, "runner_id", "text", "text", None, True, None, False, "NEVER"),
    ColumnState(12, "policy_decision", "character varying", "varchar", 32, False, None, False, "NEVER"),
    ColumnState(13, "result", "character varying", "varchar", 32, False, None, False, "NEVER"),
)


def _flyway_checksum(path: Path) -> int:
    checksum = 0
    with path.open(encoding="utf-8-sig") as source:
        for line in source:
            checksum = zlib.crc32(line.rstrip("\r\n").encode("utf-8"), checksum)
    return checksum - 2**32 if checksum >= 2**31 else checksum


def discover_expected_migrations(
    directory: Path = MIGRATION_DIRECTORY,
) -> tuple[MigrationSpec, ...]:
    discovered: list[MigrationSpec] = []
    for version in range(1, 9):
        candidates = sorted(directory.glob(f"V{version}__*.sql"))
        if len(candidates) != 1:
            raise BootstrapBlocked("LOCAL_MIGRATION_INVENTORY_INVALID")
        path = candidates[0]
        match = MIGRATION_NAME_PATTERN.fullmatch(path.name)
        if match is None or int(match.group("version")) != version:
            raise BootstrapBlocked("LOCAL_MIGRATION_INVENTORY_INVALID")
        content = path.read_bytes()
        discovered.append(
            MigrationSpec(
                installed_rank=version,
                version=str(version),
                description=match.group("description").replace("_", " "),
                script=path.name,
                checksum=_flyway_checksum(path),
                source_sha256=hashlib.sha256(content).hexdigest(),
            )
        )
    return tuple(discovered)


def discover_v9_source_guard(
    directory: Path = MIGRATION_DIRECTORY,
) -> V9SourceGuard:
    candidates = sorted(directory.glob("V9__*.sql"))
    if len(candidates) != 1 or candidates[0].name != (
        "V9__enterprise_identity_tenant_and_private_execution.sql"
    ):
        raise BootstrapBlocked("LOCAL_V9_HAZARD_SOURCE_INVALID")
    path = candidates[0]
    content = path.read_bytes()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise BootstrapBlocked("LOCAL_V9_HAZARD_SOURCE_INVALID") from error
    executable_text = _sql_without_comments(text)
    trigger_marker = (
        "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events"
    )
    add_marker = (
        "EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS "
        "organization_id varchar(96)'"
    )
    update_marker = (
        "EXECUTE format('UPDATE %I SET organization_id = %L "
        "WHERE organization_id IS NULL'"
    )
    not_null_marker = (
        "EXECUTE format('ALTER TABLE %I ALTER COLUMN organization_id SET NOT NULL'"
    )
    offsets = {
        "trigger": executable_text.find(trigger_marker),
        "add": executable_text.find(add_marker),
        "update": executable_text.find(update_marker),
        "not_null": executable_text.find(not_null_marker),
    }
    if any(offset < 0 for offset in offsets.values()) or not (
        offsets["trigger"] < offsets["add"] < offsets["update"] < offsets["not_null"]
    ):
        raise BootstrapBlocked("LOCAL_V9_HAZARD_SOURCE_INVALID")
    return V9SourceGuard(
        script=path.name,
        source_sha256=hashlib.sha256(content).hexdigest(),
        trigger_offset=offsets["trigger"],
        tenant_backfill_offset=offsets["update"],
    )


def _sql_without_comments(text: str) -> str:
    """Blank SQL comments while retaining offsets and quoted marker strings."""
    rendered = list(text)
    index = 0
    quote: str | None = None
    block_depth = 0
    while index < len(text):
        if block_depth:
            if text.startswith("/*", index):
                rendered[index] = rendered[index + 1] = " "
                block_depth += 1
                index += 2
            elif text.startswith("*/", index):
                rendered[index] = rendered[index + 1] = " "
                block_depth -= 1
                index += 2
            else:
                if text[index] not in "\r\n":
                    rendered[index] = " "
                index += 1
            continue
        if quote is not None:
            if text[index] == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if text.startswith("--", index):
            while index < len(text) and text[index] not in "\r\n":
                rendered[index] = " "
                index += 1
            continue
        if text.startswith("/*", index):
            rendered[index] = rendered[index + 1] = " "
            block_depth = 1
            index += 2
            continue
        if text[index] in ("'", '"'):
            quote = text[index]
        index += 1
    if block_depth:
        raise BootstrapBlocked("LOCAL_V9_HAZARD_SOURCE_INVALID")
    return "".join(rendered)


def _expected_history(
    migrations: Sequence[MigrationSpec],
) -> tuple[HistoryRow, ...]:
    return tuple(
        HistoryRow(
            installed_rank=item.installed_rank,
            version=item.version,
            description=item.description,
            migration_type="SQL",
            script=item.script,
            checksum=item.checksum,
            success=True,
        )
        for item in migrations
    )


def _organization_column(nullable: bool) -> ColumnState:
    return ColumnState(
        14,
        "organization_id",
        "character varying",
        "varchar",
        96,
        nullable,
        None,
        False,
        "NEVER",
    )


def evaluate_snapshot(
    snapshot: CatalogSnapshot,
    migrations: Sequence[MigrationSpec],
) -> Assessment:
    blockers: list[str] = []
    if not snapshot.history_table_present:
        blockers.append("FLYWAY_HISTORY_MISSING")
    elif snapshot.history != _expected_history(migrations):
        blockers.append("FLYWAY_HISTORY_NOT_EXACT_V1_TO_V8")
    if not snapshot.audit_table_present:
        blockers.append("AUDIT_EVENTS_TABLE_MISSING")

    organization_column: ColumnState | None = None
    if snapshot.columns == EXPECTED_BASE_COLUMNS:
        pass
    elif len(snapshot.columns) == len(EXPECTED_BASE_COLUMNS) + 1:
        if snapshot.columns[:-1] != EXPECTED_BASE_COLUMNS:
            blockers.append("AUDIT_EVENTS_V1_COLUMNS_DRIFTED")
        else:
            organization_column = snapshot.columns[-1]
            if organization_column not in {
                _organization_column(nullable=True),
                _organization_column(nullable=False),
            }:
                blockers.append("ORGANIZATION_ID_COLUMN_CONFLICT")
    else:
        blockers.append("AUDIT_EVENTS_V1_COLUMNS_DRIFTED")

    if snapshot.primary_key_columns != ("audit_id",):
        blockers.append("AUDIT_EVENTS_PRIMARY_KEY_DRIFTED")
    if snapshot.triggers:
        if any(trigger.name == "audit_events_append_only" for trigger in snapshot.triggers):
            blockers.append("V9_APPEND_ONLY_TRIGGER_PRESENT")
        else:
            blockers.append("AUDIT_EVENTS_UNEXPECTED_TRIGGER_PRESENT")

    if organization_column is None and len(snapshot.columns) > len(EXPECTED_BASE_COLUMNS):
        # A malformed extra column must never be treated as the absent-column path.
        blockers.append("ORGANIZATION_ID_STATE_UNKNOWN")
    if organization_column is not None:
        if snapshot.organization_non_system_exists:
            blockers.append("ORGANIZATION_ID_HAS_NON_SYSTEM_VALUE")
        if not organization_column.nullable and snapshot.organization_null_exists:
            blockers.append("ORGANIZATION_ID_NULLABILITY_CONFLICT")

    blockers = list(dict.fromkeys(blockers))
    if blockers:
        state = "BLOCKED"
    elif organization_column is not None and not organization_column.nullable:
        state = "ALREADY_PREPARED"
    else:
        state = "READY_TO_APPLY"
    return Assessment(snapshot=snapshot, state=state, blockers=tuple(blockers))


def _bool_text(value: Any) -> bool:
    return str(value).upper() in {"YES", "TRUE", "T", "1"}


def assess_database(
    cursor: Cursor,
    migrations: Sequence[MigrationSpec],
) -> Assessment:
    cursor.execute(
        """/* pre_v9_audit_bootstrap:target */
        SELECT current_database(), current_setting('server_version_num'),
               COALESCE(inet_server_addr()::text, 'local'),
               COALESCE(inet_server_port(), 0)
        """
    )
    target_row = cursor.fetchone()
    if target_row is None or len(target_row) != 4:
        raise BootstrapBlocked("DATABASE_CATALOG_RESPONSE_INVALID")
    target_material = "\0".join(str(value) for value in target_row)

    cursor.execute(
        """/* pre_v9_audit_bootstrap:table_presence */
        SELECT to_regclass('public.flyway_schema_history') IS NOT NULL,
               to_regclass('public.audit_events') IS NOT NULL
        """
    )
    presence_row = cursor.fetchone()
    if presence_row is None or len(presence_row) != 2:
        raise BootstrapBlocked("DATABASE_CATALOG_RESPONSE_INVALID")
    history_present = bool(presence_row[0])
    audit_present = bool(presence_row[1])

    history: tuple[HistoryRow, ...] = ()
    if history_present:
        cursor.execute(
            """/* pre_v9_audit_bootstrap:history */
            SELECT installed_rank, version, description, type, script, checksum, success
              FROM public.flyway_schema_history
             ORDER BY installed_rank
            """
        )
        history = tuple(
            HistoryRow(
                installed_rank=int(row[0]),
                version=None if row[1] is None else str(row[1]),
                description=str(row[2]),
                migration_type=str(row[3]),
                script=str(row[4]),
                checksum=None if row[5] is None else int(row[5]),
                success=bool(row[6]),
            )
            for row in cursor.fetchall()
        )

    columns: tuple[ColumnState, ...] = ()
    primary_key: tuple[str, ...] = ()
    triggers: tuple[TriggerState, ...] = ()
    null_exists = False
    non_system_exists = False
    if audit_present:
        cursor.execute(
            """/* pre_v9_audit_bootstrap:columns */
            SELECT ordinal_position, column_name, data_type, udt_name,
                   character_maximum_length, is_nullable, column_default,
                   is_identity, is_generated
              FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'audit_events'
             ORDER BY ordinal_position
            """
        )
        columns = tuple(
            ColumnState(
                ordinal_position=int(row[0]),
                name=str(row[1]),
                data_type=str(row[2]),
                udt_name=str(row[3]),
                maximum_length=None if row[4] is None else int(row[4]),
                nullable=_bool_text(row[5]),
                default=None if row[6] is None else str(row[6]),
                identity=_bool_text(row[7]),
                generated=str(row[8]),
            )
            for row in cursor.fetchall()
        )
        cursor.execute(
            """/* pre_v9_audit_bootstrap:primary_key */
            SELECT attribute.attname
              FROM pg_constraint constraint_row
              JOIN pg_class relation ON relation.oid = constraint_row.conrelid
              JOIN pg_namespace namespace_row ON namespace_row.oid = relation.relnamespace
              JOIN unnest(constraint_row.conkey) WITH ORDINALITY AS key(attnum, ordinality)
                ON true
              JOIN pg_attribute attribute
                ON attribute.attrelid = relation.oid AND attribute.attnum = key.attnum
             WHERE namespace_row.nspname = 'public'
               AND relation.relname = 'audit_events'
               AND constraint_row.contype = 'p'
             ORDER BY key.ordinality
            """
        )
        primary_key = tuple(str(row[0]) for row in cursor.fetchall())
        cursor.execute(
            """/* pre_v9_audit_bootstrap:triggers */
            SELECT trigger_row.tgname, function_namespace.nspname,
                   function_row.proname, pg_get_triggerdef(trigger_row.oid, true)
              FROM pg_trigger trigger_row
              JOIN pg_class relation ON relation.oid = trigger_row.tgrelid
              JOIN pg_namespace relation_namespace
                ON relation_namespace.oid = relation.relnamespace
              JOIN pg_proc function_row ON function_row.oid = trigger_row.tgfoid
              JOIN pg_namespace function_namespace
                ON function_namespace.oid = function_row.pronamespace
             WHERE relation_namespace.nspname = 'public'
               AND relation.relname = 'audit_events'
               AND NOT trigger_row.tgisinternal
             ORDER BY trigger_row.tgname
            """
        )
        triggers = tuple(
            TriggerState(str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in cursor.fetchall()
        )
        if any(column.name == "organization_id" for column in columns):
            cursor.execute(
                """/* pre_v9_audit_bootstrap:organization_values */
                SELECT EXISTS (
                           SELECT 1 FROM public.audit_events
                            WHERE organization_id IS NULL LIMIT 1
                       ),
                       EXISTS (
                           SELECT 1 FROM public.audit_events
                            WHERE organization_id IS NOT NULL
                              AND organization_id <> %s
                            LIMIT 1
                       )
                """,
                (SYSTEM_ORGANIZATION,),
            )
            organization_row = cursor.fetchone()
            if organization_row is None or len(organization_row) != 2:
                raise BootstrapBlocked("DATABASE_CATALOG_RESPONSE_INVALID")
            null_exists = bool(organization_row[0])
            non_system_exists = bool(organization_row[1])

    snapshot = CatalogSnapshot(
        target_material=target_material,
        server_version_num=str(target_row[1]),
        history_table_present=history_present,
        audit_table_present=audit_present,
        history=history,
        columns=columns,
        primary_key_columns=primary_key,
        triggers=triggers,
        organization_null_exists=null_exists,
        organization_non_system_exists=non_system_exists,
    )
    return evaluate_snapshot(snapshot, migrations)


def _target_fingerprint(snapshot: CatalogSnapshot) -> str:
    return hashlib.sha256(
        ("elmos/pre-v9-audit-bootstrap/target/v1\0" + snapshot.target_material).encode(
            "utf-8"
        )
    ).hexdigest()


def expected_confirmation(snapshot: CatalogSnapshot) -> str:
    return CONFIRMATION_PREFIX + _target_fingerprint(snapshot)


def expected_v9_source_confirmation(guard: V9SourceGuard) -> str:
    return V9_SOURCE_CONFIRMATION_PREFIX + guard.source_sha256


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assessment_summary(assessment: Assessment) -> dict[str, Any]:
    snapshot = assessment.snapshot
    history_material = [dataclasses.asdict(row) for row in snapshot.history]
    catalog_material = {
        "columns": [dataclasses.asdict(column) for column in snapshot.columns],
        "primary_key_columns": list(snapshot.primary_key_columns),
        "triggers": [dataclasses.asdict(trigger) for trigger in snapshot.triggers],
        "organization_null_exists": snapshot.organization_null_exists,
        "organization_non_system_exists": snapshot.organization_non_system_exists,
    }
    return {
        "state": assessment.state,
        "blockers": list(assessment.blockers),
        "history_sha256": _canonical_digest(history_material),
        "audit_catalog_sha256": _canonical_digest(catalog_material),
        "history_row_count": len(snapshot.history),
        "audit_column_count": len(snapshot.columns),
        "user_trigger_count": len(snapshot.triggers),
    }


def _finalize_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    finalized = dict(payload)
    finalized["receipt_payload_sha256"] = _canonical_digest(payload)
    return finalized


def _receipt(
    *,
    mode: str,
    assessment: Assessment,
    migrations: Sequence[MigrationSpec],
    v9_guard: V9SourceGuard,
    decision: str,
    mutation: Mapping[str, Any],
    now: Callable[[], dt.datetime],
) -> dict[str, Any]:
    migration_material = [dataclasses.asdict(migration) for migration in migrations]
    payload = {
        "schema_version": 1,
        "operation": "PRE_V9_AUDIT_EVENTS_TENANT_BOOTSTRAP",
        "mode": mode,
        "decision": decision,
        "generated_at": now().astimezone(dt.timezone.utc).isoformat(),
        "target": {
            "fingerprint_sha256": _target_fingerprint(assessment.snapshot),
            "server_version_num": assessment.snapshot.server_version_num,
        },
        "repository_input": {
            "migration_versions": [migration.version for migration in migrations],
            "migration_inventory_sha256": _canonical_digest(migration_material),
            "v9_hazard_source": dataclasses.asdict(v9_guard),
        },
        "assessment": _assessment_summary(assessment),
        "mutation": dict(mutation),
        "evidence_scope": "LOCAL_SELF_ATTESTED_ENGINEERING_EVIDENCE",
        "self_attested": True,
        "independently_verified": False,
        "production_certified": False,
        "certification_status": "NOT_CERTIFIED",
    }
    return _finalize_receipt(payload)


def _blocked_receipt(
    *, mode: str, blocker: str, now: Callable[[], dt.datetime]
) -> dict[str, Any]:
    return _finalize_receipt(
        {
            "schema_version": 1,
            "operation": "PRE_V9_AUDIT_EVENTS_TENANT_BOOTSTRAP",
            "mode": mode,
            "decision": "BLOCKED",
            "generated_at": now().astimezone(dt.timezone.utc).isoformat(),
            "blockers": [blocker],
            "evidence_scope": "LOCAL_SELF_ATTESTED_ENGINEERING_EVIDENCE",
            "self_attested": True,
            "independently_verified": False,
            "production_certified": False,
            "certification_status": "NOT_CERTIFIED",
        }
    )


def _default_connector(dsn: str, timeout_seconds: int) -> Connection:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError as error:
        raise BootstrapBlocked("PSYCOPG_NOT_AVAILABLE") from error
    try:
        return psycopg.connect(
            dsn,
            autocommit=True,
            connect_timeout=timeout_seconds,
            application_name="elmos-pre-v9-audit-bootstrap",
        )
    except Exception as error:
        raise BootstrapBlocked("DATABASE_CONNECTION_FAILED") from error


def perform(
    *,
    dsn: str,
    apply: bool,
    confirmation: str | None,
    v9_source_confirmation: str | None = None,
    durable_receipt_reserved: bool = False,
    migrations: Sequence[MigrationSpec],
    v9_guard: V9SourceGuard | None = None,
    connector: Connector = _default_connector,
    connect_timeout_seconds: int = 10,
    statement_timeout_ms: int = 60_000,
    lock_timeout_ms: int = 5_000,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
) -> dict[str, Any]:
    mode = "APPLY" if apply else "ASSESS"
    guarded_v9 = discover_v9_source_guard() if v9_guard is None else v9_guard
    if not dsn.strip():
        raise BootstrapBlocked("DATABASE_URL_REQUIRED")
    if apply:
        if confirmation is None or not confirmation.startswith(CONFIRMATION_PREFIX):
            raise BootstrapBlocked("APPLY_CONFIRMATION_REQUIRED")
        supplied_fingerprint = confirmation.removeprefix(CONFIRMATION_PREFIX)
        if SHA256_PATTERN.fullmatch(supplied_fingerprint) is None:
            raise BootstrapBlocked("APPLY_CONFIRMATION_INVALID")
        if v9_source_confirmation is None:
            raise BootstrapBlocked("APPLY_V9_SOURCE_CONFIRMATION_REQUIRED")
        if v9_source_confirmation != expected_v9_source_confirmation(guarded_v9):
            raise BootstrapBlocked("APPLY_V9_SOURCE_CONFIRMATION_MISMATCH")
        if not durable_receipt_reserved:
            raise BootstrapBlocked("APPLY_RECEIPT_RESERVATION_REQUIRED")

    connection: Connection | None = None
    cursor: Cursor | None = None
    transaction_open = False
    mutation_started = False
    commit_sent = False
    rollback_attempted = False
    rollback_acknowledged: bool | None = None
    assessment: Assessment | None = None
    column_added = False
    rows_bound: int | None = None

    def rollback_confirmed() -> bool:
        nonlocal transaction_open, rollback_attempted, rollback_acknowledged
        if not transaction_open or cursor is None:
            return True
        rollback_attempted = True
        try:
            cursor.execute("ROLLBACK")
            transaction_open = False
            rollback_acknowledged = True
            return True
        except Exception:
            rollback_acknowledged = False
            return False

    def unknown_outcome(failure_code: str) -> dict[str, Any]:
        if assessment is None:
            raise BootstrapBlocked(failure_code)
        return _receipt(
            mode=mode,
            assessment=assessment,
            migrations=migrations,
            v9_guard=guarded_v9,
            decision="OUTCOME_UNKNOWN",
            mutation={
                "attempted": mutation_started,
                "phase": "COMMIT_SENT" if commit_sent else "MUTATION_IN_PROGRESS",
                "failure_code": failure_code,
                "column_added": None,
                "rows_bound_to_org_system": rows_bound,
                "not_null_set": None,
                "flyway_history_modified": False,
                "rollback_attempted": rollback_attempted,
                "rollback_acknowledged": rollback_acknowledged is True,
                # A ROLLBACK response after COMMIT was sent cannot prove which command won.
                "rollback_confirmed": (
                    not commit_sent and rollback_acknowledged is True
                ),
                "database_outcome": "UNKNOWN",
                "reconciliation_required": True,
            },
            now=now,
        )
    try:
        connection = connector(dsn, connect_timeout_seconds)
        cursor = connection.cursor()
        if apply:
            cursor.execute("BEGIN ISOLATION LEVEL SERIALIZABLE READ WRITE")
        else:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        transaction_open = True
        cursor.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (f"{statement_timeout_ms}ms",),
        )
        cursor.execute(
            "SELECT set_config('lock_timeout', %s, true)",
            (f"{lock_timeout_ms}ms",),
        )
        if apply:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
            cursor.execute(
                "LOCK TABLE public.audit_events, public.flyway_schema_history "
                "IN ACCESS EXCLUSIVE MODE"
            )

        assessment = assess_database(cursor, migrations)
        if apply and confirmation != expected_confirmation(assessment.snapshot):
            raise BootstrapBlocked("APPLY_TARGET_CONFIRMATION_MISMATCH")
        if assessment.state == "BLOCKED":
            cursor.execute("ROLLBACK")
            transaction_open = False
            return _receipt(
                mode=mode,
                assessment=assessment,
                migrations=migrations,
                v9_guard=guarded_v9,
                decision="BLOCKED",
                mutation={
                    "attempted": False,
                    "column_added": False,
                    "rows_bound_to_org_system": 0,
                    "not_null_set": False,
                    "flyway_history_modified": False,
                },
                now=now,
            )

        if not apply:
            cursor.execute("ROLLBACK")
            transaction_open = False
            return _receipt(
                mode=mode,
                assessment=assessment,
                migrations=migrations,
                v9_guard=guarded_v9,
                decision=assessment.state,
                mutation={
                    "attempted": False,
                    "column_added": False,
                    "rows_bound_to_org_system": 0,
                    "not_null_set": False,
                    "flyway_history_modified": False,
                },
                now=now,
            )

        if assessment.state == "ALREADY_PREPARED":
            commit_sent = True
            cursor.execute("COMMIT")
            transaction_open = False
            return _receipt(
                mode=mode,
                assessment=assessment,
                migrations=migrations,
                v9_guard=guarded_v9,
                decision="ALREADY_PREPARED",
                mutation={
                    "attempted": False,
                    "column_added": False,
                    "rows_bound_to_org_system": 0,
                    "not_null_set": False,
                    "flyway_history_modified": False,
                },
                now=now,
            )

        column_added = len(assessment.snapshot.columns) == len(EXPECTED_BASE_COLUMNS)
        mutation_started = True
        if column_added:
            cursor.execute(
                "ALTER TABLE public.audit_events "
                "ADD COLUMN organization_id varchar(96)"
            )
        cursor.execute(
            "UPDATE public.audit_events SET organization_id = %s "
            "WHERE organization_id IS NULL",
            (SYSTEM_ORGANIZATION,),
        )
        rows_bound = int(cursor.rowcount)
        cursor.execute(
            "ALTER TABLE public.audit_events "
            "ALTER COLUMN organization_id SET NOT NULL"
        )

        post_assessment = assess_database(cursor, migrations)
        if post_assessment.state != "ALREADY_PREPARED":
            raise BootstrapBlocked("POST_APPLY_RECONCILIATION_FAILED")
        commit_sent = True
        cursor.execute("COMMIT")
        transaction_open = False
        return _receipt(
            mode=mode,
            assessment=post_assessment,
            migrations=migrations,
            v9_guard=guarded_v9,
            decision="APPLIED",
            mutation={
                "attempted": True,
                "column_added": column_added,
                "rows_bound_to_org_system": rows_bound,
                "not_null_set": True,
                "flyway_history_modified": False,
            },
            now=now,
        )
    except BootstrapBlocked as error:
        if commit_sent:
            rollback_confirmed()
            return unknown_outcome(error.code)
        if mutation_started:
            if not rollback_confirmed():
                return unknown_outcome(error.code)
        else:
            rollback_confirmed()
        raise
    except Exception as error:
        if commit_sent:
            rollback_confirmed()
            return unknown_outcome("DATABASE_OPERATION_FAILED")
        if mutation_started:
            if not rollback_confirmed():
                return unknown_outcome("DATABASE_OPERATION_FAILED")
        else:
            rollback_confirmed()
        raise BootstrapBlocked("DATABASE_OPERATION_FAILED") from error
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    if path.is_symlink():
        raise BootstrapBlocked("RECEIPT_PATH_SYMLINK_REJECTED")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise BootstrapBlocked("RECEIPT_PATH_ALREADY_EXISTS")
    encoded = (
        json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        # Publish with an exclusive hard link instead of os.replace(): a receipt is append-only
        # evidence and a target created after the preflight check must never be overwritten.
        os.link(temporary_path, path, follow_symlinks=False)
        temporary_path.unlink()
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def reserve_apply_receipt(
    path: Path, now: Callable[[], dt.datetime]
) -> ReceiptReservation:
    """Exclusively publishes a durable PENDING marker before any database write."""
    if path.is_symlink():
        raise BootstrapBlocked("RECEIPT_PATH_SYMLINK_REJECTED")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise BootstrapBlocked("RECEIPT_PATH_ALREADY_EXISTS") from error
    except OSError as error:
        raise BootstrapBlocked("RECEIPT_RESERVATION_FAILED") from error
    reserved_state: os.stat_result | None = None
    try:
        reserved_state = os.fstat(descriptor)
        reservation_id = os.urandom(16).hex()
        pending = _finalize_receipt(
            {
                "schema_version": 1,
                "operation": "PRE_V9_AUDIT_EVENTS_TENANT_BOOTSTRAP",
                "mode": "APPLY",
                "decision": "OUTCOME_UNKNOWN",
                "generated_at": now().astimezone(dt.timezone.utc).isoformat(),
                "receipt_publication": {
                    "status": "RECONCILIATION_REQUIRED_UNTIL_FINALIZED",
                    "reservation_id": reservation_id,
                    "database_decision": "UNKNOWN",
                },
                "evidence_scope": "LOCAL_SELF_ATTESTED_ENGINEERING_EVIDENCE",
                "self_attested": True,
                "independently_verified": False,
                "production_certified": False,
                "certification_status": "NOT_CERTIFIED",
            }
        )
        encoded = (
            json.dumps(pending, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
        ).encode("utf-8")
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        _fsync_directory(path.parent)
        return ReceiptReservation(
            path, reserved_state.st_dev, reserved_state.st_ino
        )
    except Exception as error:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            current = path.stat(follow_symlinks=False)
            if reserved_state is not None and (current.st_dev, current.st_ino) == (
                reserved_state.st_dev,
                reserved_state.st_ino,
            ):
                path.unlink(missing_ok=True)
        except OSError:
            pass
        raise BootstrapBlocked("RECEIPT_RESERVATION_FAILED") from error


def publish_reserved_receipt(
    reservation: ReceiptReservation, receipt: Mapping[str, Any]
) -> None:
    current = reservation.path.stat(follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (reservation.device, reservation.inode):
        raise BootstrapBlocked("RECEIPT_RESERVATION_REPLACED")
    encoded = (
        json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{reservation.path.name}.",
        suffix=".tmp",
        dir=reservation.path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        current = reservation.path.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (reservation.device, reservation.inode):
            raise BootstrapBlocked("RECEIPT_RESERVATION_REPLACED")
        os.replace(temporary_path, reservation.path)
        _fsync_directory(reservation.path.parent)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _receipt_publication_failed(receipt: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(receipt)
    payload.pop("receipt_payload_sha256", None)
    payload["receipt_publication"] = {
        "status": "RECONCILIATION_REQUIRED",
        "durable_file_updated": False,
        "database_decision_preserved": payload.get("decision", "UNKNOWN"),
    }
    return _finalize_receipt(payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assess or apply the exact pre-V9 audit_events tenant bootstrap."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Enable the guarded write path; default is read-only assessment.",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Atomic JSON receipt path; required before --apply may connect.",
    )
    parser.add_argument("--database-url-env", default=DATABASE_URL_ENV)
    parser.add_argument("--confirmation-env", default=CONFIRMATION_ENV)
    parser.add_argument(
        "--v9-source-confirmation-env", default=V9_SOURCE_CONFIRMATION_ENV
    )
    parser.add_argument("--connect-timeout-seconds", type=int, default=10)
    parser.add_argument("--statement-timeout-ms", type=int, default=60_000)
    parser.add_argument("--lock-timeout-ms", type=int, default=5_000)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    connector: Connector = _default_connector,
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
) -> int:
    arguments = _parser().parse_args(argv)
    environment = os.environ if environ is None else environ
    mode = "APPLY" if arguments.apply else "ASSESS"
    receipt: dict[str, Any]
    exit_code = 0
    reservation: ReceiptReservation | None = None
    receipt_preflight_failed = False
    try:
        if ENVIRONMENT_NAME_PATTERN.fullmatch(arguments.database_url_env) is None:
            raise BootstrapBlocked("DATABASE_URL_ENV_NAME_INVALID")
        if ENVIRONMENT_NAME_PATTERN.fullmatch(arguments.confirmation_env) is None:
            raise BootstrapBlocked("CONFIRMATION_ENV_NAME_INVALID")
        if (
            ENVIRONMENT_NAME_PATTERN.fullmatch(
                arguments.v9_source_confirmation_env
            )
            is None
        ):
            raise BootstrapBlocked("V9_SOURCE_CONFIRMATION_ENV_NAME_INVALID")
        if not 1 <= arguments.connect_timeout_seconds <= 60:
            raise BootstrapBlocked("CONNECT_TIMEOUT_INVALID")
        if not 1_000 <= arguments.statement_timeout_ms <= 300_000:
            raise BootstrapBlocked("STATEMENT_TIMEOUT_INVALID")
        if not 100 <= arguments.lock_timeout_ms <= 60_000:
            raise BootstrapBlocked("LOCK_TIMEOUT_INVALID")
        if arguments.apply and arguments.receipt is None:
            raise BootstrapBlocked("APPLY_RECEIPT_REQUIRED")
        migrations = discover_expected_migrations()
        v9_guard = discover_v9_source_guard()
        if arguments.apply:
            assert arguments.receipt is not None
            reservation = reserve_apply_receipt(arguments.receipt, now)
        receipt = perform(
            dsn=environment.get(arguments.database_url_env, ""),
            apply=arguments.apply,
            confirmation=environment.get(arguments.confirmation_env),
            v9_source_confirmation=environment.get(
                arguments.v9_source_confirmation_env
            ),
            durable_receipt_reserved=reservation is not None,
            migrations=migrations,
            v9_guard=v9_guard,
            connector=connector,
            connect_timeout_seconds=arguments.connect_timeout_seconds,
            statement_timeout_ms=arguments.statement_timeout_ms,
            lock_timeout_ms=arguments.lock_timeout_ms,
            now=now,
        )
        if receipt["decision"] == "BLOCKED":
            exit_code = 2
        elif receipt["decision"] == "OUTCOME_UNKNOWN":
            exit_code = 3
    except BootstrapBlocked as error:
        receipt_preflight_failed = (
            reservation is None and error.code.startswith("RECEIPT_")
        )
        receipt = _blocked_receipt(mode=mode, blocker=error.code, now=now)
        exit_code = 2
    except Exception:
        receipt = _blocked_receipt(
            mode=mode, blocker="UNEXPECTED_OPERATION_FAILURE", now=now
        )
        exit_code = 2

    if arguments.receipt is not None and not receipt_preflight_failed:
        try:
            if reservation is not None:
                publish_reserved_receipt(reservation, receipt)
            else:
                write_receipt(arguments.receipt, receipt)
        except Exception:
            # A failed durable publication after COMMIT must not rewrite APPLIED into BLOCKED.
            # The pre-commit PENDING marker remains on disk and stdout carries the exact database
            # decision plus an explicit reconciliation requirement.
            receipt = _receipt_publication_failed(receipt)
            exit_code = 3
    print(json.dumps(receipt, sort_keys=True, ensure_ascii=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
