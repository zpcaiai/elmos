package io.elmos.uir;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static io.elmos.semantic.PspModels.SourceRange;

/** Unified Intermediate Representation v1: high-level, structured, and derived flow views. */
public final class UirModels {
    private UirModels() {}
    public static final String PROTOCOL_VERSION = "1.0";

    public record Provenance(String provenanceId, String pass, String passVersion, List<String> inputEntityIds,
                             List<String> transformationIds, String confidenceReason, Instant observedAt) {
        public Provenance { inputEntityIds = copy(inputEntityIds); transformationIds = copy(transformationIds); }
    }
    public record Entity(String entityKind, String entityId, String snapshotId, String semanticRunId, String uirRunId,
                         String moduleId, Object payload, Provenance provenance, String contentHash,
                         long generation, String supersedes, boolean deleted) {
        public Entity(String entityKind, String entityId, String snapshotId, String semanticRunId, String uirRunId,
                      String moduleId, Object payload, Provenance provenance) {
            this(entityKind, entityId, snapshotId, semanticRunId, uirRunId, moduleId, payload, provenance,
                    UirIds.contentHash(payload), 1, null, false);
        }
        public Entity {
            if (contentHash == null || contentHash.isBlank()) contentHash = UirIds.contentHash(payload);
            if (generation < 1) generation = 1;
        }
    }
    public record Module(String moduleId, String projectId, String sourceLanguage, List<String> declarationIds,
                         List<String> dialects, Map<String,Object> languageSemantics) {
        public Module { declarationIds = copy(declarationIds); dialects = copy(dialects); languageSemantics = map(languageSemantics); }
    }
    public record Declaration(String declarationId, String kind, String name, String qualifiedName,
                              String containerDeclarationId, String visibility, List<String> modifiers,
                              String typeId, List<String> genericParameters, List<String> annotations,
                              String bodyRegionId, List<String> sourceSymbolIds, Map<String,Object> languageSemantics) {
        public Declaration { modifiers = copy(modifiers); genericParameters = copy(genericParameters); annotations = copy(annotations); sourceSymbolIds = copy(sourceSymbolIds); languageSemantics = map(languageSemantics); }
    }
    public record Nullability(String state, String sourceSemantics) {}
    public record NumericSemantics(String category, Integer bitWidth, Boolean signed, Integer precision, Integer scale,
                                   String overflow, boolean nanSupported, boolean infinitySupported) {}
    public record AbsenceSemantics(String kind, boolean distinguishFromNull, String runtimeRepresentation) {}
    public record Type(String typeId, String kind, String name, String declarationId, List<String> typeArguments,
                       Nullability nullability, NumericSemantics numeric, AbsenceSemantics absence,
                       List<String> parameterTypeIds, String returnTypeId, List<String> constraints,
                       List<String> traits, String origin, double confidence, Map<String,Object> languageSemantics) {
        public Type { typeArguments = copy(typeArguments); parameterTypeIds = copy(parameterTypeIds); constraints = copy(constraints); traits = copy(traits); languageSemantics = map(languageSemantics); }
    }
    public record Result(String valueId, String typeId) {}
    public record Evaluation(List<String> operandOrder, List<Integer> lazyOperands, boolean shortCircuit, boolean exceptionsStopEvaluation) {
        public Evaluation { operandOrder = copy(operandOrder); lazyOperands = copy(lazyOperands); }
    }
    public record Operation(String operationId, String dialect, String opcode, List<String> operands,
                            List<Result> results, Map<String,Object> attributes, List<String> regionIds,
                            List<String> effectIds, List<String> sourceMapIds, Evaluation evaluation,
                            double confidence) {
        public Operation { operands = copy(operands); results = copy(results); attributes = map(attributes); regionIds = copy(regionIds); effectIds = copy(effectIds); sourceMapIds = copy(sourceMapIds); }
    }
    public record Region(String regionId, String kind, List<String> blockIds, String entryBlockId,
                         String structuredPeerRegionId, String cfgPeerRegionId) {
        public Region { blockIds = copy(blockIds); }
    }
    public record Block(String blockId, List<String> argumentValueIds, List<String> operationIds,
                        String terminatorOperationId, boolean reachable) {
        public Block { argumentValueIds = copy(argumentValueIds); operationIds = copy(operationIds); }
    }
    public record Definition(String operationId, int resultIndex) {}
    public record Use(String operationId, int operandIndex) {}
    public record Value(String valueId, String typeId, Definition definition, List<Use> uses,
                        List<String> flowTypeIds, Object constantValue) {
        public Value { uses = copy(uses); flowTypeIds = copy(flowTypeIds); }
    }
    public record TypeRefinement(String valueId, String narrowedTypeId, String reason) {}
    public record CfgEdge(String edgeId, String fromBlockId, String toBlockId, String kind,
                          List<String> argumentValueIds, List<TypeRefinement> typeRefinements) {
        public CfgEdge { argumentValueIds = copy(argumentValueIds); typeRefinements = copy(typeRefinements); }
    }
    public record Effect(String effectId, String kind, String operationId, String resourceKind,
                         String resourceIdentity, String access, boolean conditional, String ordering,
                         boolean mayRepeat, String idempotency, double confidence, List<String> evidence) {
        public Effect { evidence = copy(evidence); }
    }
    public record EffectSummary(String callableDeclarationId, List<String> effectIds, boolean mayThrow,
                                boolean maySuspend, boolean blocking, String deterministic,
                                String idempotency, double confidence) {
        public EffectSummary { effectIds = copy(effectIds); }
    }
    public record ExceptionContract(String callableDeclarationId, List<String> declaredThrowTypeIds,
                                    List<String> inferredThrowTypeIds, boolean uncheckedOrDynamic,
                                    List<String> promiseRejectionTypeIds, double confidence) {
        public ExceptionContract { declaredThrowTypeIds = copy(declaredThrowTypeIds); inferredThrowTypeIds = copy(inferredThrowTypeIds); promiseRejectionTypeIds = copy(promiseRejectionTypeIds); }
    }
    public record AsyncContract(String callableDeclarationId, String asyncKind, String resultTypeId,
                                String completion, String coldOrHot, boolean startsOnCall,
                                boolean supportsCancellation, String cancellationType,
                                String schedulerAffinity, String errorChannel, String backpressure) {}
    public record Alias(String valueId, String bindingMutability, String referentMutability, String deepMutability,
                        String aliasClass, String escapeKind, String ownership, boolean disposalRequired,
                        double confidence, List<String> evidence) {
        public Alias { evidence = copy(evidence); }
    }
    public record Obligation(String obligationId, String category, String declarationId, String operationId,
                             String statement, Map<String,Object> sourceSemantics, Map<String,Object> targetRequirements,
                             List<String> verificationStrategy, String severity, String status,
                             List<String> evidence, String generatedBy) {
        public Obligation { sourceSemantics = map(sourceSemantics); targetRequirements = map(targetRequirements); verificationStrategy = copy(verificationStrategy); evidence = copy(evidence); }
    }
    public record SourceMap(String sourceMapId, List<String> pspEntityIds, List<String> uirEntityIds,
                            String mappingKind, SourceRange sourceRange, double confidence,
                            List<String> transformationIds, List<String> semanticNotes) {
        public SourceMap { pspEntityIds = copy(pspEntityIds); uirEntityIds = copy(uirEntityIds); transformationIds = copy(transformationIds); semanticNotes = copy(semanticNotes); }
    }
    public record Transformation(String transformationId, String pass, String passVersion,
                                 List<String> inputEntityIds, List<String> outputEntityIds,
                                 String semanticEquivalence, String proofLevel, boolean reversible,
                                 boolean idempotent, Map<String,Object> sourceSugarHint) {
        public Transformation { inputEntityIds = copy(inputEntityIds); outputEntityIds = copy(outputEntityIds); sourceSugarHint = map(sourceSugarHint); }
    }
    public record Diagnostic(String diagnosticId, String category, String severity, String relatedEntityId,
                             String message, boolean blocking, List<String> recommendedActions) {
        public Diagnostic { recommendedActions = copy(recommendedActions); }
    }
    public record Dialect(String name, String version, List<String> operations, List<String> types,
                          String verifier, List<String> loweringInterfaces, boolean opaqueForwardCompatible) {
        public Dialect { operations = copy(operations); types = copy(types); loweringInterfaces = copy(loweringInterfaces); }
    }
    public record LiftProfile(boolean preserveSyntaxSugar, boolean buildCfg, boolean buildSsa,
                              boolean inferEffects, boolean inferAliases, boolean preserveLanguageExtensions) {
        public static LiftProfile full() { return new LiftProfile(true, true, true, true, true, true); }
    }
    public record Coverage(double declarationLiftRate, double operationLiftRate, double sourceMapCoverage,
                           double typeCoverage, double callableBodyCoverage, double effectCoverage,
                           double unknownOperationRate, double opaqueOperationRate,
                           double unresolvedCallRate, double dynamicHighRiskRate) {}
    public record RunManifest(String uirRunId, String semanticRunId, String snapshotId, String status,
                              String protocolVersion, List<String> modules, List<String> dialects,
                              List<String> passPipeline, String configurationHash, Coverage coverage,
                              List<String> diagnosticIds, Instant createdAt) {
        public RunManifest { modules = copy(modules); dialects = copy(dialects); passPipeline = copy(passPipeline); diagnosticIds = copy(diagnosticIds); }
    }
    public record Dataset(RunManifest manifest, List<Entity> entities) { public Dataset { entities = copy(entities); } }
    public record ModuleGate(String moduleId, String gate, boolean eligibleForSkeletonGeneration,
                             boolean eligibleForAutomaticTranslation, List<String> restrictions, Coverage coverage) {
        public ModuleGate { restrictions = copy(restrictions); }
    }
    public record ConformanceReport(int batch, String status, List<ModuleGate> modules, Coverage coverage,
                                    List<String> blockingErrors, List<String> openObligations,
                                    List<String> violations, List<String> recommendedActions) {
        public ConformanceReport { modules = copy(modules); blockingErrors = copy(blockingErrors); openObligations = copy(openObligations); violations = copy(violations); recommendedActions = copy(recommendedActions); }
    }

    private static <T> List<T> copy(List<T> value) { return value == null ? List.of() : List.copyOf(value); }
    private static <K,V> Map<K,V> map(Map<K,V> value) { return value == null ? Map.of() : Map.copyOf(value); }
}
