package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringCloudMicroservicesModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesRibbonZuulHystrixAndBootstrap() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.cloud</groupId>
                      <artifactId>spring-cloud-starter-netflix-ribbon</artifactId>
                    </dependency>
                    <dependency>
                      <groupId>org.springframework.cloud</groupId>
                      <artifactId>spring-cloud-starter-netflix-zuul</artifactId>
                    </dependency>
                    <dependency>
                      <groupId>org.springframework.cloud</groupId>
                      <artifactId>spring-cloud-starter-netflix-hystrix</artifactId>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path javaFile = tempDir.resolve("ServiceApplication.java");
        Files.writeString(javaFile, """
                package com.example;

                import org.springframework.cloud.netflix.ribbon.RibbonClient;
                import org.springframework.cloud.netflix.zuul.EnableZuulProxy;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                @EnableZuulProxy
                @RibbonClient(name = "account-service")
                public class ServiceApplication {

                    @HystrixCommand(fallbackMethod = "fallback")
                    public String call() {
                        return "ok";
                    }

                    public String fallback() {
                        return "fallback";
                    }
                }
                """);

        Path bootstrapFile = tempDir.resolve("bootstrap.yml");
        Files.writeString(bootstrapFile, """
                spring:
                  cloud:
                    config:
                      uri: http://localhost:8888
                """);

        var result = SpringCloudMicroservicesModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() > 0);

        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("spring-cloud-starter-loadbalancer"));
        assertTrue(updatedPom.contains("spring-cloud-starter-gateway"));
        assertTrue(updatedPom.contains("resilience4j-spring-boot3"));

        String updatedJava = Files.readString(javaFile);
        assertFalse(updatedJava.contains("@EnableZuulProxy"));
        assertFalse(updatedJava.contains("@RibbonClient"));
        assertTrue(updatedJava.contains("@LoadBalancerClient"));
        assertFalse(updatedJava.contains("@HystrixCommand"));
        assertTrue(updatedJava.contains("@CircuitBreaker(name = \"defaultService\", fallbackMethod = \"fallback\")"));

        assertFalse(Files.exists(bootstrapFile), "bootstrap.yml should be deleted after migration to application.yml");
        Path appConfigFile = tempDir.resolve("application.yml");
        assertTrue(Files.exists(appConfigFile), "application.yml should be generated");
        String updatedConfig = Files.readString(appConfigFile);
        assertTrue(updatedConfig.contains("spring.config.import=optional:configserver:"));
    }

    @Test
    void testZuulFilterAndRibbonRuleModernization() throws Exception {
        Path filterFile = tempDir.resolve("CustomZuulFilter.java");
        Files.writeString(filterFile, """
                package com.example.filter;

                import com.netflix.zuul.ZuulFilter;
                import com.netflix.zuul.context.RequestContext;
                import com.netflix.zuul.exception.ZuulException;
                import com.netflix.loadbalancer.IRule;
                import com.netflix.loadbalancer.RoundRobinRule;

                public class CustomZuulFilter extends ZuulFilter {

                    @Override
                    public String filterType() {
                        return "pre";
                    }

                    @Override
                    public int filterOrder() {
                        return 1;
                    }

                    @Override
                    public boolean shouldFilter() {
                        return true;
                    }

                    @Override
                    public Object run() throws ZuulException {
                        return null;
                    }

                    public IRule customRule() {
                        return new RoundRobinRule();
                    }
                }
                """);

        var result = SpringCloudMicroservicesModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updated = Files.readString(filterFile);
        assertFalse(updated.contains("extends ZuulFilter"));
        assertTrue(updated.contains("implements GlobalFilter, Ordered"));
        assertTrue(updated.contains("public int getOrder()"));
        assertTrue(updated.contains("Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain)"));
        assertTrue(updated.contains("return chain.filter(exchange);"));
        assertTrue(updated.contains("ReactorLoadBalancer<ServiceInstance> customRule()"));
    }
}
