package io.elmos.intake;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/** Stable, language-neutral Batch 1 contracts. No record contains source-file contents. */
public final class IntakeModels {
    private IntakeModels() {}

    public enum SourceType { GIT, UPLOAD }
    public enum Language { JAVA, PYTHON, CSHARP, JAVASCRIPT, TYPESCRIPT, OTHER }
    public enum FileCategory {
        PRODUCTION_SOURCE, TEST_SOURCE, GENERATED_SOURCE, BUILD_CONFIG, RUNTIME_CONFIG,
        DATABASE_MIGRATION, API_CONTRACT, SCHEMA, RESOURCE, DOCUMENTATION, CI_CONFIG,
        CONTAINER_CONFIG, BINARY, VENDORED_CODE, UNKNOWN
    }
    public enum Status { PASSED, FAILED, NOT_RUN, INCONCLUSIVE, BLOCKED }

    public record ScanLimits(int maxFiles, long maxTotalBytes, long maxBytesPerFile) {
        public ScanLimits {
            if (maxFiles < 1 || maxTotalBytes < 1 || maxBytesPerFile < 1) throw new IllegalArgumentException("scan limits must be positive");
        }
        public static ScanLimits defaults() { return new ScanLimits(250_000, 2L * 1024 * 1024 * 1024, 8L * 1024 * 1024); }
    }

    public record IntakeRequest(SourceType sourceType, String repositoryRemote, String branch,
                                String commitSha, String uploadId, String targetLanguage,
                                String targetFramework, ScanLimits limits) {
        public IntakeRequest { limits = limits == null ? ScanLimits.defaults() : limits; }
    }

    public record FileEntry(String path, long bytes, String sha256, FileCategory category,
                            boolean generated, boolean vendored, boolean binary,
                            boolean secretLike, boolean excludedFromModel) {}
    public record Repository(String remote, String branch, String commit) {}
    public record RepositorySnapshot(String schemaVersion, String snapshotId, SourceType sourceType,
                                     Repository repository, String uploadId, int fileCount,
                                     long totalBytes, List<FileEntry> files, List<String> submodules,
                                     Instant createdAt, String integrityHash) {
        public RepositorySnapshot { files = List.copyOf(files); submodules = List.copyOf(submodules); }
    }

    public record Evidence(String path, String reason) {}
    public record LanguageFingerprint(Language language, int fileCount, long logicalLines,
                                      double confidence, List<Evidence> evidence) {
        public LanguageFingerprint { evidence = List.copyOf(evidence); }
    }
    public record FrameworkFingerprint(String name, String version, double confidence, List<Evidence> evidence) {
        public FrameworkFingerprint { evidence = List.copyOf(evidence); }
    }
    public record ProjectCandidate(String projectId, String path, Language language, String buildTool,
                                   List<String> sourceRoots, List<String> testRoots,
                                   List<String> generatedRoots, List<Evidence> evidence) {
        public ProjectCandidate {
            sourceRoots = List.copyOf(sourceRoots); testRoots = List.copyOf(testRoots);
            generatedRoots = List.copyOf(generatedRoots); evidence = List.copyOf(evidence);
        }
    }
    public record ProjectFingerprint(String schemaVersion, String snapshotId, Language primaryLanguage,
                                     List<LanguageFingerprint> languages, List<String> buildSystems,
                                     List<FrameworkFingerprint> frameworks, List<ProjectCandidate> modules,
                                     List<String> unresolved) {
        public ProjectFingerprint {
            languages = List.copyOf(languages); buildSystems = List.copyOf(buildSystems);
            frameworks = List.copyOf(frameworks); modules = List.copyOf(modules);
            unresolved = List.copyOf(unresolved);
        }
    }

    public record Dependency(String ecosystem, String name, String version, String scope,
                             String source, boolean direct, boolean resolved) {}
    public record BuildCommand(List<String> argv, boolean networkRequired, boolean mayExecuteCode) {
        public BuildCommand { argv = List.copyOf(argv); }
    }
    public record BuildProject(String projectId, Language language, String buildTool,
                               List<String> sourceRoots, List<String> testRoots,
                               List<String> resourceRoots, List<String> generatedRoots,
                               List<Dependency> dependencies, List<String> plugins,
                               List<String> repositories, Map<String, String> compilerOptions,
                               List<BuildCommand> testCommands, List<BuildCommand> buildCommands,
                               List<String> unresolved) {
        public BuildProject {
            sourceRoots = List.copyOf(sourceRoots); testRoots = List.copyOf(testRoots);
            resourceRoots = List.copyOf(resourceRoots); generatedRoots = List.copyOf(generatedRoots);
            dependencies = List.copyOf(dependencies); plugins = List.copyOf(plugins);
            repositories = List.copyOf(repositories); compilerOptions = Map.copyOf(compilerOptions);
            testCommands = List.copyOf(testCommands); buildCommands = List.copyOf(buildCommands);
            unresolved = List.copyOf(unresolved);
        }
    }
    public record BuildModel(String schemaVersion, String snapshotId, List<BuildProject> projects,
                             List<String> privateDependencySources, List<String> unresolved) {
        public BuildModel {
            projects = List.copyOf(projects); privateDependencySources = List.copyOf(privateDependencySources);
            unresolved = List.copyOf(unresolved);
        }
    }

    public record InventorySummary(long productionLoc, long testLoc, long generatedLoc, long binaryBytes) {}
    public record SourceInventory(String schemaVersion, String snapshotId, List<FileEntry> files,
                                  InventorySummary summary, List<String> riskFlags) {
        public SourceInventory { files = List.copyOf(files); riskFlags = List.copyOf(riskFlags); }
    }
    public record GraphNode(String id, String type, String name, Map<String, String> attributes) {
        public GraphNode { attributes = Map.copyOf(attributes); }
    }
    public record GraphEdge(String from, String to, String type, String evidencePath, String evidenceLocation) {}
    public record DependencyGraph(String schemaVersion, String snapshotId, List<GraphNode> nodes,
                                  List<GraphEdge> edges, List<List<String>> stronglyConnectedComponents,
                                  List<String> migrationCandidates, List<String> highCouplingModules,
                                  List<String> unresolved) {
        public DependencyGraph {
            nodes = List.copyOf(nodes); edges = List.copyOf(edges);
            stronglyConnectedComponents = stronglyConnectedComponents.stream().map(List::copyOf).toList();
            migrationCandidates = List.copyOf(migrationCandidates); highCouplingModules = List.copyOf(highCouplingModules);
            unresolved = List.copyOf(unresolved);
        }
    }

    public record SandboxPolicy(int policyVersion, boolean networkEnabled, boolean rootReadOnly,
                                boolean workspaceWrite, double cpuLimit, int memoryMb, int processLimit,
                                int timeoutSeconds, boolean secretsMounted, boolean privileged,
                                boolean hostDockerSocket, boolean lifecycleScriptsEnabled,
                                List<String> dependencyAllowlist) {
        public SandboxPolicy { dependencyAllowlist = List.copyOf(dependencyAllowlist); }
        public static SandboxPolicy defaults() {
            return new SandboxPolicy(1, false, true, true, 2.0, 4096, 256, 1200,
                    false, false, false, false, List.of());
        }
    }
    public record BaselineStep(String name, Status status, Integer exitCode, long durationMs,
                               String stdoutArtifact, String stderrArtifact, String errorClass,
                               List<String> failedTests) {
        public BaselineStep { failedTests = List.copyOf(failedTests); }
    }
    public record BaselineReport(String schemaVersion, String snapshotId, String environmentRef,
                                 Status dependencyRestore, Status buildStatus, Status testStatus,
                                 int totalTests, int passedTests, int failedTests, int skippedTests,
                                 Double coverage, List<BaselineStep> steps, List<String> existingFailures,
                                 List<String> unresolved) {
        public BaselineReport {
            steps = List.copyOf(steps); existingFailures = List.copyOf(existingFailures);
            unresolved = List.copyOf(unresolved);
        }
        public static BaselineReport notRun(String snapshotId, String reason) {
            return new BaselineReport("1.0", snapshotId, null, Status.NOT_RUN, Status.NOT_RUN, Status.NOT_RUN,
                    0, 0, 0, 0, null, List.of(), List.of(), List.of(reason));
        }
    }

    public record ReadinessScore(int total, int reproducibleBuild, int testCompleteness,
                                 int dependencyResolution, int typeInformation, int moduleDecoupling,
                                 int frameworkSupport, int dynamicFeatureRisk) {}
    public record MigrationTarget(String language, String languageVersion, String framework) {}
    public record MigrationManifest(String schemaVersion, String migrationId, String snapshotId,
                                    Language primaryLanguage, List<String> frameworks,
                                    List<String> buildSystems, MigrationTarget target,
                                    List<String> projectIds, List<String> sourceRoots,
                                    List<String> testRoots, Map<String, Boolean> exclusions,
                                    BaselineReport baseline, List<String> risks, List<String> unresolved,
                                    String sandboxPolicyRef, ReadinessScore readiness, Status gateStatus) {
        public MigrationManifest {
            frameworks = List.copyOf(frameworks); buildSystems = List.copyOf(buildSystems);
            projectIds = List.copyOf(projectIds); sourceRoots = List.copyOf(sourceRoots);
            testRoots = List.copyOf(testRoots); exclusions = Map.copyOf(exclusions);
            risks = List.copyOf(risks); unresolved = List.copyOf(unresolved);
        }
    }

    public record IntakeBundle(RepositorySnapshot snapshot, ProjectFingerprint fingerprint,
                               BuildModel buildModel, SourceInventory inventory,
                               DependencyGraph dependencyGraph, SandboxPolicy sandboxPolicy,
                               BaselineReport baseline, MigrationManifest migrationManifest) {}
}
