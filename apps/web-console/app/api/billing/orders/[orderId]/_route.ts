import { NextRequest, NextResponse } from "next/server";
import { commercialBillingRequest, proxyError } from "../../../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const headers = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie, Authorization",
};

const orderIdPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ orderId: string }> },
) {
  try {
    const { orderId } = await context.params;
    if (!orderIdPattern.test(orderId)) {
      return NextResponse.json(
        { code: "COMMERCIAL_ORDER_ID_INVALID" },
        { status: 400, headers },
      );
    }
    const response = await commercialBillingRequest(
      request,
      `/commercial/v1/billing/orders/${encodeURIComponent(orderId)}`,
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
