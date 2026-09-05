import { NextRequest, NextResponse } from "next/server";
import {
  commercialBillingRequest,
  proxyError,
} from "../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const privateHeaders = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Cookie, Authorization",
};

/**
 * 余额与充值上下限。
 *
 * <p>上下限跟余额一起返回，不做成独立端点：前端需要它们才能画出「最少充多少」
 * 的输入框，分两次取意味着存在一个短暂的窗口，界面上的限额和服务端将要执行的
 * 限额不是同一套。真正的强制在 V73 的 elmos_wallet_create_topup_order 里，
 * 这里拿到的只是用来提前告诉用户，不是权威。
 */
export async function GET(request: NextRequest) {
  try {
    const response = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/wallet",
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
