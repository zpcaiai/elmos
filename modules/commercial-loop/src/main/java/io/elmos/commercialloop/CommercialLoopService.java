package io.elmos.commercialloop;

import java.util.*;
import java.util.function.Supplier;

import static io.elmos.commercialloop.CommercialLoopModels.*;

/** Fail-closed B13-A through B13-G evaluator over externally observed commercial evidence. */
public final class CommercialLoopService {
    private final CommercialLoopAuthorities authorities;

    public CommercialLoopService(CommercialLoopAuthorities authorities) {
        this.authorities = Objects.requireNonNull(authorities, "authorities");
    }

    public Outcome evaluate(Request request) {
        Objects.requireNonNull(request, "request");
        admit(request);
        List<String> blockers = new ArrayList<>();

        SalesPocEvidence sales = observe("sales/POC", () -> authorities.salesPoc().observe(request), blockers);
        QuoteContractEvidence quote = observe("quote/contract", () -> authorities.quoteContract().observe(request), blockers);
        OnboardingDeliveryEvidence delivery = observe("onboarding/delivery", () -> authorities.onboardingDelivery().observe(request), blockers);
        SupportSuccessEvidence support = observe("support/customer-success", () -> authorities.supportSuccess().observe(request), blockers);
        PartnerEvidence partner = observe("partner", () -> authorities.partner().observe(request), blockers);
        OperationsEconomicsEvidence economics = observe("operations/economics", () -> authorities.operationsEconomics().observe(request), blockers);
        ScaleAcceptanceEvidence acceptance = observe("commercial scale acceptance", () -> authorities.scaleAcceptance().observe(request), blockers);

        for (EvidenceEnvelope envelope : Arrays.asList(sales, quote, delivery, support, partner, economics, acceptance))
            if (envelope != null) validateEnvelope(request, envelope, blockers);
        addCriticalBlockers(request, sales, quote, delivery, support, partner, economics, acceptance, blockers);

        boolean a = passesA(request, sales);
        boolean b = a && passesB(request, quote);
        boolean c = b && passesC(request, delivery);
        boolean d = c && passesD(request, support);
        boolean e = d && passesE(request, partner);
        boolean f = e && passesF(request, economics);
        boolean g = f && passesG(request, acceptance);
        Gate gate = g ? Gate.B13_G : f ? Gate.B13_F : e ? Gate.B13_E : d ? Gate.B13_D
                : c ? Gate.B13_C : b ? Gate.B13_B : a ? Gate.B13_A : Gate.BLOCKED;
        if (!a) blockers.add("B13-A sales and POC evidence is not satisfied");
        blockers = blockers.stream().distinct().sorted().toList();
        boolean externalComplete = allValid(request, sales, quote, delivery, support, partner, economics, acceptance);
        boolean ready = g && blockers.isEmpty() && externalComplete;
        ConformanceReport report = new ConformanceReport(13, request.assessmentRunId(),
                request.platformBusiness().platformBusinessVersion(), gate,
                blockers.isEmpty() ? status(gate) : RunStatus.BLOCKED, blockers,
                restrictions(a, b, c, d, e, f, g), metrics(sales, quote, delivery, support, partner, economics, acceptance),
                externalComplete, ready, false, request.observedAt(),
                evidenceRefs(request, sales, quote, delivery, support, partner, economics, acceptance));
        return new Outcome(request, sales, quote, delivery, support, partner, economics, acceptance, report);
    }

    private static void admit(Request request) {
        BusinessArtifact artifact = request.platformBusiness();
        if (!artifact.immutable() || !artifact.signed() || !artifact.batch12TgVerified())
            throw new IllegalArgumentException("commercial platform must be immutable, signed and bound to Batch 12 T-G evidence");
        unique(request.lifecycleRecords().stream().map(LifecycleRecord::lifecycleId).toList(), "lifecycle ids");
        unique(request.domains().stream().map(value -> value.domain().name()).toList(), "commercial domains");
        unique(request.motions().stream().map(value -> value.motion().name()).toList(), "commercial motions");
        Set<CommercialDomain> domains = EnumSet.copyOf(request.domains().stream().map(DomainProfile::domain).toList());
        if (!domains.equals(EnumSet.allOf(CommercialDomain.class))
                || request.domains().stream().anyMatch(value -> !value.available() || !value.externalOperationRequired()))
            throw new IllegalArgumentException("all eight EMCOM domains require declared external systems of record");
        Set<CommercialMotion> motions = EnumSet.copyOf(request.motions().stream().map(MotionProfile::motion).toList());
        if (!motions.equals(EnumSet.allOf(CommercialMotion.class)) || request.motions().stream().anyMatch(value ->
                !value.required() || !value.catalogDefined() || !value.contractBoundaryDefined()
                        || !value.deliveryAndSupportConfigured()))
            throw new IllegalArgumentException("all six commercial motions require catalog, contract, delivery and support boundaries");
        if (request.lifecycleRecords().stream().anyMatch(value -> !value.entryCriteriaSatisfied()))
            throw new IllegalArgumentException("commercial lifecycle records require evidenced entry criteria");
    }

    private static void unique(List<String> values, String label) {
        if (values.size() != new HashSet<>(values).size()) throw new IllegalArgumentException(label + " must be unique");
    }

    private static <T extends EvidenceEnvelope> T observe(String name, Supplier<T> call, List<String> blockers) {
        try {
            T result = call.get();
            if (result == null) blockers.add(name + " authority returned no evidence");
            return result;
        } catch (RuntimeException error) {
            blockers.add(name + " authority failed safely: " + error.getClass().getSimpleName());
            return null;
        }
    }

    private static void validateEnvelope(Request request, EvidenceEnvelope evidence, List<String> blockers) {
        if (!request.assessmentRunId().equals(evidence.assessmentRunId())) blockers.add("authority evidence run mismatch");
        if (!request.platformBusiness().platformBusinessVersion().equals(evidence.platformBusinessVersion()))
            blockers.add("authority evidence platform business version mismatch");
        if (evidence.observedAt().isAfter(request.observedAt())) blockers.add("authority evidence observation is in the future");
        if (evidence.status() != EvidenceStatus.PASSED) blockers.add("authority evidence status is " + evidence.status());
    }

    private static boolean passesA(Request request, SalesPocEvidence value) {
        return valid(request, value)
                && value.qualifiedDiscoveryCoverage() >= request.policy().requiredDiscoveryCoverage()
                && value.pocCriteriaPredefinedCoverage() >= request.policy().requiredPocCriteriaCoverage()
                && value.unapprovedPocScopeChanges() == 0
                && value.pocEvidenceCoverage() >= request.policy().requiredPocEvidenceCoverage()
                && value.discoveryBypassCommitments() == 0 && value.unscannedAutomationCommitments() == 0
                && value.hiddenPocFailures() == 0 && value.pocBudgetControlPassed()
                && value.technicalQualificationIndependent() && value.customerAcceptanceRecorded();
    }

    private static boolean passesB(Request request, QuoteContractEvidence value) {
        return valid(request, value)
                && value.catalogQuoteCoverage() >= request.policy().requiredCatalogQuoteCoverage()
                && value.unauthorizedDiscounts() == 0 && value.quoteSowScopeMismatches() == 0
                && value.unapprovedSecurityCommitments() == 0
                && value.commercialApprovalCoverage() >= request.policy().requiredCommercialApprovalCoverage()
                && value.belowFloorMarginWithoutApproval() == 0 && value.contractCapabilityMismatches() == 0
                && value.quoteHistoryImmutable() && value.signedOrderEntitlementReconciled()
                && value.billingBeforeAcceptanceEvents() == 0;
    }

    private static boolean passesC(Request request, OnboardingDeliveryEvidence value) {
        return valid(request, value)
                && value.requiredOnboardingCoverage() >= request.policy().requiredOnboardingCoverage()
                && value.securityOnboardingPassed() && value.productionSourceBeforeSecurityEvents() == 0
                && value.projectsWithoutCustomerOwner() == 0 && value.projectBaselineApproved()
                && value.milestoneAcceptanceCriteriaCoverage() >= request.policy().requiredMilestoneCriteriaCoverage()
                && value.raidOwnerCoverage() >= request.policy().requiredRaidOwnerCoverage()
                && value.unapprovedScopeWork() == 0 && value.milestonesWithoutAcceptanceEvidence() == 0
                && value.repositoryBaselineVerified() && value.runnerIdentityVerified()
                && value.deliverableVersioningPassed();
    }

    private static boolean passesD(Request request, SupportSuccessEvidence value) {
        return valid(request, value)
                && value.soldServiceSlaCoverage() >= request.policy().requiredSlaCoverage()
                && value.ticketTenantBindingCoverage() >= request.policy().requiredTicketTenantCoverage()
                && value.p1EscalationTested() && value.p1MissedEscalations() == 0
                && value.customerHealthCoverage() >= request.policy().requiredHealthCoverage()
                && value.renewalPlanCoverage() >= request.policy().requiredRenewalPlanCoverage()
                && value.valueRealizationCoverage() >= request.policy().requiredValueRealizationCoverage()
                && value.churnRisksWithoutAction() == 0 && value.unauthorizedSupportAccessEvents() == 0
                && value.incidentProblemLoopPassed() && value.safeNonRenewalLifecyclePassed();
    }

    private static boolean passesE(Request request, PartnerEvidence value) {
        return valid(request, value)
                && value.dueDiligenceCoverage() >= request.policy().requiredPartnerDueDiligenceCoverage()
                && value.projectCertificationCoverage() >= request.policy().requiredPartnerCertificationCoverage()
                && value.workspaceIsolationPassed() && value.unauthorizedCustomerAccessEvents() == 0
                && value.deliveryQualityGatesEnforced() && value.uncertifiedHighRiskMigrations() == 0
                && value.settlementReconciliationPassed() && value.unreconciledSettlements() == 0
                && value.partnerDataLeaks() == 0 && value.marketplaceAssetGovernancePassed();
    }

    private static boolean passesF(Request request, OperationsEconomicsEvidence value) {
        return valid(request, value) && value.pipelineDataQualityPassed()
                && value.deliveryCostVisibility() >= request.policy().requiredCostVisibility()
                && value.projectMarginVisibility() >= request.policy().requiredMarginVisibility()
                && value.untrackedProjectCostEvents() == 0 && value.usageValueLinkagePassed()
                && value.commercialAuditCoverage() >= request.policy().requiredAuditCoverage()
                && value.conflictingMetricDefinitions() == 0 && value.criticalRisksWithoutOwner() == 0
                && value.forecastBacktestingPassed() && value.systemOfRecordReconciliationPassed()
                && value.customerConcentrationMeasured();
    }

    private static boolean passesG(Request request, ScaleAcceptanceEvidence value) {
        return valid(request, value)
                && value.validatedMotions().equals(EnumSet.allOf(CommercialMotion.class))
                && value.salesAccepted() && value.solutionEngineeringAccepted() && value.commercialAccepted()
                && value.onboardingDeliveryAccepted() && value.supportSuccessAccepted() && value.partnerAccepted()
                && value.financeOperationsAccepted() && value.contractualCapabilitiesAligned()
                && value.criticalOpenCommercialRisks() == 0 && value.commercialEvidencePackComplete()
                && value.evidenceTraceability() >= request.policy().requiredEvidenceTraceability();
    }

    private static void addCriticalBlockers(Request request, SalesPocEvidence sales, QuoteContractEvidence quote,
                                            OnboardingDeliveryEvidence delivery, SupportSuccessEvidence support,
                                            PartnerEvidence partner, OperationsEconomicsEvidence economics,
                                            ScaleAcceptanceEvidence acceptance, List<String> blockers) {
        if (sales != null) {
            if (sales.discoveryBypassCommitments() > 0) blockers.add("large commercial commitment bypassed discovery");
            if (sales.unscannedAutomationCommitments() > 0) blockers.add("automation rate was promised without repository evidence");
            if (sales.unapprovedPocScopeChanges() > 0) blockers.add("POC scope changed without approval");
            if (sales.hiddenPocFailures() > 0) blockers.add("POC failure was hidden to influence a sale");
            if (sales.pocCriteriaPredefinedCoverage() < request.policy().requiredPocCriteriaCoverage())
                blockers.add("POC objective success criteria were not predefined");
        }
        if (quote != null) {
            if (quote.quoteSowScopeMismatches() > 0) blockers.add("Quote and SOW scope mismatch detected");
            if (quote.unauthorizedDiscounts() > 0) blockers.add("unauthorized discount detected");
            if (quote.belowFloorMarginWithoutApproval() > 0) blockers.add("below-floor margin lacks strategic approval");
            if (quote.unapprovedSecurityCommitments() > 0 || quote.contractCapabilityMismatches() > 0)
                blockers.add("contract or security commitment exceeds verified platform capability");
            if (quote.billingBeforeAcceptanceEvents() > 0) blockers.add("billing triggered before contractual acceptance");
        }
        if (delivery != null) {
            if (delivery.productionSourceBeforeSecurityEvents() > 0) blockers.add("production-scope source processed before security onboarding");
            if (delivery.projectsWithoutCustomerOwner() > 0) blockers.add("formal project has no customer owner");
            if (!delivery.projectBaselineApproved()) blockers.add("formal project has no approved delivery baseline");
            if (delivery.unapprovedScopeWork() > 0) blockers.add("unapproved scope work detected");
            if (delivery.milestonesWithoutAcceptanceEvidence() > 0) blockers.add("milestone completed without acceptance evidence");
            if (delivery.milestoneAcceptanceCriteriaCoverage() < request.policy().requiredMilestoneCriteriaCoverage()
                    || !delivery.deliverableVersioningPassed())
                blockers.add("deliverable or milestone acceptance contract is incomplete");
        }
        if (support != null) {
            if (support.soldServiceSlaCoverage() < request.policy().requiredSlaCoverage())
                blockers.add("sold SLA is not fully supportable by the service catalog");
            if (!support.p1EscalationTested()) blockers.add("P1 escalation path is not tested");
            if (support.p1MissedEscalations() > 0) blockers.add("P1 support event was not escalated");
            if (support.churnRisksWithoutAction() > 0) blockers.add("customer churn risk has no action plan");
            if (support.unauthorizedSupportAccessEvents() > 0) blockers.add("support accessed unauthorized tenant data");
        }
        if (partner != null) {
            if (partner.projectCertificationCoverage() < request.policy().requiredPartnerCertificationCoverage())
                blockers.add("partner delivery scope lacks required certification");
            if (!partner.workspaceIsolationPassed()) blockers.add("partner workspace access boundary is not isolated");
            if (partner.uncertifiedHighRiskMigrations() > 0) blockers.add("uncertified partner performed high-risk migration work");
            if (partner.unauthorizedCustomerAccessEvents() > 0 || partner.partnerDataLeaks() > 0)
                blockers.add("partner crossed an unauthorized customer boundary");
            if (partner.unreconciledSettlements() > 0) blockers.add("partner settlement cannot be reconciled");
            if (!partner.settlementReconciliationPassed()) blockers.add("partner settlement reconciliation did not pass");
        }
        if (economics != null) {
            if (economics.deliveryCostVisibility() < request.policy().requiredCostVisibility())
                blockers.add("delivery cost visibility is below the required threshold");
            if (economics.projectMarginVisibility() < request.policy().requiredMarginVisibility())
                blockers.add("project margin visibility is below the required threshold");
            if (economics.untrackedProjectCostEvents() > 0) blockers.add("project actual cost is not fully visible");
            if (economics.conflictingMetricDefinitions() > 0) blockers.add("commercial metrics use conflicting definitions");
            if (economics.criticalRisksWithoutOwner() > 0) blockers.add("critical commercial risk has no owner");
        }
        if (acceptance != null && acceptance.criticalOpenCommercialRisks() > 0)
            blockers.add("critical commercial risk remains open");
    }

    private static List<String> restrictions(boolean a, boolean b, boolean c, boolean d,
                                             boolean e, boolean f, boolean g) {
        List<String> result = new ArrayList<>();
        if (!a) result.add("B13-A sales and POC standardization gate not passed");
        if (!b) result.add("B13-B quote and contract alignment gate not passed");
        if (!c) result.add("B13-C onboarding and delivery execution gate not passed");
        if (!d) result.add("B13-D support and customer-success loop gate not passed");
        if (!e) result.add("B13-E partner delivery control gate not passed");
        if (!f) result.add("B13-F measurable commercial operations gate not passed");
        if (!g) result.add("B13-G commercial scale gate not passed");
        return List.copyOf(result);
    }

    private static RunStatus status(Gate gate) {
        return switch (gate) {
            case BLOCKED -> RunStatus.INITIALIZED;
            case B13_A -> RunStatus.SALES_POC_STANDARDIZED;
            case B13_B -> RunStatus.QUOTE_CONTRACT_ALIGNED;
            case B13_C -> RunStatus.ONBOARDING_DELIVERY_EXECUTABLE;
            case B13_D -> RunStatus.SUPPORT_SUCCESS_CLOSED_LOOP;
            case B13_E -> RunStatus.PARTNER_DELIVERY_CONTROLLED;
            case B13_F -> RunStatus.COMMERCIAL_OPERATIONS_MEASURABLE;
            case B13_G -> RunStatus.COMMERCIAL_SCALE_READY;
        };
    }

    private static Metrics metrics(SalesPocEvidence a, QuoteContractEvidence b, OnboardingDeliveryEvidence c,
                                   SupportSuccessEvidence d, PartnerEvidence e, OperationsEconomicsEvidence f,
                                   ScaleAcceptanceEvidence g) {
        return new Metrics(a == null ? 0 : a.qualifiedDiscoveryCoverage(), a == null ? 0 : a.pocCriteriaPredefinedCoverage(),
                a == null ? 0 : a.pocEvidenceCoverage(), a == null ? 0 : a.unapprovedPocScopeChanges(),
                b == null ? 0 : b.catalogQuoteCoverage(), b == null ? 0 : b.unauthorizedDiscounts(),
                b == null ? 0 : b.quoteSowScopeMismatches(), c == null ? 0 : c.requiredOnboardingCoverage(),
                c == null ? 0 : c.unapprovedScopeWork(), c == null ? 0 : c.milestoneAcceptanceCriteriaCoverage(),
                d == null ? 0 : d.soldServiceSlaCoverage(), d == null ? 0 : d.p1MissedEscalations(),
                d == null ? 0 : d.customerHealthCoverage(), d == null ? 0 : d.renewalPlanCoverage(),
                d == null ? 0 : d.valueRealizationCoverage(), e == null ? 0 : e.projectCertificationCoverage(),
                e == null ? 0 : e.unauthorizedCustomerAccessEvents(), e == null ? 0 : e.unreconciledSettlements(),
                f == null ? 0 : f.deliveryCostVisibility(), f == null ? 0 : f.projectMarginVisibility(),
                f == null ? 0 : f.untrackedProjectCostEvents(), f == null ? 0 : f.commercialAuditCoverage(),
                g == null ? 0 : g.criticalOpenCommercialRisks(), g == null ? 0 : g.evidenceTraceability());
    }

    private static List<String> evidenceRefs(Request request, EvidenceEnvelope... envelopes) {
        LinkedHashSet<String> refs = new LinkedHashSet<>(request.platformBusiness().evidenceRefs());
        request.lifecycleRecords().forEach(value -> refs.addAll(value.evidenceRefs()));
        request.domains().forEach(value -> refs.addAll(value.evidenceRefs()));
        request.motions().forEach(value -> refs.addAll(value.evidenceRefs()));
        for (EvidenceEnvelope value : envelopes) if (value != null) refs.addAll(value.evidenceRefs());
        return List.copyOf(refs);
    }

    private static boolean valid(Request request, EvidenceEnvelope value) {
        return value != null && value.status() == EvidenceStatus.PASSED
                && request.assessmentRunId().equals(value.assessmentRunId())
                && request.platformBusiness().platformBusinessVersion().equals(value.platformBusinessVersion())
                && !value.observedAt().isAfter(request.observedAt());
    }

    private static boolean allValid(Request request, EvidenceEnvelope... values) {
        return Arrays.stream(values).allMatch(value -> valid(request, value));
    }
}
