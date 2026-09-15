package io.elmos.worker.datasource;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringShardingSphereModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesShardingSphereDependencyInPom() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.apache.shardingsphere</groupId>
                      <artifactId>shardingsphere-jdbc-core-spring-boot-starter</artifactId>
                      <version>5.1.2</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        var result = SpringShardingSphereModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 1);

        String updatedPom = Files.readString(pomFile);
        assertFalse(updatedPom.contains("shardingsphere-jdbc-core-spring-boot-starter"));
        assertTrue(updatedPom.contains("shardingsphere-jdbc-core"));
        assertTrue(updatedPom.contains("5.5.0"));
    }

    @Test
    void modernizesJavaImportsAndTypeNames() throws Exception {
        Path javaFile = tempDir.resolve("src/main/java/com/example/OrderDao.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile, """
                package com.example;

                import org.apache.shardingsphere.shardingjdbc.jdbc.core.datasource.ShardingDataSource;

                public class OrderDao {
                    private ShardingDataSource shardingDataSource;
                }
                """);

        var result = SpringShardingSphereModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updatedJava = Files.readString(javaFile);
        assertFalse(updatedJava.contains("org.apache.shardingsphere.shardingjdbc.jdbc.core.datasource.ShardingDataSource"));
        assertTrue(updatedJava.contains("org.apache.shardingsphere.driver.jdbc.core.datasource.ShardingSphereDataSource"));
        assertTrue(updatedJava.contains("ShardingSphereDataSource shardingDataSource"));

        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/sharding/ShardingSphereDataSourceConfiguration.java");
        assertTrue(Files.isRegularFile(generatedConfig));
    }

    @Test
    void modernizesShardingSphereConfigYaml() throws Exception {
        Path yamlFile = tempDir.resolve("src/main/resources/application.yml");
        Files.createDirectories(yamlFile.getParent());
        Files.writeString(yamlFile, """
                spring:
                  shardingsphere:
                    datasource:
                      names: ds0,ds1
                    sharding:
                      tables:
                        t_order:
                          actual-data-nodes: ds$->{0..1}.t_order_$->{0..1}
                """);

        var result = SpringShardingSphereModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updatedYaml = Files.readString(yamlFile);
        assertFalse(updatedYaml.contains("datasource:\n      names:"));
        assertTrue(updatedYaml.contains("data-sources: ds0,ds1"));
    }
}
