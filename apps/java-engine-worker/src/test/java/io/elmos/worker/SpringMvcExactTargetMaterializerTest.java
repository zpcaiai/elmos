package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringMvcExactTargetMaterializerTest {
    @TempDir Path temporaryDirectory;
    private final ObjectMapper json = new ObjectMapper();

    @Test void exactFixtureMaterializesBootWarAndRetainsEveryRuntimeGateAsNotRun()
            throws Exception {
        Path output = temporaryDirectory.resolve("target");

        SpringMvcExactTargetMaterializer.Materialization result =
                SpringMvcExactTargetMaterializer.materialize(
                        fixture(), output, exactRoute(), json);

        assertEquals("MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED", result.status());
        assertEquals(13, result.sourceFileCount());
        assertEquals(64, result.manifestSha256().length());
        assertTrue(Files.readString(output.resolve("pom.xml"))
                .contains("<artifactId>spring-boot-starter-parent</artifactId><version>3.5.3</version>"));
        assertTrue(Files.readString(output.resolve("pom.xml"))
                .contains("<packaging>war</packaging>"));
        assertTrue(Files.readString(output.resolve(
                        "src/main/java/io/elmos/legacy/LegacyMvcApplication.java"))
                .contains("extends SpringBootServletInitializer"));
        assertTrue(Files.readString(output.resolve(
                        "src/main/java/io/elmos/legacy/boot/LegacyMvcConfiguration.java"))
                .contains("DispatcherType.REQUEST, DispatcherType.ERROR"));
        assertTrue(Files.readString(output.resolve(
                        "src/main/java/io/elmos/legacy/boot/LegacyMvcConfiguration.java"))
                .contains("addPathPatterns(\"/api/**\")"));
        assertTrue(Files.readString(output.resolve(
                        "src/main/java/io/elmos/legacy/boot/LegacyMvcConfiguration.java"))
                .contains("configurer.enable()"));
        assertTrue(Files.readString(output.resolve("src/main/resources/application.properties"))
                .contains("management.endpoints.web.exposure.include=health"));
        assertTrue(Files.readString(output.resolve("src/main/resources/application.properties"))
                .contains("server.servlet.register-default-servlet=true"));
        assertFalse(Files.exists(output.resolve("src/main/webapp/WEB-INF/web.xml")));
        assertFalse(Files.exists(output.resolve(
                "src/main/resources/WEB-INF/spring/root-context.xml")));

        JsonNode receipt = json.readTree(
                output.resolve(".elmos/migration-receipt.json").toFile());
        assertEquals("EXACT_FIXTURE_ONLY", receipt.path("profile_scope").asText());
        assertEquals(13, receipt.path("validated_source_manifest").path("file_count").asInt());
        assertTrue(receipt.path("validated_source_manifest").path("complete_file_graph").asBoolean());
        assertEquals(13, receipt.path("source_inputs").size());
        receipt.path("execution").properties().forEach(entry ->
                assertEquals("NOT_RUN", entry.getValue().asText(), entry.getKey()));
        JsonNode generator = receipt.path("generator_binding");
        assertTrue(generator.path("materializer_contract_sha256").asText()
                .matches("[0-9a-f]{64}"));
        assertTrue(generator.path("input_manifest_sha256").asText()
                .matches("[0-9a-f]{64}"));
        assertTrue(generator.path("recipe_sha256").asText().matches("[0-9a-f]{64}"));
        JsonNode controlledProfiles = generator.path("controlled_target_profile_resources");
        assertTrue(controlledProfiles.isArray());
        assertEquals(2, controlledProfiles.size());
        assertEquals("classpath:/spring-mvc/target-profile/profile.json",
                controlledProfiles.get(0).path("resource").asText());
        assertEquals(3731, controlledProfiles.get(0).path("bytes").asLong());
        assertEquals("4856d1c012274be15fa9339a4a11524314994ca858e2b7856fcd367fb1de63a5",
                controlledProfiles.get(0).path("sha256").asText());
        assertEquals("classpath:/spring-mvc/target-profile/scaffold-manifest.json",
                controlledProfiles.get(1).path("resource").asText());
        assertEquals(1773, controlledProfiles.get(1).path("bytes").asLong());
        assertEquals("a2e741b1a535c690633b27e0301f6931ad287e2b0ddd3fefb97cb5194d5819d6",
                controlledProfiles.get(1).path("sha256").asText());
        JsonNode sourceMap = json.readTree(output.resolve(".elmos/source-map.json").toFile());
        assertEquals(6, sourceMap.path("mappings").size());
        sourceMap.path("mappings").forEach(mapping ->
                assertEquals(64, mapping.path("source_sha256").asText().length()));
    }

    @Test void changedSourceBytesFailClosedWithoutPublishingOutput() throws Exception {
        Path source = temporaryDirectory.resolve("source");
        copyTree(fixture(), source);
        Files.writeString(source.resolve("src/main/resources/legacy.properties"),
                "legacy.orders.currency=USD\nlegacy.orders.audit-header=X-Legacy-Audit\n");
        Path output = temporaryDirectory.resolve("target");

        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcExactTargetMaterializer.materialize(
                        source, output, exactRoute(), json));

        assertEquals("MVC_TARGET_SOURCE_DIGEST_MISMATCH", blocked.code());
        assertFalse(Files.exists(output));
    }

    @Test void anExtraSourceFileFailsTheCompleteGraphGate() throws Exception {
        Path source = temporaryDirectory.resolve("source");
        copyTree(fixture(), source);
        Files.writeString(source.resolve("unknown.txt"), "not admitted");

        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcExactTargetMaterializer.materialize(
                        source, temporaryDirectory.resolve("target"), exactRoute(), json));

        assertEquals("MVC_TARGET_SOURCE_GRAPH_MISMATCH", blocked.code());
    }

    @Test void existingOutputIsNeverOverwritten() throws Exception {
        Path output = temporaryDirectory.resolve("target");
        Files.createDirectories(output);
        Files.writeString(output.resolve("owned.txt"), "preserve");

        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcExactTargetMaterializer.materialize(
                        fixture(), output, exactRoute(), json));

        assertEquals("MVC_TARGET_OUTPUT_EXISTS", blocked.code());
        assertEquals("preserve", Files.readString(output.resolve("owned.txt")));
    }

    @Test void everyOtherCatalogRouteIsRejectedByTheExactMaterializer() {
        SpringRouteCatalog.SpringRoute bootRoute = SpringRouteCatalog.routes().stream()
                .filter(route -> route.sourceFamily() == SpringRouteCatalog.SourceFamily.SPRING_BOOT)
                .findFirst().orElseThrow();

        SpringUpgradeModels.BlockedException blocked = assertThrows(
                SpringUpgradeModels.BlockedException.class,
                () -> SpringMvcExactTargetMaterializer.materialize(
                        fixture(), temporaryDirectory.resolve("target"), bootRoute, json));

        assertEquals("MVC_TARGET_MATERIALIZER_ROUTE_UNSUPPORTED", blocked.code());
    }

    private static SpringRouteCatalog.SpringRoute exactRoute() {
        return SpringRouteCatalog.byId(SpringMvcExactTargetMaterializer.ROUTE_ID).orElseThrow();
    }

    private static Path fixture() {
        Path current = Path.of("").toAbsolutePath().normalize();
        while (current != null) {
            Path candidate = current.resolve(
                    "framework-packs/spring-framework-5-3-mvc-to-spring-boot-3-5-3/"
                            + "corpus/development/legacy-spring-mvc");
            if (Files.isDirectory(candidate)) return candidate;
            current = current.getParent();
        }
        throw new IllegalStateException("exact Spring MVC fixture not found from working directory");
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
