package io.elmos.cas;

import javax.net.ssl.SSLContext;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/**
 * HTTPS/mTLS adapter for an independently operated KMS or HSM broker.
 *
 * <p>This adapter deliberately does not accept a bearer token, private key, PIN, cloud access
 * key, or other secret value. A deployment supplies an {@link SSLContext} backed by its workload
 * identity and two opaque {@link SecretReference}s. The references identify the mTLS credential
 * and broker-side authorization policy; the broker resolves them in its own trust boundary and
 * must compare the authenticated TLS identity with the asserted SPIFFE identity. Repository
 * configuration therefore never contains the corresponding secret values.
 *
 * <p>The broker protocol is binary rather than JSON. In particular, a generated plaintext DEK is
 * never materialized as an immutable Base64 {@link String}; every request and response byte buffer
 * is owned and zeroed. Redirects, timeouts, oversized bodies, duplicate metadata, version drift,
 * unknown status codes and malformed responses fail closed.
 *
 * <p>Constructing this class is not evidence that a production broker, HSM, identity, custody
 * ceremony, rotation drill or revocation path has been exercised. Those remain {@code NOT_RUN}
 * until an authorized deployment supplies and independently verifies them.
 */
public final class HttpKmsBrokerProvider implements KmsTenantEncryption.KeyManagementProvider {

    public static final String PROTOCOL = "elmos-kms-broker/1";

    private static final String MEDIA_TYPE =
            "application/vnd.elmos.kms-broker.v1+octet-stream";
    private static final byte[] REQUEST_MAGIC = "ELMOS-KMS-BROKER/1\n"
            .getBytes(StandardCharsets.US_ASCII);
    private static final int DATA_KEY_BYTES = 32;
    private static final int MAX_TENANT_BYTES = 4 * 1024;
    private static final int MAX_KEY_REFERENCE_BYTES = 2 * 1024;
    private static final int MAX_KEY_VERSION_BYTES = 256;
    private static final int MAX_CONTEXT_BYTES = 16 * 1024;
    private static final int MAX_WRAPPED_KEY_BYTES = 64 * 1024;
    private static final int MAX_RESPONSE_BYTES = 128 * 1024;
    private static final Duration MAX_CONNECT_TIMEOUT = Duration.ofSeconds(30);
    private static final Duration MAX_OPERATION_TIMEOUT = Duration.ofSeconds(60);

    private static final String HEADER_PROTOCOL = "X-ELMOS-KMS-Protocol";
    private static final String HEADER_OPERATION = "X-ELMOS-KMS-Operation";
    private static final String HEADER_WORKLOAD_IDENTITY = "X-ELMOS-Workload-Identity";
    private static final String HEADER_MTLS_SECRET_REFERENCE =
            "X-ELMOS-mTLS-Secret-Reference";
    private static final String HEADER_AUTHORIZATION_REFERENCE =
            "X-ELMOS-Authorization-Secret-Reference";
    private static final String HEADER_KEY_REFERENCE = "X-ELMOS-KMS-Key-Reference";
    private static final String HEADER_KEY_VERSION = "X-ELMOS-KMS-Key-Version";
    private static final String HEADER_KEY_STATE = "X-ELMOS-KMS-Key-State";
    private static final java.util.Set<String> RESPONSE_HEADERS = java.util.Set.of(
            "content-type",
            HEADER_PROTOCOL.toLowerCase(Locale.ROOT),
            HEADER_OPERATION.toLowerCase(Locale.ROOT),
            HEADER_KEY_REFERENCE.toLowerCase(Locale.ROOT),
            HEADER_KEY_VERSION.toLowerCase(Locale.ROOT),
            HEADER_KEY_STATE.toLowerCase(Locale.ROOT));

    /** Resolves the opaque mTLS reference through an external workload-identity boundary. */
    @FunctionalInterface
    public interface WorkloadSslContextProvider {
        SSLContext sslContext(IdentityBinding identity);
    }

    /** Opaque reference resolved outside this process; it is never a secret value. */
    public record SecretReference(URI reference) {
        public SecretReference {
            reference = validateSecretReference(reference);
        }

        public static SecretReference parse(String reference) {
            return new SecretReference(URI.create(CasText.required(reference, "secretReference")));
        }

        public String headerValue() {
            return reference.toASCIIString();
        }
    }

    /**
     * Exact workload identity and the external secret references that provision its TLS material
     * and broker authorization. No referenced value is read by this module.
     */
    public record IdentityBinding(WorkloadIdentity.SpiffeId workloadIdentity,
                                  SecretReference mtlsCredentialReference,
                                  SecretReference authorizationPolicyReference) {
        public IdentityBinding {
            workloadIdentity = Objects.requireNonNull(workloadIdentity, "workloadIdentity");
            mtlsCredentialReference = Objects.requireNonNull(
                    mtlsCredentialReference, "mtlsCredentialReference");
            authorizationPolicyReference = Objects.requireNonNull(
                    authorizationPolicyReference, "authorizationPolicyReference");
            if (mtlsCredentialReference.equals(authorizationPolicyReference)) {
                throw new IllegalArgumentException(
                        "mTLS credential and authorization policy require distinct references");
            }
            // Parsing makes control characters and non-URI SPIFFE values fail before a request.
            URI parsed = URI.create(workloadIdentity.uri());
            if (!"spiffe".equalsIgnoreCase(parsed.getScheme()) || parsed.getHost() == null
                    || parsed.getRawPath() == null || parsed.getRawPath().length() < 2
                    || parsed.getRawQuery() != null || parsed.getRawFragment() != null
                    || parsed.getUserInfo() != null) {
                throw new IllegalArgumentException("workloadIdentity must be an exact SPIFFE URI");
            }
        }

        String workloadIdentityHeader() {
            return URI.create(workloadIdentity.uri()).toASCIIString();
        }
    }

    public record Config(URI endpoint, Duration connectTimeout, Duration operationTimeout,
                         IdentityBinding identity) {
        public Config {
            endpoint = validateEndpoint(endpoint);
            connectTimeout = boundedTimeout(
                    connectTimeout, "connectTimeout", MAX_CONNECT_TIMEOUT);
            operationTimeout = boundedTimeout(
                    operationTimeout, "operationTimeout", MAX_OPERATION_TIMEOUT);
            identity = Objects.requireNonNull(identity, "identity");
        }
    }

    private enum Operation {
        CURRENT_VERSION("current-version"),
        KEY_STATE("key-state"),
        GENERATE_DATA_KEY("generate-data-key"),
        DECRYPT_DATA_KEY("decrypt-data-key"),
        ROTATE("rotate"),
        REVOKE("revoke");

        private final String path;

        Operation(String path) {
            this.path = path;
        }
    }

    @FunctionalInterface
    interface BrokerTransport {
        BrokerResponse exchange(BrokerRequest request) throws IOException, InterruptedException;
    }

    static final class BrokerRequest implements AutoCloseable {
        private final Operation operation;
        private final URI uri;
        private final Duration timeout;
        private final Map<String, String> headers;
        private byte[] body;

        BrokerRequest(Operation operation, URI uri, Duration timeout,
                      Map<String, String> headers, byte[] body) {
            this.operation = Objects.requireNonNull(operation, "operation");
            this.uri = Objects.requireNonNull(uri, "uri");
            this.timeout = Objects.requireNonNull(timeout, "timeout");
            this.headers = Map.copyOf(headers);
            this.body = Objects.requireNonNull(body, "body");
        }

        String operation() {
            return operation.path;
        }

        URI uri() {
            return uri;
        }

        Duration timeout() {
            return timeout;
        }

        Map<String, String> headers() {
            return headers;
        }

        /** Borrowed only for the duration of {@link BrokerTransport#exchange}. */
        byte[] body() {
            if (body == null) {
                throw new IllegalStateException("broker request body has been destroyed");
            }
            return body;
        }

        @Override
        public void close() {
            if (body != null) {
                Arrays.fill(body, (byte) 0);
                body = null;
            }
        }
    }

    /** Response bytes transfer to this object and are destroyed on close. */
    static final class BrokerResponse implements AutoCloseable {
        private final int statusCode;
        private final URI responseUri;
        private final Map<String, List<String>> headers;
        private byte[] body;

        BrokerResponse(int statusCode, URI responseUri, Map<String, List<String>> headers,
                       byte[] body) {
            this.statusCode = statusCode;
            this.responseUri = Objects.requireNonNull(responseUri, "responseUri");
            Map<String, List<String>> copied = new LinkedHashMap<>();
            Objects.requireNonNull(headers, "headers").forEach((name, values) -> {
                String normalized = name.toLowerCase(Locale.ROOT);
                if (!RESPONSE_HEADERS.contains(normalized)) {
                    return;
                }
                List<String> incoming = List.copyOf(values);
                List<String> existing = copied.get(normalized);
                if (existing == null) {
                    copied.put(normalized, incoming);
                } else {
                    List<String> ambiguous = new java.util.ArrayList<>(existing);
                    ambiguous.addAll(incoming);
                    copied.put(normalized, List.copyOf(ambiguous));
                }
            });
            this.headers = Map.copyOf(copied);
            this.body = Objects.requireNonNull(body, "body");
        }

        int statusCode() {
            return statusCode;
        }

        URI responseUri() {
            return responseUri;
        }

        String singleHeader(String name) throws KmsTenantEncryption.ProviderException {
            List<String> values = headers.getOrDefault(name.toLowerCase(Locale.ROOT), List.of());
            if (values.size() != 1 || values.get(0).isBlank()) {
                throw invalidResponse("missing or duplicate " + name);
            }
            return values.get(0);
        }

        byte[] takeBody() {
            if (body == null) {
                throw new IllegalStateException("broker response body has already transferred");
            }
            byte[] transferred = body;
            body = null;
            return transferred;
        }

        int bodyLength() {
            return body == null ? 0 : body.length;
        }

        @Override
        public void close() {
            if (body != null) {
                Arrays.fill(body, (byte) 0);
                body = null;
            }
        }
    }

    private static final class JdkHttpTransport implements BrokerTransport {
        private final HttpClient client;

        private JdkHttpTransport(HttpClient client) {
            this.client = Objects.requireNonNull(client, "client");
        }

        @Override
        public BrokerResponse exchange(BrokerRequest request)
                throws IOException, InterruptedException {
            HttpRequest.Builder builder = HttpRequest.newBuilder(request.uri())
                    .timeout(request.timeout())
                    .header("Content-Type", MEDIA_TYPE)
                    .header("Accept", MEDIA_TYPE)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(request.body()));
            request.headers().forEach(builder::header);
            HttpResponse<InputStream> response = client.send(
                    builder.build(), HttpResponse.BodyHandlers.ofInputStream());
            byte[] body;
            try (InputStream stream = response.body()) {
                body = stream.readNBytes(MAX_RESPONSE_BYTES + 1);
            }
            if (body.length > MAX_RESPONSE_BYTES) {
                Arrays.fill(body, (byte) 0);
                throw new IOException("KMS broker response exceeds the configured bound");
            }
            return new BrokerResponse(response.statusCode(), response.uri(),
                    response.headers().map(), body);
        }
    }

    private final Config config;
    private final BrokerTransport transport;

    /**
     * Builds the only public production transport: HTTPS, no redirects, explicit connect timeout
     * and a caller-provided workload-identity SSL context.
     */
    public static HttpKmsBrokerProvider usingMtls(Config config, SSLContext workloadSslContext) {
        Config validated = Objects.requireNonNull(config, "config");
        HttpClient client = HttpClient.newBuilder()
                .sslContext(Objects.requireNonNull(workloadSslContext, "workloadSslContext"))
                .connectTimeout(validated.connectTimeout())
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        return new HttpKmsBrokerProvider(validated, new JdkHttpTransport(client));
    }

    /**
     * Resolves the SSL context from the opaque identity binding without exposing credential
     * values to configuration or to this adapter.
     */
    public static HttpKmsBrokerProvider usingMtls(
            Config config, WorkloadSslContextProvider workloadSslContexts) {
        Config validated = Objects.requireNonNull(config, "config");
        WorkloadSslContextProvider provider = Objects.requireNonNull(
                workloadSslContexts, "workloadSslContexts");
        SSLContext sslContext = Objects.requireNonNull(
                provider.sslContext(validated.identity()),
                "workload SSL context provider returned null");
        return usingMtls(validated, sslContext);
    }

    HttpKmsBrokerProvider(Config config, BrokerTransport transport) {
        this.config = Objects.requireNonNull(config, "config");
        this.transport = Objects.requireNonNull(transport, "transport");
    }

    @Override
    public KmsTenantEncryption.KeyVersion currentVersion(String tenantId)
            throws KmsTenantEncryption.ProviderException {
        try (BrokerResponse response = call(
                Operation.CURRENT_VERSION, tenantId, null, null, null)) {
            requireEmptyBody(response);
            return responseKeyVersion(response);
        }
    }

    @Override
    public KmsTenantEncryption.KeyState state(
            String tenantId, KmsTenantEncryption.KeyVersion keyVersion)
            throws KmsTenantEncryption.ProviderException {
        Objects.requireNonNull(keyVersion, "keyVersion");
        try (BrokerResponse response = call(
                Operation.KEY_STATE, tenantId, keyVersion, null, null)) {
            requireEmptyBody(response);
            requireEchoedKey(response, keyVersion);
            try {
                return KmsTenantEncryption.KeyState.valueOf(
                        response.singleHeader(HEADER_KEY_STATE));
            } catch (IllegalArgumentException invalidState) {
                throw invalidResponse("unknown key state");
            }
        }
    }

    @Override
    public KmsTenantEncryption.GeneratedDataKey generateDataKey(
            String tenantId, KmsTenantEncryption.KeyVersion keyVersion,
            KmsTenantEncryption.EncryptionContext context)
            throws KmsTenantEncryption.ProviderException {
        requireContext(tenantId, keyVersion, context);
        byte[] contextBytes = context.canonicalBytes();
        try (BrokerResponse response = call(
                Operation.GENERATE_DATA_KEY, tenantId, keyVersion, contextBytes, null)) {
            requireEchoedKey(response, keyVersion);
            byte[] body = response.takeBody();
            byte[] plaintextKey = null;
            byte[] wrappedKey = null;
            try {
                ByteBuffer input = ByteBuffer.wrap(body);
                int plaintextLength = boundedFrameLength(
                        input, DATA_KEY_BYTES, DATA_KEY_BYTES, "plaintext data key");
                plaintextKey = take(input, plaintextLength);
                int wrappedLength = boundedFrameLength(
                        input, 1, MAX_WRAPPED_KEY_BYTES, "wrapped data key");
                wrappedKey = take(input, wrappedLength);
                if (input.hasRemaining()) {
                    throw invalidResponse("trailing generated-data-key bytes");
                }
                KmsTenantEncryption.GeneratedDataKey generated =
                        new KmsTenantEncryption.GeneratedDataKey(
                                keyVersion, plaintextKey, wrappedKey);
                plaintextKey = null; // ownership transferred; GeneratedDataKey closes it
                return generated;
            } catch (java.nio.BufferUnderflowException | IllegalArgumentException malformed) {
                throw invalidResponse("malformed generated data key");
            } finally {
                if (plaintextKey != null) {
                    Arrays.fill(plaintextKey, (byte) 0);
                }
                if (wrappedKey != null) {
                    Arrays.fill(wrappedKey, (byte) 0);
                }
                Arrays.fill(body, (byte) 0);
            }
        } finally {
            Arrays.fill(contextBytes, (byte) 0);
        }
    }

    @Override
    public byte[] decryptDataKey(
            String tenantId, KmsTenantEncryption.KeyVersion keyVersion, byte[] wrappedKey,
            KmsTenantEncryption.EncryptionContext context)
            throws KmsTenantEncryption.ProviderException {
        requireContext(tenantId, keyVersion, context);
        Objects.requireNonNull(wrappedKey, "wrappedKey");
        if (wrappedKey.length < 1 || wrappedKey.length > MAX_WRAPPED_KEY_BYTES) {
            throw invalidResponse("wrapped data key length is invalid");
        }
        byte[] contextBytes = context.canonicalBytes();
        try (BrokerResponse response = call(
                Operation.DECRYPT_DATA_KEY, tenantId, keyVersion, contextBytes, wrappedKey)) {
            requireEchoedKey(response, keyVersion);
            byte[] plaintextKey = response.takeBody();
            if (plaintextKey.length != DATA_KEY_BYTES) {
                Arrays.fill(plaintextKey, (byte) 0);
                throw invalidResponse("plaintext data key length is invalid");
            }
            // Ownership transfers to KmsTenantEncryption, which zeroes this exact array.
            return plaintextKey;
        } finally {
            Arrays.fill(contextBytes, (byte) 0);
        }
    }

    @Override
    public KmsTenantEncryption.KeyVersion rotate(String tenantId)
            throws KmsTenantEncryption.ProviderException {
        try (BrokerResponse response = call(Operation.ROTATE, tenantId, null, null, null)) {
            requireEmptyBody(response);
            return responseKeyVersion(response);
        }
    }

    @Override
    public void revoke(String tenantId, KmsTenantEncryption.KeyVersion keyVersion)
            throws KmsTenantEncryption.ProviderException {
        Objects.requireNonNull(keyVersion, "keyVersion");
        try (BrokerResponse response = call(
                Operation.REVOKE, tenantId, keyVersion, null, null)) {
            requireEmptyBody(response);
            requireEchoedKey(response, keyVersion);
            if (!KmsTenantEncryption.KeyState.REVOKED.name().equals(
                    response.singleHeader(HEADER_KEY_STATE))) {
                throw invalidResponse("revocation was not confirmed");
            }
        }
    }

    private BrokerResponse call(Operation operation, String tenantId,
                                KmsTenantEncryption.KeyVersion keyVersion,
                                byte[] context, byte[] wrappedKey)
            throws KmsTenantEncryption.ProviderException {
        String tenant = CasText.required(tenantId, "tenantId");
        byte[] requestBody = requestFrame(tenant, keyVersion, context, wrappedKey);
        Map<String, String> headers = Map.of(
                HEADER_PROTOCOL, PROTOCOL,
                HEADER_OPERATION, operation.path,
                HEADER_WORKLOAD_IDENTITY, config.identity().workloadIdentityHeader(),
                HEADER_MTLS_SECRET_REFERENCE,
                config.identity().mtlsCredentialReference().headerValue(),
                HEADER_AUTHORIZATION_REFERENCE,
                config.identity().authorizationPolicyReference().headerValue());
        URI requestUri = URI.create(config.endpoint().toASCIIString() + "/" + operation.path);
        try (BrokerRequest request = new BrokerRequest(
                operation, requestUri, config.operationTimeout(), headers, requestBody)) {
            BrokerResponse response;
            try {
                response = transport.exchange(request);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw providerFailure(KmsTenantEncryption.ProviderFailure.UNAVAILABLE,
                        "KMS broker request interrupted", null);
            } catch (IOException unavailable) {
                throw providerFailure(KmsTenantEncryption.ProviderFailure.UNAVAILABLE,
                        "KMS broker unavailable", null);
            } catch (RuntimeException unavailable) {
                throw providerFailure(KmsTenantEncryption.ProviderFailure.UNAVAILABLE,
                        "KMS broker transport failed", null);
            }
            if (response == null) {
                throw invalidResponse("missing response");
            }
            try {
                validateResponse(operation, requestUri, response);
                return response;
            } catch (KmsTenantEncryption.ProviderException invalid) {
                response.close();
                throw invalid;
            } catch (RuntimeException malformed) {
                response.close();
                throw invalidResponse("malformed response");
            }
        }
    }

    private static void validateResponse(Operation operation, URI requestUri,
                                         BrokerResponse response)
            throws KmsTenantEncryption.ProviderException {
        if (!requestUri.equals(response.responseUri())) {
            throw invalidResponse("redirected response URI");
        }
        if (response.bodyLength() > MAX_RESPONSE_BYTES) {
            throw invalidResponse("response body exceeds bound");
        }
        int status = response.statusCode();
        if (status != 200) {
            throw switch (status) {
                case 401, 403 -> providerFailure(
                        KmsTenantEncryption.ProviderFailure.PERMISSION_DENIED,
                        "KMS broker denied the workload identity", null);
                case 404 -> providerFailure(
                        KmsTenantEncryption.ProviderFailure.KEY_NOT_FOUND,
                        "KMS broker key not found", null);
                case 410 -> providerFailure(
                        KmsTenantEncryption.ProviderFailure.KEY_REVOKED,
                        "KMS broker key revoked", null);
                case 408, 425, 429, 500, 502, 503, 504 -> providerFailure(
                        KmsTenantEncryption.ProviderFailure.UNAVAILABLE,
                        "KMS broker unavailable", null);
                default -> invalidResponse("unexpected HTTP status");
            };
        }
        String contentType = response.singleHeader("Content-Type");
        int separator = contentType.indexOf(';');
        String mediaType = (separator < 0 ? contentType : contentType.substring(0, separator))
                .trim().toLowerCase(Locale.ROOT);
        if (!MEDIA_TYPE.equals(mediaType)) {
            throw invalidResponse("unexpected content type");
        }
        if (!PROTOCOL.equals(response.singleHeader(HEADER_PROTOCOL))) {
            throw invalidResponse("protocol version mismatch");
        }
        if (!operation.path.equals(response.singleHeader(HEADER_OPERATION))) {
            throw invalidResponse("operation binding mismatch");
        }
    }

    private static void requireContext(String tenantId,
                                       KmsTenantEncryption.KeyVersion keyVersion,
                                       KmsTenantEncryption.EncryptionContext context)
            throws KmsTenantEncryption.ProviderException {
        Objects.requireNonNull(keyVersion, "keyVersion");
        Objects.requireNonNull(context, "context");
        if (!CasText.required(tenantId, "tenantId").equals(context.tenantId())
                || !keyVersion.equals(context.keyVersion())) {
            throw providerFailure(KmsTenantEncryption.ProviderFailure.PERMISSION_DENIED,
                    "KMS encryption context does not match the requested subject", null);
        }
    }

    private static KmsTenantEncryption.KeyVersion responseKeyVersion(BrokerResponse response)
            throws KmsTenantEncryption.ProviderException {
        try {
            return new KmsTenantEncryption.KeyVersion(
                    response.singleHeader(HEADER_KEY_REFERENCE),
                    response.singleHeader(HEADER_KEY_VERSION));
        } catch (IllegalArgumentException invalidIdentity) {
            throw invalidResponse("invalid key identity");
        }
    }

    private static void requireEchoedKey(BrokerResponse response,
                                         KmsTenantEncryption.KeyVersion expected)
            throws KmsTenantEncryption.ProviderException {
        if (!expected.equals(responseKeyVersion(response))) {
            throw invalidResponse("key identity drift");
        }
    }

    private static void requireEmptyBody(BrokerResponse response)
            throws KmsTenantEncryption.ProviderException {
        if (response.bodyLength() != 0) {
            throw invalidResponse("unexpected response body");
        }
    }

    private static byte[] requestFrame(String tenantId,
                                       KmsTenantEncryption.KeyVersion keyVersion,
                                       byte[] context, byte[] wrappedKey) {
        byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
        byte[] reference = keyVersion == null ? new byte[0]
                : keyVersion.keyReference().getBytes(StandardCharsets.UTF_8);
        byte[] version = keyVersion == null ? new byte[0]
                : keyVersion.version().getBytes(StandardCharsets.UTF_8);
        byte[] contextBytes = context == null ? new byte[0] : context;
        byte[] wrapped = wrappedKey == null ? new byte[0] : wrappedKey;
        try {
            validateLength(tenant.length, 1, MAX_TENANT_BYTES, "tenantId");
            validateLength(reference.length, 0, MAX_KEY_REFERENCE_BYTES, "keyReference");
            validateLength(version.length, 0, MAX_KEY_VERSION_BYTES, "keyVersion");
            validateLength(contextBytes.length, 0, MAX_CONTEXT_BYTES, "context");
            validateLength(wrapped.length, 0, MAX_WRAPPED_KEY_BYTES, "wrappedKey");
            int length = REQUEST_MAGIC.length + Integer.BYTES * 5 + tenant.length
                    + reference.length + version.length + contextBytes.length + wrapped.length;
            ByteBuffer output = ByteBuffer.allocate(length);
            output.put(REQUEST_MAGIC);
            put(output, tenant);
            put(output, reference);
            put(output, version);
            put(output, contextBytes);
            put(output, wrapped);
            return output.array();
        } finally {
            Arrays.fill(tenant, (byte) 0);
            Arrays.fill(reference, (byte) 0);
            Arrays.fill(version, (byte) 0);
        }
    }

    private static void put(ByteBuffer output, byte[] value) {
        output.putInt(value.length);
        output.put(value);
    }

    private static int boundedFrameLength(ByteBuffer input, int minimum, int maximum,
                                          String name)
            throws KmsTenantEncryption.ProviderException {
        if (input.remaining() < Integer.BYTES) {
            throw invalidResponse("missing " + name + " length");
        }
        int length = input.getInt();
        if (length < minimum || length > maximum || length > input.remaining()) {
            throw invalidResponse("invalid " + name + " length");
        }
        return length;
    }

    private static byte[] take(ByteBuffer input, int length) {
        byte[] value = new byte[length];
        input.get(value);
        return value;
    }

    private static void validateLength(int length, int minimum, int maximum, String name) {
        if (length < minimum || length > maximum) {
            throw new IllegalArgumentException(name + " length is outside the protocol bound");
        }
    }

    private static URI validateEndpoint(URI endpoint) {
        URI value = Objects.requireNonNull(endpoint, "endpoint").normalize();
        if (!"https".equalsIgnoreCase(value.getScheme()) || value.getHost() == null
                || value.getUserInfo() != null || value.getRawQuery() != null
                || value.getRawFragment() != null || value.getRawPath() == null
                || value.getRawPath().endsWith("/")) {
            throw new IllegalArgumentException(
                    "KMS broker endpoint must be an exact HTTPS base URI without credentials, "
                            + "query, fragment or trailing slash");
        }
        if (value.getPort() == 0 || value.getPort() < -1 || value.getPort() > 65_535) {
            throw new IllegalArgumentException("KMS broker endpoint port is invalid");
        }
        return value;
    }

    private static URI validateSecretReference(URI reference) {
        URI value = Objects.requireNonNull(reference, "reference").normalize();
        if (!"secret".equalsIgnoreCase(value.getScheme()) || value.getHost() == null
                || value.getRawPath() == null || value.getRawPath().length() < 2
                || value.getUserInfo() != null || value.getRawQuery() != null
                || value.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "secret reference must be secret://<authority>/<path> without a value");
        }
        return value;
    }

    private static Duration boundedTimeout(Duration timeout, String name, Duration maximum) {
        Duration value = Objects.requireNonNull(timeout, name);
        if (value.isZero() || value.isNegative() || value.compareTo(maximum) > 0) {
            throw new IllegalArgumentException(name + " must be positive and no greater than "
                    + maximum);
        }
        return value;
    }

    private static KmsTenantEncryption.ProviderException invalidResponse(String detail) {
        return providerFailure(
                KmsTenantEncryption.ProviderFailure.INVALID_RESPONSE, detail, null);
    }

    private static KmsTenantEncryption.ProviderException providerFailure(
            KmsTenantEncryption.ProviderFailure failure, String message, Throwable cause) {
        if (cause == null) {
            return new KmsTenantEncryption.ProviderException(failure, message);
        }
        return new KmsTenantEncryption.ProviderException(failure, message, cause);
    }
}
