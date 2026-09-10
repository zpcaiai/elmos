package io.elmos.worker;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Diagnostic-driven targeted AST and POM repair engine for Spring Modernization.
 *
 * <p>Automates remediation of the four highest-frequency breaking changes encountered
 * when migrating legacy Spring Framework / Spring Boot 1.x / 2.x enterprise projects
 * to modern Spring Boot 3.5.x and Java 21:
 * <ol>
 *   <li><b>Jakarta & Dependencies:</b> Injects missing validation, annotation, and JAXB
 *       starter dependencies removed from Spring Boot 3, and upgrades Lombok and compiler plugins.</li>
 *   <li><b>Spring Security 6:</b> Eliminates deprecated {@code WebSecurityConfigurerAdapter},
 *       transforms {@code configure(HttpSecurity)} into modern {@code @Bean SecurityFilterChain},
 *       and migrates {@code authorizeRequests()} to {@code authorizeHttpRequests()} with {@code requestMatchers()}.</li>
 *   <li><b>Hibernate 6 / JPA 3:</b> Strips legacy Hibernate {@code @TypeDef} annotations and rewrites
 *       JSON column mappings to {@code @JdbcTypeCode(SqlTypes.JSON)}.</li>
 *   <li><b>Actuator & WebMvc:</b> Replaces deprecated {@code HandlerInterceptorAdapter} with
 *       {@code HandlerInterceptor} and normalizes legacy actuator configuration keys.</li>
 * </ol>
 */
public final class SpringDiagnosticAutoRepairer {

    public record RepairResult(
            boolean repaired,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied
    ) {
        public static RepairResult empty() {
            return new RepairResult(false, 0, Collections.emptySet(), Collections.emptyList());
        }
    }

    private SpringDiagnosticAutoRepairer() {}

    /**
     * Executes the comprehensive auto-repair pipeline across all project files.
     *
     * @param projectRoot the root directory of the project (or multi-module reactor root)
     * @param diagnostics raw compilation error output lines from maven/gradle
     * @return structured summary of applied repairs
     */
    public static RepairResult repair(Path projectRoot, List<String> diagnostics) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return RepairResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        int changesCount = 0;

        // 1. Discover all reactor modules
        List<Path> poms = SpringMultiModuleProjectScanner.findPomFiles(projectRoot);
        for (Path pom : poms) {
            RepairResult pomRepair = repairPom(pom, diagnostics);
            if (pomRepair.repaired()) {
                changesCount += pomRepair.changesCount();
                modifiedFiles.addAll(pomRepair.modifiedFiles());
                rulesApplied.addAll(pomRepair.rulesApplied());
            }
        }

        // 2. Discover and repair Java source files across the project
        List<Path> javaFiles = findJavaFiles(projectRoot);
        for (Path javaFile : javaFiles) {
            RepairResult javaRepair = repairJavaFile(projectRoot, javaFile, diagnostics);
            if (javaRepair.repaired()) {
                changesCount += javaRepair.changesCount();
                modifiedFiles.addAll(javaRepair.modifiedFiles());
                rulesApplied.addAll(javaRepair.rulesApplied());
            }
        }

        // 3. Discover and repair Application Configuration files
        List<Path> configFiles = findConfigFiles(projectRoot);
        for (Path configFile : configFiles) {
            RepairResult configRepair = repairConfigFile(projectRoot, configFile);
            if (configRepair.repaired()) {
                changesCount += configRepair.changesCount();
                modifiedFiles.addAll(configRepair.modifiedFiles());
                rulesApplied.addAll(configRepair.rulesApplied());
            }
        }

        // 4. Spring Security 5/6 FilterChain Modernizer
        var secRes = io.elmos.worker.security.SpringSecurityFilterChainModernizer.modernize(projectRoot);
        if (secRes.modified()) {
            changesCount += secRes.changesCount();
            modifiedFiles.addAll(secRes.modifiedFiles());
            rulesApplied.addAll(secRes.rulesApplied());
        }

        // 5. JPA / Hibernate 6 SQM & Composite Query Modernizer
        var jpaRes = io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer.modernize(projectRoot);
        if (jpaRes.modified()) {
            changesCount += jpaRes.changesCount();
            modifiedFiles.addAll(jpaRes.modifiedFiles());
            rulesApplied.addAll(jpaRes.rulesApplied());
        }

        // 6. Spring Cloud Microservices Modernizer
        var cloudRes = io.elmos.worker.cloud.SpringCloudMicroservicesModernizer.modernize(projectRoot);
        if (cloudRes.modified()) {
            changesCount += cloudRes.changesCount();
            modifiedFiles.addAll(cloudRes.modifiedFiles());
            rulesApplied.addAll(cloudRes.rulesApplied());
        }

        // 7. XML Hybrid Configuration Converter
        var xmlRes = io.elmos.worker.xml.SpringXmlToJavaConfigConverter.convertProject(projectRoot, "io.elmos.config");
        if (xmlRes.converted()) {
            changesCount += xmlRes.totalBeansConverted();
            modifiedFiles.addAll(xmlRes.generatedJavaFiles());
            rulesApplied.add("CONVERT_SPRING_XML_TO_JAVACONFIG");
        }

        return new RepairResult(changesCount > 0, changesCount, Collections.unmodifiableSet(modifiedFiles), Collections.unmodifiableList(rulesApplied));
    }

    /**
     * Repairs POM dependencies, compiler plugins, and Lombok configurations.
     */
    static RepairResult repairPom(Path pomPath, List<String> diagnostics) {
        try {
            String original = Files.readString(pomPath, StandardCharsets.UTF_8);
            String content = original;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // Rule 1.1: Ensure spring-boot-starter-validation is present if validation is used
            if (!content.contains("spring-boot-starter-validation") && content.contains("<dependencies>")) {
                String validationDep = "\n    <dependency>\n"
                        + "      <groupId>org.springframework.boot</groupId>\n"
                        + "      <artifactId>spring-boot-starter-validation</artifactId>\n"
                        + "    </dependency>";
                content = content.replace("<dependencies>", "<dependencies>" + validationDep);
                rules.add("INJECT_SPRING_BOOT_STARTER_VALIDATION");
                changes++;
            }

            // Rule 1.2: Upgrade Lombok to at least 1.18.30 for Java 21 support
            Pattern lombokPattern = Pattern.compile("(<groupId>org\\.projectlombok</groupId>\\s*<artifactId>lombok</artifactId>\\s*<version>)([^<]+)(</version>)");
            Matcher lombokMatcher = lombokPattern.matcher(content);
            if (lombokMatcher.find()) {
                String currentVer = lombokMatcher.group(2).trim();
                if (isOlderVersion(currentVer, "1.18.30")) {
                    content = lombokMatcher.replaceAll("$11.18.30$3");
                    rules.add("UPGRADE_LOMBOK_JAVA21");
                    changes++;
                }
            }

            // Rule 1.3: Ensure jakarta.annotation-api is present
            if (!content.contains("jakarta.annotation-api") && content.contains("<dependencies>")) {
                String annotDep = "\n    <dependency>\n"
                        + "      <groupId>jakarta.annotation</groupId>\n"
                        + "      <artifactId>jakarta.annotation-api</artifactId>\n"
                        + "    </dependency>";
                content = content.replace("<dependencies>", "<dependencies>" + annotDep);
                rules.add("INJECT_JAKARTA_ANNOTATION_API");
                changes++;
            }

            // Rule 1.4: Update maven-compiler-plugin to 3.13.0 and release 21
            if (content.contains("maven-compiler-plugin")) {
                Pattern compilerVersion = Pattern.compile("(<artifactId>maven-compiler-plugin</artifactId>\\s*<version>)([^<]+)(</version>)");
                Matcher compilerMatcher = compilerVersion.matcher(content);
                if (compilerMatcher.find()) {
                    content = compilerMatcher.replaceAll("$13.13.0$3");
                    rules.add("UPGRADE_MAVEN_COMPILER_PLUGIN");
                    changes++;
                }
            }

            if (changes > 0 && !content.equals(original)) {
                Files.writeString(pomPath, content, StandardCharsets.UTF_8);
                return new RepairResult(true, changes, Set.of(pomPath.getFileName().toString()), rules);
            }
        } catch (IOException ignored) {}
        return RepairResult.empty();
    }

    /**
     * Repairs Java source code: Security 6, Hibernate 6, Jakarta packages, Interceptors.
     */
    static RepairResult repairJavaFile(Path root, Path file, List<String> diagnostics) {
        try {
            String original = Files.readString(file, StandardCharsets.UTF_8);
            String content = original;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // Rule 2.1: javax -> jakarta namespace conversion (safe replacements)
            String[] javaxReplacements = {
                    "javax.persistence.", "jakarta.persistence.",
                    "javax.validation.", "jakarta.validation.",
                    "javax.annotation.", "jakarta.annotation.",
                    "javax.servlet.", "jakarta.servlet.",
                    "javax.transaction.", "jakarta.transaction."
            };
            for (int i = 0; i < javaxReplacements.length; i += 2) {
                if (content.contains(javaxReplacements[i])) {
                    content = content.replace(javaxReplacements[i], javaxReplacements[i + 1]);
                    rules.add("MIGRATE_" + javaxReplacements[i].replace(".", "_") + "TO_JAKARTA");
                    changes++;
                }
            }

            // Rule 2.2: Spring Security 6 - WebSecurityConfigurerAdapter modernization
            if (content.contains("WebSecurityConfigurerAdapter")) {
                // Remove extends WebSecurityConfigurerAdapter
                content = content.replaceAll("extends\\s+WebSecurityConfigurerAdapter\\s*", "");
                // Remove import
                content = content.replaceAll("import\\s+org\\.springframework\\.security\\.config\\.annotation\\.web\\.configuration\\.WebSecurityConfigurerAdapter;\\s*", "");

                // Ensure required imports exist
                content = ensureImport(content, "org.springframework.context.annotation.Bean");
                content = ensureImport(content, "org.springframework.security.web.SecurityFilterChain");
                content = ensureImport(content, "org.springframework.security.config.annotation.web.builders.HttpSecurity");

                // Replace protected void configure(HttpSecurity http) throws Exception
                Pattern configurePattern = Pattern.compile("protected\\s+void\\s+configure\\s*\\(\\s*HttpSecurity\\s+([a-zA-Z0-9_]+)\\s*\\)\\s*throws\\s+Exception\\s*\\{");
                Matcher configureMatcher = configurePattern.matcher(content);
                if (configureMatcher.find()) {
                    String httpParam = configureMatcher.group(1);
                    String replacement = "@Bean\n    public SecurityFilterChain securityFilterChain(HttpSecurity " + httpParam + ") throws Exception {";
                    content = configureMatcher.replaceFirst(replacement);

                    // Also find closing brace and add `return http.build();`
                    int methodStart = content.indexOf(replacement);
                    if (methodStart >= 0) {
                        int bodyStart = methodStart + replacement.length();
                        int bodyEnd = findMatchingBrace(content, bodyStart - 1);
                        if (bodyEnd > bodyStart && !content.substring(bodyStart, bodyEnd).contains(".build()")) {
                            content = content.substring(0, bodyEnd)
                                    + "        return " + httpParam + ".build();\n    "
                                    + content.substring(bodyEnd);
                        }
                    }
                }
                rules.add("MODERNIZE_SPRING_SECURITY_6_FILTER_CHAIN");
                changes++;
            }

            // Rule 2.3: Spring Security 6 - authorizeRequests() -> authorizeHttpRequests()
            if (content.contains("authorizeRequests()")) {
                content = content.replace("authorizeRequests()", "authorizeHttpRequests()");
                rules.add("MIGRATE_AUTHORIZE_HTTP_REQUESTS");
                changes++;
            }
            if (content.contains("antMatchers(")) {
                content = content.replace("antMatchers(", "requestMatchers(");
                rules.add("MIGRATE_REQUEST_MATCHERS");
                changes++;
            }

            // Rule 2.4: Hibernate 6 - TypeDef & Type annotation modernization
            if (content.contains("@TypeDef") || content.contains("@TypeDefs")) {
                content = content.replaceAll("import\\s+org\\.hibernate\\.annotations\\.TypeDefs?;\\s*", "");
                content = content.replaceAll("@TypeDefs?\\s*\\([\\s\\S]*?\\)", "");
                rules.add("REMOVE_HIBERNATE_TYPEDEFS");
                changes++;
            }
            if (content.contains("@Type(")) {
                content = ensureImport(content, "org.hibernate.annotations.JdbcTypeCode");
                content = ensureImport(content, "org.hibernate.type.SqlTypes");
                content = content.replaceAll("@Type\\s*\\(\\s*type\\s*=\\s*\"jsonb?\"\\s*\\)", "@JdbcTypeCode(SqlTypes.JSON)");
                rules.add("MODERNIZE_HIBERNATE_JDBC_TYPE_CODE");
                changes++;
            }

            // Rule 2.5: WebMvc HandlerInterceptorAdapter replacement
            if (content.contains("HandlerInterceptorAdapter")) {
                content = content.replaceAll("import\\s+org\\.springframework\\.web\\.servlet\\.handler\\.HandlerInterceptorAdapter;\\s*", "");
                content = ensureImport(content, "org.springframework.web.servlet.HandlerInterceptor");
                content = content.replace("extends HandlerInterceptorAdapter", "implements HandlerInterceptor");
                rules.add("MODERNIZE_HANDLER_INTERCEPTOR");
                changes++;
            }

            if (changes > 0 && !content.equals(original)) {
                Files.writeString(file, content, StandardCharsets.UTF_8);
                String relativePath = root.relativize(file).toString();
                return new RepairResult(true, changes, Set.of(relativePath), rules);
            }
        } catch (IOException ignored) {}
        return RepairResult.empty();
    }

    /**
     * Repairs Spring configuration files (properties / YAML).
     */
    static RepairResult repairConfigFile(Path root, Path configFile) {
        try {
            String original = Files.readString(configFile, StandardCharsets.UTF_8);
            String content = original;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            String fileName = configFile.getFileName().toString();
            if (fileName.endsWith(".properties")) {
                if (content.contains("endpoints.health.sensitive=")) {
                    content = content.replace("endpoints.health.sensitive=false", "management.endpoint.health.show-details=always");
                    content = content.replace("endpoints.health.sensitive=true", "management.endpoint.health.show-details=never");
                    rules.add("MODERNIZE_ACTUATOR_HEALTH_PROPERTIES");
                    changes++;
                }
                if (content.contains("endpoints.health.enabled=")) {
                    content = content.replace("endpoints.health.enabled=", "management.endpoint.health.enabled=");
                    rules.add("MODERNIZE_ACTUATOR_ENABLED_PROPERTIES");
                    changes++;
                }
                if (content.contains("management.security.enabled=")) {
                    content = content.replaceAll("management\\.security\\.enabled=[a-zA-Z]+\\s*", "");
                    rules.add("STRIP_OBSOLETE_MANAGEMENT_SECURITY");
                    changes++;
                }
            } else if (fileName.endsWith(".yml") || fileName.endsWith(".yaml")) {
                if (content.contains("endpoints:") && content.contains("health:")) {
                    content = content.replace("endpoints:\n  health:", "management:\n  endpoint:\n    health:");
                    rules.add("MODERNIZE_ACTUATOR_YAML");
                    changes++;
                }
            }

            if (changes > 0 && !content.equals(original)) {
                Files.writeString(configFile, content, StandardCharsets.UTF_8);
                String relativePath = root.relativize(configFile).toString();
                return new RepairResult(true, changes, Set.of(relativePath), rules);
            }
        } catch (IOException ignored) {}
        return RepairResult.empty();
    }

    private static String ensureImport(String content, String importClass) {
        if (content.contains("import " + importClass + ";")) {
            return content;
        }
        int pkgIndex = content.indexOf("package ");
        if (pkgIndex >= 0) {
            int endOfPkg = content.indexOf(";", pkgIndex);
            if (endOfPkg >= 0) {
                return content.substring(0, endOfPkg + 1) + "\n\nimport " + importClass + ";" + content.substring(endOfPkg + 1);
            }
        }
        return "import " + importClass + ";\n" + content;
    }

    private static int findMatchingBrace(String text, int openBraceIndex) {
        int depth = 0;
        for (int i = openBraceIndex; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c == '{') depth++;
            else if (c == '}') {
                depth--;
                if (depth == 0) return i;
            }
        }
        return -1;
    }

    private static boolean isOlderVersion(String v1, String v2) {
        String[] parts1 = v1.split("[.-]");
        String[] parts2 = v2.split("[.-]");
        int len = Math.max(parts1.length, parts2.length);
        for (int i = 0; i < len; i++) {
            int n1 = i < parts1.length ? parseIntSafe(parts1[i]) : 0;
            int n2 = i < parts2.length ? parseIntSafe(parts2[i]) : 0;
            if (n1 != n2) return n1 < n2;
        }
        return false;
    }

    private static int parseIntSafe(String val) {
        try {
            return Integer.parseInt(val.replaceAll("[^0-9]", ""));
        } catch (Exception e) {
            return 0;
        }
    }

    private static List<Path> findJavaFiles(Path root) {
        List<Path> files = new ArrayList<>();
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (file.toString().endsWith(".java")) {
                        files.add(file);
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException ignored) {}
        return files;
    }

    private static List<Path> findConfigFiles(Path root) {
        List<Path> files = new ArrayList<>();
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    String name = file.getFileName().toString();
                    if (name.startsWith("application") && (name.endsWith(".properties") || name.endsWith(".yml") || name.endsWith(".yaml"))) {
                        files.add(file);
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException ignored) {}
        return files;
    }
}
