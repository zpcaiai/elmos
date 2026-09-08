package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Cheap structural guard for the PostgreSQL-proven V85 payment lifecycle migration. */
class PaymentLifecycleHardeningMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V85__payment_provider_binding_and_credit_expiry.sql");
    private static final Path RUNTIME_ROLE_CONFIG = Path.of(
            "..", "..", "scripts", "commercial", "configure_billing_runtime_role.sh");
    private static final Path CATALOG_MIGRATION = Path.of(
            "src/main/resources/db/migration/V86__self_service_catalog_2026_09_08.sql");

    @Test
    void callbackDirectoriesBindTheImmutableProviderAndUseTheRealEncodeSchema() throws Exception {
        String sql = Files.readString(MIGRATION);

        for (String directory : new String[]{
                "payment_order_directory", "wallet_topup_order_directory",
                "commercial_order_directory"}) {
            assertTrue(sql.contains("ALTER TABLE " + directory));
            assertTrue(sql.contains("COMMENT ON COLUMN " + directory + ".provider"));
        }
        assertTrue(sql.contains("pg_catalog.encode(public.digest("));
        assertFalse(sql.contains("public.encode("),
                "encode is a PostgreSQL built-in in pg_catalog, not a pgcrypto function");
        for (String source : new String[]{
                "payment_checkout_sessions", "wallet_topup_orders", "commercial_orders"}) {
            assertTrue(sql.contains("ALTER TABLE " + source + " FORCE ROW LEVEL SECURITY"));
            assertTrue(sql.contains("'" + source + "'"));
        }
        assertTrue(sql.contains("% FORCE ROW LEVEL SECURITY was not restored"));
    }

    @Test
    void providerUnknownWalletStateFitsBothSourceAndDirectoryAndKeepsItsTrigger() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("ALTER COLUMN status TYPE varchar(24)"));
        assertTrue(sql.contains("DROP TRIGGER wallet_topup_orders_directory_sync"));
        assertTrue(sql.contains("CREATE TRIGGER wallet_topup_orders_directory_sync"));
        assertTrue(sql.contains("'REFUNDED', 'RECONCILIATION_REQUIRED'"));
        assertTrue(sql.contains("elmos_wallet_mark_topup_prepare_failed"));
        assertTrue(sql.contains("'PAID', 'PENDING_PAYMENT', 'CREATED', 'RECONCILIATION_REQUIRED'"));
    }

    @Test
    void onlyPrepareUnknownCommercialOrdersCanRecoverAutomatically() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("v_order.failure_code IS DISTINCT FROM "
                + "'CHECKOUT_PREPARE_OUTCOME_UNKNOWN'"));
        assertTrue(sql.contains("v_order.expires_at <= now()"));
        assertTrue(sql.contains("failure_code = 'PAYMENT_AFTER_LOCAL_EXPIRY'"));
        assertTrue(sql.contains("failure_code = NULL"));
    }

    @Test
    void expiredCreditReservationsAreReclaimedWithoutMintingExpiredCredit() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("elmos_commercial_expire_generation_reservations"));
        assertTrue(sql.contains("FOR UPDATE SKIP LOCKED"));
        assertTrue(sql.contains("expires_at <= now()"));
        assertTrue(sql.contains("SET status = 'EXPIRED'"));
        assertTrue(sql.contains("balance = balance - v_expired"));
        assertTrue(sql.contains("reserved = reserved - v_res.requested_credits"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION "
                + "elmos_commercial_expire_generation_reservations(integer) FROM PUBLIC"));
    }

    @Test
    void runtimeRoleProvisionedAfterFlywayReceivesEveryPaymentLifecycleGrant() throws Exception {
        String script = Files.readString(RUNTIME_ROLE_CONFIG);

        for (String relation : new String[]{
                "payment_callback_receipts", "payment_unmatched_callbacks",
                "payment_order_directory", "wallet_topup_order_directory",
                "commercial_order_directory", "commercial_orders",
                "commercial_credit_accounts", "commercial_credit_lots",
                "commercial_credit_ledger_entries", "project_generation_entitlements",
                "commercial_credit_reservations", "commercial_credit_reservation_lots"}) {
            assertTrue(script.contains(relation), relation + " must be granted after role creation");
        }
        for (String function : new String[]{
                "elmos_wallet_credit_topup", "elmos_wallet_topup_bounds",
                "elmos_wallet_create_topup_order", "elmos_wallet_mark_topup_handoff",
                "elmos_wallet_mark_topup_prepare_failed", "elmos_reserve_usage_v2",
                "elmos_settle_usage_v2", "elmos_release_usage_v2",
                "elmos_commercial_create_order", "elmos_commercial_fulfill_order",
                "elmos_commercial_mark_order_handoff",
                "elmos_commercial_mark_order_prepare_failed",
                "elmos_commercial_reserve_generation", "elmos_commercial_settle_generation",
                "elmos_commercial_release_generation",
                "elmos_commercial_expire_generation_reservations"}) {
            assertTrue(script.contains("'" + function + "'"),
                    function + " must be granted after role creation");
        }
        assertTrue(script.contains("GRANT UPDATE (processing_status, attempt_count, updated_at)"));
        assertFalse(script.contains("GRANT UPDATE ON TABLE payment_callback_receipts"),
                "callback receipts must retain column-scoped update privilege");
    }

    @Test
    void currentCatalogIsPersistedAndUsedByTrialAndPaidActivation() throws Exception {
        String sql = Files.readString(CATALOG_MIGRATION);

        assertTrue(sql.contains("'2026-09-08.1', 'elmos-free-trial'"));
        assertTrue(sql.contains("'2026-09-08.1', 'elmos-pro-monthly'"));
        assertTrue(sql.contains("'2026-09-08.1', 'elmos-pro-annual'"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_grant_trial"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_activate_subscription_period"));
        assertFalse(sql.contains("2026-07-28.2"),
                "new trial and paid activations must not bind the superseded catalog");
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION elmos_grant_trial"));
        assertTrue(sql.contains("GRANT EXECUTE ON FUNCTION elmos_grant_trial"));
    }
}
