package io.elmos.worker.ecosystem;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringPageHelperModernizerTest {

    @Test
    void testPageHelperStarterAndStandaloneUpgrade(@TempDir Path tempDir) throws IOException {
        String pomContent = """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>com.example</groupId>
                  <artifactId>demo-app</artifactId>
                  <version>1.0.0</version>
                  <dependencies>
                    <dependency>
                      <groupId>com.github.pagehelper</groupId>
                      <artifactId>pagehelper-spring-boot-starter</artifactId>
                      <version>1.2.13</version>
                    </dependency>
                  </dependencies>
                </project>
                """;
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, pomContent);

        String javaConfig = """
                package com.example.config;
                import com.github.pagehelper.PageHelper;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                @Configuration
                public class MybatisConfig {
                    @Bean
                    public PageHelper pageHelper() {
                        PageHelper pageHelper = new PageHelper();
                        return pageHelper;
                    }
                }
                """;
        Path javaDir = tempDir.resolve("src/main/java/com/example/config");
        Files.createDirectories(javaDir);
        Path javaFile = javaDir.resolve("MybatisConfig.java");
        Files.writeString(javaFile, javaConfig);

        var result = SpringPageHelperModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("PAGEHELPER_STARTER_BOOT3_JAKARTA_2_1_0"));
        assertTrue(result.rulesApplied().contains("PAGEHELPER_BEAN_TO_PAGE_INTERCEPTOR"));

        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("<version>2.1.0</version>"));
        assertFalse(updatedPom.contains("1.2.13"));

        String updatedJava = Files.readString(javaFile);
        assertTrue(updatedJava.contains("import com.github.pagehelper.PageInterceptor;"));
        assertTrue(updatedJava.contains("public PageInterceptor pageInterceptor()"));
        assertTrue(updatedJava.contains("PageInterceptor pageInterceptor = new PageInterceptor();"));
        assertFalse(updatedJava.contains("new PageHelper()"));
    }

    @Test
    void testStandalonePageHelperAndPropertiesUpgrade(@TempDir Path tempDir) throws IOException {
        String pomContent = """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <properties>
                    <pagehelper.version>5.1.11</pagehelper.version>
                  </properties>
                  <dependencies>
                    <dependency>
                      <groupId>com.github.pagehelper</groupId>
                      <artifactId>pagehelper</artifactId>
                      <version>5.1.11</version>
                    </dependency>
                  </dependencies>
                </project>
                """;
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, pomContent);

        var result = SpringPageHelperModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("PAGEHELPER_STANDALONE_BOOT3_6_1_0"));

        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("<pagehelper.version>6.1.0</pagehelper.version>"));
        assertTrue(updatedPom.contains("<version>6.1.0</version>"));
        assertFalse(updatedPom.contains("5.1.11"));
    }
}
