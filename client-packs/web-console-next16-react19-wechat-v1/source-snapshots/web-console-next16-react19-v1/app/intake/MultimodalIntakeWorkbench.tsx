"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  canonicalStrictJson,
  parseStrictJson,
  StrictJsonError,
} from "../../lib/multimodal-intake/strictJson";
import { useAccountSession } from "../components/AccountSessionProvider";
import { StatusChip } from "../components/StatusChip";
import { useMicrophoneRecorder } from "./useMicrophoneRecorder";
import styles from "./MultimodalIntakeWorkbench.module.css";

type AssetPhase =
  | "SELECTED"
  | "HASHING"
  | "UPLOADING"
  | "VALIDATING"
  | "PROCESSING"
  | "READY"
  | "NEEDS_REVIEW"
  | "QUARANTINED"
  | "BLOCKED";

type SkillResponse = {
  schema_version?: string;
  status?: string;
  state?: string;
  code?: string;
  error_code?: string;
  retryable?: boolean;
  trace_id?: string;
  request_digest?: string;
  implementation_state?: string;
  external_evidence?: string;
  certification?: string;
  output?: Record<string, unknown>;
  outputs?: Record<string, unknown>;
  data?: Record<string, unknown>;
  result?: Record<string, unknown>;
  result_digest?: string;
  [key: string]: unknown;
};

type AssetDraft = {
  key: string;
  fileFingerprint: string;
  attemptKey: string;
  projectId?: string;
  engineProjectId?: string;
  sessionAttemptKey?: string;
  sessionId?: string;
  file: File;
  relativePath: string;
  phase: AssetPhase;
  progress: number;
  permanentBlock: boolean;
  recoveryCandidate: boolean;
  recoveryAttached: boolean;
  confirmedPartCount: number;
  processingAttempt: number;
  processingJobId?: string;
  sha256?: string;
  uploadSessionId?: string;
  assetId?: string;
  assetVersion?: number;
  code?: string;
  traceId?: string;
  response?: SkillResponse;
  role: "PRIMARY" | "REFERENCE" | "IGNORE";
  modelReadAllowed: boolean;
};

type ReviewTargetKind =
  | "TEXT"
  | "SPEAKER"
  | "TIME_RANGE"
  | "BBOX"
  | "TABLE"
  | "REQUIREMENT"
  | "CONFLICT";

type ReviewTask = {
  tenant_id?: string;
  project_id?: string;
  created_by?: string;
  task_id: string;
  asset_id: string;
  target_kind: ReviewTargetKind;
  target?: Record<string, unknown>;
  original_value?: unknown;
  source_digest?: string;
  source_ref?: Record<string, unknown>;
  reason?: string;
  state: string;
  confidence: number;
  version: number;
  current_correction_version: number;
  current_correction_digest?: string;
  claim_actor_id?: string;
  claim_fence?: number;
  claim_expires_at?: string;
  effective_version?: number;
  effective_digest?: string;
  created_at: string;
  updated_at: string;
  closed_at?: string;
  detail_loaded?: boolean;
};

type ReviewSource = {
  schema_version: "human-review-source-summary-v1" | "human-review-source-detail-v1";
  content_id: string;
  content_version: number;
  target_kind: ReviewTargetKind;
  target: Record<string, unknown>;
  target_digest: string;
  confidence: number;
  head_version: number;
  head_direction: "SNAPSHOT" | "APPLY" | "REVERT";
  head_correction_version: number;
  original_value_client_digest: string;
  original_value_digest_contract: "sha256:rfc8785-ijson-safeint-v1";
  source_ref: Record<string, unknown>;
  original_value?: unknown;
  detail_loaded: boolean;
};

type ReviewClaim = {
  schema_version: 2;
  identity_scope: string;
  project_id: string;
  task_id: string;
  token: string;
  idempotency_key: string;
  expected_version: number;
  created_at: number;
  fence?: number;
  expires_at?: string;
};

type ReviewSourceEnqueueInput = {
  content_id: string;
  expected_asset_version: number;
  target_kind: ReviewTargetKind;
  target_digest: string;
  expected_head_version: number;
  expected_snapshot_id: string;
  expected_snapshot_digest: string;
  expected_head_value_digest: string;
  original_value_digest: string;
  reason: string;
};

type ReviewEnqueueAttempt = {
  schema_version: 3;
  identity_scope: string;
  project_scope_digest: string;
  request_digest: string;
  recovery_handle: string;
  prepare_idempotency_key: string;
  execute_idempotency_key: string;
  created_at: number;
};

type UploadRecoveryRecord = {
  schemaVersion: 2;
  identityScope: string;
  fileFingerprint: string;
  expectedSize: number;
  lastModified: number;
  partSize: number;
  attemptKey: string;
  projectId: string;
  engineProjectId: string;
  sessionAttemptKey: string;
  contentSha256?: string;
  sessionId?: string;
  uploadSessionId?: string;
  confirmedPartCount: number;
  processingAttempt: number;
  assetId?: string;
  assetVersion?: number;
  role: "PRIMARY" | "REFERENCE" | "IGNORE";
  modelReadAllowed: boolean;
  updatedAt: number;
};

const chunkBytes = 256 * 1024;
const maximumProcessableAssetBytes = 64 * 1024 * 1024;
const maximumBatchAssets = 256;
const maximumBatchBytes = 512 * 1024 * 1024;
const maximumSkillResponseBytes = 4 * 1024 * 1024;
const maximumReviewQueueTasks = 10_000;
const maximumReviewQueuePages = 50;
const maximumReviewSources = 1_000;
const maximumReviewSourcePages = 5;
const maximumStoredReviewClaims = 100;
const maximumStoredReviewEnqueueAttempts = 100;
const reviewClaimLeaseSeconds = 900;
const skillRequestTimeoutMs = 60_000;
const pendingReviewClaimRecoveryMs = (
  reviewClaimLeaseSeconds * 1000
  + skillRequestTimeoutMs
  + 2 * 60 * 1000
);
const webBffRoute = "/api/multimodal-intake/v1/execute";
const browserRequestSchemaVersion = "multimodal-intake-browser-request-v1";
const recoveryDatabaseName = "elmos-multimodal-intake-recovery-v1";
const recoveryStoreName = "upload-recovery";
const recoveryRecordKeys = new Set([
  "schemaVersion",
  "identityScope",
  "fileFingerprint",
  "expectedSize",
  "lastModified",
  "partSize",
  "attemptKey",
  "projectId",
  "engineProjectId",
  "sessionAttemptKey",
  "contentSha256",
  "sessionId",
  "uploadSessionId",
  "confirmedPartCount",
  "processingAttempt",
  "assetId",
  "assetVersion",
  "role",
  "modelReadAllowed",
  "updatedAt",
]);
const legacyReviewClaimStorageKey = "elmos-multimodal-review-claims-v1";
const reviewClaimStoragePrefix = "elmos-multimodal-review-claims-v2";
const legacyReviewEnqueueStoragePrefix = "elmos-multimodal-review-enqueue-v1";
const reviewEnqueueStoragePrefix = "elmos-multimodal-review-enqueue-v2";
const reviewClaimKeys = new Set([
  "schema_version",
  "identity_scope",
  "project_id",
  "task_id",
  "token",
  "idempotency_key",
  "expected_version",
  "created_at",
  "fence",
  "expires_at",
]);
const reviewEnqueueAttemptKeys = new Set([
  "schema_version",
  "identity_scope",
  "project_scope_digest",
  "request_digest",
  "recovery_handle",
  "prepare_idempotency_key",
  "execute_idempotency_key",
  "created_at",
]);
const reviewSourceEnqueueInputKeys = new Set([
  "content_id", "expected_asset_version", "target_kind", "target_digest",
  "expected_head_version", "expected_snapshot_id", "expected_snapshot_digest",
  "expected_head_value_digest", "original_value_digest", "reason",
]);
const reviewEnqueuePreparationFields = new Set([
  "schema_version", "recovery_handle", "request_digest", "state", "safe_to_clear",
  "expires_at", "prepared_at", "executed_at", "task_id", "enqueue_input",
]);
const reviewEnqueuePreparationAbsenceFields = new Set([
  "schema_version", "recovery_handle", "state", "safe_to_clear",
]);
const reviewTaskStates = new Set([
  "QUEUED", "CLAIMED", "EDITED", "APPROVED", "REJECTED", "REOPENED",
  "REVERTING", "REVERTED",
]);
const reviewTaskFullFields = new Set([
  "task_id", "tenant_id", "project_id", "asset_id", "target_kind", "target",
  "original_value", "source_digest", "source_ref", "confidence", "reason", "state",
  "current_correction_version", "current_correction_digest", "effective_version",
  "effective_digest", "claim_actor_id", "claim_fence", "claim_expires_at", "version",
  "created_by", "created_at", "updated_at", "closed_at",
]);
const reviewTaskSummaryFields = new Set([
  "schema_version", "task_id", "asset_id", "target_kind", "source_digest", "confidence",
  "reason", "state", "current_correction_version", "current_correction_digest",
  "effective_version", "effective_digest", "claim_actor_id", "claim_fence",
  "claim_expires_at", "version", "created_at", "updated_at", "closed_at",
]);
const reviewSourceRefFields = new Set([
  "schema_version", "content_id", "content_version", "content_digest", "asset_sha256",
  "target_kind", "target_digest", "snapshot_id", "snapshot_digest", "head_version",
  "head_value_digest", "source_digest", "provenance_digest",
  "original_value_client_digest", "original_value_digest_contract",
]);
const reviewSourceSummaryFields = new Set([
  "schema_version", "content_id", "content_version", "target_kind", "target",
  "target_digest", "confidence", "head_version", "head_direction",
  "head_correction_version", "original_value_client_digest",
  "original_value_digest_contract", "source_ref",
]);
const reviewSourceDetailFields = new Set([...reviewSourceSummaryFields, "original_value"]);
const reviewCorrectionFields = new Set([
  "correction_id", "tenant_id", "project_id", "task_id", "correction_version",
  "parent_correction_version", "target_kind", "target", "original_value",
  "corrected_value", "source_digest", "actor_id", "reason", "created_at",
  "correction_digest",
]);
const reviewDecisionFields = new Set([
  "decision_id", "tenant_id", "project_id", "task_id", "decision_version",
  "decision", "prior_state", "next_state", "correction_version",
  "correction_digest", "source_digest", "actor_id", "reason", "created_at",
]);
const reviewPropagationSummaryFields = new Set([
  "propagation_id", "task_id", "decision_id", "correction_version", "channel",
  "direction", "payload_digest", "effective_value_digest", "state", "claim_fence",
  "claim_expires_at", "dispatch_started_at", "failure_code", "reconciliation_required",
  "version", "updated_at",
]);
const reviewEffectiveFields = new Set([
  "materialized", "state", "effective_version", "effective_value",
  "effective_value_digest", "channels",
]);
const reviewEffectiveChannelFields = new Set([
  "channel", "source_decision_id", "correction_version", "direction",
  "effective_value_digest", "version", "updated_at",
]);
const supportedExtensions = new Set([
  "txt", "md", "markdown", "mdx", "log", "pdf", "doc", "docx",
  "png", "jpg", "jpeg", "webp", "heic", "tiff", "bmp", "svg",
  "mp3", "wav", "m4a", "aac", "flac", "ogg", "opus",
  "zip", "tar", "tar.gz", "gz", "tgz",
]);

function safeProject(value: string) {
  return /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value);
}

function relativePath(file: File): string {
  const candidate = file.webkitRelativePath || file.name;
  return candidate.replaceAll("\\", "/").replace(/^\/+/, "");
}

function extensionOf(file: File) {
  const suffixes = file.name.toLocaleLowerCase("en-US").split(".");
  if (suffixes.length > 2 && suffixes.slice(-2).join(".") === "tar.gz") return "tar.gz";
  return suffixes.length > 1 ? suffixes.at(-1) ?? "" : "";
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

async function sha256(buffer: ArrayBuffer): Promise<string> {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", buffer));
  return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function fingerprintFile(file: File): Promise<string> {
  const identity = `${relativePath(file)}\u0000${file.size}\u0000${file.lastModified}`;
  return sha256(new TextEncoder().encode(identity).buffer);
}

const fileHashWorkerSource = `
self.onmessage = async (event) => {
  try {
    const file = event.data;
    const bytes = await file.arrayBuffer();
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const value = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
    self.postMessage({ ok: true, digest: value });
  } catch (_error) {
    self.postMessage({ ok: false });
  }
};
`;

async function sha256FileOffMainThread(file: File): Promise<string> {
  if (typeof Worker === "undefined" || typeof URL.createObjectURL !== "function") {
    throw new Error("FILE_HASH_WORKER_UNAVAILABLE");
  }
  const workerUrl = URL.createObjectURL(new Blob([fileHashWorkerSource], { type: "text/javascript" }));
  let worker: Worker | undefined;
  try {
    const activeWorker = new Worker(workerUrl);
    worker = activeWorker;
    return await new Promise<string>((resolve, reject) => {
      activeWorker.onmessage = (event: MessageEvent<{ ok?: boolean; digest?: unknown }>) => {
        const digest = event.data?.digest;
        if (event.data?.ok === true && typeof digest === "string" && /^[0-9a-f]{64}$/.test(digest)) {
          resolve(digest);
          return;
        }
        reject(new Error("FILE_HASH_WORKER_FAILED"));
      };
      activeWorker.onerror = () => reject(new Error("FILE_HASH_WORKER_FAILED"));
      activeWorker.onmessageerror = () => reject(new Error("FILE_HASH_WORKER_FAILED"));
      activeWorker.postMessage(file);
    });
  } finally {
    worker?.terminate();
    URL.revokeObjectURL(workerUrl);
  }
}

function boundedOpaque(value: unknown): value is string {
  return typeof value === "string"
    && value.length > 0
    && value.length <= 512
    && !/[\u0000-\u001f\u007f]/.test(value);
}

function reviewClaimStorageKey(identityScope: string): string {
  return `${reviewClaimStoragePrefix}:${identityScope}`;
}

function reviewEnqueueStorageKey(identityScope: string): string {
  return `${reviewEnqueueStoragePrefix}:${identityScope}`;
}

function structurallyValidReviewEnqueueAttempt(
  value: unknown,
): value is ReviewEnqueueAttempt {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const attempt = value as Record<string, unknown>;
  return Object.keys(attempt).length === reviewEnqueueAttemptKeys.size
    && Object.keys(attempt).every((key) => reviewEnqueueAttemptKeys.has(key))
    && attempt.schema_version === 3
    && typeof attempt.identity_scope === "string"
    && /^sha256:[0-9a-f]{64}$/.test(attempt.identity_scope)
    && typeof attempt.project_scope_digest === "string"
    && /^sha256:[0-9a-f]{64}$/.test(attempt.project_scope_digest)
    && typeof attempt.request_digest === "string"
    && /^sha256:[0-9a-f]{64}$/.test(attempt.request_digest)
    && typeof attempt.recovery_handle === "string"
    && /^mmi-review-recovery-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      attempt.recovery_handle,
    )
    && typeof attempt.prepare_idempotency_key === "string"
    && /^mmi-review-enqueue-prepare-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      attempt.prepare_idempotency_key,
    )
    && typeof attempt.execute_idempotency_key === "string"
    && /^mmi-review-enqueue-execute-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
      attempt.execute_idempotency_key,
    )
    && attempt.prepare_idempotency_key !== attempt.execute_idempotency_key
    && typeof attempt.created_at === "number"
    && Number.isSafeInteger(attempt.created_at)
    && attempt.created_at >= 0
    && attempt.created_at <= Date.now() + 60_000;
}

function structurallyValidReviewSourceEnqueueInput(
  value: unknown,
): value is ReviewSourceEnqueueInput {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const input = value as Record<string, unknown>;
  const targetKind = input.target_kind as ReviewTargetKind;
  return exactObjectFields(input, reviewSourceEnqueueInputKeys)
    && typeof input.content_id === "string"
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(input.content_id)
    && positiveInteger(input.expected_asset_version) !== undefined
    && typeof input.target_kind === "string"
    && reviewTargetKinds.has(targetKind)
    && typeof input.target_digest === "string"
    && sha256ReferencePattern.test(input.target_digest)
    && positiveInteger(input.expected_head_version) !== undefined
    && boundedOpaque(input.expected_snapshot_id)
    && typeof input.expected_snapshot_digest === "string"
    && sha256ReferencePattern.test(input.expected_snapshot_digest)
    && typeof input.expected_head_value_digest === "string"
    && sha256ReferencePattern.test(input.expected_head_value_digest)
    && typeof input.original_value_digest === "string"
    && sha256ReferencePattern.test(input.original_value_digest)
    && exactRequiredText(input.reason, 2_000);
}

function loadReviewEnqueueAttempts(
  identityScope: string,
): Record<string, ReviewEnqueueAttempt> {
  if (typeof sessionStorage === "undefined") return {};
  const storageKey = reviewEnqueueStorageKey(identityScope);
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return {};
    const parsed = parseStrictJson(raw);
    if (!Array.isArray(parsed) || parsed.length > maximumStoredReviewEnqueueAttempts) {
      throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CORRUPT");
    }
    const attempts: Record<string, ReviewEnqueueAttempt> = {};
    for (const value of parsed) {
      if (
        !structurallyValidReviewEnqueueAttempt(value)
        || value.identity_scope !== identityScope
        || attempts[value.request_digest]
      ) {
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CORRUPT");
      }
      attempts[value.request_digest] = value;
    }
    const normalized = canonicalStrictJson(Object.values(attempts).sort(
      (left, right) => left.request_digest.localeCompare(right.request_digest),
    ));
    if (normalized !== raw) {
      try {
        sessionStorage.setItem(storageKey, normalized);
      } catch {
        // Keep the valid raw receipt and in-memory attempt; UNKNOWN never
        // becomes retryable merely because normalization could not persist.
      }
    }
    return attempts;
  } catch (error) {
    // A malformed or legacy receipt may still represent an UNKNOWN side
    // effect. Never erase it or silently turn it into a fresh retry.
    throw error instanceof Error
      ? error
      : new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CORRUPT");
  }
}

function persistReviewEnqueueAttempts(
  identityScope: string,
  attempts: Record<string, ReviewEnqueueAttempt>,
): boolean {
  const values = Object.values(attempts);
  if (
    typeof sessionStorage === "undefined"
    || values.length > maximumStoredReviewEnqueueAttempts
    || values.some((attempt) => (
      !structurallyValidReviewEnqueueAttempt(attempt)
      || attempt.identity_scope !== identityScope
    ))
  ) return false;
  values.sort((left, right) => left.request_digest.localeCompare(right.request_digest));
  try {
    sessionStorage.setItem(reviewEnqueueStorageKey(identityScope), canonicalStrictJson(values));
    return true;
  } catch {
    return false;
  }
}

async function reviewEnqueueRequestDigest(
  input: ReviewSourceEnqueueInput,
): Promise<string> {
  return `sha256:${await sha256(
    new TextEncoder().encode(canonicalStrictJson(input)).buffer,
  )}`;
}

async function reviewProjectScopeDigest(
  identityScope: string,
  projectId: string,
): Promise<string> {
  return `sha256:${await sha256(new TextEncoder().encode(canonicalStrictJson({
    schema_version: "multimodal-review-project-scope-v1",
    identity_scope: identityScope,
    project_id: projectId,
  })).buffer)}`;
}

async function validatedReviewEnqueuePreparation(
  value: unknown,
  attempt: ReviewEnqueueAttempt,
  expectedStates: ReadonlySet<"PREPARED" | "EXECUTED" | "EXPIRED">,
): Promise<{ preparation: Record<string, unknown>; input: ReviewSourceEnqueueInput }> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
  }
  const preparation = value as Record<string, unknown>;
  const state = preparation.state;
  const input = preparation.enqueue_input;
  if (
    !exactObjectFields(preparation, reviewEnqueuePreparationFields)
    || preparation.schema_version !== "human-review-enqueue-preparation-v1"
    || preparation.recovery_handle !== attempt.recovery_handle
    || preparation.request_digest !== attempt.request_digest
    || typeof state !== "string"
    || !expectedStates.has(state as "PREPARED" | "EXECUTED" | "EXPIRED")
    || typeof preparation.safe_to_clear !== "boolean"
    || !exactTimestamp(preparation.expires_at)
    || !exactTimestamp(preparation.prepared_at)
    || Date.parse(preparation.expires_at as string) <= Date.parse(preparation.prepared_at as string)
    || !structurallyValidReviewSourceEnqueueInput(input)
    || await reviewEnqueueRequestDigest(input) !== attempt.request_digest
  ) throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
  if (state === "PREPARED" && (
    preparation.safe_to_clear !== false
    || preparation.executed_at !== null
    || preparation.task_id !== null
  )) throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
  if (state === "EXECUTED" && (
    preparation.safe_to_clear !== true
    || !exactTimestamp(preparation.executed_at)
    || !boundedOpaque(preparation.task_id)
    || Date.parse(preparation.executed_at as string) < Date.parse(preparation.prepared_at as string)
  )) throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
  if (state === "EXPIRED" && (
    preparation.safe_to_clear !== true
    || preparation.executed_at !== null
    || preparation.task_id !== null
  )) throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
  return { preparation, input };
}

function exactReviewEnqueuePreparationAbsence(
  value: unknown,
  attempt: ReviewEnqueueAttempt,
): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const preparation = value as Record<string, unknown>;
  return exactObjectFields(preparation, reviewEnqueuePreparationAbsenceFields)
    && preparation.schema_version === "human-review-enqueue-preparation-absence-v1"
    && preparation.recovery_handle === attempt.recovery_handle
    && preparation.state === "ABSENT"
    && preparation.safe_to_clear === true;
}

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

async function validatedJobProgressEvent(
  source: string,
  jobId: string,
  lastEventId: string,
): Promise<Record<string, unknown>> {
  const value = parseStrictJson(source, { maximumDepth: 4, maximumNodes: 32 });
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("MULTIMODAL_PROGRESS_EVENT_INVALID");
  }
  const event = value as Record<string, unknown>;
  const fields = new Set([
    "schema_version", "kind", "resource_id", "sequence_number", "event_type",
    "state", "result_status", "attempt", "max_attempts", "occurred_at",
    "content_digest", "cursor",
  ]);
  const state = event.state;
  if (
    !exactObjectFields(event, fields)
    || event.schema_version !== "1.0.0"
    || event.kind !== "JOB_PROGRESS"
    || event.resource_id !== jobId
    || typeof event.sequence_number !== "number"
    || !Number.isSafeInteger(event.sequence_number)
    || event.sequence_number < 1
    || event.event_type !== "processing.job.snapshot"
    || typeof state !== "string"
    || !Object.hasOwn(jobProgressResultByState, state)
    || event.result_status !== jobProgressResultByState[state]
    || typeof event.attempt !== "number"
    || !Number.isSafeInteger(event.attempt)
    || typeof event.max_attempts !== "number"
    || !Number.isSafeInteger(event.max_attempts)
    || event.attempt < 0
    || event.max_attempts < 1
    || event.attempt > event.max_attempts
    || !exactTimestamp(event.occurred_at)
    || typeof event.content_digest !== "string"
    || !sha256ReferencePattern.test(event.content_digest)
    || typeof event.cursor !== "string"
    || event.cursor !== lastEventId
  ) throw new Error("MULTIMODAL_PROGRESS_EVENT_INVALID");
  const unsigned = { ...event };
  delete unsigned.content_digest;
  delete unsigned.cursor;
  const digest = await sha256(
    new TextEncoder().encode(canonicalStrictJson(unsigned)).buffer,
  );
  if (
    event.content_digest !== `sha256:${digest}`
    || event.cursor !== `p1-${event.sequence_number}-${digest}`
  ) throw new Error("MULTIMODAL_PROGRESS_EVENT_DIGEST_INVALID");
  return event;
}

function structurallyValidReviewClaim(value: unknown): value is ReviewClaim {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const claim = value as Record<string, unknown>;
  if (Object.keys(claim).some((key) => !reviewClaimKeys.has(key))) return false;
  const fence = claim.fence;
  const expiresAt = claim.expires_at;
  if (
    claim.schema_version !== 2
    || typeof claim.identity_scope !== "string"
    || !/^sha256:[0-9a-f]{64}$/.test(claim.identity_scope)
    || typeof claim.project_id !== "string"
    || !safeProject(claim.project_id)
    || typeof claim.task_id !== "string"
    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(claim.task_id)
    || !boundedOpaque(claim.token)
    || !boundedOpaque(claim.idempotency_key)
    || new TextEncoder().encode(claim.token as string).byteLength < 8
    || new TextEncoder().encode(claim.token as string).byteLength > 200
    || new TextEncoder().encode(claim.idempotency_key as string).byteLength < 8
    || new TextEncoder().encode(claim.idempotency_key as string).byteLength > 200
    || typeof claim.expected_version !== "number"
    || !Number.isSafeInteger(claim.expected_version)
    || claim.expected_version < 1
    || typeof claim.created_at !== "number"
    || !Number.isSafeInteger(claim.created_at)
    || claim.created_at < 0
    || claim.created_at > Date.now() + 60_000
    || ((fence === undefined) !== (expiresAt === undefined))
    || (fence !== undefined && (
      typeof fence !== "number"
      || !Number.isSafeInteger(fence)
      || fence < 1
      || typeof expiresAt !== "string"
      || !Number.isFinite(Date.parse(expiresAt))
    ))
  ) return false;
  return true;
}

function validReviewClaim(
  value: unknown,
  identityScope: string,
  now = Date.now(),
): value is ReviewClaim {
  if (!structurallyValidReviewClaim(value) || value.identity_scope !== identityScope) return false;
  if (value.fence === undefined) {
    return now - value.created_at <= pendingReviewClaimRecoveryMs;
  }
  return Date.parse(value.expires_at as string) > now;
}

function loadReviewClaims(identityScope: string): Record<string, ReviewClaim> {
  if (typeof sessionStorage === "undefined") return {};
  try {
    const storageKey = reviewClaimStorageKey(identityScope);
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return {};
    const parsed = parseStrictJson(raw);
    if (!Array.isArray(parsed) || parsed.length > maximumStoredReviewClaims) {
      sessionStorage.removeItem(storageKey);
      return {};
    }
    const claims: Record<string, ReviewClaim> = {};
    for (const value of parsed) {
      if (!structurallyValidReviewClaim(value) || claims[value.task_id]) {
        sessionStorage.removeItem(storageKey);
        return {};
      }
      if (validReviewClaim(value, identityScope)) claims[value.task_id] = value;
    }
    const retained = Object.values(claims).sort((left, right) => left.task_id.localeCompare(right.task_id));
    const normalized = canonicalStrictJson(retained);
    if (normalized !== raw) {
      try {
        sessionStorage.setItem(storageKey, normalized);
      } catch {
        // Keep recoverable in-memory receipts; a storage failure must not erase them.
      }
    }
    return claims;
  } catch {
    try {
      sessionStorage.removeItem(reviewClaimStorageKey(identityScope));
    } catch {
      // The next server operation still validates actor, task version, token and fence.
    }
    return {};
  }
}

function persistReviewClaims(
  claims: Record<string, ReviewClaim>,
  identityScope: string,
): boolean {
  if (typeof sessionStorage === "undefined") return false;
  const values = Object.values(claims);
  if (
    values.length > maximumStoredReviewClaims
    || values.some((claim) => !validReviewClaim(claim, identityScope))
  ) return false;
  values.sort((left, right) => left.task_id.localeCompare(right.task_id));
  try {
    sessionStorage.setItem(reviewClaimStorageKey(identityScope), canonicalStrictJson(values));
    return true;
  } catch {
    return false;
  }
}

function validRecoveryRecord(value: unknown): value is UploadRecoveryRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (Object.keys(record).some((key) => !recoveryRecordKeys.has(key))) return false;
  if (
    record.schemaVersion !== 2
    || typeof record.identityScope !== "string"
    || !/^sha256:[0-9a-f]{64}$/.test(record.identityScope)
    || typeof record.fileFingerprint !== "string"
    || !/^[0-9a-f]{64}$/.test(record.fileFingerprint)
    || typeof record.expectedSize !== "number"
    || !Number.isSafeInteger(record.expectedSize)
    || record.expectedSize <= 0
    || record.expectedSize > maximumProcessableAssetBytes
    || typeof record.lastModified !== "number"
    || !Number.isSafeInteger(record.lastModified)
    || record.lastModified < 0
    || record.partSize !== chunkBytes
    || !boundedOpaque(record.attemptKey)
    || typeof record.projectId !== "string"
    || !safeProject(record.projectId)
    || !boundedOpaque(record.engineProjectId)
    || !boundedOpaque(record.sessionAttemptKey)
    || typeof record.confirmedPartCount !== "number"
    || !Number.isSafeInteger(record.confirmedPartCount)
    || record.confirmedPartCount < 0
    || record.confirmedPartCount > Math.ceil(record.expectedSize / chunkBytes)
    || typeof record.processingAttempt !== "number"
    || !Number.isSafeInteger(record.processingAttempt)
    || record.processingAttempt < 0
    || record.processingAttempt > 10_000
    || !["PRIMARY", "REFERENCE", "IGNORE"].includes(String(record.role))
    || typeof record.modelReadAllowed !== "boolean"
    || record.role === "IGNORE" && record.modelReadAllowed
    || typeof record.updatedAt !== "number"
    || !Number.isSafeInteger(record.updatedAt)
    || record.updatedAt < 0
  ) return false;
  for (const key of ["sessionId", "uploadSessionId", "assetId"] as const) {
    if (record[key] !== undefined && !boundedOpaque(record[key])) return false;
  }
  if (record.contentSha256 !== undefined && (
    typeof record.contentSha256 !== "string" || !/^[0-9a-f]{64}$/.test(record.contentSha256)
  )) return false;
  if (record.assetVersion !== undefined && (
    typeof record.assetVersion !== "number"
    || !Number.isSafeInteger(record.assetVersion)
    || record.assetVersion <= 0
  )) return false;
  if (record.uploadSessionId && (!record.sessionId || !record.contentSha256)) return false;
  if (record.confirmedPartCount > 0 && !record.uploadSessionId) return false;
  if (record.assetId && (!record.uploadSessionId || !record.contentSha256)) return false;
  return true;
}

function recoveryStorageKey(
  record: Pick<UploadRecoveryRecord, "identityScope" | "projectId" | "engineProjectId" | "fileFingerprint">,
): string {
  return JSON.stringify([
    record.identityScope,
    record.projectId,
    record.engineProjectId,
    record.fileFingerprint,
  ]);
}

function openRecoveryDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("RECOVERY_STORE_UNAVAILABLE"));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(recoveryDatabaseName, 3);
    request.onupgradeneeded = () => {
      // v1/v2 records could not prove browser identity scope. They contain
      // recovery credentials and therefore cannot be adopted by the active
      // account. Discard them on upgrade; v3 keeps each identity independent.
      if (request.result.objectStoreNames.contains(recoveryStoreName)) {
        request.result.deleteObjectStore(recoveryStoreName);
      }
      request.result.createObjectStore(recoveryStoreName, {
        keyPath: ["identityScope", "projectId", "engineProjectId", "fileFingerprint"],
      });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error("RECOVERY_STORE_UNAVAILABLE"));
    request.onblocked = () => reject(new Error("RECOVERY_STORE_BLOCKED"));
  });
}

async function readRecoveryValues(): Promise<unknown[]> {
  const database = await openRecoveryDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(recoveryStoreName, "readonly");
    const request = transaction.objectStore(recoveryStoreName).getAll();
    let values: unknown[] = [];
    request.onsuccess = () => { values = request.result as unknown[]; };
    request.onerror = () => reject(new Error("RECOVERY_STORE_READ_FAILED"));
    transaction.oncomplete = () => { database.close(); resolve(values); };
    transaction.onerror = () => { database.close(); reject(new Error("RECOVERY_STORE_READ_FAILED")); };
    transaction.onabort = () => { database.close(); reject(new Error("RECOVERY_STORE_READ_FAILED")); };
  });
}

async function replaceRecoveryValues(records: readonly UploadRecoveryRecord[]): Promise<void> {
  const database = await openRecoveryDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(recoveryStoreName, "readwrite");
    const store = transaction.objectStore(recoveryStoreName);
    store.clear();
    for (const record of records) store.put(record);
    transaction.oncomplete = () => { database.close(); resolve(); };
    transaction.onerror = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
    transaction.onabort = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
  });
}

async function putRecoveryValue(record: UploadRecoveryRecord): Promise<void> {
  const database = await openRecoveryDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(recoveryStoreName, "readwrite");
    transaction.objectStore(recoveryStoreName).put(record);
    transaction.oncomplete = () => { database.close(); resolve(); };
    transaction.onerror = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
    transaction.onabort = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
  });
}

async function deleteRecoveryValue(
  record: Pick<UploadRecoveryRecord, "identityScope" | "projectId" | "engineProjectId" | "fileFingerprint">,
): Promise<void> {
  const database = await openRecoveryDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(recoveryStoreName, "readwrite");
    transaction.objectStore(recoveryStoreName).delete([
      record.identityScope,
      record.projectId,
      record.engineProjectId,
      record.fileFingerprint,
    ]);
    transaction.oncomplete = () => { database.close(); resolve(); };
    transaction.onerror = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
    transaction.onabort = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
  });
}

function nestedRecord(response: SkillResponse): Record<string, unknown> {
  for (const candidate of [response.output, response.outputs, response.data, response.result]) {
    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) return candidate;
  }
  return response;
}

type ProjectPackagePageEntry = {
  path: string;
  kind: string;
  role: "PRIMARY" | "REFERENCE" | "IGNORE";
  model_read_allowed: boolean;
  security_state: string;
  override_version: number;
};

type ProjectPackagePage = {
  package_version: number;
  items: ProjectPackagePageEntry[];
  next_cursor: string | null;
  total: number;
  collection_digest: string;
};

type ProcessingEstimate = {
  inputDigest: string;
  status: "READY" | "PARTIAL" | "BLOCKED";
  code: string;
  remainingSecondsP50?: number;
  remainingSecondsP95?: number;
  estimatedCost?: string;
  currency?: string;
  actualsState?: string;
  calibrationVersion?: string;
  estimateDigest?: string;
};

function projectPackagePage(response: SkillResponse): ProjectPackagePage {
  const output = nestedRecord(response);
  const items = output.items;
  const packageVersion = output.package_version;
  const nextCursor = output.next_cursor;
  const total = output.total;
  const collectionDigest = output.collection_digest;
  if (
    !Number.isSafeInteger(packageVersion) || Number(packageVersion) < 1
    || !Number.isSafeInteger(total) || Number(total) < 0
    || !Array.isArray(items) || items.length > 200
    || !(nextCursor === null || typeof nextCursor === "string")
    || typeof collectionDigest !== "string" || !/^[0-9a-f]{64}$/.test(collectionDigest)
  ) throw new Error("PROJECT_PACKAGE_PAGE_INVALID");
  const normalized = items.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new Error("PROJECT_PACKAGE_PAGE_ENTRY_INVALID");
    }
    const entry = item as Record<string, unknown>;
    if (
      typeof entry.path !== "string" || typeof entry.kind !== "string"
      || !["PRIMARY", "REFERENCE", "IGNORE"].includes(String(entry.role))
      || typeof entry.model_read_allowed !== "boolean"
      || typeof entry.security_state !== "string"
      || !Number.isSafeInteger(entry.override_version)
    ) throw new Error("PROJECT_PACKAGE_PAGE_ENTRY_INVALID");
    return entry as ProjectPackagePageEntry;
  });
  return {
    package_version: Number(packageVersion),
    items: normalized,
    next_cursor: nextCursor as string | null,
    total: Number(total),
    collection_digest: collectionDigest,
  };
}

function processingEstimate(
  response: SkillResponse,
  inputDigest: string,
): ProcessingEstimate {
  const output = nestedRecord(response);
  const ledger = output.ledger;
  const p50 = output.remaining_seconds_p50;
  const p95 = output.remaining_seconds_p95;
  const estimatedCost = output.estimated_cost;
  const currency = output.currency;
  const calibrationVersion = output.calibration_version;
  const estimateDigest = output.estimate_digest;
  const status = String(response.status ?? response.state ?? "").toUpperCase();
  if (
    !["SUCCEEDED", "PARTIAL"].includes(status)
    || typeof p50 !== "number" || !Number.isFinite(p50) || p50 < 0
    || typeof p95 !== "number" || !Number.isFinite(p95) || p95 < p50
    || typeof estimatedCost !== "string" || !/^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?$/.test(estimatedCost)
    || typeof currency !== "string" || !/^[A-Z]{3}$/.test(currency)
    || typeof calibrationVersion !== "string" || !boundedOpaque(calibrationVersion)
    || typeof estimateDigest !== "string" || !/^sha256:[0-9a-f]{64}$/.test(estimateDigest)
    || !ledger || typeof ledger !== "object" || Array.isArray(ledger)
  ) throw new Error("PROCESSING_ESTIMATE_RESPONSE_INVALID");
  const actualsState = (ledger as Record<string, unknown>).actuals_state;
  if (
    (ledger as Record<string, unknown>).schema_version !== "multimodal-cost-ledger-v1"
    || typeof actualsState !== "string"
    || !["NOT_RUN", "PENDING", "RECONCILED", "UNKNOWN", "BLOCKED"].includes(actualsState)
  ) throw new Error("PROCESSING_ESTIMATE_LEDGER_INVALID");
  return {
    inputDigest,
    status: status === "SUCCEEDED" ? "READY" : "PARTIAL",
    code: responseString(response, "code") ?? "PROCESSING_COST_ETA_ESTIMATED",
    remainingSecondsP50: p50,
    remainingSecondsP95: p95,
    estimatedCost,
    currency,
    actualsState,
    calibrationVersion,
    estimateDigest,
  };
}

function estimateFileType(file: File): string {
  const extension = extensionOf(file);
  if (["png", "jpg", "jpeg", "webp", "heic", "tiff", "bmp", "svg"].includes(extension)) {
    return "image/*";
  }
  if (["mp3", "wav", "m4a", "aac", "flac", "ogg", "opus"].includes(extension)) {
    return "audio/*";
  }
  if (extension === "pdf") return "application/pdf";
  if (["doc", "docx"].includes(extension)) return "application/word";
  if (["zip", "tar", "tar.gz", "gz", "tgz"].includes(extension)) return "application/archive";
  return "text/plain";
}

function formatEstimateDuration(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)} 秒`;
  if (seconds < 3_600) return `${Math.ceil(seconds / 60)} 分钟`;
  return `${(seconds / 3_600).toFixed(1)} 小时`;
}

function responseString(response: SkillResponse, ...keys: string[]): string | undefined {
  const sources = [response, nestedRecord(response)];
  for (const source of sources) {
    for (const key of keys) {
      const value = source[key];
      if (typeof value === "string" && value) return value;
    }
  }
  return undefined;
}

function outputRecord(response: SkillResponse, key: string): Record<string, unknown> | undefined {
  const value = nestedRecord(response)[key];
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function exactReviewOutput(
  response: SkillResponse,
  keys: readonly string[],
): Record<string, unknown> {
  const output = nestedRecord(response);
  if (
    Object.keys(output).length !== keys.length
    || Object.keys(output).some((key) => !keys.includes(key))
  ) {
    throw new Error("HUMAN_REVIEW_OUTPUT_FIELDS_INVALID");
  }
  return output;
}

const reviewPropagationChannels = new Set([
  "content-index", "requirements", "project-memory", "downstream",
]);

function validReviewPropagations(
  value: unknown,
  taskId: string,
  options: {
    exactBatch: boolean;
    direction?: "APPLY" | "REVERT";
    decisionId?: string;
    correctionVersion?: number;
    initial?: boolean;
  },
): value is Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return false;
  const ids = new Set<string>();
  const channels = new Set<string>();
  const payloadDigests = new Set<string>();
  const effectiveDigests = new Set<string>();
  for (const item of value) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const propagation = item as Record<string, unknown>;
    if (!exactObjectFields(propagation, reviewPropagationSummaryFields)) return false;
    const expiresAt = propagation.claim_expires_at;
    const dispatchStartedAt = propagation.dispatch_started_at;
    const failureCode = propagation.failure_code;
    const state = propagation.state;
    const claimFence = propagation.claim_fence;
    if (
      typeof propagation.propagation_id !== "string"
      || !boundedOpaque(propagation.propagation_id)
      || ids.has(propagation.propagation_id)
      || propagation.task_id !== taskId
      || typeof propagation.channel !== "string"
      || !reviewPropagationChannels.has(propagation.channel)
      || options.exactBatch && channels.has(propagation.channel)
      || !["APPLY", "REVERT"].includes(String(propagation.direction))
      || options.direction !== undefined && propagation.direction !== options.direction
      || options.decisionId !== undefined && propagation.decision_id !== options.decisionId
      || options.correctionVersion !== undefined
        && propagation.correction_version !== options.correctionVersion
      || !boundedOpaque(propagation.decision_id)
      || positiveInteger(propagation.correction_version) === undefined
      || typeof propagation.payload_digest !== "string"
      || !sha256ReferencePattern.test(propagation.payload_digest)
      || typeof propagation.effective_value_digest !== "string"
      || !sha256ReferencePattern.test(propagation.effective_value_digest)
      || typeof state !== "string"
      || !["PENDING", "CLAIMED", "SUCCEEDED", "FAILED", "UNKNOWN"].includes(state)
      || typeof claimFence !== "number"
      || !Number.isSafeInteger(claimFence)
      || claimFence < 0
      || !(expiresAt === null || exactTimestamp(expiresAt))
      || !(dispatchStartedAt === null || exactTimestamp(dispatchStartedAt))
      || !(failureCode === null || boundedOpaque(failureCode))
      || typeof propagation.reconciliation_required !== "boolean"
      || positiveInteger(propagation.version) === undefined
      || !exactTimestamp(propagation.updated_at)
      || options.initial === true && (
        state !== "PENDING" || claimFence !== 0 || propagation.version !== 1
      )
      || state === "PENDING" && (
        expiresAt !== null || dispatchStartedAt !== null || failureCode !== null
        || propagation.reconciliation_required !== false
      )
      || state === "CLAIMED" && (
        claimFence < 1 || !exactTimestamp(expiresAt) || failureCode !== null
        || propagation.reconciliation_required !== false
      )
      || state === "SUCCEEDED" && (
        expiresAt !== null || !exactTimestamp(dispatchStartedAt) || failureCode !== null
        || propagation.reconciliation_required !== false
      )
      || state === "FAILED" && (
        expiresAt !== null || !exactTimestamp(dispatchStartedAt) || !boundedOpaque(failureCode)
        || propagation.reconciliation_required !== false
      )
      || state === "UNKNOWN" && (
        expiresAt !== null || !exactTimestamp(dispatchStartedAt) || !boundedOpaque(failureCode)
        || propagation.reconciliation_required !== true
      )
    ) return false;
    ids.add(propagation.propagation_id);
    channels.add(propagation.channel);
    payloadDigests.add(propagation.payload_digest as string);
    effectiveDigests.add(propagation.effective_value_digest as string);
  }
  return !options.exactBatch || (
    value.length === reviewPropagationChannels.size
    && channels.size === reviewPropagationChannels.size
    && payloadDigests.size === reviewPropagationChannels.size
    && effectiveDigests.size === 1
  );
}

function validHistoricalPropagationBatches(value: unknown, taskId: string): boolean {
  if (!validReviewPropagations(value, taskId, { exactBatch: false })) return false;
  const groups = new Map<string, Array<Record<string, unknown>>>();
  for (const propagation of value) {
    const decisionId = propagation.decision_id as string;
    groups.set(decisionId, [...(groups.get(decisionId) ?? []), propagation]);
  }
  for (const group of groups.values()) {
    const channels = new Set(group.map((item) => item.channel));
    const correctionVersions = new Set(group.map((item) => item.correction_version));
    const directions = new Set(group.map((item) => item.direction));
    const payloadDigests = new Set(group.map((item) => item.payload_digest));
    const effectiveDigests = new Set(group.map((item) => item.effective_value_digest));
    if (
      group.length !== reviewPropagationChannels.size
      || channels.size !== reviewPropagationChannels.size
      || correctionVersions.size !== 1
      || directions.size !== 1
      || payloadDigests.size !== reviewPropagationChannels.size
      || effectiveDigests.size !== 1
    ) return false;
  }
  return true;
}

function positiveInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : undefined;
}

const reviewTargetKinds = new Set<ReviewTargetKind>([
  "TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT",
]);
const sha256ReferencePattern = /^sha256:[0-9a-f]{64}$/;

function exactReviewTarget(kind: ReviewTargetKind, value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const target = value as Record<string, unknown>;
  const exactKeys = (...keys: string[]) => (
    Object.keys(target).length === keys.length && keys.every((key) => Object.hasOwn(target, key))
  );
  const resourceId = (candidate: unknown) => (
    typeof candidate === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(candidate)
  );
  const safeNonNegativeInteger = (candidate: unknown) => (
    typeof candidate === "number" && Number.isSafeInteger(candidate) && candidate >= 0
  );
  if (kind === "TEXT") {
    return exactKeys("path") && typeof target.path === "string"
      && target.path.length > 0 && target.path === target.path.trim()
      && !/[\u0000-\u001f\u007f]/.test(target.path)
      && new TextEncoder().encode(target.path).byteLength <= 1_024;
  }
  if (kind === "SPEAKER") return exactKeys("segment_id") && resourceId(target.segment_id);
  if (kind === "TIME_RANGE") {
    return exactKeys("start_ms", "end_ms")
      && safeNonNegativeInteger(target.start_ms)
      && safeNonNegativeInteger(target.end_ms)
      && Number(target.end_ms) >= Number(target.start_ms);
  }
  if (kind === "BBOX") {
    return exactKeys("page", "x", "y", "width", "height")
      && typeof target.page === "number" && Number.isSafeInteger(target.page) && target.page >= 1
      && [target.x, target.y, target.width, target.height].every((candidate) => (
        typeof candidate === "number" && Number.isFinite(candidate) && candidate >= 0
      ))
      && Number(target.width) > 0 && Number(target.height) > 0;
  }
  if (kind === "TABLE") {
    return exactKeys("table_id", "row", "column") && resourceId(target.table_id)
      && safeNonNegativeInteger(target.row) && safeNonNegativeInteger(target.column);
  }
  if (kind === "REQUIREMENT") {
    return exactKeys("requirement_id") && resourceId(target.requirement_id);
  }
  return exactKeys("conflict_id") && resourceId(target.conflict_id);
}

function exactTimestamp(value: unknown): value is string {
  if (typeof value !== "string" || !boundedOpaque(value)) return false;
  const matched = /^(\d{4})-(\d{2})-(\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.exec(value);
  if (!matched || !Number.isFinite(Date.parse(value))) return false;
  const year = Number(matched[1]);
  const month = Number(matched[2]);
  const day = Number(matched[3]);
  if (year < 1 || month < 1 || month > 12) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1];
}

function exactRequiredText(value: unknown, maximumBytes: number): value is string {
  return typeof value === "string"
    && value.length > 0
    && value === value.trim()
    && new TextEncoder().encode(value).byteLength <= maximumBytes;
}

function exactObjectFields(value: Record<string, unknown>, fields: Set<string>): boolean {
  return Object.keys(value).length === fields.size
    && Object.keys(value).every((key) => fields.has(key));
}

function exactReviewSourceRef(
  value: unknown,
  task: {
    assetId: string;
    targetKind: ReviewTargetKind;
    sourceDigest: string;
  },
): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const source = value as Record<string, unknown>;
  if (!exactObjectFields(source, reviewSourceRefFields)) return false;
  const digestFields = [
    "content_digest", "asset_sha256", "target_digest", "snapshot_digest",
    "head_value_digest", "source_digest", "provenance_digest",
    "original_value_client_digest",
  ];
  return source.schema_version === "human-review-source-ref-v2"
    && source.content_id === task.assetId
    && positiveInteger(source.content_version) !== undefined
    && source.target_kind === task.targetKind
    && typeof source.snapshot_id === "string"
    && boundedOpaque(source.snapshot_id)
    && positiveInteger(source.head_version) !== undefined
    && source.head_value_digest === task.sourceDigest
    && source.original_value_digest_contract === "sha256:rfc8785-ijson-safeint-v1"
    && digestFields.every((field) => (
      typeof source[field] === "string" && sha256ReferencePattern.test(source[field] as string)
    ));
}

function reviewSource(value: unknown): ReviewSource | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const candidate = value as Record<string, unknown>;
  const detail = candidate.schema_version === "human-review-source-detail-v1";
  if (!exactObjectFields(candidate, detail ? reviewSourceDetailFields : reviewSourceSummaryFields)) {
    return undefined;
  }
  if (!candidate.source_ref || typeof candidate.source_ref !== "object" || Array.isArray(candidate.source_ref)) {
    return undefined;
  }
  const sourceRef = candidate.source_ref as Record<string, unknown>;
  const targetKind = candidate.target_kind as ReviewTargetKind;
  const contentVersion = positiveInteger(candidate.content_version);
  const headVersion = positiveInteger(candidate.head_version);
  const headCorrectionVersion = typeof candidate.head_correction_version === "number"
    && Number.isSafeInteger(candidate.head_correction_version)
    && candidate.head_correction_version >= 0
    ? candidate.head_correction_version
    : undefined;
  const confidence = candidate.confidence;
  const headDirection = candidate.head_direction;
  if (
    typeof candidate.content_id !== "string"
    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(candidate.content_id)
    || contentVersion === undefined
    || typeof candidate.target_kind !== "string"
    || !reviewTargetKinds.has(targetKind)
    || !exactReviewTarget(targetKind, candidate.target)
    || typeof candidate.target_digest !== "string"
    || !sha256ReferencePattern.test(candidate.target_digest)
    || typeof confidence !== "number"
    || !Number.isFinite(confidence)
    || confidence < 0
    || confidence > 1
    || headVersion === undefined
    || !["SNAPSHOT", "APPLY", "REVERT"].includes(String(headDirection))
    || headCorrectionVersion === undefined
    || headDirection === "SNAPSHOT" && headCorrectionVersion !== 0
    || headDirection === "APPLY" && headCorrectionVersion < 1
    || typeof candidate.original_value_client_digest !== "string"
    || !sha256ReferencePattern.test(candidate.original_value_client_digest)
    || candidate.original_value_digest_contract !== "sha256:rfc8785-ijson-safeint-v1"
    || !exactReviewSourceRef(sourceRef, {
      assetId: candidate.content_id,
      targetKind,
      sourceDigest: String(sourceRef.head_value_digest),
    })
    || sourceRef.content_version !== contentVersion
    || sourceRef.target_digest !== candidate.target_digest
    || sourceRef.head_version !== headVersion
    || sourceRef.original_value_client_digest !== candidate.original_value_client_digest
  ) return undefined;
  return {
    schema_version: detail
      ? "human-review-source-detail-v1"
      : "human-review-source-summary-v1",
    content_id: candidate.content_id,
    content_version: contentVersion,
    target_kind: targetKind,
    target: candidate.target as Record<string, unknown>,
    target_digest: candidate.target_digest,
    confidence,
    head_version: headVersion,
    head_direction: headDirection as ReviewSource["head_direction"],
    head_correction_version: headCorrectionVersion,
    original_value_client_digest: candidate.original_value_client_digest,
    original_value_digest_contract: "sha256:rfc8785-ijson-safeint-v1",
    source_ref: sourceRef,
    ...(detail ? { original_value: candidate.original_value } : {}),
    detail_loaded: detail,
  };
}

function reviewSourceKey(source: ReviewSource): string {
  return `${source.target_kind}:${source.target_digest}:${source.head_version}`;
}

async function validatedReviewSource(
  value: unknown,
  expected: {
    contentId: string;
    contentVersion: number;
    priorSummary?: ReviewSource;
  },
): Promise<ReviewSource> {
  const source = reviewSource(value);
  if (
    !source
    || source.content_id !== expected.contentId
    || source.content_version !== expected.contentVersion
  ) throw new Error("HUMAN_REVIEW_SOURCE_RESPONSE_INVALID");
  if (expected.priorSummary) {
    const summaryProjection = (candidate: ReviewSource) => ({
      schema_version: "human-review-source-summary-v1",
      content_id: candidate.content_id,
      content_version: candidate.content_version,
      target_kind: candidate.target_kind,
      target: candidate.target,
      target_digest: candidate.target_digest,
      confidence: candidate.confidence,
      head_version: candidate.head_version,
      head_direction: candidate.head_direction,
      head_correction_version: candidate.head_correction_version,
      original_value_client_digest: candidate.original_value_client_digest,
      original_value_digest_contract: candidate.original_value_digest_contract,
      source_ref: candidate.source_ref,
    });
    if (
      !source.detail_loaded
      || canonicalStrictJson(summaryProjection(source))
        !== canonicalStrictJson(summaryProjection(expected.priorSummary))
    ) throw new Error("HUMAN_REVIEW_SOURCE_DETAIL_BINDING_INVALID");
  }
  if (source.detail_loaded) {
    const observed = `sha256:${await sha256(
      new TextEncoder().encode(canonicalStrictJson(source.original_value)).buffer,
    )}`;
    if (observed !== source.original_value_client_digest) {
      throw new Error("HUMAN_REVIEW_SOURCE_VALUE_DIGEST_INVALID");
    }
  }
  return source;
}

function reviewTask(
  value: unknown,
  expectedScope?: { tenantId: string; projectId: string } | null,
): ReviewTask | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const candidate = value as Record<string, unknown>;
  const summary = candidate.schema_version === "human-review-task-summary-v1";
  if (!exactObjectFields(candidate, summary ? reviewTaskSummaryFields : reviewTaskFullFields)) {
    return undefined;
  }
  if (!summary && (
    !expectedScope
    || candidate.tenant_id !== expectedScope.tenantId
    || candidate.project_id !== expectedScope.projectId
    || !boundedOpaque(candidate.created_by)
  )) return undefined;
  const resourceId = (resource: unknown) => (
    typeof resource === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(resource)
  );
  const version = positiveInteger(candidate.version);
  const correctionVersion = typeof candidate.current_correction_version === "number"
    && Number.isSafeInteger(candidate.current_correction_version)
    && candidate.current_correction_version >= 0
    ? candidate.current_correction_version
    : undefined;
  const effectiveVersion = typeof candidate.effective_version === "number"
    && Number.isSafeInteger(candidate.effective_version)
    && candidate.effective_version >= 0
    ? candidate.effective_version
    : undefined;
  const claimFence = typeof candidate.claim_fence === "number"
    && Number.isSafeInteger(candidate.claim_fence)
    && candidate.claim_fence >= 0
    ? candidate.claim_fence
    : undefined;
  const targetKind = candidate.target_kind as ReviewTargetKind;
  const state = candidate.state as string;
  if (
    !resourceId(candidate.task_id)
    || !resourceId(candidate.asset_id)
    || typeof candidate.target_kind !== "string"
    || !reviewTargetKinds.has(targetKind)
    || typeof candidate.source_digest !== "string"
    || !sha256ReferencePattern.test(candidate.source_digest)
    || typeof candidate.confidence !== "number"
    || !Number.isFinite(candidate.confidence)
    || candidate.confidence < 0
    || candidate.confidence > 1
    || !exactRequiredText(candidate.reason, 2_000)
    || typeof candidate.state !== "string"
    || !reviewTaskStates.has(state)
    || version === undefined
    || correctionVersion === undefined
    || effectiveVersion === undefined
    || claimFence === undefined
    || !exactTimestamp(candidate.created_at)
    || !exactTimestamp(candidate.updated_at)
  ) return undefined;
  const correctionDigest = candidate.current_correction_digest;
  const effectiveDigest = candidate.effective_digest;
  if (
    !(correctionDigest === null || (
      typeof correctionDigest === "string" && sha256ReferencePattern.test(correctionDigest)
    ))
    || (correctionVersion === 0) !== (correctionDigest === null)
    || !(effectiveDigest === null || (
      typeof effectiveDigest === "string" && sha256ReferencePattern.test(effectiveDigest)
    ))
    || effectiveVersion > 0 && effectiveDigest === null
  ) return undefined;
  const liveClaimState = state === "CLAIMED" || state === "EDITED";
  const claimActor = candidate.claim_actor_id;
  const claimExpiresAt = candidate.claim_expires_at;
  if (
    liveClaimState && (
      !boundedOpaque(claimActor) || !exactTimestamp(claimExpiresAt) || claimFence < 1
    )
    || !liveClaimState && (claimActor !== null || claimExpiresAt !== null)
  ) return undefined;
  const closedState = state === "APPROVED" || state === "REJECTED" || state === "REVERTED";
  if (
    closedState && !exactTimestamp(candidate.closed_at)
    || !closedState && candidate.closed_at !== null
  ) return undefined;
  if (!summary && (
    !exactReviewTarget(targetKind, candidate.target)
    || !exactReviewSourceRef(candidate.source_ref, {
      assetId: candidate.asset_id as string,
      targetKind,
      sourceDigest: candidate.source_digest,
    })
  )) return undefined;
  return {
    ...(!summary ? {
      tenant_id: candidate.tenant_id as string,
      project_id: candidate.project_id as string,
      created_by: candidate.created_by as string,
      target: candidate.target as Record<string, unknown>,
      original_value: candidate.original_value,
      source_ref: candidate.source_ref as Record<string, unknown>,
    } : {}),
    task_id: candidate.task_id as string,
    asset_id: candidate.asset_id as string,
    target_kind: targetKind,
    source_digest: candidate.source_digest,
    confidence: candidate.confidence,
    reason: candidate.reason,
    state,
    current_correction_version: correctionVersion,
    ...(typeof correctionDigest === "string" ? { current_correction_digest: correctionDigest } : {}),
    effective_version: effectiveVersion,
    ...(typeof effectiveDigest === "string" ? { effective_digest: effectiveDigest } : {}),
    ...(typeof claimActor === "string" ? { claim_actor_id: claimActor } : {}),
    claim_fence: claimFence,
    ...(typeof claimExpiresAt === "string" ? { claim_expires_at: claimExpiresAt } : {}),
    version,
    created_at: candidate.created_at,
    updated_at: candidate.updated_at,
    ...(typeof candidate.closed_at === "string" ? { closed_at: candidate.closed_at } : {}),
    detail_loaded: !summary,
  };
}

function exactCurrentReviewCorrection(
  value: unknown,
  task: ReviewTask,
): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const correction = value as Record<string, unknown>;
  return task.detail_loaded === true
    && task.current_correction_version > 0
    && typeof task.current_correction_digest === "string"
    && exactObjectFields(correction, reviewCorrectionFields)
    && boundedOpaque(correction.correction_id)
    && correction.tenant_id === task.tenant_id
    && correction.project_id === task.project_id
    && correction.task_id === task.task_id
    && correction.correction_version === task.current_correction_version
    && correction.parent_correction_version === task.current_correction_version - 1
    && correction.target_kind === task.target_kind
    && canonicalStrictJson(correction.target) === canonicalStrictJson(task.target)
    && typeof correction.source_digest === "string"
    && sha256ReferencePattern.test(correction.source_digest)
    && boundedOpaque(correction.actor_id)
    && exactRequiredText(correction.reason, 2_000)
    && exactTimestamp(correction.created_at)
    && correction.correction_digest === task.current_correction_digest;
}

function exactReviewCorrection(
  value: unknown,
  priorTask: ReviewTask,
  nextTask: ReviewTask,
  correctedValue: unknown,
  reason: string,
): value is Record<string, unknown> {
  if (!exactCurrentReviewCorrection(value, nextTask)) return false;
  const correction = value as Record<string, unknown>;
  const expectedSourceDigest = (priorTask.effective_version ?? 0) > 0
    ? priorTask.effective_digest
    : priorTask.source_digest;
  return correction.task_id === priorTask.task_id
    && correction.parent_correction_version === priorTask.current_correction_version
    && correction.correction_version === priorTask.current_correction_version + 1
    && correction.target_kind === priorTask.target_kind
    && canonicalStrictJson(correction.target) === canonicalStrictJson(priorTask.target)
    && (
      (priorTask.effective_version ?? 0) > 0
      || canonicalStrictJson(correction.original_value) === canonicalStrictJson(priorTask.original_value)
    )
    && canonicalStrictJson(correction.corrected_value) === canonicalStrictJson(correctedValue)
    && typeof expectedSourceDigest === "string"
    && correction.source_digest === expectedSourceDigest
    && correction.actor_id === priorTask.claim_actor_id
    && correction.reason === reason
    && correction.correction_digest === nextTask.current_correction_digest;
}

function exactReviewDecision(
  value: unknown,
  priorTask: ReviewTask,
  nextTask: ReviewTask,
  operation: "approve" | "reject" | "reopen" | "revert",
  reason: string,
  currentCorrection: Record<string, unknown> | undefined,
  trustedActorId?: string,
): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const decision = value as Record<string, unknown>;
  const expectedDecision = operation.toUpperCase();
  const expectedCorrectionVersion = priorTask.current_correction_version > 0
    ? priorTask.current_correction_version
    : null;
  const expectedCorrectionDigest = priorTask.current_correction_digest ?? null;
  const expectedActor = operation === "approve" || operation === "reject"
    ? priorTask.claim_actor_id
    : trustedActorId;
  return exactObjectFields(decision, reviewDecisionFields)
    && boundedOpaque(decision.decision_id)
    && decision.tenant_id === nextTask.tenant_id
    && decision.project_id === nextTask.project_id
    && decision.task_id === priorTask.task_id
    && decision.decision_version === nextTask.version
    && nextTask.version === priorTask.version + 1
    && decision.decision === expectedDecision
    && decision.prior_state === priorTask.state
    && decision.next_state === nextTask.state
    && decision.correction_version === expectedCorrectionVersion
    && decision.correction_digest === expectedCorrectionDigest
    && (
      expectedCorrectionVersion === null
        ? currentCorrection === undefined && decision.source_digest === priorTask.source_digest
        : currentCorrection !== undefined
          && exactCurrentReviewCorrection(currentCorrection, priorTask)
          && decision.source_digest === currentCorrection.source_digest
    )
    && boundedOpaque(decision.actor_id)
    && (expectedActor === undefined || decision.actor_id === expectedActor)
    && decision.reason === reason
    && exactTimestamp(decision.created_at)
    && (!(operation === "approve" || operation === "revert")
      || expectedCorrectionVersion !== null && expectedCorrectionDigest !== null);
}

function exactReviewEffective(
  value: unknown,
  task: ReviewTask,
  propagations: unknown,
): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const effective = value as Record<string, unknown>;
  if (
    !exactObjectFields(effective, reviewEffectiveFields)
    || typeof effective.materialized !== "boolean"
    || effective.effective_version !== task.effective_version
    || effective.effective_value_digest !== (task.effective_digest ?? null)
    || !Array.isArray(effective.channels)
  ) return false;
  if (!effective.materialized) {
    return effective.state === "NOT_RUN"
      && effective.effective_value === null
      && effective.effective_value_digest === null
      && effective.channels.length === 0;
  }
  if (
    effective.state !== "CURRENT"
    || typeof effective.effective_value_digest !== "string"
    || !sha256ReferencePattern.test(effective.effective_value_digest)
    || effective.channels.length !== reviewPropagationChannels.size
  ) return false;
  const channels = new Set<string>();
  const decisionIds = new Set<string>();
  const correctionVersions = new Set<number>();
  const directions = new Set<string>();
  for (const item of effective.channels) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const channel = item as Record<string, unknown>;
    if (
      !exactObjectFields(channel, reviewEffectiveChannelFields)
      || typeof channel.channel !== "string"
      || !reviewPropagationChannels.has(channel.channel)
      || channels.has(channel.channel)
      || !boundedOpaque(channel.source_decision_id)
      || positiveInteger(channel.correction_version) === undefined
      || !["APPLY", "REVERT"].includes(String(channel.direction))
      || channel.effective_value_digest !== effective.effective_value_digest
      || positiveInteger(channel.version) === undefined
      || !exactTimestamp(channel.updated_at)
    ) return false;
    channels.add(channel.channel);
    decisionIds.add(channel.source_decision_id as string);
    correctionVersions.add(channel.correction_version as number);
    directions.add(channel.direction as string);
  }
  if (
    channels.size !== reviewPropagationChannels.size
    || decisionIds.size !== 1
    || correctionVersions.size !== 1
    || directions.size !== 1
    || !Array.isArray(propagations)
  ) return false;
  const [decisionId] = decisionIds;
  const [correctionVersion] = correctionVersions;
  const [direction] = directions;
  const sourceBatch = propagations.filter((item) => (
    item && typeof item === "object" && !Array.isArray(item)
    && (item as Record<string, unknown>).decision_id === decisionId
  )) as Array<Record<string, unknown>>;
  const sourceChannels = new Set<string>();
  for (const propagation of sourceBatch) {
    if (
      propagation.task_id !== task.task_id
      || propagation.correction_version !== correctionVersion
      || propagation.direction !== direction
      || propagation.effective_value_digest !== effective.effective_value_digest
      || propagation.state !== "SUCCEEDED"
      || typeof propagation.channel !== "string"
      || !reviewPropagationChannels.has(propagation.channel)
      || sourceChannels.has(propagation.channel)
    ) return false;
    sourceChannels.add(propagation.channel);
  }
  return sourceBatch.length === reviewPropagationChannels.size
    && sourceChannels.size === reviewPropagationChannels.size;
}

function reviewTaskDynamicState(task: ReviewTask): Record<string, unknown> {
  return {
    state: task.state,
    current_correction_version: task.current_correction_version,
    current_correction_digest: task.current_correction_digest ?? null,
    effective_version: task.effective_version,
    effective_digest: task.effective_digest ?? null,
    claim_actor_id: task.claim_actor_id ?? null,
    claim_fence: task.claim_fence,
    claim_expires_at: task.claim_expires_at ?? null,
    updated_at: task.updated_at,
    closed_at: task.closed_at ?? null,
  };
}

function exactReviewCursor(
  value: string,
  expectedFilterDigest: string,
  lastTask: ReviewTask,
): boolean {
  if (!/^[A-Za-z0-9_-]{1,4096}$/.test(value)) return false;
  try {
    const standard = value.replaceAll("-", "+").replaceAll("_", "/");
    const padded = standard + "=".repeat((4 - standard.length % 4) % 4);
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const decoded = parseStrictJson(source, { maximumDepth: 4, maximumNodes: 16 });
    if (!decoded || typeof decoded !== "object" || Array.isArray(decoded)) return false;
    const cursor = decoded as Record<string, unknown>;
    const fields = new Set(["version", "filter_digest", "confidence", "created_at", "task_id"]);
    const canonical = bytesToBase64(
      new TextEncoder().encode(canonicalStrictJson(cursor)),
    ).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
    return exactObjectFields(cursor, fields)
      && canonical === value
      && cursor.version === "human-review-cursor-v1"
      && cursor.filter_digest === expectedFilterDigest
      && typeof cursor.confidence === "number"
      && Number.isFinite(cursor.confidence)
      && cursor.confidence === lastTask.confidence
      && cursor.created_at === lastTask.created_at
      && cursor.task_id === lastTask.task_id;
  } catch {
    return false;
  }
}

function exactReviewSourceCursor(
  value: string,
  expectedFilterDigest: string,
  expectedCollectionDigest: string | undefined,
  expectedCollectionGeneration: number | undefined,
  lastSource: ReviewSource,
): { collectionDigest: string; collectionGeneration: number } | undefined {
  if (!/^[A-Za-z0-9_-]{1,4096}$/.test(value)) return undefined;
  try {
    const standard = value.replaceAll("-", "+").replaceAll("_", "/");
    const padded = standard + "=".repeat((4 - standard.length % 4) % 4);
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const decoded = parseStrictJson(source, { maximumDepth: 4, maximumNodes: 16 });
    if (!decoded || typeof decoded !== "object" || Array.isArray(decoded)) return undefined;
    const cursor = decoded as Record<string, unknown>;
    const fields = new Set([
      "version", "filter_digest", "collection_digest", "collection_generation",
      "target_kind", "target_digest",
    ]);
    const canonical = bytesToBase64(
      new TextEncoder().encode(canonicalStrictJson(cursor)),
    ).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
    if (
      !exactObjectFields(cursor, fields)
      || canonical !== value
      || cursor.version !== "human-review-source-cursor-v1"
      || cursor.filter_digest !== expectedFilterDigest
      || typeof cursor.collection_digest !== "string"
      || !/^[0-9a-f]{64}$/.test(cursor.collection_digest)
      || positiveInteger(cursor.collection_generation) === undefined
      || expectedCollectionDigest !== undefined
        && cursor.collection_digest !== expectedCollectionDigest
      || expectedCollectionGeneration !== undefined
        && cursor.collection_generation !== expectedCollectionGeneration
      || cursor.target_kind !== lastSource.target_kind
      || cursor.target_digest !== lastSource.target_digest
    ) return undefined;
    return {
      collectionDigest: cursor.collection_digest,
      collectionGeneration: cursor.collection_generation as number,
    };
  } catch {
    return undefined;
  }
}

function strictSkillResponse(
  value: unknown,
  httpOk: boolean,
  expectedSkill: string,
  expectedOperation: string,
): SkillResponse {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("MULTIMODAL_RESPONSE_INVALID");
  }
  const response = value as SkillResponse;
  const allowed = new Set([
    "schema_version", "skill", "operation", "status", "code", "retryable",
    "trace_id", "request_digest", "implementation_state", "external_evidence",
    "certification", "output", "result_digest",
  ]);
  if (Object.keys(response).some((key) => !allowed.has(key))) {
    throw new Error("MULTIMODAL_RESPONSE_FIELDS_INVALID");
  }
  const status = response.status;
  if (typeof status !== "string" || ![
    "SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL",
  ].includes(status.toUpperCase())) {
    throw new Error("MULTIMODAL_RESPONSE_STATUS_INVALID");
  }
  if (response.retryable !== undefined && typeof response.retryable !== "boolean") {
    throw new Error("MULTIMODAL_RESPONSE_RETRYABLE_INVALID");
  }
  for (const key of ["code", "trace_id"] as const) {
    if (response[key] !== undefined && !boundedOpaque(response[key])) {
      throw new Error("MULTIMODAL_RESPONSE_FIELD_INVALID");
    }
  }
  if (httpOk && (!response.output || typeof response.output !== "object" || Array.isArray(response.output))) {
    throw new Error("MULTIMODAL_RESPONSE_OUTPUT_INVALID");
  }
  if (!httpOk) {
    const errorFields = new Set([
      "schema_version", "status", "code", "retryable", "trace_id",
      "external_evidence", "certification", "result_digest",
    ]);
    if (
      Object.keys(response).length !== errorFields.size
      || Object.keys(response).some((key) => !errorFields.has(key))
      || response.schema_version !== "1.0.0"
      || !["BLOCKED", "FAILED"].includes(String(response.status))
      || typeof response.code !== "string"
      || !/^[A-Z][A-Z0-9_:-]{0,127}$/.test(response.code)
      || typeof response.retryable !== "boolean"
      || !boundedOpaque(response.trace_id)
      || response.external_evidence !== "NOT_RUN"
      || response.certification !== "NOT_CERTIFIED"
      || typeof response.result_digest !== "string"
      || !/^[0-9a-f]{64}$/.test(response.result_digest)
    ) {
      throw new Error("MULTIMODAL_ERROR_RESPONSE_INVALID");
    }
    return response;
  }
  const fullFields = new Set([
    "schema_version", "skill", "operation", "status", "retryable", "trace_id",
    "request_digest", "implementation_state", "external_evidence", "certification",
    "output", "result_digest",
  ]);
  if (response.code !== undefined) fullFields.add("code");
  if (
    Object.keys(response).length !== fullFields.size
    || Object.keys(response).some((key) => !fullFields.has(key))
    || response.schema_version !== "1.0.0"
    || response.skill !== expectedSkill
    || response.operation !== expectedOperation
    || !["SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL"]
      .includes(String(response.status))
    || typeof response.retryable !== "boolean"
    || !boundedOpaque(response.trace_id)
    || typeof response.request_digest !== "string"
    || !/^[0-9a-f]{64}$/.test(response.request_digest)
    || !["CODE_IMPLEMENTED_LOCAL", "BRIDGE_REQUIRED"].includes(String(response.implementation_state))
    || response.external_evidence !== "NOT_RUN"
    || response.certification !== "NOT_CERTIFIED"
    || typeof response.result_digest !== "string"
    || !/^[0-9a-f]{64}$/.test(response.result_digest)
    || (response.code !== undefined && (
      typeof response.code !== "string" || !/^[A-Z][A-Z0-9_:-]{0,127}$/.test(response.code)
    ))
    || (["BLOCKED", "FAILED"].includes(String(response.status)) && response.code === undefined)
  ) {
    throw new Error("MULTIMODAL_RESPONSE_ENVELOPE_INVALID");
  }
  return response;
}

async function readSkillResponse(
  response: Response,
  expectedSkill: string,
  expectedOperation: string,
): Promise<SkillResponse> {
  const mediaType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "application/json") throw new Error("MULTIMODAL_RESPONSE_MEDIA_TYPE_INVALID");
  const declared = response.headers.get("content-length");
  const contentEncoding = response.headers.get("content-encoding")?.trim().toLowerCase();
  if (declared && (!/^[0-9]{1,10}$/.test(declared) || Number(declared) > maximumSkillResponseBytes)) {
    throw new Error("MULTIMODAL_RESPONSE_TOO_LARGE");
  }
  if (!response.body) throw new Error("MULTIMODAL_RESPONSE_INVALID");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let observed = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      observed += value.byteLength;
      if (observed > maximumSkillResponseBytes) {
        try {
          await reader.cancel("MULTIMODAL_RESPONSE_TOO_LARGE");
        } catch {
          // The size violation remains authoritative if the peer closed first.
        }
        throw new Error("MULTIMODAL_RESPONSE_TOO_LARGE");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  if (declared && (!contentEncoding || contentEncoding === "identity") && observed !== Number(declared)) {
    throw new Error("MULTIMODAL_RESPONSE_SIZE_INVALID");
  }
  const bytes = new Uint8Array(observed);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  let source: string;
  try {
    source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("MULTIMODAL_RESPONSE_JSON_INVALID");
  }
  try {
    const payload = strictSkillResponse(
      parseStrictJson(source, { maximumDepth: 32, maximumNodes: 250_000 }),
      response.ok,
      expectedSkill,
      expectedOperation,
    );
    const unsigned: SkillResponse = { ...payload };
    delete unsigned.result_digest;
    const expectedDigest = await sha256(
      new TextEncoder().encode(canonicalStrictJson(unsigned)).buffer,
    );
    if (payload.result_digest !== expectedDigest) {
      throw new Error("MULTIMODAL_RESPONSE_DIGEST_INVALID");
    }
    return payload;
  } catch (error) {
    if (error instanceof StrictJsonError) {
      throw new Error(`MULTIMODAL_RESPONSE_${error.code}`);
    }
    throw error;
  }
}

async function executeSkill(
  projectId: string,
  skill: string,
  operation: string,
  input: Record<string, unknown>,
  idempotencyKey: string,
): Promise<SkillResponse> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort("MULTIMODAL_REQUEST_TIMEOUT"), skillRequestTimeoutMs);
  try {
    const unsigned = {
      schema_version: browserRequestSchemaVersion,
      skill,
      operation,
      projectId,
      input,
    };
    const requestDigest = await sha256(
      new TextEncoder().encode(canonicalStrictJson(unsigned)).buffer,
    );
    const response = await fetch(webBffRoute, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: canonicalStrictJson({ ...unsigned, request_digest: requestDigest }),
      signal: controller.signal,
    });
    const payload = await readSkillResponse(response, skill, operation);
    if (!response.ok) {
      const error = new Error(responseString(payload, "code", "error_code") ?? "MULTIMODAL_REQUEST_FAILED");
      Object.assign(error, { payload });
      throw error;
    }
    const state = String(payload.status ?? payload.state ?? "").toUpperCase();
    if (["BLOCKED", "FAILED"].includes(state)) {
      const error = new Error(responseString(payload, "code", "error_code") ?? "MULTIMODAL_OPERATION_BLOCKED");
      Object.assign(error, { payload });
      throw error;
    }
    return payload;
  } catch (error) {
    if (controller.signal.aborted) throw new Error("MULTIMODAL_REQUEST_TIMEOUT");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

function phaseFrom(response: SkillResponse): AssetPhase {
  const status = (response.status ?? response.state ?? responseString(
    response,
    "status",
    "state",
    "asset_status",
    "result_status",
    "job_status",
  ) ?? "").toUpperCase();
  if (["READY", "SUCCEEDED", "PASSED", "COMPLETED", "CODE_IMPLEMENTED_LOCAL"].includes(status)) return "READY";
  if (["PROCESSING", "RUNNING", "PENDING", "QUEUED", "RETRYING"].includes(status)) return "PROCESSING";
  if (["PARTIAL", "PARTIAL_READY", "PARTIALLY_READY", "NEEDS_REVIEW", "NOT_RUN", "NOT_RUN_EXTERNAL"].includes(status)) return "NEEDS_REVIEW";
  if (status.includes("QUARANTIN")) return "QUARANTINED";
  return "BLOCKED";
}

function failureDetails(error: unknown, fallback: string) {
  const payload = (error as Error & { payload?: SkillResponse })?.payload;
  const code = payload
    ? responseString(payload, "code", "error_code") ?? fallback
    : error instanceof Error
      ? error.message
      : fallback;
  const status = `${payload?.status ?? ""} ${payload?.state ?? ""} ${code}`.toUpperCase();
  return {
    payload,
    code,
    quarantined: status.includes("QUARANTIN"),
    retryable: payload?.retryable,
    traceId: payload ? responseString(payload, "trace_id") : undefined,
  };
}

export function MultimodalIntakeWorkbench() {
  const account = useAccountSession();
  const [projectId, setProjectId] = useState("default-project");
  const [directText, setDirectText] = useState("");
  const [assets, setAssets] = useState<AssetDraft[]>([]);
  const activeProgressJobKey = useMemo(() => JSON.stringify([...new Set(
    assets
      .filter((asset) => asset.processingJobId && ![
        "READY", "NEEDS_REVIEW", "QUARANTINED", "BLOCKED",
      ].includes(asset.phase))
      .map((asset) => asset.processingJobId as string),
  )].sort()), [assets]);
  const [recoveryRecordCount, setRecoveryRecordCount] = useState(0);
  const [legacyRecoveryCount, setLegacyRecoveryCount] = useState(0);
  const [recoveryStoreReady, setRecoveryStoreReady] = useState(false);
  const [recoveryStoreError, setRecoveryStoreError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [treeQuery, setTreeQuery] = useState("");
  const [packagePreview, setPackagePreview] = useState<SkillResponse | null>(null);
  const [packagePage, setPackagePage] = useState<ProjectPackagePage | null>(null);
  const [packagePageCursors, setPackagePageCursors] = useState<Array<string | null>>([null]);
  const [packagePageIndex, setPackagePageIndex] = useState(0);
  const [estimate, setEstimate] = useState<ProcessingEstimate | null>(null);
  const [estimateBusy, setEstimateBusy] = useState(false);
  const [correction, setCorrection] = useState("");
  const [correctionTouched, setCorrectionTouched] = useState(false);
  const [correctionTarget, setCorrectionTarget] = useState("");
  const [reviewTasks, setReviewTasks] = useState<ReviewTask[]>([]);
  const [reviewSources, setReviewSources] = useState<ReviewSource[]>([]);
  const [selectedReviewSourceKey, setSelectedReviewSourceKey] = useState("");
  const [selectedReviewTaskId, setSelectedReviewTaskId] = useState("");
  const [reviewTargetKind, setReviewTargetKind] = useState<ReviewTargetKind>("TEXT");
  const [reviewTargetLocator, setReviewTargetLocator] = useState("");
  const [reviewOriginalValue, setReviewOriginalValue] = useState("");
  const [reviewConfidence, setReviewConfidence] = useState("0.5");
  const [reviewReason, setReviewReason] = useState("USER_REVIEW");
  const [reviewPropagation, setReviewPropagation] = useState<SkillResponse | null>(null);
  const [reviewCurrentCorrection, setReviewCurrentCorrection] = useState<Record<string, unknown> | null>(null);
  const microphone = useMicrophoneRecorder((file) => { void addFiles([file]); });
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const fileAdditionLock = useRef(false);
  const fileAdditionOwner = useRef(0);
  const selectionCapacity = useRef({ count: 0, bytes: 0 });
  const recoveryByScope = useRef(new Map<string, UploadRecoveryRecord>());
  const recoveryLoad = useRef<Promise<boolean> | null>(null);
  const [reviewClaims, setReviewClaims] = useState<Record<string, ReviewClaim>>({});
  const [reviewIdentityScope, setReviewIdentityScope] = useState("");
  const [legacyReviewClaimDiscarded, setLegacyReviewClaimDiscarded] = useState(false);
  const [reviewEnqueueRecoveryCount, setReviewEnqueueRecoveryCount] = useState(0);
  const [reviewEnqueueRecoveryError, setReviewEnqueueRecoveryError] = useState("");
  const [reviewClock, setReviewClock] = useState(0);
  const reviewScopeGeneration = useRef(0);
  const reviewRequestOwner = useRef(0);
  const reviewEngineScope = useRef<{ tenantId: string; projectId: string } | null>(null);
  const recoveryIdentityGeneration = useRef(0);
  const activeIdentityScope = useRef("");
  const intakeBusyOwner = useRef(0);
  const estimateRequestOwner = useRef(0);
  const intakeProjectGeneration = useRef(0);
  const activeProjectId = useRef(projectId);

  const updateReviewEnqueueRecoveryState = useCallback((
    identityScope: string,
    scopedProjectId: string,
  ): Promise<Record<string, ReviewEnqueueAttempt> | undefined> => {
    return reviewProjectScopeDigest(identityScope, scopedProjectId).then((projectScopeDigest) => {
    try {
      const attempts = loadReviewEnqueueAttempts(identityScope);
      setReviewEnqueueRecoveryCount(Object.values(attempts).filter(
        (attempt) => attempt.project_scope_digest === projectScopeDigest,
      ).length);
      setReviewEnqueueRecoveryError("");
      return attempts;
    } catch (error) {
      setReviewEnqueueRecoveryCount(0);
      setReviewEnqueueRecoveryError(
        error instanceof Error
          ? error.message
          : "HUMAN_REVIEW_ENQUEUE_RECOVERY_CORRUPT",
      );
      return undefined;
    }
    }).catch((error) => {
      setReviewEnqueueRecoveryCount(0);
      setReviewEnqueueRecoveryError(
        error instanceof Error
          ? error.message
          : "HUMAN_REVIEW_ENQUEUE_RECOVERY_SCOPE_INVALID",
      );
      return undefined;
    });
  }, []);

  useLayoutEffect(() => {
    microphone.cancel();
    recoveryIdentityGeneration.current += 1;
    intakeBusyOwner.current += 1;
    estimateRequestOwner.current += 1;
    activeIdentityScope.current = "";
    recoveryLoad.current = null;
    recoveryByScope.current = new Map();
    selectionCapacity.current = { count: 0, bytes: 0 };
    fileAdditionOwner.current += 1;
    fileAdditionLock.current = false;
    setRecoveryRecordCount(0);
    setLegacyRecoveryCount(0);
    setRecoveryStoreReady(false);
    setRecoveryStoreError("");
    setBusy(false);
    setAssets([]);
    setDirectText("");
    setCorrection("");
    setCorrectionTouched(false);
    setCorrectionTarget("");
    setReviewReason("USER_REVIEW");
    setReviewConfidence("0.5");
    setReviewTargetKind("TEXT");
    setReviewSources([]);
    setSelectedReviewSourceKey("");
    setLegacyReviewClaimDiscarded(false);
    setReviewEnqueueRecoveryCount(0);
    setReviewEnqueueRecoveryError("");
    setReviewCurrentCorrection(null);
    setPackagePreview(null);
    setPackagePage(null);
    setPackagePageCursors([null]);
    setPackagePageIndex(0);
    setEstimate(null);
    setEstimateBusy(false);
    setTreeQuery("");
    if (fileInput.current) fileInput.current.value = "";
    if (folderInput.current) folderInput.current.value = "";
  }, [
    account.principal?.actorId,
    account.principal?.organizationId,
    account.status,
    microphone.cancel,
  ]);

  useLayoutEffect(() => {
    activeIdentityScope.current = reviewIdentityScope;
  }, [reviewIdentityScope]);

  useLayoutEffect(() => {
    microphone.cancel();
    if (activeProjectId.current !== projectId) {
      activeProjectId.current = projectId;
      intakeProjectGeneration.current += 1;
      estimateRequestOwner.current += 1;
      setPackagePreview(null);
      setPackagePage(null);
      setPackagePageCursors([null]);
      setPackagePageIndex(0);
      setEstimate(null);
      setEstimateBusy(false);
    }
  }, [microphone.cancel, projectId]);

  useLayoutEffect(() => {
    reviewScopeGeneration.current += 1;
    reviewRequestOwner.current += 1;
    reviewEngineScope.current = null;
    setReviewBusy(false);
    setReviewTasks([]);
    setReviewSources([]);
    setSelectedReviewSourceKey("");
    setSelectedReviewTaskId("");
    setReviewPropagation(null);
    setReviewCurrentCorrection(null);
    setReviewOriginalValue("");
    setReviewTargetLocator("");
    setFeedback("");
  }, [
    account.principal?.actorId,
    account.principal?.organizationId,
    account.status,
    projectId,
    reviewIdentityScope,
  ]);

  useEffect(() => {
    let active = true;
    setReviewIdentityScope("");
    setReviewClaims({});
    if (account.status === "loading") return () => { active = false; };
    if (account.status === "anonymous") {
      try {
        const scopedKeys: string[] = [];
        for (let index = 0; index < sessionStorage.length; index += 1) {
          const key = sessionStorage.key(index);
          if (key && (
            key === legacyReviewClaimStorageKey
            || key.startsWith(`${reviewClaimStoragePrefix}:`)
            || key.startsWith(`${legacyReviewEnqueueStoragePrefix}:`)
          )) scopedKeys.push(key);
        }
        for (const key of scopedKeys) sessionStorage.removeItem(key);
      } catch {
        // Server-side actor binding remains authoritative when local cleanup fails.
      }
      // V2 enqueue recovery records contain only opaque handles, scoped
      // digests, and idempotency keys. Preserve those records so the same actor
      // can reconcile an UNKNOWN result after signing in again. Legacy V1
      // records contained the exact correction input and are removed above.
      return () => { active = false; };
    }
    const identity = account.status === "authenticated" && account.principal
      ? {
          schema_version: "multimodal-review-browser-scope-v1",
          organization_id: account.principal.organizationId,
          actor_id: account.principal.actorId,
        }
      : {
          schema_version: "multimodal-review-browser-scope-v1",
          local_runner: true,
        };
    void sha256(new TextEncoder().encode(canonicalStrictJson(identity)).buffer).then((digest) => {
      if (active) setReviewIdentityScope(`sha256:${digest}`);
    });
    return () => { active = false; };
  }, [
    account.principal?.actorId,
    account.principal?.organizationId,
    account.status,
  ]);

  useEffect(() => {
    if (!reviewIdentityScope) return;
    try {
      const legacy = sessionStorage.getItem(legacyReviewClaimStorageKey);
      setLegacyReviewClaimDiscarded(legacy !== null);
      if (legacy !== null) sessionStorage.removeItem(legacyReviewClaimStorageKey);
      const rawEnqueueKeys: string[] = [];
      for (let index = 0; index < sessionStorage.length; index += 1) {
        const key = sessionStorage.key(index);
        if (key?.startsWith(`${legacyReviewEnqueueStoragePrefix}:`)) {
          rawEnqueueKeys.push(key);
        }
      }
      for (const key of rawEnqueueKeys) sessionStorage.removeItem(key);
    } catch {
      setLegacyReviewClaimDiscarded(false);
    }
    setReviewClaims(loadReviewClaims(reviewIdentityScope));
    void updateReviewEnqueueRecoveryState(reviewIdentityScope, projectId);
  }, [projectId, reviewIdentityScope, updateReviewEnqueueRecoveryState]);

  useEffect(() => {
    const now = Date.now();
    const boundaries = [
      ...Object.values(reviewClaims).map((claim) => (
        claim.fence === undefined
          ? claim.created_at + pendingReviewClaimRecoveryMs
          : Date.parse(claim.expires_at as string)
      )),
      ...reviewTasks.flatMap((task) => (
        task.claim_expires_at ? [Date.parse(task.claim_expires_at)] : []
      )),
    ].filter((value) => Number.isFinite(value) && value > now);
    if (boundaries.length === 0) return undefined;
    const delay = Math.min(Math.min(...boundaries) - now + 25, 2_147_000_000);
    const timer = window.setTimeout(() => {
      setReviewClock((current) => current + 1);
      if (!reviewIdentityScope) return;
      const retained = Object.fromEntries(Object.entries(reviewClaims).filter(([, claim]) => (
        validReviewClaim(claim, reviewIdentityScope)
      ))) as Record<string, ReviewClaim>;
      if (
        Object.keys(retained).length !== Object.keys(reviewClaims).length
        && persistReviewClaims(retained, reviewIdentityScope)
      ) {
        setReviewClaims(retained);
      }
    }, delay);
    return () => window.clearTimeout(timer);
  }, [reviewClaims, reviewClock, reviewIdentityScope, reviewTasks]);

  type IntakeIdentityGuard = {
    generation: number;
    identityScope: string;
    projectGeneration: number;
    projectId: string;
  };

  function captureIntakeIdentity(): IntakeIdentityGuard {
    const identityScope = activeIdentityScope.current;
    if (!identityScope) throw new Error("MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
    return {
      generation: recoveryIdentityGeneration.current,
      identityScope,
      projectGeneration: intakeProjectGeneration.current,
      projectId: activeProjectId.current,
    };
  }

  function intakeIdentityIsCurrent(guard: IntakeIdentityGuard): boolean {
    return guard.generation === recoveryIdentityGeneration.current
      && guard.identityScope === activeIdentityScope.current
      && guard.projectGeneration === intakeProjectGeneration.current
      && guard.projectId === activeProjectId.current;
  }

  function assertIntakeIdentityCurrent(guard: IntakeIdentityGuard): void {
    if (!intakeIdentityIsCurrent(guard)) throw new Error("MULTIMODAL_IDENTITY_SCOPE_CHANGED");
  }

  async function executeGuardedIntakeSkill(
    guard: IntakeIdentityGuard,
    projectAlias: string,
    skill: string,
    operation: string,
    input: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<SkillResponse> {
    assertIntakeIdentityCurrent(guard);
    if (projectAlias !== guard.projectId) throw new Error("MULTIMODAL_PROJECT_SCOPE_CHANGED");
    const response = await executeSkill(projectAlias, skill, operation, input, idempotencyKey);
    assertIntakeIdentityCurrent(guard);
    return response;
  }

  const ensureRecoveryStore = useCallback(async (): Promise<boolean> => {
    if (!reviewIdentityScope) return false;
    if (recoveryLoad.current) return recoveryLoad.current;
    const identityScope = reviewIdentityScope;
    const identityGeneration = recoveryIdentityGeneration.current;
    recoveryLoad.current = (async () => {
      try {
        const rawRecords = await readRecoveryValues();
        const valid = rawRecords.filter(validRecoveryRecord);
        const invalidCount = rawRecords.length - valid.length;
        if (invalidCount > 0) await replaceRecoveryValues(valid);
        if (identityGeneration !== recoveryIdentityGeneration.current) return false;
        const scoped = valid.filter((record) => record.identityScope === identityScope);
        recoveryByScope.current = new Map(
          scoped.map((record) => [recoveryStorageKey(record), record]),
        );
        setRecoveryRecordCount(scoped.length);
        setLegacyRecoveryCount(rawRecords.filter((record) => (
          record && typeof record === "object" && !Array.isArray(record)
          && (record as Record<string, unknown>).identityScope === identityScope
          && !validRecoveryRecord(record)
        )).length);
        setRecoveryStoreReady(true);
        setRecoveryStoreError("");
        return true;
      } catch (error) {
        if (identityGeneration !== recoveryIdentityGeneration.current) return false;
        const code = error instanceof Error ? error.message : "RECOVERY_STORE_UNAVAILABLE";
        setRecoveryStoreError(code);
        setRecoveryStoreReady(false);
        return false;
      }
    })();
    return recoveryLoad.current;
  }, [reviewIdentityScope]);

  useEffect(() => {
    if (reviewIdentityScope) void ensureRecoveryStore();
  }, [ensureRecoveryStore, reviewIdentityScope]);

  useEffect(() => {
    if (typeof EventSource === "undefined" || !safeProject(projectId)) return undefined;
    const jobIds = parseStrictJson(activeProgressJobKey, {
      maximumDepth: 2,
      maximumNodes: maximumBatchAssets + 1,
    });
    if (!Array.isArray(jobIds) || jobIds.length === 0) return undefined;
    let active = true;
    const streams: EventSource[] = [];
    for (const value of jobIds) {
      if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) {
        continue;
      }
      const jobId = value;
      const stream = new EventSource(
        `/api/multimodal-intake/v1/progress/jobs/${encodeURIComponent(jobId)}`
        + `?projectId=${encodeURIComponent(projectId)}`,
        { withCredentials: true },
      );
      let streamClosed = false;
      const closeStream = () => {
        if (streamClosed) return;
        streamClosed = true;
        stream.close();
      };
      streams.push(stream);
      stream.addEventListener("progress", (rawEvent) => {
        const event = rawEvent as MessageEvent<string>;
        void validatedJobProgressEvent(event.data, jobId, event.lastEventId).then((progress) => {
          if (!active) return;
          const state = progress.state as string;
          const phase: AssetPhase = state === "COMPLETED"
            ? "READY"
            : ["PARTIAL", "NEEDS_REVIEW"].includes(state)
              ? "NEEDS_REVIEW"
              : ["FAILED", "BLOCKED", "CANCELLED"].includes(state)
                ? "BLOCKED"
                : "PROCESSING";
          const terminal = ["READY", "NEEDS_REVIEW", "BLOCKED"].includes(phase);
          setAssets((current) => current.map((asset) => (
            asset.processingJobId === jobId
              ? {
                  ...asset,
                  phase,
                  progress: terminal ? 100 : Math.max(asset.progress, 80),
                  ...(terminal ? { processingJobId: undefined } : {}),
                }
              : asset
          )));
          if (terminal) closeStream();
        }).catch(() => {
          closeStream();
          if (!active) return;
          setAssets((current) => current.map((asset) => (
            asset.processingJobId === jobId
              ? { ...asset, code: "MULTIMODAL_PROGRESS_EVENT_INVALID" }
              : asset
          )));
        });
      });
      stream.addEventListener("error", () => {
        // The BFF response is deliberately one bounded batch. Never let native
        // EventSource turn a close or transport failure into an unbounded retry
        // loop; the existing tenant-bound get_session poll is the sole fallback.
        closeStream();
        if (!active) return;
        setAssets((current) => current.map((asset) => (
          asset.processingJobId === jobId
            ? { ...asset, code: "MULTIMODAL_PROGRESS_STREAM_UNAVAILABLE_POLLING" }
            : asset
        )));
      });
    }
    return () => {
      active = false;
      for (const stream of streams) stream.close();
    };
  }, [activeProgressJobKey, projectId]);

  useEffect(() => {
    let identityGuard: IntakeIdentityGuard;
    try {
      identityGuard = captureIntakeIdentity();
    } catch {
      return undefined;
    }
    const sessions = [...new Set(
      assets
        .filter((asset) => asset.sessionId && !["READY", "QUARANTINED"].includes(asset.phase) && !asset.permanentBlock)
        .map((asset) => asset.sessionId as string),
    )];
    if (busy || !safeProject(projectId) || sessions.length === 0) return undefined;
    let active = true;
    const poll = async () => {
      for (const sessionId of sessions) {
        try {
          const response = await executeGuardedIntakeSkill(
            identityGuard,
            projectId,
            "elmos-multimodal-input-orchestrator",
            "get_session",
            { session_id: sessionId },
            `mmi-progress-${sessionId}-${Math.floor(Date.now() / 5_000)}`,
          );
          const observed = nestedRecord(response).assets;
          if (!active || !intakeIdentityIsCurrent(identityGuard) || !Array.isArray(observed)) continue;
          const byId = new Map(observed
            .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item) && typeof (item as Record<string, unknown>).asset_id === "string")
            .map((item) => [String(item.asset_id), {
              status: String(item.status ?? "PROCESSING").toUpperCase(),
              version: positiveInteger(item.version),
            }]));
          setAssets((current) => {
            let changed = false;
            const next = current.map((asset) => {
              const observedAsset = asset.assetId ? byId.get(asset.assetId) : undefined;
              if (!observedAsset) return asset;
              // Corrections create a new immutable asset version. A lagging
              // session snapshot must never regress that newer local state.
              if (
                asset.assetVersion
                && (!observedAsset.version || observedAsset.version < asset.assetVersion)
              ) return asset;
              const state = observedAsset.status;
              const phase: AssetPhase = state === "READY" || state === "COMPLETED"
                ? "READY"
                : state === "NEEDS_REVIEW" || state === "PARTIAL"
                  ? "NEEDS_REVIEW"
                  : state === "QUARANTINED"
                    ? "QUARANTINED"
                    : state === "FAILED" || state === "BLOCKED"
                      ? "BLOCKED"
                      : "PROCESSING";
              const progress = ["READY", "NEEDS_REVIEW", "QUARANTINED", "BLOCKED"].includes(phase)
                ? 100
                : Math.max(asset.progress, 80);
              if (
                phase === asset.phase
                && progress === asset.progress
                && (!observedAsset.version || observedAsset.version === asset.assetVersion)
              ) return asset;
              changed = true;
              return {
                ...asset,
                phase,
                progress,
                ...(observedAsset.version ? { assetVersion: observedAsset.version } : {}),
              };
            });
            return changed ? next : current;
          });
        } catch {
          // Recovery metadata remains authoritative for the next bounded poll.
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 5_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [
    account.principal?.actorId,
    account.principal?.organizationId,
    account.status,
    assets,
    busy,
    projectId,
    reviewIdentityScope,
  ]);

  function publishRecoveryRecords() {
    setRecoveryRecordCount(recoveryByScope.current.size);
  }

  function recoveryRecords(
    projectAlias: string,
    fileFingerprint: string,
    engineProjectId?: string,
  ): UploadRecoveryRecord[] {
    return [...recoveryByScope.current.values()].filter((record) =>
      record.projectId === projectAlias
      && record.fileFingerprint === fileFingerprint
      && (engineProjectId === undefined || record.engineProjectId === engineProjectId));
  }

  async function persistRecovery(
    record: UploadRecoveryRecord,
    guard: IntakeIdentityGuard,
  ): Promise<void> {
    assertIntakeIdentityCurrent(guard);
    if (
      !validRecoveryRecord(record)
      || record.identityScope !== guard.identityScope
    ) throw new Error("RECOVERY_METADATA_INVALID");
    await putRecoveryValue(record);
    assertIntakeIdentityCurrent(guard);
    recoveryByScope.current.set(recoveryStorageKey(record), record);
    publishRecoveryRecords();
  }

  async function clearRecovery(
    record: { projectId?: string; engineProjectId?: string; fileFingerprint: string },
    guard: IntakeIdentityGuard,
  ): Promise<void> {
    assertIntakeIdentityCurrent(guard);
    if (!record.projectId || !record.engineProjectId) {
      throw new Error("RECOVERY_SCOPE_BINDING_MISSING");
    }
    const identity = {
      identityScope: guard.identityScope,
      projectId: record.projectId,
      engineProjectId: record.engineProjectId,
      fileFingerprint: record.fileFingerprint,
    };
    await deleteRecoveryValue(identity);
    assertIntakeIdentityCurrent(guard);
    recoveryByScope.current.delete(recoveryStorageKey(identity));
    publishRecoveryRecords();
  }

  function recoveryFromAsset(
    asset: AssetDraft,
    guard: IntakeIdentityGuard,
  ): UploadRecoveryRecord {
    assertIntakeIdentityCurrent(guard);
    if (
      !asset.projectId
      || !asset.engineProjectId
      || !asset.sessionAttemptKey
    ) {
      throw new Error("RECOVERY_SCOPE_OR_SESSION_BINDING_MISSING");
    }
    return {
      schemaVersion: 2,
      identityScope: guard.identityScope,
      fileFingerprint: asset.fileFingerprint,
      expectedSize: asset.file.size,
      lastModified: asset.file.lastModified,
      partSize: chunkBytes,
      attemptKey: asset.attemptKey,
      projectId: asset.projectId,
      engineProjectId: asset.engineProjectId,
      sessionAttemptKey: asset.sessionAttemptKey,
      ...(asset.sha256 ? { contentSha256: asset.sha256 } : {}),
      ...(asset.sessionId ? { sessionId: asset.sessionId } : {}),
      ...(asset.uploadSessionId ? { uploadSessionId: asset.uploadSessionId } : {}),
      confirmedPartCount: asset.confirmedPartCount,
      processingAttempt: asset.processingAttempt,
      ...(asset.assetId ? { assetId: asset.assetId } : {}),
      ...(asset.assetVersion ? { assetVersion: asset.assetVersion } : {}),
      role: asset.role,
      modelReadAllowed: asset.modelReadAllowed,
      updatedAt: Date.now(),
    };
  }

  const summary = useMemo(() => ({
    total: assets.length,
    uploaded: assets.filter((asset) => asset.uploadSessionId).length,
    ready: assets.filter((asset) => asset.phase === "READY").length,
    review: assets.filter((asset) => asset.phase === "NEEDS_REVIEW").length,
    blocked: assets.filter((asset) => ["BLOCKED", "QUARANTINED"].includes(asset.phase)).length,
    bytes: assets.reduce((total, asset) => total + asset.file.size, 0),
  }), [assets]);
  const estimatePlan = useMemo(() => {
    const eligible = assets.filter((asset) => (
      !asset.permanentBlock && asset.role !== "IGNORE" && asset.modelReadAllowed
    ));
    return {
      currency: "USD",
      stages: eligible.map((asset, index) => {
        const declaredUpperBound = Math.max(5, Math.ceil(asset.file.size / (1024 * 1024)) * 30);
        const progress = Math.min(1, Math.max(0, asset.progress / 100));
        return {
          stage_id: `asset-${index + 1}`,
          stage: "multimodal-intake",
          provider: "local",
          file_type: estimateFileType(asset.file),
          progress,
          elapsed_machine_seconds: Number((declaredUpperBound * 0.6 * progress).toFixed(6)),
          declared_upper_bound_seconds: declaredUpperBound,
          quantity: "0",
          unit: "none",
          depends_on: [],
        };
      }),
      history: [],
      prices: [],
    };
  }, [assets]);
  const estimatePlanDocument = useMemo(
    () => canonicalStrictJson(estimatePlan),
    [estimatePlan],
  );
  const projectLocked = assets.some((asset) => Boolean(
    asset.recoveryCandidate
      || asset.sessionAttemptKey
      || asset.sessionId
      || asset.uploadSessionId
      || asset.assetId,
  ));

  const filteredPackagePage = useMemo(() => {
    const needle = treeQuery.trim().toLocaleLowerCase("zh-CN");
    return (packagePage?.items ?? []).filter(
      (entry) => !needle || entry.path.toLocaleLowerCase("zh-CN").includes(needle),
    );
  }, [packagePage, treeQuery]);

  useEffect(() => {
    estimateRequestOwner.current += 1;
    setEstimate(null);
    setEstimateBusy(false);
  }, [estimatePlanDocument]);

  async function addFiles(files: Iterable<File>) {
    if (fileAdditionLock.current) {
      setFeedback("FILE_SELECTION_IN_PROGRESS");
      return;
    }
    const fileOwner = fileAdditionOwner.current + 1;
    fileAdditionOwner.current = fileOwner;
    fileAdditionLock.current = true;
    try {
    let identityGuard: IntakeIdentityGuard;
    try {
      identityGuard = captureIntakeIdentity();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
      return;
    }
    const selectedFiles: File[] = [];
    let selectedBytes = 0;
    for (const file of files) {
      if (selectionCapacity.current.count + selectedFiles.length >= maximumBatchAssets) {
        setFeedback("BATCH_ASSET_COUNT_LIMIT_EXCEEDED");
        return;
      }
      selectedBytes += file.size;
      if (
        !Number.isSafeInteger(file.size)
        || file.size < 0
        || !Number.isSafeInteger(selectedBytes)
        || selectionCapacity.current.bytes + selectedBytes > maximumBatchBytes
      ) {
        setFeedback("BATCH_BYTE_LIMIT_EXCEEDED");
        return;
      }
      selectedFiles.push(file);
    }
    if (selectedFiles.length === 0) return;
    if (!await ensureRecoveryStore()) {
      if (intakeIdentityIsCurrent(identityGuard)) setFeedback("RECOVERY_STORE_UNAVAILABLE");
      return;
    }
    assertIntakeIdentityCurrent(identityGuard);
    let fingerprinted: Array<{ file: File; fingerprint: string }>;
    try {
      fingerprinted = await Promise.all(
        selectedFiles.map(async (file) => ({ file, fingerprint: await fingerprintFile(file) })),
      );
      assertIntakeIdentityCurrent(identityGuard);
    } catch (_error) {
      if (intakeIdentityIsCurrent(identityGuard)) setFeedback("FILE_FINGERPRINT_FAILED");
      return;
    }
    const invalidRecoveryFingerprints = new Set<string>();
    for (const { file, fingerprint } of fingerprinted) {
      for (const record of recoveryRecords(projectId, fingerprint)) {
        if (
          record.expectedSize !== file.size
          || record.lastModified !== file.lastModified
          || record.partSize !== chunkBytes
        ) {
          try {
            await clearRecovery(record, identityGuard);
          } catch (_error) {
            if (intakeIdentityIsCurrent(identityGuard)) {
              setFeedback("RECOVERY_STORE_WRITE_FAILED");
            }
            return;
          }
          invalidRecoveryFingerprints.add(fingerprint);
        }
      }
    }
    const batchFingerprintCounts = new Map<string, number>();
    for (const { fingerprint } of fingerprinted) {
      batchFingerprintCounts.set(fingerprint, (batchFingerprintCounts.get(fingerprint) ?? 0) + 1);
    }
    const existingFingerprints = new Set(assets.map((asset) => asset.fileFingerprint));
    const collisionFingerprints = new Set(
      fingerprinted
        .map(({ fingerprint }) => fingerprint)
        .filter((fingerprint) =>
          (batchFingerprintCounts.get(fingerprint) ?? 0) > 1 || existingFingerprints.has(fingerprint)),
    );
    const hasCollision = collisionFingerprints.size > 0;
    assertIntakeIdentityCurrent(identityGuard);
    if (hasCollision) setFeedback("FILE_FINGERPRINT_COLLISION");
    selectionCapacity.current = {
      count: selectionCapacity.current.count + fingerprinted.length,
      bytes: selectionCapacity.current.bytes + selectedBytes,
    };
    setAssets((current) => {
      const protectedCurrent = current.map((asset) => collisionFingerprints.has(asset.fileFingerprint)
        ? {
            ...asset,
            phase: "BLOCKED" as const,
            progress: 100,
            permanentBlock: true,
            recoveryCandidate: false,
            recoveryAttached: false,
            code: "FILE_FINGERPRINT_COLLISION",
          }
        : asset);
      const additions = fingerprinted
        .map(({ file, fingerprint }, index): AssetDraft => {
          const collision = collisionFingerprints.has(fingerprint);
          const recoveries = collision ? [] : recoveryRecords(projectId, fingerprint);
          const code = invalidRecoveryFingerprints.has(fingerprint)
            ? "RECOVERY_METADATA_MISMATCH"
            : file.size <= 0
            ? "EMPTY_FILE_NOT_ALLOWED"
            : file.size > maximumProcessableAssetBytes
              ? "FILE_EXCEEDS_64_MIB_PROCESSING_LIMIT"
              : collision
                ? "FILE_FINGERPRINT_COLLISION"
              : supportedExtensions.has(extensionOf(file))
                ? undefined
                : "FILE_TYPE_NOT_IN_V1_ALLOWLIST";
          return {
            key: `${fingerprint}:${index}:${crypto.randomUUID()}`,
            fileFingerprint: fingerprint,
            attemptKey: crypto.randomUUID(),
            projectId: recoveries.length > 0 ? projectId : undefined,
            file,
            relativePath: relativePath(file),
            phase: code ? "BLOCKED" : "SELECTED",
            progress: 0,
            permanentBlock: Boolean(code),
            recoveryCandidate: recoveries.length > 0,
            recoveryAttached: false,
            confirmedPartCount: 0,
            processingAttempt: 0,
            role: recoveries[0]?.role ?? "PRIMARY",
            modelReadAllowed: recoveries[0]?.modelReadAllowed ?? true,
            code,
          };
        });
      return [...protectedCurrent, ...additions];
    });
    } finally {
      if (fileAdditionOwner.current === fileOwner) fileAdditionLock.current = false;
    }
  }

  function update(key: string, patch: Partial<AssetDraft>) {
    setAssets((current) => current.map((asset) => asset.key === key ? { ...asset, ...patch } : asset));
  }

  function updateMany(keys: readonly string[], patch: Partial<AssetDraft>) {
    const selected = new Set(keys);
    setAssets((current) => current.map((asset) => selected.has(asset.key) ? { ...asset, ...patch } : asset));
  }

  async function refreshProcessingEstimate() {
    if (!safeProject(projectId) || estimatePlan.stages.length === 0) {
      setEstimate({
        inputDigest: "",
        status: "BLOCKED",
        code: "ESTIMATION_STAGES_REQUIRED",
      });
      return;
    }
    let identityGuard: IntakeIdentityGuard;
    try {
      identityGuard = captureIntakeIdentity();
    } catch (error) {
      setEstimate({
        inputDigest: "",
        status: "BLOCKED",
        code: error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE",
      });
      return;
    }
    const owner = estimateRequestOwner.current + 1;
    estimateRequestOwner.current = owner;
    setEstimateBusy(true);
    setEstimate(null);
    try {
      const inputDigest = await sha256(new TextEncoder().encode(estimatePlanDocument).buffer);
      if (owner !== estimateRequestOwner.current) return;
      assertIntakeIdentityCurrent(identityGuard);
      const response = await executeGuardedIntakeSkill(
        identityGuard,
        projectId,
        "elmos-processing-cost-and-eta-estimation",
        "estimate",
        estimatePlan,
        `mmi-cost-estimate-${inputDigest.slice(0, 40)}`,
      );
      if (owner !== estimateRequestOwner.current) return;
      setEstimate(processingEstimate(response, `sha256:${inputDigest}`));
    } catch (error) {
      if (owner !== estimateRequestOwner.current || !intakeIdentityIsCurrent(identityGuard)) return;
      const failure = failureDetails(error, "PROCESSING_ESTIMATE_FAILED");
      setEstimate({
        inputDigest: "",
        status: "BLOCKED",
        code: failure.code,
      });
    } finally {
      if (owner === estimateRequestOwner.current) setEstimateBusy(false);
    }
  }

  async function uploadAsset(
    asset: AssetDraft,
    sessionId: string,
    projectAlias: string,
    identityGuard: IntakeIdentityGuard,
  ): Promise<string> {
    assertIntakeIdentityCurrent(identityGuard);
    if (asset.permanentBlock) throw new Error(asset.code ?? "ASSET_PERMANENTLY_BLOCKED");
    if (asset.sessionId && asset.sessionId !== sessionId) throw new Error("INPUT_SESSION_ID_CHANGED");
    if (asset.projectId !== projectAlias) throw new Error("ASSET_PROJECT_BINDING_MISMATCH");
    update(asset.key, {
      sessionId,
      phase: "HASHING",
      progress: 2,
      code: undefined,
      response: undefined,
      traceId: undefined,
    });
    const digest = await sha256FileOffMainThread(asset.file);
    assertIntakeIdentityCurrent(identityGuard);
    if (asset.sha256 && asset.sha256 !== digest) {
      await clearRecovery(asset, identityGuard);
      throw new Error("RECOVERY_CONTENT_HASH_MISMATCH");
    }
    update(asset.key, { sha256: digest, phase: "UPLOADING", progress: 5 });
    let recoveryAsset: AssetDraft = { ...asset, sessionId, sha256: digest };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);

    if (recoveryAsset.assetId) {
      update(asset.key, { phase: "PROCESSING", progress: 78 });
      return recoveryAsset.assetId;
    }

    const started = await executeGuardedIntakeSkill(
      identityGuard,
      projectAlias,
      "elmos-secure-resumable-upload",
      "start",
      {
        session_id: sessionId,
        display_name: asset.relativePath,
        expected_size: asset.file.size,
        expected_sha256: digest,
        declared_media_type: asset.file.type || "application/octet-stream",
        part_size: chunkBytes,
      },
      `mmi-${asset.attemptKey}-start`,
    );
    const uploadSessionId = responseString(started, "upload_session_id", "session_id", "upload_id");
    if (!uploadSessionId) throw new Error("UPLOAD_SESSION_ID_MISSING");
    if (asset.uploadSessionId && asset.uploadSessionId !== uploadSessionId) {
      throw new Error("UPLOAD_SESSION_ID_CHANGED");
    }
    update(asset.key, { uploadSessionId });
    recoveryAsset = { ...recoveryAsset, uploadSessionId };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);

    const partCount = Math.max(1, Math.ceil(asset.file.size / chunkBytes));
    if (recoveryAsset.confirmedPartCount > partCount) {
      await clearRecovery(recoveryAsset, identityGuard);
      throw new Error("RECOVERY_CONFIRMED_PROGRESS_INVALID");
    }
    for (let part = recoveryAsset.confirmedPartCount; part < partCount; part += 1) {
      const start = part * chunkBytes;
      const chunk = new Uint8Array(
        await asset.file.slice(start, Math.min(asset.file.size, start + chunkBytes)).arrayBuffer(),
      );
      const chunkDigest = await sha256(chunk.slice().buffer);
      assertIntakeIdentityCurrent(identityGuard);
      await executeGuardedIntakeSkill(
        identityGuard,
        projectAlias,
        "elmos-secure-resumable-upload",
        "upload_part",
        {
          upload_session_id: uploadSessionId,
          part_number: part,
          byte_offset: start,
          sha256: chunkDigest,
          data_b64: bytesToBase64(chunk),
        },
        `mmi-${asset.attemptKey}-part-${part + 1}`,
      );
      recoveryAsset = { ...recoveryAsset, confirmedPartCount: part + 1 };
      await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
      update(asset.key, {
        confirmedPartCount: part + 1,
        progress: 5 + Math.round(((part + 1) / partCount) * 60),
      });
    }
    update(asset.key, { phase: "VALIDATING", progress: 70 });
    const committed = await executeGuardedIntakeSkill(
      identityGuard,
      projectAlias,
      "elmos-secure-resumable-upload",
      "commit",
      { upload_session_id: uploadSessionId, expected_sha256: digest },
      `mmi-${asset.attemptKey}-commit`,
    );
    const assetId = responseString(committed, "asset_id", "asset_version_id", "object_id");
    if (!assetId) throw new Error("ASSET_ID_MISSING");
    if (asset.assetId && asset.assetId !== assetId) throw new Error("ASSET_ID_CHANGED");
    const committedAsset = outputRecord(committed, "asset");
    const assetVersion = positiveInteger(committedAsset?.version) ?? asset.assetVersion;
    recoveryAsset = { ...recoveryAsset, assetId, assetVersion };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
    update(asset.key, {
      assetId,
      assetVersion,
      phase: "PROCESSING",
      progress: 78,
    });
    return assetId;
  }

  async function processAll() {
    let identityGuard: IntakeIdentityGuard;
    try {
      identityGuard = captureIntakeIdentity();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
      return;
    }
    if (!recoveryStoreReady && !await ensureRecoveryStore()) {
      if (intakeIdentityIsCurrent(identityGuard)) setFeedback("RECOVERY_STORE_UNAVAILABLE");
      return;
    }
    assertIntakeIdentityCurrent(identityGuard);
    if (!safeProject(projectId)) {
      setFeedback("项目 ID 仅允许字母、数字、点、下划线、冒号和短横线。");
      return;
    }
    const fingerprintCounts = new Map<string, number>();
    for (const asset of assets) {
      fingerprintCounts.set(
        asset.fileFingerprint,
        (fingerprintCounts.get(asset.fileFingerprint) ?? 0) + 1,
      );
    }
    const duplicateFingerprints = new Set(
      [...fingerprintCounts]
        .filter(([, count]) => count > 1)
        .map(([fingerprint]) => fingerprint),
    );
    if (duplicateFingerprints.size > 0) {
      setAssets((current) => current.map((asset) => duplicateFingerprints.has(asset.fileFingerprint)
        ? {
            ...asset,
            phase: "BLOCKED",
            progress: 100,
            permanentBlock: true,
            recoveryCandidate: false,
            recoveryAttached: false,
            code: "FILE_FINGERPRINT_COLLISION",
          }
        : asset));
      setFeedback("FILE_FINGERPRINT_COLLISION");
      return;
    }
    const projectAlias = projectId;
    const retryable = assets.filter((asset) =>
      !asset.permanentBlock
      && asset.role !== "IGNORE"
      && asset.modelReadAllowed
      && ["SELECTED", "BLOCKED", "NEEDS_REVIEW"].includes(asset.phase));
    if (retryable.length === 0) {
      setFeedback("没有可接入或可恢复的条目；永久阻断的空文件、超限文件和不支持格式不会重试。");
      return;
    }
    if (retryable.some((asset) => asset.projectId && asset.projectId !== projectAlias)) {
      setFeedback("ASSET_PROJECT_BINDING_MISMATCH");
      return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    const newSessionAttemptKey = crypto.randomUUID();
    let candidates = retryable.map((asset): AssetDraft => {
      return {
        ...asset,
        projectId: asset.projectId ?? projectAlias,
        sessionAttemptKey: asset.sessionAttemptKey
          ?? newSessionAttemptKey,
      };
    });
    const newlyAssigned = retryable
      .filter((asset) => !asset.sessionAttemptKey && !asset.recoveryCandidate)
      .map((asset) => asset.key);
    if (newlyAssigned.length > 0) {
      updateMany(newlyAssigned, { projectId: projectAlias, sessionAttemptKey: newSessionAttemptKey });
    }
    const missingProjectBinding = retryable
      .filter((asset) => asset.sessionAttemptKey && !asset.projectId)
      .map((asset) => asset.key);
    if (missingProjectBinding.length > 0) updateMany(missingProjectBinding, { projectId: projectAlias });
    const bootstrapAttemptKey = candidates[0].sessionAttemptKey;
    if (!bootstrapAttemptKey) {
      setFeedback("INPUT_SESSION_ATTEMPT_KEY_MISSING");
      setBusy(false);
      return;
    }

    try {
      let engineProjectId = "";
      try {
        const bootstrapped = await executeGuardedIntakeSkill(
          identityGuard,
          projectAlias,
          "elmos-multimodal-input-orchestrator",
          "bootstrap_project",
          {},
          `mmi-${bootstrapAttemptKey}-bootstrap`,
        );
        engineProjectId = responseString(bootstrapped, "project_id", "engine_project_id") ?? "";
        if (!boundedOpaque(engineProjectId)) throw new Error("ENGINE_PROJECT_SCOPE_MISSING");
      } catch (error) {
        if (!intakeIdentityIsCurrent(identityGuard)) return;
        const failure = failureDetails(error, "PROJECT_BOOTSTRAP_FAILED");
        updateMany(candidates.map((asset) => asset.key), {
          phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
          progress: 100,
          permanentBlock: failure.quarantined,
          code: failure.code,
          traceId: failure.traceId,
          response: failure.payload,
        });
        setFeedback(failure.code);
        return;
      }

      const scopeMismatches = candidates.filter((asset) => {
        if (!asset.recoveryCandidate && !asset.recoveryAttached) return false;
        return recoveryRecords(projectAlias, asset.fileFingerprint, engineProjectId).length !== 1;
      });
      if (scopeMismatches.length > 0) {
        const mismatchedKeys = new Set(scopeMismatches.map((asset) => asset.key));
        for (const asset of candidates) {
          if (!mismatchedKeys.has(asset.key)) {
            update(asset.key, {
              phase: "BLOCKED",
              progress: 100,
              code: "RECOVERY_BATCH_ENGINE_PROJECT_SCOPE_MISMATCH",
            });
            continue;
          }
          update(asset.key, {
            attemptKey: crypto.randomUUID(),
            engineProjectId: undefined,
            sessionAttemptKey: undefined,
            sessionId: undefined,
            sha256: undefined,
            uploadSessionId: undefined,
            confirmedPartCount: 0,
            processingAttempt: 0,
            assetId: undefined,
            assetVersion: undefined,
            phase: "BLOCKED",
            progress: 100,
            permanentBlock: true,
            recoveryCandidate: false,
            recoveryAttached: false,
            code: "RECOVERY_ENGINE_PROJECT_SCOPE_MISMATCH",
          });
        }
        setFeedback("RECOVERY_ENGINE_PROJECT_SCOPE_MISMATCH");
        return;
      }

      candidates = candidates.map((asset) => {
        const recovery = asset.recoveryCandidate || asset.recoveryAttached
          ? recoveryRecords(projectAlias, asset.fileFingerprint, engineProjectId)[0]
          : undefined;
        return {
          ...asset,
          attemptKey: recovery?.attemptKey ?? asset.attemptKey,
          projectId: recovery?.projectId ?? asset.projectId,
          engineProjectId,
          sessionAttemptKey: recovery?.sessionAttemptKey ?? asset.sessionAttemptKey,
          sessionId: recovery?.sessionId ?? asset.sessionId,
          confirmedPartCount: recovery?.confirmedPartCount ?? asset.confirmedPartCount,
          sha256: recovery?.contentSha256 ?? asset.sha256,
          uploadSessionId: recovery?.uploadSessionId ?? asset.uploadSessionId,
          assetId: recovery?.assetId ?? asset.assetId,
          assetVersion: recovery?.assetVersion ?? asset.assetVersion,
          role: recovery?.role ?? asset.role,
          modelReadAllowed: recovery?.modelReadAllowed ?? asset.modelReadAllowed,
          processingAttempt: recovery?.processingAttempt ?? asset.processingAttempt,
          recoveryCandidate: false,
          recoveryAttached: true,
        };
      });
      const claimedAssetIds = new Map<string, string>();
      const identityCollisionKeys = new Set<string>();
      for (const asset of [...assets, ...candidates]) {
        if (!asset.assetId) continue;
        const owner = claimedAssetIds.get(asset.assetId);
        if (owner && owner !== asset.key) {
          identityCollisionKeys.add(owner);
          identityCollisionKeys.add(asset.key);
          continue;
        }
        claimedAssetIds.set(asset.assetId, asset.key);
      }
      if (identityCollisionKeys.size > 0) {
        updateMany([...identityCollisionKeys], {
          phase: "BLOCKED",
          progress: 100,
          permanentBlock: true,
          recoveryCandidate: false,
          recoveryAttached: false,
          code: "ASSET_IDENTITY_COLLISION",
        });
        setFeedback("ASSET_IDENTITY_COLLISION");
        return;
      }
      try {
        for (const asset of candidates) {
          await persistRecovery(recoveryFromAsset(asset, identityGuard), identityGuard);
          const partCount = Math.max(1, Math.ceil(asset.file.size / chunkBytes));
          update(asset.key, {
            attemptKey: asset.attemptKey,
            projectId: asset.projectId,
            engineProjectId,
            sessionAttemptKey: asset.sessionAttemptKey,
            sessionId: asset.sessionId,
            sha256: asset.sha256,
            uploadSessionId: asset.uploadSessionId,
            confirmedPartCount: asset.confirmedPartCount,
            processingAttempt: asset.processingAttempt,
            assetId: asset.assetId,
            assetVersion: asset.assetVersion,
            recoveryCandidate: false,
            recoveryAttached: true,
            progress: Math.min(69, 5 + Math.round((asset.confirmedPartCount / partCount) * 60)),
          });
        }
      } catch (error) {
        if (!intakeIdentityIsCurrent(identityGuard)) return;
        const failure = failureDetails(error, "RECOVERY_STORE_WRITE_FAILED");
        updateMany(candidates.map((asset) => asset.key), {
          phase: "BLOCKED",
          progress: 100,
          code: failure.code,
          traceId: failure.traceId,
          response: failure.payload,
        });
        setFeedback(failure.code);
        return;
      }

      const grouped = new Map<string, {
        sessionAttemptKey: string;
        sessionId?: string;
        role: AssetDraft["role"];
        assets: AssetDraft[];
      }>();
      for (const asset of candidates) {
        const sessionAttemptKey = asset.sessionAttemptKey;
        if (!sessionAttemptKey) continue;
        const groupKey = asset.sessionId
          ? `session:${asset.sessionId}`
          : `attempt:${sessionAttemptKey}:${asset.role}`;
        const group = grouped.get(groupKey) ?? {
          sessionAttemptKey,
          sessionId: asset.sessionId,
          role: asset.role,
          assets: [],
        };
        if (group.role !== asset.role) throw new Error("SESSION_ROLE_SCOPE_MISMATCH");
        group.assets.push(asset);
        grouped.set(groupKey, group);
      }

      const resolved: Array<{ sessionAttemptKey: string; sessionId: string; assets: AssetDraft[] }> = [];
      for (const group of grouped.values()) {
        try {
          let sessionId = group.sessionId;
          if (!sessionId) {
            const created = await executeGuardedIntakeSkill(
              identityGuard,
              projectAlias,
              "elmos-multimodal-input-orchestrator",
              "create_session",
              { requested_role: group.role },
              `mmi-${group.sessionAttemptKey}-session`,
            );
            sessionId = responseString(created, "session_id") ?? "";
            if (!sessionId) throw new Error("INPUT_SESSION_ID_MISSING");
            updateMany(group.assets.map((asset) => asset.key), { sessionId });
            for (const asset of group.assets) {
              await persistRecovery(
                recoveryFromAsset({ ...asset, sessionId }, identityGuard),
                identityGuard,
              );
            }
          }
          resolved.push({
            sessionAttemptKey: group.sessionAttemptKey,
            sessionId,
            assets: group.assets.map((asset) => ({ ...asset, sessionId })),
          });
        } catch (error) {
          if (!intakeIdentityIsCurrent(identityGuard)) return;
          const failure = failureDetails(error, "INPUT_SESSION_CREATION_FAILED");
          updateMany(group.assets.map((asset) => asset.key), {
            phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
            progress: 100,
            permanentBlock: failure.quarantined,
            code: failure.code,
            traceId: failure.traceId,
            response: failure.payload,
          });
        }
      }

      const uploadedGroups: Array<{
        group: { sessionAttemptKey: string; sessionId: string; assets: AssetDraft[] };
        uploaded: Map<string, string>;
      }> = [];
      for (const group of resolved) {
        const uploaded = new Map<string, string>();
        for (const asset of group.assets) {
          try {
            const assetId = await uploadAsset(
              asset,
              group.sessionId,
              projectAlias,
              identityGuard,
            );
            const owner = claimedAssetIds.get(assetId);
            if (owner && owner !== asset.key) {
              identityCollisionKeys.add(owner);
              identityCollisionKeys.add(asset.key);
              continue;
            }
            claimedAssetIds.set(assetId, asset.key);
            uploaded.set(asset.key, assetId);
          } catch (error) {
            if (!intakeIdentityIsCurrent(identityGuard)) return;
            const failure = failureDetails(error, "UPLOAD_FAILED");
            const recoveryInvalid = [
              "RECOVERY_CONTENT_HASH_MISMATCH",
              "RECOVERY_CONFIRMED_PROGRESS_INVALID",
              "RECOVERY_METADATA_INVALID",
            ].includes(failure.code);
            const permanentlyBlocked = failure.quarantined || recoveryInvalid || failure.retryable === false;
            update(asset.key, {
              phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
              progress: 100,
              permanentBlock: permanentlyBlocked,
              recoveryCandidate: false,
              recoveryAttached: permanentlyBlocked ? false : asset.recoveryAttached,
              ...(recoveryInvalid ? {
                engineProjectId: undefined,
                sessionAttemptKey: undefined,
                sessionId: undefined,
                sha256: undefined,
                uploadSessionId: undefined,
                confirmedPartCount: 0,
                processingAttempt: 0,
                assetId: undefined,
                assetVersion: undefined,
              } : {}),
              code: failure.code,
              traceId: failure.traceId,
              response: failure.payload,
            });
          }
        }
        if (uploaded.size > 0) uploadedGroups.push({ group, uploaded });
      }
      if (identityCollisionKeys.size > 0) {
        updateMany([...identityCollisionKeys], {
          phase: "BLOCKED",
          progress: 100,
          permanentBlock: true,
          recoveryCandidate: false,
          recoveryAttached: false,
          code: "ASSET_IDENTITY_COLLISION",
        });
        setFeedback("ASSET_IDENTITY_COLLISION");
        return;
      }

      for (const { group, uploaded } of uploadedGroups) {
        try {
          const committedAssetIds = new Set(
            assets
              .filter((asset) => asset.sessionId === group.sessionId && asset.assetId)
              .map((asset) => asset.assetId as string),
          );
          for (const assetId of uploaded.values()) committedAssetIds.add(assetId);
          const membership = [...committedAssetIds].sort().join("\n");
          const membershipDigest = await sha256(new TextEncoder().encode(membership).buffer);
          assertIntakeIdentityCurrent(identityGuard);
          const processingAttempt = Math.max(
            0,
            ...group.assets.map((asset) => asset.processingAttempt),
          );
          const processed = await executeGuardedIntakeSkill(
            identityGuard,
            projectAlias,
            "elmos-multimodal-input-orchestrator",
            "process_session",
            {
              session_id: group.sessionId,
              max_attempts: 3,
              expected_asset_generation_digest: membershipDigest,
            },
            `mmi-${group.sessionAttemptKey}-process-${membershipDigest.slice(0, 32)}-${processingAttempt}`,
          );
          const output = nestedRecord(processed);
          const processingJobId = responseString(processed, "job_id");
          if (
            !processingJobId
            || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(processingJobId)
          ) throw new Error("WORKFLOW_JOB_ID_MISSING");
          const processedAssets = Array.isArray(output.assets) ? output.assets : [];
          const assetsTruncated = output.assets_truncated === true;
          const resultById = new Map<string, Record<string, unknown>>();
          for (const item of processedAssets) {
            if (item && typeof item === "object" && !Array.isArray(item)) {
              const entry = item as Record<string, unknown>;
              if (typeof entry.asset_id === "string") {
                if (resultById.has(entry.asset_id)) {
                  throw new Error("WORKFLOW_DUPLICATE_ASSET_ID");
                }
                resultById.set(entry.asset_id, entry);
              }
            }
          }
          for (const [key, assetId] of uploaded) {
            const assetResult = resultById.get(assetId);
            const assetStatus = assetResult?.status;
            const assetVersion = positiveInteger(assetResult?.version);
            const phase = assetResult
              ? typeof assetStatus === "string"
                ? phaseFrom({ status: assetStatus })
                : "NEEDS_REVIEW"
              : "NEEDS_REVIEW";
            const assetCode = assetResult
              ? responseString(assetResult as SkillResponse, "failure_code", "error_code", "code")
              : undefined;
            const terminal = ["READY", "QUARANTINED"].includes(phase);
            const nextProcessingAttempt = processingAttempt + 1;
            update(key, {
              phase,
              progress: 100,
              permanentBlock: phase === "QUARANTINED",
              recoveryAttached: !terminal,
              processingAttempt: terminal ? processingAttempt : nextProcessingAttempt,
              processingJobId: terminal ? undefined : processingJobId,
              ...(assetVersion ? { assetVersion } : {}),
              response: processed,
              traceId: responseString(processed, "trace_id"),
              code: phase === "READY"
                ? undefined
                : !assetResult
                  ? assetsTruncated
                    ? "WORKFLOW_ASSET_SUMMARY_TRUNCATED"
                    : "WORKFLOW_ASSET_RESULT_MISSING"
                  : assetCode ?? responseString(processed, "code", "error_code"),
            });
            const completedAsset = group.assets.find((asset) => asset.key === key);
            if (terminal && completedAsset) {
              await clearRecovery(completedAsset, identityGuard);
            } else if (completedAsset) {
              if (!completedAsset.engineProjectId) {
                throw new Error("RECOVERY_PROCESSING_SCOPE_MISSING");
              }
              const records = recoveryRecords(
                projectAlias,
                completedAsset.fileFingerprint,
                completedAsset.engineProjectId,
              );
              if (records.length !== 1) throw new Error("RECOVERY_PROCESSING_STATE_MISSING");
              await persistRecovery(
                {
                  ...records[0],
                  processingAttempt: nextProcessingAttempt,
                  ...(assetVersion ? { assetVersion } : {}),
                  updatedAt: Date.now(),
                },
                identityGuard,
              );
            }
          }
        } catch (error) {
          if (!intakeIdentityIsCurrent(identityGuard)) return;
          const failure = failureDetails(error, "SESSION_PROCESSING_FAILED");
          const workflowIntegrityFailure = [
            "WORKFLOW_DUPLICATE_ASSET_ID",
            "RECOVERY_PROCESSING_STATE_MISSING",
            "RECOVERY_PROCESSING_SCOPE_MISSING",
          ].includes(failure.code);
          updateMany([...uploaded.keys()], {
            phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
            progress: 100,
            permanentBlock: failure.quarantined || workflowIntegrityFailure,
            code: failure.code,
            traceId: failure.traceId,
            response: failure.payload,
          });
        }
      }
    } finally {
      if (intakeBusyOwner.current === busyOwner) setBusy(false);
    }
  }

  function addDirectText() {
    const value = directText.trim();
    if (!value) return;
    const file = new File([value], `direct-input-${Date.now()}.md`, {
      type: "text/markdown;charset=utf-8",
      lastModified: Date.now(),
    });
    void addFiles([file]);
    setDirectText("");
  }

  async function buildPackagePreview() {
    if (!safeProject(projectId) || assets.length === 0) return;
    let identityGuard: IntakeIdentityGuard;
    try {
      identityGuard = captureIntakeIdentity();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
      return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    try {
      if (assets.some((asset) => asset.file.size <= 0 || asset.file.size > maximumProcessableAssetBytes)) {
        throw new Error("PREVIEW_REQUIRES_BOUNDED_NON_EMPTY_ASSETS");
      }
      const previewAssets: Array<AssetDraft & { sha256: string }> = [];
      for (const asset of assets) {
        const digest = asset.sha256 ?? await sha256FileOffMainThread(asset.file);
        assertIntakeIdentityCurrent(identityGuard);
        if (!/^[0-9a-f]{64}$/.test(digest)) throw new Error("PREVIEW_CONTENT_DIGEST_INVALID");
        if (asset.sha256 && asset.sha256 !== digest) {
          throw new Error("PREVIEW_CONTENT_DIGEST_MISMATCH");
        }
        if (!asset.sha256) update(asset.key, { sha256: digest });
        previewAssets.push({ ...asset, sha256: digest });
      }
      const previewScopeDigest = await sha256(
        new TextEncoder().encode(`preview-bootstrap\u0000${projectId}`).buffer,
      );
      assertIntakeIdentityCurrent(identityGuard);
      await executeGuardedIntakeSkill(
        identityGuard,
        projectId,
        "elmos-multimodal-input-orchestrator",
        "bootstrap_project",
        {},
        `mmi-preview-bootstrap-${previewScopeDigest.slice(0, 40)}`,
      );
      const entries = previewAssets.map((asset) => ({
        path: asset.relativePath,
        kind: "file",
        byte_count: asset.file.size,
        content_digest: `sha256:${asset.sha256}`,
        role: asset.role,
        model_read_allowed: asset.modelReadAllowed && asset.phase === "READY",
        metadata: {
          ...(asset.assetId ? { asset_id: asset.assetId } : {}),
          intake_state: asset.phase,
        },
      }));
      const packageSessionId = `package-${crypto.randomUUID()}`;
      await executeGuardedIntakeSkill(
        identityGuard,
        projectId,
        "elmos-folder-tree-input",
        "begin",
        { session_id: packageSessionId, expected_entry_count: entries.length },
        `mmi-package-begin-${packageSessionId}`,
      );
      for (let offset = 0, chunkIndex = 0; offset < entries.length; offset += 1_000, chunkIndex += 1) {
        await executeGuardedIntakeSkill(
          identityGuard,
          projectId,
          "elmos-folder-tree-input",
          "append",
          { session_id: packageSessionId, chunk_index: chunkIndex, entries: entries.slice(offset, offset + 1_000) },
          `mmi-package-append-${packageSessionId}-${chunkIndex}`,
        );
      }
      const finalized = await executeGuardedIntakeSkill(
        identityGuard,
        projectId,
        "elmos-folder-tree-input",
        "finalize",
        { session_id: packageSessionId },
        `mmi-package-finalize-${packageSessionId}`,
      );
      const packageVersion = nestedRecord(finalized).package_version;
      if (!Number.isSafeInteger(packageVersion) || Number(packageVersion) < 1) {
        throw new Error("PROJECT_PACKAGE_VERSION_INVALID");
      }
      const firstPage = await executeGuardedIntakeSkill(
        identityGuard,
        projectId,
        "elmos-project-package-preview-and-review-ui",
        "page",
        { package_version: packageVersion, limit: 100 },
        `mmi-package-page-${packageSessionId}-0`,
      );
      setPackagePreview(finalized);
      setPackagePage(projectPackagePage(firstPage));
      setPackagePageCursors([null]);
      setPackagePageIndex(0);
    } catch (error) {
      if (intakeIdentityIsCurrent(identityGuard)) {
        setFeedback(error instanceof Error ? error.message : "PACKAGE_PREVIEW_FAILED");
      }
    } finally {
      if (intakeBusyOwner.current === busyOwner) setBusy(false);
    }
  }

  async function loadPackagePage(cursor: string | null, targetIndex: number) {
    if (!packagePage || targetIndex < 0 || !safeProject(projectId)) return;
    let identityGuard: IntakeIdentityGuard;
    try {
      identityGuard = captureIntakeIdentity();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
      return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    try {
      const response = await executeGuardedIntakeSkill(
        identityGuard,
        projectId,
        "elmos-project-package-preview-and-review-ui",
        "page",
        {
          package_version: packagePage.package_version,
          limit: 100,
          ...(cursor ? { cursor } : {}),
        },
        `mmi-package-page-${packagePage.collection_digest}-${targetIndex}-${crypto.randomUUID()}`,
      );
      const page = projectPackagePage(response);
      if (
        page.package_version !== packagePage.package_version
        || page.collection_digest !== packagePage.collection_digest
      ) throw new Error("PROJECT_PACKAGE_PAGE_DRIFT");
      setPackagePage(page);
      setPackagePageIndex(targetIndex);
    } catch (error) {
      if (intakeIdentityIsCurrent(identityGuard)) {
        setFeedback(error instanceof Error ? error.message : "PROJECT_PACKAGE_PAGE_FAILED");
      }
    } finally {
      if (intakeBusyOwner.current === busyOwner) setBusy(false);
    }
  }

  function selectedReviewTask(): ReviewTask | undefined {
    return reviewTasks.find((task) => task.task_id === selectedReviewTaskId);
  }

  type ReviewRequestGuard = {
    generation: number;
    owner: number;
    projectId: string;
    identityScope: string;
  };

  function beginReviewRequest(): ReviewRequestGuard {
    const guard = {
      generation: reviewScopeGeneration.current,
      owner: reviewRequestOwner.current + 1,
      projectId,
      identityScope: reviewIdentityScope,
    };
    reviewRequestOwner.current = guard.owner;
    setReviewBusy(true);
    return guard;
  }

  function reviewRequestIsCurrent(guard: ReviewRequestGuard): boolean {
    return guard.generation === reviewScopeGeneration.current
      && guard.owner === reviewRequestOwner.current;
  }

  function assertReviewRequestCurrent(guard: ReviewRequestGuard): void {
    if (!reviewRequestIsCurrent(guard)) throw new Error("HUMAN_REVIEW_SCOPE_CHANGED");
  }

  function finishReviewRequest(guard: ReviewRequestGuard): void {
    if (reviewRequestIsCurrent(guard)) setReviewBusy(false);
  }

  async function executeGuardedReviewSkill(
    guard: ReviewRequestGuard,
    skill: string,
    operation: string,
    input: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<SkillResponse> {
    assertReviewRequestCurrent(guard);
    const response = await executeSkill(
      guard.projectId,
      skill,
      operation,
      input,
      idempotencyKey,
    );
    assertReviewRequestCurrent(guard);
    return response;
  }

  function saveReviewClaim(claim: ReviewClaim): boolean {
    if (!reviewIdentityScope || claim.identity_scope !== reviewIdentityScope) return false;
    const next = Object.fromEntries(
      Object.entries(reviewClaims).filter(([, value]) => (
        validReviewClaim(value, reviewIdentityScope)
      )),
    ) as Record<string, ReviewClaim>;
    next[claim.task_id] = claim;
    if (!persistReviewClaims(next, reviewIdentityScope)) return false;
    setReviewClaims(next);
    return true;
  }

  function discardReviewClaim(taskId: string): boolean {
    if (!reviewIdentityScope) return false;
    const next = Object.fromEntries(
      Object.entries(reviewClaims).filter(
        ([candidateId, value]) => (
          candidateId !== taskId && validReviewClaim(value, reviewIdentityScope)
        ),
      ),
    ) as Record<string, ReviewClaim>;
    if (!persistReviewClaims(next, reviewIdentityScope)) return false;
    setReviewClaims(next);
    return true;
  }

  function abandonReviewClaimRecovery(taskId: string) {
    if (!discardReviewClaim(taskId)) {
      setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED");
      return;
    }
    setReviewTasks((current) => current.filter((task) => task.task_id !== taskId));
    setSelectedReviewTaskId("");
    setFeedback("本地领取恢复已清除；请刷新队列后按最新任务版本重新领取。");
  }

  function reconcileReviewClaims(tasks: readonly ReviewTask[]) {
    if (!reviewIdentityScope) return;
    const next = { ...reviewClaims };
    let changed = false;
    for (const [taskId, claim] of Object.entries(next)) {
      if (!validReviewClaim(claim, reviewIdentityScope)) {
        delete next[taskId];
        changed = true;
        continue;
      }
      if (claim.project_id !== projectId) continue;
      const task = tasks.find((candidate) => candidate.task_id === taskId);
      const closed = task && ["APPROVED", "REJECTED", "REVERTING", "REVERTED"].includes(task.state);
      const fencedDrift = task && claim.fence !== undefined && (
        task.claim_fence !== claim.fence
        || task.claim_expires_at !== claim.expires_at
        || !["CLAIMED", "EDITED"].includes(task.state)
      );
      // A pending receipt is the only durable handle for replaying a claim
      // whose response was lost.  List state is observational: CLAIMED vN+1
      // can mean this exact request committed.  Preserve the original key and
      // token until the server gives a definitive conflict or the bounded
      // recovery window expires.
      if (!task || closed || fencedDrift) {
        delete next[taskId];
        changed = true;
      }
    }
    if (changed && persistReviewClaims(next, reviewIdentityScope)) {
      setReviewClaims(next);
    }
  }

  type ReviewTaskExpectation = {
    priorTask?: ReviewTask;
    taskId?: string;
    assetId?: string;
    targetKind?: ReviewTargetKind;
    target?: Record<string, unknown>;
    originalValue?: unknown;
    bindOriginalValue?: boolean;
    state?: string;
    version?: number;
    minimumVersion?: number;
    correctionVersion?: number;
    claimFence?: number;
  };

  async function validatedReviewTask(
    response: SkillResponse,
    guard: ReviewRequestGuard,
    expected: ReviewTaskExpectation = {},
  ): Promise<ReviewTask> {
    assertReviewRequestCurrent(guard);
    const task = reviewTask(outputRecord(response, "task"), reviewEngineScope.current);
    if (!task) throw new Error("HUMAN_REVIEW_TASK_RESPONSE_INVALID");
    if (expected.priorTask) {
      const immutable = (candidate: ReviewTask) => ({
        tenant_id: candidate.tenant_id,
        project_id: candidate.project_id,
        created_by: candidate.created_by,
        asset_id: candidate.asset_id,
        target_kind: candidate.target_kind,
        target: candidate.target,
        original_value: candidate.original_value,
        source_digest: candidate.source_digest,
        source_ref: candidate.source_ref,
        confidence: candidate.confidence,
        reason: candidate.reason,
        created_at: candidate.created_at,
      });
      if (
        !expected.priorTask.detail_loaded
        || !task.detail_loaded
        || canonicalStrictJson(immutable(task))
          !== canonicalStrictJson(immutable(expected.priorTask))
        || task.version < expected.priorTask.version
        || task.version === expected.priorTask.version
          && canonicalStrictJson(reviewTaskDynamicState(task))
            !== canonicalStrictJson(reviewTaskDynamicState(expected.priorTask))
      ) throw new Error("HUMAN_REVIEW_TASK_IMMUTABLE_BINDING_INVALID");
    }
    if (
      expected.taskId !== undefined && task.task_id !== expected.taskId
      || expected.assetId !== undefined && task.asset_id !== expected.assetId
      || expected.targetKind !== undefined && task.target_kind !== expected.targetKind
      || expected.target !== undefined && (
        task.target === undefined
        || canonicalStrictJson(task.target) !== canonicalStrictJson(expected.target)
      )
      || expected.bindOriginalValue === true && (
        !Object.hasOwn(task, "original_value")
        || canonicalStrictJson(task.original_value) !== canonicalStrictJson(expected.originalValue)
      )
      || expected.state !== undefined && task.state !== expected.state
      || expected.version !== undefined && task.version !== expected.version
      || expected.minimumVersion !== undefined && task.version < expected.minimumVersion
      || expected.correctionVersion !== undefined
        && task.current_correction_version !== expected.correctionVersion
      || expected.claimFence !== undefined && task.claim_fence !== expected.claimFence
    ) {
      throw new Error("HUMAN_REVIEW_TASK_RESPONSE_BINDING_INVALID");
    }
    if (task.detail_loaded) {
      const expectedClientDigest = task.source_ref?.original_value_client_digest;
      const observedClientDigest = `sha256:${await sha256(
        new TextEncoder().encode(canonicalStrictJson(task.original_value)).buffer,
      )}`;
      if (observedClientDigest !== expectedClientDigest) {
        throw new Error("HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_INVALID");
      }
    }
    assertReviewRequestCurrent(guard);
    return task;
  }

  function commitReviewTask(task: ReviewTask): ReviewTask {
    setReviewTasks((current) => [
      task,
      ...current.filter((candidate) => candidate.task_id !== task.task_id),
    ].sort((left, right) => left.confidence - right.confidence || left.task_id.localeCompare(right.task_id)));
    setSelectedReviewTaskId(task.task_id);
    return task;
  }

  async function ensureReviewProject(guard: ReviewRequestGuard) {
    if (!safeProject(guard.projectId)) throw new Error("PROJECT_ID_INVALID");
    const scopeDigest = await sha256(
      new TextEncoder().encode(`review-bootstrap\u0000${guard.projectId}`).buffer,
    );
    assertReviewRequestCurrent(guard);
    const response = await executeGuardedReviewSkill(
      guard,
      "elmos-multimodal-input-orchestrator",
      "bootstrap_project",
      {},
      `mmi-review-bootstrap-${scopeDigest.slice(0, 40)}`,
    );
    const tenantId = responseString(response, "tenant_id");
    const engineProjectId = responseString(response, "project_id", "engine_project_id");
    if (!boundedOpaque(tenantId) || !boundedOpaque(engineProjectId)) {
      throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
    }
    const prior = reviewEngineScope.current;
    if (prior && (prior.tenantId !== tenantId || prior.projectId !== engineProjectId)) {
      throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_CHANGED");
    }
    assertReviewRequestCurrent(guard);
    reviewEngineScope.current = { tenantId, projectId: engineProjectId };
  }

  async function refreshReviewQueue() {
    const guard = beginReviewRequest();
    setFeedback("");
    setReviewPropagation(null);
    try {
      await ensureReviewProject(guard);
      const engineScope = reviewEngineScope.current;
      if (!engineScope) throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
      const cursorFilterDigest = await sha256(
        new TextEncoder().encode(canonicalStrictJson({
          tenant_id: engineScope.tenantId,
          project_id: engineScope.projectId,
          kinds: [],
          states: [],
          confidence_lte: 1,
        })).buffer,
      );
      assertReviewRequestCurrent(guard);
      const tasks: ReviewTask[] = [];
      const taskIds = new Set<string>();
      const cursors = new Set<string>();
      let cursor: string | null = null;
      let expectedTotal: number | undefined;
      let pageCount = 0;
      do {
        pageCount += 1;
        if (pageCount > maximumReviewQueuePages) {
          throw new Error("HUMAN_REVIEW_TASK_PAGE_LIMIT_EXCEEDED");
        }
        const response = await executeGuardedReviewSkill(
          guard,
          "elmos-human-review-and-correction",
          "list",
          {
            kinds: [],
            states: [],
            confidence_lte: 1,
            limit: 200,
            cursor,
          },
          `mmi-review-list-${crypto.randomUUID()}`,
        );
        const output = exactReviewOutput(response, ["tasks", "next_cursor", "total"]);
        const rawTasks = output.tasks;
        const total = output.total;
        const nextCursor = output.next_cursor;
        if (
          !Array.isArray(rawTasks)
          || rawTasks.length > 200
          || typeof total !== "number"
          || !Number.isSafeInteger(total)
          || total < 0
          || total > maximumReviewQueueTasks
          || (nextCursor !== null && (
            typeof nextCursor !== "string" || !boundedOpaque(nextCursor)
          ))
          || (expectedTotal !== undefined && total !== expectedTotal)
        ) throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
        expectedTotal = total;
        for (const value of rawTasks) {
          const task = reviewTask(value);
          if (!task || taskIds.has(task.task_id)) {
            throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
          }
          taskIds.add(task.task_id);
          tasks.push(task);
        }
        if (tasks.length > total || tasks.length > maximumReviewQueueTasks) {
          throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
        }
        if (nextCursor !== null) {
          const lastTask = tasks.at(-1);
          if (
            cursors.has(nextCursor)
            || rawTasks.length !== 200
            || tasks.length >= total
            || pageCount >= Math.ceil(total / 200)
            || !lastTask
            || !exactReviewCursor(nextCursor, cursorFilterDigest, lastTask)
          ) {
            throw new Error("HUMAN_REVIEW_TASK_CURSOR_INVALID");
          }
          cursors.add(nextCursor);
        }
        cursor = nextCursor as string | null;
      } while (cursor !== null);
      if (tasks.length !== expectedTotal) {
        throw new Error("HUMAN_REVIEW_TASK_LIST_CHANGED");
      }
      setReviewTasks(tasks);
      reconcileReviewClaims(tasks);
      setSelectedReviewTaskId("");
      setCorrection("");
      setCorrectionTouched(false);
      setReviewPropagation(null);
      setReviewCurrentCorrection(null);
      setFeedback(`已完整载入 ${tasks.length} 个审阅任务；低置信项优先。`);
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_LIST_FAILED");
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function fetchCurrentReviewCorrection(
    guard: ReviewRequestGuard,
    task: ReviewTask,
  ): Promise<Record<string, unknown> | undefined> {
    if (task.current_correction_version === 0) return undefined;
    const response = await executeGuardedReviewSkill(
      guard,
      "elmos-human-review-and-correction",
      "current_correction",
      { task_id: task.task_id },
      `mmi-review-current-correction-${task.task_id}-${task.current_correction_version}`,
    );
    const output = exactReviewOutput(response, ["correction"]);
    if (!exactCurrentReviewCorrection(output.correction, task)) {
      throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_RESPONSE_INVALID");
    }
    assertReviewRequestCurrent(guard);
    return output.correction as Record<string, unknown>;
  }

  async function selectReviewTask(taskId: string) {
    if (taskId !== selectedReviewTaskId) {
      setCorrection("");
      setCorrectionTouched(false);
      setReviewCurrentCorrection(null);
    }
    setSelectedReviewTaskId(taskId);
    setReviewPropagation(null);
    const summary = reviewTasks.find((task) => task.task_id === taskId);
    if (!summary) return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
      let detail = summary;
      if (!summary.detail_loaded) {
        const response = await executeGuardedReviewSkill(
          guard,
          "elmos-human-review-and-correction",
          "get",
          { task_id: taskId },
          `mmi-review-get-${taskId}-${summary.version}`,
        );
        exactReviewOutput(response, ["task"]);
        detail = await validatedReviewTask(response, guard, {
          taskId,
          assetId: summary.asset_id,
          targetKind: summary.target_kind,
          minimumVersion: summary.version,
        });
        assertReviewRequestCurrent(guard);
        const immutableSummary = {
          asset_id: summary.asset_id,
          target_kind: summary.target_kind,
          source_digest: summary.source_digest,
          confidence: summary.confidence,
          reason: summary.reason,
          created_at: summary.created_at,
        };
        const immutableDetail = {
          asset_id: detail.asset_id,
          target_kind: detail.target_kind,
          source_digest: detail.source_digest,
          confidence: detail.confidence,
          reason: detail.reason,
          created_at: detail.created_at,
        };
        if (
          !detail.detail_loaded
          || canonicalStrictJson(immutableSummary) !== canonicalStrictJson(immutableDetail)
          || detail.version === summary.version
            && canonicalStrictJson(reviewTaskDynamicState(summary))
              !== canonicalStrictJson(reviewTaskDynamicState(detail))
        ) throw new Error("HUMAN_REVIEW_TASK_DETAIL_INVALID");
      }
      const currentCorrection = await fetchCurrentReviewCorrection(guard, detail);
      assertReviewRequestCurrent(guard);
      commitReviewTask(detail);
      setReviewCurrentCorrection(currentCorrection ?? null);
      setFeedback(currentCorrection
        ? `审阅任务 ${taskId} 的权威原值、来源与当前纠正版本已载入。`
        : `审阅任务 ${taskId} 的权威原值与来源已载入。`);
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        setSelectedReviewTaskId("");
        setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_TASK_DETAIL_FAILED");
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function refreshReviewSources() {
    const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    if (!asset?.assetId || !asset.sha256 || !positiveInteger(asset.assetVersion)) {
      setFeedback("HUMAN_REVIEW_SOURCE_ASSET_REQUIRED");
      return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
      await ensureReviewProject(guard);
      const engineScope = reviewEngineScope.current;
      if (!engineScope) throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
      const filterDigest = await sha256(
        new TextEncoder().encode(canonicalStrictJson({
          schema_version: "human-review-source-filter-v1",
          tenant_id: engineScope.tenantId,
          project_id: engineScope.projectId,
          content_id: asset.assetId,
          content_version: asset.assetVersion,
          kinds: [],
        })).buffer,
      );
      assertReviewRequestCurrent(guard);
      const sources: ReviewSource[] = [];
      const sourceKeys = new Set<string>();
      const cursors = new Set<string>();
      let cursor: string | null = null;
      let collectionDigest: string | undefined;
      let collectionGeneration: number | undefined;
      let expectedTotal: number | undefined;
      let pageCount = 0;
      do {
        pageCount += 1;
        if (pageCount > maximumReviewSourcePages) {
          throw new Error("HUMAN_REVIEW_SOURCE_PAGE_LIMIT_EXCEEDED");
        }
        const response = await executeGuardedReviewSkill(
          guard,
          "elmos-human-review-and-correction",
          "source_list",
          {
            content_id: asset.assetId,
            expected_asset_version: asset.assetVersion,
            kinds: [],
            limit: 200,
            cursor,
          },
          `mmi-review-source-list-${crypto.randomUUID()}`,
        );
        const output = exactReviewOutput(response, ["sources", "next_cursor", "total"]);
        const rawSources = output.sources;
        const total = output.total;
        const nextCursor = output.next_cursor;
        if (
          !Array.isArray(rawSources)
          || rawSources.length > 200
          || typeof total !== "number"
          || !Number.isSafeInteger(total)
          || total < 0
          || total > maximumReviewSources
          || !(nextCursor === null || typeof nextCursor === "string")
          || expectedTotal !== undefined && total !== expectedTotal
        ) throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
        expectedTotal = total;
        for (const value of rawSources) {
          const source = reviewSource(value);
          if (
            !source
            || source.detail_loaded
            || source.content_id !== asset.assetId
            || source.content_version !== asset.assetVersion
            || source.source_ref.asset_sha256 !== `sha256:${asset.sha256}`
          ) throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
          const key = reviewSourceKey(source);
          if (sourceKeys.has(key)) throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
          sourceKeys.add(key);
          sources.push(source);
        }
        if (sources.length > total || sources.length > maximumReviewSources) {
          throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
        }
        if (nextCursor !== null) {
          const lastSource = sources.at(-1);
          const observedCursorBinding = lastSource
            ? exactReviewSourceCursor(
                nextCursor,
                filterDigest,
                collectionDigest,
                collectionGeneration,
                lastSource,
              )
            : undefined;
          if (
            cursors.has(nextCursor)
            || rawSources.length !== 200
            || sources.length >= total
            || pageCount >= Math.ceil(total / 200)
            || observedCursorBinding === undefined
          ) throw new Error("HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
          collectionDigest = observedCursorBinding.collectionDigest;
          collectionGeneration = observedCursorBinding.collectionGeneration;
          cursors.add(nextCursor);
        }
        cursor = nextCursor as string | null;
      } while (cursor !== null);
      if (sources.length !== expectedTotal) {
        throw new Error("HUMAN_REVIEW_SOURCE_COLLECTION_CHANGED");
      }
      assertReviewRequestCurrent(guard);
      setReviewSources([...sources].sort((left, right) => (
        left.confidence - right.confidence
        || left.target_kind.localeCompare(right.target_kind)
        || left.target_digest.localeCompare(right.target_digest)
      )));
      setSelectedReviewSourceKey("");
      setReviewTargetLocator("");
      setReviewOriginalValue("");
      setFeedback(`已载入 ${sources.length} 个版本绑定的权威待审来源；请选择一项查看原值。`);
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_SOURCE_LIST_FAILED");
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function selectReviewSource(key: string) {
    setSelectedReviewSourceKey(key);
    setReviewTargetLocator("");
    setReviewOriginalValue("");
    const summary = reviewSources.find((source) => reviewSourceKey(source) === key);
    const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    if (!summary || !asset?.assetId || !asset.sha256 || !positiveInteger(asset.assetVersion)) return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
      const response = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        "source_get",
        {
          content_id: summary.content_id,
          expected_asset_version: summary.content_version,
          target_kind: summary.target_kind,
          target_digest: summary.target_digest,
          expected_head_version: summary.head_version,
        },
        `mmi-review-source-get-${crypto.randomUUID()}`,
      );
      const output = exactReviewOutput(response, ["source"]);
      const detail = await validatedReviewSource(output.source, {
        contentId: asset.assetId,
        contentVersion: summary.content_version,
        priorSummary: summary,
      });
      assertReviewRequestCurrent(guard);
      if (detail.source_ref.asset_sha256 !== `sha256:${asset.sha256}`) {
        throw new Error("HUMAN_REVIEW_SOURCE_ASSET_DIGEST_INVALID");
      }
      setReviewSources((current) => [
        detail,
        ...current.filter((source) => reviewSourceKey(source) !== key),
      ].sort((left, right) => (
        left.confidence - right.confidence
        || left.target_kind.localeCompare(right.target_kind)
        || left.target_digest.localeCompare(right.target_digest)
      )));
      setReviewTargetKind(detail.target_kind);
      setReviewTargetLocator(canonicalStrictJson(detail.target));
      setReviewOriginalValue(
        detail.target_kind === "TEXT" && typeof detail.original_value === "string"
          ? detail.original_value
          : canonicalStrictJson(detail.original_value),
      );
      setReviewConfidence(String(detail.confidence));
      setFeedback("权威来源详情已载入并绑定当前 asset/snapshot/head；现在可创建审阅任务。");
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        setSelectedReviewSourceKey("");
        setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_SOURCE_GET_FAILED");
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function validatedReviewEnqueueReceipt(
    response: SkillResponse,
    guard: ReviewRequestGuard,
    input: ReviewSourceEnqueueInput,
    outputKeys: readonly string[] = ["task"],
  ): Promise<ReviewTask> {
    exactReviewOutput(response, outputKeys);
    const task = await validatedReviewTask(response, guard, {
      assetId: input.content_id,
      targetKind: input.target_kind,
      state: "QUEUED",
      version: 1,
      correctionVersion: 0,
    });
    assertReviewRequestCurrent(guard);
    const sourceRef = task.source_ref;
    if (
      !task.detail_loaded
      || !sourceRef
      || task.reason !== input.reason
      || task.source_digest !== input.expected_head_value_digest
      || sourceRef.content_version !== input.expected_asset_version
      || sourceRef.target_digest !== input.target_digest
      || sourceRef.head_version !== input.expected_head_version
      || sourceRef.snapshot_id !== input.expected_snapshot_id
      || sourceRef.snapshot_digest !== input.expected_snapshot_digest
      || sourceRef.head_value_digest !== input.expected_head_value_digest
      || sourceRef.original_value_client_digest !== input.original_value_digest
      || sourceRef.original_value_digest_contract
        !== "sha256:rfc8785-ijson-safeint-v1"
    ) throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
    return task;
  }

  function clearReviewEnqueueAttempt(
    guard: ReviewRequestGuard,
    attempt: ReviewEnqueueAttempt,
  ): void {
    assertReviewRequestCurrent(guard);
    const attempts = loadReviewEnqueueAttempts(guard.identityScope);
    const persisted = attempts[attempt.request_digest];
    if (
      !persisted
      || canonicalStrictJson(persisted) !== canonicalStrictJson(attempt)
    ) throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
    delete attempts[attempt.request_digest];
    if (!persistReviewEnqueueAttempts(guard.identityScope, attempts)) {
      throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CLEAR_FAILED");
    }
    setReviewEnqueueRecoveryCount(Object.values(attempts).filter(
      (candidate) => candidate.project_scope_digest === attempt.project_scope_digest,
    ).length);
    setReviewEnqueueRecoveryError("");
  }

  async function recoverReviewEnqueueAttempts() {
    if (!reviewIdentityScope) {
      setFeedback("HUMAN_REVIEW_IDENTITY_SCOPE_UNAVAILABLE");
      return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    let recovered = 0;
    let safelyCleared = 0;
    try {
      await ensureReviewProject(guard);
      const projectScopeDigest = await reviewProjectScopeDigest(
        guard.identityScope,
        guard.projectId,
      );
      assertReviewRequestCurrent(guard);
      const storedAttempts = loadReviewEnqueueAttempts(guard.identityScope);
      const attempts = Object.values(storedAttempts).filter(
        (attempt) => attempt.project_scope_digest === projectScopeDigest,
      ).sort((left, right) => (
        left.created_at - right.created_at
        || left.request_digest.localeCompare(right.request_digest)
      ));
      if (attempts.length === 0) {
        setReviewEnqueueRecoveryCount(0);
        setReviewEnqueueRecoveryError("");
        setFeedback("当前项目没有待恢复的审阅入队请求。");
        return;
      }
      for (const attempt of attempts) {
        assertReviewRequestCurrent(guard);
        if (attempt.project_scope_digest !== projectScopeDigest) {
          throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
        }
        const response = await executeGuardedReviewSkill(
          guard,
          "elmos-human-review-and-correction",
          "enqueue_execute",
          { recovery_handle: attempt.recovery_handle },
          attempt.execute_idempotency_key,
        );
        if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT") {
          const output = exactReviewOutput(response, ["preparation"]);
          if (!exactReviewEnqueuePreparationAbsence(output.preparation, attempt)) {
            throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
          }
          clearReviewEnqueueAttempt(guard, attempt);
          safelyCleared += 1;
          continue;
        }
        if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED") {
          const output = exactReviewOutput(response, ["preparation"]);
          await validatedReviewEnqueuePreparation(
            output.preparation,
            attempt,
            new Set<"PREPARED" | "EXECUTED" | "EXPIRED">(["EXPIRED"]),
          );
          assertReviewRequestCurrent(guard);
          clearReviewEnqueueAttempt(guard, attempt);
          safelyCleared += 1;
          continue;
        }
        if (response.code !== "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION") {
          throw new Error("HUMAN_REVIEW_ENQUEUE_EXECUTE_RESPONSE_INVALID");
        }
        const output = exactReviewOutput(response, ["preparation", "task"]);
        const { preparation, input } = await validatedReviewEnqueuePreparation(
          output.preparation,
          attempt,
          new Set<"PREPARED" | "EXECUTED" | "EXPIRED">(["EXECUTED"]),
        );
        assertReviewRequestCurrent(guard);
        const receiptTask = await validatedReviewEnqueueReceipt(
          response,
          guard,
          input,
          ["preparation", "task"],
        );
        if (preparation.task_id !== receiptTask.task_id) {
          throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
        }
        clearReviewEnqueueAttempt(guard, attempt);
        const currentResponse = await executeGuardedReviewSkill(
          guard,
          "elmos-human-review-and-correction",
          "get",
          { task_id: receiptTask.task_id },
          `mmi-review-get-${receiptTask.task_id}-${receiptTask.version}-${crypto.randomUUID()}`,
        );
        exactReviewOutput(currentResponse, ["task"]);
        const currentTask = await validatedReviewTask(currentResponse, guard, {
          priorTask: receiptTask,
          taskId: receiptTask.task_id,
          assetId: input.content_id,
          targetKind: input.target_kind,
          minimumVersion: receiptTask.version,
        });
        commitReviewTask(currentTask);
        recovered += 1;
      }
      setFeedback(
        `审阅入队恢复完成：${recovered} 个已提交任务载入权威当前状态，${safelyCleared} 个明确未执行或已过期句柄已清理。`,
      );
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        await updateReviewEnqueueRecoveryState(guard.identityScope, guard.projectId);
        setFeedback(
          error instanceof Error
            ? error.message
            : "HUMAN_REVIEW_ENQUEUE_RECOVERY_FAILED",
        );
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function enqueueReviewTask() {
    const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    const selectedSource = reviewSources.find((source) => (
      reviewSourceKey(source) === selectedReviewSourceKey && source.detail_loaded
    ));
    const confidence = selectedSource?.confidence;
    const enqueueReason = reviewReason.trim();
    if (
      !reviewIdentityScope
      || !asset?.assetId
      || !asset.sha256
      || !positiveInteger(asset.assetVersion)
      || !selectedSource
      || selectedSource.content_id !== asset.assetId
      || selectedSource.content_version !== asset.assetVersion
      || selectedSource.source_ref.asset_sha256 !== `sha256:${asset.sha256}`
      || typeof confidence !== "number"
      || !Number.isFinite(confidence)
      || confidence < 0
      || confidence > 1
      || !exactRequiredText(enqueueReason, 2_000)
    ) {
      setFeedback("HUMAN_REVIEW_ENQUEUE_INPUT_INVALID");
      return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
      const target = selectedSource.target;
      const originalValue = selectedSource.original_value;
      const sourceRef = selectedSource.source_ref;
      await ensureReviewProject(guard);
      const originalValueClientDigest = `sha256:${await sha256(
        new TextEncoder().encode(canonicalStrictJson(originalValue)).buffer,
      )}`;
      assertReviewRequestCurrent(guard);
      if (
        originalValueClientDigest !== selectedSource.original_value_client_digest
        || sourceRef.original_value_client_digest !== originalValueClientDigest
      ) throw new Error("HUMAN_REVIEW_SOURCE_VALUE_DIGEST_INVALID");
      const enqueueInput: ReviewSourceEnqueueInput = {
        content_id: asset.assetId,
        expected_asset_version: asset.assetVersion,
        target_kind: selectedSource.target_kind,
        target_digest: selectedSource.target_digest,
        original_value_digest: originalValueClientDigest,
        reason: enqueueReason,
        expected_head_version: selectedSource.head_version,
        expected_snapshot_id: sourceRef.snapshot_id as string,
        expected_snapshot_digest: sourceRef.snapshot_digest as string,
        expected_head_value_digest: sourceRef.head_value_digest as string,
      };
      const enqueueRequestDigest = await reviewEnqueueRequestDigest(enqueueInput);
      const projectScopeDigest = await reviewProjectScopeDigest(
        guard.identityScope,
        guard.projectId,
      );
      assertReviewRequestCurrent(guard);
      const storedAttempts = loadReviewEnqueueAttempts(guard.identityScope);
      let enqueueAttempt = storedAttempts[enqueueRequestDigest];
      const recoveringUnknown = enqueueAttempt !== undefined;
      if (!enqueueAttempt) {
        if (Object.values(storedAttempts).some(
          (attempt) => attempt.project_scope_digest === projectScopeDigest,
        )) {
          throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_REQUIRED");
        }
        if (Object.keys(storedAttempts).length >= maximumStoredReviewEnqueueAttempts) {
          throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_LIMIT_EXCEEDED");
        }
        enqueueAttempt = {
          schema_version: 3,
          identity_scope: guard.identityScope,
          project_scope_digest: projectScopeDigest,
          request_digest: enqueueRequestDigest,
          recovery_handle: `mmi-review-recovery-${crypto.randomUUID()}`,
          prepare_idempotency_key: `mmi-review-enqueue-prepare-${crypto.randomUUID()}`,
          execute_idempotency_key: `mmi-review-enqueue-execute-${crypto.randomUUID()}`,
          created_at: Date.now(),
        };
        if (!persistReviewEnqueueAttempts(guard.identityScope, {
          ...storedAttempts,
          [enqueueRequestDigest]: enqueueAttempt,
        })) {
          throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_UNAVAILABLE");
        }
        setReviewEnqueueRecoveryCount(Object.values(storedAttempts).filter(
          (attempt) => attempt.project_scope_digest === projectScopeDigest,
        ).length + 1);
        setReviewEnqueueRecoveryError("");
      }
      if (
        enqueueAttempt.project_scope_digest !== projectScopeDigest
        || enqueueAttempt.request_digest !== enqueueRequestDigest
      ) {
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
      }
      if (!recoveringUnknown) {
        const preparedResponse = await executeGuardedReviewSkill(
          guard,
          "elmos-human-review-and-correction",
          "enqueue_prepare",
          {
            recovery_handle: enqueueAttempt.recovery_handle,
            execute_idempotency_key: enqueueAttempt.execute_idempotency_key,
            ...enqueueInput,
          },
          enqueueAttempt.prepare_idempotency_key,
        );
        if (preparedResponse.code !== "HUMAN_REVIEW_ENQUEUE_PREPARED") {
          throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARE_RESPONSE_INVALID");
        }
        const preparedOutput = exactReviewOutput(preparedResponse, ["preparation"]);
        const prepared = await validatedReviewEnqueuePreparation(
          preparedOutput.preparation,
          enqueueAttempt,
          new Set<"PREPARED" | "EXECUTED" | "EXPIRED">(["PREPARED"]),
        );
        assertReviewRequestCurrent(guard);
        if (canonicalStrictJson(prepared.input) !== canonicalStrictJson(enqueueInput)) {
          throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_BINDING_INVALID");
        }
      }
      const response = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        "enqueue_execute",
        { recovery_handle: enqueueAttempt.recovery_handle },
        enqueueAttempt.execute_idempotency_key,
      );
      if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT") {
        const output = exactReviewOutput(response, ["preparation"]);
        if (!exactReviewEnqueuePreparationAbsence(output.preparation, enqueueAttempt)) {
          throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
        }
        clearReviewEnqueueAttempt(guard, enqueueAttempt);
        throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT_RETRY_REQUIRED");
      }
      if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED") {
        const output = exactReviewOutput(response, ["preparation"]);
        await validatedReviewEnqueuePreparation(
          output.preparation,
          enqueueAttempt,
          new Set<"PREPARED" | "EXECUTED" | "EXPIRED">(["EXPIRED"]),
        );
        assertReviewRequestCurrent(guard);
        clearReviewEnqueueAttempt(guard, enqueueAttempt);
        throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED_RETRY_REQUIRED");
      }
      if (response.code !== "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION") {
        throw new Error("HUMAN_REVIEW_ENQUEUE_EXECUTE_RESPONSE_INVALID");
      }
      const output = exactReviewOutput(response, ["preparation", "task"]);
      const executed = await validatedReviewEnqueuePreparation(
        output.preparation,
        enqueueAttempt,
        new Set<"PREPARED" | "EXECUTED" | "EXPIRED">(["EXECUTED"]),
      );
      assertReviewRequestCurrent(guard);
      if (canonicalStrictJson(executed.input) !== canonicalStrictJson(enqueueInput)) {
        throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_BINDING_INVALID");
      }
      const receiptTask = await validatedReviewEnqueueReceipt(
        response,
        guard,
        executed.input,
        ["preparation", "task"],
      );
      if (executed.preparation.task_id !== receiptTask.task_id) {
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
      }
      clearReviewEnqueueAttempt(guard, enqueueAttempt);
      assertReviewRequestCurrent(guard);
      if (
        !receiptTask.target
        || canonicalStrictJson(receiptTask.target) !== canonicalStrictJson(target)
        || canonicalStrictJson(receiptTask.original_value) !== canonicalStrictJson(originalValue)
        || receiptTask.confidence !== confidence
        || receiptTask.reason !== enqueueReason
        || receiptTask.source_ref?.content_version !== asset.assetVersion
        || receiptTask.source_ref?.asset_sha256 !== `sha256:${asset.sha256}`
        || receiptTask.source_ref?.original_value_client_digest !== originalValueClientDigest
        || receiptTask.source_ref?.original_value_digest_contract
          !== "sha256:rfc8785-ijson-safeint-v1"
        || receiptTask.source_digest !== sourceRef.head_value_digest
        || canonicalStrictJson(receiptTask.source_ref) !== canonicalStrictJson(sourceRef)
      ) throw new Error("HUMAN_REVIEW_SOURCE_RESPONSE_BINDING_INVALID");
      const currentResponse = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        "get",
        { task_id: receiptTask.task_id },
        `mmi-review-get-${receiptTask.task_id}-${receiptTask.version}`,
      );
      exactReviewOutput(currentResponse, ["task"]);
      const currentTask = await validatedReviewTask(currentResponse, guard, {
        priorTask: receiptTask,
        taskId: receiptTask.task_id,
        assetId: asset.assetId,
        targetKind: selectedSource.target_kind,
        target,
        originalValue,
        bindOriginalValue: true,
        minimumVersion: receiptTask.version,
      });
      assertReviewRequestCurrent(guard);
      commitReviewTask(currentTask);
      setFeedback(recoveringUnknown
        ? `审阅任务 ${currentTask.task_id} 的未知结果已精确恢复；当前权威状态已载入。`
        : `审阅任务 ${currentTask.task_id} 已排队；原始资产保持不变。`);
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        await updateReviewEnqueueRecoveryState(guard.identityScope, guard.projectId);
        setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_ENQUEUE_FAILED");
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function claimReviewTask() {
    const task = selectedReviewTask();
    if (!task || !reviewIdentityScope) {
      setFeedback("HUMAN_REVIEW_IDENTITY_SCOPE_UNAVAILABLE");
      return;
    }
    const storedClaim = reviewClaims[task.task_id];
    const recoverable = storedClaim
      && storedClaim.project_id === projectId
      && validReviewClaim(storedClaim, reviewIdentityScope)
      ? storedClaim
      : undefined;
    if (storedClaim && !recoverable && !discardReviewClaim(task.task_id)) {
      setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED");
      return;
    }
    if (recoverable?.fence !== undefined && validReviewClaim(recoverable, reviewIdentityScope)) {
      setFeedback(`审阅任务 ${task.task_id} 的领取凭证仍有效。`);
      return;
    }
    const attempt: ReviewClaim = recoverable
      ? recoverable
      : {
          schema_version: 2,
          identity_scope: reviewIdentityScope,
          project_id: projectId,
          task_id: task.task_id,
          token: `review-claim:${crypto.randomUUID()}:${crypto.randomUUID()}`,
          idempotency_key: `mmi-review-claim-${task.task_id}-${crypto.randomUUID()}`,
          expected_version: task.version,
          created_at: Date.now(),
        };
    const guard = beginReviewRequest();
    if (!saveReviewClaim(attempt)) {
      setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_UNAVAILABLE");
      finishReviewRequest(guard);
      return;
    }
    setFeedback("");
    try {
      const response = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        "claim",
        {
          task_id: task.task_id,
          expected_version: attempt.expected_version,
          claim_token: attempt.token,
          lease_seconds: reviewClaimLeaseSeconds,
        },
        attempt.idempotency_key,
      );
      exactReviewOutput(response, ["task"]);
      const observedCommittedReplay = recoverable?.fence === undefined
        && task.version === attempt.expected_version + 1
        && ["CLAIMED", "EDITED"].includes(task.state)
        && task.claim_fence !== undefined;
      const claimed = await validatedReviewTask(response, guard, {
        priorTask: task,
        taskId: task.task_id,
        assetId: task.asset_id,
        state: task.state === "EDITED" ? "EDITED" : "CLAIMED",
        version: attempt.expected_version + 1,
        correctionVersion: task.current_correction_version,
        claimFence: observedCommittedReplay
          ? task.claim_fence
          : (task.claim_fence ?? 0) + 1,
      });
      assertReviewRequestCurrent(guard);
      if (
        !claimed.claim_fence
        || !claimed.claim_expires_at
        || Date.parse(claimed.claim_expires_at) <= Date.now()
        || claimed.current_correction_digest !== task.current_correction_digest
        || claimed.effective_version !== task.effective_version
        || claimed.effective_digest !== task.effective_digest
        || observedCommittedReplay && claimed.claim_expires_at !== task.claim_expires_at
        || account.status === "authenticated"
          && claimed.claim_actor_id !== account.principal?.actorId
      ) {
        throw new Error("HUMAN_REVIEW_CLAIM_FENCE_MISSING");
      }
      const completedClaim: ReviewClaim = {
        ...attempt,
        fence: claimed.claim_fence,
        expires_at: claimed.claim_expires_at,
      };
      if (!validReviewClaim(completedClaim, reviewIdentityScope) || !saveReviewClaim(completedClaim)) {
        throw new Error("HUMAN_REVIEW_CLAIM_RECOVERY_UNAVAILABLE");
      }
      assertReviewRequestCurrent(guard);
      commitReviewTask(claimed);
      setFeedback(`审阅任务 ${task.task_id} 已领取；租约写入持久状态。`);
    } catch (error) {
      if (!reviewRequestIsCurrent(guard)) return;
      const failure = failureDetails(error, "HUMAN_REVIEW_CLAIM_FAILED");
      if ([
        "HUMAN_REVIEW_CLAIM_REPLAY_STALE",
        "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
        "HUMAN_REVIEW_TASK_ALREADY_CLAIMED",
        "HUMAN_REVIEW_TASK_NOT_CLAIMABLE",
      ].includes(failure.code)) {
        if (discardReviewClaim(task.task_id)) {
          setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
          setSelectedReviewTaskId("");
          setFeedback(`${failure.code}；本地领取恢复已清除，请刷新队列后重试。`);
        } else {
          setFeedback(`${failure.code}；HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
        }
      } else {
        setFeedback(failure.code);
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  function correctionValue(): unknown {
    if (!correctionTouched) throw new Error("HUMAN_REVIEW_CORRECTION_REQUIRED");
    if (selectedReviewTask()?.target_kind === "TEXT") return correction;
    try {
      return parseStrictJson(correction);
    } catch (error) {
      if (error instanceof StrictJsonError) {
        throw new Error(`HUMAN_REVIEW_CORRECTION_${error.code}`);
      }
      throw error;
    }
  }

  async function editReviewTask() {
    const task = selectedReviewTask();
    const claim = task ? reviewClaims[task.task_id] : undefined;
    if (
      !task || !claim || claim.fence === undefined
      || !validReviewClaim(claim, reviewIdentityScope)
      || !exactRequiredText(reviewReason.trim(), 2_000)
    ) {
      setFeedback("HUMAN_REVIEW_TASK_CLAIM_REQUIRED");
      return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
      const correctedValue = correctionValue();
      const correctionReason = reviewReason.trim();
      const editInput = {
        task_id: task.task_id,
        expected_version: task.version,
        expected_correction_version: task.current_correction_version,
        claim_token: claim.token,
        claim_fence: claim.fence,
        correction: { value: correctedValue, reason: correctionReason },
      };
      const editDigest = await sha256(
        new TextEncoder().encode(canonicalStrictJson(editInput)).buffer,
      );
      assertReviewRequestCurrent(guard);
      const response = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        "edit",
        editInput,
        `mmi-review-edit-${editDigest}`,
      );
      const editOutput = exactReviewOutput(response, ["correction", "task"]);
      const edited = await validatedReviewTask(response, guard, {
        priorTask: task,
        taskId: task.task_id,
        assetId: task.asset_id,
        state: "EDITED",
        version: task.version + 1,
        correctionVersion: task.current_correction_version + 1,
        claimFence: claim.fence,
      });
      assertReviewRequestCurrent(guard);
      if (
        edited.claim_actor_id !== task.claim_actor_id
        || edited.claim_expires_at !== task.claim_expires_at
        || edited.effective_version !== task.effective_version
        || edited.effective_digest !== task.effective_digest
        || !exactReviewCorrection(
          editOutput.correction,
          task,
          edited,
          correctedValue,
          correctionReason,
        )
      ) throw new Error("HUMAN_REVIEW_CORRECTION_RESPONSE_BINDING_INVALID");
      commitReviewTask(edited);
      setReviewCurrentCorrection(editOutput.correction as Record<string, unknown>);
      setCorrection("");
      setCorrectionTouched(false);
      setFeedback(`审阅任务 ${edited.task_id} 已创建不可变纠正版本，等待批准或拒绝。`);
    } catch (error) {
      if (!reviewRequestIsCurrent(guard)) return;
      const failure = failureDetails(error, "HUMAN_REVIEW_EDIT_FAILED");
      if ([
        "HUMAN_REVIEW_CLAIM_NOT_OWNED",
        "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
      ].includes(failure.code) && discardReviewClaim(task.task_id)) {
        setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
        setSelectedReviewTaskId("");
        setFeedback(`${failure.code}；旧身份或任务版本的领取凭证已清除，请刷新队列。`);
      } else {
        setFeedback(failure.code);
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function decideReviewTask(operation: "approve" | "reject") {
    const task = selectedReviewTask();
    const claim = task ? reviewClaims[task.task_id] : undefined;
    const visibleCorrection = task && reviewCurrentCorrection
      && exactCurrentReviewCorrection(reviewCurrentCorrection, task)
      ? reviewCurrentCorrection
      : undefined;
    if (
      !task
      || !claim
      || claim.fence === undefined
      || !validReviewClaim(claim, reviewIdentityScope)
      || !exactRequiredText(reviewReason.trim(), 2_000)
      || operation === "approve" && task.state !== "EDITED"
      || task.current_correction_version > 0 && visibleCorrection === undefined
    ) {
      setFeedback("HUMAN_REVIEW_TASK_CLAIM_REQUIRED");
      return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
      const authoritativeCorrection = await fetchCurrentReviewCorrection(guard, task);
      assertReviewRequestCurrent(guard);
      if (
        canonicalStrictJson(authoritativeCorrection ?? null)
          !== canonicalStrictJson(visibleCorrection ?? null)
      ) {
        setReviewCurrentCorrection(authoritativeCorrection ?? null);
        throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_CHANGED_REVIEW_REQUIRED");
      }
      const decisionReason = reviewReason.trim();
      const decisionInput = {
        task_id: task.task_id,
        expected_version: task.version,
        claim_token: claim.token,
        claim_fence: claim.fence,
        reason: decisionReason,
      };
      const decisionDigest = await sha256(
        new TextEncoder().encode(canonicalStrictJson(decisionInput)).buffer,
      );
      assertReviewRequestCurrent(guard);
      const response = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        operation,
        decisionInput,
        `mmi-review-${operation}-${decisionDigest}`,
      );
      const decisionOutput = exactReviewOutput(response, ["decision", "propagations", "task"]);
      const decisionDocument = decisionOutput.decision;
      const propagations = decisionOutput.propagations;
      const decided = await validatedReviewTask(response, guard, {
        priorTask: task,
        taskId: task.task_id,
        assetId: task.asset_id,
        state: operation === "approve" ? "APPROVED" : "REJECTED",
        version: task.version + 1,
        correctionVersion: task.current_correction_version,
        claimFence: claim.fence,
      });
      assertReviewRequestCurrent(guard);
      const trustedActorId = account.status === "authenticated"
        ? account.principal?.actorId
        : undefined;
      if (
        !exactReviewDecision(
          decisionDocument,
          task,
          decided,
          operation,
          decisionReason,
          authoritativeCorrection,
          trustedActorId,
        )
        || decided.current_correction_digest !== task.current_correction_digest
        || decided.effective_version !== task.effective_version
        || decided.effective_digest !== task.effective_digest
        || operation === "approve" && !validReviewPropagations(
          propagations,
          task.task_id,
          {
            exactBatch: true,
            direction: "APPLY",
            decisionId: decisionDocument.decision_id as string,
            correctionVersion: task.current_correction_version,
            initial: true,
          },
        )
        || operation === "reject" && (!Array.isArray(propagations) || propagations.length !== 0)
      ) throw new Error("HUMAN_REVIEW_DECISION_RESPONSE_BINDING_INVALID");
      commitReviewTask(decided);
      const discarded = discardReviewClaim(task.task_id);
      setReviewPropagation(operation === "approve" ? response : null);
      const message = operation === "approve"
        ? `审阅任务 ${decided.task_id} 已批准；四个派生传播任务已持久排队。`
        : `审阅任务 ${decided.task_id} 已拒绝；纠正历史仍保留。`;
      setFeedback(discarded ? message : `${message} HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
    } catch (error) {
      if (!reviewRequestIsCurrent(guard)) return;
      const failure = failureDetails(error, `HUMAN_REVIEW_${operation.toUpperCase()}_FAILED`);
      if ([
        "HUMAN_REVIEW_CLAIM_NOT_OWNED",
        "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
      ].includes(failure.code) && discardReviewClaim(task.task_id)) {
        setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
        setSelectedReviewTaskId("");
        setFeedback(`${failure.code}；旧身份或任务版本的领取凭证已清除，请刷新队列。`);
      } else {
        setFeedback(failure.code);
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function transitionClosedReviewTask(operation: "reopen" | "revert") {
    const task = selectedReviewTask();
    const visibleCorrection = task && reviewCurrentCorrection
      && exactCurrentReviewCorrection(reviewCurrentCorrection, task)
      ? reviewCurrentCorrection
      : undefined;
    if (
      !task
      || !exactRequiredText(reviewReason.trim(), 2_000)
      || task.current_correction_version > 0 && visibleCorrection === undefined
    ) return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
      const authoritativeCorrection = await fetchCurrentReviewCorrection(guard, task);
      assertReviewRequestCurrent(guard);
      if (
        canonicalStrictJson(authoritativeCorrection ?? null)
          !== canonicalStrictJson(visibleCorrection ?? null)
      ) {
        setReviewCurrentCorrection(authoritativeCorrection ?? null);
        throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_CHANGED_REVIEW_REQUIRED");
      }
      const transitionReason = reviewReason.trim();
      const transitionInput = {
        task_id: task.task_id,
        expected_version: task.version,
        reason: transitionReason,
      };
      const transitionDigest = await sha256(
        new TextEncoder().encode(canonicalStrictJson(transitionInput)).buffer,
      );
      assertReviewRequestCurrent(guard);
      const response = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        operation,
        transitionInput,
        `mmi-review-${operation}-${transitionDigest}`,
      );
      const transitionOutput = exactReviewOutput(response, ["decision", "propagations", "task"]);
      const transitionDecision = transitionOutput.decision;
      const transitionPropagations = transitionOutput.propagations;
      const transitioned = await validatedReviewTask(response, guard, {
        priorTask: task,
        taskId: task.task_id,
        assetId: task.asset_id,
        state: operation === "revert" ? "REVERTING" : "REOPENED",
        version: task.version + 1,
        correctionVersion: task.current_correction_version,
        claimFence: task.claim_fence,
      });
      assertReviewRequestCurrent(guard);
      const trustedActorId = account.status === "authenticated"
        ? account.principal?.actorId
        : undefined;
      if (
        !exactReviewDecision(
          transitionDecision,
          task,
          transitioned,
          operation,
          transitionReason,
          authoritativeCorrection,
          trustedActorId,
        )
        || transitioned.current_correction_digest !== task.current_correction_digest
        || transitioned.effective_version !== task.effective_version
        || transitioned.effective_digest !== task.effective_digest
        || operation === "revert" && !validReviewPropagations(
          transitionPropagations,
          task.task_id,
          {
            exactBatch: true,
            direction: "REVERT",
            decisionId: transitionDecision.decision_id as string,
            correctionVersion: task.current_correction_version,
            initial: true,
          },
        )
        || operation === "reopen" && (
          !Array.isArray(transitionPropagations) || transitionPropagations.length !== 0
        )
      ) throw new Error("HUMAN_REVIEW_DECISION_RESPONSE_BINDING_INVALID");
      commitReviewTask(transitioned);
      const discarded = discardReviewClaim(task.task_id);
      setReviewPropagation(operation === "revert" ? response : null);
      const message = operation === "revert"
        ? `审阅任务 ${transitioned.task_id} 已进入可审计回退传播。`
        : `审阅任务 ${transitioned.task_id} 已重新打开。`;
      setFeedback(discarded ? message : `${message} HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        setFeedback(error instanceof Error ? error.message : `HUMAN_REVIEW_${operation.toUpperCase()}_FAILED`);
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function refreshReviewPropagation() {
    const task = selectedReviewTask();
    if (!task) return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
      const response = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        "propagation_status",
        { task_id: task.task_id },
        `mmi-review-propagation-${task.task_id}-${crypto.randomUUID()}`,
      );
      const statusOutput = exactReviewOutput(response, ["effective", "propagations", "task"]);
      const statusTask = await validatedReviewTask(response, guard, {
        priorTask: task,
        taskId: task.task_id,
        assetId: task.asset_id,
        minimumVersion: task.version,
      });
      assertReviewRequestCurrent(guard);
      if (!validHistoricalPropagationBatches(statusOutput.propagations, task.task_id)) {
        throw new Error("HUMAN_REVIEW_PROPAGATION_RESPONSE_BINDING_INVALID");
      }
      if (!exactReviewEffective(
        statusOutput.effective,
        statusTask,
        statusOutput.propagations,
      )) {
        throw new Error("HUMAN_REVIEW_EFFECTIVE_RESPONSE_INVALID");
      }
      commitReviewTask(statusTask);
      setReviewPropagation(response);
      setFeedback(`审阅任务 ${task.task_id} 的传播状态已刷新。`);
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_PROPAGATION_STATUS_FAILED");
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  async function submitCorrection() {
    const target = assets.find((asset) => asset.assetId === correctionTarget);
    if (!target || !correctionTouched) return;
    const currentVersion = target.assetVersion;
    if (!currentVersion) {
      setFeedback("ASSET_VERSION_REQUIRED_FOR_CORRECTION");
      return;
    }
    let identityGuard: IntakeIdentityGuard;
    try {
      identityGuard = captureIntakeIdentity();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
      return;
    }
    const guard = beginReviewRequest();
    try {
      const correctionInput = {
        content_id: target.assetId,
        expected_version: currentVersion,
        value: correction,
        reason: "USER_REVIEW",
      };
      const correctionDigest = await sha256(
        new TextEncoder().encode(canonicalStrictJson(correctionInput)).buffer,
      );
      assertReviewRequestCurrent(guard);
      const response = await executeGuardedReviewSkill(
        guard,
        "elmos-human-review-and-correction",
        "correct",
        correctionInput,
        `mmi-correction-${correctionDigest}`,
      );
      const corrected = outputRecord(response, "correction");
      const persistedAssetStatus = responseString(response, "asset_status");
      const correctedPhase = persistedAssetStatus
        ? phaseFrom({ status: persistedAssetStatus })
        : phaseFrom(response);
      update(target.key, {
        phase: correctedPhase,
        response,
        code: undefined,
        recoveryAttached: !["READY", "QUARANTINED"].includes(correctedPhase),
        assetVersion: positiveInteger(corrected?.version) ?? currentVersion,
      });
      setCorrection("");
      setCorrectionTouched(false);
      if (["READY", "QUARANTINED"].includes(correctedPhase) && target.projectId && target.engineProjectId) {
        try {
          await clearRecovery(target, identityGuard);
          assertReviewRequestCurrent(guard);
        } catch {
          if (reviewRequestIsCurrent(guard)) {
            setFeedback("CORRECTION_APPLIED_RECOVERY_CLEANUP_FAILED");
          }
          return;
        }
      }
      setFeedback("纠错版本已提交；原始资产未被覆盖。");
    } catch (error) {
      if (reviewRequestIsCurrent(guard)) {
        setFeedback(error instanceof Error ? error.message : "CORRECTION_FAILED");
      }
    } finally {
      finishReviewRequest(guard);
    }
  }

  const activeReviewSource = reviewSources.find((source) => (
    reviewSourceKey(source) === selectedReviewSourceKey
  ));
  const activeReviewTask = selectedReviewTask();
  const storedActiveReviewClaim = activeReviewTask
    ? reviewClaims[activeReviewTask.task_id]
    : undefined;
  const activeReviewClaimAttempt = storedActiveReviewClaim
    && storedActiveReviewClaim.project_id === projectId
    && validReviewClaim(storedActiveReviewClaim, reviewIdentityScope)
    ? storedActiveReviewClaim
    : undefined;
  const activeReviewClaim = activeReviewClaimAttempt
    && activeReviewClaimAttempt.fence !== undefined
    && validReviewClaim(activeReviewClaimAttempt, reviewIdentityScope)
    && activeReviewTask
    && ["CLAIMED", "EDITED"].includes(activeReviewTask.state)
    && activeReviewTask.claim_fence === activeReviewClaimAttempt.fence
    && activeReviewTask.claim_expires_at === activeReviewClaimAttempt.expires_at
    ? activeReviewClaimAttempt
    : undefined;
  const activePendingReviewClaim = activeReviewClaimAttempt?.fence === undefined
    ? activeReviewClaimAttempt
    : undefined;
  const activeReviewTaskClaimable = Boolean(activeReviewTask && (
    ["QUEUED", "REOPENED"].includes(activeReviewTask.state)
    || ["CLAIMED", "EDITED"].includes(activeReviewTask.state)
      && Boolean(activeReviewTask.claim_expires_at)
      && Date.parse(activeReviewTask.claim_expires_at as string) <= Date.now()
  ));
  const activeReviewCorrection = activeReviewTask && reviewCurrentCorrection
    && exactCurrentReviewCorrection(reviewCurrentCorrection, activeReviewTask)
    ? reviewCurrentCorrection
    : undefined;

  return (
    <div className={styles.page} data-testid="multimodal-intake-workbench">
      <header className={styles.header}>
        <div>
          <span className={styles.overline}>MULTIMODAL INTAKE · V1</span>
          <h1>把原始资料变成可追溯的项目上下文</h1>
          <p>文本、音频、图片、PDF、Word、文件夹与归档统一进入校验、隔离、解析、来源锚点和持久任务链。</p>
        </div>
        <div className={styles.headerStatus}>
          <StatusChip status="CODE_IMPLEMENTED_LOCAL" />
          <StatusChip status="NOT_RUN" />
          <span>外部 OCR / ASR / AV / 强隔离证据</span>
        </div>
      </header>

      <section className={styles.boundary} aria-label="安全边界">
        <strong>输入内容始终是不可信数据</strong>
        <span>不会执行宏、脚本、安装钩子、Dockerfile 或项目代码；能力不可用时明确阻断，不以空文本冒充成功。</span>
      </section>

      <div className={styles.layout}>
        <section className={styles.panel}>
          <div className={styles.sectionHeading}>
            <div><span>01 · SESSION</span><h2>创建输入会话</h2></div>
            <StatusChip status={busy ? "PROCESSING" : "READY"} />
          </div>
          <label className={styles.field}>
            <span>项目 ID</span>
            <input
              value={projectId}
              onChange={(event) => {
                activeProjectId.current = event.target.value;
                intakeProjectGeneration.current += 1;
                setProjectId(event.target.value);
              }}
              maxLength={128}
              disabled={busy || reviewBusy || projectLocked}
            />
            <small>这是项目别名；服务端按可信租户与身份派生隔离 ID。创建接入句柄后将锁定，避免资产跨项目混用。</small>
          </label>

          <section className={styles.boundary} aria-label="可恢复上传记录" aria-live="polite">
            <strong>
              {recoveryStoreError
                ? `恢复存储不可用：${recoveryStoreError}`
                : recoveryRecordCount > 0
                  ? `发现 ${recoveryRecordCount} 条待 BFF 作用域复核的本地恢复记录`
                  : recoveryStoreReady
                    ? "没有遗留的可恢复上传记录"
                    : "正在检查可恢复上传记录…"}
            </strong>
            <span>
              本地仅保存 SHA-256 指纹、浏览器项目别名、BFF 派生的 opaque 项目作用域、已确认分片进度、幂等 attempt 和服务端 opaque handle；
              不保存 tenant、actor、File、Blob、原文或明文相对路径。重新选择文件后，BFF bootstrap 作用域匹配前不会展示或使用恢复详情与句柄。
            </span>
            {recoveryRecordCount > 0 && <small>恢复详情已隐藏；重新选择匹配文件后由 BFF 重新验证可信作用域。</small>}
            {legacyRecoveryCount > 0 && <small>已清理 {legacyRecoveryCount} 条旧版或无效遗留记录。</small>}
          </section>

          <div className={styles.directInput}>
            <label className={styles.field}>
              <span>直接文本 / Markdown</span>
              <textarea
                value={directText}
                onChange={(event) => setDirectText(event.target.value)}
                placeholder="粘贴需求、会议纪要或日志片段；其中的指令只会作为数据处理。"
                maxLength={200_000}
              />
            </label>
            <button className="button button-secondary" type="button" onClick={addDirectText} disabled={!directText.trim() || busy || !recoveryStoreReady}>加入会话</button>
          </div>

          <div
            className={styles.dropzone}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => { event.preventDefault(); void addFiles(event.dataTransfer.files); }}
          >
            <strong>拖入文件，或选择文件 / 文件夹</strong>
            <span>保留相对路径，不上传本机绝对路径。当前端到端处理硬上限为单文件 64 MiB；超限文件会在读取和上传前永久阻断。</span>
            <div>
              <button className="button button-secondary" type="button" onClick={() => fileInput.current?.click()} disabled={busy || !recoveryStoreReady}>选择文件</button>
              <button className="button button-secondary" type="button" onClick={() => folderInput.current?.click()} disabled={busy || !recoveryStoreReady}>选择文件夹</button>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => { if (microphone.recording) microphone.stop(); else void microphone.start(); }}
                disabled={busy || !recoveryStoreReady || microphone.permission === "DENIED" || microphone.permission === "UNAVAILABLE"}
              >
                {microphone.recording ? "停止录音" : "允许并开始录音"}
              </button>
            </div>
            <small>麦克风只在点击后请求浏览器权限；录音在本机编码为 WAV，达到 10 分钟或 64 MiB 上限会停止，轨道也会在离开页面时关闭。权限：{microphone.permission}</small>
            <input
              ref={fileInput}
              hidden
              type="file"
              multiple
              onChange={(event) => {
                void addFiles(event.target.files ?? []);
                event.currentTarget.value = "";
              }}
            />
            <input
              ref={folderInput}
              hidden
              type="file"
              multiple
              {...{ webkitdirectory: "" }}
              onChange={(event) => {
                void addFiles(event.target.files ?? []);
                event.currentTarget.value = "";
              }}
            />
          </div>

          <div className={styles.assetToolbar}>
            <div>
              <strong>{summary.total} 个条目</strong>
              <span>{(summary.bytes / 1024 / 1024).toFixed(2)} MiB · {summary.ready} READY · {summary.review} 待审阅 · {summary.blocked} 阻断</span>
            </div>
            <button className="button button-primary" type="button" onClick={() => void processAll()} disabled={busy || assets.length === 0 || !recoveryStoreReady}>
              {busy ? "正在处理…" : "安全接入全部"}
            </button>
          </div>

          <section className={styles.estimateBox} aria-label="处理成本与预计耗时" aria-live="polite">
            <div>
              <strong>处理成本 / ETA</strong>
              <span>仅显示机器墙钟时间与受信任价格目录中的估算；provider 实际账单独立对账。</span>
            </div>
            <StatusChip status={estimateBusy ? "PROCESSING" : estimate?.status ?? "NOT_RUN"} compact />
            {estimate?.remainingSecondsP50 !== undefined && estimate.remainingSecondsP95 !== undefined ? (
              <dl>
                <div><dt>P50 剩余</dt><dd>{formatEstimateDuration(estimate.remainingSecondsP50)}</dd></div>
                <div><dt>P95 剩余</dt><dd>{formatEstimateDuration(estimate.remainingSecondsP95)}</dd></div>
                <div><dt>估算成本</dt><dd>{estimate.currency} {estimate.estimatedCost}</dd></div>
                <div><dt>实际值</dt><dd>{estimate.actualsState}</dd></div>
              </dl>
            ) : (
              <small>{estimate?.code ?? "尚未请求估算。若受信任校准或价格目录不可用，服务端会失败关闭。"}</small>
            )}
            {estimate?.code && estimate.remainingSecondsP50 !== undefined && <small>{estimate.code}</small>}
            <button
              className="button button-secondary"
              type="button"
              onClick={() => void refreshProcessingEstimate()}
              disabled={busy || estimateBusy || estimatePlan.stages.length === 0 || !recoveryStoreReady}
            >
              {estimateBusy ? "正在估算…" : "刷新估算"}
            </button>
          </section>

          <div className={styles.assetList} aria-live="polite">
            {assets.length === 0 && <p className={styles.empty}>尚未加入资料。仅受支持格式会进入处理；planned 格式会明确拒绝。</p>}
            {assets.map((asset) => (
              <article className={styles.assetRow} key={asset.key}>
                <div className={styles.assetIdentity}>
                  <strong>{asset.relativePath}</strong>
                  <span>{asset.file.type || "application/octet-stream"} · {asset.file.size.toLocaleString()} bytes</span>
                  {asset.sha256 && <code>sha256:{asset.sha256}</code>}
                  {asset.recoveryCandidate && !asset.recoveryAttached && (
                    <small>发现匹配的恢复候选；BFF 作用域复核前不会使用已存句柄。</small>
                  )}
                  {asset.recoveryAttached && <small>BFF 作用域已验证；重新校验内容后从确认分片继续。</small>}
                </div>
                <div className={styles.assetState}>
                  <StatusChip status={asset.phase} compact />
                  <label className={styles.inlineControl}>
                    <span>资料角色</span>
                    <select
                      value={asset.role}
                      onChange={(event) => {
                        const role = event.target.value as AssetDraft["role"];
                        update(asset.key, { role, modelReadAllowed: role === "IGNORE" ? false : asset.modelReadAllowed });
                      }}
                      disabled={busy || Boolean(asset.sessionId)}
                    >
                      <option value="PRIMARY">主资料</option>
                      <option value="REFERENCE">参考资料</option>
                      <option value="IGNORE">忽略</option>
                    </select>
                  </label>
                  <label className={styles.inlineControl}>
                    <input
                      type="checkbox"
                      checked={asset.modelReadAllowed}
                      onChange={(event) => update(asset.key, { modelReadAllowed: event.target.checked })}
                      disabled={busy || asset.role === "IGNORE" || Boolean(asset.sessionId)}
                    />
                    <span>允许模型读取</span>
                  </label>
                  {!asset.modelReadAllowed && <small>未授权条目仅留在本机预览，不会上传或进入模型处理。</small>}
                  <div
                    className={styles.progress}
                    role="progressbar"
                    aria-label={`${asset.relativePath} 处理进度`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.min(100, Math.max(0, asset.progress))}
                    aria-valuetext={`${asset.phase} · ${Math.min(100, Math.max(0, asset.progress))}%`}
                  >
                    <i
                      aria-hidden="true"
                      style={{ width: `${Math.min(100, Math.max(0, asset.progress))}%` }}
                    />
                  </div>
                  {asset.code && <small>{asset.code}</small>}
                  {asset.traceId && <code>{asset.traceId}</code>}
                </div>
              </article>
            ))}
          </div>

          {feedback && <p className={styles.feedback} role="status">{feedback}</p>}
        </section>

        <aside className={styles.sidePanel}>
          <div className={styles.sectionHeading}>
            <div><span>02 · PACKAGE REVIEW</span><h2>项目包审查</h2></div>
            <StatusChip status={packagePreview ? "REVIEW" : "NOT_RUN"} />
          </div>
          <label className={styles.field}>
            <span>过滤目录树</span>
            <input value={treeQuery} onChange={(event) => setTreeQuery(event.target.value)} placeholder="路径、文件名" />
          </label>
          <div className={styles.tree}>
            {!packagePage && <p>生成安全预览后，目录将按服务端游标分页显示。</p>}
            {filteredPackagePage.map((entry) => (
              <div key={entry.path}>
                <code>{entry.path}</code>
                <span>{entry.security_state} · {entry.role}{entry.model_read_allowed ? " · MODEL READ" : ""}</span>
              </div>
            ))}
            {packagePage && (
              <p>
                服务端第 {packagePageIndex + 1} 页，本页 {packagePage.items.length} 项，
                全部 {packagePage.total.toLocaleString()} 项；过滤仅作用于当前页。
              </p>
            )}
          </div>
          <div className={styles.reviewActions}>
            <button
              className="button button-secondary"
              type="button"
              disabled={busy || !packagePage || packagePageIndex === 0}
              onClick={() => void loadPackagePage(packagePageCursors[packagePageIndex - 1] ?? null, packagePageIndex - 1)}
            >
              上一页
            </button>
            <button
              className="button button-secondary"
              type="button"
              disabled={busy || !packagePage?.next_cursor}
              onClick={() => {
                if (!packagePage?.next_cursor) return;
                const nextIndex = packagePageIndex + 1;
                const cursors = [...packagePageCursors.slice(0, nextIndex), packagePage.next_cursor];
                setPackagePageCursors(cursors);
                void loadPackagePage(packagePage.next_cursor, nextIndex);
              }}
            >
              下一页
            </button>
          </div>
          <button className="button button-secondary" type="button" onClick={() => void buildPackagePreview()} disabled={busy || assets.length === 0}>生成安全预览</button>
          {packagePreview && <pre className={styles.jsonPreview} tabIndex={0}>{JSON.stringify(packagePreview, null, 2)}</pre>}

          <div className={styles.reviewBox}>
            <div className={styles.sectionHeading}>
              <div><span>03 · HUMAN REVIEW</span><h2>审阅队列、纠错与传播</h2></div>
            </div>
            <label className={styles.field}>
              <span>目标资产</span>
              <select
                disabled={busy || reviewBusy}
                value={correctionTarget}
                onChange={(event) => {
                  const nextAssetId = event.target.value;
                  if (nextAssetId !== correctionTarget) {
                    reviewScopeGeneration.current += 1;
                    reviewRequestOwner.current += 1;
                    setReviewBusy(false);
                    setCorrection("");
                    setCorrectionTouched(false);
                    setReviewSources([]);
                    setSelectedReviewSourceKey("");
                    setReviewTargetKind("TEXT");
                    setReviewTargetLocator("");
                    setReviewOriginalValue("");
                    setReviewConfidence("0.5");
                  }
                  setCorrectionTarget(nextAssetId);
                }}
              >
                <option value="">选择已接入资产</option>
                {assets.filter((asset) => asset.assetId).map((asset) => <option value={asset.assetId} key={asset.key}>{asset.relativePath}</option>)}
              </select>
            </label>
            <div className={styles.reviewActions}>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => void refreshReviewSources()}
                disabled={busy || reviewBusy || !correctionTarget}
              >
                刷新权威待审来源
              </button>
            </div>
            <label className={styles.field}>
              <span>权威待审来源（低置信度优先）</span>
              <select
                disabled={busy || reviewBusy || reviewSources.length === 0}
                value={selectedReviewSourceKey}
                onChange={(event) => void selectReviewSource(event.target.value)}
              >
                <option value="">选择 snapshot/head 绑定来源</option>
                {reviewSources.map((source) => (
                  <option value={reviewSourceKey(source)} key={reviewSourceKey(source)}>
                    {source.confidence.toFixed(3)} · {source.target_kind} · {source.head_direction}
                    {" · "}{String(source.target.path ?? source.target_digest)}
                  </option>
                ))}
              </select>
            </label>
            {activeReviewSource?.detail_loaded && (
              <pre className={styles.jsonPreview} tabIndex={0}>{JSON.stringify({
                target: activeReviewSource.target,
                original_value: activeReviewSource.original_value,
                confidence: activeReviewSource.confidence,
                source_ref: activeReviewSource.source_ref,
              }, null, 2)}</pre>
            )}
            <label className={styles.field}>
              <span>{activeReviewTask && activeReviewTask.target_kind !== "TEXT" ? "修正 JSON" : "修正文本"}</span>
              <textarea
                disabled={busy || reviewBusy}
                value={correction}
                onChange={(event) => {
                  setCorrection(event.target.value);
                  setCorrectionTouched(true);
                }}
                placeholder={activeReviewTask && activeReviewTask.target_kind !== "TEXT"
                  ? "输入严格 JSON；说话人、时间段、bbox、表格、需求和冲突均保留类型。"
                  : "修正会创建新版本，不覆盖原始资产。"}
              />
            </label>
            <label className={styles.field}>
              <span>目标类型</span>
              <select
                disabled
                value={reviewTargetKind}
                onChange={(event) => setReviewTargetKind(event.target.value as ReviewTargetKind)}
              >
                <option value="TEXT">文本</option>
                <option value="SPEAKER">说话人</option>
                <option value="TIME_RANGE">时间段</option>
                <option value="BBOX">图像区域 bbox</option>
                <option value="TABLE">表格</option>
                <option value="REQUIREMENT">需求</option>
                <option value="CONFLICT">冲突</option>
              </select>
            </label>
            <label className={styles.field}>
              <span>目标定位 JSON</span>
              <textarea
                disabled={busy || reviewBusy}
                readOnly
                value={reviewTargetLocator}
                placeholder={reviewTargetKind === "TEXT"
                  ? '从权威来源选择器载入，格式如 {"path":"content_blocks/.../text"}'
                  : reviewTargetKind === "SPEAKER"
                    ? '{"segment_id":"segment-1"}'
                    : reviewTargetKind === "TIME_RANGE"
                      ? '{"start_ms":0,"end_ms":1500}'
                      : reviewTargetKind === "BBOX"
                        ? '{"page":1,"x":0,"y":0,"width":100,"height":80}'
                        : reviewTargetKind === "TABLE"
                          ? '{"table_id":"table-1","row":0,"column":0}'
                          : reviewTargetKind === "REQUIREMENT"
                            ? '{"requirement_id":"requirement-1"}'
                            : '{"conflict_id":"conflict-1"}'}
              />
            </label>
            <label className={styles.field}>
              <span>{reviewTargetKind === "TEXT" ? "待审原始文本" : "待审原始值 JSON"}</span>
              <textarea
                disabled={busy || reviewBusy}
                readOnly
                value={reviewOriginalValue}
                placeholder={reviewTargetKind === "TEXT"
                  ? "输入来源中当前可见的原始文本；它会与资产来源摘要一起进入不可变审计历史。"
                  : "输入严格 JSON 的当前原值；纠正与回退不会覆盖原始资产。"}
              />
            </label>
            <label className={styles.field}>
              <span>置信度（0–1，队列按低置信优先）</span>
              <input
                disabled={busy || reviewBusy}
                readOnly
                inputMode="decimal"
                value={reviewConfidence}
              />
            </label>
            <label className={styles.field}>
              <span>审阅原因</span>
              <input disabled={busy || reviewBusy} maxLength={2000} value={reviewReason} onChange={(event) => setReviewReason(event.target.value)} />
            </label>
            <div className={styles.reviewActions}>
              <button className="button button-secondary" type="button" onClick={() => void enqueueReviewTask()} disabled={busy || reviewBusy || !reviewIdentityScope || !correctionTarget || !activeReviewSource?.detail_loaded}>加入审阅队列</button>
              <button className="button button-secondary" type="button" onClick={() => void refreshReviewQueue()} disabled={busy || reviewBusy}>刷新低置信队列</button>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => void recoverReviewEnqueueAttempts()}
                disabled={busy || reviewBusy || !reviewIdentityScope || reviewEnqueueRecoveryCount === 0 || Boolean(reviewEnqueueRecoveryError)}
              >
                精确恢复未知入队（{reviewEnqueueRecoveryCount}）
              </button>
              <button className="button button-secondary" type="button" onClick={() => void submitCorrection()} disabled={busy || reviewBusy || !correctionTarget || !correctionTouched}>兼容快速纠错</button>
            </div>
            {reviewEnqueueRecoveryCount > 0 && !reviewEnqueueRecoveryError && (
              <p role="alert">
                当前项目有 {reviewEnqueueRecoveryCount} 个入队结果未知；恢复只发送不透明句柄与原执行幂等键，精确输入由服务端准备记录绑定，不写入浏览器存储。
              </p>
            )}
            {reviewEnqueueRecoveryError && (
              <p role="alert">
                {reviewEnqueueRecoveryError}：恢复记录可能代表未知副作用，已保留且不会自动清除或降级为新请求。
              </p>
            )}
            {legacyReviewClaimDiscarded && (
              <p role="alert">检测到无法证明身份归属的旧版领取恢复记录，已安全停用；请刷新队列并由服务端重新核对任务状态。</p>
            )}

            <label className={styles.field}>
              <span>审阅任务</span>
              <select disabled={busy || reviewBusy} value={selectedReviewTaskId} onChange={(event) => void selectReviewTask(event.target.value)}>
                <option value="">选择任务</option>
                {reviewTasks.map((task) => (
                  <option value={task.task_id} key={task.task_id}>
                    {task.confidence.toFixed(3)} · {task.target_kind} · {task.state} · {task.task_id}
                  </option>
                ))}
              </select>
            </label>
            {activeReviewTask && (
              <div className={styles.reviewTaskSummary} aria-live="polite">
                <code>{activeReviewTask.task_id}</code>
                <span>{activeReviewTask.state}</span>
                <small>task v{activeReviewTask.version} · correction v{activeReviewTask.current_correction_version}</small>
                {activeReviewTask.claim_expires_at && <small>claim expires {activeReviewTask.claim_expires_at}</small>}
                {activeReviewClaimAttempt && !activeReviewClaim && <small>领取结果待恢复；再次领取会复用原幂等键和令牌。</small>}
                {activeReviewTask.detail_loaded && (
                  <>
                    <small>定位与权威来源</small>
                    <pre className={styles.jsonPreview} tabIndex={0}>{JSON.stringify({
                      target: activeReviewTask.target,
                      original_value: activeReviewTask.original_value,
                      source_digest: activeReviewTask.source_digest,
                      source_ref: activeReviewTask.source_ref,
                      reason: activeReviewTask.reason,
                    }, null, 2)}</pre>
                  </>
                )}
                {activeReviewCorrection && (
                  <>
                    <small>当前不可变纠正版本（批准前必须可见并复核）</small>
                    <pre className={styles.jsonPreview} tabIndex={0}>{JSON.stringify(activeReviewCorrection, null, 2)}</pre>
                  </>
                )}
              </div>
            )}
            <div className={styles.reviewActions}>
              <button className="button button-secondary" type="button" onClick={() => void claimReviewTask()} disabled={busy || reviewBusy || !activeReviewTask || !activeReviewTask.detail_loaded || !reviewIdentityScope || (!activeReviewTaskClaimable && !activePendingReviewClaim) || Boolean(activeReviewClaim)}>{activePendingReviewClaim ? "恢复领取" : "领取"}</button>
              {activeReviewClaimAttempt && !activeReviewClaim && activeReviewTask && (
                <button className="button button-secondary" type="button" onClick={() => abandonReviewClaimRecovery(activeReviewTask.task_id)} disabled={busy || reviewBusy}>清除本地领取恢复</button>
              )}
              <button className="button button-secondary" type="button" onClick={() => void editReviewTask()} disabled={busy || reviewBusy || !activeReviewTask || !activeReviewTask.detail_loaded || !activeReviewClaim || !correctionTouched}>保存纠正版本</button>
              <button className="button button-primary" type="button" onClick={() => void decideReviewTask("approve")} disabled={busy || reviewBusy || !activeReviewTask || !activeReviewTask.detail_loaded || !activeReviewClaim || activeReviewTask.state !== "EDITED" || activeReviewTask.current_correction_version < 1 || !activeReviewCorrection}>批准并传播</button>
              <button className="button button-secondary" type="button" onClick={() => void decideReviewTask("reject")} disabled={busy || reviewBusy || !activeReviewTask || !activeReviewTask.detail_loaded || !activeReviewClaim || activeReviewTask.current_correction_version > 0 && !activeReviewCorrection}>拒绝</button>
              <button className="button button-secondary" type="button" onClick={() => void transitionClosedReviewTask("reopen")} disabled={busy || reviewBusy || !activeReviewTask || !["REJECTED", "REVERTED"].includes(activeReviewTask.state) || activeReviewTask.current_correction_version > 0 && !activeReviewCorrection}>重新打开</button>
              <button className="button button-secondary" type="button" onClick={() => void transitionClosedReviewTask("revert")} disabled={busy || reviewBusy || !activeReviewTask || activeReviewTask.state !== "APPROVED" || activeReviewTask.effective_version !== activeReviewTask.current_correction_version || !activeReviewCorrection}>回退批准版本</button>
              <button className="button button-secondary" type="button" onClick={() => void refreshReviewPropagation()} disabled={busy || reviewBusy || !activeReviewTask}>传播状态</button>
            </div>
            {reviewPropagation && <pre className={styles.jsonPreview} tabIndex={0}>{JSON.stringify(reviewPropagation, null, 2)}</pre>}
          </div>
        </aside>
      </div>
    </div>
  );
}
