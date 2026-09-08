import { NextRequest, NextResponse } from "next/server";
import { commercialBillingRequest, proxyError } from "../../../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie, Authorization" };
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => null) as {
      sku?: unknown; projectId?: unknown;
    } | null;
    const key = request.headers.get("idempotency-key") ?? "";
    if (body?.sku !== "elmos-project-generation-once"
      || typeof body.projectId !== "string" || !ID.test(body.projectId)
      || key.length < 8 || key.length > 160) {
      return NextResponse.json({ code: "COMMERCIAL_ORDER_REQUEST_INVALID" }, { status: 400, headers });
    }
    const response = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/orders/project-generations",
      {
        method: "POST",
        idempotencyKey: key,
        body: JSON.stringify({ sku: body.sku, projectId: body.projectId }),
      },
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
