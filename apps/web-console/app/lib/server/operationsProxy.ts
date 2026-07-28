import { createHash, createHmac, randomUUID, timingSafeEqual } from "node:crypto";
import type { UserActivityEvent } from "../operationsContracts";

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
  const configured = process.env.ELMOS_CONTROL_PLANE_BASE_URL?.trim()
    || process.env.CONTROL_PLANE_BASE_URL?.trim();
  const value = configured || (
    process.env.NODE_ENV === "production"
      ? requiredEnvironment("ELMOS_CONTROL_PLANE_BASE_URL")
      : "http://127.0.0.1:8080"
  );
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new OperationsProxyError(503, "OPERATIONS_CONTROL_PLANE_URL_INVALID", "操作观测服务地址无效。");
  }
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new OperationsProxyError(503, "OPERATIONS_CONTROL_PLANE_URL_INVALID", "操作观测服务地址无效。");
  }
  return parsed.toString().replace(/\/$/, "");
}

function internalHeaders(requestId = randomUUID()): Record<string, string> {
  const configuredActor = process.env.ELMOS_OPERATIONS_ACTOR_ID?.trim();
  const actor = configuredActor || (
    process.env.NODE_ENV === "production"
      ? requiredEnvironment("ELMOS_OPERATIONS_ACTOR_ID")
      : "web-console-user"
  );
  return {
    "Content-Type": "application/json",
    "X-ELMOS-Operations-Key": requiredEnvironment("ELMOS_OPERATIONS_API_KEY", 24),
    "X-ELMOS-Organization-ID": requiredEnvironment("ELMOS_OPERATIONS_TENANT_ID"),
    "X-ELMOS-Actor-ID": actor,
    "X-Request-ID": requestId,
  };
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

export function authorizeAdmin(authorization: string | null): void {
  const configured = requiredEnvironment("ELMOS_ADMIN_OBSERVABILITY_TOKEN", 24);
  const presented = authorization?.startsWith("Bearer ") ? authorization.slice(7) : "";
  const left = createHash("sha256").update(configured).digest();
  const right = createHash("sha256").update(presented).digest();
  if (!timingSafeEqual(left, right)) {
    throw new OperationsProxyError(403, "ADMIN_OBSERVABILITY_FORBIDDEN", "管理端令牌无效。");
  }
}

export async function fetchActivitySummary(search: URLSearchParams): Promise<Response> {
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
  return fetch(`${controlPlaneBaseUrl()}/api/v1/operations-observability/summary?${query}`, {
    headers: internalHeaders(),
    cache: "no-store",
    signal: AbortSignal.timeout(5_000),
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
  if (error instanceof OperationsProxyError) {
    return Response.json(
      { errorCode: error.errorCode, message: error.message, retryable: false },
      { status: error.status },
    );
  }
  const timeout = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
  return Response.json(
    {
      errorCode: timeout ? "OPERATIONS_CONTROL_PLANE_TIMEOUT" : "OPERATIONS_CONTROL_PLANE_UNAVAILABLE",
      message: timeout ? "操作观测服务响应超时。" : "操作观测服务当前不可用。",
      retryable: true,
    },
    { status: 503 },
  );
}
