package io.elmos.workspace;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class WorkspaceFinalizer {
    public enum Status { COMPLETED, COMPLETED_WITH_WARNINGS, ALREADY_COMPLETED, FAILED_RETRYABLE }
    public record Step(String name, boolean succeeded, String detail) {}
    public record Result(Status status, List<Step> steps) { public Result { steps = List.copyOf(steps); } }
    public interface FinalizationStore {
        boolean tryStart(String workspaceId, String idempotencyKey);
        void complete(String workspaceId, String idempotencyKey, Result result);
        void retryable(String workspaceId, String idempotencyKey, Result result);
    }
    public interface ArtifactCollector { void sealAndUpload(String workspaceId); }
    public interface SecretCleanup { void revokeAndRemoveAll(String workspaceId); }
    public interface RuntimeCleanup {
        void stopExecution(String workspaceId); void removeContainer(String workspaceId);
        void removeVolumes(String workspaceId); void removeNetwork(String workspaceId); void verifyNoResidualResources(String workspaceId);
    }

    private final FinalizationStore store; private final ArtifactCollector artifacts;
    private final SecretCleanup secrets; private final RuntimeCleanup runtime;
    public WorkspaceFinalizer(FinalizationStore store, ArtifactCollector artifacts, SecretCleanup secrets, RuntimeCleanup runtime) {
        this.store = Objects.requireNonNull(store); this.artifacts = Objects.requireNonNull(artifacts);
        this.secrets = Objects.requireNonNull(secrets); this.runtime = Objects.requireNonNull(runtime);
    }

    public Result finalizeWorkspace(String workspaceId, String idempotencyKey, WorkspaceModels.TerminationReason reason) {
        Objects.requireNonNull(reason);
        if (!store.tryStart(workspaceId, idempotencyKey)) return new Result(Status.ALREADY_COMPLETED, List.of());
        List<Step> steps = new ArrayList<>();
        attempt(steps, "STOP_EXECUTION", () -> runtime.stopExecution(workspaceId));
        attempt(steps, "SEAL_ARTIFACTS", () -> artifacts.sealAndUpload(workspaceId));
        attempt(steps, "REVOKE_SECRETS", () -> secrets.revokeAndRemoveAll(workspaceId));
        attempt(steps, "REMOVE_CONTAINER", () -> runtime.removeContainer(workspaceId));
        attempt(steps, "REMOVE_VOLUMES", () -> runtime.removeVolumes(workspaceId));
        attempt(steps, "REMOVE_NETWORK", () -> runtime.removeNetwork(workspaceId));
        attempt(steps, "VERIFY_RESIDUALS", () -> runtime.verifyNoResidualResources(workspaceId));
        boolean securityComplete = succeeded(steps, "REVOKE_SECRETS") && succeeded(steps, "REMOVE_CONTAINER")
                && succeeded(steps, "REMOVE_VOLUMES") && succeeded(steps, "REMOVE_NETWORK") && succeeded(steps, "VERIFY_RESIDUALS");
        Status status = securityComplete ? (steps.stream().allMatch(Step::succeeded) ? Status.COMPLETED : Status.COMPLETED_WITH_WARNINGS) : Status.FAILED_RETRYABLE;
        Result result = new Result(status, steps);
        if (securityComplete) store.complete(workspaceId, idempotencyKey, result); else store.retryable(workspaceId, idempotencyKey, result);
        return result;
    }

    private static boolean succeeded(List<Step> steps, String name) { return steps.stream().filter(step -> step.name().equals(name)).findFirst().map(Step::succeeded).orElse(false); }
    private static void attempt(List<Step> steps, String name, Runnable action) {
        try { action.run(); steps.add(new Step(name, true, "ok")); }
        catch (RuntimeException failure) { steps.add(new Step(name, false, failure.getClass().getSimpleName())); }
    }
}
