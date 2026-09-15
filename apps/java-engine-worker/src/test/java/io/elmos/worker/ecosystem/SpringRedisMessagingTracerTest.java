package io.elmos.worker.ecosystem;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringRedisMessagingTracerTest {

    @TempDir
    Path tempDir;

    @Test
    void testJedisToStringRedisTemplate() throws IOException {
        Path javaDir = Files.createDirectories(tempDir.resolve("src/main/java/com/example/cache"));
        Path javaFile = javaDir.resolve("TokenCacheService.java");
        Files.writeString(javaFile, """
                package com.example.cache;
                
                import org.springframework.beans.factory.annotation.Autowired;
                import org.springframework.stereotype.Service;
                import redis.clients.jedis.Jedis;
                import redis.clients.jedis.JedisPool;
                
                @Service
                public class TokenCacheService {
                    @Autowired
                    private JedisPool jedisPool;
                    
                    public void saveToken(String key, String token) {
                        Jedis jedis = jedisPool.getResource();
                        jedis.set(key, token);
                        jedis.close();
                    }
                    
                    public String getToken(String key) {
                        Jedis jedis = jedisPool.getResource();
                        return jedis.get(key);
                    }
                }
                """);

        Path pom = tempDir.resolve("pom.xml");
        Files.writeString(pom, """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>redis.clients</groupId>
                            <artifactId>jedis</artifactId>
                            <version>3.8.0</version>
                        </dependency>
                    </dependencies>
                </project>
                """);

        var result = SpringRedisMessagingTracer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("JAVA_JEDIS_TO_STRINGREDISTEMPLATE"));
        assertTrue(result.rulesApplied().contains("POM_JEDIS_TO_DATA_REDIS"));

        String updatedJava = Files.readString(javaFile);
        assertFalse(updatedJava.contains("JedisPool"));
        assertTrue(updatedJava.contains("StringRedisTemplate stringRedisTemplate;"));
        assertTrue(updatedJava.contains("stringRedisTemplate.opsForValue().set(key, token);"));
        assertTrue(updatedJava.contains("stringRedisTemplate.opsForValue().get(key)"));
        assertFalse(updatedJava.contains("jedis.close()"));

        String updatedPom = Files.readString(pom);
        assertFalse(updatedPom.contains("<artifactId>jedis</artifactId>"));
        assertTrue(updatedPom.contains("<artifactId>spring-boot-starter-data-redis</artifactId>"));
    }

    @Test
    void testKafkaObservationConfigurationGenerated() throws IOException {
        Path javaDir = Files.createDirectories(tempDir.resolve("src/main/java/com/example/mq"));
        Path javaFile = javaDir.resolve("OrderConsumer.java");
        Files.writeString(javaFile, """
                package com.example.mq;
                
                import org.springframework.kafka.annotation.KafkaListener;
                import org.springframework.stereotype.Component;
                
                @Component
                public class OrderConsumer {
                    @KafkaListener(topics = "orders")
                    public void process(String message) {}
                }
                """);

        Path pom = tempDir.resolve("pom.xml");
        Files.writeString(pom, """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>org.springframework.kafka</groupId>
                            <artifactId>spring-kafka</artifactId>
                        </dependency>
                    </dependencies>
                </project>
                """);

        var result = SpringRedisMessagingTracer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("KAFKA_OBSERVATION_CONFIG_GENERATED"));
        assertTrue(result.rulesApplied().contains("POM_MICROMETER_TRACING_BRIDGE_ADDED"));

        Path configPath = tempDir.resolve("src/main/java/io/elmos/generated/config/KafkaObservationConfiguration.java");
        assertTrue(Files.exists(configPath));
        String configCode = Files.readString(configPath);
        assertTrue(configCode.contains("setObservationEnabled(true)"));

        String updatedPom = Files.readString(pom);
        assertTrue(updatedPom.contains("micrometer-tracing-bridge-brave"));
    }
}
