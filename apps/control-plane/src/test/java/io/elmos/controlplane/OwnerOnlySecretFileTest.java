package io.elmos.controlplane;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OwnerOnlySecretFileTest {
    @TempDir
    Path temporaryDirectory;

    @Test
    void readsAnExactOwnerOnlySecret() throws Exception {
        Path secret = temporaryDirectory.resolve("secret");
        Files.writeString(secret, "x".repeat(40));
        Files.setPosixFilePermissions(secret, PosixFilePermissions.fromString("rw-------"));

        assertEquals("x".repeat(40),
                OwnerOnlySecretFile.readRequired(secret.toString(), 32, 64, "INVALID"));
    }

    @Test
    void rejectsRelativeAndWorldReadablePaths() throws Exception {
        assertThrows(SecurityException.class,
                () -> OwnerOnlySecretFile.readRequired("relative", 1, 64, "INVALID"));

        Path secret = temporaryDirectory.resolve("public-secret");
        Files.writeString(secret, "x".repeat(40));
        Files.setPosixFilePermissions(secret, PosixFilePermissions.fromString("rw-r--r--"));
        assertThrows(SecurityException.class,
                () -> OwnerOnlySecretFile.readRequired(secret.toString(), 32, 64, "INVALID"));
    }

    @Test
    void permitsAnAbsentOptionalTokenOnly() {
        assertNull(OwnerOnlySecretFile.readOptional("", 16, 64, "INVALID"));
        assertThrows(IllegalStateException.class,
                () -> OwnerOnlySecretFile.readRequired("", 16, 64, "INVALID"));
    }
}
