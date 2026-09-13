package io.elmos.runner;

import java.nio.file.Path;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.util.regex.Pattern;

/**
 * Builds and supervises the workload container.
 *
 * <p>The flag set below is the sandbox. It is assembled in one place, from
 * constants, and the agent never accepts flags from the job payload - a workload
 * that could influence its own container flags is not sandboxed at all.</p>
 */
public final class ContainerRuntime {

    /**
     * Only an immutable digest reference may run. The same rule is enforced by the
     * database CHECK on {@code execution_jobs.runner_image}; duplicating it here
     * means a compromised control plane still cannot make a runner pull a mutable
     * tag.
     */
    private static final Pattern DIGEST_IMAGE =
            Pattern.compile("^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$");

    private final AgentConfig config;
    private final ProcessRunner processes;
    private static final class OwnedContainer {
        final String leaseIdentity;
        JobWorkspace.ContainerIntent intent;
        OwnedContainer(String leaseIdentity, JobWorkspace.ContainerIntent intent) {
            this.leaseIdentity = leaseIdentity;
            this.intent = intent;
        }
    }
    private final Map<String, OwnedContainer> ownedContainers = new ConcurrentHashMap<>();
    private final AtomicBoolean selfFenced = new AtomicBoolean();
    private final Object admission = new Object();
    static final String RESOURCE_LABEL = "io.elmos.runner.resource-id";
    static final String LEASE_LABEL = "io.elmos.runner.lease-sha256";

    public ContainerRuntime(AgentConfig config, ProcessRunner processes) {
        this.config = config;
        this.processes = processes;
        selfFenced.set(JobWorkspace.hasPendingContainerIntents(config.workRoot()));
    }

    public record Execution(ProcessRunner.Handle handle, String containerName) {
    }

    public boolean isFenced() { return selfFenced.get(); }

    public static final class ReconciliationRequiredException extends IllegalStateException {
        private static final long serialVersionUID = 1L;
        ReconciliationRequiredException(String message, Throwable cause) { super(message, cause); }
    }

    public static void validateImage(String image) {
        if (image == null || !DIGEST_IMAGE.matcher(image).matches()) {
            throw new IllegalArgumentException("RUNNER_IMAGE_NOT_DIGEST_PINNED");
        }
    }

    List<String> buildCommand(ControlPlaneClient.Lease lease, JobWorkspace workspace, String containerName) {
        validateImage(lease.runnerImage());

        List<String> command = new ArrayList<>();
        command.add(config.containerEngine());
        command.add("run");
        // Keep the stopped container inspectable until exact-ID cleanup is
        // confirmed. --rm would erase the identity before we can bind it.
        command.add("--name");
        command.add(containerName);
        command.add("--label=" + RESOURCE_LABEL + "=" + containerName);
        command.add("--label=" + LEASE_LABEL + "=" + JobWorkspace.leaseIdentity(lease));

        // --- isolation -------------------------------------------------------
        command.add("--network=none");             // no egress from the workload
        command.add("--read-only");                // immutable root filesystem
        command.add("--cap-drop=ALL");             // no capabilities
        command.add("--security-opt=no-new-privileges");
        // Must match the uid that created the workspace, or the first artifact
        // write fails with Permission denied. Verified at startup by the write probe.
        command.add("--user=" + config.workloadUid() + ":" + config.workloadGid());
        command.add("--userns=keep-id");           // rootless mapping stays explicit
        // A digest reference is resolved against a registry unless the image is
        // already local; never let a job stall on a registry round trip mid-lease.
        command.add("--pull=missing");

        // --- budgets ---------------------------------------------------------
        command.add("--cpus=" + String.format(java.util.Locale.ROOT, "%.2f", lease.budgetCpuMillis() / 1000.0));
        command.add("--memory=" + lease.budgetMemoryMib() + "m");
        // Without a swap limit equal to the memory limit the kernel lets the
        // workload spill past its memory budget instead of being OOM-killed.
        command.add("--memory-swap=" + lease.budgetMemoryMib() + "m");
        command.add("--pids-limit=512");
        command.add("--ulimit=nofile=4096:4096");

        // --- mounts ----------------------------------------------------------
        command.add("--volume=" + workspace.in() + ":/elmos/in:ro");
        command.add("--volume=" + workspace.out() + ":/elmos/out:rw");
        command.add("--volume=" + workspace.tmp() + ":/elmos/tmp:rw");
        command.add("--tmpfs=/tmp:rw,noexec,nosuid,size=256m");
        command.add("--workdir=/elmos/tmp");

        // --- environment -----------------------------------------------------
        // Exactly three variables. The enrolment token, the lease token and the
        // control-plane URL are never exposed to the workload.
        command.add("--env=ELMOS_JOB_KIND=" + sanitizeEnv(lease.jobKind()));
        command.add("--env=ELMOS_INPUT_DIR=/elmos/in");
        command.add("--env=ELMOS_OUTPUT_DIR=/elmos/out");

        command.add(lease.runnerImage());
        return command;
    }

    public Execution start(ControlPlaneClient.Lease lease, JobWorkspace workspace, Consumer<String> onLogLine) {
        synchronized (admission) {
            if (selfFenced.get()) throw new ReconciliationRequiredException("RUNNER_CONTAINER_RECONCILIATION_REQUIRED", null);
            if (ownedContainers.size() >= config.maxConcurrency()) throw new IllegalStateException("RUNNER_CONTAINER_CAPACITY_EXCEEDED");
            return startAdmitted(lease, workspace, onLogLine);
        }
    }

    private Execution startAdmitted(ControlPlaneClient.Lease lease, JobWorkspace workspace, Consumer<String> onLogLine) {
        String leaseIdentity = JobWorkspace.leaseIdentity(lease);
        if (lease.jobKind() == null || lease.jobKind().isBlank() || lease.jobKind().length() > 128) {
            throw new IllegalArgumentException("CONTAINER_PHASE_IDENTITY_INVALID");
        }
        // A fresh phase/invocation nonce prevents delayed cleanup from ever
        // resolving a later retry by the same human-readable job name.
        String containerName = "elmos-" + JobWorkspace.identityHash(Json.write(List.of(
                leaseIdentity, lease.jobKind(), UUID.randomUUID().toString()))).substring(0, 48);
        List<String> command = buildCommand(lease, workspace, containerName);
        JobWorkspace.ContainerIntent intent;
        try {
            intent = config.allowHostExecution() ? null : workspace.recordContainerIntent(containerName, leaseIdentity);
        } catch (IOException unknown) {
            selfFenced.set(true);
            throw new ReconciliationRequiredException("CONTAINER_INTENT_PUBLICATION_FAILED", unknown);
        }
        ownedContainers.put(containerName, new OwnedContainer(leaseIdentity, intent));
        try {
            ProcessRunner.Handle handle = processes.start(command, workspace.root(), Map.of(), onLogLine);
            return new Execution(handle, containerName);
        } catch (RuntimeException error) {
            try {
                forceRemove(containerName);
            } catch (ReconciliationRequiredException unknown) {
                unknown.addSuppressed(error);
                throw unknown;
            }
            throw error;
        }
    }

    public Execution startTranslationPreflight(ControlPlaneClient.Lease lease, JobWorkspace workspace) {
        if (!TranslationJobProtocol.applies(lease)) throw new IllegalArgumentException("TRANSLATION_JOB_KIND_INVALID");
        var preflight = new ControlPlaneClient.Lease(lease.jobId(), lease.leaseId(), lease.leaseToken(),
                lease.businessLine(), "translate-preflight-v1", lease.runnerImage(), lease.budgetWallSeconds(),
                lease.budgetCpuMillis(), lease.budgetMemoryMib(), lease.attempt(), lease.checkpointCursor(), lease.requestPayload());
        // Source/compiler stdout can never authorize the paid pipeline stage.
        return start(preflight, workspace, ignored -> {});
    }

    /**
     * Terminates a container and guarantees it is gone.
     *
     * <p>Signalling the client process is not enough: with some engines the client
     * exits while the container keeps running. The engine-level {@code kill} and
     * {@code rm -f} below are what actually stop the workload, and they are issued
     * even if the client already exited.</p>
     */
    public void stop(Execution execution, int graceSeconds) {
        execution.handle().terminate();
        try {
            Integer exit = execution.handle().waitFor(graceSeconds, TimeUnit.SECONDS);
            if (exit == null) {
                execution.handle().kill();
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            execution.handle().kill();
        }
        forceRemove(execution.containerName());
    }

    public void forceRemove(String containerName) {
        OwnedContainer owned = ownedContainers.get(containerName);
        if (owned == null) return; // Never accepts arbitrary cleanup targets.
        synchronized (owned) {
            if (ownedContainers.get(containerName) != owned) return;
            try {
                removeOwned(containerName, owned);
            } catch (IOException | RuntimeException unknown) {
                selfFenced.set(true);
                throw new ReconciliationRequiredException("RUNNER_CONTAINER_CLEANUP_UNVERIFIED", unknown);
            }
        }
    }

    private void removeOwned(String containerName, OwnedContainer owned) throws IOException {
        if (config.allowHostExecution()) {
            ownedContainers.remove(containerName, owned);
            return;
        }
        ProcessRunner.Result inspected = processes.run(List.of(config.containerEngine(), "inspect", containerName),
                null, Map.of(), 15);
        if (!inspected.ok()) {
            // Missing name/ID is not proof a daemon has finished a pending
            // create. Retain durable intent and self-fence for reconciliation.
            throw new IllegalStateException("CONTAINER_CLEANUP_IDENTITY_UNVERIFIED");
        }
        Object value = Json.parse(inspected.stdout());
        if (!(value instanceof List<?> containers) || containers.size() != 1
                || !(containers.get(0) instanceof Map<?, ?> container)
                || !(container.get("Id") instanceof String id) || !id.matches("[a-f0-9]{64}")
                || !(container.get("Name") instanceof String name)
                || !(name.equals(containerName) || name.equals("/" + containerName))
                || !(container.get("Config") instanceof Map<?, ?> settings)
                || !(settings.get("Labels") instanceof Map<?, ?> labels)
                || !containerName.equals(labels.get(RESOURCE_LABEL))
                || !owned.leaseIdentity.equals(labels.get(LEASE_LABEL))) {
            throw new IllegalStateException("CONTAINER_CLEANUP_IDENTITY_MISMATCH");
        }
        owned.intent = JobWorkspace.bindContainerId(owned.intent, id);
        // After verification use the immutable ID, never re-resolve a name for
        // a destructive command. A name can disappear/rebind between calls.
        processes.run(List.of(config.containerEngine(), "kill", id), null, Map.of(), 15);
        processes.run(List.of(config.containerEngine(), "rm", "-f", id), null, Map.of(), 15);
        if (!absent("id=" + id)) throw new IllegalStateException("CONTAINER_CLEANUP_UNVERIFIED");
        JobWorkspace.clearContainerIntent(owned.intent);
        ownedContainers.remove(containerName, owned);
    }

    private boolean absent(String filter) {
        ProcessRunner.Result listing = processes.run(List.of(config.containerEngine(), "ps", "--all", "--no-trunc",
                "--filter", filter, "--format", "{{.ID}}"), null, Map.of(), 15);
        return listing.ok() && listing.stdout().isBlank();
    }

    private static String sanitizeEnv(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length() && i < 64; i++) {
            char c = value.charAt(i);
            if (Character.isLetterOrDigit(c) || c == '-' || c == '_' || c == '.') {
                out.append(c);
            }
        }
        return out.toString();
    }
}
