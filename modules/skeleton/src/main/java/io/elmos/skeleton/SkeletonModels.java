package io.elmos.skeleton;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class SkeletonModels {
    private SkeletonModels() {}
    public enum Status { PASSED, FAILED, NOT_RUN, PROVISIONAL, BLOCKED }
    public record TargetProfile(String targetProfileId, String language, String runtimePolicy, String resolvedRuntimeVersion,
                                String preferredFramework, String preferredBuildTool, List<String> deploymentEnvironments,
                                String architecture, List<String> approvedDependencies, List<String> prohibitedDependencies,
                                Map<String,String> namingRules, boolean offlineBuildRequired, List<String> hardConstraints,
                                List<String> softPreferences, List<String> unresolvedDecisions) {
        public TargetProfile { deploymentEnvironments = copy(deploymentEnvironments); approvedDependencies = copy(approvedDependencies); prohibitedDependencies = copy(prohibitedDependencies); namingRules = map(namingRules); hardConstraints = copy(hardConstraints); softPreferences = copy(softPreferences); unresolvedDecisions = copy(unresolvedDecisions); }
    }
    public record StackDecision(String decisionId, String category, String selected, List<String> alternatives,
                                List<String> reasons, List<String> constraintsSatisfied, List<String> tradeoffs,
                                double confidence, String approvalStatus) {
        public StackDecision { alternatives = copy(alternatives); reasons = copy(reasons); constraintsSatisfied = copy(constraintsSatisfied); tradeoffs = copy(tradeoffs); }
    }
    public record ModuleMapping(String mappingId, List<String> sourceModuleIds, String targetModuleId, String mappingMode,
                                String targetKind, List<String> responsibilities, List<String> dependencies,
                                String migrationMode, String risk, List<String> rationale) {
        public ModuleMapping { sourceModuleIds = copy(sourceModuleIds); responsibilities = copy(responsibilities); dependencies = copy(dependencies); rationale = copy(rationale); }
    }
    public record NamingMapping(String sourceDeclarationId, String targetDeclarationId, String sourceQualifiedName,
                               String targetQualifiedName, String targetFile, String mappingReason,
                               String collisionStatus, List<String> obligationIds) {
        public NamingMapping { obligationIds = copy(obligationIds); }
    }
    public record TargetProject(String targetProjectId, String kind, String language, String buildTool,
                                List<String> sourceRoots, List<String> testRoots, List<String> resourceRoots,
                                List<String> projectReferences, List<String> packageDependencies,
                                Map<String,String> compilerOptions, List<List<String>> buildCommands,
                                List<List<String>> testDiscoveryCommands) {
        public TargetProject { sourceRoots=copy(sourceRoots); testRoots=copy(testRoots); resourceRoots=copy(resourceRoots); projectReferences=copy(projectReferences); packageDependencies=copy(packageDependencies); compilerOptions=map(compilerOptions); buildCommands=copy(buildCommands); testDiscoveryCommands=copy(testDiscoveryCommands); }
    }
    public record Placeholder(String placeholderId, String declarationId, String mode, String reason,
                              boolean blocking, List<String> obligationIds) { public Placeholder { obligationIds = copy(obligationIds); } }
    public record TargetMapping(String mappingId, List<String> sourceEntities, List<String> uirEntities,
                                List<String> targetEntities, String mappingKind, String generationId,
                                double confidence, boolean placeholder, String synthesizedReason) {
        public TargetMapping { sourceEntities=copy(sourceEntities); uirEntities=copy(uirEntities); targetEntities=copy(targetEntities); }
    }
    public record GeneratedFile(String path, String contentHash, String kind, List<String> targetDeclarationIds,
                                boolean provisional, boolean generated) { public GeneratedFile { targetDeclarationIds=copy(targetDeclarationIds); } }
    public record BuildBaseline(Status buildModelLoad, Status dependencyResolution, Status syntaxCompile,
                                Status testDiscovery, String environmentRef, List<String> errors,
                                List<String> artifacts) { public BuildBaseline { errors=copy(errors); artifacts=copy(artifacts); }
        public static BuildBaseline notRun(String reason) { return new BuildBaseline(Status.NOT_RUN,Status.NOT_RUN,Status.NOT_RUN,Status.NOT_RUN,null,List.of(reason),List.of()); }
    }
    @FunctionalInterface public interface BaselineRunner { BuildBaseline validate(java.nio.file.Path repository, Plan plan); }
    public record Coverage(double moduleMappingCoverage, double targetProjectGenerationRate, double targetTypeSkeletonRate,
                           double sourceTargetMappingCoverage, double publicApiSkeletonRate, double typeSignatureCoverage,
                           double asyncContractCoverage, double exceptionContractCoverage, double unresolvedTargetTypeRate) {}
    public record Manifest(String targetRepositoryId, String sourceSnapshotId, String uirRunId, String targetProfileId,
                           String generationId, List<TargetProject> projects, List<GeneratedFile> createdFiles,
                           List<String> provisionalFiles, List<String> unresolvedDependencies,
                           List<String> namingCollisions, int placeholderCount, Coverage coverage, Instant createdAt) {
        public Manifest { projects=copy(projects); createdFiles=copy(createdFiles); provisionalFiles=copy(provisionalFiles); unresolvedDependencies=copy(unresolvedDependencies); namingCollisions=copy(namingCollisions); }
    }
    public record Plan(TargetProfile profile, List<StackDecision> stackDecisions, List<ModuleMapping> modules,
                       List<NamingMapping> names, List<TargetProject> projects, List<Placeholder> placeholders,
                       List<TargetMapping> mappings, String generationId) {
        public Plan { stackDecisions=copy(stackDecisions); modules=copy(modules); names=copy(names); projects=copy(projects); placeholders=copy(placeholders); mappings=copy(mappings); }
    }
    public record ModuleGate(String targetModuleId, String gate, boolean eligibleForBodyGeneration,
                             boolean eligibleForParallelGeneration, List<String> restrictions) { public ModuleGate { restrictions=copy(restrictions); } }
    public record ConformanceReport(int batch, String status, String targetRepositoryId, List<ModuleGate> modules,
                                    Coverage coverage, BuildBaseline buildBaseline, List<String> openObligations,
                                    List<String> blockingErrors, boolean eligibleForBatch5) {
        public ConformanceReport { modules=copy(modules); openObligations=copy(openObligations); blockingErrors=copy(blockingErrors); }
    }
    public record Result(Plan plan, Manifest manifest, BuildBaseline baseline, ConformanceReport conformance) {}
    private static <T> List<T> copy(List<T> value) { return value == null ? List.of() : List.copyOf(value); }
    private static <K,V> Map<K,V> map(Map<K,V> value) { return value == null ? Map.of() : Map.copyOf(value); }
}
