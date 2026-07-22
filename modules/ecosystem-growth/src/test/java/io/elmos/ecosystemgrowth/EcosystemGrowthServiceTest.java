package io.elmos.ecosystemgrowth;

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

import static io.elmos.ecosystemgrowth.EcosystemGrowthModels.*;
import static org.junit.jupiter.api.Assertions.*;

class EcosystemGrowthServiceTest {
    private static final Instant NOW = Instant.parse("2026-07-21T05:00:00Z");
    private static final String RUN = "growth-run-14";
    private static final String VERSION = "platform-business-v14";
    private static final String DIGEST = "d".repeat(64);
    private static final List<String> MOTIONS = List.of(
            "product-led-growth", "content-led-growth", "developer-led-growth",
            "community-led-growth", "marketplace-led-growth",
            "partner-led-regional-expansion");
    @TempDir Path temp;

    @Test
    void reachesG14GOnlyWithAllExternalEvidenceAndNeverExecutesAnOperation() {
        Outcome outcome = evaluate(request(), Evidence.good());
        assertEquals(Gate.G14_G, outcome.report().gate());
        assertEquals(RunStatus.SCALABLE_GROWTH_READY, outcome.report().status());
        assertEquals("growth-ecosystem-v1", outcome.report().growthPlatformVersion());
        assertTrue(outcome.report().externalEvidenceComplete());
        assertTrue(outcome.report().scalableGrowthReady());
        assertFalse(outcome.report().externalOperationExecuted());
        assertTrue(outcome.report().blockers().isEmpty());
        assertEquals(6, outcome.gateEvidence().size());
        assertEquals(MOTIONS, outcome.report().supportedMotions());
    }

    @Test
    void admissionRequiresB13ValueNorthStarSevenDomainsAndFiveFlywheels() {
        Request base = request();
        PlatformBusinessArtifact unsigned = new PlatformBusinessArtifact(
                VERSION, DIGEST, true, false, true,
                "commercial://b13-g", List.of("platform-evidence"));
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(
                base, unsigned, base.northStar(), base.growthDomains(), base.flywheels()),
                Evidence.good()));

        NorthStarDefinition vanity = new NorthStarDefinition(
                "monthly-verified-migration-value", "count", "workspace-month",
                "registrations", null, List.of("bots"), "growth-product",
                List.of("signups"), List.of("security-incidents"),
                false, true, "1.0");
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(
                base, base.platformBusiness(), vanity,
                base.growthDomains(), base.flywheels()), Evidence.good()));

        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(
                base, base.platformBusiness(), base.northStar(),
                base.growthDomains().subList(1, base.growthDomains().size()),
                base.flywheels()), Evidence.good()));
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(
                base, base.platformBusiness(), base.northStar(), base.growthDomains(),
                base.flywheels().subList(1, base.flywheels().size())), Evidence.good()));
    }

    @Test
    void everyG14AreaIsNonCompensatingAndNeedsItsExactControls() {
        List<AssuranceArea> order = List.of(AssuranceArea.values());
        for (int index = 0; index < order.size(); index++) {
            AssuranceArea area = order.get(index);
            Set<Control> controls = EnumSet.copyOf(EcosystemGrowthService.requiredFor(area));
            controls.remove(controls.iterator().next());
            Evidence changed = Evidence.good().withArea(area, gateEvidence(
                    area, controls, true, true, true, true,
                    0, 0, 0, 0, false, EvidenceStatus.PASSED, RUN, VERSION));
            Outcome outcome = evaluate(request(), changed);
            assertEquals(Gate.values()[index], outcome.report().gate(), area.name());
            assertFalse(outcome.report().scalableGrowthReady());
            assertTrue(outcome.report().blockers().stream()
                    .anyMatch(value -> value.contains("required controls are missing")));
        }
    }

    @Test
    void tenantPrivacyGuardrailTruthAndExternalActionFailuresAreBlocking() {
        assertAreaBlocked(AssuranceArea.PRODUCT_ACTIVATION,
                false, true, true, true, 0, 0, 0, 0, false, "tenant boundary");
        assertAreaBlocked(AssuranceArea.CONTENT_AND_DEVELOPER,
                true, false, true, true, 0, 0, 0, 0, false, "privacy or consent");
        assertAreaBlocked(AssuranceArea.COMMUNITY_SAFETY,
                true, true, false, true, 0, 0, 0, 0, false, "guardrails failed");
        assertAreaBlocked(AssuranceArea.MARKETPLACE_GROWTH,
                true, true, true, false, 0, 0, 1, 0, false, "fabricated an outcome");
        assertAreaBlocked(AssuranceArea.INTERNATIONALIZATION,
                true, true, true, true, 1, 0, 0, 0, false,
                "critical control violations");
        assertAreaBlocked(AssuranceArea.REGIONAL_CHANNEL,
                true, true, true, true, 0, 1, 0, 0, true, "tenant boundary");
    }

    @Test
    void missingFailedMismatchedAndWrongAreaAuthorityEvidenceFailsClosed() {
        Evidence good = Evidence.good();
        Outcome missing = evaluate(request(), good.withArea(AssuranceArea.COMMUNITY_SAFETY, null));
        assertEquals(Gate.G14_B, missing.report().gate());
        assertTrue(missing.report().blockers().stream()
                .anyMatch(value -> value.contains("G14-C community safety external evidence is NOT_RUN")));

        GateEvidence failed = gateEvidence(AssuranceArea.CONTENT_AND_DEVELOPER,
                controls(AssuranceArea.CONTENT_AND_DEVELOPER), true, true, true, true,
                0, 0, 0, 0, false, EvidenceStatus.INCONCLUSIVE, RUN, VERSION);
        assertTrue(evaluate(request(), good.withArea(AssuranceArea.CONTENT_AND_DEVELOPER, failed))
                .report().blockers().stream().anyMatch(value -> value.contains("INCONCLUSIVE")));

        GateEvidence mismatch = gateEvidence(AssuranceArea.PRODUCT_ACTIVATION,
                controls(AssuranceArea.PRODUCT_ACTIVATION), true, true, true, true,
                0, 0, 0, 0, false, EvidenceStatus.PASSED, "wrong-run", VERSION);
        assertTrue(evaluate(request(), good.withArea(AssuranceArea.PRODUCT_ACTIVATION, mismatch))
                .report().blockers().stream().anyMatch(value -> value.contains("run mismatch")));

        EcosystemGrowthAuthorities base = authorities(good);
        EcosystemGrowthAuthorities wrong = new EcosystemGrowthAuthorities(
                ignored -> good.areas.get(AssuranceArea.CONTENT_AND_DEVELOPER),
                base.contentDeveloper(), base.communitySafety(), base.marketplaceGrowth(),
                base.internationalization(), base.regionalChannel(), base.growthConformance());
        Outcome wrongArea = new EcosystemGrowthService(wrong).evaluate(request());
        assertTrue(wrongArea.report().blockers().stream()
                .anyMatch(value -> value.contains("authority returned evidence for")));
    }

    @Test
    void authorityExceptionsAreSanitizedAndNeverLeakProviderText() {
        Evidence evidence = Evidence.good();
        EcosystemGrowthAuthorities base = authorities(evidence);
        EcosystemGrowthAuthorities broken = new EcosystemGrowthAuthorities(
                ignored -> { throw new IllegalStateException("secret-provider-token"); },
                base.contentDeveloper(), base.communitySafety(), base.marketplaceGrowth(),
                base.internationalization(), base.regionalChannel(), base.growthConformance());
        Outcome outcome = new EcosystemGrowthService(broken).evaluate(request());
        String blockers = String.join(" ", outcome.report().blockers());
        assertTrue(blockers.contains("IllegalStateException"));
        assertFalse(blockers.contains("secret-provider-token"));
    }

    @Test
    void finalConformanceNeedsEconomicsDomainsFlywheelsMotionsAndZeroRisk() {
        Evidence good = Evidence.good();
        Outcome risky = evaluate(request(), good.withAcceptance(acceptance(
                1, true, true, true, MOTIONS)));
        assertEquals(Gate.G14_F, risky.report().gate());
        assertTrue(risky.report().blockers().stream()
                .anyMatch(value -> value.contains("critical open growth")));

        Outcome noEconomics = evaluate(request(), good.withAcceptance(acceptance(
                0, false, true, true, MOTIONS)));
        assertEquals(Gate.G14_F, noEconomics.report().gate());
        assertTrue(noEconomics.report().blockers().stream()
                .anyMatch(value -> value.contains("contribution margin")));

        Outcome missingMotion = evaluate(request(), good.withAcceptance(acceptance(
                0, true, true, true, MOTIONS.subList(0, 5))));
        assertEquals(Gate.G14_F, missingMotion.report().gate());
        assertTrue(missingMotion.report().blockers().stream()
                .anyMatch(value -> value.contains("supported growth motions")));
    }

    @Test
    void writerCreatesAuthoritativeDirectoryTreeTwelveReportsAndCompressedProfiles()
            throws IOException {
        Path workspace = temp.resolve("growth-evidence");
        Outcome outcome = evaluate(request(workspace), Evidence.good());
        Map<String, Path> files = new EcosystemGrowthArtifactWriter().write(outcome);
        assertEquals(25, files.size());
        Path root = workspace.resolve("growth-platform");
        Set<String> top = Set.of("growth-core", "product-growth", "content",
                "developer-ecosystem", "community", "marketplace", "internationalization",
                "regional-growth", "economics", "governance", "reports");
        try (var values = Files.list(root)) {
            assertEquals(top, values.filter(Files::isDirectory)
                    .map(value -> value.getFileName().toString()).collect(Collectors.toSet()));
        }
        try (var values = Files.list(root.resolve("reports"))) {
            assertEquals(12, values.count());
        }
        JsonNode report = new ObjectMapper().readTree(
                root.resolve("reports/batch-14-conformance-report.json").toFile());
        assertTrue(report.path("conformance").path("scalable_growth_ready").asBoolean());
        assertEquals("G14_G", report.path("conformance").path("gate").asText());
        assertFalse(report.path("conformance").path("external_operation_executed").asBoolean());
        JsonNode pack = new ObjectMapper().readTree(root.resolve(
                "governance/playbooks/batch-14-growth-evidence-pack.json").toFile());
        assertEquals(6, pack.path("gate_evidence").size());
        assertFalse(pack.path("external_operation_executed").asBoolean());
        try (ZstdInputStream input = new ZstdInputStream(Files.newInputStream(root.resolve(
                "growth-core/journeys/growth-domain-profiles.jsonl.zst")))) {
            assertTrue(new String(input.readAllBytes()).contains("ACQUISITION"));
        }
        assertThrows(FileAlreadyExistsException.class,
                () -> new EcosystemGrowthArtifactWriter().write(outcome));
    }

    @Test
    void writerRejectsDirectNestedAndResolvedSymbolicLinkRepositoryTargets()
            throws IOException {
        Path repository = temp.resolve("repository");
        Files.createDirectories(repository);
        assertThrows(IllegalArgumentException.class,
                () -> request(repository.resolve("evidence"), repository));

        Path outside = temp.resolve("outside");
        Files.createDirectories(outside);
        Path link = outside.resolve("repo-link");
        Files.createSymbolicLink(link, repository);
        Request resolved = request(link.resolve("evidence"), repository);
        assertThrows(IllegalArgumentException.class, () ->
                new EcosystemGrowthArtifactWriter().write(evaluate(resolved, Evidence.good())));

        Path real = temp.resolve("real");
        Files.createDirectories(real);
        Path workspaceLink = temp.resolve("workspace-link");
        Files.createSymbolicLink(workspaceLink, real);
        assertThrows(IOException.class, () -> new EcosystemGrowthArtifactWriter().write(
                evaluate(request(workspaceLink), Evidence.good())));
    }

    private void assertAreaBlocked(AssuranceArea area,
                                   boolean tenant, boolean privacy, boolean guardrails,
                                   boolean preserve, int critical, int crossTenant,
                                   int fabricated, int actions, boolean executed,
                                   String fragment) {
        GateEvidence changed = gateEvidence(area, controls(area), tenant, privacy,
                guardrails, preserve, critical, crossTenant, fabricated, actions,
                executed, EvidenceStatus.PASSED, RUN, VERSION);
        Outcome outcome = evaluate(request(), Evidence.good().withArea(area, changed));
        assertFalse(outcome.report().scalableGrowthReady());
        assertTrue(outcome.report().blockers().stream()
                .anyMatch(value -> value.contains(fragment)),
                () -> area + " missing blocker: " + fragment + " in "
                        + outcome.report().blockers());
    }

    private Outcome evaluate(Request request, Evidence evidence) {
        return new EcosystemGrowthService(authorities(evidence)).evaluate(request);
    }

    private static EcosystemGrowthAuthorities authorities(Evidence value) {
        return new EcosystemGrowthAuthorities(
                ignored -> value.areas.get(AssuranceArea.PRODUCT_ACTIVATION),
                ignored -> value.areas.get(AssuranceArea.CONTENT_AND_DEVELOPER),
                ignored -> value.areas.get(AssuranceArea.COMMUNITY_SAFETY),
                ignored -> value.areas.get(AssuranceArea.MARKETPLACE_GROWTH),
                ignored -> value.areas.get(AssuranceArea.INTERNATIONALIZATION),
                ignored -> value.areas.get(AssuranceArea.REGIONAL_CHANNEL),
                ignored -> value.acceptance);
    }

    private Request request() {
        return request(temp.resolve("growth-evidence"));
    }

    private Request request(Path workspace) {
        return request(workspace, temp.resolve("platform-repository"));
    }

    private Request request(Path workspace, Path repository) {
        PlatformBusinessArtifact artifact = new PlatformBusinessArtifact(
                VERSION, DIGEST, true, true, true,
                "commercial://b13-g", List.of("platform-evidence"));
        GrowthProgram program = new GrowthProgram(
                "14.0", List.of("enterprise", "developer"), List.of("CN", "US"),
                List.of("self-service", "sales-assisted", "partner-led"),
                List.of("acquisition", "activation", "expansion"),
                "monthly-verified-migration-value", "USD", new BigDecimal("100000"));
        NorthStarDefinition northStar = new NorthStarDefinition(
                "monthly-verified-migration-value",
                "Verified migration work units completed in the month",
                "workspace-month", "verified migration work units", null,
                List.of("duplicate-runs", "demo-workspaces", "failed-validation"),
                "growth-product", List.of("assessment-completion", "first-green-build"),
                List.of("security-incidents", "support-tickets", "gross-margin"),
                true, true, "1.0");
        List<DomainProfile> domains = Arrays.stream(GrowthDomain.values()).map(domain ->
                new DomainProfile(domain,
                        "owner-" + domain.name().toLowerCase(Locale.ROOT),
                        "external-sor-" + domain.name().toLowerCase(Locale.ROOT),
                        true, true, List.of("profile-evidence-" + domain))).toList();
        List<FlywheelProfile> flywheels = Arrays.stream(Flywheel.values()).map(flywheel ->
                new FlywheelProfile(flywheel, true, true, true,
                        List.of("flywheel-evidence-" + flywheel))).toList();
        return new Request(workspace, repository, RUN, artifact, program, northStar,
                domains, flywheels, new Policy(1, 1, 1, 1, 1, 1, 1), NOW);
    }

    private static Request copy(Request base, PlatformBusinessArtifact artifact,
                                NorthStarDefinition northStar,
                                List<DomainProfile> growthDomains,
                                List<FlywheelProfile> flywheels) {
        GrowthProgram program = base.growthProgram();
        if (!program.northStarMetricId().equals(northStar.metricId())) {
            program = new GrowthProgram(program.productVersion(), program.targetSegments(),
                    program.targetRegions(), program.productMotions(), program.primaryGoals(),
                    northStar.metricId(), program.budgetCurrency(), program.budgetAmount());
        }
        return new Request(base.artifactWorkspace(), base.platformRepositoryPath(),
                base.assessmentRunId(), artifact, program, northStar,
                growthDomains, flywheels, base.policy(), base.observedAt());
    }

    private static Set<Control> controls(AssuranceArea area) {
        return EnumSet.copyOf(EcosystemGrowthService.requiredFor(area));
    }

    private static GateEvidence gateEvidence(AssuranceArea area, Set<Control> controls,
                                             boolean tenant, boolean privacy,
                                             boolean guardrails, boolean preserve,
                                             int critical, int crossTenant,
                                             int fabricated, int actions, boolean executed,
                                             EvidenceStatus status, String run,
                                             String version) {
        return new GateEvidence(run, version, area, status, 1, controls,
                tenant, privacy, guardrails, preserve, critical, crossTenant,
                fabricated, actions, executed,
                Map.of("verified_value_rate", 1.0),
                area.name().toLowerCase(Locale.ROOT) + "-authority",
                NOW, List.of("evidence-" + area));
    }

    private static GrowthConformanceEvidence acceptance(
            int risks, boolean economics, boolean allAreas,
            boolean complete, List<String> motions) {
        Set<AssuranceArea> areas = allAreas ? EnumSet.allOf(AssuranceArea.class)
                : EnumSet.of(AssuranceArea.PRODUCT_ACTIVATION);
        return new GrowthConformanceEvidence(
                RUN, VERSION, EvidenceStatus.PASSED, areas,
                EnumSet.allOf(GrowthDomain.class), EnumSet.allOf(Flywheel.class),
                economics, economics, risks, complete, 1,
                motions, List.of(), false, "growth-conformance-authority",
                NOW, List.of("acceptance-evidence"));
    }

    private record Evidence(EnumMap<AssuranceArea, GateEvidence> areas,
                            GrowthConformanceEvidence acceptance) {
        static Evidence good() {
            EnumMap<AssuranceArea, GateEvidence> areas =
                    new EnumMap<>(AssuranceArea.class);
            for (AssuranceArea area : AssuranceArea.values()) {
                areas.put(area, gateEvidence(area, controls(area),
                        true, true, true, true, 0, 0, 0, 0,
                        false, EvidenceStatus.PASSED, RUN, VERSION));
            }
            return new Evidence(areas,
                    EcosystemGrowthServiceTest.acceptance(0, true, true, true, MOTIONS));
        }

        Evidence withArea(AssuranceArea area, GateEvidence value) {
            EnumMap<AssuranceArea, GateEvidence> changed = new EnumMap<>(areas);
            if (value == null) changed.remove(area);
            else changed.put(area, value);
            return new Evidence(changed, acceptance);
        }

        Evidence withAcceptance(GrowthConformanceEvidence value) {
            return new Evidence(areas, value);
        }
    }
}
