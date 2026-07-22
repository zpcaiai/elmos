package io.elmos.workspace;

import org.junit.jupiter.api.Test;
import java.util.HashSet;
import java.util.Set;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class WorkspaceFinalizerTest {
    @Test void artifactFailureDoesNotBlockSecurityCleanupAndRepeatIsNoOp() {
        Set<String> completed = new HashSet<>(); Set<String> actions = new HashSet<>();
        var store = new WorkspaceFinalizer.FinalizationStore() {
            public boolean tryStart(String workspace, String key) { return !completed.contains(workspace + key); }
            public void complete(String workspace, String key, WorkspaceFinalizer.Result result) { completed.add(workspace + key); }
            public void retryable(String workspace, String key, WorkspaceFinalizer.Result result) {}
        };
        var runtime = new WorkspaceFinalizer.RuntimeCleanup() {
            public void stopExecution(String id) { actions.add("stop"); } public void removeContainer(String id) { actions.add("container"); }
            public void removeVolumes(String id) { actions.add("volumes"); } public void removeNetwork(String id) { actions.add("network"); }
            public void verifyNoResidualResources(String id) { actions.add("verify"); }
        };
        var finalizer = new WorkspaceFinalizer(store, ignored -> { throw new IllegalStateException("object store down"); },
                ignored -> actions.add("secrets"), runtime);
        var result = finalizer.finalizeWorkspace("ws-1", "key-1", WorkspaceModels.TerminationReason.BUILD_FAILED);
        assertEquals(WorkspaceFinalizer.Status.COMPLETED_WITH_WARNINGS, result.status());
        assertTrue(actions.containsAll(Set.of("secrets", "container", "volumes", "network", "verify")));
        assertEquals(WorkspaceFinalizer.Status.ALREADY_COMPLETED, finalizer.finalizeWorkspace("ws-1", "key-1", WorkspaceModels.TerminationReason.BUILD_FAILED).status());
    }

    @Test void residualFailureIsRetryable() {
        var store = new WorkspaceFinalizer.FinalizationStore() {
            public boolean tryStart(String a,String b){return true;} public void complete(String a,String b,WorkspaceFinalizer.Result r){}
            public void retryable(String a,String b,WorkspaceFinalizer.Result r){}
        };
        var runtime = new WorkspaceFinalizer.RuntimeCleanup() {
            public void stopExecution(String id){} public void removeContainer(String id){} public void removeVolumes(String id){}
            public void removeNetwork(String id){} public void verifyNoResidualResources(String id){throw new IllegalStateException("still exists");}
        };
        var result = new WorkspaceFinalizer(store, ignored -> {}, ignored -> {}, runtime)
                .finalizeWorkspace("ws", "key", WorkspaceModels.TerminationReason.TIMEOUT);
        assertEquals(WorkspaceFinalizer.Status.FAILED_RETRYABLE, result.status());
    }

    @Test void reaperRequiresExactOwnershipLabels() {
        Instant expiry = Instant.parse("2026-07-20T00:00:00Z"); AtomicInteger requests = new AtomicInteger();
        var expired = List.of(new WorkspaceReaper.ExpiredWorkspace("ws-1", "org-1", expiry));
        var rejected = new WorkspaceReaper(now -> expired, id -> List.of(new WorkspaceReaper.RuntimeResource("c1", "container",
                Map.of("elmos.managed", "true", "elmos.workspace_id", "someone-else", "elmos.organization_id", "org-1"))),
                (workspace, key, reason) -> requests.incrementAndGet());
        assertEquals(0, rejected.reap(expiry.plusSeconds(1))); assertEquals(0, requests.get());
        var accepted = new WorkspaceReaper(now -> expired, id -> List.of(new WorkspaceReaper.RuntimeResource("c1", "container",
                Map.of("elmos.managed", "true", "elmos.workspace_id", "ws-1", "elmos.organization_id", "org-1"))),
                (workspace, key, reason) -> requests.incrementAndGet());
        assertEquals(1, accepted.reap(expiry.plusSeconds(1))); assertEquals(1, requests.get());
    }
}
