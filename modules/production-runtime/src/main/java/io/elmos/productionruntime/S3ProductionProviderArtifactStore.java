package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ArtifactRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;
import io.elmos.storage.S3ObjectStore;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;
import java.util.UUID;

/**
 * Content-addressed S3/MinIO response sink with server-side read-back
 * verification before PostgreSQL artifact publication.
 */
public final class S3ProductionProviderArtifactStore implements ProductionProviderArtifactPort {
    private final S3ObjectStore objects;
    private final ProductionRepositoryArtifactPort artifacts;
    private final String objectUriPrefix;
    private final HttpClient http;

    public S3ProductionProviderArtifactStore(
            S3ObjectStore objects,
            ProductionRepositoryArtifactPort artifacts,
            URI objectUriPrefix
    ) {
        this.objects = Objects.requireNonNull(objects, "objects");
        this.artifacts = Objects.requireNonNull(artifacts, "artifacts");
        URI prefix = Objects.requireNonNull(objectUriPrefix, "objectUriPrefix");
        String prefixPath = prefix.getPath();
        if (!("s3".equalsIgnoreCase(prefix.getScheme())
                || "https".equalsIgnoreCase(prefix.getScheme()))
                || prefix.getHost() == null || prefix.getUserInfo() != null
                || prefix.getQuery() != null || prefix.getFragment() != null
                || (prefixPath != null
                    && prefixPath.matches("(?:^|.*/)\\.\\.(?:/.*|$)"))) {
            throw new IllegalArgumentException(
                    "objectUriPrefix must be an absolute s3:// or https:// URI without credentials, query, fragments, or traversal");
        }
        this.objectUriPrefix = prefix.toString().replaceAll("/+$", "");
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public UUID store(
            ModelCallRequest request,
            String providerRequestId,
            byte[] responseBytes,
            String mediaType
    ) {
        Objects.requireNonNull(request, "request");
        ProductionRuntimeModels.requireText(providerRequestId, "providerRequestId", 500);
        Objects.requireNonNull(responseBytes, "responseBytes");
        if (responseBytes.length == 0) {
            throw new ProductionRuntimeException(
                    "PROVIDER_RESPONSE_EMPTY", "provider response artifact is empty");
        }
        String digest = JdbcProductionProviderPayloadStore.sha256(responseBytes);
        String organization = request.tenantId().toString();
        S3ObjectStore.UploadTicket ticket = objects.presignUpload(
                organization, digest, responseBytes.length, mediaType, Duration.ofMinutes(10));
        HttpRequest.Builder upload = HttpRequest.newBuilder(ticket.uploadUrl())
                .timeout(Duration.ofMinutes(15))
                .header("Content-Type", mediaType)
                .PUT(HttpRequest.BodyPublishers.ofByteArray(responseBytes));
        ticket.requiredHeaders().forEach(upload::header);
        try {
            HttpResponse<Void> response = http.send(
                    upload.build(), HttpResponse.BodyHandlers.discarding());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new ProductionRuntimeException(
                        "PROVIDER_RESPONSE_UPLOAD_FAILED",
                        "object storage rejected provider response upload");
            }
        } catch (IOException ex) {
            throw new ProductionRuntimeException(
                    "PROVIDER_RESPONSE_UPLOAD_UNKNOWN",
                    "provider response upload outcome is uncertain", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ProductionRuntimeException(
                    "PROVIDER_RESPONSE_UPLOAD_INTERRUPTED",
                    "provider response upload was interrupted", ex);
        }
        if (!objects.verifyUpload(
                organization, ticket.contentObjectId(), digest, responseBytes.length)) {
            throw new ProductionRuntimeException(
                    "PROVIDER_RESPONSE_VERIFICATION_FAILED",
                    "uploaded provider response failed digest verification");
        }
        String objectUri = objectUriPrefix + "/" + ticket.storageKey();
        return artifacts.registerArtifact(new ArtifactRequest(
                request.tenantId(), request.projectId(), request.jobId(), request.workItemId(),
                "MODEL_PROVIDER_RESPONSE", objectUri, digest, responseBytes.length));
    }
}
