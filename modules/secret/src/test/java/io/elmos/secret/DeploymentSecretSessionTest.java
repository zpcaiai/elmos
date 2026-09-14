package io.elmos.secret;

import org.junit.jupiter.api.Test;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class DeploymentSecretSessionTest {
    @Test void canonicalSecretIsRemovedAndRevokedEvenWhenOperationFails() {
        Instant now = Instant.parse("2026-01-01T00:00:00Z");
        var revoked = new AtomicInteger();
        var removed = new AtomicInteger();
        var metadata = new HashMap<String, SecretLease>();
        var service = new SecretInjectionService(new SecretInjectionService.SecretProviderPort() {
            public SecretInjectionService.ProviderLease issue(SecretInjectionService.SecretRequest request) {
                return new SecretInjectionService.ProviderLease("provider", new SecretValue("test-value".toCharArray()),
                        now, now.plusSeconds(30));
            }
            public void revoke(String id) { revoked.incrementAndGet(); }
        }, new SecretInjectionService.SecretMaterializerPort() {
            public void materializeReadOnlyTmpfs(String workspace, String lease, SecretValue value) {}
            public void remove(String workspace, String lease) { removed.incrementAndGet(); }
        }, new SecretInjectionService.SecretLeaseStore() {
            public void save(SecretLease value) { metadata.put(value.leaseId(), value); }
            public SecretLease find(String id) { return metadata.get(id); }
        }, Clock.fixed(now, ZoneOffset.UTC));
        var checks = new AtomicInteger();
        var sessions = new DeploymentSecretSession(service, request -> checks.incrementAndGet(), Clock.fixed(now, ZoneOffset.UTC));
        var request = new DeploymentSecretSession.Request("invocation", "tenant", "account", "project", "workspace",
                "test", "sha256:"+"a".repeat(64), SecretLease.SecretType.GITHUB_INSTALLATION_TOKEN, now.plusSeconds(30));
        assertThrows(IllegalStateException.class, () -> sessions.execute(request, lease -> {
            assertEquals(SecretLease.Status.INJECTED, lease.status());
            throw new IllegalStateException("provider failed");
        }));
        assertEquals(2, checks.get());
        assertEquals(1, removed.get());
        assertEquals(1, revoked.get());
        assertEquals(SecretLease.Status.REVOKED, metadata.get("invocation").status());
        var denied = new DeploymentSecretSession(service, value -> { throw new SecurityException(); }, Clock.fixed(now, ZoneOffset.UTC));
        assertThrows(SecurityException.class, () -> denied.execute(request, lease -> null));
        assertEquals(1, revoked.get());
    }
}
