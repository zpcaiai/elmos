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
 * Enterprise modernizer for Flyway 10+ database migration modularization and baseline safety.
 *
 * <p>Key enterprise migration challenges in Spring Boot 3.2+ with Flyway 10:
 * <ol>
 *   <li><b>Database Modularization in Flyway 10:</b> Database specific support has been extracted from
 *       {@code flyway-core} into dialect-specific modules (e.g., {@code flyway-mysql}, {@code flyway-sqlserver},
 *       {@code flyway-database-oracle}). Without these modules, database connection initialization fails.</li>
 *   <li><b>Production Disaster Prevention (cleanDisabled):</b> In production environments, {@code cleanDisabled=true}
 *       must be strictly enforced to prevent accidental catastrophic schema drops.</li>
 *   <li><b>Legacy Database Onboarding (baselineOnMigrate):</b> Upgrading existing unmanaged or partially migrated
 *       databases requires {@code baselineOnMigrate=true} to avoid {@code FlywayException: Found non-empty schema(s)}.</li>
 *   <li><b>Safe Customizer Injection:</b> Generates {@code FlywayMigrationSafetyConfiguration.java} using Spring Boot 3
 *       {@code FlywayConfigurationCustomizer}.</li>
 * </ol>
 */
public final class SpringFlyway10Modernizer {

    public record FlywayModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static FlywayModernizationResult empty() {
            return new FlywayModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern FLYWAY_CORE_PATTERN = Pattern.compile(
            "<artifactId>flyway-core</artifactId>"
    );

    private static final Pattern MYSQL_DRIVER_PATTERN = Pattern.compile(
            "<artifactId>(?:mysql-connector-j|mysql-connector-java)</artifactId>"
    );

    private static final Pattern FLYWAY_MYSQL_PATTERN = Pattern.compile(
            "<artifactId>flyway-mysql</artifactId>"
    );

    private static final Pattern DEPENDENCIES_TAG_PATTERN = Pattern.compile(
            "</dependencies>"
    );

    private SpringFlyway10Modernizer() {}

    public static FlywayModernizationResult modernize(Path projectRoot) {
        return modernize(projectRoot, true);
    }

    public static FlywayModernizationResult modernize(Path projectRoot, boolean updatePom) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return FlywayModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;
        boolean flywayDetected = false;
        boolean mysqlDetected = false;

        // 1. Inspect pom.xml
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                if (FLYWAY_CORE_PATTERN.matcher(pomContent).find() || pomContent.contains("org.flywaydb")) {
                    flywayDetected = true;
                }
                if (MYSQL_DRIVER_PATTERN.matcher(pomContent).find()) {
                    mysqlDetected = true;
                }

                if (updatePom && flywayDetected && mysqlDetected && !FLYWAY_MYSQL_PATTERN.matcher(pomContent).find()) {
                    Matcher depMatcher = DEPENDENCIES_TAG_PATTERN.matcher(pomContent);
                    if (depMatcher.find()) {
                        String dependencyXml = """
                                    <dependency>
                                      <groupId>org.flywaydb</groupId>
                                      <artifactId>flyway-mysql</artifactId>
                                    </dependency>
                                  </dependencies>""";
                        String updatedPom = pomContent.substring(0, depMatcher.start()) + dependencyXml + pomContent.substring(depMatcher.end());
                        Files.writeString(pomFile, updatedPom, StandardCharsets.UTF_8);
                        modifiedFiles.add(projectRoot.relativize(pomFile).toString().replace('\\', '/'));
                        rulesApplied.add("INJECT_FLYWAY_10_MYSQL_MODULAR_DEPENDENCY");
                        changes++;
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to inspect pom.xml for Flyway: " + e.getMessage());
            }
        }

        // 2. Scan resources for application configuration
        Path srcDir = projectRoot.resolve("src");
        Path resourcesDir = srcDir.resolve("main/resources");
        if (Files.isDirectory(resourcesDir)) {
            try (Stream<Path> stream = Files.walk(resourcesDir)) {
                List<Path> configFiles = stream.filter(p -> Files.isRegularFile(p) &&
                        (p.toString().endsWith(".yml") || p.toString().endsWith(".yaml") || p.toString().endsWith(".properties"))
                ).toList();

                for (Path configFile : configFiles) {
                    try {
                        String content = Files.readString(configFile, StandardCharsets.UTF_8);
                        String updated = content;

                        if (content.contains("flyway") || content.contains("spring.flyway")) {
                            flywayDetected = true;
                        }

                        if (flywayDetected) {
                            if (configFile.toString().endsWith(".properties")) {
                                StringBuilder props = new StringBuilder(updated);
                                if (!updated.contains("spring.flyway.clean-disabled")) {
                                    props.append("\nspring.flyway.clean-disabled=true");
                                }
                                if (!updated.contains("spring.flyway.baseline-on-migrate")) {
                                    props.append("\nspring.flyway.baseline-on-migrate=true");
                                }
                                updated = props.toString();
                            } else {
                                // YAML
                                if (!updated.contains("clean-disabled")) {
                                    if (updated.contains("flyway:")) {
                                        updated = updated.replaceFirst("(?m)^(\\s*flyway:\\s*)$",
                                                "$1\n$1  clean-disabled: true\n$1  baseline-on-migrate: true");
                                    } else if (updated.contains("spring:")) {
                                        updated = updated.replaceFirst("(?m)^(\\s*spring:\\s*)$",
                                                "$1\n$1  flyway:\n$1    clean-disabled: true\n$1    baseline-on-migrate: true");
                                    } else {
                                        updated = updated + """
                                                \nspring:
                                                  flyway:
                                                    clean-disabled: true
                                                    baseline-on-migrate: true
                                                """;
                                    }
                                }
                            }
                        }

                        if (!updated.equals(content)) {
                            Files.writeString(configFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                            rulesApplied.add("ENFORCE_FLYWAY_CLEAN_DISABLED_AND_BASELINE_ON_MIGRATE");
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process config file " + configFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan resources for Flyway config: " + e.getMessage());
            }
        }

        // 3. Generate FlywayMigrationSafetyConfiguration.java
        if (flywayDetected) {
            Path targetPackageDir = srcDir.resolve("main/java/io/elmos/generated/flyway");
            try {
                Files.createDirectories(targetPackageDir);
                Path configFile = targetPackageDir.resolve("FlywayMigrationSafetyConfiguration.java");
                if (!Files.exists(configFile)) {
                    String configSource = generateFlywaySafetyConfigSource();
                    Files.writeString(configFile, configSource, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                    rulesApplied.add("GENERATE_FLYWAY_SAFETY_CONFIGURATION");
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to generate FlywayMigrationSafetyConfiguration: " + e.getMessage());
            }
        }

        return new FlywayModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private static String generateFlywaySafetyConfigSource() {
        return """
                package io.elmos.generated.flyway;

                import org.flywaydb.core.Flyway;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
                import org.springframework.boot.autoconfigure.flyway.FlywayConfigurationCustomizer;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                /**
                 * Enterprise Flyway 10+ migration safety governance.
                 * Prevents accidental schema wipe and enforces baseline on non-empty databases.
                 */
                @Configuration(proxyBeanMethods = false)
                @ConditionalOnClass(Flyway.class)
                public class FlywayMigrationSafetyConfiguration {

                    @Bean
                    public FlywayConfigurationCustomizer flywaySafetyCustomizer() {
                        return configuration -> configuration
                                .cleanDisabled(true)
                                .baselineOnMigrate(true)
                                .baselineVersion("1");
                    }
                }
                """;
    }
}
