package io.elmos.dependency;

import io.elmos.intake.IntakeModels;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

import static io.elmos.dependency.DependencyMigrationModels.*;

final class DependencyInventoryNormalizer {
    List<ResolvedGraph> normalize(IntakeModels.BuildModel model, ResolvedGraphProvider provider) {
        if (model == null) return List.of();
        return model.projects().stream().sorted(Comparator.comparing(IntakeModels.BuildProject::projectId))
                .map(project -> graph(project, provider)).toList();
    }

    private ResolvedGraph graph(IntakeModels.BuildProject project, ResolvedGraphProvider provider) {
        List<NormalizedDependency> dependencies = project.dependencies().stream()
                .map(dependency -> normalize(project.projectId(), dependency))
                .sorted(Comparator.comparing(NormalizedDependency::dependencyId)).toList();
        GraphResolution resolution = provider.reconstruct(project, dependencies);
        List<String> issues = new ArrayList<>(project.unresolved());
        issues.addAll(resolution.issues());
        Set<String> nodeIds = dependencies.stream().map(NormalizedDependency::dependencyId).collect(Collectors.toSet());
        if (nodeIds.size() != dependencies.size()) issues.add("duplicate normalized dependency identity");
        resolution.edges().stream().filter(edge -> !nodeIds.contains(edge.fromDependencyId()) || !nodeIds.contains(edge.toDependencyId()))
                .forEach(edge -> issues.add("dangling resolved edge: "+edge.fromDependencyId()+" -> "+edge.toDependencyId()));
        boolean complete = resolution.complete() && resolution.resolverRef()!=null && !resolution.resolverRef().isBlank() && issues.isEmpty()
                && dependencies.stream().allMatch(dependency -> dependency.resolved() && dependency.issues().isEmpty());
        return new ResolvedGraph(project.projectId(), dependencies, resolution.edges(), complete,
                resolution.resolverRef(), issues.stream().distinct().sorted().toList());
    }

    private NormalizedDependency normalize(String projectId, IntakeModels.Dependency dependency) {
        String ecosystem = lower(dependency.ecosystem());
        String name = dependency.name() == null ? "" : dependency.name().trim();
        String version = dependency.version() == null ? "" : dependency.version().trim();
        String scope = lower(dependency.scope());
        List<String> issues = new ArrayList<>();
        if (ecosystem.isBlank()) issues.add("missing ecosystem");
        if (name.isBlank()) issues.add("missing dependency name");
        if (!dependency.resolved() || version.isBlank()) issues.add("missing exact resolved version");
        String coordinate = canonicalCoordinate(ecosystem, name);
        String id = DependencyMigrationIds.id("dep", projectId, ecosystem, name, version, scope, dependency.direct());
        return new NormalizedDependency(id, projectId, ecosystem, coordinate, name, version,
                dependency.resolved() ? version : null, scope, dependency.source(), dependency.direct(),
                dependency.resolved() && !version.isBlank(), issues);
    }

    private static String canonicalCoordinate(String ecosystem, String name) {
        return switch (ecosystem) {
            case "maven", "gradle", "nuget" -> name.replace(':', '/');
            default -> name;
        };
    }
    private static String lower(String value) { return value == null ? "" : value.trim().toLowerCase(Locale.ROOT); }
}
