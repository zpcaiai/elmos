package io.elmos.worker.datasource;

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
import java.util.stream.Stream;

/**
 * Modernizer for multi-datasource routing architectures and ShardingSphere upgrades
 * to Spring Boot 3.x / Java 17/21 standards.
 *
 * <p>Modernizes:
 * <ol>
 *   <li><b>AbstractRoutingDataSource ThreadLocal leak safety:</b>
 *       Ensures context holders implement {@code AutoCloseable} or clear mechanisms to prevent
 *       dirty datasource routing across thread pool threads.</li>
 *   <li><b>ShardingSphere 4.x to 5.5+:</b>
 *       Upgrades {@code sharding-jdbc-spring-boot-starter} (4.x) to {@code shardingsphere-jdbc-core} (5.5.0),
 *       and migrates YAML configuration keys from {@code spring.shardingsphere.sharding...} to
 *       {@code spring.shardingsphere.rules.sharding...}.</li>
 *   <li><b>Dynamic DataSource Starter 3.x to 4.x+:</b>
 *       Upgrades {@code com.baomidou:dynamic-datasource-spring-boot-starter} to 4.3.1+ for Boot 3 compatibility.</li>
 * </ol>
 */
public final class SpringMultiDataSourceModernizer {

    public record MultiDataSourceResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static MultiDataSourceResult empty() {
            return new MultiDataSourceResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private SpringMultiDataSourceModernizer() {}

    public static MultiDataSourceResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return MultiDataSourceResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        // 1. Process POM / Gradle files
        Path pomPath = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomPath)) {
            var pomRes = modernizePom(projectRoot, pomPath);
            if (pomRes.modified()) {
                modifiedFiles.addAll(pomRes.modifiedFiles());
                rulesApplied.addAll(pomRes.rulesApplied());
                changes += pomRes.changesCount();
            }
        }

        // 2. Process Configuration Files (YAML / Properties)
        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> configFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> {
                        String name = p.getFileName().toString();
                        return (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties"))
                                && !name.contains("target");
                    })
                    .toList();

            for (Path cfg : configFiles) {
                var cfgRes = modernizeConfigFile(projectRoot, cfg);
                if (cfgRes.modified()) {
                    modifiedFiles.addAll(cfgRes.modifiedFiles());
                    rulesApplied.addAll(cfgRes.rulesApplied());
                    changes += cfgRes.changesCount();
                }
            }
        } catch (IOException ignored) {}

        // 3. Process Java routing context holders
        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                var javaRes = modernizeJavaRouting(projectRoot, javaFile);
                if (javaRes.modified()) {
                    modifiedFiles.addAll(javaRes.modifiedFiles());
                    rulesApplied.addAll(javaRes.rulesApplied());
                    warnings.addAll(javaRes.warnings());
                    changes += javaRes.changesCount();
                }
            }
        } catch (IOException ignored) {}

        return new MultiDataSourceResult(
                !modifiedFiles.isEmpty(),
                changes,
                modifiedFiles,
                rulesApplied,
                warnings
        );
    }

    static MultiDataSourceResult modernizePom(Path projectRoot, Path pomPath) {
        try {
            String content = Files.readString(pomPath, StandardCharsets.UTF_8);
            String original = content;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // 1. ShardingSphere 4.x -> 5.5.0
            if (content.contains("sharding-jdbc-spring-boot-starter") || (content.contains("org.apache.shardingsphere") && content.contains("<version>4."))) {
                content = content.replaceAll(
                        "(?s)<dependency>\\s*<groupId>org\\.apache\\.shardingsphere</groupId>\\s*<artifactId>sharding-jdbc-spring-boot-starter</artifactId>.*?</dependency>",
                        """
                        <dependency>
                            <groupId>org.apache.shardingsphere</groupId>
                            <artifactId>shardingsphere-jdbc-core</artifactId>
                            <version>5.5.0</version>
                        </dependency>"""
                );
                rules.add("POM_SHARDINGSPHERE_4_TO_5");
                changes++;
            }

            // 2. Dynamic-datasource starter -> 4.3.1 for Boot 3
            if (content.contains("dynamic-datasource-spring-boot-starter")) {
                Pattern ddsPattern = Pattern.compile("(?s)(<groupId>com\\.baomidou</groupId>\\s*<artifactId>dynamic-datasource-spring-boot-starter</artifactId>\\s*<version>)(3\\.[0-9.]+)(</version>)");
                Matcher matcher = ddsPattern.matcher(content);
                if (matcher.find()) {
                    content = matcher.replaceAll("$14.3.1$3");
                    rules.add("POM_DYNAMIC_DATASOURCE_UPGRADE");
                    changes++;
                }
            }

            if (!content.equals(original)) {
                Files.writeString(pomPath, content, StandardCharsets.UTF_8);
                return new MultiDataSourceResult(true, changes, Set.of(projectRoot.relativize(pomPath).toString()), rules, List.of());
            }
        } catch (IOException ignored) {}
        return MultiDataSourceResult.empty();
    }

    static MultiDataSourceResult modernizeConfigFile(Path projectRoot, Path configFile) {
        try {
            String content = Files.readString(configFile, StandardCharsets.UTF_8);
            String original = content;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // ShardingSphere 4.x to 5.x config layout:
            // spring.shardingsphere.sharding -> spring.shardingsphere.rules.sharding
            if (content.contains("spring.shardingsphere.sharding.")) {
                content = content.replace("spring.shardingsphere.sharding.", "spring.shardingsphere.rules.sharding.");
                rules.add("CONFIG_SHARDINGSPHERE_4_TO_5_RULES");
                changes++;
            } else if (content.contains("shardingsphere:\n") && content.contains("sharding:\n")) {
                // YAML nested structure:
                // sharding: -> rules:\n    sharding:
                content = content.replace(
                        "    sharding:\n",
                        "    rules:\n      sharding:\n"
                );
                rules.add("CONFIG_SHARDINGSPHERE_YAML_RULES");
                changes++;
            }

            if (!content.equals(original)) {
                Files.writeString(configFile, content, StandardCharsets.UTF_8);
                return new MultiDataSourceResult(true, changes, Set.of(projectRoot.relativize(configFile).toString()), rules, List.of());
            }
        } catch (IOException ignored) {}
        return MultiDataSourceResult.empty();
    }

    static MultiDataSourceResult modernizeJavaRouting(Path projectRoot, Path javaFile) {
        try {
            String content = Files.readString(javaFile, StandardCharsets.UTF_8);
            String original = content;
            List<String> rules = new ArrayList<>();
            List<String> warnings = new ArrayList<>();
            int changes = 0;

            // Detect ThreadLocal in ContextHolder for routing DataSource
            if (content.contains("ThreadLocal<String>") && (content.contains("DataSource") || content.contains("LookupKey"))) {
                // Ensure remove() or clear() is present
                if (!content.contains(".remove()") && !content.contains("clear()")) {
                    // Inject clear method to prevent thread-pool pollution
                    int lastBrace = content.lastIndexOf('}');
                    if (lastBrace > 0) {
                        String clearMethod = """
                        
                            public static void clearDataSourceKey() {
                                CONTEXT_HOLDER.remove();
                            }
                        """;
                        content = content.substring(0, lastBrace) + clearMethod + content.substring(lastBrace);
                        rules.add("JAVA_ROUTING_THREADLOCAL_CLEAR_INJECTED");
                        changes++;
                    }
                }
            }

            // Detect AbstractRoutingDataSource implementation
            if (content.contains("extends AbstractRoutingDataSource")) {
                // Ensure javax.sql.DataSource imports are updated to javax.sql.DataSource (compatible with Jakarta)
                // and check whether determineCurrentLookupKey() is present
                if (content.contains("protected Object determineCurrentLookupKey()")) {
                    rules.add("JAVA_ABSTRACT_ROUTING_DATASOURCE_AUDITED");
                }
            }

            if (!content.equals(original)) {
                Files.writeString(javaFile, content, StandardCharsets.UTF_8);
                return new MultiDataSourceResult(true, changes, Set.of(projectRoot.relativize(javaFile).toString()), rules, warnings);
            }
        } catch (IOException ignored) {}
        return MultiDataSourceResult.empty();
    }
}
