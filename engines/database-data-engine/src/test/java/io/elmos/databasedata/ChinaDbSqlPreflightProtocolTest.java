package io.elmos.databasedata;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ChinaDbSqlPreflightProtocolTest {
    private static final String SNAPSHOT = "sha256:" + "a".repeat(64);
    private static final Map<String, String> TARGETS = Map.ofEntries(
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
    private static final Map<String, String> SOURCE_FAMILIES = Map.of(
            "Oracle", "oracle",
            "SQL Server", "sql-server",
            "PostgreSQL", "postgresql",
            "MySQL/MariaDB", "mysql-mariadb",
            "DB2 LUW", "db2-luw",
            "Sybase ASE", "sybase-ase");

    private final ObjectMapper json = new ObjectMapper();
    private final ChinaDbSqlPreflightProtocol protocol = new ChinaDbSqlPreflightProtocol(json);

    @Test
    void acceptsExactMultilineRequestAndRejectsAmbiguousJson() throws Exception {
        byte[] request = requestJson("SELECT 1\nFROM dual").getBytes(StandardCharsets.UTF_8);
        assertEquals("query-1", protocol.request(request).path("queryId").textValue());

        String duplicate = requestJson("SELECT 1").replaceFirst(
                "\\\"schemaVersion\\\":\\\"1.0\\\"",
                "\\\"schemaVersion\\\":\\\"1.0\\\",\\\"schemaVersion\\\":\\\"1.0\\\"");
        assertThrows(ChinaDbSqlPreflightFailure.class,
                () -> protocol.request(duplicate.getBytes(StandardCharsets.UTF_8)));
        assertThrows(ChinaDbSqlPreflightFailure.class,
                () -> protocol.request((requestJson("SELECT 1") + " true")
                        .getBytes(StandardCharsets.UTF_8)));
        String loneSurrogate = requestJson("SELECT 1").replace(
                "SELECT 1", "SELECT " + '\\' + "ud800");
        assertThrows(ChinaDbSqlPreflightFailure.class,
                () -> protocol.request(loneSurrogate.getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void validatesCompleteCatalogAndFailClosedAssessment() throws Exception {
        JsonNode request = protocol.request(requestJson("SELECT 1").getBytes(StandardCharsets.UTF_8));
        JsonNode capabilities = protocol.capabilities(capabilities());
        assertEquals(13, capabilities.path("targetCount").intValue());
        assertEquals(78, capabilities.path("plannedRouteCount").intValue());

        ObjectNode assessment = assessment();
        JsonNode accepted = protocol.assessment(request, assessment);
        assertEquals("BLOCKED", accepted.path("state").textValue());
        assertTrue(accepted.has("targetSql"));
        assertNull(accepted.path("targetSql").textValue());
        assertEquals("NOT_CERTIFIED", accepted.path("certification").textValue());

        assessment.put("targetSql", "SELECT 1");
        assertThrows(ChinaDbSqlPreflightFailure.class,
                () -> protocol.assessment(request, assessment));
    }

    @Test
    void rejectsDuplicateOrTrailingUpstreamJsonAndBuildsCompleteError() {
        assertThrows(ChinaDbSqlPreflightFailure.class,
                () -> protocol.response("{\"a\":1,\"a\":2}".getBytes(StandardCharsets.UTF_8)));
        assertThrows(ChinaDbSqlPreflightFailure.class,
                () -> protocol.response("{} []".getBytes(StandardCharsets.UTF_8)));

        Map<String, Object> body = new ChinaDbSqlPreflightFailure(
                ChinaDbSqlPreflightFailure.Kind.STALE_SNAPSHOT).body();
        assertEquals("BLOCKED", body.get("status"));
        assertTrue(body.containsKey("targetSql"));
        assertNull(body.get("targetSql"));
        assertEquals("NOT_CERTIFIED", body.get("certification"));
        @SuppressWarnings("unchecked")
        Map<String, String> verification = (Map<String, String>) body.get("verification");
        assertEquals(8, verification.size());
        assertTrue(verification.values().stream().allMatch("NOT_RUN"::equals));
    }

    @Test
    void rejectsDeclaredUpstreamLengthMismatch() {
        HttpChinaDbSqlPreflightGateway.requireMatchingContentLength(-1, 12);
        HttpChinaDbSqlPreflightGateway.requireMatchingContentLength(12, 12);
        ChinaDbSqlPreflightFailure failure = assertThrows(
                ChinaDbSqlPreflightFailure.class,
                () -> HttpChinaDbSqlPreflightGateway.requireMatchingContentLength(13, 12));
        assertEquals(ChinaDbSqlPreflightFailure.Kind.PROTOCOL_ERROR, failure.kind());
    }

    private ObjectNode capabilities() {
        ObjectNode root = json.createObjectNode();
        root.put("schemaVersion", "1.0");
        root.put("package", "chinadb-commercial-migration-skills");
        root.put("version", "1.0.0");
        ArrayNode targets = root.putArray("targets");
        TARGETS.forEach((id, label) -> {
            ObjectNode target = targets.addObject();
            target.put("id", id);
            target.put("label", label);
            target.put("adapterId", "chinadb." + id + ".target-adapter.v1");
            target.put("versionRequirement", "exact version required");
            target.put("compatibilityModeRequirement", "exact mode required");
            target.put("implementationStatus", "SPEC_ONLY");
            target.put("externalExecution", "NOT_RUN");
            target.put("certification", "NOT_CERTIFIED");
        });
        ArrayNode routes = root.putArray("plannedRoutes");
        SOURCE_FAMILIES.forEach((family, slug) -> TARGETS.keySet().forEach(targetId -> {
            ObjectNode route = routes.addObject();
            route.put("id", slug + "--to--" + targetId);
            route.put("sourceFamily", family);
            route.put("targetId", targetId);
            route.put("priority", "T1");
            route.put("state", "SPEC_ONLY");
            route.put("externalExecution", "NOT_RUN");
            route.put("certification", "NOT_CERTIFIED");
        }));
        ArrayNode exclusions = root.putArray("excludedTargets");
        List.of("polardb", "polardb-x", "tdsql").forEach(id -> {
            ObjectNode exclusion = exclusions.addObject();
            exclusion.put("id", id);
            exclusion.put("label", id);
            exclusion.put("reason", "excluded from this exact package");
        });
        root.put("implementationStatus", "SPEC_ONLY");
        root.put("externalExecution", "NOT_RUN");
        root.put("certification", "NOT_CERTIFIED");
        root.put("capabilitySnapshotDigest", SNAPSHOT);
        root.put("targetCount", 13);
        root.put("plannedRouteCount", 78);
        ObjectNode boundaries = root.putObject("boundaries");
        boundaries.put("exactCommercialTargetProfilesRegistered", false);
        boundaries.put("verifiedTargetRenderers", 0);
        boundaries.put("productionDatabaseAccess", false);
        boundaries.put("targetSqlMayBeEmitted", false);
        boundaries.put("claim", "typed source parsing only");
        return root;
    }

    private ObjectNode assessment() {
        ObjectNode root = json.createObjectNode();
        root.put("schemaVersion", "1.0");
        root.put("queryId", "query-1");
        root.put("sourceProfile", "postgresql-17.5");
        ObjectNode target = root.putObject("target");
        target.put("id", "dm8");
        target.put("label", "DM8");
        target.put("version", "8.1.3.140");
        target.put("edition", "enterprise");
        target.put("compatibilityMode", "oracle");
        target.put("driver", "dmjdbc-8.1.3.140");
        target.put("charset", "UTF-8");
        target.put("collation", "BINARY");
        target.put("timeZone", "Asia/Shanghai");
        target.put("adapterId", "chinadb.dm8.target-adapter.v1");
        target.put("implementationStatus", "SPEC_ONLY");
        root.put("routeId", "postgresql--to--dm8");
        root.put("state", "BLOCKED");
        root.put("sourceDigest", sha256("SELECT 1"));
        root.put("capabilitySnapshotDigest", SNAPSHOT);
        ObjectNode statement = root.putArray("statements").addObject();
        statement.put("index", 0);
        statement.put("kind", "SELECT");
        statement.putObject("sourceAst").put("type", "Select");
        statement.putArray("obligations").add("TARGET_ADAPTER_REQUIRED");
        ObjectNode blocker = root.putArray("blockers").addObject();
        blocker.put("code", "TARGET_ADAPTER_NOT_IMPLEMENTED");
        blocker.put("severity", "ERROR");
        blocker.putNull("statementIndex");
        blocker.put("message", "Target rendering is unavailable.");
        root.putNull("targetSql");
        ObjectNode verification = root.putObject("verification");
        verification.put("sourceParse", "PASSED");
        List.of("targetAdapter", "targetEmit", "targetReparse", "sourceExecution",
                "targetExecution", "resultEquivalence", "externalExecution")
                .forEach(field -> verification.put(field, "NOT_RUN"));
        root.put("certification", "NOT_CERTIFIED");
        return root;
    }

    private static String requestJson(String sql) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        ObjectNode request = mapper.createObjectNode();
        request.put("schemaVersion", "1.0");
        request.put("queryId", "query-1");
        request.put("sourceProfile", "postgresql-17.5");
        request.put("targetId", "dm8");
        request.put("targetVersion", "8.1.3.140");
        request.put("targetEdition", "enterprise");
        request.put("compatibilityMode", "oracle");
        request.put("targetDriver", "dmjdbc-8.1.3.140");
        request.put("targetCharset", "UTF-8");
        request.put("targetCollation", "BINARY");
        request.put("targetTimeZone", "Asia/Shanghai");
        request.put("capabilitySnapshotDigest", SNAPSHOT);
        request.put("sql", sql);
        request.putArray("parameters");
        return mapper.writeValueAsString(request);
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return "sha256:" + HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
