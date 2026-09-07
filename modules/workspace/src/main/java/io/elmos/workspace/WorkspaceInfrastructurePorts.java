package io.elmos.workspace;

import java.io.InputStream;

public final class WorkspaceInfrastructurePorts {
    private WorkspaceInfrastructurePorts() {}
    public interface ApprovedImageRegistry { void requireApproved(String sandboxProfile, String imageDigest); }

    /**
     * Immutable database facts required to authorize and verify one workspace snapshot archive.
     *
     * <p>The digest alone is not an authorization boundary. The authenticated organization,
     * repository, migration run and snapshot identity travel with the reference all the way to
     * the artifact reader so byte-identical archives cannot be reused across resource contexts.
     */
    public record SnapshotArtifact(
            String organizationId,
            String repositoryId,
            String migrationRunId,
            String snapshotId,
            String reference,
            String sha256,
            long sizeBytes
    ) {
        public SnapshotArtifact {
            organizationId = requireResourceId(organizationId, "organizationId");
            repositoryId = requireResourceId(repositoryId, "repositoryId");
            migrationRunId = requireResourceId(migrationRunId, "migrationRunId");
            snapshotId = requireResourceId(snapshotId, "snapshotId");
            if (reference == null || reference.isBlank() || reference.length() > 1024
                    || reference.chars().anyMatch(Character::isISOControl)) {
                throw new IllegalArgumentException("snapshot artifact reference is invalid");
            }
            if (sha256 == null || !sha256.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("snapshot artifact digest is invalid");
            }
            if (sizeBytes <= 0) {
                throw new IllegalArgumentException("snapshot artifact size is invalid");
            }
        }

        private static String requireResourceId(String value, String field) {
            if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
                throw new IllegalArgumentException(field + " is invalid");
            }
            return value;
        }
    }

    public interface SnapshotArtifactResolver {
        SnapshotArtifact resolve(WorkspaceModels.WorkspaceRequest request);
    }

    /** Read-only port: workspace-service never receives snapshot artifact write authority. */
    public interface SnapshotArtifactReader {
        InputStream open(SnapshotArtifact artifact);
    }

    public interface SnapshotVolumeMaterializer {
        void materialize(WorkspaceModels.WorkspaceRequest request,
                         String snapshotVolumeName,
                         String workspaceVolumeName);
    }
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
