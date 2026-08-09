package io.elmos.workspaceservice;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;

import java.time.Clock;

@Configuration(proxyBeanMethods = false)
class WorkspaceSecurityConfiguration {
    @Bean
    UserDetailsService workspaceUserDetailsService() {
        // This service has no password-authenticated users. Declaring an empty
        // lookup prevents Boot from manufacturing and logging a development
        // password that could be mistaken for a supported production path.
        return username -> {
            throw new UsernameNotFoundException("interactive workspace login is disabled");
        };
    }

    @Bean
    SecurityFilterChain workspaceSecurity(
            HttpSecurity http,
            Clock clock,
            @Value("${elmos.workspace.service-auth.api-key:}") String apiKey,
            @Value("${elmos.workspace.service-auth.api-key-expires-at:}") String apiKeyExpiresAt,
            @Value("${elmos.workspace.service-auth.organization-id:}") String organizationId,
            @Value("${elmos.workspace.service-auth.actor-id:}") String actorId
    ) throws Exception {
        var credentialFilter = new WorkspaceServiceCredentialFilter(
                clock, apiKey, apiKeyExpiresAt, organizationId, actorId);
        return http
                .csrf(AbstractHttpConfigurer::disable)
                .cors(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .logout(AbstractHttpConfigurer::disable)
                .requestCache(cache -> cache.disable())
                .sessionManagement(session ->
                        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                "/actuator/health/**",
                                "/livez",
                                "/readyz")
                        .permitAll()
                        .requestMatchers(
                                "/internal/v1/spring-runtimes",
                                "/internal/v1/spring-verifications",
                                "/internal/v1/spring-transformations")
                        .permitAll()
                        .requestMatchers(
                                "/api/v1/workspaces",
                                "/api/v1/workspaces/**")
                        .hasAuthority(WorkspaceServiceCredentialFilter.AUTHORITY)
                        .anyRequest().denyAll())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((request, response, error) ->
                                WorkspaceServiceCredentialFilter.writeError(
                                        response,
                                        401,
                                        "WORKSPACE_SERVICE_AUTH_REQUIRED",
                                        "Workspace service authentication is required.",
                                        false))
                        .accessDeniedHandler((request, response, error) ->
                                WorkspaceServiceCredentialFilter.writeError(
                                        response,
                                        403,
                                        "WORKSPACE_SERVICE_AUTH_FORBIDDEN",
                                        "Workspace service authentication was rejected.",
                                        false)))
                .addFilterBefore(credentialFilter, AnonymousAuthenticationFilter.class)
                .build();
    }
}
