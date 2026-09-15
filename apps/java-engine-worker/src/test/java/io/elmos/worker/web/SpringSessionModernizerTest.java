package io.elmos.worker.web;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringSessionModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesJavaxCookieAndHttpSessionToJakarta() throws Exception {
        Path javaFile = tempDir.resolve("src/main/java/com/example/AuthFilter.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile, """
                package com.example;

                import javax.servlet.http.Cookie;
                import javax.servlet.http.HttpSession;

                public class AuthFilter {
                    public void doFilter(Cookie cookie, HttpSession session) {
                    }
                }
                """);

        var result = SpringSessionModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 1);

        String updated = Files.readString(javaFile);
        assertFalse(updated.contains("javax.servlet.http.Cookie"));
        assertFalse(updated.contains("javax.servlet.http.HttpSession"));
        assertTrue(updated.contains("jakarta.servlet.http.Cookie"));
        assertTrue(updated.contains("jakarta.servlet.http.HttpSession"));

        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/session/SpringSessionCookieConfiguration.java");
        assertTrue(Files.isRegularFile(generatedConfig));
    }

    @Test
    void generatesSessionConfigurationWhenSpringSessionDependencyPresent() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.session</groupId>
                      <artifactId>spring-session-data-redis</artifactId>
                    </dependency>
                  </dependencies>
                </project>
                """);

        var result = SpringSessionModernizer.modernize(tempDir);
        assertTrue(result.modified());

        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/session/SpringSessionCookieConfiguration.java");
        assertTrue(Files.isRegularFile(generatedConfig));
        String configContent = Files.readString(generatedConfig);
        assertTrue(configContent.contains("DefaultCookieSerializer"));
        assertTrue(configContent.contains("serializer.setCookieName(\"SESSION\")"));
    }
}
