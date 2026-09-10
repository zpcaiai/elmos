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
}
