package io.elmos.productionruntime;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Objects;
import java.util.Set;

/** Reads a credential from a least-privilege, non-symlink file. */
public final class OwnerOnlyProviderCredentialFile
        implements HttpProductionModelProviderAdapter.CredentialSource {
    private final Path path;

    public OwnerOnlyProviderCredentialFile(Path path) {
        this.path = Objects.requireNonNull(path, "path").toAbsolutePath().normalize();
    }

    @Override
    public String read() {
        try {
            if (Files.isSymbolicLink(path)
                    || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                throw new ProductionRuntimeException(
                        "PROVIDER_CREDENTIAL_FILE_INVALID",
                        "provider credential must be a regular non-symlink file");
            }
            try {
                Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(
                        path, LinkOption.NOFOLLOW_LINKS);
                if (permissions.contains(PosixFilePermission.GROUP_WRITE)
                        || permissions.contains(PosixFilePermission.GROUP_EXECUTE)
                        || permissions.contains(PosixFilePermission.OTHERS_READ)
                        || permissions.contains(PosixFilePermission.OTHERS_WRITE)
                        || permissions.contains(PosixFilePermission.OTHERS_EXECUTE)) {
                    throw new ProductionRuntimeException(
                            "PROVIDER_CREDENTIAL_FILE_PERMISSIONS",
                            "credential may be owner-readable or group-readable, but the group must not write/execute it and others must have no access");
                }
            } catch (UnsupportedOperationException ignored) {
                // Non-POSIX filesystems still receive the no-symlink and regular
                // file checks. Deployment policy must enforce the equivalent ACL.
            }
            long size = Files.size(path);
            if (size < 1 || size > 16_384) {
                throw new ProductionRuntimeException(
                        "PROVIDER_CREDENTIAL_FILE_SIZE",
                        "provider credential file size is outside the allowed range");
            }
            String value = Files.readString(path).trim();
            if (value.isBlank() || value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0) {
                throw new ProductionRuntimeException(
                        "PROVIDER_CREDENTIAL_INVALID",
                        "provider credential file must contain exactly one non-empty line");
            }
            return value;
        } catch (IOException ex) {
            throw new ProductionRuntimeException(
                    "PROVIDER_CREDENTIAL_FILE_UNREADABLE",
                    "provider credential file cannot be read", ex);
        }
    }
}
