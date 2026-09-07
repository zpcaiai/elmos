package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;

class CasDigestTest {

    @Test void digestCarriesAlgorithmLowercaseHexAndSize() {
        CasDigest digest = CasDigest.ofUtf8("elmos");
        assertEquals("sha256", digest.algorithm());
        assertEquals(64, digest.hex().length());
        assertEquals(digest.hex().toLowerCase(), digest.hex());
        assertEquals(5, digest.sizeBytes());
        assertEquals("sha256:" + digest.hex() + "/5", digest.compact());
        assertEquals(digest, CasDigest.parseCompact(digest.compact()));
    }

    @Test void uppercaseHexAndForeignAlgorithmsAreRefused() {
        CasDigest valid = CasDigest.ofUtf8("x");
        assertThrows(IllegalArgumentException.class,
                () -> new CasDigest("sha256", valid.hex().toUpperCase(), 1));
        assertThrows(IllegalArgumentException.class, () -> new CasDigest("sha1", valid.hex(), 1));
        assertThrows(IllegalArgumentException.class, () -> new CasDigest("sha256", valid.hex(), -1));
    }

    @Test void sizeIsPartOfIdentitySoTruncationCannotImpersonateTheOriginal() {
        CasDigest full = CasDigest.ofUtf8("abcdef");
        CasDigest sameHexWrongSize = new CasDigest("sha256", full.hex(), 3);
        assertNotEquals(full, sameHexWrongSize);
        assertFalse(sameHexWrongSize.matches("abcdef".getBytes(StandardCharsets.UTF_8)));
    }

    @Test void shardPathFansOutTwoLevels() {
        CasDigest digest = CasDigest.ofUtf8("shard");
        assertEquals("sha256/" + digest.hex().substring(0, 2) + "/" + digest.hex().substring(2, 4)
                + "/" + digest.hex(), digest.shardPath());
    }

    @Test void incrementalHashingMatchesSinglePassHashing() {
        byte[] content = "the quick brown fox".getBytes(StandardCharsets.UTF_8);
        CasHasher hasher = new CasHasher();
        hasher.update(content, 0, 4);
        hasher.update(content, 4, content.length - 4);
        assertEquals(CasDigest.of(content), hasher.finish());
    }
}
