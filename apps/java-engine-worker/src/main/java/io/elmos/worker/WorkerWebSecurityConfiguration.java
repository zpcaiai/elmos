package io.elmos.worker;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Declares the worker's HTTP boundary instead of inheriting Spring Boot's
 * generated development user and Basic-authentication login page.
 *
 * <p>The Spring-upgrade API is admitted to the servlet layer because
 * {@link SpringEngineRequestAuthenticationFilter} owns its BFF-to-worker HMAC
 * contract. Capability and health probes are read-only. Every unrelated route
 * remains denied until it gains its own explicit ingress contract.</p>
 */
@Configuration(proxyBeanMethods = false)
class WorkerWebSecurityConfiguration {

    @Bean
    SecurityFilterChain workerSecurityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.ignoringRequestMatchers("/engine/v1/spring-upgrades/**"))
                .requestCache(requestCache -> requestCache.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .logout(logout -> logout.disable())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                HttpMethod.GET,
                                "/actuator/health",
                                "/actuator/health/**",
                                "/actuator/info",
                                "/actuator/prometheus",
                                "/livez",
                                "/readyz",
                                "/engine/v1/capabilities",
                                "/engine/v1/spring-upgrades/capabilities"
                        ).permitAll()
                        // Authorization is performed by the HMAC filter. This
                        // chain must not demand a second, unrelated login.
                        .requestMatchers("/engine/v1/spring-upgrades/**").permitAll()
                        .requestMatchers("/error").permitAll()
                        .anyRequest().denyAll());
        return http.build();
    }
}
