package io.elmos.worker.web;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringWebLegacyPackagingModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void testWarToJarAndCommonsMultipartMigration() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <packaging>war</packaging>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.boot</groupId>
                      <artifactId>spring-boot-starter-tomcat</artifactId>
                      <scope>provided</scope>
                    </dependency>
                    <dependency>
                      <groupId>commons-fileupload</groupId>
                      <artifactId>commons-fileupload</artifactId>
                      <version>1.4</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path webConfig = tempDir.resolve("WebMvcConfig.java");
        Files.writeString(webConfig, """
                package com.example;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.web.multipart.commons.CommonsMultipartResolver;

                @Configuration
                public class WebMvcConfig {

                    @Bean
                    public CommonsMultipartResolver multipartResolver() {
                        return new CommonsMultipartResolver();
                    }
                }
                """);

        Path servletInitializer = tempDir.resolve("MyApplication.java");
        Files.writeString(servletInitializer, """
                package com.example;

                import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

                public class MyApplication extends SpringBootServletInitializer {
                }
                """);

        var result = SpringWebLegacyPackagingModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 4);

        // Verify pom.xml
        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("<packaging>jar</packaging>"));
        assertFalse(updatedPom.contains("<packaging>war</packaging>"));
        assertFalse(updatedPom.contains("<scope>provided</scope>"));
        assertFalse(updatedPom.contains("commons-fileupload"));

        // Verify CommonsMultipartResolver replaced
        String updatedConfig = Files.readString(webConfig);
        assertTrue(updatedConfig.contains("StandardServletMultipartResolver"));
        assertFalse(updatedConfig.contains("CommonsMultipartResolver"));

        // Verify standalone main method injected
        String updatedApp = Files.readString(servletInitializer);
        assertTrue(updatedApp.contains("public static void main(String[] args)"));
        assertTrue(updatedApp.contains("SpringApplication.run(MyApplication.class, args);"));
    }
}
