package io.elmos.cas;

import org.junit.jupiter.api.Test;

import javax.net.ssl.SSLContext;
import java.net.URI;
import java.net.http.HttpTimeoutException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpKmsBrokerProviderTest {

    private static final String MEDIA_TYPE =
            "application/vnd.elmos.kms-broker.v1+octet-stream";
    private static final String KEY_REFERENCE = "hsm://cluster-a/tenant-root";

    @Test void brokerAdapterBindsWorkloadIdentityRotatesAndDecryptsOldVersion() {
        FakeBroker broker = new FakeBroker();
        HttpKmsBrokerProvider provider = new HttpKmsBrokerProvider(config(), broker);
        KmsTenantEncryption encryption = new KmsTenantEncryption(provider);
        byte[] oldPlaintext = "old tenant artifact".getBytes(StandardCharsets.UTF_8);
        CasDigest oldDigest = CasDigest.of(oldPlaintext);

        TenantEncryption.Envelope oldEnvelope =
                encryption.seal("tenant-a", oldDigest, oldPlaintext);
        KmsTenantEncryption.KeyVersion oldVersion = encryption.currentVersion("tenant-a");
        KmsTenantEncryption.KeyVersion newVersion = encryption.rotate("tenant-a");
        byte[] newPlaintext = "new tenant artifact".getBytes(StandardCharsets.UTF_8);
        CasDigest newDigest = CasDigest.of(newPlaintext);
        TenantEncryption.Envelope newEnvelope =
                encryption.seal("tenant-a", newDigest, newPlaintext);

        assertEquals("v1", oldVersion.version());
        assertEquals("v2", newVersion.version());
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

        assertTrue(broker.sawExactIdentityReferences);
        assertFalse(broker.requestBodies.isEmpty());
        assertFalse(broker.secretValueWasSent,
                "only opaque secret references may cross the adapter boundary");
        broker.requestBodies.forEach(body -> assertTrue(allZero(body),
                "every owned request frame must be destroyed"));
        broker.responseBodies.stream().filter(body -> body.length > 0).forEach(body ->
                assertTrue(allZero(body),
                        "plaintext DEK response buffers must be destroyed by their owner"));
    }

    @Test void timeoutRedirectPermissionAndProtocolDriftFailClosed() throws Exception {
        HttpKmsBrokerProvider timeout = new HttpKmsBrokerProvider(config(), request -> {
            throw new HttpTimeoutException("simulated timeout with secret-value-never-propagated");
        });
        KmsTenantEncryption.ProviderException unavailable = assertThrows(
                KmsTenantEncryption.ProviderException.class,
                () -> timeout.currentVersion("tenant-a"));
        assertEquals(KmsTenantEncryption.ProviderFailure.UNAVAILABLE, unavailable.failure());
        assertFalse(unavailable.getMessage().contains("secret-value"));
        assertEquals(null, unavailable.getCause(),
                "transport exception details must not become loggable secret material");

        HttpKmsBrokerProvider redirected = new HttpKmsBrokerProvider(config(), request ->
                response(request, 200, URI.create("https://attacker.invalid/v1/current-version"),
                        keyHeaders("v1"), new byte[0]));
        KmsTenantEncryption.ProviderException redirectDenied = assertThrows(
                KmsTenantEncryption.ProviderException.class,
                () -> redirected.currentVersion("tenant-a"));
        assertEquals(KmsTenantEncryption.ProviderFailure.INVALID_RESPONSE,
                redirectDenied.failure());

        HttpKmsBrokerProvider forbidden = new HttpKmsBrokerProvider(config(), request ->
                response(request, 403, request.uri(), baseHeaders(), new byte[0]));
        KmsTenantEncryption.ProviderException permissionDenied = assertThrows(
                KmsTenantEncryption.ProviderException.class,
                () -> forbidden.currentVersion("tenant-a"));
        assertEquals(KmsTenantEncryption.ProviderFailure.PERMISSION_DENIED,
                permissionDenied.failure());

        Map<String, List<String>> duplicateProtocol = new LinkedHashMap<>(keyHeaders("v1"));
        duplicateProtocol.put("X-ELMOS-KMS-Protocol", List.of(
                HttpKmsBrokerProvider.PROTOCOL, "downgrade"));
        HttpKmsBrokerProvider ambiguous = new HttpKmsBrokerProvider(config(), request ->
                response(request, 200, request.uri(), duplicateProtocol, new byte[0]));
        KmsTenantEncryption.ProviderException invalidProtocol = assertThrows(
                KmsTenantEncryption.ProviderException.class,
                () -> ambiguous.currentVersion("tenant-a"));
        assertEquals(KmsTenantEncryption.ProviderFailure.INVALID_RESPONSE,
                invalidProtocol.failure());
    }

    @Test void malformedOrVersionDriftedDataKeysAreRejectedAndDestroyed() {
        List<byte[]> responseBodies = new ArrayList<>();
        HttpKmsBrokerProvider malformed = new HttpKmsBrokerProvider(config(), request -> {
            if ("current-version".equals(request.operation())) {
                return response(request, 200, request.uri(), keyHeaders("v1"), new byte[0]);
            }
            if ("key-state".equals(request.operation())) {
                Map<String, List<String>> headers = new LinkedHashMap<>(keyHeaders("v1"));
                headers.put("X-ELMOS-KMS-Key-State", List.of("ACTIVE"));
                return response(request, 200, request.uri(), headers, new byte[0]);
            }
            byte[] invalid = generatedBody(new byte[16], new byte[]{1, 2, 3});
            responseBodies.add(invalid);
            return response(request, 200, request.uri(), keyHeaders("v1"), invalid);
        });
        KmsTenantEncryption encryption = new KmsTenantEncryption(malformed);
        byte[] plaintext = "artifact".getBytes(StandardCharsets.UTF_8);
        CasExceptions.CasAccessDeniedException invalid = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> encryption.seal("tenant-a", CasDigest.of(plaintext), plaintext));
        assertEquals("TENANT_KMS_INVALID_RESPONSE", invalid.reason());
        assertTrue(allZero(responseBodies.get(0)));

        HttpKmsBrokerProvider drifted = new HttpKmsBrokerProvider(config(), request -> {
            if ("current-version".equals(request.operation())) {
                return response(request, 200, request.uri(), keyHeaders("v1"), new byte[0]);
            }
            if ("key-state".equals(request.operation())) {
                Map<String, List<String>> headers = new LinkedHashMap<>(keyHeaders("v1"));
                headers.put("X-ELMOS-KMS-Key-State", List.of("ACTIVE"));
                return response(request, 200, request.uri(), headers, new byte[0]);
            }
            return response(request, 200, request.uri(), keyHeaders("v2"),
                    generatedBody(new byte[32], new byte[]{1}));
        });
        KmsTenantEncryption driftEncryption = new KmsTenantEncryption(drifted);
        CasExceptions.CasAccessDeniedException drift = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> driftEncryption.seal(
                        "tenant-a", CasDigest.of(plaintext), plaintext));
        assertEquals("TENANT_KMS_INVALID_RESPONSE", drift.reason());
    }

    @Test void configurationRequiresHttpsSpiffeAndOpaqueDistinctSecretReferences() {
        HttpKmsBrokerProvider.IdentityBinding identity = identity();
        assertThrows(IllegalArgumentException.class, () -> new HttpKmsBrokerProvider.Config(
                URI.create("http://kms-broker.internal/v1"), Duration.ofSeconds(1),
                Duration.ofSeconds(2), identity));
        assertThrows(IllegalArgumentException.class,
                () -> HttpKmsBrokerProvider.SecretReference.parse("https://vault/secret-value"));
        assertThrows(IllegalArgumentException.class,
                () -> HttpKmsBrokerProvider.SecretReference.parse(
                        "secret://platform/credential?value=not-a-reference"));
        HttpKmsBrokerProvider.SecretReference same =
                HttpKmsBrokerProvider.SecretReference.parse("secret://platform/same");
        assertThrows(IllegalArgumentException.class,
                () -> new HttpKmsBrokerProvider.IdentityBinding(
                        new WorkloadIdentity.SpiffeId(
                                "prod.elmos.internal", "control-plane/cas"), same, same));
        assertThrows(IllegalArgumentException.class, () -> new HttpKmsBrokerProvider.Config(
                URI.create("https://kms-broker.internal/v1"), Duration.ofSeconds(31),
                Duration.ofSeconds(2), identity));
    }

    @Test void workloadSslContextProviderReceivesOnlyOpaqueIdentityAndResponseDropsOtherHeaders()
            throws Exception {
        AtomicBoolean resolved = new AtomicBoolean();
        HttpKmsBrokerProvider provider = HttpKmsBrokerProvider.usingMtls(
                config(), binding -> {
                    assertEquals("spiffe://prod.elmos.internal/control-plane/cas",
                            binding.workloadIdentity().uri());
                    assertEquals("secret://platform/cas-kms-mtls",
                            binding.mtlsCredentialReference().headerValue());
                    resolved.set(true);
                    try {
                        return SSLContext.getDefault();
                    } catch (Exception unavailable) {
                        throw new IllegalStateException(unavailable);
                    }
                });
        assertTrue(resolved.get());
        assertNotNull(provider);

        try (HttpKmsBrokerProvider.BrokerResponse response =
                     new HttpKmsBrokerProvider.BrokerResponse(
                             200,
                             URI.create("https://kms-broker.internal/v1/current-version"),
                             Map.of(
                                     "Content-Type", List.of(MEDIA_TYPE),
                                     "Set-Cookie", List.of("must-not-be-retained")),
                             new byte[0])) {
            assertThrows(KmsTenantEncryption.ProviderException.class,
                    () -> response.singleHeader("Set-Cookie"));
        }
    }

    private static HttpKmsBrokerProvider.Config config() {
        return new HttpKmsBrokerProvider.Config(
                URI.create("https://kms-broker.internal/v1"),
                Duration.ofSeconds(3), Duration.ofSeconds(5), identity());
    }

    private static HttpKmsBrokerProvider.IdentityBinding identity() {
        return new HttpKmsBrokerProvider.IdentityBinding(
                new WorkloadIdentity.SpiffeId(
                        "prod.elmos.internal", "control-plane/cas"),
                HttpKmsBrokerProvider.SecretReference.parse(
                        "secret://platform/cas-kms-mtls"),
                HttpKmsBrokerProvider.SecretReference.parse(
                        "secret://platform/cas-kms-policy"));
    }

    private static HttpKmsBrokerProvider.BrokerResponse response(
            HttpKmsBrokerProvider.BrokerRequest request, int status, URI uri,
            Map<String, List<String>> headers, byte[] body) {
        Map<String, List<String>> boundHeaders = new LinkedHashMap<>(headers);
        boundHeaders.put("X-ELMOS-KMS-Operation", List.of(request.operation()));
        return new HttpKmsBrokerProvider.BrokerResponse(status, uri, boundHeaders, body);
    }

    private static Map<String, List<String>> baseHeaders() {
        return Map.of(
                "Content-Type", List.of(MEDIA_TYPE),
                "X-ELMOS-KMS-Protocol", List.of(HttpKmsBrokerProvider.PROTOCOL));
    }

    private static Map<String, List<String>> keyHeaders(String version) {
        Map<String, List<String>> headers = new LinkedHashMap<>(baseHeaders());
        headers.put("X-ELMOS-KMS-Key-Reference", List.of(KEY_REFERENCE));
        headers.put("X-ELMOS-KMS-Key-Version", List.of(version));
        return headers;
    }

    private static byte[] generatedBody(byte[] plaintextKey, byte[] wrappedKey) {
        return ByteBuffer.allocate(Integer.BYTES * 2 + plaintextKey.length + wrappedKey.length)
                .putInt(plaintextKey.length).put(plaintextKey)
                .putInt(wrappedKey.length).put(wrappedKey).array();
    }

    private static boolean allZero(byte[] value) {
        for (byte element : value) {
            if (element != 0) {
                return false;
            }
        }
        return true;
    }

    private static final class FakeBroker implements HttpKmsBrokerProvider.BrokerTransport {
        private final Map<String, KmsTenantEncryption.KeyState> states =
                new ConcurrentHashMap<>();
        private final Map<String, WrappedDataKey> dataKeys = new ConcurrentHashMap<>();
        private final List<byte[]> requestBodies = new ArrayList<>();
        private final List<byte[]> responseBodies = new ArrayList<>();
        private String currentVersion = "v1";
        private int wrappedSequence;
        private boolean sawExactIdentityReferences;
        private boolean secretValueWasSent;

        private FakeBroker() {
            states.put("v1", KmsTenantEncryption.KeyState.ACTIVE);
        }

        @Override
        public HttpKmsBrokerProvider.BrokerResponse exchange(
                HttpKmsBrokerProvider.BrokerRequest request) {
            byte[] ownedRequest = request.body();
            requestBodies.add(ownedRequest);
            RequestFrame frame = RequestFrame.parse(ownedRequest);
            assertEquals("tenant-a", frame.tenantId);
            assertEquals("spiffe://prod.elmos.internal/control-plane/cas",
                    request.headers().get("X-ELMOS-Workload-Identity"));
            assertEquals("secret://platform/cas-kms-mtls",
                    request.headers().get("X-ELMOS-mTLS-Secret-Reference"));
            assertEquals("secret://platform/cas-kms-policy",
                    request.headers().get("X-ELMOS-Authorization-Secret-Reference"));
            sawExactIdentityReferences = true;
            secretValueWasSent |= request.headers().values().stream()
                    .anyMatch(value -> value.contains("super-secret-value"));

            return switch (request.operation()) {
                case "current-version" -> ok(request, keyHeaders(currentVersion), new byte[0]);
                case "key-state" -> stateResponse(request, frame.version);
                case "generate-data-key" -> generate(request, frame);
                case "decrypt-data-key" -> decrypt(request, frame);
                case "rotate" -> rotate(request);
                case "revoke" -> revoke(request, frame.version);
                default -> throw new AssertionError("unexpected operation " + request.operation());
            };
        }

        private HttpKmsBrokerProvider.BrokerResponse stateResponse(
                HttpKmsBrokerProvider.BrokerRequest request, String version) {
            Map<String, List<String>> headers = new LinkedHashMap<>(keyHeaders(version));
            headers.put("X-ELMOS-KMS-Key-State",
                    List.of(states.getOrDefault(
                            version, KmsTenantEncryption.KeyState.UNKNOWN).name()));
            return ok(request, headers, new byte[0]);
        }

        private HttpKmsBrokerProvider.BrokerResponse generate(
                HttpKmsBrokerProvider.BrokerRequest request, RequestFrame frame) {
            assertEquals(currentVersion, frame.version);
            assertFalse(frame.context.length == 0);
            byte[] plaintextKey = digest("dek/" + frame.version + "/" + wrappedSequence);
            byte[] wrapped = ("wrapped/" + frame.version + "/" + wrappedSequence++)
                    .getBytes(StandardCharsets.UTF_8);
            dataKeys.put(Base64.getEncoder().encodeToString(wrapped),
                    new WrappedDataKey(plaintextKey.clone(), frame.context.clone(), frame.version));
            byte[] body = generatedBody(plaintextKey, wrapped);
            Arrays.fill(plaintextKey, (byte) 0);
            Arrays.fill(wrapped, (byte) 0);
            return ok(request, keyHeaders(frame.version), body);
        }

        private HttpKmsBrokerProvider.BrokerResponse decrypt(
                HttpKmsBrokerProvider.BrokerRequest request, RequestFrame frame) {
            WrappedDataKey stored = dataKeys.get(
                    Base64.getEncoder().encodeToString(frame.wrappedKey));
            if (stored == null || !stored.version.equals(frame.version)
                    || !MessageDigest.isEqual(stored.context, frame.context)) {
                return response(request, 403, request.uri(), baseHeaders(), new byte[0]);
            }
            if (states.getOrDefault(frame.version,
                    KmsTenantEncryption.KeyState.UNKNOWN)
                    == KmsTenantEncryption.KeyState.REVOKED) {
                return response(request, 410, request.uri(), baseHeaders(), new byte[0]);
            }
            return ok(request, keyHeaders(frame.version), stored.plaintextKey.clone());
        }

        private HttpKmsBrokerProvider.BrokerResponse rotate(
                HttpKmsBrokerProvider.BrokerRequest request) {
            states.put(currentVersion, KmsTenantEncryption.KeyState.DECRYPT_ONLY);
            currentVersion = "v2";
            states.put(currentVersion, KmsTenantEncryption.KeyState.ACTIVE);
            return ok(request, keyHeaders(currentVersion), new byte[0]);
        }

        private HttpKmsBrokerProvider.BrokerResponse revoke(
                HttpKmsBrokerProvider.BrokerRequest request, String version) {
            states.put(version, KmsTenantEncryption.KeyState.REVOKED);
            Map<String, List<String>> headers = new LinkedHashMap<>(keyHeaders(version));
            headers.put("X-ELMOS-KMS-Key-State", List.of("REVOKED"));
            return ok(request, headers, new byte[0]);
        }

        private HttpKmsBrokerProvider.BrokerResponse ok(
                HttpKmsBrokerProvider.BrokerRequest request,
                Map<String, List<String>> headers, byte[] body) {
            responseBodies.add(body);
            return response(request, 200, request.uri(), headers, body);
        }

        private static byte[] digest(String value) {
            try {
                return MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8));
            } catch (Exception impossible) {
                throw new IllegalStateException(impossible);
            }
        }
    }

    private record WrappedDataKey(byte[] plaintextKey, byte[] context, String version) {
    }

    private static final class RequestFrame {
        private static final byte[] MAGIC = "ELMOS-KMS-BROKER/1\n"
                .getBytes(StandardCharsets.US_ASCII);

        private final String tenantId;
        private final String reference;
        private final String version;
        private final byte[] context;
        private final byte[] wrappedKey;

        private RequestFrame(String tenantId, String reference, String version,
                             byte[] context, byte[] wrappedKey) {
            this.tenantId = tenantId;
            this.reference = reference;
            this.version = version;
            this.context = context;
            this.wrappedKey = wrappedKey;
        }

        private static RequestFrame parse(byte[] encoded) {
            ByteBuffer input = ByteBuffer.wrap(encoded);
            byte[] exactMagic = new byte[MAGIC.length];
            input.get(exactMagic);
            assertArrayEquals(MAGIC, exactMagic);
            return new RequestFrame(
                    new String(take(input), StandardCharsets.UTF_8),
                    new String(take(input), StandardCharsets.UTF_8),
                    new String(take(input), StandardCharsets.UTF_8),
                    take(input), take(input));
        }

        private static byte[] take(ByteBuffer input) {
            int length = input.getInt();
            byte[] value = new byte[length];
            input.get(value);
            return value;
        }
    }
}
