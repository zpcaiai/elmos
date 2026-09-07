package io.elmos.testquality;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TestToolAdapterRegistryTest {
    @Test void allAdaptersAreExplicitlyNotConfiguredAndNetworkDenied() {
        var adapters = new TestToolAdapterRegistry().adapters();
        assertEquals(12, adapters.size());
        assertTrue(adapters.stream().allMatch(a -> a.status() == QualityModels.AdapterStatus.NOT_CONFIGURED));
        assertTrue(adapters.stream().allMatch(a -> a.defaultNetwork().equals("DENY")));
    }
}
