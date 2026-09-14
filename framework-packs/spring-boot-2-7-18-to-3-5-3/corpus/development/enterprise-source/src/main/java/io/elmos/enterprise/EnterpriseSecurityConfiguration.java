package io.elmos.enterprise;

import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
class EnterpriseSecurityConfiguration {
    @Bean
    SecurityFilterChain enterpriseSecurityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeRequests(authorize -> authorize
            .antMatchers("/actuator/health", "/actuator/health/**", "/error").permitAll()
            .antMatchers("/actuator/metrics", "/actuator/metrics/**").hasRole("ADMIN")
            .antMatchers(HttpMethod.GET, "/api/enterprise/orders/**").hasAnyRole("OPERATOR", "VIEWER")
            .antMatchers(HttpMethod.POST, "/api/enterprise/orders").hasRole("OPERATOR")
            .anyRequest().denyAll()
        ).csrf(csrf -> csrf.ignoringAntMatchers("/api/enterprise/orders"))
            .httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService enterpriseUsers(
            PasswordEncoder encoder,
            @Value("${enterprise.security.operator-password}") String operatorPassword,
            @Value("${enterprise.security.viewer-password}") String viewerPassword,
            @Value("${enterprise.security.admin-password}") String adminPassword) {
        return new InMemoryUserDetailsManager(
            User.withUsername("operator").password(encoder.encode(operatorPassword)).roles("OPERATOR").build(),
            User.withUsername("viewer").password(encoder.encode(viewerPassword)).roles("VIEWER").build(),
            User.withUsername("admin").password(encoder.encode(adminPassword)).roles("ADMIN").build());
    }
}
