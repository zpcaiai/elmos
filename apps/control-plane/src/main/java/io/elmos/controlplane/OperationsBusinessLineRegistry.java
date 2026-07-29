package io.elmos.controlplane;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Canonical control-plane route ownership. Longest prefixes are declared first.
 */
final class OperationsBusinessLineRegistry {
    private static final Map<String, String> ROUTES = new LinkedHashMap<>();

    static {
        ROUTES.put("/api/v1/operations-observability", "ADMIN_OPERATIONS");
        ROUTES.put("/api/v1/repository-workspaces", "REPOSITORY_WORKSPACE");
        ROUTES.put("/api/v1/repository-snapshots", "REPOSITORY_WORKSPACE");
        ROUTES.put("/api/v1/github", "REPOSITORY_WORKSPACE");
        ROUTES.put("/api/webhooks/github", "REPOSITORY_WORKSPACE");
        ROUTES.put("/api/v1/migration-pack-certification", "MIGRATION_GOVERNANCE");
        ROUTES.put("/api/v1/database-data", "DATABASE_DATA");
        ROUTES.put("/api/v1/frontend-client", "CLIENT_MODERNIZATION");
        ROUTES.put("/api/v1/infrastructure", "CLOUD_INFRASTRUCTURE");
        ROUTES.put("/api/v1/security-compliance", "SECURITY_COMPLIANCE");
        ROUTES.put("/api/v1/test-quality", "SKILLS_QUALIFICATION");
        ROUTES.put("/api/v1/delivery", "DELIVERY_GOVERNANCE");
        ROUTES.put("/api/v1/product-commercialization", "COMMERCIALIZATION");
        ROUTES.put("/api/v1/product-roadmap", "COMMERCIALIZATION");
        ROUTES.put("/api/v1/mainframe", "MAINFRAME_MODERNIZATION");
        ROUTES.put("/api/v1/integration", "SYSTEM_INTEGRATION");
        ROUTES.put("/api/v1/composite", "SYSTEM_INTEGRATION");
        ROUTES.put("/api/v1/enterprise-suite", "ENTERPRISE_MODERNIZATION");
        ROUTES.put("/api/v1/domain-governance", "ENTERPRISE_MODERNIZATION");
        ROUTES.put("/api/v1/demo-runs", "PRODUCT_OVERVIEW");
    }

    private OperationsBusinessLineRegistry() {}

    static String classify(String path) {
        if (path == null) return "PRODUCT_OVERVIEW";
        return ROUTES.entrySet().stream()
                .filter(entry -> path.startsWith(entry.getKey()))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElse("PRODUCT_OVERVIEW");
    }

    static Map<String, String> routes() {
        return Map.copyOf(ROUTES);
    }
}
