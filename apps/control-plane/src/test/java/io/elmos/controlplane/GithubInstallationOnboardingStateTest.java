package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.junit.jupiter.api.Assertions.*;

class GithubInstallationOnboardingStateTest {
    private static final Instant NOW = Instant.parse("2026-07-26T00:00:00Z");
    private final GithubInstallationOnboardingService.StateCodec codec =
            new GithubInstallationOnboardingService.StateCodec(
                    "0123456789abcdef0123456789abcdef".getBytes(),
                    new ObjectMapper().findAndRegisterModules(),
                    Clock.fixed(NOW, ZoneOffset.UTC)
            );

    @Test
    void authenticatesExactInstallStateAndRejectsTamperingAndStageConfusion() {
        var claims = new GithubInstallationOnboardingService.Claims(
                1,
                GithubInstallationOnboardingService.Stage.INSTALL,
                "org-a",
                "connection-a",
                "abcdefghijklmnopqrstuvwxyz0123456789_-ABCDE",
                null,
                NOW.plusSeconds(600)
        );

        String encoded = codec.encode(claims);

        assertEquals(claims, codec.decode(
                encoded, GithubInstallationOnboardingService.Stage.INSTALL));
        assertThrows(SecurityException.class, () -> codec.decode(
                encoded.substring(0, encoded.length() - 1) + "A",
                GithubInstallationOnboardingService.Stage.INSTALL));
        assertThrows(SecurityException.class, () -> codec.decode(
                encoded, GithubInstallationOnboardingService.Stage.OAUTH));
    }

    @Test
    void derivesBoundedDeterministicPkceVerifierWithoutExposingStateSecret() {
        String first = codec.pkceVerifier(
                "abcdefghijklmnopqrstuvwxyz0123456789_-ABCDE");
        String second = codec.pkceVerifier(
                "abcdefghijklmnopqrstuvwxyz0123456789_-ABCDE");
        String different = codec.pkceVerifier(
                "abcdefghijklmnopqrstuvwxyz0123456789_-ABCDF");

        assertEquals(first, second);
        assertNotEquals(first, different);
        assertEquals(43, first.length());
        assertFalse(first.contains("="));
    }
}
