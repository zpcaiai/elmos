-- ELMOS Batch 14: frontend and client modernization projections.
-- Source execution remains in the isolated TypeScript worker and capability-matched Runners.

DO $$
DECLARE
    table_name text;
    client_tables text[] := ARRAY[
        'client_applications','client_application_versions','client_platforms','client_runtime_profiles','browser_support_profiles',
        'frontend_workspaces','frontend_packages','frontend_package_dependencies','frontend_entry_points','frontend_build_targets','frontend_build_results','frontend_bundles','frontend_bundle_chunks',
        'frontend_routes','frontend_route_edges','frontend_route_guards','frontend_screens','frontend_pages','frontend_components','frontend_component_dependencies','frontend_dynamic_components',
        'frontend_state_stores','frontend_state_slices','frontend_state_transitions','frontend_side_effects','frontend_event_handlers',
        'user_journeys','user_journey_steps','user_interactions','form_contracts','form_validation_rules',
        'design_systems','design_tokens','design_token_versions','design_components','design_component_versions','component_mappings','component_adoption_records',
        'client_api_contracts','bff_contracts','bff_operations','authentication_flows','authorization_ui_rules','client_storage_contracts',
        'visual_baselines','visual_scenarios','visual_snapshots','visual_differences','visual_approvals',
        'accessibility_profiles','accessibility_scenarios','accessibility_runs','accessibility_findings','keyboard_flow_results','focus_flow_results','screen_reader_reviews',
        'desktop_capabilities','desktop_integrations','desktop_packaging_results',
        'mobile_capabilities','mobile_permissions','mobile_deep_links','mobile_push_contracts','mobile_offline_stores','mobile_release_results',
        'client_release_plans','client_release_stages','client_release_cohorts','client_cutover_decisions','client_stability_observations','client_decommission_plans'
    ];
BEGIN
    FOREACH table_name IN ARRAY client_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),' ||
            'repository_snapshot_ref varchar(255),' ||
            'client_application_ref varchar(255),' ||
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
            'UNIQUE (organization_id, idempotency_key))', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id)', 'idx_' || table_name || '_org', table_name);
        EXECUTE format('CREATE INDEX %I ON %I (organization_id, client_application_ref)',
            'idx_' || table_name || '_client', table_name);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name);
    END LOOP;
END;
$$;

CREATE TRIGGER client_application_versions_append_only BEFORE UPDATE OR DELETE ON client_application_versions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER frontend_build_results_append_only BEFORE UPDATE OR DELETE ON frontend_build_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER visual_snapshots_append_only BEFORE UPDATE OR DELETE ON visual_snapshots
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER visual_differences_append_only BEFORE UPDATE OR DELETE ON visual_differences
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER visual_approvals_append_only BEFORE UPDATE OR DELETE ON visual_approvals
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER accessibility_runs_append_only BEFORE UPDATE OR DELETE ON accessibility_runs
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER accessibility_findings_append_only BEFORE UPDATE OR DELETE ON accessibility_findings
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER keyboard_flow_results_append_only BEFORE UPDATE OR DELETE ON keyboard_flow_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER focus_flow_results_append_only BEFORE UPDATE OR DELETE ON focus_flow_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER screen_reader_reviews_append_only BEFORE UPDATE OR DELETE ON screen_reader_reviews
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER desktop_packaging_results_append_only BEFORE UPDATE OR DELETE ON desktop_packaging_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER mobile_release_results_append_only BEFORE UPDATE OR DELETE ON mobile_release_results
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER client_cutover_decisions_append_only BEFORE UPDATE OR DELETE ON client_cutover_decisions
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER client_stability_observations_append_only BEFORE UPDATE OR DELETE ON client_stability_observations
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
