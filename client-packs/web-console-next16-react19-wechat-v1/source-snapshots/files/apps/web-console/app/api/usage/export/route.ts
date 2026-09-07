import { NextRequest, NextResponse } from "next/server";
import {
  commercialBillingRequest,
  proxyError,
} from "../../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  try {
    const from = request.nextUrl.searchParams.get("from") ?? "";
    const to = request.nextUrl.searchParams.get("to") ?? "";
    const bucket = request.nextUrl.searchParams.get("bucket") ?? "DAY";
    if (!Number.isFinite(Date.parse(from)) || !Number.isFinite(Date.parse(to))
      || !["HOUR", "DAY"].includes(bucket)) {
      return NextResponse.json({
        code: "USAGE_EXPORT_QUERY_INVALID",
        message: "用量导出范围无效。",
        retryable: false,
        status: "ERROR",
      }, { status: 400 });
    }
    const query = new URLSearchParams({ from, to, bucket });
    const response = await commercialBillingRequest(
      request,
      `/commercial/v1/billing/usage/export?${query}`,
      { accept: "text/csv" },
    );
    return new NextResponse(await response.arrayBuffer(), {
      status: response.status,
      headers: {
        "Cache-Control": "private, no-store, max-age=0",
        "Content-Type": response.headers.get("content-type") ?? "text/csv;charset=UTF-8",
        "Content-Disposition": "attachment; filename=\"elmos-usage.csv\"",
        "Vary": "Cookie, Authorization",
      },
    });
  } catch (error) {
    const mapped = proxyError(error);
    return NextResponse.json(mapped.body, { status: mapped.status });
  }
}
