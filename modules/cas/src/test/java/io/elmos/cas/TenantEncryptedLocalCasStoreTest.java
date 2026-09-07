package io.elmos.cas;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TenantEncryptedLocalCasStoreTest {

    @TempDir Path temporary;

    @Test void plaintextNeverReachesDiskAndASecondInstanceCanReadTheObject() throws Exception {
        TenantEncryption.AesGcm encryption = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 1), true);
        Path root = temporary.resolve("cas");
        TenantEncryptedLocalCasStore first = new TenantEncryptedLocalCasStore(
                "encrypted", root, encryption);
        CasStore writer = first.forTenant("tenant-a");
        byte[] plaintext = "highly distinctive private source bytes".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        writer.put(digest, plaintext);

        List<Path> encryptedFiles;
        try (var walk = Files.walk(root.resolve("tenants"))) {
            encryptedFiles = walk.filter(path -> path.getFileName().toString().endsWith(".enc")).toList();
        }
        assertTrue(encryptedFiles.size() == 1);
        assertFalse(new String(Files.readAllBytes(encryptedFiles.get(0)), StandardCharsets.UTF_8)
                .contains("highly distinctive private source bytes"));

        TenantEncryptedLocalCasStore restarted = new TenantEncryptedLocalCasStore(
                "encrypted", root, encryption);
        assertArrayEquals(plaintext, restarted.forTenant("tenant-a").get(digest));
    }

    @Test void identicalPlaintextHasDifferentTenantCiphertextAndNamespaces() throws Exception {
        TenantEncryption.AesGcm encryption = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 1), true)
                .registerKey("tenant-b", "v1", key((byte) 2), true);
        Path root = temporary.resolve("cas");
        TenantEncryptedLocalCasStore store = new TenantEncryptedLocalCasStore(
                "encrypted", root, encryption);
        byte[] plaintext = "same private source".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        store.forTenant("tenant-a").put(digest, plaintext);
        store.forTenant("tenant-b").put(digest, plaintext);

        List<byte[]> physical;
        try (var walk = Files.walk(root.resolve("tenants"))) {
            physical = walk.filter(path -> path.getFileName().toString().endsWith(".enc"))
                    .sorted().map(path -> {
                        try {
                            return Files.readAllBytes(path);
                        } catch (java.io.IOException error) {
                            throw new java.io.UncheckedIOException(error);
                        }
                    }).toList();
        }
        assertTrue(physical.size() == 2);
        assertFalse(java.util.Arrays.equals(physical.get(0), physical.get(1)));
        assertArrayEquals(plaintext, store.forTenant("tenant-a").get(digest));
        assertArrayEquals(plaintext, store.forTenant("tenant-b").get(digest));
    }

    @Test void authenticatedCiphertextTamperingIsQuarantined() throws Exception {
        TenantEncryption.AesGcm encryption = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 3), true);
        Path root = temporary.resolve("cas");
        CasStore store = new TenantEncryptedLocalCasStore("encrypted", root, encryption)
                .forTenant("tenant-a");
        byte[] plaintext = "artifact".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        store.put(digest, plaintext);
        Path encrypted;
        try (var walk = Files.walk(root.resolve("tenants"))) {
            encrypted = walk.filter(path -> path.getFileName().toString().endsWith(".enc"))
                    .findFirst().orElseThrow();
        }
        byte[] tampered = Files.readAllBytes(encrypted);
        tampered[tampered.length - 1] ^= 1;
        Files.write(encrypted, tampered);

        assertThrows(CasExceptions.CasCorruptionException.class, () -> store.get(digest));
        assertFalse(store.contains(digest));
        try (var walk = Files.walk(root.resolve("quarantine"))) {
            assertTrue(walk.anyMatch(path -> path.getFileName().toString().endsWith(".poisoned")));
        }
    }

    @Test void malformedEnvelopeIsReportedAsCorruptionAndQuarantined() throws Exception {
        TenantEncryption.AesGcm encryption = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 4), true);
        Path root = temporary.resolve("malformed-cas");
        CasStore store = new TenantEncryptedLocalCasStore("encrypted", root, encryption)
                .forTenant("tenant-a");
        byte[] plaintext = "artifact".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        store.put(digest, plaintext);
        Path encrypted;
        try (var walk = Files.walk(root.resolve("tenants"))) {
            encrypted = walk.filter(path -> path.getFileName().toString().endsWith(".enc"))
                    .findFirst().orElseThrow();
        }
        Files.write(encrypted, "not-an-envelope".getBytes(StandardCharsets.US_ASCII));

        assertThrows(CasExceptions.CasCorruptionException.class, () -> store.get(digest));
        assertFalse(store.contains(digest));
    }

    @Test void aDisabledEncryptionAdapterCannotMasqueradeAsEncryptedStorage() {
        assertThrows(IllegalArgumentException.class, () -> new TenantEncryptedLocalCasStore(
                "encrypted", temporary.resolve("cas"), TenantEncryption.disabled()));
    }

    @Test void symlinkedStorageRootsAndControlDirectoriesFailClosed() throws Exception {
        TenantEncryption.AesGcm encryption = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 5), true);
        Path externalRoot = Files.createDirectory(temporary.resolve("external-root"));
        Path linkedRoot = temporary.resolve("linked-root");
        Files.createSymbolicLink(linkedRoot, externalRoot);
        assertThrows(IllegalArgumentException.class,
                () -> new TenantEncryptedLocalCasStore("encrypted", linkedRoot, encryption));

        for (String controlDirectory : List.of("tenants", "staging", "quarantine")) {
            Path root = Files.createDirectory(temporary.resolve("cas-" + controlDirectory));
            Path external = Files.createDirectory(temporary.resolve("external-" + controlDirectory));
            Files.createSymbolicLink(root.resolve(controlDirectory), external);
            assertThrows(IllegalArgumentException.class,
                    () -> new TenantEncryptedLocalCasStore("encrypted", root, encryption));
        }
    }

    @Test void rangeReadsAreOverVerifiedPlaintext() {
        TenantEncryption.AesGcm encryption = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 5), true);
        CasStore store = new TenantEncryptedLocalCasStore("encrypted", temporary.resolve("cas"), encryption)
                .forTenant("tenant-a");
        byte[] plaintext = "0123456789".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        store.put(digest, plaintext);
        assertArrayEquals("3456".getBytes(StandardCharsets.UTF_8), store.readRange(digest, 3, 4));
        assertNotEquals(0, store.totalBytes());
    }

    @Test void unavailableOldKeyVersionDoesNotQuarantineValidCiphertext() throws Exception {
        Path root = temporary.resolve("rotated-cas");
        TenantEncryption.AesGcm originalKeys = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 1), true);
        CasStore writer = new TenantEncryptedLocalCasStore("encrypted", root, originalKeys)
                .forTenant("tenant-a");
        byte[] plaintext = "old-key artifact".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        writer.put(digest, plaintext);

        TenantEncryption.AesGcm rotatedWithoutOldKey = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v2", key((byte) 2), true);
        CasStore reader = new TenantEncryptedLocalCasStore(
                "encrypted", root, rotatedWithoutOldKey).forTenant("tenant-a");

        CasExceptions.CasAccessDeniedException unavailable = assertThrows(
                CasExceptions.CasAccessDeniedException.class, () -> reader.get(digest));
        assertTrue("TENANT_KEY_VERSION_MISSING".equals(unavailable.reason()));
        assertTrue(reader.contains(digest));
        assertFalse(hasPoisonedFile(root));
    }

    @Test void keyProviderIoFailureDoesNotQuarantineValidCiphertext() throws Exception {
        Path root = temporary.resolve("key-io-cas");
        TenantEncryption.AesGcm working = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 3), true);
        CasStore writer = new TenantEncryptedLocalCasStore("encrypted", root, working)
                .forTenant("tenant-a");
        byte[] plaintext = "provider unavailable artifact".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        writer.put(digest, plaintext);

        TenantEncryption unavailable = new TenantEncryption() {
            @Override public byte[] encrypt(String tenantId, CasDigest expected, byte[] content) {
                throw new java.io.UncheckedIOException(new java.io.IOException("KMS unavailable"));
            }

            @Override public byte[] decrypt(String tenantId, CasDigest expected, byte[] ciphertext) {
                throw new java.io.UncheckedIOException(new java.io.IOException("KMS unavailable"));
            }

            @Override public boolean hasKey(String tenantId) {
                return true;
            }

            @Override public boolean encryptsAtRest() {
                return true;
            }

            @Override public byte[] open(String tenantId, CasDigest expected,
                                         TenantEncryption.Envelope envelope) {
                throw new java.io.UncheckedIOException(new java.io.IOException("KMS unavailable"));
            }
        };
        CasStore reader = new TenantEncryptedLocalCasStore("encrypted", root, unavailable)
                .forTenant("tenant-a");

        assertThrows(java.io.UncheckedIOException.class, () -> reader.get(digest));
        assertTrue(reader.contains(digest));
        assertFalse(hasPoisonedFile(root));
    }

    @Test void aConcurrentPoisonedWinnerIsVerifiedAndNeverOverwritten() throws Exception {
        Path root = temporary.resolve("winner-cas");
        byte[] plaintext = "concurrent artifact".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        String namespace = CasDigest.ofUtf8("elmos-tenant-cas-namespace/1\ntenant-a").hex();
        Path winner = root.resolve("tenants").resolve(namespace.substring(0, 2))
                .resolve(namespace).resolve("blobs").resolve(digest.algorithm())
                .resolve(digest.hex().substring(0, 2)).resolve(digest.hex().substring(2, 4))
                .resolve(digest.hex() + "." + digest.sizeBytes() + ".enc");
        TenantEncryption.AesGcm delegate = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", key((byte) 4), true);
        TenantEncryption racing = new TenantEncryption() {
            @Override public byte[] encrypt(String tenantId, CasDigest expected, byte[] content) {
                return delegate.encrypt(tenantId, expected, content);
            }

            @Override public byte[] decrypt(String tenantId, CasDigest expected, byte[] ciphertext) {
                return delegate.decrypt(tenantId, expected, ciphertext);
            }

            @Override public boolean hasKey(String tenantId) {
                return delegate.hasKey(tenantId);
            }

            @Override public boolean encryptsAtRest() {
                return true;
            }

            @Override public TenantEncryption.Envelope seal(
                    String tenantId, CasDigest expected, byte[] content) {
                try {
                    Files.createDirectories(winner.getParent());
                    Files.writeString(winner, "poisoned winner", StandardCharsets.UTF_8);
                } catch (java.io.IOException error) {
                    throw new java.io.UncheckedIOException(error);
                }
                return delegate.seal(tenantId, expected, content);
            }

            @Override public byte[] open(String tenantId, CasDigest expected,
                                         TenantEncryption.Envelope envelope) {
                return delegate.open(tenantId, expected, envelope);
            }
        };
        CasStore writer = new TenantEncryptedLocalCasStore("encrypted", root, racing)
                .forTenant("tenant-a");

        assertThrows(CasExceptions.CasCorruptionException.class,
                () -> writer.put(digest, plaintext));
        assertFalse(writer.contains(digest));
        assertTrue(hasPoisonedFile(root));
    }

    private static boolean hasPoisonedFile(Path root) throws Exception {
        try (var walk = Files.walk(root.resolve("quarantine"))) {
            return walk.anyMatch(path -> path.getFileName().toString().endsWith(".poisoned"));
        }
    }

    private static byte[] key(byte fill) {
        byte[] key = new byte[32];
        java.util.Arrays.fill(key, fill);
        return key;
    }
}
