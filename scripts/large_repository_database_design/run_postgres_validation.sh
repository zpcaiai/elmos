#!/usr/bin/env bash

set -euo pipefail
IFS=$'\n\t'
export LC_ALL=C

die() {
  printf 'large-repository database validation: %s\n' "$*" >&2
  exit 1
}

if [[ "${ELMOS_LARGE_REPOSITORY_DB_DISPOSABLE_CONFIRMED:-}" != "true" ]]; then
  die "ELMOS_LARGE_REPOSITORY_DB_DISPOSABLE_CONFIRMED must be exactly true"
fi

database_url="${ELMOS_LARGE_REPOSITORY_DB_URL:-}"
[[ -n "$database_url" ]] || die "ELMOS_LARGE_REPOSITORY_DB_URL is required"
command -v psql >/dev/null 2>&1 || die "psql is required"

repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
source_root="$repository_root/skills/elmos-large-repository-database-design-v1.0.0"
canonical_migrations_root="$source_root/database/migrations"
role_hardening="$source_root/database/roles/roles-and-grants.example.sql"
role_check="$source_root/database/queries/role_hardening_check.sql"
invariants="$source_root/database/tests/invariants.sql"
runtime_scenarios="$repository_root/scripts/large_repository_database_design/runtime_scenarios.sql"
runtime_renderer="$repository_root/scripts/large_repository_database_design/render_runtime_migrations.py"

[[ -d "$canonical_migrations_root" ]] || die "immutable migration root is missing: $canonical_migrations_root"
[[ -f "$role_hardening" ]] || die "role hardening SQL is missing: $role_hardening"
[[ -f "$role_check" ]] || die "role hardening check is missing: $role_check"
[[ -f "$invariants" ]] || die "invariant SQL is missing: $invariants"
[[ -f "$runtime_scenarios" ]] || die "runtime scenario SQL is missing: $runtime_scenarios"
[[ -f "$runtime_renderer" ]] || die "runtime migration renderer is missing: $runtime_renderer"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

runtime_overlay_root="$(mktemp -d "${TMPDIR:-/tmp}/elmos-large-repository-db-overlay.XXXXXX")"
cleanup_runtime_overlay() {
  if [[ -n "$runtime_overlay_root" && -d "$runtime_overlay_root" ]]; then
    rm -rf -- "$runtime_overlay_root"
  fi
}
trap cleanup_runtime_overlay EXIT
migrations_root="$runtime_overlay_root/migrations"
printf 'Rendering digest-bound PostgreSQL 16/17 compatibility migrations\n'
python3 "$runtime_renderer" --package-root "$source_root" --output-root "$migrations_root"

expected_migrations=(
  V001__extensions_schemas_and_helpers.sql
  V010__tenancy_projects_jobs_and_admission.sql
  V020__runs_tasks_sessions_and_recovery.sql
  V030__artifacts_manifests_staging_and_checkpoints.sql
  V040__repository_intelligence_semantic_ir_and_capabilities.sql
  V045__project_generation_and_transformation.sql
  V050__verification_evidence_gates_and_repair.sql
  V060__model_tool_metering_cost_eta_and_cache.sql
  V070__integration_learning_deployment_and_audit.sql
  V080__cross_links_rls_and_read_models.sql
  V090__transactional_runtime_functions.sql
)

shopt -s nullglob
actual_migrations=("$migrations_root"/V*.sql)
shopt -u nullglob

if [[ ${#actual_migrations[@]} -ne ${#expected_migrations[@]} ]]; then
  die "expected exactly ${#expected_migrations[@]} canonical migrations, found ${#actual_migrations[@]}"
fi

for index in "${!expected_migrations[@]}"; do
  actual_name="${actual_migrations[$index]##*/}"
  expected_name="${expected_migrations[$index]}"
  [[ "$actual_name" == "$expected_name" ]] ||
    die "migration order mismatch at index $index: expected $expected_name, found $actual_name"
done

run_psql() {
  command psql \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --dbname="$database_url" \
    "$@"
}

server_version_num="$(run_psql --tuples-only --no-align --command='SHOW server_version_num')"
[[ "$server_version_num" =~ ^[0-9]+$ ]] || die "PostgreSQL returned an invalid server_version_num"
server_major=$((server_version_num / 10000))
case "$server_major" in
  16 | 17) ;;
  *) die "only PostgreSQL 16 and 17 are in this package's declared runtime scope; found major $server_major" ;;
esac
server_version="$(run_psql --tuples-only --no-align --command='SHOW server_version')"

existing_canonical_schemas="$(run_psql --tuples-only --no-align --command="
  SELECT nspname
  FROM pg_namespace
  WHERE nspname IN (
    'extensions','core','exec','artifact','analysis','generation','transform',
    'verify','metering','cache','integration','learning','ops','audit'
  )
  ORDER BY nspname;
")"
[[ -z "$existing_canonical_schemas" ]] ||
  die "the disposable database is not empty; canonical schemas already exist: ${existing_canonical_schemas//$'\n'/, }"

for migration in "${actual_migrations[@]}"; do
  printf 'Applying canonical migration %s\n' "${migration##*/}"
  run_psql --file="$migration"
done

printf 'Applying production-style role hardening\n'
run_psql --file="$role_hardening"

printf 'Checking role ownership, ACLs, login, and BYPASSRLS properties\n'
run_psql --file="$role_check"

printf 'Checking database invariants\n'
run_psql --file="$invariants"

printf 'Checking bounded transactional runtime scenarios\n'
run_psql --file="$runtime_scenarios"

assert_exact_inventory() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  if [[ "$actual" != "$expected" ]]; then
    printf 'Exact %s inventory assertion failed.\nExpected:\n%s\nActual:\n%s\n' \
      "$label" "$expected" "$actual" >&2
    return 1
  fi
  printf 'Exact %s inventory verified\n' "$label"
}

expected_schemas="$(
  cat <<'EOF'
analysis
artifact
audit
cache
core
exec
extensions
generation
integration
learning
metering
ops
transform
verify
EOF
)"

expected_tables="$(
  cat <<'EOF'
analysis.analysis_snapshot
analysis.build_target
analysis.capability
analysis.capability_edge
analysis.dependency_record
analysis.discovery_warning
analysis.graph_shard
analysis.ir_shard
analysis.module_record
analysis.repository_file
analysis.repository_scan
analysis.runtime_surface
analysis.semantic_ir_revision
analysis.symbol_record
analysis.unsupported_semantic
artifact.artifact
artifact.artifact_link
artifact.manifest
artifact.manifest_entry
artifact.object_blob
artifact.run_archive
artifact.staged_object
audit.audit_event
cache.cache_access
cache.cache_dependency
cache.cache_entry
cache.cache_invalidation
core.account
core.account_task_slot
core.job
core.job_input_revision
core.job_submission
core.project
core.repository
core.repository_revision
core.revision_snapshot
core.tenant
exec.approval_decision
exec.approval_request
exec.checkpoint
exec.checkpoint_component
exec.context_compaction
exec.context_epoch
exec.execution_lease
exec.human_gate
exec.recovery_action
exec.run
exec.run_attempt
exec.run_control_request
exec.run_event
exec.run_event_cursor
exec.run_progress_snapshot
exec.run_stage
exec.session
exec.session_event
exec.session_event_cursor
exec.task
exec.task_attempt
exec.task_dependency
exec.worker_node
exec.workpad
exec.workpad_item
exec.workspace
generation.acceptance_criterion
generation.archetype_selection
generation.architecture_revision
generation.capability_mapping
generation.generated_file
generation.generation_decision
generation.generation_iteration
generation.generation_unit
generation.project_generation_plan
generation.requirement_edge
generation.requirement_node
generation.requirement_set
integration.compensation_action
integration.inbox_message
integration.outbox_event
integration.reconciliation_issue
integration.reconciliation_run
integration.side_effect_receipt
learning.benchmark_result
learning.benchmark_run
learning.benchmark_suite
learning.data_authorization
learning.repair_trace
learning.rule_candidate
learning.rule_release
learning.rule_validation
learning.transformation_case
metering.budget_reservation
metering.cost_ledger
metering.eta_forecast
metering.model_invocation
metering.price_snapshot
metering.resource_usage_aggregate
metering.revenue_ledger
metering.tool_invocation
metering.usage_ledger
ops.deployment
ops.deployment_check
ops.deployment_gate
ops.migration_run
ops.release
ops.release_component
ops.service_health_snapshot
transform.cutover_plan
transform.mapping_decision
transform.patch_set
transform.rule_application
transform.target_revision
transform.transformation_plan
transform.transformation_unit
verify.behavior_observation
verify.capability_coverage
verify.certification
verify.differential_mismatch
verify.evidence_bundle
verify.evidence_bundle_item
verify.evidence_item
verify.evidence_revocation
verify.failure_cluster
verify.gate_evaluation
verify.gate_finding
verify.invariant
verify.invariant_result
verify.repair_attempt
verify.requirement
verify.requirement_coverage
verify.semantic_gap
verify.verification_case
verify.verification_execution
verify.verification_plan
verify.verification_result
verify.verification_suite
verify.waiver
EOF
)"

expected_functions="$(
  cat <<'EOF'
artifact.reject_sealed_manifest_entry_change
artifact.validate_available_artifact
artifact.validate_manifest_seal
core.claim_account_slot
core.current_actor_id
core.current_request_id
core.current_tenant_id
core.json_object_or_empty
core.nonblank
core.provision_account_task_slots
core.reject_delete
core.reject_update_delete
core.release_account_slot
core.renew_account_slot
core.sha256_is_valid
core.touch_updated_at
exec.append_run_event
exec.append_session_event
exec.claim_ready_task
exec.create_run
exec.finish_task_attempt
exec.initialize_run_records
exec.initialize_session_cursor
exec.refresh_run_progress
exec.renew_task_lease
exec.seal_checkpoint
integration.reserve_side_effect
ops.complete_deployment_with_gate
verify.complete_run_with_gate
verify.validate_evidence_item
verify.validate_gate_evaluation
EOF
)"

expected_views="$(
  cat <<'EOF'
analysis.v_repository_inventory
cache.v_run_cache_effectiveness
core.v_account_slot_usage
exec.v_run_dashboard
exec.v_stalled_task_attempts
metering.v_run_financials
ops.v_deployment_readiness
verify.v_completion_readiness
EOF
)"

actual_schemas="$(run_psql --tuples-only --no-align --command="
  SELECT nspname
  FROM pg_namespace
  WHERE nspname !~ '^pg_'
    AND nspname NOT IN ('information_schema', 'public')
  ORDER BY nspname;
")"

actual_tables="$(run_psql --tuples-only --no-align --command="
  SELECT n.nspname || '.' || c.relname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname IN (
    'core','exec','artifact','analysis','generation','transform',
    'verify','metering','cache','integration','learning','ops','audit'
  )
    AND c.relkind IN ('r', 'p')
    AND NOT EXISTS (
      SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid
    )
  ORDER BY 1;
")"

actual_functions="$(run_psql --tuples-only --no-align --command="
  SELECT DISTINCT n.nspname || '.' || p.proname
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname IN (
    'core','exec','artifact','analysis','generation','transform',
    'verify','metering','cache','integration','learning','ops','audit'
  )
    AND p.prokind = 'f'
  ORDER BY 1;
")"

actual_views="$(run_psql --tuples-only --no-align --command="
  SELECT n.nspname || '.' || c.relname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname IN (
    'core','exec','artifact','analysis','generation','transform',
    'verify','metering','cache','integration','learning','ops','audit'
  )
    AND c.relkind = 'v'
  ORDER BY 1;
")"

assert_exact_inventory schemas "$expected_schemas" "$actual_schemas"
assert_exact_inventory parent_tables "$expected_tables" "$actual_tables"
assert_exact_inventory functions "$expected_functions" "$actual_functions"
assert_exact_inventory views "$expected_views" "$actual_views"

printf 'ELMOS LARGE-REPOSITORY DATABASE VALIDATION PASSED\n'
printf 'postgres_server_version=%s\n' "$server_version"
printf 'canonical_migrations=%s\n' "${#expected_migrations[@]}"
printf 'parent_tables=136\n'
printf 'functions=31\n'
printf 'views=8\n'
printf 'external_evidence_status=NOT_RUN\n'
printf 'certification_status=NOT_CERTIFIED\n'
