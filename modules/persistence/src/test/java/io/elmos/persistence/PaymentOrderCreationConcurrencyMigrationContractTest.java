package io.elmos.persistence;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class PaymentOrderCreationConcurrencyMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V88__payment_order_creation_concurrency.sql");

    @Test
    void walletDailyCapAndReplayFactsAreSerialized() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertTrue(sql.contains("FROM wallet_accounts"));
        assertTrue(sql.contains("FOR UPDATE"));
        assertTrue(sql.indexOf("FROM wallet_accounts")
                < sql.indexOf("SELECT coalesce(sum(amount_minor), 0)"));
        assertTrue(sql.contains("ELMOS_WALLET_TOPUP_IDEMPOTENCY_CONFLICT"));
        assertTrue(sql.contains("SET search_path = pg_catalog, public, pg_temp"));
        assertTrue(sql.contains("v_existing.actor_id IS DISTINCT FROM p_actor_id"));
        assertTrue(sql.contains("v_existing.amount_minor IS DISTINCT FROM p_amount_minor"));
        assertTrue(sql.contains("v_existing.provider IS DISTINCT FROM p_provider"));
        assertTrue(sql.contains(
                "status NOT IN ('CREATED', 'PENDING_PAYMENT') OR expires_at > now()"));
        assertFalse(sql.contains("SET status = 'EXPIRED'"),
                "late provider success must retain the reconciliation path");
    }

    @Test
    void commercialConcurrentReplayUsesTransactionScopedKeyLock() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertTrue(sql.contains("pg_advisory_xact_lock"));
        assertTrue(sql.contains("hashtextextended(v_org || chr(31) || p_idempotency_key, 0)"));
        assertTrue(sql.contains("ELMOS_COMMERCIAL_ORDER_IDEMPOTENCY_CONFLICT"));
        assertFalse(sql.contains("LOCK TABLE"), "unrelated tenants must remain concurrent");
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION elmos_wallet_create_topup_order"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION elmos_commercial_create_order"));
    }
}
