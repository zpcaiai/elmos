package io.elmos.controlplane;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.HttpProductionModelProviderAdapter;
import io.elmos.productionruntime.JdbcProductionProviderPayloadStore;
import io.elmos.productionruntime.JdbcProductionObjectStorageMetadata;
import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import io.elmos.productionruntime.ProductionModelProviderPort;
import io.elmos.productionruntime.ProductionModelProviderRegistry;
import io.elmos.productionruntime.ProductionProviderArtifactPort;
import io.elmos.productionruntime.ProductionRepositoryArtifactPort;
import io.elmos.productionruntime.ProductionRuntimeException;
import io.elmos.productionruntime.S3ProductionProviderArtifactStore;
import io.elmos.storage.S3ObjectStore;
import io.elmos.storage.SigV4Presigner;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.IOException;
import java.net.InetAddress;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Clock;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/** Exact provider/model adapters and verified object-storage publication. */
@Configuration
@ConditionalOnProperty(
        prefix = "elmos.production-runtime.provider",
        name = "enabled",
        havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' == 'billing'")
class ProductionRuntimeProviderConfiguration {
    @Bean
    S3ObjectStore productionProviderObjectStore(
            JdbcClient jdbc,
            TransactionTemplate transactions,
            Clock clock,
            @Value("${elmos.production-runtime.provider.object-storage.backend-id}") String backendId,
            @Value("${elmos.production-runtime.provider.object-storage.endpoint}") URI endpoint,
            @Value("${elmos.production-runtime.provider.object-storage.bucket}") String bucket,
            @Value("${elmos.production-runtime.provider.object-storage.region}") String region,
            @Value("${elmos.production-runtime.provider.object-storage.path-style:false}") boolean pathStyle,
            @Value("${elmos.production-runtime.provider.object-storage.server-side-encryption:SSE_KMS}") String encryption,
            @Value("${elmos.production-runtime.provider.object-storage.cmk-reference:}") String cmkReference,
            @Value("${elmos.production-runtime.provider.object-storage.max-object-bytes:16777216}") long maxObjectBytes,
            @Value("${elmos.production-runtime.provider.object-storage.access-key-file}") Path accessKeyFile,
            @Value("${elmos.production-runtime.provider.object-storage.secret-key-file}") Path secretKeyFile,
            @Value("${elmos.production-runtime.provider.object-storage.session-token-file:}") String sessionTokenFile,
            @Value("${elmos.production-runtime.service-mesh-http:false}") boolean serviceMeshHttp
    ) {
        requireStorageEndpoint(endpoint, serviceMeshHttp);
        if (!backendId.matches("[A-Za-z0-9][A-Za-z0-9._-]{1,159}")) {
            throw new IllegalArgumentException("object storage backend id is invalid");
        }
        if (!bucket.matches("[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")
                || bucket.contains("..")) {
            throw new IllegalArgumentException("object storage bucket is invalid");
        }
        if (!region.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,99}")) {
            throw new IllegalArgumentException("object storage region is invalid");
        }
        if (!Set.of("SSE_S3", "SSE_KMS").contains(encryption)) {
            throw new IllegalArgumentException("provider response storage must enable server-side encryption");
        }
        if ("SSE_KMS".equals(encryption) && (cmkReference == null || cmkReference.isBlank())) {
            throw new IllegalArgumentException("SSE_KMS requires an exact CMK reference");
        }
        if (maxObjectBytes < 1 || maxObjectBytes > 5L * 1024 * 1024 * 1024) {
            throw new IllegalArgumentException("object storage maximum size is invalid");
        }
        String accessKey = new OwnerOnlyProviderCredentialFile(accessKeyFile).read();
        String secretKey = new OwnerOnlyProviderCredentialFile(secretKeyFile).read();
        String sessionToken = sessionTokenFile == null || sessionTokenFile.isBlank()
                ? null
                : new OwnerOnlyProviderCredentialFile(Path.of(sessionTokenFile)).read();
        if (accessKey.length() > 256 || secretKey.length() > 4096
                || (sessionToken != null && sessionToken.length() > 16_384)) {
            throw new IllegalArgumentException("object storage credential is malformed");
        }
        var backend = new S3ObjectStore.Backend(
                backendId, "ACTIVE", endpoint.toString(), bucket, region, pathStyle,
                encryption, "SSE_KMS".equals(encryption) ? cmkReference : "",
                maxObjectBytes,
                new SigV4Presigner.Credentials(accessKey, secretKey, sessionToken));
        return new S3ObjectStore(
                backend, new JdbcProductionObjectStorageMetadata(jdbc, transactions), clock);
    }

    @Bean
    ProductionProviderArtifactPort productionProviderArtifactPort(
            S3ObjectStore objects,
            ProductionRepositoryArtifactPort metadata,
            @Value("${elmos.production-runtime.provider.object-uri-prefix}") URI objectUriPrefix
    ) {
        return (request, providerRequestId, responseBytes, mediaType) ->
                new S3ProductionProviderArtifactStore(
                        objects, metadata, objectUriPrefix)
                        .store(request, providerRequestId, responseBytes, mediaType);
    }

    @Bean
    ProductionModelProviderRegistry productionModelProviderRegistry(
            @Value("${elmos.production-runtime.provider.profile-file}") Path profileFile,
            JdbcProductionProviderPayloadStore payloads,
            ProductionProviderArtifactPort artifacts,
            ObjectMapper json
    ) {
        if (Files.isSymbolicLink(profileFile) || !Files.isRegularFile(profileFile)) {
            throw new ProductionRuntimeException(
                    "PROVIDER_PROFILE_FILE_INVALID",
                    "provider profile file must be a regular non-symlink file");
        }
        try {
            JsonNode root = json.readTree(profileFile.toFile());
            if (root.path("schema_version").asInt() != 1 || !root.path("profiles").isArray()) {
                throw new ProductionRuntimeException(
                        "PROVIDER_PROFILE_FILE_INVALID", "provider profile schema is invalid");
            }
            Map<String, ProductionModelProviderPort> configured = new LinkedHashMap<>();
            for (JsonNode value : root.path("profiles")) {
                String provider = text(value, "provider", 80);
                String model = text(value, "model", 200);
                var protocol = HttpProductionModelProviderAdapter.Protocol.valueOf(
                        text(value, "protocol", 80));
                URI endpoint = URI.create(text(value, "endpoint", 2_000));
                Path credentialFile = Path.of(text(value, "credential_file", 2_000));
                int timeout = value.path("request_timeout_seconds").asInt(120);
                int maximum = value.path("max_response_bytes").asInt(8 * 1024 * 1024);
                var profile = new HttpProductionModelProviderAdapter.Profile(
                        provider, model, protocol, endpoint, Duration.ofSeconds(5),
                        Duration.ofSeconds(timeout), maximum, false);
                var adapter = new HttpProductionModelProviderAdapter(
                        profile, new OwnerOnlyProviderCredentialFile(credentialFile),
                        payloads, artifacts, json);
                String key = ProductionModelProviderRegistry.key(provider, model);
                if (configured.put(key, adapter) != null) {
                    throw new ProductionRuntimeException(
                            "PROVIDER_PROFILE_DUPLICATE",
                            "duplicate exact provider/model profile");
                }
            }
            return new ProductionModelProviderRegistry(configured);
        } catch (IOException | IllegalArgumentException ex) {
            if (ex instanceof ProductionRuntimeException runtime) throw runtime;
            throw new ProductionRuntimeException(
                    "PROVIDER_PROFILE_FILE_INVALID", "provider profile file cannot be parsed", ex);
        }
    }

    private static String text(JsonNode value, String field, int maximum) {
        String text = value.path(field).asText("");
        if (text.isBlank() || text.length() > maximum) {
            throw new ProductionRuntimeException(
                    "PROVIDER_PROFILE_FILE_INVALID", "provider profile field is invalid: " + field);
        }
        return text;
    }

    private static void requireStorageEndpoint(URI endpoint, boolean serviceMeshHttp) {
        if (endpoint == null || endpoint.getHost() == null || endpoint.getUserInfo() != null
                || endpoint.getQuery() != null || endpoint.getFragment() != null) {
            throw new IllegalArgumentException("object storage endpoint is malformed");
        }
        boolean secure = "https".equalsIgnoreCase(endpoint.getScheme());
        boolean mesh = "http".equalsIgnoreCase(endpoint.getScheme()) && serviceMeshHttp
                && (endpoint.getHost().endsWith(".svc")
                || endpoint.getHost().endsWith(".svc.cluster.local")
                || loopback(endpoint.getHost()));
        if (!secure && !mesh) {
            throw new IllegalArgumentException(
                    "object storage endpoint requires HTTPS or approved service-mesh HTTP");
        }
    }

    private static boolean loopback(String host) {
        try {
            return InetAddress.getByName(host).isLoopbackAddress();
        } catch (Exception ignored) {
            return false;
        }
    }
}
