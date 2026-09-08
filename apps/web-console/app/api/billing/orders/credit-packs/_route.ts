import { NextRequest, NextResponse } from "next/server";
import { commercialBillingRequest, proxyError } from "../../../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie, Authorization" };

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => null) as { sku?: unknown } | null;
    const key = request.headers.get("idempotency-key") ?? "";
    if (body?.sku !== "elmos-credit-500" || key.length < 8 || key.length > 160) {
      return NextResponse.json({ code: "COMMERCIAL_ORDER_REQUEST_INVALID" }, { status: 400, headers });
    }
    const response = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/orders/credit-packs",
      { method: "POST", idempotencyKey: key, body: JSON.stringify({ sku: body.sku }) },
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
