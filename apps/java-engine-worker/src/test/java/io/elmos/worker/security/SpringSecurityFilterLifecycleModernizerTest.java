package io.elmos.worker.security;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringSecurityFilterLifecycleModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void detectsBeanFilterAddedToSecurityFilterChainAndGeneratesFilterRegistrationBean() throws IOException {
        Path src = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(src);

        // 1. Write custom filter with @Component
        Path filterFile = src.resolve("JwtAuthenticationFilter.java");
        Files.writeString(filterFile, """
                package com.example;

                import org.springframework.stereotype.Component;
                import org.springframework.web.filter.OncePerRequestFilter;
                import jakarta.servlet.FilterChain;
                import jakarta.servlet.http.HttpServletRequest;
                import jakarta.servlet.http.HttpServletResponse;

                @Component
                public class JwtAuthenticationFilter extends OncePerRequestFilter {
                    @Override
                    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) {}
                }
                """);

        // 2. Write SecurityConfig that adds JwtAuthenticationFilter to HttpSecurity
        Path configFile = src.resolve("SecurityConfig.java");
        Files.writeString(configFile, """
                package com.example;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;
                import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

                @Configuration
                public class SecurityConfig {

                    private final JwtAuthenticationFilter jwtAuthenticationFilter;

                    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter) {
                        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
                    }

                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);
                        return http.build();
                    }
                }
                """);

        var result = SpringSecurityFilterLifecycleModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertEquals(1, result.changesCount());
        assertTrue(result.disabledFilters().contains("JwtAuthenticationFilter"));

        String updatedConfig = Files.readString(configFile);
        assertTrue(updatedConfig.contains("FilterRegistrationBean<JwtAuthenticationFilter>"));
        assertTrue(updatedConfig.contains("registration.setEnabled(false)"));
        assertTrue(updatedConfig.contains("import org.springframework.boot.web.servlet.FilterRegistrationBean;"));
    }

    @Test
    void skipsWhenFilterRegistrationBeanAlreadyExists() throws IOException {
        Path src = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(src);

        Path configFile = src.resolve("SecurityConfig.java");
        Files.writeString(configFile, """
                package com.example;

                import org.springframework.boot.web.servlet.FilterRegistrationBean;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                @Configuration
                public class SecurityConfig {

                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http, JwtAuthenticationFilter jwtFilter) throws Exception {
                        http.addFilterBefore(jwtFilter, null);
                        return http.build();
                    }

                    @Bean
                    public FilterRegistrationBean<JwtAuthenticationFilter> jwtFilterRegistration(JwtAuthenticationFilter filter) {
                        FilterRegistrationBean<JwtAuthenticationFilter> reg = new FilterRegistrationBean<>(filter);
                        reg.setEnabled(false);
                        return reg;
                    }
                }
                """);

        var result = SpringSecurityFilterLifecycleModernizer.modernize(tempDir);
        assertFalse(result.modified());
        assertEquals(0, result.changesCount());
    }

    @Test
    void modernizeContentInPlace() {
        String original = """
                package com.example;

                import org.springframework.context.annotation.Configuration;

                @Configuration
                public class SecurityConfig {
                }
                """;

        String updated = SpringSecurityFilterLifecycleModernizer.modernizeContent(original, "CustomTokenFilter");
        assertTrue(updated.contains("FilterRegistrationBean<CustomTokenFilter>"));
        assertTrue(updated.contains("registration.setEnabled(false)"));
        assertTrue(updated.contains("import org.springframework.boot.web.servlet.FilterRegistrationBean;"));

        // Idempotency: second run shouldn't add duplicate bean
        String secondRun = SpringSecurityFilterLifecycleModernizer.modernizeContent(updated, "CustomTokenFilter");
        assertEquals(updated, secondRun);
    }
}
