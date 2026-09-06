import { NextRequest, NextResponse } from "next/server";

import {
  accountCookieNames,
  accountSessionErrorResponse,
  assertSameOriginMutation,
  createDescopeOauthFlow,
  trustedPublicOrigin,
} from "../../../../../lib/server/accountSession";
import { startDescopeWechat } from "../../../../../lib/server/descopeIdentity";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function safeReturnTo(value: FormDataEntryValue | null): string {
  return typeof value === "string"
    && value.startsWith("/")
    && !value.startsWith("//")
    && !value.startsWith("/admin")
    && !/[\\\r\n\0]/.test(value)
    ? value
    : "/";
}

function errorRedirect(request: NextRequest, code: string, intent: "LOGIN" | "REGISTER") {
  const target = new URL(intent === "REGISTER" ? "/register" : "/login", trustedPublicOrigin(request));
  target.searchParams.set("error", code);
  const response = NextResponse.redirect(target, 303);
  response.headers.set("Cache-Control", "no-store, private");
  return response;
}

export async function POST(request: NextRequest) {
  let intent: "LOGIN" | "REGISTER" = "LOGIN";
  try {
    assertSameOriginMutation(request);
    const form = await request.formData();
    intent = form.get("intent") === "REGISTER" ? "REGISTER" : "LOGIN";
    const returnTo = safeReturnTo(form.get("returnTo"));
    const callbackUrl = new URL(
      "/api/auth/descope/wechat/callback",
      trustedPublicOrigin(request),
    ).toString();
    const started = await startDescopeWechat(callbackUrl);
    const { sealedFlow } = createDescopeOauthFlow({
      provider: started.provider,
      intent,
      returnTo,
    });
    const response = NextResponse.redirect(started.authorizationUrl, 303);
    response.cookies.set(accountCookieNames.descopeOauthFlow, sealedFlow, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: 10 * 60,
    });
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error
      ? String(error.code)
      : "DESCOPE_WECHAT_START_REJECTED";
    try {
      return errorRedirect(request, code, intent);
    } catch (redirectError) {
      return accountSessionErrorResponse(redirectError);
    }
  }
}
