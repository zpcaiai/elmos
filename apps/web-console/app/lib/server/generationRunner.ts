import { createHash, randomUUID, timingSafeEqual } from "node:crypto";
import { spawn, type ChildProcess } from "node:child_process";
import {
  constants as fsConstants,
  createReadStream,
  existsSync,
  lstatSync,
  readFileSync,
  statSync,
} from "node:fs";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { beginMeteredExecution, type MeteredExecution } from "./commercialUsageProducer";
import {
  buildGenerationSourceBundle,
  sourceIngestionError,
} from "./generationSourceIngestion";
import {
  RepositoryWorkspaceProxyError,
  repositoryGenerationSources,
} from "./repositoryWorkspaceProxy";
import {
  DurableJobLease,
  DurableLeaseError,
  durableQueueConfiguration,
} from "./durableJobLease";
import {
  accountCookieNames,
  AccountSessionError,
  accountSessionFromRequest,
  unsafeCookieValue,
  type AccountPermission,
} from "./accountSession";
import { OrderedSnapshotPersistence } from "./orderedSnapshotPersistence";
import type { NextRequest } from "next/server";
import type {
  GenerationAnalysis,
  GenerationAnalyzeRequest,
  GenerationArtifact,
  GenerationJob,
  GenerationJobCreateRequest,
  GenerationJobLog,
  GenerationRuntime,
  GenerationSourceBundle,
  GenerationSourceReference,
  GenerationTargetId,
} from "../contracts";

type GenerationRunnerProcessState = {
  activeJobs: Map<string, ChildProcess>;
  activeRuntimes: Map<string, ChildProcess>;
  runtimeJobs: Map<string, GenerationJob>;
  activeRootlessRuntimes: Set<string>;
  previewProcesses: Set<ChildProcess>;
  activeAnalyses: Map<string, number>;
  scheduledJobs: Set<string>;
  cancelledJobs: Set<string>;
  intentionallyStoppedRuntimes: WeakSet<ChildProcess>;
  jobPersistence: OrderedSnapshotPersistence;
  exitCleanupRegistered: boolean;
};

const globalRunnerState = globalThis as typeof globalThis & {
  __elmosGenerationRunnerState?: GenerationRunnerProcessState;
};
const processState = globalRunnerState.__elmosGenerationRunnerState ??= {
  activeJobs: new Map<string, ChildProcess>(),
  activeRuntimes: new Map<string, ChildProcess>(),
  runtimeJobs: new Map<string, GenerationJob>(),
  activeRootlessRuntimes: new Set<string>(),
  previewProcesses: new Set<ChildProcess>(),
  activeAnalyses: new Map<string, number>(),
  scheduledJobs: new Set<string>(),
  cancelledJobs: new Set<string>(),
  intentionallyStoppedRuntimes: new WeakSet<ChildProcess>(),
  jobPersistence: new OrderedSnapshotPersistence(atomicJson),
  exitCleanupRegistered: false,
};
// Next.js development HMR preserves this object across module revisions. Hydrate
// every field independently so a newly added registry cannot be undefined in an
// already-running process; production starts still take the initializer above.
processState.activeJobs ??= new Map<string, ChildProcess>();
processState.activeRuntimes ??= new Map<string, ChildProcess>();
processState.runtimeJobs ??= new Map<string, GenerationJob>();
processState.activeRootlessRuntimes ??= new Set<string>();
processState.jobPersistence ??= new OrderedSnapshotPersistence(atomicJson);
processState.activeAnalyses ??= new Map<string, number>();
processState.scheduledJobs ??= new Set<string>();
processState.cancelledJobs ??= new Set<string>();
processState.intentionallyStoppedRuntimes ??= new WeakSet<ChildProcess>();
processState.exitCleanupRegistered ??= false;
const {
  activeJobs,
  activeRuntimes,
  runtimeJobs,
  activeRootlessRuntimes,
  previewProcesses,
  activeAnalyses,
  scheduledJobs,
  cancelledJobs,
  intentionallyStoppedRuntimes,
} = processState;
if (!processState.exitCleanupRegistered) {
  const terminateAll = () => {
    for (const child of [
      ...activeJobs.values(),
      ...activeRuntimes.values(),
      ...previewProcesses.values(),
    ]) terminate(child);
  };
  process.once("exit", terminateAll);
  for (const [signal, exitCode] of [
    ["SIGINT", 130],
    ["SIGTERM", 143],
    ["SIGHUP", 129],
  ] as const) {
    process.once(signal, () => {
      terminateAll();
      process.exit(exitCode);
    });
  }
  processState.exitCleanupRegistered = true;
}
const targetIds = new Set<GenerationTargetId>([
  "java",
  "python",
  "csharp",
  "typescript",
  "go",
  "kotlin",
  "php",
  "rust",
]);
const targetPorts: Record<GenerationTargetId, number> = {
  java: 8081,
  python: 8082,
  csharp: 8083,
  typescript: 8084,
  go: 8085,
  kotlin: 8086,
  php: 8087,
  rust: 8088,
};
const pythonModulePattern = /^[a-z][a-z0-9_]{1,127}$/;
const jobIdPattern = /^[0-9a-f-]{36}$/;
const digestPattern = /^[a-f0-9]{64}$/;
const tenantPattern = /^[a-z][a-z0-9-]{2,62}$/;
const actorPattern = /^[a-zA-Z0-9][a-zA-Z0-9._:@/-]{2,199}$/;
const namePattern = /^[a-z][a-z0-9-]{1,62}[a-z0-9]$/;
const namespacePattern = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/;
const entityPattern = /^[a-z][a-z0-9_]{1,62}[a-z0-9]$/;
const sensitivePattern = /(authorization|token|secret|password|cookie|api[-_]?key)\s*[:=]\s*\S+/gi;

type RunnerConfig = {
  root: string;
  repositoryRoot: string;
  engineRoot: string;
  uv: string;
  executor: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT";
  containerEngine?: string;
  buildNetwork: string;
  rootlessTool: string;
};

export type GenerationRunnerHealth = {
  status: "READY" | "DISABLED" | "BLOCKED";
  persistence: "FILESYSTEM_ATOMIC";
  auth: "BEARER_TENANT_BOUND";
  storage: "READ_WRITE" | "NOT_RUN" | "BLOCKED";
  isolation: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT" | "NOT_CONFIGURED";
  recovery: "PERSISTENT_RECONCILIATION";
  activeJobs: number;
  activeRuntimes: number;
  activeAnalyses: number;
  reason?: string;
  checkedAt: string;
};

type AuthorizedContext = {
  tenantId: string;
  actor: string;
  accessToken?: string;
};

type CommandResult = {
  exitCode: number;
  stdout: string;
  stderr: string;
};

type StoredAnalysisReview = {
  tenantId: string;
  actor: string;
  createdAt: string;
  expiresAt: string;
  intent: GenerationAnalyzeRequest;
  requestDigest: string;
  request: GenerationAnalysis["request"];
};

type StoredSourceBundle = {
  tenantId: string;
  actor: string;
  createdAt: string;
  expiresAt: string;
  bundle: GenerationSourceBundle;
};

export class GenerationRunnerError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
  ) {
    super(code);
  }
}

function configuredToken(): string {
  const token = process.env.ELMOS_LOCAL_RUNNER_AUTH_TOKEN;
  const tokenFile = process.env.ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE;
  if (Boolean(token) === Boolean(tokenFile)) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_AUTH_NOT_CONFIGURED");
  }
  if (token) {
    if (token.length < 24 || token.length > 4_096) {
      throw new GenerationRunnerError(503, "LOCAL_RUNNER_AUTH_NOT_CONFIGURED");
    }
    return token;
  }
  if (!tokenFile || !path.isAbsolute(tokenFile)) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_AUTH_NOT_CONFIGURED");
  }
  const info = lstatSync(tokenFile);
  if (
    info.isSymbolicLink()
    || !info.isFile()
    || info.size > 4_096
    || (info.mode & 0o077) !== 0
  ) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_AUTH_FILE_UNSAFE");
  }
  const value = readFileSync(tokenFile, "utf-8").trim();
  if (value.length < 24 || value.length > 4_096) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_AUTH_NOT_CONFIGURED");
  }
  return value;
}

function config(): RunnerConfig {
  if (process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true") {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_NOT_ENABLED");
  }
  const root = process.env.ELMOS_LOCAL_RUNNER_ROOT;
  const repositoryRoot = process.env.ELMOS_REPOSITORY_ROOT;
  const uv = process.env.ELMOS_UV_PATH;
  const executor = process.env.ELMOS_LOCAL_RUNNER_EXECUTOR;
  const containerEngine = process.env.ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE;
  const buildNetwork = process.env.ELMOS_LOCAL_RUNNER_BUILD_NETWORK ?? "none";
  if (!root || !path.isAbsolute(root)) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_ROOT_NOT_CONFIGURED");
  }
  if (!repositoryRoot || !path.isAbsolute(repositoryRoot)) {
    throw new GenerationRunnerError(503, "REPOSITORY_ROOT_NOT_CONFIGURED");
  }
  if (!uv || !path.isAbsolute(uv)) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_UV_NOT_CONFIGURED");
  }
  if (!["ROOTLESS_CONTAINER", "HOST_DEVELOPMENT"].includes(executor ?? "")) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_EXECUTOR_NOT_CONFIGURED");
  }
  if (executor === "HOST_DEVELOPMENT" && process.env.NODE_ENV === "production") {
    throw new GenerationRunnerError(503, "HOST_EXECUTOR_FORBIDDEN_IN_PRODUCTION");
  }
  if (!/^(none|slirp4netns|[a-z0-9][a-z0-9_.-]{2,62})$/.test(buildNetwork)) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_BUILD_NETWORK_INVALID");
  }
  const resolvedRoot = path.resolve(root);
  const resolvedRepositoryRoot = path.resolve(repositoryRoot);
  const engineRoot = path.resolve(resolvedRepositoryRoot, "engines/project-synthesis-engine");
  const rootlessTool = path.resolve(
    resolvedRepositoryRoot,
    "scripts/operations/rootless_project_runner.py",
  );
  if (
    resolvedRoot === path.parse(resolvedRoot).root
    || resolvedRepositoryRoot === resolvedRoot
    || resolvedRepositoryRoot.startsWith(`${resolvedRoot}${path.sep}`)
  ) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_ROOT_UNSAFE");
  }
  if (
    !existsSync(engineRoot)
    || !statSync(engineRoot).isDirectory()
    || !existsSync(uv)
    || !statSync(uv).isFile()
    || !existsSync(rootlessTool)
    || !statSync(rootlessTool).isFile()
  ) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_EXECUTION_ASSET_MISSING");
  }
  if (executor === "ROOTLESS_CONTAINER") {
    if (
      !containerEngine
      || !path.isAbsolute(containerEngine)
      || !existsSync(containerEngine)
      || !statSync(containerEngine).isFile()
      || !["docker", "podman"].includes(path.basename(containerEngine))
    ) {
      throw new GenerationRunnerError(503, "ROOTLESS_CONTAINER_ENGINE_NOT_CONFIGURED");
    }
  }
  return {
    root: resolvedRoot,
    repositoryRoot: resolvedRepositoryRoot,
    engineRoot,
    uv,
    executor: executor as RunnerConfig["executor"],
    containerEngine,
    buildNetwork,
    rootlessTool,
  };
}

function safeEqual(left: string, right: string): boolean {
  const leftDigest = createHash("sha256").update(left).digest();
  const rightDigest = createHash("sha256").update(right).digest();
  return timingSafeEqual(leftDigest, rightDigest);
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map(
    (key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`,
  ).join(",")}}`;
}

function sha256Json(value: unknown): string {
  return createHash("sha256").update(canonicalJson(value)).digest("hex");
}

function intentContract(request: GenerationAnalyzeRequest): GenerationAnalyzeRequest {
  return {
    name: request.name,
    namespace: request.namespace,
    description: request.description,
    entity: request.entity,
    targets: [...request.targets],
    persistence: request.persistence,
    authMode: request.authMode,
    ...(request.sources ? { sources: request.sources.map((source) => ({ ...source })) } : {}),
    ...(request.sourceBundleSha256 ? { sourceBundleSha256: request.sourceBundleSha256 } : {}),
  };
}

export function authorize(
  request: NextRequest,
  permission: AccountPermission = "generation:execute",
): AuthorizedContext {
  const hasAccountCookie = Boolean(
    unsafeCookieValue(request, accountCookieNames.session),
  );
  if (hasAccountCookie) {
    try {
      const account = accountSessionFromRequest(request, permission);
      return {
        tenantId: account.principal.organizationId,
        actor: account.principal.actorId,
        accessToken: account.accessToken,
      };
    } catch (error) {
      if (error instanceof AccountSessionError) {
        throw new GenerationRunnerError(error.status, error.code);
      }
      throw error;
    }
  }
  if (
    process.env.NODE_ENV === "production"
    || process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true"
  ) {
    throw new GenerationRunnerError(401, "ACCOUNT_SESSION_REQUIRED");
  }
  const runner = {
    token: configuredToken(),
    tenantId: process.env.ELMOS_LOCAL_RUNNER_TENANT_ID ?? "",
    actor: process.env.ELMOS_LOCAL_RUNNER_ACTOR_ID ?? "",
  };
  const tokenExpiresAt = process.env.ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT ?? "";
  const tokenExpiry = Date.parse(tokenExpiresAt);
  if (
    !tenantPattern.test(runner.tenantId)
    || !actorPattern.test(runner.actor)
  ) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_IDENTITY_LEASE_INVALID");
  }
  if (
    !/(Z|[+-]\d{2}:\d{2})$/.test(tokenExpiresAt)
    || Number.isNaN(tokenExpiry)
    || tokenExpiry <= Date.now()
    || tokenExpiry > Date.now() + 24 * 60 * 60_000
  ) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_TOKEN_LEASE_INVALID");
  }
  const authorization = request.headers.get("authorization") ?? "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  const tenantId = request.headers.get("x-elmos-tenant") ?? "";
  const actor = request.headers.get("x-elmos-actor") ?? "";
  if (!safeEqual(token, runner.token)) {
    throw new GenerationRunnerError(401, "AUTHENTICATION_REQUIRED");
  }
  if (!tenantPattern.test(tenantId) || !safeEqual(tenantId, runner.tenantId)) {
    throw new GenerationRunnerError(403, "TENANT_ID_NOT_BOUND_TO_CREDENTIAL");
  }
  if (!actorPattern.test(actor) || !safeEqual(actor, runner.actor)) {
    throw new GenerationRunnerError(403, "ACTOR_ID_NOT_BOUND_TO_CREDENTIAL");
  }
  return { tenantId, actor };
}

function confined(base: string, ...segments: string[]): string {
  const candidate = path.resolve(base, ...segments);
  if (candidate !== base && !candidate.startsWith(`${base}${path.sep}`)) {
    throw new GenerationRunnerError(400, "PATH_CONFINEMENT_FAILED");
  }
  return candidate;
}

function jobKey(context: AuthorizedContext, jobId: string): string {
  return `${context.tenantId}:${jobId}`;
}

function jobRoot(runner: RunnerConfig, context: AuthorizedContext, jobId: string): string {
  if (!jobIdPattern.test(jobId)) {
    throw new GenerationRunnerError(400, "JOB_ID_INVALID");
  }
  return confined(runner.root, "tenants", context.tenantId, "jobs", jobId);
}

function jobFile(runner: RunnerConfig, context: AuthorizedContext, jobId: string): string {
  return confined(jobRoot(runner, context, jobId), "job.json");
}

function analysisReviewFile(
  runner: RunnerConfig,
  context: AuthorizedContext,
  requestDigest: string,
): string {
  if (!digestPattern.test(requestDigest)) {
    throw new GenerationRunnerError(400, "ANALYSIS_DIGEST_INVALID");
  }
  return confined(
    runner.root,
    "tenants",
    context.tenantId,
    "analysis-reviews",
    `${requestDigest}.json`,
  );
}

function sourceBundleFile(
  runner: RunnerConfig,
  context: AuthorizedContext,
  bundleDigest: string,
): string {
  if (!digestPattern.test(bundleDigest)) {
    throw new GenerationRunnerError(400, "SOURCE_BUNDLE_DIGEST_INVALID");
  }
  return confined(
    runner.root,
    "tenants",
    context.tenantId,
    "source-bundles",
    `${bundleDigest}.json`,
  );
}

function maintenanceFile(runner: RunnerConfig): string {
  return confined(runner.root, ".maintenance.json");
}

function ensureMutationsAllowed(runner: RunnerConfig): void {
  if (existsSync(maintenanceFile(runner))) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_QUIESCED");
  }
}

function redact(value: string): string {
  let token: string | undefined;
  try {
    token = configuredToken();
  } catch {
    token = undefined;
  }
  const tokenRedacted = token ? value.replaceAll(token, "[REDACTED]") : value;
  return tokenRedacted.replace(
    sensitivePattern,
    "$1=[REDACTED]",
  );
}

function runtimeCommandShapeValid(
  language: GenerationTargetId,
  command: string[],
  port: number,
): boolean {
  const executable = path.basename(command[0]);
  if (!path.isAbsolute(command[0]) && command[0] !== executable) return false;
  switch (language) {
    case "java":
      return executable === "java"
        && command.length === 3
        && command[1] === "-jar"
        && path.isAbsolute(command[2])
        && command[2].endsWith(".jar");
    case "python":
      return executable === "uv"
        && command[1] === "run"
        && command[2] === "python"
        && (
          (
            command.length === 5
            && command[3] === "-m"
            && pythonModulePattern.test(command[4])
          )
          || (
            command.length === 4
            && command[3] === "scripts/local_runtime.py"
          )
        );
    case "csharp":
      return executable === "dotnet"
        && command.length === 7
        && command[1] === "run"
        && command[2] === "--no-build"
        && command[3] === "-c"
        && command[4] === "Release"
        && command[5] === "--project"
        && path.isAbsolute(command[6])
        && command[6].endsWith(".csproj");
    case "typescript":
      return executable === "pnpm" && command.length === 2 && command[1] === "start";
    case "go":
      return executable === "go" && command.length === 3 && command[1] === "run" && command[2] === ".";
    case "kotlin":
      return executable === "gradle"
        && command.length === 3
        && command[1] === "--no-daemon"
        && command[2] === "run";
    case "php":
      return executable === "php"
        && command.length === 4
        && command[1] === "-S"
        && command[2] === `127.0.0.1:${port}`
        && command[3] === "public/index.php";
    case "rust":
      return executable === "cargo"
        && command.length === 3
        && command[1] === "run"
        && command[2] === "--locked";
  }
}

async function sha256File(file: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(file)) {
    digest.update(chunk);
  }
  return digest.digest("hex");
}

async function atomicJson(destination: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
  const temporary = `${destination}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: "utf-8",
    mode: 0o600,
  });
  await rename(temporary, destination);
}

function log(job: GenerationJob, stream: GenerationJobLog["stream"], message: string): void {
  const redacted = redact(message).trim();
  if (!redacted) return;
  job.logs.push({
    at: new Date().toISOString(),
    stream,
    message: redacted.slice(-4_000),
  });
  job.logs = job.logs.slice(-250);
  job.updatedAt = new Date().toISOString();
}

async function persist(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
): Promise<void> {
  await processState.jobPersistence.persist(jobFile(runner, context, job.id), job);
}

async function load(
  runner: RunnerConfig,
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  let parsed: GenerationJob;
  try {
    parsed = JSON.parse(
      await readFile(jobFile(runner, context, jobId), "utf-8"),
    ) as GenerationJob;
  } catch {
    throw new GenerationRunnerError(404, "JOB_NOT_FOUND");
  }
  if (parsed.tenantId !== context.tenantId) {
    throw new GenerationRunnerError(404, "JOB_NOT_FOUND");
  }
  parsed.artifacts ??= [];
  const key = jobKey(context, jobId);
  if (
    ["QUEUED", "ANALYZING", "GENERATING", "VERIFYING", "ARCHIVING"].includes(parsed.status)
    && !activeJobs.has(key)
    && !scheduledJobs.has(key)
  ) {
    parsed.recoveryAttempts = (parsed.recoveryAttempts ?? 0) + 1;
    parsed.stage = "restart-recovery";
    if (parsed.recoveryAttempts > 2) {
      parsed.status = "BLOCKED";
      parsed.reason = "RESTART_RECOVERY_LIMIT_EXCEEDED";
      log(parsed, "system", "Runner restart recovery limit exceeded; manual review is required.");
    } else {
      parsed.status = "QUEUED";
      parsed.reason = "RECOVERY_REQUEUED_AFTER_RESTART";
      scheduledJobs.add(key);
      log(parsed, "system", "Runner restart detected; the durable job was requeued.");
    }
    await persist(runner, context, parsed);
    if (parsed.status === "QUEUED") void runJob(runner, context, parsed);
  }
  if (
    parsed.runtime.executor === "ROOTLESS_CONTAINER"
    && ["STARTING", "RUNNING"].includes(parsed.runtime.status)
  ) {
    await reconcileRootlessRuntime(runner, context, parsed);
  } else if (parsed.runtime.status === "RUNNING" && !activeRuntimes.has(key)) {
    parsed.runtime.status = "BLOCKED";
    parsed.runtime.reason = "RUNTIME_PROCESS_LOST_AFTER_RESTART";
    parsed.runtime.updatedAt = new Date().toISOString();
    await persist(runner, context, parsed);
  }
  return parsed;
}

function sourceReferenceValid(source: unknown): source is GenerationSourceReference {
  if (!source || typeof source !== "object") return false;
  const value = source as Partial<GenerationSourceReference>;
  return typeof value.id === "string"
    && /^SRC-\d{3}$/.test(value.id)
    && [
      "description",
      "text-file",
      "markdown-file",
      "word-file",
      "html-file",
      "pdf-file",
      "online-html",
      "skill",
    ].includes(value.kind ?? "")
    && typeof value.label === "string"
    && value.label.length > 0
    && value.label.length <= 180
    && typeof value.mediaType === "string"
    && value.mediaType.length > 0
    && value.mediaType.length <= 160
    && (value.origin === undefined || (
      typeof value.origin === "string" && value.origin.length > 0 && value.origin.length <= 2_000
    ))
    && typeof value.sha256 === "string"
    && digestPattern.test(value.sha256)
    && Number.isInteger(value.byteCount)
    && (value.byteCount ?? 0) > 0
    && (value.byteCount ?? 0) <= 8 * 1024 * 1024
    && Number.isInteger(value.extractedCharacters)
    && (value.extractedCharacters ?? 0) >= 3
    && Number.isInteger(value.includedCharacters)
    && (value.includedCharacters ?? 0) >= 3
    && (value.includedCharacters ?? 0) <= (value.extractedCharacters ?? 0)
    && typeof value.truncated === "boolean"
    && Array.isArray(value.warnings)
    && value.warnings.length <= 20
    && value.warnings.every((warning) => (
      typeof warning === "string" && /^[A-Z0-9_:.-]{1,160}$/.test(warning)
    ));
}

function validateSourceBinding(request: GenerationAnalyzeRequest): void {
  const sourcesPresent = request.sources !== undefined;
  const digestPresent = request.sourceBundleSha256 !== undefined;
  if (sourcesPresent !== digestPresent) {
    throw new GenerationRunnerError(400, "SOURCE_BUNDLE_BINDING_INCOMPLETE");
  }
  if (!sourcesPresent || !digestPresent) return;
  if (
    !Array.isArray(request.sources)
    || request.sources.length === 0
    || request.sources.length > 17
    || !request.sources.every(sourceReferenceValid)
    || new Set(request.sources.map((source) => source.id)).size !== request.sources.length
    || request.sources.some((source, index) => source.id !== `SRC-${String(index + 1).padStart(3, "0")}`)
    || typeof request.sourceBundleSha256 !== "string"
    || !digestPattern.test(request.sourceBundleSha256)
    || !safeEqual(
      request.sourceBundleSha256,
      sha256Json({ description: request.description, sources: request.sources }),
    )
  ) {
    throw new GenerationRunnerError(400, "SOURCE_BUNDLE_BINDING_INVALID");
  }
}

function validateAnalyze(request: GenerationAnalyzeRequest): GenerationAnalyzeRequest {
  if (
    !request
    || typeof request !== "object"
    || typeof request.name !== "string"
    || typeof request.namespace !== "string"
    || typeof request.entity !== "string"
    || typeof request.description !== "string"
    || !Array.isArray(request.targets)
    || typeof request.persistence !== "string"
    || typeof request.authMode !== "string"
    || !namePattern.test(request.name)
    || !namespacePattern.test(request.namespace)
    || !entityPattern.test(request.entity)
  ) {
    throw new GenerationRunnerError(400, "PROJECT_INTENT_INVALID");
  }
  if (
    request.description.length < 3
    || request.description.length > 32_000
    || request.targets.length === 0
    || request.targets.length > targetIds.size
    || new Set(request.targets).size !== request.targets.length
    || !request.targets.every((target) => targetIds.has(target))
  ) {
    throw new GenerationRunnerError(400, "PROJECT_INTENT_INVALID");
  }
  const defaultProfile = request.persistence === "in-memory" && request.authMode === "none";
  // Mirrors SUPPORTED_PROFILE_TARGETS in the engine's models.py. Every target
  // named here carries PostgreSQL-backed integration evidence produced through
  // the shared runtime harness; a target without that evidence must not be
  // accepted even if its starter emitter exists.
  const productionEvidencedTargets = new Set([
    "python",
    "java",
    "go",
    "typescript",
    "csharp",
    "kotlin",
    "rust",
    "php",
  ]);
  const enterpriseProfile = request.persistence === "postgresql"
    && ["jwt", "oidc"].includes(request.authMode)
    && request.targets.length === 1
    && productionEvidencedTargets.has(request.targets[0]);
  if (!defaultProfile && !enterpriseProfile) {
    throw new GenerationRunnerError(400, "UNIMPLEMENTED_PRODUCTION_PROFILE");
  }
  validateSourceBinding(request);
  return request;
}

function validateCreate(
  request: GenerationJobCreateRequest,
  context: AuthorizedContext,
): GenerationJobCreateRequest {
  validateAnalyze(request);
  if (
    typeof request.reviewer !== "string"
    || typeof request.approved !== "boolean"
    || typeof request.analysisDigest !== "string"
    || request.reviewer !== context.actor
    || request.approved !== true
    || !digestPattern.test(request.analysisDigest)
  ) {
    throw new GenerationRunnerError(403, "EXPLICIT_APPROVAL_REQUIRED");
  }
  return request;
}

function commandEnvironment(runner: RunnerConfig): NodeJS.ProcessEnv {
  return {
    PATH: process.env.PATH,
    HOME: confined(runner.root, "home"),
    NODE_ENV: process.env.NODE_ENV,
    LANG: process.env.LANG ?? "en_US.UTF-8",
    LC_ALL: process.env.LC_ALL ?? "en_US.UTF-8",
    NO_PROXY: "127.0.0.1,localhost",
    no_proxy: "127.0.0.1,localhost",
  };
}

function engineCommandEnvironment(runner: RunnerConfig): NodeJS.ProcessEnv {
  return {
    ...commandEnvironment(runner),
    // Load the audited source tree directly. The synthesis CLI intentionally
    // has no third-party runtime dependencies; generated projects own their
    // language-specific dependencies and lockfiles.
    PYTHONPATH: path.join(runner.engineRoot, "src"),
  };
}

function isolatedPythonArguments(command: string[]): string[] {
  return [
    "run",
    "--offline",
    "--no-project",
    "--python",
    ">=3.12,<3.15",
    "python",
    ...command,
  ];
}

function engineCliArguments(command: string[]): string[] {
  return isolatedPythonArguments([
    "-m",
    "elmos_project_synthesis.cli",
    ...command,
  ]);
}

async function executePreviewCommand(
  runner: RunnerConfig,
  args: string[],
): Promise<CommandResult> {
  await mkdir(confined(runner.root, "home"), { recursive: true, mode: 0o700 });
  return new Promise((resolve, reject) => {
    const child = spawn(runner.uv, args, {
      cwd: runner.engineRoot,
      env: engineCommandEnvironment(runner),
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    previewProcesses.add(child);
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      terminate(child);
      reject(new GenerationRunnerError(504, "ANALYSIS_TIMEOUT"));
    }, 60_000);
    child.stdout?.on("data", (chunk: Buffer) => {
      stdout = `${stdout}${chunk.toString("utf-8")}`.slice(-200_000);
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr = `${stderr}${chunk.toString("utf-8")}`.slice(-200_000);
    });
    child.once("error", (error) => {
      clearTimeout(timeout);
      previewProcesses.delete(child);
      reject(error);
    });
    child.once("close", (code, signal) => {
      clearTimeout(timeout);
      previewProcesses.delete(child);
      resolve({
        exitCode: code ?? (signal ? 128 : 1),
        stdout: redact(stdout),
        stderr: redact(stderr),
      });
    });
  });
}

async function rootlessCommand(
  runner: RunnerConfig,
  args: string[],
  timeoutMs = 20 * 60_000,
): Promise<Record<string, unknown>> {
  if (runner.executor !== "ROOTLESS_CONTAINER" || !runner.containerEngine) {
    throw new GenerationRunnerError(503, "ROOTLESS_CONTAINER_EXECUTOR_REQUIRED");
  }
  return new Promise((resolve, reject) => {
    const child = spawn(
      runner.uv,
      isolatedPythonArguments([
        runner.rootlessTool,
        ...args,
      ]),
      {
        cwd: runner.repositoryRoot,
        env: engineCommandEnvironment(runner),
        detached: true,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      terminate(child);
      reject(new GenerationRunnerError(504, "ROOTLESS_RUNNER_TIMEOUT"));
    }, timeoutMs);
    child.stdout?.on("data", (chunk: Buffer) => {
      stdout = `${stdout}${chunk.toString("utf-8")}`.slice(-20_000);
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr = `${stderr}${chunk.toString("utf-8")}`.slice(-20_000);
    });
    child.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.once("close", (code) => {
      clearTimeout(timeout);
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(stdout.trim()) as Record<string, unknown>;
      } catch {
        reject(new GenerationRunnerError(500, "ROOTLESS_RUNNER_RESULT_INVALID"));
        return;
      }
      if (code !== 0 || parsed.status === "BLOCKED") {
        reject(
          new GenerationRunnerError(
            503,
            `ROOTLESS_RUNNER_BLOCKED:${redact(String(parsed.reason ?? stderr ?? "UNKNOWN"))}`,
          ),
        );
        return;
      }
      resolve(parsed);
    });
  });
}

export async function ingestGenerationSources(
  context: AuthorizedContext,
  input: {
    description?: string;
    url?: string;
    skillNames?: string[];
    files?: File[];
    repositoryWorkspaceId?: string;
    repositoryPaths?: string[];
  },
): Promise<GenerationSourceBundle> {
  const runner = config();
  ensureMutationsAllowed(runner);
  let bundle: GenerationSourceBundle;
  try {
    const repositorySources = input.repositoryWorkspaceId
      ? await repositoryGenerationSources({
        tenantId: context.tenantId,
        actor: context.actor,
        accessToken: context.accessToken,
        workspaceId: input.repositoryWorkspaceId,
        paths: input.repositoryPaths,
      })
      : [];
    bundle = await buildGenerationSourceBundle({
      description: input.description,
      url: input.url,
      skillNames: input.skillNames,
      files: input.files,
      repositorySources,
      repositoryRoot: runner.repositoryRoot,
    });
  } catch (error) {
    if (error instanceof RepositoryWorkspaceProxyError) {
      throw new GenerationRunnerError(error.status, error.errorCode);
    }
    const blocked = sourceIngestionError(error);
    throw new GenerationRunnerError(blocked.status, blocked.reason);
  }
  const sourceRoot = confined(runner.root, "tenants", context.tenantId, "source-bundles");
  await mkdir(sourceRoot, { recursive: true, mode: 0o700 });
  const existing = (await readdir(sourceRoot)).filter((entry) => entry.endsWith(".json"));
  if (existing.length >= 100 && !existing.includes(`${bundle.bundleSha256}.json`)) {
    throw new GenerationRunnerError(429, "SOURCE_BUNDLE_TENANT_LIMIT");
  }
  const now = new Date();
  const stored: StoredSourceBundle = {
    tenantId: context.tenantId,
    actor: context.actor,
    createdAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + 60 * 60_000).toISOString(),
    bundle,
  };
  await atomicJson(sourceBundleFile(runner, context, bundle.bundleSha256), stored);
  return bundle;
}

async function assertPersistedSourceBundle(
  runner: RunnerConfig,
  context: AuthorizedContext,
  request: GenerationAnalyzeRequest,
): Promise<void> {
  const digest = request.sourceBundleSha256;
  if (!digest || !request.sources) {
    throw new GenerationRunnerError(409, "SOURCE_BUNDLE_BINDING_INCOMPLETE");
  }
  let stored: StoredSourceBundle;
  try {
    stored = JSON.parse(
      await readFile(sourceBundleFile(runner, context, digest), "utf-8"),
    ) as StoredSourceBundle;
  } catch {
    throw new GenerationRunnerError(409, "SOURCE_BUNDLE_NOT_FOUND");
  }
  if (
    stored.tenantId !== context.tenantId
    || stored.actor !== context.actor
    || Number.isNaN(Date.parse(stored.expiresAt))
    || Date.parse(stored.expiresAt) <= Date.now()
    || stored.bundle.status !== "READY_FOR_REVIEW"
    || !safeEqual(stored.bundle.bundleSha256 ?? "", digest)
    || !safeEqual(stored.bundle.combinedText ?? "", request.description)
    || !safeEqual(sha256Json(stored.bundle.sources), sha256Json(request.sources))
    || !safeEqual(
      digest,
      sha256Json({ description: stored.bundle.combinedText, sources: stored.bundle.sources }),
    )
  ) {
    throw new GenerationRunnerError(409, "SOURCE_BUNDLE_MISMATCH");
  }
}

export async function analyzeIntent(
  context: AuthorizedContext,
  request: GenerationAnalyzeRequest,
): Promise<GenerationAnalysis> {
  const runner = config();
  ensureMutationsAllowed(runner);
  const validated = validateAnalyze(request);
  if (validated.sourceBundleSha256) {
    await assertPersistedSourceBundle(runner, context, validated);
  }
  const active = activeAnalyses.get(context.tenantId) ?? 0;
  if (active >= 2) {
    throw new GenerationRunnerError(429, "ANALYSIS_CONCURRENCY_LIMIT");
  }
  activeAnalyses.set(context.tenantId, active + 1);
  const base = confined(runner.root, "tenants", context.tenantId, "analysis");
  let temporary: string | undefined;
  try {
    await mkdir(base, { recursive: true, mode: 0o700 });
    temporary = await mkdtemp(path.join(base, "request-"));
    const intentPath = confined(temporary, "project-intent.json");
    const outputPath = confined(temporary, "synthesis-request.json");
    await atomicJson(intentPath, {
      schema_version: "1.1.0",
      name: validated.name,
      namespace: validated.namespace,
      description: validated.description,
      entity: validated.entity,
      languages: validated.targets,
      project_kind: "api",
      persistence: validated.persistence,
      auth_mode: validated.authMode,
      business_rules: [],
      permissions: [],
      ...(validated.sources ? { requirement_sources: validated.sources } : {}),
      ...(validated.sourceBundleSha256
        ? { source_bundle_sha256: validated.sourceBundleSha256 }
        : {}),
    });
    const result = await executePreviewCommand(runner, engineCliArguments([
      "analyze",
      "--intent",
      intentPath,
      "--output",
      outputPath,
    ]));
    if (result.exitCode !== 0) {
      throw new GenerationRunnerError(
        422,
        `ANALYSIS_FAILED:${(result.stderr || result.stdout).slice(-2_000)}`,
      );
    }
    const parsed = JSON.parse(await readFile(outputPath, "utf-8")) as GenerationAnalysis["request"];
    if (
      parsed.schema_version !== "1.1.0"
      || !Array.isArray(parsed.entities)
      || !Array.isArray(parsed.requirements)
      || !Array.isArray(parsed.open_questions)
    ) {
      throw new GenerationRunnerError(500, "ANALYSIS_RESULT_INVALID");
    }
    const requestDigest = sha256Json(parsed);
    const analyzedAt = new Date();
    const review: StoredAnalysisReview = {
      tenantId: context.tenantId,
      actor: context.actor,
      createdAt: analyzedAt.toISOString(),
      expiresAt: new Date(analyzedAt.getTime() + 30 * 60_000).toISOString(),
      intent: intentContract(validated),
      requestDigest,
      request: parsed,
    };
    await atomicJson(analysisReviewFile(runner, context, requestDigest), review);
    return {
      status: "REVIEW_REQUIRED",
      analyzedAt: analyzedAt.toISOString(),
      requestDigest,
      request: parsed,
    };
  } finally {
    const remaining = Math.max(0, (activeAnalyses.get(context.tenantId) ?? 1) - 1);
    if (remaining === 0) activeAnalyses.delete(context.tenantId);
    else activeAnalyses.set(context.tenantId, remaining);
    if (temporary) await rm(temporary, { recursive: true, force: true });
  }
}

async function loadApprovedAnalysis(
  runner: RunnerConfig,
  context: AuthorizedContext,
  request: GenerationJobCreateRequest,
): Promise<StoredAnalysisReview> {
  let review: StoredAnalysisReview;
  try {
    review = JSON.parse(
      await readFile(analysisReviewFile(runner, context, request.analysisDigest), "utf-8"),
    ) as StoredAnalysisReview;
  } catch {
    throw new GenerationRunnerError(409, "ANALYSIS_REVIEW_NOT_FOUND");
  }
  if (
    review.tenantId !== context.tenantId
    || review.actor !== context.actor
    || !safeEqual(review.requestDigest ?? "", request.analysisDigest)
    || !safeEqual(sha256Json(review.request), request.analysisDigest)
    || !safeEqual(sha256Json(review.intent), sha256Json(intentContract(request)))
  ) {
    throw new GenerationRunnerError(409, "ANALYSIS_REVIEW_MISMATCH");
  }
  if (Number.isNaN(Date.parse(review.expiresAt)) || Date.parse(review.expiresAt) <= Date.now()) {
    throw new GenerationRunnerError(409, "ANALYSIS_REVIEW_EXPIRED");
  }
  if (!Array.isArray(review.request.open_questions) || review.request.open_questions.length > 0) {
    throw new GenerationRunnerError(409, "OPEN_QUESTIONS_UNRESOLVED");
  }
  return review;
}

async function executeCommand(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
  stage: GenerationJob["stage"],
  args: string[],
): Promise<CommandResult> {
  await mkdir(confined(runner.root, "home"), { recursive: true, mode: 0o700 });
  job.stage = stage;
  if (stage === "analyze") {
    job.status = "ANALYZING";
    job.progress = 10;
  } else if (stage === "pipeline") {
    job.status = "GENERATING";
    job.progress = 35;
  }
  log(job, "system", `${stage} started`);
  await persist(runner, context, job);
  return new Promise((resolve, reject) => {
    const child = spawn(runner.uv, args, {
      cwd: runner.engineRoot,
      env: engineCommandEnvironment(runner),
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const key = jobKey(context, job.id);
    activeJobs.set(key, child);
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      log(job, "system", `${stage} exceeded its bounded execution time.`);
      terminate(child);
    }, stage === "analyze" ? 60_000 : 20 * 60_000);
    child.stdout?.on("data", (chunk: Buffer) => {
      stdout = `${stdout}${chunk.toString("utf-8")}`.slice(-200_000);
      log(job, "stdout", chunk.toString("utf-8"));
      void persist(runner, context, job);
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr = `${stderr}${chunk.toString("utf-8")}`.slice(-200_000);
      log(job, "stderr", chunk.toString("utf-8"));
      void persist(runner, context, job);
    });
    child.once("error", (error) => {
      clearTimeout(timeout);
      activeJobs.delete(key);
      reject(error);
    });
    child.once("close", (code, signal) => {
      clearTimeout(timeout);
      activeJobs.delete(key);
      const exitCode = timedOut ? 124 : code ?? (signal ? 128 : 1);
      log(job, "system", `${stage} finished with exit code ${exitCode}`);
      resolve({ exitCode, stdout: redact(stdout), stderr: redact(stderr) });
    });
  });
}

async function loadArtifacts(root: string): Promise<GenerationArtifact[]> {
  const workspace = confined(root, "workspace");
  const realWorkspace = await realpath(workspace);
  const manifestPath = confined(workspace, ".elmos", "generation-manifest.json");
  const manifest = JSON.parse(await readFile(manifestPath, "utf-8")) as {
    files?: Array<{ path?: unknown; sha256?: unknown; ownership?: unknown }>;
  };
  if (!Array.isArray(manifest.files) || manifest.files.length > 5_000) {
    throw new GenerationRunnerError(500, "GENERATION_MANIFEST_INVALID");
  }
  const artifacts: GenerationArtifact[] = [];
  let totalBytes = 0;
  for (const entry of manifest.files) {
    if (
      typeof entry.path !== "string"
      || typeof entry.sha256 !== "string"
      || !/^[a-f0-9]{64}$/.test(entry.sha256)
      || entry.ownership !== "managed"
    ) {
      throw new GenerationRunnerError(500, "GENERATION_MANIFEST_ENTRY_INVALID");
    }
    const artifactPath = confined(workspace, entry.path);
    const realArtifactPath = await realpath(artifactPath);
    if (
      realArtifactPath !== realWorkspace
      && !realArtifactPath.startsWith(`${realWorkspace}${path.sep}`)
    ) {
      throw new GenerationRunnerError(500, "GENERATION_ARTIFACT_OUTSIDE_WORKSPACE");
    }
    const info = await stat(realArtifactPath);
    totalBytes += info.size;
    if (!info.isFile() || totalBytes > 128 * 1024 * 1024) {
      throw new GenerationRunnerError(500, "GENERATION_ARTIFACT_INVALID");
    }
    if (!safeEqual(await sha256File(realArtifactPath), entry.sha256)) {
      throw new GenerationRunnerError(500, "GENERATION_ARTIFACT_DIGEST_MISMATCH");
    }
    artifacts.push({
      path: entry.path,
      sha256: entry.sha256,
      ownership: "managed",
    });
  }
  return artifacts;
}

async function runJob(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
): Promise<void> {
  const root = jobRoot(runner, context, job.id);
  const key = jobKey(context, job.id);
  let requeued = false;
  let queueLease: DurableJobLease | null = null;
  let leaseHeartbeat: NodeJS.Timeout | null = null;
  let metering: MeteredExecution | null = null;
  try {
    if (cancelledJobs.has(key)) return;
    try {
      queueLease = await DurableJobLease.acquire({
        configuration: durableQueueConfiguration(runner.root, "generation"),
        tenantId: context.tenantId,
        jobId: job.id,
        createdAt: job.createdAt,
        inputDigest: await sha256File(confined(root, "synthesis-request.json")),
      });
      leaseHeartbeat = setInterval(() => {
        void queueLease?.heartbeat().catch(() => {
          const child = activeJobs.get(key);
          if (child) terminate(child);
        });
      }, queueLease.heartbeatIntervalMs);
      leaseHeartbeat.unref();
    } catch (error) {
      if (error instanceof DurableLeaseError && error.retryable) {
        job.status = "QUEUED";
        job.stage = "queued";
        job.reason = error.code;
        log(job, "system", `Queue admission delayed: ${error.code}.`);
        await persist(runner, context, job);
        scheduledJobs.add(key);
        requeued = true;
        setTimeout(
          () => void runJob(runner, context, job),
          1_000 + Math.floor(Math.random() * 2_000),
        ).unref();
        return;
      }
      throw error;
    }
    metering = await beginMeteredExecution(`generation-${job.id}`);
    job.status = "VERIFYING";
    const pipeline = await executeCommand(
      runner,
      context,
      job,
      "pipeline",
      engineCliArguments([
        "pipeline",
        "--request",
        confined(root, "synthesis-request.json"),
        "--actor",
        context.actor,
        "--output",
        confined(root, "workspace"),
        "--evidence",
        confined(root, "verification.json"),
        "--archive",
        confined(root, "generated-project.zip"),
      ]),
    );
    if (pipeline.exitCode !== 0) {
      throw new Error(`PIPELINE_FAILED:${pipeline.stderr || pipeline.stdout}`);
    }
    if (cancelledJobs.has(key)) return;
    const result = JSON.parse(pipeline.stdout) as {
      status?: string;
      runtime_plan?: GenerationRuntime["plans"];
    };
    if (!["PASSED", "PARTIAL"].includes(result.status ?? "")) {
      throw new Error(`PIPELINE_RESULT_INVALID:${result.status ?? "MISSING"}`);
    }
    if (!Array.isArray(result.runtime_plan) || result.runtime_plan.length > targetIds.size) {
      throw new Error("RUNTIME_PLAN_INVALID");
    }
    job.resultStatus = result.status ?? "UNKNOWN";
    job.runtime.plans = result.runtime_plan;
    job.artifacts = await loadArtifacts(root);
    const archive = confined(root, "generated-project.zip");
    const archiveInfo = await stat(archive);
    if (!archiveInfo.isFile() || archiveInfo.size <= 0 || archiveInfo.size > 128 * 1024 * 1024) {
      throw new Error("ARCHIVE_INVALID");
    }
    job.artifactSha256 = await sha256File(archive);
    job.artifactSize = archiveInfo.size;
    job.stage = "metering";
    job.progress = 99;
    job.artifactReady = false;
    job.updatedAt = new Date().toISOString();
    await metering?.finish(true);
    metering = null;
    job.status = result.status === "PASSED" ? "COMPLETED" : "PARTIAL";
    job.stage = "complete";
    job.progress = 100;
    job.artifactReady = true;
    job.updatedAt = new Date().toISOString();
    log(job, "system", `Job completed with result ${job.resultStatus}.`);
  } catch (error) {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (meteringError) {
        error = meteringError;
      }
      metering = null;
    }
    if (!cancelledJobs.has(key)) {
      job.status = "BLOCKED";
      job.stage = "blocked";
      job.artifactReady = false;
      job.reason = redact(error instanceof Error ? error.message : "UNKNOWN_RUNNER_ERROR");
      log(job, "system", job.reason);
    }
  } finally {
    if (metering) {
      try {
        await metering.finish(false);
      } catch (error) {
        job.status = "BLOCKED";
        job.stage = "blocked";
        job.artifactReady = false;
        job.reason = redact(error instanceof Error ? error.message : "USAGE_SETTLEMENT_FAILED");
      }
    }
    if (cancelledJobs.has(key)) {
      job.status = "CANCELLED";
      job.stage = "cancelled";
      job.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
      job.artifactReady = false;
      job.runtime.plans = [];
      log(job, "system", `Cancelled by ${context.actor}.`);
    }
    if (leaseHeartbeat) clearInterval(leaseHeartbeat);
    if (queueLease) {
      const outcome = job.status === "COMPLETED" || job.status === "PARTIAL"
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
      }
    }
    await persist(runner, context, job);
    if (!requeued) {
      scheduledJobs.delete(key);
      cancelledJobs.delete(key);
    }
  }
}

export async function createJob(
  context: AuthorizedContext,
  request: GenerationJobCreateRequest,
): Promise<GenerationJob> {
  const runner = config();
  ensureMutationsAllowed(runner);
  const validated = validateCreate(request, context);
  const analysisReview = await loadApprovedAnalysis(runner, context, validated);
  const multiEntityProductionTargets = new Set<GenerationTargetId>(["java", "python"]);
  if (
    validated.persistence === "postgresql"
    && analysisReview.request.entities.length > 1
    && validated.targets.some((target) => !multiEntityProductionTargets.has(target))
  ) {
    throw new GenerationRunnerError(409, "PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY");
  }
  const id = randomUUID();
  const now = new Date().toISOString();
  const job: GenerationJob = {
    id,
    tenantId: context.tenantId,
    actor: context.actor,
    createdAt: now,
    updatedAt: now,
    status: "QUEUED",
    stage: "queued",
    progress: 0,
    resultStatus: "NOT_RUN",
    artifactReady: false,
    artifactSha256: undefined,
    artifactSize: undefined,
    artifacts: [],
    logs: [],
    runtime: {
      status: "STOPPED",
      plans: [],
      updatedAt: now,
    },
  };
  const root = jobRoot(runner, context, id);
  await mkdir(root, { recursive: true, mode: 0o700 });
  await atomicJson(confined(root, "project-intent.json"), {
    schema_version: "1.1.0",
    name: validated.name,
    namespace: validated.namespace,
    description: validated.description,
    entity: validated.entity,
    languages: validated.targets,
    project_kind: "api",
    persistence: validated.persistence,
    auth_mode: validated.authMode,
    business_rules: [],
    permissions: [],
    ...(validated.sources ? { requirement_sources: validated.sources } : {}),
    ...(validated.sourceBundleSha256
      ? { source_bundle_sha256: validated.sourceBundleSha256 }
      : {}),
    approval_context: {
      actor: context.actor,
      tenant_id: context.tenantId,
      explicitly_approved: true,
      analysis_digest: validated.analysisDigest,
      requested_at: now,
    },
  });
  await atomicJson(confined(root, "synthesis-request.json"), analysisReview.request);
  try {
    await rename(
      analysisReviewFile(runner, context, validated.analysisDigest),
      confined(root, "analysis-review.json"),
    );
  } catch {
    await rm(root, { recursive: true, force: true });
    throw new GenerationRunnerError(409, "ANALYSIS_REVIEW_ALREADY_CONSUMED");
  }
  log(job, "system", "Job accepted into the tenant-isolated local runner.");
  await persist(runner, context, job);
  scheduledJobs.add(jobKey(context, id));
  void runJob(runner, context, job);
  return job;
}

export async function getJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  return load(config(), context, jobId);
}

function terminate(child: ChildProcess): void {
  if (child.pid === undefined) return;
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }
}

export async function cancelJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  const runner = config();
  const job = await load(runner, context, jobId);
  if (["COMPLETED", "PARTIAL", "BLOCKED", "CANCELLED"].includes(job.status)) {
    return job;
  }
  const key = jobKey(context, jobId);
  cancelledJobs.add(key);
  const child = activeJobs.get(key);
  if (child) terminate(child);
  job.status = "CANCELLED";
  job.stage = "cancelled";
  job.reason = "CANCELLED_BY_AUTHORIZED_ACTOR";
  log(job, "system", `Cancelled by ${context.actor}.`);
  await persist(runner, context, job);
  return job;
}

export async function artifact(
  context: AuthorizedContext,
  jobId: string,
): Promise<{ path: string; size: number; sha256: string }> {
  const runner = config();
  const job = await load(runner, context, jobId);
  if (!job.artifactReady) throw new GenerationRunnerError(409, "ARTIFACT_NOT_READY");
  const root = await realpath(jobRoot(runner, context, jobId));
  const archive = await realpath(confined(root, "generated-project.zip"));
  if (archive !== root && !archive.startsWith(`${root}${path.sep}`)) {
    throw new GenerationRunnerError(409, "ARTIFACT_OUTSIDE_JOB_ROOT");
  }
  const info = await stat(archive);
  if (!info.isFile()) throw new GenerationRunnerError(404, "ARTIFACT_NOT_FOUND");
  const sha256 = await sha256File(archive);
  if (
    !job.artifactSha256
    || job.artifactSize !== info.size
    || !safeEqual(job.artifactSha256, sha256)
  ) {
    throw new GenerationRunnerError(409, "ARTIFACT_INTEGRITY_MISMATCH");
  }
  return { path: archive, size: info.size, sha256 };
}

async function confirmRuntimeHealth(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
  child: ChildProcess,
  key: string,
  port: number,
  expectedService: string,
): Promise<void> {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline && child.exitCode === null && activeRuntimes.get(key) === child) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`, {
        cache: "no-store",
        signal: AbortSignal.timeout(1_000),
      });
      const payload = await response.json() as { status?: unknown; service?: unknown };
      if (
        response.ok
        && payload.status === "UP"
        && payload.service === expectedService
      ) {
        if (child.exitCode !== null || activeRuntimes.get(key) !== child) return;
        job.runtime.status = "RUNNING";
        job.runtime.reason = undefined;
        job.runtime.updatedAt = new Date().toISOString();
        log(job, "system", `Runtime health probe passed on 127.0.0.1:${port}.`);
        await persist(runner, context, job);
        return;
      }
    } catch {
      // A bounded retry is expected while the selected runtime starts.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  if (activeRuntimes.get(key) !== child) return;
  job.runtime.status = "BLOCKED";
  job.runtime.reason = child.exitCode === null
    ? "RUNTIME_HEALTH_PROBE_TIMEOUT"
    : `RUNTIME_EXIT_${child.exitCode}`;
  job.runtime.updatedAt = new Date().toISOString();
  log(job, "system", job.runtime.reason);
  if (child.exitCode === null) terminate(child);
  await persist(runner, context, job);
}

async function reconcileRootlessRuntime(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
): Promise<void> {
  const language = job.runtime.language;
  if (!language) {
    job.runtime.status = "BLOCKED";
    job.runtime.reason = "ROOTLESS_RUNTIME_LANGUAGE_MISSING";
    job.runtime.updatedAt = new Date().toISOString();
    await persist(runner, context, job);
    return;
  }
  try {
    const state = await rootlessCommand(
      runner,
      [
        "status",
        "--engine",
        runner.containerEngine ?? "",
        "--language",
        language,
        "--job-id",
        job.id,
      ],
      30_000,
    );
    const status = state.status;
    if (status === "RUNNING" || status === "STARTING") {
      activeRootlessRuntimes.add(jobKey(context, job.id));
      job.runtime.status = status;
      job.runtime.reason = undefined;
    } else {
      activeRootlessRuntimes.delete(jobKey(context, job.id));
      job.runtime.status = "BLOCKED";
      job.runtime.reason = status === "MISSING"
        ? "ROOTLESS_RUNTIME_MISSING"
        : `ROOTLESS_RUNTIME_${String(status ?? "UNKNOWN")}`;
    }
  } catch (error) {
    activeRootlessRuntimes.delete(jobKey(context, job.id));
    job.runtime.status = "BLOCKED";
    job.runtime.reason = error instanceof GenerationRunnerError
      ? error.code
      : "ROOTLESS_RUNTIME_RECONCILIATION_FAILED";
  }
  job.runtime.updatedAt = new Date().toISOString();
  await persist(runner, context, job);
}

export async function startRuntime(
  context: AuthorizedContext,
  jobId: string,
  language: GenerationTargetId,
): Promise<GenerationJob> {
  const runner = config();
  ensureMutationsAllowed(runner);
  const job = await load(runner, context, jobId);
  if (!targetIds.has(language)) throw new GenerationRunnerError(400, "LANGUAGE_INVALID");
  if (!["COMPLETED", "PARTIAL"].includes(job.status)) {
    throw new GenerationRunnerError(409, "JOB_NOT_READY");
  }
  const currentArtifacts = await loadArtifacts(jobRoot(runner, context, jobId));
  if (!safeEqual(sha256Json(currentArtifacts), sha256Json(job.artifacts))) {
    throw new GenerationRunnerError(409, "WORKSPACE_INTEGRITY_MISMATCH");
  }
  const key = jobKey(context, jobId);
  if (activeRuntimes.has(key)) throw new GenerationRunnerError(409, "RUNTIME_ALREADY_RUNNING");
  const plan = job.runtime.plans.find((candidate) => candidate.language === language);
  if (!plan) throw new GenerationRunnerError(409, "RUNTIME_PLAN_NOT_AVAILABLE");
  const workspace = await realpath(confined(jobRoot(runner, context, jobId), "workspace"));
  const blueprint = JSON.parse(
    await readFile(confined(workspace, "requirements", "project-blueprint.json"), "utf-8"),
  ) as {
    project?: { name?: unknown };
    applications?: Array<{
      language?: unknown;
      storage?: unknown;
      auth_mode?: unknown;
    }>;
  };
  const expectedService = blueprint.project?.name;
  if (typeof expectedService !== "string" || !namePattern.test(expectedService)) {
    throw new GenerationRunnerError(409, "PROJECT_BLUEPRINT_NAME_INVALID");
  }
  if (runner.executor === "ROOTLESS_CONTAINER") {
    if (plan.port !== targetPorts[language]) {
      throw new GenerationRunnerError(400, "RUNTIME_PORT_PROFILE_MISMATCH");
    }
    const profile = blueprint.applications?.find(
      (candidate) => candidate.language === language,
    );
    if (
      !profile
      || !["in-memory", "postgresql"].includes(String(profile.storage))
      || !["none", "jwt", "oidc"].includes(String(profile.auth_mode))
    ) {
      throw new GenerationRunnerError(409, "RUNTIME_PROFILE_MISSING");
    }
    const result = await rootlessCommand(runner, [
      "start",
      "--engine",
      runner.containerEngine ?? "",
      "--workspace",
      workspace,
      "--language",
      language,
      "--port",
      String(plan.port),
      "--job-id",
      job.id,
      "--service",
      expectedService,
      "--state",
      confined(jobRoot(runner, context, jobId), "runtime-state"),
      "--persistence",
      String(profile.storage),
      "--auth-mode",
      String(profile.auth_mode),
      "--build-network",
      runner.buildNetwork,
    ]);
    job.runtime = {
      ...job.runtime,
      status: result.status === "RUNNING" ? "RUNNING" : "STARTING",
      executor: "ROOTLESS_CONTAINER",
      language,
      containerName: String(result.container_name ?? ""),
      pid: undefined,
      reason: undefined,
      updatedAt: new Date().toISOString(),
    };
    activeRootlessRuntimes.add(key);
    log(
      job,
      "system",
      "Rootless runtime passed its loopback identity probe with a read-only filesystem, internal-only runtime network, dropped capabilities, and bounded resources.",
    );
    await persist(runner, context, job);
    return job;
  }
  const cwd = await realpath(plan.cwd);
  if (cwd !== workspace && !cwd.startsWith(`${workspace}${path.sep}`)) {
    throw new GenerationRunnerError(400, "RUNTIME_CWD_OUTSIDE_WORKSPACE");
  }
  if (
    plan.port !== targetPorts[language]
    || !Array.isArray(plan.command)
    || plan.command.length === 0
    || plan.command.length > 32
    || !plan.command.every(
      (argument) =>
        typeof argument === "string"
        && argument.length > 0
        && argument.length <= 2_000
        && !/[\0\r\n]/.test(argument),
    )
  ) {
    throw new GenerationRunnerError(400, "RUNTIME_COMMAND_INVALID");
  }
  if (!runtimeCommandShapeValid(language, plan.command, plan.port)) {
    throw new GenerationRunnerError(400, "RUNTIME_COMMAND_SHAPE_INVALID");
  }
  const allowedExecutable = new Set([
    "java",
    "uv",
    "dotnet",
    "pnpm",
    "go",
    "gradle",
    "php",
    "cargo",
  ]);
  const executableName = path.basename(plan.command[0]);
  if (!allowedExecutable.has(executableName)) {
    throw new GenerationRunnerError(400, "RUNTIME_EXECUTABLE_NOT_ALLOWED");
  }
  for (const argument of plan.command.slice(1)) {
    if (path.isAbsolute(argument)) {
      const realArgument = await realpath(argument);
      if (realArgument !== workspace && !realArgument.startsWith(`${workspace}${path.sep}`)) {
        throw new GenerationRunnerError(400, "RUNTIME_ARGUMENT_OUTSIDE_WORKSPACE");
      }
    }
  }
  if (
    !plan.environment
    || typeof plan.environment !== "object"
    || Array.isArray(plan.environment)
  ) {
    throw new GenerationRunnerError(400, "RUNTIME_ENVIRONMENT_INVALID");
  }
  const environmentEntries = Object.entries(plan.environment);
  if (
    environmentEntries.length < 1
    || environmentEntries.length > 3
    || !environmentEntries.every(
      ([keyName, value]) =>
        ["PORT", "ASPNETCORE_URLS", "HOST", "SERVER_ADDRESS", "ELMOS_RUNTIME_STATE_DIR"].includes(keyName)
        && typeof value === "string"
        && value.length <= 2_000
        && !/[\0\r\n]/.test(value),
    )
  ) {
    throw new GenerationRunnerError(400, "RUNTIME_ENVIRONMENT_INVALID");
  }
  const runtimeStateDirectory = plan.environment.ELMOS_RUNTIME_STATE_DIR;
  if (runtimeStateDirectory !== undefined) {
    const normalizedStateDirectory = path.resolve(runtimeStateDirectory);
    if (
      language !== "python"
      || !path.isAbsolute(runtimeStateDirectory)
      || normalizedStateDirectory === cwd
      || !normalizedStateDirectory.startsWith(`${cwd}${path.sep}`)
    ) {
      throw new GenerationRunnerError(400, "RUNTIME_STATE_DIRECTORY_INVALID");
    }
  }
  const expectedPortValue = String(plan.port);
  const expectedLoopbackKey: Partial<Record<GenerationTargetId, "HOST" | "SERVER_ADDRESS">> = {
    java: "SERVER_ADDRESS",
    python: "HOST",
    typescript: "HOST",
    go: "HOST",
    kotlin: "HOST",
    rust: "HOST",
  };
  const loopbackKey = expectedLoopbackKey[language];
  const environmentValid =
    language === "csharp"
      ? (
        environmentEntries.length === 1
        && plan.environment.ASPNETCORE_URLS === `http://127.0.0.1:${expectedPortValue}`
      )
      : (
        plan.environment.PORT === expectedPortValue
        && (
          language === "php"
            ? environmentEntries.length === 1
            : (
              environmentEntries.length === (runtimeStateDirectory === undefined ? 2 : 3)
              && loopbackKey !== undefined
              && plan.environment[loopbackKey] === "127.0.0.1"
            )
        )
      );
  if (!environmentValid) {
    throw new GenerationRunnerError(400, "RUNTIME_PORT_BINDING_INVALID");
  }
  const child = spawn(plan.command[0], plan.command.slice(1), {
    cwd,
    env: { ...commandEnvironment(runner), ...plan.environment },
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  activeRuntimes.set(key, child);
  runtimeJobs.set(key, job);
  job.runtime = {
    ...job.runtime,
    status: "STARTING",
    executor: "HOST_DEVELOPMENT",
    language,
    pid: child.pid,
    reason: undefined,
    updatedAt: new Date().toISOString(),
  };
  child.stdout?.on("data", (chunk: Buffer) => {
    if (activeRuntimes.get(key) !== child || runtimeJobs.get(key) !== job) return;
    log(job, "runtime", chunk.toString("utf-8"));
    void persist(runner, context, job);
  });
  child.stderr?.on("data", (chunk: Buffer) => {
    if (activeRuntimes.get(key) !== child || runtimeJobs.get(key) !== job) return;
    log(job, "runtime", chunk.toString("utf-8"));
    void persist(runner, context, job);
  });
  child.once("spawn", () => {
    void confirmRuntimeHealth(
      runner,
      context,
      job,
      child,
      key,
      plan.port,
      expectedService,
    );
  });
  child.once("error", (error) => {
    if (runtimeJobs.get(key) !== job) return;
    activeRuntimes.delete(key);
    runtimeJobs.delete(key);
    job.runtime.status = "BLOCKED";
    job.runtime.reason = `RUNTIME_SPAWN_FAILED:${redact(error.message)}`;
    job.runtime.pid = undefined;
    job.runtime.updatedAt = new Date().toISOString();
    void persist(runner, context, job);
  });
  child.once("close", (code) => {
    if (runtimeJobs.get(key) !== job) return;
    activeRuntimes.delete(key);
    runtimeJobs.delete(key);
    const intentionallyStopped = intentionallyStoppedRuntimes.delete(child);
    const healthBlocked = job.runtime.status === "BLOCKED"
      && job.runtime.reason?.startsWith("RUNTIME_HEALTH_PROBE");
    if (intentionallyStopped) {
      job.runtime.status = "STOPPED";
      job.runtime.reason = "STOPPED_BY_AUTHORIZED_ACTOR";
    } else if (!healthBlocked) {
      job.runtime.status = code === 0 ? "STOPPED" : "BLOCKED";
      job.runtime.reason = code === 0 ? undefined : `RUNTIME_EXIT_${code ?? "UNKNOWN"}`;
    }
    job.runtime.pid = undefined;
    job.runtime.updatedAt = new Date().toISOString();
    void persist(runner, context, job);
  });
  await persist(runner, context, job);
  return job;
}

export async function stopRuntime(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  const runner = config();
  const job = await load(runner, context, jobId);
  if (job.runtime.executor === "ROOTLESS_CONTAINER" && job.runtime.language) {
    await rootlessCommand(
      runner,
      [
        "stop",
        "--engine",
        runner.containerEngine ?? "",
        "--language",
        job.runtime.language,
        "--job-id",
        job.id,
      ],
      60_000,
    );
    job.runtime.status = "STOPPED";
    activeRootlessRuntimes.delete(jobKey(context, job.id));
    job.runtime.pid = undefined;
    job.runtime.reason = "STOPPED_BY_AUTHORIZED_ACTOR";
    job.runtime.updatedAt = new Date().toISOString();
    log(job, "system", `Rootless runtime stopped by ${context.actor}.`);
    await persist(runner, context, job);
    return job;
  }
  const key = jobKey(context, jobId);
  const child = activeRuntimes.get(key);
  const runtimeJob = runtimeJobs.get(key) ?? job;
  if (child) {
    intentionallyStoppedRuntimes.add(child);
    runtimeJob.runtime.status = "STOPPED";
    runtimeJob.runtime.pid = undefined;
    runtimeJob.runtime.reason = "STOPPED_BY_AUTHORIZED_ACTOR";
    runtimeJob.runtime.updatedAt = new Date().toISOString();
    log(runtimeJob, "system", `Runtime stopped by ${context.actor}.`);
    activeRuntimes.delete(key);
    terminate(child);
  } else {
    runtimeJob.runtime.status = "STOPPED";
    runtimeJob.runtime.pid = undefined;
    runtimeJob.runtime.reason = "STOPPED_BY_AUTHORIZED_ACTOR";
    runtimeJob.runtime.updatedAt = new Date().toISOString();
    log(runtimeJob, "system", `Runtime stopped by ${context.actor}.`);
  }
  await persist(runner, context, runtimeJob);
  return runtimeJob;
}

async function reconcilePersistentQueue(
  runner: RunnerConfig,
  context: AuthorizedContext,
): Promise<void> {
  const jobsRoot = confined(runner.root, "tenants", context.tenantId, "jobs");
  let entries;
  try {
    entries = await readdir(jobsRoot, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
    throw error;
  }
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    if (
      !entry.isDirectory()
      || !jobIdPattern.test(entry.name)
      || activeJobs.size + scheduledJobs.size >= 2
    ) continue;
    await load(runner, context, entry.name);
  }
}

export function capability(): {
  enabled: boolean;
  persistence: "FILESYSTEM_ATOMIC";
  auth: "BEARER_TENANT_BOUND";
  isolation: "ROOTLESS_CONTAINER" | "HOST_DEVELOPMENT" | "NOT_CONFIGURED";
  recovery: "PERSISTENT_RECONCILIATION";
} {
  try {
    const runner = config();
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

export async function health(): Promise<GenerationRunnerHealth> {
  const checkedAt = new Date().toISOString();
  const base = {
    persistence: "FILESYSTEM_ATOMIC" as const,
    auth: "BEARER_TENANT_BOUND" as const,
    recovery: "PERSISTENT_RECONCILIATION" as const,
    activeJobs: activeJobs.size,
    activeRuntimes: activeRuntimes.size + activeRootlessRuntimes.size,
    activeAnalyses: [...activeAnalyses.values()].reduce((sum, value) => sum + value, 0),
    checkedAt,
  };
  if (process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true") {
    return {
      ...base,
      status: "DISABLED",
      storage: "NOT_RUN",
      isolation: "NOT_CONFIGURED",
    };
  }
  try {
    const runner = config();
    await mkdir(runner.root, { recursive: true, mode: 0o700 });
    ensureMutationsAllowed(runner);
    await access(runner.root, fsConstants.R_OK | fsConstants.W_OK | fsConstants.X_OK);
    const maintenanceContext = {
      tenantId: process.env.ELMOS_LOCAL_RUNNER_TENANT_ID ?? "",
      actor: process.env.ELMOS_LOCAL_RUNNER_ACTOR_ID ?? "",
    };
    if (
      tenantPattern.test(maintenanceContext.tenantId)
      && actorPattern.test(maintenanceContext.actor)
    ) {
      await reconcilePersistentQueue(runner, maintenanceContext);
    }
    if (runner.executor === "ROOTLESS_CONTAINER") {
      await rootlessCommand(
        runner,
        ["preflight", "--engine", runner.containerEngine ?? ""],
        30_000,
      );
    }
    return {
      ...base,
      status: "READY",
      storage: "READ_WRITE",
      isolation: runner.executor,
    };
  } catch (error) {
    return {
      ...base,
      status: "BLOCKED",
      storage: "BLOCKED",
      isolation: "NOT_CONFIGURED",
      reason: error instanceof GenerationRunnerError
        ? error.code
        : "LOCAL_RUNNER_HEALTH_CHECK_FAILED",
    };
  }
}
