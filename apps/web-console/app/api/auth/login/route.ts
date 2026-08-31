import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountCookieDeletionOptions,
  accountSessionErrorResponse,
  assertLocalCredentialRequest,
  assertSameOriginMutation,
  authenticateLocalCredentials,
  authorizationFlowCookieMaxAge,
  createAuthorizationFlow,
  localAccountCookieNames,
  localAccountCookieOptions,
  sessionCookieMaxAge,
  trustedPublicOrigin,
} from "../../../lib/server/accountSession";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function safeReturnTo(value: unknown): string {
  return typeof value === "string"
    && value.startsWith("/")
    && !value.startsWith("//")
    && !/[\r\n\0]/.test(value)
    ? value
    : "/";
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
  response.cookies.set(localAccountCookieNames.session, result.session, {
    ...options,
    maxAge,
  });
  response.cookies.set(localAccountCookieNames.accessToken, result.accessToken, {
    ...options,
    maxAge,
  });
  for (const name of [
    accountCookieNames.refreshToken,
    accountCookieNames.authorizationFlow,
    accountCookieNames.tenant,
  ]) {
    response.cookies.set(name, "", accountCookieDeletionOptions(name));
  }
}

async function loginFields(request: NextRequest): Promise<{
  username: string;
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
      username: typeof body.username === "string" ? body.username : "",
      password: typeof body.password === "string" ? body.password : "",
      returnTo: safeReturnTo(body.returnTo),
    };
  }
  const form = await request.formData();
  const username = form.get("username");
  const password = form.get("password");
  const returnTo = form.get("returnTo");
  return {
    username: typeof username === "string" ? username : "",
    password: typeof password === "string" ? password : "",
    returnTo: safeReturnTo(returnTo),
  };
}

export async function GET(request: NextRequest) {
  try {
    const { sealedFlow, authorizationUrl } = createAuthorizationFlow(
      request.nextUrl.searchParams.get("returnTo") ?? "/",
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
    const result = authenticateLocalCredentials(fields.username, fields.password);
    const response = jsonResponse
      ? NextResponse.json({
        authenticated: true,
        authentication: "LOCAL_DEVELOPMENT_CREDENTIAL",
        principal: result.principal,
        expiresAt: new Date(result.expiresAt).toISOString(),
      })
      : NextResponse.redirect(
        new URL(fields.returnTo, trustedPublicOrigin(request)),
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
