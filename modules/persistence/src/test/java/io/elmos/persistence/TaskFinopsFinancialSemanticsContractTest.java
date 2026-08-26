package io.elmos.persistence;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Focused source contract for the V77 finance rules; no database or provider is started. */
class TaskFinopsFinancialSemanticsContractTest {
    private static String migration;

    @BeforeAll
    static void readMigration() throws Exception {
        Path path = Path.of(
                System.getProperty("basedir"),
                "src", "main", "resources", "db", "migration",
                "V77__account_task_control_and_finops_runtime.sql");
        migration = normalize(Files.readString(path));
    }

    @Test
    void financialSummaryFallsBackFromAbsentFinalCostToPostedCost() {
        String summary = section(
                "CREATE VIEW mtf_task_financial_summary AS",
                "-- 13. Capability grants (deployment logins remain externally provisioned)");

        assertTrue(summary.contains(
                "(sum(base_cost_minor) FILTER (WHERE cost_state = 'FINAL'))" +
                        "::numeric(30,6) AS final_cost_minor"));
        assertFalse(summary.contains(
                "coalesce(sum(base_cost_minor) FILTER (WHERE cost_state = 'FINAL'), 0)"));
        assertTrue(summary.contains(
                "coalesce(usage.final_cost_minor, usage.posted_cost_minor, 0)"));
    }

    @Test
    void manualReconciliationReplayComparesTheWholeGovernedPayload() {
        String function = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_request_manual_reconciliation(",
                "-- 11. Checkpoint, side-effect, usage and revenue write boundaries");

        assertTrue(function.contains("pg_advisory_xact_lock"));
        assertTrue(function.contains("v_existing.job_id IS DISTINCT FROM p_task_id"));
        assertTrue(function.contains(
                "v_existing.actor_id IS DISTINCT FROM current_setting('app.actor_id')"));
        assertTrue(function.contains(
                "v_existing.reason_code IS DISTINCT FROM p_reason_code"));
        assertTrue(function.contains(
                "jsonb_build_object('evidence_reference', p_evidence_reference)"));
        assertTrue(function.contains(
                "v_job.organization_id, v_job.account_id, v_job.job_id, " +
                        "'REQUEST_RECONCILIATION', p_idempotency_key"));
        assertTrue(function.contains("ELMOS_MTF_RECONCILIATION_IDEMPOTENCY_CONFLICT"));
        assertFalse(function.contains("ON CONFLICT"));
    }

    @Test
    void allocationAllowsPartialConservationButNeverOverAllocation() {
        String allocation = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_allocate_revenue(",
                "-- 12. Account-safe read projections and metric definitions");
        String summary = section(
                "CREATE VIEW mtf_task_financial_summary AS",
                "-- 13. Capability grants (deployment logins remain externally provisioned)");

        assertTrue(allocation.contains(
                "IF abs(v_allocated + elmos_mtf_round_half_even(p_amount_minor, 6)) > " +
                        "abs(v_source.amount_minor) THEN"));
        assertFalse(allocation.contains(
                "abs(v_allocated + elmos_mtf_round_half_even(p_amount_minor, 6)) <> " +
                        "abs(v_source.amount_minor)"));
        assertTrue(summary.contains(
                "abs(coalesce(allocation.allocated_amount_minor, 0)) <> " +
                        "abs(revenue.amount_minor)"));
        assertTrue(summary.contains("AS unreconciled_revenue_count"));
    }

    @Test
    void halfEvenRoundingIsSharedBySignedFinanceWritesAndChecksBothTieSigns() {
        String helper = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_round_half_even(",
                "ALTER TABLE price_books");
        String financeWrites = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_usage(",
                "-- 12. Account-safe read projections and metric definitions");

        assertTrue(helper.contains("ELSIF mod(abs(v_floor), 2) = 0 THEN"));
        assertTrue(helper.contains(
                "IF p_value::text IN ('NaN', 'Infinity', '-Infinity') THEN"));
        assertTrue(helper.contains(
                "elmos_mtf_round_half_even(1.2345665, 6) IS DISTINCT FROM 1.234566"));
        assertTrue(helper.contains(
                "elmos_mtf_round_half_even(1.2345675, 6) IS DISTINCT FROM 1.234568"));
        assertTrue(helper.contains(
                "elmos_mtf_round_half_even(-1.2345665, 6) IS DISTINCT FROM -1.234566"));
        assertTrue(helper.contains(
                "elmos_mtf_round_half_even(-1.2345675, 6) IS DISTINCT FROM -1.234568"));
        assertTrue(financeWrites.contains(
                "v_existing.exact_quantity IS DISTINCT FROM " +
                        "elmos_mtf_round_half_even(p_quantity, 9)"));
        assertTrue(financeWrites.contains(
                "v_existing.amount_minor IS DISTINCT FROM " +
                        "elmos_mtf_round_half_even(p_amount_minor, 6)"));
        assertFalse(financeWrites.contains("round(p_amount_minor, 6)"));
    }

    @Test
    void governedSqlWritesRejectExcessDecimalScaleAndPrecisionBeforeRounding() {
        String usage = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_usage(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_revenue(");
        String revenue = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_revenue(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_allocate_revenue(");
        String allocation = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_allocate_revenue(",
                "-- 12. Account-safe read projections and metric definitions");

        assertContainsAll(usage,
                "LANGUAGE plpgsql SECURITY DEFINER",
                "scale(p_quantity) > 9",
                "scale(p_unit_price_minor) > 9",
                "scale(p_fx_rate) > 12",
                "scale(p_source_cost_minor) > 6",
                "scale(p_base_cost_minor) > 6",
                "abs(p_quantity) >= power(10::numeric, 21)",
                "abs(p_unit_price_minor) >= power(10::numeric, 21)",
                "abs(p_fx_rate) >= power(10::numeric, 18)",
                "abs(p_source_cost_minor) >= power(10::numeric, 24)",
                "abs(p_base_cost_minor) >= power(10::numeric, 24)",
                "ELMOS_MTF_USAGE_ENTRY_INVALID_OR_CORRECTION_UNAPPROVED");
        assertContainsAll(revenue,
                "LANGUAGE plpgsql SECURITY DEFINER",
                "scale(p_amount_minor) > 6",
                "abs(p_amount_minor) >= power(10::numeric, 24)",
                "ELMOS_MTF_REVENUE_ENTRY_INVALID_OR_APPROVAL_UNRESOLVED");
        assertContainsAll(allocation,
                "LANGUAGE plpgsql SECURITY DEFINER",
                "scale(p_amount_minor) > 6",
                "abs(p_amount_minor) >= power(10::numeric, 24)",
                "ELMOS_MTF_ALLOCATION_INVALID_OR_APPROVAL_UNRESOLVED");
        assertOrdered(usage, "scale(p_quantity) > 9", "SELECT * INTO v_job");
        assertOrdered(revenue, "scale(p_amount_minor) > 6", "SELECT * INTO v_job");
        assertOrdered(allocation, "scale(p_amount_minor) > 6", "SELECT * INTO v_job");
        assertTrue(migration.contains(
                "REVOKE ALL ON task_revenue_ledger_entries FROM PUBLIC"));
        assertTrue(migration.contains(
                "REVOKE ALL ON task_revenue_allocations FROM PUBLIC"));
        assertFalse(migration.contains("GRANT INSERT ON task_revenue_ledger_entries"));
        assertFalse(migration.contains("GRANT INSERT ON task_revenue_allocations"));
    }

    @Test
    void taxAndPaymentFeeAreNegativeAndExcludedFromRecognizedRevenue() {
        String ledger = section(
                "CREATE TABLE task_revenue_ledger_entries (",
                "CREATE INDEX task_revenue_job_time_idx");
        String summary = section(
                "CREATE VIEW mtf_task_financial_summary AS",
                "-- 13. Capability grants (deployment logins remain externally provisioned)");

        assertTrue(ledger.contains("'REVENUE_RECOGNITION', 'TAX', 'PAYMENT_FEE',"));
        assertTrue(ledger.contains(
                "'CREDIT', 'REFUND', 'TAX', 'PAYMENT_FEE', 'REVERSAL'"));
        assertTrue(ledger.contains(
                "entry_kind NOT IN ('TAX', 'PAYMENT_FEE') " +
                        "OR entry_state IN ('RECORDED', 'POSTED', 'UNRECONCILED')"));
        assertTrue(summary.contains(
                "WHERE revenue.entry_kind NOT IN ('TAX', 'PAYMENT_FEE')"));
    }

    @Test
    void everyAppendReplayComparesTheCompletePersistedGovernedPayload() {
        String checkpoint = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_append_checkpoint(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_side_effect_receipt(");
        String sideEffect = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_side_effect_receipt(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_usage(");
        String usage = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_usage(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_revenue(");
        String revenue = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_record_revenue(",
                "CREATE OR REPLACE FUNCTION elmos_mtf_allocate_revenue(");
        String allocation = section(
                "CREATE OR REPLACE FUNCTION elmos_mtf_allocate_revenue(",
                "-- 12. Account-safe read projections and metric definitions");

        assertContainsAll(checkpoint,
                "v_existing.checkpoint_id IS DISTINCT FROM p_checkpoint_id",
                "v_existing.organization_id IS DISTINCT FROM v_job.organization_id",
                "v_existing.account_id IS DISTINCT FROM v_job.account_id",
                "v_existing.job_id IS DISTINCT FROM v_job.job_id",
                "v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number",
                "v_existing.event_key IS DISTINCT FROM p_idempotency_key",
                "v_existing.checkpoint_sequence IS DISTINCT FROM p_checkpoint_sequence",
                "v_existing.input_manifest_digest IS DISTINCT FROM",
                "v_existing.repository_revision IS DISTINCT FROM p_repository_revision",
                "v_existing.state_digest IS DISTINCT FROM p_content_digest::char(64)",
                "v_existing.toolchain_digest IS DISTINCT FROM p_toolchain_digest::char(64)",
                "v_existing.model_digest IS DISTINCT FROM p_model_digest::char(64)",
                "v_existing.schema_version IS DISTINCT FROM p_schema_version",
                "v_existing.next_node IS DISTINCT FROM p_node_id",
                "v_existing.manifest IS DISTINCT FROM jsonb_build_object(",
                "v_existing.compatibility_state IS DISTINCT FROM 'UNKNOWN'",
                "v_existing.created_by_actor_id IS DISTINCT FROM",
                "v_existing.created_at IS DISTINCT FROM p_created_at",
                "ELMOS_MTF_CHECKPOINT_IDEMPOTENCY_CONFLICT");
        assertContainsAll(sideEffect,
                "pg_advisory_xact_lock",
                "v_existing.side_effect_receipt_id IS DISTINCT FROM p_receipt_id",
                "v_existing.organization_id IS DISTINCT FROM v_job.organization_id",
                "v_existing.account_id IS DISTINCT FROM v_job.account_id",
                "v_existing.job_id IS DISTINCT FROM v_job.job_id",
                "v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number",
                "v_existing.node_key IS DISTINCT FROM p_node_id",
                "v_existing.operation_type IS DISTINCT FROM p_effect_type",
                "v_existing.idempotency_key IS DISTINCT FROM p_idempotency_key",
                "v_existing.intent_digest IS DISTINCT FROM p_request_digest::char(64)",
                "v_existing.provider_reference IS DISTINCT FROM p_provider_reference",
                "v_existing.receipt_digest IS DISTINCT FROM p_result_digest::char(64)",
                "v_existing.receipt_state IS DISTINCT FROM p_result_state",
                "v_existing.occurred_at IS DISTINCT FROM p_occurred_at",
                "v_existing.signature_algorithm IS DISTINCT FROM p_signature_algorithm",
                "v_existing.signing_key_id IS DISTINCT FROM p_signing_key_id",
                "v_existing.signature IS DISTINCT FROM p_signature",
                "v_existing.recorded_by_actor_id IS DISTINCT FROM",
                "v_existing.metadata IS DISTINCT FROM '{}'::jsonb",
                "ELMOS_MTF_SIDE_EFFECT_IDEMPOTENCY_CONFLICT");
        assertContainsAll(usage,
                "pg_advisory_xact_lock",
                "v_existing.usage_event_id IS DISTINCT FROM p_usage_entry_id",
                "v_existing.organization_id IS DISTINCT FROM v_job.organization_id",
                "v_existing.account_id IS DISTINCT FROM v_job.account_id",
                "v_existing.job_id IS DISTINCT FROM v_job.job_id",
                "v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number",
                "v_existing.schema_version IS DISTINCT FROM 'mtf-1.0'",
                "v_existing.status IS DISTINCT FROM 'RECORDED'",
                "v_existing.external_ref IS DISTINCT FROM p_provider_receipt_ref",
                "v_existing.idempotency_key IS DISTINCT FROM p_idempotency_key",
                "v_existing.payload IS DISTINCT FROM '{}'::jsonb",
                "v_existing.actor_id IS DISTINCT FROM current_setting('app.actor_id')",
                "v_existing.operation_key IS DISTINCT FROM 'task-runtime-cost'",
                "v_existing.provider IS DISTINCT FROM p_provider",
                "v_existing.provider_sku IS DISTINCT FROM p_provider_sku",
                "v_existing.usage_unit IS DISTINCT FROM p_usage_unit",
                "v_existing.exact_quantity IS DISTINCT FROM",
                "v_existing.price_book_ref IS DISTINCT FROM p_price_book_id",
                "v_existing.price_book_version IS DISTINCT FROM p_price_book_version",
                "v_existing.price_effective_at IS DISTINCT FROM p_price_effective_at",
                "v_existing.price_item_ref IS DISTINCT FROM v_item.price_item_id",
                "v_existing.unit_price_minor IS DISTINCT FROM",
                "v_existing.fx_snapshot_ref IS DISTINCT FROM p_fx_snapshot_id",
                "v_existing.fx_rate IS DISTINCT FROM",
                "v_existing.provider_cost_currency IS DISTINCT FROM p_source_currency",
                "v_existing.provider_cost_minor IS DISTINCT FROM v_source_cost",
                "v_existing.base_currency IS DISTINCT FROM p_base_currency",
                "v_existing.base_cost_minor IS DISTINCT FROM v_base_cost",
                "v_existing.cost_state IS DISTINCT FROM p_cost_state",
                "v_existing.cost_class IS DISTINCT FROM v_cost_class",
                "v_existing.reconciliation_status IS DISTINCT FROM",
                "v_existing.provider_receipt_ref IS DISTINCT FROM p_provider_receipt_ref",
                "v_existing.period_start IS DISTINCT FROM p_period_start",
                "v_existing.period_end IS DISTINCT FROM p_period_end",
                "v_existing.occurred_at IS DISTINCT FROM p_occurred_at",
                "v_existing.correction_of_event_id IS NOT NULL",
                "ELMOS_MTF_USAGE_IDEMPOTENCY_CONFLICT");
        assertContainsAll(revenue,
                "pg_advisory_xact_lock",
                "v_existing.revenue_entry_id IS DISTINCT FROM p_revenue_entry_id",
                "v_existing.organization_id IS DISTINCT FROM v_job.organization_id",
                "v_existing.account_id IS DISTINCT FROM v_job.account_id",
                "v_existing.project_id IS DISTINCT FROM p_project_id",
                "v_existing.legal_entity_id IS DISTINCT FROM p_legal_entity_id",
                "v_existing.job_id IS DISTINCT FROM v_job.job_id",
                "v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number",
                "v_existing.entry_kind IS DISTINCT FROM p_entry_kind",
                "v_existing.entry_state IS DISTINCT FROM p_entry_state",
                "v_existing.amount_minor IS DISTINCT FROM",
                "v_existing.currency IS DISTINCT FROM p_currency",
                "v_existing.effective_at IS DISTINCT FROM p_effective_at",
                "v_existing.period_start IS DISTINCT FROM p_period_start",
                "v_existing.period_end IS DISTINCT FROM p_period_end",
                "v_existing.source_type IS DISTINCT FROM p_source_type",
                "v_existing.source_reference IS DISTINCT FROM p_source_reference",
                "v_existing.idempotency_key IS DISTINCT FROM p_idempotency_key",
                "v_existing.correction_of_revenue_entry_id IS DISTINCT FROM",
                "v_existing.reconciliation_status IS DISTINCT FROM",
                "v_existing.signature_algorithm IS DISTINCT FROM p_signature_algorithm",
                "v_existing.signing_key_id IS DISTINCT FROM p_signing_key_id",
                "v_existing.signed_digest IS DISTINCT FROM p_signed_digest::char(64)",
                "v_existing.signature IS DISTINCT FROM p_signature",
                "v_existing.submitted_by_actor_id IS DISTINCT FROM",
                "ELMOS_MTF_REVENUE_IDEMPOTENCY_CONFLICT");
        assertContainsAll(allocation,
                "pg_advisory_xact_lock",
                "v_existing.revenue_allocation_id IS DISTINCT FROM p_allocation_id",
                "v_existing.organization_id IS DISTINCT FROM v_job.organization_id",
                "v_existing.account_id IS DISTINCT FROM v_job.account_id",
                "v_existing.revenue_entry_id IS DISTINCT FROM p_revenue_entry_id",
                "v_existing.project_id IS DISTINCT FROM p_project_id",
                "v_existing.job_id IS DISTINCT FROM v_job.job_id",
                "v_existing.run_number IS DISTINCT FROM v_job.workflow_run_number",
                "v_existing.allocation_basis IS DISTINCT FROM p_allocation_basis",
                "v_existing.policy_version IS DISTINCT FROM p_policy_version",
                "v_existing.allocated_amount_minor IS DISTINCT FROM",
                "v_existing.currency IS DISTINCT FROM p_currency",
                "v_existing.effective_at IS DISTINCT FROM p_effective_at",
                "v_existing.idempotency_key IS DISTINCT FROM p_idempotency_key",
                "v_existing.allocated_by_actor_id IS DISTINCT FROM",
                "v_existing.signature_algorithm IS DISTINCT FROM p_signature_algorithm",
                "v_existing.signing_key_id IS DISTINCT FROM p_signing_key_id",
                "v_existing.signed_digest IS DISTINCT FROM p_signed_digest::char(64)",
                "v_existing.signature IS DISTINCT FROM p_signature",
                "ELMOS_MTF_ALLOCATION_IDEMPOTENCY_CONFLICT");
    }

    private static String section(String start, String end) {
        int startIndex = migration.indexOf(start);
        int endIndex = migration.indexOf(end, startIndex);
        if (startIndex < 0 || endIndex < 0) {
            throw new AssertionError("V77 section markers missing: " + start + " / " + end);
        }
        return migration.substring(startIndex, endIndex);
    }

    private static void assertContainsAll(String section, String... fragments) {
        for (String fragment : fragments) {
            assertTrue(section.contains(fragment), () -> "Missing replay guard: " + fragment);
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
