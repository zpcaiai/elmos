package io.elmos.runner;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardCopyOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Stream;

/**
 * Per-lease scratch directory with identity-checked teardown.
 *
 * <p>Layout, all owner-only (0700):</p>
 * <pre>
 *   &lt;workRoot&gt;/lease-&lt;sha256(jobId, leaseId, attempt)&gt;/
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

    private static final String OWNER_FILE = ".elmos-workspace-owner";
    private static final String INTENTS_DIRECTORY = ".elmos-container-intents";
    // Do not open/close a second descriptor for an in-process locked file:
    // on POSIX, closing it can release the process's original advisory lock.
    private static final Set<Path> ACTIVE_ROOTS = ConcurrentHashMap.newKeySet();

    private final Path root;
    private final Path in;
    private final Path out;
    private final Path tmp;
    private final Object rootKey;
    private final Object ownerKey;
    private final String owner;
    private final FileChannel ownerChannel;
    private final FileLock ownerLock;
    private boolean closed;

    private JobWorkspace(Path root, Path in, Path out, Path tmp, Object rootKey, Object ownerKey, String owner,
                         FileChannel ownerChannel, FileLock ownerLock) {
        this.root = root;
        this.in = in;
        this.out = out;
        this.tmp = tmp;
        this.rootKey = rootKey;
        this.ownerKey = ownerKey;
        this.owner = owner;
        this.ownerChannel = ownerChannel;
        this.ownerLock = ownerLock;
    }

    /** Domain-separated lease identity. Credentials never become path/label data. */
    static String leaseIdentity(ControlPlaneClient.Lease lease) {
        if (lease == null || lease.jobId() == null || !lease.jobId().matches("^[A-Za-z0-9][A-Za-z0-9._-]{2,95}$")
                || lease.leaseId() == null || lease.leaseId().isBlank() || lease.leaseId().length() > 256
                || lease.attempt() < 1) throw new IllegalArgumentException("LEASE_RESOURCE_IDENTITY_INVALID");
        return identityHash(Json.write(List.of("elmos-runner-lease-resource-v1", lease.jobId(), lease.leaseId(), lease.attempt())));
    }

    static String identityHash(String value) {
        try {
            return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    public static JobWorkspace create(Path workRoot, ControlPlaneClient.Lease lease, int workloadUid, int workloadGid)
            throws IOException {
        return createOwned(workRoot, "lease-" + leaseIdentity(lease), workloadUid, workloadGid, false);
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
        if (jobId == null || !jobId.matches("^[A-Za-z0-9][A-Za-z0-9._-]{2,95}$")) {
            // The job id becomes a path segment. Anything else is a traversal risk.
            throw new IOException("JOB_ID_UNSAFE_FOR_PATH");
        }
        return createOwned(workRoot, jobId, workloadUid, workloadGid, true);
    }

    private static JobWorkspace createOwned(Path workRoot, String segment, int workloadUid, int workloadGid,
                                           boolean legacy) throws IOException {
        Files.createDirectories(workRoot);
        Path base = workRoot.toRealPath();
        Path root = base.resolve(segment);
        if (base.getParent() == null || !root.startsWith(base)) {
            throw new IOException("JOB_WORKSPACE_ESCAPES_ROOT");
        }
        if (Files.exists(root, LinkOption.NOFOLLOW_LINKS)) {
            if (!legacy || !removeOrphan(root)) throw new IOException("JOB_WORKSPACE_ALREADY_OWNED");
        }
        if (!ACTIVE_ROOTS.add(root)) throw new IOException("JOB_WORKSPACE_ALREADY_OWNED");
        try {
            return initializeOwned(root, workloadUid, workloadGid);
        } catch (IOException | RuntimeException error) {
            ACTIVE_ROOTS.remove(root);
            throw error;
        }
    }

    private static JobWorkspace initializeOwned(Path root, int workloadUid, int workloadGid) throws IOException {
        var ownerOnly = PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------"));
        Files.createDirectory(root, ownerOnly);
        Object rootKey = Files.readAttributes(root, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).fileKey();
        if (rootKey == null) throw new IOException("JOB_WORKSPACE_IDENTITY_UNAVAILABLE");
        String owner = UUID.randomUUID().toString();
        FileChannel ownerChannel = FileChannel.open(root.resolve(OWNER_FILE),
                StandardOpenOption.CREATE_NEW, StandardOpenOption.READ, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS);
        FileLock ownerLock = null;
        try {
            ownerLock = ownerChannel.tryLock();
            if (ownerLock == null) throw new IOException("JOB_WORKSPACE_ALREADY_OWNED");
            Object ownerKey = Files.readAttributes(root.resolve(OWNER_FILE), BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS).fileKey();
            if (ownerKey == null) throw new IOException("JOB_WORKSPACE_IDENTITY_UNAVAILABLE");
            ByteBuffer token = ByteBuffer.wrap(owner.getBytes(StandardCharsets.UTF_8));
            while (token.hasRemaining()) ownerChannel.write(token);
            ownerChannel.force(true);
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
            return new JobWorkspace(root, in, out, tmp, rootKey, ownerKey, owner, ownerChannel, ownerLock);
        } catch (IOException | RuntimeException error) {
            try {
                if (ownerLock != null) ownerLock.release();
            } finally {
                ownerChannel.close();
            }
            throw error;
        }
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

    record ContainerIntent(Path file, Object key, String contents) { }

    synchronized ContainerIntent recordContainerIntent(String containerName, String leaseIdentity) throws IOException {
        if (closed || !ownsRoot() || !containerName.matches("elmos-[a-f0-9]{48}")
                || !leaseIdentity.matches("[a-f0-9]{64}")
                || !root.getFileName().toString().equals("lease-" + leaseIdentity)) {
            throw new IOException("CONTAINER_INTENT_IDENTITY_INVALID");
        }
        Path namespace = intentNamespace(root);
        privateDirectory(namespace.getParent());
        privateDirectory(namespace);
        Path file = namespace.resolve(containerName + ".json");
        String contents = Json.write(java.util.Map.of("schemaVersion", "runner-container-intent-v1",
                "containerName", containerName, "leaseIdentity", leaseIdentity, "workspace", root.getFileName().toString()));
        try (FileChannel channel = FileChannel.open(file, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE,
                LinkOption.NOFOLLOW_LINKS)) {
            ByteBuffer bytes = ByteBuffer.wrap(contents.getBytes(StandardCharsets.UTF_8));
            while (bytes.hasRemaining()) channel.write(bytes);
            channel.force(true);
        }
        forceDirectory(namespace);
        Object key = Files.readAttributes(file, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).fileKey();
        if (key == null) throw new IOException("CONTAINER_INTENT_IDENTITY_UNAVAILABLE");
        return new ContainerIntent(file, key, contents);
    }

    static void clearContainerIntent(ContainerIntent intent) throws IOException {
        verifyIntent(intent);
        Path file = intent.file();
        Files.delete(file);
        forceDirectory(file.getParent());
        try { Files.delete(file.getParent()); } catch (DirectoryNotEmptyException active) { /* other phase */ }
    }

    static ContainerIntent bindContainerId(ContainerIntent intent, String containerId) throws IOException {
        if (containerId == null || !containerId.matches("[a-f0-9]{64}")) {
            throw new IOException("CONTAINER_INTENT_IDENTITY_INVALID");
        }
        verifyIntent(intent);
        var document = Json.parseObject(intent.contents());
        document.put("containerId", containerId);
        String contents = Json.write(document);
        Path temporary = Files.createTempFile(intent.file().getParent(), ".intent-", ".tmp");
        try {
            try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
                ByteBuffer bytes = ByteBuffer.wrap(contents.getBytes(StandardCharsets.UTF_8));
                while (bytes.hasRemaining()) channel.write(bytes);
                channel.force(true);
            }
            verifyIntent(intent);
            Files.move(temporary, intent.file(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            forceDirectory(intent.file().getParent());
            Object key = Files.readAttributes(intent.file(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).fileKey();
            if (key == null) throw new IOException("CONTAINER_INTENT_IDENTITY_UNAVAILABLE");
            return new ContainerIntent(intent.file(), key, contents);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static void verifyIntent(ContainerIntent intent) throws IOException {
        Path file = intent.file();
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(file)
                || !Objects.equals(intent.key(), Files.readAttributes(file, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS).fileKey())) throw new IOException("CONTAINER_INTENT_IDENTITY_CHANGED");
        try (FileChannel channel = FileChannel.open(file, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
            ByteBuffer content = ByteBuffer.allocate(4097);
            while (content.hasRemaining() && channel.read(content) != -1) { }
            if (content.position() > 4096 || !intent.contents().equals(new String(content.array(), 0,
                    content.position(), StandardCharsets.UTF_8))) throw new IOException("CONTAINER_INTENT_CONTENT_CHANGED");
        }
    }

    static boolean hasPendingContainerIntents(Path workRoot) {
        Path directory = workRoot.resolve(INTENTS_DIRECTORY);
        try {
            if (!Files.readAttributes(directory, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).isDirectory()) return true;
        } catch (NoSuchFileException absent) { return false; }
        catch (IOException | RuntimeException unknown) { return true; }
        try (Stream<Path> paths = Files.walk(directory, 2)) {
            return paths.anyMatch(path -> !path.equals(directory) && (Files.isSymbolicLink(path)
                    || !Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                    || directory.relativize(path).getNameCount() == 2));
        } catch (IOException | RuntimeException unknown) {
            return true;
        }
    }

    private static Path intentNamespace(Path workspace) {
        return workspace.getParent().resolve(INTENTS_DIRECTORY).resolve(workspace.getFileName());
    }

    private static boolean hasPendingIntent(Path workspace) {
        Path directory = workspace.getParent().resolve(INTENTS_DIRECTORY);
        try {
            if (!Files.readAttributes(directory, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).isDirectory()) return true;
        } catch (NoSuchFileException absent) { return false; }
        catch (IOException | RuntimeException unknown) { return true; }
        Path namespace = intentNamespace(workspace);
        try {
            if (!Files.readAttributes(namespace, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).isDirectory()) return true;
        } catch (NoSuchFileException absent) { return false; }
        catch (IOException | RuntimeException unknown) { return true; }
        try (Stream<Path> files = Files.list(namespace)) {
            return files.findAny().isPresent();
        } catch (IOException unknown) { return true; }
    }

    private static void privateDirectory(Path path) throws IOException {
        try {
            Files.createDirectory(path, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
            forceDirectory(path.getParent());
        } catch (FileAlreadyExistsException existing) {
            if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path)) {
                throw new IOException("CONTAINER_INTENT_DIRECTORY_UNSAFE");
            }
        }
    }

    private static void forceDirectory(Path directory) throws IOException {
        try (FileChannel channel = FileChannel.open(directory, StandardOpenOption.READ)) { channel.force(true); }
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
    public synchronized void close() {
        if (closed) return;
        closed = true;
        try {
            if (ownsRoot() && !hasPendingIntent(root)) deleteRecursively(root);
        } catch (IOException ignored) {
            // Identity drift fails closed. The trusted node reconciler owns it.
        } finally {
            try { ownerLock.release(); } catch (IOException ignored) { }
            try { ownerChannel.close(); } catch (IOException ignored) { }
            ACTIVE_ROOTS.remove(root);
        }
    }

    private boolean ownsRoot() throws IOException {
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(root)
                || !Objects.equals(rootKey, Files.readAttributes(root, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS).fileKey())) return false;
        Path marker = root.resolve(OWNER_FILE);
        if (!Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS) || Files.size(marker) != owner.length()
                || !Objects.equals(ownerKey, Files.readAttributes(marker, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS).fileKey())) return false;
        ByteBuffer content = ByteBuffer.allocate(owner.length() + 1);
        ownerChannel.position(0);
        while (content.hasRemaining() && ownerChannel.read(content) != -1) { }
        return content.position() == owner.length()
                && owner.equals(new String(content.array(), 0, content.position(), StandardCharsets.UTF_8));
    }

    private static boolean removeOrphan(Path root) throws IOException {
        if (!ACTIVE_ROOTS.add(root)) return false;
        try {
            return removeClaimedOrphan(root);
        } finally {
            ACTIVE_ROOTS.remove(root);
        }
    }

    private static boolean removeClaimedOrphan(Path root) throws IOException {
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(root)) return false;
        if (hasPendingIntent(root)) return false;
        Object rootKey = Files.readAttributes(root, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).fileKey();
        if (rootKey == null) return false;
        Path marker = root.resolve(OWNER_FILE);
        if (!Files.exists(marker, LinkOption.NOFOLLOW_LINKS)) {
            // This can be an initializing directory or an active legacy binary
            // which predates ownership markers. Neither is proven orphaned.
            return false;
        }
        // The owner writes its complete token only after acquiring the lock.
        // An empty/partial marker is an initialization window, not an orphan.
        if (!Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS) || Files.size(marker) != 36) return false;
        try (FileChannel channel = FileChannel.open(marker, StandardOpenOption.READ, StandardOpenOption.WRITE,
                LinkOption.NOFOLLOW_LINKS)) {
            try (FileLock lock = channel.tryLock()) {
                if (lock == null) return false;
                if (!Objects.equals(rootKey, Files.readAttributes(root, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS).fileKey())) return false;
                ByteBuffer token = ByteBuffer.allocate(37);
                while (token.hasRemaining() && channel.read(token) != -1) { }
                if (token.position() != 36 || !new String(token.array(), 0, token.position(), StandardCharsets.UTF_8)
                        .matches("[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}")) return false;
                deleteRecursively(root);
                return true;
            }
        } catch (OverlappingFileLockException busy) {
            return false;
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
        try (Stream<Path> entries = Files.list(workRoot.toRealPath())) {
            for (Path entry : entries.toList()) {
                if (Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS)) {
                    if (removeOrphan(entry)) removed++;
                }
            }
        } catch (IOException ignored) {
            // Nothing actionable; the agent still starts.
        }
        return removed;
    }
}
