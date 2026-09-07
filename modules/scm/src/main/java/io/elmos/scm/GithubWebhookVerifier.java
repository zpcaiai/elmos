package io.elmos.scm;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;

public final class GithubWebhookVerifier {
    public boolean verify(byte[] rawBody, String signatureHeader, List<char[]> activeSecrets) {
        if (rawBody == null || signatureHeader == null || !signatureHeader.startsWith("sha256=") || activeSecrets == null) return false;
        byte[] supplied;
        try { supplied = HexFormat.of().parseHex(signatureHeader.substring(7)); }
        catch (IllegalArgumentException exception) { return false; }
        if (supplied.length != 32) return false;
        boolean valid = false;
        for (char[] secret : activeSecrets) {
            if (secret == null || secret.length == 0) continue;
            ByteBuffer encoded = StandardCharsets.UTF_8.encode(CharBuffer.wrap(secret));
            byte[] key = new byte[encoded.remaining()]; encoded.get(key);
            try {
                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(new SecretKeySpec(key, "HmacSHA256"));
                valid |= MessageDigest.isEqual(mac.doFinal(rawBody), supplied);
            } catch (Exception exception) {
                throw new IllegalStateException("HMAC-SHA-256 is unavailable", exception);
            } finally {
                java.util.Arrays.fill(key, (byte) 0);
            }
        }
        return valid;
    }
}
