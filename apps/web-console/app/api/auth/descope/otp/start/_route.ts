import { NextRequest, NextResponse } from "next/server";

import {
  accountCookieNames,
  accountSessionErrorResponse,
  assertSameOriginMutation,
  createDescopeOtpChallenge,
  trustedPublicOrigin,
  type AccountLoginMode,
} from "../../../../../lib/server/accountSession";
import { startDescopeOtp } from "../../../../../lib/server/descopeIdentity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function pageFor(mode: AccountLoginMode, intent: "LOGIN" | "REGISTER"): string {
  if (mode === "ADMIN") return "/admin/login";
  return intent === "REGISTER" ? "/register" : "/login";
}

function safeReturnTo(value: FormDataEntryValue | null): string {
  return typeof value === "string"
    && value.startsWith("/")
    && !value.startsWith("//")
    && !/[\\\r\n\0]/.test(value)
    ? value
    : "/";
}

function errorRedirect(
  request: NextRequest,
  code: string,
  mode: AccountLoginMode,
  intent: "LOGIN" | "REGISTER",
): NextResponse {
  const target = new URL(pageFor(mode, intent), trustedPublicOrigin(request));
  target.searchParams.set("error", code);
  const response = NextResponse.redirect(target, 303);
  response.headers.set("Cache-Control", "no-store, private");
  return response;
}

export async function POST(request: NextRequest) {
  let mode: AccountLoginMode = "USER";
  let intent: "LOGIN" | "REGISTER" = "LOGIN";
  try {
    assertSameOriginMutation(request);
    const contentLength = Number(request.headers.get("content-length") ?? "");
    if (Number.isFinite(contentLength) && contentLength > 16 * 1024) {
      throw new Error("DESCOPE_REQUEST_TOO_LARGE");
    }
    const form = await request.formData();
    mode = form.get("loginMode") === "ADMIN" ? "ADMIN" : "USER";
    intent = form.get("intent") === "REGISTER" ? "REGISTER" : "LOGIN";
    const channel = form.get("channel") === "SMS" ? "SMS" : "EMAIL";
    const loginId = typeof form.get("loginId") === "string"
      ? String(form.get("loginId"))
      : "";
    const displayName = typeof form.get("displayName") === "string"
      ? String(form.get("displayName"))
      : undefined;
    const draft = createDescopeOtpChallenge({
      channel,
      intent,
      loginMode: mode,
      loginId,
      ...(displayName ? { displayName } : {}),
      returnTo: safeReturnTo(form.get("returnTo")),
    });
    const started = await startDescopeOtp({
      channel,
      intent,
      loginId: draft.challenge.loginId,
      ...(draft.challenge.displayName ? { displayName: draft.challenge.displayName } : {}),
      ...(mode === "ADMIN" ? { allowSignUpOrIn: true } : {}),
    });
    const { sealedChallenge } = createDescopeOtpChallenge({
      ...draft.challenge,
      loginId: started.loginId,
    });
    const target = new URL(pageFor(mode, intent), trustedPublicOrigin(request));
    target.searchParams.set("verify", "1");
    const response = NextResponse.redirect(target, 303);
    response.cookies.set(accountCookieNames.descopeOtpChallenge, sealedChallenge, {
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      path: "/",
      maxAge: 10 * 60,
    });
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error
      ? String(error.code)
      : "DESCOPE_OTP_START_REJECTED";
    try {
      return errorRedirect(request, code, mode, intent);
    } catch (redirectError) {
      return accountSessionErrorResponse(redirectError);
    }
  }
}
