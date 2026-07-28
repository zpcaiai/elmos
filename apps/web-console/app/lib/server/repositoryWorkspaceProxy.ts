import { createHash, randomUUID, timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";

const sessionCookieName = "__Host-elmos_access_token";
const maximumBodyBytes = 3 * 1024 * 1024;
const requestTimeoutMs = 30_000;
const workspaceIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export class RepositoryWorkspaceProxyError extends Error {
  constructor(
    readonly status: number,
    readonly errorCode: string,
    message: string,
    readonly retryable = false,
  ) {
    super(message);
  }
}

function requiredEnvironment(name: string, minimumLength = 1): string {
  const value = process.env[name]?.trim() ?? "";
  if (value.length < minimumLength) {
    throw new RepositoryWorkspaceProxyError(
      503,
      "REPOSITORY_WORKSPACE_NOT_CONFIGURED",
      "仓库工作区尚未配置。",
    );
  }
  return value;
}

function controlPlaneBaseUrl(): string {
  const configured = process.env.ELMOS_REPOSITORY_WORKSPACE_BASE_URL?.trim()
    || process.env.ELMOS_CONTROL_PLANE_BASE_URL?.trim()
    || (process.env.NODE_ENV === "production" ? "" : "http://127.0.0.1:8080");
  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    throw new RepositoryWorkspaceProxyError(
      503,
      "REPOSITORY_WORKSPACE_URL_INVALID",
      "仓库工作区服务地址无效。",
    );
  }
  const local = parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
  if ((parsed.protocol !== "https:" && !(local && parsed.protocol === "http:"))
    || parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new RepositoryWorkspaceProxyError(
      503,
      "REPOSITORY_WORKSPACE_URL_INVALID",
      "仓库工作区服务必须使用无凭据 HTTPS 地址。",
    );
  }
  return parsed.toString().replace(/\/$/, "");
}

function authorizeBrowser(request: NextRequest): void {
  const configured = requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_USER_TOKEN", 24);
  const authorization = request.headers.get("authorization") ?? "";
  const headerToken = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  const presented = request.cookies.get(sessionCookieName)?.value || headerToken;
  const expectedHash = createHash("sha256").update(configured).digest();
  const presentedHash = createHash("sha256").update(presented).digest();
  if (!timingSafeEqual(expectedHash, presentedHash)) {
    throw new RepositoryWorkspaceProxyError(
      401,
      "REPOSITORY_WORKSPACE_SESSION_REQUIRED",
      "需要有效会话才能访问仓库工作区。",
    );
  }
}

function validatePath(parts: string[], search: URLSearchParams): string {
  if (parts.length === 0) return "";
  if (parts.length === 1 && parts[0] === "capabilities") return "/capabilities";
  if (!workspaceIdPattern.test(parts[0] ?? "")) {
    throw new RepositoryWorkspaceProxyError(
      400,
      "REPOSITORY_WORKSPACE_PATH_INVALID",
      "仓库工作区路径无效。",
    );
  }
  if (parts.length === 1) return `/${parts[0]}`;
  if (parts.length === 2 && parts[1] === "changes") return `/${parts[0]}/changes`;
  if (parts.length === 2 && parts[1] === "files") {
    const filePath = search.get("path") ?? "";
    if (!filePath || filePath.length > 512 || filePath.startsWith("/")
      || filePath.split("/").includes("..") || /[\0\r\n]/.test(filePath)) {
      throw new RepositoryWorkspaceProxyError(
        400,
        "REPOSITORY_FILE_PATH_INVALID",
        "仓库文件路径无效。",
      );
    }
    return `/${parts[0]}/files?${new URLSearchParams({ path: filePath })}`;
  }
  throw new RepositoryWorkspaceProxyError(
    400,
    "REPOSITORY_WORKSPACE_PATH_INVALID",
    "仓库工作区路径无效。",
  );
}

export async function repositoryWorkspaceRequest(
  request: NextRequest,
  parts: string[],
): Promise<Response> {
  authorizeBrowser(request);
  const method = request.method;
  if (!["GET", "POST", "DELETE"].includes(method)) {
    throw new RepositoryWorkspaceProxyError(405, "REPOSITORY_METHOD_NOT_ALLOWED", "请求方法不受支持。");
  }
  if (method !== "GET" && request.cookies.has(sessionCookieName)) {
    const origin = request.headers.get("origin");
    if (!origin || origin !== request.nextUrl.origin) {
      throw new RepositoryWorkspaceProxyError(403, "REPOSITORY_ORIGIN_INVALID", "仓库写操作来源校验失败。");
    }
  }
  const targetPath = validatePath(parts, request.nextUrl.searchParams);
  if (method === "POST" && targetPath !== "" && !targetPath.endsWith("/changes")) {
    throw new RepositoryWorkspaceProxyError(405, "REPOSITORY_METHOD_NOT_ALLOWED", "请求方法不受支持。");
  }
  if (method === "DELETE" && (!workspaceIdPattern.test(parts[0] ?? "") || parts.length !== 1)) {
    throw new RepositoryWorkspaceProxyError(405, "REPOSITORY_METHOD_NOT_ALLOWED", "请求方法不受支持。");
  }
  let body: string | undefined;
  if (method === "POST") {
    body = await request.text();
    if (Buffer.byteLength(body, "utf8") > maximumBodyBytes) {
      throw new RepositoryWorkspaceProxyError(413, "REPOSITORY_REQUEST_TOO_LARGE", "仓库变更请求过大。");
    }
    try {
      JSON.parse(body);
    } catch {
      throw new RepositoryWorkspaceProxyError(400, "REPOSITORY_REQUEST_INVALID", "请求不是有效 JSON。");
    }
  }
  const headers = new Headers({
    "Accept": "application/json",
    "X-ELMOS-Repository-Key": requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_API_KEY", 24),
    "X-ELMOS-Organization-ID": requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_TENANT_ID"),
    "X-ELMOS-Actor-ID": requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_ACTOR_ID"),
    "X-Request-ID": randomUUID(),
  });
  if (body !== undefined) headers.set("Content-Type", "application/json");
  try {
    return await fetch(`${controlPlaneBaseUrl()}/api/v1/repository-workspaces${targetPath}`, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(requestTimeoutMs),
    });
  } catch (error) {
    if (error instanceof RepositoryWorkspaceProxyError) throw error;
    throw new RepositoryWorkspaceProxyError(
      503,
      "REPOSITORY_WORKSPACE_UNAVAILABLE",
      "仓库工作区服务暂时不可用。",
      true,
    );
  }
}

export function repositoryWorkspaceError(error: unknown): Response {
  if (error instanceof RepositoryWorkspaceProxyError) {
    return Response.json({
      errorCode: error.errorCode,
      message: error.message,
      retryable: error.retryable,
    }, { status: error.status });
  }
  return Response.json({
    errorCode: "REPOSITORY_WORKSPACE_PROXY_ERROR",
    message: "仓库工作区代理发生内部错误。",
    retryable: true,
  }, { status: 500 });
}
