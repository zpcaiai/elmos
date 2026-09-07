import { type NextRequest, NextResponse } from "next/server";
import {
  AccountSessionError,
  accountSessionFromRequest,
  type AccountPermission,
} from "../../../lib/server/accountSession";
import {
  configuredLiveWorkbenchBaseUrl,
  UpstreamConfigurationError,
} from "../../../lib/server/trustedUpstream";
import {
  liveWorkbenchIdentifier,
  liveWorkbenchRouteAllowed,
} from "../../../lib/server/liveWorkbenchRoutePolicy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Context = { params: Promise<{ path?: string[] }> };
const maxBodyBytes = 128 * 1024;
const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie, Authorization",
};

function failure(status: number, code: string): NextResponse {
  return NextResponse.json({ code, message: code }, { status, headers: privateHeaders });
}

async function forward(request: NextRequest, context: Context): Promise<Response> {
  try {
    const { path = [] } = await context.params;
    if (!liveWorkbenchRouteAllowed(path, request.method)) return failure(404, "LIVE_WORKBENCH_ROUTE_NOT_FOUND");
    const permission: AccountPermission = request.method === "GET" ? "workspace:view" : "generation:execute";
    const session = accountSessionFromRequest(request, permission);
    const baseUrl = configuredLiveWorkbenchBaseUrl();
    if (!baseUrl) return failure(503, "LIVE_WORKBENCH_NOT_CONFIGURED");

    const declared = request.headers.get("content-length");
    if (declared && (!/^\d{1,9}$/.test(declared) || Number(declared) > maxBodyBytes))
      return failure(413, "LIVE_WORKBENCH_REQUEST_TOO_LARGE");
    const body = request.method === "POST" ? new Uint8Array(await request.arrayBuffer()) : undefined;
    if (body && body.byteLength > maxBodyBytes) return failure(413, "LIVE_WORKBENCH_REQUEST_TOO_LARGE");

    const upstream = new URL(`/api/v1/live-workbench/${path.map(encodeURIComponent).join("/")}`, baseUrl);
    for (const key of ["after", "limit"]) {
      const value = request.nextUrl.searchParams.get(key);
      if (value !== null && /^\d{1,10}$/.test(value)) upstream.searchParams.set(key, value);
    }
    const headers = new Headers({
      Accept: request.headers.get("accept") === "text/event-stream" ? "text/event-stream" : "application/json",
      Authorization: `Bearer ${session.accessToken}`,
      "X-Request-ID": request.headers.get("x-request-id")?.slice(0, 128) || crypto.randomUUID(),
    });
    if (body) headers.set("Content-Type", "application/json");
    const idempotencyKey = request.headers.get("idempotency-key");
    if (idempotencyKey && liveWorkbenchIdentifier(idempotencyKey)) headers.set("Idempotency-Key", idempotencyKey);

    const streaming = path.slice(2).join("/") === "events/stream";
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(streaming ? 240_000 : 30_000),
    });
    const responseHeaders = new Headers(privateHeaders);
    responseHeaders.set("Content-Type", response.headers.get("content-type") || "application/json; charset=utf-8");
    if (streaming) {
      responseHeaders.set("Connection", "keep-alive");
      responseHeaders.set("X-Accel-Buffering", "no");
    }
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  } catch (error) {
    if (error instanceof AccountSessionError) return failure(error.status, error.code);
    if (error instanceof UpstreamConfigurationError) return failure(503, "LIVE_WORKBENCH_CONFIGURATION_INVALID");
    return failure(503, "LIVE_WORKBENCH_UPSTREAM_UNAVAILABLE");
  }
}

export const GET = forward;
export const POST = forward;
