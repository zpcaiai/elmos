package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SelfServiceBillingMigrationContractTest {
    @Test
    void migrationOwnsTypedMoneyUsageRlsAndAtomicReservationContracts() throws Exception {
        Path migration = Path.of(
                System.getProperty("basedir"),
                "src", "main", "resources", "db", "migration",
                "V49__self_service_billing_and_usage.sql");
        String sql = Files.readString(migration);

        assertTrue(sql.contains("numeric(19,0)"));
        assertTrue(sql.contains("numeric(30,0)"));
        assertFalse(sql.toLowerCase().contains(" double precision"));
        assertFalse(sql.toLowerCase().contains(" real "));
        assertTrue(sql.contains("ALTER TABLE subscriptions"));
        assertTrue(sql.contains("ALTER TABLE quota_allocations"));
        assertTrue(sql.contains("ALTER TABLE usage_reservations"));
        assertTrue(sql.contains("ALTER TABLE usage_events"));
        assertTrue(sql.contains("ALTER TABLE usage_ledger_entries"));
        assertTrue(sql.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("elmos_reserve_usage"));
        assertTrue(sql.contains("FOR UPDATE"));
        assertTrue(sql.contains("USAGE_RESERVATION_IDEMPOTENCY_CONFLICT"));
        assertTrue(sql.contains("USAGE_RELEASE_IDEMPOTENCY_CONFLICT"));
        assertTrue(sql.contains("USAGE_ACTUAL_EXCEEDS_RESERVATION"));
        assertTrue(sql.contains("elmos_correct_usage"));
        assertTrue(sql.contains("TRIAL_ALREADY_USED"));
        assertTrue(sql.contains("'TRIALING'"));
        assertTrue(sql.contains("elmos_expire_current_trial"));
        assertTrue(sql.contains("elmos_enqueue_usage_alerts"));
        assertTrue(sql.contains("elmos_resolve_payment_reconciliation"));
        assertTrue(sql.contains("payment_provider_events_append_only"));
        assertTrue(sql.contains("payment_reconciliation_case_events_append_only"));
        assertTrue(sql.contains("failure_code varchar(96)"));
        assertTrue(sql.contains("REVOKE EXECUTE ON FUNCTION"));
        assertFalse(sql.contains("secret_value"));
    }
}
