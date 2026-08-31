import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountCookieDeletionOptions,
  exchangeAuthorizationCode,
  readAuthorizationFlow,
  sessionCookieMaxAge,
  trustedPublicOrigin,
} from "../../../lib/server/accountSession";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function loginError(request: NextRequest, code: string): NextResponse {
  const target = new URL("/login", trustedPublicOrigin(request));
  target.searchParams.set("error", code);
  const response = NextResponse.redirect(target, 302);
  response.cookies.set(
    accountCookieNames.authorizationFlow,
    "",
    accountCookieDeletionOptions(accountCookieNames.authorizationFlow),
  );
  response.headers.set("Cache-Control", "no-store, private");
  return response;
}

export async function GET(request: NextRequest) {
  const providerError = request.nextUrl.searchParams.get("error");
  if (providerError) return loginError(request, "OIDC_AUTHORIZATION_REJECTED");
  const code = request.nextUrl.searchParams.get("code") ?? "";
  const state = request.nextUrl.searchParams.get("state") ?? "";
  const sealedFlow = request.cookies.get(accountCookieNames.authorizationFlow)?.value ?? "";
  if (!code || code.length > 4_096 || !state || state.length > 512 || !sealedFlow) {
    return loginError(request, "OIDC_CALLBACK_INVALID");
  }
  try {
    const flow = readAuthorizationFlow(sealedFlow, state);
    const result = await exchangeAuthorizationCode(code, flow);
    const response = NextResponse.redirect(
      new URL(flow.returnTo, trustedPublicOrigin(request)),
      302,
    );
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
      accountCookieNames.authorizationFlow,
      "",
      accountCookieDeletionOptions(accountCookieNames.authorizationFlow),
    );
    response.cookies.set(
      accountCookieNames.tenant,
      "",
      accountCookieDeletionOptions(accountCookieNames.tenant),
    );
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error
      ? String(error.code)
      : "OIDC_CALLBACK_FAILED";
    return loginError(request, code);
  }
}
