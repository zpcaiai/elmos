package io.elmos.runner;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * The claim loop, plus drain and shutdown coordination.
 *
 * <p>Drain is what makes {@code helm upgrade} safe. On SIGTERM - or when the
 * control plane sets the drain flag - the agent stops claiming immediately but
 * keeps running what it already holds until those jobs finish. Killing in-flight
 * work on every deploy is how a platform teaches its users not to trust it.</p>
 */
public final class LeasePoller implements AutoCloseable {

    private final AgentConfig config;
    private final ControlPlaneClient client;
    private final ContainerRuntime containers;
    private final JobExecutor executor;
    private final AgentMetrics metrics;

    private final Semaphore slots;
    private final ExecutorService jobs = Executors.newVirtualThreadPerTaskExecutor();
    private final AtomicBoolean draining = new AtomicBoolean(false);
    private final AtomicBoolean stopped = new AtomicBoolean(false);
    private final Backoff idleBackoff = new Backoff(1_000, 5_000);
    private final Backoff errorBackoff = new Backoff(2_000, 60_000);

    public LeasePoller(AgentConfig config, ControlPlaneClient client,
                       ContainerRuntime containers, JobExecutor executor, AgentMetrics metrics) {
        this.config = config;
        this.client = client;
        this.containers = containers;
        this.executor = executor;
        this.metrics = metrics;
        this.slots = new Semaphore(config.maxConcurrency());
    }

    public void requestDrain() {
        if (draining.compareAndSet(false, true)) {
            metrics.gauge(AgentMetrics.DRAINING, 1);
        }
    }

    public boolean draining() {
        return draining.get();
    }

    public int runningJobs() {
        return config.maxConcurrency() - slots.availablePermits();
    }

    /** Blocks until the agent is drained and idle. */
    public void run() {
        while (!stopped.get()) {
            if (draining.get() && runningJobs() == 0) {
                return;
            }
            try {
                pollOnce();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                requestDrain();
            }
        }
    }

    void pollOnce() throws InterruptedException {
        // Node heartbeat first: it is also how the control plane asks us to drain.
        try {
            if (client.nodeHeartbeat()) {
                requestDrain();
            }
            errorBackoff.reset();
        } catch (RuntimeException ex) {
            metrics.increment(AgentMetrics.CLAIM_FAILURES);
            Thread.sleep(errorBackoff.nextDelayMillis());
            return;
        }

        if (draining.get()) {
            // Do not claim while draining; just wait for in-flight work.
            Thread.sleep(1_000);
            return;
        }

        int free = slots.availablePermits();
        if (free <= 0) {
            Thread.sleep(1_000);
            return;
        }

        List<ControlPlaneClient.Lease> leases;
        try {
            List<String> availableImages = containers.locallyAvailableImages();
            if (availableImages.isEmpty()) {
                metrics.markUnhealthy("runner_image_not_local");
                Thread.sleep(errorBackoff.nextDelayMillis());
                return;
            }
            leases = client.claim(Math.min(free, config.claimBatchSize()), availableImages);
            errorBackoff.reset();
        } catch (RuntimeException ex) {
            metrics.increment(AgentMetrics.CLAIM_FAILURES);
            Thread.sleep(errorBackoff.nextDelayMillis());
            return;
        }

        if (leases.isEmpty()) {
            Thread.sleep(idleBackoff.nextDelayMillis());
            return;
        }
        idleBackoff.reset();

        for (ControlPlaneClient.Lease lease : leases) {
            if (!slots.tryAcquire()) {
                // The control plane granted more than we can run. This should not
                // happen - it tracks our capacity - but if it does, the safe move is
                // to leave the extra lease to expire rather than to over-subscribe.
                metrics.increment(AgentMetrics.JOBS_ABANDONED);
                continue;
            }
            jobs.submit(() -> {
                try {
                    executor.execute(lease);
                } finally {
                    slots.release();
                }
            });
        }
    }

    /**
     * Graceful shutdown: stop claiming, wait for in-flight jobs up to the timeout,
     * then give up. The timeout must exceed the longest expected job, otherwise a
     * deploy still truncates work.
     */
    public void shutdown(long timeoutSeconds) {
        requestDrain();
        jobs.shutdown();
        try {
            if (!jobs.awaitTermination(timeoutSeconds, TimeUnit.SECONDS)) {
                // Containers are killed by the JobExecutor's finally block when its
                // thread is interrupted, so nothing is left running on the node.
                jobs.shutdownNow();
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            jobs.shutdownNow();
        }
        stopped.set(true);
    }

    @Override
    public void close() {
        shutdown(0);
    }
}
