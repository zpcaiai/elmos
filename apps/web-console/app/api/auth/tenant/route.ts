import { NextRequest, NextResponse } from "next/server";
import {
  accountCookieNames,
  accountSessionErrorResponse,
  accountSessionFromRequest,
  selectTenantCookie,
  sessionCookieMaxAge,
} from "../../../lib/server/accountSession";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const session = accountSessionFromRequest(request);
    const body = await request.json() as { organizationId?: unknown };
    if (typeof body.organizationId !== "string") {
      return NextResponse.json(
        { errorCode: "TENANT_SELECTION_INVALID", message: "租户选择无效。" },
        { status: 400 },
      );
    }
    const response = NextResponse.json({ switched: true, organizationId: body.organizationId });
    response.cookies.set(
      accountCookieNames.tenant,
      selectTenantCookie(session.principal, body.organizationId, session.expiresAt),
      {
        httpOnly: true,
        secure: true,
        sameSite: "lax",
        path: "/",
        maxAge: sessionCookieMaxAge(session.expiresAt),
      },
    );
    response.headers.set("Cache-Control", "no-store, private");
    return response;
  } catch (error) {
    return accountSessionErrorResponse(error);
  }
}
