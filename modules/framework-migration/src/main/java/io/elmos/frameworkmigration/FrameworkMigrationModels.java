package io.elmos.frameworkmigration;

import io.elmos.dependency.DependencyMigrationModels;
import io.elmos.skeleton.SkeletonModels;
import io.elmos.uir.UirModels;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/** Batch 7 AFSM contracts. Every executable claim is backed by an injected authority. */
public final class FrameworkMigrationModels {
    private FrameworkMigrationModels() {}

    public enum Status { PASSED, FAILED, BLOCKED, NOT_RUN, INCONCLUSIVE, PASSED_WITH_OBLIGATIONS }

    public static final List<String> ENTITY_KINDS = List.of(
            "application", "module", "component", "provider", "dependency-binding", "lifecycle-scope",
            "http-pipeline", "middleware", "filter", "interceptor", "guard", "endpoint",
            "parameter-binding", "response-contract", "exception-mapping", "validation-contract",
            "authentication-scheme", "authorization-policy", "entity-model", "repository-model",
            "query-model", "unit-of-work", "transaction-policy", "configuration-source",
            "configuration-binding", "message-producer", "message-consumer", "message-contract",
            "cache-region", "cache-operation", "scheduled-job", "background-task", "startup-hook",
            "shutdown-hook", "health-check");

    public record Request(Path workspace, UirModels.Dataset uir,
                          SkeletonModels.TargetProfile targetProfile,
                          String targetFrameworkVersion,
                          DependencyMigrationModels.ConformanceReport dependencyConformance,
                          Map<String,String> sourceProjectToTargetModule,
                          List<FrameworkSignal> frameworkSignals,
                          List<Recipe> recipes, Instant observedAt) {
        public Request {
            sourceProjectToTargetModule = map(sourceProjectToTargetModule);
            frameworkSignals = copy(frameworkSignals);
            recipes = copy(recipes);
        }
    }

    public record FrameworkSignal(String kind, String value, String sourceRef) {}

    public record FrameworkFingerprint(String frameworkId, String family, String webMode,
                                       String programmingModel, String adapter, String version,
                                       double confidence, boolean complete,
                                       List<FrameworkSignal> evidence, List<String> components,
                                       List<String> diagnostics) {
        public FrameworkFingerprint {
            evidence = copy(evidence); components = copy(components); diagnostics = copy(diagnostics);
        }
    }

    @FunctionalInterface public interface FingerprintDetector {
        FrameworkFingerprint detect(List<FrameworkSignal> signals, SkeletonModels.TargetProfile targetProfile);
    }

    public record Provenance(String extractor, String extractorVersion, String ruleId,
                             double confidence, Instant observedAt, List<String> evidenceRefs) {
        public Provenance { evidenceRefs = copy(evidenceRefs); }
    }

    public record AfsmEntity(String afsmVersion, String entityId, String entityKind,
                             String targetModuleId, String sourceFramework, String sourceVersion,
                             String targetFramework, Map<String,String> attributes,
                             List<String> relatedEntityIds, List<String> sourceMapIds,
                             List<String> obligationIds, Provenance provenance) {
        public AfsmEntity {
            attributes = map(attributes); relatedEntityIds = copy(relatedEntityIds);
            sourceMapIds = copy(sourceMapIds); obligationIds = copy(obligationIds);
        }
    }

    public record SemanticObligation(String obligationId, String entityId, String category,
                                     String severity, String status, String statement,
                                     List<String> verificationStrategy, List<String> evidenceRefs,
                                     String owner, String waiverReason) {
        public SemanticObligation {
            verificationStrategy = copy(verificationStrategy); evidenceRefs = copy(evidenceRefs);
        }
        public boolean openAndBlocking() {
            return "blocking".equalsIgnoreCase(severity)
                    && !"verified".equalsIgnoreCase(status) && !"waived".equalsIgnoreCase(status);
        }
    }

    public record LiftRequest(FrameworkFingerprint fingerprint, UirModels.Dataset uir,
                              SkeletonModels.TargetProfile targetProfile,
                              Map<String,String> sourceProjectToTargetModule) {
        public LiftRequest { sourceProjectToTargetModule = map(sourceProjectToTargetModule); }
    }

    public record LiftResult(boolean complete, String analyzerRef, List<AfsmEntity> entities,
                             List<SemanticObligation> obligations, List<String> diagnostics) {
        public LiftResult { entities = copy(entities); obligations = copy(obligations); diagnostics = copy(diagnostics); }
    }

    @FunctionalInterface public interface AfsmLifter { LiftResult lift(LiftRequest request); }

    public record Recipe(String recipeId, String version, String sourceFramework,
                         String sourceVersionRange, String targetFramework,
                         String targetVersionRange, String entityKind, int specificity,
                         int priority, String fidelity, boolean idempotent,
                         boolean production, List<String> transformations,
                         List<String> requiredDependencies, List<String> obligationTemplates,
                         List<String> validations, List<String> tests, String provenanceRef) {
        public Recipe {
            transformations = copy(transformations); requiredDependencies = copy(requiredDependencies);
            obligationTemplates = copy(obligationTemplates); validations = copy(validations); tests = copy(tests);
        }
    }

    public record RecipePlan(String planId, String entityId, String selectedRecipeId,
                             List<String> alternatives, List<String> transformations,
                             List<String> requiredDependencies, List<String> obligationIds,
                             String status, boolean automatic, List<String> diagnostics) {
        public RecipePlan {
            alternatives = copy(alternatives); transformations = copy(transformations);
            requiredDependencies = copy(requiredDependencies); obligationIds = copy(obligationIds);
            diagnostics = copy(diagnostics);
        }
    }

    public record EmissionRequest(AfsmEntity entity, RecipePlan plan,
                                  SkeletonModels.TargetProfile targetProfile,
                                  Path targetRepository) {}

    public record Emission(String emissionId, String entityId, String recipeId,
                           Status status, List<String> targetArtifacts,
                           Map<String,String> targetSemantics, List<String> sourceMapIds,
                           List<String> obligationIds, String backendRef,
                           boolean parsed, boolean registered, boolean deterministic,
                           boolean placeholder, boolean agentGenerated,
                           boolean humanReviewApproved, String reviewEvidenceRef,
                           boolean containsSecretMaterial, List<String> diagnostics) {
        public Emission {
            targetArtifacts = copy(targetArtifacts); targetSemantics = map(targetSemantics);
            sourceMapIds = copy(sourceMapIds); obligationIds = copy(obligationIds); diagnostics = copy(diagnostics);
        }
        public boolean passed() {
            return status == Status.PASSED && parsed && registered && deterministic && !placeholder
                    && !containsSecretMaterial && backendRef != null && !backendRef.isBlank()
                    && !targetArtifacts.isEmpty() && !sourceMapIds.isEmpty();
        }
    }

    @FunctionalInterface public interface FrameworkBackend { Emission emit(EmissionRequest request); }

    public record ValidationRequest(Path targetRepository, FrameworkFingerprint fingerprint,
                                    List<AfsmEntity> entities, List<Emission> emissions) {
        public ValidationRequest { entities = copy(entities); emissions = copy(emissions); }
    }

    public record FrameworkValidation(Status staticModel, Status bootstrap,
                                      Status containerResolution, Status routeDiscovery,
                                      Status openapiGeneration, Status smoke, Status shutdown,
                                      boolean isolatedEnvironment, boolean productionAccessDenied,
                                      boolean schedulerExecutionDisabled, boolean consumerExecutionDisabled,
                                      String backendRef, String environmentRef,
                                      List<String> artifacts, List<String> diagnostics) {
        public FrameworkValidation { artifacts = copy(artifacts); diagnostics = copy(diagnostics); }
        public boolean frameworkReady() {
            return staticModel == Status.PASSED && bootstrap == Status.PASSED
                    && containerResolution == Status.PASSED && routeDiscovery == Status.PASSED
                    && openapiGeneration == Status.PASSED && isolatedEnvironment
                    && productionAccessDenied && schedulerExecutionDisabled && consumerExecutionDisabled
                    && backendRef != null && !backendRef.isBlank() && environmentRef != null
                    && !environmentRef.isBlank() && !artifacts.isEmpty();
        }
        public boolean smokeReady() {
            return frameworkReady() && smoke == Status.PASSED && shutdown == Status.PASSED;
        }
        public static FrameworkValidation blocked(String diagnostic) {
            return new FrameworkValidation(Status.BLOCKED, Status.NOT_RUN, Status.NOT_RUN,
                    Status.NOT_RUN, Status.NOT_RUN, Status.NOT_RUN, Status.NOT_RUN,
                    false, false, false, false, null, null, List.of(), List.of(diagnostic));
        }
    }

    @FunctionalInterface public interface StartupValidator {
        FrameworkValidation validate(ValidationRequest request);
    }

    public record SemanticDifference(String differenceId, String entityId, String category,
                                     String sourceValue, String targetValue, String assessment,
                                     String risk, String obligationId) {}

    public record Coverage(double frameworkEntityLiftRate, double endpointMigrationRate,
                           double providerMigrationRate, double validationMigrationRate,
                           double ormMappingRate, double transactionMappingRate,
                           double securityMappingRate, double configurationMappingRate,
                           double messagingMappingRate, double cacheMappingRate,
                           double schedulerMappingRate, double sourceTargetTraceCoverage) {}

    public record Fidelity(double routeContract, double requestBinding,
                           double responseContract, double middlewareOrder,
                           double diScope, double validation, double transaction,
                           double authentication, double authorization,
                           double messaging, double cache, double scheduler,
                           double lifecycle) {}

    public record ModuleGate(String targetModuleId, String gate, Status status,
                             boolean eligibleForBuildRepair,
                             boolean eligibleForIntegrationTesting,
                             boolean eligibleForProductionValidation,
                             List<String> restrictions, List<String> evidenceRefs) {
        public ModuleGate { restrictions = copy(restrictions); evidenceRefs = copy(evidenceRefs); }
    }

    public record ConformanceReport(int batch, String status, String frameworkRunId,
                                    List<ModuleGate> modules, Coverage coverage, Fidelity fidelity,
                                    List<String> blockingErrors, List<String> openObligations,
                                    boolean eligibleForBatch8) {
        public ConformanceReport {
            modules = copy(modules); blockingErrors = copy(blockingErrors); openObligations = copy(openObligations);
        }
    }

    public record RunManifest(String frameworkRunId, String sourceSnapshotId, String uirRunId,
                              String dependencyRunId, String targetProfileId,
                              String targetFrameworkVersion, String frameworkFingerprintId, String configurationHash,
                              List<String> afsmEntityIds, List<String> recipePlanIds,
                              List<String> emissionIds, Instant createdAt) {
        public RunManifest {
            afsmEntityIds = copy(afsmEntityIds); recipePlanIds = copy(recipePlanIds); emissionIds = copy(emissionIds);
        }
    }

    public record RunResult(RunManifest manifest, FrameworkFingerprint fingerprint,
                            LiftResult lift, List<RecipePlan> recipePlans,
                            List<Emission> emissions, List<SemanticDifference> differences,
                            List<SemanticObligation> obligations,
                            FrameworkValidation validation, ConformanceReport conformance) {
        public RunResult {
            recipePlans = copy(recipePlans); emissions = copy(emissions); differences = copy(differences);
            obligations = copy(obligations);
        }
    }

    private static <T> List<T> copy(List<T> value) { return value == null ? List.of() : List.copyOf(value); }
    private static <K,V> Map<K,V> map(Map<K,V> value) { return value == null ? Map.of() : Map.copyOf(value); }
}
