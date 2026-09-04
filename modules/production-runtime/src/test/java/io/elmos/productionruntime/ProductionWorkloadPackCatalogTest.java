package io.elmos.productionruntime;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import io.elmos.productionruntime.ProductionRuntimeModels.OutputVerificationReceipt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProductionWorkloadPackCatalogTest {
    @Test
    void bindsAllFourPackageWorkloadsWithoutGenericFallback() {
        assertEquals(4, ProductionWorkloadPackCatalog.all().size());
        assertEquals("spring-modernization-v1", ProductionWorkloadPackCatalog.require("SPRING_MODERNIZATION", List.of("inventory")).id());
        assertEquals("repository-language-conversion-v1", ProductionWorkloadPackCatalog.require("LANGUAGE_CONVERSION", List.of("inventory", "semantic-ir")).id());
        assertEquals("multilingual-project-generation-v1", ProductionWorkloadPackCatalog.require("PROJECT_GENERATION", List.of("requirements-normalization")).id());
        assertEquals("sql-dialect-routine-conversion-v1", ProductionWorkloadPackCatalog.require("SQL_CONVERSION", List.of("inventory-parse", "dependency-graph")).id());
    }

    @Test
    void rejectsUnknownOrOutOfOrderStages() {
        assertThrows(ProductionRuntimeException.class, () -> ProductionWorkloadPackCatalog.require("UNKNOWN", List.of("stage")));
        assertThrows(ProductionRuntimeException.class, () -> ProductionWorkloadPackCatalog.require("SQL_CONVERSION", List.of("target-compile", "inventory-parse")));
    }

    @Test
    void exposesTheCompleteOrderedStageContractForEachZipWorkload() {
        assertEquals(17, ProductionWorkloadPackCatalog.requireComplete("SPRING_MODERNIZATION").stages().size());
        assertEquals(13, ProductionWorkloadPackCatalog.requireComplete("LANGUAGE_CONVERSION").stages().size());
        assertEquals(12, ProductionWorkloadPackCatalog.requireComplete("PROJECT_GENERATION").stages().size());
        assertEquals(12, ProductionWorkloadPackCatalog.requireComplete("SQL_CONVERSION").stages().size());
        ProductionWorkloadPackCatalog.all().forEach(pack ->
                org.junit.jupiter.api.Assertions.assertFalse(pack.completionGates().isEmpty()));
    }

    @Test
    void acceptsOnlyDigestBoundOutputThatPassesEveryTypedGate() {
        OutputVerificationReceipt receipt = receipt("SQL_CONVERSION", "convert-query", Map.of(
                "target_compile_pass", true,
                "result_regression_pass", true,
                "constraint_semantics_preserved", true,
                "transaction_semantics_preserved", true,
                "unresolved_semantic_gaps", 0));

        ProductionWorkloadPackCatalog.verifyOutput(
                "SQL_CONVERSION", "convert-query", receipt);

        OutputVerificationReceipt missingRegression = receipt(
                "SQL_CONVERSION", "convert-query", Map.of(
                        "target_compile_pass", true,
                        "constraint_semantics_preserved", true,
                        "transaction_semantics_preserved", true,
                        "unresolved_semantic_gaps", 0));
        assertThrows(ProductionRuntimeException.class, () ->
                ProductionWorkloadPackCatalog.verifyOutput(
                        "SQL_CONVERSION", "convert-query", missingRegression));
        assertThrows(ProductionRuntimeException.class, () ->
                ProductionWorkloadPackCatalog.verifyOutput(
                        "SQL_CONVERSION", "different-work", receipt));
    }

    private static OutputVerificationReceipt receipt(
            String jobType,
            String workType,
            Map<String, Object> checks
    ) {
        String packId = ProductionWorkloadPackCatalog.requireComplete(jobType).id();
        return new OutputVerificationReceipt(
                OutputVerificationReceipt.SCHEMA_VERSION,
                packId,
                jobType,
                workType,
                "cas://sha256/" + "a".repeat(64),
                "a".repeat(64),
                "repository-owned-output-gate",
                "PASSED",
                "NOT_CERTIFIED",
                checks);
    }
}
