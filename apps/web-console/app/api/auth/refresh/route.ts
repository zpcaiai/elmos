import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountCookieDeletionOptions,
  accountSessionErrorResponse,
  assertSameOriginMutation,
  refreshAccountSession,
  sessionCookieMaxAge,
  unsafeCookieValue,
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
    const refreshToken = unsafeCookieValue(request, accountCookieNames.refreshToken);
    if (!refreshToken) {
      return NextResponse.json(
        { errorCode: "REFRESH_TOKEN_REQUIRED", message: "会话无法刷新，请重新登录。" },
        { status: 401 },
      );
    }
    const result = await refreshAccountSession(refreshToken);
    const response = NextResponse.json({
      authenticated: true,
      principal: result.principal,
      expiresAt: new Date(result.expiresAt).toISOString(),
    });
    const maxAge = sessionCookieMaxAge(result.expiresAt);
    response.cookies.set(accountCookieNames.session, result.session, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge,
    });
    response.cookies.set(accountCookieNames.accessToken, result.tokens.accessToken, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge,
    });
    if (result.tokens.refreshToken) {
      response.cookies.set(accountCookieNames.refreshToken, result.tokens.refreshToken, {
        httpOnly: true,
        secure: true,
        sameSite: "strict",
        path: "/",
        maxAge: 8 * 60 * 60,
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
