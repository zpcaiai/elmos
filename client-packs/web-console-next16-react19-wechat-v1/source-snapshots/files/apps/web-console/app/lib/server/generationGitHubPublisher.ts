import { createHash, randomUUID } from "node:crypto";
import type { GenerationGitHubPublication, GenerationJob } from "../contracts";
import {
  GenerationRunnerError,
  generationPublishSnapshot,
  recordGenerationGitHubPublication,
  withGenerationPublicationOperation,
  type AuthorizedContext,
  type GenerationPublishFile,
} from "./generationRunner";

const repositoryNamePattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;
const ownerPattern = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/;
const tenantPattern = /^[a-z][a-z0-9-]{2,62}$/;
const gitObjectDigestPattern = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/;
const idempotencyKeyPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const maximumGitHubJsonResponseBytes = 2 * 1024 * 1024;
const maximumConcurrentPublications = 1;
const maximumConcurrentPublicationsPerTenant = 1;
const activePublications = new Set<string>();
const activePublicationsByTenant = new Map<string, number>();

export type GenerationGitHubPublishRequest = {
  repositoryName: string;
  owner?: string;
  description?: string;
  token: string;
  artifactSha256: string;
  idempotencyKey: string;
  confirmed: boolean;
};

type GitHubRepository = {
  id?: unknown;
  name?: unknown;
  full_name?: unknown;
  html_url?: unknown;
  private?: unknown;
  default_branch?: unknown;
  description?: unknown;
  owner?: { login?: unknown };
};

export class GenerationGitHubPublishError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

function apiBase(): string {
  const configured = process.env.ELMOS_GENERATION_GITHUB_API_BASE?.trim()
    || "https://api.github.com";
  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    throw new GenerationGitHubPublishError(503, "GITHUB_API_BASE_INVALID");
  }
  const localTest = process.env.NODE_ENV !== "production"
    && process.env.ELMOS_GENERATION_GITHUB_ALLOW_HTTP_LOCALHOST === "true"
    && parsed.protocol === "http:"
    && ["127.0.0.1", "localhost"].includes(parsed.hostname);
  const allowedHosts = new Set(
    (process.env.ELMOS_GENERATION_GITHUB_ALLOWED_API_HOSTS ?? "")
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean),
  );
  if (
    (parsed.protocol !== "https:" && !localTest)
    || (!localTest && parsed.hostname !== "api.github.com" && !allowedHosts.has(parsed.host.toLowerCase()))
    || parsed.username
    || parsed.password
    || parsed.search
    || parsed.hash
  ) throw new GenerationGitHubPublishError(503, "GITHUB_API_BASE_INVALID");
  return parsed.toString().replace(/\/$/, "");
}

function validate(rawInput: unknown): GenerationGitHubPublishRequest {
  if (!rawInput || typeof rawInput !== "object" || Array.isArray(rawInput)) {
    throw new GenerationGitHubPublishError(400, "GITHUB_PUBLISH_REQUEST_INVALID");
  }
  const input = rawInput as Partial<GenerationGitHubPublishRequest>;
  const repositoryName = typeof input.repositoryName === "string"
    ? input.repositoryName.trim()
    : "";
  const owner = typeof input.owner === "string" ? input.owner.trim() || undefined : undefined;
  const description = typeof input.description === "string"
    ? input.description.trim() || undefined
    : undefined;
  const token = typeof input.token === "string" ? input.token.trim() : "";
  if (
    input.confirmed !== true
    || (input.owner !== undefined && typeof input.owner !== "string")
    || (input.description !== undefined && typeof input.description !== "string")
    || !repositoryNamePattern.test(repositoryName)
    || repositoryName === "."
    || repositoryName === ".."
    || repositoryName.toLowerCase().endsWith(".git")
    || owner && !ownerPattern.test(owner)
    || description && (description.length > 350 || /[\0\r\n]/.test(description))
    || token.length < 20
    || token.length > 512
    || /\s/.test(token)
    || typeof input.artifactSha256 !== "string"
    || !/^[0-9a-f]{64}$/.test(input.artifactSha256)
    || typeof input.idempotencyKey !== "string"
    || !idempotencyKeyPattern.test(input.idempotencyKey)
  ) throw new GenerationGitHubPublishError(400, "GITHUB_PUBLISH_REQUEST_INVALID");
  return {
    repositoryName,
    ...(owner ? { owner } : {}),
    ...(description ? { description } : {}),
    token,
    artifactSha256: input.artifactSha256,
    idempotencyKey: input.idempotencyKey,
    confirmed: true,
  };
}

function safePath(owner: string, repository: string, suffix: string): string {
  return `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repository)}${suffix}`;
}

function repositoryUrlMatches(value: string, owner: string, repository: string): boolean {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  const base = new URL(apiBase());
  const allowedWebHosts = new Set(
    (process.env.ELMOS_GENERATION_GITHUB_ALLOWED_WEB_HOSTS ?? "")
      .split(",")
      .map((host) => host.trim().toLowerCase())
      .filter(Boolean),
  );
  if (base.hostname === "api.github.com") {
    allowedWebHosts.add("github.com");
  } else if (base.protocol === "https:") {
    allowedWebHosts.add(base.host.toLowerCase());
  } else if (
    process.env.NODE_ENV !== "production"
    && process.env.ELMOS_GENERATION_GITHUB_ALLOW_HTTP_LOCALHOST === "true"
    && ["127.0.0.1", "localhost"].includes(base.hostname)
  ) {
    allowedWebHosts.add("github.example.invalid");
  }
  return url.protocol === "https:"
    && !url.username
    && !url.password
    && !url.search
    && !url.hash
    && allowedWebHosts.has(url.host.toLowerCase())
    && url.pathname.toLowerCase() === `/${owner}/${repository}`.toLowerCase();
}

async function githubResponse(
  method: string,
  target: string,
  token: string,
  body: unknown,
  expected: readonly number[],
  deadline: number,
  accept: string,
): Promise<Response> {
  const apiVersion = process.env.ELMOS_GENERATION_GITHUB_API_VERSION?.trim()
    || "2022-11-28";
  if (!/^20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$/.test(apiVersion)) {
    throw new GenerationGitHubPublishError(503, "GITHUB_API_VERSION_INVALID");
  }
  const base = apiBase();
  const remaining = deadline - Date.now();
  if (remaining <= 0) {
    throw new GenerationGitHubPublishError(504, "GITHUB_PUBLICATION_DEADLINE_EXCEEDED");
  }
  let response: Response;
  try {
    response = await fetch(`${base}${target}`, {
      method,
      headers: {
        "Accept": accept,
        "Accept-Encoding": "identity",
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
        "User-Agent": "ELMOS-Web-Console/0.1",
        "X-GitHub-Api-Version": apiVersion,
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(Math.min(30_000, remaining)),
    });
  } catch {
    throw new GenerationGitHubPublishError(503, "GITHUB_API_UNAVAILABLE");
  }
  if (!expected.includes(response.status)) {
    await response.body?.cancel().catch(() => undefined);
    const code = response.status === 401
      ? "GITHUB_CREDENTIAL_REJECTED"
      : response.status === 403
        ? "GITHUB_PERMISSION_OR_RATE_LIMIT_DENIED"
        : response.status === 404
          ? "GITHUB_OWNER_OR_REPOSITORY_NOT_FOUND"
          : response.status === 409
            ? "GITHUB_REPOSITORY_STATE_CONFLICT"
            : response.status === 422
              ? "GITHUB_REPOSITORY_ALREADY_EXISTS_OR_VALIDATION_FAILED"
              : "GITHUB_API_REQUEST_FAILED";
    throw new GenerationGitHubPublishError(
      response.status >= 500 ? 503 : response.status,
      code,
    );
  }
  return response;
}

function declaredResponseLength(response: Response, maximumBytes: number): void {
  const declaredHeader = response.headers.get("content-length");
  if (declaredHeader === null) return;
  if (!/^\d{1,16}$/.test(declaredHeader)) {
    throw new GenerationGitHubPublishError(502, "GITHUB_API_RESPONSE_TOO_LARGE");
  }
  const declaredLength = Number(declaredHeader);
  if (!Number.isSafeInteger(declaredLength) || declaredLength > maximumBytes) {
    throw new GenerationGitHubPublishError(502, "GITHUB_API_RESPONSE_TOO_LARGE");
  }
}

async function readResponseBufferBounded(
  response: Response,
  maximumBytes: number,
): Promise<Buffer> {
  try {
    declaredResponseLength(response, maximumBytes);
  } catch (error) {
    await response.body?.cancel().catch(() => undefined);
    throw error;
  }
  if (!response.body) return Buffer.alloc(0);
  const reader = response.body.getReader();
  const chunks: Buffer[] = [];
  let byteLength = 0;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      byteLength += next.value.byteLength;
      if (byteLength > maximumBytes) {
        await reader.cancel().catch(() => undefined);
        throw new GenerationGitHubPublishError(502, "GITHUB_API_RESPONSE_TOO_LARGE");
      }
      chunks.push(Buffer.from(next.value));
    }
  } catch (error) {
    if (error instanceof GenerationGitHubPublishError) throw error;
    throw new GenerationGitHubPublishError(502, "GITHUB_API_RESPONSE_READ_FAILED");
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks, byteLength);
}

async function readResponseDigestBounded(
  response: Response,
  maximumBytes: number,
): Promise<{ byteLength: number; sha256: string }> {
  try {
    declaredResponseLength(response, maximumBytes);
  } catch (error) {
    await response.body?.cancel().catch(() => undefined);
    throw error;
  }
  const digest = createHash("sha256");
  if (!response.body) return { byteLength: 0, sha256: digest.digest("hex") };
  const reader = response.body.getReader();
  let byteLength = 0;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      byteLength += next.value.byteLength;
      if (byteLength > maximumBytes) {
        await reader.cancel().catch(() => undefined);
        throw new GenerationGitHubPublishError(502, "GITHUB_API_RESPONSE_TOO_LARGE");
      }
      digest.update(next.value);
    }
  } catch (error) {
    if (error instanceof GenerationGitHubPublishError) throw error;
    throw new GenerationGitHubPublishError(502, "GITHUB_API_RESPONSE_READ_FAILED");
  } finally {
    reader.releaseLock();
  }
  return { byteLength, sha256: digest.digest("hex") };
}

async function githubJson<T>(
  method: string,
  target: string,
  token: string,
  body: unknown,
  expected: readonly number[],
  deadline: number,
): Promise<T> {
  const response = await githubResponse(
    method,
    target,
    token,
    body,
    expected,
    deadline,
    "application/vnd.github+json",
  );
  if (response.status === 204) return undefined as T;
  const raw = (await readResponseBufferBounded(
    response,
    maximumGitHubJsonResponseBytes,
  )).toString("utf-8");
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new GenerationGitHubPublishError(502, "GITHUB_API_RESPONSE_INVALID");
  }
}

async function verifyGitHubBlob(
  owner: string,
  repository: string,
  token: string,
  blobSha: string,
  file: GenerationPublishFile,
  deadline: number,
): Promise<void> {
  const response = await githubResponse(
    "GET",
    safePath(owner, repository, `/git/blobs/${blobSha}`),
    token,
    undefined,
    [200],
    deadline,
    "application/vnd.github.raw+json",
  );
  const observed = await readResponseDigestBounded(response, file.content.length);
  if (observed.byteLength !== file.content.length || observed.sha256 !== file.sha256) {
    throw new GenerationGitHubPublishError(502, "GITHUB_BLOB_CONTENT_VERIFICATION_FAILED");
  }
}

async function createBlobs(
  owner: string,
  repository: string,
  token: string,
  files: GenerationPublishFile[],
  deadline: number,
): Promise<Array<{ path: string; mode: "100644" | "100755"; sha: string }>> {
  const output: Array<{ path: string; mode: "100644" | "100755"; sha: string }> = [];
  for (let offset = 0; offset < files.length; offset += 4) {
    const batch = files.slice(offset, offset + 4);
    const outcomes = await Promise.allSettled(batch.map(async (file) => {
      const blob = await githubJson<{ sha?: unknown }>(
        "POST",
        safePath(owner, repository, "/git/blobs"),
        token,
        { content: file.content.toString("base64"), encoding: "base64" },
        [201],
        deadline,
      );
      if (typeof blob.sha !== "string" || !gitObjectDigestPattern.test(blob.sha)) {
        throw new GenerationGitHubPublishError(502, "GITHUB_BLOB_RECEIPT_INVALID");
      }
      await verifyGitHubBlob(owner, repository, token, blob.sha, file, deadline);
      return { path: file.path, mode: file.mode, sha: blob.sha };
    }));
    const failed = outcomes.find(
      (outcome): outcome is PromiseRejectedResult => outcome.status === "rejected",
    );
    if (failed) {
      if (failed.reason instanceof GenerationGitHubPublishError) throw failed.reason;
      throw new GenerationGitHubPublishError(502, "GITHUB_BLOB_CONTENT_VERIFICATION_FAILED");
    }
    output.push(...outcomes.map((outcome) => (
      outcome as PromiseFulfilledResult<{ path: string; mode: "100644" | "100755"; sha: string }>
    ).value));
  }
  return output;
}

function publicationMarker(idempotencyKey: string): string {
  return `ELMOS-Publication-ID:${idempotencyKey}`;
}

function repositoryDescription(input: GenerationGitHubPublishRequest): string {
  const suffix = `${publicationMarker(input.idempotencyKey)} | Artifact-SHA256:${input.artifactSha256}`;
  const prefixBudget = Math.max(0, 350 - suffix.length - 3);
  const prefix = input.description && prefixBudget > 0
    ? `${input.description.slice(0, prefixBudget)} | `
    : "";
  return `${prefix}${suffix}`;
}

function repositoryIdentityMatches(
  repository: GitHubRepository,
  owner: string,
  name: string,
  expectedDescription: string,
): repository is GitHubRepository & { id: number; full_name: string; html_url: string } {
  return Number.isSafeInteger(repository.id)
    && Number(repository.id) > 0
    && repository.private === true
    && typeof repository.name === "string"
    && repository.name.toLowerCase() === name.toLowerCase()
    && typeof repository.full_name === "string"
    && repository.full_name.toLowerCase() === `${owner}/${name}`.toLowerCase()
    && typeof repository.owner?.login === "string"
    && repository.owner.login.toLowerCase() === owner.toLowerCase()
    && typeof repository.html_url === "string"
    && repositoryUrlMatches(repository.html_url, owner, name)
    && typeof repository.description === "string"
    && repository.description === expectedDescription;
}

function allowedOwnersForContext(context: AuthorizedContext): Set<string> | undefined {
  if (process.env.NODE_ENV !== "production") return undefined;
  const allowedTenantId = process.env.ELMOS_GENERATION_GITHUB_ALLOWED_TENANT_ID?.trim() ?? "";
  const allowedOwners = new Set(
    (process.env.ELMOS_GENERATION_GITHUB_ALLOWED_OWNERS ?? "")
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean),
  );
  if (!tenantPattern.test(allowedTenantId) || allowedOwners.size === 0) {
    throw new GenerationGitHubPublishError(
      503,
      "GITHUB_OWNER_TENANT_BINDING_NOT_CONFIGURED",
    );
  }
  if (context.tenantId !== allowedTenantId) {
    throw new GenerationGitHubPublishError(403, "GITHUB_TENANT_NOT_APPROVED");
  }
  return allowedOwners;
}

async function resolveExpectedOwner(
  input: GenerationGitHubPublishRequest,
  deadline: number,
  allowedOwners: Set<string> | undefined,
): Promise<string> {
  let owner = input.owner;
  if (!owner) {
    const user = await githubJson<{ login?: unknown }>(
      "GET", "/user", input.token, undefined, [200], deadline,
    );
    if (typeof user.login !== "string" || !ownerPattern.test(user.login)) {
      throw new GenerationGitHubPublishError(502, "GITHUB_ACCOUNT_IDENTITY_INVALID");
    }
    owner = user.login;
  }
  if (allowedOwners && !allowedOwners.has(owner.toLowerCase())) {
    throw new GenerationGitHubPublishError(403, "GITHUB_OWNER_NOT_APPROVED");
  }
  return owner;
}

function exactPublishedReceipt(
  existing: GenerationGitHubPublication | undefined,
  input: GenerationGitHubPublishRequest,
  expectedOwner: string,
): boolean {
  if (existing?.status !== "PUBLISHED") return false;
  const expectedName = `${expectedOwner}/${input.repositoryName}`.toLowerCase();
  return existing.artifactSha256 === input.artifactSha256
    && existing.idempotencyKey === input.idempotencyKey
    && existing.repositoryFullName?.toLowerCase() === expectedName;
}

async function publishGenerationToGitHubLocked(
  context: AuthorizedContext,
  jobId: string,
  rawInput: GenerationGitHubPublishRequest,
): Promise<GenerationJob> {
  const input = validate(rawInput);
  const deadline = Date.now() + 10 * 60_000;
  const operationKey = `${context.tenantId}:${jobId}`;
  if (activePublications.has(operationKey)) {
    throw new GenerationGitHubPublishError(409, "GITHUB_PUBLICATION_ALREADY_IN_PROGRESS");
  }
  const tenantActivePublications = activePublicationsByTenant.get(context.tenantId) ?? 0;
  if (tenantActivePublications >= maximumConcurrentPublicationsPerTenant) {
    throw new GenerationGitHubPublishError(
      429,
      "GITHUB_TENANT_PUBLICATION_CAPACITY_EXCEEDED",
    );
  }
  if (activePublications.size >= maximumConcurrentPublications) {
    throw new GenerationGitHubPublishError(429, "GITHUB_PUBLICATION_CAPACITY_EXCEEDED");
  }
  activePublications.add(operationKey);
  activePublicationsByTenant.set(context.tenantId, tenantActivePublications + 1);
  try {
    const snapshot = await generationPublishSnapshot(context, jobId);
    if (snapshot.existingPublication?.status === "CREATING") {
      const pending = snapshot.existingPublication;
      await recordGenerationGitHubPublication(context, jobId, {
        status: "BLOCKED",
        repositoryFullName: pending.repositoryFullName,
        artifactSha256: pending.artifactSha256,
        idempotencyKey: pending.idempotencyKey,
        reason: "GITHUB_CREATION_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED",
        updatedAt: new Date().toISOString(),
      });
      throw new GenerationGitHubPublishError(
        409,
        "GITHUB_CREATION_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED",
      );
    }
    if (
      snapshot.existingPublication?.reason?.includes("MANUAL_CLEANUP_REQUIRED")
      || snapshot.existingPublication?.reason?.includes("RECONCILIATION_REQUIRED")
    ) {
      throw new GenerationGitHubPublishError(409, "GITHUB_PUBLICATION_RECONCILIATION_REQUIRED");
    }
    if (snapshot.artifactSha256 !== input.artifactSha256) {
      throw new GenerationGitHubPublishError(409, "GITHUB_PUBLISH_ARTIFACT_DIGEST_MISMATCH");
    }
    const allowedOwners = allowedOwnersForContext(context);
    const expectedOwner = await resolveExpectedOwner(input, deadline, allowedOwners);
    const expectedFullName = `${expectedOwner}/${input.repositoryName}`;
    const description = repositoryDescription(input);
    if (exactPublishedReceipt(snapshot.existingPublication, input, expectedOwner)) {
      return recordGenerationGitHubPublication(
        context,
        jobId,
        snapshot.existingPublication as GenerationGitHubPublication,
      );
    }
    if (snapshot.existingPublication?.status === "PUBLISHED") {
      throw new GenerationGitHubPublishError(409, "GITHUB_PUBLICATION_ALREADY_RECORDED");
    }
    let repositoryId = 0;
    let repositoryUrl = "";
    let createdThisAttemptConfirmed = false;
    let creationAttempted = false;
    try {
      await recordGenerationGitHubPublication(context, jobId, {
        status: "CREATING",
        repositoryFullName: expectedFullName,
        artifactSha256: snapshot.artifactSha256,
        idempotencyKey: input.idempotencyKey,
        updatedAt: new Date().toISOString(),
      });
      creationAttempted = true;
      const repository = await githubJson<GitHubRepository>(
        "POST",
        input.owner ? `/orgs/${encodeURIComponent(expectedOwner)}/repos` : "/user/repos",
        input.token,
        {
          name: input.repositoryName,
          description,
          private: true,
          auto_init: false,
          has_issues: true,
          has_projects: false,
          has_wiki: false,
        },
        [201],
        deadline,
      );
      if (!repositoryIdentityMatches(repository, expectedOwner, input.repositoryName, description)) {
        throw new GenerationGitHubPublishError(502, "GITHUB_REPOSITORY_IDENTITY_MISMATCH");
      }
      repositoryId = repository.id;
      repositoryUrl = repository.html_url;
      createdThisAttemptConfirmed = true;

      const blobs = await createBlobs(
        expectedOwner,
        input.repositoryName,
        input.token,
        snapshot.files,
        deadline,
      );
      const tree = await githubJson<{ sha?: unknown }>(
        "POST",
        safePath(expectedOwner, input.repositoryName, "/git/trees"),
        input.token,
        { tree: blobs.map((blob) => ({ ...blob, type: "blob" })) },
        [201],
        deadline,
      );
      if (typeof tree.sha !== "string" || !gitObjectDigestPattern.test(tree.sha)) {
        throw new GenerationGitHubPublishError(502, "GITHUB_TREE_RECEIPT_INVALID");
      }
      const commit = await githubJson<{ sha?: unknown }>(
        "POST",
        safePath(expectedOwner, input.repositoryName, "/git/commits"),
        input.token,
        {
          message: `Generate ${snapshot.projectName}\n\nELMOS-Artifact-SHA256: ${snapshot.artifactSha256}`,
          tree: tree.sha,
          parents: [],
        },
        [201],
        deadline,
      );
      if (typeof commit.sha !== "string" || !gitObjectDigestPattern.test(commit.sha)) {
        throw new GenerationGitHubPublishError(502, "GITHUB_COMMIT_RECEIPT_INVALID");
      }
      await githubJson(
        "POST",
        safePath(expectedOwner, input.repositoryName, "/git/refs"),
        input.token,
        { ref: "refs/heads/main", sha: commit.sha },
        [201],
        deadline,
      );
      await githubJson(
        "PATCH",
        safePath(expectedOwner, input.repositoryName, ""),
        input.token,
        { default_branch: "main" },
        [200],
        deadline,
      );
      const reference = await githubJson<{ object?: { sha?: unknown } }>(
        "GET",
        safePath(expectedOwner, input.repositoryName, "/git/ref/heads/main"),
        input.token,
        undefined,
        [200],
        deadline,
      );
      if (reference.object?.sha !== commit.sha) {
        throw new GenerationGitHubPublishError(502, "GITHUB_BRANCH_VERIFICATION_FAILED");
      }
      const verifiedCommit = await githubJson<{ tree?: { sha?: unknown } }>(
        "GET",
        safePath(expectedOwner, input.repositoryName, `/git/commits/${commit.sha}`),
        input.token,
        undefined,
        [200],
        deadline,
      );
      if (verifiedCommit.tree?.sha !== tree.sha) {
        throw new GenerationGitHubPublishError(502, "GITHUB_COMMIT_VERIFICATION_FAILED");
      }
      const verifiedTree = await githubJson<{
        truncated?: unknown;
        tree?: Array<{ path?: unknown; type?: unknown; mode?: unknown; sha?: unknown }>;
      }>(
        "GET",
        `${safePath(expectedOwner, input.repositoryName, `/git/trees/${tree.sha}`)}?recursive=1`,
        input.token,
        undefined,
        [200],
        deadline,
      );
      const remoteBlobs = Array.isArray(verifiedTree.tree)
        ? verifiedTree.tree.filter((entry) => entry.type === "blob")
        : [];
      const remoteByPath = new Map(
        remoteBlobs.map((entry) => [entry.path, `${String(entry.mode)}:${String(entry.sha)}`]),
      );
      if (
        verifiedTree.truncated !== false
        || remoteByPath.size !== blobs.length
        || blobs.some((blob) => remoteByPath.get(blob.path) !== `${blob.mode}:${blob.sha}`)
      ) throw new GenerationGitHubPublishError(502, "GITHUB_TREE_VERIFICATION_FAILED");
      const verifiedRepository = await githubJson<GitHubRepository>(
        "GET",
        safePath(expectedOwner, input.repositoryName, ""),
        input.token,
        undefined,
        [200],
        deadline,
      );
      if (
        !repositoryIdentityMatches(
          verifiedRepository,
          expectedOwner,
          input.repositoryName,
          description,
        )
        || verifiedRepository.id !== repositoryId
        || verifiedRepository.default_branch !== "main"
      ) throw new GenerationGitHubPublishError(502, "GITHUB_REPOSITORY_FINAL_VERIFICATION_FAILED");

      return recordGenerationGitHubPublication(context, jobId, {
        status: "PUBLISHED",
        repositoryFullName: expectedFullName,
        repositoryId,
        repositoryUrl,
        branch: "main",
        commitSha: commit.sha,
        artifactSha256: snapshot.artifactSha256,
        fileCount: snapshot.files.length,
        idempotencyKey: input.idempotencyKey,
        updatedAt: new Date().toISOString(),
      });
    } catch (error) {
      const failure = error instanceof GenerationGitHubPublishError
        ? error
        : new GenerationGitHubPublishError(500, "GITHUB_PUBLICATION_FAILED");
      let reason = failure.code;
      if (creationAttempted && !createdThisAttemptConfirmed) {
        reason = "GITHUB_CREATION_OUTCOME_UNKNOWN_RECONCILIATION_REQUIRED";
      }
      if (createdThisAttemptConfirmed) {
        reason = `${failure.code}_MANUAL_CLEANUP_REQUIRED`;
      }
      await recordGenerationGitHubPublication(context, jobId, {
        status: "BLOCKED",
        ...((reason.includes("MANUAL_CLEANUP_REQUIRED") || reason.includes("RECONCILIATION_REQUIRED"))
          ? {
              repositoryFullName: expectedFullName,
              ...(repositoryId > 0 ? { repositoryId } : {}),
              ...(repositoryUrl ? { repositoryUrl } : {}),
            }
          : {}),
        artifactSha256: snapshot.artifactSha256,
        idempotencyKey: input.idempotencyKey,
        reason,
        updatedAt: new Date().toISOString(),
      });
      throw new GenerationGitHubPublishError(failure.status, reason);
    }
  } catch (error) {
    if (error instanceof GenerationGitHubPublishError) throw error;
    if (error instanceof GenerationRunnerError) {
      throw new GenerationGitHubPublishError(error.status, error.code);
    }
    throw new GenerationGitHubPublishError(500, "GITHUB_PUBLICATION_FAILED");
  } finally {
    activePublications.delete(operationKey);
    const remainingTenantPublications = (activePublicationsByTenant.get(context.tenantId) ?? 1) - 1;
    if (remainingTenantPublications <= 0) {
      activePublicationsByTenant.delete(context.tenantId);
    } else {
      activePublicationsByTenant.set(context.tenantId, remainingTenantPublications);
    }
  }
}

export async function publishGenerationToGitHub(
  context: AuthorizedContext,
  jobId: string,
  rawInput: GenerationGitHubPublishRequest,
): Promise<GenerationJob> {
  return withGenerationPublicationOperation(
    context,
    jobId,
    () => publishGenerationToGitHubLocked(context, jobId, rawInput),
  );
}

export function newGitHubPublicationIdempotencyKey(): string {
  return randomUUID();
}
