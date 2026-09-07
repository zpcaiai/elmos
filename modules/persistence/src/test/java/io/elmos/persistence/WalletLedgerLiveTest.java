package io.elmos.persistence;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Exercises the V73 accounting rules against a real PostgreSQL.
 *
 * <p>The point of this test is the refusals. A CHECK constraint or a BEFORE
 * trigger that was written but never fired is indistinguishable from one that
 * was never written, and money is the last place to accept that distinction on
 * trust. Every guard here is driven by attempting the illegal write and
 * asserting the database rejects it.
 *
 * <p>Gated on an explicit disposable-database confirmation, like
 * {@link JdbcSelfServiceBillingLiveTest}: it writes fixtures and races
 * transactions, and must never be pointed at anything real.
 */
@EnabledIfEnvironmentVariable(named = "ELMOS_WALLET_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
class WalletLedgerLiveTest {

    private static final BigDecimal TOPUP = new BigDecimal("100000");

    @Test void holdsSettlementsRefusalsAndConcurrencyBehaveAsTheMigrationPromises() throws Exception {
        Assumptions.assumeTrue("true".equals(
                System.getenv("ELMOS_WALLET_TEST_DISPOSABLE_CONFIRMED")));
        var dataSource = new DriverManagerDataSource(
                System.getenv("ELMOS_WALLET_TEST_JDBC_URL"),
                environment("ELMOS_WALLET_TEST_DATABASE_USERNAME", "postgres"),
                environment("ELMOS_WALLET_TEST_DATABASE_PASSWORD", ""));
        var jdbc = JdbcClient.create(dataSource);

        String organizationId = "org-wallet-" + UUID.randomUUID();
        jdbc.sql("INSERT INTO organizations (organization_id, display_name, data_region) "
                        + "VALUES (?, 'wallet live test', 'cn-north')")
                .param(organizationId).update();
        jdbc.sql("SELECT elmos_wallet_open(?)").param(organizationId).query(String.class).single();

        // ---- a confirmed top-up credits exactly once, however often it replays
        String tradeNo = "WX-" + UUID.randomUUID();
        createTopupOrder(jdbc, organizationId, "tu-" + tradeNo, "WECHAT_PAY", tradeNo, TOPUP);

        // The callback resolves its tenant from the directory projection before it
        // has any tenant context. Without that row the order is invisible under
        // FORCE row level security and the top-up silently goes unmatched.
        assertEquals(organizationId, jdbc
                .sql("SELECT organization_id FROM wallet_topup_order_directory WHERE out_trade_no = ?")
                .param(tradeNo).query(String.class).single());

        String firstEntry = creditTopup(jdbc, organizationId, "tu-" + tradeNo);
        assertEquals(firstEntry, creditTopup(jdbc, organizationId, "tu-" + tradeNo));
        assertEquals(firstEntry, creditTopup(jdbc, organizationId, "tu-" + tradeNo));
        assertEquals(TOPUP, balance(jdbc, organizationId));
        assertEquals(1, count(jdbc,
                "SELECT count(*) FROM wallet_ledger_entries WHERE organization_id = ? "
                        + "AND entry_type = 'TOPUP_SETTLED'", organizationId));

        // ---- a hold moves spendable, not balance, and is not a ledger movement
        reserve(jdbc, organizationId, "job-a", new BigDecimal("30000"), 3600);
        assertEquals(TOPUP, balance(jdbc, organizationId));
        assertEquals(new BigDecimal("30000"), reserved(jdbc, organizationId));
        assertEquals(1, count(jdbc,
                "SELECT count(*) FROM wallet_ledger_entries WHERE organization_id = ?", organizationId));

        // ---- the second hold is checked against spendable, not against balance
        var overReserve = assertThrows(Exception.class, () ->
                reserve(jdbc, organizationId, "job-b", new BigDecimal("80000"), 3600));
        assertTrue(overReserve.getMessage().contains("ELMOS_WALLET_INSUFFICIENT_BALANCE"),
                overReserve::getMessage);

        // ---- settlement charges at most the hold and hands back the difference
        settle(jdbc, organizationId, "job-a", new BigDecimal("12000"));
        assertEquals(new BigDecimal("88000"), balance(jdbc, organizationId));
        assertEquals(BigDecimal.ZERO, reserved(jdbc, organizationId));

        // ---- a settler retry is a no-op, not a second charge
        settle(jdbc, organizationId, "job-a", new BigDecimal("12000"));
        assertEquals(new BigDecimal("88000"), balance(jdbc, organizationId));
        assertEquals(1, count(jdbc,
                "SELECT count(*) FROM wallet_ledger_entries WHERE organization_id = ? "
                        + "AND entry_type = 'CONSUME'", organizationId));

        // ---- an over-quote is clamped to what the user was promised at submit time
        reserve(jdbc, organizationId, "job-c", new BigDecimal("5000"), 3600);
        settle(jdbc, organizationId, "job-c", new BigDecimal("999999"));
        assertEquals(new BigDecimal("5000"), jdbc
                .sql("SELECT settled_amount_minor FROM wallet_reservations "
                        + "WHERE organization_id = ? AND job_id = 'job-c'")
                .param(organizationId).query(BigDecimal.class).single());

        // ---- an unresolved hold is swept rather than freezing the tenant out
        reserve(jdbc, organizationId, "job-d", new BigDecimal("9000"), 60);
        jdbc.sql("UPDATE wallet_reservations SET held_at = now() - interval '2 hours', "
                        + "expires_at = now() - interval '1 hour' "
                        + "WHERE organization_id = ? AND job_id = 'job-d'")
                .param(organizationId).update();
        assertEquals(1, jdbc.sql("SELECT elmos_wallet_expire_reservations(?, 100)")
                .param(organizationId).query(Integer.class).single());
        assertEquals("EXPIRED", jdbc
                .sql("SELECT status FROM wallet_reservations WHERE organization_id = ? AND job_id = 'job-d'")
                .param(organizationId).query(String.class).single());
        assertEquals(BigDecimal.ZERO, reserved(jdbc, organizationId));

        // ---- every one of these must be refused by the database itself
        assertRefused(() -> jdbc.sql("UPDATE wallet_accounts SET balance_minor = 999999 "
                        + "WHERE organization_id = ?").param(organizationId).update(),
                "ELMOS_WALLET_BALANCE_DIRECT_MUTATION_DENIED");
        assertRefused(() -> jdbc.sql("UPDATE wallet_accounts SET reserved_minor = 5 "
                        + "WHERE organization_id = ?").param(organizationId).update(),
                "ELMOS_WALLET_BALANCE_DIRECT_MUTATION_DENIED");
        assertRefused(() -> jdbc.sql("DELETE FROM wallet_accounts WHERE organization_id = ?")
                        .param(organizationId).update(),
                "ELMOS_WALLET_DELETE_DENIED");
        assertRefused(() -> jdbc.sql("UPDATE wallet_ledger_entries SET amount_minor = 1 "
                        + "WHERE organization_id = ?").param(organizationId).update(),
                "append-only");
        assertRefused(() -> jdbc.sql("DELETE FROM wallet_ledger_entries WHERE organization_id = ?")
                        .param(organizationId).update(),
                "append-only");
        assertRefused(() -> jdbc.sql("UPDATE wallet_reservations SET status = 'HELD' "
                        + "WHERE organization_id = ? AND job_id = 'job-a'").param(organizationId).update(),
                "ELMOS_WALLET_RESERVATION_TERMINAL_IMMUTABLE");
        assertRefused(() -> jdbc.sql("UPDATE wallet_topup_orders SET amount_minor = 1 "
                        + "WHERE organization_id = ?").param(organizationId).update(),
                "IMMUTABLE");
        assertRefused(() -> jdbc.sql("UPDATE wallet_price_book SET reserve_minor = 1 "
                        + "WHERE business_line = 'GENERATION'").update(),
                "append-only");

        // ---- moving money by hand without saying why is refused; with a reason it
        //      is recorded once, however many times the administrator clicks
        assertRefused(() -> jdbc.sql("SELECT elmos_wallet_adjust(?, 'CREDIT', 100, 'admin-1', NULL, ?)")
                        .params(organizationId, "idem-noreason").query(String.class).single(),
                "ELMOS_WALLET_ADJUSTMENT_REASON_REQUIRED");
        assertRefused(() -> jdbc.sql("SELECT elmos_wallet_adjust(?, 'DEBIT', 99999999, 'admin-1', "
                                + "'attempt to overdraw', ?)")
                        .params(organizationId, "idem-overdraw").query(String.class).single(),
                "ELMOS_WALLET_INSUFFICIENT_BALANCE");
        adjust(jdbc, organizationId, "客服补偿工单", "idem-adjust");
        adjust(jdbc, organizationId, "客服补偿工单", "idem-adjust");
        assertEquals(1, count(jdbc,
                "SELECT count(*) FROM wallet_ledger_entries WHERE organization_id = ? "
                        + "AND entry_type = 'ADMIN_ADJUSTMENT'", organizationId));

        // ---- the projection must equal the authority, on both columns
        assertNoDrift(jdbc, organizationId);

        // ---- and the ledger must prove itself by replay, without consulting the
        //      projection at all
        assertTrue(jdbc.sql("SELECT bool_and(replayed = balance_after_minor) FROM ("
                        + "  SELECT balance_after_minor, sum(CASE WHEN direction = 'CREDIT' "
                        + "    THEN amount_minor ELSE -amount_minor END) "
                        + "    OVER (PARTITION BY organization_id ORDER BY seq) AS replayed "
                        + "  FROM wallet_ledger_entries WHERE organization_id = ?) t")
                .param(organizationId).query(Boolean.class).single());

        concurrentHoldsCannotOverCommitOneBalance(dataSource);
    }

    /**
     * Eight callers race for a balance that can only cover three of them. The
     * interesting assertion is not that some fail -- it is that the survivors sum
     * to no more than the balance, which is what a lost update would break.
     */
    private void concurrentHoldsCannotOverCommitOneBalance(DriverManagerDataSource dataSource)
            throws Exception {
        var jdbc = JdbcClient.create(dataSource);
        String organizationId = "org-race-" + UUID.randomUUID();
        String tradeNo = "ALI-" + UUID.randomUUID();
        jdbc.sql("INSERT INTO organizations (organization_id, display_name, data_region) "
                        + "VALUES (?, 'wallet race test', 'cn-north')").param(organizationId).update();
        createTopupOrder(jdbc, organizationId, "tu-" + tradeNo, "ALIPAY", tradeNo, TOPUP);
        creditTopup(jdbc, organizationId, "tu-" + tradeNo);

        var pool = Executors.newFixedThreadPool(8);
        try {
            List<Callable<Boolean>> attempts = java.util.stream.IntStream.range(0, 8)
                    .<Callable<Boolean>>mapToObj(index -> () -> {
                        try {
                            reserve(JdbcClient.create(dataSource), organizationId,
                                    "race-job-" + index, new BigDecimal("30000"), 3600);
                            return true;
                        } catch (Exception refused) {
                            return false;
                        }
                    })
                    .toList();
            long granted = 0;
            for (Future<Boolean> attempt : pool.invokeAll(attempts)) {
                if (attempt.get()) {
                    granted++;
                }
            }
            assertEquals(3, granted, "a 100000 balance can back exactly three 30000 holds");
        } finally {
            pool.shutdownNow();
        }

        assertEquals(new BigDecimal("90000"), reserved(jdbc, organizationId));
        assertTrue(reserved(jdbc, organizationId).compareTo(balance(jdbc, organizationId)) <= 0,
                "held money must be money that is actually there");
        assertNoDrift(jdbc, organizationId);
    }

    private void assertNoDrift(JdbcClient jdbc, String organizationId) {
        var drift = jdbc.sql("SELECT projected_balance_minor - ledger_balance_minor "
                        + "|| '/' || (projected_reserved_minor - held_reserved_minor) "
                        + "FROM elmos_wallet_reconcile(?)")
                .param(organizationId).query(String.class).single();
        assertEquals("0/0", drift, "wallet projection drifted from its ledger");
    }

    private static void assertRefused(Runnable illegalWrite, String expectedCode) {
        var refusal = assertThrows(Exception.class, illegalWrite::run);
        String message = String.valueOf(refusal.getMessage());
        assertTrue(message.contains(expectedCode),
                () -> "expected refusal containing " + expectedCode + " but got " + message);
        assertNotEquals("", message);
    }

    private static String creditTopup(JdbcClient jdbc, String organizationId, String topupOrderId) {
        // The organization is passed explicitly because the real caller is a
        // payment callback that resolved it from wallet_topup_order_directory and
        // holds no tenant context of its own.
        return jdbc.sql("SELECT elmos_wallet_credit_topup(?, ?, 'txn', 'actor-1')")
                .params(organizationId, topupOrderId).query(String.class).single();
    }

    private static void createTopupOrder(JdbcClient jdbc, String organizationId,
                                         String topupOrderId, String provider,
                                         String outTradeNo, BigDecimal amount) {
        jdbc.sql("SELECT elmos_wallet_create_topup_order(?, ?, 'actor-1', ?, ?, ?, ?, 3600)")
                .params(topupOrderId, organizationId, amount, provider, outTradeNo,
                        "idem-" + outTradeNo)
                .query(String.class).single();
    }

    private static void reserve(JdbcClient jdbc, String organizationId, String jobId,
                                BigDecimal amount, int ttlSeconds) {
        jdbc.sql("SELECT elmos_wallet_reserve(?, ?, ?, ?, 'test-quote', 'actor-1', ?)")
                .params("res-" + organizationId + "-" + jobId, organizationId, jobId, amount, ttlSeconds)
                .query(String.class).single();
    }

    private static void settle(JdbcClient jdbc, String organizationId, String jobId, BigDecimal amount) {
        jdbc.sql("SELECT elmos_wallet_settle(?, ?, ?, 'settler', 'SUCCEEDED')")
                .params(organizationId, jobId, amount).query(String.class).single();
    }

    private static void adjust(JdbcClient jdbc, String organizationId, String reason, String key) {
        jdbc.sql("SELECT elmos_wallet_adjust(?, 'CREDIT', 2500, 'admin-1', ?, ?)")
                .params(organizationId, reason, key).query(String.class).single();
    }

    private static BigDecimal balance(JdbcClient jdbc, String organizationId) {
        return jdbc.sql("SELECT balance_minor FROM wallet_accounts WHERE organization_id = ?")
                .param(organizationId).query(BigDecimal.class).single();
    }

    private static BigDecimal reserved(JdbcClient jdbc, String organizationId) {
        return jdbc.sql("SELECT reserved_minor FROM wallet_accounts WHERE organization_id = ?")
                .param(organizationId).query(BigDecimal.class).single();
    }

    private static int count(JdbcClient jdbc, String sql, String organizationId) {
        return jdbc.sql(sql).param(organizationId).query(Integer.class).single();
    }

    private static String environment(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
