package io.elmos.workspaceservice;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;

class WorkspaceSecretRegistryTest {
    @Test void redactsEveryActiveOccurrenceAndStopsAfterRevocation() {
        WorkspaceSecretRegistry registry = new WorkspaceSecretRegistry();
        char[] secret = "short-lived-token".toCharArray();
        registry.register("ws-1", "lease-1", secret);
        java.util.Arrays.fill(secret, '\0');

        byte[] sanitized = registry.sanitize("ws-1", "before short-lived-token after short-lived-token"
                .getBytes(StandardCharsets.UTF_8));
        assertEquals("before [REDACTED] after [REDACTED]", new String(sanitized, StandardCharsets.UTF_8));

        registry.remove("ws-1", "lease-1");
        assertEquals("short-lived-token", new String(registry.sanitize("ws-1", "short-lived-token"
                .getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8));
        assertThrows(SecurityException.class, () -> registry.register("ws-1", "lease-2", "abc".toCharArray()));
    }
}
