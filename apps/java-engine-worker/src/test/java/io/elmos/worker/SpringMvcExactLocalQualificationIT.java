package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.jar.Attributes;
import java.util.jar.JarFile;

import static io.elmos.worker.SpringUpgradeModels.SourceMode;
import static io.elmos.worker.SpringUpgradeModels.Stage;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Explicit, environment-provisioned local qualification for the single exact
 * Spring Framework 5.3.39 MVC WAR to Spring Boot 3.5.3 executable-WAR route.
 *
 * <p>The class name deliberately ends in {@code IT}; it is not part of the
 * default Surefire scan. An operator must name it explicitly and provision the
 * exact JDK, Maven and digest-bound Tomcat inputs. Its maximum claim is local
 * engineering evidence. It never produces certification or external evidence.</p>
 */
class SpringMvcExactLocalQualificationIT {
    private static final long GIB = 1024L * 1024L * 1024L;
    private static final long START_FLOOR = 10L * GIB;
    private static final long HARD_STOP_FLOOR = 8L * GIB;

    @Test
    void executesExactSourceRewriteMaterializerTargetAndRuntimeOracle() throws Exception {
        Path qualificationRoot = absoluteDirectory("ELMOS_MVC_QUALIFICATION_ROOT");
        Path sourceJavaHome = absoluteDirectory("ELMOS_MVC_SOURCE_JAVA_HOME");
        Path targetJavaHome = absoluteDirectory("ELMOS_MVC_TARGET_JAVA_HOME");
        Path maven = absoluteRegularFile("ELMOS_MVC_MAVEN_EXECUTABLE");
        Path mavenArchive = absoluteRegularFile("ELMOS_MVC_MAVEN_ARCHIVE");
        Path tomcatArchive = absoluteRegularFile("ELMOS_MVC_TOMCAT_ARCHIVE");
        Path tomcatHome = absoluteDirectory("ELMOS_MVC_TOMCAT_HOME");
        Path harnessRoot = absoluteDirectory("ELMOS_MVC_HARNESS_ROOT");
        String sourceRelative = required("ELMOS_MVC_SOURCE_RELATIVE_PATH");
        String sourceCommit = required("ELMOS_MVC_SOURCE_COMMIT");
        String harnessCommit = required("ELMOS_MVC_HARNESS_COMMIT");
        String tomcatVersion = required("ELMOS_MVC_TOMCAT_VERSION");
        assertTrue(sourceCommit.matches("[0-9a-f]{40}"));
        assertTrue(harnessCommit.matches("[0-9a-f]{40}"));
        assertEquals("9.0.120", tomcatVersion);
        requireCapacity(qualificationRoot, START_FLOOR, "qualification start");

        ObjectMapper json = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);
        String catalinaSha256 = digest(tomcatHome.resolve("lib/catalina.jar"), "SHA-256");
        String consumedTomcatManifestSha256 =
                SpringMvcWarRuntime.consumedTomcatManifestSha256(tomcatHome);
        SpringMvcWarRuntime.Configuration runtime = SpringMvcWarRuntime.Configuration.of(
                tomcatHome.toString(),
                tomcatVersion,
                catalinaSha256,
                consumedTomcatManifestSha256,
                "",
                oracleCases(),
                json);

        LocalSpringUpgradeExecutionPort port = new LocalSpringUpgradeExecutionPort(
                qualificationRoot,
                Map.of("11", sourceJavaHome, "21", targetJavaHome),
                maven.toString(),
                "gradle",
                Set.of(),
                false,
                false,
                null,
                true,
                json,
                new DisabledSpringUpgradeCodingAgentPort("local qualification keeps coding agents disabled"),
                runtime);
        SpringUpgradeModels.StartRequest request = new SpringUpgradeModels.StartRequest(
                "elmos-local-engineering",
                SourceMode.MATERIALIZED_SNAPSHOT,
                "",
                "",
                sourceCommit,
                null,
                sourceRelative,
                false,
                "spring-mvc-exact-local-qualification",
                "3.5.3",
                "21");
        Path runRoot = qualificationRoot.resolve("runs/spring-mvc-5.3.39-to-boot-3.5.3");
        if (Files.exists(runRoot, LinkOption.NOFOLLOW_LINKS)) {
            assertTrue(Files.isDirectory(runRoot, LinkOption.NOFOLLOW_LINKS)
                    && !Files.isSymbolicLink(runRoot));
            try (var children = Files.list(runRoot)) {
                assertTrue(children.allMatch(path -> path.getFileName().toString().equals("maven-home")
                                && Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                                && !Files.isSymbolicLink(path)),
                        "a retried qualification may retain only its isolated Maven dependency cache");
            }
        }

        SpringUpgradeModels.ExecutionResult result;
        QualificationControl control = new QualificationControl(qualificationRoot);
        try (control) {
            result = port.execute(request, runRoot, control);
        }
        Files.writeString(runRoot.resolve("evidence/control.log"),
                String.join("\n", control.lines()) + "\n", StandardCharsets.UTF_8);

        assertEquals("spring-mvc", result.fingerprint().sourceFrameworkFamily());
        assertEquals("5.3.39", result.fingerprint().sourceFrameworkVersion());
        assertEquals("11", SpringRouteCatalog.normalizeJava(result.fingerprint().javaVersion()));
        assertTrue(Files.isRegularFile(result.downloadArtifact(), LinkOption.NOFOLLOW_LINKS));
        assertEquals(result.artifactSha256(), digest(result.downloadArtifact(), "SHA-256"));
        Path executedWar = SpringMvcWarRuntime.executableBootWar(
                result.migratedRepository(), SpringRouteCatalog.MAVEN_BUILD_TOOL);
        Map<String, String> executedWarManifest = executableWarManifest(executedWar);
        assertEquals(SpringMvcWarRuntime.WAR_LAUNCHER, executedWarManifest.get("Main-Class"));
        assertEquals("io.elmos.legacy.LegacyMvcApplication", executedWarManifest.get("Start-Class"));
        assertEquals("3.5.3", executedWarManifest.get("Spring-Boot-Version"));
        JsonNode oracle = json.readTree(runRoot.resolve("evidence/spring-mvc-http-oracle.json").toFile());
        assertEquals("PASS_LOCAL_ENGINEERING", oracle.path("status").asText());
        assertEquals(2, oracle.path("comparisons").size());
        assertTrue(Files.size(runRoot.resolve("evidence/source-startup.log")) > 0);
        assertTrue(Files.size(runRoot.resolve("evidence/target-startup.log")) > 0);

        Path expectedDownloadArtifact = runRoot.resolve(
                "artifacts/migrated-spring-boot-3.5.3.zip").toAbsolutePath().normalize();
        assertEquals(expectedDownloadArtifact,
                result.downloadArtifact().toAbsolutePath().normalize());
        Path preservedExecutedWar = runRoot.resolve(
                "artifacts/executed-spring-boot-3.5.3.war");
        preserveExact(executedWar, preservedExecutedWar);
        assertEquals(Files.size(executedWar), Files.size(preservedExecutedWar));
        assertEquals(digest(executedWar, "SHA-256"),
                digest(preservedExecutedWar, "SHA-256"));

        Path materializerReceipt = result.migratedRepository()
                .resolve(".elmos/migration-receipt.json");
        Path materializerSourceMap = result.migratedRepository().resolve(".elmos/source-map.json");
        Path preservedMaterializerReceipt = runRoot.resolve(
                "evidence/target-materialization-receipt.json");
        Path preservedMaterializerSourceMap = runRoot.resolve(
                "evidence/target-materialization-source-map.json");
        preserveExact(materializerReceipt, preservedMaterializerReceipt);
        preserveExact(materializerSourceMap, preservedMaterializerSourceMap);
        assertControlledTargetProfileBindings(json.readTree(
                preservedMaterializerReceipt.toFile()));

        List<Map<String, Object>> evidenceFiles = evidenceInventory(runRoot);
        Map<String, Object> receipt = new LinkedHashMap<>();
        receipt.put("schema_version", "1.1");
        receipt.put("status", "PASSED_LOCAL");
        receipt.put("claim_scope", "LOCAL_ENGINEERING_EXACT_FIXTURE_ONLY");
        receipt.put("certified", false);
        receipt.put("external_execution_status", "NOT_RUN");
        receipt.put("observed_at", Instant.now().toString());
        receipt.put("source_commit", sourceCommit);
        receipt.put("source_snapshot_sha256", result.snapshotDigest());
        receipt.put("route_id", SpringMvcWarRuntime.ROUTE_ID);
        receipt.put("pack_key", SpringMvcExactTargetMaterializer.PACK_KEY);
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("spring_framework", "5.3.39");
        source.put("java", toolOutput(sourceJavaHome.resolve("bin/java"), "-version"));
        source.put("maven", toolOutput(maven, sourceJavaHome, "-version"));
        source.put("maven_archive", archiveEvidence(mavenArchive));
        source.put("tomcat", tomcatVersion);
        source.put("tomcat_archive", archiveEvidence(tomcatArchive));
        source.put("catalina_jar", fileEvidence(tomcatHome, tomcatHome.resolve("lib/catalina.jar")));
        source.put("tomcat_consumed_manifest_sha256", consumedTomcatManifestSha256);
        receipt.put("source", source);
        Map<String, Object> target = new LinkedHashMap<>();
        target.put("spring_boot", "3.5.3");
        target.put("spring_framework", "6.2.8");
        target.put("embedded_tomcat", "10.1.42");
        target.put("java", toolOutput(targetJavaHome.resolve("bin/java"), "-version"));
        target.put("maven", toolOutput(maven, targetJavaHome, "-version"));
        target.put("download_artifact", Map.of(
                "path", runRoot.relativize(result.downloadArtifact()).toString().replace('\\', '/'),
                "format", "migrated-repository-zip",
                "sha256", result.artifactSha256(),
                "bytes", result.artifactSize()));
        target.put("executed_war", Map.of(
                "path", runRoot.relativize(preservedExecutedWar).toString().replace('\\', '/'),
                "format", "spring-boot-executable-war",
                "sha256", digest(preservedExecutedWar, "SHA-256"),
                "bytes", Files.size(preservedExecutedWar),
                "manifest", executedWarManifest));
        receipt.put("target", target);
        receipt.put("harness", Map.of(
                "repository_head", harnessCommit,
                "worktree_binding", "repository-head-plus-content-addressed-files",
                "files", harnessInventory(harnessRoot)));
        receipt.put("execution", Map.of(
                "source_clean_verify", "PASSED",
                "source_tomcat_startup", "PASSED",
                "openrewrite_actual_execution", true,
                "trusted_java_materializer", "PASSED",
                "target_clean_verify", "PASSED",
                "target_warlauncher_startup", "PASSED",
                "target_actuator_health", "PASSED",
                "get_and_jsp_oracle_comparisons", 2,
                "validation_and_error_contract_tests", "PASSED",
                "bounded_shutdown", "PASSED"));
        receipt.put("evidence_files", evidenceFiles);
        json.writeValue(runRoot.resolve("local-qualification.json").toFile(), receipt);
        System.out.println("ELMOS_MVC_QUALIFICATION_RECEIPT="
                + runRoot.resolve("local-qualification.json"));
    }

    private static Map<String, String> executableWarManifest(Path war) throws IOException {
        try (JarFile archive = new JarFile(war.toFile())) {
            Attributes attributes = archive.getManifest().getMainAttributes();
            return Map.of(
                    "Main-Class", attributes.getValue(Attributes.Name.MAIN_CLASS),
                    "Start-Class", attributes.getValue("Start-Class"),
                    "Spring-Boot-Version", attributes.getValue("Spring-Boot-Version"));
        }
    }

    private static List<Map<String, Object>> harnessInventory(Path root) throws IOException {
        List<String> relatives = List.of(
                "apps/java-engine-worker/src/main/java/io/elmos/worker/LocalSpringUpgradeExecutionPort.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringDeploymentGuidance.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringMvcExactTargetMaterializer.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringMvcWarRuntime.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java",
                "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringUpgradeModels.java",
                "apps/java-engine-worker/src/main/resources/rewrite/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml",
                "apps/java-engine-worker/src/main/resources/spring-mvc/exact-5.3.39-fixture-manifest.json",
                "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/profile.json",
                "apps/java-engine-worker/src/main/resources/spring-mvc/target-profile/scaffold-manifest.json",
                "apps/java-engine-worker/src/test/java/io/elmos/worker/SpringMvcExactLocalQualificationIT.java");
        List<Map<String, Object>> files = new ArrayList<>();
        for (String relative : relatives) {
            files.add(fileEvidence(root, root.resolve(relative)));
        }
        return List.copyOf(files);
    }

    private static void preserveExact(Path source, Path target) throws IOException {
        assertTrue(Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(source),
                "preserved evidence source must be a real regular file: " + source);
        assertTrue(!Files.exists(target, LinkOption.NOFOLLOW_LINKS),
                "preserved evidence target must not already exist: " + target);
        Files.createDirectories(target.getParent());
        Files.copy(source, target);
        assertTrue(Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(target),
                "preserved evidence target must be a real regular file: " + target);
        assertEquals(Files.size(source), Files.size(target));
        assertEquals(digest(source, "SHA-256"), digest(target, "SHA-256"));
    }

    private static void assertControlledTargetProfileBindings(JsonNode receipt) {
        assertEquals("spring-framework-5-3-mvc-to-spring-boot-3-5-3",
                receipt.path("pack_key").asText());
        assertEquals("MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED",
                receipt.path("status").asText());
        JsonNode generator = receipt.path("generator_binding");
        assertEquals("c49c796656a34391b892b4a61973161aafce778a4cfc742e5dfb1f0e2eb27f24",
                generator.path("materializer_contract_sha256").asText());
        JsonNode profiles = generator.path("controlled_target_profile_resources");
        assertTrue(profiles.isArray());
        assertEquals(2, profiles.size());
        assertEquals("classpath:/spring-mvc/target-profile/profile.json",
                profiles.get(0).path("resource").asText());
        assertEquals(3731, profiles.get(0).path("bytes").asLong());
        assertEquals("4856d1c012274be15fa9339a4a11524314994ca858e2b7856fcd367fb1de63a5",
                profiles.get(0).path("sha256").asText());
        assertEquals("classpath:/spring-mvc/target-profile/scaffold-manifest.json",
                profiles.get(1).path("resource").asText());
        assertEquals(1773, profiles.get(1).path("bytes").asLong());
        assertEquals("a2e741b1a535c690633b27e0301f6931ad287e2b0ddd3fefb97cb5194d5819d6",
                profiles.get(1).path("sha256").asText());
    }

    private static Map<String, Object> fileEvidence(Path root, Path path) throws IOException {
        Path normalizedRoot = root.toAbsolutePath().normalize();
        Path normalized = path.toAbsolutePath().normalize();
        assertTrue(normalized.startsWith(normalizedRoot)
                        && Files.isRegularFile(normalized, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(normalized),
                "evidence file must be a real regular file below its declared root: " + normalized);
        return Map.of(
                "path", normalizedRoot.relativize(normalized).toString().replace('\\', '/'),
                "bytes", Files.size(normalized),
                "sha256", digest(normalized, "SHA-256"));
    }

    private static Map<String, Object> archiveEvidence(Path path) throws IOException {
        return Map.of(
                "path", path.toAbsolutePath().normalize().toString(),
                "bytes", Files.size(path),
                "sha256", digest(path, "SHA-256"),
                "sha512", digest(path, "SHA-512"));
    }

    private static String oracleCases() {
        return """
                [
                  {
                    "id": "source-readiness-order-42",
                    "method": "GET",
                    "path": "/api/orders/42",
                    "headers": {"accept": "application/json"},
                    "expected_statuses": [200],
                    "body_mode": "EXACT_BYTES",
                    "readiness": true
                  },
                  {
                    "id": "odd-order-review",
                    "method": "GET",
                    "path": "/api/orders/7",
                    "headers": {"accept": "application/json"},
                    "expected_statuses": [200],
                    "body_mode": "EXACT_BYTES"
                  },
                  {
                    "id": "jsp-order-list",
                    "method": "GET",
                    "path": "/orders",
                    "headers": {"accept": "text/html"},
                    "expected_statuses": [200],
                    "body_mode": "JSP_UTF8_LINE_ENDINGS"
                  }
                ]
                """;
    }

    private static List<Map<String, Object>> evidenceInventory(Path runRoot) throws IOException {
        List<Path> paths;
        try (var stream = Files.walk(runRoot.resolve("evidence"))) {
            paths = stream.filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                    .sorted(Comparator.comparing(path -> runRoot.relativize(path).toString()))
                    .toList();
        }
        List<Map<String, Object>> files = new ArrayList<>();
        for (Path path : paths) {
            files.add(Map.of(
                    "path", runRoot.relativize(path).toString().replace('\\', '/'),
                    "bytes", Files.size(path),
                    "sha256", digest(path, "SHA-256")));
        }
        return List.copyOf(files);
    }

    private static String toolOutput(Path executable, String argument) throws Exception {
        Process process = new ProcessBuilder(executable.toString(), argument).redirectErrorStream(true).start();
        byte[] output = process.getInputStream().readAllBytes();
        assertTrue(process.waitFor(15, java.util.concurrent.TimeUnit.SECONDS));
        assertEquals(0, process.exitValue());
        return new String(output, StandardCharsets.UTF_8).trim();
    }

    private static String toolOutput(Path executable, Path javaHome, String argument) throws Exception {
        ProcessBuilder builder = new ProcessBuilder(executable.toString(), argument).redirectErrorStream(true);
        builder.environment().put("JAVA_HOME", javaHome.toString());
        Process process = builder.start();
        byte[] output = process.getInputStream().readAllBytes();
        assertTrue(process.waitFor(15, java.util.concurrent.TimeUnit.SECONDS));
        assertEquals(0, process.exitValue());
        return new String(output, StandardCharsets.UTF_8).trim();
    }

    private static String digest(Path path, String algorithm) throws IOException {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance(algorithm);
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) >= 0) digest.update(buffer, 0, read);
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static Path absoluteDirectory(String name) {
        Path path = Path.of(required(name));
        assertTrue(path.isAbsolute() && Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                && !Files.isSymbolicLink(path), name + " must be an absolute real directory");
        return path.toAbsolutePath().normalize();
    }

    private static Path absoluteRegularFile(String name) {
        Path path = Path.of(required(name));
        assertTrue(path.isAbsolute() && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                && !Files.isSymbolicLink(path), name + " must be an absolute regular file");
        return path.toAbsolutePath().normalize();
    }

    private static String required(String name) {
        String value = System.getenv(name);
        assertTrue(value != null && !value.isBlank(), name + " is required");
        return value.trim();
    }

    private static void requireCapacity(Path path, long floor, String stage) throws IOException {
        FileStore store = Files.getFileStore(path);
        assertTrue(store.getUsableSpace() >= floor,
                stage + " requires at least " + floor + " usable bytes; found " + store.getUsableSpace());
    }

    private static final class QualificationControl
            implements SpringUpgradeExecutionPort.Control, AutoCloseable {
        private final Path capacityPath;
        private final CopyOnWriteArrayList<String> lines = new CopyOnWriteArrayList<>();
        private final Set<Process> processes = ConcurrentHashMap.newKeySet();
        private final AtomicBoolean closed = new AtomicBoolean();
        private final AtomicBoolean capacityStop = new AtomicBoolean();
        private final Thread monitor;

        QualificationControl(Path capacityPath) {
            this.capacityPath = capacityPath;
            this.monitor = Thread.ofPlatform().daemon().name("mvc-capacity-monitor").start(() -> {
                while (!closed.get()) {
                    try {
                        long usable = Files.getFileStore(capacityPath).getUsableSpace();
                        if (usable <= HARD_STOP_FLOOR) {
                            capacityStop.set(true);
                            log("CAPACITY_HARD_STOP usable_bytes=" + usable);
                            processes.stream().filter(Process::isAlive).forEach(Process::destroyForcibly);
                            return;
                        }
                        Thread.sleep(1_000);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        return;
                    } catch (IOException error) {
                        capacityStop.set(true);
                        log("CAPACITY_MONITOR_FAILED " + error.getClass().getSimpleName());
                        processes.stream().filter(Process::isAlive).forEach(Process::destroyForcibly);
                        return;
                    }
                }
            });
        }

        @Override public void stage(Stage stage, String message) {
            log("STAGE " + stage + " " + message);
        }

        @Override public void log(String line) {
            String bounded = line == null ? "" : line.replace('\r', ' ').replace('\n', ' ');
            if (bounded.length() > 16_384) bounded = bounded.substring(0, 16_384);
            lines.add(bounded);
            System.out.println(bounded);
        }

        @Override public void process(Process process) {
            if (process != null) processes.add(process);
        }

        @Override public boolean cancelled() {
            return capacityStop.get();
        }

        List<String> lines() {
            return List.copyOf(lines);
        }

        @Override public void close() throws InterruptedException {
            closed.set(true);
            monitor.interrupt();
            monitor.join(5_000);
            processes.stream().filter(Process::isAlive).forEach(Process::destroyForcibly);
        }
    }
}
