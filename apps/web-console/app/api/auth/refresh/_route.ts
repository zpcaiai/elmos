import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountCookieDeletionOptions,
  accountSessionErrorResponse,
  assertSameOriginMutation,
  refreshAccountSession,
  refreshSessionCookieMaxAge,
  refreshSessionFromRequest,
  sessionCookieMaxAge,
} from "../../../lib/server/accountSession";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    assertSameOriginMutation(request);
  } catch (error) {
    return accountSessionErrorResponse(error);
  }
  try {
    const current = refreshSessionFromRequest(request);
    const result = await refreshAccountSession(current.refreshToken, {
      actorId: current.actorId,
      loginMode: current.loginMode,
      refreshExpiresAt: current.refreshExpiresAt,
    });
    const response = NextResponse.json({
      authenticated: true,
      principal: result.principal,
      expiresAt: new Date(result.expiresAt).toISOString(),
    });
    const accessMaxAge = sessionCookieMaxAge(result.expiresAt);
    const refreshMaxAge = refreshSessionCookieMaxAge(result.refreshExpiresAt);
    response.cookies.set(accountCookieNames.session, result.session, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: refreshMaxAge,
    });
    response.cookies.set(accountCookieNames.accessToken, result.tokens.accessToken, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: accessMaxAge,
    });
    if (result.tokens.refreshToken) {
      response.cookies.set(accountCookieNames.refreshToken, result.tokens.refreshToken, {
        httpOnly: true,
        secure: true,
        sameSite: "strict",
        path: "/",
        maxAge: refreshMaxAge,
      });
    }
    response.cookies.set(
      accountCookieNames.tenant,
      "",
      accountCookieDeletionOptions(accountCookieNames.tenant),
    );
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    return accountSessionErrorResponse(error);
  }
}
