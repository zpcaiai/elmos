package io.elmos.security;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringHmacProtocolTest {
    private static final byte[] SECRET = "spring-hmac-secret-value-0123456789abcdef".getBytes(StandardCharsets.UTF_8);
    private static final String TIMESTAMP = "1788480000";
    private static final String NONCE = "12345678-1234-4234-8234-123456789abc";
    private static final byte[] BODY = "{\"run\":\"run-1\"}".getBytes(StandardCharsets.UTF_8);

    @TempDir
    Path temporary;

    @BeforeEach
    void canonicalizeTemporaryDirectory() throws Exception {
        temporary = temporary.toRealPath();
    }

    @Test
    void canonicalBytesBindVersionRoleMethodPathAndBody() {
        String canonical = new String(SpringHmacProtocol.canonical(
                SpringHmacProtocol.Role.VERIFIER, TIMESTAMP, NONCE, BODY), StandardCharsets.UTF_8);

        assertTrue(canonical.startsWith("ELMOS-SPRING-HMAC-V1\nVERIFIER\nPOST\n"
                + "/internal/v1/spring-verifications\n"));
        assertTrue(canonical.endsWith(SpringHmacProtocol.sha256(BODY)));
    }

    @Test
    void signaturesCannotReplayAcrossRolesOrRoutes() {
        String verifier = SpringHmacProtocol.sign(
                SECRET, SpringHmacProtocol.Role.VERIFIER, TIMESTAMP, NONCE, BODY);
        String transformer = SpringHmacProtocol.sign(
                SECRET, SpringHmacProtocol.Role.TRANSFORMER, TIMESTAMP, NONCE, BODY);
        String runtime = SpringHmacProtocol.sign(
                SECRET, SpringHmacProtocol.Role.RUNTIME, TIMESTAMP, NONCE, BODY);

        assertNotEquals(verifier, transformer);
        assertNotEquals(verifier, runtime);
        assertNotEquals(transformer, runtime);
    }

    @Test
    void readsSecretBytesWithoutNormalization() throws Exception {
        Path secret = temporary.resolve("secret");
        Files.write(secret, SECRET);
        ownerOnly(secret);

        assertArrayEquals(SECRET, SpringHmacProtocol.readSecret(secret, "runtime"));
    }

    @Test
    void rejectsAsciiAndUnicodeBoundaryWhitespaceInsteadOfTrimmingIt() throws Exception {
        Path ascii = temporary.resolve("ascii-secret");
        Path unicode = temporary.resolve("unicode-secret");
        Files.writeString(ascii, " " + "a".repeat(40), StandardCharsets.UTF_8);
        Files.writeString(unicode, "b".repeat(40) + "\u2003", StandardCharsets.UTF_8);
        ownerOnly(ascii);
        ownerOnly(unicode);

        assertThrows(IllegalStateException.class,
                () -> SpringHmacProtocol.readSecret(ascii, "verifier"));
        assertThrows(IllegalStateException.class,
                () -> SpringHmacProtocol.readSecret(unicode, "transformer"));
    }

    @Test
    void rejectsRelativeParentSymlinkHardlinkAndGroupReadableSecrets() throws Exception {
        Path insecure = temporary.resolve("insecure");
        Files.write(insecure, SECRET);
        Files.setPosixFilePermissions(insecure, Set.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.GROUP_READ));
        assertThrows(IllegalStateException.class,
                () -> SpringHmacProtocol.readSecret(insecure, "runtime"));

        Path original = temporary.resolve("original");
        Path hardlink = temporary.resolve("hardlink");
        Files.write(original, SECRET);
        ownerOnly(original);
        Files.createLink(hardlink, original);
        assertThrows(IllegalStateException.class,
                () -> SpringHmacProtocol.readSecret(original, "runtime"));

        Path realParent = temporary.resolve("real-parent");
        Files.createDirectory(realParent);
        Path nested = realParent.resolve("secret");
        Files.write(nested, SECRET);
        ownerOnly(nested);
        Path linkedParent = temporary.resolve("linked-parent");
        Files.createSymbolicLink(linkedParent, realParent);
        assertThrows(IllegalStateException.class,
                () -> SpringHmacProtocol.readSecret(linkedParent.resolve("secret"), "runtime"));

        assertThrows(IllegalStateException.class,
                () -> SpringHmacProtocol.readSecret(Path.of("relative-secret"), "runtime"));
    }

    @Test
    void rejectsAnInodeReplacementDuringTheOpenReadWindow() throws Exception {
        Path secret = temporary.resolve("raced-secret");
        Path displaced = temporary.resolve("displaced-secret");
        Files.write(secret, SECRET);
        ownerOnly(secret);

        assertThrows(IllegalStateException.class, () -> SpringHmacProtocol.readSecret(
                secret,
                "runtime",
                () -> {
                    try {
                        Files.move(secret, displaced, StandardCopyOption.ATOMIC_MOVE);
                        Files.write(secret, "replacement-secret-value-0123456789abcdef".getBytes(
                                StandardCharsets.UTF_8));
                        ownerOnly(secret);
                    } catch (Exception error) {
                        throw new IllegalStateException(error);
                    }
                }));
    }

    @Test
    void rejectsAParentReplacementDuringTheOpenReadWindow() throws Exception {
        Path parent = temporary.resolve("active-parent");
        Path displaced = temporary.resolve("displaced-parent");
        Files.createDirectory(parent);
        Path secret = parent.resolve("secret");
        Files.write(secret, SECRET);
        ownerOnly(secret);

        assertThrows(IllegalStateException.class, () -> SpringHmacProtocol.readSecret(
                secret,
                "runtime",
                () -> {
                    try {
                        Files.move(parent, displaced, StandardCopyOption.ATOMIC_MOVE);
                        Files.createDirectory(parent);
                        Path replacement = parent.resolve("secret");
                        Files.write(replacement, SECRET);
                        ownerOnly(replacement);
                    } catch (Exception error) {
                        throw new IllegalStateException(error);
                    }
                }));
    }

    @Test
    void parsesTheEffectiveNonRootUidRatherThanTheProcSelfSymlinkOwner() {
        assertEquals(10_001L, SpringHmacProtocol.parseEffectiveUid("""
                Name:\tjava
                Uid:\t0\t10001\t10001\t10001
                Gid:\t0\t10001\t10001\t10001
                """));
        assertThrows(IllegalStateException.class,
                () -> SpringHmacProtocol.parseEffectiveUid("Uid:\t0\tnot-a-uid\t0\t0"));
    }

    private static void ownerOnly(Path path) throws Exception {
        Files.setPosixFilePermissions(path, Set.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE));
    }
}
