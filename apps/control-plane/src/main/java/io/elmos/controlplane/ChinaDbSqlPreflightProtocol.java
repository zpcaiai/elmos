package io.elmos.controlplane;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.util.Iterator;
import java.util.Set;
import java.util.regex.Pattern;

import static io.elmos.controlplane.ChinaDbSqlPreflightFailure.Kind.PROTOCOL_ERROR;
import static io.elmos.controlplane.ChinaDbSqlPreflightFailure.Kind.REQUEST_REJECTED;
import static io.elmos.controlplane.ChinaDbSqlPreflightFailure.Kind.REQUEST_TOO_LARGE;

/** Independently validates the request and the worker's fail-closed response. */
final class ChinaDbSqlPreflightProtocol {
    static final int MAX_REQUEST_BYTES = 1_310_720;
    static final int MAX_RESPONSE_BYTES = 8_388_608;

    private static final Set<String> REQUEST_FIELDS = Set.of(
            "schemaVersion", "queryId", "sourceProfile", "targetId", "targetVersion",
            "targetEdition", "compatibilityMode", "targetDriver", "targetCharset",
            "targetCollation", "targetTimeZone", "capabilitySnapshotDigest", "sql", "parameters");
    private static final Set<String> PARAMETER_FIELDS = Set.of("name", "logicalType", "nullable");
    private static final Set<String> SOURCE_PROFILES = Set.of(
            "postgresql-17.5", "postgresql-18.4", "mysql-8.4.10-lts",
            "sqlserver-2022-cu26", "oracle-26ai-ee", "sqlite-3.53.3", "duckdb-1.5.4");
    private static final Set<String> TARGET_IDS = Set.of(
            "dm8", "kingbasees", "opengauss", "tidb", "gbase-8s", "gbase-8c", "gbase-8a",
            "highgo-hgdb", "oceanbase-oracle", "oceanbase-mysql", "gaussdb-oracle",
            "gaussdb-m", "goldendb");
    private static final Pattern DIGEST = Pattern.compile("sha256:[0-9a-f]{64}");
    private static final Pattern VERSION = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._+~-]{0,127}");
    private static final Pattern CONTEXT = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._+:/~-]{0,127}");
    private static final Set<String> FLOATING = Set.of(
            "latest", "current", "unknown", "unspecified", "*", "x");

    private final ObjectMapper json;

    ChinaDbSqlPreflightProtocol(ObjectMapper json) {
        this.json = json;
    }

    JsonNode request(byte[] body) {
        if (body == null || body.length == 0) throw failure(REQUEST_REJECTED);
        if (body.length > MAX_REQUEST_BYTES) throw failure(REQUEST_TOO_LARGE);
        final JsonNode request;
        try {
            request = json.readTree(body);
        } catch (IOException error) {
            throw failure(REQUEST_REJECTED);
        }
        if (request == null || !request.isObject() || !fieldNames(request).equals(REQUEST_FIELDS)) {
            throw failure(REQUEST_REJECTED);
        }
        if (!"1.0".equals(text(request, "schemaVersion", 16))) throw failure(REQUEST_REJECTED);
        text(request, "queryId", 160);
        String sourceProfile = text(request, "sourceProfile", 128);
        String targetId = text(request, "targetId", 128);
        if (!SOURCE_PROFILES.contains(sourceProfile) || !TARGET_IDS.contains(targetId)) {
            throw failure(REQUEST_REJECTED);
        }
        exact(text(request, "targetVersion", 128), VERSION);
        exact(text(request, "targetEdition", 128), CONTEXT);
        exact(text(request, "compatibilityMode", 128), CONTEXT);
        exact(text(request, "targetDriver", 128), CONTEXT);
        exact(text(request, "targetCharset", 128), CONTEXT);
        exact(text(request, "targetCollation", 128), CONTEXT);
        exact(text(request, "targetTimeZone", 128), CONTEXT);
        if (!DIGEST.matcher(text(request, "capabilitySnapshotDigest", 80)).matches()) {
            throw failure(REQUEST_REJECTED);
        }
        text(request, "sql", 1_048_576);
        JsonNode parameters = request.path("parameters");
        if (!parameters.isArray() || parameters.size() > 4096) throw failure(REQUEST_REJECTED);
        for (JsonNode parameter : parameters) {
            if (!parameter.isObject() || !fieldNames(parameter).equals(PARAMETER_FIELDS)) {
                throw failure(REQUEST_REJECTED);
            }
            text(parameter, "name", 128);
            text(parameter, "logicalType", 128);
            if (!parameter.path("nullable").isBoolean()) throw failure(REQUEST_REJECTED);
        }
        return request;
    }

    JsonNode capabilities(JsonNode response) {
        object(response);
        equalsText(response, "implementationStatus", "SPEC_ONLY");
        equalsText(response, "externalExecution", "NOT_RUN");
        equalsText(response, "certification", "NOT_CERTIFIED");
        if (response.path("targetCount").asInt(-1) != 13
                || response.path("plannedRouteCount").asInt(-1) != 78
                || !response.path("targets").isArray()
                || response.path("targets").size() != 13
                || !response.path("plannedRoutes").isArray()
                || response.path("plannedRoutes").size() != 78) {
            throw failure(PROTOCOL_ERROR);
        }
        for (JsonNode target : response.path("targets")) {
            equalsText(target, "implementationStatus", "SPEC_ONLY");
            equalsText(target, "externalExecution", "NOT_RUN");
            equalsText(target, "certification", "NOT_CERTIFIED");
        }
        for (JsonNode route : response.path("plannedRoutes")) {
            equalsText(route, "state", "SPEC_ONLY");
            equalsText(route, "externalExecution", "NOT_RUN");
            equalsText(route, "certification", "NOT_CERTIFIED");
        }
        JsonNode boundaries = response.path("boundaries");
        if (!boundaries.isObject()
                || boundaries.path("exactCommercialTargetProfilesRegistered").asBoolean(true)
                || boundaries.path("verifiedTargetRenderers").asInt(-1) != 0
                || boundaries.path("productionDatabaseAccess").asBoolean(true)
                || boundaries.path("targetSqlMayBeEmitted").asBoolean(true)) {
            throw failure(PROTOCOL_ERROR);
        }
        return response;
    }

    JsonNode assessment(JsonNode request, JsonNode response) {
        object(request);
        object(response);
        equalsText(response, "state", "BLOCKED");
        if (!response.has("targetSql") || !response.path("targetSql").isNull()) {
            throw failure(PROTOCOL_ERROR);
        }
        equalsText(response, "certification", "NOT_CERTIFIED");
        equalsText(response, "queryId", text(request, "queryId", 160));
        equalsText(response, "sourceProfile", text(request, "sourceProfile", 128));
        equalsText(response, "capabilitySnapshotDigest",
                text(request, "capabilitySnapshotDigest", 80));

        JsonNode target = response.path("target");
        object(target);
        equalsText(target, "id", text(request, "targetId", 128));
        equalsText(target, "version", text(request, "targetVersion", 128));
        equalsText(target, "edition", text(request, "targetEdition", 128));
        equalsText(target, "compatibilityMode", text(request, "compatibilityMode", 128));
        equalsText(target, "driver", text(request, "targetDriver", 128));
        equalsText(target, "charset", text(request, "targetCharset", 128));
        equalsText(target, "collation", text(request, "targetCollation", 128));
        equalsText(target, "timeZone", text(request, "targetTimeZone", 128));
        equalsText(target, "adapterId", "chinadb." + target.path("id").asText() + ".target-adapter.v1");
        equalsText(target, "implementationStatus", "SPEC_ONLY");

        JsonNode verification = response.path("verification");
        object(verification);
        String sourceParse = verification.path("sourceParse").asText("");
        if (!Set.of("PASSED", "FAILED").contains(sourceParse)) throw failure(PROTOCOL_ERROR);
        for (String field : Set.of("targetAdapter", "targetEmit", "targetReparse",
                "sourceExecution", "targetExecution", "resultEquivalence", "externalExecution")) {
            equalsText(verification, field, "NOT_RUN");
        }
        JsonNode statements = response.path("statements");
        JsonNode blockers = response.path("blockers");
        if (!statements.isArray() || !blockers.isArray() || blockers.isEmpty()
                || ("PASSED".equals(sourceParse) && statements.isEmpty())
                || ("FAILED".equals(sourceParse) && !statements.isEmpty())) {
            throw failure(PROTOCOL_ERROR);
        }
        return response;
    }

    private static void exact(String value, Pattern pattern) {
        String normalized = value.toLowerCase(java.util.Locale.ROOT);
        if (!pattern.matcher(value).matches() || FLOATING.contains(normalized)
                || normalized.endsWith(".*") || normalized.endsWith(".x")) {
            throw failure(REQUEST_REJECTED);
        }
    }

    private static Set<String> fieldNames(JsonNode object) {
        java.util.HashSet<String> names = new java.util.HashSet<>();
        Iterator<String> fields = object.fieldNames();
        fields.forEachRemaining(names::add);
        return Set.copyOf(names);
    }

    private static void object(JsonNode value) {
        if (value == null || !value.isObject()) throw failure(PROTOCOL_ERROR);
    }

    private static String text(JsonNode object, String field, int maxLength) {
        JsonNode value = object.path(field);
        if (!value.isTextual() || value.textValue().isBlank() || value.textValue().length() > maxLength) {
            throw failure(REQUEST_REJECTED);
        }
        return value.textValue();
    }

    private static void equalsText(JsonNode object, String field, String expected) {
        if (!expected.equals(object.path(field).asText(null))) throw failure(PROTOCOL_ERROR);
    }

    private static ChinaDbSqlPreflightFailure failure(ChinaDbSqlPreflightFailure.Kind kind) {
        return new ChinaDbSqlPreflightFailure(kind);
    }
}
