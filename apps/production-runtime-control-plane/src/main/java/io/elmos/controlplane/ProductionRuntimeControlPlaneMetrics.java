package io.elmos.controlplane;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.Objects;
import java.util.Set;

/** Low-cardinality runtime-loop telemetry; tenant and project identities are never labels. */
final class ProductionRuntimeControlPlaneMetrics {
    private static final Set<String> COMPONENTS = Set.of("scheduler", "billing", "projector");
    private static final Set<String> LOOPS = Set.of(
            "schedule", "recover", "billing-recovery", "projection", "outbox");

    private final MeterRegistry meters;

    ProductionRuntimeControlPlaneMetrics(MeterRegistry meters) {
        this.meters = Objects.requireNonNull(meters, "meters");
    }

    void record(String component, String loop, Runnable operation) {
        if (!COMPONENTS.contains(component) || !LOOPS.contains(loop)) {
            throw new IllegalArgumentException("runtime metric tags are not allowlisted");
        }
        Objects.requireNonNull(operation, "operation");
        Timer.Sample sample = Timer.start(meters);
        String outcome = "success";
        try {
            operation.run();
        } catch (RuntimeException | Error ex) {
            outcome = "failure";
            throw ex;
        } finally {
            Counter.builder("elmos.production.runtime.loop.runs")
                    .description("Production runtime scheduled-loop executions")
                    .tag("component", component)
                    .tag("loop", loop)
                    .tag("outcome", outcome)
                    .register(meters)
                    .increment();
            sample.stop(Timer.builder("elmos.production.runtime.loop.duration")
                    .description("Production runtime scheduled-loop duration")
                    .tag("component", component)
                    .tag("loop", loop)
                    .register(meters));
        }
    }
}
