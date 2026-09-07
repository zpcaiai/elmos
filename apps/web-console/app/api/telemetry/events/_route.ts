import { appendUserActivity, proxyErrorResponse } from "../../../lib/server/operationsProxy";
import {
  parseTelemetryBatch,
  TelemetryValidationError,
  toUserActivityEvent,
} from "../../../lib/telemetry/filter";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const windows = new Map<string, { startedAt: number; eventCount: number }>();
const WINDOW_MS = 60_000;
const MAX_EVENTS_PER_WINDOW = 120;

function reject(status: number, reason: string): Response {
  const retryable = status === 429;
  return Response.json(
    { status: "BLOCKED", reason, retryable },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
        ...(status === 429 ? { "Retry-After": "60" } : {}),
      },
    },
  );
}

function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    const presented = new URL(origin);
    const internal = new URL(request.url);
    if (presented.origin === internal.origin) return true;
    const host = request.headers.get("host");
    const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",", 1)[0]?.trim();
    const protocol = forwardedProtocol ? `${forwardedProtocol}:` : internal.protocol;
    return Boolean(host)
      && presented.protocol === protocol
      && presented.host.toLocaleLowerCase("en-US") === host?.toLocaleLowerCase("en-US");
  } catch {
    return false;
  }
}

function acceptRate(sessionId: string, eventCount: number): boolean {
  const now = Date.now();
  if (windows.size > 5_000) {
    for (const [key, value] of windows) {
      if (now - value.startedAt >= WINDOW_MS) windows.delete(key);
    }
    if (windows.size > 5_000 && !windows.has(sessionId)) return false;
  }
  const current = windows.get(sessionId);
  if (!current || now - current.startedAt >= WINDOW_MS) {
    windows.set(sessionId, { startedAt: now, eventCount });
    return eventCount <= MAX_EVENTS_PER_WINDOW;
  }
  current.eventCount += eventCount;
  return current.eventCount <= MAX_EVENTS_PER_WINDOW;
}

export async function POST(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return reject(403, "SAME_ORIGIN_REQUIRED");
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return reject(415, "JSON_CONTENT_TYPE_REQUIRED");
  }
  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(contentLength) && contentLength > 8 * 1024) {
    return reject(413, "REQUEST_TOO_LARGE");
  }
  try {
    const events = parseTelemetryBatch(await request.text());
    if (!acceptRate(events[0].sessionId, events.length)) {
      return reject(429, "TELEMETRY_RATE_LIMITED");
    }
    const upstream = await appendUserActivity(events.map(toUserActivityEvent));
    if (!upstream.ok) {
      const response = proxyErrorResponse(new Error("operations control plane rejected telemetry"));
      return new Response(response.body, {
        status: upstream.status >= 400 && upstream.status < 500 ? upstream.status : 503,
        headers: response.headers,
      });
    }
    return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof TelemetryValidationError) {
      const status = error.reason === "REQUEST_TOO_LARGE" ? 413 : 400;
      return reject(status, error.reason);
    }
    return proxyErrorResponse(error);
  }
}
