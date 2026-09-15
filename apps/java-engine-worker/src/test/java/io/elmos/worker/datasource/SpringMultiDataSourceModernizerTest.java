package io.elmos.worker.datasource;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringMultiDataSourceModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void testShardingSpherePomAndConfigUpgrade() throws IOException {
        Path pom = tempDir.resolve("pom.xml");
        Files.writeString(pom, """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>org.apache.shardingsphere</groupId>
                            <artifactId>sharding-jdbc-spring-boot-starter</artifactId>
                            <version>4.1.1</version>
                        </dependency>
                    </dependencies>
                </project>
                """);

        Path resDir = Files.createDirectories(tempDir.resolve("src/main/resources"));
        Path appYml = resDir.resolve("application.yml");
        Files.writeString(appYml, """
                spring:
                  shardingsphere:
                    datasource:
                      names: ds0,ds1
                    sharding:
                      tables:
                        t_order:
                          actual-data-nodes: ds$->{0..1}.t_order_$->{0..1}
                """);

        var result = SpringMultiDataSourceModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("POM_SHARDINGSPHERE_4_TO_5"));
        assertTrue(result.rulesApplied().contains("CONFIG_SHARDINGSPHERE_YAML_RULES"));

        String updatedPom = Files.readString(pom);
        assertTrue(updatedPom.contains("<artifactId>shardingsphere-jdbc-core</artifactId>"));
        assertTrue(updatedPom.contains("<version>5.5.0</version>"));

        String updatedYml = Files.readString(appYml);
        assertTrue(updatedYml.contains("rules:\n      sharding:"));
    }

    @Test
    void testDynamicDataSourcePomUpgrade() throws IOException {
        Path pom = tempDir.resolve("pom.xml");
        Files.writeString(pom, """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>com.baomidou</groupId>
                            <artifactId>dynamic-datasource-spring-boot-starter</artifactId>
                            <version>3.5.2</version>
                        </dependency>
                    </dependencies>
                </project>
                """);

        var result = SpringMultiDataSourceModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("POM_DYNAMIC_DATASOURCE_UPGRADE"));

        String updatedPom = Files.readString(pom);
        assertTrue(updatedPom.contains("<version>4.3.1</version>"));
    }

    @Test
    void testRoutingDataSourceThreadLocalClearInjected() throws IOException {
        Path javaDir = Files.createDirectories(tempDir.resolve("src/main/java/com/example/db"));
        Path javaFile = javaDir.resolve("DynamicDataSourceContextHolder.java");
        Files.writeString(javaFile, """
                package com.example.db;
                
                public class DynamicDataSourceContextHolder {
                    private static final ThreadLocal<String> CONTEXT_HOLDER = new ThreadLocal<>();
                    
                    public static void setDataSourceKey(String key) {
                        CONTEXT_HOLDER.set(key);
                    }
                    
                    public static String getDataSourceKey() {
                        return CONTEXT_HOLDER.get();
                    }
                }
                """);

        var result = SpringMultiDataSourceModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("JAVA_ROUTING_THREADLOCAL_CLEAR_INJECTED"));

        String content = Files.readString(javaFile);
        assertTrue(content.contains("public static void clearDataSourceKey()"));
        assertTrue(content.contains("CONTEXT_HOLDER.remove();"));
    }
}
