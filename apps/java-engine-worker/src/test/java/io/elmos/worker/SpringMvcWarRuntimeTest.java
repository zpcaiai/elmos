package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.List;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.Base64;
import java.util.jar.Attributes;
import java.util.jar.Manifest;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringMvcWarRuntimeTest {
    @TempDir Path temporary;

    @Test void missingTomcatConfigurationFailsClosedAtTheExactBoundary() {
        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcWarRuntime.Configuration.unconfigured().verify());

        assertEquals("SPRING_MVC_TOMCAT_HOME_NOT_CONFIGURED", blocked.code());
    }

    @Test void sharedManagementPortUsesTheLoopbackServerAddressWithoutAnInvalidManagementAddress() {
        Map<String, String> environment = new HashMap<>();
        environment.put("MANAGEMENT_SERVER_ADDRESS", "inherited.invalid.example");

        SpringMvcWarRuntime.configureTargetLoopbackEnvironment(
                environment, Path.of("/exact/jdk-21"), 49152);

        assertEquals("/exact/jdk-21", environment.get("JAVA_HOME"));
        assertEquals("127.0.0.1", environment.get("SERVER_ADDRESS"));
        assertEquals("49152", environment.get("SERVER_PORT"));
        assertEquals("49152", environment.get("MANAGEMENT_SERVER_PORT"));
        assertFalse(environment.containsKey("MANAGEMENT_SERVER_ADDRESS"));
    }

    @Test void sourceWarDetectionRequiresOneActualServletWar() throws Exception {
        Path target = Files.createDirectories(temporary.resolve("target"));
        writeArchive(target.resolve("legacy.war"), Map.of(
                "WEB-INF/", new byte[0],
                "WEB-INF/web.xml", "<web-app/>".getBytes(StandardCharsets.UTF_8)));

        assertEquals(target.resolve("legacy.war"),
                SpringMvcWarRuntime.sourceWar(temporary, "maven"));

        writeArchive(target.resolve("other.war"), Map.of(
                "WEB-INF/", new byte[0],
                "WEB-INF/classes/", new byte[0]));
        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcWarRuntime.sourceWar(temporary, "maven"));
        assertEquals("SPRING_MVC_SOURCE_WAR_AMBIGUOUS", blocked.code());
    }

    @Test void targetWarMustBeRepackagedWithTheExactWarLauncher() throws Exception {
        Path target = Files.createDirectories(temporary.resolve("target"));
        Manifest manifest = new Manifest();
        manifest.getMainAttributes().put(Attributes.Name.MANIFEST_VERSION, "1.0");
        manifest.getMainAttributes().put(Attributes.Name.MAIN_CLASS, SpringMvcWarRuntime.WAR_LAUNCHER);
        manifest.getMainAttributes().putValue("Start-Class", "example.Application");
        manifest.getMainAttributes().putValue(
                SpringMvcWarRuntime.BOOT_VERSION_ATTRIBUTE, SpringMvcWarRuntime.TARGET_BOOT);
        writeArchive(target.resolve("application.war"), Map.of(
                "META-INF/MANIFEST.MF", manifestBytes(manifest),
                "WEB-INF/classes/", new byte[0],
                "org/springframework/boot/loader/launch/WarLauncher.class", new byte[]{1}));

        assertEquals(target.resolve("application.war"),
                SpringMvcWarRuntime.executableBootWar(temporary, "maven"));

        manifest.getMainAttributes().putValue(SpringMvcWarRuntime.BOOT_VERSION_ATTRIBUTE, "3.5.2");
        writeArchive(target.resolve("application.war"), Map.of(
                "META-INF/MANIFEST.MF", manifestBytes(manifest),
                "WEB-INF/classes/", new byte[0],
                "org/springframework/boot/loader/launch/WarLauncher.class", new byte[]{1}));
        assertEquals("BOOT_EXECUTABLE_WAR_NOT_FOUND",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.executableBootWar(temporary, "maven")).code());
    }

    @Test void httpOracleComparesStatusStableHeadersAndRawBodyBytes() {
        SpringMvcWarRuntime.OracleCase oracleCase = getCase(
                "fetch-order", "/api/orders/42", SpringMvcWarRuntime.BodyMode.EXACT_BYTES);
        var source = sourceRun(oracleCase, response("Mon, 10 Aug", "application/json", "body"));
        var target = targetRun(oracleCase, response("Tue, 11 Aug", "application/json", "body"));

        assertEquals("PASS_LOCAL_ENGINEERING",
                SpringMvcWarRuntime.compare(source, target).get("status"));

        var different = targetRun(
                oracleCase, response("Tue, 11 Aug", "application/json", "changed"));
        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcWarRuntime.compare(source, different));
        assertEquals("SPRING_MVC_HTTP_ORACLE_MISMATCH", blocked.code());
    }

    @Test void typedConfigurationCoversGetHeadersValidationAndExplicitJspMode() {
        SpringMvcWarRuntime.Configuration configuration = SpringMvcWarRuntime.Configuration.of(
                "", "", "", "", """
                [
                  {
                    "id":"fetch-order",
                    "method":"GET",
                    "path":"/api/orders/42",
                    "headers":{"Accept":"application/json"},
                    "expected_statuses":[200],
                    "body_mode":"EXACT_BYTES",
                    "readiness":true
                  },
                  {
                    "id":"get-order-validation",
                    "method":"GET",
                    "path":"/api/orders",
                    "headers":{"Accept":"application/json","X-Contract":"validation"},
                    "expected_statuses":[400,422],
                    "body_mode":"EXACT_BYTES"
                  },
                  {
                    "id":"render-orders-jsp",
                    "method":"GET",
                    "path":"/orders",
                    "headers":{"Accept":"text/html"},
                    "expected_statuses":[200],
                    "body_mode":"JSP_UTF8_LINE_ENDINGS"
                  }
                ]
                """, new ObjectMapper());

        assertEquals(3, configuration.oracleCases().size());
        SpringMvcWarRuntime.OracleCase validationGet = configuration.oracleCases().get(1);
        assertEquals("GET", validationGet.method());
        assertEquals("application/json", validationGet.requestHeaders().get("accept"));
        assertEquals(0, validationGet.requestBody().length);
        assertEquals(Set.of(400, 422), validationGet.expectedStatuses());
        assertEquals(SpringMvcWarRuntime.BodyMode.JSP_UTF8_LINE_ENDINGS,
                configuration.oracleCases().get(2).bodyMode());
    }

    @Test void legacyGetPathConfigurationRemainsAcceptedButPinsStatusAndBodyMode() {
        SpringMvcWarRuntime.Configuration configuration = SpringMvcWarRuntime.Configuration.of(
                "", "", "", "/api/orders/42,/orders");

        assertEquals(List.of("legacy-get-1", "legacy-get-2"),
                configuration.oracleCases().stream().map(SpringMvcWarRuntime.OracleCase::id).toList());
        assertEquals(Set.of(200), configuration.oracleCases().get(0).expectedStatuses());
        assertEquals(SpringMvcWarRuntime.BodyMode.EXACT_BYTES,
                configuration.oracleCases().get(0).bodyMode());
        assertTrue(configuration.oracleCases().get(0).readiness());
        assertFalse(configuration.oracleCases().get(1).readiness());
    }

    @Test void unexpectedStatusesAndMissingTargetOnlyActuatorFailClosed() {
        SpringMvcWarRuntime.OracleCase validation = new SpringMvcWarRuntime.OracleCase(
                "validation", "GET", "/api/orders", Map.of("accept", "application/json"),
                "",
                Set.of(400), SpringMvcWarRuntime.BodyMode.EXACT_BYTES);
        SpringUpgradeModels.BlockedException statusBlocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcWarRuntime.requireExpectedStatus(
                        validation, response("Tue, 11 Aug", "application/json", "200")));
        assertEquals("SPRING_MVC_HTTP_ORACLE_UNEXPECTED_STATUS", statusBlocked.code());

        SpringMvcWarRuntime.OracleResponse expected = new SpringMvcWarRuntime.OracleResponse(
                400, Map.of("content-type", List.of("application/json")), new byte[0]);
        var source = sourceRun(validation, expected);
        var targetWithoutActuator = new SpringMvcWarRuntime.OracleRun(
                Map.of(validation.id(), new SpringMvcWarRuntime.OracleObservation(validation, expected)),
                SpringMvcWarRuntime.WAR_LAUNCHER);
        SpringUpgradeModels.BlockedException actuatorBlocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcWarRuntime.compare(source, targetWithoutActuator));
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_PROBE_MISSING", actuatorBlocked.code());
    }

    @Test void jspModeNormalizesOnlyUtf8LineEndingsAndStillDetectsContentChanges() {
        SpringMvcWarRuntime.OracleCase jsp = getCase(
                "orders-jsp", "/orders", SpringMvcWarRuntime.BodyMode.JSP_UTF8_LINE_ENDINGS);
        var source = sourceRun(jsp, response("Mon, 10 Aug", "text/html;charset=UTF-8", "<p>A</p>\r\n"));
        var normalized = targetRun(
                jsp, response("Tue, 11 Aug", "text/html;charset=UTF-8", "<p>A</p>\n"));
        assertEquals("PASS_LOCAL_ENGINEERING", SpringMvcWarRuntime.compare(source, normalized).get("status"));

        var changed = targetRun(
                jsp, response("Tue, 11 Aug", "text/html;charset=UTF-8", "<p>B</p>\n"));
        assertEquals("SPRING_MVC_HTTP_ORACLE_MISMATCH",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.compare(source, changed)).code());
    }

    @Test void jspSessionCookieNormalizesOnlyOneExactTomcatSessionIdAndPreservesAttributes() {
        SpringMvcWarRuntime.OracleCase jsp = getCase(
                "orders-jsp", "/orders", SpringMvcWarRuntime.BodyMode.JSP_UTF8_LINE_ENDINGS);
        SpringMvcWarRuntime.OracleResponse sourceResponse = jspCookieResponse(List.of(
                "JSESSIONID=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA; Path=/; HttpOnly"));
        var source = sourceRun(jsp, sourceResponse);
        assertEquals("PASS_LOCAL_ENGINEERING", SpringMvcWarRuntime.compare(
                source, targetRun(jsp, jspCookieResponse(List.of(
                        "JSESSIONID=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB; Path=/; HttpOnly")))).get("status"));

        List<List<String>> rejected = List.of(
                List.of("JSESSIONID=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB; Path=/; HttpOnly"),
                List.of("JSESSIONID=GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG; Path=/; HttpOnly"),
                List.of("JSESSIONID=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB; Path=/changed; HttpOnly"),
                List.of("JSESSIONID=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB; Path=/; HttpOnly; Secure"),
                List.of("JSESSIONID=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB; Path=/; HttpOnly; SameSite=Lax"),
                List.of(
                        "JSESSIONID=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB; Path=/; HttpOnly",
                        "other=value; Path=/; HttpOnly"),
                List.of("OTHER=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB; Path=/; HttpOnly"));
        for (List<String> cookies : rejected) {
            assertEquals("SPRING_MVC_HTTP_ORACLE_MISMATCH",
                    assertThrows(SpringUpgradeModels.BlockedException.class,
                            () -> SpringMvcWarRuntime.compare(
                                    source, targetRun(jsp, jspCookieResponse(cookies)))).code());
        }

        var nonSessionSource = sourceRun(jsp, jspCookieResponse(List.of("OTHER=source; Path=/")));
        assertEquals("SPRING_MVC_HTTP_ORACLE_MISMATCH",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.compare(nonSessionSource,
                                targetRun(jsp, jspCookieResponse(List.of("OTHER=target; Path=/"))))).code());
    }

    @Test void unsafeOrAmbiguousTypedRequestsFailClosed() {
        assertEquals("SPRING_MVC_HTTP_ORACLE_HEADER_INVALID",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> new SpringMvcWarRuntime.OracleCase(
                                "unsafe", "GET", "/api/orders", Map.of("Host", "elsewhere"),
                                "", Set.of(200), SpringMvcWarRuntime.BodyMode.EXACT_BYTES)).code());
        assertEquals("SPRING_MVC_HTTP_ORACLE_MUTATING_METHOD_REQUIRES_ATTESTATION",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> new SpringMvcWarRuntime.OracleCase(
                                "mutating", "POST", "/api/orders", Map.of(),
                                "", Set.of(201), SpringMvcWarRuntime.BodyMode.EXACT_BYTES)).code());
        assertEquals("SPRING_MVC_HTTP_ORACLE_GET_BODY_REJECTED",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> new SpringMvcWarRuntime.OracleCase(
                                "get-body", "GET", "/api/orders", Map.of(),
                                Base64.getEncoder().encodeToString(new byte[]{1}), Set.of(200),
                                SpringMvcWarRuntime.BodyMode.EXACT_BYTES)).code());
        assertEquals("SPRING_MVC_HTTP_ORACLE_CONFIGURATION_AMBIGUOUS",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.Configuration.of(
                                "", "", "", "/api/orders", "[]", new ObjectMapper())).code());
    }

    @Test void typedJsonIsBoundedDuplicateFreeTrailingFreeIntegralAndCanonical() {
        String duplicateKey = validCasesJson().replace(
                "\"id\":\"source-ready\"", "\"id\":\"source-ready\",\"id\":\"shadow\"");
        assertConfigurationBlocked(duplicateKey, "SPRING_MVC_HTTP_ORACLE_JSON_INVALID");
        assertConfigurationBlocked(validCasesJson() + " []", "SPRING_MVC_HTTP_ORACLE_JSON_INVALID");
        assertConfigurationBlocked(validCasesJson().replace("[201]", "[201.0]"),
                "SPRING_MVC_HTTP_ORACLE_STATUS_INVALID");
        assertConfigurationBlocked(validCasesJson().replace(
                        "\"path\":\"/api/orders\",",
                        "\"path\":\"/api/orders\",\"body_base64\":\"eA\","),
                "SPRING_MVC_HTTP_ORACLE_BODY_INVALID");
        assertConfigurationBlocked(validCasesJson().replace(
                        "\"path\":\"/api/orders\",",
                        "\"path\":\"/api/orders\",\"body_base64\":\" eA==\","),
                "SPRING_MVC_HTTP_ORACLE_BODY_INVALID");
        assertConfigurationBlocked(" ".repeat(
                        SpringMvcWarRuntime.MAX_ORACLE_CONFIGURATION_BYTES + 1),
                "SPRING_MVC_HTTP_ORACLE_JSON_TOO_LARGE");
        String duplicateReadiness = validCasesJson().replace(
                "\"expected_statuses\":[201]", "\"readiness\":true,\"expected_statuses\":[201]");
        assertConfigurationBlocked(duplicateReadiness,
                "SPRING_MVC_HTTP_READINESS_NOT_EXACT");
    }

    @Test void readinessIsNeverReplayedAsABusinessCase() {
        assertEquals("SPRING_MVC_HTTP_READINESS_REPLAY_REJECTED",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.executeBusinessCasesOnce(
                                List.of(readinessCase()), ignored -> {
                                    throw new AssertionError("readiness must not be replayed");
                                })).code());
    }

    @Test void actuatorRequiresExactJsonContractUniqueTextualUpAndNoTrailingToken() {
        SpringMvcWarRuntime.validateTargetActuator(actuator(
                "application/json;charset=UTF-8", "{\"status\":\"UP\",\"components\":{}}"));
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_CONTRACT_MISMATCH",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.validateTargetActuator(actuator(
                                "application/json", "{\"status\":\"UP\"}"))).code());
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_CONTRACT_MISMATCH",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.validateTargetActuator(actuator(
                                "application/vnd.spring-boot.actuator.v2+json", "{\"status\":\"UP\"}"))).code());
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_CONTRACT_MISMATCH",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.validateTargetActuator(actuator(
                                "text/html", "{\"status\":\"UP\"}"))).code());
        SpringMvcWarRuntime.OracleResponse multipleContentTypes = new SpringMvcWarRuntime.OracleResponse(
                200,
                Map.of("content-type", List.of(
                        "application/json;charset=UTF-8", "application/json;charset=UTF-8")),
                "{\"status\":\"UP\"}".getBytes(StandardCharsets.UTF_8));
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_CONTRACT_MISMATCH",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.validateTargetActuator(multipleContentTypes)).code());
        SpringMvcWarRuntime.OracleResponse unavailable = new SpringMvcWarRuntime.OracleResponse(
                503,
                Map.of("content-type", List.of("application/json;charset=UTF-8")),
                "{\"status\":\"UP\"}".getBytes(StandardCharsets.UTF_8));
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_CONTRACT_MISMATCH",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.validateTargetActuator(unavailable)).code());
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_JSON_INVALID",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.validateTargetActuator(actuator(
                                "application/json;charset=UTF-8", "{\"status\":\"UP\",\"status\":\"DOWN\"}"))).code());
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_JSON_INVALID",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.validateTargetActuator(actuator(
                                "application/json;charset=UTF-8", "{\"status\":\"UP\"} []"))).code());
        assertEquals("SPRING_MVC_TARGET_ACTUATOR_STATUS_INVALID",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.validateTargetActuator(actuator(
                                "application/json;charset=UTF-8", "{\"status\":1}"))).code());
    }

    @Test void responseBodiesAreHardBoundedAndEvidenceOmitsHeaderValues() throws Exception {
        byte[] tooLarge = new byte[SpringMvcWarRuntime.MAX_RESPONSE_BODY_BYTES + 1];
        assertEquals("SPRING_MVC_HTTP_RESPONSE_BODY_TOO_LARGE",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> new SpringMvcWarRuntime.OracleResponse(200, Map.of(), tooLarge)).code());
        assertEquals("SPRING_MVC_HTTP_RESPONSE_BODY_TOO_LARGE",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.readBoundedBody(
                                new ByteArrayInputStream(tooLarge), "oversized")).code());

        SpringMvcWarRuntime.OracleCase request = new SpringMvcWarRuntime.OracleCase(
                "secret-header", "GET", "/api/orders", Map.of("authorization", "Bearer secret"),
                "", Set.of(200), SpringMvcWarRuntime.BodyMode.EXACT_BYTES);
        SpringMvcWarRuntime.OracleResponse response = new SpringMvcWarRuntime.OracleResponse(
                200, Map.of("set-cookie", List.of("session=secret")), new byte[0]);
        assertFalse(request.evidence().toString().contains("Bearer secret"));
        assertFalse(response.evidence().toString().contains("session=secret"));
        assertTrue(request.evidence().toString().contains("authorization"));
        assertTrue(response.evidence().toString().contains("set-cookie"));
        assertEquals("SPRING_MVC_HTTP_RESPONSE_HEADER_DUPLICATE",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> new SpringMvcWarRuntime.OracleResponse(
                                200, Map.of("Set-Cookie", List.of("a"),
                                        "set-cookie", List.of("b")), new byte[0])).code());
    }

    @Test void tomcatRuntimeFilesAreBoundToOneCanonicalConsumedManifest() throws Exception {
        Path home = writeTomcatHome(temporary.resolve("tomcat"));
        String catalinaDigest = fileSha256(home.resolve("lib/catalina.jar"));
        String manifestDigest = SpringMvcWarRuntime.consumedTomcatManifestSha256(home);
        SpringMvcWarRuntime.Configuration configuration = new SpringMvcWarRuntime.Configuration(
                home, "9.0.99", catalinaDigest, manifestDigest,
                List.of(readinessCase(), getCase(
                        "fetch-order", "/api/orders/42", SpringMvcWarRuntime.BodyMode.EXACT_BYTES)));
        assertEquals(manifestDigest, configuration.verify().consumedManifestDigest());

        Files.writeString(home.resolve("bin/bootstrap.jar"), "mutated", StandardCharsets.UTF_8);
        assertEquals("SPRING_MVC_TOMCAT_MANIFEST_DIGEST_MISMATCH",
                assertThrows(SpringUpgradeModels.BlockedException.class, configuration::verify).code());

        SpringMvcWarRuntime.Configuration missingManifest = new SpringMvcWarRuntime.Configuration(
                home, "9.0.99", catalinaDigest, "",
                List.of(readinessCase(), getCase(
                        "fetch-order", "/api/orders/42", SpringMvcWarRuntime.BodyMode.EXACT_BYTES)));
        assertEquals("SPRING_MVC_TOMCAT_MANIFEST_DIGEST_NOT_CONFIGURED",
                assertThrows(SpringUpgradeModels.BlockedException.class, missingManifest::verify).code());

        Files.writeString(home.resolve("lib/unbound.class"), "unsafe", StandardCharsets.UTF_8);
        assertEquals("SPRING_MVC_TOMCAT_CLASSLOADER_UNBOUNDED",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.consumedTomcatManifestSha256(home)).code());
    }

    @Test void catalinaBaseIsFreshConfinedAndExactAllowlisted() throws Exception {
        Path home = writeTomcatHome(temporary.resolve("tomcat-fresh-base"));
        SpringMvcWarRuntime.Configuration configuration = new SpringMvcWarRuntime.Configuration(
                home, "9.0.99", fileSha256(home.resolve("lib/catalina.jar")),
                SpringMvcWarRuntime.consumedTomcatManifestSha256(home),
                List.of(readinessCase(), getCase(
                        "fetch-order", "/api/orders/42", SpringMvcWarRuntime.BodyMode.EXACT_BYTES)));
        SpringMvcWarRuntime.VerifiedTomcat tomcat = configuration.verify();
        Path sourceWar = temporary.resolve("source.war");
        writeArchive(sourceWar,
                Map.of("WEB-INF/web.xml", "<web-app/>".getBytes(StandardCharsets.UTF_8)));
        Path runtimeRoot = Files.createDirectories(temporary.resolve("runtime"));
        Path predictablePreseed = Files.createDirectories(runtimeRoot.resolve("source-tomcat/lib"));
        Files.writeString(predictablePreseed.resolve("untrusted.jar"),
                "preseed", StandardCharsets.UTF_8);

        Path base = SpringMvcWarRuntime.createTomcatBase(tomcat, runtimeRoot, sourceWar, 18080);

        assertEquals(runtimeRoot.toRealPath(), base.getParent());
        assertTrue(base.getFileName().toString().startsWith("source-tomcat-"));
        assertFalse(base.equals(runtimeRoot.resolve("source-tomcat")));
        assertFalse(Files.exists(base.resolve("lib")));
        assertFalse(Files.exists(base.resolve("conf/Catalina")));
        SpringMvcWarRuntime.verifyInitialCatalinaBaseAllowlist(base);

        Files.createDirectory(base.resolve("lib"));
        assertEquals("SPRING_MVC_CATALINA_BASE_UNEXPECTED_CONTENT",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.verifyInitialCatalinaBaseAllowlist(base)).code());
        Files.delete(base.resolve("lib"));
        Files.createDirectories(base.resolve("conf/Catalina/localhost"));
        assertEquals("SPRING_MVC_CATALINA_BASE_UNEXPECTED_CONTENT",
                assertThrows(SpringUpgradeModels.BlockedException.class,
                        () -> SpringMvcWarRuntime.verifyInitialCatalinaBaseAllowlist(base)).code());
    }

    @Test void runtimeRejectsEveryTupleExceptTheSingleExactMvcRoute() {
        SpringUpgradeModels.Fingerprint exact = new SpringUpgradeModels.Fingerprint(
                "UNKNOWN", "11", "maven", List.of(), List.of("spring-mvc"), List.of(), Map.of(),
                "spring-mvc", "5.3.39");
        SpringRouteCatalog.SpringRoute route = SpringRouteCatalog
                .byId(SpringMvcWarRuntime.ROUTE_ID).orElseThrow();
        SpringMvcWarRuntime.requireExactTuple(exact, route);

        SpringUpgradeModels.Fingerprint wrongJava = new SpringUpgradeModels.Fingerprint(
                "UNKNOWN", "17", "maven", List.of(), List.of("spring-mvc"), List.of(), Map.of(),
                "spring-mvc", "5.3.39");
        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcWarRuntime.requireExactTuple(wrongJava, route));
        assertEquals("SPRING_MVC_WAR_RUNTIME_TUPLE_UNSUPPORTED", blocked.code());
    }

    private static SpringMvcWarRuntime.OracleCase getCase(
            String id, String path, SpringMvcWarRuntime.BodyMode bodyMode) {
        return new SpringMvcWarRuntime.OracleCase(
                id, "GET", path, Map.of("accept", bodyMode == SpringMvcWarRuntime.BodyMode.EXACT_BYTES
                        ? "application/json" : "text/html"), "", Set.of(200), bodyMode);
    }

    private static SpringMvcWarRuntime.OracleRun sourceRun(
            SpringMvcWarRuntime.OracleCase oracleCase, SpringMvcWarRuntime.OracleResponse response) {
        SpringMvcWarRuntime.OracleCase readiness = readinessCase();
        SpringMvcWarRuntime.OracleResponse readinessResponse = new SpringMvcWarRuntime.OracleResponse(
                200, Map.of("content-type", List.of("application/json")),
                "ready".getBytes(StandardCharsets.UTF_8));
        return new SpringMvcWarRuntime.OracleRun(
                Map.of(oracleCase.id(), new SpringMvcWarRuntime.OracleObservation(oracleCase, response)),
                "tomcat-9", Map.of(),
                Map.of(readiness.id(),
                        new SpringMvcWarRuntime.OracleObservation(readiness, readinessResponse)));
    }

    private static SpringMvcWarRuntime.OracleRun targetRun(
            SpringMvcWarRuntime.OracleCase oracleCase, SpringMvcWarRuntime.OracleResponse response) {
        return new SpringMvcWarRuntime.OracleRun(
                Map.of(oracleCase.id(), new SpringMvcWarRuntime.OracleObservation(oracleCase, response)),
                SpringMvcWarRuntime.WAR_LAUNCHER,
                Map.of(SpringMvcWarRuntime.TARGET_ACTUATOR_CASE_ID,
                        new SpringMvcWarRuntime.OracleResponse(
                                200, Map.of("content-type", List.of(
                                        "application/json;charset=UTF-8")),
                                "{\"status\":\"UP\"}".getBytes(StandardCharsets.UTF_8))));
    }

    private static SpringMvcWarRuntime.OracleResponse response(
            String date, String contentType, String body) {
        return new SpringMvcWarRuntime.OracleResponse(
                200,
                Map.of("date", List.of(date), "content-type", List.of(contentType)),
                body.getBytes(StandardCharsets.UTF_8));
    }

    private static SpringMvcWarRuntime.OracleResponse actuator(String contentType, String body) {
        return new SpringMvcWarRuntime.OracleResponse(
                200, Map.of("content-type", List.of(contentType)),
                body.getBytes(StandardCharsets.UTF_8));
    }

    private static SpringMvcWarRuntime.OracleResponse jspCookieResponse(List<String> cookies) {
        return new SpringMvcWarRuntime.OracleResponse(
                200,
                Map.of(
                        "content-type", List.of("text/html;charset=UTF-8"),
                        "content-language", List.of("en-US"),
                        "set-cookie", cookies),
                "<h1>Legacy orders</h1>\n".getBytes(StandardCharsets.UTF_8));
    }

    private static String validCasesJson() {
        return """
                [
                  {
                    "id":"source-ready",
                    "method":"GET",
                    "path":"/ready",
                    "headers":{"Accept":"application/json"},
                    "expected_statuses":[200],
                    "body_mode":"EXACT_BYTES",
                    "readiness":true
                  },
                  {
                    "id":"read-order",
                    "method":"GET",
                    "path":"/api/orders",
                    "headers":{"Accept":"application/json"},
                    "expected_statuses":[201],
                    "body_mode":"EXACT_BYTES"
                  }
                ]
                """;
    }

    private static void assertConfigurationBlocked(String json, String code) {
        assertEquals(code, assertThrows(SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcWarRuntime.Configuration.of(
                        "", "", "", "", json, new ObjectMapper())).code());
    }

    private static Path writeTomcatHome(Path home) throws Exception {
        Files.createDirectories(home.resolve("bin"));
        Files.createDirectories(home.resolve("conf"));
        Files.createDirectories(home.resolve("lib"));
        Files.writeString(home.resolve("bin/bootstrap.jar"), "bootstrap", StandardCharsets.UTF_8);
        Files.writeString(home.resolve("bin/tomcat-juli.jar"), "juli", StandardCharsets.UTF_8);
        Files.writeString(home.resolve("conf/catalina.properties"), """
                common.loader="${catalina.base}/lib","${catalina.base}/lib/*.jar","${catalina.home}/lib","${catalina.home}/lib/*.jar"
                server.loader=
                shared.loader=
                """, StandardCharsets.ISO_8859_1);
        Files.writeString(home.resolve("conf/context.xml"), "<Context/>", StandardCharsets.UTF_8);
        Files.writeString(home.resolve("conf/logging.properties"), ".handlers=", StandardCharsets.UTF_8);
        Files.writeString(home.resolve("conf/web.xml"), "<web-app/>", StandardCharsets.UTF_8);
        Manifest catalina = new Manifest();
        catalina.getMainAttributes().put(Attributes.Name.MANIFEST_VERSION, "1.0");
        catalina.getMainAttributes().put(Attributes.Name.IMPLEMENTATION_VERSION, "9.0.99");
        writeArchive(home.resolve("lib/catalina.jar"),
                Map.of("META-INF/MANIFEST.MF", manifestBytes(catalina)));
        return home;
    }

    private static String fileSha256(Path path) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path));
        StringBuilder value = new StringBuilder(64);
        for (byte current : digest) value.append(String.format("%02x", current));
        return value.toString();
    }

    private static SpringMvcWarRuntime.OracleCase readinessCase() {
        return new SpringMvcWarRuntime.OracleCase(
                "source-readiness", "GET", "/ready", Map.of("accept", "application/json"),
                "", Set.of(200), SpringMvcWarRuntime.BodyMode.EXACT_BYTES, true);
    }

    private static byte[] manifestBytes(Manifest manifest) throws IOException {
        var output = new java.io.ByteArrayOutputStream();
        manifest.write(output);
        return output.toByteArray();
    }

    private static void writeArchive(Path path, Map<String, byte[]> entries) throws IOException {
        try (ZipOutputStream output = new ZipOutputStream(Files.newOutputStream(path))) {
            for (Map.Entry<String, byte[]> entry : entries.entrySet()) {
                output.putNextEntry(new ZipEntry(entry.getKey()));
                output.write(entry.getValue());
                output.closeEntry();
            }
        }
    }
}
