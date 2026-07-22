package io.elmos.scm;

import org.junit.jupiter.api.Test;
import java.time.*;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.jupiter.api.Assertions.*;

class GitHubInstallationTokenBrokerTest {
    private final Instant now = Instant.parse("2026-07-20T00:00:00Z");
    private final Clock clock = Clock.fixed(now, ZoneOffset.UTC);

    @Test void scopesTokenAndAuditsMetadataOnly() {
        AtomicReference<GitHubInstallationTokenBroker.LeaseMetadata> audit = new AtomicReference<>();
        GitHubInstallationTokenBroker broker = new GitHubInstallationTokenBroker((a,b,c) -> true,
                (installation, repository, permissions) -> new GitHubInstallationTokenBroker.TokenGrant(
                        "github_pat_secret".toCharArray(), now, now.plusSeconds(3600), permissions), audit::set, clock);
        EphemeralCredential credential = broker.issue("repo-1", 11, 22, GitHubInstallationTokenBroker.Operation.CAPTURE_SNAPSHOT);
        assertEquals(Set.of(new GitHubInstallationTokenBroker.Permission("contents", GitHubInstallationTokenBroker.Access.READ),
                new GitHubInstallationTokenBroker.Permission("metadata", GitHubInstallationTokenBroker.Access.READ)), audit.get().permissions());
        assertFalse(audit.get().toString().contains("github_pat_secret"));
        credential.close();
        assertTrue(credential.cleared());
        assertThrows(IllegalStateException.class, () -> credential.use(String::new));
    }

    @Test void rejectsUnauthorizedOverlongAndOverprivilegedGrants() {
        var denied = new GitHubInstallationTokenBroker((a,b,c) -> false, (a,b,c) -> null, ignored -> {}, clock);
        assertThrows(SecurityException.class, () -> denied.issue("repo", 1, 2, GitHubInstallationTokenBroker.Operation.CAPTURE_SNAPSHOT));
        var overlong = new GitHubInstallationTokenBroker((a,b,c) -> true,
                (a,b,permissions) -> new GitHubInstallationTokenBroker.TokenGrant("x".toCharArray(), now, now.plusSeconds(3601), permissions), ignored -> {}, clock);
        assertThrows(SecurityException.class, () -> overlong.issue("repo", 1, 2, GitHubInstallationTokenBroker.Operation.CAPTURE_SNAPSHOT));
        var broad = new GitHubInstallationTokenBroker((a,b,c) -> true,
                (a,b,permissions) -> new GitHubInstallationTokenBroker.TokenGrant("x".toCharArray(), now, now.plusSeconds(60),
                        Set.of(new GitHubInstallationTokenBroker.Permission("contents", GitHubInstallationTokenBroker.Access.WRITE))), ignored -> {}, clock);
        assertThrows(SecurityException.class, () -> broad.issue("repo", 1, 2, GitHubInstallationTokenBroker.Operation.CAPTURE_SNAPSHOT));
    }
}
