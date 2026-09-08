package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CommercialCreditMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V83__commercial_credit_and_one_time_orders.sql");
    private static final Path ELMPAY_MIGRATION = Path.of(
            "src/main/resources/db/migration/V84__elmpay_order_digest_lookup.sql");
    private static final Path CATALOG_MIGRATION = Path.of(
            "src/main/resources/db/migration/V85__self_service_catalog_2026_09_08.sql");
    private static final Path RESERVATION_EXPIRY_MIGRATION = Path.of(
            "src/main/resources/db/migration/V86__payment_callback_and_generation_reservation_lifecycle.sql");
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

    @Test void postMigrationRoleProvisioningIncludesEveryCommercialFunctionBoundary() throws Exception {
        String script = Files.readString(RUNTIME_ROLE_CONFIGURATION);
        for (String table : new String[]{
                "payment_order_directory", "wallet_topup_order_directory",
                "commercial_order_directory", "commercial_products",
                "commercial_credit_accounts", "project_generation_entitlements"}) {
            assertTrue(script.contains(table), table + " must be granted after Flyway");
        }
        for (String function : new String[]{
                "elmos_wallet_credit_topup", "elmos_wallet_create_topup_order",
                "elmos_wallet_mark_topup_handoff", "elmos_wallet_mark_topup_prepare_failed",
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

    @Test void elmpayDigestTriggersUsePinnedCoreHashFunctions() throws Exception {
        String sql = Files.readString(ELMPAY_MIGRATION);
        assertTrue(sql.contains("pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to("));
        assertFalse(sql.contains("public.encode("));
        assertFalse(sql.contains("public.digest("));
        assertFalse(sql.contains("digest("));
    }

    @Test void databaseCatalogAndSubscriptionFunctionsUseTheCurrentAppendOnlyVersion() throws Exception {
        String sql = Files.readString(CATALOG_MIGRATION);
        for (String plan : new String[]{
                "elmos-free-trial", "elmos-pro-monthly", "elmos-pro-annual"}) {
            assertTrue(sql.contains("'2026-09-08.1', '" + plan + "'"),
                    plan + " must be present in the current database catalog snapshot");
        }
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_activate_subscription_period"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_grant_trial"));
        assertTrue(sql.contains("WHERE catalog_version = '2026-09-08.1' AND plan_id = p_plan_id"));
        assertTrue(sql.contains(
                "WHERE catalog_version = '2026-09-08.1' AND plan_id = 'elmos-free-trial'"));
        assertFalse(sql.contains("catalog_version = '2026-07-28.2'"));
        assertFalse(sql.contains("('2026-07-28.2',"));
        assertFalse(sql.contains("ON CONFLICT (catalog_version, plan_id)"));
    }

    @Test void expiredGenerationReservationsUseABoundedTenantScopedFunction() throws Exception {
        String sql = Files.readString(RESERVATION_EXPIRY_MIGRATION);
        assertTrue(sql.contains("ALTER TABLE payment_order_directory\n    ADD COLUMN provider varchar(32)"));
        assertTrue(sql.contains("ALTER TABLE wallet_topup_order_directory\n    ADD COLUMN provider varchar(16)"));
        assertTrue(sql.contains("ALTER TABLE commercial_order_directory\n    ADD COLUMN provider varchar(32)"));
        for (String table : new String[]{
                "payment_checkout_sessions", "wallet_topup_orders", "commercial_orders"}) {
            assertTrue(sql.contains("ALTER TABLE " + table + " NO FORCE ROW LEVEL SECURITY"));
            assertTrue(sql.contains("ALTER TABLE " + table + " FORCE ROW LEVEL SECURITY"));
        }
        assertTrue(sql.contains("ELMOS_PAYMENT_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE"));
        assertTrue(sql.contains("ELMOS_WALLET_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE"));
        assertTrue(sql.contains("ELMOS_COMMERCIAL_DIRECTORY_PROVIDER_BACKFILL_INCOMPLETE"));
        assertTrue(sql.contains("NEW.provider, NEW.status"));
        assertTrue(sql.contains("v_order.failure_code = 'CHECKOUT_PREPARE_OUTCOME_UNKNOWN'"));
        assertTrue(sql.contains("failure_code = NULL, updated_at = now()"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_wallet_mark_topup_handoff"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_wallet_mark_topup_prepare_failed"));
        assertTrue(sql.contains("v_org varchar := elmos_current_organization_id()"));
        assertTrue(sql.contains("p_limit < 1 OR p_limit > 1000"));
        assertTrue(sql.contains("LIMIT p_limit\n         FOR UPDATE SKIP LOCKED"));
        assertTrue(sql.contains("organization_id = v_org"));
        assertTrue(sql.contains("SET status = 'EXPIRED'"));
        assertTrue(sql.contains("held_by_job_id = NULL"));
        assertTrue(sql.contains("reserved = reserved - v_reservation.requested_credits"));
        assertTrue(sql.contains(
                "REVOKE ALL ON FUNCTION elmos_commercial_expire_generation_reservations(integer) FROM PUBLIC"));
    }
}
