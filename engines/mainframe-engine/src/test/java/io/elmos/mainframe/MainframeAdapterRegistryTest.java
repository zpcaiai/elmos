package io.elmos.mainframe;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class MainframeAdapterRegistryTest {
    @Test void allExternalAdaptersStartUnconfiguredAndAllowlisted() {
        var registry = new MainframeAdapterRegistry();
        assertEquals(10, registry.all().size());
        assertTrue(registry.all().stream().allMatch(a -> a.status() == MainframeModels.AdapterStatus.NOT_CONFIGURED));
        assertTrue(registry.all().stream().allMatch(a -> "ALLOWLIST_REQUIRED".equals(a.networkPolicy())));
        assertFalse(registry.anyReady(MainframeModels.RunnerType.DISCOVERY));
    }
}
