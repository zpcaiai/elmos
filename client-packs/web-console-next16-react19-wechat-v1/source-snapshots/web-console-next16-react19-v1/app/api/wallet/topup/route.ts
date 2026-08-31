import { NextRequest, NextResponse } from "next/server";
import {
  commercialBillingRequest,
  proxyError,
} from "../../../lib/server/commercialBillingProxy";
import {
  describeTopupHandoffProblem,
  requireTopupAmountMinor,
  requireTopupIdempotencyKey,
  WalletTopupPolicyError,
} from "../../../lib/server/walletTopupPolicy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Cookie, Authorization",
};

function policyResponse(error: WalletTopupPolicyError): NextResponse {
  return NextResponse.json({
    status: "ERROR",
    code: error.code,
    message: error.message,
    retryable: error.retryable,
  }, { status: error.status, headers: privateHeaders });
}

export async function POST(request: NextRequest) {
  let idempotencyKey: string;
  let amountMinor: number;
  try {
    idempotencyKey = requireTopupIdempotencyKey(request.headers.get("idempotency-key"));
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      body = null;
    }
    amountMinor = requireTopupAmountMinor(body);
  } catch (error) {
    if (error instanceof WalletTopupPolicyError) return policyResponse(error);
    throw error;
  }

  try {
    const response = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/wallet/topup",
      {
        method: "POST",
        idempotencyKey,
        body: JSON.stringify({ amountMinor }),
      },
    );
    const text = await response.text();

    // 只校验成功响应。上游错误有自己的 code/message/retryable，原样透传，
    // 在这里二次包装会把上游的错误码吃掉——而余额不足(402)、超单日上限(429)、
    // 钱包冻结(409) 恰恰是前端需要分开处理的三件事。
    if (response.ok) {
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = null;
      }
      const problem = describeTopupHandoffProblem(parsed);
      if (problem) {
        return NextResponse.json({
          status: "ERROR",
          code: "TOPUP_HANDOFF_UNUSABLE",
          message: "支付渠道返回了无法使用的充值信息，未发起支付。",
          detail: problem,
          // 订单已经在服务端建好并停在 CREATED，由过期机制收口。
          // 重试要带同一个 Idempotency-Key，否则会开出第二笔可付款的单，
          // 所以这里标不可重试——由前端保留原键后决定，而不是自动重发。
          retryable: false,
        }, { status: 502, headers: privateHeaders });
      }
    }

    return new NextResponse(text, {
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
