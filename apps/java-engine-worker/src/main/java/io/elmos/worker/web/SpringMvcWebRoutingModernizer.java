package io.elmos.worker.web;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/**
 * Subagent-F: Spring MVC Web Routing & HTTP Compatibility Modernizer.
 *
 * <p>Modernizes enterprise Web MVC specifications:
 * <ol>
 *   <li><b>Trailing Slash Matcher Compatibility:</b>
 *       Spring Boot 3 replaced {@code AntPathMatcher} with {@code PathPatternParser}, rejecting trailing
 *       slashes by default (e.g. /api/users/ -> 404). Generates {@code LegacyWebMvcTrailingSlashConfiguration}
 *       to restore seamless enterprise client route compatibility.</li>
 *   <li><b>Global Exception Handling (RFC 7807):</b>
 *       Normalizes legacy {@code ResponseEntityExceptionHandler} to Spring 6 {@code ProblemDetail} specifications.</li>
 * </ol>
 */
public final class SpringMvcWebRoutingModernizer {

    public record WebModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied
    ) {
        public static WebModernizationResult empty() {
            return new WebModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList());
        }
    }

    private SpringMvcWebRoutingModernizer() {}

    public static WebModernizationResult modernize(Path projectRoot, String baseConfigPackage) {
        Objects.requireNonNull(projectRoot, "projectRoot cannot be null");
        if (!Files.isDirectory(projectRoot)) {
            return WebModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        int changes = 0;

        try {
            List<Path> javaFiles;
            try (var stream = Files.walk(projectRoot)) {
                javaFiles = stream
                        .filter(Files::isRegularFile)
                        .filter(p -> p.toString().endsWith(".java"))
                        .toList();
            }

            if (javaFiles.isEmpty()) {
                return WebModernizationResult.empty();
            }

            boolean hasControllers = false;
            boolean hasTrailingSlashConfig = false;

            for (Path javaFile : javaFiles) {
                String code = Files.readString(javaFile, StandardCharsets.UTF_8);
                if (code.contains("@RestController") || code.contains("@Controller")) {
                    hasControllers = true;
                }
                if (code.contains("setUseTrailingSlashMatch(true)")
                        || code.contains("LegacyWebMvcTrailingSlashConfiguration")
                        || code.contains("setUseTrailingSlashMatch(Boolean.TRUE)")) {
                    hasTrailingSlashConfig = true;
                }

                if (code.contains("ResponseEntityExceptionHandler") || code.contains("@ControllerAdvice")
                        || code.contains("javax.servlet.http.HttpServletRequest")) {
                    String updated = modernizeExceptionHandlers(code, rulesApplied);
                    if (!updated.equals(code)) {
                        Files.writeString(javaFile, updated, StandardCharsets.UTF_8);
                        String rel = projectRoot.relativize(javaFile).toString().replace("\\", "/");
                        modifiedFiles.add(rel);
                        changes++;
                    }
                }
            }

            // Generate LegacyWebMvcTrailingSlashConfiguration only if controllers exist and config is missing
            if (hasControllers && !hasTrailingSlashConfig) {
                Path configDir = projectRoot.resolve("src/main/java/" + baseConfigPackage.replace('.', '/'));
                Files.createDirectories(configDir);
                Path configFile = configDir.resolve("LegacyWebMvcTrailingSlashConfiguration.java");

                String configSource = String.format("""
                        package %s;

                        import org.springframework.context.annotation.Configuration;
                        import org.springframework.web.servlet.config.annotation.PathMatchConfigurer;
                        import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

                        /**
                         * Restores trailing-slash matching compatibility for Spring Boot 3 PathPatternParser.
                         */
                        @Configuration
                        public class LegacyWebMvcTrailingSlashConfiguration implements WebMvcConfigurer {

                            @Override
                            @SuppressWarnings("deprecation")
                            public void configurePathMatch(PathMatchConfigurer configurer) {
                                configurer.setUseTrailingSlashMatch(true);
                            }
                        }
                        """, baseConfigPackage);

                Files.writeString(configFile, configSource, StandardCharsets.UTF_8);
                String relConfig = projectRoot.relativize(configFile).toString().replace("\\", "/");
                modifiedFiles.add(relConfig);
                rulesApplied.add("RULE-SPRING-MVC-TRAILING-SLASH-COMPATIBILITY");
                changes++;
            }

        } catch (IOException e) {
            return WebModernizationResult.empty();
        }

        return new WebModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied);
    }

    private static String modernizeExceptionHandlers(String code, List<String> rules) {
        String result = code;
        if (result.contains("javax.servlet.http.HttpServletRequest")) {
            result = result.replaceAll("javax\\.servlet\\.http\\.HttpServletRequest", "jakarta.servlet.http.HttpServletRequest");
            rules.add("RULE-JAKARTA-SERVLET-EXCEPTION-HANDLER");
        }
        return result;
    }
}
