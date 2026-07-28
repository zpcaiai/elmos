import type { NextRequest } from "next/server";

const sessionCookieName = "__Host-elmos_access_token";
const requestTimeoutMs = 8_000;

export class CommercialBillingProxyError extends Error {
  constructor(
    readonly httpStatus: number,
    readonly code: string,
    message: string,
    readonly retryable: boolean,
    readonly responseStatus: "ERROR" | "NOT_CONFIGURED" = "ERROR",
  ) {
    super(message);
  }
}

function apiBase(): string {
  const configured = process.env.ELMOS_COMMERCIAL_API_URL;
  if (!configured) {
    throw new CommercialBillingProxyError(
      503,
      "COMMERCIAL_API_NOT_CONFIGURED",
      "商业计量 API 尚未配置。",
      false,
      "NOT_CONFIGURED",
    );
  }
  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    throw new CommercialBillingProxyError(
      503,
      "COMMERCIAL_API_URL_INVALID",
      "商业计量 API 地址无效。",
      false,
      "NOT_CONFIGURED",
    );
  }
  const local = parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
  if (parsed.protocol !== "https:" && !(local && parsed.protocol === "http:")) {
    throw new CommercialBillingProxyError(
      503,
      "COMMERCIAL_API_TRANSPORT_INVALID",
      "商业计量 API 必须使用 HTTPS。",
      false,
      "NOT_CONFIGURED",
    );
  }
  return parsed.toString().replace(/\/$/, "");
}

function bearer(request: NextRequest): string {
  const cookie = request.cookies.get(sessionCookieName)?.value ?? "";
  const authorization = request.headers.get("authorization") ?? "";
  const headerToken = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  const token = cookie || headerToken;
  if (token.length < 24 || token.length > 16_384) {
    throw new CommercialBillingProxyError(
      401,
      "ACCOUNT_SESSION_REQUIRED",
      "请先登录后查看账户用量。",
      false,
    );
  }
  return token;
}

function requireSameOriginForCookieMutation(
  request: NextRequest,
  method: "GET" | "POST" | "PUT",
): void {
  if (method === "GET" || !request.cookies.has(sessionCookieName)) return;
  const origin = request.headers.get("origin");
  if (!origin || origin !== request.nextUrl.origin) {
    throw new CommercialBillingProxyError(
      403,
      "ACCOUNT_SESSION_ORIGIN_INVALID",
      "账户写操作来源校验失败。",
      false,
    );
  }
}

export async function commercialBillingRequest(
  request: NextRequest,
  path: string,
  init: {
    method?: "GET" | "POST" | "PUT";
    body?: string;
    idempotencyKey?: string;
    accept?: string;
  } = {},
): Promise<Response> {
  if (!path.startsWith("/commercial/v1/billing/") || path.includes("..")) {
    throw new CommercialBillingProxyError(
      500,
      "COMMERCIAL_API_PATH_INVALID",
      "商业计量代理路径无效。",
      false,
    );
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), requestTimeoutMs);
  const method = init.method ?? "GET";
  requireSameOriginForCookieMutation(request, method);
  const headers = new Headers({
    "Authorization": `Bearer ${bearer(request)}`,
    "Accept": init.accept ?? "application/json",
  });
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  if (init.idempotencyKey) headers.set("Idempotency-Key", init.idempotencyKey);
  try {
    return await fetch(`${apiBase()}${path}`, {
      method,
      headers,
      body: init.body,
      cache: "no-store",
      redirect: "error",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof CommercialBillingProxyError) throw error;
    throw new CommercialBillingProxyError(
      503,
      "COMMERCIAL_API_UNAVAILABLE",
      "商业计量服务暂时不可用。",
      true,
    );
  } finally {
    clearTimeout(timer);
  }
}

export function proxyError(error: unknown): {
  status: number;
  body: { code: string; message: string; retryable: boolean; status: "ERROR" | "NOT_CONFIGURED" };
} {
  if (error instanceof CommercialBillingProxyError) {
    return {
      status: error.httpStatus,
      body: {
        code: error.code,
        message: error.message,
        retryable: error.retryable,
        status: error.responseStatus,
      },
    };
  }
  return {
    status: 500,
    body: {
      code: "COMMERCIAL_PROXY_INTERNAL_ERROR",
      message: "商业计量代理发生内部错误。",
      retryable: true,
      status: "ERROR",
    },
  };
}
