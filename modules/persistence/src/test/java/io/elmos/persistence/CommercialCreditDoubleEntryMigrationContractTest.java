package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Structural guard for the PostgreSQL-executed V88 accounting migration. */
class CommercialCreditDoubleEntryMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V88__commercial_credit_double_entry_and_outbox.sql");

    @Test
    void journalIsAppendOnlyTenantScopedAndBalancedAtCommit() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("CREATE TABLE commercial_credit_journal_transactions"));
        assertTrue(sql.contains("CREATE TABLE commercial_credit_journal_entries"));
        assertTrue(sql.contains("ELMOS_CREDIT_JOURNAL_APPEND_ONLY"));
        assertTrue(sql.contains("ELMOS_CREDIT_JOURNAL_UNBALANCED"));
        assertTrue(sql.contains("DEFERRABLE INITIALLY DEFERRED"));
        assertTrue(sql.contains("FOREIGN KEY (transaction_id, organization_id)"));
        for (String table : new String[]{
                "commercial_credit_journal_transactions",
                "commercial_credit_journal_entries",
                "commercial_credit_projection_rebuilds"}) {
            assertTrue(sql.contains("'" + table + "'"), table + " must use FORCE RLS");
        }
        assertTrue(sql.contains("FORCE ROW LEVEL SECURITY"));
    }

    @Test
    void everyProjectionMutationPostsJournalAndTransactionalOutbox() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("CREATE TRIGGER commercial_credit_account_double_entry"));
        assertTrue(sql.contains("AFTER INSERT OR UPDATE OF balance, reserved"));
        assertTrue(sql.contains("CREATE TABLE commercial_credit_outbox_events"));
        assertTrue(sql.contains("CREATE TABLE commercial_credit_outbox_delivery_attempts"));
        assertTrue(sql.contains("commercial_credit_outbox_delivery_attempts_append_only"));
        assertTrue(sql.contains("transaction_id varchar(96) NOT NULL UNIQUE"));
        assertTrue(sql.contains("COMMERCIAL_CREDIT_BALANCE_CHANGED"));
        assertTrue(sql.contains("FOR UPDATE SKIP LOCKED"));
        assertTrue(sql.contains("ELMOS_CREDIT_OUTBOX_EVENT_IMMUTABLE"));
        assertTrue(sql.contains("p_limit IS NULL"));
        assertTrue(sql.contains("p_lease_seconds IS NULL"));
        assertTrue(sql.contains("elmos_complete_commercial_credit_outbox"));
        assertFalse(sql.contains("GRANT INSERT ON commercial_credit_journal"));
        assertFalse(sql.contains("GRANT UPDATE ON commercial_credit_outbox_events"));
        assertFalse(sql.contains("GRANT INSERT ON commercial_credit_outbox_delivery_attempts"));
    }

    @Test
    void openingBalancesAndProjectionRebuildAreAuditableAndIdempotent() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("'OPENING_BALANCE'"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_commercial_credit_reconcile()"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_commercial_rebuild_credit_projection"));
        assertTrue(sql.contains("ELMOS_CREDIT_REBUILD_IDEMPOTENCY_CONFLICT"));
        assertTrue(sql.contains("commercial_credit_projection_rebuilds_append_only"));
        assertTrue(sql.contains("TO elmos_credit_reconciler"));
        assertTrue(sql.contains("TO elmos_credit_outbox_publisher"));
    }
}
