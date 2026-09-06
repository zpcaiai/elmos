package io.elmos.liveworkbench;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

final class LwDigest {
    private LwDigest() {}

    static String sha256(String value) { return sha256(value.getBytes(StandardCharsets.UTF_8)); }
    static String sha256(byte[] value) {
        try {
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    static boolean exact(String value) { return value != null && value.matches("sha256:[0-9a-f]{64}"); }
}
