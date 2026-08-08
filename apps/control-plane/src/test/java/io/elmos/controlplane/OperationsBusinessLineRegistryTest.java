package io.elmos.controlplane;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OperationsBusinessLineRegistryTest {
    @Test
    void classifiesEveryControlPlaneBusinessSurface() {
        Map<String, String> routes = OperationsBusinessLineRegistry.routes();
        assertTrue(routes.size() >= 20);
        for (Map.Entry<String, String> route : routes.entrySet()) {
            assertEquals(route.getValue(), OperationsBusinessLineRegistry.classify(route.getKey()));
        }
        assertEquals(
                "REPOSITORY_WORKSPACE",
                OperationsBusinessLineRegistry.classify("/api/v1/repository-workspaces/123/files"));
        assertEquals(
                "ADMIN_OPERATIONS",
                OperationsBusinessLineRegistry.classify("/api/v1/operations-observability/console"));
        assertEquals(
                "MIGRATION_GOVERNANCE",
                OperationsBusinessLineRegistry.classify("/api/v1/modernization-proof/jobs/123"));
        assertEquals(
                "COMMERCIALIZATION",
                OperationsBusinessLineRegistry.classify("/api/v1/tenant-quota/adjust"));
        assertEquals(
                "PRODUCT_OVERVIEW",
                OperationsBusinessLineRegistry.classify("/api/v1/future-capability"));
    }
}
