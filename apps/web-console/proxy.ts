import { NextRequest, NextResponse } from "next/server";

const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

const protectedPrefixes = [
  "/spring",
  "/translation",
  "/generation",
  "/repositories",
  "/migration",
  "/commercialization",
  "/skills",
  "/admin",
];

function businessLine(path: string): string {
  if (path.startsWith("/api/spring-upgrades")) return "SPRING_MODERNIZATION";
  if (path.startsWith("/api/translation")) return "LANGUAGE_TRANSLATION";
  if (path.startsWith("/api/generation")) return "PROJECT_SYNTHESIS";
  if (path.startsWith("/api/repository-workspaces") || path.startsWith("/api/github")) return "REPOSITORY_WORKSPACE";
  if (path.startsWith("/api/capabilities/migration")) return "MIGRATION_GOVERNANCE";
  if (path.startsWith("/api/capabilities/product")) return "COMMERCIALIZATION";
  if (path.startsWith("/api/billing") || path.startsWith("/api/usage") || path.startsWith("/api/pricing")) return "PRICING_USAGE";
  if (path.startsWith("/api/admin")) return "ADMIN_OPERATIONS";
  return "PRODUCT_OVERVIEW";
}

function normalizedRoute(path: string): string {
  return path
    .replace(/\/[0-9a-f]{8}-[0-9a-f-]{27,36}(?=\/|$)/gi, "/:id")
    .replace(/\/[0-9a-f]{24,64}(?=\/|$)/gi, "/:id")
    .replace(/\/\d{4,}(?=\/|$)/g, "/:id")
    .slice(0, 160);
}

async function auditApiAttempt(request: NextRequest): Promise<NextResponse | null> {
  const path = request.nextUrl.pathname;
  if (!path.startsWith("/api/") || path === "/api/telemetry/events" || path === "/api/health") {
    return null;
  }
  const baseUrl = process.env.ELMOS_CONTROL_PLANE_BASE_URL?.trim()
    || process.env.CONTROL_PLANE_BASE_URL?.trim()
    || "";
  const key = process.env.ELMOS_OPERATIONS_API_KEY?.trim() || "";
  const tenant = process.env.ELMOS_OPERATIONS_TENANT_ID?.trim() || "";
  const actor = process.env.ELMOS_OPERATIONS_ACTOR_ID?.trim() || "";
  const expiry = Date.parse(process.env.ELMOS_OPERATIONS_API_KEY_EXPIRES_AT?.trim() || "");
  const configured = /^https?:\/\//.test(baseUrl)
    && key.length >= 24
    && identifier.test(tenant)
    && identifier.test(actor)
    && Number.isFinite(expiry)
    && expiry > Date.now()
    && expiry <= Date.now() + 24 * 60 * 60_000;
  if (!configured) {
    return process.env.NODE_ENV === "production"
      ? NextResponse.json(
        {
          errorCode: "SERVER_OPERATION_AUDIT_NOT_CONFIGURED",
          message: "服务端操作审计尚未配置。",
          retryable: false,
        },
        { status: 503 },
      )
      : null;
  }
  const requestIdHeader = request.headers.get("x-request-id");
  const requestId = requestIdHeader && identifier.test(requestIdHeader)
    ? requestIdHeader
    : crypto.randomUUID();
  const route = normalizedRoute(path);
  const method = request.method.toUpperCase();
  try {
    const response = await fetch(
      `${baseUrl.replace(/\/$/, "")}/api/v1/operations-observability/audit-events`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-ELMOS-Operations-Key": key,
          "X-ELMOS-Organization-ID": tenant,
          "X-ELMOS-Actor-ID": actor,
          "X-Request-ID": requestId,
        },
        body: JSON.stringify({
          events: [{
            eventId: crypto.randomUUID(),
            sessionId: requestId,
            eventKind: "SERVER_ATTEMPT",
            action: `HTTP_${method}`,
            businessLine: businessLine(path),
            route,
            target: route,
            occurredAt: new Date().toISOString(),
            result: "SUCCESS",
            metadata: {
              HTTP_METHOD: method,
              STATUS_PHASE: "ATTEMPT",
              SERVER_SIDE: "true",
            },
          }],
        }),
        cache: "no-store",
      },
    );
    if (!response.ok) throw new Error("SERVER_OPERATION_AUDIT_REJECTED");
  } catch {
    return NextResponse.json(
      {
        errorCode: "SERVER_OPERATION_AUDIT_UNAVAILABLE",
        message: "服务端操作审计暂不可用。",
        retryable: true,
      },
      { status: 503 },
    );
  }
  return null;
}

export async function proxy(request: NextRequest) {
  const auditFailure = await auditApiAttempt(request);
  if (auditFailure) return auditFailure;
  const protectedRoute = protectedPrefixes.some(
    (prefix) => request.nextUrl.pathname === prefix
      || request.nextUrl.pathname.startsWith(`${prefix}/`),
  );
  if (!protectedRoute) return NextResponse.next();
  const localCredentialMode = process.env.NODE_ENV !== "production"
    && (
      process.env.ELMOS_ALLOW_LOCAL_CREDENTIALS === "true"
      || process.env.ELMOS_LOCAL_RUNNER_ENABLED === "true"
    );
  if (
    localCredentialMode
    || request.cookies.has("__Host-elmos_session")
  ) {
    return NextResponse.next();
  }
  const target = new URL("/login", request.url);
  target.searchParams.set(
    "returnTo",
    `${request.nextUrl.pathname}${request.nextUrl.search}`,
  );
  return NextResponse.redirect(target);
}

export const config = {
  matcher: [
    "/api/:path*",
    "/spring/:path*",
    "/translation/:path*",
    "/generation/:path*",
    "/repositories/:path*",
    "/migration/:path*",
    "/commercialization/:path*",
    "/skills/:path*",
    "/admin/:path*",
  ],
};
