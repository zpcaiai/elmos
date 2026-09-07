import { randomUUID } from "node:crypto";
import type { UserActivityEvent } from "../operationsContracts";
import {
  telemetryBusinessLines,
  telemetryDurationBuckets,
  telemetryEventNames,
  telemetryOutcomes,
  telemetrySchemaVersion,
  telemetryTargetKinds,
  telemetryViewportClasses,
  type ConsoleTelemetryEvent,
} from "./contracts";

export class TelemetryValidationError extends Error {
  constructor(readonly reason: string) {
    super(reason);
  }
}

const allowedFields = new Set<keyof ConsoleTelemetryEvent>([
  "schemaVersion",
  "eventName",
  "businessLine",
  "route",
  "actionKey",
  "targetKind",
  "outcome",
  "durationBucket",
  "viewportClass",
  "sessionId",
  "occurredAt",
  "durationMs",
  "errorCode",
]);
const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const actionPattern = /^[a-z0-9][a-z0-9._-]{2,80}$/;
const errorPattern = /^[A-Z0-9][A-Z0-9._:-]{0,95}$/;

function expectEnum<T extends string>(value: unknown, values: readonly T[], reason: string): T {
  if (typeof value !== "string" || !values.includes(value as T)) {
    throw new TelemetryValidationError(reason);
  }
  return value as T;
}

function expectString(value: unknown, maximum: number, reason: string): string {
  if (typeof value !== "string" || value.length < 1 || value.length > maximum || /[\r\n\0]/.test(value)) {
    throw new TelemetryValidationError(reason);
  }
  return value;
}

function parseEvent(value: unknown): ConsoleTelemetryEvent {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new TelemetryValidationError("EVENT_INVALID");
  }
  const candidate = value as Record<string, unknown>;
  if (Object.keys(candidate).some((key) => !allowedFields.has(key as keyof ConsoleTelemetryEvent))) {
    throw new TelemetryValidationError("EVENT_FIELDS_NOT_ALLOWLISTED");
  }
  if (candidate.schemaVersion !== telemetrySchemaVersion) {
    throw new TelemetryValidationError("SCHEMA_VERSION_UNSUPPORTED");
  }
  const route = expectString(candidate.route, 160, "ROUTE_INVALID");
  if (!route.startsWith("/") || /[?#]/.test(route)) throw new TelemetryValidationError("ROUTE_INVALID");
  const actionKey = expectString(candidate.actionKey, 81, "ACTION_KEY_INVALID");
  if (!actionPattern.test(actionKey)) throw new TelemetryValidationError("ACTION_KEY_INVALID");
  const sessionId = expectString(candidate.sessionId, 128, "SESSION_ID_INVALID");
  if (!identifierPattern.test(sessionId)) throw new TelemetryValidationError("SESSION_ID_INVALID");
  const occurredAt = expectString(candidate.occurredAt, 40, "OCCURRED_AT_INVALID");
  const instant = Date.parse(occurredAt);
  const now = Date.now();
  if (!Number.isFinite(instant) || instant < now - 7 * 86_400_000 || instant > now + 300_000) {
    throw new TelemetryValidationError("OCCURRED_AT_INVALID");
  }
  const durationMs = candidate.durationMs;
  if (durationMs !== null && (
    typeof durationMs !== "number"
    || !Number.isInteger(durationMs)
    || durationMs < 0
    || durationMs > 3_600_000
  )) {
    throw new TelemetryValidationError("DURATION_INVALID");
  }
  const errorCode = candidate.errorCode;
  if (errorCode !== null && (typeof errorCode !== "string" || !errorPattern.test(errorCode))) {
    throw new TelemetryValidationError("ERROR_CODE_INVALID");
  }
  return {
    schemaVersion: telemetrySchemaVersion,
    eventName: expectEnum(candidate.eventName, telemetryEventNames, "EVENT_NAME_INVALID"),
    businessLine: expectEnum(candidate.businessLine, telemetryBusinessLines, "BUSINESS_LINE_INVALID"),
    route,
    actionKey,
    targetKind: expectEnum(candidate.targetKind, telemetryTargetKinds, "TARGET_KIND_INVALID"),
    outcome: expectEnum(candidate.outcome, telemetryOutcomes, "OUTCOME_INVALID"),
    durationBucket: expectEnum(candidate.durationBucket, telemetryDurationBuckets, "DURATION_BUCKET_INVALID"),
    viewportClass: expectEnum(candidate.viewportClass, telemetryViewportClasses, "VIEWPORT_INVALID"),
    sessionId,
    occurredAt: new Date(instant).toISOString(),
    durationMs,
    errorCode,
  };
}

export function parseTelemetryBatch(rawBody: string): ConsoleTelemetryEvent[] {
  if (Buffer.byteLength(rawBody, "utf8") > 8 * 1024) {
    throw new TelemetryValidationError("REQUEST_TOO_LARGE");
  }
  let payload: unknown;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    throw new TelemetryValidationError("BODY_UNPARSEABLE");
  }
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw new TelemetryValidationError("BODY_INVALID");
  }
  const keys = Object.keys(payload);
  if (keys.length !== 1 || keys[0] !== "events") {
    throw new TelemetryValidationError("BODY_FIELDS_NOT_ALLOWLISTED");
  }
  const events = (payload as { events?: unknown }).events;
  if (!Array.isArray(events) || events.length < 1 || events.length > 20) {
    throw new TelemetryValidationError("EVENT_BATCH_INVALID");
  }
  const parsed = events.map(parseEvent);
  if (parsed.some((event) => event.sessionId !== parsed[0].sessionId)) {
    throw new TelemetryValidationError("EVENT_BATCH_SESSION_MISMATCH");
  }
  return parsed;
}

const businessLineMap: Record<ConsoleTelemetryEvent["businessLine"], string> = {
  overview: "PRODUCT_OVERVIEW",
  spring: "SPRING_MODERNIZATION",
  translation: "LANGUAGE_TRANSLATION",
  generation: "PROJECT_SYNTHESIS",
  repositories: "REPOSITORY_WORKSPACE",
  migration: "MIGRATION_GOVERNANCE",
  commercialization: "COMMERCIALIZATION",
  pricing: "PRICING_USAGE",
  skills: "SKILLS_QUALIFICATION",
  admin: "ADMIN_OPERATIONS",
};

const eventKindMap: Record<ConsoleTelemetryEvent["eventName"], string> = {
  page_view: "NAVIGATION",
  interaction: "USER_ACTION",
  form_submit: "USER_ACTION",
  api_request: "API_REQUEST",
  js_error: "CLIENT_ERROR",
  performance: "PERFORMANCE",
};

export function toUserActivityEvent(event: ConsoleTelemetryEvent): UserActivityEvent {
  const action = event.actionKey.toUpperCase().replace(/[^A-Z0-9._:-]/g, "_").slice(0, 64);
  return {
    eventId: randomUUID(),
    sessionId: event.sessionId,
    eventKind: eventKindMap[event.eventName],
    action,
    businessLine: businessLineMap[event.businessLine],
    route: event.route,
    target: `${event.targetKind}:${event.actionKey}`.slice(0, 160),
    occurredAt: event.occurredAt,
    durationMs: event.durationMs ?? undefined,
    result: event.outcome === "failed"
      ? "FAILURE"
      : event.outcome === "cancelled" ? "CANCELLED" : "SUCCESS",
    errorCode: event.errorCode ?? undefined,
    metricName: event.eventName === "performance"
      ? (event.actionKey.includes("fcp") ? "FCP_MS" : "PAGE_LOAD_MS")
      : undefined,
    metricValue: event.eventName === "performance" ? event.durationMs ?? undefined : undefined,
    metadata: {
      DURATION_BUCKET: event.durationBucket,
      VIEWPORT_CLASS: event.viewportClass,
    },
  };
}
