package io.elmos.worker.cloud;

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
 * Industrial-grade modernizer for Spring Cloud bootstrap configuration to {@code spring.config.import}.
 *
 * <p>In Spring Boot 2.4+ and Spring Boot 3.x / Spring Cloud 2020+, the bootstrap context phase
 * initialized by {@code bootstrap.yml} / {@code bootstrap.properties} is disabled by default.
 * Instead, Spring uses the unified {@code spring.config.import} mechanism.
 *
 * <p>This modernizer:
 * <ol>
 *   <li>Converts {@code bootstrap.yml} / {@code bootstrap.properties} to {@code application.yml} / {@code application.properties}.</li>
 *   <li>Generates the correct {@code spring.config.import} directives for:
 *       <ul>
 *         <li>Spring Cloud Config Server (e.g., {@code optional:configserver:...})</li>
 *         <li>Alibaba Nacos (e.g., {@code optional:nacos:...})</li>
 *         <li>HashiCorp Consul (e.g., {@code optional:consul:...})</li>
 *       </ul>
 *   </li>
 *   <li>Removes legacy {@code spring-cloud-starter-bootstrap} dependency from {@code pom.xml} / {@code build.gradle}.</li>
 *   <li>Modernizes {@code @RefreshScope} usage and recommends {@code @ConfigurationProperties} binding.</li>
 *   <li>Cleans up redundant legacy bootstrap files.</li>
 * </ol>
 */
public final class SpringConfigImportModernizer {

    public record ConfigImportModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static ConfigImportModernizationResult empty() {
            return new ConfigImportModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private SpringConfigImportModernizer() {}

    public static ConfigImportModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return ConfigImportModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        // 1. Process bootstrap config files in resources
        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> bootstrapFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> {
                        String name = p.getFileName().toString();
                        return (name.startsWith("bootstrap.") || name.startsWith("bootstrap-")) &&
                                (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties"));
                    })
                    .toList();

            for (Path bootstrapFile : bootstrapFiles) {
                ConfigImportModernizationResult res = modernizeConfigFile(projectRoot, bootstrapFile);
                if (res.modified()) {
                    modifiedFiles.addAll(res.modifiedFiles());
                    rulesApplied.addAll(res.rulesApplied());
                    warnings.addAll(res.warnings());
                    changes += res.changesCount();
                }
            }
        } catch (IOException ignored) {}

        // 2. Modernize POM / Gradle dependency
        Path pomPath = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomPath)) {
            ConfigImportModernizationResult pomRes = modernizePom(projectRoot, pomPath);
            if (pomRes.modified()) {
                modifiedFiles.addAll(pomRes.modifiedFiles());
                rulesApplied.addAll(pomRes.rulesApplied());
                changes += pomRes.changesCount();
            }
        }

        Path gradlePath = projectRoot.resolve("build.gradle");
        if (Files.isRegularFile(gradlePath)) {
            ConfigImportModernizationResult gradleRes = modernizeGradle(projectRoot, gradlePath);
            if (gradleRes.modified()) {
                modifiedFiles.addAll(gradleRes.modifiedFiles());
                rulesApplied.addAll(gradleRes.rulesApplied());
                changes += gradleRes.changesCount();
            }
        }

        // 3. Scan Java files for @RefreshScope validation
        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                ConfigImportModernizationResult javaRes = modernizeJavaRefreshScope(projectRoot, javaFile);
                if (javaRes.modified()) {
                    modifiedFiles.addAll(javaRes.modifiedFiles());
                    rulesApplied.addAll(javaRes.rulesApplied());
                    warnings.addAll(javaRes.warnings());
                    changes += javaRes.changesCount();
                }
            }
        } catch (IOException ignored) {}

        return new ConfigImportModernizationResult(
                !modifiedFiles.isEmpty(),
                changes,
                modifiedFiles,
                rulesApplied,
                warnings
        );
    }

    static ConfigImportModernizationResult modernizeConfigFile(Path projectRoot, Path bootstrapFile) {
        try {
            String original = Files.readString(bootstrapFile, StandardCharsets.UTF_8);
            String fileName = bootstrapFile.getFileName().toString();
            boolean isProperties = fileName.endsWith(".properties");

            String appFileName = fileName.replace("bootstrap", "application");
            Path appFile = bootstrapFile.resolveSibling(appFileName);

            StringBuilder imports = new StringBuilder();
            List<String> rules = new ArrayList<>();
            List<String> warnings = new ArrayList<>();

            // Detect Config Server
            if (original.contains("spring.cloud.config.uri") || (original.contains("uri:") && original.contains("config"))) {
                String uri = extractValue(original, "spring.cloud.config.uri", "http://localhost:8888");
                if (isProperties) {
                    imports.append("\nspring.config.import=optional:configserver:").append(uri).append("\n");
                } else {
                    imports.append("\nspring:\n  config:\n    import:\n      - \"optional:configserver:").append(uri).append("\"\n");
                }
                rules.add("CONFIG_IMPORT_CONFIG_SERVER");
            }

            // Detect Nacos Config
            if (original.contains("nacos.config") || original.contains("spring.cloud.nacos.config")) {
                String serverAddr = extractValue(original, "spring.cloud.nacos.config.server-addr", "localhost:8848");
                String group = extractValue(original, "spring.cloud.nacos.config.group", "DEFAULT_GROUP");
                String ext = extractValue(original, "spring.cloud.nacos.config.file-extension", "yaml");
                if (isProperties) {
                    imports.append("\nspring.config.import=optional:nacos:${spring.application.name}.").append(ext)
                            .append("?group=").append(group).append("&refreshEnabled=true\n");
                } else {
                    imports.append("\nspring:\n  config:\n    import:\n      - \"optional:nacos:${spring.application.name}.")
                            .append(ext).append("?group=").append(group).append("&refreshEnabled=true\"\n");
                }
                rules.add("CONFIG_IMPORT_NACOS");
            }

            // Detect Consul Config
            if (original.contains("consul.config") || original.contains("spring.cloud.consul")) {
                String host = extractValue(original, "spring.cloud.consul.host", "localhost");
                String port = extractValue(original, "spring.cloud.consul.port", "8500");
                if (isProperties) {
                    imports.append("\nspring.config.import=optional:consul:").append(host).append(":").append(port).append("\n");
                } else {
                    imports.append("\nspring:\n  config:\n    import:\n      - \"optional:consul:").append(host).append(":").append(port).append("\"\n");
                }
                rules.add("CONFIG_IMPORT_CONSUL");
            }

            // Fallback default if bootstrap existed but no specific server detected
            if (rules.isEmpty()) {
                if (isProperties) {
                    imports.append("\n# Note: bootstrap.properties migrated to application.properties for Spring Boot 3.x\n");
                } else {
                    imports.append("\n# Note: bootstrap.yml migrated to application.yml for Spring Boot 3.x\n");
                }
                rules.add("CONFIG_BOOTSTRAP_MIGRATED");
            }

            // Clean original content from bootstrap-specific keys
            String cleanedContent = cleanBootstrapKeys(original);

            // Merge into application file
            if (Files.exists(appFile)) {
                String existing = Files.readString(appFile, StandardCharsets.UTF_8);
                String merged = existing.trim() + "\n\n# --- Migrated from " + fileName + " ---\n" + cleanedContent.trim() + imports;
                Files.writeString(appFile, merged, StandardCharsets.UTF_8);
            } else {
                String newContent = "# Migrated from " + fileName + "\n" + cleanedContent.trim() + imports;
                Files.writeString(appFile, newContent, StandardCharsets.UTF_8);
            }

            // Remove legacy bootstrap file
            Files.deleteIfExists(bootstrapFile);

            String relPath = projectRoot.relativize(appFile).toString();
            return new ConfigImportModernizationResult(true, rules.size(), Set.of(relPath), rules, warnings);
        } catch (IOException e) {
            return ConfigImportModernizationResult.empty();
        }
    }

    private static String extractValue(String content, String key, String defaultValue) {
        // 1. Try full dot-notation key (properties or flattened YAML)
        Pattern fullPattern = Pattern.compile("(?m)^\\s*(?:" + Pattern.quote(key) + ")\\s*[:=]\\s*[\"']?([^\"'\\r\\n]+)[\"']?");
        Matcher fullMatcher = fullPattern.matcher(content);
        if (fullMatcher.find()) {
            return fullMatcher.group(1).trim();
        }
        // 2. Try leaf key (last segment after '.') for nested YAML
        String leaf = key.contains(".") ? key.substring(key.lastIndexOf('.') + 1) : key;
        Pattern leafPattern = Pattern.compile("(?m)^\\s*(?:" + Pattern.quote(leaf) + ")\\s*[:=]\\s*[\"']?([^\"'\\r\\n]+)[\"']?");
        Matcher leafMatcher = leafPattern.matcher(content);
        if (leafMatcher.find()) {
            return leafMatcher.group(1).trim();
        }
        return defaultValue;
    }

    private static String cleanBootstrapKeys(String content) {
        // Remove old spring.cloud.bootstrap.enabled flags
        content = content.replaceAll("(?m)^\\s*spring\\.cloud\\.bootstrap\\.enabled\\s*[:=].*$\\n?", "");
        return content;
    }

    static ConfigImportModernizationResult modernizePom(Path projectRoot, Path pomPath) {
        try {
            String content = Files.readString(pomPath, StandardCharsets.UTF_8);
            String original = content;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // Remove legacy spring-cloud-starter-bootstrap
            if (content.contains("spring-cloud-starter-bootstrap")) {
                content = content.replaceAll(
                        "(?s)\\s*<dependency>\\s*<groupId>org\\.springframework\\.cloud</groupId>\\s*<artifactId>spring-cloud-starter-bootstrap</artifactId>.*?\\s*</dependency>",
                        ""
                );
                rules.add("POM_REMOVE_STARTER_BOOTSTRAP");
                changes++;
            }

            if (!content.equals(original)) {
                Files.writeString(pomPath, content, StandardCharsets.UTF_8);
                return new ConfigImportModernizationResult(true, changes, Set.of(projectRoot.relativize(pomPath).toString()), rules, List.of());
            }
        } catch (IOException ignored) {}
        return ConfigImportModernizationResult.empty();
    }

    static ConfigImportModernizationResult modernizeGradle(Path projectRoot, Path gradlePath) {
        try {
            String content = Files.readString(gradlePath, StandardCharsets.UTF_8);
            String original = content;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            if (content.contains("spring-cloud-starter-bootstrap")) {
                content = content.replaceAll("(?m)^.*spring-cloud-starter-bootstrap.*$\\n?", "");
                rules.add("GRADLE_REMOVE_STARTER_BOOTSTRAP");
                changes++;
            }

            if (!content.equals(original)) {
                Files.writeString(gradlePath, content, StandardCharsets.UTF_8);
                return new ConfigImportModernizationResult(true, changes, Set.of(projectRoot.relativize(gradlePath).toString()), rules, List.of());
            }
        } catch (IOException ignored) {}
        return ConfigImportModernizationResult.empty();
    }

    static ConfigImportModernizationResult modernizeJavaRefreshScope(Path projectRoot, Path javaFile) {
        try {
            String content = Files.readString(javaFile, StandardCharsets.UTF_8);
            String original = content;
            List<String> rules = new ArrayList<>();
            List<String> warnings = new ArrayList<>();
            int changes = 0;

            if (content.contains("@RefreshScope")) {
                // In Spring Cloud 2023, @RefreshScope with @ConfigurationProperties is discouraged;
                // @ConfigurationProperties beans are refreshed by ConfigurationPropertiesRebinder automatically.
                if (content.contains("@ConfigurationProperties")) {
                    content = content.replaceAll("@RefreshScope\\s*", "");
                    content = content.replaceAll("import\\s+org\\.springframework\\.cloud\\.context\\.config\\.annotation\\.RefreshScope;\\s*", "");
                    rules.add("JAVA_REMOVE_REFRESH_SCOPE_ON_CONFIG_PROPS");
                    changes++;
                } else {
                    warnings.add("Class " + javaFile.getFileName() + " uses @RefreshScope with @Value. Consider migrating to @ConfigurationProperties for type safety and auto-rebind in Spring Boot 3.");
                }
            }

            if (!content.equals(original)) {
                Files.writeString(javaFile, content, StandardCharsets.UTF_8);
                return new ConfigImportModernizationResult(true, changes, Set.of(projectRoot.relativize(javaFile).toString()), rules, warnings);
            }
        } catch (IOException ignored) {}
        return ConfigImportModernizationResult.empty();
    }
}
