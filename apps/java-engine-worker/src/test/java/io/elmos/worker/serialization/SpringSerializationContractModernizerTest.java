package io.elmos.worker.serialization;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringSerializationContractModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesFastjsonAndGeneratesJacksonGlobalConfiguration() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>com.alibaba</groupId>
                      <artifactId>fastjson</artifactId>
                      <version>1.2.83</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path javaDir = tempDir.resolve("src/main/java/com/example/dto");
        Files.createDirectories(javaDir);
        Path dtoClass = javaDir.resolve("UserPayload.java");
        Files.writeString(dtoClass, """
                package com.example.dto;

                import com.alibaba.fastjson.JSON;
                import com.alibaba.fastjson.JSONObject;

                public class UserPayload {

                    public String serialize(Object obj) {
                        return JSON.toJSONString(obj);
                    }
                }
                """);

        Path appYml = tempDir.resolve("application.yml");
        Files.writeString(appYml, "server:\n  port: 8080\n");

        var result = SpringSerializationContractModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() > 0);

        // 1. Verify Java import rewritten to fastjson2
        String updatedJava = Files.readString(dtoClass);
        assertFalse(updatedJava.contains("com.alibaba.fastjson.JSON;"));
        assertTrue(updatedJava.contains("com.alibaba.fastjson2.JSON;"));

        // 2. Verify JacksonConfiguration generated with Long serializer and JavaTimeModule
        Path jacksonConfig = tempDir.resolve("src/main/java/io/elmos/generated/serialization/JacksonConfiguration.java");
        assertTrue(Files.exists(jacksonConfig));
        String jacksonContent = Files.readString(jacksonConfig);
        assertTrue(jacksonContent.contains("ToStringSerializer.instance"));
        assertTrue(jacksonContent.contains("JavaTimeModule"));
        assertTrue(jacksonContent.contains("yyyy-MM-dd HH:mm:ss"));

        // 3. Verify pom.xml fastjson eliminated and jackson-datatype-jsr310 injected
        String updatedPom = Files.readString(pomFile);
        assertFalse(updatedPom.contains("<artifactId>fastjson</artifactId>"));
        assertTrue(updatedPom.contains("jackson-datatype-jsr310"));

        // 4. Verify application.yml has date-format and timezone
        String updatedYml = Files.readString(appYml);
        assertTrue(updatedYml.contains("date-format: yyyy-MM-dd HH:mm:ss"));
        assertTrue(updatedYml.contains("time-zone: GMT+8"));
    }
}
