import { NextRequest, NextResponse } from "next/server";
import {
  commercialBillingRequest,
  proxyError,
} from "../../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Cookie, Authorization",
};

export async function GET(request: NextRequest) {
  try {
    const response = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/subscriptions/current",
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
