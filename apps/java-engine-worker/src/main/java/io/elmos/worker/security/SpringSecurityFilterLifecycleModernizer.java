package io.elmos.worker.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Industrial-grade modernizer to resolve Spring Security 6 / Spring Boot 3 Filter duplicate execution defects.
 *
 * <p><b>Problem in Spring Boot &amp; Security:</b>
 * When a custom security filter (such as {@code JwtAuthenticationFilter} extending {@code OncePerRequestFilter}
 * or implementing {@code jakarta.servlet.Filter}) is declared as a Spring {@code @Component}, {@code @Service},
 * or {@code @Bean}, Spring Boot's {@code ServletContextInitializerBeans} discovers it and registers it as a root
 * Servlet container filter (mapped to {@code /*}).
 * In addition, the security configuration registers it in {@code SecurityFilterChain} via
 * {@code http.addFilterBefore(...) / addFilterAfter(...) / addFilterAt(...)}.
 * Consequently, the filter executes <i>twice</i> for every incoming HTTP request: once in the root servlet filter
 * chain, and once inside the Spring Security filter chain.
 *
 * <p><b>Industrial Resolution:</b>
 * Configures an explicit {@code FilterRegistrationBean<CustomFilter>} with {@code setEnabled(false)} in the
 * security configuration class. This prevents Spring Boot from registering the filter into the servlet container
 * while preserving its injection into {@code SecurityFilterChain}.
 */
public final class SpringSecurityFilterLifecycleModernizer {

    public record FilterLifecycleResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> disabledFilters
    ) {
        public static FilterLifecycleResult empty() {
            return new FilterLifecycleResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    public record CustomFilterInfo(
            String simpleClassName,
            String qualifiedClassName,
            boolean isBeanAnnotated,
            Path sourceFile
    ) {}

    private static final Pattern ADD_FILTER_PATTERN = Pattern.compile(
            "\\.addFilter(?:Before|After|At)\\s*\\(\\s*([a-zA-Z0-9_$.]+)(?:\\s*,|\\))"
    );

    private static final Pattern CLASS_DECL_PATTERN = Pattern.compile(
            "(?:public\\s+)?class\\s+([A-Za-z0-9_]+)\\s+(?:extends|implements)\\s+[^\\{]*(?:Filter|OncePerRequestFilter|GenericFilterBean)"
    );

    private static final Pattern BEAN_ANNOTATION_PATTERN = Pattern.compile(
            "@(Component|Service|Bean|Configuration)"
    );

    private static final Pattern FILTER_REGISTRATION_PATTERN = Pattern.compile(
            "FilterRegistrationBean\\s*<\\s*([A-Za-z0-9_]+)\\s*>"
    );

    private SpringSecurityFilterLifecycleModernizer() {}

    /**
     * Modernizes a project directory by finding custom filters registered in {@code SecurityFilterChain}
     * that are also Spring beans, and ensuring {@code FilterRegistrationBean} with {@code setEnabled(false)}
     * is generated.
     */
    public static FilterLifecycleResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return FilterLifecycleResult.empty();
        }

        Map<String, CustomFilterInfo> discoveredFilters = new LinkedHashMap<>();
        Set<String> alreadyDisabledFilters = new LinkedHashSet<>();
        Path primaryConfigPath = null;
        String primaryConfigContent = null;
        Set<String> filtersAddedToSecurityChain = new LinkedHashSet<>();

        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                String content = Files.readString(javaFile, StandardCharsets.UTF_8);

                // 1. Check for custom Filter classes
                Matcher classMatcher = CLASS_DECL_PATTERN.matcher(content);
                if (classMatcher.find()) {
                    String className = classMatcher.group(1);
                    boolean isBean = BEAN_ANNOTATION_PATTERN.matcher(content).find();
                    discoveredFilters.put(className, new CustomFilterInfo(className, className, isBean, javaFile));
                }

                // 2. Check for @Bean methods that return a Filter
                Pattern beanMethodPattern = Pattern.compile("@Bean\\s+(?:public\\s+)?([A-Za-z0-9_]+Filter)\\s+([a-zA-Z0-9_]+)\\s*\\(");
                Matcher beanMethodMatcher = beanMethodPattern.matcher(content);
                while (beanMethodMatcher.find()) {
                    String filterType = beanMethodMatcher.group(1);
                    discoveredFilters.put(filterType, new CustomFilterInfo(filterType, filterType, true, javaFile));
                }

                // 3. Check for filters added to SecurityFilterChain
                Matcher addFilterMatcher = ADD_FILTER_PATTERN.matcher(content);
                while (addFilterMatcher.find()) {
                    String filterRef = addFilterMatcher.group(1).trim();
                    // filterRef can be new JwtFilter(), or jwtFilter (variable), or this.jwtFilter
                    if (filterRef.startsWith("new ")) {
                        String instantiatedClass = filterRef.substring(4).replaceAll("\\(.*\\)", "").trim();
                        filtersAddedToSecurityChain.add(instantiatedClass);
                    } else {
                        filtersAddedToSecurityChain.add(filterRef);
                    }
                }

                // 4. Check for already existing FilterRegistrationBean disabling servlet container registration
                Matcher regMatcher = FILTER_REGISTRATION_PATTERN.matcher(content);
                while (regMatcher.find()) {
                    String filterType = regMatcher.group(1);
                    if (content.contains(".setEnabled(false)")) {
                        alreadyDisabledFilters.add(filterType);
                    }
                }

                // 5. Track primary security configuration file
                if (content.contains("@Configuration") && (content.contains("SecurityFilterChain") || content.contains("WebSecurityConfigurerAdapter"))) {
                    if (primaryConfigPath == null) {
                        primaryConfigPath = javaFile;
                        primaryConfigContent = content;
                    }
                }
            }
        } catch (IOException e) {
            return FilterLifecycleResult.empty();
        }

        if (primaryConfigPath == null || primaryConfigContent == null) {
            return FilterLifecycleResult.empty();
        }

        // Determine which filters need remediation
        List<String> filtersToDisable = new ArrayList<>();
        for (Map.Entry<String, CustomFilterInfo> entry : discoveredFilters.entrySet()) {
            String filterName = entry.getKey();
            CustomFilterInfo info = entry.getValue();

            boolean inSecurityChain = filtersAddedToSecurityChain.contains(filterName)
                    || filtersAddedToSecurityChain.stream().anyMatch(ref -> ref.equalsIgnoreCase(filterName) || ref.toLowerCase().contains(filterName.toLowerCase()));

            if (info.isBeanAnnotated() && inSecurityChain && !alreadyDisabledFilters.contains(filterName)) {
                filtersToDisable.add(filterName);
            }
        }

        if (filtersToDisable.isEmpty()) {
            return FilterLifecycleResult.empty();
        }

        // Perform AST / structured code injection into primaryConfigPath
        String updatedContent = primaryConfigContent;
        List<String> appliedRules = new ArrayList<>();
        int changes = 0;

        for (String filterName : filtersToDisable) {
            String methodName = Character.toLowerCase(filterName.charAt(0)) + filterName.substring(1) + "Registration";
            String beanCode = """

    @Bean
    public FilterRegistrationBean<%s> %s(%s filter) {
        FilterRegistrationBean<%s> registration = new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }
""".formatted(filterName, methodName, filterName, filterName);

            // Inject right before the closing brace of the configuration class
            int lastBraceIndex = updatedContent.lastIndexOf('}');
            if (lastBraceIndex != -1) {
                updatedContent = updatedContent.substring(0, lastBraceIndex) + beanCode + updatedContent.substring(lastBraceIndex);
                changes++;
                appliedRules.add("SEC-050: Generated FilterRegistrationBean with setEnabled(false) for " + filterName + " to eliminate duplicate servlet container execution");
            }
        }

        // Ensure necessary imports are present
        if (!updatedContent.contains("import org.springframework.boot.web.servlet.FilterRegistrationBean;")) {
            updatedContent = insertImport(updatedContent, "org.springframework.boot.web.servlet.FilterRegistrationBean");
        }

        try {
            Files.writeString(primaryConfigPath, updatedContent, StandardCharsets.UTF_8);
            String relPath = projectRoot.relativize(primaryConfigPath).toString().replace("\\", "/");
            return new FilterLifecycleResult(true, changes, Set.of(relPath), appliedRules, filtersToDisable);
        } catch (IOException e) {
            return FilterLifecycleResult.empty();
        }
    }

    /**
     * Modernizes a single Java source file or pair of filter and config content in-memory.
     */
    public static String modernizeContent(String configContent, String filterTypeName) {
        Objects.requireNonNull(configContent, "configContent must not be null");
        Objects.requireNonNull(filterTypeName, "filterTypeName must not be null");

        if (configContent.contains("FilterRegistrationBean<" + filterTypeName + ">") && configContent.contains(".setEnabled(false)")) {
            return configContent;
        }

        String methodName = Character.toLowerCase(filterTypeName.charAt(0)) + filterTypeName.substring(1) + "Registration";
        String beanCode = """

    @Bean
    public FilterRegistrationBean<%s> %s(%s filter) {
        FilterRegistrationBean<%s> registration = new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }
""".formatted(filterTypeName, methodName, filterTypeName, filterTypeName);

        int lastBraceIndex = configContent.lastIndexOf('}');
        if (lastBraceIndex == -1) {
            return configContent;
        }

        String updated = configContent.substring(0, lastBraceIndex) + beanCode + configContent.substring(lastBraceIndex);
        if (!updated.contains("import org.springframework.boot.web.servlet.FilterRegistrationBean;")) {
            updated = insertImport(updated, "org.springframework.boot.web.servlet.FilterRegistrationBean");
        }
        return updated;
    }

    private static String insertImport(String code, String importStatement) {
        String fullImport = "import " + importStatement + ";\n";
        int packageIdx = code.indexOf("package ");
        if (packageIdx != -1) {
            int semi = code.indexOf(";\n", packageIdx);
            if (semi != -1) {
                return code.substring(0, semi + 2) + "\n" + fullImport + code.substring(semi + 2);
            }
        }
        return fullImport + code;
    }
}
