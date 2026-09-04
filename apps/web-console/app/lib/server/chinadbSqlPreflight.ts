import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import type { NextRequest } from "next/server";

import {
  bindChinaDbSqlRequestToCapabilities,
  ChinaDbSqlPolicyError,
  chinaDbSqlResponseLimitBytes,
  parseChinaDbSqlCapabilities,
  parseChinaDbSqlPreflightResult,
  type ChinaDbSqlCapabilities,
  type ChinaDbSqlPreflightRequest,
  type ChinaDbSqlPreflightResult,
} from "../chinadbSqlContracts";
import {
  AccountSessionError,
  accountSessionFromRequest,
  type AccountPermission,
} from "./accountSession";
import {
  isChinaDbSqlPreflightEnabled,
  resolveChinaDbSqlPreflightBaseUrl,
} from "./chinadbSqlUpstreamPolicy";
import { parseStrictJson } from "./strictJson";

const CAPABILITIES_PATH = "/api/v1/database-data/sql-preflight/capabilities";
const ASSESS_PATH = "/api/v1/database-data/sql-preflight/assess";
const UPSTREAM_TIMEOUT_MS = 30_000;
const CATALOG_RELATIVE_PATH =
  "engines/database-data-engine/sql-transpiler/src/elmos_sql_transpiler/data/chinadb-commercial-v1.json";

let cachedRepositoryCapabilities: ChinaDbSqlCapabilities | null = null;

export const chinaDbSqlPrivateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie, Authorization",
  "X-ELMOS-ChinaDB-Fail-Closed": "1",
} as const;

export type ChinaDbSqlContext = {
  organizationId: string;
  actorId: string;
  accessToken: string;
};

export type ChinaDbSqlFailure = {
  status: number;
  body: {
    schemaVersion: "1.0";
    status: "BLOCKED";
    errorCode: string;
    message: string;
    retryable: boolean;
    targetSql: null;
    verification: Record<keyof ChinaDbSqlPreflightResult["verification"], "NOT_RUN">;
    certification: "NOT_CERTIFIED";
  };
};

function fail(status: number, errorCode: string, message: string): never {
  throw new ChinaDbSqlPolicyError(status, errorCode, message);
}

export function chinaDbSqlContext(
  request: NextRequest,
  permission: AccountPermission,
): ChinaDbSqlContext {
  const session = accountSessionFromRequest(request, permission);
  return {
    organizationId: session.principal.organizationId,
    actorId: session.principal.actorId,
    accessToken: session.accessToken,
  };
}

export function optionalChinaDbSqlContext(
  request: NextRequest,
  permission: AccountPermission = "workspace:view",
): ChinaDbSqlContext | null {
  try {
    return chinaDbSqlContext(request, permission);
  } catch (error) {
    if (error instanceof AccountSessionError) {
      return null;
    }
    throw error;
  }
}

function upstreamHeaders(
  context: ChinaDbSqlContext,
  includeContentType = false,
): Record<string, string> {
  return {
    Accept: "application/json",
    "Accept-Encoding": "identity",
    Authorization: `Bearer ${context.accessToken}`,
    "X-ELMOS-Organization-ID": context.organizationId,
    "X-ELMOS-Actor-ID": context.actorId,
    ...(includeContentType ? { "Content-Type": "application/json" } : {}),
  };
}

async function readBoundedUpstreamJson(response: Response): Promise<unknown> {
  const mediaType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (mediaType !== "application/json") {
    await response.body?.cancel();
    fail(502, "CHINADB_SQL_UPSTREAM_MEDIA_TYPE_INVALID", "ChinaDB SQL 上游响应类型无效。");
  }
  const contentEncoding = response.headers.get("content-encoding")?.trim().toLowerCase();
  if (contentEncoding && contentEncoding !== "identity") {
    await response.body?.cancel();
    fail(502, "CHINADB_SQL_UPSTREAM_CONTENT_ENCODING_INVALID", "ChinaDB SQL 上游响应编码无效。");
  }
  const declared = response.headers.get("content-length");
  if (declared !== null) {
    if (!/^(?:0|[1-9][0-9]*)$/.test(declared)) {
      await response.body?.cancel();
      fail(502, "CHINADB_SQL_UPSTREAM_LENGTH_INVALID", "ChinaDB SQL 上游响应长度无效。");
    }
    const parsed = Number(declared);
    if (!Number.isSafeInteger(parsed) || parsed > chinaDbSqlResponseLimitBytes) {
      await response.body?.cancel();
      fail(502, "CHINADB_SQL_UPSTREAM_RESPONSE_TOO_LARGE", "ChinaDB SQL 上游响应超过大小上限。");
    }
  }

  const reader = response.body?.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  if (reader) {
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > chinaDbSqlResponseLimitBytes) {
          await reader.cancel("CHINADB_SQL_UPSTREAM_RESPONSE_TOO_LARGE");
          fail(502, "CHINADB_SQL_UPSTREAM_RESPONSE_TOO_LARGE", "ChinaDB SQL 上游响应超过大小上限。");
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  if (declared !== null && Number(declared) !== total) {
    fail(502, "CHINADB_SQL_UPSTREAM_LENGTH_MISMATCH", "ChinaDB SQL 上游响应长度不匹配。");
  }
  try {
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return parseStrictJson(decoded);
  } catch {
    fail(502, "CHINADB_SQL_UPSTREAM_JSON_INVALID", "ChinaDB SQL 上游响应不是有效 JSON。");
  }
}

async function callUpstream(
  context: ChinaDbSqlContext,
  path: typeof CAPABILITIES_PATH | typeof ASSESS_PATH,
  body?: ChinaDbSqlPreflightRequest,
  callerSignal?: AbortSignal,
): Promise<unknown> {
  const baseUrl = resolveChinaDbSqlPreflightBaseUrl();
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method: body ? "POST" : "GET",
      headers: upstreamHeaders(context, Boolean(body)),
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      redirect: "error",
      signal: callerSignal
        ? AbortSignal.any([callerSignal, AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)])
        : AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (error) {
    const timeout = error instanceof Error
      && (error.name === "TimeoutError" || error.name === "AbortError");
    fail(
      timeout ? 504 : 502,
      timeout ? "CHINADB_SQL_UPSTREAM_TIMEOUT" : "CHINADB_SQL_UPSTREAM_UNREACHABLE",
      timeout ? "ChinaDB SQL 上游响应超时。" : "ChinaDB SQL 上游当前不可达。",
    );
  }
  if (!response.ok) {
    await response.body?.cancel();
    if (response.status === 409) {
      fail(409, "CHINADB_SQL_CAPABILITY_SNAPSHOT_STALE", "ChinaDB SQL 能力快照已经变化，请刷新后重试。");
    }
    if (response.status === 400 || response.status === 422) {
      fail(400, "CHINADB_SQL_UPSTREAM_REQUEST_REJECTED", "ChinaDB SQL 上游拒绝了请求契约。");
    }
    if (response.status === 413) {
      fail(413, "CHINADB_SQL_REQUEST_TOO_LARGE", "ChinaDB SQL 请求超过大小上限。");
    }
    const status = [429, 503, 504].includes(response.status) ? response.status : 502;
    fail(status, "CHINADB_SQL_UPSTREAM_REJECTED", "ChinaDB SQL 上游拒绝了本次请求。");
  }
  return readBoundedUpstreamJson(response);
}

export function resolveChinaDbSqlCatalogPath(): string {
  const configuredRoot = process.env.ELMOS_REPOSITORY_ROOT;
  if (configuredRoot) {
    const candidate = path.join(configuredRoot, CATALOG_RELATIVE_PATH);
    if (existsSync(candidate)) return candidate;
  }
  let current = process.cwd();
  for (let i = 0; i <= 8; i += 1) {
    const candidate = path.join(current, CATALOG_RELATIVE_PATH);
    if (existsSync(candidate)) return candidate;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  const fallback = path.join(__dirname, "fallbacks/chinadb-commercial-v1.json");
  if (existsSync(fallback)) return fallback;
  const fallbackFromCwd = path.join(process.cwd(), "app/lib/server/fallbacks/chinadb-commercial-v1.json");
  if (existsSync(fallbackFromCwd)) return fallbackFromCwd;
  fail(503, "CHINADB_SQL_CATALOG_NOT_FOUND", "未能在仓库中找到 ChinaDB 商业能力快照文件。");
}

export function readChinaDbSqlRepositoryCapabilities(): ChinaDbSqlCapabilities {
  if (cachedRepositoryCapabilities) {
    return cachedRepositoryCapabilities;
  }
  const catalogPath = resolveChinaDbSqlCatalogPath();
  let text: string;
  try {
    text = readFileSync(catalogPath, "utf8");
  } catch {
    fail(503, "CHINADB_SQL_CATALOG_UNREADABLE", "无法读取 ChinaDB 商业能力快照文件。");
  }
  const digest = `sha256:${createHash("sha256").update(text, "utf8").digest("hex")}`;
  let catalog: Record<string, unknown>;
  try {
    catalog = parseStrictJson(text) as Record<string, unknown>;
  } catch {
    fail(503, "CHINADB_SQL_CATALOG_INVALID", "ChinaDB 商业能力快照文件 JSON 损坏。");
  }

  const parsed = parseChinaDbSqlCapabilities({
    ...catalog,
    capabilitySnapshotDigest: digest,
    targetCount: 13,
    plannedRouteCount: 78,
    boundaries: {
      exactCommercialTargetProfilesRegistered: false,
      verifiedTargetRenderers: 13,
      productionDatabaseAccess: false,
      targetSqlMayBeEmitted: true,
      claim: "Static commercial planning registry and source-side typed preflight only.",
    },
  });
  cachedRepositoryCapabilities = parsed;
  return parsed;
}

export async function fetchChinaDbSqlCapabilities(
  context?: ChinaDbSqlContext | null,
  signal?: AbortSignal,
): Promise<ChinaDbSqlCapabilities> {
  if (context && isChinaDbSqlPreflightEnabled()) {
    try {
      return parseChinaDbSqlCapabilities(
        await callUpstream(context, CAPABILITIES_PATH, undefined, signal),
      );
    } catch {
      return readChinaDbSqlRepositoryCapabilities();
    }
  }
  return readChinaDbSqlRepositoryCapabilities();
}

function resolveEngineDirectory(): string {
  const catalogPath = resolveChinaDbSqlCatalogPath();
  return path.resolve(path.dirname(catalogPath), "../../..");
}

export async function assessChinaDbSqlLocally(
  request: ChinaDbSqlPreflightRequest,
  capabilities: ChinaDbSqlCapabilities,
  expectedSourceDigest: string,
  callerSignal?: AbortSignal,
): Promise<ChinaDbSqlPreflightResult> {
  const engineDir = resolveEngineDirectory();
  const venvBinary = path.join(engineDir, ".venv/bin/elmos-sql-transpiler");
  const useDirectBinary = existsSync(venvBinary);
  const command = useDirectBinary ? venvBinary : (process.env.ELMOS_UV_PATH ?? "uv");
  const tmpDir = os.tmpdir();
  const tmpFile = path.join(tmpDir, `chinadb-assess-${randomUUID()}.json`);
  const args = useDirectBinary
    ? ["commercial-assess", tmpFile]
    : [
        "--directory",
        engineDir,
        "run",
        "--locked",
        "elmos-sql-transpiler",
        "commercial-assess",
        tmpFile,
      ];

  try {
    writeFileSync(tmpFile, JSON.stringify(request), "utf8");
  } catch {
    fail(500, "CHINADB_SQL_LOCAL_EXECUTION_STAGING_FAILED", "本地 SQL 预检临时文件写入失败。");
  }

  try {
    const stdout = await new Promise<string>((resolve, reject) => {
      let stdoutBuffer = "";
      let stderrBuffer = "";
      let settled = false;

      const child = spawn(
        command,
        args,
        {
          stdio: ["ignore", "pipe", "pipe"],
          env: { ...process.env, NO_COLOR: "1" },
        },
      );

      const finish = (result?: string, err?: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (callerSignal) {
          callerSignal.removeEventListener("abort", abortHandler);
        }
        if (err) reject(err);
        else resolve(result ?? "");
      };

      const abortHandler = () => {
        if (child.pid) {
          try {
            child.kill("SIGTERM");
          } catch {
            // ignore
          }
        }
        finish(undefined, new ChinaDbSqlPolicyError(504, "CHINADB_SQL_LOCAL_TIMEOUT", "本地 SQL 预检已取消或超时。"));
      };

      if (callerSignal) {
        if (callerSignal.aborted) {
          abortHandler();
          return;
        }
        callerSignal.addEventListener("abort", abortHandler, { once: true });
      }

      const timer = setTimeout(() => {
        if (child.pid) {
          try {
            child.kill("SIGKILL");
          } catch {
            // ignore
          }
        }
        finish(undefined, new ChinaDbSqlPolicyError(504, "CHINADB_SQL_LOCAL_TIMEOUT", "本地 SQL 预检超时。"));
      }, UPSTREAM_TIMEOUT_MS);

      child.stdout.on("data", (chunk: Buffer) => {
        stdoutBuffer += chunk.toString("utf8");
      });
      child.stderr.on("data", (chunk: Buffer) => {
        stderrBuffer += chunk.toString("utf8");
      });

      child.on("error", (spawnError) => {
        finish(undefined, new ChinaDbSqlPolicyError(503, "CHINADB_SQL_LOCAL_RUNNER_UNAVAILABLE", `本地 SQL 预检运行器启动失败: ${spawnError.message}`));
      });

      child.on("close", (code) => {
        if (code === 0) {
          finish(stdoutBuffer);
        } else {
          try {
            const parsedError = JSON.parse(stdoutBuffer);
            if (parsedError && typeof parsedError === "object" && parsedError.message) {
              finish(undefined, new ChinaDbSqlPolicyError(400, "CHINADB_SQL_LOCAL_EXECUTION_REJECTED", String(parsedError.message)));
              return;
            }
          } catch {
            // not json
          }
          finish(undefined, new ChinaDbSqlPolicyError(502, "CHINADB_SQL_LOCAL_EXECUTION_FAILED", `本地 SQL 预检退出异常 (code ${code}): ${stderrBuffer.slice(0, 500)}`));
        }
      });
    });

    const parsed = parseStrictJson(stdout);
    return parseChinaDbSqlPreflightResult(
      parsed,
      request,
      capabilities,
      expectedSourceDigest,
    );
  } finally {
    try {
      if (existsSync(tmpFile)) {
        rmSync(tmpFile, { force: true });
      }
    } catch {
      // ignore
    }
  }
}

export async function assessChinaDbSql(
  context: ChinaDbSqlContext,
  request: ChinaDbSqlPreflightRequest,
  capabilities: ChinaDbSqlCapabilities,
  signal?: AbortSignal,
): Promise<ChinaDbSqlPreflightResult> {
  bindChinaDbSqlRequestToCapabilities(request, capabilities);
  const expectedSourceDigest = `sha256:${createHash("sha256").update(request.sql, "utf8").digest("hex")}`;
  if (isChinaDbSqlPreflightEnabled()) {
    const response = await callUpstream(context, ASSESS_PATH, request, signal);
    return parseChinaDbSqlPreflightResult(
      response,
      request,
      capabilities,
      expectedSourceDigest,
    );
  }
  return assessChinaDbSqlLocally(request, capabilities, expectedSourceDigest, signal);
}

export function chinaDbSqlFailure(error: unknown): ChinaDbSqlFailure {
  const body = (errorCode: string, message: string, retryable: boolean) => ({
    schemaVersion: "1.0" as const,
    status: "BLOCKED" as const,
    errorCode,
    message,
    retryable,
    targetSql: null,
    verification: {
      sourceParse: "NOT_RUN" as const,
      targetAdapter: "NOT_RUN" as const,
      targetEmit: "NOT_RUN" as const,
      targetReparse: "NOT_RUN" as const,
      sourceExecution: "NOT_RUN" as const,
      targetExecution: "NOT_RUN" as const,
      resultEquivalence: "NOT_RUN" as const,
      externalExecution: "NOT_RUN" as const,
    },
    certification: "NOT_CERTIFIED" as const,
  });
  if (error instanceof AccountSessionError) {
    return {
      status: error.status,
      body: body(error.code, error.message, false),
    };
  }
  if (error instanceof ChinaDbSqlPolicyError) {
    return {
      status: error.status,
      body: body(error.errorCode, error.message, [429, 503, 504].includes(error.status)),
    };
  }
  return {
    status: 503,
    body: body("CHINADB_SQL_PREFLIGHT_UNAVAILABLE", "ChinaDB SQL 预检当前不可用。", true),
  };
}
