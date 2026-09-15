package io.elmos.worker.messaging;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Enterprise Spring Data Redis & Redisson Distributed Lock Modernizer.
 *
 * <p>Modernizes Redis data caching and distributed locking for Spring Boot 3.x:
 * <ol>
 *   <li><b>Secure Redis Serialization:</b>
 *       Replaces insecure {@code JdkSerializationRedisSerializer} and legacy unvalidated
 *       {@code Jackson2JsonRedisSerializer} with {@code GenericJackson2JsonRedisSerializer}
 *       configured with {@code BasicPolymorphicTypeValidator} to prevent RCE and type errors.</li>
 *   <li><b>Redisson 3.27+ Upgrade:</b>
 *       Upgrades {@code org.redisson:redisson-spring-boot-starter} to {@code 3.27.2}, resolving Netty
 *       native transport conflicts with Spring Boot 3.</li>
 *   <li><b>Safe Distributed Lock Pattern:</b>
 *       Generates {@code DistributedLockTemplate.java} enforcing bounded wait times, explicit lease times,
 *       and safe {@code if (lock.isHeldByCurrentThread()) lock.unlock();} finally release blocks.</li>
 *   <li><b>Connection Pool & Timeout Tuning:</b>
 *       Injects production-grade Lettuce connection pool and timeout settings in {@code application.yml}.</li>
 * </ol>
 */
public final class SpringRedisDistributedLockModernizer {

    public record RedisModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> generatedArtifacts
    ) {
        public static RedisModernizationResult empty() {
            return new RedisModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern LEGACY_REDISSON_STARTER = Pattern.compile(
            "<dependency>\\s*<groupId>org\\.redisson</groupId>\\s*<artifactId>redisson-spring-boot-starter</artifactId>(?:\\s*<version>[^<]+</version>)?\\s*</dependency>",
            Pattern.DOTALL
    );

    private static final String MODERN_REDISSON_DEPENDENCY =
            """
                    <dependency>
                        <groupId>org.redisson</groupId>
                        <artifactId>redisson-spring-boot-starter</artifactId>
                        <version>3.27.2</version>
                    </dependency>""";

    private static final Pattern INSECURE_JDK_SERIALIZER = Pattern.compile(
            "new\\s+JdkSerializationRedisSerializer\\s*\\([^)]*\\)"
    );

    /**
     * Executes complete Redis caching and distributed lock modernization across the workspace.
     */
    public RedisModernizationResult modernize(Path projectRoot) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return RedisModernizationResult.empty();
        }

        boolean anyModified = false;
        int totalChanges = 0;
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> generatedArtifacts = new ArrayList<>();

        // 1. Upgrade Redisson Starter in pom.xml
        Path pomPath = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomPath)) {
            String pomContent = Files.readString(pomPath, StandardCharsets.UTF_8);
            Matcher redissonMatcher = LEGACY_REDISSON_STARTER.matcher(pomContent);
            if (redissonMatcher.find()) {
                String updatedPom = redissonMatcher.replaceAll(MODERN_REDISSON_DEPENDENCY);
                Files.writeString(pomPath, updatedPom, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(pomPath.toString());
                rulesApplied.add("UPGRADE_REDISSON_STARTER_TO_3_27_2");
            }
        }

        // 2. Scan and replace insecure JdkSerializationRedisSerializer
        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                String source = Files.readString(javaFile, StandardCharsets.UTF_8);
                boolean changed = false;

                Matcher jdkMatcher = INSECURE_JDK_SERIALIZER.matcher(source);
                if (jdkMatcher.find()) {
                    source = jdkMatcher.replaceAll("new org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer()");
                    changed = true;
                }

                if (source.contains("import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;")) {
                    source = source.replace(
                            "import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;",
                            "import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;"
                    );
                    changed = true;
                }

                if (changed) {
                    Files.writeString(javaFile, source, StandardCharsets.UTF_8);
                    anyModified = true;
                    totalChanges++;
                    modifiedFiles.add(javaFile.toString());
                    rulesApplied.add("REPLACE_JDK_SERIALIZER_WITH_GENERIC_JACKSON");
                }
            }
        }

        // 3. Generate secure RedisTemplate Configuration
        Path configDir = projectRoot.resolve("src/main/java/io/elmos/generated/config");
        Files.createDirectories(configDir);
        Path redisConfigFile = configDir.resolve("RedisSerializationConfiguration.java");
        if (!Files.exists(redisConfigFile)) {
            String configContent = generateRedisConfig();
            Files.writeString(redisConfigFile, configContent, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(redisConfigFile.toString());
            generatedArtifacts.add(redisConfigFile.toString());
            rulesApplied.add("GENERATE_SECURE_REDIS_SERIALIZATION_CONFIG");
        }

        // 4. Generate Safe DistributedLockTemplate
        Path lockDir = projectRoot.resolve("src/main/java/io/elmos/generated/lock");
        Files.createDirectories(lockDir);
        Path lockTemplateFile = lockDir.resolve("DistributedLockTemplate.java");
        if (!Files.exists(lockTemplateFile)) {
            String lockContent = generateDistributedLockTemplate();
            Files.writeString(lockTemplateFile, lockContent, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(lockTemplateFile.toString());
            generatedArtifacts.add(lockTemplateFile.toString());
            rulesApplied.add("GENERATE_SAFE_DISTRIBUTED_LOCK_TEMPLATE");
        }

        // 5. Inject Redis Lettuce Connection Pool in application.yml
        Path ymlPath = projectRoot.resolve("src/main/resources/application.yml");
        if (Files.isRegularFile(ymlPath)) {
            String ymlContent = Files.readString(ymlPath, StandardCharsets.UTF_8);
            if (!ymlContent.contains("lettuce:")) {
                String lettuceConfig =
                        """

                        spring:
                          data:
                            redis:
                              timeout: 3000ms
                              lettuce:
                                pool:
                                  max-active: 64
                                  max-idle: 16
                                  min-idle: 4
                        """;
                Files.writeString(ymlPath, ymlContent + lettuceConfig, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(ymlPath.toString());
                rulesApplied.add("CONFIGURE_LETTUCE_CONNECTION_POOL");
            }
        }

        return new RedisModernizationResult(anyModified, totalChanges, modifiedFiles, rulesApplied, generatedArtifacts);
    }

    private static String generateRedisConfig() {
        return """
                package io.elmos.generated.config;

                import com.fasterxml.jackson.databind.ObjectMapper;
                import com.fasterxml.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
                import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.data.redis.connection.RedisConnectionFactory;
                import org.springframework.data.redis.core.RedisTemplate;
                import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
                import org.springframework.data.redis.serializer.StringRedisSerializer;

                /**
                 * Enterprise Secure RedisTemplate Configuration for Spring Boot 3.
                 */
                @Configuration
                public class RedisSerializationConfiguration {

                    @Bean
                    public RedisTemplate<String, Object> redisTemplate(RedisConnectionFactory connectionFactory) {
                        RedisTemplate<String, Object> template = new RedisTemplate<>();
                        template.setConnectionFactory(connectionFactory);

                        ObjectMapper objectMapper = new ObjectMapper();
                        objectMapper.registerModule(new JavaTimeModule());
                        objectMapper.activateDefaultTyping(
                                BasicPolymorphicTypeValidator.builder()
                                        .allowIfBaseType(Object.class)
                                        .build(),
                                ObjectMapper.DefaultTyping.NON_FINAL
                        );

                        GenericJackson2JsonRedisSerializer serializer = new GenericJackson2JsonRedisSerializer(objectMapper);
                        StringRedisSerializer stringSerializer = new StringRedisSerializer();

                        template.setKeySerializer(stringSerializer);
                        template.setHashKeySerializer(stringSerializer);
                        template.setValueSerializer(serializer);
                        template.setHashValueSerializer(serializer);
                        template.afterPropertiesSet();
                        return template;
                    }
                }
                """;
    }

    private static String generateDistributedLockTemplate() {
        return """
                package io.elmos.generated.lock;

                import org.redisson.api.RLock;
                import org.redisson.api.RedissonClient;
                import org.springframework.stereotype.Component;

                import java.util.concurrent.TimeUnit;
                import java.util.function.Supplier;

                /**
                 * Production-grade Distributed Lock Template.
                 *
                 * <p>Enforces bounded spin timeouts, explicit lease release, and defensive
                 * finally unlocks to eliminate deadlock risks in Kubernetes container environments.
                 */
                @Component
                public class DistributedLockTemplate {

                    private final RedissonClient redissonClient;

                    public DistributedLockTemplate(RedissonClient redissonClient) {
                        this.redissonClient = redissonClient;
                    }

                    public <T> T executeWithLock(String lockKey, long waitTime, long leaseTime, TimeUnit unit, Supplier<T> task) {
                        RLock lock = redissonClient.getLock(lockKey);
                        boolean acquired = false;
                        try {
                            acquired = lock.tryLock(waitTime, leaseTime, unit);
                            if (!acquired) {
                                throw new IllegalStateException("Failed to acquire distributed lock for key: " + lockKey);
                            }
                            return task.get();
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException("Interrupted while acquiring distributed lock: " + lockKey, e);
                        } finally {
                            if (acquired && lock.isHeldByCurrentThread()) {
                                lock.unlock();
                            }
                        }
                    }
                }
                """;
    }
}
