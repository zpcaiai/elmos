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

async function forward(request: NextRequest, method: "GET" | "PUT") {
  try {
    const body = method === "PUT" ? await request.text() : undefined;
    const response = await commercialBillingRequest(
      request,
      "/commercial/v1/billing/usage/alerts",
      { method, body },
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

export async function GET(request: NextRequest) {
  return forward(request, "GET");
}

export async function PUT(request: NextRequest) {
  return forward(request, "PUT");
}
