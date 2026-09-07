package io.elmos.commercialapi;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

import java.util.List;

@Configuration
@EnableMethodSecurity
public class CommercialSecurityConfiguration {
    @Bean
    JwtDecoder commercialJwtDecoder(
            @Value("${elmos.identity.issuer-uri:}") String issuer,
            @Value("${elmos.identity.jwk-set-uri:}") String jwkSetUri,
            @Value("${elmos.identity.audience:}") String audience
    ) {
        if (issuer.isBlank() || jwkSetUri.isBlank() || audience.isBlank()) {
            return token -> {
                throw new BadJwtException("ELMOS_OIDC_NOT_CONFIGURED");
            };
        }
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
        OAuth2TokenValidator<Jwt> issuerValidator = JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token", "Required audience is missing", null));
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                List.of(issuerValidator, audienceValidator)));
        return decoder;
    }

    @Bean
    SecurityFilterChain commercialSecurity(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                "/actuator/health/**",
                                "/livez",
                                "/readyz",
                                "/commercial/v1/pricing/catalog",
                                "/commercial/v1/capabilities",
                                // 支付回调路径必须放行：提供方不会携带我们的令牌，
                                // 安全性完全由各自的验签保证（RSA2 / APIv3 平台证书）。
                                //
                                // 逐条列出精确路径，**不要**写成 /callbacks/**：
                                // 通配会把将来任何新增的 callbacks 子路径一并放行，
                                // 而新增路径未必带验签。放行范围必须与验签实现一一对应。
                                "/commercial/v1/billing/webhooks/stripe",
                                "/commercial/v1/billing/callbacks/alipay",
                                "/commercial/v1/billing/callbacks/wechat")
                        .permitAll()
                        // 注意顺序：上面的精确路径先匹配先生效。
                        // 这条规则覆盖 /commercial/v1/billing/** 全部其余路径，
                        // 回调路径若不在上面列出，会落到这里变成 401。
                        .requestMatchers("/commercial/v1/billing/**").authenticated()
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resourceServer -> resourceServer.jwt(Customizer.withDefaults()))
                .build();
    }
}
