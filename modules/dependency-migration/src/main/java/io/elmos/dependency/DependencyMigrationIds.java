package io.elmos.dependency;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

final class DependencyMigrationIds {
    private DependencyMigrationIds() {}
    static String id(String prefix, Object... values) {
        StringBuilder canonical = new StringBuilder(prefix);
        for (Object value : values) canonical.append('\u001f').append(value == null ? "" : value);
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(canonical.toString().getBytes(StandardCharsets.UTF_8));
            return prefix + "-" + java.util.HexFormat.of().formatHex(digest, 0, 12);
        } catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
}
