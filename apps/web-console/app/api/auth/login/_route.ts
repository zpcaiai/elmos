import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountCookieDeletionOptions,
  accountSessionErrorResponse,
  AccountSessionError,
  assertLoginModeAccess,
  assertLocalCredentialRequest,
  assertSameOriginMutation,
  authenticateLocalCredentials,
  authorizationFlowCookieMaxAge,
  createAuthorizationFlow,
  isPlatformAdministrator,
  localAccountCookieNames,
  localAccountCookieOptions,
  sessionCookieMaxAge,
  trustedPublicOrigin,
  type AccountLoginMode,
} from "../../../lib/server/accountSession";
import { notifyAdministratorLogin } from "../../../lib/server/adminLoginNotification";
import {
  isPlatformOperationsSurface,
  safeOperationsReturnTo,
} from "../../../lib/surfaceAudience";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function safeReturnTo(value: unknown): string {
  return typeof value === "string"
    && value.startsWith("/")
    && !value.startsWith("//")
    && !/[\\\r\n\0]/.test(value)
    ? value
    : "/";
}

function loginMode(value: unknown): AccountLoginMode {
  if (value === undefined || value === null || value === "" || value === "USER") return "USER";
  if (value === "ADMIN") return "ADMIN";
  throw new AccountSessionError(400, "LOGIN_MODE_INVALID", "登录入口无效。");
}

function localLoginError(
  request: NextRequest,
  code: string,
  mode: AccountLoginMode,
): NextResponse {
  const target = new URL(mode === "ADMIN" ? "/admin/login" : "/login", trustedPublicOrigin(request));
  target.searchParams.set("error", code);
  const response = NextResponse.redirect(target, 303);
  response.headers.set("Cache-Control", "no-store, private");
  return response;
}

function setLocalSessionCookies(
  request: NextRequest,
  response: NextResponse,
  result: ReturnType<typeof authenticateLocalCredentials>,
): void {
  const maxAge = sessionCookieMaxAge(result.expiresAt);
  const options = localAccountCookieOptions(request);
  response.cookies.set(localAccountCookieNames.session, result.session, {
    ...options,
    maxAge,
  });
  response.cookies.set(localAccountCookieNames.accessToken, result.accessToken, {
    ...options,
    maxAge,
  });
  for (const name of Object.values(accountCookieNames)) {
    response.cookies.set(name, "", accountCookieDeletionOptions(name));
  }
}

async function loginFields(request: NextRequest): Promise<{
  email: string;
  password: string;
  returnTo: string;
  loginMode: AccountLoginMode;
}> {
  const contentLength = Number(request.headers.get("content-length") ?? "");
  if (Number.isFinite(contentLength) && contentLength > 16 * 1024) {
    throw new Error("LOCAL_CREDENTIALS_REQUEST_TOO_LARGE");
  }
  if ((request.headers.get("content-type") ?? "").includes("application/json")) {
    const body = await request.json() as Record<string, unknown>;
    return {
      email: typeof body.email === "string"
        ? body.email
        : typeof body.username === "string" ? body.username : "",
      password: typeof body.password === "string" ? body.password : "",
      returnTo: safeReturnTo(body.returnTo),
      loginMode: loginMode(body.loginMode),
    };
  }
  const form = await request.formData();
  const email = form.get("email") ?? form.get("username");
  const password = form.get("password");
  const returnTo = form.get("returnTo");
  return {
    email: typeof email === "string" ? email : "",
    password: typeof password === "string" ? password : "",
    returnTo: safeReturnTo(returnTo),
    loginMode: loginMode(form.get("loginMode")),
  };
}

export async function GET(request: NextRequest) {
  try {
    const mode = loginMode(request.nextUrl.searchParams.get("mode"));
    const { sealedFlow, authorizationUrl } = createAuthorizationFlow(
      request.nextUrl.searchParams.get("returnTo") ?? "/",
      mode,
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
  const jsonResponse = (request.headers.get("content-type") ?? "").includes("application/json");
  let mode: AccountLoginMode = "USER";
  try {
    assertSameOriginMutation(request);
    assertLocalCredentialRequest(request);
    const fields = await loginFields(request);
    mode = fields.loginMode;
    const result = authenticateLocalCredentials(fields.email, fields.password);
    assertLoginModeAccess(result.principal, mode);
    // Administrators land on a platform operations surface; customer sessions
    // are never redirected onto one, whatever returnTo asked for.
    const returnTo = mode === "ADMIN"
      ? safeOperationsReturnTo(fields.returnTo)
      : isPlatformOperationsSurface(fields.returnTo) ? "/" : fields.returnTo;
    const notification = isPlatformAdministrator(result.principal)
      ? await notifyAdministratorLogin(
        request,
        result.principal,
        "LOCAL_DEVELOPMENT_CREDENTIAL",
      )
      : null;
    const response = jsonResponse
      ? NextResponse.json({
        authenticated: true,
        authentication: "LOCAL_DEVELOPMENT_CREDENTIAL",
        principal: result.principal,
        expiresAt: new Date(result.expiresAt).toISOString(),
        adminLoginNotification: notification
          ? { status: "ACCEPTED", eventId: notification.eventId }
          : null,
      })
      : NextResponse.redirect(
        new URL(returnTo, trustedPublicOrigin(request)),
        303,
      );
    setLocalSessionCookies(request, response, result);
    if (notification) {
      response.headers.set("X-ELMOS-Admin-Login-Notification", "ACCEPTED");
    }
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    if (jsonResponse) return accountSessionErrorResponse(error);
    try {
      const code = error && typeof error === "object" && "code" in error
        ? String(error.code)
        : "LOCAL_CREDENTIALS_UNAVAILABLE";
      return localLoginError(request, code, mode);
    } catch (redirectError) {
      return accountSessionErrorResponse(redirectError);
    }
  }
}
