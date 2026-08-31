import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieDeletionOptions,
  accountCookieNames,
  accountSessionErrorResponse,
  assertLocalCredentialRequest,
  assertSameOriginMutation,
  authenticateLocalCredentials,
  registerLocalAccount,
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

function registrationError(request: NextRequest, code: string): NextResponse {
  const target = new URL("/register", trustedPublicOrigin(request));
  target.searchParams.set("error", code);
  const returnTo = request.nextUrl.searchParams.get("returnTo");
  if (returnTo) target.searchParams.set("returnTo", safeReturnTo(returnTo));
  const response = NextResponse.redirect(target, 303);
  response.headers.set("Cache-Control", "no-store, private");
  return response;
}

function setLocalSessionCookies(
  response: NextResponse,
  result: ReturnType<typeof authenticateLocalCredentials>,
): void {
  const maxAge = sessionCookieMaxAge(result.expiresAt);
  response.cookies.set(accountCookieNames.session, result.session, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge,
  });
  response.cookies.set(accountCookieNames.accessToken, result.accessToken, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
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

async function registrationFields(request: NextRequest): Promise<{
  username: string;
  password: string;
  passwordConfirmation: string;
  displayName: string;
  email?: string;
  returnTo: string;
}> {
  const contentLength = Number(request.headers.get("content-length") ?? "");
  if (Number.isFinite(contentLength) && contentLength > 16 * 1024) {
    throw new Error("LOCAL_REGISTRATION_REQUEST_TOO_LARGE");
  }
  if ((request.headers.get("content-type") ?? "").includes("application/json")) {
    const body = await request.json() as Record<string, unknown>;
    return {
      username: typeof body.username === "string" ? body.username : "",
      password: typeof body.password === "string" ? body.password : "",
      passwordConfirmation: typeof body.passwordConfirmation === "string"
        ? body.passwordConfirmation
        : "",
      displayName: typeof body.displayName === "string" ? body.displayName : "",
      email: typeof body.email === "string" ? body.email : undefined,
      returnTo: safeReturnTo(body.returnTo),
    };
  }
  const form = await request.formData();
  const username = form.get("username");
  const password = form.get("password");
  const passwordConfirmation = form.get("passwordConfirmation");
  const displayName = form.get("displayName");
  const email = form.get("email");
  const returnTo = form.get("returnTo");
  return {
    username: typeof username === "string" ? username : "",
    password: typeof password === "string" ? password : "",
    passwordConfirmation: typeof passwordConfirmation === "string" ? passwordConfirmation : "",
    displayName: typeof displayName === "string" ? displayName : "",
    email: typeof email === "string" && email ? email : undefined,
    returnTo: safeReturnTo(returnTo),
  };
}

export async function POST(request: NextRequest) {
  const jsonResponse = (request.headers.get("content-type") ?? "").includes("application/json");
  try {
    assertSameOriginMutation(request);
    assertLocalCredentialRequest(request);
    const fields = await registrationFields(request);
    registerLocalAccount(fields);
    const result = authenticateLocalCredentials(fields.username, fields.password);
    const response = jsonResponse
      ? NextResponse.json({
        registered: true,
        authenticated: true,
        authentication: "LOCAL_DEVELOPMENT_CREDENTIAL",
        principal: result.principal,
        expiresAt: new Date(result.expiresAt).toISOString(),
      })
      : NextResponse.redirect(
        new URL(fields.returnTo, trustedPublicOrigin(request)),
        303,
      );
    setLocalSessionCookies(response, result);
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    if (jsonResponse) return accountSessionErrorResponse(error);
    try {
      const code = error && typeof error === "object" && "code" in error
        ? String(error.code)
        : "LOCAL_REGISTRATION_UNAVAILABLE";
      return registrationError(request, code);
    } catch (redirectError) {
      return accountSessionErrorResponse(redirectError);
    }
  }
}
