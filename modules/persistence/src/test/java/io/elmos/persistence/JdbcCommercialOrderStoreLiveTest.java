package io.elmos.persistence;

import io.elmos.commercial.CommercialOrderPort;
import io.elmos.commercial.SelfServiceBillingPort;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.Statement;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Real PostgreSQL proof for V83 order fulfillment, Credit accounting and entitlements. */
@Testcontainers(disabledWithoutDocker = true)
class JdbcCommercialOrderStoreLiveTest {
    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:17.5-alpine");

    private static final String RUNTIME_USER = "elmos_commercial_order_live";
    private static final String RUNTIME_PASSWORD = "commercial-order-live-only";
    private static JdbcClient admin;
    private static JdbcClient runtime;
    private static CommercialOrderPort orders;
    private static DriverManagerDataSource adminDataSource;
    private static DriverManagerDataSource runtimeDataSource;

    @BeforeAll
    static void migrateAndCreateLeastPrivilegeRuntime() throws Exception {
        Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .defaultSchema("public")
                .load()
                .migrate();
        adminDataSource = dataSource(POSTGRES.getUsername(), POSTGRES.getPassword());
        admin = JdbcClient.create(adminDataSource);
        try (Connection connection = adminDataSource.getConnection();
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE ROLE " + RUNTIME_USER + " LOGIN PASSWORD '"
                    + RUNTIME_PASSWORD + "' NOSUPERUSER NOBYPASSRLS NOINHERIT");
            statement.execute("GRANT USAGE ON SCHEMA public TO " + RUNTIME_USER);
            statement.execute("GRANT USAGE ON SCHEMA identity, ai_usage, billing TO "
                    + RUNTIME_USER);
            statement.execute("GRANT SELECT ON commercial_products, commercial_orders, "
                    + "commercial_order_directory, commercial_credit_accounts, "
                    + "commercial_credit_lots, commercial_credit_ledger_entries, "
                    + "project_generation_entitlements, commercial_credit_reservations, "
                    + "commercial_credit_reservation_lots TO " + RUNTIME_USER);
            statement.execute("GRANT SELECT ON usage_events, usage_ledger_entries, "
                    + "identity.accounts, ai_usage.model_calls, billing.token_usage_events TO "
                    + RUNTIME_USER);
            statement.execute("GRANT SELECT, INSERT ON payment_callback_receipts TO "
                    + RUNTIME_USER);
            statement.execute("GRANT UPDATE (processing_status, attempt_count, updated_at) "
                    + "ON payment_callback_receipts TO " + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_commercial_create_order(varchar,varchar,varchar,varchar,varchar,"
                    + "varchar,varchar,char,integer) TO " + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_commercial_fulfill_order(varchar,varchar,varchar,varchar) TO "
                    + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_commercial_mark_order_handoff(varchar,varchar) TO " + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_commercial_mark_order_prepare_failed(varchar,varchar,boolean,varchar) TO "
                    + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_commercial_reserve_generation(varchar,varchar,varchar,varchar,"
                    + "numeric,varchar,integer) TO " + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_commercial_settle_generation(varchar,varchar,numeric) TO "
                    + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION "
                    + "elmos_commercial_release_generation(varchar,varchar) TO " + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION elmos_expire_current_trial() TO "
                    + RUNTIME_USER);
            statement.execute("GRANT EXECUTE ON FUNCTION elmos_current_organization_id() TO "
                    + RUNTIME_USER);
        }
        runtimeDataSource = dataSource(RUNTIME_USER, RUNTIME_PASSWORD);
        runtime = JdbcClient.create(runtimeDataSource);
        orders = new JdbcCommercialOrderStore(
                runtime, new TransactionTemplate(new DataSourceTransactionManager(runtimeDataSource)));
    }

    @Test
    void fulfillsExactlyOnceAndAccountsForCreditAndOneTimeGeneration() throws Exception {
        String suffix = UUID.randomUUID().toString();
        String organization = "commercial-live-" + suffix;
        insertOrganization(organization);

        String creditOrder = createOrder(
                organization, "actor-a", "credit-order-" + suffix,
                "elmos-credit-500", null, "credit-idem-" + suffix);
        assertEquals(creditOrder, createOrder(
                organization, "actor-a", "ignored-order-" + suffix,
                "elmos-credit-500", null, "credit-idem-" + suffix));
        var persisted = orders.findOrder(organization, creditOrder).orElseThrow();
        assertEquals(new BigDecimal("9900"), persisted.amountMinor());
        assertEquals(new BigDecimal("500"), persisted.creditQuantity());
        assertEquals("PENDING_PAYMENT", orders.markOrderAwaitingPayment(
                organization, "actor-a", creditOrder));
        assertEquals("PENDING_PAYMENT", orders.findOrder(
                organization, creditOrder).orElseThrow().status());
        assertEquals(organization, runtime.sql("select organization_id "
                        + "from commercial_order_directory where out_trade_no = ?")
                .param(creditOrder).query(String.class).single());

        fulfill(organization, creditOrder, "provider-credit-" + suffix);
        fulfill(organization, creditOrder, "provider-credit-" + suffix);
        assertBalance(organization, "500", "0", "500");
        assertEquals(1, orders.creditLedger(organization, "actor-a", 20, 0, false).size());
        assertEquals(1, count("select count(*) from commercial_credit_lots "
                + "where organization_id = ?", organization));

        var hold = orders.reserveGeneration(
                "reservation-" + suffix, organization, "actor-a", "project-a", "job-a",
                new BigDecimal("60"), "reserve-idem-" + suffix, 600);
        assertEquals("RESERVED", hold.decision());
        assertEquals("CREDIT_ACCOUNT", hold.fundingSource());
        assertThrows(RuntimeException.class, () -> orders.settleGeneration(
                organization, "actor-b", hold.reservationId(), new BigDecimal("45")));
        assertEquals("SETTLED", orders.settleGeneration(
                organization, "actor-a", hold.reservationId(), new BigDecimal("45")));
        assertEquals("SETTLED", orders.settleGeneration(
                organization, "actor-a", hold.reservationId(), new BigDecimal("45")));
        assertBalance(organization, "455", "0", "455");
        assertEquals(List.of("GENERATION", "PURCHASE"), orders.creditLedger(
                organization, "actor-a", 20, 0, false).stream()
                .map(CommercialOrderPort.CreditLedgerEntry::entryType).toList());

        var released = orders.reserveGeneration(
                "release-reservation-" + suffix, organization, "actor-a", "project-a", "job-release",
                new BigDecimal("50"), "release-idem-" + suffix, 600);
        assertEquals("RELEASED", orders.releaseGeneration(
                organization, "actor-a", released.reservationId()));
        assertEquals("RELEASED", orders.releaseGeneration(
                organization, "actor-a", released.reservationId()));
        assertBalance(organization, "455", "0", "455");

        String oneTimeOrder = createOrder(
                organization, "actor-a", "one-time-order-" + suffix,
                "elmos-project-generation-once", "project-once", "one-time-idem-" + suffix);
        fulfill(organization, oneTimeOrder, "provider-once-" + suffix);
        var oneTimeHold = orders.reserveGeneration(
                "one-time-reservation-" + suffix, organization, "actor-a", "project-once", "job-once",
                new BigDecimal("60"), "one-time-reserve-" + suffix, 600);
        assertEquals("ONE_TIME_ENTITLEMENT", oneTimeHold.fundingSource());
        assertEquals("SETTLED", orders.settleGeneration(
                organization, "actor-a", oneTimeHold.reservationId(), new BigDecimal("60")));
        assertEquals("CONSUMED", inTenant(organization, "select status "
                + "from project_generation_entitlements where source_order_id = ?", oneTimeOrder));
        assertBalance(organization, "455", "0", "455");

        concurrentReservationsCannotOvercommit(organization, suffix);
        assertTrue(orders.creditBalance(organization).reserved()
                .compareTo(orders.creditBalance(organization).balance()) <= 0);
        assertEquals(creditOrder, orders.orders(
                organization, "actor-a", 20, 0, false).stream()
                .filter(order -> order.orderType().equals("CREDIT_PACK"))
                .findFirst().orElseThrow().orderId());
    }

    @Test
    void projectEntitlementAndTenantScopeFailClosed() {
        String suffix = UUID.randomUUID().toString();
        String organization = "commercial-scope-a-" + suffix;
        String otherOrganization = "commercial-scope-b-" + suffix;
        insertOrganization(organization);
        insertOrganization(otherOrganization);
        String order = createOrder(
                organization, "actor-a", "scope-order-" + suffix,
                "elmos-project-generation-once", "project-a", "scope-idem-" + suffix);
        fulfill(organization, order, "scope-provider-" + suffix);

        var wrongProject = orders.reserveGeneration(
                "scope-res-wrong-" + suffix, organization, "actor-a", "project-b", "scope-job-b",
                new BigDecimal("60"), "scope-res-idem-wrong-" + suffix, 600);
        assertEquals("DENY_CREDIT_LIMIT", wrongProject.decision());
        assertTrue(orders.findOrder(otherOrganization, order).isEmpty());
        assertThrows(RuntimeException.class, () -> fulfill(
                otherOrganization, order, "scope-provider-" + suffix));

        String failedOrder = createOrder(
                organization, "actor-a", "failed-order-" + suffix,
                "elmos-credit-500", null, "failed-idem-" + suffix);
        assertEquals("FAILED", orders.markOrderPreparationFailed(
                organization, "actor-a", failedOrder, false, "CHECKOUT_PREPARE_FAILED"));
        assertEquals("CHECKOUT_PREPARE_FAILED", orders.findOrder(
                organization, failedOrder).orElseThrow().failureCode());

        String unknownOrder = createOrder(
                organization, "actor-a", "unknown-order-" + suffix,
                "elmos-credit-500", null, "unknown-idem-" + suffix);
        assertEquals("RECONCILIATION_REQUIRED", orders.markOrderPreparationFailed(
                organization, "actor-a", unknownOrder, true,
                "CHECKOUT_PREPARE_OUTCOME_UNKNOWN"));

        String expiredOrder = createOrder(
                organization, "actor-a", "expired-order-" + suffix,
                "elmos-credit-500", null, "expired-idem-" + suffix);
        admin.sql("update commercial_orders set created_at = now() - interval '2 seconds', "
                        + "expires_at = now() - interval '1 second' "
                        + "where order_id = ?")
                .param(expiredOrder).update();
        fulfill(organization, expiredOrder, "late-provider-" + suffix);
        var late = orders.findOrder(organization, expiredOrder).orElseThrow();
        assertEquals("RECONCILIATION_REQUIRED", late.status());
        assertEquals("PAYMENT_AFTER_LOCAL_EXPIRY", late.failureCode());
        assertTrue(orders.creditLedger(organization, "actor-a", 20, 0, false).isEmpty());
    }

    @Test
    void preservesSelfScopedRawTokenHistoryAndExecutionDimensions() {
        String suffix = UUID.randomUUID().toString();
        String organization = "commercial-usage-" + suffix;
        insertOrganization(organization);
        SelfServiceBillingPort billing = new JdbcSelfServiceBillingStore(
                admin, new TransactionTemplate(new DataSourceTransactionManager(adminDataSource)));
        var trial = billing.grantTrial(
                organization, "actor-token", "b".repeat(64), "trial-idem-" + suffix);
        var reservation = billing.reserveDetailed(
                organization, "actor-token", trial.subscriptionId(),
                "token-res-" + suffix, "token-res-idem-" + suffix, "model-inference",
                new BigDecimal("1000"), BigDecimal.ZERO,
                java.time.Instant.now().plusSeconds(600),
                "project-token", "job-token", "openai/gpt-6-astra");
        assertEquals("RESERVED", reservation.decision());
        assertEquals(reservation.reservationId(), billing.reserveDetailed(
                organization, "actor-token", trial.subscriptionId(),
                "ignored-token-res-" + suffix, "token-res-idem-" + suffix, "model-inference",
                new BigDecimal("1000"), BigDecimal.ZERO,
                java.time.Instant.now().plusSeconds(600),
                "project-token", "job-token", "openai/gpt-6-astra").reservationId());
        assertThrows(RuntimeException.class, () -> billing.reserveDetailed(
                organization, "actor-token", trial.subscriptionId(),
                "ignored-token-conflict-" + suffix, "token-res-idem-" + suffix, "model-inference",
                new BigDecimal("1000"), BigDecimal.ZERO,
                java.time.Instant.now().plusSeconds(600),
                "project-token", "job-token", "different-model"));
        assertThrows(RuntimeException.class, () -> billing.settle(
                organization, "actor-other", reservation.reservationId(),
                "token-event-wrong-" + suffix, new BigDecimal("750"), BigDecimal.ZERO,
                "OUTPUT", "OPENAI", "provider-token-" + suffix,
                "CNY", new BigDecimal("12.340000"), java.time.Instant.now()));
        billing.settle(
                organization, "actor-token", reservation.reservationId(),
                "token-event-" + suffix, new BigDecimal("750"), BigDecimal.ZERO,
                "OUTPUT", "OPENAI", "provider-token-" + suffix,
                "CNY", new BigDecimal("12.340000"), java.time.Instant.now());

        var from = java.time.Instant.now().minusSeconds(60);
        var to = java.time.Instant.now().plusSeconds(60);
        var history = billing.usageHistory(
                organization, "actor-token", from, to, "HOUR", false);
        assertEquals(1, history.size());
        assertEquals("actor-token", history.getFirst().actorId());
        assertEquals("project-token", history.getFirst().projectId());
        assertEquals("job-token", history.getFirst().jobId());
        assertEquals("openai/gpt-6-astra", history.getFirst().model());
        assertEquals(new BigDecimal("750"), history.getFirst().net());

        var events = billing.usageEvents(
                organization, "actor-token", from, to, 100, 0, false);
        assertEquals(1, events.size());
        assertEquals("provider-token-" + suffix, events.getFirst().providerReceiptRef());
        assertEquals("RECONCILED", events.getFirst().reconciliationStatus());
        assertEquals("OUTPUT", events.getFirst().tokenClass());
        assertEquals("openai/gpt-6-astra", events.getFirst().model());
        assertTrue(billing.usageEvents(
                organization, "actor-other", from, to, 100, 0, false).isEmpty());
        assertEquals(1, billing.usageEvents(
                organization, "actor-other", from, to, 100, 0, true).size());
    }

    @Test
    void callbackClaimCanBeRetriedAfterFailureButNotAfterCompletion() {
        String key = "ALIPAY_CHECKOUT:event-" + UUID.randomUUID();
        assertTrue(claimCallback(key));
        assertTrue(!claimCallback(key));
        markCallback(key, "FAILED");
        assertTrue(claimCallback(key));
        markCallback(key, "COMPLETED");
        assertTrue(!claimCallback(key));
        assertEquals(2, admin.sql("select attempt_count from payment_callback_receipts "
                        + "where provider = 'ALIPAY_CHECKOUT' and provider_event_id = ?")
                .param(key.substring(key.indexOf(':') + 1)).query(Integer.class).single());
    }

    @Test
    void includesProductionProviderUsageInPerUserHistoryWithoutLosingTokenClasses() {
        UUID tenant = UUID.randomUUID();
        UUID account = UUID.randomUUID();
        UUID project = UUID.randomUUID();
        UUID modelCall = UUID.randomUUID();
        UUID providerPrice = UUID.randomUUID();
        UUID commercialPrice = UUID.randomUUID();
        String organization = tenant.toString();
        String actor = "actor-production-" + tenant;
        insertOrganization(organization);
        admin.sql("insert into identity.tenants(id, name) values (?, 'usage tenant')")
                .param(tenant).update();
        admin.sql("insert into identity.accounts(id, tenant_id, external_subject) values (?, ?, ?)")
                .params(account, tenant, actor).update();
        admin.sql("insert into project.projects(id, tenant_id, account_id, name, project_type) "
                        + "values (?, ?, ?, 'usage project', 'GENERATION')")
                .params(project, tenant, account).update();
        admin.sql("insert into billing.provider_pricing_versions(id, name, effective_from) "
                        + "values (?, 'provider-v1', now() - interval '1 day')")
                .param(providerPrice).update();
        admin.sql("insert into billing.commercial_pricing_versions(id, name, effective_from) "
                        + "values (?, 'commercial-v1', now() - interval '1 day')")
                .param(commercialPrice).update();
        admin.sql("insert into ai_usage.model_calls(id, tenant_id, account_id, project_id, "
                        + "provider, model, idempotency_key, status, completed_at) "
                        + "values (?, ?, ?, ?, 'OPENAI', 'gpt-production', ?, 'COMPLETE', now())")
                .params(modelCall, tenant, account, project, "model-call-" + modelCall).update();
        admin.sql("insert into billing.token_usage_events(id, tenant_id, model_call_id, "
                        + "provider, model, provider_usage_id, provider_pricing_version_id, "
                        + "commercial_pricing_version_id, input_tokens, cached_input_tokens, "
                        + "output_tokens, reasoning_tokens, provider_total_cost, customer_credit_cost) "
                        + "values (?, ?, ?, 'OPENAI', 'gpt-production', ?, ?, ?, 100, 20, 30, 10, 1, 2)")
                .params(UUID.randomUUID(), tenant, modelCall, "provider-usage-" + modelCall,
                        providerPrice, commercialPrice).update();

        SelfServiceBillingPort billing = new JdbcSelfServiceBillingStore(
                runtime, new TransactionTemplate(new DataSourceTransactionManager(runtimeDataSource)));
        var from = java.time.Instant.now().minusSeconds(60);
        var to = java.time.Instant.now().plusSeconds(60);
        var events = billing.usageEvents(organization, actor, from, to, 100, 0, false);
        assertEquals(4, events.size());
        assertEquals(List.of("CACHE_READ", "INPUT", "OUTPUT", "REASONING"), events.stream()
                .map(SelfServiceBillingPort.UsageEventDetail::tokenClass).sorted().toList());
        assertEquals(new BigDecimal("160"), events.stream()
                .map(SelfServiceBillingPort.UsageEventDetail::quantity)
                .reduce(BigDecimal.ZERO, BigDecimal::add));
        assertTrue(billing.usageEvents(
                organization, "actor-other", from, to, 100, 0, false).isEmpty());
        assertEquals(4, billing.usageEvents(
                organization, "actor-other", from, to, 100, 0, true).size());
        assertEquals(4, billing.usageHistory(
                organization, actor, from, to, "HOUR", false).size());
    }

    private void concurrentReservationsCannotOvercommit(String organization, String suffix)
            throws Exception {
        try (var executor = Executors.newFixedThreadPool(8)) {
            List<Callable<String>> calls = java.util.stream.IntStream.range(0, 8)
                    .<Callable<String>>mapToObj(index -> () -> orders.reserveGeneration(
                            "race-res-" + index + "-" + suffix, organization, "actor-a",
                            "race-project", "race-job-" + index,
                            new BigDecimal("100"), "race-idem-" + index + "-" + suffix, 600)
                            .decision())
                    .toList();
            long accepted = 0;
            for (var future : executor.invokeAll(calls)) {
                if ("RESERVED".equals(future.get())) accepted++;
            }
            assertEquals(4, accepted, "455 Credits can back exactly four concurrent 100 holds");
        }
    }

    private static String createOrder(String organization, String actor, String orderId,
                                      String sku, String project, String idempotency) {
        return orders.createOrder(orderId, organization, actor, sku, project,
                "WECHAT_PAY_NATIVE", orderId, idempotency, "a".repeat(64), 1800);
    }

    private static void fulfill(String organization, String orderId, String providerReference) {
        assertEquals(orderId, runtime.sql(
                        "select elmos_commercial_fulfill_order(?, ?, ?, 'payment-callback')")
                .params(organization, orderId, providerReference).query(String.class).single());
    }

    private static void insertOrganization(String organization) {
        admin.sql("insert into organizations(organization_id, display_name, status) "
                        + "values (?, 'Commercial live test', 'ACTIVE')")
                .param(organization).update();
    }

    private static void assertBalance(String organization, String balance,
                                      String reserved, String spendable) {
        var value = orders.creditBalance(organization);
        assertEquals(new BigDecimal(balance), value.balance());
        assertEquals(new BigDecimal(reserved), value.reserved());
        assertEquals(new BigDecimal(spendable), value.spendable());
    }

    private static int count(String sql, String organization) {
        return admin.sql(sql).param(organization).query(Integer.class).single();
    }

    private static String inTenant(String organization, String sql, String argument) {
        var dataSource = dataSource(RUNTIME_USER, RUNTIME_PASSWORD);
        var transaction = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
        return transaction.execute(status -> {
            var jdbc = JdbcClient.create(dataSource);
            jdbc.sql("select set_config('app.organization_id', ?, true)")
                    .param(organization).query(String.class).single();
            return jdbc.sql(sql).param(argument).query(String.class).single();
        });
    }

    private static boolean claimCallback(String key) {
        String event = key.substring(key.indexOf(':') + 1);
        return runtime.sql("""
                insert into payment_callback_receipts (
                    provider, provider_event_id, processing_status)
                values ('ALIPAY_CHECKOUT', ?, 'PROCESSING')
                on conflict (provider, provider_event_id) do update
                   set processing_status = 'PROCESSING',
                       attempt_count = payment_callback_receipts.attempt_count + 1,
                       updated_at = now()
                 where payment_callback_receipts.processing_status = 'FAILED'
                    or (payment_callback_receipts.processing_status = 'PROCESSING'
                        and payment_callback_receipts.updated_at < now() - interval '5 minutes')
                returning provider_event_id
                """).param(event).query(String.class).optional().isPresent();
    }

    private static void markCallback(String key, String status) {
        String event = key.substring(key.indexOf(':') + 1);
        assertEquals(1, runtime.sql("update payment_callback_receipts "
                        + "set processing_status = ?, updated_at = now() "
                        + "where provider = 'ALIPAY_CHECKOUT' and provider_event_id = ? "
                        + "and processing_status = 'PROCESSING'")
                .params(status, event).update());
    }

    private static DriverManagerDataSource dataSource(String user, String password) {
        return new DriverManagerDataSource(POSTGRES.getJdbcUrl(), user, password);
    }
}
