package io.elmos.workspace;

public final class WorkspaceInfrastructurePorts {
    private WorkspaceInfrastructurePorts() {}
    public interface ApprovedImageRegistry { void requireApproved(String sandboxProfile, String imageDigest); }
    public interface SnapshotVolumeMaterializer { void materialize(String snapshotId, String snapshotVolumeName, String workspaceVolumeName); }
    public interface CommandArtifactStore { String store(String workspaceId, String commandId, String stream, byte[] redactedBytes); }
    public interface CommandOutputSanitizer { byte[] sanitize(String workspaceId, byte[] rawBytes); }
    public record NetworkBinding(String bindingId, String proxyUrl, String proxyExternalId) {}
    public interface NetworkPolicyEnforcer {
        NetworkBinding apply(WorkspaceModels.WorkspaceRequest request, String dockerNetworkId, String dockerNetworkName);
        void collectAndRemove(String workspaceId);
    }
    public interface WorkspaceLifecycleStore {
        void requested(WorkspaceModels.WorkspaceRequest request);
        void ready(WorkspaceModels.WorkspaceRequest request, String containerId, String networkId, java.util.Map<String,String> volumes);
        void commandStarted(String workspaceId, WorkspaceModels.WorkspaceCommand command, String argvSha256, java.time.Instant startedAt);
        void commandFinished(String workspaceId, WorkspaceModels.CommandResult result);
        void terminated(String workspaceId, WorkspaceModels.TerminationReason reason, java.time.Instant at);
    }
    public interface WorkspaceSecretFinalizer { void revokeAll(String workspaceId); }
}
