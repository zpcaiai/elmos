package io.elmos.securitycompliance;

import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class SecurityToolAdapterRegistryTest {
    @Test void everyAdapterStartsNotConfiguredWithDenyByDefaultNetwork() {
        var adapters = new SecurityToolAdapterRegistry().all();
        assertEquals(SecurityModels.AdapterType.values().length, adapters.size());
        adapters.values().forEach(adapter -> {
            assertEquals(SecurityModels.AdapterStatus.NOT_CONFIGURED, adapter.status());
            assertEquals("DENY", adapter.defaultNetwork());
        });
    }

    @Test void rejectsRiskAcceptanceOrProductionMutationPermissions() {
        assertThrows(IllegalArgumentException.class, () -> new SecurityModels.ToolAdapter(
                SecurityModels.AdapterType.SAST, "bad", "1", SecurityModels.AdapterStatus.READY,
                Set.of("SOURCE"), Set.of("ACCEPT_RISK"), false, "DENY", "approved", "redacted",
                "json", "review", "full"));
    }
}
