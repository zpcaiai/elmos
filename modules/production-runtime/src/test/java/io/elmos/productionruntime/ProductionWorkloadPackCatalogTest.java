package io.elmos.productionruntime;

import org.junit.jupiter.api.Test;

import java.util.List;

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
    }
}
