package io.elmos.worker.messaging;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringRedisDistributedLockModernizerTest {

    @Test
    void testRedisAndDistributedLockModernizationFlow(@TempDir Path tempDir) throws IOException {
        // 1. Setup pom.xml with legacy Redisson starter
        Path pomPath = tempDir.resolve("pom.xml");
        String pomContent = """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>org.redisson</groupId>
                            <artifactId>redisson-spring-boot-starter</artifactId>
                            <version>3.17.4</version>
                        </dependency>
                    </dependencies>
                </project>
                """;
        Files.writeString(pomPath, pomContent);

        // 2. Setup legacy Redis configuration with JdkSerializationRedisSerializer
        Path srcDir = tempDir.resolve("src/main/java/com/example/config");
        Files.createDirectories(srcDir);
        Path redisConfigPath = srcDir.resolve("OldRedisConfig.java");
        String legacyCode = """
                package com.example.config;

                import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
                import org.springframework.context.annotation.Bean;

                public class OldRedisConfig {
                    @Bean
                    public Object redisSerializer() {
                        return new JdkSerializationRedisSerializer();
                    }
                }
                """;
        Files.writeString(redisConfigPath, legacyCode);

        // 3. Setup application.yml
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path ymlPath = resDir.resolve("application.yml");
        Files.writeString(ymlPath, "spring:\n  application:\n    name: cache-service\n");

        // Execute modernization
        SpringRedisDistributedLockModernizer modernizer = new SpringRedisDistributedLockModernizer();
        SpringRedisDistributedLockModernizer.RedisModernizationResult result = modernizer.modernize(tempDir);

        assertTrue(result.modified(), "Project should be modified");
        assertTrue(result.changesCount() >= 4, "Should have applied at least 4 modifications");

        // Verify POM upgraded Redisson
        String updatedPom = Files.readString(pomPath);
        assertTrue(updatedPom.contains("<version>3.27.2</version>"), "Should upgrade Redisson to 3.27.2");

        // Verify JdkSerialization replaced
        String updatedJava = Files.readString(redisConfigPath);
        assertFalse(updatedJava.contains("JdkSerializationRedisSerializer"), "JdkSerialization should be eliminated");
        assertTrue(updatedJava.contains("GenericJackson2JsonRedisSerializer"), "Should replace with GenericJackson2JsonRedisSerializer");

        // Verify RedisSerializationConfiguration generated
        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/config/RedisSerializationConfiguration.java");
        assertTrue(Files.exists(generatedConfig), "RedisSerializationConfiguration should be generated");
        String configSource = Files.readString(generatedConfig);
        assertTrue(configSource.contains("BasicPolymorphicTypeValidator"), "Should use polymorphic type validator");

        // Verify DistributedLockTemplate generated
        Path generatedLock = tempDir.resolve("src/main/java/io/elmos/generated/lock/DistributedLockTemplate.java");
        assertTrue(Files.exists(generatedLock), "DistributedLockTemplate should be generated");
        String lockSource = Files.readString(generatedLock);
        assertTrue(lockSource.contains("lock.isHeldByCurrentThread()"), "Should verify lock ownership before unlock");

        // Verify application.yml has Lettuce pool settings
        String updatedYml = Files.readString(ymlPath);
        assertTrue(updatedYml.contains("lettuce:"), "Should inject Lettuce connection pool settings");
        assertTrue(updatedYml.contains("max-active: 64"), "Should set max-active connection limit");
    }
}
