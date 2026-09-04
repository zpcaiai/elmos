export const telemetrySchemaVersion = "1.0.0" as const;

export const telemetryEventNames = [
  "page_view",
  "interaction",
  "form_submit",
  "api_request",
  "js_error",
  "performance",
] as const;

export const telemetryBusinessLines = [
  "overview",
  "spring",
  "translation",
  "generation",
  "repositories",
  "migration",
  "commercialization",
  "pricing",
  "skills",
  "admin",
] as const;

export const telemetryTargetKinds = [
  "page",
  "api",
  "window",
  "button",
  "link",
  "form",
  "input",
  "select",
  "textarea",
  "unknown",
] as const;

export const telemetryOutcomes = ["succeeded", "failed", "cancelled"] as const;
export const telemetryDurationBuckets = [
  "not_measured",
  "lt_100ms",
  "100_499ms",
  "500_999ms",
  "1_2s",
  "2_5s",
  "gte_5s",
] as const;
export const telemetryViewportClasses = ["mobile", "tablet", "desktop"] as const;

export type TelemetryEventName = (typeof telemetryEventNames)[number];
export type TelemetryBusinessLine = (typeof telemetryBusinessLines)[number];
export type TelemetryTargetKind = (typeof telemetryTargetKinds)[number];
export type TelemetryOutcome = (typeof telemetryOutcomes)[number];
export type TelemetryDurationBucket = (typeof telemetryDurationBuckets)[number];
export type TelemetryViewportClass = (typeof telemetryViewportClasses)[number];

export type ConsoleTelemetryEvent = {
  schemaVersion: typeof telemetrySchemaVersion;
  eventName: TelemetryEventName;
  businessLine: TelemetryBusinessLine;
  route: string;
  actionKey: string;
  targetKind: TelemetryTargetKind;
  outcome: TelemetryOutcome;
  durationBucket: TelemetryDurationBucket;
  viewportClass: TelemetryViewportClass;
  sessionId: string;
  occurredAt: string;
  durationMs: number | null;
  errorCode: string | null;
};

export function normalizeTelemetryRoute(value: string): string {
  const route = (value.split(/[?#]/, 1)[0] || "/")
    .replace(/\/[0-9a-f]{8}-[0-9a-f-]{27,36}(?=\/|$)/gi, "/:id")
    .replace(/\/[0-9a-f]{24,64}(?=\/|$)/gi, "/:id")
    .replace(/\/\d{4,}(?=\/|$)/g, "/:id");
  if (!route.startsWith("/") || route.length > 160 || /[\r\n\0]/.test(route)) return "/";
  return route;
}

export function routeBusinessLine(route: string): TelemetryBusinessLine {
  if (route.startsWith("/spring")) return "spring";
  if (route.startsWith("/translation")) return "translation";
  if (route.startsWith("/generation")) return "generation";
  if (route.startsWith("/repositories")) return "repositories";
  if (route.startsWith("/migration")) return "migration";
  if (route.startsWith("/commercialization")) return "commercialization";
  if (route.startsWith("/pricing")) return "pricing";
  if (route.startsWith("/capabilities") || route.startsWith("/skills")) return "skills";
  if (route.startsWith("/admin")) return "admin";
  return "overview";
}

export function bucketDuration(value: number | undefined): TelemetryDurationBucket {
  if (value === undefined) return "not_measured";
  if (value < 100) return "lt_100ms";
  if (value < 500) return "100_499ms";
  if (value < 1_000) return "500_999ms";
  if (value < 2_000) return "1_2s";
  if (value < 5_000) return "2_5s";
  return "gte_5s";
}
