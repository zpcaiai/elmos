import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountSessionErrorResponse,
  authorizationFlowCookieMaxAge,
  createAuthorizationFlow,
  AccountSessionError,
  accountCookieDeletionOptions,
  assertSameOriginMutation,
  authenticateTemporaryAdministrator,
  localAccountCookieNames,
  localAccountCookieOptions,
  sessionCookieMaxAge,
  trustedPublicOrigin,
} from "../../../../lib/server/accountSession";
import { safeOperationsReturnTo } from "../../../../lib/surfaceAudience";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Administrator login entry, deliberately separate from /api/auth/login:
 * GET starts ADMIN OIDC. POST is an explicitly configured loopback-only
 * development bootstrap; the ordinary user entry cannot mint this session.
 */
export async function GET(request: NextRequest) {
  try {
    const { sealedFlow, authorizationUrl } = createAuthorizationFlow(
      safeOperationsReturnTo(request.nextUrl.searchParams.get("returnTo") ?? undefined),
      "ADMIN",
    );
    const response = NextResponse.redirect(authorizationUrl, 302);
    response.cookies.set(accountCookieNames.authorizationFlow, sealedFlow, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: authorizationFlowCookieMaxAge(),
    });
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    return accountSessionErrorResponse(error);
  }
}

export async function POST(request: NextRequest) {
  const json = (request.headers.get("content-type") ?? "").includes("application/json");
  try {
    assertSameOriginMutation(request);
    // Bound actual bytes, including requests without Content-Length.
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 16_384) {
            await reader.cancel();
            throw new AccountSessionError(413, "TEMP_ADMIN_REQUEST_TOO_LARGE", "登录请求过大。");
          }
          chunks.push(value);
        }
      } finally { reader.releaseLock(); }
    }
    const raw = Buffer.concat(chunks).toString("utf8");
    let fields: Record<string, unknown>;
    try {
      fields = json ? JSON.parse(raw) : Object.fromEntries(new URLSearchParams(raw));
      if (!fields || typeof fields !== "object" || Array.isArray(fields)) throw new Error();
    } catch { throw new AccountSessionError(400, "TEMP_ADMIN_INVALID", "登录请求无效。"); }
    const username = typeof fields.username === "string" ? fields.username
      : typeof fields.email === "string" ? fields.email : "";
    const result = authenticateTemporaryAdministrator(request, username,
      typeof fields.password === "string" ? fields.password : "");
    const target = safeOperationsReturnTo(typeof fields.returnTo === "string" ? fields.returnTo : undefined);
    const response = json
      ? NextResponse.json({ authenticated: true, authentication: "TEMPORARY_ADMIN_PASSWORD",
          principal: result.principal, expiresAt: new Date(result.expiresAt).toISOString() })
      : NextResponse.redirect(new URL(target, trustedPublicOrigin(request)), 303);
    for (const name of Object.values(accountCookieNames)) {
      response.cookies.set(name, "", accountCookieDeletionOptions(name));
    }
    for (const name of Object.values(localAccountCookieNames)) {
      response.cookies.set(name, "", { ...localAccountCookieOptions(request), maxAge: 0 });
    }
    response.cookies.set(localAccountCookieNames.administratorSession, result.session, {
      ...localAccountCookieOptions(request), sameSite: "strict", maxAge: sessionCookieMaxAge(result.expiresAt),
    });
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    if (json) return accountSessionErrorResponse(error);
    try {
      const target = new URL("/admin/login", trustedPublicOrigin(request));
      target.searchParams.set("error", error instanceof AccountSessionError ? error.code : "TEMP_ADMIN_INVALID");
      const response = NextResponse.redirect(target, 303);
      response.headers.set("Cache-Control", "no-store, private");
      return response;
    } catch (redirectError) { return accountSessionErrorResponse(redirectError); }
  }
}
