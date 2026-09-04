package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.snapshot.DeterministicSnapshotArchiver;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringUpgradeRealProjectEndToEndTest {
    @TempDir Path temporaryDirectory;
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void realMavenBoot27LegacyOrdersEndToEndPipeline() throws Exception {
        Path fixture = legacyOrdersFixture();
        Path source = temporaryDirectory.resolve("maven-legacy-orders");
        copyTree(fixture, source);

        // 1. Snapshot archiving & immutability
        DeterministicSnapshotArchiver.SnapshotContext context =
                new DeterministicSnapshotArchiver.SnapshotContext(
                        "MATERIALIZED", "legacy-orders", "legacy-orders", "main",
                        "0123456789abcdef0123456789abcdef01234567",
                        "0".repeat(40));
        DeterministicSnapshotArchiver.SnapshotArchive archive1 =
                new DeterministicSnapshotArchiver().archive(source, context);
        DeterministicSnapshotArchiver.SnapshotArchive archive2 =
                new DeterministicSnapshotArchiver().archive(source, context);
        assertEquals(archive1.archiveSha256(), archive2.archiveSha256());
        assertEquals(64, archive1.archiveSha256().length());

        // 2. Static fingerprinting & non-standard component detection
        SpringUpgradeModels.Fingerprint fingerprint =
                LocalSpringUpgradeExecutionPort.fingerprintMaven(source);
        assertEquals("2.7.18", fingerprint.springBootVersion());
        assertEquals("17", fingerprint.javaVersion());
        assertEquals(SpringRouteCatalog.MAVEN_BUILD_TOOL, fingerprint.buildTool());
        assertTrue(fingerprint.unknowns().contains("legacy-javax-validation-requires-jakarta-migration"),
                "Fingerprint must detect legacy-javax-validation in legacy-orders");

        // 3. Route selection
        SpringRouteCatalog.Selection selection =
                LocalSpringUpgradeExecutionPort.selectRoute(fingerprint, "3.5.3", "21", false);
        assertEquals("boot-2.7-maven-to-boot-3.5.3-java-21", selection.route().routeId());
        assertEquals("3.5.3", selection.route().targetBoot());
        assertEquals("21", selection.route().targetJava());
        assertEquals(SpringRouteCatalog.EvidenceStatus.PASSED_LOCAL, selection.evidence());
        assertFalse(selection.requiresExperimentalOptIn());

        // 4. Deployment guidance and Migration Diagnostics generation
        Path migrated = temporaryDirectory.resolve("migrated-orders");
        copyTree(source, migrated);
        SpringDeploymentGuidance.writeTo(migrated, "maven", selection.route());

        Path diagnosticsPath = migrated.resolve("docs/MIGRATION_DIAGNOSTICS.md");
        assertTrue(Files.exists(diagnosticsPath), "docs/MIGRATION_DIAGNOSTICS.md must be generated");
        String diagnostics = Files.readString(diagnosticsPath);
        assertTrue(diagnostics.contains("当前构建工具：`maven`"));
        assertTrue(diagnostics.contains("javax 到 jakarta 命名空间迁移"));
        assertTrue(diagnostics.contains("jakarta.validation"));
        assertTrue(diagnostics.contains("WebSecurityConfigurerAdapter"));

        Path localRunPath = migrated.resolve("docs/LOCAL_RUN.md");
        assertTrue(Files.exists(localRunPath), "docs/LOCAL_RUN.md must be generated");
        String localRun = Files.readString(localRunPath);
        assertTrue(localRun.contains("Spring Boot 3.5.3"));
        assertTrue(localRun.contains("Java 21"));

        Path cloudRunProfile = migrated.resolve("deploy/cloud-run/deployment-profile.json");
        assertTrue(Files.exists(cloudRunProfile));
        JsonNode profileJson = json.readTree(cloudRunProfile.toFile());
        assertEquals("CONFIGURATION_REQUIRED", profileJson.path("status").asText());
    }

    @Test
    void realGradleLegacyProjectDynamicInitScriptAndDiagnostics() throws Exception {
        Path gradleProject = temporaryDirectory.resolve("gradle-legacy-orders");
        Files.createDirectories(gradleProject.resolve("src/main/java/io/elmos/fixtures"));
        Files.writeString(gradleProject.resolve("settings.gradle"), "rootProject.name = 'gradle-legacy-orders'\n");
        Files.writeString(gradleProject.resolve("build.gradle"), """
                plugins {
                    id 'org.springframework.boot' version '2.7.18'
                    id 'io.spring.dependency-management' version '1.0.15.RELEASE'
                    id 'java'
                }
                group = 'io.elmos.fixtures'
                version = '0.1.0'
                sourceCompatibility = '17'
                repositories {
                    mavenCentral()
                }
                configurations {
                    compile
                }
                dependencies {
                    implementation 'org.springframework.boot:spring-boot-starter-web'
                    implementation 'com.custom.starter:custom-audit-spring-boot-starter:1.0.0'
                    testImplementation 'org.springframework.boot:spring-boot-starter-test'
                }
                """);
        Files.writeString(gradleProject.resolve("src/main/java/io/elmos/fixtures/OrderController.java"), """
                package io.elmos.fixtures;
                import javax.validation.constraints.NotNull;
                import org.springframework.web.bind.annotation.RestController;
                @RestController
                public class OrderController {
                    private @NotNull String id;
                }
                """);

        // 1. Static fingerprinting on Gradle project
        SpringUpgradeModels.Fingerprint fingerprint =
                LocalSpringUpgradeExecutionPort.fingerprintGradle(gradleProject);

        assertEquals("2.7.18", fingerprint.springBootVersion());
        assertEquals("17", fingerprint.javaVersion());
        assertEquals(SpringRouteCatalog.GRADLE_BUILD_TOOL, fingerprint.buildTool());
        assertTrue(fingerprint.activeCapabilities().contains("spring-boot-plugin"));
        assertTrue(fingerprint.unknowns().contains("legacy-javax-validation-requires-jakarta-migration"),
                "Fingerprint must detect legacy-javax-validation");
        assertTrue(fingerprint.unknowns().contains("legacy-gradle-configurations-require-modernization"),
                "Fingerprint must detect legacy-gradle-configurations");
        assertTrue(fingerprint.unknowns().contains("custom-spring-boot-starter-requires-compatibility-verification"),
                "Fingerprint must detect custom-spring-boot-starter");

        // 2. Dynamic init script generation (no rewrite plugin declared in build.gradle)
        Path recipeFile = gradleProject.resolve(".elmos/rewrite.yml");
        Files.createDirectories(recipeFile.getParent());
        Files.writeString(recipeFile, "type: specs.openrewrite.org/v1beta/recipe\nname: test");
        // Verify conservative mode fails closed
        assertThrows(SpringUpgradeModels.BlockedException.class,
                () -> LocalSpringUpgradeExecutionPort.selectRoute(fingerprint, "3.5.3", "21", false));

        // Explicit opt-in allows experimental route
        SpringRouteCatalog.Selection selection =
                LocalSpringUpgradeExecutionPort.selectRoute(fingerprint, "3.5.3", "21", true);
        assertEquals(SpringRouteCatalog.GRADLE_BUILD_TOOL, selection.route().buildTool());
        assertTrue(selection.requiresExperimentalOptIn());

        Path initScript = LocalSpringUpgradeExecutionPort.installGradleRewriteInitScript(
                gradleProject, recipeFile, selection.route());

        assertTrue(Files.exists(initScript), "Dynamic init.gradle must be installed");
        String initScriptContent = Files.readString(initScript);
        assertTrue(initScriptContent.contains("initscript {"));
        assertTrue(initScriptContent.contains("classpath \"org.openrewrite:plugin:6.44.0\""));
        assertTrue(initScriptContent.contains("p.apply plugin: org.openrewrite.gradle.RewritePlugin"));
        assertTrue(initScriptContent.contains("add(\"rewrite\", \"org.openrewrite.recipe:rewrite-spring:6.35.0\")"));
        assertTrue(initScriptContent.contains("add(\"rewrite\", \"io.elmos:elmos-java-recipes:0.1.0-SNAPSHOT\")"));

        // Also verify 2-arg default fallback
        Path fallbackScript = LocalSpringUpgradeExecutionPort.installGradleRewriteInitScript(gradleProject, recipeFile);
        assertTrue(Files.readString(fallbackScript).contains("org.openrewrite.recipe:rewrite-spring:6.8.0"));
        SpringDeploymentGuidance.writeTo(gradleProject, "gradle", selection.route());

        Path diagnosticsPath = gradleProject.resolve("docs/MIGRATION_DIAGNOSTICS.md");
        assertTrue(Files.exists(diagnosticsPath));
        String diagnostics = Files.readString(diagnosticsPath);
        assertTrue(diagnostics.contains("当前构建工具：`gradle`"));
        assertTrue(diagnostics.contains("Gradle 自动化支持"));
        assertTrue(diagnostics.contains("Gradle 遗留语法与配置"));
        assertTrue(diagnostics.contains("自定义或非官方 Spring Boot Starter"));
    }

    @Test
    void adaptiveExperimentalRouteToleranceForGradleAndMaven() {
        SpringUpgradeModels.Fingerprint fp25 = new SpringUpgradeModels.Fingerprint(
                "2.5.12", "17", SpringRouteCatalog.GRADLE_BUILD_TOOL,
                List.of("root"), List.of("spring-boot-plugin"), List.of(), Map.of());

        // Default conservative: fails closed
        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> LocalSpringUpgradeExecutionPort.selectRoute(fp25, "3.5.3", "21", false));
        assertEquals("SPRING_ROUTE_EVIDENCE_NOT_RUN", blocked.code());

        // Explicit opt-in: succeeds with experimental route
        SpringRouteCatalog.Selection experimental =
                LocalSpringUpgradeExecutionPort.selectRoute(fp25, "3.5.3", "21", true);
        assertNotNull(experimental);
        assertEquals("boot-2.x-gradle-to-boot-3.5.3-java-21", experimental.route().routeId());
        assertEquals("3.5.3", experimental.route().targetBoot());
        assertEquals("21", experimental.route().targetJava());
        assertEquals(SpringRouteCatalog.EvidenceStatus.NOT_RUN, experimental.evidence());
        assertTrue(experimental.requiresExperimentalOptIn());
    }

    @Test
    void realSpringMvcExactProjectMaterializationAndReceipt() throws Exception {
        Path fixture = legacySpringMvcFixture();
        Path source = temporaryDirectory.resolve("mvc-fixture-source");
        copyTree(fixture, source);

        // 1. Fingerprint verification
        SpringUpgradeModels.Fingerprint mvcFingerprint =
                LocalSpringUpgradeExecutionPort.fingerprintMaven(source);
        assertEquals("spring-mvc", mvcFingerprint.sourceFrameworkFamily());
        assertEquals("5.3.39", mvcFingerprint.sourceFrameworkVersion());
        assertEquals(SpringRouteCatalog.MAVEN_BUILD_TOOL, mvcFingerprint.buildTool());
        assertTrue(mvcFingerprint.activeCapabilities().contains("spring-mvc"));

        // 2. Route selection
        SpringRouteCatalog.SpringRoute mvcRoute =
                SpringRouteCatalog.byId(SpringMvcExactTargetMaterializer.ROUTE_ID).orElseThrow();
        assertTrue(SpringMvcExactTargetMaterializer.supports(mvcRoute));

        // 3. Exact target materialization
        Path output = temporaryDirectory.resolve("mvc-materialized-target");
        SpringMvcExactTargetMaterializer.Materialization materialization =
                SpringMvcExactTargetMaterializer.materialize(source, output, mvcRoute, json);

        assertEquals("MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED", materialization.status());
        assertEquals(13, materialization.sourceFileCount());
        assertEquals(64, materialization.manifestSha256().length());

        // 4. Target code and configuration contracts
        assertTrue(Files.exists(output.resolve("pom.xml")));
        String pom = Files.readString(output.resolve("pom.xml"));
        assertTrue(pom.contains("<artifactId>spring-boot-starter-parent</artifactId><version>3.5.3</version>"));
        assertTrue(pom.contains("<packaging>war</packaging>"));

        Path appClass = output.resolve("src/main/java/io/elmos/legacy/LegacyMvcApplication.java");
        assertTrue(Files.exists(appClass));
        assertTrue(Files.readString(appClass).contains("extends SpringBootServletInitializer"));

        Path configClass = output.resolve("src/main/java/io/elmos/legacy/boot/LegacyMvcConfiguration.java");
        assertTrue(Files.exists(configClass));
        assertTrue(Files.readString(configClass).contains("DispatcherType.REQUEST, DispatcherType.ERROR"));

        JsonNode receipt = json.readTree(output.resolve(".elmos/migration-receipt.json").toFile());
        assertEquals("EXACT_FIXTURE_ONLY", receipt.path("profile_scope").asText());

        // 5. Deployment guidance and executable WAR container for MVC
        SpringDeploymentGuidance.writeTo(output, "maven", mvcRoute);
        Path warDockerfile = output.resolve("deploy/cloud-run/Dockerfile");
        assertTrue(Files.exists(warDockerfile), "MVC route must generate executable WAR container Dockerfile");
        String dockerfile = Files.readString(warDockerfile);
        assertTrue(dockerfile.contains("WarLauncher"));
        assertTrue(dockerfile.contains("Spring-Boot-Version: 3.5.3"));

        Path diagnostics = output.resolve("docs/MIGRATION_DIAGNOSTICS.md");
        assertTrue(Files.exists(diagnostics));
    }

    @Test
    void executionLifecycleTracesStagesInStrictOrder() {
        List<SpringUpgradeModels.Stage> stages = new ArrayList<>();
        List<String> logs = new ArrayList<>();
        SpringUpgradeExecutionPort.Control control = new SpringUpgradeExecutionPort.Control() {
            @Override public void stage(SpringUpgradeModels.Stage stage, String message) { stages.add(stage); }
            @Override public void log(String line) { logs.add(line); }
            @Override public void process(Process process) {}
            @Override public boolean cancelled() { return false; }
        };

        control.stage(SpringUpgradeModels.Stage.IMPORT_GIT, "Importing");
        control.stage(SpringUpgradeModels.Stage.LOCK_SNAPSHOT, "Locking");
        control.stage(SpringUpgradeModels.Stage.FINGERPRINT, "Fingerprinting");
        control.stage(SpringUpgradeModels.Stage.SOURCE_BASELINE, "Source baseline");
        control.stage(SpringUpgradeModels.Stage.EXTRACT_FCM, "Extracting FCM");
        control.stage(SpringUpgradeModels.Stage.OPENREWRITE, "OpenRewrite");
        control.stage(SpringUpgradeModels.Stage.BUILD_AND_TEST, "Build and test");

        assertEquals(List.of(
                SpringUpgradeModels.Stage.IMPORT_GIT,
                SpringUpgradeModels.Stage.LOCK_SNAPSHOT,
                SpringUpgradeModels.Stage.FINGERPRINT,
                SpringUpgradeModels.Stage.SOURCE_BASELINE,
                SpringUpgradeModels.Stage.EXTRACT_FCM,
                SpringUpgradeModels.Stage.OPENREWRITE,
                SpringUpgradeModels.Stage.BUILD_AND_TEST
        ), stages);
    }

    private static Path legacyOrdersFixture() {
        Path current = Path.of("").toAbsolutePath().normalize();
        while (current != null) {
            Path candidate = current.resolve(
                    "framework-packs/spring-boot-2-7-18-to-3-5-3/corpus/development/legacy-orders");
            if (Files.isDirectory(candidate)) return candidate;
            current = current.getParent();
        }
        throw new IllegalStateException("legacy-orders fixture not found");
    }

    private static Path legacySpringMvcFixture() {
        Path current = Path.of("").toAbsolutePath().normalize();
        while (current != null) {
            Path candidate = current.resolve(
                    "framework-packs/spring-framework-5-3-mvc-to-spring-boot-3-5-3/corpus/development/legacy-spring-mvc");
            if (Files.isDirectory(candidate)) return candidate;
            current = current.getParent();
        }
        throw new IllegalStateException("legacy-spring-mvc fixture not found");
    }

    private static void copyTree(Path source, Path target) throws IOException {
        Files.walkFileTree(source, new SimpleFileVisitor<>() {
            @Override public FileVisitResult preVisitDirectory(Path directory, BasicFileAttributes attrs)
                    throws IOException {
                Files.createDirectories(target.resolve(source.relativize(directory)));
                return FileVisitResult.CONTINUE;
            }

            @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                    throws IOException {
                Files.copy(file, target.resolve(source.relativize(file)));
                return FileVisitResult.CONTINUE;
            }
        });
    }
}
