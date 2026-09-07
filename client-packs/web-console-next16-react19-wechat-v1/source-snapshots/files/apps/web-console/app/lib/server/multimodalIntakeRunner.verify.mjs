import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { registerHooks } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";

registerHooks({
  resolve(specifier, context, nextResolve) {
    try {
      return nextResolve(specifier, context);
    } catch (error) {
      if (specifier.startsWith(".") && !/\.[A-Za-z0-9]+$/.test(specifier)) {
        return nextResolve(`${specifier}.ts`, context);
      }
      throw error;
    }
  },
});

const { canonicalStrictJson } = await import("../../../lib/multimodal-intake/strictJson.ts");
const {
  MultimodalIntakeRunnerError,
  boundMultimodalProjectId,
  executeMultimodalSkill,
  multimodalChildEnvironment,
  parseMultimodalExecuteBody,
  readMultimodalProgressBatch,
  requiredMultimodalPermission,
  validateEngineEnvelope,
} = await import("./multimodalIntakeRunner.ts");
const { multimodalOperationCount } = await import("../multimodalSkillCatalog.ts");

const skill = "elmos-multimodal-input-orchestrator";
const traceId = "trace_runner_contract";
const requestDigest = "a".repeat(64);
const engineProjectId = "mmi-prj-test-scope";
let checks = 0;

function digest(value) {
  return createHash("sha256").update(canonicalStrictJson(value)).digest("hex");
}

function assertExactFields(value, fields) {
  assert.ok(value !== null && typeof value === "object" && !Array.isArray(value));
  assert.deepEqual(Object.keys(value).sort(), [...fields].sort());
}

function assertExactEngineOutputFields(value, fields) {
  assertExactFields(value, [...fields, "handler_id", "phase", "metrics"]);
  assert.equal(typeof value.handler_id, "string");
  assert.equal(typeof value.phase, "string");
  assert.ok(value.metrics !== null && typeof value.metrics === "object");
  assert.equal(Array.isArray(value.metrics), false);
}

const sourceRefFields = [
  "schema_version", "content_id", "content_version", "content_digest",
  "asset_sha256", "target_kind", "target_digest", "snapshot_id",
  "snapshot_digest", "head_version", "head_value_digest", "source_digest",
  "provenance_digest", "original_value_client_digest",
  "original_value_digest_contract",
];
const sourceSummaryFields = [
  "schema_version", "content_id", "content_version", "target_kind", "target",
  "target_digest", "confidence", "head_version", "head_direction",
  "head_correction_version", "original_value_client_digest",
  "original_value_digest_contract", "source_ref",
];
const sourceDetailFields = [...sourceSummaryFields, "original_value"];
const sourceBoundEnqueueFields = [
  "content_id", "expected_asset_version", "target_kind", "target_digest",
  "expected_head_version", "expected_snapshot_id", "expected_snapshot_digest",
  "expected_head_value_digest", "original_value_digest", "reason",
];
const enqueuePreparationFields = [
  "schema_version", "recovery_handle", "request_digest", "state", "safe_to_clear",
  "expires_at", "prepared_at", "executed_at", "task_id", "enqueue_input",
];
const reviewTaskFields = [
  "task_id", "tenant_id", "project_id", "asset_id", "target_kind", "target",
  "original_value", "source_digest", "source_ref", "confidence", "reason",
  "state", "current_correction_version", "current_correction_digest",
  "effective_version", "effective_digest", "claim_actor_id", "claim_fence",
  "claim_expires_at", "version", "created_by", "created_at", "updated_at",
  "closed_at",
];
const reviewTaskSummaryFields = [
  "schema_version", "task_id", "asset_id", "target_kind", "source_digest",
  "confidence", "reason", "state", "current_correction_version",
  "current_correction_digest", "effective_version", "effective_digest",
  "claim_actor_id", "claim_fence", "claim_expires_at", "version",
  "created_at", "updated_at", "closed_at",
];
const reviewCorrectionFields = [
  "correction_id", "tenant_id", "project_id", "task_id",
  "correction_version", "parent_correction_version", "target_kind", "target",
  "original_value", "corrected_value", "source_digest", "actor_id", "reason",
  "created_at", "correction_digest",
];
const reviewDecisionFields = [
  "decision_id", "tenant_id", "project_id", "task_id", "decision_version",
  "decision", "prior_state", "next_state", "correction_version",
  "correction_digest", "source_digest", "actor_id", "reason", "created_at",
];
const reviewPropagationSummaryFields = [
  "propagation_id", "task_id", "decision_id", "correction_version", "channel",
  "direction", "payload_digest", "effective_value_digest", "state",
  "claim_fence", "claim_expires_at", "dispatch_started_at", "failure_code",
  "reconciliation_required", "version", "updated_at",
];
const reviewEffectiveFields = [
  "materialized", "state", "effective_version", "effective_value",
  "effective_value_digest", "channels",
];
const reviewReservationFields = [
  "schema_version", "reservation_id", "tenant_id", "project_id", "asset_id",
  "asset_version", "asset_content_digest", "asset_sha256", "target_kind",
  "target_digest", "snapshot_id", "snapshot_digest", "reserved_head_version",
  "reserved_head_value_digest", "task_id", "decision_id", "decision_action",
  "correction_version", "correction_digest", "source_digest", "source_ref_digest",
  "parent_reservation_id", "reservation_fence", "binding_digest", "state",
  "state_version", "materialized_head_version", "failure_code", "created_at",
  "updated_at", "completed_at",
];

function fullEnvelope(overrides = {}) {
  const unsigned = {
    schema_version: "1.0.0",
    skill,
    operation: "bootstrap_project",
    status: "SUCCEEDED",
    retryable: false,
    trace_id: traceId,
    request_digest: requestDigest,
    implementation_state: "CODE_IMPLEMENTED_LOCAL",
    external_evidence: "NOT_RUN",
    certification: "NOT_CERTIFIED",
    output: { project_id: engineProjectId },
    ...overrides,
  };
  return { ...unsigned, result_digest: digest(unsigned), _http_status: 200 };
}

function rejected(envelope, operation, code) {
  assert.throws(
    () => validateEngineEnvelope(
      envelope,
      skill,
      operation,
      traceId,
      requestDigest,
      engineProjectId,
    ),
    (error) => {
      assert.ok(error instanceof MultimodalIntakeRunnerError);
      assert.equal(error.status, 502);
      assert.equal(error.code, code);
      return true;
    },
  );
  checks += 1;
}

assert.equal(
  validateEngineEnvelope(
    fullEnvelope(),
    skill,
    "bootstrap_project",
    traceId,
    requestDigest,
    engineProjectId,
  ).status,
  "SUCCEEDED",
);
checks += 1;

rejected(
  fullEnvelope({ status: ["SUCCEEDED"] }),
  "bootstrap_project",
  "MULTIMODAL_ENGINE_RESPONSE_INVALID",
);
rejected(
  fullEnvelope({ implementation_state: ["CODE_IMPLEMENTED_LOCAL"] }),
  "bootstrap_project",
  "MULTIMODAL_ENGINE_RESPONSE_INVALID",
);
rejected(
  fullEnvelope({ operation: "bootstrap-project", output: { project_id: "wrong-project" } }),
  "bootstrap-project",
  "MULTIMODAL_ENGINE_PROJECT_SCOPE_INVALID",
);

const businessBlocked = fullEnvelope({
  status: "BLOCKED",
  code: "BOOTSTRAP_POLICY_BLOCKED",
  output: {},
});
assert.equal(
  validateEngineEnvelope(
    businessBlocked,
    skill,
    "bootstrap_project",
    traceId,
    requestDigest,
    engineProjectId,
  ).status,
  "BLOCKED",
);
checks += 1;

for (const [transportStatus, status, accepted] of [
  [404, "BLOCKED", true],
  [500, "FAILED", true],
  [404, "FAILED", false],
  [500, "BLOCKED", false],
]) {
  const envelope = {
    schema_version: "1.0.0",
    status,
    code: "BOUNDARY_TEST",
    retryable: false,
    _http_status: transportStatus,
  };
  if (accepted) {
    assert.equal(
      validateEngineEnvelope(
        envelope,
        skill,
        "bootstrap_project",
        traceId,
        requestDigest,
        engineProjectId,
      ).status,
      status,
    );
    checks += 1;
  } else {
    rejected(envelope, "bootstrap_project", "MULTIMODAL_ENGINE_RESPONSE_INVALID");
  }
}

function browserRequest(overrides = {}) {
  const unsigned = {
    schema_version: "multimodal-intake-browser-request-v1",
    skill,
    operation: "bootstrap_project",
    projectId: "project-a",
    input: {},
    ...overrides,
  };
  return { ...unsigned, request_digest: digest(unsigned) };
}

assert.equal(parseMultimodalExecuteBody(browserRequest()).operation, "bootstrap_project");
checks += 1;

assert.equal(multimodalOperationCount, 147);
assert.equal(requiredMultimodalPermission(skill, "bootstrap_project"), "intake:admin");
assert.equal(requiredMultimodalPermission(skill, "get_session"), "intake:read");
assert.equal(requiredMultimodalPermission(skill, "create_session"), "intake:write");
assert.equal(
  requiredMultimodalPermission("elmos-human-review-and-correction", "correct"),
  "intake:review",
);
checks += 5;

assert.throws(
  () => parseMultimodalExecuteBody(browserRequest({ operation: "undeclared_operation" })),
  (error) => {
    assert.ok(error instanceof MultimodalIntakeRunnerError);
    assert.equal(error.code, "MULTIMODAL_OPERATION_UNKNOWN");
    return true;
  },
);
checks += 1;

await assert.rejects(
  executeMultimodalSkill(
    { tenantId: "tenant-no-side-effect", actor: "actor-no-side-effect" },
    {
      skill,
      operation: "undeclared_operation",
      projectId: "project-no-side-effect",
      input: {},
    },
    "unknown-operation-no-side-effect-0001",
  ),
  (error) => {
    assert.ok(error instanceof MultimodalIntakeRunnerError);
    assert.equal(error.code, "MULTIMODAL_OPERATION_UNKNOWN");
    return true;
  },
);
checks += 1;

const childEnvironment = multimodalChildEnvironment("/trusted/engine/src");
assert.deepEqual(Object.keys(childEnvironment).sort(), [
  "NODE_ENV", "PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "PYTHONPATH", "PYTHONUTF8",
]);
assert.equal(childEnvironment.PYTHONPATH, "/trusted/engine/src");
assert.equal(childEnvironment.AWS_SECRET_ACCESS_KEY, undefined);
checks += 3;

const projectScopeA = boundMultimodalProjectId(
  { tenantId: "tenant-scope-a", actor: "actor-one" },
  "project-alias",
);
assert.equal(
  projectScopeA,
  boundMultimodalProjectId(
    { tenantId: "tenant-scope-a", actor: "actor-two" },
    "project-alias",
  ),
);
assert.notEqual(
  projectScopeA,
  boundMultimodalProjectId(
    { tenantId: "tenant-scope-b", actor: "actor-one" },
    "project-alias",
  ),
);
checks += 2;

const realIdentity = { tenantId: "tenant-bff-review", actor: "reviewer-bff" };
const realProjectAlias = "project-bff-review";
const realEngineProjectId = `mmi-prj-${createHash("sha256")
  .update("elmos-multimodal-intake-project-v1")
  .update("\0")
  .update(realIdentity.tenantId)
  .update("\0")
  .update(realProjectAlias)
  .digest("hex")}`;
const realDataRoot = await mkdtemp(path.join(tmpdir(), "elmos-mmi-bff-review-"));
await chmod(realDataRoot, 0o700);
const realEnvironment = {
  dataRoot: process.env.ELMOS_MULTIMODAL_INTAKE_DATA_ROOT,
  endpoint: process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT,
  token: process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN,
  nodeEnv: process.env.NODE_ENV,
};
try {
  await writeFile(
    path.join(realDataRoot, "trusted-context-v1.json"),
    JSON.stringify({
      schema_version: "1.0",
      bindings: [{
        tenant_id: realIdentity.tenantId,
        project_id: realEngineProjectId,
        actor_id: realIdentity.actor,
        context_epoch: "bff-review-context-v1",
        policy: {
          human_review: {
            version: "bff-review-policy-v1",
            tenant_id: realIdentity.tenantId,
            project_id: realEngineProjectId,
            allowed_actions: [
              "correct", "source_list", "source_get", "enqueue_prepare",
              "enqueue_execute", "enqueue", "get", "list", "claim", "edit",
              "current_correction", "approve", "reject",
              "reopen", "revert", "propagation_status",
            ],
            allowed_actor_ids: [realIdentity.actor],
          },
        },
        capabilities: {
          // This deliberately stale value proves the bridge replaces mutable
          // review state with the exact IntakeStore snapshot.
          human_review_state: {
            version: "stale-browser-adjacent-state",
            tenant_id: "wrong-tenant",
            project_id: "wrong-project",
            content_id: "wrong-content",
            current_version: 999,
            current_digest: `sha256:${"0".repeat(64)}`,
          },
        },
      }],
    }),
    { mode: 0o600 },
  );
  process.env.ELMOS_MULTIMODAL_INTAKE_DATA_ROOT = realDataRoot;
  delete process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT;
  delete process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN;
  process.env.NODE_ENV = "test";

  const realExecute = (skillName, operation, input, key) => executeMultimodalSkill(
    realIdentity,
    { skill: skillName, operation, projectId: realProjectAlias, input },
    key,
  );
  const bootstrap = await realExecute(
    "elmos-multimodal-input-orchestrator",
    "bootstrap_project",
    {},
    "bff-real-bootstrap-0001",
  );
  assert.equal(bootstrap.status, "SUCCEEDED");
  assert.equal(bootstrap.output.project_id, realEngineProjectId);

  const created = await realExecute(
    "elmos-multimodal-input-orchestrator",
    "create_session",
    { requested_role: "PRIMARY" },
    "bff-real-session-0001",
  );
  const sessionId = created.output.session_id;
  assert.equal(typeof sessionId, "string");
  const content = Buffer.from("# Trusted review source\nHuman correction is versioned.\n", "utf8");
  const contentDigest = createHash("sha256").update(content).digest("hex");
  const started = await realExecute(
    "elmos-secure-resumable-upload",
    "start",
    {
      session_id: sessionId,
      display_name: "review/source.md",
      declared_media_type: "text/markdown",
      expected_size: content.byteLength,
      expected_sha256: contentDigest,
    },
    "bff-real-upload-start-0001",
  );
  const uploadSessionId = started.output.upload_session_id;
  const assetId = started.output.asset_id;
  assert.equal(typeof uploadSessionId, "string");
  assert.equal(typeof assetId, "string");
  await realExecute(
    "elmos-secure-resumable-upload",
    "upload_part",
    {
      upload_session_id: uploadSessionId,
      part_number: 0,
      byte_offset: 0,
      sha256: contentDigest,
      data_b64: content.toString("base64"),
    },
    "bff-real-upload-part-0001",
  );
  await realExecute(
    "elmos-secure-resumable-upload",
    "commit",
    { upload_session_id: uploadSessionId },
    "bff-real-upload-commit-0001",
  );
  const processed = await realExecute(
    "elmos-multimodal-input-orchestrator",
    "process_session",
    {
      session_id: sessionId,
      max_attempts: 3,
      expected_asset_generation_digest: createHash("sha256").update(assetId).digest("hex"),
    },
    "bff-real-process-0001",
  );
  const processedAsset = processed.output.assets.find((asset) => asset.asset_id === assetId);
  assert.ok(processedAsset);
  assert.equal(processedAsset.status, "NEEDS_REVIEW");
  assert.ok(Number.isSafeInteger(processedAsset.version));

  const correctionInput = {
    content_id: assetId,
    expected_version: processedAsset.version,
    value: { confidence: 1e-7, text: "Cafe\u0301 人工复核" },
    reason: "BFF_REAL_RUNTIME_REVIEW",
  };
  const corrected = await realExecute(
    "elmos-human-review-and-correction",
    "correct",
    correctionInput,
    "bff-real-correction-0001",
  );
  assert.equal(corrected.status, "SUCCEEDED");
  assert.equal(corrected.code, "CORRECTION_VERSION_CREATED");
  assert.equal(corrected.output.asset_status, "NEEDS_REVIEW");
  assert.equal(corrected.output.asset_version, processedAsset.version + 1);
  assert.equal(corrected.output.rebuild_state, "NOT_RUN");
  assert.ok(corrected.output.rebuild_tasks.every((task) => task.state === "NOT_RUN"));
  assert.equal(Object.hasOwn(correctionInput, "current"), false);

  const replayedCorrection = await realExecute(
    "elmos-human-review-and-correction",
    "correct",
    correctionInput,
    "bff-real-correction-0001",
  );
  assert.deepEqual(replayedCorrection.output, corrected.output);

  const sourceListInput = {
    content_id: assetId,
    expected_asset_version: corrected.output.asset_version,
    kinds: ["TEXT"],
    limit: 200,
    cursor: null,
  };
  assertExactFields(sourceListInput, [
    "content_id", "expected_asset_version", "kinds", "limit", "cursor",
  ]);
  const listedSources = await realExecute(
    "elmos-human-review-and-correction",
    "source_list",
    sourceListInput,
    "bff-real-review-source-list-0001",
  );
  assert.equal(listedSources.status, "SUCCEEDED");
  assert.equal(listedSources.code, "HUMAN_REVIEW_SOURCES_LISTED");
  assertExactEngineOutputFields(listedSources.output, ["sources", "next_cursor", "total"]);
  assert.equal(listedSources.output.total, 1);
  assert.equal(listedSources.output.next_cursor, null);
  assert.equal(listedSources.output.sources.length, 1);
  const sourceSummary = listedSources.output.sources[0];
  assertExactFields(sourceSummary, sourceSummaryFields);
  assert.equal(sourceSummary.schema_version, "human-review-source-summary-v1");
  assert.equal(sourceSummary.content_id, assetId);
  assert.equal(sourceSummary.content_version, corrected.output.asset_version);
  assert.equal(sourceSummary.target_kind, "TEXT");
  assertExactFields(sourceSummary.target, ["path"]);
  assert.match(
    sourceSummary.target.path,
    /^human_review_corrections\/correction-[0-9a-f]{32}\/value$/,
  );
  assert.match(sourceSummary.target_digest, /^sha256:[0-9a-f]{64}$/);
  assert.equal(sourceSummary.confidence, 1);
  assert.equal(sourceSummary.head_version, 1);
  assert.equal(sourceSummary.head_direction, "SNAPSHOT");
  assert.equal(sourceSummary.head_correction_version, 0);
  assert.equal(
    sourceSummary.original_value_digest_contract,
    "sha256:rfc8785-ijson-safeint-v1",
  );
  const expectedOriginalValueDigest = `sha256:${digest(correctionInput.value)}`;
  assert.equal(sourceSummary.original_value_client_digest, expectedOriginalValueDigest);
  assertExactFields(sourceSummary.source_ref, sourceRefFields);

  const sourceGetInput = {
    content_id: assetId,
    expected_asset_version: corrected.output.asset_version,
    target_kind: sourceSummary.target_kind,
    target_digest: sourceSummary.target_digest,
    expected_head_version: sourceSummary.head_version,
  };
  assertExactFields(sourceGetInput, [
    "content_id", "expected_asset_version", "target_kind", "target_digest",
    "expected_head_version",
  ]);
  const retrievedSource = await realExecute(
    "elmos-human-review-and-correction",
    "source_get",
    sourceGetInput,
    "bff-real-review-source-get-0001",
  );
  assert.equal(retrievedSource.status, "SUCCEEDED");
  assert.equal(retrievedSource.code, "HUMAN_REVIEW_SOURCE_RETRIEVED");
  assertExactEngineOutputFields(retrievedSource.output, ["source"]);
  const sourceDetail = retrievedSource.output.source;
  assertExactFields(sourceDetail, sourceDetailFields);
  assert.equal(sourceDetail.schema_version, "human-review-source-detail-v1");
  assert.deepEqual(sourceDetail.target, sourceSummary.target);
  assert.deepEqual(sourceDetail.original_value, correctionInput.value);
  assert.deepEqual(sourceDetail.source_ref, sourceSummary.source_ref);
  assert.equal(sourceDetail.original_value_client_digest, expectedOriginalValueDigest);
  const sourceRef = sourceDetail.source_ref;
  assertExactFields(sourceRef, sourceRefFields);
  assert.equal(sourceRef.schema_version, "human-review-source-ref-v2");
  assert.equal(sourceRef.content_id, assetId);
  assert.equal(sourceRef.content_version, corrected.output.asset_version);
  assert.equal(sourceRef.asset_sha256, `sha256:${contentDigest}`);
  assert.equal(sourceRef.target_kind, sourceDetail.target_kind);
  assert.equal(sourceRef.target_digest, sourceDetail.target_digest);
  assert.equal(sourceRef.head_version, sourceDetail.head_version);
  assert.equal(sourceRef.original_value_client_digest, expectedOriginalValueDigest);
  assert.equal(
    sourceRef.original_value_digest_contract,
    "sha256:rfc8785-ijson-safeint-v1",
  );
  for (const field of [
    "content_digest", "snapshot_digest", "head_value_digest", "source_digest",
    "provenance_digest",
  ]) {
    assert.match(sourceRef[field], /^sha256:[0-9a-f]{64}$/);
  }
  assert.equal(typeof sourceRef.snapshot_id, "string");

  const enqueueInput = {
    content_id: assetId,
    expected_asset_version: corrected.output.asset_version,
    target_kind: sourceDetail.target_kind,
    target_digest: sourceDetail.target_digest,
    expected_head_version: sourceDetail.head_version,
    expected_snapshot_id: sourceRef.snapshot_id,
    expected_snapshot_digest: sourceRef.snapshot_digest,
    expected_head_value_digest: sourceRef.head_value_digest,
    original_value_digest: expectedOriginalValueDigest,
    reason: "BFF_REAL_RUNTIME_REVIEW",
  };
  assertExactFields(enqueueInput, sourceBoundEnqueueFields);
  assert.equal(Object.hasOwn(enqueueInput, "target"), false);
  assert.equal(Object.hasOwn(enqueueInput, "original_value"), false);
  assert.equal(Object.hasOwn(enqueueInput, "confidence"), false);
  const recoveryHandle = "bff-real-review-recovery-handle-0001";
  const executeIdempotencyKey = "bff-real-review-enqueue-execute-0001";
  const prepared = await realExecute(
    "elmos-human-review-and-correction",
    "enqueue_prepare",
    {
      recovery_handle: recoveryHandle,
      execute_idempotency_key: executeIdempotencyKey,
      ...enqueueInput,
    },
    "bff-real-review-enqueue-prepare-0001",
  );
  assert.equal(prepared.status, "SUCCEEDED");
  assert.equal(prepared.code, "HUMAN_REVIEW_ENQUEUE_PREPARED");
  assertExactEngineOutputFields(prepared.output, ["preparation"]);
  assertExactFields(prepared.output.preparation, enqueuePreparationFields);
  assert.equal(prepared.output.preparation.schema_version, "human-review-enqueue-preparation-v1");
  assert.equal(prepared.output.preparation.recovery_handle, recoveryHandle);
  assert.equal(prepared.output.preparation.request_digest, `sha256:${digest(enqueueInput)}`);
  assert.equal(prepared.output.preparation.state, "PREPARED");
  assert.equal(prepared.output.preparation.safe_to_clear, false);
  assert.equal(prepared.output.preparation.executed_at, null);
  assert.equal(prepared.output.preparation.task_id, null);
  assert.deepEqual(prepared.output.preparation.enqueue_input, enqueueInput);

  const enqueued = await realExecute(
    "elmos-human-review-and-correction",
    "enqueue_execute",
    { recovery_handle: recoveryHandle },
    executeIdempotencyKey,
  );
  assert.equal(enqueued.status, "SUCCEEDED");
  assert.equal(enqueued.code, "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION");
  assertExactEngineOutputFields(enqueued.output, ["preparation", "task"]);
  assertExactFields(enqueued.output.preparation, enqueuePreparationFields);
  assert.equal(enqueued.output.preparation.state, "EXECUTED");
  assert.equal(enqueued.output.preparation.safe_to_clear, true);
  assert.equal(enqueued.output.preparation.recovery_handle, recoveryHandle);
  assert.equal(enqueued.output.preparation.request_digest, `sha256:${digest(enqueueInput)}`);
  assert.deepEqual(enqueued.output.preparation.enqueue_input, enqueueInput);
  assertExactFields(enqueued.output.task, reviewTaskFields);
  assert.equal(enqueued.output.task.state, "QUEUED");
  assert.equal(enqueued.output.task.version, 1);
  assert.equal(enqueued.output.task.tenant_id, realIdentity.tenantId);
  assert.equal(enqueued.output.task.project_id, realEngineProjectId);
  assert.equal(enqueued.output.task.asset_id, assetId);
  assert.deepEqual(enqueued.output.task.target, sourceDetail.target);
  assert.deepEqual(enqueued.output.task.original_value, sourceDetail.original_value);
  assert.equal(enqueued.output.task.confidence, sourceDetail.confidence);
  assert.deepEqual(enqueued.output.task.source_ref, sourceRef);
  assert.equal(enqueued.output.task.source_digest, sourceRef.head_value_digest);
  const reviewTaskId = enqueued.output.task.task_id;

  assert.equal(enqueued.output.preparation.task_id, reviewTaskId);

  // Recovery persists only the opaque handle and exact execute key. Replaying
  // them returns the durable execution receipt without browser-side source data.
  const replayedEnqueue = await realExecute(
    "elmos-human-review-and-correction",
    "enqueue_execute",
    { recovery_handle: recoveryHandle },
    executeIdempotencyKey,
  );
  assert.equal(replayedEnqueue.code, "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION");
  assert.deepEqual(replayedEnqueue.output, enqueued.output);

  const retrievedTask = await realExecute(
    "elmos-human-review-and-correction",
    "get",
    { task_id: reviewTaskId },
    "bff-real-review-get-0001",
  );
  assert.equal(retrievedTask.code, "HUMAN_REVIEW_TASK_RETRIEVED");
  assertExactEngineOutputFields(retrievedTask.output, ["task"]);
  assertExactFields(retrievedTask.output.task, reviewTaskFields);
  assert.deepEqual(retrievedTask.output.task, enqueued.output.task);

  const listed = await realExecute(
    "elmos-human-review-and-correction",
    "list",
    { kinds: [], states: [], confidence_lte: 1, limit: 200, cursor: null },
    "bff-real-review-list-0001",
  );
  assert.equal(listed.code, "HUMAN_REVIEW_TASKS_LISTED");
  assertExactEngineOutputFields(listed.output, ["tasks", "next_cursor", "total"]);
  assert.equal(listed.output.total, 1);
  assert.equal(listed.output.next_cursor, null);
  assert.equal(listed.output.tasks.length, 1);
  assertExactFields(listed.output.tasks[0], reviewTaskSummaryFields);
  assert.equal(listed.output.tasks[0].schema_version, "human-review-task-summary-v1");
  assert.equal(listed.output.tasks[0].task_id, reviewTaskId);

  const claimToken = "bff-review-claim-token-0001";
  const claimed = await realExecute(
    "elmos-human-review-and-correction",
    "claim",
    {
      task_id: reviewTaskId,
      expected_version: enqueued.output.task.version,
      claim_token: claimToken,
      lease_seconds: 900,
    },
    "bff-real-review-claim-0001",
  );
  assert.equal(claimed.code, "HUMAN_REVIEW_TASK_CLAIMED");
  assertExactEngineOutputFields(claimed.output, ["task"]);
  assert.equal(claimed.output.task.state, "CLAIMED");
  assert.equal(claimed.output.task.claim_fence, 1);
  assertExactFields(claimed.output.task, reviewTaskFields);

  const editInput = {
    task_id: reviewTaskId,
    expected_version: claimed.output.task.version,
    expected_correction_version: 0,
    claim_token: claimToken,
    claim_fence: claimed.output.task.claim_fence,
    correction: {
      value: "Human correction is approved and versioned.",
      reason: "BFF_REAL_RUNTIME_REVIEW",
    },
  };
  const edited = await realExecute(
    "elmos-human-review-and-correction",
    "edit",
    editInput,
    "bff-real-review-edit-0001",
  );
  assert.equal(edited.code, "HUMAN_REVIEW_CORRECTION_EDITED");
  assertExactEngineOutputFields(edited.output, ["task", "correction"]);
  assert.equal(edited.output.task.state, "EDITED");
  assert.equal(edited.output.task.current_correction_version, 1);
  assertExactFields(edited.output.task, reviewTaskFields);
  assertExactFields(edited.output.correction, reviewCorrectionFields);
  assert.match(edited.output.correction.correction_digest, /^sha256:[0-9a-f]{64}$/);

  const replayedEdit = await realExecute(
    "elmos-human-review-and-correction",
    "edit",
    editInput,
    "bff-real-review-edit-0001",
  );
  assert.equal(replayedEdit.code, "HUMAN_REVIEW_CORRECTION_EDITED");
  assert.deepEqual(replayedEdit.output, edited.output);

  const recoveredCorrection = await realExecute(
    "elmos-human-review-and-correction",
    "current_correction",
    { task_id: reviewTaskId },
    "bff-real-review-current-correction-0001",
  );
  assert.equal(
    recoveredCorrection.code,
    "HUMAN_REVIEW_CURRENT_CORRECTION_RETRIEVED",
  );
  assertExactEngineOutputFields(recoveredCorrection.output, ["correction"]);
  assertExactFields(recoveredCorrection.output.correction, reviewCorrectionFields);
  assert.deepEqual(recoveredCorrection.output.correction, edited.output.correction);
  assert.equal(recoveredCorrection.output.correction.task_id, reviewTaskId);
  assert.deepEqual(recoveredCorrection.output.correction.target, sourceDetail.target);
  assert.deepEqual(
    recoveredCorrection.output.correction.original_value,
    sourceDetail.original_value,
  );
  assert.equal(
    recoveredCorrection.output.correction.corrected_value,
    editInput.correction.value,
  );
  assert.equal(
    recoveredCorrection.output.correction.correction_digest,
    edited.output.task.current_correction_digest,
  );

  const recoveredEditedTask = await realExecute(
    "elmos-human-review-and-correction",
    "get",
    { task_id: reviewTaskId },
    "bff-real-review-get-after-edit-0001",
  );
  assert.equal(recoveredEditedTask.code, "HUMAN_REVIEW_TASK_RETRIEVED");
  assertExactEngineOutputFields(recoveredEditedTask.output, ["task"]);
  assertExactFields(recoveredEditedTask.output.task, reviewTaskFields);
  assert.deepEqual(recoveredEditedTask.output.task, edited.output.task);

  const approved = await realExecute(
    "elmos-human-review-and-correction",
    "approve",
    {
      task_id: reviewTaskId,
      expected_version: recoveredEditedTask.output.task.version,
      claim_token: claimToken,
      claim_fence: claimed.output.task.claim_fence,
      reason: "BFF_REAL_RUNTIME_REVIEW",
    },
    "bff-real-review-approve-0001",
  );
  assert.equal(approved.code, "HUMAN_REVIEW_CORRECTION_APPROVED");
  assert.equal(approved.output.task.state, "APPROVED");
  assertExactEngineOutputFields(approved.output, ["decision", "task", "propagations"]);
  assertExactFields(approved.output.decision, reviewDecisionFields);
  assertExactFields(approved.output.task, reviewTaskFields);
  for (const propagation of approved.output.propagations) {
    assertExactFields(propagation, reviewPropagationSummaryFields);
  }
  assert.deepEqual(
    approved.output.propagations.map((item) => [item.channel, item.state]),
    [
      ["content-index", "PENDING"],
      ["requirements", "PENDING"],
      ["project-memory", "PENDING"],
      ["downstream", "PENDING"],
    ],
  );
  const reservationStatus = await realExecute(
    "elmos-human-review-and-correction",
    "reservation_status",
    { task_id: reviewTaskId },
    "bff-real-review-reservation-status-0001",
  );
  assert.equal(
    reservationStatus.code,
    "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATUS",
  );
  assertExactEngineOutputFields(
    reservationStatus.output,
    ["schema_version", "task_id", "reservations"],
  );
  assert.equal(
    reservationStatus.output.schema_version,
    "human-review-target-head-reservation-status-v1",
  );
  assert.equal(reservationStatus.output.task_id, reviewTaskId);
  assert.equal(reservationStatus.output.reservations.length, 1);
  assertExactFields(reservationStatus.output.reservations[0], reviewReservationFields);
  assert.equal(reservationStatus.output.reservations[0].task_id, reviewTaskId);
  assert.equal(reservationStatus.output.reservations[0].decision_id, approved.output.decision.decision_id);
  assert.equal(reservationStatus.output.reservations[0].state, "PROPAGATING");
  const propagationStatus = await realExecute(
    "elmos-human-review-and-correction",
    "propagation_status",
    { task_id: reviewTaskId },
    "bff-real-review-status-0001",
  );
  assert.equal(propagationStatus.code, "HUMAN_REVIEW_PROPAGATION_STATUS");
  assert.equal(propagationStatus.output.task.task_id, reviewTaskId);
  assertExactEngineOutputFields(
    propagationStatus.output,
    ["task", "propagations", "effective"],
  );
  assertExactFields(propagationStatus.output.task, reviewTaskFields);
  assertExactFields(propagationStatus.output.effective, reviewEffectiveFields);
  for (const propagation of propagationStatus.output.propagations) {
    assertExactFields(propagation, reviewPropagationSummaryFields);
  }
  assert.equal(propagationStatus.output.effective.materialized, false);
  assert.equal(propagationStatus.output.propagations.length, 4);
  checks += 1;
} finally {
  if (realEnvironment.dataRoot === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_DATA_ROOT;
  else process.env.ELMOS_MULTIMODAL_INTAKE_DATA_ROOT = realEnvironment.dataRoot;
  if (realEnvironment.endpoint === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT;
  else process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT = realEnvironment.endpoint;
  if (realEnvironment.token === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN;
  else process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN = realEnvironment.token;
  if (realEnvironment.nodeEnv === undefined) delete process.env.NODE_ENV;
  else process.env.NODE_ENV = realEnvironment.nodeEnv;
  await rm(realDataRoot, { recursive: true, force: true });
}

const resetEndpoint = process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT;
const resetToken = process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN;
const progressToken = "progress-contract-token-000000000001";
const progressIdentity = { tenantId: "tenant-a", actor: "actor-a" };
const progressProjectAlias = "project-a";
const progressEngineProjectId = boundMultimodalProjectId(
  progressIdentity,
  progressProjectAlias,
);
const invalidJobProgressOverrides = new Map([
  ["job-invalid-event-type", { event_type: "processing.job.replayed" }],
  ["job-invalid-state", { state: "UNKNOWN" }],
  ["job-invalid-result", { result_status: "PASSED" }],
  ["job-invalid-attempt", { attempt: 4 }],
  ["job-invalid-max-attempts", { max_attempts: 0 }],
  ["job-invalid-timestamp", { occurred_at: "2026-02-30T00:00:00+00:00" }],
]);
let progressAuthorizedReads = 0;
const progressServer = createServer((request, response) => {
  const target = new URL(request.url ?? "/", "http://127.0.0.1");
  const resourceId = target.pathname.split("/").at(-2) ?? "";
  const taskProgress = target.pathname.includes("/progress/tasks/");
  const cursor = target.searchParams.get("cursor");
  if (
    request.method !== "GET"
    || request.headers.authorization !== `Bearer ${progressToken}`
    || request.headers.accept !== "text/event-stream"
    || request.headers["x-elmos-bound-tenant"] !== progressIdentity.tenantId
    || request.headers["x-elmos-bound-project"] !== progressEngineProjectId
    || request.headers["x-elmos-bound-actor"] !== progressIdentity.actor
  ) {
    response.writeHead(403, { "Content-Type": "application/json" });
    response.end('{"status":"BLOCKED","code":"BOUND_IDENTITY_MISMATCH","retryable":false}');
    return;
  }
  progressAuthorizedReads += 1;
  let body;
  if (cursor) {
    const sequence = Number(cursor.split("-", 3)[1]);
    const unsigned = {
      schema_version: "1.0.0",
      kind: taskProgress ? "TASK_PROGRESS_HEARTBEAT" : "JOB_PROGRESS_HEARTBEAT",
      resource_id: resourceId,
      sequence_number: sequence,
      status: "NO_CHANGE",
    };
    body = `event: heartbeat\ndata: ${canonicalStrictJson({
      ...unsigned,
      content_digest: `sha256:${digest(unsigned)}`,
      cursor,
    })}\n\n`;
  } else if (taskProgress) {
    const unsigned = {
      schema_version: "1.0.0",
      kind: "TASK_PROGRESS",
      resource_id: resourceId,
      sequence_number: 1,
      event_type: "durable.task.transitioned",
      state: "RUNNING",
      previous_state: resourceId === "task-invalid-transition" ? "SUCCEEDED" : "PENDING",
      occurred_at: "2026-08-22T00:00:00+00:00",
    };
    const contentDigest = digest(unsigned);
    const document = {
      ...unsigned,
      content_digest: `sha256:${contentDigest}`,
      cursor: `p1-1-${contentDigest}`,
    };
    body = `id: ${document.cursor}\nevent: progress\ndata: ${canonicalStrictJson(document)}\n\n`;
  } else {
    const unsigned = {
      schema_version: "1.0.0",
      kind: "JOB_PROGRESS",
      resource_id: resourceId,
      sequence_number: 1,
      event_type: "processing.job.snapshot",
      state: "RUNNING",
      result_status: "NOT_RUN",
      attempt: 1,
      max_attempts: 3,
      occurred_at: "2026-08-22T00:00:00+00:00",
      ...(invalidJobProgressOverrides.get(resourceId) ?? {}),
    };
    const contentDigest = digest(unsigned);
    const document = {
      ...unsigned,
      content_digest: `sha256:${contentDigest}`,
      cursor: `p1-1-${contentDigest}`,
    };
    if (resourceId === "job-tampered") document.content_digest = `sha256:${"0".repeat(64)}`;
    body = `id: ${document.cursor}\nevent: progress\ndata: ${canonicalStrictJson(document)}\n\n`;
  }
  response.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Content-Length": String(Buffer.byteLength(body)),
    "Cache-Control": "private, no-store, max-age=0",
  });
  response.end(body);
});
await new Promise((resolve, reject) => {
  progressServer.once("error", reject);
  progressServer.listen(0, "127.0.0.1", resolve);
});
try {
  const address = progressServer.address();
  assert.ok(address && typeof address === "object");
  process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT = `http://127.0.0.1:${address.port}`;
  process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN = progressToken;
  const firstBatch = await readMultimodalProgressBatch(
    progressIdentity,
    progressProjectAlias,
    "jobs",
    "job-a",
    undefined,
  );
  assert.match(firstBatch, /^id: (p1-1-[0-9a-f]{64})\nevent: progress\ndata: /);
  const firstTaskBatch = await readMultimodalProgressBatch(
    progressIdentity,
    progressProjectAlias,
    "tasks",
    "task-a",
    undefined,
  );
  assert.match(firstTaskBatch, /^id: (p1-1-[0-9a-f]{64})\nevent: progress\ndata: /);
  await assert.rejects(
    readMultimodalProgressBatch(
      progressIdentity,
      progressProjectAlias,
      "tasks",
      "task-invalid-transition",
      undefined,
    ),
    (error) => {
      assert.ok(error instanceof MultimodalIntakeRunnerError);
      assert.equal(error.code, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
      return true;
    },
  );
  const cursor = firstBatch.match(/^id: (p1-1-[0-9a-f]{64})/)?.[1];
  assert.ok(cursor);
  const heartbeat = await readMultimodalProgressBatch(
    progressIdentity,
    progressProjectAlias,
    "jobs",
    "job-a",
    cursor,
  );
  assert.match(heartbeat, /^event: heartbeat\ndata: /);
  await assert.rejects(
    readMultimodalProgressBatch(
      progressIdentity,
      progressProjectAlias,
      "jobs",
      "job-tampered",
      undefined,
    ),
    (error) => {
      assert.ok(error instanceof MultimodalIntakeRunnerError);
      assert.equal(error.code, "MULTIMODAL_PROGRESS_DIGEST_INVALID");
      return true;
    },
  );
  for (const resourceId of invalidJobProgressOverrides.keys()) {
    await assert.rejects(
      readMultimodalProgressBatch(
        progressIdentity,
        progressProjectAlias,
        "jobs",
        resourceId,
        undefined,
      ),
      (error) => {
        assert.ok(error instanceof MultimodalIntakeRunnerError);
        assert.equal(error.code, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
        return true;
      },
    );
  }
  const readsBeforeCrossTenant = progressAuthorizedReads;
  await assert.rejects(
    readMultimodalProgressBatch(
      { tenantId: "tenant-b", actor: "actor-b" },
      progressProjectAlias,
      "jobs",
      "job-a",
      undefined,
    ),
    (error) => {
      assert.ok(error instanceof MultimodalIntakeRunnerError);
      assert.equal(error.status, 403);
      assert.equal(error.code, "MULTIMODAL_PROGRESS_ENGINE_REJECTED");
      return true;
    },
  );
  assert.equal(progressAuthorizedReads, readsBeforeCrossTenant);
  checks += 1;
} finally {
  if (resetEndpoint === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT;
  else process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT = resetEndpoint;
  if (resetToken === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN;
  else process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN = resetToken;
  await new Promise((resolve, reject) => progressServer.close((error) => (
    error ? reject(error) : resolve()
  )));
}

const hangingProgressSockets = new Set();
const hangingProgressServer = createServer((request, response) => {
  assert.equal(request.method, "GET");
  assert.equal(request.headers.authorization, `Bearer ${progressToken}`);
  assert.equal(request.headers.accept, "text/event-stream");
  assert.equal(request.headers["x-elmos-bound-tenant"], progressIdentity.tenantId);
  assert.equal(request.headers["x-elmos-bound-project"], progressEngineProjectId);
  assert.equal(request.headers["x-elmos-bound-actor"], progressIdentity.actor);
  // Resolve fetch with valid SSE headers, then leave the body reader pending.
  // The BFF must independently bound and cancel this upstream reader even when
  // the browser remains connected.
  response.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "private, no-store, max-age=0",
  });
  response.flushHeaders();
});
hangingProgressServer.on("connection", (socket) => {
  hangingProgressSockets.add(socket);
  socket.once("close", () => hangingProgressSockets.delete(socket));
});
await new Promise((resolve, reject) => {
  hangingProgressServer.once("error", reject);
  hangingProgressServer.listen(0, "127.0.0.1", resolve);
});
try {
  const address = hangingProgressServer.address();
  assert.ok(address && typeof address === "object");
  process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT = `http://127.0.0.1:${address.port}`;
  process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN = progressToken;
  await assert.rejects(
    readMultimodalProgressBatch(
      progressIdentity,
      progressProjectAlias,
      "jobs",
      "job-timeout",
      undefined,
      undefined,
      25,
    ),
    (error) => {
      assert.ok(error instanceof MultimodalIntakeRunnerError);
      assert.equal(error.status, 504);
      assert.equal(error.code, "MULTIMODAL_PROGRESS_ENDPOINT_TIMEOUT");
      assert.equal(error.retryable, true);
      return true;
    },
  );
  const clientController = new AbortController();
  const clientCancelled = readMultimodalProgressBatch(
    progressIdentity,
    progressProjectAlias,
    "jobs",
    "job-client-close",
    undefined,
    clientController.signal,
    1_000,
  );
  clientController.abort();
  await assert.rejects(clientCancelled, (error) => {
    assert.ok(error instanceof DOMException);
    assert.equal(error.name, "AbortError");
    assert.equal(error.message, "MULTIMODAL_PROGRESS_CLIENT_CLOSED");
    return true;
  });
  checks += 1;
} finally {
  if (resetEndpoint === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT;
  else process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT = resetEndpoint;
  if (resetToken === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN;
  else process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN = resetToken;
  for (const socket of hangingProgressSockets) socket.destroy();
  await new Promise((resolve, reject) => hangingProgressServer.close((error) => (
    error ? reject(error) : resolve()
  )));
}

const responseLossServer = createServer((request, response) => {
  request.resume();
  request.once("end", () => response.destroy());
});
await new Promise((resolve, reject) => {
  responseLossServer.once("error", reject);
  responseLossServer.listen(0, "127.0.0.1", resolve);
});
try {
  const address = responseLossServer.address();
  assert.ok(address && typeof address === "object");
  process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT = `http://127.0.0.1:${address.port}`;
  process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN = "t".repeat(32);
  await assert.rejects(
    executeMultimodalSkill(
      { tenantId: "tenant-a", actor: "actor-a" },
      {
        skill,
        operation: "bootstrap_project",
        projectId: "project-a",
        input: {},
      },
      "response-loss-key-0001",
    ),
    (error) => {
      assert.ok(error instanceof MultimodalIntakeRunnerError);
      assert.equal(error.code, "MULTIMODAL_ENGINE_OUTCOME_RECONCILIATION_REQUIRED");
      assert.equal(error.retryable, false);
      return true;
    },
  );
  checks += 1;
} finally {
  if (resetEndpoint === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT;
  else process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT = resetEndpoint;
  if (resetToken === undefined) delete process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN;
  else process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN = resetToken;
  await new Promise((resolve, reject) => responseLossServer.close((error) => (
    error ? reject(error) : resolve()
  )));
}

console.log(`multimodal intake runner contract checks: ${checks}`);
