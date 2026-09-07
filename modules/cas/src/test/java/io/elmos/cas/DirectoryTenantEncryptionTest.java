package io.elmos.cas;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Base64;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DirectoryTenantEncryptionTest {

    @TempDir Path temporary;

    @Test void rotationChangesNewCiphertextButKeepsOldEnvelopesReadable() throws Exception {
        Path root = Files.createDirectory(temporary.resolve("keys"));
        DirectoryTenantEncryption encryption = new DirectoryTenantEncryption(root);
        provision(encryption, "tenant-a", "v1", (byte) 1, true);
        CasDigest digest = CasDigest.ofUtf8("private source");
        byte[] plaintext = "private source".getBytes(StandardCharsets.UTF_8);
        TenantEncryption.Envelope first = encryption.seal("tenant-a", digest, plaintext);

        provision(encryption, "tenant-a", "v2", (byte) 2, true);
        TenantEncryption.Envelope second = encryption.seal("tenant-a", digest, plaintext);

        assertNotEquals(first.keyId(), second.keyId());
        assertFalse(java.util.Arrays.equals(first.ciphertext(), second.ciphertext()));
        assertArrayEquals(plaintext, encryption.open("tenant-a", digest, first));
        assertArrayEquals(plaintext, encryption.open("tenant-a", digest, second));
    }

    @Test void aCiphertextCannotBeMovedIntoAnotherTenantEvenWithTheSameRawKey() throws Exception {
        Path root = Files.createDirectory(temporary.resolve("keys"));
        DirectoryTenantEncryption encryption = new DirectoryTenantEncryption(root);
        provision(encryption, "tenant-a", "v1", (byte) 7, true);
        provision(encryption, "tenant-b", "v1", (byte) 7, true);
        byte[] plaintext = "customer source".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        TenantEncryption.Envelope envelope = encryption.seal("tenant-a", digest, plaintext);

        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> encryption.open("tenant-b", digest, envelope));
    }

    @Test void groupReadableKeyMaterialFailsClosed() throws Exception {
        Path root = Files.createDirectory(temporary.resolve("keys"));
        DirectoryTenantEncryption encryption = new DirectoryTenantEncryption(root);
        Path keyFile = provision(encryption, "tenant-a", "v1", (byte) 4, true);
        Files.setPosixFilePermissions(keyFile, Set.of(PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE, PosixFilePermission.GROUP_READ));

        assertFalse(encryption.hasKey("tenant-a"));
        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> encryption.seal("tenant-a", CasDigest.ofUtf8("x"), new byte[]{'x'}));
    }

    @Test void groupWritableCurrentKeySelectorFailsClosed() throws Exception {
        Path root = Files.createDirectory(temporary.resolve("keys"));
        DirectoryTenantEncryption encryption = new DirectoryTenantEncryption(root);
        provision(encryption, "tenant-a", "v1", (byte) 4, true);
        Path current = encryption.tenantKeyDirectory("tenant-a").resolve("current");
        Files.setPosixFilePermissions(current, Set.of(PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE, PosixFilePermission.GROUP_WRITE));

        assertFalse(encryption.hasKey("tenant-a"));
        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> encryption.seal("tenant-a", CasDigest.ofUtf8("x"), new byte[]{'x'}));
    }

    @Test void openingAnOldEnvelopeStillChecksItsParentDirectories() throws Exception {
        Path root = Files.createDirectory(temporary.resolve("keys"));
        DirectoryTenantEncryption encryption = new DirectoryTenantEncryption(root);
        provision(encryption, "tenant-a", "v1", (byte) 4, true);
        byte[] plaintext = new byte[]{'x'};
        CasDigest digest = CasDigest.of(plaintext);
        TenantEncryption.Envelope envelope = encryption.seal("tenant-a", digest, plaintext);
        Path tenantDirectory = encryption.tenantKeyDirectory("tenant-a");
        Files.setPosixFilePermissions(tenantDirectory, Set.of(
                PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.OWNER_EXECUTE, PosixFilePermission.GROUP_WRITE));

        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> encryption.open("tenant-a", digest, envelope));
    }

    private static Path provision(DirectoryTenantEncryption encryption, String tenantId,
                                  String keyId, byte fill, boolean current) throws Exception {
        Path directory = encryption.tenantKeyDirectory(tenantId);
        Files.createDirectories(directory);
        byte[] key = new byte[32];
        java.util.Arrays.fill(key, fill);
        Path keyFile = directory.resolve(keyId + ".key");
        Files.writeString(keyFile, Base64.getEncoder().encodeToString(key), StandardCharsets.US_ASCII);
        Files.setPosixFilePermissions(keyFile, Set.of(
                PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE));
        if (current) {
            Files.writeString(directory.resolve("current"), keyId + "\n", StandardCharsets.UTF_8);
        }
        java.util.Arrays.fill(key, (byte) 0);
        assertTrue(encryption.hasKey(tenantId));
        return keyFile;
    }
}
