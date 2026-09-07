package io.elmos.repair;

import io.elmos.repair.RepairModels.*;

import java.time.Instant;
import java.util.*;

public final class RepairTaskBuilder {
    public RepairTask build(FailureCluster cluster, RepairScope scope, Risk risk, int maximumAttempts, Instant createdAt) {
        String intent = switch (cluster.category()) {
            case MISSING_SYMBOL, COMPILATION, TYPE_MISMATCH -> "Restore compilation for " + cluster.module();
            case TEST_FAILURE -> "Repair the clustered failing test behavior for " + cluster.module();
            case DEPENDENCY -> "Restore deterministic dependency resolution for " + cluster.module();
            default -> "Resolve one normalized " + cluster.category() + " failure cluster for " + cluster.module();
        };
        List<String> forbidden = List.of("do-not-disable-tests", "do-not-weaken-assertions", "do-not-add-network-egress",
                "do-not-access-secrets", "do-not-commit-or-push", "do-not-run-validation-in-editing-workspace");
        List<ValidationRequirement> validators = List.of(
                new ValidationRequirement("fresh-workspace-build", true, true),
                new ValidationRequirement("targeted-tests", true, true),
                new ValidationRequirement("patch-policy", true, true));
        String contextSeed = cluster.fingerprint() + "\n" + new TreeSet<>(scope.allowedPathPrefixes()) + "\n" + intent;
        String contextHash = FailureNormalizer.hash(contextSeed);
        return new RepairTask("1.0", "repair-" + contextHash.substring(0, 24), cluster.clusterId(), intent, scope,
                forbidden, validators, risk, contextHash, maximumAttempts, createdAt);
    }

    public ContextPack pack(RepairTask task, List<ContextItem> candidates, int maximumBytes) {
        if (maximumBytes < 1) throw new IllegalArgumentException("context limit must be positive");
        List<ContextItem> ordered = candidates.stream().filter(item -> !item.secret())
                .sorted(Comparator.comparingInt(ContextItem::priority).reversed().thenComparing(ContextItem::reference)).toList();
        List<ContextItem> selected = new ArrayList<>(); int total = 0;
        for (ContextItem item : ordered) {
            if (item.bytes() > maximumBytes - total) continue;
            selected.add(item); total += item.bytes();
        }
        boolean truncated = candidates.stream().anyMatch(ContextItem::secret) || selected.size() < candidates.size();
        boolean untrusted = selected.stream().anyMatch(ContextItem::repositoryControlled);
        String hash = FailureNormalizer.hash(task.taskId() + "\n" + selected.stream().map(value -> value.reference() + "@" + value.contentHash()).toList());
        return new ContextPack("1.0", task.taskId(), selected, total, truncated, untrusted, hash);
    }
}
