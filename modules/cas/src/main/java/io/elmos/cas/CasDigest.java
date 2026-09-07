package io.elmos.cas;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Pattern;

/**
 * ELMOS-CAS-001. The single digest representation used by every content-addressed
 * surface: algorithm, lowercase hex, and the exact byte size of the addressed content.
 *
 * <p>The size is part of the identity on purpose. A digest without a size cannot detect a
 * truncated transfer that happens to be aborted at a chunk boundary, and it cannot be used
 * to pre-allocate or to reject an oversized upload before the bytes are spent.
 *
 * <p>Wire form matches {@code schemas/digest.schema.json}: {@code algorithm} / {@code hex} /
 * {@code size_bytes}. The compact form {@code sha256:<hex>/<size>} is used inside canonical
 * key encodings where a nested object would add ambiguity.
 */
public record CasDigest(String algorithm, String hex, long sizeBytes) implements Comparable<CasDigest> {

    public static final String ALGORITHM = "sha256";
    private static final Pattern HEX = Pattern.compile("^[0-9a-f]{64}$");
    private static final Pattern COMPACT = Pattern.compile("^sha256:([0-9a-f]{64})/(\\d+)$");

    public CasDigest {
        if (!ALGORITHM.equals(algorithm)) {
            throw new IllegalArgumentException("unsupported digest algorithm: " + algorithm);
        }
        if (hex == null || !HEX.matcher(hex).matches()) {
            throw new IllegalArgumentException("digest hex must be 64 lowercase hex characters: " + hex);
        }
        if (sizeBytes < 0) {
            throw new IllegalArgumentException("digest size must not be negative: " + sizeBytes);
        }
    }

    public static CasDigest of(byte[] content) {
        return new CasDigest(ALGORITHM, HexFormat.of().formatHex(sha256().digest(content)), content.length);
    }

    /**
     * Digests text as UTF-8. Callers must never route file content through this method:
     * ELMOS-CAS-004 forbids implicit encoding or line-ending normalisation, and file bytes are
     * always hashed exactly as they were read.
     */
    public static CasDigest ofUtf8(String text) {
        return of(text.getBytes(StandardCharsets.UTF_8));
    }

    public static CasDigest parseCompact(String compact) {
        var matcher = COMPACT.matcher(compact);
        if (!matcher.matches()) {
            throw new IllegalArgumentException("not a compact digest: " + compact);
        }
        return new CasDigest(ALGORITHM, matcher.group(1), Long.parseLong(matcher.group(2)));
    }

    public String compact() {
        return ALGORITHM + ":" + hex + "/" + sizeBytes;
    }

    /** Two-level fan-out keeps directory entry counts sane on local disk tiers. */
    public String shardPath() {
        return ALGORITHM + "/" + hex.substring(0, 2) + "/" + hex.substring(2, 4) + "/" + hex;
    }

    public boolean matches(byte[] content) {
        return content.length == sizeBytes && hex.equals(HexFormat.of().formatHex(sha256().digest(content)));
    }

    @Override
    public int compareTo(CasDigest other) {
        int byHex = hex.compareTo(other.hex);
        return byHex != 0 ? byHex : Long.compare(sizeBytes, other.sizeBytes);
    }

    @Override
    public String toString() {
        return compact();
    }

    static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is required by the platform", error);
        }
    }
}
