package io.elmos.integrations;

import io.elmos.snapshot.SnapshotPorts;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class LocalContentAddressedArtifactStoreTest {
    @TempDir Path root;
    @Test void storesByVerifiedDigestAndReusesImmutableContent() throws Exception {
        byte[] bytes = "artifact".getBytes(StandardCharsets.UTF_8);
        String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        LocalContentAddressedArtifactStore store = new LocalContentAddressedArtifactStore(root, 1024);
        var resource = new SnapshotPorts.ArtifactResourceContext("org-a", "repo-a");
        String first = store.putIfAbsent(resource, digest, bytes.length,
                new ByteArrayInputStream(bytes), "application/octet-stream");
        String second = store.putIfAbsent(resource, digest, bytes.length,
                new ByteArrayInputStream(bytes), "application/octet-stream");
        assertEquals(first, second);
        assertArrayEquals(bytes, store.open(resource, first).readAllBytes());
        assertDoesNotThrow(() -> store.retainSnapshot(
                resource, "snapshot-existing", List.of(first)));
        assertThrows(SecurityException.class, () -> store.putIfAbsent(resource,
                "0".repeat(64), bytes.length, new ByteArrayInputStream(bytes),
                "application/octet-stream"));

        Files.writeString(store.pathFor(first), "tampered");
        assertThrows(SecurityException.class, () -> store.open(resource, first),
                "legacy dual-read must verify the digest before returning bytes");
        assertThrows(SecurityException.class, () -> store.retainSnapshot(
                resource, "snapshot-existing", List.of(first)),
                "legacy reusable snapshots must be revalidated before return");
    }
}
