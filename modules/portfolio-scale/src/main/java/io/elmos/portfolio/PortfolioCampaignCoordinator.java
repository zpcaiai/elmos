package io.elmos.portfolio;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;

import static io.elmos.portfolio.PortfolioScaleModels.*;

public final class PortfolioCampaignCoordinator {
    public CampaignDecision plan(Campaign campaign) {
        List<String> blockers = new ArrayList<>();
        Set<String> missingApprovals = new HashSet<>(campaign.requiredApprovals());
        missingApprovals.removeAll(campaign.grantedApprovals());
        if (!missingApprovals.isEmpty()) blockers.add("MISSING_APPROVALS:" + missingApprovals.stream().sorted().toList());
        long estimatedCost = campaign.workUnits().stream().mapToLong(unit -> Math.max(1, (unit.estimatedLoc() + 999) / 1000)).sum();
        if (estimatedCost > campaign.budgetUnits()) blockers.add("BUDGET_EXCEEDED:" + estimatedCost + ">" + campaign.budgetUnits());

        Map<String, WorkUnit> units = new HashMap<>();
        campaign.workUnits().forEach(unit -> {
            if (units.put(unit.id(), unit) != null) throw new IllegalArgumentException("duplicate work unit: " + unit.id());
        });
        List<List<String>> waves = waves(units, campaign.maximumParallel());
        return new CampaignDecision(blockers.isEmpty() ? CampaignStatus.READY : CampaignStatus.BLOCKED,
                waves, estimatedCost, blockers);
    }

    private static List<List<String>> waves(Map<String, WorkUnit> units, int maximumParallel) {
        Map<String, Integer> indegree = new HashMap<>();
        Map<String, List<String>> consumers = new HashMap<>();
        for (WorkUnit unit : units.values()) {
            indegree.put(unit.id(), unit.dependsOn().size());
            for (String dependency : unit.dependsOn()) {
                if (!units.containsKey(dependency)) throw new IllegalArgumentException("unknown campaign dependency: " + dependency);
                consumers.computeIfAbsent(dependency, ignored -> new ArrayList<>()).add(unit.id());
            }
        }
        PriorityQueue<String> ready = new PriorityQueue<>();
        indegree.forEach((id, degree) -> { if (degree == 0) ready.add(id); });
        List<List<String>> waves = new ArrayList<>();
        int visited = 0;
        while (!ready.isEmpty()) {
            List<String> wave = new ArrayList<>();
            while (!ready.isEmpty() && wave.size() < maximumParallel) wave.add(ready.remove());
            waves.add(List.copyOf(wave));
            visited += wave.size();
            List<String> newlyReady = new ArrayList<>();
            for (String completed : wave) for (String consumer : consumers.getOrDefault(completed, List.of())) {
                int remaining = indegree.compute(consumer, (ignored, value) -> value - 1);
                if (remaining == 0) newlyReady.add(consumer);
            }
            ready.addAll(newlyReady);
        }
        if (visited != units.size()) throw new IllegalArgumentException("campaign dependency graph contains a cycle");
        return waves;
    }
}
