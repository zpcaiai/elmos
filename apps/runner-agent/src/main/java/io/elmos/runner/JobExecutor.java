package io.elmos.runner;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Runs exactly one leased job from start to terminal report.
 *
 * <p>The ordering below is deliberate and is the part worth reviewing carefully:
 * the container is always stopped before anything is reported, artifacts are only
 * published while the lease is still demonstrably ours, and a lost lease produces
 * <em>no</em> report at all - the control plane has already given the job to
 * someone else, and a late report from this agent would overwrite a newer truth.</p>
 */
public final class JobExecutor {

    /**
     * Structured progress line the workload may emit on stdout:
     * {@code ::elmos stage=building progress=40}
     * Anything else is treated as ordinary log output.
     */
    private static final Pattern PROGRESS_LINE =
            Pattern.compile("^::elmos\\s+stage=([a-z0-9_-]{1,64})(?:\\s+progress=(\\d{1,3}))?\\s*$");

    private final AgentConfig config;
    private final ControlPlaneClient client;
    private final ContainerRuntime containers;
    private final ArtifactPublisher artifacts;
    private final AgentMetrics metrics;

    public JobExecutor(AgentConfig config, ControlPlaneClient client, ContainerRuntime containers,
                       ArtifactPublisher artifacts, AgentMetrics metrics) {
        this.config = config;
        this.client = client;
        this.containers = containers;
        this.artifacts = artifacts;
        this.metrics = metrics;
    }

    public enum Outcome { SUCCEEDED, FAILED, CANCELLED, PAUSED, ABANDONED }

    public Outcome execute(ControlPlaneClient.Lease lease) {
        metrics.increment(AgentMetrics.JOBS_CLAIMED);
        metrics.gauge(AgentMetrics.RUNNING_JOBS, metrics.gaugeValue(AgentMetrics.RUNNING_JOBS) + 1);
        try {
            return runGuarded(lease);
        } finally {
            metrics.gauge(AgentMetrics.RUNNING_JOBS, Math.max(0, metrics.gaugeValue(AgentMetrics.RUNNING_JOBS) - 1));
        }
    }

    private Outcome runGuarded(ControlPlaneClient.Lease lease) {
        JobWorkspace workspace = null;
        ContainerRuntime.Execution execution = null;
        HeartbeatPump pump = new HeartbeatPump(client, lease, config, metrics);

        try {
            ContainerRuntime.validateImage(lease.runnerImage());

            workspace = JobWorkspace.create(config.workRoot(), lease.jobId(),
                    config.workloadUid(), config.workloadGid());
            workspace.writeInput("request.json", Json.write(lease.requestPayload()));
            workspace.writeInput("checkpoint.json", Json.write(lease.checkpointCursor()));

            pump.start();

            AtomicReference<String> lastStage = new AtomicReference<>("running");
            execution = containers.start(lease, workspace, line -> {
                Matcher matcher = PROGRESS_LINE.matcher(line.strip());
                if (matcher.matches()) {
                    String stage = matcher.group(1);
                    int progress = matcher.group(2) == null ? 0 : Integer.parseInt(matcher.group(2));
                    lastStage.set(stage);
                    pump.report(stage, progress);
                }
            });

            Outcome supervision = supervise(lease, pump, execution);
            if (supervision != null) {
                return supervision;
            }

            Integer exitCode = execution.handle().waitFor(5, TimeUnit.SECONDS);
            if (exitCode == null) {
                containers.stop(execution, config.cancelGraceSeconds());
                return report(lease, pump, Outcome.FAILED, "WORKLOAD_DID_NOT_EXIT");
            }

            // Close the narrow race where the workload exits between the
            // supervision poll and the heartbeat response. Control requests
            // still win before any artifact publication or terminal success.
            if (pump.cancelRequested()) {
                return report(lease, pump, Outcome.CANCELLED, null);
            }
            if (pump.pauseRequested()) {
                return report(lease, pump, Outcome.PAUSED, null);
            }

            if (exitCode != 0) {
                return report(lease, pump, Outcome.FAILED, "WORKLOAD_EXIT_" + exitCode);
            }

            // Publish only while the lease is still ours.
            if (pump.leaseLost() != null) {
                metrics.increment(AgentMetrics.JOBS_ABANDONED);
                return Outcome.ABANDONED;
            }
            List<ArtifactPublisher.Published> published = artifacts.publishAll(lease, workspace);
            if (published.isEmpty()) {
                // A "successful" job that produced nothing is not a success; it is
                // a silent failure that would show the user an empty download.
                return report(lease, pump, Outcome.FAILED, "WORKLOAD_PRODUCED_NO_ARTIFACT");
            }
            return report(lease, pump, Outcome.SUCCEEDED, null);

        } catch (ControlPlaneClient.LeaseLostException ex) {
            metrics.increment(AgentMetrics.JOBS_ABANDONED);
            return Outcome.ABANDONED;
        } catch (ControlPlaneClient.TransportException ex) {
            return report(lease, pump, Outcome.FAILED, ex.getMessage());
        } catch (IllegalArgumentException ex) {
            return report(lease, pump, Outcome.FAILED, ex.getMessage());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return report(lease, pump, Outcome.FAILED, "AGENT_INTERRUPTED");
        } catch (Exception ex) {
            return report(lease, pump, Outcome.FAILED, "AGENT_INTERNAL_ERROR");
        } finally {
            pump.close();
            if (execution != null) {
                containers.forceRemove(execution.containerName());
            }
            if (workspace != null) {
                workspace.close();
            }
        }
    }

    /**
     * Watches the running container. Returns a terminal outcome when the job must
     * stop early, or null when the container exited on its own.
     */
    private Outcome supervise(ControlPlaneClient.Lease lease, HeartbeatPump pump,
                              ContainerRuntime.Execution execution) throws InterruptedException {
        Instant deadline = Instant.now().plusSeconds(lease.budgetWallSeconds());

        while (execution.handle().isAlive()) {
            String lost = pump.leaseLost();
            if (lost != null) {
                // Self-fencing. Another runner may already be executing this job;
                // this container must die now and must not report anything.
                containers.stop(execution, config.cancelGraceSeconds());
                metrics.increment(AgentMetrics.JOBS_ABANDONED);
                return Outcome.ABANDONED;
            }

            if (pump.cancelRequested()) {
                containers.stop(execution, config.cancelGraceSeconds());
                return report(lease, pump, Outcome.CANCELLED, null);
            }

            if (pump.pauseRequested()) {
                // The heartbeat carrying the pause signal committed the current
                // checkpoint before returning. Stop gracefully, publish nothing,
                // and acknowledge only after the workload is no longer running.
                containers.stop(execution, config.cancelGraceSeconds());
                return report(lease, pump, Outcome.PAUSED, null);
            }

            if (Instant.now().isAfter(deadline)) {
                containers.stop(execution, config.cancelGraceSeconds());
                return report(lease, pump, Outcome.FAILED, "WALL_CLOCK_BUDGET_EXCEEDED");
            }

            Thread.sleep(Duration.ofMillis(500));
        }
        return null;
    }

    private Outcome report(ControlPlaneClient.Lease lease, HeartbeatPump pump, Outcome outcome, String failureCode) {
        if (pump.leaseLost() != null) {
            metrics.increment(AgentMetrics.JOBS_ABANDONED);
            return Outcome.ABANDONED;
        }
        String status = switch (outcome) {
            case SUCCEEDED -> "SUCCEEDED";
            case CANCELLED -> "CANCELLED";
            case PAUSED -> "PAUSED";
            default -> "FAILED";
        };
        String resultStatus = switch (outcome) {
            case SUCCEEDED -> "PASSED";
            case CANCELLED -> "BLOCKED";
            case PAUSED -> "NOT_RUN";
            default -> "FAILED";
        };
        try {
            client.complete(lease, status, resultStatus, failureCode);
        } catch (ControlPlaneClient.LeaseLostException ex) {
            metrics.increment(AgentMetrics.JOBS_ABANDONED);
            return Outcome.ABANDONED;
        } catch (RuntimeException ex) {
            // The completion could not be delivered. Do not retry forever: the
            // control-plane reaper will requeue or fail the job, and this agent has
            // already stopped the container, so nothing is running twice.
            metrics.increment(AgentMetrics.JOBS_ABANDONED);
            return Outcome.ABANDONED;
        }
        switch (outcome) {
            case SUCCEEDED -> metrics.increment(AgentMetrics.JOBS_SUCCEEDED);
            case CANCELLED -> metrics.increment(AgentMetrics.JOBS_CANCELLED);
            case PAUSED -> { /* A pause is neither a failure nor a cancellation. */ }
            default -> metrics.increment(AgentMetrics.JOBS_FAILED);
        }
        return outcome;
    }

    /** Exposed for the self-test. */
    static Map<String, Object> parseProgress(String line) {
        Matcher matcher = PROGRESS_LINE.matcher(line.strip());
        if (!matcher.matches()) {
            return Map.of();
        }
        return Map.of(
                "stage", matcher.group(1),
                "progress", matcher.group(2) == null ? 0 : Integer.parseInt(matcher.group(2)));
    }
}
