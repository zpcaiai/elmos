package io.elmos.controlplane;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Instant;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RepositoryWorkspaceCredentialStoreTest {
    @TempDir Path temporary;

    @Test
    void leasesOwnerOnlyCredentialWithoutReturningItAsText() throws Exception {
        Path file = temporary.resolve("private-git.credential");
        Files.writeString(file, "git-user\n" + Instant.now().plusSeconds(900)
                + "\nprovider-token-value\n");
        Files.setPosixFilePermissions(file, Set.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE
        ));
        RepositoryWorkspaceCredentialStore store =
                new RepositoryWorkspaceCredentialStore(temporary);

        try (RepositoryWorkspaceCredentialStore.Lease lease = store.lease("private-git")) {
            assertEquals("git-user", lease.username());
            assertTrue(lease.credential().isPresent());
            assertEquals("EphemeralCredential[REDACTED]", lease.credential().orElseThrow().toString());
        }
    }

    @Test
    void rejectsPathEscapeAndGroupReadableCredential() throws Exception {
        RepositoryWorkspaceCredentialStore store =
                new RepositoryWorkspaceCredentialStore(temporary);
        assertThrows(SecurityException.class, () -> store.lease("../secret"));

        Path file = temporary.resolve("shared.credential");
        Files.writeString(file, "git-user\n" + Instant.now().plusSeconds(900)
                + "\nprovider-token-value\n");
        Files.setPosixFilePermissions(file, Set.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.GROUP_READ
        ));
        assertThrows(SecurityException.class, () -> store.lease("shared"));
    }

    @Test
    void rejectsExpiredAndOverlongCredentialLeases() throws Exception {
        RepositoryWorkspaceCredentialStore store =
                new RepositoryWorkspaceCredentialStore(temporary);
        for (var expiry : new Instant[] {
                Instant.now().minusSeconds(1),
                Instant.now().plusSeconds(3_601)
        }) {
            Path file = temporary.resolve("lease-" + Math.abs(expiry.getEpochSecond()) + ".credential");
            Files.writeString(file, "git-user\n" + expiry + "\nprovider-token-value\n");
            Files.setPosixFilePermissions(file, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE
            ));
            String reference = file.getFileName().toString().replace(".credential", "");
            assertThrows(SecurityException.class, () -> store.lease(reference));
        }
    }
}
