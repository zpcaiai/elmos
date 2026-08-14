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
} from "./accountSession";
import { resolveChinaDbSqlPreflightBaseUrl } from "./chinadbSqlUpstreamPolicy";

const CAPABILITIES_PATH = "/api/v1/database-data/sql-preflight/capabilities";
const ASSESS_PATH = "/api/v1/database-data/sql-preflight/assess";
const UPSTREAM_TIMEOUT_MS = 15_000;

export const chinaDbSqlPrivateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie, Authorization",
} as const;

export type ChinaDbSqlContext = {
  organizationId: string;
  actorId: string;
  accessToken: string;
};

export type ChinaDbSqlFailure = {
  status: number;
  body: {
    status: "BLOCKED";
    errorCode: string;
    message: string;
    externalExecution: "NOT_RUN";
    certification: "NOT_CERTIFIED";
    targetSql: null;
  };
};

function fail(status: number, errorCode: string, message: string): never {
  throw new ChinaDbSqlPolicyError(status, errorCode, message);
}

export function chinaDbSqlContext(request: NextRequest): ChinaDbSqlContext {
  const session = accountSessionFromRequest(request, "translation:execute");
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
  try {
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return JSON.parse(decoded) as unknown;
  } catch {
    fail(502, "CHINADB_SQL_UPSTREAM_JSON_INVALID", "ChinaDB SQL 上游响应不是有效 JSON。");
  }
}

async function callUpstream(
  context: ChinaDbSqlContext,
  path: typeof CAPABILITIES_PATH | typeof ASSESS_PATH,
  body?: ChinaDbSqlPreflightRequest,
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
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
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
    const status = response.status === 429 ? 429 : response.status === 503 ? 503 : 502;
    fail(status, "CHINADB_SQL_UPSTREAM_REJECTED", "ChinaDB SQL 上游拒绝了本次请求。");
  }
  return readBoundedUpstreamJson(response);
}

export async function fetchChinaDbSqlCapabilities(
  context: ChinaDbSqlContext,
): Promise<ChinaDbSqlCapabilities> {
  return parseChinaDbSqlCapabilities(await callUpstream(context, CAPABILITIES_PATH));
}

export async function assessChinaDbSql(
  context: ChinaDbSqlContext,
  request: ChinaDbSqlPreflightRequest,
  capabilities: ChinaDbSqlCapabilities,
): Promise<ChinaDbSqlPreflightResult> {
  bindChinaDbSqlRequestToCapabilities(request, capabilities);
  const expectedSourceDigest = `sha256:${createHash("sha256").update(request.sql, "utf8").digest("hex")}`;
  const response = await callUpstream(context, ASSESS_PATH, request);
  return parseChinaDbSqlPreflightResult(
    response,
    request,
    capabilities,
    expectedSourceDigest,
  );
}

export function chinaDbSqlFailure(error: unknown): ChinaDbSqlFailure {
  if (error instanceof AccountSessionError) {
    return {
      status: error.status,
      body: {
        status: "BLOCKED",
        errorCode: error.code,
        message: error.message,
        externalExecution: "NOT_RUN",
        certification: "NOT_CERTIFIED",
        targetSql: null,
      },
    };
  }
  if (error instanceof ChinaDbSqlPolicyError) {
    return {
      status: error.status,
      body: {
        status: "BLOCKED",
        errorCode: error.errorCode,
        message: error.message,
        externalExecution: "NOT_RUN",
        certification: "NOT_CERTIFIED",
        targetSql: null,
      },
    };
  }
  return {
    status: 503,
    body: {
      status: "BLOCKED",
      errorCode: "CHINADB_SQL_PREFLIGHT_UNAVAILABLE",
      message: "ChinaDB SQL 预检当前不可用。",
      externalExecution: "NOT_RUN",
      certification: "NOT_CERTIFIED",
      targetSql: null,
    },
  };
}
