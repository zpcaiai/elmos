package io.elmos.worker;

import java.io.IOException;
import java.nio.file.*;
import java.util.Objects;

final class WorkspacePathResolver {
    private final Path root;
    WorkspacePathResolver(Path root) { this.root = Objects.requireNonNull(root).toAbsolutePath().normalize(); }
    Path resolve(String relativePath) {
        if (relativePath == null || relativePath.isBlank() || relativePath.indexOf('\0') >= 0) throw new IllegalArgumentException("relativePath is required");
        Path candidate = root.resolve(relativePath).normalize();
        if (!candidate.startsWith(root) || Files.isSymbolicLink(candidate)) throw new SecurityException("project path escapes workspace");
        try {
            Path realRoot = root.toRealPath(LinkOption.NOFOLLOW_LINKS), real = candidate.toRealPath(LinkOption.NOFOLLOW_LINKS);
            if (!real.startsWith(realRoot) || !Files.isDirectory(real, LinkOption.NOFOLLOW_LINKS)) throw new SecurityException("project path escapes workspace");
            return real;
        } catch (IOException error) { throw new IllegalArgumentException("project path is unavailable", error); }
    }
}
