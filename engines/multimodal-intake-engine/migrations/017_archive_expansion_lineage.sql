PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;

CREATE TABLE archive_expansion_roots (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    root_archive_digest TEXT NOT NULL CHECK (length(root_archive_digest) = 64),
    policy_digest TEXT NOT NULL CHECK (length(policy_digest) = 64),
    max_total_uncompressed_bytes INTEGER NOT NULL CHECK (max_total_uncompressed_bytes >= 1),
    max_entries INTEGER NOT NULL CHECK (max_entries >= 1),
    max_nested_depth INTEGER NOT NULL CHECK (max_nested_depth >= 0),
    consumed_uncompressed_bytes INTEGER NOT NULL CHECK (
        consumed_uncompressed_bytes >= 0
        AND consumed_uncompressed_bytes <= max_total_uncompressed_bytes
    ),
    consumed_entries INTEGER NOT NULL CHECK (
        consumed_entries >= 0 AND consumed_entries <= max_entries
    ),
    version INTEGER NOT NULL CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, project_id, root_archive_digest)
);

CREATE TABLE archive_expansion_nodes (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    node_digest TEXT NOT NULL CHECK (length(node_digest) = 64),
    root_archive_digest TEXT NOT NULL CHECK (length(root_archive_digest) = 64),
    parent_node_digest TEXT CHECK (
        parent_node_digest IS NULL OR length(parent_node_digest) = 64
    ),
    parent_archive_digest TEXT CHECK (
        parent_archive_digest IS NULL OR length(parent_archive_digest) = 64
    ),
    parent_entry_digest TEXT CHECK (
        parent_entry_digest IS NULL OR length(parent_entry_digest) = 64
    ),
    parent_entry_receipt_digest TEXT CHECK (
        parent_entry_receipt_digest IS NULL OR length(parent_entry_receipt_digest) = 64
    ),
    parent_generation_digest TEXT CHECK (
        parent_generation_digest IS NULL OR length(parent_generation_digest) = 64
    ),
    archive_digest TEXT NOT NULL CHECK (length(archive_digest) = 64),
    depth INTEGER NOT NULL CHECK (depth >= 0),
    expanded_uncompressed_bytes INTEGER NOT NULL CHECK (expanded_uncompressed_bytes >= 0),
    expanded_entries INTEGER NOT NULL CHECK (expanded_entries >= 1),
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    state TEXT NOT NULL CHECK (state IN ('RESERVED', 'PUBLISHED')),
    generation_digest TEXT CHECK (
        generation_digest IS NULL OR length(generation_digest) = 64
    ),
    result_digest TEXT CHECK (result_digest IS NULL OR length(result_digest) = 64),
    created_at TEXT NOT NULL,
    published_at TEXT,
    PRIMARY KEY (tenant_id, project_id, node_digest),
    UNIQUE (
        tenant_id, project_id, root_archive_digest,
        parent_node_digest, parent_entry_receipt_digest
    ),
    FOREIGN KEY (tenant_id, project_id, root_archive_digest)
        REFERENCES archive_expansion_roots (
            tenant_id, project_id, root_archive_digest
        ),
    FOREIGN KEY (tenant_id, project_id, parent_node_digest)
        REFERENCES archive_expansion_nodes (tenant_id, project_id, node_digest),
    CHECK (
        (depth = 0
            AND parent_node_digest IS NULL
            AND parent_archive_digest IS NULL
            AND parent_entry_digest IS NULL
            AND parent_entry_receipt_digest IS NULL
            AND parent_generation_digest IS NULL
            AND root_archive_digest = archive_digest)
        OR (depth > 0
            AND parent_node_digest IS NOT NULL
            AND parent_archive_digest IS NOT NULL
            AND parent_entry_digest IS NOT NULL
            AND parent_entry_receipt_digest IS NOT NULL
            AND parent_generation_digest IS NOT NULL)
    ),
    CHECK (
        (state = 'RESERVED'
            AND generation_digest IS NULL
            AND result_digest IS NULL
            AND published_at IS NULL)
        OR (state = 'PUBLISHED'
            AND generation_digest IS NOT NULL
            AND result_digest IS NOT NULL
            AND published_at IS NOT NULL)
    )
);

CREATE TABLE archive_expansion_entries (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    node_digest TEXT NOT NULL CHECK (length(node_digest) = 64),
    entry_receipt_digest TEXT NOT NULL CHECK (length(entry_receipt_digest) = 64),
    entry_digest TEXT NOT NULL CHECK (length(entry_digest) = 64),
    path_digest TEXT NOT NULL CHECK (length(path_digest) = 64),
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    nested_container TEXT CHECK (nested_container IN ('zip', 'tar', 'gzip')),
    generation_digest TEXT NOT NULL CHECK (length(generation_digest) = 64),
    PRIMARY KEY (tenant_id, project_id, node_digest, entry_receipt_digest),
    FOREIGN KEY (tenant_id, project_id, node_digest)
        REFERENCES archive_expansion_nodes (tenant_id, project_id, node_digest)
);

CREATE UNIQUE INDEX archive_expansion_top_level_unique
    ON archive_expansion_nodes (tenant_id, project_id, root_archive_digest)
    WHERE depth = 0;

CREATE UNIQUE INDEX archive_expansion_child_unique
    ON archive_expansion_nodes (
        tenant_id, project_id, parent_node_digest, parent_entry_receipt_digest
    )
    WHERE depth > 0;

CREATE INDEX archive_expansion_entries_lookup
    ON archive_expansion_entries (
        tenant_id, project_id, entry_receipt_digest, entry_digest
    );

CREATE TRIGGER archive_expansion_roots_guard_update
BEFORE UPDATE ON archive_expansion_roots
WHEN NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.root_archive_digest IS NOT OLD.root_archive_digest
  OR NEW.policy_digest IS NOT OLD.policy_digest
  OR NEW.max_total_uncompressed_bytes IS NOT OLD.max_total_uncompressed_bytes
  OR NEW.max_entries IS NOT OLD.max_entries
  OR NEW.max_nested_depth IS NOT OLD.max_nested_depth
  OR NEW.consumed_uncompressed_bytes < OLD.consumed_uncompressed_bytes
  OR NEW.consumed_entries < OLD.consumed_entries
  OR NEW.version <> OLD.version + 1
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'ARCHIVE_EXPANSION_ROOT_UPDATE_INVALID');
END;

CREATE TRIGGER archive_expansion_nodes_guard_update
BEFORE UPDATE ON archive_expansion_nodes
WHEN NEW.tenant_id IS NOT OLD.tenant_id
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.node_digest IS NOT OLD.node_digest
  OR NEW.root_archive_digest IS NOT OLD.root_archive_digest
  OR NEW.parent_node_digest IS NOT OLD.parent_node_digest
  OR NEW.parent_archive_digest IS NOT OLD.parent_archive_digest
  OR NEW.parent_entry_digest IS NOT OLD.parent_entry_digest
  OR NEW.parent_entry_receipt_digest IS NOT OLD.parent_entry_receipt_digest
  OR NEW.parent_generation_digest IS NOT OLD.parent_generation_digest
  OR NEW.archive_digest IS NOT OLD.archive_digest
  OR NEW.depth IS NOT OLD.depth
  OR NEW.expanded_uncompressed_bytes IS NOT OLD.expanded_uncompressed_bytes
  OR NEW.expanded_entries IS NOT OLD.expanded_entries
  OR NEW.request_digest IS NOT OLD.request_digest
  OR OLD.state <> 'RESERVED'
  OR NEW.state <> 'PUBLISHED'
  OR NEW.generation_digest IS NULL
  OR NEW.result_digest IS NULL
  OR NEW.published_at IS NULL
  OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'ARCHIVE_EXPANSION_NODE_UPDATE_INVALID');
END;

CREATE TRIGGER archive_expansion_roots_no_delete
BEFORE DELETE ON archive_expansion_roots
BEGIN
    SELECT RAISE(ABORT, 'ARCHIVE_EXPANSION_ROOT_IMMUTABLE');
END;

CREATE TRIGGER archive_expansion_nodes_no_delete
BEFORE DELETE ON archive_expansion_nodes
BEGIN
    SELECT RAISE(ABORT, 'ARCHIVE_EXPANSION_NODE_IMMUTABLE');
END;

CREATE TRIGGER archive_expansion_entries_immutable_update
BEFORE UPDATE ON archive_expansion_entries
BEGIN
    SELECT RAISE(ABORT, 'ARCHIVE_EXPANSION_ENTRY_IMMUTABLE');
END;

CREATE TRIGGER archive_expansion_entries_no_delete
BEFORE DELETE ON archive_expansion_entries
BEGIN
    SELECT RAISE(ABORT, 'ARCHIVE_EXPANSION_ENTRY_IMMUTABLE');
END;

PRAGMA user_version = 17;
COMMIT;
