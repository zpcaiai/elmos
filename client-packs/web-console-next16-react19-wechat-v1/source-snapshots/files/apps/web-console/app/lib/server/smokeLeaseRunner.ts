import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { closeSync, constants as fsConstants, openSync } from "node:fs";
import { lstat, mkdir, open, readFile, readdir, realpath, rename, rm, rmdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import type { NextRequest } from "next/server";

import { authorize as authorizeLocalRunner, GenerationRunnerError } from "./generationRunner";
import type {
  SmokeCapabilityLocation,
  SmokeCapabilityResponse,
  SmokeCheckResult,
  SmokeEntry,
  SmokeEntryAvailability,
  SmokeEvidenceBundle,
  SmokeExecutionLocation,
  SmokePackSummary,
  SmokeSession,
  SmokeSessionState,
  SmokeTeardownReport,
} from "../smokeContracts";

/**
 * Console-side driver for ELMOS Batch 46 runnable smoke packs.
 *
 * The button in the console starts a *lease*, not a deployment: 10 minutes of
 * free runtime, after which the batch46 watchdog stops every service it started
 * and deletes the ephemeral data. This module never implements that policy
 * itself — it starts the pack's own vendored runner and reads the evidence that
 * runner writes, so the console and the CLI cannot drift apart.
 */

type AuthorizedContext = ReturnType<typeof authorizeLocalRunner>;

const FREE_QUOTA_SECONDS = 600;
const GRACE_SECONDS = 30;
const MIN_TTL_SECONDS = 60;
const MAX_EXTENSION_SECONDS = 1_800;
const MAX_ACTIVE_SESSIONS_DEFAULT = 3;
const LOG_TAIL_BYTES = 8_000;
const MAX_SNAPSHOT_FILE_BYTES = 2 * 1024 * 1024;

const projectRefPattern = /^[a-z0-9][a-z0-9._/-]{2,180}$/i;
const sessionIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const entries: SmokeEntry[] = ["script", "compose", "make", "zero-dep"];
const controlCharacters = /[\u0000-\u001f\u007f]/;

type StoredSession = {
  sessionId: string;
  tenantId: string;
  actor: string;
  projectRef: string;
  projectPath: string;
  entry: SmokeEntry;
  location: SmokeExecutionLocation;
  hostedRunId?: string;
  pid?: number;
  createdAt: string;
  requestedTtlSeconds: number;
};

function fail(status: number, code: string): never {
  throw new GenerationRunnerError(status, code);
}

function nowIso(): string {
  return new Date().toISOString();
}

/* ------------------------------------------------------------------ config */

function projectsRoot(): string {
  const configured = process.env.ELMOS_SMOKE_PROJECTS_ROOT;
  if (!configured) fail(503, "SMOKE_PROJECTS_ROOT_NOT_CONFIGURED");
  return path.resolve(configured);
}

function sessionsRoot(): string {
  const base = process.env.ELMOS_RUNTIME_STATE_DIR;
  if (!base) fail(503, "RUNTIME_STATE_DIR_NOT_CONFIGURED");
  return path.resolve(base, "smoke-sessions");
}

function pythonBinary(): string {
  return process.env.ELMOS_SMOKE_PYTHON ?? "python3";
}

function hostedEndpoint(): string | null {
  const endpoint = process.env.ELMOS_SMOKE_HOSTED_ENDPOINT;
  if (!endpoint) return null;
  try {
    const parsed = new URL(endpoint);
    return parsed.protocol === "https:" || parsed.hostname === "127.0.0.1" ? endpoint.replace(/\/$/, "") : null;
  } catch {
    return null;
  }
}

function maxActiveSessions(): number {
  const raw = Number.parseInt(process.env.ELMOS_SMOKE_MAX_ACTIVE_SESSIONS ?? "", 10);
  return Number.isInteger(raw) && raw > 0 && raw <= 20 ? raw : MAX_ACTIVE_SESSIONS_DEFAULT;
}

function confined(base: string, ...segments: string[]): string {
  const candidate = path.resolve(base, ...segments);
  if (candidate !== base && !candidate.startsWith(`${base}${path.sep}`)) {
    fail(400, "SMOKE_PATH_CONFINEMENT_FAILED");
  }
  return candidate;
}

function isMissing(error: unknown): boolean {
  return error instanceof Error && "code" in error && error.code === "ENOENT";
}

async function realConfined(base: string, ...segments: string[]): Promise<string | null> {
  const candidate = confined(base, ...segments);
  let resolved: string;
  try {
    resolved = await realpath(candidate);
  } catch (error) {
    if (isMissing(error)) return null;
    fail(409, "SMOKE_PATH_RESOLUTION_FAILED");
  }
  if (resolved !== base && !resolved.startsWith(`${base}${path.sep}`)) {
    fail(400, "SMOKE_PATH_CONFINEMENT_FAILED");
  }
  return resolved;
}

async function ensureConfinedDirectory(base: string, ...segments: string[]): Promise<string> {
  if (segments.length === 0) return base;
  const parentSegments = segments.slice(0, -1);
  const leaf = segments.at(-1)!;
  const parent = parentSegments.length ? await realConfined(base, ...parentSegments) : base;
  if (!parent) fail(409, "SMOKE_DIRECTORY_PARENT_MISSING");
  const candidate = confined(parent, leaf);
  try {
    const existing = await lstat(candidate);
    if (existing.isSymbolicLink() || !existing.isDirectory()) {
      fail(400, "SMOKE_PATH_CONFINEMENT_FAILED");
    }
  } catch (error) {
    if (!isMissing(error)) throw error;
    await mkdir(candidate, { mode: 0o700 });
  }
  const resolved = await realConfined(base, ...segments);
  if (!resolved) fail(409, "SMOKE_DIRECTORY_UNAVAILABLE");
  return resolved;
}

/* ---------------------------------------------------------------- authorize */

export function authorizeSmoke(request: NextRequest): AuthorizedContext {
  return authorizeLocalRunner(request, "generation:execute");
}

/* --------------------------------------------------------------- capability */

export function smokeCapability(): SmokeCapabilityResponse {
  const locations: SmokeCapabilityLocation[] = [];

  const endpoint = hostedEndpoint();
  if (!process.env.ELMOS_SMOKE_HOSTED_ENDPOINT) {
    locations.push({
      location: "HOSTED_RUNNER",
      status: "NOT_CONFIGURED",
      reason: "ELMOS_SMOKE_HOSTED_ENDPOINT 未配置；沙箱运行不可用",
    });
  } else if (!endpoint) {
    locations.push({
      location: "HOSTED_RUNNER",
      status: "BLOCKED",
      reason: "托管 Runner 端点必须是 https 或本机回环地址",
    });
  } else if (!process.env.ELMOS_SMOKE_HOSTED_TOKEN) {
    locations.push({
      location: "HOSTED_RUNNER",
      status: "BLOCKED",
      reason: "托管 Runner 已配置端点但缺少凭据",
    });
  } else {
    locations.push({ location: "HOSTED_RUNNER", status: "AVAILABLE" });
  }

  if (process.env.ELMOS_LOCAL_RUNNER_ENABLED !== "true") {
    locations.push({
      location: "LOCAL_WORKSTATION",
      status: "NOT_CONFIGURED",
      reason: "本机运行未启用（ELMOS_LOCAL_RUNNER_ENABLED != true）",
    });
  } else if (!process.env.ELMOS_SMOKE_PROJECTS_ROOT) {
    locations.push({
      location: "LOCAL_WORKSTATION",
      status: "BLOCKED",
      reason: "ELMOS_SMOKE_PROJECTS_ROOT 未配置，无法定位生成项目",
    });
  } else if (!process.env.ELMOS_RUNTIME_STATE_DIR) {
    locations.push({
      location: "LOCAL_WORKSTATION",
      status: "BLOCKED",
      reason: "ELMOS_RUNTIME_STATE_DIR 未配置，会话无法持久化",
    });
  } else {
    locations.push({ location: "LOCAL_WORKSTATION", status: "AVAILABLE" });
  }

  // Hosted first: the recipient needs no toolchain of their own. Local is the
  // fallback, not a downgrade — it is closer to how they will really run it.
  const preferred = locations.find((entry) => entry.status === "AVAILABLE")?.location ?? null;

  return {
    freeQuotaSeconds: FREE_QUOTA_SECONDS,
    graceSeconds: GRACE_SECONDS,
    autoRenew: false,
    extendPolicy: "EXPLICIT_ONLY",
    locations,
    preferredLocation: preferred,
    checkedAt: nowIso(),
  };
}

/* --------------------------------------------------------------- pack facts */

async function readJson(file: string): Promise<Record<string, unknown> | null> {
  try {
    return JSON.parse(await readFile(file, "utf-8")) as Record<string, unknown>;
  } catch {
    return null;
  }
}

async function readProjectJson(
  projectPath: string,
  ...segments: string[]
): Promise<Record<string, unknown> | null> {
  const file = await realConfined(projectPath, ...segments);
  return file ? await readJson(file) : null;
}

async function resolveProject(projectRef: string): Promise<string> {
  if (!projectRefPattern.test(projectRef) || projectRef.includes("..")) {
    fail(400, "SMOKE_PROJECT_REF_INVALID");
  }
  let root: string;
  try {
    root = await realpath(projectsRoot());
  } catch {
    fail(503, "SMOKE_PROJECTS_ROOT_UNAVAILABLE");
  }
  const resolved = await realConfined(root, projectRef);
  if (!resolved) fail(404, "SMOKE_PACK_NOT_FOUND");
  return resolved;
}

export async function smokePackSummary(projectRef: string): Promise<SmokePackSummary> {
  const projectPath = await resolveProject(projectRef);
  const pack = await readProjectJson(projectPath, "smoke", "pack.json");
  const runner = await readProjectJson(projectPath, "smoke", "runner-manifest.json");
  if (!pack || !runner) fail(404, "SMOKE_PACK_NOT_FOUND");

  const manifestEntries = (runner.entries ?? {}) as Record<string, Record<string, unknown>>;
  const availability: SmokeEntryAvailability[] = entries.map((entry) => {
    const declared = manifestEntries[entry] ?? {};
    return {
      entry,
      status: declared.status === "available" ? "available" : "unavailable",
      command: typeof declared.command === "string" ? declared.command : undefined,
      reason: typeof declared.reason === "string" ? declared.reason : undefined,
      semanticWarning:
        typeof declared.semantic_warning === "string" ? declared.semantic_warning : undefined,
    };
  });

  return {
    projectRef,
    languages: Array.isArray(pack.languages) ? (pack.languages as string[]) : [],
    frameworks: Array.isArray(pack.frameworks) ? (pack.frameworks as string[]) : [],
    datastores: Array.isArray(pack.datastores) ? (pack.datastores as string[]) : [],
    entries: availability,
    defaultEntry: (pack.default_entry as SmokeEntry | null) ?? null,
    unknownCount: Array.isArray(pack.unknown) ? pack.unknown.length : 0,
  };
}

/* ----------------------------------------------------------- session store */

async function writeSession(stored: StoredSession): Promise<void> {
  const root = sessionsRoot();
  await mkdir(root, { recursive: true });
  const target = confined(root, `${stored.sessionId}.json`);
  const staging = `${target}.tmp`;
  await writeFile(staging, JSON.stringify(stored, null, 2), "utf-8");
  await rename(staging, target);
}

async function loadSession(context: AuthorizedContext, sessionId: string): Promise<StoredSession> {
  if (!sessionIdPattern.test(sessionId)) fail(400, "SMOKE_SESSION_ID_INVALID");
  const stored = (await readJson(confined(sessionsRoot(), `${sessionId}.json`))) as StoredSession | null;
  if (!stored) fail(404, "SMOKE_SESSION_NOT_FOUND");
  if (stored.tenantId !== context.tenantId) fail(404, "SMOKE_SESSION_NOT_FOUND");
  if (
    typeof stored.projectRef !== "string"
    || typeof stored.projectPath !== "string"
    || !entries.includes(stored.entry)
    || !["LOCAL_WORKSTATION", "HOSTED_RUNNER"].includes(stored.location)
  ) {
    fail(409, "SMOKE_SESSION_RECORD_INVALID");
  }
  const resolvedProject = await resolveProject(stored.projectRef);
  if (stored.projectPath !== resolvedProject) fail(409, "SMOKE_SESSION_PROJECT_BINDING_INVALID");
  return stored;
}

function snapshotRoot(sessionId: string): string {
  if (!sessionIdPattern.test(sessionId)) fail(400, "SMOKE_SESSION_ID_INVALID");
  return confined(sessionsRoot(), "evidence", sessionId);
}

async function snapshotExists(sessionId: string): Promise<boolean> {
  try {
    return (await stat(confined(snapshotRoot(sessionId), "snapshot.json"))).isFile();
  } catch {
    return false;
  }
}

const runtimeJsonFiles = [
  "status.json",
  "lease.json",
  "lease-result.json",
  "result.json",
  "gate-result.json",
] as const;
const runtimeLogFiles = [
  "app.stdout.log",
  "app.stderr.log",
  "console-run.log",
  "compose.log",
  "install.log",
] as const;

async function snapshotFile(
  source: string | null,
  target: string,
  captureTail = false,
): Promise<{ size: number; sourceSize: number; sha256: string } | null> {
  if (!source) return null;
  try {
    const handle = await open(source, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
    try {
      const info = await handle.stat();
      if (!info.isFile()) return null;
      if (info.size > MAX_SNAPSHOT_FILE_BYTES && !captureTail) {
        fail(413, "SMOKE_SNAPSHOT_FILE_TOO_LARGE");
      }
      let bytes: Buffer;
      if (info.size > MAX_SNAPSHOT_FILE_BYTES) {
        bytes = Buffer.alloc(MAX_SNAPSHOT_FILE_BYTES);
        const read = await handle.read(bytes, 0, bytes.byteLength, info.size - bytes.byteLength);
        bytes = bytes.subarray(0, read.bytesRead);
      } else {
        bytes = await handle.readFile();
      }
      await writeFile(target, bytes, { mode: 0o600 });
      return {
        size: bytes.byteLength,
        sourceSize: info.size,
        sha256: createHash("sha256").update(bytes).digest("hex"),
      };
    } finally {
      await handle.close();
    }
  } catch (error) {
    if (isMissing(error)) return null;
    throw error;
  }
}

async function snapshotCompletedRuntime(stored: StoredSession): Promise<boolean> {
  if (await snapshotExists(stored.sessionId)) return true;
  const sourceRuntime = await realConfined(stored.projectPath, "smoke", "runtime");
  if (!sourceRuntime) return false;
  const status = await readJson(confined(sourceRuntime, "status.json"));
  const state = String(status?.state ?? "STARTING");
  if (["STARTING", "RUNNING", "READY", "HOLDING"].includes(state)) return false;
  for (const required of ["result.json", "lease-result.json", "gate-result.json"]) {
    if (!await realConfined(sourceRuntime, required)) return false;
  }

  const root = snapshotRoot(stored.sessionId);
  const logs = confined(root, "logs");
  await mkdir(logs, { recursive: true, mode: 0o700 });
  const files: Record<string, { size: number; sourceSize: number; sha256: string }> = {};
  for (const name of runtimeJsonFiles) {
    const captured = await snapshotFile(await realConfined(sourceRuntime, name), confined(root, name));
    if (captured) files[name] = captured;
  }
  for (const name of runtimeLogFiles) {
    const captured = await snapshotFile(
      await realConfined(sourceRuntime, "logs", name),
      confined(logs, name),
      true,
    );
    if (captured) files[`logs/${name}`] = captured;
  }
  await writeFile(
    confined(root, "snapshot.json"),
    JSON.stringify({
      sessionId: stored.sessionId,
      projectPath: stored.projectPath,
      capturedAt: nowIso(),
      files,
    }, null, 2),
    { mode: 0o600 },
  );
  return true;
}

async function runtimeFile(stored: StoredSession, ...segments: string[]): Promise<string | null> {
  if (await snapshotExists(stored.sessionId)) {
    const root = await realpath(snapshotRoot(stored.sessionId));
    const relative = segments.join("/");
    const manifest = await readJson(confined(root, "snapshot.json"));
    if (
      !manifest
      || manifest.sessionId !== stored.sessionId
      || manifest.projectPath !== stored.projectPath
      || typeof manifest.files !== "object"
      || manifest.files === null
    ) {
      fail(409, "SMOKE_SNAPSHOT_INTEGRITY_FAILED");
    }
    const declared = (manifest?.files as Record<string, { size?: unknown; sha256?: unknown }> | undefined)?.[relative];
    if (!declared) return null;
    const file = await realConfined(root, ...segments);
    if (!file) fail(409, "SMOKE_SNAPSHOT_INTEGRITY_FAILED");
    const bytes = await readFile(file);
    const digest = createHash("sha256").update(bytes).digest("hex");
    if (declared.size !== bytes.byteLength || declared.sha256 !== digest) {
      fail(409, "SMOKE_SNAPSHOT_INTEGRITY_FAILED");
    }
    return file;
  }
  return await realConfined(stored.projectPath, "smoke", "runtime", ...segments);
}

async function readRuntimeJson(
  stored: StoredSession,
  ...segments: string[]
): Promise<Record<string, unknown> | null> {
  const file = await runtimeFile(stored, ...segments);
  return file ? await readJson(file) : null;
}

async function prepareProjectRuntime(projectPath: string): Promise<void> {
  let names: string[] = [];
  let ownedCurrentRuntime = false;
  try {
    names = await readdir(sessionsRoot());
  } catch {
    // First run has no session store yet.
  }
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    const stored = (await readJson(confined(sessionsRoot(), name))) as StoredSession | null;
    if (!stored || stored.projectPath !== projectPath || stored.location !== "LOCAL_WORKSTATION") continue;
    ownedCurrentRuntime = true;
    if (await snapshotExists(stored.sessionId)) continue;
    const status = await readProjectJson(projectPath, "smoke", "runtime", "status.json");
    const state = String(status?.state ?? "STARTING");
    if (["STARTING", "RUNNING", "READY", "HOLDING"].includes(state)) {
      fail(409, "SMOKE_PROJECT_ALREADY_RUNNING");
    }
    if (!await snapshotCompletedRuntime(stored)) {
      fail(409, "SMOKE_RUNTIME_FINALIZATION_IN_PROGRESS");
    }
  }

  if (!ownedCurrentRuntime) {
    for (const name of runtimeJsonFiles) {
      if (await realConfined(projectPath, "smoke", "runtime", name)) {
        fail(409, "SMOKE_UNOWNED_RUNTIME_PRESENT");
      }
    }
  }

  // A new run must never inherit a previous run's terminal status, result,
  // gate, or logs. Historical bytes have been copied to the session snapshot.
  for (const name of runtimeJsonFiles) {
    const file = await realConfined(projectPath, "smoke", "runtime", name);
    if (file) await rm(file, { force: true });
  }
  for (const name of runtimeLogFiles) {
    const file = await realConfined(projectPath, "smoke", "runtime", "logs", name);
    if (file) await rm(file, { force: true });
  }
}

async function activeSessionCount(tenantId: string): Promise<number> {
  let names: string[];
  try {
    names = await readdir(sessionsRoot());
  } catch {
    return 0;
  }
  let active = 0;
  for (const name of names) {
    if (!name.endsWith(".json")) continue;
    const stored = (await readJson(path.join(sessionsRoot(), name))) as StoredSession | null;
    if (!stored || stored.tenantId !== tenantId) continue;
    let resolvedProject: string;
    try {
      resolvedProject = await resolveProject(stored.projectRef);
    } catch {
      // A corrupt or removed session must consume quota until an operator
      // reconciles it; treating it as inactive would permit quota bypass.
      active += 1;
      continue;
    }
    if (resolvedProject !== stored.projectPath) {
      active += 1;
      continue;
    }
    let state = "STARTING";
    if (stored.location === "HOSTED_RUNNER") {
      try {
        const hosted = await hostedRequest("GET", `/smoke-runs/${stored.hostedRunId}`);
        state = String(hosted.state ?? "STARTING");
      } catch {
        // An unreachable hosted runner is not evidence that quota was released.
        active += 1;
        continue;
      }
    } else {
      const status = await readRuntimeJson(stored, "status.json");
      state = String(status?.state ?? "STARTING");
    }
    if (["STARTING", "RUNNING", "READY", "HOLDING"].includes(state)) active += 1;
  }
  return active;
}

/* -------------------------------------------------------------- local run */

async function spawnLocalRun(stored: StoredSession, ttlSeconds: number): Promise<number> {
  const runner = await realConfined(stored.projectPath, "smoke", "tools", "run_smoke.py");
  if (!runner) fail(409, "SMOKE_RUNNER_NOT_VENDORED");
  await ensureConfinedDirectory(stored.projectPath, "smoke", "runtime");
  const realLogsDir = await ensureConfinedDirectory(stored.projectPath, "smoke", "runtime", "logs");
  const consoleLog = openSync(
    confined(realLogsDir, "console-run.log"),
    fsConstants.O_TRUNC | fsConstants.O_CREAT | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW,
    0o600,
  );

  const argv = [
    runner,
    "--project", stored.projectPath,
    "--entry", stored.entry,
    "--ttl", String(ttlSeconds),
  ];
  // Environments that pre-provision the toolchain (CI, a prepared sandbox image)
  // skip the install step; everywhere else the install is part of proving the
  // project starts from a clean checkout.
  if (process.env.ELMOS_SMOKE_SKIP_INSTALL === "true") argv.push("--no-install");

  // The runner is vendored inside an operator-mounted project root and is not
  // a Web Console build input. Tracing this dynamic path would copy the whole
  // repository into the Next server artifact.
  let child: ReturnType<typeof spawn>;
  try {
    child = spawn(/*turbopackIgnore: true*/
      pythonBinary(),
      argv,
      {
        cwd: stored.projectPath,
        detached: true,
        env: { ...process.env, ELMOS_SMOKE_CONSOLE_SESSION_ID: stored.sessionId },
        stdio: ["ignore", consoleLog, consoleLog],
      },
    );
  } finally {
    closeSync(consoleLog);
  }
  if (!child.pid) fail(500, "SMOKE_RUN_SPAWN_FAILED");
  // Detach: the lease watchdog owns the run's lifetime, not this request and not
  // a console restart. Teardown still happens because the watchdog lives in the
  // spawned process, and `stop` can reach it through the pack's own CLI.
  child.unref();
  return child.pid;
}

async function runLeaseCommand(stored: StoredSession, args: string[]): Promise<{ code: number; stderr: string }> {
  const lease = await realConfined(stored.projectPath, "smoke", "tools", "smoke_lease.py");
  if (!lease) return { code: 1, stderr: "SMOKE_LEASE_CLI_UNAVAILABLE" };
  return await new Promise((resolve) => {
    // Like run_smoke.py above, smoke_lease.py is validated at request time in
    // the confined mounted project. It must not expand the Next build trace.
    const child = spawn(/*turbopackIgnore: true*/ pythonBinary(), [lease, ...args], {
      cwd: stored.projectPath,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stderr = "";
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr = `${stderr}${chunk.toString("utf-8")}`.slice(-4_000);
    });
    child.on("error", () => resolve({ code: 1, stderr: "SMOKE_LEASE_CLI_UNAVAILABLE" }));
    child.on("close", (code) => resolve({ code: code ?? 1, stderr }));
  });
}

/* ------------------------------------------------------------- hosted run */

async function hostedRequest(
  method: "GET" | "POST",
  suffix: string,
  body?: unknown,
): Promise<Record<string, unknown>> {
  const endpoint = hostedEndpoint();
  const token = process.env.ELMOS_SMOKE_HOSTED_TOKEN;
  if (!endpoint || !token) fail(503, "SMOKE_HOSTED_RUNNER_NOT_CONFIGURED");
  let response: Response;
  try {
    response = await fetch(`${endpoint}${suffix}`, {
      method,
      headers: {
        authorization: `Bearer ${token}`,
        ...(body ? { "content-type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    fail(503, "SMOKE_HOSTED_RUNNER_UNREACHABLE");
  }
  if (!response.ok) fail(response.status === 404 ? 404 : 502, "SMOKE_HOSTED_RUNNER_REJECTED");
  return (await response.json()) as Record<string, unknown>;
}

/* ------------------------------------------------------------------ create */

export async function createSmokeSession(
  context: AuthorizedContext,
  payload: unknown,
): Promise<SmokeSession> {
  const body = (payload ?? {}) as Record<string, unknown>;
  const projectRef = typeof body.projectRef === "string" ? body.projectRef : "";
  const projectPath = await resolveProject(projectRef);

  const summary = await smokePackSummary(projectRef);
  const requestedEntry = typeof body.entry === "string" ? (body.entry as SmokeEntry) : null;
  const entry = requestedEntry ?? summary.defaultEntry;
  if (!entry || !entries.includes(entry)) fail(400, "SMOKE_ENTRY_INVALID");
  const declared = summary.entries.find((item) => item.entry === entry);
  if (!declared || declared.status !== "available") {
    // The pack itself already decided this; the console must not override it.
    throw new GenerationRunnerError(409, `SMOKE_ENTRY_UNAVAILABLE:${declared?.reason ?? "unknown"}`);
  }

  const capability = smokeCapability();
  const requestedLocation = typeof body.location === "string" ? (body.location as SmokeExecutionLocation) : null;
  const location = requestedLocation ?? capability.preferredLocation;
  if (!location) fail(503, "SMOKE_NO_EXECUTION_LOCATION_AVAILABLE");
  const locationState = capability.locations.find((item) => item.location === location);
  if (!locationState || locationState.status !== "AVAILABLE") {
    throw new GenerationRunnerError(503, `SMOKE_LOCATION_UNAVAILABLE:${locationState?.reason ?? "unknown"}`);
  }

  const requestedTtl = Number.isInteger(body.ttlSeconds) ? (body.ttlSeconds as number) : FREE_QUOTA_SECONDS;
  // The free quota is a ceiling the client cannot raise. Shortening is allowed.
  const ttlSeconds = Math.min(Math.max(requestedTtl, MIN_TTL_SECONDS), FREE_QUOTA_SECONDS);

  const sessionRoot = sessionsRoot();
  await mkdir(sessionRoot, { recursive: true, mode: 0o700 });
  const tenantLock = confined(
    sessionRoot,
    `.create-${createHash("sha256").update(context.tenantId).digest("hex")}.lock`,
  );
  try {
    await mkdir(tenantLock, { mode: 0o700 });
  } catch (error) {
    if (error instanceof Error && "code" in error && error.code === "EEXIST") {
      fail(429, "SMOKE_SESSION_CREATE_IN_PROGRESS");
    }
    fail(503, "SMOKE_SESSION_LOCK_UNAVAILABLE");
  }

  let projectLock: string | null = null;
  try {
    projectLock = confined(
      sessionRoot,
      `.project-${createHash("sha256").update(projectPath).digest("hex")}.lock`,
    );
    try {
      await mkdir(projectLock, { mode: 0o700 });
    } catch (error) {
      if (error instanceof Error && "code" in error && error.code === "EEXIST") {
        fail(429, "SMOKE_PROJECT_CREATE_IN_PROGRESS");
      }
      fail(503, "SMOKE_PROJECT_LOCK_UNAVAILABLE");
    }

    if (await activeSessionCount(context.tenantId) >= maxActiveSessions()) {
      fail(429, "SMOKE_ACTIVE_SESSION_LIMIT_REACHED");
    }
    if (location === "LOCAL_WORKSTATION") await prepareProjectRuntime(projectPath);

    const stored: StoredSession = {
      sessionId: randomUUID(),
      tenantId: context.tenantId,
      actor: context.actor,
      projectRef,
      projectPath,
      entry,
      location,
      createdAt: nowIso(),
      requestedTtlSeconds: ttlSeconds,
    };

    if (location === "LOCAL_WORKSTATION") {
      stored.pid = await spawnLocalRun(stored, ttlSeconds);
    } else {
      const hosted = await hostedRequest("POST", "/smoke-runs", {
        projectRef,
        entry,
        ttlSeconds,
        freeQuotaSeconds: FREE_QUOTA_SECONDS,
        tenantId: context.tenantId,
      });
      const runId = hosted.runId;
      if (typeof runId !== "string") fail(502, "SMOKE_HOSTED_RUN_ID_MISSING");
      stored.hostedRunId = runId;
    }

    try {
      await writeSession(stored);
    } catch {
      if (stored.location === "LOCAL_WORKSTATION") {
        await runLeaseCommand(stored, ["stop", "--project", stored.projectPath, "--reason", "session-store-failed"]);
      } else if (stored.hostedRunId) {
        await hostedRequest("POST", `/smoke-runs/${stored.hostedRunId}/stop`, { reason: "session-store-failed" });
      }
      fail(503, "SMOKE_SESSION_STORE_FAILED");
    }
    return await readSmokeSession(context, stored.sessionId);
  } finally {
    if (projectLock) {
      try {
        await rmdir(projectLock);
      } catch {
        // Same recovery rule as the tenant lock below.
      }
    }
    try {
      await rmdir(tenantLock);
    } catch {
      // The lock is an empty, process-owned directory. If an operator removed
      // it during recovery there is nothing left to release; any unexpected
      // content is intentionally not deleted recursively.
    }
  }
}

/* -------------------------------------------------------------------- read */

function toChecks(raw: unknown): SmokeCheckResult[] {
  if (!Array.isArray(raw)) return [];
  return raw.slice(0, 30).map((item) => {
    const check = item as Record<string, unknown>;
    return {
      id: String(check.id ?? "unknown"),
      status: (check.status === "PASS" || check.status === "FAIL" ? check.status : "NOT_RUN") as
        SmokeCheckResult["status"],
      detail: String(check.detail ?? ""),
      required: check.required === true,
    };
  });
}

function toTeardown(lease: Record<string, unknown> | null): SmokeTeardownReport | null {
  const raw = lease?.teardown as Record<string, unknown> | undefined;
  if (!raw) return null;
  const processes = Array.isArray(raw.processes) ? raw.processes : [];
  const compose = Array.isArray(raw.compose) ? raw.compose : [];
  const removed = Array.isArray(raw.removed_paths) ? raw.removed_paths : [];
  return {
    reason: String(raw.reason ?? "unknown"),
    stoppedAt: typeof raw.stopped_at === "string" ? raw.stopped_at : undefined,
    processes: processes.map((item) => {
      const entry = item as Record<string, unknown>;
      return {
        pid: Number(entry.pid ?? 0),
        graceful: entry.graceful === true,
        killed: entry.killed === true,
        exitCode: typeof entry.exit_code === "number" ? entry.exit_code : null,
      };
    }),
    compose: compose.map((item) => {
      const entry = item as Record<string, unknown>;
      return {
        composeFile: String(entry.compose_file ?? ""),
        status: String(entry.status ?? "unknown"),
        reason: typeof entry.reason === "string" ? entry.reason : undefined,
      };
    }),
    removedPaths: removed.map((item) => {
      const entry = item as Record<string, unknown>;
      return { path: String(entry.path ?? ""), removed: String(entry.removed ?? "unknown") };
    }),
    complete: lease?.teardown_complete === true,
  };
}

export async function readSmokeSession(
  context: AuthorizedContext,
  sessionId: string,
): Promise<SmokeSession> {
  const stored = await loadSession(context, sessionId);

  if (stored.location === "HOSTED_RUNNER") {
    const hosted = await hostedRequest("GET", `/smoke-runs/${stored.hostedRunId}`);
    return normalizeHosted(stored, hosted);
  }

  const status = await readRuntimeJson(stored, "status.json");
  const lease = await readRuntimeJson(stored, "lease.json");
  const result = await readRuntimeJson(stored, "result.json");
  const gate = await readRuntimeJson(stored, "gate-result.json");

  const expiresAtEpoch = typeof lease?.expires_at_epoch === "number" ? lease.expires_at_epoch : null;
  const state = ((status?.state as SmokeSessionState) ?? "STARTING") as SmokeSessionState;
  const live = ["STARTING", "RUNNING", "READY", "HOLDING"].includes(state);
  const remaining = live && expiresAtEpoch ? Math.max(0, expiresAtEpoch * 1000 - Date.now()) / 1000 : 0;

  const extensionsRaw = Array.isArray(lease?.extensions) ? lease.extensions : [];

  const response: SmokeSession = {
    sessionId: stored.sessionId,
    projectRef: stored.projectRef,
    entry: stored.entry,
    location: stored.location,
    // A live state with an exhausted clock has not been reconciled by the
    // watchdog yet; report it as expiring rather than as still running.
    state: live && remaining <= 0 ? "EXPIRED" : state,
    url: typeof status?.url === "string" ? status.url : null,
    createdAt: stored.createdAt,
    updatedAt: typeof status?.updated_at === "string" ? status.updated_at : stored.createdAt,
    freeQuotaSeconds: FREE_QUOTA_SECONDS,
    ttlSeconds: typeof lease?.ttl_seconds === "number" ? lease.ttl_seconds : stored.requestedTtlSeconds,
    billableSeconds: typeof lease?.billable_seconds === "number" ? lease.billable_seconds : 0,
    remainingSeconds: Math.round(remaining),
    expiresAtEpoch,
    checks: toChecks(status?.checks ?? result?.checks),
    notes: Array.isArray(status?.notes) ? (status.notes as string[]).slice(0, 20) : [],
    extensions: extensionsRaw.slice(0, 20).map((item) => {
      const entry = item as Record<string, unknown>;
      return {
        grantedAt: String(entry.granted_at ?? ""),
        seconds: Number(entry.seconds ?? 0),
        reason: String(entry.reason ?? ""),
        actor: String(entry.actor ?? ""),
        beyondFreeQuota: entry.beyond_free_quota === true,
      };
    }),
    teardown: toTeardown(lease),
    gateStatus: (gate?.status as SmokeSession["gateStatus"]) ?? "NOT_RUN",
    gateFailures: Array.isArray(gate?.failures) ? (gate.failures as string[]).slice(0, 20) : [],
    gateLimitations: Array.isArray(gate?.limitations) ? (gate.limitations as string[]).slice(0, 20) : [],
    evidenceAvailable: Boolean(result),
  };
  if (!["STARTING", "RUNNING", "READY", "HOLDING"].includes(response.state)) {
    await snapshotCompletedRuntime(stored);
  }
  return response;
}

function normalizeHosted(stored: StoredSession, hosted: Record<string, unknown>): SmokeSession {
  const remaining = typeof hosted.remainingSeconds === "number" ? hosted.remainingSeconds : 0;
  return {
    sessionId: stored.sessionId,
    projectRef: stored.projectRef,
    entry: stored.entry,
    location: "HOSTED_RUNNER",
    state: ((hosted.state as SmokeSessionState) ?? "STARTING"),
    url: typeof hosted.url === "string" ? hosted.url : null,
    createdAt: stored.createdAt,
    updatedAt: typeof hosted.updatedAt === "string" ? hosted.updatedAt : nowIso(),
    freeQuotaSeconds: FREE_QUOTA_SECONDS,
    ttlSeconds: typeof hosted.ttlSeconds === "number" ? hosted.ttlSeconds : stored.requestedTtlSeconds,
    billableSeconds: typeof hosted.billableSeconds === "number" ? hosted.billableSeconds : 0,
    remainingSeconds: Math.max(0, Math.round(remaining)),
    expiresAtEpoch: typeof hosted.expiresAtEpoch === "number" ? hosted.expiresAtEpoch : null,
    checks: toChecks(hosted.checks),
    notes: Array.isArray(hosted.notes) ? (hosted.notes as string[]).slice(0, 20) : [],
    extensions: [],
    teardown: toTeardown(hosted.lease as Record<string, unknown> | null),
    gateStatus: (hosted.gateStatus as SmokeSession["gateStatus"]) ?? "NOT_RUN",
    gateFailures: Array.isArray(hosted.gateFailures) ? (hosted.gateFailures as string[]) : [],
    gateLimitations: Array.isArray(hosted.gateLimitations) ? (hosted.gateLimitations as string[]) : [],
    evidenceAvailable: hosted.evidenceAvailable === true,
  };
}

/* ------------------------------------------------------------------ extend */

function sanitizeText(value: unknown, field: string, max: number): string {
  if (typeof value !== "string") fail(400, `SMOKE_${field}_REQUIRED`);
  const trimmed = value.trim();
  if (trimmed.length < 4 || trimmed.length > max || controlCharacters.test(trimmed)) {
    fail(400, `SMOKE_${field}_INVALID`);
  }
  return trimmed;
}

async function assertCurrentLocalLease(stored: StoredSession): Promise<void> {
  if (await snapshotExists(stored.sessionId)) fail(409, "SMOKE_SESSION_NOT_ACTIVE");
  let lease: Record<string, unknown> | null = null;
  const deadline = Date.now() + 2_000;
  while (!lease && Date.now() < deadline) {
    lease = await readProjectJson(stored.projectPath, "smoke", "runtime", "lease.json");
    if (!lease) await new Promise((resolve) => setTimeout(resolve, 50));
  }
  if (!lease) fail(409, "SMOKE_LEASE_NOT_READY");
  if (lease.console_session_id !== stored.sessionId) {
    fail(409, "SMOKE_SESSION_LEASE_BINDING_INVALID");
  }
  if (lease.state !== "active") fail(409, "SMOKE_SESSION_NOT_ACTIVE");
}

export async function extendSmokeSession(
  context: AuthorizedContext,
  sessionId: string,
  payload: unknown,
): Promise<SmokeSession> {
  const body = (payload ?? {}) as Record<string, unknown>;
  const seconds = Number.isInteger(body.seconds) ? (body.seconds as number) : 0;
  if (seconds < MIN_TTL_SECONDS || seconds > MAX_EXTENSION_SECONDS) fail(400, "SMOKE_EXTENSION_SECONDS_INVALID");
  // Extension is an attributable decision, not a checkbox.
  const reason = sanitizeText(body.reason, "REASON", 240);
  const actor = sanitizeText(body.actor ?? context.actor, "ACTOR", 120);

  const stored = await loadSession(context, sessionId);
  if (stored.location === "HOSTED_RUNNER") {
    await hostedRequest("POST", `/smoke-runs/${stored.hostedRunId}/extend`, { seconds, reason, actor });
    return await readSmokeSession(context, sessionId);
  }
  await assertCurrentLocalLease(stored);
  const outcome = await runLeaseCommand(stored, [
    "extend", "--project", stored.projectPath,
    "--seconds", String(seconds), "--reason", reason, "--actor", actor,
  ]);
  if (outcome.code !== 0) {
    throw new GenerationRunnerError(409, `SMOKE_EXTENSION_REJECTED:${outcome.stderr.trim().slice(0, 160)}`);
  }
  return await readSmokeSession(context, sessionId);
}

/* -------------------------------------------------------------------- stop */

export async function stopSmokeSession(
  context: AuthorizedContext,
  sessionId: string,
  payload: unknown,
): Promise<SmokeSession> {
  const body = (payload ?? {}) as Record<string, unknown>;
  const reason = typeof body.reason === "string" && !controlCharacters.test(body.reason)
    ? body.reason.trim().slice(0, 120) || "manual"
    : "manual";
  const stored = await loadSession(context, sessionId);
  if (stored.location === "HOSTED_RUNNER") {
    await hostedRequest("POST", `/smoke-runs/${stored.hostedRunId}/stop`, { reason });
    return await readSmokeSession(context, sessionId);
  }
  if (await snapshotExists(stored.sessionId)) return await readSmokeSession(context, sessionId);
  await assertCurrentLocalLease(stored);
  const outcome = await runLeaseCommand(stored, ["stop", "--project", stored.projectPath, "--reason", reason]);
  if (outcome.code !== 0) {
    throw new GenerationRunnerError(409, `SMOKE_STOP_REJECTED:${outcome.stderr.trim().slice(0, 160)}`);
  }
  return await readSmokeSession(context, sessionId);
}

/* ---------------------------------------------------------------- evidence */

async function logTail(
  stored: StoredSession,
  name: string,
): Promise<{ name: string; bytes: number; tail: string } | null> {
  try {
    const file = await runtimeFile(stored, "logs", name);
    if (!file) return null;
    // `file` is runtime evidence below a request-time realpath confinement
    // boundary, not a build input. Do not make Turbopack trace the mounted
    // project (and potentially the whole repository) into the server bundle.
    const info = await stat(/*turbopackIgnore: true*/ file);
    const content = await readFile(/*turbopackIgnore: true*/ file, "utf-8");
    let sourceBytes = info.size;
    if (await snapshotExists(stored.sessionId)) {
      const manifest = await readJson(confined(snapshotRoot(stored.sessionId), "snapshot.json"));
      const declared = (manifest?.files as Record<string, { sourceSize?: unknown }> | undefined)?.[`logs/${name}`];
      if (typeof declared?.sourceSize === "number") sourceBytes = declared.sourceSize;
    }
    return { name, bytes: sourceBytes, tail: content.slice(-LOG_TAIL_BYTES) };
  } catch {
    return null;
  }
}

export async function smokeSessionEvidence(
  context: AuthorizedContext,
  sessionId: string,
): Promise<SmokeEvidenceBundle> {
  const stored = await loadSession(context, sessionId);
  if (stored.location === "HOSTED_RUNNER") {
    const hosted = await hostedRequest("GET", `/smoke-runs/${stored.hostedRunId}/evidence`);
    return {
      sessionId,
      result: hosted.result ?? null,
      gate: hosted.gate ?? null,
      lease: hosted.lease ?? null,
      logs: Array.isArray(hosted.logs) ? (hosted.logs as SmokeEvidenceBundle["logs"]) : [],
      retainedAfterExpiry: true,
    };
  }
  const logs = (
    await Promise.all([
      logTail(stored, "app.stdout.log"),
      logTail(stored, "app.stderr.log"),
      logTail(stored, "console-run.log"),
      logTail(stored, "compose.log"),
    ])
  ).filter((entry): entry is { name: string; bytes: number; tail: string } => entry !== null);

  return {
    sessionId,
    // Services are reclaimed at expiry; the evidence they produced is not.
    result: await readRuntimeJson(stored, "result.json"),
    gate: await readRuntimeJson(stored, "gate-result.json"),
    lease: await readRuntimeJson(stored, "lease-result.json"),
    logs,
    retainedAfterExpiry: true,
  };
}
