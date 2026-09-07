package io.elmos.workspace;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class WorkspaceReaper {
    public record ExpiredWorkspace(String workspaceId, String organizationId, Instant expiresAt) {}
    public record RuntimeResource(String externalId, String resourceType, Map<String,String> labels) {
        public RuntimeResource { labels = Map.copyOf(labels); }
    }
    public interface Registry { List<ExpiredWorkspace> expired(Instant now); }
    public interface RuntimeInventory { List<RuntimeResource> resources(String workspaceId); }
    public interface CleanupScheduler { void request(String workspaceId, String idempotencyKey, WorkspaceModels.TerminationReason reason); }
    private final Registry registry; private final RuntimeInventory runtime; private final CleanupScheduler cleanup;
    public WorkspaceReaper(Registry registry, RuntimeInventory runtime, CleanupScheduler cleanup) {
        this.registry = Objects.requireNonNull(registry); this.runtime = Objects.requireNonNull(runtime); this.cleanup = Objects.requireNonNull(cleanup);
    }

    public int reap(Instant now) {
        int scheduled = 0;
        for (ExpiredWorkspace workspace : registry.expired(now)) {
            List<RuntimeResource> resources = runtime.resources(workspace.workspaceId());
            boolean ownershipProved = !resources.isEmpty() && resources.stream().allMatch(resource ->
                    "true".equals(resource.labels().get("elmos.managed"))
                            && workspace.workspaceId().equals(resource.labels().get("elmos.workspace_id"))
                            && workspace.organizationId().equals(resource.labels().get("elmos.organization_id")));
            if (!ownershipProved) continue;
            cleanup.request(workspace.workspaceId(), "reaper:" + workspace.workspaceId() + ":" + workspace.expiresAt().toEpochMilli(),
                    WorkspaceModels.TerminationReason.ORPHAN_REAPED);
            scheduled++;
        }
        return scheduled;
    }
}
