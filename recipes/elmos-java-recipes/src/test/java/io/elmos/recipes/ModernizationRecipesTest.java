package io.elmos.recipes;

import io.elmos.recipes.cloud.*;
import io.elmos.recipes.jpa.*;
import io.elmos.recipes.security.*;
import org.junit.jupiter.api.Test;
import org.openrewrite.InMemoryExecutionContext;
import org.openrewrite.SourceFile;
import org.openrewrite.java.JavaParser;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ModernizationRecipesTest {

    @Test
    void testSpringSecurityFilterChainRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                public class SecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests()
                            .antMatchers("/public/**").permitAll()
                            .anyRequest().authenticated();
                    }
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityFilterChainRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("extends WebSecurityConfigurerAdapter"));
        assertTrue(res.contains("authorizeHttpRequests"));
        assertTrue(res.contains("requestMatchers"));
    }

    @Test
    void testSpringSecurityMethodSecurityRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

                @EnableGlobalMethodSecurity(prePostEnabled = true)
                public class MethodSecurityConfig {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityMethodSecurityRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("@EnableGlobalMethodSecurity"));
        assertTrue(res.contains("@EnableMethodSecurity"));
    }

    @Test
    void testSpringSecurityAuthenticationRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.security.config.annotation.authentication.builders.AuthenticationManagerBuilder;

                public class AuthConfig {
                    public void configure(AuthenticationManagerBuilder auth) throws Exception {
                    }
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityAuthenticationRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertTrue(res.contains("AuthenticationManager authenticationManager"));
    }

    @Test
    void testSpringSecurityOAuth2ResourceServerRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.security.oauth2.config.annotation.web.configuration.EnableResourceServer;

                @EnableResourceServer
                public class OAuth2Config {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityOAuth2ResourceServerRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("@EnableResourceServer"));
        assertTrue(res.contains("@Configuration"));
    }

    @Test
    void testSpringSecurityCsrfCookieRepositoryRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

                public class CsrfConfig {
                    CookieCsrfTokenRepository repo = new CookieCsrfTokenRepository();
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityCsrfCookieRepositoryRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertTrue(res.contains("withHttpOnlyFalse"));
    }

    @Test
    void testSpringSecurityCorsConfigurationRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.web.cors.CorsConfiguration;

                public class CorsConfig {
                    public void configure(CorsConfiguration cors) {
                        cors.addAllowedOrigin("*");
                    }
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityCorsConfigurationRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertTrue(res.contains("addAllowedOriginPattern"));
    }

    @Test
    void testSpringSecuritySessionManagementRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                public class SessionConfig {
                    public void configure(HttpSecurity http) throws Exception {
                        http.sessionManagement().maximumSessions(1);
                    }
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecuritySessionManagementRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertTrue(res.contains("sessionManagement"));
    }

    @Test
    void testSpringSecurityCustomFilterOrderRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import javax.servlet.Filter;

                public class FilterConfig {
                    public void configure(HttpSecurity http, Filter customFilter) throws Exception {
                        http.addFilterBefore(customFilter, null);
                    }
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringSecurityCustomFilterOrderRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertTrue(res.contains("addFilterBefore"));
    }

    @Test
    void testHibernate6TypeMappingRecipe() {
        String sourceText = """
                package com.example;
                import org.hibernate.annotations.Type;

                public class Entity {
                    @Type(type = "json")
                    private String details;
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new Hibernate6TypeMappingRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertTrue(res.contains("JdbcTypeCode(SqlTypes.JSON)"));
    }

    @Test
    void testHibernate6CriteriaModernizationRecipe() {
        String sourceText = """
                package com.example;
                import org.hibernate.Criteria;

                public class Dao {
                    void query(Criteria criteria) {
                    }
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new Hibernate6CriteriaModernizationRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("import org.hibernate.Criteria;"));
        assertTrue(res.contains("CriteriaQuery"));
    }

    @Test
    void testSpringDataJpaNamedQueryModernizationRecipe() {
        String sourceText = """
                package com.example;
                import javax.persistence.NamedQuery;

                @NamedQuery(name = "User.findByName", query = "SELECT u FROM User u WHERE u.name = ?1")
                public class UserEntity {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringDataJpaNamedQueryModernizationRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("javax.persistence.NamedQuery"));
        assertTrue(res.contains("jakarta.persistence.NamedQuery"));
    }

    @Test
    void testHibernate6DialectFunctionRecipe() {
        String sourceText = """
                package com.example;
                import org.hibernate.dialect.Dialect;

                public class CustomDialect extends Dialect {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new Hibernate6DialectFunctionRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("extends Dialect"));
        assertTrue(res.contains("FunctionContributor"));
    }

    @Test
    void testHibernate6EnversAuditRecipe() {
        String sourceText = """
                package com.example;
                import org.hibernate.envers.RevisionEntity;

                @RevisionEntity
                public class AuditRev {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new Hibernate6EnversAuditRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertTrue(res.contains("@RevisionEntity"));
    }

    @Test
    void testSpringCloudRibbonToLoadBalancerRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.cloud.netflix.ribbon.RibbonClient;

                @RibbonClient(name = "user-service")
                public class ClientConfig {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringCloudRibbonToLoadBalancerRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("@RibbonClient"));
        assertTrue(res.contains("@LoadBalancerClient"));
    }

    @Test
    void testSpringCloudHystrixToResilience4jRecipe() {
        String sourceText = """
                package com.example;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                public class Service {
                    @HystrixCommand(fallbackMethod = "fallback")
                    public String call() { return "ok"; }
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringCloudHystrixToResilience4jRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("@HystrixCommand"));
        assertTrue(res.contains("@CircuitBreaker"));
    }

    @Test
    void testSpringCloudZuulToGatewayRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.cloud.netflix.zuul.EnableZuulProxy;
                import com.netflix.zuul.ZuulFilter;

                @EnableZuulProxy
                public class GatewayApp extends ZuulFilter {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringCloudZuulToGatewayRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("@EnableZuulProxy"));
        assertTrue(res.contains("@Configuration"));
        assertFalse(res.contains("extends ZuulFilter"));
        assertTrue(res.contains("GlobalFilter"));
    }

    @Test
    void testSpringCloudOpenFeignModernizationRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.cloud.netflix.feign.FeignClient;

                @FeignClient(name = "order-svc")
                public interface OrderClient {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringCloudOpenFeignModernizationRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("org.springframework.cloud.netflix.feign.FeignClient"));
        assertTrue(res.contains("org.springframework.cloud.openfeign.FeignClient"));
    }

    @Test
    void testSpringCloudEurekaDiscoveryRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.cloud.netflix.eureka.EnableEurekaClient;

                @EnableEurekaClient
                public class EurekaApp {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringCloudEurekaDiscoveryRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("@EnableEurekaClient"));
        assertTrue(res.contains("@EnableDiscoveryClient"));
    }

    @Test
    void testSpringCloudDistributedTracingRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.cloud.sleuth.annotation.NewSpan;
                import org.springframework.cloud.sleuth.Tracer;

                public class TraceService {
                    private Tracer tracer;

                    @NewSpan("process-order")
                    public void process() {
                    }
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringCloudDistributedTracingRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertFalse(res.contains("org.springframework.cloud.sleuth.annotation.NewSpan"));
        assertTrue(res.contains("io.micrometer.tracing.annotation.NewSpan"));
    }

    @Test
    void testSpringCloudConfigBootstrapRecipe() {
        String sourceText = """
                package com.example;
                import org.springframework.cloud.config.server.EnableConfigServer;

                @EnableConfigServer
                public class ConfigApp {
                }
                """;
        SourceFile source = JavaParser.fromJavaVersion().build().parse(sourceText).findFirst().orElseThrow();
        SourceFile transformed = (SourceFile) new SpringCloudConfigBootstrapRecipe().getVisitor()
                .visit(source, new InMemoryExecutionContext());
        String res = transformed.printAll();

        assertTrue(res.contains("@EnableConfigServer"));
    }
}
