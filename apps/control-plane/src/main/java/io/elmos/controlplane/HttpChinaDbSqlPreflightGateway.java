package io.elmos.controlplane;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

import static io.elmos.controlplane.ChinaDbSqlPreflightFailure.Kind.PROTOCOL_ERROR;
import static io.elmos.controlplane.ChinaDbSqlPreflightFailure.Kind.REQUEST_REJECTED;
import static io.elmos.controlplane.ChinaDbSqlPreflightFailure.Kind.REQUEST_TOO_LARGE;
import static io.elmos.controlplane.ChinaDbSqlPreflightFailure.Kind.UNAVAILABLE;

/** Fixed-destination, bounded HTTP client for the database-data worker. */
final class HttpChinaDbSqlPreflightGateway implements ChinaDbSqlPreflightGateway {
    private static final Pattern ORGANIZATION = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private static final Pattern ACTOR = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}");

    private final URI capabilitiesUri;
    private final URI assessUri;
    private final Duration requestTimeout;
    private final ObjectMapper json;
    private final ChinaDbSqlPreflightProtocol protocol;
    private final HttpClient client;

    HttpChinaDbSqlPreflightGateway(
            boolean enabled,
            String baseUrl,
            Duration connectTimeout,
            Duration requestTimeout,
            ObjectMapper json
    ) {
        this.json = Objects.requireNonNull(json);
        this.protocol = new ChinaDbSqlPreflightProtocol(json);
        this.requestTimeout = boundedTimeout(requestTimeout, Duration.ofSeconds(60));
        Duration connect = boundedTimeout(connectTimeout, Duration.ofSeconds(30));
        this.client = HttpClient.newBuilder()
                .connectTimeout(connect)
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        URI base = enabled && baseUrl != null && !baseUrl.isBlank() ? safeBase(baseUrl) : null;
        this.capabilitiesUri = base == null ? null : base.resolve("engine/v1/sql-preflight/capabilities");
        this.assessUri = base == null ? null : base.resolve("engine/v1/sql-preflight/assess");
    }

    @Override
    public JsonNode capabilities() {
        return protocol.capabilities(call(capabilitiesUri, null, null, null));
    }

    @Override
    public JsonNode assess(byte[] request, String organizationId, String actorId) {
        JsonNode parsed = protocol.request(request);
        if (!ORGANIZATION.matcher(Objects.requireNonNullElse(organizationId, "")).matches()
                || !ACTOR.matcher(Objects.requireNonNullElse(actorId, "")).matches()) {
            throw new ChinaDbSqlPreflightFailure(REQUEST_REJECTED);
        }
        return protocol.assessment(parsed, call(assessUri, request, organizationId, actorId));
    }

    private JsonNode call(URI uri, byte[] body, String organizationId, String actorId) {
        if (uri == null) throw new ChinaDbSqlPreflightFailure(UNAVAILABLE);
        HttpRequest.Builder request = HttpRequest.newBuilder(uri)
                .timeout(requestTimeout)
                .header("Accept", "application/json");
        if (body == null) {
            request.GET();
        } else {
            if (body.length > ChinaDbSqlPreflightProtocol.MAX_REQUEST_BYTES) {
                throw new ChinaDbSqlPreflightFailure(REQUEST_TOO_LARGE);
            }
            request.header("Content-Type", "application/json")
                    .header("X-ELMOS-Organization-ID", organizationId)
                    .header("X-ELMOS-Actor-ID", actorId)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body));
        }
        final HttpResponse<InputStream> response;
        try {
            response = client.send(request.build(), HttpResponse.BodyHandlers.ofInputStream());
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new ChinaDbSqlPreflightFailure(UNAVAILABLE);
        } catch (IOException | IllegalArgumentException error) {
            throw new ChinaDbSqlPreflightFailure(UNAVAILABLE);
        }
        int status = response.statusCode();
        if (status != 200) {
            close(response.body());
            if (status == 400 || status == 422) throw new ChinaDbSqlPreflightFailure(REQUEST_REJECTED);
            if (status == 413) throw new ChinaDbSqlPreflightFailure(REQUEST_TOO_LARGE);
            if (status == 503 || status == 504) throw new ChinaDbSqlPreflightFailure(UNAVAILABLE);
            throw new ChinaDbSqlPreflightFailure(PROTOCOL_ERROR);
        }
        String contentType = response.headers().firstValue("Content-Type").orElse("");
        if (!contentType.toLowerCase(java.util.Locale.ROOT).startsWith("application/json")) {
            close(response.body());
            throw new ChinaDbSqlPreflightFailure(PROTOCOL_ERROR);
        }
        long declared = response.headers().firstValueAsLong("Content-Length").orElse(-1);
        if (declared > ChinaDbSqlPreflightProtocol.MAX_RESPONSE_BYTES) {
            close(response.body());
            throw new ChinaDbSqlPreflightFailure(PROTOCOL_ERROR);
        }
        byte[] bytes = readBounded(response.body());
        try {
            JsonNode value = json.readTree(bytes);
            if (value == null) throw new ChinaDbSqlPreflightFailure(PROTOCOL_ERROR);
            return value;
        } catch (IOException error) {
            throw new ChinaDbSqlPreflightFailure(PROTOCOL_ERROR);
        }
    }

    private static byte[] readBounded(InputStream body) {
        try (body) {
            byte[] bytes = body.readNBytes(ChinaDbSqlPreflightProtocol.MAX_RESPONSE_BYTES + 1);
            if (bytes.length > ChinaDbSqlPreflightProtocol.MAX_RESPONSE_BYTES) {
                throw new ChinaDbSqlPreflightFailure(PROTOCOL_ERROR);
            }
            return bytes;
        } catch (IOException error) {
            throw new ChinaDbSqlPreflightFailure(UNAVAILABLE);
        }
    }

    private static void close(InputStream body) {
        try {
            body.close();
        } catch (IOException ignored) {
            // No upstream error bytes are trusted or returned to the caller.
        }
    }

    private static URI safeBase(String configured) {
        final URI base;
        try {
            base = URI.create(configured.endsWith("/") ? configured : configured + "/");
        } catch (IllegalArgumentException error) {
            throw new IllegalStateException("DATABASE_DATA_ENGINE_BASE_URL_INVALID", error);
        }
        if (!("http".equals(base.getScheme()) || "https".equals(base.getScheme()))
                || base.getHost() == null || base.getUserInfo() != null
                || base.getQuery() != null || base.getFragment() != null
                || !(base.getPath().isEmpty() || "/".equals(base.getPath()))
                || ("http".equals(base.getScheme()) && !allowedPlainHttpBase(base))) {
            throw new IllegalStateException("DATABASE_DATA_ENGINE_BASE_URL_INVALID");
        }
        return base;
    }

    private static boolean allowedPlainHttpBase(URI base) {
        String host = base.getHost().toLowerCase(java.util.Locale.ROOT);
        if ("database-data-engine-worker".equals(host)) {
            return base.getPort() == 8089;
        }
        return Set.of("localhost", "127.0.0.1", "::1").contains(host)
                && base.getPort() >= 1 && base.getPort() <= 65_535;
    }

    private static Duration boundedTimeout(Duration value, Duration maximum) {
        if (value == null || value.isZero() || value.isNegative() || value.compareTo(maximum) > 0) {
            throw new IllegalStateException("DATABASE_DATA_PREFLIGHT_TIMEOUT_INVALID");
        }
        return value;
    }
}
