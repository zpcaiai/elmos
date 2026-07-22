package io.elmos.integrations;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

import static org.junit.jupiter.api.Assertions.*;

class LocalContentAddressedArtifactStoreTest {
    @TempDir Path root;
    @Test void storesByVerifiedDigestAndReusesImmutableContent() throws Exception {
        byte[] bytes = "artifact".getBytes(StandardCharsets.UTF_8);
        String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        LocalContentAddressedArtifactStore store = new LocalContentAddressedArtifactStore(root, 1024);
        String first = store.putIfAbsent(digest, bytes.length, new ByteArrayInputStream(bytes), "application/octet-stream");
        String second = store.putIfAbsent(digest, bytes.length, new ByteArrayInputStream(bytes), "application/octet-stream");
        assertEquals(first, second); assertArrayEquals(bytes, store.open(first).readAllBytes());
        assertThrows(SecurityException.class, () -> store.putIfAbsent("0".repeat(64), bytes.length, new ByteArrayInputStream(bytes), "application/octet-stream"));
    }
}
