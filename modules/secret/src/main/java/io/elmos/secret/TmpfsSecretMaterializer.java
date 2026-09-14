package io.elmos.secret;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Map;

/** Actual Linux tmpfs adapter for the canonical secret injection lifecycle. */
public final class TmpfsSecretMaterializer implements SecretInjectionService.SecretMaterializerPort {
    private final Map<String, Path> workspaces;

    /** Bind workspace identities from trusted host registration, never request paths. */
    public TmpfsSecretMaterializer(Map<String, Path> workspaces) {
        this.workspaces = Map.copyOf(workspaces);
        this.workspaces.keySet().forEach(this::root);
        if (this.workspaces.values().stream().map(Path::normalize).distinct().count() != this.workspaces.size()) {
            throw new SecurityException("SECRET_WORKSPACE_ALIAS");
        }
        for (Path left : this.workspaces.values()) {
            for (Path right : this.workspaces.values()) {
                if (!left.equals(right) && left.startsWith(right)) {
                    throw new SecurityException("SECRET_WORKSPACE_OVERLAP");
                }
            }
        }
    }

    private Path root(String workspace) {
        Path path = workspaces.get(workspace);
        if (path == null || !path.isAbsolute() || !path.equals(path.normalize())) {
            throw new SecurityException("SECRET_WORKSPACE_NOT_BOUND");
        }
        try {
            for (Path part = path; part != null; part = part.getParent()) {
                if (Files.isSymbolicLink(part)) throw new SecurityException("SECRET_WORKSPACE_SYMLINK");
            }
            if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                    || !"tmpfs".equals(Files.getFileStore(path).type())
                    || !Files.getPosixFilePermissions(path).equals(PosixFilePermissions.fromString("rwx------"))
                    || !Files.getOwner(path).equals(Files.getOwner(Path.of("/proc/self")))) {
                throw new SecurityException("SECRET_WORKSPACE_NOT_PRIVATE_TMPFS");
            }
            return path;
        } catch (IOException | UnsupportedOperationException failure) {
            throw new SecurityException("SECRET_WORKSPACE_INSPECTION_FAILED");
        }
    }

    private Path target(String workspace, String leaseId) {
        if (leaseId == null || !leaseId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
            throw new SecurityException("SECRET_LEASE_PATH");
        }
        return root(workspace).resolve(leaseId);
    }

    @Override
    public void materializeReadOnlyTmpfs(String workspace, String leaseId, SecretValue value) {
        Path target = target(workspace, leaseId);
        value.use(chars -> {
            ByteBuffer encoded = null;
            boolean created = false;
            try {
                encoded = StandardCharsets.UTF_8.newEncoder().encode(CharBuffer.wrap(chars));
                if (encoded.remaining() == 0 || encoded.remaining() > 65536) {
                    throw new SecurityException("SECRET_VALUE_BOUNDS");
                }
                try (FileChannel file = FileChannel.open(target,
                        java.util.Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS),
                        PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("r--------")))) {
                    created = true;
                    while (encoded.hasRemaining()) file.write(encoded);
                    file.force(true);
                }
                return null;
            } catch (IOException failure) {
                if (created) {
                    try { Files.delete(target); }
                    catch (IOException cleanup) { throw new SecurityException("SECRET_PARTIAL_FILE_CLEANUP_FAILED"); }
                }
                throw new SecurityException("SECRET_MATERIALIZATION_FAILED");
            } finally {
                if (encoded != null) {
                    encoded.clear();
                    while (encoded.hasRemaining()) encoded.put((byte) 0);
                }
            }
        });
    }

    @Override
    public void remove(String workspace, String leaseId) {
        Path target = target(workspace, leaseId);
        try {
            if (Files.isSymbolicLink(target)) throw new SecurityException("SECRET_LEASE_SYMLINK");
            if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)
                    && (!Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)
                        || !Files.getOwner(target).equals(Files.getOwner(target.getParent())))) {
                throw new SecurityException("SECRET_LEASE_OWNER");
            }
            Files.deleteIfExists(target);
        } catch (IOException failure) {
            throw new SecurityException("SECRET_REMOVAL_FAILED");
        }
    }
}
