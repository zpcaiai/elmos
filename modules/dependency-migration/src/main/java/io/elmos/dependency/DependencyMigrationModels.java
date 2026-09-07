package io.elmos.dependency;

import io.elmos.intake.IntakeModels;
import io.elmos.lowering.LoweringModels;
import io.elmos.skeleton.SkeletonModels;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/** Stable Batch 6 contracts. Evidence is explicit; absence of evidence never means compatibility. */
public final class DependencyMigrationModels {
    private DependencyMigrationModels() {}

    public enum Status { PASSED, FAILED, BLOCKED, NOT_RUN, INCONCLUSIVE, PASSED_WITH_OBLIGATIONS }
    public enum Strategy {
        REMOVE, TARGET_STANDARD_LIBRARY, APPROVED_NATIVE, ECOSYSTEM_PACKAGE,
        GENERATED_ADAPTER, COMPATIBILITY_RUNTIME, IN_PROCESS_WRAPPER,
        SIDECAR, REMOTE_SERVICE, RETAIN_SOURCE_RUNTIME, MANUAL_REVIEW, PROHIBITED
    }

    public record Request(Path workspace, IntakeModels.BuildModel buildModel,
                          SkeletonModels.TargetProfile targetProfile,
                          LoweringModels.ConformanceReport loweringConformance,
                          Map<String,String> projectToTargetModule,
                          UsageEvidenceBundle usageEvidence,
                          List<KnowledgeMapping> knowledgeMappings,
                          Instant observedAt) {
        public Request {
            projectToTargetModule = map(projectToTargetModule);
            knowledgeMappings = copy(knowledgeMappings);
        }
    }

    public record NormalizedDependency(String dependencyId, String projectId, String ecosystem,
                                       String coordinate, String name, String declaredVersion,
                                       String resolvedVersion, String scope, String source,
                                       boolean direct, boolean resolved, List<String> issues) {
        public NormalizedDependency { issues = copy(issues); }
    }
    public record ResolvedEdge(String fromDependencyId, String toDependencyId, String relation,
                               String evidenceRef) {}
    public record ResolvedGraph(String projectId, List<NormalizedDependency> nodes,
                                List<ResolvedEdge> edges, boolean complete,
                                String resolverRef, List<String> issues) {
        public ResolvedGraph { nodes=copy(nodes); edges=copy(edges); issues=copy(issues); }
    }
    public record GraphResolution(List<ResolvedEdge> edges, boolean complete,
                                  String resolverRef, List<String> issues) {
        public GraphResolution { edges=copy(edges); issues=copy(issues); }
    }
    @FunctionalInterface public interface ResolvedGraphProvider {
        GraphResolution reconstruct(IntakeModels.BuildProject project, List<NormalizedDependency> dependencies);
    }

    public record ApiUsageEvidence(String projectId, String ecosystem, String dependencyName,
                                   List<String> importedSymbols, List<String> calledApis,
                                   List<String> constructedTypes, List<String> annotations,
                                   List<String> sourceRefs, Map<String,String> observedSemantics) {
        public ApiUsageEvidence {
            importedSymbols=copy(importedSymbols); calledApis=copy(calledApis);
            constructedTypes=copy(constructedTypes); annotations=copy(annotations);
            sourceRefs=copy(sourceRefs); observedSemantics=map(observedSemantics);
        }
    }
    public record UsageEvidenceBundle(boolean complete, String analyzerRef,
                                      List<ApiUsageEvidence> usages, List<String> unresolved) {
        public UsageEvidenceBundle { usages=copy(usages); unresolved=copy(unresolved); }
    }
    public record ApiUsage(String dependencyId, List<String> importedSymbols,
                           List<String> calledApis, List<String> constructedTypes,
                           List<String> annotations, List<String> sourceRefs,
                           Map<String,String> observedSemantics, boolean observed) {
        public ApiUsage {
            importedSymbols=copy(importedSymbols); calledApis=copy(calledApis);
            constructedTypes=copy(constructedTypes); annotations=copy(annotations);
            sourceRefs=copy(sourceRefs); observedSemantics=map(observedSemantics);
        }
    }
    public record SemanticProfile(String dependencyId, List<String> requiredApis,
                                  Map<String,String> requirements, List<String> evidenceRefs,
                                  double confidence, List<String> unresolved) {
        public SemanticProfile { requiredApis=copy(requiredApis); requirements=map(requirements); evidenceRefs=copy(evidenceRefs); unresolved=copy(unresolved); }
    }

    public record KnowledgeMapping(String mappingId, String sourceEcosystem, String sourceName,
                                   String sourceVersionRange, String targetLanguage, String targetKind,
                                   String targetCoordinate, String targetVersion, Strategy strategy,
                                   Map<String,String> apiMappings, Map<String,String> semanticClaims,
                                   double confidence, String provenanceRef, Instant observedAt,
                                   String approvalStatus) {
        public KnowledgeMapping { apiMappings=map(apiMappings); semanticClaims=map(semanticClaims); }
    }
    public record Candidate(String candidateId, String mappingId, String targetKind,
                            String coordinate, String version, Strategy strategy,
                            Map<String,String> apiMappings, Map<String,String> semanticClaims,
                            double knowledgeConfidence, String provenanceRef) {
        public Candidate { apiMappings=map(apiMappings); semanticClaims=map(semanticClaims); }
    }
    public record CompatibilityScore(String candidateId, double apiCoverage,
                                     double semanticFit, double platformFit,
                                     double operationalFit, double total,
                                     List<String> gaps, List<String> blockingReasons) {
        public CompatibilityScore { gaps=copy(gaps); blockingReasons=copy(blockingReasons); }
        public boolean selectable() { return blockingReasons.isEmpty(); }
    }
    public record SupplyChainAssessment(String candidateId, Status status, String license,
                                        String licenseEvidenceRef, String vulnerabilityState,
                                        String vulnerabilityEvidenceRef, String provenanceState,
                                        String supportState, String platformState,
                                        Instant assessedAt, List<String> blockers) {
        public SupplyChainAssessment { blockers=copy(blockers); }
        public boolean passed() {
            return status == Status.PASSED && blockers.isEmpty() && assessedAt != null
                    && licenseEvidenceRef != null && !licenseEvidenceRef.isBlank()
                    && vulnerabilityEvidenceRef != null && !vulnerabilityEvidenceRef.isBlank();
        }
    }
    @FunctionalInterface public interface RiskAssessor {
        SupplyChainAssessment assess(Candidate candidate, SkeletonModels.TargetProfile targetProfile, Instant observedAt);
    }

    public record AdapterPlan(String adapterId, String dependencyId, Strategy strategy,
                              String targetModuleId, List<String> mappedApis,
                              List<String> generatedFiles, List<String> obligations) {
        public AdapterPlan { mappedApis=copy(mappedApis); generatedFiles=copy(generatedFiles); obligations=copy(obligations); }
    }
    public record BoundaryPlan(String boundaryId, String dependencyId, Strategy strategy,
                               String protocol, String serialization, String lifecycle,
                               String threading, List<String> resources,
                               List<String> deploymentArtifacts, List<String> obligations) {
        public BoundaryPlan { resources=copy(resources); deploymentArtifacts=copy(deploymentArtifacts); obligations=copy(obligations); }
    }
    public record Decision(String decisionId, String dependencyId, String sourceCoordinate,
                           String sourceVersion, String targetModuleId,
                           Strategy strategy, Candidate selectedCandidate,
                           CompatibilityScore score, SupplyChainAssessment risk,
                           AdapterPlan adapter, BoundaryPlan boundary,
                           List<String> rationale, List<String> obligations,
                           boolean automatic) {
        public Decision { rationale=copy(rationale); obligations=copy(obligations); }
    }

    public record PatchOperation(String operation, String coordinate, String version,
                                 String scope, String reason) {}
    public record BuildPatch(String patchId, String targetModuleId, String buildTool,
                             List<PatchOperation> operations, String lockfilePolicy,
                             boolean lifecycleScriptsAllowed, List<String> expectedFiles,
                             List<String> obligations) {
        public BuildPatch { operations=copy(operations); expectedFiles=copy(expectedFiles); obligations=copy(obligations); }
    }
    public record BuildValidation(String patchId, Status status, String backendRef,
                                  boolean dependencyResolutionPassed, boolean lockfileRegenerated,
                                  boolean lifecycleScriptsExecuted, List<String> artifacts,
                                  List<String> diagnostics) {
        public BuildValidation { artifacts=copy(artifacts); diagnostics=copy(diagnostics); }
        public boolean passed() { return status==Status.PASSED && dependencyResolutionPassed && !lifecycleScriptsExecuted && backendRef!=null && !backendRef.isBlank() && !artifacts.isEmpty(); }
    }
    @FunctionalInterface public interface BuildPatchBackend {
        BuildValidation validate(Path targetRepository, BuildPatch patch);
    }
    public record ContractValidation(String dependencyId, Status status,
                                     double apiContractCoverage, double differentialPassRate,
                                     String validatorRef, List<String> artifacts,
                                     List<String> diagnostics) {
        public ContractValidation { artifacts=copy(artifacts); diagnostics=copy(diagnostics); }
        public boolean passed() { return status==Status.PASSED && apiContractCoverage==1.0 && differentialPassRate==1.0 && validatorRef!=null && !validatorRef.isBlank() && !artifacts.isEmpty(); }
    }
    @FunctionalInterface public interface ContractValidator {
        ContractValidation validate(Decision decision, SemanticProfile profile, ApiUsage usage);
    }

    public record ModuleGate(String targetModuleId, String gate, Status status,
                             boolean eligibleForFrameworkMigration,
                             List<String> restrictions, List<String> evidenceRefs) {
        public ModuleGate { restrictions=copy(restrictions); evidenceRefs=copy(evidenceRefs); }
    }
    public record Coverage(double inventoryCoverage, double resolvedGraphCoverage,
                           double usageCoverage, double semanticProfileCoverage,
                           double decisionCoverage, double buildValidationCoverage,
                           double contractValidationCoverage, int unresolvedCount) {}
    public record ConformanceReport(int batch, String status, String dependencyRunId,
                                    List<ModuleGate> modules, Coverage coverage,
                                    List<String> blockingErrors, List<String> openObligations,
                                    boolean eligibleForBatch7) {
        public ConformanceReport { modules=copy(modules); blockingErrors=copy(blockingErrors); openObligations=copy(openObligations); }
    }
    public record RunManifest(String dependencyRunId, String sourceSnapshotId,
                              String loweringRunId, String targetProfileId,
                              String configurationHash, List<String> dependencyIds,
                              List<String> decisionIds, Instant createdAt) {
        public RunManifest { dependencyIds=copy(dependencyIds); decisionIds=copy(decisionIds); }
    }
    public record RunResult(RunManifest manifest, List<ResolvedGraph> graphs,
                            List<ApiUsage> usages, List<SemanticProfile> profiles,
                            List<Decision> decisions, List<BuildPatch> patches,
                            List<BuildValidation> buildValidations,
                            List<ContractValidation> contractValidations,
                            ConformanceReport conformance) {
        public RunResult {
            graphs=copy(graphs); usages=copy(usages); profiles=copy(profiles); decisions=copy(decisions);
            patches=copy(patches); buildValidations=copy(buildValidations); contractValidations=copy(contractValidations);
        }
    }

    private static <T> List<T> copy(List<T> value) { return value == null ? List.of() : List.copyOf(value); }
    private static <K,V> Map<K,V> map(Map<K,V> value) { return value == null ? Map.of() : Map.copyOf(value); }
}
