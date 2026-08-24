#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf '%s\n' "control-plane runtime role blocked: $1" >&2
  exit 1
}

required() {
  local name="$1"
  test -n "${!name:-}" || fail "$name is required"
}

required ELMOS_DATABASE_URL
required ELMOS_DATABASE_MIGRATION_USER
required ELMOS_DATABASE_MIGRATION_PASSWORD
required ELMOS_DATABASE_RUNTIME_USER

command -v psql >/dev/null || fail "psql is required"
runtime_role="$ELMOS_DATABASE_RUNTIME_USER"
[[ "$runtime_role" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] \
  || fail "runtime role name is invalid"
test "$runtime_role" != "$ELMOS_DATABASE_MIGRATION_USER" \
  || fail "runtime and migration roles must be different"

psql_url="${ELMOS_DATABASE_URL#jdbc:}"
export PGPASSWORD="$ELMOS_DATABASE_MIGRATION_PASSWORD"

role_state="$(psql "$psql_url" \
  --username "$ELMOS_DATABASE_MIGRATION_USER" \
  --no-psqlrc --tuples-only --no-align --set ON_ERROR_STOP=1 \
  --command "select case when not rolsuper and not rolbypassrls and rolcanlogin and not rolinherit and not rolcreatedb and not rolcreaterole and not rolreplication then 'ok' else 'bad' end from pg_roles where rolname = '$runtime_role'")"
test "$role_state" = "ok" \
  || fail "runtime role must exist with LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION"

membership_count="$(psql "$psql_url" \
  --username "$ELMOS_DATABASE_MIGRATION_USER" \
  --no-psqlrc --tuples-only --no-align --set ON_ERROR_STOP=1 \
  --command "select count(*) from pg_auth_members where member = (select oid from pg_roles where rolname = '$runtime_role')")"
test "$membership_count" = "0" \
  || fail "runtime role must not inherit privileges through role membership"

owned_relation_count="$(psql "$psql_url" \
  --username "$ELMOS_DATABASE_MIGRATION_USER" \
  --no-psqlrc --tuples-only --no-align --set ON_ERROR_STOP=1 \
  --command "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relowner = (select oid from pg_roles where rolname = '$runtime_role')")"
test "$owned_relation_count" = "0" \
  || fail "runtime role must not own public schema relations"

psql "$psql_url" \
  --username "$ELMOS_DATABASE_MIGRATION_USER" \
  --no-psqlrc --set ON_ERROR_STOP=1 --set runtime_role="$runtime_role" <<'SQL'
BEGIN;
GRANT USAGE ON SCHEMA public TO :"runtime_role";

-- Only tables queried or mutated directly by the control-plane JDBC adapters.
-- Tenant tables remain protected by FORCE RLS and app.organization_id.
GRANT SELECT ON TABLE
  execution_jobs,
  runner_enrollment_credentials,
  runner_node_authentication,
  runner_pools,
  runner_nodes,
  runner_job_leases,
  object_storage_backends,
  content_objects,
  job_artifacts,
  repositories,
  scm_connections,
  github_app_installations,
  scm_repositories,
  github_app_onboarding_states,
  github_webhook_deliveries,
  repository_snapshots,
  snapshot_root_reconciliations,
  cas_object_catalog,
  cas_object_placement,
  cas_resource_bindings,
  cas_reference_roots,
  cas_deletion_manifests,
  cas_quarantine_events,
  cas_action_cache_entries,
  cas_action_cache_invalidations,
  cas_action_cache_quarantined_nodes
TO :"runtime_role";

-- Idempotently tighten roles created by an earlier script revision before restoring the exact
-- lifecycle grant below. A table-level UPDATE would bypass the intended column boundary.
REVOKE UPDATE, DELETE ON TABLE
  repository_snapshots,
  github_app_onboarding_states,
  github_app_installations,
  scm_repositories,
  github_webhook_deliveries
FROM :"runtime_role";

GRANT INSERT, UPDATE ON TABLE
  runner_enrollment_credentials,
  runner_node_authentication,
  runner_pools,
  runner_nodes,
  content_objects,
  snapshot_root_reconciliations,
  cas_object_catalog,
  cas_object_placement,
  cas_resource_bindings,
  cas_reference_roots,
  cas_action_cache_entries
TO :"runtime_role";

GRANT INSERT ON TABLE
  audit_events,
  outbox_events,
  scm_connections,
  github_app_onboarding_states,
  github_app_installations,
  repositories,
  scm_repositories,
  github_webhook_deliveries,
  repository_snapshots,
  cas_deletion_manifests,
  cas_quarantine_events,
  cas_action_cache_invalidations,
  cas_action_cache_quarantined_nodes
TO :"runtime_role";

GRANT UPDATE (duplicate_count)
ON TABLE github_webhook_deliveries TO :"runtime_role";

GRANT UPDATE (status) ON TABLE repository_snapshots TO :"runtime_role";

GRANT UPDATE (stage, installation_external_id, expires_at, updated_at, consumed_at)
ON TABLE github_app_onboarding_states TO :"runtime_role";

GRANT UPDATE (status, suspended_at, deleted_at, last_synced_at)
ON TABLE github_app_installations TO :"runtime_role";

GRANT UPDATE (
  installation_id, owner_login, repository_name, full_name, clone_url, html_url,
  default_branch, visibility, archived, disabled, fork, parent_repository_external_id,
  authorization_status, synced_at
)
ON TABLE scm_repositories TO :"runtime_role";

SELECT set_config('elmos.runtime_role', :'runtime_role', false);

DO $$
DECLARE
  v_function record;
BEGIN
  FOR v_function IN
    SELECT p.oid::regprocedure AS signature
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public'
       AND p.proname IN (
         'elmos_issue_verification_challenge',
         'elmos_consume_verification_challenge',
         'elmos_find_account_by_phone',
         'elmos_find_account_by_email',
         'elmos_find_account',
         'elmos_create_phone_account',
         'elmos_create_email_account',
         'elmos_complete_signup',
         'elmos_clear_sign_in_failures',
         'elmos_record_sign_in_failure',
         'elmos_memberships_of_account',
         'elmos_open_session',
         'elmos_rotate_session_token',
         'elmos_switch_session_organization',
         'elmos_revoke_session',
         'elmos_find_session_by_token',
         'elmos_record_security_event',
         'elmos_resolve_oidc_account',
         'elmos_create_self_service_organization',
         'elmos_create_organization_invitation',
         'elmos_accept_organization_invitation',
         'elmos_list_organization_members',
         'elmos_update_organization_member',
         'elmos_invitation_organization',
         'elmos_enqueue_execution_job',
         'elmos_claim_execution_jobs',
         'elmos_heartbeat_execution_lease',
         'elmos_complete_execution_job',
         'elmos_request_execution_cancel',
         'elmos_reap_execution_leases',
         'elmos_publish_job_artifact',
         'elmos_issue_download_grant',
         'elmos_expire_artifacts',
         'elmos_pending_object_purges',
         'elmos_confirm_object_purged',
         'elmos_finish_object_gc'
       )
  LOOP
    EXECUTE format(
      'GRANT EXECUTE ON FUNCTION %s TO %I',
      v_function.signature,
      current_setting('elmos.runtime_role')
    );
  END LOOP;
END;
$$;

DO $$
BEGIN
  IF to_regprocedure(
      'public.elmos_resolve_github_webhook_organization(bigint,bigint)') IS NULL THEN
    RAISE EXCEPTION 'required GitHub webhook tenant resolver is missing';
  END IF;
  EXECUTE format(
    'GRANT EXECUTE ON FUNCTION '
    || 'public.elmos_resolve_github_webhook_organization(bigint,bigint) TO %I',
    current_setting('elmos.runtime_role')
  );
END;
$$;

-- V72 keeps snapshot materialization leases and the global reconciliation queue private.
-- The runtime role receives only the six fenced SECURITY DEFINER entry points, and a
-- partially migrated database fails closed instead of silently omitting a grant.
DO $$
DECLARE
  function_signature text;
  required_functions text[] := ARRAY[
    'public.elmos_acquire_snapshot_materialization_lease(varchar,varchar,varchar,varchar,varchar,integer)',
    'public.elmos_renew_snapshot_materialization_lease(varchar,varchar,varchar,varchar,varchar,bigint,integer)',
    'public.elmos_require_active_snapshot_materialization_lease(varchar,varchar,varchar,varchar,varchar,bigint)',
    'public.elmos_release_snapshot_materialization_lease(varchar,varchar,varchar,varchar,varchar,bigint)',
    'public.elmos_claim_snapshot_reconciliation_work(varchar,integer,integer)',
    'public.elmos_complete_snapshot_reconciliation_work(varchar,varchar,bigint,boolean,integer)'
  ];
BEGIN
  FOREACH function_signature IN ARRAY required_functions
  LOOP
    IF to_regprocedure(function_signature) IS NULL THEN
      RAISE EXCEPTION 'required snapshot lease/scheduler function is missing: %',
        function_signature;
    END IF;
    EXECUTE format(
      'GRANT EXECUTE ON FUNCTION %s TO %I',
      function_signature,
      current_setting('elmos.runtime_role')
    );
  END LOOP;
END;
$$;
COMMIT;
SQL

unset PGPASSWORD
printf '%s\n' "Control-plane runtime role grants applied with RLS bypass disabled."
