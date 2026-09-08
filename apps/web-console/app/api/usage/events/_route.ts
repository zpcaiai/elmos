import { NextRequest, NextResponse } from "next/server";
import { commercialBillingRequest, proxyError } from "../../../lib/server/commercialBillingProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const headers = { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie, Authorization" };

export async function GET(request: NextRequest) {
  try {
    const from = request.nextUrl.searchParams.get("from") ?? "";
    const to = request.nextUrl.searchParams.get("to") ?? "";
    const scope = request.nextUrl.searchParams.get("scope") ?? "SELF";
    const limit = request.nextUrl.searchParams.get("limit") ?? "100";
    const offset = request.nextUrl.searchParams.get("offset") ?? "0";
    if (!Number.isFinite(Date.parse(from)) || !Number.isFinite(Date.parse(to))
      || !["SELF", "ORGANIZATION"].includes(scope)
      || !/^\d{1,3}$/.test(limit) || Number(limit) < 1 || Number(limit) > 500
      || !/^\d+$/.test(offset)) {
      return NextResponse.json({ code: "USAGE_EVENTS_QUERY_INVALID" }, { status: 400, headers });
    }
    const query = new URLSearchParams({ from, to, scope, limit, offset });
    const response = await commercialBillingRequest(
      request, `/commercial/v1/billing/usage/events?${query}`,
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
