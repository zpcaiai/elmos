package io.elmos.worker.security;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringLegacySecurityModernizerTest {
    @TempDir Path root;

    @Test void migratesSimpleAuthorizationServerAndShiroJakartaBaseline() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependencies>
                  <dependency><groupId>org.springframework.security.oauth</groupId>
                    <artifactId>spring-security-oauth2</artifactId><version>2.5.2.RELEASE</version></dependency>
                  <dependency><groupId>org.apache.shiro</groupId>
                    <artifactId>shiro-spring</artifactId><version>1.13.0</version></dependency>
                </dependencies></project>
                """);
        Path oauth = root.resolve("LegacyAuthorizationServer.java");
        Files.writeString(oauth, """
                package com.acme;
                import org.springframework.security.oauth2.config.annotation.web.configuration.EnableAuthorizationServer;
                @EnableAuthorizationServer
                public class LegacyAuthorizationServer {}
                """);
        Path shiro = root.resolve("ShiroWeb.java");
        Files.writeString(shiro, """
                import org.apache.shiro.web.servlet.ShiroHttpServletRequest;
                import javax.servlet.Filter;
                class ShiroWeb { Filter filter; }
                """);

        var result = SpringLegacySecurityModernizer.modernize(root);

        assertTrue(result.modified());
        String pom = Files.readString(root.resolve("pom.xml"));
        assertTrue(pom.contains("spring-boot-starter-oauth2-authorization-server"));
        assertTrue(pom.contains("shiro-spring-boot-web-starter"));
        assertTrue(pom.contains("<version>3.0.1</version>"));
        String oauthSource = Files.readString(oauth);
        assertTrue(oauthSource.contains("AuthorizationServerSettings"));
        assertFalse(oauthSource.contains("EnableAuthorizationServer"));
        assertTrue(Files.readString(shiro).contains("import jakarta.servlet.Filter"));
        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("registered clients")));
    }

    @Test void convertsSimpleResourceServerAndFailsClosedForCustomOauthAndRealm() throws Exception {
        Path simple = root.resolve("ResourceSecurity.java");
        Files.writeString(simple, """
                import org.springframework.security.oauth2.config.annotation.web.configuration.EnableResourceServer;
                @EnableResourceServer public class ResourceSecurity {}
                """);
        Path custom = root.resolve("CustomAuthorizationServer.java");
        Files.writeString(custom, """
                import org.springframework.security.oauth2.config.annotation.web.configuration.EnableAuthorizationServer;
                @EnableAuthorizationServer class CustomAuthorizationServer {
                  void configure(ClientDetailsServiceConfigurer clients) {}
                }
                """);
        Path realm = root.resolve("BankRealm.java");
        Files.writeString(realm, """
                import org.apache.shiro.realm.AuthorizingRealm;
                class BankRealm extends AuthorizingRealm {}
                """);

        var result = SpringLegacySecurityModernizer.modernize(root);

        assertTrue(Files.readString(simple).contains("@EnableResourceServer"),
                "mixed/custom OAuth2 projects must be retained atomically");
        assertTrue(Files.readString(custom).contains("@EnableAuthorizationServer"));
        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("retained atomically")));
        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("Shiro realm")));
    }

    @Test void usesResourceServerStarterForAnIsolatedResourceServer() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependencies><dependency>
                  <groupId>org.springframework.security.oauth</groupId>
                  <artifactId>spring-security-oauth2</artifactId><version>2.5.2.RELEASE</version>
                </dependency></dependencies></project>
                """);
        Path resource = root.resolve("ResourceSecurity.java");
        Files.writeString(resource, """
                import org.springframework.security.oauth2.config.annotation.web.configuration.EnableResourceServer;
                @EnableResourceServer public class ResourceSecurity {}
                """);

        var result = SpringLegacySecurityModernizer.modernize(root);

        String pom = Files.readString(root.resolve("pom.xml"));
        assertTrue(pom.contains("spring-boot-starter-oauth2-resource-server"));
        assertFalse(pom.contains("spring-boot-starter-oauth2-authorization-server"));
        assertTrue(Files.readString(resource).contains("SecurityFilterChain"));
        assertTrue(result.rulesApplied().contains("LEGACY_OAUTH2_DEPENDENCY_TO_BOOT_RESOURCE_SERVER_STARTER"));
    }
}
