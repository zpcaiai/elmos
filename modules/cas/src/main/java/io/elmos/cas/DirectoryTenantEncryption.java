package io.elmos.cas;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Base64;
import java.util.EnumSet;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Loads versioned tenant AES keys from an operator-mounted, owner-only directory.
 *
 * <p>No key bytes or key paths are accepted through application properties. The configured value
 * names only the mount root. Tenant names are SHA-256 namespaced before path resolution, so an
 * authenticated tenant identifier cannot traverse the filesystem.
 *
 * <p>Layout:
 * <pre>
 *   key-root/&lt;sha256(tenant namespace)&gt;/current        # key id, UTF-8
 *   key-root/&lt;sha256(tenant namespace)&gt;/&lt;key-id&gt;.key   # base64 of 32 bytes, mode 0600
 * </pre>
 * Old key files remain readable after {@code current} changes, which permits online rotation of
 * new writes without making existing envelopes unreadable.
 */
public final class DirectoryTenantEncryption implements TenantEncryption {

    private static final Pattern KEY_ID = Pattern.compile("^[A-Za-z0-9._-]{1,64}$");
    private static final Set<PosixFilePermission> FORBIDDEN_KEY_PERMISSIONS = EnumSet.of(
            PosixFilePermission.GROUP_READ, PosixFilePermission.GROUP_WRITE,
            PosixFilePermission.GROUP_EXECUTE, PosixFilePermission.OTHERS_READ,
            PosixFilePermission.OTHERS_WRITE, PosixFilePermission.OTHERS_EXECUTE);
    private static final Set<PosixFilePermission> FORBIDDEN_CONTROL_PERMISSIONS = EnumSet.of(
            PosixFilePermission.GROUP_WRITE, PosixFilePermission.OTHERS_WRITE);

    private final Path keyRoot;

    public DirectoryTenantEncryption(Path keyRoot) {
        this.keyRoot = keyRoot.toAbsolutePath().normalize();
        if (!Files.isDirectory(this.keyRoot, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(this.keyRoot)) {
            throw new IllegalArgumentException("tenant key root must be a real directory");
        }
        requireNotGroupWritable(this.keyRoot, "tenant key root");
    }

    @Override
    public byte[] encrypt(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
        return seal(tenantId, plaintextDigest, plaintext).ciphertext();
    }

    @Override
    public byte[] decrypt(String tenantId, CasDigest plaintextDigest, byte[] ciphertext) {
        String current = currentKeyId(tenantId);
        return open(tenantId, plaintextDigest, new Envelope(current, ciphertext));
    }

    @Override
    public boolean hasKey(String tenantId) {
        try {
            String keyId = currentKeyId(tenantId);
            byte[] key = loadKey(tenantId, keyId);
            java.util.Arrays.fill(key, (byte) 0);
            return true;
        } catch (CasExceptions.CasAccessDeniedException unavailable) {
            // A missing/invalid/unsafe key is an authorization failure. Provider and mount I/O
            // deliberately propagates as an availability failure rather than being flattened to
            // the indistinguishable boolean "missing key" state.
            return false;
        }
    }

    @Override
    public boolean encryptsAtRest() {
        return true;
    }

    @Override
    public Envelope seal(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
        String keyId = currentKeyId(tenantId);
        byte[] key = loadKey(tenantId, keyId);
        try {
            return new TenantEncryption.AesGcm()
                    .registerKey(tenantId, keyId, key, true)
                    .seal(tenantId, plaintextDigest, plaintext);
        } finally {
            java.util.Arrays.fill(key, (byte) 0);
        }
    }

    @Override
    public byte[] open(String tenantId, CasDigest plaintextDigest, Envelope envelope) {
        String keyId = validateKeyId(envelope.keyId());
        byte[] key = loadKey(tenantId, keyId);
        try {
            return new TenantEncryption.AesGcm()
                    .registerKey(tenantId, keyId, key, true)
                    .open(tenantId, plaintextDigest, envelope);
        } finally {
            java.util.Arrays.fill(key, (byte) 0);
        }
    }

    public Path tenantKeyDirectory(String tenantId) {
        String tenant = CasText.required(tenantId, "tenantId");
        String namespace = CasDigest.ofUtf8("elmos-tenant-key-namespace/1\n" + tenant).hex();
        return keyRoot.resolve(namespace.substring(0, 2)).resolve(namespace).normalize();
    }

    private String currentKeyId(String tenantId) {
        Path directory = tenantKeyDirectory(tenantId);
        requireSecureDirectory(directory.getParent(), "tenant key namespace prefix");
        requireSecureDirectory(directory, "tenant key directory");
        Path current = confined(directory, directory.resolve("current"));
        requireRegularNonSymlink(current, "tenant current-key selector");
        requireNotGroupWritable(current, "tenant current-key selector");
        try {
            String value = Files.readString(current, StandardCharsets.UTF_8).trim();
            return validateKeyId(value);
        } catch (IOException error) {
            throw new UncheckedIOException("cannot read tenant current-key selector", error);
        }
    }

    private byte[] loadKey(String tenantId, String keyId) {
        Path directory = tenantKeyDirectory(tenantId);
        // open(old-envelope) does not consult current, so it must independently protect every
        // parent component. Checking only the final .key file would still follow a swapped tenant
        // directory symlink into attacker-controlled key material.
        requireSecureDirectory(directory.getParent(), "tenant key namespace prefix");
        requireSecureDirectory(directory, "tenant key directory");
        Path keyFile = confined(directory, directory.resolve(validateKeyId(keyId) + ".key"));
        requireRegularNonSymlink(keyFile, "tenant key file");
        requireOwnerOnly(keyFile);
        final String encoded;
        try {
            encoded = Files.readString(keyFile, StandardCharsets.US_ASCII).trim();
        } catch (IOException error) {
            // A provider/mount read failure is an availability event, not evidence that the
            // immutable ciphertext or the encoded key material is malformed.
            throw new UncheckedIOException("cannot read tenant key", error);
        }
        try {
            if (encoded.length() > 128) {
                throw new CasExceptions.CasAccessDeniedException(
                        "TENANT_KEY_INVALID", tenantId + "/" + keyId);
            }
            byte[] key = Base64.getDecoder().decode(encoded);
            if (key.length != 32) {
                java.util.Arrays.fill(key, (byte) 0);
                throw new CasExceptions.CasAccessDeniedException(
                        "TENANT_KEY_INVALID", tenantId + "/" + keyId);
            }
            return key;
        } catch (IllegalArgumentException error) {
            throw new CasExceptions.CasAccessDeniedException(
                    "TENANT_KEY_INVALID", tenantId + "/" + keyId);
        }
    }

    private static String validateKeyId(String keyId) {
        if (keyId == null || !KEY_ID.matcher(keyId).matches()) {
            throw new CasExceptions.CasAccessDeniedException("TENANT_KEY_ID_INVALID", "redacted");
        }
        return keyId;
    }

    private static Path confined(Path directory, Path candidate) {
        Path normalizedDirectory = directory.toAbsolutePath().normalize();
        Path normalized = candidate.toAbsolutePath().normalize();
        if (!normalized.startsWith(normalizedDirectory)) {
            throw new CasExceptions.CasAccessDeniedException("TENANT_KEY_PATH_ESCAPE", "redacted");
        }
        return normalized;
    }

    private static void requireRegularNonSymlink(Path path, String label) {
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path)) {
            throw new CasExceptions.CasAccessDeniedException(
                    "TENANT_KEY_FILE_UNAVAILABLE", label);
        }
    }

    private static void requireSecureDirectory(Path path, String label) {
        if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path)) {
            throw new CasExceptions.CasAccessDeniedException(
                    "TENANT_KEY_DIRECTORY_UNAVAILABLE", label);
        }
        requireNotGroupWritable(path, label);
    }

    private static void requireNotGroupWritable(Path path, String label) {
        try {
            Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(
                    path, LinkOption.NOFOLLOW_LINKS);
            if (permissions.stream().anyMatch(FORBIDDEN_CONTROL_PERMISSIONS::contains)) {
                throw new CasExceptions.CasAccessDeniedException(
                        "TENANT_KEY_CONTROL_PERMISSIONS_TOO_BROAD", label);
            }
        } catch (UnsupportedOperationException ignored) {
            throw new CasExceptions.CasAccessDeniedException(
                    "TENANT_KEY_PERMISSIONS_UNVERIFIABLE", "POSIX permissions unavailable");
        } catch (IOException error) {
            throw new UncheckedIOException("cannot inspect tenant key control permissions", error);
        }
    }

    private static void requireOwnerOnly(Path keyFile) {
        try {
            Set<PosixFilePermission> permissions = Files.getPosixFilePermissions(
                    keyFile, LinkOption.NOFOLLOW_LINKS);
            if (permissions.stream().anyMatch(FORBIDDEN_KEY_PERMISSIONS::contains)) {
                throw new CasExceptions.CasAccessDeniedException(
                        "TENANT_KEY_PERMISSIONS_TOO_BROAD", "key file must be owner-only");
            }
        } catch (UnsupportedOperationException ignored) {
            // Non-POSIX providers cannot prove the permission boundary. Fail closed instead of
            // silently accepting a world-readable key on such a filesystem.
            throw new CasExceptions.CasAccessDeniedException(
                    "TENANT_KEY_PERMISSIONS_UNVERIFIABLE", "POSIX permissions unavailable");
        } catch (IOException error) {
            throw new UncheckedIOException("cannot inspect tenant key permissions", error);
        }
    }
}
