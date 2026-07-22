package io.elmos.marketplace;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

final class Digests {
    private Digests() {}
    static String sha256(byte[] value) {
        try { return "sha256:"+HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    static boolean exact(String value) { return value!=null && value.matches("sha256:[0-9a-f]{64}"); }
}
