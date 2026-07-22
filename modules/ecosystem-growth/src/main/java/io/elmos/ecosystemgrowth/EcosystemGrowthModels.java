package io.elmos.ecosystemgrowth;

import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

/** Immutable Batch 14 Product and Ecosystem Growth Model (PEGM). */
public final class EcosystemGrowthModels {
    private EcosystemGrowthModels() {}

    /** The seven authoritative PEGM value domains. */
    public enum GrowthDomain {
        ACQUISITION, ACTIVATION, ADOPTION, RETENTION, EXPANSION, ADVOCACY, ECOSYSTEM
    }

    /** The five flywheels named by the Batch 14 measurement contract. */
    public enum Flywheel {
        PRODUCT, CONTENT, COMMUNITY, MARKETPLACE, REGIONAL
    }

    /** Evidence areas adjudicated by G14-A through G14-F. */
    public enum AssuranceArea {
        PRODUCT_ACTIVATION, CONTENT_AND_DEVELOPER, COMMUNITY_SAFETY,
        MARKETPLACE_GROWTH, INTERNATIONALIZATION, REGIONAL_CHANNEL
    }

    public enum Control {
        SELF_SERVICE_SIGNUP, REPOSITORY_CONNECTION, ASSESSMENT_ACTIVATION,
        TIME_TO_VALUE_MEASURABLE, TRIAL_COST_CONTROL, SECURITY_GUARDRAILS,

        TECHNICAL_CONTENT_REVIEW_COMPLETE, DOCS_CORE_JOURNEYS_COMPLETE,
        SDK_CORE_JOURNEYS_TESTED, SAMPLE_REPOSITORIES_BUILDING, DEVELOPER_PORTAL_AVAILABLE,

        COMMUNITY_IDENTITY_ISOLATED, MODERATION_SLA_PASSED, MALICIOUS_CONTENT_CONTROLLED,
        VERIFIED_KNOWLEDGE_WORKFLOW, PRIVATE_CUSTOMER_LEAKAGE_ZERO,

        PUBLISHER_VERIFIED, EXECUTABLE_ASSET_SECURITY_GATE, MARKETPLACE_LICENSE_GATE,
        INSTALL_ROLLBACK_PASSED, FAKE_REVIEW_CONTROLLED, CRITICAL_ASSET_INCIDENTS_ZERO,

        I18N_ARCHITECTURE_PASSED, CRITICAL_UI_LOCALIZED,
        SECURITY_BILLING_HUMAN_REVIEWED, REGIONAL_FORMAT_TESTED, REGIONAL_COMPLIANCE_PASSED,

        REGIONAL_ENTRY_ASSESSMENT_COMPLETE, LAUNCH_PLAYBOOK_APPROVED,
        LOCAL_SUPPORT_READY, REGIONAL_PARTNER_QUALITY_GATES,
        REGIONAL_METRICS_AVAILABLE
    }

    public enum Gate {
        BLOCKED(0), G14_A(1), G14_B(2), G14_C(3), G14_D(4),
        G14_E(5), G14_F(6), G14_G(7);
        private final int level;
        Gate(int level) { this.level = level; }
        public int level() { return level; }
    }

    public enum RunStatus {
        INITIALIZED, PRODUCT_ACTIVATION_CONTROLLED, CONTENT_DEVELOPER_CONTROLLED,
        COMMUNITY_CONTROLLED, MARKETPLACE_CONTROLLED, INTERNATIONALIZATION_CONTROLLED,
        REGIONAL_CHANNEL_CONTROLLED, SCALABLE_GROWTH_READY, BLOCKED, FAILED_SAFELY
    }

    public enum EvidenceStatus { PASSED, FAILED, NOT_RUN, BLOCKED, INCONCLUSIVE, NOT_APPLICABLE }

    public record PlatformBusinessArtifact(String platformBusinessVersion, String artifactDigest,
                                           boolean immutable, boolean signed, boolean batch13GVerified,
                                           String commercialEvidenceRef, List<String> evidenceRefs) {
        public PlatformBusinessArtifact {
            text(platformBusinessVersion, "platformBusinessVersion");
            digest(artifactDigest, "artifactDigest");
            text(commercialEvidenceRef, "commercialEvidenceRef");
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record GrowthProgram(String productVersion, List<String> targetSegments,
                                List<String> targetRegions, List<String> productMotions,
                                List<String> primaryGoals, String northStarMetricId,
                                String budgetCurrency, BigDecimal budgetAmount) {
        public GrowthProgram {
            text(productVersion, "productVersion");
            targetSegments = nonempty(targetSegments, "targetSegments");
            targetRegions = nonempty(targetRegions, "targetRegions");
            productMotions = nonempty(productMotions, "productMotions");
            primaryGoals = nonempty(primaryGoals, "primaryGoals");
            text(northStarMetricId, "northStarMetricId");
            if (budgetCurrency == null || !budgetCurrency.matches("[A-Z]{3}"))
                throw new IllegalArgumentException("budgetCurrency must be ISO-4217");
            if (budgetAmount == null || budgetAmount.signum() < 0)
                throw new IllegalArgumentException("budgetAmount must be non-negative");
        }
    }

    public record NorthStarDefinition(String metricId, String definition, String grain,
                                      String numerator, String denominator, List<String> exclusions,
                                      String owner, List<String> driverMetricIds,
                                      List<String> guardrailMetricIds, boolean customerValueBound,
                                      boolean qualityGateRequired, String definitionVersion) {
        public NorthStarDefinition {
            text(metricId, "metricId"); text(definition, "definition"); text(grain, "grain");
            text(numerator, "numerator"); exclusions = nonempty(exclusions, "exclusions");
            text(owner, "owner"); driverMetricIds = nonempty(driverMetricIds, "driverMetricIds");
            guardrailMetricIds = nonempty(guardrailMetricIds, "guardrailMetricIds");
            text(definitionVersion, "definitionVersion");
        }
    }

    public record DomainProfile(GrowthDomain domain, String owner, String systemOfRecord,
                                boolean enabled, boolean externalEvidenceRequired,
                                List<String> evidenceRefs) {
        public DomainProfile {
            required(domain, "domain"); text(owner, "owner");
            text(systemOfRecord, "systemOfRecord"); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record FlywheelProfile(Flywheel flywheel, boolean customerValueLinked,
                                  boolean qualityGuardrailsDefined, boolean feedbackLoopDefined,
                                  List<String> evidenceRefs) {
        public FlywheelProfile {
            required(flywheel, "flywheel"); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record Policy(double requiredProductActivationCoverage,
                         double requiredContentDeveloperCoverage,
                         double requiredCommunityCoverage,
                         double requiredMarketplaceCoverage,
                         double requiredInternationalizationCoverage,
                         double requiredRegionalChannelCoverage,
                         double requiredEvidenceTraceability) {
        public Policy {
            rates(requiredProductActivationCoverage, requiredContentDeveloperCoverage,
                    requiredCommunityCoverage, requiredMarketplaceCoverage,
                    requiredInternationalizationCoverage, requiredRegionalChannelCoverage,
                    requiredEvidenceTraceability);
        }

        public double coverageFor(AssuranceArea area) {
            return switch (area) {
                case PRODUCT_ACTIVATION -> requiredProductActivationCoverage;
                case CONTENT_AND_DEVELOPER -> requiredContentDeveloperCoverage;
                case COMMUNITY_SAFETY -> requiredCommunityCoverage;
                case MARKETPLACE_GROWTH -> requiredMarketplaceCoverage;
                case INTERNATIONALIZATION -> requiredInternationalizationCoverage;
                case REGIONAL_CHANNEL -> requiredRegionalChannelCoverage;
            };
        }
    }

    public record Request(Path artifactWorkspace, Path platformRepositoryPath, String assessmentRunId,
                          PlatformBusinessArtifact platformBusiness, GrowthProgram growthProgram,
                          NorthStarDefinition northStar, List<DomainProfile> growthDomains,
                          List<FlywheelProfile> flywheels, Policy policy, Instant observedAt) {
        public Request {
            required(artifactWorkspace, "artifactWorkspace");
            required(platformRepositoryPath, "platformRepositoryPath");
            text(assessmentRunId, "assessmentRunId");
            required(platformBusiness, "platformBusiness"); required(growthProgram, "growthProgram");
            required(northStar, "northStar"); growthDomains = nonempty(growthDomains, "growthDomains");
            flywheels = nonempty(flywheels, "flywheels"); required(policy, "policy");
            required(observedAt, "observedAt");
            if (!growthProgram.northStarMetricId().equals(northStar.metricId()))
                throw new IllegalArgumentException("growth program and North Star metric must match");
            Path workspace = artifactWorkspace.toAbsolutePath().normalize();
            if (workspace.startsWith(platformRepositoryPath.toAbsolutePath().normalize()))
                throw new IllegalArgumentException("growth evidence workspace must be outside the platform repository");
        }
    }

    public interface EvidenceEnvelope {
        String assessmentRunId();
        String platformBusinessVersion();
        EvidenceStatus status();
        String authorityId();
        Instant observedAt();
        List<String> evidenceRefs();
    }

    public record GateEvidence(String assessmentRunId, String platformBusinessVersion,
                               AssuranceArea area, EvidenceStatus status, double coverage,
                               Set<Control> controls, boolean tenantIsolationPassed,
                               boolean privacyAndConsentPassed, boolean guardrailsPassed,
                               boolean failureAndNegativeEvidencePreserved,
                               int criticalViolations, int crossTenantEvents,
                               int fabricatedOutcomes, int unauthorizedExternalActions,
                               boolean externalOperationExecuted, Map<String, Double> metrics,
                               String authorityId, Instant observedAt,
                               List<String> evidenceRefs) implements EvidenceEnvelope {
        public GateEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            required(area, "area"); rates(coverage);
            controls = controls == null ? Set.of() : Set.copyOf(controls);
            nonnegative(criticalViolations, crossTenantEvents, fabricatedOutcomes,
                    unauthorizedExternalActions);
            metrics = metrics == null ? Map.of() : Map.copyOf(metrics);
            if (metrics.entrySet().stream().anyMatch(entry -> entry.getKey() == null
                    || entry.getKey().isBlank() || entry.getValue() == null
                    || !Double.isFinite(entry.getValue())))
                throw new IllegalArgumentException("metrics require named finite values");
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record GrowthConformanceEvidence(String assessmentRunId, String platformBusinessVersion,
                                            EvidenceStatus status, Set<AssuranceArea> acceptedAreas,
                                            Set<GrowthDomain> validatedDomains,
                                            Set<Flywheel> validatedFlywheels,
                                            boolean channelCacVisible,
                                            boolean contributionMarginVisible,
                                            int criticalOpenGrowthRisks,
                                            boolean evidencePackComplete,
                                            double evidenceTraceability,
                                            List<String> supportedMotions,
                                            List<String> openNonBlockingItems,
                                            boolean externalOperationExecuted,
                                            String authorityId, Instant observedAt,
                                            List<String> evidenceRefs) implements EvidenceEnvelope {
        public GrowthConformanceEvidence {
            common(assessmentRunId, platformBusinessVersion, status, authorityId, observedAt);
            acceptedAreas = acceptedAreas == null ? Set.of() : Set.copyOf(acceptedAreas);
            validatedDomains = validatedDomains == null ? Set.of() : Set.copyOf(validatedDomains);
            validatedFlywheels = validatedFlywheels == null ? Set.of() : Set.copyOf(validatedFlywheels);
            nonnegative(criticalOpenGrowthRisks); rates(evidenceTraceability);
            supportedMotions = nonempty(supportedMotions, "supportedMotions");
            openNonBlockingItems = copy(openNonBlockingItems);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record ConformanceReport(int batch, String growthPlatformVersion,
                                    String assessmentRunId, String platformBusinessVersion,
                                    Gate gate, RunStatus status, List<String> supportedMotions,
                                    List<String> openNonBlockingItems, List<String> blockers,
                                    List<String> restrictions, Map<String, Double> metrics,
                                    boolean externalEvidenceComplete, boolean scalableGrowthReady,
                                    boolean externalOperationExecuted, Instant evaluatedAt,
                                    List<String> evidenceRefs) {
        public ConformanceReport {
            if (batch != 14) throw new IllegalArgumentException("batch must be 14");
            text(growthPlatformVersion, "growthPlatformVersion");
            text(assessmentRunId, "assessmentRunId");
            text(platformBusinessVersion, "platformBusinessVersion");
            required(gate, "gate"); required(status, "status");
            supportedMotions = copy(supportedMotions);
            openNonBlockingItems = copy(openNonBlockingItems);
            blockers = copy(blockers); restrictions = copy(restrictions);
            metrics = metrics == null ? Map.of() : Map.copyOf(metrics);
            required(evaluatedAt, "evaluatedAt"); evidenceRefs = copy(evidenceRefs);
            if (externalOperationExecuted)
                throw new IllegalArgumentException("Batch 14 control plane cannot execute growth, marketplace, messaging, payment, moderation, legal, or regional operations");
            if (scalableGrowthReady && (gate != Gate.G14_G || status != RunStatus.SCALABLE_GROWTH_READY
                    || !externalEvidenceComplete || !blockers.isEmpty()))
                throw new IllegalArgumentException("scalable growth readiness requires G14-G and complete external evidence");
        }
    }

    public record Outcome(Request request, Map<AssuranceArea, GateEvidence> gateEvidence,
                          GrowthConformanceEvidence acceptance, ConformanceReport report) {
        public Outcome {
            required(request, "request");
            gateEvidence = gateEvidence == null ? Map.of() : Map.copyOf(gateEvidence);
            required(report, "report");
        }
    }

    static <T> List<T> copy(Collection<T> values) {
        return values == null ? List.of() : List.copyOf(values);
    }

    static <T> List<T> nonempty(Collection<T> values, String name) {
        List<T> result = copy(values);
        if (result.isEmpty()) throw new IllegalArgumentException(name + " is required");
        return result;
    }

    static void common(String run, String version, EvidenceStatus status,
                       String authority, Instant observedAt) {
        text(run, "assessmentRunId"); text(version, "platformBusinessVersion");
        required(status, "status"); text(authority, "authorityId"); required(observedAt, "observedAt");
    }

    static List<String> evidence(List<String> refs) {
        List<String> result = copy(refs);
        if (result.isEmpty() || result.stream().anyMatch(value -> value == null || value.isBlank()))
            throw new IllegalArgumentException("evidence refs are required");
        return result;
    }

    static void nonnegative(int... values) {
        if (Arrays.stream(values).anyMatch(value -> value < 0))
            throw new IllegalArgumentException("counts must be non-negative");
    }

    static void rates(double... values) {
        if (Arrays.stream(values).anyMatch(value -> !Double.isFinite(value) || value < 0 || value > 1))
            throw new IllegalArgumentException("rates must be in [0,1]");
    }

    static void digest(String value, String name) {
        if (value == null || !value.matches("[0-9a-f]{64}"))
            throw new IllegalArgumentException(name + " must be sha256 hex");
    }

    static void text(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    static <T> T required(T value, String name) {
        if (value == null) throw new IllegalArgumentException(name + " is required");
        return value;
    }
}
