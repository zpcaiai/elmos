package io.elmos.snapshot;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.github.luben.zstd.ZstdOutputStream;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.*;

public final class DeterministicSnapshotArchiver {
    public record Limits(int maxEntries, int maxFiles, long maxFileBytes, long maxSourceBytes) {
        public Limits {
            if (maxEntries < 1 || maxEntries > 500_000 || maxFiles < 1 || maxFiles > maxEntries
                    || maxFileBytes < 1 || maxSourceBytes < maxFileBytes || maxSourceBytes > 2_147_483_648L)
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
                                  String manifestSha256, long sourceBytes, int sourceFiles) {
        public SnapshotArchive { archive = archive.clone(); manifest = manifest.clone(); }
        @Override public byte[] archive() { return archive.clone(); }
        @Override public byte[] manifest() { return manifest.clone(); }
    }

    private static final Set<String> EXCLUDED_NAMES = Set.of(".git", ".elmos", ".env", "id_rsa", "id_ed25519");
    private final ObjectMapper objectMapper = new ObjectMapper().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    private final Limits limits;

    public DeterministicSnapshotArchiver() { this(new Limits(100_000, 50_000, 64L * 1024 * 1024, 256L * 1024 * 1024)); }
    public DeterministicSnapshotArchiver(Limits limits) { this.limits = Objects.requireNonNull(limits); }

    public SnapshotArchive archive(Path sourceRoot) {
        return archive(sourceRoot, new SnapshotContext("UNKNOWN", "unknown", "unknown/unknown", "unknown",
                "0".repeat(40), "unknown"));
    }

    public SnapshotArchive archive(Path sourceRoot, SnapshotContext context) {
        try {
            Path root = sourceRoot.toRealPath(LinkOption.NOFOLLOW_LINKS);
            if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) throw new IllegalArgumentException("snapshot source must be a directory");
            List<Path> paths;
            try (var stream = Files.walk(root)) {
                paths = stream.filter(path -> !path.equals(root)).filter(path -> !excluded(root.relativize(path)))
                        .limit((long) limits.maxEntries() + 1)
                        .sorted(Comparator.comparing(path -> portable(root.relativize(path)))).toList();
            }
            if (paths.size() > limits.maxEntries()) throw new SecurityException("snapshot entry count exceeds policy");
            int sourceFileCount = 0; long sourceByteCount = 0;
            for (Path path : paths) {
                BasicFileAttributes attributes = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
                if (attributes.isRegularFile()) {
                    sourceFileCount++;
                    if (sourceFileCount > limits.maxFiles() || attributes.size() > limits.maxFileBytes())
                        throw new SecurityException("snapshot file limits exceeded");
                    sourceByteCount = Math.addExact(sourceByteCount, attributes.size());
                    if (sourceByteCount > limits.maxSourceBytes()) throw new SecurityException("snapshot source bytes exceed policy");
                }
            }
            List<ManifestEntry> entries = new ArrayList<>();
            ByteArrayOutputStream archiveBytes = new ByteArrayOutputStream();
            try (ZstdOutputStream zstd = new ZstdOutputStream(archiveBytes, 9);
                 TarArchiveOutputStream tar = new TarArchiveOutputStream(zstd, StandardCharsets.UTF_8.name())) {
                tar.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX);
                for (Path path : paths) add(root, path, tar, entries);
                tar.finish();
            }
            String archiveDigest = digest(archiveBytes.toByteArray());
            List<String> symlinks = entries.stream().filter(entry -> entry.type().equals("symlink")).map(ManifestEntry::path).toList();
            List<String> lfs = entries.stream().filter(entry -> entry.type().equals("file"))
                    .filter(entry -> isLfsPointer(root.resolve(entry.path()))).map(ManifestEntry::path).toList();
            List<String> submodules = Files.exists(root.resolve(".gitmodules")) ? List.of(".gitmodules:review-required") : List.of();
            byte[] manifest = objectMapper.writeValueAsBytes(new SnapshotManifest("1.0",
                    new RepositoryInfo(context.provider(), context.repositoryId(), context.fullName()),
                    new SourceInfo(context.requestedRef(), context.commitSha(), context.treeSha()),
                    new ArchiveInfo("SHA-256", archiveDigest, "tar.zst"), entries,
                    new SpecialContent(submodules, lfs, symlinks)));
            long sourceBytes = sourceByteCount;
            int sourceFiles = sourceFileCount;
            return new SnapshotArchive(archiveBytes.toByteArray(), archiveDigest, manifest,
                    digest(manifest), sourceBytes, sourceFiles);
        } catch (IOException exception) {
            throw new IllegalStateException("unable to create deterministic snapshot", exception);
        }
    }

    private static void add(Path root, Path path, TarArchiveOutputStream tar, List<ManifestEntry> manifest) throws IOException {
        String name = portable(root.relativize(path));
        BasicFileAttributes attributes = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (attributes.isOther()) throw new SecurityException("unsupported special file: " + name);
        TarArchiveEntry entry;
        String type; String fileDigest = null; String target = null; long size = 0; int mode;
        byte[] content = null;
        if (attributes.isSymbolicLink()) {
            Path rawTarget = Files.readSymbolicLink(path);
            if (rawTarget.isAbsolute()) throw new SecurityException("absolute symlink is not deterministic: " + name);
            Path resolved = path.getParent().resolve(rawTarget).normalize();
            if (!resolved.startsWith(root)) throw new SecurityException("symlink escapes snapshot root: " + name);
            entry = new TarArchiveEntry(name, TarArchiveEntry.LF_SYMLINK);
            target = portable(rawTarget); entry.setLinkName(target); type = "symlink"; mode = 0777;
            fileDigest = digest(target.getBytes(StandardCharsets.UTF_8));
        } else if (attributes.isDirectory()) {
            entry = new TarArchiveEntry(name + "/"); type = "directory"; mode = 0755;
        } else if (attributes.isRegularFile()) {
            content = Files.readAllBytes(path); size = content.length; fileDigest = digest(content);
            entry = new TarArchiveEntry(name); entry.setSize(size); type = "file"; mode = Files.isExecutable(path) ? 0755 : 0644;
        } else throw new SecurityException("unsupported entry: " + name);
        entry.setMode(mode); entry.setUserId(10001); entry.setGroupId(10001); entry.setUserName("elmos"); entry.setGroupName("elmos"); entry.setModTime(0);
        tar.putArchiveEntry(entry); if (content != null) tar.write(content); tar.closeArchiveEntry();
        manifest.add(new ManifestEntry(name, type, size, mode, fileDigest, target));
    }

    private static boolean excluded(Path relative) {
        for (Path segment : relative) if (EXCLUDED_NAMES.contains(segment.toString()) || segment.toString().startsWith("elmos-secret-")) return true;
        return false;
    }
    private static String portable(Path path) { return path.toString().replace(path.getFileSystem().getSeparator(), "/"); }
    private static boolean isLfsPointer(Path path) {
        try {
            if (Files.size(path) > 1024) return false;
            return Files.readString(path, StandardCharsets.UTF_8).startsWith("version https://git-lfs.github.com/spec/v1");
        } catch (IOException | RuntimeException ignored) { return false; }
    }
    private static String digest(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (Exception exception) { throw new IllegalStateException(exception); }
    }
}
