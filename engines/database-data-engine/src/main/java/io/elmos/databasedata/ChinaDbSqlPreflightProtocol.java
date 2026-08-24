package io.elmos.databasedata;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

import static io.elmos.databasedata.ChinaDbSqlPreflightFailure.Kind.PROTOCOL_ERROR;
import static io.elmos.databasedata.ChinaDbSqlPreflightFailure.Kind.REQUEST_REJECTED;
import static io.elmos.databasedata.ChinaDbSqlPreflightFailure.Kind.REQUEST_TOO_LARGE;

/** Exact request and fail-closed response checks applied before and after the sidecar hop. */
final class ChinaDbSqlPreflightProtocol {
    static final int MAX_REQUEST_BYTES = 1_310_720;
    static final int MAX_SQL_BYTES = 256 * 1024;
    static final int MAX_PARAMETERS = 256;
    static final int MAX_STATEMENTS = 256;
    static final int MAX_RESPONSE_BYTES = 4_194_304;

    private static final Set<String> REQUEST_FIELDS = Set.of(
            "schemaVersion", "queryId", "sourceProfile", "targetId", "targetVersion",
            "targetEdition", "compatibilityMode", "targetDriver", "targetCharset",
            "targetCollation", "targetTimeZone", "capabilitySnapshotDigest", "sql", "parameters");
    private static final Set<String> PARAMETER_FIELDS = Set.of("name", "logicalType", "nullable");
    private static final Set<String> CAPABILITY_FIELDS = Set.of(
            "schemaVersion", "package", "version", "targets", "plannedRoutes",
            "excludedTargets", "implementationStatus", "externalExecution", "certification",
            "capabilitySnapshotDigest", "targetCount", "plannedRouteCount", "boundaries");
    private static final Set<String> CAPABILITY_TARGET_FIELDS = Set.of(
            "id", "label", "adapterId", "versionRequirement", "compatibilityModeRequirement",
            "implementationStatus", "externalExecution", "certification");
    private static final Set<String> ROUTE_FIELDS = Set.of(
            "id", "sourceFamily", "targetId", "priority", "state",
            "externalExecution", "certification");
    private static final Set<String> EXCLUSION_FIELDS = Set.of("id", "label", "reason");
    private static final Set<String> BOUNDARY_FIELDS = Set.of(
            "exactCommercialTargetProfilesRegistered", "verifiedTargetRenderers",
            "productionDatabaseAccess", "targetSqlMayBeEmitted", "claim");
    private static final Set<String> RESULT_FIELDS = Set.of(
            "schemaVersion", "queryId", "sourceProfile", "target", "routeId", "state",
            "sourceDigest", "capabilitySnapshotDigest", "statements", "blockers",
            "targetSql", "verification", "certification");
    private static final Set<String> RESULT_TARGET_FIELDS = Set.of(
            "id", "label", "version", "edition", "compatibilityMode", "driver",
            "charset", "collation", "timeZone", "adapterId", "implementationStatus");
    private static final Set<String> VERIFICATION_FIELDS = Set.of(
            "sourceParse", "targetAdapter", "targetEmit", "targetReparse", "sourceExecution",
            "targetExecution", "resultEquivalence", "externalExecution");
    private static final Set<String> STATEMENT_FIELDS =
            Set.of("index", "kind", "sourceAst", "obligations");
    private static final Set<String> BLOCKER_FIELDS =
            Set.of("code", "severity", "statementIndex", "message");

    private static final Set<String> SOURCE_PROFILES = Set.of(
            "postgresql-17.5", "postgresql-18.4", "mysql-8.4.10-lts",
            "sqlserver-2022-cu26", "oracle-26ai-ee", "sqlite-3.53.3", "duckdb-1.5.4");
    private static final Map<String, String> SOURCE_ROUTE_SLUGS = Map.of(
            "postgresql-17.5", "postgresql",
            "postgresql-18.4", "postgresql",
            "mysql-8.4.10-lts", "mysql-mariadb",
            "sqlserver-2022-cu26", "sql-server",
            "oracle-26ai-ee", "oracle",
            "sqlite-3.53.3", "sqlite-3-53-3",
            "duckdb-1.5.4", "duckdb-1-5-4");
    private static final Map<String, String> SOURCE_FAMILY_SLUGS = Map.of(
            "Oracle", "oracle",
            "SQL Server", "sql-server",
            "PostgreSQL", "postgresql",
            "MySQL/MariaDB", "mysql-mariadb",
            "DB2 LUW", "db2-luw",
            "Sybase ASE", "sybase-ase");
    private static final Map<String, String> TARGET_LABELS = Map.ofEntries(
            Map.entry("dm8", "DM8"),
            Map.entry("kingbasees", "KingbaseES"),
            Map.entry("opengauss", "openGauss"),
            Map.entry("tidb", "TiDB"),
            Map.entry("gbase-8s", "GBase 8s"),
            Map.entry("gbase-8c", "GBase 8c"),
            Map.entry("gbase-8a", "GBase 8a"),
            Map.entry("highgo-hgdb", "HighGo / HGDB"),
            Map.entry("oceanbase-oracle", "OceanBase Oracle-compatible mode"),
            Map.entry("oceanbase-mysql", "OceanBase MySQL-compatible mode"),
            Map.entry("gaussdb-oracle", "GaussDB Oracle-compatible mode"),
            Map.entry("gaussdb-m", "GaussDB M-compatible mode"),
            Map.entry("goldendb", "GoldenDB"));
    private static final Set<String> TARGET_IDS = TARGET_LABELS.keySet();
    private static final Set<String> EXCLUDED_TARGET_IDS = Set.of("polardb", "polardb-x", "tdsql");
    private static final Set<String> PRIORITIES = Set.of("T1", "T2", "ANALYTICAL");

    private static final Pattern DIGEST = Pattern.compile("sha256:[0-9a-f]{64}");
    private static final Pattern QUERY_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,159}");
    private static final Pattern VERSION = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._+~-]{0,127}");
    private static final Pattern CONTEXT = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._+:/~-]{0,127}");
    private static final Pattern CODE = Pattern.compile("[A-Z][A-Z0-9_]{0,127}");
    private static final Pattern STATEMENT_KIND = Pattern.compile("[A-Z][A-Z0-9_]{0,127}");
    private static final Set<String> FLOATING =
            Set.of("latest", "current", "unknown", "unspecified", "*", "x");

    private final ObjectReader reader;

    ChinaDbSqlPreflightProtocol(ObjectMapper json) {
        this.reader = json.reader()
                .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                .with(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
    }

    JsonNode response(byte[] body) {
        try {
            JsonNode response = reader.readTree(body);
            if (response == null) throw failure(PROTOCOL_ERROR);
            return response;
        } catch (IOException | RuntimeException error) {
            throw failure(PROTOCOL_ERROR);
        }
    }

    JsonNode request(byte[] body) {
        if (body == null || body.length == 0) throw failure(REQUEST_REJECTED);
        if (body.length > MAX_REQUEST_BYTES) throw failure(REQUEST_TOO_LARGE);
        final JsonNode request;
        try {
            request = reader.readTree(body);
        } catch (IOException | RuntimeException error) {
            throw failure(REQUEST_REJECTED);
        }
        exactObject(request, REQUEST_FIELDS, REQUEST_REJECTED);
        equalsRequestText(request, "schemaVersion", "1.0");
        exact(requestText(request, "queryId", 160), QUERY_ID);
        String sourceProfile = requestText(request, "sourceProfile", 128);
        String targetId = requestText(request, "targetId", 128);
        if (!SOURCE_PROFILES.contains(sourceProfile) || !TARGET_IDS.contains(targetId)) {
            throw failure(REQUEST_REJECTED);
        }
        exact(requestText(request, "targetVersion", 128), VERSION);
        exact(requestText(request, "targetEdition", 128), CONTEXT);
        exact(requestText(request, "compatibilityMode", 128), CONTEXT);
        exact(requestText(request, "targetDriver", 128), CONTEXT);
        exact(requestText(request, "targetCharset", 128), CONTEXT);
        exact(requestText(request, "targetCollation", 128), CONTEXT);
        exact(requestText(request, "targetTimeZone", 128), CONTEXT);
        if (!DIGEST.matcher(requestText(request, "capabilitySnapshotDigest", 80)).matches()) {
            throw failure(REQUEST_REJECTED);
        }
        requestSql(request);
        JsonNode parameters = request.path("parameters");
        if (!parameters.isArray() || parameters.size() > MAX_PARAMETERS) {
            throw failure(REQUEST_REJECTED);
        }
        Set<String> names = new HashSet<>();
        for (JsonNode parameter : parameters) {
            exactObject(parameter, PARAMETER_FIELDS, REQUEST_REJECTED);
            String name = requestText(parameter, "name", 128);
            requestText(parameter, "logicalType", 128);
            if (!names.add(name) || !parameter.path("nullable").isBoolean()) {
                throw failure(REQUEST_REJECTED);
            }
        }
        return request;
    }

    JsonNode capabilities(JsonNode response) {
        exactObject(response, CAPABILITY_FIELDS, PROTOCOL_ERROR);
        equalsResponseText(response, "schemaVersion", "1.0");
        equalsResponseText(response, "package", "chinadb-commercial-migration-skills");
        equalsResponseText(response, "version", "1.0.0");
        equalsResponseText(response, "implementationStatus", "SPEC_ONLY");
        equalsResponseText(response, "externalExecution", "NOT_RUN");
        equalsResponseText(response, "certification", "NOT_CERTIFIED");
        if (!DIGEST.matcher(responseText(response, "capabilitySnapshotDigest", 80)).matches()) {
            throw failure(PROTOCOL_ERROR);
        }
        if (!exactInteger(response.path("targetCount"), 13)
                || !exactInteger(response.path("plannedRouteCount"), 78)) {
            throw failure(PROTOCOL_ERROR);
        }

        JsonNode targets = response.path("targets");
        if (!targets.isArray() || targets.size() != 13) throw failure(PROTOCOL_ERROR);
        Set<String> observedTargets = new HashSet<>();
        for (JsonNode target : targets) {
            exactObject(target, CAPABILITY_TARGET_FIELDS, PROTOCOL_ERROR);
            String id = responseText(target, "id", 128);
            if (!TARGET_IDS.contains(id) || !observedTargets.add(id)) throw failure(PROTOCOL_ERROR);
            equalsResponseText(target, "label", TARGET_LABELS.get(id));
            equalsResponseText(target, "adapterId", adapterId(id));
            responseText(target, "versionRequirement", 256);
            responseText(target, "compatibilityModeRequirement", 256);
            equalsResponseText(target, "implementationStatus", "SPEC_ONLY");
            equalsResponseText(target, "externalExecution", "NOT_RUN");
            equalsResponseText(target, "certification", "NOT_CERTIFIED");
        }
        if (!observedTargets.equals(TARGET_IDS)) throw failure(PROTOCOL_ERROR);

        JsonNode routes = response.path("plannedRoutes");
        if (!routes.isArray() || routes.size() != 78) throw failure(PROTOCOL_ERROR);
        Set<String> observedRoutes = new HashSet<>();
        for (JsonNode route : routes) {
            exactObject(route, ROUTE_FIELDS, PROTOCOL_ERROR);
            String sourceFamily = responseText(route, "sourceFamily", 128);
            String sourceSlug = SOURCE_FAMILY_SLUGS.get(sourceFamily);
            String targetId = responseText(route, "targetId", 128);
            String routeId = responseText(route, "id", 160);
            if (sourceSlug == null || !TARGET_IDS.contains(targetId)
                    || !routeId.equals(sourceSlug + "--to--" + targetId)
                    || !observedRoutes.add(routeId)
                    || !PRIORITIES.contains(responseText(route, "priority", 16))) {
                throw failure(PROTOCOL_ERROR);
            }
            equalsResponseText(route, "state", "SPEC_ONLY");
            equalsResponseText(route, "externalExecution", "NOT_RUN");
            equalsResponseText(route, "certification", "NOT_CERTIFIED");
        }
        if (observedRoutes.size() != SOURCE_FAMILY_SLUGS.size() * TARGET_IDS.size()) {
            throw failure(PROTOCOL_ERROR);
        }

        JsonNode exclusions = response.path("excludedTargets");
        if (!exclusions.isArray() || exclusions.size() != 3) throw failure(PROTOCOL_ERROR);
        Set<String> observedExclusions = new HashSet<>();
        for (JsonNode exclusion : exclusions) {
            exactObject(exclusion, EXCLUSION_FIELDS, PROTOCOL_ERROR);
            String id = responseText(exclusion, "id", 64);
            if (!EXCLUDED_TARGET_IDS.contains(id) || !observedExclusions.add(id)) {
                throw failure(PROTOCOL_ERROR);
            }
            responseText(exclusion, "label", 128);
            responseText(exclusion, "reason", 512);
        }
        if (!observedExclusions.equals(EXCLUDED_TARGET_IDS)) throw failure(PROTOCOL_ERROR);

        JsonNode boundaries = response.path("boundaries");
        exactObject(boundaries, BOUNDARY_FIELDS, PROTOCOL_ERROR);
        if (!exactBoolean(boundaries.path("exactCommercialTargetProfilesRegistered"), false)
                || !exactInteger(boundaries.path("verifiedTargetRenderers"), 0)
                || !exactBoolean(boundaries.path("productionDatabaseAccess"), false)
                || !exactBoolean(boundaries.path("targetSqlMayBeEmitted"), false)) {
            throw failure(PROTOCOL_ERROR);
        }
        responseText(boundaries, "claim", 1024);
        return response;
    }

    JsonNode assessment(JsonNode request, JsonNode response) {
        exactObject(request, REQUEST_FIELDS, PROTOCOL_ERROR);
        exactObject(response, RESULT_FIELDS, PROTOCOL_ERROR);
        equalsResponseText(response, "schemaVersion", "1.0");
        equalsResponseText(response, "queryId", requestText(request, "queryId", 160));
        String sourceProfile = requestText(request, "sourceProfile", 128);
        String targetId = requestText(request, "targetId", 128);
        equalsResponseText(response, "sourceProfile", sourceProfile);
        equalsResponseText(response, "routeId", SOURCE_ROUTE_SLUGS.get(sourceProfile)
                + "--to--" + targetId);
        equalsResponseText(response, "state", "BLOCKED");
        if (!response.has("targetSql") || !response.path("targetSql").isNull()) {
            throw failure(PROTOCOL_ERROR);
        }
        equalsResponseText(response, "sourceDigest", sha256(requestSql(request)));
        equalsResponseText(response, "capabilitySnapshotDigest",
                requestText(request, "capabilitySnapshotDigest", 80));
        equalsResponseText(response, "certification", "NOT_CERTIFIED");

        JsonNode target = response.path("target");
        exactObject(target, RESULT_TARGET_FIELDS, PROTOCOL_ERROR);
        equalsResponseText(target, "id", targetId);
        equalsResponseText(target, "label", TARGET_LABELS.get(targetId));
        equalsResponseText(target, "version", requestText(request, "targetVersion", 128));
        equalsResponseText(target, "edition", requestText(request, "targetEdition", 128));
        equalsResponseText(target, "compatibilityMode",
                requestText(request, "compatibilityMode", 128));
        equalsResponseText(target, "driver", requestText(request, "targetDriver", 128));
        equalsResponseText(target, "charset", requestText(request, "targetCharset", 128));
        equalsResponseText(target, "collation", requestText(request, "targetCollation", 128));
        equalsResponseText(target, "timeZone", requestText(request, "targetTimeZone", 128));
        equalsResponseText(target, "adapterId", adapterId(targetId));
        equalsResponseText(target, "implementationStatus", "SPEC_ONLY");

        JsonNode verification = response.path("verification");
        exactObject(verification, VERIFICATION_FIELDS, PROTOCOL_ERROR);
        String sourceParse = responseText(verification, "sourceParse", 16);
        if (!Set.of("PASSED", "FAILED").contains(sourceParse)) throw failure(PROTOCOL_ERROR);
        for (String field : VERIFICATION_FIELDS) {
            if (!"sourceParse".equals(field)) equalsResponseText(verification, field, "NOT_RUN");
        }

        JsonNode statements = response.path("statements");
        if (!statements.isArray() || statements.size() > MAX_STATEMENTS) {
            throw failure(PROTOCOL_ERROR);
        }
        for (int index = 0; index < statements.size(); index++) {
            JsonNode statement = statements.get(index);
            exactObject(statement, STATEMENT_FIELDS, PROTOCOL_ERROR);
            if (!exactInteger(statement.path("index"), index)
                    || !STATEMENT_KIND.matcher(responseText(statement, "kind", 128)).matches()) {
                throw failure(PROTOCOL_ERROR);
            }
            JsonNode ast = statement.path("sourceAst");
            if (!((ast.isObject() || ast.isArray()) && ast.size() > 0)) {
                throw failure(PROTOCOL_ERROR);
            }
            JsonNode obligations = statement.path("obligations");
            if (!obligations.isArray() || obligations.isEmpty() || obligations.size() > 256) {
                throw failure(PROTOCOL_ERROR);
            }
            Set<String> observedObligations = new HashSet<>();
            for (JsonNode obligation : obligations) {
                String value = responseText(obligation, 256);
                if (!observedObligations.add(value)) throw failure(PROTOCOL_ERROR);
            }
        }

        JsonNode blockers = response.path("blockers");
        if (!blockers.isArray() || blockers.isEmpty() || blockers.size() > 4096) {
            throw failure(PROTOCOL_ERROR);
        }
        boolean errorBlocker = false;
        for (JsonNode blocker : blockers) {
            exactObject(blocker, BLOCKER_FIELDS, PROTOCOL_ERROR);
            if (!CODE.matcher(responseText(blocker, "code", 128)).matches()) {
                throw failure(PROTOCOL_ERROR);
            }
            String severity = responseText(blocker, "severity", 16);
            if (!Set.of("ERROR", "WARNING").contains(severity)) throw failure(PROTOCOL_ERROR);
            errorBlocker |= "ERROR".equals(severity);
            JsonNode statementIndex = blocker.path("statementIndex");
            if (!statementIndex.isNull()
                    && (!statementIndex.isIntegralNumber()
                    || statementIndex.intValue() < 0
                    || statementIndex.intValue() >= statements.size())) {
                throw failure(PROTOCOL_ERROR);
            }
            responseText(blocker, "message", 2048);
        }

        if (!errorBlocker
                || ("PASSED".equals(sourceParse) && statements.isEmpty())
                || ("FAILED".equals(sourceParse) && !statements.isEmpty())) {
            throw failure(PROTOCOL_ERROR);
        }
        return response;
    }

    private static String adapterId(String targetId) {
        return "chinadb." + targetId + ".target-adapter.v1";
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return "sha256:" + HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static boolean hasUnpairedSurrogate(String value) {
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            if (Character.isHighSurrogate(current)) {
                if (index + 1 >= value.length()
                        || !Character.isLowSurrogate(value.charAt(index + 1))) {
                    return true;
                }
                index++;
            } else if (Character.isLowSurrogate(current)) {
                return true;
            }
        }
        return false;
    }

    private static void exact(String value, Pattern pattern) {
        String normalized = value.toLowerCase(java.util.Locale.ROOT);
        if (!pattern.matcher(value).matches() || FLOATING.contains(normalized)
                || normalized.endsWith(".*") || normalized.endsWith(".x")) {
            throw failure(REQUEST_REJECTED);
        }
    }

    private static void exactObject(
            JsonNode value,
            Set<String> expected,
            ChinaDbSqlPreflightFailure.Kind kind
    ) {
        if (value == null || !value.isObject() || !fieldNames(value).equals(expected)) {
            throw failure(kind);
        }
    }

    private static Set<String> fieldNames(JsonNode object) {
        Set<String> names = new HashSet<>();
        Iterator<String> fields = object.fieldNames();
        fields.forEachRemaining(names::add);
        return Set.copyOf(names);
    }

    private static boolean exactInteger(JsonNode value, int expected) {
        return value.isIntegralNumber() && value.canConvertToInt() && value.intValue() == expected;
    }

    private static boolean exactBoolean(JsonNode value, boolean expected) {
        return value.isBoolean() && value.booleanValue() == expected;
    }

    private static String requestText(JsonNode object, String field, int maximum) {
        return text(object.path(field), maximum, REQUEST_REJECTED);
    }

    private static String requestSql(JsonNode object) {
        JsonNode value = object.path("sql");
        if (!value.isTextual()) throw failure(REQUEST_REJECTED);
        String sql = value.textValue();
        if (sql.isBlank() || sql.indexOf('\0') >= 0 || hasUnpairedSurrogate(sql)
                || sql.getBytes(StandardCharsets.UTF_8).length > MAX_SQL_BYTES) {
            throw failure(REQUEST_REJECTED);
        }
        return sql;
    }

    private static String responseText(JsonNode object, String field, int maximum) {
        return text(object.path(field), maximum, PROTOCOL_ERROR);
    }

    private static String responseText(JsonNode value, int maximum) {
        return text(value, maximum, PROTOCOL_ERROR);
    }

    private static String text(
            JsonNode value,
            int maximum,
            ChinaDbSqlPreflightFailure.Kind kind
    ) {
        if (!value.isTextual()) throw failure(kind);
        String text = value.textValue();
        if (text.isBlank() || text.length() > maximum || !text.equals(text.trim())
                || text.indexOf('\0') >= 0 || text.indexOf('\r') >= 0
                || text.indexOf('\n') >= 0 || hasUnpairedSurrogate(text)) {
            throw failure(kind);
        }
        return text;
    }

    private static void equalsRequestText(JsonNode object, String field, String expected) {
        if (!expected.equals(requestText(object, field, Math.max(16, expected.length())))) {
            throw failure(REQUEST_REJECTED);
        }
    }

    private static void equalsResponseText(JsonNode object, String field, String expected) {
        if (expected == null
                || !expected.equals(responseText(object, field, Math.max(16, expected.length())))) {
            throw failure(PROTOCOL_ERROR);
        }
    }

    private static ChinaDbSqlPreflightFailure failure(ChinaDbSqlPreflightFailure.Kind kind) {
        return new ChinaDbSqlPreflightFailure(kind);
    }
}
