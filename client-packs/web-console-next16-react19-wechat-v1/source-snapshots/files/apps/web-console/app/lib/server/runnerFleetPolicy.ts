import type {
  RunnerFleetListView,
  RunnerFleetMutationView,
  RunnerFleetNodeView,
  RunnerFleetStatus,
} from "../operationsContracts";

export const runnerFleetRequiredRole = "VIEWER" as const;

export const runnerFleetStatuses = [
  "REGISTERED",
  "READY",
  "DRAINING",
  "QUARANTINED",
  "LOST",
  "RETIRED",
] as const satisfies readonly RunnerFleetStatus[];

const allowedListParameters = new Set(["limit", "status"]);
const statuses = new Set<string>(runnerFleetStatuses);
const boundedLimitPattern = /^(?:[1-9]|[1-9][0-9]|100)$/;
const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const runnerNodeIdPattern = /^[a-z0-9][a-z0-9._-]{2,95}$/;
const instantPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$/;
const maximumResponseBytes = 512 * 1024;
const topLevelKeys = new Set([
  "schemaVersion",
  "items",
  "limit",
  "returned",
  "truncated",
  "status",
]);
const nodeKeys = new Set([
  "runnerNodeId",
  "runnerPoolId",
  "agentVersion",
  "fleetStatus",
  "capabilities",
  "maxConcurrency",
  "attestationVerified",
  "attestationVerifiedAt",
  "imageAllowlistVersion",
  "lastHeartbeatAt",
  "drainRequestedAt",
  "createdAt",
  "updatedAt",
]);

export class RunnerFleetPolicyError extends Error {
  readonly status: number;
  readonly errorCode: string;

  constructor(
    status: number,
    errorCode: string,
    message: string,
  ) {
    super(message);
    this.name = "RunnerFleetPolicyError";
    this.status = status;
    this.errorCode = errorCode;
  }
}

export type RunnerFleetAdminPrincipal = {
  role: "VIEWER" | "OPERATOR" | "APPROVER";
  authentication: "OIDC_SESSION" | "BREAK_GLASS_TOKEN";
  accessToken?: string;
};

const roleRank = { VIEWER: 1, OPERATOR: 2, APPROVER: 3 } as const;

export function requireRunnerFleetOidcAdmin(
  principal: RunnerFleetAdminPrincipal,
  requiredRole: "OPERATOR" | "APPROVER",
): void {
  if (
    principal.authentication !== "OIDC_SESSION"
    || typeof principal.accessToken !== "string"
    || principal.accessToken.length < 24
    || principal.accessToken.length > 16_384
  ) {
    throw new RunnerFleetPolicyError(
      403,
      "RUNNER_FLEET_OIDC_SESSION_REQUIRED",
      "Runner Fleet 治理动作只接受已验证的企业账户会话，break-glass 不授予 Runner 写权限。",
    );
  }
  if (roleRank[principal.role] < roleRank[requiredRole]) {
    throw new RunnerFleetPolicyError(
      403,
      "RUNNER_FLEET_ADMIN_ROLE_INSUFFICIENT",
      requiredRole === "APPROVER"
        ? "Runner attestation 验证需要 APPROVER。"
        : "Runner 排空需要 OPERATOR。",
    );
  }
}

function rejectQuery(message: string): never {
  throw new RunnerFleetPolicyError(400, "ADMIN_RUNNER_FLEET_QUERY_INVALID", message);
}

function rejectResponse(message: string): never {
  throw new RunnerFleetPolicyError(502, "ADMIN_RUNNER_FLEET_RESPONSE_INVALID", message);
}

function singleValue(search: URLSearchParams, field: string): string | null {
  const values = search.getAll(field);
  if (values.length > 1) rejectQuery(`${field} 只能提供一次。`);
  return values[0] ?? null;
}

/**
 * Produces the only query shape accepted by the runner fleet endpoint.
 * Unknown, repeated, blank, non-canonical, or out-of-range values fail closed.
 */
export function runnerFleetListQuery(search: URLSearchParams): URLSearchParams {
  for (const key of search.keys()) {
    if (!allowedListParameters.has(key)) {
      rejectQuery("存在不支持的 Runner 筛选条件。");
    }
  }

  const rawLimit = singleValue(search, "limit");
  const limit = rawLimit ?? "50";
  if (!boundedLimitPattern.test(limit)) {
    rejectQuery("limit 必须是 1 到 100 之间的规范整数。");
  }

  const query = new URLSearchParams({ limit });
  const status = singleValue(search, "status");
  if (status !== null) {
    if (!statuses.has(status)) {
      rejectQuery("status 不在 Runner Fleet 状态允许清单中。");
    }
    query.set("status", status);
  }
  return query;
}

export function runnerFleetNodeId(value: unknown): string {
  if (typeof value !== "string" || !runnerNodeIdPattern.test(value)) {
    throw new RunnerFleetPolicyError(
      400,
      "ADMIN_RUNNER_FLEET_NODE_ID_INVALID",
      "runnerNodeId 不符合 Runner 节点标识契约。",
    );
  }
  return value;
}

export function assertEmptyRunnerFleetMutationQuery(search: URLSearchParams): void {
  if ([...search.keys()].length > 0) {
    throw new RunnerFleetPolicyError(
      400,
      "ADMIN_RUNNER_FLEET_MUTATION_QUERY_INVALID",
      "Runner Fleet 治理动作不接受查询参数。",
    );
  }
}

export function assertRunnerFleetSameOrigin(request: Request): void {
  const presentedOrigin = request.headers.get("origin");
  let expectedOrigin: string;
  try {
    expectedOrigin = new URL(request.url).origin;
  } catch {
    throw new RunnerFleetPolicyError(
      403,
      "RUNNER_FLEET_SAME_ORIGIN_REQUIRED",
      "Runner Fleet 治理请求的 origin 无法验证。",
    );
  }
  if (
    presentedOrigin === null
    || presentedOrigin !== expectedOrigin
    || (
      request.headers.has("sec-fetch-site")
      && request.headers.get("sec-fetch-site") !== "same-origin"
    )
  ) {
    throw new RunnerFleetPolicyError(
      403,
      "RUNNER_FLEET_SAME_ORIGIN_REQUIRED",
      "Runner Fleet 治理请求必须来自当前管理端同源页面。",
    );
  }
}

export async function assertEmptyRunnerFleetMutationBody(request: Request): Promise<void> {
  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null && declaredLength !== "0") {
    throw new RunnerFleetPolicyError(
      400,
      "ADMIN_RUNNER_FLEET_MUTATION_BODY_INVALID",
      "Runner Fleet 治理动作不接受请求体。",
    );
  }
  if (request.body === null) return;
  const reader = request.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) return;
      if (value.byteLength > 0) {
        await reader.cancel();
        throw new RunnerFleetPolicyError(
          400,
          "ADMIN_RUNNER_FLEET_MUTATION_BODY_INVALID",
          "Runner Fleet 治理动作不接受请求体。",
        );
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** Exact route-level request policy shared by drain and attestation writes. */
export async function validateRunnerFleetMutationRequest(
  request: Request,
  rawRunnerNodeId: unknown,
  principal: RunnerFleetAdminPrincipal,
  requiredRole: "OPERATOR" | "APPROVER",
): Promise<string> {
  requireRunnerFleetOidcAdmin(principal, requiredRole);
  assertRunnerFleetSameOrigin(request);
  assertEmptyRunnerFleetMutationQuery(new URL(request.url).searchParams);
  await assertEmptyRunnerFleetMutationBody(request);
  return runnerFleetNodeId(rawRunnerNodeId);
}

function record(value: unknown, context: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    rejectResponse(`${context} 不符合契约。`);
  }
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, allowed: Set<string>, context: string): void {
  const keys = Object.keys(value);
  if (keys.length !== allowed.size || keys.some((key) => !allowed.has(key))) {
    rejectResponse(`${context} 字段与 secret-free 契约不一致。`);
  }
}

function safeString(value: unknown, context: string, maximum = 128): string {
  if (
    typeof value !== "string"
    || value.length < 1
    || value.length > maximum
    || /[\r\n\0]/.test(value)
  ) {
    rejectResponse(`${context} 不符合安全字符串契约。`);
  }
  return value;
}

function identifier(value: unknown, context: string): string {
  const resolved = safeString(value, context);
  if (!identifierPattern.test(resolved)) rejectResponse(`${context} 不符合标识符契约。`);
  return resolved;
}

function instant(value: unknown, context: string, nullable: boolean): string | null {
  if (nullable && value === null) return null;
  const resolved = safeString(value, context, 40);
  if (!instantPattern.test(resolved) || !Number.isFinite(Date.parse(resolved))) {
    rejectResponse(`${context} 不符合 UTC Instant 契约。`);
  }
  return resolved;
}

function fleetStatus(value: unknown, context: string): RunnerFleetStatus {
  if (typeof value !== "string" || !statuses.has(value)) {
    rejectResponse(`${context} 不在 Runner Fleet 状态允许清单中。`);
  }
  return value as RunnerFleetStatus;
}

function node(value: unknown): RunnerFleetNodeView {
  const candidate = record(value, "Runner Fleet item");
  exactKeys(candidate, nodeKeys, "Runner Fleet item");
  if (!Array.isArray(candidate.capabilities) || candidate.capabilities.length > 64) {
    rejectResponse("Runner capabilities 不符合有界列表契约。");
  }
  const capabilities = candidate.capabilities.map((capability) =>
    safeString(capability, "Runner capability"));
  if (new Set(capabilities).size !== capabilities.length) {
    rejectResponse("Runner capabilities 不得包含重复值。");
  }
  if (
    typeof candidate.maxConcurrency !== "number"
    || !Number.isInteger(candidate.maxConcurrency)
    || candidate.maxConcurrency < 1
    || candidate.maxConcurrency > 10_000
  ) {
    rejectResponse("Runner maxConcurrency 不符合有界整数契约。");
  }
  if (typeof candidate.attestationVerified !== "boolean") {
    rejectResponse("Runner attestationVerified 不符合布尔契约。");
  }
  const attestationVerifiedAt = instant(
    candidate.attestationVerifiedAt,
    "Runner attestationVerifiedAt",
    true,
  );
  if (candidate.attestationVerified !== (attestationVerifiedAt !== null)) {
    rejectResponse("Runner attestation 状态与时间不一致。");
  }
  return {
    runnerNodeId: identifier(candidate.runnerNodeId, "runnerNodeId"),
    runnerPoolId: identifier(candidate.runnerPoolId, "runnerPoolId"),
    agentVersion: safeString(candidate.agentVersion, "agentVersion"),
    fleetStatus: fleetStatus(candidate.fleetStatus, "fleetStatus"),
    capabilities,
    maxConcurrency: candidate.maxConcurrency,
    attestationVerified: candidate.attestationVerified,
    attestationVerifiedAt,
    imageAllowlistVersion: safeString(candidate.imageAllowlistVersion, "imageAllowlistVersion"),
    lastHeartbeatAt: instant(candidate.lastHeartbeatAt, "lastHeartbeatAt", true),
    drainRequestedAt: instant(candidate.drainRequestedAt, "drainRequestedAt", true),
    createdAt: instant(candidate.createdAt, "createdAt", false) as string,
    updatedAt: instant(candidate.updatedAt, "updatedAt", false) as string,
  };
}

function parseSuccessfulResponse(payload: string): RunnerFleetListView {
  let decoded: unknown;
  try {
    decoded = JSON.parse(payload);
  } catch {
    rejectResponse("Runner Fleet 上游响应不是有效 JSON。");
  }
  const candidate = record(decoded, "Runner Fleet response");
  exactKeys(candidate, topLevelKeys, "Runner Fleet response");
  if (candidate.schemaVersion !== "1.0.0") {
    rejectResponse("Runner Fleet schemaVersion 不受支持。");
  }
  if (
    typeof candidate.limit !== "number"
    || !Number.isInteger(candidate.limit)
    || candidate.limit < 1
    || candidate.limit > 100
  ) {
    rejectResponse("Runner Fleet limit 不符合有界整数契约。");
  }
  if (!Array.isArray(candidate.items) || candidate.items.length > candidate.limit) {
    rejectResponse("Runner Fleet items 不符合有界列表契约。");
  }
  const items = candidate.items.map(node);
  if (candidate.returned !== items.length) {
    rejectResponse("Runner Fleet returned 与 items 数量不一致。");
  }
  if (typeof candidate.truncated !== "boolean") {
    rejectResponse("Runner Fleet truncated 不符合布尔契约。");
  }
  const status = candidate.status === null
    ? null
    : fleetStatus(candidate.status, "Runner Fleet status");
  if (status !== null && items.some((item) => item.fleetStatus !== status)) {
    rejectResponse("Runner Fleet 返回了越过状态筛选的节点。");
  }
  return {
    schemaVersion: "1.0.0",
    items,
    limit: candidate.limit,
    returned: items.length,
    truncated: candidate.truncated,
    status,
  };
}

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie, Authorization",
} as const;

/**
 * Relays error status without retry and reconstructs successful responses from
 * an exact allowlist so an upstream contract drift cannot leak credentials.
 */
export async function relayRunnerFleetResponse(upstream: Response): Promise<Response> {
  const payload = await upstream.text();
  if (Buffer.byteLength(payload, "utf8") > maximumResponseBytes) {
    rejectResponse("Runner Fleet 上游响应超过允许大小。");
  }
  if (!upstream.ok) {
    return new Response(payload, {
      status: upstream.status,
      headers: {
        ...privateHeaders,
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  }
  return Response.json(parseSuccessfulResponse(payload), {
    status: upstream.status,
    headers: privateHeaders,
  });
}

export async function relayRunnerFleetMutationResponse(
  upstream: Response,
  expectedStatus: "DRAINING" | "READY",
  expectedRunnerNodeId: string,
): Promise<Response> {
  const payload = await upstream.text();
  if (Buffer.byteLength(payload, "utf8") > 64 * 1024) {
    rejectResponse("Runner Fleet 治理上游响应超过允许大小。");
  }
  if (!upstream.ok) {
    return new Response(payload, {
      status: upstream.status,
      headers: {
        ...privateHeaders,
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(payload);
  } catch {
    rejectResponse("Runner Fleet 治理上游响应不是有效 JSON。");
  }
  const candidate = record(decoded, "Runner Fleet mutation response");
  const mutationKeys = new Set(["status", "runnerNodeId"]);
  exactKeys(candidate, mutationKeys, "Runner Fleet mutation response");
  if (candidate.status !== expectedStatus || candidate.runnerNodeId !== expectedRunnerNodeId) {
    rejectResponse("Runner Fleet 治理结果与请求目标不一致。");
  }
  const response: RunnerFleetMutationView = {
    status: expectedStatus,
    runnerNodeId: expectedRunnerNodeId,
  };
  return Response.json(response, {
    status: upstream.status,
    headers: privateHeaders,
  });
}
