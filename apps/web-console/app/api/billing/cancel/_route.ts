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

export async function POST(request: NextRequest) {
  const idempotencyKey = request.headers.get("idempotency-key") ?? "";
  if (!idempotencyPattern.test(idempotencyKey)) {
    return NextResponse.json({
      status: "ERROR",
      code: "IDEMPOTENCY_KEY_INVALID",
      message: "取消订阅请求标识无效。",
      retryable: false,
    }, { status: 400, headers: privateHeaders });
  }
  try {
    const response = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/subscriptions/cancel",
      { method: "POST", idempotencyKey },
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
