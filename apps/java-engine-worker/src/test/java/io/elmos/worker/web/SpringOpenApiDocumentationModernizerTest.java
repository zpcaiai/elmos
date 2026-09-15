package io.elmos.worker.web;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringOpenApiDocumentationModernizerTest {

    @Test
    void testOpenApiDocumentationModernizationFlow(@TempDir Path tempDir) throws IOException {
        // 1. Setup pom.xml with legacy springfox
        Path pomPath = tempDir.resolve("pom.xml");
        String pomContent = """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>io.springfox</groupId>
                            <artifactId>springfox-swagger2</artifactId>
                            <version>2.9.2</version>
                        </dependency>
                    </dependencies>
                </project>
                """;
        Files.writeString(pomPath, pomContent);

        // 2. Setup controller with Swagger 2 annotations
        Path srcDir = tempDir.resolve("src/main/java/com/example/controller");
        Files.createDirectories(srcDir);
        Path controllerPath = srcDir.resolve("UserController.java");
        String legacyCode = """
                package com.example.controller;

                import io.swagger.annotations.Api;
                import io.swagger.annotations.ApiOperation;
                import io.swagger.annotations.ApiParam;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.PathVariable;
                import org.springframework.web.bind.annotation.RestController;

                @Api(tags = "User Management API")
                @RestController
                public class UserController {

                    @ApiOperation(value = "Fetch user details")
                    @GetMapping("/users/{id}")
                    public String getUser(@ApiParam(value = "User Unique ID") @PathVariable String id) {
                        return id;
                    }
                }
                """;
        Files.writeString(controllerPath, legacyCode);

        // 3. Setup application.yml
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path ymlPath = resDir.resolve("application.yml");
        Files.writeString(ymlPath, "server:\n  port: 8080\n");

        // Execute modernization
        SpringOpenApiDocumentationModernizer modernizer = new SpringOpenApiDocumentationModernizer();
        SpringOpenApiDocumentationModernizer.OpenApiModernizationResult result = modernizer.modernize(tempDir);

        assertTrue(result.modified(), "Project should be modified");
        assertTrue(result.changesCount() >= 4, "Should have applied at least 4 modifications");

        // Verify pom.xml upgraded to springdoc
        String updatedPom = Files.readString(pomPath);
        assertTrue(updatedPom.contains("springdoc-openapi-starter-webmvc-ui"), "Should contain springdoc dependency");
        assertFalse(updatedPom.contains("springfox-swagger2"), "Legacy springfox should be eliminated");

        // Verify annotations translated
        String updatedJava = Files.readString(controllerPath);
        assertTrue(updatedJava.contains("@Tag(name = \"User Management API\")"), "Should translate @Api to @Tag");
        assertTrue(updatedJava.contains("@Operation(summary = \"Fetch user details\")"), "Should translate @ApiOperation to @Operation");
        assertTrue(updatedJava.contains("@Parameter(description = \"User Unique ID\")"), "Should translate @ApiParam to @Parameter");
        assertFalse(updatedJava.contains("import io.swagger.annotations"), "Legacy swagger imports should be removed");
        assertTrue(updatedJava.contains("import io.swagger.v3.oas.annotations"), "OpenAPI 3 imports should be present");

        // Verify OpenApiDocumentationConfiguration generated
        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/config/OpenApiDocumentationConfiguration.java");
        assertTrue(Files.exists(generatedConfig), "OpenApiDocumentationConfiguration should be generated");
        String configSource = Files.readString(generatedConfig);
        assertTrue(configSource.contains("OpenAPI customOpenAPI()"), "Should declare custom OpenAPI bean");
        assertTrue(configSource.contains("BearerAuth"), "Should configure BearerAuth scheme");

        // Verify application.yml updated
        String updatedYml = Files.readString(ymlPath);
        assertTrue(updatedYml.contains("springdoc:"), "Should configure springdoc in application.yml");
        assertTrue(updatedYml.contains("path: /swagger-ui.html"), "Should set swagger-ui path");
    }
}
