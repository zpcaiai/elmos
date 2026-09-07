package io.elmos.storage;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

/**
 * AWS Signature Version 4 query-string presigner.
 *
 * <p>Written against the JDK alone rather than pulling in an SDK. Two reasons:
 * the control plane must reach both AWS S3 and Alibaba Cloud OSS through the same
 * code path, and presigning is a closed, fully specified ~150-line algorithm whose
 * correctness can be pinned to the published test vector in
 * {@code SigV4PresignerTest}. An SDK would add a large transitive tree for one
 * function this service uses.</p>
 *
 * <p>Two flavours are implemented, and they are genuinely different algorithms
 * sharing one set of primitives:</p>
 *
 * <ul>
 *   <li>{@link #presign} produces a query-string signed URL. The control plane hands
 *       these to clients so it never has to stream object bytes itself.</li>
 *   <li>{@link #authorizationHeader} produces the {@code Authorization} header for a
 *       request this process makes directly. {@code modules/cas} needs it: a CAS tier
 *       does read and write bytes, over range reads and multipart uploads that a
 *       presigned URL cannot express.</li>
 * </ul>
 *
 * <p>The header flavour was added rather than duplicated. A second SigV4
 * implementation would mean a second RFC 3986 encoder, and the failure mode of the
 * two drifting apart is a signature that verifies locally and 403s in production.
 * The published AWS presign vector in {@code SigV4PresignerTest} pins the shared encoding and
 * signing primitives; the CAS tests additionally exercise the header flavour end to end against
 * a strict in-process S3 endpoint. That remains local engineering evidence, not a real-provider
 * certification.</p>
 */
public final class SigV4Presigner {

    private static final String ALGORITHM = "AWS4-HMAC-SHA256";
    private static final String SERVICE = "s3";
    private static final String TERMINATOR = "aws4_request";
    /** S3 presigned URLs sign the literal string UNSIGNED-PAYLOAD, not a body hash. */
    private static final String UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD";

    private static final DateTimeFormatter AMZ_DATE_TIME =
            DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC);
    private static final DateTimeFormatter AMZ_DATE =
            DateTimeFormatter.ofPattern("yyyyMMdd").withZone(ZoneOffset.UTC);

    public record Credentials(String accessKeyId, String secretAccessKey, String sessionToken) {
        public static Credentials of(String accessKeyId, String secretAccessKey) {
            return new Credentials(accessKeyId, secretAccessKey, null);
        }
    }

    private SigV4Presigner() {
    }

    /**
     * @param method       HTTP verb, for example GET or PUT
     * @param endpoint     scheme and host, for example https://oss-cn-beijing.aliyuncs.com
     * @param bucket       bucket name
     * @param key          object key, not yet URI-encoded
     * @param region       signing region
     * @param pathStyle    true for MinIO and most on-premise gateways, false for virtual-hosted
     * @param extraQuery   additional query parameters to sign, may be empty
     */
    public static URI presign(String method,
                              String endpoint,
                              String bucket,
                              String key,
                              String region,
                              boolean pathStyle,
                              Credentials credentials,
                              Instant signingTime,
                              Duration expiresIn,
                              Map<String, String> extraQuery) {

        long expiresSeconds = expiresIn.toSeconds();
        if (expiresSeconds < 1 || expiresSeconds > 604800) {
            // S3 caps presigned URL lifetime at seven days; the ELMOS policy caps
            // it far lower still (fifteen minutes, enforced in the database).
            throw new IllegalArgumentException("PRESIGN_EXPIRY_OUT_OF_RANGE");
        }

        URI base = URI.create(endpoint);
        String host = base.getHost();
        if (base.getPort() > 0) {
            host = host + ":" + base.getPort();
        }
        String canonicalUri;
        if (pathStyle) {
            canonicalUri = "/" + bucket + "/" + encodePath(key);
        } else {
            host = bucket + "." + host;
            canonicalUri = "/" + encodePath(key);
        }

        String amzDateTime = AMZ_DATE_TIME.format(signingTime);
        String amzDate = AMZ_DATE.format(signingTime);
        String scope = amzDate + "/" + region + "/" + SERVICE + "/" + TERMINATOR;

        // Query parameters must be sorted by encoded key; TreeMap over the already
        // encoded names gives exactly that ordering.
        TreeMap<String, String> query = new TreeMap<>();
        extraQuery.forEach((name, value) -> query.put(encode(name), encode(value)));
        query.put(encode("X-Amz-Algorithm"), encode(ALGORITHM));
        query.put(encode("X-Amz-Credential"), encode(credentials.accessKeyId() + "/" + scope));
        query.put(encode("X-Amz-Date"), encode(amzDateTime));
        query.put(encode("X-Amz-Expires"), encode(Long.toString(expiresSeconds)));
        query.put(encode("X-Amz-SignedHeaders"), encode("host"));
        if (credentials.sessionToken() != null && !credentials.sessionToken().isBlank()) {
            query.put(encode("X-Amz-Security-Token"), encode(credentials.sessionToken()));
        }

        String canonicalQuery = joinQuery(query);
        String canonicalHeaders = "host:" + host + "\n";
        String canonicalRequest = String.join("\n",
                method.toUpperCase(Locale.ROOT),
                canonicalUri,
                canonicalQuery,
                canonicalHeaders,
                "host",
                UNSIGNED_PAYLOAD);

        String stringToSign = String.join("\n",
                ALGORITHM,
                amzDateTime,
                scope,
                hex(sha256(canonicalRequest)));

        byte[] signingKey = signingKey(credentials.secretAccessKey(), amzDate, region);
        String signature = hex(hmac(signingKey, stringToSign));

        String url = base.getScheme() + "://" + host + canonicalUri + "?" + canonicalQuery
                + "&X-Amz-Signature=" + signature;
        return URI.create(url);
    }

    // ---- header signing ----------------------------------------------------

    /** SHA-256 of an empty body, the value S3 expects when there is no payload. */
    public static final String EMPTY_PAYLOAD_SHA256 =
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

    /** The {@code x-amz-date} value for an instant. */
    public static String amzDateTime(Instant signingTime) {
        return AMZ_DATE_TIME.format(signingTime);
    }

    public static String sha256Hex(byte[] payload) {
        try {
            return hex(MessageDigest.getInstance("SHA-256").digest(payload));
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    /**
     * Canonical form of a request path. Unlike {@link #encodePath}, which takes a bare
     * object key, this keeps a leading slash: the canonical URI of {@code /bucket/key}
     * is {@code /bucket/key}, and losing that slash silently changes the signature.
     */
    public static String canonicalUri(String path) {
        if (path == null || path.isEmpty() || path.equals("/")) {
            return "/";
        }
        boolean leadingSlash = path.charAt(0) == '/';
        String encoded = encodePath(leadingSlash ? path.substring(1) : path);
        return leadingSlash ? "/" + encoded : encoded;
    }

    /** Query parameters sorted by encoded name, as the canonical request requires. */
    public static String canonicalQuery(Map<String, String> parameters) {
        TreeMap<String, String> encoded = new TreeMap<>();
        parameters.forEach((name, value) -> encoded.put(encode(name), encode(value == null ? "" : value)));
        return joinQuery(encoded);
    }

    /**
     * Builds the {@code Authorization} header for a header-signed request.
     *
     * <p>Every entry of {@code headers} is signed, so adding a header after calling this
     * invalidates the request. {@code host}, {@code x-amz-date} and
     * {@code x-amz-content-sha256} must all be present.
     *
     * @param payloadSha256 hex SHA-256 of the exact body being sent, or
     *                      {@link #EMPTY_PAYLOAD_SHA256}. S3 rejects a mismatch, which is
     *                      the point: the signature covers the bytes, not just the intent.
     */
    public static String authorizationHeader(String method,
                                             String canonicalUri,
                                             String canonicalQuery,
                                             Map<String, String> headers,
                                             String payloadSha256,
                                             String region,
                                             Credentials credentials,
                                             Instant signingTime) {
        TreeMap<String, String> canonicalHeaders = new TreeMap<>();
        headers.forEach((name, value) -> canonicalHeaders.put(
                name.toLowerCase(Locale.ROOT), value.trim().replaceAll("\\s+", " ")));
        String signedHeaders = String.join(";", canonicalHeaders.keySet());

        StringBuilder headerBlock = new StringBuilder();
        canonicalHeaders.forEach((name, value) -> headerBlock.append(name).append(':').append(value).append('\n'));

        String amzDateTime = AMZ_DATE_TIME.format(signingTime);
        String amzDate = AMZ_DATE.format(signingTime);
        String scope = amzDate + "/" + region + "/" + SERVICE + "/" + TERMINATOR;

        String canonicalRequest = String.join("\n",
                method.toUpperCase(Locale.ROOT),
                canonicalUri,
                canonicalQuery,
                headerBlock.toString(),
                signedHeaders,
                payloadSha256);

        String stringToSign = String.join("\n",
                ALGORITHM,
                amzDateTime,
                scope,
                hex(sha256(canonicalRequest)));

        String signature = hex(hmac(signingKey(credentials.secretAccessKey(), amzDate, region), stringToSign));
        return ALGORITHM + " Credential=" + credentials.accessKeyId() + "/" + scope
                + ", SignedHeaders=" + signedHeaders
                + ", Signature=" + signature;
    }

    // ---- signing primitives ------------------------------------------------

    static byte[] signingKey(String secretAccessKey, String amzDate, String region) {
        byte[] key = ("AWS4" + secretAccessKey).getBytes(StandardCharsets.UTF_8);
        byte[] dateKey = hmac(key, amzDate);
        byte[] regionKey = hmac(dateKey, region);
        byte[] serviceKey = hmac(regionKey, SERVICE);
        return hmac(serviceKey, TERMINATOR);
    }

    static byte[] hmac(byte[] key, String data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            throw new IllegalStateException("HmacSHA256 unavailable", ex);
        }
    }

    static byte[] sha256(String data) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(data.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    static String hex(byte[] bytes) {
        return HexFormat.of().formatHex(bytes).toLowerCase(Locale.ROOT);
    }

    // ---- canonical encoding ------------------------------------------------

    private static String joinQuery(Map<String, String> encoded) {
        StringBuilder out = new StringBuilder();
        for (Map.Entry<String, String> entry : encoded.entrySet()) {
            if (out.length() > 0) {
                out.append('&');
            }
            out.append(entry.getKey()).append('=').append(entry.getValue());
        }
        return out.toString();
    }

    /** Path segments keep their separators; everything else is percent-encoded. */
    static String encodePath(String key) {
        StringBuilder out = new StringBuilder();
        for (String segment : key.split("/", -1)) {
            if (out.length() > 0) {
                out.append('/');
            }
            out.append(encode(segment));
        }
        return out.toString();
    }

    /**
     * RFC 3986 unreserved-set encoding.
     *
     * <p>{@code URLEncoder} cannot be used: it emits {@code +} for space and leaves
     * {@code *} and {@code ~} in forms AWS rejects, which produces signatures that
     * verify locally and fail in production - the worst kind of bug to debug.</p>
     */
    static String encode(String value) {
        StringBuilder out = new StringBuilder();
        for (byte b : value.getBytes(StandardCharsets.UTF_8)) {
            int c = b & 0xFF;
            if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')
                    || c == '-' || c == '_' || c == '.' || c == '~') {
                out.append((char) c);
            } else {
                out.append('%').append(String.format(Locale.ROOT, "%02X", c));
            }
        }
        return out.toString();
    }
}
