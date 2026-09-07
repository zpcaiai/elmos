package io.elmos.workspace;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class WorkspaceModels {
    private WorkspaceModels() {}
    public enum State { REQUESTED, PROVISIONING, STARTING, READY, EXECUTING, FINALIZING, TERMINATING,
        TERMINATED, TIMED_OUT, POLICY_VIOLATION, QUARANTINED, FAILED }
    public enum TerminationReason { COMPLETED, COMMAND_FAILED, BUILD_FAILED, TIMEOUT, USER_CANCELLED,
        WORKER_SHUTDOWN, POLICY_VIOLATION, SECRET_LEAK_SUSPECTED, HOST_RESOURCE_PRESSURE, ORPHAN_REAPED }

    public record ResourceLimits(double cpu, int memoryMb, int pids, int diskMb, Duration workspaceTimeout) {
        public ResourceLimits {
            if (cpu < .25 || cpu > 16 || memoryMb < 512 || memoryMb > 65536 || pids < 32 || pids > 4096
                    || diskMb < 1024 || diskMb > 102400) throw new IllegalArgumentException("workspace resources are outside policy");
            if (workspaceTimeout == null || workspaceTimeout.compareTo(Duration.ofMinutes(1)) < 0
                    || workspaceTimeout.compareTo(Duration.ofHours(4)) > 0) throw new IllegalArgumentException("workspace timeout is outside policy");
        }
        public long memoryBytes() { return memoryMb * 1024L * 1024L; }
        public long nanoCpus() { return Math.round(cpu * 1_000_000_000L); }
    }

    public record WorkspaceRequest(String workspaceId, String organizationId, String migrationRunId,
                                   String snapshotId, String sandboxProfile, String imageDigest,
                                   ResourceLimits resources, String networkPolicyId, String correlationId) {
        public WorkspaceRequest {
            requireId(workspaceId, "workspaceId",64); requireId(organizationId, "organizationId",64); requireId(migrationRunId, "migrationRunId",64);
            requireId(snapshotId, "snapshotId",64); requireId(sandboxProfile, "sandboxProfile",64); requireId(networkPolicyId, "networkPolicyId",64);
            requireId(correlationId, "correlationId",128); Objects.requireNonNull(resources);
            if (imageDigest == null || !imageDigest.matches("sha256:[0-9a-f]{64}")) throw new IllegalArgumentException("approved image digest is required");
        }
    }

    public record WorkspaceCommand(String commandId, List<String> argv, String workingDirectory,
                                   Map<String, String> safeEnvironment, Duration timeout) {
        public WorkspaceCommand {
            requireId(commandId, "commandId",64); argv = List.copyOf(argv); safeEnvironment = Map.copyOf(safeEnvironment);
            if (argv.isEmpty() || argv.stream().anyMatch(value -> value == null || value.isBlank() || value.indexOf('\0') >= 0)) throw new IllegalArgumentException("argv must contain safe individual arguments");
            if (workingDirectory == null || !(workingDirectory.equals("/workspace") || workingDirectory.startsWith("/workspace/"))) throw new SecurityException("working directory must stay below /workspace");
            if (timeout == null || timeout.isNegative() || timeout.isZero() || timeout.compareTo(Duration.ofHours(1)) > 0) throw new IllegalArgumentException("command timeout is outside policy");
            if (safeEnvironment.keySet().stream().anyMatch(key -> key.matches("(?i).*(token|secret|password|credential|authorization).*"))) throw new SecurityException("secret-shaped environment variable is forbidden");
        }
    }

    public record CommandResult(String commandId, String argvSha256, String workingDirectory, Instant startedAt,
                                Instant finishedAt, Integer exitCode, String terminationReason,
                                String stdoutArtifactRef, String stderrArtifactRef, boolean outputTruncated,
                                String outputSha256, List<String> policyViolations) {}

    private static void require(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    private static void requireId(String value,String name,int max){require(value,name);if(value.length()>max||!value.matches("[A-Za-z0-9._:-]+"))throw new IllegalArgumentException(name+" is invalid");}
}
