package io.elmos.runner;

import java.time.Duration;
import java.time.Instant;

/**
 * Entry point.
 *
 * <p>Startup order is a policy statement: configuration is validated, the sandbox
 * is probed, orphaned workspaces from a previous crash are swept, and only then
 * does the node register. An agent that cannot prove its own sandbox never asks
 * for work.</p>
 */
public final class RunnerAgentMain {

    public static final String VERSION = "0.1.0";

    private RunnerAgentMain() {
    }

    public static void main(String[] args) {
        AgentMetrics metrics = new AgentMetrics();
        Instant startedAt = Instant.now();

        AgentConfig config;
        try {
            config = AgentConfig.fromEnvironment(System.getenv());
            config.validateTimings();
        } catch (RuntimeException ex) {
            // Configuration failures are the one place a human-readable message is
            // worth more than a stable code, because only an operator sees it.
            System.err.println("[elmos-runner] refusing to start: " + ex.getMessage());
            System.exit(78); // EX_CONFIG
            return;
        }

        ProcessRunner processes = new ProcessRunner.Os();
        SandboxAttestation attestation = SandboxAttestation.probe(config, processes);

        System.out.println("[elmos-runner] version=" + VERSION
                + " node=" + config.runnerNodeId()
                + " capabilities=" + config.capabilities()
                + " concurrency=" + config.maxConcurrency());
        attestation.evidence().forEach((key, value) ->
                System.out.println("[elmos-runner] attestation " + key + "=" + value));

        if (!attestation.complete() && !config.allowHostExecution()) {
            System.err.println("[elmos-runner] refusing to start: incomplete sandbox attestation: "
                    + attestation.describeFailures());
            System.exit(78);
            return;
        }

        // Prove the workload can write before asking for any work. Discovering this
        // on the first customer job costs a job and produces a silent empty result.
        WorkspaceAccessProbe.Result access = WorkspaceAccessProbe.verify(config);
        System.out.println("[elmos-runner] workspace access: " + access.detail());
        if (!access.usable()) {
            System.err.println("[elmos-runner] refusing to start: " + access.detail());
            metrics.markUnhealthy("workspace_not_writable");
            System.exit(78);
            return;
        }

        int swept = JobWorkspace.sweepOrphans(config.workRoot());
        if (swept > 0) {
            System.out.println("[elmos-runner] swept " + swept + " orphaned workspace(s) from a previous run");
        }

        ControlPlaneClient client = new ControlPlaneClient(config);
        ContainerRuntime containers = new ContainerRuntime(config, processes);
        ArtifactPublisher artifacts = new ArtifactPublisher(client, metrics);
        JobExecutor executor = new JobExecutor(config, client, containers, artifacts, metrics);
        LeasePoller poller = new LeasePoller(config, client, executor, metrics);

        try {
            metrics.start(config.metricsPort(), "127.0.0.1");
        } catch (Exception ex) {
            System.err.println("[elmos-runner] refusing to start: metrics port unavailable");
            System.exit(70); // EX_SOFTWARE
            return;
        }

        // Registration is retried: a runner that starts during a control-plane
        // rollout should wait, not crash-loop.
        Backoff registration = new Backoff(2_000, 60_000);
        boolean registered = false;
        while (!registered && Duration.between(startedAt, Instant.now()).toMinutes() < 10) {
            try {
                client.register(attestation);
                registered = true;
            } catch (RuntimeException ex) {
                System.err.println("[elmos-runner] registration failed, retrying");
                if (!registration.sleep()) {
                    break;
                }
            }
        }
        if (!registered) {
            metrics.markUnhealthy("registration_failed");
            System.err.println("[elmos-runner] could not register within 10 minutes");
            metrics.stop();
            System.exit(75); // EX_TEMPFAIL
            return;
        }

        System.out.println("[elmos-runner] registered; awaiting verification and leases");

        Thread main = Thread.currentThread();
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            System.out.println("[elmos-runner] SIGTERM received; draining");
            poller.requestDrain();
            // Outlive the longest job budget so a deploy does not truncate work.
            poller.shutdown(3600);
            metrics.stop();
            try {
                main.join(Duration.ofSeconds(30));
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }));

        poller.run();
        System.out.println("[elmos-runner] drained; exiting cleanly");
        metrics.stop();
    }
}
