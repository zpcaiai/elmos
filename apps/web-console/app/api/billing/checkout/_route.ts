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

/**
 * D-01（2026-07-28）之后，结账响应有两种互斥形态：
 *
 *   跳转型（Stripe / 支付宝）→ checkoutUrl
 *   扫码型（微信 Native）    → qrCodeUrl
 *
 * 本路由不再把上游响应原样透传，而是先确认它<b>恰好</b>是其中一种。
 * 理由：透传意味着上游一旦返回一个既没有 checkoutUrl 也没有 qrCodeUrl 的
 * "成功"响应，前端只会显示一个什么都不做的按钮——用户以为系统坏了，
 * 我们这边一条错误日志都没有。校验在这里做，故障就变成一条明确的错误码。
 */
const PAYMENT_PROVIDERS = new Set([
  "STRIPE_CHECKOUT",
  "ALIPAY_CHECKOUT",
  "WECHAT_PAY_NATIVE",
]);

type CheckoutShape = {
  paymentProvider?: unknown;
  checkoutUrl?: unknown;
  qrCodeUrl?: unknown;
};

function describeShapeProblem(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) {
    return "结账响应不是对象";
  }
  const body = payload as CheckoutShape;
  const provider = body.paymentProvider;
  if (typeof provider !== "string" || !PAYMENT_PROVIDERS.has(provider)) {
    return "结账响应缺少可识别的 paymentProvider";
  }
  const hasRedirect = typeof body.checkoutUrl === "string" && body.checkoutUrl.length > 0;
  const hasQrCode = typeof body.qrCodeUrl === "string" && body.qrCodeUrl.length > 0;
  if (hasRedirect === hasQrCode) {
    // 两个都有同样是错误：说明上游对该订单到底走哪条路自己都没定，
    // 前端选哪个都可能选错。这和两个都没有一样必须挡下。
    return hasRedirect
      ? "结账响应同时给了跳转地址与二维码，无法判定支付方式"
      : "结账响应既没有跳转地址也没有二维码";
  }
  if (provider === "WECHAT_PAY_NATIVE" && !hasQrCode) {
    return "微信 Native 支付必须返回二维码内容";
  }
  if (provider !== "WECHAT_PAY_NATIVE" && !hasRedirect) {
    return `${provider} 必须返回跳转地址`;
  }
  return null;
}

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
    const text = await response.text();

    // 只校验成功响应。上游的错误响应有自己的结构（code/message/retryable），
    // 原样透传，不要在这里二次包装——那会把上游的错误码吃掉。
    if (response.ok) {
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = null;
      }
      const problem = describeShapeProblem(parsed);
      if (problem) {
        return NextResponse.json({
          status: "ERROR",
          code: "CHECKOUT_RESPONSE_UNUSABLE",
          // 对用户说人话，具体原因留在 detail 里给排障用，不含上游原文
          message: "支付服务返回了无法使用的结账信息，未发起支付。",
          detail: problem,
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
