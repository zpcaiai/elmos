package io.elmos.worker.web;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringFileUploadSecurityModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesCommonsMultipartResolverAndFileImports() throws Exception {
        Path javaFile = tempDir.resolve("src/main/java/com/example/FileUploadConfig.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile, """
                package com.example;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.web.multipart.commons.CommonsMultipartFile;
                import org.springframework.web.multipart.commons.CommonsMultipartResolver;

                @Configuration
                public class FileUploadConfig {

                    @Bean(name = "multipartResolver")
                    public CommonsMultipartResolver multipartResolver() {
                        CommonsMultipartResolver resolver = new CommonsMultipartResolver();
                        resolver.setDefaultEncoding("utf-8");
                        return new CommonsMultipartResolver();
                    }

                    public void handle(CommonsMultipartFile file) {
                    }
                }
                """);

        var result = SpringFileUploadSecurityModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 1);

        String updated = Files.readString(javaFile);
        assertFalse(updated.contains("org.springframework.web.multipart.commons.CommonsMultipartResolver"));
        assertFalse(updated.contains("CommonsMultipartFile"));
        assertTrue(updated.contains("StandardServletMultipartResolver"));
        assertTrue(updated.contains("MultipartFile"));

        Path helperFile = tempDir.resolve("src/main/java/io/elmos/generated/upload/SecureFileUploadHelper.java");
        assertTrue(Files.isRegularFile(helperFile));
    }

    @Test
    void modernizesLegacyMultipartPropertiesInYaml() throws Exception {
        Path ymlFile = tempDir.resolve("src/main/resources/application.yml");
        Files.createDirectories(ymlFile.getParent());
        Files.writeString(ymlFile, """
                spring:
                  http:
                    multipart:
                      max-file-size: 10MB
                      max-request-size: 50MB
                """);

        var result = SpringFileUploadSecurityModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updated = Files.readString(ymlFile);
        assertFalse(updated.contains("http:"));
        assertTrue(updated.contains("servlet:"));
        assertTrue(updated.contains("multipart:"));
    }
}
