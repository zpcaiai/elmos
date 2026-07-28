package io.elmos.controlplane;

import io.elmos.scm.EphemeralCredential;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Arrays;
import java.util.Optional;
import java.util.Set;

/**
 * Reads short-lived Git credentials from owner-only files without persisting
 * tokens in repository URLs, application properties, or workspace metadata.
 */
final class RepositoryWorkspaceCredentialStore {
    record Lease(String username, Optional<EphemeralCredential> credential) implements AutoCloseable {
        @Override public void close() { credential.ifPresent(EphemeralCredential::close); }
    }

    private static final int MAXIMUM_CREDENTIAL_BYTES = 65_536;
    private final Path root;

    RepositoryWorkspaceCredentialStore(Path root) {
        this.root = root.toAbsolutePath().normalize();
        if (this.root.getParent() == null) {
            throw new IllegalArgumentException("credential root must not be a filesystem root");
        }
        if (Files.isSymbolicLink(this.root)
                || !Files.isDirectory(this.root, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalArgumentException("credential root must be an existing regular directory");
        }
        try {
            Set<PosixFilePermission> permissions =
                    Files.getPosixFilePermissions(this.root, LinkOption.NOFOLLOW_LINKS);
            if (permissions.stream().anyMatch(permission ->
                    permission.name().startsWith("GROUP_")
                            || permission.name().startsWith("OTHERS_"))) {
                throw new SecurityException("credential root must be owner-only");
            }
        } catch (UnsupportedOperationException ignored) {
            // The underlying filesystem does not expose POSIX permissions.
        } catch (IOException error) {
            throw new IllegalArgumentException("credential root is unavailable", error);
        }
    }

    Lease lease(String credentialRef) {
        if (credentialRef == null || credentialRef.isBlank()) {
            return new Lease("git", Optional.empty());
        }
        if (!credentialRef.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")) {
            throw new SecurityException("GIT_CREDENTIAL_REFERENCE_INVALID");
        }
        Path path = root.resolve(credentialRef + ".credential").normalize();
        if (!path.startsWith(root) || path.equals(root)) {
            throw new SecurityException("GIT_CREDENTIAL_REFERENCE_ESCAPE");
        }
        byte[] bytes = null;
        char[] token = null;
        try {
            validateOwnerOnlyFile(path);
            bytes = Files.readAllBytes(path);
            int newline = firstNewline(bytes);
            if (newline < 1 || newline >= bytes.length - 1) {
                throw new SecurityException("GIT_CREDENTIAL_FILE_FORMAT_INVALID");
            }
            String username = decode(bytes, 0, newline).trim();
            if (!username.matches("[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}")) {
                throw new SecurityException("GIT_CREDENTIAL_USERNAME_INVALID");
            }
            int tokenStart = newline + 1;
            int tokenEnd = bytes.length;
            while (tokenEnd > tokenStart && (bytes[tokenEnd - 1] == '\n' || bytes[tokenEnd - 1] == '\r')) {
                tokenEnd--;
            }
            token = decodeChars(bytes, tokenStart, tokenEnd - tokenStart);
            if (token.length < 8) throw new SecurityException("GIT_CREDENTIAL_TOKEN_INVALID");
            EphemeralCredential credential = new EphemeralCredential(token);
            return new Lease(username, Optional.of(credential));
        } catch (RuntimeException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("GIT_CREDENTIAL_UNAVAILABLE", error);
        } finally {
            if (bytes != null) Arrays.fill(bytes, (byte) 0);
            if (token != null) Arrays.fill(token, '\0');
        }
    }

    private static void validateOwnerOnlyFile(Path path) throws IOException {
        if (Files.isSymbolicLink(path)
                || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                || Files.size(path) < 10
                || Files.size(path) > MAXIMUM_CREDENTIAL_BYTES) {
            throw new SecurityException("GIT_CREDENTIAL_FILE_INVALID");
        }
        try {
            Set<PosixFilePermission> permissions =
                    Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS);
            if (permissions.stream().anyMatch(permission ->
                    permission.name().startsWith("GROUP_")
                            || permission.name().startsWith("OTHERS_"))) {
                throw new SecurityException("GIT_CREDENTIAL_FILE_MUST_BE_OWNER_ONLY");
            }
        } catch (UnsupportedOperationException ignored) {
            // The underlying filesystem does not expose POSIX permissions.
        }
    }

    private static int firstNewline(byte[] value) {
        for (int index = 0; index < value.length; index++) {
            if (value[index] == '\n') return index;
        }
        return -1;
    }

    private static String decode(byte[] value, int offset, int length) throws Exception {
        char[] decoded = decodeChars(value, offset, length);
        try {
            return new String(decoded);
        } finally {
            Arrays.fill(decoded, '\0');
        }
    }

    private static char[] decodeChars(byte[] value, int offset, int length) throws Exception {
        CharBuffer decoded = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(value, offset, length));
        char[] output = new char[decoded.remaining()];
        decoded.get(output);
        return output;
    }
}
