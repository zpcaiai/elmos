import { randomUUID, sign } from "node:crypto";
import { lstatSync, readFileSync } from "node:fs";
import path from "node:path";

import type { NextRequest } from "next/server";
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

function validateInput(input: unknown): Record<string, unknown> | undefined {
  if (input === undefined) return undefined;
  const value = exactObject(input, [], ["files", "inventory", "target", "currentVersions"]);
  if (value.files !== undefined) {
    if (!value.files || typeof value.files !== "object" || Array.isArray(value.files)) {
      throw new FrtEngineProxyError(400, "FRT_SOURCE_FILES_INVALID");
    }
    const files = value.files as Record<string, unknown>;
    const entries = Object.entries(files);
    if (entries.length === 0 || entries.length > 512
      || entries.some(([name, content]) => !name || name.length > 512 || name.startsWith("/")
        || name.split("/").includes("..") || typeof content !== "string" || content.length > 1_000_000)) {
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
  ], ["input"]);
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
  return {
    skillId: body.skillId,
    action: body.action as FrtConsoleRunRequest["action"],
    idempotencyKey: body.idempotencyKey as string,
    workspaceId: body.workspaceId as string,
    projectId: body.projectId as string,
    environmentId: body.environmentId as string,
    releaseId: body.releaseId as string,
    sourceSnapshotDigest: body.sourceSnapshotDigest,
    policyVersion: body.policyVersion as string,
    risk: body.risk as FrtConsoleRunRequest["risk"],
    ...(body.input === undefined ? {} : { input: validateInput(body.input) }),
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
  return forward(context, scope, `/engine/v1/frt/skills/${value.skillId}/runs`,
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
        ...(value.input ? { input: value.input } : {}),
      }),
    });
}

export async function getFrtConsoleRun(
  request: NextRequest,
  runId: string,
  resource = "",
) {
  const context = authorizedContext(request, "workspace:view");
  const scope = consoleReadScope(context);
  return forward(context, scope, `/engine/v1/frt/runs/${runId}${resource}`, ["frt:read"]);
}

export async function transitionFrtConsoleRun(
  request: NextRequest,
  runId: string,
  operation: "claim" | "cancel" | "retry",
  expectedVersion: number,
) {
  const context = authorizedContext(request, "generation:execute");
  const scope = consoleReadScope(context);
  return forward(context, scope, `/engine/v1/frt/runs/${runId}/${operation}`, ["frt:run"], {
    method: "POST",
    body: JSON.stringify({ schemaVersion: "1.0", expectedVersion }),
  });
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
  const scope = consoleReadScope(context);
  const validated = validateFrtConsoleCompletion(completion);
  return forward(context, scope, `/engine/v1/frt/runs/${runId}/complete`, ["frt:run", "frt:evidence"], {
    method: "POST",
    body: JSON.stringify({ schemaVersion: "1.0", expectedVersion, completion: validated }),
  });
}

function consoleReadScope(context: { tenantId: string; actor: string }): Record<string, string> {
  return {
    organizationId: context.tenantId,
    tenantId: context.tenantId,
    workspaceId: "frt-console-read",
    projectId: "frt-console-read",
    accountId: context.actor,
    environmentId: "frt-console-read",
    releaseId: "frt-console-read",
  };
}
