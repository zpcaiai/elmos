package io.elmos.worker.web;

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
 * Enterprise OpenAPI 3 / Springdoc Modernizer (Replacing Legacy Swagger 2 / Springfox).
 *
 * <p>Modernizes REST API documentation for Spring Boot 3.x / Jakarta EE 10:
 * <ol>
 *   <li><b>Dependency Modernization:</b>
 *       Eliminates broken {@code springfox-swagger2} / {@code springfox-boot-starter} and replaces with
 *       {@code org.springdoc:springdoc-openapi-starter-webmvc-ui:2.5.0}.</li>
 *   <li><b>Annotation Translation:</b>
 *       Maps legacy Swagger 2 annotations to OpenAPI 3 annotations:
 *       <ul>
 *         <li>{@code @Api} &rarr; {@code @Tag}</li>
 *         <li>{@code @ApiOperation} &rarr; {@code @Operation}</li>
 *         <li>{@code @ApiParam} / {@code @ApiImplicitParam} &rarr; {@code @Parameter}</li>
 *         <li>{@code @ApiModelProperty} &rarr; {@code @Schema}</li>
 *       </ul>
 *   </li>
 *   <li><b>OpenAPI 3 Configuration Generation:</b>
 *       Generates {@code OpenApiDocumentationConfiguration.java} with Bearer Auth security scheme.</li>
 *   <li><b>Actuator & Swagger UI Path Configuration:</b>
 *       Sets standardized {@code /v3/api-docs} and {@code /swagger-ui.html} routes in {@code application.yml}.</li>
 * </ol>
 */
public final class SpringOpenApiDocumentationModernizer {

    public record OpenApiModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> generatedArtifacts
    ) {
        public static OpenApiModernizationResult empty() {
            return new OpenApiModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern LEGACY_SPRINGFOX_STARTER = Pattern.compile(
            "<dependency>\\s*<groupId>io\\.springfox</groupId>\\s*<artifactId>(?:springfox-swagger2|springfox-swagger-ui|springfox-boot-starter)</artifactId>(?:\\s*<version>[^<]+</version>)?\\s*</dependency>",
            Pattern.DOTALL
    );

    private static final String MODERN_SPRINGDOC_DEPENDENCY =
            """
                    <dependency>
                        <groupId>org.springdoc</groupId>
                        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
                        <version>2.5.0</version>
                    </dependency>""";

    private static final Pattern SWAGGER2_API_ANNOTATION = Pattern.compile(
            "@Api\\s*\\(\\s*(?:tags\\s*=\\s*|value\\s*=\\s*)?(\"[^\"]+\")[^)]*\\)"
    );

    private static final Pattern SWAGGER2_OPERATION_ANNOTATION = Pattern.compile(
            "@ApiOperation\\s*\\(\\s*(?:value\\s*=\\s*)?(\"[^\"]+\")[^)]*\\)"
    );

    private static final Pattern SWAGGER2_PARAM_ANNOTATION = Pattern.compile(
            "@ApiParam\\s*\\(\\s*(?:value\\s*=\\s*)?(\"[^\"]+\")[^)]*\\)"
    );

    private static final Pattern SWAGGER2_MODEL_PROP_ANNOTATION = Pattern.compile(
            "@ApiModelProperty\\s*\\(\\s*(?:value\\s*=\\s*)?(\"[^\"]+\")[^)]*\\)"
    );

    /**
     * Executes OpenAPI 3 / Springdoc modernization across the project workspace.
     */
    public OpenApiModernizationResult modernize(Path projectRoot) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return OpenApiModernizationResult.empty();
        }

        boolean anyModified = false;
        int totalChanges = 0;
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> generatedArtifacts = new ArrayList<>();

        // 1. Upgrade pom.xml dependencies
        Path pomPath = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomPath)) {
            String pomContent = Files.readString(pomPath, StandardCharsets.UTF_8);
            Matcher pomMatcher = LEGACY_SPRINGFOX_STARTER.matcher(pomContent);
            if (pomMatcher.find()) {
                String updatedPom = pomMatcher.replaceAll(MODERN_SPRINGDOC_DEPENDENCY);
                Files.writeString(pomPath, updatedPom, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(pomPath.toString());
                rulesApplied.add("REPLACE_SPRINGFOX_WITH_SPRINGDOC_OPENAPI");
            }
        }

        // 2. Scan and translate Swagger 2 annotations in Java files
        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                String source = Files.readString(javaFile, StandardCharsets.UTF_8);
                boolean fileChanged = false;

                if (source.contains("io.swagger.annotations")) {
                    // Update annotations
                    Matcher apiMatcher = SWAGGER2_API_ANNOTATION.matcher(source);
                    if (apiMatcher.find()) {
                        source = apiMatcher.replaceAll("@Tag(name = $1)");
                        fileChanged = true;
                    }

                    Matcher opMatcher = SWAGGER2_OPERATION_ANNOTATION.matcher(source);
                    if (opMatcher.find()) {
                        source = opMatcher.replaceAll("@Operation(summary = $1)");
                        fileChanged = true;
                    }

                    Matcher paramMatcher = SWAGGER2_PARAM_ANNOTATION.matcher(source);
                    if (paramMatcher.find()) {
                        source = paramMatcher.replaceAll("@Parameter(description = $1)");
                        fileChanged = true;
                    }

                    Matcher propMatcher = SWAGGER2_MODEL_PROP_ANNOTATION.matcher(source);
                    if (propMatcher.find()) {
                        source = propMatcher.replaceAll("@Schema(description = $1)");
                        fileChanged = true;
                    }

                    // Replace imports
                    source = source.replaceAll("import\\s+io\\.swagger\\.annotations\\.[^;]+;", "");
                    source = "import io.swagger.v3.oas.annotations.tags.Tag;\n"
                            + "import io.swagger.v3.oas.annotations.Operation;\n"
                            + "import io.swagger.v3.oas.annotations.Parameter;\n"
                            + "import io.swagger.v3.oas.annotations.media.Schema;\n"
                            + source;

                    fileChanged = true;
                    totalChanges++;
                    rulesApplied.add("TRANSLATE_SWAGGER2_TO_OPENAPI3_ANNOTATIONS");
                }

                if (fileChanged) {
                    Files.writeString(javaFile, source, StandardCharsets.UTF_8);
                    anyModified = true;
                    modifiedFiles.add(javaFile.toString());
                }
            }
        }

        // 3. Generate OpenApiDocumentationConfiguration
        Path configDir = projectRoot.resolve("src/main/java/io/elmos/generated/config");
        Files.createDirectories(configDir);
        Path openApiConfigFile = configDir.resolve("OpenApiDocumentationConfiguration.java");
        if (!Files.exists(openApiConfigFile)) {
            String configSource = generateOpenApiConfig();
            Files.writeString(openApiConfigFile, configSource, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(openApiConfigFile.toString());
            generatedArtifacts.add(openApiConfigFile.toString());
            rulesApplied.add("GENERATE_OPENAPI3_CONFIGURATION");
        }

        // 4. Configure springdoc paths in application.yml
        Path ymlPath = projectRoot.resolve("src/main/resources/application.yml");
        if (Files.isRegularFile(ymlPath)) {
            String ymlContent = Files.readString(ymlPath, StandardCharsets.UTF_8);
            if (!ymlContent.contains("springdoc:")) {
                String docSettings =
                        """

                        springdoc:
                          api-docs:
                            path: /v3/api-docs
                          swagger-ui:
                            path: /swagger-ui.html
                            operations-sorter: alpha
                            tags-sorter: alpha
                        """;
                Files.writeString(ymlPath, ymlContent + docSettings, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(ymlPath.toString());
                rulesApplied.add("CONFIGURE_SPRINGDOC_PATHS_IN_YML");
            }
        }

        return new OpenApiModernizationResult(anyModified, totalChanges, modifiedFiles, rulesApplied, generatedArtifacts);
    }

    private static String generateOpenApiConfig() {
        return """
                package io.elmos.generated.config;

                import io.swagger.v3.oas.models.Components;
                import io.swagger.v3.oas.models.OpenAPI;
                import io.swagger.v3.oas.models.info.Info;
                import io.swagger.v3.oas.models.security.SecurityRequirement;
                import io.swagger.v3.oas.models.security.SecurityScheme;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                /**
                 * Enterprise OpenAPI 3 Documentation Configuration.
                 */
                @Configuration
                public class OpenApiDocumentationConfiguration {

                    @Bean
                    public OpenAPI customOpenAPI() {
                        return new OpenAPI()
                                .info(new Info()
                                        .title("Modernized Enterprise REST API")
                                        .version("1.0.0")
                                        .description("Enterprise API Contract conforming to OpenAPI 3.0 standards."))
                                .addSecurityItem(new SecurityRequirement().addList("BearerAuth"))
                                .components(new Components()
                                        .addSecuritySchemes("BearerAuth", new SecurityScheme()
                                                .type(SecurityScheme.Type.HTTP)
                                                .scheme("bearer")
                                                .bearerFormat("JWT")));
                    }
                }
                """;
    }
}
