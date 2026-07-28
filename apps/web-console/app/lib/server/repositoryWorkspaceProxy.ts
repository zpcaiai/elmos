import { createHash, randomUUID, timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";

const sessionCookieName = "__Host-elmos_access_token";
const maximumBodyBytes = 3 * 1024 * 1024;
const maximumControlPlaneResponseBytes = 16 * 1024 * 1024;
const maximumGenerationRepositoryFiles = 8;
const requestTimeoutMs = 30_000;
const workspaceIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const sourceCommitPattern = /^[0-9a-f]{40}$/;
const digestPattern = /^[0-9a-f]{64}$/;

type RepositoryFileEntry = {
  path: string;
  bytes: number;
  sha256: string;
  category:
    | "SOURCE"
    | "DOCUMENTATION"
    | "CONFIGURATION"
    | "LOCAL_DEPLOYMENT"
    | "CLOUD_DEPLOYMENT"
    | "TEST"
    | "OTHER";
  writable: boolean;
};

type RepositoryWorkspaceSnapshot = {
  workspaceId: string;
  provider: "GITHUB" | "GITEE" | "GENERIC_GIT";
  providerInstanceId: string;
  nativeRepositoryId: string;
  sourceCommit: string;
  completeness: "COMPLETE" | "INCOMPLETE_SUBMODULES" | "INCOMPLETE_LFS";
  files: RepositoryFileEntry[];
  externalOperationExecuted: boolean;
};

type RepositoryFileContent = {
  workspaceId: string;
  path: string;
  sha256: string;
  category: RepositoryFileEntry["category"];
  encoding: "UTF-8";
  content: string;
};

export type RepositoryGenerationSource = {
  path: string;
  mediaType: string;
  origin: string;
  raw: Buffer;
  warnings: string[];
};

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

function trustedHeaders(): Headers {
  return new Headers({
    "Accept": "application/json",
    "X-ELMOS-Repository-Key": requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_API_KEY", 24),
    "X-ELMOS-Organization-ID": requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_TENANT_ID"),
    "X-ELMOS-Actor-ID": requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_ACTOR_ID"),
    "X-Request-ID": randomUUID(),
  });
}

function safeRepositoryFilePath(value: string): string {
  const candidate = value.trim();
  if (
    !candidate
    || candidate.length > 512
    || candidate.startsWith("/")
    || candidate.includes("\\")
    || candidate.split("/").includes("..")
    || /[\0\r\n]/.test(candidate)
  ) {
    throw new RepositoryWorkspaceProxyError(
      400,
      "REPOSITORY_FILE_PATH_INVALID",
      "仓库来源文件路径无效。",
    );
  }
  return candidate;
}

async function controlPlaneJson<T>(targetPath: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${controlPlaneBaseUrl()}/api/v1/repository-workspaces${targetPath}`, {
      method: "GET",
      headers: trustedHeaders(),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(requestTimeoutMs),
    });
  } catch {
    throw new RepositoryWorkspaceProxyError(
      503,
      "REPOSITORY_WORKSPACE_UNAVAILABLE",
      "仓库工作区服务暂时不可用。",
      true,
    );
  }
  const body = await response.text();
  if (Buffer.byteLength(body, "utf8") > maximumControlPlaneResponseBytes) {
    throw new RepositoryWorkspaceProxyError(
      413,
      "REPOSITORY_WORKSPACE_RESPONSE_TOO_LARGE",
      "仓库工作区响应超过项目生成来源限额。",
    );
  }
  let payload: unknown;
  try {
    payload = JSON.parse(body);
  } catch {
    throw new RepositoryWorkspaceProxyError(
      502,
      "REPOSITORY_WORKSPACE_RESPONSE_INVALID",
      "仓库工作区返回了无效响应。",
      true,
    );
  }
  if (!response.ok) {
    const error = payload && typeof payload === "object"
      ? payload as { errorCode?: unknown; message?: unknown; retryable?: unknown }
      : {};
    throw new RepositoryWorkspaceProxyError(
      response.status,
      typeof error.errorCode === "string" ? error.errorCode : "REPOSITORY_WORKSPACE_REQUEST_FAILED",
      typeof error.message === "string" ? error.message : "仓库工作区请求失败。",
      error.retryable === true,
    );
  }
  return payload as T;
}

function sourcePriority(file: RepositoryFileEntry): number {
  const lower = file.path.toLowerCase();
  if (lower === "readme.md" || lower === "readme") return 0;
  if (lower.startsWith("docs/")) return 1;
  if (file.category === "DOCUMENTATION") return 2;
  if (file.category === "LOCAL_DEPLOYMENT" || file.category === "CLOUD_DEPLOYMENT") return 3;
  if (file.category === "CONFIGURATION") return 4;
  if (file.category === "TEST") return 5;
  if (file.category === "SOURCE") return 6;
  return 7;
}

function repositoryMediaType(filePath: string): string {
  const lower = filePath.toLowerCase();
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "text/markdown";
  if (lower.endsWith(".json")) return "application/json";
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "application/yaml";
  if (lower.endsWith(".xml")) return "application/xml";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "text/html";
  return "text/plain";
}

export async function repositoryGenerationSources(input: {
  tenantId: string;
  actor: string;
  workspaceId: string;
  paths?: string[];
}): Promise<RepositoryGenerationSource[]> {
  const configuredTenant = requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_TENANT_ID");
  const configuredActor = requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_ACTOR_ID");
  if (input.tenantId !== configuredTenant || input.actor !== configuredActor) {
    throw new RepositoryWorkspaceProxyError(
      403,
      "REPOSITORY_GENERATION_IDENTITY_MISMATCH",
      "仓库工作区与项目生成器的租户或操作者身份不一致。",
    );
  }
  if (!workspaceIdPattern.test(input.workspaceId)) {
    throw new RepositoryWorkspaceProxyError(
      400,
      "REPOSITORY_WORKSPACE_ID_INVALID",
      "仓库工作区 ID 无效。",
    );
  }
  const snapshot = await controlPlaneJson<RepositoryWorkspaceSnapshot>(`/${input.workspaceId}`);
  if (
    snapshot.workspaceId !== input.workspaceId
    || snapshot.completeness !== "COMPLETE"
    || snapshot.externalOperationExecuted !== false
    || !sourceCommitPattern.test(snapshot.sourceCommit)
    || !Array.isArray(snapshot.files)
  ) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_WORKSPACE_NOT_COMPLETE",
      "仓库快照不完整或来源状态无法用于项目生成。",
    );
  }
  const requested = [...new Set((input.paths ?? []).map(safeRepositoryFilePath))];
  if (requested.length > maximumGenerationRepositoryFiles) {
    throw new RepositoryWorkspaceProxyError(
      413,
      "REPOSITORY_SOURCE_FILE_COUNT_EXCEEDED",
      "仓库来源文件最多选择 8 个。",
    );
  }
  const catalog = new Map(snapshot.files.map((file) => [file.path, file]));
  const selected = requested.length > 0
    ? requested.map((filePath) => catalog.get(filePath))
    : [...snapshot.files]
      .filter((file) => file.writable)
      .sort((left, right) => sourcePriority(left) - sourcePriority(right)
        || left.path.localeCompare(right.path))
      .slice(0, maximumGenerationRepositoryFiles);
  const selectedFiles = selected.filter(
    (file): file is RepositoryFileEntry => file !== undefined,
  );
  if (
    selectedFiles.length === 0
    || selectedFiles.length !== selected.length
    || selectedFiles.some((file) => !file.writable || !digestPattern.test(file.sha256))
  ) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_SOURCE_FILE_NOT_AVAILABLE",
      "选择的仓库来源文件不存在、受保护或不可读取。",
    );
  }
  const sources: RepositoryGenerationSource[] = [];
  for (const entry of selectedFiles) {
    const filePath = safeRepositoryFilePath(entry.path);
    const content = await controlPlaneJson<RepositoryFileContent>(
      `/${input.workspaceId}/files?${new URLSearchParams({ path: filePath })}`,
    );
    const raw = Buffer.from(content.content, "utf8");
    const digest = createHash("sha256").update(raw).digest("hex");
    if (
      content.workspaceId !== input.workspaceId
      || content.path !== filePath
      || content.encoding !== "UTF-8"
      || content.sha256 !== entry.sha256
      || digest !== entry.sha256
    ) {
      throw new RepositoryWorkspaceProxyError(
        409,
        "REPOSITORY_SOURCE_DIGEST_MISMATCH",
        "仓库来源文件在读取期间发生变化或摘要不一致。",
      );
    }
    const origin = [
      `workspace=${encodeURIComponent(snapshot.workspaceId)}`,
      `provider=${encodeURIComponent(snapshot.provider)}`,
      `instance=${encodeURIComponent(snapshot.providerInstanceId)}`,
      `repository=${encodeURIComponent(snapshot.nativeRepositoryId)}`,
      `commit=${snapshot.sourceCommit}`,
      `path=${encodeURIComponent(filePath)}`,
    ].join(";");
    sources.push({
      path: filePath,
      mediaType: repositoryMediaType(filePath),
      origin,
      raw,
      warnings: [
        "REPOSITORY_WORKSPACE_CONTENT_IMPORTED_NOT_EXECUTED",
        "REMOTE_PUSH_PR_MERGE_AND_DEPLOYMENT_NOT_RUN",
      ],
    });
  }
  return sources;
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
  const headers = trustedHeaders();
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
