import { createHash, randomUUID } from "node:crypto";
import { spawn, type ChildProcess } from "node:child_process";
import {
  accessSync,
  existsSync,
  lstatSync,
  mkdirSync,
  realpathSync,
  statSync,
  type Stats,
} from "node:fs";
import {
  access,
  lstat,
  mkdir,
  open,
  readFile,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
  type FileHandle,
} from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import path from "node:path";
import type { NextRequest } from "next/server";
import type {
  TranslationJob,
  TranslationJobLog,
  TranslationCapabilityResponse,
  TranslationExecutionRuntimeReceipt,
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
  withDurableQueueControlLock,
} from "./durableJobLease";
import {
  BUNDLE_MANIFEST_PATH,
  MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES,
  translationConversionBundleFiles,
  validateTranslationConversion,
  validateTranslationConversionBundleArchive,
  validateTranslationConversionBundleManifest,
  validateTranslationCodeArtifactArchive,
  validateTranslationConversionDocument,
  validateTranslationConversionIndex,
  validateTranslationConversionMarkdown,
  validateTranslationConversionShardDocuments,
  validateTranslationPreflight,
} from "./translationConversionReport";

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
  generations: Map<string, number>;
  writes: Map<string, Promise<void>>;
};

const globalState = globalThis as typeof globalThis & {
  __elmosTranslationRunnerState?: TranslationProcessState;
};
const state = globalState.__elmosTranslationRunnerState ??= {
  active: new Map<string, ChildProcess>(),
  scheduled: new Set<string>(),
  cancelled: new Set<string>(),
  generations: new Map<string, number>(),
  writes: new Map<string, Promise<void>>(),
};
state.active ??= new Map<string, ChildProcess>();
state.scheduled ??= new Set<string>();
state.cancelled ??= new Set<string>();
state.generations ??= new Map<string, number>();
state.writes ??= new Map<string, Promise<void>>();

function executionIsCurrent(processKey: string, generation: number): boolean {
  return state.generations.get(processKey) === generation
    && !state.cancelled.has(processKey);
}

const identifierPattern = /^[a-z0-9][a-z0-9._-]{2,80}$/;
const jobIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const digestPattern = /^[0-9a-f]{64}$/;
const immutableImagePattern = /^[^@\s]+@sha256:[0-9a-f]{64}$/;
const containerIdPattern = /^[0-9a-f]{12,64}$/;
const translationJobLabel = "io.elmos.translation.job-id";
const translationExecutionLabel = "io.elmos.translation.execution-id";
const translationPhaseLabel = "io.elmos.translation.phase";
const terminalTranslationStatuses = new Set<TranslationJob["status"]>([
  "COMPLETE",
  "PARTIAL",
  "BLOCKED",
  "CANCELLED",
]);
export const MAX_TRANSLATION_ARTIFACT_BYTES = 256 * 1024 * 1024;
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

function pathsOverlap(left: string, right: string): boolean {
  return left === right
    || left.startsWith(`${right}${path.sep}`)
    || right.startsWith(`${left}${path.sep}`);
}

function canonicalDirectory(raw: string, code: string, create = false): string {
  try {
    if (create) mkdirSync(raw, { recursive: true, mode: 0o700 });
    const lexical = lstatSync(raw);
    if (lexical.isSymbolicLink() || !lexical.isDirectory()) fail(503, code);
    const resolved = realpathSync(raw);
    if (!statSync(resolved).isDirectory()) fail(503, code);
    return resolved;
  } catch (error) {
    if (error instanceof GenerationRunnerError) throw error;
    fail(503, code);
  }
}

function canonicalExecutable(raw: string, code: string): string {
  try {
    const lexical = lstatSync(raw);
    if (lexical.isSymbolicLink() || !lexical.isFile()) fail(503, code);
    const resolved = realpathSync(raw);
    if (!statSync(resolved).isFile()) fail(503, code);
    accessSync(resolved, fsConstants.R_OK | fsConstants.X_OK);
    return resolved;
  } catch (error) {
    if (error instanceof GenerationRunnerError) throw error;
    fail(503, code);
  }
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
    root: canonicalDirectory(path.resolve(/* turbopackIgnore: true */ root), "TRANSLATION_RUNNER_ROOT_UNSAFE", true),
    repositoryRoot: canonicalDirectory(
      path.resolve(/* turbopackIgnore: true */ repositoryRoot),
      "TRANSLATION_REPOSITORY_ROOT_UNSAFE",
    ),
    sourceRoot: canonicalDirectory(
      path.resolve(/* turbopackIgnore: true */ sourceRoot),
      "TRANSLATION_SOURCE_ROOT_UNSAFE",
    ),
    casesRoot: canonicalDirectory(
      path.resolve(/* turbopackIgnore: true */ casesRoot),
      "TRANSLATION_CASES_ROOT_UNSAFE",
    ),
    uv: canonicalExecutable(
      path.resolve(/* turbopackIgnore: true */ uv),
      "TRANSLATION_RUNNER_UV_UNSAFE",
    ),
  };
  const storageLocations = [
    resolved.root,
    resolved.repositoryRoot,
    resolved.sourceRoot,
    resolved.casesRoot,
  ];
  if (
    resolved.root === path.parse(resolved.root).root
    || storageLocations.some((left, index) => (
      storageLocations.slice(index + 1).some((right) => pathsOverlap(left, right))
    ))
  ) {
    fail(503, "TRANSLATION_RUNNER_ROOT_UNSAFE");
  }
  for (const required of [
    resolved.repositoryRoot,
    resolved.sourceRoot,
    resolved.casesRoot,
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

function clearUnvalidatedReport(job: TranslationJob): void {
  job.reportReady = false;
  delete job.reportJson;
  delete job.reportMarkdown;
  delete job.reportBundle;
  delete job.conversionSummary;
}

function clearPriorExecutionOutputs(job: TranslationJob): void {
  clearUnvalidatedReport(job);
  job.artifactReady = false;
  delete job.artifactSha256;
  delete job.artifactSize;
  delete job.snapshotSha256;
  delete job.readyCount;
  delete job.workUnitCount;
  delete job.includedUnitCount;
  delete job.statusCounts;
  delete job.buildVerification;
}

async function atomicJson(destination: string, serialized: string): Promise<void> {
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.${randomUUID()}.tmp`;
  await writeFile(temporary, serialized, { mode: 0o600 });
  await rename(temporary, destination);
}

async function persist(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<void> {
  job.updatedAt = new Date().toISOString();
  const destination = jobFile(runner, context, job.id);
  const serialized = `${JSON.stringify(job, null, 2)}\n`;
  const prior = state.writes.get(destination) ?? Promise.resolve();
  const queued = prior
    .catch(() => undefined)
    .then(() => atomicJson(destination, serialized));
  state.writes.set(destination, queued);
  try {
    await queued;
  } finally {
    if (state.writes.get(destination) === queued) state.writes.delete(destination);
  }
}

function translationInputDigest(job: TranslationJob): string {
  return createHash("sha256").update(JSON.stringify({
    repositoryRef: job.repositoryRef,
    casesBundleId: job.casesBundleId,
    sourceLanguage: job.sourceLanguage,
    targetLanguage: job.targetLanguage,
  })).digest("hex");
}

function synchronizeJob(target: TranslationJob, source: TranslationJob): void {
  for (const field of Object.keys(target) as Array<keyof TranslationJob>) {
    if (!(field in source)) delete target[field];
  }
  Object.assign(target, source);
}

async function withTranslationControl<T>(
  runner: TranslationRunnerConfig,
  operation: () => Promise<T>,
): Promise<T> {
  return withDurableQueueControlLock(
    durableQueueConfiguration(runner.root, "translation"),
    operation,
  );
}

async function writeControlledJob(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<void> {
  job.updatedAt = new Date().toISOString();
  await atomicJson(jobFile(runner, context, job.id), `${JSON.stringify(job, null, 2)}\n`);
}

async function claimExecution(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  localJob: TranslationJob,
  leaseOwnerId: string,
): Promise<string | undefined> {
  return withTranslationControl(runner, async () => {
    const current = await load(runner, context, localJob.id);
    if (
      terminalTranslationStatuses.has(current.status)
      || current.cancelRequestedAt
    ) return undefined;
    const executionId = randomUUID();
    clearPriorExecutionOutputs(current);
    current.executionId = executionId;
    current.executionLeaseOwnerId = leaseOwnerId;
    delete current.runtimeReceipt;
    await writeControlledJob(runner, context, current);
    synchronizeJob(localJob, current);
    return executionId;
  });
}

async function persistUnclaimedIfActive(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  localJob: TranslationJob,
): Promise<boolean> {
  return withTranslationControl(runner, async () => {
    const current = await load(runner, context, localJob.id);
    if (
      terminalTranslationStatuses.has(current.status)
      || current.cancelRequestedAt
      || current.executionId
      || current.executionLeaseOwnerId
    ) return false;
    const next = { ...localJob, logs: [...localJob.logs] };
    await writeControlledJob(runner, context, next);
    synchronizeJob(localJob, next);
    return true;
  });
}

async function persistExecutionIfCurrent(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  localJob: TranslationJob,
  executionId: string,
): Promise<boolean> {
  return withTranslationControl(runner, async () => {
    const current = await load(runner, context, localJob.id);
    if (
      current.executionId !== executionId
      || current.cancelRequestedAt
      || current.status === "CANCELLED"
    ) return false;
    const next = {
      ...localJob,
      executionId,
      executionLeaseOwnerId: current.executionLeaseOwnerId,
      logs: [...localJob.logs],
    };
    delete next.cancelRequestedAt;
    delete next.cancelRequestedBy;
    await writeControlledJob(runner, context, next);
    synchronizeJob(localJob, next);
    return true;
  });
}

async function durableExecutionIsCurrent(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  jobId: string,
  executionId: string,
): Promise<boolean> {
  try {
    const current = await load(runner, context, jobId);
    return current.executionId === executionId
      && !current.cancelRequestedAt
      && current.status !== "CANCELLED";
  } catch {
    return false;
  }
}

async function sha256OpenPipelineFile(
  handle: FileHandle,
  expected: Stats,
  errorCode: string,
): Promise<string> {
  const digest = createHash("sha256");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  let position = 0;
  while (position < expected.size) {
    const { bytesRead } = await handle.read(
      buffer,
      0,
      Math.min(buffer.length, expected.size - position),
      position,
    );
    if (bytesRead <= 0) fail(409, errorCode);
    digest.update(buffer.subarray(0, bytesRead));
    position += bytesRead;
  }
  const after = await handle.stat();
  if (
    after.dev !== expected.dev
    || after.ino !== expected.ino
    || after.size !== expected.size
    || after.mtimeMs !== expected.mtimeMs
    || after.ctimeMs !== expected.ctimeMs
    || after.nlink !== expected.nlink
  ) fail(409, errorCode);
  return digest.digest("hex");
}

type OpenedPipelineFile = {
  handle: FileHandle;
  path: string;
  size: number;
  sha256: string;
  stats: Stats;
};

function sameOpenFileStats(left: Stats, right: Stats): boolean {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.size === right.size
    && left.mtimeMs === right.mtimeMs
    && left.ctimeMs === right.ctimeMs
    && left.nlink === right.nlink;
}

async function boundedOpenPipelineFile(
  pipeline: string,
  relativePath: string,
  maximumBytes: number,
  errorCode: string,
): Promise<OpenedPipelineFile> {
  const candidate = confined(pipeline, relativePath);
  let resolved: string;
  let resolvedPipeline: string;
  try {
    const linkInfo = await lstat(candidate);
    if (!linkInfo.isFile() || linkInfo.isSymbolicLink()) fail(409, errorCode);
    resolvedPipeline = await realpath(pipeline);
    resolved = await realpath(candidate);
  } catch (error) {
    if (error instanceof GenerationRunnerError) throw error;
    fail(409, errorCode);
  }
  if (
    resolved !== path.resolve(resolvedPipeline, relativePath)
    || !resolved.startsWith(`${resolvedPipeline}${path.sep}`)
  ) fail(409, errorCode);
  let handle: FileHandle;
  try {
    handle = await open(resolved, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  } catch {
    fail(409, errorCode);
  }
  try {
    const info = await handle.stat();
    if (!info.isFile() || info.nlink !== 1 || info.size < 1 || info.size > maximumBytes) {
      fail(409, errorCode);
    }
    const sha256 = await sha256OpenPipelineFile(handle, info, errorCode);
    return { handle, path: resolved, size: info.size, sha256, stats: info };
  } catch (error) {
    await handle.close().catch(() => undefined);
    throw error;
  }
}

async function verifiedOpenPipelineFile(
  pipeline: string,
  descriptor: { path: string; bytes: number; sha256: string },
  errorCode: string,
): Promise<OpenedPipelineFile> {
  const opened = await boundedOpenPipelineFile(pipeline, descriptor.path, descriptor.bytes, errorCode);
  if (opened.size !== descriptor.bytes || opened.sha256 !== descriptor.sha256) {
    await opened.handle.close().catch(() => undefined);
    fail(409, errorCode);
  }
  return opened;
}

async function readOpenedPipelineFile(opened: OpenedPipelineFile, errorCode: string): Promise<Buffer> {
  const content = Buffer.allocUnsafe(opened.size);
  let position = 0;
  while (position < content.length) {
    const { bytesRead } = await opened.handle.read(
      content,
      position,
      content.length - position,
      position,
    );
    if (bytesRead <= 0) fail(409, errorCode);
    position += bytesRead;
  }
  const after = await opened.handle.stat();
  if (
    !sameOpenFileStats(opened.stats, after)
    || createHash("sha256").update(content).digest("hex") !== opened.sha256
  ) fail(409, errorCode);
  return content;
}

async function readBoundedPipelineFile(
  pipeline: string,
  relativePath: string,
  maximumBytes: number,
  errorCode: string,
): Promise<{ content: Buffer; path: string; size: number; sha256: string }> {
  const opened = await boundedOpenPipelineFile(pipeline, relativePath, maximumBytes, errorCode);
  try {
    return {
      content: await readOpenedPipelineFile(opened, errorCode),
      path: opened.path,
      size: opened.size,
      sha256: opened.sha256,
    };
  } finally {
    await opened.handle.close().catch(() => undefined);
  }
}

async function readVerifiedPipelineFile(
  pipeline: string,
  descriptor: { path: string; bytes: number; sha256: string },
  errorCode: string,
): Promise<{ content: Buffer; path: string; size: number; sha256: string }> {
  const opened = await verifiedOpenPipelineFile(pipeline, descriptor, errorCode);
  try {
    return {
      content: await readOpenedPipelineFile(opened, errorCode),
      path: opened.path,
      size: opened.size,
      sha256: opened.sha256,
    };
  } finally {
    await opened.handle.close().catch(() => undefined);
  }
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

export function translationCasesBase(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
): string {
  if (process.env.NODE_ENV !== "production") return runner.casesRoot;
  if (!identifierPattern.test(context.tenantId)) {
    fail(403, "TRANSLATION_TENANT_CASES_BINDING_INVALID");
  }
  return confined(runner.casesRoot, context.tenantId);
}

type TranslationRuntimePhase = TranslationExecutionRuntimeReceipt["phase"];
type BoundedCommandResult = { exitCode: number; stdout: string; stderr: string };

function expectedContainerName(
  jobId: string,
  executionId: string,
  phase: TranslationRuntimePhase,
): string {
  return `elmos-tr-${jobId}-${executionId.replaceAll("-", "")}-${phase}`;
}

function expectedCidFile(
  executionId: string,
  phase: TranslationRuntimePhase,
): string {
  return path.posix.join("runtime", executionId, `${phase}.cid`);
}

function receiptCidPath(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  jobId: string,
  receipt: TranslationExecutionRuntimeReceipt,
): string {
  if (!receipt.cidFile) fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
  return confined(jobRoot(runner, context, jobId), ...receipt.cidFile.split("/"));
}

function validateRuntimeReceipt(
  job: TranslationJob,
  receipt: TranslationExecutionRuntimeReceipt,
): void {
  if (
    receipt.schemaVersion !== "1.0"
    || !jobIdPattern.test(receipt.executionId)
    || receipt.executionId !== job.executionId
    || !["preflight", "pipeline"].includes(receipt.phase)
    || receipt.executor !== job.executor
    || !["STARTING", "RUNNING", "EXITED", "CLEANUP_VERIFIED", "CLEANUP_UNVERIFIED"].includes(receipt.state)
    || !Number.isSafeInteger(receipt.processGroupId)
    || receipt.processGroupId <= 1
    || receipt.processGroupId === process.pid
    || !Number.isFinite(Date.parse(receipt.startedAt))
    || !Number.isFinite(Date.parse(receipt.updatedAt))
  ) fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
  if (receipt.executor === "ROOTLESS_CONTAINER") {
    if (
      receipt.containerName !== expectedContainerName(job.id, receipt.executionId, receipt.phase)
      || receipt.cidFile !== expectedCidFile(receipt.executionId, receipt.phase)
      || receipt.labels?.jobId !== job.id
      || receipt.labels.executionId !== receipt.executionId
      || receipt.labels.phase !== receipt.phase
      || (receipt.containerId !== undefined && !containerIdPattern.test(receipt.containerId))
    ) fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
  } else if (
    receipt.containerName !== undefined
    || receipt.cidFile !== undefined
    || receipt.containerId !== undefined
    || receipt.labels !== undefined
  ) fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
}

function processGroupAlive(processGroupId: number): boolean {
  try {
    process.kill(-processGroupId, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code !== "ESRCH";
  }
}

function signalProcessGroup(processGroupId: number, signal: NodeJS.Signals): void {
  try {
    process.kill(-processGroupId, signal);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ESRCH") throw error;
  }
}

async function waitForProcessGroupExit(processGroupId: number, attempts = 40): Promise<boolean> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (!processGroupAlive(processGroupId)) return true;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return !processGroupAlive(processGroupId);
}

async function terminateProcessGroup(processGroupId: number): Promise<boolean> {
  if (!Number.isSafeInteger(processGroupId) || processGroupId <= 1 || processGroupId === process.pid) {
    return false;
  }
  if (!processGroupAlive(processGroupId)) return true;
  try {
    signalProcessGroup(processGroupId, "SIGTERM");
  } catch {
    return false;
  }
  if (await waitForProcessGroupExit(processGroupId)) return true;
  try {
    signalProcessGroup(processGroupId, "SIGKILL");
  } catch {
    return false;
  }
  return waitForProcessGroupExit(processGroupId);
}

async function boundedCommand(
  executable: string,
  args: string[],
  timeoutMs = 15_000,
): Promise<BoundedCommandResult> {
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    let settled = false;
    const child = spawn(executable, args, {
      shell: false,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, NO_COLOR: "1" },
    });
    const finish = (result?: BoundedCommandResult, error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(result ?? { exitCode: 1, stdout, stderr });
    };
    const timer = setTimeout(() => {
      if (child.pid) {
        try {
          signalProcessGroup(child.pid, "SIGKILL");
        } catch {
          child.kill("SIGKILL");
        }
      }
      finish(undefined, new GenerationRunnerError(502, "CANCEL_CLEANUP_UNVERIFIED"));
    }, timeoutMs);
    timer.unref();
    const capture = (stream: "stdout" | "stderr", chunk: Buffer) => {
      if (stream === "stdout") stdout += chunk.toString("utf8");
      else stderr += chunk.toString("utf8");
      if (Buffer.byteLength(stdout) + Buffer.byteLength(stderr) > 1024 * 1024) {
        if (child.pid) {
          try {
            signalProcessGroup(child.pid, "SIGKILL");
          } catch {
            child.kill("SIGKILL");
          }
        }
        finish(undefined, new GenerationRunnerError(502, "CANCEL_CLEANUP_UNVERIFIED"));
      }
    };
    child.stdout.on("data", (chunk: Buffer) => capture("stdout", chunk));
    child.stderr.on("data", (chunk: Buffer) => capture("stderr", chunk));
    child.once("error", () => finish(
      undefined,
      new GenerationRunnerError(502, "CANCEL_CLEANUP_UNVERIFIED"),
    ));
    child.once("close", (exitCode) => finish({
      exitCode: exitCode ?? 1,
      stdout,
      stderr,
    }));
  });
}

async function readExpectedContainerId(cidFile: string): Promise<string | undefined> {
  try {
    const candidate = (await readFile(cidFile, "utf8")).trim();
    return containerIdPattern.test(candidate) ? candidate : undefined;
  } catch {
    return undefined;
  }
}

async function inspectRuntimeContainer(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
  receipt: TranslationExecutionRuntimeReceipt,
): Promise<{ status: "ABSENT" } | { status: "PRESENT"; containerId: string }> {
  if (!runner.containerEngine || !receipt.containerName || !receipt.labels) {
    fail(409, "TRANSLATION_RUNTIME_RECEIPT_INVALID");
  }
  const inspected = await boundedCommand(runner.containerEngine, [
    "inspect",
    "--format",
    "{{json .}}",
    receipt.containerName,
  ]);
  if (inspected.exitCode !== 0) {
    const absent = await boundedCommand(runner.containerEngine, [
      "ps",
      "--all",
      "--filter", `label=${translationJobLabel}=${job.id}`,
      "--filter", `label=${translationExecutionLabel}=${receipt.executionId}`,
      "--filter", `label=${translationPhaseLabel}=${receipt.phase}`,
      "--format", "{{.ID}}",
    ]);
    if (absent.exitCode === 0 && absent.stdout.trim() === "") return { status: "ABSENT" };
    fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  }
  let document: Record<string, unknown>;
  try {
    document = JSON.parse(inspected.stdout) as Record<string, unknown>;
  } catch {
    fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  }
  const labels = (document.Config as { Labels?: unknown } | undefined)?.Labels;
  const containerId = String(document.Id ?? "");
  const observedName = String(document.Name ?? "").replace(/^\//, "");
  if (
    !containerIdPattern.test(containerId)
    || observedName !== receipt.containerName
    || !labels
    || typeof labels !== "object"
    || Array.isArray(labels)
    || (labels as Record<string, unknown>)[translationJobLabel] !== job.id
    || (labels as Record<string, unknown>)[translationExecutionLabel] !== receipt.executionId
    || (labels as Record<string, unknown>)[translationPhaseLabel] !== receipt.phase
  ) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  const cidPath = receiptCidPath(runner, context, job.id, receipt);
  let cid = await readExpectedContainerId(cidPath);
  for (let attempt = 0; !cid && attempt < 20; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 25));
    cid = await readExpectedContainerId(cidPath);
  }
  if (!cid || cid !== containerId) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  return { status: "PRESENT", containerId };
}

async function cleanupRuntimeReceipt(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
): Promise<TranslationExecutionRuntimeReceipt | undefined> {
  const receipt = job.runtimeReceipt;
  if (!receipt) return undefined;
  validateRuntimeReceipt(job, receipt);
  const processExited = receipt.state === "EXITED" || receipt.state === "CLEANUP_VERIFIED"
    ? !processGroupAlive(receipt.processGroupId)
    : await terminateProcessGroup(receipt.processGroupId);
  if (!processExited) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
  if (receipt.executor === "ROOTLESS_CONTAINER") {
    let observation = await inspectRuntimeContainer(runner, context, job, receipt);
    if (observation.status === "PRESENT") {
      receipt.containerId = observation.containerId;
      const stop = await boundedCommand(runner.containerEngine ?? "", [
        "stop", "--time", "5", receipt.containerName ?? "",
      ]);
      if (stop.exitCode !== 0) {
        const kill = await boundedCommand(runner.containerEngine ?? "", [
          "kill", receipt.containerName ?? "",
        ]);
        if (kill.exitCode !== 0) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
      }
      const remove = await boundedCommand(runner.containerEngine ?? "", [
        "rm", "--force", receipt.containerName ?? "",
      ]);
      if (remove.exitCode !== 0) fail(502, "CANCEL_CLEANUP_UNVERIFIED");
      observation = await inspectRuntimeContainer(runner, context, job, receipt);
      if (observation.status !== "ABSENT") fail(502, "CANCEL_CLEANUP_UNVERIFIED");
    }
    await rm(receiptCidPath(runner, context, job.id, receipt), { force: true });
  }
  const now = new Date().toISOString();
  return {
    ...receipt,
    state: "CLEANUP_VERIFIED",
    updatedAt: now,
    cleanupVerifiedAt: now,
  };
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

function preflightCommand(
  runner: TranslationRunnerConfig,
  job: TranslationJob,
  source: string,
  preflightDirectory: string,
  outputName: string,
): { executable: string; args: string[] } {
  const output = confined(preflightDirectory, outputName);
  const routeArgs = [
    "repository-preflight",
    "--repository", source,
    "--repository-ref", job.repositoryRef,
    "--source-language", job.sourceLanguage,
    "--target-language", job.targetLanguage,
    "--output", output,
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
      "--mount", `type=bind,source=${preflightDirectory},destination=/preflight`,
      "--env", "PYTHONPATH=/elmos/engines/polyglot-route-engine/src",
      runner.containerImage ?? "",
      "python", "-m", "elmos_polyglot_route.cli",
      ...routeArgs.map((argument) => argument
        .replace(source, "/source")
        .replace(output, `/preflight/${outputName}`)),
    ],
  };
}

async function runChild(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  executable: string,
  args: string[],
  job: TranslationJob,
  processKey: string,
  executionId: string,
  phase: TranslationRuntimePhase,
  timeoutCode = "TRANSLATION_PIPELINE_TIMEOUT",
  executionCode = "TRANSLATION_PIPELINE_EXECUTION_FAILED",
): Promise<number> {
  const relativeCidFile = expectedCidFile(executionId, phase);
  const cidFile = confined(jobRoot(runner, context, job.id), ...relativeCidFile.split("/"));
  if (runner.executor === "ROOTLESS_CONTAINER") {
    await mkdir(path.dirname(cidFile), { recursive: true, mode: 0o700 });
    await rm(cidFile, { force: true });
  }
  const containerName = expectedContainerName(job.id, executionId, phase);
  const executionArgs = runner.executor === "ROOTLESS_CONTAINER"
    ? [
        args[0],
        "--name", containerName,
        "--cidfile", cidFile,
        "--label", `${translationJobLabel}=${job.id}`,
        "--label", `${translationExecutionLabel}=${executionId}`,
        "--label", `${translationPhaseLabel}=${phase}`,
        ...args.slice(1),
      ]
    : args;

  let child: ChildProcess | undefined;
  let completion: Promise<number> | undefined;
  await withTranslationControl(runner, async () => {
    const current = await load(runner, context, job.id);
    if (
      current.executionId !== executionId
      || current.cancelRequestedAt
      || current.status === "CANCELLED"
    ) return;
    child = spawn(executable, executionArgs, {
      shell: false,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, NO_COLOR: "1" },
    });
    if (!child.pid || child.pid <= 1 || child.pid === process.pid) {
      child.kill("SIGKILL");
      child = undefined;
      fail(409, executionCode);
    }
    const startedAt = new Date().toISOString();
    const receipt: TranslationExecutionRuntimeReceipt = {
      schemaVersion: "1.0",
      executionId,
      phase,
      executor: runner.executor,
      state: "RUNNING",
      processGroupId: child.pid,
      ...(runner.executor === "ROOTLESS_CONTAINER" ? {
        containerName,
        cidFile: relativeCidFile,
        labels: {
          jobId: job.id,
          executionId,
          phase,
        },
      } : {}),
      startedAt,
      updatedAt: startedAt,
    };
    current.runtimeReceipt = receipt;
    await writeControlledJob(runner, context, current);
    job.runtimeReceipt = receipt;
    state.active.set(processKey, child);

    completion = new Promise<number>((resolve, reject) => {
      let settled = false;
      let timedOut = false;
      const finish = async (exitCode: number | null, spawnFailed = false) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (state.active.get(processKey) === child) state.active.delete(processKey);
        try {
          const durable = await load(runner, context, job.id);
          if (!durable.cancelRequestedAt && durable.executionId === executionId) {
            const cleaned = await cleanupRuntimeReceipt(runner, context, durable);
            if (!cleaned) fail(502, "TRANSLATION_RUNTIME_CLEANUP_UNVERIFIED");
            const recorded = await withTranslationControl(runner, async () => {
              const latest = await load(runner, context, job.id);
              if (latest.executionId !== executionId || latest.cancelRequestedAt) return false;
              latest.runtimeReceipt = cleaned;
              await writeControlledJob(runner, context, latest);
              job.runtimeReceipt = cleaned;
              return true;
            });
            if (!recorded) return resolve(exitCode ?? 1);
          }
          if (timedOut) reject(new GenerationRunnerError(409, timeoutCode));
          else if (spawnFailed) reject(new GenerationRunnerError(409, executionCode));
          else resolve(exitCode ?? 1);
        } catch (error) {
          reject(error);
        }
      };
      const timer = setTimeout(() => {
        timedOut = true;
        if (child?.pid) {
          void terminateProcessGroup(child.pid).then((exited) => {
            if (!exited) void finish(null, true);
          });
        } else {
          void finish(null, true);
        }
      }, 20 * 60_000);
      timer.unref();
      child?.stdout?.on("data", (chunk: Buffer) => appendLog(job, "stdout", chunk.toString("utf-8")));
      child?.stderr?.on("data", (chunk: Buffer) => appendLog(job, "stderr", chunk.toString("utf-8")));
      child?.once("error", () => void finish(null, true));
      child?.once("close", (exitCode) => void finish(exitCode));
    });
  });
  if (!child || !completion) fail(409, "TRANSLATION_EXECUTION_FENCED");
  return completion;
}

async function execute(
  runner: TranslationRunnerConfig,
  context: AuthorizedContext,
  job: TranslationJob,
  generation: number,
): Promise<void> {
  const processKey = key(context, job.id);
  if (!executionIsCurrent(processKey, generation)) return;
  state.scheduled.delete(processKey);
  let requeued = false;
  let queueLease: DurableJobLease | null = null;
  let leaseHeartbeat: NodeJS.Timeout | null = null;
  let metering: MeteredExecution | null = null;
  let finalizedReportValidated = false;
  let executionId: string | undefined;
  try {
    try {
      queueLease = await DurableJobLease.acquire({
        configuration: durableQueueConfiguration(runner.root, "translation"),
        tenantId: context.tenantId,
        jobId: job.id,
        createdAt: job.createdAt,
        inputDigest: translationInputDigest(job),
      });
      if (!executionIsCurrent(processKey, generation)) return;
      executionId = await claimExecution(
        runner,
        context,
        job,
        String(queueLease.ownerId ?? "unavailable-owner"),
      );
      if (!executionId) return;
      leaseHeartbeat = setInterval(() => {
        void queueLease?.heartbeat().catch(() => {
          const child = state.active.get(processKey);
          if (child?.pid) void terminateProcessGroup(child.pid);
        });
      }, queueLease.heartbeatIntervalMs);
      leaseHeartbeat.unref();
    } catch (error) {
      if (!executionIsCurrent(processKey, generation)) return;
      if (error instanceof DurableLeaseError && error.retryable) {
        job.status = "QUEUED";
        job.stage = "queued";
        job.reason = error.code;
        appendLog(job, "system", `Queue admission delayed: ${error.code}.`);
        if (!await persistUnclaimedIfActive(runner, context, job)) return;
        if (!executionIsCurrent(processKey, generation)) return;
        state.scheduled.add(processKey);
        requeued = true;
        setTimeout(
          () => {
            if (executionIsCurrent(processKey, generation)) {
              void execute(runner, context, job, generation);
            }
          },
          1_000 + Math.floor(Math.random() * 2_000),
        ).unref();
        return;
      }
      throw error;
    }
    if (!executionId || !await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const source = await materializedDirectory(
      runner.sourceRoot,
      job.workspaceId,
      "TRANSLATION_SOURCE_WORKSPACE",
    );
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const cases = await materializedDirectory(
      translationCasesBase(runner, context),
      job.casesBundleId,
      "TRANSLATION_CASES_BUNDLE",
    );
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const durableJobRoot = jobRoot(runner, context, job.id);
    const pipeline = confined(durableJobRoot, "pipeline");
    const preflightDirectory = confined(durableJobRoot, "preflight");
    const preflightOutputName = `repository-preflight-${randomUUID()}.json`;
    await Promise.all([
      mkdir(pipeline, { recursive: true, mode: 0o700 }),
      mkdir(preflightDirectory, { recursive: true, mode: 0o700 }),
    ]);
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    job.status = "PRECHECK";
    job.stage = "preflight";
    job.progress = 5;
    appendLog(job, "system", `Non-billing repository preflight started with ${runner.executor}.`);
    if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const preflightInvocation = preflightCommand(
      runner,
      job,
      source,
      preflightDirectory,
      preflightOutputName,
    );
    const preflightExitCode = await runChild(
      runner,
      context,
      preflightInvocation.executable,
      preflightInvocation.args,
      job,
      processKey,
      executionId,
      "preflight",
      "TRANSLATION_PREFLIGHT_TIMEOUT",
      "TRANSLATION_PREFLIGHT_EXECUTION_FAILED",
    );
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    if (preflightExitCode !== 0) fail(409, "TRANSLATION_PREFLIGHT_BLOCKED");
    const preflightFile = await readBoundedPipelineFile(
      preflightDirectory,
      preflightOutputName,
      1024 * 1024,
      "TRANSLATION_PREFLIGHT_EVIDENCE_INVALID",
    );
    let preflightDocument: unknown;
    try {
      preflightDocument = JSON.parse(preflightFile.content.toString("utf8"));
    } catch {
      fail(409, "TRANSLATION_PREFLIGHT_EVIDENCE_INVALID");
    }
    const preflight = validateTranslationPreflight(preflightDocument, {
      repositoryRef: job.repositoryRef,
      routeId: `${job.sourceLanguage}-to-${job.targetLanguage}`,
      sourceLanguage: job.sourceLanguage,
      targetLanguage: job.targetLanguage,
    });
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    job.snapshotSha256 = preflight.snapshotSha256;
    if (preflight.status === "REJECTED") {
      job.status = "BLOCKED";
      job.stage = "blocked";
      job.progress = 100;
      job.reason = "FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED";
      appendLog(
        job,
        "system",
        "Precheck rejected at 10,001 reported obligation rows; conversion and metering were not accepted.",
      );
      if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
      return;
    }
    job.status = "RUNNING";
    job.stage = "metering";
    job.progress = 10;
    appendLog(
      job,
      "system",
      preflight.status === "PASSED"
        ? `Precheck passed for ${preflight.obligationCount} exact reported rows; conversion accepted and metering begins.`
        : `Precheck passed with an incomplete inventory at ${preflight.reportedObligationLowerBound} reported rows; conversion accepted, project rate remains indeterminate, and metering begins.`,
    );
    if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    metering = await beginMeteredExecution(`translation-${job.id}`);
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    job.status = "RUNNING";
    job.stage = "pipeline";
    job.progress = 15;
    appendLog(job, "system", `Pipeline started with ${runner.executor}; source and cases are read-only.`);
    if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const invocation = command(runner, job, source, cases, pipeline);
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    const exitCode = await runChild(
      runner,
      context,
      invocation.executable,
      invocation.args,
      job,
      processKey,
      executionId,
      "pipeline",
    );
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    if (exitCode !== 0) fail(409, "TRANSLATION_PIPELINE_BLOCKED");
    const pipelineReport = await readBoundedPipelineFile(
      pipeline,
      "repository-pipeline-report.json",
      64 * 1024 * 1024,
      "TRANSLATION_PIPELINE_EVIDENCE_INVALID",
    );
    let report: Record<string, unknown>;
    try {
      report = JSON.parse(pipelineReport.content.toString("utf8")) as Record<string, unknown>;
    } catch {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }
    const status = String(report.status);
    const workUnitCount = Number(report.work_unit_count);
    const conversion = validateTranslationConversion(report.functional_conversion, workUnitCount);
    const artifact = report.artifact as Record<string, unknown> | null | undefined;
    if (
      report.schema_version !== "1.0.0"
      || report.kind !== "elmos.repository-pipeline-report"
      || !["COMPLETE", "PARTIAL", "BLOCKED"].includes(status)
      || report.repository_ref !== job.repositoryRef
      || report.source_language !== job.sourceLanguage
      || report.target_language !== job.targetLanguage
      || report.route_id !== `${job.sourceLanguage}-to-${job.targetLanguage}`
      || report.profile !== "typed-pure-function-v1"
      || !digestPattern.test(String(report.snapshot_sha256))
      || report.snapshot_sha256 !== preflight.snapshotSha256
      || !digestPattern.test(String(report.cases_manifest_sha256))
      || report.cases_manifest_sha256 !== conversion.summary.casesManifestSha256
      || report.independent_verification_status !== "NOT_RUN"
      || report.external_verification_status !== "NOT_RUN"
      || report.certification_status !== "NOT_CERTIFIED"
    ) {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }

    const batchStatusCounts = report.status_counts;
    const readyCount = Number(report.ready_count);
    const includedUnitCount = Number(report.included_unit_count);
    const buildRaw = report.build_verification;
    if (
      !batchStatusCounts || typeof batchStatusCounts !== "object" || Array.isArray(batchStatusCounts)
      || !Number.isSafeInteger(readyCount) || readyCount < 0 || readyCount > workUnitCount
      || !Number.isSafeInteger(includedUnitCount) || includedUnitCount < 0 || includedUnitCount > workUnitCount
      || !buildRaw || typeof buildRaw !== "object" || Array.isArray(buildRaw)
    ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    const batchCounts = batchStatusCounts as Record<string, unknown>;
    if (
      Object.keys(batchCounts).length < 1
      || Object.keys(batchCounts).length > 16
      || Object.entries(batchCounts).some(([key, value]) => (
        !/^[A-Z][A-Z0-9_]{1,99}$/.test(key)
        || !Number.isSafeInteger(value)
        || Number(value) < 0
      ))
      || Object.values(batchCounts).reduce<number>((total, value) => total + Number(value), 0) !== workUnitCount
    ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    const build = buildRaw as Record<string, unknown>;
    const buildStatus = String(build.status);
    if (
      !["PASSED", "FAILED", "NOT_RUN"].includes(buildStatus)
      || (build.command !== null && build.command !== undefined && (
        !Array.isArray(build.command)
        || build.command.length > 100
        || !build.command.every((part) => typeof part === "string" && part.length >= 1 && part.length <= 1_000)
      ))
      || (build.toolchain !== null && build.toolchain !== undefined && (
        typeof build.toolchain !== "string" || build.toolchain.length > 1_000
      ))
      || (build.reason !== null && (
        typeof build.reason !== "string" || build.reason.length > 4_000
      ))
    ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    const buildReason = typeof build.reason === "string" ? build.reason : null;
    const functionalStatus: "COMPLETE" | "PARTIAL" | "BLOCKED" =
      conversion.summary.numerator === 0
        ? "BLOCKED"
        : conversion.summary.denominatorComplete
          && conversion.summary.numerator === conversion.summary.denominator
          && buildStatus === "PASSED"
          ? "COMPLETE"
          : "PARTIAL";
    const packagingRaw = report.artifact_packaging;
    if (!packagingRaw || typeof packagingRaw !== "object" || Array.isArray(packagingRaw)) {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }
    const packaging = packagingRaw as Record<string, unknown>;
    const packagingStatus = String(packaging.status);
    const packagingReasonCode = packaging.reason_code;
    const packagingReason = packaging.reason;
    const packagingLimitsValid =
      packaging.max_uncompressed_bytes === MAX_TRANSLATION_ARTIFACT_BYTES
      && packaging.max_compressed_bytes === MAX_TRANSLATION_ARTIFACT_BYTES;
    const packagingPassed = packagingStatus === "PASSED"
      && packagingReasonCode === null
      && packagingReason === null
      && conversion.summary.codeArtifactReady
      && artifact !== null
      && artifact !== undefined
      && status === functionalStatus
      && functionalStatus !== "BLOCKED";
    const packagingNotRun = packagingStatus === "NOT_RUN"
      && packagingReasonCode === "FUNCTIONAL_CONVERSION_NOT_CODE_READY"
      && typeof packagingReason === "string"
      && packagingReason.length >= 1
      && packagingReason.length <= 2_000
      && !conversion.summary.codeArtifactReady
      && (artifact === null || artifact === undefined)
      && status === functionalStatus;
    const packagingCapacityFailed = packagingStatus === "FAILED"
      && [
        "PIPELINE_ARTIFACT_UNCOMPRESSED_LIMIT_EXCEEDED",
        "PIPELINE_ARTIFACT_COMPRESSED_LIMIT_EXCEEDED",
      ].includes(String(packagingReasonCode))
      && typeof packagingReason === "string"
      && packagingReason.length >= 1
      && packagingReason.length <= 2_000
      && !conversion.summary.codeArtifactReady
      && (artifact === null || artifact === undefined)
      && status === "BLOCKED"
      && functionalStatus !== "BLOCKED";
    if (
      !packagingLimitsValid
      || Object.keys(packaging).some((key) => ![
        "status",
        "reason_code",
        "reason",
        "max_uncompressed_bytes",
        "max_compressed_bytes",
      ].includes(key))
      || !(packagingPassed || packagingNotRun || packagingCapacityFailed)
    ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    const buildVerification: TranslationJob["buildVerification"] = {
      status: buildStatus,
      ...(Array.isArray(build.command) ? { command: [...build.command] as string[] } : {}),
      ...(typeof build.toolchain === "string" ? { toolchain: build.toolchain } : {}),
    };

    const [verifiedJsonReport, verifiedMarkdownReport] = await Promise.all([
      readVerifiedPipelineFile(
        pipeline,
        conversion.jsonReport,
        "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
      ),
      readVerifiedPipelineFile(
        pipeline,
        conversion.markdownReport,
        "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
      ),
    ]);
    let conversionDocument: unknown;
    try {
      conversionDocument = JSON.parse(verifiedJsonReport.content.toString("utf8"));
    } catch {
      fail(409, "TRANSLATION_REPORT_DOCUMENT_INVALID");
    }
    const conversionContext = {
      pipelineStatus: functionalStatus,
      repositoryRef: job.repositoryRef,
      snapshotSha256: String(report.snapshot_sha256),
      routeId: `${job.sourceLanguage}-to-${job.targetLanguage}`,
      sourceLanguage: job.sourceLanguage,
      targetLanguage: job.targetLanguage,
      profile: String(report.profile),
      buildStatus,
      buildReason,
      markdownSha256: conversion.markdownReport.sha256,
      casesManifestSha256: conversion.summary.casesManifestSha256,
    };
    if (conversion.summary.storageMode === "SINGLE") {
      validateTranslationConversionDocument(
        conversionDocument,
        conversionContext,
        conversion.summary,
      );
      validateTranslationConversionMarkdown(
        conversionDocument,
        verifiedMarkdownReport.content,
      );
    } else {
      const shardDescriptors = validateTranslationConversionIndex(
        conversionDocument,
        conversionContext,
        conversion.summary,
      );
      validateTranslationConversionMarkdown(
        conversionDocument,
        verifiedMarkdownReport.content,
      );
      const shardOutputs = await Promise.all(shardDescriptors.map(async (descriptor) => {
        const [jsonFile, markdownFile] = await Promise.all([
          readVerifiedPipelineFile(
            pipeline,
            descriptor.json,
            "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
          ),
          readVerifiedPipelineFile(
            pipeline,
            descriptor.markdown,
            "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
          ),
        ]);
        try {
          return {
            document: JSON.parse(jsonFile.content.toString("utf8")) as unknown,
            markdown: markdownFile.content,
          };
        } catch {
          fail(409, "TRANSLATION_REPORT_DOCUMENT_INVALID");
        }
      }));
      shardOutputs.forEach((output, offset) => {
        const descriptor = shardDescriptors[offset];
        validateTranslationConversionMarkdown(
          output.document,
          output.markdown,
          `分片 ${descriptor.sequence}/${conversion.summary.shardCount}；本分片 ${descriptor.functionCount} 个功能；总指标来自全部分片`,
        );
      });
      validateTranslationConversionShardDocuments(
        conversionDocument,
        shardOutputs.map((output) => output.document),
        conversionContext,
        conversion.summary,
        shardDescriptors,
      );
      const expectedBundleFiles = translationConversionBundleFiles(
        conversion,
        shardDescriptors,
      );
      const manifestFile = await readBoundedPipelineFile(
        pipeline,
        BUNDLE_MANIFEST_PATH,
        1024 * 1024,
        "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
      );
      const manifestDescriptor = validateTranslationConversionBundleManifest(
        manifestFile.content,
        conversion.summary.reportId,
        expectedBundleFiles,
      );
      if (
        manifestDescriptor.bytes !== manifestFile.size
        || manifestDescriptor.sha256 !== manifestFile.sha256
        || !conversion.reportBundle
      ) fail(409, "TRANSLATION_REPORT_INTEGRITY_MISMATCH");
      const bundleFile = await verifiedOpenPipelineFile(
        pipeline,
        conversion.reportBundle,
        "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
      );
      if (bundleFile.size > MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES) {
        await bundleFile.handle.close().catch(() => undefined);
        fail(409, "TRANSLATION_REPORT_INTEGRITY_MISMATCH");
      }
      try {
        await validateTranslationConversionBundleArchive(
          bundleFile.handle,
          conversion.reportBundle,
          expectedBundleFiles,
          manifestDescriptor,
        );
      } finally {
        await bundleFile.handle.close().catch(() => undefined);
      }
    }

    let verifiedArtifact: { path: string; size: number; sha256: string } | undefined;
    if (conversion.summary.codeArtifactReady) {
      if (
        !artifact
        || artifact.path !== "repository-migration-artifact.zip"
        || !Number.isSafeInteger(artifact.bytes)
        || Number(artifact.bytes) < 1
        || Number(artifact.bytes) > MAX_TRANSLATION_ARTIFACT_BYTES
        || !digestPattern.test(String(artifact.sha256))
      ) fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
      if (functionalStatus === "BLOCKED") {
        fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
      }
      const artifactDescriptor = {
        path: "repository-migration-artifact.zip" as const,
        bytes: Number(artifact.bytes),
        sha256: String(artifact.sha256),
      };
      const artifactFile = await verifiedOpenPipelineFile(
        pipeline,
        artifactDescriptor,
        "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH",
      );
      try {
        await validateTranslationCodeArtifactArchive(
          artifactFile.handle,
          artifactDescriptor,
          {
            pipelineStatus: functionalStatus,
            repositoryRef: job.repositoryRef,
            snapshotSha256: String(report.snapshot_sha256),
            routeId: `${job.sourceLanguage}-to-${job.targetLanguage}`,
            profile: String(report.profile),
            summary: conversion.summary,
          },
        );
        verifiedArtifact = {
          path: artifactFile.path,
          size: artifactFile.size,
          sha256: artifactFile.sha256,
        };
      } catch {
        fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
      } finally {
        await artifactFile.handle.close().catch(() => undefined);
      }
    } else if (artifact !== null && artifact !== undefined) {
      fail(409, "TRANSLATION_PIPELINE_EVIDENCE_INVALID");
    }

    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;

    job.reportJson = conversion.jsonReport;
    job.reportMarkdown = conversion.markdownReport;
    if (conversion.reportBundle) job.reportBundle = conversion.reportBundle;
    else delete job.reportBundle;
    job.conversionSummary = conversion.summary;
    job.reportReady = true;
    job.artifactReady = false;
    if (verifiedArtifact) {
      job.artifactSha256 = verifiedArtifact.sha256;
      job.artifactSize = verifiedArtifact.size;
    } else {
      delete job.artifactSha256;
      delete job.artifactSize;
    }
    job.snapshotSha256 = String(report.snapshot_sha256);
    job.readyCount = readyCount;
    job.workUnitCount = workUnitCount;
    job.includedUnitCount = includedUnitCount;
    job.statusCounts = Object.fromEntries(
      Object.entries(batchCounts).map(([key, value]) => [key, Number(value)]),
    );
    job.buildVerification = buildVerification;
    finalizedReportValidated = true;
    job.stage = "metering";
    job.progress = 99;
    job.artifactReady = false;
    await metering?.finish(status !== "BLOCKED");
    metering = null;
    if (!await durableExecutionIsCurrent(runner, context, job.id, executionId)) return;
    job.status = status as "COMPLETE" | "PARTIAL" | "BLOCKED";
    job.stage = status === "BLOCKED" ? "blocked" : "complete";
    job.progress = 100;
    job.artifactReady = conversion.summary.codeArtifactReady;
    if (status === "BLOCKED") {
      job.reason = packagingCapacityFailed
        ? String(packagingReasonCode)
        : typeof report.reason === "string"
        ? redact(report.reason)
        : conversion.summary.failureSummaries[0]?.failureCode
          ?? "TRANSLATION_PIPELINE_REPORTED_BLOCKED";
    } else {
      delete job.reason;
    }
    appendLog(
      job,
      "system",
      conversion.summary.denominatorComplete
        ? `Pipeline ${job.status}; project functional conversion ${conversion.summary.exactFraction} (${conversion.summary.displayPercent}); report digest ${conversion.markdownReport.sha256}.`
        : `Pipeline ${job.status}; reported CALLABLE diagnostic ${conversion.summary.exactFraction} (${conversion.summary.displayPercent}); project rate ${conversion.summary.projectSuccessRateDisplay}; report digest ${conversion.markdownReport.sha256}.`,
    );
    if (!await persistExecutionIfCurrent(runner, context, job, executionId)) return;
  } catch (error) {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (meteringError) {
        error = meteringError;
      }
      metering = null;
    }
    if (
      !executionId
      || !await durableExecutionIsCurrent(runner, context, job.id, executionId)
    ) return;
    if (!finalizedReportValidated) clearUnvalidatedReport(job);
    job.status = "BLOCKED";
    job.stage = "blocked";
    job.progress = 100;
    job.artifactReady = false;
    job.reason = error instanceof GenerationRunnerError
      ? error.message
      : "TRANSLATION_PIPELINE_BLOCKED";
    appendLog(job, "system", `Pipeline blocked: ${job.reason}`);
    await persistExecutionIfCurrent(runner, context, job, executionId);
  } finally {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (error) {
        if (
          executionId
          && await durableExecutionIsCurrent(runner, context, job.id, executionId)
        ) {
          if (!finalizedReportValidated) clearUnvalidatedReport(job);
          job.status = "BLOCKED";
          job.stage = "blocked";
          job.artifactReady = false;
          job.reason = error instanceof GenerationRunnerError
            ? error.message
            : "USAGE_SETTLEMENT_FAILED";
          await persistExecutionIfCurrent(runner, context, job, executionId);
        }
      }
    }
    if (state.generations.get(processKey) === generation) state.active.delete(processKey);
    if (leaseHeartbeat) clearInterval(leaseHeartbeat);
    if (queueLease) {
      let durableJob = job;
      try {
        durableJob = await load(runner, context, job.id);
      } catch {
        // Release still fails closed below if durable storage disappeared.
      }
      const outcome = durableJob.cancelRequestedAt || durableJob.status === "CANCELLED"
        ? "CANCELLED"
        : durableJob.status === "COMPLETE" || durableJob.status === "PARTIAL"
        ? "SUCCEEDED"
        : durableJob.status === "BLOCKED"
            ? "BLOCKED"
            : "FAILED";
      try {
        await queueLease.release(outcome);
      } catch {
        if (
          executionId
          && await durableExecutionIsCurrent(runner, context, job.id, executionId)
        ) {
          job.status = "BLOCKED";
          job.stage = "blocked";
          job.artifactReady = false;
          job.reason = "QUEUE_LEASE_RELEASE_FAILED";
          await persistExecutionIfCurrent(runner, context, job, executionId);
        }
      }
    }
    if (!requeued) {
      if (executionIsCurrent(processKey, generation)) {
        state.scheduled.delete(processKey);
        state.cancelled.delete(processKey);
        state.generations.delete(processKey);
      } else if (
        state.cancelled.has(processKey)
        && state.generations.get(processKey) !== generation
        && !state.active.has(processKey)
      ) {
        state.scheduled.delete(processKey);
        state.cancelled.delete(processKey);
        state.generations.delete(processKey);
      }
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
  const generation = (state.generations.get(processKey) ?? 0) + 1;
  state.generations.set(processKey, generation);
  state.scheduled.add(processKey);
  setImmediate(() => void execute(runner, context, job, generation));
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
  if (process.env.NODE_ENV === "production" && request.workspaceId) {
    fail(400, "TRANSLATION_DIRECT_WORKSPACE_FORBIDDEN");
  }
  if (process.env.NODE_ENV === "production" && !request.repositoryWorkspaceId) {
    fail(400, "TRANSLATION_REPOSITORY_WORKSPACE_REQUIRED");
  }
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
  await materializedDirectory(
    translationCasesBase(runner, context),
    casesBundleId,
    "TRANSLATION_CASES_BUNDLE",
  );
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
    reportReady: false,
    independentVerificationStatus: "NOT_RUN",
    externalVerificationStatus: "NOT_RUN",
    certificationStatus: "NOT_CERTIFIED",
    logs: [],
  };
  appendLog(
    job,
    "system",
    `Precheck queued for ${sourceLanguage}-to-${targetLanguage}; conversion and metering are not yet accepted.`,
  );
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
  let job = await load(runner, context, jobId);
  const processKey = key(context, job.id);
  if (!["QUEUED", "PRECHECK", "RUNNING"].includes(job.status)) return job;
  const lease = await DurableJobLease.observe({
    configuration: durableQueueConfiguration(runner.root, "translation"),
    tenantId: context.tenantId,
    jobId: job.id,
    inputDigest: translationInputDigest(job),
  });
  if (lease.active) {
    if (!lease.inputDigestMatches) fail(409, "TRANSLATION_QUEUE_LEASE_IDENTITY_MISMATCH");
    return job;
  }

  let cleanedReceipt: TranslationExecutionRuntimeReceipt | undefined;
  try {
    cleanedReceipt = await cleanupRuntimeReceipt(runner, context, job);
  } catch {
    job = await withTranslationControl(runner, async () => {
      const current = await load(runner, context, jobId);
      if (current.runtimeReceipt) {
        current.runtimeReceipt.state = "CLEANUP_UNVERIFIED";
        current.runtimeReceipt.updatedAt = new Date().toISOString();
      }
      current.status = "BLOCKED";
      current.stage = "blocked";
      current.progress = 100;
      current.reason = "CANCEL_CLEANUP_UNVERIFIED";
      clearPriorExecutionOutputs(current);
      appendLog(current, "system", "Persistent execution recovery could not verify runtime cleanup.");
      await writeControlledJob(runner, context, current);
      return current;
    });
    return job;
  }

  let shouldSchedule = false;
  job = await withTranslationControl(runner, async () => {
    const current = await load(runner, context, jobId);
    if (!["QUEUED", "PRECHECK", "RUNNING"].includes(current.status)) return current;
    if (cleanedReceipt && current.executionId === cleanedReceipt.executionId) {
      current.runtimeReceipt = cleanedReceipt;
    }
    if (current.cancelRequestedAt) {
      current.status = "CANCELLED";
      current.stage = "cancelled";
      current.progress = 100;
      current.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
      clearPriorExecutionOutputs(current);
      appendLog(current, "system", "Durable cancellation reconciled after the prior worker lease ended.");
    } else {
      const recoveryAlreadyQueued = current.stage === "restart-recovery"
        && Date.now() - Date.parse(current.updatedAt) < 30_000;
      if (!recoveryAlreadyQueued) current.recoveryAttempts += 1;
      current.stage = "restart-recovery";
      if (current.recoveryAttempts > 2) {
        current.status = "BLOCKED";
        current.stage = "blocked";
        current.reason = "TRANSLATION_RESTART_RECOVERY_LIMIT_EXCEEDED";
      } else {
        current.status = "QUEUED";
        if (!recoveryAlreadyQueued) {
          appendLog(current, "system", "Expired worker lease reconciled; pipeline will resume.");
        }
        shouldSchedule = true;
      }
    }
    await writeControlledJob(runner, context, current);
    return current;
  });
  if (shouldSchedule && !state.active.has(processKey) && !state.scheduled.has(processKey)) {
    schedule(runner, context, job);
  }
  return job;
}

export async function cancelTranslationJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<TranslationJob> {
  const runner = runnerConfig();
  const requestedAt = new Date().toISOString();
  let job = await withTranslationControl(runner, async () => {
    const current = await load(runner, context, jobId);
    const retryingCleanup = current.status === "BLOCKED"
      && current.reason === "CANCEL_CLEANUP_UNVERIFIED"
      && Boolean(current.cancelRequestedAt);
    if (!["QUEUED", "PRECHECK", "RUNNING"].includes(current.status) && !retryingCleanup) {
      fail(409, "TRANSLATION_JOB_NOT_CANCELLABLE");
    }
    clearPriorExecutionOutputs(current);
    current.cancelRequestedAt ??= requestedAt;
    current.cancelRequestedBy ??= context.actor;
    current.reason = "CANCEL_REQUESTED";
    appendLog(current, "system", `Durable cancellation requested by ${context.actor}.`);
    await writeControlledJob(runner, context, current);
    return current;
  });
  const processKey = key(context, job.id);
  state.generations.set(processKey, (state.generations.get(processKey) ?? 0) + 1);
  state.cancelled.add(processKey);
  state.scheduled.delete(processKey);
  let cleanedReceipt: TranslationExecutionRuntimeReceipt | undefined;
  try {
    cleanedReceipt = await cleanupRuntimeReceipt(runner, context, job);
  } catch {
    job = await withTranslationControl(runner, async () => {
      const current = await load(runner, context, jobId);
      if (current.runtimeReceipt) {
        current.runtimeReceipt.state = "CLEANUP_UNVERIFIED";
        current.runtimeReceipt.updatedAt = new Date().toISOString();
      }
      current.status = "BLOCKED";
      current.stage = "blocked";
      current.progress = 100;
      current.reason = "CANCEL_CLEANUP_UNVERIFIED";
      clearPriorExecutionOutputs(current);
      appendLog(current, "system", "Cancellation blocked because runtime cleanup could not be verified.");
      await writeControlledJob(runner, context, current);
      return current;
    });
    return job;
  }
  job = await withTranslationControl(runner, async () => {
    const current = await load(runner, context, jobId);
    if (cleanedReceipt && current.executionId === cleanedReceipt.executionId) {
      current.runtimeReceipt = cleanedReceipt;
    }
    current.status = "CANCELLED";
    current.stage = "cancelled";
    current.progress = 100;
    current.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
    clearPriorExecutionOutputs(current);
    appendLog(current, "system", `Job cancellation and runtime cleanup verified for ${context.actor}.`);
    await writeControlledJob(runner, context, current);
    return current;
  });
  if (!state.active.has(processKey)) {
    state.cancelled.delete(processKey);
    state.generations.delete(processKey);
  }
  return job;
}

export async function translationArtifact(
  context: AuthorizedContext,
  jobId: string,
): Promise<{ handle: FileHandle; path: string; size: number; sha256: string }> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  if (!job.artifactReady || !job.artifactSha256 || !job.artifactSize) {
    fail(409, "TRANSLATION_ARTIFACT_NOT_READY");
  }
  if (
    !digestPattern.test(job.artifactSha256)
    || !Number.isSafeInteger(job.artifactSize)
    || job.artifactSize < 1
    || job.artifactSize > MAX_TRANSLATION_ARTIFACT_BYTES
  ) {
    fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
  }
  if (
    (job.status !== "COMPLETE" && job.status !== "PARTIAL")
    || !job.snapshotSha256
    || !job.conversionSummary
    || !job.conversionSummary.codeArtifactReady
  ) fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
  const descriptor = {
    path: "repository-migration-artifact.zip" as const,
    bytes: job.artifactSize,
    sha256: job.artifactSha256,
  };
  const artifact = await verifiedOpenPipelineFile(
    confined(jobRoot(runner, context, jobId), "pipeline"),
    descriptor,
    "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH",
  );
  try {
    await validateTranslationCodeArtifactArchive(
      artifact.handle,
      descriptor,
      {
        pipelineStatus: job.status,
        repositoryRef: job.repositoryRef,
        snapshotSha256: job.snapshotSha256,
        routeId: `${job.sourceLanguage}-to-${job.targetLanguage}`,
        profile: "typed-pure-function-v1",
        summary: job.conversionSummary,
      },
    );
    return artifact;
  } catch {
    await artifact.handle.close().catch(() => undefined);
    fail(409, "TRANSLATION_ARTIFACT_INTEGRITY_MISMATCH");
  }
}

export async function translationReport(
  context: AuthorizedContext,
  jobId: string,
  format: "json" | "markdown" | "bundle",
): Promise<{ handle: FileHandle; path: string; size: number; sha256: string }> {
  const runner = runnerConfig();
  const job = await load(runner, context, jobId);
  const descriptor = format === "json"
    ? job.reportJson
    : format === "bundle" ? job.reportBundle : job.reportMarkdown;
  if (!job.reportReady || !descriptor) fail(409, "TRANSLATION_REPORT_NOT_READY");
  const expectedPath = format === "json"
    ? "functional-conversion-report.json"
    : format === "bundle"
      ? "FUNCTION_CONVERSION_REPORT_BUNDLE.zip"
      : "FUNCTION_CONVERSION_REPORT.md";
  const maximumBytes = format === "bundle"
    ? MAX_FUNCTIONAL_REPORT_BUNDLE_BYTES
    : 64 * 1024 * 1024;
  if (
    descriptor.path !== expectedPath
    || !Number.isSafeInteger(descriptor.bytes)
    || descriptor.bytes < 1
    || descriptor.bytes > maximumBytes
    || !digestPattern.test(descriptor.sha256)
  ) fail(409, "TRANSLATION_REPORT_INTEGRITY_MISMATCH");
  return verifiedOpenPipelineFile(
    confined(jobRoot(runner, context, jobId), "pipeline"),
    descriptor,
    "TRANSLATION_REPORT_INTEGRITY_MISMATCH",
  );
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
      reason: error instanceof GenerationRunnerError
        ? error.message
        : "TRANSLATION_RUNNER_BLOCKED",
    };
  }
}
