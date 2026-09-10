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

        String updatedBootstrap = Files.readString(bootstrapFile);
        assertTrue(updatedBootstrap.contains("spring.config.import=optional:configserver:"));
    }
}
