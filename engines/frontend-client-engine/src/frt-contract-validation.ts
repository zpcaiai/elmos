import type {
  FrtAction,
  FrtBatchPlanRequest,
  FrtEvidenceReference,
  FrtEvidenceState,
  FrtExecutionContext,
  FrtExecutionScope,
  FrtPrerequisiteCertificate,
  FrtRunCompletionRequest,
  FrtRunnerArtifactReference,
  FrtRunnerCompletion,
  FrtRunnerExitStatus,
  FrtSkillRunRequest,
  FrtRunTransitionRequest,
} from "./frt-types.js";

export const frtActions = ["PLAN", "ANALYZE", "EXECUTE", "VERIFY"] as const;
const runnerExitStatuses = ["COMPLETED", "FAILED"] as const;
const evidenceStates = ["PASSED", "FAILED", "INCONCLUSIVE", "NOT_RUN"] as const;
const certificateStates = ["ACTIVE", "STALE", "REVOKED", "RETEST_REQUIRED"] as const;
const riskLevels = ["R0", "R1", "R2", "R3", "R4", "R5"] as const;
const scopedId = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$/;
const skillId = /^(?:FRT-[0-9]{4}|frt-[a-z0-9-]+)$/;
const runId = /^[a-f0-9]{24}$/;
const batchId = /^G(?:0[1-9]|[12][0-9]|30)$/;
const sha256 = /^sha256:[a-f0-9]{64}$/;
const isoTimestamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/;
const signature = /^[A-Za-z0-9_-]+$/;

export class FrtContractValidationError extends Error {
  readonly code = "FRT_CONTRACT_INVALID";
  readonly path: string;

  constructor(path: string, reason: string) {
    super(`${path}: ${reason}`);
    this.name = "FrtContractValidationError";
    this.path = path;
  }
}

function fail(path: string, reason: string): never {
  throw new FrtContractValidationError(path, reason);
}

function object(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return fail(path, "must be an object");
  }
  return value as Record<string, unknown>;
}

function exactKeys(
  value: Record<string, unknown>,
  path: string,
  required: readonly string[],
  optional: readonly string[] = [],
): void {
  const allowed = new Set([...required, ...optional]);
  for (const key of required) {
    if (!Object.hasOwn(value, key)) fail(`${path}.${key}`, "is required");
  }
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) fail(`${path}.${key}`, "is not allowed");
  }
}

function text(value: unknown, path: string, pattern?: RegExp): string {
  if (typeof value !== "string" || !value.length) fail(path, "must be a non-empty string");
  if (pattern && !pattern.test(value)) fail(path, "has an invalid format");
  return value;
}

function oneOf<T extends string>(value: unknown, path: string, choices: readonly T[]): T {
  if (typeof value !== "string" || !choices.includes(value as T)) {
    fail(path, `must be one of ${choices.join(", ")}`);
  }
  return value as T;
}

function integer(value: unknown, path: string): number {
  if (!Number.isInteger(value) || (value as number) < 0) {
    fail(path, "must be a non-negative integer");
  }
  return value as number;
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") fail(path, "must be a boolean");
  return value;
}

function stringArray(value: unknown, path: string, minimum = 0): readonly string[] {
  if (!Array.isArray(value) || value.length < minimum) {
    fail(path, `must be an array with at least ${minimum} item(s)`);
  }
  return value.map((item, index) => text(item, `${path}[${index}]`));
}

function scope(value: unknown, path: string): FrtExecutionScope {
  const candidate = object(value, path);
  const keys = [
    "organizationId",
    "tenantId",
    "workspaceId",
    "projectId",
    "accountId",
    "environmentId",
    "releaseId",
  ] as const;
  exactKeys(candidate, path, keys);
  return {
    organizationId: text(candidate.organizationId, `${path}.organizationId`, scopedId),
    tenantId: text(candidate.tenantId, `${path}.tenantId`, scopedId),
    workspaceId: text(candidate.workspaceId, `${path}.workspaceId`, scopedId),
    projectId: text(candidate.projectId, `${path}.projectId`, scopedId),
    accountId: text(candidate.accountId, `${path}.accountId`, scopedId),
    environmentId: text(candidate.environmentId, `${path}.environmentId`, scopedId),
    releaseId: text(candidate.releaseId, `${path}.releaseId`, scopedId),
  };
}

function context(value: unknown, path: string): FrtExecutionContext {
  const candidate = object(value, path);
  const scopeKeys = [
    "organizationId",
    "tenantId",
    "workspaceId",
    "projectId",
    "accountId",
    "environmentId",
    "releaseId",
  ] as const;
  exactKeys(candidate, path, [
    ...scopeKeys,
    "sourceSnapshotDigest",
    "policyVersion",
    "requestedBy",
    "risk",
  ]);
  const parsedScope = scope(
    Object.fromEntries(scopeKeys.map(key => [key, candidate[key]])),
    path,
  );
  return {
    ...parsedScope,
    sourceSnapshotDigest: text(candidate.sourceSnapshotDigest, `${path}.sourceSnapshotDigest`, sha256),
    policyVersion: text(candidate.policyVersion, `${path}.policyVersion`, scopedId),
    requestedBy: text(candidate.requestedBy, `${path}.requestedBy`, scopedId),
    risk: oneOf(candidate.risk, `${path}.risk`, riskLevels),
  };
}

function certificate(value: unknown, path: string): FrtPrerequisiteCertificate {
  const candidate = object(value, path);
  exactKeys(candidate, path, [
    "batch",
    "state",
    "scope",
    "artifactDigest",
    "evidenceRefs",
    "authority",
    "keyId",
    "issuedAt",
    "expiresAt",
    "signature",
  ]);
  return {
    batch: text(candidate.batch, `${path}.batch`, batchId),
    state: oneOf(candidate.state, `${path}.state`, certificateStates),
    scope: scope(candidate.scope, `${path}.scope`),
    artifactDigest: text(candidate.artifactDigest, `${path}.artifactDigest`, sha256),
    evidenceRefs: stringArray(candidate.evidenceRefs, `${path}.evidenceRefs`, 1),
    authority: text(candidate.authority, `${path}.authority`, scopedId),
    keyId: text(candidate.keyId, `${path}.keyId`, scopedId),
    issuedAt: text(candidate.issuedAt, `${path}.issuedAt`, isoTimestamp),
    expiresAt: text(candidate.expiresAt, `${path}.expiresAt`, isoTimestamp),
    signature: text(candidate.signature, `${path}.signature`, signature),
  };
}

function evidence(value: unknown, path: string): FrtEvidenceReference {
  const candidate = object(value, path);
  exactKeys(candidate, path, [
    "role",
    "uri",
    "digest",
    "state",
    "executor",
    "verifier",
    "synthetic",
    "byteCount",
    "authority",
    "keyId",
    "issuedAt",
    "expiresAt",
    "signature",
  ]);
  return {
    role: text(candidate.role, `${path}.role`),
    uri: text(candidate.uri, `${path}.uri`),
    digest: text(candidate.digest, `${path}.digest`, sha256),
    state: oneOf<FrtEvidenceState>(candidate.state, `${path}.state`, evidenceStates),
    executor: text(candidate.executor, `${path}.executor`),
    verifier: text(candidate.verifier, `${path}.verifier`),
    synthetic: boolean(candidate.synthetic, `${path}.synthetic`),
    byteCount: integer(candidate.byteCount, `${path}.byteCount`),
    authority: text(candidate.authority, `${path}.authority`, scopedId),
    keyId: text(candidate.keyId, `${path}.keyId`, scopedId),
    issuedAt: text(candidate.issuedAt, `${path}.issuedAt`, isoTimestamp),
    expiresAt: text(candidate.expiresAt, `${path}.expiresAt`, isoTimestamp),
    signature: text(candidate.signature, `${path}.signature`, signature),
  };
}

function arrayOf<T>(
  value: unknown,
  path: string,
  parser: (item: unknown, itemPath: string) => T,
): readonly T[] {
  if (!Array.isArray(value)) fail(path, "must be an array");
  return value.map((item, index) => parser(item, `${path}[${index}]`));
}

export function validateFrtSkillRunRequest(value: unknown): FrtSkillRunRequest {
  const candidate = object(value, "request");
  exactKeys(candidate, "request", [
    "schemaVersion",
    "skillId",
    "action",
    "idempotencyKey",
    "expectedVersion",
    "context",
    "prerequisiteCertificates",
    "evidence",
  ], ["verificationSubject", "input"]);
  if (candidate.schemaVersion !== "1.0") fail("request.schemaVersion", "must equal 1.0");
  const input = candidate.input === undefined ? undefined : object(candidate.input, "request.input");
  const action = oneOf<FrtAction>(candidate.action, "request.action", frtActions);
  let verificationSubject: FrtSkillRunRequest["verificationSubject"];
  if (candidate.verificationSubject !== undefined) {
    if (action !== "VERIFY") fail("request.verificationSubject", "is only allowed for VERIFY");
    const subject = object(candidate.verificationSubject, "request.verificationSubject");
    exactKeys(subject, "request.verificationSubject", ["runId", "resultDigest"]);
    verificationSubject = {
      runId: text(subject.runId, "request.verificationSubject.runId", runId),
      resultDigest: text(subject.resultDigest, "request.verificationSubject.resultDigest", sha256),
    };
  }
  return {
    schemaVersion: "1.0",
    skillId: text(candidate.skillId, "request.skillId", skillId),
    action,
    idempotencyKey: text(candidate.idempotencyKey, "request.idempotencyKey", scopedId),
    expectedVersion: integer(candidate.expectedVersion, "request.expectedVersion"),
    context: context(candidate.context, "request.context"),
    prerequisiteCertificates: arrayOf(
      candidate.prerequisiteCertificates,
      "request.prerequisiteCertificates",
      certificate,
    ),
    evidence: arrayOf(candidate.evidence, "request.evidence", evidence),
    ...(verificationSubject === undefined ? {} : { verificationSubject }),
    ...(input === undefined ? {} : { input }),
  };
}

export function validateFrtBatchPlanRequest(value: unknown): FrtBatchPlanRequest {
  const candidate = object(value, "request");
  exactKeys(candidate, "request", [
    "schemaVersion",
    "batch",
    "idempotencyKey",
    "expectedVersion",
    "context",
    "prerequisiteCertificates",
  ]);
  if (candidate.schemaVersion !== "1.0") fail("request.schemaVersion", "must equal 1.0");
  return {
    schemaVersion: "1.0",
    batch: text(candidate.batch, "request.batch", batchId),
    idempotencyKey: text(candidate.idempotencyKey, "request.idempotencyKey", scopedId),
    expectedVersion: integer(candidate.expectedVersion, "request.expectedVersion"),
    context: context(candidate.context, "request.context"),
    prerequisiteCertificates: arrayOf(
      candidate.prerequisiteCertificates,
      "request.prerequisiteCertificates",
      certificate,
    ),
  };
}

function runnerArtifact(value: unknown, path: string): FrtRunnerArtifactReference {
  const candidate = object(value, path);
  exactKeys(candidate, path, ["name", "uri", "digest", "byteCount"]);
  return {
    name: text(candidate.name, `${path}.name`, scopedId),
    uri: text(candidate.uri, `${path}.uri`),
    digest: text(candidate.digest, `${path}.digest`, sha256),
    byteCount: integer(candidate.byteCount, `${path}.byteCount`),
  };
}

export function validateFrtRunnerCompletion(value: unknown, path = "completion"): FrtRunnerCompletion {
  const candidate = object(value, path);
  exactKeys(candidate, path, [
    "schemaVersion",
    "runnerId",
    "exitStatus",
    "startedAt",
    "finishedAt",
    "customerCodeExecuted",
    "productionOperationExecuted",
    "artifacts",
    "evidence",
    "authority",
    "keyId",
    "issuedAt",
    "expiresAt",
    "signature",
  ]);
  if (candidate.schemaVersion !== "1.0") fail(`${path}.schemaVersion`, "must equal 1.0");
  const startedAt = text(candidate.startedAt, `${path}.startedAt`, isoTimestamp);
  const finishedAt = text(candidate.finishedAt, `${path}.finishedAt`, isoTimestamp);
  if (Date.parse(finishedAt) < Date.parse(startedAt)) {
    fail(`${path}.finishedAt`, "must not precede startedAt");
  }
  return {
    schemaVersion: "1.0",
    runnerId: text(candidate.runnerId, `${path}.runnerId`, scopedId),
    exitStatus: oneOf<FrtRunnerExitStatus>(candidate.exitStatus, `${path}.exitStatus`, runnerExitStatuses),
    startedAt,
    finishedAt,
    customerCodeExecuted: boolean(candidate.customerCodeExecuted, `${path}.customerCodeExecuted`),
    productionOperationExecuted: boolean(
      candidate.productionOperationExecuted,
      `${path}.productionOperationExecuted`,
    ),
    artifacts: arrayOf(candidate.artifacts, `${path}.artifacts`, runnerArtifact),
    evidence: arrayOf(candidate.evidence, `${path}.evidence`, evidence),
    authority: text(candidate.authority, `${path}.authority`, scopedId),
    keyId: text(candidate.keyId, `${path}.keyId`, scopedId),
    issuedAt: text(candidate.issuedAt, `${path}.issuedAt`, isoTimestamp),
    expiresAt: text(candidate.expiresAt, `${path}.expiresAt`, isoTimestamp),
    signature: text(candidate.signature, `${path}.signature`, signature),
  };
}

export function validateFrtRunCompletionRequest(value: unknown): FrtRunCompletionRequest {
  const candidate = object(value, "request");
  exactKeys(candidate, "request", ["schemaVersion", "expectedVersion", "completion"]);
  if (candidate.schemaVersion !== "1.0") fail("request.schemaVersion", "must equal 1.0");
  return {
    schemaVersion: "1.0",
    expectedVersion: integer(candidate.expectedVersion, "request.expectedVersion"),
    completion: validateFrtRunnerCompletion(candidate.completion, "request.completion"),
  };
}

export function validateFrtRunTransitionRequest(value: unknown): FrtRunTransitionRequest {
  const candidate = object(value, "request");
  exactKeys(candidate, "request", ["schemaVersion", "expectedVersion"]);
  if (candidate.schemaVersion !== "1.0") fail("request.schemaVersion", "must equal 1.0");
  return {
    schemaVersion: "1.0",
    expectedVersion: integer(candidate.expectedVersion, "request.expectedVersion"),
  };
}
