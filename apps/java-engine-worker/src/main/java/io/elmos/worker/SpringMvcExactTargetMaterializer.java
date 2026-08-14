package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import static io.elmos.worker.SpringUpgradeModels.BlockedException;

/**
 * Trusted, typed target emitter for one exact development fixture.
 *
 * <p>This class deliberately is not a general Spring MVC source transformer. It accepts only the
 * complete, content-addressed Spring Framework 5.3.39 fixture owned by the corresponding Batch 30
 * pack. The immutable manifest, POM, XML, Java and JSP shapes are all checked before any target is
 * published. Unknown files, changed bytes, symlinks and unsupported route tuples fail closed.
 * Repository code is never executed to materialize the target.</p>
 */
final class SpringMvcExactTargetMaterializer {
    static final String ROUTE_ID =
            "spring-framework-5.3-mvc-maven-to-boot-3.5.3-java-21";
    static final String PACK_KEY =
            "spring-framework-5-3-mvc-to-spring-boot-3-5-3";
    static final String STATUS = "MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED";

    private static final String MANIFEST_RESOURCE =
            "/spring-mvc/exact-5.3.39-fixture-manifest.json";
    private static final String MANIFEST_SHA256 =
            "f982de2d2daca2247f5f3efa788a64f653bb2d576a4c8516fafc0cd96d34fe74";
    private static final String RECIPE_SHA256 =
            "e6b648f5dfdf350c1f6ac0ccc9636b40453af13a48e18974076e455dc872b75b";
    private static final String TARGET_PROFILE_RESOURCE =
            "/spring-mvc/target-profile/profile.json";
    private static final long TARGET_PROFILE_BYTES = 3731;
    private static final String TARGET_PROFILE_SHA256 =
            "e343284913ec4c95837eb997292ce862ccb4fb23265de58cb27924d1233b39d5";
    private static final String TARGET_SCAFFOLD_MANIFEST_RESOURCE =
            "/spring-mvc/target-profile/scaffold-manifest.json";
    private static final long TARGET_SCAFFOLD_MANIFEST_BYTES = 1773;
    private static final String TARGET_SCAFFOLD_MANIFEST_SHA256 =
            "a2e741b1a535c690633b27e0301f6931ad287e2b0ddd3fefb97cb5194d5819d6";
    private static final String MATERIALIZER_CONTRACT_SHA256 = sha256(
            "io.elmos.worker.SpringMvcExactTargetMaterializer:v2:exact-fixture-profile-bound"
                    .getBytes(StandardCharsets.UTF_8));
    private static final long MAX_MANIFEST_BYTES = 64 * 1024;
    private static final String MAVEN_NS = "http://maven.apache.org/POM/4.0.0";
    private static final String WEB_NS = "http://xmlns.jcp.org/xml/ns/javaee";
    private static final String BEANS_NS = "http://www.springframework.org/schema/beans";
    private static final String CONTEXT_NS = "http://www.springframework.org/schema/context";
    private static final String MVC_NS = "http://www.springframework.org/schema/mvc";

    private static final Map<String, String> EXPECTED_PROPERTIES = Map.ofEntries(
            Map.entry("project.build.sourceEncoding", "UTF-8"),
            Map.entry("maven.compiler.release", "11"),
            Map.entry("spring-framework.version", "5.3.39"),
            Map.entry("servlet-api.version", "4.0.1"),
            Map.entry("validation-api.version", "2.0.1.Final"),
            Map.entry("hibernate-validator.version", "6.2.5.Final"),
            Map.entry("jackson.version", "2.17.2"),
            Map.entry("junit.version", "5.10.3"),
            Map.entry("hamcrest.version", "2.2"),
            Map.entry("json-path.version", "2.7.0"));
    private static final Map<String, String> EXPECTED_DEPENDENCIES = Map.ofEntries(
            Map.entry("org.springframework:spring-webmvc", "${spring-framework.version}|"),
            Map.entry("javax.servlet:javax.servlet-api", "${servlet-api.version}|provided"),
            Map.entry("javax.validation:validation-api", "${validation-api.version}|"),
            Map.entry("org.hibernate.validator:hibernate-validator", "${hibernate-validator.version}|"),
            Map.entry("org.glassfish:javax.el", "3.0.1-b12|"),
            Map.entry("com.fasterxml.jackson.core:jackson-databind", "${jackson.version}|"),
            Map.entry("org.springframework:spring-test", "${spring-framework.version}|test"),
            Map.entry("org.junit.jupiter:junit-jupiter", "${junit.version}|test"),
            Map.entry("org.hamcrest:hamcrest", "${hamcrest.version}|test"),
            Map.entry("com.jayway.jsonpath:json-path", "${json-path.version}|test"));
    private static final Map<String, String> EXPECTED_PLUGINS = Map.of(
            "org.apache.maven.plugins:maven-compiler-plugin", "3.13.0|release|11",
            "org.apache.maven.plugins:maven-surefire-plugin", "3.5.2|useModulePath|false",
            "org.apache.maven.plugins:maven-war-plugin", "3.4.0|failOnMissingWebXml|true");

    private static final String TARGET_POM = """
            <?xml version="1.0" encoding="UTF-8"?>
            <project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
              <modelVersion>4.0.0</modelVersion>
              <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.5.3</version><relativePath/></parent>
              <groupId>io.elmos.fixtures</groupId><artifactId>legacy-spring-mvc-boot</artifactId><version>1.0.0</version><packaging>war</packaging>
              <properties><java.version>21</java.version><maven.compiler.release>21</maven.compiler.release><spring-boot.version>3.5.3</spring-boot.version></properties>
              <dependencies>
                <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
                <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-validation</artifactId></dependency>
                <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>
                <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-tomcat</artifactId><scope>provided</scope></dependency>
                <dependency><groupId>org.apache.tomcat.embed</groupId><artifactId>tomcat-embed-jasper</artifactId><scope>provided</scope></dependency>
                <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>
              </dependencies>
              <build><finalName>legacy-spring-mvc-boot</finalName><plugins>
                <plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId><version>3.5.3</version><configuration><mainClass>io.elmos.legacy.LegacyMvcApplication</mainClass></configuration><executions><execution><goals><goal>repackage</goal></goals></execution></executions></plugin>
                <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-war-plugin</artifactId><version>3.4.0</version><configuration><failOnMissingWebXml>false</failOnMissingWebXml></configuration></plugin>
              </plugins></build>
            </project>
            """;
    private static final String APPLICATION = """
            package io.elmos.legacy;

            import io.elmos.legacy.boot.LegacyMvcConfiguration;
            import org.springframework.boot.SpringApplication;
            import org.springframework.boot.autoconfigure.SpringBootApplication;
            import org.springframework.boot.builder.SpringApplicationBuilder;
            import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
            import org.springframework.context.annotation.Import;

            @SpringBootApplication(scanBasePackages = {"io.elmos.legacy.service", "io.elmos.legacy.web"})
            @Import(LegacyMvcConfiguration.class)
            public class LegacyMvcApplication extends SpringBootServletInitializer {
                public static void main(String[] args) { SpringApplication.run(LegacyMvcApplication.class, args); }
                @Override
                protected SpringApplicationBuilder configure(SpringApplicationBuilder application) { return application.sources(LegacyMvcApplication.class); }
            }
            """;
    private static final String CONFIGURATION = """
            package io.elmos.legacy.boot;

            import io.elmos.legacy.web.RequestAuditInterceptor;
            import jakarta.servlet.DispatcherType;
            import java.util.EnumSet;
            import org.springframework.boot.web.servlet.FilterRegistrationBean;
            import org.springframework.context.annotation.Bean;
            import org.springframework.context.annotation.Configuration;
            import org.springframework.core.Ordered;
            import org.springframework.validation.Validator;
            import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
            import org.springframework.web.filter.CharacterEncodingFilter;
            import org.springframework.web.servlet.config.annotation.DefaultServletHandlerConfigurer;
            import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
            import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
            import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
            import org.springframework.web.servlet.view.InternalResourceViewResolver;

            @Configuration
            public class LegacyMvcConfiguration implements WebMvcConfigurer {
                @Bean(name = "validator") public LocalValidatorFactoryBean validator() { return new LocalValidatorFactoryBean(); }
                @Override public Validator getValidator() { return validator(); }
                @Bean public RequestAuditInterceptor requestAuditInterceptor() { return new RequestAuditInterceptor(); }
                @Override public void addInterceptors(InterceptorRegistry registry) { registry.addInterceptor(requestAuditInterceptor()).addPathPatterns("/api/**"); }
                @Override public void configureDefaultServletHandling(DefaultServletHandlerConfigurer configurer) { configurer.enable(); }
                @Override public void addResourceHandlers(ResourceHandlerRegistry registry) { registry.addResourceHandler("/assets/**").addResourceLocations("/assets/").setCachePeriod(3600); }
                @Bean public InternalResourceViewResolver internalResourceViewResolver() {
                    InternalResourceViewResolver resolver = new InternalResourceViewResolver();
                    resolver.setPrefix("/WEB-INF/views/"); resolver.setSuffix(".jsp"); resolver.setOrder(10); return resolver;
                }
                @Bean public FilterRegistrationBean<CharacterEncodingFilter> characterEncodingFilter() {
                    CharacterEncodingFilter filter = new CharacterEncodingFilter(); filter.setEncoding("UTF-8"); filter.setForceEncoding(true);
                    FilterRegistrationBean<CharacterEncodingFilter> registration = new FilterRegistrationBean<>(filter);
                    registration.setName("characterEncodingFilter"); registration.setUrlPatterns(java.util.List.of("/*"));
                    registration.setDispatcherTypes(EnumSet.of(DispatcherType.REQUEST, DispatcherType.ERROR));
                    registration.setOrder(Ordered.HIGHEST_PRECEDENCE); return registration;
                }
            }
            """;
    private static final String BOOT_PROPERTIES = """
            server.servlet.encoding.enabled=false
            server.servlet.register-default-servlet=true
            server.shutdown=graceful
            management.endpoints.web.exposure.include=health
            management.endpoint.health.show-details=never
            """;
    private static final String BOOT_TEST = """
            package io.elmos.legacy;

            import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
            import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
            import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
            import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
            import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;
            import org.junit.jupiter.api.Test;
            import org.springframework.beans.factory.annotation.Autowired;
            import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
            import org.springframework.boot.test.context.SpringBootTest;
            import org.springframework.test.web.servlet.MockMvc;

            @SpringBootTest
            @AutoConfigureMockMvc
            class LegacyMvcApplicationTest {
                @Autowired MockMvc mvc;
                @Test void bootsWithApiInterceptor() throws Exception {
                    mvc.perform(get("/api/orders/42")).andExpect(status().isOk()).andExpect(header().string("X-Legacy-Audit", "GET /api/orders/42")).andExpect(jsonPath("$.currency").value("CNY"));
                }
                @Test void keepsJspRouteOutsideApiInterceptor() throws Exception {
                    mvc.perform(get("/orders")).andExpect(status().isOk()).andExpect(view().name("orders/list")).andExpect(header().doesNotExist("X-Legacy-Audit"));
                }
                @Test void exposesOnlyHealthOutsideApiInterceptor() throws Exception {
                    mvc.perform(get("/actuator/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("UP")).andExpect(header().doesNotExist("X-Legacy-Audit"));
                    mvc.perform(get("/actuator/env")).andExpect(status().isNotFound()).andExpect(header().doesNotExist("X-Legacy-Audit"));
                }
            }
            """;

    private SpringMvcExactTargetMaterializer() {}

    static Materialization materialize(
            Path source,
            Path output,
            SpringRouteCatalog.SpringRoute route,
            ObjectMapper json
    ) {
        requireExactRoute(route);
        Objects.requireNonNull(json, "json");
        Path sourceRoot = source.toAbsolutePath().normalize();
        Path target = output.toAbsolutePath().normalize();
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
            throw blocked("MVC_TARGET_OUTPUT_EXISTS",
                    "The exact MVC target emitter refuses to overwrite an existing output tree.");
        }
        SourceManifest manifest = loadManifest(json);
        List<ControlledResource> targetProfileResources = loadTargetProfileResources(json);
        validateSource(sourceRoot, manifest);
        Path parent = target.getParent();
        if (parent == null) {
            throw blocked("MVC_TARGET_OUTPUT_INVALID", "The exact MVC target needs a parent directory.");
        }
        Path staging = parent.resolve("." + target.getFileName() + ".elmos-" + UUID.randomUUID());
        try {
            Files.createDirectories(parent);
            if (Files.exists(staging, LinkOption.NOFOLLOW_LINKS)) {
                throw blocked("MVC_TARGET_OUTPUT_EXISTS", "The MVC target staging path already exists.");
            }
            Files.createDirectory(staging);
            List<Map<String, Object>> sourceMap = copyJava(sourceRoot, staging, manifest);
            copyExact(sourceRoot.resolve("src/main/webapp/WEB-INF/views/orders/list.jsp"),
                    staging.resolve("src/main/webapp/WEB-INF/views/orders/list.jsp"));
            write(staging.resolve("pom.xml"), TARGET_POM);
            write(staging.resolve("src/main/java/io/elmos/legacy/LegacyMvcApplication.java"), APPLICATION);
            write(staging.resolve("src/main/java/io/elmos/legacy/boot/LegacyMvcConfiguration.java"),
                    CONFIGURATION);
            String legacyProperties = Files.readString(
                    sourceRoot.resolve("src/main/resources/legacy.properties"), StandardCharsets.UTF_8)
                    .stripTrailing();
            write(staging.resolve("src/main/resources/application.properties"),
                    legacyProperties + "\n" + BOOT_PROPERTIES);
            write(staging.resolve("src/test/java/io/elmos/legacy/LegacyMvcApplicationTest.java"),
                    BOOT_TEST);
            writeEvidence(staging, manifest, sourceMap, targetProfileResources, json);
            publish(staging, target);
            return new Materialization(target, MANIFEST_SHA256, manifest.files().size(), STATUS);
        } catch (BlockedException error) {
            deleteQuietly(staging);
            throw error;
        } catch (Exception error) {
            deleteQuietly(staging);
            throw blocked("MVC_TARGET_MATERIALIZATION_FAILED",
                    "The trusted exact MVC target could not be materialized: "
                            + error.getClass().getSimpleName());
        }
    }

    static boolean supports(SpringRouteCatalog.SpringRoute route) {
        return route != null
                && ROUTE_ID.equals(route.routeId())
                && PACK_KEY.equals(route.packKey())
                && route.sourceFamily() == SpringRouteCatalog.SourceFamily.SPRING_MVC
                && "5.3.39".equals(route.exactSourceVersion())
                && "3.5.3".equals(route.targetBoot())
                && "21".equals(route.targetJava())
                && SpringRouteCatalog.MAVEN_BUILD_TOOL.equals(route.buildTool());
    }

    private static void requireExactRoute(SpringRouteCatalog.SpringRoute route) {
        if (!supports(route)) {
            throw blocked("MVC_TARGET_MATERIALIZER_ROUTE_UNSUPPORTED",
                    "The trusted MVC target materializer supports only the exact Spring Framework "
                            + "5.3.39 / Java 11 / Maven 3.9.11 to Boot 3.5.3 / Java 21 route.");
        }
    }

    private static SourceManifest loadManifest(ObjectMapper json) {
        byte[] bytes;
        try (InputStream input = SpringMvcExactTargetMaterializer.class
                .getResourceAsStream(MANIFEST_RESOURCE)) {
            if (input == null) {
                throw blocked("MVC_TARGET_MANIFEST_MISSING",
                        "The immutable exact MVC input manifest is not packaged with the worker.");
            }
            bytes = input.readNBytes((int) MAX_MANIFEST_BYTES + 1);
        } catch (IOException error) {
            throw blocked("MVC_TARGET_MANIFEST_UNREADABLE",
                    "The immutable exact MVC input manifest could not be read.");
        }
        if (bytes.length > MAX_MANIFEST_BYTES || !MANIFEST_SHA256.equals(sha256(bytes))) {
            throw blocked("MVC_TARGET_MANIFEST_DIGEST_MISMATCH",
                    "The immutable exact MVC input manifest failed its embedded digest check.");
        }
        try {
            JsonNode root = json.readTree(bytes);
            require(root != null && root.isObject(), "MVC_TARGET_MANIFEST_INVALID",
                    "The exact MVC input manifest must be a JSON object.");
            require(root.path("schema_version").asInt(-1) == 1,
                    "MVC_TARGET_MANIFEST_INVALID", "The exact MVC manifest schema must equal 1.");
            require("EXACT_FIXTURE_ONLY".equals(root.path("profile_kind").asText()),
                    "MVC_TARGET_MANIFEST_INVALID", "The MVC manifest must remain exact-fixture-only.");
            require(PACK_KEY.equals(root.path("pack_key").asText()),
                    "MVC_TARGET_MANIFEST_INVALID", "The MVC manifest pack identity changed.");
            JsonNode tuple = root.path("exact_tuple");
            require("spring-mvc".equals(tuple.path("source_framework").asText())
                            && "5.3.39".equals(tuple.path("source_version").asText())
                            && "11".equals(tuple.path("source_java").asText())
                            && "maven-3.9.11".equals(tuple.path("source_build_tool").asText())
                            && "spring-boot".equals(tuple.path("target_framework").asText())
                            && "3.5.3".equals(tuple.path("target_version").asText())
                            && "21".equals(tuple.path("target_java").asText())
                            && "executable-war".equals(tuple.path("target_packaging").asText()),
                    "MVC_TARGET_MANIFEST_INVALID", "The MVC manifest exact tuple changed.");
            JsonNode files = root.path("files");
            require(files.isArray() && files.size() == 13, "MVC_TARGET_MANIFEST_INVALID",
                    "The exact MVC manifest must bind all 13 fixture files.");
            LinkedHashMap<String, SourceFile> parsed = new LinkedHashMap<>();
            for (JsonNode file : files) {
                String path = file.path("path").asText();
                long size = file.path("bytes").asLong(-1);
                String digest = file.path("sha256").asText();
                String role = file.path("role").asText();
                Path relative = Path.of(path).normalize();
                require(!path.isBlank() && !relative.isAbsolute() && !path.contains("\\")
                                && !path.startsWith("../") && !path.equals("..")
                                && relative.toString().replace('\\', '/').equals(path),
                        "MVC_TARGET_MANIFEST_INVALID", "The MVC manifest contains an unsafe path.");
                require(size >= 0 && digest.matches("[0-9a-f]{64}") && !role.isBlank(),
                        "MVC_TARGET_MANIFEST_INVALID", "The MVC manifest file binding is incomplete.");
                require(parsed.put(path, new SourceFile(path, size, digest, role)) == null,
                        "MVC_TARGET_MANIFEST_INVALID", "The MVC manifest contains a duplicate path.");
            }
            return new SourceManifest(parsed);
        } catch (BlockedException error) {
            throw error;
        } catch (Exception error) {
            throw blocked("MVC_TARGET_MANIFEST_INVALID",
                    "The immutable exact MVC input manifest could not be decoded.");
        }
    }

    private static List<ControlledResource> loadTargetProfileResources(ObjectMapper json) {
        ControlledResource profile = loadControlledResource(
                TARGET_PROFILE_RESOURCE, TARGET_PROFILE_BYTES, TARGET_PROFILE_SHA256);
        ControlledResource scaffold = loadControlledResource(
                TARGET_SCAFFOLD_MANIFEST_RESOURCE,
                TARGET_SCAFFOLD_MANIFEST_BYTES,
                TARGET_SCAFFOLD_MANIFEST_SHA256);
        try {
            JsonNode profileJson = json.readTree(profile.content());
            require(profileJson != null && profileJson.isObject()
                            && "spring-framework-5-3-mvc-to-spring-boot-3-5-3-target"
                            .equals(profileJson.path("profile_key").asText())
                            && profileJson.path("framework_versions").size() == 1
                            && "3.5.3".equals(profileJson.path("framework_versions").get(0).asText())
                            && profileJson.path("runtime_versions").size() == 1
                            && "21".equals(profileJson.path("runtime_versions").get(0).asText()),
                    "MVC_TARGET_PROFILE_INVALID",
                    "The controlled target profile identity or exact tuple changed.");
            JsonNode scaffoldJson = json.readTree(scaffold.content());
            require(scaffoldJson != null && scaffoldJson.isObject()
                            && PACK_KEY.equals(scaffoldJson.path("pack_key").asText())
                            && "executable-war".equals(scaffoldJson.path("target_packaging").asText())
                            && "target-profile/scaffold/materialize_target.py"
                            .equals(scaffoldJson.path("emitter").asText()),
                    "MVC_TARGET_PROFILE_INVALID",
                    "The controlled target scaffold manifest identity changed.");
        } catch (BlockedException error) {
            throw error;
        } catch (Exception error) {
            throw blocked("MVC_TARGET_PROFILE_INVALID",
                    "The controlled target profile resources could not be decoded.");
        }
        return List.of(profile, scaffold);
    }

    private static ControlledResource loadControlledResource(
            String resource,
            long expectedBytes,
            String expectedSha256
    ) {
        byte[] bytes;
        try (InputStream input = SpringMvcExactTargetMaterializer.class.getResourceAsStream(resource)) {
            if (input == null) {
                throw blocked("MVC_TARGET_PROFILE_MISSING",
                        "A controlled target profile resource is not packaged with the worker: "
                                + resource);
            }
            bytes = input.readNBytes((int) MAX_MANIFEST_BYTES + 1);
        } catch (IOException error) {
            throw blocked("MVC_TARGET_PROFILE_UNREADABLE",
                    "A controlled target profile resource could not be read: " + resource);
        }
        if (bytes.length != expectedBytes || !expectedSha256.equals(sha256(bytes))) {
            throw blocked("MVC_TARGET_PROFILE_DIGEST_MISMATCH",
                    "A controlled target profile resource failed its byte and digest check: "
                            + resource);
        }
        return new ControlledResource(resource, expectedBytes, expectedSha256, bytes);
    }

    private static void validateSource(Path source, SourceManifest manifest) {
        require(Files.isDirectory(source, LinkOption.NOFOLLOW_LINKS)
                        && !Files.isSymbolicLink(source),
                "MVC_TARGET_SOURCE_INVALID", "The MVC source must be a regular directory.");
        Set<String> actual = new LinkedHashSet<>();
        try (var paths = Files.walk(source)) {
            for (Path path : paths.toList()) {
                if (path.equals(source)) continue;
                Path relativePath = source.relativize(path);
                String relative = relativePath.toString().replace('\\', '/');
                String first = relativePath.getNameCount() == 0 ? "" : relativePath.getName(0).toString();
                if (Files.isSymbolicLink(path)) {
                    throw blocked("MVC_TARGET_SOURCE_SYMLINK_REJECTED",
                            "The exact MVC source may not contain symlinks.");
                }
                // Version-control metadata and disposable Maven output are not
                // source inputs. Every project-owned file outside those two
                // bounded roots must still match the immutable manifest.
                if (".git".equals(first) || "target".equals(first)) continue;
                if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) actual.add(relative);
                else if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                    throw blocked("MVC_TARGET_SOURCE_INVALID",
                            "The exact MVC source contains a non-regular entry.");
                }
            }
        } catch (BlockedException error) {
            throw error;
        } catch (IOException error) {
            throw blocked("MVC_TARGET_SOURCE_UNREADABLE",
                    "The exact MVC source file graph could not be inspected.");
        }
        require(actual.equals(manifest.files().keySet()), "MVC_TARGET_SOURCE_GRAPH_MISMATCH",
                "The exact MVC materializer accepts only the complete 13-file development fixture.");
        for (SourceFile expected : manifest.files().values()) {
            Path path = source.resolve(expected.path()).normalize();
            require(path.startsWith(source) && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS),
                    "MVC_TARGET_SOURCE_GRAPH_MISMATCH", "A required exact MVC input is unavailable.");
            try {
                require(Files.size(path) == expected.bytes()
                                && expected.sha256().equals(sha256(path)),
                        "MVC_TARGET_SOURCE_DIGEST_MISMATCH",
                        "Exact MVC fixture bytes changed: " + expected.path());
            } catch (IOException error) {
                throw blocked("MVC_TARGET_SOURCE_UNREADABLE",
                        "An exact MVC input could not be read: " + expected.path());
            }
        }
        validatePom(source.resolve("pom.xml"));
        validateWebXml(source.resolve("src/main/webapp/WEB-INF/web.xml"));
        validateSpringContexts(source);
        validateJavaShapes(source, manifest);
        try {
            String jsp = Files.readString(
                    source.resolve("src/main/webapp/WEB-INF/views/orders/list.jsp"),
                    StandardCharsets.UTF_8);
            require(!jsp.contains("<%@ taglib") && !jsp.contains("<jsp:"),
                    "MVC_TARGET_JSP_UNSUPPORTED",
                    "The exact MVC executable-WAR profile does not admit JSP tag libraries/actions.");
        } catch (IOException error) {
            throw blocked("MVC_TARGET_SOURCE_UNREADABLE", "The exact MVC JSP could not be read.");
        }
    }

    private static void validatePom(Path pom) {
        Element root = document(pom).getDocumentElement();
        require(MAVEN_NS.equals(root.getNamespaceURI()) && "project".equals(root.getLocalName()),
                "MVC_TARGET_POM_SHAPE_MISMATCH", "The source POM namespace/root is unsupported.");
        require(localNames(children(root)).equals(List.of("modelVersion", "groupId", "artifactId",
                        "version", "packaging", "properties", "dependencies", "build")),
                "MVC_TARGET_POM_SHAPE_MISMATCH", "The source POM graph changed.");
        require("4.0.0".equals(text(root, MAVEN_NS, "modelVersion"))
                        && "io.elmos.fixtures".equals(text(root, MAVEN_NS, "groupId"))
                        && "legacy-spring-mvc".equals(text(root, MAVEN_NS, "artifactId"))
                        && "1.0.0".equals(text(root, MAVEN_NS, "version"))
                        && "war".equals(text(root, MAVEN_NS, "packaging")),
                "MVC_TARGET_POM_SHAPE_MISMATCH", "The source Maven identity changed.");
        Element properties = one(root, MAVEN_NS, "properties");
        require(elementMap(properties).equals(EXPECTED_PROPERTIES),
                "MVC_TARGET_POM_SHAPE_MISMATCH", "The exact source POM properties changed.");
        LinkedHashMap<String, String> dependencies = new LinkedHashMap<>();
        for (Element dependency : children(one(root, MAVEN_NS, "dependencies"))) {
            require("dependency".equals(dependency.getLocalName()),
                    "MVC_TARGET_POM_SHAPE_MISMATCH", "Unknown Maven dependency element.");
            String coordinate = text(dependency, MAVEN_NS, "groupId") + ":"
                    + text(dependency, MAVEN_NS, "artifactId");
            require(dependencies.put(coordinate, text(dependency, MAVEN_NS, "version") + "|"
                            + text(dependency, MAVEN_NS, "scope")) == null,
                    "MVC_TARGET_POM_SHAPE_MISMATCH", "Duplicate Maven dependency.");
        }
        require(dependencies.equals(EXPECTED_DEPENDENCIES),
                "MVC_TARGET_POM_SHAPE_MISMATCH", "The exact source dependency graph changed.");
        Element build = one(root, MAVEN_NS, "build");
        require("legacy-spring-mvc".equals(text(build, MAVEN_NS, "finalName")),
                "MVC_TARGET_POM_SHAPE_MISMATCH", "The exact source WAR name changed.");
        LinkedHashMap<String, String> plugins = new LinkedHashMap<>();
        for (Element plugin : children(one(build, MAVEN_NS, "plugins"))) {
            String coordinate = text(plugin, MAVEN_NS, "groupId") + ":"
                    + text(plugin, MAVEN_NS, "artifactId");
            Element configuration = one(plugin, MAVEN_NS, "configuration");
            List<Element> settings = children(configuration);
            require(settings.size() == 1, "MVC_TARGET_POM_SHAPE_MISMATCH",
                    "Each exact source plugin must have one pinned setting.");
            Element setting = settings.get(0);
            require(plugins.put(coordinate, text(plugin, MAVEN_NS, "version") + "|"
                            + setting.getLocalName() + "|" + setting.getTextContent().trim()) == null,
                    "MVC_TARGET_POM_SHAPE_MISMATCH", "Duplicate Maven plugin.");
        }
        require(plugins.equals(EXPECTED_PLUGINS), "MVC_TARGET_POM_SHAPE_MISMATCH",
                "The exact source build plugin graph changed.");
    }

    private static void validateWebXml(Path webXml) {
        Element root = document(webXml).getDocumentElement();
        require(WEB_NS.equals(root.getNamespaceURI()) && "web-app".equals(root.getLocalName())
                        && "4.0".equals(root.getAttribute("version")),
                "MVC_TARGET_WEB_XML_SHAPE_MISMATCH", "Only the exact Servlet 4 web.xml is admitted.");
        require(localNames(children(root)).equals(List.of("display-name", "context-param", "listener",
                        "filter", "filter-mapping", "servlet", "servlet-mapping")),
                "MVC_TARGET_WEB_XML_SHAPE_MISMATCH", "The exact web.xml element graph changed.");
        require("Legacy Spring MVC Orders".equals(text(root, WEB_NS, "display-name"))
                        && "org.springframework.web.context.ContextLoaderListener".equals(
                        text(one(root, WEB_NS, "listener"), WEB_NS, "listener-class"))
                        && "org.springframework.web.filter.CharacterEncodingFilter".equals(
                        text(one(root, WEB_NS, "filter"), WEB_NS, "filter-class"))
                        && "org.springframework.web.servlet.DispatcherServlet".equals(
                        text(one(root, WEB_NS, "servlet"), WEB_NS, "servlet-class"))
                        && "/".equals(text(one(root, WEB_NS, "servlet-mapping"), WEB_NS, "url-pattern")),
                "MVC_TARGET_WEB_XML_SHAPE_MISMATCH", "The Servlet bootstrap semantics changed.");
        Element filterMapping = one(root, WEB_NS, "filter-mapping");
        require(texts(filterMapping, WEB_NS, "dispatcher").equals(List.of("REQUEST", "ERROR"))
                        && "/*".equals(text(filterMapping, WEB_NS, "url-pattern")),
                "MVC_TARGET_WEB_XML_SHAPE_MISMATCH", "The UTF-8 filter mapping changed.");
    }

    private static void validateSpringContexts(Path source) {
        Element rootContext = document(source.resolve(
                "src/main/resources/WEB-INF/spring/root-context.xml")).getDocumentElement();
        require(BEANS_NS.equals(rootContext.getNamespaceURI())
                        && qualifiedNames(children(rootContext)).equals(List.of(
                        CONTEXT_NS + "#property-placeholder", CONTEXT_NS + "#component-scan")),
                "MVC_TARGET_CONTEXT_SHAPE_MISMATCH", "The root Spring context graph changed.");
        Element placeholder = one(rootContext, CONTEXT_NS, "property-placeholder");
        Element serviceScan = one(rootContext, CONTEXT_NS, "component-scan");
        require(attributes(placeholder).equals(Map.of(
                        "location", "classpath:legacy.properties", "ignore-unresolvable", "false"))
                        && attributes(serviceScan).equals(Map.of(
                        "base-package", "io.elmos.legacy.service")),
                "MVC_TARGET_CONTEXT_SHAPE_MISMATCH", "The root context configuration changed.");

        Element servlet = document(source.resolve(
                "src/main/resources/WEB-INF/spring/servlet-context.xml")).getDocumentElement();
        require(BEANS_NS.equals(servlet.getNamespaceURI())
                        && qualifiedNames(children(servlet)).equals(List.of(
                        CONTEXT_NS + "#component-scan", MVC_NS + "#annotation-driven",
                        MVC_NS + "#resources", MVC_NS + "#default-servlet-handler",
                        MVC_NS + "#interceptors", BEANS_NS + "#bean", BEANS_NS + "#bean")),
                "MVC_TARGET_CONTEXT_SHAPE_MISMATCH", "The servlet Spring context graph changed.");
        require(attributes(one(servlet, CONTEXT_NS, "component-scan")).equals(Map.of(
                        "base-package", "io.elmos.legacy.web"))
                        && attributes(one(servlet, MVC_NS, "annotation-driven")).equals(Map.of(
                        "validator", "validator"))
                        && attributes(one(servlet, MVC_NS, "resources")).equals(Map.of(
                        "mapping", "/assets/**", "location", "/assets/", "cache-period", "3600"))
                        && attributes(one(servlet, MVC_NS, "default-servlet-handler")).isEmpty(),
                "MVC_TARGET_CONTEXT_SHAPE_MISMATCH", "The exact MVC configuration changed.");
        Element interceptors = one(servlet, MVC_NS, "interceptors");
        require(qualifiedNames(children(interceptors)).equals(List.of(MVC_NS + "#interceptor")),
                "MVC_TARGET_CONTEXT_SHAPE_MISMATCH", "The MVC interceptor graph changed.");
        Element interceptor = one(interceptors, MVC_NS, "interceptor");
        require(qualifiedNames(children(interceptor)).equals(List.of(
                        MVC_NS + "#mapping", BEANS_NS + "#bean"))
                        && attributes(one(interceptor, MVC_NS, "mapping")).equals(Map.of(
                        "path", "/api/**"))
                        && attributes(one(interceptor, BEANS_NS, "bean")).equals(Map.of(
                        "class", "io.elmos.legacy.web.RequestAuditInterceptor")),
                "MVC_TARGET_CONTEXT_SHAPE_MISMATCH", "The exact audit interceptor mapping changed.");
        List<Element> beans = elements(servlet, BEANS_NS, "bean");
        require(beans.size() == 3, "MVC_TARGET_CONTEXT_SHAPE_MISMATCH",
                "The exact servlet bean graph changed.");
    }

    private static void validateJavaShapes(Path source, SourceManifest manifest) {
        Map<String, List<String>> required = Map.of(
                "src/main/java/io/elmos/legacy/service/LegacyOrderService.java", List.of(
                        "package io.elmos.legacy.service;", "@Service", "public class LegacyOrderService"),
                "src/main/java/io/elmos/legacy/web/ApiExceptionHandler.java", List.of(
                        "package io.elmos.legacy.web;", "@ControllerAdvice", "public class ApiExceptionHandler"),
                "src/main/java/io/elmos/legacy/web/LegacyOrderController.java", List.of(
                        "package io.elmos.legacy.web;", "@Controller", "public class LegacyOrderController"),
                "src/main/java/io/elmos/legacy/web/LegacyOrderForm.java", List.of(
                        "package io.elmos.legacy.web;", "public class LegacyOrderForm"),
                "src/main/java/io/elmos/legacy/web/RequestAuditInterceptor.java", List.of(
                        "package io.elmos.legacy.web;", "public class RequestAuditInterceptor implements HandlerInterceptor"));
        List<String> blockedTokens = List.of(
                "WebApplicationInitializer", "ServletContainerInitializer",
                "AbstractAnnotationConfigDispatcherServletInitializer", "org.springframework.security",
                "javax.persistence", "jakarta.persistence", "@Transactional", "JmsTemplate",
                "RabbitTemplate", "CacheManager", "@Scheduled", "@Configuration", "@Bean",
                "@ComponentScan", "@EnableWebMvc", "@Import", "@ImportResource");
        for (SourceFile file : manifest.files().values()) {
            if (!file.role().equals("java-main")) continue;
            try {
                String text = Files.readString(source.resolve(file.path()), StandardCharsets.UTF_8);
                for (String token : required.get(file.path())) {
                    require(text.contains(token), "MVC_TARGET_JAVA_SHAPE_MISMATCH",
                            "An exact Java declaration changed: " + file.path());
                }
                for (String token : blockedTokens) {
                    require(!text.contains(token), "MVC_TARGET_JAVA_SHAPE_MISMATCH",
                            "An unsupported Java construct is active: " + token);
                }
            } catch (IOException error) {
                throw blocked("MVC_TARGET_SOURCE_UNREADABLE",
                        "An exact MVC Java source could not be read.");
            }
        }
    }

    private static List<Map<String, Object>> copyJava(
            Path source,
            Path target,
            SourceManifest manifest
    ) throws IOException {
        List<Map<String, Object>> mappings = new ArrayList<>();
        for (SourceFile file : manifest.files().values()) {
            if (!file.role().startsWith("java-")) continue;
            String text = Files.readString(source.resolve(file.path()), StandardCharsets.UTF_8)
                    .replace("javax.validation", "jakarta.validation")
                    .replace("javax.servlet", "jakarta.servlet");
            write(target.resolve(file.path()), text);
            LinkedHashMap<String, Object> mapping = new LinkedHashMap<>();
            mapping.put("source", file.path());
            mapping.put("target", file.path());
            mapping.put("source_sha256", file.sha256());
            mapping.put("mapping",
                    "copy-with-exact-javax-validation-and-servlet-namespace-migration");
            mappings.add(mapping);
        }
        return mappings;
    }

    private static void writeEvidence(
            Path target,
            SourceManifest manifest,
            List<Map<String, Object>> sourceMap,
            List<ControlledResource> targetProfileResources,
            ObjectMapper json
    ) throws IOException {
        LinkedHashMap<String, Object> receipt = new LinkedHashMap<>();
        receipt.put("schema_version", 1);
        receipt.put("pack_key", PACK_KEY);
        receipt.put("status", STATUS);
        receipt.put("profile_scope", "EXACT_FIXTURE_ONLY");
        receipt.put("generator_binding", Map.of(
                "materializer_contract_sha256", MATERIALIZER_CONTRACT_SHA256,
                "input_manifest_sha256", MANIFEST_SHA256,
                "recipe_sha256", RECIPE_SHA256,
                "controlled_target_profile_resources", targetProfileResources.stream()
                        .map(ControlledResource::evidence).toList()));
        receipt.put("validated_source_manifest", Map.of(
                "sha256", MANIFEST_SHA256,
                "file_count", manifest.files().size(),
                "complete_file_graph", true));
        receipt.put("exact_tuple", Map.of(
                "source", Map.of("spring_framework", "5.3.39", "java", "11",
                        "maven", "3.9.11", "packaging", "war"),
                "target", Map.of("spring_boot", "3.5.3", "java", "21",
                        "maven", "3.9.11", "packaging", "executable-war")));
        List<Map<String, Object>> sourceInputs = manifest.files().values().stream()
                .map(file -> Map.<String, Object>of(
                        "path", file.path(), "bytes", file.bytes(), "sha256", file.sha256(),
                        "role", file.role()))
                .toList();
        receipt.put("source_inputs", sourceInputs);
        receipt.put("retired_from_target", List.of(
                Map.of("path", "src/main/webapp/WEB-INF/web.xml",
                        "replacement", "LegacyMvcApplication plus LegacyMvcConfiguration"),
                Map.of("path", "src/main/resources/WEB-INF/spring/root-context.xml",
                        "replacement", "Boot component scan and application.properties"),
                Map.of("path", "src/main/resources/WEB-INF/spring/servlet-context.xml",
                        "replacement", "LegacyMvcConfiguration")));
        receipt.put("preserved_contracts", List.of(
                "DispatcherServlet / through Boot MVC",
                "UTF-8 CharacterEncodingFilter REQUEST and ERROR dispatch",
                "service and web component scanning",
                "fail-fast legacy.orders.currency property resolution",
                "Jakarta Validation and ControllerAdvice error shape",
                "RequestAuditInterceptor /api/** mapping",
                "JSP /WEB-INF/views prefix and .jsp suffix at order 10",
                "static /assets/** mapping with 3600 second cache",
                "default servlet fallback", "Actuator health-only exposure",
                "Boot main and SpringBootServletInitializer executable WAR entry points"));
        receipt.put("execution", Map.of(
                "source_build", "NOT_RUN", "source_startup", "NOT_RUN",
                "target_build", "NOT_RUN", "target_startup", "NOT_RUN",
                "behavior_equivalence", "NOT_RUN"));
        writeJson(target.resolve(".elmos/migration-receipt.json"), receipt, json);
        writeJson(target.resolve(".elmos/source-map.json"), Map.of(
                "schema_version", 1, "mappings", sourceMap), json);
    }

    private static void publish(Path staging, Path target) throws IOException {
        try {
            Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException unsupported) {
            Files.move(staging, target);
        }
    }

    private static void copyExact(Path source, Path target) throws IOException {
        Files.createDirectories(target.getParent());
        Files.copy(source, target);
    }

    private static void write(Path path, String content) throws IOException {
        Files.createDirectories(path.getParent());
        Files.writeString(path, content, StandardCharsets.UTF_8);
    }

    private static void writeJson(Path path, Object value, ObjectMapper json) throws IOException {
        Files.createDirectories(path.getParent());
        Files.write(path, json.writerWithDefaultPrettyPrinter().writeValueAsBytes(value));
    }

    private static Document document(Path path) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            return factory.newDocumentBuilder().parse(path.toFile());
        } catch (Exception error) {
            throw blocked("MVC_TARGET_XML_SHAPE_MISMATCH",
                    "An exact MVC XML contract could not be parsed safely.");
        }
    }

    private static List<Element> children(Element parent) {
        List<Element> children = new ArrayList<>();
        for (Node node = parent.getFirstChild(); node != null; node = node.getNextSibling()) {
            if (node instanceof Element element) children.add(element);
        }
        return children;
    }

    private static List<Element> elements(Element parent, String namespace, String localName) {
        List<Element> matches = new ArrayList<>();
        var nodes = parent.getElementsByTagNameNS(namespace, localName);
        for (int index = 0; index < nodes.getLength(); index++) {
            matches.add((Element) nodes.item(index));
        }
        return matches;
    }

    private static Element one(Element parent, String namespace, String localName) {
        List<Element> matches = elements(parent, namespace, localName);
        require(matches.size() == 1, "MVC_TARGET_XML_SHAPE_MISMATCH",
                "Expected exactly one XML element: " + localName);
        return matches.get(0);
    }

    private static String text(Element parent, String namespace, String localName) {
        List<Element> matches = elements(parent, namespace, localName);
        return matches.isEmpty() ? "" : matches.get(0).getTextContent().trim();
    }

    private static List<String> texts(Element parent, String namespace, String localName) {
        return elements(parent, namespace, localName).stream()
                .map(element -> element.getTextContent().trim()).toList();
    }

    private static List<String> localNames(List<Element> elements) {
        return elements.stream().map(Element::getLocalName).toList();
    }

    private static List<String> qualifiedNames(List<Element> elements) {
        return elements.stream().map(element -> element.getNamespaceURI() + "#"
                + element.getLocalName()).toList();
    }

    private static Map<String, String> elementMap(Element parent) {
        LinkedHashMap<String, String> values = new LinkedHashMap<>();
        for (Element element : children(parent)) {
            require(values.put(element.getLocalName(), element.getTextContent().trim()) == null,
                    "MVC_TARGET_XML_SHAPE_MISMATCH", "Duplicate XML element: "
                            + element.getLocalName());
        }
        return values;
    }

    private static Map<String, String> attributes(Element element) {
        LinkedHashMap<String, String> values = new LinkedHashMap<>();
        for (int index = 0; index < element.getAttributes().getLength(); index++) {
            Node attribute = element.getAttributes().item(index);
            if (XMLConstants.XMLNS_ATTRIBUTE_NS_URI.equals(attribute.getNamespaceURI())) continue;
            values.put(attribute.getLocalName() == null ? attribute.getNodeName()
                    : attribute.getLocalName(), attribute.getNodeValue());
        }
        return values;
    }

    private static String sha256(Path path) throws IOException {
        try (InputStream input = Files.newInputStream(path)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[8192];
            for (int read; (read = input.read(buffer)) >= 0;) {
                if (read > 0) digest.update(buffer, 0, read);
            }
            return hex(digest.digest());
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static String sha256(byte[] bytes) {
        try {
            return hex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder hex = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) hex.append(String.format("%02x", value));
        return hex.toString();
    }

    private static void deleteQuietly(Path path) {
        if (path == null || !Files.exists(path, LinkOption.NOFOLLOW_LINKS)) return;
        try {
            Files.walkFileTree(path, new SimpleFileVisitor<>() {
                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                        throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override public FileVisitResult postVisitDirectory(Path directory, IOException error)
                        throws IOException {
                    if (error != null) throw error;
                    Files.deleteIfExists(directory);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException ignored) {
            // Best-effort cleanup of a never-published staging tree. The caller still fails closed.
        }
    }

    private static void require(boolean condition, String code, String message) {
        if (!condition) throw blocked(code, message);
    }

    private static BlockedException blocked(String code, String message) {
        return new BlockedException(code, message);
    }

    record Materialization(Path output, String manifestSha256, int sourceFileCount, String status) {}
    private record ControlledResource(String resource, long bytes, String sha256, byte[] content) {
        Map<String, Object> evidence() {
            return Map.of(
                    "resource", "classpath:" + resource,
                    "bytes", bytes,
                    "sha256", sha256);
        }
    }
    private record SourceFile(String path, long bytes, String sha256, String role) {}
    private record SourceManifest(LinkedHashMap<String, SourceFile> files) {}
}
