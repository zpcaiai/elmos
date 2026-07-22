package io.elmos.commercial;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class CommercialModels {
    private CommercialModels() {}

    public enum EntitlementDecisionType { ALLOW, DENY_NOT_ENTITLED, DENY_LIMIT_EXCEEDED,
        DENY_EXPIRED, DENY_LICENSE_INVALID, REQUIRE_ADD_ON, REQUIRE_UPGRADE }
    public enum EntitlementSource { SUBSCRIPTION, ORDER, PRIVATE_LICENSE, TRIAL, PROMOTION,
        MANUAL_GRANT, CONTRACT_OVERRIDE, MARKETPLACE_PURCHASE }
    public enum LimitType { BOOLEAN, USAGE, CONCURRENCY, CAPACITY, SEAT, REPOSITORY, RUNNER, REGION, FEATURE_VARIANT }
    public enum OrderStatus { DRAFT, QUOTED, APPROVED, ACCEPTED, FULFILLMENT_PENDING, FULFILLING,
        FULFILLED, CLOSED, REJECTED, EXPIRED, CANCELLED, FULFILLMENT_BLOCKED, PARTIALLY_FULFILLED }
    public enum ReadinessStatus { READY, READY_WITH_CONDITIONS, NOT_READY, BLOCKED, UNKNOWN }
    public enum ProjectHealth { GREEN, AMBER, RED, UNKNOWN }
    public enum SupportSeverity { SEV1, SEV2, SEV3, SEV4 }
    public enum TicketStatus { NEW, TRIAGED, IN_PROGRESS, WAITING_FOR_CUSTOMER, WAITING_FOR_ENGINEERING,
        WAITING_FOR_PROVIDER, MONITORING, RESOLVED, CLOSED }
    public enum AssetVisibility { PRIVATE, ORGANIZATION, PARTNER_GROUP, MARKETPLACE, PUBLIC }
    public enum AssetCertification { UNVERIFIED, COMMUNITY_TESTED, ELMOS_VALIDATED, ELMOS_CERTIFIED,
        CUSTOMER_CERTIFIED, BLOCKED, REVOKED }
    public enum KnowledgeTrust { DRAFT, AI_GENERATED, HUMAN_REVIEWED, EVIDENCE_BACKED,
        CUSTOMER_APPROVED, DEPRECATED, REVOKED }
    public enum CustomerHealthStatus { HEALTHY, WATCH, AT_RISK, CRITICAL, UNKNOWN }
    public enum MetricValueStatus { MEASURED, ESTIMATED, MISSING, INCONCLUSIVE }

    public record Entitlement(String entitlementId, String organizationId, String featureKey,
                              EntitlementSource source, LimitType limitType, BigDecimal limit,
                              BigDecimal consumed, Instant validFrom, Instant validUntil,
                              boolean licenseSignatureValid, boolean active) {
        public Entitlement {
            require(entitlementId, "entitlementId"); require(organizationId, "organizationId");
            require(featureKey, "featureKey");
            if (source == null || limitType == null || limit == null || consumed == null
                    || limit.signum() < 0 || consumed.signum() < 0 || consumed.compareTo(limit) > 0
                    || validFrom == null || validUntil == null || !validUntil.isAfter(validFrom))
                throw new IllegalArgumentException("entitlement limits or validity window are invalid");
        }
    }
    public record EntitlementDecision(EntitlementDecisionType decision, String organizationId,
                                      String featureKey, BigDecimal remainingAllowance,
                                      List<String> sourceEntitlementIds, String policyVersion,
                                      List<String> reasonCodes) {
        public EntitlementDecision { sourceEntitlementIds = List.copyOf(sourceEntitlementIds); reasonCodes = List.copyOf(reasonCodes); }
    }

    public record OrderLine(String lineId, String productType, String featureKey, BigDecimal quantity,
                            String unit, Map<String, String> attributes) {
        public OrderLine {
            require(lineId, "lineId"); require(productType, "productType"); require(unit, "unit");
            if (quantity == null || quantity.signum() <= 0) throw new IllegalArgumentException("order line quantity must be positive");
            attributes = Map.copyOf(attributes);
        }
    }
    public record CommercialOrder(String orderId, String organizationId, String quoteVersionId,
                                  OrderStatus status, List<OrderLine> lines, String contractReference,
                                  String fulfillmentIdempotencyKey) {
        public CommercialOrder {
            require(orderId, "orderId"); require(organizationId, "organizationId"); require(quoteVersionId, "quoteVersionId");
            require(contractReference, "contractReference"); require(fulfillmentIdempotencyKey, "fulfillmentIdempotencyKey");
            if (status == null || lines == null || lines.isEmpty()) throw new IllegalArgumentException("commercial order is incomplete");
            lines = List.copyOf(lines);
        }
    }
    public record FulfillmentTask(String taskId, String taskType, String ownerRole,
                                  List<String> preconditions, List<String> completionEvidence,
                                  boolean completed) {
        public FulfillmentTask { preconditions = List.copyOf(preconditions); completionEvidence = List.copyOf(completionEvidence); }
    }
    public record FulfillmentResult(String orderId, OrderStatus status, List<Entitlement> entitlements,
                                    List<FulfillmentTask> tasks, List<String> generatedObjectIds,
                                    List<String> blockingReasons) {
        public FulfillmentResult {
            entitlements = List.copyOf(entitlements); tasks = List.copyOf(tasks);
            generatedObjectIds = List.copyOf(generatedObjectIds); blockingReasons = List.copyOf(blockingReasons);
        }
    }

    public record ReadinessDimension(String name, ReadinessStatus status, String owner,
                                     List<String> evidenceRefs, List<String> blockingTaskIds) {
        public ReadinessDimension { evidenceRefs = List.copyOf(evidenceRefs); blockingTaskIds = List.copyOf(blockingTaskIds); }
    }
    public record OnboardingReadiness(String organizationId, String deploymentMode,
                                      ReadinessStatus overallStatus, List<ReadinessDimension> dimensions,
                                      List<String> blockingTaskIds, boolean formalMigrationAllowed) {
        public OnboardingReadiness { dimensions = List.copyOf(dimensions); blockingTaskIds = List.copyOf(blockingTaskIds); }
    }

    public record ProjectStep(String stepId, BigDecimal weight, boolean completed, boolean criticalGate,
                              boolean gatePassed, String owner, String blockerType) {}
    public record ProjectStatusSnapshot(String projectId, ProjectHealth health, BigDecimal progress,
                                        List<String> blockingReasons, Instant p50Date, Instant p80Date,
                                        BigDecimal budgetUsed, BigDecimal budgetLimit,
                                        boolean overrideApplied, String overrideReason) {
        public ProjectStatusSnapshot { blockingReasons = List.copyOf(blockingReasons); }
    }
    public record ChangeRequest(String changeId, String projectId, String description,
                                int repositoryDelta, BigDecimal creditDelta, boolean approved,
                                List<String> recalculationDomains) {
        public ChangeRequest { recalculationDomains = List.copyOf(recalculationDomains); }
    }

    public record ServiceLevelObjective(String objectiveId, String domain, BigDecimal target,
                                        String unit, String measurementWindow, String contractRuleId) {}
    public record ServiceLevelMeasurement(String measurementId, String objectiveId, BigDecimal achieved,
                                          BigDecimal excluded, String exclusionEvidenceRef,
                                          Instant windowStart, Instant windowEnd) {}
    public record ServiceLevelDecision(boolean breached, BigDecimal eligibleServiceCredit,
                                       List<String> reasonCodes, String adjustmentRequestStatus) {
        public ServiceLevelDecision { reasonCodes = List.copyOf(reasonCodes); }
    }

    public record TicketContext(String organizationId, String repositoryId, String migrationRunId,
                                String runnerId, String modelInvocationId, String evidenceRef,
                                String subscriptionId, String slaPolicyId) {}
    public record SupportTicket(String ticketId, String type, SupportSeverity severity, TicketStatus status,
                                TicketContext context, String impact, String urgency,
                                String incidentCommander, boolean agentMayClose,
                                List<String> relatedFingerprints) {
        public SupportTicket { relatedFingerprints = List.copyOf(relatedFingerprints); }
    }

    public record RecipeAsset(String assetId, String organizationId, String origin, AssetVisibility visibility,
                              AssetCertification certification, String version, String artifactHash,
                              boolean licenseApproved, boolean sbomPresent, boolean signed,
                              boolean idempotent, boolean securityReviewed, boolean customerPublicationApproved) {}
    public record AssetDecision(boolean allowed, AssetVisibility effectiveVisibility,
                                AssetCertification effectiveCertification, List<String> reasonCodes) {
        public AssetDecision { reasonCodes = List.copyOf(reasonCodes); }
    }

    public record KnowledgeArticle(String knowledgeId, String organizationId, String type,
                                   KnowledgeTrust trust, String visibility, String sourceText,
                                   List<String> evidenceRefs, boolean anonymized, boolean humanApproved,
                                   String sourceVersion, String targetVersion) {
        public KnowledgeArticle { evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record KnowledgeDecision(boolean usableForAgent, KnowledgeTrust effectiveTrust,
                                    List<String> reasonCodes, String sanitizedSummary) {
        public KnowledgeDecision { reasonCodes = List.copyOf(reasonCodes); }
    }

    public record CustomerSignals(String organizationId, BigDecimal adoption, BigDecimal deliverySuccess,
                                  BigDecimal validationQuality, BigDecimal supportHealth,
                                  boolean plannedProjectsComplete, boolean privateUsageMissing,
                                  boolean slaBreachOpen, int daysToRenewal, List<String> evidenceRefs) {
        public CustomerSignals { evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record CustomerHealth(CustomerHealthStatus status, BigDecimal score,
                                 List<String> reasonCodes, List<String> evidenceRefs,
                                 boolean renewalActionRequired, boolean expansionCandidate) {
        public CustomerHealth { reasonCodes = List.copyOf(reasonCodes); evidenceRefs = List.copyOf(evidenceRefs); }
    }

    public record CommercialMetric(String metricKey, BigDecimal value, MetricValueStatus status,
                                   String definitionVersion, String source, String timeWindow,
                                   String currency, BigDecimal coverage) {}
    public record ProductizationCandidate(String candidateId, String patternFingerprint,
                                          int distinctOrganizations, int reuseCount,
                                          BigDecimal engineerCost, Set<String> suggestedAssets,
                                          List<String> evidenceRefs) {
        public ProductizationCandidate { suggestedAssets = Set.copyOf(suggestedAssets); evidenceRefs = List.copyOf(evidenceRefs); }
    }

    static void require(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
}
