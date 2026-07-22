package io.elmos.cutover;

import java.util.*;
import java.util.function.Function;

import static io.elmos.cutover.ProductionCutoverModels.*;

/** Fail-closed C-A through C-G evaluator over externally observed production evidence. */
public final class ProductionCutoverService {
    private final ProductionCutoverAuthorities authorities;

    public ProductionCutoverService(ProductionCutoverAuthorities authorities) {
        this.authorities = Objects.requireNonNull(authorities, "authorities");
    }

    public Outcome evaluate(Request request) {
        Objects.requireNonNull(request, "request");
        admit(request);
        List<String> blockers = new ArrayList<>();
        TopologySchemaEvidence topology = call("topology/schema", blockers,
                () -> authorities.topologySchema().observe(request), request);
        DataMigrationEvidence data = call("data migration", blockers,
                () -> authorities.dataMigration().observe(request), request);
        TrafficAuthorityEvidence traffic = call("traffic/authority", blockers,
                () -> authorities.traffic().observe(request), request);
        IntegrationEvidence integration = call("integration", blockers,
                () -> authorities.integrations().observe(request), request);
        RollbackIncidentEvidence rollback = call("rollback/incident", blockers,
                () -> authorities.rollbackIncident().observe(request), request);
        HypercareAcceptanceEvidence acceptance = call("hypercare/acceptance", blockers,
                () -> authorities.hypercareAcceptance().observe(request), request);
        RetirementEvidence retirement = call("retirement", blockers,
                () -> authorities.retirement().observe(request), request);

        Gate gate = Gate.BLOCKED;
        boolean ca = gateA(request, topology, data);
        if (!ca) blockers.add("C-A data migration preparation requirements failed"); else gate = Gate.C_A;
        boolean cb = ca && gateB(request, data, traffic);
        if (cb) gate = Gate.C_B;
        boolean cc = cb && gateC(request, traffic, integration, rollback);
        if (cc) gate = Gate.C_C;
        boolean cd = cc && gateD(request, data, traffic, integration);
        if (cd) gate = Gate.C_D;
        boolean ce = cd && gateE(request, data, traffic, rollback);
        if (ce) gate = Gate.C_E;
        boolean cf = ce && gateF(request, traffic, integration, rollback, acceptance, retirement);
        if (cf) gate = Gate.C_F;
        boolean cg = cf && gateG(request, traffic, acceptance, retirement);
        if (cg) gate = Gate.C_G;

        if (traffic != null && traffic.observedPhase() != request.currentPhase())
            blockers.add("declared phase does not match observed production routing phase");
        if (traffic != null && !phaseRoutingConsistent(request.currentPhase(), traffic))
            blockers.add("observed read/write routing is inconsistent with the PCCM phase");
        Gate requiredForObservedPhase = ProductionCutoverStateMachine.minimumEvidenceForObservedPhase(request.currentPhase());
        if (gate.level() < requiredForObservedPhase.level())
            blockers.add("observed production phase exceeds its evidenced gate");
        if (rollback != null && rollback.destructiveActionAttemptedByControlPlane())
            blockers.add("control-plane destructive production action is prohibited");

        boolean completed = gate == Gate.C_G && blockers.isEmpty();
        boolean targetTruth = completed && traffic.targetSystemOfRecord();
        boolean decommissioned = completed && retirement.legacySystemDecommissioned();
        RunStatus status = blockers.isEmpty() ? statusFor(request.currentPhase(), completed) : RunStatus.BLOCKED;
        List<String> restrictions = new ArrayList<>(request.approvals().stream()
                .filter(value -> value.status() == ApprovalStatus.ACCEPTED_WITH_CONDITIONS)
                .map(value -> value.dimension() + ": " + value.conditions()).toList());
        if (gate != Gate.C_G) restrictions.add("next gate " + Gate.values()[gate.ordinal() + 1] + " is not yet evidenced");
        List<String> evidenceRefs = refs(topology, data, traffic, integration, rollback, acceptance, retirement);
        ConformanceReport report = new ConformanceReport(11, request.cutoverRunId(), request.migrationId(),
                request.sourceArtifact().artifactId(), request.targetArtifact().artifactId(), request.currentPhase(),
                gate, status, blockers, restrictions, metrics(data, traffic, integration, acceptance, retirement),
                targetTruth, decommissioned, completed, request.observedAt(), evidenceRefs);
        return new Outcome(request, topology, data, traffic, integration, rollback, acceptance, retirement, report);
    }

    private static void admit(Request request) {
        if (!request.batch10Eligible()) throw new IllegalArgumentException("Batch 10 eligibility is required");
        if (request.sourceArtifact().role() != SystemRole.SOURCE || request.targetArtifact().role() != SystemRole.TARGET)
            throw new IllegalArgumentException("source and target artifact roles are invalid");
        if (!request.sourceArtifact().immutable() || !request.targetArtifact().immutable())
            throw new IllegalArgumentException("source and target artifacts must be immutable");
        if (!request.targetArtifact().eligibleForProgressiveDelivery()
                || !Set.of("P_E", "P_F").contains(request.targetArtifact().batch10Gate()))
            throw new IllegalArgumentException("target artifact must pass Batch 10 P-E or P-F");
        if (request.sourceArtifact().evidenceRefs().isEmpty() || request.targetArtifact().evidenceRefs().isEmpty())
            throw new IllegalArgumentException("artifact evidence is required");

        Map<String, MigrationWave> waves = uniqueBy(request.waves(), MigrationWave::waveId, "wave");
        Set<Integer> orders = new TreeSet<>();
        for (MigrationWave wave : waves.values()) {
            if (!orders.add(wave.order())) throw new IllegalArgumentException("duplicate wave order");
            if (!wave.stableSegmentation() || !wave.independentlyReversible())
                throw new IllegalArgumentException("every wave needs stable segmentation and independent rollback");
        }
        if (!orders.equals(new TreeSet<>(java.util.stream.IntStream.rangeClosed(1, waves.size()).boxed().toList())))
            throw new IllegalArgumentException("wave orders must be contiguous from one");
        uniqueBy(request.dataAssets(), DataAsset::assetId, "data asset");
        if (request.dataAssets().stream().noneMatch(DataAsset::authoritative))
            throw new IllegalArgumentException("at least one authoritative data asset is required");
        Set<String> authorityKeys = new HashSet<>();
        for (AggregateAuthority authority : request.authorities()) {
            if (!authorityKeys.add(authority.aggregateId() + "\u0000" + authority.segmentId()))
                throw new IllegalArgumentException("duplicate aggregate authority");
            if (authority.phase() != request.currentPhase())
                throw new IllegalArgumentException("authority phase does not match the cutover phase");
        }
        for (ApprovalDimension dimension : List.of(ApprovalDimension.ENGINEERING, ApprovalDimension.OPERATIONS,
                ApprovalDimension.SECURITY, ApprovalDimension.BUSINESS)) {
            long count = request.approvals().stream().filter(value -> value.dimension() == dimension && value.acceptedAt(request.observedAt())).count();
            if (count != 1) throw new IllegalArgumentException("one current accepted approval is required for " + dimension);
        }
    }

    private static boolean gateA(Request request, TopologySchemaEvidence top, DataMigrationEvidence data) {
        if (!passed(top) || !passed(data)) return false;
        Set<String> expectedAssets = request.dataAssets().stream().map(DataAsset::assetId).collect(java.util.stream.Collectors.toSet());
        Map<String, AssetResult> actual;
        try { actual = uniqueBy(data.assets(), AssetResult::assetId, "asset result"); }
        catch (IllegalArgumentException error) { return false; }
        boolean assetCoverage = actual.keySet().equals(expectedAssets) && request.dataAssets().stream().allMatch(asset -> {
            AssetResult result = actual.get(asset.assetId());
            return result != null && (!asset.authoritative() || (result.mappingComplete() && result.backfillPlanned()))
                    && asset.mappingCoverage() >= request.policy().requiredMappingCoverage()
                    && (!asset.irreversibleTransformation() || asset.lossyTransformationApproved());
        });
        return top.topologyComplete() && top.unknownCallers() == 0 && top.ownerlessDependencies() == 0
                && top.unknownDirectDatabaseConnections() == 0 && top.externalPartnersPending() == 0
                && top.schemaExpandApplied() && top.oldAppReadsNewSchema() && top.oldAppWritesNewSchema()
                && top.newAppReadsOldData() && top.newAppWritesOldCompatibleData() && !top.contractExecutedPrematurely()
                && data.authoritativeInventoryCoverage() >= request.policy().requiredInventoryCoverage()
                && data.mappingCoverage() >= request.policy().requiredMappingCoverage()
                && data.backfillPlanApproved() && data.backfillResumable() && data.backfillIdempotent()
                && data.cdcHealthy() && data.cdcPositionsRecorded() && data.insertCoverage() == 1.0
                && data.updateCoverage() == 1.0 && data.deleteCoverage() == 1.0 && assetCoverage;
    }

    private static boolean gateB(Request request, DataMigrationEvidence data, TrafficAuthorityEvidence traffic) {
        if (!passed(data) || !passed(traffic)) return false;
        return data.backfillCompletionRate() >= request.policy().requiredBackfillCompletion()
                && data.backfillVerificationRate() >= request.policy().requiredBackfillVerification()
                && data.cdcHealthy() && data.cdcLagSeconds() <= request.policy().maximumCdcLagSeconds()
                && data.duplicatesHandled() && data.outOfOrderHandled()
                && data.assets().stream().filter(result -> authoritative(request, result.assetId()))
                .allMatch(result -> result.backfillCompleted() && result.reconciliationPassed())
                && traffic.shadowSideEffectsIsolated()
                && traffic.shadowReadDifferenceRate() <= request.policy().maximumShadowDifferenceRate()
                && traffic.criticalReadDifferences() == 0 && wavesCovered(request, traffic);
    }

    private static boolean gateC(Request request, TrafficAuthorityEvidence traffic,
                                 IntegrationEvidence integration, RollbackIncidentEvidence rollback) {
        if (!passed(traffic) || !passed(integration) || !passed(rollback)) return false;
        return traffic.targetReadPercent() == 100 && traffic.targetReadPrimaryStable()
                && traffic.writeAuthorityRegistryReady() && traffic.stableCohortRouting()
                && traffic.dualPrimaryWriterEvents() == 0 && traffic.allWriteEntrypointsCompliant()
                && request.authorities().stream().allMatch(authority -> authority.allEntrypointsCompliant()
                && !authority.dualPrimaryDetected() && authority.atomicallyPublished() && !authority.clientCanOverride())
                && integration.sessionsCompatible() && integration.websocketReconnectIdempotent()
                && rollback.trafficRollbackPlanValidated() && rollback.trafficRollbackDrillPassed()
                && rollback.dataRollbackPlanValidated() && rollback.dataRollbackDrillPassed()
                && rollback.automatedStopTriggersTested() && rollback.forwardFixPlanValidated();
    }

    private static boolean gateD(Request request, DataMigrationEvidence data,
                                 TrafficAuthorityEvidence traffic, IntegrationEvidence integration) {
        if (!passed(data) || !passed(traffic) || !passed(integration)) return false;
        boolean positionsMatch = !data.finalSourcePosition().isBlank()
                && data.finalSourcePosition().equals(data.finalTargetPosition());
        return traffic.targetWritePercent() > 0 && traffic.writeCanaryStable()
                && traffic.dualPrimaryWriterEvents() == 0 && traffic.transactionRegressions() == 0
                && traffic.securityRegressions() == 0 && traffic.finalWriteFreezeExecuted()
                && traffic.inFlightWritesDrained() && data.finalDeltaApplied() && positionsMatch
                && data.finalReconciliationPassed() && data.unresolvedDataConflicts() == 0
                && data.assets().stream().filter(result -> authoritative(request, result.assetId()))
                .allMatch(result -> result.cdcAtRequiredPosition() && result.unresolvedConflicts() == 0
                        && result.dataLossEvents() == 0 && result.uncontrolledDuplicates() == 0
                        && result.idMappingComplete() && result.valueTransformsVerified())
                && integration.messageLossEvents() == 0 && integration.uncontrolledDuplicateMessages() == 0
                && integration.duplicateJobExecutions() == 0 && integration.fileHashFailures() == 0
                && integration.cacheTenantContaminationEvents() == 0 && integration.searchResultRegressions() == 0;
    }

    private static boolean gateE(Request request, DataMigrationEvidence data,
                                 TrafficAuthorityEvidence traffic, RollbackIncidentEvidence rollback) {
        if (!passed(data) || !passed(traffic) || !passed(rollback)) return false;
        return traffic.targetWritePercent() == 100 && traffic.targetSystemOfRecord()
                && traffic.sourceWriteCount() == 0 && traffic.reverseSyncHealthy()
                && traffic.reverseSyncLagSeconds() <= request.policy().maximumCdcLagSeconds()
                && traffic.sourceFallbackCapacitySufficient() && traffic.rollbackPointVerified()
                && data.unresolvedDataConflicts() == 0 && rollback.unresolvedCriticalIncidents() == 0
                && rollback.manualActionsRecorded()
                && (!traffic.irreversibilityFrontierCrossed() || traffic.irreversibilityApproved());
    }

    private static boolean gateF(Request request, TrafficAuthorityEvidence traffic,
                                 IntegrationEvidence integration, RollbackIncidentEvidence rollback,
                                 HypercareAcceptanceEvidence acceptance, RetirementEvidence retirement) {
        if (!passed(traffic) || !passed(integration) || !passed(rollback) || !passed(acceptance) || !passed(retirement)) return false;
        return acceptance.stableDays() >= request.policy().minimumHypercareStableDays()
                && acceptance.criticalIncidents() == 0 && acceptance.sloContinuouslyPassed()
                && acceptance.dataInvariantsPassed() && acceptance.businessMetricsPassed()
                && acceptance.unplannedFallbackRate() <= request.policy().maximumUnplannedFallbackRate()
                && acceptance.businessAcceptance() == ApprovalStatus.ACCEPTED
                && acceptance.operationsHandoffPassed() && acceptance.runbooksExercised() && acceptance.onCallActive()
                && traffic.sourceBusinessTrafficPercent() == 0 && traffic.sourceWriteCount() == 0
                && integration.sourceConsumersEnabled() == 0 && integration.sourceJobsEnabled() == 0
                && integration.longConnectionsDrained() && retirement.sourceBusinessTrafficPercent() == 0
                && retirement.sourceWrites() == 0 && retirement.sourceConsumers() == 0 && retirement.sourceJobs() == 0
                && retirement.hiddenDependencies() == 0 && retirement.openDirectDatabaseConnections() == 0
                && retirement.externalPartnersPending() == 0 && retirement.trafficDrained()
                && retirement.archiveIntegrityVerified() && retirement.archiveRestorePassed()
                && retirement.legalHoldsPreserved() && retirement.decommissionDualApproval()
                && approved(request, ApprovalDimension.DECOMMISSION);
    }

    private static boolean gateG(Request request, TrafficAuthorityEvidence traffic,
                                 HypercareAcceptanceEvidence acceptance, RetirementEvidence retirement) {
        if (!passed(traffic) || !passed(acceptance) || !passed(retirement)) return false;
        return request.currentPhase() == Phase.P12_DECOMMISSIONED
                && traffic.targetSystemOfRecord() && traffic.targetReadPercent() == 100 && traffic.targetWritePercent() == 100
                && acceptance.businessAcceptance() == ApprovalStatus.ACCEPTED
                && acceptance.engineeringAcceptance() == ApprovalStatus.ACCEPTED
                && acceptance.securityAcceptance() == ApprovalStatus.ACCEPTED
                && acceptance.operationsAcceptance() == ApprovalStatus.ACCEPTED
                && acceptance.complianceAcceptance() == ApprovalStatus.ACCEPTED
                && retirement.credentialsRevoked() && retirement.dnsAndRoutesClosed()
                && retirement.infrastructureClosed() && retirement.licensesClosed()
                && retirement.unknownContinuingCosts() == 0 && retirement.legacySystemDecommissioned()
                && retirement.decommissionExecutedByAuthority() && retirement.auditPackComplete()
                && retirement.evidenceTraceability() >= request.policy().requiredEvidenceTraceability()
                && retirement.benefitTrackingStarted() && retirement.openCriticalRisks() == 0;
    }

    private static boolean approved(Request request, ApprovalDimension dimension) {
        return request.approvals().stream().anyMatch(value -> value.dimension() == dimension && value.acceptedAt(request.observedAt()));
    }

    private static boolean wavesCovered(Request request, TrafficAuthorityEvidence traffic) {
        Map<String, WaveResult> actual;
        try { actual = uniqueBy(traffic.waves(), WaveResult::waveId, "wave result"); }
        catch (IllegalArgumentException error) { return false; }
        return actual.keySet().equals(request.waves().stream().map(MigrationWave::waveId).collect(java.util.stream.Collectors.toSet()))
                && actual.values().stream().allMatch(value -> value.stableCohort()
                && value.criticalReadDifferences() == 0);
    }

    private static boolean authoritative(Request request, String assetId) {
        return request.dataAssets().stream().anyMatch(asset -> asset.assetId().equals(assetId) && asset.authoritative());
    }

    private static boolean phaseRoutingConsistent(Phase phase, TrafficAuthorityEvidence traffic) {
        return switch (phase) {
            case P0_PREPARED, P1_SCHEMA_EXPANDED, P2_BACKFILL_RUNNING,
                    P3_INCREMENTAL_SYNC_HEALTHY, P4_SHADOW_READ ->
                    traffic.targetReadPercent() == 0 && traffic.targetWritePercent() == 0;
            case P5_READ_CANARY -> traffic.targetReadPercent() > 0 && traffic.targetReadPercent() < 100
                    && traffic.targetWritePercent() == 0;
            case P6_TARGET_READ_PRIMARY -> traffic.targetReadPercent() == 100 && traffic.targetWritePercent() == 0;
            case P7_WRITE_CANARY -> traffic.targetReadPercent() == 100
                    && traffic.targetWritePercent() > 0 && traffic.targetWritePercent() < 100;
            case P8_TARGET_WRITE_PRIMARY, P9_SOURCE_READ_ONLY, P10_HYPERCARE,
                    P11_RETIREMENT_CANDIDATE, P12_DECOMMISSIONED ->
                    traffic.targetReadPercent() == 100 && traffic.targetWritePercent() == 100;
        };
    }

    private static boolean passed(EvidenceEnvelope evidence) { return evidence != null && evidence.status() == EvidenceStatus.PASSED; }

    private static Metrics metrics(DataMigrationEvidence data, TrafficAuthorityEvidence traffic,
                                   IntegrationEvidence integration, HypercareAcceptanceEvidence acceptance,
                                   RetirementEvidence retirement) {
        return new Metrics(data == null ? 0 : data.authoritativeInventoryCoverage(), data == null ? 0 : data.mappingCoverage(),
                data == null ? 0 : data.backfillCompletionRate(), data == null ? 0 : data.backfillVerificationRate(),
                data == null ? Long.MAX_VALUE : data.cdcLagSeconds(), data == null ? Integer.MAX_VALUE : data.unresolvedDataConflicts(),
                traffic == null ? 0 : traffic.targetReadPercent(), traffic == null ? 0 : traffic.targetWritePercent(),
                traffic == null ? 100 : traffic.sourceBusinessTrafficPercent(), traffic == null ? Long.MAX_VALUE : traffic.sourceWriteCount(),
                traffic == null ? Integer.MAX_VALUE : traffic.dualPrimaryWriterEvents(), integration == null ? Integer.MAX_VALUE : integration.messageLossEvents(),
                integration == null ? Integer.MAX_VALUE : integration.duplicateJobExecutions(), retirement == null ? Integer.MAX_VALUE : retirement.hiddenDependencies(),
                acceptance == null ? Integer.MAX_VALUE : acceptance.criticalIncidents(), retirement == null ? 0 : retirement.evidenceTraceability());
    }

    private static RunStatus statusFor(Phase phase, boolean completed) {
        if (completed) return RunStatus.COMPLETED;
        return switch (phase) {
            case P0_PREPARED, P1_SCHEMA_EXPANDED -> RunStatus.PREPARING;
            case P2_BACKFILL_RUNNING -> RunStatus.BACKFILLING;
            case P3_INCREMENTAL_SYNC_HEALTHY -> RunStatus.CATCHING_UP;
            case P4_SHADOW_READ -> RunStatus.SHADOW_READING;
            case P5_READ_CANARY -> RunStatus.READ_CANARY;
            case P6_TARGET_READ_PRIMARY -> RunStatus.TARGET_READ_PRIMARY;
            case P7_WRITE_CANARY -> RunStatus.WRITE_CANARY;
            case P8_TARGET_WRITE_PRIMARY -> RunStatus.TARGET_WRITE_PRIMARY;
            case P9_SOURCE_READ_ONLY -> RunStatus.SOURCE_READ_ONLY;
            case P10_HYPERCARE -> RunStatus.HYPERCARE;
            case P11_RETIREMENT_CANDIDATE -> RunStatus.RETIRING;
            case P12_DECOMMISSIONED -> RunStatus.ACCEPTED;
        };
    }

    private static List<String> refs(EvidenceEnvelope... values) {
        return Arrays.stream(values).filter(Objects::nonNull).flatMap(value -> value.evidenceRefs().stream()).distinct().toList();
    }

    private interface AuthorityCall<T extends EvidenceEnvelope> { T call(); }
    private static <T extends EvidenceEnvelope> T call(String label, List<String> blockers,
                                                       AuthorityCall<T> call, Request request) {
        final T value;
        try { value = call.call(); }
        catch (RuntimeException error) {
            blockers.add(label + " authority failed safely: " + error.getClass().getSimpleName()); return null;
        }
        if (value == null) { blockers.add(label + " authority returned no evidence"); return null; }
        if (!value.cutoverRunId().equals(request.cutoverRunId())) { blockers.add(label + " evidence run mismatch"); return null; }
        if (!value.targetArtifactId().equals(request.targetArtifact().artifactId())) { blockers.add(label + " evidence artifact mismatch"); return null; }
        if (value.evidenceRefs().isEmpty()) { blockers.add(label + " evidence references are missing"); return null; }
        if (value.productionObservedAt().isAfter(request.observedAt())) { blockers.add(label + " evidence is from the future"); return null; }
        return value;
    }

    private static <T> Map<String, T> uniqueBy(List<T> values, Function<T, String> key, String label) {
        Map<String, T> result = new LinkedHashMap<>();
        for (T value : values) if (result.putIfAbsent(key.apply(value), value) != null)
            throw new IllegalArgumentException("duplicate " + label + ": " + key.apply(value));
        return result;
    }
}
