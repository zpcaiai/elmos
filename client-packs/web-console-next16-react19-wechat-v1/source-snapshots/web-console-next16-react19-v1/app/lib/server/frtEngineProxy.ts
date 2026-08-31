import { createHash, randomUUID, sign } from "node:crypto";
import { lstatSync, readFileSync } from "node:fs";
import path from "node:path";

import type { NextRequest } from "next/server";
import { frtCatalog } from "../frtCatalog.generated";
import { authorize, GenerationRunnerError } from "./generationRunner";

const identifier = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}$/;
const skillId = /^FRT-[0-9]{4}$/;
const digest = /^sha256:[a-f0-9]{64}$/;
const actions = new Set(["PLAN", "ANALYZE", "EXECUTE", "VERIFY"]);
const risks = new Set(["R0", "R1", "R2", "R3", "R4", "R5"]);

export type FrtConsoleRunRequest = {
  skillId: string;
  action: "PLAN" | "ANALYZE" | "EXECUTE" | "VERIFY";
  idempotencyKey: string;
  workspaceId: string;
  projectId: string;
  environmentId: string;
  releaseId: string;
  sourceSnapshotDigest: string;
  policyVersion: string;
  risk: "R0" | "R1" | "R2" | "R3" | "R4" | "R5";
  verificationSubject?: { runId: string; resultDigest: string };
  input?: Record<string, unknown>;
};

export class FrtEngineProxyError extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(code);
  }
}

function authorizedContext(
  request: NextRequest,
  permission: Parameters<typeof authorize>[1],
): { tenantId: string; actor: string } {
  try {
    return authorize(request, permission);
  } catch (error) {
    if (error instanceof GenerationRunnerError) {
      throw new FrtEngineProxyError(error.status, error.code);
    }
    throw error;
  }
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function canonicalDigest(value: unknown): string {
  return `sha256:${createHash("sha256").update(canonical(value)).digest("hex")}`;
}

function engineUrl(): string {
  const configured = process.env.ELMOS_FRONTEND_ENGINE_URL?.trim() ?? "";
  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    throw new FrtEngineProxyError(503, "FRT_ENGINE_NOT_CONFIGURED");
  }
  const local = process.env.NODE_ENV !== "production"
    && parsed.protocol === "http:"
    && ["127.0.0.1", "localhost"].includes(parsed.hostname);
  if ((!local && parsed.protocol !== "https:") || parsed.username || parsed.password || parsed.hash) {
    throw new FrtEngineProxyError(503, "FRT_ENGINE_URL_REJECTED");
  }
  return parsed.href.replace(/\/$/, "");
}

function signingConfiguration() {
  const privateKeyPath = process.env.ELMOS_FRT_IDENTITY_PRIVATE_KEY_PATH?.trim() ?? "";
  const authority = process.env.ELMOS_FRT_IDENTITY_AUTHORITY?.trim() ?? "";
  const keyId = process.env.ELMOS_FRT_IDENTITY_KEY_ID?.trim() ?? "";
  if (!path.isAbsolute(privateKeyPath) || !identifier.test(authority) || !identifier.test(keyId)) {
    throw new FrtEngineProxyError(503, "FRT_IDENTITY_SIGNER_NOT_CONFIGURED");
  }
  let stats: ReturnType<typeof lstatSync>;
  let privateKey: string;
  try {
    stats = lstatSync(/* turbopackIgnore: true */ privateKeyPath);
    privateKey = readFileSync(/* turbopackIgnore: true */ privateKeyPath, "utf8");
  } catch {
    throw new FrtEngineProxyError(503, "FRT_IDENTITY_SIGNER_UNAVAILABLE");
  }
  if (stats.isSymbolicLink() || !stats.isFile() || stats.size > 16_384 || (stats.mode & 0o077) !== 0) {
    throw new FrtEngineProxyError(503, "FRT_IDENTITY_PRIVATE_KEY_UNSAFE");
  }
  return { authority, keyId, privateKey };
}

function exactObject(value: unknown, keys: readonly string[], optional: readonly string[] = []): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new FrtEngineProxyError(400, "FRT_CONSOLE_REQUEST_INVALID");
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set([...keys, ...optional]);
  if (keys.some(key => !Object.hasOwn(record, key)) || Object.keys(record).some(key => !allowed.has(key))) {
    throw new FrtEngineProxyError(400, "FRT_CONSOLE_REQUEST_INVALID");
  }
  return record;
}

function validateJsonStructure(value: unknown): void {
  const pending: Array<{ value: unknown; depth: number }> = [{ value, depth: 0 }];
  const unsafeKeys = new Set(["__proto__", "prototype", "constructor"]);
  let nodes = 0;
  while (pending.length) {
    const current = pending.pop()!;
    nodes += 1;
    if (nodes > 200_000 || current.depth > 32) {
      throw new FrtEngineProxyError(413, "FRT_INPUT_STRUCTURE_LIMIT_EXCEEDED");
    }
    if (typeof current.value === "string") {
      if (Buffer.byteLength(current.value, "utf8") > 1_000_000) {
        throw new FrtEngineProxyError(413, "FRT_INPUT_STRING_LIMIT_EXCEEDED");
      }
      continue;
    }
    if (typeof current.value === "number" && !Number.isFinite(current.value)) {
      throw new FrtEngineProxyError(400, "FRT_INPUT_NUMBER_INVALID");
    }
    if (current.value === null || ["boolean", "number"].includes(typeof current.value)) continue;
    if (Array.isArray(current.value)) {
      if (current.value.length > 20_000) {
        throw new FrtEngineProxyError(413, "FRT_INPUT_CONTAINER_LIMIT_EXCEEDED");
      }
      for (const item of current.value) pending.push({ value: item, depth: current.depth + 1 });
      continue;
    }
    if (typeof current.value !== "object") {
      throw new FrtEngineProxyError(400, "FRT_INPUT_JSON_TYPE_INVALID");
    }
    const entries = Object.entries(current.value as Record<string, unknown>);
    if (entries.length > 20_000) {
      throw new FrtEngineProxyError(413, "FRT_INPUT_CONTAINER_LIMIT_EXCEEDED");
    }
    for (const [key, item] of entries) {
      if (!key || key.length > 256 || unsafeKeys.has(key)) {
        throw new FrtEngineProxyError(400, "FRT_INPUT_KEY_REJECTED");
      }
      pending.push({ value: item, depth: current.depth + 1 });
    }
  }
}

function validateInput(
  requestedSkillId: string,
  action: FrtConsoleRunRequest["action"],
  input: unknown,
): Record<string, unknown> | undefined {
  if (action === "VERIFY" && input !== undefined) {
    throw new FrtEngineProxyError(400, "FRT_VERIFY_INPUT_NOT_ALLOWED");
  }
  const skill = frtCatalog.skills.find(item => item.id === requestedSkillId);
  if (!skill) throw new FrtEngineProxyError(400, "FRT_SKILL_UNKNOWN");
  const required = skill.executionContract.inputContract.required;
  const optional = skill.executionContract.inputContract.optional;
  if (input === undefined) {
    if (["ANALYZE", "EXECUTE"].includes(action) && required.length) {
      throw new FrtEngineProxyError(400, "FRT_HANDLER_INPUT_REQUIRED");
    }
    return undefined;
  }
  const value = exactObject(input, [], [...required, ...optional]);
  validateJsonStructure(value);
  if (["ANALYZE", "EXECUTE"].includes(action)
    && required.some(key => !Object.hasOwn(value, key))) {
    throw new FrtEngineProxyError(400, "FRT_HANDLER_INPUT_REQUIRED");
  }
  if (value.files !== undefined) {
    if (!value.files || typeof value.files !== "object" || Array.isArray(value.files)) {
      throw new FrtEngineProxyError(400, "FRT_SOURCE_FILES_INVALID");
    }
    const files = value.files as Record<string, unknown>;
    const entries = Object.entries(files);
    let totalBytes = 0;
    if (entries.length === 0 || entries.length > 512
      || entries.some(([name, content]) => {
        if (typeof content === "string") totalBytes += Buffer.byteLength(content, "utf8");
        return !name || name.length > 512 || name.startsWith("/") || name.includes("\\")
          || name.split("/").some(segment => !segment || segment === "." || segment === "..")
          || typeof content !== "string" || Buffer.byteLength(content, "utf8") > 1_000_000;
      }) || totalBytes > 16 * 1024 * 1024) {
      throw new FrtEngineProxyError(400, "FRT_SOURCE_FILES_INVALID");
    }
  }
  return value;
}

export function validateFrtConsoleRunRequest(value: unknown): FrtConsoleRunRequest {
  const body = exactObject(value, [
    "skillId",
    "action",
    "idempotencyKey",
    "workspaceId",
    "projectId",
    "environmentId",
    "releaseId",
    "sourceSnapshotDigest",
    "policyVersion",
    "risk",
  ], ["verificationSubject", "input"]);
  const texts = [
    body.idempotencyKey,
    body.workspaceId,
    body.projectId,
    body.environmentId,
    body.releaseId,
    body.policyVersion,
  ];
  if (typeof body.skillId !== "string" || !skillId.test(body.skillId)
    || typeof body.action !== "string" || !actions.has(body.action)
    || texts.some(value => typeof value !== "string" || !identifier.test(value))
    || typeof body.sourceSnapshotDigest !== "string" || !digest.test(body.sourceSnapshotDigest)
    || typeof body.risk !== "string" || !risks.has(body.risk)) {
    throw new FrtEngineProxyError(400, "FRT_CONSOLE_REQUEST_INVALID");
  }
  const requestedAction = body.action as FrtConsoleRunRequest["action"];
  const validatedInput = validateInput(body.skillId, requestedAction, body.input);
  let verificationSubject: FrtConsoleRunRequest["verificationSubject"];
  if (body.verificationSubject !== undefined) {
    const subject = exactObject(body.verificationSubject, ["runId", "resultDigest"]);
    if (requestedAction !== "VERIFY" || typeof subject.runId !== "string"
      || !/^[a-f0-9]{24}$/.test(subject.runId)
      || typeof subject.resultDigest !== "string" || !digest.test(subject.resultDigest)) {
      throw new FrtEngineProxyError(400, "FRT_VERIFICATION_SUBJECT_INVALID");
    }
    verificationSubject = { runId: subject.runId, resultDigest: subject.resultDigest };
  }
  if (requestedAction === "VERIFY" && verificationSubject === undefined) {
    throw new FrtEngineProxyError(400, "FRT_VERIFICATION_SUBJECT_REQUIRED");
  }
  const authoritativeSourceSnapshotDigest = requestedAction === "VERIFY"
    ? body.sourceSnapshotDigest
    : canonicalDigest(validatedInput ?? {});
  if (requestedAction !== "VERIFY" && body.sourceSnapshotDigest !== authoritativeSourceSnapshotDigest) {
    throw new FrtEngineProxyError(400, "FRT_SOURCE_SNAPSHOT_DIGEST_MISMATCH");
  }
  return {
    skillId: body.skillId,
    action: requestedAction,
    idempotencyKey: body.idempotencyKey as string,
    workspaceId: body.workspaceId as string,
    projectId: body.projectId as string,
    environmentId: body.environmentId as string,
    releaseId: body.releaseId as string,
    sourceSnapshotDigest: authoritativeSourceSnapshotDigest,
    policyVersion: body.policyVersion as string,
    risk: body.risk as FrtConsoleRunRequest["risk"],
    ...(verificationSubject === undefined ? {} : { verificationSubject }),
    ...(validatedInput === undefined ? {} : { input: validatedInput }),
  };
}

function identityToken(
  context: { tenantId: string; actor: string },
  scope: Record<string, string>,
  permissions: readonly ("frt:plan" | "frt:run" | "frt:read" | "frt:evidence")[],
): string {
  const signer = signingConfiguration();
  const now = new Date();
  const envelope = {
    schemaVersion: "1.0",
    authority: signer.authority,
    keyId: signer.keyId,
    claims: {
      schemaVersion: "1.0",
      subject: context.actor,
      permissions,
      scope,
      issuedAt: now.toISOString(),
      expiresAt: new Date(now.getTime() + 5 * 60_000).toISOString(),
      nonce: randomUUID(),
    },
  };
  const encoded = Buffer.from(canonical(envelope)).toString("base64url");
  const signature = sign(null, Buffer.from(canonical(envelope)), signer.privateKey).toString("base64url");
  return `${encoded}.${signature}`;
}

async function forward(
  context: { tenantId: string; actor: string },
  scope: Record<string, string>,
  pathname: string,
  permissions: readonly ("frt:plan" | "frt:run" | "frt:read" | "frt:evidence")[],
  init?: RequestInit,
): Promise<{ status: number; body: unknown }> {
  try {
    const response = await fetch(`${engineUrl()}${pathname}`, {
      ...init,
      headers: {
        ...(init?.body ? { "content-type": "application/json" } : {}),
        authorization: `Bearer ${identityToken(context, scope, permissions)}`,
      },
      signal: AbortSignal.timeout(15_000),
    });
    return { status: response.status, body: await response.json() };
  } catch (error) {
    if (error instanceof FrtEngineProxyError) throw error;
    throw new FrtEngineProxyError(502, "FRT_ENGINE_UNAVAILABLE");
  }
}

async function attachPersistedAudit(
  context: { tenantId: string; actor: string },
  scope: Record<string, string>,
  result: { status: number; body: unknown },
): Promise<{ status: number; body: unknown }> {
  if (result.status < 200 || result.status >= 300 || !result.body
    || typeof result.body !== "object" || Array.isArray(result.body)) return result;
  const body = result.body as Record<string, unknown>;
  if (typeof body.runId !== "string" || !/^[a-f0-9]{24}$/.test(body.runId)) return result;
  try {
    const audit = await forward(
      context,
      scope,
      `/engine/v1/frt/runs/${body.runId}/audit`,
      ["frt:read"],
    );
    if (audit.status !== 200 || !audit.body || typeof audit.body !== "object"
      || Array.isArray(audit.body)) return result;
    const events = (audit.body as Record<string, unknown>).audit;
    return Array.isArray(events)
      ? { ...result, body: { ...body, audit: events } }
      : result;
  } catch {
    // The mutation is already durable. A transient read failure must not turn
    // success into an ambiguous retry; client polling remains the fallback.
    return result;
  }
}

export async function createFrtConsoleRun(request: NextRequest, rawBody: unknown) {
  const context = authorizedContext(request, "generation:execute");
  const value = validateFrtConsoleRunRequest(rawBody);
  const scope = {
    organizationId: context.tenantId,
    tenantId: context.tenantId,
    workspaceId: value.workspaceId,
    projectId: value.projectId,
    accountId: context.actor,
    environmentId: value.environmentId,
    releaseId: value.releaseId,
  };
  const pathname = value.verificationSubject
    ? `/engine/v1/frt/skills/${value.skillId}/runs/${value.verificationSubject.runId}/verify`
    : `/engine/v1/frt/skills/${value.skillId}/runs`;
  const result = await forward(context, scope, pathname,
    value.action === "VERIFY" ? ["frt:run", "frt:evidence"] : ["frt:run"], {
      method: "POST",
      body: JSON.stringify({
        schemaVersion: "1.0",
        skillId: value.skillId,
        action: value.action,
        idempotencyKey: value.idempotencyKey,
        expectedVersion: 0,
        context: {
          ...scope,
          sourceSnapshotDigest: value.sourceSnapshotDigest,
          policyVersion: value.policyVersion,
          requestedBy: context.actor,
          risk: value.risk,
        },
        prerequisiteCertificates: [],
        evidence: [],
        ...(value.verificationSubject ? { verificationSubject: value.verificationSubject } : {}),
        ...(value.input ? { input: value.input } : {}),
      }),
    });
  return attachPersistedAudit(context, scope, result);
}

export async function getFrtConsoleRun(
  request: NextRequest,
  runId: string,
  resource = "",
) {
  const context = authorizedContext(request, "workspace:view");
  const scope = consoleResourceScope(request, context);
  return forward(context, scope, `/engine/v1/frt/runs/${runId}${resource}`, ["frt:read"]);
}

export async function transitionFrtConsoleRun(
  request: NextRequest,
  runId: string,
  operation: "claim" | "heartbeat" | "cancel" | "retry",
  expectedVersion: number,
) {
  const context = authorizedContext(request, "generation:execute");
  const scope = consoleResourceScope(request, context);
  const result = await forward(context, scope, `/engine/v1/frt/runs/${runId}/${operation}`, ["frt:run"], {
    method: "POST",
    body: JSON.stringify({ schemaVersion: "1.0", expectedVersion }),
  });
  return attachPersistedAudit(context, scope, result);
}

/**
 * Shape-only gate for a runner completion. Field-level validation, attestation
 * verification and the executor/verifier separation rule are enforced by the engine,
 * which is the only authority; re-deriving them here would let the two drift apart.
 * The completion object is forwarded byte-for-byte so the engine verifies the
 * signature over exactly what the runner signed.
 */
export function validateFrtConsoleCompletion(value: unknown): Record<string, unknown> {
  const completion = exactObject(value, [
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
  if (completion.schemaVersion !== "1.0"
    || typeof completion.runnerId !== "string" || !identifier.test(completion.runnerId)
    || typeof completion.exitStatus !== "string"
    || !["COMPLETED", "FAILED"].includes(completion.exitStatus)
    || !Array.isArray(completion.artifacts) || completion.artifacts.length > 256
    || !Array.isArray(completion.evidence) || completion.evidence.length > 256
    || typeof completion.signature !== "string" || !completion.signature.length) {
    throw new FrtEngineProxyError(400, "FRT_RUNNER_COMPLETION_INVALID");
  }
  return completion;
}

export async function completeFrtConsoleRun(
  request: NextRequest,
  runId: string,
  expectedVersion: number,
  completion: unknown,
) {
  const context = authorizedContext(request, "generation:execute");
  const scope = consoleResourceScope(request, context);
  const validated = validateFrtConsoleCompletion(completion);
  return forward(context, scope, `/engine/v1/frt/runs/${runId}/complete`, ["frt:run", "frt:evidence"], {
    method: "POST",
    body: JSON.stringify({ schemaVersion: "1.0", expectedVersion, completion: validated }),
  });
}

function consoleResourceScope(
  request: NextRequest,
  context: { tenantId: string; actor: string },
): Record<string, string> {
  const url = new URL(request.url);
  const values = {
    workspaceId: url.searchParams.get("workspaceId") ?? "",
    projectId: url.searchParams.get("projectId") ?? "",
    environmentId: url.searchParams.get("environmentId") ?? "",
    releaseId: url.searchParams.get("releaseId") ?? "",
  };
  if (Object.values(values).some(value => !identifier.test(value))) {
    throw new FrtEngineProxyError(400, "FRT_RESOURCE_SCOPE_INVALID");
  }
  return {
    organizationId: context.tenantId,
    tenantId: context.tenantId,
    workspaceId: values.workspaceId,
    projectId: values.projectId,
    accountId: context.actor,
    environmentId: values.environmentId,
    releaseId: values.releaseId,
  };
}
