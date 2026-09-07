import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountCookieDeletionOptions,
  exchangeAuthorizationCode,
  isPlatformAdministrator,
  localAccountCookieDeletionOptions,
  localAccountCookieNames,
  readAuthorizationFlow,
  refreshSessionCookieMaxAge,
  revokeToken,
  sessionCookieMaxAge,
  trustedPublicOrigin,
  type AccountLoginMode,
} from "../../../lib/server/accountSession";
import { notifyAdministratorLogin } from "../../../lib/server/adminLoginNotification";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function loginError(
  request: NextRequest,
  code: string,
  mode: AccountLoginMode = "USER",
): NextResponse {
  const target = new URL(mode === "ADMIN" ? "/admin/login" : "/login", trustedPublicOrigin(request));
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
  const code = request.nextUrl.searchParams.get("code") ?? "";
  const state = request.nextUrl.searchParams.get("state") ?? "";
  const sealedFlow = request.cookies.get(accountCookieNames.authorizationFlow)?.value ?? "";
  let trustedFlow: ReturnType<typeof readAuthorizationFlow> | null = null;
  let flowError: unknown = null;
  if (state && state.length <= 512 && sealedFlow) {
    try {
      // The sealed flow alone is not authority for the login surface. Recover its
      // mode only after the provider-returned state has passed constant-time
      // validation inside readAuthorizationFlow.
      trustedFlow = readAuthorizationFlow(sealedFlow, state);
    } catch (error) {
      flowError = error;
    }
  }
  if (providerError) {
    return loginError(
      request,
      "OIDC_AUTHORIZATION_REJECTED",
      trustedFlow?.loginMode ?? "USER",
    );
  }
  if (!code || code.length > 4_096 || !state || state.length > 512 || !sealedFlow) {
    return loginError(request, "OIDC_CALLBACK_INVALID", trustedFlow?.loginMode ?? "USER");
  }
  let mode: AccountLoginMode = trustedFlow?.loginMode ?? "USER";
  try {
    if (flowError) throw flowError;
    const flow = trustedFlow ?? readAuthorizationFlow(sealedFlow, state);
    mode = flow.loginMode;
    const result = await exchangeAuthorizationCode(code, flow);
    let notification: Awaited<ReturnType<typeof notifyAdministratorLogin>> | null = null;
    if (isPlatformAdministrator(result.principal)) {
      try {
        notification = await notifyAdministratorLogin(request, result.principal, "OIDC");
      } catch (error) {
        await Promise.allSettled([
          revokeToken(result.tokens.accessToken),
          ...(result.tokens.refreshToken ? [revokeToken(result.tokens.refreshToken)] : []),
        ]);
        throw error;
      }
    }
    const response = NextResponse.redirect(
      new URL(flow.returnTo, trustedPublicOrigin(request)),
      302,
    );
    const accessMaxAge = sessionCookieMaxAge(result.expiresAt);
    const sessionMaxAge = result.refreshExpiresAt
      ? refreshSessionCookieMaxAge(result.refreshExpiresAt)
      : accessMaxAge;
    response.cookies.set(accountCookieNames.session, result.session, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: sessionMaxAge,
    });
    response.cookies.set(accountCookieNames.accessToken, result.tokens.accessToken, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: accessMaxAge,
    });
    if (result.tokens.refreshToken && result.refreshExpiresAt) {
      const refreshMaxAge = refreshSessionCookieMaxAge(result.refreshExpiresAt);
      response.cookies.set(accountCookieNames.refreshToken, result.tokens.refreshToken, {
        httpOnly: true,
        secure: true,
        sameSite: "strict",
        path: "/",
        maxAge: refreshMaxAge,
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
    for (const name of Object.values(localAccountCookieNames)) {
      response.cookies.set(name, "", localAccountCookieDeletionOptions(request));
    }
    response.headers.set("Cache-Control", "no-store, private");
    if (notification) {
      response.headers.set("X-ELMOS-Admin-Login-Notification", "ACCEPTED");
    }
    return response;
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error
      ? String(error.code)
      : "OIDC_CALLBACK_FAILED";
    return loginError(request, code, mode);
  }
}
