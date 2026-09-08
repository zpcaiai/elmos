package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CommercialCreditMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V83__commercial_credit_and_one_time_orders.sql");
    private static final Path DIGEST_TRIGGER_REPAIR = Path.of(
            "src/main/resources/db/migration/V86__elmpay_digest_trigger_catalog_hashing.sql");
    private static final Path RUNTIME_ROLE_CONFIGURATION = Path.of(
            "../../scripts/commercial/configure_billing_runtime_role.sh");

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

    @Test void elmpayDigestTriggersUseCatalogHashingUnderPinnedSearchPath() throws Exception {
        String sql = Files.readString(DIGEST_TRIGGER_REPAIR);
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_sync_payment_order_directory()"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_sync_wallet_topup_directory()"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_sync_commercial_order_directory()"));
        assertTrue(sql.contains("SET search_path = pg_catalog, public, pg_temp"));
        assertTrue(sql.contains("pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to("));
        assertTrue(sql.contains("amount_minor, provider, status)"));
        assertTrue(sql.contains("NEW.amount_minor, NEW.provider, NEW.status)"));
        assertFalse(sql.contains("public.encode("));
        assertFalse(sql.contains("public.digest("));
    }

    @Test void postMigrationRoleProvisioningIncludesEveryCommercialBoundary() throws Exception {
        String script = Files.readString(RUNTIME_ROLE_CONFIGURATION);
        for (String table : new String[]{
                "payment_order_directory", "wallet_topup_order_directory",
                "commercial_order_directory", "commercial_products",
                "commercial_credit_accounts", "project_generation_entitlements"}) {
            assertTrue(script.contains(table), table + " must be granted after Flyway");
        }
        for (String function : new String[]{
                "elmos_wallet_credit_topup", "elmos_wallet_create_topup_order",
                "elmos_reserve_usage_v2", "elmos_settle_usage_v2", "elmos_release_usage_v2",
                "elmos_commercial_create_order", "elmos_commercial_fulfill_order",
                "elmos_commercial_mark_order_handoff", "elmos_commercial_mark_order_prepare_failed",
                "elmos_commercial_reserve_generation", "elmos_commercial_settle_generation",
                "elmos_commercial_release_generation",
                "elmos_commercial_expire_generation_reservations"}) {
            assertTrue(script.contains("'" + function + "'"),
                    function + " must be granted when the runtime role is created after Flyway");
        }
        assertTrue(script.contains("GRANT SELECT ON TABLE\n  commercial_products,"));
        assertTrue(script.contains("payment_unmatched_callbacks_payment_unmatched_callback_id_seq"));
        assertTrue(script.contains("GRANT UPDATE (processing_status, attempt_count, updated_at)"));
        assertFalse(script.contains("GRANT INSERT ON TABLE commercial_credit_accounts"));
        assertFalse(script.contains("GRANT DELETE ON TABLE commercial_credit_ledger_entries"));
    }
}
