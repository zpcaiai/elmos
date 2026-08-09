package io.elmos.verifier;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.util.LinkedHashMap;
import java.util.Map;

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
            @Value("${elmos.verifier.java-homes:}") String additionalJavaHomes,
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
                mavenVerifiers(javaHome, additionalJavaHomes, mavenExecutable,
                        timeoutMinutes, dependencyCacheRoot),
                json,
                clock
        );
    }

    static Map<String, MavenVerification> mavenVerifiers(
            String java21Home,
            String additionalJavaHomes,
            String mavenExecutable,
            int timeoutMinutes,
            String dependencyCacheRoot
    ) {
        Map<String, Path> homes = new LinkedHashMap<>();
        homes.put("21", Path.of(java21Home));
        if (additionalJavaHomes != null && !additionalJavaHomes.isBlank()) {
            for (String raw : additionalJavaHomes.split(",")) {
                String entry = raw.trim();
                if (entry.isEmpty()) continue;
                int separator = entry.indexOf('=');
                if (separator <= 0 || separator == entry.length() - 1) {
                    throw new IllegalArgumentException(
                            "verifier java-homes entries must be <release>=<absolute-path>");
                }
                String release = entry.substring(0, separator).trim();
                if (!release.matches("[0-9]{1,2}")) {
                    throw new IllegalArgumentException("verifier Java release is invalid: " + release);
                }
                Path home = Path.of(entry.substring(separator + 1).trim());
                if (!home.isAbsolute()) {
                    throw new IllegalArgumentException(
                            "verifier JAVA_HOME for release " + release + " must be absolute");
                }
                homes.put(release, home);
            }
        }
        Path cache = dependencyCacheRoot == null || dependencyCacheRoot.isBlank()
                ? null : Path.of(dependencyCacheRoot);
        Map<String, MavenVerification> result = new LinkedHashMap<>();
        for (Map.Entry<String, Path> entry : homes.entrySet()) {
            result.put(entry.getKey(), new ProcessMavenVerification(
                    entry.getValue(), mavenExecutable, timeoutMinutes, cache, entry.getKey()));
        }
        return Map.copyOf(result);
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
