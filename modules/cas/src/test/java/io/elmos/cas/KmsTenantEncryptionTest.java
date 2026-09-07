package io.elmos.cas;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KmsTenantEncryptionTest {

    @TempDir Path temporary;

    @Test void durableEnvelopeContainsNoPlaintextKeyAndBindsTheExactContext() {
        FakeProvider provider = new FakeProvider().provision("tenant-a");
        KmsTenantEncryption encryption = new KmsTenantEncryption(provider);
        byte[] plaintext = "private repository source".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);

        TenantEncryption.Envelope envelope = encryption.seal("tenant-a", digest, plaintext);

        assertTrue(envelope.keyId().startsWith("kms1."));
        assertTrue(envelope.keyId().length() <= 64);
        assertFalse(contains(envelope.ciphertext(), plaintext));
        assertFalse(contains(envelope.ciphertext(), provider.masterKey(
                encryption.currentVersion("tenant-a"))));
        assertTrue(provider.lastPlaintextDataKeyWasZeroed());
        assertArrayEquals(plaintext, encryption.open("tenant-a", digest, envelope));
        assertTrue(provider.lastDecryptedDataKeyWasZeroed());

        CasExceptions.CasAccessDeniedException wrongDigest = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> encryption.open("tenant-a", CasDigest.ofUtf8("other"), envelope));
        assertEquals("TENANT_KMS_PERMISSION_DENIED", wrongDigest.reason());

        CasExceptions.CasAccessDeniedException movedTenant = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> encryption.open("tenant-b", digest, envelope));
        assertEquals("TENANT_KMS_PERMISSION_DENIED", movedTenant.reason());

        TenantEncryption.Envelope relabelled = new TenantEncryption.Envelope(
                "kms1." + "A".repeat(43), envelope.ciphertext());
        CasExceptions.CasAccessDeniedException wrongReference = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> encryption.open("tenant-a", digest, relabelled));
        assertEquals("TENANT_KMS_ENVELOPE_KEY_MISMATCH", wrongReference.reason());
    }

    @Test void rotationKeepsDecryptOnlyVersionsReadableUntilExplicitRevocation() {
        FakeProvider provider = new FakeProvider().provision("tenant-a");
        KmsTenantEncryption encryption = new KmsTenantEncryption(provider);
        byte[] oldPlaintext = "old version".getBytes(StandardCharsets.UTF_8);
        CasDigest oldDigest = CasDigest.of(oldPlaintext);
        TenantEncryption.Envelope oldEnvelope = encryption.seal(
                "tenant-a", oldDigest, oldPlaintext);
        KmsTenantEncryption.KeyVersion oldVersion = encryption.currentVersion("tenant-a");

        KmsTenantEncryption.KeyVersion rotated = encryption.rotate("tenant-a");
        byte[] newPlaintext = "new version".getBytes(StandardCharsets.UTF_8);
        CasDigest newDigest = CasDigest.of(newPlaintext);
        TenantEncryption.Envelope newEnvelope = encryption.seal(
                "tenant-a", newDigest, newPlaintext);

        assertNotEquals(oldVersion, rotated);
        assertArrayEquals(oldPlaintext,
                encryption.open("tenant-a", oldDigest, oldEnvelope));
        assertArrayEquals(newPlaintext,
                encryption.open("tenant-a", newDigest, newEnvelope));

        encryption.revoke("tenant-a", oldVersion);
        CasExceptions.CasAccessDeniedException revoked = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> encryption.open("tenant-a", oldDigest, oldEnvelope));
        assertEquals("TENANT_KMS_KEY_REVOKED", revoked.reason());
        assertArrayEquals(newPlaintext,
                encryption.open("tenant-a", newDigest, newEnvelope));
    }

    @Test void providerOutageAndUnknownCurrentVersionFailClosed() {
        FakeProvider provider = new FakeProvider().provision("tenant-a");
        KmsTenantEncryption encryption = new KmsTenantEncryption(provider);
        byte[] plaintext = "durable ciphertext".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        TenantEncryption.Envelope envelope = encryption.seal("tenant-a", digest, plaintext);

        provider.unavailable = true;
        CasExceptions.CasAccessDeniedException unavailable = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> encryption.open("tenant-a", digest, envelope));
        assertEquals("TENANT_KMS_UNAVAILABLE", unavailable.reason());
        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> encryption.hasKey("tenant-a"));

        provider.unavailable = false;
        assertFalse(encryption.hasKey("missing-tenant"));
    }

    @Test void providerOutageDoesNotQuarantineValidDurableCiphertext() throws Exception {
        FakeProvider provider = new FakeProvider().provision("tenant-a");
        KmsTenantEncryption encryption = new KmsTenantEncryption(provider);
        Path root = temporary.resolve("kms-cas");
        CasStore store = new TenantEncryptedLocalCasStore("kms", root, encryption)
                .forTenant("tenant-a");
        byte[] plaintext = "retain during provider outage".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        store.put(digest, plaintext);

        provider.unavailable = true;
        CasExceptions.CasAccessDeniedException unavailable = assertThrows(
                CasExceptions.CasAccessDeniedException.class, () -> store.get(digest));
        assertEquals("TENANT_KMS_UNAVAILABLE", unavailable.reason());
        assertTrue(store.contains(digest));
        try (var walk = Files.walk(root.resolve("quarantine"))) {
            assertFalse(walk.anyMatch(path -> path.getFileName().toString()
                    .endsWith(".poisoned")));
        }
    }

    @Test void tamperedPayloadFailsAuthenticatedDecryption() {
        FakeProvider provider = new FakeProvider().provision("tenant-a");
        KmsTenantEncryption encryption = new KmsTenantEncryption(provider);
        byte[] plaintext = "artifact".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(plaintext);
        TenantEncryption.Envelope original = encryption.seal("tenant-a", digest, plaintext);
        byte[] tampered = original.ciphertext();
        tampered[tampered.length - 1] ^= 1;

        CasExceptions.CasAccessDeniedException invalid = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> encryption.open("tenant-a", digest,
                        new TenantEncryption.Envelope(original.keyId(), tampered)));
        assertEquals("TENANT_CIPHERTEXT_AUTHENTICATION_FAILED", invalid.reason());
        assertTrue(provider.lastDecryptedDataKeyWasZeroed());
    }

    @Test void rejectedProviderDataKeyBuffersAreAlsoDestroyed() {
        byte[] invalidPlaintextKey = new byte[16];
        java.util.Arrays.fill(invalidPlaintextKey, (byte) 7);
        KmsTenantEncryption.KeyVersion keyVersion = new KmsTenantEncryption.KeyVersion(
                "kms://test/tenant-a/root", "v1");

        assertThrows(IllegalArgumentException.class,
                () -> new KmsTenantEncryption.GeneratedDataKey(
                        keyVersion, invalidPlaintextKey, new byte[]{1}));
        for (byte value : invalidPlaintextKey) {
            assertEquals(0, value);
        }

        byte[] validPlaintextKey = new byte[32];
        java.util.Arrays.fill(validPlaintextKey, (byte) 9);
        assertThrows(IllegalArgumentException.class,
                () -> new KmsTenantEncryption.GeneratedDataKey(
                        keyVersion, validPlaintextKey, new byte[0]));
        for (byte value : validPlaintextKey) {
            assertEquals(0, value);
        }

        byte[] missingVersionPlaintextKey = new byte[32];
        java.util.Arrays.fill(missingVersionPlaintextKey, (byte) 11);
        assertThrows(NullPointerException.class,
                () -> new KmsTenantEncryption.GeneratedDataKey(
                        null, missingVersionPlaintextKey, new byte[]{1}));
        for (byte value : missingVersionPlaintextKey) {
            assertEquals(0, value,
                    "ownership begins before any other provider metadata is validated");
        }
    }

    private static boolean contains(byte[] haystack, byte[] needle) {
        outer:
        for (int start = 0; start <= haystack.length - needle.length; start++) {
            for (int index = 0; index < needle.length; index++) {
                if (haystack[start + index] != needle[index]) {
                    continue outer;
                }
            }
            return true;
        }
        return false;
    }

    private static final class FakeProvider implements KmsTenantEncryption.KeyManagementProvider {
        private final Map<String, KmsTenantEncryption.KeyVersion> current = new ConcurrentHashMap<>();
        private final Map<KmsTenantEncryption.KeyVersion, KmsTenantEncryption.KeyState> states =
                new ConcurrentHashMap<>();
        private final Map<String, CasDigest> wrappedContexts = new ConcurrentHashMap<>();
        private final AtomicInteger version = new AtomicInteger(1);
        private final SecureRandom random = new SecureRandom();
        private volatile byte[] lastPlaintextDataKey;
        private volatile byte[] lastDecryptedDataKey;
        private volatile boolean unavailable;

        FakeProvider provision(String tenantId) {
            KmsTenantEncryption.KeyVersion keyVersion = new KmsTenantEncryption.KeyVersion(
                    "kms://test/" + tenantId + "/root", "v" + version.get());
            current.put(tenantId, keyVersion);
            states.put(keyVersion, KmsTenantEncryption.KeyState.ACTIVE);
            return this;
        }

        @Override
        public KmsTenantEncryption.KeyVersion currentVersion(String tenantId)
                throws KmsTenantEncryption.ProviderException {
            requireAvailable();
            KmsTenantEncryption.KeyVersion value = current.get(tenantId);
            if (value == null) {
                throw new KmsTenantEncryption.ProviderException(
                        KmsTenantEncryption.ProviderFailure.KEY_NOT_FOUND, "missing tenant key");
            }
            return value;
        }

        @Override
        public KmsTenantEncryption.KeyState state(
                String tenantId, KmsTenantEncryption.KeyVersion keyVersion)
                throws KmsTenantEncryption.ProviderException {
            requireAvailable();
            return states.getOrDefault(keyVersion, KmsTenantEncryption.KeyState.UNKNOWN);
        }

        @Override
        public KmsTenantEncryption.GeneratedDataKey generateDataKey(
                String tenantId, KmsTenantEncryption.KeyVersion keyVersion,
                KmsTenantEncryption.EncryptionContext context)
                throws KmsTenantEncryption.ProviderException {
            requireAvailable();
            if (state(tenantId, keyVersion) != KmsTenantEncryption.KeyState.ACTIVE) {
                throw new KmsTenantEncryption.ProviderException(
                        KmsTenantEncryption.ProviderFailure.KEY_REVOKED, "key is not active");
            }
            byte[] plaintextKey = new byte[32];
            random.nextBytes(plaintextKey);
            lastPlaintextDataKey = plaintextKey;
            byte[] wrapped = wrap(keyVersion, plaintextKey);
            wrappedContexts.put(Base64.getEncoder().encodeToString(wrapped),
                    CasDigest.of(context.canonicalBytes()));
            return new KmsTenantEncryption.GeneratedDataKey(keyVersion, plaintextKey, wrapped);
        }

        private boolean lastPlaintextDataKeyWasZeroed() {
            if (lastPlaintextDataKey == null) {
                return false;
            }
            for (byte value : lastPlaintextDataKey) {
                if (value != 0) {
                    return false;
                }
            }
            return true;
        }

        private boolean lastDecryptedDataKeyWasZeroed() {
            if (lastDecryptedDataKey == null) {
                return false;
            }
            for (byte value : lastDecryptedDataKey) {
                if (value != 0) {
                    return false;
                }
            }
            return true;
        }

        @Override
        public byte[] decryptDataKey(String tenantId,
                                     KmsTenantEncryption.KeyVersion keyVersion,
                                     byte[] wrappedKey,
                                     KmsTenantEncryption.EncryptionContext context)
                throws KmsTenantEncryption.ProviderException {
            requireAvailable();
            CasDigest expected = wrappedContexts.get(Base64.getEncoder().encodeToString(wrappedKey));
            if (expected == null || !expected.equals(CasDigest.of(context.canonicalBytes()))) {
                throw new KmsTenantEncryption.ProviderException(
                        KmsTenantEncryption.ProviderFailure.PERMISSION_DENIED,
                        "encryption context mismatch");
            }
            if (state(tenantId, keyVersion) == KmsTenantEncryption.KeyState.REVOKED) {
                throw new KmsTenantEncryption.ProviderException(
                        KmsTenantEncryption.ProviderFailure.KEY_REVOKED, "revoked");
            }
            byte[] plaintextKey = unwrap(keyVersion, wrappedKey);
            lastDecryptedDataKey = plaintextKey;
            return plaintextKey;
        }

        @Override
        public KmsTenantEncryption.KeyVersion rotate(String tenantId)
                throws KmsTenantEncryption.ProviderException {
            requireAvailable();
            KmsTenantEncryption.KeyVersion previous = currentVersion(tenantId);
            states.put(previous, KmsTenantEncryption.KeyState.DECRYPT_ONLY);
            KmsTenantEncryption.KeyVersion next = new KmsTenantEncryption.KeyVersion(
                    previous.keyReference(), "v" + version.incrementAndGet());
            states.put(next, KmsTenantEncryption.KeyState.ACTIVE);
            current.put(tenantId, next);
            return next;
        }

        @Override
        public void revoke(String tenantId, KmsTenantEncryption.KeyVersion keyVersion)
                throws KmsTenantEncryption.ProviderException {
            requireAvailable();
            if (!states.containsKey(keyVersion)) {
                throw new KmsTenantEncryption.ProviderException(
                        KmsTenantEncryption.ProviderFailure.KEY_NOT_FOUND, "missing key");
            }
            states.put(keyVersion, KmsTenantEncryption.KeyState.REVOKED);
        }

        private void requireAvailable() throws KmsTenantEncryption.ProviderException {
            if (unavailable) {
                throw new KmsTenantEncryption.ProviderException(
                        KmsTenantEncryption.ProviderFailure.UNAVAILABLE, "test provider unavailable");
            }
        }

        private byte[] masterKey(KmsTenantEncryption.KeyVersion keyVersion) {
            try {
                return MessageDigest.getInstance("SHA-256").digest(
                        ("test-master\n" + keyVersion.keyReference() + "\n" + keyVersion.version())
                                .getBytes(StandardCharsets.UTF_8));
            } catch (Exception impossible) {
                throw new IllegalStateException(impossible);
            }
        }

        private byte[] wrap(KmsTenantEncryption.KeyVersion keyVersion, byte[] plaintextKey)
                throws KmsTenantEncryption.ProviderException {
            try {
                Cipher wrapper = Cipher.getInstance("AESWrap");
                wrapper.init(Cipher.WRAP_MODE, new SecretKeySpec(masterKey(keyVersion), "AES"));
                return wrapper.wrap(new SecretKeySpec(plaintextKey, "AES"));
            } catch (Exception failure) {
                throw new KmsTenantEncryption.ProviderException(
                        KmsTenantEncryption.ProviderFailure.UNAVAILABLE, "cannot wrap", failure);
            }
        }

        private byte[] unwrap(KmsTenantEncryption.KeyVersion keyVersion, byte[] wrappedKey)
                throws KmsTenantEncryption.ProviderException {
            try {
                Cipher wrapper = Cipher.getInstance("AESWrap");
                wrapper.init(Cipher.UNWRAP_MODE, new SecretKeySpec(masterKey(keyVersion), "AES"));
                SecretKey key = (SecretKey) wrapper.unwrap(wrappedKey, "AES", Cipher.SECRET_KEY);
                return key.getEncoded();
            } catch (Exception failure) {
                throw new KmsTenantEncryption.ProviderException(
                        KmsTenantEncryption.ProviderFailure.PERMISSION_DENIED, "cannot unwrap", failure);
            }
        }
    }
}
