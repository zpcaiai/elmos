package io.elmos.verifier;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.HexFormat;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

import static io.elmos.verifier.VerificationModels.Rejected;

final class VerifierAuthentication {
    private final byte[] secret;
    private final Clock clock;
    private final long windowSeconds;
    private final Map<String, Long> nonces = new ConcurrentHashMap<>();

    VerifierAuthentication(byte[] secret, Clock clock, long windowSeconds) {
        this.secret = Objects.requireNonNull(secret).clone();
        this.clock = Objects.requireNonNull(clock);
        this.windowSeconds = windowSeconds;
        if (secret.length < 32) throw new IllegalArgumentException("verifier HMAC secret must contain at least 32 bytes");
        if (windowSeconds < 30 || windowSeconds > 300) throw new IllegalArgumentException("verifier auth window must be 30-300 seconds");
    }

    void verify(String timestampValue, String nonce, String signature, byte[] body) {
        long now = clock.instant().getEpochSecond();
        long timestamp;
        try {
            timestamp = Long.parseLong(Objects.toString(timestampValue, ""));
        } catch (NumberFormatException error) {
            throw rejected();
        }
        if (Math.abs(now - timestamp) > windowSeconds
                || nonce == null
                || !nonce.matches("[0-9a-fA-F-]{36}")
                || signature == null
                || !signature.matches("[0-9a-f]{64}")) {
            throw rejected();
        }
        nonces.entrySet().removeIf(entry -> entry.getValue() < now - windowSeconds);
        if (nonces.putIfAbsent(nonce, timestamp) != null) throw rejected();
        String expected = sign(secret, timestampValue, nonce, body);
        if (!MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII),
                signature.getBytes(StandardCharsets.US_ASCII))) {
            nonces.remove(nonce, timestamp);
            throw rejected();
        }
    }

    static String sign(byte[] secret, String timestamp, String nonce, byte[] body) {
        try {
            String bodySha = sha256(body);
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] signed = (timestamp + "\n" + nonce + "\n" + bodySha).getBytes(StandardCharsets.UTF_8);
            return HexFormat.of().formatHex(mac.doFinal(signed));
        } catch (Exception error) {
            throw new IllegalStateException("HMAC-SHA256 is unavailable", error);
        }
    }

    static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }

    private static Rejected rejected() {
        return new Rejected("UNAUTHORIZED", "Verifier request authentication failed.");
    }
}
