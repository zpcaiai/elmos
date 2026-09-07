package io.elmos.cas;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.regex.Pattern;

/**
 * Production-shaped KMS envelope encryption without a provider-specific dependency.
 *
 * <p>The provider creates a fresh 256-bit data-encryption key (DEK) and returns both its
 * plaintext form and a KMS-wrapped ciphertext. The plaintext DEK exists only while one local
 * AES-GCM operation is running and is zeroed afterwards. The durable envelope contains only the
 * provider key reference, version, wrapped DEK, nonce and ciphertext. It never contains a
 * plaintext tenant or provider key.
 *
 * <p>No cloud adapter is enabled by this class. A deployment must explicitly supply a
 * {@link KeyManagementProvider}; unavailable, unknown and revoked provider states fail closed.
 */
public final class KmsTenantEncryption implements TenantEncryption {

    public static final String ENVELOPE_FORMAT = "elmos-kms-envelope/1";

    private static final byte[] MAGIC = "ELMOS-KMS-ENVELOPE/1\n"
            .getBytes(StandardCharsets.US_ASCII);
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int DATA_KEY_BYTES = 32;
    private static final int MAX_KEY_REFERENCE_BYTES = 2048;
    private static final int MAX_KEY_VERSION_BYTES = 256;
    private static final int MAX_WRAPPED_KEY_BYTES = 64 * 1024;
    private static final long MAX_ENVELOPE_OVERHEAD_BYTES = 128 * 1024L;
    private static final Pattern KEY_VERSION = Pattern.compile("^[A-Za-z0-9._:/@+-]{1,256}$");

    /** Provider state is checked on every seal and open; UNKNOWN never authorizes use. */
    public enum KeyState {
        ACTIVE,
        DECRYPT_ONLY,
        REVOKED,
        UNKNOWN
    }

    /** Stable provider-native key identity. Display names are not key identities. */
    public record KeyVersion(String keyReference, String version) {
        public KeyVersion {
            keyReference = boundedVisibleText(keyReference, "keyReference", MAX_KEY_REFERENCE_BYTES);
            version = boundedVisibleText(version, "version", MAX_KEY_VERSION_BYTES);
            if (!KEY_VERSION.matcher(version).matches()) {
                throw new IllegalArgumentException("KMS key version contains unsupported characters");
            }
        }
    }

    /**
     * Non-secret, exact KMS encryption context. Providers should bind every returned wrapped key
     * to this context using their native encryption-context/AAD mechanism.
     */
    public record EncryptionContext(String tenantId, CasDigest plaintextDigest,
                                    KeyVersion keyVersion) {
        public EncryptionContext {
            tenantId = CasText.required(tenantId, "tenantId");
            Objects.requireNonNull(plaintextDigest, "plaintextDigest");
            Objects.requireNonNull(keyVersion, "keyVersion");
        }

        public Map<String, String> attributes() {
            Map<String, String> attributes = new LinkedHashMap<>();
            attributes.put("format", ENVELOPE_FORMAT);
            attributes.put("tenant", tenantId);
            attributes.put("digest", plaintextDigest.compact());
            attributes.put("key_reference", keyVersion.keyReference());
            attributes.put("key_version", keyVersion.version());
            return Map.copyOf(attributes);
        }

        public byte[] canonicalBytes() {
            CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder(
                    "elmos-kms-encryption-context/1");
            encoder.map("context", attributes());
            return encoder.bytes();
        }
    }

    public enum ProviderFailure {
        UNAVAILABLE,
        KEY_NOT_FOUND,
        KEY_REVOKED,
        PERMISSION_DENIED,
        INVALID_RESPONSE
    }

    /** Checked provider failure so an adapter cannot accidentally turn an outage into a miss. */
    public static final class ProviderException extends Exception {
        private static final long serialVersionUID = 1L;

        private final ProviderFailure failure;

        public ProviderException(ProviderFailure failure, String message) {
            super(CasText.required(message, "message"));
            this.failure = Objects.requireNonNull(failure, "failure");
        }

        public ProviderException(ProviderFailure failure, String message, Throwable cause) {
            super(CasText.required(message, "message"), cause);
            this.failure = Objects.requireNonNull(failure, "failure");
        }

        public ProviderFailure failure() {
            return failure;
        }
    }

    /**
     * One generated data key. The plaintext is never exposed by an accessor and is wiped by
     * {@link #close()}; {@link #usePlaintextKey(Function)} is deliberately scoped to one call.
     */
    public static final class GeneratedDataKey implements AutoCloseable {
        private final KeyVersion keyVersion;
        private byte[] plaintextKey;
        private final byte[] wrappedKey;

        /**
         * Takes ownership of {@code plaintextKey}. The caller must not retain or reuse that array;
         * closing this object zeroes the exact supplied buffer, not merely a clone.
         */
        public GeneratedDataKey(KeyVersion keyVersion, byte[] plaintextKey, byte[] wrappedKey) {
            byte[] ownedPlaintext = requireDataKey(plaintextKey);
            KeyVersion validatedVersion;
            byte[] validatedWrappedKey;
            try {
                validatedVersion = Objects.requireNonNull(keyVersion, "keyVersion");
                validatedWrappedKey = requireWrappedKey(wrappedKey);
            } catch (RuntimeException invalidMetadata) {
                Arrays.fill(ownedPlaintext, (byte) 0);
                throw invalidMetadata;
            }
            this.keyVersion = validatedVersion;
            this.wrappedKey = validatedWrappedKey;
            this.plaintextKey = ownedPlaintext;
        }

        public KeyVersion keyVersion() {
            return keyVersion;
        }

        public byte[] wrappedKey() {
            return wrappedKey.clone();
        }

        private synchronized <T> T usePlaintextKey(Function<byte[], T> operation) {
            Objects.requireNonNull(operation, "operation");
            if (plaintextKey == null) {
                throw new IllegalStateException("plaintext data key has already been destroyed");
            }
            return operation.apply(plaintextKey);
        }

        @Override
        public synchronized void close() {
            if (plaintextKey != null) {
                Arrays.fill(plaintextKey, (byte) 0);
                plaintextKey = null;
            }
        }
    }

    /**
     * Adapter boundary for AWS KMS, Google Cloud KMS, Azure Key Vault, Vault Transit, or an
     * equivalent approved service. Implementations must not cache plaintext master keys here.
     */
    public interface KeyManagementProvider {
        KeyVersion currentVersion(String tenantId) throws ProviderException;

        KeyState state(String tenantId, KeyVersion keyVersion) throws ProviderException;

        GeneratedDataKey generateDataKey(String tenantId, KeyVersion keyVersion,
                                         EncryptionContext context) throws ProviderException;

        /**
         * Returns a newly owned plaintext data-key buffer. Ownership transfers to this adapter,
         * which zeroes the exact returned array after one decrypt operation; providers must not
         * retain, reuse, pool, or expose that buffer elsewhere.
         */
        byte[] decryptDataKey(String tenantId, KeyVersion keyVersion, byte[] wrappedKey,
                              EncryptionContext context) throws ProviderException;

        KeyVersion rotate(String tenantId) throws ProviderException;

        void revoke(String tenantId, KeyVersion keyVersion) throws ProviderException;
    }

    private record ParsedEnvelope(KeyVersion keyVersion, byte[] wrappedKey,
                                  byte[] nonce, byte[] ciphertext) {
        private ParsedEnvelope {
            Objects.requireNonNull(keyVersion, "keyVersion");
            wrappedKey = wrappedKey.clone();
            nonce = nonce.clone();
            ciphertext = ciphertext.clone();
        }
    }

    private final KeyManagementProvider provider;
    private final SecureRandom nonceSource;

    public KmsTenantEncryption(KeyManagementProvider provider) {
        this(provider, new SecureRandom());
    }

    KmsTenantEncryption(KeyManagementProvider provider, SecureRandom nonceSource) {
        this.provider = Objects.requireNonNull(provider, "provider");
        this.nonceSource = Objects.requireNonNull(nonceSource, "nonceSource");
    }

    @Override
    public boolean encryptsAtRest() {
        return true;
    }

    @Override
    public String atRestProtection() {
        return "TENANT_KMS_ENVELOPE_AES_256_GCM";
    }

    @Override
    public long maximumEnvelopeOverheadBytes() {
        return MAX_ENVELOPE_OVERHEAD_BYTES;
    }

    @Override
    public boolean hasKey(String tenantId) {
        try {
            requireActiveCurrentVersion(tenantId);
            return true;
        } catch (CasExceptions.CasAccessDeniedException denied) {
            if ("TENANT_KMS_KEY_NOT_FOUND".equals(denied.reason())) {
                return false;
            }
            throw denied;
        }
    }

    public KeyVersion currentVersion(String tenantId) {
        return requireActiveCurrentVersion(tenantId);
    }

    /** Explicit control-plane operation; constructing this adapter never rotates a key. */
    public KeyVersion rotate(String tenantId) {
        String tenant = CasText.required(tenantId, "tenantId");
        KeyVersion rotated = providerCall(tenant, null, () -> provider.rotate(tenant));
        KeyVersion current = requireActiveCurrentVersion(tenant);
        if (!current.equals(rotated)) {
            throw denied("TENANT_KMS_INCONSISTENT_ROTATION", tenant);
        }
        return rotated;
    }

    /** Explicit irreversible control-plane operation; callers must authorize it independently. */
    public void revoke(String tenantId, KeyVersion keyVersion) {
        String tenant = CasText.required(tenantId, "tenantId");
        Objects.requireNonNull(keyVersion, "keyVersion");
        providerRun(tenant, keyVersion, () -> provider.revoke(tenant, keyVersion));
        KeyState state = keyState(tenant, keyVersion);
        if (state != KeyState.REVOKED) {
            throw denied("TENANT_KMS_REVOKE_NOT_CONFIRMED", subject(tenant, keyVersion));
        }
    }

    @Override
    public byte[] encrypt(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
        return seal(tenantId, plaintextDigest, plaintext).ciphertext();
    }

    @Override
    public byte[] decrypt(String tenantId, CasDigest plaintextDigest, byte[] ciphertext) {
        ParsedEnvelope parsed = decode(ciphertext);
        return openParsed(CasText.required(tenantId, "tenantId"), plaintextDigest, parsed);
    }

    @Override
    public Envelope seal(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
        String tenant = CasText.required(tenantId, "tenantId");
        verifyPlaintextDigest(tenant, plaintextDigest, plaintext);
        KeyVersion keyVersion = requireActiveCurrentVersion(tenant);
        EncryptionContext context = new EncryptionContext(tenant, plaintextDigest, keyVersion);
        GeneratedDataKey generated = providerCall(tenant, keyVersion,
                () -> provider.generateDataKey(tenant, keyVersion, context));
        if (generated == null || !keyVersion.equals(generated.keyVersion())) {
            if (generated != null) {
                generated.close();
            }
            throw denied("TENANT_KMS_INVALID_DATA_KEY", subject(tenant, keyVersion));
        }
        try (generated) {
            byte[] nonce = new byte[NONCE_BYTES];
            byte[] wrapped = generated.wrappedKey();
            byte[] payload = null;
            try {
                nonceSource.nextBytes(nonce);
                payload = generated.usePlaintextKey(key -> transform(
                        Cipher.ENCRYPT_MODE, key, nonce, plaintext, context));
                byte[] encoded = encode(new ParsedEnvelope(keyVersion, wrapped, nonce, payload));
                return new Envelope(keyToken(keyVersion), encoded);
            } finally {
                // GeneratedDataKey closes the exact provider buffer. These non-plaintext envelope
                // components are also cleared so no avoidable copy survives the operation.
                Arrays.fill(wrapped, (byte) 0);
                Arrays.fill(nonce, (byte) 0);
                if (payload != null) {
                    Arrays.fill(payload, (byte) 0);
                }
            }
        }
    }

    @Override
    public byte[] open(String tenantId, CasDigest plaintextDigest, Envelope envelope) {
        Objects.requireNonNull(envelope, "envelope");
        ParsedEnvelope parsed = decode(envelope.ciphertext());
        if (!MessageDigest.isEqual(
                keyToken(parsed.keyVersion()).getBytes(StandardCharsets.US_ASCII),
                envelope.keyId().getBytes(StandardCharsets.US_ASCII))) {
            clear(parsed);
            throw denied("TENANT_KMS_ENVELOPE_KEY_MISMATCH", envelope.keyId());
        }
        return openParsed(CasText.required(tenantId, "tenantId"), plaintextDigest, parsed);
    }

    private byte[] openParsed(String tenantId, CasDigest plaintextDigest, ParsedEnvelope parsed) {
        Objects.requireNonNull(plaintextDigest, "plaintextDigest");
        KeyState state = keyState(tenantId, parsed.keyVersion());
        if (state == KeyState.REVOKED) {
            clear(parsed);
            throw denied("TENANT_KMS_KEY_REVOKED", subject(tenantId, parsed.keyVersion()));
        }
        if (state != KeyState.ACTIVE && state != KeyState.DECRYPT_ONLY) {
            clear(parsed);
            throw denied("TENANT_KMS_KEY_STATE_UNKNOWN", subject(tenantId, parsed.keyVersion()));
        }
        EncryptionContext context = new EncryptionContext(
                tenantId, plaintextDigest, parsed.keyVersion());
        byte[] dataKey = providerCall(tenantId, parsed.keyVersion(), () ->
                provider.decryptDataKey(tenantId, parsed.keyVersion(),
                        parsed.wrappedKey(), context));
        if (dataKey == null || dataKey.length != DATA_KEY_BYTES) {
            if (dataKey != null) {
                Arrays.fill(dataKey, (byte) 0);
            }
            clear(parsed);
            throw denied("TENANT_KMS_INVALID_DATA_KEY", subject(tenantId, parsed.keyVersion()));
        }
        byte[] plaintext;
        try {
            plaintext = transform(Cipher.DECRYPT_MODE, dataKey, parsed.nonce(),
                    parsed.ciphertext(), context);
        } finally {
            Arrays.fill(dataKey, (byte) 0);
            clear(parsed);
        }
        CasDigest actual = CasDigest.of(plaintext);
        if (!actual.equals(plaintextDigest)) {
            Arrays.fill(plaintext, (byte) 0);
            throw new CasExceptions.CasCorruptionException(
                    "tenant-kms-encryption:" + tenantId, plaintextDigest, actual);
        }
        return plaintext;
    }

    private KeyVersion requireActiveCurrentVersion(String tenantId) {
        String tenant = CasText.required(tenantId, "tenantId");
        KeyVersion current = providerCall(tenant, null, () -> provider.currentVersion(tenant));
        if (current == null) {
            throw denied("TENANT_KMS_INVALID_RESPONSE", tenant);
        }
        KeyState state = keyState(tenant, current);
        if (state == KeyState.REVOKED) {
            throw denied("TENANT_KMS_KEY_REVOKED", subject(tenant, current));
        }
        if (state != KeyState.ACTIVE) {
            throw denied("TENANT_KMS_CURRENT_KEY_NOT_ACTIVE", subject(tenant, current));
        }
        return current;
    }

    private KeyState keyState(String tenantId, KeyVersion keyVersion) {
        KeyState state = providerCall(tenantId, keyVersion,
                () -> provider.state(tenantId, keyVersion));
        return state == null ? KeyState.UNKNOWN : state;
    }

    private static byte[] transform(int mode, byte[] key, byte[] nonce, byte[] input,
                                    EncryptionContext context) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(mode, new SecretKeySpec(key, "AES"), new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(context.canonicalBytes());
            return cipher.doFinal(input);
        } catch (AEADBadTagException invalidTag) {
            throw denied("TENANT_CIPHERTEXT_AUTHENTICATION_FAILED",
                    subject(context.tenantId(), context.keyVersion()) + "/"
                            + context.plaintextDigest().compact());
        } catch (GeneralSecurityException unavailable) {
            throw denied("TENANT_CRYPTO_UNAVAILABLE",
                    subject(context.tenantId(), context.keyVersion()));
        }
    }

    private static byte[] encode(ParsedEnvelope envelope) {
        byte[] reference = envelope.keyVersion().keyReference().getBytes(StandardCharsets.UTF_8);
        byte[] version = envelope.keyVersion().version().getBytes(StandardCharsets.UTF_8);
        byte[] wrapped = envelope.wrappedKey();
        byte[] nonce = envelope.nonce();
        byte[] ciphertext = envelope.ciphertext();
        long size = (long) MAGIC.length + Integer.BYTES * 5L + reference.length + version.length
                + wrapped.length + nonce.length + ciphertext.length;
        if (size > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("KMS envelope is too large");
        }
        ByteBuffer encoded = ByteBuffer.allocate((int) size);
        encoded.put(MAGIC);
        encoded.putInt(reference.length);
        encoded.putInt(version.length);
        encoded.putInt(wrapped.length);
        encoded.putInt(nonce.length);
        encoded.putInt(ciphertext.length);
        encoded.put(reference);
        encoded.put(version);
        encoded.put(wrapped);
        encoded.put(nonce);
        encoded.put(ciphertext);
        Arrays.fill(reference, (byte) 0);
        Arrays.fill(version, (byte) 0);
        Arrays.fill(wrapped, (byte) 0);
        Arrays.fill(nonce, (byte) 0);
        Arrays.fill(ciphertext, (byte) 0);
        return encoded.array();
    }

    private static ParsedEnvelope decode(byte[] encoded) {
        Objects.requireNonNull(encoded, "ciphertext");
        if (encoded.length < MAGIC.length + Integer.BYTES * 5 + NONCE_BYTES + 17) {
            throw denied("TENANT_KMS_ENVELOPE_MALFORMED", "truncated");
        }
        ByteBuffer input = ByteBuffer.wrap(encoded);
        byte[] magic = new byte[MAGIC.length];
        input.get(magic);
        if (!MessageDigest.isEqual(MAGIC, magic)) {
            throw denied("TENANT_KMS_ENVELOPE_MALFORMED", "magic");
        }
        int referenceLength = boundedLength(input.getInt(), MAX_KEY_REFERENCE_BYTES, "key reference");
        int versionLength = boundedLength(input.getInt(), MAX_KEY_VERSION_BYTES, "key version");
        int wrappedLength = boundedLength(input.getInt(), MAX_WRAPPED_KEY_BYTES, "wrapped key");
        int nonceLength = boundedLength(input.getInt(), NONCE_BYTES, "nonce");
        int ciphertextLength = boundedLength(input.getInt(), Integer.MAX_VALUE, "ciphertext");
        if (nonceLength != NONCE_BYTES || ciphertextLength < 17) {
            throw denied("TENANT_KMS_ENVELOPE_MALFORMED", "nonce/ciphertext length");
        }
        long remaining = (long) referenceLength + versionLength + wrappedLength
                + nonceLength + ciphertextLength;
        if (remaining != input.remaining()) {
            throw denied("TENANT_KMS_ENVELOPE_MALFORMED", "length mismatch");
        }
        byte[] reference = take(input, referenceLength);
        byte[] version = take(input, versionLength);
        byte[] wrapped = take(input, wrappedLength);
        byte[] nonce = take(input, nonceLength);
        byte[] ciphertext = take(input, ciphertextLength);
        try {
            KeyVersion keyVersion = new KeyVersion(
                    new String(reference, StandardCharsets.UTF_8),
                    new String(version, StandardCharsets.UTF_8));
            return new ParsedEnvelope(keyVersion, wrapped, nonce, ciphertext);
        } catch (IllegalArgumentException malformed) {
            throw denied("TENANT_KMS_ENVELOPE_MALFORMED", "key identity");
        } finally {
            Arrays.fill(reference, (byte) 0);
            Arrays.fill(version, (byte) 0);
            Arrays.fill(wrapped, (byte) 0);
            Arrays.fill(nonce, (byte) 0);
            Arrays.fill(ciphertext, (byte) 0);
        }
    }

    private static byte[] take(ByteBuffer input, int size) {
        byte[] value = new byte[size];
        input.get(value);
        return value;
    }

    private static int boundedLength(int length, int maximum, String name) {
        if (length < 1 || length > maximum) {
            throw denied("TENANT_KMS_ENVELOPE_MALFORMED", name + " length");
        }
        return length;
    }

    private static void verifyPlaintextDigest(String tenantId, CasDigest expected,
                                              byte[] plaintext) {
        Objects.requireNonNull(expected, "plaintextDigest");
        Objects.requireNonNull(plaintext, "plaintext");
        CasDigest actual = CasDigest.of(plaintext);
        if (!actual.equals(expected)) {
            throw new CasExceptions.CasCorruptionException(
                    "tenant-kms-encryption-input:" + tenantId, expected, actual);
        }
    }

    private static byte[] requireDataKey(byte[] plaintextKey) {
        Objects.requireNonNull(plaintextKey, "plaintextKey");
        if (plaintextKey.length != DATA_KEY_BYTES) {
            Arrays.fill(plaintextKey, (byte) 0);
            throw new IllegalArgumentException("KMS plaintext data key must be 256 bits");
        }
        return plaintextKey;
    }

    private static byte[] requireWrappedKey(byte[] wrappedKey) {
        Objects.requireNonNull(wrappedKey, "wrappedKey");
        if (wrappedKey.length < 1 || wrappedKey.length > MAX_WRAPPED_KEY_BYTES) {
            throw new IllegalArgumentException("KMS wrapped data key length is invalid");
        }
        return wrappedKey.clone();
    }

    private static String boundedVisibleText(String value, String name, int maximumBytes) {
        String required = CasText.required(value, name);
        byte[] bytes = required.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > maximumBytes) {
            throw new IllegalArgumentException(name + " exceeds " + maximumBytes + " UTF-8 bytes");
        }
        for (int index = 0; index < required.length(); index++) {
            if (Character.isISOControl(required.charAt(index))) {
                throw new IllegalArgumentException(name + " contains control characters");
            }
        }
        return required;
    }

    private static String keyToken(KeyVersion keyVersion) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update((ENVELOPE_FORMAT + "\n" + keyVersion.keyReference() + "\n"
                    + keyVersion.version()).getBytes(StandardCharsets.UTF_8));
            return "kms1." + Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(digest.digest());
        } catch (GeneralSecurityException impossible) {
            throw new IllegalStateException("SHA-256 unavailable", impossible);
        }
    }

    private static void clear(ParsedEnvelope envelope) {
        Arrays.fill(envelope.wrappedKey(), (byte) 0);
        Arrays.fill(envelope.nonce(), (byte) 0);
        Arrays.fill(envelope.ciphertext(), (byte) 0);
    }

    private static String subject(String tenantId, KeyVersion keyVersion) {
        return tenantId + "/" + keyVersion.keyReference() + "@" + keyVersion.version();
    }

    private static CasExceptions.CasAccessDeniedException denied(String reason, String detail) {
        return new CasExceptions.CasAccessDeniedException(reason, detail);
    }

    @FunctionalInterface
    private interface ProviderCall<T> {
        T call() throws ProviderException;
    }

    @FunctionalInterface
    private interface ProviderRun {
        void run() throws ProviderException;
    }

    private static <T> T providerCall(String tenantId, KeyVersion keyVersion,
                                      ProviderCall<T> call) {
        try {
            return call.call();
        } catch (ProviderException failure) {
            throw mapProviderFailure(tenantId, keyVersion, failure);
        } catch (RuntimeException unavailable) {
            throw denied("TENANT_KMS_UNAVAILABLE",
                    keyVersion == null ? tenantId : subject(tenantId, keyVersion));
        }
    }

    private static void providerRun(String tenantId, KeyVersion keyVersion, ProviderRun call) {
        providerCall(tenantId, keyVersion, () -> {
            call.run();
            return null;
        });
    }

    private static CasExceptions.CasAccessDeniedException mapProviderFailure(
            String tenantId, KeyVersion keyVersion, ProviderException failure) {
        String detail = keyVersion == null ? tenantId : subject(tenantId, keyVersion);
        String reason = switch (failure.failure()) {
            case UNAVAILABLE -> "TENANT_KMS_UNAVAILABLE";
            case KEY_NOT_FOUND -> "TENANT_KMS_KEY_NOT_FOUND";
            case KEY_REVOKED -> "TENANT_KMS_KEY_REVOKED";
            case PERMISSION_DENIED -> "TENANT_KMS_PERMISSION_DENIED";
            case INVALID_RESPONSE -> "TENANT_KMS_INVALID_RESPONSE";
        };
        return denied(reason, detail);
    }
}
