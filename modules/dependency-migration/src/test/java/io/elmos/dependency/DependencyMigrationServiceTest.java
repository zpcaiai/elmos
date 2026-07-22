package io.elmos.dependency;

import io.elmos.intake.IntakeModels;
import io.elmos.lowering.LoweringModels;
import io.elmos.skeleton.SkeletonModels;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static io.elmos.dependency.DependencyMigrationModels.*;
import static org.junit.jupiter.api.Assertions.*;

class DependencyMigrationServiceTest {
    @TempDir Path workspace;

    @Test void selectsOnlyExplicitSemanticallyCompleteAndRiskApprovedCandidate() {
        Request request = request(true, true, approvedMapping(), List.of("target.client"));
        RunResult result = passingService().migrate(request);

        assertEquals(Strategy.ECOSYSTEM_PACKAGE, result.decisions().getFirst().strategy());
        assertEquals(1.0, result.decisions().getFirst().score().apiCoverage());
        assertTrue(result.buildValidations().getFirst().lockfileRegenerated());
        assertTrue(result.conformance().eligibleForBatch7());
        assertEquals(List.of("D-A", "D-B", "D-C", "D-D"), result.conformance().modules().stream().map(ModuleGate::gate).toList());
    }

    @Test void removesDependencyOnlyWhenCompleteAnalyzerProvesNoUse() {
        Request request = request(true, false, null, List.of());
        RunResult result = passingService().migrate(request);

        assertEquals(Strategy.REMOVE, result.decisions().getFirst().strategy());
        assertEquals("legacy.client", result.patches().getFirst().operations().getFirst().coordinate());
        assertEquals("remove", result.patches().getFirst().operations().getFirst().operation());
    }

    @Test void incompleteUsageEvidenceNeverClassifiesDependencyAsUnused() {
        Request request = request(false, false, null, List.of());
        RunResult result = passingService().migrate(request);

        assertEquals(Strategy.MANUAL_REVIEW, result.decisions().getFirst().strategy());
        assertFalse(result.decisions().getFirst().automatic());
        assertTrue(result.decisions().getFirst().obligations().stream().anyMatch(value -> value.contains("incomplete")));
        assertFalse(result.conformance().eligibleForBatch7());
    }

    @Test void unknownSupplyChainEvidenceBlocksEvenHighCompatibilityScore() {
        Request request = request(true, true, approvedMapping(), List.of("target.client"));
        DependencyMigrationService service = new DependencyMigrationService(completeGraph(),
                (candidate, profile, at) -> new SupplyChainAssessment(candidate.candidateId(), Status.INCONCLUSIVE,
                        "unknown", null, "unknown", null, "unknown", "unknown", "supported", at,
                        List.of("license and vulnerability evidence missing")), passingBuild(), passingContracts());
        RunResult result = service.migrate(request);

        assertEquals(Strategy.PROHIBITED, result.decisions().getFirst().strategy());
        assertFalse(result.decisions().getFirst().automatic());
        assertTrue(result.conformance().blockingErrors().stream().anyMatch(value -> value.contains("supply-chain") || value.contains("license")));
    }

    @Test void packageNameSimilarityWithoutApprovedMappingCannotSelectCandidate() {
        KnowledgeMapping merelySimilar = new KnowledgeMapping("kb-similar", "maven", "legacy-client", "*", "java",
                "package", "target.client", "3.1.0", Strategy.ECOSYSTEM_PACKAGE,
                Map.of("Client.fetch", "Client.fetch"), Map.of("timeout", "timeout"), 1.0,
                "kb/review/42", NOW, "approved");
        RunResult result = passingService().migrate(request(true, true, merelySimilar, List.of("target.client")));
        assertEquals(Strategy.MANUAL_REVIEW, result.decisions().getFirst().strategy());
    }

    @Test void mappingOutsideResolvedSourceVersionRangeIsRejected() {
        KnowledgeMapping wrongRange = new KnowledgeMapping("kb-wrong-version", "maven", "legacy.client", "[2,3)", "java",
                "package", "target.client", "3.1.0", Strategy.ECOSYSTEM_PACKAGE,
                Map.of("com.legacy.Client", "com.target.Client", "Client.fetch", "Client.fetch"),
                Map.of("timeout", "preserved"), 1.0, "kb/review/99", NOW, "approved");
        RunResult result = passingService().migrate(request(true, true, wrongRange, List.of("target.client")));
        assertEquals(Strategy.MANUAL_REVIEW, result.decisions().getFirst().strategy());
    }

    @Test void danglingResolvedGraphEdgeBlocksGateDA() {
        ResolvedGraphProvider dangling = (project, dependencies) -> new GraphResolution(
                List.of(new ResolvedEdge(dependencies.getFirst().dependencyId(), "dep-missing", "transitive", "lock:9")),
                true, "lock-parser@test", List.of());
        DependencyMigrationService service = new DependencyMigrationService(dangling, passingRisk(), passingBuild(), passingContracts());
        RunResult result = service.migrate(request(true, true, approvedMapping(), List.of("target.client")));
        assertEquals(Status.BLOCKED, result.conformance().modules().stream().filter(gate -> gate.gate().equals("D-A")).findFirst().orElseThrow().status());
        assertTrue(result.graphs().getFirst().issues().stream().anyMatch(value -> value.contains("dangling")));
    }

    @Test void blockedBuildBackendPreventsGateDCAndWriterStaysOutsideTargetRepository() throws Exception {
        BuildPatchBackend blocked = (repository, patch) -> new BuildValidation(patch.patchId(), Status.BLOCKED,
                "offline-resolver", false, false, false, List.of(), List.of("resolution evidence unavailable"));
        DependencyMigrationService service = new DependencyMigrationService(completeGraph(), passingRisk(), blocked, passingContracts());
        RunResult result = service.migrate(request(true, true, approvedMapping(), List.of("target.client")));
        assertEquals(Status.BLOCKED, result.conformance().modules().stream().filter(gate -> gate.gate().equals("D-C")).findFirst().orElseThrow().status());

        Path sentinel = workspace.resolve("target-repository/pom.xml");
        Files.createDirectories(sentinel.getParent()); Files.writeString(sentinel, "owned-by-user");
        Map<String,Path> artifacts = new DependencyArtifactWriter().write(workspace, result);
        assertEquals("owned-by-user", Files.readString(sentinel));
        assertTrue(artifacts.containsKey("reports/batch-6-conformance.json"));
        assertTrue(Files.exists(workspace.resolve("dependencies/used-api-surface.json")));
    }

    @Test void sameEvidenceProducesDeterministicIds() {
        Request request = request(true, true, approvedMapping(), List.of("target.client"));
        RunResult first = passingService().migrate(request), second = passingService().migrate(request);
        assertEquals(first.manifest(), second.manifest());
        assertEquals(first.decisions(), second.decisions());
    }

    private DependencyMigrationService passingService() {
        return new DependencyMigrationService(completeGraph(), passingRisk(), passingBuild(), passingContracts());
    }
    private ResolvedGraphProvider completeGraph() {
        return (project, dependencies) -> new GraphResolution(List.of(), true, "lock-parser@test", List.of());
    }
    private RiskAssessor passingRisk() {
        return (candidate, profile, at) -> new SupplyChainAssessment(candidate.candidateId(), Status.PASSED,
                "Apache-2.0", "license-scan/1", "no-known-vulnerabilities", "osv-snapshot/1",
                "verified-registry", "supported", "supported", at, List.of());
    }
    private BuildPatchBackend passingBuild() {
        return (repository, patch) -> new BuildValidation(patch.patchId(), Status.PASSED,
                "sandboxed-maven@1", true, true, false, List.of("reports/resolution.txt", "target-lock-hash"), List.of());
    }
    private ContractValidator passingContracts() {
        return (decision, profile, usage) -> new ContractValidation(decision.dependencyId(), Status.PASSED,
                1.0, 1.0, "differential-harness@1", List.of("reports/contracts.xml"), List.of());
    }

    private Request request(boolean usageComplete, boolean observedUse, KnowledgeMapping mapping, List<String> approved) {
        IntakeModels.Dependency dependency = new IntakeModels.Dependency("maven", "legacy.client", "1.4.2", "runtime", "pom.xml", true, true);
        IntakeModels.BuildProject project = new IntakeModels.BuildProject("source-app", IntakeModels.Language.JAVA, "maven",
                List.of("src/main/java"), List.of("src/test/java"), List.of(), List.of(), List.of(dependency),
                List.of(), List.of(), Map.of(), List.of(), List.of(), List.of());
        IntakeModels.BuildModel buildModel = new IntakeModels.BuildModel("1", "snapshot-1", List.of(project), List.of(), List.of());
        SkeletonModels.TargetProfile target = new SkeletonModels.TargetProfile("java-21", "java", "fixed", "21",
                "none", "maven", List.of("linux"), "modular-monolith", approved, List.of("forbidden.pkg"),
                Map.of(), true, List.of(), List.of(), List.of());
        LoweringModels.Coverage loweringCoverage = new LoweringModels.Coverage(1,1,0,0,0,1,1,0,0);
        LoweringModels.Fidelity fidelity = new LoweringModels.Fidelity(1,1,1,1,1,1,1);
        LoweringModels.ModuleGate moduleGate = new LoweringModels.ModuleGate("target-app", "L-D", true, true, true, List.of());
        LoweringModels.ConformanceReport lowering = new LoweringModels.ConformanceReport(5,"PASSED","lowering-1",List.of(moduleGate),loweringCoverage,fidelity,List.of(),List.of(),true);
        List<ApiUsageEvidence> usage = observedUse ? List.of(new ApiUsageEvidence("source-app", "maven", "legacy.client",
                List.of("com.legacy.Client"), List.of("Client.fetch"), List.of(), List.of(), List.of("src/App.java:12"),
                Map.of("timeout", "required"))) : List.of();
        UsageEvidenceBundle evidence = new UsageEvidenceBundle(usageComplete, "symbol-resolver@1", usage, usageComplete?List.of():List.of("dynamic import analysis incomplete"));
        return new Request(workspace, buildModel, target, lowering, Map.of("source-app", "target-app"), evidence,
                mapping==null?List.of():List.of(mapping), NOW);
    }

    private KnowledgeMapping approvedMapping() {
        return new KnowledgeMapping("kb-1", "maven", "legacy.client", "[1,2)", "java", "package",
                "target.client", "3.1.0", Strategy.ECOSYSTEM_PACKAGE,
                Map.of("com.legacy.Client", "com.target.Client", "Client.fetch", "Client.fetch"),
                Map.of("timeout", "preserved"), 1.0, "kb/review/1", NOW, "approved");
    }
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");
}
