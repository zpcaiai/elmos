import "server-only";

import type { NextRequest } from "next/server";

import {
  parseRepositoryModelCatalog,
  parseRepositoryPreflightResult,
  RepositoryOrchestratorContractError,
  repositoryOrchestratorResponseLimitBytes,
  type RepositoryModelCatalog,
  type RepositoryPreflightRequest,
  type RepositoryPreflightResult,
} from "../repositoryOrchestratorContracts";
import {
  AccountSessionError,
  accountSessionFromRequest,
} from "./accountSession";

const MODEL_CATALOG_PATH = "/agent/v1/repository-orchestrator/models";
const PREFLIGHT_PATH = "/agent/v1/repository-orchestrator/preflight";
const UPSTREAM_TIMEOUT_MS = 10_000;
const loopbackHosts = new Set(["127.0.0.1", "localhost", "[::1]"]);

export const repositoryOrchestratorPrivateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Pragma: "no-cache",
  Vary: "Cookie, Authorization",
  "X-Content-Type-Options": "nosniff",
} as const;

export type RepositoryOrchestratorContext = {
  organizationId: string;
  actorId: string;
  accessToken: string;
};

export type RepositoryOrchestratorFailure = {
  status: number;
  body: {
    status: "BLOCKED";
    errorCode: string;
    message: string;
    providerInvocation: "NOT_RUN";
    taskDecomposition: "NOT_RUN";
    runCreation: "NOT_RUN";
    workspaceMutation: "NOT_RUN";
    scmEffects: "NOT_RUN";
    externalVerification: "NOT_RUN";
    certification: "NOT_CERTIFIED";
  };
};

class RepositoryGatewayError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "RepositoryGatewayError";
  }
}

function gatewayFail(status: number, code: string, message: string): never {
  throw new RepositoryGatewayError(status, code, message);
}

export function repositoryOrchestratorContext(request: NextRequest): RepositoryOrchestratorContext {
  const session = accountSessionFromRequest(request, "repository:read");
  return {
    organizationId: session.principal.organizationId,
    actorId: session.principal.actorId,
    accessToken: session.accessToken,
  };
}

function resolveAgentGatewayBaseUrl(): string {
  const configured = process.env.ELMOS_AGENT_GATEWAY_BASE_URL?.trim() ?? "";
  if (!configured) {
    gatewayFail(503, "REPOSITORY_AGENT_GATEWAY_NOT_CONFIGURED", "仓库编排 Agent Gateway 尚未配置。");
  }
  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    gatewayFail(503, "REPOSITORY_AGENT_GATEWAY_CONFIGURATION_INVALID", "仓库编排 Agent Gateway 配置无效。");
  }
  if (
    parsed.pathname !== "/"
    || parsed.search
    || parsed.hash
    || parsed.username
    || parsed.password
    || !parsed.hostname
  ) {
    gatewayFail(503, "REPOSITORY_AGENT_GATEWAY_CONFIGURATION_INVALID", "仓库编排 Agent Gateway 配置无效。");
  }
  const host = parsed.hostname.toLowerCase();
  const localDevelopment = process.env.NODE_ENV !== "production"
    && parsed.protocol === "http:"
    && loopbackHosts.has(host);
  const trustedInternal = process.env.ELMOS_TRUSTED_INTERNAL_HTTP === "true"
    && parsed.protocol === "http:"
    && parsed.host.toLowerCase() === "agent-gateway:8083";
  if (parsed.protocol !== "https:" && !localDevelopment && !trustedInternal) {
    gatewayFail(503, "REPOSITORY_AGENT_GATEWAY_CONFIGURATION_INVALID", "仓库编排 Agent Gateway 必须使用可信地址。");
  }
  return parsed.origin;
}

function upstreamHeaders(
  context: RepositoryOrchestratorContext,
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

async function readBoundedJson(response: Response): Promise<unknown> {
  const mediaType = response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (mediaType !== "application/json") {
    await response.body?.cancel();
    gatewayFail(502, "REPOSITORY_AGENT_GATEWAY_MEDIA_TYPE_INVALID", "仓库编排上游响应类型无效。");
  }
  const declared = response.headers.get("content-length");
  if (declared !== null) {
    if (!/^(?:0|[1-9][0-9]*)$/.test(declared)) {
      await response.body?.cancel();
      gatewayFail(502, "REPOSITORY_AGENT_GATEWAY_LENGTH_INVALID", "仓库编排上游响应长度无效。");
    }
    const length = Number(declared);
    if (!Number.isSafeInteger(length) || length > repositoryOrchestratorResponseLimitBytes) {
      await response.body?.cancel();
      gatewayFail(502, "REPOSITORY_AGENT_GATEWAY_RESPONSE_TOO_LARGE", "仓库编排上游响应超过大小上限。");
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
        if (total > repositoryOrchestratorResponseLimitBytes) {
          await reader.cancel("REPOSITORY_AGENT_GATEWAY_RESPONSE_TOO_LARGE");
          gatewayFail(502, "REPOSITORY_AGENT_GATEWAY_RESPONSE_TOO_LARGE", "仓库编排上游响应超过大小上限。");
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
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)) as unknown;
  } catch {
    gatewayFail(502, "REPOSITORY_AGENT_GATEWAY_JSON_INVALID", "仓库编排上游响应不是有效 JSON。");
  }
}

async function callGateway(
  context: RepositoryOrchestratorContext,
  path: typeof MODEL_CATALOG_PATH | typeof PREFLIGHT_PATH,
  body?: RepositoryPreflightRequest,
): Promise<{ status: number; value: unknown }> {
  let response: Response;
  try {
    response = await fetch(`${resolveAgentGatewayBaseUrl()}${path}`, {
      method: body ? "POST" : "GET",
      headers: upstreamHeaders(context, Boolean(body)),
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (error) {
    if (error instanceof RepositoryGatewayError) throw error;
    const timeout = error instanceof Error
      && (error.name === "TimeoutError" || error.name === "AbortError");
    gatewayFail(
      timeout ? 504 : 502,
      timeout ? "REPOSITORY_AGENT_GATEWAY_TIMEOUT" : "REPOSITORY_AGENT_GATEWAY_UNREACHABLE",
      timeout ? "仓库编排上游响应超时。" : "仓库编排上游当前不可达。",
    );
  }
  if (!response.ok && !(path === PREFLIGHT_PATH && response.status === 400)) {
    await response.body?.cancel();
    const status = response.status === 429 ? 429 : response.status === 503 ? 503 : 502;
    gatewayFail(status, "REPOSITORY_AGENT_GATEWAY_REJECTED", "仓库编排上游拒绝了本次请求。");
  }
  return { status: response.status, value: await readBoundedJson(response) };
}

export async function fetchRepositoryModelCatalog(
  context: RepositoryOrchestratorContext,
): Promise<RepositoryModelCatalog> {
  const response = await callGateway(context, MODEL_CATALOG_PATH);
  return parseRepositoryModelCatalog(response.value);
}

export async function submitRepositoryPreflight(
  context: RepositoryOrchestratorContext,
  request: RepositoryPreflightRequest,
): Promise<{ status: number; result: RepositoryPreflightResult }> {
  const response = await callGateway(context, PREFLIGHT_PATH, request);
  return { status: response.status, result: parseRepositoryPreflightResult(response.value) };
}

export function repositoryOrchestratorFailure(error: unknown): RepositoryOrchestratorFailure {
  let status = 503;
  let errorCode = "REPOSITORY_ORCHESTRATOR_UNAVAILABLE";
  let message = "仓库编排预检当前不可用。";
  if (error instanceof AccountSessionError) {
    status = error.status;
    errorCode = error.code;
    message = error.message;
  } else if (error instanceof RepositoryOrchestratorContractError) {
    status = error.status;
    errorCode = error.code;
    message = error.message;
  } else if (error instanceof RepositoryGatewayError) {
    status = error.status;
    errorCode = error.code;
    message = error.message;
  }
  return {
    status,
    body: {
      status: "BLOCKED",
      errorCode,
      message,
      providerInvocation: "NOT_RUN",
      taskDecomposition: "NOT_RUN",
      runCreation: "NOT_RUN",
      workspaceMutation: "NOT_RUN",
      scmEffects: "NOT_RUN",
      externalVerification: "NOT_RUN",
      certification: "NOT_CERTIFIED",
    },
  };
}
