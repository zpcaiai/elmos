-- V67 makes cas_action_cache_entries a complete, replayable ActionCache.Entry index.
--
-- V65 deliberately created the authorization-critical table early, but it did not persist the
-- ActionKey components or enough digest/resource metadata to reconstruct the Java record without
-- inventing values. Existing rows are therefore invalidated instead of being read with fabricated
-- zero sizes. A cache miss is safe; a false hit is not.

-- V65 forces RLS even for the table owner.  Flyway's schema owner must temporarily bypass the
-- tenant policy while it invalidates every legacy row; otherwise an unset app.organization_id
-- makes this upgrade silently touch no rows.  The migration is transactional and restores FORCE
-- before it can commit.
ALTER TABLE cas_action_cache_entries NO FORCE ROW LEVEL SECURITY;

UPDATE cas_action_cache_entries
SET invalidated_at = coalesce(invalidated_at, now()),
    invalidation_reason = coalesce(invalidation_reason, 'V67_METADATA_SCHEMA_UPGRADE')
WHERE invalidated_at IS NULL;

-- The Java contract uses IEEE-754 doubles. V65's numeric(...,3) columns silently rounded a
-- result before a second process reconstructed it, so even a legitimate hit was not an exact
-- ActionCache.Entry. Legacy rows are already invalidated above; new rows use float8 and reject
-- every non-finite value below.
ALTER TABLE cas_action_cache_entries
    ALTER COLUMN wall_seconds TYPE double precision
        USING wall_seconds::double precision,
    ALTER COLUMN cpu_seconds TYPE double precision
        USING cpu_seconds::double precision;

ALTER TABLE cas_action_cache_entries
    ADD COLUMN action_key_bytes bigint,
    ADD COLUMN action_component_names text[],
    ADD COLUMN action_component_values text[],
    ADD COLUMN result_schema_version varchar(16),
    ADD COLUMN result_started_at varchar(64),
    ADD COLUMN result_finished_at varchar(64),
    ADD COLUMN failure_message text,
    ADD COLUMN provenance_digest_bytes bigint,
    ADD COLUMN stdout_digest_bytes bigint,
    ADD COLUMN stderr_digest_bytes bigint,
    ADD COLUMN producer_provenance_digest_hex varchar(64),
    ADD COLUMN producer_provenance_digest_bytes bigint,
    ADD COLUMN writer_attested boolean,
    ADD COLUMN attestation_algorithm varchar(64),
    ADD COLUMN attestation_signature_bytes bigint,
    ADD COLUMN attestation_envelope_version varchar(64),
    ADD COLUMN attestation_envelope_hex varchar(64),
    ADD COLUMN attestation_envelope_bytes bigint,
    ADD COLUMN attestation_signed_at_epoch_millis bigint,
    ADD COLUMN attestation_verified boolean,
    ADD COLUMN max_memory_mb double precision,
    ADD COLUMN read_bytes bigint,
    ADD COLUMN written_bytes bigint,
    ADD COLUMN gpu_seconds double precision,
    ADD COLUMN cost_names text[],
    ADD COLUMN cost_values double precision[];

ALTER TABLE cas_action_cache_entries
    ADD CONSTRAINT cas_action_key_bytes_nonnegative
        CHECK (action_key_bytes IS NULL OR action_key_bytes >= 0),
    ADD CONSTRAINT cas_action_components_same_length
        CHECK (action_component_names IS NULL OR action_component_values IS NULL
               OR cardinality(action_component_names) = cardinality(action_component_values)),
    ADD CONSTRAINT cas_action_provenance_bytes_nonnegative
        CHECK (provenance_digest_bytes IS NULL OR provenance_digest_bytes >= 0),
    ADD CONSTRAINT cas_action_stdout_bytes_nonnegative
        CHECK (stdout_digest_bytes IS NULL OR stdout_digest_bytes >= 0),
    ADD CONSTRAINT cas_action_stderr_bytes_nonnegative
        CHECK (stderr_digest_bytes IS NULL OR stderr_digest_bytes >= 0),
    ADD CONSTRAINT cas_action_producer_provenance_shape
        CHECK ((producer_provenance_digest_hex IS NULL) =
               (producer_provenance_digest_bytes IS NULL)),
    ADD CONSTRAINT cas_action_producer_provenance_hex
        CHECK (producer_provenance_digest_hex IS NULL
               OR producer_provenance_digest_hex ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT cas_action_producer_provenance_bytes_nonnegative
        CHECK (producer_provenance_digest_bytes IS NULL OR producer_provenance_digest_bytes >= 0),
    ADD CONSTRAINT cas_action_attestation_complete_shape CHECK (
        invalidated_at IS NOT NULL OR (
            (attestation_key_id IS NULL
             AND attestation_algorithm IS NULL
             AND attestation_signature_hex IS NULL
             AND attestation_signature_bytes IS NULL
             AND attestation_envelope_version IS NULL
             AND attestation_envelope_hex IS NULL
             AND attestation_envelope_bytes IS NULL
             AND attestation_signed_at_epoch_millis IS NULL
             AND attestation_verified IS NULL)
            OR
            (attestation_key_id IS NOT NULL
             AND attestation_algorithm IS NOT NULL
             AND attestation_signature_hex IS NOT NULL
             AND attestation_signature_bytes IS NOT NULL
             AND attestation_envelope_version IS NOT NULL
             AND attestation_envelope_hex IS NOT NULL
             AND attestation_envelope_bytes IS NOT NULL
             AND attestation_signed_at_epoch_millis IS NOT NULL
             AND attestation_verified IS TRUE)
        )
    ),
    ADD CONSTRAINT cas_action_attestation_supported_envelope_version
        CHECK (invalidated_at IS NOT NULL
               OR attestation_envelope_version IS NULL
               OR attestation_envelope_version = 'elmos-result-signature/2'),
    ADD CONSTRAINT cas_action_attestation_envelope_hex
        CHECK (attestation_envelope_hex IS NULL
               OR attestation_envelope_hex ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT cas_action_attestation_size_nonnegative
        CHECK (attestation_signature_bytes IS NULL OR attestation_signature_bytes >= 0),
    ADD CONSTRAINT cas_action_attestation_envelope_size_nonnegative
        CHECK (attestation_envelope_bytes IS NULL OR attestation_envelope_bytes >= 0),
    ADD CONSTRAINT cas_action_attestation_signed_at_nonnegative
        CHECK (attestation_signed_at_epoch_millis IS NULL
               OR attestation_signed_at_epoch_millis >= 0),
    ADD CONSTRAINT cas_action_active_writer_attested
        CHECK (invalidated_at IS NOT NULL OR writer_attested IS TRUE),
    ADD CONSTRAINT cas_action_active_high_risk_verified
        CHECK (invalidated_at IS NOT NULL OR risk_tier <> 'HIGH'
               OR attestation_verified IS TRUE),
    ADD CONSTRAINT cas_action_resource_usage_nonnegative
        CHECK ((max_memory_mb IS NULL OR max_memory_mb >= 0)
               AND (read_bytes IS NULL OR read_bytes >= 0)
               AND (written_bytes IS NULL OR written_bytes >= 0)
               AND (gpu_seconds IS NULL OR gpu_seconds >= 0)),
    ADD CONSTRAINT cas_action_active_resource_usage_finite CHECK (
        invalidated_at IS NOT NULL OR (
            wall_seconds <> 'NaN'::double precision
            AND wall_seconds < 'Infinity'::double precision
            AND cpu_seconds <> 'NaN'::double precision
            AND cpu_seconds < 'Infinity'::double precision
            AND max_memory_mb <> 'NaN'::double precision
            AND max_memory_mb < 'Infinity'::double precision
            AND gpu_seconds <> 'NaN'::double precision
            AND gpu_seconds < 'Infinity'::double precision
        )
    ),
    ADD CONSTRAINT cas_action_cost_same_length
        CHECK (cost_names IS NULL OR cost_values IS NULL
               OR cardinality(cost_names) = cardinality(cost_values)),
    -- PostgreSQL arrays may be non-null while still containing null elements. JDBC must never
    -- coerce such an element into the literal string "null", because that changes the signed/keyed
    -- metadata. Legacy rows remain retained only as invalidation evidence.
    ADD CONSTRAINT cas_action_active_arrays_have_no_null_elements CHECK (
        invalidated_at IS NOT NULL OR (
            array_position(action_component_names, NULL) IS NULL
            AND array_position(action_component_values, NULL) IS NULL
            AND array_position(producer_permission_scope, NULL) IS NULL
            AND array_position(cost_names, NULL) IS NULL
            AND array_position(cost_values, NULL) IS NULL
            AND array_position(cost_values, 'NaN'::double precision) IS NULL
            AND array_position(cost_values, 'Infinity'::double precision) IS NULL
            AND array_position(cost_values, '-Infinity'::double precision) IS NULL
        )
    ),
    -- Legacy rows are retained as invalidation evidence but can never be served. Every active row
    -- must contain enough data to rebuild the exact typed entry.
    ADD CONSTRAINT cas_action_active_metadata_complete CHECK (
        invalidated_at IS NOT NULL OR (
            action_key_bytes IS NOT NULL
            AND action_component_names IS NOT NULL
            AND action_component_values IS NOT NULL
            AND result_schema_version IS NOT NULL
            AND result_started_at IS NOT NULL
            AND result_finished_at IS NOT NULL
            AND provenance_digest_bytes IS NOT NULL
            AND writer_attested IS TRUE
            AND max_memory_mb IS NOT NULL
            AND read_bytes IS NOT NULL
            AND written_bytes IS NOT NULL
            AND gpu_seconds IS NOT NULL
            AND cost_names IS NOT NULL
            AND cost_values IS NOT NULL
            AND ((stdout_digest_hex IS NULL AND stdout_digest_bytes IS NULL)
                 OR (stdout_digest_hex IS NOT NULL AND stdout_digest_bytes IS NOT NULL))
            AND ((stderr_digest_hex IS NULL AND stderr_digest_bytes IS NULL)
                 OR (stderr_digest_hex IS NOT NULL AND stderr_digest_bytes IS NOT NULL))
        )
    );

ALTER TABLE cas_action_cache_entries FORCE ROW LEVEL SECURITY;

CREATE TABLE cas_action_cache_invalidations (
    organization_id varchar(64) NOT NULL,
    action_key_hex varchar(64) NOT NULL
        CHECK (action_key_hex ~ '^[0-9a-f]{64}$'),
    invalidated_at timestamptz NOT NULL,
    reason varchar(128) NOT NULL,
    writer_node_id varchar(256),
    PRIMARY KEY (organization_id, action_key_hex, invalidated_at)
);

CREATE TABLE cas_action_cache_quarantined_nodes (
    organization_id varchar(64) NOT NULL,
    writer_node_id varchar(256) NOT NULL,
    reason varchar(512) NOT NULL,
    quarantined_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, writer_node_id)
);

CREATE TRIGGER cas_action_cache_invalidations_append_only
BEFORE UPDATE OR DELETE ON cas_action_cache_invalidations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TRIGGER cas_action_cache_quarantined_nodes_append_only
BEFORE UPDATE OR DELETE ON cas_action_cache_quarantined_nodes
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

DO $$
DECLARE cas_table text;
BEGIN
    FOREACH cas_table IN ARRAY ARRAY[
        'cas_action_cache_invalidations', 'cas_action_cache_quarantined_nodes'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', cas_table);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', cas_table);
        EXECUTE format(
            'CREATE POLICY cas_b67_tenant_isolation ON public.%I '
            || 'USING (organization_id = current_setting(''app.organization_id'', true)) '
            || 'WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            cas_table);
    END LOOP;
END;
$$;
