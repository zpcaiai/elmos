package io.elmos.verifier;

import io.elmos.security.FileNonceStore;
import io.elmos.security.SpringHmacProtocol;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import static io.elmos.verifier.VerificationModels.Rejected;

final class VerifierAuthentication {
    private final byte[] secret;
    private final Clock clock;
    private final long windowSeconds;
    private final FileNonceStore nonces;

    VerifierAuthentication(
            byte[] secret,
            Clock clock,
            long windowSeconds,
            FileNonceStore nonces
    ) {
        this.secret = SpringHmacProtocol.requireSecret(secret, "verifier");
        this.clock = Objects.requireNonNull(clock);
        this.windowSeconds = windowSeconds;
        this.nonces = Objects.requireNonNull(nonces);
        if (secret.length < 32) throw new IllegalArgumentException("verifier HMAC secret must contain at least 32 bytes");
        if (windowSeconds < 30 || windowSeconds > 300) throw new IllegalArgumentException("verifier auth window must be 30-300 seconds");
    }

    void verify(String timestampValue, String nonce, String signature, byte[] body) {
        long now = clock.instant().getEpochSecond();
        long timestamp;
        if (!SpringHmacProtocol.isCanonicalTimestamp(timestampValue)) {
            throw rejected();
        }
        try {
            timestamp = Long.parseLong(timestampValue);
        } catch (NumberFormatException error) {
            throw rejected();
        }
        if (timestamp < now - windowSeconds
                || timestamp > now + windowSeconds
                || !SpringHmacProtocol.isCanonicalNonce(nonce)
                || signature == null
                || !signature.matches("[0-9a-f]{64}")) {
            throw rejected();
        }
        String expected = sign(secret, timestampValue, nonce, body);
        if (!MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII),
                signature.getBytes(StandardCharsets.US_ASCII))) {
            throw rejected();
        }
        boolean claimed;
        try {
            long expiry = Math.addExact(Math.max(now, timestamp), windowSeconds);
            claimed = nonces.claim(
                    SpringHmacProtocol.Role.VERIFIER,
                    "SPRING_VERIFIER_BROKER",
                    nonce,
                    Instant.ofEpochSecond(expiry));
        } catch (RuntimeException error) {
            throw rejected();
        }
        if (!claimed) {
            throw rejected();
        }
    }

    static String sign(byte[] secret, String timestamp, String nonce, byte[] body) {
        return SpringHmacProtocol.sign(
                secret, SpringHmacProtocol.Role.VERIFIER, timestamp, nonce, body);
    }

    static String sha256(byte[] value) {
        return SpringHmacProtocol.sha256(value);
    }

    private static Rejected rejected() {
        return new Rejected("UNAUTHORIZED", "Verifier request authentication failed.");
    }
}
