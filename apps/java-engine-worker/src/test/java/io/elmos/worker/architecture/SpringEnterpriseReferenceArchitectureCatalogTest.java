package io.elmos.worker.architecture;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SpringEnterpriseReferenceArchitectureCatalogTest {

    @Test
    void testAllBlueprintsRegistered() {
        List<SpringEnterpriseReferenceArchitectureCatalog.ArchitectureBlueprint> blueprints =
                SpringEnterpriseReferenceArchitectureCatalog.getAllBlueprints();

        assertEquals(5, blueprints.size(), "All 5 enterprise archetypes must be registered");

        for (var bp : blueprints) {
            assertNotNull(bp.title());
            assertNotNull(bp.description());
            assertTrue(bp.securityFilterChainTemplate().contains("SecurityFilterChain"));
            assertTrue(bp.persistenceModelTemplate().contains("jakarta.persistence") || bp.persistenceModelTemplate().contains("Entity"));
            assertNotNull(bp.resilienceConfigurationTemplate());
            assertFalse(bp.keyMigrationMilestones().isEmpty());
            assertFalse(bp.recommendedProperties().isEmpty());
        }
    }

    @Test
    void testBankingBlueprintDetails() {
        var bp = SpringEnterpriseReferenceArchitectureCatalog.getBlueprint(
                SpringEnterpriseReferenceArchitectureCatalog.EnterpriseArchetype.BANKING_CORE_LEDGER);

        assertNotNull(bp);
        assertTrue(bp.securityFilterChainTemplate().contains("bankingSecurityFilterChain"));
        assertTrue(bp.persistenceModelTemplate().contains("@JdbcTypeCode(SqlTypes.JSON)"));
        assertTrue(bp.resilienceConfigurationTemplate().contains("@CircuitBreaker"));
        assertTrue(bp.cloudIntegrationTemplate().contains("@LoadBalancerClient"));
    }
}
