package io.elmos.runner;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Keeps one lease alive and carries two signals back to the job.
 *
 * <p><b>Cancellation</b> is pull-based on purpose. The control plane cannot open a
 * connection to a runner: runners sit behind NAT, inside customer VPCs, and scale
 * in and out. So a cancel is written to the job row and the runner discovers it on
 * its next heartbeat, within one interval.</p>
 *
 * <p><b>Self-fencing</b> is the more important half. If this pump cannot renew the
 * lease before it expires, the control plane will hand the job to another runner.
 * Continuing to execute would then produce two containers writing two sets of
 * artifacts for one job. So when the lease can no longer be trusted the pump
 * raises {@link #leaseLost()} and the executor kills its own container - the agent
 * fences itself rather than waiting to be told.</p>
 */
public final class HeartbeatPump implements AutoCloseable {

    /**
     * Stop trusting the lease this many seconds before it actually expires, to
     * cover clock skew and the in-flight request that may still be travelling.
     */
    private static final int SAFETY_MARGIN_SECONDS = 10;

    private final ControlPlaneClient client;
    private final ControlPlaneClient.Lease lease;
    private final AgentConfig config;
    private final AgentMetrics metrics;

    private final AtomicBoolean cancelRequested = new AtomicBoolean(false);
    private final AtomicReference<String> leaseLost = new AtomicReference<>(null);
    private final AtomicReference<String> stage = new AtomicReference<>("starting");
    private final AtomicReference<Integer> progress = new AtomicReference<>(0);
    private final AtomicReference<Map<String, Object>> checkpoint = new AtomicReference<>(Map.of());

    private volatile Instant lastSuccess = Instant.now();
    private volatile boolean running = true;
    private Thread thread;

    public HeartbeatPump(ControlPlaneClient client, ControlPlaneClient.Lease lease,
                         AgentConfig config, AgentMetrics metrics) {
        this.client = client;
        this.lease = lease;
        this.config = config;
        this.metrics = metrics;
        this.checkpoint.set(lease.checkpointCursor());
    }

    public void start() {
        thread = Thread.ofVirtual().name("heartbeat-" + lease.jobId()).start(this::loop);
    }

    /** Called by the workload log parser as the job progresses. */
    public void report(String newStage, int newProgress) {
        stage.set(newStage);
        progress.set(Math.max(0, Math.min(100, newProgress)));
    }

    public void checkpoint(Map<String, Object> cursor) {
        checkpoint.set(cursor == null ? Map.of() : cursor);
    }

    public boolean cancelRequested() {
        return cancelRequested.get();
    }

    /** Non-null once the lease can no longer be trusted; the value is a stable code. */
    public String leaseLost() {
        return leaseLost.get();
    }

    private void loop() {
        while (running) {
            try {
                Thread.sleep(Duration.ofSeconds(config.heartbeatIntervalSeconds()));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            if (!running) {
                return;
            }
            beatOnce();
        }
    }

    void beatOnce() {
        try {
            boolean cancel = client.heartbeat(lease, stage.get(), progress.get(), checkpoint.get());
            lastSuccess = Instant.now();
            if (cancel) {
                cancelRequested.set(true);
            }
        } catch (ControlPlaneClient.LeaseLostException ex) {
            // Explicit: somebody else owns this job now. Stop immediately.
            metrics.increment(AgentMetrics.HEARTBEAT_FAILURES);
            leaseLost.compareAndSet(null, ex.code());
        } catch (RuntimeException ex) {
            metrics.increment(AgentMetrics.HEARTBEAT_FAILURES);
            // Transport failure. The lease is still notionally ours until it
            // expires, so keep working - but only while there is time left.
            long silentSeconds = Duration.between(lastSuccess, Instant.now()).toSeconds();
            if (silentSeconds >= config.leaseSeconds() - SAFETY_MARGIN_SECONDS) {
                leaseLost.compareAndSet(null, "LEASE_RENEWAL_TIMED_OUT");
            }
        }
    }

    /** Test seam: how long the pump has been unable to renew. */
    long silentSeconds() {
        return Duration.between(lastSuccess, Instant.now()).toSeconds();
    }

    @Override
    public void close() {
        running = false;
        if (thread != null) {
            thread.interrupt();
        }
    }
}
