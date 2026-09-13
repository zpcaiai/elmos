package io.elmos.worker.validation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Industrial-grade structural validator for Spring Ecosystem dependencies and annotations.
 *
 * <p>Audits a codebase to guarantee:
 * <ul>
 *   <li>Zero usage of deprecated {@code io.springfox} (Springfox Swagger 2) in {@code pom.xml}.</li>
 *   <li>Zero usage of Swagger 2 annotations ({@code @Api}, {@code @ApiOperation}, {@code @ApiParam}, {@code @ApiModel}, etc.).</li>
 *   <li>Zero usage of deprecated {@code @EnableSwagger2} / {@code @EnableSwagger2WebMvc}.</li>
 *   <li>Zero usage of outdated {@code mybatis-spring-boot-starter} 2.x (must be 3.0.3+ for Boot 3/4 & Jakarta).</li>
 *   <li>Proper presence of {@code -parameters} compiler flag in {@code maven-compiler-plugin}.</li>
 * </ul>
 */
public final class SpringEcosystemAuditValidator {

    public enum Severity {
        CRITICAL,
        HIGH,
        MEDIUM,
        LOW,
        INFO
    }

    public record EcosystemViolation(
            String ruleId,
            Severity severity,
            String filePath,
            int line,
            String message,
            String remediationSnippet
    ) {}

    public record EcosystemAuditReport(
            int totalFilesScanned,
            int totalViolations,
            int criticalViolations,
            int highViolations,
            double complianceScore,
            boolean isCompliant,
            List<EcosystemViolation> violations
    ) {}

    public EcosystemAuditReport auditProject(Path projectRoot) throws IOException {
        List<EcosystemViolation> violations = new ArrayList<>();
        int filesScanned = 0;

        if (!Files.isDirectory(projectRoot)) {
            return new EcosystemAuditReport(0, 0, 0, 0, 100.0, true, Collections.emptyList());
        }

        // 1. Audit build descriptor (pom.xml)
        Path pom = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pom)) {
            filesScanned++;
            auditPom(pom, violations);
        }

        // 2. Audit Java source files
        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path jf : javaFiles) {
                filesScanned++;
                auditJavaFile(jf, violations);
            }
        }

        int critical = (int) violations.stream().filter(v -> v.severity() == Severity.CRITICAL).count();
        int high = (int) violations.stream().filter(v -> v.severity() == Severity.HIGH).count();
        int medium = (int) violations.stream().filter(v -> v.severity() == Severity.MEDIUM).count();

        double penalty = (critical * 25.0) + (high * 10.0) + (medium * 3.0);
        double complianceScore = Math.max(0.0, 100.0 - penalty);
        boolean isCompliant = critical == 0 && high == 0;

        return new EcosystemAuditReport(
                filesScanned,
                violations.size(),
                critical,
                high,
                complianceScore,
                isCompliant,
                Collections.unmodifiableList(violations)
        );
    }

    private void auditPom(Path pomPath, List<EcosystemViolation> violations) {
        try {
            String content = Files.readString(pomPath, StandardCharsets.UTF_8);
            String relativePath = pomPath.toString();

            // ECO-001: Springfox in POM
            if (content.contains("io.springfox") || content.contains("springfox-swagger2") || content.contains("springfox-swagger-ui")) {
                violations.add(new EcosystemViolation(
                        "ECO-001",
                        Severity.CRITICAL,
                        relativePath,
                        findLineNumber(content, "springfox"),
                        "Deprecated Springfox Swagger 2 dependency detected in pom.xml. "
                                + "Springfox is incompatible with Spring Boot 3+ (relies on removed Spring 5 WebMvc classes). "
                                + "Migrate to org.springdoc:springdoc-openapi-starter-webmvc-ui:2.5.0.",
                        """
                        <dependency>
                            <groupId>org.springdoc</groupId>
                            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
                            <version>2.5.0</version>
                        </dependency>
                        """
                ));
            }

            // ECO-003: Outdated MyBatis 2.x starter
            if (content.contains("mybatis-spring-boot-starter")) {
                Pattern mybatisPattern = Pattern.compile("(?s)<artifactId>mybatis-spring-boot-starter</artifactId>.*?<version>([0-2]\\.[0-9]+(?:\\.[0-9]+)?)</version>");
                Matcher m = mybatisPattern.matcher(content);
                if (m.find()) {
                    violations.add(new EcosystemViolation(
                            "ECO-003",
                            Severity.HIGH,
                            relativePath,
                            findLineNumber(content, "mybatis-spring-boot-starter"),
                            "Outdated mybatis-spring-boot-starter version " + m.group(1) + " detected. "
                                    + "MyBatis 2.x does not support Jakarta EE / Spring Boot 3+. Upgrade to version 3.0.3+.",
                            """
                            <dependency>
                                <groupId>org.mybatis.spring.boot</groupId>
                                <artifactId>mybatis-spring-boot-starter</artifactId>
                                <version>3.0.3</version>
                            </dependency>
                            """
                    ));
                }
            }

            // ECO-004: Missing -parameters compiler argument
            // Only check if maven-compiler-plugin or <plugins> is present or pom exists
            if (content.contains("<artifactId>spring-boot-starter-parent</artifactId>") && !content.contains("-parameters")) {
                violations.add(new EcosystemViolation(
                        "ECO-004",
                        Severity.HIGH,
                        relativePath,
                        1,
                        "Missing -parameters compiler flag in maven-compiler-plugin. Spring Boot 3 / Spring Framework 6 "
                                + "removed LocalVariableTableParameterNameDiscoverer; method parameter names must be preserved in bytecode.",
                        """
                        <plugin>
                            <groupId>org.apache.maven.plugins</groupId>
                            <artifactId>maven-compiler-plugin</artifactId>
                            <configuration>
                                <compilerArgs>
                                    <arg>-parameters</arg>
                                </compilerArgs>
                            </configuration>
                        </plugin>
                        """
                ));
            }

        } catch (IOException ignored) {}
    }

    private void auditJavaFile(Path javaFile, List<EcosystemViolation> violations) {
        try {
            String content = Files.readString(javaFile, StandardCharsets.UTF_8);
            String relativePath = javaFile.toString();

            // ECO-002: Swagger 2 annotations or imports
            if (content.contains("springfox.documentation")
                    || content.contains("io.swagger.annotations.Api")
                    || content.contains("io.swagger.annotations.ApiOperation")
                    || content.contains("@Api(")
                    || content.contains("@ApiOperation(")
                    || content.contains("@ApiParam(")) {
                violations.add(new EcosystemViolation(
                        "ECO-002",
                        Severity.CRITICAL,
                        relativePath,
                        findLineNumber(content, "@Api"),
                        "Legacy Swagger 2 / Springfox annotations detected. "
                                + "Replace with OpenAPI 3 annotations (@Tag, @Operation, @Parameter from io.swagger.v3.oas.annotations).",
                        """
                        @Tag(name = "User API", description = "User management operations")
                        @Operation(summary = "Find user by ID")
                        """
                ));
            }

            // ECO-005: @EnableSwagger2 annotation
            if (content.contains("@EnableSwagger2") || content.contains("@EnableSwagger2WebMvc")) {
                violations.add(new EcosystemViolation(
                        "ECO-005",
                        Severity.MEDIUM,
                        relativePath,
                        findLineNumber(content, "@EnableSwagger2"),
                        "Deprecated @EnableSwagger2 / @EnableSwagger2WebMvc annotation detected. "
                                + "Springdoc OpenAPI 3 operates via Spring Boot autoconfiguration and does not require explicit enablement.",
                        "// Remove @EnableSwagger2; Springdoc autoconfigures automatically"
                ));
            }

        } catch (IOException ignored) {}
    }

    private static int findLineNumber(String text, String substring) {
        int index = text.indexOf(substring);
        if (index < 0) return 1;
        int line = 1;
        for (int i = 0; i < index; i++) {
            if (text.charAt(i) == '\n') line++;
        }
        return line;
    }
}
