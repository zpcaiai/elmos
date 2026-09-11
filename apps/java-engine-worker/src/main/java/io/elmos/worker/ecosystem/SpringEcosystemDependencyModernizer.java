package io.elmos.worker.ecosystem;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Subagent-E: Industrial-grade Ecosystem Dependency & Annotation Modernizer.
 *
 * <p>Modernizes enterprise third-party ecosystem dependencies:
 * <ol>
 *   <li><b>Swagger 2 to OpenAPI 3 (Springdoc):</b>
 *       Replaces abandoned {@code springfox-swagger2} & {@code springfox-swagger-ui} with
 *       {@code org.springdoc:springdoc-openapi-starter-webmvc-ui:2.5.0}.
 *       Rewrites {@code @Api} to {@code @Tag}, {@code @ApiOperation} to {@code @Operation}.</li>
 *   <li><b>MyBatis Jakarta Compatibility:</b>
 *       Upgrades {@code mybatis-spring-boot-starter} 2.x to 3.0.3+ for Jakarta Servlet & Persistence support.</li>
 *   <li><b>Compiler Parameters Flag (-parameters):</b>
 *       Mandatorily injects {@code <compilerArgs><arg>-parameters</arg></compilerArgs>} into {@code maven-compiler-plugin}
 *       to prevent Spring 6 argument name reflection runtime failures.</li>
 * </ol>
 */
public final class SpringEcosystemDependencyModernizer {

    public record EcosystemModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied
    ) {
        public static EcosystemModernizationResult empty() {
            return new EcosystemModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList());
        }
    }

    private SpringEcosystemDependencyModernizer() {}

    public static EcosystemModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot cannot be null");
        if (!Files.isDirectory(projectRoot)) {
            return EcosystemModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        int changes = 0;

        try {
            // 1. Modernize all pom.xml files discovered across multi-module reactor
            List<Path> poms = io.elmos.worker.SpringMultiModuleProjectScanner.findPomFiles(projectRoot);
            for (Path pom : poms) {
                String pomContent = Files.readString(pom, StandardCharsets.UTF_8);
                String updatedPom = modernizePom(pomContent, rulesApplied);
                if (!updatedPom.equals(pomContent)) {
                    Files.writeString(pom, updatedPom, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(pom).toString().replace("\\", "/"));
                    changes++;
                }
            }

            // 2. Synthesize Spring Boot 3 AutoConfiguration.imports from spring.factories
            int importsChanged = modernizeAutoConfigurationImports(projectRoot, modifiedFiles, rulesApplied);
            changes += importsChanged;

            // 3. Modernize Java Controllers (Swagger 2 -> OpenAPI 3)
            try (var stream = Files.walk(projectRoot)) {
                List<Path> javaFiles = stream
                        .filter(Files::isRegularFile)
                        .filter(p -> p.toString().endsWith(".java"))
                        .toList();

                for (Path javaFile : javaFiles) {
                    String code = Files.readString(javaFile, StandardCharsets.UTF_8);
                    String updated = modernizeAnnotations(code, rulesApplied);
                    if (!updated.equals(code)) {
                        Files.writeString(javaFile, updated, StandardCharsets.UTF_8);
                        String rel = projectRoot.relativize(javaFile).toString().replace("\\", "/");
                        modifiedFiles.add(rel);
                        changes++;
                    }
                }
            }

        } catch (IOException e) {
            return EcosystemModernizationResult.empty();
        }

        return new EcosystemModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied);
    }

    private static int modernizeAutoConfigurationImports(Path projectRoot, Set<String> modifiedFiles, List<String> rules) {
        int count = 0;
        try (var stream = Files.walk(projectRoot)) {
            List<Path> factories = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().equals("spring.factories"))
                    .toList();

            for (Path factory : factories) {
                String content = Files.readString(factory, StandardCharsets.UTF_8);
                if (content.contains("org.springframework.boot.autoconfigure.EnableAutoConfiguration")) {
                    List<String> autoConfigs = extractAutoConfigurations(content);
                    if (!autoConfigs.isEmpty()) {
                        Path importsFile = factory.getParent().resolve("spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports");
                        if (!Files.exists(importsFile)) {
                            Files.createDirectories(importsFile.getParent());
                            Files.writeString(importsFile, String.join("\n", autoConfigs) + "\n", StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(importsFile).toString().replace("\\", "/"));
                            rules.add("RULE-SPRING-BOOT3-AUTOCONFIGURATION-IMPORTS-SYNTHESIZED");
                            count++;
                        }
                    }
                }
            }
        } catch (IOException ignored) {}
        return count;
    }

    private static List<String> extractAutoConfigurations(String factoriesContent) {
        List<String> configs = new ArrayList<>();
        String[] lines = factoriesContent.split("\n");
        boolean inAutoConfig = false;
        for (String line : lines) {
            String trimmed = line.trim();
            if (trimmed.startsWith("org.springframework.boot.autoconfigure.EnableAutoConfiguration")) {
                inAutoConfig = true;
                int eqIdx = trimmed.indexOf('=');
                if (eqIdx != -1) {
                    String rest = trimmed.substring(eqIdx + 1).replace("\\", "").trim();
                    if (!rest.isEmpty()) configs.add(rest);
                }
                continue;
            }
            if (inAutoConfig) {
                if (trimmed.isEmpty() || (!trimmed.endsWith("\\") && !trimmed.contains("."))) {
                    if (!trimmed.isEmpty() && trimmed.contains(".")) {
                        configs.add(trimmed.replace("\\", "").trim());
                    }
                    inAutoConfig = false;
                } else {
                    String cls = trimmed.replace("\\", "").replace(",", "").trim();
                    if (!cls.isEmpty()) {
                        configs.add(cls);
                    }
                    if (!line.endsWith("\\")) {
                        inAutoConfig = false;
                    }
                }
            }
        }
        return configs;
    }

    private static String modernizePom(String pom, List<String> rules) {
        String result = pom;

        // 1. Replace Springfox with Springdoc
        if (result.contains("springfox-swagger2") || result.contains("springfox-swagger-ui")) {
            result = result.replaceAll(
                    "<groupId>io\\.springfox</groupId>\\s*<artifactId>springfox-swagger2</artifactId>(?:\\s*<version>[^<]+</version>)?",
                    "<groupId>org.springdoc</groupId>\n            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>\n            <version>2.5.0</version>"
            );
            result = result.replaceAll(
                    "<dependency>\\s*<groupId>io\\.springfox</groupId>\\s*<artifactId>springfox-swagger-ui</artifactId>(?:\\s*<version>[^<]+</version>)?\\s*</dependency>",
                    ""
            );
            rules.add("RULE-SPRINGFOX-TO-SPRINGDOC-OPENAPI3");
        }

        // 2. Upgrade MyBatis 2.x to 3.0.3
        if (result.contains("mybatis-spring-boot-starter")) {
            Pattern mybatisPattern = Pattern.compile("(?s)(<artifactId>mybatis-spring-boot-starter</artifactId>.*?<version>)2\\.[0-9]+\\.[0-9]+(</version>)");
            Matcher m = mybatisPattern.matcher(result);
            if (m.find()) {
                result = m.replaceFirst(Matcher.quoteReplacement(m.group(1)) + "3.0.3" + Matcher.quoteReplacement(m.group(2)));
                rules.add("RULE-MYBATIS-BOOT-3-JAKARTA-UPGRADE");
            }
        }

        // 2b. Upgrade mybatis-spring 2.x to 3.0.3
        if (result.contains("mybatis-spring")) {
            Pattern mybatisSpringPattern = Pattern.compile("(?s)(<artifactId>mybatis-spring</artifactId>.*?<version>)2\\.[0-9]+\\.[0-9]+(</version>)");
            Matcher m2 = mybatisSpringPattern.matcher(result);
            if (m2.find()) {
                result = m2.replaceAll(Matcher.quoteReplacement(m2.group(1)) + "3.0.3" + Matcher.quoteReplacement(m2.group(2)));
                rules.add("RULE-MYBATIS-SPRING-3-UPGRADE");
            }
            if (result.contains("<mybatis-spring.version>2.")) {
                result = result.replaceAll("<mybatis-spring\\.version>2\\.[0-9]+\\.[0-9]+</mybatis-spring\\.version>", "<mybatis-spring.version>3.0.3</mybatis-spring.version>");
                rules.add("RULE-MYBATIS-SPRING-PROPERTY-UPGRADE");
            }
        }

        // 2c. Upgrade HikariCP 4.x to 5.1.0 for Spring Boot 3
        if (result.contains("<HikariCP.version>4.")) {
            result = result.replaceAll("<HikariCP\\.version>4\\.[0-9]+\\.[0-9]+</HikariCP\\.version>", "<HikariCP.version>5.1.0</HikariCP.version>");
            rules.add("RULE-HIKARICP-VERSION-UPGRADE");
        }

        // 3. Inject -parameters into maven-compiler-plugin if not already present
        if (!result.contains("-parameters")) {
            if (result.contains("<artifactId>maven-compiler-plugin</artifactId>")) {
                if (result.contains("<compilerArgs>")) {
                    result = result.replaceAll(
                            "(?s)(<compilerArgs>)",
                            "$1\n                    <arg>-parameters</arg>"
                    );
                } else if (result.contains("<configuration>")) {
                    result = result.replaceAll(
                            "(?s)(<artifactId>maven-compiler-plugin</artifactId>.*?<configuration>)",
                            "$1\n                    <compilerArgs><arg>-parameters</arg></compilerArgs>"
                    );
                } else {
                    result = result.replaceAll(
                            "(<artifactId>maven-compiler-plugin</artifactId>)",
                            "$1\n                    <configuration><compilerArgs><arg>-parameters</arg></compilerArgs></configuration>"
                    );
                }
            } else if (result.contains("</plugins>")) {
                String pluginDef = """
                            <plugin>
                                <groupId>org.apache.maven.plugins</groupId>
                                <artifactId>maven-compiler-plugin</artifactId>
                                <configuration>
                                    <compilerArgs>
                                        <arg>-parameters</arg>
                                    </compilerArgs>
                                </configuration>
                            </plugin>
                        </plugins>""";
                result = result.replaceFirst("</plugins>", pluginDef);
            } else if (result.contains("</project>")) {
                String pluginDef = """
                    <build>
                        <plugins>
                            <plugin>
                                <groupId>org.apache.maven.plugins</groupId>
                                <artifactId>maven-compiler-plugin</artifactId>
                                <configuration>
                                    <compilerArgs>
                                        <arg>-parameters</arg>
                                    </compilerArgs>
                                </configuration>
                            </plugin>
                        </plugins>
                    </build>
                </project>""";
                result = result.replaceFirst("</project>", pluginDef);
            }
            rules.add("RULE-INJECT-COMPILER-PARAMETERS-FLAG");
        }

        return result;
    }

    private static String modernizeAnnotations(String code, List<String> rules) {
        String result = code;

        // Replace @Api(tags = "...") or @Api(value = "...") -> @Tag(name = "...")
        if (result.contains("@Api")) {
            result = result.replaceAll("import\\s+io\\.springfox\\.annotations\\.Api;", "import io.swagger.v3.oas.annotations.tags.Tag;");
            result = result.replaceAll("import\\s+io\\.swagger\\.annotations\\.Api;", "import io.swagger.v3.oas.annotations.tags.Tag;");
            result = result.replaceAll("@Api\\s*\\(\\s*(?:tags|value)\\s*=\\s*(\"[^\"]+\")\\s*\\)", "@Tag(name = $1)");
            rules.add("RULE-ANNOTATION-API-TO-TAG");
        }

        // Replace @ApiOperation(value = "...", notes = "...") -> @Operation(summary = "...", description = "...")
        if (result.contains("@ApiOperation")) {
            result = result.replaceAll("import\\s+io\\.springfox\\.annotations\\.ApiOperation;", "import io.swagger.v3.oas.annotations.Operation;");
            result = result.replaceAll("import\\s+io\\.swagger\\.annotations\\.ApiOperation;", "import io.swagger.v3.oas.annotations.Operation;");
            result = result.replaceAll("@ApiOperation\\s*\\(\\s*value\\s*=\\s*(\"[^\"]+\")\\s*,\\s*notes\\s*=\\s*(\"[^\"]+\")\\s*\\)",
                    "@Operation(summary = $1, description = $2)");
            result = result.replaceAll("@ApiOperation\\s*\\(\\s*(\"[^\"]+\")\\s*\\)",
                    "@Operation(summary = $1)");
            result = result.replaceAll("@ApiOperation\\s*\\(\\s*value\\s*=\\s*(\"[^\"]+\")\\s*\\)",
                    "@Operation(summary = $1)");
            rules.add("RULE-ANNOTATION-APIOPERATION-TO-OPERATION");
        }

        // Clean up remaining Swagger 2 imports
        result = result.replaceAll("import\\s+io\\.swagger\\.annotations\\.[^;]+;\n?", "");
        result = result.replaceAll("import\\s+io\\.springfox\\.[^;]+;\n?", "");

        return result;
    }
}
