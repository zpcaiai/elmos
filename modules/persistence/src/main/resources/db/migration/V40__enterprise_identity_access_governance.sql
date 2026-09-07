-- ELMOS Product Batch 34: enterprise identity, multitenancy and access governance.
-- Records are evidence-bound and append-only. This schema does not execute external actions.

CREATE SCHEMA IF NOT EXISTS identity_access_governance;

DO $$
DECLARE
    target_schema text := 'identity_access_governance';
    table_name text;
    batch_tables text[] := ARRAY[
        'identity_providers',
        'identity_provider_versions',
        'federated_identities',
        'human_identities',
        'service_identities',
        'tenants',
        'organization_units',
        'tenant_hierarchies',
        'tenant_policies',
        'memberships',
        'invitations',
        'membership_events',
        'roles',
        'role_versions',
        'permissions',
        'role_permissions',
        'role_assignments',
        'sod_rules',
        'sod_conflicts',
        'resources',
        'resource_scopes',
        'resource_grants',
        'relationship_grants',
        'authorization_decisions',
        'authorization_conditions',
        'sessions',
        'authentication_events',
        'step_up_challenges',
        'workload_identities',
        'service_principals',
        'certificates',
        'machine_credentials',
        'privileged_access_requests',
        'privileged_grants',
        'break_glass_sessions',
        'access_reviews',
        'access_review_items',
        'certification_decisions',
        'entitlement_drifts',
        'identity_audit_events',
        'identity_security_incidents',
        'identity_corrections',
        'saml_connections',
        'saml_connection_versions',
        'saml_metadata_snapshots',
        'saml_attribute_mappings',
        'saml_certificates',
        'saml_replay_records',
        'saml_login_exchanges',
        'saml_authentication_events',
        'scim_connections',
        'scim_connection_versions',
        'scim_client_credentials',
        'scim_attribute_mappings',
        'scim_schema_extensions',
        'scim_users',
        'scim_groups',
        'scim_group_members',
        'scim_operations',
        'scim_operation_errors',
        'scim_idempotency_records',
        'scim_cursors',
        'scim_tombstones',
        'organization_unit_versions',
        'organization_closure',
        'organization_memberships',
        'organization_workspaces',
        'delegated_admin_scopes',
        'domain_claims',
        'organization_events',
        'external_groups',
        'external_group_versions',
        'external_group_members',
        'group_entitlement_mappings',
        'group_mapping_versions',
        'group_mapping_simulations',
        'group_mapping_approvals',
        'provisioned_entitlements',
        'entitlement_sources',
        'manual_entitlement_overrides',
        'offboarding_cases',
        'offboarding_steps',
        'offboarding_impacted_resources',
        'offboarding_ownership_transfers',
        'credential_revocation_jobs',
        'session_revocation_jobs',
        'offboarding_reconciliations',
        'identity_tombstones',
        'provisioning_jobs',
        'provisioning_operations',
        'provisioning_checkpoints',
        'reconciliation_runs',
        'reconciliation_findings',
        'entitlement_snapshots',
        'scim_event_feeds',
        'scim_event_deliveries',
        'scim_event_receipts',
        'trust_domains',
        'trust_domain_bundles',
        'trust_domain_federations',
        'workload_registrations',
        'workload_selectors',
        'workload_attestations',
        'workload_certificates',
        'workload_authorization_bindings',
        'workload_identity_events',
        'service_principal_versions',
        'oauth_clients',
        'oauth_client_authentication_methods',
        'machine_authorization_providers',
        'token_exchange_policies',
        'delegations',
        'delegation_chain_entries',
        'delegated_token_records',
        'token_status_observations',
        'token_exchange_events',
        'secret_providers',
        'secret_references',
        'machine_credential_versions',
        'secret_leases',
        'credential_rotation_policies',
        'credential_rotation_runs',
        'credential_revocations',
        'credential_usage_observations',
        'credential_compromise_findings',
        'token_introspection_records',
        'token_revocation_records',
        'privileged_access_profiles',
        'privileged_access_request_resources',
        'privileged_access_risk_assessments',
        'privileged_access_approvals',
        'privileged_grant_leases',
        'privileged_access_sessions',
        'privileged_access_actions',
        'privileged_access_expiry_jobs',
        'privileged_access_reviews',
        'break_glass_profiles',
        'break_glass_identities',
        'break_glass_requests',
        'break_glass_approvals',
        'break_glass_action_events',
        'break_glass_alerts',
        'break_glass_revocations',
        'break_glass_post_reviews',
        'break_glass_drills',
        'access_review_profiles',
        'access_review_campaigns',
        'access_review_scopes',
        'access_review_snapshots',
        'access_review_reviewers',
        'access_review_decisions',
        'access_review_remediations',
        'access_review_verifications',
        'access_review_exceptions',
        'access_review_events',
        'identity_incident_indicators',
        'identity_incident_subjects',
        'identity_incident_resources',
        'identity_incident_actions',
        'identity_containment_jobs',
        'credential_blast_radius_runs',
        'credential_dependency_edges',
        'identity_recovery_plans',
        'identity_recovery_runs',
        'identity_incident_reviews',
        'identity_security_drills'
    ];
BEGIN
    FOREACH table_name IN ARRAY batch_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'domain_run_id varchar(160) NOT NULL,' ||
            'snapshot_digest varchar(64) NOT NULL CHECK (snapshot_digest ~ ''^[0-9a-f]{64}$''),' ||
            'policy_version varchar(96) NOT NULL,' ||
            'human_owner_id varchar(160) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''NOT_RUN'' CHECK (status IN (''OBSERVED'',''NOT_RUN'',''INCONCLUSIVE'',''BLOCKED'',''READY_FOR_HUMAN_DECISION'')),' ||
            'independent_judge boolean NOT NULL DEFAULT false,' ||
            'critical_open_risks integer NOT NULL DEFAULT 0 CHECK (critical_open_risks >= 0),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'human_approval_ref varchar(512),' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (status <> ''READY_FOR_HUMAN_DECISION'' OR (independent_judge AND critical_open_risks = 0 AND jsonb_array_length(evidence_refs) > 0)),' ||
            'CHECK (human_approval_ref IS NULL OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, idempotency_key))',
            target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id, domain_run_id, status)',
                       'idx_' || left(table_name, 38) || '_roadmap_run', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            target_schema, table_name);
        EXECUTE format(
            'CREATE TRIGGER product_governance_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
            target_schema, table_name);
    END LOOP;
END;
$$;
