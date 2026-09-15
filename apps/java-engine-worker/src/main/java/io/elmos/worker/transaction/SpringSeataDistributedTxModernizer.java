package io.elmos.worker.transaction;

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
 * Enterprise Seata Distributed Transaction Modernizer for Spring Boot 3.x / 4.x.
 *
 * <p>Solves four critical industrial distributed transaction migration pitfalls:
 * <ol>
 *   <li><b>Dependency & Package Migration:</b>
 *       Upgrades legacy Seata 1.x / Alibaba Cloud Seata starters to Apache Seata 2.x
 *       ({@code org.apache.seata:seata-spring-boot-starter:2.2.0}) and updates package imports.</li>
 *   <li><b>Double-Proxy Deadlock Prevention:</b>
 *       Seata 2.x natively handles data source proxying via {@code AutoDataSourceProxy}.
 *       Legacy manual {@code new DataSourceProxy(target)} beans create nested proxy chains that
 *       lead to connection starvation and two-phase commit deadlocks; this modernizer strips
 *       manual wrappers and configures automatic proxying.</li>
 *   <li><b>Configuration Normalization:</b>
 *       Injects essential {@code seata.enable-auto-data-source-proxy=true},
 *       {@code seata.tx-service-group}, and vgroup mappings into YAML/properties.</li>
 *   <li><b>XID Cross-Thread Propagation:</b>
 *       Generates {@code SeataXidTaskDecorator} to ensure distributed transaction contexts
 *       ({@code RootContext.getXID()}) propagate safely across {@code @Async} and thread pools.</li>
 * </ol>
 */
public final class SpringSeataDistributedTxModernizer {

    public record SeataModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> generatedArtifacts
    ) {
        public static SeataModernizationResult empty() {
            return new SeataModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern LEGACY_SEATA_POM = Pattern.compile(
            "<dependency>\\s*<groupId>(?:com\\.alibaba\\.cloud|io\\.seata)</groupId>\\s*<artifactId>(?:spring-cloud-starter-alibaba-seata|seata-spring-boot-starter)</artifactId>(?:\\s*<version>.*?</version>)?\\s*</dependency>",
            Pattern.DOTALL
    );

    private static final String APACHE_SEATA_DEPENDENCY =
            """
                    <dependency>
                        <groupId>org.apache.seata</groupId>
                        <artifactId>seata-spring-boot-starter</artifactId>
                        <version>2.2.0</version>
                    </dependency>""";

    private static final Pattern LEGACY_SEATA_IMPORT = Pattern.compile(
            "import\\s+io\\.seata\\.(spring\\.annotation\\.(?:GlobalTransactional|GlobalLock)|core\\.context\\.RootContext|rm\\.datasource\\.DataSourceProxy);",
            Pattern.MULTILINE
    );

    private static final Pattern MANUAL_DATASOURCE_PROXY_BEAN = Pattern.compile(
            "@Bean(?:\\([^)]*\\))?\\s*(?:@Primary\\s*)?public\\s+(?:DataSourceProxy|DataSource)\\s+(\\w+)\\s*\\([^)]*\\)\\s*\\{[^}]*new\\s+DataSourceProxy\\s*\\([^)]+\\)[^}]*\\}",
            Pattern.DOTALL
    );

    /**
     * Executes complete Seata distributed transaction modernization on the workspace.
     */
    public SeataModernizationResult modernize(Path projectRoot) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return SeataModernizationResult.empty();
        }

        boolean anyModified = false;
        int totalChanges = 0;
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> generatedArtifacts = new ArrayList<>();

        // 1. Modernize pom.xml dependencies
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
            Matcher pomMatcher = LEGACY_SEATA_POM.matcher(pomContent);
            if (pomMatcher.find()) {
                String modernizedPom = pomMatcher.replaceAll(APACHE_SEATA_DEPENDENCY);
                Files.writeString(pomFile, modernizedPom, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(pomFile.toString());
                rulesApplied.add("UPGRADE_SEATA_STARTER_TO_APACHE_2_2");
            }
        }

        // 2. Scan and modernize Java sources (imports & eliminate manual DataSourceProxy)
        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                String source = Files.readString(javaFile, StandardCharsets.UTF_8);
                boolean fileChanged = false;

                // Eliminate manual DataSourceProxy bean
                Matcher proxyBeanMatcher = MANUAL_DATASOURCE_PROXY_BEAN.matcher(source);
                if (proxyBeanMatcher.find()) {
                    source = proxyBeanMatcher.replaceAll("// [ELMOS-MIGRATED] Seata 2.x uses AutoDataSourceProxy. Manual DataSourceProxy Bean removed to prevent double-proxy deadlock.");
                    fileChanged = true;
                    totalChanges++;
                    rulesApplied.add("ELIMINATE_MANUAL_DATASOURCE_PROXY_BEAN");
                }

                // Migrate package imports from io.seata to org.apache.seata
                Matcher importMatcher = LEGACY_SEATA_IMPORT.matcher(source);
                if (importMatcher.find()) {
                    source = importMatcher.replaceAll(mr -> {
                        String matched = mr.group(1);
                        if (matched.contains("DataSourceProxy")) {
                            return "// [ELMOS-CLEANUP] Deprecated manual DataSourceProxy import removed.";
                        }
                        return "import org.apache.seata." + matched + ";";
                    });
                    fileChanged = true;
                    totalChanges++;
                    rulesApplied.add("MIGRATE_SEATA_IMPORTS_TO_APACHE");
                }

                if (fileChanged) {
                    Files.writeString(javaFile, source, StandardCharsets.UTF_8);
                    anyModified = true;
                    modifiedFiles.add(javaFile.toString());
                }
            }
        }

        // 3. Ensure Seata AutoDataSourceProxy & Tx Configuration in application.yml / properties
        Path ymlPath = projectRoot.resolve("src/main/resources/application.yml");
        if (Files.isRegularFile(ymlPath)) {
            String ymlContent = Files.readString(ymlPath, StandardCharsets.UTF_8);
            if (!ymlContent.contains("seata:")) {
                String seataConfig =
                        """

                        seata:
                          enabled: true
                          application-id: ${spring.application.name:application}
                          tx-service-group: default_tx_group
                          enable-auto-data-source-proxy: true
                          data-source-proxy-mode: AT
                          service:
                            vgroup-mapping:
                              default_tx_group: default
                        """;
                Files.writeString(ymlPath, ymlContent + seataConfig, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(ymlPath.toString());
                rulesApplied.add("INJECT_SEATA_AUTO_DATASOURCE_PROXY_CONFIG");
            }
        }

        // 4. Generate XID cross-thread propagation decorator
        Path configDir = projectRoot.resolve("src/main/java/io/elmos/generated/config");
        Files.createDirectories(configDir);
        Path decoratorFile = configDir.resolve("SeataXidTaskDecorator.java");
        if (!Files.exists(decoratorFile)) {
            String decoratorSource = generateSeataXidTaskDecorator();
            Files.writeString(decoratorFile, decoratorSource, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(decoratorFile.toString());
            generatedArtifacts.add(decoratorFile.toString());
            rulesApplied.add("GENERATE_SEATA_XID_TASK_DECORATOR");
        }

        return new SeataModernizationResult(anyModified, totalChanges, modifiedFiles, rulesApplied, generatedArtifacts);
    }

    private static String generateSeataXidTaskDecorator() {
        return """
                package io.elmos.generated.config;

                import org.apache.seata.core.context.RootContext;
                import org.springframework.core.task.TaskDecorator;
                import org.springframework.stereotype.Component;

                /**
                 * Seata Distributed Transaction XID Cross-Thread Propagator.
                 *
                 * <p>Propagates the current RootContext XID into asynchronous worker threads
                 * (@Async / ThreadPoolTaskExecutor) and unbinds cleanly in finally blocks,
                 * preventing global transaction context loss and dirty state leaks.
                 */
                @Component
                public class SeataXidTaskDecorator implements TaskDecorator {

                    @Override
                    public Runnable decorate(Runnable runnable) {
                        String xid = RootContext.getXID();
                        return () -> {
                            boolean bound = false;
                            if (xid != null && RootContext.getXID() == null) {
                                RootContext.bind(xid);
                                bound = true;
                            }
                            try {
                                runnable.run();
                            } finally {
                                if (bound) {
                                    RootContext.unbind();
                                }
                            }
                        };
                    }
                }
                """;
    }
}
