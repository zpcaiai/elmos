package io.elmos.persistence;

import io.elmos.commercial.SelfServiceBillingPort;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@EnabledIfEnvironmentVariable(named = "ELMOS_BILLING_TEST_JDBC_URL", matches = "jdbc:postgresql:.*")
class JdbcSelfServiceBillingLiveTest {
    @Test
    void exercisesTrialReservationSettlementHistoryAlertsAndConcurrentHardStop() throws Exception {
        Assumptions.assumeTrue("true".equals(
                System.getenv("ELMOS_BILLING_TEST_DISPOSABLE_CONFIRMED")));
        var fixtureDataSource = new DriverManagerDataSource(
                System.getenv("ELMOS_BILLING_TEST_JDBC_URL"),
                environment("ELMOS_BILLING_TEST_DATABASE_USERNAME", "postgres"),
                environment("ELMOS_BILLING_TEST_DATABASE_PASSWORD", "")
        );
        var runtimeDataSource = new DriverManagerDataSource(
                System.getenv("ELMOS_BILLING_TEST_JDBC_URL"),
                environment(
                        "ELMOS_BILLING_TEST_RUNTIME_USERNAME",
                        environment("ELMOS_BILLING_TEST_DATABASE_USERNAME", "postgres")),
                environment("ELMOS_BILLING_TEST_RUNTIME_PASSWORD", "")
        );
        var jdbc = JdbcClient.create(fixtureDataSource);
        SelfServiceBillingPort billing = new JdbcSelfServiceBillingStore(
                JdbcClient.create(runtimeDataSource),
                new TransactionTemplate(new DataSourceTransactionManager(runtimeDataSource))
        );
        String suffix = UUID.randomUUID().toString();
        String organization = "billing-it-" + suffix;
        String actor = "actor-" + suffix;
        jdbc.sql("""
                insert into organizations(organization_id, display_name, status)
                values (:organization, 'Billing integration test', 'ACTIVE')
                """).param("organization", organization).update();

        var trial = billing.grantTrial(
                organization, actor, sha256Identity(suffix), "trial-key-" + suffix);
        var preference = billing.saveAlertPreference(
                organization, actor, "ACTOR", List.of(5000, 8000, 10000),
                false, true, 0);
        assertEquals(1, preference.version());
        assertEquals(List.of(5000, 8000, 10000), preference.thresholdBps());
        var first = billing.reserve(
                organization, actor, trial.subscriptionId(), "reservation-" + suffix,
                "reservation-key-" + suffix, "model-inference",
                BigDecimal.valueOf(1_000_000), BigDecimal.ZERO, Instant.now().plusSeconds(600));
        assertEquals("RESERVED", first.decision());
        var settlement = billing.settle(
                organization, actor, first.reservationId(), "event-" + suffix,
                BigDecimal.valueOf(1_000_000), BigDecimal.ZERO, "INPUT",
                "TEST_PROVIDER", "provider-receipt-" + suffix,
                "CNY", new BigDecimal("1.250000"), Instant.now());
        assertEquals(new BigDecimal("1000000"), settlement.consumedTokens());
        assertEquals(1, billing.usageHistory(
                organization, actor, Instant.now().minusSeconds(60),
                Instant.now().plusSeconds(60), "HOUR").size());
        assertEquals(1, billing.usageAlerts(
                organization, actor, Instant.now().minusSeconds(60)).size());

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var left = executor.submit(() -> billing.reserve(
                    organization, actor, trial.subscriptionId(), "left-" + suffix,
                    "left-key-" + suffix, "verified-generation-or-migration",
                    BigDecimal.ZERO, BigDecimal.valueOf(40), Instant.now().plusSeconds(600)));
            var right = executor.submit(() -> billing.reserve(
                    organization, actor, trial.subscriptionId(), "right-" + suffix,
                    "right-key-" + suffix, "verified-generation-or-migration",
                    BigDecimal.ZERO, BigDecimal.valueOf(40), Instant.now().plusSeconds(600)));
            var decisions = List.of(left.get().decision(), right.get().decision());
            assertTrue(decisions.contains("RESERVED"));
            assertTrue(decisions.contains("DENY_CREDIT_LIMIT"));
        }

        String checkoutKey = "checkout-key-" + suffix;
        billing.prepareCheckout(
                organization, actor, "checkout-" + suffix, "elmos-pro-monthly",
                Instant.now().plusSeconds(1800), checkoutKey, sha256Identity("checkout-" + suffix));
        billing.markCheckoutReconciliationRequired(
                organization, actor, checkoutKey, "PROVIDER_RESULT_UNKNOWN");
        var openCases = billing.reconciliationCases(organization, actor, "OPEN", 10);
        assertEquals(1, openCases.size());
        billing.resolveReconciliationCase(
                organization, actor, openCases.getFirst().reconciliationCaseId(),
                "REJECTED", "manual-review-" + suffix, "recon-key-" + suffix);
        assertEquals(1, billing.reconciliationCases(organization, actor, "REJECTED", 10).size());

        String secondOrganization = "billing-it-other-" + suffix;
        jdbc.sql("""
                insert into organizations(organization_id, display_name, status)
                values (:organization, 'Billing integration test other', 'ACTIVE')
                """).param("organization", secondOrganization).update();
        assertThrows(RuntimeException.class, () -> billing.grantTrial(
                secondOrganization, actor, sha256Identity(suffix), "second-trial-key-" + suffix));

        jdbc.sql("""
                update trial_grants
                   set starts_at = current_timestamp - interval '2 days',
                       ends_at = current_timestamp - interval '1 second'
                 where trial_grant_id = :grant
                """).param("grant", trial.trialGrantId()).update();
        assertThrows(JdbcSelfServiceBillingStore.BillingStateException.class,
                () -> billing.currentUsage(organization, actor));
        assertEquals("EXPIRED", jdbc.sql("""
                select status from trial_grants where trial_grant_id = :grant
                """).param("grant", trial.trialGrantId()).query(String.class).single());
    }

    private static String environment(String name, String fallback) {
        String value = System.getenv(name);
        return value == null ? fallback : value;
    }

    private static String sha256Identity(String value) {
        try {
            return java.util.HexFormat.of().formatHex(
                    java.security.MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
