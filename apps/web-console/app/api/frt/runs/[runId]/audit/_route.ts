import { NextRequest, NextResponse } from "next/server";

import { FrtEngineProxyError, getFrtConsoleRun } from "../../../../../lib/server/frtEngineProxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ runId: string }> },
) {
  try {
    const { runId } = await context.params;
    if (!/^[a-f0-9]{24}$/.test(runId)) throw new FrtEngineProxyError(400, "FRT_RUN_ID_INVALID");
    const result = await getFrtConsoleRun(request, runId, "/audit");
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
