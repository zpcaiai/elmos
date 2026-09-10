package io.elmos.worker.security;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringSecurityFilterChainModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesWebSecurityConfigurerAdapterAndLambdaDsl() throws Exception {
        Path javaFile = tempDir.resolve("SecurityConfig.java");
        Files.writeString(javaFile, """
                package com.example.security;

                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.config.annotation.web.builders.WebSecurity;
                import org.springframework.security.config.annotation.authentication.builders.AuthenticationManagerBuilder;
                import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

                @EnableGlobalMethodSecurity(prePostEnabled = true)
                public class SecurityConfig extends WebSecurityConfigurerAdapter {

                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.csrf().disable()
                            .cors().and()
                            .headers().frameOptions().disable().and()
                            .authorizeRequests()
                            .antMatchers("/public/**").permitAll()
                            .antMatchers("/admin/**").hasRole("ADMIN")
                            .anyRequest().authenticated()
                            .and()
                            .formLogin().disable();
                    }

                    @Override
                    public void configure(WebSecurity web) {
                        web.ignoring().antMatchers("/css/**");
                    }

                    @Override
                    protected void configure(AuthenticationManagerBuilder auth) throws Exception {
                        auth.inMemoryAuthentication();
                    }
                }
                """);

        var result = SpringSecurityFilterChainModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() > 0);

        String updated = Files.readString(javaFile);
        assertFalse(updated.contains("extends WebSecurityConfigurerAdapter"));
        assertFalse(updated.contains("@EnableGlobalMethodSecurity"));
        assertTrue(updated.contains("@EnableMethodSecurity"));
        assertTrue(updated.contains("@Bean\n    public SecurityFilterChain securityFilterChain"));
        assertTrue(updated.contains("authorizeHttpRequests()"));
        assertTrue(updated.contains("requestMatchers(\"/public/**\")"));
        assertTrue(updated.contains(".csrf(csrf -> csrf.disable())"));
        assertTrue(updated.contains("public WebSecurityCustomizer webSecurityCustomizer()"));
        assertTrue(updated.contains("public AuthenticationManager authenticationManager"));
    }

    @Test
    void modernizesAdvancedSecurityPatterns() throws Exception {
        Path javaFile = tempDir.resolve("AdvancedSecurityConfig.java");
        Files.writeString(javaFile, """
                package com.example.security;

                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                public class AdvancedSecurityConfig extends WebSecurityConfigurerAdapter {

                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests()
                            .mvcMatchers("/api/v1/**").authenticated()
                            .and()
                            .httpBasic()
                            .and()
                            .anonymous().disable()
                            .and()
                            .logout().disable();
                    }
                }
                """);

        var result = SpringSecurityFilterChainModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updated = Files.readString(javaFile);
        assertFalse(updated.contains("extends WebSecurityConfigurerAdapter"));
        assertTrue(updated.contains("requestMatchers(\"/api/v1/**\")"));
        assertTrue(updated.contains(".httpBasic(Customizer.withDefaults())"));
        assertTrue(updated.contains(".anonymous(anon -> anon.disable())"));
        assertTrue(updated.contains(".logout(logout -> logout.disable())"));
        assertTrue(updated.contains("return http.build();"));
    }

    @Test
    void modernizesOAuth2AndExceptionHandling() throws Exception {
        Path javaFile = tempDir.resolve("OAuth2SecurityConfig.java");
        Files.writeString(javaFile, """
                package com.example.security;

                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                public class OAuth2SecurityConfig extends WebSecurityConfigurerAdapter {

                    @Override
                    public void configure(HttpSecurity http) throws Exception {
                        http.oauth2ResourceServer().jwt()
                            .and()
                            .exceptionHandling().authenticationEntryPoint(null);
                    }
                }
                """);

        var result = SpringSecurityFilterChainModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updated = Files.readString(javaFile);
        assertFalse(updated.contains("extends WebSecurityConfigurerAdapter"));
        assertTrue(updated.contains("@Bean\n    public SecurityFilterChain securityFilterChain"));
        assertTrue(updated.contains(".oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))"));
        assertTrue(updated.contains(".exceptionHandling(ex -> ex.authenticationEntryPoint(null))"));
        assertTrue(updated.contains("return http.build();"));
    }
}
