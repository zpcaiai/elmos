import { NextRequest, NextResponse } from "next/server";
import {
  commercialBillingRequest,
  proxyError,
} from "../../../lib/server/commercialBillingProxy";
import { boundedLedgerParam } from "../../../lib/server/walletTopupPolicy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Cookie, Authorization",
};

export async function GET(request: NextRequest) {
  try {
    const params = request.nextUrl.searchParams;
    const limit = boundedLedgerParam(params.get("limit"), 50, 200);
    const offset = boundedLedgerParam(params.get("offset"), 0, 100_000);
    const response = await commercialBillingRequest(
      request,
      `/commercial/v1/billing/wallet/ledger?limit=${limit}&offset=${offset}`,
    );
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { ...privateHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    const mapped = proxyError(error);
    return NextResponse.json(mapped.body, {
      status: mapped.status,
      headers: privateHeaders,
    });
  }
}
