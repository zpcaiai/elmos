package io.elmos.cas;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

/**
 * ELMOS-CAS-018. Per-tenant envelope encryption for objects at rest in a shared tier.
 *
 * <p>Each encryption uses a fresh 96-bit random GCM nonce stored as a prefix of the ciphertext.
 * Content addressing still provides deduplication: the encrypted store publishes exactly one
 * immutable winner at the plaintext digest path and verifies any concurrent winner before
 * returning. Reusing a digest prefix as a deterministic nonce would reduce GCM's uniqueness
 * boundary to 96 bits and is therefore deliberately avoided.
 */
public interface TenantEncryption {

    record Envelope(String keyId, byte[] ciphertext) {
        public Envelope {
            keyId = CasText.required(keyId, "keyId");
            ciphertext = Objects.requireNonNull(ciphertext, "ciphertext").clone();
        }

        @Override
        public byte[] ciphertext() {
            return ciphertext.clone();
        }
    }

    byte[] encrypt(String tenantId, CasDigest plaintextDigest, byte[] plaintext);

    byte[] decrypt(String tenantId, CasDigest plaintextDigest, byte[] ciphertext);

    boolean hasKey(String tenantId);

    /** True only when this implementation itself guarantees ciphertext at the application tier. */
    default boolean encryptsAtRest() {
        return false;
    }

    /** Versioned form used by durable encrypted tiers so a key rotation keeps old objects readable. */
    default Envelope seal(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
        return new Envelope("default", encrypt(tenantId, plaintextDigest, plaintext));
    }

    /** Opens a versioned envelope. Implementations without a keyring only accept {@code default}. */
    default byte[] open(String tenantId, CasDigest plaintextDigest, Envelope envelope) {
        if (!"default".equals(envelope.keyId())) {
            throw new CasExceptions.CasAccessDeniedException(
                    "TENANT_KEY_VERSION_MISSING", tenantId + "/" + envelope.keyId());
        }
        return decrypt(tenantId, plaintextDigest, envelope.ciphertext());
    }

    /** No-op implementation for deployments where the storage tier is already encrypted. */
    static TenantEncryption disabled() {
        return new TenantEncryption() {
            @Override
            public byte[] encrypt(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
                return plaintext.clone();
            }

            @Override
            public byte[] decrypt(String tenantId, CasDigest plaintextDigest, byte[] ciphertext) {
                return ciphertext.clone();
            }

            @Override
            public boolean hasKey(String tenantId) {
                return true;
            }

            @Override
            public Envelope seal(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
                return new Envelope("storage-tier-managed", plaintext);
            }

            @Override
            public byte[] open(String tenantId, CasDigest plaintextDigest, Envelope envelope) {
                if (!"storage-tier-managed".equals(envelope.keyId())) {
                    throw new CasExceptions.CasAccessDeniedException(
                            "TENANT_KEY_VERSION_MISSING", envelope.keyId());
                }
                return envelope.ciphertext();
            }
        };
    }

    final class AesGcm implements TenantEncryption {

        private static final int NONCE_BYTES = 12;
        private static final int TAG_BITS = 128;
        private static final int TAG_BYTES = TAG_BITS / Byte.SIZE;
        private static final Pattern KEY_ID = Pattern.compile("^[A-Za-z0-9._-]{1,64}$");

        private record KeyRef(String tenantId, String keyId) {
        }

        private final Map<KeyRef, byte[]> keys = new ConcurrentHashMap<>();
        private final Map<String, String> currentKeyIds = new ConcurrentHashMap<>();
        private final SecureRandom nonceSource = new SecureRandom();

        public AesGcm registerKey(String tenantId, byte[] key256) {
            return registerKey(tenantId, "default", key256, true);
        }

        public AesGcm registerKey(String tenantId, String keyId, byte[] key256, boolean current) {
            String tenant = CasText.required(tenantId, "tenantId");
            if (keyId == null || !KEY_ID.matcher(keyId).matches()) {
                throw new IllegalArgumentException("tenant key id is invalid");
            }
            Objects.requireNonNull(key256, "key256");
            if (key256.length != 32) {
                throw new IllegalArgumentException("tenant key must be 256 bits, was " + key256.length * 8);
            }
            KeyRef reference = new KeyRef(tenant, keyId);
            byte[] candidate = key256.clone();
            byte[] registered = keys.putIfAbsent(reference, candidate);
            if (registered != null) {
                boolean sameMaterial = MessageDigest.isEqual(registered, candidate);
                Arrays.fill(candidate, (byte) 0);
                if (!sameMaterial) {
                    throw new IllegalArgumentException(
                            "tenant key id is already bound to different key material: " + keyId);
                }
            }
            if (current) {
                currentKeyIds.put(tenant, keyId);
            }
            return this;
        }

        @Override
        public boolean hasKey(String tenantId) {
            String current = currentKeyIds.get(tenantId);
            return current != null && keys.containsKey(new KeyRef(tenantId, current));
        }

        @Override
        public boolean encryptsAtRest() {
            return true;
        }

        @Override
        public byte[] encrypt(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
            verifyPlaintextDigest(tenantId, plaintextDigest, plaintext);
            return encryptWithKey(tenantId, currentKeyId(tenantId), plaintextDigest, plaintext);
        }

        @Override
        public byte[] decrypt(String tenantId, CasDigest plaintextDigest, byte[] ciphertext) {
            return decryptWithKey(tenantId, currentKeyId(tenantId), plaintextDigest, ciphertext);
        }

        @Override
        public Envelope seal(String tenantId, CasDigest plaintextDigest, byte[] plaintext) {
            verifyPlaintextDigest(tenantId, plaintextDigest, plaintext);
            String keyId = currentKeyId(tenantId);
            return new Envelope(keyId, encryptWithKey(tenantId, keyId, plaintextDigest, plaintext));
        }

        @Override
        public byte[] open(String tenantId, CasDigest plaintextDigest, Envelope envelope) {
            return decryptWithKey(tenantId, envelope.keyId(), plaintextDigest, envelope.ciphertext());
        }

        private byte[] decryptWithKey(String tenantId, String keyId, CasDigest plaintextDigest,
                                      byte[] ciphertext) {
            Objects.requireNonNull(ciphertext, "ciphertext");
            if (ciphertext.length < NONCE_BYTES + TAG_BYTES) {
                throw authenticationFailure(tenantId, keyId, plaintextDigest);
            }
            byte[] nonce = Arrays.copyOf(ciphertext, NONCE_BYTES);
            byte[] payload = Arrays.copyOfRange(ciphertext, NONCE_BYTES, ciphertext.length);
            byte[] plaintext;
            try {
                plaintext = transform(Cipher.DECRYPT_MODE, tenantId, keyId,
                        plaintextDigest, nonce, payload);
            } finally {
                Arrays.fill(nonce, (byte) 0);
                Arrays.fill(payload, (byte) 0);
            }
            CasDigest actual = CasDigest.of(plaintext);
            if (!actual.equals(plaintextDigest)) {
                throw new CasExceptions.CasCorruptionException("tenant-encrypted tier", plaintextDigest, actual);
            }
            return plaintext;
        }

        private byte[] encryptWithKey(String tenantId, String keyId, CasDigest digest,
                                      byte[] plaintext) {
            byte[] nonce = new byte[NONCE_BYTES];
            nonceSource.nextBytes(nonce);
            try {
                byte[] payload = transform(Cipher.ENCRYPT_MODE, tenantId, keyId,
                        digest, nonce, plaintext);
                byte[] encoded = new byte[nonce.length + payload.length];
                System.arraycopy(nonce, 0, encoded, 0, nonce.length);
                System.arraycopy(payload, 0, encoded, nonce.length, payload.length);
                Arrays.fill(payload, (byte) 0);
                return encoded;
            } finally {
                Arrays.fill(nonce, (byte) 0);
            }
        }

        private String currentKeyId(String tenantId) {
            String tenant = CasText.required(tenantId, "tenantId");
            String keyId = currentKeyIds.get(tenant);
            if (keyId == null) {
                throw new CasExceptions.CasAccessDeniedException("TENANT_KEY_MISSING", tenant);
            }
            return keyId;
        }

        private static void verifyPlaintextDigest(String tenantId, CasDigest expected,
                                                  byte[] plaintext) {
            String tenant = CasText.required(tenantId, "tenantId");
            Objects.requireNonNull(expected, "plaintextDigest");
            Objects.requireNonNull(plaintext, "plaintext");
            CasDigest actual = CasDigest.of(plaintext);
            if (!actual.equals(expected)) {
                throw new CasExceptions.CasCorruptionException(
                        "tenant-encryption-input:" + tenant, expected, actual);
            }
        }

        private byte[] transform(int mode, String tenantId, String keyId,
                                 CasDigest digest, byte[] nonce, byte[] input) {
            byte[] key = keys.get(new KeyRef(tenantId, keyId));
            if (key == null) {
                throw new CasExceptions.CasAccessDeniedException(
                        "TENANT_KEY_VERSION_MISSING", tenantId + "/" + keyId);
            }
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                byte[] tenantKey = deriveTenantKey(key, tenantId);
                try {
                    cipher.init(mode, new SecretKeySpec(tenantKey, "AES"),
                            new GCMParameterSpec(TAG_BITS, nonce));
                } finally {
                    Arrays.fill(tenantKey, (byte) 0);
                }
                // Bind every identity field that selects the key or immutable object. Moving a
                // blob, relabelling a key version, or changing the declared digest must fail the
                // tag before any plaintext is returned.
                cipher.updateAAD(("elmos-cas-aes-gcm/2\n" + tenantId + "\n" + keyId + "\n"
                        + digest.compact()).getBytes(StandardCharsets.UTF_8));
                return cipher.doFinal(input);
            } catch (AEADBadTagException authenticationFailure) {
                throw authenticationFailure(tenantId, keyId, digest);
            } catch (GeneralSecurityException providerFailure) {
                // Provider/key-initialisation failures are availability events. Conflating them
                // with an AEAD tag failure would cause a healthy ciphertext to be quarantined.
                throw new CasExceptions.CasAccessDeniedException("TENANT_CRYPTO_UNAVAILABLE",
                        tenantId + "/" + keyId + "/" + digest.compact());
            }
        }

        private static CasExceptions.CasAccessDeniedException authenticationFailure(
                String tenantId, String keyId, CasDigest digest) {
            return new CasExceptions.CasAccessDeniedException(
                    "TENANT_CIPHERTEXT_AUTHENTICATION_FAILED",
                    tenantId + "/" + keyId + "/" + digest.compact());
        }

        private static byte[] deriveTenantKey(byte[] keyMaterial, String tenantId)
                throws GeneralSecurityException {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(keyMaterial, "HmacSHA256"));
            return mac.doFinal(("elmos-cas-tenant-dek/1\n" + tenantId)
                    .getBytes(StandardCharsets.UTF_8));
        }
    }
}
