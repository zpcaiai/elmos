package io.elmos.worker.reactive;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Spring Reactive Blocking Call Auditor & Isolation Modernizer.
 *
 * <p>Audits and remediates critical thread-blocking anti-patterns in Spring WebFlux,
 * Spring Cloud Gateway, and Reactive Streams architectures:
 * <ol>
 *   <li><b>Explicit Reactor Blocking Calls:</b>
 *       Detects fatal {@code Mono.block()} and {@code Flux.blockFirst()/blockLast()} invocations on EventLoop threads.</li>
 *   <li><b>Synchronous I/O & Thread Sleep:</b>
 *       Flags {@code Thread.sleep()}, {@code RestTemplate}, and synchronous {@code JdbcTemplate} calls.</li>
 *   <li><b>Elastic Scheduler Offloading:</b>
 *       Automatically wraps blocking calls with {@code Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())}.</li>
 *   <li><b>BlockHound Test Harness Integration:</b>
 *       Injects BlockHound test dependency and generates {@code BlockHoundIntegrationTestCustomizer} to detect
 *       runtime thread stalls deterministically in CI/CD.</li>
 * </ol>
 */
public final class SpringReactiveBlockingCallAuditor {

    public enum BlockingType {
        EXPLICIT_MONO_FLUX_BLOCK,
        THREAD_SLEEP,
        REST_TEMPLATE_CALL,
        JDBC_BLOCKING_CALL,
        SYNC_FILE_IO
    }

    public record BlockingFinding(
            String filePath,
            int lineNumber,
            BlockingType type,
            String message,
            String snippet
    ) {}

    public record ReactiveAuditResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<BlockingFinding> findings,
            List<String> generatedArtifacts
    ) {
        public static ReactiveAuditResult empty() {
            return new ReactiveAuditResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern EXPLICIT_BLOCK_PATTERN = Pattern.compile(
            "\\.(?:block|blockFirst|blockLast|toIterable|toStream)\\s*\\("
    );

    private static final Pattern THREAD_SLEEP_PATTERN = Pattern.compile(
            "Thread\\.sleep\\s*\\("
    );

    private static final Pattern REST_TEMPLATE_PATTERN = Pattern.compile(
            "restTemplate\\.(?:getForObject|postForObject|exchange|execute|getForEntity|postForEntity)\\s*\\("
    );

    private static final Pattern JDBC_TEMPLATE_PATTERN = Pattern.compile(
            "jdbcTemplate\\.(?:query|queryForObject|queryForList|queryForRowSet|update|batchUpdate|execute)\\s*\\("
    );

    private static final String BLOCKHOUND_DEPENDENCY =
            """
                    <dependency>
                        <groupId>io.projectreactor.tools</groupId>
                        <artifactId>blockhound</artifactId>
                        <version>1.0.9.RELEASE</version>
                        <scope>test</scope>
                    </dependency>""";

    /**
     * Audits and remediates reactive blocking calls across the workspace.
     */
    public ReactiveAuditResult auditAndRemediate(Path projectRoot) throws IOException {
        return auditAndRemediate(projectRoot, true);
    }

    public ReactiveAuditResult auditAndRemediate(Path projectRoot, boolean updatePom) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return ReactiveAuditResult.empty();
        }

        boolean anyModified = false;
        int totalChanges = 0;
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<BlockingFinding> findings = new ArrayList<>();
        List<String> generatedArtifacts = new ArrayList<>();

        // 1. Scan Java files for reactive code and blocking patterns
        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                String source = Files.readString(javaFile, StandardCharsets.UTF_8);
                boolean isReactiveFile = source.contains("reactor.core.publisher.Mono")
                        || source.contains("reactor.core.publisher.Flux")
                        || source.contains("org.springframework.web.reactive")
                        || source.contains("Mono<")
                        || source.contains("Flux<");

                if (!isReactiveFile) {
                    continue;
                }

                String[] lines = source.split("\n", -1);
                for (int i = 0; i < lines.length; i++) {
                    String line = lines[i];
                    int lineNum = i + 1;

                    // Audit explicit block calls
                    Matcher blockMatcher = EXPLICIT_BLOCK_PATTERN.matcher(line);
                    if (blockMatcher.find()) {
                        findings.add(new BlockingFinding(
                                projectRoot.relativize(javaFile).toString().replace('\\', '/'),
                                lineNum,
                                BlockingType.EXPLICIT_MONO_FLUX_BLOCK,
                                "Direct .block() or terminal stream operation inside reactive component pins EventLoop thread",
                                line.trim()
                        ));
                    }

                    // Audit Thread.sleep
                    Matcher sleepMatcher = THREAD_SLEEP_PATTERN.matcher(line);
                    if (sleepMatcher.find()) {
                        findings.add(new BlockingFinding(
                                projectRoot.relativize(javaFile).toString().replace('\\', '/'),
                                lineNum,
                                BlockingType.THREAD_SLEEP,
                                "Thread.sleep blocks reactive Netty worker thread; should use Mono.delay or boundedElastic",
                                line.trim()
                        ));
                    }

                    // Audit RestTemplate
                    Matcher restMatcher = REST_TEMPLATE_PATTERN.matcher(line);
                    if (restMatcher.find()) {
                        findings.add(new BlockingFinding(
                                projectRoot.relativize(javaFile).toString().replace('\\', '/'),
                                lineNum,
                                BlockingType.REST_TEMPLATE_CALL,
                                "Synchronous RestTemplate call inside reactive pipeline; should migrate to WebClient or isolate on boundedElastic",
                                line.trim()
                        ));
                    }

                    // Audit JdbcTemplate
                    Matcher jdbcMatcher = JDBC_TEMPLATE_PATTERN.matcher(line);
                    if (jdbcMatcher.find()) {
                        findings.add(new BlockingFinding(
                                projectRoot.relativize(javaFile).toString().replace('\\', '/'),
                                lineNum,
                                BlockingType.JDBC_BLOCKING_CALL,
                                "Synchronous JdbcTemplate query pins EventLoop; wrap in Mono.fromCallable().subscribeOn(Schedulers.boundedElastic()) or migrate to R2DBC",
                                line.trim()
                        ));
                    }
                }

                // Automatic Remediation: wrap raw RestTemplate or JdbcTemplate in Mono.fromCallable offload
                boolean fileChanged = false;
                if (source.contains("restTemplate.") && source.contains("return restTemplate.")) {
                    source = source.replaceAll(
                            "return\\s+(restTemplate\\.[^;]+);",
                            "return reactor.core.publisher.Mono.fromCallable(() -> $1).subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());"
                    );
                    fileChanged = true;
                    totalChanges++;
                    rulesApplied.add("WRAP_BLOCKING_REST_TEMPLATE_ON_BOUNDED_ELASTIC");
                }

                if (source.contains("jdbcTemplate.") && source.contains("return jdbcTemplate.")) {
                    source = source.replaceAll(
                            "return\\s+(jdbcTemplate\\.[^;]+);",
                            "return reactor.core.publisher.Mono.fromCallable(() -> $1).subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());"
                    );
                    fileChanged = true;
                    totalChanges++;
                    rulesApplied.add("WRAP_BLOCKING_JDBC_ON_BOUNDED_ELASTIC");
                }

                if (fileChanged) {
                    Files.writeString(javaFile, source, StandardCharsets.UTF_8);
                    anyModified = true;
                    modifiedFiles.add(projectRoot.relativize(javaFile).toString().replace('\\', '/'));
                }
            }
        }

        // 2. Inject BlockHound test dependency in pom.xml if WebFlux project and permitted
        Path pomFile = projectRoot.resolve("pom.xml");
        if (updatePom && Files.isRegularFile(pomFile)) {
            String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
            if (pomContent.contains("spring-boot-starter-webflux") && !pomContent.contains("blockhound")) {
                int depEnd = pomContent.indexOf("</dependencies>");
                if (depEnd != -1) {
                    String updatedPom = pomContent.substring(0, depEnd)
                            + BLOCKHOUND_DEPENDENCY + "\n    "
                            + pomContent.substring(depEnd);
                    Files.writeString(pomFile, updatedPom, StandardCharsets.UTF_8);
                    anyModified = true;
                    totalChanges++;
                    modifiedFiles.add(projectRoot.relativize(pomFile).toString().replace('\\', '/'));
                    rulesApplied.add("INJECT_BLOCKHOUND_TEST_DEPENDENCY");
                }
            }
        }

        // 3. Generate BlockHound CI test customizer
        Path testDir = projectRoot.resolve("src/test/java/io/elmos/generated/test");
        Files.createDirectories(testDir);
        Path customizerFile = testDir.resolve("BlockHoundIntegrationTestCustomizer.java");
        if (!Files.exists(customizerFile)) {
            String testHelper = generateBlockHoundCustomizer();
            Files.writeString(customizerFile, testHelper, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            String relCustomizer = projectRoot.relativize(customizerFile).toString().replace('\\', '/');
            modifiedFiles.add(relCustomizer);
            generatedArtifacts.add(relCustomizer);
            rulesApplied.add("GENERATE_BLOCKHOUND_TEST_CUSTOMIZER");
        }

        return new ReactiveAuditResult(anyModified, totalChanges, modifiedFiles, rulesApplied, findings, generatedArtifacts);
    }

    private static String generateBlockHoundCustomizer() {
        return """
                package io.elmos.generated.test;

                import reactor.blockhound.BlockHound;
                import reactor.blockhound.integration.BlockHoundIntegration;

                /**
                 * Automated BlockHound Test Customizer for Spring WebFlux / Reactor architectures.
                 *
                 * <p>Ensures any blocking I/O calls on Reactor / Netty non-blocking threads
                 * throw an immediate Error during integration tests, preventing production latency stalls.
                 */
                public class BlockHoundIntegrationTestCustomizer implements BlockHoundIntegration {

                    public static void installBlockHound() {
                        BlockHound.builder()
                                .with(new BlockHoundIntegrationTestCustomizer())
                                .allowBlockingCallsInside("java.io.FileInputStream", "readBytes")
                                .install();
                    }

                    @Override
                    public void applyTo(BlockHound.Builder builder) {
                        // Allow intentional test logging or test assertion calls if necessary
                        builder.allowBlockingCallsInside("org.slf4j.impl.SimpleLogger", "write");
                    }
                }
                """;
    }
}
