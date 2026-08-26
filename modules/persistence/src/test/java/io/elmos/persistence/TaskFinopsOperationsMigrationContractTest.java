package io.elmos.persistence;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Static guardrails for the V77.1/V77.2 fail-closed operations. */
class TaskFinopsOperationsMigrationContractTest {
    private static String runtime;
    private static String operations;
    private static String analytics;

    @BeforeAll
    static void readMigrations() throws Exception {
        Path root = Path.of(System.getProperty("basedir"),
                "src", "main", "resources", "db", "migration");
        runtime = normalize(Files.readString(root.resolve(
                "V77__account_task_control_and_finops_runtime.sql")));
        operations = normalize(Files.readString(root.resolve(
                "V77_1__task_finops_recovery_lifecycle_and_settlement.sql")));
        analytics = normalize(Files.readString(root.resolve(
                "V77_2__task_finops_analytics_rebuild_and_exports.sql")));
    }

    @Test
    void tenantAuthorityIsTransactionBoundBeforeAnyRoutingGucIsTrusted() {
        String contextTable = section(runtime,
                "CREATE TABLE task_finops_bound_contexts (",
                "CREATE OR REPLACE FUNCTION elmos_mtf_context_matches(");
        String contextMatcher = section(runtime,
                "CREATE OR REPLACE FUNCTION elmos_mtf_context_matches(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_account_context_matches(");
        String assertion = section(runtime,
                "CREATE OR REPLACE FUNCTION elmos_mtf_assert_bound_context()",
                "CREATE OR REPLACE FUNCTION elmos_mtf_bind_identity(");
        String memberRole = section(operations,
                "CREATE OR REPLACE FUNCTION elmos_mtf_require_member_role(",
                "-- 6. Ordered feature rollout mutation");
        String publication = section(analytics,
                "CREATE OR REPLACE FUNCTION elmos_mtf_publish_analytics_projection(",
                "CREATE VIEW mtf_current_task_run_projections");

        assertContainsAll(contextTable,
                "backend_pid integer NOT NULL",
                "transaction_id bigint NOT NULL",
                "session_role name NOT NULL",
                "PRIMARY KEY (backend_pid, transaction_id, session_role)",
                "REVOKE ALL ON task_finops_bound_contexts FROM PUBLIC");
        assertContainsAll(contextMatcher,
                "bound.backend_pid = pg_backend_pid()",
                "bound.transaction_id = txid_current()",
                "bound.session_role = session_user",
                "account.status = 'ACTIVE'",
                "membership.member_state = 'ACTIVE'",
                "identity.deprovisioned_at IS NULL");
        assertContainsAll(assertion,
                "FROM task_finops_bound_contexts bound",
                "bound.backend_pid = pg_backend_pid()",
                "bound.transaction_id = txid_current()",
                "bound.session_role = session_user",
                "RAISE EXCEPTION 'ELMOS_MTF_IDENTITY_CONTEXT_UNBOUND'");
        assertOrdered(memberRole,
                "PERFORM elmos_mtf_assert_bound_context();",
                "current_setting('app.organization_id')");
        assertContainsAll(publication,
                "elmos_mtf_bound_organization_id()",
                "elmos_mtf_bound_account_id()",
                "elmos_mtf_context_matches(v_organization_id, v_account_id)");
        assertFalse(publication.contains("current_setting('app.organization_id'"));
        assertFalse(publication.contains("current_setting('app.account_id'"));
    }

    @Test
    void pauseAndResumeReplayAreExactlyBoundToJobOrganizationAndAccount() {
        String pause = section(runtime,
                "CREATE OR REPLACE FUNCTION elmos_mtf_pause_task(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_resume_task(");
        String resume = section(runtime,
                "CREATE OR REPLACE FUNCTION elmos_mtf_resume_task(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_request_execution_cancel(");

        assertContainsAll(pause,
                "PERFORM elmos_mtf_assert_bound_context();",
                "action = 'PAUSE_TASK' AND idempotency_key = p_idempotency_key",
                "v_audit.job_id IS DISTINCT FROM p_task_id",
                "v_audit.target_digest IS DISTINCT FROM p_request_digest::char(64)",
                "WHERE job_id = p_task_id AND organization_id = " +
                        "current_setting('app.organization_id') AND account_id = " +
                        "current_setting('app.account_id')",
                "RAISE EXCEPTION 'ELMOS_MTF_CONTROL_IDEMPOTENCY_CONFLICT'");
        assertContainsAll(resume,
                "PERFORM elmos_mtf_assert_bound_context();",
                "action = 'RESUME_TASK' AND idempotency_key = p_idempotency_key",
                "v_audit.job_id IS DISTINCT FROM p_task_id",
                "v_audit.target_digest IS DISTINCT FROM p_request_digest::char(64)",
                "WHERE job_id = p_task_id AND organization_id = " +
                        "current_setting('app.organization_id') AND account_id = " +
                        "current_setting('app.account_id')",
                "RAISE EXCEPTION 'ELMOS_MTF_CONTROL_IDEMPOTENCY_CONFLICT'");
        assertOrdered(pause, "PERFORM elmos_mtf_assert_bound_context();",
                "SELECT * INTO v_audit FROM task_finops_audit_events");
        assertOrdered(resume, "PERFORM elmos_mtf_assert_bound_context();",
                "SELECT * INTO v_audit FROM task_finops_audit_events");
    }

    @Test
    void tenantExportPagesFormAnAppendOnlyTerminallyBoundCountedChain() {
        String table = section(operations,
                "CREATE TABLE task_tenant_export_pages (",
                "CREATE TABLE task_tenant_lifecycle_events (");
        String checkpoint = section(operations,
                "CREATE OR REPLACE FUNCTION elmos_mtf_checkpoint_tenant_export_page(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_advance_tenant_lifecycle(");
        String advance = section(operations,
                "CREATE OR REPLACE FUNCTION elmos_mtf_advance_tenant_lifecycle(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_tenant_purge_result(");

        assertContainsAll(table,
                "cumulative_row_count bigint NOT NULL CHECK (cumulative_row_count >= row_count)",
                "cumulative_byte_count bigint NOT NULL CHECK (cumulative_byte_count >= byte_count)",
                "checkpoint_chain_digest char(64) NOT NULL",
                "UNIQUE (lifecycle_job_id, page_number)",
                "UNIQUE (organization_id, account_id, idempotency_key)",
                "FOREIGN KEY (lifecycle_job_id, organization_id, account_id)",
                "terminal AND manifest_digest IS NOT NULL AND manifest_digest = checkpoint_chain_digest",
                "CREATE TRIGGER task_tenant_export_pages_append_only",
                "elmos_forbid_append_only_mutation()");
        assertContainsAll(checkpoint,
                "v_existing.cumulative_row_count IS DISTINCT FROM p_cumulative_row_count",
                "v_existing.cumulative_byte_count IS DISTINCT FROM p_cumulative_byte_count",
                "v_existing.terminal IS DISTINCT FROM p_terminal",
                "v_previous.terminal",
                "ELMOS_MTF_EXPORT_PAGE_ALREADY_TERMINAL",
                "ELMOS_MTF_EXPORT_PAGE_SEQUENCE_INVALID",
                "ELMOS_MTF_EXPORT_CURSOR_DID_NOT_ADVANCE",
                "'ELMOS_TENANT_EXPORT_PAGE_V1'",
                "v_previous.checkpoint_chain_digest::varchar",
                "v_manifest_digest := CASE WHEN p_terminal THEN v_chain_digest ELSE NULL END",
                "exported_row_count = p_cumulative_row_count",
                "exported_byte_count = p_cumulative_byte_count");
        assertContainsAll(advance,
                "ELMOS_MTF_EXPORT_PROGRESS_NOT_CHECKPOINTED",
                "NOT v_terminal_page.terminal",
                "v_terminal_page.manifest_digest IS DISTINCT FROM p_manifest_digest::char(64)",
                "v_terminal_page.cumulative_row_count IS DISTINCT FROM p_exported_row_count",
                "v_terminal_page.cumulative_byte_count IS DISTINCT FROM p_exported_byte_count",
                "ELMOS_MTF_EXPORT_TERMINAL_CHECKPOINT_REQUIRED");
    }

    @Test
    void unknownAndBlockedLifecycleRecoveryRemainFailClosed() {
        String advance = section(operations,
                "CREATE OR REPLACE FUNCTION elmos_mtf_advance_tenant_lifecycle(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_tenant_purge_result(");

        assertContainsAll(advance,
                "p_provider_result_state = 'UNKNOWN' AND p_next_state NOT IN " +
                        "('UNKNOWN_RESULT', 'RECONCILING')",
                "p_next_state = 'UNKNOWN_RESULT' AND p_provider_result_state <> 'UNKNOWN'",
                "v_job.operation_state = 'BLOCKED' AND p_next_state = 'REQUESTED'",
                "ELMOS_MTF_BLOCKED_RECOVERY_PROVIDER_STATE_INVALID",
                "v_job.operation_state = 'UNKNOWN_RESULT' AND p_next_state = 'RECONCILING'",
                "ELMOS_MTF_UNKNOWN_RESULT_UNRESOLVED",
                "v_job.operation_state = 'RECONCILING' AND p_next_state IN " +
                        "('EXPORTING', 'PURGE_PENDING') AND " +
                        "p_provider_result_state <> 'CONFIRMED'");
        assertFalse(advance.contains(
                "v_job.operation_state = 'UNKNOWN_RESULT' AND p_next_state = 'TOMBSTONED'"));
        assertFalse(advance.contains(
                "v_job.operation_state = 'UNKNOWN_RESULT' AND p_next_state = 'COMPLETED'"));
    }

    @Test
    void tombstoningRechecksUnknownScopeRetentionHoldsAndActiveTasks() {
        String request = section(operations,
                "CREATE OR REPLACE FUNCTION elmos_mtf_request_tenant_lifecycle(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_checkpoint_tenant_export_page(");
        String advance = section(operations,
                "CREATE OR REPLACE FUNCTION elmos_mtf_advance_tenant_lifecycle(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_tenant_purge_result(");

        assertContainsAll(request,
                "job.account_id IS NULL",
                "ELMOS_MTF_RESOURCE_ACCOUNT_BINDING_UNKNOWN",
                "job.organization_id = current_setting('app.organization_id')",
                "artifact.legal_hold OR artifact.retention_class = 'LEGAL_HOLD'",
                "ELMOS_MTF_LEGAL_HOLD_ACTIVE",
                "artifact.expires_at IS NULL OR artifact.expires_at > now()",
                "ELMOS_MTF_RETENTION_ACTIVE_OR_UNKNOWN");
        assertContainsAll(advance,
                "job.account_id IS NULL",
                "ELMOS_MTF_RESOURCE_ACCOUNT_BINDING_UNKNOWN",
                "job.organization_id = v_job.organization_id",
                "ELMOS_MTF_LEGAL_HOLD_ACTIVE",
                "ELMOS_MTF_RETENTION_ACTIVE_OR_UNKNOWN",
                "'QUEUED', 'CLAIMED', 'RUNNING', 'PAUSED', 'UNKNOWN_RESULT', 'RECONCILING'",
                "ELMOS_MTF_ACTIVE_OR_UNKNOWN_TASKS_BLOCK_DELETION",
                "item.purge_state <> 'CONFIRMED'",
                "ELMOS_MTF_PURGE_RECONCILIATION_REQUIRED",
                "SET tenant_tombstoned_at = now()");
        assertOrdered(advance,
                "ELMOS_MTF_ACTIVE_OR_UNKNOWN_TASKS_BLOCK_DELETION",
                "IF p_next_state = 'TOMBSTONED' THEN");
    }

    @Test
    void productionRolloutAndRecoveryRequireExternalAndIndependentDecisions() {
        assertTrue(operations.contains(
                "p_environment = 'PRODUCTION' AND p_rollout_stage = 'ON'"));
        assertTrue(operations.contains("ELMOS_MTF_EXTERNAL_GATE_REQUIRED"));
        assertTrue(operations.contains(
                "v_checkpoint.created_by_actor_id = current_setting('app.actor_id')"));
        assertTrue(operations.contains("ELMOS_MTF_INDEPENDENT_VERIFIER_REQUIRED"));
        assertTrue(operations.contains("v_decision.decision_state <> 'INCOMPATIBLE'"));
        assertTrue(operations.contains("ELMOS_MTF_INCOMPATIBLE_DECISION_REQUIRED"));
        assertTrue(operations.contains(
                "v_decision.verifier_actor_id = current_setting('app.actor_id')"));
        assertTrue(operations.contains(
                "ELMOS_MTF_EXECUTOR_VERIFIER_SEPARATION_REQUIRED"));
    }

    @Test
    void lifecycleCannotCompleteOnLegalHoldOrUnknownProviderOutcome() {
        assertTrue(operations.contains("ELMOS_MTF_LEGAL_HOLD_ACTIVE"));
        assertTrue(operations.contains(
                "p_provider_result_state = 'UNKNOWN' AND p_next_state NOT IN " +
                        "('UNKNOWN_RESULT', 'RECONCILING')"));
        assertTrue(operations.contains("ELMOS_MTF_PROVIDER_RESULT_UNKNOWN"));
        assertTrue(operations.contains("ELMOS_MTF_PURGE_RECONCILIATION_REQUIRED"));
        assertTrue(operations.contains("provider_result_state = 'CONFIRMED'"));
        assertFalse(operations.contains("provider_result_state <> 'FAILED' OR"));
    }

    @Test
    void settlementMatchNeedsExactMoneyAndSeparateEvidenceVerifier() {
        String settlement = section(operations,
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_settlement_reconciliation(",
                "-- 10. Capability grants");

        assertTrue(settlement.contains(
                "v_difference := CASE WHEN p_provider_result_state = 'CONFIRMED'"));
        assertTrue(settlement.contains("WHEN v_difference IS DISTINCT FROM 0"));
        assertContainsAll(settlement,
                "scale(p_ledger_recorded_minor) > 6",
                "abs(p_ledger_recorded_minor) >= 1000000000000000000000000::numeric",
                "scale(p_provider_reported_minor) > 6",
                "abs(p_provider_reported_minor) >= " +
                        "1000000000000000000000000::numeric",
                "abs(v_difference) >= 1000000000000000000000000::numeric",
                "v_existing.provider_reported_minor IS DISTINCT FROM CASE",
                "v_existing.ledger_recorded_minor IS DISTINCT FROM",
                "v_existing.difference_minor IS DISTINCT FROM v_difference",
                "v_existing.provider_result_state IS DISTINCT FROM p_provider_result_state",
                "v_existing.reconciliation_state IS DISTINCT FROM v_state");
        assertOrdered(settlement,
                "PERFORM pg_advisory_xact_lock",
                "SELECT * INTO v_existing FROM task_settlement_reconciliations");
        assertTrue(settlement.contains(
                "p_evidence_verifier_actor_id = current_setting('app.actor_id')"));
        assertTrue(settlement.contains(
                "ELMOS_MTF_INDEPENDENT_SETTLEMENT_EVIDENCE_REQUIRED"));
        assertContainsAll(settlement,
                "identity.account_ref <> current_setting('app.account_id')",
                "membership.member_state = 'ACTIVE'",
                "membership.member_role IN ('OWNER', 'ADMIN', 'BILLING')");
        assertTrue(operations.contains(
                "reconciliation_state IN ('MATCHED', 'UNRECONCILED', 'UNKNOWN')"));
    }

    @Test
    void analyticsPublicationIsBoundedGenerationScopedAndConservative() {
        String rebuildTable = section(analytics,
                "CREATE TABLE task_finops_projection_rebuilds (",
                "CREATE TABLE task_finops_run_projections (");
        String publication = section(analytics,
                "CREATE OR REPLACE FUNCTION elmos_mtf_publish_analytics_projection(",
                "CREATE VIEW mtf_current_task_run_projections");
        String currentViews = section(analytics,
                "CREATE VIEW mtf_current_task_run_projections",
                "REVOKE ALL ON mtf_task_journal_for_rebuild FROM PUBLIC");

        assertContainsAll(rebuildTable,
                "event_count bigint NOT NULL CHECK (event_count >= 0)",
                "fact_count bigint NOT NULL CHECK (fact_count >= 0)",
                "run_count bigint NOT NULL CHECK (run_count >= 0)",
                "bucket_count bigint NOT NULL CHECK (bucket_count >= 0)",
                "run_payload_digest char(64) NOT NULL",
                "bucket_payload_digest char(64) NOT NULL",
                "storage_payload_digest char(64) NOT NULL",
                "input_continuity varchar(24) NOT NULL CHECK " +
                        "(input_continuity IN ('COMPLETE', 'UNKNOWN'))",
                "external_evidence_state varchar(24) NOT NULL DEFAULT 'NOT_RUN' " +
                        "CHECK (external_evidence_state = 'NOT_RUN')",
                "provider_outcome varchar(24) NOT NULL DEFAULT 'UNKNOWN' " +
                        "CHECK (provider_outcome = 'UNKNOWN')",
                "production_certification varchar(24) NOT NULL DEFAULT 'NOT_CERTIFIED' " +
                        "CHECK (production_certification = 'NOT_CERTIFIED')",
                "generation_version = expected_generation + 1");
        assertContainsAll(publication,
                "jsonb_array_length(p_runs) > 10000",
                "jsonb_array_length(p_buckets) > 50000",
                "p_input_continuity <> 'COMPLETE'",
                "ELMOS_MTF_ANALYTICS_CONTINUITY_INCOMPLETE",
                "v_run_count := jsonb_array_length(p_runs)",
                "v_bucket_count := jsonb_array_length(p_buckets)",
                "v_run_payload_digest := encode(sha256(convert_to(p_runs::text, 'UTF8')), 'hex')",
                "v_bucket_payload_digest := encode(sha256(convert_to(p_buckets::text, 'UTF8')), 'hex')",
                "'run_count', v_run_count",
                "'run_payload_digest', v_run_payload_digest",
                "'bucket_count', v_bucket_count",
                "'bucket_payload_digest', v_bucket_payload_digest",
                "v_existing.event_count IS DISTINCT FROM p_event_count",
                "v_existing.fact_count IS DISTINCT FROM p_fact_count",
                "v_existing.expected_generation IS DISTINCT FROM p_expected_generation",
                "v_existing.run_count IS DISTINCT FROM v_run_count",
                "v_existing.bucket_count IS DISTINCT FROM v_bucket_count",
                "v_existing.run_payload_digest IS DISTINCT FROM " +
                        "v_run_payload_digest::char(64)",
                "v_existing.bucket_payload_digest IS DISTINCT FROM " +
                        "v_bucket_payload_digest::char(64)",
                "v_existing.storage_payload_digest IS DISTINCT FROM " +
                        "v_payload_digest::char(64)",
                "v_existing.input_continuity IS DISTINCT FROM p_input_continuity",
                "ELMOS_MTF_ANALYTICS_GENERATION_CONFLICT",
                "v_generation := coalesce(v_head.generation_version, 0) + 1",
                "WHERE rebuild_id = p_rebuild_id) <> v_run_count",
                "WHERE rebuild_id = p_rebuild_id) <> p_event_count",
                "WHERE rebuild_id = p_rebuild_id) <> v_bucket_count",
                "FILTER (WHERE grain = 'HOUR')",
                "FILTER (WHERE grain = 'DAY')",
                "task_finops_projection_heads");
        assertOrdered(publication,
                "IF p_input_continuity <> 'COMPLETE' THEN",
                "PERFORM pg_advisory_xact_lock");
        assertOrdered(publication,
                "PERFORM pg_advisory_xact_lock",
                "SELECT * INTO v_existing FROM task_finops_projection_rebuilds");
        assertOrdered(publication,
                "SELECT * INTO v_head FROM task_finops_projection_heads",
                "v_generation := coalesce(v_head.generation_version, 0) + 1");
        assertContainsAll(currentViews,
                "rebuild.input_continuity = 'COMPLETE'",
                "rebuild.external_evidence_state = 'NOT_RUN'",
                "rebuild.provider_outcome = 'UNKNOWN'",
                "rebuild.production_certification = 'NOT_CERTIFIED'",
                "false AS externally_qualified");
        assertTrue(analytics.contains("ALTER TABLE %I FORCE ROW LEVEL SECURITY"));
    }

    private static String section(String source, String start, String end) {
        int startIndex = source.indexOf(start);
        int endIndex = source.indexOf(end, startIndex);
        if (startIndex < 0 || endIndex < 0) {
            throw new AssertionError("Migration section markers missing: " + start + " / " + end);
        }
        return source.substring(startIndex, endIndex);
    }

    private static void assertContainsAll(String source, String... fragments) {
        for (String fragment : fragments) {
            assertTrue(source.contains(fragment), () -> "Missing SQL contract: " + fragment);
        }
    }

    private static void assertOrdered(String source, String first, String second) {
        int firstIndex = source.indexOf(first);
        int secondIndex = source.indexOf(second);
        assertTrue(firstIndex >= 0, () -> "Missing ordered SQL contract: " + first);
        assertTrue(secondIndex > firstIndex, () ->
                "SQL contract out of order: " + first + " before " + second);
    }

    private static String normalize(String value) {
        return value.replaceAll("\\s+", " ").trim();
    }
}
