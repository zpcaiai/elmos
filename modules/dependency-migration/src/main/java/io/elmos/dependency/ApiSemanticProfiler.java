package io.elmos.dependency;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import static io.elmos.dependency.DependencyMigrationModels.*;

final class ApiSemanticProfiler {
    List<ApiUsage> usages(List<ResolvedGraph> graphs, UsageEvidenceBundle evidence) {
        UsageEvidenceBundle safe = evidence == null ? new UsageEvidenceBundle(false, "missing", List.of(), List.of("usage evidence missing")) : evidence;
        Map<String,List<ApiUsageEvidence>> byKey = new LinkedHashMap<>();
        for (ApiUsageEvidence item : safe.usages()) byKey.computeIfAbsent(key(item.projectId(), item.ecosystem(), item.dependencyName()), ignored -> new ArrayList<>()).add(item);
        List<ApiUsage> result = new ArrayList<>();
        graphs.stream().flatMap(graph -> graph.nodes().stream()).sorted(Comparator.comparing(NormalizedDependency::dependencyId)).forEach(dependency -> {
            List<ApiUsageEvidence> matches = byKey.getOrDefault(key(dependency.projectId(), dependency.ecosystem(), dependency.name()), List.of());
            result.add(merge(dependency.dependencyId(), matches));
        });
        return List.copyOf(result);
    }

    List<SemanticProfile> profiles(List<ApiUsage> usages, UsageEvidenceBundle evidence) {
        boolean complete = evidence != null && evidence.complete() && evidence.unresolved().isEmpty();
        return usages.stream().map(usage -> {
            LinkedHashSet<String> apis = new LinkedHashSet<>();
            apis.addAll(usage.importedSymbols()); apis.addAll(usage.calledApis());
            apis.addAll(usage.constructedTypes()); apis.addAll(usage.annotations());
            List<String> unresolved = new ArrayList<>();
            if (!usage.observed() && !complete) unresolved.add("absence of usage is not proven by a complete analyzer run");
            if (usage.observed() && apis.isEmpty()) unresolved.add("usage observed without a resolvable API surface");
            if (usage.observedSemantics().values().stream().anyMatch(value -> value.startsWith("CONFLICT:"))) unresolved.add("conflicting observed semantics require review");
            double confidence = usage.observed() ? (unresolved.isEmpty() ? 1.0 : 0.5) : (complete ? 1.0 : 0.0);
            return new SemanticProfile(usage.dependencyId(), apis.stream().sorted().toList(),
                    usage.observedSemantics(), usage.sourceRefs(), confidence, unresolved);
        }).toList();
    }

    private ApiUsage merge(String dependencyId, List<ApiUsageEvidence> matches) {
        LinkedHashSet<String> imports=new LinkedHashSet<>(), calls=new LinkedHashSet<>(), types=new LinkedHashSet<>(), annotations=new LinkedHashSet<>(), refs=new LinkedHashSet<>();
        Map<String,String> semantics = new LinkedHashMap<>();
        matches.forEach(item -> { imports.addAll(item.importedSymbols()); calls.addAll(item.calledApis()); types.addAll(item.constructedTypes()); annotations.addAll(item.annotations()); refs.addAll(item.sourceRefs()); item.observedSemantics().forEach((key,value) -> semantics.merge(key, value, (left,right) -> left.equals(right) ? left : "CONFLICT:"+left+"|"+right)); });
        return new ApiUsage(dependencyId, sorted(imports), sorted(calls), sorted(types), sorted(annotations), sorted(refs), semantics, !matches.isEmpty());
    }
    private static List<String> sorted(LinkedHashSet<String> values) { return values.stream().sorted().toList(); }
    private static String key(String project, String ecosystem, String name) { return (project+"\u001f"+ecosystem+"\u001f"+name).toLowerCase(Locale.ROOT); }
}
