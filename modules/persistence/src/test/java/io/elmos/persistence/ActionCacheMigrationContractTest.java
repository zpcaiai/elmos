package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ActionCacheMigrationContractTest {

    private static String migration() throws Exception {
        Path root = Path.of(System.getProperty("basedir"), "src", "main", "resources",
                "db", "migration");
        return Files.readString(root.resolve("V67__durable_action_cache_index.sql"));
    }

    @Test void legacyIncompleteRowsAreInvalidatedRatherThanServedWithInventedMetadata()
            throws Exception {
        String v67 = migration();
        assertTrue(v67.contains("V67_METADATA_SCHEMA_UPGRADE"));
        assertTrue(v67.contains("WHERE invalidated_at IS NULL"));
        assertTrue(v67.contains("cas_action_active_metadata_complete"));
        assertTrue(v67.contains("invalidated_at IS NOT NULL OR"));
        assertTrue(v67.contains("action_component_names"));
        assertTrue(v67.contains("provenance_digest_bytes"));
        assertTrue(v67.contains("result_schema_version"));
        assertTrue(v67.contains("ALTER TABLE cas_action_cache_entries NO FORCE ROW LEVEL SECURITY"));
        assertTrue(v67.contains("ALTER TABLE cas_action_cache_entries FORCE ROW LEVEL SECURITY"));
    }

    @Test void durableInvalidationsAndQuarantinesAreTenantIsolated() throws Exception {
        String v67 = migration();
        assertTrue(v67.contains("CREATE TABLE cas_action_cache_invalidations"));
        assertTrue(v67.contains("CREATE TABLE cas_action_cache_quarantined_nodes"));
        assertTrue(v67.contains("cas_action_cache_invalidations_append_only"));
        assertTrue(v67.contains("ENABLE ROW LEVEL SECURITY"));
        assertTrue(v67.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(v67.contains("current_setting(''app.organization_id'', true)"));
        assertTrue(v67.contains("cas_b67_tenant_isolation"));
    }

    @Test void everyPersistedDigestCarriesItsExactByteSize() throws Exception {
        String v67 = migration();
        for (String column : new String[]{"action_key_bytes", "provenance_digest_bytes",
                "stdout_digest_bytes", "stderr_digest_bytes",
                "producer_provenance_digest_bytes", "attestation_signature_bytes",
                "attestation_envelope_bytes"}) {
            assertTrue(v67.contains(column), column + " is not persisted");
        }
        assertTrue(v67.contains("cas_action_attestation_complete_shape"));
        assertTrue(v67.contains("cas_action_attestation_envelope_hex"));
        assertTrue(v67.contains("cas_action_producer_provenance_shape"));
        assertTrue(v67.contains("cas_action_active_arrays_have_no_null_elements"));
        assertTrue(v67.contains("array_position(action_component_names, NULL) IS NULL"));
        assertTrue(v67.contains("array_position(producer_permission_scope, NULL) IS NULL"));
        assertTrue(v67.contains("array_position(cost_values, NULL) IS NULL"));
    }

    @Test void trustDecisionsArePersistedExactlyInsteadOfInventedDuringReadback()
            throws Exception {
        String v67 = migration();
        assertTrue(v67.contains("ADD COLUMN writer_attested boolean"));
        assertTrue(v67.contains("ADD COLUMN attestation_algorithm varchar(64)"));
        assertTrue(v67.contains("ADD COLUMN attestation_envelope_version varchar(64)"));
        assertTrue(v67.contains("ADD COLUMN attestation_envelope_hex varchar(64)"));
        assertTrue(v67.contains("ADD COLUMN attestation_envelope_bytes bigint"));
        assertTrue(v67.contains("ADD COLUMN attestation_signed_at_epoch_millis bigint"));
        assertTrue(v67.contains("ADD COLUMN attestation_verified boolean"));
        assertTrue(v67.contains("cas_action_attestation_complete_shape"));
        assertTrue(v67.contains("cas_action_attestation_supported_envelope_version"));
        assertTrue(v67.contains("attestation_envelope_version = 'elmos-result-signature/2'"));
        assertTrue(v67.contains("cas_action_active_writer_attested"));
        assertTrue(v67.contains("cas_action_active_high_risk_verified"));
        assertTrue(v67.contains("attestation_verified IS TRUE"));
    }

    @Test void resourceUsageKeepsDoublePrecisionAndRejectsNonFiniteActiveRows()
            throws Exception {
        String v67 = migration();
        assertTrue(v67.contains("ALTER COLUMN wall_seconds TYPE double precision"));
        assertTrue(v67.contains("ALTER COLUMN cpu_seconds TYPE double precision"));
        assertTrue(v67.contains("ADD COLUMN max_memory_mb double precision"));
        assertTrue(v67.contains("ADD COLUMN gpu_seconds double precision"));
        assertTrue(v67.contains("cas_action_active_resource_usage_finite"));
        assertTrue(v67.contains("array_position(cost_values, 'NaN'::double precision) IS NULL"));
    }
}
