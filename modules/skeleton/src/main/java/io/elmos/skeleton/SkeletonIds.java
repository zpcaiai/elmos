package io.elmos.skeleton;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

final class SkeletonIds {
    private SkeletonIds() {}
    static String id(String prefix, Object... parts) { StringBuilder value = new StringBuilder("skeleton-id-v1"); for (Object part : parts) value.append('\0').append(part); try { return prefix + ":" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.toString().getBytes(StandardCharsets.UTF_8))); } catch (Exception error) { throw new IllegalStateException(error); } }
    static String hash(byte[] bytes) { try { return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); } catch (Exception error) { throw new IllegalStateException(error); } }
}
