import { NextRequest, NextResponse } from "next/server";
import {
  accountSessionFromRequest,
  oidcConfigured,
} from "../../../lib/server/accountSession";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const session = accountSessionFromRequest(request);
    return NextResponse.json(
      {
        authenticated: true,
        configured: true,
        principal: session.principal,
        expiresAt: new Date(session.expiresAt).toISOString(),
      },
      {
        headers: {
          "Cache-Control": "no-store, private",
          "Vary": "Cookie",
        },
      },
    );
  } catch {
    return NextResponse.json(
      {
        authenticated: false,
        configured: oidcConfigured(),
        principal: null,
        expiresAt: null,
      },
      {
        headers: {
          "Cache-Control": "no-store, private",
          "Vary": "Cookie",
        },
      },
    );
  }
}
