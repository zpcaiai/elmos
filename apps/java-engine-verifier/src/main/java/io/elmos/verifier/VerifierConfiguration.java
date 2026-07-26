package io.elmos.verifier;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;

@Configuration
class VerifierConfiguration {
    @Bean
    Clock verifierClock() {
        return Clock.systemUTC();
    }

    @Bean
    SpringArtifactVerifier springArtifactVerifier(
            @Value("${elmos.verifier.id}") String verifierId,
            @Value("${elmos.verifier.input-root}") String inputRoot,
            @Value("${elmos.verifier.evidence-root}") String evidenceRoot,
            @Value("${elmos.verifier.secret-file}") String secretFile,
            @Value("${elmos.verifier.one-time-secret:}") String oneTimeSecret,
            @Value("${elmos.verifier.java-home}") String javaHome,
            @Value("${elmos.verifier.maven-executable}") String mavenExecutable,
            @Value("${elmos.verifier.dependency-cache-root:}") String dependencyCacheRoot,
            @Value("${elmos.verifier.timeout-minutes}") int timeoutMinutes,
            @Value("${elmos.verifier.auth-window-seconds}") long authWindowSeconds,
            ObjectMapper json,
            Clock clock
    ) {
        byte[] secret = oneTimeSecret.isBlank()
                ? readSecret(Path.of(secretFile))
                : oneTimeSecret.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        if (secret.length < 32 || secret.length > 4096) {
            throw new IllegalStateException("verifier HMAC secret must contain 32-4096 bytes");
        }
        return new SpringArtifactVerifier(
                verifierId,
                Path.of(inputRoot),
                Path.of(evidenceRoot),
                new VerifierAuthentication(secret, clock, authWindowSeconds),
                new ProcessMavenVerification(
                        Path.of(javaHome),
                        mavenExecutable,
                        timeoutMinutes,
                        dependencyCacheRoot.isBlank() ? null : Path.of(dependencyCacheRoot)
                ),
                json,
                clock
        );
    }

    private static byte[] readSecret(Path path) {
        try {
            if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) {
                throw new IllegalStateException("verifier HMAC secret file is unavailable");
            }
            byte[] raw = Files.readAllBytes(path);
            if (raw.length > 4096) throw new IllegalStateException("verifier HMAC secret file is too large");
            String value = new String(raw, java.nio.charset.StandardCharsets.UTF_8).trim();
            if (value.getBytes(java.nio.charset.StandardCharsets.UTF_8).length < 32) {
                throw new IllegalStateException("verifier HMAC secret must contain at least 32 bytes");
            }
            return value.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        } catch (IOException error) {
            throw new IllegalStateException("verifier HMAC secret file could not be read", error);
        }
    }
}
