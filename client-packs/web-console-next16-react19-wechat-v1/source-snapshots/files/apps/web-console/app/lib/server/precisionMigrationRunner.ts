import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import type { NextRequest } from "next/server";

import {
  authorize,
  GenerationRunnerError,
} from "./generationRunner";

type AuthorizedContext = { tenantId: string; actor: string; accessToken?: string };

const executeFile = promisify(execFile);
const jobIdPattern = /^pmj-[0-9a-f]{32}$/;
const artifactPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const bundledRepositoryRoot = path.resolve(/* turbopackIgnore: true */ process.cwd(), "../..");

export class PrecisionMigrationRunnerError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

type RunnerConfig = {
  repositoryRoot: string;
  jobRoot: string;
  evidenceRoots: string[];
  trustStore?: string;
  maxActive: number;
  maxJobs: number;
  maxBytes: number;
};

function confined(base: string, candidate: string): string {
  const resolvedBase = realpathSync(/* turbopackIgnore: true */ base);
  const resolved = realpathSync(/* turbopackIgnore: true */ candidate);
  if (resolved !== resolvedBase && !resolved.startsWith(`${resolvedBase}${path.sep}`)) {
    throw new PrecisionMigrationRunnerError(403, "ARTIFACT_PATH_NOT_CONFINED");
  }
  return resolved;
}

function positiveInteger(name: string, fallback: number): number {
  const parsed = Number.parseInt(process.env[name] ?? String(fallback), 10);
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    throw new PrecisionMigrationRunnerError(503, `${name}_INVALID`);
  }
  return parsed;
}

function configuration(): RunnerConfig {
  const repositoryRoot = path.resolve(/* turbopackIgnore: true */ process.env.ELMOS_REPOSITORY_ROOT ?? bundledRepositoryRoot);
  const configuredJobRoot = process.env.ELMOS_PRECISION_MIGRATION_JOB_ROOT?.trim();
  const configuredEvidence = process.env.ELMOS_PRECISION_EVIDENCE_ROOTS?.trim();
  const trustStore = process.env.ELMOS_PRECISION_TRUST_STORE?.trim();
  if (process.env.NODE_ENV === "production" && (!configuredJobRoot || !configuredEvidence || !trustStore)) {
    throw new PrecisionMigrationRunnerError(503, "PRECISION_MIGRATION_RUNNER_NOT_CONFIGURED");
  }
  return {
    repositoryRoot,
    jobRoot: path.resolve(/* turbopackIgnore: true */ configuredJobRoot || path.join(tmpdir(), "elmos-precision-migration-jobs")),
    evidenceRoots: (configuredEvidence || repositoryRoot).split(path.delimiter).filter(Boolean).map((value) => path.resolve(/* turbopackIgnore: true */ value)),
    ...(trustStore ? { trustStore: path.resolve(/* turbopackIgnore: true */ trustStore) } : {}),
    maxActive: positiveInteger("ELMOS_PRECISION_MAX_ACTIVE_JOBS", 2),
    maxJobs: positiveInteger("ELMOS_PRECISION_MAX_RETAINED_JOBS", 100),
    maxBytes: positiveInteger("ELMOS_PRECISION_MAX_TENANT_BYTES", 1024 * 1024 * 1024),
  };
}

function commonArguments(config: RunnerConfig, context: AuthorizedContext): string[] {
  return [
    "--root", config.jobRoot,
    "--tenant", context.tenantId,
    "--actor", context.actor,
    "--max-active", String(config.maxActive),
    "--max-jobs", String(config.maxJobs),
    "--max-bytes", String(config.maxBytes),
  ];
}

async function invoke(command: string, context: AuthorizedContext, extra: string[]): Promise<Record<string, unknown>> {
  const config = configuration();
  const script = confined(config.repositoryRoot, path.join(config.repositoryRoot, "scripts/precision_migration/jobs.py"));
  const args = [script, command, ...commonArguments(config, context), ...extra];
  try {
    const { stdout } = await executeFile(process.env.PYTHON ?? "python3", args, {
      cwd: config.repositoryRoot,
      timeout: 15_000,
      maxBuffer: 2 * 1024 * 1024,
      env: {
        PATH: process.env.PATH ?? "",
        PYTHONDONTWRITEBYTECODE: "1",
        NODE_ENV: process.env.NODE_ENV ?? "development",
      },
    });
    return JSON.parse(stdout) as Record<string, unknown>;
  } catch (error) {
    const candidate = error as { stderr?: string; killed?: boolean };
    if (candidate.killed) throw new PrecisionMigrationRunnerError(504, "PRECISION_RUNNER_TIMEOUT");
    try {
      const parsed = JSON.parse(candidate.stderr ?? "") as { error?: string };
      const message = parsed.error ?? "PRECISION_RUNNER_BLOCKED";
      const status = /quota/.test(message) ? 429 : /not found/.test(message) ? 404 : 400;
      throw new PrecisionMigrationRunnerError(status, message);
    } catch (parseError) {
      if (parseError instanceof PrecisionMigrationRunnerError) throw parseError;
      throw new PrecisionMigrationRunnerError(500, "PRECISION_RUNNER_FAILED");
    }
  }
}

function startArguments(config: RunnerConfig): string[] {
  return [
    "--start",
    ...config.evidenceRoots.flatMap((root) => ["--evidence-root", root]),
    ...(config.trustStore ? ["--trust-store", config.trustStore] : []),
  ];
}

export function precisionContext(request: NextRequest, permission: "generation:execute" | "admin:operate" = "generation:execute"): AuthorizedContext {
  try {
    return authorize(request, permission);
  } catch (error) {
    if (error instanceof GenerationRunnerError) {
      throw new PrecisionMigrationRunnerError(error.status, error.message);
    }
    throw error;
  }
}

export async function createPrecisionJob(context: AuthorizedContext, body: unknown): Promise<Record<string, unknown>> {
  const encoded = JSON.stringify(body);
  if (Buffer.byteLength(encoded, "utf-8") > 1024 * 1024) {
    throw new PrecisionMigrationRunnerError(413, "PRECISION_REQUEST_TOO_LARGE");
  }
  const temporary = await mkdtemp(path.join(tmpdir(), "elmos-precision-request-"));
  const requestPath = path.join(temporary, "request.json");
  try {
    await writeFile(requestPath, encoded, { encoding: "utf-8", mode: 0o600, flag: "wx" });
    const config = configuration();
    return await invoke("submit", context, ["--request", requestPath, ...startArguments(config)]);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

export function listPrecisionJobs(context: AuthorizedContext): Promise<Record<string, unknown>> {
  return invoke("list", context, []);
}

export function getPrecisionJob(context: AuthorizedContext, jobId: string): Promise<Record<string, unknown>> {
  if (!jobIdPattern.test(jobId)) throw new PrecisionMigrationRunnerError(400, "JOB_ID_INVALID");
  return invoke("status", context, ["--job-id", jobId]);
}

export function cancelPrecisionJob(context: AuthorizedContext, jobId: string): Promise<Record<string, unknown>> {
  if (!jobIdPattern.test(jobId)) throw new PrecisionMigrationRunnerError(400, "JOB_ID_INVALID");
  return invoke("cancel", context, ["--job-id", jobId]);
}

export function retryPrecisionJob(context: AuthorizedContext, jobId: string): Promise<Record<string, unknown>> {
  if (!jobIdPattern.test(jobId)) throw new PrecisionMigrationRunnerError(400, "JOB_ID_INVALID");
  const config = configuration();
  return invoke("retry", context, ["--job-id", jobId, ...startArguments(config)]);
}

export function archiveExpiredPrecisionJobs(context: AuthorizedContext, olderThanSeconds: number): Promise<Record<string, unknown>> {
  if (!Number.isSafeInteger(olderThanSeconds) || olderThanSeconds < 3600) {
    throw new PrecisionMigrationRunnerError(400, "RETENTION_INVALID");
  }
  return invoke("gc", context, ["--older-than-seconds", String(olderThanSeconds)]);
}

export async function readPrecisionArtifact(
  context: AuthorizedContext,
  jobId: string,
  artifactName: string,
): Promise<{ content: Buffer; mediaType: string; fileName: string }> {
  if (!jobIdPattern.test(jobId) || !artifactPattern.test(artifactName)) {
    throw new PrecisionMigrationRunnerError(400, "ARTIFACT_ID_INVALID");
  }
  const job = await getPrecisionJob(context, jobId);
  const artifacts = Array.isArray(job.artifacts) ? job.artifacts : [];
  const artifact = artifacts.find((item) => {
    if (typeof item !== "object" || item === null) return false;
    const uri = (item as { uri?: unknown }).uri;
    return typeof uri === "string" && path.basename(fileURLToPath(uri)) === artifactName;
  }) as { uri?: string; media_type?: string; digest?: string; size_bytes?: number } | undefined;
  if (!artifact?.uri) throw new PrecisionMigrationRunnerError(404, "ARTIFACT_NOT_FOUND");
  const config = configuration();
  const tenantDigest = createHash("sha256").update(context.tenantId).digest("hex");
  const exactJobRoot = path.join(config.jobRoot, "tenants", tenantDigest, "jobs", jobId);
  const file = confined(exactJobRoot, fileURLToPath(artifact.uri));
  const content = await readFile(/* turbopackIgnore: true */ file);
  const observedDigest = `sha256:${createHash("sha256").update(content).digest("hex")}`;
  if (artifact.digest !== observedDigest || artifact.size_bytes !== content.byteLength) {
    throw new PrecisionMigrationRunnerError(409, "ARTIFACT_INTEGRITY_MISMATCH");
  }
  return {
    content,
    mediaType: artifact.media_type ?? "application/octet-stream",
    fileName: artifactName,
  };
}
