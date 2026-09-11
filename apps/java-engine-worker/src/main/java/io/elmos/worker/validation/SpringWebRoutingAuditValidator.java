package io.elmos.worker.validation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Industrial-grade structural validator for Spring MVC Web Routing & HTTP Compatibility.
 *
 * <p>Audits a codebase to guarantee:
 * <ul>
 *   <li>Presence of trailing slash matching configuration when Spring MVC controllers are present.</li>
 *   <li>Zero lingering usage of legacy {@code javax.servlet} packages in web controllers, filters, interceptors, or exception handlers.</li>
 *   <li>Zero usage of deprecated {@code WebMvcConfigurerAdapter} (must implement {@code WebMvcConfigurer} directly).</li>
 *   <li>Zero usage of deprecated suffix pattern matching ({@code setUseSuffixPatternMatch(true)}).</li>
 * </ul>
 */
public final class SpringWebRoutingAuditValidator {

    public enum Severity {
        CRITICAL,
        HIGH,
        MEDIUM,
        LOW,
        INFO
    }

    public record WebRoutingViolation(
            String ruleId,
            Severity severity,
            String filePath,
            int line,
            String message,
            String remediationSnippet
    ) {}

    public record WebRoutingAuditReport(
            int totalFilesScanned,
            int totalViolations,
            int criticalViolations,
            int highViolations,
            double complianceScore,
            boolean isCompliant,
            List<WebRoutingViolation> violations
    ) {}

    public WebRoutingAuditReport auditProject(Path projectRoot) throws IOException {
        List<WebRoutingViolation> violations = new ArrayList<>();
        int filesScanned = 0;

        if (!Files.isDirectory(projectRoot)) {
            return new WebRoutingAuditReport(0, 0, 0, 0, 100.0, true, Collections.emptyList());
        }

        boolean hasControllers = false;
        boolean hasTrailingSlashConfig = false;

        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path jf : javaFiles) {
                filesScanned++;
                String content = Files.readString(jf, StandardCharsets.UTF_8);

                if (content.contains("@RestController") || content.contains("@Controller")) {
                    hasControllers = true;
                }
                if (content.contains("setUseTrailingSlashMatch(true)")
                        || content.contains("LegacyWebMvcTrailingSlashConfiguration")
                        || content.contains("setUseTrailingSlashMatch(Boolean.TRUE)")) {
                    hasTrailingSlashConfig = true;
                }

                auditJavaFile(jf, content, violations);
            }
        }

        // WEB-001: Missing trailing slash configuration when controllers are present
        if (hasControllers && !hasTrailingSlashConfig) {
            violations.add(new WebRoutingViolation(
                    "WEB-001",
                    Severity.HIGH,
                    projectRoot.toString(),
                    1,
                    "Spring Boot 3 replaced AntPathMatcher with PathPatternParser, breaking trailing-slash matching by default. "
                            + "Enterprise controllers detected without LegacyWebMvcTrailingSlashConfiguration or setUseTrailingSlashMatch(true).",
                    """
                    @Configuration
                    public class LegacyWebMvcTrailingSlashConfiguration implements WebMvcConfigurer {
                        @Override
                        public void configurePathMatch(PathMatchConfigurer configurer) {
                            configurer.setUseTrailingSlashMatch(true);
                        }
                    }
                    """
            ));
        }

        int critical = (int) violations.stream().filter(v -> v.severity() == Severity.CRITICAL).count();
        int high = (int) violations.stream().filter(v -> v.severity() == Severity.HIGH).count();
        int medium = (int) violations.stream().filter(v -> v.severity() == Severity.MEDIUM).count();

        double penalty = (critical * 25.0) + (high * 10.0) + (medium * 3.0);
        double complianceScore = Math.max(0.0, 100.0 - penalty);
        boolean isCompliant = critical == 0 && high == 0;

        return new WebRoutingAuditReport(
                filesScanned,
                violations.size(),
                critical,
                high,
                complianceScore,
                isCompliant,
                Collections.unmodifiableList(violations)
        );
    }

    private void auditJavaFile(Path javaFile, String content, List<WebRoutingViolation> violations) {
        String relativePath = javaFile.toString();

        // WEB-002: Lingering javax.servlet in web components
        if (content.contains("javax.servlet.http.")
                || content.contains("javax.servlet.Filter")
                || content.contains("javax.servlet.ServletException")
                || content.contains("javax.servlet.ServletRequest")
                || content.contains("javax.servlet.ServletResponse")) {
            violations.add(new WebRoutingViolation(
                    "WEB-002",
                    Severity.CRITICAL,
                    relativePath,
                    findLineNumber(content, "javax.servlet"),
                    "Legacy javax.servlet package detected in web component. "
                            + "Spring Boot 3+ and Jakarta EE 10 require jakarta.servlet.*.",
                    "import jakarta.servlet.http.HttpServletRequest;\nimport jakarta.servlet.http.HttpServletResponse;"
            ));
        }

        // WEB-003: WebMvcConfigurerAdapter
        if (content.contains("extends WebMvcConfigurerAdapter")) {
            violations.add(new WebRoutingViolation(
                    "WEB-003",
                    Severity.MEDIUM,
                    relativePath,
                    findLineNumber(content, "WebMvcConfigurerAdapter"),
                    "Deprecated WebMvcConfigurerAdapter detected. In Spring 5+ and Boot 3+, implement WebMvcConfigurer directly.",
                    "public class WebConfig implements WebMvcConfigurer { ... }"
            ));
        }

        // WEB-004: Deprecated setUseSuffixPatternMatch
        if (content.contains("setUseSuffixPatternMatch(")) {
            violations.add(new WebRoutingViolation(
                    "WEB-004",
                    Severity.MEDIUM,
                    relativePath,
                    findLineNumber(content, "setUseSuffixPatternMatch("),
                    "Deprecated setUseSuffixPatternMatch() detected. Suffix pattern matching has been removed in Spring Framework 6+.",
                    "// Suffix matching removed for security and unambiguous path resolution"
            ));
        }
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
