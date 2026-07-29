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
  --command "select rolsuper || '|' || rolbypassrls || '|' || rolcanlogin from pg_roles where rolname = '$runtime_role'")"
test "$role_state" = "false|false|true" \
  || fail "runtime role must exist with LOGIN NOSUPERUSER NOBYPASSRLS"

psql "$psql_url" \
  --username "$ELMOS_DATABASE_MIGRATION_USER" \
  --no-psqlrc --set ON_ERROR_STOP=1 --set runtime_role="$runtime_role" <<'SQL'
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
  job_artifacts
TO :"runtime_role";

GRANT INSERT, UPDATE ON TABLE
  runner_enrollment_credentials,
  runner_node_authentication,
  runner_pools,
  runner_nodes,
  content_objects
TO :"runtime_role";

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
SQL

unset PGPASSWORD
printf '%s\n' "Control-plane runtime role grants applied with RLS bypass disabled."
