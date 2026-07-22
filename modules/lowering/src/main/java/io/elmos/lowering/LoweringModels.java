package io.elmos.lowering;

import io.elmos.skeleton.SkeletonModels;
import io.elmos.uir.UirModels;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class LoweringModels {
    private LoweringModels() {}

    public enum Status { PASSED, FAILED, BLOCKED, NOT_RUN, PASSED_WITH_OBLIGATIONS }
    public record GenerationProfile(String fidelityMode, boolean allowHelpers, boolean allowCompatibilityRuntime,
                                    boolean allowAgentFallback, boolean preserveSourceStructure,
                                    String generateComments, int idiomaticLevel) {}
    public record Budgets(int maxAgentCalls, int maxGeneratedLocPerPatch, int maxRuleIterations) {}
    public record Request(Path workspace, UirModels.Dataset uir, UirModels.ConformanceReport uirConformance,
                          SkeletonModels.Result skeleton, GenerationProfile profile, Budgets budgets) {}

    public record Capability(String capabilityId, String targetLanguage, String targetVersion, String state,
                             List<String> targetConstructs, List<String> preconditions,
                             List<String> semanticGaps, List<String> fallbacks, List<String> ruleIds) {
        public Capability { targetConstructs=copy(targetConstructs); preconditions=copy(preconditions); semanticGaps=copy(semanticGaps); fallbacks=copy(fallbacks); ruleIds=copy(ruleIds); }
    }
    public record Rule(String ruleId, String version, String dialect, String opcode, String targetLanguage,
                       String minVersion, String maxVersion, String strategy, int specificity, int priority,
                       String fidelity, boolean idempotent, boolean production,
                       List<String> emittedConstructs, List<String> obligations,
                       List<String> approvedDependencies, List<String> tests) {
        public Rule { emittedConstructs=copy(emittedConstructs); obligations=copy(obligations); approvedDependencies=copy(approvedDependencies); tests=copy(tests); }
    }
    public record TypeMapping(String sourceTypeId, String targetLanguage, String targetSyntax, String strategy,
                              String lossiness, boolean conversionRequired, List<String> obligationIds) {
        public TypeMapping { obligationIds=copy(obligationIds); }
    }
    public record Temporary(String temporaryId, String name, String typeId, List<String> initializerOperationIds,
                            String lifetimeScope, String reason) { public Temporary { initializerOperationIds=copy(initializerOperationIds); } }
    public record OperationPlan(String operationId, String ruleId, String strategy, String fidelity,
                                List<String> operandOrder, List<Integer> lazyOperands,
                                List<String> temporaryIds, List<String> generatedNodeIds,
                                List<String> obligationIds, double confidence) {
        public OperationPlan { operandOrder=copy(operandOrder); lazyOperands=copy(lazyOperands); temporaryIds=copy(temporaryIds); generatedNodeIds=copy(generatedNodeIds); obligationIds=copy(obligationIds); }
    }
    public record CallablePlan(String callablePlanId, String moduleId, String sourceDeclarationId,
                               String targetDeclarationId, String targetFile, String targetLanguage,
                               String status, List<String> operationIds, List<OperationPlan> operations,
                               List<TypeMapping> typeMappings, List<Temporary> temporaries,
                               List<String> openObligations, List<String> escalationReasons,
                               String inputHash, String rulesHash) {
        public CallablePlan { operationIds=copy(operationIds); operations=copy(operations); typeMappings=copy(typeMappings); temporaries=copy(temporaries); openObligations=copy(openObligations); escalationReasons=copy(escalationReasons); }
    }

    public record EmissionRequest(CallablePlan plan, UirModels.Declaration declaration,
                                  List<UirModels.Operation> operations, String phase) {}
    public record Emission(String phase, String body, List<String> importSymbols,
                           List<String> generatedNodeIds, List<String> sourceOperationIds,
                           List<String> diagnostics) {
        public Emission { importSymbols=copy(importSymbols); generatedNodeIds=copy(generatedNodeIds); sourceOperationIds=copy(sourceOperationIds); diagnostics=copy(diagnostics); }
    }
    @FunctionalInterface public interface TargetEmitter { Emission emit(EmissionRequest request); }
    public record ValidationRequest(CallablePlan plan, Emission emission, Path targetRepository) {}
    public record StaticValidation(String targetDeclarationId, Status syntax, Status symbols, Status types,
                                   Status semanticChecks, List<String> diagnostics,
                                   List<String> openObligations, String backendRef) {
        public StaticValidation { diagnostics=copy(diagnostics); openObligations=copy(openObligations); }
        public boolean passed() { return syntax==Status.PASSED && symbols==Status.PASSED && types==Status.PASSED && semanticChecks!=Status.FAILED && semanticChecks!=Status.BLOCKED && semanticChecks!=Status.NOT_RUN; }
    }
    @FunctionalInterface public interface StaticValidator { StaticValidation validate(ValidationRequest request); }

    public record Patch(String patchId, String targetDeclarationId, String generationId, String baseFileHash,
                        String resultFileHash, String targetFile, List<String> sourceOperationIds,
                        List<String> ruleIds, List<String> obligationIds, String status, boolean reversible) {
        public Patch { sourceOperationIds=copy(sourceOperationIds); ruleIds=copy(ruleIds); obligationIds=copy(obligationIds); }
    }
    public record AgentPacket(String taskId, String targetDeclarationId, String targetLanguage,
                              String migrationMode, List<String> operationIds, List<String> typeIds,
                              List<String> effectIds, List<String> obligationIds,
                              List<String> constraints, List<String> validationCommands,
                              String expectedOutput, String reason) {
        public AgentPacket { operationIds=copy(operationIds); typeIds=copy(typeIds); effectIds=copy(effectIds); obligationIds=copy(obligationIds); constraints=copy(constraints); validationCommands=copy(validationCommands); }
    }
    public record CallableResult(String targetDeclarationId, String moduleId, String status,
                                 String faithfulBodyHash, String idiomaticBodyHash,
                                 Patch patch, StaticValidation faithfulValidation,
                                 StaticValidation idiomaticValidation, AgentPacket agentPacket,
                                 List<String> diagnostics) { public CallableResult { diagnostics=copy(diagnostics); } }
    public record Coverage(double callableGenerationRate, double deterministicLoweringRate,
                           double agentLoweringRate, double manualRate, double opaqueRate,
                           double staticValidationRate, double sourceMapCoverage,
                           int placeholderCount, int untrackedGeneratedCode) {}
    public record Fidelity(double typeMapping, double evaluationOrder, double numericSemantics,
                           double collectionSemantics, double exceptionContract,
                           double asyncContract, double nullabilityContract) {}
    public record ModuleGate(String targetModuleId, String gate, boolean eligibleForDependencyMapping,
                             boolean eligibleForFrameworkLowering, boolean eligibleForBehavioralTesting,
                             List<String> restrictions) { public ModuleGate { restrictions=copy(restrictions); } }
    public record ConformanceReport(int batch, String status, String loweringRunId,
                                    List<ModuleGate> modules, Coverage coverage, Fidelity fidelity,
                                    List<String> blockingErrors, List<String> openObligations,
                                    boolean eligibleForBatch6) {
        public ConformanceReport { modules=copy(modules); blockingErrors=copy(blockingErrors); openObligations=copy(openObligations); }
    }
    public record RunManifest(String loweringRunId, String uirRunId, String targetRepositoryId,
                              String targetProfileId, String targetLanguage, String configurationHash,
                              List<String> callablePlanIds, List<String> ruleIds,
                              List<String> capabilityIds, Instant createdAt) {
        public RunManifest { callablePlanIds=copy(callablePlanIds); ruleIds=copy(ruleIds); capabilityIds=copy(capabilityIds); }
    }
    public record RunResult(RunManifest manifest, List<CallablePlan> plans,
                            List<CallableResult> results, ConformanceReport conformance) {
        public RunResult { plans=copy(plans); results=copy(results); }
    }

    private static <T> List<T> copy(List<T> value) { return value == null ? List.of() : List.copyOf(value); }
}
