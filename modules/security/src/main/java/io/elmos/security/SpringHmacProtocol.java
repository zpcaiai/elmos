package io.elmos.security;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.nio.file.SecureDirectoryStream;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.PosixFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Canonical authentication contract for the three privileged Spring launch routes.
 *
 * <p>The protocol, role, HTTP method and exact route are signed before the request metadata and
 * body digest. A signature from one role therefore cannot authorize another role or route, even
 * if an operator accidentally deploys the same secret to both services.</p>
 */
public final class SpringHmacProtocol {
    public static final String VERSION = "ELMOS-SPRING-HMAC-V1";
    public static final String HTTP_METHOD = "POST";
    public static final int MIN_SECRET_BYTES = 32;
    public static final int MAX_SECRET_BYTES = 4096;
    private static final Pattern CANONICAL_TIMESTAMP = Pattern.compile("[0-9]{1,20}");
    private static final Pattern CANONICAL_NONCE = Pattern.compile(
            "[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}");

    public enum Role {
        VERIFIER("VERIFIER", "/internal/v1/spring-verifications"),
        TRANSFORMER("TRANSFORMER", "/internal/v1/spring-transformations"),
        RUNTIME("RUNTIME", "/internal/v1/spring-runtimes");

        private final String wireName;
        private final String exactPath;

        Role(String wireName, String exactPath) {
            this.wireName = wireName;
            this.exactPath = exactPath;
        }

        public String wireName() {
            return wireName;
        }

        public String exactPath() {
            return exactPath;
        }
    }

    private SpringHmacProtocol() {}

    /**
     * Reads the secret byte-for-byte. Text trimming is deliberately forbidden: different files
     * must never collapse to one effective HMAC credential at runtime.
     */
    public static byte[] readSecret(Path path, String label) {
        return readSecret(path, label, () -> {});
    }

    static byte[] readSecret(Path path, String label, Runnable afterOpen) {
        Objects.requireNonNull(path, "secret path");
        Objects.requireNonNull(afterOpen, "afterOpen");
        String description = requireLabel(label);
        if (!path.isAbsolute() || !path.equals(path.normalize())) {
            throw new IllegalStateException(
                    description + " HMAC secret path must be absolute and normalized");
        }
        Path root = path.getRoot();
        Path leaf = path.getFileName();
        if (root == null || leaf == null || path.getNameCount() < 1) {
            throw new IllegalStateException(description + " HMAC secret path is invalid");
        }
        List<SecureDirectoryStream<Path>> opened = new ArrayList<>();
        try {
            SecureDirectoryStream<Path> parent = openSecureRoot(root, description, opened);
            if (parent == null) {
                if (System.getProperty("os.name", "").equalsIgnoreCase("Linux")) {
                    throw new IllegalStateException(
                            description + " HMAC secret requires secure no-follow filesystem access");
                }
                return readSecretDevelopmentFallback(path, description, afterOpen);
            }
            for (int index = 0; index < path.getNameCount() - 1; index++) {
                Path component = path.getName(index);
                PosixFileAttributes attributes = posixAttributes(parent, component, description);
                if (!attributes.isDirectory() || attributes.isSymbolicLink()) {
                    throw new IllegalStateException(
                            description + " HMAC secret path contains a symbolic or non-directory parent");
                }
                parent = parent.newDirectoryStream(component, LinkOption.NOFOLLOW_LINKS);
                opened.add(parent);
            }

            PosixFileAttributes before = posixAttributes(parent, leaf, description);
            UnixPathIdentity beforeIdentity = unixPathIdentity(
                    path, before.fileKey(), description);
            validateSecretMetadata(before, beforeIdentity, description);

            Set<OpenOption> options = Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS);
            byte[] raw;
            try (SeekableByteChannel channel = parent.newByteChannel(leaf, options)) {
                afterOpen.run();
                raw = readBounded(channel, before.size(), description);
            }

            PosixFileAttributes after = posixAttributes(parent, leaf, description);
            UnixPathIdentity afterIdentity = unixPathIdentity(
                    path, after.fileKey(), description);
            validateSecretMetadata(after, afterIdentity, description);
            validateStable(before, after, beforeIdentity, afterIdentity, description);
            return requireSecret(raw, description);
        } catch (IOException error) {
            throw new IllegalStateException(
                    description + " HMAC secret file could not be read", error);
        } finally {
            for (int index = opened.size() - 1; index >= 0; index--) {
                try {
                    opened.get(index).close();
                } catch (IOException ignored) {
                    // The secret bytes are already detached; a close failure grants no access.
                }
            }
        }
    }

    /** Validates an injected one-time credential under the same byte contract as file secrets. */
    public static byte[] requireSecret(byte[] value, String label) {
        Objects.requireNonNull(value, "secret");
        String description = requireLabel(label);
        if (value.length < MIN_SECRET_BYTES || value.length > MAX_SECRET_BYTES) {
            throw new IllegalStateException(
                    description + " HMAC secret must contain 32-4096 bytes");
        }
        String decoded;
        try {
            decoded = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(value))
                    .toString();
        } catch (CharacterCodingException error) {
            throw new IllegalStateException(
                    description + " HMAC secret must contain canonical UTF-8 bytes", error);
        }
        if (decoded.isEmpty()
                || boundaryWhitespace(decoded.codePointAt(0))
                || boundaryWhitespace(decoded.codePointBefore(decoded.length()))) {
            throw new IllegalStateException(
                    description + " HMAC secret must not have leading or trailing whitespace");
        }
        return value.clone();
    }

    public static String sign(
            byte[] secret,
            Role role,
            String timestamp,
            String nonce,
            byte[] body
    ) {
        try {
            byte[] key = requireSecret(secret, role.wireName().toLowerCase());
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(canonical(role, timestamp, nonce, body)));
        } catch (IllegalStateException error) {
            throw error;
        } catch (Exception error) {
            throw new IllegalStateException("Spring HMAC-SHA256 is unavailable", error);
        }
    }

    public static byte[] canonical(Role role, String timestamp, String nonce, byte[] body) {
        Objects.requireNonNull(role, "role");
        Objects.requireNonNull(body, "body");
        if (!isCanonicalTimestamp(timestamp)) {
            throw new IllegalArgumentException("Spring HMAC timestamp is invalid");
        }
        if (!isCanonicalNonce(nonce)) {
            throw new IllegalArgumentException("Spring HMAC nonce is invalid");
        }
        String canonical = String.join("\n",
                VERSION,
                role.wireName(),
                HTTP_METHOD,
                role.exactPath(),
                timestamp,
                nonce,
                sha256(body));
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    /** Returns true only for the unsigned base-10 epoch representation used on the wire. */
    public static boolean isCanonicalTimestamp(String value) {
        return value != null && CANONICAL_TIMESTAMP.matcher(value).matches();
    }

    /** Returns true only for the lowercase RFC 4122 version-4 nonce emitted by the clients. */
    public static boolean isCanonicalNonce(String value) {
        return value != null && CANONICAL_NONCE.matcher(value).matches();
    }

    public static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(Objects.requireNonNull(value)));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }

    private static boolean boundaryWhitespace(int codePoint) {
        return Character.isWhitespace(codePoint) || Character.isSpaceChar(codePoint);
    }

    @SuppressWarnings("unchecked")
    private static SecureDirectoryStream<Path> openSecureRoot(
            Path root,
            String description,
            List<SecureDirectoryStream<Path>> opened
    ) throws IOException {
        var stream = Files.newDirectoryStream(root);
        if (!(stream instanceof SecureDirectoryStream<?>)) {
            stream.close();
            return null;
        }
        SecureDirectoryStream<Path> secure = (SecureDirectoryStream<Path>) stream;
        opened.add(secure);
        return secure;
    }

    /**
     * macOS' default NIO provider has no SecureDirectoryStream. This development-only branch
     * checks every parent and the final inode both before and after a no-follow channel read. A
     * Linux production runtime never reaches this weaker compatibility branch.
     */
    private static byte[] readSecretDevelopmentFallback(
            Path path,
            String description,
            Runnable afterOpen
    ) throws IOException {
        Map<Path, BasicFileAttributes> parents = parentAttributes(path, description);
        PosixFileAttributes before = Files.readAttributes(
                path, PosixFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        UnixPathIdentity beforeIdentity = unixPathIdentity(path, before.fileKey(), description);
        validateSecretMetadata(before, beforeIdentity, description);
        byte[] raw;
        try (SeekableByteChannel channel = Files.newByteChannel(
                path, Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
            afterOpen.run();
            raw = readBounded(channel, before.size(), description);
        }
        PosixFileAttributes after = Files.readAttributes(
                path, PosixFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        UnixPathIdentity afterIdentity = unixPathIdentity(path, after.fileKey(), description);
        validateSecretMetadata(after, afterIdentity, description);
        validateStable(before, after, beforeIdentity, afterIdentity, description);
        for (Map.Entry<Path, BasicFileAttributes> entry : parents.entrySet()) {
            BasicFileAttributes current = Files.readAttributes(
                    entry.getKey(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            BasicFileAttributes expected = entry.getValue();
            if (current.isSymbolicLink()
                    || !current.isDirectory()
                    || expected.fileKey() == null
                    || !expected.fileKey().equals(current.fileKey())) {
                throw new IllegalStateException(
                        description + " HMAC secret parent changed while it was being read");
            }
        }
        return requireSecret(raw, description);
    }

    private static Map<Path, BasicFileAttributes> parentAttributes(
            Path path,
            String description
    ) throws IOException {
        Map<Path, BasicFileAttributes> result = new LinkedHashMap<>();
        Path current = path.getRoot();
        for (int index = 0; index < path.getNameCount() - 1; index++) {
            current = current.resolve(path.getName(index));
            BasicFileAttributes attributes = Files.readAttributes(
                    current, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attributes.isDirectory() || attributes.isSymbolicLink()) {
                throw new IllegalStateException(
                        description + " HMAC secret path contains a symbolic or non-directory parent");
            }
            result.put(current, attributes);
        }
        return result;
    }

    private static PosixFileAttributes posixAttributes(
            SecureDirectoryStream<Path> directory,
            Path relative,
            String description
    ) throws IOException {
        PosixFileAttributeView view = directory.getFileAttributeView(
                relative, PosixFileAttributeView.class, LinkOption.NOFOLLOW_LINKS);
        if (view == null) {
            throw new IllegalStateException(
                    description + " HMAC secret requires POSIX ownership and mode checks");
        }
        return view.readAttributes();
    }

    private static void validateSecretMetadata(
            PosixFileAttributes attributes,
            UnixPathIdentity identity,
            String description
    ) throws IOException {
        if (!attributes.isRegularFile() || attributes.isSymbolicLink()) {
            throw new IllegalStateException(description + " HMAC secret must be a regular file");
        }
        Set<PosixFilePermission> permissions = attributes.permissions();
        Set<PosixFilePermission> ownerReadOnly = Set.of(PosixFilePermission.OWNER_READ);
        Set<PosixFilePermission> ownerReadWrite = Set.of(
                PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE);
        if (!permissions.equals(ownerReadOnly) && !permissions.equals(ownerReadWrite)) {
            throw new IllegalStateException(
                    description + " HMAC secret mode must be 0400 or 0600");
        }
        if (identity.uid() != processEffectiveUid()) {
            throw new IllegalStateException(
                    description + " HMAC secret must be owned by the current process user");
        }
        if (identity.links() != 1) {
            throw new IllegalStateException(
                    description + " HMAC secret must have exactly one hard link");
        }
        if (attributes.size() < MIN_SECRET_BYTES || attributes.size() > MAX_SECRET_BYTES) {
            throw new IllegalStateException(
                    description + " HMAC secret must contain 32-4096 bytes");
        }
    }

    private static void validateStable(
            PosixFileAttributes before,
            PosixFileAttributes after,
            UnixPathIdentity beforeIdentity,
            UnixPathIdentity afterIdentity,
            String description
    ) {
        if (before.fileKey() == null
                || !before.fileKey().equals(after.fileKey())
                || before.size() != after.size()
                || !before.lastModifiedTime().equals(after.lastModifiedTime())
                || !before.owner().equals(after.owner())
                || !before.permissions().equals(after.permissions())
                || !beforeIdentity.equals(afterIdentity)) {
            throw new IllegalStateException(
                    description + " HMAC secret changed while it was being read");
        }
    }

    private static long processEffectiveUid() throws IOException {
        if (System.getProperty("os.name", "").equalsIgnoreCase("Linux")) {
            return parseEffectiveUid(Files.readString(
                    Path.of("/proc/self/status"), StandardCharsets.US_ASCII));
        }
        String userHome = System.getProperty("user.home", "");
        if (userHome.isBlank()) {
            throw new IllegalStateException(
                    "current process owner cannot be established on this development platform");
        }
        Object value = Files.getAttribute(
                Path.of(userHome).toAbsolutePath().normalize(), "unix:uid");
        if (value instanceof Number number) return number.longValue();
        throw new IllegalStateException(
                "current process UID cannot be established on this development platform");
    }

    static long parseEffectiveUid(String procStatus) {
        for (String line : Objects.requireNonNull(procStatus).split("\\R")) {
            if (!line.startsWith("Uid:")) continue;
            String[] fields = line.trim().split("\\s+");
            if (fields.length != 5 || !fields[2].matches("[0-9]+")) break;
            try {
                return Long.parseLong(fields[2]);
            } catch (NumberFormatException ignored) {
                break;
            }
        }
        throw new IllegalStateException("effective UID is unavailable from /proc/self/status");
    }

    private static UnixPathIdentity unixPathIdentity(
            Path path,
            Object secureFileKey,
            String description
    ) throws IOException {
        try {
            BasicFileAttributes before = Files.readAttributes(
                    path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (secureFileKey == null || !secureFileKey.equals(before.fileKey())) {
                throw new IllegalStateException(
                        description + " HMAC secret full path no longer names the opened inode");
            }
            Map<String, Object> values = Files.readAttributes(
                    path, "unix:uid,nlink", LinkOption.NOFOLLOW_LINKS);
            BasicFileAttributes after = Files.readAttributes(
                    path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!secureFileKey.equals(after.fileKey())
                    || !before.fileKey().equals(after.fileKey())) {
                throw new IllegalStateException(
                        description + " HMAC secret full path changed during metadata inspection");
            }
            Object uid = values.get("uid");
            Object links = values.get("nlink");
            if (uid instanceof Number owner && links instanceof Number linkCount) {
                return new UnixPathIdentity(
                        secureFileKey, owner.longValue(), linkCount.longValue());
            }
        } catch (UnsupportedOperationException error) {
            throw new IllegalStateException(
                    description + " HMAC secret requires Unix ownership and link metadata", error);
        }
        throw new IllegalStateException(
                description + " HMAC secret Unix metadata is unavailable");
    }

    private static byte[] readBounded(
            SeekableByteChannel channel,
            long expectedSize,
            String description
    ) throws IOException {
        if (expectedSize < MIN_SECRET_BYTES || expectedSize > MAX_SECRET_BYTES) {
            throw new IllegalStateException(
                    description + " HMAC secret must contain 32-4096 bytes");
        }
        ByteBuffer buffer = ByteBuffer.allocate(Math.toIntExact(expectedSize));
        int zeroReads = 0;
        while (buffer.hasRemaining()) {
            int count = channel.read(buffer);
            if (count < 0) break;
            if (count == 0 && ++zeroReads > 8) {
                throw new IllegalStateException(
                        description + " HMAC secret could not be read completely");
            }
            if (count > 0) zeroReads = 0;
        }
        if (buffer.hasRemaining() || channel.read(ByteBuffer.allocate(1)) != -1) {
            throw new IllegalStateException(
                    description + " HMAC secret size changed while it was being read");
        }
        return buffer.array();
    }

    private static String requireLabel(String value) {
        if (value == null || !value.matches("[A-Za-z][A-Za-z0-9 _-]{1,80}")) {
            throw new IllegalArgumentException("secret label is invalid");
        }
        return value;
    }

    private record UnixPathIdentity(Object fileKey, long uid, long links) {}
}
