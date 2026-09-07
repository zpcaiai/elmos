package io.elmos.hardening;

import java.time.Instant;
import java.util.*;
import java.util.function.Function;

import static io.elmos.hardening.ProductionHardeningModels.*;

/** Fail-closed Batch 10 gate evaluator. It evaluates evidence; it never executes a deployment. */
public final class ProductionHardeningService {
    private final ProductionHardeningAuthorities authorities;

    public ProductionHardeningService(ProductionHardeningAuthorities authorities) {
        this.authorities = Objects.requireNonNull(authorities, "authorities");
    }

    public Outcome evaluate(Request request) {
        Objects.requireNonNull(request, "request");
        admit(request);
        Set<String> serviceIds = new LinkedHashSet<>();
        request.deploymentUnits().forEach(unit -> serviceIds.add(unit.serviceId()));
        List<String> globalBlockers = new ArrayList<>();

        Map<String, ServiceCalibration> calibrations = callAndIndex("environment calibration", globalBlockers,
                () -> authorities.environment().calibrate(request), serviceIds,
                ServiceCalibration::serviceId, ServiceCalibration::artifactId, ServiceCalibration::evidenceRefs,
                request.targetArtifactId());
        Map<String, PerformanceEvidence> performance = callAndIndex("performance", globalBlockers,
                () -> authorities.performance().assess(request, calibrations), serviceIds,
                PerformanceEvidence::serviceId, PerformanceEvidence::artifactId, PerformanceEvidence::evidenceRefs,
                request.targetArtifactId());
        Map<String, SecurityEvidence> security = callAndIndex("security", globalBlockers,
                () -> authorities.security().assess(request), serviceIds,
                SecurityEvidence::serviceId, SecurityEvidence::artifactId, SecurityEvidence::evidenceRefs,
                request.targetArtifactId());
        Map<String, ReliabilityEvidence> reliability = callAndIndex("reliability", globalBlockers,
                () -> authorities.reliability().assess(request), serviceIds,
                ReliabilityEvidence::serviceId, ReliabilityEvidence::artifactId, ReliabilityEvidence::evidenceRefs,
                request.targetArtifactId());
        Map<String, ObservabilityEvidence> observability = callAndIndex("observability", globalBlockers,
                () -> authorities.observability().assess(request), serviceIds,
                ObservabilityEvidence::serviceId, ObservabilityEvidence::artifactId, ObservabilityEvidence::evidenceRefs,
                request.targetArtifactId());
        Map<String, ReleaseEvidence> release = callAndIndex("release", globalBlockers,
                () -> authorities.release().assess(request), serviceIds,
                ReleaseEvidence::serviceId, ReleaseEvidence::artifactId, ReleaseEvidence::evidenceRefs,
                request.targetArtifactId());
        Map<String, CostEvidence> costs = callAndIndex("cost", globalBlockers,
                () -> authorities.cost().assess(request), serviceIds,
                CostEvidence::serviceId, CostEvidence::artifactId, CostEvidence::evidenceRefs,
                request.targetArtifactId());

        Map<String, RiskProfile> profiles = uniqueBy(request.riskProfiles(), RiskProfile::serviceId, "risk profile");
        List<ServiceGate> serviceGates = new ArrayList<>();
        for (String serviceId : serviceIds) {
            serviceGates.add(evaluateService(request, serviceId, profiles.get(serviceId), calibrations.get(serviceId),
                    performance.get(serviceId), security.get(serviceId), reliability.get(serviceId),
                    observability.get(serviceId), release.get(serviceId), costs.get(serviceId)));
        }

        boolean progressive = globalBlockers.isEmpty()
                && serviceGates.stream().allMatch(ServiceGate::eligibleForProgressiveDelivery);
        boolean restrictions = request.openRisks().stream().anyMatch(risk -> !risk.releaseBlocking());
        RunStatus status = progressive
                ? (restrictions ? RunStatus.READY_WITH_RESTRICTIONS : RunStatus.READY_FOR_PROGRESSIVE_DELIVERY)
                : RunStatus.BLOCKED;
        List<String> reportBlockers = new ArrayList<>(globalBlockers);
        serviceGates.forEach(gate -> gate.blockers().forEach(blocker -> reportBlockers.add(gate.serviceId() + ": " + blocker)));
        ConformanceReport report = new ConformanceReport(10, request.hardeningRunId(), request.targetArtifactId(),
                status, serviceGates, reportBlockers, progressive, false, false, request.observedAt());
        return new Outcome(request, calibrations, performance, security, reliability, observability, release, costs, report);
    }

    private static void admit(Request request) {
        if (!request.batch9Eligible() || !request.artifact().batch8Passed() || !request.artifact().batch9Passed())
            throw new IllegalArgumentException("Batch 8 and Batch 9 evidence must pass before Batch 10");
        if (!request.artifact().immutable()) throw new IllegalArgumentException("Batch 10 requires an immutable artifact");
        if (request.artifact().evidenceRefs().isEmpty()) throw new IllegalArgumentException("artifact evidence is required");
        if (request.scenarios().size() > request.policy().maximumScenarios())
            throw new IllegalArgumentException("scenario count exceeds the approved policy limit");

        Map<String, DeploymentUnit> units = uniqueBy(request.deploymentUnits(), DeploymentUnit::serviceId, "deployment unit");
        Map<String, RiskProfile> profiles = uniqueBy(request.riskProfiles(), RiskProfile::serviceId, "risk profile");
        Map<String, WorkloadModel> workloads = uniqueBy(request.workloadModels(), WorkloadModel::serviceId, "workload model");
        if (!profiles.keySet().equals(units.keySet())) throw new IllegalArgumentException("every service needs exactly one risk profile");
        if (!workloads.keySet().equals(units.keySet())) throw new IllegalArgumentException("every service needs exactly one workload model");
        for (DeploymentUnit unit : units.values()) {
            RiskProfile profile = profiles.get(unit.serviceId());
            WorkloadModel workload = workloads.get(unit.serviceId());
            if (!profile.approved()) throw new IllegalArgumentException("risk profile is not approved: " + unit.serviceId());
            if (unit.highRisk() && profile.tier().level() < RiskTier.TIER_3.level())
                throw new IllegalArgumentException("high-risk service cannot be downgraded below TIER_3: " + unit.serviceId());
            if (!workload.sanitized() || !workload.credentialsRemoved() || workload.evidenceRefs().isEmpty())
                throw new IllegalArgumentException("workload is not sanitized and evidence-bound: " + unit.serviceId());
            EnumSet<ScenarioKind> kinds = EnumSet.noneOf(ScenarioKind.class);
            for (HardeningScenario scenario : request.scenarios()) {
                if (!scenario.serviceId().equals(unit.serviceId())) continue;
                kinds.add(scenario.kind());
            }
            requireKinds(unit.serviceId(), kinds, ScenarioKind.NORMAL, ScenarioKind.PEAK, ScenarioKind.STRESS,
                    ScenarioKind.SECURITY, ScenarioKind.OBSERVABILITY, ScenarioKind.CANARY, ScenarioKind.ROLLBACK,
                    ScenarioKind.COST);
            if (profile.requireSoak()) requireKinds(unit.serviceId(), kinds, ScenarioKind.SOAK);
            if (profile.requireBackupRestore()) requireKinds(unit.serviceId(), kinds, ScenarioKind.RESTORE);
            if (profile.requirePitr()) requireKinds(unit.serviceId(), kinds, ScenarioKind.PITR);
            if (profile.requireDisasterRecovery()) requireKinds(unit.serviceId(), kinds, ScenarioKind.DISASTER_RECOVERY);
            if (profile.tier().level() >= RiskTier.TIER_3.level())
                requireKinds(unit.serviceId(), kinds, ScenarioKind.CHAOS, ScenarioKind.CRASH);
        }
        Set<String> scenarioIds = new HashSet<>();
        for (HardeningScenario scenario : request.scenarios()) {
            if (!units.containsKey(scenario.serviceId())) throw new IllegalArgumentException("scenario references unknown service");
            if (!scenarioIds.add(scenario.scenarioId())) throw new IllegalArgumentException("duplicate scenario id: " + scenario.scenarioId());
            if (!scenario.artifactId().equals(request.targetArtifactId())) throw new IllegalArgumentException("scenario artifact mismatch");
            if (!scenario.nonProduction() || scenario.usesProductionDependency())
                throw new IllegalArgumentException("Batch 10 scenarios must be isolated from production");
            if (scenario.destructive() || scenario.kind() == ScenarioKind.CHAOS || scenario.kind() == ScenarioKind.STRESS) {
                if (!scenario.abortConditionsDefined() || !scenario.killSwitchDefined())
                    throw new IllegalArgumentException("destructive, chaos and stress scenarios need abort conditions and kill switches");
            }
        }
        for (OpenRisk risk : request.openRisks()) {
            if (!units.containsKey(risk.serviceId())) throw new IllegalArgumentException("risk references unknown service");
            if (risk.approved() && !risk.expiresAt().isAfter(request.observedAt()))
                throw new IllegalArgumentException("risk approval is expired: " + risk.riskId());
        }
    }

    private static void requireKinds(String service, Set<ScenarioKind> actual, ScenarioKind... required) {
        for (ScenarioKind kind : required) if (!actual.contains(kind))
            throw new IllegalArgumentException("missing " + kind + " scenario for " + service);
    }

    private static ServiceGate evaluateService(Request request, String serviceId, RiskProfile profile,
                                               ServiceCalibration calibration, PerformanceEvidence perf,
                                               SecurityEvidence sec, ReliabilityEvidence rel,
                                               ObservabilityEvidence obs, ReleaseEvidence release,
                                               CostEvidence cost) {
        List<String> blockers = new ArrayList<>();
        List<String> restrictions = request.openRisks().stream()
                .filter(risk -> risk.serviceId().equals(serviceId) && !risk.releaseBlocking())
                .map(risk -> risk.riskId() + ": " + risk.mitigation()).toList();
        Gate gate = Gate.BLOCKED;

        if (calibration == null) blockers.add("missing environment calibration evidence");
        if (perf == null) blockers.add("missing performance evidence");
        boolean pa = calibration != null && perf != null
                && safe(calibration.productionResourceAccessed(), calibration.secretMaterialObserved())
                && calibration.valid() && calibration.repeatedRunVariance() <= request.policy().maximumEnvironmentVariance()
                && calibration.warmupExcluded() && calibration.autoscalingDisabled() && !calibration.generatorSaturated()
                && calibration.sourceResourcesComparable() && calibration.dataVolumeComparable()
                && safe(perf.productionResourceAccessed(), perf.secretMaterialObserved())
                && perf.status() == EvidenceStatus.PASSED && perf.normalLoadPassed() && perf.peakLoadPassed()
                && perf.stressComplete() && perf.p95SloPassed() && perf.p99SloPassed() && perf.errorRateSloPassed()
                && perf.saturationControlled() && perf.recoveredAfterOverload()
                && perf.requiredScenarioPassRate() >= request.policy().requiredPerformancePassRate()
                && perf.headroomPercent() >= profile.minimumHeadroomPercent()
                && perf.criticalRegressions() == 0 && perf.unexplainedLeaks() == 0 && !perf.unboundedResourceGrowth()
                && (!profile.requireSoak() || perf.soakPassed());
        if (!pa) blockers.add("P-A performance or calibration requirements failed");
        else gate = Gate.P_A;

        if (sec == null) blockers.add("missing security evidence");
        boolean pb = pa && sec != null && safe(sec.productionResourceAccessed(), sec.secretMaterialObserved())
                && sec.status() == EvidenceStatus.PASSED && sec.criticalVulnerabilities() == 0
                && sec.exploitableHighVulnerabilities() == 0 && sec.criticalSastFindings() == 0
                && sec.criticalDastFindings() == 0 && sec.secretLeaks() == 0
                && sec.authenticationRegressions() == 0 && sec.authorizationRegressions() == 0
                && sec.tenantIsolationRegressions() == 0 && sec.weakCryptographyFindings() == 0
                && sec.criticalConfigurationFindings() == 0 && sec.unknownOriginBinaries() == 0
                && sec.unapprovedSecurityWaivers() == 0
                && sec.criticalScenarioPassRate() >= request.policy().requiredCriticalSecurityPassRate()
                && (!profile.requirePenetration() || sec.penetrationPassed())
                && sec.sbomComplete() && sec.sbomMatchesArtifact() && sec.fixedImageDigest() && sec.nonRootLeastPrivilege();
        if (pa && !pb) blockers.add("P-B security requirements failed");
        else if (pb) gate = Gate.P_B;

        if (rel == null) blockers.add("missing reliability and recovery evidence");
        boolean pc = pb && rel != null && safe(rel.productionResourceAccessed(), rel.secretMaterialObserved())
                && !rel.destructiveProductionChaos() && rel.status() == EvidenceStatus.PASSED
                && rel.criticalChaosPassRate() >= request.policy().requiredCriticalChaosPassRate()
                && rel.recoveryScenarioPassRate() == 1.0 && rel.dataCorruptionEvents() == 0
                && rel.unboundedRetries() == 0 && rel.unboundedQueues() == 0 && rel.retryStorms() == 0
                && rel.crashConsistencyPassed() && rel.dependencyRecoveryPassed() && rel.abortAndKillSwitchesVerified()
                && (!profile.requireBackupRestore() || rel.backupRestorePassed())
                && (!profile.requirePitr() || rel.pitrPassed())
                && (!profile.requireDisasterRecovery() || (rel.rpoPassed() && rel.rtoPassed() && rel.failoverAndFailbackPassed()));
        if (pb && !pc) blockers.add("P-C reliability, recovery or chaos requirements failed");
        else if (pc) gate = Gate.P_C;

        if (obs == null) blockers.add("missing observability evidence");
        boolean pd = pc && obs != null && safe(obs.productionResourceAccessed(), obs.secretMaterialObserved())
                && obs.status() == EvidenceStatus.PASSED
                && obs.criticalSliCoverage() >= request.policy().requiredCriticalSliCoverage()
                && obs.alertCoverage() >= request.policy().requiredAlertCoverage()
                && obs.runbookCoverage() >= request.policy().requiredRunbookCoverage()
                && obs.traceCoverage() >= request.policy().requiredTraceCoverage()
                && obs.sloCalculable() && obs.criticalAlertsTested() && obs.criticalRunbooksValidated()
                && obs.correlationPassed() && obs.telemetryOverheadWithinBudget()
                && obs.sensitiveTelemetryLeaks() == 0 && obs.unboundedMetricLabels() == 0;
        if (pc && !pd) blockers.add("P-D observability and operability requirements failed");
        else if (pd) gate = Gate.P_D;

        if (release == null) blockers.add("missing release evidence");
        if (cost == null) blockers.add("missing capacity cost evidence");
        boolean blockingRisk = request.openRisks().stream().anyMatch(risk -> risk.serviceId().equals(serviceId)
                && (risk.releaseBlocking() || risk.severity() == Severity.CRITICAL || !risk.approved()));
        boolean pe = pd && release != null && cost != null
                && safe(release.productionResourceAccessed(), release.secretMaterialObserved())
                && !release.productionDeploymentExecuted() && release.progressiveDeliveryOnly()
                && release.status() == EvidenceStatus.PASSED && release.artifactImmutable()
                && release.artifactSigned() && release.signatureVerified() && release.provenanceComplete()
                && release.reproducibleBuildPassed() && release.sbomComplete()
                && release.canaryPlanValidated() && release.rollbackPlanValidated()
                && release.schemaCompatibilityPassed() && release.forwardFixRunbookValidated()
                && (!profile.requireCanaryDrill() || release.canaryDrillPassed())
                && (!profile.requireRollbackDrill() || release.rollbackDrillPassed())
                && release.openCriticalRisks() == 0 && release.unapprovedRisks() == 0 && !blockingRisk
                && cost.status() == EvidenceStatus.PASSED && cost.assumptionsVersioned()
                && cost.sourceComparable() && cost.headroomAndDrIncluded() && cost.sloPreserved();
        if (pd && !pe) blockers.add("P-E release safety, cost or risk-acceptance requirements failed");
        else if (pe) gate = Gate.P_E;

        boolean pf = pe
                && perf.requiredScenarioPassRate() >= request.policy().highConfidencePerformancePassRate()
                && sec.criticalScenarioPassRate() == 1.0 && rel.criticalChaosPassRate() == 1.0
                && (!profile.requireSoak() || perf.soakPassed())
                && perf.headroomPercent() >= Math.max(profile.minimumHeadroomPercent(), request.policy().highConfidenceMinimumHeadroom())
                && (!profile.requireBackupRestore() || rel.backupRestorePassed())
                && (!profile.requireDisasterRecovery() || (rel.rpoPassed() && rel.rtoPassed()))
                && obs.criticalSliCoverage() == 1.0 && obs.alertCoverage() == 1.0 && obs.runbookCoverage() == 1.0
                && obs.traceCoverage() >= request.policy().highConfidenceTraceCoverage()
                && (!profile.requireCanaryDrill() || release.canaryDrillPassed())
                && (!profile.requireRollbackDrill() || release.rollbackDrillPassed())
                && request.openRisks().stream().noneMatch(risk -> risk.serviceId().equals(serviceId));
        if (pf) gate = Gate.P_F;

        Metrics metrics = metrics(perf, sec, rel, obs, release);
        List<String> evidence = new ArrayList<>();
        addRefs(evidence, calibration == null ? null : calibration.evidenceRefs());
        addRefs(evidence, perf == null ? null : perf.evidenceRefs()); addRefs(evidence, sec == null ? null : sec.evidenceRefs());
        addRefs(evidence, rel == null ? null : rel.evidenceRefs()); addRefs(evidence, obs == null ? null : obs.evidenceRefs());
        addRefs(evidence, release == null ? null : release.evidenceRefs()); addRefs(evidence, cost == null ? null : cost.evidenceRefs());
        if (gate.ordinal() >= Gate.P_E.ordinal()) blockers.clear();
        return new ServiceGate(serviceId, gate, gate.ordinal() >= Gate.P_E.ordinal(), false, false,
                blockers, restrictions, metrics, evidence);
    }

    private static Metrics metrics(PerformanceEvidence p, SecurityEvidence s, ReliabilityEvidence r,
                                   ObservabilityEvidence o, ReleaseEvidence release) {
        return new Metrics(p == null ? 0 : p.requiredScenarioPassRate(), s == null ? 0 : s.criticalScenarioPassRate(),
                r == null ? 0 : r.criticalChaosPassRate(), r == null ? 0 : r.recoveryScenarioPassRate(),
                o == null ? 0 : o.criticalSliCoverage(), o == null ? 0 : o.alertCoverage(),
                o == null ? 0 : o.runbookCoverage(), o == null ? 0 : o.traceCoverage(),
                p == null ? 0 : p.headroomPercent(), s == null ? 0 : s.criticalVulnerabilities(),
                s == null ? 0 : s.exploitableHighVulnerabilities(), s == null ? 0 :
                s.authenticationRegressions() + s.authorizationRegressions() + s.tenantIsolationRegressions(),
                r == null ? 0 : r.dataCorruptionEvents(), p == null ? 0 : p.unexplainedLeaks(),
                release == null ? 0 : release.openCriticalRisks());
    }

    private static boolean safe(boolean productionAccess, boolean secretObserved) {
        return !productionAccess && !secretObserved;
    }

    private static void addRefs(List<String> target, List<String> refs) { if (refs != null) target.addAll(refs); }

    private interface AuthorityCall<T> { List<T> call(); }

    private static <T> Map<String, T> callAndIndex(String label, List<String> blockers, AuthorityCall<T> call,
                                                   Set<String> expectedServices, Function<T, String> serviceId,
                                                   Function<T, String> artifactId, Function<T, List<String>> refs,
                                                   String expectedArtifact) {
        final List<T> values;
        try {
            values = Optional.ofNullable(call.call()).orElse(List.of());
        } catch (RuntimeException exception) {
            blockers.add(label + " authority failed safely: " + exception.getClass().getSimpleName());
            return Map.of();
        }
        Map<String, T> indexed = new LinkedHashMap<>();
        for (T value : values) {
            if (value == null) { blockers.add(label + " returned null evidence"); continue; }
            String service = serviceId.apply(value);
            if (!expectedServices.contains(service)) { blockers.add(label + " evidence references unknown service: " + service); continue; }
            if (!expectedArtifact.equals(artifactId.apply(value))) { blockers.add(label + " evidence artifact mismatch: " + service); continue; }
            if (refs.apply(value) == null || refs.apply(value).isEmpty()) { blockers.add(label + " evidence has no evidence refs: " + service); continue; }
            if (indexed.putIfAbsent(service, value) != null) blockers.add(label + " returned duplicate evidence: " + service);
        }
        return Map.copyOf(indexed);
    }

    private static <T> Map<String, T> uniqueBy(List<T> values, Function<T, String> key, String label) {
        Map<String, T> result = new LinkedHashMap<>();
        for (T value : values) if (result.putIfAbsent(key.apply(value), value) != null)
            throw new IllegalArgumentException("duplicate " + label + ": " + key.apply(value));
        return result;
    }
}
