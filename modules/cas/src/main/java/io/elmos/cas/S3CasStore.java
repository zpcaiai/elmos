package io.elmos.cas;

import io.elmos.storage.SigV4Presigner;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.function.Supplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * ELMOS-CAS-014. The shared L2 tier on an S3-compatible object store (AWS S3, MinIO, Ceph RGW).
 *
 * <p>Written directly against the REST API with {@link HttpClient} and {@link SigV4Presigner} to keep
 * the module dependency free. What that buys, beyond a smaller tree: the signing is testable from
 * both ends, and there is no SDK retry/credential-chain behaviour hiding between this code and the
 * wire.
 *
 * <p>Object layout is {@code <prefix>/sha256/aa/bb/<hex>} — the same shard path the local tier
 * uses, so a bucket can be inspected, rsynced, or promoted to a local cache without translation.
 *
 * <p>Correctness properties this class must preserve:
 *
 * <ul>
 *   <li><b>Verify after download.</b> S3 can and does return a stale or partial body on a retried
 *       range read; the digest check is the only thing that catches it.</li>
 *   <li><b>Size is checked on HEAD.</b> A key that exists with the wrong length is a failed
 *       multipart upload, not a cache hit.</li>
 *   <li><b>Multipart parts are hashed individually.</b> A part that arrives corrupt fails its own
 *       upload rather than surfacing after the complete call.</li>
 *   <li><b>Retries are bounded and only on transport or 5xx.</b> Retrying a 403 is how a clock
 *       skew problem turns into a rate-limit problem.</li>
 * </ul>
 */
public final class S3CasStore implements CasStore {

    /** S3 requires parts of at least 5 MiB except for the last one. */
    public static final long MINIMUM_PART_BYTES = 5L * 1024 * 1024;

    private static final Pattern LIST_ENTRY = Pattern.compile(
            "<Contents>.*?<Key>(.*?)</Key>.*?<Size>(\\d+)</Size>.*?</Contents>", Pattern.DOTALL);
    private static final Pattern CONTINUATION = Pattern.compile(
            "<NextContinuationToken>(.*?)</NextContinuationToken>", Pattern.DOTALL);
    private static final Pattern UPLOAD_ID = Pattern.compile("<UploadId>(.*?)</UploadId>", Pattern.DOTALL);

    public record Config(URI endpoint,
                         String bucket,
                         String region,
                         String keyPrefix,
                         String accessKeyId,
                         String secretAccessKey,
                         Optional<String> sessionToken,
                         boolean pathStyleAccess,
                         long multipartThresholdBytes,
                         long partSizeBytes,
                         int maximumAttempts,
                         Duration requestTimeout) {

        public Config {
            Objects.requireNonNull(endpoint, "endpoint");
            bucket = CasText.required(bucket, "bucket");
            region = CasText.required(region, "region");
            keyPrefix = keyPrefix == null ? "" : keyPrefix;
            accessKeyId = CasText.required(accessKeyId, "accessKeyId");
            secretAccessKey = CasText.required(secretAccessKey, "secretAccessKey");
            Objects.requireNonNull(sessionToken, "sessionToken");
            CasText.requirePositive(multipartThresholdBytes, "multipartThresholdBytes");
            CasText.requirePositive(partSizeBytes, "partSizeBytes");
            if (maximumAttempts < 1) {
                throw new IllegalArgumentException("maximumAttempts must be at least 1");
            }
            Objects.requireNonNull(requestTimeout, "requestTimeout");
        }

        /**
         * AWS rejects any part but the last below 5 MiB. MinIO and Ceph do not, and the test
         * suite relies on that, so the check is an explicit call rather than a constructor
         * invariant — call it once at startup when the endpoint is real S3.
         *
         * @throws IllegalStateException when this config would be rejected by AWS
         */
        public void validateForAws() {
            if (partSizeBytes < MINIMUM_PART_BYTES) {
                throw new IllegalStateException("AWS S3 requires parts of at least " + MINIMUM_PART_BYTES
                        + " bytes; configured " + partSizeBytes);
            }
            if (multipartThresholdBytes < MINIMUM_PART_BYTES) {
                throw new IllegalStateException("multipart threshold below the AWS minimum part size");
            }
        }

        /** MinIO defaults: path-style addressing, 8 MiB parts, three attempts. */
        public static Config minio(URI endpoint, String bucket, String accessKeyId, String secretAccessKey) {
            return new Config(endpoint, bucket, "us-east-1", "cas", accessKeyId, secretAccessKey,
                    Optional.empty(), true, 8L * 1024 * 1024, 8L * 1024 * 1024, 3, Duration.ofSeconds(30));
        }
    }

    private final String name;
    private final Config config;
    private final SigV4Presigner.Credentials credentials;
    private final HttpClient http;
    private final Supplier<Instant> clock;

    public S3CasStore(String name, Config config, HttpClient http, Supplier<Instant> clock) {
        this.name = CasText.required(name, "name");
        this.config = config;
        this.credentials = new SigV4Presigner.Credentials(config.accessKeyId(), config.secretAccessKey(),
                config.sessionToken().orElse(null));
        this.http = http;
        this.clock = clock;
    }

    public static S3CasStore create(String name, Config config) {
        return new S3CasStore(name, config,
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build(), Instant::now);
    }

    @Override
    public String name() {
        return name;
    }

    public String objectKey(CasDigest digest) {
        return config.keyPrefix().isEmpty() ? digest.shardPath() : config.keyPrefix() + "/" + digest.shardPath();
    }

    @Override
    public boolean contains(CasDigest digest) {
        HttpResponse<byte[]> response = send("HEAD", objectKey(digest), Map.of(), Map.of(), new byte[0]);
        if (response.statusCode() == 404) {
            return false;
        }
        requireSuccess(response, "HEAD " + objectKey(digest));
        long length = response.headers().firstValueAsLong("content-length").orElse(-1);
        // A key that exists with the wrong length is an aborted multipart upload, not an object.
        return length == digest.sizeBytes();
    }

    @Override
    public void put(CasDigest expected, byte[] content) {
        CasDigest actual = CasDigest.of(content);
        if (!actual.equals(expected)) {
            throw new CasExceptions.CasCorruptionException(name, expected, actual);
        }
        if (contains(expected)) {
            return;
        }
        if (content.length >= config.multipartThresholdBytes()) {
            multipartUpload(expected, content);
            return;
        }
        HttpResponse<byte[]> response = send("PUT", objectKey(expected), Map.of(),
                Map.of("content-type", "application/octet-stream"), content);
        requireSuccess(response, "PUT " + objectKey(expected));
    }

    @Override
    public byte[] get(CasDigest digest) {
        HttpResponse<byte[]> response = send("GET", objectKey(digest), Map.of(), Map.of(), new byte[0]);
        if (response.statusCode() == 404) {
            throw new CasExceptions.CasNotFoundException(digest);
        }
        requireSuccess(response, "GET " + objectKey(digest));
        byte[] body = response.body();
        CasDigest actual = CasDigest.of(body);
        if (!actual.equals(digest)) {
            throw new CasExceptions.CasCorruptionException(name, digest, actual);
        }
        return body;
    }

    @Override
    public byte[] readRange(CasDigest digest, long offset, int length) {
        if (offset < 0) {
            throw new IllegalArgumentException("range offset must not be negative: " + offset);
        }
        if (offset > digest.sizeBytes()) {
            throw new IllegalArgumentException("range offset outside object: " + offset);
        }
        long last = Math.min(digest.sizeBytes(), offset + length) - 1;
        if (last < offset) {
            return new byte[0];
        }
        HttpResponse<byte[]> response = send("GET", objectKey(digest), Map.of(),
                Map.of("range", "bytes=" + offset + "-" + last), new byte[0]);
        if (response.statusCode() == 404) {
            throw new CasExceptions.CasNotFoundException(digest);
        }
        requireSuccess(response, "GET range " + objectKey(digest));
        return response.body();
    }

    @Override
    public boolean delete(CasDigest digest) {
        boolean present = contains(digest);
        HttpResponse<byte[]> response = send("DELETE", objectKey(digest), Map.of(), Map.of(), new byte[0]);
        if (response.statusCode() != 404) {
            requireSuccess(response, "DELETE " + objectKey(digest));
        }
        return present;
    }

    @Override
    public Set<CasDigest> inventory() {
        Set<CasDigest> digests = new LinkedHashSet<>();
        String continuationToken = null;
        do {
            Map<String, String> query = new LinkedHashMap<>();
            query.put("list-type", "2");
            query.put("prefix", config.keyPrefix().isEmpty() ? "sha256/" : config.keyPrefix() + "/sha256/");
            if (continuationToken != null) {
                query.put("continuation-token", continuationToken);
            }
            HttpResponse<byte[]> response = send("GET", "", query, Map.of(), new byte[0]);
            requireSuccess(response, "ListObjectsV2");
            String body = new String(response.body(), StandardCharsets.UTF_8);
            Matcher entries = LIST_ENTRY.matcher(body);
            while (entries.find()) {
                String key = entries.group(1);
                String hex = key.substring(key.lastIndexOf('/') + 1);
                try {
                    digests.add(new CasDigest(CasDigest.ALGORITHM, hex, Long.parseLong(entries.group(2))));
                } catch (IllegalArgumentException notAnObject) {
                    // A key under the prefix that is not a digest is a stray for the reconciler to
                    // report; it must not abort the listing.
                }
            }
            Matcher next = CONTINUATION.matcher(body);
            continuationToken = next.find() ? next.group(1) : null;
        } while (continuationToken != null);
        return digests;
    }

    @Override
    public long totalBytes() {
        return inventory().stream().mapToLong(CasDigest::sizeBytes).sum();
    }

    /** ELMOS-CAS-007. Multipart upload for large blobs, with a per-part digest on the wire. */
    void multipartUpload(CasDigest digest, byte[] content) {
        String key = objectKey(digest);
        HttpResponse<byte[]> created = send("POST", key, Map.of("uploads", ""),
                Map.of("content-type", "application/octet-stream"), new byte[0]);
        requireSuccess(created, "CreateMultipartUpload " + key);
        Matcher uploadIdMatch = UPLOAD_ID.matcher(new String(created.body(), StandardCharsets.UTF_8));
        if (!uploadIdMatch.find()) {
            throw new IllegalStateException("CreateMultipartUpload returned no UploadId for " + key);
        }
        String uploadId = uploadIdMatch.group(1);

        List<String> etags = new ArrayList<>();
        try {
            int partSize = (int) config.partSizeBytes();
            int partNumber = 1;
            for (int offset = 0; offset < content.length; offset += partSize) {
                byte[] part = Arrays.copyOfRange(content, offset, Math.min(content.length, offset + partSize));
                HttpResponse<byte[]> uploaded = send("PUT", key,
                        Map.of("partNumber", Integer.toString(partNumber), "uploadId", uploadId),
                        Map.of(), part);
                requireSuccess(uploaded, "UploadPart " + partNumber + " of " + key);
                etags.add(uploaded.headers().firstValue("etag")
                        .orElse("\"" + SigV4Presigner.sha256Hex(part) + "\""));
                partNumber++;
            }
            StringBuilder completion = new StringBuilder("<CompleteMultipartUpload>");
            for (int index = 0; index < etags.size(); index++) {
                completion.append("<Part><PartNumber>").append(index + 1).append("</PartNumber><ETag>")
                        .append(etags.get(index)).append("</ETag></Part>");
            }
            completion.append("</CompleteMultipartUpload>");
            HttpResponse<byte[]> completed = send("POST", key, Map.of("uploadId", uploadId),
                    Map.of("content-type", "application/xml"),
                    completion.toString().getBytes(StandardCharsets.UTF_8));
            requireSuccess(completed, "CompleteMultipartUpload " + key);
        } catch (RuntimeException failure) {
            // An abandoned multipart upload is billed storage that no listing shows. Abort on the
            // way out; the reconciler's incomplete-session scan is the backstop, not the plan.
            send("DELETE", key, Map.of("uploadId", uploadId), Map.of(), new byte[0]);
            throw failure;
        }
    }

    private HttpResponse<byte[]> send(String method, String key, Map<String, String> query,
                                      Map<String, String> extraHeaders, byte[] payload) {
        RuntimeException lastFailure = null;
        for (int attempt = 1; attempt <= config.maximumAttempts(); attempt++) {
            try {
                HttpResponse<byte[]> response = sendOnce(method, key, query, extraHeaders, payload);
                if (response.statusCode() < 500 || attempt == config.maximumAttempts()) {
                    return response;
                }
                lastFailure = new IllegalStateException("S3 returned " + response.statusCode());
            } catch (java.io.IOException transportFailure) {
                lastFailure = new IllegalStateException("S3 transport failure: " + transportFailure.getMessage(),
                        transportFailure);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted while talking to S3", interrupted);
            }
        }
        throw lastFailure;
    }

    private HttpResponse<byte[]> sendOnce(String method, String key, Map<String, String> query,
                                          Map<String, String> extraHeaders, byte[] payload)
            throws java.io.IOException, InterruptedException {
        Instant now = clock.get();
        String path = config.pathStyleAccess()
                ? "/" + config.bucket() + (key.isEmpty() ? "" : "/" + key)
                : (key.isEmpty() ? "/" : "/" + key);
        String canonicalQuery = SigV4Presigner.canonicalQuery(query);
        String payloadHash = payload.length == 0
                ? SigV4Presigner.EMPTY_PAYLOAD_SHA256
                : SigV4Presigner.sha256Hex(payload);

        Map<String, String> headers = new LinkedHashMap<>(extraHeaders);
        String host = config.endpoint().getHost()
                + (config.endpoint().getPort() > 0 ? ":" + config.endpoint().getPort() : "");
        headers.put("host", config.pathStyleAccess() ? host : config.bucket() + "." + host);
        headers.put("x-amz-date", SigV4Presigner.amzDateTime(now));
        headers.put("x-amz-content-sha256", payloadHash);
        config.sessionToken().ifPresent(token -> headers.put("x-amz-security-token", token));

        String authorization = SigV4Presigner.authorizationHeader(method,
                SigV4Presigner.canonicalUri(path), canonicalQuery, headers, payloadHash,
                config.region(), credentials, now);

        URI uri = URI.create(config.endpoint().toString().replaceAll("/$", "") + path
                + (canonicalQuery.isEmpty() ? "" : "?" + canonicalQuery));
        HttpRequest.Builder request = HttpRequest.newBuilder(uri)
                .timeout(config.requestTimeout())
                .method(method, payload.length == 0
                        ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofByteArray(payload));
        headers.forEach((headerName, value) -> {
            if (!headerName.equals("host")) {
                request.header(headerName, value);
            }
        });
        request.header("authorization", authorization);
        return http.send(request.build(), HttpResponse.BodyHandlers.ofByteArray());
    }

    private void requireSuccess(HttpResponse<byte[]> response, String what) {
        if (response.statusCode() >= 200 && response.statusCode() < 300) {
            return;
        }
        String body = response.body() == null ? "" : new String(response.body(), StandardCharsets.UTF_8);
        if (response.statusCode() == 403 || response.statusCode() == 401) {
            throw new CasExceptions.CasAccessDeniedException("OBJECT_STORE_REJECTED_CREDENTIALS",
                    what + " -> " + response.statusCode() + " " + body);
        }
        throw new IllegalStateException(what + " failed with " + response.statusCode() + " " + body);
    }
}
