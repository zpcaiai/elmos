import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieDeletionOptions,
  accountCookieNames,
  accountSessionErrorResponse,
  assertLocalCredentialRequest,
  assertSameOriginMutation,
  authenticateLocalCredentials,
  localAccountCookieNames,
  localAccountCookieOptions,
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
    && !value.startsWith("/admin")
    && !/[\\\r\n\0]/.test(value)
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

async function registrationFields(request: NextRequest): Promise<{
  username: string;
  password: string;
  passwordConfirmation: string;
  displayName: string;
  email: string;
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
      email: typeof body.email === "string" ? body.email : "",
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
    email: typeof email === "string" ? email : "",
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
    const result = authenticateLocalCredentials(fields.email, fields.password);
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
    setLocalSessionCookies(request, response, result);
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
