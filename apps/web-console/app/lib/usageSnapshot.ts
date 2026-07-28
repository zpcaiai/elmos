export const usageSnapshotSchemaVersion = "1.0.0";

export type UsageSnapshotStatus = "CURRENT" | "PARTIAL";

export type UsageMeasureSnapshot = {
  consumed: number;
  limit: number;
  remaining: number;
  usageBps: number;
  hardStop: boolean;
};

export type CurrentUsageSnapshot = {
  schemaVersion: typeof usageSnapshotSchemaVersion;
  snapshotVersion: string;
  status: UsageSnapshotStatus;
  subject: {
    tenantId: string;
    actorId: string;
  };
  plan: {
    planId: string;
    displayName: string;
    allowanceWindow: "TRIAL_TERM" | "MONTHLY";
  };
  period: {
    startsAt: string;
    endsAt: string;
    resetsAt: string | null;
  };
  tokens: UsageMeasureSnapshot;
  credits: UsageMeasureSnapshot;
  reconciledEventCount: number;
  unreconciledEventCount: number;
  duplicateEventCount: number;
  eventWatermark: string | null;
  generatedAt: string;
  refreshAfterSeconds: number;
};

export type UsageApiError = {
  code: string;
  message: string;
  retryable: boolean;
  status: "ERROR" | "NOT_CONFIGURED";
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`USAGE_SNAPSHOT_${field.toUpperCase()}_INVALID`);
  }
  return value;
}

function isoDate(value: unknown, field: string): string {
  const result = text(value, field);
  if (!Number.isFinite(Date.parse(result))) {
    throw new Error(`USAGE_SNAPSHOT_${field.toUpperCase()}_INVALID`);
  }
  return result;
}

function integer(value: unknown, field: string): number {
  if (!Number.isSafeInteger(value) || Number(value) < 0) {
    throw new Error(`USAGE_SNAPSHOT_${field.toUpperCase()}_INVALID`);
  }
  return Number(value);
}

function boolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`USAGE_SNAPSHOT_${field.toUpperCase()}_INVALID`);
  }
  return value;
}

function measure(value: unknown, field: string): UsageMeasureSnapshot {
  if (!isRecord(value)) {
    throw new Error(`USAGE_SNAPSHOT_${field.toUpperCase()}_INVALID`);
  }
  const consumed = integer(value.consumed, `${field}_consumed`);
  const limit = integer(value.limit, `${field}_limit`);
  const remaining = integer(value.remaining, `${field}_remaining`);
  const usageBps = integer(value.usageBps, `${field}_usage_bps`);
  const hardStop = boolean(value.hardStop, `${field}_hard_stop`);
  if (
    limit === 0
    || remaining !== Math.max(0, limit - consumed)
    || usageBps > 10_000
    || hardStop !== (remaining === 0)
  ) {
    throw new Error(`USAGE_SNAPSHOT_${field.toUpperCase()}_INCONSISTENT`);
  }
  return { consumed, limit, remaining, usageBps, hardStop };
}

export function parseCurrentUsageSnapshot(value: unknown): CurrentUsageSnapshot {
  if (!isRecord(value) || value.schemaVersion !== usageSnapshotSchemaVersion) {
    throw new Error("USAGE_SNAPSHOT_SCHEMA_VERSION_UNSUPPORTED");
  }
  if (!isRecord(value.subject) || !isRecord(value.plan) || !isRecord(value.period)) {
    throw new Error("USAGE_SNAPSHOT_STRUCTURE_INVALID");
  }
  const status = value.status;
  if (status !== "CURRENT" && status !== "PARTIAL") {
    throw new Error("USAGE_SNAPSHOT_STATUS_INVALID");
  }
  const allowanceWindow = value.plan.allowanceWindow;
  if (allowanceWindow !== "TRIAL_TERM" && allowanceWindow !== "MONTHLY") {
    throw new Error("USAGE_SNAPSHOT_ALLOWANCE_WINDOW_INVALID");
  }
  const resetsAt = value.period.resetsAt;
  if (resetsAt !== null && (typeof resetsAt !== "string" || !Number.isFinite(Date.parse(resetsAt)))) {
    throw new Error("USAGE_SNAPSHOT_RESETS_AT_INVALID");
  }
  const snapshotVersion = text(value.snapshotVersion, "snapshot_version");
  if (!/^[a-f0-9]{64}$/.test(snapshotVersion)) {
    throw new Error("USAGE_SNAPSHOT_VERSION_INVALID");
  }
  return {
    schemaVersion: usageSnapshotSchemaVersion,
    snapshotVersion,
    status,
    subject: {
      tenantId: text(value.subject.tenantId, "tenant_id"),
      actorId: text(value.subject.actorId, "actor_id"),
    },
    plan: {
      planId: text(value.plan.planId, "plan_id"),
      displayName: text(value.plan.displayName, "plan_display_name"),
      allowanceWindow,
    },
    period: {
      startsAt: isoDate(value.period.startsAt, "period_starts_at"),
      endsAt: isoDate(value.period.endsAt, "period_ends_at"),
      resetsAt,
    },
    tokens: measure(value.tokens, "tokens"),
    credits: measure(value.credits, "credits"),
    reconciledEventCount: integer(value.reconciledEventCount, "reconciled_event_count"),
    unreconciledEventCount: integer(value.unreconciledEventCount, "unreconciled_event_count"),
    duplicateEventCount: integer(value.duplicateEventCount, "duplicate_event_count"),
    eventWatermark: value.eventWatermark === null
      ? null
      : isoDate(value.eventWatermark, "event_watermark"),
    generatedAt: isoDate(value.generatedAt, "generated_at"),
    refreshAfterSeconds: integer(value.refreshAfterSeconds, "refresh_after_seconds"),
  };
}

export function parseUsageApiError(value: unknown, fallbackStatus: number): UsageApiError {
  if (
    isRecord(value)
    && typeof value.code === "string"
    && typeof value.message === "string"
    && typeof value.retryable === "boolean"
    && (value.status === "ERROR" || value.status === "NOT_CONFIGURED")
  ) {
    return {
      code: value.code,
      message: value.message,
      retryable: value.retryable,
      status: value.status,
    };
  }
  return {
    code: `USAGE_HTTP_${fallbackStatus}`,
    message: "实时用量服务返回了无法识别的响应。",
    retryable: fallbackStatus >= 500,
    status: fallbackStatus === 503 ? "NOT_CONFIGURED" : "ERROR",
  };
}
