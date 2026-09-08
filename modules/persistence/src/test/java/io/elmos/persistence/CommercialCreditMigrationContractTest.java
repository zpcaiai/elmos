package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CommercialCreditMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V83__commercial_credit_and_one_time_orders.sql");
    @Test void catalogContainsExactServerOwnedProducts() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertTrue(sql.contains("'elmos-credit-500', 'CREDIT_PACK', '2026-09-08.1'"));
        assertTrue(sql.contains("'elmos-project-generation-once', 'PROJECT_GENERATION_ONCE'"));
        assertTrue(sql.contains("ELMOS_COMMERCIAL_PRODUCT_IMMUTABLE"));
    }

    @Test void callbacksSeeOnlyTheMinimalDirectoryBeforeTenantResolution() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertTrue(sql.contains("CREATE TABLE commercial_order_directory"));
        assertTrue(sql.contains("CREATE TRIGGER commercial_orders_directory_sync"));
        assertTrue(sql.contains("SECURITY DEFINER\nSET search_path = pg_catalog, public, pg_temp"));
        assertFalse(sql.contains("'commercial_order_directory'"));
    }

    @Test void creditBalancesAndEntitlementsAreAtomicAndTenantForced() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertTrue(sql.contains("ELMOS_CREDIT_BALANCE_DIRECT_MUTATION_DENIED"));
        assertTrue(sql.contains("CREATE TRIGGER commercial_credit_ledger_append_only"));
        assertTrue(sql.contains("FOR UPDATE SKIP LOCKED"));
        assertTrue(sql.contains("UNIQUE (organization_id, job_id)"));
        for (String table : new String[]{
                "commercial_orders", "commercial_credit_accounts",
                "commercial_credit_lots", "commercial_credit_ledger_entries",
                "project_generation_entitlements", "commercial_credit_reservations",
                "commercial_credit_reservation_lots"}) {
            assertTrue(sql.contains("'" + table + "'"), table + " must use FORCE RLS");
        }
        assertTrue(sql.contains("FORCE ROW LEVEL SECURITY"));
    }

    @Test void perUserTokenHistoryCarriesProjectJobAndModelDimensions() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertTrue(sql.contains("ALTER TABLE usage_reservations"));
        assertTrue(sql.contains("ADD COLUMN project_id varchar(128)"));
        assertTrue(sql.contains("ADD COLUMN job_id varchar(128)"));
        assertTrue(sql.contains("ADD COLUMN model varchar(160)"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_reserve_usage_v2"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_settle_usage_v2"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_release_usage_v2"));
        assertTrue(sql.contains("'CACHE_WRITE', 'REASONING'"));
        assertTrue(sql.contains("GRANT SELECT ON identity.accounts, ai_usage.model_calls"));
        assertTrue(sql.contains("AND actor_id = p_actor_id"));
        assertTrue(sql.contains("USAGE_RESERVATION_DIMENSION_CONFLICT"));
    }

    @Test void paymentRuntimeGetsFunctionsButNoWriteableCreditTables() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertTrue(sql.contains("ADD COLUMN processing_status varchar(16)"));
        assertTrue(sql.contains("GRANT UPDATE (processing_status, attempt_count, updated_at)"));
        assertTrue(sql.contains("PAYMENT_AFTER_LOCAL_EXPIRY"));
        assertTrue(sql.contains("elmos_commercial_mark_order_handoff"));
        assertTrue(sql.contains("elmos_commercial_mark_order_prepare_failed"));
        assertTrue(sql.contains("GRANT EXECUTE ON FUNCTION elmos_commercial_fulfill_order"));
        assertTrue(sql.contains("GRANT SELECT ON commercial_order_directory"));
        assertFalse(sql.contains("GRANT INSERT ON commercial_credit_accounts"));
        assertFalse(sql.contains("GRANT UPDATE ON commercial_credit_accounts"));
        assertFalse(sql.contains("GRANT DELETE ON commercial_credit_ledger_entries"));
    }
}
