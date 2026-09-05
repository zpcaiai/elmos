import { NextRequest, NextResponse } from "next/server";

import {
  accountCookieDeletionOptions,
  accountCookieNames,
  accountSessionErrorResponse,
  createDescopeAccountSession,
  localAccountCookieDeletionOptions,
  localAccountCookieNames,
  readDescopeOauthFlow,
  refreshSessionCookieMaxAge,
  sessionCookieMaxAge,
  trustedPublicOrigin,
} from "../../../../../lib/server/accountSession";
import { exchangeDescopeWechat } from "../../../../../lib/server/descopeIdentity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function errorRedirect(request: NextRequest, code: string, intent: "LOGIN" | "REGISTER") {
  const target = new URL(intent === "REGISTER" ? "/register" : "/login", trustedPublicOrigin(request));
  target.searchParams.set("error", code);
  const response = NextResponse.redirect(target, 302);
  response.cookies.set(
    accountCookieNames.descopeOauthFlow,
    "",
    accountCookieDeletionOptions(accountCookieNames.descopeOauthFlow),
  );
  response.headers.set("Cache-Control", "no-store, private");
  return response;
}

export async function GET(request: NextRequest) {
  let intent: "LOGIN" | "REGISTER" = "LOGIN";
  try {
    const sealedFlow = request.cookies.get(accountCookieNames.descopeOauthFlow)?.value ?? "";
    const flow = readDescopeOauthFlow(sealedFlow);
    intent = flow.intent;
    if (request.nextUrl.searchParams.get("error")) {
      return errorRedirect(request, "DESCOPE_WECHAT_AUTHORIZATION_REJECTED", intent);
    }
    const code = request.nextUrl.searchParams.get("code") ?? "";
    const verified = await exchangeDescopeWechat(flow.provider, code);
    const result = createDescopeAccountSession({
      ...verified,
      loginMode: "USER",
    });
    const response = NextResponse.redirect(
      new URL(flow.returnTo, trustedPublicOrigin(request)),
      302,
    );
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
    response.cookies.set(accountCookieNames.refreshToken, result.tokens.refreshToken, {
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      path: "/",
      maxAge: refreshMaxAge,
    });
    response.cookies.set(
      accountCookieNames.descopeOauthFlow,
      "",
      accountCookieDeletionOptions(accountCookieNames.descopeOauthFlow),
    );
    response.cookies.set(accountCookieNames.tenant, "", accountCookieDeletionOptions(accountCookieNames.tenant));
    for (const name of Object.values(localAccountCookieNames)) {
      response.cookies.set(name, "", localAccountCookieDeletionOptions(request));
    }
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error
      ? String(error.code)
      : "DESCOPE_WECHAT_EXCHANGE_REJECTED";
    try {
      return errorRedirect(request, code, intent);
    } catch (redirectError) {
      return accountSessionErrorResponse(redirectError);
    }
  }
}
