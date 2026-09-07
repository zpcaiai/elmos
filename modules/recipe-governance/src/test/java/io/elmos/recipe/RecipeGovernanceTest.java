package io.elmos.recipe;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.recipe.RecipeModels.*;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class RecipeGovernanceTest {
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");
    private static final String SHA_A = "sha256:" + "a".repeat(64);
    private static final String SHA_B = "sha256:" + "b".repeat(64);
    private static final String RAW_C = "c".repeat(64);

    @Test
    void commercialExecutionAllowsPermissiveArtifactAndBlocksNestedMsalArtifact() {
        Descriptor apache = descriptor("org.example.Apache", LicenseType.APACHE_2_0, Set.of("java-17"), List.of(), List.of());
        Descriptor msalChild = descriptor("org.example.Msal", LicenseType.MODERNE_SOURCE_AVAILABLE, Set.of("spring-boot"), List.of(), List.of());
        Descriptor composite = descriptor("org.example.Composite", LicenseType.APACHE_2_0, Set.of("spring-boot"),
                List.of("org.example.Msal"), List.of());
        Catalog catalog = catalog(apache, msalChild, composite);
        RecipeLicensePolicy policy = new RecipeLicensePolicy(catalog, List.of());

        LicenseDecision allowed = policy.evaluate(apache.recipeName(), ExecutionContext.ELMOS_COMMERCIAL_SAAS, "license-v1", NOW);
        LicenseDecision blocked = policy.evaluate(composite.recipeName(), ExecutionContext.ELMOS_COMMERCIAL_SAAS, "license-v1", NOW);

        assertTrue(allowed.permitsExecution());
        assertEquals(LicenseOutcome.BLOCKED, blocked.decision());
        assertEquals("RECIPE_CHILD_LICENSE_BLOCKED:org.example.Msal", blocked.reasonCode());
        assertTrue(blocked.evidenceRefs().stream().anyMatch(ref -> ref.contains("org.example.Msal")));
    }

    @Test
    void commercialExecutionBlocksUnknownTransitiveDependencyUnlessAValidScopedGrantExists() {
        Artifact unknown = artifact("unknown-lib", LicenseType.UNKNOWN, List.of());
        Descriptor root = descriptor("org.example.Root", LicenseType.APACHE_2_0, Set.of("upgrade"), List.of(), List.of(unknown));
        RecipeLicensePolicy blockedPolicy = new RecipeLicensePolicy(catalog(root), List.of());
        assertEquals("RECIPE_ARTIFACT_DEPENDENCY_LICENSE_BLOCKED",
                blockedPolicy.evaluate(root.recipeName(), ExecutionContext.ELMOS_COMMERCIAL_SAAS, "v1", NOW).reasonCode());

        Descriptor msal = descriptor("org.example.Msal", LicenseType.MODERNE_SOURCE_AVAILABLE, Set.of("upgrade"), List.of(), List.of());
        CommercialGrant valid = new CommercialGrant("grant-1", Set.of(ExecutionContext.ELMOS_COMMERCIAL_SAAS),
                Set.of(msal.artifact().coordinate()), NOW.minus(1, ChronoUnit.DAYS), NOW.plus(1, ChronoUnit.DAYS), SHA_B, "legal@example.com");
        CommercialGrant expired = new CommercialGrant("grant-old", Set.of(ExecutionContext.ELMOS_COMMERCIAL_SAAS),
                Set.of(msal.artifact().coordinate()), NOW.minus(2, ChronoUnit.DAYS), NOW.minus(1, ChronoUnit.DAYS), SHA_B, "legal@example.com");
        assertTrue(new RecipeLicensePolicy(catalog(msal), List.of(valid))
                .evaluate(msal.recipeName(), ExecutionContext.ELMOS_COMMERCIAL_SAAS, "v1", NOW).permitsExecution());
        assertFalse(new RecipeLicensePolicy(catalog(msal), List.of(expired))
                .evaluate(msal.recipeName(), ExecutionContext.ELMOS_COMMERCIAL_SAAS, "v1", NOW).permitsExecution());
    }

    @Test
    void selectionAndManifestAreDeterministicAndRejectDynamicVersions() {
        Descriptor recipe = descriptor("org.example.Upgrade", LicenseType.APACHE_2_0, Set.of("spring-boot", "java-17"), List.of(), List.of());
        RecipeGovernanceService service = new RecipeGovernanceService(catalog(recipe), List.of(), new ObjectMapper());
        SelectionRequest request = new SelectionRequest("step-1", Set.of("spring-boot"), "2.7", "3.5",
                ExecutionContext.ELMOS_COMMERCIAL_SAAS, "license-v1", NOW);
        Selection first = service.select(request);
        Selection second = service.select(request);
        assertEquals(first, second);
        assertEquals(SelectionStatus.SELECTED, first.status());

        RuntimeConfiguration runtime = new RuntimeConfiguration("21.0.8", "3.9.11", SHA_A, "network-deny-v1", 2048, 2);
        ExecutionManifest manifestA = service.buildManifest(first, "snapshot-1", "deadbeef", "target-1", "compat-1",
                "8.87.0", "6.20.0", Map.of(), runtime, 3, 900, SHA_B, NOW);
        ExecutionManifest manifestB = service.buildManifest(first, "snapshot-1", "deadbeef", "target-1", "compat-1",
                "8.87.0", "6.20.0", Map.of(), runtime, 3, 900, SHA_B, NOW);
        assertEquals(manifestA.manifestHash(), manifestB.manifestHash());
        assertEquals(List.of("mvn", "-B", "--no-transfer-progress",
                "org.openrewrite.maven:rewrite-maven-plugin:6.20.0:run",
                "-Drewrite.activeRecipes=org.example.Upgrade",
                "-Drewrite.recipeArtifactCoordinates=org.example:upgrade:1.2.3",
                "-Drewrite.exportDatatables=true", "-Drewrite.activeStyles="), service.mavenInvocation(manifestA));
        assertThrows(IllegalArgumentException.class, () -> service.buildManifest(first, "snapshot-1", "deadbeef", "target-1", "compat-1",
                "LATEST", "6.20.0", Map.of(), runtime, 3, 900, SHA_B, NOW));
    }

    @Test
    void freshProcessIdempotenceAndOscillationAreEvidenceBased() {
        RecipeOutcomeEvaluator evaluator = new RecipeOutcomeEvaluator();
        assertEquals(IdempotenceStatus.IDEMPOTENT,
                evaluator.evaluateIdempotence(List.of("tree-a", "tree-b"), false, 0, 3).status());
        assertEquals(IdempotenceStatus.NON_IDEMPOTENT,
                evaluator.evaluateIdempotence(List.of("tree-a", "tree-b"), true, 2, 3).status());
        assertEquals(IdempotenceStatus.OSCILLATING,
                evaluator.evaluateIdempotence(List.of("tree-a", "tree-b", "tree-a"), true, 1, 3).status());
        assertEquals(IdempotenceStatus.INCONCLUSIVE,
                evaluator.evaluateIdempotence(List.of(), false, 0, 3).status());
    }

    @Test
    void successfulRecipeRunRequiresDataTablesAndFreshProcessIdempotenceEvidence() {
        Descriptor recipe = descriptor("org.example.Upgrade", LicenseType.APACHE_2_0, Set.of("spring-boot"), List.of(), List.of());
        RecipeGovernanceService service = new RecipeGovernanceService(catalog(recipe), List.of(), new ObjectMapper());
        Selection selection = service.select(new SelectionRequest("step-1", Set.of("spring-boot"), "2.7", "3.5",
                ExecutionContext.ELMOS_COMMERCIAL_SAAS, "license-v1", NOW));
        ExecutionManifest manifest = service.buildManifest(selection, "snapshot-1", "deadbeef", "target-1", "compat-1",
                "8.87.0", "6.20.0", Map.of(), new RuntimeConfiguration("21", "3.9.11", SHA_A, "deny-v1", 1024, 1),
                3, 900, SHA_B, NOW);
        FileResult change = new FileResult("src/A.java", "src/A.java", "parent", "recipe", 1, 2,
                "core", "upgrade", Risk.LOW, false, false);
        Set<String> requiredTables = Set.of("org.openrewrite.table.SourcesFileResults",
                "org.openrewrite.table.SourcesFileErrors", "org.openrewrite.table.RecipeRunStats");
        RecipeOutcomeEvaluator evaluator = new RecipeOutcomeEvaluator();

        RecipeRun missingIdempotence = evaluator.evaluate(manifest, new RunEvidence(manifest.manifestHash(), 1,
                List.of(change), List.of(), List.of(), requiredTables, List.of(), false,
                false, false, false, Map.of()));
        assertEquals(RunStatus.POLICY_BLOCKED, missingIdempotence.status());
        assertTrue(missingIdempotence.findings().contains("RECIPE_INCONCLUSIVE"));

        RecipeRun missingTables = evaluator.evaluate(manifest, new RunEvidence(manifest.manifestHash(), 1,
                List.of(change), List.of(), List.of(), Set.of(), List.of("before", "after"), false,
                false, false, false, Map.of()));
        assertEquals(RunStatus.POLICY_BLOCKED, missingTables.status());
        assertTrue(missingTables.findings().contains("OPENREWRITE_DATA_TABLE_MISSING"));
    }

    @Test
    void patchSegmentationSeparatesFormattingAndRequiresReviewForSecurityAndScopeViolations() {
        List<FileResult> files = List.of(
                new FileResult("src/A.java", "src/A.java", "parent", "recipe-a", 1, 4, "core", "format import", Risk.LOW, false, false),
                new FileResult("src/B.java", "src/B.java", "parent", "recipe-b", 1, 12, "core", "security_configuration", Risk.HIGH, false, false),
                new FileResult("pom.xml", "pom.xml", "parent", "recipe-b", 1, 2, "root", "dependency", Risk.MEDIUM, false, false));
        List<PatchSegment> segments = new PatchGovernance().segment("step-1", "artifact://patches", files,
                new PatchPolicy(10, 100, Set.of("src/"), Set.of()));

        assertEquals(3, segments.size());
        assertTrue(segments.stream().anyMatch(segment -> segment.primaryIntent().equals("FORMATTING_ONLY") && !segment.manualReviewRequired()));
        assertTrue(segments.stream().anyMatch(segment -> segment.primaryIntent().equals("SECURITY_CONFIGURATION") && segment.manualReviewRequired()));
        assertTrue(segments.stream().anyMatch(segment -> segment.findings().contains("PATCH_OUTSIDE_STEP_SCOPE")));
    }

    @Test
    void promotionCannotAdvanceWithoutIndependentEvidenceAndHumanReview() {
        RecipeOutcomeEvaluator evaluator = new RecipeOutcomeEvaluator();
        PromotionDecision blocked = evaluator.promotion(new RegressionEvidence(true, true, true, true,
                IdempotenceStatus.IDEMPOTENT, true, true, true, true, false, 0, true));
        assertFalse(blocked.productionEligible());
        assertEquals(PromotionStatus.BLOCKED, blocked.promotionStatus());
        assertTrue(blocked.blockingReasons().containsAll(Set.of("SBOM_MISSING", "HUMAN_REVIEW_MISSING")));
        PromotionDecision approved = evaluator.promotion(new RegressionEvidence(true, true, true, true,
                IdempotenceStatus.IDEMPOTENT, true, true, true, true, true, 1, true));
        assertTrue(approved.productionEligible());
        assertEquals(PromotionStatus.APPROVED, approved.promotionStatus());
    }

    private static Catalog catalog(Descriptor... descriptors) {
        return new Catalog("catalog-v1", java.util.Arrays.stream(descriptors)
                .collect(java.util.stream.Collectors.toMap(Descriptor::recipeName, value -> value)));
    }

    private static Descriptor descriptor(String name, LicenseType license, Set<String> capabilities,
                                         List<String> children, List<Artifact> dependencies) {
        String artifactId = name.substring(name.lastIndexOf('.') + 1).toLowerCase();
        return new Descriptor(name, name, artifact(artifactId, license, dependencies), capabilities,
                Set.of("2.7"), Set.of("3.5"), Map.of(), children, PromotionStatus.APPROVED,
                new QualityProfile(1.0, true, true, 100, true, 100, 100), true, Set.of());
    }

    private static Artifact artifact(String artifactId, LicenseType license, List<Artifact> dependencies) {
        return new Artifact("org.example", artifactId, "1.2.3", "https://repo1.maven.org/maven2", SHA_A, SHA_B,
                license, true, "sbom://" + artifactId, dependencies);
    }
}
