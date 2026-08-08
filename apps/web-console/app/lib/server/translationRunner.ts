import { createHash, randomUUID } from "node:crypto";
import { spawn, type ChildProcess } from "node:child_process";
import { createReadStream, existsSync, statSync } from "node:fs";
import {
  access,
  mkdir,
  readFile,
  realpath,
  rename,
  stat,
  writeFile,
} from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import path from "node:path";
import type { NextRequest } from "next/server";
import type {
  TranslationJob,
  TranslationJobLog,
  TranslationCapabilityResponse,
  TranslationLanguageId,
} from "../contracts";
import {
  authorize as authorizeLocalRunner,
  GenerationRunnerError,
  health as generationRunnerHealth,
} from "./generationRunner";
import { readTranslationCapability, resolveRepositoryRoot } from "./translationRoutes";
import { repositoryTranslationWorkspace } from "./repositoryWorkspaceProxy";
import { beginMeteredExecution, type MeteredExecution } from "./commercialUsageProducer";
import {
  DurableJobLease,
  DurableLeaseError,
  durableQueueConfiguration,
} from "./durableJobLease";

type AuthorizedContext = ReturnType<typeof authorizeLocalRunner>;
type TranslationRunnerConfig = {
  root: string;
  repositoryRoot: string;
  sourceRoot: string;
  casesRoot: string;
  uv: string;
  executor: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT";
  containerEngine?: string;
  containerImage?: string;
};

type TranslationProcessState = {
  active: Map<string, ChildProcess>;
  scheduled: Set<string>;
  cancelled: Set<string>;
};

const globalState = globalThis as typeof globalThis & {
  __elmosTranslationRunnerState?: TranslationProcessState;
};
const state = globalState.__elmosTranslationRunnerState ??= {
  active: new Map<string, ChildProcess>(),
  scheduled: new Set<string>(),
  cancelled: new Set<string>(),
};
state.active ??= new Map<string, ChildProcess>();
state.scheduled ??= new Set<string>();
state.cancelled ??= new Set<string>();

const identifierPattern = /^[a-z0-9][a-z0-9._-]{2,80}$/;
const jobIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const digestPattern = /^[0-9a-f]{64}$/;
const immutableImagePattern = /^[^@\s]+@sha256:[0-9a-f]{64}$/;
const languages = new Set<TranslationLanguageId>([
  "java",
  "csharp",
  "go",
  "rust",
  "python",
  "typescript",
]);
const sensitivePattern = /(authorization|token|secret|password|cookie|api[-_]?key)\s*[:=]\s*\S+/gi;

export type TranslationRunnerHealth = {
  status: "READY" | "DISABLED" | "BLOCKED";
  persistence: "FILESYSTEM_ATOMIC";
  auth: "BEARER_TENANT_BOUND";
  isolation: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT" | "NOT_CONFIGURED";
  recovery: "PERSISTENT_RECONCILIATION";
  sourceStorage: "READ_ONLY" | "NOT_RUN" | "BLOCKED";
  activeJobs: number;
  reason?: string;
  checkedAt: string;
};

function fail(status: number, code: string): never {
  throw new GenerationRunnerError(status, code);
}

function confined(base: string, ...segments: string[]): string {
  const candidate = path.resolve(/* turbopackIgnore: true */ base, ...segments);
  if (candidate !== base && !candidate.startsWith(`${base}${path.sep}`)) {
    fail(400, "TRANSLATION_PATH_CONFINEMENT_FAILED");
  }
  return candidate;
}

function runnerConfig(): TranslationRunnerConfig {
  if (process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true") {
    fail(503, "LOCAL_RUNNER_NOT_ENABLED");
  }
  const root = process.env.ELMOS_LOCAL_RUNNER_ROOT;
  const sourceRoot = process.env.ELMOS_TRANSLATION_SOURCE_ROOT;
  const casesRoot = process.env.ELMOS_TRANSLATION_CASES_ROOT;
  const uv = process.env.ELMOS_UV_PATH;
  const executor = process.env.ELMOS_LOCAL_RUNNER_EXECUTOR;
  if (
    !root || !path.isAbsolute(root)
    || !sourceRoot || !path.isAbsolute(sourceRoot)
    || !casesRoot || !path.isAbsolute(casesRoot)
    || !uv || !path.isAbsolute(uv)
  ) {
    fail(503, "TRANSLATION_RUNNER_PATHS_NOT_CONFIGURED");
  }
  if (!["ROOTLESS_CONTAINER", "HOST_DEVELOPMENT"].includes(executor ?? "")) {
    fail(503, "LOCAL_RUNNER_EXECUTOR_NOT_CONFIGURED");
  }
  if (executor === "HOST_DEVELOPMENT" && process.env.NODE_ENV === "production") {
    fail(503, "HOST_EXECUTOR_FORBIDDEN_IN_PRODUCTION");
  }
  const repositoryRoot = resolveRepositoryRoot();
  const resolved = {
    root: path.resolve(/* turbopackIgnore: true */ root),
    repositoryRoot: path.resolve(/* turbopackIgnore: true */ repositoryRoot),
    sourceRoot: path.resolve(/* turbopackIgnore: true */ sourceRoot),
    casesRoot: path.resolve(/* turbopackIgnore: true */ casesRoot),
    uv: path.resolve(/* turbopackIgnore: true */ uv),
  };
  if (
    resolved.root === path.parse(resolved.root).root
    || resolved.root === resolved.repositoryRoot
    || resolved.repositoryRoot.startsWith(`${resolved.root}${path.sep}`)
    || resolved.sourceRoot === resolved.root
    || resolved.sourceRoot.startsWith(`${resolved.root}${path.sep}`)
    || resolved.casesRoot === resolved.root
    || resolved.casesRoot.startsWith(`${resolved.root}${path.sep}`)
  ) {
    fail(503, "TRANSLATION_RUNNER_ROOT_UNSAFE");
  }
  for (const required of [
    resolved.repositoryRoot,
    resolved.sourceRoot,
    resolved.casesRoot,
    resolved.uv,
    path.join(/* turbopackIgnore: true */ resolved.repositoryRoot, "engines/polyglot-route-engine"),
  ]) {
    if (!existsSync(/* turbopackIgnore: true */ required)) {
      fail(503, "TRANSLATION_RUNNER_EXECUTION_ASSET_MISSING");
    }
  }
  const containerEngine = process.env.ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE;
  const containerImage = process.env.ELMOS_TRANSLATION_RUNNER_IMAGE;
  if (executor === "ROOTLESS_CONTAINER") {
    if (
      !containerEngine
      || !path.isAbsolute(containerEngine)
      || !existsSync(containerEngine)
      || !["docker", "podman"].includes(path.basename(containerEngine))
    ) {
      fail(503, "ROOTLESS_CONTAINER_ENGINE_NOT_CONFIGURED");
    }
    if (!containerImage || !immutableImagePattern.test(containerImage)) {
      fail(503, "TRANSLATION_RUNNER_IMAGE_NOT_IMMUTABLE");
    }
  }
  return {
    ...resolved,
    executor: executor as TranslationRunnerConfig["executor"],
    containerEngine,
    containerImage,
  };
}

export function authorizeTranslation(request: NextRequest): AuthorizedContext {
  return authorizeLocalRunner(request, "translation:execute");
}

function jobRoot(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  jobId: string,
): string {
  if (!jobIdPattern.test(jobId)) fail(400, "TRANSLATION_JOB_ID_INVALID");
  return confined(runner.root, "tenants", context.tenantId, "translation-jobs", jobId);
}

function jobFile(runner: TranslationRunnerConfig, context: AuthorizedContext, jobId: string): string {
  return confined(jobRoot(runner, context, jobId), "job.json");
}

function key(context: AuthorizedContext, jobId: string): string {
  return `${context.tenantId}:${jobId}`;
}

function redact(value: string): string {
  return value.replace(sensitivePattern, "$1=[REDACTED]").slice(0, 4_000);
}

function appendLog(job: TranslationJob, stream: TranslationJobLog["stream"], raw: string): void {
  for (const line of raw.split(/\r?\n/)) {
    const message = redact(line).trim();
    if (!message) continue;
    job.logs.push({ at: new Date().toISOString(), stream, message });
    if (job.logs.length > 400) job.logs.shift();
  }
}

async function atomicJson(destination: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  await rename(temporary, destination);
}

async function persist(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<void> {
  job.updatedAt = new Date().toISOString();
  await atomicJson(jobFile(runner, context, job.id), job);
}

async function sha256File(file: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
}

async function materializedDirectory(base: string, identifier: string, code: string): Promise<string> {
  if (!identifierPattern.test(identifier)) fail(400, `${code}_ID_INVALID`);
  const candidate = confined(base, identifier);
  let resolved: string;
  try {
    resolved = await realpath(candidate);
  } catch {
    fail(400, `${code}_NOT_FOUND`);
  }
  if (resolved !== candidate || !resolved.startsWith(`${base}${path.sep}`)) {
    fail(400, `${code}_PATH_UNSAFE`);
  }
  const details = await stat(resolved);
  if (!details.isDirectory()) fail(400, `${code}_NOT_DIRECTORY`);
  return resolved;
}

function command(
  runner: TranslationRunnerConfig,
  job: TranslationJob,
  source: string,
  cases: string,
  pipeline: string,
): { executable: string; args: string[] } {
  const routeArgs = [
    "repository-pipeline",
    "--repository", source,
    "--repository-ref", job.repositoryRef,
    "--source-language", job.sourceLanguage,
    "--target-language", job.targetLanguage,
    "--cases-directory", cases,
    "--output", pipeline,
  ];
  if (runner.executor === "HOST_DEVELOPMENT") {
    return {
      executable: runner.uv,
      args: [
        "--directory",
        path.join(/* turbopackIgnore: true */ runner.repositoryRoot, "engines/polyglot-route-engine"),
        "run",
        "--locked",
        "elmos-polyglot-route",
        ...routeArgs,
      ],
    };
  }
  return {
    executable: runner.containerEngine ?? "",
    args: [
      "run", "--rm",
      "--network", "none",
      "--read-only",
      "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m",
      "--cap-drop", "ALL",
      "--security-opt", "no-new-privileges",
      "--pids-limit", "512",
      "--memory", "3g",
      "--cpus", "2",
      "--mount", `type=bind,source=${runner.repositoryRoot},destination=/elmos,readonly`,
      "--mount", `type=bind,source=${source},destination=/source,readonly`,
      "--mount", `type=bind,source=${cases},destination=/cases,readonly`,
      "--mount", `type=bind,source=${pipeline},destination=/work`,
      "--env", "PYTHONPATH=/elmos/engines/polyglot-route-engine/src",
      runner.containerImage ?? "",
      "python", "-m", "elmos_polyglot_route.cli",
      ...routeArgs.map((argument) => argument
        .replace(source, "/source")
        .replace(cases, "/cases")
        .replace(pipeline, "/work")),
    ],
  };
}

async function runChild(
  executable: string,
  args: string[],
  job: TranslationJob,
  processKey: string,
): Promise<number> {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, {
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, NO_COLOR: "1" },
    });
    state.active.set(processKey, child);
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 5_000).unref();
    }, 20 * 60_000);
    child.stdout.on("data", (chunk: Buffer) => appendLog(job, "stdout", chunk.toString("utf-8")));
    child.stderr.on("data", (chunk: Buffer) => appendLog(job, "stderr", chunk.toString("utf-8")));
    child.once("error", reject);
    child.once("close", (exitCode) => {
      clearTimeout(timer);
      state.active.delete(processKey);
      resolve(exitCode ?? 1);
    });
  });
}

async function execute(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<void> {
  const processKey = key(context, job.id);
  state.scheduled.delete(processKey);
  if (state.cancelled.has(processKey)) return;
  let requeued = false;
  let queueLease: DurableJobLease | null = null;
  let leaseHeartbeat: NodeJS.Timeout | null = null;
  let metering: MeteredExecution | null = null;
  try {
    try {
      queueLease = await DurableJobLease.acquire({
        configuration: durableQueueConfiguration(runner.root, "translation"),
        tenantId: context.tenantId,
        jobId: job.id,
        createdAt: job.createdAt,
        inputDigest: createHash("sha256").update(JSON.stringify({
          repositoryRef: job.repositoryRef,
          casesBundleId: job.casesBundleId,
          sourceLanguage: job.sourceLanguage,
          targetLanguage: job.targetLanguage,
        })).digest("hex"),
      });
      leaseHeartbeat = setInterval(() => {
        void queueLease?.heartbeat().catch(() => {
          state.active.get(processKey)?.kill("SIGTERM");
        });
      }, queueLease.heartbeatIntervalMs);
      leaseHeartbeat.unref();
    } catch (error) {
      if (error instanceof DurableLeaseError && error.retryable) {
        job.status = "QUEUED";
        job.stage = "queued";
        job.reason = error.code;
        appendLog(job, "system", `Queue admission delayed: ${error.code}.`);
        await persist(runner, context, job);
        state.scheduled.add(processKey);
        requeued = true;
        setTimeout(
          () => void execute(runner, context, job),
          1_000 + Math.floor(Math.random() * 2_000),
        ).unref();
        return;
      }
      throw error;
    }
    metering = await beginMeteredExecution(`translation-${job.id}`);
    const source = await materializedDirectory(
      runner.sourceRoot,
      job.workspaceId,
      "TRANSLATION_SOURCE_WORKSPACE",
    );
    const cases = await materializedDirectory(
      runner.casesRoot,
      job.casesBundleId,
      "TRANSLATION_CASES_BUNDLE",
    );
    const pipeline = confined(jobRoot(runner, context, job.id), "pipeline");
    await mkdir(pipeline, { recursive: true, mode: 0o700 });
    job.status = "RUNNING";
    job.stage = "pipeline";
    job.progress = 15;
    appendLog(job, "system", `Pipeline started with ${runner.executor}; source and cases are read-only.`);
    await persist(runner, context, job);
    const invocation = command(runner, job, source, cases, pipeline);
    const exitCode = await runChild(invocation.executable, invocation.args, job, processKey);
    if (state.cancelled.has(processKey)) {
      job.status = "CANCELLED";
      job.stage = "cancelled";
      job.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
      job.progress = 100;
      await persist(runner, context, job);
      return;
    }
    if (exitCode !== 0) fail(409, "TRANSLATION_PIPELINE_BLOCKED");
    const report = JSON.parse(
      await readFile(confined(pipeline, "repository-pipeline-report.json"), "utf-8"),
    ) as Record<string, unknown>;
    const artifact = report.artifact as Record<string, unknown> | undefined;
    const artifactPath = confined(pipeline, "repository-migration-artifact.zip");
    const artifactInfo = await stat(artifactPath);
    const digest = await sha256File(artifactPath);
    if (
      !["COMPLETE", "PARTIAL"].includes(String(report.status))
      || !artifact
      || artifact.path !== "repository-migration-artifact.zip"
      || artifact.sha256 !== digest
      || artifact.bytes !== artifactInfo.size
      || !digestPattern.test(digest)
      || report.independent_verification_status !== "NOT_RUN"
      || report.external_verification_status !== "NOT_RUN"
      || report.certification_status !== "NOT_CERTIFIED"
    ) {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }
    job.artifactSha256 = digest;
    job.artifactSize = artifactInfo.size;
    job.snapshotSha256 = String(report.snapshot_sha256);
    job.readyCount = Number(report.ready_count);
    job.workUnitCount = Number(report.work_unit_count);
    job.includedUnitCount = Number(report.included_unit_count);
    job.statusCounts = report.status_counts as Record<string, number>;
    job.buildVerification = report.build_verification as TranslationJob["buildVerification"];
    job.stage = "metering";
    job.progress = 99;
    job.artifactReady = false;
    await metering?.finish(true);
    metering = null;
    job.status = report.status as "COMPLETE" | "PARTIAL";
    job.stage = "complete";
    job.progress = 100;
    job.artifactReady = true;
    appendLog(job, "system", `Pipeline ${job.status}; artifact digest ${digest}.`);
    await persist(runner, context, job);
  } catch (error) {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (meteringError) {
        error = meteringError;
      }
      metering = null;
    }
    if (job.status === "CANCELLED") return;
    job.status = "BLOCKED";
    job.stage = "blocked";
    job.progress = 100;
    job.artifactReady = false;
    job.reason = error instanceof Error ? error.message : "TRANSLATION_PIPELINE_BLOCKED";
    appendLog(job, "system", `Pipeline blocked: ${job.reason}`);
    await persist(runner, context, job);
  } finally {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (error) {
        job.status = "BLOCKED";
        job.stage = "blocked";
        job.artifactReady = false;
        job.reason = error instanceof Error ? error.message : "USAGE_SETTLEMENT_FAILED";
        await persist(runner, context, job);
      }
    }
    state.active.delete(processKey);
    if (leaseHeartbeat) clearInterval(leaseHeartbeat);
    if (queueLease) {
      const outcome = job.status === "COMPLETE" || job.status === "PARTIAL"
        ? "SUCCEEDED"
        : job.status === "CANCELLED"
          ? "CANCELLED"
          : job.status === "BLOCKED"
            ? "BLOCKED"
            : "FAILED";
      try {
        await queueLease.release(outcome);
      } catch {
        job.status = "BLOCKED";
        job.stage = "blocked";
        job.reason = "QUEUE_LEASE_RELEASE_FAILED";
        await persist(runner, context, job);
      }
    }
    if (!requeued) {
      state.scheduled.delete(processKey);
      state.cancelled.delete(processKey);
    }
  }
}

function schedule(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): void {
  const processKey = key(context, job.id);
  if (state.active.has(processKey) || state.scheduled.has(processKey)) return;
  state.scheduled.add(processKey);
  setImmediate(() => void execute(runner, context, job));
}

export async function createTranslationJob(
  context: AuthorizedContext,
  request: {
    workspaceId?: string;
    repositoryWorkspaceId?: string;
    casesBundleId?: string;
    sourceLanguage?: TranslationLanguageId;
    targetLanguage?: TranslationLanguageId;
  },
): Promise<TranslationJob> {
  const runner = runnerConfig();
  const sourceLanguage = request.sourceLanguage;
  const targetLanguage = request.targetLanguage;
  if (
    !sourceLanguage || !targetLanguage
    || !languages.has(sourceLanguage) || !languages.has(targetLanguage)
    || sourceLanguage === targetLanguage
  ) {
    fail(400, "TRANSLATION_ROUTE_INVALID");
  }
  const capability = readTranslationCapability();
  const route = capability.routes.find(
    (candidate) => candidate.source === sourceLanguage && candidate.target === targetLanguage,
  );
  if (!route || route.localExecution !== "PASSED") {
    fail(409, "TRANSLATION_ROUTE_NOT_LOCALLY_EXECUTABLE");
  }
  let workspaceId = request.workspaceId ?? "";
  const casesBundleId = request.casesBundleId ?? "";
  let repositoryWorkspaceId: string | undefined;
  let repositoryCommit: string | undefined;
  if (request.repositoryWorkspaceId) {
    const materialized = await repositoryTranslationWorkspace({
      tenantId: context.tenantId,
      actor: context.actor,
      accessToken: context.accessToken,
      workspaceId: request.repositoryWorkspaceId,
      sourceRoot: runner.sourceRoot,
    });
    workspaceId = materialized.materializedId;
    repositoryWorkspaceId = request.repositoryWorkspaceId;
    repositoryCommit = materialized.currentHeadCommit;
  }
  await materializedDirectory(runner.sourceRoot, workspaceId, "TRANSLATION_SOURCE_WORKSPACE");
  await materializedDirectory(runner.casesRoot, casesBundleId, "TRANSLATION_CASES_BUNDLE");
  const now = new Date().toISOString();
  const job: TranslationJob = {
    id: randomUUID(),
    tenantId: context.tenantId,
    actor: context.actor,
    createdAt: now,
    updatedAt: now,
    repositoryRef: repositoryCommit
      ? `repository-workspace:${repositoryWorkspaceId}@${repositoryCommit}`
      : `local:${workspaceId}`,
    workspaceId,
    ...(repositoryWorkspaceId ? { repositoryWorkspaceId } : {}),
    casesBundleId,
    sourceLanguage,
    targetLanguage,
    status: "QUEUED",
    stage: "queued",
    progress: 0,
    executor: runner.executor,
    recoveryAttempts: 0,
    artifactReady: false,
    independentVerificationStatus: "NOT_RUN",
    externalVerificationStatus: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    logs: [],
  };
  appendLog(job, "system", `Job accepted for ${sourceLanguage}-to-${targetLanguage}.`);
  await persist(runner, context, job);
  schedule(runner, context, job);
  return job;
}

async function load(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  jobId: string,
): Promise<TranslationJob> {
  let job: TranslationJob;
  try {
    job = JSON.parse(await readFile(jobFile(runner, context, jobId), "utf-8")) as TranslationJob;
  } catch {
    fail(404, "TRANSLATION_JOB_NOT_FOUND");
  }
  if (job.tenantId !== context.tenantId) fail(404, "TRANSLATION_JOB_NOT_FOUND");
  return job;
}

export async function getTranslationJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<TranslationJob> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  const processKey = key(context, job.id);
  if (
    ["QUEUED", "RUNNING"].includes(job.status)
    && !state.active.has(processKey)
    && !state.scheduled.has(processKey)
  ) {
    job.recoveryAttempts += 1;
    job.stage = "restart-recovery";
    if (job.recoveryAttempts > 2) {
      job.status = "BLOCKED";
      job.stage = "blocked";
      job.reason = "TRANSLATION_RESTART_RECOVERY_LIMIT_EXCEEDED";
    } else {
      job.status = "QUEUED";
      appendLog(job, "system", "Persistent checkpoint recovered; pipeline will resume.");
      schedule(runner, context, job);
    }
    await persist(runner, context, job);
  }
  return job;
}

export async function cancelTranslationJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<TranslationJob> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  if (!["QUEUED", "RUNNING"].includes(job.status)) fail(409, "TRANSLATION_JOB_NOT_CANCELLABLE");
  const processKey = key(context, job.id);
  state.cancelled.add(processKey);
  state.scheduled.delete(processKey);
  state.active.get(processKey)?.kill("SIGTERM");
  job.status = "CANCELLED";
  job.stage = "cancelled";
  job.progress = 100;
  job.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
  appendLog(job, "system", `Job cancelled by ${context.actor}.`);
  await persist(runner, context, job);
  return job;
}

export async function translationArtifact(
  context: AuthorizedContext,
  jobId: string,
): Promise<{ path: string; size: number; sha256: string }> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  if (!job.artifactReady || !job.artifactSha256 || !job.artifactSize) {
    fail(409, "TRANSLATION_ARTIFACT_NOT_READY");
  }
  const artifactPath = confined(
    jobRoot(runner, context, jobId),
    "pipeline",
    "repository-migration-artifact.zip",
  );
  const info = await stat(artifactPath);
  const digest = await sha256File(artifactPath);
  if (info.size !== job.artifactSize || digest !== job.artifactSha256) {
    fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
  }
  return { path: artifactPath, size: info.size, sha256: digest };
}

export function translationRunnerCapability(): TranslationCapabilityResponse["localRunner"] {
  try {
    const runner = runnerConfig();
    return {
      enabled: true,
      persistence: "FILESYSTEM_ATOMIC",
      auth: "BEARER_TENANT_BOUND",
      isolation: runner.executor,
      recovery: "PERSISTENT_RECONCILIATION",
    };
  } catch {
    return {
      enabled: false,
      persistence: "FILESYSTEM_ATOMIC",
      auth: "BEARER_TENANT_BOUND",
      isolation: "NOT_CONFIGURED",
      recovery: "PERSISTENT_RECONCILIATION",
    };
  }
}

export async function translationRunnerHealth(): Promise<TranslationRunnerHealth> {
  const checkedAt = new Date().toISOString();
  const base = {
    persistence: "FILESYSTEM_ATOMIC" as const,
    auth: "BEARER_TENANT_BOUND" as const,
    recovery: "PERSISTENT_RECONCILIATION" as const,
    activeJobs: state.active.size + state.scheduled.size,
    checkedAt,
  };
  if (process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true") {
    return {
      ...base,
      status: "DISABLED",
      isolation: "NOT_CONFIGURED",
      sourceStorage: "NOT_RUN",
    };
  }
  try {
    const runner = runnerConfig();
    await mkdir(runner.root, { recursive: true, mode: 0o700 });
    await access(runner.root, fsConstants.R_OK | fsConstants.W_OK | fsConstants.X_OK);
    await access(runner.sourceRoot, fsConstants.R_OK | fsConstants.X_OK);
    await access(runner.casesRoot, fsConstants.R_OK | fsConstants.X_OK);
    if (runner.executor === "ROOTLESS_CONTAINER") {
      const sharedRunnerHealth = await generationRunnerHealth();
      if (sharedRunnerHealth.status !== "READY" || sharedRunnerHealth.isolation !== "ROOTLESS_CONTAINER") {
        fail(503, sharedRunnerHealth.reason ?? "ROOTLESS_RUNNER_PREFLIGHT_BLOCKED");
      }
    }
    return {
      ...base,
      status: "READY",
      isolation: runner.executor,
      sourceStorage: "READ_ONLY",
    };
  } catch (error) {
    return {
      ...base,
      status: "BLOCKED",
      isolation: "NOT_CONFIGURED",
      sourceStorage: "BLOCKED",
      reason: error instanceof Error ? error.message : "TRANSLATION_RUNNER_BLOCKED",
    };
  }
}
