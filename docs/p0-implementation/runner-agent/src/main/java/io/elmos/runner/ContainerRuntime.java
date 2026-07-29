package io.elmos.runner;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
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

    public ContainerRuntime(AgentConfig config, ProcessRunner processes) {
        this.config = config;
        this.processes = processes;
    }

    public record Execution(ProcessRunner.Handle handle, String containerName) {
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
        command.add("--rm");
        command.add("--name");
        command.add(containerName);

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
        String containerName = "elmos-" + lease.jobId();
        List<String> command = buildCommand(lease, workspace, containerName);
        ProcessRunner.Handle handle = processes.start(command, workspace.root(), Map.of(), onLogLine);
        return new Execution(handle, containerName);
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
        if (config.allowHostExecution()) {
            return;
        }
        processes.run(List.of(config.containerEngine(), "kill", containerName), null, Map.of(), 15);
        processes.run(List.of(config.containerEngine(), "rm", "-f", containerName), null, Map.of(), 15);
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
