package io.elmos.suite;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SuiteAdapterRegistryTest {
    @Test void everyAdapterStartsUnconfiguredReadOnlyAndAllowlisted() {
        var adapters = new SuiteAdapterRegistry().all();
        assertEquals(9, adapters.size());
        assertTrue(adapters.stream().allMatch(a -> a.status() == SuiteModels.AdapterStatus.NOT_CONFIGURED));
        assertTrue(adapters.stream().allMatch(a -> !a.productionCapable()));
        assertTrue(adapters.stream().allMatch(a -> a.networkPolicy().equals("ALLOWLIST_REQUIRED")));
    }
}
