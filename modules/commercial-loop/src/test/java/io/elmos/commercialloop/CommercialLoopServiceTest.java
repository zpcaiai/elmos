package io.elmos.commercialloop;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.luben.zstd.ZstdInputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;

import static io.elmos.commercialloop.CommercialLoopModels.*;
import static org.junit.jupiter.api.Assertions.*;

class CommercialLoopServiceTest {
    private static final String DIGEST = "c".repeat(64);
    private static final String RUN = "commercial-assessment-1";
    private static final String VERSION = "commercial-operations-v1";
    private static final Instant NOW = Instant.parse("2026-07-21T05:00:00Z");
    @TempDir Path temp;

    @Test void completeExternalEvidenceReachesCommercialScaleGate() {
        Outcome outcome = evaluate(request(), Evidence.good());
        assertEquals(Gate.B13_G, outcome.report().gate());
        assertEquals(RunStatus.COMMERCIAL_SCALE_READY, outcome.report().status());
        assertTrue(outcome.report().externalEvidenceComplete());
        assertTrue(outcome.report().commercialScaleReady());
        assertFalse(outcome.report().commercialOperationExecuted());
    }

    @Test void admissionRequiresSignedBatch12TgArtifact() {
        Request base = request();
        BusinessArtifact invalid = new BusinessArtifact(VERSION, DIGEST, true, true, false,
                "sbom", "provenance", List.of("evidence"));
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(base, invalid, base.domains(), base.motions(), base.lifecycleRecords()), Evidence.good()));
    }

    @Test void allEightDomainsAreRequired() {
        Request base = request();
        List<DomainProfile> missing = base.domains().stream().filter(value -> value.domain() != CommercialDomain.GO_TO_MARKET).toList();
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(base, base.platformBusiness(), missing, base.motions(), base.lifecycleRecords()), Evidence.good()));
    }

    @Test void allSixCommercialMotionsAreRequired() {
        Request base = request();
        List<MotionProfile> missing = base.motions().stream().filter(value -> value.motion() != CommercialMotion.DIRECT_SALES).toList();
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(base, base.platformBusiness(), base.domains(), missing, base.lifecycleRecords()), Evidence.good()));
    }

    @Test void lifecycleCannotEnterStageWithoutCriteriaEvidence() {
        Request base = request(); LifecycleRecord value = base.lifecycleRecords().get(0);
        LifecycleRecord invalid = new LifecycleRecord(value.lifecycleId(), value.accountId(), value.opportunityId(), value.tenantId(),
                value.stage(), value.owner(), false, false, value.nextAction(), value.estimatedDate(), value.risks(),
                value.commercialAmount(), value.technicalScope(), value.evidenceRefs());
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(base, base.platformBusiness(), base.domains(), base.motions(), List.of(invalid)), Evidence.good()));
    }

    @Test void authorityFailureIsSanitizedAndFailsClosed() {
        Evidence good = Evidence.good(); CommercialLoopAuthorities ports = authorities(good);
        ports = new CommercialLoopAuthorities(ignored -> { throw new IllegalStateException("api-key=secret"); },
                ports.quoteContract(), ports.onboardingDelivery(), ports.supportSuccess(), ports.partner(),
                ports.operationsEconomics(), ports.scaleAcceptance());
        Outcome outcome = new CommercialLoopService(ports).evaluate(request());
        assertEquals(Gate.BLOCKED, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("sales/POC authority failed safely: IllegalStateException"));
        assertTrue(outcome.report().blockers().stream().noneMatch(value -> value.contains("api-key")));
    }

    @Test void mismatchedBusinessVersionCannotAdvance() {
        SalesPocEvidence wrong = new SalesPocEvidence(RUN, "other", EvidenceStatus.PASSED, 1, 1, 0, 1,
                0, 0, 0, true, true, true, "sales-authority", NOW, List.of("sales-evidence"));
        Outcome outcome = evaluate(request(), Evidence.good().withSales(wrong));
        assertEquals(Gate.BLOCKED, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("authority evidence platform business version mismatch"));
    }

    @Test void discoveryBypassBlocksSalesGate() { assertBlocked(Gate.BLOCKED, Evidence.good().withSales(sales(1,0,0,0)), "bypassed discovery"); }
    @Test void unscannedAutomationPromiseBlocksSalesGate() { assertBlocked(Gate.BLOCKED, Evidence.good().withSales(sales(0,1,0,0)), "without repository evidence"); }
    @Test void unapprovedPocScopeChangeBlocksSalesGate() { assertBlocked(Gate.BLOCKED, Evidence.good().withSales(sales(0,0,1,0)), "POC scope changed"); }
    @Test void hiddenPocFailureBlocksSalesGate() { assertBlocked(Gate.BLOCKED, Evidence.good().withSales(sales(0,0,0,1)), "POC failure was hidden"); }
    @Test void pocWithoutPredefinedObjectiveCriteriaIsBlocking() { assertBlocked(Gate.BLOCKED, Evidence.good().withSales(salesWithCriteria(0)), "objective success criteria"); }

    @Test void unauthorizedDiscountBlocksQuoteGate() { assertBlocked(Gate.B13_A, Evidence.good().withQuote(quote(1,0,0,0,0,0)), "unauthorized discount"); }
    @Test void quoteSowMismatchBlocksQuoteGate() { assertBlocked(Gate.B13_A, Evidence.good().withQuote(quote(0,1,0,0,0,0)), "Quote and SOW"); }
    @Test void securityOvercommitBlocksQuoteGate() { assertBlocked(Gate.B13_A, Evidence.good().withQuote(quote(0,0,1,0,0,0)), "exceeds verified platform capability"); }
    @Test void belowFloorMarginNeedsApproval() { assertBlocked(Gate.B13_A, Evidence.good().withQuote(quote(0,0,0,1,0,0)), "below-floor margin"); }
    @Test void contractCapabilityMismatchBlocksQuoteGate() { assertBlocked(Gate.B13_A, Evidence.good().withQuote(quote(0,0,0,0,1,0)), "exceeds verified platform capability"); }
    @Test void billingBeforeAcceptanceBlocksQuoteGate() { assertBlocked(Gate.B13_A, Evidence.good().withQuote(quote(0,0,0,0,0,1)), "before contractual acceptance"); }

    @Test void sourceBeforeSecurityOnboardingBlocksDeliveryGate() { assertBlocked(Gate.B13_B, Evidence.good().withDelivery(delivery(1,0,0,0)), "before security onboarding"); }
    @Test void projectWithoutCustomerOwnerBlocksDeliveryGate() { assertBlocked(Gate.B13_B, Evidence.good().withDelivery(delivery(0,1,0,0)), "no customer owner"); }
    @Test void scopeCreepBlocksDeliveryGate() { assertBlocked(Gate.B13_B, Evidence.good().withDelivery(delivery(0,0,1,0)), "unapproved scope work"); }
    @Test void milestoneNeedsAcceptanceEvidence() { assertBlocked(Gate.B13_B, Evidence.good().withDelivery(delivery(0,0,0,1)), "without acceptance evidence"); }
    @Test void projectWithoutApprovedBaselineIsBlocking() { assertBlocked(Gate.B13_B, Evidence.good().withDelivery(deliveryControls(false,1,true)), "approved delivery baseline"); }
    @Test void incompleteMilestoneCriteriaIsBlocking() { assertBlocked(Gate.B13_B, Evidence.good().withDelivery(deliveryControls(true,0,true)), "acceptance contract"); }
    @Test void unversionedDeliverableIsBlocking() { assertBlocked(Gate.B13_B, Evidence.good().withDelivery(deliveryControls(true,1,false)), "acceptance contract"); }

    @Test void missedP1EscalationBlocksSupportGate() { assertBlocked(Gate.B13_C, Evidence.good().withSupport(support(1,0,0)), "P1 support event"); }
    @Test void churnRiskNeedsAction() { assertBlocked(Gate.B13_C, Evidence.good().withSupport(support(0,1,0)), "churn risk"); }
    @Test void unauthorizedSupportAccessBlocksSupportGate() { assertBlocked(Gate.B13_C, Evidence.good().withSupport(support(0,0,1)), "unauthorized tenant data"); }
    @Test void unsupportedSoldSlaIsBlocking() { assertBlocked(Gate.B13_C, Evidence.good().withSupport(supportControls(0,true)), "not fully supportable"); }
    @Test void untestedP1EscalationIsBlocking() { assertBlocked(Gate.B13_C, Evidence.good().withSupport(supportControls(1,false)), "not tested"); }

    @Test void uncertifiedPartnerCannotPerformHighRiskWork() { assertBlocked(Gate.B13_D, Evidence.good().withPartner(partner(1,0,0,0)), "uncertified partner"); }
    @Test void partnerCannotCrossCustomerBoundary() { assertBlocked(Gate.B13_D, Evidence.good().withPartner(partner(0,1,0,0)), "unauthorized customer boundary"); }
    @Test void partnerSettlementMustReconcile() { assertBlocked(Gate.B13_D, Evidence.good().withPartner(partner(0,0,1,0)), "settlement cannot be reconciled"); }
    @Test void partnerDataLeakBlocksPartnerGate() { assertBlocked(Gate.B13_D, Evidence.good().withPartner(partner(0,0,0,1)), "unauthorized customer boundary"); }
    @Test void missingPartnerCertificationIsBlocking() { assertBlocked(Gate.B13_D, Evidence.good().withPartner(partnerControls(0,true,true)), "required certification"); }
    @Test void unisolatedPartnerWorkspaceIsBlocking() { assertBlocked(Gate.B13_D, Evidence.good().withPartner(partnerControls(1,false,true)), "not isolated"); }
    @Test void failedPartnerSettlementReconciliationIsBlocking() { assertBlocked(Gate.B13_D, Evidence.good().withPartner(partnerControls(1,true,false)), "did not pass"); }

    @Test void untrackedCostBlocksEconomicsGate() { assertBlocked(Gate.B13_E, Evidence.good().withEconomics(economics(1,0,0)), "actual cost"); }
    @Test void conflictingMetricsBlockEconomicsGate() { assertBlocked(Gate.B13_E, Evidence.good().withEconomics(economics(0,1,0)), "conflicting definitions"); }
    @Test void ownerlessCommercialRiskBlocksEconomicsGate() { assertBlocked(Gate.B13_E, Evidence.good().withEconomics(economics(0,0,1)), "has no owner"); }
    @Test void missingDeliveryCostVisibilityIsBlocking() { assertBlocked(Gate.B13_E, Evidence.good().withEconomics(economicsVisibility(0,1)), "cost visibility"); }
    @Test void missingProjectMarginVisibilityIsBlocking() { assertBlocked(Gate.B13_E, Evidence.good().withEconomics(economicsVisibility(1,0)), "margin visibility"); }

    @Test void criticalRiskPreventsScaleReadiness() { assertBlocked(Gate.B13_F, Evidence.good().withAcceptance(acceptance(1, true, true)), "critical commercial risk remains open"); }
    @Test void everyCommercialMotionNeedsAcceptance() {
        Outcome outcome = evaluate(request(), Evidence.good().withAcceptance(acceptance(0, false, true)));
        assertEquals(Gate.B13_F, outcome.report().gate()); assertFalse(outcome.report().commercialScaleReady());
    }
    @Test void everyAcceptanceDomainMustPass() {
        Outcome outcome = evaluate(request(), Evidence.good().withAcceptance(acceptance(0, true, false)));
        assertEquals(Gate.B13_F, outcome.report().gate()); assertFalse(outcome.report().commercialScaleReady());
    }

    @Test void writerCreatesExactTreeReportsAndRefusesOverwrite() throws IOException {
        Path workspace = temp.resolve("commercial-evidence"); Outcome outcome = evaluate(request(workspace), Evidence.good());
        Map<String, Path> files = new CommercialLoopArtifactWriter().write(outcome); assertEquals(27, files.size());
        Path root = workspace.resolve("commercial-platform");
        Set<String> top = Set.of("go-to-market", "solution-engineering", "commercial", "onboarding", "delivery",
                "support", "customer-success", "partners", "revenue-operations", "dashboards", "reports");
        try (var values = Files.list(root)) { assertEquals(top, values.filter(Files::isDirectory).map(value -> value.getFileName().toString()).collect(Collectors.toSet())); }
        try (var values = Files.walk(root)) { assertEquals(76, values.filter(Files::isDirectory).count()); }
        Set<String> reports = Set.of("icp-performance-report.json", "sales-funnel-report.json", "poc-conversion-report.json",
                "quote-margin-report.json", "onboarding-report.json", "delivery-performance-report.json", "sla-support-report.json",
                "customer-health-report.json", "renewal-report.json", "partner-performance-report.json", "profitability-report.json",
                "value-realization-report.json", "batch-13-conformance-report.json");
        try (var values = Files.list(root.resolve("reports"))) { assertEquals(reports, values.map(value -> value.getFileName().toString()).collect(Collectors.toSet())); }
        JsonNode report = new ObjectMapper().readTree(root.resolve("reports/batch-13-conformance-report.json").toFile());
        assertTrue(report.path("conformance").path("commercial_scale_ready").asBoolean());
        try (ZstdInputStream input = new ZstdInputStream(Files.newInputStream(root.resolve("go-to-market/opportunities/customer-lifecycle.jsonl.zst")))) {
            assertTrue(new String(input.readAllBytes()).contains("account-a"));
        }
        assertThrows(FileAlreadyExistsException.class, () -> new CommercialLoopArtifactWriter().write(outcome));
    }

    @Test void writerRejectsSymbolicLinkWorkspace() throws IOException {
        Path real = temp.resolve("real"); Files.createDirectories(real); Path link = temp.resolve("link"); Files.createSymbolicLink(link, real);
        assertThrows(IOException.class, () -> new CommercialLoopArtifactWriter().write(evaluate(request(link), Evidence.good())));
    }

    @Test void writerRejectsAncestorResolvingIntoRepository() throws IOException {
        Path repository = temp.resolve("repository-real"); Files.createDirectories(repository);
        Path link = temp.resolve("repository-link"); Files.createSymbolicLink(link, repository);
        Request base = request(link.resolve("evidence"));
        Request attack = new Request(base.artifactWorkspace(), repository, base.assessmentRunId(), base.platformBusiness(),
                base.lifecycleRecords(), base.domains(), base.motions(), base.policy(), base.observedAt());
        assertThrows(IllegalArgumentException.class, () -> new CommercialLoopArtifactWriter().write(evaluate(attack, Evidence.good())));
        assertFalse(Files.exists(repository.resolve("evidence")));
    }

    private void assertBlocked(Gate gate, Evidence evidence, String fragment) {
        Outcome outcome = evaluate(request(), evidence); assertEquals(gate, outcome.report().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains(fragment)));
    }

    private Outcome evaluate(Request request, Evidence evidence) { return new CommercialLoopService(authorities(evidence)).evaluate(request); }
    private static CommercialLoopAuthorities authorities(Evidence value) {
        return new CommercialLoopAuthorities(ignored -> value.sales, ignored -> value.quote, ignored -> value.delivery,
                ignored -> value.support, ignored -> value.partner, ignored -> value.economics, ignored -> value.acceptance);
    }

    private Request request() { return request(temp.resolve("commercial-evidence")); }
    private Request request(Path workspace) {
        BusinessArtifact artifact = new BusinessArtifact(VERSION, DIGEST, true, true, true,
                "sbom://commercial-v1", "provenance://commercial-v1", List.of("platform-business-evidence"));
        LifecycleRecord lifecycle = new LifecycleRecord("lifecycle-a", "account-a", "opportunity-a", "tenant-a",
                LifecycleStage.QUALIFIED_OPPORTUNITY, "account-owner", true, false, "run discovery", NOW.plusSeconds(86400),
                List.of(), new BigDecimal("100000"), List.of("repo-a", "java-to-csharp"), List.of("lifecycle-evidence"));
        List<DomainProfile> domains = Arrays.stream(CommercialDomain.values()).map(domain -> new DomainProfile(domain,
                "sor-" + domain.name().toLowerCase(Locale.ROOT), "owner-" + domain.name().toLowerCase(Locale.ROOT),
                true, true, List.of("domain-evidence-" + domain))).toList();
        List<MotionProfile> motions = Arrays.stream(CommercialMotion.values()).map(motion -> new MotionProfile(motion,
                true, true, true, true, List.of("motion-evidence-" + motion))).toList();
        Policy policy = new Policy(1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1);
        return new Request(workspace, temp.resolve("platform-repository"), RUN, artifact,
                List.of(lifecycle), domains, motions, policy, NOW);
    }

    private static Request copy(Request base, BusinessArtifact artifact, List<DomainProfile> domains,
                                List<MotionProfile> motions, List<LifecycleRecord> lifecycle) {
        return new Request(base.artifactWorkspace(), base.platformRepositoryPath(), base.assessmentRunId(), artifact,
                lifecycle, domains, motions, base.policy(), base.observedAt());
    }

    private static SalesPocEvidence sales(int bypass, int unscanned, int scope, int hidden) {
        return new SalesPocEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, 1, scope, 1,
                bypass, unscanned, hidden, true, true, true, "sales-authority", NOW, List.of("sales-evidence"));
    }
    private static SalesPocEvidence salesWithCriteria(double coverage) {
        return new SalesPocEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, coverage, 0, 1,
                0, 0, 0, true, true, true, "sales-authority", NOW, List.of("sales-evidence"));
    }
    private static QuoteContractEvidence quote(int discount, int mismatch, int security, int margin, int capability, int billing) {
        return new QuoteContractEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, discount, mismatch, security, 1,
                margin, capability, true, true, billing, "quote-authority", NOW, List.of("quote-evidence"));
    }
    private static OnboardingDeliveryEvidence delivery(int source, int owner, int scope, int milestone) {
        return new OnboardingDeliveryEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, true, source, owner,
                true, 1, 1, scope, milestone, true, true, true, "delivery-authority", NOW, List.of("delivery-evidence"));
    }
    private static OnboardingDeliveryEvidence deliveryControls(boolean baseline, double criteria, boolean versioned) {
        return new OnboardingDeliveryEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, true, 0, 0,
                baseline, criteria, 1, 0, 0, true, true, versioned,
                "delivery-authority", NOW, List.of("delivery-evidence"));
    }
    private static SupportSuccessEvidence support(int p1, int churn, int access) {
        return new SupportSuccessEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, 1, true, p1,
                1, 1, 1, churn, access, true, true, "support-authority", NOW, List.of("support-evidence"));
    }
    private static SupportSuccessEvidence supportControls(double sla, boolean p1Tested) {
        return new SupportSuccessEvidence(RUN, VERSION, EvidenceStatus.PASSED, sla, 1, p1Tested, 0,
                1, 1, 1, 0, 0, true, true, "support-authority", NOW, List.of("support-evidence"));
    }
    private static PartnerEvidence partner(int uncertified, int access, int settlement, int leak) {
        return new PartnerEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, 1, true, access,
                true, uncertified, settlement == 0, settlement, leak, true, "partner-authority", NOW, List.of("partner-evidence"));
    }
    private static PartnerEvidence partnerControls(double certification, boolean isolated, boolean reconciled) {
        return new PartnerEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, certification, isolated, 0,
                true, 0, reconciled, 0, 0, true, "partner-authority", NOW, List.of("partner-evidence"));
    }
    private static OperationsEconomicsEvidence economics(int cost, int definitions, int risks) {
        return new OperationsEconomicsEvidence(RUN, VERSION, EvidenceStatus.PASSED, true, 1, 1, cost,
                true, 1, definitions, risks, true, true, true, "economics-authority", NOW, List.of("economics-evidence"));
    }
    private static OperationsEconomicsEvidence economicsVisibility(double cost, double margin) {
        return new OperationsEconomicsEvidence(RUN, VERSION, EvidenceStatus.PASSED, true, cost, margin, 0,
                true, 1, 0, 0, true, true, true, "economics-authority", NOW, List.of("economics-evidence"));
    }
    private static ScaleAcceptanceEvidence acceptance(int risks, boolean allMotions, boolean allAccepted) {
        Set<CommercialMotion> motions = allMotions ? EnumSet.allOf(CommercialMotion.class) : EnumSet.of(CommercialMotion.DIRECT_SALES);
        return new ScaleAcceptanceEvidence(RUN, VERSION, EvidenceStatus.PASSED, motions, allAccepted, allAccepted,
                allAccepted, allAccepted, allAccepted, allAccepted, allAccepted, true, risks, true, 1,
                "acceptance-authority", NOW, List.of("acceptance-evidence"));
    }

    private record Evidence(SalesPocEvidence sales, QuoteContractEvidence quote,
                            OnboardingDeliveryEvidence delivery, SupportSuccessEvidence support,
                            PartnerEvidence partner, OperationsEconomicsEvidence economics,
                            ScaleAcceptanceEvidence acceptance) {
        static Evidence good() { return new Evidence(CommercialLoopServiceTest.sales(0,0,0,0),
                CommercialLoopServiceTest.quote(0,0,0,0,0,0), CommercialLoopServiceTest.delivery(0,0,0,0),
                CommercialLoopServiceTest.support(0,0,0), CommercialLoopServiceTest.partner(0,0,0,0),
                CommercialLoopServiceTest.economics(0,0,0), CommercialLoopServiceTest.acceptance(0,true,true)); }
        Evidence withSales(SalesPocEvidence value) { return new Evidence(value,quote,delivery,support,partner,economics,acceptance); }
        Evidence withQuote(QuoteContractEvidence value) { return new Evidence(sales,value,delivery,support,partner,economics,acceptance); }
        Evidence withDelivery(OnboardingDeliveryEvidence value) { return new Evidence(sales,quote,value,support,partner,economics,acceptance); }
        Evidence withSupport(SupportSuccessEvidence value) { return new Evidence(sales,quote,delivery,value,partner,economics,acceptance); }
        Evidence withPartner(PartnerEvidence value) { return new Evidence(sales,quote,delivery,support,value,economics,acceptance); }
        Evidence withEconomics(OperationsEconomicsEvidence value) { return new Evidence(sales,quote,delivery,support,partner,value,acceptance); }
        Evidence withAcceptance(ScaleAcceptanceEvidence value) { return new Evidence(sales,quote,delivery,support,partner,economics,value); }
    }
}
