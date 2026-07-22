package io.elmos.workspaceservice;

import io.elmos.secret.SecretInjectionService;
import io.elmos.secret.SecretLease;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.*;

class DirectorySecretProviderTest {
    @TempDir Path root;

    @Test void issuesBoundedLeaseAndConsumesProviderFileOnRevoke() throws Exception {
        Path secretFile = root.resolve("ws-1.GITHUB_INSTALLATION_TOKEN.secret");
        Files.writeString(secretFile, "ephemeral-installation-token");
        try { Files.setPosixFilePermissions(secretFile, PosixFilePermissions.fromString("rw-------")); }
        catch (UnsupportedOperationException ignored) { }
        Instant now = Instant.parse("2026-07-20T00:00:00Z");
        DirectorySecretProvider provider = new DirectorySecretProvider(root, Clock.fixed(now, ZoneOffset.UTC));

        var lease = provider.issue(new SecretInjectionService.SecretRequest("ws-1",
                SecretLease.SecretType.GITHUB_INSTALLATION_TOKEN, Duration.ofMinutes(10)));
        assertEquals(now, lease.issuedAt());
        assertEquals(now.plus(Duration.ofMinutes(10)), lease.expiresAt());
        assertEquals("ephemeral-installation-token", lease.value().use(String::new));
        lease.value().close();

        provider.revoke(lease.providerLeaseId());
        assertFalse(Files.exists(secretFile));
        assertDoesNotThrow(() -> provider.revoke(lease.providerLeaseId()));
    }

    @Test void rejectsGroupReadableProviderFiles() throws Exception {
        Path secretFile = root.resolve("ws-2.NEXUS_READ_TOKEN.secret");
        Files.writeString(secretFile, "must-not-be-readable-by-group");
        try { Files.setPosixFilePermissions(secretFile, PosixFilePermissions.fromString("rw-r-----")); }
        catch (UnsupportedOperationException ignored) { return; }
        DirectorySecretProvider provider = new DirectorySecretProvider(root, Clock.systemUTC());
        assertThrows(SecurityException.class, () -> provider.issue(new SecretInjectionService.SecretRequest(
                "ws-2", SecretLease.SecretType.NEXUS_READ_TOKEN, Duration.ofMinutes(5))));
    }
}
