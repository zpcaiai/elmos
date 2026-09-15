package io.elmos.worker.ecosystem;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringEcosystemDependencyModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesSpringfoxSwaggerToSpringdocOpenApi3() throws IOException {
        Path pom = tempDir.resolve("pom.xml");
        Files.writeString(pom, """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>com.example</groupId>
                  <artifactId>demo</artifactId>
                  <version>1.0.0</version>
                  <dependencies>
                    <dependency>
                      <groupId>io.springfox</groupId>
                      <artifactId>springfox-swagger2</artifactId>
                      <version>2.9.2</version>
                    </dependency>
                    <dependency>
                      <groupId>io.springfox</groupId>
                      <artifactId>springfox-swagger-ui</artifactId>
                      <version>2.9.2</version>
                    </dependency>
                    <dependency>
                      <groupId>org.mybatis.spring.boot</groupId>
                      <artifactId>mybatis-spring-boot-starter</artifactId>
                      <version>2.2.2</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path srcDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(srcDir);
        Path controller = srcDir.resolve("OrderController.java");
        Files.writeString(controller, """
                package com.example;

                import io.swagger.annotations.Api;
                import io.swagger.annotations.ApiOperation;
                import io.swagger.annotations.ApiParam;

                @Api(tags = "Order Management")
                public class OrderController {

                    @ApiOperation(value = "Get Order", notes = "Fetches order by code")
                    public String getOrder(@ApiParam(value = "Order code", required = true) String code) {
                        return code;
                    }
                }
                """);

        Path dto = srcDir.resolve("OrderDto.java");
        Files.writeString(dto, """
                package com.example;

                import io.swagger.annotations.ApiModel;
                import io.swagger.annotations.ApiModelProperty;

                @ApiModel(description = "Order Details")
                public class OrderDto {
                    @ApiModelProperty(value = "Order number", example = "ORD-12345")
                    private String orderNo;
                }
                """);

        var result = SpringEcosystemDependencyModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("RULE-SPRINGFOX-TO-SPRINGDOC-OPENAPI3"));
        assertTrue(result.rulesApplied().contains("RULE-MYBATIS-BOOT-3-JAKARTA-UPGRADE"));
        assertTrue(result.rulesApplied().contains("RULE-ANNOTATION-API-TO-TAG"));
        assertTrue(result.rulesApplied().contains("RULE-ANNOTATION-APIOPERATION-TO-OPERATION"));
        assertTrue(result.rulesApplied().contains("RULE-ANNOTATION-APIPARAM-TO-PARAMETER"));
        assertTrue(result.rulesApplied().contains("RULE-ANNOTATION-APIMODEL-TO-SCHEMA"));
        assertTrue(result.rulesApplied().contains("RULE-ANNOTATION-APIMODELPROPERTY-TO-SCHEMA"));

        String updatedPom = Files.readString(pom);
        assertTrue(updatedPom.contains("springdoc-openapi-starter-webmvc-ui"));
        assertTrue(updatedPom.contains("<version>3.0.3</version>"));
        assertTrue(updatedPom.contains("<arg>-parameters</arg>"));

        String updatedController = Files.readString(controller);
        assertTrue(updatedController.contains("@Tag(name = \"Order Management\")"));
        assertTrue(updatedController.contains("@Operation(summary = \"Get Order\", description = \"Fetches order by code\")"));
        assertTrue(updatedController.contains("@Parameter(description = \"Order code\", required = true)"));

        String updatedDto = Files.readString(dto);
        assertTrue(updatedDto.contains("@Schema(description = \"Order Details\")"));
        assertTrue(updatedDto.contains("@Schema(description = \"Order number\", example = \"ORD-12345\")"));
    }

    @Test
    void modernizesControllerParameterNamesMissingExplicitName() throws IOException {
        Path srcDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(srcDir);
        Path controller = srcDir.resolve("UserController.java");
        Files.writeString(controller, """
                package com.example;

                import org.springframework.web.bind.annotation.*;

                @RestController
                @RequestMapping("/api/users")
                public class UserController {

                    @GetMapping("/{id}")
                    public String getUser(@PathVariable Long id, @RequestParam String query, @RequestHeader String auth) {
                        return id + query + auth;
                    }
                }
                """);

        var result = SpringEcosystemDependencyModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("RULE-EXPLICIT-CONTROLLER-PARAM-NAME-PATHVARIABLE"));
        assertTrue(result.rulesApplied().contains("RULE-EXPLICIT-CONTROLLER-PARAM-NAME-REQUESTPARAM"));
        assertTrue(result.rulesApplied().contains("RULE-EXPLICIT-CONTROLLER-PARAM-NAME-REQUESTHEADER"));

        String code = Files.readString(controller);
        assertTrue(code.contains("@PathVariable(\"id\") Long id"));
        assertTrue(code.contains("@RequestParam(\"query\") String query"));
        assertTrue(code.contains("@RequestHeader(\"auth\") String auth"));
    }
}
