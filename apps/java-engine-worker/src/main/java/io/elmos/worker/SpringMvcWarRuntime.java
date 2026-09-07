package io.elmos.worker;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Properties;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.jar.Attributes;
import java.util.jar.Manifest;
import java.util.regex.Pattern;
import java.util.zip.ZipFile;

import io.elmos.worker.SpringUpgradeExecutionPort.Control;

import static io.elmos.worker.SpringUpgradeModels.BlockedException;

/** Exact, local-engineering runtime for the single traditional Spring MVC route. */
final class SpringMvcWarRuntime {
    /**
     * One client for every loopback probe this class makes.
     *
     * <p>Each {@link HttpClient} owns a selector thread and an executor, and the
     * class is never closed here, so a client built per probe kept those threads
     * alive until it was collected. Every run made several, and concurrent runs
     * multiplied them. The probes all target 127.0.0.1 with the same two-second
     * connect timeout, so a single shared client is equivalent.</p>
     */
    private static final HttpClient LOOPBACK_PROBE_CLIENT =
            HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();

    static final String SOURCE_SPRING = "5.3.39";
    static final String SOURCE_JAVA = "11";
    static final String TARGET_BOOT = "3.5.3";
    static final String TARGET_JAVA = "21";
    static final String ROUTE_ID = "spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21";
    static final String TOMCAT_MAJOR_PREFIX = "9.0.";
    static final String WAR_LAUNCHER = "org.springframework.boot.loader.launch.WarLauncher";
    static final String TARGET_ACTUATOR_CASE_ID = "target-actuator-health";
    static final String TARGET_ACTUATOR_PATH = "/actuator/health";
    static final String TARGET_ACTUATOR_CONTENT_TYPE = "application/json;charset=utf-8";
    static final String BOOT_VERSION_ATTRIBUTE = "Spring-Boot-Version";
    private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
    private static final Pattern PATH = Pattern.compile("/[A-Za-z0-9._~!$&'()*+,;=:@%/?-]*");
    private static final Pattern CASE_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final Pattern HEADER_NAME = Pattern.compile("[!#$%&'*+.^_`|~0-9A-Za-z-]+");
    private static final Pattern EXACT_TOMCAT_SESSION_COOKIE = Pattern.compile(
            "^JSESSIONID=[0-9A-F]{32}; Path=/; HttpOnly$");
    private static final int MAX_ORACLE_CASES = 32;
    private static final int MAX_REQUEST_BODY_BYTES = 1024 * 1024;
    static final int MAX_RESPONSE_BODY_BYTES = 4 * 1024 * 1024;
    static final int MAX_ORACLE_CONFIGURATION_BYTES = 2 * 1024 * 1024;
    private static final Duration ORACLE_EXCHANGE_TIMEOUT = Duration.ofSeconds(30);
    private static final int UNEXPECTED_STATUS_RETRY_LIMIT = 5;
    private static final Set<String> INITIAL_CATALINA_BASE_DIRECTORIES = Set.of(
            "", "conf", "logs", "temp", "webapps", "work");
    private static final Set<String> INITIAL_CATALINA_BASE_FILES = Set.of(
            "conf/catalina.properties", "conf/context.xml", "conf/logging.properties",
            "conf/server.xml", "conf/web.xml", "webapps/ROOT.war");
    private static final List<String> CONSUMED_TOMCAT_CONFIGURATION = List.of(
            "catalina.properties", "context.xml", "logging.properties", "web.xml");
    private static final String EXPECTED_COMMON_LOADER =
            "\"${catalina.base}/lib\",\"${catalina.base}/lib/*.jar\","
                    + "\"${catalina.home}/lib\",\"${catalina.home}/lib/*.jar\"";
    private static final Set<String> FORBIDDEN_REQUEST_HEADERS = Set.of(
            "connection", "content-length", "expect", "host", "transfer-encoding", "upgrade", "user-agent");
    private static final Set<String> VOLATILE_RESPONSE_HEADERS = Set.of(
            "connection", "content-length", "date", "keep-alive", "server", "transfer-encoding");

    record Configuration(Path tomcatHome, String tomcatVersion, String catalinaJarSha256,
                         String consumedTomcatManifestSha256, List<OracleCase> oracleCases) {
        Configuration {
            tomcatVersion = trim(tomcatVersion);
            catalinaJarSha256 = trim(catalinaJarSha256).toLowerCase(Locale.ROOT);
            consumedTomcatManifestSha256 = trim(consumedTomcatManifestSha256).toLowerCase(Locale.ROOT);
            oracleCases = oracleCases == null ? List.of() : List.copyOf(oracleCases);
            if (oracleCases.size() > MAX_ORACLE_CASES) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_TOO_LARGE",
                        "The exact Spring MVC HTTP oracle is bounded to " + MAX_ORACLE_CASES + " cases.");
            }
            Set<String> ids = new LinkedHashSet<>();
            for (OracleCase oracleCase : oracleCases) {
                if (oracleCase == null || !ids.add(oracleCase.id())) {
                    throw blocked("SPRING_MVC_HTTP_ORACLE_CASE_ID_DUPLICATE",
                            "Every typed Spring MVC HTTP oracle case requires a unique case id.");
                }
            }
            if (!oracleCases.isEmpty()) {
                long readinessCases = oracleCases.stream().filter(OracleCase::readiness).count();
                if (readinessCases != 1) {
                    throw blocked("SPRING_MVC_HTTP_READINESS_NOT_EXACT",
                            "Exactly one explicitly marked, side-effect-free GET readiness case is required.");
                }
                if (oracleCases.stream().noneMatch(oracleCase -> !oracleCase.readiness())) {
                    throw blocked("SPRING_MVC_HTTP_ORACLE_BUSINESS_CASE_MISSING",
                            "At least one business oracle case must remain after the readiness case.");
                }
            }
        }

        static Configuration unconfigured() {
            return new Configuration(null, "", "", "", List.of());
        }

        static Configuration of(String home, String version, String digest, String paths) {
            Path configuredHome = home == null || home.isBlank() ? null : Path.of(home.trim());
            return new Configuration(configuredHome, version, digest, "", legacyCases(paths));
        }

        static Configuration of(String home, String version, String digest, String paths,
                                String casesJson, ObjectMapper json) {
            Path configuredHome = home == null || home.isBlank() ? null : Path.of(home.trim());
            return new Configuration(configuredHome, version, digest, "",
                    parseCases(paths, casesJson, Objects.requireNonNull(json, "json")));
        }

        static Configuration of(String home, String version, String catalinaDigest,
                                String consumedManifestDigest, String paths,
                                String casesJson, ObjectMapper json) {
            Path configuredHome = home == null || home.isBlank() ? null : Path.of(home.trim());
            return new Configuration(configuredHome, version, catalinaDigest, consumedManifestDigest,
                    parseCases(paths, casesJson, Objects.requireNonNull(json, "json")));
        }

        OracleCase sourceReadinessCase() {
            return oracleCases.stream().filter(OracleCase::readiness).findFirst()
                    .orElseThrow(() -> blocked("SPRING_MVC_HTTP_READINESS_NOT_EXACT",
                            "The source runtime has no explicit GET readiness case."));
        }

        List<OracleCase> businessCases() {
            return oracleCases.stream().filter(oracleCase -> !oracleCase.readiness()).toList();
        }

        VerifiedTomcat verify() {
            if (tomcatHome == null) {
                throw blocked("SPRING_MVC_TOMCAT_HOME_NOT_CONFIGURED",
                        "The exact Spring MVC source runtime requires an approved absolute Tomcat 9 home.");
            }
            Path home = tomcatHome.toAbsolutePath().normalize();
            if (!tomcatHome.isAbsolute() || !Files.isDirectory(home, LinkOption.NOFOLLOW_LINKS)) {
                throw blocked("SPRING_MVC_TOMCAT_HOME_INVALID",
                        "The configured Tomcat home must be an existing absolute directory.");
            }
            if (!tomcatVersion.startsWith(TOMCAT_MAJOR_PREFIX)
                    || !tomcatVersion.substring(TOMCAT_MAJOR_PREFIX.length()).matches("[0-9]+")) {
                throw blocked("SPRING_MVC_TOMCAT_VERSION_NOT_EXACT",
                        "The source runtime requires one exact Apache Tomcat 9.0.x version.");
            }
            if (!SHA256.matcher(catalinaJarSha256).matches()) {
                throw blocked("SPRING_MVC_TOMCAT_DIGEST_NOT_CONFIGURED",
                        "The exact lowercase SHA-256 of Tomcat lib/catalina.jar is required.");
            }
            if (!SHA256.matcher(consumedTomcatManifestSha256).matches()) {
                throw blocked("SPRING_MVC_TOMCAT_MANIFEST_DIGEST_NOT_CONFIGURED",
                        "The exact lowercase SHA-256 of the canonical consumed-file manifest is required.");
            }
            if (oracleCases.isEmpty()) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_NOT_CONFIGURED",
                        "At least one typed loopback HTTP oracle case is required.");
            }
            Path catalina = regular(home.resolve("lib/catalina.jar"), "SPRING_MVC_TOMCAT_INSTALLATION_INVALID");
            Path bootstrap = regular(home.resolve("bin/bootstrap.jar"), "SPRING_MVC_TOMCAT_INSTALLATION_INVALID");
            Path juli = regular(home.resolve("bin/tomcat-juli.jar"), "SPRING_MVC_TOMCAT_INSTALLATION_INVALID");
            String actualDigest = sha256(catalina);
            if (!MessageDigest.isEqual(actualDigest.getBytes(StandardCharsets.US_ASCII),
                    catalinaJarSha256.getBytes(StandardCharsets.US_ASCII))) {
                throw blocked("SPRING_MVC_TOMCAT_DIGEST_MISMATCH",
                        "The configured Tomcat catalina.jar does not match its approved SHA-256.");
            }
            String actualVersion = implementationVersion(catalina);
            if (!tomcatVersion.equals(actualVersion)) {
                throw blocked("SPRING_MVC_TOMCAT_VERSION_MISMATCH",
                        "The digest-bound Tomcat catalina.jar does not report the configured exact version.");
            }
            TomcatContentManifest contentManifest = tomcatContentManifest(home);
            if (!MessageDigest.isEqual(contentManifest.digest().getBytes(StandardCharsets.US_ASCII),
                    consumedTomcatManifestSha256.getBytes(StandardCharsets.US_ASCII))) {
                throw blocked("SPRING_MVC_TOMCAT_MANIFEST_DIGEST_MISMATCH",
                        "The Tomcat files actually consumed by the runtime do not match the approved manifest.");
            }
            return new VerifiedTomcat(home, bootstrap, juli, tomcatVersion, actualDigest,
                    contentManifest.digest(), contentManifest.files());
        }
    }

    record TomcatContentFile(String path, long bytes, String sha256) {}

    record TomcatContentManifest(String digest, List<TomcatContentFile> files) {
        TomcatContentManifest { files = List.copyOf(files); }
    }

    record VerifiedTomcat(Path home, Path bootstrapJar, Path juliJar, String version, String digest,
                          String consumedManifestDigest, List<TomcatContentFile> consumedFiles) {
        VerifiedTomcat { consumedFiles = List.copyOf(consumedFiles); }
    }

    enum BodyMode {
        EXACT_BYTES,
        JSP_UTF8_LINE_ENDINGS
    }

    record OracleCase(String id, String method, String path, Map<String, String> requestHeaders,
                      String requestBodyBase64, Set<Integer> expectedStatuses, BodyMode bodyMode,
                      boolean readiness) {
        OracleCase(String id, String method, String path, Map<String, String> requestHeaders,
                   String requestBodyBase64, Set<Integer> expectedStatuses, BodyMode bodyMode) {
            this(id, method, path, requestHeaders, requestBodyBase64, expectedStatuses, bodyMode, false);
        }

        OracleCase {
            id = trim(id);
            method = trim(method).toUpperCase(Locale.ROOT);
            path = trim(path);
            String rawBodyBase64 = requestBodyBase64 == null ? "" : requestBodyBase64;
            if (!rawBodyBase64.equals(rawBodyBase64.trim())) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_BODY_INVALID",
                        "HTTP oracle body_base64 cannot contain surrounding whitespace.");
            }
            requestBodyBase64 = rawBodyBase64;
            bodyMode = Objects.requireNonNull(bodyMode, "bodyMode");
            if (!CASE_ID.matcher(id).matches()) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_CASE_ID_INVALID",
                        "HTTP oracle case ids must use the bounded safe identifier grammar.");
            }
            if (!"GET".equals(method)) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_MUTATING_METHOD_REQUIRES_ATTESTATION",
                        "Spring MVC runtime oracles are temporarily GET-only. Mutating methods require "
                                + "a disposable side-effect attestation that is not implemented yet.");
            }
            requireSafePath(path);
            Map<String, String> normalizedHeaders = new LinkedHashMap<>();
            if (requestHeaders != null) {
                requestHeaders.entrySet().stream()
                        .sorted(Map.Entry.comparingByKey(String.CASE_INSENSITIVE_ORDER))
                        .forEach(entry -> {
                            String name = trim(entry.getKey()).toLowerCase(Locale.ROOT);
                            String value = entry.getValue() == null ? "" : entry.getValue();
                            if (!HEADER_NAME.matcher(name).matches()
                                    || FORBIDDEN_REQUEST_HEADERS.contains(name)
                                    || value.contains("\r") || value.contains("\n")) {
                                throw blocked("SPRING_MVC_HTTP_ORACLE_HEADER_INVALID",
                                        "HTTP oracle request headers must use safe names and single-line values.");
                            }
                            if (normalizedHeaders.put(name, value) != null) {
                                throw blocked("SPRING_MVC_HTTP_ORACLE_HEADER_DUPLICATE",
                                        "HTTP oracle request header names are case-insensitively unique.");
                            }
                        });
            }
            requestHeaders = Map.copyOf(normalizedHeaders);
            byte[] requestBody = decodeBase64(requestBodyBase64,
                    "SPRING_MVC_HTTP_ORACLE_BODY_INVALID");
            if (requestBody.length > MAX_REQUEST_BODY_BYTES) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_BODY_TOO_LARGE",
                        "Each HTTP oracle request body is bounded to one MiB.");
            }
            if ("GET".equals(method) && requestBody.length != 0) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_GET_BODY_REJECTED",
                        "GET oracle cases cannot carry a request body.");
            }
            if (readiness && (!"GET".equals(method) || requestBody.length != 0)) {
                throw blocked("SPRING_MVC_HTTP_READINESS_NOT_SAFE",
                        "The source readiness case must be a body-free GET and is never a business mutation.");
            }
            Set<Integer> normalizedStatuses = new LinkedHashSet<>();
            if (expectedStatuses != null) {
                expectedStatuses.stream().sorted().forEach(status -> {
                    if (status == null || status < 200 || status >= 500) {
                        throw blocked("SPRING_MVC_HTTP_ORACLE_STATUS_INVALID",
                                "Expected HTTP statuses must be explicit values from 200 through 499.");
                    }
                    normalizedStatuses.add(status);
                });
            }
            if (normalizedStatuses.isEmpty()) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_STATUS_NOT_CONFIGURED",
                        "Every HTTP oracle case requires at least one expected response status.");
            }
            expectedStatuses = Set.copyOf(normalizedStatuses);
        }

        byte[] requestBody() {
            return decodeBase64(requestBodyBase64, "SPRING_MVC_HTTP_ORACLE_BODY_INVALID");
        }

        Map<String, Object> evidence() {
            byte[] body = requestBody();
            return Map.of(
                    "id", id,
                    "method", method,
                    "path", path,
                    "request_header_names", requestHeaders.keySet().stream().sorted().toList(),
                    "request_body_sha256", sha256(body),
                    "request_body_bytes", body.length,
                    "expected_statuses", expectedStatuses.stream().sorted().toList(),
                    "body_mode", bodyMode.name(),
                    "readiness", readiness);
        }
    }

    record TargetOnlyProbe(String id, String path, Set<Integer> expectedStatuses) {
        TargetOnlyProbe {
            id = trim(id);
            path = trim(path);
            requireSafePath(path);
            expectedStatuses = Set.copyOf(expectedStatuses);
            if (!TARGET_ACTUATOR_CASE_ID.equals(id)
                    || !TARGET_ACTUATOR_PATH.equals(path)
                    || !expectedStatuses.equals(Set.of(200))) {
                throw blocked("SPRING_MVC_TARGET_ACTUATOR_PROBE_INVALID",
                        "The target-only probe is fixed to GET /actuator/health with expected status 200.");
            }
        }

        static TargetOnlyProbe actuatorHealth() {
            return new TargetOnlyProbe(TARGET_ACTUATOR_CASE_ID, TARGET_ACTUATOR_PATH, Set.of(200));
        }
    }

    record OracleResponse(int status, Map<String, List<String>> headers, byte[] body) {
        OracleResponse {
            Objects.requireNonNull(headers, "headers");
            Objects.requireNonNull(body, "body");
            if (body.length > MAX_RESPONSE_BODY_BYTES) {
                throw blocked("SPRING_MVC_HTTP_RESPONSE_BODY_TOO_LARGE",
                        "HTTP oracle response bodies are bounded to four MiB.");
            }
            Map<String, List<String>> copied = new LinkedHashMap<>();
            headers.entrySet().stream().sorted(Map.Entry.comparingByKey()).forEach(entry -> {
                String name = entry.getKey().toLowerCase(Locale.ROOT);
                if (copied.put(name, List.copyOf(entry.getValue())) != null) {
                    throw blocked("SPRING_MVC_HTTP_RESPONSE_HEADER_DUPLICATE",
                            "HTTP response header names must be case-insensitively unique.");
                }
            });
            headers = Map.copyOf(copied);
            body = body.clone();
        }

        @Override public byte[] body() { return body.clone(); }

        Map<String, Object> evidence() {
            return Map.of(
                    "status", status,
                    "header_names", headers.keySet().stream().sorted().toList(),
                    "body_sha256", sha256(body),
                    "body_bytes", body.length);
        }
    }

    record OracleObservation(OracleCase oracleCase, OracleResponse response) {
        OracleObservation {
            Objects.requireNonNull(oracleCase, "oracleCase");
            Objects.requireNonNull(response, "response");
        }
    }

    record OracleRun(Map<String, OracleObservation> observations, String runtimeIdentity,
                     Map<String, OracleResponse> targetOnlyProbes,
                     Map<String, OracleObservation> sourceReadinessProbes) {
        OracleRun {
            observations = Map.copyOf(observations);
            runtimeIdentity = trim(runtimeIdentity);
            targetOnlyProbes = targetOnlyProbes == null ? Map.of() : Map.copyOf(targetOnlyProbes);
            sourceReadinessProbes = sourceReadinessProbes == null
                    ? Map.of() : Map.copyOf(sourceReadinessProbes);
        }

        OracleRun(Map<String, OracleObservation> observations, String runtimeIdentity) {
            this(observations, runtimeIdentity, Map.of(), Map.of());
        }

        OracleRun(Map<String, OracleObservation> observations, String runtimeIdentity,
                  Map<String, OracleResponse> targetOnlyProbes) {
            this(observations, runtimeIdentity, targetOnlyProbes, Map.of());
        }
    }

    static void requireExactTuple(SpringUpgradeModels.Fingerprint fingerprint,
                                  SpringRouteCatalog.SpringRoute route) {
        if (!"spring-mvc".equals(fingerprint.sourceFrameworkFamily())
                || !SOURCE_SPRING.equals(fingerprint.sourceFrameworkVersion())
                || !SOURCE_JAVA.equals(SpringRouteCatalog.normalizeJava(fingerprint.javaVersion()))
                || !SpringRouteCatalog.MAVEN_BUILD_TOOL.equals(fingerprint.buildTool())
                || !ROUTE_ID.equals(route.routeId())
                || !TARGET_BOOT.equals(route.targetBoot())
                || !TARGET_JAVA.equals(route.targetJava())) {
            throw blocked("SPRING_MVC_WAR_RUNTIME_TUPLE_UNSUPPORTED",
                    "The WAR runtime is implemented only for Spring Framework 5.3.39 / Java 11 / "
                            + "Maven 3.9.11 to Spring Boot 3.5.3 / Java 21.");
        }
    }

    static Path sourceWar(Path root, String buildTool) {
        if (!SpringRouteCatalog.MAVEN_BUILD_TOOL.equals(buildTool)) {
            throw blocked("SPRING_MVC_SOURCE_WAR_BUILD_UNSUPPORTED",
                    "The exact Spring MVC WAR runtime currently requires Maven 3.9.11.");
        }
        return uniqueWar(root.resolve("target"), false,
                "SPRING_MVC_SOURCE_WAR_NOT_FOUND", "SPRING_MVC_SOURCE_WAR_AMBIGUOUS");
    }

    static Path executableBootWar(Path root, String buildTool) {
        Path output = SpringRouteCatalog.GRADLE_BUILD_TOOL.equals(buildTool)
                ? root.resolve("build/libs") : root.resolve("target");
        return uniqueWar(output, true, "BOOT_EXECUTABLE_WAR_NOT_FOUND", "BOOT_EXECUTABLE_WAR_AMBIGUOUS");
    }

    OracleRun runSource(Path sourceRoot, Path runRoot, Path javaHome, String buildTool,
                        Configuration configuration, Control control) {
        VerifiedTomcat tomcat = configuration.verify();
        Path war = sourceWar(sourceRoot, buildTool);
        int port = reservePort();
        Path base = createTomcatBase(tomcat, runRoot.resolve("runtime"), war, port);
        Path log = runRoot.resolve("evidence/source-startup.log");
        reverifyTomcat(tomcat);
        Process process = startTomcat(tomcat, base, javaHome, log, control);
        try {
            OracleObservation readiness = awaitSourceReadiness(
                    process, port, configuration.sourceReadinessCase(), control);
            Map<String, OracleObservation> observations = executeBusinessCasesOnce(
                    configuration.businessCases(), oracleCase -> {
                        requireActive(process, control);
                        return exchange(LOOPBACK_PROBE_CLIENT, port, oracleCase);
                    });
            return new OracleRun(observations,
                    "apache-tomcat-" + tomcat.version() + ":" + tomcat.digest()
                            + ":manifest:" + tomcat.consumedManifestDigest(),
                    Map.of(), Map.of(readiness.oracleCase().id(), readiness));
        } finally {
            stopBounded(process, control, "source Tomcat");
        }
    }

    OracleRun runTarget(Path targetRoot, Path runRoot, Path javaHome, String buildTool,
                        Configuration configuration, Control control) {
        Path war = executableBootWar(targetRoot, buildTool);
        int port = reservePort();
        Path log = runRoot.resolve("evidence/target-startup.log");
        Filesystem.createDirectories(log.getParent());
        ProcessBuilder builder = new ProcessBuilder(javaHome.resolve("bin/java").toString(), "-jar", war.toString());
        builder.directory(targetRoot.toFile());
        configureTargetLoopbackEnvironment(builder.environment(), javaHome, port);
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.appendTo(log.toFile()));
        Process process;
        try {
            process = builder.start();
            control.process(process);
        } catch (IOException error) {
            throw blocked("BOOT_EXECUTABLE_WAR_START_FAILED",
                    "The verified WarLauncher artifact could not be started with Java 21.");
        }
        try {
            Map<String, OracleResponse> targetOnly = awaitTargetOnlyProbe(
                    process, port, TargetOnlyProbe.actuatorHealth(), control);
            HttpClient client = LOOPBACK_PROBE_CLIENT;
            Map<String, OracleObservation> observations = executeBusinessCasesOnce(
                    configuration.businessCases(), oracleCase -> {
                        requireActive(process, control);
                        return exchange(client, port, oracleCase);
                    });
            return new OracleRun(observations, WAR_LAUNCHER, targetOnly);
        } finally {
            stopBounded(process, control, "target WarLauncher");
        }
    }

    static void configureTargetLoopbackEnvironment(
            Map<String, String> environment, Path javaHome, int port) {
        environment.put("JAVA_HOME", javaHome.toString());
        environment.put("SERVER_ADDRESS", "127.0.0.1");
        environment.put("SERVER_PORT", Integer.toString(port));
        environment.put("MANAGEMENT_SERVER_PORT", Integer.toString(port));
        // Boot rejects a management-specific address when management shares the application port.
        // SERVER_ADDRESS already confines both contexts to loopback.
        environment.remove("MANAGEMENT_SERVER_ADDRESS");
    }

    static Map<String, Object> compare(OracleRun source, OracleRun target) {
        if (!source.targetOnlyProbes().isEmpty()) {
            throw blocked("SPRING_MVC_SOURCE_TARGET_ONLY_PROBE_REJECTED",
                    "Target-only probes must never be executed against the source runtime.");
        }
        if (!target.sourceReadinessProbes().isEmpty()) {
            throw blocked("SPRING_MVC_TARGET_SOURCE_READINESS_REJECTED",
                    "The source-only GET readiness case must never run against the target runtime.");
        }
        if (source.sourceReadinessProbes().size() != 1) {
            throw blocked("SPRING_MVC_SOURCE_READINESS_PROBE_MISSING",
                    "The source runtime must pass exactly one explicit side-effect-free GET readiness case.");
        }
        OracleObservation sourceReadiness = source.sourceReadinessProbes().values().iterator().next();
        if (!sourceReadiness.oracleCase().readiness()
                || !"GET".equals(sourceReadiness.oracleCase().method())) {
            throw blocked("SPRING_MVC_SOURCE_READINESS_PROBE_INVALID",
                    "The source readiness observation is not the configured body-free GET case.");
        }
        requireExpectedStatus(sourceReadiness.oracleCase(), sourceReadiness.response());
        OracleResponse actuator = target.targetOnlyProbes().get(TARGET_ACTUATOR_CASE_ID);
        if (target.targetOnlyProbes().size() != 1 || actuator == null || actuator.status() != 200) {
            throw blocked("SPRING_MVC_TARGET_ACTUATOR_PROBE_MISSING",
                    "The target runtime must independently pass GET /actuator/health with status 200.");
        }
        validateTargetActuator(actuator);
        if (!source.observations().keySet().equals(target.observations().keySet())) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_CASE_MISMATCH",
                    "Source and target did not execute the same exact typed HTTP oracle case ids.");
        }
        List<Map<String, Object>> comparisons = new ArrayList<>();
        for (String caseId : source.observations().keySet().stream().sorted().toList()) {
            OracleObservation sourceObservation = source.observations().get(caseId);
            OracleObservation targetObservation = target.observations().get(caseId);
            OracleCase oracleCase = sourceObservation.oracleCase();
            if (!oracleCase.equals(targetObservation.oracleCase())) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_CASE_DEFINITION_MISMATCH",
                        "Source and target did not execute the same request definition for case "
                                + caseId + ".");
            }
            OracleResponse left = sourceObservation.response();
            OracleResponse right = targetObservation.response();
            requireExpectedStatus(oracleCase, left);
            requireExpectedStatus(oracleCase, right);
            Map<String, List<String>> leftHeaders = stableHeaders(left.headers());
            Map<String, List<String>> rightHeaders = stableHeaders(right.headers());
            boolean equal = left.status() == right.status()
                    && leftHeaders.equals(rightHeaders)
                    && bodiesEqual(oracleCase, left, right);
            comparisons.add(Map.of(
                    "case", oracleCase.evidence(),
                    "equal", equal,
                    "source", left.evidence(),
                    "target", right.evidence(),
                    "compared_headers", leftHeaders.keySet()));
            if (!equal) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_MISMATCH",
                        "The target WarLauncher response differs from the source Tomcat response for case "
                                + caseId + ".");
            }
        }
        return Map.of(
                "schema_version", "1.0",
                "status", "PASS_LOCAL_ENGINEERING",
                "source_runtime", source.runtimeIdentity(),
                "target_runtime", target.runtimeIdentity(),
                "volatile_headers_excluded", VOLATILE_RESPONSE_HEADERS.stream().sorted().toList(),
                "target_only_actuator", Map.of(
                        "id", TARGET_ACTUATOR_CASE_ID,
                        "method", "GET",
                        "path", TARGET_ACTUATOR_PATH,
                        "response", actuator.evidence()),
                "source_readiness", Map.of(
                        "case", sourceReadiness.oracleCase().evidence(),
                        "response", sourceReadiness.response().evidence()),
                "comparisons", comparisons);
    }

    private static Path uniqueWar(Path output, boolean boot, String missingCode, String ambiguousCode) {
        if (!Files.isDirectory(output, LinkOption.NOFOLLOW_LINKS)) {
            throw blocked(missingCode, "The verified build output directory does not contain the required WAR.");
        }
        List<Path> wars;
        try (var stream = Files.list(output)) {
            wars = stream.filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                    .filter(path -> path.getFileName().toString().endsWith(".war"))
                    .filter(path -> !path.getFileName().toString().endsWith(".original"))
                    .filter(path -> !path.getFileName().toString().startsWith("original-"))
                    .filter(path -> boot ? isExecutableBootWar(path) : isServletWar(path))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString())).toList();
        } catch (IOException error) {
            throw blocked(missingCode, "The verified build output directory could not be inspected.");
        }
        if (wars.isEmpty()) throw blocked(missingCode, "The required verified WAR artifact was not found.");
        if (wars.size() != 1) throw blocked(ambiguousCode, "More than one eligible WAR artifact was produced.");
        return wars.get(0);
    }

    private static boolean isServletWar(Path path) {
        try (ZipFile archive = new ZipFile(path.toFile())) {
            return archive.getEntry("WEB-INF/web.xml") != null || hasEntryPrefix(archive, "WEB-INF/classes/");
        } catch (IOException error) {
            return false;
        }
    }

    private static boolean isExecutableBootWar(Path path) {
        try (ZipFile archive = new ZipFile(path.toFile())) {
            var manifestEntry = archive.getEntry("META-INF/MANIFEST.MF");
            if (manifestEntry == null || !hasEntryPrefix(archive, "WEB-INF/classes/")
                    || archive.getEntry("org/springframework/boot/loader/launch/WarLauncher.class") == null) {
                return false;
            }
            Manifest manifest = new Manifest(archive.getInputStream(manifestEntry));
            return WAR_LAUNCHER.equals(manifest.getMainAttributes().getValue(Attributes.Name.MAIN_CLASS))
                    && !trim(manifest.getMainAttributes().getValue("Start-Class")).isEmpty()
                    && TARGET_BOOT.equals(trim(manifest.getMainAttributes()
                            .getValue(BOOT_VERSION_ATTRIBUTE)));
        } catch (IOException error) {
            return false;
        }
    }

    private static boolean hasEntryPrefix(ZipFile archive, String prefix) {
        return archive.stream().anyMatch(entry -> entry.getName().startsWith(prefix));
    }

    static Path createTomcatBase(VerifiedTomcat tomcat, Path runtimeRoot, Path war, int port) {
        try {
            Filesystem.createDirectories(runtimeRoot);
            Path root = runtimeRoot.toAbsolutePath().normalize();
            if (Files.isSymbolicLink(root) || !Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
                throw blocked("SPRING_MVC_CATALINA_BASE_ROOT_UNSAFE",
                        "The per-run runtime root must be a real directory, never a symbolic link.");
            }
            Path realRoot = root.toRealPath();
            Path base = Files.createTempDirectory(realRoot, "source-tomcat-");
            if (Files.isSymbolicLink(base) || !Files.isDirectory(base, LinkOption.NOFOLLOW_LINKS)) {
                throw blocked("SPRING_MVC_CATALINA_BASE_CREATION_FAILED",
                        "The fresh CATALINA_BASE is not a real directory.");
            }
            Path realBase = base.toRealPath();
            if (!realRoot.equals(realBase.getParent()) || !isEmptyDirectory(realBase)) {
                throw blocked("SPRING_MVC_CATALINA_BASE_CONFINEMENT_FAILED",
                        "CATALINA_BASE must be an unpredictable fresh empty child of the per-run root.");
            }
            Files.createDirectory(realBase.resolve("conf"));
            Files.createDirectory(realBase.resolve("logs"));
            Files.createDirectory(realBase.resolve("temp"));
            Files.createDirectory(realBase.resolve("webapps"));
            Files.createDirectory(realBase.resolve("work"));
            for (String name : List.of("catalina.properties", "context.xml", "logging.properties", "web.xml")) {
                Path source = regular(tomcat.home().resolve("conf").resolve(name),
                        "SPRING_MVC_TOMCAT_INSTALLATION_INVALID");
                Files.copy(source, realBase.resolve("conf").resolve(name));
            }
            Files.copy(war, realBase.resolve("webapps/ROOT.war"));
            Files.writeString(realBase.resolve("conf/server.xml"), serverXml(port), StandardCharsets.UTF_8);
            verifyMaterializedTomcatBase(tomcat, realBase, war, port);
            return realBase;
        } catch (BlockedException error) {
            throw error;
        } catch (IOException error) {
            throw blocked("SPRING_MVC_CATALINA_BASE_CREATION_FAILED",
                    "The isolated per-run CATALINA_BASE could not be materialized.");
        }
    }

    private static Process startTomcat(VerifiedTomcat tomcat, Path base, Path javaHome,
                                       Path log, Control control) {
        Filesystem.createDirectories(log.getParent());
        String classpath = tomcat.bootstrapJar() + System.getProperty("path.separator") + tomcat.juliJar();
        ProcessBuilder builder = new ProcessBuilder(
                javaHome.resolve("bin/java").toString(),
                "-Djava.util.logging.config.file=" + base.resolve("conf/logging.properties"),
                "-Djava.util.logging.manager=org.apache.juli.ClassLoaderLogManager",
                "-Dcatalina.base=" + base,
                "-Dcatalina.home=" + tomcat.home(),
                "-Djava.io.tmpdir=" + base.resolve("temp"),
                "-classpath", classpath,
                "org.apache.catalina.startup.Bootstrap", "start");
        builder.directory(base.toFile());
        builder.environment().put("JAVA_HOME", javaHome.toString());
        builder.environment().put("CATALINA_BASE", base.toString());
        builder.environment().put("CATALINA_HOME", tomcat.home().toString());
        builder.redirectErrorStream(true);
        builder.redirectOutput(ProcessBuilder.Redirect.appendTo(log.toFile()));
        try {
            Process process = builder.start();
            control.process(process);
            return process;
        } catch (IOException error) {
            throw blocked("SPRING_MVC_SOURCE_START_FAILED",
                    "The exact Tomcat 9 source runtime could not be started with Java 11.");
        }
    }

    private static OracleObservation awaitSourceReadiness(Process process, int port,
                                                           OracleCase readiness, Control control) {
        if (!readiness.readiness() || !"GET".equals(readiness.method())) {
            throw blocked("SPRING_MVC_HTTP_READINESS_NOT_SAFE",
                    "Only the explicitly marked body-free GET case may be retried for source readiness.");
        }
        HttpClient client = LOOPBACK_PROBE_CLIENT;
        long deadline = System.nanoTime() + Duration.ofMinutes(2).toNanos();
        int unexpectedStatuses = 0;
        int lastStatus = -1;
        while (System.nanoTime() < deadline) {
            requireActive(process, control);
            try {
                OracleResponse response = exchange(client, port, readiness);
                if (readiness.expectedStatuses().contains(response.status())) {
                    control.log("captured explicit source GET readiness case on loopback");
                    return new OracleObservation(readiness, response);
                }
                lastStatus = response.status();
                if (++unexpectedStatuses >= UNEXPECTED_STATUS_RETRY_LIMIT) {
                    throw unexpectedStatus(readiness.id(), lastStatus);
                }
            } catch (IOException error) {
                // Connection refusal is allowed only for this non-mutating readiness GET.
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw blocked("RUN_CANCELLED", "Source readiness execution was interrupted.");
            }
            boundedPause();
        }
        if (lastStatus >= 0) throw unexpectedStatus(readiness.id(), lastStatus);
        throw blocked("SPRING_MVC_HTTP_READINESS_TIMEOUT",
                "The bounded source runtime did not expose its explicit GET readiness case.");
    }

    @FunctionalInterface
    interface OracleExchange {
        OracleResponse exchange(OracleCase oracleCase) throws IOException, InterruptedException;
    }

    static Map<String, OracleObservation> executeBusinessCasesOnce(
            List<OracleCase> cases, OracleExchange exchange) {
        Map<String, OracleObservation> observations = new LinkedHashMap<>();
        for (OracleCase oracleCase : cases) {
            if (oracleCase.readiness()) {
                throw blocked("SPRING_MVC_HTTP_READINESS_REPLAY_REJECTED",
                        "The readiness GET cannot be replayed as a business oracle case.");
            }
            try {
                OracleResponse response = exchange.exchange(oracleCase);
                requireExpectedStatus(oracleCase, response);
                observations.put(oracleCase.id(), new OracleObservation(oracleCase, response));
            } catch (IOException error) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_EXCHANGE_FAILED",
                        "Business HTTP oracle case " + oracleCase.id()
                                + " failed during its single allowed execution.");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw blocked("RUN_CANCELLED", "Business HTTP oracle execution was interrupted.");
            }
        }
        return Map.copyOf(observations);
    }

    private static Map<String, OracleResponse> awaitTargetOnlyProbe(
            Process process, int port, TargetOnlyProbe probe, Control control) {
        HttpClient client = LOOPBACK_PROBE_CLIENT;
        long deadline = System.nanoTime() + Duration.ofMinutes(2).toNanos();
        int unexpectedStatuses = 0;
        int lastStatus = -1;
        while (System.nanoTime() < deadline) {
            requireActive(process, control);
            try {
                HttpResponse<InputStream> response = client.send(
                        HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + probe.path()))
                                .timeout(Duration.ofSeconds(3))
                                .header("Accept", "application/json")
                                .header("User-Agent", "elmos-spring-mvc-target-probe/1")
                                .GET().build(), HttpResponse.BodyHandlers.ofInputStream());
                OracleResponse observed = boundedOracleResponse(response, probe.id());
                if (probe.expectedStatuses().contains(observed.status())) {
                    validateTargetActuator(observed);
                    control.log("captured independent target-only actuator health probe on loopback");
                    return Map.of(probe.id(), observed);
                }
                lastStatus = observed.status();
                unexpectedStatuses += 1;
                if (unexpectedStatuses >= UNEXPECTED_STATUS_RETRY_LIMIT) {
                    throw unexpectedStatus(probe.id(), lastStatus);
                }
            } catch (IOException error) {
                // Connection refusal is allowed only while the bounded target startup window remains open.
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw blocked("RUN_CANCELLED", "The target-only actuator probe was interrupted.");
            }
            boundedPause();
        }
        if (lastStatus >= 0) throw unexpectedStatus(probe.id(), lastStatus);
        throw blocked("SPRING_MVC_TARGET_ACTUATOR_PROBE_TIMEOUT",
                "The target executable WAR did not expose GET /actuator/health in time.");
    }

    private static OracleResponse exchange(HttpClient client, int port, OracleCase oracleCase)
            throws IOException, InterruptedException {
        HttpRequest.Builder request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + port + oracleCase.path()))
                .timeout(ORACLE_EXCHANGE_TIMEOUT)
                .header("User-Agent", "elmos-spring-mvc-oracle/2");
        oracleCase.requestHeaders().forEach(request::header);
        if (!"GET".equals(oracleCase.method())) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_MUTATING_METHOD_REQUIRES_ATTESTATION",
                    "Spring MVC runtime oracles cannot execute a mutating method without disposable "
                            + "side-effect attestation.");
        }
        request.GET();
        HttpResponse<InputStream> response = client.send(
                request.build(), HttpResponse.BodyHandlers.ofInputStream());
        return boundedOracleResponse(response, oracleCase.id());
    }

    private static OracleResponse boundedOracleResponse(
            HttpResponse<InputStream> response, String caseId) throws IOException {
        long declaredLength = response.headers().firstValueAsLong("content-length").orElse(-1);
        try (InputStream body = response.body()) {
            if (declaredLength > MAX_RESPONSE_BODY_BYTES) {
                throw blocked("SPRING_MVC_HTTP_RESPONSE_BODY_TOO_LARGE",
                        "HTTP oracle case " + caseId + " declared a response above four MiB.");
            }
            return new OracleResponse(response.statusCode(), response.headers().map(),
                    readBoundedBody(body, caseId));
        }
    }

    static byte[] readBoundedBody(InputStream body, String caseId) throws IOException {
        byte[] bytes = body.readNBytes(MAX_RESPONSE_BODY_BYTES + 1);
        if (bytes.length > MAX_RESPONSE_BODY_BYTES) {
            throw blocked("SPRING_MVC_HTTP_RESPONSE_BODY_TOO_LARGE",
                    "HTTP oracle case " + caseId + " exceeded the four MiB response limit.");
        }
        return bytes;
    }

    static void validateTargetActuator(OracleResponse response) {
        List<String> contentTypes = response.headers().getOrDefault("content-type", List.of());
        if (response.status() != 200 || contentTypes.size() != 1
                || !TARGET_ACTUATOR_CONTENT_TYPE.equals(
                        contentTypes.get(0).trim().toLowerCase(Locale.ROOT))) {
            throw blocked("SPRING_MVC_TARGET_ACTUATOR_CONTRACT_MISMATCH",
                    "Target actuator health must return 200 with the single exact Boot 3.5.3 Content-Type "
                            + "application/json;charset=UTF-8 (ASCII case-insensitive, outer whitespace ignored).");
        }
        JsonNode health = strictJsonTree(response.body(), new ObjectMapper(),
                "SPRING_MVC_TARGET_ACTUATOR_JSON_INVALID");
        JsonNode status = health != null && health.isObject() ? health.get("status") : null;
        if (status == null || !status.isTextual() || !"UP".equals(status.textValue())) {
            throw blocked("SPRING_MVC_TARGET_ACTUATOR_STATUS_INVALID",
                    "Target actuator JSON must contain one textual status field exactly equal to UP.");
        }
    }

    static void requireExpectedStatus(OracleCase oracleCase, OracleResponse response) {
        if (!oracleCase.expectedStatuses().contains(response.status())) {
            throw unexpectedStatus(oracleCase.id(), response.status());
        }
    }

    private static BlockedException unexpectedStatus(String caseId, int status) {
        return blocked("SPRING_MVC_HTTP_ORACLE_UNEXPECTED_STATUS",
                "HTTP oracle case " + caseId + " returned unconfigured status " + status + ".");
    }

    private static void requireActive(Process process, Control control) {
        if (control.cancelled()) {
            throw blocked("RUN_CANCELLED", "Spring MVC runtime execution was cancelled.");
        }
        if (!process.isAlive()) {
            throw blocked("SPRING_MVC_RUNTIME_EXITED",
                    "The Spring MVC oracle runtime exited before all HTTP cases were observed.");
        }
    }

    private static void boundedPause() {
        try {
            Thread.sleep(200);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw blocked("RUN_CANCELLED", "HTTP oracle readiness wait was interrupted.");
        }
    }

    private static List<OracleCase> legacyCases(String paths) {
        if (paths == null || paths.isBlank()) return List.of();
        List<OracleCase> cases = new ArrayList<>();
        for (String rawPath : paths.split(",")) {
            String path = trim(rawPath);
            if (path.isEmpty()) continue;
            cases.add(new OracleCase(
                    "legacy-get-" + (cases.size() + 1),
                    "GET",
                    path,
                    Map.of("accept", "*/*"),
                    "",
                    Set.of(200),
                    BodyMode.EXACT_BYTES,
                    cases.isEmpty()));
        }
        return List.copyOf(cases);
    }

    private static List<OracleCase> parseCases(
            String legacyPaths, String casesJson, ObjectMapper json) {
        boolean hasLegacy = legacyPaths != null && !legacyPaths.isBlank();
        boolean hasTyped = casesJson != null && !casesJson.isEmpty();
        if (hasLegacy && hasTyped) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_CONFIGURATION_AMBIGUOUS",
                    "Configure either legacy GET paths or typed HTTP oracle cases, never both.");
        }
        if (!hasTyped) return legacyCases(legacyPaths);
        byte[] configurationBytes = strictUtf8(casesJson,
                "SPRING_MVC_HTTP_ORACLE_JSON_INVALID");
        if (configurationBytes.length > MAX_ORACLE_CONFIGURATION_BYTES) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_JSON_TOO_LARGE",
                    "Typed Spring MVC HTTP oracle configuration is bounded to two MiB.");
        }
        JsonNode root = strictJsonTree(configurationBytes, json,
                "SPRING_MVC_HTTP_ORACLE_JSON_INVALID");
        if (root == null || !root.isArray() || root.isEmpty()) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_JSON_INVALID",
                    "Typed Spring MVC HTTP oracle configuration must be a non-empty JSON array.");
        }
        List<OracleCase> cases = new ArrayList<>();
        for (JsonNode node : root) {
            if (!node.isObject()) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_JSON_INVALID",
                        "Every typed HTTP oracle case must be a JSON object.");
            }
            Set<String> allowed = Set.of(
                    "id", "method", "path", "headers", "body_utf8", "body_base64",
                    "expected_statuses", "body_mode", "readiness");
            node.fieldNames().forEachRemaining(name -> {
                if (!allowed.contains(name)) {
                    throw blocked("SPRING_MVC_HTTP_ORACLE_FIELD_UNSUPPORTED",
                            "Unknown typed HTTP oracle field: " + name + ".");
                }
            });
            JsonNode headersNode = node.path("headers");
            if (!headersNode.isMissingNode() && !headersNode.isObject()) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_JSON_INVALID",
                        "HTTP oracle headers must be a JSON object of string values.");
            }
            Map<String, String> headers = new LinkedHashMap<>();
            if (headersNode.isObject()) {
                headersNode.fields().forEachRemaining(entry -> {
                    if (!entry.getValue().isTextual()) {
                        throw blocked("SPRING_MVC_HTTP_ORACLE_JSON_INVALID",
                                "HTTP oracle header values must be strings.");
                    }
                    headers.put(entry.getKey(), entry.getValue().textValue());
                });
            }
            boolean hasUtf8 = node.has("body_utf8");
            boolean hasBase64 = node.has("body_base64");
            if (hasUtf8 && hasBase64) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_BODY_AMBIGUOUS",
                        "An HTTP oracle case cannot configure both body_utf8 and body_base64.");
            }
            if (hasUtf8 && !node.get("body_utf8").isTextual()
                    || hasBase64 && !node.get("body_base64").isTextual()) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_JSON_INVALID",
                        "HTTP oracle request bodies must be JSON strings.");
            }
            String bodyBase64 = hasUtf8
                    ? Base64.getEncoder().encodeToString(
                            node.get("body_utf8").textValue().getBytes(StandardCharsets.UTF_8))
                    : hasBase64 ? node.get("body_base64").textValue() : "";
            JsonNode statusesNode = node.path("expected_statuses");
            if (!statusesNode.isArray() || statusesNode.isEmpty()) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_STATUS_NOT_CONFIGURED",
                        "Every typed HTTP oracle case requires expected_statuses.");
            }
            Set<Integer> statuses = new LinkedHashSet<>();
            for (JsonNode status : statusesNode) {
                if (!status.isIntegralNumber() || !status.canConvertToInt()) {
                    throw blocked("SPRING_MVC_HTTP_ORACLE_STATUS_INVALID",
                            "Expected HTTP statuses must be integers.");
                }
                if (!statuses.add(status.intValue())) {
                    throw blocked("SPRING_MVC_HTTP_ORACLE_STATUS_DUPLICATE",
                            "Expected HTTP statuses must be unique exact integers.");
                }
            }
            String mode = requiredText(node, "body_mode");
            BodyMode bodyMode;
            try {
                bodyMode = BodyMode.valueOf(mode);
            } catch (IllegalArgumentException error) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_BODY_MODE_INVALID",
                        "body_mode must be EXACT_BYTES or JSP_UTF8_LINE_ENDINGS.");
            }
            JsonNode readinessNode = node.get("readiness");
            if (readinessNode != null && !readinessNode.isBoolean()) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_JSON_INVALID",
                        "The optional readiness field must be a JSON boolean.");
            }
            cases.add(new OracleCase(
                    requiredText(node, "id"),
                    requiredText(node, "method"),
                    requiredText(node, "path"),
                    headers,
                    bodyBase64,
                    statuses,
                    bodyMode,
                    readinessNode != null && readinessNode.booleanValue()));
        }
        return List.copyOf(cases);
    }

    private static String requiredText(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_JSON_INVALID",
                    "Every typed HTTP oracle case requires textual field " + field + ".");
        }
        return value.textValue();
    }

    private static void requireSafePath(String path) {
        if (!PATH.matcher(path).matches() || path.startsWith("//")
                || path.contains("#") || path.contains("\\")
                || path.contains("\r") || path.contains("\n")) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_PATH_INVALID",
                    "HTTP oracle paths must use the bounded safe absolute-path grammar.");
        }
        try {
            URI parsed = URI.create(path);
            String decodedPath = parsed.getPath();
            if (parsed.isAbsolute() || parsed.getRawAuthority() != null || decodedPath == null
                    || List.of(decodedPath.split("/")).contains("..")) {
                throw blocked("SPRING_MVC_HTTP_ORACLE_PATH_INVALID",
                        "HTTP oracle paths cannot contain an authority or parent traversal segment.");
            }
        } catch (IllegalArgumentException error) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_PATH_INVALID",
                    "HTTP oracle paths must be valid URI paths.");
        }
    }

    private static byte[] decodeBase64(String value, String code) {
        String canonical = trim(value);
        try {
            byte[] decoded = Base64.getDecoder().decode(canonical);
            if (!Base64.getEncoder().encodeToString(decoded).equals(canonical)) {
                throw blocked(code, "HTTP oracle body_base64 must use canonical padded Base64 bytes.");
            }
            return decoded;
        } catch (IllegalArgumentException error) {
            throw blocked(code, "HTTP oracle body_base64 must use canonical Base64 bytes.");
        }
    }

    private static byte[] strictUtf8(String value, String code) {
        try {
            ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(value));
            byte[] result = new byte[encoded.remaining()];
            encoded.get(result);
            return result;
        } catch (CharacterCodingException error) {
            throw blocked(code, "Typed JSON configuration must be strictly valid UTF-8 text.");
        }
    }

    private static JsonNode strictJsonTree(byte[] bytes, ObjectMapper mapper, String code) {
        ObjectMapper strict = mapper.copy().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
        try (JsonParser parser = strict.getFactory().createParser(bytes)) {
            JsonNode root = strict.readTree(parser);
            if (root == null || parser.nextToken() != null) {
                throw blocked(code, "JSON must contain exactly one value with no trailing token.");
            }
            return root;
        } catch (BlockedException error) {
            throw error;
        } catch (IOException | RuntimeException error) {
            throw blocked(code, "JSON must be valid, duplicate-key-free, and contain no trailing token.");
        }
    }

    private static boolean bodiesEqual(
            OracleCase oracleCase, OracleResponse source, OracleResponse target) {
        if (oracleCase.bodyMode() == BodyMode.EXACT_BYTES) {
            return MessageDigest.isEqual(source.body(), target.body());
        }
        requireJspContentType(source);
        requireJspContentType(target);
        return normalizeJsp(source.body()).equals(normalizeJsp(target.body()));
    }

    private static void requireJspContentType(OracleResponse response) {
        boolean html = response.headers().getOrDefault("content-type", List.of()).stream()
                .map(value -> value.toLowerCase(Locale.ROOT))
                .anyMatch(value -> value.startsWith("text/html")
                        || value.startsWith("application/xhtml+xml"));
        if (!html) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_JSP_CONTENT_TYPE_MISMATCH",
                    "JSP_UTF8_LINE_ENDINGS requires an HTML or XHTML response Content-Type.");
        }
    }

    private static String normalizeJsp(byte[] body) {
        try {
            String text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(body)).toString();
            if (text.startsWith("\uFEFF")) text = text.substring(1);
            return text.replace("\r\n", "\n").replace('\r', '\n');
        } catch (CharacterCodingException error) {
            throw blocked("SPRING_MVC_HTTP_ORACLE_JSP_UTF8_INVALID",
                    "JSP_UTF8_LINE_ENDINGS requires strictly valid UTF-8 response bytes.");
        }
    }

    private static void stopBounded(Process process, Control control, String label) {
        if (process == null || !process.isAlive()) return;
        process.destroy();
        try {
            if (!process.waitFor(15, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                if (!process.waitFor(5, TimeUnit.SECONDS)) {
                    throw blocked("SPRING_MVC_RUNTIME_SHUTDOWN_TIMEOUT",
                            "The " + label + " process did not stop inside the bounded shutdown window.");
                }
            }
            control.log(label + " stopped inside the bounded shutdown window");
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            process.destroyForcibly();
            throw blocked("RUN_CANCELLED", "The " + label + " shutdown was interrupted.");
        }
    }

    private static Map<String, List<String>> stableHeaders(Map<String, List<String>> headers) {
        Map<String, List<String>> stable = new LinkedHashMap<>();
        headers.entrySet().stream().sorted(Map.Entry.comparingByKey())
                .filter(entry -> !VOLATILE_RESPONSE_HEADERS.contains(entry.getKey().toLowerCase(Locale.ROOT)))
                .forEach(entry -> {
                    String name = entry.getKey().toLowerCase(Locale.ROOT);
                    List<String> values = entry.getValue();
                    if ("set-cookie".equals(name) && values.size() == 1
                            && EXACT_TOMCAT_SESSION_COOKIE.matcher(values.get(0)).matches()) {
                        values = List.of("JSESSIONID=<opaque>; Path=/; HttpOnly");
                    }
                    stable.put(name, values);
                });
        return Map.copyOf(stable);
    }

    static String consumedTomcatManifestSha256(Path home) {
        return tomcatContentManifest(home.toAbsolutePath().normalize()).digest();
    }

    private static TomcatContentManifest tomcatContentManifest(Path home) {
        Path propertiesPath = regular(home.resolve("conf/catalina.properties"),
                "SPRING_MVC_TOMCAT_INSTALLATION_INVALID");
        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(propertiesPath)) {
            properties.load(input);
        } catch (IOException error) {
            throw blocked("SPRING_MVC_TOMCAT_INSTALLATION_INVALID",
                    "Tomcat catalina.properties could not be inspected.");
        }
        if (!EXPECTED_COMMON_LOADER.equals(trim(properties.getProperty("common.loader")))
                || !trim(properties.getProperty("server.loader")).isEmpty()
                || !trim(properties.getProperty("shared.loader")).isEmpty()) {
            throw blocked("SPRING_MVC_TOMCAT_CLASSLOADER_UNBOUNDED",
                    "Tomcat classloader paths must be the exact bounded local lib defaults.");
        }

        List<TomcatContentFile> files = new ArrayList<>();
        files.add(contentFile(home, "bin/bootstrap.jar"));
        files.add(contentFile(home, "bin/tomcat-juli.jar"));
        for (String name : CONSUMED_TOMCAT_CONFIGURATION) {
            files.add(contentFile(home, "conf/" + name));
        }
        Path lib = home.resolve("lib").toAbsolutePath().normalize();
        if (!Files.isDirectory(lib, LinkOption.NOFOLLOW_LINKS)) {
            throw blocked("SPRING_MVC_TOMCAT_INSTALLATION_INVALID",
                    "The exact Tomcat lib directory is missing or unsafe.");
        }
        try (var stream = Files.list(lib)) {
            List<Path> jars = stream
                    .sorted(Comparator.comparing(path -> path.getFileName().toString())).toList();
            if (jars.isEmpty()) {
                throw blocked("SPRING_MVC_TOMCAT_INSTALLATION_INVALID",
                        "The exact Tomcat lib directory contains no runtime jars.");
            }
            for (Path jar : jars) {
                if (!jar.getFileName().toString().endsWith(".jar")
                        || !Files.isRegularFile(jar, LinkOption.NOFOLLOW_LINKS)) {
                    throw blocked("SPRING_MVC_TOMCAT_CLASSLOADER_UNBOUNDED",
                            "Tomcat lib may contain only manifest-bound regular jar files.");
                }
                files.add(contentFile(home, "lib/" + jar.getFileName()));
            }
        } catch (IOException error) {
            throw blocked("SPRING_MVC_TOMCAT_INSTALLATION_INVALID",
                    "The exact Tomcat lib directory could not be enumerated.");
        }
        files.sort(Comparator.comparing(TomcatContentFile::path));
        StringBuilder canonical = new StringBuilder();
        for (TomcatContentFile file : files) {
            canonical.append(file.path()).append('\t').append(file.bytes()).append('\t')
                    .append(file.sha256()).append('\n');
        }
        return new TomcatContentManifest(
                sha256(canonical.toString().getBytes(StandardCharsets.UTF_8)), files);
    }

    private static TomcatContentFile contentFile(Path home, String relative) {
        Path file = regular(home.resolve(relative), "SPRING_MVC_TOMCAT_INSTALLATION_INVALID");
        try {
            return new TomcatContentFile(relative, Files.size(file), sha256(file));
        } catch (IOException error) {
            throw blocked("SPRING_MVC_TOMCAT_INSTALLATION_INVALID",
                    "A consumed Tomcat file could not be measured.");
        }
    }

    private static void reverifyTomcat(VerifiedTomcat tomcat) {
        TomcatContentManifest current = tomcatContentManifest(tomcat.home());
        if (!MessageDigest.isEqual(current.digest().getBytes(StandardCharsets.US_ASCII),
                tomcat.consumedManifestDigest().getBytes(StandardCharsets.US_ASCII))
                || !current.files().equals(tomcat.consumedFiles())
                || !tomcat.digest().equals(sha256(tomcat.home().resolve("lib/catalina.jar")))
                || !tomcat.version().equals(implementationVersion(
                        tomcat.home().resolve("lib/catalina.jar")))) {
            throw blocked("SPRING_MVC_TOMCAT_INSTALLATION_CHANGED",
                    "Tomcat consumed files changed after approval and before process start.");
        }
    }

    private static void verifyMaterializedTomcatBase(
            VerifiedTomcat tomcat, Path base, Path sourceWar, int port) {
        verifyInitialCatalinaBaseAllowlist(base);
        for (String name : CONSUMED_TOMCAT_CONFIGURATION) {
            TomcatContentFile approved = tomcat.consumedFiles().stream()
                    .filter(file -> file.path().equals("conf/" + name)).findFirst()
                    .orElseThrow(() -> blocked("SPRING_MVC_TOMCAT_MANIFEST_INCOMPLETE",
                            "The approved Tomcat manifest omits conf/" + name + "."));
            Path copied = regular(base.resolve("conf").resolve(name),
                    "SPRING_MVC_CATALINA_BASE_CREATION_FAILED");
            try {
                if (Files.size(copied) != approved.bytes()
                        || !approved.sha256().equals(sha256(copied))) {
                    throw blocked("SPRING_MVC_CATALINA_BASE_DIGEST_MISMATCH",
                            "A copied Tomcat configuration file does not match its approved digest.");
                }
            } catch (IOException error) {
                throw blocked("SPRING_MVC_CATALINA_BASE_CREATION_FAILED",
                        "A copied Tomcat configuration file could not be measured.");
            }
        }
        if (!sha256(sourceWar).equals(sha256(base.resolve("webapps/ROOT.war")))) {
            throw blocked("SPRING_MVC_CATALINA_BASE_DIGEST_MISMATCH",
                    "The deployed source WAR does not match the verified build artifact.");
        }
        try {
            if (!serverXml(port).equals(Files.readString(
                    base.resolve("conf/server.xml"), StandardCharsets.UTF_8))) {
                throw blocked("SPRING_MVC_CATALINA_BASE_DIGEST_MISMATCH",
                        "The generated loopback-only server.xml changed during materialization.");
            }
        } catch (IOException error) {
            throw blocked("SPRING_MVC_CATALINA_BASE_CREATION_FAILED",
                    "The generated loopback-only server.xml could not be verified.");
        }
    }

    private static boolean isEmptyDirectory(Path directory) throws IOException {
        try (var entries = Files.list(directory)) {
            return entries.findAny().isEmpty();
        }
    }

    static void verifyInitialCatalinaBaseAllowlist(Path base) {
        try {
            Path normalized = base.toAbsolutePath().normalize();
            if (Files.isSymbolicLink(normalized)
                    || !Files.isDirectory(normalized, LinkOption.NOFOLLOW_LINKS)) {
                throw blocked("SPRING_MVC_CATALINA_BASE_CONFINEMENT_FAILED",
                        "CATALINA_BASE must remain a real directory.");
            }
            Path realBase = normalized.toRealPath();
            Set<String> directories = new LinkedHashSet<>();
            Set<String> files = new LinkedHashSet<>();
            try (var paths = Files.walk(realBase)) {
                for (Path path : paths.toList()) {
                    if (Files.isSymbolicLink(path)) {
                        throw blocked("SPRING_MVC_CATALINA_BASE_CONFINEMENT_FAILED",
                                "CATALINA_BASE may not contain symbolic links.");
                    }
                    Path real = path.toRealPath(LinkOption.NOFOLLOW_LINKS);
                    if (!real.startsWith(realBase)) {
                        throw blocked("SPRING_MVC_CATALINA_BASE_CONFINEMENT_FAILED",
                                "Every CATALINA_BASE entry must remain inside its real path.");
                    }
                    String relative = realBase.relativize(real).toString().replace('\\', '/');
                    if (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                        directories.add(relative);
                    } else if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                        files.add(relative);
                    } else {
                        throw blocked("SPRING_MVC_CATALINA_BASE_UNEXPECTED_CONTENT",
                                "CATALINA_BASE contains an unsupported filesystem entry.");
                    }
                }
            }
            if (!directories.equals(INITIAL_CATALINA_BASE_DIRECTORIES)
                    || !files.equals(INITIAL_CATALINA_BASE_FILES)
                    || Files.exists(realBase.resolve("lib"), LinkOption.NOFOLLOW_LINKS)
                    || Files.exists(realBase.resolve("conf/Catalina"), LinkOption.NOFOLLOW_LINKS)) {
                throw blocked("SPRING_MVC_CATALINA_BASE_UNEXPECTED_CONTENT",
                        "Fresh CATALINA_BASE must contain only the exact copied configuration and ROOT.war allowlist.");
            }
        } catch (BlockedException error) {
            throw error;
        } catch (IOException error) {
            throw blocked("SPRING_MVC_CATALINA_BASE_CONFINEMENT_FAILED",
                    "CATALINA_BASE real-path confinement could not be verified.");
        }
    }

    private static Path regular(Path path, String code) {
        Path normalized = path.toAbsolutePath().normalize();
        if (!Files.isRegularFile(normalized, LinkOption.NOFOLLOW_LINKS)) {
            throw blocked(code, "The exact Tomcat installation is incomplete or contains an unsafe link.");
        }
        return normalized;
    }

    private static String implementationVersion(Path jar) {
        try (ZipFile archive = new ZipFile(jar.toFile())) {
            var entry = archive.getEntry("META-INF/MANIFEST.MF");
            if (entry == null) return "";
            Manifest manifest = new Manifest(archive.getInputStream(entry));
            return trim(manifest.getMainAttributes().getValue(Attributes.Name.IMPLEMENTATION_VERSION));
        } catch (IOException error) {
            throw blocked("SPRING_MVC_TOMCAT_INSTALLATION_INVALID",
                    "Tomcat catalina.jar metadata could not be read.");
        }
    }

    private static String serverXml(int port) {
        return """
                <?xml version="1.0" encoding="UTF-8"?>
                <Server port="-1" shutdown="ELMOS_DISABLED">
                  <Service name="Catalina">
                    <Connector address="127.0.0.1" port="%d" protocol="HTTP/1.1"
                               connectionTimeout="20000" maxParameterCount="1000" />
                    <Engine name="Catalina" defaultHost="localhost">
                      <Host name="localhost" appBase="webapps" unpackWARs="true"
                            autoDeploy="false" deployOnStartup="true"
                            deployXML="false" copyXML="false" />
                    </Engine>
                  </Service>
                </Server>
                """.formatted(port);
    }

    private static int reservePort() {
        try (var socket = new java.net.ServerSocket()) {
            socket.bind(new InetSocketAddress("127.0.0.1", 0));
            return socket.getLocalPort();
        } catch (IOException error) {
            throw blocked("RUNTIME_PORT_UNAVAILABLE", "A loopback runtime port could not be reserved.");
        }
    }

    private static String sha256(Path path) {
        try (InputStream input = Files.newInputStream(path)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[8192];
            for (int read; (read = input.read(buffer)) >= 0;) {
                if (read > 0) digest.update(buffer, 0, read);
            }
            return hex(digest.digest());
        } catch (IOException error) {
            throw blocked("SPRING_MVC_TOMCAT_INSTALLATION_INVALID", "The configured artifact could not be hashed.");
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static String sha256(byte[] value) {
        try {
            return hex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    private static String hex(byte[] digest) {
        StringBuilder result = new StringBuilder(64);
        for (byte current : digest) result.append(String.format("%02x", current));
        return result.toString();
    }

    private static String trim(String value) { return value == null ? "" : value.trim(); }

    private static BlockedException blocked(String code, String message) {
        return new BlockedException(code, message);
    }

    /** Keeps checked file operations concise without hiding their fail-closed caller handling. */
    private static final class Filesystem {
        private Filesystem() {}
        static void createDirectories(Path path) {
            try {
                Files.createDirectories(path);
            } catch (IOException error) {
                throw blocked("SPRING_MVC_RUNTIME_DIRECTORY_FAILED",
                        "A per-run Spring MVC runtime directory could not be created.");
            }
        }
    }
}
