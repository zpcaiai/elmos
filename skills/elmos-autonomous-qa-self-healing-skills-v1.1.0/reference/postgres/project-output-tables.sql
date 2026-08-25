-- Reference schema. Adapt naming/types to the Elmos persistence layer.

CREATE TABLE project_outputs (
    output_id            text PRIMARY KEY,
    tenant_id            text NOT NULL,
    project_id           text NOT NULL,
    revision_id          text NOT NULL,
    run_id               text NOT NULL,
    source_snapshot_id   text NOT NULL,
    status               text NOT NULL CHECK (status IN ('assembling','partial','failed','verified','certified','publication_failed','superseded')),
    output_mode          text NOT NULL CHECK (output_mode IN ('embedded','sidecar','both')),
    manifest_uri         text,
    manifest_sha256      text,
    created_at           timestamptz NOT NULL,
    published_at         timestamptz,
    superseded_by        text REFERENCES project_outputs(output_id),
    UNIQUE (tenant_id, project_id, revision_id, run_id)
);

CREATE TABLE output_artifacts (
    artifact_id          text PRIMARY KEY,
    output_id            text NOT NULL REFERENCES project_outputs(output_id) ON DELETE RESTRICT,
    category             text NOT NULL,
    role                 text NOT NULL,
    relative_path        text NOT NULL,
    content_type         text NOT NULL,
    sha256               text NOT NULL,
    size_bytes           bigint NOT NULL CHECK (size_bytes >= 0),
    validation_status    text NOT NULL,
    retention_class      text NOT NULL,
    metadata             jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at           timestamptz NOT NULL,
    UNIQUE (output_id, relative_path)
);

CREATE INDEX idx_output_artifacts_sha256 ON output_artifacts(sha256);
CREATE INDEX idx_output_artifacts_category ON output_artifacts(output_id, category);

CREATE TABLE output_bundles (
    bundle_id            text PRIMARY KEY,
    output_id            text NOT NULL REFERENCES project_outputs(output_id) ON DELETE RESTRICT,
    kind                 text NOT NULL CHECK (kind IN ('project-with-tests','tests-only','qa-evidence','repair-patches')),
    format               text NOT NULL,
    object_uri           text NOT NULL,
    sha256               text NOT NULL,
    size_bytes           bigint NOT NULL CHECK (size_bytes >= 0),
    status               text NOT NULL CHECK (status IN ('building','verified','failed','superseded')),
    created_at           timestamptz NOT NULL,
    UNIQUE (output_id, kind, format)
);

CREATE TABLE artifact_lineage (
    lineage_id           text PRIMARY KEY,
    output_id            text NOT NULL REFERENCES project_outputs(output_id) ON DELETE RESTRICT,
    artifact_id          text NOT NULL REFERENCES output_artifacts(artifact_id) ON DELETE RESTRICT,
    relation             text NOT NULL CHECK (relation IN ('generated_from','modified_by','validated_by','supersedes','derived_from','contained_in')),
    subject_ref          text NOT NULL,
    metadata             jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at           timestamptz NOT NULL
);

CREATE INDEX idx_project_outputs_latest ON project_outputs(tenant_id, project_id, created_at DESC);
CREATE INDEX idx_artifact_lineage_artifact ON artifact_lineage(artifact_id, relation);
