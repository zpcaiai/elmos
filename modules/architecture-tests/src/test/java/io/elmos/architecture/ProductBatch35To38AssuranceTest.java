package io.elmos.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class ProductBatch35To38AssuranceTest {
    private final Path root = Path.of(System.getProperty("basedir")).resolve("../..").normalize();

    @Test void productAndMigrationPackNamespacesRemainExplicitlySeparate() throws IOException {
        String agents = Files.readString(root.resolve("AGENTS.md"));
        String adr = Files.readString(root.resolve("docs/adr/ADR-0058-product-b35-b38-trust-plane-separation.md"));
        String manifest = Files.readString(root.resolve("docs/product-batches33-38/skill-source-manifest.json"));
        String completeManifest = Files.readString(root.resolve(
                "docs/product-batches34-38-complete/skill-source-manifest.json"));
        String batch39Manifest = Files.readString(root.resolve(
                "docs/product-batches39-complete/skill-source-manifest.json"));
        for (String content : List.of(agents, adr, manifest, completeManifest)) {
            assertTrue(content.contains("Product Batch"));
            assertTrue(content.contains("Migration Pack M35-M45") || content.contains("M35-M45"));
        }
        assertTrue(batch39Manifest.contains("Product Batch"));
        assertTrue(batch39Manifest.contains("Migration Pack M39 Global SRE"));
        assertEquals(208, Pattern.compile("\"family\": \"elmos-product-commercialization\"").matcher(manifest).results().count());
        assertEquals(188, Pattern.compile("\"family\": \"elmos-product-commercialization-complete\"")
                .matcher(completeManifest).results().count());
        assertTrue(completeManifest.contains("\"canonical_product_skill_count_with_legacy_b33_b38\": 291"));
        assertTrue(completeManifest.contains("\"superseded_legacy_record_count\": 105"));
        assertEquals(48, Pattern.compile("\"family\": \"elmos-product-commercialization-b39-complete\"")
                .matcher(batch39Manifest).results().count());
        assertTrue(batch39Manifest.contains("\"canonical_product_skill_count_with_prior_families\": 339"));
        assertTrue(manifest.contains("\"external_execution_evidence\": \"NOT_RUN\""));
        assertTrue(completeManifest.contains("\"external_execution_evidence\": \"NOT_RUN\""));
        assertTrue(batch39Manifest.contains("\"external_execution_evidence\": \"NOT_RUN\""));
    }

    @Test void fourProductDomainsArePureFailClosedAdmissionModules() throws IOException {
        for (String module : List.of("source-control-workspace-governance", "secure-execution-plane",
                "evidence-assurance-fabric", "continuous-authorization")) {
            Path source = root.resolve("modules").resolve(module).resolve("src/main/java");
            String production;
            try (var files = Files.walk(source)) {
                production = files.filter(path -> path.toString().endsWith(".java")).map(path -> {
                    try { return Files.readString(path); }
                    catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                }).collect(Collectors.joining("\n"));
            }
            assertTrue(production.contains("BLOCKED"));
            assertTrue(production.contains("externalOperationExecuted"));
            assertFalse(production.contains("ProcessBuilder"));
            assertFalse(production.contains("Runtime.getRuntime"));
            assertFalse(production.contains("HttpClient"));
            assertFalse(production.contains("java.sql"));
        }
    }

    @Test void exactProductDatabaseInventoriesAreTenantIsolatedAppendOnlyAndNonExecuting() throws IOException {
        Path migrations = root.resolve("modules/persistence/src/main/resources/db/migration");
        var expected = List.of(
                new Migration("V42__product_source_control_and_workspace.sql", 279),
                new Migration("V43__product_secure_execution_plane.sql", 419),
                new Migration("V44__product_artifact_evidence_fabric.sql", 174),
                new Migration("V45__product_external_evidence_producers.sql", 146),
                new Migration("V46__product_assurance_analytics.sql", 214),
                new Migration("V47__product_continuous_authorization.sql", 185));
        long total = 0;
        for (Migration migration : expected) {
            String sql = Files.readString(migrations.resolve(migration.file()));
            long declared = Pattern.compile("\\('[a-z_]+', '[a-z0-9_]+'\\)").matcher(sql).results().count();
            assertEquals(migration.tables(), declared, migration.file());
            assertTrue(sql.contains("FORCE ROW LEVEL SECURITY"));
            assertTrue(sql.contains("external_operation_executed = false"));
            assertTrue(sql.contains("elmos_forbid_append_only_mutation"));
            assertTrue(sql.contains("independent_verifier_id"));
            assertFalse(sql.contains("secret_value"));
            total += declared;
        }
        assertEquals(1417, total);
    }

    @Test void apiNeverClaimsExternalExecutionApprovalOrCertification() throws IOException {
        String controller = Files.readString(root.resolve(
                "apps/control-plane/src/main/java/io/elmos/controlplane/ProductCommercializationController.java"));
        assertTrue(controller.contains("externalExecutionEvidence\", \"NOT_RUN"));
        assertTrue(controller.contains("Product Batch B35-B38"));
        assertFalse(controller.contains("certified\", true"));
        assertFalse(controller.contains("externalOperationExecuted\", true"));
    }

    private record Migration(String file, int tables) {}
}
