-- ELMOS Product B37A: exact evidence projection generated from the commercial specification.
-- This migration records readiness and evidence only; external operations remain NOT_RUN.

DO $$
DECLARE
    target record;
BEGIN
    FOR target IN SELECT * FROM (VALUES
        ('artifact', 'content_objects'),
        ('artifact', 'content_object_locations'),
        ('artifact', 'content_object_integrity'),
        ('artifact', 'artifacts'),
        ('artifact', 'artifact_versions'),
        ('artifact', 'artifact_types'),
        ('artifact', 'artifact_type_versions'),
        ('artifact', 'artifact_media_types'),
        ('artifact', 'artifact_classifications'),
        ('artifact', 'artifact_owners'),
        ('artifact', 'artifact_relationships'),
        ('artifact', 'artifact_relationship_versions'),
        ('artifact', 'artifact_lifecycle_events'),
        ('artifact', 'artifact_authorization_decisions'),
        ('artifact', 'artifact_findings'),
        ('evidence', 'producers'),
        ('evidence', 'producer_versions'),
        ('evidence', 'producer_capabilities'),
        ('evidence', 'schema_registry'),
        ('evidence', 'schema_versions'),
        ('evidence', 'schema_compatibility_rules'),
        ('evidence', 'ingestion_requests'),
        ('evidence', 'ingestion_batches'),
        ('evidence', 'ingestion_items'),
        ('evidence', 'ingestion_results'),
        ('evidence', 'ingestion_idempotency'),
        ('evidence', 'ingestion_failures'),
        ('evidence', 'producer_conformance_results'),
        ('attestation', 'predicate_types'),
        ('attestation', 'predicate_type_versions'),
        ('attestation', 'attestation_statements'),
        ('attestation', 'attestation_subjects'),
        ('attestation', 'attestation_predicates'),
        ('attestation', 'attestation_envelopes'),
        ('attestation', 'attestation_signatures'),
        ('attestation', 'attestation_extensions'),
        ('attestation', 'attestation_supersessions'),
        ('attestation', 'attestation_revocations'),
        ('attestation', 'attestation_validation_results'),
        ('signing', 'signing_providers'),
        ('signing', 'signing_profiles'),
        ('signing', 'signing_profile_versions'),
        ('signing', 'signer_identities'),
        ('signing', 'signing_key_references'),
        ('signing', 'signing_key_versions'),
        ('signing', 'signing_requests'),
        ('signing', 'signing_results'),
        ('signing', 'sigstore_bundles'),
        ('signing', 'timestamp_authorities'),
        ('signing', 'transparency_log_profiles'),
        ('signing', 'transparency_log_entries'),
        ('signing', 'trust_roots'),
        ('signing', 'trust_root_versions'),
        ('signing', 'trust_root_distributions'),
        ('signing', 'signer_revocations'),
        ('signing', 'signing_findings'),
        ('provenance', 'source_provenance_records'),
        ('provenance', 'source_revision_evidence'),
        ('provenance', 'source_control_profiles'),
        ('provenance', 'build_provenance_records'),
        ('provenance', 'build_definitions'),
        ('provenance', 'build_run_details'),
        ('provenance', 'builders'),
        ('provenance', 'builder_versions'),
        ('provenance', 'resolved_dependencies'),
        ('provenance', 'external_parameters'),
        ('provenance', 'internal_parameters'),
        ('provenance', 'slsa_level_assessments'),
        ('provenance', 'slsa_verified_properties'),
        ('provenance', 'slsa_verification_runs'),
        ('provenance', 'slsa_vsa_records'),
        ('provenance', 'provenance_findings'),
        ('sbom', 'sbom_profiles'),
        ('sbom', 'sbom_documents'),
        ('sbom', 'sbom_document_versions'),
        ('sbom', 'sbom_generation_runs'),
        ('sbom', 'sbom_components'),
        ('sbom', 'sbom_component_versions'),
        ('sbom', 'sbom_component_identifiers'),
        ('sbom', 'sbom_relationships'),
        ('sbom', 'sbom_licenses'),
        ('sbom', 'sbom_suppliers'),
        ('sbom', 'sbom_hashes'),
        ('sbom', 'sbom_evidence'),
        ('sbom', 'sbom_completeness'),
        ('sbom', 'sbom_merge_runs'),
        ('sbom', 'sbom_conflicts'),
        ('sbom', 'sbom_quality_results'),
        ('sbom', 'sbom_exports'),
        ('sbom', 'sbom_findings'),
        ('oci', 'registry_profiles'),
        ('oci', 'registry_profile_versions'),
        ('oci', 'registry_capabilities'),
        ('oci', 'registry_repositories'),
        ('oci', 'registry_artifacts'),
        ('oci', 'registry_manifests'),
        ('oci', 'registry_descriptors'),
        ('oci', 'registry_referrers'),
        ('oci', 'registry_publications'),
        ('oci', 'registry_discovery_runs'),
        ('oci', 'registry_fallback_indexes'),
        ('oci', 'registry_findings'),
        ('evidence', 'claims'),
        ('evidence', 'claim_versions'),
        ('evidence', 'claim_subjects'),
        ('evidence', 'claim_objects'),
        ('evidence', 'claim_producers'),
        ('evidence', 'claim_evidence_links'),
        ('evidence', 'observations'),
        ('evidence', 'inferences'),
        ('evidence', 'inference_rules'),
        ('evidence', 'lineage_relations'),
        ('evidence', 'projection_offsets'),
        ('evidence', 'projection_runs'),
        ('evidence', 'graph_findings'),
        ('verification', 'policies'),
        ('verification', 'policy_versions'),
        ('verification', 'policy_expectations'),
        ('verification', 'trust_profiles'),
        ('verification', 'trusted_signers'),
        ('verification', 'trusted_builders'),
        ('verification', 'trusted_verifiers'),
        ('verification', 'verification_requests'),
        ('verification', 'verification_runs'),
        ('verification', 'verification_inputs'),
        ('verification', 'verification_checks'),
        ('verification', 'verification_results'),
        ('verification', 'verification_explanations'),
        ('verification', 'verification_cache'),
        ('verification', 'reverification_jobs'),
        ('verification', 'vsa_issuances'),
        ('verification', 'findings'),
        ('retention', 'retention_profiles'),
        ('retention', 'retention_profile_versions'),
        ('retention', 'retention_assignments'),
        ('retention', 'object_lock_profiles'),
        ('retention', 'object_lock_capabilities'),
        ('retention', 'object_lock_records'),
        ('retention', 'legal_holds'),
        ('retention', 'legal_hold_scopes'),
        ('retention', 'legal_hold_events'),
        ('retention', 'retention_extensions'),
        ('retention', 'disposition_requests'),
        ('retention', 'disposition_reviews'),
        ('retention', 'disposition_decisions'),
        ('retention', 'disposition_executions'),
        ('retention', 'deletion_receipts'),
        ('retention', 'retention_findings'),
        ('evidence', 'evidence_pack_profiles'),
        ('evidence', 'evidence_packs'),
        ('evidence', 'evidence_pack_versions'),
        ('evidence', 'evidence_pack_items'),
        ('evidence', 'evidence_pack_manifests'),
        ('evidence', 'evidence_pack_signatures'),
        ('evidence', 'evidence_pack_encryption'),
        ('evidence', 'evidence_pack_exports'),
        ('evidence', 'evidence_pack_imports'),
        ('evidence', 'evidence_pack_verification_runs'),
        ('evidence', 'evidence_pack_disclosure_decisions'),
        ('evidence', 'evidence_pack_findings'),
        ('privacy', 'evidence_classification_profiles'),
        ('privacy', 'evidence_classification_rules'),
        ('privacy', 'evidence_scanning_runs'),
        ('privacy', 'evidence_scan_findings'),
        ('privacy', 'redaction_profiles'),
        ('privacy', 'redaction_rules'),
        ('privacy', 'redaction_runs'),
        ('privacy', 'redaction_results'),
        ('privacy', 'pseudonymization_profiles'),
        ('privacy', 'disclosure_profiles'),
        ('privacy', 'disclosure_decisions'),
        ('privacy', 'source_locality_policies'),
        ('privacy', 'source_locality_decisions'),
        ('privacy', 'evidence_privacy_events')
    ) AS listed(schema_name, table_name)
    LOOP
        EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', target.schema_name);
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'domain_run_id varchar(160) NOT NULL,' ||
            'subject_digest varchar(64) NOT NULL CHECK (subject_digest ~ ''^[0-9a-f]{64}$''),' ||
            'context_snapshot_digest varchar(64) NOT NULL CHECK (context_snapshot_digest ~ ''^[0-9a-f]{64}$''),' ||
            'policy_version varchar(96) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''NOT_RUN'' CHECK (status IN (''OBSERVED'',''VERIFIED'',''FAILED'',''NOT_RUN'',''INCONCLUSIVE'',''UNKNOWN'',''BLOCKED'',''READY_FOR_EXTERNAL_GATE'',''READY_FOR_HUMAN_DECISION'')),' ||
            'independent_verifier_id varchar(160),' ||
            'critical_open_risks integer NOT NULL DEFAULT 0 CHECK (critical_open_risks >= 0),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'human_approval_ref varchar(512),' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (status <> ''READY_FOR_HUMAN_DECISION'' OR (independent_verifier_id IS NOT NULL AND critical_open_risks = 0 AND jsonb_array_length(evidence_refs) > 0)),' ||
            'CHECK (human_approval_ref IS NULL OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, idempotency_key))',
            target.schema_name, target.table_name);
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I.%I (organization_id, domain_run_id, status)',
            'idx_' || left(target.table_name, 32) || '_' || substr(md5(target.schema_name || target.table_name), 1, 8),
            target.schema_name, target.table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target.schema_name, target.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target.schema_name, target.table_name);
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = target.schema_name AND tablename = target.table_name AND policyname = 'product_b37a_tenant_isolation'
        ) THEN
            EXECUTE format(
                'CREATE POLICY product_b37a_tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
                target.schema_name, target.table_name);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger trigger
            JOIN pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = target.schema_name AND relation.relname = target.table_name
              AND trigger.tgname = 'product_b37a_append_only' AND NOT trigger.tgisinternal
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER product_b37a_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target.schema_name, target.table_name);
        END IF;
    END LOOP;
END;
$$;
