package io.elmos.worker.transaction;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringSeataDistributedTxModernizerTest {

    @Test
    void testSeataModernizationCompleteFlow(@TempDir Path tempDir) throws IOException {
        // 1. Setup legacy pom.xml
        Path pomPath = tempDir.resolve("pom.xml");
        String legacyPom = """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>com.alibaba.cloud</groupId>
                            <artifactId>spring-cloud-starter-alibaba-seata</artifactId>
                            <version>2.2.8.RELEASE</version>
                        </dependency>
                    </dependencies>
                </project>
                """;
        Files.writeString(pomPath, legacyPom);

        // 2. Setup legacy DataSource configuration with manual DataSourceProxy bean
        Path javaDir = tempDir.resolve("src/main/java/com/example/config");
        Files.createDirectories(javaDir);
        Path dsConfigPath = javaDir.resolve("DataSourceConfiguration.java");
        String legacyJava = """
                package com.example.config;

                import io.seata.rm.datasource.DataSourceProxy;
                import io.seata.spring.annotation.GlobalTransactional;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.context.annotation.Primary;
                import javax.sql.DataSource;

                @Configuration
                public class DataSourceConfiguration {

                    @Bean
                    @Primary
                    public DataSourceProxy dataSourceProxy(DataSource dataSource) {
                        return new DataSourceProxy(dataSource);
                    }

                    @GlobalTransactional(rollbackFor = Exception.class)
                    public void placeOrder() {
                    }
                }
                """;
        Files.writeString(dsConfigPath, legacyJava);

        // 3. Setup application.yml
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path ymlPath = resDir.resolve("application.yml");
        Files.writeString(ymlPath, "spring:\n  application:\n    name: order-service\n");

        // Execute modernization
        SpringSeataDistributedTxModernizer modernizer = new SpringSeataDistributedTxModernizer();
        SpringSeataDistributedTxModernizer.SeataModernizationResult result = modernizer.modernize(tempDir);

        assertTrue(result.modified(), "Project should have been modified");
        assertTrue(result.changesCount() >= 4, "Should have applied at least 4 modifications");

        // Verify POM upgraded
        String updatedPom = Files.readString(pomPath);
        assertTrue(updatedPom.contains("org.apache.seata"), "Should upgrade to org.apache.seata");
        assertFalse(updatedPom.contains("com.alibaba.cloud"), "Legacy groupId should be eliminated");

        // Verify DataSourceProxy removed & imports updated
        String updatedJava = Files.readString(dsConfigPath);
        assertFalse(updatedJava.contains("new DataSourceProxy"), "Manual DataSourceProxy should be eliminated");
        assertTrue(updatedJava.contains("org.apache.seata.spring.annotation.GlobalTransactional"), "GlobalTransactional should use Apache package");

        // Verify application.yml has Seata AutoDataSourceProxy config
        String updatedYml = Files.readString(ymlPath);
        assertTrue(updatedYml.contains("enable-auto-data-source-proxy: true"), "Auto proxy config should be injected");
        assertTrue(updatedYml.contains("tx-service-group: default_tx_group"), "Tx service group should be set");

        // Verify SeataXidTaskDecorator generated
        Path generatedDecorator = tempDir.resolve("src/main/java/io/elmos/generated/config/SeataXidTaskDecorator.java");
        assertTrue(Files.exists(generatedDecorator), "SeataXidTaskDecorator should be generated");
        String decoratorSource = Files.readString(generatedDecorator);
        assertTrue(decoratorSource.contains("RootContext.bind(xid)"), "Should bind XID across threads");
        assertTrue(decoratorSource.contains("RootContext.unbind()"), "Should unbind XID safely");
    }
}
