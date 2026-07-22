package io.elmos.portfolio;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;

import static io.elmos.portfolio.PortfolioScaleModels.*;

public final class PortfolioPlanner {
    public PlanningResult plan(PortfolioSnapshot snapshot) {
        Map<String, WorkUnit> unitsByRepository = new LinkedHashMap<>();
        List<String> blockers = new ArrayList<>();
        List<RepositoryAsset> orderedRepositories = snapshot.repositories().stream()
                .sorted(Comparator.comparing(RepositoryAsset::id)).toList();
        for (RepositoryAsset repository : orderedRepositories) {
            if (repository.status() != RepositoryStatus.ACTIVE) {
                blockers.add("REPOSITORY_NOT_ACTIVE:" + repository.id() + ":" + repository.status());
                continue;
            }
            String unitId = stableId("wu", snapshot.digest() + "\0" + repository.id());
            unitsByRepository.put(repository.id(), new WorkUnit(unitId, repository.tenantId(), repository.owner(),
                    repository.id(), repository.regions(), repository.toolchains().stream().sorted().findFirst().orElseThrow(),
                    repository.loc(), repository.criticality(), List.of(),
                    snapshot.digest() + ":" + repository.id(), repository.evidenceRefs()));
        }
        for (UnreachableAsset unreachable : snapshot.unreachable()) {
            blockers.add("REPOSITORY_UNREACHABLE:" + unreachable.logicalKey() + ":" + unreachable.reason());
        }
        int visible = snapshot.repositories().size() + snapshot.unreachable().size();
        if (visible < snapshot.expectedRepositoryCount()) {
            blockers.add("INVENTORY_SCOPE_INCOMPLETE:" + (snapshot.expectedRepositoryCount() - visible));
        }

        Map<String, List<String>> dependencies = new HashMap<>();
        for (Dependency edge : snapshot.dependencies()) {
            WorkUnit consumer = unitsByRepository.get(edge.fromRepositoryId());
            WorkUnit provider = unitsByRepository.get(edge.toRepositoryId());
            if (consumer == null || provider == null) {
                blockers.add("DEPENDENCY_ENDPOINT_NOT_EXECUTABLE:" + edge.id());
                continue;
            }
            dependencies.computeIfAbsent(consumer.id(), ignored -> new ArrayList<>()).add(provider.id());
        }
        Map<String, WorkUnit> byId = new LinkedHashMap<>();
        for (WorkUnit unit : unitsByRepository.values()) {
            List<String> deps = dependencies.getOrDefault(unit.id(), List.of()).stream().distinct().sorted().toList();
            WorkUnit completed = new WorkUnit(unit.id(), unit.tenantId(), unit.owner(), unit.repositoryId(),
                    unit.regions(), unit.toolchain(), unit.estimatedLoc(), unit.criticality(), deps,
                    unit.partitionKey(), unit.evidenceRefs());
            byId.put(completed.id(), completed);
        }
        List<WorkUnit> ordered = topologicalOrder(byId);
        double coverage = snapshot.expectedRepositoryCount() == 0 ? 0
                : snapshot.repositories().size() / (double) snapshot.expectedRepositoryCount();
        return new PlanningResult(ordered, coverage, blockers);
    }

    static List<WorkUnit> topologicalOrder(Map<String, WorkUnit> units) {
        Map<String, Integer> indegree = new HashMap<>();
        Map<String, List<String>> consumers = new HashMap<>();
        for (WorkUnit unit : units.values()) {
            indegree.put(unit.id(), unit.dependsOn().size());
            for (String dependency : unit.dependsOn()) {
                if (!units.containsKey(dependency)) throw new IllegalArgumentException("unknown work-unit dependency: " + dependency);
                consumers.computeIfAbsent(dependency, ignored -> new ArrayList<>()).add(unit.id());
            }
        }
        PriorityQueue<String> ready = new PriorityQueue<>();
        indegree.forEach((id, degree) -> { if (degree == 0) ready.add(id); });
        List<WorkUnit> result = new ArrayList<>();
        while (!ready.isEmpty()) {
            String id = ready.remove();
            result.add(units.get(id));
            for (String consumer : consumers.getOrDefault(id, List.of())) {
                int remaining = indegree.compute(consumer, (ignored, value) -> value - 1);
                if (remaining == 0) ready.add(consumer);
            }
        }
        if (result.size() != units.size()) {
            Set<String> blocked = new HashSet<>(units.keySet());
            result.forEach(unit -> blocked.remove(unit.id()));
            throw new IllegalArgumentException("work-unit dependency cycle: " + blocked.stream().sorted().toList());
        }
        return result;
    }

    private static String stableId(String prefix, String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            return prefix + "-" + HexFormat.of().formatHex(digest).substring(0, 20);
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
