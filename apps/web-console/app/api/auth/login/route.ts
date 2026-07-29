import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountSessionErrorResponse,
  authorizationFlowCookieMaxAge,
  createAuthorizationFlow,
} from "../../../lib/server/accountSession";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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
