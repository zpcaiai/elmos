package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Text contract for V65, in the same shape as the other migration contract tests: it runs without
 * Docker, so the boundaries it protects are checked on every build rather than only where
 * Testcontainers can start.
 *
 * <p>What it protects is the set of rules that are cheap to delete and expensive to lose: tenant
 * isolation, the append-only record of destructive work, and the constraints that stop an entry
 * the cache would never serve from existing as a row anyway.
 */
class CasMigrationContractTest {

    private static String migration() throws Exception {
        Path root = Path.of(System.getProperty("basedir"), "src", "main", "resources", "db", "migration");
        return Files.readString(root.resolve("V65_1__content_addressed_store_and_action_cache.sql"));
    }

    @Test void everyCasTableIsTenantIsolatedWithForcedRowLevelSecurity() throws Exception {
        String v65 = migration();
        assertTrue(v65.contains("ENABLE ROW LEVEL SECURITY"));
        assertTrue(v65.contains("FORCE ROW LEVEL SECURITY"),
                "without FORCE, the table owner bypasses its own isolation policy");
        assertTrue(v65.contains("current_setting(''app.organization_id'', true)"));
        assertTrue(v65.contains("cas_b65_tenant_isolation"));
        for (String table : new String[]{"cas_object_catalog", "cas_object_placement",
                "cas_action_cache_entries", "cas_reference_roots", "cas_upload_sessions",
                "cas_deletion_manifests", "cas_quarantine_events"}) {
            assertTrue(v65.contains("'" + table + "'"),
                    table + " is missing from the row level security loop");
            assertTrue(v65.contains("CREATE TABLE " + table), table + " is not created");
        }
    }

    @Test void destructiveRecordsAreAppendOnly() throws Exception {
        String v65 = migration();
        assertTrue(v65.contains("CREATE TRIGGER cas_deletion_manifests_append_only BEFORE UPDATE OR DELETE"));
        assertTrue(v65.contains("CREATE TRIGGER cas_quarantine_events_append_only BEFORE UPDATE OR DELETE"));
        assertTrue(v65.contains("EXECUTE FUNCTION elmos_forbid_append_only_mutation()"));
    }

    @Test void digestColumnsRefuseAnythingThatIsNotLowercaseSha256() throws Exception {
        String v65 = migration();
        int shapeChecks = v65.split("~ '\\^\\[0-9a-f\\]\\{64\\}\\$'", -1).length - 1;
        assertTrue(shapeChecks >= 10,
                "expected every digest column to carry a shape check, found " + shapeChecks);
        assertTrue(v65.contains("size_bytes >= 0"));
    }

    @Test void theActionCacheCannotHoldAnEntryTheCacheWouldRefuseToServe() throws Exception {
        String v65 = migration();
        assertTrue(v65.contains("cas_action_cache_high_risk_signed"),
                "a high-risk result must not exist unsigned even if the service layer is bypassed");
        assertTrue(v65.contains("cas_action_cache_success_has_zero_exit"));
        assertTrue(v65.contains("cas_action_cache_failure_is_classified"));
        assertTrue(v65.contains("cas_action_cache_failure_ttl"));
        assertTrue(v65.contains("failure_class IN ('CODE', 'POLICY', 'SECURITY')"),
                "only failures that are deterministic given the inputs may be cached");
        assertTrue(v65.contains("cas_action_cache_invalidation_has_reason"));
        assertTrue(v65.contains("toolchain_image ~ '@sha256:[0-9a-f]{64}$'"),
                "an entry keyed on a mutable tag is a stale hit waiting to happen");
    }

    @Test void placementAndProvenanceBoundariesAreEnforcedByTheSchema() throws Exception {
        String v65 = migration();
        assertTrue(v65.contains("cas_object_placement_single_primary_uq"));
        assertTrue(v65.contains("WHERE placement_role = 'PRIMARY'"));
        assertTrue(v65.contains("cas_object_catalog_shared_needs_provenance"));
        assertTrue(v65.contains("REFERENCES cas_object_catalog (organization_id, digest_hex)"));
    }

    @Test void theSweepAndCollectionPathsHaveSupportingIndexes() throws Exception {
        String v65 = migration();
        assertTrue(v65.contains("CREATE INDEX cas_object_catalog_collection_idx"));
        assertTrue(v65.contains("CREATE INDEX cas_action_cache_expiry_idx"));
        assertTrue(v65.contains("CREATE INDEX cas_action_cache_node_idx"),
                "quarantining a node must not require a sequential scan of the cache");
        assertTrue(v65.contains("CREATE INDEX cas_upload_sessions_sweep_idx"));
        assertTrue(v65.contains("CREATE INDEX cas_reference_roots_digest_idx"));
    }
}
