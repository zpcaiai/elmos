package io.elmos.cutover;

import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

/** Immutable Batch 11 Production Cutover Control Model (PCCM). */
public final class ProductionCutoverModels {
    private ProductionCutoverModels() {}

    public enum Phase {
        P0_PREPARED(0), P1_SCHEMA_EXPANDED(1), P2_BACKFILL_RUNNING(2),
        P3_INCREMENTAL_SYNC_HEALTHY(3), P4_SHADOW_READ(4), P5_READ_CANARY(5),
        P6_TARGET_READ_PRIMARY(6), P7_WRITE_CANARY(7), P8_TARGET_WRITE_PRIMARY(8),
        P9_SOURCE_READ_ONLY(9), P10_HYPERCARE(10), P11_RETIREMENT_CANDIDATE(11),
        P12_DECOMMISSIONED(12);
        private final int sequence;
        Phase(int sequence) { this.sequence = sequence; }
        public int sequence() { return sequence; }
    }
    public enum Gate {
        BLOCKED(0), C_A(1), C_B(2), C_C(3), C_D(4), C_E(5), C_F(6), C_G(7);
        private final int level;
        Gate(int level) { this.level = level; }
        public int level() { return level; }
    }
    public enum RunStatus { INITIALIZED, PREPARING, BACKFILLING, CATCHING_UP, SHADOW_READING,
        READ_CANARY, TARGET_READ_PRIMARY, WRITE_CANARY, TARGET_WRITE_PRIMARY, SOURCE_READ_ONLY,
        HYPERCARE, ACCEPTED, RETIRING, COMPLETED, ROLLED_BACK, FORWARD_FIX_REQUIRED, BLOCKED, FAILED_SAFELY }
    public enum EvidenceStatus { PASSED, FAILED, NOT_RUN, BLOCKED, INCONCLUSIVE, NOT_APPLICABLE }
    public enum SystemRole { SOURCE, TARGET }
    public enum AssetCategory { AUTHORITATIVE, DERIVED, REBUILDABLE, EPHEMERAL, AUDIT, REGULATED, ARCHIVAL, OBSOLETE, UNKNOWN }
    public enum ApprovalDimension { ENGINEERING, OPERATIONS, SECURITY, BUSINESS, COMPLIANCE, IRREVERSIBILITY, DECOMMISSION }
    public enum ApprovalStatus { PENDING, ACCEPTED, ACCEPTED_WITH_CONDITIONS, REJECTED, EXPIRED }

    public record Request(Path artifactWorkspace, Path sourceRepositoryPath, Path targetRepositoryPath,
                          String cutoverRunId, String migrationId, ArtifactBinding sourceArtifact,
                          ArtifactBinding targetArtifact, boolean batch10Eligible, Phase currentPhase,
                          List<MigrationWave> waves, List<AggregateAuthority> authorities,
                          List<DataAsset> dataAssets, List<Approval> approvals, Policy policy, Instant observedAt) {
        public Request {
            required(artifactWorkspace, "artifactWorkspace"); required(sourceRepositoryPath, "sourceRepositoryPath");
            required(targetRepositoryPath, "targetRepositoryPath"); text(cutoverRunId, "cutoverRunId");
            text(migrationId, "migrationId"); required(sourceArtifact, "sourceArtifact");
            required(targetArtifact, "targetArtifact"); required(currentPhase, "currentPhase");
            waves = copy(waves); authorities = copy(authorities); dataAssets = copy(dataAssets); approvals = copy(approvals);
            required(policy, "policy"); required(observedAt, "observedAt");
            if (waves.isEmpty() || authorities.isEmpty() || dataAssets.isEmpty())
                throw new IllegalArgumentException("waves, authorities and data assets are required");
            Path workspace = artifactWorkspace.toAbsolutePath().normalize();
            if (workspace.startsWith(sourceRepositoryPath.toAbsolutePath().normalize())
                    || workspace.startsWith(targetRepositoryPath.toAbsolutePath().normalize()))
                throw new IllegalArgumentException("artifact workspace must be outside source and target repositories");
        }
    }

    public record ArtifactBinding(SystemRole role, String artifactId, String artifactDigest,
                                  String snapshotId, boolean immutable, String batch10Gate,
                                  boolean eligibleForProgressiveDelivery, List<String> evidenceRefs) {
        public ArtifactBinding {
            required(role, "role"); text(artifactId, "artifactId"); digest(artifactDigest, "artifactDigest");
            text(snapshotId, "snapshotId"); text(batch10Gate, "batch10Gate"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record MigrationWave(String waveId, int order, int riskTier, boolean stableSegmentation,
                                boolean independentlyReversible, String businessOwner,
                                List<String> segmentKeys, List<String> entryGateRefs,
                                List<String> exitGateRefs, List<String> evidenceRefs) {
        public MigrationWave {
            text(waveId, "waveId"); if (order < 1 || riskTier < 0 || riskTier > 4)
                throw new IllegalArgumentException("wave order or risk tier is invalid");
            text(businessOwner, "businessOwner"); segmentKeys = copy(segmentKeys);
            entryGateRefs = copy(entryGateRefs); exitGateRefs = copy(exitGateRefs); evidenceRefs = copy(evidenceRefs);
            if (segmentKeys.isEmpty() || entryGateRefs.isEmpty() || exitGateRefs.isEmpty() || evidenceRefs.isEmpty())
                throw new IllegalArgumentException("wave segmentation and gate evidence is required");
        }
    }

    public record AggregateAuthority(String aggregateId, String segmentId, Phase phase,
                                     SystemRole primaryWriter, SystemRole primaryReader,
                                     SystemRole fallbackReader, String stableRoutingKey,
                                     long version, boolean allEntrypointsCompliant,
                                     boolean dualPrimaryDetected, boolean atomicallyPublished,
                                     boolean clientCanOverride, List<String> evidenceRefs) {
        public AggregateAuthority {
            text(aggregateId, "aggregateId"); text(segmentId, "segmentId"); required(phase, "phase");
            required(primaryWriter, "primaryWriter"); required(primaryReader, "primaryReader");
            text(stableRoutingKey, "stableRoutingKey"); if (version < 1) throw new IllegalArgumentException("authority version must be positive");
            evidenceRefs = copy(evidenceRefs); if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("authority evidence is required");
        }
    }

    public record DataAsset(String assetId, AssetCategory category, String owner,
                            String sourceLocation, String targetLocation,
                            long estimatedRecords, long estimatedBytes, double changeRatePerSecond,
                            String sensitivity, String migrationStrategy, String retentionPolicy,
                            boolean legalHold, double mappingCoverage,
                            boolean irreversibleTransformation, boolean lossyTransformationApproved,
                            List<String> evidenceRefs) {
        public DataAsset {
            text(assetId, "assetId"); required(category, "category"); text(owner, "owner");
            text(sourceLocation, "sourceLocation"); text(targetLocation, "targetLocation");
            if (estimatedRecords < 0 || estimatedBytes < 0 || Double.isNaN(changeRatePerSecond) || changeRatePerSecond < 0)
                throw new IllegalArgumentException("data asset volume and change rate must be nonnegative");
            text(sensitivity, "sensitivity");
            text(migrationStrategy, "migrationStrategy"); text(retentionPolicy, "retentionPolicy");
            rate(mappingCoverage, "mappingCoverage"); evidenceRefs = copy(evidenceRefs);
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("data asset evidence is required");
        }
        public boolean authoritative() { return category == AssetCategory.AUTHORITATIVE || category == AssetCategory.REGULATED || category == AssetCategory.AUDIT; }
    }

    public record Approval(ApprovalDimension dimension, ApprovalStatus status, String approver,
                           Instant expiresAt, String conditions, String evidenceRef) {
        public Approval {
            required(dimension, "dimension"); required(status, "status"); text(approver, "approver");
            required(expiresAt, "expiresAt"); text(evidenceRef, "evidenceRef");
            conditions = conditions == null ? "" : conditions;
        }
        public boolean acceptedAt(Instant at) {
            return status == ApprovalStatus.ACCEPTED && expiresAt.isAfter(at);
        }
    }

    public record Policy(double requiredInventoryCoverage, double requiredMappingCoverage,
                         double requiredBackfillCompletion, double requiredBackfillVerification,
                         long maximumCdcLagSeconds, double maximumShadowDifferenceRate,
                         double maximumUnplannedFallbackRate, int minimumHypercareStableDays,
                         double requiredEvidenceTraceability) {
        public Policy {
            rate(requiredInventoryCoverage, "requiredInventoryCoverage"); rate(requiredMappingCoverage, "requiredMappingCoverage");
            rate(requiredBackfillCompletion, "requiredBackfillCompletion"); rate(requiredBackfillVerification, "requiredBackfillVerification");
            rate(maximumShadowDifferenceRate, "maximumShadowDifferenceRate");
            rate(maximumUnplannedFallbackRate, "maximumUnplannedFallbackRate");
            rate(requiredEvidenceTraceability, "requiredEvidenceTraceability");
            if (maximumCdcLagSeconds < 0 || minimumHypercareStableDays < 1)
                throw new IllegalArgumentException("cutover policy limits are invalid");
        }
    }

    public interface EvidenceEnvelope {
        String cutoverRunId(); String targetArtifactId(); EvidenceStatus status();
        String authorityId(); Instant productionObservedAt(); List<String> evidenceRefs();
    }

    public record TopologySchemaEvidence(String cutoverRunId, String targetArtifactId, EvidenceStatus status,
                                         boolean topologyComplete, int unknownCallers, int ownerlessDependencies,
                                         int unknownDirectDatabaseConnections, int externalPartnersPending,
                                         boolean schemaExpandApplied, boolean oldAppReadsNewSchema,
                                         boolean oldAppWritesNewSchema, boolean newAppReadsOldData,
                                         boolean newAppWritesOldCompatibleData, boolean contractExecutedPrematurely,
                                         String authorityId, Instant productionObservedAt,
                                         List<String> evidenceRefs) implements EvidenceEnvelope {
        public TopologySchemaEvidence {
            common(cutoverRunId, targetArtifactId, status, authorityId, productionObservedAt);
            nonnegative(unknownCallers, ownerlessDependencies, unknownDirectDatabaseConnections, externalPartnersPending);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record AssetResult(String assetId, boolean mappingComplete, boolean backfillPlanned,
                              boolean backfillCompleted, boolean reconciliationPassed,
                              boolean cdcAtRequiredPosition, int unresolvedConflicts,
                              int dataLossEvents, int uncontrolledDuplicates,
                              boolean idMappingComplete, boolean valueTransformsVerified,
                              List<String> evidenceRefs) {
        public AssetResult {
            text(assetId, "assetId"); nonnegative(unresolvedConflicts, dataLossEvents, uncontrolledDuplicates);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record DataMigrationEvidence(String cutoverRunId, String targetArtifactId, EvidenceStatus status,
                                        double authoritativeInventoryCoverage, double mappingCoverage,
                                        boolean backfillPlanApproved, boolean backfillResumable,
                                        boolean backfillIdempotent, double backfillCompletionRate,
                                        double backfillVerificationRate, boolean cdcHealthy,
                                        long cdcLagSeconds, boolean cdcPositionsRecorded,
                                        double insertCoverage, double updateCoverage, double deleteCoverage,
                                        boolean duplicatesHandled, boolean outOfOrderHandled,
                                        boolean finalDeltaApplied, String finalSourcePosition,
                                        String finalTargetPosition, boolean finalReconciliationPassed,
                                        int unresolvedDataConflicts, List<AssetResult> assets,
                                        String authorityId, Instant productionObservedAt,
                                        List<String> evidenceRefs) implements EvidenceEnvelope {
        public DataMigrationEvidence {
            common(cutoverRunId, targetArtifactId, status, authorityId, productionObservedAt);
            rate(authoritativeInventoryCoverage, "authoritativeInventoryCoverage"); rate(mappingCoverage, "mappingCoverage");
            rate(backfillCompletionRate, "backfillCompletionRate"); rate(backfillVerificationRate, "backfillVerificationRate");
            rate(insertCoverage, "insertCoverage"); rate(updateCoverage, "updateCoverage"); rate(deleteCoverage, "deleteCoverage");
            if (cdcLagSeconds < 0 || unresolvedDataConflicts < 0) throw new IllegalArgumentException("data evidence counts are invalid");
            finalSourcePosition = finalSourcePosition == null ? "" : finalSourcePosition;
            finalTargetPosition = finalTargetPosition == null ? "" : finalTargetPosition;
            assets = copy(assets); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record WaveResult(String waveId, double targetReadPercent, double targetWritePercent,
                             boolean stableCohort, boolean readStable, boolean writeCanaryStable,
                             int criticalReadDifferences, int criticalWriteDifferences,
                             int dualPrimaryEvents, List<String> evidenceRefs) {
        public WaveResult {
            text(waveId, "waveId"); percent(targetReadPercent, "targetReadPercent"); percent(targetWritePercent, "targetWritePercent");
            nonnegative(criticalReadDifferences, criticalWriteDifferences, dualPrimaryEvents);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record TrafficAuthorityEvidence(String cutoverRunId, String targetArtifactId, EvidenceStatus status,
                                           Phase observedPhase, double targetReadPercent, double targetWritePercent,
                                           double sourceBusinessTrafficPercent, long sourceWriteCount,
                                           boolean targetSystemOfRecord, boolean shadowSideEffectsIsolated,
                                           double shadowReadDifferenceRate, int criticalReadDifferences,
                                           double unplannedFallbackRate, boolean targetReadPrimaryStable,
                                           boolean writeAuthorityRegistryReady, boolean stableCohortRouting,
                                           int dualPrimaryWriterEvents, boolean allWriteEntrypointsCompliant,
                                           boolean writeCanaryStable, int transactionRegressions,
                                           int securityRegressions, boolean finalWriteFreezeExecuted,
                                           boolean inFlightWritesDrained, boolean reverseSyncHealthy,
                                           long reverseSyncLagSeconds, boolean sourceFallbackCapacitySufficient,
                                           boolean rollbackPointVerified, boolean irreversibilityFrontierCrossed,
                                           boolean irreversibilityApproved, List<WaveResult> waves,
                                           String authorityId, Instant productionObservedAt,
                                           List<String> evidenceRefs) implements EvidenceEnvelope {
        public TrafficAuthorityEvidence {
            common(cutoverRunId, targetArtifactId, status, authorityId, productionObservedAt); required(observedPhase, "observedPhase");
            percent(targetReadPercent, "targetReadPercent"); percent(targetWritePercent, "targetWritePercent");
            percent(sourceBusinessTrafficPercent, "sourceBusinessTrafficPercent"); rate(shadowReadDifferenceRate, "shadowReadDifferenceRate");
            rate(unplannedFallbackRate, "unplannedFallbackRate");
            if (sourceWriteCount < 0 || reverseSyncLagSeconds < 0) throw new IllegalArgumentException("traffic counters are invalid");
            nonnegative(criticalReadDifferences, dualPrimaryWriterEvents, transactionRegressions, securityRegressions);
            waves = copy(waves); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record IntegrationEvidence(String cutoverRunId, String targetArtifactId, EvidenceStatus status,
                                      int messageLossEvents, int uncontrolledDuplicateMessages,
                                      int duplicateJobExecutions, int sourceConsumersEnabled, int sourceJobsEnabled,
                                      boolean producerCutoverComplete, boolean consumerOffsetsVerified,
                                      boolean sessionsCompatible, boolean longConnectionsDrained,
                                      boolean websocketReconnectIdempotent, int fileHashFailures,
                                      int cacheTenantContaminationEvents, int searchResultRegressions,
                                      String authorityId, Instant productionObservedAt,
                                      List<String> evidenceRefs) implements EvidenceEnvelope {
        public IntegrationEvidence {
            common(cutoverRunId, targetArtifactId, status, authorityId, productionObservedAt);
            nonnegative(messageLossEvents, uncontrolledDuplicateMessages, duplicateJobExecutions,
                    sourceConsumersEnabled, sourceJobsEnabled, fileHashFailures,
                    cacheTenantContaminationEvents, searchResultRegressions);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record RollbackIncidentEvidence(String cutoverRunId, String targetArtifactId, EvidenceStatus status,
                                           boolean trafficRollbackPlanValidated, boolean trafficRollbackDrillPassed,
                                           boolean dataRollbackPlanValidated, boolean dataRollbackDrillPassed,
                                           boolean automatedStopTriggersTested, boolean currentPhaseReversible,
                                           boolean reverseSyncWithinThreshold, boolean forwardFixPlanValidated,
                                           int unresolvedCriticalIncidents, boolean manualActionsRecorded,
                                           boolean destructiveActionAttemptedByControlPlane,
                                           String authorityId, Instant productionObservedAt,
                                           List<String> evidenceRefs) implements EvidenceEnvelope {
        public RollbackIncidentEvidence {
            common(cutoverRunId, targetArtifactId, status, authorityId, productionObservedAt);
            nonnegative(unresolvedCriticalIncidents); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record HypercareAcceptanceEvidence(String cutoverRunId, String targetArtifactId, EvidenceStatus status,
                                              int stableDays, int criticalIncidents,
                                              boolean sloContinuouslyPassed, boolean dataInvariantsPassed,
                                              boolean businessMetricsPassed, double unplannedFallbackRate,
                                              ApprovalStatus businessAcceptance, ApprovalStatus engineeringAcceptance,
                                              ApprovalStatus securityAcceptance, ApprovalStatus operationsAcceptance,
                                              ApprovalStatus complianceAcceptance, boolean operationsHandoffPassed,
                                              boolean runbooksExercised, boolean onCallActive,
                                              String authorityId, Instant productionObservedAt,
                                              List<String> evidenceRefs) implements EvidenceEnvelope {
        public HypercareAcceptanceEvidence {
            common(cutoverRunId, targetArtifactId, status, authorityId, productionObservedAt);
            if (stableDays < 0 || criticalIncidents < 0) throw new IllegalArgumentException("hypercare counts are invalid");
            rate(unplannedFallbackRate, "unplannedFallbackRate"); required(businessAcceptance, "businessAcceptance");
            required(engineeringAcceptance, "engineeringAcceptance"); required(securityAcceptance, "securityAcceptance");
            required(operationsAcceptance, "operationsAcceptance"); required(complianceAcceptance, "complianceAcceptance");
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record RetirementEvidence(String cutoverRunId, String targetArtifactId, EvidenceStatus status,
                                     double sourceBusinessTrafficPercent, long sourceWrites,
                                     int sourceConsumers, int sourceJobs, int hiddenDependencies,
                                     int openDirectDatabaseConnections, int externalPartnersPending,
                                     boolean trafficDrained, boolean archiveIntegrityVerified,
                                     boolean archiveRestorePassed, boolean legalHoldsPreserved,
                                     boolean credentialsRevoked, boolean dnsAndRoutesClosed,
                                     boolean infrastructureClosed, boolean licensesClosed,
                                     int unknownContinuingCosts, boolean legacySystemDecommissioned,
                                     boolean decommissionDualApproval, boolean decommissionExecutedByAuthority,
                                     boolean auditPackComplete, double evidenceTraceability,
                                     boolean benefitTrackingStarted, int openCriticalRisks,
                                     String authorityId, Instant productionObservedAt,
                                     List<String> evidenceRefs) implements EvidenceEnvelope {
        public RetirementEvidence {
            common(cutoverRunId, targetArtifactId, status, authorityId, productionObservedAt);
            percent(sourceBusinessTrafficPercent, "sourceBusinessTrafficPercent"); rate(evidenceTraceability, "evidenceTraceability");
            if (sourceWrites < 0) throw new IllegalArgumentException("sourceWrites cannot be negative");
            nonnegative(sourceConsumers, sourceJobs, hiddenDependencies, openDirectDatabaseConnections,
                    externalPartnersPending, unknownContinuingCosts, openCriticalRisks);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record Metrics(double inventoryCoverage, double mappingCoverage, double backfillCompletion,
                          double backfillVerification, long cdcLagSeconds, int unresolvedDataConflicts,
                          double targetReadPercent, double targetWritePercent, double sourceTrafficPercent,
                          long sourceWrites, int dualPrimaryEvents, int messageLossEvents,
                          int duplicateJobs, int hiddenDependencies, int criticalIncidents,
                          double evidenceTraceability) {}

    public record ConformanceReport(int batch, String cutoverRunId, String migrationId,
                                    String sourceArtifactId, String targetArtifactId, Phase observedPhase,
                                    Gate gate, RunStatus status, List<String> blockers,
                                    List<String> restrictions, Metrics metrics,
                                    boolean targetSystemOfRecord, boolean legacySystemDecommissioned,
                                    boolean migrationCompleted, Instant evaluatedAt,
                                    List<String> evidenceRefs) {
        public ConformanceReport {
            if (batch != 11) throw new IllegalArgumentException("batch must be 11");
            text(cutoverRunId, "cutoverRunId"); text(migrationId, "migrationId");
            text(sourceArtifactId, "sourceArtifactId"); text(targetArtifactId, "targetArtifactId");
            required(observedPhase, "observedPhase"); required(gate, "gate"); required(status, "status");
            blockers = copy(blockers); restrictions = copy(restrictions); required(metrics, "metrics");
            required(evaluatedAt, "evaluatedAt"); evidenceRefs = copy(evidenceRefs);
            if (migrationCompleted && (gate != Gate.C_G || !targetSystemOfRecord || !legacySystemDecommissioned))
                throw new IllegalArgumentException("migration completion requires C-G, target truth and legacy decommission");
        }
    }

    public record Outcome(Request request, TopologySchemaEvidence topologySchema,
                          DataMigrationEvidence dataMigration, TrafficAuthorityEvidence traffic,
                          IntegrationEvidence integrations, RollbackIncidentEvidence rollback,
                          HypercareAcceptanceEvidence hypercareAcceptance,
                          RetirementEvidence retirement, ConformanceReport report) {
        public Outcome { required(request, "request"); required(report, "report"); }
    }

    static <T> List<T> copy(Collection<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static void common(String run, String artifact, EvidenceStatus status, String authority, Instant observed) {
        text(run, "cutoverRunId"); text(artifact, "targetArtifactId"); required(status, "status");
        text(authority, "authorityId"); required(observed, "productionObservedAt");
    }
    static List<String> evidence(List<String> refs) {
        List<String> result = copy(refs); if (result.isEmpty()) throw new IllegalArgumentException("evidence refs are required"); return result;
    }
    static void nonnegative(int... values) { if (Arrays.stream(values).anyMatch(value -> value < 0)) throw new IllegalArgumentException("counts cannot be negative"); }
    static void text(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    static void required(Object value, String name) { if (value == null) throw new IllegalArgumentException(name + " is required"); }
    static void digest(String value, String name) { text(value, name); if (!value.matches("[A-Fa-f0-9]{64}")) throw new IllegalArgumentException(name + " must be sha-256"); }
    static void rate(double value, String name) { if (Double.isNaN(value) || value < 0 || value > 1) throw new IllegalArgumentException(name + " must be between 0 and 1"); }
    static void percent(double value, String name) { if (Double.isNaN(value) || value < 0 || value > 100) throw new IllegalArgumentException(name + " must be between 0 and 100"); }
}
