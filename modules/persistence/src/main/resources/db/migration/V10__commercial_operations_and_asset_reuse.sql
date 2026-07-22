-- ELMOS Batch 10: commercial fulfillment, delivery operations and reusable asset lifecycle.
-- This is not a CRM, payment processor, tax engine or accounting ledger; those remain external ports.

CREATE TABLE products (
    product_id varchar(96) PRIMARY KEY,
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

CREATE TABLE product_editions (
    product_edition_id varchar(96) PRIMARY KEY,
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

CREATE TABLE product_features (
    product_feature_id varchar(96) PRIMARY KEY,
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

CREATE TABLE product_packages (
    product_package_id varchar(96) PRIMARY KEY,
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

CREATE TABLE package_features (
    package_feature_id varchar(96) PRIMARY KEY,
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

CREATE TABLE price_books (
    price_book_id varchar(96) PRIMARY KEY,
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

CREATE TABLE price_items (
    price_item_id varchar(96) PRIMARY KEY,
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

CREATE TABLE commercial_accounts (
    commercial_account_id varchar(96) PRIMARY KEY,
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

CREATE TABLE subscriptions (
    subscription_id varchar(96) PRIMARY KEY,
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

CREATE TABLE subscription_items (
    subscription_item_id varchar(96) PRIMARY KEY,
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

CREATE TABLE subscription_events (
    subscription_event_id varchar(96) PRIMARY KEY,
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

CREATE TABLE subscription_changes (
    subscription_change_id varchar(96) PRIMARY KEY,
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

CREATE TABLE entitlements (
    entitlement_id varchar(96) PRIMARY KEY,
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

CREATE TABLE entitlement_limits (
    entitlement_limit_id varchar(96) PRIMARY KEY,
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

CREATE TABLE entitlement_consumptions (
    entitlement_consumption_id varchar(96) PRIMARY KEY,
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

CREATE TABLE license_grants (
    license_grant_id varchar(96) PRIMARY KEY,
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

CREATE TABLE license_activations (
    license_activation_id varchar(96) PRIMARY KEY,
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

CREATE TABLE quotes (
    quote_id varchar(96) PRIMARY KEY,
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

CREATE TABLE quote_versions (
    quote_version_id varchar(96) PRIMARY KEY,
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

CREATE TABLE quote_lines (
    quote_line_id varchar(96) PRIMARY KEY,
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

CREATE TABLE quote_approvals (
    quote_approval_id varchar(96) PRIMARY KEY,
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

CREATE TABLE orders (
    order_id varchar(96) PRIMARY KEY,
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

CREATE TABLE order_lines (
    order_line_id varchar(96) PRIMARY KEY,
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

CREATE TABLE order_events (
    order_event_id varchar(96) PRIMARY KEY,
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

CREATE TABLE contract_references (
    contract_reference_id varchar(96) PRIMARY KEY,
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

CREATE TABLE fulfillment_plans (
    fulfillment_plan_id varchar(96) PRIMARY KEY,
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

CREATE TABLE fulfillment_tasks (
    fulfillment_task_id varchar(96) PRIMARY KEY,
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

CREATE TABLE onboarding_plans (
    onboarding_plan_id varchar(96) PRIMARY KEY,
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

CREATE TABLE onboarding_tasks (
    onboarding_task_id varchar(96) PRIMARY KEY,
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

CREATE TABLE readiness_assessments (
    readiness_assessment_id varchar(96) PRIMARY KEY,
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

CREATE TABLE readiness_findings (
    readiness_finding_id varchar(96) PRIMARY KEY,
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

CREATE TABLE customer_environments (
    customer_environment_id varchar(96) PRIMARY KEY,
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

CREATE TABLE customer_contacts (
    customer_contact_id varchar(96) PRIMARY KEY,
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

CREATE TABLE integration_checklists (
    integration_checklist_id varchar(96) PRIMARY KEY,
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

CREATE TABLE migration_projects (
    migration_project_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_repositories (
    project_repository_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_workstreams (
    project_workstream_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_milestones (
    project_milestone_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_tasks (
    project_task_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_dependencies (
    project_dependency_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_decisions (
    project_decision_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_risks (
    project_risk_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_status_snapshots (
    project_status_snapshot_id varchar(96) PRIMARY KEY,
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

CREATE TABLE project_change_requests (
    project_change_request_id varchar(96) PRIMARY KEY,
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

CREATE TABLE service_level_policies (
    service_level_policy_id varchar(96) PRIMARY KEY,
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

CREATE TABLE service_level_objectives (
    service_level_objective_id varchar(96) PRIMARY KEY,
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

CREATE TABLE service_level_measurements (
    service_level_measurement_id varchar(96) PRIMARY KEY,
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

CREATE TABLE service_level_breaches (
    service_level_breache_id varchar(96) PRIMARY KEY,
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

CREATE TABLE service_credit_records (
    service_credit_record_id varchar(96) PRIMARY KEY,
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

CREATE TABLE maintenance_windows (
    maintenance_window_id varchar(96) PRIMARY KEY,
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

CREATE TABLE support_tickets (
    support_ticket_id varchar(96) PRIMARY KEY,
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

CREATE TABLE support_ticket_events (
    support_ticket_event_id varchar(96) PRIMARY KEY,
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

CREATE TABLE support_comments (
    support_comment_id varchar(96) PRIMARY KEY,
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

CREATE TABLE support_attachments (
    support_attachment_id varchar(96) PRIMARY KEY,
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

CREATE TABLE support_incidents (
    support_incident_id varchar(96) PRIMARY KEY,
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

CREATE TABLE incident_timelines (
    incident_timeline_id varchar(96) PRIMARY KEY,
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

CREATE TABLE problem_records (
    problem_record_id varchar(96) PRIMARY KEY,
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

CREATE TABLE known_errors (
    known_error_id varchar(96) PRIMARY KEY,
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

CREATE TABLE support_resolutions (
    support_resolution_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_assets (
    recipe_asset_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_asset_versions (
    recipe_asset_version_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_listings (
    recipe_listing_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_prices (
    recipe_price_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_entitlements (
    recipe_entitlement_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_reviews (
    recipe_review_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_certifications (
    recipe_certification_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_installations (
    recipe_installation_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_usage_records (
    recipe_usage_record_id varchar(96) PRIMARY KEY,
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

CREATE TABLE recipe_revenue_shares (
    recipe_revenue_share_id varchar(96) PRIMARY KEY,
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

CREATE TABLE knowledge_articles (
    knowledge_article_id varchar(96) PRIMARY KEY,
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

CREATE TABLE implementation_playbooks (
    implementation_playbook_id varchar(96) PRIMARY KEY,
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

CREATE TABLE resolution_patterns (
    resolution_pattern_id varchar(96) PRIMARY KEY,
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

CREATE TABLE migration_patterns (
    migration_pattern_id varchar(96) PRIMARY KEY,
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

CREATE TABLE knowledge_sources (
    knowledge_source_id varchar(96) PRIMARY KEY,
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

CREATE TABLE knowledge_reviews (
    knowledge_review_id varchar(96) PRIMARY KEY,
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

CREATE TABLE knowledge_access_policies (
    knowledge_access_policy_id varchar(96) PRIMARY KEY,
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

CREATE TABLE customer_health_scores (
    customer_health_score_id varchar(96) PRIMARY KEY,
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

CREATE TABLE customer_success_plans (
    customer_success_plan_id varchar(96) PRIMARY KEY,
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

CREATE TABLE adoption_metrics (
    adoption_metric_id varchar(96) PRIMARY KEY,
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

CREATE TABLE renewal_opportunities (
    renewal_opportunity_id varchar(96) PRIMARY KEY,
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

CREATE TABLE expansion_opportunities (
    expansion_opportunity_id varchar(96) PRIMARY KEY,
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

CREATE TABLE renewal_events (
    renewal_event_id varchar(96) PRIMARY KEY,
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

CREATE TABLE commercial_events (
    commercial_event_id varchar(96) PRIMARY KEY,
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

CREATE TABLE commercial_metric_snapshots (
    commercial_metric_snapshot_id varchar(96) PRIMARY KEY,
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

CREATE TABLE delivery_economics (
    delivery_economic_id varchar(96) PRIMARY KEY,
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

CREATE TABLE customer_profitability_snapshots (
    customer_profitability_snapshot_id varchar(96) PRIMARY KEY,
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

CREATE TABLE commercial_alerts (
    commercial_alert_id varchar(96) PRIMARY KEY,
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

CREATE TRIGGER commercial_events_append_only BEFORE UPDATE OR DELETE ON commercial_events
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

DO $$
DECLARE tenant_table record;
BEGIN
    FOR tenant_table IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename NOT IN ('organizations', 'flyway_schema_history')
          AND NOT EXISTS (
              SELECT 1 FROM pg_policies
              WHERE schemaname = 'public' AND tablename = pg_tables.tablename AND policyname = 'tenant_isolation'
          )
    LOOP
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (organization_id)', 'idx_' || tenant_table.tablename || '_organization', tenant_table.tablename);
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tenant_table.tablename);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tenant_table.tablename);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            tenant_table.tablename
        );
    END LOOP;
END;
$$;

