import { createHash, timingSafeEqual } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import type { NextRequest } from "next/server";
import {
  accountCookieNames,
  AccountSessionError,
  accountSessionFromRequest,
  unsafeCookieValue,
} from "./accountSession";
import { pricingCatalog } from "../pricingCatalog";
import {
  type CurrentUsageSnapshot,
  usageSnapshotSchemaVersion,
} from "../usageSnapshot";

const identityPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const eventIdPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/;
const maxLedgerBytes = 10 * 1024 * 1024;
const refreshAfterSeconds = 5;

type MeterId = "model-token-v1" | "platform-credit-v1";
type ReconciliationStatus = "RECONCILED" | "PENDING" | "REJECTED";

type UsageLedgerEvent = {
  schemaVersion: "1.0.0";
  eventId: string;
  idempotencyKey: string;
  tenantId: string;
  actorId: string;
  planId: string;
  meterId: MeterId;
  quantity: number;
  occurredAt: string;
  recordedAt: string;
  reconciliationStatus: ReconciliationStatus;
};

type UsageSettings = {
  root: string;
  tenantId: string;
  actorId: string;
  token: string;
  tokenExpiresAt: Date;
  planId: string;
  periodStartsAt: Date;
  periodEndsAt: Date;
};

export class UsageMeterError extends Error {
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

function required(value: string | undefined, code: string, message: string): string {
  if (!value) {
    throw new UsageMeterError(503, code, message, true, "NOT_CONFIGURED");
  }
  return value;
}

function exactDate(value: string, field: string): Date {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw new UsageMeterError(503, `${field}_INVALID`, `${field} 必须是规范 UTC 时间。`, false);
  }
  return parsed;
}

function monthlyPeriod(now: Date): { startsAt: Date; endsAt: Date } {
  const startsAt = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  const endsAt = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
  return { startsAt, endsAt };
}

function settings(now: Date): UsageSettings {
  const localRunnerEnabled = process.env.ELMOS_LOCAL_RUNNER_ENABLED === "true";
  const explicitlyEnabled = process.env.ELMOS_USAGE_METER_ENABLED === "true";
  if (!localRunnerEnabled && !explicitlyEnabled) {
    throw new UsageMeterError(
      503,
      "USAGE_METER_NOT_CONFIGURED",
      "实时计量源尚未配置。",
      true,
      "NOT_CONFIGURED",
    );
  }
  const root = required(
    process.env.ELMOS_USAGE_METER_ROOT ?? process.env.ELMOS_LOCAL_RUNNER_ROOT,
    "USAGE_METER_ROOT_NOT_CONFIGURED",
    "实时计量根目录尚未配置。",
  );
  const tenantId = required(
    process.env.ELMOS_USAGE_METER_TENANT_ID ?? process.env.ELMOS_LOCAL_RUNNER_TENANT_ID,
    "USAGE_TENANT_NOT_CONFIGURED",
    "实时计量租户尚未配置。",
  );
  const actorId = required(
    process.env.ELMOS_USAGE_METER_ACTOR_ID ?? process.env.ELMOS_LOCAL_RUNNER_ACTOR_ID,
    "USAGE_ACTOR_NOT_CONFIGURED",
    "实时计量用户尚未配置。",
  );
  const token = required(
    process.env.ELMOS_USAGE_METER_AUTH_TOKEN ?? process.env.ELMOS_LOCAL_RUNNER_AUTH_TOKEN,
    "USAGE_AUTH_NOT_CONFIGURED",
    "实时计量认证尚未配置。",
  );
  const tokenExpiresAt = exactDate(
    required(
      process.env.ELMOS_USAGE_METER_AUTH_TOKEN_EXPIRES_AT
        ?? process.env.ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT,
      "USAGE_AUTH_EXPIRY_NOT_CONFIGURED",
      "实时计量认证到期时间尚未配置。",
    ),
    "USAGE_AUTH_EXPIRY",
  );
  const planId = process.env.ELMOS_USAGE_PLAN_ID
    ?? (localRunnerEnabled ? "elmos-pro-monthly" : "");
  if (!planId) {
    throw new UsageMeterError(
      503,
      "USAGE_PLAN_NOT_CONFIGURED",
      "当前账户套餐尚未绑定。",
      true,
      "NOT_CONFIGURED",
    );
  }
  const plan = pricingCatalog.plans.find((candidate) => candidate.planId === planId);
  if (!plan) {
    throw new UsageMeterError(503, "USAGE_PLAN_INVALID", "当前账户套餐无法识别。", false);
  }
  if (!identityPattern.test(tenantId) || !identityPattern.test(actorId) || token.length < 24) {
    throw new UsageMeterError(503, "USAGE_IDENTITY_CONFIGURATION_INVALID", "实时计量身份配置无效。", false);
  }
  const configuredStart = process.env.ELMOS_USAGE_PERIOD_START;
  const configuredEnd = process.env.ELMOS_USAGE_PERIOD_END;
  let period: { startsAt: Date; endsAt: Date };
  if (configuredStart || configuredEnd) {
    period = {
      startsAt: exactDate(
        required(configuredStart, "USAGE_PERIOD_START_NOT_CONFIGURED", "用量周期开始时间缺失。"),
        "USAGE_PERIOD_START",
      ),
      endsAt: exactDate(
        required(configuredEnd, "USAGE_PERIOD_END_NOT_CONFIGURED", "用量周期结束时间缺失。"),
        "USAGE_PERIOD_END",
      ),
    };
  } else if (localRunnerEnabled && plan.allowanceWindow === "MONTHLY") {
    period = monthlyPeriod(now);
  } else {
    throw new UsageMeterError(
      503,
      "USAGE_PERIOD_NOT_CONFIGURED",
      "当前用量周期尚未配置。",
      true,
      "NOT_CONFIGURED",
    );
  }
  if (
    period.startsAt.getTime() >= period.endsAt.getTime()
    || now.getTime() < period.startsAt.getTime()
    || now.getTime() >= period.endsAt.getTime()
  ) {
    throw new UsageMeterError(409, "USAGE_PERIOD_NOT_CURRENT", "配置的用量周期不是当前周期。", false);
  }
  return {
    root: path.resolve(root),
    tenantId,
    actorId,
    token,
    tokenExpiresAt,
    planId,
    periodStartsAt: period.startsAt,
    periodEndsAt: period.endsAt,
  };
}

function safeEqual(left: string, right: string): boolean {
  const leftBytes = Buffer.from(left);
  const rightBytes = Buffer.from(right);
  return leftBytes.length === rightBytes.length && timingSafeEqual(leftBytes, rightBytes);
}

function authorize(request: NextRequest, configured: UsageSettings, now: Date): void {
  if (unsafeCookieValue(request, accountCookieNames.session)) {
    try {
      const account = accountSessionFromRequest(request, "usage:read");
      if (
        account.principal.organizationId !== configured.tenantId
        || account.principal.actorId !== configured.actorId
      ) {
        throw new UsageMeterError(
          403,
          "USAGE_SUBJECT_MISMATCH",
          "账户会话与当前用量账本绑定不一致。",
          false,
        );
      }
      return;
    } catch (error) {
      if (error instanceof UsageMeterError) throw error;
      if (error instanceof AccountSessionError) {
        throw new UsageMeterError(error.status, error.code, error.message, false);
      }
      throw error;
    }
  }
  if (process.env.NODE_ENV === "production") {
    throw new UsageMeterError(
      401,
      "ACCOUNT_SESSION_REQUIRED",
      "请先登录企业账户。",
      false,
    );
  }
  const authorization = request.headers.get("authorization") ?? "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  const tenantId = request.headers.get("x-elmos-tenant") ?? "";
  const actorId = request.headers.get("x-elmos-actor") ?? "";
  if (!token || !safeEqual(token, configured.token)) {
    throw new UsageMeterError(401, "USAGE_AUTHENTICATION_REQUIRED", "实时用量凭证无效。", false);
  }
  if (now.getTime() >= configured.tokenExpiresAt.getTime()) {
    throw new UsageMeterError(401, "USAGE_AUTHENTICATION_EXPIRED", "实时用量凭证已过期。", false);
  }
  if (!safeEqual(tenantId, configured.tenantId) || !safeEqual(actorId, configured.actorId)) {
    throw new UsageMeterError(403, "USAGE_SUBJECT_MISMATCH", "凭证与账户范围不匹配。", false);
  }
}

function confined(root: string, ...segments: string[]): string {
  const candidate = path.resolve(root, ...segments);
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) {
    throw new UsageMeterError(503, "USAGE_LEDGER_PATH_INVALID", "实时计量路径无效。", false);
  }
  return candidate;
}

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new UsageMeterError(503, "USAGE_LEDGER_EVENT_INVALID", "计量事件格式无效。", false);
  }
  return value as Record<string, unknown>;
}

function eventText(
  source: Record<string, unknown>,
  field: string,
  pattern: RegExp = eventIdPattern,
): string {
  const value = source[field];
  if (typeof value !== "string" || !pattern.test(value)) {
    throw new UsageMeterError(503, "USAGE_LEDGER_EVENT_INVALID", `计量事件字段 ${field} 无效。`, false);
  }
  return value;
}

function eventDate(source: Record<string, unknown>, field: string): string {
  const value = source[field];
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) {
    throw new UsageMeterError(503, "USAGE_LEDGER_EVENT_INVALID", `计量事件字段 ${field} 无效。`, false);
  }
  return value;
}

function parseEvent(line: string): UsageLedgerEvent {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    throw new UsageMeterError(503, "USAGE_LEDGER_EVENT_INVALID", "计量事件不是有效 JSON。", false);
  }
  const source = record(parsed);
  const meterId = source.meterId;
  const reconciliationStatus = source.reconciliationStatus;
  if (source.schemaVersion !== "1.0.0") {
    throw new UsageMeterError(503, "USAGE_LEDGER_SCHEMA_UNSUPPORTED", "计量事件版本不受支持。", false);
  }
  if (meterId !== "model-token-v1" && meterId !== "platform-credit-v1") {
    throw new UsageMeterError(503, "USAGE_LEDGER_METER_INVALID", "计量器无法识别。", false);
  }
  if (
    reconciliationStatus !== "RECONCILED"
    && reconciliationStatus !== "PENDING"
    && reconciliationStatus !== "REJECTED"
  ) {
    throw new UsageMeterError(503, "USAGE_RECONCILIATION_STATUS_INVALID", "计量对账状态无效。", false);
  }
  if (!Number.isSafeInteger(source.quantity) || Number(source.quantity) <= 0) {
    throw new UsageMeterError(503, "USAGE_LEDGER_QUANTITY_INVALID", "计量数量必须是正整数。", false);
  }
  return {
    schemaVersion: "1.0.0",
    eventId: eventText(source, "eventId"),
    idempotencyKey: eventText(source, "idempotencyKey"),
    tenantId: eventText(source, "tenantId", identityPattern),
    actorId: eventText(source, "actorId", identityPattern),
    planId: eventText(source, "planId"),
    meterId,
    quantity: Number(source.quantity),
    occurredAt: eventDate(source, "occurredAt"),
    recordedAt: eventDate(source, "recordedAt"),
    reconciliationStatus,
  };
}

function measure(consumed: number, limit: number) {
  const remaining = Math.max(0, limit - consumed);
  return {
    consumed,
    reserved: 0,
    limit,
    remaining,
    usageBps: Math.min(10_000, Math.floor((consumed * 10_000) / limit)),
    hardStop: remaining === 0,
  };
}

export async function currentUsageSnapshot(
  request: NextRequest,
  now = new Date(),
): Promise<CurrentUsageSnapshot> {
  const configured = settings(now);
  authorize(request, configured, now);
  const plan = pricingCatalog.plans.find((candidate) => candidate.planId === configured.planId);
  if (!plan) {
    throw new UsageMeterError(503, "USAGE_PLAN_INVALID", "当前账户套餐无法识别。", false);
  }
  const ledgerPath = confined(
    configured.root,
    "tenants",
    configured.tenantId,
    "usage",
    "ledger.jsonl",
  );
  let ledgerStat;
  let content;
  try {
    ledgerStat = await stat(ledgerPath);
    if (!ledgerStat.isFile() || ledgerStat.size > maxLedgerBytes) {
      throw new UsageMeterError(503, "USAGE_LEDGER_SIZE_INVALID", "计量账本不存在或超过读取上限。", false);
    }
    content = await readFile(ledgerPath, "utf8");
  } catch (error) {
    if (error instanceof UsageMeterError) throw error;
    const code = error instanceof Error && "code" in error ? String(error.code) : "";
    if (code === "ENOENT") {
      throw new UsageMeterError(
        503,
        "USAGE_LEDGER_NOT_CONFIGURED",
        "可信用量账本尚未连接；不会把缺失用量显示为 0。",
        true,
        "NOT_CONFIGURED",
      );
    }
    throw new UsageMeterError(503, "USAGE_LEDGER_UNAVAILABLE", "可信用量账本暂时不可用。", true);
  }
  const events = content
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0)
    .map(parseEvent);
  const identities = new Map<string, string>();
  const eventIds = new Set<string>();
  let duplicateEventCount = 0;
  let reconciledEventCount = 0;
  let unreconciledEventCount = 0;
  let consumedTokens = 0;
  let consumedCredits = 0;
  let eventWatermark: string | null = null;
  for (const event of events) {
    if (event.tenantId !== configured.tenantId) {
      throw new UsageMeterError(403, "USAGE_LEDGER_CROSS_TENANT_EVENT", "计量账本包含跨租户事件。", false);
    }
    const canonical = JSON.stringify(event);
    const previous = identities.get(event.idempotencyKey);
    if (previous) {
      if (previous !== canonical) {
        throw new UsageMeterError(503, "USAGE_LEDGER_IDEMPOTENCY_CONFLICT", "计量事件幂等键冲突。", false);
      }
      duplicateEventCount += 1;
      continue;
    }
    identities.set(event.idempotencyKey, canonical);
    if (eventIds.has(event.eventId)) {
      throw new UsageMeterError(503, "USAGE_LEDGER_EVENT_ID_CONFLICT", "计量事件 ID 重复。", false);
    }
    eventIds.add(event.eventId);
    const occurredAt = Date.parse(event.occurredAt);
    if (
      occurredAt < configured.periodStartsAt.getTime()
      || occurredAt >= configured.periodEndsAt.getTime()
    ) {
      continue;
    }
    if (event.planId !== configured.planId) {
      throw new UsageMeterError(409, "USAGE_LEDGER_PLAN_MISMATCH", "当前周期包含其他套餐的计量事件。", false);
    }
    if (event.reconciliationStatus === "PENDING") {
      unreconciledEventCount += 1;
      continue;
    }
    if (event.reconciliationStatus === "REJECTED") {
      continue;
    }
    reconciledEventCount += 1;
    if (event.meterId === "model-token-v1") consumedTokens += event.quantity;
    else consumedCredits += event.quantity;
    if (!eventWatermark || Date.parse(event.recordedAt) > Date.parse(eventWatermark)) {
      eventWatermark = event.recordedAt;
    }
  }
  if (!Number.isSafeInteger(consumedTokens) || !Number.isSafeInteger(consumedCredits)) {
    throw new UsageMeterError(503, "USAGE_LEDGER_AGGREGATE_OVERFLOW", "计量聚合超过安全整数范围。", false);
  }
  const snapshotVersion = createHash("sha256")
    .update(content)
    .update("\0")
    .update(configured.tenantId)
    .update("\0")
    .update(configured.planId)
    .update("\0")
    .update(configured.periodStartsAt.toISOString())
    .update("\0")
    .update(configured.periodEndsAt.toISOString())
    .digest("hex");
  return {
    schemaVersion: usageSnapshotSchemaVersion,
    snapshotVersion,
    status: unreconciledEventCount > 0 ? "PARTIAL" : "CURRENT",
    subject: {
      tenantId: configured.tenantId,
      actorId: configured.actorId,
    },
    plan: {
      planId: plan.planId,
      displayName: plan.name,
      allowanceWindow: plan.allowanceWindow,
    },
    period: {
      startsAt: configured.periodStartsAt.toISOString(),
      endsAt: configured.periodEndsAt.toISOString(),
      resetsAt: plan.allowanceWindow === "MONTHLY"
        ? configured.periodEndsAt.toISOString()
        : null,
    },
    tokens: measure(consumedTokens, plan.tokens),
    credits: measure(consumedCredits, plan.credits),
    reconciledEventCount,
    unreconciledEventCount,
    duplicateEventCount,
    eventWatermark,
    generatedAt: now.toISOString(),
    refreshAfterSeconds,
  };
}
