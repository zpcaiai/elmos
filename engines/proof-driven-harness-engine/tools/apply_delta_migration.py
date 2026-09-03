#!/usr/bin/env python3
"""Apply the repository-authored V304 delta with exact PostgreSQL 17 guards.

The deployment-owner DSN is accepted only through a named environment
variable, keeping credentials out of process arguments. The SQL file is read
once through a no-follow descriptor, bounded, digest-checked, and executed in
one transaction under an advisory lock. The exact V001 ledger is a mandatory
prerequisite. No application, scheduler, worker, verifier, or certifier role
can stand in for the dedicated NOLOGIN migration owner.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any


MAX_MIGRATION_BYTES = 8 * 1024 * 1024
MIGRATION_NAME = "V304__harness_runtime_assurance_delta.sql"
SCHEMA_VERSION = 304
PACKAGE_VERSION = "3.1.0"
BASE_MIGRATION_NAME = "V001__proof_harness_core.sql"
BASE_SCHEMA_VERSION = 1
BASE_SOURCE_DIGEST = (
    "sha256:bdddb1ff1a962df931df57e4d8d428e08c232b4ac88e5189bf8c2ccde34e388f"
)
EXPECTED_SOURCE_DIGEST = (
    "sha256:e723bc02c28bd0580c56e8b9cf1ba63ed5c81fff258671f45e7af774cdf57ef2"
)
DELTA_RLS_CANONICAL_EXPRESSION = (
    "tenant_id=proof_harness.current_tenant_keyAND"
    "project_id=proof_harness.current_project_keyAND"
    "actor_id=current_setting'app.actor_id',trueAND"
    "run_id=current_setting'app.run_id',trueAND"
    "execution_epoch=current_setting'app.execution_epoch',trueAND"
    "fencing_generation=current_setting'app.fencing_generation',trueAND"
    "authority_revision=current_setting'app.authority_revision',trueAND"
    "revision_set_id=current_setting'app.revision_set_id',true"
)
PSYCOPG_VERSION = "3.2.13"
ADVISORY_LOCK_KEY = 0x454C4D4F53563331

METADATA_RELATION = "proof_harness_runtime.runtime_assurance_migrations"
LEDGER_RELATION = "proof_harness_runtime.runtime_assurance_migration_digest_ledger"
DELTA_RELATIONS = (
    "proof_harness_runtime.tool_result_commits",
    "proof_harness_runtime.step_execution_plans",
    "proof_harness_runtime.step_plan_tool_bindings",
    "proof_harness_runtime.pending_tool_call_bindings",
    "proof_harness_runtime.runtime_authority_capability_receipts",
    "proof_harness_runtime.subagent_budget_reservation_bindings",
    "proof_harness_runtime.capability_leases",
    "proof_harness_runtime.executor_generations",
    "proof_harness_runtime.environment_attachments",
    "proof_harness_runtime.executor_replacement_effects",
    "proof_harness_runtime.workspace_leases",
    "proof_harness_runtime.durable_event_registrations",
    "proof_harness_runtime.durable_event_instances",
    "proof_harness_runtime.typed_ingress_records",
    "proof_harness_runtime.subagent_execution_specs",
    "proof_harness_runtime.runtime_assurance_invocation_receipts",
)
SUPPORT_RELATIONS = (
    "proof_harness_runtime.typed_ingress_records_persisted_sequence_seq",
)
CONTROL_FUNCTIONS = (
    "is_bounded_text_array",
    "is_valid_interceptor_chain",
    "is_valid_workspace_scopes",
    "canonical_jsonb_text",
    "append_runtime_assurance_event",
    "runtime_assurance_event_is_exact",
    "is_live_runtime_assurance_claim",
    "assert_runtime_application_writer",
    "guard_runtime_run_actor_identity",
    "assert_runtime_assurance_scope",
    "claim_runtime_assurance_invocation",
    "complete_runtime_assurance_invocation",
    "reconcile_runtime_assurance_invocation",
    "guard_tool_result_commit",
    "guard_step_execution_plan",
    "guard_step_plan_tool_binding",
    "guard_runtime_authority_capability_receipt",
    "guard_pending_tool_call_binding",
    "guard_subagent_budget_reservation",
    "guard_capability_lease",
    "guard_executor_generation",
    "guard_environment_attachment",
    "guard_executor_replacement_effect",
    "guard_workspace_lease",
    "guard_runtime_assurance_invocation_receipt",
    "guard_durable_event_instance",
    "guard_subagent_execution_spec",
    "consume_subagent_reservation_and_spec",
)
CONTROL_TRIGGERS = (
    "tool_result_commits_scope_guard",
    "step_execution_plans_scope_guard",
    "step_plan_tool_bindings_scope_guard",
    "pending_tool_call_bindings_scope_guard",
    "runtime_authority_capability_receipts_scope_guard",
    "subagent_budget_reservation_bindings_scope_guard",
    "capability_leases_scope_guard",
    "executor_generations_scope_guard",
    "environment_attachments_scope_guard",
    "executor_replacement_effects_scope_guard",
    "workspace_leases_scope_guard",
    "durable_event_registrations_scope_guard",
    "durable_event_instances_scope_guard",
    "typed_ingress_records_scope_guard",
    "subagent_execution_specs_scope_guard",
    "runtime_assurance_invocation_receipts_scope_guard",
    "tool_result_commits_lifecycle_guard",
    "step_execution_plans_lifecycle_guard",
    "step_plan_tool_bindings_immutable",
    "pending_tool_call_bindings_lifecycle_guard",
    "runtime_authority_capability_receipts_immutable",
    "subagent_budget_reservation_bindings_lifecycle_guard",
    "capability_leases_lifecycle_guard",
    "executor_generations_lifecycle_guard",
    "environment_attachments_lifecycle_guard",
    "executor_replacement_effects_lifecycle_guard",
    "workspace_leases_lifecycle_guard",
    "durable_event_registrations_immutable",
    "durable_event_instances_lifecycle_guard",
    "typed_ingress_records_immutable",
    "subagent_execution_specs_lifecycle_guard",
    "runtime_assurance_invocation_receipts_lifecycle_guard",
)
CONTROL_INDEXES = (
    "capability_leases_active_invocation_idx",
    "step_execution_plans_one_active_scope",
    "pending_tool_call_bindings_state_idx",
    "executor_generations_one_active_environment",
    "environment_attachments_one_active",
    "workspace_leases_one_active_owner",
    "workspace_leases_one_live_repository_base",
    "tool_result_commits_run_idx",
    "step_execution_plans_run_state_idx",
    "capability_leases_expiry_idx",
    "durable_event_registrations_type_idx",
    "durable_event_instances_correlation_idx",
    "typed_ingress_records_dedup_unique",
    "subagent_execution_specs_budget_unique",
    "typed_ingress_records_run_idx",
    "typed_ingress_records_correlation_page_idx",
    "subagent_execution_specs_run_idx",
    "runtime_assurance_invocation_receipts_state_idx",
)
RESERVED_ROLE_TOKENS = {
    "app",
    "application",
    "certifier",
    "runtime",
    "scheduler",
    "verifier",
    "worker",
}

_CATALOG_FINGERPRINT_SQL = """
WITH target_relations AS (
  SELECT c.oid,c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity,
         pg_get_userbyid(c.relowner) AS owner_name
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='proof_harness_runtime' AND c.relname=ANY(%s)
), target_functions AS (
  SELECT p.oid,p.proname,p.provolatile,p.proisstrict,p.prosecdef,p.proleakproof,
         p.proparallel,p.proconfig,l.lanname,
         pg_get_userbyid(p.proowner) AS owner_name
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  JOIN pg_language l ON l.oid=p.prolang
  WHERE n.nspname='proof_harness_runtime' AND p.proname=ANY(%s)
)
SELECT jsonb_build_object(
  'relations',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(relname,relkind,relrowsecurity,
                                      relforcerowsecurity,owner_name) ORDER BY relname)
    FROM target_relations
  ),'[]'::jsonb),
  'columns',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(r.relname,a.attnum,a.attname,
             format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,
             a.attgenerated,COALESCE(pg_get_expr(d.adbin,d.adrelid,true),''),
             COALESCE(coll.collname,'')) ORDER BY r.relname,a.attnum)
    FROM target_relations r JOIN pg_attribute a ON a.attrelid=r.oid
    LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
    LEFT JOIN pg_collation coll ON coll.oid=a.attcollation
    WHERE a.attnum>0 AND NOT a.attisdropped
  ),'[]'::jsonb),
  'constraints',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(r.relname,con.conname,con.contype,
             con.convalidated,con.condeferrable,con.condeferred,
             pg_get_constraintdef(con.oid,true)) ORDER BY r.relname,con.conname)
    FROM target_relations r JOIN pg_constraint con ON con.conrelid=r.oid
  ),'[]'::jsonb),
  'functions',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(f.proname,
             pg_get_function_identity_arguments(f.oid),
             pg_get_function_result(f.oid),f.lanname,f.provolatile,f.proisstrict,
             f.prosecdef,f.proleakproof,f.proparallel,COALESCE(f.proconfig,ARRAY[]::text[]),
             f.owner_name,
             pg_get_functiondef(f.oid)) ORDER BY f.proname,f.oid)
    FROM target_functions f
  ),'[]'::jsonb),
  'triggers',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(r.relname,t.tgname,t.tgenabled,
             pg_get_triggerdef(t.oid,true)) ORDER BY r.relname,t.tgname)
    FROM target_relations r JOIN pg_trigger t ON t.tgrelid=r.oid
    WHERE NOT t.tgisinternal
  ),'[]'::jsonb),
  'indexes',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(r.relname,i.relname,x.indisprimary,
             x.indisunique,x.indisvalid,x.indisready,pg_get_indexdef(i.oid))
             ORDER BY r.relname,i.relname)
    FROM target_relations r JOIN pg_index x ON x.indrelid=r.oid
    JOIN pg_class i ON i.oid=x.indexrelid
  ),'[]'::jsonb),
  'policies',COALESCE((
    SELECT jsonb_agg(jsonb_build_array(p.tablename,p.policyname,p.permissive,
             p.roles,p.cmd,p.qual,p.with_check) ORDER BY p.tablename,p.policyname)
    FROM pg_policies p
    WHERE p.schemaname='proof_harness_runtime' AND p.tablename=ANY(%s)
  ),'[]'::jsonb)
) AS catalog
"""
_CATALOG_FINGERPRINT_KEYS = frozenset(
    {"relations", "columns", "constraints", "functions", "triggers", "indexes", "policies"}
)


class MigrationRejected(RuntimeError):
    """Fail-closed validation error safe to expose without the configured DSN."""


def _digest_bytes(content: bytes) -> str:
    prefix = b"elmos.proof-harness.v3.1\x00postgres-migration-file\x00"
    return "sha256:" + hashlib.sha256(prefix + content).hexdigest()


def _read_once(path: Path) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise MigrationRejected("platform cannot enforce no-follow migration reads")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MigrationRejected("migration source could not be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MigrationRejected("migration source is not a regular file")
        if metadata.st_size < 1 or metadata.st_size > MAX_MIGRATION_BYTES:
            raise MigrationRejected(
                "migration source size is outside the allowed bound"
            )
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise MigrationRejected(
                    "migration source changed during its single-FD read"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise MigrationRejected("migration source grew during its single-FD read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _validate_owner_role(role: str) -> None:
    normalized = role.strip()
    if normalized != role or not 1 <= len(normalized) <= 63:
        raise MigrationRejected(
            "expected owner role must be an exact PostgreSQL identifier"
        )
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", normalized):
        raise MigrationRejected(
            "expected owner role must be an unquoted PostgreSQL identifier"
        )
    tokens = set(filter(None, re.split(r"[^a-z0-9]+", normalized.casefold())))
    if tokens & RESERVED_ROLE_TOKENS:
        raise MigrationRejected(
            "expected owner role is reserved for a non-owner service role"
        )


def _migration_sql(path: Path) -> tuple[str, str]:
    if path.name != MIGRATION_NAME:
        raise MigrationRejected(f"only {MIGRATION_NAME} may be applied by this tool")
    source = _read_once(path)
    source_digest = _digest_bytes(source)
    if not hmac.compare_digest(source_digest, EXPECTED_SOURCE_DIGEST):
        raise MigrationRejected(
            "migration source digest does not match the packaged constant"
        )
    try:
        sql = source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MigrationRejected("migration source is not strict UTF-8") from exc
    if re.search(r"(?im)^\s*(BEGIN|COMMIT|ROLLBACK)\s*;", sql):
        raise MigrationRejected(
            "migration source must not control the applicator transaction"
        )
    return sql, source_digest


def _load_driver() -> Any:
    try:
        psycopg = importlib.import_module("psycopg")
    except ImportError as exc:
        raise MigrationRejected(
            f"psycopg[binary]=={PSYCOPG_VERSION} is not installed"
        ) from exc
    if str(getattr(psycopg, "__version__", "")) != PSYCOPG_VERSION:
        raise MigrationRejected(
            f"migration applicator requires psycopg {PSYCOPG_VERSION} exactly"
        )
    return psycopg


def _relation_state(cursor: Any) -> tuple[Any, ...]:
    names = (
        METADATA_RELATION,
        LEDGER_RELATION,
        *DELTA_RELATIONS,
        *SUPPORT_RELATIONS,
    )
    cursor.execute(
        "SELECT " + ",".join("to_regclass(%s)" for _ in names),
        names,
    )
    row = cursor.fetchone()
    if row is None or len(row) != len(names):
        raise MigrationRejected("database returned an invalid relation inventory")
    return tuple(row)


def _catalog_fingerprint(cursor: Any) -> str:
    relation_names = [
        METADATA_RELATION.rsplit(".", 1)[1],
        LEDGER_RELATION.rsplit(".", 1)[1],
        *(name.rsplit(".", 1)[1] for name in DELTA_RELATIONS),
    ]
    # PostgreSQL deparser functions such as pg_get_constraintdef() omit schema
    # qualification for objects visible through the caller's search_path.
    # Pin the path before hashing so the deployment owner and application
    # readiness probe observe the same catalog bytes for the same controls.
    # This is the terminal catalog operation on both applicator paths.
    cursor.execute("SET LOCAL search_path = pg_catalog")
    cursor.execute(
        _CATALOG_FINGERPRINT_SQL,
        (
            relation_names,
            list(CONTROL_FUNCTIONS),
            relation_names,
        ),
    )
    row = cursor.fetchone()
    if row is None or len(row) != 1:
        raise MigrationRejected("database returned an invalid control catalog")
    candidate = row[0]
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise MigrationRejected("control catalog is not canonical JSON") from exc
    if not isinstance(candidate, dict) or set(candidate) != _CATALOG_FINGERPRINT_KEYS:
        raise MigrationRejected("control catalog has an invalid shape")
    if any(not isinstance(candidate[key], list) for key in _CATALOG_FINGERPRINT_KEYS):
        raise MigrationRejected("control catalog collections are not arrays")
    if (
        len(candidate["relations"]) != len(relation_names)
        or len(candidate["functions"]) != len(CONTROL_FUNCTIONS)
        or len(candidate["triggers"]) != len(CONTROL_TRIGGERS)
        or len(candidate["indexes"]) < len(CONTROL_INDEXES)
        or len(candidate["policies"]) != len(DELTA_RELATIONS)
        or not candidate["columns"]
        or not candidate["constraints"]
    ):
        raise MigrationRejected("control catalog inventory is incomplete")
    encoded = json.dumps(
        candidate,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(
        b"elmos.proof-harness.v3.1\0postgres-control-catalog\0" + encoded
    ).hexdigest()


def _verify_database_authority(
    cursor: Any,
    expected_owner_role: str,
) -> tuple[str, bool]:
    cursor.execute("SELECT current_setting('server_version_num')::integer")
    version_row = cursor.fetchone()
    if version_row is None or not 170000 <= int(version_row[0]) < 180000:
        raise MigrationRejected("migration applicator requires PostgreSQL 17 exactly")

    cursor.execute(
        "SELECT current_user,session_user,r.rolsuper,r.rolbypassrls,r.rolcreatedb,"
        "r.rolcreaterole,r.rolcanlogin,r.rolreplication,"
        "has_database_privilege(current_user,current_database(),'CREATE'),"
        "pg_has_role(session_user,current_user,'SET') "
        "FROM pg_roles r WHERE r.rolname=current_user"
    )
    row = cursor.fetchone()
    if row is None:
        raise MigrationRejected("connected migration owner role is not visible")
    (
        role_name,
        session_role,
        superuser,
        bypass_rls,
        create_database,
        create_role,
        can_login,
        replication,
        can_create_schema,
        session_can_set_role,
    ) = row
    if role_name != expected_owner_role:
        raise MigrationRejected(
            "connected role does not match the exact migration owner"
        )
    if role_name == session_role or can_login or not session_can_set_role:
        raise MigrationRejected(
            "migration owner must be a NOLOGIN role assumed by an authorized session"
        )
    if superuser or bypass_rls or create_database or create_role or replication:
        raise MigrationRejected(
            "migration owner has forbidden administrative capabilities"
        )
    return str(role_name), bool(can_create_schema)


def _verify_base(cursor: Any) -> None:
    cursor.execute(
        "SELECT to_regclass('proof_harness_runtime.schema_migrations'),"
        "to_regclass('proof_harness_runtime.migration_digest_ledger'),"
        "to_regclass('proof_harness_runtime.projects'),"
        "to_regclass('proof_harness_runtime.actors'),"
        "to_regclass('proof_harness_runtime.runs')"
    )
    relation_row = cursor.fetchone()
    if relation_row is None or any(value is None for value in relation_row):
        raise MigrationRejected("complete V001 base relations are required")
    cursor.execute(
        "SELECT count(*)=2 AND bool_and(pg_get_userbyid(nspowner)=current_user) "
        "FROM pg_namespace "
        "WHERE nspname IN ('proof_harness','proof_harness_runtime')"
    )
    owner_row = cursor.fetchone()
    if owner_row is None or owner_row[0] is not True:
        raise MigrationRejected("migration owner must own both V001 schemas")
    cursor.execute(
        "SELECT m.migration_name,l.content_sha256 "
        "FROM proof_harness_runtime.schema_migrations m "
        "JOIN proof_harness_runtime.migration_digest_ledger l "
        "ON l.version=m.version AND l.migration_name=m.migration_name "
        "WHERE m.version=%s AND m.migration_name=%s",
        (BASE_SCHEMA_VERSION, BASE_MIGRATION_NAME),
    )
    row = cursor.fetchone()
    if row is None or row[0] != BASE_MIGRATION_NAME:
        raise MigrationRejected("exact V001 base migration record is missing")
    if not hmac.compare_digest(str(row[1]), BASE_SOURCE_DIGEST):
        raise MigrationRejected("V001 base migration digest mismatch")


def _verify_installed_controls(cursor: Any) -> str:
    relation_names = [name.rsplit(".", 1)[1] for name in DELTA_RELATIONS]
    cursor.execute(
        "SELECT "
        "(SELECT count(*)=%s AND bool_and(c.relkind IN ('r','p') "
        "AND c.relrowsecurity AND c.relforcerowsecurity "
        "AND pg_get_userbyid(c.relowner)=current_user) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='proof_harness_runtime' AND c.relname=ANY(%s)) "
        "AND (SELECT count(*)=%s "
        "AND bool_and(pg_get_userbyid(p.proowner)=current_user) "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='proof_harness_runtime' AND p.proname=ANY(%s)) "
        "AND (SELECT count(*)=%s AND bool_and(t.tgenabled<>'D') "
        "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='proof_harness_runtime' AND NOT t.tgisinternal "
        "AND t.tgname=ANY(%s)) "
        "AND (SELECT count(*)=%s AND bool_and("
        "policyname='runtime_assurance_trusted_scope_isolation' "
        "AND permissive='PERMISSIVE' AND cmd='ALL' "
        "AND roles=ARRAY['public']::name[] "
        "AND regexp_replace(regexp_replace(qual,'[[:space:]()]','','g'),"
        "'::text','','g')=%s "
        "AND regexp_replace(regexp_replace(with_check,'[[:space:]()]','','g'),"
        "'::text','','g')=%s) "
        "FROM pg_policies "
        "WHERE schemaname='proof_harness_runtime' "
        "AND tablename=ANY(%s)) "
        "AND (SELECT count(*)=%s AND bool_and(pg_get_userbyid(c.relowner)=current_user) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='proof_harness_runtime' AND c.relkind='i' "
        "AND c.relname=ANY(%s)) "
        "AND (SELECT count(*)=%s AND bool_and(c.relkind='S' "
        "AND pg_get_userbyid(c.relowner)=current_user) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='proof_harness_runtime' AND c.relname=ANY(%s))",
        (
            len(relation_names),
            relation_names,
            len(CONTROL_FUNCTIONS),
            list(CONTROL_FUNCTIONS),
            len(CONTROL_TRIGGERS),
            list(CONTROL_TRIGGERS),
            len(relation_names),
            DELTA_RLS_CANONICAL_EXPRESSION,
            DELTA_RLS_CANONICAL_EXPRESSION,
            relation_names,
            len(CONTROL_INDEXES),
            list(CONTROL_INDEXES),
            len(SUPPORT_RELATIONS),
            [name.rsplit(".", 1)[1] for name in SUPPORT_RELATIONS],
        ),
    )
    row = cursor.fetchone()
    if row is None or row[0] is not True:
        raise MigrationRejected(
            "runtime-assurance controls are incomplete or not owner-bound"
        )
    return _catalog_fingerprint(cursor)


def _already_applied(cursor: Any, source_digest: str) -> bool:
    relations = _relation_state(cursor)
    if all(value is None for value in relations):
        return False
    if any(value is None for value in relations):
        raise MigrationRejected("partial runtime-assurance schema exists")
    cursor.execute(
        "SELECT m.package_version,m.required_base_version,m.required_base_sha256,"
        "m.control_fingerprint_sha256,l.content_sha256 "
        f"FROM {METADATA_RELATION} m JOIN {LEDGER_RELATION} l "
        "ON l.version=m.version AND l.migration_name=m.migration_name "
        "WHERE m.version=%s AND m.migration_name=%s",
        (SCHEMA_VERSION, MIGRATION_NAME),
    )
    row = cursor.fetchone()
    if row is None:
        raise MigrationRejected(
            "runtime-assurance schema exists without its exact ledger entry"
        )
    (
        package_version,
        base_version,
        base_digest,
        stored_control_fingerprint,
        installed_digest,
    ) = row
    if package_version != PACKAGE_VERSION or int(base_version) != BASE_SCHEMA_VERSION:
        raise MigrationRejected(
            "installed runtime-assurance migration metadata conflicts"
        )
    if not hmac.compare_digest(str(base_digest), BASE_SOURCE_DIGEST):
        raise MigrationRejected("installed runtime-assurance base binding conflicts")
    if not hmac.compare_digest(str(installed_digest), source_digest):
        raise MigrationRejected("installed runtime-assurance source digest conflicts")
    observed_control_fingerprint = _verify_installed_controls(cursor)
    if (
        not isinstance(stored_control_fingerprint, str)
        or not hmac.compare_digest(
            stored_control_fingerprint,
            observed_control_fingerprint,
        )
    ):
        raise MigrationRejected(
            "runtime-assurance control catalog fingerprint conflicts"
        )
    return True


def apply(
    *, dsn: str, expected_owner_role: str, migration_path: Path
) -> dict[str, Any]:
    if not dsn.strip():
        raise MigrationRejected("migration-owner DSN is not configured")
    _validate_owner_role(expected_owner_role)
    sql, source_digest = _migration_sql(migration_path)
    psycopg = _load_driver()

    try:
        with psycopg.connect(dsn, autocommit=False) as connection:
            with connection.cursor() as cursor:
                role_name, can_create_schema = _verify_database_authority(
                    cursor,
                    expected_owner_role,
                )
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
                _verify_base(cursor)
                if _already_applied(cursor, source_digest):
                    connection.rollback()
                    return {
                        "baseContentSha256": BASE_SOURCE_DIGEST,
                        "contentSha256": source_digest,
                        "migration": MIGRATION_NAME,
                        "ownerRole": role_name,
                        "status": "ALREADY_APPLIED",
                        "version": SCHEMA_VERSION,
                    }
                if not can_create_schema:
                    raise MigrationRejected(
                        "migration owner lacks database CREATE authority for initial apply"
                    )
                cursor.execute(sql)
                control_fingerprint = _verify_installed_controls(cursor)
                cursor.execute(
                    f"UPDATE {METADATA_RELATION} "
                    "SET control_fingerprint_sha256=%s "
                    "WHERE version=%s AND migration_name=%s "
                    "AND control_fingerprint_sha256 IS NULL",
                    (
                        control_fingerprint,
                        SCHEMA_VERSION,
                        MIGRATION_NAME,
                    ),
                )
                if cursor.rowcount != 1:
                    raise MigrationRejected(
                        "runtime-assurance control fingerprint could not be pinned"
                    )
                cursor.execute(
                    f"INSERT INTO {LEDGER_RELATION}("
                    "version,migration_name,content_sha256,recorded_by) "
                    "VALUES (%s,%s,%s,current_user)",
                    (SCHEMA_VERSION, MIGRATION_NAME, source_digest),
                )
            connection.commit()
    except MigrationRejected:
        raise
    except Exception as exc:
        raise MigrationRejected(
            "database connection or migration transaction failed"
        ) from exc

    return {
        "baseContentSha256": BASE_SOURCE_DIGEST,
        "contentSha256": source_digest,
        "migration": MIGRATION_NAME,
        "ownerRole": expected_owner_role,
        "status": "APPLIED",
        "version": SCHEMA_VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    default_migration = (
        Path(__file__).resolve().parents[1] / "migrations" / MIGRATION_NAME
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-env", default="ELMOS_DELTA_MIGRATION_OWNER_DSN")
    parser.add_argument("--expected-owner-role", required=True)
    parser.add_argument("--migration", type=Path, default=default_migration)
    arguments = parser.parse_args(argv)
    try:
        result = apply(
            dsn=os.environ.get(arguments.dsn_env, ""),
            expected_owner_role=arguments.expected_owner_role,
            migration_path=arguments.migration,
        )
    except MigrationRejected as exc:
        print(
            json.dumps(
                {"code": "MIGRATION_REJECTED", "reason": str(exc), "status": "FAILED"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
