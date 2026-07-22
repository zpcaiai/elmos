package io.elmos.workspaceservice;

import com.github.dockerjava.api.DockerClient;
import com.github.dockerjava.api.exception.NotFoundException;
import com.github.dockerjava.api.model.*;
import com.github.dockerjava.core.command.ExecStartResultCallback;
import io.elmos.workspace.*;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.*;
import java.util.concurrent.TimeUnit;

final class DockerWorkspaceProvisioner implements WorkspaceProvisioningPort {
    private static final int MAX_OUTPUT_BYTES = 10 * 1024 * 1024;
    private final DockerClient docker; private final WorkspaceSecurityPolicy policy;
    private final WorkspaceInfrastructurePorts.ApprovedImageRegistry images;
    private final WorkspaceInfrastructurePorts.SnapshotVolumeMaterializer snapshots;
    private final WorkspaceInfrastructurePorts.CommandOutputSanitizer sanitizer;
    private final WorkspaceInfrastructurePorts.CommandArtifactStore artifacts;
    private final WorkspaceInfrastructurePorts.NetworkPolicyEnforcer networkPolicies;
    private final WorkspaceInfrastructurePorts.WorkspaceLifecycleStore lifecycle;
    private final WorkspaceInfrastructurePorts.WorkspaceSecretFinalizer secrets; private final Clock clock;

    DockerWorkspaceProvisioner(DockerClient docker, WorkspaceSecurityPolicy policy,
            WorkspaceInfrastructurePorts.ApprovedImageRegistry images,
            WorkspaceInfrastructurePorts.SnapshotVolumeMaterializer snapshots,
            WorkspaceInfrastructurePorts.CommandOutputSanitizer sanitizer,
            WorkspaceInfrastructurePorts.CommandArtifactStore artifacts,
            WorkspaceInfrastructurePorts.NetworkPolicyEnforcer networkPolicies,
            WorkspaceInfrastructurePorts.WorkspaceLifecycleStore lifecycle,
            WorkspaceInfrastructurePorts.WorkspaceSecretFinalizer secrets, Clock clock) {
        this.docker = docker; this.policy = policy; this.images = images; this.snapshots = snapshots; this.sanitizer = sanitizer; this.artifacts = artifacts;
        this.networkPolicies = networkPolicies; this.lifecycle = lifecycle; this.secrets = secrets; this.clock = clock;
    }

    @Override public WorkspaceHandle provision(WorkspaceModels.WorkspaceRequest request) {
        requireRootless(); images.requireApproved(request.sandboxProfile(), request.imageDigest());
        var spec = policy.specification(request); String suffix = stableName(request.workspaceId()); lifecycle.requested(request);
        try {
            String snapshotVolume = createVolume("elmos-snapshot-" + suffix, labels(request, "snapshot"));
            String workspaceVolume = createVolume("elmos-workspace-" + suffix, labels(request, "workspace"));
            String artifactVolume = createVolume("elmos-artifacts-" + suffix, labels(request, "artifacts"));
            String cacheVolume = createVolume("elmos-m2-" + suffix, labels(request, "maven-cache"));
            snapshots.materialize(request.snapshotId(), snapshotVolume, workspaceVolume);
            String networkName = "elmos-net-" + suffix;
            String networkId = docker.createNetworkCmd().withName(networkName).withInternal(true).withLabels(labels(request, "network")).exec().getId();
            WorkspaceInfrastructurePorts.NetworkBinding binding = networkPolicies.apply(request, networkId, networkName);
            HostConfig host = HostConfig.newHostConfig().withPrivileged(false).withReadonlyRootfs(true)
                    .withCapDrop(Capability.ALL).withSecurityOpts(spec.securityOptions()).withMemory(spec.memoryBytes())
                    .withMemorySwap(spec.memorySwapBytes()).withNanoCPUs(spec.nanoCpus()).withPidsLimit(spec.pidsLimit())
                    .withDiskQuota((long) spec.diskMb() * 1024L * 1024L).withNetworkMode(networkName)
                    .withIpcMode("private").withTmpFs(spec.tmpfs()).withBinds(
                            new Bind(snapshotVolume, new Volume("/input/snapshot"), AccessMode.ro),
                            new Bind(workspaceVolume, new Volume("/workspace"), AccessMode.rw),
                            new Bind(artifactVolume, new Volume("/artifacts"), AccessMode.rw),
                            new Bind(cacheVolume, new Volume("/home/elmos/.m2"), AccessMode.rw));
            var created = docker.createContainerCmd(spec.imageDigest()).withName("elmos-ws-" + suffix).withUser(spec.user())
                    .withWorkingDir("/workspace").withEnv(proxyEnvironment(binding)).withHostConfig(host).withLabels(labels(request, "container")).exec();
            docker.startContainerCmd(created.getId()).exec();
            lifecycle.ready(request, created.getId(), networkId, Map.of("snapshot",snapshotVolume,"workspace",workspaceVolume,"artifacts",artifactVolume,"maven-cache",cacheVolume));
            return new WorkspaceHandle(request.workspaceId(), created.getId(), networkId);
        } catch (RuntimeException failure) {
            try { terminate(request.workspaceId(), WorkspaceModels.TerminationReason.COMMAND_FAILED); } catch (RuntimeException cleanupFailure) { failure.addSuppressed(cleanupFailure); }
            throw failure;
        }
    }

    @Override public WorkspaceModels.CommandResult execute(String workspaceId, WorkspaceModels.WorkspaceCommand command) {
        policy.validateCommand(command); String container = containerId(workspaceId);
        List<String> environment = command.safeEnvironment().entrySet().stream().sorted(Map.Entry.comparingByKey())
                .map(entry -> entry.getKey() + "=" + entry.getValue()).toList();
        var started = clock.instant(); String argvSha = digest(String.join("\0", command.argv()).getBytes(StandardCharsets.UTF_8));
        lifecycle.commandStarted(workspaceId, command, argvSha, started);
        var exec = docker.execCreateCmd(container).withAttachStdout(true).withAttachStderr(true).withPrivileged(false)
                .withWorkingDir(command.workingDirectory()).withEnv(environment).withCmd(command.argv().toArray(String[]::new)).exec();
        BoundedOutputStream stdout = new BoundedOutputStream(MAX_OUTPUT_BYTES), stderr = new BoundedOutputStream(MAX_OUTPUT_BYTES);
        boolean completed;
        try { completed = docker.execStartCmd(exec.getId()).exec(new ExecStartResultCallback(stdout, stderr))
                .awaitCompletion(command.timeout().toMillis(), TimeUnit.MILLISECONDS); }
        catch (InterruptedException exception) { Thread.currentThread().interrupt(); throw new IllegalStateException("workspace command interrupted", exception); }
        if (!completed) docker.killContainerCmd(container).exec();
        Long exit = completed ? docker.inspectExecCmd(exec.getId()).exec().getExitCodeLong() : null;
        byte[] out = sanitizer.sanitize(workspaceId, stdout.bytes()), err = sanitizer.sanitize(workspaceId, stderr.bytes());
        String outRef = artifacts.store(workspaceId, command.commandId(), "stdout", out);
        String errRef = artifacts.store(workspaceId, command.commandId(), "stderr", err);
        WorkspaceModels.CommandResult result = new WorkspaceModels.CommandResult(command.commandId(), argvSha,
                command.workingDirectory(), started, clock.instant(), exit == null ? null : exit.intValue(),
                completed ? (exit != null && exit == 0 ? "COMPLETED" : "COMMAND_FAILED") : "EXECUTION_TIMEOUT",
                outRef, errRef, stdout.truncated || stderr.truncated, digest(concat(out, err)), List.of());
        lifecycle.commandFinished(workspaceId, result); return result;
    }

    @Override public void terminate(String workspaceId) { terminate(workspaceId, WorkspaceModels.TerminationReason.COMPLETED); }
    private void terminate(String workspaceId, WorkspaceModels.TerminationReason reason) {
        RuntimeException failure = null;
        try { secrets.revokeAll(workspaceId); } catch (RuntimeException error) { failure = error; }
        try { networkPolicies.collectAndRemove(workspaceId); } catch (RuntimeException error) { failure = combine(failure,error); }
        for (var container : docker.listContainersCmd().withShowAll(true).withLabelFilter(Map.of("elmos.workspace_id", workspaceId, "elmos.managed", "true")).exec()) {
            try { docker.stopContainerCmd(container.getId()).withTimeout(10).exec(); } catch (NotFoundException ignored) {} catch (RuntimeException error) { failure = combine(failure,error); }
            try { docker.removeContainerCmd(container.getId()).withForce(true).exec(); } catch (NotFoundException ignored) {} catch (RuntimeException error) { failure = combine(failure,error); }
        }
        for (var volume : docker.listVolumesCmd().withFilter("label", List.of("elmos.workspace_id=" + workspaceId, "elmos.managed=true")).exec().getVolumes())
            try { docker.removeVolumeCmd(volume.getName()).exec(); } catch (NotFoundException ignored) {} catch (RuntimeException error) { failure = combine(failure,error); }
        for (var network : docker.listNetworksCmd().withFilter("label", List.of("elmos.workspace_id=" + workspaceId, "elmos.managed=true")).exec())
            try { docker.removeNetworkCmd(network.getId()).exec(); } catch (NotFoundException ignored) {} catch (RuntimeException error) { failure = combine(failure,error); }
        try { lifecycle.terminated(workspaceId, reason, clock.instant()); } catch (RuntimeException error) { failure = combine(failure,error); }
        if (failure != null) throw failure;
    }

    private void requireRootless() {
        List<String> options = docker.infoCmd().exec().getSecurityOptions();
        if (options == null || options.stream().map(String::toLowerCase).noneMatch(value -> value.contains("rootless")))
            throw new SecurityException("Docker daemon did not prove rootless mode");
    }
    private String createVolume(String name, Map<String,String> labels) { return docker.createVolumeCmd().withName(name).withLabels(labels).exec().getName(); }
    private String containerId(String workspaceId) {
        var containers = docker.listContainersCmd().withShowAll(true).withLabelFilter(Map.of("elmos.workspace_id", workspaceId, "elmos.managed", "true", "elmos.resource_role", "container")).exec();
        if (containers.size() != 1) throw new IllegalStateException("workspace container identity is missing or ambiguous"); return containers.getFirst().getId();
    }
    private static Map<String,String> labels(WorkspaceModels.WorkspaceRequest request, String role) { return Map.of(
            "elmos.managed", "true", "elmos.organization_id", request.organizationId(), "elmos.workspace_id", request.workspaceId(),
            "elmos.migration_run_id", request.migrationRunId(), "elmos.resource_role", role, "elmos.retention", "ephemeral"); }
    private static String stableName(String value) { return digest(value.getBytes(StandardCharsets.UTF_8)).substring(0, 24); }
    private static List<String> proxyEnvironment(WorkspaceInfrastructurePorts.NetworkBinding binding) {
        if (binding == null || binding.proxyUrl() == null || binding.proxyUrl().isBlank()) return List.of("NO_PROXY=localhost,127.0.0.1");
        return List.of("HTTPS_PROXY="+binding.proxyUrl(),"https_proxy="+binding.proxyUrl(),"HTTP_PROXY="+binding.proxyUrl(),"http_proxy="+binding.proxyUrl(),"NO_PROXY=localhost,127.0.0.1","no_proxy=localhost,127.0.0.1");
    }
    private static RuntimeException combine(RuntimeException first, RuntimeException next) { if (first == null) return next; first.addSuppressed(next); return first; }
    private static String digest(byte[] bytes) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); } catch (Exception e) { throw new IllegalStateException(e); } }
    private static byte[] concat(byte[] first, byte[] second) { byte[] joined = Arrays.copyOf(first, first.length + second.length); System.arraycopy(second, 0, joined, first.length, second.length); return joined; }
    private static final class BoundedOutputStream extends java.io.OutputStream {
        private final ByteArrayOutputStream delegate = new ByteArrayOutputStream(); private final int limit; private boolean truncated;
        private BoundedOutputStream(int limit) { this.limit = limit; }
        @Override public void write(int value) { if (delegate.size() < limit) delegate.write(value); else truncated = true; }
        @Override public void write(byte[] bytes, int offset, int length) { int accepted = Math.min(length, limit - delegate.size()); if (accepted > 0) delegate.write(bytes, offset, accepted); if (accepted < length) truncated = true; }
        byte[] bytes() { return delegate.toByteArray(); }
    }
}
