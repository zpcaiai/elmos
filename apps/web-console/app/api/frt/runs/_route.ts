import { NextRequest, NextResponse } from "next/server";

import {
  createFrtConsoleRun,
  FrtEngineProxyError,
} from "../../../lib/server/frtEngineProxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  try {
    if (!request.headers.get("content-type")?.startsWith("application/json")) {
      return NextResponse.json({ status: "BLOCKED", reason: "JSON_CONTENT_TYPE_REQUIRED" }, { status: 415 });
    }
    const raw = await request.text();
    if (Buffer.byteLength(raw, "utf8") > 2 * 1024 * 1024) {
      return NextResponse.json({ status: "BLOCKED", reason: "REQUEST_TOO_LARGE" }, { status: 413 });
    }
    const result = await createFrtConsoleRun(request, JSON.parse(raw));
    return NextResponse.json(result.body, {
      status: result.status,
      headers: { "cache-control": "private, no-store" },
    });
  } catch (error) {
    const status = error instanceof FrtEngineProxyError ? error.status : 400;
    const reason = error instanceof FrtEngineProxyError ? error.code : "FRT_CONSOLE_REQUEST_REJECTED";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
