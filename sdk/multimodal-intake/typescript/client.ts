export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export type SkillExecutionRequest = {
  schema_version: "1.0.0";
  skill: string;
  operation: string;
  tenant_id: string;
  project_id: string;
  actor_id: string;
  idempotency_key: string;
  trace_id: string;
  input: Record<string, Json>;
};

/** Generated mirror of multimodal-operation-registry-v1.
 * The server remains authoritative; drift tests bind this map to OpenAPI and
 * the Python registry.  The mapped type is a skill/operation discriminated
 * union rather than two unrelated strings.
 */
export const operationRegistry = Object.freeze({
  "elmos-multimodal-input-orchestrator": ["bootstrap_project", "cancel_job", "create_session", "get_session", "process_session", "resume_job"],
  "elmos-secure-resumable-upload": ["abort", "commit", "start", "status", "upload_part"],
  "elmos-file-type-detection-and-validation": ["inspect", "process_asset"],
  "elmos-malware-quarantine-and-sandbox": ["inspect", "process_asset"],
  "elmos-audio-asr-and-diarization": ["parse", "process_asset"],
  "elmos-image-ocr-and-preprocessing": ["parse", "process_asset"],
  "elmos-visual-ui-understanding": ["parse", "process_asset", "understand"],
  "elmos-diagram-and-architecture-understanding": ["parse", "process_asset", "understand"],
  "elmos-pdf-layout-table-parser": ["parse", "process_asset"],
  "elmos-word-document-parser": ["parse", "process_asset"],
  "elmos-markdown-text-log-parser": ["parse", "process_asset"],
  "elmos-unified-multimodal-content-ir": ["normalize"],
  "elmos-source-anchor-and-provenance": ["anchor"],
  "elmos-multimodal-requirement-extraction": ["extract"],
  "elmos-multi-asset-content-fusion": ["fuse"],
  "elmos-document-version-and-conflict-detection": ["detect_conflicts"],
  "elmos-human-review-and-correction": ["approve", "claim", "correct", "current_correction", "edit", "enqueue", "enqueue_execute", "enqueue_prepare", "get", "list", "propagation_claim", "propagation_complete", "propagation_dispatch", "propagation_reconcile", "propagation_status", "reject", "reopen", "reservation_status", "revert", "source_get", "source_list", "source_register"],
  "elmos-prompt-injection-defense": ["evaluate"],
  "elmos-provider-routing-and-fallback": ["route"],
  "elmos-storage-index-and-retrieval": ["delete", "query", "rebuild_status", "repair", "upsert"],
  "elmos-durable-processing-and-recovery": ["get_task_state", "list_outbox", "mark_outbox_published", "process_durable_transition", "transition"],
  "elmos-processing-cost-and-eta-estimation": ["estimate"],
  "elmos-multimodal-observability": ["observe"],
  "elmos-multimodal-evaluation-framework": ["catalog", "evaluate", "get_run", "verify"],
  "elmos-multimodal-input-workbench-ui": ["build_preview", "capabilities", "describe", "health"],
  "elmos-ingestion-api-and-sdk": ["build_contract", "capabilities", "describe", "health"],
  "elmos-data-retention-and-governance": ["delete", "delete_status", "evaluate", "export", "provider_access"],
  "elmos-downstream-agent-integration": ["build_context", "get_context", "get_grant", "link_result", "list_result_links", "revoke_grant"],
  "elmos-codex-context-capacity-parity": ["check"],
  "elmos-context-budget-manager": ["calculate"],
  "elmos-multimodal-token-accounting": ["account"],
  "elmos-long-context-packing-and-ranking": ["pack"],
  "elmos-context-pressure-monitor": ["monitor"],
  "elmos-structured-context-compaction": ["compact"],
  "elmos-context-checkpoint-and-recovery": ["create", "diff", "list", "restore", "rollback"],
  "elmos-context-rehydration": ["rehydrate"],
  "elmos-project-memory-and-retrieval": ["delete", "query", "rebuild_status", "repair", "write"],
  "elmos-repository-context-map": ["rebuild", "rollback", "status"],
  "elmos-model-capability-discovery": ["discover", "history", "rollback"],
  "elmos-context-integrity-and-loss-detection": ["verify"],
  "elmos-folder-tree-input": ["append", "begin", "finalize", "page", "status"],
  "elmos-resumable-multi-file-folder-upload": ["confirm_part", "negotiate", "status"],
  "elmos-project-package-manifest": ["diff", "finalize", "page"],
  "elmos-secure-zip-tar-extraction": ["expand_nested", "extract", "publish"],
  "elmos-archive-bomb-and-path-traversal-defense": ["inspect"],
  "elmos-project-root-language-framework-detection": ["rebuild", "rollback", "status"],
  "elmos-ignore-generated-vendored-file-classification": ["rebuild", "rollback", "status"],
  "elmos-repository-map-and-symbol-indexing": ["rebuild", "rollback", "status"],
  "elmos-project-package-version-and-incremental-update": ["diff"],
  "elmos-project-package-preview-and-review-ui": ["override", "page", "undo"],
} as const);

export type RegisteredSkill = keyof typeof operationRegistry;
export type RegisteredOperation<S extends RegisteredSkill> = (typeof operationRegistry)[S][number];
export type RegisteredSkillExecutionRequest = {
  [S in RegisteredSkill]: SkillExecutionRequest & { skill: S; operation: RegisteredOperation<S> }
}[RegisteredSkill];

type TypedRequest<S extends RegisteredSkill, O extends RegisteredOperation<S>, I extends Record<string, Json>> =
  Omit<SkillExecutionRequest, "skill" | "operation" | "input"> & { skill: S; operation: O; input: I };
export type EvaluationSubject = Readonly<{
  subject_id: string;
  subject_kind: "parser" | "provider" | "model" | "runtime" | "configuration";
  artifact_digest: `sha256:${string}`;
  implementation_version: string;
  configuration_digest: `sha256:${string}`;
}>;
export type EvaluationEvidence = Readonly<{
  case_id: string;
  media_type: string;
  content_base64: string;
}>;
export type EvaluationOperationRequest =
  | TypedRequest<"elmos-multimodal-evaluation-framework", "evaluate", { subject: EvaluationSubject; evidence: EvaluationEvidence[] }>
  | TypedRequest<"elmos-multimodal-evaluation-framework", "verify" | "get_run", { run_id: string }>
  | TypedRequest<"elmos-multimodal-evaluation-framework", "catalog", Record<never, never>>;
export type DownstreamAgentOperationRequest =
  | TypedRequest<"elmos-downstream-agent-integration", "build_context", { task_id: string; subject_id: string; package_version: number; source_receipt_ids: string[]; tool_receipt_ids?: string[] }>
  | TypedRequest<"elmos-downstream-agent-integration", "get_context", { context_id: string }>
  | TypedRequest<"elmos-downstream-agent-integration", "get_grant", { context_id: string; grant_id: string }>
  | TypedRequest<"elmos-downstream-agent-integration", "revoke_grant", { context_id: string; grant_id: string; reason: string }>
  | TypedRequest<"elmos-downstream-agent-integration", "link_result", { context_id: string; grant_id: string; result_receipt_id: string }>
  | TypedRequest<"elmos-downstream-agent-integration", "list_result_links", { context_id: string }>;
export type ProjectPackageEntry = Readonly<{
  path: string;
  kind?: "file" | "directory" | "symlink" | "hardlink" | "special";
  byte_count?: number;
  content_digest?: `sha256:${string}`;
  role?: "PRIMARY" | "REFERENCE" | "IGNORE";
  model_read_allowed?: boolean;
  metadata?: Readonly<Record<string, Json>>;
}>;
export type ProjectPackageOperationRequest =
  | TypedRequest<"elmos-folder-tree-input", "begin", { session_id?: string; expected_entry_count: number }>
  | TypedRequest<"elmos-folder-tree-input", "append", { session_id: string; chunk_index: number; entries: ProjectPackageEntry[] }>
  | TypedRequest<"elmos-folder-tree-input", "finalize" | "status", { session_id: string }>
  | TypedRequest<"elmos-folder-tree-input", "page", { package_version: number; limit?: number; cursor?: string }>
  | TypedRequest<"elmos-resumable-multi-file-folder-upload", "negotiate", { session_id: string; path: string; byte_count: number; content_digest: `sha256:${string}`; part_size?: number }>
  | TypedRequest<"elmos-resumable-multi-file-folder-upload", "confirm_part", { session_id: string; path: string; part_number: number; byte_count: number; part_digest: `sha256:${string}`; data_base64: string }>
  | TypedRequest<"elmos-resumable-multi-file-folder-upload", "status", { session_id: string; path?: string }>
  | TypedRequest<"elmos-project-package-manifest", "finalize", { session_id: string }>
  | TypedRequest<"elmos-project-package-manifest", "page", { package_version: number; limit?: number; cursor?: string }>
  | TypedRequest<"elmos-project-package-manifest" | "elmos-project-package-version-and-incremental-update", "diff", { old_version: number; new_version: number }>
  | TypedRequest<"elmos-project-package-preview-and-review-ui", "page", { package_version: number; limit?: number; cursor?: string }>
  | TypedRequest<"elmos-project-package-preview-and-review-ui", "override", { package_version: number; path: string; expected_override_version: number; role?: "PRIMARY" | "REFERENCE" | "IGNORE"; model_read_allowed?: boolean; reason: string }>
  | TypedRequest<"elmos-project-package-preview-and-review-ui", "undo", { package_version: number; path: string; expected_override_version: number; audit_id: string; reason: string }>;

function validateRegisteredOperation(skill: string, operation: string): void {
  if (!Object.prototype.hasOwnProperty.call(operationRegistry, skill)) throw new Error("REQUIRES_ADAPTER");
  const operations = operationRegistry[skill as RegisteredSkill] as readonly string[];
  if (!operations.includes(operation)) throw new Error("REQUIRES_ADAPTER");
}

type InputFieldContract = Readonly<{ allowed: readonly string[]; required: readonly string[] }>;
const inputFieldContracts: Readonly<Record<string, InputFieldContract>> = Object.freeze({
  "elmos-multimodal-evaluation-framework/evaluate": { allowed: ["subject", "evidence"], required: ["subject", "evidence"] },
  "elmos-multimodal-evaluation-framework/verify": { allowed: ["run_id"], required: ["run_id"] },
  "elmos-multimodal-evaluation-framework/get_run": { allowed: ["run_id"], required: ["run_id"] },
  "elmos-multimodal-evaluation-framework/catalog": { allowed: [], required: [] },
  "elmos-multimodal-requirement-extraction/extract": { allowed: ["sources", "package_version", "projection_key", "task_id"], required: ["package_version"] },
  "elmos-multi-asset-content-fusion/fuse": { allowed: ["assets", "package_version", "projection_key", "task_id"], required: ["package_version"] },
  "elmos-document-version-and-conflict-detection/detect_conflicts": { allowed: ["claims", "package_version", "projection_key", "task_id"], required: ["package_version"] },
  "elmos-downstream-agent-integration/build_context": { allowed: ["task_id", "subject_id", "package_version", "source_receipt_ids", "tool_receipt_ids"], required: ["task_id", "subject_id", "package_version", "source_receipt_ids"] },
  "elmos-downstream-agent-integration/get_context": { allowed: ["context_id"], required: ["context_id"] },
  "elmos-downstream-agent-integration/get_grant": { allowed: ["context_id", "grant_id"], required: ["context_id", "grant_id"] },
  "elmos-downstream-agent-integration/revoke_grant": { allowed: ["context_id", "grant_id", "reason"], required: ["context_id", "grant_id", "reason"] },
  "elmos-downstream-agent-integration/link_result": { allowed: ["context_id", "grant_id", "result_receipt_id"], required: ["context_id", "grant_id", "result_receipt_id"] },
  "elmos-downstream-agent-integration/list_result_links": { allowed: ["context_id"], required: ["context_id"] },
  "elmos-codex-context-capacity-parity/check": { allowed: ["capability_snapshot", "task_id"], required: [] },
  "elmos-context-budget-manager/calculate": { allowed: ["capability_snapshot", "reserved_output_tokens", "safety_headroom_tokens", "usage", "task_id"], required: [] },
  "elmos-multimodal-token-accounting/account": { allowed: ["estimator_version", "items", "model_id", "model_version", "tokenizer_id", "tokenizer_version", "task_id", "current_window_output_reserved_tokens", "model_snapshot_id"], required: [] },
  "elmos-long-context-packing-and-ranking/pack": { allowed: ["candidates", "effective_input_budget", "task_id"], required: [] },
  "elmos-context-pressure-monitor/monitor": { allowed: ["effective_input_budget", "previous_state", "used_tokens", "task_id", "forecast_horizon", "next_turn_tokens", "pending_tool_tokens", "pending_test_log_tokens"], required: [] },
  "elmos-structured-context-compaction/compact": { allowed: ["source_history_digest", "state", "task_id", "raw_history", "package_version", "model_snapshot_id", "rollback_checkpoint_id", "side_effect_cursor", "cost_cursor", "input_tokens", "output_tokens"], required: [] },
  "elmos-context-checkpoint-and-recovery/create": { allowed: ["state", "payload", "task_id", "raw_history", "package_version", "model_snapshot_id", "rollback_checkpoint_id", "side_effect_cursor", "cost_cursor", "input_tokens", "output_tokens"], required: [] },
  "elmos-context-checkpoint-and-recovery/list": { allowed: ["task_id"], required: [] },
  "elmos-context-checkpoint-and-recovery/diff": { allowed: ["left_checkpoint_id", "right_checkpoint_id", "task_id"], required: ["left_checkpoint_id", "right_checkpoint_id"] },
  "elmos-context-checkpoint-and-recovery/restore": { allowed: ["checkpoint_id", "task_id"], required: ["checkpoint_id"] },
  "elmos-context-checkpoint-and-recovery/rollback": { allowed: ["checkpoint_id", "task_id"], required: ["checkpoint_id"] },
  "elmos-model-capability-discovery/discover": { allowed: ["observation", "previous_snapshot", "task_id"], required: [] },
  "elmos-model-capability-discovery/history": { allowed: ["provider", "model_id"], required: ["provider", "model_id"] },
  "elmos-model-capability-discovery/rollback": { allowed: ["snapshot_id"], required: ["snapshot_id"] },
  "elmos-context-rehydration/rehydrate": { allowed: ["package_version", "remaining_budget_tokens", "source_ids", "task_id"], required: [] },
  "elmos-context-integrity-and-loss-detection/verify": { allowed: ["after", "before", "task_id", "checkpoint_id"], required: [] },
  "elmos-repository-context-map/rebuild": { allowed: ["package_version", "source_input"], required: ["package_version", "source_input"] },
  "elmos-repository-context-map/status": { allowed: ["package_version"], required: ["package_version"] },
  "elmos-repository-context-map/rollback": { allowed: ["package_version", "artifact_version"], required: ["package_version", "artifact_version"] },
  "elmos-folder-tree-input/begin": { allowed: ["session_id", "expected_entry_count"], required: ["expected_entry_count"] },
  "elmos-folder-tree-input/append": { allowed: ["session_id", "chunk_index", "entries"], required: ["session_id", "chunk_index", "entries"] },
  "elmos-folder-tree-input/finalize": { allowed: ["session_id"], required: ["session_id"] },
  "elmos-folder-tree-input/status": { allowed: ["session_id"], required: ["session_id"] },
  "elmos-folder-tree-input/page": { allowed: ["package_version", "limit", "cursor"], required: ["package_version"] },
  "elmos-resumable-multi-file-folder-upload/negotiate": { allowed: ["session_id", "path", "byte_count", "content_digest", "part_size"], required: ["session_id", "path", "byte_count", "content_digest"] },
  "elmos-resumable-multi-file-folder-upload/confirm_part": { allowed: ["session_id", "path", "part_number", "byte_count", "part_digest", "data_base64"], required: ["session_id", "path", "part_number", "byte_count", "part_digest", "data_base64"] },
  "elmos-resumable-multi-file-folder-upload/status": { allowed: ["session_id", "path"], required: ["session_id"] },
  "elmos-project-package-manifest/finalize": { allowed: ["session_id"], required: ["session_id"] },
  "elmos-project-package-manifest/page": { allowed: ["package_version", "limit", "cursor"], required: ["package_version"] },
  "elmos-project-package-manifest/diff": { allowed: ["old_version", "new_version"], required: ["old_version", "new_version"] },
  "elmos-project-package-version-and-incremental-update/diff": { allowed: ["old_version", "new_version"], required: ["old_version", "new_version"] },
  "elmos-project-package-preview-and-review-ui/page": { allowed: ["package_version", "limit", "cursor"], required: ["package_version"] },
  "elmos-project-package-preview-and-review-ui/override": { allowed: ["package_version", "path", "expected_override_version", "role", "model_read_allowed", "reason"], required: ["package_version", "path", "expected_override_version", "reason"] },
  "elmos-project-package-preview-and-review-ui/undo": { allowed: ["package_version", "path", "expected_override_version", "audit_id", "reason"], required: ["package_version", "path", "expected_override_version", "audit_id", "reason"] },
  "elmos-project-root-language-framework-detection/rebuild": { allowed: ["package_version", "source_input"], required: ["package_version", "source_input"] },
  "elmos-project-root-language-framework-detection/status": { allowed: ["package_version"], required: ["package_version"] },
  "elmos-project-root-language-framework-detection/rollback": { allowed: ["package_version", "artifact_version"], required: ["package_version", "artifact_version"] },
  "elmos-ignore-generated-vendored-file-classification/rebuild": { allowed: ["package_version", "source_input"], required: ["package_version", "source_input"] },
  "elmos-ignore-generated-vendored-file-classification/status": { allowed: ["package_version"], required: ["package_version"] },
  "elmos-ignore-generated-vendored-file-classification/rollback": { allowed: ["package_version", "artifact_version"], required: ["package_version", "artifact_version"] },
  "elmos-repository-map-and-symbol-indexing/rebuild": { allowed: ["package_version", "source_input"], required: ["package_version", "source_input"] },
  "elmos-repository-map-and-symbol-indexing/status": { allowed: ["package_version"], required: ["package_version"] },
  "elmos-repository-map-and-symbol-indexing/rollback": { allowed: ["package_version", "artifact_version"], required: ["package_version", "artifact_version"] },
});

export const CAPABILITIES_PATH = "/api/v1/multimodal-intake/capabilities";
export const EXECUTE_PATH = "/api/v1/multimodal-intake/execute";
export const PROGRESS_TASK_EVENTS_PREFIX = "/api/v1/multimodal-intake/progress/tasks/";
export const PROGRESS_JOB_EVENTS_PREFIX = "/api/v1/multimodal-intake/progress/jobs/";
export const PROGRESS_TASK_WEBSOCKET_PREFIX = "/api/v1/multimodal-intake/progress/ws/tasks/";
export const PROGRESS_JOB_WEBSOCKET_PREFIX = "/api/v1/multimodal-intake/progress/ws/jobs/";
export const progressTransportSupport = Object.freeze({ sse: true, websocket: false });
export const HUMAN_REVIEW_SKILL = "elmos-human-review-and-correction";
export const HUMAN_REVIEW_SOURCE_LIST_OPERATION = "source_list";
export const HUMAN_REVIEW_SOURCE_GET_OPERATION = "source_get";
export const HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION = "enqueue";
export const HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION = "enqueue_prepare";
export const HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION = "enqueue_execute";
export const HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT = "sha256:rfc8785-ijson-safeint-v1";
export const HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS = 200;
export const HUMAN_REVIEW_SOURCE_COLLECTION_MAX_ITEMS = 1_000;
export const humanReviewSourceRefV2Fields = Object.freeze([
  "schema_version", "content_id", "content_version", "content_digest", "asset_sha256",
  "target_kind", "target_digest", "snapshot_id", "snapshot_digest", "head_version",
  "head_value_digest", "source_digest", "provenance_digest",
  "original_value_client_digest", "original_value_digest_contract",
] as const);
export const humanReviewSourceSummaryFields = Object.freeze([
  "schema_version", "content_id", "content_version", "target_kind", "target",
  "target_digest", "confidence", "head_version", "head_direction",
  "head_correction_version", "original_value_client_digest",
  "original_value_digest_contract", "source_ref",
] as const);
export const humanReviewSourceDetailFields = Object.freeze([
  ...humanReviewSourceSummaryFields, "original_value",
] as const);
export const humanReviewSourceBoundEnqueueFields = Object.freeze([
  "content_id", "expected_asset_version", "target_kind", "target_digest",
  "expected_head_version", "expected_snapshot_id", "expected_snapshot_digest",
  "expected_head_value_digest", "original_value_digest", "reason",
] as const);
export const humanReviewEnqueuePrepareFields = Object.freeze([
  ...humanReviewSourceBoundEnqueueFields, "recovery_handle", "execute_idempotency_key",
] as const);
export const humanReviewEnqueueExecuteFields = Object.freeze(["recovery_handle"] as const);
export const humanReviewEnqueuePreparationFields = Object.freeze([
  "schema_version", "recovery_handle", "request_digest", "state", "safe_to_clear",
  "expires_at", "prepared_at", "executed_at", "task_id", "enqueue_input",
] as const);
export const humanReviewEnqueuePreparationAbsenceFields = Object.freeze([
  "schema_version", "recovery_handle", "state", "safe_to_clear",
] as const);

export type HumanReviewTargetKind =
  | "TEXT" | "SPEAKER" | "TIME_RANGE" | "BBOX" | "TABLE" | "REQUIREMENT" | "CONFLICT";
export type HumanReviewSourceRefV2 = Readonly<{
  schema_version: "human-review-source-ref-v2";
  content_id: string;
  content_version: number;
  content_digest: `sha256:${string}`;
  asset_sha256: `sha256:${string}`;
  target_kind: HumanReviewTargetKind;
  target_digest: `sha256:${string}`;
  snapshot_id: string;
  snapshot_digest: `sha256:${string}`;
  head_version: number;
  head_value_digest: `sha256:${string}`;
  source_digest: `sha256:${string}`;
  provenance_digest: `sha256:${string}`;
  original_value_client_digest: `sha256:${string}`;
  original_value_digest_contract: typeof HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT;
}>;
export type HumanReviewSourceSummary = Readonly<{
  schema_version: "human-review-source-summary-v1";
  content_id: string;
  content_version: number;
  target_kind: HumanReviewTargetKind;
  target: Readonly<Record<string, Json>>;
  target_digest: `sha256:${string}`;
  confidence: number;
  head_version: number;
  head_direction: "SNAPSHOT" | "APPLY" | "REVERT";
  head_correction_version: number;
  original_value_client_digest: `sha256:${string}`;
  original_value_digest_contract: typeof HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT;
  source_ref: HumanReviewSourceRefV2;
}>;
export type HumanReviewSourceDetail = Readonly<
  Omit<HumanReviewSourceSummary, "schema_version"> & {
    schema_version: "human-review-source-detail-v1";
    original_value: Json;
  }
>;
export type HumanReviewSourceBoundEnqueueInput = Readonly<{
  content_id: string;
  expected_asset_version: number;
  target_kind: HumanReviewTargetKind;
  target_digest: `sha256:${string}`;
  expected_head_version: number;
  expected_snapshot_id: string;
  expected_snapshot_digest: `sha256:${string}`;
  expected_head_value_digest: `sha256:${string}`;
  original_value_digest: `sha256:${string}`;
  reason: string;
}>;
export type HumanReviewEnqueuePrepareInput = HumanReviewSourceBoundEnqueueInput & Readonly<{
  recovery_handle: string;
  execute_idempotency_key: string;
}>;
export type HumanReviewEnqueueExecuteInput = Readonly<{ recovery_handle: string }>;
export type HumanReviewEnqueuePreparation = Readonly<{
  schema_version: "human-review-enqueue-preparation-v1";
  recovery_handle: string;
  request_digest: `sha256:${string}`;
  state: "PREPARED" | "EXECUTED" | "EXPIRED";
  safe_to_clear: boolean;
  expires_at: string;
  prepared_at: string;
  executed_at: string | null;
  task_id: string | null;
  enqueue_input: HumanReviewSourceBoundEnqueueInput;
}>;
export type HumanReviewEnqueuePreparationAbsence = Readonly<{
  schema_version: "human-review-enqueue-preparation-absence-v1";
  recovery_handle: string;
  state: "ABSENT";
  safe_to_clear: true;
}>;

export type ProgressResourceKind = "task" | "job";
export type ProgressContext = Readonly<{
  tenantId: string;
  projectId: string;
  actorId: string;
}>;
export type ProgressDocument = Readonly<Record<string, Json>>;
export type ProgressBatch = Readonly<{
  resourceKind: ProgressResourceKind;
  resourceId: string;
  documents: readonly ProgressDocument[];
  heartbeat: ProgressDocument | null;
  requestedCursor: string | null;
  nextCursor: string | null;
}>;

export class MultimodalIntakeRemoteError extends Error {
  constructor(
    public readonly statusCode: number,
    public readonly code: string,
    public readonly retryable: boolean,
    public readonly traceId: string | null,
  ) {
    super(code);
    this.name = "MultimodalIntakeRemoteError";
  }
}

const minimumTimeoutMs = 1_000;
const maximumTimeoutMs = 120_000;
const maximumJsonDepth = 32;
const maximumJsonNodes = 200_000;
const maximumRequestBytes = 2 * 1024 * 1024;
const maximumResponseBytes = 4 * 1024 * 1024;
const maximumProgressDocuments = 64;
const resourceIdPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const progressCursorPattern = /^p1-([1-9][0-9]{0,15})-([0-9a-f]{64})$/;
const contentDigestPattern = /^sha256:([0-9a-f]{64})$/;
const timestampPattern = /^(\d{4})-(\d{2})-(\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;
const jobProgressResultByState: Readonly<Record<string, string>> = Object.freeze({
  QUEUED: "NOT_RUN",
  RUNNING: "NOT_RUN",
  COMPLETED: "PASSED",
  PARTIAL: "PARTIAL",
  NEEDS_REVIEW: "NEEDS_REVIEW",
  BLOCKED: "BLOCKED",
  FAILED: "FAILED",
  CANCELLED: "BLOCKED",
});
const publicCodePattern = /^[A-Z][A-Z0-9_:-]{0,127}$/;
const skillPattern = /^elmos-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const operationPattern = /^[a-z][a-z0-9_-]{0,63}$/;
const handlerPattern = /^execute_[a-z0-9_]+$/;
const actorIdPattern = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$/;
const digestPattern = /^[0-9a-f]{64}$/;
const jsonSuffixMediaTypePattern = /^application\/[a-z0-9!#$%&'*.^_`|~-]+\+json$/;
const resultStates = new Set([
  "SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL",
]);
const capabilityPhases = new Set([
  "secure-intake", "normalization", "content", "project-package", "governance",
  "indexing", "context", "review", "delivery", "evaluation",
]);
const expectedCapabilityCatalogDigest = "546ec5aae1d7a031b00abab4cd96b3a5c3968ee5e947f7a6c68aeecbe7599d3a";
const expectedCapabilityDocumentDigest = "bd72f6fb88eb1daf6da13f9552508cca6c7df3a2fd7318299647450114693a8c";

type ExpectedExecutionRequest = Readonly<{
  skill: string;
  operation: string;
  tenantId: string;
  projectId: string;
  actorId: string;
  traceId: string;
  requestDigest: string;
  input: Readonly<Record<string, Json>>;
}>;

function validBearerToken(value: unknown): value is string {
  if (typeof value !== "string" || value.length < 32 || value.length > 4096) return false;
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit < 0x21 || unit > 0x7e) return false;
  }
  return true;
}

function validUnicode(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return false;
    }
  }
  return true;
}

function numericLoopbackHost(value: string): boolean {
  let host = value.toLowerCase();
  if (host.startsWith("[") && host.endsWith("]")) host = host.slice(1, -1);
  if (host === "::1") return true;
  const segments = host.split(".");
  return segments.length === 4
    && segments[0] === "127"
    && segments.every((segment) => /^(?:0|[1-9][0-9]{0,2})$/.test(segment) && Number(segment) <= 255);
}

function jsonMediaType(value: string | null): boolean {
  if (value === null) return false;
  const mediaType = value.split(";", 1)[0].trim().toLowerCase();
  return mediaType === "application/json" || jsonSuffixMediaTypePattern.test(mediaType);
}

function boundedText(value: Json | undefined, maximumBytes: number): value is string {
  return typeof value === "string"
    && value.length > 0
    && validUnicode(value)
    && new TextEncoder().encode(value).byteLength <= maximumBytes
    && ![...value].some((character) => {
      const codePoint = character.codePointAt(0)!;
      return codePoint < 0x20 || codePoint === 0x7f;
    });
}

function assertStrictJson(value: unknown, boundary: "SDK_REQUEST" | "SDK_RESPONSE"): asserts value is Json {
  const active = new WeakSet<object>();
  let nodes = 0;
  const visit = (candidate: unknown, depth: number): void => {
    nodes += 1;
    if (nodes > maximumJsonNodes || depth > maximumJsonDepth) throw new Error(`${boundary}_JSON_LIMIT_EXCEEDED`);
    if (candidate === null || typeof candidate === "boolean") return;
    if (typeof candidate === "string") {
      if (!validUnicode(candidate)) throw new Error(`${boundary}_JSON_UNICODE_INVALID`);
      return;
    }
    if (typeof candidate === "number") {
      if (!Number.isFinite(candidate)) throw new Error(`${boundary}_JSON_NUMBER_NON_FINITE`);
      if (Number.isInteger(candidate) && !Number.isSafeInteger(candidate)) throw new Error(`${boundary}_JSON_INTEGER_UNSAFE`);
      return;
    }
    if (!candidate || typeof candidate !== "object") throw new Error(`${boundary}_JSON_VALUE_INVALID`);
    if (active.has(candidate)) throw new Error(`${boundary}_JSON_CYCLE`);
    const prototype = Object.getPrototypeOf(candidate);
    if (!Array.isArray(candidate) && prototype !== Object.prototype && prototype !== null) {
      throw new Error(`${boundary}_JSON_OBJECT_INVALID`);
    }
    active.add(candidate);
    if (Array.isArray(candidate)) {
      const keys = Object.keys(candidate);
      if (
        keys.length !== candidate.length
        || Reflect.ownKeys(candidate).length !== candidate.length + 1
        || keys.some((key, index) => key !== String(index))
      ) {
        throw new Error(`${boundary}_JSON_ARRAY_INVALID`);
      }
      for (const item of candidate) visit(item, depth + 1);
    } else {
      const keys = Object.keys(candidate);
      if (Reflect.ownKeys(candidate).length !== keys.length) throw new Error(`${boundary}_JSON_OBJECT_INVALID`);
      for (const key of keys) {
        if (
          !key
          || !validUnicode(key)
          || new TextEncoder().encode(key).byteLength > 256
        ) throw new Error(`${boundary}_JSON_OBJECT_KEY_INVALID`);
        const descriptor = Object.getOwnPropertyDescriptor(candidate, key);
        if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
          throw new Error(`${boundary}_JSON_OBJECT_INVALID`);
        }
        visit(descriptor.value, depth + 1);
      }
    }
    active.delete(candidate);
  };
  visit(value, 0);
}

/** Parse JSON without losing duplicate object keys before validation. */
class StrictJsonParser {
  private offset = 0;
  private nodes = 0;

  constructor(private readonly source: string) {}

  parse(): Json {
    const result = this.value(0);
    this.whitespace();
    if (this.offset !== this.source.length) this.invalid();
    return result;
  }

  private value(depth: number): Json {
    this.nodes += 1;
    if (depth > maximumJsonDepth || this.nodes > maximumJsonNodes) {
      throw new Error("SDK_RESPONSE_JSON_LIMIT_EXCEEDED");
    }
    this.whitespace();
    if (this.offset >= this.source.length) return this.invalid();
    switch (this.source[this.offset]) {
      case "{": return this.object(depth + 1);
      case "[": return this.array(depth + 1);
      case '"': return this.string();
      case "t": return this.literal("true", true);
      case "f": return this.literal("false", false);
      case "n": return this.literal("null", null);
      default: return this.number();
    }
  }

  private object(depth: number): Record<string, Json> {
    this.offset += 1;
    const result: Record<string, Json> = Object.create(null) as Record<string, Json>;
    this.whitespace();
    if (this.take("}")) return result;
    while (true) {
      this.whitespace();
      if (this.source[this.offset] !== '"') return this.invalid();
      const key = this.string();
      if (
        !key
        || new TextEncoder().encode(key).byteLength > 256
        || Object.prototype.hasOwnProperty.call(result, key)
      ) return this.invalid();
      this.whitespace();
      if (!this.take(":")) return this.invalid();
      result[key] = this.value(depth);
      this.whitespace();
      if (this.take("}")) return result;
      if (!this.take(",")) return this.invalid();
    }
  }

  private array(depth: number): Json[] {
    this.offset += 1;
    const result: Json[] = [];
    this.whitespace();
    if (this.take("]")) return result;
    while (true) {
      result.push(this.value(depth));
      this.whitespace();
      if (this.take("]")) return result;
      if (!this.take(",")) return this.invalid();
    }
  }

  private string(): string {
    if (!this.take('"')) return this.invalid();
    let result = "";
    while (this.offset < this.source.length) {
      const character = this.source[this.offset++];
      if (character === '"') {
        if (!validUnicode(result)) return this.invalid();
        return result;
      }
      if (character.charCodeAt(0) < 0x20) return this.invalid();
      if (character !== "\\") {
        result += character;
        continue;
      }
      if (this.offset >= this.source.length) return this.invalid();
      const escaped = this.source[this.offset++];
      switch (escaped) {
        case '"': case "\\": case "/": result += escaped; break;
        case "b": result += "\b"; break;
        case "f": result += "\f"; break;
        case "n": result += "\n"; break;
        case "r": result += "\r"; break;
        case "t": result += "\t"; break;
        case "u": {
          const hex = this.source.slice(this.offset, this.offset + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) return this.invalid();
          result += String.fromCharCode(Number.parseInt(hex, 16));
          this.offset += 4;
          break;
        }
        default: return this.invalid();
      }
    }
    return this.invalid();
  }

  private number(): number {
    const start = this.offset;
    if (this.take("-") && this.offset >= this.source.length) return this.invalid();
    if (this.take("0")) {
      if (/\d/.test(this.source[this.offset] ?? "")) return this.invalid();
    } else {
      if (!/[1-9]/.test(this.source[this.offset] ?? "")) return this.invalid();
      this.offset += 1;
      while (/\d/.test(this.source[this.offset] ?? "")) this.offset += 1;
    }
    if (this.take(".")) {
      if (!/\d/.test(this.source[this.offset] ?? "")) return this.invalid();
      while (/\d/.test(this.source[this.offset] ?? "")) this.offset += 1;
    }
    if (this.take("e") || this.take("E")) {
      if (this.take("+") || this.take("-")) { /* optional exponent sign */ }
      if (!/\d/.test(this.source[this.offset] ?? "")) return this.invalid();
      while (/\d/.test(this.source[this.offset] ?? "")) this.offset += 1;
    }
    const result = Number(this.source.slice(start, this.offset));
    if (!Number.isFinite(result) || (Number.isInteger(result) && !Number.isSafeInteger(result))) {
      return this.invalid();
    }
    return result;
  }

  private literal<T extends Json>(text: string, value: T): T {
    if (!this.source.startsWith(text, this.offset)) return this.invalid();
    this.offset += text.length;
    return value;
  }

  private whitespace(): void {
    while (" \t\r\n".includes(this.source[this.offset] ?? "\0")) this.offset += 1;
  }

  private take(expected: string): boolean {
    if (this.source[this.offset] !== expected) return false;
    this.offset += 1;
    return true;
  }

  private invalid(): never {
    throw new Error("SDK_RESPONSE_JSON_INVALID");
  }
}

function parseStrictJsonBytes(bytes: Uint8Array, invalidCode: string): { rawJson: string; value: Json } {
  let rawJson: string;
  try {
    rawJson = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error(invalidCode);
  }
  try {
    const value = new StrictJsonParser(rawJson).parse();
    assertStrictJson(value, "SDK_RESPONSE");
    return { rawJson, value };
  } catch {
    throw new Error(invalidCode);
  }
}

function strictResourceId(value: unknown): string {
  if (typeof value !== "string" || !resourceIdPattern.test(value)) throw new Error("SDK_PROGRESS_RESOURCE_ID_INVALID");
  return value;
}

function strictCursor(value: unknown): { sequence: number; digest: string } | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" || value.trim() !== value) throw new Error("SDK_PROGRESS_CURSOR_INVALID");
  const matched = progressCursorPattern.exec(value);
  const sequence = matched ? Number(matched[1]) : 0;
  if (!matched || !Number.isSafeInteger(sequence) || sequence < 1) throw new Error("SDK_PROGRESS_CURSOR_INVALID");
  return { sequence, digest: matched[2] };
}

function canonicalJson(value: Json): string {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") return value === 0 ? "0" : JSON.stringify(value) as string;
  if (typeof value === "string") return JSON.stringify(value) as string;
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
}

async function sha256Hex(value: Uint8Array): Promise<string> {
  // WebCrypto accepts only ArrayBuffer-backed views.  A caller may provide a
  // Uint8Array whose backing store is SharedArrayBuffer, so copy the exact
  // visible bytes into a fresh ArrayBuffer before hashing.
  const digestInput = new Uint8Array(new ArrayBuffer(value.byteLength));
  digestInput.set(value);
  const digest = await crypto.subtle.digest("SHA-256", digestInput);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function validTimestamp(value: Json | undefined): value is string {
  if (typeof value !== "string") return false;
  const matched = timestampPattern.exec(value);
  if (!matched || !Number.isFinite(Date.parse(value))) return false;
  const year = Number(matched[1]);
  const month = Number(matched[2]);
  const day = Number(matched[3]);
  if (year < 1 || month < 1 || month > 12) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1];
}

function exactFields(value: Record<string, Json>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((field, index) => field === wanted[index]);
}

function jsonObject(value: Json | undefined): value is Record<string, Json> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

async function validateOperationInput(skill: string, operation: string, input: Record<string, Json>): Promise<void> {
  const contract = inputFieldContracts[`${skill}/${operation}`];
  if (contract) {
    const actual = Object.keys(input);
    if (
      actual.some((field) => !contract.allowed.includes(field))
      || contract.required.some((field) => !Object.prototype.hasOwnProperty.call(input, field))
    ) throw new Error("OPERATION_INPUT_FIELDS_INVALID");
  }
  if (skill === "elmos-multimodal-evaluation-framework" && operation === "evaluate") {
    const subject = input.subject;
    const evidence = input.evidence;
    if (
      !jsonObject(subject)
      || !exactFields(subject, ["subject_id", "subject_kind", "artifact_digest", "implementation_version", "configuration_digest"])
      || !boundedText(subject.subject_id, 128)
      || !["parser", "provider", "model", "runtime", "configuration"].includes(String(subject.subject_kind))
      || typeof subject.artifact_digest !== "string" || !contentDigestPattern.test(subject.artifact_digest)
      || !boundedText(subject.implementation_version, 128)
      || typeof subject.configuration_digest !== "string" || !contentDigestPattern.test(subject.configuration_digest)
      || !Array.isArray(evidence) || evidence.length < 1 || evidence.length > 240
    ) throw new Error("OPERATION_INPUT_SHAPE_INVALID");
    const caseIds = new Set<string>();
    for (const item of evidence) {
      if (
        !jsonObject(item)
        || !exactFields(item, ["case_id", "media_type", "content_base64"])
        || !boundedText(item.case_id, 128)
        || !boundedText(item.media_type, 256)
        || !boundedText(item.content_base64, 16 * 1024 * 1024)
        || caseIds.has(item.case_id as string)
        || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(item.content_base64 as string)
      ) throw new Error("OPERATION_INPUT_SHAPE_INVALID");
      caseIds.add(item.case_id as string);
    }
  }
  if (skill === "elmos-folder-tree-input" && operation === "append") {
    const entries = input.entries;
    if (!Array.isArray(entries) || entries.length < 1 || entries.length > 1_000) {
      throw new Error("OPERATION_INPUT_SHAPE_INVALID");
    }
    const allowed = ["path", "kind", "byte_count", "content_digest", "role", "model_read_allowed", "metadata"];
    for (const item of entries) {
      if (!jsonObject(item) || Object.keys(item).some((field) => !allowed.includes(field)) || !boundedText(item.path, 4096)) {
        throw new Error("OPERATION_INPUT_SHAPE_INVALID");
      }
      if (item.content_digest !== undefined && (typeof item.content_digest !== "string" || !contentDigestPattern.test(item.content_digest))) {
        throw new Error("OPERATION_INPUT_SHAPE_INVALID");
      }
    }
  }
  if (skill === "elmos-resumable-multi-file-folder-upload" && operation === "confirm_part") {
    if (
      !Number.isSafeInteger(input.part_number) || (input.part_number as number) < 1
      || !Number.isSafeInteger(input.byte_count) || (input.byte_count as number) < 0
      || typeof input.part_digest !== "string" || !contentDigestPattern.test(input.part_digest)
      || typeof input.data_base64 !== "string"
      || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(input.data_base64)
    ) throw new Error("OPERATION_INPUT_SHAPE_INVALID");
    let decoded: Uint8Array;
    try {
      const binary = atob(input.data_base64);
      decoded = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    } catch {
      throw new Error("OPERATION_INPUT_SHAPE_INVALID");
    }
    if (
      decoded.byteLength !== input.byte_count
      || `sha256:${await sha256Hex(decoded)}` !== input.part_digest
    ) throw new Error("OPERATION_INPUT_SHAPE_INVALID");
  }
  if (skill === "elmos-downstream-agent-integration") {
    const idFields: Readonly<Record<string, readonly string[]>> = {
      build_context: ["task_id", "subject_id"],
      get_context: ["context_id"],
      get_grant: ["context_id", "grant_id"],
      revoke_grant: ["context_id", "grant_id"],
      link_result: ["context_id", "grant_id", "result_receipt_id"],
      list_result_links: ["context_id"],
    };
    const requiredIds = idFields[operation];
    if (!requiredIds || requiredIds.some((field) => typeof input[field] !== "string" || !resourceIdPattern.test(input[field] as string))) {
      throw new Error("OPERATION_INPUT_SHAPE_INVALID");
    }
    if (operation === "build_context") {
      if (!Number.isSafeInteger(input.package_version) || (input.package_version as number) < 1) {
        throw new Error("OPERATION_INPUT_SHAPE_INVALID");
      }
      for (const [field, required] of [["source_receipt_ids", true], ["tool_receipt_ids", false]] as const) {
        const values = input[field] ?? [];
        if (
          !Array.isArray(values) || (required && values.length === 0) || values.length > 256
          || values.some((value) => typeof value !== "string" || !resourceIdPattern.test(value))
          || new Set(values).size !== values.length
        ) throw new Error("OPERATION_INPUT_SHAPE_INVALID");
      }
    }
    if (operation === "revoke_grant" && !boundedText(input.reason, 512)) {
      throw new Error("OPERATION_INPUT_SHAPE_INVALID");
    }
  }
}

async function validateExecutionRequest(document: SkillExecutionRequest): Promise<ExpectedExecutionRequest> {
  assertStrictJson(document, "SDK_REQUEST");
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    throw new Error("SDK_REQUEST_INVALID");
  }
  const value = document as unknown as Record<string, Json>;
  if (
    !exactFields(value, [
      "schema_version", "skill", "operation", "tenant_id", "project_id", "actor_id",
      "idempotency_key", "trace_id", "input",
    ])
    || value.schema_version !== "1.0.0"
    || typeof value.skill !== "string" || !skillPattern.test(value.skill)
    || typeof value.operation !== "string" || !operationPattern.test(value.operation)
    || typeof value.tenant_id !== "string" || !resourceIdPattern.test(value.tenant_id)
    || typeof value.project_id !== "string" || !resourceIdPattern.test(value.project_id)
    || typeof value.actor_id !== "string" || !actorIdPattern.test(value.actor_id)
    || !boundedText(value.idempotency_key, 200)
    || new TextEncoder().encode(value.idempotency_key as string).byteLength < 8
    || (value.idempotency_key as string).trim() !== value.idempotency_key
    || !boundedText(value.trace_id, 128)
    || !jsonObject(value.input)
  ) throw new Error("SDK_REQUEST_INVALID");
  validateRegisteredOperation(value.skill as string, value.operation as string);
  await validateOperationInput(value.skill as string, value.operation as string, value.input);
  const encoded = new TextEncoder().encode(canonicalJson(value));
  if (encoded.byteLength > maximumRequestBytes) throw new Error("SDK_REQUEST_TOO_LARGE");
  const digestDocument: Record<string, Json> = {
    execution_contract: "multimodal-intake-execution-v2",
    schema_version: "1.0.0",
    skill: value.skill,
    operation: value.operation,
    tenant_id: value.tenant_id,
    project_id: value.project_id,
    actor_id: value.actor_id,
    idempotency_key: value.idempotency_key,
    input: value.input,
  };
  return Object.freeze({
    skill: value.skill,
    operation: value.operation,
    tenantId: value.tenant_id,
    projectId: value.project_id,
    actorId: value.actor_id,
    traceId: value.trace_id,
    requestDigest: await sha256Hex(new TextEncoder().encode(canonicalJson(digestDocument))),
    input: Object.freeze({ ...value.input }),
  });
}

function safeVersion(value: Json | undefined, allowZero = false): value is number {
  return typeof value === "number"
    && Number.isSafeInteger(value)
    && value >= (allowZero ? 0 : 1)
    && value < Number.MAX_SAFE_INTEGER;
}

function validateHumanReviewSourceRef(value: Json | undefined): Record<string, Json> {
  if (!jsonObject(value) || !exactFields(value, humanReviewSourceRefV2Fields)) {
    throw new Error("SDK_HUMAN_REVIEW_SOURCE_REF_INVALID");
  }
  const digestFields = [
    "content_digest", "asset_sha256", "target_digest", "snapshot_digest",
    "head_value_digest", "source_digest", "provenance_digest", "original_value_client_digest",
  ];
  if (
    value.schema_version !== "human-review-source-ref-v2"
    || typeof value.content_id !== "string" || !resourceIdPattern.test(value.content_id)
    || !safeVersion(value.content_version)
    || typeof value.target_kind !== "string"
    || !["TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT"].includes(value.target_kind)
    || typeof value.snapshot_id !== "string" || !resourceIdPattern.test(value.snapshot_id)
    || !safeVersion(value.head_version)
    || value.original_value_digest_contract !== HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT
    || digestFields.some((field) => typeof value[field] !== "string" || !contentDigestPattern.test(value[field] as string))
  ) throw new Error("SDK_HUMAN_REVIEW_SOURCE_REF_INVALID");
  return value;
}

async function validateHumanReviewSource(
  value: Json | undefined,
  detail: boolean,
  expectedInput: Readonly<Record<string, Json>>,
): Promise<Record<string, Json>> {
  const fields = detail ? humanReviewSourceDetailFields : humanReviewSourceSummaryFields;
  if (!jsonObject(value) || !exactFields(value, fields)) {
    throw new Error("SDK_HUMAN_REVIEW_SOURCE_CONTRACT_INVALID");
  }
  const sourceRef = validateHumanReviewSourceRef(value.source_ref);
  if (
    value.schema_version !== (detail ? "human-review-source-detail-v1" : "human-review-source-summary-v1")
    || value.content_id !== expectedInput.content_id
    || value.content_version !== expectedInput.expected_asset_version
    || typeof value.target_kind !== "string"
    || !["TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT"].includes(value.target_kind)
    || !jsonObject(value.target)
    || typeof value.target_digest !== "string" || !contentDigestPattern.test(value.target_digest)
    || typeof value.confidence !== "number" || !Number.isFinite(value.confidence)
    || value.confidence < 0 || value.confidence > 1
    || !safeVersion(value.head_version)
    || typeof value.head_direction !== "string" || !["SNAPSHOT", "APPLY", "REVERT"].includes(value.head_direction)
    || !safeVersion(value.head_correction_version, true)
    || typeof value.original_value_client_digest !== "string"
    || !contentDigestPattern.test(value.original_value_client_digest)
    || value.original_value_digest_contract !== HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT
    || sourceRef.content_id !== value.content_id
    || sourceRef.content_version !== value.content_version
    || sourceRef.target_kind !== value.target_kind
    || sourceRef.target_digest !== value.target_digest
    || sourceRef.head_version !== value.head_version
    || sourceRef.original_value_client_digest !== value.original_value_client_digest
    || sourceRef.original_value_digest_contract !== value.original_value_digest_contract
  ) throw new Error("SDK_HUMAN_REVIEW_SOURCE_CONTRACT_INVALID");
  if (detail) {
    const digest = await sha256Hex(new TextEncoder().encode(canonicalJson(value.original_value!)));
    if (`sha256:${digest}` !== value.original_value_client_digest) {
      throw new Error("SDK_HUMAN_REVIEW_SOURCE_DIGEST_INVALID");
    }
  }
  return value;
}

async function validateHumanReviewSourceCursor(
  value: Json | undefined,
  expected: ExpectedExecutionRequest,
): Promise<Record<string, Json>> {
  if (
    typeof value !== "string"
    || value.length < 1 || value.length > 4_096
    || value.includes("=")
    || !/^[A-Za-z0-9_-]+$/.test(value)
  ) throw new Error("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
  let bytes: Uint8Array;
  let rawJson: string;
  let decoded: Json;
  try {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4);
    const binary = atob(padded);
    bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const canonicalBase64 = btoa(String.fromCharCode(...bytes))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
    if (canonicalBase64 !== value) throw new Error("non-canonical base64url");
    rawJson = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    decoded = new StrictJsonParser(rawJson).parse();
    assertStrictJson(decoded, "SDK_RESPONSE");
  } catch {
    throw new Error("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
  }
  if (
    !jsonObject(decoded)
    || canonicalJson(decoded) !== rawJson
    || !exactFields(decoded, [
      "version", "filter_digest", "collection_digest", "collection_generation",
      "target_kind", "target_digest",
    ])
  ) throw new Error("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
  const kinds = expected.input.kinds;
  if (
    typeof expected.input.content_id !== "string"
    || !resourceIdPattern.test(expected.input.content_id)
    || !safeVersion(expected.input.expected_asset_version)
    || !Array.isArray(kinds)
    || kinds.some((kind) => typeof kind !== "string"
      || !["TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT"].includes(kind))
    || kinds.some((kind, index) => index > 0 && (kinds[index - 1] as string) >= (kind as string))
  ) throw new Error("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
  const filterDocument: Record<string, Json> = {
    schema_version: "human-review-source-filter-v1",
    tenant_id: expected.tenantId,
    project_id: expected.projectId,
    content_id: expected.input.content_id!,
    content_version: expected.input.expected_asset_version!,
    kinds,
  };
  const filterDigest = await sha256Hex(new TextEncoder().encode(canonicalJson(filterDocument)));
  if (
    decoded.version !== "human-review-source-cursor-v1"
    || typeof decoded.filter_digest !== "string" || !digestPattern.test(decoded.filter_digest)
    || decoded.filter_digest !== filterDigest
    || typeof decoded.collection_digest !== "string" || !digestPattern.test(decoded.collection_digest)
    || !safeVersion(decoded.collection_generation)
    || typeof decoded.target_kind !== "string"
    || !["TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT"].includes(decoded.target_kind)
    || typeof decoded.target_digest !== "string" || !contentDigestPattern.test(decoded.target_digest)
  ) throw new Error("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
  return decoded;
}

async function validateHumanReviewTask(
  value: Json | undefined,
  expected: ExpectedExecutionRequest,
  expectedInput: Readonly<Record<string, Json>> = expected.input,
): Promise<Record<string, Json>> {
  const taskFields = [
    "task_id", "tenant_id", "project_id", "asset_id", "target_kind", "target",
    "original_value", "source_digest", "source_ref", "confidence", "reason", "state",
    "current_correction_version", "current_correction_digest", "effective_version",
    "effective_digest", "claim_actor_id", "claim_fence", "claim_expires_at", "version",
    "created_by", "created_at", "updated_at", "closed_at",
  ];
  if (!jsonObject(value) || !exactFields(value, taskFields)) {
    throw new Error("SDK_HUMAN_REVIEW_TASK_CONTRACT_INVALID");
  }
  const sourceRef = validateHumanReviewSourceRef(value.source_ref);
  const nullableDigest = (candidate: Json | undefined): boolean =>
    candidate === null || typeof candidate === "string" && contentDigestPattern.test(candidate);
  const nullableTimestamp = (candidate: Json | undefined): boolean =>
    candidate === null || validTimestamp(candidate);
  if (
    typeof value.task_id !== "string" || !resourceIdPattern.test(value.task_id)
    || value.tenant_id !== expected.tenantId
    || value.project_id !== expected.projectId
    || value.asset_id !== expectedInput.content_id
    || value.target_kind !== expectedInput.target_kind
    || !jsonObject(value.target)
    || typeof value.source_digest !== "string" || !contentDigestPattern.test(value.source_digest)
    || value.source_digest !== sourceRef.source_digest
    || sourceRef.content_id !== value.asset_id
    || sourceRef.content_version !== expectedInput.expected_asset_version
    || sourceRef.target_kind !== value.target_kind
    || sourceRef.target_digest !== expectedInput.target_digest
    || sourceRef.snapshot_id !== expectedInput.expected_snapshot_id
    || sourceRef.snapshot_digest !== expectedInput.expected_snapshot_digest
    || sourceRef.head_version !== expectedInput.expected_head_version
    || sourceRef.head_value_digest !== expectedInput.expected_head_value_digest
    || sourceRef.original_value_client_digest !== expectedInput.original_value_digest
    || typeof value.confidence !== "number" || !Number.isFinite(value.confidence)
    || value.confidence < 0 || value.confidence > 1
    || !boundedText(value.reason, 2_000)
    || value.reason !== expectedInput.reason
    || typeof value.state !== "string"
    || !["QUEUED", "CLAIMED", "EDITED", "APPROVED", "REJECTED", "REOPENED", "REVERTING", "REVERTED"].includes(value.state)
    || !safeVersion(value.current_correction_version, true)
    || !nullableDigest(value.current_correction_digest)
    || !safeVersion(value.effective_version, true)
    || !nullableDigest(value.effective_digest)
    || value.claim_actor_id !== null && (typeof value.claim_actor_id !== "string" || !actorIdPattern.test(value.claim_actor_id))
    || !safeVersion(value.claim_fence, true)
    || !nullableTimestamp(value.claim_expires_at)
    || !safeVersion(value.version)
    || value.created_by !== expected.actorId
    || !validTimestamp(value.created_at)
    || !validTimestamp(value.updated_at)
    || !nullableTimestamp(value.closed_at)
  ) throw new Error("SDK_HUMAN_REVIEW_TASK_CONTRACT_INVALID");
  const originalDigest = await sha256Hex(new TextEncoder().encode(canonicalJson(value.original_value!)));
  if (`sha256:${originalDigest}` !== sourceRef.original_value_client_digest) {
    throw new Error("SDK_HUMAN_REVIEW_TASK_DIGEST_INVALID");
  }
  return value;
}

function validateHumanReviewEnqueueInput(value: Json | undefined): Record<string, Json> {
  if (!jsonObject(value) || !exactFields(value, humanReviewSourceBoundEnqueueFields)) {
    throw new Error("SDK_HUMAN_REVIEW_ENQUEUE_INPUT_INVALID");
  }
  if (
    typeof value.content_id !== "string" || !resourceIdPattern.test(value.content_id)
    || !safeVersion(value.expected_asset_version)
    || typeof value.target_kind !== "string"
    || !["TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT"].includes(value.target_kind)
    || typeof value.target_digest !== "string" || !contentDigestPattern.test(value.target_digest)
    || !safeVersion(value.expected_head_version)
    || typeof value.expected_snapshot_id !== "string" || !resourceIdPattern.test(value.expected_snapshot_id)
    || typeof value.expected_snapshot_digest !== "string" || !contentDigestPattern.test(value.expected_snapshot_digest)
    || typeof value.expected_head_value_digest !== "string" || !contentDigestPattern.test(value.expected_head_value_digest)
    || typeof value.original_value_digest !== "string" || !contentDigestPattern.test(value.original_value_digest)
    || !boundedText(value.reason, 2_000)
  ) throw new Error("SDK_HUMAN_REVIEW_ENQUEUE_INPUT_INVALID");
  return value;
}

async function validateHumanReviewPreparation(
  value: Json | undefined,
  expected: ExpectedExecutionRequest,
  allowedStates: ReadonlySet<string>,
): Promise<{ preparation: Record<string, Json>; enqueueInput: Record<string, Json> }> {
  if (!jsonObject(value) || !exactFields(value, humanReviewEnqueuePreparationFields)) {
    throw new Error("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
  }
  if (
    value.schema_version !== "human-review-enqueue-preparation-v1"
    || value.recovery_handle !== expected.input.recovery_handle
    || typeof value.recovery_handle !== "string"
    || new TextEncoder().encode(value.recovery_handle).byteLength < 32
    || new TextEncoder().encode(value.recovery_handle).byteLength > 200
    || typeof value.request_digest !== "string" || !contentDigestPattern.test(value.request_digest)
    || typeof value.state !== "string" || !allowedStates.has(value.state)
    || typeof value.safe_to_clear !== "boolean"
    || !validTimestamp(value.expires_at) || !validTimestamp(value.prepared_at)
    || value.executed_at !== null && !validTimestamp(value.executed_at)
    || value.task_id !== null
    && (typeof value.task_id !== "string" || !resourceIdPattern.test(value.task_id))
  ) throw new Error("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
  const enqueueInput = validateHumanReviewEnqueueInput(value.enqueue_input);
  if (
    expected.operation.replace(/-/g, "_") === HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION
    && Object.keys(enqueueInput).some((field) => expected.input[field] !== enqueueInput[field])
  ) throw new Error("SDK_HUMAN_REVIEW_PREPARATION_BINDING_INVALID");
  const digest = await sha256Hex(new TextEncoder().encode(canonicalJson(enqueueInput)));
  if (`sha256:${digest}` !== value.request_digest) {
    throw new Error("SDK_HUMAN_REVIEW_PREPARATION_DIGEST_INVALID");
  }
  if (value.state === "PREPARED"
      && (value.safe_to_clear || value.executed_at !== null || value.task_id !== null)) {
    throw new Error("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
  }
  if (value.state === "EXECUTED"
      && (!value.safe_to_clear || value.executed_at === null || value.task_id === null)) {
    throw new Error("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
  }
  if (value.state === "EXPIRED"
      && (!value.safe_to_clear || value.executed_at !== null || value.task_id !== null)) {
    throw new Error("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
  }
  return { preparation: value, enqueueInput };
}

function validateHumanReviewPreparationAbsence(
  value: Json | undefined,
  expected: ExpectedExecutionRequest,
): Record<string, Json> {
  if (
    !jsonObject(value)
    || !exactFields(value, humanReviewEnqueuePreparationAbsenceFields)
    || value.schema_version !== "human-review-enqueue-preparation-absence-v1"
    || value.recovery_handle !== expected.input.recovery_handle
    || value.state !== "ABSENT"
    || value.safe_to_clear !== true
  ) throw new Error("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
  return value;
}

async function validateHumanReviewExecutionOutput(
  output: Record<string, Json>,
  expected: ExpectedExecutionRequest,
  resultCode: Json | undefined,
): Promise<void> {
  const metadata = ["handler_id", "phase", "metrics"];
  if (
    output.handler_id !== "execute_human_review_and_correction"
    || output.phase !== "review"
    || !jsonObject(output.metrics) || !exactFields(output.metrics, [])
  ) throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
  const operation = expected.operation.replace(/-/g, "_");
  if (operation === HUMAN_REVIEW_SOURCE_LIST_OPERATION) {
    if (resultCode !== "HUMAN_REVIEW_SOURCES_LISTED") {
      throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID");
    }
    if (
      !exactFields(expected.input, ["content_id", "expected_asset_version", "kinds", "limit", "cursor"])
      || !exactFields(output, [...metadata, "sources", "next_cursor", "total"])
    ) {
      throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    }
    const inputCursor = expected.input.cursor;
    if (
      !Array.isArray(output.sources)
      || typeof expected.input.content_id !== "string"
      || !resourceIdPattern.test(expected.input.content_id)
      || !safeVersion(expected.input.expected_asset_version)
      || !Array.isArray(expected.input.kinds)
      || expected.input.kinds.some((kind) => typeof kind !== "string"
        || !["TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT"].includes(kind))
      || expected.input.kinds.some((kind, index) => index > 0
        && ((expected.input.kinds as Json[])[index - 1] as string) >= (kind as string))
      || !safeVersion(output.total, true)
      || output.total > HUMAN_REVIEW_SOURCE_COLLECTION_MAX_ITEMS
      || output.total < output.sources.length
      || !safeVersion(expected.input.limit)
      || expected.input.limit > HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS
      || output.sources.length > Math.min(expected.input.limit, HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS)
      || inputCursor !== null && typeof inputCursor !== "string"
    ) throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    const priorCursor = inputCursor === null
      ? null
      : await validateHumanReviewSourceCursor(inputCursor, expected);
    const sources: Record<string, Json>[] = [];
    for (const source of output.sources) {
      sources.push(await validateHumanReviewSource(source, false, expected.input));
    }
    const pairs = sources.map((source) => `${source.target_kind}\u0000${source.target_digest}`);
    const sortedPairs = [...new Set(pairs)].sort();
    const kinds = expected.input.kinds;
    if (
      pairs.length !== sortedPairs.length
      || pairs.some((pair, index) => pair !== sortedPairs[index])
      || Array.isArray(kinds) && kinds.length > 0
      && sources.some((source) => !kinds.includes(source.target_kind))
      || priorCursor !== null && pairs.length > 0
      && pairs[0] <= `${priorCursor.target_kind}\u0000${priorCursor.target_digest}`
    ) throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    if (output.next_cursor === null) {
      if (
        inputCursor === null && output.total !== sources.length
        || inputCursor !== null && output.total <= sources.length
      ) {
        throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
    } else {
      const nextCursor = await validateHumanReviewSourceCursor(output.next_cursor, expected);
      if (
        sources.length !== expected.input.limit
        || output.total <= sources.length
        || pairs.length === 0
        || `${nextCursor.target_kind}\u0000${nextCursor.target_digest}` !== pairs[pairs.length - 1]
        || priorCursor !== null
        && (nextCursor.collection_digest !== priorCursor.collection_digest
          || nextCursor.collection_generation !== priorCursor.collection_generation)
      ) throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    }
    return;
  }
  if (operation === HUMAN_REVIEW_SOURCE_GET_OPERATION) {
    if (resultCode !== "HUMAN_REVIEW_SOURCE_RETRIEVED") {
      throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID");
    }
    if (
      !exactFields(expected.input, [
        "content_id", "expected_asset_version", "target_kind", "target_digest",
        "expected_head_version",
      ])
      || !exactFields(output, [...metadata, "source"])
    ) {
      throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    }
    const source = await validateHumanReviewSource(output.source, true, expected.input);
    if (
      source.target_kind !== expected.input.target_kind
      || source.target_digest !== expected.input.target_digest
      || source.head_version !== expected.input.expected_head_version
    ) throw new Error("SDK_HUMAN_REVIEW_SOURCE_BINDING_INVALID");
    return;
  }
  if (operation === HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION) {
    if (resultCode !== "HUMAN_REVIEW_TASK_ENQUEUED") {
      throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID");
    }
    if (!exactFields(output, [...metadata, "task"])) {
      throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    }
    validateHumanReviewEnqueueInput(expected.input);
    await validateHumanReviewTask(output.task, expected);
    return;
  }
  if (operation === HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION) {
    if (
      resultCode !== "HUMAN_REVIEW_ENQUEUE_PREPARED"
      || !exactFields(expected.input, humanReviewEnqueuePrepareFields)
      || !boundedText(expected.input.execute_idempotency_key, 200)
      || new TextEncoder().encode(expected.input.execute_idempotency_key).byteLength < 8
      || !exactFields(output, [...metadata, "preparation"])
    ) throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    await validateHumanReviewPreparation(output.preparation, expected, new Set(["PREPARED"]));
    return;
  }
  if (operation === HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION) {
    if (
      !exactFields(expected.input, humanReviewEnqueueExecuteFields)
      || !boundedText(expected.input.recovery_handle, 200)
      || new TextEncoder().encode(expected.input.recovery_handle).byteLength < 32
    ) {
      throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    }
    if (resultCode === "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT") {
      if (!exactFields(output, [...metadata, "preparation"])) {
        throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      validateHumanReviewPreparationAbsence(output.preparation, expected);
      return;
    }
    if (resultCode === "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED") {
      if (!exactFields(output, [...metadata, "preparation"])) {
        throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      await validateHumanReviewPreparation(output.preparation, expected, new Set(["EXPIRED"]));
      return;
    }
    if (resultCode === "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION") {
      if (!exactFields(output, [...metadata, "preparation", "task"])) {
        throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      const { preparation, enqueueInput } = await validateHumanReviewPreparation(
        output.preparation, expected, new Set(["EXECUTED"]),
      );
      const task = await validateHumanReviewTask(output.task, expected, enqueueInput);
      if (preparation.task_id !== task.task_id) {
        throw new Error("SDK_HUMAN_REVIEW_PREPARATION_BINDING_INVALID");
      }
      return;
    }
    throw new Error("SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID");
  }
}

async function validateExecutionResult(
  value: Record<string, Json>,
  expected: ExpectedExecutionRequest,
  rawJson: string,
): Promise<Record<string, Json>> {
  const required = [
    "schema_version", "skill", "operation", "status", "retryable", "trace_id",
    "request_digest", "implementation_state", "external_evidence", "certification",
    "output", "result_digest",
  ];
  const fieldsAreExact = exactFields(value, required) || exactFields(value, [...required, "code"]);
  const status = value.status;
  const output = value.output;
  if (
    !fieldsAreExact
    || value.schema_version !== "1.0.0"
    || typeof value.skill !== "string" || !skillPattern.test(value.skill)
    || typeof value.operation !== "string" || !operationPattern.test(value.operation)
    || typeof status !== "string" || !resultStates.has(status)
    || typeof value.retryable !== "boolean"
    || !boundedText(value.trace_id, 128)
    || typeof value.request_digest !== "string" || !digestPattern.test(value.request_digest)
    || (value.implementation_state !== "CODE_IMPLEMENTED_LOCAL" && value.implementation_state !== "BRIDGE_REQUIRED")
    || value.external_evidence !== "NOT_RUN"
    || value.certification !== "NOT_CERTIFIED"
    || !jsonObject(output)
    || ((status === "BLOCKED" || status === "FAILED") && !("code" in value))
    || ("code" in value && (typeof value.code !== "string" || !publicCodePattern.test(value.code)))
    || typeof value.result_digest !== "string" || !digestPattern.test(value.result_digest)
  ) throw new Error("SDK_RESPONSE_CONTRACT_INVALID");
  if (canonicalJson(value) !== rawJson) throw new Error("SDK_RESPONSE_CANONICAL_JSON_REQUIRED");
  if (
    value.skill !== expected.skill
    || value.operation !== expected.operation
    || value.trace_id !== expected.traceId
    || value.request_digest !== expected.requestDigest
  ) throw new Error("SDK_RESPONSE_REQUEST_BINDING_INVALID");
  if (
    expected.skill === "elmos-multimodal-input-orchestrator"
    && expected.operation.replace(/-/g, "_") === "bootstrap_project"
    && status === "SUCCEEDED"
    && output.project_id !== expected.projectId
  ) throw new Error("SDK_RESPONSE_PROJECT_BINDING_INVALID");
  if (
    expected.skill === HUMAN_REVIEW_SKILL
    && status === "SUCCEEDED"
    && [
      HUMAN_REVIEW_SOURCE_LIST_OPERATION,
      HUMAN_REVIEW_SOURCE_GET_OPERATION,
      HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION,
      HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION,
      HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION,
    ].includes(expected.operation.replace(/-/g, "_"))
  ) await validateHumanReviewExecutionOutput(output, expected, value.code);
  const unsigned = { ...value };
  delete unsigned.result_digest;
  const expectedDigest = await sha256Hex(new TextEncoder().encode(canonicalJson(unsigned)));
  if (value.result_digest !== expectedDigest) throw new Error("SDK_RESPONSE_DIGEST_INVALID");
  return Object.freeze({ ...value });
}

async function validateCapabilityResponse(
  value: Record<string, Json>,
  rawJson: string,
): Promise<Record<string, Json>> {
  if (
    !exactFields(value, [
      "schema_version", "status", "skill_count", "skills", "external_evidence", "certification",
    ])
    || value.schema_version !== "1.0.0"
    || value.status !== "CODE_IMPLEMENTED_LOCAL"
    || value.skill_count !== 50
    || !Array.isArray(value.skills) || value.skills.length !== 50
    || value.external_evidence !== "NOT_RUN"
    || value.certification !== "NOT_CERTIFIED"
  ) throw new Error("SDK_CAPABILITIES_CONTRACT_INVALID");
  if (canonicalJson(value) !== rawJson) throw new Error("SDK_CAPABILITIES_CANONICAL_JSON_REQUIRED");
  const ordinals = new Set<number>();
  const names = new Set<string>();
  for (const rawItem of value.skills) {
    if (!jsonObject(rawItem)) throw new Error("SDK_CAPABILITIES_CONTRACT_INVALID");
    const item = rawItem;
    const transport = item.transport;
    if (
      !exactFields(item, [
        "ordinal", "skill", "handler_id", "phase", "implementation_state",
        "external_evidence", "certification", "transport",
      ])
      || typeof item.ordinal !== "number" || !Number.isSafeInteger(item.ordinal)
      || item.ordinal < 1 || item.ordinal > 50 || ordinals.has(item.ordinal)
      || typeof item.skill !== "string" || !skillPattern.test(item.skill) || names.has(item.skill)
      || typeof item.handler_id !== "string" || !handlerPattern.test(item.handler_id)
      || typeof item.phase !== "string" || !capabilityPhases.has(item.phase)
      || item.implementation_state !== "CODE_IMPLEMENTED_LOCAL"
      || item.external_evidence !== "NOT_RUN"
      || item.certification !== "NOT_CERTIFIED"
      || !jsonObject(transport)
      || !exactFields(transport, ["maximum_request_bytes", "maximum_json_part_bytes", "part_number_base"])
      || transport.maximum_request_bytes !== maximumRequestBytes
      || transport.maximum_json_part_bytes !== 1024 * 1024
      || transport.part_number_base !== 0
    ) throw new Error("SDK_CAPABILITIES_CONTRACT_INVALID");
    ordinals.add(item.ordinal);
    names.add(item.skill);
  }
  if (ordinals.size !== 50 || names.size !== 50) throw new Error("SDK_CAPABILITIES_CONTRACT_INVALID");
  const catalogDigest = await sha256Hex(new TextEncoder().encode(canonicalJson(value.skills)));
  const documentDigest = await sha256Hex(new TextEncoder().encode(canonicalJson(value)));
  if (
    catalogDigest !== expectedCapabilityCatalogDigest
    || documentDigest !== expectedCapabilityDocumentDigest
  ) throw new Error("SDK_CAPABILITIES_DIGEST_INVALID");
  return Object.freeze({ ...value, skills: Object.freeze([...value.skills]) as unknown as Json });
}

function validateErrorEnvelope(
  value: Record<string, Json>,
  statusCode: number,
  rawJson: string,
): { code: string; retryable: boolean; traceId: string | null } {
  const required = ["schema_version", "status", "code", "retryable", "trace_id"];
  const fieldsAreExact = exactFields(value, required);
  if (
    !Number.isInteger(statusCode)
    || statusCode < 400 || statusCode > 599
    || !fieldsAreExact
    || value.schema_version !== "1.0.0"
    || value.status !== (statusCode >= 500 ? "FAILED" : "BLOCKED")
    || typeof value.code !== "string" || !publicCodePattern.test(value.code)
    || typeof value.retryable !== "boolean"
    || !boundedText(value.trace_id, 128)
  ) throw new Error("SDK_ERROR_RESPONSE_CONTRACT_INVALID");
  if (canonicalJson(value) !== rawJson) throw new Error("SDK_ERROR_RESPONSE_CANONICAL_JSON_REQUIRED");
  return {
    code: value.code,
    retryable: value.retryable,
    traceId: value.trace_id as string,
  };
}

function progressTimestamp(value: Json | undefined): boolean {
  return validTimestamp(value);
}

async function validateProgressDocument(
  value: Record<string, Json>,
  resourceKind: ProgressResourceKind,
  resourceId: string,
  eventName: string,
  eventId: string | null,
  requestedCursor: string | null,
): Promise<ProgressDocument> {
  const common = ["schema_version", "kind", "resource_id", "sequence_number", "content_digest", "cursor"];
  const sequence = value.sequence_number;
  const digestMatch = typeof value.content_digest === "string" ? contentDigestPattern.exec(value.content_digest) : null;
  if (
    value.schema_version !== "1.0.0"
    || value.resource_id !== resourceId
    || typeof sequence !== "number"
    || !Number.isSafeInteger(sequence)
    || sequence < 0
    || !digestMatch
  ) throw new Error("SDK_PROGRESS_ENVELOPE_INVALID");
  const parsedRequested = strictCursor(requestedCursor);
  if (eventName === "heartbeat") {
    if (
      !exactFields(value, [...common, "status"])
      || value.kind !== `${resourceKind.toUpperCase()}_PROGRESS_HEARTBEAT`
      || value.status !== "NO_CHANGE"
      || eventId !== null
      || value.cursor !== requestedCursor
      || sequence !== (parsedRequested?.sequence ?? 0)
    ) throw new Error("SDK_PROGRESS_HEARTBEAT_INVALID");
  } else if (eventName === "progress" && resourceKind === "task") {
    const states = new Set(["PENDING", "RUNNING", "PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"]);
    const transitions: Record<string, ReadonlySet<string>> = {
      PENDING: new Set(["RUNNING", "CANCELLED"]),
      RUNNING: new Set(["PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"]),
      PAUSED: new Set(["RUNNING", "CANCELLED"]),
      FAILED_RETRYABLE: new Set(["RUNNING", "FAILED_FINAL", "CANCELLED"]),
      SUCCEEDED: new Set(), FAILED_FINAL: new Set(), CANCELLED: new Set(),
    };
    if (
      !exactFields(value, [...common, "event_type", "state", "previous_state", "occurred_at"])
      || value.kind !== "TASK_PROGRESS"
      || value.event_type !== "durable.task.transitioned"
      || typeof value.state !== "string" || !states.has(value.state)
      || typeof value.previous_state !== "string" || !states.has(value.previous_state)
      || !transitions[value.previous_state].has(value.state)
      || !progressTimestamp(value.occurred_at)
    ) throw new Error("SDK_PROGRESS_ENVELOPE_INVALID");
  } else if (eventName === "progress" && resourceKind === "job") {
    const attempt = value.attempt;
    const maximumAttempts = value.max_attempts;
    if (
      !exactFields(value, [...common, "event_type", "state", "result_status", "attempt", "max_attempts", "occurred_at"])
      || value.kind !== "JOB_PROGRESS"
      || value.event_type !== "processing.job.snapshot"
      || typeof value.state !== "string" || !Object.hasOwn(jobProgressResultByState, value.state)
      || value.result_status !== jobProgressResultByState[value.state]
      || typeof attempt !== "number" || !Number.isSafeInteger(attempt) || attempt < 0
      || typeof maximumAttempts !== "number" || !Number.isSafeInteger(maximumAttempts)
      || maximumAttempts < 1 || attempt > maximumAttempts
      || !progressTimestamp(value.occurred_at)
    ) throw new Error("SDK_PROGRESS_ENVELOPE_INVALID");
  } else {
    throw new Error("SDK_PROGRESS_ENVELOPE_INVALID");
  }
  const unsigned = { ...value };
  delete unsigned.content_digest;
  delete unsigned.cursor;
  const expectedDigest = await sha256Hex(new TextEncoder().encode(canonicalJson(unsigned)));
  if (digestMatch[1] !== expectedDigest) throw new Error("SDK_PROGRESS_DIGEST_INVALID");
  if (eventName === "progress") {
    const expectedCursor = `p1-${sequence}-${expectedDigest}`;
    if (
      value.cursor !== expectedCursor
      || eventId !== expectedCursor
      || parsedRequested && sequence <= parsedRequested.sequence
    ) throw new Error("SDK_PROGRESS_CURSOR_INVALID");
  }
  return Object.freeze({ ...value });
}

async function readBoundedBody(response: Response): Promise<Uint8Array> {
  const declared = response.headers.get("content-length");
  if (declared && (
    !/^[0-9]{1,10}$/.test(declared)
    || Number(declared) < 1
    || Number(declared) > maximumResponseBytes
  )) {
    throw new Error("SDK_RESPONSE_TOO_LARGE");
  }
  if (!response.body) throw new Error("SDK_RESPONSE_INVALID");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let observed = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      observed += value.byteLength;
      if (observed > maximumResponseBytes) {
        await reader.cancel("SDK_RESPONSE_TOO_LARGE");
        throw new Error("SDK_RESPONSE_TOO_LARGE");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  if (observed === 0) throw new Error("SDK_RESPONSE_INVALID");
  if (declared && observed !== Number(declared)) throw new Error("SDK_RESPONSE_SIZE_INVALID");
  const bytes = new Uint8Array(observed);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes;
}

async function rejectRemoteError(response: Response): Promise<never> {
  if (response.status < 400 || response.status > 599) throw new Error("SDK_HTTP_STATUS_INVALID");
  const errorContentType = response.headers.get("content-type");
  if (errorContentType === null || errorContentType.includes(",") || !jsonMediaType(errorContentType)) {
    throw new Error("SDK_ERROR_RESPONSE_CONTENT_TYPE_INVALID");
  }
  const encoding = response.headers.get("content-encoding")?.trim().toLowerCase();
  if (encoding && encoding !== "identity") throw new Error("SDK_ERROR_RESPONSE_CONTENT_ENCODING_INVALID");
  const bytes = await readBoundedBody(response);
  const { rawJson, value: parsed } = parseStrictJsonBytes(bytes, "SDK_ERROR_RESPONSE_INVALID");
  if (!jsonObject(parsed)) {
    throw new Error("SDK_ERROR_RESPONSE_CONTRACT_INVALID");
  }
  const envelope = validateErrorEnvelope(parsed, response.status, rawJson);
  throw new MultimodalIntakeRemoteError(
    response.status, envelope.code, envelope.retryable, envelope.traceId,
  );
}

export async function parseProgressSse(
  bytes: Uint8Array,
  resourceKind: ProgressResourceKind,
  resourceId: string,
  requestedCursor: string | null,
): Promise<ProgressBatch> {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength < 1 || bytes.byteLength > maximumResponseBytes) {
    throw new Error("SDK_PROGRESS_RESPONSE_SIZE_INVALID");
  }
  if (resourceKind !== "task" && resourceKind !== "job") {
    throw new Error("SDK_PROGRESS_RESOURCE_KIND_INVALID");
  }
  const safeResourceId = strictResourceId(resourceId);
  strictCursor(requestedCursor);
  let source: string;
  try {
    source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("SDK_PROGRESS_SSE_INVALID");
  }
  if (!source || source.includes("\r") || source.includes("\0") || !source.endsWith("\n\n")) {
    throw new Error("SDK_PROGRESS_SSE_INVALID");
  }
  const frames = source.slice(0, -2).split("\n\n");
  if (frames.length < 1 || frames.length > maximumProgressDocuments) throw new Error("SDK_PROGRESS_SSE_INVALID");
  const documents: ProgressDocument[] = [];
  let heartbeat: ProgressDocument | null = null;
  let previousSequence = strictCursor(requestedCursor)?.sequence ?? 0;
  let previousTaskState: string | null = null;
  for (const frame of frames) {
    const lines = frame.split("\n");
    let eventId: string | null = null;
    if (lines.length === 3 && lines[0].startsWith("id: ")) eventId = lines.shift()!.slice(4);
    if (lines.length !== 2 || !lines[0].startsWith("event: ") || !lines[1].startsWith("data: ")) {
      throw new Error("SDK_PROGRESS_SSE_INVALID");
    }
    const eventName = lines[0].slice(7);
    const rawJson = lines[1].slice(6);
    let parsed: unknown;
    try {
      parsed = new StrictJsonParser(rawJson).parse();
    } catch {
      throw new Error("SDK_PROGRESS_JSON_INVALID");
    }
    assertStrictJson(parsed, "SDK_RESPONSE");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("SDK_PROGRESS_ENVELOPE_INVALID");
    if (canonicalJson(parsed) !== rawJson) throw new Error("SDK_PROGRESS_CANONICAL_JSON_REQUIRED");
    const document = await validateProgressDocument(
      parsed as Record<string, Json>, resourceKind, safeResourceId, eventName, eventId, requestedCursor,
    );
    if (eventName === "heartbeat") {
      if (heartbeat || documents.length || frames.length !== 1) throw new Error("SDK_PROGRESS_HEARTBEAT_INVALID");
      heartbeat = document;
      continue;
    }
    if (resourceKind === "job" && documents.length !== 0) {
      // The job endpoint returns exactly one snapshot or one heartbeat; it is
      // not a task-like transition history.
      throw new Error("SDK_PROGRESS_HISTORY_INVALID");
    }
    const sequence = document.sequence_number as number;
    if ((resourceKind === "task" && sequence !== previousSequence + 1) || sequence <= previousSequence) {
      throw new Error("SDK_PROGRESS_SEQUENCE_INVALID");
    }
    previousSequence = sequence;
    if (resourceKind === "task") {
      const documentPreviousState = document.previous_state as string;
      if (previousTaskState === null && requestedCursor === null && documentPreviousState !== "PENDING") {
        throw new Error("SDK_PROGRESS_HISTORY_INVALID");
      }
      if (previousTaskState !== null && documentPreviousState !== previousTaskState) {
        throw new Error("SDK_PROGRESS_HISTORY_INVALID");
      }
      // A p1 cursor binds sequence and digest but cannot reveal prior task state.
      // Only states observed inside this response batch can extend the chain.
      previousTaskState = document.state as string;
    }
    documents.push(document);
  }
  const nextCursor = documents.length
    ? documents[documents.length - 1].cursor as string
    : (heartbeat?.cursor as string | null | undefined) ?? null;
  return Object.freeze({ resourceKind, resourceId: safeResourceId, documents: Object.freeze(documents), heartbeat, requestedCursor, nextCursor });
}

export class MultimodalIntakeClient {
  constructor(
    private readonly baseUrl: string,
    private readonly bearerToken: string,
    private readonly timeoutMs = 30_000,
  ) {
    const endpoint = new URL(baseUrl);
    if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash) throw new Error("SDK_BASE_URL_INVALID");
    if (endpoint.protocol !== "https:" && !(endpoint.protocol === "http:" && numericLoopbackHost(endpoint.hostname))) {
      throw new Error("SDK_BASE_URL_HTTPS_OR_LOOPBACK_REQUIRED");
    }
    if (!validBearerToken(bearerToken)) throw new Error("SDK_TOKEN_INVALID");
    if (!Number.isSafeInteger(timeoutMs) || timeoutMs < minimumTimeoutMs || timeoutMs > maximumTimeoutMs) {
      throw new Error("SDK_TIMEOUT_INVALID");
    }
  }

  capabilities(): Promise<Record<string, Json>> {
    return this.request("GET", CAPABILITIES_PATH);
  }

  async execute(document: RegisteredSkillExecutionRequest): Promise<Record<string, Json>>;
  async execute(document: SkillExecutionRequest): Promise<Record<string, Json>>;
  async execute(document: SkillExecutionRequest): Promise<Record<string, Json>> {
    const expected = await validateExecutionRequest(document);
    return await this.request(
      "POST",
      EXECUTE_PATH,
      document as unknown as Record<string, Json>,
      expected,
    );
  }

  taskProgress(
    taskId: string,
    context: ProgressContext,
    cursor: string | null = null,
  ): Promise<ProgressBatch> {
    return this.progress("task", taskId, context, cursor);
  }

  jobProgress(
    jobId: string,
    context: ProgressContext,
    cursor: string | null = null,
  ): Promise<ProgressBatch> {
    return this.progress("job", jobId, context, cursor);
  }

  private async progress(
    resourceKind: ProgressResourceKind,
    rawResourceId: string,
    context: ProgressContext,
    cursor: string | null,
  ): Promise<ProgressBatch> {
    const resourceId = strictResourceId(rawResourceId);
    strictCursor(cursor);
    if (
      !context
      || typeof context !== "object"
      || !resourceIdPattern.test(context.tenantId)
      || !resourceIdPattern.test(context.projectId)
      || !actorIdPattern.test(context.actorId)
    ) throw new Error("SDK_PROGRESS_BOUND_IDENTITY_INVALID");
    const prefix = resourceKind === "task" ? PROGRESS_TASK_EVENTS_PREFIX : PROGRESS_JOB_EVENTS_PREFIX;
    const endpoint = new URL(`${prefix}${resourceId}/events`, this.baseUrl);
    if (cursor !== null) endpoint.searchParams.set("cursor", cursor);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(endpoint, {
        method: "GET",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
        headers: {
          Accept: "text/event-stream",
          Authorization: `Bearer ${this.bearerToken}`,
          "X-ELMOS-Bound-Tenant": context.tenantId,
          "X-ELMOS-Bound-Project": context.projectId,
          "X-ELMOS-Bound-Actor": context.actorId,
        },
      });
      if (response.status !== 200) await rejectRemoteError(response);
      const mediaType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
      if (mediaType !== "text/event-stream") throw new Error("SDK_PROGRESS_CONTENT_TYPE_INVALID");
      const encoding = response.headers.get("content-encoding")?.trim().toLowerCase();
      if (encoding && encoding !== "identity") throw new Error("SDK_PROGRESS_CONTENT_ENCODING_INVALID");
      const bytes = await readBoundedBody(response);
      return await parseProgressSse(bytes, resourceKind, resourceId, cursor);
    } finally {
      clearTimeout(timer);
    }
  }

  private async request(
    method: string,
    path: string,
    body?: Record<string, Json>,
    expectedRequest?: ExpectedExecutionRequest,
  ): Promise<Record<string, Json>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(new URL(path, this.baseUrl), {
        method,
        redirect: "error",
        signal: controller.signal,
        headers: { Accept: "application/json", Authorization: `Bearer ${this.bearerToken}`, ...(body ? { "Content-Type": "application/json" } : {}) },
        body: body ? (() => {
          assertStrictJson(body, "SDK_REQUEST");
          const encoded = canonicalJson(body);
          if (new TextEncoder().encode(encoded).byteLength > maximumRequestBytes) throw new Error("SDK_REQUEST_TOO_LARGE");
          return encoded;
        })() : undefined,
      });
      if (response.status !== 200) await rejectRemoteError(response);
      if (!jsonMediaType(response.headers.get("content-type"))) throw new Error("SDK_RESPONSE_CONTENT_TYPE_INVALID");
      const encoding = response.headers.get("content-encoding")?.trim().toLowerCase();
      if (encoding && encoding !== "identity") throw new Error("SDK_RESPONSE_CONTENT_ENCODING_INVALID");
      const bytes = await readBoundedBody(response);
      const { rawJson, value } = parseStrictJsonBytes(bytes, "SDK_RESPONSE_INVALID");
      if (!jsonObject(value)) throw new Error("SDK_RESPONSE_INVALID");
      if (path === CAPABILITIES_PATH && method === "GET" && body === undefined) {
        return await validateCapabilityResponse(value, rawJson);
      }
      if (path === EXECUTE_PATH && method === "POST" && body !== undefined && expectedRequest) {
        return await validateExecutionResult(value, expectedRequest, rawJson);
      }
      throw new Error("SDK_RESPONSE_ROUTE_INVALID");
    } finally {
      clearTimeout(timer);
    }
  }
}
