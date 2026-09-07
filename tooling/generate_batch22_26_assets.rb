#!/usr/bin/env ruby
# frozen_string_literal: true

require "fileutils"
require "json"
require "open3"

ROOT = File.expand_path("..", __dir__)
SKILL_TOOL = "/Users/stephen/.codex/skills/.system/skill-creator/scripts"
PYTHON = File.join(ROOT, "engines/python-engine/.venv/bin/python")

BATCHES = [
  { number: 22, engine: "software-delivery-platform-engine", title: "Software Delivery Platform", port: 8096,
    runners: %w[scm-migration ci-validation artifact-validation environment-validation platform-acceptance],
    endpoints: %w[discover plan execute-step validate self-service],
    adapters: %w[GITHUB GITLAB AZURE_DEVOPS BITBUCKET SVN PERFORCE CLEARCASE JENKINS TEKTON ARTIFACT_REGISTRY BACKSTAGE CDEVENTS GITOPS SURVEY],
    fixture: "engines/software-delivery-platform-engine/test-fixtures/batch22-acceptance-scenarios.json", expected: 36,
    migration: "V28__software_delivery_platform_engine.sql", schema: "software_delivery",
    attachment: "/Users/stephen/.codex/attachments/206eea53-bddc-480a-a4bd-9b0831676c2e/pasted-text.txt" },
  { number: 23, engine: "ai-platform-engine", title: "AI ML and Generative AI Platform", port: 8097,
    runners: %w[ai-discovery cpu-training gpu-training inference-validation rag-sandbox agent-sandbox evaluation red-team],
    endpoints: %w[discover plan train evaluate deploy monitor],
    adapters: %w[MLFLOW FEAST KUBEFLOW KSERVE INFERENCE_GATEWAY ENVOY_AI_GATEWAY CLOUD_AI VECTOR_STORE AGENT_FRAMEWORK OPENTELEMETRY HUMAN_REVIEW],
    fixture: "engines/ai-platform-engine/test-fixtures/batch23-acceptance-scenarios.json", expected: 44,
    migration: "V29__ai_ml_generative_ai_platform.sql", schema: "ai_platform",
    attachment: "/Users/stephen/.codex/attachments/7699acc6-99d2-44d0-bbaa-c76772d89bbe/pasted-text.txt" },
  { number: 24, engine: "edge-iot-industrial-engine", title: "Edge IoT and Industrial Systems", port: 8098,
    runners: %w[passive-discovery protocol-validation edge-runtime ota-validation edge-ai-validation sil hil],
    endpoints: %w[discover plan execute-step validate command],
    adapters: %w[OPCUA MQTT SPARKPLUG MODBUS INDUSTRIAL_PROTOCOLS ECLIPSE_DITTO KUBEEDGE HISTORIAN OTA EDGE_AI VENDOR_PLC],
    fixture: "engines/edge-iot-industrial-engine/test-fixtures/batch24-acceptance-scenarios.json", expected: 36,
    migration: "V30__edge_iot_industrial_systems.sql", schema: "edge_industrial",
    attachment: "/Users/stephen/.codex/attachments/a41077a9-44a4-4228-900e-638a34ac82c1/pasted-text.txt" },
  { number: 25, engine: "operations-sre-itsm-engine", title: "Operations SRE and ITSM", port: 8099,
    runners: %w[operations-discovery event-correlation incident-simulation runbook-automation capacity-simulation continuity-drill],
    endpoints: %w[discover events incidents changes remediate validate],
    adapters: %w[ITSM CMDB SERVICENOW_CSDM OPENTELEMETRY METRICS LOGS TRACES PAGER CHAT STATUS_PAGE CLOUD DEPLOYMENT SECURITY BUSINESS_KPI],
    fixture: "engines/operations-sre-itsm-engine/test-fixtures/batch25-acceptance-scenarios.json", expected: 44,
    migration: "V31__operations_sre_itsm.sql", schema: "operations_sre",
    attachment: "/Users/stephen/.codex/attachments/ba6b46b1-b372-46fd-9ba1-8f3e0c1e0421/pasted-text.txt" },
  { number: 26, engine: "enterprise-architecture-engine", title: "Enterprise Architecture and Portfolio", port: 8100,
    runners: %w[portfolio-analysis architecture-graph-analysis option-evaluation roadmap-simulation conformance-validation],
    endpoints: %w[discover assess plan evaluate decisions conformance],
    adapters: %w[TOGAF ARCHIMATE ISO_42010 IT4IT OPEN_AGILE_ARCHITECTURE EA_REPOSITORY CMDB SERVICE_CATALOG DATA_CATALOG TECHNOLOGY_RADAR PORTFOLIO_MANAGEMENT FINANCE MODELING_TOOL],
    fixture: "engines/enterprise-architecture-engine/test-fixtures/batch26-acceptance-scenarios.json", expected: 50,
    migration: "V32__enterprise_architecture_portfolio.sql", schema: "enterprise_architecture",
    attachment: "/Users/stephen/.codex/attachments/2ec8e7d5-c467-4e35-a099-4579be331139/pasted-text.txt" }
].freeze

NAME_ALIASES = {
  "data-integration-security-platform-and-domain-architecture-mapper" => "data-integration-security-platform-domain-architecture-mapper",
  "architecture-decision-record-review-board-and-governance-workflow" => "architecture-decision-review-board-and-governance-workflow",
  "enterprise-architecture-operating-model-adoption-and-value-measurement" => "enterprise-architecture-operating-model-adoption-metrics"
}.freeze

def run!(*command)
  output, status = Open3.capture2e(*command)
  raise "#{command.join(' ')} failed:\n#{output}" unless status.success?
  output
end

def scenario_assets(batch, source)
  matches = source.to_enum(:scan, /^## Scenario (\d+)：(.+)$/).map { Regexp.last_match }
  scenarios = matches.map.with_index do |match, index|
    tail = index + 1 < matches.length ? matches[index + 1].begin(0) : source.length
    body = source[match.end(0)...tail]
    text = body[/```text\s*(.*?)```/m, 1]&.strip || body.strip
    {
      "scenarioId" => "B#{batch[:number]}-S#{match[1].rjust(2, '0')}",
      "title" => match[2].strip,
      "requirements" => text,
      "safeOutcome" => "FAIL_CLOSED",
      "externalExecutionExpected" => false,
      "autoApprovalAllowed" => false
    }
  end
  raise "Batch #{batch[:number]} scenario count #{scenarios.length}, expected #{batch[:expected]}" unless scenarios.length == batch[:expected]

  destination = File.join(ROOT, batch[:fixture])
  FileUtils.mkdir_p(File.dirname(destination))
  File.write(destination, JSON.pretty_generate(scenarios) + "\n")
end

def sample_value(schema, key = "value")
  return schema["enum"].first if schema["enum"]
  case schema["type"]
  when "string" then "#{key}-fixture"
  when "number", "integer" then schema.fetch("minimum", 0)
  when "boolean" then false
  when "array" then []
  when "object" then (schema["required"] || []).to_h { |required| [required, sample_value(schema.dig("properties", required) || {}, required)] }
  else "#{key}-fixture"
  end
end

def schema_assets(batch, source)
  section = source[/^# [^\n]*核心\s*Schema(.*?)(?=\n---\n)/m, 1]
  raise "core schema section not found" unless section

  schemas = section.scan(/```json\s*(\{.*?\})\s*```/m).flatten
  schemas.each do |raw|
    schema = JSON.parse(raw)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    id = schema.fetch("$id").sub(/^elmos\./, "").sub(/\.v1$/, "").tr(".", "-")
    destination = File.join(ROOT, "contracts", "#{id}-schema", "#{id}.schema.json")
    FileUtils.mkdir_p(File.dirname(destination))
    File.write(destination, JSON.pretty_generate(schema) + "\n")
    fixture = File.join(ROOT, "engines", batch[:engine], "test-fixtures", "#{id}-fixture.json")
    FileUtils.mkdir_p(File.dirname(fixture))
    File.write(fixture, JSON.pretty_generate(sample_value(schema, id)) + "\n")
  end
  schemas.length
end

def delivery_assets(batch, source)
  engine_root = File.join(ROOT, "engines", batch[:engine])
  matrix = source[/^# [^\n]*测试Fixture矩阵\n\n```text\n(.*?)\n```/m, 1]
  raise "Batch #{batch[:number]} fixture matrix not found" unless matrix
  entries = matrix.lines.map(&:strip).reject(&:empty?).map { |line| line.sub(/^[│├└─\s]+/, "").sub(%r{/$}, "") }
  File.write(File.join(engine_root, "test-fixtures/fixture-matrix.json"), JSON.pretty_generate({
    schemaVersion: "1.0", batch: batch[:number], externalStatus: "NOT_RUN", entries: entries
  }) + "\n")

  batch[:runners].each do |runner|
    directory = File.join(ROOT, "sandbox-images", runner)
    FileUtils.mkdir_p(directory)
    File.write(File.join(directory, "runner-policy.json"), JSON.pretty_generate({
      schemaVersion: "1.0", batch: batch[:number], runnerProfile: runner,
      imageStatus: "NOT_CONFIGURED", rootless: true, readOnlyRootFilesystem: true,
      allowPrivilegeEscalation: false, capabilitiesDrop: ["ALL"], networkDefault: "DENY",
      networkAllowlistRequired: true, shortLivedJobLeaseRequired: true,
      exactEnvironmentScopeRequired: true, tenantIsolationRequired: true,
      productionMutationDefault: "DENY", externalOperationExecuted: false,
      evidenceStatus: "NOT_RUN"
    }) + "\n")
  end

  FileUtils.mkdir_p(File.join(engine_root, "policies"))
  File.write(File.join(engine_root, "policies/adapters-v1.json"), JSON.pretty_generate({
    schemaVersion: "1.0", adapters: batch[:adapters].to_h { |adapter| [adapter, "NOT_CONFIGURED"] },
    tokenPolicy: "SHORT_LIVED_SCOPED", discoveryDefault: "READ_ONLY"
  }) + "\n")
  File.write(File.join(engine_root, "policies/safety-boundary-v1.json"), JSON.pretty_generate({
    schemaVersion: "1.0", batch: batch[:number], controlPlaneExecution: false,
    productionMutationDefault: "DENY", humanDecisionAutoGrant: false,
    workerMayModifyGate: false, notRunCanPass: false, riskAcceptanceAuthority: "HUMAN_ONLY"
  }) + "\n")
  FileUtils.mkdir_p(File.join(engine_root, "validation-profiles"))
  File.write(File.join(engine_root, "validation-profiles/hard-gates-v1.json"), JSON.pretty_generate({
    schemaVersion: "1.0", batch: batch[:number], outcomeOnMissingEvidence: "BLOCKED",
    outcomeOnStaleEvidence: "BLOCKED", independentEvidenceRequired: true,
    productionDecisionAuthority: "INDEPENDENT_CONTROL_PLANE_AND_HUMAN"
  }) + "\n")

  FileUtils.mkdir_p(File.join(engine_root, "openapi"))
  paths = batch[:endpoints].map do |endpoint|
    request = %w[execute-step self-service train deploy command changes remediate decisions].include?(endpoint) ? "ExecuteStepRequest" : "JobRequest"
    <<~PATH
        /engine/v1/#{endpoint}:
          post:
            operationId: #{endpoint.tr('-', '_')}
            requestBody:
              required: true
              content:
                application/json:
                  schema: { $ref: '#/components/schemas/#{request}' }
            responses:
              '202': { description: Accepted or fail-closed result }
    PATH
  end.join.lines.map { |line| "  #{line}" }.join
  openapi = <<~YAML
    openapi: 3.1.0
    info:
      title: ELMOS #{batch[:title]} Engine
      version: 1.0.0
    servers:
      - url: http://localhost:#{batch[:port]}
    paths:
      /engine/v1/capabilities:
        get:
          operationId: capabilities
          responses:
            '200': { description: Fail-closed capabilities }
    #{paths.rstrip}
      /engine/v1/jobs/{jobId}:
        get:
          operationId: job
          parameters:
            - { name: jobId, in: path, required: true, schema: { type: string } }
            - { name: organizationId, in: query, required: true, schema: { type: string } }
          responses:
            '200': { description: Tenant-scoped job }
      /engine/v1/jobs/{jobId}/cancel:
        post:
          operationId: cancel
          parameters:
            - { name: jobId, in: path, required: true, schema: { type: string } }
            - { name: organizationId, in: query, required: true, schema: { type: string } }
          responses:
            '200': { description: Cancellation result }
    components:
      schemas:
        JobRequest:
          type: object
          required: [organizationId, repositorySnapshotRef, workspaceRef, profile, correlationId, idempotencyKey]
          properties:
            organizationId: { type: string }
            repositorySnapshotRef: { type: string }
            workspaceRef: { type: string }
            profile: { type: string }
            correlationId: { type: string }
            idempotencyKey: { type: string }
        ExecuteStepRequest:
          type: object
          required: [organizationId, migrationRunId, stepDefinition, workspaceRef, sourceCommit, executionBudget, correlationId, idempotencyKey]
          properties:
            organizationId: { type: string }
            migrationRunId: { type: string }
            migrationPlanVersion: { type: integer }
            stepDefinition: { type: object }
            workspaceRef: { type: string }
            sourceCommit: { type: string }
            executionBudget: { type: object }
            policy: { type: object }
            correlationId: { type: string }
            idempotencyKey: { type: string }
  YAML
  File.write(File.join(engine_root, "openapi/engine-v1.yaml"), openapi)

  artifact = File.basename(engine_root)
  dockerfile = <<~DOCKER
    FROM maven:3.9.11-eclipse-temurin-21@sha256:66f7d4ef603ef4fe9592494c9f7981e3b2af447010225d33738efda5556f33c2 AS build
    WORKDIR /workspace
    COPY . .
    RUN mvn -B -pl engines/#{artifact} -am package -DskipTests

    FROM eclipse-temurin:21.0.8_9-jre-alpine@sha256:5d86cf6fece431ed36d8e93edce193127ce1659067650691b4399a693b9b8f69
    RUN addgroup -S elmos && adduser -S -G elmos -u 10001 elmos
    WORKDIR /app
    COPY --from=build /workspace/engines/#{artifact}/target/*-exec.jar app.jar
    USER 10001
    EXPOSE #{batch[:port]}
    ENTRYPOINT ["java","-jar","/app/app.jar"]
  DOCKER
  File.write(File.join(engine_root, "Dockerfile"), dockerfile)
  File.write(File.join(engine_root, "README.md"), <<~MARKDOWN)
    # ELMOS #{batch[:title]} Engine

    Batch #{batch[:number]} 独立 Java 21 Worker，默认端口 `#{batch[:port]}`。所有 Provider Adapter 初始为
    `NOT_CONFIGURED`；无短期 Job Lease、精确环境范围、专用授权或独立生产批准时保持
    `NOT_RUN`、`INCONCLUSIVE` 或 `BLOCKED`。控制面不执行客户操作，Worker 不得修改 Gate、接受风险或授予人工决定。
  MARKDOWN
end

def skill_assets(batch, source)
  blocks = source.scan(/```markdown\s*(---\nname: .*?\n---.*?)(?:```|````)/m).flatten
  raise "Batch #{batch[:number]} skill count #{blocks.length}, expected 18" unless blocks.length == 18

  blocks.each_with_index do |block, index|
    original = block[/^name:\s*([a-z0-9-]+)$/m, 1]
    raise "skill name missing" unless original
    name = NAME_ALIASES.fetch(original, original)
    content = block.sub(/^name:\s*#{Regexp.escape(original)}$/m, "name: #{name}").rstrip + "\n"
    directory = File.join(ROOT, "agent-skills/runtime", name)
    unless File.directory?(directory)
      run!(PYTHON, File.join(SKILL_TOOL, "init_skill.py"), name, "--path", File.join(ROOT, "agent-skills/runtime"),
           "--interface", "display_name=Batch #{batch[:number]} #{format('%03d', index + 1)}",
           "--interface", "short_description=Run Batch #{batch[:number]} runtime contract safely",
           "--interface", "default_prompt=Use $#{name} to apply its fail-closed ELMOS runtime contract.")
    end
    File.write(File.join(directory, "SKILL.md"), content)
    run!(PYTHON, File.join(SKILL_TOOL, "generate_openai_yaml.py"), directory,
         "--interface", "display_name=Batch #{batch[:number]} #{format('%03d', index + 1)}",
         "--interface", "short_description=Run Batch #{batch[:number]} runtime contract safely",
         "--interface", "default_prompt=Use $#{name} to apply its fail-closed ELMOS runtime contract.")
  end
end

def migration_asset(batch, source)
  block = source[/^# [^\n]*新增数据库表\n\n```text\n(.*?)\n```/m, 1]
  raise "Batch #{batch[:number]} table list not found" unless block
  tables = block.lines.map(&:strip).reject(&:empty?)
  append_only = tables.select do |name|
    name.match?(/(?:versions|observations|runs|results|events|records|timelines|histories|approvals|decisions|measurements|findings|executions|communications|handoffs|inferences|traces|spans|points|feedback|reviews)$/)
  end
  quote = ->(values) { values.map { |value| "        '#{value}'" }.join(",\n") }
  sql = <<~SQL
    -- ELMOS Skill Pack Batch #{batch[:number]}. Generated from the authoritative attachment table inventory.
    -- A dedicated namespace preserves logical names without stealing authority from earlier batch tables.
    -- These tables record tenant-scoped evidence and decisions; they do not execute provider or production actions.

    CREATE SCHEMA IF NOT EXISTS #{batch[:schema]};

    DO $$
    DECLARE
        target_schema text := '#{batch[:schema]}';
        table_name text;
        batch_tables text[] := ARRAY[
    #{quote.call(tables)}
        ];
        append_only_tables text[] := ARRAY[
    #{quote.call(append_only)}
        ];
    BEGIN
        FOREACH table_name IN ARRAY batch_tables LOOP
            EXECUTE format(
                'CREATE TABLE %I.%I (' ||
                'record_id varchar(96) PRIMARY KEY,' ||
                'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
                'tenant_id varchar(96) NOT NULL,' ||
                'domain_run_id varchar(160),' ||
                'workspace_ref varchar(512),' ||
                'owner_id varchar(160) NOT NULL,' ||
                'human_owner_id varchar(160) NOT NULL,' ||
                'status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
                'authority_status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
                'confidence numeric(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),' ||
                'source varchar(160) NOT NULL,' ||
                'source_record_ref varchar(512) NOT NULL,' ||
                'idempotency_key varchar(160) NOT NULL,' ||
                'evidence_status varchar(32) NOT NULL DEFAULT ''NOT_RUN'' CHECK (evidence_status IN (''NOT_RUN'',''INCONCLUSIVE'',''PASS'',''FAIL'',''BLOCKED'')),' ||
                'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
                'payload jsonb NOT NULL DEFAULT ''{}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
                'external_operation_executed boolean NOT NULL DEFAULT false,' ||
                'actual_execution_evidence_ref varchar(512),' ||
                'production_state_changed boolean NOT NULL DEFAULT false,' ||
                'human_approval_ref varchar(512),' ||
                'observed_at timestamptz NOT NULL,' ||
                'created_at timestamptz NOT NULL DEFAULT now(),' ||
                'updated_at timestamptz NOT NULL DEFAULT now(),' ||
                'CHECK (NOT external_operation_executed OR actual_execution_evidence_ref IS NOT NULL),' ||
                'CHECK (NOT production_state_changed OR human_approval_ref IS NOT NULL),' ||
                'CHECK (status NOT IN (''SUCCEEDED'',''APPROVED'',''PASS'') OR jsonb_array_length(evidence_refs) > 0),' ||
                'UNIQUE (organization_id, idempotency_key),' ||
                'UNIQUE (organization_id, source, source_record_ref))',
                target_schema, table_name);
            EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id)',
                           'idx_' || table_name || '_organization', target_schema, table_name);
            EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id, domain_run_id, status)',
                           'idx_' || table_name || '_domain_run', target_schema, table_name);
            EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, table_name);
            EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target_schema, table_name);
            EXECUTE format(
                'CREATE POLICY tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
                target_schema, table_name);
            IF table_name = ANY(append_only_tables) THEN
                EXECUTE format(
                    'CREATE TRIGGER batch_#{batch[:number]}_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                    target_schema, table_name);
            END IF;
        END LOOP;
    END;
    $$;
  SQL
  destination = File.join(ROOT, "modules/persistence/src/main/resources/db/migration", batch[:migration])
  File.write(destination, sql)
  tables.length
end

generated_skills = 0
generated_scenarios = 0
generated_schemas = 0
generated_tables = 0
BATCHES.each do |batch|
  source = File.read(batch[:attachment])
  scenario_assets(batch, source)
  generated_schemas += schema_assets(batch, source)
  skill_assets(batch, source)
  generated_tables += migration_asset(batch, source)
  delivery_assets(batch, source)
  generated_skills += 18
  generated_scenarios += batch[:expected]
end

puts JSON.generate(skills: generated_skills, schemas: generated_schemas, scenarios: generated_scenarios, tables: generated_tables)
