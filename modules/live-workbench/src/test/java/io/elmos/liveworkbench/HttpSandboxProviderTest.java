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

    @Test void liveDockerSandboxProviderLifecycleWhenDaemonIsRunning() {
        HttpSandboxProvider provider = new HttpSandboxProvider(HttpClient.newHttpClient(), new ObjectMapper(),
                new HttpSandboxProvider.Configuration(URI.create("http://127.0.0.1:8099"), Duration.ofSeconds(15),
                        "0123456789abcdef0123456789abcdef", true, Set.of("https://preview.example.test")));
        if (!provider.ready()) {
            return;
        }
        PrincipalScope scope = new PrincipalScope("tenant-test", "account-test", "actor-test", "env-test", Set.of());
        String snapshot = LwDigest.sha256("snapshot-test");
        String sessionId = "java-sess-" + System.currentTimeMillis();
        CreateSessionRequest req = new CreateSessionRequest("repo-test", snapshot, "del-1", "java-21", "ecommerce", "debug", 1, true);
        ProviderAllocation alloc = provider.allocate(scope, sessionId, req, "idem-alloc", System.currentTimeMillis() / 1000 + 600);
        assertNotNull(alloc.providerSessionId());
        assertTrue(alloc.providerSessionId().startsWith("docker-"));

        SessionView session = new SessionView("tenant-test", "account-test", "actor-test", sessionId, "del-1", "repo-test",
                snapshot, "java-21", "ecommerce", "debug", 1, 1, SessionState.READY, RuntimeStatus.RUNNING,
                1, 10L, System.currentTimeMillis() / 1000 + 600, 700, alloc.providerSessionId(), alloc.resourceLeaseId(),
                alloc.members(), List.of(), 1);
        ProviderCommandResult cmdRes = provider.dispatchDebug(scope, session, "cmd-step", "idem-step", new DebugRequest("stepIn", LwDigest.sha256("{}"), 1, "ctl"));
        assertEquals(CommandState.COMMITTED, cmdRes.state());

        CleanupOutcome cleanup = provider.cleanup(scope, session, "test-complete");
        assertEquals(SessionState.CLEANED, cleanup.status());
        assertTrue(Boolean.TRUE.equals(cleanup.memberChecks().get("containerKilled")));
    }

    private static HttpSandboxProvider.Configuration configuration(String value) {
        return new HttpSandboxProvider.Configuration(URI.create(value), Duration.ofSeconds(1),
                "0123456789abcdef0123456789abcdef", false, Set.of());
    }
}
