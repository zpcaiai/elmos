import type { NextRequest } from "next/server";
import {
  AccountSessionError,
  accountSessionErrorResponse,
  accountSessionFromRequest,
} from "./accountSession";

const organizationPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const accountPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function baseUrl(): string {
  const configured = process.env.ELMOS_CONTROL_PLANE_BASE_URL?.trim() ?? "";
  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    throw new AccountSessionError(
      503, "CONTROL_PLANE_NOT_CONFIGURED", "账户控制面尚未配置。",
    );
  }
  const localDevelopment = process.env.NODE_ENV !== "production"
    && ["localhost", "127.0.0.1"].includes(parsed.hostname);
  if (
    (parsed.protocol !== "https:" && !(localDevelopment && parsed.protocol === "http:"))
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
  ) {
    throw new AccountSessionError(
      503, "CONTROL_PLANE_CONFIGURATION_INVALID", "账户控制面地址无效。",
    );
  }
  return parsed.toString().replace(/\/$/, "");
}

function targetPath(parts: string[], method: string): {
  path: string;
  organizationId?: string;
} {
  if (parts.length === 1 && parts[0] === "organizations"
      && ["GET", "POST"].includes(method)) {
    return { path: "/organizations" };
  }
  if (parts.length === 2 && parts[0] === "invitations"
      && parts[1] === "accept" && method === "POST") {
    return { path: "/invitations/accept" };
  }
  const organizationId = parts[1] ?? "";
  if (parts[0] !== "organizations" || !organizationPattern.test(organizationId)) {
    throw new AccountSessionError(
      404, "ACCOUNT_ROUTE_UNKNOWN", "账户操作不存在。",
    );
  }
  if (parts.length === 3 && parts[2] === "members" && method === "GET") {
    return {
      path: `/organizations/${encodeURIComponent(organizationId)}/members`,
      organizationId,
    };
  }
  if (parts.length === 3 && parts[2] === "invitations" && method === "POST") {
    return {
      path: `/organizations/${encodeURIComponent(organizationId)}/invitations`,
      organizationId,
    };
  }
  const accountId = parts[3] ?? "";
  if (
    parts.length === 4
    && parts[2] === "members"
    && accountPattern.test(accountId)
    && ["PATCH", "DELETE"].includes(method)
  ) {
    return {
      path: `/organizations/${encodeURIComponent(organizationId)}/members/${encodeURIComponent(accountId)}`,
      organizationId,
    };
  }
  throw new AccountSessionError(
    404, "ACCOUNT_ROUTE_UNKNOWN", "账户操作不存在。",
  );
}

export async function accountControlPlaneRequest(
  request: NextRequest,
  parts: string[],
): Promise<Response> {
  const method = request.method.toUpperCase();
  if (!["GET", "POST", "PATCH", "DELETE"].includes(method)) {
    throw new AccountSessionError(
      405, "ACCOUNT_METHOD_NOT_ALLOWED", "账户操作方法不受支持。",
    );
  }
  const session = accountSessionFromRequest(request);
  const target = targetPath(parts, method);
  let body: string | undefined;
  if (!["GET", "DELETE"].includes(method)) {
    body = await request.text();
    if (Buffer.byteLength(body, "utf8") > 32 * 1024) {
      throw new AccountSessionError(
        413, "ACCOUNT_REQUEST_TOO_LARGE", "账户请求过大。",
      );
    }
    try {
      JSON.parse(body);
    } catch {
      throw new AccountSessionError(
        400, "ACCOUNT_REQUEST_INVALID", "账户请求不是有效 JSON。",
      );
    }
  }
  const headers = new Headers({
    Accept: "application/json",
    Authorization: `Bearer ${session.accessToken}`,
  });
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (target.organizationId) {
    headers.set("X-ELMOS-Organization-ID", target.organizationId);
  }
  let response: Response;
  try {
    response = await fetch(`${baseUrl()}/api/v1/account${target.path}`, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    throw new AccountSessionError(
      503, "ACCOUNT_CONTROL_PLANE_UNAVAILABLE", "账户控制面暂时不可用。",
    );
  }
  const payload = await response.text();
  if (Buffer.byteLength(payload, "utf8") > 256 * 1024) {
    throw new AccountSessionError(
      502, "ACCOUNT_RESPONSE_TOO_LARGE", "账户控制面响应异常。",
    );
  }
  return new Response(payload, {
    status: response.status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store, private",
    },
  });
}

export function accountControlPlaneError(error: unknown): Response {
  return accountSessionErrorResponse(error);
}
