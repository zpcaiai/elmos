package io.elmos.persistence;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;

class PricingBillingFinancialCoreMigrationContractTest {
    private static final String MIGRATION = "db/migration/V65__pricing_billing_financial_core.sql";

    @Test
    void declaresTenantAndLegalEntityIsolationForEveryFinancialAggregate() throws IOException {
        String sql = migration();
        List<String> scopedTables = List.of(
                "pricing_billing_wallet",
                "pricing_billing_wallet_lot",
                "pricing_billing_wallet_entry",
                "pricing_billing_wallet_command",
                "pricing_billing_usage_source_fact",
                "pricing_billing_usage_normalized_fact",
                "pricing_billing_invoice",
                "pricing_billing_invoice_line",
                "pricing_billing_invoice_event",
                "pricing_billing_credit_note",
                "pricing_billing_fx_rate_fact",
                "pricing_billing_financial_fact",
                "pricing_billing_metric_observation",
                "pricing_billing_outbox");
        for (String table : scopedTables) {
            assertTrue(sql.contains("alter table " + table + " enable row level security"), table);
            assertTrue(sql.contains("alter table " + table + " force row level security"), table);
        }
        assertTrue(sql.contains("app.current_tenant_id"));
        assertTrue(sql.contains("app.current_legal_entity_id"));
        assertTrue(sql.contains("tenant_id uuid not null"));
        assertTrue(sql.contains("legal_entity_id uuid not null"));
    }

    @Test
    void preservesAppendOnlyWalletUsageInvoiceAndAnalyticsFacts() throws IOException {
        String sql = migration();
        assertTrue(sql.contains("pricing_billing_reject_immutable_change"));
        for (String trigger : List.of(
                "pricing_billing_wallet_entry_immutable",
                "pricing_billing_wallet_command_immutable",
                "pricing_billing_usage_source_immutable",
                "pricing_billing_usage_normalized_immutable",
                "pricing_billing_invoice_line_immutable",
                "pricing_billing_invoice_event_immutable",
                "pricing_billing_credit_note_immutable",
                "pricing_billing_fx_rate_immutable",
                "pricing_billing_financial_fact_immutable",
                "pricing_billing_metric_definition_immutable",
                "pricing_billing_metric_observation_immutable")) {
            assertTrue(sql.contains("create trigger " + trigger), trigger);
        }
        assertTrue(sql.contains("before update or delete"));
        assertTrue(sql.contains("append a correction instead"));
    }

    @Test
    void constrainsDoubleEntryReservationIdempotencyAndExactQuantities() throws IOException {
        String sql = migration();
        assertTrue(sql.contains("check (debit_account <> credit_account)"));
        assertTrue(sql.contains("quantity numeric(38, 12) not null check (quantity > 0)"));
        assertTrue(sql.contains("unique (tenant_id, legal_entity_id, wallet_id, aggregate_version)"));
        assertTrue(sql.contains("primary key (tenant_id, legal_entity_id, wallet_id, command_id)"));
        assertTrue(sql.contains("command_fingerprint char(64)"));
        assertTrue(sql.contains("credit_kind in ('paid', 'promotional')"));
        assertTrue(sql.contains("entry_type in ('grant', 'reserve', 'commit', 'release', 'expire', 'adjustment')"));
        assertTrue(sql.contains("create trigger pricing_billing_wallet_version_guard"));
        assertTrue(sql.contains("for update"));
        assertTrue(sql.contains("wallet optimistic version mismatch"));
    }

    @Test
    void modelsUsageDedupeCorrectionsWindowsLateDecisionsAndOutbox() throws IOException {
        String sql = migration();
        assertTrue(sql.contains("unique (tenant_id, legal_entity_id, source_system, source_event_id)"));
        assertTrue(sql.contains("unique (tenant_id, legal_entity_id, ingest_command_id)"));
        assertTrue(sql.contains("fact_type in ('original', 'correction')"));
        assertTrue(sql.contains("fact_type = 'correction' or quantity > 0"));
        assertTrue(sql.contains("foreign key (tenant_id, legal_entity_id, correction_of)"));
        assertTrue(sql.contains("billing_window_start timestamptz not null"));
        assertTrue(sql.contains("allowed_lateness interval not null"));
        assertTrue(sql.contains("usage_decision in ('accepted', 'late_review')"));
        assertTrue(sql.contains("(usage_decision = 'accepted') = billable"));
        assertTrue(sql.contains("create table pricing_billing_outbox"));
        assertTrue(sql.contains("aggregate_version bigint not null"));
        assertTrue(sql.contains("create unique index pricing_billing_payment_external_ref_uq"));
        assertTrue(sql.contains("create trigger pricing_billing_usage_outbox"));
        assertTrue(sql.contains("create trigger pricing_billing_outbox_guard"));
    }

    @Test
    void failsClosedForUnknownTaxAndUnreconciledPayments() throws IOException {
        String sql = migration();
        assertTrue(sql.contains("tax_state in ('calculated', 'exempt', 'unknown')"));
        assertTrue(sql.contains("tax_state <> 'unknown' and tax_evidence_ref is not null"));
        assertTrue(sql.contains("checker_actor_id <> maker_actor_id"));
        assertTrue(sql.contains("provider_state = 'reconciled' and bank_state = 'reconciled'"));
        assertTrue(sql.contains("provider_evidence_ref is not null and bank_evidence_ref is not null"));
        assertTrue(sql.contains("event_type in ('created', 'submitted_for_review', 'finalized', 'issued', 'payment_reconciled', 'credit_note_issued', 'voided')"));
        assertTrue(sql.contains("create trigger pricing_billing_invoice_projection_guard"));
        assertTrue(sql.contains("unknown line tax blocks invoice finalization"));
        assertTrue(sql.contains("invoice totals must equal immutable line totals"));
        assertTrue(sql.contains("invoice paid total must equal reconciled payment events"));
        assertTrue(sql.contains("invoice credited total must equal immutable credit notes"));
        assertTrue(sql.contains("credit note must bind one matching credit_note_issued event"));
        assertTrue(sql.contains("cumulative credit notes exceed invoice total"));
        assertTrue(sql.contains("create trigger pricing_billing_credit_note_guard"));
        assertTrue(sql.contains("unique (tenant_id, legal_entity_id, invoice_id, source_event_id)"));
        assertTrue(sql.contains("create trigger pricing_billing_invoice_outbox"));
    }

    @Test
    void versionsMarginDefinitionsAndKeepsUnknownDistinctFromZero() throws IOException {
        String sql = migration();
        assertTrue(sql.contains("primary key (metric_id, definition_version)"));
        assertTrue(sql.contains("denominator_name text not null"));
        assertTrue(sql.contains("metric_state in ('available', 'unknown')"));
        assertTrue(sql.contains("(metric_state = 'available') = (metric_value is not null)"));
        assertTrue(sql.contains("allocation_coverage >= 0 and allocation_coverage <= 1"));
        assertTrue(sql.contains("evidence_state in ('reconciled', 'final', 'unknown', 'disputed')"));
        assertFalse(sql.contains("double precision"));
        assertFalse(sql.contains(" real "));
    }

    @Test
    void statesThatMigrationIsNotCertification() throws IOException {
        String sql = migration();
        assertTrue(sql.contains("does not certify accounting"));
        assertTrue(sql.contains("not accounting certification"));
    }

    private static String migration() throws IOException {
        try (InputStream stream = PricingBillingFinancialCoreMigrationContractTest.class
                .getClassLoader().getResourceAsStream(MIGRATION)) {
            assertNotNull(stream, "missing migration " + MIGRATION);
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8)
                    .toLowerCase(java.util.Locale.ROOT)
                    .replaceAll("\\s+", " ")
                    .trim();
        }
    }
}
