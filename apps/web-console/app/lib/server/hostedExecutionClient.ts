import { createHash } from "node:crypto";
import type {
  GenerationArtifact,
  GenerationJob,
  GenerationJobCreateRequest,
} from "../contracts";
import { GenerationRunnerError } from "./generationRunner";
import { configuredControlPlaneBaseUrl } from "./trustedUpstream";

type AuthorizedContext = {
  tenantId: string;
  actor: string;
  accessToken?: string;
};

type ArtifactSummary = {
  role: string;
  filename: string;
  contentSha256: string;
  byteSize: number;
};

type ControlPlaneJob = {
  jobId: string;
  organizationId: string;
  actorId: string;
  status: "QUEUED" | "CLAIMED" | "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "CANCELLED" | "LOST";
  stage: string;
  progress: number;
  resultStatus: string;
  failureCode?: string;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  cancelRequested: boolean;
  artifacts?: ArtifactSummary[];
};

export type HostedArtifactTicket = {
  downloadUrl: string;
  filename: string;
  contentSha256: string;
  byteSize: number;
  expiresInSeconds: number;
};

export function hostedExecutionEnabled(): boolean {
  return process.env.ELMOS_HOSTED_EXECUTION_ENABLED === "true";
}

function baseUrl(): string {
  let configured: string | null;
  try {
    configured = configuredControlPlaneBaseUrl();
  } catch {
    throw new GenerationRunnerError(503, "CONTROL_PLANE_CONFIGURATION_INVALID");
  }
  if (!configured) throw new GenerationRunnerError(503, "CONTROL_PLANE_NOT_CONFIGURED");
  return configured;
}

function idempotencyKey(context: AuthorizedContext, analysisDigest: string): string {
  return createHash("sha256")
    .update(`${context.tenantId}\u0000${context.actor}\u0000${analysisDigest}`)
    .digest("hex")
    .slice(0, 48);
}

async function call<T>(
  context: AuthorizedContext,
  path: string,
  method: "GET" | "POST" | "DELETE",
  body?: unknown,
): Promise<T> {
  if (!context.accessToken) {
    throw new GenerationRunnerError(401, "ACCOUNT_ACCESS_TOKEN_REQUIRED");
  }
  const response = await fetch(`${baseUrl()}${path}`, {
    method,
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${context.accessToken}`,
      "X-ELMOS-Organization-ID": context.tenantId,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch((error: unknown) => {
    if (error instanceof Error && error.name === "TimeoutError") {
      throw new GenerationRunnerError(504, "CONTROL_PLANE_TIMEOUT");
    }
    throw new GenerationRunnerError(502, "CONTROL_PLANE_UNREACHABLE");
  });
  const text = await response.text();
  let payload: Record<string, unknown> = {};
  try {
    payload = text ? JSON.parse(text) as Record<string, unknown> : {};
  } catch {
    throw new GenerationRunnerError(502, "CONTROL_PLANE_RESPONSE_INVALID");
  }
  if (!response.ok) {
    const code = typeof payload.code === "string" ? payload.code : "CONTROL_PLANE_REJECTED";
    throw new GenerationRunnerError(response.status, code);
  }
  return payload as T;
}

function generationStatus(status: ControlPlaneJob["status"]): GenerationJob["status"] {
  switch (status) {
    case "QUEUED": return "QUEUED";
    case "CLAIMED":
    case "RUNNING": return "GENERATING";
    case "SUCCEEDED": return "COMPLETED";
    case "PARTIAL": return "PARTIAL";
    case "CANCELLED": return "CANCELLED";
    default: return "BLOCKED";
  }
}

function generationStage(job: ControlPlaneJob): GenerationJob["stage"] {
  if (job.status === "QUEUED") return "queued";
  if (job.status === "SUCCEEDED" || job.status === "PARTIAL") return "complete";
  if (job.status === "CANCELLED") return "cancelled";
  if (job.status === "FAILED" || job.status === "LOST") return "blocked";
  return "pipeline";
}

function mapJob(job: ControlPlaneJob): GenerationJob {
  const artifactRows = job.artifacts ?? [];
  const projectArchive = artifactRows.find((artifact) => artifact.role === "PROJECT_ARCHIVE");
  const artifacts: GenerationArtifact[] = artifactRows.map((artifact) => ({
    path: artifact.filename,
    sha256: artifact.contentSha256,
    ownership: "managed",
  }));
  const updatedAt = job.finishedAt ?? job.startedAt ?? job.createdAt;
  return {
    id: job.jobId,
    tenantId: job.organizationId,
    actor: job.actorId,
    createdAt: job.createdAt,
    updatedAt,
    status: generationStatus(job.status),
    stage: generationStage(job),
    progress: job.progress,
    resultStatus: job.resultStatus,
    artifactReady: Boolean(projectArchive),
    ...(projectArchive ? {
      artifactSha256: projectArchive.contentSha256,
      artifactSize: projectArchive.byteSize,
    } : {}),
    artifacts,
    ...(job.failureCode ? { reason: job.failureCode } : {}),
    logs: [{
      at: updatedAt,
      stream: "system",
      message: `Hosted execution: ${job.status} / ${job.stage}`,
    }],
    runtime: {
      status: "STOPPED",
      plans: [],
      updatedAt,
    },
  };
}

export async function createHostedGenerationJob(
  context: AuthorizedContext,
  request: GenerationJobCreateRequest,
): Promise<GenerationJob> {
  if (!request.approved || !/^[0-9a-f]{64}$/.test(request.analysisDigest)) {
    throw new GenerationRunnerError(409, "APPROVED_ANALYSIS_REQUIRED");
  }
  const accepted = await call<{ jobId: string }>(
    context,
    "/api/v1/execution/jobs",
    "POST",
    {
      businessLine: "GENERATION",
      jobKind: "project-synthesis",
      idempotencyKey: idempotencyKey(context, request.analysisDigest),
      payload: request,
      priority: 100,
      budgetWallSeconds: 3600,
      maxAttempts: 2,
    },
  );
  return getHostedGenerationJob(context, accepted.jobId);
}

export async function getHostedGenerationJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  return mapJob(await call<ControlPlaneJob>(
    context,
    `/api/v1/execution/jobs/${encodeURIComponent(jobId)}`,
    "GET",
  ));
}

export async function cancelHostedGenerationJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  await call<Record<string, unknown>>(
    context,
    `/api/v1/execution/jobs/${encodeURIComponent(jobId)}`,
    "DELETE",
  );
  return getHostedGenerationJob(context, jobId);
}

export async function hostedArtifactTicket(
  context: AuthorizedContext,
  jobId: string,
): Promise<HostedArtifactTicket> {
  return call<HostedArtifactTicket>(
    context,
    `/api/v1/execution/jobs/${encodeURIComponent(jobId)}/artifacts/PROJECT_ARCHIVE/download-ticket`,
    "POST",
  );
}
