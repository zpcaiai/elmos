#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf '%s\n' "commercial billing runtime role blocked: $1" >&2
  exit 1
}

required() {
  local name="$1"
  test -n "${!name:-}" || fail "$name is required"
}

required ELMOS_COMMERCIAL_DATABASE_URL
required ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME
required ELMOS_COMMERCIAL_DATABASE_MIGRATION_PASSWORD
required ELMOS_COMMERCIAL_DATABASE_RUNTIME_USERNAME

command -v psql >/dev/null || fail "psql is required"
runtime_role="$ELMOS_COMMERCIAL_DATABASE_RUNTIME_USERNAME"
case "$runtime_role" in
  [A-Za-z_]*)
    [[ "$runtime_role" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] \
      || fail "runtime role name is invalid"
    ;;
  *) fail "runtime role name is invalid" ;;
esac
test "$runtime_role" != "$ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME" \
  || fail "runtime and migration roles must be different"

psql_url="${ELMOS_COMMERCIAL_DATABASE_URL#jdbc:}"
export PGPASSWORD="$ELMOS_COMMERCIAL_DATABASE_MIGRATION_PASSWORD"

role_state="$(psql "$psql_url" \
  --username "$ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME" \
  --no-psqlrc --tuples-only --no-align --set ON_ERROR_STOP=1 \
  --command "select rolsuper || '|' || rolbypassrls from pg_roles where rolname = '$runtime_role'")"
test "$role_state" = "false|false" \
  || fail "runtime role must exist with NOSUPERUSER and NOBYPASSRLS"

psql "$psql_url" \
  --username "$ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME" \
  --no-psqlrc --set ON_ERROR_STOP=1 <<SQL
GRANT USAGE ON SCHEMA public TO "$runtime_role";
GRANT SELECT ON TABLE self_service_pricing_plan_versions TO "$runtime_role";
GRANT SELECT, INSERT, UPDATE ON TABLE
  subscriptions,
  subscription_events,
  quota_allocations,
  usage_reservations,
  usage_events,
  usage_ledger_entries,
  trial_grants,
  trial_events,
  payment_checkout_sessions,
  payment_provider_events,
  payment_reconciliation_cases,
  payment_reconciliation_case_events,
  usage_alert_preferences,
  usage_alert_deliveries
TO "$runtime_role";
DO \$\$
DECLARE
  v_function record;
BEGIN
  FOR v_function IN
    SELECT p.oid::regprocedure AS signature
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public'
       AND p.proname IN (
         'elmos_enqueue_usage_alerts',
         'elmos_current_organization_id',
         'elmos_reserve_usage',
         'elmos_settle_usage',
         'elmos_release_usage',
         'elmos_correct_usage',
         'elmos_activate_subscription_period',
         'elmos_grant_trial',
         'elmos_resolve_payment_reconciliation',
         'elmos_expire_current_trial'
       )
  LOOP
    EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO %I', v_function.signature, '$runtime_role');
  END LOOP;
END;
\$\$;
SQL

unset PGPASSWORD
printf '%s\n' "Commercial billing runtime role grants applied with RLS bypass disabled."
