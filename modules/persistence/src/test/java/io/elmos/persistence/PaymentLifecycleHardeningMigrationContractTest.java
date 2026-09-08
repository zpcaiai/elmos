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
}
