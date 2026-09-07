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
  localAccountCookieNames,
  localAccountCookieOptions,
  sessionCookieMaxAge,
  trustedPublicOrigin,
  type AccountLoginMode,
} from "../../../lib/server/accountSession";
import { isPlatformOperationsSurface } from "../../../lib/surfaceAudience";

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

// The user login entry only ever establishes a USER flow. Administrator
// sign-in has its own entry at /api/auth/admin/login and is refused here.
function userLoginMode(value: unknown): AccountLoginMode {
  if (value === undefined || value === null || value === "" || value === "USER") return "USER";
  throw new AccountSessionError(400, "LOGIN_MODE_INVALID", "用户登录入口不支持该登录模式。");
}

function localLoginError(request: NextRequest, code: string): NextResponse {
  const target = new URL("/login", trustedPublicOrigin(request));
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
  response.cookies.set(localAccountCookieNames.administratorSession, "", { ...options, maxAge: 0 });
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
  };
}

export async function GET(request: NextRequest) {
  try {
    const mode = userLoginMode(request.nextUrl.searchParams.get("mode"));
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
  try {
    assertSameOriginMutation(request);
    assertLocalCredentialRequest(request);
    const fields = await loginFields(request);
    const result = authenticateLocalCredentials(fields.email, fields.password);
    // Local credentials can only ever mint a customer session; the platform
    // administrator is rejected before any cookie or session is issued.
    assertLoginModeAccess(result.principal, "USER");
    // A user session is never redirected onto a platform operations surface.
    const returnTo = isPlatformOperationsSurface(fields.returnTo) ? "/" : fields.returnTo;
    const response = jsonResponse
      ? NextResponse.json({
        authenticated: true,
        authentication: "LOCAL_DEVELOPMENT_CREDENTIAL",
        principal: result.principal,
        expiresAt: new Date(result.expiresAt).toISOString(),
      })
      : NextResponse.redirect(
        new URL(returnTo, trustedPublicOrigin(request)),
        303,
      );
    setLocalSessionCookies(request, response, result);
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    if (jsonResponse) return accountSessionErrorResponse(error);
    try {
      const code = error && typeof error === "object" && "code" in error
        ? String(error.code)
        : "LOCAL_CREDENTIALS_UNAVAILABLE";
      return localLoginError(request, code);
    } catch (redirectError) {
      return accountSessionErrorResponse(redirectError);
    }
  }
}
