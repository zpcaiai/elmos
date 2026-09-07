-- Searchable metadata for very large repositories. Source bodies, complete AST,
-- CFG/DFG/call graphs and IR payloads remain in CAS; PostgreSQL keeps identities,
-- coordinates, summaries and capability closure state.

BEGIN;

CREATE TABLE analysis.repository_scan (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'created'
    CHECK (status IN ('created', 'running', 'succeeded', 'failed', 'partial', 'quarantined')),
  scanner_name text NOT NULL,
  scanner_version text NOT NULL,
  manifest_artifact_id uuid,
  file_catalog_artifact_id uuid,
  file_count bigint NOT NULL DEFAULT 0 CHECK (file_count >= 0),
  source_file_count bigint NOT NULL DEFAULT 0 CHECK (source_file_count >= 0),
  generated_file_count bigint NOT NULL DEFAULT 0 CHECK (generated_file_count >= 0),
  vendor_file_count bigint NOT NULL DEFAULT 0 CHECK (vendor_file_count >= 0),
  binary_file_count bigint NOT NULL DEFAULT 0 CHECK (binary_file_count >= 0),
  total_bytes bigint NOT NULL DEFAULT 0 CHECK (total_bytes >= 0),
  total_lines bigint NOT NULL DEFAULT 0 CHECK (total_lines >= 0),
  language_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  framework_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  warning_count integer NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, run_id, repository_revision_id, scanner_name, scanner_version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, manifest_artifact_id) REFERENCES artifact.artifact(tenant_id, id),
  FOREIGN KEY (tenant_id, file_catalog_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE analysis.repository_file (
  tenant_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  file_id uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  scan_id uuid NOT NULL,
  normalized_path text NOT NULL,
  path_hash text NOT NULL CHECK (core.sha256_is_valid(path_hash)),
  content_sha256 text CHECK (core.sha256_is_valid(content_sha256)),
  semantic_sha256 text CHECK (core.sha256_is_valid(semantic_sha256)),
  blob_artifact_id uuid,
  file_kind text NOT NULL
    CHECK (file_kind IN ('source', 'test', 'config', 'schema', 'migration', 'build', 'infrastructure', 'documentation', 'asset', 'binary', 'generated', 'vendor', 'unknown')),
  language text,
  framework text,
  encoding text,
  size_bytes bigint NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
  line_count integer CHECK (line_count IS NULL OR line_count >= 0),
  is_generated boolean NOT NULL DEFAULT false,
  is_vendor boolean NOT NULL DEFAULT false,
  is_test boolean NOT NULL DEFAULT false,
  parse_status text NOT NULL DEFAULT 'pending'
    CHECK (parse_status IN ('pending', 'parsed', 'partial', 'unsupported', 'failed', 'skipped')),
  parser_name text,
  parser_version text,
  module_key text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  discovered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, repository_revision_id, file_id),
  UNIQUE (tenant_id, repository_revision_id, normalized_path),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, scan_id) REFERENCES analysis.repository_scan(tenant_id, id),
  FOREIGN KEY (tenant_id, blob_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
) PARTITION BY HASH (repository_revision_id);

DO $$
DECLARE i integer;
BEGIN
  FOR i IN 0..15 LOOP
    EXECUTE format(
      'CREATE TABLE analysis.repository_file_p%s PARTITION OF analysis.repository_file FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
      lpad(i::text, 2, '0'), i
    );
  END LOOP;
END $$;

CREATE TABLE analysis.module_record (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  module_key text NOT NULL,
  module_kind text NOT NULL DEFAULT 'source'
    CHECK (module_kind IN ('source', 'library', 'service', 'application', 'test', 'generated', 'infrastructure', 'unknown')),
  name text NOT NULL,
  root_path text NOT NULL,
  language text,
  framework text,
  build_system text,
  manifest_path text,
  parent_module_id uuid,
  file_count bigint NOT NULL DEFAULT 0 CHECK (file_count >= 0),
  symbol_count bigint NOT NULL DEFAULT 0 CHECK (symbol_count >= 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, repository_revision_id, module_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, parent_module_id) REFERENCES analysis.module_record(tenant_id, id)
);

CREATE TABLE analysis.build_target (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  repository_revision_id uuid NOT NULL,
  module_id uuid,
  target_key text NOT NULL,
  target_kind text NOT NULL CHECK (target_kind IN ('application', 'library', 'test', 'package', 'container', 'migration', 'codegen', 'deploy', 'unknown')),
  build_system text NOT NULL,
  command_template text,
  output_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  dependency_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, repository_revision_id, target_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, module_id) REFERENCES analysis.module_record(tenant_id, id)
);

CREATE TABLE analysis.dependency_record (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  repository_revision_id uuid NOT NULL,
  source_module_id uuid,
  source_file_id uuid,
  dependency_kind text NOT NULL
    CHECK (dependency_kind IN ('package', 'module', 'symbol', 'service', 'database', 'message', 'cache', 'file', 'runtime', 'build', 'external_api')),
  dependency_name text NOT NULL,
  requested_version text,
  resolved_version text,
  scope text,
  target_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
  optional boolean NOT NULL DEFAULT false,
  confidence numeric(5,4) NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  discovered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, source_module_id) REFERENCES analysis.module_record(tenant_id, id)
);

CREATE TABLE analysis.symbol_record (
  tenant_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  symbol_id uuid NOT NULL DEFAULT extensions.gen_random_uuid(),
  file_id uuid NOT NULL,
  module_id uuid,
  symbol_key text NOT NULL,
  symbol_kind text NOT NULL,
  qualified_name text NOT NULL,
  display_name text NOT NULL,
  signature text,
  signature_sha256 text CHECK (core.sha256_is_valid(signature_sha256)),
  visibility text,
  start_line integer NOT NULL CHECK (start_line >= 0),
  start_character integer NOT NULL DEFAULT 0 CHECK (start_character >= 0),
  end_line integer NOT NULL CHECK (end_line >= start_line),
  end_character integer NOT NULL DEFAULT 0 CHECK (end_character >= 0),
  parent_symbol_key text,
  semantic_summary text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (tenant_id, repository_revision_id, symbol_id),
  UNIQUE (tenant_id, repository_revision_id, symbol_key),
  FOREIGN KEY (tenant_id, repository_revision_id, file_id)
    REFERENCES analysis.repository_file(tenant_id, repository_revision_id, file_id),
  FOREIGN KEY (tenant_id, module_id) REFERENCES analysis.module_record(tenant_id, id)
) PARTITION BY HASH (repository_revision_id);

DO $$
DECLARE i integer;
BEGIN
  FOR i IN 0..15 LOOP
    EXECUTE format(
      'CREATE TABLE analysis.symbol_record_p%s PARTITION OF analysis.symbol_record FOR VALUES WITH (MODULUS 16, REMAINDER %s)',
      lpad(i::text, 2, '0'), i
    );
  END LOOP;
END $$;

CREATE TABLE analysis.runtime_surface (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  surface_key text NOT NULL,
  surface_kind text NOT NULL
    CHECK (surface_kind IN ('http_api', 'rpc', 'database', 'message_producer', 'message_consumer', 'scheduled_job', 'cache', 'security_rule', 'feature_flag', 'websocket', 'sse', 'file_io', 'external_api', 'configuration', 'observability')),
  name text NOT NULL,
  owner_module_id uuid,
  source_reference jsonb NOT NULL,
  contract_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  criticality text NOT NULL DEFAULT 'medium' CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
  confidence numeric(5,4) NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, repository_revision_id, surface_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, owner_module_id) REFERENCES analysis.module_record(tenant_id, id)
);

CREATE TABLE analysis.graph_shard (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  graph_kind text NOT NULL
    CHECK (graph_kind IN ('dependency', 'call', 'control_flow', 'data_flow', 'api', 'database', 'message', 'configuration', 'security', 'capability')),
  shard_key text NOT NULL,
  shard_no integer NOT NULL CHECK (shard_no >= 0),
  node_count bigint NOT NULL DEFAULT 0 CHECK (node_count >= 0),
  edge_count bigint NOT NULL DEFAULT 0 CHECK (edge_count >= 0),
  min_key text,
  max_key text,
  artifact_id uuid NOT NULL,
  content_sha256 text NOT NULL CHECK (core.sha256_is_valid(content_sha256)),
  schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, repository_revision_id, graph_kind, shard_key, shard_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE analysis.semantic_ir_revision (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  ir_schema_version text NOT NULL,
  generator_name text NOT NULL,
  generator_version text NOT NULL,
  status text NOT NULL DEFAULT 'building'
    CHECK (status IN ('building', 'complete', 'partial', 'invalid', 'superseded')),
  root_artifact_id uuid,
  root_sha256 text CHECK (core.sha256_is_valid(root_sha256)),
  shard_count integer NOT NULL DEFAULT 0 CHECK (shard_count >= 0),
  entity_count bigint NOT NULL DEFAULT 0 CHECK (entity_count >= 0),
  invariant_count bigint NOT NULL DEFAULT 0 CHECK (invariant_count >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  completed_at timestamptz,
  UNIQUE (tenant_id, repository_revision_id, ir_schema_version, generator_name, generator_version),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, root_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE analysis.ir_shard (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  semantic_ir_revision_id uuid NOT NULL,
  shard_kind text NOT NULL,
  shard_key text NOT NULL,
  shard_no integer NOT NULL CHECK (shard_no >= 0),
  entity_count bigint NOT NULL DEFAULT 0 CHECK (entity_count >= 0),
  artifact_id uuid NOT NULL,
  content_sha256 text NOT NULL CHECK (core.sha256_is_valid(content_sha256)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, semantic_ir_revision_id, shard_kind, shard_key, shard_no),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, semantic_ir_revision_id) REFERENCES analysis.semantic_ir_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE analysis.capability (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  semantic_ir_revision_id uuid,
  capability_key text NOT NULL,
  capability_type text NOT NULL
    CHECK (capability_type IN ('business_rule', 'api', 'data', 'transaction', 'authorization', 'message', 'schedule', 'cache', 'integration', 'ui', 'configuration', 'observability', 'resilience', 'deployment')),
  title text NOT NULL,
  semantic_description text NOT NULL,
  source_reference jsonb NOT NULL,
  invariant_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  criticality text NOT NULL DEFAULT 'medium' CHECK (criticality IN ('low', 'medium', 'high', 'critical')),
  discovery_method text NOT NULL CHECK (discovery_method IN ('ast', 'lsp', 'graph', 'runtime', 'test', 'document', 'llm', 'rule', 'human')),
  confidence numeric(5,4) NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  status text NOT NULL DEFAULT 'discovered'
    CHECK (status IN ('discovered', 'confirmed', 'mapped', 'generated', 'verified', 'unsupported', 'semantic_gap', 'superseded')),
  semantic_sha256 text NOT NULL CHECK (core.sha256_is_valid(semantic_sha256)),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, repository_revision_id, capability_key),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, semantic_ir_revision_id) REFERENCES analysis.semantic_ir_revision(tenant_id, id)
);

CREATE TRIGGER capability_touch_updated_at
BEFORE UPDATE ON analysis.capability
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE analysis.capability_edge (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  from_capability_id uuid NOT NULL,
  to_capability_id uuid NOT NULL,
  edge_kind text NOT NULL CHECK (edge_kind IN ('depends_on', 'calls', 'reads', 'writes', 'emits', 'consumes', 'authorizes', 'compensates', 'conflicts', 'contains')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (tenant_id, from_capability_id, to_capability_id, edge_kind),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, from_capability_id) REFERENCES analysis.capability(tenant_id, id),
  FOREIGN KEY (tenant_id, to_capability_id) REFERENCES analysis.capability(tenant_id, id),
  CHECK (from_capability_id <> to_capability_id)
);

CREATE TABLE analysis.unsupported_semantic (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  source_kind text NOT NULL,
  source_reference jsonb NOT NULL,
  semantic_category text NOT NULL,
  description text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('info', 'warning', 'high', 'critical')),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'mapped', 'waived', 'blocked', 'resolved', 'superseded')),
  resolution_reference jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id)
);

CREATE TRIGGER unsupported_semantic_touch_updated_at
BEFORE UPDATE ON analysis.unsupported_semantic
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE analysis.analysis_snapshot (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  repository_revision_id uuid NOT NULL,
  scan_id uuid NOT NULL,
  semantic_ir_revision_id uuid,
  snapshot_kind text NOT NULL CHECK (snapshot_kind IN ('discovery', 'semantic', 'capability', 'complete')),
  status text NOT NULL CHECK (status IN ('building', 'complete', 'partial', 'invalid')),
  root_sha256 text NOT NULL CHECK (core.sha256_is_valid(root_sha256)),
  snapshot_artifact_id uuid NOT NULL,
  coverage_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  completed_at timestamptz,
  UNIQUE (tenant_id, run_id, snapshot_kind, root_sha256),
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, repository_revision_id) REFERENCES core.repository_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, scan_id) REFERENCES analysis.repository_scan(tenant_id, id),
  FOREIGN KEY (tenant_id, semantic_ir_revision_id) REFERENCES analysis.semantic_ir_revision(tenant_id, id),
  FOREIGN KEY (tenant_id, snapshot_artifact_id) REFERENCES artifact.artifact(tenant_id, id)
);

CREATE TABLE analysis.discovery_warning (
  id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES core.tenant(id),
  run_id uuid NOT NULL,
  scan_id uuid,
  warning_code text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
  source_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
  message text NOT NULL,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved', 'waived')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  resolved_at timestamptz,
  UNIQUE (tenant_id, id),
  FOREIGN KEY (tenant_id, run_id) REFERENCES exec.run(tenant_id, id),
  FOREIGN KEY (tenant_id, scan_id) REFERENCES analysis.repository_scan(tenant_id, id)
);

CREATE INDEX repository_file_path_trgm_idx ON analysis.repository_file USING gin (normalized_path extensions.gin_trgm_ops);
CREATE INDEX repository_file_language_idx ON analysis.repository_file (tenant_id, repository_revision_id, language, file_kind);
CREATE INDEX module_repository_idx ON analysis.module_record (tenant_id, repository_revision_id, root_path);
CREATE INDEX dependency_lookup_idx ON analysis.dependency_record (tenant_id, repository_revision_id, dependency_kind, dependency_name);
CREATE INDEX symbol_name_trgm_idx ON analysis.symbol_record USING gin (qualified_name extensions.gin_trgm_ops);
CREATE INDEX surface_kind_idx ON analysis.runtime_surface (tenant_id, repository_revision_id, surface_kind);
CREATE INDEX capability_status_idx ON analysis.capability (tenant_id, run_id, status, criticality);
CREATE INDEX capability_type_idx ON analysis.capability (tenant_id, repository_revision_id, capability_type);
CREATE INDEX unsupported_open_idx ON analysis.unsupported_semantic (tenant_id, run_id, severity)
  WHERE status IN ('open', 'blocked');

COMMIT;
