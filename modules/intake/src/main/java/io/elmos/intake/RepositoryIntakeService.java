package io.elmos.intake;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.*;

import static io.elmos.intake.IntakeModels.*;

/** Orchestrates Batch 1 only. Target-language source generation is deliberately absent. */
public final class RepositoryIntakeService {
    private final Clock clock; private final BaselineRunner baselineRunner;

    public RepositoryIntakeService(Clock clock, BaselineRunner baselineRunner) {
        this.clock = Objects.requireNonNull(clock); this.baselineRunner = Objects.requireNonNull(baselineRunner);
    }

    public IntakeBundle analyze(Path requestedRoot, IntakeRequest request) {
        Path root = secureRoot(requestedRoot);
        RepositorySnapshot snapshot = new SecureRepositoryScanner(clock).scan(root, request);
        BuildModel buildModel = new BuildManifestInspector().inspect(root, snapshot);
        ProjectFingerprint fingerprint = fingerprint(root, snapshot, buildModel);
        SourceInventory inventory = inventory(root, snapshot);
        DependencyGraph graph = graph(snapshot, buildModel);
        SandboxPolicy policy = SandboxPolicy.defaults();
        BaselineReport baseline = Objects.requireNonNull(baselineRunner.run(snapshot, buildModel, policy), "baseline report");
        if (!snapshot.snapshotId().equals(baseline.snapshotId())) throw new IllegalArgumentException("BASELINE_SNAPSHOT_MISMATCH");
        MigrationManifest manifest = manifest(request, snapshot, fingerprint, buildModel, inventory, graph, baseline);
        return new IntakeBundle(snapshot, fingerprint, buildModel, inventory, graph, policy, baseline, manifest);
    }

    private static ProjectFingerprint fingerprint(Path root, RepositorySnapshot snapshot, BuildModel buildModel) {
        EnumMap<Language, Integer> counts = new EnumMap<>(Language.class); EnumMap<Language, Long> loc = new EnumMap<>(Language.class);
        EnumMap<Language, List<Evidence>> evidence = new EnumMap<>(Language.class); List<String> unresolved = new ArrayList<>(buildModel.unresolved());
        for (FileEntry file : snapshot.files()) {
            Language language = language(file.path()); if (language == Language.OTHER || file.generated() || file.vendored() || file.binary() || file.secretLike()) continue;
            counts.merge(language, 1, Integer::sum); loc.merge(language, logicalLines(root.resolve(file.path())), Long::sum);
            evidence.computeIfAbsent(language, ignored -> new ArrayList<>());
            if (evidence.get(language).size() < 5) evidence.get(language).add(new Evidence(file.path(), "source-file"));
        }
        List<LanguageFingerprint> languages = counts.entrySet().stream().map(entry -> new LanguageFingerprint(entry.getKey(), entry.getValue(),
                loc.getOrDefault(entry.getKey(), 0L), confidence(entry.getKey(), buildModel), evidence.getOrDefault(entry.getKey(), List.of())))
                .sorted(Comparator.comparingLong(LanguageFingerprint::logicalLines).reversed().thenComparing(value -> value.language().name())).toList();
        Language primary = languages.isEmpty() ? Language.OTHER : languages.getFirst().language();
        List<String> buildSystems = buildModel.projects().stream().map(BuildProject::buildTool).distinct().sorted().toList();
        List<FrameworkFingerprint> frameworks = frameworks(buildModel);
        List<ProjectCandidate> modules = buildModel.projects().stream().map(project -> new ProjectCandidate(project.projectId(), projectBase(project.projectId()),
                project.language(), project.buildTool(), project.sourceRoots(), project.testRoots(), project.generatedRoots(),
                List.of(new Evidence(project.projectId(), "parsed-build-manifest")))).toList();
        if (snapshot.files().stream().anyMatch(file -> file.path().endsWith(".ipynb"))) unresolved.add("notebooks are inventoried as resources and are not treated as the Python application root");
        if (languages.size() > 1) unresolved.add("mixed-language boundaries require Batch 2 semantic adapters");
        return new ProjectFingerprint("1.0", snapshot.snapshotId(), primary, languages, buildSystems, frameworks, modules,
                unresolved.stream().distinct().sorted().toList());
    }

    private static SourceInventory inventory(Path root, RepositorySnapshot snapshot) {
        long production = 0, tests = 0, generated = 0, binaries = 0; List<String> risks = new ArrayList<>();
        for (FileEntry file : snapshot.files()) {
            long lines = file.binary() || file.secretLike() ? 0 : logicalLines(root.resolve(file.path()));
            if (file.category() == FileCategory.PRODUCTION_SOURCE) production += lines;
            if (file.category() == FileCategory.TEST_SOURCE) tests += lines;
            if (file.generated()) generated += lines;
            if (file.binary()) binaries += file.bytes();
            if (file.secretLike()) risks.add("secret-like file excluded from model context:" + file.path());
            if (file.bytes() > 1024 * 1024) risks.add("large-file:" + file.path());
        }
        return new SourceInventory("1.0", snapshot.snapshotId(), snapshot.files(), new InventorySummary(production, tests, generated, binaries),
                risks.stream().distinct().sorted().toList());
    }

    private static DependencyGraph graph(RepositorySnapshot snapshot, BuildModel buildModel) {
        List<GraphNode> nodes = new ArrayList<>(); List<GraphEdge> edges = new ArrayList<>();
        String repositoryId = "repository:" + snapshot.snapshotId();
        nodes.add(new GraphNode(repositoryId, "Repository", snapshot.snapshotId(), Map.of()));
        Map<String, String> projectNodes = new TreeMap<>();
        for (BuildProject project : buildModel.projects()) {
            String id = "project:" + SecureRepositoryScanner.sha256(project.projectId().getBytes(StandardCharsets.UTF_8)).substring(0, 16);
            projectNodes.put(project.projectId(), id); nodes.add(new GraphNode(id, "Project", project.projectId(), Map.of("buildTool", project.buildTool(), "language", project.language().name())));
            edges.add(new GraphEdge(repositoryId, id, "CONTAINS", project.projectId(), null));
        }
        Map<String, String> externalNodes = new TreeMap<>();
        for (BuildProject project : buildModel.projects()) for (Dependency dependency : project.dependencies()) {
            String from = projectNodes.get(project.projectId()); String internal = findInternal(dependency, buildModel.projects(), projectNodes);
            if (internal != null) edges.add(new GraphEdge(from, internal, "DEPENDS_ON", dependency.source(), dependency.name()));
            else {
                String key = dependency.ecosystem() + ":" + dependency.name();
                String id = externalNodes.computeIfAbsent(key, ignored -> "external:" + SecureRepositoryScanner.sha256(key.getBytes(StandardCharsets.UTF_8)).substring(0, 16));
                edges.add(new GraphEdge(from, id, "DEPENDS_ON", dependency.source(), dependency.name()));
            }
        }
        externalNodes.forEach((name, id) -> nodes.add(new GraphNode(id, "ExternalPackage", name, Map.of())));
        nodes.sort(Comparator.comparing(GraphNode::id)); edges.sort(Comparator.comparing(GraphEdge::from).thenComparing(GraphEdge::to).thenComparing(GraphEdge::evidencePath));
        List<List<String>> components = stronglyConnected(projectNodes.values(), edges);
        Map<String, Integer> degree = new HashMap<>(); for (GraphEdge edge : edges) { degree.merge(edge.from(), 1, Integer::sum); degree.merge(edge.to(), 1, Integer::sum); }
        List<String> high = degree.entrySet().stream().filter(entry -> entry.getValue() >= 10).map(Map.Entry::getKey).sorted().toList();
        List<String> candidates = projectNodes.values().stream().filter(id -> components.stream().noneMatch(component -> component.size() > 1 && component.contains(id)))
                .sorted(Comparator.comparingInt(id -> degree.getOrDefault(id, 0))).limit(10).toList();
        List<String> unresolved = new ArrayList<>(buildModel.unresolved());
        unresolved.add("source-level IMPORTS, REFERENCES and CALLS edges are deferred to Batch 2 parsers; no targets are guessed");
        return new DependencyGraph("1.0", snapshot.snapshotId(), nodes, edges, components, candidates, high,
                unresolved.stream().distinct().sorted().toList());
    }

    private static MigrationManifest manifest(IntakeRequest request, RepositorySnapshot snapshot, ProjectFingerprint fingerprint,
                                              BuildModel build, SourceInventory inventory, DependencyGraph graph, BaselineReport baseline) {
        int reproducible = baseline.buildStatus() == Status.PASSED ? 20 : 0;
        int tests = baseline.testStatus() == Status.PASSED && baseline.totalTests() > 0 ? 20 : baseline.totalTests() > 0 ? 8 : 0;
        long dependencyCount = build.projects().stream().mapToLong(project -> project.dependencies().size()).sum();
        long resolved = build.projects().stream().flatMap(project -> project.dependencies().stream()).filter(Dependency::resolved).count();
        int dependency = dependencyCount == 0 ? 5 : (int) Math.round(15d * resolved / dependencyCount);
        int type = (int) Math.round(15d * fingerprint.languages().stream().filter(value -> value.language() == Language.JAVA || value.language() == Language.CSHARP || value.language() == Language.TYPESCRIPT).mapToLong(LanguageFingerprint::fileCount).sum()
                / Math.max(1, fingerprint.languages().stream().mapToLong(LanguageFingerprint::fileCount).sum()));
        int decoupling = graph.stronglyConnectedComponents().stream().anyMatch(component -> component.size() > 1) ? 3 : 10;
        int framework = fingerprint.frameworks().isEmpty() ? 0 : 10;
        boolean dynamic = fingerprint.languages().stream().anyMatch(value -> value.language() == Language.PYTHON || value.language() == Language.JAVASCRIPT);
        int dynamicRisk = dynamic ? 5 : 10; int total = reproducible + tests + dependency + type + decoupling + framework + dynamicRisk;
        ReadinessScore readiness = new ReadinessScore(total, reproducible, tests, dependency, type, decoupling, framework, dynamicRisk);
        List<String> risks = new ArrayList<>(inventory.riskFlags()); List<String> unresolved = new ArrayList<>();
        unresolved.addAll(fingerprint.unresolved()); unresolved.addAll(build.unresolved()); unresolved.addAll(graph.unresolved()); unresolved.addAll(baseline.unresolved());
        Status gate = baseline.buildStatus() == Status.NOT_RUN || baseline.testStatus() == Status.NOT_RUN || build.projects().isEmpty() ? Status.BLOCKED : Status.PASSED;
        return new MigrationManifest("1.0", "migration-" + snapshot.integrityHash().substring(0, 16), snapshot.snapshotId(), fingerprint.primaryLanguage(),
                fingerprint.frameworks().stream().map(FrameworkFingerprint::name).toList(), fingerprint.buildSystems(),
                new MigrationTarget(request.targetLanguage(), "latest-supported", request.targetFramework()),
                build.projects().stream().map(BuildProject::projectId).toList(), build.projects().stream().flatMap(project -> project.sourceRoots().stream()).distinct().toList(),
                build.projects().stream().flatMap(project -> project.testRoots().stream()).distinct().toList(), Map.of("generatedCode", true, "vendoredCode", true, "binaries", true),
                baseline, risks.stream().distinct().sorted().toList(), unresolved.stream().distinct().sorted().toList(), "sandbox-policy.yaml", readiness, gate);
    }

    private static List<FrameworkFingerprint> frameworks(BuildModel model) {
        Map<String, List<Evidence>> found = new TreeMap<>(); Map<String, String> versions = new HashMap<>();
        for (BuildProject project : model.projects()) for (Dependency dependency : project.dependencies()) {
            String lower = dependency.name().toLowerCase(Locale.ROOT); String name = null;
            if (lower.contains("spring-boot")) name = "spring-boot";
            else if (lower.equals("fastapi") || lower.endsWith(":fastapi")) name = "fastapi";
            else if (lower.contains("microsoft.aspnetcore")) name = "aspnet-core";
            else if (lower.equals("@nestjs/core")) name = "nestjs";
            else if (lower.equals("express")) name = "express";
            if (name != null) { found.computeIfAbsent(name, ignored -> new ArrayList<>()).add(new Evidence(dependency.source(), "declared-dependency:" + dependency.name())); versions.putIfAbsent(name, dependency.version()); }
        }
        return found.entrySet().stream().map(entry -> new FrameworkFingerprint(entry.getKey(), versions.get(entry.getKey()), 0.95, entry.getValue())).toList();
    }
    private static double confidence(Language language, BuildModel model) { return model.projects().stream().anyMatch(project -> project.language() == language) ? 0.99 : 0.85; }
    private static Language language(String path) { String lower = path.toLowerCase(Locale.ROOT); if (lower.endsWith(".java")) return Language.JAVA; if (lower.endsWith(".py")) return Language.PYTHON; if (lower.endsWith(".cs")) return Language.CSHARP; if (lower.endsWith(".ts") || lower.endsWith(".tsx")) return Language.TYPESCRIPT; if (lower.endsWith(".js") || lower.endsWith(".jsx") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return Language.JAVASCRIPT; return Language.OTHER; }
    private static long logicalLines(Path file) { try { if (!Files.isRegularFile(file)) return 0; return Files.readAllLines(file, StandardCharsets.UTF_8).stream().map(String::strip).filter(line -> !line.isBlank() && !line.startsWith("//") && !line.startsWith("#") && !line.startsWith("/*") && !line.startsWith("*")).count(); } catch (IOException | RuntimeException ignored) { return 0; } }
    private static String projectBase(String projectId) { String[] parts = projectId.split(":", 3); return parts.length > 1 ? parts[1] : "."; }
    private static String findInternal(Dependency dependency, List<BuildProject> projects, Map<String, String> nodes) { String artifact = dependency.name().contains(":") ? dependency.name().substring(dependency.name().lastIndexOf(':') + 1) : dependency.name(); return projects.stream().filter(project -> project.projectId().endsWith(":" + artifact) || project.projectId().endsWith(":" + artifact + ".csproj")).map(project -> nodes.get(project.projectId())).findFirst().orElse(null); }

    private static List<List<String>> stronglyConnected(Collection<String> projectIds, List<GraphEdge> edges) {
        Set<String> projects = Set.copyOf(projectIds); Map<String, List<String>> adjacency = new HashMap<>();
        for (String id : projects) adjacency.put(id, new ArrayList<>()); for (GraphEdge edge : edges) if (projects.contains(edge.from()) && projects.contains(edge.to())) adjacency.get(edge.from()).add(edge.to());
        List<List<String>> result = new ArrayList<>(); Map<String,Integer> index = new HashMap<>(), low = new HashMap<>(); Deque<String> stack = new ArrayDeque<>(); Set<String> active = new HashSet<>(); int[] next = {0};
        for (String id : projects.stream().sorted().toList()) if (!index.containsKey(id)) tarjan(id, adjacency, index, low, stack, active, next, result);
        result.replaceAll(component -> component.stream().sorted().toList()); result.sort(Comparator.comparing(component -> component.getFirst())); return result;
    }
    private static void tarjan(String node, Map<String,List<String>> adjacency, Map<String,Integer> index, Map<String,Integer> low, Deque<String> stack, Set<String> active, int[] next, List<List<String>> result) {
        index.put(node, next[0]); low.put(node, next[0]++); stack.push(node); active.add(node);
        for (String target : adjacency.getOrDefault(node, List.of())) { if (!index.containsKey(target)) { tarjan(target, adjacency, index, low, stack, active, next, result); low.put(node, Math.min(low.get(node), low.get(target))); } else if (active.contains(target)) low.put(node, Math.min(low.get(node), index.get(target))); }
        if (low.get(node).equals(index.get(node))) { List<String> component = new ArrayList<>(); String current; do { current = stack.pop(); active.remove(current); component.add(current); } while (!current.equals(node)); result.add(component); }
    }
    private static Path secureRoot(Path requested) { try { Path absolute = requested.toAbsolutePath().normalize(); if (Files.isSymbolicLink(absolute)) throw new SecurityException("repository root must not be a symlink"); return absolute.toRealPath(java.nio.file.LinkOption.NOFOLLOW_LINKS); } catch (IOException error) { throw new IllegalArgumentException("REPOSITORY_ROOT_UNAVAILABLE", error); } }
}
