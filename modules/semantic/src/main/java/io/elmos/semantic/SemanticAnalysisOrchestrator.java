package io.elmos.semantic;

import io.elmos.intake.IntakeModels.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.*;

import static io.elmos.semantic.PspModels.*;

public final class SemanticAnalysisOrchestrator {
    private final Map<String, SemanticAdapter> adapters; private final Clock clock;

    public SemanticAnalysisOrchestrator(List<SemanticAdapter> adapters, Clock clock) {
        Map<String, SemanticAdapter> indexed = new HashMap<>();
        for (SemanticAdapter adapter : adapters) if (indexed.put(adapter.descriptor().language(), adapter) != null)
            throw new IllegalArgumentException("only one primary semantic adapter is allowed per language");
        this.adapters = Map.copyOf(indexed); this.clock = Objects.requireNonNull(clock);
    }

    public SemanticDataset analyze(Path requestedRoot, IntakeBundle intake, AnalysisProfile profile,
                                   ResourceBudget budget, Map<String, String> configuration) {
        Objects.requireNonNull(intake); Objects.requireNonNull(profile); Objects.requireNonNull(budget);
        if (!intake.snapshot().snapshotId().equals(intake.migrationManifest().snapshotId())) throw new IllegalArgumentException("INTAKE_SNAPSHOT_MISMATCH");
        if (intake.migrationManifest().gateStatus() != Status.PASSED) throw new IllegalStateException("BATCH_1_GATE_NOT_PASSED");
        Path root = secureRoot(requestedRoot); verifySnapshotFiles(root, intake.snapshot());
        Map<BuildProject, List<FileEntry>> routed = routeFiles(intake, profile.includeTests());
        List<AdapterDescriptor> descriptors = routed.keySet().stream().map(project -> requireAdapter(language(project.language())).descriptor())
                .distinct().sorted(Comparator.comparing(AdapterDescriptor::language)).toList();
        String configHash = configurationHash(profile, budget, configuration, descriptors, intake);
        String runId = SemanticIds.id("semrun", intake.snapshot().snapshotId(), configHash);
        List<EntityEnvelope> entities = new ArrayList<>(); List<String> artifacts = new ArrayList<>(); boolean partial = false;
        for (BuildProject project : topologicalOrder(routed.keySet(), intake.dependencyGraph())) {
            SemanticAdapter adapter = requireAdapter(language(project.language()));
            try {
                SemanticAdapter.AdapterResult result = adapter.analyze(new SemanticAdapter.AdapterRequest(root, intake.snapshot().snapshotId(), runId,
                        project, routed.getOrDefault(project, List.of()), profile, budget, configuration));
                validateAdapterResult(adapter, result, runId, intake.snapshot().snapshotId(), project.projectId());
                entities.addAll(result.entities()); partial |= result.partial(); artifacts.add("adapter:" + adapter.descriptor().adapter());
            } catch (RuntimeException error) {
                partial = true; entities.add(adapterFailure(adapter, project, intake.snapshot().snapshotId(), runId, profile, error));
            }
        }
        entities.sort(Comparator.comparing(EntityEnvelope::entityKind).thenComparing(EntityEnvelope::entityId));
        CoverageMetrics metrics = SemanticConformanceValidator.coverage(entities);
        List<String> diagnostics = entities.stream().filter(entity -> entity.entityKind().equals("diagnostic")).map(EntityEnvelope::entityId).toList();
        boolean blocking = entities.stream().filter(entity -> entity.payload() instanceof DiagnosticPayload).map(entity -> (DiagnosticPayload) entity.payload()).anyMatch(DiagnosticPayload::blocking);
        String status = blocking ? "completed_with_restrictions" : partial || !diagnostics.isEmpty() ? "completed_with_warnings" : "completed";
        SemanticRunManifest manifest = new SemanticRunManifest(runId, intake.snapshot().snapshotId(), status, descriptors,
                routed.keySet().stream().map(BuildProject::projectId).sorted().toList(), artifacts.stream().distinct().sorted().toList(), metrics,
                diagnostics, configHash, clock.instant());
        return new SemanticDataset(manifest, entities);
    }

    private SemanticAdapter requireAdapter(String language) { SemanticAdapter adapter = adapters.get(language); if (adapter == null) throw new IllegalStateException("SEMANTIC_ADAPTER_MISSING:" + language); return adapter; }
    private static Map<BuildProject, List<FileEntry>> routeFiles(IntakeBundle intake, boolean includeTests) {
        Map<BuildProject, List<FileEntry>> result = new LinkedHashMap<>(); for (BuildProject project : intake.buildModel().projects()) result.put(project, new ArrayList<>());
        for (FileEntry file : intake.snapshot().files()) {
            if (file.generated() || file.vendored() || file.binary() || file.secretLike() || (!includeTests && file.category() == FileCategory.TEST_SOURCE)) continue;
            String language = fileLanguage(file.path()); if (language.equals("other")) continue;
            List<BuildProject> candidates = result.keySet().stream().filter(project -> compatible(project.language(), language)).filter(project -> belongs(file.path(), project)).toList();
            candidates.stream().max(Comparator.comparingInt(project -> specificity(file.path(), project))).ifPresent(project -> result.get(project).add(file));
        }
        result.values().forEach(files -> files.sort(Comparator.comparing(FileEntry::path))); return result;
    }
    private static boolean belongs(String path, BuildProject project) { List<String> roots = new ArrayList<>(); roots.addAll(project.sourceRoots()); roots.addAll(project.testRoots()); if (roots.isEmpty()) return path.startsWith(projectBase(project.projectId())); return roots.stream().anyMatch(root -> root.equals(".") || path.equals(root) || path.startsWith(root + "/")); }
    private static int specificity(String path, BuildProject project) { return java.util.stream.Stream.concat(project.sourceRoots().stream(), project.testRoots().stream()).filter(root -> root.equals(".") || path.startsWith(root)).mapToInt(String::length).max().orElse(projectBase(project.projectId()).length()); }
    private static String projectBase(String id) { String[] parts = id.split(":", 3); return parts.length > 1 && !parts[1].equals(".") ? parts[1] + "/" : ""; }
    private static boolean compatible(Language project, String language) { return language(project).equals(language) || project == Language.TYPESCRIPT && language.equals("javascript"); }
    private static String language(Language language) { return switch (language) { case JAVA -> "java"; case PYTHON -> "python"; case CSHARP -> "csharp"; case JAVASCRIPT -> "javascript"; case TYPESCRIPT -> "typescript"; default -> "other"; }; }
    private static String fileLanguage(String path) { String lower = path.toLowerCase(Locale.ROOT); if (lower.endsWith(".java")) return "java"; if (lower.endsWith(".py") || lower.endsWith(".pyi")) return "python"; if (lower.endsWith(".cs")) return "csharp"; if (lower.endsWith(".ts") || lower.endsWith(".tsx")) return "typescript"; if (lower.endsWith(".js") || lower.endsWith(".jsx") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return "javascript"; return "other"; }
    private static List<BuildProject> topologicalOrder(Collection<BuildProject> projects, DependencyGraph graph) {
        Map<String, BuildProject> selected = new TreeMap<>();
        projects.forEach(project -> selected.put(project.projectId(), project));
        Map<String, String> graphNodeToProject = new HashMap<>();
        graph.nodes().stream().filter(node -> node.type().equals("Project") && selected.containsKey(node.name()))
                .forEach(node -> graphNodeToProject.put(node.id(), node.name()));
        Map<String, Set<String>> dependents = new HashMap<>(); Map<String, Integer> indegree = new HashMap<>();
        selected.keySet().forEach(id -> { dependents.put(id, new TreeSet<>()); indegree.put(id, 0); });
        for (GraphEdge edge : graph.edges()) {
            if (!edge.type().equals("DEPENDS_ON")) continue;
            String dependent = graphNodeToProject.get(edge.from()), dependency = graphNodeToProject.get(edge.to());
            if (dependent != null && dependency != null && !dependent.equals(dependency) && dependents.get(dependency).add(dependent))
                indegree.merge(dependent, 1, Integer::sum);
        }
        PriorityQueue<String> ready = new PriorityQueue<>();
        indegree.forEach((id, count) -> { if (count == 0) ready.add(id); });
        List<BuildProject> ordered = new ArrayList<>();
        while (!ready.isEmpty()) {
            String id = ready.remove(); ordered.add(selected.get(id));
            for (String dependent : dependents.get(id)) if (indegree.merge(dependent, -1, Integer::sum) == 0) ready.add(dependent);
        }
        // Batch 1 records SCCs. Preserve deterministic progress inside cycles instead of inventing an order.
        Set<String> emitted = new HashSet<>(); ordered.forEach(project -> emitted.add(project.projectId()));
        selected.values().stream().filter(project -> !emitted.contains(project.projectId())).forEach(ordered::add);
        return List.copyOf(ordered);
    }
    private static void validateAdapterResult(SemanticAdapter adapter, SemanticAdapter.AdapterResult result, String runId, String snapshotId, String projectId) {
        if (!adapter.descriptor().equals(result.descriptor())) throw new SecurityException("ADAPTER_DESCRIPTOR_MISMATCH");
        for (EntityEnvelope entity : result.entities()) if (!entity.semanticRunId().equals(runId) || !entity.snapshotId().equals(snapshotId) || !entity.projectId().equals(projectId))
            throw new SecurityException("ADAPTER_ENTITY_PROVENANCE_MISMATCH:" + entity.entityId());
    }
    private static EntityEnvelope adapterFailure(SemanticAdapter adapter, BuildProject project, String snapshotId, String runId, AnalysisProfile profile, RuntimeException error) {
        String id = SemanticIds.diagnostic(adapter.descriptor().provider(), "internal-adapter-error", "file:none", 0, error.getClass().getSimpleName());
        DiagnosticPayload payload = new DiagnosticPayload(id, "internal-adapter-error", "blocking", "file:none", null,
                error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage(), adapter.descriptor().provider(), error.getClass().getSimpleName(),
                List.of("semantic-analysis-incomplete"), "inspect-adapter-log", 1.0, true);
        Provenance provenance = new Provenance(adapter.descriptor().adapter(), adapter.descriptor().adapterVersion(), adapter.descriptor().provider(), adapter.descriptor().providerVersion(),
                "adapter-boundary", profile.name(), "unresolved", 1.0, List.of(), java.time.Instant.EPOCH);
        return new EntityEnvelope(PROTOCOL_VERSION, "diagnostic", id, snapshotId, runId, project.projectId(), adapter.descriptor().language(), payload, provenance);
    }
    private static String configurationHash(AnalysisProfile profile, ResourceBudget budget, Map<String,String> configuration, List<AdapterDescriptor> descriptors, IntakeBundle intake) {
        String canonical = profile + "\0" + budget + "\0" + new TreeMap<>(configuration) + "\0" + descriptors + "\0" + intake.buildModel().projects() + "\0" + intake.dependencyGraph().edges();
        return SemanticIds.hashText(canonical);
    }
    private static void verifySnapshotFiles(Path root, RepositorySnapshot snapshot) {
        for (FileEntry file : snapshot.files()) {
            Path path = root.resolve(file.path()).normalize(); if (!path.startsWith(root)) throw new SecurityException("SOURCE_PATH_ESCAPE");
            if (!Files.isRegularFile(path, java.nio.file.LinkOption.NOFOLLOW_LINKS)) throw new IllegalArgumentException("SNAPSHOT_FILE_MISSING:" + file.path());
            try { String actual = hashBytes(Files.readAllBytes(path)); if (!actual.equals(file.sha256())) throw new IllegalArgumentException("SNAPSHOT_FILE_HASH_MISMATCH:" + file.path());
            } catch (java.io.IOException error) { throw new IllegalArgumentException("SNAPSHOT_FILE_READ_FAILED:" + file.path(), error); }
        }
    }
    private static String hashBytes(byte[] bytes) { try { return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes)); } catch (Exception error) { throw new IllegalStateException(error); } }
    private static Path secureRoot(Path requested) { try { Path root = requested.toAbsolutePath().normalize(); if (Files.isSymbolicLink(root)) throw new SecurityException("repository root must not be a symlink"); return root.toRealPath(java.nio.file.LinkOption.NOFOLLOW_LINKS); } catch (java.io.IOException error) { throw new IllegalArgumentException("REPOSITORY_ROOT_UNAVAILABLE", error); } }
}
