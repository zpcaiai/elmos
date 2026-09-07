import { NextRequest, NextResponse } from "next/server";
import {
  commercialBillingRequest,
  proxyError,
} from "../../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const headers = {
  "Cache-Control": "private, no-store, max-age=0",
  "Vary": "Cookie, Authorization",
};

export async function GET(request: NextRequest) {
  try {
    const from = request.nextUrl.searchParams.get("from") ?? "";
    const to = request.nextUrl.searchParams.get("to") ?? "";
    const bucket = request.nextUrl.searchParams.get("bucket") ?? "DAY";
    if (!Number.isFinite(Date.parse(from)) || !Number.isFinite(Date.parse(to))
      || !["HOUR", "DAY"].includes(bucket)) {
      return NextResponse.json({
        code: "USAGE_HISTORY_QUERY_INVALID",
        message: "用量历史查询范围无效。",
        retryable: false,
        status: "ERROR",
      }, { status: 400, headers });
    }
    const query = new URLSearchParams({ from, to, bucket });
    const response = await commercialBillingRequest(
      request,
      `/commercial/v1/billing/usage/history?${query}`,
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
