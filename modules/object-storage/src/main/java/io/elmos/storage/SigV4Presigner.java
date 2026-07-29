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
 * <p>Only the query-string (presigned URL) flavour is implemented. The control
 * plane never streams object bytes itself, so header-based signing is not needed
 * and is deliberately absent rather than half-built.</p>
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
