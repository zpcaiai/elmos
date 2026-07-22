package io.elmos.frameworkmigration;

import io.elmos.dependency.DependencyMigrationModels;
import io.elmos.semantic.PspModels;
import io.elmos.skeleton.SkeletonModels;
import io.elmos.uir.UirModels;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;
import java.util.function.UnaryOperator;

import static io.elmos.frameworkmigration.FrameworkMigrationModels.*;
import static org.junit.jupiter.api.Assertions.*;

class FrameworkMigrationServiceTest {
    private static final Instant NOW = Instant.parse("2026-07-21T08:00:00Z");
    @TempDir Path workspace;

    @Test void verifiedAfsmRecipesAndSandboxEvidenceReachGateFD() {
        RunResult result = service(entities(), passingBackend(), passingValidation()).migrate(request(recipes()));

        assertTrue(result.conformance().eligibleForBatch8());
        assertEquals("F-D", result.conformance().modules().getLast().gate());
        assertEquals(Status.PASSED, result.conformance().modules().getLast().status());
        assertEquals(1.0, result.conformance().coverage().securityMappingRate());
        assertEquals(1.0, result.conformance().fidelity().middlewareOrder());
        assertTrue(result.obligations().isEmpty());
    }

    @Test void batch6MustExplicitlyAdmitFrameworkMigration() {
        Request passing = request(recipes());
        DependencyMigrationModels.ConformanceReport blocked = new DependencyMigrationModels.ConformanceReport(
                6, "BLOCKED", "dependency-run-1", passing.dependencyConformance().modules(),
                passing.dependencyConformance().coverage(), List.of("D-D blocked"), List.of(), false);
        Request request = new Request(workspace, passing.uir(), passing.targetProfile(),
                passing.targetFrameworkVersion(), blocked,
                passing.sourceProjectToTargetModule(), passing.frameworkSignals(), passing.recipes(), NOW);

        assertThrows(IllegalArgumentException.class,
                () -> service(entities(), passingBackend(), passingValidation()).migrate(request));
    }

    @Test void protectedEndpointWithoutAuthorizationPolicyFailsClosed() {
        List<AfsmEntity> broken = entities().stream().map(entity -> {
            if (!entity.entityId().equals("afsm:endpoint:orders")) return entity;
            return replace(entity, attributes -> attributes, List.of("afsm:authn:jwt"));
        }).toList();
        RunResult result = service(broken, passingBackend(), passingValidation()).migrate(request(recipes()));

        assertFalse(result.conformance().eligibleForBatch8());
        assertTrue(result.conformance().blockingErrors().stream()
                .anyMatch(value -> value.contains("protected-endpoint-authorization-missing")));
        assertEquals(Status.NOT_RUN, result.validation().bootstrap());
    }

    @Test void authenticationMustPrecedeAuthorizationInBothPipelines() {
        List<AfsmEntity> broken = entities().stream().map(entity -> {
            if (entity.entityId().equals("afsm:middleware:authn")) return replace(entity,
                    attributes -> with(attributes, "order", "200"), entity.relatedEntityIds());
            if (entity.entityId().equals("afsm:middleware:authz")) return replace(entity,
                    attributes -> with(attributes, "order", "100"), entity.relatedEntityIds());
            return entity;
        }).toList();
        RunResult result = service(broken, passingBackend(), passingValidation()).migrate(request(recipes()));

        assertTrue(result.conformance().blockingErrors().stream().anyMatch(value -> value.contains("order-invalid")));
        assertFalse(result.conformance().eligibleForBatch8());
    }

    @Test void secretMaterialAndUnreviewedHighRiskAgentPatchAreBlocking() {
        FrameworkBackend unsafe = emission(entity -> entity.entityId().equals("afsm:authz:orders-read"),
                true, true);
        RunResult result = service(entities(), unsafe, passingValidation()).migrate(request(recipes()));

        assertTrue(result.conformance().blockingErrors().stream()
                .anyMatch(value -> value.contains("secret-material-in-framework-emission")));
        assertTrue(result.conformance().blockingErrors().stream()
                .anyMatch(value -> value.contains("unreviewed-agent-high-risk-framework-patch")));
        assertFalse(result.conformance().eligibleForBatch8());
    }

    @Test void equalPriorityRecipesAndUnapprovedDependenciesNeverAutoSelect() {
        List<Recipe> ambiguous = new ArrayList<>(recipes());
        Recipe endpoint = ambiguous.stream().filter(recipe -> recipe.entityKind().equals("endpoint")).findFirst().orElseThrow();
        ambiguous.add(new Recipe("recipe:endpoint:other", "1", endpoint.sourceFramework(), "*",
                endpoint.targetFramework(), "*", "endpoint", endpoint.specificity(), endpoint.priority(),
                "exact", true, true, List.of("emit-endpoint"), List.of(), List.of(),
                List.of("route-table"), List.of("fixture:endpoint:other"), "review/other"));
        RunResult conflict = service(entities(), passingBackend(), passingValidation()).migrate(request(ambiguous));
        assertTrue(conflict.recipePlans().stream().filter(plan -> plan.entityId().equals("afsm:endpoint:orders"))
                .anyMatch(plan -> !plan.automatic() && plan.diagnostics().stream().anyMatch(value -> value.contains("ambiguous"))));

        List<Recipe> unapproved = recipes().stream().map(recipe -> recipe.entityKind().equals("endpoint")
                ? new Recipe(recipe.recipeId(), recipe.version(), recipe.sourceFramework(), recipe.sourceVersionRange(),
                recipe.targetFramework(), recipe.targetVersionRange(), recipe.entityKind(), recipe.specificity(),
                recipe.priority(), recipe.fidelity(), recipe.idempotent(), recipe.production(), recipe.transformations(),
                List.of("not.approved.framework"), recipe.obligationTemplates(), recipe.validations(), recipe.tests(), recipe.provenanceRef())
                : recipe).toList();
        RunResult dependency = service(entities(), passingBackend(), passingValidation()).migrate(request(unapproved));
        assertTrue(dependency.recipePlans().stream().anyMatch(plan -> plan.diagnostics().stream()
                .anyMatch(value -> value.contains("unapproved-recipe-dependencies"))));
    }

    @Test void startupNotRunCannotBeRenderedAsFrameworkReadiness() {
        FrameworkValidation notRun = FrameworkValidation.blocked("native framework runner unavailable");
        RunResult result = service(entities(), passingBackend(), request -> notRun).migrate(request(recipes()));

        assertFalse(result.conformance().eligibleForBatch8());
        assertTrue(result.conformance().blockingErrors().contains("framework-startup-and-discovery-not-proven"));
    }

    @Test void artifactWriterUsesCompressedAfsmAndRejectsSymlinkParents() throws Exception {
        RunResult result = service(entities(), passingBackend(), passingValidation()).migrate(request(recipes()));
        Map<String,Path> artifacts = new FrameworkArtifactWriter().write(workspace, result);
        assertTrue(Files.size(artifacts.get("framework/entities.jsonl.zst")) > 0);
        assertFalse(Files.exists(workspace.resolve("target-repository/generated-by-writer")));

        Path outside = workspace.resolveSibling(workspace.getFileName() + "-outside");
        Files.createDirectories(outside);
        Path reports = workspace.resolve("reports");
        if (Files.exists(reports)) Files.move(reports, workspace.resolve("reports-owned"));
        Files.createSymbolicLink(reports, outside);
        assertThrows(SecurityException.class, () -> new FrameworkArtifactWriter().write(workspace, result));
        assertEquals(0, Files.list(outside).count());
    }

    @Test void identicalEvidenceProducesIdenticalManifestAndPlans() {
        FrameworkMigrationService service = service(entities(), passingBackend(), passingValidation());
        RunResult first = service.migrate(request(recipes()));
        RunResult second = service.migrate(request(recipes()));
        assertEquals(first.manifest(), second.manifest());
        assertEquals(first.recipePlans(), second.recipePlans());
        assertEquals(first.emissions(), second.emissions());
    }

    @Test void frameworkVersionRangeIsNotConfusedWithLanguageRuntimeVersion() {
        List<Recipe> wrongVersion = recipes().stream().map(recipe -> recipe.entityKind().equals("endpoint")
                ? new Recipe(recipe.recipeId(), recipe.version(), recipe.sourceFramework(), recipe.sourceVersionRange(),
                recipe.targetFramework(), "9.*", recipe.entityKind(), recipe.specificity(), recipe.priority(),
                recipe.fidelity(), recipe.idempotent(), recipe.production(), recipe.transformations(),
                recipe.requiredDependencies(), recipe.obligationTemplates(), recipe.validations(), recipe.tests(), recipe.provenanceRef())
                : recipe).toList();
        RunResult result = service(entities(), passingBackend(), passingValidation()).migrate(request(wrongVersion));
        assertTrue(result.recipePlans().stream().filter(plan -> plan.entityId().equals("afsm:endpoint:orders"))
                .anyMatch(plan -> plan.diagnostics().contains("no-production-recipe")));
    }

    @Test void targetSemanticDriftCreatesBlockingDifferenceAndObligation() {
        FrameworkBackend drift = request -> {
            Emission base = passingBackend().emit(request);
            if (!request.entity().entityId().equals("afsm:tx:create")) return base;
            Map<String,String> semantics = new LinkedHashMap<>(base.targetSemantics());
            semantics.put("propagation", "supports");
            return new Emission(base.emissionId(), base.entityId(), base.recipeId(), base.status(), base.targetArtifacts(),
                    semantics, base.sourceMapIds(), base.obligationIds(), base.backendRef(), base.parsed(),
                    base.registered(), base.deterministic(), base.placeholder(), base.agentGenerated(),
                    base.humanReviewApproved(), base.reviewEvidenceRef(), base.containsSecretMaterial(), base.diagnostics());
        };
        RunResult result = service(entities(), drift, passingValidation()).migrate(request(recipes()));
        assertTrue(result.differences().stream().anyMatch(difference -> difference.category().equals("propagation")
                && difference.assessment().equals("not-equivalent")));
        assertTrue(result.obligations().stream().anyMatch(SemanticObligation::openAndBlocking));
        assertFalse(result.conformance().eligibleForBatch8());
    }

    @Test void fingerprintNeedsIndependentEvidenceAndRejectsMixedSpringModes() {
        EvidenceFrameworkFingerprintDetector detector = new EvidenceFrameworkFingerprintDetector();
        FrameworkFingerprint single = detector.detect(List.of(
                new FrameworkSignal("dependency", "spring-boot-starter-web", "pom.xml")), request(recipes()).targetProfile());
        assertFalse(single.complete());
        assertTrue(single.diagnostics().contains("framework-version-unresolved"));

        FrameworkFingerprint mixed = detector.detect(List.of(
                new FrameworkSignal("dependency", "spring-boot-starter-web", "pom.xml"),
                new FrameworkSignal("annotation", "Spring MVC @RestController", "A.java"),
                new FrameworkSignal("configuration", "spring webflux reactive", "application.yml"),
                new FrameworkSignal("framework-version", "3.5.3", "effective-pom")), request(recipes()).targetProfile());
        assertFalse(mixed.complete());
        assertTrue(mixed.diagnostics().contains("mixed-spring-mvc-and-webflux"));
    }

    @Test void canonicalHashDoesNotDependOnMapInsertionOrder() {
        Map<String,String> first = new LinkedHashMap<>(); first.put("b", "2"); first.put("a", "1");
        Map<String,String> second = new LinkedHashMap<>(); second.put("a", "1"); second.put("b", "2");
        assertEquals(FrameworkIds.hash(first), FrameworkIds.hash(second));
    }

    private FrameworkMigrationService service(List<AfsmEntity> entities, FrameworkBackend backend,
                                              StartupValidator validator) {
        AfsmLifter lifter = request -> new LiftResult(true, "spring-afsm-adapter@1", entities, List.of(), List.of());
        return new FrameworkMigrationService(lifter, backend, validator);
    }

    private FrameworkBackend passingBackend() { return emission(entity -> false, false, false); }

    private FrameworkBackend emission(java.util.function.Predicate<AfsmEntity> selected,
                                      boolean agent, boolean secret) {
        return request -> {
            AfsmEntity entity = request.entity();
            Map<String,String> semantics = new LinkedHashMap<>(entity.attributes());
            return new Emission(FrameworkIds.id("framework-emission", entity.entityId(), request.plan().planId()),
                    entity.entityId(), request.plan().selectedRecipeId(), Status.PASSED,
                    List.of("generated/" + entity.entityId().replace(':', '-') + ".ast-patch"),
                    semantics, entity.sourceMapIds(), List.of(), "native-framework-emitter@1",
                    true, true, true, false, selected.test(entity) && agent,
                    false, null, selected.test(entity) && secret, List.of());
        };
    }

    private StartupValidator passingValidation() {
        return request -> new FrameworkValidation(Status.PASSED, Status.PASSED, Status.PASSED,
                Status.PASSED, Status.PASSED, Status.PASSED, Status.PASSED,
                true, true, true, true, "framework-sandbox@1", "image@sha256:123",
                List.of("route-table.json", "openapi.json", "startup.log", "shutdown.log"), List.of());
    }

    private Request request(List<Recipe> recipes) {
        SkeletonModels.TargetProfile target = new SkeletonModels.TargetProfile("target-dotnet-8", "csharp",
                "exact", "8.0", "aspnet-core-controller", "msbuild", List.of("container"),
                "web-api", List.of(), List.of(), Map.of(), true, List.of(), List.of(), List.of());
        DependencyMigrationModels.Coverage coverage = new DependencyMigrationModels.Coverage(1,1,1,1,1,1,1,0);
        DependencyMigrationModels.ModuleGate gate = new DependencyMigrationModels.ModuleGate("target-app", "D-D",
                DependencyMigrationModels.Status.PASSED, true, List.of(), List.of("dependency-contracts.json"));
        DependencyMigrationModels.ConformanceReport dependency = new DependencyMigrationModels.ConformanceReport(6,
                "PASSED", "dependency-run-1", List.of(gate), coverage, List.of(), List.of(), true);
        List<FrameworkSignal> signals = List.of(
                new FrameworkSignal("dependency", "org.springframework.boot:spring-boot-starter-web", "pom.xml:20"),
                new FrameworkSignal("annotation", "@RestController", "src/Orders.java:5"),
                new FrameworkSignal("framework-version", "3.5.3", "effective-pom.json"));
        return new Request(workspace, uir(), target, "8.0", dependency, Map.of("source-app", "target-app"),
                signals, recipes, NOW);
    }

    private UirModels.Dataset uir() {
        UirModels.Coverage coverage = new UirModels.Coverage(1,1,1,1,1,1,0,0,0,0);
        UirModels.RunManifest manifest = new UirModels.RunManifest("uir-run-1", "semantic-run-1", "snapshot-1",
                "PASSED", "1.0", List.of("source-module"), List.of("uir.core"), List.of("lift"),
                "config-1", coverage, List.of(), NOW);
        UirModels.SourceMap sourceMap = new UirModels.SourceMap("uir-sm-1", List.of("psp:symbol:orders"),
                List.of("uirdecl:orders"), "exact", new PspModels.SourceRange("file:orders", 0, 20, 1, 0, 1, 20),
                1, List.of(), List.of());
        UirModels.Provenance provenance = new UirModels.Provenance("uir-prov-1", "lift", "1",
                List.of("psp:symbol:orders"), List.of(), "exact", NOW);
        UirModels.Entity entity = new UirModels.Entity("source-map", "uir-sm-1", "snapshot-1", "semantic-run-1",
                "uir-run-1", "source-module", sourceMap, provenance);
        return new UirModels.Dataset(manifest, List.of(entity));
    }

    private List<AfsmEntity> entities() {
        List<AfsmEntity> values = new ArrayList<>();
        values.add(entity("afsm:authn:jwt", "authentication-scheme", Map.of(
                "issuer", "issuer-a", "audience", "orders", "algorithm", "RS256",
                "unauthenticatedStatus", "401", "challenge", "Bearer"), List.of()));
        values.add(entity("afsm:authz:orders-read", "authorization-policy", Map.of(
                "expression", "permission:orders.read", "defaultDecision", "deny", "failureStatus", "403"), List.of()));
        values.add(entity("afsm:endpoint:orders", "endpoint", Map.of(
                "route", "/orders/{id}", "methods", "GET", "access", "protected",
                "status", "200", "contentType", "application/json"),
                List.of("afsm:authn:jwt", "afsm:authz:orders-read")));
        values.add(entity("afsm:middleware:authn", "middleware", Map.of(
                "concern", "authentication", "order", "100", "shortCircuit", "true", "async", "true"), List.of()));
        values.add(entity("afsm:middleware:authz", "middleware", Map.of(
                "concern", "authorization", "order", "200", "shortCircuit", "true", "async", "true"), List.of()));
        values.add(entity("afsm:provider:orders", "provider", Map.of(
                "scope", "request", "lazy", "false", "optional", "false", "factoryCalls", "one", "cleanup", "dispose"), List.of()));
        values.add(entity("afsm:tx:create", "transaction-policy", Map.of(
                "propagation", "required", "isolation", "read-committed", "rollback", "runtime-error",
                "timeout", "30", "readOnly", "false"), List.of()));
        values.add(entity("afsm:config:database", "configuration-binding", Map.of(
                "required", "true", "reload", "startup", "secret", "true",
                "secretReference", "secret://database/url"), List.of()));
        return List.copyOf(values);
    }

    private AfsmEntity entity(String id, String kind, Map<String,String> attributes, List<String> related) {
        Provenance provenance = new Provenance("spring-afsm-adapter", "1", "spring.annotation", 1, NOW,
                List.of("src/Orders.java", "application.yml"));
        return new AfsmEntity("1.0", id, kind, "target-app", "spring-boot", "3.5.3",
                "aspnet-core-controller", attributes, related, List.of("uir-sm-1"), List.of(), provenance);
    }

    private List<Recipe> recipes() {
        return entities().stream().map(AfsmEntity::entityKind).distinct().sorted().map(kind ->
                new Recipe("recipe:" + kind, "1", "spring-boot", "*", "aspnet-core-controller", "*",
                        kind, 100, 500, "exact", true, true, List.of("emit-" + kind), List.of(),
                        List.of(), List.of("static", "startup"), List.of("fixture:" + kind), "review/" + kind)).toList();
    }

    private AfsmEntity replace(AfsmEntity entity, UnaryOperator<Map<String,String>> transform,
                               List<String> related) {
        return new AfsmEntity(entity.afsmVersion(), entity.entityId(), entity.entityKind(), entity.targetModuleId(),
                entity.sourceFramework(), entity.sourceVersion(), entity.targetFramework(),
                transform.apply(entity.attributes()), related, entity.sourceMapIds(), entity.obligationIds(), entity.provenance());
    }

    private Map<String,String> with(Map<String,String> source, String key, String value) {
        Map<String,String> result = new LinkedHashMap<>(source); result.put(key, value); return Map.copyOf(result);
    }
}
