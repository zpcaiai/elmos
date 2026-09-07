import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { createHash, timingSafeEqual } from "node:crypto";
import {
  canonicalStrictJson,
  parseStrictJson,
  StrictJsonError,
} from "../../../lib/multimodal-intake/strictJson";
import {
  multimodalPermissionForOperation,
  multimodalSkillNames,
  type MultimodalIntakePermission,
  type MultimodalSkillName,
} from "../multimodalSkillCatalog";

const MAX_ENGINE_OUTPUT_BYTES = 4 * 1024 * 1024;
const MAX_ENGINE_INPUT_BYTES = 2 * 1024 * 1024;
const ENGINE_RESPONSE_WAIT_MS = 45_000;
const executionContractVersion = "multimodal-intake-execution-v2";
const browserRequestSchemaVersion = "multimodal-intake-browser-request-v1";
const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const actorPattern = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$/;
const operationPattern = /^[a-z][a-z0-9_-]{0,63}$/;
const idempotencyPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,199}$/;
const engineProjectBindingVersion = "elmos-multimodal-intake-project-v1";
const trustedExecutePath = "/api/v1/multimodal-intake/execute";
const progressCursorPattern = /^p1-([1-9][0-9]{0,15})-([0-9a-f]{64})$/;
const progressTimestampPattern = /^(\d{4})-(\d{2})-(\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;
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
const taskProgressTransitions: Readonly<Record<string, readonly string[]>> = Object.freeze({
  PENDING: ["RUNNING", "CANCELLED"],
  RUNNING: ["PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"],
  PAUSED: ["RUNNING", "CANCELLED"],
  FAILED_RETRYABLE: ["RUNNING", "FAILED_FINAL", "CANCELLED"],
  SUCCEEDED: [],
  FAILED_FINAL: [],
  CANCELLED: [],
});
const MAX_PROGRESS_EVENTS = 64;

function validProgressTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const matched = progressTimestampPattern.exec(value);
  if (!matched || !Number.isFinite(Date.parse(value))) return false;
  const year = Number(matched[1]);
  const month = Number(matched[2]);
  const day = Number(matched[3]);
  if (year < 1 || month < 1 || month > 12) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1];
}

export class MultimodalIntakeRunnerError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(
    status: number,
    code: string,
    retryable = false,
  ) {
    super(code);
    this.status = status;
    this.code = code;
    this.retryable = retryable;
    this.name = "MultimodalIntakeRunnerError";
  }
}

export function parseStrictMultimodalJson(source: string): unknown {
  try {
    return parseStrictJson(source);
  } catch (error) {
    if (error instanceof StrictJsonError) {
      const code = error.code === "JSON_DUPLICATE_KEY"
        ? "MULTIMODAL_DUPLICATE_JSON_KEY"
        : `MULTIMODAL_REQUEST_${error.code}`;
      throw new MultimodalIntakeRunnerError(400, code);
    }
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_REQUEST_JSON_INVALID");
  }
}

export type MultimodalRunnerIdentity = {
  tenantId: string;
  actor: string;
};

export type MultimodalExecuteBody = {
  skill: MultimodalSkillName;
  operation: string;
  projectId: string;
  input: Record<string, unknown>;
};

export function requiredMultimodalPermission(
  skill: string,
  operation: string,
): MultimodalIntakePermission {
  const permission = multimodalPermissionForOperation(skill, operation);
  if (!permission) {
    throw new MultimodalIntakeRunnerError(404, "MULTIMODAL_OPERATION_UNKNOWN");
  }
  return permission;
}

export function multimodalBoundaryEnvelope(
  status: number,
  code: string,
  retryable: boolean,
  traceId: string,
): Record<string, unknown> {
  const unsigned = {
    schema_version: "1.0.0",
    status: status >= 500 ? "FAILED" : "BLOCKED",
    code,
    retryable,
    trace_id: traceId,
    external_evidence: "NOT_RUN",
    certification: "NOT_CERTIFIED",
  };
  return {
    ...unsigned,
    result_digest: createHash("sha256").update(canonicalStrictJson(unsigned)).digest("hex"),
  };
}

function record(value: unknown, code: string, status = 400): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new MultimodalIntakeRunnerError(status, code);
  }
  return value as Record<string, unknown>;
}

function parseStrictEngineJson(source: string): unknown {
  try {
    return parseStrictJson(source);
  } catch {
    throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_JSON_INVALID");
  }
}

export function validateEngineEnvelope(
  response: Record<string, unknown>,
  expectedSkill: MultimodalSkillName,
  expectedOperation: string,
  expectedTraceId: string,
  expectedRequestDigest: string,
  expectedProjectId: string,
): Record<string, unknown> {
  const transportStatus = response._http_status;
  if (
    typeof transportStatus !== "number"
    || !Number.isInteger(transportStatus)
    || transportStatus < 200
    || transportStatus > 599
  ) {
    throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_STATUS_INVALID");
  }
  const resultDigest = response.result_digest;
  if (typeof resultDigest === "string" && /^[0-9a-f]{64}$/.test(resultDigest)) {
    const required = new Set([
      "schema_version", "skill", "operation", "status", "retryable", "trace_id",
      "request_digest", "implementation_state", "external_evidence", "certification",
      "output", "result_digest", "_http_status",
    ]);
    if (Object.hasOwn(response, "code")) required.add("code");
    const status = response.status;
    if (
      transportStatus !== 200
      || Object.keys(response).length !== required.size
      || Object.keys(response).some((key) => !required.has(key))
      || response.schema_version !== "1.0.0"
      || response.skill !== expectedSkill
      || response.operation !== expectedOperation
      || typeof status !== "string"
      || !["SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL"].includes(status)
      || typeof response.retryable !== "boolean"
      || response.trace_id !== expectedTraceId
      || response.request_digest !== expectedRequestDigest
      || typeof response.implementation_state !== "string"
      || !["CODE_IMPLEMENTED_LOCAL", "BRIDGE_REQUIRED"].includes(response.implementation_state)
      || response.external_evidence !== "NOT_RUN"
      || response.certification !== "NOT_CERTIFIED"
      || !response.output
      || typeof response.output !== "object"
      || Array.isArray(response.output)
      || (Object.hasOwn(response, "code") && (
        typeof response.code !== "string" || !/^[A-Z][A-Z0-9_:-]{0,127}$/.test(response.code)
      ))
      || (["BLOCKED", "FAILED"].includes(status) && !Object.hasOwn(response, "code"))
    ) {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_INVALID");
    }
    const digestDocument = { ...response };
    delete digestDocument._http_status;
    delete digestDocument.result_digest;
    const expectedResultDigest = createHash("sha256")
      .update(canonicalStrictJson(digestDocument))
      .digest("hex");
    if (resultDigest !== expectedResultDigest) {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_DIGEST_INVALID");
    }
    if (
      expectedSkill === "elmos-multimodal-input-orchestrator"
      && expectedOperation.replaceAll("-", "_") === "bootstrap_project"
      && ["SUCCEEDED", "PARTIAL"].includes(status)
      && (response.output as Record<string, unknown>).project_id !== expectedProjectId
    ) {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_PROJECT_SCOPE_INVALID");
    }
    return response;
  }
  const transportFields = new Set(["schema_version", "status", "code", "retryable", "_http_status"]);
  if (Object.hasOwn(response, "trace_id")) transportFields.add("trace_id");
  if (
    transportStatus < 400
    || Object.keys(response).length !== transportFields.size
    || Object.keys(response).some((key) => !transportFields.has(key))
    || response.schema_version !== "1.0.0"
    || typeof response.status !== "string"
    || !["BLOCKED", "FAILED"].includes(response.status)
    || (transportStatus < 500 && response.status !== "BLOCKED")
    || (transportStatus >= 500 && response.status !== "FAILED")
    || typeof response.code !== "string"
    || !/^[A-Z][A-Z0-9_:-]{0,127}$/.test(response.code)
    || typeof response.retryable !== "boolean"
    || (Object.hasOwn(response, "trace_id") && response.trace_id !== expectedTraceId)
  ) {
    throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_INVALID");
  }
  return response;
}

export function boundMultimodalProjectId(
  identity: MultimodalRunnerIdentity,
  projectAlias: string,
): string {
  const digest = createHash("sha256")
    .update(engineProjectBindingVersion)
    .update("\0")
    .update(identity.tenantId)
    .update("\0")
    .update(projectAlias)
    .digest("hex");
  return `mmi-prj-${digest}`;
}

export function parseMultimodalExecuteBody(value: unknown): MultimodalExecuteBody {
  const body = record(value, "MULTIMODAL_REQUEST_INVALID");
  const fields = Object.keys(body).sort();
  if (
    fields.join(",")
    !== "input,operation,projectId,request_digest,schema_version,skill"
  ) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_REQUEST_FIELDS_INVALID");
  }
  if (body.schema_version !== browserRequestSchemaVersion) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_REQUEST_SCHEMA_INVALID");
  }
  if (typeof body.skill !== "string" || !multimodalSkillNames.has(body.skill)) {
    throw new MultimodalIntakeRunnerError(404, "MULTIMODAL_SKILL_UNKNOWN");
  }
  if (typeof body.operation !== "string" || !operationPattern.test(body.operation)) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_OPERATION_INVALID");
  }
  if (typeof body.projectId !== "string" || !identifierPattern.test(body.projectId)) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_PROJECT_INVALID");
  }
  const input = record(body.input, "MULTIMODAL_INPUT_INVALID");
  if (typeof body.request_digest !== "string" || !/^[0-9a-f]{64}$/.test(body.request_digest)) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_REQUEST_DIGEST_INVALID");
  }
  const expectedDigest = createHash("sha256").update(canonicalStrictJson({
    schema_version: browserRequestSchemaVersion,
    skill: body.skill,
    operation: body.operation,
    projectId: body.projectId,
    input,
  })).digest();
  const suppliedDigest = Buffer.from(body.request_digest, "hex");
  if (suppliedDigest.byteLength !== expectedDigest.byteLength
    || !timingSafeEqual(suppliedDigest, expectedDigest)) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_REQUEST_DIGEST_INVALID");
  }
  requiredMultimodalPermission(body.skill, body.operation);
  return {
    skill: body.skill as MultimodalSkillName,
    operation: body.operation,
    projectId: body.projectId,
    input,
  };
}

export function multimodalChildEnvironment(engineSource: string): NodeJS.ProcessEnv {
  return {
    NODE_ENV: process.env.NODE_ENV ?? "development",
    PATH: "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
    PYTHONPATH: engineSource,
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONNOUSERSITE: "1",
    PYTHONUTF8: "1",
  };
}

function repositoryRoot(): string {
  const configured = process.env.ELMOS_REPOSITORY_ROOT;
  const candidates = [configured, process.cwd(), path.resolve(process.cwd(), "../..")]
    .filter((candidate): candidate is string => Boolean(candidate));
  const root = candidates.find((candidate) => existsSync(
    path.join(candidate, "engines/multimodal-intake-engine/src/elmos_multimodal_intake"),
  ));
  if (!root) throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_ENGINE_NOT_INSTALLED", true);
  return path.resolve(root);
}

function dataRoot(): string {
  const configured = process.env.ELMOS_MULTIMODAL_INTAKE_DATA_ROOT;
  if (configured) {
    if (!path.isAbsolute(configured) || configured === path.parse(configured).root) {
      throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_DATA_ROOT_INVALID");
    }
    return configured;
  }
  if (process.env.NODE_ENV === "production") {
    throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_DATA_ROOT_REQUIRED");
  }
  return path.join(tmpdir(), "elmos-multimodal-intake-local-v1");
}

function executePython(
  payload: string,
  identity: MultimodalRunnerIdentity,
  engineProjectId: string,
  expectedSkill: MultimodalSkillName,
  expectedOperation: string,
  expectedTraceId: string,
  expectedRequestDigest: string,
): Promise<Record<string, unknown>> {
  const root = repositoryRoot();
  const engineSource = path.join(root, "engines/multimodal-intake-engine/src");
  const configuredExecutable = process.env.ELMOS_MULTIMODAL_INTAKE_PYTHON;
  if (process.env.NODE_ENV === "production" && !configuredExecutable) {
    return Promise.reject(new MultimodalIntakeRunnerError(503, "MULTIMODAL_PYTHON_312_REQUIRED"));
  }
  const executable = configuredExecutable ?? "python3.12";
  if (configuredExecutable && !path.isAbsolute(configuredExecutable)) {
    return Promise.reject(new MultimodalIntakeRunnerError(503, "MULTIMODAL_PYTHON_PATH_INVALID"));
  }
  if (Buffer.byteLength(payload, "utf8") > MAX_ENGINE_INPUT_BYTES) {
    return Promise.reject(new MultimodalIntakeRunnerError(413, "MULTIMODAL_REQUEST_TOO_LARGE"));
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    let discardStdout = false;
    const fail = (error: MultimodalIntakeRunnerError) => {
      if (settled) return;
      settled = true;
      reject(error);
    };
    const child = spawn(
      /* turbopackIgnore: true */ executable,
      [
        "-m",
        "elmos_multimodal_intake.cli",
        "execute",
        "--data-root",
        dataRoot(),
        "--tenant-id",
        identity.tenantId,
        "--project-id",
        engineProjectId,
        "--actor-id",
        identity.actor,
      ],
      {
        cwd: root,
        env: multimodalChildEnvironment(engineSource),
        shell: false,
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    const stdout: Buffer[] = [];
    let outputBytes = 0;
    const timer = setTimeout(() => {
      // The child may already have invoked a scanner/model/provider.  Killing
      // it here would create a crash window before its durable receipt can be
      // completed.  Stop waiting for the HTTP response, but keep draining the
      // supervised child so it can persist a terminal outcome.
      fail(new MultimodalIntakeRunnerError(
        504,
        "MULTIMODAL_ENGINE_OUTCOME_RECONCILIATION_REQUIRED",
        false,
      ));
    }, ENGINE_RESPONSE_WAIT_MS);
    child.stdout.on("data", (chunk: Buffer) => {
      if (discardStdout) return;
      outputBytes += chunk.byteLength;
      if (outputBytes > MAX_ENGINE_OUTPUT_BYTES) {
        stdout.length = 0;
        discardStdout = true;
        fail(new MultimodalIntakeRunnerError(
          502,
          "MULTIMODAL_ENGINE_OUTCOME_RECONCILIATION_REQUIRED",
          false,
        ));
        return;
      }
      stdout.push(chunk);
    });
    child.stderr.on("data", (_chunk: Buffer) => {
      // Drain without retaining untrusted diagnostic output.
    });
    child.stdin.once("error", () => {
      // The pipe can fail after the child accepted a complete request.  Treat
      // that timing as unknown instead of inviting a new idempotency key.
      fail(new MultimodalIntakeRunnerError(
        502,
        "MULTIMODAL_ENGINE_OUTCOME_RECONCILIATION_REQUIRED",
        false,
      ));
    });
    child.stdout.once("error", () => {
      fail(new MultimodalIntakeRunnerError(
        502,
        "MULTIMODAL_ENGINE_OUTCOME_RECONCILIATION_REQUIRED",
        false,
      ));
    });
    child.stderr.once("error", () => {
      // stderr is deliberately ignored and never participates in the public
      // result contract.  A logging-pipe failure must not terminate execution.
    });
    child.once("error", () => {
      clearTimeout(timer);
      fail(new MultimodalIntakeRunnerError(503, "MULTIMODAL_ENGINE_UNAVAILABLE", true));
    });
    child.once("close", (code) => {
      clearTimeout(timer);
      if (settled) return;
      try {
        let source: string;
        try {
          source = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(stdout));
        } catch {
          throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_JSON_INVALID");
        }
        const response = validateEngineEnvelope(
          record(
            parseStrictEngineJson(source),
            "MULTIMODAL_ENGINE_RESPONSE_INVALID",
            502,
          ),
          expectedSkill,
          expectedOperation,
          expectedTraceId,
          expectedRequestDigest,
          engineProjectId,
        );
        const transportStatus = response._http_status as number;
        if (
          (transportStatus === 200 && code !== 0 && code !== 3)
          || (transportStatus >= 400 && code !== 2)
        ) {
          fail(new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_EXIT_STATUS_INVALID"));
          return;
        }
        settled = true;
        resolve(response);
      } catch (error) {
        fail(error instanceof MultimodalIntakeRunnerError
          ? error
          : new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_INVALID"));
      }
    });
    child.stdin.end(payload);
  });
}

function trustedLoopbackEndpoint(): { executeUrl: URL; token: string } | undefined {
  const configured = process.env.ELMOS_MULTIMODAL_INTAKE_ENDPOINT;
  const token = process.env.ELMOS_MULTIMODAL_INTAKE_BEARER_TOKEN;
  if (!configured && !token) return undefined;
  if (!configured || !token || token.length < 32 || token.length > 4096 || /[^\x21-\x7e]/.test(token)) {
    throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_TRUSTED_ENDPOINT_CONFIG_INVALID");
  }
  let endpoint: URL;
  try {
    endpoint = new URL(configured);
  } catch {
    throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_TRUSTED_ENDPOINT_CONFIG_INVALID");
  }
  if (
    endpoint.protocol !== "http:"
    || !["127.0.0.1", "::1", "[::1]"].includes(endpoint.hostname)
    || endpoint.username || endpoint.password || endpoint.search || endpoint.hash
    || !["", "/"].includes(endpoint.pathname)
  ) {
    throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_TRUSTED_ENDPOINT_CONFIG_INVALID");
  }
  return { executeUrl: new URL(trustedExecutePath, endpoint), token };
}

function validatedProgressSseBatch(
  source: string,
  kind: "jobs" | "tasks",
  resourceId: string,
  suppliedCursor: string | undefined,
): string {
  if (!source || source.includes("\r") || !source.endsWith("\n\n")) {
    throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
  }
  const rawFrames = source.slice(0, -2).split("\n\n");
  if (!rawFrames.length || rawFrames.length > MAX_PROGRESS_EVENTS) {
    throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
  }
  const expectedKind = kind === "jobs" ? "JOB_PROGRESS" : "TASK_PROGRESS";
  const progressFields = kind === "jobs"
    ? new Set([
        "schema_version", "kind", "resource_id", "sequence_number", "event_type",
        "state", "result_status", "attempt", "max_attempts", "occurred_at",
        "content_digest", "cursor",
      ])
    : new Set([
        "schema_version", "kind", "resource_id", "sequence_number", "event_type",
        "state", "previous_state", "occurred_at", "content_digest", "cursor",
      ]);
  const heartbeatFields = new Set([
    "schema_version", "kind", "resource_id", "sequence_number", "status",
    "content_digest", "cursor",
  ]);
  const suppliedSequence = suppliedCursor
    ? Number(progressCursorPattern.exec(suppliedCursor)?.[1] ?? 0)
    : 0;
  let lastSequence = suppliedSequence;
  let lastTaskState: string | undefined;
  let progressDocumentCount = 0;
  let observedHeartbeat = false;
  const canonicalFrames: string[] = [];
  for (const [index, frame] of rawFrames.entries()) {
    const lines = frame.split("\n");
    const progress = lines.length === 3 && lines[0].startsWith("id: ")
      && lines[1] === "event: progress" && lines[2].startsWith("data: ");
    const heartbeat = lines.length === 2 && lines[0] === "event: heartbeat"
      && lines[1].startsWith("data: ");
    if (!progress && !heartbeat) {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
    }
    if (heartbeat && (rawFrames.length !== 1 || index !== 0)) {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
    }
    const eventName = progress ? "progress" : "heartbeat";
    const id = progress ? lines[0].slice(4) : undefined;
    const dataLine = lines[progress ? 2 : 1];
    let parsed: unknown;
    try {
      parsed = parseStrictJson(dataLine.slice(6));
    } catch {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
    }
    const document = record(parsed, "MULTIMODAL_PROGRESS_RESPONSE_INVALID", 502);
    const expectedFields = progress ? progressFields : heartbeatFields;
    const sequence = document.sequence_number;
    if (
      Object.keys(document).length !== expectedFields.size
      || Object.keys(document).some((key) => !expectedFields.has(key))
      || document.schema_version !== "1.0.0"
      || document.kind !== (progress ? expectedKind : `${expectedKind}_HEARTBEAT`)
      || document.resource_id !== resourceId
      || typeof sequence !== "number"
      || !Number.isSafeInteger(sequence)
      || sequence < 0
      || typeof document.content_digest !== "string"
      || !/^sha256:[0-9a-f]{64}$/.test(document.content_digest)
    ) throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
    if (progress && kind === "jobs") {
      const state = document.state;
      const resultStatus = document.result_status;
      const attempt = document.attempt;
      const maximumAttempts = document.max_attempts;
      const occurredAt = document.occurred_at;
      if (
        document.event_type !== "processing.job.snapshot"
        || typeof state !== "string"
        || !Object.hasOwn(jobProgressResultByState, state)
        || resultStatus !== jobProgressResultByState[state]
        || typeof attempt !== "number"
        || !Number.isSafeInteger(attempt)
        || attempt < 0
        || typeof maximumAttempts !== "number"
        || !Number.isSafeInteger(maximumAttempts)
        || maximumAttempts < 1
        || attempt > maximumAttempts
        || !validProgressTimestamp(occurredAt)
      ) {
        throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
      }
    }
    if (progress && kind === "tasks") {
      const state = document.state;
      const previousState = document.previous_state;
      if (
        document.event_type !== "durable.task.transitioned"
        || typeof state !== "string"
        || typeof previousState !== "string"
        || !Object.hasOwn(taskProgressTransitions, previousState)
        || !Object.hasOwn(taskProgressTransitions, state)
        || !taskProgressTransitions[previousState].includes(state)
        || lastTaskState !== undefined && previousState !== lastTaskState
        || lastTaskState === undefined && suppliedCursor === undefined && previousState !== "PENDING"
      ) {
        throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
      }
      lastTaskState = state;
    }
    const unsigned = { ...document };
    delete unsigned.content_digest;
    delete unsigned.cursor;
    const expectedDigest = createHash("sha256")
      .update(canonicalStrictJson(unsigned))
      .digest("hex");
    if (document.content_digest !== `sha256:${expectedDigest}`) {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_DIGEST_INVALID");
    }
    if (progress) {
      progressDocumentCount += 1;
      if (
        !id
        || document.cursor !== id
        || id !== `p1-${sequence}-${expectedDigest}`
        || sequence < 1
        || kind === "tasks" && sequence !== lastSequence + 1
        || kind === "jobs" && sequence <= lastSequence
        || kind === "jobs" && progressDocumentCount !== 1
        || typeof document.event_type !== "string"
        || typeof document.state !== "string"
        || !validProgressTimestamp(document.occurred_at)
      ) throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_CURSOR_INVALID");
      lastSequence = sequence;
      canonicalFrames.push(`id: ${id}\nevent: progress\ndata: ${canonicalStrictJson(document)}\n\n`);
    } else {
      if (
        document.status !== "NO_CHANGE"
        || sequence !== suppliedSequence
        || document.cursor !== (suppliedCursor ?? null)
      ) throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_HEARTBEAT_INVALID");
      observedHeartbeat = true;
      canonicalFrames.push(`event: heartbeat\ndata: ${canonicalStrictJson(document)}\n\n`);
    }
  }
  if (observedHeartbeat && canonicalFrames.length !== 1) {
    throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
  }
  return canonicalFrames.join("");
}

export async function readMultimodalProgressBatch(
  identity: MultimodalRunnerIdentity,
  projectId: string,
  kind: "jobs" | "tasks",
  resourceId: string,
  cursor: string | undefined,
  signal?: AbortSignal,
  upstreamWaitMs = ENGINE_RESPONSE_WAIT_MS,
): Promise<string> {
  if (
    !identifierPattern.test(identity.tenantId)
    || !actorPattern.test(identity.actor)
    || !identifierPattern.test(projectId)
  ) throw new MultimodalIntakeRunnerError(403, "MULTIMODAL_IDENTITY_INVALID");
  if (!identifierPattern.test(resourceId)) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_PROGRESS_RESOURCE_INVALID");
  }
  if (cursor !== undefined && !progressCursorPattern.test(cursor)) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_PROGRESS_CURSOR_INVALID");
  }
  if (
    !Number.isSafeInteger(upstreamWaitMs)
    || upstreamWaitMs < 1
    || upstreamWaitMs > ENGINE_RESPONSE_WAIT_MS
  ) {
    throw new MultimodalIntakeRunnerError(500, "MULTIMODAL_PROGRESS_TIMEOUT_INVALID");
  }
  // Derive the same scoped engine project used by execute requests and send
  // the complete trusted context to the loopback boundary.  The bearer token
  // authenticates the BFF, but is deliberately insufficient to select a
  // tenant, project, actor or resource by itself.
  const engineProjectId = boundMultimodalProjectId(identity, projectId);
  const trusted = trustedLoopbackEndpoint();
  if (!trusted) {
    throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_PROGRESS_ENDPOINT_NOT_CONFIGURED", true);
  }
  const progressUrl = new URL(
    `/api/v1/multimodal-intake/progress/${kind}/${encodeURIComponent(resourceId)}/events`,
    trusted.executeUrl,
  );
  if (cursor) progressUrl.searchParams.set("cursor", cursor);
  const upstreamController = new AbortController();
  let upstreamTimedOut = false;
  const clientAborted = () => signal?.aborted === true;
  const abortFromClient = () => upstreamController.abort("MULTIMODAL_PROGRESS_CLIENT_CLOSED");
  if (clientAborted()) {
    throw new DOMException("MULTIMODAL_PROGRESS_CLIENT_CLOSED", "AbortError");
  }
  signal?.addEventListener("abort", abortFromClient, { once: true });
  const timeout = setTimeout(() => {
    upstreamTimedOut = true;
    upstreamController.abort("MULTIMODAL_PROGRESS_ENDPOINT_TIMEOUT");
  }, upstreamWaitMs);
  let response: Response;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    response = await fetch(progressUrl, {
      method: "GET",
      redirect: "error",
      signal: upstreamController.signal,
      headers: {
        Accept: "text/event-stream",
        Authorization: `Bearer ${trusted.token}`,
        "X-ELMOS-Bound-Tenant": identity.tenantId,
        "X-ELMOS-Bound-Project": engineProjectId,
        "X-ELMOS-Bound-Actor": identity.actor,
      },
    });
    if (!response.ok) {
      throw new MultimodalIntakeRunnerError(
        response.status >= 400 && response.status <= 599 ? response.status : 502,
        "MULTIMODAL_PROGRESS_ENGINE_REJECTED",
        response.status >= 500,
      );
    }
    const mediaType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
    if (mediaType !== "text/event-stream") {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_CONTENT_TYPE_INVALID");
    }
    const encoding = response.headers.get("content-encoding")?.trim().toLowerCase();
    if (encoding && encoding !== "identity") {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_ENCODING_INVALID");
    }
    reader = response.body?.getReader();
    if (!reader) throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
    const chunks: Uint8Array[] = [];
    let observed = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        observed += value.byteLength;
        if (observed > MAX_ENGINE_OUTPUT_BYTES) {
          try {
            await reader.cancel("MULTIMODAL_PROGRESS_RESPONSE_TOO_LARGE");
          } catch {
            // The deterministic size rejection survives a concurrent close.
          }
          throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_TOO_LARGE");
        }
        chunks.push(value);
      }
    } catch (error) {
      try {
        await reader.cancel(
          upstreamTimedOut
            ? "MULTIMODAL_PROGRESS_ENDPOINT_TIMEOUT"
            : clientAborted()
              ? "MULTIMODAL_PROGRESS_CLIENT_CLOSED"
              : "MULTIMODAL_PROGRESS_RESPONSE_ABORTED",
        );
      } catch {
        // Cancellation is best-effort after the authoritative failure.
      }
      throw error;
    } finally {
      reader.releaseLock();
    }
    let source: string;
    try {
      source = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(
        chunks.map((chunk) => Buffer.from(chunk)),
      ));
    } catch {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_PROGRESS_RESPONSE_INVALID");
    }
    return validatedProgressSseBatch(source, kind, resourceId, cursor);
  } catch (error) {
    if (upstreamTimedOut) {
      throw new MultimodalIntakeRunnerError(
        504,
        "MULTIMODAL_PROGRESS_ENDPOINT_TIMEOUT",
        true,
      );
    }
    if (clientAborted()) {
      throw new DOMException("MULTIMODAL_PROGRESS_CLIENT_CLOSED", "AbortError");
    }
    if (error instanceof MultimodalIntakeRunnerError) throw error;
    throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_PROGRESS_ENDPOINT_UNAVAILABLE", true);
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abortFromClient);
  }
}

async function executeTrustedEndpoint(
  payload: string,
  expectedSkill: MultimodalSkillName,
  expectedOperation: string,
  expectedTraceId: string,
  expectedRequestDigest: string,
  expectedProjectId: string,
): Promise<Record<string, unknown>> {
  const trusted = trustedLoopbackEndpoint();
  if (!trusted) throw new MultimodalIntakeRunnerError(503, "MULTIMODAL_TRUSTED_ENDPOINT_NOT_CONFIGURED");
  if (Buffer.byteLength(payload, "utf8") > MAX_ENGINE_INPUT_BYTES) {
    throw new MultimodalIntakeRunnerError(413, "MULTIMODAL_REQUEST_TOO_LARGE");
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ENGINE_RESPONSE_WAIT_MS);
  try {
    const response = await fetch(trusted.executeUrl, {
      method: "POST",
      redirect: "error",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${trusted.token}`,
        "Content-Type": "application/json",
        "Content-Length": String(Buffer.byteLength(payload, "utf8")),
      },
      body: payload,
    });
    const contentType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
    if (contentType !== "application/json") {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_CONTENT_TYPE_INVALID");
    }
    const contentEncoding = response.headers.get("content-encoding")?.trim().toLowerCase();
    if (contentEncoding && contentEncoding !== "identity") {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_ENCODING_INVALID");
    }
    const declared = response.headers.get("content-length");
    if (declared && (!/^[0-9]{1,10}$/.test(declared) || Number(declared) > MAX_ENGINE_OUTPUT_BYTES)) {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_OUTPUT_TOO_LARGE");
    }
    const reader = response.body?.getReader();
    if (!reader) throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_INVALID");
    const chunks: Uint8Array[] = [];
    let observed = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        observed += value.byteLength;
        if (observed > MAX_ENGINE_OUTPUT_BYTES) {
          await reader.cancel("MULTIMODAL_ENGINE_OUTPUT_TOO_LARGE");
          throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_OUTPUT_TOO_LARGE");
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    if (declared && observed !== Number(declared)) {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_SIZE_INVALID");
    }
    const bytes = new Uint8Array(observed);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    let source: string;
    try {
      source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_RESPONSE_JSON_INVALID");
    }
    const parsed = record(parseStrictEngineJson(source), "MULTIMODAL_ENGINE_RESPONSE_INVALID", 502);
    return validateEngineEnvelope(
      { ...parsed, _http_status: response.status },
      expectedSkill,
      expectedOperation,
      expectedTraceId,
      expectedRequestDigest,
      expectedProjectId,
    );
  } catch (error) {
    if (error instanceof MultimodalIntakeRunnerError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new MultimodalIntakeRunnerError(
        504,
        "MULTIMODAL_ENGINE_OUTCOME_RECONCILIATION_REQUIRED",
        false,
      );
    }
    // fetch can reject after the trusted engine accepted and executed the
    // request (connection reset, truncated response, proxy failure).  The
    // exact key may be reconciled, but automatic re-execution is forbidden.
    throw new MultimodalIntakeRunnerError(
      503,
      "MULTIMODAL_ENGINE_OUTCOME_RECONCILIATION_REQUIRED",
      false,
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function executeMultimodalSkill(
  identity: MultimodalRunnerIdentity,
  body: MultimodalExecuteBody,
  idempotencyKey: string,
): Promise<Record<string, unknown>> {
  if (!identifierPattern.test(identity.tenantId) || !actorPattern.test(identity.actor)) {
    throw new MultimodalIntakeRunnerError(403, "MULTIMODAL_IDENTITY_INVALID");
  }
  if (!idempotencyPattern.test(idempotencyKey)) {
    throw new MultimodalIntakeRunnerError(400, "MULTIMODAL_IDEMPOTENCY_KEY_INVALID");
  }
  // The route checks the caller's exact AccountPermission. Keep this second
  // lookup here so direct callers also fail before endpoint selection/spawn.
  requiredMultimodalPermission(body.skill, body.operation);
  const engineProjectId = boundMultimodalProjectId(identity, body.projectId);
  const traceId = `trace_${createHash("sha256")
    .update(identity.tenantId)
    .update("\0")
    .update(engineProjectId)
    .update("\0")
    .update(idempotencyKey)
    .digest("hex")
    .slice(0, 32)}`;
  const requestDocument = {
    schema_version: "1.0.0",
    skill: body.skill,
    operation: body.operation,
    tenant_id: identity.tenantId,
    project_id: engineProjectId,
    actor_id: identity.actor,
    idempotency_key: idempotencyKey,
    trace_id: traceId,
    input: body.input,
  };
  const requestDigest = createHash("sha256")
    .update(canonicalStrictJson({
      execution_contract: executionContractVersion,
      schema_version: requestDocument.schema_version,
      skill: requestDocument.skill,
      operation: requestDocument.operation,
      tenant_id: requestDocument.tenant_id,
      project_id: requestDocument.project_id,
      actor_id: requestDocument.actor_id,
      idempotency_key: requestDocument.idempotency_key,
      input: requestDocument.input,
    }))
    .digest("hex");
  const payload = JSON.stringify(requestDocument);
  const response = trustedLoopbackEndpoint()
    ? await executeTrustedEndpoint(
      payload, body.skill, body.operation, traceId, requestDigest, engineProjectId,
    )
    : await executePython(
      payload, identity, engineProjectId, body.skill, body.operation, traceId, requestDigest,
    );
  const engineStatus = response._http_status;
  delete response._http_status;
  if (typeof engineStatus !== "number" || !Number.isInteger(engineStatus)) {
    throw new MultimodalIntakeRunnerError(502, "MULTIMODAL_ENGINE_STATUS_INVALID");
  }
  if (engineStatus !== 200) {
    const code = typeof response.code === "string" ? response.code : "MULTIMODAL_ENGINE_REJECTED";
    const retryable = response.retryable === true;
    throw new MultimodalIntakeRunnerError(engineStatus, code, retryable);
  }
  return response;
}
