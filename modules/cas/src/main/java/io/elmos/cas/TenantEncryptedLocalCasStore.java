package io.elmos.cas;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * Single-host tenant-namespaced AES-GCM CAS tier.
 *
 * <p>The public identity remains the plaintext {@link CasDigest}; only ciphertext reaches disk.
 * A tenant namespace is derived from the authenticated tenant id, and the tenant id is also GCM
 * additional authenticated data. Copying an encrypted file into another namespace therefore
 * fails authentication rather than producing plausible bytes.
 */
public final class TenantEncryptedLocalCasStore implements TenantCasStore {

    private static final byte[] MAGIC = "ELMOS-CAS-ENC/2\n".getBytes(StandardCharsets.US_ASCII);
    private static final Pattern FILE_NAME = Pattern.compile("^([0-9a-f]{64})\\.(\\d+)\\.enc$");

    private final String name;
    private final Path root;
    private final TenantEncryption encryption;
    private final long maximumStreamBytes;
    private final long maximumLegacyBytes;

    public TenantEncryptedLocalCasStore(String name, Path root, TenantEncryption encryption) {
        this(name, root, encryption, 1024L * 1024 * 1024, 64L * 1024 * 1024);
    }

    /** Legacy v2 reads need a bounded whole-envelope JCE operation; v3 is frame-bounded. */
    public TenantEncryptedLocalCasStore(String name, Path root, TenantEncryption encryption,
                                        long maximumStreamBytes, long maximumLegacyBytes) {
        this.name = CasText.required(name, "name");
        this.root = Objects.requireNonNull(root, "root").toAbsolutePath().normalize();
        this.encryption = Objects.requireNonNull(encryption, "encryption");
        if (maximumStreamBytes < 1 || maximumStreamBytes > (1L << 40)
                || maximumLegacyBytes < 0 || maximumLegacyBytes > Integer.MAX_VALUE - 1024 * 1024) {
            throw new IllegalArgumentException("encrypted CAS input bounds are invalid");
        }
        this.maximumStreamBytes = maximumStreamBytes;
        this.maximumLegacyBytes = maximumLegacyBytes;
        if (!encryption.encryptsAtRest()) {
            throw new IllegalArgumentException(
                    "tenant encrypted store requires application-layer encryption");
        }
        try {
            createAndRequireRealDirectory(this.root, "encrypted CAS root");
            createAndRequireRealDirectory(this.root.resolve("tenants"), "encrypted CAS tenants root");
            createAndRequireRealDirectory(this.root.resolve("staging"), "encrypted CAS staging root");
            createAndRequireRealDirectory(this.root.resolve("quarantine"), "encrypted CAS quarantine root");
        } catch (IOException error) {
            throw new UncheckedIOException("cannot initialise encrypted CAS root", error);
        }
    }

    @Override
    public CasStore forTenant(String tenantId) {
        String tenant = CasText.required(tenantId, "tenantId");
        if (!encryption.hasKey(tenant)) {
            throw new CasExceptions.CasAccessDeniedException("TENANT_KEY_MISSING", tenant);
        }
        return new ScopedStore(tenant);
    }

    @Override
    public String atRestProtection() {
        return encryption.atRestProtection();
    }

    @Override
    public String physicalNamespace() {
        return "TENANT_NAMESPACED_CIPHERTEXT";
    }

    @Override
    public DeletionScope deletionScope() {
        return DeletionScope.TENANT_ISOLATED;
    }

    public Path root() {
        return root;
    }

    private final class ScopedStore implements CasStore {
        private final String tenantId;
        private final String namespace;
        private final Path blobs;
        private final Path quarantine;

        private ScopedStore(String tenantId) {
            this.tenantId = tenantId;
            this.namespace = CasDigest.ofUtf8("elmos-tenant-cas-namespace/1\n" + tenantId).hex();
            this.blobs = root.resolve("tenants").resolve(namespace.substring(0, 2))
                    .resolve(namespace).resolve("blobs");
            this.quarantine = root.resolve("quarantine").resolve(namespace);
            try {
                Files.createDirectories(blobs);
                Files.createDirectories(quarantine);
            } catch (IOException error) {
                throw new UncheckedIOException("cannot initialise encrypted tenant CAS namespace", error);
            }
        }

        @Override
        public String name() {
            return name + ":tenant:" + namespace.substring(0, 12);
        }

        private Path pathFor(CasDigest digest) {
            return blobs.resolve(digest.algorithm()).resolve(digest.hex().substring(0, 2))
                    .resolve(digest.hex().substring(2, 4))
                    .resolve(digest.hex() + "." + digest.sizeBytes() + ".enc");
        }

        @Override
        public boolean contains(CasDigest digest) {
            Path path = pathFor(digest);
            return Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                    && !Files.isSymbolicLink(path);
        }

        @Override
        public void put(CasDigest expected, byte[] content) {
            putDurable(expected, new java.io.ByteArrayInputStream(content));
        }

        @Override
        public void putDurable(CasDigest expected, java.io.InputStream content) {
            requireStreamSize(expected);
            Path target = pathFor(expected);
            try (CasContent verified = CasContent.capture(expected, content)) {
                if (contains(expected)) {
                    verifyStored(expected);
                    return;
                }
                Files.createDirectories(target.getParent());
                Path temporary = Files.createTempFile(root.resolve("staging"), namespace + "-", ".part");
                try {
                    try (var input = verified.openStream(); var output = Files.newOutputStream(temporary)) {
                        FramedTenantCipher.write(encryption, tenantId, expected, input, output);
                    }
                    try (var channel = java.nio.channels.FileChannel.open(temporary,
                            java.nio.file.StandardOpenOption.WRITE)) { channel.force(true); }
                    moveIntoPlace(temporary, target);
                } finally {
                    Files.deleteIfExists(temporary);
                }
            } catch (IOException error) {
                throw new UncheckedIOException("cannot store encrypted " + expected.compact(), error);
            }
            // A concurrent publisher may have won the immutable name. Never report success until
            // the bytes that actually won that name authenticate and hash to the requested digest.
            verifyStored(expected);
        }

        @Override
        public byte[] get(CasDigest digest) {
            if (digest.sizeBytes() > Integer.MAX_VALUE - 8) {
                throw new IllegalArgumentException("large encrypted object requires openVerified");
            }
            try (var input = openVerified(digest)) { return input.readAllBytes(); }
            catch (IOException error) { throw new UncheckedIOException(error); }
        }

        @Override
        public java.io.InputStream openVerified(CasDigest digest) {
            requireStreamSize(digest);
            Path path = pathFor(digest);
            if (!contains(digest)) throw new CasExceptions.CasNotFoundException(digest);
            try (var input = Files.newInputStream(path)) {
                byte[] magic = input.readNBytes(MAGIC.length);
                if (Arrays.equals(magic, MAGIC)) {
                    if (digest.sizeBytes() > maximumLegacyBytes) {
                        throw new IllegalArgumentException("CAS_LEGACY_V2_REQUIRES_BOUNDED_OFFLINE_MIGRATION");
                    }
                    byte[] plaintext = readLegacy(digest);
                    try {
                        return CasContent.capture(digest, new java.io.ByteArrayInputStream(plaintext)).ownedStream();
                    } finally { Arrays.fill(plaintext, (byte) 0); }
                }
                if (!Arrays.equals(magic, FramedTenantCipher.MAGIC)
                        || Files.size(path) > FramedTenantCipher.maximumPhysicalBytes(encryption, digest.sizeBytes())) {
                    throw new CasExceptions.CasCorruptionException(name(), digest, CasDigest.ofUtf8("invalid envelope size or version"));
                }
                try (var decrypted = FramedTenantCipher.decrypt(encryption, tenantId, digest, input)) {
                    // No caller observes even the first plaintext byte before ALL tags and SHA pass.
                    return CasContent.capture(digest, decrypted).ownedStream();
                }
            } catch (CasExceptions.CasCorruptionException corruption) {
                if (contains(digest)) quarantine(digest, path, "stream-authentication-failed");
                throw corruption;
            } catch (CasExceptions.CasAccessDeniedException denied) {
                if (Set.of("TENANT_CIPHERTEXT_AUTHENTICATION_FAILED", "TENANT_KMS_ENVELOPE_MALFORMED",
                        "TENANT_KMS_ENVELOPE_KEY_MISMATCH").contains(denied.reason())) {
                    if (contains(digest)) quarantine(digest, path, "stream-key-authentication-failed");
                    throw new CasExceptions.CasCorruptionException(name(), digest, CasDigest.ofUtf8("invalid encrypted key"));
                }
                throw denied;
            } catch (java.io.EOFException truncated) {
                if (contains(digest)) quarantine(digest, path, "stream-truncated");
                throw new CasExceptions.CasCorruptionException(name(), digest, CasDigest.ofUtf8("truncated encrypted stream"));
            } catch (IOException error) { throw new UncheckedIOException("cannot read encrypted stream", error); }
        }

        private void requireStreamSize(CasDigest digest) {
            if (digest.sizeBytes() > maximumStreamBytes) {
                throw new IllegalArgumentException("encrypted CAS object exceeds streaming byte budget");
            }
        }

        private byte[] readLegacy(CasDigest digest) {
            Path path = pathFor(digest);
            if (!contains(digest)) {
                throw new CasExceptions.CasNotFoundException(digest);
            }
            byte[] encoded;
            try {
                long physicalSize = Files.size(path);
                long maximumPhysicalSize;
                long maximumEnvelopeOverhead = encryption.maximumEnvelopeOverheadBytes();
                try {
                    maximumPhysicalSize = Math.addExact(
                            digest.sizeBytes(), maximumEnvelopeOverhead);
                } catch (ArithmeticException invalidBound) {
                    throw new IllegalStateException("encrypted envelope size bound overflow", invalidBound);
                }
                if (maximumEnvelopeOverhead < 64L
                        || physicalSize < MAGIC.length + 4L
                        || physicalSize > maximumPhysicalSize) {
                    quarantine(digest, path, "invalid-size");
                    throw new CasExceptions.CasCorruptionException(name(), digest,
                            CasDigest.ofUtf8("invalid encrypted envelope size"));
                }
                encoded = Files.readAllBytes(path);
            } catch (IOException error) {
                throw new UncheckedIOException("cannot read encrypted " + digest.compact(), error);
            }
            try {
                TenantEncryption.Envelope envelope;
                try {
                    envelope = decode(encoded);
                } catch (IllegalArgumentException malformedEnvelope) {
                    quarantine(digest, path, "malformed-envelope");
                    CasExceptions.CasCorruptionException corruption =
                            new CasExceptions.CasCorruptionException(name(), digest,
                                    CasDigest.ofUtf8("malformed encrypted envelope"));
                    corruption.initCause(malformedEnvelope);
                    throw corruption;
                }
                byte[] plaintext = encryption.open(tenantId, digest, envelope);
                CasDigest actual = CasDigest.of(plaintext);
                if (!actual.equals(digest)) {
                    Arrays.fill(plaintext, (byte) 0);
                    quarantine(digest, path, "plaintext-digest-mismatch");
                    throw new CasExceptions.CasCorruptionException(name(), digest, actual);
                }
                return plaintext;
            } catch (CasExceptions.CasAccessDeniedException keyFailure) {
                boolean ciphertextIntegrityFailure = Set.of(
                                "TENANT_CIPHERTEXT_AUTHENTICATION_FAILED",
                                "TENANT_KMS_ENVELOPE_MALFORMED",
                                "TENANT_KMS_ENVELOPE_KEY_MISMATCH")
                        .contains(keyFailure.reason());
                if (!ciphertextIntegrityFailure) {
                    // Missing/revoked versions, unsafe permissions, or key-provider I/O are
                    // authorization/availability events. They say nothing about the immutable
                    // ciphertext and must never move it out of the live namespace.
                    throw keyFailure;
                }
                quarantine(digest, path, "authentication-failed");
                throw new CasExceptions.CasCorruptionException(name(), digest,
                        CasDigest.ofUtf8("encrypted envelope authentication failed"));
            } catch (CasExceptions.CasCorruptionException corruption) {
                if (contains(digest)) {
                    quarantine(digest, path, "authentication-failed");
                }
                throw corruption;
            } finally {
                Arrays.fill(encoded, (byte) 0);
            }
        }

        @Override
        public byte[] readRange(CasDigest digest, long offset, int length) {
            if (offset < 0 || length < 0) {
                throw new IllegalArgumentException("range offset and length must not be negative");
            }
            byte[] plaintext = get(digest);
            if (offset > plaintext.length) {
                throw new IllegalArgumentException("range offset outside object: " + offset);
            }
            int from = (int) offset;
            long requestedEnd = offset + (long) length;
            int to = (int) Math.min((long) plaintext.length, requestedEnd);
            return Arrays.copyOfRange(plaintext, from, to);
        }

        @Override
        public boolean delete(CasDigest digest) {
            try {
                return Files.deleteIfExists(pathFor(digest));
            } catch (IOException error) {
                throw new UncheckedIOException("cannot delete encrypted " + digest.compact(), error);
            }
        }

        @Override
        public Set<CasDigest> inventory() {
            Set<CasDigest> result = new LinkedHashSet<>();
            if (!Files.exists(blobs)) {
                return result;
            }
            try (Stream<Path> walk = Files.walk(blobs)) {
                walk.filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                        .sorted(Comparator.comparing(Path::toString))
                        .forEach(path -> parseFileName(path.getFileName().toString()).ifPresent(result::add));
            } catch (IOException error) {
                throw new UncheckedIOException("cannot inventory encrypted tenant CAS", error);
            }
            return result;
        }

        @Override
        public long totalBytes() {
            return inventory().stream().mapToLong(CasDigest::sizeBytes).sum();
        }

        private void quarantine(CasDigest digest, Path path, String reason) {
            try {
                Files.createDirectories(quarantine);
                Path destination = quarantine.resolve(digest.hex() + "." + digest.sizeBytes()
                        + "." + reason + "." + java.util.UUID.randomUUID() + ".poisoned");
                // Quarantine evidence is append-only. A second incident must never overwrite the
                // first poisoned payload merely because it has the same declared digest.
                Files.move(path, destination);
            } catch (IOException error) {
                throw new UncheckedIOException("cannot quarantine encrypted object", error);
            }
        }

        private void verifyStored(CasDigest digest) {
            try (var verified = openVerified(digest)) { /* Authentication completed before return. */ }
            catch (IOException error) { throw new UncheckedIOException(error); }
        }
    }

    private static byte[] encode(TenantEncryption.Envelope envelope) {
        byte[] keyId = envelope.keyId().getBytes(StandardCharsets.US_ASCII);
        if (keyId.length < 1 || keyId.length > 64) {
            throw new IllegalArgumentException("envelope key id length is invalid");
        }
        byte[] ciphertext = envelope.ciphertext();
        byte[] encoded = new byte[MAGIC.length + 1 + keyId.length + ciphertext.length];
        System.arraycopy(MAGIC, 0, encoded, 0, MAGIC.length);
        encoded[MAGIC.length] = (byte) keyId.length;
        System.arraycopy(keyId, 0, encoded, MAGIC.length + 1, keyId.length);
        System.arraycopy(ciphertext, 0, encoded, MAGIC.length + 1 + keyId.length, ciphertext.length);
        Arrays.fill(ciphertext, (byte) 0);
        return encoded;
    }

    private static TenantEncryption.Envelope decode(byte[] encoded) {
        if (encoded.length < MAGIC.length + 2) {
            throw new IllegalArgumentException("encrypted envelope is truncated");
        }
        for (int index = 0; index < MAGIC.length; index++) {
            if (encoded[index] != MAGIC[index]) {
                throw new IllegalArgumentException("encrypted envelope magic is invalid");
            }
        }
        int keyLength = Byte.toUnsignedInt(encoded[MAGIC.length]);
        int ciphertextOffset = MAGIC.length + 1 + keyLength;
        if (keyLength < 1 || keyLength > 64 || ciphertextOffset >= encoded.length) {
            throw new IllegalArgumentException("encrypted envelope key id is invalid");
        }
        String keyId = new String(encoded, MAGIC.length + 1, keyLength, StandardCharsets.US_ASCII);
        return new TenantEncryption.Envelope(keyId,
                Arrays.copyOfRange(encoded, ciphertextOffset, encoded.length));
    }

    private static java.util.Optional<CasDigest> parseFileName(String name) {
        Matcher matcher = FILE_NAME.matcher(name);
        if (!matcher.matches()) {
            return java.util.Optional.empty();
        }
        try {
            return java.util.Optional.of(new CasDigest(CasDigest.ALGORITHM,
                    matcher.group(1), Long.parseLong(matcher.group(2))));
        } catch (IllegalArgumentException invalid) {
            return java.util.Optional.empty();
        }
    }

    private static void createAndRequireRealDirectory(Path path, String label) throws IOException {
        Files.createDirectories(path);
        if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(path)) {
            throw new IllegalArgumentException(label + " must be a real directory, not a symlink");
        }
    }

    private static void moveIntoPlace(Path temporary, Path target) throws IOException {
        try {
            // No REPLACE_EXISTING: an immutable digest name is write-once. If another publisher
            // wins, put() authenticates and hashes that winner before returning.
            Files.move(temporary, target);
        } catch (java.nio.file.FileAlreadyExistsException concurrentWinner) {
            // Verified by the caller after this method returns.
        }
    }
}
