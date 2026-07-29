package io.elmos.runner;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Prometheus exposition and liveness, served by the JDK's built-in HTTP server.
 *
 * <p>Bound to loopback by default. A runner sits next to untrusted workloads; its
 * metrics port should not be another thing on the network to attack.</p>
 */
public final class AgentMetrics {

    private final Map<String, AtomicLong> counters = new ConcurrentHashMap<>();
    private final Map<String, AtomicLong> gauges = new ConcurrentHashMap<>();
    private volatile HttpServer server;
    private volatile boolean healthy = true;
    private volatile String unhealthyReason = "";

    public void increment(String name) {
        add(name, 1);
    }

    public void add(String name, long delta) {
        counters.computeIfAbsent(name, key -> new AtomicLong()).addAndGet(delta);
    }

    public void gauge(String name, long value) {
        gauges.computeIfAbsent(name, key -> new AtomicLong()).set(value);
    }

    public long counter(String name) {
        AtomicLong value = counters.get(name);
        return value == null ? 0 : value.get();
    }

    public long gaugeValue(String name) {
        AtomicLong value = gauges.get(name);
        return value == null ? 0 : value.get();
    }

    public void markUnhealthy(String reason) {
        this.healthy = false;
        this.unhealthyReason = reason;
    }

    public boolean healthy() {
        return healthy;
    }

    public void start(int port, String bindHost) throws IOException {
        HttpServer http = HttpServer.create(new InetSocketAddress(bindHost, port), 0);
        http.createContext("/healthz", exchange -> {
            if (healthy) {
                respond(exchange, 200, "ok\n");
            } else {
                respond(exchange, 503, "unhealthy: " + unhealthyReason + "\n");
            }
        });
        http.createContext("/metrics", exchange -> respond(exchange, 200, render()));
        http.setExecutor(null);
        http.start();
        this.server = http;
    }

    public void stop() {
        HttpServer http = server;
        if (http != null) {
            http.stop(0);
        }
    }

    String render() {
        StringBuilder out = new StringBuilder();
        counters.forEach((name, value) -> out
                .append("# TYPE ").append(name).append(" counter\n")
                .append(name).append(' ').append(value.get()).append('\n'));
        gauges.forEach((name, value) -> out
                .append("# TYPE ").append(name).append(" gauge\n")
                .append(name).append(' ').append(value.get()).append('\n'));
        return out.toString();
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "text/plain; version=0.0.4");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    // Metric names, kept in one place so the dashboards and the code cannot drift.
    public static final String JOBS_CLAIMED = "elmos_runner_jobs_claimed_total";
    public static final String JOBS_SUCCEEDED = "elmos_runner_jobs_succeeded_total";
    public static final String JOBS_FAILED = "elmos_runner_jobs_failed_total";
    public static final String JOBS_CANCELLED = "elmos_runner_jobs_cancelled_total";
    public static final String JOBS_ABANDONED = "elmos_runner_jobs_abandoned_total";
    public static final String HEARTBEAT_FAILURES = "elmos_runner_heartbeat_failures_total";
    public static final String CLAIM_FAILURES = "elmos_runner_claim_failures_total";
    public static final String ARTIFACTS_PUBLISHED = "elmos_runner_artifacts_published_total";
    public static final String RUNNING_JOBS = "elmos_runner_running_jobs";
    public static final String DRAINING = "elmos_runner_draining";
}
