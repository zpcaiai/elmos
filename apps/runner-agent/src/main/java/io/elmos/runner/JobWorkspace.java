package io.elmos.runner;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

/**
 * Per-job scratch directory with a guaranteed teardown.
 *
 * <p>Layout, all owner-only (0700):</p>
 * <pre>
 *   &lt;workRoot&gt;/&lt;jobId&gt;/
 *     in/       request payload, checkpoint  (mounted read-only)
 *     out/      artifacts the workload produces (mounted read-write)
 *     tmp/      workload scratch              (mounted read-write)
 * </pre>
 *
 * <p>The split matters: the workload can write only to {@code out} and
 * {@code tmp}, so a compromised build cannot rewrite its own inputs and make the
 * evidence trail describe something that never happened.</p>
 */
public final class JobWorkspace implements AutoCloseable {

    private final Path root;
    private final Path in;
    private final Path out;
    private final Path tmp;

    private JobWorkspace(Path root, Path in, Path out, Path tmp) {
        this.root = root;
        this.in = in;
        this.out = out;
        this.tmp = tmp;
    }

    public static JobWorkspace create(Path workRoot, String jobId) throws IOException {
        // Same identity for agent and workload: the 0700 dirs are already usable.
        return create(workRoot, jobId, WorkspaceAccessProbe.currentUid(), WorkspaceAccessProbe.currentGid());
    }

    /**
     * Creates a workspace the workload identity can actually use.
     *
     * <p>When the container runs as a different uid than the agent, 0700
     * directories owned by the agent are unusable: the workload cannot read its
     * inputs and cannot write its outputs. Ownership is therefore transferred
     * explicitly rather than left to coincide.</p>
     */
    public static JobWorkspace create(Path workRoot, String jobId, int workloadUid, int workloadGid)
            throws IOException {
        if (!jobId.matches("^[A-Za-z0-9][A-Za-z0-9._-]{2,95}$")) {
            // The job id becomes a path segment. Anything else is a traversal risk.
            throw new IOException("JOB_ID_UNSAFE_FOR_PATH");
        }
        var ownerOnly = PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------"));
        Files.createDirectories(workRoot);
        Path root = workRoot.resolve(jobId).normalize();
        if (!root.startsWith(workRoot)) {
            throw new IOException("JOB_WORKSPACE_ESCAPES_ROOT");
        }
        if (Files.exists(root, LinkOption.NOFOLLOW_LINKS)) {
            // A leftover directory from a previous attempt must not be reused: it
            // could contain a half-written artifact that would be published as if
            // this attempt had produced it.
            deleteRecursively(root);
        }
        Files.createDirectory(root, ownerOnly);
        Path in = Files.createDirectory(root.resolve("in"), ownerOnly);
        Path out = Files.createDirectory(root.resolve("out"), ownerOnly);
        Path tmp = Files.createDirectory(root.resolve("tmp"), ownerOnly);

        if (workloadUid != WorkspaceAccessProbe.currentUid()
                || workloadGid != WorkspaceAccessProbe.currentGid()) {
            // The root stays owned by the agent so the workload cannot rename or
            // replace its own workspace; only the three leaves change hands.
            for (Path directory : new Path[]{in, out, tmp}) {
                if (!WorkspaceAccessProbe.chown(directory, workloadUid, workloadGid)) {
                    throw new IOException("WORKSPACE_OWNERSHIP_TRANSFER_FAILED");
                }
            }
        }
        return new JobWorkspace(root, in, out, tmp);
    }

    public Path root() {
        return root;
    }

    public Path in() {
        return in;
    }

    public Path out() {
        return out;
    }

    public Path tmp() {
        return tmp;
    }

    public void writeInput(String filename, String content) throws IOException {
        Path target = in.resolve(filename).normalize();
        if (!target.startsWith(in)) {
            throw new IOException("INPUT_PATH_ESCAPES_WORKSPACE");
        }
        Files.writeString(target, content);
        Files.setPosixFilePermissions(target, PosixFilePermissions.fromString("rw-------"));
    }

    /** Regular files produced by the workload, sorted for deterministic publication order. */
    public List<Path> outputs() throws IOException {
        if (!Files.isDirectory(out)) {
            return List.of();
        }
        try (Stream<Path> walk = Files.walk(out)) {
            return walk.filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                    // A symlink in out/ could point at the agent's own token file.
                    .filter(path -> !Files.isSymbolicLink(path))
                    .sorted(Comparator.comparing(Path::toString))
                    .toList();
        }
    }

    @Override
    public void close() {
        deleteQuietly(root);
    }

    private static void deleteQuietly(Path path) {
        try {
            deleteRecursively(path);
        } catch (IOException ignored) {
            // Teardown is best effort; the node-level sweeper is the backstop.
        }
    }

    static void deleteRecursively(Path path) throws IOException {
        if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
            return;
        }
        Files.walkFileTree(path, new SimpleFileVisitor<>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                Files.deleteIfExists(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(Path dir, IOException exc) throws IOException {
                Files.deleteIfExists(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    /**
     * Removes workspaces left behind by a crashed agent. Called once at startup:
     * without it a node that OOMs repeatedly fills its disk with orphans.
     */
    public static int sweepOrphans(Path workRoot) {
        if (!Files.isDirectory(workRoot)) {
            return 0;
        }
        int removed = 0;
        try (Stream<Path> entries = Files.list(workRoot)) {
            for (Path entry : entries.toList()) {
                if (Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS)) {
                    deleteQuietly(entry);
                    removed++;
                }
            }
        } catch (IOException ignored) {
            // Nothing actionable; the agent still starts.
        }
        return removed;
    }
}
