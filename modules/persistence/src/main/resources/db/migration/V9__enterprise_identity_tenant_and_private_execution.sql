-- ELMOS Batch 9: tenant, identity, policy, private execution, usage, audit and data lifecycle.
-- Tenant context is transaction scoped. Missing app.organization_id yields no RLS-visible rows.

ALTER TABLE organizations
    ADD COLUMN display_name varchar(255) NOT NULL DEFAULT 'Unconfigured Organization',
    ADD COLUMN status varchar(64) NOT NULL DEFAULT 'PROVISIONING',
    ADD COLUMN isolation_class varchar(64) NOT NULL DEFAULT 'T1_SHARED_SAAS',
    ADD COLUMN data_region varchar(64) NOT NULL DEFAULT 'local',
    ADD COLUMN encryption_context_id varchar(128) NOT NULL DEFAULT 'key-unconfigured',
    ADD COLUMN schema_version varchar(32) NOT NULL DEFAULT '1.0',
    ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

INSERT INTO organizations (organization_id, display_name, status, isolation_class, data_region, encryption_context_id)
VALUES ('org-system', 'ELMOS pre-tenant migration owner', 'ACTIVE', 'T3_DEDICATED_DEPLOYMENT', 'local', 'key-system');

CREATE TABLE organization_profiles (
    organization_profile_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE organization_settings (
    organization_setting_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE organization_domains (
    organization_domain_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE organization_memberships (
    organization_membership_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE organization_service_accounts (
    organization_service_account_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE tenant_isolation_profiles (
    tenant_isolation_profile_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE tenant_data_boundaries (
    tenant_data_boundary_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE tenant_encryption_contexts (
    tenant_encryption_context_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE identity_provider_connections (
    identity_provider_connection_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE identity_provider_domains (
    identity_provider_domain_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE federated_identities (
    federated_identity_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE user_identities (
    user_identity_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE authentication_sessions (
    authentication_session_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE authentication_events (
    authentication_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE service_identities (
    service_identity_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE service_credentials (
    service_credential_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE roles (
    role_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE permissions (
    permission_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE role_permissions (
    role_permission_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE role_bindings (
    role_binding_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE authorization_policies (
    authorization_policy_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE authorization_policy_versions (
    authorization_policy_version_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE authorization_decisions (
    authorization_decision_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE temporary_privileges (
    temporary_privilege_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE break_glass_grants (
    break_glass_grant_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_pools (
    runner_pool_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_nodes (
    runner_node_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_capabilities (
    runner_capability_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_enrollments (
    runner_enrollment_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_certificates (
    runner_certificate_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_heartbeats (
    runner_heartbeat_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_job_leases (
    runner_job_lease_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_job_events (
    runner_job_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE runner_attestations (
    runner_attestation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE secret_providers (
    secret_provider_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE secret_references (
    secret_reference_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE encryption_key_references (
    encryption_key_reference_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE key_rotation_events (
    key_rotation_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_providers (
    model_provider_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_endpoints (
    model_endpoint_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_profiles (
    model_profile_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_policy_profiles (
    model_policy_profile_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_routing_rules (
    model_routing_rule_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_routing_decisions (
    model_routing_decision_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_invocations (
    model_invocation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_usage_records (
    model_usage_record_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE model_evaluation_results (
    model_evaluation_result_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE quota_allocations (
    quota_allocation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE usage_events (
    usage_event_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE usage_reservations (
    usage_reservation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE usage_ledger_entries (
    usage_ledger_entry_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE credit_accounts (
    credit_account_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE credit_transactions (
    credit_transaction_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE billing_periods (
    billing_period_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE invoice_lines (
    invoice_line_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE cost_snapshots (
    cost_snapshot_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE audit_event_hashes (
    audit_event_hash_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE audit_chains (
    audit_chain_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE audit_exports (
    audit_export_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE audit_export_runs (
    audit_export_run_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE data_classification_policies (
    data_classification_policy_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE data_residency_policies (
    data_residency_policy_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE retention_policies (
    retention_policy_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE retention_assignments (
    retention_assignment_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE deletion_requests (
    deletion_request_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE deletion_tasks (
    deletion_task_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE legal_holds (
    legal_hold_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE data_inventory_entries (
    data_inventory_entry_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE deployment_installations (
    deployment_installation_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE installation_components (
    installation_component_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE offline_licenses (
    offline_license_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE release_bundles (
    release_bundle_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE release_bundle_imports (
    release_bundle_import_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE upgrade_plans (
    upgrade_plan_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE backup_runs (
    backup_run_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE restore_runs (
    restore_run_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE disaster_recovery_tests (
    disaster_recovery_test_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    schema_version varchar(32) NOT NULL DEFAULT '1.0',
    status varchar(64) NOT NULL DEFAULT 'CREATED',
    external_ref varchar(255),
    idempotency_key varchar(160),
    content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);

CREATE OR REPLACE FUNCTION elmos_forbid_append_only_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append-only table % cannot be updated or deleted', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER audit_event_hashes_append_only BEFORE UPDATE OR DELETE ON audit_event_hashes
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();
CREATE TRIGGER usage_ledger_entries_append_only BEFORE UPDATE OR DELETE ON usage_ledger_entries
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

DO $$
DECLARE tenant_table record;
BEGIN
    FOR tenant_table IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename NOT IN ('organizations', 'flyway_schema_history')
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS organization_id varchar(96)', tenant_table.tablename);
        EXECUTE format('UPDATE %I SET organization_id = %L WHERE organization_id IS NULL', tenant_table.tablename, 'org-system');
        EXECUTE format('ALTER TABLE %I ALTER COLUMN organization_id SET NOT NULL', tenant_table.tablename);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (organization_id)', 'idx_' || tenant_table.tablename || '_organization', tenant_table.tablename);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tenant_table.tablename);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tenant_table.tablename);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', tenant_table.tablename);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            tenant_table.tablename
        );
    END LOOP;
END;
$$;
