import { NextRequest, NextResponse } from "next/server";
import { configuredControlPlaneBaseUrl } from "./app/lib/server/trustedUpstream";

const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

// Platform operations surfaces: only a verified administrator session reaches
// them, so an anonymous visitor is sent to the administrator entry, never the
// customer one. Kept in sync with app/lib/surfaceAudience.ts.
const operationsPrefixes = [
  "/admin",
  "/observability",
  "/governance",
  "/commercialization",
  "/proof-loop",
  "/playground",
  "/smoke",
];

// Product surfaces: any signed-in customer session is enough.
const userPrefixes = [
  "/spring",
  "/translation",
  "/generation",
  "/repositories",
  "/migration",
  "/capabilities",
];

const protectedPrefixes = [...userPrefixes, ...operationsPrefixes];

function matchesPrefix(pathname: string, prefixes: readonly string[]): boolean {
  return prefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

function trustedRedirectOrigin(request: NextRequest): string | null {
  const configured = process.env.ELMOS_PUBLIC_ORIGIN?.trim() ?? "";
  if (!configured) {
    return process.env.NODE_ENV === "production" ? null : request.nextUrl.origin;
  }
  try {
    const parsed = new URL(configured);
    const localDevelopment = process.env.NODE_ENV !== "production"
      && ["127.0.0.1", "localhost"].includes(parsed.hostname);
    if (
      (parsed.protocol !== "https:" && !(localDevelopment && parsed.protocol === "http:"))
      || parsed.username
      || parsed.password
      || parsed.pathname !== "/"
      || parsed.search
      || parsed.hash
    ) {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
}

function businessLine(path: string): string {
  if (path.startsWith("/api/spring-upgrades")) return "SPRING_MODERNIZATION";
  if (path.startsWith("/api/translation")) return "LANGUAGE_TRANSLATION";
  if (path.startsWith("/api/generation")) return "PROJECT_SYNTHESIS";
  if (path.startsWith("/api/repository-workspaces") || path.startsWith("/api/github")) return "REPOSITORY_WORKSPACE";
  if (path.startsWith("/api/database-sql") || path.startsWith("/api/capabilities/database-sql")) return "DATABASE_DATA_SQL";
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

function auditFailure(
  path: string,
  errorCode: string,
  message: string,
  retryable: boolean,
): NextResponse {
  if (path.startsWith("/api/database-sql") || path.startsWith("/api/capabilities/database-sql")) {
    return NextResponse.json(
      {
        schemaVersion: "1.0",
        status: "BLOCKED",
        errorCode,
        message,
        retryable,
        targetSql: null,
        verification: {
          sourceParse: "NOT_RUN",
          targetAdapter: "NOT_RUN",
          targetEmit: "NOT_RUN",
          targetReparse: "NOT_RUN",
          sourceExecution: "NOT_RUN",
          targetExecution: "NOT_RUN",
          resultEquivalence: "NOT_RUN",
          externalExecution: "NOT_RUN",
        },
        certification: "NOT_CERTIFIED",
      },
      {
        status: 503,
        headers: {
          "Cache-Control": "private, no-store, max-age=0",
          Vary: "Cookie, Authorization",
          "X-ELMOS-ChinaDB-Fail-Closed": "1",
        },
      },
    );
  }
  return NextResponse.json(
    { errorCode, message, retryable },
    { status: 503 },
  );
}

async function auditApiAttempt(request: NextRequest): Promise<NextResponse | null> {
  const path = request.nextUrl.pathname;
  // Authentication has its own security-event/audit boundary and must remain
  // reachable before a session exists. The operations audit key is not an
  // authentication prerequisite; otherwise an audit outage would make login
  // and logout impossible and turn a recoverable dependency issue into a lockout.
  if (
    !path.startsWith("/api/")
    || path.startsWith("/api/auth/")
    || path === "/api/telemetry/events"
    || path === "/api/health"
  ) {
    return null;
  }
  let baseUrl = "";
  try {
    baseUrl = configuredControlPlaneBaseUrl() ?? "";
  } catch {
    // Treat malformed, conflicting, or policy-rejected configuration exactly
    // like missing configuration. Never echo the rejected URL or send a key to it.
  }
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
      ? auditFailure(
        path,
        "SERVER_OPERATION_AUDIT_NOT_CONFIGURED",
        "服务端操作审计尚未配置。",
        false,
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
        redirect: "error",
        signal: AbortSignal.timeout(3_000),
      },
    );
    if (!response.ok) throw new Error("SERVER_OPERATION_AUDIT_REJECTED");
  } catch {
    return auditFailure(
      path,
      "SERVER_OPERATION_AUDIT_UNAVAILABLE",
      "服务端操作审计暂不可用。",
      true,
    );
  }
  return null;
}

export async function proxy(request: NextRequest) {
  const auditFailure = await auditApiAttempt(request);
  if (auditFailure) return auditFailure;
  if (request.nextUrl.pathname === "/admin/login") {
    return NextResponse.next();
  }
  if (!matchesPrefix(request.nextUrl.pathname, protectedPrefixes)) {
    return NextResponse.next();
  }
  const localCredentialMode = process.env.NODE_ENV !== "production"
    && process.env.ELMOS_LOCAL_RUNNER_ENABLED === "true";
  const adminRoute = matchesPrefix(request.nextUrl.pathname, operationsPrefixes);
  if (
    (localCredentialMode && !adminRoute)
    || request.cookies.has("__Host-elmos_session")
  ) {
    return NextResponse.next();
  }
  const redirectOrigin = trustedRedirectOrigin(request);
  if (!redirectOrigin) {
    return NextResponse.json(
      {
        errorCode: "PUBLIC_ORIGIN_NOT_CONFIGURED",
        message: "登录重定向的可信公开源尚未配置。",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
  const target = new URL(
    adminRoute
      ? "/admin/login"
      : "/login",
    redirectOrigin,
  );
  target.searchParams.set(
    "returnTo",
    `${request.nextUrl.pathname}${request.nextUrl.search}`,
  );
  return NextResponse.redirect(target);
}

export const config = {
  // "/skills" is deliberately absent: it only permanent-redirects to
  // /capabilities, and gating it would bounce the legacy link to /login instead.
  matcher: [
    "/api/:path*",
    "/spring/:path*",
    "/translation/:path*",
    "/generation/:path*",
    "/repositories/:path*",
    "/migration/:path*",
    "/capabilities/:path*",
    "/admin/:path*",
    "/observability/:path*",
    "/governance/:path*",
    "/commercialization/:path*",
    "/proof-loop/:path*",
    "/playground/:path*",
    "/smoke/:path*",
  ],
};
