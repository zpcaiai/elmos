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
 * Industrial-grade modernizer for Cloud-Native Containerization and GraalVM AOT Native Image.
 *
 * <p>Modern Spring Boot (3.x / 2.3+) running on Kubernetes and Cloud-Native environments requires:
 * <ol>
 *   <li><b>Graceful Shutdown:</b> {@code server.shutdown=graceful} with a configured buffer
 *       ({@code spring.lifecycle.timeout-per-shutdown-phase=30s}) to allow in-flight HTTP requests
 *       to drain during Pod eviction/rolling updates without dropping client traffic.</li>
 *   <li><b>Kubernetes Health Probes:</b> Actuator Liveness and Readiness state probes exposed
 *       via {@code /actuator/health/liveness} and {@code /actuator/health/readiness}.</li>
 *   <li><b>Actuator &amp; Native Image Toolchain:</b> Inject {@code spring-boot-starter-actuator} and
 *       {@code org.graalvm.buildtools:native-maven-plugin} into build definitions.</li>
 *   <li><b>AOT RuntimeHints Deduction:</b> Statically analyze Java source for dynamic reflection
 *       (e.g., {@code Class.forName}, reflective method invocations) and resource patterns,
 *       generating {@code RuntimeHintsRegistrar} implementations and registering them in
 *       {@code META-INF/spring/aot.factories}.</li>
 * </ol>
 */
public final class SpringNativeAndContainerModernizer {

    public record NativeContainerModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static NativeContainerModernizationResult empty() {
            return new NativeContainerModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern CLASS_FOR_NAME_PATTERN = Pattern.compile("Class\\.forName\\(\\s*\"([^\"]+)\"\\s*\\)");
    private static final Pattern PACKAGE_PATTERN = Pattern.compile("(?m)^\\s*package\\s+([a-zA-Z0-9_.]+);");
    private static final Pattern SPRING_BOOT_APP_PATTERN = Pattern.compile("@SpringBootApplication");

    private SpringNativeAndContainerModernizer() {}

    public static NativeContainerModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return NativeContainerModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        // 1. Modernize Application Configuration (Graceful shutdown & Probes)
        NativeContainerModernizationResult configRes = modernizeConfiguration(projectRoot);
        if (configRes.modified()) {
            modifiedFiles.addAll(configRes.modifiedFiles());
            rulesApplied.addAll(configRes.rulesApplied());
            warnings.addAll(configRes.warnings());
            changes += configRes.changesCount();
        }

        // 2. Modernize POM / Gradle for Actuator and GraalVM Native Plugin
        NativeContainerModernizationResult buildRes = modernizeBuildFiles(projectRoot);
        if (buildRes.modified()) {
            modifiedFiles.addAll(buildRes.modifiedFiles());
            rulesApplied.addAll(buildRes.rulesApplied());
            warnings.addAll(buildRes.warnings());
            changes += buildRes.changesCount();
        }

        // 3. Scan Source Files for Dynamic Reflection and Deduce AOT RuntimeHints
        NativeContainerModernizationResult aotRes = modernizeAotRuntimeHints(projectRoot);
        if (aotRes.modified()) {
            modifiedFiles.addAll(aotRes.modifiedFiles());
            rulesApplied.addAll(aotRes.rulesApplied());
            warnings.addAll(aotRes.warnings());
            changes += aotRes.changesCount();
        }

        return new NativeContainerModernizationResult(
                !modifiedFiles.isEmpty(),
                changes,
                modifiedFiles,
                rulesApplied,
                warnings
        );
    }

    private static NativeContainerModernizationResult modernizeConfiguration(Path projectRoot) {
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        List<Path> configFiles = findApplicationConfigFiles(projectRoot);

        if (configFiles.isEmpty()) {
            // Create default application.yml in src/main/resources
            Path resDir = projectRoot.resolve("src/main/resources");
            Path appYml = resDir.resolve("application.yml");
            try {
                Files.createDirectories(resDir);
                String defaultYml = """
                        server:
                          shutdown: graceful

                        spring:
                          lifecycle:
                            timeout-per-shutdown-phase: 30s

                        management:
                          endpoint:
                            health:
                              probes:
                                enabled: true
                          health:
                            livenessstate:
                              enabled: true
                            readinessstate:
                              enabled: true
                          endpoints:
                            web:
                              exposure:
                                include: health,info,prometheus
                        """;
                Files.writeString(appYml, defaultYml, StandardCharsets.UTF_8);
                modifiedFiles.add(projectRoot.relativize(appYml).toString());
                rules.add("CONTAINER_GRACEFUL_SHUTDOWN_INJECTED");
                rules.add("KUBERNETES_ACTUATOR_PROBES_CONFIGURED");
                changes += 2;
            } catch (IOException e) {
                warnings.add("Failed to create application.yml: " + e.getMessage());
            }
        } else {
            for (Path configFile : configFiles) {
                String fileName = configFile.getFileName().toString();
                try {
                    String content = Files.readString(configFile, StandardCharsets.UTF_8);
                    String updated = content;

                    if (fileName.endsWith(".yml") || fileName.endsWith(".yaml")) {
                        updated = injectYamlGracefulShutdownAndProbes(updated, rules);
                    } else if (fileName.endsWith(".properties")) {
                        updated = injectPropertiesGracefulShutdownAndProbes(updated, rules);
                    }

                    if (!updated.equals(content)) {
                        Files.writeString(configFile, updated, StandardCharsets.UTF_8);
                        modifiedFiles.add(projectRoot.relativize(configFile).toString());
                        changes++;
                    }
                } catch (IOException e) {
                    warnings.add("Failed to read/write " + fileName + ": " + e.getMessage());
                }
            }
        }

        return new NativeContainerModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rules, warnings);
    }

    private static String injectYamlGracefulShutdownAndProbes(String content, List<String> rules) {
        StringBuilder sb = new StringBuilder(content);
        boolean hasServerShutdown = content.contains("shutdown: graceful") || content.contains("shutdown: \"graceful\"");
        boolean hasLifecycleTimeout = content.contains("timeout-per-shutdown-phase");
        boolean hasProbes = content.contains("livenessstate") || (content.contains("probes:") && content.contains("enabled: true"));

        if (!hasServerShutdown || !hasLifecycleTimeout) {
            sb.append("\n# Injected by Elmos Spring Native Modernizer for Kubernetes Graceful Drain\n");
            if (!hasServerShutdown) {
                sb.append("server:\n  shutdown: graceful\n");
            }
            if (!hasLifecycleTimeout) {
                sb.append("spring:\n  lifecycle:\n    timeout-per-shutdown-phase: 30s\n");
            }
            rules.add("CONTAINER_GRACEFUL_SHUTDOWN_INJECTED");
        }

        if (!hasProbes) {
            sb.append("\n# Injected by Elmos Spring Native Modernizer for Kubernetes Liveness & Readiness Probes\n");
            sb.append("""
                    management:
                      endpoint:
                        health:
                          probes:
                            enabled: true
                      health:
                        livenessstate:
                          enabled: true
                        readinessstate:
                          enabled: true
                      endpoints:
                        web:
                          exposure:
                            include: health,info,prometheus
                    """);
            rules.add("KUBERNETES_ACTUATOR_PROBES_CONFIGURED");
        }

        return sb.toString();
    }

    private static String injectPropertiesGracefulShutdownAndProbes(String content, List<String> rules) {
        StringBuilder sb = new StringBuilder(content);
        boolean hasServerShutdown = content.contains("server.shutdown=graceful");
        boolean hasLifecycleTimeout = content.contains("spring.lifecycle.timeout-per-shutdown-phase");
        boolean hasProbes = content.contains("management.health.livenessstate.enabled=true") || content.contains("management.endpoint.health.probes.enabled=true");

        if (!hasServerShutdown || !hasLifecycleTimeout) {
            sb.append("\n# Injected by Elmos Spring Native Modernizer for Kubernetes Graceful Drain\n");
            if (!hasServerShutdown) {
                sb.append("server.shutdown=graceful\n");
            }
            if (!hasLifecycleTimeout) {
                sb.append("spring.lifecycle.timeout-per-shutdown-phase=30s\n");
            }
            rules.add("CONTAINER_GRACEFUL_SHUTDOWN_INJECTED");
        }

        if (!hasProbes) {
            sb.append("\n# Injected by Elmos Spring Native Modernizer for Kubernetes Liveness & Readiness Probes\n");
            sb.append("""
                    management.endpoint.health.probes.enabled=true
                    management.health.livenessstate.enabled=true
                    management.health.readinessstate.enabled=true
                    management.endpoints.web.exposure.include=health,info,prometheus
                    """);
            rules.add("KUBERNETES_ACTUATOR_PROBES_CONFIGURED");
        }

        return sb.toString();
    }

    private static NativeContainerModernizationResult modernizeBuildFiles(Path projectRoot) {
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String content = Files.readString(pomFile, StandardCharsets.UTF_8);
                String updated = content;

                // 1. Ensure spring-boot-starter-actuator
                if (!updated.contains("spring-boot-starter-actuator")) {
                    String actuatorDep = """
                                <dependency>
                                  <groupId>org.springframework.boot</groupId>
                                  <artifactId>spring-boot-starter-actuator</artifactId>
                                </dependency>
                          </dependencies>""";
                    updated = updated.replaceFirst("(?s)</dependencies>", Matcher.quoteReplacement(actuatorDep));
                    rules.add("ACTUATOR_STARTER_DEPENDENCY_INJECTED");
                }

                // 2. Ensure native-maven-plugin in <plugins>
                if (!updated.contains("native-maven-plugin")) {
                    String nativePlugin = """
                                <plugin>
                                  <groupId>org.graalvm.buildtools</groupId>
                                  <artifactId>native-maven-plugin</artifactId>
                                </plugin>
                          </plugins>""";
                    if (updated.contains("</plugins>")) {
                        updated = updated.replaceFirst("(?s)</plugins>", Matcher.quoteReplacement(nativePlugin));
                    } else if (updated.contains("</build>")) {
                        String pluginsSection = """
                              <plugins>
                                <plugin>
                                  <groupId>org.graalvm.buildtools</groupId>
                                  <artifactId>native-maven-plugin</artifactId>
                                </plugin>
                              </plugins>
                            </build>""";
                        updated = updated.replaceFirst("(?s)</build>", Matcher.quoteReplacement(pluginsSection));
                    } else if (updated.contains("</project>")) {
                        String buildSection = """
                            <build>
                              <plugins>
                                <plugin>
                                  <groupId>org.graalvm.buildtools</groupId>
                                  <artifactId>native-maven-plugin</artifactId>
                                </plugin>
                              </plugins>
                            </build>
                          </project>""";
                        updated = updated.replaceFirst("(?s)</project>", Matcher.quoteReplacement(buildSection));
                    }
                    rules.add("GRAALVM_NATIVE_MAVEN_PLUGIN_INJECTED");
                }

                if (!updated.equals(content)) {
                    Files.writeString(pomFile, updated, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(pomFile).toString());
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to modernize pom.xml: " + e.getMessage());
            }
        }

        Path gradleFile = projectRoot.resolve("build.gradle");
        if (Files.isRegularFile(gradleFile)) {
            try {
                String content = Files.readString(gradleFile, StandardCharsets.UTF_8);
                String updated = content;

                if (!updated.contains("spring-boot-starter-actuator")) {
                    updated += "\ndependencies {\n    implementation 'org.springframework.boot:spring-boot-starter-actuator'\n}\n";
                    rules.add("ACTUATOR_STARTER_DEPENDENCY_INJECTED");
                }
                if (!updated.contains("org.graalvm.buildtools.native")) {
                    updated += "\nplugins {\n    id 'org.graalvm.buildtools.native' version '0.10.2'\n}\n";
                    rules.add("GRAALVM_NATIVE_GRADLE_PLUGIN_INJECTED");
                }

                if (!updated.equals(content)) {
                    Files.writeString(gradleFile, updated, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(gradleFile).toString());
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to modernize build.gradle: " + e.getMessage());
            }
        }

        return new NativeContainerModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rules, warnings);
    }

    private static NativeContainerModernizationResult modernizeAotRuntimeHints(Path projectRoot) {
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        Set<String> reflectiveClasses = new LinkedHashSet<>();
        String basePackage = "com.example";
        Path mainAppPath = null;

        // Scan java files
        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                try {
                    String content = Files.readString(javaFile, StandardCharsets.UTF_8);

                    Matcher pkgMatcher = PACKAGE_PATTERN.matcher(content);
                    if (pkgMatcher.find() && "com.example".equals(basePackage)) {
                        basePackage = pkgMatcher.group(1);
                    }

                    if (SPRING_BOOT_APP_PATTERN.matcher(content).find()) {
                        mainAppPath = javaFile;
                        Matcher m = PACKAGE_PATTERN.matcher(content);
                        if (m.find()) {
                            basePackage = m.group(1);
                        }
                    }

                    // Extract Class.forName targets
                    Matcher cfm = CLASS_FOR_NAME_PATTERN.matcher(content);
                    while (cfm.find()) {
                        String target = cfm.group(1).trim();
                        if (!target.isEmpty() && !target.contains("$")) {
                            reflectiveClasses.add(target);
                        }
                    }
                } catch (IOException ignored) {}
            }
        } catch (IOException ignored) {}

        // Always register default reflection targets if none detected to ensure baseline AOT sanity
        if (reflectiveClasses.isEmpty()) {
            reflectiveClasses.add(basePackage + ".model.GenericPayload");
        }

        // 1. Generate RuntimeHintsRegistrar Java class
        String packagePath = basePackage.replace('.', '/');
        Path aotDir = projectRoot.resolve("src/main/java/" + packagePath + "/aot");
        Path hintsFile = aotDir.resolve("AppRuntimeHintsRegistrar.java");

        try {
            Files.createDirectories(aotDir);
            StringBuilder code = new StringBuilder();
            code.append("package ").append(basePackage).append(".aot;\n\n");
            code.append("import org.springframework.aot.hint.MemberCategory;\n");
            code.append("import org.springframework.aot.hint.RuntimeHints;\n");
            code.append("import org.springframework.aot.hint.RuntimeHintsRegistrar;\n");
            code.append("import org.springframework.aot.hint.TypeReference;\n\n");
            code.append("/**\n");
            code.append(" * Auto-generated by Elmos SpringNativeAndContainerModernizer for GraalVM AOT Compilation.\n");
            code.append(" */\n");
            code.append("public class AppRuntimeHintsRegistrar implements RuntimeHintsRegistrar {\n\n");
            code.append("    @Override\n");
            code.append("    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {\n");
            code.append("        // 1. Register resource pattern hints for native classpath discovery\n");
            code.append("        hints.resources().registerPattern(\"*.json\");\n");
            code.append("        hints.resources().registerPattern(\"*.sql\");\n");
            code.append("        hints.resources().registerPattern(\"*.xml\");\n");
            code.append("        hints.resources().registerPattern(\"*.properties\");\n\n");
            code.append("        // 2. Register dynamic reflection hints\n");
            for (String clazz : reflectiveClasses) {
                code.append("        hints.reflection().registerType(\n");
                code.append("                TypeReference.of(\"").append(clazz).append("\"),\n");
                code.append("                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,\n");
                code.append("                MemberCategory.INVOKE_DECLARED_METHODS,\n");
                code.append("                MemberCategory.DECLARED_FIELDS\n");
                code.append("        );\n");
            }
            code.append("    }\n");
            code.append("}\n");

            Files.writeString(hintsFile, code.toString(), StandardCharsets.UTF_8);
            modifiedFiles.add(projectRoot.relativize(hintsFile).toString());
            rules.add("AOT_RUNTIME_HINTS_REGISTRAR_GENERATED");
            changes++;
        } catch (IOException e) {
            warnings.add("Failed to write AppRuntimeHintsRegistrar.java: " + e.getMessage());
        }

        // 2. Register in META-INF/spring/aot.factories
        Path metaInfSpring = projectRoot.resolve("src/main/resources/META-INF/spring");
        Path aotFactories = metaInfSpring.resolve("aot.factories");
        try {
            Files.createDirectories(metaInfSpring);
            String entry = "org.springframework.aot.hint.RuntimeHintsRegistrar=" + basePackage + ".aot.AppRuntimeHintsRegistrar\n";
            Files.writeString(aotFactories, entry, StandardCharsets.UTF_8);
            modifiedFiles.add(projectRoot.relativize(aotFactories).toString());
            rules.add("AOT_FACTORIES_CONFIGURED");
            changes++;
        } catch (IOException e) {
            warnings.add("Failed to write aot.factories: " + e.getMessage());
        }

        // 3. Annotate @SpringBootApplication with @ImportRuntimeHints if found
        if (mainAppPath != null) {
            try {
                String content = Files.readString(mainAppPath, StandardCharsets.UTF_8);
                if (!content.contains("@ImportRuntimeHints")) {
                    String updated = content;
                    if (!updated.contains("import org.springframework.context.annotation.ImportRuntimeHints;")) {
                        updated = updated.replaceFirst("(?m)^package\\s+[^;]+;\\s*", "$0\nimport org.springframework.context.annotation.ImportRuntimeHints;\nimport " + basePackage + ".aot.AppRuntimeHintsRegistrar;\n");
                    }
                    updated = updated.replaceFirst("@SpringBootApplication", "@SpringBootApplication\n@ImportRuntimeHints(AppRuntimeHintsRegistrar.class)");
                    if (!updated.equals(content)) {
                        Files.writeString(mainAppPath, updated, StandardCharsets.UTF_8);
                        modifiedFiles.add(projectRoot.relativize(mainAppPath).toString());
                        rules.add("IMPORT_RUNTIME_HINTS_ANNOTATED");
                        changes++;
                    }
                }
            } catch (IOException ignored) {}
        }

        return new NativeContainerModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rules, warnings);
    }

    private static List<Path> findApplicationConfigFiles(Path projectRoot) {
        List<Path> list = new ArrayList<>();
        try (Stream<Path> stream = Files.walk(projectRoot)) {
            list = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> {
                        String name = p.getFileName().toString();
                        return (name.startsWith("application.") || name.startsWith("application-")) &&
                                (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties"));
                    })
                    .toList();
        } catch (IOException ignored) {}
        return list;
    }
}
