-- ELMOS Batch 17: horizontal security and compliance modernization projections.
-- Organization, identity, secret lease/reference, risk exception/acceptance, authorization,
-- workflow, evidence, audit, billing, and delivery authorities remain shared.
-- Secret values, private keys, scanner credentials, and raw sensitive payloads are forbidden.

DO $$
DECLARE
    table_name text;
    security_tables text[] := ARRAY[
        'security_estates','security_assets','security_asset_versions','security_boundaries','security_trust_zones','security_trust_relationships','attack_surfaces',
        'security_identities','human_identities','device_identities','workload_identities','privileged_identities','authentication_factors',
        'access_policies','access_policy_versions','access_decisions',
        'secret_assets','secret_rotation_records','cryptographic_assets','certificate_assets','certificate_lifecycle_events','crypto_policies','crypto_inventory_snapshots',
        'security_requirements','security_requirement_versions','security_controls','security_control_parameters','control_implementations','control_implementation_versions','control_assessments','control_evidence_links',
        'software_components','sbom_documents','sbom_components','sbom_relationships','sbom_completeness_results','provenance_statements','supply_chain_attestations','vex_statements','supply_chain_policy_results',
        'security_tools','security_tool_versions','security_scans','security_scan_targets','security_findings','security_finding_locations','security_finding_evidence',
        'vulnerabilities','vulnerability_aliases','vulnerability_affected_assets','vulnerability_exposures','exploitability_assessments','vulnerability_risk_decisions','vulnerability_remediations',
        'cloud_security_findings','kubernetes_security_findings','runtime_security_events','security_detections','security_detection_rules','incident_scenarios','incident_readiness_results',
        'data_protection_policies','data_processing_activities','data_flows','privacy_risks','encryption_assignments','tokenization_policies','masking_policies','dlp_policies',
        'threat_models','threat_model_versions','threat_model_assets','threats','abuse_cases','attack_paths','security_assumptions','security_mitigations',
        'compliance_catalogs','compliance_catalog_versions','compliance_profiles','compliance_controls','control_crosswalks','control_scope_assignments',
        'oscal_catalog_artifacts','oscal_profile_artifacts','oscal_component_definitions','oscal_system_security_plans','oscal_assessment_plans','oscal_assessment_results','oscal_poam_artifacts',
        'authorization_boundaries','authorization_packages','continuous_monitoring_plans','continuous_monitoring_events'
    ];
BEGIN
    FOREACH table_name IN ARRAY security_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'security_estate_ref varchar(255),' ||
            'authorization_boundary_ref varchar(255),' ||
            'source_commit varchar(128),' ||
            'artifact_digest varchar(255),' ||
            'deployment_revision varchar(255),' ||
            'security_profile varchar(64) NOT NULL DEFAULT ''BASELINE'',' ||
            'engine_version varchar(64) NOT NULL DEFAULT ''1.0.0'',' ||
            'schema_version varchar(32) NOT NULL DEFAULT ''1.0'',' ||
            'status varchar(64) NOT NULL DEFAULT ''CREATED'',' ||
            'external_ref varchar(255),' ||
            'idempotency_key varchar(160),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{64}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (security_profile IN (''BASELINE'',''STANDARD'',''HIGH_ASSURANCE'',''REGULATED'',''CRITICAL_SYSTEM'')),' ||
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, security_estate_ref)', 'idx_' || table_name || '_estate', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

-- Extend shared authorities rather than introducing a second identity, secret, risk, or authorization source of truth.
ALTER TABLE service_identities
    ADD COLUMN IF NOT EXISTS workload_identity_ref varchar(255),
    ADD COLUMN IF NOT EXISTS security_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE secret_references
    ADD COLUMN IF NOT EXISTS security_estate_ref varchar(255),
    ADD COLUMN IF NOT EXISTS secret_fingerprint varchar(255),
    ADD COLUMN IF NOT EXISTS exposure_status varchar(64),
    ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE secret_leases
    ADD COLUMN IF NOT EXISTS workload_identity_ref varchar(255),
    ADD COLUMN IF NOT EXISTS rotation_record_ref varchar(255),
    ADD COLUMN IF NOT EXISTS security_evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE risk_exceptions
    ADD COLUMN IF NOT EXISTS security_finding_ref varchar(255),
    ADD COLUMN IF NOT EXISTS compensating_control_ref varchar(255),
    ADD COLUMN IF NOT EXISTS reassessment_trigger jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE risk_acceptances
    ADD COLUMN IF NOT EXISTS authorization_boundary_ref varchar(255),
    ADD COLUMN IF NOT EXISTS qualified_human_approver varchar(255),
    ADD COLUMN IF NOT EXISTS security_evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE authorization_decisions
    ADD COLUMN IF NOT EXISTS authorization_boundary_ref varchar(255),
    ADD COLUMN IF NOT EXISTS artifact_digest varchar(255),
    ADD COLUMN IF NOT EXISTS deployment_revision varchar(255),
    ADD COLUMN IF NOT EXISTS valid_until timestamptz,
    ADD COLUMN IF NOT EXISTS internal_decision_only boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS external_certification_granted boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS security_evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD CONSTRAINT authorization_decisions_no_external_certification CHECK (external_certification_granted = false);

CREATE INDEX IF NOT EXISTS idx_service_identities_security_estate ON service_identities (organization_id, security_estate_ref);
CREATE INDEX IF NOT EXISTS idx_secret_references_security_estate ON secret_references (organization_id, security_estate_ref);
CREATE INDEX IF NOT EXISTS idx_risk_exceptions_security_finding ON risk_exceptions (organization_id, security_finding_ref);
CREATE INDEX IF NOT EXISTS idx_authorization_decisions_security_boundary ON authorization_decisions (organization_id, authorization_boundary_ref);

CREATE TRIGGER security_asset_versions_append_only BEFORE UPDATE OR DELETE ON security_asset_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER access_policy_versions_append_only BEFORE UPDATE OR DELETE ON access_policy_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER access_decisions_security_append_only BEFORE UPDATE OR DELETE ON access_decisions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER secret_rotation_records_append_only BEFORE UPDATE OR DELETE ON secret_rotation_records FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER certificate_lifecycle_events_append_only BEFORE UPDATE OR DELETE ON certificate_lifecycle_events FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER crypto_inventory_snapshots_append_only BEFORE UPDATE OR DELETE ON crypto_inventory_snapshots FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER security_requirement_versions_append_only BEFORE UPDATE OR DELETE ON security_requirement_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER control_implementation_versions_append_only BEFORE UPDATE OR DELETE ON control_implementation_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER control_assessments_append_only BEFORE UPDATE OR DELETE ON control_assessments FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER sbom_documents_append_only BEFORE UPDATE OR DELETE ON sbom_documents FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER provenance_statements_append_only BEFORE UPDATE OR DELETE ON provenance_statements FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER supply_chain_attestations_append_only BEFORE UPDATE OR DELETE ON supply_chain_attestations FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER vex_statements_append_only BEFORE UPDATE OR DELETE ON vex_statements FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER security_scans_append_only BEFORE UPDATE OR DELETE ON security_scans FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER security_finding_evidence_append_only BEFORE UPDATE OR DELETE ON security_finding_evidence FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER vulnerability_risk_decisions_append_only BEFORE UPDATE OR DELETE ON vulnerability_risk_decisions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER runtime_security_events_append_only BEFORE UPDATE OR DELETE ON runtime_security_events FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER threat_model_versions_append_only BEFORE UPDATE OR DELETE ON threat_model_versions FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER oscal_assessment_results_append_only BEFORE UPDATE OR DELETE ON oscal_assessment_results FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER authorization_packages_append_only BEFORE UPDATE OR DELETE ON authorization_packages FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER continuous_monitoring_events_append_only BEFORE UPDATE OR DELETE ON continuous_monitoring_events FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
