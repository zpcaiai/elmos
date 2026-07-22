package io.elmos.secret;

import org.junit.jupiter.api.Test;
import java.time.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class SecretSecurityTest {
    @Test void clearsValuesAndRedactsExactAndStructuredSecrets() {
        SecretValue value = new SecretValue("sentinel-value".toCharArray()); value.close(); assertTrue(value.cleared());
        String output = "sentinel-value\nAuthorization: Bearer abc123\npassword=hunter2";
        String redacted = new SecretRedactor().redact(output, List.of("sentinel-value".toCharArray()));
        assertFalse(redacted.contains("sentinel-value")); assertFalse(redacted.contains("abc123")); assertFalse(redacted.contains("hunter2"));
    }

    @Test void injectsMetadataOnlyAndRevokesOnMaterializationFailure() {
        Instant now = Instant.parse("2026-07-20T00:00:00Z"); List<String> revoked = new ArrayList<>(); List<SecretLease> saved = new ArrayList<>();
        var provider = new SecretInjectionService.SecretProviderPort() {
            public SecretInjectionService.ProviderLease issue(SecretInjectionService.SecretRequest ignored) {
                return new SecretInjectionService.ProviderLease("provider-1", new SecretValue("sentinel-value".toCharArray()), now, now.plusSeconds(60));
            }
            public void revoke(String id) { revoked.add(id); }
        };
        var materializer = new SecretInjectionService.SecretMaterializerPort() {
            public void materializeReadOnlyTmpfs(String workspace, String lease, SecretValue value) { throw new IllegalStateException("disk failure"); }
            public void remove(String workspace, String lease) {}
        };
        var store = new SecretInjectionService.SecretLeaseStore() {
            public void save(SecretLease lease) { saved.add(lease); }
            public SecretLease find(String id) { return saved.getLast(); }
        };
        var service = new SecretInjectionService(provider, materializer, store, Clock.fixed(now, ZoneOffset.UTC));
        assertThrows(IllegalStateException.class, () -> service.inject("lease-1", new SecretInjectionService.SecretRequest("workspace-1", SecretLease.SecretType.MAVEN_SERVER_TOKEN, Duration.ofMinutes(1))));
        assertEquals(List.of("provider-1"), revoked);
        assertFalse(saved.toString().contains("sentinel-value"));
    }
}
