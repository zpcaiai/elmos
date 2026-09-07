package io.elmos.integrations;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GitHubCloneUriPolicyTest {
    @Test void acceptsOnlyTheConfiguredCredentialFreeGitHubOriginAndPath() {
        var policy = new GitHubCloneUriPolicy("https://github.example.test/source");

        assertEquals("https://github.example.test/source/acme/repository.git",
                policy.requireAllowed(
                        "https://github.example.test/source/acme/repository.git").toString());
        assertThrows(SecurityException.class,
                () -> policy.requireAllowed("file:///tmp/repository"));
        assertThrows(SecurityException.class,
                () -> policy.requireAllowed("https://evil.example/source/acme/repository.git"));
        assertThrows(SecurityException.class,
                () -> policy.requireAllowed(
                        "https://token@github.example.test/source/acme/repository.git"));
        assertThrows(SecurityException.class,
                () -> policy.requireAllowed(
                        "https://github.example.test/source/acme/repository.git?redirect=evil"));
        assertThrows(SecurityException.class,
                () -> policy.requireAllowed(
                        "https://github.example.test/source/acme/%2e%2e.git"));
        assertThrows(SecurityException.class,
                () -> policy.requireAllowed(
                        "https://github.example.test/other/acme/repository.git"));
    }

    @Test void rejectsUnsafeCloneBaseConfiguration() {
        assertThrows(SecurityException.class,
                () -> new GitHubCloneUriPolicy("http://github.example.test"));
        assertThrows(SecurityException.class,
                () -> new GitHubCloneUriPolicy("https://user@github.example.test"));
        assertThrows(SecurityException.class,
                () -> new GitHubCloneUriPolicy("https://github.example.test/%2e%2e"));
    }
}
