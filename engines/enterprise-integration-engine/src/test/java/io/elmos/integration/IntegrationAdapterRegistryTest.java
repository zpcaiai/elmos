package io.elmos.integration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class IntegrationAdapterRegistryTest {
    @Test void allExternalAdaptersStartUnconfiguredAndAllowlisted() {
        var registry = new IntegrationAdapterRegistry();
        assertEquals(12, registry.all().size());
        assertTrue(registry.all().stream().allMatch(a -> a.status() == IntegrationModels.AdapterStatus.NOT_CONFIGURED));
        assertTrue(registry.all().stream().allMatch(a -> "ALLOWLIST_REQUIRED".equals(a.networkPolicy())));
        assertFalse(registry.anyReady(IntegrationModels.RunnerType.DISCOVERY));
    }
}
