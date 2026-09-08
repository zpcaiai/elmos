import { NextRequest, NextResponse } from "next/server";
import { commercialBillingRequest, proxyError } from "../../../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie, Authorization" };

export async function GET(request: NextRequest) {
  try {
    const response = await commercialBillingRequest(
      request, "/commercial/v1/billing/credits/ledger?scope=SELF&limit=100&offset=0",
    );
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { ...headers, "Content-Type": "application/json" },
    });
  } catch (error) {
    const mapped = proxyError(error);
    return NextResponse.json(mapped.body, { status: mapped.status, headers });
  }
}
