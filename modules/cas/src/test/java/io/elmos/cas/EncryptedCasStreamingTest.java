package io.elmos.cas;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.Executors;
import static org.junit.jupiter.api.Assertions.*;

class EncryptedCasStreamingTest {
    @TempDir Path root;

    private TenantEncryption.AesGcm encryption() {
        return new TenantEncryption.AesGcm().registerKey("tenant", "v1", new byte[32], true);
    }

    private static byte[] bytes(int size) {
        byte[] value = new byte[size];
        new java.util.Random(915L + size).nextBytes(value);
        return value;
    }

    private static Path object(Path storage) throws Exception {
        try (var walk = Files.walk(storage.resolve("tenants"))) {
            return walk.filter(path -> path.toString().endsWith(".enc")).findFirst().orElseThrow();
        }
    }

    @Test void byteAndStreamWritesUseV3AcrossFrameBoundariesIncludingEmpty() throws Exception {
        int index = 0;
        for (int size : List.of(0, 1, 65535, 65536, 65537, 196608)) {
            Path location = root.resolve("case-" + index++);
            var store = new TenantEncryptedLocalCasStore("encrypted", location, encryption()).forTenant("tenant");
            byte[] value = bytes(size);
            var digest = CasDigest.of(value);
            if (size % 2 == 0) store.put(digest, value);
            else store.putDurable(digest, new ByteArrayInputStream(value));
            try (var file = Files.newInputStream(object(location))) {
                assertArrayEquals(FramedTenantCipher.MAGIC, file.readNBytes(FramedTenantCipher.MAGIC.length));
            }
            try (var input = store.openVerified(digest)) { assertArrayEquals(value, input.readAllBytes()); }
        }
    }

    @Test void finalFrameCorruptionTruncationAndTrailingDataExposeNoStream() throws Exception {
        for (String mutation : List.of("last-tag", "truncated", "trailing", "header", "frame-order")) {
            Path location = root.resolve(mutation);
            var store = new TenantEncryptedLocalCasStore("encrypted", location, encryption()).forTenant("tenant");
            byte[] value = bytes(2 * FramedTenantCipher.CHUNK_BYTES);
            var digest = CasDigest.of(value);
            store.put(digest, value);
            Path file = object(location);
            byte[] encoded = Files.readAllBytes(file);
            switch (mutation) {
                case "last-tag" -> encoded[encoded.length - 1] ^= 1;
                case "truncated" -> encoded = Arrays.copyOf(encoded, encoded.length - 1);
                case "trailing" -> encoded = Arrays.copyOf(encoded, encoded.length + 1);
                case "header" -> encoded[FramedTenantCipher.MAGIC.length] = 'z';
                case "frame-order" -> {
                    int frame = FramedTenantCipher.CHUNK_BYTES + 16;
                    int start = encoded.length - 2 * frame;
                    byte[] first = Arrays.copyOfRange(encoded, start, start + frame);
                    System.arraycopy(encoded, start + frame, encoded, start, frame);
                    System.arraycopy(first, 0, encoded, start + frame, frame);
                }
                default -> throw new AssertionError();
            }
            Files.write(file, encoded);
            assertThrows(CasExceptions.CasCorruptionException.class, () -> store.openVerified(digest), mutation);
            assertFalse(store.contains(digest), mutation);
        }
    }

    @Test void verifiedPlaintextStreamIsIndependentOfLaterCiphertextMutation() throws Exception {
        Path location = root.resolve("immutable");
        var store = new TenantEncryptedLocalCasStore("encrypted", location, encryption()).forTenant("tenant");
        byte[] value = bytes(200000);
        var digest = CasDigest.of(value);
        store.put(digest, value);
        try (var input = store.openVerified(digest)) {
            Files.write(object(location), new byte[1]);
            assertArrayEquals(value, input.readAllBytes());
        }
    }

    @Test void wrongLengthOrDigestNeverPublishesAndStagingIsCleaned() throws Exception {
        Path location = root.resolve("invalid");
        var store = new TenantEncryptedLocalCasStore("encrypted", location, encryption()).forTenant("tenant");
        var digest = CasDigest.of(bytes(100));
        assertThrows(IllegalArgumentException.class,
                () -> store.putDurable(digest, new ByteArrayInputStream(bytes(99))));
        assertThrows(CasExceptions.CasCorruptionException.class,
                () -> store.putDurable(digest, new ByteArrayInputStream(new byte[100])));
        assertFalse(store.contains(digest));
        try (var staging = Files.list(location.resolve("staging"))) { assertEquals(0, staging.count()); }
    }

    @Test void rotationKeepsOldObjectsAndCrossTenantCiphertextFailsAuthentication() throws Exception {
        Path location = root.resolve("rotation");
        var keys = encryption();
        keys.registerKey("other", "v1", new byte[32], true);
        var backend = new TenantEncryptedLocalCasStore("encrypted", location, keys);
        var store = backend.forTenant("tenant");
        byte[] value = bytes(150000);
        var digest = CasDigest.of(value);
        store.put(digest, value);
        Path first = object(location);
        keys.registerKey("tenant", "v2", bytes(32), true);
        assertArrayEquals(value, store.get(digest));
        var other = backend.forTenant("other");
        other.put(digest, value);
        Path second;
        try (var walk = Files.walk(location.resolve("tenants"))) {
            second = walk.filter(path -> path.toString().endsWith(".enc") && !path.equals(first)).findFirst().orElseThrow();
        }
        Files.copy(first, second, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        assertThrows(CasExceptions.CasCorruptionException.class, () -> other.openVerified(digest));
        assertArrayEquals(value, store.get(digest));
    }

    @Test void parallelIdenticalPublishersVerifyImmutableWinner() throws Exception {
        Path location = root.resolve("parallel");
        var backend = new TenantEncryptedLocalCasStore("encrypted", location, encryption());
        byte[] value = bytes(512000);
        var digest = CasDigest.of(value);
        try (var pool = Executors.newFixedThreadPool(4)) {
            var futures = java.util.stream.IntStream.range(0, 4).mapToObj(index -> pool.submit(() -> {
                backend.forTenant("tenant").putDurable(digest, new ByteArrayInputStream(value));
                return backend.forTenant("tenant").get(digest);
            })).toList();
            for (var future : futures) assertArrayEquals(value, future.get());
        }
    }

    @Test void legacyReadThenStreamToNewRootProducesV3AndLegacyBudgetFailsClosed() throws Exception {
        var keys = encryption();
        Path legacyRoot = root.resolve("legacy");
        var legacy = new TenantEncryptedLocalCasStore("encrypted", legacyRoot, keys).forTenant("tenant");
        byte[] value = bytes(100000);
        var digest = CasDigest.of(value);
        legacy.put(digest, value); // Establish the exact tenant-owned object path.
        var envelope = keys.seal("tenant", digest, value);
        byte[] id = envelope.keyId().getBytes(StandardCharsets.US_ASCII);
        var encoded = new java.io.ByteArrayOutputStream();
        encoded.write("ELMOS-CAS-ENC/2\n".getBytes(StandardCharsets.US_ASCII));
        encoded.write(id.length);
        encoded.write(id);
        encoded.write(envelope.ciphertext());
        Files.write(object(legacyRoot), encoded.toByteArray());
        Path nextRoot = root.resolve("migrated");
        var next = new TenantEncryptedLocalCasStore("encrypted", nextRoot, keys).forTenant("tenant");
        try (var input = legacy.openVerified(digest)) { next.putDurable(digest, input); }
        assertArrayEquals(value, next.get(digest));
        try (var input = Files.newInputStream(object(nextRoot))) {
            assertArrayEquals(FramedTenantCipher.MAGIC, input.readNBytes(FramedTenantCipher.MAGIC.length));
        }
        var limited = new TenantEncryptedLocalCasStore("limited", legacyRoot, keys, 1000000, 10).forTenant("tenant");
        assertThrows(IllegalArgumentException.class, () -> limited.openVerified(digest));
        assertTrue(limited.contains(digest), "budget rejection is not ciphertext corruption");
    }
}
