package io.elmos.productionworker;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Objects;

/** Low-cardinality worker health and durable-inbox telemetry. */
final class ProductionWorkerMetrics {
    ProductionWorkerMetrics(
            MeterRegistry meters,
            ProductionWorkerAttemptService attempts
    ) {
        Objects.requireNonNull(meters, "meters");
        Objects.requireNonNull(attempts, "attempts");
        Gauge.builder("elmos.production.runtime.worker.journal.healthy",
                        attempts, value -> value.journalHealthy() ? 1.0 : 0.0)
                .description("Whether the worker durable journal can accept new work")
                .register(meters);
        for (ProductionWorkerAttemptService.LocalStatus status
                : ProductionWorkerAttemptService.LocalStatus.values()) {
            Gauge.builder("elmos.production.runtime.worker.attempts",
                            attempts, value -> value.attemptsWithStatus(status))
                    .description("Number of retained worker attempts by local state")
                    .tag("status", status.name())
                    .register(meters);
        }
    }
}
