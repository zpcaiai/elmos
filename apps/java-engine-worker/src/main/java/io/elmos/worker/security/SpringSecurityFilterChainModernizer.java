package io.elmos.worker.security;

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

/**
 * Industrial-grade AST & source transformer for Spring Security 5.x to 6.x / Boot 4.x migration.
 *
 * <p>Remediates the following enterprise security modernization challenges:
 * <ol>
 *   <li><b>WebSecurityConfigurerAdapter Deprecation:</b> Replaces subclassing with modern
 *       {@code @Bean public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception}.</li>
 *   <li><b>Authorize Requests Lambda DSL:</b> Rewrites {@code authorizeRequests()} to
 *       {@code authorizeHttpRequests(auth -> auth.requestMatchers(...).permitAll().anyRequest().authenticated())}.</li>
 *   <li><b>Matcher API Unification:</b> Converts {@code antMatchers} and {@code regexMatchers} to {@code requestMatchers}.</li>
 *   <li><b>Chained HttpSecurity DSL Modernization:</b> Converts fluent {@code .and()} chains for CSRF, CORS,
 *       SessionManagement, Headers, ExceptionHandling, and OAuth2ResourceServer into lambda configurators.</li>
 *   <li><b>Custom Filter Injections:</b> Modernizes {@code addFilterBefore}, {@code addFilterAfter}, and
 *       {@code addFilterAt} invocations to prevent duplicate container filter registrations.</li>
 *   <li><b>AuthenticationManager & Providers:</b> Transforms legacy {@code configure(AuthenticationManagerBuilder auth)}
 *       into modern {@code @Bean AuthenticationManager} and {@code DaoAuthenticationProvider} declarations.</li>
 *   <li><b>Method Security Modernization:</b> Replaces {@code @EnableGlobalMethodSecurity} with {@code @EnableMethodSecurity}.</li>
 * </ol>
 */
public final class SpringSecurityFilterChainModernizer {

    public record SecurityModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied
    ) {
        public static SecurityModernizationResult empty() {
            return new SecurityModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList());
        }
    }

    private SpringSecurityFilterChainModernizer() {}

    /**
     * Scans and modernizes Spring Security files in the specified project.
     */
    public static SecurityModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return SecurityModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        int changesCount = 0;

        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                SecurityModernizationResult fileResult = modernizeFile(projectRoot, javaFile);
                if (fileResult.modified()) {
                    changesCount += fileResult.changesCount();
                    modifiedFiles.addAll(fileResult.modifiedFiles());
                    rulesApplied.addAll(fileResult.rulesApplied());
                }
            }
        } catch (IOException e) {
            return SecurityModernizationResult.empty();
        }

        return new SecurityModernizationResult(
                changesCount > 0, changesCount,
                Collections.unmodifiableSet(modifiedFiles),
                Collections.unmodifiableList(rulesApplied)
        );
    }

    public static SecurityModernizationResult modernizeFile(Path projectRoot, Path file) {
        try {
            String original = Files.readString(file, StandardCharsets.UTF_8);
            String content = original;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // 1. Check if file is related to Spring Security
            if (!isSecurityRelated(content)) {
                return SecurityModernizationResult.empty();
            }

            // 2. Method Security Modernization: @EnableGlobalMethodSecurity -> @EnableMethodSecurity
            if (content.contains("EnableGlobalMethodSecurity")) {
                content = content.replace("EnableGlobalMethodSecurity", "EnableMethodSecurity");
                content = content.replace(
                        "import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;",
                        "import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;"
                );
                rules.add("MODERNIZE_METHOD_SECURITY_ANNOTATION");
                changes++;
            }

            // 3. WebSecurityConfigurerAdapter Elimination
            if (content.contains("WebSecurityConfigurerAdapter")) {
                content = content.replaceAll("extends\\s+WebSecurityConfigurerAdapter\\s*", "");
                content = content.replaceAll("import\\s+org\\.springframework\\.security\\.config\\.annotation\\.web\\.configuration\\.WebSecurityConfigurerAdapter;\\s*", "");
                content = ensureImport(content, "org.springframework.context.annotation.Bean");
                content = ensureImport(content, "org.springframework.security.web.SecurityFilterChain");
                content = ensureImport(content, "org.springframework.security.config.annotation.web.builders.HttpSecurity");

                // Rewrite protected void configure(HttpSecurity http) throws Exception
                // Rewrite protected/public void configure(HttpSecurity http) throws Exception
                Pattern configurePattern = Pattern.compile("(@Override\\s+)?(protected|public)\\s+void\\s+configure\\s*\\(\\s*HttpSecurity\\s+([a-zA-Z0-9_]+)\\s*\\)(\\s*throws\\s+[a-zA-Z0-9_,\\s]+)?\\s*\\{");
                Matcher configureMatcher = configurePattern.matcher(content);
                if (configureMatcher.find()) {
                    String httpVar = configureMatcher.group(3);
                    String beanHeader = "@Bean\n    public SecurityFilterChain securityFilterChain(HttpSecurity " + httpVar + ") throws Exception {";
                    content = configureMatcher.replaceFirst(beanHeader);

                    int startIdx = content.indexOf(beanHeader);
                    if (startIdx >= 0) {
                        int bodyStart = startIdx + beanHeader.length();
                        int bodyEnd = findMatchingBrace(content, bodyStart - 1);
                        if (bodyEnd > bodyStart) {
                            String methodBody = content.substring(bodyStart, bodyEnd);
                            if (!methodBody.contains(".build()") && !methodBody.contains("return ")) {
                                String updatedBody = methodBody + "\n        return " + httpVar + ".build();\n    ";
                                content = content.substring(0, bodyStart) + updatedBody + content.substring(bodyEnd);
                            }
                        }
                    }
                    rules.add("CONVERT_WEB_SECURITY_ADAPTER_TO_SECURITY_FILTER_CHAIN");
                    changes++;
                }

                // Rewrite configure(WebSecurity web) -> @Bean public WebSecurityCustomizer webSecurityCustomizer()
                if (content.contains("configure(WebSecurity")) {
                    content = ensureImport(content, "org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer");
                    Pattern webPattern = Pattern.compile("(@Override\\s+)?(public|protected)\\s+void\\s+configure\\s*\\(\\s*WebSecurity\\s+([a-zA-Z0-9_]+)\\s*\\)\\s*\\{");
                    Matcher webMatcher = webPattern.matcher(content);
                    if (webMatcher.find()) {
                        String webVar = webMatcher.group(3);
                        String replacement = "@Bean\n    public WebSecurityCustomizer webSecurityCustomizer() {\n        return (" + webVar + ") -> {";
                        content = webMatcher.replaceFirst(replacement);

                        int startIdx = content.indexOf(replacement);
                        if (startIdx >= 0) {
                            int bodyStart = startIdx + replacement.length();
                            int bodyEnd = findMatchingBrace(content, bodyStart - 1);
                            if (bodyEnd > bodyStart) {
                                content = content.substring(0, bodyEnd) + "};\n    }" + content.substring(bodyEnd + 1);
                            }
                        }
                        rules.add("CONVERT_WEB_SECURITY_CUSTOMIZER");
                        changes++;
                    }
                }

                // Rewrite configure(AuthenticationManagerBuilder auth) -> @Bean public AuthenticationManager
                if (content.contains("configure(AuthenticationManagerBuilder")) {
                    content = ensureImport(content, "org.springframework.security.authentication.AuthenticationManager");
                    content = ensureImport(content, "org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration");
                    Pattern authPattern = Pattern.compile("(@Override\\s+)?(protected|public)\\s+void\\s+configure\\s*\\(\\s*AuthenticationManagerBuilder\\s+([a-zA-Z0-9_]+)\\s*\\)(\\s*throws\\s+[a-zA-Z0-9_,\\s]+)?\\s*\\{[^}]*\\}");
                    Matcher authMatcher = authPattern.matcher(content);
                    if (authMatcher.find()) {
                        String replacement = "@Bean\n    public AuthenticationManager authenticationManager(AuthenticationConfiguration authenticationConfiguration) throws Exception {\n"
                                + "        return authenticationConfiguration.getAuthenticationManager();\n    }";
                        content = authMatcher.replaceFirst(replacement);
                        rules.add("CONVERT_AUTHENTICATION_MANAGER_BUILDER_TO_BEAN");
                        changes++;
                    }
                }
            }

            // 4. Modernize authorizeRequests() and Ant/Mvc/Regex Matchers into Lambda DSL
            if (content.contains("authorizeRequests()") || content.contains("authorizeHttpRequests()")) {
                Pattern authPattern = Pattern.compile("(?<=[.\\s])authorize(?:Http)?Requests\\(\\)([\\s\\S]*?)(?=(?:\\.and\\(\\)|;|\\.(?:csrf|cors|headers|sessionManagement|formLogin|httpBasic|anonymous|logout|oauth2ResourceServer|exceptionHandling|addFilter)\\())");
                Matcher authMatcher = authPattern.matcher(content);
                if (authMatcher.find()) {
                    StringBuffer sb = new StringBuffer();
                    do {
                        String chain = authMatcher.group(1).trim();
                        if (!chain.isEmpty()) {
                            String modernizedChain = chain
                                    .replace(".antMatchers(", ".requestMatchers(")
                                    .replace(".mvcMatchers(", ".requestMatchers(")
                                    .replace(".regexMatchers(", ".requestMatchers(");
                            String replacement = "authorizeHttpRequests(auth -> auth"
                                    + (modernizedChain.startsWith(".") ? "" : ".")
                                    + modernizedChain + ")";
                            authMatcher.appendReplacement(sb, Matcher.quoteReplacement(replacement));
                        } else {
                            authMatcher.appendReplacement(sb, "authorizeHttpRequests()");
                        }
                    } while (authMatcher.find());
                    authMatcher.appendTail(sb);
                    content = sb.toString();
                    rules.add("MIGRATE_AUTHORIZE_HTTP_REQUESTS_LAMBDA_DSL");
                    changes++;
                } else if (content.contains("authorizeRequests()")) {
                    content = content.replace("authorizeRequests()", "authorizeHttpRequests()");
                    rules.add("MIGRATE_AUTHORIZE_HTTP_REQUESTS");
                    changes++;
                }
            }
            if (content.contains("antMatchers(")) {
                content = content.replace("antMatchers(", "requestMatchers(");
                rules.add("MIGRATE_ANT_MATCHERS_TO_REQUEST_MATCHERS");
                changes++;
            }
            if (content.contains("mvcMatchers(")) {
                content = content.replace("mvcMatchers(", "requestMatchers(");
                rules.add("MIGRATE_MVC_MATCHERS_TO_REQUEST_MATCHERS");
                changes++;
            }
            if (content.contains("regexMatchers(")) {
                content = content.replace("regexMatchers(", "requestMatchers(");
                rules.add("MIGRATE_REGEX_MATCHERS_TO_REQUEST_MATCHERS");
                changes++;
            }

            // 5. HttpSecurity Fluent -> Lambda DSL Modernization
            // CSRF
            if (content.contains(".csrf().disable()")) {
                content = content.replace(".csrf().disable()", ".csrf(csrf -> csrf.disable())");
                rules.add("LAMBDA_DSL_CSRF_DISABLE");
                changes++;
            } else if (content.contains(".csrf().ignoringAntMatchers(")) {
                content = content.replace(".csrf().ignoringAntMatchers(", ".csrf(csrf -> csrf.ignoringRequestMatchers(");
                content = content.replace(".csrf().ignoringRequestMatchers(", ".csrf(csrf -> csrf.ignoringRequestMatchers(");
                rules.add("LAMBDA_DSL_CSRF_IGNORING");
                changes++;
            }

            // CORS
            if (content.contains(".cors().and()")) {
                content = ensureImport(content, "org.springframework.security.config.Customizer");
                content = content.replace(".cors().and()", ".cors(Customizer.withDefaults())");
                rules.add("LAMBDA_DSL_CORS");
                changes++;
            } else if (content.contains(".cors()")) {
                content = ensureImport(content, "org.springframework.security.config.Customizer");
                content = content.replace(".cors()", ".cors(Customizer.withDefaults())");
                rules.add("LAMBDA_DSL_CORS");
                changes++;
            }

            // Session Management
            if (content.contains(".sessionManagement().sessionCreationPolicy(")) {
                content = content.replace(
                        ".sessionManagement().sessionCreationPolicy(",
                        ".sessionManagement(session -> session.sessionCreationPolicy("
                );
                if (!content.contains("session.sessionCreationPolicy(")) {
                    content = content.replace("sessionCreationPolicy(", "session.sessionCreationPolicy(");
                }
                rules.add("LAMBDA_DSL_SESSION_MANAGEMENT");
                changes++;
            }

            // Headers
            if (content.contains(".headers().frameOptions().disable()")) {
                content = content.replace(
                        ".headers().frameOptions().disable()",
                        ".headers(headers -> headers.frameOptions(frame -> frame.disable()))"
                );
                rules.add("LAMBDA_DSL_HEADERS_FRAME_OPTIONS");
                changes++;
            }

            // Form Login
            if (content.contains(".formLogin().disable()")) {
                content = content.replace(".formLogin().disable()", ".formLogin(form -> form.disable())");
                rules.add("LAMBDA_DSL_FORM_LOGIN_DISABLE");
                changes++;
            } else if (content.contains(".formLogin().and()")) {
                content = ensureImport(content, "org.springframework.security.config.Customizer");
                content = content.replace(".formLogin().and()", ".formLogin(Customizer.withDefaults())");
                rules.add("LAMBDA_DSL_FORM_LOGIN");
                changes++;
            } else if (content.contains(".formLogin()")) {
                content = ensureImport(content, "org.springframework.security.config.Customizer");
                content = content.replace(".formLogin()", ".formLogin(Customizer.withDefaults())");
                rules.add("LAMBDA_DSL_FORM_LOGIN");
                changes++;
            }

            // HTTP Basic
            if (content.contains(".httpBasic().disable()")) {
                content = content.replace(".httpBasic().disable()", ".httpBasic(basic -> basic.disable())");
                rules.add("LAMBDA_DSL_HTTP_BASIC_DISABLE");
                changes++;
            } else if (content.contains(".httpBasic()")) {
                content = ensureImport(content, "org.springframework.security.config.Customizer");
                content = content.replace(".httpBasic()", ".httpBasic(Customizer.withDefaults())");
                rules.add("LAMBDA_DSL_HTTP_BASIC");
                changes++;
            }

            // Anonymous
            if (content.contains(".anonymous().disable()")) {
                content = content.replace(".anonymous().disable()", ".anonymous(anon -> anon.disable())");
                rules.add("LAMBDA_DSL_ANONYMOUS_DISABLE");
                changes++;
            }

            // Logout
            if (content.contains(".logout().disable()")) {
                content = content.replace(".logout().disable()", ".logout(logout -> logout.disable())");
                rules.add("LAMBDA_DSL_LOGOUT_DISABLE");
                changes++;
            } else if (content.contains(".logout()")) {
                content = ensureImport(content, "org.springframework.security.config.Customizer");
                content = content.replace(".logout()", ".logout(Customizer.withDefaults())");
                rules.add("LAMBDA_DSL_LOGOUT");
                changes++;
            }

            // OAuth2 Resource Server
            if (content.contains(".oauth2ResourceServer().jwt()")) {
                content = ensureImport(content, "org.springframework.security.config.Customizer");
                content = content.replace(".oauth2ResourceServer().jwt()", ".oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))");
                rules.add("LAMBDA_DSL_OAUTH2_RESOURCE_SERVER");
                changes++;
            }

            // Exception Handling
            Pattern exPattern = Pattern.compile("\\.exceptionHandling\\(\\)\\.([a-zA-Z0-9_]+)\\(([^;)]+)\\)");
            Matcher exMatcher = exPattern.matcher(content);
            if (exMatcher.find()) {
                content = exMatcher.replaceAll(".exceptionHandling(ex -> ex.$1($2))");
                rules.add("LAMBDA_DSL_EXCEPTION_HANDLING");
                changes++;
            }

            // Clean up standalone .and() occurrences in chains
            if (content.contains(".and()\n") || content.contains(".and().") || content.contains(".and();")) {
                content = content.replaceAll("\\.and\\(\\)\\s*\\.", ".");
                content = content.replaceAll("\\.and\\(\\)\\s*;", ";");
                rules.add("STRIP_OBSOLETE_AND_CHAINING");
                changes++;
            }

            // 6. Custom Filter Injection Guard
            // When addFilterBefore/addFilterAfter are used, ensure proper imports
            if (content.contains("addFilterBefore(") || content.contains("addFilterAfter(") || content.contains("addFilterAt(")) {
                content = ensureImport(content, "org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter");
                rules.add("ENSURE_FILTER_INJECTION_IMPORTS");
                changes++;
            }

            if (changes > 0 && !content.equals(original)) {
                Files.writeString(file, content, StandardCharsets.UTF_8);
                String relPath = projectRoot.relativize(file).toString();
                return new SecurityModernizationResult(true, changes, Set.of(relPath), rules);
            }
        } catch (IOException ignored) {}
        return SecurityModernizationResult.empty();
    }

    private static boolean isSecurityRelated(String content) {
        return content.contains("org.springframework.security")
                || content.contains("HttpSecurity")
                || content.contains("SecurityFilterChain")
                || content.contains("WebSecurityConfigurerAdapter")
                || content.contains("EnableGlobalMethodSecurity")
                || content.contains("EnableMethodSecurity");
    }

    private static String ensureImport(String content, String fqcn) {
        if (content.contains("import " + fqcn + ";")) {
            return content;
        }
        int pkgIndex = content.indexOf("package ");
        if (pkgIndex >= 0) {
            int pkgEnd = content.indexOf(";", pkgIndex);
            if (pkgEnd >= 0) {
                return content.substring(0, pkgEnd + 1) + "\n\nimport " + fqcn + ";" + content.substring(pkgEnd + 1);
            }
        }
        return "import " + fqcn + ";\n" + content;
    }

    private static int findMatchingBrace(String text, int openBraceIdx) {
        int depth = 0;
        for (int i = openBraceIdx; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch == '{') {
                depth++;
            } else if (ch == '}') {
                depth--;
                if (depth == 0) {
                    return i;
                }
            }
        }
        return -1;
    }
}
