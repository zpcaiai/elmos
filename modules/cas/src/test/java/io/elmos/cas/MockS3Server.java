package io.elmos.cas;

import io.elmos.storage.SigV4Presigner;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * An in-process S3-compatible endpoint, used to exercise {@link S3CasStore} end to end.
 *
 * <p>It is not a fake in the usual sense: it <b>recomputes the SigV4 signature</b> with the same
 * {@link SigV4Presigner} the client used and rejects the request with 403 if it does not match. That
 * is what makes the signing code actually tested — a canonicalisation bug fails here rather than
 * silently working against a mock that ignores the Authorization header and then 403-ing against
 * a real bucket.
 *
 * <p>Implements the subset the store uses: HEAD/GET (incl. Range)/PUT/DELETE on objects,
 * ListObjectsV2 with continuation, and the three multipart calls.
 */
final class MockS3Server implements AutoCloseable {

    /**
     * The JDK server warns on every HEAD response that carries a Content-Length, which an S3
     * response must. The strong references are load bearing: java.util.logging holds its loggers
     * weakly, so a level set on a logger nobody keeps is collected and silently reverts to the
     * parent's - which is why the warnings came back on a machine with different GC timing.
     */
    private static final java.util.logging.Logger[] SILENCED = {
            java.util.logging.Logger.getLogger("sun.net.httpserver"),
            java.util.logging.Logger.getLogger("sun.net.httpserver.ExchangeImpl"),
            java.util.logging.Logger.getLogger("com.sun.net.httpserver")
    };

    static {
        for (java.util.logging.Logger logger : SILENCED) {
            logger.setLevel(java.util.logging.Level.OFF);
            logger.setUseParentHandlers(false);
        }
    }

    private static final DateTimeFormatter AMZ_DATE =
            DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC);

    private final HttpServer server;
    private final String bucket;
    private final SigV4Presigner.Credentials credentials;
    private final String region;
    private final Map<String, byte[]> objects = new LinkedHashMap<>();
    private final Map<String, Map<Integer, byte[]>> multipart = new LinkedHashMap<>();
    private final List<String> abortedUploads = new ArrayList<>();
    private final AtomicInteger uploadCounter = new AtomicInteger();
    private final AtomicInteger requestCount = new AtomicInteger();
    private final AtomicInteger signatureRejections = new AtomicInteger();

    private int maxKeysPerPage = 1000;
    private int failNextRequests;
    private int failNextPartUploads;
    private String corruptOnGetKey;

    MockS3Server(String bucket, String accessKeyId, String secretAccessKey, String region) throws IOException {
        this.bucket = bucket;
        this.credentials = SigV4Presigner.Credentials.of(accessKeyId, secretAccessKey);
        this.region = region;
        this.server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        this.server.createContext("/", this::handle);
        this.server.start();
    }

    URI endpoint() {
        return URI.create("http://127.0.0.1:" + server.getAddress().getPort());
    }

    int requestCount() {
        return requestCount.get();
    }

    int signatureRejections() {
        return signatureRejections.get();
    }

    void failNextRequests(int count) {
        this.failNextRequests = count;
    }

    /** Fails only UploadPart calls, so CreateMultipartUpload succeeds and an upload is left open. */
    void failNextPartUploads(int count) {
        this.failNextPartUploads = count;
    }

    void corruptOnGet(String key) {
        this.corruptOnGetKey = key;
    }

    void maxKeysPerPage(int maxKeys) {
        this.maxKeysPerPage = maxKeys;
    }

    Map<String, byte[]> objects() {
        return objects;
    }

    List<String> abortedUploads() {
        return abortedUploads;
    }

    void putDirectly(String key, byte[] content) {
        objects.put(key, content.clone());
    }

    @Override
    public void close() {
        server.stop(0);
    }

    private void handle(HttpExchange exchange) throws IOException {
        requestCount.incrementAndGet();
        try {
            boolean isPartUpload = exchange.getRequestMethod().equals("PUT")
                    && String.valueOf(exchange.getRequestURI().getRawQuery()).contains("partNumber");
            if (failNextPartUploads > 0 && isPartUpload) {
                failNextPartUploads--;
                respond(exchange, 503, "<Error><Code>SlowDown</Code></Error>".getBytes(StandardCharsets.UTF_8));
                return;
            }
            if (failNextRequests > 0) {
                failNextRequests--;
                respond(exchange, 503, "<Error><Code>SlowDown</Code></Error>".getBytes(StandardCharsets.UTF_8));
                return;
            }
            if (!signatureMatches(exchange)) {
                signatureRejections.incrementAndGet();
                respond(exchange, 403, "<Error><Code>SignatureDoesNotMatch</Code></Error>"
                        .getBytes(StandardCharsets.UTF_8));
                return;
            }
            route(exchange);
        } catch (RuntimeException error) {
            respond(exchange, 500, ("<Error><Code>Mock</Code><Message>" + error + "</Message></Error>")
                    .getBytes(StandardCharsets.UTF_8));
        }
    }

    private void route(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        Map<String, String> query = parseQuery(exchange.getRequestURI().getRawQuery());
        String method = exchange.getRequestMethod();
        String prefixToStrip = "/" + bucket;
        if (!path.startsWith(prefixToStrip)) {
            respond(exchange, 404, new byte[0]);
            return;
        }
        String key = path.length() > prefixToStrip.length() ? path.substring(prefixToStrip.length() + 1) : "";

        if (key.isEmpty() && "2".equals(query.get("list-type"))) {
            listObjects(exchange, query);
            return;
        }
        if (method.equals("POST") && query.containsKey("uploads")) {
            String uploadId = "upload-" + uploadCounter.incrementAndGet();
            multipart.put(uploadId, new TreeMap<>());
            respond(exchange, 200, ("<InitiateMultipartUploadResult><Bucket>" + bucket + "</Bucket><Key>" + key
                    + "</Key><UploadId>" + uploadId + "</UploadId></InitiateMultipartUploadResult>")
                    .getBytes(StandardCharsets.UTF_8));
            return;
        }
        if (method.equals("PUT") && query.containsKey("uploadId")) {
            byte[] part = exchange.getRequestBody().readAllBytes();
            multipart.get(query.get("uploadId")).put(Integer.parseInt(query.get("partNumber")), part);
            exchange.getResponseHeaders().add("ETag", "\"" + SigV4Presigner.sha256Hex(part) + "\"");
            respond(exchange, 200, new byte[0]);
            return;
        }
        if (method.equals("POST") && query.containsKey("uploadId")) {
            Map<Integer, byte[]> parts = multipart.remove(query.get("uploadId"));
            byte[] assembled = new byte[parts.values().stream().mapToInt(part -> part.length).sum()];
            int offset = 0;
            for (byte[] part : parts.values()) {
                System.arraycopy(part, 0, assembled, offset, part.length);
                offset += part.length;
            }
            objects.put(key, assembled);
            respond(exchange, 200, ("<CompleteMultipartUploadResult><Key>" + key + "</Key>"
                    + "</CompleteMultipartUploadResult>").getBytes(StandardCharsets.UTF_8));
            return;
        }
        if (method.equals("DELETE") && query.containsKey("uploadId")) {
            multipart.remove(query.get("uploadId"));
            abortedUploads.add(query.get("uploadId"));
            respond(exchange, 204, new byte[0]);
            return;
        }

        byte[] stored = objects.get(key);
        switch (method) {
            case "HEAD" -> {
                if (stored == null) {
                    respond(exchange, 404, new byte[0]);
                } else {
                    exchange.getResponseHeaders().add("Content-Length", Integer.toString(stored.length));
                    exchange.sendResponseHeaders(200, -1);
                    exchange.close();
                }
            }
            case "GET" -> {
                if (stored == null) {
                    respond(exchange, 404, new byte[0]);
                    return;
                }
                byte[] body = key.equals(corruptOnGetKey)
                        ? "corrupted-by-the-object-store".getBytes(StandardCharsets.UTF_8)
                        : stored;
                String range = firstHeader(exchange, "range");
                if (range != null && range.startsWith("bytes=")) {
                    String[] bounds = range.substring("bytes=".length()).split("-");
                    int from = Integer.parseInt(bounds[0]);
                    int to = Math.min(body.length - 1, Integer.parseInt(bounds[1]));
                    respond(exchange, 206, Arrays.copyOfRange(body, from, to + 1));
                } else {
                    respond(exchange, 200, body);
                }
            }
            case "PUT" -> {
                objects.put(key, exchange.getRequestBody().readAllBytes());
                respond(exchange, 200, new byte[0]);
            }
            case "DELETE" -> {
                objects.remove(key);
                respond(exchange, 204, new byte[0]);
            }
            default -> respond(exchange, 405, new byte[0]);
        }
    }

    private void listObjects(HttpExchange exchange, Map<String, String> query) throws IOException {
        String prefix = query.getOrDefault("prefix", "");
        List<String> keys = objects.keySet().stream().filter(key -> key.startsWith(prefix)).sorted().toList();
        int from = 0;
        String token = query.get("continuation-token");
        if (token != null) {
            from = Integer.parseInt(token);
        }
        int to = Math.min(keys.size(), from + maxKeysPerPage);
        StringBuilder xml = new StringBuilder("<ListBucketResult>");
        for (String key : keys.subList(from, to)) {
            xml.append("<Contents><Key>").append(key).append("</Key><Size>")
                    .append(objects.get(key).length).append("</Size></Contents>");
        }
        if (to < keys.size()) {
            xml.append("<NextContinuationToken>").append(to).append("</NextContinuationToken>");
        }
        xml.append("</ListBucketResult>");
        respond(exchange, 200, xml.toString().getBytes(StandardCharsets.UTF_8));
    }

    private boolean signatureMatches(HttpExchange exchange) {
        String authorization = firstHeader(exchange, "authorization");
        if (authorization == null || !authorization.startsWith("AWS4-HMAC-SHA256")) {
            return false;
        }
        String signedHeaders = extract(authorization, "SignedHeaders=", ",");
        String amzDate = firstHeader(exchange, "x-amz-date");
        String contentSha = firstHeader(exchange, "x-amz-content-sha256");
        if (signedHeaders == null || amzDate == null || contentSha == null) {
            return false;
        }
        Map<String, String> headers = new LinkedHashMap<>();
        for (String name : signedHeaders.split(";")) {
            String value = firstHeader(exchange, name);
            if (value == null) {
                return false;
            }
            headers.put(name, value);
        }
        String expected = SigV4Presigner.authorizationHeader(exchange.getRequestMethod(),
                SigV4Presigner.canonicalUri(exchange.getRequestURI().getPath()),
                canonicalize(exchange.getRequestURI().getRawQuery()),
                headers, contentSha, region, credentials, Instant.from(AMZ_DATE.parse(amzDate)));
        return expected.equals(authorization);
    }

    private static String canonicalize(String rawQuery) {
        return SigV4Presigner.canonicalQuery(parseQuery(rawQuery));
    }

    private static Map<String, String> parseQuery(String rawQuery) {
        Map<String, String> parameters = new LinkedHashMap<>();
        if (rawQuery == null || rawQuery.isEmpty()) {
            return parameters;
        }
        for (String pair : rawQuery.split("&")) {
            int equals = pair.indexOf('=');
            String name = equals < 0 ? pair : pair.substring(0, equals);
            String value = equals < 0 ? "" : pair.substring(equals + 1);
            parameters.put(java.net.URLDecoder.decode(name, StandardCharsets.UTF_8),
                    java.net.URLDecoder.decode(value, StandardCharsets.UTF_8));
        }
        return parameters;
    }

    private static String extract(String source, String prefix, String terminator) {
        int start = source.indexOf(prefix);
        if (start < 0) {
            return null;
        }
        start += prefix.length();
        int end = source.indexOf(terminator, start);
        return end < 0 ? source.substring(start) : source.substring(start, end);
    }

    private static String firstHeader(HttpExchange exchange, String name) {
        for (Map.Entry<String, List<String>> header : exchange.getRequestHeaders().entrySet()) {
            if (header.getKey().equalsIgnoreCase(name)) {
                return header.getValue().get(0);
            }
        }
        return null;
    }

    private static void respond(HttpExchange exchange, int status, byte[] body) throws IOException {
        exchange.sendResponseHeaders(status, body.length == 0 ? -1 : body.length);
        if (body.length > 0) {
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        }
        exchange.close();
    }
}
