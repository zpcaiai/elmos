package io.elmos.controlplane;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProductionRuntimeControlPlaneMetricsTest {
    @Test
    void loopTelemetryRecordsSuccessAndFailureWithoutTenantLabels() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        ProductionRuntimeControlPlaneMetrics metrics =
                new ProductionRuntimeControlPlaneMetrics(registry);

        metrics.record("scheduler", "schedule", () -> { });
        assertThrows(IllegalStateException.class, () -> metrics.record(
                "billing", "billing-recovery", () -> {
                    throw new IllegalStateException("synthetic");
                }));

        assertEquals(1.0, registry.get("elmos.production.runtime.loop.runs")
                .tag("component", "scheduler")
                .tag("loop", "schedule")
                .tag("outcome", "success")
                .counter().count());
        assertEquals(1.0, registry.get("elmos.production.runtime.loop.runs")
                .tag("component", "billing")
                .tag("loop", "billing-recovery")
                .tag("outcome", "failure")
                .counter().count());
        registry.getMeters().forEach(meter -> meter.getId().getTags().forEach(tag ->
                org.junit.jupiter.api.Assertions.assertNotEquals("tenantId", tag.getKey())));
    }

    @Test
    void unknownLoopTagsAreRejected() {
        ProductionRuntimeControlPlaneMetrics metrics =
                new ProductionRuntimeControlPlaneMetrics(new SimpleMeterRegistry());
        assertThrows(IllegalArgumentException.class, () ->
                metrics.record("scheduler", "tenant-specific", () -> { }));
    }
}
