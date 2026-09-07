package io.elmos.workspace;

import java.util.List;
import java.util.Map;
import java.util.Set;

public final class WorkspaceSecurityPolicy {
    public static final String SANDBOX_USER = "10001:10001";
    private static final Set<String> COMMANDS = Set.of("java", "javac", "mvn", "./mvnw", "git", "tar", "unzip", "sha256sum", "find", "grep", "sed", "cat", "test");
    public record Mount(String volumeRole, String containerPath, boolean readOnly) {}
    public record ContainerSpec(String imageDigest, String user, boolean privileged, boolean readOnlyRoot,
                                boolean hostNetwork, boolean hostPid, boolean hostIpc, List<String> capDrop,
                                List<String> securityOptions, long memoryBytes, long memorySwapBytes,
                                long nanoCpus, long pidsLimit, int diskMb, boolean internalNetwork,
                                Map<String, String> tmpfs, List<Mount> mounts, Map<String, String> labels) {}

    public ContainerSpec specification(WorkspaceModels.WorkspaceRequest request) {
        var limits = request.resources();
        Map<String, String> labels = Map.of(
                "elmos.managed", "true", "elmos.organization_id", request.organizationId(),
                "elmos.workspace_id", request.workspaceId(), "elmos.migration_run_id", request.migrationRunId(),
                "elmos.retention", "ephemeral");
        return new ContainerSpec(request.imageDigest(), SANDBOX_USER, false, true, false, false, false,
                List.of("ALL"), List.of("no-new-privileges:true"), limits.memoryBytes(), limits.memoryBytes(),
                limits.nanoCpus(), limits.pids(), limits.diskMb(), true,
                Map.of("/tmp", "rw,noexec,nosuid,size=256m", "/run", "rw,noexec,nosuid,size=64m", "/run/secrets", "rw,noexec,nosuid,size=16m,mode=0700"),
                List.of(new Mount("snapshot", "/input/snapshot", true), new Mount("workspace", "/workspace", false),
                        new Mount("artifacts", "/artifacts", false), new Mount("maven-cache", "/home/elmos/.m2", false)), labels);
    }

    public void validateCommand(WorkspaceModels.WorkspaceCommand command) {
        if (!COMMANDS.contains(command.argv().getFirst())) throw new SecurityException("command is not in the workspace allowlist");
        if (command.argv().getFirst().equals("git") && command.argv().size() > 1
                && Set.of("credential", "remote", "config", "push", "commit", "merge", "rebase", "tag", "branch", "checkout", "switch")
                .contains(command.argv().get(1))) throw new SecurityException("mutating git command is forbidden in a customer-code workspace");
    }
}
