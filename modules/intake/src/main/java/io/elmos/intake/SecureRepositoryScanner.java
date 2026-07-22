package io.elmos.intake;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.*;

import static io.elmos.intake.IntakeModels.*;

/** Metadata-only scanner. It never executes repository code or returns file contents. */
final class SecureRepositoryScanner {
    private static final Set<String> SECRET_NAMES = Set.of(".env", "id_rsa", "id_ed25519", "credentials", "credentials.json",
            "secrets.yml", "secrets.yaml", "secrets.json", ".npmrc", "settings.xml", "nuget.config", "pip.conf");
    private static final Set<String> VENDORED_SEGMENTS = Set.of("vendor", "vendors", "third_party", "third-party", "node_modules");
    private static final Set<String> GENERATED_SEGMENTS = Set.of("target", "build", "dist", "out", ".next", "coverage", "bin", "obj");
    private final Clock clock;

    SecureRepositoryScanner(Clock clock) { this.clock = Objects.requireNonNull(clock); }

    RepositorySnapshot scan(Path requestedRoot, IntakeRequest request) {
        validateRequest(request);
        Path root = secureRoot(requestedRoot);
        List<FileEntry> files = new ArrayList<>();
        long[] total = {0}; int[] count = {0};
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    if (!dir.equals(root) && dir.getFileName().toString().equals(".git")) return FileVisitResult.SKIP_SUBTREE;
                    if (Files.isSymbolicLink(dir)) throw new SecurityException("SYMLINK_DIRECTORY_REJECTED:" + portable(root.relativize(dir)));
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFile(Path path, BasicFileAttributes attrs) throws IOException {
                    if (attrs.isSymbolicLink()) throw new SecurityException("SYMLINK_FILE_REJECTED:" + portable(root.relativize(path)));
                    if (!attrs.isRegularFile()) throw new SecurityException("SPECIAL_FILE_REJECTED:" + portable(root.relativize(path)));
                    count[0]++; total[0] += attrs.size();
                    if (count[0] > request.limits().maxFiles() || total[0] > request.limits().maxTotalBytes())
                        throw new ScanLimitException("REPOSITORY_SCAN_LIMIT_EXCEEDED");
                    if (attrs.size() > request.limits().maxBytesPerFile())
                        throw new ScanLimitException("FILE_SCAN_LIMIT_EXCEEDED:" + portable(root.relativize(path)));
                    byte[] bytes = Files.readAllBytes(path);
                    String relative = portable(root.relativize(path));
                    boolean binary = isBinary(bytes); boolean generated = generated(relative, bytes);
                    boolean vendored = hasSegment(relative, VENDORED_SEGMENTS);
                    boolean secret = secretLike(relative);
                    files.add(new FileEntry(relative, attrs.size(), sha256(bytes), classify(relative, binary, generated, vendored),
                            generated, vendored, binary, secret, secret || binary || vendored));
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (ScanLimitException error) { throw new IllegalArgumentException(error.getMessage()); }
        catch (IOException error) { throw new IllegalArgumentException("REPOSITORY_SCAN_FAILED", error); }
        files.sort(Comparator.comparing(FileEntry::path));
        String integrity = integrityHash(request, files);
        String snapshotId = "sha256:" + integrity;
        Repository repository = request.sourceType() == SourceType.GIT
                ? new Repository(safeRemote(request.repositoryRemote()), request.branch(), request.commitSha().toLowerCase(Locale.ROOT)) : null;
        return new RepositorySnapshot("1.0", snapshotId, request.sourceType(), repository, request.uploadId(),
                files.size(), total[0], files, readSubmodules(root), clock.instant(), integrity);
    }

    private static void validateRequest(IntakeRequest request) {
        Objects.requireNonNull(request, "request"); Objects.requireNonNull(request.sourceType(), "sourceType");
        if (request.sourceType() == SourceType.GIT) {
            if (request.repositoryRemote() == null || request.repositoryRemote().isBlank()) throw new IllegalArgumentException("repositoryRemote is required");
            if (request.commitSha() == null || !request.commitSha().matches("(?i)[0-9a-f]{40}|[0-9a-f]{64}"))
                throw new IllegalArgumentException("resolved commit SHA is required");
            safeRemote(request.repositoryRemote());
        } else if (request.uploadId() == null || request.uploadId().isBlank()) throw new IllegalArgumentException("uploadId is required");
    }

    private static String safeRemote(String value) {
        if (value == null) return null;
        if (value.matches("^[^/]+@[^:]+:.*$")) return "ssh://" + value.substring(value.indexOf('@') + 1).replace(':', '/');
        URI uri;
        try { uri = URI.create(value); } catch (RuntimeException error) { throw new IllegalArgumentException("repositoryRemote is invalid"); }
        if (!Set.of("https", "ssh").contains(uri.getScheme())) throw new IllegalArgumentException("repositoryRemote protocol is not allowed");
        if (uri.getRawUserInfo() != null) {
            if (!uri.getScheme().equals("ssh")) throw new IllegalArgumentException("repositoryRemote must not contain credentials");
            try { return new URI(uri.getScheme(), null, uri.getHost(), uri.getPort(), uri.getPath(), uri.getQuery(), uri.getFragment()).toString(); }
            catch (URISyntaxException error) { throw new IllegalArgumentException("repositoryRemote is invalid"); }
        }
        return uri.toString();
    }

    private static Path secureRoot(Path requested) {
        Objects.requireNonNull(requested, "repository root");
        try {
            Path absolute = requested.toAbsolutePath().normalize();
            if (Files.isSymbolicLink(absolute) || !Files.isDirectory(absolute, LinkOption.NOFOLLOW_LINKS))
                throw new SecurityException("repository root must be a real directory");
            return absolute.toRealPath(LinkOption.NOFOLLOW_LINKS);
        } catch (IOException error) { throw new IllegalArgumentException("REPOSITORY_ROOT_UNAVAILABLE", error); }
    }

    private static List<String> readSubmodules(Path root) {
        Path file = root.resolve(".gitmodules"); if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) return List.of();
        try {
            return Files.readAllLines(file, StandardCharsets.UTF_8).stream().map(String::strip)
                    .filter(line -> line.startsWith("path") && line.contains("="))
                    .map(line -> line.substring(line.indexOf('=') + 1).strip()).filter(value -> !value.isBlank()).sorted().toList();
        } catch (IOException error) { throw new IllegalArgumentException("GITMODULES_READ_FAILED", error); }
    }

    static FileCategory classify(String path, boolean binary, boolean generated, boolean vendored) {
        String lower = path.toLowerCase(Locale.ROOT); String name = lower.substring(lower.lastIndexOf('/') + 1);
        if (binary) return FileCategory.BINARY;
        if (vendored) return FileCategory.VENDORED_CODE;
        if (generated) return FileCategory.GENERATED_SOURCE;
        if (lower.contains("/src/test/") || lower.contains("/tests/") || lower.contains("/test/") || name.matches(".*(test|tests|spec)\\.(java|py|cs|js|jsx|ts|tsx)$")) return FileCategory.TEST_SOURCE;
        if (name.equals("dockerfile") || name.startsWith("dockerfile.") || name.equals("docker-compose.yml") || name.equals("compose.yml")) return FileCategory.CONTAINER_CONFIG;
        if (lower.startsWith(".github/") || lower.contains("/.github/") || name.equals(".gitlab-ci.yml") || name.equals("azure-pipelines.yml")) return FileCategory.CI_CONFIG;
        if (Set.of("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "pipfile", "poetry.lock", "uv.lock", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json", "jsconfig.json", "turbo.json", "nx.json", "global.json", "directory.build.props", "directory.packages.props").contains(name)
                || name.endsWith(".csproj") || name.endsWith(".sln") || name.endsWith(".fsproj")) return FileCategory.BUILD_CONFIG;
        if (name.endsWith(".sql") || lower.contains("/migrations/") || lower.contains("/db/migration/")) return FileCategory.DATABASE_MIGRATION;
        if (name.endsWith(".proto") || name.endsWith(".graphql") || name.contains("openapi") || name.contains("swagger")) return FileCategory.API_CONTRACT;
        if (name.endsWith(".schema.json") || name.endsWith(".xsd")) return FileCategory.SCHEMA;
        if (name.endsWith(".md") || name.endsWith(".adoc") || name.endsWith(".rst") || name.startsWith("license")) return FileCategory.DOCUMENTATION;
        if (name.endsWith(".java") || name.endsWith(".py") || name.endsWith(".cs") || name.endsWith(".js") || name.endsWith(".jsx") || name.endsWith(".ts") || name.endsWith(".tsx")) return FileCategory.PRODUCTION_SOURCE;
        if (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties") || name.endsWith(".toml") || name.endsWith(".ini") || name.endsWith(".conf") || name.endsWith(".json")) return FileCategory.RUNTIME_CONFIG;
        if (lower.contains("/resources/") || lower.contains("/public/") || lower.contains("/assets/")) return FileCategory.RESOURCE;
        return FileCategory.UNKNOWN;
    }

    private static boolean generated(String path, byte[] bytes) {
        if (hasSegment(path, GENERATED_SEGMENTS)) return true;
        if (bytes.length == 0 || isBinary(bytes)) return false;
        String head = new String(bytes, 0, Math.min(bytes.length, 4096), StandardCharsets.UTF_8).toLowerCase(Locale.ROOT);
        return head.contains("generated code") || head.contains("code generated") || head.contains("auto-generated") || head.contains("@generated");
    }
    private static boolean secretLike(String path) {
        String lower = path.toLowerCase(Locale.ROOT); String name = lower.substring(lower.lastIndexOf('/') + 1);
        return SECRET_NAMES.contains(name) || name.endsWith(".pem") || name.endsWith(".p12") || name.endsWith(".pfx")
                || name.endsWith(".key") || lower.contains("/secrets/");
    }
    private static boolean hasSegment(String path, Set<String> names) {
        for (String segment : path.toLowerCase(Locale.ROOT).split("/")) if (names.contains(segment)) return true;
        return false;
    }
    static boolean isBinary(byte[] bytes) {
        int sample = Math.min(bytes.length, 8192); if (sample == 0) return false;
        int suspicious = 0;
        for (int i = 0; i < sample; i++) { int value = bytes[i] & 0xff; if (value == 0) return true; if (value < 9 || (value > 13 && value < 32)) suspicious++; }
        return suspicious > sample / 10;
    }
    static String sha256(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch (Exception error) { throw new IllegalStateException(error); }
    }
    private static String integrityHash(IntakeRequest request, List<FileEntry> files) {
        StringBuilder canonical = new StringBuilder(request.sourceType().name()).append('\0');
        if (request.sourceType() == SourceType.GIT) canonical.append(request.commitSha().toLowerCase(Locale.ROOT));
        else canonical.append(request.uploadId());
        for (FileEntry file : files) canonical.append('\0').append(file.path()).append('\0').append(file.bytes()).append('\0').append(file.sha256());
        return sha256(canonical.toString().getBytes(StandardCharsets.UTF_8));
    }
    private static String portable(Path path) { return path.toString().replace(path.getFileSystem().getSeparator(), "/"); }
    private static final class ScanLimitException extends RuntimeException { ScanLimitException(String message) { super(message); } }
}
