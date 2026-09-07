import { NextRequest, NextResponse } from "next/server";

import {
  accountCookieDeletionOptions,
  accountCookieNames,
  accountSessionErrorResponse,
  assertSameOriginMutation,
  createDescopeAccountSession,
  isPlatformAdministrator,
  localAccountCookieDeletionOptions,
  localAccountCookieNames,
  readDescopeOtpChallenge,
  refreshSessionCookieMaxAge,
  sessionCookieMaxAge,
  trustedPublicOrigin,
  type AccountLoginMode,
} from "../../../../../lib/server/accountSession";
import { notifyAdministratorLogin } from "../../../../../lib/server/adminLoginNotification";
import { revokeDescopeSession, verifyDescopeOtp } from "../../../../../lib/server/descopeIdentity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function errorRedirect(request: NextRequest, code: string, mode: AccountLoginMode): NextResponse {
  const target = new URL(mode === "ADMIN" ? "/admin/login" : "/login", trustedPublicOrigin(request));
  target.searchParams.set("error", code);
  const response = NextResponse.redirect(target, 303);
  response.cookies.set(
    accountCookieNames.descopeOtpChallenge,
    "",
    accountCookieDeletionOptions(accountCookieNames.descopeOtpChallenge),
  );
  response.headers.set("Cache-Control", "no-store, private");
  return response;
}

export async function POST(request: NextRequest) {
  let mode: AccountLoginMode = "USER";
  let intent: "LOGIN" | "REGISTER" = "LOGIN";
  try {
    assertSameOriginMutation(request);
    const sealedChallenge = request.cookies.get(accountCookieNames.descopeOtpChallenge)?.value ?? "";
    const challenge = readDescopeOtpChallenge(sealedChallenge);
    mode = challenge.loginMode;
    intent = challenge.intent;
    const form = await request.formData();
    const code = typeof form.get("code") === "string" ? String(form.get("code")) : "";
    const verified = await verifyDescopeOtp({
      channel: challenge.channel,
      loginId: challenge.loginId,
      code,
    });
    const result = createDescopeAccountSession({
      ...verified,
      loginMode: challenge.loginMode,
    });
    let notification: Awaited<ReturnType<typeof notifyAdministratorLogin>> | null = null;
    if (isPlatformAdministrator(result.principal)) {
      try {
        notification = await notifyAdministratorLogin(
          request,
          result.principal,
          "DESCOPE_EMAIL_OTP",
        );
      } catch (error) {
        await revokeDescopeSession(result.tokens.refreshToken);
        throw error;
      }
    }
    const response = NextResponse.redirect(
      new URL(challenge.returnTo, trustedPublicOrigin(request)),
      303,
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
      accountCookieNames.descopeOtpChallenge,
      "",
      accountCookieDeletionOptions(accountCookieNames.descopeOtpChallenge),
    );
    response.cookies.set(accountCookieNames.tenant, "", accountCookieDeletionOptions(accountCookieNames.tenant));
    for (const name of Object.values(localAccountCookieNames)) {
      response.cookies.set(name, "", localAccountCookieDeletionOptions(request));
    }
    response.headers.set("Cache-Control", "no-store, private");
    if (notification) response.headers.set("X-ELMOS-Admin-Login-Notification", "ACCEPTED");
    return response;
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error
      ? String(error.code)
      : "DESCOPE_OTP_VERIFY_REJECTED";
    try {
      const response = errorRedirect(request, code, mode);
      if (mode === "USER" && intent === "REGISTER") {
        const target = new URL(response.headers.get("location") ?? "/login");
        target.pathname = "/register";
        response.headers.set("location", target.toString());
      }
      return response;
    } catch (redirectError) {
      return accountSessionErrorResponse(redirectError);
    }
  }
}
