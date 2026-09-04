package io.elmos.worker;

import io.elmos.security.FileNonceStore;
import io.elmos.security.SpringHmacProtocol;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import io.elmos.worker.EphemeralTransformerController.Rejected;

final class EphemeralTransformerAuthentication {
    private final byte[] secret;
    private final Clock clock;
    private final long windowSeconds;
    private final FileNonceStore nonces;

    EphemeralTransformerAuthentication(
            byte[] secret,
            Clock clock,
            long windowSeconds,
            FileNonceStore nonces
    ) {
        this.secret = SpringHmacProtocol.requireSecret(secret, "ephemeral transformer");
        this.clock = Objects.requireNonNull(clock);
        this.windowSeconds = windowSeconds;
        this.nonces = Objects.requireNonNull(nonces);
        if (windowSeconds < 30 || windowSeconds > 300) {
            throw new IllegalStateException(
                    "ephemeral transformer auth window must be 30-300 seconds");
        }
    }

    void verify(String timestampValue, String nonce, String signature, byte[] body) {
        long now = clock.instant().getEpochSecond();
        long timestamp;
        if (!SpringHmacProtocol.isCanonicalTimestamp(timestampValue)) {
            throw unauthorized();
        }
        try {
            timestamp = Long.parseLong(timestampValue);
        } catch (NumberFormatException error) {
            throw unauthorized();
        }
        if (timestamp < now - windowSeconds
                || timestamp > now + windowSeconds
                || !SpringHmacProtocol.isCanonicalNonce(nonce)
                || signature == null
                || !signature.matches("[0-9a-f]{64}")) {
            throw unauthorized();
        }
        String expected = sign(secret, timestampValue, nonce, body);
        if (!MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII),
                signature.getBytes(StandardCharsets.US_ASCII))) {
            throw unauthorized();
        }
        boolean claimed;
        try {
            long expiry = Math.addExact(Math.max(now, timestamp), windowSeconds);
            claimed = nonces.claim(
                    SpringHmacProtocol.Role.TRANSFORMER,
                    "SPRING_TRANSFORMER_BROKER",
                    nonce,
                    Instant.ofEpochSecond(expiry));
        } catch (RuntimeException error) {
            throw unauthorized();
        }
        if (!claimed) {
            throw unauthorized();
        }
    }

    static String sign(byte[] secret, String timestamp, String nonce, byte[] body) {
        return SpringHmacProtocol.sign(
                secret, SpringHmacProtocol.Role.TRANSFORMER, timestamp, nonce, body);
    }

    private static Rejected unauthorized() {
        return new Rejected("UNAUTHORIZED", "Ephemeral transformer authentication failed.");
    }
}
