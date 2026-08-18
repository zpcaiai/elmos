import { createHash, randomUUID, timingSafeEqual } from "node:crypto";
import {
  lstat,
  mkdir,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import type { NextRequest } from "next/server";
import {
  accountCookieNames,
  AccountSessionError,
  accountSessionFromRequest,
  unsafeCookieValue,
  type AccountPermission,
} from "./accountSession";

const maximumBodyBytes = 3 * 1024 * 1024;
const maximumControlPlaneResponseBytes = 16 * 1024 * 1024;
const maximumGenerationRepositoryFiles = 8;
const maximumTranslationRepositoryFiles = 1_000;
const maximumTranslationRepositoryBytes = 64 * 1024 * 1024;
const requestTimeoutMs = 30_000;
const workspaceIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const sourceCommitPattern = /^[0-9a-f]{40}$/;
const digestPattern = /^[0-9a-f]{64}$/;
const translationCategories = new Set<RepositoryFileEntry["category"]>([
  "SOURCE",
  "DOCUMENTATION",
  "CONFIGURATION",
  "TEST",
]);
const translationMarkerName = ".elmos-repository-source.json";

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
  readable: boolean;
  writable: boolean;
};

type RepositoryWorkspaceSnapshot = {
  workspaceId: string;
  provider: "GITHUB" | "GITEE" | "GENERIC_GIT";
  providerInstanceId: string;
  nativeRepositoryId: string;
  sourceCommit: string;
  currentHeadCommit: string;
  completeness: "COMPLETE" | "INCOMPLETE_SUBMODULES" | "INCOMPLETE_LFS";
  files: RepositoryFileEntry[];
  pendingPaths: string[];
  pushedCommit?: string | null;
  pullRequestId?: string | null;
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

export type RepositorySpringMaterialization = {
  workspaceId: string;
  sourceCommit: string;
  resolvedCommitSha: string;
  relativePath: string;
  manifestSha256: string;
  excludedProtectedPaths: string[];
  status: "MATERIALIZED_VERIFIED";
};

export type RepositoryGenerationSource = {
  path: string;
  mediaType: string;
  origin: string;
  raw: Buffer;
  warnings: string[];
};

export type RepositoryTranslationWorkspace = {
  materializedId: string;
  sourceCommit: string;
  currentHeadCommit: string;
  fileCount: number;
  totalBytes: number;
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

type RepositoryActorContext = {
  organizationId: string;
  actorId: string;
  accessToken?: string;
};

function authorizeBrowser(
  request: NextRequest,
  permission: AccountPermission,
): RepositoryActorContext {
  if (unsafeCookieValue(request, accountCookieNames.session)) {
    try {
      const account = accountSessionFromRequest(request, permission);
      return {
        organizationId: account.principal.organizationId,
        actorId: account.principal.actorId,
        accessToken: account.accessToken,
      };
    } catch (error) {
      if (error instanceof AccountSessionError) {
        throw new RepositoryWorkspaceProxyError(error.status, error.code, error.message);
      }
      throw error;
    }
  }
  if (process.env.NODE_ENV === "production") {
    throw new RepositoryWorkspaceProxyError(
      401,
      "ACCOUNT_SESSION_REQUIRED",
      "请先登录企业账户。",
    );
  }
  const configured = requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_USER_TOKEN", 24);
  const authorization = request.headers.get("authorization") ?? "";
  const headerToken = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  const expectedHash = createHash("sha256").update(configured).digest();
  const presentedHash = createHash("sha256").update(headerToken).digest();
  if (!timingSafeEqual(expectedHash, presentedHash)) {
    throw new RepositoryWorkspaceProxyError(
      401,
      "REPOSITORY_WORKSPACE_SESSION_REQUIRED",
      "需要有效会话才能访问仓库工作区。",
    );
  }
  return {
    organizationId: requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_TENANT_ID"),
    actorId: requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_ACTOR_ID"),
  };
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
  if (parts.length === 2 && ["commit", "push", "pull-request"].includes(parts[1])) {
    return `/${parts[0]}/${parts[1]}`;
  }
  if (parts.length === 3 && parts[1] === "materializations" && parts[2] === "spring") {
    return `/${parts[0]}/materializations/spring`;
  }
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

function trustedHeaders(context: RepositoryActorContext): Headers {
  const headers = new Headers({
    "Accept": "application/json",
    "X-ELMOS-Organization-ID": context.organizationId,
    "X-ELMOS-Actor-ID": context.actorId,
    "X-Request-ID": randomUUID(),
  });
  if (context.accessToken) {
    headers.set("Authorization", `Bearer ${context.accessToken}`);
  } else {
    headers.set(
      "X-ELMOS-Repository-Key",
      requiredEnvironment("ELMOS_REPOSITORY_WORKSPACE_API_KEY", 24),
    );
  }
  return headers;
}

function safeRepositoryFilePath(value: string): string {
  const candidate = value.trim();
  if (
    !candidate
    || candidate !== value
    || candidate.length > 512
    || candidate.startsWith("/")
    || candidate.includes("\\")
    || candidate.split("/").includes("..")
    || [...candidate].some((character) => character.codePointAt(0)! < 32 || character.codePointAt(0) === 127)
  ) {
    throw new RepositoryWorkspaceProxyError(
      400,
      "REPOSITORY_FILE_PATH_INVALID",
      "仓库来源文件路径无效。",
    );
  }
  return candidate;
}

type TranslationManifestFile = Pick<RepositoryFileEntry, "path" | "bytes" | "sha256" | "category">;

function translationManifestFiles(files: RepositoryFileEntry[]): TranslationManifestFile[] {
  const normalized = files.map((file) => ({
    path: safeRepositoryFilePath(file.path),
    bytes: file.bytes,
    sha256: file.sha256,
    category: file.category,
  })).sort((left, right) => left.path.localeCompare(right.path));
  if (
    normalized.some((file) => (
      !Number.isSafeInteger(file.bytes)
      || file.bytes < 0
      || file.bytes > maximumTranslationRepositoryBytes
      || !digestPattern.test(file.sha256)
      || !translationCategories.has(file.category)
    ))
    || new Set(normalized.map((file) => file.path)).size !== normalized.length
  ) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_TRANSLATION_SOURCE_MANIFEST_INVALID",
      "仓库转换来源清单无效或包含重复路径。",
    );
  }
  return normalized;
}

function translationManifestSha256(input: {
  tenantId: string;
  workspaceId: string;
  sourceCommit: string;
  currentHeadCommit: string;
  files: TranslationManifestFile[];
}): string {
  return createHash("sha256").update(JSON.stringify(input)).digest("hex");
}

async function stableMaterializedFile(
  file: string,
  expected: { bytes: number; sha256: string },
): Promise<void> {
  const before = await lstat(file);
  if (!before.isFile() || before.isSymbolicLink() || before.nlink !== 1) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
      "仓库转换来源包含不安全或已漂移的文件。",
    );
  }
  const content = await readFile(file);
  const after = await lstat(file);
  if (
    before.dev !== after.dev
    || before.ino !== after.ino
    || before.size !== after.size
    || before.mtimeMs !== after.mtimeMs
    || content.length !== before.size
    || content.length !== expected.bytes
    || createHash("sha256").update(content).digest("hex") !== expected.sha256
  ) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
      "仓库转换来源文件摘要与已授权提交不一致。",
    );
  }
}

async function materializedRelativeFiles(root: string): Promise<string[]> {
  const rootInfo = await lstat(root);
  if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
      "仓库转换来源目录不安全。",
    );
  }
  const canonicalRoot = await realpath(root);
  const observed: string[] = [];
  const visit = async (directory: string, prefix: string): Promise<void> => {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      safeRepositoryFilePath(relative);
      const candidate = path.resolve(directory, entry.name);
      const info = await lstat(candidate);
      if (info.isSymbolicLink()) {
        throw new RepositoryWorkspaceProxyError(
          409,
          "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
          "仓库转换来源包含符号链接。",
        );
      }
      const canonical = await realpath(candidate);
      if (!canonical.startsWith(`${canonicalRoot}${path.sep}`)) {
        throw new RepositoryWorkspaceProxyError(
          409,
          "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
          "仓库转换来源路径逸出物化目录。",
        );
      }
      if (info.isDirectory()) {
        await visit(candidate, relative);
      } else if (info.isFile() && info.nlink === 1) {
        observed.push(relative);
        if (observed.length > maximumTranslationRepositoryFiles + 1) {
          throw new RepositoryWorkspaceProxyError(
            409,
            "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
            "仓库转换来源出现额外文件。",
          );
        }
      } else {
        throw new RepositoryWorkspaceProxyError(
          409,
          "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
          "仓库转换来源包含不支持的文件类型。",
        );
      }
    }
  };
  await visit(root, "");
  return observed.sort();
}

async function controlPlaneJson<T>(
  targetPath: string,
  context: RepositoryActorContext,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${controlPlaneBaseUrl()}/api/v1/repository-workspaces${targetPath}`, {
      method: "GET",
      headers: trustedHeaders(context),
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
  accessToken?: string;
  workspaceId: string;
  paths?: string[];
}): Promise<RepositoryGenerationSource[]> {
  const context = {
    organizationId: input.tenantId,
    actorId: input.actor,
    accessToken: input.accessToken,
  };
  if (!workspaceIdPattern.test(input.workspaceId)) {
    throw new RepositoryWorkspaceProxyError(
      400,
      "REPOSITORY_WORKSPACE_ID_INVALID",
      "仓库工作区 ID 无效。",
    );
  }
  const snapshot = await controlPlaneJson<RepositoryWorkspaceSnapshot>(
    `/${input.workspaceId}`,
    context,
  );
  if (
    snapshot.workspaceId !== input.workspaceId
    || snapshot.completeness !== "COMPLETE"
    || !sourceCommitPattern.test(snapshot.sourceCommit)
    || !sourceCommitPattern.test(snapshot.currentHeadCommit)
    || !Array.isArray(snapshot.files)
    || !Array.isArray(snapshot.pendingPaths)
    || snapshot.pendingPaths.length > 0
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
      context,
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
      `sourceCommit=${snapshot.sourceCommit}`,
      `headCommit=${snapshot.currentHeadCommit}`,
      `path=${encodeURIComponent(filePath)}`,
    ].join(";");
    sources.push({
      path: filePath,
      mediaType: repositoryMediaType(filePath),
      origin,
      raw,
      warnings: [
        "REPOSITORY_WORKSPACE_CONTENT_IMPORTED_NOT_EXECUTED",
        snapshot.pullRequestId
          ? "PULL_REQUEST_EXISTS_MERGE_AND_DEPLOYMENT_NOT_RUN"
          : snapshot.pushedCommit
            ? "REMOTE_BRANCH_EXISTS_MERGE_AND_DEPLOYMENT_NOT_RUN"
            : "REMOTE_PUSH_PR_MERGE_AND_DEPLOYMENT_NOT_RUN",
      ],
    });
  }
  return sources;
}

export async function repositoryTranslationWorkspace(input: {
  tenantId: string;
  actor: string;
  accessToken?: string;
  workspaceId: string;
  sourceRoot: string;
}): Promise<RepositoryTranslationWorkspace> {
  if (!workspaceIdPattern.test(input.workspaceId)) {
    throw new RepositoryWorkspaceProxyError(
      400, "REPOSITORY_WORKSPACE_ID_INVALID", "仓库工作区 ID 无效。",
    );
  }
  const context = {
    organizationId: input.tenantId,
    actorId: input.actor,
    accessToken: input.accessToken,
  };
  const snapshot = await controlPlaneJson<RepositoryWorkspaceSnapshot>(
    `/${input.workspaceId}`,
    context,
  );
  if (
    snapshot.workspaceId !== input.workspaceId
    || snapshot.completeness !== "COMPLETE"
    || !sourceCommitPattern.test(snapshot.sourceCommit)
    || !sourceCommitPattern.test(snapshot.currentHeadCommit)
    || !Array.isArray(snapshot.files)
    || !Array.isArray(snapshot.pendingPaths)
    || snapshot.pendingPaths.length > 0
  ) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_TRANSLATION_SOURCE_NOT_IMMUTABLE",
      "语言转换仅接受完整且无待提交变更的仓库工作区。",
    );
  }
  if (snapshot.files.some((file) => typeof file.readable !== "boolean" || typeof file.writable !== "boolean")) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_TRANSLATION_READABILITY_EVIDENCE_MISSING",
      "仓库文件缺少独立的可读性证据，不能安全物化转换来源。",
    );
  }
  if (snapshot.files.some((file) => file.category === "SOURCE" && !file.readable)) {
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_TRANSLATION_PROTECTED_SOURCE_EXCLUDED",
      "仓库含不可读取的受保护源码；请先创建不含秘密且授权完整的转换快照。",
    );
  }
  // Translation is read-only. Protected/branch-governed source must remain in
  // the functional denominator even when it is not writable. Secret-bearing
  // files are independently unreadable and are never requested from the
  // control plane.
  const selected = snapshot.files.filter(
    (file) => file.readable && translationCategories.has(file.category),
  );
  const manifestFiles = translationManifestFiles(selected);
  const declaredBytes = selected.reduce((total, file) => total + file.bytes, 0);
  if (
    selected.length === 0
    || selected.length > maximumTranslationRepositoryFiles
    || declaredBytes > maximumTranslationRepositoryBytes
  ) {
    throw new RepositoryWorkspaceProxyError(
      413,
      "REPOSITORY_TRANSLATION_SCOPE_EXCEEDED",
      "仓库可转换文本范围超过 1000 个文件或 64 MB，需先拆分工作区。",
    );
  }
  const manifestSha256 = translationManifestSha256({
    tenantId: input.tenantId,
    workspaceId: input.workspaceId,
    sourceCommit: snapshot.sourceCommit,
    currentHeadCommit: snapshot.currentHeadCommit,
    files: manifestFiles,
  });
  // A workspace UUID is mutable as its branch advances. Bind the cache path to
  // the tenant and exact authorized snapshot so a newer commit cannot collide
  // with, or silently reuse, an older tenant's materialization.
  const materializedId = `repo-${manifestSha256.slice(0, 48)}`;
  const destination = path.resolve(input.sourceRoot, materializedId);
  const root = path.resolve(input.sourceRoot);
  if (!destination.startsWith(`${root}${path.sep}`)) {
    throw new RepositoryWorkspaceProxyError(
      400, "REPOSITORY_TRANSLATION_PATH_INVALID", "仓库转换工作区路径无效。",
    );
  }
  const marker = path.join(destination, ".elmos-repository-source.json");
  try {
    const markerInfo = await lstat(marker);
    if (!markerInfo.isFile() || markerInfo.isSymbolicLink() || markerInfo.nlink !== 1) {
      throw new RepositoryWorkspaceProxyError(
        409,
        "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
        "仓库转换来源标记不安全。",
      );
    }
    const existing = JSON.parse(await readFile(marker, "utf8")) as {
      tenantId?: string;
      workspaceId?: string;
      sourceCommit?: string;
      currentHeadCommit?: string;
      manifestSha256?: string;
      files?: TranslationManifestFile[];
    };
    if (
      existing.tenantId === input.tenantId
      && existing.workspaceId === input.workspaceId
      && existing.sourceCommit === snapshot.sourceCommit
      && existing.currentHeadCommit === snapshot.currentHeadCommit
      && existing.manifestSha256 === manifestSha256
      && JSON.stringify(existing.files) === JSON.stringify(manifestFiles)
    ) {
      const observed = await materializedRelativeFiles(destination);
      const expected = [...manifestFiles.map((file) => file.path), translationMarkerName].sort();
      if (JSON.stringify(observed) !== JSON.stringify(expected)) {
        throw new RepositoryWorkspaceProxyError(
          409,
          "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
          "仓库转换来源包含缺失或额外文件。",
        );
      }
      for (const file of manifestFiles) {
        await stableMaterializedFile(path.resolve(destination, file.path), file);
      }
      return {
        materializedId,
        sourceCommit: snapshot.sourceCommit,
        currentHeadCommit: snapshot.currentHeadCommit,
        fileCount: selected.length,
        totalBytes: declaredBytes,
      };
    }
    throw new RepositoryWorkspaceProxyError(
      409,
      "REPOSITORY_TRANSLATION_MATERIALIZATION_CONFLICT",
      "同名转换来源与当前仓库提交不一致。",
    );
  } catch (error) {
    if (error instanceof RepositoryWorkspaceProxyError) throw error;
    try {
      await lstat(destination);
      throw new RepositoryWorkspaceProxyError(
        409,
        "REPOSITORY_TRANSLATION_MATERIALIZATION_DRIFT",
        "既有仓库转换来源缺少可验证的内容清单。",
      );
    } catch (destinationError) {
      if (destinationError instanceof RepositoryWorkspaceProxyError) throw destinationError;
      if ((destinationError as NodeJS.ErrnoException).code !== "ENOENT") throw destinationError;
    }
  }
  const temporary = path.resolve(root, `.${materializedId}.${randomUUID()}.tmp`);
  await mkdir(temporary, { recursive: false, mode: 0o700 });
  let actualBytes = 0;
  try {
    for (const entry of selected) {
      const filePath = safeRepositoryFilePath(entry.path);
      const content = await controlPlaneJson<RepositoryFileContent>(
        `/${input.workspaceId}/files?${new URLSearchParams({ path: filePath })}`,
        context,
      );
      const raw = Buffer.from(content.content, "utf8");
      const digest = createHash("sha256").update(raw).digest("hex");
      if (
        content.workspaceId !== input.workspaceId
        || content.path !== filePath
        || content.category !== entry.category
        || content.encoding !== "UTF-8"
        || content.sha256 !== entry.sha256
        || digest !== entry.sha256
        || raw.length !== entry.bytes
      ) {
        throw new RepositoryWorkspaceProxyError(
          409,
          "REPOSITORY_TRANSLATION_DIGEST_MISMATCH",
          "仓库文件在转换来源物化期间发生变化。",
        );
      }
      actualBytes += raw.length;
      if (actualBytes > maximumTranslationRepositoryBytes) {
        throw new RepositoryWorkspaceProxyError(
          413,
          "REPOSITORY_TRANSLATION_SCOPE_EXCEEDED",
          "仓库转换来源实际大小超过 64 MB。",
        );
      }
      const target = path.resolve(temporary, filePath);
      if (!target.startsWith(`${temporary}${path.sep}`)) {
        throw new RepositoryWorkspaceProxyError(
          400, "REPOSITORY_TRANSLATION_PATH_INVALID", "仓库文件路径逸出物化目录。",
        );
      }
      await mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
      await writeFile(target, raw, { mode: 0o600, flag: "wx" });
    }
    await writeFile(
      path.join(temporary, translationMarkerName),
      `${JSON.stringify({
        schemaVersion: "1.0",
        tenantId: input.tenantId,
        workspaceId: input.workspaceId,
        sourceCommit: snapshot.sourceCommit,
        currentHeadCommit: snapshot.currentHeadCommit,
        includedCategories: ["SOURCE", "DOCUMENTATION", "CONFIGURATION", "TEST"],
        includedReadableReadOnlySources: true,
        excludedDeploymentAndBinaryAssets: true,
        fileCount: selected.length,
        totalBytes: actualBytes,
        manifestSha256,
        files: manifestFiles,
      }, null, 2)}\n`,
      { mode: 0o600, flag: "wx" },
    );
    try {
      await rename(temporary, destination);
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code === "EEXIST" || code === "ENOTEMPTY") {
        // Another process won the same content-addressed publication race.
        // Re-enter through the normal cache verifier; never trust the winner
        // merely because the destination now exists.
        await rm(temporary, { recursive: true, force: true });
        return repositoryTranslationWorkspace(input);
      }
      throw error;
    }
  } catch (error) {
    await rm(temporary, { recursive: true, force: true });
    throw error;
  }
  return {
    materializedId,
    sourceCommit: snapshot.sourceCommit,
    currentHeadCommit: snapshot.currentHeadCommit,
    fileCount: selected.length,
    totalBytes: actualBytes,
  };
}

export async function repositorySpringMaterialization(
  request: NextRequest,
  workspaceId: string,
  expectedHeadCommit: string,
): Promise<RepositorySpringMaterialization> {
  if (!workspaceIdPattern.test(workspaceId) || !sourceCommitPattern.test(expectedHeadCommit)) {
    throw new RepositoryWorkspaceProxyError(
      400, "REPOSITORY_SPRING_SOURCE_INVALID", "Spring 仓库工作区来源无效。",
    );
  }
  const actor = authorizeBrowser(request, "spring:execute");
  const headers = trustedHeaders(actor);
  headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(
      `${controlPlaneBaseUrl()}/api/v1/repository-workspaces/${workspaceId}/materializations/spring`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ expectedHeadCommit }),
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(120_000),
      },
    );
  } catch {
    throw new RepositoryWorkspaceProxyError(
      503,
      "REPOSITORY_SPRING_MATERIALIZATION_UNAVAILABLE",
      "Spring 仓库来源物化服务暂时不可用。",
      true,
    );
  }
  const payload = await response.json().catch(() => null) as
    | RepositorySpringMaterialization
    | { errorCode?: string; message?: string; retryable?: boolean }
    | null;
  if (!response.ok || !payload || !("resolvedCommitSha" in payload)) {
    const error = payload && !("resolvedCommitSha" in payload) ? payload : {};
    throw new RepositoryWorkspaceProxyError(
      response.status,
      error?.errorCode ?? "REPOSITORY_SPRING_MATERIALIZATION_FAILED",
      error?.message ?? "Spring 仓库来源物化失败。",
      error?.retryable === true,
    );
  }
  if (
    payload.workspaceId !== workspaceId
    || payload.resolvedCommitSha !== expectedHeadCommit
    || payload.status !== "MATERIALIZED_VERIFIED"
    || !digestPattern.test(payload.manifestSha256)
    || !payload.relativePath
    || payload.relativePath.startsWith("/")
    || payload.relativePath.split("/").includes("..")
  ) {
    throw new RepositoryWorkspaceProxyError(
      502,
      "REPOSITORY_SPRING_MATERIALIZATION_EVIDENCE_INVALID",
      "Spring 仓库物化结果未通过身份、提交与摘要校验。",
    );
  }
  return payload;
}

export async function repositoryWorkspaceRequest(
  request: NextRequest,
  parts: string[],
): Promise<Response> {
  const method = request.method;
  if (!["GET", "POST", "DELETE"].includes(method)) {
    throw new RepositoryWorkspaceProxyError(405, "REPOSITORY_METHOD_NOT_ALLOWED", "请求方法不受支持。");
  }
  const actor = authorizeBrowser(
    request,
    method === "GET"
      ? "repository:read"
      : parts[1] === "commit"
        ? "repository:commit"
        : parts[1] === "push"
          ? "repository:push"
          : parts[1] === "pull-request"
            ? "repository:pr"
            : "repository:write",
  );
  const targetPath = validatePath(parts, request.nextUrl.searchParams);
  if (method === "POST" && targetPath !== ""
      && !["/changes", "/commit", "/push", "/pull-request"].some(
        (suffix) => targetPath.endsWith(suffix),
      ) && !targetPath.endsWith("/materializations/spring")) {
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
  const headers = trustedHeaders(actor);
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
