package io.elmos.liveworkbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;
import static org.junit.jupiter.api.Assertions.*;

class HttpSandboxProviderTest {
    @Test void providerTransportRejectsCleartextAndCredentialBearingUrls() {
        assertThrows(IllegalArgumentException.class, () -> configuration("http://provider.example.test"));
        assertThrows(IllegalArgumentException.class, () -> configuration("https://user:secret@provider.example.test"));
        assertDoesNotThrow(() -> new HttpSandboxProvider.Configuration(URI.create("http://127.0.0.1:9876"),
                Duration.ofSeconds(1), "0123456789abcdef0123456789abcdef", true,
                Set.of("https://preview.example.test")));
    }

    @Test void lostDebugResponseBecomesUnknownAndIsNeverReportedCommitted() {
        HttpSandboxProvider provider = new HttpSandboxProvider(HttpClient.newHttpClient(), new ObjectMapper(),
                new HttpSandboxProvider.Configuration(URI.create("http://127.0.0.1:9"), Duration.ofMillis(100),
                        "0123456789abcdef0123456789abcdef", true, Set.of("https://preview.example.test")));
        PrincipalScope scope = new PrincipalScope("tenant-a", "account-a", "actor-a", "env-a", Set.of());
        String snapshot = LwDigest.sha256("snapshot");
        SessionView session = new SessionView("tenant-a", "account-a", "actor-a", "session-a", "delivery-a", "repo-a",
                snapshot, "node", "smoke", "debug", 1, 1, SessionState.READY, RuntimeStatus.RUNNING,
                1, 10L, 610L, 700, "provider-a", "lease-a", Map.of("sandbox", "sandbox-a"), List.of("evidence"), 1);
        ProviderCommandResult result = provider.dispatchDebug(scope, session, "command-a", "idempotency-a",
                new DebugRequest("next", LwDigest.sha256("{}"), 1, "control-a"));
        assertEquals(CommandState.UNKNOWN, result.state());
        assertFalse(provider.ready());
    }

    private static HttpSandboxProvider.Configuration configuration(String value) {
        return new HttpSandboxProvider.Configuration(URI.create(value), Duration.ofSeconds(1),
                "0123456789abcdef0123456789abcdef", false, Set.of());
    }
}
