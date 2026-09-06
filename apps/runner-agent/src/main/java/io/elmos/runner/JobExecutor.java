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

    public enum Outcome { SUCCEEDED, PARTIAL, FAILED, CANCELLED, ABANDONED }

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
        Instant executionDeadline = Instant.now().plusSeconds(lease.budgetWallSeconds());

        try {
            ContainerRuntime.validateImage(lease.runnerImage());

            workspace = JobWorkspace.create(config.workRoot(), lease,
                    config.workloadUid(), config.workloadGid());
            workspace.writeInput("request.json", Json.write(lease.requestPayload()));
            workspace.writeInput("checkpoint.json", Json.write(lease.checkpointCursor()));

            pump.start();

            if (TranslationJobProtocol.applies(lease)) {
                PathBundle.materialize(client, lease, workspace);
                if (Instant.now().isAfter(executionDeadline)) return report(lease, pump, Outcome.FAILED, "WALL_CLOCK_BUDGET_EXCEEDED");
                if (pump.cancelRequested()) return report(lease, pump, Outcome.CANCELLED, null);
                if (pump.leaseLost() != null) return Outcome.ABANDONED;
                execution = containers.startTranslationPreflight(lease, workspace);
                Outcome preflightSupervision = supervise(lease, pump, execution, executionDeadline);
                if (preflightSupervision != null) return preflightSupervision;
                Integer preflightExit = execution.handle().waitFor(5, TimeUnit.SECONDS);
                if (preflightExit == null || preflightExit != 0) {
                    return report(lease, pump, Outcome.FAILED, "TRANSLATION_PREFLIGHT_REJECTED");
                }
                TranslationJobProtocol.verifyPreflight(workspace.out().resolve("preflight.json"), lease.requestPayload());
                containers.forceRemove(execution.containerName());
                execution = null;
                if (Instant.now().isAfter(executionDeadline)) return report(lease, pump, Outcome.FAILED, "WALL_CLOCK_BUDGET_EXCEEDED");
                // Synchronous, fenced acknowledgement before executing any paid
                // phase. Never derive this transition from workload log lines.
                if (client.heartbeat(lease, "pipeline", 10, lease.checkpointCursor())) {
                    return report(lease, pump, Outcome.CANCELLED, null);
                }
            }

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

            Outcome supervision = supervise(lease, pump, execution, executionDeadline);
            if (supervision != null) {
                return supervision;
            }

            Integer exitCode = execution.handle().waitFor(5, TimeUnit.SECONDS);
            if (exitCode == null) {
                containers.stop(execution, config.cancelGraceSeconds());
                return report(lease, pump, Outcome.FAILED, "WORKLOAD_DID_NOT_EXIT");
            }

            if (exitCode != 0) {
                return report(lease, pump, Outcome.FAILED, "WORKLOAD_EXIT_" + exitCode);
            }

            String translationStatus = TranslationJobProtocol.applies(lease)
                    ? TranslationJobProtocol.result(workspace.out().resolve("gate/translation-job.json"), lease.requestPayload())
                    : null;

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
            if (TranslationJobProtocol.applies(lease)) {
                return report(lease, pump,
                        translationStatus.equals("COMPLETE") ? Outcome.SUCCEEDED : translationStatus.equals("PARTIAL") ? Outcome.PARTIAL : Outcome.FAILED,
                        translationStatus.equals("BLOCKED") ? "TRANSLATION_PIPELINE_REPORTED_BLOCKED" : null);
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
                              ContainerRuntime.Execution execution, Instant deadline) throws InterruptedException {

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
            case PARTIAL -> "PARTIAL";
            case CANCELLED -> "CANCELLED";
            default -> "FAILED";
        };
        String resultStatus = switch (outcome) {
            case SUCCEEDED -> "PASSED";
            case PARTIAL -> "PARTIAL";
            case CANCELLED -> "BLOCKED";
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
            case PARTIAL -> metrics.increment("jobs_partial");
            case CANCELLED -> metrics.increment(AgentMetrics.JOBS_CANCELLED);
            default -> metrics.increment(AgentMetrics.JOBS_FAILED);
        }
        return outcome;
    }

    private static final class PathBundle {
        static void materialize(ControlPlaneClient client, ControlPlaneClient.Lease lease, JobWorkspace workspace) throws Exception {
            var archive = workspace.tmp().resolve("translation-input.zip");
            client.downloadTranslationInput(lease, archive);
            TranslationInputMaterializer.materialize(archive, workspace.in(), lease.requestPayload());
            java.nio.file.Files.delete(archive);
        }
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
