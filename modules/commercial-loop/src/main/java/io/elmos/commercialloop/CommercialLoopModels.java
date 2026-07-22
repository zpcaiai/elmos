package io.elmos.commercialloop;

import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

/** Immutable Batch 13 Enterprise Migration Commercial Operating Model (EMCOM). */
public final class CommercialLoopModels {
    private CommercialLoopModels() {}

    public enum CommercialDomain { GO_TO_MARKET, CUSTOMER_DISCOVERY, SOLUTION_ENGINEERING,
        COMMERCIAL_CONTRACT, CUSTOMER_ONBOARDING, DELIVERY_MANAGEMENT,
        CUSTOMER_SUCCESS_SUPPORT, PARTNER_REVENUE_OPERATIONS }
    public enum CommercialMotion { DIRECT_SALES, POC_LED_SALES, ENTERPRISE_SUBSCRIPTION,
        PROFESSIONAL_SERVICES, PARTNER_LED_DELIVERY, MANAGED_MIGRATION_SERVICE }
    public enum LifecycleStage { TARGET_ACCOUNT, QUALIFIED_LEAD, QUALIFIED_OPPORTUNITY, DISCOVERY,
        TECHNICAL_ASSESSMENT, POC_PROPOSED, POC_RUNNING, POC_ACCEPTED, COMMERCIAL_PROPOSAL,
        CONTRACTED, ONBOARDING, IMPLEMENTATION, PRODUCTION_MIGRATION, HYPERCARE,
        CUSTOMER_ACCEPTED, MANAGED_SERVICE, RENEWAL_EXPANSION, DISQUALIFIED, NO_DECISION,
        POC_FAILED, SECURITY_BLOCKED, BUDGET_BLOCKED, TECHNICAL_BLOCKED,
        LOST_TO_COMPETITOR, PAUSED, CHURN_RISK, TERMINATED }
    public enum Gate {
        BLOCKED(0), B13_A(1), B13_B(2), B13_C(3), B13_D(4), B13_E(5), B13_F(6), B13_G(7);
        private final int level;
        Gate(int level) { this.level = level; }
        public int level() { return level; }
    }
    public enum RunStatus { INITIALIZED, SALES_POC_STANDARDIZED, QUOTE_CONTRACT_ALIGNED,
        ONBOARDING_DELIVERY_EXECUTABLE, SUPPORT_SUCCESS_CLOSED_LOOP, PARTNER_DELIVERY_CONTROLLED,
        COMMERCIAL_OPERATIONS_MEASURABLE, COMMERCIAL_SCALE_READY, BLOCKED, FAILED_SAFELY }
    public enum EvidenceStatus { PASSED, FAILED, NOT_RUN, BLOCKED, INCONCLUSIVE, NOT_APPLICABLE }

    public record Request(Path artifactWorkspace, Path platformRepositoryPath, String assessmentRunId,
                          BusinessArtifact platformBusiness, List<LifecycleRecord> lifecycleRecords,
                          List<DomainProfile> domains, List<MotionProfile> motions,
                          Policy policy, Instant observedAt) {
        public Request {
            required(artifactWorkspace, "artifactWorkspace"); required(platformRepositoryPath, "platformRepositoryPath");
            text(assessmentRunId, "assessmentRunId"); required(platformBusiness, "platformBusiness");
            lifecycleRecords = copy(lifecycleRecords); domains = copy(domains); motions = copy(motions);
            if (lifecycleRecords.isEmpty() || domains.isEmpty() || motions.isEmpty())
                throw new IllegalArgumentException("lifecycle, domain and commercial motion records are required");
            required(policy, "policy"); required(observedAt, "observedAt");
            Path workspace = artifactWorkspace.toAbsolutePath().normalize();
            if (workspace.startsWith(platformRepositoryPath.toAbsolutePath().normalize()))
                throw new IllegalArgumentException("commercial evidence workspace must be outside the platform repository");
        }
    }

    public record BusinessArtifact(String platformBusinessVersion, String artifactDigest, boolean immutable,
                                   boolean signed, boolean batch12TgVerified, String sbomRef,
                                   String provenanceRef, List<String> evidenceRefs) {
        public BusinessArtifact {
            text(platformBusinessVersion, "platformBusinessVersion"); digest(artifactDigest, "artifactDigest");
            text(sbomRef, "sbomRef"); text(provenanceRef, "provenanceRef"); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record LifecycleRecord(String lifecycleId, String accountId, String opportunityId, String tenantId,
                                  LifecycleStage stage, String owner, boolean entryCriteriaSatisfied,
                                  boolean exitCriteriaSatisfied, String nextAction, Instant estimatedDate,
                                  List<String> risks, BigDecimal commercialAmount,
                                  List<String> technicalScope, List<String> evidenceRefs) {
        public LifecycleRecord {
            text(lifecycleId, "lifecycleId"); text(accountId, "accountId"); text(opportunityId, "opportunityId");
            required(stage, "stage"); text(owner, "owner"); text(nextAction, "nextAction"); required(estimatedDate, "estimatedDate");
            risks = copy(risks); technicalScope = copy(technicalScope); evidenceRefs = evidence(evidenceRefs);
            if (commercialAmount == null || commercialAmount.signum() < 0 || technicalScope.isEmpty())
                throw new IllegalArgumentException("commercial amount and technical scope are required");
        }
    }

    public record DomainProfile(CommercialDomain domain, String systemOfRecord, String owner,
                                boolean available, boolean externalOperationRequired, List<String> evidenceRefs) {
        public DomainProfile {
            required(domain, "domain"); text(systemOfRecord, "systemOfRecord"); text(owner, "owner"); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record MotionProfile(CommercialMotion motion, boolean required, boolean catalogDefined,
                                boolean contractBoundaryDefined, boolean deliveryAndSupportConfigured,
                                List<String> evidenceRefs) {
        public MotionProfile { CommercialLoopModels.required(motion, "motion"); evidenceRefs = evidence(evidenceRefs); }
    }

    public record Policy(double requiredDiscoveryCoverage, double requiredPocCriteriaCoverage,
                         double requiredPocEvidenceCoverage, double requiredCatalogQuoteCoverage,
                         double requiredCommercialApprovalCoverage, double requiredOnboardingCoverage,
                         double requiredMilestoneCriteriaCoverage, double requiredRaidOwnerCoverage,
                         double requiredSlaCoverage, double requiredTicketTenantCoverage,
                         double requiredHealthCoverage, double requiredRenewalPlanCoverage,
                         double requiredPartnerDueDiligenceCoverage, double requiredPartnerCertificationCoverage,
                         double requiredCostVisibility, double requiredMarginVisibility,
                         double requiredAuditCoverage, double requiredValueRealizationCoverage,
                         double requiredEvidenceTraceability) {
        public Policy {
            rates(requiredDiscoveryCoverage, requiredPocCriteriaCoverage, requiredPocEvidenceCoverage,
                    requiredCatalogQuoteCoverage, requiredCommercialApprovalCoverage, requiredOnboardingCoverage,
                    requiredMilestoneCriteriaCoverage, requiredRaidOwnerCoverage, requiredSlaCoverage,
                    requiredTicketTenantCoverage, requiredHealthCoverage, requiredRenewalPlanCoverage,
                    requiredPartnerDueDiligenceCoverage, requiredPartnerCertificationCoverage,
                    requiredCostVisibility, requiredMarginVisibility, requiredAuditCoverage,
                    requiredValueRealizationCoverage, requiredEvidenceTraceability);
        }
    }

    public interface EvidenceEnvelope {
        String assessmentRunId(); String platformBusinessVersion(); EvidenceStatus status();
        String authorityId(); Instant observedAt(); List<String> evidenceRefs();
    }

    public record SalesPocEvidence(String assessmentRunId, String platformBusinessVersion, EvidenceStatus status,
                                   double qualifiedDiscoveryCoverage, double pocCriteriaPredefinedCoverage,
                                   int unapprovedPocScopeChanges, double pocEvidenceCoverage,
                                   int discoveryBypassCommitments, int unscannedAutomationCommitments,
                                   int hiddenPocFailures, boolean pocBudgetControlPassed,
                                   boolean technicalQualificationIndependent, boolean customerAcceptanceRecorded,
                                   String authorityId, Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public SalesPocEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            rates(qualifiedDiscoveryCoverage, pocCriteriaPredefinedCoverage, pocEvidenceCoverage);
            nonnegative(unapprovedPocScopeChanges, discoveryBypassCommitments, unscannedAutomationCommitments, hiddenPocFailures);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record QuoteContractEvidence(String assessmentRunId, String platformBusinessVersion, EvidenceStatus status,
                                        double catalogQuoteCoverage, int unauthorizedDiscounts,
                                        int quoteSowScopeMismatches, int unapprovedSecurityCommitments,
                                        double commercialApprovalCoverage, int belowFloorMarginWithoutApproval,
                                        int contractCapabilityMismatches, boolean quoteHistoryImmutable,
                                        boolean signedOrderEntitlementReconciled, int billingBeforeAcceptanceEvents,
                                        String authorityId, Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public QuoteContractEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            rates(catalogQuoteCoverage, commercialApprovalCoverage);
            nonnegative(unauthorizedDiscounts, quoteSowScopeMismatches, unapprovedSecurityCommitments,
                    belowFloorMarginWithoutApproval, contractCapabilityMismatches, billingBeforeAcceptanceEvents);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record OnboardingDeliveryEvidence(String assessmentRunId, String platformBusinessVersion, EvidenceStatus status,
                                             double requiredOnboardingCoverage, boolean securityOnboardingPassed,
                                             int productionSourceBeforeSecurityEvents, int projectsWithoutCustomerOwner,
                                             boolean projectBaselineApproved, double milestoneAcceptanceCriteriaCoverage,
                                             double raidOwnerCoverage, int unapprovedScopeWork,
                                             int milestonesWithoutAcceptanceEvidence, boolean repositoryBaselineVerified,
                                             boolean runnerIdentityVerified, boolean deliverableVersioningPassed,
                                             String authorityId, Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public OnboardingDeliveryEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            rates(requiredOnboardingCoverage, milestoneAcceptanceCriteriaCoverage, raidOwnerCoverage);
            nonnegative(productionSourceBeforeSecurityEvents, projectsWithoutCustomerOwner,
                    unapprovedScopeWork, milestonesWithoutAcceptanceEvidence); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record SupportSuccessEvidence(String assessmentRunId, String platformBusinessVersion, EvidenceStatus status,
                                         double soldServiceSlaCoverage, double ticketTenantBindingCoverage,
                                         boolean p1EscalationTested, int p1MissedEscalations,
                                         double customerHealthCoverage, double renewalPlanCoverage,
                                         double valueRealizationCoverage, int churnRisksWithoutAction,
                                         int unauthorizedSupportAccessEvents, boolean incidentProblemLoopPassed,
                                         boolean safeNonRenewalLifecyclePassed, String authorityId,
                                         Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public SupportSuccessEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            rates(soldServiceSlaCoverage, ticketTenantBindingCoverage, customerHealthCoverage,
                    renewalPlanCoverage, valueRealizationCoverage);
            nonnegative(p1MissedEscalations, churnRisksWithoutAction, unauthorizedSupportAccessEvents);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record PartnerEvidence(String assessmentRunId, String platformBusinessVersion, EvidenceStatus status,
                                  double dueDiligenceCoverage, double projectCertificationCoverage,
                                  boolean workspaceIsolationPassed, int unauthorizedCustomerAccessEvents,
                                  boolean deliveryQualityGatesEnforced, int uncertifiedHighRiskMigrations,
                                  boolean settlementReconciliationPassed, int unreconciledSettlements,
                                  int partnerDataLeaks, boolean marketplaceAssetGovernancePassed,
                                  String authorityId, Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public PartnerEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            rates(dueDiligenceCoverage, projectCertificationCoverage);
            nonnegative(unauthorizedCustomerAccessEvents, uncertifiedHighRiskMigrations, unreconciledSettlements, partnerDataLeaks);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record OperationsEconomicsEvidence(String assessmentRunId, String platformBusinessVersion, EvidenceStatus status,
                                              boolean pipelineDataQualityPassed, double deliveryCostVisibility,
                                              double projectMarginVisibility, int untrackedProjectCostEvents,
                                              boolean usageValueLinkagePassed, double commercialAuditCoverage,
                                              int conflictingMetricDefinitions, int criticalRisksWithoutOwner,
                                              boolean forecastBacktestingPassed, boolean systemOfRecordReconciliationPassed,
                                              boolean customerConcentrationMeasured, String authorityId,
                                              Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public OperationsEconomicsEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            rates(deliveryCostVisibility, projectMarginVisibility, commercialAuditCoverage);
            nonnegative(untrackedProjectCostEvents, conflictingMetricDefinitions, criticalRisksWithoutOwner);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record ScaleAcceptanceEvidence(String assessmentRunId, String platformBusinessVersion, EvidenceStatus status,
                                          Set<CommercialMotion> validatedMotions, boolean salesAccepted,
                                          boolean solutionEngineeringAccepted, boolean commercialAccepted,
                                          boolean onboardingDeliveryAccepted, boolean supportSuccessAccepted,
                                          boolean partnerAccepted, boolean financeOperationsAccepted,
                                          boolean contractualCapabilitiesAligned, int criticalOpenCommercialRisks,
                                          boolean commercialEvidencePackComplete, double evidenceTraceability,
                                          String authorityId, Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public ScaleAcceptanceEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            validatedMotions = validatedMotions == null ? Set.of() : Set.copyOf(validatedMotions);
            nonnegative(criticalOpenCommercialRisks); rates(evidenceTraceability); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record Metrics(double discoveryCoverage, double pocCriteriaCoverage, double pocEvidenceCoverage,
                          int unapprovedPocScopeChanges, double catalogQuoteCoverage, int unauthorizedDiscounts,
                          int quoteScopeMismatches, double onboardingCoverage, int unapprovedScopeWork,
                          double acceptanceEvidenceCoverage, double slaCoverage, int p1MissedEscalations,
                          double healthCoverage, double renewalCoverage, double valueRealizationCoverage,
                          double partnerCertificationCoverage, int partnerAccessViolations,
                          int unreconciledPartnerSettlements, double costVisibility, double marginVisibility,
                          int untrackedProjectCosts, double auditCoverage, int criticalOpenRisks,
                          double evidenceTraceability) {}

    public record ConformanceReport(int batch, String assessmentRunId, String platformBusinessVersion,
                                    Gate gate, RunStatus status, List<String> blockers, List<String> restrictions,
                                    Metrics metrics, boolean externalEvidenceComplete, boolean commercialScaleReady,
                                    boolean commercialOperationExecuted, Instant evaluatedAt, List<String> evidenceRefs) {
        public ConformanceReport {
            if (batch != 13) throw new IllegalArgumentException("batch must be 13");
            text(assessmentRunId, "assessmentRunId"); text(platformBusinessVersion, "platformBusinessVersion");
            required(gate, "gate"); required(status, "status"); blockers = copy(blockers); restrictions = copy(restrictions);
            required(metrics, "metrics"); required(evaluatedAt, "evaluatedAt"); evidenceRefs = copy(evidenceRefs);
            if (commercialOperationExecuted) throw new IllegalArgumentException("Batch 13 control plane cannot execute commercial operations");
            if (commercialScaleReady && (gate != Gate.B13_G || !externalEvidenceComplete || !blockers.isEmpty()))
                throw new IllegalArgumentException("commercial scale readiness requires B13-G and complete external evidence");
        }
    }

    public record Outcome(Request request, SalesPocEvidence salesPoc, QuoteContractEvidence quoteContract,
                          OnboardingDeliveryEvidence onboardingDelivery, SupportSuccessEvidence supportSuccess,
                          PartnerEvidence partner, OperationsEconomicsEvidence operationsEconomics,
                          ScaleAcceptanceEvidence scaleAcceptance, ConformanceReport report) {
        public Outcome { required(request, "request"); required(report, "report"); }
    }

    static <T> List<T> copy(Collection<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static void common(String run, String version, EvidenceStatus status, String authority, Instant observedAt) {
        text(run, "assessmentRunId"); text(version, "platformBusinessVersion"); required(status, "status");
        text(authority, "authorityId"); required(observedAt, "observedAt");
    }
    static List<String> evidence(List<String> refs) {
        List<String> result = copy(refs); if (result.isEmpty()) throw new IllegalArgumentException("evidence refs are required"); return result;
    }
    static void nonnegative(int... values) { if (Arrays.stream(values).anyMatch(value -> value < 0)) throw new IllegalArgumentException("counts cannot be negative"); }
    static void text(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    static void required(Object value, String name) { if (value == null) throw new IllegalArgumentException(name + " is required"); }
    static void digest(String value, String name) { text(value, name); if (!value.matches("[A-Fa-f0-9]{64}")) throw new IllegalArgumentException(name + " must be sha-256"); }
    static void rates(double... values) { if (Arrays.stream(values).anyMatch(value -> Double.isNaN(value) || value < 0 || value > 1)) throw new IllegalArgumentException("rates must be between 0 and 1"); }
}
