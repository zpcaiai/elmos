package io.elmos.controlplane;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Set;

/**
 * Loads a bounded secret from an exact, owner-only file.
 *
 * <p>The configuration contains only a Secret Reference and file paths. Secret
 * values are never accepted as application properties and symbolic links are
 * rejected, so repository configuration cannot redirect the process to an
 * arbitrary credential.</p>
 */
final class OwnerOnlySecretFile {
    private static final Set<PosixFilePermission> UNSAFE_PERMISSIONS = Set.of(
            PosixFilePermission.GROUP_READ,
            PosixFilePermission.GROUP_WRITE,
            PosixFilePermission.GROUP_EXECUTE,
            PosixFilePermission.OTHERS_READ,
            PosixFilePermission.OTHERS_WRITE,
            PosixFilePermission.OTHERS_EXECUTE);

    private OwnerOnlySecretFile() {
    }

    static String readRequired(String configuredPath, int minimumBytes, int maximumBytes, String errorCode) {
        String value = read(configuredPath, minimumBytes, maximumBytes, errorCode, false);
        if (value == null) {
            throw new IllegalStateException(errorCode);
        }
        return value;
    }

    static String readOptional(String configuredPath, int minimumBytes, int maximumBytes, String errorCode) {
        return read(configuredPath, minimumBytes, maximumBytes, errorCode, true);
    }

    private static String read(
            String configuredPath,
            int minimumBytes,
            int maximumBytes,
            String errorCode,
            boolean optional
    ) {
        if (configuredPath == null || configuredPath.isBlank()) {
            if (optional) {
                return null;
            }
            throw new IllegalStateException(errorCode);
        }
        try {
            Path path = Path.of(configuredPath.trim());
            if (!path.isAbsolute()
                    || Files.isSymbolicLink(path)
                    || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                throw new SecurityException(errorCode);
            }
            long byteSize = Files.size(path);
            if (byteSize < minimumBytes || byteSize > maximumBytes) {
                throw new SecurityException(errorCode);
            }
            try {
                Set<PosixFilePermission> permissions =
                        Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS);
                if (permissions.stream().anyMatch(UNSAFE_PERMISSIONS::contains)) {
                    throw new SecurityException(errorCode);
                }
            } catch (UnsupportedOperationException ignored) {
                // Non-POSIX deployments must provide an equivalent platform ACL.
            }
            String value = Files.readString(path, StandardCharsets.UTF_8).trim();
            int length = value.getBytes(StandardCharsets.UTF_8).length;
            if (length < minimumBytes || length > maximumBytes
                    || value.chars().anyMatch(character ->
                    character == 0 || character == '\r' || character == '\n')) {
                throw new SecurityException(errorCode);
            }
            return value;
        } catch (IOException | IllegalArgumentException error) {
            throw new IllegalStateException(errorCode, error);
        }
    }
}
