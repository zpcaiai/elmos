import { NextRequest, NextResponse } from "next/server";
import {
  commercialBillingRequest,
  proxyError,
} from "../../../../lib/server/commercialBillingProxy";
import {
  requireTopupOrderId,
  WalletTopupPolicyError,
} from "../../../../lib/server/walletTopupPolicy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Cookie, Authorization",
};

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ topupOrderId: string }> },
) {
  try {
    const { topupOrderId } = await context.params;
    const safeOrderId = requireTopupOrderId(topupOrderId);
    const response = await commercialBillingRequest(
      request,
      `/commercial/v1/billing/wallet/topup/${encodeURIComponent(safeOrderId)}`,
    );
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { ...privateHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    if (error instanceof WalletTopupPolicyError) {
      return NextResponse.json({
        status: "ERROR",
        code: error.code,
        message: error.message,
        retryable: error.retryable,
      }, { status: error.status, headers: privateHeaders });
    }
    const mapped = proxyError(error);
    return NextResponse.json(mapped.body, {
      status: mapped.status,
      headers: privateHeaders,
    });
  }
}
