CREATE TABLE scm_connections (
    connection_id varchar(64) PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    provider varchar(32) NOT NULL CHECK (provider = 'GITHUB'),
    status varchar(32) NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE github_app_installations (
    installation_id varchar(64) PRIMARY KEY,
    connection_id varchar(64) NOT NULL REFERENCES scm_connections(connection_id),
    github_installation_id bigint NOT NULL UNIQUE,
    account_external_id bigint NOT NULL,
    account_login text NOT NULL,
    target_type varchar(32) NOT NULL,
    installer_external_id bigint,
    installed_at timestamptz NOT NULL,
    permissions jsonb NOT NULL,
    repository_selection varchar(32) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'ACTIVE',
    suspended_at timestamptz,
    deleted_at timestamptz,
    last_synced_at timestamptz NOT NULL
);

CREATE TABLE scm_repositories (
    scm_repository_id varchar(64) PRIMARY KEY,
    repository_id varchar(64) NOT NULL UNIQUE REFERENCES repositories(repository_id),
    installation_id varchar(64) NOT NULL REFERENCES github_app_installations(installation_id),
    github_repository_id bigint NOT NULL UNIQUE,
    owner_login text NOT NULL,
    repository_name text NOT NULL,
    full_name text NOT NULL,
    clone_url text NOT NULL,
    html_url text NOT NULL,
    default_branch text NOT NULL,
    visibility varchar(32) NOT NULL,
    archived boolean NOT NULL DEFAULT false,
    disabled boolean NOT NULL DEFAULT false,
    fork boolean NOT NULL DEFAULT false,
    parent_repository_external_id bigint,
    authorization_status varchar(32) NOT NULL,
    synced_at timestamptz NOT NULL
);

CREATE TABLE scm_repository_permissions (
    scm_repository_id varchar(64) NOT NULL REFERENCES scm_repositories(scm_repository_id),
    permission_name varchar(64) NOT NULL,
    access_level varchar(16) NOT NULL CHECK (access_level IN ('READ', 'WRITE', 'ADMIN')),
    observed_at timestamptz NOT NULL,
    PRIMARY KEY (scm_repository_id, permission_name)
);

CREATE TABLE github_webhook_deliveries (
    webhook_delivery_id varchar(64) PRIMARY KEY,
    github_delivery_id varchar(128) NOT NULL UNIQUE,
    event_type varchar(64) NOT NULL,
    action varchar(64),
    normalized_event_type varchar(64),
    installation_external_id bigint,
    repository_external_id bigint,
    payload_sha256 char(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    received_at timestamptz NOT NULL,
    signature_valid boolean NOT NULL DEFAULT true,
    processing_status varchar(32) NOT NULL DEFAULT 'RECEIVED',
    duplicate_count integer NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
    processed_at timestamptz,
    failure_code varchar(64),
    payload_artifact_ref text
);

ALTER TABLE repository_snapshots RENAME COLUMN branch TO requested_ref;
ALTER TABLE repository_snapshots RENAME COLUMN source_archive_ref TO archive_artifact_ref;
ALTER TABLE repository_snapshots
    ADD COLUMN tree_sha varchar(64),
    ADD COLUMN archive_sha256 char(64),
    ADD COLUMN archive_size bigint,
    ADD COLUMN manifest_artifact_ref text,
    ADD COLUMN manifest_sha256 char(64),
    ADD COLUMN source_file_count integer,
    ADD COLUMN source_byte_count bigint,
    ADD COLUMN submodule_state varchar(32) NOT NULL DEFAULT 'NOT_DETECTED',
    ADD COLUMN git_lfs_state varchar(32) NOT NULL DEFAULT 'NOT_DETECTED',
    ADD COLUMN snapshot_schema_version integer NOT NULL DEFAULT 1 CHECK (snapshot_schema_version > 0),
    ADD COLUMN status varchar(32) NOT NULL DEFAULT 'AVAILABLE';
ALTER TABLE repository_snapshots DROP CONSTRAINT repository_snapshots_content_v1_uq;
ALTER TABLE repository_snapshots ADD CONSTRAINT repository_snapshot_content_uq UNIQUE (repository_id, commit_sha, snapshot_schema_version);

CREATE TABLE snapshot_source_artifacts (
    source_artifact_id varchar(64) PRIMARY KEY,
    snapshot_id varchar(64) NOT NULL REFERENCES repository_snapshots(snapshot_id),
    artifact_ref text NOT NULL,
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    media_type text NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (snapshot_id, sha256)
);

CREATE TABLE snapshot_manifests (
    manifest_id varchar(64) PRIMARY KEY,
    snapshot_id varchar(64) NOT NULL UNIQUE REFERENCES repository_snapshots(snapshot_id),
    artifact_ref text NOT NULL,
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    schema_version integer NOT NULL CHECK (schema_version > 0),
    source_file_count integer NOT NULL CHECK (source_file_count >= 0),
    source_byte_count bigint NOT NULL CHECK (source_byte_count >= 0),
    created_at timestamptz NOT NULL
);

CREATE TABLE snapshot_materializations (
    materialization_id varchar(64) PRIMARY KEY,
    snapshot_id varchar(64) NOT NULL REFERENCES repository_snapshots(snapshot_id),
    workspace_external_id varchar(128) NOT NULL,
    status varchar(32) NOT NULL,
    materialized_at timestamptz,
    removed_at timestamptz,
    UNIQUE (snapshot_id, workspace_external_id)
);

CREATE TABLE sandbox_profiles (
    sandbox_profile_id varchar(64) PRIMARY KEY,
    profile_version integer NOT NULL CHECK (profile_version > 0),
    java_version integer NOT NULL CHECK (java_version IN (8, 11, 17, 21)),
    image_digest varchar(80) NOT NULL CHECK (image_digest ~ '^sha256:[0-9a-f]{64}$'),
    approved boolean NOT NULL DEFAULT false,
    resource_defaults jsonb NOT NULL,
    evidence_refs jsonb NOT NULL,
    UNIQUE (sandbox_profile_id, profile_version)
);

CREATE TABLE workspace_instances (
    workspace_id varchar(64) PRIMARY KEY,
    workspace_external_id varchar(128) NOT NULL UNIQUE,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    migration_run_id varchar(64) REFERENCES migration_runs(migration_run_id),
    snapshot_id varchar(64) NOT NULL REFERENCES repository_snapshots(snapshot_id),
    sandbox_profile_id varchar(64) NOT NULL,
    image_digest varchar(80) NOT NULL CHECK (image_digest ~ '^sha256:[0-9a-f]{64}$'),
    state varchar(32) NOT NULL,
    resource_limits jsonb NOT NULL,
    network_policy_id varchar(64) NOT NULL,
    created_at timestamptz NOT NULL,
    last_heartbeat_at timestamptz,
    expires_at timestamptz NOT NULL,
    terminated_at timestamptz
);
CREATE INDEX workspace_expiry_idx ON workspace_instances(state, expires_at);

CREATE TABLE workspace_mounts (
    mount_id varchar(64) PRIMARY KEY,
    workspace_id varchar(64) NOT NULL REFERENCES workspace_instances(workspace_id),
    volume_external_id varchar(128) NOT NULL,
    role varchar(32) NOT NULL,
    container_path text NOT NULL CHECK (container_path LIKE '/%'),
    read_only boolean NOT NULL,
    ownership_labels jsonb NOT NULL,
    UNIQUE (workspace_id, container_path)
);

CREATE TABLE workspace_commands (
    command_id varchar(64) PRIMARY KEY,
    workspace_id varchar(64) NOT NULL REFERENCES workspace_instances(workspace_id),
    idempotency_key varchar(128) NOT NULL,
    argv_sha256 char(64) NOT NULL,
    working_directory text NOT NULL,
    status varchar(32) NOT NULL,
    started_at timestamptz,
    finished_at timestamptz,
    exit_code integer,
    termination_reason varchar(64),
    stdout_artifact_ref text,
    stderr_artifact_ref text,
    output_sha256 char(64),
    output_truncated boolean NOT NULL DEFAULT false,
    UNIQUE (workspace_id, idempotency_key)
);

CREATE TABLE workspace_resource_samples (
    sample_id bigserial PRIMARY KEY,
    workspace_id varchar(64) NOT NULL REFERENCES workspace_instances(workspace_id),
    sampled_at timestamptz NOT NULL,
    cpu_nanos bigint NOT NULL DEFAULT 0,
    memory_bytes bigint NOT NULL DEFAULT 0,
    pids integer NOT NULL DEFAULT 0,
    disk_bytes bigint NOT NULL DEFAULT 0,
    network_connections integer NOT NULL DEFAULT 0
);

CREATE TABLE workspace_events (
    workspace_event_id varchar(64) PRIMARY KEY,
    workspace_id varchar(64) NOT NULL REFERENCES workspace_instances(workspace_id),
    event_type varchar(64) NOT NULL,
    occurred_at timestamptz NOT NULL,
    attributes jsonb NOT NULL
);

CREATE TABLE secret_leases (
    lease_id varchar(64) PRIMARY KEY,
    provider_lease_id varchar(128) NOT NULL UNIQUE,
    secret_type varchar(64) NOT NULL,
    workspace_id varchar(64) REFERENCES workspace_instances(workspace_id),
    issued_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    status varchar(32) NOT NULL,
    CHECK (expires_at > issued_at)
);

CREATE TABLE secret_lease_bindings (
    binding_id varchar(64) PRIMARY KEY,
    lease_id varchar(64) NOT NULL REFERENCES secret_leases(lease_id),
    workspace_id varchar(64) NOT NULL REFERENCES workspace_instances(workspace_id),
    injection_type varchar(32) NOT NULL,
    mount_path text,
    injected_at timestamptz,
    removed_at timestamptz,
    UNIQUE (lease_id, workspace_id)
);

CREATE TABLE secret_access_events (
    access_event_id varchar(64) PRIMARY KEY,
    lease_id varchar(64) NOT NULL REFERENCES secret_leases(lease_id),
    workspace_id varchar(64) REFERENCES workspace_instances(workspace_id),
    action varchar(32) NOT NULL,
    occurred_at timestamptz NOT NULL,
    result varchar(32) NOT NULL,
    failure_code varchar(64)
);

CREATE TABLE network_policies (
    network_policy_id varchar(64) NOT NULL,
    policy_version integer NOT NULL CHECK (policy_version > 0),
    organization_id varchar(64) REFERENCES organizations(organization_id),
    default_action varchar(16) NOT NULL CHECK (default_action = 'DENY'),
    status varchar(32) NOT NULL,
    valid_from timestamptz NOT NULL,
    expires_at timestamptz,
    PRIMARY KEY (network_policy_id, policy_version)
);

CREATE TABLE network_policy_rules (
    network_policy_id varchar(64) NOT NULL,
    policy_version integer NOT NULL,
    rule_order integer NOT NULL CHECK (rule_order >= 0),
    protocol varchar(16) NOT NULL CHECK (protocol = 'HTTPS'),
    exact_host text NOT NULL CHECK (exact_host NOT LIKE '%*%'),
    port integer NOT NULL DEFAULT 443 CHECK (port = 443),
    PRIMARY KEY (network_policy_id, policy_version, rule_order),
    FOREIGN KEY (network_policy_id, policy_version) REFERENCES network_policies(network_policy_id, policy_version)
);

CREATE TABLE network_policy_bindings (
    binding_id varchar(64) PRIMARY KEY,
    workspace_id varchar(64) NOT NULL REFERENCES workspace_instances(workspace_id),
    network_policy_id varchar(64) NOT NULL,
    policy_version integer NOT NULL,
    proxy_external_id varchar(128),
    applied_at timestamptz NOT NULL,
    removed_at timestamptz,
    UNIQUE (workspace_id, policy_version),
    FOREIGN KEY (network_policy_id, policy_version) REFERENCES network_policies(network_policy_id, policy_version)
);

CREATE TABLE network_access_events (
    access_event_id varchar(64) PRIMARY KEY,
    binding_id varchar(64) NOT NULL REFERENCES network_policy_bindings(binding_id),
    occurred_at timestamptz NOT NULL,
    scheme varchar(16) NOT NULL,
    host text NOT NULL,
    resolved_addresses jsonb NOT NULL,
    decision varchar(16) NOT NULL,
    reason varchar(128) NOT NULL,
    bytes_sent bigint NOT NULL DEFAULT 0,
    bytes_received bigint NOT NULL DEFAULT 0
);

CREATE TABLE workspace_artifacts (
    workspace_artifact_id varchar(64) PRIMARY KEY,
    workspace_id varchar(64) NOT NULL REFERENCES workspace_instances(workspace_id),
    artifact_type varchar(64) NOT NULL,
    artifact_ref text NOT NULL,
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    secret_scan_status varchar(32) NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (workspace_id, artifact_type, sha256)
);

CREATE TABLE workspace_cleanup_runs (
    cleanup_run_id varchar(64) PRIMARY KEY,
    workspace_id varchar(64) NOT NULL REFERENCES workspace_instances(workspace_id),
    idempotency_key varchar(128) NOT NULL,
    trigger_reason varchar(64) NOT NULL,
    status varchar(32) NOT NULL,
    steps jsonb NOT NULL,
    requested_at timestamptz NOT NULL,
    completed_at timestamptz,
    UNIQUE (workspace_id, idempotency_key)
);
