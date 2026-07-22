package io.elmos.commercial;

import io.elmos.commercial.CommercialModels.*;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.*;

class CommercialOperationsTest {
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");

    @Test void assessmentEntitlementDoesNotGrantMigration() {
        var service = new EntitlementAndFulfillmentService();
        Entitlement assessment = entitlement("assessment.run", new BigDecimal("10"));
        assertEquals(EntitlementDecisionType.ALLOW,
                service.decide("org-a", "assessment.run", List.of(assessment), BigDecimal.ONE, false, false, "p1", NOW).decision());
        assertEquals(EntitlementDecisionType.DENY_NOT_ENTITLED,
                service.decide("org-a", "migration.execute", List.of(assessment), BigDecimal.ONE, false, false, "p1", NOW).decision());
    }

    @Test void entitlementConsumptionIsConcurrencySafe() throws Exception {
        var service = new EntitlementAndFulfillmentService();
        Entitlement entitlement = entitlement("assessment.run", BigDecimal.TEN);
        try (var executor = Executors.newFixedThreadPool(2)) {
            Callable<EntitlementDecision> task = () -> service.consume("org-a", "assessment.run", List.of(entitlement),
                    new BigDecimal("6"), "p1", NOW);
            var decisions = executor.invokeAll(List.of(task, task)).stream().map(future -> {
                try { return future.get(); } catch (Exception error) { throw new RuntimeException(error); }
            }).toList();
            assertEquals(1, decisions.stream().filter(value -> value.decision() == EntitlementDecisionType.ALLOW).count());
            assertEquals(1, decisions.stream().filter(value -> value.decision() == EntitlementDecisionType.DENY_LIMIT_EXCEEDED).count());
        }
    }

    @Test void expiredAllowanceCannotSubsidizeAValidEntitlement() {
        var service = new EntitlementAndFulfillmentService();
        Entitlement expired = new Entitlement("expired", "org-a", "migration.execute", EntitlementSource.ORDER,
                LimitType.USAGE, new BigDecimal("100"), BigDecimal.ZERO, NOW.minusSeconds(200), NOW.minusSeconds(100), true, true);
        Entitlement valid = new Entitlement("valid", "org-a", "migration.execute", EntitlementSource.ORDER,
                LimitType.USAGE, BigDecimal.ONE, BigDecimal.ZERO, NOW.minusSeconds(10), NOW.plusSeconds(100), true, true);
        EntitlementDecision decision = service.decide("org-a", "migration.execute", List.of(expired, valid),
                new BigDecimal("2"), false, false, "p1", NOW);
        assertEquals(EntitlementDecisionType.DENY_LIMIT_EXCEEDED, decision.decision());
        assertEquals(BigDecimal.ONE, decision.remainingAllowance());
    }

    @Test void duplicateOrderFulfillmentIsIdempotentAndPartialWorkIsVisible() {
        var service = new EntitlementAndFulfillmentService();
        CommercialOrder order = order(List.of(new OrderLine("l1", "PRIVATE_RUNNER", "runner.private",
                new BigDecimal("2"), "RUNNER", Map.of())));
        FulfillmentResult first = service.fulfill(order, NOW);
        FulfillmentResult duplicate = service.fulfill(order, NOW.plusSeconds(60));
        assertSame(first, duplicate);
        assertEquals(OrderStatus.PARTIALLY_FULFILLED, first.status());
        assertTrue(first.generatedObjectIds().stream().anyMatch(value -> value.startsWith("subscription-")));
    }

    @Test void fulfillmentIdempotencyIsTenantScopedAndRejectsChangedInput() {
        var service = new EntitlementAndFulfillmentService();
        CommercialOrder orgA = order(List.of(new OrderLine("l1", "PRIVATE_RUNNER", "runner.private",
                BigDecimal.ONE, "RUNNER", Map.of())));
        CommercialOrder changed = new CommercialOrder("order-2", "org-a", "quote-v1", OrderStatus.ACCEPTED,
                orgA.lines(), "contract-ref", orgA.fulfillmentIdempotencyKey());
        assertThrows(IllegalStateException.class, () -> { service.fulfill(orgA, NOW); service.fulfill(changed, NOW); });

        CommercialOrder orgB = new CommercialOrder("order-b", "org-b", "quote-v1", OrderStatus.ACCEPTED,
                orgA.lines(), "contract-ref", orgA.fulfillmentIdempotencyKey());
        FulfillmentResult result = service.fulfill(orgB, NOW);
        assertTrue(result.entitlements().stream().allMatch(value -> value.organizationId().equals("org-b")));
    }

    @Test void readinessBlocksMigrationWhenDependencyAccessFails() {
        var service = new OnboardingAndProjectService();
        List<ReadinessDimension> dimensions = readyDimensions();
        dimensions = dimensions.stream().map(value -> value.name().equals("DEPENDENCY")
                ? new ReadinessDimension("DEPENDENCY", ReadinessStatus.NOT_READY, "customer-build", List.of("probe"), List.of("maven-access"))
                : value).toList();
        OnboardingReadiness readiness = service.assessReadiness("org-a", "HYBRID_PRIVATE_RUNNER", dimensions);
        assertEquals(ReadinessStatus.NOT_READY, readiness.overallStatus());
        assertFalse(readiness.formalMigrationAllowed());
        assertEquals(List.of("maven-access"), readiness.blockingTaskIds());
    }

    @Test void readinessWithoutEvidenceCannotAuthorizeFormalMigration() {
        var service = new OnboardingAndProjectService();
        List<ReadinessDimension> dimensions = readyDimensions().stream().map(value -> value.name().equals("RUNNER")
                ? new ReadinessDimension("RUNNER", ReadinessStatus.READY, "owner", List.of(), List.of()) : value).toList();
        OnboardingReadiness readiness = service.assessReadiness("org-a", "HYBRID_PRIVATE_RUNNER", dimensions);
        assertEquals(ReadinessStatus.UNKNOWN, readiness.overallStatus());
        assertFalse(readiness.formalMigrationAllowed());
        assertTrue(readiness.blockingTaskIds().contains("READINESS_EVIDENCE_MISSING:RUNNER"));
    }

    @Test void scopeExpansionCreatesChangeRequestAndRecalculatesAllDomains() {
        var service = new OnboardingAndProjectService();
        ChangeRequest change = service.scopeChange("c1", "p1", "add repositories", 20, new BigDecimal("5"));
        assertEquals(new BigDecimal("100"), change.creditDelta());
        assertEquals(Set.of("RISK", "EFFORT", "COST", "MILESTONE", "ENTITLEMENT"), Set.copyOf(change.recalculationDomains()));
        assertFalse(change.approved());
    }

    @Test void failedCriticalGateCannotBeHiddenByHighProgress() {
        var service = new OnboardingAndProjectService();
        ProjectStatusSnapshot snapshot = service.projectStatus("p1", List.of(
                new ProjectStep("done", new BigDecimal("85"), true, false, true, "dev", null),
                new ProjectStep("transaction", new BigDecimal("15"), false, true, false, "dba", "TECHNICAL")),
                NOW.plusSeconds(100), NOW.plusSeconds(200), BigDecimal.TEN, new BigDecimal("100"), true, "looks good");
        assertEquals(new BigDecimal("0.8500"), snapshot.progress());
        assertEquals(ProjectHealth.RED, snapshot.health());
        assertFalse(snapshot.overrideApplied());
    }

    @Test void slaExclusionNeedsContractAndEvidence() {
        var service = new SlaAndSupportService();
        ServiceLevelObjective objective = new ServiceLevelObjective("slo", "PLATFORM_AVAILABILITY",
                new BigDecimal("99.9"), "PERCENT", "MONTHLY", "contract-1");
        ServiceLevelMeasurement missingEvidence = new ServiceLevelMeasurement("m1", "slo", new BigDecimal("99.0"),
                new BigDecimal("1.0"), null, NOW, NOW.plusSeconds(3600));
        assertTrue(service.evaluate(objective, missingEvidence, true, BigDecimal.ONE, BigDecimal.TEN).breached());
        ServiceLevelMeasurement evidenced = new ServiceLevelMeasurement("m2", "slo", new BigDecimal("99.0"),
                new BigDecimal("1.0"), "evidence-network", NOW, NOW.plusSeconds(3600));
        assertFalse(service.evaluate(objective, evidenced, true, BigDecimal.ONE, BigDecimal.TEN).breached());
    }

    @Test void evidenceIntegrityFailureCreatesSev1AgentCannotClose() {
        var service = new SlaAndSupportService();
        TicketContext context = new TicketContext("org-a", null, "run", null, null, "evidence", "sub", "sla");
        SupportTicket ticket = service.triage("t1", "INCIDENT", context, false, true, false,
                false, false, "broad verification failure", "immediate", List.of("sig-failure"));
        assertEquals(SupportSeverity.SEV1, ticket.severity());
        assertFalse(ticket.agentMayClose());
        assertNotNull(ticket.incidentCommander());
    }

    @Test void ticketDoesNotAutomaticallyAuthorizeSourceAccess() {
        var service = new SlaAndSupportService();
        TicketContext context = new TicketContext("org-a", "repo", "run", null, null, null, null, null);
        SupportTicket ticket = service.triage("t", "MIGRATION_FAILURE", context, false, false, false,
                false, true, "normal", "normal", List.of());
        assertThrows(SecurityException.class, () -> service.authorizeSupportAccess(ticket, "org-a", true, true, true, true));
    }

    @Test void customerPrivateAssetCannotBePublishedWithoutApproval() {
        var service = new AssetAndKnowledgeGovernance();
        RecipeAsset privateAsset = asset("CUSTOMER_PRIVATE", false);
        AssetDecision decision = service.evaluateListing(privateAsset, AssetVisibility.MARKETPLACE, true, true, true);
        assertFalse(decision.allowed());
        assertEquals(AssetVisibility.PRIVATE, decision.effectiveVisibility());
    }

    @Test void recalledAssetBlocksFutureUseAndPreservesHistory() {
        var service = new AssetAndKnowledgeGovernance();
        AssetDecision decision = service.recall(asset("ELMOS_OFFICIAL", true), "SEMANTIC_CORRUPTION");
        assertEquals(AssetCertification.BLOCKED, decision.effectiveCertification());
        assertTrue(decision.reasonCodes().contains("HISTORICAL_EVIDENCE_PRESERVED"));
    }

    @Test void generalizedKnowledgeRequiresAnonymizationReviewAndEvidence() {
        var service = new AssetAndKnowledgeGovernance();
        KnowledgeArticle article = new KnowledgeArticle("k", "org-a", "MIGRATION_PATTERN",
                KnowledgeTrust.EVIDENCE_BACKED, "ELMOS_INTERNAL", "customer: acme com.acme.billing at nexus.internal",
                List.of("e1"), false, false, "spring-5", "spring-6");
        KnowledgeDecision blocked = service.evaluateKnowledge(article, "org-a", true, true);
        assertFalse(blocked.usableForAgent());
        KnowledgeArticle approved = new KnowledgeArticle("k2", "org-a", "MIGRATION_PATTERN",
                KnowledgeTrust.EVIDENCE_BACKED, "ELMOS_INTERNAL", "generic example", List.of("e1"), true, true,
                "spring-5", "spring-6");
        assertTrue(service.evaluateKnowledge(approved, "org-a", true, true).usableForAgent());
    }

    @Test void lowUsageAfterCompletedPlanIsNotAutomaticallyAtRisk() {
        var service = new CustomerSuccessAndAnalyticsService();
        CustomerSignals signals = new CustomerSignals("org-a", new BigDecimal("0.1"), new BigDecimal("0.95"),
                new BigDecimal("0.9"), new BigDecimal("0.8"), true, false, false, 100, List.of("success-plan"));
        CustomerHealth health = service.health(signals);
        assertNotEquals(CustomerHealthStatus.AT_RISK, health.status());
        assertTrue(health.reasonCodes().contains("PLANNED_PROJECTS_COMPLETE"));
    }

    @Test void missingPrivateUsageIsNotRecordedAsZeroAndCostAnomalyIsVisible() {
        var service = new CustomerSuccessAndAnalyticsService();
        assertThrows(IllegalArgumentException.class, () -> service.metric("usage", BigDecimal.ZERO, MetricValueStatus.MISSING,
                "v1", "private", "month", "CNY", BigDecimal.ZERO));
        assertTrue(service.costAnomaly(new BigDecimal("400"), new BigDecimal("100"), new BigDecimal("3")));
    }

    @Test void repeatedCrossCustomerWorkCreatesProductizationCandidate() {
        var service = new CustomerSuccessAndAnalyticsService();
        ProductizationCandidate candidate = service.productizationCandidate("internal-api-v2",
                Map.of("a", 1, "b", 1, "c", 1, "d", 1, "e", 1), new BigDecimal("50"), List.of("e1", "e2"));
        assertEquals(5, candidate.distinctOrganizations());
        assertTrue(candidate.suggestedAssets().contains("CUSTOM_RECIPE"));
    }

    private static Entitlement entitlement(String feature, BigDecimal limit) {
        return new Entitlement("e-" + feature, "org-a", feature, EntitlementSource.ORDER, LimitType.USAGE,
                limit, BigDecimal.ZERO, NOW.minusSeconds(10), NOW.plusSeconds(3600), true, true);
    }
    private static CommercialOrder order(List<OrderLine> lines) {
        return new CommercialOrder("order-1", "org-a", "quote-v1", OrderStatus.ACCEPTED,
                lines, "contract-ref", "fulfill-order-1");
    }
    private static List<ReadinessDimension> readyDimensions() {
        return List.of("IDENTITY", "SCM", "RUNNER", "DEPENDENCY", "BUILD", "TEST", "SECURITY", "MODEL",
                        "GOVERNANCE", "SUPPORT", "PILOT").stream()
                .map(name -> new ReadinessDimension(name, ReadinessStatus.READY, "owner", List.of("e-" + name), List.of()))
                .toList();
    }
    private static RecipeAsset asset(String origin, boolean publicationApproved) {
        return new RecipeAsset("asset", "org-a", origin, AssetVisibility.PRIVATE, AssetCertification.UNVERIFIED,
                "1.0", "a".repeat(64), true, true, true, true, true, publicationApproved);
    }
}
