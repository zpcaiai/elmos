package io.elmos.cas;

import java.security.MessageDigest;
import java.util.HexFormat;

/**
 * Incremental SHA-256 accumulator used by chunked transfer (ELMOS-CAS-008/009) so a
 * multi-gigabyte blob never has to be held in memory to learn its identity.
 *
 * <p>Not thread safe. One hasher belongs to exactly one upload session and one session is
 * advanced by one writer at a time; the session object is what serialises concurrent chunks.
 */
public final class CasHasher {

    private final MessageDigest digest = CasDigest.sha256();
    private long length;

    public CasHasher update(byte[] chunk) {
        return update(chunk, 0, chunk.length);
    }

    public CasHasher update(byte[] chunk, int offset, int length) {
        digest.update(chunk, offset, length);
        this.length += length;
        return this;
    }

    public long length() {
        return length;
    }

    /** Terminal: the hasher must not be reused after this call. */
    public CasDigest finish() {
        return new CasDigest(CasDigest.ALGORITHM, HexFormat.of().formatHex(digest.digest()), length);
    }
}
