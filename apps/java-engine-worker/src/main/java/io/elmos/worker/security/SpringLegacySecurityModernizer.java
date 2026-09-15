package io.elmos.worker.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Fail-closed migration for legacy Spring OAuth2 Boot and Apache Shiro security surfaces. */
public final class SpringLegacySecurityModernizer {
    static final String SHIRO_VERSION = "3.0.1";

    public record ModernizationResult(
            boolean modified,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> blockingObligations
    ) {}

    private static final Pattern LEGACY_OAUTH_DEPENDENCY = Pattern.compile(
            "(?s)<dependency>\\s*<groupId>org\\.springframework\\.security\\.oauth</groupId>\\s*"
                    + "<artifactId>spring-security-oauth2</artifactId>.*?</dependency>");
    private static final Pattern SHIRO_DEPENDENCY = Pattern.compile(
            "(?s)(<dependency>\\s*<groupId>org\\.apache\\.shiro</groupId>\\s*<artifactId>)"
                    + "(?:shiro-spring|shiro-spring-boot-starter|shiro-spring-boot-web-starter)(</artifactId>)"
                    + "(?:(?!</dependency>).)*?</dependency>");
    private static final Pattern PACKAGE = Pattern.compile("(?m)^package\\s+([A-Za-z_$][\\w$]*(?:\\.[A-Za-z_$][\\w$]*)*)\\s*;");
    private static final Pattern CLASS_NAME = Pattern.compile("\\bclass\\s+([A-Za-z_$][\\w$]*)");

    private SpringLegacySecurityModernizer() {}

    public static ModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        Set<String> changed = new LinkedHashSet<>();
        Set<String> rules = new LinkedHashSet<>();
        Set<String> blockers = new LinkedHashSet<>();
        if (!Files.isDirectory(projectRoot)) {
            return new ModernizationResult(false, changed, List.copyOf(rules),
                    List.of("project root does not exist"));
        }

        boolean authorizationServerSeen = false;
        boolean resourceServerSeen = false;
        boolean oauthSourceSafelyRewritten = true;
        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().endsWith(".java")).toList();
            for (Path file : javaFiles) {
                String source = Files.readString(file, StandardCharsets.UTF_8);
                if (source.contains("@EnableAuthorizationServer") || source.contains("@EnableResourceServer")) {
                    authorizationServerSeen |= source.contains("@EnableAuthorizationServer");
                    resourceServerSeen |= source.contains("@EnableResourceServer");
                    oauthSourceSafelyRewritten &= !hasCustomOauthConfiguration(source);
                }
            }
            for (Path file : javaFiles) {
                String source = Files.readString(file, StandardCharsets.UTF_8);
                if (source.contains("@EnableAuthorizationServer") || source.contains("@EnableResourceServer")) {
                    if (oauthSourceSafelyRewritten) {
                        rewriteLegacyOauthConfiguration(projectRoot, file, source, changed, rules, blockers);
                        source = Files.readString(file, StandardCharsets.UTF_8);
                    } else {
                        blockers.add(relative(projectRoot, file)
                                + ": legacy OAuth2 project contains custom or mixed server configuration; all legacy sources and dependency are retained atomically");
                    }
                }
                rewriteShiroJakartaImports(projectRoot, file, source, changed, rules, blockers);
            }
        } catch (IOException error) {
            blockers.add("IO:" + error.getClass().getSimpleName());
            oauthSourceSafelyRewritten = false;
        }

        try (var stream = Files.walk(projectRoot)) {
            for (Path pom : stream.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().equals("pom.xml")).toList()) {
                rewritePom(projectRoot, pom, authorizationServerSeen, resourceServerSeen,
                        oauthSourceSafelyRewritten,
                        changed, rules, blockers);
            }
        } catch (IOException error) {
            blockers.add("IO:" + error.getClass().getSimpleName());
        }
        return new ModernizationResult(!changed.isEmpty(), Set.copyOf(changed),
                List.copyOf(rules), List.copyOf(blockers));
    }

    private static boolean rewriteLegacyOauthConfiguration(
            Path root, Path file, String source, Set<String> changed,
            Set<String> rules, Set<String> blockers) throws IOException {
        boolean authorizationServer = source.contains("@EnableAuthorizationServer");
        boolean resourceServer = source.contains("@EnableResourceServer");
        Matcher packageMatcher = PACKAGE.matcher(source);
        Matcher classMatcher = CLASS_NAME.matcher(source);
        if (!classMatcher.find()) {
            blockers.add(relative(root, file) + ": legacy OAuth2 configuration class name was not recovered");
            return false;
        }
        String packageLine = packageMatcher.find() ? "package " + packageMatcher.group(1) + ";\n\n" : "";
        String className = classMatcher.group(1);
        String replacement;
        if (authorizationServer) {
            replacement = packageLine + """
                    import org.springframework.context.annotation.Bean;
                    import org.springframework.context.annotation.Configuration;
                    import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

                    @Configuration
                    public class %s {
                        @Bean
                        AuthorizationServerSettings authorizationServerSettings() {
                            return AuthorizationServerSettings.builder().build();
                        }
                    }
                    """.formatted(className);
            rules.add("LEGACY_OAUTH2_AUTHORIZATION_SERVER_TO_BOOT_STARTER");
            blockers.add(relative(root, file)
                    + ": bind issuer, registered clients, consent, JWK/key rotation, token lifetimes and legacy token migration before startup");
        } else {
            replacement = packageLine + """
                    import org.springframework.context.annotation.Bean;
                    import org.springframework.context.annotation.Configuration;
                    import org.springframework.security.config.Customizer;
                    import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                    import org.springframework.security.web.SecurityFilterChain;

                    @Configuration
                    public class %s {
                        @Bean
                        SecurityFilterChain resourceServerSecurityFilterChain(HttpSecurity http) throws Exception {
                            http.authorizeHttpRequests(authorize -> authorize.anyRequest().authenticated());
                            http.oauth2ResourceServer(resource -> resource.jwt(Customizer.withDefaults()));
                            return http.build();
                        }
                    }
                    """.formatted(className);
            rules.add("LEGACY_OAUTH2_RESOURCE_SERVER_TO_SECURITY_FILTER_CHAIN");
            blockers.add(relative(root, file)
                    + ": bind trusted issuer/JWK set and replay scopes, authorities, audience and bearer-token failures");
        }
        Files.writeString(file, replacement, StandardCharsets.UTF_8);
        changed.add(relative(root, file));
        return true;
    }

    /**
     * Modernizes in-memory Java source for legacy OAuth2 and Apache Shiro.
     */
    public static String modernizeJavaSource(String source, List<String> rules, List<String> blockers) {
        if (source == null || source.isBlank()) return source;
        String current = source;

        if (current.contains("@EnableAuthorizationServer") || current.contains("@EnableResourceServer")) {
            if (hasCustomOauthConfiguration(current)) {
                if (blockers != null) blockers.add("legacy OAuth2 project contains custom or mixed server configuration; all legacy sources and dependency are retained atomically");
            } else {
                boolean authorizationServer = current.contains("@EnableAuthorizationServer");
                Matcher packageMatcher = PACKAGE.matcher(current);
                Matcher classMatcher = CLASS_NAME.matcher(current);
                if (classMatcher.find()) {
                    String packageLine = packageMatcher.find() ? "package " + packageMatcher.group(1) + ";\n\n" : "";
                    String className = classMatcher.group(1);
                    if (authorizationServer) {
                        current = packageLine + """
                                import org.springframework.context.annotation.Bean;
                                import org.springframework.context.annotation.Configuration;
                                import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

                                @Configuration
                                public class %s {
                                    @Bean
                                    AuthorizationServerSettings authorizationServerSettings() {
                                        return AuthorizationServerSettings.builder().build();
                                    }
                                }
                                """.formatted(className);
                        if (rules != null) rules.add("LEGACY_OAUTH2_AUTHORIZATION_SERVER_TO_BOOT_STARTER");
                        if (blockers != null) blockers.add("bind issuer, registered clients, consent, JWK/key rotation, token lifetimes and legacy token migration before startup");
                    } else {
                        current = packageLine + """
                                import org.springframework.context.annotation.Bean;
                                import org.springframework.context.annotation.Configuration;
                                import org.springframework.security.config.Customizer;
                                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                                import org.springframework.security.web.SecurityFilterChain;

                                @Configuration
                                public class %s {
                                    @Bean
                                    SecurityFilterChain resourceServerSecurityFilterChain(HttpSecurity http) throws Exception {
                                        http.authorizeHttpRequests(authorize -> authorize.anyRequest().authenticated());
                                        http.oauth2ResourceServer(resource -> resource.jwt(Customizer.withDefaults()));
                                        return http.build();
                                    }
                                }
                                """.formatted(className);
                        if (rules != null) rules.add("LEGACY_OAUTH2_RESOURCE_SERVER_TO_SECURITY_FILTER_CHAIN");
                        if (blockers != null) blockers.add("bind trusted issuer/JWK set and replay scopes, authorities, audience and bearer-token failures");
                    }
                }
            }
        }

        if (current.contains("org.apache.shiro")) {
            String after = current
                    .replace("import javax.servlet.", "import jakarta.servlet.")
                    .replace("import javax.annotation.", "import jakarta.annotation.");
            if (!after.equals(current)) {
                current = after;
                if (rules != null) rules.add("SHIRO_JAKARTA_SOURCE_NAMESPACE");
            }
            if (containsAny(current, " extends AuthorizingRealm", " extends AuthenticatingRealm",
                    "SessionDAO", "RememberMeManager", "ShiroFilterFactoryBean", "filterChainDefinitionMap")) {
                if (blockers != null) blockers.add("Shiro realm credentials, permission matching, sessions, remember-me and URL-chain ordering require security differential replay");
            }
        }

        return current;
    }

    private static boolean hasCustomOauthConfiguration(String source) {
        return (source.contains("@EnableAuthorizationServer") && source.contains("@EnableResourceServer"))
                || source.contains("ClientDetailsServiceConfigurer")
                || source.contains("AuthorizationServerEndpointsConfigurer")
                || source.contains("AuthorizationServerSecurityConfigurer")
                || source.contains("ResourceServerSecurityConfigurer")
                || Pattern.compile("\\bconfigure\\s*\\(").matcher(source).find();
    }

    private static void rewriteShiroJakartaImports(
            Path root, Path file, String original, Set<String> changed,
            Set<String> rules, Set<String> blockers) throws IOException {
        if (!original.contains("org.apache.shiro")) return;
        String after = original
                .replace("import javax.servlet.", "import jakarta.servlet.")
                .replace("import javax.annotation.", "import jakarta.annotation.");
        if (!after.equals(original)) {
            Files.writeString(file, after, StandardCharsets.UTF_8);
            changed.add(relative(root, file));
            rules.add("SHIRO_JAKARTA_SOURCE_NAMESPACE");
        }
        if (containsAny(original, " extends AuthorizingRealm", " extends AuthenticatingRealm",
                "SessionDAO", "RememberMeManager", "ShiroFilterFactoryBean", "filterChainDefinitionMap")) {
            blockers.add(relative(root, file)
                    + ": Shiro realm credentials, permission matching, sessions, remember-me and URL-chain ordering require security differential replay");
        }
    }

    private static void rewritePom(Path root, Path pom, boolean authorizationServerSeen,
                                   boolean resourceServerSeen, boolean oauthSafe,
                                   Set<String> changed, Set<String> rules,
                                   Set<String> blockers) throws IOException {
        String before = Files.readString(pom, StandardCharsets.UTF_8);
        String after = before;
        if (oauthSafe && (authorizationServerSeen || resourceServerSeen)) {
            List<String> replacements = new ArrayList<>();
            if (authorizationServerSeen) {
                replacements.add("""
                        <dependency>
                          <groupId>org.springframework.boot</groupId>
                          <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
                        </dependency>""");
            }
            if (resourceServerSeen) {
                replacements.add("""
                        <dependency>
                          <groupId>org.springframework.boot</groupId>
                          <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
                        </dependency>""");
            }
            after = LEGACY_OAUTH_DEPENDENCY.matcher(after).replaceAll(
                    Matcher.quoteReplacement(String.join("\n", replacements)));
            if (!after.equals(before)) {
                if (authorizationServerSeen)
                    rules.add("LEGACY_OAUTH2_DEPENDENCY_TO_BOOT_AUTHORIZATION_SERVER_STARTER");
                if (resourceServerSeen)
                    rules.add("LEGACY_OAUTH2_DEPENDENCY_TO_BOOT_RESOURCE_SERVER_STARTER");
            }
        } else if (LEGACY_OAUTH_DEPENDENCY.matcher(before).find()) {
            blockers.add(relative(root, pom) + ": legacy OAuth2 dependency retained because source configuration was not safely rewritten");
        }

        Matcher shiro = SHIRO_DEPENDENCY.matcher(after);
        StringBuffer rewritten = new StringBuffer();
        boolean shiroChanged = false;
        while (shiro.find()) {
            String dependency = shiro.group();
            String replacement = "<dependency>\n"
                    + "  <groupId>org.apache.shiro</groupId>\n"
                    + "  <artifactId>shiro-spring-boot-web-starter</artifactId>\n"
                    + "  <version>" + SHIRO_VERSION + "</version>\n"
                    + "</dependency>";
            shiro.appendReplacement(rewritten, Matcher.quoteReplacement(replacement));
            shiroChanged |= !dependency.equals(replacement);
        }
        shiro.appendTail(rewritten);
        if (shiroChanged) {
            after = rewritten.toString();
            rules.add("SHIRO_3_0_1_BOOT3_JAKARTA_STARTER");
        }
        if (!after.equals(before)) {
            Files.writeString(pom, after, StandardCharsets.UTF_8);
            changed.add(relative(root, pom));
        }
    }

    private static boolean containsAny(String value, String... needles) {
        for (String needle : needles) if (value.contains(needle)) return true;
        return false;
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
