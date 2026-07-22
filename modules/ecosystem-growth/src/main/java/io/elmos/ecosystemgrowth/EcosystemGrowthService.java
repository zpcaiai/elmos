package io.elmos.ecosystemgrowth;

import java.util.*;
import java.util.function.Supplier;

import static io.elmos.ecosystemgrowth.EcosystemGrowthModels.*;

/** Fail-closed G14-A through G14-G evaluator over externally observed PEGM evidence. */
public final class EcosystemGrowthService {
    private static final List<String> REQUIRED_MOTIONS = List.of(
            "product-led-growth", "content-led-growth", "developer-led-growth",
            "community-led-growth", "marketplace-led-growth",
            "partner-led-regional-expansion");
    private static final Map<AssuranceArea, Set<Control>> REQUIRED_CONTROLS = requiredControls();
    private final EcosystemGrowthAuthorities authorities;

    public EcosystemGrowthService(EcosystemGrowthAuthorities authorities) {
        this.authorities = Objects.requireNonNull(authorities, "authorities");
    }

    public Outcome evaluate(Request request) {
        Objects.requireNonNull(request, "request");
        admit(request);
        List<String> blockers = new ArrayList<>();
        EnumMap<AssuranceArea, GateEvidence> evidence = new EnumMap<>(AssuranceArea.class);

        observeArea(request, AssuranceArea.PRODUCT_ACTIVATION, "G14-A product activation",
                () -> authorities.productActivation().observe(request), evidence, blockers);
        observeArea(request, AssuranceArea.CONTENT_AND_DEVELOPER, "G14-B content and developer",
                () -> authorities.contentDeveloper().observe(request), evidence, blockers);
        observeArea(request, AssuranceArea.COMMUNITY_SAFETY, "G14-C community safety",
                () -> authorities.communitySafety().observe(request), evidence, blockers);
        observeArea(request, AssuranceArea.MARKETPLACE_GROWTH, "G14-D Marketplace growth",
                () -> authorities.marketplaceGrowth().observe(request), evidence, blockers);
        observeArea(request, AssuranceArea.INTERNATIONALIZATION, "G14-E internationalization",
                () -> authorities.internationalization().observe(request), evidence, blockers);
        observeArea(request, AssuranceArea.REGIONAL_CHANNEL, "G14-F regional channel",
                () -> authorities.regionalChannel().observe(request), evidence, blockers);
        GrowthConformanceEvidence acceptance = observe("G14-G growth conformance",
                () -> authorities.growthConformance().observe(request), blockers);

        for (GateEvidence value : evidence.values()) validateEnvelope(request, value, blockers);
        if (acceptance != null) validateEnvelope(request, acceptance, blockers);
        addCriticalBlockers(request, evidence, acceptance, blockers);

        boolean a = passes(request, evidence.get(AssuranceArea.PRODUCT_ACTIVATION));
        boolean b = a && passes(request, evidence.get(AssuranceArea.CONTENT_AND_DEVELOPER));
        boolean c = b && passes(request, evidence.get(AssuranceArea.COMMUNITY_SAFETY));
        boolean d = c && passes(request, evidence.get(AssuranceArea.MARKETPLACE_GROWTH));
        boolean e = d && passes(request, evidence.get(AssuranceArea.INTERNATIONALIZATION));
        boolean f = e && passes(request, evidence.get(AssuranceArea.REGIONAL_CHANNEL));
        boolean g = f && passesAcceptance(request, acceptance);
        Gate gate = g ? Gate.G14_G : f ? Gate.G14_F : e ? Gate.G14_E
                : d ? Gate.G14_D : c ? Gate.G14_C : b ? Gate.G14_B
                : a ? Gate.G14_A : Gate.BLOCKED;
        if (!a) blockers.add("G14-A product activation evidence is not satisfied");
        blockers = blockers.stream().distinct().sorted().toList();

        boolean ready = gate == Gate.G14_G && blockers.isEmpty();
        boolean complete = ready && evidence.size() == AssuranceArea.values().length
                && acceptance != null && acceptance.evidencePackComplete();
        ConformanceReport report = new ConformanceReport(
                14, "growth-ecosystem-v1", request.assessmentRunId(),
                request.platformBusiness().platformBusinessVersion(), gate, status(gate, blockers),
                acceptance == null ? List.of() : acceptance.supportedMotions(),
                acceptance == null ? List.of() : acceptance.openNonBlockingItems(),
                blockers, restrictions(), metrics(request, evidence, acceptance),
                complete, ready, false, request.observedAt(), evidenceRefs(evidence, acceptance));
        return new Outcome(request, evidence, acceptance, report);
    }

    private static void admit(Request request) {
        PlatformBusinessArtifact artifact = request.platformBusiness();
        if (!artifact.immutable() || !artifact.signed() || !artifact.batch13GVerified())
            throw new IllegalArgumentException("Batch 14 requires immutable signed externally verified B13-G evidence");
        NorthStarDefinition northStar = request.northStar();
        if (!northStar.customerValueBound() || !northStar.qualityGateRequired())
            throw new IllegalArgumentException("North Star must represent verified customer migration value");
        EnumSet<GrowthDomain> domains = request.growthDomains().stream()
                .map(DomainProfile::domain).collect(
                        java.util.stream.Collectors.toCollection(() -> EnumSet.noneOf(GrowthDomain.class)));
        if (!domains.equals(EnumSet.allOf(GrowthDomain.class))
                || request.growthDomains().stream().anyMatch(profile ->
                !profile.enabled() || !profile.externalEvidenceRequired()))
            throw new IllegalArgumentException("all seven PEGM growth domains require enabled evidence profiles");
        EnumSet<Flywheel> flywheels = request.flywheels().stream()
                .map(FlywheelProfile::flywheel).collect(
                        java.util.stream.Collectors.toCollection(() -> EnumSet.noneOf(Flywheel.class)));
        if (!flywheels.equals(EnumSet.allOf(Flywheel.class))
                || request.flywheels().stream().anyMatch(profile ->
                !profile.customerValueLinked() || !profile.qualityGuardrailsDefined()
                        || !profile.feedbackLoopDefined()))
            throw new IllegalArgumentException("all five PEGM flywheels require value linkage, guardrails, and feedback loops");
    }

    private static void observeArea(Request request, AssuranceArea expected, String label,
                                    Supplier<GateEvidence> supplier,
                                    Map<AssuranceArea, GateEvidence> evidence,
                                    List<String> blockers) {
        GateEvidence value = observe(label, supplier, blockers);
        if (value == null) return;
        if (value.area() != expected) {
            blockers.add(label + " authority returned evidence for " + value.area());
            return;
        }
        evidence.put(expected, value);
    }

    private static <T> T observe(String label, Supplier<T> supplier, List<String> blockers) {
        try {
            T value = supplier.get();
            if (value == null) blockers.add(label + " external evidence is NOT_RUN");
            return value;
        } catch (RuntimeException error) {
            blockers.add(label + " authority failed safely: " + error.getClass().getSimpleName());
            return null;
        }
    }

    private static void validateEnvelope(Request request, EvidenceEnvelope value, List<String> blockers) {
        if (!request.assessmentRunId().equals(value.assessmentRunId()))
            blockers.add("evidence run mismatch from " + value.authorityId());
        if (!request.platformBusiness().platformBusinessVersion().equals(value.platformBusinessVersion()))
            blockers.add("platform-business version mismatch from " + value.authorityId());
        if (value.observedAt().isAfter(request.observedAt()))
            blockers.add("future-dated evidence from " + value.authorityId());
        if (value.evidenceRefs().isEmpty())
            blockers.add("missing immutable evidence references from " + value.authorityId());
    }

    private static boolean passes(Request request, GateEvidence value) {
        return value != null && value.status() == EvidenceStatus.PASSED
                && value.coverage() >= request.policy().coverageFor(value.area())
                && value.controls().containsAll(REQUIRED_CONTROLS.get(value.area()))
                && value.tenantIsolationPassed() && value.privacyAndConsentPassed()
                && value.guardrailsPassed() && value.failureAndNegativeEvidencePreserved()
                && value.criticalViolations() == 0 && value.crossTenantEvents() == 0
                && value.fabricatedOutcomes() == 0 && value.unauthorizedExternalActions() == 0
                && !value.externalOperationExecuted();
    }

    private static boolean passesAcceptance(Request request, GrowthConformanceEvidence value) {
        return value != null && value.status() == EvidenceStatus.PASSED
                && value.acceptedAreas().equals(EnumSet.allOf(AssuranceArea.class))
                && value.validatedDomains().equals(EnumSet.allOf(GrowthDomain.class))
                && value.validatedFlywheels().equals(EnumSet.allOf(Flywheel.class))
                && value.channelCacVisible() && value.contributionMarginVisible()
                && value.criticalOpenGrowthRisks() == 0 && value.evidencePackComplete()
                && value.evidenceTraceability() >= request.policy().requiredEvidenceTraceability()
                && value.supportedMotions().containsAll(REQUIRED_MOTIONS)
                && !value.externalOperationExecuted();
    }

    private static void addCriticalBlockers(Request request,
                                            Map<AssuranceArea, GateEvidence> evidence,
                                            GrowthConformanceEvidence acceptance,
                                            List<String> blockers) {
        for (AssuranceArea area : AssuranceArea.values()) {
            GateEvidence value = evidence.get(area);
            if (value == null) continue;
            if (value.status() != EvidenceStatus.PASSED)
                blockers.add(area + " status is " + value.status());
            if (value.coverage() < request.policy().coverageFor(area))
                blockers.add(area + " coverage is below policy");
            if (!value.controls().containsAll(REQUIRED_CONTROLS.get(area)))
                blockers.add(area + " required controls are missing");
            if (!value.tenantIsolationPassed() || value.crossTenantEvents() > 0)
                blockers.add(area + " tenant boundary failed");
            if (!value.privacyAndConsentPassed())
                blockers.add(area + " privacy or consent failed");
            if (!value.guardrailsPassed())
                blockers.add(area + " guardrails failed");
            if (!value.failureAndNegativeEvidencePreserved())
                blockers.add(area + " negative evidence was not preserved");
            if (value.criticalViolations() > 0)
                blockers.add(area + " has critical control violations");
            if (value.fabricatedOutcomes() > 0)
                blockers.add(area + " fabricated an outcome");
            if (value.unauthorizedExternalActions() > 0 || value.externalOperationExecuted())
                blockers.add(area + " attempted an unauthorized external operation");
        }
        if (acceptance == null) {
            blockers.add("G14-G conformance evidence is NOT_RUN");
            return;
        }
        if (acceptance.criticalOpenGrowthRisks() > 0)
            blockers.add("critical open growth risks must be zero");
        if (!acceptance.channelCacVisible() || !acceptance.contributionMarginVisible())
            blockers.add("channel CAC and growth contribution margin must be visible");
        if (!acceptance.evidencePackComplete())
            blockers.add("growth evidence pack is incomplete");
        if (!acceptance.supportedMotions().containsAll(REQUIRED_MOTIONS))
            blockers.add("supported growth motions are incomplete");
        if (acceptance.externalOperationExecuted())
            blockers.add("G14-G authority attempted an external operation");
    }

    private static Map<String, Double> metrics(Request request,
                                                Map<AssuranceArea, GateEvidence> evidence,
                                                GrowthConformanceEvidence acceptance) {
        Map<String, Double> metrics = new LinkedHashMap<>();
        for (AssuranceArea area : AssuranceArea.values()) {
            GateEvidence value = evidence.get(area);
            metrics.put(area.name().toLowerCase(Locale.ROOT) + "_coverage",
                    value == null ? 0.0 : value.coverage());
        }
        metrics.put("evidence_traceability",
                acceptance == null ? 0.0 : acceptance.evidenceTraceability());
        metrics.put("channel_cac_visibility",
                acceptance != null && acceptance.channelCacVisible() ? 1.0 : 0.0);
        metrics.put("growth_contribution_margin_visibility",
                acceptance != null && acceptance.contributionMarginVisible() ? 1.0 : 0.0);
        return Map.copyOf(metrics);
    }

    private static List<String> evidenceRefs(Map<AssuranceArea, GateEvidence> evidence,
                                             GrowthConformanceEvidence acceptance) {
        List<String> refs = new ArrayList<>();
        evidence.values().forEach(value -> refs.addAll(value.evidenceRefs()));
        if (acceptance != null) refs.addAll(acceptance.evidenceRefs());
        return refs.stream().distinct().sorted().toList();
    }

    private static List<String> restrictions() {
        return List.of(
                "Field growth, community, Marketplace, localization, legal, tax, partner and regional outcomes remain external",
                "Repository tests and generated artifacts do not establish operational acceptance",
                "Every control-plane artifact records external_operation_executed=false");
    }

    private static RunStatus status(Gate gate, List<String> blockers) {
        if (!blockers.isEmpty() && gate == Gate.BLOCKED) return RunStatus.BLOCKED;
        return switch (gate) {
            case BLOCKED -> RunStatus.INITIALIZED;
            case G14_A -> RunStatus.PRODUCT_ACTIVATION_CONTROLLED;
            case G14_B -> RunStatus.CONTENT_DEVELOPER_CONTROLLED;
            case G14_C -> RunStatus.COMMUNITY_CONTROLLED;
            case G14_D -> RunStatus.MARKETPLACE_CONTROLLED;
            case G14_E -> RunStatus.INTERNATIONALIZATION_CONTROLLED;
            case G14_F -> RunStatus.REGIONAL_CHANNEL_CONTROLLED;
            case G14_G -> blockers.isEmpty() ? RunStatus.SCALABLE_GROWTH_READY : RunStatus.BLOCKED;
        };
    }

    static Set<Control> requiredFor(AssuranceArea area) {
        return REQUIRED_CONTROLS.get(area);
    }

    private static Map<AssuranceArea, Set<Control>> requiredControls() {
        EnumMap<AssuranceArea, Set<Control>> result = new EnumMap<>(AssuranceArea.class);
        result.put(AssuranceArea.PRODUCT_ACTIVATION, EnumSet.of(
                Control.SELF_SERVICE_SIGNUP, Control.REPOSITORY_CONNECTION,
                Control.ASSESSMENT_ACTIVATION, Control.TIME_TO_VALUE_MEASURABLE,
                Control.TRIAL_COST_CONTROL, Control.SECURITY_GUARDRAILS));
        result.put(AssuranceArea.CONTENT_AND_DEVELOPER, EnumSet.of(
                Control.TECHNICAL_CONTENT_REVIEW_COMPLETE, Control.DOCS_CORE_JOURNEYS_COMPLETE,
                Control.SDK_CORE_JOURNEYS_TESTED, Control.SAMPLE_REPOSITORIES_BUILDING,
                Control.DEVELOPER_PORTAL_AVAILABLE));
        result.put(AssuranceArea.COMMUNITY_SAFETY, EnumSet.of(
                Control.COMMUNITY_IDENTITY_ISOLATED, Control.MODERATION_SLA_PASSED,
                Control.MALICIOUS_CONTENT_CONTROLLED, Control.VERIFIED_KNOWLEDGE_WORKFLOW,
                Control.PRIVATE_CUSTOMER_LEAKAGE_ZERO));
        result.put(AssuranceArea.MARKETPLACE_GROWTH, EnumSet.of(
                Control.PUBLISHER_VERIFIED, Control.EXECUTABLE_ASSET_SECURITY_GATE,
                Control.MARKETPLACE_LICENSE_GATE, Control.INSTALL_ROLLBACK_PASSED,
                Control.FAKE_REVIEW_CONTROLLED, Control.CRITICAL_ASSET_INCIDENTS_ZERO));
        result.put(AssuranceArea.INTERNATIONALIZATION, EnumSet.of(
                Control.I18N_ARCHITECTURE_PASSED, Control.CRITICAL_UI_LOCALIZED,
                Control.SECURITY_BILLING_HUMAN_REVIEWED, Control.REGIONAL_FORMAT_TESTED,
                Control.REGIONAL_COMPLIANCE_PASSED));
        result.put(AssuranceArea.REGIONAL_CHANNEL, EnumSet.of(
                Control.REGIONAL_ENTRY_ASSESSMENT_COMPLETE, Control.LAUNCH_PLAYBOOK_APPROVED,
                Control.LOCAL_SUPPORT_READY, Control.REGIONAL_PARTNER_QUALITY_GATES,
                Control.REGIONAL_METRICS_AVAILABLE));
        return Map.copyOf(result);
    }
}
