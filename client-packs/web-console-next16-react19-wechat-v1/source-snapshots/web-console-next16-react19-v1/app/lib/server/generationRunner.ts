import { createHash, randomUUID, timingSafeEqual } from "node:crypto";
import { spawn, type ChildProcess } from "node:child_process";
import {
  constants as fsConstants,
  createReadStream,
  createWriteStream,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  statSync,
  type Stats,
} from "node:fs";
import {
  access,
  mkdir,
  mkdtemp,
  lstat,
  open,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
  type FileHandle,
} from "node:fs/promises";
import path from "node:path";
import { pipeline as streamPipeline } from "node:stream/promises";
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
import { validateVerifiedInsightProjection } from "./generationInsights";
import {
  accountCookieNames,
  AccountSessionError,
  accountSessionFromRequest,
  unsafeCookieValue,
  type AccountPermission,
} from "./accountSession";
import type { NextRequest } from "next/server";
import type {
  GenerationAnalysis,
  GenerationAnalyzeRequest,
  GenerationArtifact,
  GenerationGitHubPublication,
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
  activeRootlessRuntimes: Set<string>;
  previewProcesses: Set<ChildProcess>;
  activeAnalyses: Map<string, number>;
  scheduledJobs: Set<string>;
  cancelledJobs: Set<string>;
  stoppedRuntimes: Set<string>;
  expiredRuntimes: Set<string>;
  runtimeLeaseTimers: Map<string, NodeJS.Timeout>;
  runtimeOperationTails: Map<string, Promise<void>>;
  exitCleanupRegistered: boolean;
};

const globalRunnerState = globalThis as typeof globalThis & {
  __elmosGenerationRunnerState?: GenerationRunnerProcessState;
};
const processState = globalRunnerState.__elmosGenerationRunnerState ??= {
  activeJobs: new Map<string, ChildProcess>(),
  activeRuntimes: new Map<string, ChildProcess>(),
  activeRootlessRuntimes: new Set<string>(),
  previewProcesses: new Set<ChildProcess>(),
  activeAnalyses: new Map<string, number>(),
  scheduledJobs: new Set<string>(),
  cancelledJobs: new Set<string>(),
  stoppedRuntimes: new Set<string>(),
  expiredRuntimes: new Set<string>(),
  runtimeLeaseTimers: new Map<string, NodeJS.Timeout>(),
  runtimeOperationTails: new Map<string, Promise<void>>(),
  exitCleanupRegistered: false,
};
// Next.js development HMR preserves this object across module revisions. Hydrate
// every field independently so a newly added registry cannot be undefined in an
// already-running process; production starts still take the initializer above.
processState.activeJobs ??= new Map<string, ChildProcess>();
processState.activeRuntimes ??= new Map<string, ChildProcess>();
processState.activeRootlessRuntimes ??= new Set<string>();
processState.activeAnalyses ??= new Map<string, number>();
processState.scheduledJobs ??= new Set<string>();
processState.cancelledJobs ??= new Set<string>();
processState.stoppedRuntimes ??= new Set<string>();
processState.expiredRuntimes ??= new Set<string>();
processState.runtimeLeaseTimers ??= new Map<string, NodeJS.Timeout>();
processState.runtimeOperationTails ??= new Map<string, Promise<void>>();
processState.exitCleanupRegistered ??= false;
const {
  activeJobs,
  activeRuntimes,
  activeRootlessRuntimes,
  previewProcesses,
  activeAnalyses,
  scheduledJobs,
  cancelledJobs,
  stoppedRuntimes,
  expiredRuntimes,
  runtimeLeaseTimers,
  runtimeOperationTails,
} = processState;
if (!processState.exitCleanupRegistered) {
  const terminateAll = () => {
    for (const timer of runtimeLeaseTimers.values()) clearTimeout(timer);
    runtimeLeaseTimers.clear();
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
const defaultRuntimeLeaseMilliseconds = 10 * 60_000;
const githubIdempotencyKeyPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function configuredRuntimeLeaseMilliseconds(): number {
  if (
    process.env.NODE_ENV === "production"
    || process.env.ELMOS_ALLOW_TEST_RUNTIME_TTL !== "true"
  ) return defaultRuntimeLeaseMilliseconds;
  const value = Number.parseInt(process.env.ELMOS_TEST_RUNTIME_TTL_MS ?? "", 10);
  return Number.isInteger(value) && value >= 1_000 && value <= defaultRuntimeLeaseMilliseconds
    ? value
    : defaultRuntimeLeaseMilliseconds;
}

function safeExternalHttpsUrl(value: string | undefined): boolean {
  if (!value) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:"
      && !parsed.username
      && !parsed.password
      && !parsed.hash;
  } catch {
    return false;
  }
}

type RunnerConfig = {
  root: string;
  repositoryRoot: string;
  engineRoot: string;
  engineHome: string;
  engineXdgRuntimeDir?: string;
  dockerUnixSocket?: string;
  engineContextDigest?: string;
  uv: string;
  uvCache: string;
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

export type AuthorizedContext = {
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
  authorizedActors?: string[];
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

function configuredEngineDirectory(raw: string | undefined): string | undefined {
  const value = raw?.trim();
  if (!value) return undefined;
  try {
    const info = lstatSync(value);
    if (
      !path.isAbsolute(value)
      || path.resolve(value) !== value
      || realpathSync(value) !== value
      || info.isSymbolicLink()
      || !info.isDirectory()
      || (info.mode & 0o077) !== 0
      || (typeof process.getuid === "function" && info.uid !== process.getuid())
    ) throw new Error("unsafe rootless engine runtime directory");
  } catch {
    throw new GenerationRunnerError(503, "ROOTLESS_ENGINE_XDG_RUNTIME_DIR_INVALID");
  }
  return value;
}

function configuredDockerUnixSocket(raw: string | undefined): string | undefined {
  const value = raw?.trim();
  if (!value) return undefined;
  try {
    const info = lstatSync(value);
    if (
      !path.isAbsolute(value)
      || path.resolve(value) !== value
      || realpathSync(value) !== value
      || info.isSymbolicLink()
      || !info.isSocket()
      || (info.mode & 0o002) !== 0
      || (typeof process.getuid === "function" && info.uid !== process.getuid())
    ) throw new Error("unsafe rootless Docker socket");
  } catch {
    throw new GenerationRunnerError(503, "ROOTLESS_DOCKER_UNIX_SOCKET_INVALID");
  }
  return value;
}

function configuredRootlessEngine(raw: string | undefined): string {
  const value = raw?.trim();
  try {
    if (!value) throw new Error("missing rootless engine");
    const info = lstatSync(value);
    if (
      !path.isAbsolute(value)
      || path.resolve(value) !== value
      || realpathSync(value) !== value
      || info.isSymbolicLink()
      || !info.isFile()
      || !["docker", "podman"].includes(path.basename(value))
    ) throw new Error("unsafe rootless engine");
  } catch {
    throw new GenerationRunnerError(503, "ROOTLESS_CONTAINER_ENGINE_NOT_CONFIGURED");
  }
  return value;
}

function canonicalProspectivePath(requested: string): string {
  let cursor = requested;
  const missing: string[] = [];
  while (!existsSync(cursor)) {
    const parent = path.dirname(cursor);
    if (parent === cursor) throw new Error("runner root has no existing ancestor");
    missing.unshift(path.basename(cursor));
    cursor = parent;
  }
  return path.resolve(realpathSync(cursor), ...missing);
}

function sameOrWithin(candidate: string, parent: string): boolean {
  return candidate === parent || candidate.startsWith(`${parent}${path.sep}`);
}

function configuredRunnerRoot(raw: string, repositoryRoot: string): string {
  const requested = path.resolve(raw);
  if (requested === path.parse(requested).root) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_ROOT_UNSAFE");
  }
  try {
    const prospective = canonicalProspectivePath(requested);
    if (
      sameOrWithin(repositoryRoot, prospective)
      || sameOrWithin(prospective, repositoryRoot)
    ) throw new Error("runner root overlaps repository");
    mkdirSync(requested, { recursive: true, mode: 0o700 });
    const info = lstatSync(requested);
    const resolved = realpathSync(requested);
    if (
      info.isSymbolicLink()
      || !info.isDirectory()
      || (info.mode & 0o077) !== 0
      || (typeof process.getuid === "function" && info.uid !== process.getuid())
      || sameOrWithin(repositoryRoot, resolved)
      || sameOrWithin(resolved, repositoryRoot)
    ) throw new Error("unsafe runner root");
    return resolved;
  } catch {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_ROOT_UNSAFE");
  }
}

function configuredEngineHome(root: string): string {
  const requested = path.join(root, "home");
  try {
    mkdirSync(requested, { recursive: true, mode: 0o700 });
    const info = lstatSync(requested);
    if (
      info.isSymbolicLink()
      || !info.isDirectory()
      || (info.mode & 0o077) !== 0
      || (typeof process.getuid === "function" && info.uid !== process.getuid())
    ) throw new Error("unsafe runner engine home");
    return realpathSync(requested);
  } catch {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_HOME_INVALID");
  }
}

function rootlessEngineContextDigest(
  engine: string,
  home: string,
  xdgRuntimeDirectory: string | undefined,
  dockerUnixSocket: string | undefined,
): string {
  const digest = createHash("sha256");
  for (const value of [engine, home, xdgRuntimeDirectory ?? "", dockerUnixSocket ?? ""]) {
    digest.update(value, "utf-8");
    digest.update("\0", "utf-8");
  }
  return digest.digest("hex");
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
  const configuredEngineXdgRuntimeDir = process.env.ELMOS_LOCAL_RUNNER_ENGINE_XDG_RUNTIME_DIR;
  const configuredDockerSocket = process.env.ELMOS_LOCAL_RUNNER_DOCKER_UNIX_SOCKET;
  const configuredUvCache = process.env.ELMOS_PROJECT_SYNTHESIS_UV_CACHE?.trim();
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
  const resolvedRepositoryRoot = realpathSync(repositoryRoot);
  const resolvedRoot = configuredRunnerRoot(root, resolvedRepositoryRoot);
  const engineHome = configuredEngineHome(resolvedRoot);
  const uvCache = configuredUvCache
    ? path.resolve(configuredUvCache)
    : path.resolve(resolvedRoot, "dependency-cache", "uv");
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
    (configuredUvCache && !path.isAbsolute(configuredUvCache))
    || uvCache === path.parse(uvCache).root
    || uvCache === resolvedRepositoryRoot
    || uvCache.startsWith(`${resolvedRepositoryRoot}${path.sep}`)
    || (
      existsSync(uvCache)
      && (lstatSync(uvCache).isSymbolicLink() || !statSync(uvCache).isDirectory())
    )
  ) {
    throw new GenerationRunnerError(503, "PROJECT_SYNTHESIS_UV_CACHE_UNSAFE");
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
  let resolvedContainerEngine: string | undefined;
  let engineXdgRuntimeDir: string | undefined;
  let dockerUnixSocket: string | undefined;
  let engineContextDigest: string | undefined;
  if (executor === "ROOTLESS_CONTAINER") {
    resolvedContainerEngine = configuredRootlessEngine(containerEngine);
    engineXdgRuntimeDir = configuredEngineDirectory(configuredEngineXdgRuntimeDir);
    dockerUnixSocket = configuredDockerUnixSocket(configuredDockerSocket);
    if (path.basename(resolvedContainerEngine) === "docker" && !dockerUnixSocket) {
      throw new GenerationRunnerError(503, "ROOTLESS_DOCKER_UNIX_SOCKET_NOT_CONFIGURED");
    }
    if (path.basename(resolvedContainerEngine) !== "docker" && dockerUnixSocket) {
      throw new GenerationRunnerError(503, "ROOTLESS_DOCKER_UNIX_SOCKET_ENGINE_MISMATCH");
    }
    engineContextDigest = rootlessEngineContextDigest(
      resolvedContainerEngine,
      engineHome,
      engineXdgRuntimeDir,
      dockerUnixSocket,
    );
  }
  return {
    root: resolvedRoot,
    repositoryRoot: resolvedRepositoryRoot,
    engineRoot,
    engineHome,
    engineXdgRuntimeDir,
    dockerUnixSocket,
    engineContextDigest,
    uv,
    uvCache,
    executor: executor as RunnerConfig["executor"],
    containerEngine: resolvedContainerEngine,
    buildNetwork,
    rootlessTool,
  };
}

async function assertProductionRuntimeReaper(runner: RunnerConfig): Promise<void> {
  if (process.env.NODE_ENV !== "production" || runner.executor !== "ROOTLESS_CONTAINER") return;
  const heartbeat = confined(runner.root, ".runtime-reaper-heartbeat.json");
  try {
    const info = await lstat(heartbeat);
    if (
      info.isSymbolicLink()
      || !info.isFile()
      || info.size < 2
      || info.size > 64 * 1024
      || (info.mode & 0o077) !== 0
    ) throw new Error("RUNTIME_REAPER_HEARTBEAT_UNSAFE");
    const value = JSON.parse(await readFile(heartbeat, "utf-8")) as Record<string, unknown>;
    const observedAt = Date.parse(String(value.observed_at ?? ""));
    const age = Date.now() - observedAt;
    if (
      value.schema_version !== "elmos.generation-runtime-reaper-heartbeat.v2"
      || value.engine_context_sha256 !== runner.engineContextDigest
      || !Number.isSafeInteger(value.pid)
      || Number(value.pid) < 1
      || !["REAPER_IDLE", "REAPER_SWEEP_COMPLETE"].includes(String(value.sweep_status ?? ""))
      || !Number.isFinite(observedAt)
      || age < -5_000
      || age > 10_000
    ) throw new Error("RUNTIME_REAPER_HEARTBEAT_INVALID");
  } catch {
    throw new GenerationRunnerError(503, "RUNTIME_REAPER_NOT_READY");
  }
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

async function withRuntimeOperation<T>(key: string, operation: () => Promise<T>): Promise<T> {
  const previous = runtimeOperationTails.get(key) ?? Promise.resolve();
  let release = (): void => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const tail = previous.then(() => gate);
  runtimeOperationTails.set(key, tail);
  await previous;
  try {
    return await operation();
  } finally {
    release();
    if (runtimeOperationTails.get(key) === tail) runtimeOperationTails.delete(key);
  }
}

async function withDurableRuntimeOperation<T>(
  runner: RunnerConfig,
  context: AuthorizedContext,
  jobId: string,
  operation: () => Promise<T>,
  line = "generation-runtime-operation",
): Promise<T> {
  const configuration = {
    ...durableQueueConfiguration(runner.root, line),
    globalCapacity: 1_000,
    tenantCapacity: 1_000,
    queueTtlMs: 60 * 60_000,
    leaseTtlMs: 120_000,
  };
  const deadline = Date.now() + 35_000;
  let lease: DurableJobLease | undefined;
  while (!lease && Date.now() < deadline) {
    try {
      lease = await DurableJobLease.acquire({
        configuration,
        tenantId: context.tenantId,
        jobId,
        createdAt: new Date().toISOString(),
        inputDigest: createHash("sha256")
          .update(`${context.tenantId}:${jobId}:runtime-operation`)
          .digest("hex"),
      });
    } catch (error) {
      if (
        error instanceof DurableLeaseError
        && error.retryable
        && ["QUEUE_JOB_ALREADY_LEASED", "QUEUE_CONTROL_LOCK_UNAVAILABLE"].includes(error.code)
      ) {
        await new Promise((resolve) => setTimeout(resolve, 100));
        continue;
      }
      throw error;
    }
  }
  if (!lease) throw new GenerationRunnerError(409, "RUNTIME_OPERATION_IN_PROGRESS");
  let outcome: "SUCCEEDED" | "FAILED" = "FAILED";
  let heartbeatFailure: unknown;
  const heartbeat = setInterval(() => {
    void lease?.heartbeat().catch((error: unknown) => {
      heartbeatFailure = error;
    });
  }, lease.heartbeatIntervalMs);
  heartbeat.unref();
  try {
    const result = await operation();
    if (heartbeatFailure) throw new GenerationRunnerError(409, "RUNTIME_OPERATION_LEASE_LOST");
    outcome = "SUCCEEDED";
    return result;
  } finally {
    clearInterval(heartbeat);
    await lease.release(outcome);
  }
}

export async function withGenerationPublicationOperation<T>(
  context: AuthorizedContext,
  jobId: string,
  operation: () => Promise<T>,
): Promise<T> {
  if (!jobIdPattern.test(jobId)) throw new GenerationRunnerError(400, "JOB_ID_INVALID");
  const runner = config();
  return withDurableRuntimeOperation(
    runner,
    context,
    jobId,
    async () => {
      ensureMutationsAllowed(runner);
      return operation();
    },
    "generation-github-publication",
  );
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
  const actorDigest = createHash("sha256").update(context.actor).digest("hex");
  return confined(
    runner.root,
    "tenants",
    context.tenantId,
    "analysis-reviews",
    `${actorDigest}-${requestDigest}.json`,
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

function tenantMaintenanceJobId(tenantId: string, scope: string): string {
  const digest = createHash("sha256").update(`${scope}:${tenantId}`).digest("hex");
  return `${digest.slice(0, 8)}-${digest.slice(8, 12)}-4${digest.slice(13, 16)}`
    + `-8${digest.slice(17, 20)}-${digest.slice(20, 32)}`;
}

async function activeSourceBundles(
  runner: RunnerConfig,
  context: AuthorizedContext,
  sourceRoot: string,
): Promise<Map<string, StoredSourceBundle>> {
  const quarantineRoot = confined(
    runner.root,
    "tenants",
    context.tenantId,
    "storage-quarantine",
    "source-bundles",
  );
  await mkdir(quarantineRoot, { recursive: true, mode: 0o700 });
  const quarantineEntries = await readdir(quarantineRoot, { withFileTypes: true });
  if (
    quarantineEntries.some((entry) => entry.isSymbolicLink() || !entry.isFile())
    || quarantineEntries.length >= 100
  ) throw new GenerationRunnerError(507, "SOURCE_BUNDLE_QUARANTINE_LIMIT");
  const active = new Map<string, StoredSourceBundle>();
  const entries = await readdir(sourceRoot, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isSymbolicLink()) {
      throw new GenerationRunnerError(409, "SOURCE_BUNDLE_STORAGE_SYMLINK_FORBIDDEN");
    }
    if (!entry.isFile() || !/^[0-9a-f]{64}\.json$/.test(entry.name)) continue;
    const source = confined(sourceRoot, entry.name);
    const digest = entry.name.slice(0, -5);
    let stored: StoredSourceBundle;
    try {
      const info = await stat(source);
      if (info.size < 2 || info.size > 1024 * 1024) throw new Error("SOURCE_BUNDLE_DOCUMENT_SIZE_INVALID");
      stored = JSON.parse(await readFile(source, "utf-8")) as StoredSourceBundle;
      const authorizedActors = stored.authorizedActors ?? [stored.actor];
      if (
        !safeEqual(stored.tenantId ?? "", context.tenantId)
        || !actorPattern.test(stored.actor ?? "")
        || !Array.isArray(authorizedActors)
        || authorizedActors.length < 1
        || authorizedActors.length > 64
        || !authorizedActors.every((actor) => actorPattern.test(actor))
        || stored.bundle?.status !== "READY_FOR_REVIEW"
        || !safeEqual(stored.bundle.bundleSha256 ?? "", digest)
        || !safeEqual(
          sha256Json({ description: stored.bundle.combinedText, sources: stored.bundle.sources }),
          digest,
        )
        || !Number.isFinite(Date.parse(stored.createdAt))
        || !Number.isFinite(Date.parse(stored.expiresAt))
      ) throw new Error("SOURCE_BUNDLE_DOCUMENT_INVALID");
    } catch {
      await rename(source, confined(quarantineRoot, `invalid-${digest}-${randomUUID()}.json`));
      continue;
    }
    if (Date.parse(stored.expiresAt) <= Date.now()) {
      await rm(source, { force: true });
      continue;
    }
    active.set(entry.name, stored);
  }
  return active;
}

async function activeAnalysisReviews(
  runner: RunnerConfig,
  context: AuthorizedContext,
  reviewRoot: string,
): Promise<Set<string>> {
  const quarantineRoot = confined(
    runner.root,
    "tenants",
    context.tenantId,
    "storage-quarantine",
    "analysis-reviews",
  );
  await mkdir(quarantineRoot, { recursive: true, mode: 0o700 });
  const quarantineEntries = await readdir(quarantineRoot, { withFileTypes: true });
  if (
    quarantineEntries.some((entry) => entry.isSymbolicLink() || !entry.isFile())
    || quarantineEntries.length >= 100
  ) throw new GenerationRunnerError(507, "ANALYSIS_REVIEW_QUARANTINE_LIMIT");
  const active = new Set<string>();
  for (const entry of await readdir(reviewRoot, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) {
      throw new GenerationRunnerError(409, "ANALYSIS_REVIEW_STORAGE_SYMLINK_FORBIDDEN");
    }
    if (!entry.isFile() || !/^[0-9a-f]{64}-[0-9a-f]{64}\.json$/.test(entry.name)) continue;
    const source = confined(reviewRoot, entry.name);
    const [actorDigest, digestWithSuffix] = entry.name.split("-", 2);
    const requestDigest = digestWithSuffix.slice(0, -5);
    let review: StoredAnalysisReview;
    try {
      const info = await stat(source);
      if (info.size < 2 || info.size > 4 * 1024 * 1024) {
        throw new Error("ANALYSIS_REVIEW_DOCUMENT_SIZE_INVALID");
      }
      review = JSON.parse(await readFile(source, "utf-8")) as StoredAnalysisReview;
      if (
        !safeEqual(review.tenantId ?? "", context.tenantId)
        || !actorPattern.test(review.actor ?? "")
        || !safeEqual(createHash("sha256").update(review.actor).digest("hex"), actorDigest)
        || !safeEqual(review.requestDigest ?? "", requestDigest)
        || !safeEqual(sha256Json(review.request), requestDigest)
        || !Number.isFinite(Date.parse(review.createdAt))
        || !Number.isFinite(Date.parse(review.expiresAt))
      ) throw new Error("ANALYSIS_REVIEW_DOCUMENT_INVALID");
    } catch {
      await rename(source, confined(quarantineRoot, `invalid-${requestDigest}-${randomUUID()}.json`));
      continue;
    }
    if (Date.parse(review.expiresAt) <= Date.now()) {
      await rm(source, { force: true });
      continue;
    }
    active.add(entry.name);
  }
  return active;
}

async function storeAnalysisReview(
  runner: RunnerConfig,
  context: AuthorizedContext,
  review: StoredAnalysisReview,
): Promise<void> {
  const reviewRoot = confined(runner.root, "tenants", context.tenantId, "analysis-reviews");
  await mkdir(reviewRoot, { recursive: true, mode: 0o700 });
  await withDurableRuntimeOperation(
    runner,
    context,
    tenantMaintenanceJobId(context.tenantId, "analysis-reviews"),
    async () => {
      ensureMutationsAllowed(runner);
      const active = await activeAnalysisReviews(runner, context, reviewRoot);
      const destination = analysisReviewFile(runner, context, review.requestDigest);
      if (active.size >= 100 && !active.has(path.basename(destination))) {
        throw new GenerationRunnerError(429, "ANALYSIS_REVIEW_TENANT_LIMIT");
      }
      await atomicJson(destination, review);
    },
    "generation-analysis-review-maintenance",
  );
}

async function sweepExpiredTenantInputs(
  runner: RunnerConfig,
  context: AuthorizedContext,
): Promise<void> {
  const sourceRoot = confined(runner.root, "tenants", context.tenantId, "source-bundles");
  const reviewRoot = confined(runner.root, "tenants", context.tenantId, "analysis-reviews");
  await mkdir(sourceRoot, { recursive: true, mode: 0o700 });
  await mkdir(reviewRoot, { recursive: true, mode: 0o700 });
  await withDurableRuntimeOperation(
    runner,
    context,
    tenantMaintenanceJobId(context.tenantId, "source-bundles"),
    async () => {
      ensureMutationsAllowed(runner);
      await activeSourceBundles(runner, context, sourceRoot);
    },
    "generation-source-bundle-maintenance",
  );
  await withDurableRuntimeOperation(
    runner,
    context,
    tenantMaintenanceJobId(context.tenantId, "analysis-reviews"),
    async () => {
      ensureMutationsAllowed(runner);
      await activeAnalysisReviews(runner, context, reviewRoot);
    },
    "generation-analysis-review-maintenance",
  );
}

type GenerationStoragePolicy = {
  retentionMs: number;
  maxJobs: number;
  maxBytes: number;
  reservationBytes: number;
};

function generationStoragePolicy(): GenerationStoragePolicy {
  const retentionSeconds = Number.parseInt(
    process.env.ELMOS_GENERATION_JOB_RETENTION_SECONDS ?? String(7 * 24 * 60 * 60),
    10,
  );
  const maxJobs = Number.parseInt(process.env.ELMOS_GENERATION_MAX_JOBS_PER_TENANT ?? "100", 10);
  const maxBytes = Number.parseInt(
    process.env.ELMOS_GENERATION_MAX_STORAGE_BYTES_PER_TENANT ?? String(5 * 1024 * 1024 * 1024),
    10,
  );
  // The workspace may contain up to 256 MiB of declared archive input, plus a
  // compressed archive, verification evidence, logs and a bounded publication
  // snapshot. Reserve the complete job footprint rather than only the ZIP.
  const reservationBytes = 512 * 1024 * 1024;
  const productionRetentionValid = process.env.NODE_ENV !== "production"
    || [7, 30, 90].map((days) => days * 24 * 60 * 60).includes(retentionSeconds);
  if (
    !productionRetentionValid
    ||
    !Number.isSafeInteger(retentionSeconds)
    || retentionSeconds < 60 * 60
    || retentionSeconds > 90 * 24 * 60 * 60
    || !Number.isSafeInteger(maxJobs)
    || maxJobs < 10
    || maxJobs > 1_000
    || !Number.isSafeInteger(maxBytes)
    || maxBytes < 1024 * 1024 * 1024
    || maxBytes > 1024 * 1024 * 1024 * 1024
    || maxBytes <= reservationBytes
  ) throw new GenerationRunnerError(503, "GENERATION_STORAGE_POLICY_INVALID");
  return {
    retentionMs: retentionSeconds * 1_000,
    maxJobs,
    maxBytes,
    reservationBytes,
  };
}

async function boundedDirectoryBytes(root: string): Promise<number> {
  const pending = [root];
  let fileCount = 0;
  let total = 0;
  while (pending.length > 0) {
    const directory = pending.pop();
    if (!directory) break;
    let entries;
    try {
      entries = await readdir(directory, { withFileTypes: true });
    } catch (error) {
      if (error instanceof Error && "code" in error && error.code === "ENOENT") continue;
      throw error;
    }
    for (const entry of entries) {
      const candidate = confined(root, path.relative(root, directory), entry.name);
      let info;
      try {
        info = await lstat(candidate);
      } catch (error) {
        if (error instanceof Error && "code" in error && error.code === "ENOENT") continue;
        throw error;
      }
      if (info.isSymbolicLink()) {
        // Build tools legitimately create virtual-environment/toolchain links.
        // Count only the link inode and never resolve or follow its target.
        fileCount += 1;
        total += info.size;
        if (fileCount > 250_000 || !Number.isSafeInteger(total)) {
          throw new GenerationRunnerError(507, "GENERATION_STORAGE_SCAN_LIMIT");
        }
        continue;
      }
      if (info.isDirectory()) {
        pending.push(candidate);
        continue;
      }
      if (!info.isFile()) {
        throw new GenerationRunnerError(409, "GENERATION_STORAGE_SPECIAL_FILE_FORBIDDEN");
      }
      fileCount += 1;
      if (fileCount > 250_000) {
        throw new GenerationRunnerError(507, "GENERATION_STORAGE_SCAN_LIMIT");
      }
      total += info.size;
      if (!Number.isSafeInteger(total)) {
        throw new GenerationRunnerError(507, "GENERATION_STORAGE_SIZE_INVALID");
      }
    }
  }
  return total;
}

async function enforceTenantJobStorage(
  runner: RunnerConfig,
  context: AuthorizedContext,
): Promise<void> {
  const policy = generationStoragePolicy();
  const tenantRoot = confined(runner.root, "tenants", context.tenantId);
  const jobsRoot = confined(tenantRoot, "jobs");
  await mkdir(jobsRoot, { recursive: true, mode: 0o700 });
  await sweepExpiredTenantInputs(runner, context);
  let retainedJobs = 0;
  const retainedBytes = await boundedDirectoryBytes(tenantRoot);
  let outstandingReservationBytes = 0;
  const allStatuses = new Set<GenerationJob["status"]>([
    "QUEUED", "ANALYZING", "GENERATING", "VERIFYING", "ARCHIVING",
    "COMPLETED", "PARTIAL", "BLOCKED", "CANCELLED",
  ]);
  const terminalStatuses = new Set<GenerationJob["status"]>([
    "COMPLETED", "PARTIAL", "BLOCKED", "CANCELLED",
  ]);
  const entries = await readdir(jobsRoot, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isSymbolicLink()) {
      throw new GenerationRunnerError(409, "GENERATION_STORAGE_SYMLINK_FORBIDDEN");
    }
    if (!entry.isDirectory() || !jobIdPattern.test(entry.name)) continue;
    const root = confined(jobsRoot, entry.name);
    const recordPath = confined(root, "job.json");
    const recordInfo = await lstat(recordPath);
    if (recordInfo.isSymbolicLink() || !recordInfo.isFile() || recordInfo.size > 4 * 1024 * 1024) {
      throw new GenerationRunnerError(409, "GENERATION_JOB_RECORD_INVALID");
    }
    let record: GenerationJob;
    try {
      record = JSON.parse(await readFile(recordPath, "utf-8")) as GenerationJob;
    } catch {
      throw new GenerationRunnerError(409, "GENERATION_JOB_RECORD_INVALID");
    }
    if (
      record.id !== entry.name
      || record.tenantId !== context.tenantId
      || !allStatuses.has(record.status)
    ) throw new GenerationRunnerError(409, "GENERATION_JOB_RECORD_INVALID");
    const jobBytes = await boundedDirectoryBytes(root);
    retainedJobs += 1;
    if (!terminalStatuses.has(record.status)) {
      outstandingReservationBytes += Math.max(0, policy.reservationBytes - jobBytes);
    }
  }
  if (retainedJobs >= policy.maxJobs) {
    throw new GenerationRunnerError(429, "GENERATION_JOB_TENANT_LIMIT");
  }
  if (
    retainedBytes
    + outstandingReservationBytes
    + policy.reservationBytes
    > policy.maxBytes
  ) {
    throw new GenerationRunnerError(507, "GENERATION_STORAGE_TENANT_LIMIT");
  }
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

async function sha256OpenFile(
  handle: FileHandle,
  expected: Stats,
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
    if (bytesRead <= 0) {
      throw new GenerationRunnerError(409, "ARTIFACT_READ_INCOMPLETE");
    }
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
  ) {
    throw new GenerationRunnerError(409, "ARTIFACT_CHANGED_DURING_VERIFICATION");
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

function bindTerminalRetention(job: GenerationJob): void {
  if (
    !["COMPLETED", "PARTIAL", "BLOCKED", "CANCELLED"].includes(job.status)
    || job.retentionExpiresAt
  ) return;
  const seconds = job.retentionPolicySeconds;
  if (!Number.isSafeInteger(seconds) || (seconds ?? 0) < 60 * 60) return;
  const terminalAt = new Date();
  job.terminalAt = terminalAt.toISOString();
  job.retentionExpiresAt = new Date(terminalAt.getTime() + Number(seconds) * 1_000).toISOString();
}

async function persist(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
): Promise<void> {
  await atomicJson(jobFile(runner, context, job.id), job);
}

function clearRuntimeLeaseTimer(key: string): void {
  const timer = runtimeLeaseTimers.get(key);
  if (timer) clearTimeout(timer);
  runtimeLeaseTimers.delete(key);
}

async function persistRootlessStateDivergence(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
): Promise<void> {
  activeRootlessRuntimes.delete(jobKey(context, job.id));
  job.runtime.status = "BLOCKED";
  job.runtime.previewPort = undefined;
  job.runtime.reason = "ROOTLESS_RUNTIME_LEASE_STATE_DIVERGED";
  job.runtime.updatedAt = new Date().toISOString();
  log(job, "system", "A newer rootless lease exists; the stale job receipt was blocked without stopping it.");
  await persist(runner, context, job);
}

async function expireRuntimeLease(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
): Promise<void> {
  const key = jobKey(context, job.id);
  clearRuntimeLeaseTimer(key);
  if (!['STARTING', 'RUNNING'].includes(job.runtime.status)) return;
  if (job.runtime.executor === "ROOTLESS_CONTAINER" && job.runtime.language) {
    try {
      const cleanup = await rootlessCommand(
        runner,
        [
          "stop",
          "--engine",
          runner.containerEngine ?? "",
          "--language",
          job.runtime.language,
          "--job-id",
          job.id,
          "--state",
          confined(jobRoot(runner, context, job.id), "runtime-state"),
          ...(job.runtime.leaseId ? ["--lease-id", job.runtime.leaseId] : []),
        ],
        60_000,
      );
      if (cleanup.status === "SUPERSEDED") {
        await persistRootlessStateDivergence(runner, context, job);
        return;
      }
      if (cleanup.status !== "STOPPED" && cleanup.status !== "MISSING") {
        throw new GenerationRunnerError(502, "ROOTLESS_RUNTIME_CLEANUP_UNVERIFIED");
      }
      activeRootlessRuntimes.delete(key);
    } catch {
      job.runtime.status = "BLOCKED";
      job.runtime.reason = "RUNTIME_LEASE_CLEANUP_FAILED";
      job.runtime.pid = undefined;
      job.runtime.updatedAt = new Date().toISOString();
      log(job, "system", "Ten-minute runtime lease expired, but rootless cleanup could not be verified.");
      await persist(runner, context, job);
      return;
    }
  } else {
    const child = activeRuntimes.get(key);
    if (child) {
      expiredRuntimes.add(key);
      try {
        await terminateAndWait(child);
      } catch {
        job.runtime.status = "BLOCKED";
        job.runtime.reason = "RUNTIME_PROCESS_TERMINATION_UNVERIFIED";
        job.runtime.updatedAt = new Date().toISOString();
        log(job, "system", "Runtime lease expired, but process termination could not be verified.");
        await persist(runner, context, job);
        return;
      }
    }
  }
  job.runtime.status = "STOPPED";
  job.runtime.previewPort = undefined;
  job.runtime.pid = undefined;
  job.runtime.reason = "RUNTIME_LEASE_EXPIRED";
  job.runtime.updatedAt = new Date().toISOString();
  log(job, "system", "Ten-minute browser runtime lease expired and the runtime was stopped.");
  await persist(runner, context, job);
}

async function expireExpectedRuntimeLease(
  runner: RunnerConfig,
  context: AuthorizedContext,
  expected: GenerationJob,
): Promise<void> {
  const latest = await load(runner, context, expected.id, true);
  if (
    !["STARTING", "RUNNING"].includes(latest.runtime.status)
    || latest.runtime.executor !== expected.runtime.executor
    || latest.runtime.leaseId !== expected.runtime.leaseId
    || latest.runtime.leaseExpiresAt !== expected.runtime.leaseExpiresAt
  ) return;
  await expireRuntimeLease(runner, context, latest);
}

function attemptExpectedRuntimeExpiration(
  runner: RunnerConfig,
  context: AuthorizedContext,
  expected: GenerationJob,
  retryCount = 0,
): void {
  const key = jobKey(context, expected.id);
  void withRuntimeOperation(
    key,
    () => withDurableRuntimeOperation(
      runner,
      context,
      expected.id,
      () => expireExpectedRuntimeLease(runner, context, expected),
    ),
  ).catch(() => {
    if (runtimeLeaseTimers.has(key)) return;
    if (retryCount === 0 || retryCount % 12 === 0) {
      console.error("Generation runtime expiry reconciliation will retry after a durable-lock failure.");
    }
    const retry = setTimeout(() => {
      if (runtimeLeaseTimers.get(key) !== retry) return;
      runtimeLeaseTimers.delete(key);
      attemptExpectedRuntimeExpiration(runner, context, expected, retryCount + 1);
    }, 5_000);
    retry.unref();
    runtimeLeaseTimers.set(key, retry);
  });
}

function scheduleRuntimeLease(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
): void {
  const key = jobKey(context, job.id);
  clearRuntimeLeaseTimer(key);
  const expiresAt = Date.parse(job.runtime.leaseExpiresAt ?? "");
  if (!Number.isFinite(expiresAt)) return;
  const remaining = expiresAt - Date.now();
  if (remaining <= 0) {
    attemptExpectedRuntimeExpiration(runner, context, job);
    return;
  }
  const timer = setTimeout(() => {
    runtimeLeaseTimers.delete(key);
    attemptExpectedRuntimeExpiration(runner, context, job);
  }, remaining);
  timer.unref();
  runtimeLeaseTimers.set(key, timer);
}

async function load(
  runner: RunnerConfig,
  context: AuthorizedContext,
  jobId: string,
  runtimeOperationHeld = false,
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
  if (!safeEqual(parsed.actor, context.actor)) {
    throw new GenerationRunnerError(404, "JOB_NOT_FOUND");
  }
  parsed.artifacts ??= [];
  const key = jobKey(context, jobId);
  if (
    !runtimeOperationHeld
    && (
      ["STARTING", "RUNNING"].includes(parsed.runtime.status)
      || parsed.runtime.reason === "RUNTIME_LEASE_CLEANUP_FAILED"
    )
  ) {
    return withRuntimeOperation(
      key,
      () => withDurableRuntimeOperation(
        runner,
        context,
        jobId,
        () => load(runner, context, jobId, true),
      ),
    );
  }
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
  if (parsed.runtime.status === "RUNNING") {
    const leaseExpiresAt = Date.parse(parsed.runtime.leaseExpiresAt ?? "");
    if (!Number.isFinite(leaseExpiresAt) || leaseExpiresAt <= Date.now()) {
      await expireRuntimeLease(runner, context, parsed);
      return parsed;
    }
  }
  if (
    parsed.runtime.executor === "ROOTLESS_CONTAINER"
    && (
      ["STARTING", "RUNNING"].includes(parsed.runtime.status)
      || parsed.runtime.reason === "RUNTIME_LEASE_CLEANUP_FAILED"
    )
  ) {
    await reconcileRootlessRuntime(runner, context, parsed);
    if (["STARTING", "RUNNING"].includes(parsed.runtime.status)) {
      scheduleRuntimeLease(runner, context, parsed);
    }
  } else if (parsed.runtime.status === "RUNNING" && !activeRuntimes.has(key)) {
    clearRuntimeLeaseTimer(key);
    parsed.runtime.status = "BLOCKED";
    parsed.runtime.reason = "RUNTIME_PROCESS_LOST_AFTER_RESTART";
    parsed.runtime.updatedAt = new Date().toISOString();
    await persist(runner, context, parsed);
  } else if (["STARTING", "RUNNING"].includes(parsed.runtime.status)) {
    scheduleRuntimeLease(runner, context, parsed);
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
    HOME: runner.engineHome,
    NODE_ENV: process.env.NODE_ENV,
    LANG: process.env.LANG ?? "en_US.UTF-8",
    LC_ALL: process.env.LC_ALL ?? "en_US.UTF-8",
    NO_PROXY: "127.0.0.1,localhost",
    no_proxy: "127.0.0.1,localhost",
    // Generated dependency graphs are pinned by the synthesis engine. A
    // service-owned, persistent uv cache prevents every browser job from
    // redownloading the same verified wheels while HOME remains job-isolated.
    UV_CACHE_DIR: runner.uvCache,
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

function rootlessCommandEnvironment(runner: RunnerConfig): NodeJS.ProcessEnv {
  const environment = engineCommandEnvironment(runner);
  if (runner.engineXdgRuntimeDir) {
    environment.XDG_RUNTIME_DIR = runner.engineXdgRuntimeDir;
  }
  if (runner.dockerUnixSocket) {
    environment.DOCKER_HOST = `unix://${runner.dockerUnixSocket}`;
  }
  return environment;
}

async function ensureRunnerHome(runner: RunnerConfig): Promise<void> {
  await mkdir(runner.engineHome, { recursive: true, mode: 0o700 });
  const info = await lstat(runner.engineHome);
  if (
    info.isSymbolicLink()
    || !info.isDirectory()
    || (info.mode & 0o077) !== 0
    || (typeof process.getuid === "function" && info.uid !== process.getuid())
    || await realpath(runner.engineHome) !== runner.engineHome
  ) {
    throw new GenerationRunnerError(503, "LOCAL_RUNNER_HOME_INVALID");
  }
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
  await ensureRunnerHome(runner);
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
  await ensureRunnerHome(runner);
  return new Promise((resolve, reject) => {
    const child = spawn(
      runner.uv,
      isolatedPythonArguments([
        runner.rootlessTool,
        ...args,
      ]),
      {
        cwd: runner.repositoryRoot,
        env: rootlessCommandEnvironment(runner),
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
  return withDurableRuntimeOperation(
    runner,
    context,
    tenantMaintenanceJobId(context.tenantId, "source-bundles"),
    async () => {
      ensureMutationsAllowed(runner);
      const existing = await activeSourceBundles(runner, context, sourceRoot);
      const filename = `${bundle.bundleSha256}.json`;
      if (existing.size >= 100 && !existing.has(filename)) {
        throw new GenerationRunnerError(429, "SOURCE_BUNDLE_TENANT_LIMIT");
      }
      const now = new Date();
      const prior = existing.get(filename);
      const authorizedActors = new Set(prior?.authorizedActors ?? (prior ? [prior.actor] : []));
      authorizedActors.add(context.actor);
      if (authorizedActors.size > 64) {
        throw new GenerationRunnerError(429, "SOURCE_BUNDLE_ACTOR_LIMIT");
      }
      const stored: StoredSourceBundle = {
        tenantId: context.tenantId,
        actor: prior?.actor ?? context.actor,
        authorizedActors: [...authorizedActors].sort(),
        createdAt: prior?.createdAt ?? now.toISOString(),
        expiresAt: new Date(now.getTime() + 60 * 60_000).toISOString(),
        bundle,
      };
      await atomicJson(sourceBundleFile(runner, context, bundle.bundleSha256), stored);
      return bundle;
    },
    "generation-source-bundle-maintenance",
  );
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
    || !(stored.authorizedActors ?? [stored.actor]).some((actor) => safeEqual(actor, context.actor))
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
    await storeAnalysisReview(runner, context, review);
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
  await ensureRunnerHome(runner);
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
    let commandClosed = false;
    let storageCheckInFlight = false;
    let storageFailure: Error | null = null;
    let persistenceFailure: Error | null = null;
    let persistenceQueue = Promise.resolve();
    const queuePersist = () => {
      persistenceQueue = persistenceQueue
        .then(() => persist(runner, context, job))
        .catch((error: unknown) => {
          persistenceFailure ??= error instanceof Error ? error : new Error("JOB_PERSISTENCE_FAILED");
        });
    };
    const startedAt = Date.now();
    const progressHeartbeat = stage === "pipeline"
      ? setInterval(() => {
          const elapsedSeconds = Math.floor((Date.now() - startedAt) / 1_000);
          log(job, "system", `pipeline is still running within the bounded execution window (${elapsedSeconds}s elapsed).`);
          queuePersist();
        }, 30_000)
      : null;
    progressHeartbeat?.unref();
    const storageMonitor = stage === "pipeline"
      ? setInterval(() => {
          if (commandClosed || storageCheckInFlight || storageFailure) return;
          storageCheckInFlight = true;
          void boundedDirectoryBytes(jobRoot(runner, context, job.id))
            .then((bytes) => {
              if (
                !commandClosed
                && bytes > generationStoragePolicy().reservationBytes
              ) {
                const failure = new GenerationRunnerError(
                  507,
                  "GENERATION_JOB_STORAGE_RESERVATION_EXCEEDED",
                );
                storageFailure = failure;
                log(job, "system", failure.code);
                terminate(child);
              }
            })
            .catch((error: unknown) => {
              if (commandClosed) return;
              storageFailure = error instanceof Error
                ? error
                : new GenerationRunnerError(507, "GENERATION_STORAGE_SCAN_FAILED");
              terminate(child);
            })
            .finally(() => {
              storageCheckInFlight = false;
            });
        }, 2_000)
      : null;
    storageMonitor?.unref();
    const timeout = setTimeout(() => {
      timedOut = true;
      log(job, "system", `${stage} exceeded its bounded execution time.`);
      terminate(child);
    }, stage === "analyze" ? 60_000 : 20 * 60_000);
    child.stdout?.on("data", (chunk: Buffer) => {
      stdout = `${stdout}${chunk.toString("utf-8")}`.slice(-200_000);
      log(job, "stdout", chunk.toString("utf-8"));
      queuePersist();
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr = `${stderr}${chunk.toString("utf-8")}`.slice(-200_000);
      log(job, "stderr", chunk.toString("utf-8"));
      queuePersist();
    });
    child.once("error", async (error) => {
      commandClosed = true;
      clearTimeout(timeout);
      if (progressHeartbeat) clearInterval(progressHeartbeat);
      if (storageMonitor) clearInterval(storageMonitor);
      activeJobs.delete(key);
      await persistenceQueue;
      reject(persistenceFailure ?? error);
    });
    child.once("close", async (code, signal) => {
      commandClosed = true;
      clearTimeout(timeout);
      if (progressHeartbeat) clearInterval(progressHeartbeat);
      if (storageMonitor) clearInterval(storageMonitor);
      activeJobs.delete(key);
      await persistenceQueue;
      if (storageFailure) {
        reject(storageFailure);
        return;
      }
      if (persistenceFailure) {
        reject(persistenceFailure);
        return;
      }
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

async function loadVerifiedGenerationInsights(
  root: string,
  verificationInsights: unknown,
  expectedVerificationStatus: string,
): Promise<NonNullable<GenerationJob["insights"]>> {
  const workspace = confined(root, "workspace");
  const insightPath = confined(workspace, "requirements", "project-insights.json");
  const details = lstatSync(insightPath);
  if (details.isSymbolicLink() || !details.isFile() || details.size < 1 || details.size > 4_000_000) {
    throw new GenerationRunnerError(500, "GENERATION_INSIGHTS_ARTIFACT_INVALID");
  }
  let generated: unknown;
  try {
    generated = JSON.parse(await readFile(insightPath, "utf-8"));
  } catch {
    throw new GenerationRunnerError(500, "GENERATION_INSIGHTS_ARTIFACT_INVALID");
  }
  const verified = validateVerifiedInsightProjection(generated, verificationInsights);
  if (verified.verification_status !== expectedVerificationStatus) {
    throw new GenerationRunnerError(500, "GENERATION_INSIGHTS_STATUS_MISMATCH");
  }
  return verified;
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
      verification?: { insights?: unknown };
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
    if (!job.artifacts.some((artifact) => artifact.path === "requirements/project-insights.json")) {
      throw new Error("GENERATION_INSIGHTS_ARTIFACT_MISSING");
    }
    job.insights = await loadVerifiedGenerationInsights(
      root,
      result.verification?.insights,
      result.status ?? "UNKNOWN",
    );
    const archive = confined(root, "generated-project.zip");
    const archiveInfo = await stat(archive);
    if (!archiveInfo.isFile() || archiveInfo.size <= 0 || archiveInfo.size > 128 * 1024 * 1024) {
      throw new Error("ARCHIVE_INVALID");
    }
    job.artifactSha256 = await sha256File(archive);
    job.artifactSize = archiveInfo.size;
    if ((await boundedDirectoryBytes(root)) > generationStoragePolicy().reservationBytes) {
      throw new Error("GENERATION_JOB_STORAGE_RESERVATION_EXCEEDED");
    }
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
    bindTerminalRetention(job);
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
  const job = await withDurableRuntimeOperation(
    runner,
    context,
    tenantMaintenanceJobId(context.tenantId, "job-storage"),
    async () => {
      ensureMutationsAllowed(runner);
      await enforceTenantJobStorage(runner, context);
      const id = randomUUID();
      const now = new Date().toISOString();
      const storagePolicy = generationStoragePolicy();
      const accepted: GenerationJob = {
        id,
        tenantId: context.tenantId,
        actor: context.actor,
        createdAt: now,
        updatedAt: now,
        retentionPolicySeconds: Math.floor(storagePolicy.retentionMs / 1_000),
        retentionPolicyVersion: "generation-storage-v1",
        legalHold: false,
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
      let reviewMoved = false;
      try {
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
          reviewMoved = true;
        } catch {
          throw new GenerationRunnerError(409, "ANALYSIS_REVIEW_ALREADY_CONSUMED");
        }
        log(accepted, "system", "Job accepted into the tenant-isolated local runner.");
        await persist(runner, context, accepted);
        return accepted;
      } catch (error) {
        if (reviewMoved) {
          try {
            await rename(
              confined(root, "analysis-review.json"),
              analysisReviewFile(runner, context, validated.analysisDigest),
            );
          } catch {
            throw new GenerationRunnerError(500, "GENERATION_JOB_STORAGE_ROLLBACK_FAILED");
          }
        }
        await rm(root, { recursive: true, force: true });
        throw error;
      }
    },
    "generation-job-storage-maintenance",
  );
  scheduledJobs.add(jobKey(context, job.id));
  void runJob(runner, context, job);
  return job;
}

export async function getJob(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  const job = await load(config(), context, jobId);
  const expiresAt = Date.parse(job.runtime.leaseExpiresAt ?? "");
  job.runtime.remainingSeconds = job.runtime.status === "RUNNING" && Number.isFinite(expiresAt)
    ? Math.max(0, Math.ceil((expiresAt - Date.now()) / 1_000))
    : 0;
  return job;
}

function terminate(child: ChildProcess): void {
  if (
    child.pid === undefined
    || child.exitCode !== null
    || child.signalCode !== null
  ) return;
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }
}

async function terminateAndWait(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const closed = new Promise<void>((resolve) => child.once("close", () => resolve()));
  terminate(child);
  await Promise.race([
    closed,
    new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
  ]);
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (child.pid !== undefined) {
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      child.kill("SIGKILL");
    }
  }
  await Promise.race([
    closed,
    new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
  ]);
  if (child.exitCode === null && child.signalCode === null) {
    throw new GenerationRunnerError(503, "RUNTIME_PROCESS_TERMINATION_UNVERIFIED");
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
  bindTerminalRetention(job);
  await persist(runner, context, job);
  return job;
}

export async function artifact(
  context: AuthorizedContext,
  jobId: string,
): Promise<{ handle: FileHandle; path: string; size: number; sha256: string }> {
  const runner = config();
  ensureMutationsAllowed(runner);
  const job = await load(runner, context, jobId);
  if (!job.artifactReady) throw new GenerationRunnerError(409, "ARTIFACT_NOT_READY");
  const root = await realpath(jobRoot(runner, context, jobId));
  const archive = await realpath(confined(root, "generated-project.zip"));
  if (archive !== root && !archive.startsWith(`${root}${path.sep}`)) {
    throw new GenerationRunnerError(409, "ARTIFACT_OUTSIDE_JOB_ROOT");
  }
  const handle = await open(
    archive,
    fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW,
  );
  try {
    const info = await handle.stat();
    if (!info.isFile() || info.nlink !== 1) {
      throw new GenerationRunnerError(404, "ARTIFACT_NOT_FOUND");
    }
    const sha256 = await sha256OpenFile(handle, info);
    if (
      !job.artifactSha256
      || job.artifactSize !== info.size
      || !safeEqual(job.artifactSha256, sha256)
    ) {
      throw new GenerationRunnerError(409, "ARTIFACT_INTEGRITY_MISMATCH");
    }
    return { handle, path: archive, size: info.size, sha256 };
  } catch (error) {
    await handle.close().catch(() => undefined);
    throw error;
  }
}

export type GenerationPublishFile = {
  path: string;
  sha256: string;
  mode: "100644" | "100755";
  content: Buffer;
};

export type GenerationPublishSnapshot = {
  projectName: string;
  artifactSha256: string;
  files: GenerationPublishFile[];
  existingPublication?: GenerationGitHubPublication;
};

async function readArchivePublishFiles(extractedRoot: string): Promise<GenerationPublishFile[]> {
  const files: GenerationPublishFile[] = [];
  let totalBytes = 0;
  const visit = async (directory: string, depth: number): Promise<void> => {
    if (depth > 24) throw new GenerationRunnerError(409, "PUBLISH_TREE_DEPTH_EXCEEDED");
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      if (entry.isSymbolicLink()) {
        throw new GenerationRunnerError(409, "PUBLISH_TREE_SYMLINK_FORBIDDEN");
      }
      const child = confined(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(child, depth + 1);
        continue;
      }
      if (!entry.isFile()) throw new GenerationRunnerError(409, "GITHUB_PUBLISH_FILE_INVALID");
      const resolved = await realpath(child);
      if (resolved !== child || !resolved.startsWith(`${extractedRoot}${path.sep}`)) {
        throw new GenerationRunnerError(409, "GITHUB_PUBLISH_FILE_OUTSIDE_ARCHIVE");
      }
      const info = await stat(resolved);
      if (!info.isFile() || info.size > 32 * 1024 * 1024) {
        throw new GenerationRunnerError(409, "GITHUB_PUBLISH_FILE_INVALID");
      }
      totalBytes += info.size;
      if (totalBytes > 64 * 1024 * 1024) {
        throw new GenerationRunnerError(409, "GITHUB_PUBLISH_BYTES_EXCEEDED");
      }
      if (files.length >= 1_000) {
        throw new GenerationRunnerError(409, "GITHUB_PUBLISH_FILE_COUNT_EXCEEDED");
      }
      const content = await readFile(resolved);
      files.push({
        path: path.relative(extractedRoot, resolved).split(path.sep).join("/"),
        sha256: createHash("sha256").update(content).digest("hex"),
        mode: info.mode & 0o111 ? "100755" : "100644",
        content,
      });
    }
  };
  await visit(extractedRoot, 0);
  if (files.length === 0) throw new GenerationRunnerError(409, "GITHUB_PUBLISH_ARCHIVE_EMPTY");
  return files;
}

export async function generationPublishSnapshot(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationPublishSnapshot> {
  const runner = config();
  const job = await load(runner, context, jobId);
  if (job.status !== "COMPLETED" || job.resultStatus !== "PASSED" || !job.artifactReady) {
    throw new GenerationRunnerError(409, "GITHUB_PUBLISH_REQUIRES_PASSED_GENERATION");
  }
  if (!job.artifactSha256 || !digestPattern.test(job.artifactSha256)) {
    throw new GenerationRunnerError(409, "GITHUB_PUBLISH_ARTIFACT_IDENTITY_MISSING");
  }
  const root = await realpath(jobRoot(runner, context, jobId));
  const archive = await artifact(context, jobId);
  const publicationRoot = await mkdtemp(confined(root, ".github-publish-snapshot-"));
  const extractionRoot = confined(publicationRoot, "extracted");
  const archiveSnapshot = confined(publicationRoot, "generated-project.zip");
  try {
    if (!safeEqual(archive.sha256, job.artifactSha256)) {
      throw new GenerationRunnerError(409, "ARTIFACT_INTEGRITY_MISMATCH");
    }
    await mkdir(extractionRoot, { mode: 0o700 });
    await streamPipeline(
      archive.handle.createReadStream({ start: 0, autoClose: false }),
      createWriteStream(archiveSnapshot, { flags: "wx", mode: 0o600 }),
    );
    const snapshotInfo = await stat(archiveSnapshot);
    if (
      !snapshotInfo.isFile()
      || snapshotInfo.size !== archive.size
      || !safeEqual(await sha256File(archiveSnapshot), archive.sha256)
    ) {
      throw new GenerationRunnerError(409, "GITHUB_PUBLISH_ARCHIVE_SNAPSHOT_INVALID");
    }
    const extraction = await executePreviewCommand(runner, engineCliArguments([
      "extract-publish-archive",
      "--archive",
      archiveSnapshot,
      "--expected-sha256",
      archive.sha256,
      "--output",
      extractionRoot,
    ]));
    if (extraction.exitCode !== 0) {
      throw new GenerationRunnerError(409, "GITHUB_PUBLISH_ARCHIVE_EXTRACTION_FAILED");
    }
    const receipt = JSON.parse(extraction.stdout) as {
      status?: unknown;
      project_name?: unknown;
      file_count?: unknown;
      archive_sha256?: unknown;
    };
    const projectName = receipt.project_name;
    if (
      receipt.status !== "EXTRACTED"
      || receipt.archive_sha256 !== archive.sha256
      || typeof projectName !== "string"
      || !namePattern.test(projectName)
      || !Number.isInteger(receipt.file_count)
      || Number(receipt.file_count) < 1
      || Number(receipt.file_count) > 1_000
    ) throw new GenerationRunnerError(409, "GITHUB_PUBLISH_ARCHIVE_RECEIPT_INVALID");
    const extractedRoot = await realpath(confined(extractionRoot, projectName));
    const files = await readArchivePublishFiles(extractedRoot);
    if (files.length !== receipt.file_count) {
      throw new GenerationRunnerError(409, "GITHUB_PUBLISH_ARCHIVE_RECEIPT_INVALID");
    }
    const blueprint = JSON.parse(
      await readFile(confined(extractedRoot, "requirements", "project-blueprint.json"), "utf-8"),
    ) as { project?: { name?: unknown } };
    if (blueprint.project?.name !== projectName) {
      throw new GenerationRunnerError(409, "PROJECT_BLUEPRINT_NAME_INVALID");
    }
    return {
      projectName,
      artifactSha256: job.artifactSha256,
      files,
      ...(job.githubPublication ? { existingPublication: job.githubPublication } : {}),
    };
  } finally {
    await archive.handle.close().catch(() => undefined);
    await rm(publicationRoot, { recursive: true, force: true });
  }
}

export async function recordGenerationGitHubPublication(
  context: AuthorizedContext,
  jobId: string,
  publication: GenerationGitHubPublication,
): Promise<GenerationJob> {
  const runner = config();
  const job = await load(runner, context, jobId);
  const repositoryIdentityValid = (
    typeof publication.repositoryFullName === "string"
    && /^[A-Za-z0-9-]{1,39}\/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(publication.repositoryFullName)
  );
  const creatingReceiptValid = publication.status !== "CREATING" || (
    repositoryIdentityValid
    && publication.repositoryId === undefined
    && publication.repositoryUrl === undefined
    && publication.branch === undefined
    && publication.commitSha === undefined
    && publication.fileCount === undefined
    && publication.reason === undefined
  );
  const publishedReceiptValid = publication.status !== "PUBLISHED" || (
    repositoryIdentityValid
    && Number.isSafeInteger(publication.repositoryId)
    && (publication.repositoryId ?? 0) > 0
    && safeExternalHttpsUrl(publication.repositoryUrl)
    && publication.branch === "main"
    && typeof publication.commitSha === "string"
    && /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(publication.commitSha)
    && Number.isInteger(publication.fileCount)
    && (publication.fileCount ?? 0) > 0
    && (publication.fileCount ?? 0) <= 1_000
    && publication.reason === undefined
  );
  const blockedReceiptValid = publication.status !== "BLOCKED" || (
    typeof publication.reason === "string"
    && /^[A-Z0-9_]{3,256}$/.test(publication.reason)
    && (publication.repositoryFullName === undefined || repositoryIdentityValid)
    && (
      publication.repositoryId === undefined
      || (Number.isSafeInteger(publication.repositoryId) && (publication.repositoryId ?? 0) > 0)
    )
    && publication.branch === undefined
    && publication.commitSha === undefined
    && publication.fileCount === undefined
    && (publication.repositoryUrl === undefined || safeExternalHttpsUrl(publication.repositoryUrl))
  );
  if (
    !digestPattern.test(publication.artifactSha256)
    || !githubIdempotencyKeyPattern.test(publication.idempotencyKey)
    || publication.reason && publication.reason.length > 256
    || !creatingReceiptValid
    || !publishedReceiptValid
    || !blockedReceiptValid
    || Number.isNaN(Date.parse(publication.updatedAt))
  ) throw new GenerationRunnerError(500, "GITHUB_PUBLICATION_RECEIPT_INVALID");
  if (
    job.githubPublication?.status === "PUBLISHED"
    && canonicalJson(job.githubPublication) !== canonicalJson(publication)
  ) throw new GenerationRunnerError(409, "GITHUB_PUBLICATION_ALREADY_RECORDED");
  job.githubPublication = publication;
  log(
    job,
    "system",
    publication.status === "PUBLISHED"
      ? `GitHub private repository ${publication.repositoryFullName} verified at ${publication.commitSha}.`
      : publication.status === "CREATING"
        ? `GitHub repository creation intent persisted for ${publication.repositoryFullName}.`
        : `GitHub publication blocked: ${publication.reason ?? "UNKNOWN"}.`,
  );
  await persist(runner, context, job);
  return job;
}

async function runtimePreviewLocked(
  context: AuthorizedContext,
  jobId: string,
): Promise<{
  status: "RUNNING";
  service: string;
  language: GenerationTargetId;
  health: unknown;
  leaseExpiresAt: string;
  remainingSeconds: number;
}> {
  const runner = config();
  const job = await load(runner, context, jobId, true);
  if (job.runtime.status !== "RUNNING" || !job.runtime.language) {
    throw new GenerationRunnerError(409, "RUNTIME_PREVIEW_NOT_RUNNING");
  }
  const expiresAt = Date.parse(job.runtime.leaseExpiresAt ?? "");
  if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
    await expireRuntimeLease(runner, context, job);
    throw new GenerationRunnerError(409, "RUNTIME_LEASE_EXPIRED");
  }
  const plan = job.runtime.plans.find((candidate) => candidate.language === job.runtime.language);
  if (!plan || plan.port !== targetPorts[job.runtime.language]) {
    throw new GenerationRunnerError(409, "RUNTIME_PLAN_NOT_AVAILABLE");
  }
  const previewPort = job.runtime.executor === "ROOTLESS_CONTAINER"
    ? job.runtime.previewPort
    : plan.port;
  if (
    typeof previewPort !== "number"
    || !Number.isSafeInteger(previewPort)
    || previewPort < 1_024
    || previewPort > 65_535
  ) throw new GenerationRunnerError(409, "RUNTIME_PREVIEW_PORT_INVALID");
  const workspace = await realpath(confined(jobRoot(runner, context, jobId), "workspace"));
  const blueprint = JSON.parse(
    await readFile(confined(workspace, "requirements", "project-blueprint.json"), "utf-8"),
  ) as { project?: { name?: unknown } };
  const service = blueprint.project?.name;
  if (typeof service !== "string" || !namePattern.test(service)) {
    throw new GenerationRunnerError(409, "PROJECT_BLUEPRINT_NAME_INVALID");
  }
  let response: Response;
  const healthPath = plan.providers?.includes("postgresql") ? "/health/ready" : "/health";
  try {
    response = await fetch(`http://127.0.0.1:${previewPort}${healthPath}`, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(2_000),
    });
  } catch {
    throw new GenerationRunnerError(503, "RUNTIME_PREVIEW_UNAVAILABLE");
  }
  const declaredHeader = response.headers.get("content-length");
  const declaredLength = Number.parseInt(declaredHeader ?? "0", 10);
  if (
    !response.ok
    || (
      declaredHeader !== null
      && (!Number.isSafeInteger(declaredLength) || declaredLength < 0 || declaredLength > 64 * 1024)
    )
    || !response.body
  ) {
    throw new GenerationRunnerError(502, "RUNTIME_PREVIEW_HEALTH_INVALID");
  }
  const reader = response.body.getReader();
  const chunks: Buffer[] = [];
  let received = 0;
  while (true) {
    const part = await reader.read();
    if (part.done) break;
    received += part.value.byteLength;
    if (received > 64 * 1024) {
      await reader.cancel();
      throw new GenerationRunnerError(502, "RUNTIME_PREVIEW_HEALTH_INVALID");
    }
    chunks.push(Buffer.from(part.value));
  }
  const raw = Buffer.concat(chunks).toString("utf-8");
  let health: unknown;
  try {
    health = JSON.parse(raw);
  } catch {
    throw new GenerationRunnerError(502, "RUNTIME_PREVIEW_HEALTH_INVALID");
  }
  const identity = health as { status?: unknown; service?: unknown };
  if (identity.status !== "UP" || identity.service !== service) {
    throw new GenerationRunnerError(502, "RUNTIME_PREVIEW_IDENTITY_MISMATCH");
  }
  if (Date.now() >= expiresAt) {
    await expireRuntimeLease(runner, context, job);
    throw new GenerationRunnerError(409, "RUNTIME_LEASE_EXPIRED");
  }
  return {
    status: "RUNNING",
    service,
    language: job.runtime.language,
    health: { status: "UP", service },
    leaseExpiresAt: new Date(expiresAt).toISOString(),
    remainingSeconds: Math.max(0, Math.ceil((expiresAt - Date.now()) / 1_000)),
  };
}

export async function runtimePreview(
  context: AuthorizedContext,
  jobId: string,
): Promise<Awaited<ReturnType<typeof runtimePreviewLocked>>> {
  if (!jobIdPattern.test(jobId)) throw new GenerationRunnerError(400, "JOB_ID_INVALID");
  const runner = config();
  const key = jobKey(context, jobId);
  return withRuntimeOperation(
    key,
    () => withDurableRuntimeOperation(
      runner,
      context,
      jobId,
      () => runtimePreviewLocked(context, jobId),
    ),
  );
}

async function confirmRuntimeHealth(
  runner: RunnerConfig,
  context: AuthorizedContext,
  job: GenerationJob,
  child: ChildProcess,
  key: string,
  port: number,
  expectedService: string,
  leaseDurationMs: number,
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
        const leaseStartedAt = new Date();
        const leaseExpiresAt = new Date(leaseStartedAt.getTime() + leaseDurationMs);
        job.runtime.status = "RUNNING";
        job.runtime.reason = undefined;
        job.runtime.leaseStartedAt = leaseStartedAt.toISOString();
        job.runtime.leaseExpiresAt = leaseExpiresAt.toISOString();
        job.runtime.leaseDurationSeconds = Math.ceil(leaseDurationMs / 1_000);
        job.runtime.updatedAt = new Date().toISOString();
        log(job, "system", `Runtime health probe passed on 127.0.0.1:${port}.`);
        log(job, "system", `Browser preview lease expires at ${leaseExpiresAt.toISOString()}.`);
        await persist(runner, context, job);
        scheduleRuntimeLease(runner, context, job);
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
    if (job.runtime.reason === "RUNTIME_LEASE_CLEANUP_FAILED") {
      const cleanup = await rootlessCommand(
        runner,
        [
          "stop",
          "--engine",
          runner.containerEngine ?? "",
          "--language",
          language,
          "--job-id",
          job.id,
          "--state",
          confined(jobRoot(runner, context, job.id), "runtime-state"),
          ...(job.runtime.leaseId ? ["--lease-id", job.runtime.leaseId] : []),
        ],
        60_000,
      );
      if (cleanup.status === "SUPERSEDED") {
        await persistRootlessStateDivergence(runner, context, job);
        return;
      }
      if (cleanup.status !== "STOPPED" && cleanup.status !== "MISSING") {
        throw new GenerationRunnerError(502, "ROOTLESS_RUNTIME_CLEANUP_UNVERIFIED");
      }
      activeRootlessRuntimes.delete(jobKey(context, job.id));
      job.runtime.status = "STOPPED";
      job.runtime.previewPort = undefined;
      job.runtime.reason = "RUNTIME_CLEANUP_RECONCILED";
      job.runtime.updatedAt = new Date().toISOString();
      log(job, "system", "Rootless runtime cleanup was reconciled and verified.");
      await persist(runner, context, job);
      return;
    }
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
        "--state",
        confined(jobRoot(runner, context, job.id), "runtime-state"),
        ...(job.runtime.leaseId ? ["--lease-id", job.runtime.leaseId] : []),
      ],
      30_000,
    );
    const status = state.status;
    if (status === "RUNNING" || status === "STARTING") {
      const hostPort = state.host_port;
      if (
        status === "RUNNING"
        && (
          typeof hostPort !== "number"
          || !Number.isSafeInteger(hostPort)
          || hostPort < 1_024
          || hostPort > 65_535
        )
      ) throw new GenerationRunnerError(502, "ROOTLESS_RUNTIME_HOST_PORT_INVALID");
      activeRootlessRuntimes.add(jobKey(context, job.id));
      job.runtime.status = status;
      job.runtime.previewPort = status === "RUNNING" ? Number(hostPort) : undefined;
      job.runtime.reason = undefined;
    } else if (status === "SUPERSEDED") {
      await persistRootlessStateDivergence(runner, context, job);
      return;
    } else if (
      status === "EXPIRED"
      || (
        status === "MISSING"
        && Date.parse(job.runtime.leaseExpiresAt ?? "") <= Date.now()
      )
    ) {
      activeRootlessRuntimes.delete(jobKey(context, job.id));
      job.runtime.status = "STOPPED";
      job.runtime.previewPort = undefined;
      job.runtime.reason = "RUNTIME_LEASE_EXPIRED";
      if (!job.logs.some((entry) => entry.message.includes("Ten-minute browser runtime lease expired"))) {
        log(job, "system", "Ten-minute browser runtime lease expired and the runtime was stopped.");
      }
    } else {
      activeRootlessRuntimes.delete(jobKey(context, job.id));
      job.runtime.status = "BLOCKED";
      job.runtime.previewPort = undefined;
      job.runtime.reason = status === "MISSING"
        ? "ROOTLESS_RUNTIME_MISSING"
        : `ROOTLESS_RUNTIME_${String(status ?? "UNKNOWN")}`;
    }
  } catch (error) {
    activeRootlessRuntimes.delete(jobKey(context, job.id));
    job.runtime.status = "BLOCKED";
    job.runtime.previewPort = undefined;
    job.runtime.reason = error instanceof GenerationRunnerError
      ? error.code
      : "ROOTLESS_RUNTIME_RECONCILIATION_FAILED";
  }
  job.runtime.updatedAt = new Date().toISOString();
  await persist(runner, context, job);
}

async function startRuntimeLocked(
  context: AuthorizedContext,
  jobId: string,
  language: GenerationTargetId,
): Promise<GenerationJob> {
  const runner = config();
  ensureMutationsAllowed(runner);
  const job = await load(runner, context, jobId, true);
  if (!targetIds.has(language)) throw new GenerationRunnerError(400, "LANGUAGE_INVALID");
  if (!["COMPLETED", "PARTIAL"].includes(job.status)) {
    throw new GenerationRunnerError(409, "JOB_NOT_READY");
  }
  const currentArtifacts = await loadArtifacts(jobRoot(runner, context, jobId));
  if (!safeEqual(sha256Json(currentArtifacts), sha256Json(job.artifacts))) {
    throw new GenerationRunnerError(409, "WORKSPACE_INTEGRITY_MISMATCH");
  }
  const key = jobKey(context, jobId);
  if (
    activeRuntimes.has(key)
    || activeRootlessRuntimes.has(key)
    || ["STARTING", "RUNNING"].includes(job.runtime.status)
  ) throw new GenerationRunnerError(409, "RUNTIME_ALREADY_RUNNING");
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
  const leaseDurationMs = configuredRuntimeLeaseMilliseconds();
  if (runner.executor === "ROOTLESS_CONTAINER") {
    await assertProductionRuntimeReaper(runner);
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
      "--lease-seconds",
      String(Math.ceil(leaseDurationMs / 1_000)),
    ]);
    const leaseSeconds = result.lease_seconds;
    const leaseStartedEpoch = result.lease_started_epoch;
    const leaseExpiresEpoch = result.lease_expires_epoch;
    const leaseId = result.lease_id;
    const hostPort = result.host_port;
    const observedAtEpoch = Math.floor(Date.now() / 1_000);
    const leaseIdValid = typeof leaseId === "string" && /^[0-9a-f]{32}$/.test(leaseId);
    const hostPortValid = typeof hostPort === "number"
      && Number.isSafeInteger(hostPort)
      && hostPort >= 1_024
      && hostPort <= 65_535;
    const leaseReceiptValid = !(
      result.status !== "RUNNING"
      || typeof leaseSeconds !== "number"
      || !Number.isSafeInteger(leaseSeconds)
      || leaseSeconds !== Math.ceil(leaseDurationMs / 1_000)
      || typeof leaseStartedEpoch !== "number"
      || !Number.isSafeInteger(leaseStartedEpoch)
      || typeof leaseExpiresEpoch !== "number"
      || !Number.isSafeInteger(leaseExpiresEpoch)
      || leaseExpiresEpoch - leaseStartedEpoch !== leaseSeconds
      || leaseStartedEpoch > observedAtEpoch + 5
      || leaseExpiresEpoch <= observedAtEpoch
      || leaseExpiresEpoch - observedAtEpoch < leaseSeconds - 2
      || leaseExpiresEpoch > observedAtEpoch + leaseSeconds + 5
      || !leaseIdValid
      || !hostPortValid
    );
    if (!leaseReceiptValid) {
      let cleanupStatus: unknown;
      try {
        cleanupStatus = (await rootlessCommand(
          runner,
          [
            "stop",
            "--engine",
            runner.containerEngine ?? "",
            "--language",
            language,
            "--job-id",
            job.id,
            "--state",
            confined(jobRoot(runner, context, job.id), "runtime-state"),
            ...(leaseIdValid ? ["--lease-id", String(leaseId)] : []),
          ],
          60_000,
        )).status;
      } catch {
        cleanupStatus = "BLOCKED";
      }
      if (cleanupStatus === "SUPERSEDED") {
        job.runtime = {
          ...job.runtime,
          status: "BLOCKED",
          executor: "ROOTLESS_CONTAINER",
          language,
          containerName: String(result.container_name ?? ""),
          leaseId: leaseIdValid ? String(leaseId) : undefined,
          previewPort: undefined,
          updatedAt: new Date().toISOString(),
          plans: job.runtime.plans,
        };
        await persistRootlessStateDivergence(runner, context, job);
      } else if (cleanupStatus !== "STOPPED" && cleanupStatus !== "MISSING") {
        job.runtime = {
          ...job.runtime,
          status: "BLOCKED",
          executor: "ROOTLESS_CONTAINER",
          language,
          containerName: String(result.container_name ?? ""),
          leaseId: leaseIdValid ? String(leaseId) : undefined,
          previewPort: undefined,
          reason: "RUNTIME_LEASE_CLEANUP_FAILED",
          updatedAt: new Date().toISOString(),
          plans: job.runtime.plans,
        };
        log(job, "system", "An invalid rootless lease receipt could not be cleaned up and requires reconciliation.");
        await persist(runner, context, job);
      }
      throw new GenerationRunnerError(502, "ROOTLESS_RUNTIME_LEASE_RECEIPT_INVALID");
    }
    const verifiedLeaseSeconds = Number(leaseSeconds);
    const verifiedLeaseStartedEpoch = Number(leaseStartedEpoch);
    const verifiedLeaseExpiresEpoch = Number(leaseExpiresEpoch);
    const leaseStartedAt = new Date(verifiedLeaseStartedEpoch * 1_000);
    const leaseExpiresAt = new Date(verifiedLeaseExpiresEpoch * 1_000);
    job.runtime = {
      ...job.runtime,
      status: "RUNNING",
      executor: "ROOTLESS_CONTAINER",
      language,
      containerName: String(result.container_name ?? ""),
      previewPort: Number(hostPort),
      pid: undefined,
      reason: undefined,
      leaseStartedAt: leaseStartedAt.toISOString(),
      leaseExpiresAt: leaseExpiresAt.toISOString(),
      leaseDurationSeconds: verifiedLeaseSeconds,
      leaseId: String(leaseId),
      updatedAt: new Date().toISOString(),
    };
    activeRootlessRuntimes.add(key);
    log(
      job,
      "system",
      "Rootless runtime passed its loopback identity probe with a read-only filesystem, internal-only runtime network, dropped capabilities, and bounded resources.",
    );
    log(job, "system", `Browser preview lease expires at ${leaseExpiresAt.toISOString()}.`);
    await persist(runner, context, job);
    scheduleRuntimeLease(runner, context, job);
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
  job.runtime = {
    ...job.runtime,
    status: "STARTING",
    executor: "HOST_DEVELOPMENT",
    language,
    previewPort: plan.port,
    pid: child.pid,
    reason: undefined,
    leaseId: randomUUID().replaceAll("-", ""),
    leaseStartedAt: undefined,
    leaseExpiresAt: undefined,
    leaseDurationSeconds: undefined,
    updatedAt: new Date().toISOString(),
  };
  child.stdout?.on("data", (chunk: Buffer) => {
    log(job, "runtime", chunk.toString("utf-8"));
    void persist(runner, context, job);
  });
  child.stderr?.on("data", (chunk: Buffer) => {
    log(job, "runtime", chunk.toString("utf-8"));
    void persist(runner, context, job);
  });
  child.once("error", (error) => {
    if (activeRuntimes.get(key) !== child) return;
    clearRuntimeLeaseTimer(key);
    activeRuntimes.delete(key);
    job.runtime.status = "BLOCKED";
    job.runtime.reason = `RUNTIME_SPAWN_FAILED:${redact(error.message)}`;
    job.runtime.previewPort = undefined;
    job.runtime.pid = undefined;
    job.runtime.updatedAt = new Date().toISOString();
    void persist(runner, context, job);
  });
  child.once("close", (code) => {
    if (activeRuntimes.get(key) !== child) return;
    clearRuntimeLeaseTimer(key);
    activeRuntimes.delete(key);
    const intentionallyStopped = stoppedRuntimes.delete(key);
    const leaseExpired = expiredRuntimes.delete(key);
    const healthBlocked = job.runtime.status === "BLOCKED"
      && job.runtime.reason?.startsWith("RUNTIME_HEALTH_PROBE");
    if (leaseExpired) {
      job.runtime.status = "STOPPED";
      job.runtime.reason = "RUNTIME_LEASE_EXPIRED";
      if (!job.logs.some((entry) => entry.message.includes("Ten-minute browser runtime lease expired"))) {
        log(job, "system", "Ten-minute browser runtime lease expired and the runtime was stopped.");
      }
    } else if (intentionallyStopped) {
      job.runtime.status = "STOPPED";
      job.runtime.reason = "STOPPED_BY_AUTHORIZED_ACTOR";
      if (!job.logs.some((entry) => entry.message.includes("Runtime stopped by"))) {
        log(job, "system", "Runtime stopped by an authorized actor.");
      }
    } else if (!healthBlocked) {
      job.runtime.status = code === 0 ? "STOPPED" : "BLOCKED";
      job.runtime.reason = code === 0 ? undefined : `RUNTIME_EXIT_${code ?? "UNKNOWN"}`;
    }
    job.runtime.previewPort = undefined;
    job.runtime.pid = undefined;
    job.runtime.updatedAt = new Date().toISOString();
    void persist(runner, context, job);
  });
  await confirmRuntimeHealth(
    runner,
    context,
    job,
    child,
    key,
    plan.port,
    expectedService,
    leaseDurationMs,
  );
  await persist(runner, context, job);
  return job;
}

export async function startRuntime(
  context: AuthorizedContext,
  jobId: string,
  language: GenerationTargetId,
): Promise<GenerationJob> {
  if (!jobIdPattern.test(jobId)) throw new GenerationRunnerError(400, "JOB_ID_INVALID");
  const runner = config();
  const key = jobKey(context, jobId);
  return withRuntimeOperation(
    key,
    () => withDurableRuntimeOperation(
      runner,
      context,
      jobId,
      () => startRuntimeLocked(context, jobId, language),
    ),
  );
}

async function stopRuntimeLocked(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  const runner = config();
  const job = await load(runner, context, jobId, true);
  const key = jobKey(context, jobId);
  clearRuntimeLeaseTimer(key);
  expiredRuntimes.delete(key);
  if (job.runtime.executor === "ROOTLESS_CONTAINER" && job.runtime.language) {
    let cleanup: Record<string, unknown>;
    try {
      cleanup = await rootlessCommand(
        runner,
        [
          "stop",
          "--engine",
          runner.containerEngine ?? "",
          "--language",
          job.runtime.language,
          "--job-id",
          job.id,
          "--state",
          confined(jobRoot(runner, context, job.id), "runtime-state"),
          ...(job.runtime.leaseId ? ["--lease-id", job.runtime.leaseId] : []),
        ],
        60_000,
      );
    } catch (error) {
      job.runtime.status = "BLOCKED";
      job.runtime.reason = "RUNTIME_LEASE_CLEANUP_FAILED";
      job.runtime.updatedAt = new Date().toISOString();
      log(job, "system", "Rootless runtime cleanup failed and requires reconciliation.");
      await persist(runner, context, job);
      throw error;
    }
    if (cleanup.status === "SUPERSEDED") {
      await persistRootlessStateDivergence(runner, context, job);
      throw new GenerationRunnerError(409, "RUNTIME_LEASE_SUPERSEDED");
    }
    if (cleanup.status !== "STOPPED" && cleanup.status !== "MISSING") {
      job.runtime.status = "BLOCKED";
      job.runtime.previewPort = undefined;
      job.runtime.reason = "RUNTIME_LEASE_CLEANUP_FAILED";
      job.runtime.updatedAt = new Date().toISOString();
      log(job, "system", "Rootless runtime cleanup returned an unverified receipt.");
      await persist(runner, context, job);
      throw new GenerationRunnerError(502, "ROOTLESS_RUNTIME_CLEANUP_UNVERIFIED");
    }
    job.runtime.status = "STOPPED";
    job.runtime.previewPort = undefined;
    activeRootlessRuntimes.delete(key);
    job.runtime.pid = undefined;
    job.runtime.reason = "STOPPED_BY_AUTHORIZED_ACTOR";
    job.runtime.updatedAt = new Date().toISOString();
    log(job, "system", `Rootless runtime stopped by ${context.actor}.`);
    await persist(runner, context, job);
    return job;
  }
  const child = activeRuntimes.get(key);
  if (child) {
    stoppedRuntimes.add(key);
    await terminateAndWait(child);
  }
  job.runtime.status = "STOPPED";
  job.runtime.previewPort = undefined;
  job.runtime.pid = undefined;
  job.runtime.reason = "STOPPED_BY_AUTHORIZED_ACTOR";
  job.runtime.updatedAt = new Date().toISOString();
  log(job, "system", `Runtime stopped by ${context.actor}.`);
  await persist(runner, context, job);
  return job;
}

export async function stopRuntime(
  context: AuthorizedContext,
  jobId: string,
): Promise<GenerationJob> {
  if (!jobIdPattern.test(jobId)) throw new GenerationRunnerError(400, "JOB_ID_INVALID");
  const runner = config();
  const key = jobKey(context, jobId);
  return withRuntimeOperation(
    key,
    () => withDurableRuntimeOperation(
      runner,
      context,
      jobId,
      () => stopRuntimeLocked(context, jobId),
    ),
  );
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
      await assertProductionRuntimeReaper(runner);
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
