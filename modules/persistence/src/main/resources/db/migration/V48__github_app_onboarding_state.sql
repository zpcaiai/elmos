CREATE TABLE github_app_onboarding_states (
    state_nonce varchar(64) PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    connection_id varchar(64) NOT NULL REFERENCES scm_connections(connection_id),
    stage varchar(16) NOT NULL CHECK (stage IN ('INSTALL', 'OAUTH')),
    installation_external_id bigint,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz,
    consumed_at timestamptz,
    CHECK (
        (stage = 'INSTALL' AND installation_external_id IS NULL)
        OR (stage = 'OAUTH' AND installation_external_id > 0)
    )
);

CREATE INDEX github_app_onboarding_expiry_idx
    ON github_app_onboarding_states(expires_at)
    WHERE consumed_at IS NULL;

ALTER TABLE github_app_onboarding_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE github_app_onboarding_states FORCE ROW LEVEL SECURITY;

CREATE POLICY github_app_onboarding_tenant_isolation
    ON github_app_onboarding_states
    USING (
        organization_id = current_setting('app.organization_id', true)
    )
    WITH CHECK (
        organization_id = current_setting('app.organization_id', true)
    );
