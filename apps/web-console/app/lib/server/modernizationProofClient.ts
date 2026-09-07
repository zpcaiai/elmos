import { createHash } from "node:crypto";

import type { NextRequest } from "next/server";

import { authorize, GenerationRunnerError } from "./generationRunner";

export type ModernizationProofContext = {
  tenantId: string;
  actor: string;
  accessToken?: string;
};

export type ModernizationProofContract = {
  id: string;
  batch: number;
  name: string;
  dependencies: string[];
  canonicalSha256: string;
  executionClass: "CONTROL_PLANE" | "ISOLATED_RUNNER" | "INDEPENDENT_GATE";
  evidenceSlots: string[];
};

export type ModernizationProofJob = {
  jobId: string;
  organizationId: string;
  actorId: string;
  businessLine: "MODERNIZATION_PROOF";
  jobKind: string;
  status: "QUEUED" | "CLAIMED" | "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "CANCELLED" | "LOST";
  stage: string;
  progress: number;
  resultStatus: "NOT_RUN" | "PASSED" | "PARTIAL" | "FAILED" | "BLOCKED";
  failureCode?: string;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  cancelRequested: boolean;
  artifacts?: Array<{ role: string; filename: string; contentSha256: string; byteSize: number }>;
};

export type ModernizationProofSubmission = {
  targetSkillId: string;
  projectId: string;
  repositoryId: string;
  baselineCommit?: string;
  candidateCommit?: string;
  imageDigest?: string;
  policyDigest: string;
  inputs: Record<string, unknown>;
  evidence: Record<string, unknown>;
};

export class ModernizationProofClientError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

export function proofContext(request: NextRequest): ModernizationProofContext {
  try {
    return authorize(request, "modernization:execute");
  } catch (error) {
    if (error instanceof GenerationRunnerError) {
      throw new ModernizationProofClientError(error.status, error.message);
    }
    throw error;
  }
}

function controlPlaneBaseUrl(): string {
  const configured = process.env.ELMOS_CONTROL_PLANE_BASE_URL?.trim() ?? "";
  let parsed: URL;
  try { parsed = new URL(configured); }
  catch { throw new ModernizationProofClientError(503, "CONTROL_PLANE_NOT_CONFIGURED"); }
  const local = process.env.NODE_ENV !== "production" && ["127.0.0.1", "localhost"].includes(parsed.hostname);
  if ((parsed.protocol !== "https:" && !(local && parsed.protocol === "http:"))
      || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new ModernizationProofClientError(503, "CONTROL_PLANE_CONFIGURATION_INVALID");
  }
  return configured.replace(/\/+$/, "");
}

async function call<T>(
  context: ModernizationProofContext,
  path: string,
  method: "GET" | "POST" | "DELETE",
  body?: unknown,
): Promise<T> {
  if (!context.accessToken) throw new ModernizationProofClientError(401, "ACCOUNT_ACCESS_TOKEN_REQUIRED");
  let response: Response;
  try {
    response = await fetch(`${controlPlaneBaseUrl()}${path}`, {
      method,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${context.accessToken}`,
        "x-elmos-organization-id": context.tenantId,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    const code = error instanceof Error && error.name === "TimeoutError"
      ? "CONTROL_PLANE_TIMEOUT" : "CONTROL_PLANE_UNREACHABLE";
    throw new ModernizationProofClientError(code.endsWith("TIMEOUT") ? 504 : 502, code);
  }
  const text = await response.text();
  let payload: unknown;
  try { payload = text ? JSON.parse(text) : {}; }
  catch { throw new ModernizationProofClientError(502, "CONTROL_PLANE_RESPONSE_INVALID"); }
  if (!response.ok) {
    const code = typeof payload === "object" && payload && "code" in payload
      && typeof payload.code === "string" ? payload.code : "CONTROL_PLANE_REJECTED";
    throw new ModernizationProofClientError(response.status, code);
  }
  return payload as T;
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(",")}}`;
}

function idempotencyKey(context: ModernizationProofContext, body: ModernizationProofSubmission): string {
  return createHash("sha256")
    .update(`${context.tenantId}\u0000${context.actor}\u0000${canonicalJson(body)}`)
    .digest("hex").slice(0, 64);
}

export function listProofContracts(context: ModernizationProofContext): Promise<ModernizationProofContract[]> {
  return call(context, "/api/v1/modernization-proof/contracts", "GET");
}

export function subjectDigest(context: ModernizationProofContext, body: Omit<ModernizationProofSubmission, "targetSkillId" | "inputs" | "evidence">) {
  return call<{ organizationId: string; subjectDigest: string; canonicalizationVersion: number }>(
    context, "/api/v1/modernization-proof/subject-digest", "POST", body);
}

export async function createProofJob(
  context: ModernizationProofContext,
  body: ModernizationProofSubmission,
): Promise<{ jobId: string; status: string; requestDigest: string }> {
  return call(context, "/api/v1/execution/jobs", "POST", {
    businessLine: "MODERNIZATION_PROOF",
    idempotencyKey: idempotencyKey(context, body),
    payload: body,
    priority: 100,
    budgetWallSeconds: 3600,
    maxAttempts: 2,
  });
}

export function getProofJob(context: ModernizationProofContext, jobId: string): Promise<ModernizationProofJob> {
  return call(context, `/api/v1/execution/jobs/${encodeURIComponent(jobId)}`, "GET");
}

export async function cancelProofJob(context: ModernizationProofContext, jobId: string): Promise<ModernizationProofJob> {
  await call(context, `/api/v1/execution/jobs/${encodeURIComponent(jobId)}`, "DELETE");
  return getProofJob(context, jobId);
}
