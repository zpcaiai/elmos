import { createHmac, randomUUID } from "node:crypto";
import type { UserActivityEvent } from "../operationsContracts";
import {
  AccountSessionError,
  accountSessionFromRequest,
  accountCookieNames,
  isPlatformAdministrator,
  unsafeCookieValue,
  type AccountPermission,
} from "./accountSession";
import {
  AdminMutationPolicyError,
  assertAdminMutationOrigin,
} from "./adminMutationPolicy";
import {
  assertEmptyOperationsJobQuery,
  OperationsJobsPolicyError,
  operationsJobId,
  operationsJobListQuery,
} from "./operationsJobsPolicy";
import {
  RunnerFleetPolicyError,
  requireRunnerFleetOidcAdmin,
  runnerFleetNodeId,
  runnerFleetListQuery,
} from "./runnerFleetPolicy";
import { configuredControlPlaneBaseUrl } from "./trustedUpstream";

const MAX_BODY_BYTES = 64 * 1024;
const MAX_BATCH_SIZE = 50;
const TOKEN_PATTERN = /^[A-Z0-9][A-Z0-9._:-]*$/;
const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]*$/;

export class OperationsProxyError extends Error {
  constructor(
    readonly status: number,
    readonly errorCode: string,
    message: string,
  ) {
    super(message);
  }
}

function requiredEnvironment(name: string, minimumLength = 1): string {
  const value = process.env[name]?.trim() ?? "";
  if (value.length < minimumLength) {
    throw new OperationsProxyError(
      503,
      "OPERATIONS_OBSERVABILITY_NOT_CONFIGURED",
      "操作观测服务尚未配置。",
    );
  }
  return value;
}

function controlPlaneBaseUrl(): string {
  let configured: string | null;
  try {
    configured = configuredControlPlaneBaseUrl({
      developmentFallback: "http://127.0.0.1:8080",
    });
  } catch {
    throw new OperationsProxyError(503, "OPERATIONS_CONTROL_PLANE_URL_INVALID", "操作观测服务地址无效。");
  }
  return configured ?? requiredEnvironment("ELMOS_CONTROL_PLANE_BASE_URL");
}

function internalHeaders(
  requestId: string = randomUUID(),
  administrator?: AdminPrincipal,
): Record<string, string> {
  const configuredActor = process.env.ELMOS_OPERATIONS_ACTOR_ID?.trim();
  const serviceActor = configuredActor || (
    process.env.NODE_ENV === "production"
      ? requiredEnvironment("ELMOS_OPERATIONS_ACTOR_ID")
      : "web-console-user"
  );
  const configuredTenant = administrator
    ? administrator.organizationId
    : requiredEnvironment("ELMOS_OPERATIONS_TENANT_ID");
  if (
    administrator
    && !administrator.accessToken
    && administrator.organizationId !== configuredTenant
  ) {
    throw new OperationsProxyError(
      403,
      "ADMIN_OBSERVABILITY_IDENTITY_MISMATCH",
      "企业账户所选租户与运营控制面绑定不一致。",
    );
  }
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-ELMOS-Operations-Key": administrator?.accessToken
      ? "OIDC"
      : requiredEnvironment("ELMOS_OPERATIONS_API_KEY", 24),
    "X-ELMOS-Organization-ID": administrator?.organizationId ?? configuredTenant,
    "X-ELMOS-Actor-ID": administrator?.actorId ?? serviceActor,
    "X-Request-ID": requestId,
  };
  if (administrator) {
    headers["X-ELMOS-Admin-Role"] = administrator.role;
    if (administrator.accessToken) {
      headers.Authorization = `Bearer ${administrator.accessToken}`;
    }
  }
  return headers;
}

function safeString(value: unknown, field: string, maxLength: number): string {
  if (typeof value !== "string" || value.length < 1 || value.length > maxLength || /[\r\n\0]/.test(value)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", `${field} 不符合操作日志契约。`);
  }
  return value;
}

function token(value: unknown, field: string, maxLength: number): string {
  const resolved = safeString(value, field, maxLength);
  if (!TOKEN_PATTERN.test(resolved)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", `${field} 不符合操作日志契约。`);
  }
  return resolved;
}

function identifier(value: unknown, field: string, maxLength = 128): string {
  const resolved = safeString(value, field, maxLength);
  if (!IDENTIFIER_PATTERN.test(resolved)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", `${field} 不符合操作日志契约。`);
  }
  return resolved;
}

function optionalToken(value: unknown, field: string, maxLength: number): string | undefined {
  return value === undefined || value === null || value === "" ? undefined : token(value, field, maxLength);
}

function sanitizeMetadata(value: unknown): Record<string, string> {
  if (value === undefined || value === null) return {};
  if (typeof value !== "object" || Array.isArray(value)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "metadata 不符合操作日志契约。");
  }
  const entries = Object.entries(value);
  if (entries.length > 8) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "metadata 维度过多。");
  }
  return Object.fromEntries(entries.map(([key, item]) => [
    token(key, "metadata key", 32),
    safeString(item, "metadata value", 64),
  ]));
}

function sanitizeEvent(value: unknown): UserActivityEvent {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "事件不符合操作日志契约。");
  }
  const candidate = value as Record<string, unknown>;
  const occurredAt = safeString(candidate.occurredAt, "occurredAt", 40);
  const parsedAt = Date.parse(occurredAt);
  if (!Number.isFinite(parsedAt)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "occurredAt 不符合操作日志契约。");
  }
  const durationMs = candidate.durationMs === undefined ? undefined : Number(candidate.durationMs);
  if (durationMs !== undefined && (!Number.isInteger(durationMs) || durationMs < 0 || durationMs > 3_600_000)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "durationMs 不符合操作日志契约。");
  }
  const metricValue = candidate.metricValue === undefined ? undefined : Number(candidate.metricValue);
  if (metricValue !== undefined && !Number.isFinite(metricValue)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "metricValue 不符合操作日志契约。");
  }
  const result = token(candidate.result, "result", 16);
  if (!["SUCCESS", "FAILURE", "CANCELLED"].includes(result)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "result 不符合操作日志契约。");
  }
  return {
    eventId: identifier(candidate.eventId, "eventId"),
    sessionId: identifier(candidate.sessionId, "sessionId"),
    eventKind: token(candidate.eventKind, "eventKind", 32),
    action: token(candidate.action, "action", 64),
    businessLine: token(candidate.businessLine, "businessLine", 64),
    route: stripQuery(safeString(candidate.route, "route", 160)),
    target: safeString(candidate.target, "target", 160),
    occurredAt: new Date(parsedAt).toISOString(),
    durationMs,
    result: result as UserActivityEvent["result"],
    errorCode: optionalToken(candidate.errorCode, "errorCode", 96),
    metricName: optionalToken(candidate.metricName, "metricName", 64),
    metricValue,
    metadata: sanitizeMetadata(candidate.metadata),
  };
}

function stripQuery(value: string): string {
  return value.split(/[?#]/, 1)[0] || "/";
}

export function parseEventBatch(rawBody: string): UserActivityEvent[] {
  if (Buffer.byteLength(rawBody, "utf8") > MAX_BODY_BYTES) {
    throw new OperationsProxyError(413, "OPERATIONS_EVENT_BATCH_TOO_LARGE", "操作日志批次过大。");
  }
  let body: unknown;
  try {
    body = JSON.parse(rawBody);
  } catch {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "操作日志请求不是有效 JSON。");
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "操作日志请求不符合契约。");
  }
  const events = (body as { events?: unknown }).events;
  if (!Array.isArray(events) || events.length < 1 || events.length > MAX_BATCH_SIZE) {
    throw new OperationsProxyError(400, "OPERATIONS_EVENT_INVALID", "每批必须包含 1 到 50 条事件。");
  }
  return events.map(sanitizeEvent);
}

export async function appendUserActivity(events: UserActivityEvent[]): Promise<Response> {
  const hmacKey = requiredEnvironment("ELMOS_OPERATIONS_API_KEY", 24);
  const privacySafeEvents = events.map((event) => ({
    ...event,
    sessionId: createHmac("sha256", hmacKey).update(event.sessionId).digest("hex"),
  }));
  const response = await fetch(`${controlPlaneBaseUrl()}/api/v1/operations-observability/events`, {
    method: "POST",
    headers: internalHeaders(),
    body: JSON.stringify({ events: privacySafeEvents }),
    cache: "no-store",
    signal: AbortSignal.timeout(5_000),
  });
  return response;
}

export type BusinessAuditDescriptor = {
  action: string;
  businessLine: string;
  route: string;
  target: string;
};

function safeRequestIdentifier(request: Request): string {
  const presented = request.headers.get("x-request-id");
  return presented && IDENTIFIER_PATTERN.test(presented) && presented.length <= 128
    ? presented
    : randomUUID();
}

async function appendBusinessAuditEvent(
  request: Request,
  requestId: string,
  descriptor: BusinessAuditDescriptor,
  phase: "ATTEMPT" | "COMPLETION",
  result: UserActivityEvent["result"],
  status: number | null,
  startedAt: number,
): Promise<void> {
  let administrator: AdminPrincipal | undefined;
  try {
    const account = accountSessionFromRequest(request);
    administrator = {
      role: "VIEWER",
      organizationId: account.principal.organizationId,
      actorId: account.principal.actorId,
      authentication: "OIDC_SESSION",
      accessToken: account.accessToken,
    };
  } catch (error) {
    if (process.env.NODE_ENV === "production") throw error;
  }
  const now = Date.now();
  const event: UserActivityEvent = {
    eventId: randomUUID(),
    sessionId: requestId,
    eventKind: phase === "ATTEMPT" ? "BUSINESS_ATTEMPT" : "BUSINESS_OPERATION",
    action: token(descriptor.action, "action", 64),
    businessLine: token(descriptor.businessLine, "businessLine", 64),
    route: stripQuery(safeString(descriptor.route, "route", 160)),
    target: safeString(descriptor.target, "target", 160),
    occurredAt: new Date(now).toISOString(),
    durationMs: phase === "COMPLETION" ? Math.min(3_600_000, now - startedAt) : undefined,
    result,
    errorCode: status !== null && status >= 400 ? `HTTP_${status}` : undefined,
    metadata: {
      PHASE: phase,
      SERVER_SIDE: "true",
    },
  };
  const response = await fetch(
    `${controlPlaneBaseUrl()}/api/v1/operations-observability/audit-events`,
    {
      method: "POST",
      headers: internalHeaders(requestId, administrator),
      body: JSON.stringify({ events: [event] }),
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    },
  );
  if (!response.ok) {
    throw new OperationsProxyError(
      response.status >= 400 && response.status < 500 ? response.status : 503,
      "BUSINESS_AUDIT_UNAVAILABLE",
      "业务操作审计未能持久化。",
    );
  }
}

export async function withBusinessAudit(
  request: Request,
  descriptor: BusinessAuditDescriptor,
  operation: () => Promise<Response>,
): Promise<Response> {
  const startedAt = Date.now();
  const requestId = safeRequestIdentifier(request);
  const required = process.env.NODE_ENV === "production"
    || process.env.ELMOS_BUSINESS_AUDIT_REQUIRED === "true";
  if (required) {
    await appendBusinessAuditEvent(
      request, requestId, descriptor, "ATTEMPT", "SUCCESS", null, startedAt,
    );
  } else {
    void appendBusinessAuditEvent(
      request, requestId, descriptor, "ATTEMPT", "SUCCESS", null, startedAt,
    ).catch(() => undefined);
  }
  let response: Response;
  try {
    response = await operation();
  } catch (error) {
    if (required) {
      try {
        await appendBusinessAuditEvent(
          request, requestId, descriptor, "COMPLETION", "FAILURE", 500, startedAt,
        );
      } catch {
        // Preserve the original operation failure; the attempt is durable when required.
      }
    } else {
      void appendBusinessAuditEvent(
        request, requestId, descriptor, "COMPLETION", "FAILURE", 500, startedAt,
      ).catch(() => undefined);
    }
    throw error;
  }
  if (!required) {
    void appendBusinessAuditEvent(
      request,
      requestId,
      descriptor,
      "COMPLETION",
      response.ok ? "SUCCESS" : "FAILURE",
      response.status,
      startedAt,
    ).catch(() => undefined);
    return response;
  }
  try {
    await appendBusinessAuditEvent(
      request,
      requestId,
      descriptor,
      "COMPLETION",
      response.ok ? "SUCCESS" : "FAILURE",
      response.status,
      startedAt,
    );
  } catch {
    if (response.ok) {
      return Response.json(
        {
          status: "BLOCKED",
          reason: "BUSINESS_AUDIT_COMPLETION_UNAVAILABLE",
          operationMayHaveCompleted: true,
        },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
  }
  return response;
}

export type AdminRole = "VIEWER" | "OPERATOR" | "APPROVER";
export type AdminPrincipal = {
  role: AdminRole;
  organizationId: string;
  actorId: string;
  authentication: "OIDC_SESSION";
  accessToken?: string;
};

export function authorizeAdmin(
  request: Request,
  requiredRole: AdminRole = "VIEWER",
): AdminPrincipal {
  const permission: Record<AdminRole, AccountPermission> = {
    VIEWER: "admin:read",
    OPERATOR: "admin:operate",
    APPROVER: "admin:approve",
  };
  const hasAccountSession = Boolean(
    unsafeCookieValue(request, accountCookieNames.session),
  );
  if (!hasAccountSession) {
    throw new OperationsProxyError(
      401,
      "ACCOUNT_SESSION_REQUIRED",
      "管理端要求已验证的管理员企业账户会话。",
    );
  }
  try {
    const session = accountSessionFromRequest(request, permission[requiredRole]);
    if (!isPlatformAdministrator(session.principal)) {
      throw new OperationsProxyError(
        403,
        "ADMIN_EMAIL_REQUIRED",
        "当前账户不是已验证的平台管理员账户。",
      );
    }
    const permissions = new Set(session.principal.permissions);
    const role: AdminRole = permissions.has("admin:approve")
      ? "APPROVER"
      : permissions.has("admin:operate") ? "OPERATOR" : "VIEWER";
    return {
      role,
      organizationId: session.principal.organizationId,
      actorId: session.principal.actorId,
      authentication: "OIDC_SESSION",
      accessToken: session.accessToken,
    };
  } catch (error) {
    if (error instanceof OperationsProxyError) throw error;
    if (error instanceof AccountSessionError) {
      throw new OperationsProxyError(error.status, error.code, error.message);
    }
    throw error;
  }
}

export function requireAdminMutationSameOrigin(request: Request): void {
  assertAdminMutationOrigin(request);
}

export async function fetchOperationsConsole(
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  const hours = boundedInteger(search.get("hours"), 24, 1, 744);
  const limit = boundedInteger(search.get("limit"), 50, 1, 200);
  const businessLine = filterToken(search.get("businessLine"));
  const result = filterToken(search.get("result"));
  const query = new URLSearchParams({
    hours: String(hours),
    limit: String(limit),
    businessLine,
    result,
  });
  return fetch(`${controlPlaneBaseUrl()}/api/v1/operations-observability/console?${query}`, {
    headers: internalHeaders(randomUUID(), administrator),
    cache: "no-store",
    signal: AbortSignal.timeout(5_000),
  });
}

export async function fetchOperationsJobs(
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  const query = operationsJobListQuery(search);
  return fetch(`${controlPlaneBaseUrl()}/api/v1/operations-observability/jobs?${query}`, {
    headers: internalHeaders(randomUUID(), administrator),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
}

export async function fetchOperationsRunnerFleet(
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  const query = runnerFleetListQuery(search);
  return fetch(`${controlPlaneBaseUrl()}/api/v1/operations-observability/runners?${query}`, {
    headers: internalHeaders(randomUUID(), administrator),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
}

export async function requestRunnerDrain(
  runnerNodeId: string,
  administrator: AdminPrincipal,
): Promise<Response> {
  requireRunnerFleetOidcAdmin(administrator, "OPERATOR");
  const resolvedNodeId = runnerFleetNodeId(runnerNodeId);
  return fetch(
    `${controlPlaneBaseUrl()}/api/v1/runner/nodes/${encodeURIComponent(resolvedNodeId)}/drain`,
    {
      method: "POST",
      headers: internalHeaders(randomUUID(), administrator),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    },
  );
}

export async function verifyRunnerAttestation(
  runnerNodeId: string,
  administrator: AdminPrincipal,
): Promise<Response> {
  requireRunnerFleetOidcAdmin(administrator, "APPROVER");
  const resolvedNodeId = runnerFleetNodeId(runnerNodeId);
  return fetch(
    `${controlPlaneBaseUrl()}/api/v1/runner/nodes/${encodeURIComponent(resolvedNodeId)}/attestation/verify`,
    {
      method: "POST",
      headers: internalHeaders(randomUUID(), administrator),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    },
  );
}

export async function cancelOperationsJob(
  jobId: string,
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  assertEmptyOperationsJobQuery(search);
  const resolvedJobId = operationsJobId(jobId);
  return fetch(
    `${controlPlaneBaseUrl()}/api/v1/operations-observability/jobs/${encodeURIComponent(resolvedJobId)}/cancel`,
    {
      method: "POST",
      headers: internalHeaders(randomUUID(), administrator),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    },
  );
}

/**
 * One keyset page of the audit export.
 *
 * Read path, so it does not go through the `mutateOperations` allowlist. The
 * page size is deliberately capped well below the control plane's own limit of
 * 1000: this proxy refuses bodies over 64KB and gives up after a few seconds,
 * so a caller wanting a full export walks the cursor rather than asking for one
 * oversized response that would be truncated or time out.
 */
export async function fetchAuditExport(
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  const days = boundedInteger(search.get("days"), 7, 1, 366);
  const limit = boundedInteger(search.get("limit"), 200, 1, 500);
  const businessLine = filterToken(search.get("businessLine"));
  const result = filterToken(search.get("result"));
  const query = new URLSearchParams({
    days: String(days),
    limit: String(limit),
    businessLine,
    result,
  });
  // A cursor is a pair; forwarding half of one would restart the export from
  // the top of the window and duplicate everything already downloaded.
  const afterOccurredAt = search.get("afterOccurredAt");
  const afterEventId = search.get("afterEventId");
  if ((afterOccurredAt === null) !== (afterEventId === null)) {
    throw new OperationsProxyError(
      400,
      "ADMIN_AUDIT_EXPORT_CURSOR_INCOMPLETE",
      "审计导出游标必须同时提供时间与事件 ID。",
    );
  }
  if (afterOccurredAt !== null && afterEventId !== null) {
    if (Number.isNaN(Date.parse(afterOccurredAt))) {
      throw new OperationsProxyError(
        400,
        "ADMIN_AUDIT_EXPORT_CURSOR_INVALID",
        "审计导出游标时间无效。",
      );
    }
    query.set("afterOccurredAt", afterOccurredAt);
    query.set("afterEventId", identifier(afterEventId, "afterEventId"));
  }
  return fetch(`${controlPlaneBaseUrl()}/api/v1/operations-observability/audit-export?${query}`, {
    headers: internalHeaders(randomUUID(), administrator),
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
}

/**
 * The reconstructed history of one migration run.
 *
 * The other half of the audit loop: the export answers what happened across the
 * tenant, this answers what happened to one run. Both are GET and both are
 * VIEWER, because a replay reveals nothing the export does not already reveal
 * to the same reader.
 *
 * The run id is validated here rather than forwarded raw so a malformed id
 * fails as a 400 with a reason, instead of travelling to the control plane and
 * coming back as an opaque rejection. It is the same identifier contract every
 * other proxied id goes through -- one place, one rule.
 *
 * No paging: a single run's history is bounded by the run, and the store
 * reports {@code truncated} per section rather than silently shortening. That
 * flag is forwarded untouched; deciding it "probably doesn't matter" here is
 * exactly how a partial audit artifact starts looking complete.
 */
export async function fetchRunHistoryReplay(
  migrationRunId: string,
  administrator: AdminPrincipal,
): Promise<Response> {
  const runId = identifier(migrationRunId, "migrationRunId");
  return fetch(
    `${controlPlaneBaseUrl()}/api/v1/operations-observability/runs/${encodeURIComponent(runId)}/replay`,
    {
      headers: internalHeaders(randomUUID(), administrator),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    },
  );
}

/**
 * Reads the tenant's allowance for operator review.
 *
 * A separate function rather than a path passed to a generic helper: the quota
 * endpoints live under their own control-plane prefix because a quota is
 * commercial state, not an observation, and routing them through the
 * observability allowlist would have meant widening that allowlist to cover a
 * write to billing.
 */
export async function fetchTenantQuota(administrator: AdminPrincipal): Promise<Response> {
  return fetch(`${controlPlaneBaseUrl()}/api/v1/tenant-quota`, {
    headers: internalHeaders(randomUUID(), administrator),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
}

/**
 * Adjusts the allowance.
 *
 * `expectedVersion` is forwarded, not defaulted. A proxy that supplied a
 * plausible-looking version on the caller's behalf would defeat the only
 * mechanism stopping two operators from overwriting each other, so a body
 * arriving without one is a 400 here rather than a guess.
 *
 * `reasonCode` is checked against the same token shape the control plane
 * enforces. Validating in both places is not duplication for its own sake: this
 * one produces a message the operator can act on, and the control plane's one
 * still holds if this proxy is ever bypassed.
 */
export async function adjustTenantQuota(
  body: unknown,
  administrator: AdminPrincipal,
): Promise<Response> {
  if (typeof body !== "object" || body === null) {
    throw new OperationsProxyError(400, "ADMIN_QUOTA_REQUEST_INVALID", "配额调整请求格式无效。");
  }
  const raw = body as Record<string, unknown>;
  const allowedFields = new Set([
    "quotaAllocationId",
    "tokenLimit",
    "creditLimit",
    "expectedVersion",
    "reasonCode",
  ]);
  if (
    Object.keys(raw).length !== allowedFields.size
    || Object.keys(raw).some((field) => !allowedFields.has(field))
  ) {
    throw new OperationsProxyError(
      400,
      "ADMIN_QUOTA_REQUEST_INVALID",
      "配额调整请求包含缺失或多余字段。",
    );
  }
  const quotaAllocationId = identifier(raw.quotaAllocationId, "quotaAllocationId");
  const tokenLimit = decimalString(raw.tokenLimit, "tokenLimit");
  const creditLimit = decimalString(raw.creditLimit, "creditLimit");
  if (typeof raw.expectedVersion !== "number" || !Number.isInteger(raw.expectedVersion) || raw.expectedVersion < 0) {
    throw new OperationsProxyError(400, "ADMIN_QUOTA_VERSION_INVALID", "缺少或非法的 expectedVersion，请先重新读取配额。");
  }
  if (typeof raw.reasonCode !== "string" || !/^[A-Z][A-Z0-9_]{2,47}$/.test(raw.reasonCode)) {
    throw new OperationsProxyError(400, "ADMIN_QUOTA_REASON_INVALID", "调整原因必须是大写字母、数字与下划线组成的代号。");
  }
  return fetch(`${controlPlaneBaseUrl()}/api/v1/tenant-quota/adjust`, {
    method: "POST",
    headers: internalHeaders(randomUUID(), administrator),
    body: JSON.stringify({
      quotaAllocationId,
      tokenLimit,
      creditLimit,
      expectedVersion: raw.expectedVersion,
      reasonCode: raw.reasonCode,
    }),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
}

/**
 * A limit crosses the wire as a decimal string, never as a JavaScript number.
 * `BigDecimal` on the other side holds values this language cannot represent
 * exactly, and a limit that arrives off by a fraction because it round-tripped
 * through a float is a billing defect nobody would think to look for.
 */
function decimalString(value: unknown, field: string): string {
  const text = typeof value === "number" ? String(value) : value;
  if (typeof text !== "string" || !/^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?$/.test(text)) {
    throw new OperationsProxyError(400, "ADMIN_QUOTA_LIMIT_INVALID", `${field} 必须是非负的十进制数值。`);
  }
  return text;
}

export async function mutateOperations(
  path: string,
  body: Record<string, unknown>,
  administrator: AdminPrincipal,
): Promise<Response> {
  if (!/^\/(?:evaluate|alerts\/[A-Za-z0-9._:-]+\/acknowledge|incidents\/[A-Za-z0-9._:-]+\/(?:assign|resolve)|remediations\/[A-Za-z0-9._:-]+\/(?:decision|prepare-scm)|retention\/enforce)$/.test(path)) {
    throw new OperationsProxyError(400, "ADMIN_OPERATION_INVALID", "管理操作不在允许清单中。");
  }
  return fetch(`${controlPlaneBaseUrl()}/api/v1/operations-observability${path}`, {
    method: "POST",
    headers: internalHeaders(randomUUID(), administrator),
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
}

function boundedInteger(value: string | null, fallback: number, minimum: number, maximum: number): number {
  if (value === null || value === "") return fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new OperationsProxyError(400, "ADMIN_OBSERVABILITY_FILTER_INVALID", "管理端筛选条件无效。");
  }
  return parsed;
}

function filterToken(value: string | null): string {
  if (value === null || value === "" || value === "ALL") return "ALL";
  return token(value, "filter", 64);
}

export function proxyErrorResponse(error: unknown): Response {
  if (error instanceof AdminMutationPolicyError) {
    return Response.json(
      { errorCode: error.errorCode, message: error.message, retryable: false },
      {
        status: error.status,
        headers: { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie, Authorization" },
      },
    );
  }
  if (error instanceof RunnerFleetPolicyError) {
    return Response.json(
      { errorCode: error.errorCode, message: error.message, retryable: false },
      {
        status: error.status,
        headers: { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie, Authorization" },
      },
    );
  }
  if (error instanceof OperationsJobsPolicyError) {
    return Response.json(
      { errorCode: error.errorCode, message: error.message, retryable: false },
      {
        status: 400,
        headers: { "Cache-Control": "no-store, private", Vary: "Authorization" },
      },
    );
  }
  if (error instanceof OperationsProxyError) {
    return Response.json(
      { errorCode: error.errorCode, message: error.message, retryable: false },
      {
        status: error.status,
        headers: { "Cache-Control": "no-store, private", Vary: "Authorization" },
      },
    );
  }
  const timeout = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
  return Response.json(
    {
      errorCode: timeout ? "OPERATIONS_CONTROL_PLANE_TIMEOUT" : "OPERATIONS_CONTROL_PLANE_UNAVAILABLE",
      message: timeout ? "操作观测服务响应超时。" : "操作观测服务当前不可用。",
      retryable: true,
    },
    {
      status: 503,
      headers: { "Cache-Control": "no-store, private", Vary: "Authorization" },
    },
  );
}

// ---------------------------------------------------------------------------
// 平台管理端（跨组织）
// ---------------------------------------------------------------------------
//
// 与上面那些函数的关键差别：`administrator.organizationId` 在这里**不是**被操作
// 的租户，而只是用来在控制面反查「调用者是哪个账号」。被读的租户是路径参数或
// 过滤条件，可能是任意一个。
//
// 这也是为什么这些请求照常带 X-ELMOS-Organization-ID：控制面拿它 + Actor-ID 去
// identity_membership_directory 反查 account_id，再拿 account_id 去查平台管理员
// 名单。会话里没有 account_id（actorId 是 sha256(orgId:accountId) 的单向派生），
// 而给会话加字段会作废所有在线会话。

function platformAdminUrl(path: string, search?: URLSearchParams): string {
  const query = search && search.toString() ? `?${search.toString()}` : "";
  return `${controlPlaneBaseUrl()}/api/v1/platform-admin${path}${query}`;
}

async function platformAdminGet(
  path: string,
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  return fetch(platformAdminUrl(path, search), {
    headers: internalHeaders(randomUUID(), administrator),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
}

async function platformAdminPost(
  path: string,
  body: unknown,
  administrator: AdminPrincipal,
): Promise<Response> {
  return fetch(platformAdminUrl(path), {
    method: "POST",
    headers: internalHeaders(randomUUID(), administrator),
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
}

// 刻意不复用 TOKEN_PATTERN：那个是 /^[A-Z0-9][A-Z0-9._:-]*$/，只收大写。
// 它服务的是业务线、状态这类枚举式取值（GENERATION、SUCCEEDED），而真实的
// 组织与账号标识是 org-xxxx / acct-xxxx，全小写——用它会把每一个真实标识都拒掉，
// 而且症状是整个面板恒空，不是报错。
// 形状对齐 CommercialPrincipal.ID。
const PLATFORM_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function platformIdentifier(value: unknown, field: string): string {
  if (typeof value !== "string" || !PLATFORM_ID_PATTERN.test(value)) {
    throw new OperationsProxyError(
      400, "PLATFORM_IDENTIFIER_INVALID", `${field} 不符合标识契约。`);
  }
  return value;
}

/** 组织标识用于路径与过滤，必须先校形，避免把任意串拼进 URL。 */
function platformOrganizationId(value: string): string {
  return platformIdentifier(value, "organizationId");
}

export async function fetchPlatformWallets(
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  const query = new URLSearchParams();
  const after = search.get("after");
  if (after) {
    query.set("after", platformOrganizationId(after));
  }
  query.set("limit", String(boundedInteger(search.get("limit"), 50, 1, 200)));
  return platformAdminGet("/wallets", query, administrator);
}

export async function fetchPlatformLedger(
  organizationId: string,
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  const query = new URLSearchParams();
  query.set("limit", String(boundedInteger(search.get("limit"), 50, 1, 200)));
  query.set("offset", String(boundedInteger(search.get("offset"), 0, 0, 100_000)));
  return platformAdminGet(
    `/wallets/${encodeURIComponent(platformOrganizationId(organizationId))}/ledger`,
    query, administrator);
}

export async function fetchPlatformTopups(
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  const query = new URLSearchParams();
  const status = search.get("status");
  // 白名单而不是透传：状态是拼进下游查询的，且取值域是封闭的。
  if (status) {
    if (!["CREATED", "PENDING_PAYMENT", "PAID", "CREDITED", "FAILED", "EXPIRED", "REFUNDED"]
        .includes(status)) {
      throw new OperationsProxyError(
        400, "PLATFORM_TOPUP_STATUS_INVALID", "充值状态不在取值域内。");
    }
    query.set("status", status);
  }
  query.set("limit", String(boundedInteger(search.get("limit"), 50, 1, 200)));
  return platformAdminGet("/topups", query, administrator);
}

export async function fetchPlatformJobs(
  search: URLSearchParams,
  administrator: AdminPrincipal,
): Promise<Response> {
  const query = new URLSearchParams();
  const status = search.get("status");
  if (status) {
    if (!["QUEUED", "CLAIMED", "RUNNING", "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "LOST"]
        .includes(status)) {
      throw new OperationsProxyError(
        400, "PLATFORM_JOB_STATUS_INVALID", "任务状态不在取值域内。");
    }
    query.set("status", status);
  }
  const organizationId = search.get("organizationId");
  if (organizationId) {
    query.set("organizationId", platformOrganizationId(organizationId));
  }
  query.set(
    "limitPerOrganization",
    String(boundedInteger(search.get("limitPerOrganization"), 25, 1, 200)));
  return platformAdminGet("/execution-jobs", query, administrator);
}

export async function adjustPlatformWallet(
  body: Record<string, unknown>,
  administrator: AdminPrincipal,
): Promise<Response> {
  return platformAdminPost("/wallets/adjust", {
    organizationId: platformOrganizationId(String(body.organizationId ?? "")),
    direction: body.direction === "DEBIT" ? "DEBIT" : "CREDIT",
    // 不用 boundedInteger：它在空值时返回 fallback，而这里任何 fallback 都是错的
    // ——传 0 会让一笔空金额变成一笔零元调账并被放行。金额必须显式给。
    amountMinor: platformAmountMinor(body.amountMinor),
    reason: safeString(body.reason, "reason", 255),
    idempotencyKey: platformIdentifier(body.idempotencyKey, "idempotencyKey"),
  }, administrator);
}

function platformAmountMinor(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 100_000_000) {
    throw new OperationsProxyError(
      400, "PLATFORM_ADJUSTMENT_AMOUNT_INVALID", "调整金额必须是 1..100000000 的整数分。");
  }
  return parsed;
}

export async function grantPlatformAdmin(
  body: Record<string, unknown>,
  administrator: AdminPrincipal,
): Promise<Response> {
  const role = String(body.platformRole ?? "");
  if (!["PLATFORM_VIEWER", "PLATFORM_OPERATOR", "PLATFORM_APPROVER"].includes(role)) {
    throw new OperationsProxyError(
      400, "PLATFORM_ROLE_INVALID", "平台角色不在取值域内。");
  }
  return platformAdminPost("/administrators/grant", {
    accountId: platformIdentifier(body.accountId, "accountId"),
    platformRole: role,
    reason: safeString(body.reason, "reason", 255),
  }, administrator);
}

export async function revokePlatformAdmin(
  body: Record<string, unknown>,
  administrator: AdminPrincipal,
): Promise<Response> {
  return platformAdminPost("/administrators/revoke", {
    accountId: platformIdentifier(body.accountId, "accountId"),
    reason: safeString(body.reason, "reason", 255),
  }, administrator);
}
