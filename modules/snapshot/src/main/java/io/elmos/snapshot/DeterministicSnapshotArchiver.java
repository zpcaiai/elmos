package io.elmos.snapshot;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.github.luben.zstd.ZstdOutputStream;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.util.*;

/**
 * Produces the canonical ELMOS snapshot tar profile from an exclusively owned source tree.
 *
 * <p>The caller must hold an authoritative source lease (for example a fenced checkout lease or a
 * read-only filesystem snapshot) for the complete call. Java file locks are advisory and neither
 * {@link BasicFileAttributes} nor a repeated path read can prove that another process running as
 * the same OS identity did not rewrite an inode and restore its size and timestamps. This class
 * therefore requires stable file keys, reads regular files and symbolic links through private
 * same-filesystem hard-link anchors, and fails closed when it cannot establish those anchors. The
 * anchors defeat pathname swap/restore attacks; the external production lease remains mandatory
 * for same-inode writers and must not be replaced by a second read of the source path.
 */
public final class DeterministicSnapshotArchiver {
    public enum SourceAssurance {
        LOCAL_SELF_ATTESTED,
        AUTHORITATIVE_LEASE
    }

    /**
     * Result of an external fenced source-lease validation.
     *
     * <p>The archiver validates this receipt before and after reading the tree. Production lease
     * implementations must derive it from authoritative state rather than trusting repository
     * content or advisory file locks.</p>
     */
    public record SourceLeaseReceipt(
            Path sourceRoot,
            String leaseId,
            long fence,
            SourceAssurance assurance
    ) {
        public SourceLeaseReceipt {
            sourceRoot = Objects.requireNonNull(sourceRoot, "sourceRoot")
                    .toAbsolutePath().normalize();
            if (leaseId == null || leaseId.isBlank() || leaseId.length() > 256) {
                throw new IllegalArgumentException("source lease id is invalid");
            }
            if (fence < 0) {
                throw new IllegalArgumentException("source lease fence is invalid");
            }
            Objects.requireNonNull(assurance, "assurance");
        }
    }

    @FunctionalInterface
    public interface SourceLease {
        SourceLeaseReceipt validate(Path canonicalSourceRoot);
    }

    public record Limits(int maxEntries, int maxFiles, long maxFileBytes, long maxSourceBytes) {
        public Limits {
            if (maxEntries < 1 || maxEntries > MAX_ENTRIES
                    || maxFiles < 1 || maxFiles > maxEntries
                    || maxFileBytes < 1 || maxSourceBytes < maxFileBytes
                    || maxSourceBytes > MAX_SOURCE_BYTES)
                throw new IllegalArgumentException("snapshot limits are outside policy");
        }
    }
    public record ManifestEntry(String path, String type, long size, int mode, String sha256, String linkTarget) {}
    public record SnapshotContext(String provider, String repositoryId, String fullName, String requestedRef,
                                  String commitSha, String treeSha) {}
    public record RepositoryInfo(String provider, String repositoryId, String fullName) {}
    public record SourceInfo(String requestedRef, String commitSha, String treeSha) {}
    public record ArchiveInfo(String algorithm, String digest, String format) {}
    public record SpecialContent(List<String> submodules, List<String> gitLfsPointers, List<String> symlinks) {}
    public record SnapshotManifest(String schemaVersion, RepositoryInfo repository, SourceInfo source,
                                   ArchiveInfo archive, List<ManifestEntry> files, SpecialContent specialContent) {
        public SnapshotManifest { files = List.copyOf(files); }
    }
    public record SnapshotArchive(byte[] archive, String archiveSha256, byte[] manifest,
                                  String manifestSha256, long sourceBytes, int sourceFiles,
                                  SourceAssurance sourceAssurance) {
        public SnapshotArchive {
            archive = archive.clone();
            manifest = manifest.clone();
            Objects.requireNonNull(sourceAssurance, "sourceAssurance");
        }
        @Override public byte[] archive() { return archive.clone(); }
        @Override public byte[] manifest() { return manifest.clone(); }
    }

    private static final Set<String> EXCLUDED_NAMES = Set.of(".git", ".elmos", ".env", "id_rsa", "id_ed25519");
    private static final int READ_BUFFER_BYTES = 64 * 1024;
    private static final int MAX_ENTRIES = 100_000;
    private static final long MAX_SOURCE_BYTES = 256L * 1024 * 1024;
    private static final int MAX_PORTABLE_UTF8_BYTES = 4096;
    private static final int MAX_MANIFEST_BYTES = 32 * 1024 * 1024;
    private static final long MAX_TAR_METADATA_BYTES = 64L * 1024 * 1024;
    private static final int TAR_RECORD_BYTES = 512;
    private static final int CANONICAL_FILE_MODE = 0644;
    private static final int CANONICAL_EXECUTABLE_MODE = 0755;
    private static final int CANONICAL_DIRECTORY_MODE = 0755;
    private static final int CANONICAL_SYMLINK_MODE = 0777;
    private static final int CANONICAL_UID = 10001;
    private static final int CANONICAL_GID = 10001;
    private static final String CANONICAL_USER = "elmos";
    private static final String CANONICAL_GROUP = "elmos";
    private static final long CANONICAL_MTIME_MILLIS = 0L;
    private final ObjectMapper objectMapper = new ObjectMapper().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    private final Limits limits;
    private final FileReadProbe fileReadProbe;

    @FunctionalInterface
    interface FileReadProbe {
        default void beforeAnchoredRead(Path path) {
        }

        void afterRead(Path path);
    }

    public DeterministicSnapshotArchiver() {
        this(new Limits(100_000, 50_000, 64L * 1024 * 1024, 256L * 1024 * 1024));
    }

    public DeterministicSnapshotArchiver(Limits limits) {
        this(limits, ignored -> { });
    }

    DeterministicSnapshotArchiver(Limits limits, FileReadProbe fileReadProbe) {
        this.limits = Objects.requireNonNull(limits);
        this.fileReadProbe = Objects.requireNonNull(fileReadProbe);
    }

    public SnapshotArchive archive(Path sourceRoot) {
        return archive(sourceRoot, new SnapshotContext("UNKNOWN", "unknown", "unknown/unknown", "unknown",
                "0".repeat(40), "unknown"));
    }

    /**
     * Archives {@code sourceRoot} while the caller's authoritative source lease is held.
     *
     * <p>This method verifies stable filesystem identities and creates private inode anchors, but
     * it cannot acquire or infer a cross-process production lease. Callers that cannot guarantee
     * exclusive source ownership for the complete invocation must not call it. The result is
     * explicitly marked {@link SourceAssurance#LOCAL_SELF_ATTESTED}; it is not production source
     * lease evidence.</p>
     */
    public SnapshotArchive archive(Path sourceRoot, SnapshotContext context) {
        return archiveInternal(sourceRoot, context, localSelfAttestedLease(), false);
    }

    /**
     * Compatibility lease for bounded local tests and explicitly non-production callers.
     * Production capture services must require {@link SourceAssurance#AUTHORITATIVE_LEASE}.
     */
    public static SourceLease localSelfAttestedLease() {
        return canonicalRoot -> new SourceLeaseReceipt(
                canonicalRoot, "local-self-attested", 0,
                SourceAssurance.LOCAL_SELF_ATTESTED);
    }

    /**
     * Production entry point. A non-authoritative or changing lease receipt fails before a result
     * can be returned; the caller must continue holding the same lease until publication completes.
     */
    public SnapshotArchive archive(
            Path sourceRoot,
            SnapshotContext context,
            SourceLease sourceLease
    ) {
        return archiveInternal(sourceRoot, context,
                Objects.requireNonNull(sourceLease, "sourceLease"), true);
    }

    private SnapshotArchive archiveInternal(
            Path sourceRoot,
            SnapshotContext context,
            SourceLease sourceLease,
            boolean requireAuthoritativeLease
    ) {
        try {
            Path root = sourceRoot.toRealPath(LinkOption.NOFOLLOW_LINKS);
            if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) throw new IllegalArgumentException("snapshot source must be a directory");
            SourceLeaseReceipt initialLease = validateSourceLease(
                    sourceLease, root, requireAuthoritativeLease);
            BasicFileAttributes rootIdentity = Files.readAttributes(
                    root, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            requireStableFileKey(rootIdentity, ".");
            List<SnapshotNode> nodes = collectNodes(root);
            SourceBudget sourceBudget = new SourceBudget();
            ArchiveMetadataBudget metadataBudget = new ArchiveMetadataBudget(
                    MAX_TAR_METADATA_BYTES);
            List<ManifestEntry> entries = new ArrayList<>();
            List<String> lfsPointers = new ArrayList<>();
            ByteArrayOutputStream archiveBytes = new ByteArrayOutputStream();
            try (SourceAnchors anchors = SourceAnchors.create(root);
                 ZstdOutputStream zstd = new ZstdOutputStream(archiveBytes, 9);
                 TarArchiveOutputStream tar = new TarArchiveOutputStream(zstd, StandardCharsets.UTF_8.name())) {
                tar.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX);
                tar.setBigNumberMode(TarArchiveOutputStream.BIGNUMBER_ERROR);
                tar.setAddPaxHeadersForNonAsciiNames(true);
                for (SnapshotNode node : nodes) {
                    add(root, node, anchors, tar, entries, lfsPointers, sourceBudget,
                            metadataBudget);
                }
                tar.finish();
            }
            for (SnapshotNode node : nodes) {
                if (node.attributes().isDirectory()) {
                    requireSameIdentity(node.attributes(), Files.readAttributes(
                            node.path(), BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS),
                            portable(root.relativize(node.path())), true);
                }
            }
            requireSameIdentity(rootIdentity, Files.readAttributes(
                    root, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS),
                    ".", true);
            SourceLeaseReceipt finalLease = validateSourceLease(
                    sourceLease, root, requireAuthoritativeLease);
            if (!initialLease.equals(finalLease)) {
                throw new SecurityException(
                        "snapshot source lease changed during archive");
            }
            String archiveDigest = digest(archiveBytes.toByteArray());
            List<String> symlinks = entries.stream().filter(entry -> entry.type().equals("symlink")).map(ManifestEntry::path).toList();
            List<String> submodules = entries.stream().anyMatch(
                    entry -> entry.path().equals(".gitmodules"))
                    ? List.of(".gitmodules:review-required") : List.of();
            byte[] manifest = objectMapper.writeValueAsBytes(new SnapshotManifest("1.0",
                    new RepositoryInfo(context.provider(), context.repositoryId(), context.fullName()),
                    new SourceInfo(context.requestedRef(), context.commitSha(), context.treeSha()),
                    new ArchiveInfo("SHA-256", archiveDigest, "tar.zst"), entries,
                    new SpecialContent(submodules, List.copyOf(lfsPointers), symlinks)));
            if (manifest.length > MAX_MANIFEST_BYTES) {
                throw new SecurityException(
                        "snapshot manifest exceeds materialization policy");
            }
            long sourceBytes = sourceBudget.sourceBytes;
            int sourceFiles = sourceBudget.sourceFiles;
            return new SnapshotArchive(archiveBytes.toByteArray(), archiveDigest, manifest,
                    digest(manifest), sourceBytes, sourceFiles, initialLease.assurance());
        } catch (IOException exception) {
            throw new IllegalStateException("unable to create deterministic snapshot", exception);
        }
    }

    private static SourceLeaseReceipt validateSourceLease(
            SourceLease sourceLease,
            Path root,
            boolean requireAuthoritativeLease
    ) {
        SourceLeaseReceipt receipt = Objects.requireNonNull(
                sourceLease.validate(root), "source lease receipt");
        if (!receipt.sourceRoot().equals(root.toAbsolutePath().normalize())) {
            throw new SecurityException("snapshot source lease is bound to another root");
        }
        if (requireAuthoritativeLease
                && receipt.assurance() != SourceAssurance.AUTHORITATIVE_LEASE) {
            throw new SecurityException(
                    "production snapshot requires an authoritative source lease");
        }
        return receipt;
    }

    private List<SnapshotNode> collectNodes(Path root) throws IOException {
        List<SnapshotNode> nodes = new ArrayList<>();
        Files.walkFileTree(root, EnumSet.noneOf(FileVisitOption.class), Integer.MAX_VALUE,
                new SimpleFileVisitor<>() {
                    private int visitedNodes;

                    private void account(Path path) {
                        if (path.equals(root)) {
                            return;
                        }
                        visitedNodes++;
                        if (visitedNodes > limits.maxEntries()) {
                            throw new SecurityException(
                                    "snapshot visited node count exceeds policy");
                        }
                    }

                    @Override
                    public FileVisitResult preVisitDirectory(
                            Path directory, BasicFileAttributes attributes
                    ) {
                        account(directory);
                        if (directory.equals(root)) {
                            return FileVisitResult.CONTINUE;
                        }
                        Path relative = root.relativize(directory);
                        if (excluded(relative)) {
                            return FileVisitResult.SKIP_SUBTREE;
                        }
                        nodes.add(new SnapshotNode(directory, attributes));
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFile(Path path, BasicFileAttributes attributes) {
                        account(path);
                        if (!excluded(root.relativize(path))) {
                            nodes.add(new SnapshotNode(path, attributes));
                        }
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFileFailed(Path path, IOException failure)
                            throws IOException {
                        account(path);
                        throw failure;
                    }
                });
        nodes.sort(Comparator.comparing(node -> portable(root.relativize(node.path()))));
        return List.copyOf(nodes);
    }

    private void add(Path root, SnapshotNode node, SourceAnchors anchors,
                     TarArchiveOutputStream tar,
                     List<ManifestEntry> manifest, List<String> lfsPointers,
                     SourceBudget sourceBudget,
                     ArchiveMetadataBudget metadataBudget) throws IOException {
        Path path = node.path();
        String name = portable(root.relativize(path));
        BasicFileAttributes attributes = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        requireSameIdentity(node.attributes(), attributes, name, true);
        if (attributes.isOther()) throw new SecurityException("unsupported special file: " + name);
        TarArchiveEntry entry;
        String type; String fileDigest = null; String target = null; long size = 0; int mode;
        byte[] content = null;
        if (attributes.isSymbolicLink()) {
            VerifiedSymbolicLink verified = readVerifiedSymbolicLink(
                    root, path, name, attributes, anchors);
            entry = new TarArchiveEntry(name, TarArchiveEntry.LF_SYMLINK);
            target = verified.target();
            entry.setLinkName(target);
            type = "symlink";
            mode = CANONICAL_SYMLINK_MODE;
            fileDigest = verified.sha256();
        } else if (attributes.isDirectory()) {
            entry = new TarArchiveEntry(name + "/");
            type = "directory";
            mode = CANONICAL_DIRECTORY_MODE;
        } else if (attributes.isRegularFile()) {
            VerifiedRegularFile verified = readVerifiedRegularFile(
                    path, name, attributes, anchors, sourceBudget);
            content = verified.content();
            size = content.length;
            fileDigest = verified.sha256();
            entry = new TarArchiveEntry(name);
            type = "file";
            mode = verified.executable()
                    ? CANONICAL_EXECUTABLE_MODE : CANONICAL_FILE_MODE;
            if (verified.lfsPointer()) {
                lfsPointers.add(name);
            }
        } else throw new SecurityException("unsupported entry: " + name);
        metadataBudget.reserve(type.equals("directory") ? name + "/" : name, target);
        applyCanonicalHeader(entry, type, mode, size);
        tar.putArchiveEntry(entry); if (content != null) tar.write(content); tar.closeArchiveEntry();
        manifest.add(new ManifestEntry(name, type, size, mode, fileDigest, target));
    }

    private VerifiedRegularFile readVerifiedRegularFile(
            Path path,
            String name,
            BasicFileAttributes discovered,
            SourceAnchors anchors,
            SourceBudget sourceBudget
    ) throws IOException {
        BasicFileAttributes before = Files.readAttributes(
                path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        requireSameIdentity(discovered, before, name, true);
        if (!before.isRegularFile()) {
            throw new SecurityException("snapshot entry changed type before read: " + name);
        }
        sourceBudget.reserve(before.size());
        try (AnchoredNode anchored = anchors.anchor(path, name, before)) {
            boolean executable = Files.isExecutable(anchored.path());
            int initialCapacity = (int) Math.min(before.size(), READ_BUFFER_BYTES);
            ByteArrayOutputStream content = new ByteArrayOutputStream(initialCapacity);
            MessageDigest contentDigest = sha256Digest();
            long readBytes = 0;
            Set<OpenOption> options = Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS);
            fileReadProbe.beforeAnchoredRead(path);
            try (SeekableByteChannel channel = Files.newByteChannel(anchored.path(), options)) {
                if (channel.size() != before.size()) {
                    throw new SecurityException("snapshot file changed while opening: " + name);
                }
                ByteBuffer buffer = ByteBuffer.allocate(READ_BUFFER_BYTES);
                while (true) {
                    int count = channel.read(buffer);
                    if (count < 0) {
                        break;
                    }
                    if (count == 0) {
                        continue;
                    }
                    if (readBytes > before.size() - count) {
                        throw new SecurityException("snapshot file grew while reading: " + name);
                    }
                    content.write(buffer.array(), 0, count);
                    contentDigest.update(buffer.array(), 0, count);
                    readBytes += count;
                    buffer.clear();
                }
                if (readBytes != before.size()) {
                    throw new SecurityException("snapshot file size changed while reading: " + name);
                }
                fileReadProbe.afterRead(path);
                BasicFileAttributes anchoredAfter = Files.readAttributes(
                        anchored.path(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                requireSameIdentity(before, anchoredAfter, name, true);
                BasicFileAttributes sourceAfter;
                try {
                    sourceAfter = Files.readAttributes(
                            path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                } catch (IOException missingOrReplaced) {
                    throw new SecurityException(
                            "snapshot file disappeared while reading: " + name,
                            missingOrReplaced);
                }
                requireSameIdentity(before, sourceAfter, name, true);
                if (channel.size() != before.size()
                        || Files.isExecutable(anchored.path()) != executable
                        || Files.isExecutable(path) != executable) {
                    throw new SecurityException(
                            "snapshot file metadata changed while reading: " + name);
                }
            }
            byte[] verifiedContent = content.toByteArray();
            return new VerifiedRegularFile(verifiedContent,
                    HexFormat.of().formatHex(contentDigest.digest()),
                    isLfsPointer(verifiedContent), executable);
        }
    }

    private VerifiedSymbolicLink readVerifiedSymbolicLink(
            Path root,
            Path path,
            String name,
            BasicFileAttributes discovered,
            SourceAnchors anchors
    ) throws IOException {
        BasicFileAttributes before = Files.readAttributes(
                path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        requireSameIdentity(discovered, before, name, true);
        if (!before.isSymbolicLink()) {
            throw new SecurityException(
                    "snapshot entry changed type before readlink: " + name);
        }
        try (AnchoredNode anchored = anchors.anchor(path, name, before)) {
            fileReadProbe.beforeAnchoredRead(path);
            Path rawTarget = Files.readSymbolicLink(anchored.path());
            fileReadProbe.afterRead(path);
            requireSameIdentity(before, Files.readAttributes(
                    anchored.path(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS),
                    name, true);
            BasicFileAttributes sourceAfter;
            try {
                sourceAfter = Files.readAttributes(
                        path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            } catch (IOException missingOrReplaced) {
                throw new SecurityException(
                        "snapshot symlink disappeared while reading: " + name,
                        missingOrReplaced);
            }
            requireSameIdentity(before, sourceAfter, name, true);
            if (rawTarget.isAbsolute()) {
                throw new SecurityException(
                        "absolute symlink is not deterministic: " + name);
            }
            Path resolved = path.getParent().resolve(rawTarget).normalize();
            if (!resolved.startsWith(root)) {
                throw new SecurityException("symlink escapes snapshot root: " + name);
            }
            String target = portable(rawTarget);
            return new VerifiedSymbolicLink(
                    target, digest(target.getBytes(StandardCharsets.UTF_8)));
        }
    }

    private static void applyCanonicalHeader(
            TarArchiveEntry entry,
            String type,
            int mode,
            long size
    ) {
        entry.setSize(size);
        entry.setMode(mode);
        entry.setUserId(CANONICAL_UID);
        entry.setGroupId(CANONICAL_GID);
        entry.setUserName(CANONICAL_USER);
        entry.setGroupName(CANONICAL_GROUP);
        entry.setModTime(CANONICAL_MTIME_MILLIS);
        boolean expectedType = switch (type) {
            case "file" -> entry.isFile();
            case "directory" -> entry.isDirectory();
            case "symlink" -> entry.isSymbolicLink();
            default -> false;
        };
        if (!expectedType
                || entry.getMode() != mode
                || entry.getSize() != size
                || entry.getLongUserId() != CANONICAL_UID
                || entry.getLongGroupId() != CANONICAL_GID
                || !CANONICAL_USER.equals(entry.getUserName())
                || !CANONICAL_GROUP.equals(entry.getGroupName())
                || entry.getModTime().getTime() != CANONICAL_MTIME_MILLIS) {
            throw new IllegalStateException("snapshot tar entry is outside canonical profile");
        }
    }

    private static void requireStableFileKey(
            BasicFileAttributes attributes,
            String name
    ) {
        if (attributes.fileKey() == null) {
            throw new SecurityException(
                    "snapshot entry lacks a stable filesystem identity: " + name);
        }
    }

    private static void requireSameIdentity(
            BasicFileAttributes expected,
            BasicFileAttributes observed,
            String name,
            boolean requireFileKey
    ) {
        Object expectedKey = expected.fileKey();
        Object observedKey = observed.fileKey();
        if ((requireFileKey && (expectedKey == null || observedKey == null))
                || !Objects.equals(expectedKey, observedKey)
                || expected.size() != observed.size()
                || !expected.lastModifiedTime().equals(observed.lastModifiedTime())
                || expected.isRegularFile() != observed.isRegularFile()
                || expected.isDirectory() != observed.isDirectory()
                || expected.isSymbolicLink() != observed.isSymbolicLink()
                || expected.isOther() != observed.isOther()) {
            throw new SecurityException("snapshot entry identity changed: " + name);
        }
    }

    private final class SourceBudget {
        private int sourceFiles;
        private long sourceBytes;

        private void reserve(long fileBytes) {
            sourceFiles++;
            if (sourceFiles > limits.maxFiles()
                    || fileBytes < 0
                    || fileBytes > limits.maxFileBytes()
                    || fileBytes > Integer.MAX_VALUE) {
                throw new SecurityException("snapshot file limits exceeded");
            }
            try {
                sourceBytes = Math.addExact(sourceBytes, fileBytes);
            } catch (ArithmeticException overflow) {
                throw new SecurityException("snapshot source bytes exceed policy", overflow);
            }
            if (sourceBytes > limits.maxSourceBytes()) {
                throw new SecurityException("snapshot source bytes exceed policy");
            }
        }
    }

    private record SnapshotNode(Path path, BasicFileAttributes attributes) {
    }

    private record VerifiedRegularFile(
            byte[] content, String sha256, boolean lfsPointer, boolean executable
    ) {
    }

    private record VerifiedSymbolicLink(String target, String sha256) {
    }

    private static final class SourceAnchors implements AutoCloseable {
        private static final Set<PosixFilePermission> OWNER_ONLY = Set.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE,
                PosixFilePermission.OWNER_EXECUTE);

        private final Path directory;
        private final Set<Path> liveAnchors = new LinkedHashSet<>();
        private long sequence;

        private SourceAnchors(Path directory) {
            this.directory = directory;
        }

        private static SourceAnchors create(Path root) {
            Path parent = root.getParent();
            if (parent == null) {
                throw new SecurityException(
                        "snapshot filesystem root cannot host a private source anchor");
            }
            Path directory = null;
            try {
                directory = Files.createTempDirectory(parent, ".elmos-snapshot-anchor-",
                        PosixFilePermissions.asFileAttribute(OWNER_ONLY));
                BasicFileAttributes attributes = Files.readAttributes(
                        directory, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                if (!attributes.isDirectory()
                        || attributes.fileKey() == null
                        || !Files.getPosixFilePermissions(
                                directory, LinkOption.NOFOLLOW_LINKS).equals(OWNER_ONLY)) {
                    throw new SecurityException(
                            "snapshot source anchor is not owner-private and stable");
                }
                return new SourceAnchors(directory);
            } catch (UnsupportedOperationException unsupported) {
                deleteFailedAnchorDirectory(directory, unsupported);
                throw new SecurityException(
                        "snapshot source requires owner-private POSIX inode anchors",
                        unsupported);
            } catch (IOException unavailable) {
                deleteFailedAnchorDirectory(directory, unavailable);
                throw new SecurityException(
                        "snapshot source cannot establish a same-filesystem inode anchor",
                        unavailable);
            } catch (RuntimeException invalid) {
                deleteFailedAnchorDirectory(directory, invalid);
                throw invalid;
            }
        }

        private AnchoredNode anchor(
                Path source,
                String name,
                BasicFileAttributes expected
        ) {
            Path anchor = directory.resolve(String.format(
                    Locale.ROOT, "%016x", ++sequence));
            try {
                Files.createLink(anchor, source);
                liveAnchors.add(anchor);
                BasicFileAttributes anchored = Files.readAttributes(
                        anchor, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                requireSameIdentity(expected, anchored, name, true);
                return new AnchoredNode(anchor, this);
            } catch (UnsupportedOperationException | IOException unavailable) {
                throw new SecurityException(
                        "snapshot entry cannot be bound to a stable inode anchor: " + name,
                        unavailable);
            }
        }

        private void release(Path anchor) throws IOException {
            if (liveAnchors.contains(anchor)) {
                Files.delete(anchor);
                liveAnchors.remove(anchor);
            }
        }

        @Override
        public void close() throws IOException {
            IOException failure = null;
            List<Path> remaining = new ArrayList<>(liveAnchors);
            Collections.reverse(remaining);
            for (Path anchor : remaining) {
                try {
                    Files.deleteIfExists(anchor);
                    liveAnchors.remove(anchor);
                } catch (IOException cleanupFailure) {
                    if (failure == null) {
                        failure = cleanupFailure;
                    } else {
                        failure.addSuppressed(cleanupFailure);
                    }
                }
            }
            try {
                Files.delete(directory);
            } catch (IOException cleanupFailure) {
                if (failure == null) {
                    failure = cleanupFailure;
                } else {
                    failure.addSuppressed(cleanupFailure);
                }
            }
            if (failure != null) {
                throw failure;
            }
        }

        private static void deleteFailedAnchorDirectory(
                Path directory,
                Throwable failure
        ) {
            if (directory == null) {
                return;
            }
            try {
                Files.deleteIfExists(directory);
            } catch (IOException cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
        }
    }

    private record AnchoredNode(Path path, SourceAnchors owner) implements AutoCloseable {
        @Override
        public void close() throws IOException {
            owner.release(path);
        }
    }

    static final class ArchiveMetadataBudget {
        private final long limit;
        private long used = 2L * TAR_RECORD_BYTES;

        ArchiveMetadataBudget(long limit) {
            if (limit < used) {
                throw new IllegalArgumentException("tar metadata limit is too small");
            }
            this.limit = limit;
        }

        void reserve(String archiveName, String linkTarget) {
            long charge = canonicalMetadataCharge(archiveName, linkTarget);
            if (charge > limit - used) {
                throw new SecurityException(
                        "snapshot tar headers exceed materialization policy");
            }
            used += charge;
        }

        long used() {
            return used;
        }
    }

    static long canonicalMetadataCharge(String archiveName, String linkTarget) {
        int nameBytes = utf8Length(archiveName);
        long paxPayload = requiresPax(archiveName, 100)
                ? paxRecordUpperBound("path", nameBytes) : 0;
        if (linkTarget != null && requiresPax(linkTarget, 100)) {
            paxPayload = Math.addExact(paxPayload,
                    paxRecordUpperBound("linkpath", utf8Length(linkTarget)));
        }
        long charge = TAR_RECORD_BYTES;
        if (paxPayload > 0) {
            charge = Math.addExact(charge, TAR_RECORD_BYTES);
            charge = Math.addExact(charge, roundUpTarRecord(paxPayload));
        }
        return charge;
    }

    private static boolean requiresPax(String value, int fieldBytes) {
        return utf8Length(value) >= fieldBytes
                || value.codePoints().anyMatch(codePoint -> codePoint > 0x7f);
    }

    private static long paxRecordUpperBound(String key, int valueBytes) {
        // POSIX record: decimal length, one space, key, '=', value, and newline. Thirty-two bytes
        // is a conservative bound for the decimal length and separators at this policy scale.
        return Math.addExact(valueBytes, key.getBytes(StandardCharsets.US_ASCII).length + 32L);
    }

    private static long roundUpTarRecord(long bytes) {
        long remainder = bytes % TAR_RECORD_BYTES;
        return remainder == 0 ? bytes : Math.addExact(bytes, TAR_RECORD_BYTES - remainder);
    }

    private static boolean excluded(Path relative) {
        for (Path segment : relative) if (EXCLUDED_NAMES.contains(segment.toString()) || segment.toString().startsWith("elmos-secret-")) return true;
        return false;
    }
    static String portable(Path path) {
        String portable = path.toString().replace(path.getFileSystem().getSeparator(), "/");
        if (portable.isBlank()
                || portable.indexOf('\\') >= 0
                || portable.indexOf('\0') >= 0
                || utf8Length(portable) > MAX_PORTABLE_UTF8_BYTES) {
            throw new SecurityException(
                    "snapshot portable path is outside materialization policy");
        }
        return portable;
    }

    private static int utf8Length(String value) {
        return value.getBytes(StandardCharsets.UTF_8).length;
    }
    private static boolean isLfsPointer(byte[] content) {
        return content.length <= 1024
                && new String(content, StandardCharsets.UTF_8)
                .startsWith("version https://git-lfs.github.com/spec/v1");
    }

    private static MessageDigest sha256Digest() {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch (Exception exception) { throw new IllegalStateException(exception); }
    }
    private static String digest(byte[] bytes) {
        return HexFormat.of().formatHex(sha256Digest().digest(bytes));
    }
}
