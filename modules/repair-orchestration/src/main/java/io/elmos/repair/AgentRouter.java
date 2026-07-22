package io.elmos.repair;

import io.elmos.repair.RepairModels.*;

import java.util.*;

public final class AgentRouter {
    public RoutingDecision route(RoutingRequest request, List<ProviderProfile> profiles) {
        List<String> considered = profiles.stream().map(ProviderProfile::providerId).sorted().toList();
        if (request.task().risk() == Risk.CRITICAL) return decision(request, RoutingOutcome.HUMAN_REQUIRED, null,
                List.of("CRITICAL_RISK_REQUIRES_HUMAN"), considered);
        if (request.estimatedCostMicros() > request.remainingBudgetMicros()) return decision(request, RoutingOutcome.BUDGET_BLOCKED, null,
                List.of("BUDGET_RESERVATION_UNAVAILABLE"), considered);
        Map<String,List<String>> rejected = new TreeMap<>();
        List<ProviderProfile> eligible = new ArrayList<>();
        for (ProviderProfile profile : profiles) {
            List<String> reasons = new ArrayList<>();
            if (!profile.enabled()) reasons.add("PROVIDER_DISABLED");
            if (!profile.allowedResidencies().contains(request.residency())) reasons.add("DATA_RESIDENCY_MISMATCH");
            if (request.privateRepository() && !profile.supportsPrivateRepositories()) reasons.add("PRIVATE_REPOSITORY_UNSUPPORTED");
            if (!profile.tools().containsAll(request.requiredTools())) reasons.add("REQUIRED_TOOL_UNAVAILABLE");
            if (!profile.allowedRisks().contains(request.task().risk())) reasons.add("RISK_NOT_ALLOWED");
            if (request.contextBytes() > profile.contextLimitBytes()) reasons.add("CONTEXT_LIMIT_EXCEEDED");
            if (request.estimatedCostMicros() > profile.maximumCostMicrosPerTask()) reasons.add("PROVIDER_COST_LIMIT_EXCEEDED");
            if (reasons.isEmpty()) eligible.add(profile); else rejected.put(profile.providerId(), reasons);
        }
        if (eligible.isEmpty()) {
            List<String> reasons = rejected.entrySet().stream().map(entry -> entry.getKey() + ":" + String.join(",", entry.getValue())).toList();
            return decision(request, RoutingOutcome.NO_ELIGIBLE_PROVIDER, null, reasons, considered);
        }
        ProviderProfile selected = eligible.stream().sorted(Comparator.comparingInt(ProviderProfile::priority)
                .thenComparingLong(ProviderProfile::maximumCostMicrosPerTask).thenComparing(ProviderProfile::providerId)).findFirst().orElseThrow();
        return decision(request, RoutingOutcome.ROUTED, selected.providerId(), List.of("ALL_HARD_FILTERS_PASSED"), considered);
    }

    private static RoutingDecision decision(RoutingRequest request, RoutingOutcome outcome, String provider,
                                            List<String> reasons, List<String> considered) {
        String seed = request.task().taskId() + "\n" + outcome + "\n" + provider + "\n" + reasons;
        return new RoutingDecision("route-" + FailureNormalizer.hash(seed).substring(0, 24), outcome, provider, reasons, considered);
    }
}
