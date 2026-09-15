package io.elmos.worker.reactive;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringReactiveBlockingCallAuditorTest {

    @Test
    void testReactiveBlockingCallAuditAndRemediation(@TempDir Path tempDir) throws IOException {
        // 1. Setup pom.xml with webflux
        Path pomPath = tempDir.resolve("pom.xml");
        String pomContent = """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-starter-webflux</artifactId>
                        </dependency>
                    </dependencies>
                </project>
                """;
        Files.writeString(pomPath, pomContent);

        // 2. Setup reactive service with blocking calls
        Path srcDir = tempDir.resolve("src/main/java/com/example/service");
        Files.createDirectories(srcDir);
        Path servicePath = srcDir.resolve("ReactiveOrderService.java");
        String reactiveCode = """
                package com.example.service;

                import reactor.core.publisher.Mono;
                import org.springframework.web.client.RestTemplate;
                import org.springframework.jdbc.core.JdbcTemplate;

                public class ReactiveOrderService {

                    private RestTemplate restTemplate;
                    private JdbcTemplate jdbcTemplate;

                    public Mono<String> getOrderDetails(String orderId) {
                        return restTemplate.getForObject("https://api.example.com/orders/" + orderId, String.class);
                    }

                    public Mono<Integer> queryStock(String itemId) {
                        return jdbcTemplate.queryForObject("SELECT stock FROM inventory WHERE item_id = ?", Integer.class, itemId);
                    }

                    public void badBlockingMethod() {
                        Mono.just("data").block();
                    }
                }
                """;
        Files.writeString(servicePath, reactiveCode);

        // Execute audit and remediation
        SpringReactiveBlockingCallAuditor auditor = new SpringReactiveBlockingCallAuditor();
        SpringReactiveBlockingCallAuditor.ReactiveAuditResult result = auditor.auditAndRemediate(tempDir);

        assertTrue(result.modified(), "Should have modified files");
        assertTrue(result.findings().size() >= 3, "Should detect at least 3 blocking findings");

        // Verify findings
        boolean foundBlock = result.findings().stream()
                .anyMatch(f -> f.type() == SpringReactiveBlockingCallAuditor.BlockingType.EXPLICIT_MONO_FLUX_BLOCK);
        boolean foundRest = result.findings().stream()
                .anyMatch(f -> f.type() == SpringReactiveBlockingCallAuditor.BlockingType.REST_TEMPLATE_CALL);
        boolean foundJdbc = result.findings().stream()
                .anyMatch(f -> f.type() == SpringReactiveBlockingCallAuditor.BlockingType.JDBC_BLOCKING_CALL);

        assertTrue(foundBlock, "Should flag Mono.block()");
        assertTrue(foundRest, "Should flag RestTemplate call");
        assertTrue(foundJdbc, "Should flag JdbcTemplate query");

        // Verify remediation offloading
        String updatedCode = Files.readString(servicePath);
        assertTrue(updatedCode.contains("Schedulers.boundedElastic()"), "Should offload blocking call to boundedElastic scheduler");

        // Verify pom.xml injected with blockhound
        String updatedPom = Files.readString(pomPath);
        assertTrue(updatedPom.contains("blockhound"), "Should inject BlockHound test dependency");

        // Verify BlockHound customizer generated
        Path customizerPath = tempDir.resolve("src/test/java/io/elmos/generated/test/BlockHoundIntegrationTestCustomizer.java");
        assertTrue(Files.exists(customizerPath), "BlockHoundIntegrationTestCustomizer should be generated");
    }
}
