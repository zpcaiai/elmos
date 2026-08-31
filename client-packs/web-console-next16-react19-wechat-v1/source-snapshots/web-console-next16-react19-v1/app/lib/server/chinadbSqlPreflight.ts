import { createHash } from "node:crypto";
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
import { resolveChinaDbSqlPreflightBaseUrl } from "./chinadbSqlUpstreamPolicy";
import { parseStrictJson } from "./strictJson";

const CAPABILITIES_PATH = "/api/v1/database-data/sql-preflight/capabilities";
const ASSESS_PATH = "/api/v1/database-data/sql-preflight/assess";
const UPSTREAM_TIMEOUT_MS = 15_000;

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

export async function fetchChinaDbSqlCapabilities(
  context: ChinaDbSqlContext,
  signal?: AbortSignal,
): Promise<ChinaDbSqlCapabilities> {
  return parseChinaDbSqlCapabilities(await callUpstream(context, CAPABILITIES_PATH, undefined, signal));
}

export async function assessChinaDbSql(
  context: ChinaDbSqlContext,
  request: ChinaDbSqlPreflightRequest,
  capabilities: ChinaDbSqlCapabilities,
  signal?: AbortSignal,
): Promise<ChinaDbSqlPreflightResult> {
  bindChinaDbSqlRequestToCapabilities(request, capabilities);
  const expectedSourceDigest = `sha256:${createHash("sha256").update(request.sql, "utf8").digest("hex")}`;
  const response = await callUpstream(context, ASSESS_PATH, request, signal);
  return parseChinaDbSqlPreflightResult(
    response,
    request,
    capabilities,
    expectedSourceDigest,
  );
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
