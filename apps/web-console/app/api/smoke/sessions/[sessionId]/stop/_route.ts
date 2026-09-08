import { NextRequest, NextResponse } from "next/server";
import { GenerationRunnerError } from "../../../../../lib/server/generationRunner";
import { withBusinessAudit } from "../../../../../lib/server/operationsProxy";
import { authorizeSmoke, stopSmokeSession } from "../../../../../lib/server/smokeLeaseRunner";
import { BoundedJsonError, readBoundedJson } from "../../../../../lib/server/boundedJson";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  try {
    return await withBusinessAudit(
      request,
      {
        action: "SMOKE_SESSION_STOP",
        businessLine: "RUNNABLE_SMOKE",
        route: "/api/smoke/sessions/:id/stop",
        target: "smoke-session",
      },
      () => stop(request, context),
    );
  } catch {
    return NextResponse.json(
      { status: "BLOCKED", reason: "BUSINESS_AUDIT_UNAVAILABLE" },
      { status: 503 },
    );
  }
}

async function stop(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  try {
    const authorized = authorizeSmoke(request);
    const { sessionId } = await context.params;
    const payload = await readBoundedJson(request, 4 * 1024);
    return NextResponse.json(await stopSmokeSession(authorized, sessionId, payload));
  } catch (error) {
    const status = error instanceof GenerationRunnerError || error instanceof BoundedJsonError ? error.status : 500;
    const reason = error instanceof Error ? error.message : "SMOKE_SESSION_STOP_FAILED";
    return NextResponse.json({ status: "BLOCKED", reason }, { status });
  }
}
