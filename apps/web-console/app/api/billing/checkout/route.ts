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
const idempotencyPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$/;
const paidPlans = new Set(["elmos-pro-monthly", "elmos-pro-annual"]);

export async function POST(request: NextRequest) {
  const idempotencyKey = request.headers.get("idempotency-key") ?? "";
  if (!idempotencyPattern.test(idempotencyKey)) {
    return NextResponse.json({
      status: "ERROR",
      code: "IDEMPOTENCY_KEY_INVALID",
      message: "结账请求标识无效。",
      retryable: false,
    }, { status: 400, headers: privateHeaders });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = null;
  }
  const planId = typeof body === "object" && body !== null
    ? (body as Record<string, unknown>).planId
    : null;
  if (typeof planId !== "string" || !paidPlans.has(planId)) {
    return NextResponse.json({
      status: "ERROR",
      code: "CHECKOUT_PLAN_INVALID",
      message: "请选择有效的人民币付费套餐。",
      retryable: false,
    }, { status: 400, headers: privateHeaders });
  }
  try {
    const response = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/checkout",
      {
        method: "POST",
        idempotencyKey,
        body: JSON.stringify({ planId }),
      },
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
