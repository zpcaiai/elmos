-- ELMOS Batch 20: Enterprise Integration and Middleware Modernization Engine.
-- Physical V21 is used because V20 already belongs to the enterprise commercial loop.
-- Batch 7/13/16 remain authoritative for message_contracts, message_contract_versions,
-- file_contracts and message_brokers; this migration extends rather than duplicates them.

DO $$
DECLARE
    table_name text;
    integration_tables text[] := ARRAY[
        'integration_estates','integration_platforms','integration_runtimes','integration_applications','integration_environment_profiles',
        'integration_endpoints','api_endpoints','message_endpoints','file_endpoints','partner_endpoints',
        'integration_routes','integration_route_steps','integration_route_conditions','integration_transformations','integration_adapters','integration_protocol_bindings',
        'queue_managers','message_queues','message_topics','message_exchanges','message_bindings','topic_partitions','consumer_groups','message_subscriptions',
        'event_contracts','command_contracts','partner_contracts','schema_versions',
        'message_envelopes','message_header_definitions','correlation_policies','delivery_policies','ordering_policies','retry_policies','dead_letter_policies',
        'api_gateways','api_routes','api_route_versions','gateway_policies','api_products','api_consumers',
        'trading_partners','partner_agreements','partner_certificates','edi_documents','edi_transaction_sets','edi_mappings','as2_agreements','as2_transfers','as2_receipts','mft_routes','mft_transfers',
        'workflow_definitions','workflow_versions','workflow_steps','workflow_transitions','workflow_timers','workflow_compensations','workflow_instances',
        'integration_target_profiles','integration_migration_plans','integration_migration_steps','parallel_bridges','integration_cutover_plans','integration_decommission_plans',
        'integration_runtime_observations','message_lag_samples','message_delivery_results','dead_letter_records','integration_replay_runs'
    ];
BEGIN
    FOREACH table_name IN ARRAY integration_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'integration_estate_ref varchar(255),' ||
            'integration_platform_ref varchar(255),' ||
            'environment_ref varchar(255),' ||
            'route_ref varchar(255),' ||
            'endpoint_ref varchar(255),' ||
            'contract_ref varchar(255),' ||
            'partner_ref varchar(255),' ||
            'workflow_ref varchar(255),' ||
            'repository_snapshot_ref varchar(255),' ||
            'source_artifact_ref varchar(512),' ||
            'runtime_artifact_ref varchar(512),' ||
            'engine_version varchar(64) NOT NULL DEFAULT ''1.0.0'',' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'status varchar(64) NOT NULL DEFAULT ''DISCOVERED'',' ||
            'external_ref varchar(512),' ||
            'idempotency_key varchar(160),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, integration_estate_ref)', 'idx_' || table_name || '_estate', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

ALTER TABLE message_brokers
    ADD COLUMN IF NOT EXISTS integration_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS integration_platform_ref varchar(255),
    ADD COLUMN IF NOT EXISTS broker_semantics varchar(64),
    ADD COLUMN IF NOT EXISTS runtime_artifact_ref varchar(512);
ALTER TABLE message_contracts
    ADD COLUMN IF NOT EXISTS integration_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS owner_ref varchar(255),
    ADD COLUMN IF NOT EXISTS contract_type varchar(32),
    ADD COLUMN IF NOT EXISTS delivery_policy_ref varchar(255),
    ADD COLUMN IF NOT EXISTS business_semantic_hash varchar(64),
    ADD CONSTRAINT message_contract_business_semantic_hash CHECK (business_semantic_hash IS NULL OR business_semantic_hash ~ '^[0-9a-f]{64}$');
ALTER TABLE message_contract_versions
    ADD COLUMN IF NOT EXISTS integration_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS registry_subject_ref varchar(255),
    ADD COLUMN IF NOT EXISTS compatibility_mode varchar(32),
    ADD COLUMN IF NOT EXISTS generated_code_hash varchar(64);
ALTER TABLE file_contracts
    ADD COLUMN IF NOT EXISTS integration_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS partner_ref varchar(255),
    ADD COLUMN IF NOT EXISTS atomic_delivery_policy varchar(64),
    ADD COLUMN IF NOT EXISTS checksum_policy varchar(64);

ALTER TABLE integration_routes
    ADD COLUMN route_key varchar(255), ADD COLUMN route_version varchar(64), ADD COLUMN stateful boolean NOT NULL DEFAULT false,
    ADD COLUMN dynamic_resolution_status varchar(32) NOT NULL DEFAULT 'UNRESOLVED',
    ADD CONSTRAINT integration_route_resolution CHECK (dynamic_resolution_status IN ('STATIC_RESOLVED','CONFIG_RESOLVED','RUNTIME_OBSERVED','PARTIAL','UNRESOLVED'));
ALTER TABLE integration_route_steps
    ADD COLUMN sequence_number integer, ADD COLUMN step_kind varchar(32), ADD COLUMN business_logic boolean NOT NULL DEFAULT false;
ALTER TABLE message_topics
    ADD COLUMN topic_name varchar(255), ADD COLUMN cluster_ref varchar(255), ADD COLUMN partition_count integer,
    ADD COLUMN key_contract_ref varchar(255), ADD COLUMN retention_policy_ref varchar(255), ADD COLUMN compaction_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE consumer_groups
    ADD COLUMN consumer_group_id varchar(255), ADD COLUMN broker_ref varchar(255), ADD COLUMN owner_ref varchar(255),
    ADD COLUMN observed_active boolean NOT NULL DEFAULT false, ADD COLUMN offset_frontier_ref varchar(255);
ALTER TABLE delivery_policies
    ADD COLUMN delivery_semantics varchar(64) NOT NULL DEFAULT 'UNKNOWN', ADD COLUMN idempotency_boundary varchar(255),
    ADD CONSTRAINT integration_delivery_semantics CHECK (delivery_semantics IN ('AT_MOST_ONCE','AT_LEAST_ONCE','BROKER_TRANSACTIONAL','EXACTLY_ONCE_WITHIN_PLATFORM','EFFECTIVELY_ONCE_WITH_IDEMPOTENCY','END_TO_END_VERIFIED','UNKNOWN'));
ALTER TABLE partner_agreements
    ADD COLUMN agreement_version varchar(64), ADD COLUMN protocol varchar(32), ADD COLUMN transport_ack_policy varchar(255),
    ADD COLUMN business_ack_policy varchar(255), ADD COLUMN certificate_overlap_required boolean NOT NULL DEFAULT true;
ALTER TABLE schema_versions
    ADD COLUMN subject_ref varchar(255), ADD COLUMN schema_version_ref varchar(64), ADD COLUMN registry_provider varchar(64),
    ADD COLUMN compatibility_mode varchar(32), ADD COLUMN business_semantic_status varchar(32) NOT NULL DEFAULT 'INCONCLUSIVE';
ALTER TABLE workflow_definitions
    ADD COLUMN workflow_key varchar(255), ADD COLUMN process_type varchar(64), ADD COLUMN executability varchar(32);
ALTER TABLE parallel_bridges
    ADD COLUMN bridge_type varchar(64), ADD COLUMN source_platform_ref varchar(255), ADD COLUMN target_platform_ref varchar(255),
    ADD COLUMN message_identity_preserved boolean NOT NULL DEFAULT false, ADD COLUMN expires_at timestamptz;
ALTER TABLE integration_cutover_plans
    ADD COLUMN producer_status varchar(64), ADD COLUMN consumer_status varchar(64), ADD COLUMN partner_status varchar(64),
    ADD COLUMN workflow_status varchar(64), ADD COLUMN backlog_status varchar(64), ADD COLUMN rollback_feasible boolean NOT NULL DEFAULT false;
ALTER TABLE integration_decommission_plans
    ADD COLUMN producers_zero boolean NOT NULL DEFAULT false, ADD COLUMN consumers_zero boolean NOT NULL DEFAULT false,
    ADD COLUMN partner_traffic_zero boolean NOT NULL DEFAULT false, ADD COLUMN workflow_instances_zero boolean NOT NULL DEFAULT false,
    ADD COLUMN backlog_zero_or_archived boolean NOT NULL DEFAULT false, ADD COLUMN credentials_revoked boolean NOT NULL DEFAULT false,
    ADD COLUMN certificates_revoked boolean NOT NULL DEFAULT false, ADD COLUMN config_archived boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX uq_integration_route_identity ON integration_routes
    (organization_id, integration_estate_ref, route_key, route_version) WHERE route_key IS NOT NULL AND route_version IS NOT NULL;
CREATE UNIQUE INDEX uq_message_topic_identity ON message_topics
    (organization_id, integration_estate_ref, cluster_ref, topic_name) WHERE cluster_ref IS NOT NULL AND topic_name IS NOT NULL;
CREATE UNIQUE INDEX uq_consumer_group_identity ON consumer_groups
    (organization_id, integration_estate_ref, broker_ref, consumer_group_id) WHERE broker_ref IS NOT NULL AND consumer_group_id IS NOT NULL;
CREATE UNIQUE INDEX uq_partner_agreement_identity ON partner_agreements
    (organization_id, integration_estate_ref, partner_ref, agreement_version) WHERE partner_ref IS NOT NULL AND agreement_version IS NOT NULL;
CREATE UNIQUE INDEX uq_schema_version_identity ON schema_versions
    (organization_id, integration_estate_ref, subject_ref, schema_version_ref) WHERE subject_ref IS NOT NULL AND schema_version_ref IS NOT NULL;

CREATE TRIGGER integration_runtime_observations_append_only BEFORE UPDATE OR DELETE ON integration_runtime_observations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER message_lag_samples_append_only BEFORE UPDATE OR DELETE ON message_lag_samples FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER message_delivery_results_append_only BEFORE UPDATE OR DELETE ON message_delivery_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER dead_letter_records_append_only BEFORE UPDATE OR DELETE ON dead_letter_records FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER integration_replay_runs_append_only BEFORE UPDATE OR DELETE ON integration_replay_runs FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER integration_migration_steps_append_only BEFORE UPDATE OR DELETE ON integration_migration_steps FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER parallel_bridges_append_only BEFORE UPDATE OR DELETE ON parallel_bridges FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER integration_cutover_plans_append_only BEFORE UPDATE OR DELETE ON integration_cutover_plans FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER integration_decommission_plans_append_only BEFORE UPDATE OR DELETE ON integration_decommission_plans FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER as2_transfers_append_only BEFORE UPDATE OR DELETE ON as2_transfers FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER as2_receipts_append_only BEFORE UPDATE OR DELETE ON as2_receipts FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mft_transfers_append_only BEFORE UPDATE OR DELETE ON mft_transfers FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER workflow_instances_append_only BEFORE UPDATE OR DELETE ON workflow_instances FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER api_route_versions_append_only BEFORE UPDATE OR DELETE ON api_route_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER schema_versions_append_only BEFORE UPDATE OR DELETE ON schema_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
